# Remove manual "Run review" — Plan

## Context snapshot

**Existing symbols that stay:** `assemble_comment`, `truncate_diff`, `count_changed_lines`, `handle_review`, `POST /api/v1/auth/dev-login`, `local_workspace` / `DEFAULT_LOCAL_REPO`, `ReviewDetail`, `reviews_service.review_detail`, the `NotFound` catch-all route.

**Removed symbols:** `RunReview` page, `/run` route, the "Run review" `NAV_ITEMS` entry, `reviewsApi.runManual`, `ManualReviewInput`, `POST /api/v1/reviews/manual` (`create_manual_review`), `ManualReviewIn`, `run_manual_review`, `diff_stats`, `EmptyDiffError`, `scripts/run_review.py`.

**Modified symbols:** `assemble_comment` (requester trigger set becomes `{"comment"}`), `backend/.env.example` local-mode comment, `test_local_mode.py`, `pages.test.tsx`.

**New symbols:** none.

## Hotspot map

| Area | File | Change |
| --- | --- | --- |
| Frontend page | `frontend/src/pages/RunReview.tsx` | Delete |
| Routing | `frontend/src/App.tsx` (lines 10, 39) | Remove the lazy import and the `/run` route |
| Nav | `frontend/src/components/layout/Sidebar.tsx` (lines 2, 8) | Remove the entry and the `Sparkles` import |
| API client | `frontend/src/services/endpoints.ts` (lines 11, 52) | Remove `runManual` and the `ManualReviewInput` import |
| Types | `frontend/src/types/api.ts` (line 108) | Remove `ManualReviewInput` |
| FE tests | `frontend/src/pages/pages.test.tsx` (line 6, lines 64–94) | Remove the import and the "Run review page" block. Add a test that `/run` renders Not Found |
| API | `backend/app/api/reviews.py` (lines 13, 16, 31–57) | Remove the endpoint and any imports it leaves unused |
| Schema | `backend/app/schemas/reviews.py` (lines 24–37) | Remove `ManualReviewIn` and any imports it leaves unused |
| Service | `backend/app/services/reviewer.py` (lines 18, 91, 130, 185–247) | Remove `run_manual_review`, `diff_stats`, the `EmptyDiffError` import, and `"manual"` from the trigger set |
| Errors | `backend/app/services/errors.py` (lines 45–48) | Remove `EmptyDiffError` |
| Script | `backend/scripts/run_review.py` | Delete |
| BE tests | `backend/tests/test_local_mode.py` | Remove the manual-review and script tests and their unused helpers/imports. Keep the dev-login and installations tests. Add a test that `POST /reviews/manual` returns 404/405 |
| Docs | `backend/.env.example` (lines 9–12) | Drop the script line and the "reviews are saved" wording |

## Tasks

### Phase 1 — Remove the frontend Run review UI

1. [x] Remove `/run` from `App.tsx` and the nav entry and `Sparkles` import from `Sidebar.tsx`. Delete `RunReview.tsx`. `ba7d20b`
2. [x] Remove `runManual` from `endpoints.ts` and `ManualReviewInput` from `types/api.ts`. `363ea5b`
3. [~] Update `pages.test.tsx`: delete the "Run review page" describe block and its import. Add a test that routing to `/run` shows Not Found. If a sidebar test exists in `components.test.tsx`, assert that "Run review" is gone.
4. [ ] Quality gate from `frontend/`: `npm run lint`, `npm run typecheck`, `npm test`. Commit as `refactor(frontend): Remove Run review page`.

### Phase 2 — Remove the backend manual review path

1. [ ] Delete `create_manual_review` in `api/reviews.py` and `ManualReviewIn` in `schemas/reviews.py`, then prune unused imports (`reviewer`, `get_settings`, `EmptyDiffError`, `NotConfiguredError`, `ServiceError`, `CurrentUser`, `field_validator`, `parse_repo_full_name`). Check each one with grep before removing it.
2. [ ] Delete `run_manual_review` and `diff_stats` from `reviewer.py`, drop the `EmptyDiffError` import, and change `{"comment", "manual"}` to `{"comment"}` (or a plain `trigger == "comment"`). Delete `EmptyDiffError` from `errors.py`.
3. [ ] Delete `backend/scripts/run_review.py`. Keep `scripts/__init__.py`, because `import_legacy_db.py` still lives there.
4. [ ] Update `test_local_mode.py`: remove `MANUAL`, `_gemini`, `GEMINI_URL`, `DIFF`, `LLM_OUTPUT`, the `scripts.run_review` import, and the five manual/script tests. Add `test_manual_review_endpoint_is_gone` (POST returns 404 or 405). Update the module docstring.
5. [ ] Update the local-mode comment in `backend/.env.example`.
6. [ ] Quality gate from `backend/`: `ruff check .`, `pytest`. Run a final grep to confirm none of the removed symbols remain in `backend/` or `frontend/src/`. Commit as `refactor(backend): Remove manual review endpoint and script`.
