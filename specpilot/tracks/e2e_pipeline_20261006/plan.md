# Plan: End-to-end pipeline integration and performance testing

## Context Snapshot

| Kind | Symbols |
| --- | --- |
| Existing (driven, not changed) | `POST /api/v1/webhooks/github` (`app/api/webhooks.py::receive`), `dispatcher.ingest`/`plan_jobs`, `worker.Worker.run_once`/`claim_next_job`/`recover_interrupted_jobs`/`BACKOFF_SECONDS`, `reviewer.handle_review`/`handle_plan`/`handle_welcome`/`_load_rules`/`_docs_for_prompt`/`_save_review`/`_post_review`/`parse_review`/`build_review_system_prompt`/`build_pr_context`, `github_app.get_pull`/`get_pull_diff`/`post_issue_comment`/`add_reaction`, `gemini.generate`/`create_cached_content`/`delete_cached_content`, `documents.MIN_CACHE_CHARS`/`ensure_context_cache`, APIs `/reviews`, `/reviews/{id}`, `/reviews/{id}/feedback`, `/metrics/summary`, `/metrics/trend`, `/rules/{owner}/{repo}`, `/rules/{owner}/{repo}/documents`, `/webhooks/events` |
| Existing test infra (reused) | `tests/conftest.py`: `env` (autouse), `db`, `mock_http`, `app`, `client`, `login`, `sign`, `post_webhook`, `GITHUB_API`, `GEMINI_API`, `WEBHOOK_SECRET` |
| New | `tests/e2e/__init__.py`, `tests/e2e/diffs.py` (`DiffScenario`, `generate_diff`, `SIZE_TIERS`, `PLANTED_SCENARIOS`, `EDGE_SCENARIOS`), `tests/e2e/harness.py` (`FakeGitHub`, `MockGemini`, `StageTimer`, `ReportCollector`, `drain_worker`, `fast_forward_jobs`), `tests/e2e/conftest.py` (fixtures `fake_github`, `mock_gemini`, `stage_timer`, `e2e_report`, `live_gemini`; `pytest_sessionfinish` report writer), test modules `test_diffs.py`, `test_review_flows.py`, `test_documents_flow.py`, `test_dashboard_flow.py`, `test_security_flow.py`, `test_resilience_flow.py`, `test_perf_scaling.py`, `test_throughput.py`, `test_live_gemini.py` |
| Modified | `backend/pyproject.toml` (register `e2e`, `live` markers), `.gitignore` (`backend/e2e-reports/`), `README.md` (§3 Test & lint: E2E + live mode) |

### Hotspot map

| Requirement | Files / symbols touched |
| --- | --- |
| FR1 diff generator | `tests/e2e/diffs.py` |
| FR2 harness | `tests/e2e/harness.py`, `tests/e2e/conftest.py`; reuses `tests/conftest.py::post_webhook`, `login` |
| FR3 features | `test_review_flows.py` (dispatcher + reviewer), `test_documents_flow.py` (documents API + `ensure_context_cache`), `test_dashboard_flow.py` (reviews/feedback/metrics/events APIs) |
| FR4 security/resilience | `test_security_flow.py` (`receive`, `is_bot_event`, duplicate ingest), `test_resilience_flow.py` (`execute_job` retry policy, `handle_review` idempotency, `recover_interrupted_jobs`) |
| FR5 throughput | `test_throughput.py` (`Worker.start`/`stop`, `_running_prs` deferral) |
| FR6/FR7 timings + report | `harness.StageTimer` (monkeypatched wrappers on `reviewer.*`, `gh.*`, `gemini.generate`, `worker.claim_next_job`), `harness.ReportCollector`, `conftest.pytest_sessionfinish` |
| FR8 live | `test_live_gemini.py`, `conftest.live_gemini` (respx pass-through for the real Gemini host) |

### Design notes

- **Stage timing without prod changes:** `reviewer` calls `gh.get_pull`, `gemini.generate`, etc. through module
  attributes, and imports `parse_review`, `build_review_system_prompt`, `build_pr_context` by name. `StageTimer`
  wraps each with `monkeypatch.setattr` on the namespace the caller resolves it from (e.g.
  `reviewer.parse_review`, `app.services.github_app.get_pull`). Timings are keyed by job id via a contextvar set
  in a wrapper around `worker.execute_job`.
