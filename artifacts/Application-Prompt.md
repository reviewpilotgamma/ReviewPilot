# ReviewPilot: Deep Technical Analysis & Production Transformation Prompt

---

## Part 1: Elaborated Understanding of the Existing Project

### 1. Project Overview & Value Proposition

**ReviewPilot** is an AI-powered GitHub App designed to act as an automated senior software architect in pull request review loops. Unlike general coding assistants (like GitHub Copilot) that assist in code generation inside the IDE, ReviewPilot enforces **team-specific architectural standards, boundary isolation, and quality gates directly within the GitHub PR workflow**.

Key differentiators identified in the codebase and pitch deck:

- **Architectural-Only Focus**: Ignores formatting nits and style linting unless they represent system-level risks. Focuses on module layering, coupling/cohesion, API contracts, failure modes, async lifecycles, and security boundaries.
- **Team-Defined Rules**: Allows teams to define custom instructions in plain English per repository (e.g., *"Focus on async lifecycles and auth boundaries"* or *"Strict check on idempotency keys in payment flows"*).
- **Native GitHub Workflow**: Operates via GitHub App webhooks and PR comments (`@review`, `@bot plan`, and automatic review on PR open).

---



### 2. Core Logic & Existing Codebase Analysis



#### A. Webhook Ingestion & Cryptographic Verification (`main.py`)

- **Ingress (**`POST /webhook`**)**: GitHub delivers event payloads with the `X-Hub-Signature-256` header.
- **HMAC-SHA256 Verification**: Computes an HMAC digest of the raw request payload using `GITHUB_WEBHOOK_SECRET` and compares it using constant-time string comparison (`hmac.compare_digest`).
- **Bot Loop Suppression**: Explicitly checks `sender.type == 'Bot'`, `comment.user.type == 'Bot'`, or logins ending in `[bot]`. If detected, the event drops immediately to prevent infinite commenting loops.
- **Asynchronous Processing**: Responds with `HTTP 200 {"status": "ok"}` immediately and schedules payload processing in `fastapi.BackgroundTasks`.
- **In-Memory Event Bus**: Stores the last 30 webhook events in a `collections.deque(maxlen=30)`.



#### B. GitHub App Authentication Lifecycle (`auth.py`)

GitHub App authentication involves a two-tiered token exchange:

1. **RS256 App JWT (Server-to-GitHub)**:
  - Generated using the GitHub App ID (`iss: GITHUB_APP_ID`), issued at `now - 60s`, expiring in `10 minutes`.
  - Signed with the App's private key (`.pem` file) using `pyjwt` with RS256 algorithm.
  - Used to authenticate GitHub App meta-endpoints (e.g., `/app`, `/app/installations`).
2. **Installation Access Token (Repo-Scoped Work)**:
  - Mints a short-lived access token by calling `POST https://api.github.com/app/installations/{installation_id}/access_tokens` using the App JWT.
  - Used for all repository operations: fetching diffs, reading PR metadata, and posting comments.



#### C. Architectural Review Engine (`reviewer.py`)

- **PR Metadata Extraction**: Fetches PR title, base branch, head branch, author, and description from `GET /repos/{owner}/{repo}/pulls/{pull_number}`.
- **Diff Ingestion**: Requests the raw unified diff via header `Accept: application/vnd.github.v3.diff`.
  - Enforces a safety cutoff (`MAX_DIFF_CHARS = 120,000`) with truncation notices to avoid LLM context overflow.
- **Gemini LLM Prompting**:
  - Model: Google Gemini (`gemini-2.0-flash` by default via REST API `generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`).
  - Strict system prompt mandating structured sections:
    - `## Summary`
    - `## Architectural findings` (categorized with severity: **high**, **medium**, **low**)
    - `## Recommendations`
    - `## What looks solid`
  - Passes user context notes extracted from comment triggers (e.g., `@review focus on auth boundaries` extracts `"focus on auth boundaries"` into `requester_note`).
- **Comment Delivery**: Posts the structured review markdown back to the PR comments thread using the installation token.



#### D. Database & Persistence Layer (`reviewpilot.db` / `db.py`)

The project utilizes SQLite with three core tables:

