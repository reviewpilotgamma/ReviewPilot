# ReviewPilot architecture

*Clearance to merge, not comment noise.* Architectural review for every pull request.

| Field | Value |
| --- | --- |
| Status | Pilot-ready prototype. Describes the code on `main` as of 8 October 2026. |
| Companions | [`REQUIREMENTS.md`](REQUIREMENTS.md) (what we must deliver), [`API.md`](API.md) (endpoint reference) |

The first three sections explain why the product exists. The rest describes the system as it runs today.

---

## 1. Problem: engineering knowledge doesn't scale

As teams and codebases grow, critical engineering knowledge stays spread across senior reviewers, architecture
decisions, repository rules and product requirements. Every PR depends on a human reviewer to bring that context
together.

| Gap | What happens |
| --- | --- |
| Consistency | Review quality varies with who reviews the PR and what they remember. |
| Coverage | Seniors spend time catching repetitive issues, while architectural or requirement-level risks can still slip through. |
| Learning | Valuable review feedback stays trapped in individual PRs instead of becoming measurable organizational knowledge. |

> **The real problem:** our engineering knowledge exists, but it isn't consistently applied, measured, or learned
> from at the point where code changes happen.

## 2. Why ReviewPilot

AI-powered PR review is not a new idea. ReviewPilot is not trying to win by being another AI code reviewer. It is
an **internal engineering quality layer** for the people who review large volumes of PRs.

| Advantage | Meaning |
| --- | --- |
| Built around our organization | Hosted internally and tailored to our architecture, engineering standards, business rules and practices. |
| Consistent first-pass review | Every PR goes through the same organization-defined checks before a senior reviewer sees it. |
| Requirements as ground truth | Checks whether the change delivers what the PR description and requirement documents say, not only whether the code looks right. |
| Learns from our reviews | Keeps review history and surfaces recurring mistakes and repeated architectural violations. |
| From reviews to measurable quality | A dashboard shows review volume, verdict mix, health scores and recurring themes. |
| Works alongside existing AI tools | Doesn't replace Copilot, Cursor or human reviewers. It ensures every PR gets a consistent organizational pass. |

> **Our core advantage:** other tools help review a PR. ReviewPilot helps our organization keep improving how PRs
> are reviewed.

## 3. Key strengths

| Strength | What it means for reviewers |
| --- | --- |
| Consistent reviews | Every PR gets the same baseline checks, whoever reviews it. |
| Reduces reviewer workload | Catches repetitive issues before a senior engineer spends time on the PR. |
| Uses our own rules | Reviews follow per-repository instructions, uploaded architecture/requirement documents and an org-wide golden prompt. |
| Checks against requirements | A Scope Check compares the PR description with the diff. |
| Learns from review history | Insights groups findings that keep appearing across PRs. |
| Shows quality trends | The dashboard shows where quality is improving or where problems persist. |
| Built for internal use | Self-hosted; credentials and data stay under the organization's control. |
| Scales senior expertise | One senior engineer's standards become a consistent check across many PRs. |

---

## 4. System context

```
                         ┌──────────────────────────────────────────┐
  Browser ──────────────►│ frontend/  React SPA (Vite build)         │
  (/, /login, /dashboard)│   same origin, /api proxied to backend    │
                         └───────────────┬──────────────────────────┘
                                         │ /api/v1/* (session cookie)
  GitHub App webhooks ──────────────────►│
  POST /api/v1/webhooks/github           ▼
                         ┌──────────────────────────────────────────┐
                         │ backend/  FastAPI (one uvicorn process)   │
                         │   API routers · webhook ingress           │
                         │   in-process DB-backed job worker         │
                         └──────┬─────────────┬──────────────┬──────┘
                                ▼             ▼              ▼
                         GitHub REST     Gemini API      SQLite (WAL)
                         (App JWT +      generateContent  reviewpilot.db
                          installation   + Cached         + backend/.env
                          tokens, user   Contents         + PEM in secrets/
                          OAuth token)
```

| Actor | Role |
| --- | --- |
| GitHub | Sends `pull_request`, `issue_comment` and `installation*` webhooks; hosts PRs and comments. |
| Developer on GitHub | Opens PRs, comments `@review [note]` or `@bot plan`. |
| Dashboard user (`dev` role) | Signs in, links GitHub by installing the App, edits rules and documents, reads history and insights, gives feedback. |
| Admin (`admin` role) | Everything a dev can do, plus Settings, the golden prompt, and every repository the App is installed on. |
| Gemini | Generates reviews, merges batched reviews, plans and insights. Called only from `services/gemini.py`. |

