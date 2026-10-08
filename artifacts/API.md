# ReviewPilot API reference

Taken from `backend/app/api/*.py` and `backend/app/main.py` on 8 October 2026. Interactive OpenAPI docs are at
`GET /docs` on a running backend outside production.

## Conventions

| Topic | Rule |
| --- | --- |
| Base path | `/api/v1` for every route below unless shown with a leading `/`. |
| Format | JSON. Errors are `{"detail": ...}`. Unhandled errors return `500 {"detail", "request_id"}`. |
| Session | `rp_session` cookie (HS256 JWT, `HttpOnly`, `SameSite=Lax`), set by `POST /auth/login`. |
| CSRF | Every `POST`, `PUT` and `DELETE` on the rules, documents, prompt, reviews, insights, settings and auth routers needs `X-Requested-With: ReviewPilot`, or it gets `403`. |
| Request id | Send `X-Request-ID` or one is generated; it is echoed in the response header and logs. |
| Tenant scope | Data routes only cover repositories the user can reach (see [ARCHITECTURE.md §9](ARCHITECTURE.md#9-authentication-roles-and-tenant-isolation)). Other repositories return `404`. |
| Shared errors | `401 {"detail": "reauth_required"}` (GitHub link revoked), `502` (GitHub call failed), `503` (integration not configured). |

**Auth column:** **P** public · **U** signed-in user · **A** admin role · **R** user with access to that repository ·
**S** valid GitHub webhook signature.

`{owner}` and `{repo}` must match `^[A-Za-z0-9_.-]{1,100}$` and are compared lower-case.

## Health and webhooks

| Method & path | Auth | Input | Response |
| --- | --- | --- | --- |
| `GET /health` | P | — | `{status: "ok"\|"degraded", db: bool, worker: "running"\|"stopped"}` |
| `POST /webhooks/github` | S | GitHub payload; headers `X-Hub-Signature-256`, `X-GitHub-Event`, `X-GitHub-Delivery` | `200 {status: "ok"\|"duplicate", jobs: n}`; `401` bad signature; `400` bad JSON |
| `POST /webhook` | S | Same | Legacy alias kept for older App configurations |
| `GET /webhooks/events` | U | `status?` (`queued`/`processed`/`ignored`/`failed`), `repo?`, `limit` 1–200 (50), `before_id?`, `include_bot` (false) | `EventOut[]` with their `jobs` (`kind`, `status`, `attempts`, `last_error`, `error_code`, `review_id`). Admins also see events with no repository. |

## Auth

| Method & path | Auth | Input | Response |
| --- | --- | --- | --- |
| `POST /auth/login` | P | `{username, password}` | `UserOut`, sets the session cookie. `401` wrong credentials; `429` after 5 failures in 5 minutes |
| `GET /auth/me` | U | — | `UserOut {id, username, role, avatar_url, email, github_id, github_login, github_linked, is_admin}` |
| `POST /auth/logout` | P | — | `204`, clears the cookie |
| `GET /auth/github/connect` | U (cookie) | `mode` = `install` (default) or `authorize` | `302` to the App install page or GitHub OAuth; sets `rp_oauth_state`. Not signed in → `/login`. Not configured → `/dashboard?github_error=not_configured` |
| `GET /auth/callback` | U (cookie) | `code?`, `state`, `installation_id?`, `setup_action?` | `302` to `/dashboard` after linking; `?github_error=state` or `exchange` on failure. With no `code`, redirects to OAuth authorize |

## GitHub

| Method & path | Auth | Input | Response |
| --- | --- | --- | --- |
| `GET /github/app` | P | — | `{configured, slug, name, install_url, html_url}` (App details cached 10 min) |
| `GET /github/installations` | U | `refresh` (false) bypasses the 5-minute access cache | `[{installation_id, account_login, account_type, avatar_url, repos: [{full_name, private, html_url, has_rules}]}]` |

## Rules and documents

| Method & path | Auth | Input | Response |
| --- | --- | --- | --- |
| `GET /rules/presets` | P | — | `[{id, name, description, instructions}]` (microservices, security, performance) |
| `GET /rules` | U | — | `RuleOut[]` for every accessible repository, defaults filled in (`is_default: true`) |
| `GET /rules/{owner}/{repo}` | R | — | `RuleOut {repo_full_name, custom_instructions, verbosity, review_mode, enable_security, updated_at, is_default}` |
| `PUT /rules/{owner}/{repo}` | R | `{custom_instructions` ≤ 10 000 chars, `verbosity` `concise`/`detailed`, `review_mode` `auto`/`on_demand`, `enable_security}` | `RuleOut` |
| `DELETE /rules/{owner}/{repo}` | R | — | `204`; the repository goes back to defaults |
| `GET /rules/{owner}/{repo}/documents` | R | — | `{items: DocumentOut[], total, cache_status: none\|inline\|cached\|pending}` |
| `POST /rules/{owner}/{repo}/documents` | R | multipart `file` (`.txt` `.md` `.markdown` `.rst` `.pdf`, ≤ 5 MB, ≤ 20 per repo); `warm` (true) builds the Gemini cache before responding | `201 DocumentOut + {cache_status, cache_error}` |
| `DELETE /rules/{owner}/{repo}/documents/{id}` | R | — | `204`, then rebuilds the cache; `404` unknown document |

## Golden prompt

| Method & path | Auth | Input | Response |
| --- | --- | --- | --- |
| `GET /prompt` | U | — | `PromptOut {template, is_default, updated_at, updated_by, segments, slots, directives, placeholders, warnings}` |
| `PUT /prompt` | A | `{template}` (≤ 20 000 chars; must contain `{{custom_instructions}}`) | `PromptOut`; `422 {errors}` when invalid |
| `DELETE /prompt` | A | — | `204`, back to the built-in prompt |

## Reviews and feedback

| Method & path | Auth | Input | Response |
| --- | --- | --- | --- |
| `GET /reviews` | U | `repo?`, `author?`, `verdict?` (`passed`/`warning`/`critical`), `q?` (title search), `page` (1), `page_size` 1–100 (20), `sort` `-created_at`/`created_at` | `{items: ReviewListItem[], total, page, page_size}` |
| `GET /reviews/{id}` | R | — | `ReviewDetail` = list item + `full_markdown`, `requester`, `model`, `review_context`, `my_feedback` |
| `GET /reviews/{id}/feedback` | R | — | `FeedbackOut[]` |
| `POST /reviews/{id}/feedback` | R | `{rating: helpful\|unhelpful, notes?` ≤ 2 000`}` | `FeedbackOut` (one per user per review; re-posting updates it) |

`ReviewListItem`: `id, repo_full_name, pr_number, pr_title, author, verdict, score, lines_reviewed, summary,
created_at, trigger, pr_url, diff_truncated, feedback_counts`.

## Metrics and insights

| Method & path | Auth | Input | Response |
| --- | --- | --- | --- |
| `GET /metrics/summary` | U | `repo?`, `days` 1–365 (30) | `{total_reviews, avg_score, pass_rate, lines_reviewed, verdict_counts, recent: ReviewListItem[10]}` |
| `GET /metrics/trend` | U | `repo?`, `days` 1–365 (30) | `[{date, reviews, avg_score}]`, one point per day |
| `GET /insights` | U | `repo` (required) | `{repo_full_name, snapshot, total_reviews, pending_count, pending_capped, ran_model}` |
| `POST /insights/analyze` | U | `{repo, rebuild?}` | Same, after a Gemini run. `422` no usable reviews; `502` model failure or unreadable output |

## Settings

| Method & path | Auth | Input | Response |
| --- | --- | --- | --- |
| `GET /settings` | U | — | `SettingsOut` with secrets masked, `github_private_key_present`, `webhook_url`, `is_admin` |
| `PUT /settings` | A | Partial: `github_app_id`, `github_app_slug`, `github_webhook_secret`, `github_private_key_path`, `github_client_id`, `github_client_secret`, `gemini_api_key`, `gemini_model`. Masked values are ignored; newlines rejected | Writes `backend/.env`, reloads → `SettingsOut`; `422` invalid |
| `POST /settings/validate/gemini` | A | `{api_key?, model?}` (falls back to stored values) | `{ok, message, model}` |
| `POST /settings/validate/github` | A | — | `{ok, message, app_name?, installations?}` |
| `GET /settings/replies` | U | — | `{welcome, plan, error, empty_diff}` |
| `PUT /settings/replies` | A | Same, each 1–5 000 chars | Saved replies |
