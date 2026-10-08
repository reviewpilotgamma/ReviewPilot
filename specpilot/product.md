# Product

## Goal

ReviewPilot is an internal, self-hosted GitHub App. It gives every pull request a consistent first-pass
architectural review against rules the organization defines, so senior reviewers can spend their time on
high-risk decisions instead of repeating the same comments.

It does not replace Copilot, Cursor, or human approval. It is the **consistent first pass** and the
**memory** of how the organization reviews code.

## Target users

| Role | What they need |
| --- | --- |
| Senior / staff engineer | Fewer repetitive reviews; confidence that baseline checks ran |
| PR author | Clear architectural feedback directly on the PR |
| Engineering manager / quality lead | Trends, recurring issues, evidence that standards are applied |
| Platform / operator | Host the service, GitHub App, secrets, availability |

## Core problem

Engineering knowledge lives in senior reviewers, architecture decisions, repository rules, and product
requirements. It is not consistently applied, measured, or learned from at the point where code changes.

## Core capability: the AI review pipeline

1. A PR is raised, or someone comments `@review [focus note]`. The webhook lands on the service.
2. The pipeline fetches the PR's git diff. Large diffs are batched or chunked instead of being silently cut.
3. The diff is grounded in **that repository's custom data**: custom instructions, requirement documents
   (prompt or uploaded docs), and project-specific context. These inputs are parsed and processed into
   review context.
4. The LLM reviews the change against that grounded context.
5. The output is parsed into a structured review (score, verdict, findings), stored, and posted back to
   GitHub as a PR comment.

## First meaningful outcome (MVP)

On one real internal service:

1. `@review` (or auto mode) posts an architectural comment on a PR.
2. The comment reflects that repository's stored rules and data, not only the global prompt.
3. The review is stored and visible on the dashboard without demo seed data.
4. A reviewer can mark the review helpful or not helpful, and metrics update from real records.
5. Webhooks with invalid signatures are rejected, and bot-authored events never create comment loops.
6. The service runs on an internal or agreed host with org-controlled credentials.

## Out of scope (this phase)

- Multi-tenant SaaS, billing, public marketplace
- Auto-merge or required-status-check gating
- Org-wide multi-team analytics
- Jira / Azure DevOps as the system of record
- Line-level style or lint feedback, unless it creates an architectural or security risk

## Sources

- [`artifacts/REQUIREMENTS.md`](../artifacts/REQUIREMENTS.md)
- [`artifacts/ARCHITECTURE.md`](../artifacts/ARCHITECTURE.md)
- [`artifacts/API.md`](../artifacts/API.md)
- [`artifacts/implementation.md`](../artifacts/implementation.md) (original build plan)
