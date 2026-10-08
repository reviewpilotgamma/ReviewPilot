# Spec: Raise test coverage above 95%

## Overview

Coverage was measured on 2026-10-08 (branch `chore/test-coverage`, cut from `feature/credential-auth` at `5329b50`):

| Side | Tests | Line coverage | Notes |
| --- | --- | --- | --- |
| Backend (pytest + pytest-cov) | 383 passed, 9 skipped | 95.38% (157 of 3397 statements missed) | Just above the target, with no floor enforced |
| Frontend (Vitest) | 72 passed | 74.54% statements | No coverage provider was installed. `pages/Settings.tsx` and `hooks/useSettings.ts` have 0% |

This track adds tests until both sides clear 95% with some margin, and makes the test runners fail when coverage drops below 95%.

## Functional Requirements

1. Add `@vitest/coverage-v8` (pinned to the installed Vitest 2.1.x) and configure coverage in `frontend/vite.config.ts`.
   - Include `src/**`. Exclude test files, `src/test/**`, the `main.tsx` bootstrap, and type-only files (`vite-env.d.ts`, `types/**`).
   - Set thresholds of 95% for `lines` and `statements`.
   - Add an `npm run coverage` script.
2. Configure pytest-cov in `backend/pyproject.toml` (`[tool.coverage.run]` source `app`, `[tool.coverage.report]` `fail_under = 95`). Plain `pytest` stays fast; `pytest --cov` enforces the floor.
3. Backend tests that cover the largest gaps: `services/documents.py`, `services/gemini.py`, `services/insights.py`, `main.py`, `api/github.py`, `api/webhooks.py`, `services/worker.py`, `services/reviewer.py`, `core/security.py`, plus smaller gaps where they are cheap to cover.
4. Frontend tests for `pages/Settings.tsx` and `hooks/useSettings.ts` (currently untested), `Navbar`, `AuthContext`, `WorkspaceContext`, `useReviews`, `InstallAppGate`, `States`, `Table`, `lib/rules.ts`, and the uncovered branches in the Dashboard, History, Activity, Insights, and Rules pages.
5. Tests exercise behavior through the public surface (rendered UI, HTTP endpoints, service functions). They must not assert on implementation details.

## Non-Functional Requirements

- No live Gemini or GitHub calls. Use respx/mocked HTTP on the backend and `mockFetch` on the frontend, as `workflow.md` requires.
- No production code changes unless a test exposes a real bug. Any such fix is called out in `plan.md`.
- `ruff check .`, `npm run lint`, and `npm run typecheck` stay clean.
- The suite stays deterministic. Do not rely on sleeps or wall-clock time.

## Sad Paths & Error States

- New tests should prefer error branches: GitHub/Gemini HTTP failures, invalid uploads, invalid settings input, unauthenticated/forbidden access, and API errors in the UI (toasts and error states).

## Edge Cases

- Skipped backend tests (`live`, opt-in) stay skipped and do not count against the suite.
- Coverage thresholds must not make the plain `npm test` / `pytest` commands slower or fail when run without coverage.

## Acceptance Criteria

- [ ] Backend: `pytest --cov` passes with total line coverage ≥ 95% (target ≥ 97%) and `fail_under = 95` enforced.
- [ ] Frontend: `npm run coverage` passes with lines and statements ≥ 95% and thresholds enforced.
- [ ] All tests pass on both sides; lint and typecheck are clean.
- [ ] README documents the coverage commands.

## Out of Scope

- Raising branch coverage to 95%. Branch coverage is reported but not enforced.
- E2E browser tests.
- Refactoring production code to improve testability.