- **Backoff fast-forward:** after a retry, `fast_forward_jobs(db)` sets `next_run_at = utcnow()` on queued jobs so
  `drain_worker` proceeds without sleeping.
- **Live mode:** `live_gemini` overrides `GEMINI_API_URL` (real default) and `GEMINI_API_KEY` (from
  `REVIEWPILOT_E2E_GEMINI_API_KEY`) via `monkeypatch.setenv` + `reload_settings()`, and adds
  `mock_http.route(host="generativelanguage.googleapis.com").pass_through()`. GitHub routes stay mocked.
- **Concurrency check:** `MockGemini` adds a small async delay (default 20 ms) so jobs overlap. A wrapper on
  `reviewer.HANDLERS["review"]` records active `(repo, pr)` keys and fails if one is entered twice.

## Phase 0 — Environment and baseline [checkpoint: d8ae04b]

- [x] 0.1 Install backend dependencies into `backend/.venv` `f890abf`
  - From `backend/`: `.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt`.
  - Run `pytest -q` and `ruff check .`; record the baseline pass count in the implementation notes below. If any
    pre-existing test fails, stop and report it before continuing.

## Phase 1 — Harness and dummy data [checkpoint: dac6362]

- [x] 1.1 Register markers and ignore reports `da955a0`
  - `backend/pyproject.toml` `[tool.pytest.ini_options]`: add
    `markers = ["e2e: end-to-end pipeline tests", "live: hits real Gemini (opt-in)"]`.
  - `.gitignore`: add `backend/e2e-reports/`.
- [x] 1.2 Dummy diff generator — `tests/e2e/diffs.py` `54bdc4c`
  - `@dataclass(frozen=True) DiffScenario(name, diff, title, body, expected_verdict_floor, expected_keywords,
    mock_review_markdown)`. `expected_verdict_floor` ∈ `passed|warning|critical` (worst verdict acceptable to
    assert in live mode); `mock_review_markdown` is the canned LLM output for mocked mode.
  - `generate_diff(*, files: int, lines_per_file: int, seed: int, lang="py") -> str`: uses
    `random.Random(seed)`; emits `diff --git`, `index`, `---/+++`, valid `@@ -a,b +c,d @@` hunks with correct
    counts, a mix of context/`+`/`-` lines.
  - `SIZE_TIERS = {"small": (1, 20), "medium": (10, 100), "large": (50, ~200 lines × long lines ≈ 500 KB),
    "very_large": (≈ 5 MB)}`; build lazily via `scenario_for_tier(name)`, so a 5 MB string is only created when
    used.
  - `PLANTED_SCENARIOS`: `sql_injection` (f-string SQL in a repository function), `hardcoded_secret`
    (`AWS_SECRET_ACCESS_KEY = "AKIA..."` / `ghp_` token), `no_timeout_retry` (`requests.post` without timeout in a
    loop), `breaking_api` (removed/renamed field in a public Pydantic response model + route path change),
    `blocking_async` (`time.sleep` / sync `requests` inside `async def`), `clean` (small, well-tested change).
    Each has keywords (e.g. `["injection", "parameter"]`) and a mock markdown with the right severity tags and
    `<!-- reviewpilot-meta: {...} -->` line.
  - `EDGE_SCENARIOS`: `empty` (`""`), `whitespace` (`"\n  \n"`), `binary` (`Binary files a/x.png and b/x.png
    differ`), `rename_only` (`similarity index 100%` / `rename from` / `rename to`), `unicode` (emoji, CJK, and a
    U+FFFD replacement char).
- [x] 1.3 Generator self-tests — `tests/e2e/test_diffs.py` `decbabd`
  - Same seed → identical output; different seed → different output.
  - Every generated hunk header's counts match its body lines (parse with a small regex).
  - Tier sizes fall within ±20 % of target; `count_changed_lines` > 0 for non-empty tiers.
  - Each planted scenario's `mock_review_markdown` parses via `parse_review` to its declared verdict.
