"""Repo documents end to end: upload builds the Gemini context cache (or inline) → reviews reuse it → invalidation."""

from __future__ import annotations

from app.services.documents import MIN_CACHE_CHARS
from tests.e2e.diffs import PLANTED_SCENARIOS

DOCS_URL = "/api/v1/rules/acme/api/documents"
SMALL_DOC = "# Architecture\n\nAll payments go through the billing SDK with idempotency keys.\n"
MARKER = "BEGIN DOCUMENT: arch.md"


def big_doc(tag: str) -> str:
    line = f"Rule {tag}: services own their data; cross-service access goes through versioned APIs.\n"
    return "# Architecture handbook\n\n" + line * (MIN_CACHE_CHARS // len(line) + 50)


def upload(client, text: str, filename: str = "arch.md", **params) -> dict:
    response = client.post(
        DOCS_URL, params=params, files={"file": (filename, text.encode("utf-8"), "text/markdown")}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def review(pipeline, number: int) -> dict:
    pipeline.open_pr(number, PLANTED_SCENARIOS["no_timeout_retry"])
    await pipeline.drain()
    return pipeline.llm.requests[-1]


def cached_text(pipeline, index: int) -> str:
    return pipeline.llm.cache_creates[index]["contents"][0]["parts"][0]["text"]


async def test_small_document_is_injected_inline(pipeline, login):
    login()
    assert upload(pipeline.client, SMALL_DOC)["cache_status"] == "inline"

    body = await review(pipeline, 30)

    assert pipeline.llm.cache_creates == []
    assert "cachedContent" not in body
    system = pipeline.llm.system_prompt(body)
    assert MARKER in system and "billing SDK with idempotency keys" in system
    assert len(pipeline.reviews()) == 1


async def test_large_document_cached_at_upload_reused_and_invalidated(pipeline, login):
    login()
    uploaded = upload(pipeline.client, big_doc("v1"))

    # The cache exists before any review runs.
    assert uploaded["cache_status"] == "cached"
    assert len(pipeline.llm.cache_creates) == 1 and pipeline.llm.generate_calls == 0
    assert "Rule v1" in cached_text(pipeline, 0) and "acme/api" in cached_text(pipeline, 0)

    first = await review(pipeline, 31)
    second = await review(pipeline, 32)
    assert len(pipeline.llm.cache_creates) == 1, "reviews must reuse the cache built at upload"
    assert first["cachedContent"] == second["cachedContent"] == "cachedContents/e2e1"
    assert MARKER not in pipeline.llm.system_prompt(first)

    # Re-uploading the same filename with new content swaps the cache during the upload.
    changed = upload(pipeline.client, big_doc("v2"))
    assert (changed["id"], changed["cache_status"]) == (uploaded["id"], "cached")
    assert pipeline.llm.cache_deletes == ["e2e1"] and len(pipeline.llm.cache_creates) == 2
    assert "Rule v2" in cached_text(pipeline, 1)
    third = await review(pipeline, 33)
    assert third["cachedContent"] == "cachedContents/e2e2"
    assert len(pipeline.llm.cache_creates) == 2

    # Deleting the only document drops the cache and the next review has no documents.
    assert pipeline.client.delete(f"{DOCS_URL}/{uploaded['id']}").status_code == 204
    assert pipeline.llm.cache_deletes == ["e2e1", "e2e2"]
    assert pipeline.client.get(DOCS_URL).json()["cache_status"] == "none"
    fourth = await review(pipeline, 34)
    assert "cachedContent" not in fourth
    assert MARKER not in pipeline.llm.system_prompt(fourth)
    assert len(pipeline.reviews()) == 4


async def test_batch_upload_builds_one_cache(pipeline, login):
    login()
    statuses = [
        upload(pipeline.client, big_doc("a"), "a.md", warm="false")["cache_status"],
        upload(pipeline.client, big_doc("b"), "b.md", warm="false")["cache_status"],
        upload(pipeline.client, SMALL_DOC, "c.md")["cache_status"],
    ]

    assert statuses == ["pending", "pending", "cached"]
    assert len(pipeline.llm.cache_creates) == 1
    text = cached_text(pipeline, 0)
    assert all(f"BEGIN DOCUMENT: {name}" in text for name in ("a.md", "b.md", "c.md"))
    body = await review(pipeline, 36)
    assert body["cachedContent"] == "cachedContents/e2e1"


async def test_failed_upload_build_is_pending_then_built_by_next_review(pipeline, login):
    login()
    pipeline.llm.fail_next(500)  # consumed by the cachedContents create during the upload

    uploaded = upload(pipeline.client, big_doc("v1"))

    assert uploaded["cache_status"] == "pending" and "Gemini 500" in uploaded["cache_error"]
    assert pipeline.llm.cache_creates == []
    body = await review(pipeline, 35)
    assert len(pipeline.llm.cache_creates) == 1, "the review builds the cache lazily"
    assert body["cachedContent"] == "cachedContents/e2e1"
    assert pipeline.client.get(DOCS_URL).json()["cache_status"] == "cached"
    [review_row] = pipeline.reviews()
    assert review_row.verdict == "warning"
