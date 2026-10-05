"""Thin client for the Google Gemini ``generateContent`` REST API."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.http import get_http_client
from app.services.errors import GeminiNotConfigured, GeminiPermanentError, GeminiTransientError

logger = logging.getLogger(__name__)

BLOCKING_FINISH_REASONS = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}


@dataclass(frozen=True)
class GeminiResult:
    text: str
    model: str
    finish_reason: str | None


def _api_key(override: str | None = None) -> str:
    key = override or get_settings().GEMINI_API_KEY.get_secret_value()
    if not key:
        raise GeminiNotConfigured("GEMINI_API_KEY is not set")
    return key


async def _post(url: str, key: str, body: dict) -> httpx.Response:
    try:
        return await get_http_client().post(
            url, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body
        )
    except httpx.TimeoutException as exc:
        raise GeminiTransientError("Gemini request timed out") from exc
    except httpx.TransportError as exc:
        raise GeminiTransientError(f"Gemini transport error: {exc.__class__.__name__}") from exc


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    try:
        message = response.json().get("error", {}).get("message", "")
    except ValueError:
        message = ""
    text = f"Gemini {status}: {message[:300]}"
    if status == 429 or status >= 500:
        raise GeminiTransientError(text)
    raise GeminiPermanentError(text)


async def generate(system_prompt: str, user_content: str, *, max_output_tokens: int | None = None) -> GeminiResult:
    settings = get_settings()
    key = _api_key()
    model = settings.GEMINI_MODEL
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_content}]}],
        "generationConfig": {
            "temperature": settings.GEMINI_TEMPERATURE,
            "maxOutputTokens": max_output_tokens or settings.GEMINI_MAX_OUTPUT_TOKENS,
        },
    }
    response = await _post(f"{settings.GEMINI_API_URL}/models/{model}:generateContent", key, body)
    _raise_for_status(response)
    data = response.json()

    block_reason = (data.get("promptFeedback") or {}).get("blockReason")
    candidates = data.get("candidates") or []
    if not candidates:
        raise GeminiPermanentError(f"Model returned no content ({block_reason or 'no candidates'})")

    candidate = candidates[0]
    finish_reason = candidate.get("finishReason")
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        reason = finish_reason if finish_reason in BLOCKING_FINISH_REASONS else (block_reason or "empty")
        raise GeminiPermanentError(f"Model returned no content ({reason})")
    if finish_reason == "MAX_TOKENS":
        logger.warning("Gemini output hit MAX_TOKENS; review may be incomplete")
    return GeminiResult(text=text, model=model, finish_reason=finish_reason)


async def validate(api_key: str | None = None, model: str | None = None) -> tuple[bool, str, str]:
    """Check that the key can see the model. Returns (ok, message, model)."""
    settings = get_settings()
    model = model or settings.GEMINI_MODEL
    try:
        key = _api_key(api_key)
    except GeminiNotConfigured:
        return False, "No Gemini API key configured", model
    try:
        response = await get_http_client().get(
            f"{settings.GEMINI_API_URL}/models/{model}", headers={"x-goog-api-key": key}
        )
    except httpx.HTTPError:
        return False, "Could not reach the Gemini API", model
    if response.status_code == 200:
        return True, "API key is valid and the model is available", model
    if response.status_code == 404:
        return False, f"Model '{model}' not found", model
    if response.status_code in (400, 401, 403):
        return False, "Invalid API key", model
    return False, f"Unexpected response from Gemini ({response.status_code})", model
