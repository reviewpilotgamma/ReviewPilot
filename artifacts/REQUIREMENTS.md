# ReviewPilot — Software Requirements Specification

| Field | Value |
| --- | --- |
| Document | Software Requirements Specification (SRS) |
| Product | ReviewPilot |
| Motto | Clearance to merge, not comment noise |
| Tagline | Architectural review for every pull request |
| Status | PoC in progress; MVP requirements for panel review |
| Audience | Evaluation panel, product sponsors, engineering |
| Companion | `ARCHITECTURE.md` (current system) |
| Date | 28 September 2026 |

This specification states **what ReviewPilot must do** for an internal engineering quality layer. It is written so a panel can judge intent, scope, and success without reading the code.

The architecture document describes **what is running today**. This document describes **what we are building toward**, and marks what the PoC already demonstrates.

---

## 1. Purpose

ReviewPilot is an internal, self-hosted GitHub App service. It applies **organization-defined** architectural and engineering checks at the pull request, so senior reviewers spend time on high-risk decisions rather than repeating the same comments.

It is not a replacement for Copilot, Cursor, or human review. Those tools help an individual investigate a change. ReviewPilot is the **consistent first pass** and the **memory** of how we review.

**MVP question this product must answer**

> On a real internal service, can we catch meaningful issues before human review, reduce repetitive reviewer effort, and turn review history into actionable engineering knowledge?

---

## 2. Problem

Engineering knowledge lives in senior reviewers, architecture decisions, repository rules, and product requirements. Every PR currently depends on a person to assemble that context.

| Gap | Effect |
| --- | --- |
| Consistency | Review quality varies with who reviews and what they remember. |
| Coverage | Seniors spend time on repetitive issues; architectural and requirement-level risks can still slip through. |
| Learning | Feedback stays trapped in individual PRs instead of becoming measurable organizational knowledge. |

**Problem statement.** Our engineering knowledge exists, but it is not consistently applied, measured, or learned from at the point where code changes happen.

---

## 3. Goals

| ID | Goal | How we will know |
| --- | --- | --- |
| G1 | Apply the same baseline checks to every in-scope PR | Review comments follow a defined structure and org rules |
| G2 | Reduce repetitive senior review work | Reviewers report fewer nits; first-pass comments cover known patterns |
| G3 | Treat requirements as ground truth (MVP+) | Implementation is checked against stated requirement text, not only “does the code look right” |
| G4 | Retain reviews as organizational knowledge | History, verdicts, and feedback are stored and visible |
| G5 | Show quality trends | Dashboard reports volume, pass/warn/critical mix, and recurring themes |
| G6 | Remain internal and customizable | Self-hosted; rules and prompts owned by the organization |

---

## 4. Scope

### 4.1 In scope — proof of concept (current)

Demonstrate a self-hosted pipeline: GitHub webhook → App authentication → comment on the PR → optional Gemini architectural review on `@review` → operator dashboard.

### 4.2 In scope — MVP (what we must prove next)

| Theme | MVP requirement |
| --- | --- |
| First-pass review | Organization-defined checks on PRs for an agreed internal service |
| Own rules | Per-repository (or org) instructions actually used in the review |
| Persistence | Live reviews stored, not only posted to GitHub |
| Feedback loop | Reviewer can mark a review helpful / not helpful |
| Dashboard | Metrics and history from **real** reviews (not only demo seed data) |
| Internal hosting | Runnable as a single service on an internal host |

### 4.3 Out of scope (this phase)

- Replacing GitHub Copilot, Cursor, or the human approver
- Multi-tenant SaaS, billing, or public marketplace
- Automatic merge, required status checks as a GitHub “required review” gate (nice later; not MVP)
- Full multi-repo org analytics across many teams (MVP is one real internal service)
- Formal requirements-management integration (Jira/Azure DevOps as system of record) — **Could** after MVP
- Line-by-line style/lint (unless it creates an architectural or security risk)

---

## 5. Users and stakeholders

| Role | Interest |
| --- | --- |
| Senior / staff engineer | Fewer repetitive reviews; confidence that baseline checks ran |
| PR author | Clear, architectural feedback on the PR itself |
| Engineering manager / quality lead | Trends, recurring issues, evidence that standards are applied |
| Platform / operator | Host the service, GitHub App, secrets, availability |
| Panel / sponsor | Fit to problem, honesty of PoC vs MVP, path to a service |

