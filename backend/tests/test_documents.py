from __future__ import annotations

import pytest

from app.services.documents import (
    DocumentError,
    _safe_name,
    assemble_documents_text,
    extract_text,
    list_documents,
    save_document,
)


def test_safe_name_rejects_bad_extensions():
    with pytest.raises(DocumentError):
        _safe_name("payload.exe")
    assert _safe_name("architecture.md") == "architecture.md"


def test_extract_text_utf8():
    assert "hello" in extract_text("notes.txt", b"hello architecture")


async def test_save_and_assemble_documents(db):
    doc = await save_document(
        db,
        repo_full_name="Acme/API",
        filename="arch.md",
        content_type="text/markdown",
        data=b"# Boundaries\nNo cross-service DB access.\n",
        user_id=None,
    )
    assert doc.id
    assert doc.repo_full_name == "acme/api"
    items = list_documents(db, "acme/api")
    assert len(items) == 1
    text = assemble_documents_text(db, "acme/api")
    assert "BEGIN DOCUMENT: arch.md" in text
    assert "No cross-service DB access" in text


async def test_ensure_context_cache_reuses_stored_cache(db):
    """Regression: a stored cache row's expiry must load as aware UTC so reuse does not raise TypeError."""
    from datetime import UTC, datetime, timedelta

    from app.core.config import get_settings
    from app.models import RepoContextCache
    from app.services.documents import documents_content_hash, ensure_context_cache

    await save_document(
        db, repo_full_name="acme/api", filename="arch.md", content_type="text/markdown", data=b"# Rules\n", user_id=None
    )
    db.add(
        RepoContextCache(
            repo_full_name="acme/api",
            cache_name="cachedContents/abc",
            content_hash=documents_content_hash(db, "acme/api"),
            model=get_settings().GEMINI_MODEL,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()
    db.expire_all()

    assert db.get(RepoContextCache, "acme/api").expires_at.tzinfo is not None
    cached, inline = await ensure_context_cache(db, "acme/api")
    assert cached == "cachedContents/abc"
    assert "BEGIN DOCUMENT: arch.md" in inline


# --------------------------------------------------------------------------- warm_context_cache / cache_state
CACHE_URL = "https://gemini.test/v1beta/cachedContents"


async def _save(db, text: str, filename: str = "arch.md"):
    await save_document(
        db, repo_full_name="acme/api", filename=filename, content_type="text/markdown",
        data=text.encode(), user_id=None,
    )


def _big(tag: str = "v1") -> str:
    from app.services.documents import MIN_CACHE_CHARS

    return f"# Handbook {tag}\n" + "Services own their data.\n" * (MIN_CACHE_CHARS // 24 + 10)


def _cache_ok(mock_http):
    return mock_http.post(CACHE_URL).respond(
        200, json={"name": "cachedContents/w1", "expireTime": "2099-01-01T00:00:00Z"}
    )


async def test_warm_below_gate_is_inline_without_gemini(db, mock_http):
    from app.services.documents import warm_context_cache

    route = _cache_ok(mock_http)
    await _save(db, "# Small\n")
    assert (await warm_context_cache(db, "acme/api")).status == "inline"
    assert not route.called


async def test_warm_above_gate_builds_once_and_reuses(db, mock_http):
    from app.services.documents import cache_state, warm_context_cache

    route = _cache_ok(mock_http)
    await _save(db, _big())
    assert cache_state(db, "acme/api").status == "pending"
    assert (await warm_context_cache(db, "acme/api")).status == "cached"
    assert cache_state(db, "acme/api").status == "cached"
    state = await warm_context_cache(db, "acme/api")
    assert (state.status, state.error) == ("cached", None)
    assert route.call_count == 1


async def test_warm_failure_is_pending_with_reason(db, mock_http):
    from app.services.documents import cache_state, warm_context_cache

    mock_http.post(CACHE_URL).respond(500, json={"error": {"message": "backend unavailable"}})
    await _save(db, _big())
    state = await warm_context_cache(db, "acme/api")
    assert state.status == "pending"
    assert "Gemini 500" in state.error and "gemini-key-1234" not in state.error
    assert cache_state(db, "acme/api").status == "pending"


async def test_warm_without_gemini_key_is_pending(db, mock_http, monkeypatch):
    from app.core.config import reload_settings
    from app.services.documents import warm_context_cache

    monkeypatch.setenv("GEMINI_API_KEY", "")
    reload_settings()
    route = _cache_ok(mock_http)
    await _save(db, _big())
    state = await warm_context_cache(db, "acme/api")
    assert (state.status, state.error) == ("pending", "Gemini is not configured")
    assert not route.called


def test_cache_state_none_without_documents(db):
    from app.services.documents import cache_state

    assert cache_state(db, "acme/api").status == "none"
