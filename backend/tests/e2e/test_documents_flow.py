"""Repo documents end to end: upload → inline injection or Gemini context cache → reuse → invalidation."""

from __future__ import annotations

from app.services.documents import MIN_CACHE_CHARS
from tests.e2e.diffs import PLANTED_SCENARIOS

DOCS_URL = "/api/v1/rules/acme/api/documents"
SMALL_DOC = "# Architecture\n\nAll payments go through the billing SDK with idempotency keys.\n"
MARKER = "BEGIN DOCUMENT: arch.md"


def big_doc(tag: str) -> str:
    line = f"Rule {tag}: services own their data; cross-service access goes through versioned APIs.\n"
    return "# Architecture handbook\n\n" + line * (MIN_CACHE_CHARS // len(line) + 50)


def upload(client, text: str, filename: str = "arch.md") -> int:
    response = client.post(DOCS_URL, files={"file": (filename, text.encode("utf-8"), "text/markdown")})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def review(pipeline, number: int) -> dict:
    pipeline.open_pr(number, PLANTED_SCENARIOS["no_timeout_retry"])
    await pipeline.drain()
    return pipeline.llm.requests[-1]


async def test_small_document_is_injected_inline(pipeline, login):
    login()
    upload(pipeline.client, SMALL_DOC)

    body = await review(pipeline, 30)

    assert pipeline.llm.cache_creates == []
    assert "cachedContent" not in body
    system = pipeline.llm.system_prompt(body)
    assert MARKER in system and "billing SDK with idempotency keys" in system
    assert len(pipeline.reviews()) == 1


async def test_large_document_uses_cache_reuses_and_invalidates(pipeline, login):
    login()
    doc_id = upload(pipeline.client, big_doc("v1"))

    first = await review(pipeline, 31)
    assert len(pipeline.llm.cache_creates) == 1
    assert first["cachedContent"] == "cachedContents/e2e1"
    assert MARKER not in pipeline.llm.system_prompt(first)
    cached_text = pipeline.llm.cache_creates[0]["contents"][0]["parts"][0]["text"]
    assert "Rule v1" in cached_text and "acme/api" in cached_text

    second = await review(pipeline, 32)
    assert len(pipeline.llm.cache_creates) == 1, "unchanged documents must reuse the cache"
    assert second["cachedContent"] == "cachedContents/e2e1"

    # Re-uploading the same filename with new content invalidates the cache.
    assert upload(pipeline.client, big_doc("v2")) == doc_id
    assert pipeline.llm.cache_deletes == ["e2e1"]
    third = await review(pipeline, 33)
    assert len(pipeline.llm.cache_creates) == 2
    assert third["cachedContent"] == "cachedContents/e2e2"
    assert "Rule v2" in pipeline.llm.cache_creates[1]["contents"][0]["parts"][0]["text"]

    # Deleting the only document drops the cache and the next review has no documents.
    assert pipeline.client.delete(f"{DOCS_URL}/{doc_id}").status_code == 204
    assert pipeline.llm.cache_deletes == ["e2e1", "e2e2"]
    fourth = await review(pipeline, 34)
    assert "cachedContent" not in fourth
    assert MARKER not in pipeline.llm.system_prompt(fourth)
    assert len(pipeline.reviews()) == 4


async def test_cache_create_failure_falls_back_to_inline(pipeline, login):
    login()
    upload(pipeline.client, big_doc("v1"))
    pipeline.llm.fail_next(500)  # consumed by the cachedContents create (docs load runs before generate)

    body = await review(pipeline, 35)

    assert pipeline.llm.cache_creates == []
    assert "cachedContent" not in body
    assert MARKER in pipeline.llm.system_prompt(body)
    [review_row] = pipeline.reviews()
    assert review_row.verdict == "warning"
