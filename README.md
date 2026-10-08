# ReviewPilot

AI-powered GitHub App that acts as an automated senior software architect in pull-request review loops.
It reviews architecture (module boundaries, async lifecycles, API contracts, failure modes, security boundaries)
against team-defined rules written in plain English, and posts the audit directly on the PR.

```
backend/   FastAPI · SQLAlchemy 2 (SQLite, WAL) · Alembic · Pydantic v2 · httpx
frontend/  React 18 · Vite · TypeScript · TanStack Query · Tailwind CSS
```

Local pilot data lives in `backend/reviewpilot.db` (SQLite).

See [`implementation.md`](implementation.md) for the full design. The source brief is [`Application-Prompt.md`](Application-Prompt.md).

## How it works

1. GitHub delivers a webhook. The backend verifies `X-Hub-Signature-256` over the raw body, drops bot events,
   dedupes by `X-GitHub-Delivery`, and stores the event plus its **jobs** in SQLite in a single transaction. It
   responds `200` immediately.
2. An in-process, DB-backed **worker** claims jobs atomically. It retries transient failures (30 s / 2 min / 10 min,
   honoring `retry-after`), re-queues jobs interrupted by a restart, and never runs two reviews of the same PR at once.
3. A **review** job fetches PR metadata and the unified diff, truncates the diff at 120 000 chars, and injects the
   repository's rules (custom instructions, verbosity, security mode) and the `@review <note>` into the Gemini
   prompt. It then parses the score and verdict, **saves the review before posting**, and posts the banner-wrapped
   comment. A retry never calls the LLM twice.
4. If a job fails for good, a polite comment is posted to the PR with a safe reason, and the failure appears in the
   Activity log.

| PR trigger | Behaviour |
|---|---|
| PR opened, repo in `auto` mode | Full architectural review |
| PR opened, repo in `on_demand` mode | Welcome comment explaining `@review` |
| Comment `@review [focus note]` | Review with the note injected (any mode) |
| Comment `@bot plan` | Pre-merge execution checklist (canned fallback if the model is unavailable) |

## 1. Register the GitHub App

GitHub → Settings → Developer settings → GitHub Apps → **New GitHub App**:

