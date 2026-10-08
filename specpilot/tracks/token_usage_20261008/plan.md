# Show tokens used per review in Review History — Plan

## Context snapshot

**Existing symbols that stay:** `PRReview.lines_reviewed`, `parse_review`, `fallback_merge`, the `Table`/`Row`/`Cell`
UI primitives, migration `0008_review_followups` (the pattern to follow).

**Modified symbols:** `GeminiResult`, `gemini.generate`, `PRReview`, `BatchOutcome`, `BatchedReview`,
`_review_one_batch`, `_merge_reviews`, `_review_in_batches`, `handle_review`, `ReviewListItem` (backend schema and
TS type), `ReviewsTable`, `History`.

**New symbols:** `gemini._usage_tokens`, `reviewer.sum_tokens`, migration `0009_review_tokens`,
`format.formatTokens`, the `showTokens` prop.

## Hotspot map

| Area | File | Change |
| --- | --- | --- |
| Gemini client | `backend/app/services/gemini.py` | `GeminiResult.tokens_used`, `_usage_tokens(usage)` with fallback sum |
| Model | `backend/app/models/pr_review.py` | `tokens_used: Mapped[int \| None]` |
| Migration | `backend/alembic/versions/0009_review_tokens.py` | Idempotent `ADD COLUMN tokens_used INTEGER` |
| Reviewer | `backend/app/services/reviewer.py` | Carry tokens through batches/merge; set `PRReview.tokens_used` |
| Schema | `backend/app/schemas/reviews.py` | `ReviewListItem.tokens_used: int \| None = None` |
| BE tests | `test_gemini.py`, `test_migration_review_tokens.py`, `test_reviewer.py`, `test_batched_review.py`, `test_reviews_api.py` | Cover the above |
| Types | `frontend/src/types/api.ts` | `tokens_used?: number \| null` |
| Format | `frontend/src/lib/format.ts` | `formatTokens()` → "—" for null |
| Table | `frontend/src/components/reviews/ReviewsTable.tsx` | `showTokens` prop, Tokens column after Lines |
| Page | `frontend/src/pages/History.tsx` | Pass `showTokens` |
| FE tests | `frontend/src/lib/lib.test.ts`, `frontend/src/pages/pages.test.tsx` | Format + column rendering |

## Phase 1: Capture and store token usage

- [x] **1.1 Gemini usage.** `4ca6ab9` Add `tokens_used: int | None = None` to `GeminiResult`; add `_usage_tokens(usage)`
  (`totalTokenCount`, else the sum of prompt/candidates/thoughts counts, else `None`); set it in `generate()`.
  Tests: total present, fallback sum, missing usage → `None`. Gate: `ruff check .`, `pytest`.
- [x] **1.2 Column and migration.** `99303ae` Add `PRReview.tokens_used` and `0009_review_tokens` (add the column only when
  missing; downgrade drops it with SQLite foreign keys off, like `0008`). Test upgrade/downgrade and that feedback
  rows survive. Gate: `ruff check .`, `pytest`.
- [~] **1.3 Reviewer totals.** Add `sum_tokens(*counts) -> int | None`. `BatchOutcome.tokens`; `_merge_reviews`
  returns the merge call's tokens; `BatchedReview.tokens_used` = succeeded batches + merge; `handle_review` sets
  `PRReview(tokens_used=...)` on both paths. Tests: single call, batches + merge, merge fallback, failed batch
  excluded. Gate: `ruff check .`, `pytest`.
- [ ] **1.4 API field.** Add `tokens_used` to `ReviewListItem`. Test the list endpoint returns it (value and
  `null`). Gate: `ruff check .`, `pytest`.

## Phase 2: Tokens column on Review History

- [ ] **2.1 Type and formatter.** `tokens_used?: number | null` on `ReviewListItem`; `formatTokens()` in
  `lib/format.ts`. Vitest cases. Gate: `npm run lint`, `npm run typecheck`, `npm test`.
- [ ] **2.2 Table column.** `showTokens` prop on `ReviewsTable` (header "Tokens" after "Lines"); `History` passes
  it. Vitest: History shows the value and "—"; Dashboard has no Tokens column. Gate: same as 2.1.
- [ ] **2.3 Docs.** Update the README if it documents the History columns.

## Phase 3: Verification

- [ ] Run a real `@review` on a sandbox PR and confirm History shows a non-zero token count.
