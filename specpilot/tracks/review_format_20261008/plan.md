# Structured, highlighted review comments — Plan

## Context snapshot

**Existing symbols that stay:** `SEV_RE`, `_section`, `extract_summary`, `parse_review`, `BANNER`, `render_comment`.

**Modified symbols:** `REVIEW_SYSTEM_TEMPLATE` (and so `DEFAULT_REVIEW_TEMPLATE`), `MERGE_SYSTEM_PROMPT`,
`VERBOSITY_DIRECTIVES`, `SAMPLE_COMMENT` (Landing).

**New symbols:** none.

## Hotspot map

| Area | File | Change |
| --- | --- | --- |
| Prompts | `backend/app/services/prompts.py` | New OUTPUT FORMAT block with example and rules; same rules in `MERGE_SYSTEM_PROMPT`; verbosity wording |
| Fixture | `backend/tests/fixtures/gemini_review.md` | New format |
| BE tests | `backend/tests/test_prompts.py`, `backend/tests/test_review_parser.py` | Format rules present; parser on new format |
| Landing | `frontend/src/pages/Landing.tsx` | `SAMPLE_COMMENT` in the new layout |

## Phase 1: Review format

- [x] **1.1 Prompt format.** `c7b07ad` Rewrite the review and merge OUTPUT FORMAT blocks and verbosity directives. Gate: `ruff check .`, `pytest`.
- [x] **1.2 Fixture and tests.** `01d5ce4` Update `gemini_review.md`; add prompt-rule and parser tests. Gate: `ruff check .`, `pytest`.
- [x] **1.3 Landing sample.** `8b8940f` Update `SAMPLE_COMMENT`. Gate: `npm run lint`, `npm run typecheck`, `npm test`.
