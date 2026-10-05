# ReviewPilot architecture

PoC-stage product, designed as a **single self-hosted service**: one FastAPI process that receives GitHub webhooks, talks to GitHub and Gemini, stores workspace data, and serves a small web UI.

This document describes **what exists now**, not a target platform.

---

## What it is

ReviewPilot is a GitHub App companion:

1. GitHub sends events to this host.
2. The service authenticates as the App, posts comments, and (on `@review`) runs an architectural review via Gemini.
3. A dashboard shows settings, webhook activity, per-repo rules, review history, and pitch-demo metrics.

It is **not** multi-tenant, queued, or auth-gated yet. Treat the process as one workspace on one machine.

---

## System context

```
                    ┌─────────────┐
  Browser ─────────►│  ReviewPilot │◄──── GitHub App webhooks
  (landing + /app)  │  FastAPI     │      (POST /webhook)
                    │  :8000       │
                    └──────┬───────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
     GitHub REST      Gemini generate     Local files
     (App JWT +       Content API         SQLite, .env,
      installation                        PEM, bot_replies.json
      tokens)
```

**Actors**

| Actor | Role |
| --- | --- |
| GitHub | Delivers `issue_comment` / `pull_request` webhooks; hosts PRs and comments |
| Operator / demo user | Uses `/` and `/app`; no login |
| Gemini | Generates review markdown from the PR diff |
| This process | HMAC verify, App auth, review, persistence, static UI |

---

## Runtime

One Uvicorn worker serving `main:app`.

| Concern | Current choice |
| --- | --- |
| HTTP | FastAPI |
| Webhook work | FastAPI `BackgroundTasks` (same process, after `200`) |
| GitHub / Gemini HTTP | synchronous `requests` |
| Config | `.env` + `bot_replies.json` + PEM on disk |
| Data | SQLite `reviewpilot.db` (WAL) |
| Events feed | in-memory `deque` (max 30), lost on restart |
| Auth on `/api/*` | none |

Intended service shape later: keep this as the **control plane + webhook ingress**; extract review work to a job worker and replace file/SQLite config with a real store. Do not split those layers until persistence and jobs exist.

---

## Code map

```
ReviewPilot/
  main.py            HTTP app: webhooks, APIs, static routes
  auth.py            GitHub App JWT + installation tokens + GitHub reads
  reviewer.py        PR diff + Gemini architectural review
  db.py              SQLite schema, seed data, queries
  config_store.py    .env upsert, replies JSON, settings snapshot
  bot_replies.json   Canned comment templates
  static/            Landing + dashboard (HTML/CSS/JS)
  sources/           Pitch HTML / deck (served at /pitch)
```

| Module | Responsibility |
| --- | --- |
| `main.py` | Signature check, event dispatch, REST, pages, in-memory event log |
| `auth.py` | RS256 App JWT (`GITHUB_APP_ID` + PEM); installation token; list app / installs / repos / open PRs |
| `reviewer.py` | Fetch PR meta + unified diff (truncated); Gemini prompt; wrap markdown comment |
| `db.py` | `repo_rules`, `pr_reviews`, `review_feedback`; demo seed if empty |
| `config_store.py` | Resolve PEM path; rewrite `.env`; load/save replies; mask secrets in settings |

`db.save_pr_review()` exists but **is not called** from the webhook/review path. Live `@review` comments are not written to SQLite.

---

## Request surfaces

### Pages

| Path | File |
| --- | --- |
| `GET /` | `static/index.html` (marketing + install status) |
| `GET /app` | `static/app.html` (Alpine dashboard) |
| `GET /pitch` | `sources/pitch.html` |
| `GET /assets/*` | `static/` via `StaticFiles` |
| `GET /health` | JSON liveness |

Landing (`landing.js`) and dashboard (`app.js`) both call `GET /api/github/app` to set the GitHub App install URL.

### Operator APIs (unauthenticated)

| Method | Path | Notes |
| --- | --- | --- |
| GET/PUT | `/api/settings` | Snapshot / write `.env` + replies |
| POST | `/api/settings/private-key` | Upload PEM |
| GET | `/api/events` | Last 30 webhook headers (memory) |
| GET | `/api/github/app` | App profile + `install_url` |
| GET | `/api/github/installations` | App installations |
| GET | `/api/github/installations/{id}/repos` | Repos for an installation |
| GET | `/api/github/installations/{id}/repos/{owner}/{repo}/pulls` | Open PRs |
| POST | `/api/github/comment` | Post issue/PR comment via installation token |
| GET | `/api/rules` | All repo rules |
| GET/POST | `/api/rules/{owner}/{repo}` | Get / upsert one rule |
| GET | `/api/reviews` | Optional `?repo=` |
| GET | `/api/reviews/{id}` | One stored review |
| POST | `/api/reviews/{id}/feedback` | Rating + notes |
| GET | `/api/metrics` | Aggregates from SQLite (incl. demo seed) |

