# ReviewPilot

AI-powered GitHub App that acts as an automated senior software architect in pull-request review loops.
It reviews architecture (module boundaries, async lifecycles, API contracts, failure modes, security boundaries)
against team-defined rules written in plain English, and posts the audit directly on the PR.

```
backend/   FastAPI · SQLAlchemy 2 (SQLite, WAL) · Alembic · Pydantic v2 · httpx
frontend/  React 18 · Vite · TypeScript · TanStack Query · Tailwind CSS
```

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
`ADMIN_GITHUB_LOGINS` (comma-separated) controls who can edit Settings.

> Settings saved from the UI are written to `backend/.env`. Real environment variables take precedence over
> `.env`, so don't also set those keys in the process environment if you want to manage them from the UI.

## 3. Test & lint

```bash
cd backend
pytest -q --cov=app                  # 170 tests, ~95 % coverage
ruff check . && ruff format --check .

cd frontend
npm test                             # Vitest + Testing Library
npm run typecheck && npm run lint && npm run build
```

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
