# Follow-up reviews after new pushes — Plan

## Context snapshot

**Existing symbols reused:** `plan_jobs`, `load_rule_settings`, `handle_review`, `assemble_comment`, `_merge_reviews`, `fallback_merge`, `review_parser._section`, `_installation_request`, `PRReview.github_comment_id`.

**New symbols:** `get_compare_files`, `FOLLOWUP_DIRECTIVE`, `FOLLOWUP_BANNER`, `build_previous_review_block`, `PRReview.head_sha`, `PRReview.previous_review_id`, migration `0008_review_followups`.

**Modified symbols:** `PullRequest`, `build_pr_context`, `build_merge_content`, `MERGED_SECTIONS`, `OPTIONAL_SECTIONS`, `ReviewListItem`, `ReviewDrawer`, History list.

## Tasks

### Phase 1: Data and GitHub
- [x] **1.1 Migration and model.** `83ef680`
  - `backend/alembic/versions/0008_review_followups.py` adds `pr_reviews.head_sha` (String 40, nullable) and
    `previous_review_id` (Integer, nullable, FK to `pr_reviews.id` with `ON DELETE SET NULL`), using
    `batch_alter_table` as `0005` does for SQLite.
  - Update `backend/app/models/pr_review.py`, and add `head_sha` and `previous_review_id` to `ReviewListItem` in
    `backend/app/schemas/reviews.py`.
  - Test: upgrade and downgrade, following `tests/test_migration_credential_auth.py`.
- [x] **1.2 GitHub client** `e077819` in `backend/app/services/github_app.py`:
  - Add `head_sha` to `PullRequest` (from `head.sha`).
  - Add `get_compare_files(installation_id, owner, repo, base_sha, head_sha) -> list[tuple[str, int, int]] | None`,
    which calls `GET /repos/{o}/{r}/compare/{base}...{head}` through `_installation_request` and returns `None`
    on a 404 or 422.
  - respx tests in `tests/test_github_app.py`.

### Phase 2: Triggers
- [x] **2.1 Dispatcher** `b794b9c` in `backend/app/services/dispatcher.py` `plan_jobs`:
  - Add a `pull_request` + `synchronize` branch. When `load_rule_settings(...).review_mode == "auto"`, queue
    `JobSpec("review", {...base, "trigger": "push", "requester": None})`.
  - Skip with `ignore_reason="review already queued"` when a queued review `Job` for the same owner, repo and PR
    exists (check `json.loads(Job.payload)` on queued review jobs).
  - On-demand mode: `ignore_reason="on-demand mode"`.
  - Tests in `tests/test_dispatcher.py`, with a new fixture `tests/fixtures/pull_request_synchronize.json`.

### Phase 3: Follow-up review
- [x] **3.1 Prompt** `01de1d2` in `backend/app/services/prompts.py`:
  - `FOLLOWUP_DIRECTIVE`: the Follow-up Status section and its rules (no severity tags; Architectural Findings
    lists current issues only).
  - `build_previous_review_block(prev_markdown, sha, verdict, score, changed_files)`: takes the previous review's
    Architectural Findings and Recommendations through `review_parser._section`, caps them at 6,000 characters,
    and wraps them as UNTRUSTED.
  - `build_pr_context(..., previous=...)` puts the block before `Diff:`.
  - `build_merge_content(..., previous=...)` does the same for large PRs.
- [x] **3.2 Reviewer** `6410453` in `backend/app/services/reviewer.py` `handle_review`:
  - Load the previous review: the latest `PRReview` for the repo and PR with `github_comment_id` set.
  - Decide whether this is a follow-up (requirement 2). If so, call `gh.get_compare_files`, add
    `FOLLOWUP_DIRECTIVE` to the system prompt, and pass `previous` to the single-pass context or to
    `_merge_reviews`.
  - `assemble_comment` gets a `followup` argument that swaps the banner to `FOLLOWUP_BANNER`, adds the
    "Follow-up to…" line, and adds the unavailable note when the code-joined fallback was used.
  - Save `head_sha` and `previous_review_id` on the new `PRReview`.
  - Add "Follow-up Status" to `OPTIONAL_SECTIONS` and `MERGED_SECTIONS`, right after the summary.
- [x] **3.3 Tests:** `95f5acf`
  - `tests/test_reviewer.py`: a follow-up posts a new comment with the follow-up banner, the context has the
    previous findings and changed files, a compare 404 still works, the same head sha gives a full review, and
    `head_sha` and `previous_review_id` are stored.
  - `tests/test_batched_review.py`: only the merge gets the previous review, and the fallback shows the note.
  - `tests/e2e/test_review_flows.py`: open, push, follow-up, using the harness (`add_pr`, `comments_for`).

### Phase 4: Dashboard
- [x] **4.1** `ae0282e` Add `head_sha?` and `previous_review_id?` to `frontend/src/types/api.ts`.
- [x] **4.2** `ae0282e` `frontend/src/components/reviews/ReviewDrawer.tsx` shows the trigger text for `push` and follow-ups,
  plus the "Previous review" link.
- [x] **4.3** `ae0282e` `frontend/src/pages/History.tsx` shows a "Follow-up" badge.
- [x] **4.4** `ae0282e` Vitest cases in `frontend/src/pages/pages.test.tsx`.
- [~] **4.5** Update the README's PR trigger table: push in auto mode, and `@review` after a push.

### Phase 5: Live verification
- [ ] **5.1** In the `ReviewPilot-demo` worktree, branch `demo/followup` from `demo/base`.
  - First commit: add an endpoint with two clear issues, an `httpx` call without a timeout and a hardcoded
    secret.
  - Open a PR against `demo/base` with a neutral description. Wait for the first review.
  - Push a second commit that fixes the timeout, keeps the secret and adds a new issue (an unbounded query).
  - The repo is in auto mode, so the push should trigger a follow-up as a **new** comment showing Fixed (timeout),
    Still open (secret) and New (unbounded query).
  - Then comment `@review` to confirm the comment-triggered follow-up. Record the results in `plan.md`.

## Quality gates (per task, per `specpilot/workflow.md`)
- Backend: `ruff check .` and `pytest`. Frontend: `npm run lint`, `npm run typecheck`, `npm test`.
- One conventional commit per task on `feature/credential-auth`, with the SHA recorded in `plan.md`.
- Commits leave out the user's unrelated `README.md` sqlite-backup edit and the `lines_kpi` plan edit (README
  hunks are staged selectively).