1. `repo_rules`: `repo_full_name` (PK), `custom_instructions`, `verbosity` (`concise` | `detailed`), `review_mode` (`auto` | `on_demand`), `enable_security` (bool), `updated_at`.
2. `pr_reviews`: `id` (PK AUTOINCREMENT), `repo_full_name`, `pr_number`, `pr_title`, `author`, `summary`, `full_markdown`, `verdict` (`passed` | `warning` | `critical`), `score` (0.0 to 10.0), `lines_reviewed`, `created_at`.
3. `review_feedback`: `id` (PK AUTOINCREMENT), `review_id` (FK), `rating` (`helpful` | `unhelpful`), `notes`, `created_at`.



#### E. Configuration & Settings Store (`config_store.py`)

- Reads and updates `.env` dynamically on the server (`GITHUB_APP_ID`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_PRIVATE_KEY_PATH`, `GEMINI_API_KEY`, `GEMINI_MODEL`).
- Masking helper: hides sensitive credentials in API snapshots (e.g., `••••••••1234`).
- Canned fallback templates loaded from `bot_replies.json`.

---



### 3. Critical Gaps to Solve for Real User Onboarding


| Existing State (PoC)                                                                                                                | Required State (Production Prototype)                                                                                                                                   |
| ----------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **No User Auth / Tenant Boundaries**: Anyone reaching the API can read/write configurations.                                        | **User & Organization Authentication**: GitHub OAuth login, user sessions, and organization-scoped data isolation.                                                      |
| **Rules Disconnected from Reviewer**: `repo_rules` are saved in SQLite but not injected into the Gemini prompt during live reviews. | **Dynamic Rule Injection**: Every `@review` query fetches active `repo_rules` and injects custom guidelines, verbosity level, and security enforcement into the prompt. |
| **Reviews Not Persisted**: Live `@review` runs were not recorded into `pr_reviews`; the dashboard relied on mock seed data.         | **Complete Review Persistence**: Webhook-triggered reviews are saved to SQLite with automated verdict and score extraction, enabling live metrics.                      |
| **In-Memory Webhook Queue**: Background tasks execute in-process; failures or restarts result in dropped jobs.                      | **Durable Asynchronous Job Handling**: Structured task execution with error tracking, retry policies, and persistent audit logs.                                        |
| **Monolithic Static Frontend**: HTML, vanilla JS, and CSS bundled inside FastAPI static directory.                                  | **Clean Decoupled Architecture**: Root `frontend/` (React + Vite + TypeScript) and `backend/` (FastAPI + SQLite + Pydantic v2).                                         |


---



## Part 2: The Master Transformation Prompt

*You can copy and supply the prompt below directly to any AI coding system or developer to scaffold and build the full-fledged production prototype.*

---

```markdown
# TASK SPECIFICATION: Build ReviewPilot - Production-Ready PR Architectural Review Platform
 
## 1. PROJECT OVERVIEW & VALUE PROPOSITION
ReviewPilot is an automated AI software architect packaged as a GitHub App with a web-based management dashboard.
Unlike general autocomplete or lint tools, ReviewPilot reviews Pull Requests at the architectural and systems level:
- Module layering, coupling, cohesion, and boundary leaks
- Async lifecycle safety, database query efficiency, and concurrency
- Security boundaries, token leakage, and trust assumptions
- Breaking API contracts, backward compatibility, and migration risks
- Strict adherence to repository-specific guidelines defined by the team in plain English
 
---
 
## 2. TECHNOLOGY STACK & ARCHITECTURAL BOUNDARIES
The project must strictly separate frontend and backend into clean root directories:
 
```

PR-Review-Tool/
├── backend/                  # FastAPI Application & Background Tasks
│   ├── app/
│   │   ├── api/              # REST Endpoints (v1)
│   │   │   ├── auth.py       # GitHub OAuth & Session Endpoints
│   │   │   ├── webhooks.py   # GitHub App Webhook Ingress (HMAC verified)
│   │   │   ├── rules.py      # Per-repo custom review rules CRUD
│   │   │   ├── reviews.py    # PR review history & reviewer feedback
│   │   │   ├── metrics.py    # Analytics & health score aggregates
│   │   │   ├── github.py     # Proxy endpoints for App, installations, repos
│   │   │   └── settings.py   # System & model settings
│   │   ├── core/
│   │   │   ├── config.py     # Pydantic BaseSettings (.env validation)
│   │   │   ├── security.py   # HMAC signature verification & JWT utilities
│   │   │   └── database.py   # SQLite connection engine & session factory
│   │   ├── models/           # SQLAlchemy / SQLModel ORM models
│   │   ├── schemas/          # Pydantic v2 request/response schemas
│   │   ├── services/         # Business logic
│   │   │   ├── github_app.py # GitHub App JWT, Installation tokens, REST client
│   │   │   ├── reviewer.py   # PR Diff fetcher, Gemini API prompt orchestrator
│   │   │   └── metrics.py    # Metrics calculation service
│   │   └── main.py           # FastAPI app instance, CORS, routers
│   ├── tests/                # Pytest unit & integration tests
│   ├── alembic/              # Database migration scripts (or SQLite schema manager)
│   ├── requirements.txt      # Python dependencies
│   └── .env.example
│
├── frontend/                 # React (Vite) Single Page Application
│   ├── src/
│   │   ├── assets/           # Logos, icons, SVGs
│   │   ├── components/       # Reusable UI components
│   │   │   ├── layout/       # Navbar, Sidebar, Page Shell
│   │   │   ├── ui/           # Cards, Modals, Drawers, Badges, Tables
│   │   │   └── diff/         # Markdown & Diff Viewer
│   │   ├── context/          # Auth & Workspace state providers
│   │   ├── hooks/            # Custom React hooks (useAuth, useRules, useReviews)
│   │   ├── pages/            # View pages
│   │   │   ├── Landing.tsx   # Marketing & GitHub App install CTA
│   │   │   ├── Dashboard.tsx # Overview metrics, health scores, recent activity
│   │   │   ├── Rules.tsx     # Repo-level rule editor with prompt presets
│   │   │   ├── History.tsx   # Searchable PR reviews table with slide-over drawer
│   │   │   ├── Activity.tsx  # Live webhook log inspector
│   │   │   └── Settings.tsx  # GitHub App status, Gemini configuration
│   │   ├── services/         # Axios / Fetch API client
│   │   ├── types/            # TypeScript interfaces & types
│   │   ├── App.tsx           # Router configuration
│   │   └── main.tsx
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
└── README.md

```
 
---
 
## 3. CORE LOGIC SPECIFICATIONS
 
### A. GitHub App Integration (`backend/app/services/github_app.py`)
1. **GitHub App RS256 JWT**:
   - Mint an RS256 JWT signed with the App's private `.pem` key.
   - Claims: `iat = now - 60`, `exp = now + 600`, `iss = GITHUB_APP_ID`.
2. **Installation Token Exchange**:
   - `POST https://api.github.com/app/installations/{installation_id}/access_tokens` using the App JWT.
   - Cache tokens until expiry (50 minutes) to avoid rate limits.
3. **Repository Operations**:
   - Fetch PR metadata: `GET /repos/{owner}/{repo}/pulls/{pull_number}`
   - Fetch Unified Diff: Same endpoint with header `Accept: application/vnd.github.v3.diff`
   - Post Comment: `POST /repos/{owner}/{repo}/issues/{pull_number}/comments`
 
### B. Webhook Validation & Processing (`backend/app/api/webhooks.py`)
1. **Signature Verification**:
   - Verify `X-Hub-Signature-256` header against `HMAC-SHA256(raw_body, GITHUB_WEBHOOK_SECRET)`.
   - Reject mismatches with `401 Unauthorized`.
2. **Loop Prevention**:
   - If `sender.type == "Bot"` or `comment.user.type == "Bot"` or login ends with `[bot]`, ignore immediately.
3. **Event Dispatching**:
   - Respond with `200 OK` immediately.
   - Dispatch job asynchronously:
     - `pull_request.opened`:
       - If repo `review_mode == 'auto'`: Run full review and post comment.
       - Else: Post configurable welcome comment.
     - `issue_comment.created`:
       - If on a PR and body contains `@review`:
         - Extract user instruction note after `@review`.
         - Trigger architectural review with custom repo rules.
         - Post the generated review as a comment.
       - If body contains `@bot plan`:
         - Post planned execution checklist comment.
 
### C. Architectural Review Engine (`backend/app/services/reviewer.py`)
1. **Rule Integration**:
   - Retrieve stored `repo_rules` for the target repository from SQLite.
   - Invert flags into prompt directives:
     - Verbosity: `concise` (bulleted, brief) vs `detailed` (in-depth code-path analysis).
     - Security: When `enable_security == True`, explicitly enforce OWASP, secret leaks, and trust boundary checks.
     - Custom Instructions: Append raw team rules directly into the system prompt.
2. **Diff Handling**:
   - Truncate unified diff if length exceeds 120,000 characters with an explicit note.
3. **LLM Orchestration**:
   - Target Model: Google Gemini API (`gemini-2.0-flash` or configurable model).
   - Structured Output Prompt:
     ```text
     You are ReviewPilot, a senior software architect reviewing a GitHub pull request.
     Focus strictly on architectural concerns:
     - Module boundaries, decoupling, and dependency direction
     - Async lifecycles, database query patterns, and connection management
     - API contracts, breaking changes, and backward compatibility
     - Failure domains, retry safety, idempotency, and scalability
     - Security boundaries and trust assumptions
 
     Custom Repository Rules to Enforce:
     {custom_instructions}
 
     Verbosity: {verbosity}
     Security Mode: {enable_security}
     Requester Note: {requester_note}
 
     Diff:
     {diff}
     ```
   - Must output structured markdown with:
     - Executive Summary
     - Architectural Findings (tagged with severity: **Critical**, **Warning**, or **Passed**)
     - Specific Recommendations
     - What Looks Solid
     - Numerical score (0.0 to 10.0) and overall verdict (`passed`, `warning`, `critical`).
4. **Persistence**:
   - Save completed review into `pr_reviews` table.
   - Return formatted markdown with banner:
     ```markdown
     ## ✈️ ReviewPilot Architectural Audit
     ... review content ...
     ---
     _Triggered via ReviewPilot · Architecture Gatekeeper_
     ```
 
---
 
## 4. DATABASE SCHEMA (SQLite via SQLAlchemy / SQLModel)
 
### 1. `users`
- `id` (INTEGER, PK, AUTOINCREMENT)
- `github_id` (INTEGER, UNIQUE)
- `username` (VARCHAR)
- `avatar_url` (VARCHAR)
- `email` (VARCHAR, NULLABLE)
- `access_token` (VARCHAR) # Encrypted / protected
- `created_at` (TIMESTAMP)
 
### 2. `repo_rules`
- `repo_full_name` (VARCHAR, PK) # e.g. "org/repo"
- `custom_instructions` (TEXT, DEFAULT "")
- `verbosity` (VARCHAR, DEFAULT "concise") # "concise" | "detailed"
- `review_mode` (VARCHAR, DEFAULT "auto")  # "auto" | "on_demand"
- `enable_security` (BOOLEAN, DEFAULT 1)
- `updated_at` (TIMESTAMP)
 
### 3. `pr_reviews`
- `id` (INTEGER, PK, AUTOINCREMENT)
- `repo_full_name` (VARCHAR, INDEXED)
- `pr_number` (INTEGER)
- `pr_title` (VARCHAR)
- `author` (VARCHAR)
- `summary` (TEXT)
- `full_markdown` (TEXT)
- `verdict` (VARCHAR) # "passed" | "warning" | "critical"
- `score` (FLOAT)     # 0.0 - 10.0
- `lines_reviewed` (INTEGER)
- `created_at` (TIMESTAMP)
 
### 4. `review_feedback`
- `id` (INTEGER, PK, AUTOINCREMENT)
- `review_id` (INTEGER, FK -> pr_reviews.id)
- `user_id` (INTEGER, FK -> users.id, NULLABLE)
- `rating` (VARCHAR) # "helpful" | "unhelpful"
- `notes` (TEXT, DEFAULT "")
- `created_at` (TIMESTAMP)
 
### 5. `webhook_events`
- `id` (INTEGER, PK, AUTOINCREMENT)
- `event` (VARCHAR)
- `action` (VARCHAR)
- `repo` (VARCHAR)
- `sender` (VARCHAR)
- `payload_preview` (TEXT)
- `status` (VARCHAR) # "processed" | "ignored" | "failed"
- `error_message` (TEXT, NULLABLE)
- `created_at` (TIMESTAMP)
 
---
 
## 5. USER ONBOARDING & AUTHENTICATION FLOW
 
### A. User Authentication (GitHub OAuth)
1. **Login with GitHub**:
   - `GET /api/v1/auth/login`: Redirects user to GitHub OAuth authorize screen (`read:user`, `repo` scopes).
   - `GET /api/v1/auth/callback`: Exchanges authorization code for GitHub user access token.
   - Fetches user profile, creates/updates row in `users`, and sets an HTTP-only JWT session cookie.
   - `GET /api/v1/auth/me`: Returns authenticated user details.
   - `POST /api/v1/auth/logout`: Clears session.
 
### B. User Onboarding Flow
1. **Welcome & Connect**:
   - If user has no active repositories, guide them to install the GitHub App via dynamic link:
     `https://github.com/apps/<app-slug>/installations/new`.
2. **Repository Discovery**:
   - Once installed, the dashboard lists all installed organizations and repositories via `GET /api/v1/github/installations`.
3. **Configure First Rule**:
   - Prompt the user to select their repository and pick from preset rule templates:
     - *Standard Microservices* (isolation, API backwards compatibility)
     - *Strict Security* (OWASP, SQL injection, token leaks, input sanitization)
     - *Performance & Async* (connection pooling, event-loop blocking, index awareness)
4. **Trigger Review**:
   - Clear instructions to create a test PR or comment `@review` on an open PR.
 
---
 
## 6. FRONTEND UI/UX DESIGN SPECIFICATION (React + Vite)
 
### Aesthetic & Design System
- **Theme**: Dark mode by default, modern developer aesthetic (deep slate `#0b0f19`, dark card surfaces `#111827`, crisp borders `#1f2937`, electric violet `#8b5cf6` and emerald `#10b981` accents).
- **Typography**: Inter or Sora for headings, Fira Code or JetBrains Mono for code blocks.
- **Glassmorphism**: Subtle backdrop-blur on panels, clean micro-interactions, responsive side drawer for full PR review write-ups.
 
### Core Screens & Features
1. **Landing Page (`/`)**:
   - Value proposition hero ("Architectural review for every pull request").
   - Live installation button linking to GitHub App install flow.
   - Visual comparison: Traditional Linters vs ReviewPilot.
2. **Dashboard Overview (`/dashboard`)**:
   - 4 Top Metric Cards:
     - Total PRs Reviewed
     - Average Architecture Health Score (e.g. `8.7/10`)
     - Pass Rate (`88.2%`)
     - Developer Acceptance / Helpful Rate (`94%`)
   - Recent PR Reviews table with status badges (`Passed`, `Warning`, `Critical Risk`).
3. **Rule Editor (`/rules`)**:
   - Repo selector dropdown.
   - Preset chips (click to insert boilerplate rules).
   - Markdown textarea for custom team instructions.
   - Toggles: Verbosity (`Concise` / `Detailed`), Mode (`Auto on PR open` / `On-demand @review only`), Security Audit (`Enabled` / `Disabled`).
4. **Review History Drawer (`/history`)**:
   - Filter by repository, author, or verdict.
   - Clicking a row opens a slide-over drawer rendering the full Markdown audit with code diff snippets.
   - Interactive feedback widget: *"Was this review helpful? [Yes] [No]"* with optional feedback input.
5. **Activity Log (`/activity`)**:
   - Live feed of inbound webhook events with timestamps, payload details, and execution status.
6. **Settings (`/settings`)**:
   - GitHub App credentials status, Gemini API Key validation, and custom canned reply templates.
 
---
 
## 7. CODING PRACTICES & IMPLEMENTATION GUIDELINES
1. **Clean Architecture**:
   - Backend routes must remain thin, delegating to services (`reviewer.py`, `github_app.py`, `metrics.py`).
   - Use Pydantic v2 for strict request validation and response serialization.
   - SQLite should run in **WAL mode** (`PRAGMA journal_mode=WAL;`) with thread-safe connections.
2. **Error Resilience**:
   - If the Gemini API or GitHub diff fetch fails, the webhook must post a polite GitHub comment informing the developer rather than failing silently.
   - All external HTTP calls must have explicit timeouts (`timeout=30`).
3. **Security Standards**:
   - Never expose raw API keys or private keys to the client. Mask secrets in settings endpoints.
   - Validate HMAC webhook signatures before parsing payload data.
```



---



### Summary of What Was Covered

1. **Complete Analysis**: Traced all existing files (`main.py`, `auth.py`, `reviewer.py`, `config_store.py`, `bot_replies.json`, `reviewpilot.db`), explaining cryptographic verification, JWT minting, GitHub REST interactions, Gemini prompting, and SQLite data models.
2. **Identified Missing Links**: Highlighted why the current PoC didn't apply stored rules to live reviews, didn't persist live webhook reviews to SQLite, lacked user auth, and had an in-process background worker.
3. **Actionable Production Prompt**: Provided a standalone blueprint specifying root folder separation (`frontend/` Vite+React, `backend/` FastAPI), SQLite schema & connection handling, GitHub OAuth user onboarding, dynamic prompt rule injection, and responsive UI flows.

