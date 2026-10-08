# ReviewPilot artifacts

Product and design documents for ReviewPilot. Last checked against the code on 8 October 2026.

## Current

Read these to understand the product and the system as it runs today.

| Document | What it answers | Audience |
| --- | --- | --- |
| [REQUIREMENTS.md](REQUIREMENTS.md) | What must ReviewPilot do, how do we judge the MVP, and what is done? | Panel, sponsors, engineering |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Why the product exists, and how the running system is built: pipeline, auth, data, config, gaps | Panel, engineering |
| [API.md](API.md) | Every backend endpoint with its auth level, inputs and response | Engineering |
| [TODO.md](TODO.md) | The original backlog, with the status of each item | Team |

## Historical

Kept for design rationale. Each one opens with a note that explains what has changed since.

| Document | What it is |
| --- | --- |
| [implementation.md](implementation.md) | The build plan the current code was built from, with a "Changes since this plan" table |
| [Application-Prompt.md](Application-Prompt.md) | The brief that analyzed the original PoC and specified the rebuild |

## Elsewhere

| Where | What |
| --- | --- |
| [`../README.md`](../README.md) | GitHub App registration, local setup, tests, deployment notes |
| [`../specpilot/`](../specpilot/index.md) | Product context, tech stack, workflow and the per-feature tracks (spec + plan for each change) |

Word or PDF copies are not kept here, so the Markdown stays the single source. Export from the Markdown when a
panel needs a document file.
