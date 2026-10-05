from __future__ import annotations

from pydantic import BaseModel, Field

MAX_REPLY_CHARS = 5_000


class SettingsOut(BaseModel):
    github_app_id: str
    github_app_slug: str
    github_webhook_secret: str
    github_private_key_path: str
    github_private_key_present: bool
    github_client_id: str
    github_client_secret: str
    gemini_api_key: str
    gemini_model: str
    max_diff_chars: int
    webhook_url: str
    is_admin: bool


class SettingsIn(BaseModel):
    """Partial update. Only provided (non-null) fields are written; masked secrets are ignored."""

    github_app_id: str | None = Field(None, pattern=r"^\d*$", max_length=20)
    github_app_slug: str | None = Field(None, pattern=r"^[a-z0-9-]*$", max_length=100)
    github_webhook_secret: str | None = Field(None, max_length=500)
    github_private_key_path: str | None = Field(None, max_length=1000)
    github_client_id: str | None = Field(None, pattern=r"^[A-Za-z0-9._-]*$", max_length=100)
    github_client_secret: str | None = Field(None, max_length=500)
    gemini_api_key: str | None = Field(None, max_length=500)
    gemini_model: str | None = Field(None, pattern=r"^[a-zA-Z0-9.\-]+$", max_length=100)


class ValidateGeminiIn(BaseModel):
    api_key: str | None = Field(None, max_length=500)
    model: str | None = Field(None, pattern=r"^[a-zA-Z0-9.\-]+$", max_length=100)


class ValidationResult(BaseModel):
    ok: bool
    message: str
    model: str | None = None
    app_name: str | None = None
    installations: int | None = None


class RepliesModel(BaseModel):
    welcome: str = Field(..., min_length=1, max_length=MAX_REPLY_CHARS)
    plan: str = Field(..., min_length=1, max_length=MAX_REPLY_CHARS)
    error: str = Field(..., min_length=1, max_length=MAX_REPLY_CHARS)
    empty_diff: str = Field(..., min_length=1, max_length=MAX_REPLY_CHARS)