---

## 5. Runtime

| Concern | Current choice |
| --- | --- |
| HTTP | FastAPI, served by **one** uvicorn process (`app.main:app`) |
| Background work | In-process async worker polling the `jobs` table (`services/worker.py`) |
| Outbound HTTP | Shared async `httpx` client (`core/http.py`) |
| Data | SQLite in WAL mode via SQLAlchemy 2; Alembic migrations run on startup |
| Config | `backend/.env` via pydantic-settings (`core/config.py`); admins can edit an allow-list from the UI |
| Sessions | HS256 JWT in an `HttpOnly; SameSite=Lax` cookie (`Secure` in production) |
| Frontend | React 18 + TypeScript + Vite, TanStack Query, Tailwind; built to `frontend/dist` |

Startup (`lifespan`): run migrations → seed the `dev` and `admin` accounts → open the HTTP client → start the
worker. Shutdown stops the worker (10 s grace) and closes the client.

---

## 6. Code map

```
backend/
  app/main.py              App factory, middleware (request id, CORS), error handlers, /health, /webhook alias
  app/api/                 Routers (all under /api/v1): auth, webhooks, rules, documents, prompt,
                           reviews, insights, metrics, github, settings; deps.py = session, CSRF, admin, tenant scope
  app/core/                config, database (engine, WAL, migrations), security (HMAC, JWT, Fernet,
                           masking, scrypt), http client, logging (request/job ids)
  app/models/              SQLAlchemy tables (see §10)
  app/schemas/             Pydantic v2 request/response models
  app/services/
    dispatcher.py          Webhook payload → event row + jobs (one transaction), bot filter, dedupe
    worker.py              Claim, run, retry, recover, per-PR serialization, event status roll-up
    reviewer.py            Job handlers: review, welcome, plan; batching orchestration; comment assembly
    prompts.py             Review/plan/merge prompts, output format (incl. Scope Check), rule presets
    golden_prompt.py       Org-wide editable review prompt with {{slot}} validation
    diff_batching.py       Noise filtering and context-window-sized diff batches
    documents.py           Per-repo document upload, text extraction, Gemini context cache
    gemini.py              generateContent + Cached Contents client
    review_parser.py       Score / verdict / summary extraction from review markdown
    insights.py            On-demand recurring-theme synthesis with rolling snapshots
    metrics.py, reviews.py, rules.py, replies.py, config_store.py
    github_app.py          App JWT, cached installation tokens, PR/diff/comment/reaction REST calls
    github_user.py         OAuth code exchange and user profile (used only to link GitHub)
    access.py              Repositories a user can reach (tenant isolation), 5-minute cache
    accounts.py            Seeded accounts, scrypt passwords, failed-login throttle
  app/data/bot_replies.json  Canned comments: welcome, plan, error, empty_diff
  alembic/versions/        0001 … 0007 migrations
  scripts/                 grant_repo.py (admin grants), import_legacy_db.py (PoC data import)
  tests/                   pytest unit + tests/e2e pipeline suite (GitHub and Gemini mocked)
frontend/src/
  pages/                   Landing, Login, Dashboard, Rules, History, Insights, Activity, Settings, NotFound
  components/              layout (AppShell, Sidebar, Navbar, GithubConnect), onboarding (InstallAppGate),
                           reviews, rules (GoldenPromptPanel, Instructions/Documents dialogs), ui kit
  context/                 Auth, Workspace (selected repo), Toast
  hooks/, services/        TanStack Query hooks; typed API client (sends X-Requested-With)
```

---

## 7. Request surfaces

### Pages (frontend)

| Path | Access | Purpose |
| --- | --- | --- |
| `/` | Public | Landing page with a sample review comment |
| `/login` | Public | Username/password sign-in |
| `/dashboard` | Signed in | KPIs (reviews, avg health, pass rate, lines reviewed), trend, recent reviews; Install-App gate when no repository is reachable |
| `/rules` | Signed in | Golden prompt (edit: admin) and per-repo instructions, verbosity, mode, security, documents |
| `/history` | Signed in | Filterable review list; drawer with full review, "Reviewed with" context, feedback |
| `/insights` | Signed in | Recurring themes per repository, refreshed on demand |
| `/activity` | Signed in | Webhook events and their jobs, polled; bot events hidden unless toggled |
| `/settings` | Signed in (edit: admin) | GitHub App and Gemini settings, connection tests, canned replies |

### Backend

