# PR description vs diff scope check — Specification

## Overview

Every review gets a **Scope Check** section that compares the PR description with the actual diff. It flags
changes the description does not mention and things the description promises that the diff does not contain.
It is informational and never changes the verdict or score.

## Functional Requirements

1. New `### Scope Check` section right after Executive Summary:
   - **Matches description:** Yes / Partly / No
   - **Unexpected changes:** sub-bullets `path`: what changed and why it looks unrelated (or "None.")
   - **Described but not found:** what the description promises that the diff lacks (or "None.")
2. Empty or too-vague description: a single bullet, **No description to compare against**, suggesting the author add one.
3. Scope differences never add a finding or change the verdict or score. Unexpected code is still reviewed normally.
4. Lockfiles and generated files are never flagged as unexpected.
5. The single-pass review context lists all changed files, so files cut from a truncated diff are not reported
   as "described but not found".
6. Batched reviews: each batch reports only unexpected changes in its own diff and omits "Described but not
   found"; the merge step receives the description and writes one Scope Check. The code-joined fallback merge
   keeps the batches' Scope Check sections.
7. Always on; lives in the default golden prompt.

## Non-Functional Requirements

- The parser is unaffected: Scope Check never uses the **Critical** / **Warning** / **Passed** tags, and
  severities are counted only under Architectural Findings.

## Sad Paths & Error States

- Merge call fails: the fallback join keeps Scope Check per part.

## Edge Cases

- Description truncated at 4,000 characters, as today.
- Old reviews have no Scope Check.
- A custom golden prompt saved later needs its own Scope Check text.

## Acceptance Criteria

- Default and merge prompts contain the Scope Check rules; the single-pass context lists changed files; the
  merge input includes the description; the fallback keeps Scope Check; the landing sample shows it.
- Live check on two demo PRs: one whose description matches the diff (Matches: Yes) and one with an
  undescribed extra change (flagged under Unexpected changes, verdict unaffected by it).

## Out of Scope

- Per-repo toggle, score impact, non-LLM comparison.
