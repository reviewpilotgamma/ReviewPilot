# Local review pipeline

## Context snapshot

Existing symbols stay: `AuthContext.login`, session cookie in `auth.py`, `PRReview`, `assemble_comment`, `build_review_system_prompt`, `gemini.generate`, `parse_review`, `load_rule_settings`.

New symbols: `POST /api/v1/auth/dev-login`, `Settings.local_mode`, `local_workspace`, `run_manual_review`, `POST /api/v1/reviews/manual`, `RunReview` page, `scripts.run_review`.

Unchanged: webhook receive, the worker, and posting comments through `github_app.py`.

## Tasks

### Phase 1 — Local product path

1. [x] Local session. Add `POST /api/v1/auth/dev-login` (404 in production). Add `local_mode` to `GET /api/v1/github/app`. Show **Continue locally** on the landing page when `local_mode` is true.
2. [x] Local repositories. When `local_mode` is on, `get_accessible` returns `local/manual` plus repos that already have a review or a rule, and does not call GitHub. Skip the install wizard in that mode.
3. [x] Manual review run. `run_manual_review` uses the existing prompt, Gemini, parser, and `assemble_comment`, then saves a `PRReview` with `trigger="manual"`. `POST /api/v1/reviews/manual` exposes it. Add a Run review screen that opens the saved review in history.
4. [x] Script. `python -m scripts.run_review` calls `run_manual_review` and prints the review id, verdict, and score.
5. [x] Tests. Dev-login, local installations, manual run with mocked Gemini, empty diff, missing key, and the Run review form.
6. [x] Docs. Note local mode and the script in `backend/.env.example`.
