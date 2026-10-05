from __future__ import annotations

import pytest

from app.services.documents import DocumentError, _safe_name, assemble_documents_text, extract_text
from app.services.documents import save_document, list_documents


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