The dashboard UI currently uses: GitHub app, metrics, rules, reviews, events, settings **read**, rule save, review feedback. It does **not** call installations/repos/pulls/comment, settings PUT, or PEM upload.

### Ingress

`POST /webhook`

1. Read raw body; HMAC-SHA256 vs `GITHUB_WEBHOOK_SECRET` (`X-Hub-Signature-256`).
2. Require `X-GitHub-Event`; parse JSON.
3. Append a short event record to memory.
4. Return `{"status":"ok"}` and process in a background task.

---

## Webhook behavior

Ignore events from bots (`sender.type`, comment user type, or login ending `[bot]`).

Requires `installation.id` to mint an installation token.

| Event | Action | Behavior |
| --- | --- | --- |
| `issue_comment` | `created` | If body contains `@review` (case-insensitive): only on PRs; Gemini review posted as a comment. Else if body contains `@bot plan`: post `bot_plan_reply`. |
| `pull_request` | `opened` | Post `pr_opened_reply`. |
| other | — | Log and drop. |

`repo_rules` (`verbosity`, `review_mode`, `enable_security`, custom instructions) are stored and editable in the UI; **the reviewer does not read them**. Extra text after `@review` is passed to Gemini as `requester_note`.

---

## Data

SQLite file: `reviewpilot.db` next to the app. `init_db()` on import; empty `pr_reviews` → seed fictional `acme/*` rules, reviews, and feedback (pitch/demo).

```
repo_rules          1:1 per repo_full_name (instructions + flags)
pr_reviews          historical reviews (demo + future live writes)
review_feedback     N:1 on pr_reviews
```

**Files (not in SQLite)**

- `.env` — App ID, webhook secret, PEM path, Gemini key/model
- PEM — GitHub App private key
- `bot_replies.json` — canned comments

---

## UI

CDN: Alpine.js, Lucide, Marked (dashboard). No frontend build.

| Surface | JS | Role |
| --- | --- | --- |
| `/` | `landing.js`, `home-motion.js` | Install URL + motion |
| `/app` | `app.js` | Tabs: overview, rules, history, activity, settings |

Dashboard is labeled as a demo workspace; metrics/history are primarily seed data until live reviews are persisted.

---

## Configuration

From `.env.example`:

| Variable | Used for |
| --- | --- |
| `GITHUB_APP_ID` | App JWT `iss` |
| `GITHUB_WEBHOOK_SECRET` | Webhook HMAC |
| `GITHUB_PRIVATE_KEY_PATH` | PEM (relative to repo root if not absolute) |
| `GEMINI_API_KEY` | Review generation |
| `GEMINI_MODEL` | Default `gemini-2.0-flash` |
| `GITHUB_APP_SLUG` | In example only; live install URL comes from GitHub `/app` |

---

## Auth to GitHub (not user auth)

1. Sign JWT (RS256, ~10 min) with App ID + private key.
2. `POST /app/installations/{id}/access_tokens` for repo-scoped work.
3. Call REST with `X-GitHub-Api-Version: 2022-11-28`.

Dashboard APIs have **no** session, API key, or GitHub OAuth. Anyone who can reach the host can read/write settings and data.

---

## PoC vs service

Keep these as the **module boundaries** when growing:

| Boundary | Today | Service direction |
| --- | --- | --- |
| Ingress | `/webhook` in `main.py` | Same; verify then enqueue |
| Review | `reviewer.py` in-request | Worker + persist via `save_pr_review` |
| GitHub client | `auth.py` | Shared client; cache tokens |
| Workspace data | SQLite + files | DB + secret store; drop demo seed in prod |
| Control UI | static `/app` | Same APIs, add auth |

**Gaps that matter for “service” (current code):**

- Live reviews are not stored; dashboard history is seed data.
- Rules are unused by the model prompt.
- Settings/PEM/GitHub browse APIs exist on the server but are mostly unused by the UI.
- In-process background tasks + blocking HTTP will not survive scale or process restart.
- No tenant model, no API authentication, secrets on disk and writable via HTTP.

---

## Dependencies

`fastapi`, `uvicorn`, `pyjwt[crypto]`, `requests`, `python-dotenv`, `python-multipart`. Python 3.10+.
