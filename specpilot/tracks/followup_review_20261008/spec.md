# Follow-up reviews after new pushes — Specification

## Overview

ReviewPilot reviews a PR once: when it's opened (auto mode) or when someone comments `@review`. When the author
pushes fixes, nothing checks whether the findings were actually fixed. A second `@review` today runs a fresh
review that knows nothing about the first one.

Goal: after new commits, ReviewPilot posts a **new** "Follow-up review" comment. It compares the updated code
against the previous review and reports what was **Fixed**, what is **Still open**, and what is **New**. Earlier
comments are never edited, so the PR keeps a full review history.

## Functional Requirements
1. **Triggers**
   - **Auto mode:** `pull_request.synchronize` (a new push) queues a review job with `trigger="push"`. If a review
     job for the same PR is already **queued** (not yet running), the push is skipped, so a burst of pushes
     gives one follow-up.
   - **On-demand mode:** pushes do nothing; the author comments `@review [note]` as today.
   - **Either mode:** `@review` on a PR that already has a posted review runs a follow-up.
2. **When it is a follow-up:** the job finds the latest posted review for the same repo and PR. It's a follow-up
   when that review exists and its `head_sha` differs from the PR's current head, or is unknown for reviews made
   before this change. If the head commit hasn't changed, `@review` runs a normal full review, as today.
3. **What the AI receives**
   - The **full current diff**, as today, so "still open" is judged against the whole code.
   - The previous review's findings and recommendations (capped in size), its verdict and score, and its commit.
   - The list of files changed since that commit, from GitHub's compare API. If the compare fails, for example
     after a force-push, the list is left out.
4. **Comment format**: posted as a new comment.
   - The banner reads `## ReviewPilot Follow-up Review`, followed by a line like:
     `_Follow-up to the review of `abc1234` (🔴 Critical Risk, 3.5/10) · 3 files changed since_`
   - Then the usual verdict line, which describes the current code.
   - A new `### Follow-up Status` section comes right after Executive Summary:
     - **Fixed:** sub-bullets `**<finding title>** in `path`: what changed to fix it`
     - **Still open:** sub-bullets `**<finding title>** in `path`: what remains`
     - **New:** sub-bullets `**<finding title>** in `path`: what is new`
     - "None." under an empty label. No severity tags in this section.
   - Architectural Findings lists only issues in the current code (still open plus new), with severity tags, so
     the verdict and score describe the current state.
   - Scope Check, Recommendations and What Looks Solid work as before.
5. **Large PRs reviewed in parts:** each part is reviewed as normal, and only the merge step gets the previous
   review and the follow-up rules. If the merge falls back to joining the parts in code, the comment says:
   `> Follow-up status unavailable for this large PR; the findings below describe the current code.`
6. **Storage and dashboard**
   - `pr_reviews` gains `head_sha` and `previous_review_id`.
   - The review drawer shows "Follow-up after push" or "Follow-up requested by @x", with a link to the previous
     review (`/history?review=<id>`).
   - The History list shows a "Follow-up" badge.
7. The follow-up instructions are added in code, outside the editable golden prompt, so a custom template still
   gets follow-ups.

## Non-Functional Requirements
- Bot-loop protection is unchanged. The bot's own comments are still ignored (`is_bot_event`).
- The previous review is quoted PR content, so the prompt marks it as UNTRUSTED.
- A retried job still never calls the AI twice (existing `ctx.review_id` path).
- Follow-ups count as reviews in metrics, and their lines count toward "Lines reviewed". This is expected.

## Edge Cases
- A push to a closed PR is skipped, as today.
- Push before any review exists: auto mode runs a normal full review.
- The previous review has no Critical or Warning findings: Fixed and Still open are "None.", and New lists
  anything new.
- A diff with no reviewable files posts the existing empty-diff notice.

## Out of Scope
- Editing earlier comments.
- File-anchored comments.
- Skipping draft PRs.
- Debouncing by time (only coalescing while a job is queued).


## Sad Paths & Error States

- Compare API 404/422 (force-push): the changed-files list is omitted; the follow-up still runs.
- Merge call fails on a large PR: code-joined fallback with the "Follow-up status unavailable" note.

## Acceptance Criteria

- A push in auto mode, or `@review` after a push, posts a new comment headed `## ReviewPilot Follow-up Review` with Fixed / Still open / New.
- Earlier comments are untouched.
- `head_sha` and `previous_review_id` are stored; the dashboard shows the follow-up link and badge.
- Live demo PR shows the expected Fixed, Still open and New items.
