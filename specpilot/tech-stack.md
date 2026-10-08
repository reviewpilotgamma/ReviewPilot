# Tech Stack

Record any change to this stack here *before* implementing it.

## Backend (`backend/`)

- Python 3.11+
- FastAPI and uvicorn
- SQLAlchemy 2 with Alembic migrations
- Pydantic v2 and pydantic-settings. Config is loaded from `backend/.env` (`app/core/config.py`).
- httpx for GitHub and LLM HTTP calls
- PyJWT (GitHub App JWT and session cookie) and cryptography (Fernet token encryption)
- Seeded username/password accounts (`dev`, `admin` roles) hashed with stdlib `hashlib.scrypt`. GitHub OAuth
  is used only to link a user's GitHub identity while installing the GitHub App.
- In-process, DB-backed job worker that claims jobs atomically, retries with backoff, and resumes jobs after a restart

## AI / LLM

- Google Gemini (`gemini-2.0-flash` by default), configured via `GEMINI_*` settings.
- The model sits behind the reviewer service so it can be swapped later. No Gemini-specific types should
  leak outside it.
- Explicit Gemini Cached Contents for per-repo architecture/requirements documents (fallback: inline
  injection when the pack is below the cache size gate). Built synchronously on document upload/delete, with
  a lazy rebuild on the next review as fallback. TTL via `GEMINI_CACHE_TTL_SECONDS`.
- PDF text extraction for uploads via `pypdf`; multipart uploads via `python-multipart`.

## Storage

- SQLite in WAL mode for the pilot (rules, reviews, jobs, uploaded documents, cache metadata, and the
  org-wide golden prompt override).
- Postgres is a possible later target. Keep SQL portable through SQLAlchemy.

## Frontend (`frontend/`)

- React 18, TypeScript, and Vite
- TanStack Query for server state; react-router for routing
- Tailwind CSS, lucide-react, react-markdown with remark-gfm and rehype-highlight
- The API base comes from `VITE_API_BASE` (defaults to `/api/v1`, proxied by Vite in development)

## Tooling

- Backend: ruff (lint and isort), pytest, pytest-asyncio, pytest-cov, and respx (HTTP mocking)
- Frontend: ESLint, `tsc` type checking, Vitest, and Testing Library

## Deployment

- Runs as a single service on an internal host or VM. A free host (Render, etc.) is acceptable for the pilot.
- No multi-tenant SaaS.
- Secrets live in `backend/.env` and `backend/secrets/`, both gitignored.
- `SPECPILOT_API_KEY` belongs only in the repo-root `.env`, which the SpecPilot tooling reads. It is not
  application config.
