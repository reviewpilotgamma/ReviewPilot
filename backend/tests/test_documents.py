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