All application routes live under `/api/v1`. See [`API.md`](API.md) for the full table. Outside the prefix:
`GET /health` (`{status, db, worker}`), `POST /webhook` (legacy alias of the webhook route) and `GET /docs` (OpenAPI,
disabled when `ENV=production`).

---

## 8. Webhook → job → review pipeline

### 8.1 Ingress (`api/webhooks.py`, `services/dispatcher.py`)

1. Read the raw body and verify `X-Hub-Signature-256` (HMAC-SHA256, constant-time). An empty secret rejects every
   delivery. Invalid → **401**.
2. Parse JSON, then record a `webhook_events` row and any `jobs` rows **in one transaction**. A repeated
   `X-GitHub-Delivery` is acknowledged as `duplicate` and not processed again.
3. Respond `200 {"status": "ok", "jobs": n}` immediately.

| Event | Condition | Result |
| --- | --- | --- |
| any | Sender or commenter is a bot (`type == Bot` or login ends `[bot]`) | Event `ignored` with reason `bot sender`; hidden from Activity by default |
| `ping` | — | `processed` |
| `installation`, `installation_repositories` | — | `processed`; repository-access cache cleared |
| `pull_request.opened` | Repo rule `review_mode = auto` (the default) | `review` job, trigger `auto` |
| `pull_request.opened` | `review_mode = on_demand` | `welcome` job (explains `@review`) |
| `issue_comment.created` on a PR | Body contains `@review [note]` | `review` job, trigger `comment`, note ≤ 500 chars |
| `issue_comment.created` on a PR | Body contains `@bot plan` | `plan` job (both jobs if both triggers are present) |
| `issue_comment.created` on an issue | — | `ignored` (`not a pull request`) |
| anything else | — | `ignored` |

### 8.2 Worker (`services/worker.py`)

- `WORKER_CONCURRENCY` loops (default 2) poll every `WORKER_POLL_INTERVAL_SECONDS`.
- A job is claimed with one atomic `UPDATE … WHERE status='queued' RETURNING`, so it never runs twice.
- Jobs for a PR that is already being processed are deferred 5 s (per-PR serialization).
- Each run is bounded by `JOB_TIMEOUT_SECONDS` (default 600).
- Retryable failures (timeouts, 5xx, rate limits) back off 30 s / 2 min / 10 min, honoring `retry-after`, up to
  `JOB_MAX_ATTEMPTS` (default 3). Permanent failures post the polite `error` comment with a safe reason.
- On startup, jobs left `running` by a crash are re-queued.
- The event's status rolls up from its jobs: `queued` → `processed` or `failed` (with the first error).

### 8.3 Review job (`services/reviewer.py`)

1. **Idempotent retry.** If the job already saved a review, only re-post it; the LLM is never called twice.
2. Add an 👀 reaction to the triggering comment (first attempt only).
3. Fetch the PR; skip if it is closed. Fetch the unified diff; post `empty_diff` if there is nothing to review.
4. Optional hard cap `MAX_DIFF_CHARS` (default `0` = no cap).
5. Load the repo rules, the effective golden prompt, and the repo's documents (Gemini cache name or inline text).
6. Build the system prompt: golden prompt with `{{custom_instructions}}`, `{{verbosity_directive}}`,
   `{{security_directive}}`, `{{requester_note}}` filled in.
7. **Plan batches** (`diff_batching.py`): drop noise (lockfiles, `.min.js`, `.map`, `vendor/`, `node_modules/`,
   `dist/`, `build/`), split per file, pack into batches of about `DIFF_BATCH_TOKENS` (default 100 000 tokens),
   capped by the context window `GEMINI_CONTEXT_TOKENS`. Above `MAX_DIFF_BATCHES` the batch size grows instead of
   dropping files.
8. **One batch:** a single Gemini call with the PR title, description, changed-file list and diff.
   **Several batches:** review up to `DIFF_BATCH_CONCURRENCY` batches at once (2 attempts each), then one merge
   call. If the merge fails, sections are joined in code. The merged verdict is never better than the worst batch.
9. Parse the score and verdict from the trailing `<!-- reviewpilot-meta: {...} -->` line, with severity-count
   fallbacks and a consistency guard (a Critical finding forces `critical`, score < 5).
10. Assemble the comment (§8.5), **save the `pr_reviews` row first**, then post it and store the GitHub comment id.

`welcome` posts the canned reply. `plan` asks Gemini for a ≤ 12-item pre-merge checklist (diff capped at 40 000
chars) and falls back to the canned `plan` reply on a permanent model error. Plans are not stored.

