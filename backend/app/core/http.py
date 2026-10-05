"""Shared outbound HTTP client. Every external call goes through it so timeouts apply uniformly."""

from __future__ import annotations

import ssl
from functools import lru_cache

import certifi
import httpx

DEFAULT_TIMEOUT = httpx.Timeout(30.0)
USER_AGENT = "ReviewPilot/1.0"

_client: httpx.AsyncClient | None = None


@lru_cache
def _ssl_context() -> ssl.SSLContext:
    """Building a CA bundle context is expensive (~0.4 s); do it once per process."""
    return ssl.create_default_context(cafile=certifi.where())


def create_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT}, verify=_ssl_context())


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = create_client()
    return _client


def set_http_client(client: httpx.AsyncClient | None) -> None:
    global _client
    _client = client


async def close_http_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
