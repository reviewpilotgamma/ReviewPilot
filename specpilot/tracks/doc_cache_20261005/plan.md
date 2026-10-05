# Plan: Architecture docs + Gemini context caching

## Context Snapshot

| Kind | Symbols |
| --- | --- |
| Existing | `RepoRule`, `gemini.generate`, `truncate_diff`, `Rules.tsx`, `rulesApi` |
| New | `RepoDocument`, `RepoContextCache`, documents API, `ensure_context_cache`, multipart upload UI |
| Modified | `config.MAX_DIFF_CHARS`, `reviewer`, `gemini.generate`, `.env.example` |

## Phase 1 — Data + API

- [x] 1. Models + Alembic migration for `repo_documents` and `repo_context_caches`
- [x] 2. Document extract/upload/list/delete service + routes under `/rules/{owner}/{repo}/documents`
- [x] 3. Config: `MAX_DIFF_CHARS` default 0 (unlimited), `GEMINI_CACHE_TTL_SECONDS`

## Phase 2 — Gemini cache + reviews

- [x] 4. Gemini create/delete cachedContents; `generate(..., cached_content=)`
- [x] 5. Wire reviewer/manual/plan to ensure cache and pass docs; remove default 120k truncate
- [x] 6. Backend tests for truncate(0) and document assembly

## Phase 3 — Frontend

- [x] 7. Rules UI multi-file upload + list/delete; client FormData helper
- [x] 8. Frontend typecheck/lint
