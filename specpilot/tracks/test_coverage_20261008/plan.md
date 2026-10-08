# Plan: Raise test coverage above 95%

The user asked to proceed without approval pauses, so the phase checkpoints below are committed without waiting
for manual verification. The verification steps are listed for the user to run afterwards.

## Context Snapshot

**Existing symbols (tested through, not modified):**
- Backend: `app/services/documents.py`, `app/services/gemini.py`, `app/services/insights.py`, `app/main.py`
  (`lifespan`, SPA/static handlers), `app/api/github.py`, `app/api/webhooks.py`, `app/services/worker.py`,
  `app/services/reviewer.py`, `app/core/security.py`, `app/api/insights.py`, `app/api/settings.py`.
- Frontend: `pages/Settings.tsx`, `hooks/useSettings.ts`, `components/layout/Navbar.tsx`, `context/AuthContext.tsx`,
  `context/WorkspaceContext.tsx`, `hooks/useReviews.ts`, `components/onboarding/InstallAppGate.tsx`,
  `components/ui/States.tsx`, `components/ui/Table.tsx`, `lib/rules.ts`, `pages/{Dashboard,History,Activity,Insights,Rules}.tsx`.
- Test helpers: `frontend/src/test/utils.tsx` (`mockFetch`, `renderWithProviders`), `backend/tests/conftest.py`.

**New symbols:**
- `frontend/src/pages/settings.test.tsx`, `frontend/src/context/context.test.tsx`, `frontend/src/pages/coverage.test.tsx`
  (page branch gaps), `frontend/src/components/layout/layout.test.tsx`.
- `backend/tests/test_coverage_gaps.py` and topic files as needed (`test_gemini.py`, `test_documents_service.py`, `test_main.py`).
- `npm run coverage` script.

**Modified symbols:**
- `frontend/vite.config.ts` (`test.coverage`), `frontend/package.json` (devDependency + script).
- `backend/pyproject.toml` (`[tool.coverage.*]`).
- `README.md` (testing section).

## Phase 1: Coverage tooling [checkpoint: 529ab72]

- [x] Task 1.1 [529ab72]: Frontend coverage provider and thresholds
  - Add `@vitest/coverage-v8@2.1.9` as a devDependency and add `"coverage": "vitest run --coverage"`.
  - In `vite.config.ts` `test.coverage`, set provider `v8`, include `src/**`, exclude `src/**/*.test.*`,
    `src/test/**`, `src/main.tsx`, `src/vite-env.d.ts`, `src/types/**`, and set thresholds `lines: 95` and `statements: 95`.
  - Record the new dev tool in `specpilot/tech-stack.md` (Tooling).
- [x] Task 1.2 [529ab72]: Backend coverage config
  - In `pyproject.toml`, add `[tool.coverage.run] source = ["app"]` and `[tool.coverage.report] fail_under = 95`,
    `show_missing = true`, `skip_covered = true`.

## Phase 2: Frontend tests [checkpoint: 3f2114d]

- [x] Task 2.1 [b0aed04]: Settings page + `useSettings` (load, edit, validate, save, error toast, replies config).
- [x] Task 2.2 [7bf100f]: Contexts and layout: `AuthContext` (load me, signIn, logout, 401), `WorkspaceContext`, `Navbar`
  (menu, logout), `ProtectedRoute`, `InstallAppGate`, `States`, `Table`, `lib/rules.ts`, `useReviews`.
- [x] Task 2.3 [3f2114d]: Page branch gaps: Dashboard, History, Activity, Insights, Rules, Login, plus the remaining UI
  components until frontend lines and statements are ≥ 95%.

### Phase 2 notes

- Frontend: 72 → 129 tests; statements/lines 81.91% → 98.13% (after excluding `main.tsx` and type-only files).
- Bug fixed: `InstallAppGate` Refresh left an unhandled promise rejection with no feedback when GitHub failed.
  It now shows the error in a toast.
- Also added `coverage` to the ESLint ignores so the generated HTML report does not produce lint warnings.

## Phase 3: Backend tests [checkpoint: 5673b31]

- [x] Task 3.1 [680d7de]: `services/documents.py`, `services/gemini.py`, and `services/insights.py` error and edge branches (respx).
- [x] Task 3.2 [5673b31]: `main.py` (lifespan/static handlers), `api/github.py`, `api/webhooks.py`, `api/insights.py`,
  `api/settings.py`, `core/security.py`, `services/worker.py`, `services/reviewer.py`, and smaller gaps until
  backend coverage is ≥ 97%.

### Phase 3 notes

- Backend: 383 → 453 passed (9 opt-in `live` tests still skipped); coverage 95.38% → 97.91%.
- New files: `test_gemini.py`, `test_documents_service.py`, `test_insights_service.py`, `test_main.py`; extended
  `test_webhooks.py` (non-object payloads, installation events, repo/before_id filters, admin view) and
  `test_security.py` (password hashing, ephemeral dev secrets).
- Bug fixed: unhandled 500 responses returned `"request_id": "-"` because Starlette's outermost error handler runs
  after `request_id_middleware` resets the context var. The middleware now also stores the id on `request.state`,
  and the handler uses it for the log line, the body, and an `X-Request-ID` header.
- The local `backend/venv` was missing `pypdf` (declared in `requirements.txt`); it was installed so PDF tests run.
- `insights.py:265` and `:305` look unreachable (incremental batches only hold reviews newer than the watermark,
  and rebuilds pass no previous snapshot). They were left alone because removing code is out of scope.

## Phase 4: Documentation

- [ ] Task 4.1: README testing section lists `pytest --cov` and `npm run coverage` and the 95% floor.

## Manual Verification

1. `cd backend && pytest --cov`: all tests pass and the total is ≥ 95%.
2. `cd frontend && npm run coverage`: all tests pass and the thresholds hold.
3. `ruff check .`, `npm run lint`, and `npm run typecheck` are clean.
