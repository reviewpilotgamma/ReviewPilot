# Plan: Batch large PR diffs instead of cutting them

## Context Snapshot

| Kind | Symbols |
| --- | --- |
| Existing | `reviewer.handle_review`, `truncate_diff`, `count_changed_lines`, `assemble_comment`, `_docs_for_prompt`, `build_review_context`; `prompts.build_review_system_prompt`, `build_pr_context`; `review_parser.parse_review`, `SCORE_RANGES`; `gemini.generate`; `errors.DiffFetchError`, `GitHubPermanentError`; `worker.execute_job`, `finish_job`; `schemas/events.JobOut`; `Activity.tsx`, `History.tsx`, `ReviewDrawer.tsx`, `ui/Badge.tsx`; e2e `MockGemini`, `diffs.scenario_for_tier` |
| New | `services/diff_batching.py` (`FileDiff`, `DiffBatch`, `BatchPlan`, `parse_file_diffs`, `is_noise_path`, `NOISE_*`, `split_oversized`, `pack_batches`, `plan_batches`, `token_ceiling_chars`); `prompts.build_batch_context`, `MERGE_SYSTEM_PROMPT`, `build_merge_content`; `reviewer._review_batches`, `_review_one_batch`, `_merge_reviews`, `_fallback_merge`, `enforce_verdict_floor`; `errors.DiffTooLargeError`, `ServiceError.code`, `error_code_for`; settings `DIFF_BATCH_TOKENS`, `MAX_DIFF_BATCHES`, `DIFF_BATCH_CONCURRENCY`, `GEMINI_CONTEXT_TOKENS`; `JobOut.error_code`; `ui/Badge.PartialBadge` |
| Modified | `handle_review` (batching path; single-batch path unchanged), `assemble_comment` (`not_reviewed`, `filtered`), `config.JOB_TIMEOUT_SECONDS` 180→600, `.env.example`, `Activity.tsx`, `History.tsx`, `ReviewDrawer.tsx`, `types/api.ts`, `test_perf_scaling.py` |

### Hotspot map

| Requirement | Files / symbols |
| --- | --- |
| FR1–3 | `backend/app/services/diff_batching.py`, `core/config.py` |
| FR4, FR6 | `backend/app/services/prompts.py` |
| FR5–10, NFR | `backend/app/services/reviewer.py` |
| FR11–12 | `services/errors.py`, `reviewer.handle_review`, `schemas/events.py` |
| FR13 | `frontend/src/types/api.ts`, `pages/Activity.tsx`, `pages/History.tsx`, `components/reviews/ReviewDrawer.tsx`, `components/ui/Badge.tsx` |
| Tests | `tests/test_diff_batching.py` (new), `tests/test_reviewer.py`, `tests/test_worker.py`, `tests/e2e/test_review_flows.py`, `test_resilience_flow.py`, `test_perf_scaling.py`, `frontend/src/pages/pages.test.tsx` |

Coordination: Phase 3 touches `types/api.ts` and `ReviewDrawer.tsx`, which `prompt_recipe_20261007` Phase 3 also
edits. Start Phase 3 only after that work is committed.

## Phase 1 — Splitting the diff (pure code)

- [ ] 1.1 Settings — `core/config.py`, `.env.example`
  - `DIFF_BATCH_TOKENS: int = Field(100_000, ge=1_000)`, `MAX_DIFF_BATCHES: int = Field(50, ge=1, le=200)`,
    `DIFF_BATCH_CONCURRENCY: int = Field(4, ge=1, le=16)`, `GEMINI_CONTEXT_TOKENS: int = Field(1_048_576, ge=8_192)`.
  - `JOB_TIMEOUT_SECONDS` default 180 → 600.
  - `.env.example`: document the new settings; `GEMINI_MODEL=gemini-3.5-flash-lite`; note the model allows up to
    65,536 output tokens.
- [ ] 1.2 `services/diff_batching.py`
  - `CHARS_PER_TOKEN = 3`. `NOISE_FILENAMES`, `NOISE_SUFFIXES = (".min.js", ".min.css", ".map")`,
    `NOISE_DIRS = ("vendor/", "node_modules/", "dist/", "build/")` (match at path start or after `/`).
  - `FileDiff(path, header, hunks, binary)` with `text` and `changed_lines`.
  - `parse_file_diffs(diff)`: split on `diff --git a/… b/…`; header = text before the first `@@`; hunks split on
    `@@`; `Binary files … differ` → `binary=True`; text before the first header is ignored.
  - `split_oversized(file, budget)`: hunk groups with the header repeated; oversized hunk cut by lines with header +
    `@@` line repeated; oversized line hard-cut (file recorded in `cut_files`).
  - `pack_batches(files, budget)`: greedy, in order.
  - `plan_batches(diff, *, target_chars, ceiling_chars, max_batches) -> BatchPlan(batches, filtered, cut_files,
    overflow, budget_chars)`: drop noise/binary; pack at `min(target, ceiling)`; double the budget (capped at the
    ceiling) while over `max_batches`; if still over, keep the first `max_batches` and list the rest in `overflow`.
    `ceiling <= 0` raises `ValueError`.
  - `token_ceiling_chars(*, context_tokens, max_output_tokens, system_chars, docs_chars)`.
