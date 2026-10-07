# Plan: Build the Gemini context cache at upload time

## Context Snapshot

| Kind | Symbols |
| --- | --- |
| Existing | `documents.ensure_context_cache`, `invalidate_context_cache`, `save_document`, `delete_document`, `assemble_documents_text`, `MIN_CACHE_CHARS`, `RepoContextCache`; `api/documents.py::upload_document`/`delete_document`/`_cache_status`; `schemas/documents.py::DocumentOut`/`DocumentListOut`; `rulesApi.uploadDocument`, `useUploadDocument`, `Rules.tsx::DocumentPanel`, `ToastContext`; `tests/e2e/test_documents_flow.py` |
| New | `documents.CacheState` (dataclass: `status`, `error`), `documents.cache_state(db, repo)`, `documents.warm_context_cache(db, repo) -> CacheState`; `DocumentUploadOut` schema; toast kind `warning` |
| Modified | `ensure_context_cache` (build step extracted into `_build_cache`, which raises; lazy path unchanged), `upload_document` (`warm` query param, returns `DocumentUploadOut`), `delete_document` route (re-warm), `_cache_status` → `cache_state`, `CacheStatus` types on both sides, `Rules.tsx` (batch `warm=false`, badge, button label, warning toast) |

### Hotspot map

| Requirement | Files / symbols |
| --- | --- |
| FR1, FR4, FR6 | `backend/app/services/documents.py` (`warm_context_cache`, `cache_state`, `_build_cache`) |
| FR1, FR2, FR4, FR5 | `backend/app/api/documents.py`, `backend/app/schemas/documents.py` |
| FR3, FR7 | `frontend/src/services/endpoints.ts`, `frontend/src/hooks/useRules.ts`, `frontend/src/pages/Rules.tsx`, `frontend/src/context/ToastContext.tsx`, `frontend/src/types/api.ts` |
| Tests | `backend/tests/test_documents.py`, new `backend/tests/test_documents_api.py`, `backend/tests/e2e/test_documents_flow.py`, `frontend/src/pages/pages.test.tsx` |

## Phase 1 — Backend

- [ ] 1.1 Service: build-on-demand and cache state — `app/services/documents.py`
  - Extract the create-and-store block of `ensure_context_cache` into `async _build_cache(db, key, docs_text,
    content_hash) -> str`. It raises `GeminiNotConfigured`/`GeminiPermanentError`/`GeminiTransientError`.
    `ensure_context_cache` keeps its current behavior: it catches these and returns `(None, docs_text)`.
  - `@dataclass(frozen=True) CacheState(status: str, error: str | None = None)`.
  - `cache_state(db, repo) -> CacheState`:
    - no docs → `none`
    - text below `MIN_CACHE_CHARS` → `inline`
    - a row whose hash and model match and which hasn't expired → `cached`
    - otherwise → `pending`
  - `async warm_context_cache(db, repo) -> CacheState`:
    - Calls `ensure_context_cache` logic with error capture: if the gate isn't met → `cache_state`.
    - Gemini not configured → `pending` with "Gemini is not configured".
    - Gemini error → `pending` with a reason derived from the error (truncated to 200 chars; this never contains
      the key, because errors are built from the response message only).
    - Success → `cached`.
  - Tests in `tests/test_documents.py` (respx):
    - below gate → `inline` and no HTTP call
    - above gate → `cached` and one create
    - same content warmed again → no second create
    - create 500 → `pending` with an error
    - no key → `pending` with "not configured"
    - `cache_state` covers all four values
- [ ] 1.2 API — `app/api/documents.py`, `app/schemas/documents.py`
  - `DocumentUploadOut(DocumentOut)` adds `cache_status: Literal["none","inline","cached","pending"]` and
    `cache_error: str | None`. `DocumentListOut.cache_status` uses the same `Literal`.
  - `upload_document(..., warm: bool = Query(True))`: after `save_document`, `state = await
    warm_context_cache(...)` if `warm`, else `cache_state(...)`. Returns `DocumentUploadOut`.
  - `delete_document`: after delete, `await warm_context_cache(...)`, then 204 (keeps the explicit `Response`).
  - `_cache_status` is replaced by `cache_state(db, repo).status`.
  - New `tests/test_documents_api.py` (`login` + respx):
    - large upload → 201, `cached`, and the list shows `cached`
    - `warm=false` → `pending` with no create
    - small upload → `inline`
    - create 500 → 201, `pending`, `cache_error` set
    - deleting one of two large docs → re-warmed `cached`
    - deleting the last doc → list `none`
- [ ] 1.3 E2E update — `tests/e2e/test_documents_flow.py`
  - Large upload → cache created during the upload (before any review); the first review reuses it
    (`cache_creates == 1`).
  - Add a 3-file batch (`warm=false`, `warm=false`, `warm=true`) → exactly one create.
  - Failure test: `fail_next(500)` before the upload → upload `pending`; the next review builds the cache lazily
    (one create, `cachedContent` set).
- [ ] 1.4 Quality gate: `ruff check .`, `pytest`.

## Phase 2 — Frontend

- [ ] 2.1 Types and API — `types/api.ts`: `CacheStatus = "none" | "inline" | "cached" | "pending"`;
  `RepoDocumentUpload extends RepoDocument { cache_status; cache_error }`. `endpoints.ts`:
  `uploadDocument(repo, file, { warm = true } = {})` appends `?warm=false` when false. `useUploadDocument`
  mutation takes `{ file, warm }`.
- [ ] 2.2 Toast `warning` kind — `ToastContext.tsx`: add `warning` (amber border, `AlertTriangle` icon) and
  `toast.warning(message)`.
- [ ] 2.3 Rules UI — `Rules.tsx::DocumentPanel`:
  - In the loop, `warm: index === files.length - 1`.
  - On a `cache_error`, call `toast.warning(\`Uploaded ${name} — Gemini cache could not be built: ${error}\`)`;
    otherwise `toast.success`.
  - Button label "Uploading & building cache…" while pending.
  - Badge: `pending` → amber "Will be cached on next review"; `inline` → gray "Inline reference (below cache
    size)"; `cached` → emerald "Gemini cache ready".
- [ ] 2.4 Tests — `pages.test.tsx` Rules page:
  - the badge renders for each status
  - a 2-file upload sends `warm=false` then `warm` omitted
  - a `cache_error` shows the warning toast
- [ ] 2.5 Quality gate: `npm run lint`, `npm run typecheck`, `npm test`.

## Implementation Notes

_(filled in during implementation)_
