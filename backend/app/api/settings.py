"""System settings, integration validation and canned replies."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from app.api.deps import AdminUser, CurrentUser, csrf_protect, is_admin
from app.core.config import get_settings
from app.schemas.settings import (
    RepliesModel,
    SettingsIn,
    SettingsOut,
    ValidateGeminiIn,
    ValidationResult,
)
from app.services import config_store, gemini, github_app, replies
from app.services.errors import ServiceError

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(csrf_protect)])


def _out(user_is_admin: bool) -> SettingsOut:
    return SettingsOut(**config_store.snapshot(get_settings()), is_admin=user_is_admin)


@router.get("", response_model=SettingsOut)
def read_settings(user: CurrentUser) -> SettingsOut:
    return _out(is_admin(user))


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsIn, _admin: AdminUser) -> SettingsOut:
    try:
        config_store.apply_updates(body.model_dump(exclude_none=True))
    except config_store.ConfigValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _out(True)


@router.post("/validate/gemini", response_model=ValidationResult)
async def validate_gemini(body: ValidateGeminiIn, _admin: AdminUser) -> ValidationResult:
    api_key = None if (body.api_key or "").startswith("••••") else body.api_key
    ok, message, model = await gemini.validate(api_key or None, body.model)
    return ValidationResult(ok=ok, message=message, model=model)


@router.post("/validate/github", response_model=ValidationResult)
async def validate_github(_admin: AdminUser) -> ValidationResult:
    try:
        app = await github_app.get_app()
        installs = await github_app.list_app_installations()
    except ServiceError as exc:
        return ValidationResult(ok=False, message=str(exc))
    return ValidationResult(
        ok=True,
        message="GitHub App credentials are valid",
        app_name=app.get("name"),
        installations=len(installs),
    )


@router.get("/replies", response_model=RepliesModel)
def get_replies(_user: CurrentUser) -> dict[str, str]:
    return replies.load_replies()


@router.put("/replies", response_model=RepliesModel)
async def put_replies(body: RepliesModel, _admin: AdminUser) -> dict[str, str]:
    return await run_in_threadpool(replies.save_replies, body.model_dump())