- [x] 1.4 Harness — `tests/e2e/harness.py` `4701715`
  - `FakeGitHub(mock_http)`:
    - `add_pr(owner, repo, number, scenario, state="open")` registers the token, PR JSON, and diff routes
      (switch on the `Accept` header, as in `tests/test_reviewer.py::github`).
    - Records `comments: list[(repo, pr, body)]` and `reactions`, with an optional injected failure queue per
      route (e.g. `fail_next("comment", 502)`).
  - `MockGemini(mock_http)`:
    - Routes `generateContent`, `cachedContents` POST/DELETE.
    - `requests: list[dict]` (parsed JSON bodies), `responses` queue or a default per-scenario lookup
      (matches the scenario name embedded in the PR title).
    - `fail_next(status)`, `delay_s`, and `cache_created`/`cache_deleted` counters.
  - `StageTimer`: `install(monkeypatch)` wraps the stage functions listed in the Design notes; `record(job_id,
    stage, seconds)`; `summary(job_id) -> dict[str, float]`.
  - `ReportCollector`: `add(scenario, mode, diff_bytes, changed_lines, verdict, stages, total_s, extra)`,
    `add_throughput(...)`, `write(dir) -> (json_path, md_path)` (try/except `OSError` → `warnings.warn`).
  - `async drain_worker(max_iterations=500, worker=None)`: loops `Worker().run_once()`; when it returns `False`,
    calls `fast_forward_jobs` once and retries; stops when no `queued` or `running` jobs remain.
  - `fast_forward_jobs()`: `UPDATE jobs SET next_run_at = utcnow() WHERE status='queued'`.
- [x] 1.5 E2E fixtures — `tests/e2e/conftest.py` `7cfb96d`
  - `pytestmark`-style auto-marking: `pytest_collection_modifyitems` adds `e2e` to every item under `tests/e2e/`.
  - Fixtures: `fake_github`, `mock_gemini`, `stage_timer` (installed by default), session-scoped `e2e_report`
    (one `ReportCollector`), `live_gemini` (skips unless `REVIEWPILOT_E2E_LIVE=1` and the key env var are set).
  - `pytest_sessionfinish`: if the collector has entries, write to `backend/e2e-reports/`.
  - Helper `webhook_pr_opened(client, scenario, number, delivery)` and `webhook_comment(client, body, number,
    delivery, sender="alice", sender_type="User")` that build payloads (based on
    `fixtures/pull_request_opened.json` / `issue_comment_review.json`) and call `post_webhook`.
- [x] 1.6 Quality gate: `ruff check .`, `pytest tests/e2e/test_diffs.py`. `7cfb96d`

## Phase 2 — Feature E2E flows [checkpoint: 189e85e]

- [x] 2.1 Review flows — `tests/e2e/test_review_flows.py` `720bfca`
  - `test_auto_mode_pr_opened_posts_review`: signed `pull_request.opened` (default rules → `auto`) → drain → one
    comment starting with `reviewer.BANNER`, one `PRReview` row with `trigger="auto"`, and the job/event
    `succeeded`/`processed`.
  - `test_on_demand_mode_welcome_then_review_with_note`: `PUT /rules/acme/api` `review_mode=on_demand` (via `login`) →
    PR opened → welcome comment only; `@review focus on retries` → `eyes` reaction, comment contains
    `Requested by @alice`, Gemini system prompt contains `focus on retries`.
  - `test_plan_trigger_posts_plan` / `test_plan_falls_back_to_canned_on_permanent_error` (Gemini 400) /
    `test_review_and_plan_in_one_comment_creates_two_jobs`.
  - `test_rules_reflected_in_prompt`: custom instructions + `verbosity=detailed` + `enable_security=false` →
    assert `VERBOSITY_DIRECTIVES["detailed"]`, `SECURITY_DISABLED_DIRECTIVE`, and the custom text in
    `mock_gemini.requests[-1]["systemInstruction"]`.
  - Parametrized over `PLANTED_SCENARIOS`: stored verdict/score match the mock markdown; the comment contains the
    verdict label.
  - `test_empty_and_whitespace_diff_reply_no_review`, `test_closed_pr_skipped`.
  - `test_truncation_with_max_diff_chars` (`MAX_DIFF_CHARS=2000` via `monkeypatch.setenv` + `reload_settings`)
    → `diff_truncated` true, warning line present, and the Gemini user content contains `DIFF TRUNCATED`.
  - `test_unlimited_sends_full_diff` (large tier, default `0`) → the Gemini user content includes the last line
    of the diff.
  - `test_long_llm_output_truncated_to_comment_limit` (mock 80k-char body) → posted body ≤ `MAX_COMMENT_CHARS`
    and ends with `FOOTER`.
  - `test_parser_fallback_without_meta`.
  - Parametrized over `EDGE_SCENARIOS` (binary, rename_only, unicode): the pipeline completes, and unicode
    survives into the stored `full_markdown` when the mock echoes it.
