# PR description vs diff scope check — Plan

## Context snapshot

**Existing symbols that stay:** `PullRequest.body` (already fetched), `_section`, `_severity_counts`, `parse_review`.

**Modified symbols:** `OUTPUT_FORMAT`, `MERGE_SYSTEM_PROMPT`, `build_pr_context`, `build_batch_context`,
`build_merge_content` (`backend/app/services/prompts.py`); `MERGED_SECTIONS`, `handle_review`
(`backend/app/services/reviewer.py`); `SAMPLE_COMMENT` (Landing).

**New symbols:** `NO_DESCRIPTION` reuse; the `manifest` keyword on `build_pr_context`; `format_manifest` helper.

## Hotspot map

| Area | File | Change |
| --- | --- | --- |
| Prompt | `backend/app/services/prompts.py` | Scope Check in `OUTPUT_FORMAT`; batch note; description in merge content; merge rules |
| Context | `backend/app/services/prompts.py` (`build_pr_context`) | Optional `manifest` → "Changed files" list |
| Reviewer | `backend/app/services/reviewer.py` | Pass `plan.files` manifest in the single-pass call; `MERGED_SECTIONS` starts with "Scope Check" |
| BE tests | `test_prompts.py`, `test_review_parser.py`, `test_batched_review.py`, fixture `gemini_review.md` | Rules, context, merge input, fallback, severity isolation |
| Landing | `frontend/src/pages/Landing.tsx` | Scope Check in the sample |

## Phase 1: Backend

- [x] **1.1 Prompt.** `eee10db` Scope Check section and rules in `OUTPUT_FORMAT`; batch note; description and rules for the merge. Gate: `ruff check .`, `pytest`.
- [x] **1.2 Context and fallback.** `1886e45` `manifest` on `build_pr_context`, passed from `handle_review`; "Scope Check" in `MERGED_SECTIONS`. Gate: `ruff check .`, `pytest`.
- [~] **1.3 Tests.** Prompt, context, merge, fallback and parser tests. Gate: `ruff check .`, `pytest`.

## Phase 2: Frontend

- [ ] **2.1 Landing sample.** Gate: `npm run lint`, `npm run typecheck`, `npm test`.

## Phase 3: Live verification

- [ ] **3.1 Demo PRs.** From `demo/base`: `demo/scope-match` (description matches) and `demo/scope-extra-change` (undescribed extra change). Open both against `demo/base` and check the posted comments.
