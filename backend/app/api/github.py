"""GitHub App metadata and the current user's installations."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import Accessible, DbSession
from app.core.config import get_settings
from app.models import RepoRule
from app.schemas.github import AppInfo, InstallationOut, RepoOut
from app.services import github_app
from app.services.errors import ServiceError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/github", tags=["github"])

APP_CACHE_TTL = 600
_app_cache: dict[str, tuple[float, dict]] = {}


async def _app_details() -> dict:
    cached = _app_cache.get("app")
    if cached and cached[0] > time.time():
        return cached[1]
    data = await github_app.get_app()
    _app_cache["app"] = (time.time() + APP_CACHE_TTL, data)
    return data


async def app_slug() -> str:
    """The configured slug, or the App's own slug from GitHub when ``GITHUB_APP_SLUG`` is unset."""
    settings = get_settings()
    if settings.GITHUB_APP_SLUG or not settings.github_app_configured:
        return settings.GITHUB_APP_SLUG
    try:
        return (await _app_details()).get("slug") or ""
    except ServiceError as exc:
        logger.info("Could not fetch GitHub App slug: %s", exc)
        return ""


@router.get("/app", response_model=AppInfo)
async def app_info() -> AppInfo:
    settings = get_settings()
    slug, name, html_url = settings.GITHUB_APP_SLUG, "ReviewPilot", ""
    if settings.github_app_configured:
        try:
            data = await _app_details()
            slug = data.get("slug") or slug
            name = data.get("name") or name
            html_url = data.get("html_url") or ""
        except ServiceError as exc:
            logger.info("Could not fetch GitHub App details: %s", exc)
    install_url = f"https://github.com/apps/{slug}/installations/new" if slug else ""
    return AppInfo(
        configured=bool(slug and settings.oauth_configured),
        slug=slug,
        name=name,
        install_url=install_url,
        html_url=html_url or (f"https://github.com/apps/{slug}" if slug else ""),
    )


@router.get("/installations", response_model=list[InstallationOut])
def installations(db: DbSession, accessible: Accessible) -> list[InstallationOut]:
    names = list(accessible)
    with_rules = (
        set(db.scalars(select(RepoRule.repo_full_name).where(RepoRule.repo_full_name.in_(names)))) if names else set()
    )

    grouped: dict[int, InstallationOut] = {}
    for info in sorted(accessible.values(), key=lambda r: r.full_name):
        inst = grouped.setdefault(
            info.installation_id,
            InstallationOut(
                installation_id=info.installation_id,
                account_login=info.account_login,
                account_type=info.account_type,
                avatar_url=info.account_avatar_url,
                repos=[],
            ),
        )
        inst.repos.append(
            RepoOut(
                full_name=info.full_name,
                private=info.private,
                html_url=info.html_url,
                has_rules=info.full_name in with_rules,
            )
        )
    return sorted(grouped.values(), key=lambda i: i.account_login.lower())
