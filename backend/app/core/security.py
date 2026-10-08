"""Cryptographic helpers: webhook HMAC verification, password hashing, session JWTs, token encryption, masking."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from functools import lru_cache
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = logging.getLogger(__name__)

MASK_PREFIX = "••••"
SESSION_COOKIE = "rp_session"
OAUTH_STATE_COOKIE = "rp_oauth_state"
CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "ReviewPilot"


# --------------------------------------------------------------------------- webhooks
def verify_github_signature(raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    """Validate ``X-Hub-Signature-256`` against HMAC-SHA256(raw_body, secret) in constant time."""
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# --------------------------------------------------------------------------- passwords
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)


def hash_password(password: str) -> str:
    """``scrypt$n$r$p$salt$hash`` with a random per-password salt (stdlib only)."""
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    b64 = base64.b64encode
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    try:
        scheme, n, r, p, salt, digest = (stored or "").split("$")
        if scheme != "scrypt":
            return False
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
        return hmac.compare_digest(actual, base64.b64decode(digest))
    except ValueError:
        return False


# --------------------------------------------------------------------------- secrets with dev fallbacks
@lru_cache
def _ephemeral_secret(name: str) -> str:
    logger.warning("%s is not set; using an ephemeral value (sessions/tokens reset on restart)", name)
    if name == "TOKEN_ENCRYPTION_KEY":
        return Fernet.generate_key().decode()
    return secrets.token_urlsafe(48)


def _session_secret() -> str:
    return get_settings().SESSION_SECRET.get_secret_value() or _ephemeral_secret("SESSION_SECRET")


def _fernet() -> Fernet:
    key = get_settings().TOKEN_ENCRYPTION_KEY.get_secret_value() or _ephemeral_secret("TOKEN_ENCRYPTION_KEY")
    return Fernet(key.encode())


# --------------------------------------------------------------------------- session JWT
def create_session_token(user_id: int, username: str) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "login": username,
        "iat": now,
        "exp": now + settings.SESSION_TTL_HOURS * 3600,
        "typ": "session",
    }
    return jwt.encode(payload, _session_secret(), algorithm="HS256")


def decode_session_token(token: str) -> dict[str, Any]:
    """Decode a session JWT. Raises ``jwt.InvalidTokenError`` on any problem."""
    payload = jwt.decode(token, _session_secret(), algorithms=["HS256"], options={"require": ["exp", "sub"]})
    if payload.get("typ") != "session":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


# --------------------------------------------------------------------------- token encryption
def encrypt_token(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_token(cipher: str) -> str | None:
    """Return the plaintext token, or ``None`` if it cannot be decrypted (e.g. key rotated)."""
    try:
        return _fernet().decrypt(cipher.encode()).decode()
    except (InvalidToken, ValueError):
        return None


# --------------------------------------------------------------------------- masking
def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    return MASK_PREFIX * 2 + value[-4:] if len(value) > 4 else MASK_PREFIX


def is_masked(value: str | None) -> bool:
    return bool(value) and value.startswith(MASK_PREFIX)  # type: ignore[union-attr]
