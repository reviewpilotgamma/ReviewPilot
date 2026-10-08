# Credential sign-in, with GitHub linked through the App install

## Overview

The landing page no longer offers GitHub sign-in, "Continue locally", or an install button. A single
**Sign in** button in the top-right opens `/login`, where the seeded **dev** and **admin** accounts sign in
with a username and password. Once signed in, the navbar shows **Install GitHub App**. Installing the App
(with GitHub's "request user authorization during installation") links the user's GitHub identity to the
signed-in account, which keeps the existing per-user repository scoping. Until a user has linked GitHub and
can see at least one installation, the dashboard shows only a message that they must install the GitHub App
before their data appears.

## Functional Requirements

1. **Landing.** Remove the Install GitHub App, Sign in with GitHub and Continue locally buttons (hero and
   header). The header has one **Sign in** button that goes to `/login`, or **Go to dashboard** when signed in.
2. **Login page (`/login`).** Username and password form, with a link back to the landing page. A successful
   sign-in sets the existing `rp_session` cookie and navigates to `next` (default `/dashboard`). There is no
   sign-up: accounts are seeded only. A signed-in visitor is redirected to `/dashboard`.
3. **Seeded accounts.** On startup the backend creates or updates two users from `backend/.env`:
   `SEED_DEV_USERNAME` / `SEED_DEV_PASSWORD` (role `dev`) and `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD`
   (role `admin`). Outside production, unset values default to `dev`/`dev12345` and `admin`/`admin12345`. In
   production, an account with no password configured is not seeded.
4. **Roles.** A new `users.role` column (`dev` | `admin`) replaces `ADMIN_GITHUB_LOGINS`.
   `is_admin(user)` is `user.role == "admin"`.
5. **Install GitHub App (navbar).** Visible to every signed-in user.
   - The button navigates to `GET /api/v1/auth/github/connect?mode=install`. That endpoint requires a session,
     sets a short-lived state cookie, and redirects to `https://github.com/apps/<slug>/installations/new?state=…`.
   - GitHub redirects back to the App's callback URL, `GET /api/v1/auth/callback?code&state&installation_id&setup_action`.
     The backend checks `state`, exchanges `code` for a user token, and stores the token, `github_id`,
     `github_login`, avatar and email on the **signed-in** user. It then redirects to `/dashboard`.
   - If GitHub returns without a `code` (the App does not request authorization on install), the callback
     continues with the plain OAuth authorize flow into the same callback.
   - If the App is already installed on the user's account, **Connect GitHub**
     (`/auth/github/connect?mode=authorize`) runs the OAuth authorize flow directly.
   - Once the user is linked and can see installations, the button reads **Manage GitHub App**.
6. **First-login gate.** While the user is not linked, or the linked token sees no installations, the
   dashboard shows the "Install the GitHub App to see your data" step with the install and connect actions.
   Other pages show a banner with the same actions. This also applies when GitHub is not configured (local
   development): the user is gated and the install button is disabled.
7. **Removed.** GitHub OAuth used as login (`GET /auth/login`), `POST /auth/dev-login`, local mode (the
   `local/manual` workspace and `AppInfo.local_mode`), the frontend `loginUrl` and `authApi.devLogin`.
   `ProtectedRoute` redirects to `/login?next=…`.
8. **`/auth/me`** returns `role`, `github_login` (nullable), `github_linked: bool` and a nullable `github_id`.

## Non-Functional Requirements

- Passwords are hashed with stdlib `hashlib.scrypt` (per-user salt, constant-time compare). No new
  dependency. Plaintext passwords never appear in logs or responses.
- `POST /auth/login` needs the existing `X-Requested-With` CSRF header. It returns one generic error
  for unknown users and wrong passwords. An in-memory limiter allows 5 failures per username per
  5 minutes.
- Per-user tenant isolation stays as it is today, driven by the linked user token.
- The migration keeps existing `users` rows and every foreign key that references them.
- Tests use pytest and respx, plus Vitest. No live GitHub calls.

## Sad Paths & Error States

- Wrong credentials: 401 "Invalid username or password".
- Too many failures: 429 "Too many attempts, try again later".
- `/auth/github/connect` without a session: redirect to `/login`.
- Callback with a bad or missing `state`, or no session: redirect to `/dashboard?github_error=state`, shown
  as a toast.
- Code exchange fails: `/dashboard?github_error=exchange`.
- GitHub App or OAuth client not configured: the install button is disabled with the tooltip "GitHub App not
  configured — ask an admin". `/auth/github/connect` redirects to `/dashboard?github_error=not_configured`.
- A linked token that is revoked or cannot be decrypted: the user is **not** logged out. The user sees no
  repositories, so the gate shows again.

## Edge Cases

- The same GitHub account linked by two ReviewPilot users: allowed (`github_id` is no longer unique).
- Users created by the old GitHub OAuth login stay in the database without a password, so they cannot sign
  in. Their reviews and rules are unaffected.
- A seed username that matches an existing row: that row gets the password and role.
- `setup_action=update`: the user is re-linked and the access cache is refreshed.

## Acceptance Criteria

- The landing page has no Install, GitHub or Continue-locally buttons. The top-right **Sign in** opens
  `/login`.
- The seeded `dev` and `admin` accounts sign in. `admin` gets admin-only Settings and Prompt editing; `dev`
  does not.
- A first sign-in shows the install message on the dashboard, and the navbar shows **Install GitHub App**.
- After install and callback, the dashboard shows only that user's repositories.
- Backend `ruff check .` and `pytest` pass. Frontend `npm run lint`, `npm run typecheck` and `npm test` pass.

## Out of Scope

Public sign-up, password reset or change UI, a user-management admin page, email verification, SSO.