- [ ] 1.3 Tests — `tests/test_diff_batching.py`: parsing (multi-file, rename-only, mode-only, deletion, binary,
  preamble); noise paths (nested `src/build/x.py` is noise per the dir rule, `src/builder/x.py` is not); packing
  respects the budget; oversized file split at hunks; oversized hunk/line cut; budget growth to ≤ 50 batches;
  overflow at the ceiling; ceiling ≤ 0 raises; every hunk line of non-noise files appears exactly once.
- [ ] 1.4 Quality gate: `ruff check .`, `pytest`.

## Phase 2 — Review pipeline, merge, and the 406 case

- [ ] 2.1 `errors.py`: `ServiceError.code = None`; `DiffTooLargeError(DiffFetchError)` with `code = "diff_too_large"`
  and the spec's `user_reason`; `error_code_for(last_error)` maps the worker's `"<ClassName>:"` prefix to a code.
- [ ] 2.2 `handle_review` / `handle_plan`: a 406 from `get_pull_diff` raises `DiffTooLargeError`; other permanent
  errors raise `DiffFetchError` as before.
- [ ] 2.3 `prompts.py`: `build_batch_context(...)` (file manifest capped at 500 lines + "Batch i of N");
  `MERGE_SYSTEM_PROMPT`; `build_merge_content(pr, owner, repo, reviews)`.
- [ ] 2.4 `reviewer.py` batching:
  - ceiling from system prompt + docs chars; ceiling ≤ 0 → permanent error, no LLM call.
  - no batches (all filtered) → `empty_diff` + filtered list; one batch with nothing filtered/cut → today's exact
    path; one batch with filtered files → same path with the batch text and the filtered notice; more → batches.
  - `_review_batches`: deadline = start + `JOB_TIMEOUT_SECONDS` − `MERGE_RESERVE_SECONDS` (120); semaphore of
    `DIFF_BATCH_CONCURRENCY`; `_review_one_batch` makes ≤ 2 attempts on `GeminiTransientError` and never raises;
    unfinished batches at the deadline are cancelled and recorded as skipped.
  - all batches failed → raise the first `ServiceError` (worker policy applies).
  - `_merge_reviews` (no docs, no cache) → `parse_review`; on `ServiceError` → `_fallback_merge`.
  - `enforce_verdict_floor`: worst verdict across merge and batches; score clamped to its range.
  - `not_reviewed`, `lines_reviewed`, `diff_truncated` per the spec; save then post (idempotent retries).
- [ ] 2.5 `assemble_comment(..., not_reviewed=(), filtered=())`: partial and filtered notices in `head`, ≤ 50 names.
- [ ] 2.6 `schemas/events.JobOut.error_code` (computed from `last_error`).
- [ ] 2.7 Unit tests — `test_reviewer.py`, `test_worker.py`: single-batch parity; multi-batch + merge; concurrency
  cap; partial on transient and on permanent batch failure; all-fail raises; merge fallback; verdict floor;
  deadline; filtered-only; ceiling ≤ 0; 406 → `DiffTooLargeError`, no LLM call, `error_code` in `/events`.
- [ ] 2.8 E2E — `test_perf_scaling.py` (very large tier batched + merged, all reviewed), `test_resilience_flow.py`
  (batch failure → partial, no requeue), `test_review_flows.py` (406).
- [ ] 2.9 Quality gate: `ruff check .`, `pytest`.

## Phase 3 — Frontend (after prompt_recipe Phase 3 is committed)

- [ ] 3.1 `types/api.ts`: `Job.error_code: "diff_too_large" | null`; confirm `diff_truncated` on list items.
- [ ] 3.2 `ui/Badge.tsx`: `PartialBadge` (amber, lucide icon, "Partially reviewed").
- [ ] 3.3 `Activity.tsx`: amber notice for `diff_too_large`, raw error behind "Details".
- [ ] 3.4 `History.tsx`, `ReviewDrawer.tsx`: `PartialBadge` when `diff_truncated`.
- [ ] 3.5 Tests — `pages.test.tsx`.
- [ ] 3.6 Quality gate: `npm run lint`, `npm run typecheck`, `npm test`.
