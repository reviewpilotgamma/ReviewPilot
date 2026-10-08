# Plan: Credential sign-in, with GitHub linked through the App install

## Context Snapshot

| Kind | Symbols |
| --- | --- |
| Existing | `User`, `auth.py` (`login`, `callback`, `dev_login`, `me`, `logout`, `_safe_next`, `_cookie_kwargs`), `deps.get_current_user`/`is_admin`/`get_accessible`, `access.get_accessible_repos`/`local_workspace`, `github_user.exchange_code`/`get_user`, `security.create_session_token`/`encrypt_token`, `config.Settings`, `main.lifespan`; frontend `Landing.tsx`, `Navbar.tsx`, `AuthContext`, `ProtectedRoute`, `OnboardingWizard.InstallStep`, `Dashboard.showWizard`, `AppShell`, `client.loginUrl`, `endpoints.authApi` |
| New | migration `0005_credential_auth.py`; `security.hash_password`/`verify_password`; `services/accounts.py` (`seed_accounts`, `authenticate`, `LoginThrottle`); `schemas/auth.LoginIn`; endpoints `POST /auth/login`, `GET /auth/github/connect`; frontend `pages/Login.tsx`, `components/layout/GithubConnect.tsx` (`InstallAppButton`, `ConnectGithubLink`, `InstallBanner`), `client.githubConnectUrl` |
| Modified | `models/user.py` (role, password_hash, github_login, nullable github_id), `schemas/auth.UserOut`, `schemas/github.AppInfo` (drop `local_mode`), `api/github.py`, `config.py` (SEED_* settings, drop `ADMIN_GITHUB_LOGINS`/`local_mode`), `deps.py`, `access.py`, `main.py`, `tests/conftest.py`, `test_auth.py`, `test_local_mode.py`; frontend `App.tsx`, `Landing.tsx`, `Navbar.tsx`, `AuthContext.tsx`, `ProtectedRoute.tsx`, `OnboardingWizard.tsx`, `Dashboard.tsx`, `AppShell.tsx`, `types/api.ts`, `endpoints.ts`, `client.ts`, tests; `backend/.env.example`, `README.md`, `tech-stack.md` |

### Hotspot map

| Requirement | Files / symbols |
| --- | --- |
| FR1 landing | `pages/Landing.tsx` |
| FR2 login page | `pages/Login.tsx`, `App.tsx`, `AuthContext.login`, `ProtectedRoute` |
| FR3 seeding | `services/accounts.seed_accounts`, `main.lifespan`, `config.SEED_*` |
| FR4 roles | `models/user.role`, `0005_credential_auth.py`, `deps.is_admin` |
| FR5 install + link | `api/auth.github_connect`, `api/auth.callback`, `GithubConnect.tsx`, `Navbar.tsx` |
| FR6 gate | `OnboardingWizard.InstallStep`, `Dashboard.showWizard`, `AppShell` + `InstallBanner`, `deps.get_accessible` |
| FR7 removals | `auth.py`, `access.local_workspace`, `config.local_mode`, `AppInfo.local_mode`, `client.loginUrl`, `endpoints.devLogin` |
| FR8 me | `schemas/auth.UserOut`, `api/auth.me` |

### Design notes

- Password format: `scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>` with n=2**14, r=8, p=1.
- Migration: on SQLite, set `PRAGMA foreign_keys=OFF` before the batch rebuild of `users`, so dropping the
  old table does not fire `ON DELETE SET NULL` on referencing rows. A batch `naming_convention` gives the
  unnamed unique constraint on `github_id` a name so it can be dropped.
- `access_token` stays `NOT NULL`; `""` means not linked. `get_accessible` returns `{}` when not linked or
  when the token cannot be decrypted, and catches `ReauthRequired` so a revoked token does not log the user out.
- The callback path stays `/api/v1/auth/callback`, so existing GitHub App callback settings keep working.
- The test helper `make_user` gives `admin-user` the admin role, replacing `ADMIN_GITHUB_LOGINS` in fixtures.

## Phase 1 — Backend

- [x] 1.1 Model, migration 0005, password hashing, settings, account seeding and throttle, `POST /auth/login`,
      `GET /auth/github/connect`, linking callback, `get_accessible` changes, removal of dev-login and local mode
- [x] 1.2 Tests: login, throttle, seeding, connect/callback linking, the migration keeps FK references,
      `/me` fields, unlinked user sees no repos; update the conftest admin fixture
- [x] 1.3 Quality gate: `ruff check .`, `pytest` — `ee7d3f9`

## Phase 2 — Frontend

- [x] 2.1 Types, endpoints, client; `Login` page and route; `AuthContext.login` → `/login`; `ProtectedRoute` text
- [x] 2.2 Landing cleanup; Navbar install button; `GithubConnect` components; wizard install step; dashboard
      gate; app-shell banner; `github_error` toast
- [x] 2.3 Tests and quality gate: `npm run lint`, `npm run typecheck`, `npm test` — `8454db0`

## Phase 3 — Docs

- [x] 3.1 `backend/.env.example`, `README.md` (seed accounts, GitHub App callback and "request user
      authorization during installation"), `tech-stack.md` auth line

## Phase 4 — Admin sees all App installations (follow-up)

- [x] 4.1 `github_app.list_installation_repositories`, `access.get_app_repos`; `get_accessible` uses them for
      admins; navbar treats any installation as installed; tests
- [x] 4.2 Quality gate (backend and frontend) and a README note

## Implementation Notes

- Connect is a `GET /auth/github/connect?mode=install|authorize` redirect rather than a POST that returns a
  URL. The state lives in an HttpOnly cookie and the callback also requires the session, so a cross-site
  GET cannot link a foreign account.
- `get_accessible` returns `{}` for unlinked users and for `ReauthRequired`, so a revoked token gates the user
  instead of logging them out. `test_access.test_api_maps_reauth_to_401` was renamed to match.
- Migration 0005 turns SQLite foreign keys off around the `users` rebuild. `test_migration_credential_auth`
  checks that `repo_rules.updated_by_user_id` survives the upgrade. The downgrade gives duplicate or missing
  `github_id` values a placeholder `-id` so the restored UNIQUE holds.
- The seeder converts the old local-mode row (`github_id = 0`, username `dev`) into the seeded dev account.
- The 401 from a failed sign-in still fires the client's unauthorized listeners. That is harmless, because
  `me` is already null, and the login page maps 401 and 429 to its own messages.
