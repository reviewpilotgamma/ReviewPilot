# Remove manual "Run review"

## Overview

Take out the manual review run completely: the Run review screen, the `POST /api/v1/reviews/manual` endpoint, the `run_manual_review` service, and the `python -m scripts.run_review` CLI. After this, reviews only come from the GitHub webhook pipeline (a PR event or an `@review` comment). Local sign-in and local repo listing stay as they are.

## Functional Requirements

- The sidebar no longer shows "Run review".
- The `/run` route is removed. Opening `/run` shows the existing Not Found page.
- The `RunReview` page, `reviewsApi.runManual`, and the `ManualReviewInput` type are deleted.
- `POST /api/v1/reviews/manual` is removed, so calling it returns 404/405. `ManualReviewIn` is deleted.
- `run_manual_review`, `diff_stats` (only used there), and `EmptyDiffError` are deleted from the backend.
- `backend/scripts/run_review.py` is deleted, and the `.env.example` comment that points to it is updated.
- `assemble_comment` stops treating `"manual"` as a requester trigger.
- Dashboard, History, Rules, Settings, Activity, the webhook flow, and local sign-in behave exactly as before.

## Non-Functional Requirements

- No database migration. Existing `PRReview` rows with `trigger="manual"` stay readable and still appear in history.
- Lint, typecheck, pytest, and Vitest all pass after the removal.

## Sad Paths & Error States

- An old bookmark or link to `/run` shows Not Found and does not crash.
- A client that still posts to `/reviews/manual` gets a 404 or 405, not a 500.

## Edge Cases

- In local mode with no GitHub configured, there is no longer a way to create a review, so history stays empty. This is accepted.
- Reviews saved earlier with `trigger="manual"` still render in History and the review drawer.

## Acceptance Criteria

- No references to `RunReview`, `runManual`, `ManualReviewIn`, `run_manual_review`, `EmptyDiffError`, or `scripts.run_review` remain in `backend/` or `frontend/src/`.
- The sidebar has 5 items: Dashboard, Rules, Review History, Activity, Settings.
- Local-mode tests for dev-login and local installations still pass.
- All quality gates pass.

## Out of Scope

- Deleting or migrating existing `trigger="manual"` reviews.
- Removing local sign-in or `local/manual` repo access.
- Rewriting the completed `local_review_20261003` track. It stays as history, and this track supersedes its tasks 3 and 4.
