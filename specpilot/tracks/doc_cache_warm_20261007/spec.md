# Build the Gemini context cache at upload time

## Overview

Today an upload or delete only extracts text and invalidates the repo's Gemini context cache. The cache is
rebuilt lazily on the next PR review, so the Rules page shows a misleading "Inline reference" badge until then.
This track builds the cache synchronously inside the upload and delete requests, so the UI shows the real state
as soon as the request returns.

## Functional Requirements

1. **Upload warms the cache.** `POST /rules/{owner}/{repo}/documents` saves the document. If the repo's combined
   documents are at or above `MIN_CACHE_CHARS` and Gemini is configured, it creates the cache before responding.
   Below the gate no Gemini call is made and the status is `inline`.
2. **Batch control.** An optional query parameter `warm` (default `true`). With `warm=false`, the document is
   saved and the cache invalidated, but no cache is built.
3. **Frontend batches.** The Rules page uploads a multi-file pick one file at a time, sending `warm=false` for all
   but the last file, so a batch of N files builds one cache.
4. **Delete re-warms.** `DELETE …/documents/{id}` invalidates the cache, then rebuilds it before returning 204 if
   the remaining documents are still at or above the gate.
5. **Response reports the outcome.** The upload response adds `cache_status` (`none | inline | cached | pending`)
   and `cache_error` (a short reason, or `null`).
6. **New `pending` status.** The list endpoint's `cache_status` gains `pending`: the documents are at or above
   the gate but no cache exists (a failed build, a batch in progress, or after a restart). Reviews still build the
   cache lazily, so a `pending` repo is cached on its next review.
7. **UI.**
   - The upload button reads "Uploading & building cache…" while busy.
   - The badge has a fourth amber state, "Will be cached on next review".
   - When `cache_error` is set, the toast is a warning ("Uploaded arch.pdf — Gemini cache could not be built:
     <reason>") instead of a success.

## Non-Functional Requirements

- No migration and no new dependencies.
- Uploads below the gate make no Gemini calls, so their latency is unchanged.
- The API key never appears in `cache_error`.
- Tests mock Gemini with respx; no live calls.

## Sad Paths & Error States

- **Cache build fails** (Gemini 4xx/5xx/timeout): the upload still returns 201 with `cache_status=pending` and
  `cache_error` set. The document is saved and nothing is lost.
- **Gemini not configured:** no build is attempted. `cache_status=pending`, `cache_error="Gemini is not
  configured"`.
- **Invalid upload** (type, size, empty): returns 400 as today; no build is attempted.

## Edge Cases

- Re-uploading identical content leaves the content hash unchanged: the existing cache is reused, with no rebuild
  and no Gemini call.
- Deleting down to below the gate returns `inline`; deleting the last document returns `none`.
- A review that runs while an upload is warming: both paths go through `ensure_context_cache`'s content-hash
  check, so at worst one extra cache is built and the stored row wins.

## Acceptance Criteria

- After uploading a large document, the list shows "Gemini cache ready" immediately, with no review needed. The
  next review reuses that cache and creates no new one (checked in E2E).
- A 3-file batch creates exactly one cache.
- A failed build returns 201 with `pending` and the UI shows a warning toast; the next review builds the cache.
- `ruff check .`, `pytest`, `npm run lint`, `npm run typecheck` and `npm test` all pass.

## Out of Scope

- Background or durable warming (synchronous was chosen).
- Extracted-text preview.
- `.docx` or OCR support.
