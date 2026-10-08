# Remove the aeroplane emoji from the review banner — Specification

## Overview

Review comments open with `## ✈️ ReviewPilot Architectural Audit`. Drop the emoji so the banner reads
`## ReviewPilot Architectural Audit`.

## Functional Requirements

1. `BANNER` in `backend/app/services/reviewer.py` has no emoji.
2. The Landing page sample comment matches the new banner.

## Non-Functional Requirements

- No other comment text changes.

## Sad Paths & Error States

- None. No code matches on the banner text other than tests.

## Edge Cases

- Reviews already posted or stored keep their old banner.

## Acceptance Criteria

- New review comments start with `## ReviewPilot Architectural Audit`.
- Tests assert the new banner.

## Out of Scope

- Verdict emoji (🟢🟡🔴), ⚠️ notes, and the plan, welcome and error comments (user chose banner only).
- Rewriting stored reviews.