- [x] 2.2 Documents flow — `tests/e2e/test_documents_flow.py` `8ebdbe4`
  - Small `.md` upload via `POST /rules/acme/api/documents` → review → no `cachedContents` POST; the system prompt
    contains `BEGIN DOCUMENT: arch.md`.
  - Upload ≥ `documents.MIN_CACHE_CHARS` → review → one cache create, and the generate body has `cachedContent`.
    A second review → still one create (reused). Upload a changed doc → one delete and a new create on the next
    review. Delete doc → cache deleted and the next review is inline/none.
  - Cache create returns 500 → falls back to inline and the review still succeeds.
- [x] 2.3 Dashboard flow — `tests/e2e/test_dashboard_flow.py` `2c41f5f`
  - After two reviews (one critical, one passed): `GET /reviews` lists both with correct verdicts; `GET
    /reviews/{id}` returns `full_markdown` equal to the posted comment; `GET /webhooks/events` shows `processed`
    with jobs.
  - `POST /reviews/{id}/feedback` helpful + unhelpful (two users) → `feedback_counts` updated;
    `/metrics/summary` and `/metrics/trend` reflect the reviews and feedback (assert counts derived from DB
    rows, no seed data).
- [x] 2.4 Quality gate: `ruff check .`, `pytest -m e2e`. `2c41f5f`

## Phase 3 — Security and resilience [checkpoint: 75eefa0]

- [x] 3.1 `tests/e2e/test_security_flow.py` `2f0f031`
  - Bad signature, missing signature, and wrong secret → 401; zero `WebhookEvent`/`Job` rows.
  - `sender.type=Bot` and `login` ending `[bot]` on `issue_comment` with `@review` → event `ignored`
    (`bot sender`) and no job.
  - Same delivery id twice → second response `{"status": "duplicate"}`; one review and one comment after drain.
  - Malformed JSON with a valid signature → 400.
  - The posted comment and the report never contain `gemini-key-1234` or the installation token.
- [x] 3.2 `tests/e2e/test_resilience_flow.py` `b7883a2`
  - Gemini 503 then 200 → after the first drain pass the job is `queued` with `last_error`; fast-forward → `succeeded`;
    two generate calls total.
  - Gemini 429 → retried. Gemini 400 → `failed`, exactly one error comment (`render_reply("error")`).
  - Comment POST 502 on first try after save → retry posts the stored markdown; `mock_gemini` generate count == 1.
  - Diff GET 404 → failure comment, job `failed`.
  - Exhausted retries (`JOB_MAX_ATTEMPTS=2`, always 503) → `failed`, one failure comment.
  - Crash recovery: ingest, manually set the job `running`, call `worker.recover_interrupted_jobs()` → drain →
    `succeeded`.
- [x] 3.3 Quality gate: `ruff check .`, `pytest -m e2e`. `b7883a2`

## Phase 4 — Performance [checkpoint: 7b9ae6f]

- [x] 4.1 Size scaling — `tests/e2e/test_perf_scaling.py` `475a865`
  - Parametrize over `SIZE_TIERS`. For each: register the PR, POST the webhook (timed as `ingest`), drain, and
    collect `stage_timer.summary(job_id)`. Add to `e2e_report` with diff bytes, changed lines, and verdict.
  - Assert total pipeline time ≤ budget from `PERF_BUDGETS = {"small": 1, "medium": 2, "large": 5,
    "very_large": 15}`. Budgets can be overridden with the `REVIEWPILOT_E2E_BUDGET_SCALE` float env var for
    slow machines.
  - Extra case: very large with `MAX_DIFF_CHARS=200_000` → record truncated vs. unlimited timings side by side.
