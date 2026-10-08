# Remove the aeroplane emoji from the review banner — Plan

## Context snapshot

**Modified symbols:** `BANNER` (`backend/app/services/reviewer.py`), `SAMPLE_COMMENT` (`frontend/src/pages/Landing.tsx`).

**Existing symbols that stay:** `PLAN_BANNER`, `VERDICT_LABELS`, `render_reply` templates.

## Hotspot map

| Area | File | Change |
| --- | --- | --- |
| Reviewer | `backend/app/services/reviewer.py` | `BANNER = "## ReviewPilot Architectural Audit"` |
| BE tests | `backend/tests/test_reviewer.py` | Assert the new banner |
| Landing | `frontend/src/pages/Landing.tsx` | Sample comment banner |
| FE tests | `frontend/src/pages/pages.test.tsx` | Fixture `full_markdown` banner |

## Phase 1: Banner

- [~] **1.1 Drop the emoji.** Update the four files above. Gate: `ruff check .`, `pytest`, `npm run lint`, `npm run typecheck`, `npm test`.
