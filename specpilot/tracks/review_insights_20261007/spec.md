# Recurring themes from stored ReviewPilot comments

## Overview

ReviewPilot already stores each PR review. Operators still cannot see **recurring
architectural themes** across those comments.

This track adds an on-demand **Insights** page. The operator picks a repository,
clicks Analyze, and an LLM summarizes ReviewPilot's stored review comments for
that repo. Later runs merge the **previous snapshot** with **only the new
reviews** (watermark). A regenerate option rebuilds from recent reviews without
the old snapshot.

The UI uses the existing design system (paper/ink, signal teal, `glass` cards,
lucide icons) and **no emojis**.

## Functional Requirements

1. **Per-repo snapshots.** Insights are scoped to one `owner/repo`. Selecting
   "All repositories" does not run analysis. Each successful run stores a
   snapshot: watermark (`through_review_id`), `included_count`, summary
   markdown, structured themes, model name, and who ran it.
2. **GET current state.** `GET /api/v1/insights?repo=` returns the latest
   snapshot (or null), `total_reviews`, `pending_count` (reviews with `id`
   greater than the watermark), and `pending_capped` when pending exceeds the
   per-run cap.
3. **Analyze (incremental).** `POST /api/v1/insights/analyze` with `{repo}`
   loads the latest snapshot and the next pending reviews (oldest first, cap
   50). Compact cards (id, PR, verdict, score, summary, findings excerpt,
   helpful/unhelpful) go to Gemini together with the previous themes JSON.
   Unhelpful-majority reviews are omitted from cards. The model returns JSON
   themes; invented review ids are dropped. A new snapshot is saved.
4. **No-op.** If there is a snapshot and `pending_count` is 0, POST does not
   call the model and returns the existing snapshot with `ran_model: false`.
5. **Regenerate.** `{repo, rebuild: true}` ignores the snapshot and analyzes
   the newest 50 reviews in the repo. Requires at least one review.
6. **Zero reviews.** POST with no reviews in that repo returns 422.
7. **Insights page (`/insights`).** New sidebar item after Review History,
   same AppShell/Navbar. Uses the header repository selector. Empty state if
   none selected. Shows pending count, **Analyze N new reviews**,
   **Regenerate from scratch** (confirm modal), last-run meta, summary
   markdown, and theme cards (severity badge, evidence, links to
   `/history?review=`). Loading and error states match other pages.
8. **History affordance.** The History page has a quiet link to Insights so
   operators can move from the review table to themes without hunting the nav.

## Non-Functional Requirements

- One Alembic migration (`0004`) for `review_insight_snapshots`.
- No new dependencies. Gemini via existing `gemini.generate`. No live Gemini
  or GitHub in tests.
- Keyboard accessible; WCAG AA; no emojis in new UI copy.
- Analyze is a single Gemini call (not a worker job). Cap 50 new cards.

## Sad Paths & Error States

- Unauthenticated: 401.
- Repo not in the user's workspace: 404.
- Missing/invalid repo: 422.
- `GEMINI_API_KEY` missing: 503 (existing `NotConfiguredError` mapping).
- Gemini failure or unreadable JSON: 502, snapshot unchanged.
- GET/POST error on the page: `ErrorState` with retry; failed analyze: toast.

## Edge Cases

- First run (no snapshot): all reviews up to the cap, oldest first.
- Pending over 50: analyze the next 50; remaining stay pending for the next
  click.
- Rebuild with more than 50 reviews: newest 50 only; older ones are outside
  this snapshot until a later incremental run cannot see them (accepted for
  v1; regenerate is the escape hatch).
- Switching repos reloads GET for that repo.
- Themes with no valid example review ids after sanitizing are dropped.

## Acceptance Criteria

- An operator can open Insights, select a repo, see how many new ReviewPilot
  comments would be analyzed, run Analyze, and read themes with links back to
  reviews.
- A second Analyze with no new reviews does not call Gemini.
- After new reviews exist, Analyze uses the previous snapshot plus those new
  reviews (unit-tested via the user payload, with Gemini mocked).
- Rebuild ignores the previous snapshot.
- Another user's repo is 404.
- `ruff`, `pytest`, `npm run lint`, `npm run typecheck`, and `npm test` pass.

## Out of Scope

- Analyzing GitHub human comments (only stored ReviewPilot reviews).
- Auto-run after every `@review`.
- Org-wide multi-repo insights.
- Feeding themes back into the PR review prompt.
- Snapshot version history UI (only the latest snapshot is shown).
