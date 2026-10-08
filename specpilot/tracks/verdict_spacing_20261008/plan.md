# Wider spacing in the review verdict line — Plan

## Context snapshot

**Modified symbols:** the verdict line in `render_comment`'s header (`backend/app/services/reviewer.py`), `SAMPLE_COMMENT` (`frontend/src/pages/Landing.tsx`).

**New symbols:** `META_SEPARATOR` (`reviewer.py`).

## Hotspot map

| Area | File | Change |
| --- | --- | --- |
| Reviewer | `backend/app/services/reviewer.py` | `META_SEPARATOR = "&emsp;·&emsp;"` used in the verdict line |
| BE tests | `backend/tests/test_reviewer.py` | Assert the separator |
| Landing | `frontend/src/pages/Landing.tsx` | Same separator in the sample |

## Phase 1: Spacing

- [x] **1.1 Em-space separators.** `6201835` Update the files above. Gate: `ruff check .`, `pytest`, `npm run lint`, `npm run typecheck`, `npm test`.