There is **no end-user login** in the PoC. The operator and anyone who can reach the host share the dashboard. MVP **should** add access control for an internal deployment.

---

## 6. Definitions of priority

| Priority | Meaning |
| --- | --- |
| **Must** | Required to call the MVP successful |
| **Should** | Expected in MVP if time allows; otherwise first increment after MVP |
| **Could** | Valuable later; not required to answer the MVP question |
| **Won’t (this phase)** | Explicitly deferred |

**Status in PoC** is noted per requirement: *Done*, *Partial*, or *Not started*.

---

## 7. Functional requirements

### 7.1 GitHub integration

| ID | Requirement | Priority | PoC |
| --- | --- | --- | --- |
| FR-G1 | The system shall authenticate as a GitHub App (JWT + installation access token). | Must | Done |
| FR-G2 | The system shall accept GitHub webhooks and reject payloads that fail HMAC-SHA256 signature verification. | Must | Done |
| FR-G3 | The system shall ignore events originating from bots to avoid comment loops. | Must | Done |
| FR-G4 | On pull request opened, the system shall post a configurable acknowledgement comment. | Should | Done |
| FR-G5 | On a PR comment containing `@review`, the system shall produce an architectural review and post it on the PR. | Must | Done |
| FR-G6 | `@review` on a non-PR issue shall not run a review; the system shall explain that the command is PR-only. | Must | Done |
| FR-G7 | The operator shall be able to install the App and see a valid install URL from the running service. | Must | Done |
| FR-G8 | The system should list installations, repositories, and open PRs for operator workflows. | Could | Partial (API exists; dashboard unused) |

### 7.2 Review quality (the product)

| ID | Requirement | Priority | PoC |
| --- | --- | --- | --- |
| FR-R1 | Reviews shall focus on architecture, boundaries, failure modes, security trust boundaries, and maintainability—not formatting nits. | Must | Done (prompt) |
| FR-R2 | Reviews shall follow a consistent markdown structure (summary, findings with severity, recommendations, what looks solid). | Must | Done (prompt) |
| FR-R3 | The reviewer shall use the PR unified diff (truncated if needed) plus title/description as input. | Must | Done |
| FR-R4 | Extra text after `@review` shall be treated as requester notes to the model. | Should | Done |
| FR-R5 | Stored repository rules (custom instructions, verbosity, review mode, security flag) shall be applied to the review. | Must | Not started (stored, not used) |
| FR-R6 | The system should support an auto mode (review on PR open) and an on-demand mode (`@review` only), per repository. | Should | Not started (flag stored only) |
| FR-R7 | The system should check the change against stated requirements (PR body, linked ticket text, or attached requirement snippet). | Should | Not started |
| FR-R8 | If the model or GitHub fetch fails, the system shall post a clear failure comment rather than failing silently. | Must | Partial |

### 7.3 Knowledge and dashboard

| ID | Requirement | Priority | PoC |
| --- | --- | --- | --- |
| FR-D1 | The system shall persist each completed review (repo, PR, author, summary, full markdown, verdict/score as available). | Must | Not started (seed data only) |
| FR-D2 | Operators shall browse review history and open a full write-up. | Must | Partial (UI + seed) |
| FR-D3 | Reviewers shall submit feedback (e.g. helpful / not helpful) on a stored review. | Must | Partial (API + UI; not tied to live reviews) |
| FR-D4 | The dashboard shall show workspace metrics derived from persisted reviews (volume, scores, pass rate, acceptance). | Must | Partial (computed from seed) |
| FR-D5 | The dashboard should surface recurring issue themes across PRs (learning). | Should | Not started |
| FR-D6 | Operators shall edit per-repo review rules from the dashboard. | Must | Partial (save works; not used in review) |
| FR-D7 | Operators shall see recent webhook activity for operations/debugging. | Should | Done (in-memory, lost on restart) |
| FR-D8 | Operators shall configure App secrets, model, and canned replies without editing files by hand. | Should | Partial (API exists; UI is mostly read-only) |

### 7.4 Service shape

| ID | Requirement | Priority | PoC |
| --- | --- | --- | --- |
| FR-S1 | The product shall run as a single deployable HTTP service (webhook + API + UI). | Must | Done |
| FR-S2 | The service shall expose a health check. | Must | Done (`GET /health`) |
| FR-S3 | Review work should be processed asynchronously so GitHub receives a timely webhook acknowledgement. | Must | Partial (in-process background task) |
| FR-S4 | Live review jobs should survive process restart (durable queue). | Could | Not started |
| FR-S5 | Dashboard and operator APIs shall require authentication in an internal deployment. | Should | Not started |

