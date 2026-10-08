"""Document service edge cases: upload validation, PDF extraction and Gemini cache housekeeping."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import pytest

from app.models import RepoContextCache
from app.services import documents
from app.services.documents import (
    MAX_FILE_BYTES,
    MAX_FILES_PER_REPO,
    DocumentError,
    _parse_expire_time,
    _safe_name,
    delete_document,
    ensure_context_cache,
    extract_text,
    get_document,
    invalidate_context_cache,
    save_document,
)
from tests.conftest import GEMINI_API


def _pdf(text: str | None) -> bytes:
    """A one-page PDF; ``None`` gives a page with no text layer (like a scanned image)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode() if text else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


async def _save(db, data: bytes = b"# Doc\n", filename: str = "arch.md", repo: str = "acme/api"):
    return await save_document(
        db, repo_full_name=repo, filename=filename, content_type="", data=data, user_id=None
    )


@pytest.mark.parametrize("filename", ["", "..", "a/../..", "bad*name.md", "notes"])
def test_safe_name_rejects_unsafe_or_extensionless_names(filename):
    with pytest.raises(DocumentError):
        _safe_name(filename)


def test_safe_name_strips_client_paths():
    assert _safe_name("C:\\Users\\me\\arch.md") == "arch.md"
    assert _safe_name("/tmp/specs/reqs.PDF") == "reqs.PDF"


def test_extract_text_from_pdf():
    assert extract_text("spec.pdf", _pdf("Services own their data")) == "Services own their data"


def test_extract_text_rejects_image_only_pdf():
    with pytest.raises(DocumentError, match="scanned"):
        extract_text("scan.pdf", _pdf(None))


def test_extract_text_without_pdf_support(monkeypatch):
    monkeypatch.setitem(sys.modules, "pypdf", None)
    with pytest.raises(DocumentError, match="PDF support is not installed"):
        extract_text("spec.pdf", b"%PDF-1.4")


def test_extract_text_replaces_invalid_utf8():
    assert extract_text("notes.txt", b"caf\xe9") == "caf\ufffd"


async def test_upload_limits(db, monkeypatch):
    with pytest.raises(DocumentError, match="File is empty"):
        await _save(db, b"")
    with pytest.raises(DocumentError, match="exceeds 5 MB"):
        await _save(db, b"x" * (MAX_FILE_BYTES + 1))

    monkeypatch.setattr(documents, "MAX_FILES_PER_REPO", 2)
    await _save(db, filename="a.md")
    await _save(db, filename="b.md")
    with pytest.raises(DocumentError, match="Maximum of 2 documents"):
        await _save(db, filename="c.md")
    # Replacing an existing file is allowed at the limit.
    replaced = await _save(db, b"# New\n", filename="a.md")
    assert replaced.extracted_text == "# New\n"
    assert replaced.content_type == "application/octet-stream"
    assert MAX_FILES_PER_REPO == 20


async def test_documents_are_scoped_to_their_repository(db):
    doc = await _save(db)
    assert get_document(db, "ACME/API", doc.id) is not None
    assert get_document(db, "acme/web", doc.id) is None
    assert get_document(db, "acme/api", doc.id + 999) is None
    assert await delete_document(db, "acme/web", doc.id) is False
    assert await delete_document(db, "acme/api", doc.id) is True


def _cache_row(db, name: str = "cachedContents/old", content_hash: str = "stale"):
    db.add(
        RepoContextCache(
            repo_full_name="acme/api",
            cache_name=name,
            content_hash=content_hash,
            model="gemini-2.0-flash",
            expires_at=None,
        )
    )
    db.commit()


async def test_invalidate_deletes_the_gemini_cache_and_row(db, mock_http):
    await invalidate_context_cache(db, "acme/api")  # no row: nothing to do

    route = mock_http.delete(f"{GEMINI_API}/cachedContents/old").respond(200, json={})
    _cache_row(db)
    await invalidate_context_cache(db, "Acme/API")
    assert route.called
    assert db.get(RepoContextCache, "acme/api") is None


async def test_invalidate_drops_the_row_even_when_gemini_fails(db, mock_http):
    mock_http.delete(f"{GEMINI_API}/cachedContents/old").respond(400, json={"error": {"message": "bad"}})
    _cache_row(db)
    await invalidate_context_cache(db, "acme/api")
    assert db.get(RepoContextCache, "acme/api") is None


async def test_stale_cache_row_is_replaced_on_next_review(db, mock_http, monkeypatch):
    monkeypatch.setattr(documents, "MIN_CACHE_CHARS", 10)
    deleted = mock_http.delete(f"{GEMINI_API}/cachedContents/old").respond(200, json={})
    created = mock_http.post(f"{GEMINI_API}/cachedContents").respond(
        200, json={"name": "cachedContents/new", "expireTime": "not-a-date"}
    )
    await _save(db, b"# Architecture handbook\n")
    _cache_row(db)

    name, text = await ensure_context_cache(db, "acme/api")
    assert name == "cachedContents/new"
    assert "Architecture handbook" in text
    assert deleted.called and created.called
    row = db.get(RepoContextCache, "acme/api")
    assert row.cache_name == "cachedContents/new"
    assert row.expires_at is None  # unparseable expiry is stored as unknown


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("garbage", None),
        ("2026-10-09T00:00:00Z", datetime(2026, 10, 9, tzinfo=UTC)),
    ],
)
def test_parse_expire_time(raw, expected):
    assert _parse_expire_time(raw) == expected
