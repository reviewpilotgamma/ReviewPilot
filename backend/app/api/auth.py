"""GitHub OAuth login and session endpoints."""

from __future__ import annotations

import hmac
import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, DbSession, csrf_protect, is_admin
from app.core.config import get_settings
from app.core.database import SessionLocal, utcnow
from app.core.security import (
    OAUTH_NEXT_COOKIE,
    OAUTH_STATE_COOKIE,
    SESSION_COOKIE,
    create_session_token,
    encrypt_token,
)
from app.models import User
from app.schemas.auth import UserOut
from app.services import access, github_user
from app.services.access import LOCAL_GITHUB_ID
from app.services.errors import ServiceError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

STATE_MAX_AGE = 600
DEFAULT_NEXT = "/dashboard"


def _safe_next(value: str | None) -> str:
    """Only allow same-site relative paths (prevents open redirects)."""
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return DEFAULT_NEXT


def _callback_url() -> str:
    return f"{get_settings().API_BASE_URL.rstrip('/')}/api/v1/auth/callback"


def _frontend(path: str) -> str:
    return f"{get_settings().FRONTEND_ORIGIN.rstrip('/')}{path}"


def _cookie_kwargs() -> dict:
    return {"httponly": True, "samesite": "lax", "secure": get_settings().is_production, "path": "/"}


@router.get("/login")
def login(next: str | None = Query(None, max_length=500)) -> RedirectResponse:  # noqa: A002
    settings = get_settings()
    if not settings.oauth_configured:
        return RedirectResponse(_frontend("/?auth_error=not_configured"), status.HTTP_302_FOUND)
    state = secrets.token_urlsafe(32)
    query = urlencode(
        {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": _callback_url(),
            "state": state,
            "scope": "read:user",
        }
    )
    response = RedirectResponse(f"{settings.GITHUB_OAUTH_URL}/login/oauth/authorize?{query}", status.HTTP_302_FOUND)
    response.set_cookie(OAUTH_STATE_COOKIE, state, max_age=STATE_MAX_AGE, **_cookie_kwargs())
    response.set_cookie(OAUTH_NEXT_COOKIE, _safe_next(next), max_age=STATE_MAX_AGE, **_cookie_kwargs())
    return response


def _upsert_user(profile: dict, email: str | None, token: str) -> tuple[int, str]:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.github_id == int(profile["id"])))
        if user is None:
            user = User(github_id=int(profile["id"]), created_at=utcnow())
        user.username = profile["login"]
        user.avatar_url = profile.get("avatar_url")
        user.email = email
        user.access_token = encrypt_token(token)
        user.last_login_at = utcnow()
        db.add(user)
        db.commit()
        return user.id, user.username


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = Query(None, max_length=200),
    state: str | None = Query(None, max_length=200),
) -> RedirectResponse:
    expected = request.cookies.get(OAUTH_STATE_COOKIE)
    if not code or not state or not expected or not hmac.compare_digest(state, expected):
        return RedirectResponse(_frontend("/?auth_error=state"), status.HTTP_302_FOUND)

    try:
        token = await github_user.exchange_code(code, _callback_url())
        profile = await github_user.get_user(token)
        email = profile.get("email") or await github_user.get_primary_email(token)
    except ServiceError as exc:
        logger.warning("OAuth callback failed: %s", exc)
        return RedirectResponse(_frontend("/?auth_error=exchange"), status.HTTP_302_FOUND)

    user_id, username = await run_in_threadpool(_upsert_user, profile, email, token)
    access.clear_cache(user_id)

    settings = get_settings()
    response = RedirectResponse(_frontend(_safe_next(request.cookies.get(OAUTH_NEXT_COOKIE))), status.HTTP_302_FOUND)
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user_id, username),
        max_age=settings.SESSION_TTL_HOURS * 3600,
        **_cookie_kwargs(),
    )
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    response.delete_cookie(OAUTH_NEXT_COOKIE, path="/")
    return response


@router.post("/dev-login", response_model=UserOut, dependencies=[Depends(csrf_protect)])
def dev_login(db: DbSession, response: Response) -> UserOut:
    """Development-only session so the UI works before GitHub OAuth is configured."""
    settings = get_settings()
    if settings.is_production:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    user = db.scalar(select(User).where(User.github_id == LOCAL_GITHUB_ID))
    if user is None:
        user = User(github_id=LOCAL_GITHUB_ID, username="dev", access_token="", created_at=utcnow())
    user.username = "dev"
    user.last_login_at = utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user.id, user.username),
        max_age=settings.SESSION_TTL_HOURS * 3600,
        **_cookie_kwargs(),
    )
    out = UserOut.model_validate(user)
    out.is_admin = is_admin(user)
    return out


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    out = UserOut.model_validate(user)
    out.is_admin = is_admin(user)
    return out


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(csrf_protect)])
def logout(response: Response) -> Response:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
