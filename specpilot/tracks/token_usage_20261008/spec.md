# Show tokens used per review in Review History — Specification

## Overview

Add a **Tokens** column to the Review History table showing how many Gemini tokens were spent producing each
review. Token usage is only logged today (`gemini.generate` reads `usageMetadata` for cache-hit logging), so it
must be captured and stored per review.

## Functional Requirements

1. Each Gemini call's token count is `usageMetadata.totalTokenCount` (input, including cached documents, plus
   output and thinking). When that field is missing, use `promptTokenCount + candidatesTokenCount +
   thoughtsTokenCount`.
2. A review's total is the sum over every successful Gemini call that produced it: the single call for small PRs,
   or all succeeded batches plus the merge call for batched PRs.
3. The total is stored on `pr_reviews.tokens_used` (nullable integer).
4. `ReviewListItem` (and therefore `ReviewDetail`) exposes `tokens_used: int | None`.
5. The History table shows a **Tokens** column after **Lines**, formatted like Lines (`12,480`). The Dashboard's
   recent-reviews table is unchanged; the column is enabled with a `showTokens` prop.

## Non-Functional Requirements

- The migration is additive and idempotent (same pattern as `0008`); no table rebuild on upgrade, so
  `review_feedback` rows are never touched.
- Tests mock Gemini; no live calls.

## Sad Paths & Error States

- Older reviews, or calls that report no usage → `null` → the cell shows "—".
- Failed, retried or timed-out batches are not counted (they produce no usable usage data).
- When the merge call fails and batches are joined in code, only the batch tokens count.

## Edge Cases

- Mixed usage reporting across calls: sum the calls that report usage; `null` only when none do.
- Idempotent job retry of an already-saved review: no new LLM call, stored value unchanged.

## Acceptance Criteria

- A new review stores a non-null `tokens_used` equal to the sum of its calls.
- `GET /api/v1/reviews` returns `tokens_used`.
- The History page shows the Tokens column, with "—" for `null`; the Dashboard does not.
- `ruff check .`, `pytest`, `npm run lint`, `npm run typecheck` and `npm test` pass.

## Out of Scope

- Dollar cost, input/output breakdown.
- Tokens on the Dashboard or in the review drawer.
- Insights and `@plan` token usage (not PR reviews).
- Backfilling older reviews.