- **Webhook URL**: `{API_BASE_URL}/api/v1/webhooks/github`. For local development, use a tunnel such as
  [smee.io](https://smee.io) or `ngrok http 8000`. The legacy `/webhook` path is also accepted.
- **Webhook secret**: a random string. Use the same value for `GITHUB_WEBHOOK_SECRET`.
- **Repository permissions**:
  - Pull requests: *Read & write*
  - Issues: *Read & write* (comments and reactions)
  - Contents: *Read-only*
  - Metadata: *Read-only*
- **Subscribe to events**: *Pull request*, *Issue comment*.
- **Callback URL** (Identifying and authorizing users): `{API_BASE_URL}/api/v1/auth/callback`.
- Turn on **Request user authorization (OAuth) during installation**. Installing the App from ReviewPilot's
  navbar then links the signed-in user's GitHub account in one step. Without it, ReviewPilot runs a separate
  authorize step after the install.
- Generate a **private key** and save it as `backend/secrets/reviewpilot.private-key.pem`.
- Copy the App ID, slug, Client ID and Client secret into `backend/.env`.

## 2. Run locally

Prerequisites: Python 3.11+ and Node 20+.

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                 # then fill in the values (see comments in the file)
uvicorn app.main:app --reload --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                          # http://localhost:5173 (proxies /api to :8000)
```

Database migrations run automatically on startup (`alembic upgrade head`). API docs are at
http://localhost:8000/docs (disabled when `ENV=production`).

Required secrets for production:

```bash
python -c "import secrets;print(secrets.token_urlsafe(48))"                               # SESSION_SECRET
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"  # TOKEN_ENCRYPTION_KEY
```

In development, these fall back to ephemeral values, so sessions reset when the server restarts.

### Signing in

Users sign in at `/login` with one of two accounts that are seeded on startup from `backend/.env`:

| Role | Settings | Development default |
| --- | --- | --- |
| `dev` | `SEED_DEV_USERNAME` / `SEED_DEV_PASSWORD` | `dev` / `dev12345` |
| `admin` | `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD` | `admin` / `admin12345` |

Only `admin` can edit Settings and the golden prompt. `admin` also sees every repository the GitHub App is
installed on, using the App's own credentials, so no GitHub account needs to be connected. In production, set both passwords. An account without
a password is not created, and changing a password in `.env` takes effect on the next restart.

After the first sign-in the dashboard asks the user to **Install GitHub App** (also in the navbar). The install
links that user's GitHub account, and from then on they see the repositories their GitHub account can reach
through the App. If the App is already installed, use **Already installed? Connect GitHub**.

An admin can also grant a user repositories the App is already installed on, without that user connecting
GitHub:

```bash
cd backend
python -m scripts.grant_repo dev reviewpilotgamma/reviewpilot   # add --revoke to remove, --list to show
```

> Settings saved from the UI are written to `backend/.env`. Real environment variables take precedence over
> `.env`, so don't also set those keys in the process environment if you want to manage them from the UI.

## 3. Test & lint

```bash
cd backend
pytest -q --cov=app                  # ~250 tests incl. E2E, ~94 % coverage
ruff check . && ruff format --check .

cd frontend
npm test                             # Vitest + Testing Library
npm run typecheck && npm run lint && npm run build
```

### End-to-end pipeline suite

`backend/tests/e2e/` drives every feature through the real entry points: signed webhook → job queue → worker →
review → GitHub comment → dashboard, feedback and metrics APIs. It uses generated dummy diffs (size tiers from
~1 KB to ~5 MB, planted issues such as SQL injection or a hardcoded secret, and edge cases). GitHub and Gemini are
mocked, so it is deterministic and offline, and it runs as part of plain `pytest`.

```bash
cd backend
pytest -m e2e --durations=10         # E2E only (~30 s)
```

Every run writes `backend/e2e-reports/report.md` and `report.json` (gitignored). They hold per-stage timings
(ingest, claim, PR/diff fetch, rules/docs load, prompt build, LLM, parse, persist, comment post), the size-scaling
table and burst throughput. Perf budgets are asserted. On a slow machine, scale them with
`REVIEWPILOT_E2E_BUDGET_SCALE=2`.

**Live mode (opt-in).** This sends the same dummy diffs to the real Gemini API to measure real latency and
review quality; GitHub stays mocked. It's skipped unless enabled, and the key never goes into `backend/.env` or
the report.

```powershell
# PowerShell
$env:REVIEWPILOT_E2E_LIVE = "1"; $env:REVIEWPILOT_E2E_GEMINI_API_KEY = "<key>"
pytest -m live                       # optional: $env:REVIEWPILOT_E2E_GEMINI_MODEL = "gemini-2.5-flash"
```

```bash
# bash
REVIEWPILOT_E2E_LIVE=1 REVIEWPILOT_E2E_GEMINI_API_KEY=<key> pytest -m live
```

Live mode fails if a review job fails, if the SQL-injection or hardcoded-secret diffs come back `passed`, or if
the clean diff comes back `critical`. Keyword hit rates are reported but not asserted.

## Migrating PoC data (optional)

```bash
cd backend
python -m scripts.import_legacy_db --src path/to/old/reviewpilot.db --dry-run
python -m scripts.import_legacy_db --src path/to/old/reviewpilot.db
```

## Deployment notes

- Run **one** uvicorn worker process. The job worker runs in-process, and its caches and per-PR serialization assume
  a single process. Job claiming itself is atomic.
- Serve `frontend/dist` behind the same origin as the API, routing `/api` to the backend, so the `HttpOnly` session
  cookie stays first-party. Set `ENV=production` and use HTTPS (cookies become `Secure`).
- Back up SQLite with `sqlite3 reviewpilot.db ".backup backup.db"`. Don't copy the files while the server is running,
  because the database uses WAL mode.

## Security summary

- The HMAC is verified over the raw body before parsing, with a constant-time compare. An empty secret rejects
  every webhook.
- OAuth `state` is checked against a cookie. Post-login redirects only allow relative paths.
- User GitHub tokens are encrypted at rest with Fernet. Sessions are HS256 JWTs in `HttpOnly; SameSite=Lax` cookies.
- Mutating endpoints require an `X-Requested-With: ReviewPilot` header as a second CSRF layer.
- Tenant isolation: every data endpoint is filtered to the repositories the user can reach through their GitHub App
  installations. Other repositories return 404.
- Secrets are always masked in API responses. Settings writes are admin-only, limited to an allowlist of keys,
  and reject newlines.
- The LLM prompt treats the diff and PR description as untrusted data. The frontend renders review markdown
  without raw HTML.
