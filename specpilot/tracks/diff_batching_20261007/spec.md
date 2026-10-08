# Batch large PR diffs instead of cutting them

## Overview

Very large PR diffs are either sent whole (which overflows the model context window when `MAX_DIFF_CHARS=0`) or cut
at `MAX_DIFF_CHARS`, so everything past the cap is never reviewed. This track splits the diff into batches sized to
the model's context window (Gemini 3.5 Flash-Lite: 1,048,576 input tokens, 65,536 output tokens), reviews the
batches concurrently, and merges the batch reviews into one review with a single LLM merge call. A diff that fits in
one batch behaves exactly as it does today.

GitHub refuses the `.diff` media type for very large PRs (HTTP 406). That case is not worked around: it fails with a
clear reason on the PR and a clear notice in the UI.

## Functional Requirements

1. **Filter noise.** Before batching, drop files on a fixed default list:
   - lockfiles (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`, `Pipfile.lock`, `Cargo.lock`,
     `go.sum`, `composer.lock`, `Gemfile.lock`);
   - `*.min.js`, `*.min.css`, `*.map`;
   - anything under `vendor/`, `node_modules/`, `dist/` or `build/`;
   - binary-file entries.

   The comment lists these under "Not reviewed (generated or lockfiles)".
2. **Split** at `diff --git` file boundaries, packing whole files until a batch is full. A file larger than the
   budget is split at `@@` hunks with the file header repeated; a hunk larger than the budget is cut on line
   boundaries; a single line larger than the budget is hard-cut.
3. **Batch budget.** Target `DIFF_BATCH_TOKENS` (default 100k tokens, estimated at 3 characters per token). If the
   diff needs more than `MAX_DIFF_BATCHES` (default 50) batches, the budget grows until the diff fits, up to a
   ceiling: `GEMINI_CONTEXT_TOKENS` (default 1,048,576) minus the system prompt, the cached or inline documents,
   `GEMINI_MAX_OUTPUT_TOKENS`, and a 10% safety margin.
4. **Context in every batch:** PR metadata and description, a list of every changed file with +/- counts,
   "Batch i of N", and an instruction to review only this batch.
5. **Concurrency.** Batches run concurrently, limited by `DIFF_BATCH_CONCURRENCY` (default 4), reusing the same
   Gemini docs cache.
6. **Merge.** One LLM call merges the batch reviews into the standard four-section review plus `reviewpilot-meta`,
   removing duplicate findings. Code enforces the verdict: the merged verdict is never better than the worst batch
   verdict, and the score is clamped to that verdict's range. If the merge call fails, the batch findings are joined
   in code and the review is still posted.
7. **One batch means no change.** No merge call; prompt and comment are byte-identical to today.
8. **`MAX_DIFF_CHARS` stays** as an overall cut before batching; `0` still means unlimited.
9. **Partial review.** If any batch can't be reviewed (permanent failure, still failing after its retries, or the
   time limit ran out), the review is still posted with "Reviewed X of Y files. Not reviewed: …" (at most 50 names,
   then "and N more").
10. **Stored results.** `lines_reviewed` counts changed lines in reviewed batches; `diff_truncated=true` whenever
    something was skipped or cut. No new column, no migration, no batch count anywhere.
11. **GitHub's diff size limit (no fallback).** A 406 from `get_pull_diff` raises `DiffTooLargeError(DiffFetchError)`:
    permanent, never retried. Its `user_reason`: "this PR's diff is larger than GitHub allows ReviewPilot to fetch —
    split the PR into smaller ones and comment @review again". The PR gets the existing `error` reply.
12. **Error code on the job.** `ServiceError` gets an optional stable `code` (`diff_too_large`). The job API returns
    `error_code` next to `last_error`.
13. **Limit notices in the UI** (from existing fields, no migration):
    - **Activity:** a failed job with `error_code=diff_too_large` shows an amber notice ("Diff too large for GitHub.
      Not reviewed. Split the PR.") instead of the raw red error; the raw error stays behind "Details".
    - **History rows and the review drawer:** a review with `diff_truncated=true` shows a "Partially reviewed"
      badge. The drawer shows the not-reviewed list from the stored markdown.
    - lucide icons, existing amber/warning tokens, no emojis.

## Non-Functional Requirements

- **No endless retries.** Each batch gets at most 2 attempts for transient errors; after that it counts as skipped
  and the error doesn't escape to the job. The job raises only if every batch fails (normal `JOB_MAX_ATTEMPTS`, then
  the failure comment). Once a partial review is stored, a retry only reposts it and never calls the LLM again.
- **Time limit.** The batch phase has its own deadline (`JOB_TIMEOUT_SECONDS` minus a reserve for merge and
  posting). When it runs out, no new batches start, the rest are listed as not reviewed, and the merge runs on what
  finished. `JOB_TIMEOUT_SECONDS` default goes from 180 to 600.
- Gemini-specific numbers stay inside the config, gemini and reviewer services.
- Every new setting is in `.env.example` with validation.

## Sad Paths & Error States

| Case | Outcome |
| --- | --- |
| One batch blocked by a safety filter | Partial review naming that batch's files |
| Merge call fails | Batch findings joined in code, with a note that the summary was generated automatically |
| Every batch fails | Job error, retried by the worker, then the existing failure comment |
| Documents alone fill the context window | Ceiling ≤ 0: permanent error with a clear reason, no retry loop |
| Only filtered files changed | The `empty_diff` reply plus the list of filtered files |
| GitHub returns 406 for the diff | `DiffTooLargeError`, one attempt, failure comment with the reason, amber notice on Activity |

## Edge Cases

- A minified file not on the list and larger than the ceiling: hard-cut and marked partially reviewed.
- Renames, mode-only changes and deletion-only files are kept.
- `MAX_DIFF_CHARS` plus batching: cut first, then batch.
- Duplicate findings across batches: removed by the merge call.

## Acceptance Criteria

- A diff under one batch: identical request and comment to today; existing tests pass unchanged.
- The ~5 MB e2e tier produces several batch requests plus one merge request, each under the ceiling; all files
  reviewed, `diff_truncated=false`.
- An injected batch failure gives a posted partial review listing the right files; the job finishes in one attempt,
  and a forced retry makes 0 LLM calls.
- An injected time limit leaves the remaining batches listed as not reviewed, and the review is posted.
- A Critical finding in one batch makes the merged verdict Critical even if the merge says "passed".
- Lockfiles and `dist/` never reach the prompt.
- A mocked 406: one attempt, no LLM call, PR comment with the reason, `error_code=diff_too_large` from the API, amber
  notice on Activity (Vitest).
- A partial review shows "Partially reviewed" in History and the drawer (Vitest).

## Out of Scope

- Batching `@bot plan` (keeps its 40k cap).
- Batch count in the UI or database.
- Per-repo filter list.
- Per-batch persistence for retries.
- A real tokenizer.
- Falling back to `/pulls/{n}/files` or any other way around GitHub's limit.
- Showing failed jobs on Dashboard or History.