### 8.4 Review output format (`prompts.py`)

Every review has these sections, as bullet lists:

| Section | Content |
| --- | --- |
| Executive Summary | What it does, overall risk, main concern |
| Scope Check | Does the diff match the PR description? Unexpected changes; described but not found. Informational only: never changes the verdict. |
| Architectural Findings | `**Critical**` / `**Warning**` / `**Passed**` · title, with File(s), Problem, Impact |
| Specific Recommendations | Numbered actions naming the file to change |
| What Looks Solid | Good choices, with files |

Verdict → score ranges: `critical` < 5.0, `warning` 5.0–7.9, `passed` ≥ 8.0.

### 8.5 Posted comment

```
## ReviewPilot Architectural Audit

**Verdict:** 🟡 Warning  ·  **Health score:** 6.5/10  ·  **Lines reviewed:** 412
_Requested by @alice: "focus on auth boundaries"_        (comment trigger only)
> notes on partial reviews, split files, skipped generated files (when they apply)

<review sections>

---
_Triggered via ReviewPilot · Architecture Gatekeeper_
```

The comment is cut to `MAX_COMMENT_CHARS` (default 65 000) on a line boundary if needed. The stored
`full_markdown` is exactly what was posted. `review_context` stores what the review used (prompt source, rule
values, document **filenames** and cache mode) and is shown as "Reviewed with" in History.

### 8.6 Grounding documents (`services/documents.py`)

- Per repository: up to 20 files of `.txt`, `.md`, `.markdown`, `.rst` or `.pdf` (text extracted with `pypdf`),
  5 MB each.
- If the combined text is at least 80 000 characters, it is uploaded once as a **Gemini Cached Content** (TTL
  `GEMINI_CACHE_TTL_SECONDS`, default 24 h). The cache is rebuilt on upload/delete, and lazily on the next review
  if that failed. Smaller packs are injected inline into each request.
- Documents are injected whole. There is no semantic search over them.

### 8.7 Insights (`services/insights.py`)

On request (`POST /insights/analyze`), up to 50 reviews newer than the last snapshot are sent to Gemini as compact
cards (findings excerpts and severity counts) along with the previous snapshot. The model returns recurring
themes, "new this period" and "still showing". The result is stored as a new `review_insight_snapshots` row.
`rebuild` starts again from scratch.

---

## 9. Authentication, roles and tenant isolation

| Topic | Behavior |
| --- | --- |
| Sign-in | `POST /auth/login` with a seeded username/password. Passwords are hashed with `hashlib.scrypt`. 5 failures in 5 minutes per username → 429. |
| Accounts | `dev` and `admin`, created or updated on every startup from `SEED_*` settings. Outside production, empty passwords default to `dev12345` / `admin12345`. In production, an account without a password is not created. |
| Linking GitHub | `GET /auth/github/connect` sends the user to install the App (or to OAuth authorize). The callback checks `state` against a cookie, exchanges the code, and stores the user token **Fernet-encrypted**. |
| Admin | Sees every repository of every App installation using the App's own credentials; no GitHub link needed. Only admins can write Settings, canned replies and the golden prompt. |
| Dev | Sees the repositories their linked GitHub identity can reach through the App, plus repositories an admin granted with `scripts/grant_repo.py` (only while the App is installed there). |
| Scope | Every data endpoint filters by the accessible set. Other repositories return **404**, not 403. The set is cached 5 minutes and cleared on installation webhooks. |
| CSRF | `SameSite=Lax` cookie plus a required `X-Requested-With: ReviewPilot` header on every mutating request. |

---

## 10. Data model (SQLite)

