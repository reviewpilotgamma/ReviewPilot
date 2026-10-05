# CLAUDE.md

This project uses the `specpilot` plugin as the process manager for spec-driven development.
Project context lives in [`specpilot/index.md`](specpilot/index.md).

Invoke it in four ways:

1. `I want to setup specpilot`
   Run setup only. Create project-management artifacts. Do not create a new track.
   Note: this is not the same as "scaffold this project".
2. Ordinary feature, bug, or task requests, or `specpilot plan <description>`
   Run planning. Create or refine the track, spec, and implementation plan.
3. `Implement this track <track_id>`
   Run track implementation for the specified track.
4. `I want to customize the workflow`
   Update `specpilot/workflow.md`.

Expectations:

- Treat ordinary feature, bug, and task requests as planning requests by default.
- Keep setup separate from planning, and workflow customization separate from track implementation.
- Point implementation requests at a concrete `track_id` whenever one is available.
- `SPECPILOT_API_KEY` lives only in the repo-root `.env`, which SpecPilot reads. Application config lives in `backend/.env`.