- [x] 4.2 Throughput — `tests/e2e/test_throughput.py` `41349e2`
  - Set `WORKER_CONCURRENCY=4`, `mock_gemini.delay_s=0.02`. Create 5 PRs and 25 webhooks: a mix of PR opened and
    `@review`, including several on the same PR and 3 duplicate delivery ids.
  - `await Worker().start()`, poll until no queued/running jobs (timeout 30 s), then `stop()`.
  - Assert all jobs `succeeded`, reviews == unique non-duplicate review jobs, no overlapping `(repo, pr)` in the
    handler wrapper, and duplicates produced no extra jobs. Record jobs/sec and p50/p95 job latency to
    `e2e_report.add_throughput`.
- [x] 4.3 Report writer check: a test (ordered last via file name or an explicit fixture) asserting that `eb5bd00`
  `ReportCollector.write(tmp_path)` produces valid JSON and a Markdown table with one row per recorded scenario.
- [x] 4.4 Quality gate: `ruff check .`, `pytest -m e2e --durations=10`; confirm the E2E subset runs in < 60 s and `eb5bd00`
  `backend/e2e-reports/report.md` is produced.

## Phase 5 — Live mode and docs

- [x] 5.1 Live Gemini — `tests/e2e/test_live_gemini.py` `1b65953`
  - `pytestmark = [pytest.mark.live]`; every test takes the `live_gemini` fixture (skip reason:
    `"set REVIEWPILOT_E2E_LIVE=1 and REVIEWPILOT_E2E_GEMINI_API_KEY to run"`).
  - Parametrize over `PLANTED_SCENARIOS` plus the `small`/`medium`/`large` tiers (no `very_large`). Run the full
    webhook → drain flow with GitHub mocked.
  - Record real stage timings, the verdict, and keyword hit rate (`sum(k in markdown.lower()) / len(keywords)`).
  - Assert: job `succeeded`; `sql_injection`/`hardcoded_secret` verdict ≠ `passed`; `clean` verdict ≠ `critical`.
    On `ServiceError`, record the error class in the report and then fail.
  - Ensure the API key never appears in the report: `ReportCollector` redacts any `extra` value containing the key.
- [~] 5.2 README — §3 Test & lint: add "End-to-end suite" with `pytest -m e2e`, where the report lands, the
  budget-scale env var, and live-mode commands for PowerShell and bash.
- [ ] 5.3 Final quality gate: `ruff check .`, `pytest` (full suite, live auto-skipped), and optionally one live run
  if a key is available. Record any pipeline gaps discovered as follow-up notes below (not fixed in this track).

## Implementation Notes

- **0.1 baseline:** Python 3.13.5 venv; `pytest` 177 passed (~30 s). `ruff check .` had 3 pre-existing errors
  (import order in `reviewer.py` / `tests/test_documents.py`, long line in `documents.py`), fixed lint-only in
  `f890abf`. An unrelated uncommitted edit to `app/api/documents.py` was present in the worktree and left untouched.
- **2.1:** the non-auto review mode is `on_demand` (not `manual`); test renamed accordingly.
- **2.2 bug found & fixed (`88c62b0`, deviation from "no prod changes"):** `RepoContextCache.expires_at` was
  `DateTime(timezone=True)`; SQLite returns it naive, so `ensure_context_cache` raised `TypeError` comparing it
  with aware `now()` and **every review after the first on a cached repo failed permanently**. Switched to
  `UTCDateTime` (same storage, no migration) plus a unit regression test in `tests/test_documents.py`.
- **4.x observed (mocked, dev laptop):** whole pipeline 0.2–0.55 s from small (1.4 KB) to very large (4.9 MB);
  very large spends ~130 ms in `llm` (JSON-encoding a ~5 MB request) and ~180 ms ingesting; truncating to
  200k chars drops it to ~0.28 s. `github_pr_fetch` is ~120–170 ms in every test because each test mints a fresh
  installation token (RSA key load + JWT); production caches the token ~50 min, so it is a cold-start cost.
  Burst: 25 webhooks → 20 jobs, concurrency 4, ~16 jobs/s, 0 overlaps, 4 PRs in parallel; stable over 5 runs.
  E2E subset: 73 tests in ~26 s. `report.md` test lives in `test_report_writer.py` (unit-level, `tmp_path`).
