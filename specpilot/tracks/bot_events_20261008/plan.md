# Hide bot-sender events from the Activity feed — Plan

## Context snapshot

**Existing symbols that stay:** `is_bot_event`, `ingest` (still records bot events as `ignored`),
`WebhookEvent`, `useEvents`, `eventsApi.list`.

**Modified symbols:** `list_events` (`backend/app/api/webhooks.py`), `EventFilters` (TS type), `Activity` page.

**New symbols:** `BOT_SENDER_REASON` (dispatcher), the `include_bot` query parameter, migration `0007_purge_bot_events`.

## Hotspot map

| Area | File | Change |
| --- | --- | --- |
| Dispatcher | `backend/app/services/dispatcher.py` | Add `BOT_SENDER_REASON` and use it in `ingest` |
| API | `backend/app/api/webhooks.py` (`list_events`) | `include_bot: bool = False`; filter `coalesce(error_message, '') != BOT_SENDER_REASON` |
| Migration | `backend/alembic/versions/0007_purge_bot_events.py` | Delete `ignored` + `bot sender` rows; downgrade does nothing |
| BE tests | `backend/tests/test_webhooks.py`, `backend/tests/test_migrations.py` | Filter and purge cases |
| Types | `frontend/src/types/api.ts` (`EventFilters`) | Add `include_bot?: boolean` |
| Page | `frontend/src/pages/Activity.tsx` | `showBot` state, checkbox, pass through `filters`, reset paging |
| FE tests | `frontend/src/pages/pages.test.tsx` | Checkbox sends `include_bot` |
| Docs | `README.md` | Note that bot events are hidden in Activity by default |

## Phase 1: Backend

- [x] **1.1 API filter.** `86aa700` Add `BOT_SENDER_REASON`, the `include_bot` parameter, and the NULL-safe filter. Tests: hidden by default, shown with `include_bot=true`, human ignores and NULL-message events still listed. Gate: `ruff check .`, `pytest`.
- [x] **1.2 Purge migration.** `914fb55` Add `0007_purge_bot_events` deleting `status = 'ignored' AND error_message = 'bot sender'`. Test that only bot rows are removed. Gate: `ruff check .`, `pytest`.

## Phase 2: Frontend and docs

- [~] **2.1 Show bot events checkbox.** Add `include_bot` to `EventFilters`, a `showBot` checkbox to Activity (reset paging on change). Vitest case for the request param. Gate: `npm run lint`, `npm run typecheck`, `npm test`.
- [ ] **2.2 Docs.** README note on the Activity default.
