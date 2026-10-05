"""Application settings loaded from environment variables / the backend ``.env`` file."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


def env_file_path() -> Path:
    """Location of the writable ``.env`` file (overridable for tests)."""
    return Path(os.environ.get("REVIEWPILOT_ENV_FILE", BACKEND_DIR / ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    # --- Runtime ---
    ENV: str = "development"
    API_BASE_URL: str = "http://localhost:8000"
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    DATABASE_URL: str = f"sqlite:///{(BACKEND_DIR / 'reviewpilot.db').as_posix()}"
    LOG_LEVEL: str = "INFO"

    # --- GitHub App ---
    GITHUB_APP_ID: str = ""
    GITHUB_APP_SLUG: str = ""
    GITHUB_WEBHOOK_SECRET: SecretStr = SecretStr("")
    GITHUB_PRIVATE_KEY_PATH: str = "./secrets/reviewpilot.private-key.pem"
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: SecretStr = SecretStr("")
    GITHUB_API_URL: str = "https://api.github.com"
    GITHUB_OAUTH_URL: str = "https://github.com"

    # --- Gemini ---
    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_API_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    GEMINI_TEMPERATURE: float = 0.2
    GEMINI_MAX_OUTPUT_TOKENS: int = 8192
    GEMINI_CACHE_TTL_SECONDS: int = Field(86_400, ge=60, le=7 * 24 * 3600)

    # --- Auth / security ---
    SESSION_SECRET: SecretStr = SecretStr("")
    SESSION_TTL_HOURS: int = Field(8, ge=1, le=24 * 30)
    TOKEN_ENCRYPTION_KEY: SecretStr = SecretStr("")
    ADMIN_GITHUB_LOGINS: str = ""

    # --- Review engine ---
    # 0 = no truncation (send full PR diff). Positive values restore a hard character cap.
    MAX_DIFF_CHARS: int = Field(0, ge=0)
    MAX_COMMENT_CHARS: int = Field(65_000, gt=1000, le=65_536)
    INSTALLATION_TOKEN_TTL_SECONDS: int = Field(3000, gt=60, le=3600)

    # --- Worker ---
    WORKER_ENABLED: bool = True
    WORKER_CONCURRENCY: int = Field(2, ge=1, le=16)
    WORKER_POLL_INTERVAL_SECONDS: float = Field(1.0, gt=0)
    JOB_MAX_ATTEMPTS: int = Field(3, ge=1, le=10)
    JOB_TIMEOUT_SECONDS: float = Field(180.0, gt=0)

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    @property
    def admin_logins(self) -> set[str]:
        return {x.strip().lower() for x in self.ADMIN_GITHUB_LOGINS.split(",") if x.strip()}

    @property
    def private_key_path(self) -> Path:
        path = Path(self.GITHUB_PRIVATE_KEY_PATH)
        return path if path.is_absolute() else (BACKEND_DIR / path).resolve()

    @property
    def github_app_configured(self) -> bool:
        return bool(self.GITHUB_APP_ID and self.private_key_path.is_file())

    @property
    def oauth_configured(self) -> bool:
        return bool(self.GITHUB_CLIENT_ID and self.GITHUB_CLIENT_SECRET.get_secret_value())

    @property
    def local_mode(self) -> bool:
        """Development without GitHub OAuth: local sign-in and a local repo list."""
        return not self.is_production and not self.oauth_configured

    @property
    def gemini_configured(self) -> bool:
        return bool(self.GEMINI_API_KEY.get_secret_value())

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.is_production:
            if len(self.SESSION_SECRET.get_secret_value()) < 32:
                raise ValueError("SESSION_SECRET must be at least 32 characters in production")
            if not self.TOKEN_ENCRYPTION_KEY.get_secret_value():
                raise ValueError("TOKEN_ENCRYPTION_KEY is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=env_file_path())  # type: ignore[call-arg]


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
