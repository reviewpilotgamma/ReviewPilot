# End-to-end pipeline integration and performance testing

## Overview

Add an end-to-end integration suite under `backend/tests/e2e/` that drives every ReviewPilot feature through
its real HTTP entry points: signed webhook → `dispatcher.ingest` → `Job` queue → `Worker.run_once` →
`reviewer` handlers → stored `PRReview` → GitHub comment → dashboard, feedback and metrics APIs.

Inputs are generated dummy git diffs. The suite records per-stage timings and diff-size scaling and writes a
performance report. GitHub is always mocked with respx. Gemini is mocked by default; an opt-in live mode sends
the same dummy diffs to real Gemini to measure real latency and review quality.

No production code changes are planned. Timing comes from test-side wrappers around existing service functions.

## Functional Requirements

1. **Dummy diff generator** (`tests/e2e/diffs.py`) producing deterministic (seeded), valid unified diffs:
   - Size tiers: *small* (~1 file / 20 lines), *medium* (~10 files / 1k lines), *large* (~50 files / ~500 KB),
     *very large* (~5 MB).
   - Planted-issue scenarios with expected outcomes: SQL injection, hardcoded secret/token, outbound HTTP call
     without timeout/retry, breaking API contract change, blocking I/O inside async code, and a *clean* diff
     (expected `passed`).
   - Edge diffs: empty / whitespace-only, binary-file markers, rename-only, unicode / non-UTF-8 content.
   - Every scenario declares an expected verdict floor and the keywords expected in the findings.
2. **E2E harness** (`tests/e2e/conftest.py`):
   - A fake GitHub that registers PRs (metadata + diff) and captures posted comments and reactions.
   - A helper that posts signed webhooks.
   - A worker drain that runs the queue until it is empty (fast-forwarding retry backoff).
   - API helpers that read results back through the dashboard endpoints.
   - A mock Gemini that returns scenario-appropriate markdown with the `reviewpilot-meta` line and records every
     request body.
3. **Feature coverage** — one or more E2E tests each:
   - Auto mode: `pull_request.opened` → review posted, stored, visible in `/reviews`, `/reviews/{id}`,
     `/webhooks/events`.
   - Manual mode: PR opened → welcome comment; `@review <note>` → 👀 reaction, review with requester attribution
     and the note in the system prompt.
   - `@bot plan` → plan comment; permanent Gemini failure → canned plan; a comment containing both `@review` and
     `@bot plan` → two jobs.
   - Repo rules via `PUT /rules/{owner}/{repo}` (custom instructions, verbosity, security on/off, review mode)
     reflected in the outgoing Gemini prompt.
   - Documents: upload below the cache gate → inline injection; above the gate → `cachedContents` create plus
     `cachedContent` on generate; a second review reuses the cache; document change/delete invalidates it.
   - Empty diff → `empty_diff` reply, no review stored. Closed PR → skipped, no comment.
   - `MAX_DIFF_CHARS` truncation → `diff_truncated=true` and a warning in the comment. Over-long LLM output →
     comment truncated to `MAX_COMMENT_CHARS`.
   - Parser fallback: LLM output without the meta line still yields a verdict and score from severities.
   - Feedback: `POST /reviews/{id}/feedback` → `/metrics/summary` and `/metrics/trend` update from real records.
4. **Security and resilience coverage:**
   - Invalid or missing signature → 401, nothing stored.
   - Bot sender → event ignored, no job.
   - Duplicate delivery id → acknowledged once.
   - Transient Gemini 5xx/429 → retried with backoff (clock fast-forwarded), then succeeds.
   - Permanent Gemini error → job `failed`, exactly one failure comment.
   - GitHub comment post fails after the review is saved → retry posts the stored review **without a second LLM
     call**.
   - Diff fetch 404/406 → failure comment.
   - A job stuck in `running` is re-queued by `recover_interrupted_jobs` and completes.
5. **Throughput and concurrency:** a burst of N webhooks (default 25, across several PRs, including repeated
   deliveries for the same PR) on a `Worker` with concurrency > 1. Assert every job ends `succeeded`, there are no
   duplicate reviews/comments per delivery, one PR is never processed by two jobs at once, and record jobs/sec.
6. **Stage timings** per scenario: ingest, claim, GitHub PR fetch, diff fetch, rules/docs load, prompt build,
   LLM, parse, persist, comment post — plus total, diff bytes, changed lines, verdict.
7. **Performance report:** every E2E run writes `backend/e2e-reports/report.json` and `report.md` (gitignored)
   with a scenario table, stage timings, size-scaling table, throughput, and — in live mode — verdict and keyword
   hit rate per planted scenario.
8. **Live mode:** enabled only when `REVIEWPILOT_E2E_LIVE=1` and `REVIEWPILOT_E2E_GEMINI_API_KEY` are set;
   marked `@pytest.mark.live`. Runs planted-issue and size-tier scenarios against real Gemini (GitHub still
   mocked). Asserts the pipeline completes, critical-planted scenarios (secret, SQL injection) do not come back
   `passed`, and the clean diff does not come back `critical`. Keyword hit rate is reported, not asserted.

## Non-Functional Requirements

- The mocked suite runs in plain `pytest`, is deterministic, and makes no network calls (respx enforces this).
  The E2E subset finishes in under ~60 s on a dev laptop.
- Mocked-mode pipeline-overhead budgets (configurable, generous to avoid flakiness): small < 1 s, medium < 2 s,
  large < 5 s, very large < 15 s.
- Live mode is skipped by default and never runs in CI unless explicitly enabled. The live key never comes from
  or goes into `backend/.env` and never appears in reports or logs.
- Code follows `specpilot/code_styleguides/python.md`; `ruff check .` passes.

## Sad Paths & Error States

- Live mode enabled but key missing → live tests skip with a clear reason (no error).
- Live Gemini rate limit / outage → recorded in the report as a failed scenario with the error class; only that
  scenario's test fails.
- Report directory not writable → warning only; tests do not fail.

## Edge Cases

- Very large diff with `MAX_DIFF_CHARS=0` (unlimited) is sent whole; covered alongside the truncation case.
- Unicode / non-UTF-8 diff bytes survive the round trip into the stored review and comment.
- A burst with duplicate deliveries and multiple deliveries for the same PR exercises per-PR serialization via
  the worker's deferral path.
- Live mode excludes the *very large* tier (it exceeds the model context window).

## Acceptance Criteria

- `pytest` from `backend/` runs the full mocked E2E suite green, covering every feature in requirements 3–5, and
  writes `e2e-reports/report.{json,md}`.
- `pytest -m e2e` runs only the E2E suite; `REVIEWPILOT_E2E_LIVE=1 REVIEWPILOT_E2E_GEMINI_API_KEY=… pytest -m live`
  runs the live scenarios and produces a report with real latencies and quality results.
- README documents how to run the E2E suite and live mode.
- `ruff check .` passes.

## Out of Scope

- Browser / Playwright UI tests and frontend changes.
- Live GitHub calls or a real sandbox repository.
- Changing pipeline behavior. Gaps the suite exposes (e.g. the product's "chunk instead of truncate" goal) are
  recorded as follow-up findings, not fixed here.
- Load testing beyond the in-process worker (multi-process, Postgres).
