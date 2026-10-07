"""Documents API: the Gemini context cache is built at upload/delete time and reported to the UI."""

from __future__ import annotations

import itertools

import httpx
import pytest

from app.services.documents import MIN_CACHE_CHARS
from tests.conftest import GEMINI_API

DOCS_URL = "/api/v1/rules/acme/api/documents"


def big(tag: str) -> bytes:
    line = f"Rule {tag}: services own their data.\n"
    return (f"# Handbook {tag}\n" + line * (MIN_CACHE_CHARS // len(line) + 10)).encode()


@pytest.fixture
def gemini_cache(mock_http):
    """Mock cachedContents create/delete; returns (create route, delete route)."""
    seq = itertools.count(1)
    create = mock_http.post(f"{GEMINI_API}/cachedContents").mock(
        side_effect=lambda request: httpx.Response(
            200, json={"name": f"cachedContents/c{next(seq)}", "expireTime": "2099-01-01T00:00:00Z"}
        )
    )
    delete = mock_http.delete(url__regex=rf"{GEMINI_API}/cachedContents/.+").respond(200, json={})
    return create, delete


def upload(client, data: bytes, filename: str = "arch.md", **params):
    return client.post(DOCS_URL, params=params, files={"file": (filename, data, "text/markdown")})


def listing(client) -> dict:
    return client.get(DOCS_URL).json()


def test_large_upload_builds_cache_before_responding(client, login, gemini_cache):
    login()
    create, _ = gemini_cache

    response = upload(client, big("v1"))

    assert response.status_code == 201
    body = response.json()
    assert (body["cache_status"], body["cache_error"]) == ("cached", None)
    assert create.call_count == 1
    assert listing(client)["cache_status"] == "cached"


def test_warm_false_defers_and_last_file_builds_once(client, login, gemini_cache):
    login()
    create, _ = gemini_cache

    first = upload(client, big("a"), "a.md", warm="false").json()
    second = upload(client, big("b"), "b.md", warm="false").json()
    assert (first["cache_status"], second["cache_status"]) == ("pending", "pending")
    assert listing(client)["cache_status"] == "pending"
    assert create.call_count == 0

    last = upload(client, b"# Notes\n", "c.md").json()

    assert last["cache_status"] == "cached"
    assert create.call_count == 1


def test_small_upload_is_inline_without_gemini(client, login, gemini_cache):
    login()
    create, _ = gemini_cache

    body = upload(client, b"# Small doc\n").json()

    assert (body["cache_status"], body["cache_error"]) == ("inline", None)
    assert create.call_count == 0
    assert listing(client)["cache_status"] == "inline"


def test_identical_reupload_reuses_cache(client, login, gemini_cache):
    login()
    create, delete = gemini_cache
    upload(client, big("v1"))

    body = upload(client, big("v1")).json()

    assert body["cache_status"] == "cached"
    assert (create.call_count, delete.call_count) == (1, 0)


def test_changed_reupload_replaces_cache(client, login, gemini_cache):
    login()
    create, delete = gemini_cache
    upload(client, big("v1"))

    assert upload(client, big("v2")).json()["cache_status"] == "cached"
    assert (create.call_count, delete.call_count) == (2, 1)


def test_cache_failure_still_saves_document(client, login, mock_http):
    login()
    mock_http.post(f"{GEMINI_API}/cachedContents").respond(503, json={"error": {"message": "overloaded"}})

    response = upload(client, big("v1"))

    assert response.status_code == 201
    body = response.json()
    assert body["cache_status"] == "pending"
    assert "Gemini 503" in body["cache_error"] and "gemini-key-1234" not in body["cache_error"]
    data = listing(client)
    assert data["total"] == 1 and data["cache_status"] == "pending"


def test_delete_rewarms_remaining_and_last_delete_is_none(client, login, gemini_cache):
    login()
    create, delete = gemini_cache
    first = upload(client, big("a"), "a.md", warm="false").json()["id"]
    second = upload(client, big("b"), "b.md").json()["id"]
    assert create.call_count == 1

    assert client.delete(f"{DOCS_URL}/{first}").status_code == 204
    assert (create.call_count, delete.call_count) == (2, 1)
    assert listing(client)["cache_status"] == "cached"

    assert client.delete(f"{DOCS_URL}/{second}").status_code == 204
    assert (create.call_count, delete.call_count) == (2, 2)
    assert listing(client)["cache_status"] == "none"


def test_invalid_upload_does_not_call_gemini(client, login, gemini_cache):
    login()
    create, _ = gemini_cache

    assert upload(client, b"MZ...", "tool.exe").status_code == 400
    assert create.call_count == 0
