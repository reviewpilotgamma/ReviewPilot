# Validate and refresh the artifacts documents — Plan

## Context snapshot

**Existing documents that stay:** `artifacts/REQUIREMENTS.md`, `artifacts/ARCHITECTURE.md`,
`artifacts/implementation.md`, `artifacts/Application-Prompt.md`, `artifacts/TODO.md`.

**Removed:** `artifacts/ReviewPilot_Requirements.docx`, `artifacts/ReviewPilot_Architecture.docx`.

**New:** `artifacts/README.md`, `artifacts/API.md`.

**Sources of truth checked:** `backend/app/main.py`, `backend/app/api/*.py`, `backend/app/api/deps.py`,
`backend/app/models/*.py`, `backend/app/core/config.py`, `backend/.env.example`,
`backend/app/services/{dispatcher,worker,reviewer,prompts,documents,diff_batching,insights,metrics,accounts,access,config_store}.py`,
`backend/app/data/bot_replies.json`, `backend/scripts/grant_repo.py`, `frontend/src/App.tsx`,
`frontend/src/components/layout/Sidebar.tsx`.

## Hotspot map

| Area | File | Change |
| --- | --- | --- |
| Duplicates | `artifacts/*.docx` | Delete after migrating the Architecture docx's unique sections |
| Architecture | `artifacts/ARCHITECTURE.md` | Full rewrite to current code + product sections from the docx |
| Requirements | `artifacts/REQUIREMENTS.md` | Status column, new FR rows, auth/seed statements, date |
| API | `artifacts/API.md` (new) | Route table from the routers |
| Build plan | `artifacts/implementation.md` | Status banner, changes table, §8.2/§8.7/§9/§10/§13.5/§13.7 fixes |
| Brief | `artifacts/Application-Prompt.md` | Historical note |
| Backlog | `artifacts/TODO.md` | Status per item |
| Index | `artifacts/README.md` (new) | Folder index |
| Links | `README.md`, `specpilot/product.md` | Point at `artifacts/` |

## Phase 1: Documents

- [ ] **1.1 Remove duplicates and rewrite the architecture.** Move Problem / Why / Key strengths from the
  Architecture docx into `ARCHITECTURE.md`, rewrite the rest from the code, delete both `.docx` files.
- [ ] **1.2 API reference.** Write `artifacts/API.md` from the routers and `deps.py`.
- [ ] **1.3 Requirements.** Update status, add new rows, fix the auth and seed statements.
- [ ] **1.4 Historical docs.** `implementation.md` banner, changes table and in-place fixes; `Application-Prompt.md`
  note; `TODO.md` status.
- [ ] **1.5 Index and links.** `artifacts/README.md`; fix links in `README.md` and `specpilot/product.md`; check every
  relative link resolves.

Gate (docs only, no code touched): every relative Markdown link resolves; spot-check claims against the source.
