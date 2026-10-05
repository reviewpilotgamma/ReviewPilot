"""Read and atomically update the backend ``.env`` file for whitelisted settings."""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

from dotenv import dotenv_values

from app.core.config import BACKEND_DIR, Settings, env_file_path, reload_settings
from app.core.security import is_masked, mask_secret
from app.services import access, github_app

# API field name -> (env key, is_secret)
WRITABLE_FIELDS: dict[str, tuple[str, bool]] = {
    "github_app_id": ("GITHUB_APP_ID", False),
    "github_app_slug": ("GITHUB_APP_SLUG", False),
    "github_webhook_secret": ("GITHUB_WEBHOOK_SECRET", True),
    "github_private_key_path": ("GITHUB_PRIVATE_KEY_PATH", False),
    "github_client_id": ("GITHUB_CLIENT_ID", False),
    "github_client_secret": ("GITHUB_CLIENT_SECRET", True),
    "gemini_api_key": ("GEMINI_API_KEY", True),
    "gemini_model": ("GEMINI_MODEL", False),
}

_lock = threading.Lock()
_NEEDS_QUOTES = re.compile(r"[\s#'\"=]")


class ConfigValidationError(ValueError):
    pass


def read_env() -> dict[str, str | None]:
    path = env_file_path()
    return dict(dotenv_values(path)) if path.exists() else {}


def _format_value(value: str) -> str:
    if value == "" or not _NEEDS_QUOTES.search(value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_env(updates: dict[str, str]) -> None:
    """Replace ``KEY=`` lines in place (keeping comments/order) and append new keys, atomically."""
    for key, value in updates.items():
        if "\n" in value or "\r" in value:
            raise ConfigValidationError(f"{key} must not contain newlines")
    path = env_file_path()
    with _lock:
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        remaining = dict(updates)
        output: list[str] = []
        for line in lines:
            match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if match and match.group(1) in remaining:
                key = match.group(1)
                output.append(f"{key}={_format_value(remaining.pop(key))}")
            else:
                output.append(line)
        output.extend(f"{key}={_format_value(value)}" for key, value in remaining.items())
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text("\n".join(output) + "\n", encoding="utf-8")
        os.replace(tmp, path)


def _resolve_key_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


def apply_updates(fields: dict[str, str | None]) -> Settings:
    """Validate and persist provided fields; masked secrets are treated as unchanged."""
    updates: dict[str, str] = {}
    for field, value in fields.items():
        if value is None or field not in WRITABLE_FIELDS:
            continue
        env_key, secret = WRITABLE_FIELDS[field]
        if secret and is_masked(value):
            continue
        value = value.strip()
        if field == "github_private_key_path" and value:
            resolved = _resolve_key_path(value)
            if not resolved.is_file() or not os.access(resolved, os.R_OK):
                raise ConfigValidationError(f"Private key file not found or unreadable: {value}")
        updates[env_key] = value
    if updates:
        write_env(updates)
    settings = reload_settings()
    github_app.clear_caches()
    access.clear_cache()
    return settings


def snapshot(settings: Settings) -> dict[str, object]:
    return {
        "github_app_id": settings.GITHUB_APP_ID,
        "github_app_slug": settings.GITHUB_APP_SLUG,
        "github_webhook_secret": mask_secret(settings.GITHUB_WEBHOOK_SECRET.get_secret_value()),
        "github_private_key_path": settings.GITHUB_PRIVATE_KEY_PATH,
        "github_private_key_present": settings.private_key_path.is_file(),
        "github_client_id": settings.GITHUB_CLIENT_ID,
        "github_client_secret": mask_secret(settings.GITHUB_CLIENT_SECRET.get_secret_value()),
        "gemini_api_key": mask_secret(settings.GEMINI_API_KEY.get_secret_value()),
        "gemini_model": settings.GEMINI_MODEL,
        "max_diff_chars": settings.MAX_DIFF_CHARS,
        "webhook_url": f"{settings.API_BASE_URL.rstrip('/')}/api/v1/webhooks/github",
    }
