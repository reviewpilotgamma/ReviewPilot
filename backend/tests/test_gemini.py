"""Gemini client edge cases: transport errors, status mapping, caches, empty output and key validation."""

from __future__ import annotations

import logging

import httpx
import pytest

from app.core.config import reload_settings
from app.services import gemini
from app.services.errors import GeminiNotConfigured, GeminiPermanentError, GeminiTransientError
from tests.conftest import GEMINI_API

GENERATE = f"{GEMINI_API}/models/gemini-2.0-flash:generateContent"


def _candidate(text: str, finish: str = "STOP") -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]}


async def test_timeouts_and_transport_errors_are_transient(mock_http):
    mock_http.post(GENERATE).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(GeminiTransientError, match="timed out"):
        await gemini.generate("system", "user")

    mock_http.post(GENERATE).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(GeminiTransientError, match="ConnectError"):
        await gemini.generate("system", "user")


@pytest.mark.parametrize(
    ("status", "error"),
    [(429, GeminiTransientError), (503, GeminiTransientError), (400, GeminiPermanentError)],
)
async def test_status_codes_map_to_error_kinds(mock_http, status, error):
    mock_http.post(GENERATE).respond(status, json={"error": {"message": "nope"}})
    with pytest.raises(error, match=f"Gemini {status}: nope"):
        await gemini.generate("system", "user")


async def test_non_json_error_body_still_reports_status(mock_http):
    mock_http.post(GENERATE).respond(500, text="<html>bad gateway</html>")
    with pytest.raises(GeminiTransientError, match=r"^Gemini 500: $"):
        await gemini.generate("system", "user")


async def test_missing_api_key_is_not_configured(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    reload_settings()
    with pytest.raises(GeminiNotConfigured):
        await gemini.generate("system", "user")


async def test_generate_sends_cache_handle_and_logs_cache_hits(mock_http, caplog):
    route = mock_http.post(GENERATE).respond(
        200,
        json={**_candidate("review", "MAX_TOKENS"), "usageMetadata": {"cachedContentTokenCount": 900, "promptTokenCount": 1000}},
    )
    with caplog.at_level(logging.INFO, logger="app.services.gemini"):
        result = await gemini.generate("system", "user", cached_content="cachedContents/abc", inline_documents="ignored")

    assert result.text == "review"
    assert result.finish_reason == "MAX_TOKENS"
    body = route.calls.last.request.content.decode()
    assert '"cachedContent":"cachedContents/abc"' in body.replace(" ", "")
    assert "ignored" not in body
    assert "MAX_TOKENS" in caplog.text
    assert "cache hit: cached=900 prompt=1000" in caplog.text


async def test_generate_inlines_documents_without_a_cache(mock_http):
    route = mock_http.post(GENERATE).respond(200, json=_candidate("ok"))
    await gemini.generate("system", "user", inline_documents="ARCH DOC")
    assert "ARCH DOC" in route.calls.last.request.content.decode()


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "SAFETY"),
        ({}, "no candidates"),
        ({"candidates": [{"content": {"parts": []}, "finishReason": "RECITATION"}]}, "RECITATION"),
        ({"candidates": [{"finishReason": "STOP"}], "promptFeedback": {"blockReason": "OTHER"}}, "OTHER"),
        ({"candidates": [{"content": {"parts": [{"text": "  "}]}, "finishReason": "STOP"}]}, "empty"),
    ],
)
async def test_empty_output_is_a_permanent_error(mock_http, payload, reason):
    mock_http.post(GENERATE).respond(200, json=payload)
    with pytest.raises(GeminiPermanentError, match=rf"no content \({reason}\)"):
        await gemini.generate("system", "user")


async def test_create_cached_content(mock_http):
    route = mock_http.post(f"{GEMINI_API}/cachedContents").respond(
        200, json={"name": "cachedContents/xyz", "expireTime": "2026-10-09T00:00:00Z"}
    )
    result = await gemini.create_cached_content(display_name="rp", documents_text="DOCS", ttl="3600s")
    assert result == gemini.CachedContentResult(name="cachedContents/xyz", expire_time="2026-10-09T00:00:00Z")
    sent = route.calls.last.request.content.decode()
    assert '"model":"models/gemini-2.0-flash"' in sent.replace(" ", "")
    assert "AUTHORITATIVE" in sent


async def test_create_cached_content_without_a_name_fails(mock_http):
    mock_http.post(f"{GEMINI_API}/cachedContents").respond(200, json={})
    with pytest.raises(GeminiPermanentError, match="no name"):
        await gemini.create_cached_content(display_name="rp", documents_text="DOCS", ttl="60s")


async def test_delete_cached_content(mock_http):
    await gemini.delete_cached_content("")  # nothing to delete, no request

    deleted = mock_http.delete(f"{GEMINI_API}/cachedContents/abc").respond(200, json={})
    await gemini.delete_cached_content("abc")
    await gemini.delete_cached_content("cachedContents/abc")
    assert deleted.call_count == 2

    mock_http.delete(f"{GEMINI_API}/cachedContents/gone").respond(404)
    await gemini.delete_cached_content("cachedContents/gone")

    mock_http.delete(f"{GEMINI_API}/cachedContents/boom").respond(500, json={"error": {"message": "x"}})
    with pytest.raises(GeminiTransientError):
        await gemini.delete_cached_content("cachedContents/boom")


async def test_model_resource_keeps_a_full_name(monkeypatch):
    assert gemini._model_resource("models/custom") == "models/custom"
    assert gemini._model_resource("custom") == "models/custom"


@pytest.mark.parametrize(
    ("status", "ok", "message"),
    [
        (200, True, "API key is valid and the model is available"),
        (404, False, "Model 'gemini-2.0-flash' not found"),
        (401, False, "Invalid API key"),
        (500, False, "Unexpected response from Gemini (500)"),
    ],
)
async def test_validate_maps_responses(mock_http, status, ok, message):
    mock_http.get(f"{GEMINI_API}/models/gemini-2.0-flash").respond(status, json={})
    assert await gemini.validate() == (ok, message, "gemini-2.0-flash")


async def test_validate_without_key_or_network(mock_http, monkeypatch):
    mock_http.get(f"{GEMINI_API}/models/gemini-2.5-pro").mock(side_effect=httpx.ConnectError("down"))
    assert await gemini.validate(api_key="k", model="gemini-2.5-pro") == (
        False,
        "Could not reach the Gemini API",
        "gemini-2.5-pro",
    )

    monkeypatch.setenv("GEMINI_API_KEY", "")
    reload_settings()
    assert await gemini.validate() == (False, "No Gemini API key configured", "gemini-2.0-flash")
