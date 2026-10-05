# Local review pipeline

## Overview

In development, you sign in without GitHub, open the existing dashboard, paste a pull request (title, repo, diff), and run the same review pipeline the webhook will use later. The result is stored as a normal review and shows up on the dashboard and in Review History. Nothing is posted to GitHub.

## Functional Requirements

- Local sign-in exists only when `ENV` is not `production`. The landing page shows a "Continue locally" button. It creates one local user, sets the same session cookie, and sends you to the dashboard. GitHub OAuth stays as it is for when credentials exist.
- While GitHub OAuth is not configured and the environment is not production, the sidebar lists a default repo, `local/manual`, plus any repo name that already has a saved review or a saved rule. The install wizard does not block the dashboard.
- A "Run review" screen takes repository (`owner/repo`), pull-request number, title, optional description, optional focus note, and the diff. It calls the existing prompt, Gemini, parser, and comment assembly, then saves a `PRReview`. The screen opens that review when it finishes.
- The same run is available from `python -m scripts.run_review`.
- Dashboard and history keep using the current APIs. A new row appears there with no change to how those pages load data.
- The local user can open Settings. Rules for a local repo still save through the existing rules API and are what the next run uses.

## Non-Functional Requirements

- Local sign-in and local repo access are refused when `ENV=production`.
- The Gemini key stays server-side. Tests mock Gemini and do not call it.
- A run does not need the GitHub App id, private key, or webhook secret.

## Sad Paths & Error States

- No `GEMINI_API_KEY`: the run fails with a clear message. Sign-in and empty history still work.
- Empty diff: the run is rejected and nothing is saved.
- Gemini failure: the error is shown on the form. No partial review is saved.

## Edge Cases

- Re-running the same repo and pull-request number saves another review. History shows both.
- A diff over the existing size limit is truncated the same way a webhook review already truncates it, and the comment says so.

## Acceptance Criteria

- With only `SESSION_SECRET`, `TOKEN_ENCRYPTION_KEY`, and `GEMINI_API_KEY` set, you can sign in locally, paste a diff, and see the verdict on the dashboard and in Review History.
- The same diff run from the script shows up in that history.
- Production mode does not expose local sign-in.

## Out of Scope

- GitHub App installation, webhooks, and posting the comment to GitHub.
- Email/password accounts.
- Seeded fake review results. History stays empty until you run one.
