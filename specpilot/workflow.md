# Project Workflow

## Guiding Principles

1. **The Plan is the Source of Truth:** All work must be tracked in `plan.md`.
2. **The Tech Stack is Deliberate:** Changes to the tech stack must be documented in `tech-stack.md` *before* implementation.
3. **User Experience First:** Every decision should prioritize user experience and intuitive design.
4. **Non-Interactive & CI-Aware:** Prefer non-interactive commands. Use `CI=true` for watch-mode tools to ensure single execution.
5. **Branching:** Work on a feature branch and merge into `main` via pull request. Never commit directly to `main`.

## Task Workflow

All tasks follow a strict lifecycle:

### Standard Task Workflow

1. **Select Task:** Choose the next available task from `plan.md` in sequential order.
2. **Mark In Progress:** Before beginning work, edit `plan.md` and change the task from `[ ]` to `[~]`.
3. **Implement Feature:** Write the application code necessary to fulfill the task requirements, with tests.
4. **Run the Quality Gate:** Run the commands under *Daily Development* for each side (backend or frontend)
   the task touched. All of them must pass.
5. **Commit Code Changes:**
   - Stage all code changes related to the task.
   - Use a conventional commit message (e.g., `feat(pipeline): Chunk large diffs before review`).
   - Perform the commit.
6. **Record Task Commit SHA:** Update `plan.md`, change the status to `[x]`, and append the first 7
   characters of the commit hash. Include this plan update in the next task's commit or in the phase
   checkpoint commit.

### Phase Completion Verification and Checkpointing Protocol

**Trigger:** Executed immediately after a task completes a phase in `plan.md`.

1. **Announce Protocol Start:** Inform the user that the phase is complete.
2. **Propose Manual Verification Plan:** Generate a step-by-step plan for the user to verify the phase's goals (e.g., dev server commands, specific UI checks, a test `@review` on a sandbox PR).
3. **Await User Feedback:** Pause for explicit user confirmation ("Does this meet your expectations?").
4. **Create Checkpoint Commit:** Stage all changes, including `plan.md`, and commit (e.g., `specpilot(checkpoint): Checkpoint end of Phase X`).
5. **Record Phase Checkpoint SHA:** Update the phase heading in `plan.md` with `[checkpoint: <sha>]`. This edit is committed with the next task or checkpoint.

## Testing Rules

- Every new backend service or endpoint ships with pytest tests. Every new frontend component with logic
  ships with Vitest tests.
- AI pipeline and GitHub code is tested with mocked HTTP (respx) and fixtures. **No live Gemini or GitHub
  calls in tests.**
- Webhook signature verification, bot-loop prevention, and secret masking must keep test coverage.

## Quality Gates

Before marking any task complete, verify:

- [ ] Code follows the guidelines in `specpilot/code_styleguides/`.
- [ ] Documentation is updated if needed (README, `.env.example` for new settings).
- [ ] Types are enforced: TypeScript types on the frontend, type hints and Pydantic models on the backend.
- [ ] There are no lint or static analysis errors.
- [ ] No security vulnerabilities are introduced (no secrets in code, logs, or API responses).

## Development Commands

### Setup
```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env            # then fill in values
alembic upgrade head

# Frontend
cd frontend
npm install
```

### Daily Development
```bash
# Backend (from backend/)
uvicorn app.main:app --reload --port 8000
ruff check .
pytest

# Frontend (from frontend/)
npm run dev
npm run lint
npm run typecheck
npm test
```

## Definition of Done

A task is complete when:
1. All code is implemented to the specification.
2. The quality gate commands pass for every side the task touched.
3. Implementation notes are added to `plan.md`.
4. Changes are committed with a conventional commit message, and the SHA is recorded in `plan.md`.
