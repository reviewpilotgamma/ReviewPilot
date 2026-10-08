# Plan: Recurring themes from stored ReviewPilot comments

## Context Snapshot

| Kind | Symbols |
| --- | --- |
| Existing | `PRReview`, `ReviewFeedback`, `reviews.list_reviews`, `metrics` APIs, `gemini.generate`, `review_parser._section`, `deps.scoped_repos`/`csrf_protect`, `main.create_app` router loop; frontend `App.tsx` routes, `Sidebar.NAV_ITEMS`, `History.tsx`, `Dashboard.tsx` Card/EmptyState/ErrorState, `MarkdownView`, `VerdictBadge`, `useWorkspace().selectedRepo`, `endpoints.ts`, `pages.test.tsx`, `components.test.tsx` |
| New | `models/insight.py::ReviewInsightSnapshot`; migration `0004_review_insights.py`; `services/insights.py`; `api/insights.py`; `schemas/insights.py`; frontend `pages/Insights.tsx`, `hooks/useInsights.ts`, types `InsightSnapshot`/`InsightState`/`InsightTheme` |
| Modified | `models/__init__.py`, `main.py`, `review_parser.py` (public findings excerpt), `App.tsx`, `Sidebar.tsx`, `History.tsx`, `endpoints.ts`, `types/api.ts` |

### Hotspot map

| Requirement | Files / symbols |
| --- | --- |
| FR1 storage | `models/insight.py`, `0004_review_insights.py` |
| FR2–FR6 analyze + GET | `services/insights.py`, `api/insights.py`, `schemas/insights.py` |
| Findings cards | `review_parser.findings_excerpt` |
| FR7 page | `pages/Insights.tsx`, routing, sidebar |
| FR8 History link | `History.tsx` |

### Design notes

- Watermark is `through_review_id` (max review id included). Pending = reviews
  in repo with `id > watermark`, ordered by `id` ascending, limit `MAX_NEW = 50`.
- Rebuild: newest 50 by `id` desc, then chronological for the prompt.
- Gemini system prompt asks for JSON only: `summary_markdown`, `themes`
  (`title`, `severity`, `count`, `last_seen_review_id`, `example_review_ids`,
  `evidence`), `new_this_period`, `still_showing`. Parse fenced or raw JSON;
  sanitize ids against that repo's review ids.
- `ran_model` is true only when Gemini was called.

## Phase 1 — Backend

- [x] 1.1 Model, migration, findings excerpt, insight service, API, tests
- [x] 1.2 Quality gate: `ruff check .`, `pytest` (insights + review_parser + metrics + reviews_api)

## Phase 2 — Frontend

- [x] 2.1 Types, API, hook, Insights page, nav, History link, tests
- [x] 2.2 Quality gate: `npm run lint`, `npm run typecheck`, `npm test`

## Implementation Notes

- Snapshots are append-only; GET uses the newest row per repo. Watermark is
  `through_review_id`. Incremental Gemini user payload is previous themes JSON
  plus compact cards for pending reviews (oldest first, cap 50).
- Unhelpful-majority reviews are omitted from cards; the batch still advances
  the watermark when mixed. A batch with zero usable cards returns 422.
- Full `ruff check .` / full `pytest` may fail if another in-progress track
  leaves `prompts.py` in a temporarily invalid state; insights modules are
  clean.