| Table | Key columns | Notes |
| --- | --- | --- |
| `users` | `username`, `role` (`dev`/`admin`), `password_hash`, `github_id`, `github_login`, `access_token` (encrypted) | `access_token = ""` means GitHub is not linked |
| `repo_grants` | (`user_id`, `repo_full_name`) | Admin-granted access |
| `repo_rules` | `repo_full_name` (PK), `custom_instructions`, `verbosity` (`concise`/`detailed`), `review_mode` (`auto`/`on_demand`), `enable_security` | Missing row = defaults |
| `repo_documents` | `repo_full_name`, `filename` (unique per repo), `sha256`, `extracted_text` | Grounding documents |
| `repo_context_caches` | `repo_full_name` (PK), `cache_name`, `content_hash`, `model`, `expires_at` | Gemini cache handle per repo |
| `review_prompt` | single row: `template`, `updated_by` | Golden prompt override; no row = built-in default |
| `webhook_events` | `delivery_id` (unique), `event`, `action`, `repo`, `sender`, `payload_preview`, `status`, `error_message` | Activity log |
| `jobs` | `event_id`, `kind` (`review`/`welcome`/`plan`), `payload`, `status`, `attempts`, `next_run_at`, `last_error`, `review_id` | Durable queue |
| `pr_reviews` | `repo_full_name`, `pr_number`, `pr_title`, `author`, `summary`, `full_markdown`, `verdict`, `score`, `lines_reviewed`, `trigger`, `requester`, `github_comment_id`, `diff_truncated`, `model`, `review_context` | Every posted review |
| `review_feedback` | (`review_id`, `user_id`) unique, `rating` (`helpful`/`unhelpful`), `notes` | One rating per user per review |
| `review_insight_snapshots` | `repo_full_name`, `through_review_id`, `themes_json`, `summary_markdown`, … | Rolling insight snapshots |

There is no demo seed data. Everything on the dashboard comes from live reviews (or an imported PoC database).

---

## 11. Configuration (`backend/.env`)

| Group | Settings (code default) |
| --- | --- |
| Runtime | `ENV` (`development`), `API_BASE_URL`, `FRONTEND_ORIGIN`, `DATABASE_URL` (`backend/reviewpilot.db`), `LOG_LEVEL` |
| GitHub App | `GITHUB_APP_ID`, `GITHUB_APP_SLUG` (looked up from GitHub when empty), `GITHUB_WEBHOOK_SECRET`, `GITHUB_PRIVATE_KEY_PATH` (`./secrets/reviewpilot.private-key.pem`), `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_API_URL` |
| Gemini | `GEMINI_API_KEY`, `GEMINI_MODEL` (code `gemini-2.0-flash`; `.env.example` uses `gemini-3.5-flash-lite`), `GEMINI_TEMPERATURE` (0.2), `GEMINI_MAX_OUTPUT_TOKENS` (8192), `GEMINI_CONTEXT_TOKENS` (1 048 576), `GEMINI_CACHE_TTL_SECONDS` (86 400) |
| Auth | `SESSION_SECRET` (≥ 32 chars in production), `SESSION_TTL_HOURS` (8), `TOKEN_ENCRYPTION_KEY` (required in production), `SEED_DEV_USERNAME`/`PASSWORD`, `SEED_ADMIN_USERNAME`/`PASSWORD` |
| Review engine | `MAX_DIFF_CHARS` (0 = no cap), `DIFF_BATCH_TOKENS` (100 000), `MAX_DIFF_BATCHES` (50), `DIFF_BATCH_CONCURRENCY` (4), `MAX_COMMENT_CHARS` (65 000), `INSTALLATION_TOKEN_TTL_SECONDS` (3000) |
| Worker | `WORKER_ENABLED` (true), `WORKER_CONCURRENCY` (2), `WORKER_POLL_INTERVAL_SECONDS` (1.0), `JOB_MAX_ATTEMPTS` (3), `JOB_TIMEOUT_SECONDS` (600) |

Admins can edit the GitHub App fields, `GEMINI_API_KEY` and `GEMINI_MODEL` from Settings; the values are written
back to `backend/.env`. Real environment variables take precedence over `.env`.

---

## 12. Deployment

- Run exactly **one** uvicorn process. The worker, access cache, login throttle and per-PR serialization are
  in-process. Job claiming is atomic, but caches are not shared.
- Serve `frontend/dist` on the same origin as the API and route `/api` to the backend, so the session cookie stays
  first-party. Use HTTPS and `ENV=production`.
- Back up with `sqlite3 reviewpilot.db ".backup backup.db"`, not by copying files (WAL mode).

---

## 13. Remaining gaps

| Gap | Effect | Direction |
| --- | --- | --- |
| Single process | No horizontal scaling; caches and throttle are per process | Move jobs to a shared queue, caches to a shared store |
| SQLite | Fine for one pilot service, not for many teams | Postgres via SQLAlchemy (SQL kept portable) |
| Secrets in `.env` and on disk, writable from the UI by admins | Operational risk on a shared host | Secret store; read-only config in production |
| Seeded accounts only | No SSO; two shared roles | Org SSO, per-user accounts |
| Gemini only | One external model processor | The model sits behind `services/gemini.py` and can be swapped |
| Documents injected whole | Large packs cost tokens; no retrieval | Semantic search / retrieval over documents |
| No re-review on push | `pull_request.synchronize` is not handled | Opt-in re-review per repo |
