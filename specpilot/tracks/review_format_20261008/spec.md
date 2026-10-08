# Structured, highlighted review comments — Specification

## Overview

Review comments (on GitHub and in GitHub's notification emails) are prose-heavy. Change the default golden
prompt so every section is bulleted, labels are bold, and every finding and recommendation names its exact file
path. Paths and code use inline code, which gets a grey background on GitHub, in email and in the dashboard.

## Functional Requirements

1. **Executive Summary**: 2–3 bullets — **What it does**, **Overall risk**, optional **Main concern**.
2. **Architectural Findings**: `- **Critical** · **<title>**` (or **Warning** / **Passed**) with sub-bullets
   **File(s)**, **Problem**, **Impact**.
3. **Specific Recommendations**: `1. **<action>** in `path`` with 1–2 sub-bullets on how.
4. **What Looks Solid**: `- **<point>** in `path`: <why>`.
5. Paths, functions, classes, endpoints and config keys always in inline code. Paths copied exactly from the
   diff. No line numbers, no emoji.
6. The batch merge prompt carries the same format rules.

## Non-Functional Requirements

- Parser compatibility: severity tags stay exactly `**Critical**`, `**Warning**`, `**Passed**`; section headings
  and the `reviewpilot-meta` line are unchanged.
- Verbosity directives keep their `Be concise` / `Be detailed` openings.

## Sad Paths & Error States

- If the model ignores the format, parsing still works because headings, tags and meta are unchanged.

## Edge Cases

- A finding spanning several files lists them all on the **File(s)** line.
- No issues: a single **Passed** finding.
- Stored and already-posted reviews keep their old format.

## Acceptance Criteria

- Default and merge prompts contain the new format rules.
- The fixture review uses the new format; parser tests still count severities and extract the summary.
- Landing page sample shows the new layout.

## Out of Scope

- Coloured alert boxes, emoji, line numbers, file links.
- Custom golden prompts already saved (none exists today).