---

## 8. Non-functional requirements

| ID | Requirement | Priority | Notes |
| --- | --- | --- | --- |
| NFR-1 | **Hosting.** Deployable on an internal machine or VM; no mandatory public SaaS. | Must | Matches “built for internal use” |
| NFR-2 | **Secrets.** Webhook secret, App private key, and model API key shall not be returned in full via the UI. | Must | Masking exists; `.env` still writable from API |
| NFR-3 | **Integrity.** Webhook processing shall not proceed without a valid signature when a secret is configured. | Must | |
| NFR-4 | **Availability (MVP).** Suitable for a pilot on one service, not a 24/7 multi-team SLA. | Should | State honestly to the panel |
| NFR-5 | **Latency.** Webhook HTTP response shall return quickly (ack then work). Review comment may take up to ~90s for the model. | Must | |
| NFR-6 | **Observability.** Failures in GitHub or model calls shall be logged. | Must | |
| NFR-7 | **Data residency.** Review text and diffs stay on the org host except calls to GitHub and the configured model API. | Must | Call out Gemini as an external processor |
| NFR-8 | **Usability.** Primary actions stay on GitHub (`@review`) and a simple dashboard. | Must | |
| NFR-9 | **Maintainability.** Clear module boundaries: ingress, GitHub client, reviewer, store, UI. | Should | See architecture doc |

---

## 9. Constraints and assumptions

1. GitHub is the source of PRs and comments for this phase.
2. A registered GitHub App exists with permission to read PRs and write issue/PR comments, subscribed to `issue_comment` and `pull_request`.
3. The PoC uses Google Gemini for generation; the design shall not assume the model cannot be swapped later.
4. Pilot success is measured on **one real internal service**, not organization-wide rollout.
5. Demo seed data in the database is for pitch/demo only; MVP acceptance uses live data.

---

## 10. Acceptance criteria (MVP)

The MVP is accepted when all of the following are true for the chosen internal service:

1. A PR on that service can receive a ReviewPilot architectural comment via `@review` (or auto mode if enabled).
2. The comment reflects **that repository’s** stored rules, not only the global prompt.
3. The same review is stored and visible on the dashboard without relying on dummy seed rows.
4. A reviewer can record feedback on that review; metrics update from real records.
5. Webhooks with an invalid signature are rejected.
6. Bot-authored events do not create a comment loop.
7. The service is run internally (or on an agreed internal-like host) with org-controlled credentials.

**PoC demo (panel today)** may show: webhook path, `@review` on GitHub, dashboard with sample history, and the product story above. That **does not** by itself satisfy MVP items 2–4.

---

## 11. Success metrics (directional)

These are for the pilot, not contractual SLAs:

| Metric | Intent |
| --- | --- |
| Issues caught before human review | Meaningful architectural or requirement findings in first-pass comments |
| Repetitive comment reduction | Seniors report less time on known nits |
| Feedback rate | Share of stored reviews marked helpful |
| Recurring patterns | Same class of finding appearing across PRs (learning) |

Exact numeric targets should be set with the pilot team after a baseline week of reviews.

---

## 12. Requirements traceability (summary)

| Product claim | Primary requirements |
| --- | --- |
| Consistent first-pass review | FR-R1, FR-R2, FR-R5, FR-R6 |
| Own rules / internal hosting | FR-D6, FR-S1, NFR-1, NFR-7 |
| Requirements as ground truth | FR-R7 |
| Learns from reviews | FR-D1, FR-D3, FR-D5 |
| Quality trends | FR-D4 |
| Works alongside existing tools | Scope §4.3; FR-G5 (comment on GitHub, no replacement of IDE tools) |
| Scales senior expertise | FR-R5, FR-D6 |

---

## 13. Glossary

| Term | Meaning |
| --- | --- |
| GitHub App | Integration that acts as a bot with installation tokens per org/account |
| Installation | One App install on a user or organization |
| First-pass review | Automated organizational check before deep human review |
| PoC | Current starter codebase proving the pipeline |
| MVP | Smallest product that answers the MVP question on a real internal service |

---

*ReviewPilot — Clearance to merge, not comment noise.*
