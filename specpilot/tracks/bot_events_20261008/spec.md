# Hide bot-sender events from the Activity feed — Specification

## Overview

Every PR review posts a comment. GitHub echoes that comment back as `issue_comment.created`, which the
dispatcher stores as `ignored` with `error_message = "bot sender"`. The Activity feed then shows a grey
"ignored" row for every PR, which reads like a failure. Hide these events by default, keep them viewable on
demand, and delete the ones already stored.

## Functional Requirements

1. `GET /webhooks/events` excludes events whose `error_message` is `bot sender` by default.
2. A new query parameter, `include_bot=true`, includes them.
3. The Activity page has a **Show bot events** checkbox next to the filters, off by default. Toggling it
   resets paging and refetches.
4. Human ignores (`no trigger`, `not a pull request`, and so on) stay visible.
5. Bot events are still recorded and ignored. Bot-loop prevention is unchanged.
6. Migration `0007` deletes the existing `ignored` + `bot sender` rows. They have no jobs.

## Non-Functional Requirements

- "Load more" pagination works with the filter on.
- The `bot sender` reason lives in one constant (`BOT_SENDER_REASON`).

## Sad Paths & Error States

- Events with a NULL `error_message` must not be dropped by the filter (NULL-safe comparison).

## Edge Cases

- A feed that only contains bot events shows the standard empty state.
- `include_bot` combines with the `status` and `repo` filters.

## Acceptance Criteria

- The default feed shows no `bot sender` rows. With the checkbox on, they appear.
- After `alembic upgrade head`, the historic bot rows are gone and every other event is kept.
- Tests cover the API filter, the migration's delete, and the checkbox.

## Out of Scope

- Not storing bot events at all.
- Time-based retention or pruning of events.
- Relabelling status badges.
