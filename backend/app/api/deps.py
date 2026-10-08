"""Shared FastAPI dependencies: DB session, current user, CSRF, admin and tenant checks."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Path, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    CSRF_HEADER,
    CSRF_HEADER_VALUE,
    SESSION_COOKIE,
    decode_session_token,
    decrypt_token,
)
from app.models import RepoGrant, User
from app.models.user import ROLE_ADMIN
from app.schemas.common import REPO_SEGMENT_PATTERN
from app.services.access import RepoInfo, get_accessible_repos, get_app_repos
from app.services.errors import ReauthRequired

DbSession = Annotated[Session, Depends(get_db)]
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def csrf_protect(request: Request) -> None:
    """Mutating requests must carry a custom header a cross-site form cannot set."""
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF header")


def get_current_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_session_token(token)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session") from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def is_admin(user: User) -> bool:
    return user.role == ROLE_ADMIN


def require_admin(user: CurrentUser) -> User:
    if not is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin privileges required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


async def get_accessible(user: CurrentUser, db: DbSession, refresh: bool = Query(False)) -> dict[str, RepoInfo]:
    """Repositories visible to the current user.

    Admins see every installation of the GitHub App (App credentials, no GitHub link needed). Everyone else sees
    what their linked GitHub identity can reach through the App, plus repositories an admin granted them that the
    App is still installed on. Not linked, or a token that is undecryptable or revoked, contributes nothing (the UI
    then asks the user to install the GitHub App) rather than a 401, so the user keeps their session.
    """
    app_configured = get_settings().github_app_configured
    if is_admin(user) and app_configured:
        return await get_app_repos(refresh=refresh)

    repos: dict[str, RepoInfo] = {}
    token = decrypt_token(user.access_token) if user.access_token else None
    if token is not None:
        try:
            repos.update(await get_accessible_repos(user, token, refresh=refresh))
        except ReauthRequired:
            pass
    granted = list(db.scalars(select(RepoGrant.repo_full_name).where(RepoGrant.user_id == user.id)))
    if granted and app_configured:
        installed = await get_app_repos(refresh=refresh)
        repos.update({name: installed[name] for name in granted if name in installed})
    return repos


Accessible = Annotated[dict[str, RepoInfo], Depends(get_accessible)]


def repo_full_name(
    owner: Annotated[str, Path(pattern=REPO_SEGMENT_PATTERN)],
    repo: Annotated[str, Path(pattern=REPO_SEGMENT_PATTERN)],
) -> str:
    return f"{owner}/{repo}".lower()


def require_repo_access(accessible: Accessible, full_name: Annotated[str, Depends(repo_full_name)]) -> str:
    """404 (not 403) so the existence of inaccessible repositories is not revealed."""
    if full_name not in accessible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    return full_name


AccessibleRepo = Annotated[str, Depends(require_repo_access)]


def scoped_repos(accessible: dict[str, RepoInfo], repo: str | None) -> list[str]:
    """Restrict queries to accessible repos, optionally narrowed to one (404 if not accessible)."""
    if repo:
        key = repo.lower()
        if key not in accessible:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
        return [key]
    return list(accessible)
