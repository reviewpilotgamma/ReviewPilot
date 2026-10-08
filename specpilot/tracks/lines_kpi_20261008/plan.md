# Replace "Helpful rate" KPI with "Lines reviewed" — Plan

## Context snapshot

**Existing symbols that stay:** `PRReview.lines_reviewed`, `MetricCard` (shows "No data yet" when the value is "—"), `add_review` test helper (`lines_reviewed=10`), `ReviewFeedback` and `feedback_counts_for`.

**Modified symbols:** `MetricsSummary` (backend schema and TS type), `metrics.summary`, the Dashboard KPI grid.

**New symbols:** the `lines_reviewed` field on `MetricsSummary`.

## Hotspot map

| Area | File | Change |
| --- | --- | --- |
| Schema | `backend/app/schemas/metrics.py` | Swap `helpful_rate: float \| None` for `lines_reviewed: int` |
| Service | `backend/app/services/metrics.py` (`summary`) | Add `COALESCE(SUM(lines_reviewed), 0)` to the totals select. Remove the feedback query. Return `0` when there are no repos |
| BE tests | `backend/tests/test_metrics.py`, `backend/tests/e2e/test_dashboard_flow.py` | Assert `lines_reviewed` and drop the `helpful_rate` assertions |
| Types | `frontend/src/types/api.ts` (`MetricsSummary`) | Swap `helpful_rate` for `lines_reviewed: number` |
| Page | `frontend/src/pages/Dashboard.tsx` | Replace the card and swap the `ThumbsUp` import for `FileCode2` |
| FE tests | `frontend/src/pages/pages.test.tsx` | Assert the card renders `12,480` and Helpful rate is gone |

## Phase 1: Lines reviewed KPI

- [x] **1.1 Backend metric.** `0e6b311` Update the schema and service as in the hotspot map. Tests: `test_summary_aggregates` asserts `lines_reviewed == 40`; `test_summary_empty` asserts `0` for no reviews and for no repos; the e2e dashboard flow asserts `lines_reviewed` instead of `helpful_rate`. Gate: `ruff check .`, `pytest`.
- [x] **1.2 Frontend card.** `dd67dcd` Update the type and the Dashboard card (`FileCode2`, `data?.lines_reviewed?.toLocaleString() ?? "—"`, hint "Diff lines read by the AI"). Add a Vitest case for the card. Gate: `npm run lint`, `npm run typecheck`, `npm test`.
