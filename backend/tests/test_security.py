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
