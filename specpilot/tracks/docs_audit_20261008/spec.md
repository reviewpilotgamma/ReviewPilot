# Validate and refresh the artifacts documents — Specification

## Overview

`artifacts/` holds the product documents that the panel and new engineers read. Most of them were written on
28 September 2026 for the original PoC: a single `main.py` with SQLite, a static Alpine UI, and no login. The code
has since become a `backend/` (FastAPI, SQLAlchemy, Alembic, DB-backed job worker) and `frontend/` (React, Vite)
app with seeded sign-in, per-repo documents, a golden prompt, diff batching, a Scope Check, and Insights.

Current state of the folder:

| File | Finding |
| --- | --- |
| `ARCHITECTURE.md` | Describes the old PoC (`main.py`, `auth.py`, `static/`, in-memory events, no auth). Wrong in almost every section. |
| `ReviewPilot_Architecture.docx` | Same content as `ARCHITECTURE.md`, plus three product sections (Problem, Why ReviewPilot, Key strengths) that exist nowhere else. |
| `REQUIREMENTS.md` | Requirement text still valid; the PoC status column is stale (most "Not started" items are now done) and features added since are missing. |
| `ReviewPilot_Requirements.docx` | Word copy of `REQUIREMENTS.md`. Duplicate. |
| `implementation.md` | The original build plan. Mostly still accurate. Outdated on login (GitHub OAuth → seeded credentials), admin rule (`ADMIN_GITHUB_LOGINS` → `admin` role), diff truncation (→ batching), banner emoji, dashboard KPI, and routes. Its §10 API table duplicates what an API reference should hold, and is incomplete. |
| `Application-Prompt.md` | The source brief that `implementation.md` was built from. Historical input, not a description of the system. |
| `TODO.md` | Early backlog notes with no status. |

Missing: an index that says which document is current and which is historical, and an API reference that matches
the routers. The README and `specpilot/product.md` also link `implementation.md` and `Application-Prompt.md` at the
repo root, where they do not exist.

## Functional Requirements

1. **FR-1 Remove duplicates.** Delete `ReviewPilot_Requirements.docx` and `ReviewPilot_Architecture.docx`. Markdown
   is the single source (diffable, reviewed in PRs). Before deleting the Architecture `.docx`, move its unique
   Problem / Why ReviewPilot / Key strengths content into `ARCHITECTURE.md`.
2. **FR-2 Rewrite `ARCHITECTURE.md`** to describe the current code: system context, runtime, code map, request
   surfaces, webhook → job → worker → review pipeline, prompt assembly, data model (all tables), auth and tenant
   isolation, frontend, configuration, deployment, and remaining gaps.
3. **FR-3 Update `REQUIREMENTS.md`.** Keep requirement IDs and wording. Refresh the status column to match the
   code, add requirements for features built since (documents, golden prompt, diff batching, Scope Check,
   Insights, roles, repo grants, bot-event filtering), correct statements about login and seed data, and bump the
   date.
4. **FR-4 Update `implementation.md`.** Mark it as the original build plan, add a "Changes since this plan" table,
   correct the outdated sections in place (auth, truncation, comment banner, routing, dashboard KPI), and replace
   the §10 endpoint table with a link to the new API reference.
5. **FR-5 Mark `Application-Prompt.md` as historical** with a short header note. Do not rewrite the brief.
6. **FR-6 Update `TODO.md`** with a status per item (done / not started / not a code task), keeping the
   author's items.
7. **FR-7 Add `artifacts/API.md`**: every `/api/v1` route plus `/health` and `/webhook`, with auth level, inputs
   and response, taken from the routers.
8. **FR-8 Add `artifacts/README.md`**: an index of the folder that says what each document is for and whether it is
   current or historical.
9. **FR-9 Fix broken links** in the root `README.md` and `specpilot/product.md`.

## Non-Functional Requirements

- Every factual claim (route, table, setting, default, behavior) must be checked against the code.
- Follow `specpilot/product-guidelines.md` voice and keep docs concise: tables over prose.
- No secrets or real credentials beyond the documented development defaults.

## Sad Paths & Error States

- If a `.docx` holds content not present in Markdown, it is migrated before deletion, never lost.
- The user's own uncommitted `README.md` edit must not be included in this track's commits.

## Edge Cases

- `.env.example` sets `GEMINI_MODEL=gemini-3.5-flash-lite` while the code default is `gemini-2.0-flash`. Document
  both.
- `@review` on a plain issue is now ignored and recorded in Activity, not answered with a comment (FR-G6 changed).
  Record this honestly as Partial.

## Acceptance Criteria

1. `artifacts/` contains no `.docx` duplicates.
2. `ARCHITECTURE.md`, `REQUIREMENTS.md`, `API.md` and `implementation.md` describe the current code; spot checks of
   routes, tables and settings against the source all match.
3. `artifacts/README.md` indexes every file.
4. No Markdown link in `README.md`, `specpilot/`, or `artifacts/` points at a missing file.

## Out of Scope

- Code changes. Regenerating Word or PDF exports (they can be produced from the Markdown on demand).
- Rewriting `Application-Prompt.md` or the per-track specs.
