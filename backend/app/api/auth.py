"""Credential sign-in, session endpoints, and linking a GitHub identity via the GitHub App install."""

from __future__ import annotations

import hmac
import logging
import secrets
from typing import Literal
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, DbSession, csrf_protect, is_admin
from app.core.config import get_settings
from app.core.database import SessionLocal, utcnow
from app.core.security import (
    OAUTH_STATE_COOKIE,
    SESSION_COOKIE,
    create_session_token,
    decode_session_token,
    encrypt_token,
)
from app.models import User
from app.schemas.auth import LoginIn, UserOut
from app.services import access, accounts, github_user
from app.services.errors import ServiceError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

STATE_MAX_AGE = 600
AFTER_LINK = "/dashboard"


def _callback_url() -> str:
    return f"{get_settings().API_BASE_URL.rstrip('/')}/api/v1/auth/callback"


def _frontend(path: str) -> str:
    return f"{get_settings().FRONTEND_ORIGIN.rstrip('/')}{path}"


def _cookie_kwargs() -> dict:
    return {"httponly": True, "samesite": "lax", "secure": get_settings().is_production, "path": "/"}


def _user_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.is_admin = is_admin(user)
    out.github_linked = bool(user.access_token)
    return out


def _session_user_id(request: Request) -> int | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        return int(decode_session_token(token)["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


@router.post("/login", response_model=UserOut, dependencies=[Depends(csrf_protect)])
def login(body: LoginIn, db: DbSession, response: Response) -> UserOut:
    if accounts.throttle.blocked(body.username):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later")
    user = accounts.authenticate(db, body.username, body.password)
    if user is None:
        accounts.throttle.record_failure(body.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    accounts.throttle.reset(body.username)
    user.last_login_at = utcnow()
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user.id, user.username),
        max_age=get_settings().SESSION_TTL_HOURS * 3600,
        **_cookie_kwargs(),
    )
    return _user_out(user)


def _authorize_redirect(state: str) -> RedirectResponse:
    settings = get_settings()
    query = urlencode(
        {"client_id": settings.GITHUB_CLIENT_ID, "redirect_uri": _callback_url(), "state": state, "scope": "read:user"}
    )
    return RedirectResponse(f"{settings.GITHUB_OAUTH_URL}/login/oauth/authorize?{query}", status.HTTP_302_FOUND)


@router.get("/github/connect")
def github_connect(request: Request, mode: Literal["install", "authorize"] = "install") -> RedirectResponse:
    """Start linking the signed-in user's GitHub identity: install the App, or authorize when already installed."""
    if _session_user_id(request) is None:
        return RedirectResponse(_frontend("/login?next=/dashboard"), status.HTTP_302_FOUND)
    settings = get_settings()
    if not settings.oauth_configured or (mode == "install" and not settings.GITHUB_APP_SLUG):
        return RedirectResponse(_frontend(f"{AFTER_LINK}?github_error=not_configured"), status.HTTP_302_FOUND)
    state = secrets.token_urlsafe(32)
    if mode == "install":
        query = urlencode({"state": state})
        response = RedirectResponse(
            f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new?{query}", status.HTTP_302_FOUND
        )
    else:
        response = _authorize_redirect(state)
    response.set_cookie(OAUTH_STATE_COOKIE, state, max_age=STATE_MAX_AGE, **_cookie_kwargs())
    return response


def _link_github(user_id: int, profile: dict, email: str | None, token: str) -> bool:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            return False
        user.github_id = int(profile["id"])
        user.github_login = profile["login"]
        user.avatar_url = profile.get("avatar_url")
        user.email = email
        user.access_token = encrypt_token(token)
        db.commit()
        return True


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = Query(None, max_length=200),
    state: str | None = Query(None, max_length=200),
    installation_id: int | None = Query(None),
    setup_action: str | None = Query(None, max_length=20),
) -> RedirectResponse:
    """GitHub returns here after installing the App (or after OAuth authorize) to link the signed-in user."""
    expected = request.cookies.get(OAUTH_STATE_COOKIE)
    user_id = _session_user_id(request)
    if user_id is None or not state or not expected or not hmac.compare_digest(state, expected):
        return RedirectResponse(_frontend(f"{AFTER_LINK}?github_error=state"), status.HTTP_302_FOUND)
    if not code:
        # The App does not request user authorization on install: authorize separately (state is reused).
        logger.info("Install returned without a code (installation=%s, action=%s)", installation_id, setup_action)
        return _authorize_redirect(state)

    try:
        token = await github_user.exchange_code(code, _callback_url())
        profile = await github_user.get_user(token)
        email = profile.get("email") or await github_user.get_primary_email(token)
    except ServiceError as exc:
        logger.warning("GitHub link failed: %s", exc)
        return RedirectResponse(_frontend(f"{AFTER_LINK}?github_error=exchange"), status.HTTP_302_FOUND)

    if not await run_in_threadpool(_link_github, user_id, profile, email, token):
        return RedirectResponse(_frontend(f"{AFTER_LINK}?github_error=state"), status.HTTP_302_FOUND)
    access.clear_cache(user_id)
    response = RedirectResponse(_frontend(AFTER_LINK), status.HTTP_302_FOUND)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return _user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(csrf_protect)])
def logout(response: Response) -> Response:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
