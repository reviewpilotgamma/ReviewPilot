from __future__ import annotations

import time

import jwt
import pytest

from app.core import security
from tests.conftest import WEBHOOK_SECRET, sign


class TestWebhookSignature:
    def test_valid_signature(self):
        body = b'{"a":1}'
        assert security.verify_github_signature(body, sign(body), WEBHOOK_SECRET)

    @pytest.mark.parametrize("header", [None, "", "sha1=abc", "sha256=deadbeef"])
    def test_invalid_or_missing_signature(self, header):
        assert not security.verify_github_signature(b"{}", header, WEBHOOK_SECRET)

    def test_body_tampering_detected(self):
        assert not security.verify_github_signature(b'{"a":2}', sign(b'{"a":1}'), WEBHOOK_SECRET)

    def test_empty_secret_always_rejects(self):
        body = b"{}"
        assert not security.verify_github_signature(body, sign(body, ""), "")


class TestSessionToken:
    def test_round_trip(self):
        token = security.create_session_token(7, "alice")
        payload = security.decode_session_token(token)
        assert payload["sub"] == "7" and payload["login"] == "alice"

    def test_expired_token_rejected(self):
        past = int(time.time()) - 3600
        token = jwt.encode({"sub": "7", "iat": past - 10, "exp": past, "typ": "session"}, "s" * 48, "HS256")
        with pytest.raises(jwt.ExpiredSignatureError):
            security.decode_session_token(token)

    def test_wrong_type_rejected(self):
        token = jwt.encode({"sub": "1", "exp": int(time.time()) + 60, "typ": "other"}, "s" * 48, "HS256")
        with pytest.raises(jwt.InvalidTokenError):
            security.decode_session_token(token)

    def test_forged_signature_rejected(self):
        token = jwt.encode({"sub": "1", "exp": int(time.time()) + 60, "typ": "session"}, "x" * 48, "HS256")
        with pytest.raises(jwt.InvalidTokenError):
            security.decode_session_token(token)


class TestTokenEncryption:
    def test_round_trip(self):
        cipher = security.encrypt_token("gho_secret")
        assert cipher != "gho_secret"
        assert security.decrypt_token(cipher) == "gho_secret"

    def test_garbage_returns_none(self):
        assert security.decrypt_token("not-a-token") is None


class TestMasking:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(None, ""), ("", ""), ("abc", "••••"), ("abcd1234", "••••••••1234")],
    )
    def test_mask(self, value, expected):
        assert security.mask_secret(value) == expected

    def test_is_masked(self):
        assert security.is_masked("••••••••1234")
        assert not security.is_masked("real-secret")
        assert not security.is_masked(None)


class TestPasswords:
    def test_round_trip_and_wrong_password(self):
        stored = security.hash_password("correct horse")
        assert stored.startswith("scrypt$")
        assert security.verify_password("correct horse", stored)
        assert not security.verify_password("wrong horse", stored)

    @pytest.mark.parametrize("stored", [None, "", "plain-text", "bcrypt$1$2$3$c2FsdA==$ZGlnZXN0", "scrypt$x$8$1$a$b"])
    def test_unknown_or_malformed_hashes_never_verify(self, stored):
        assert not security.verify_password("anything", stored)


class TestEphemeralSecrets:
    """Without configured secrets, development falls back to per-process random values."""

    @pytest.fixture(autouse=True)
    def _fresh_cache(self):
        security._ephemeral_secret.cache_clear()
        yield
        security._ephemeral_secret.cache_clear()

    def test_session_tokens_work_with_an_ephemeral_secret(self, monkeypatch, caplog):
        from app.core.config import reload_settings

        monkeypatch.setenv("SESSION_SECRET", "")
        reload_settings()
        token = security.create_session_token(7, "alice")
        assert security.decode_session_token(token)["sub"] == "7"
        assert "SESSION_SECRET is not set" in caplog.text

    def test_token_encryption_works_with_an_ephemeral_key(self, monkeypatch):
        from app.core.config import reload_settings

        monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "")
        reload_settings()
        assert security.decrypt_token(security.encrypt_token("gho_secret")) == "gho_secret"
