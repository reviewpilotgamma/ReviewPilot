# Wider spacing in the review verdict line — Specification

## Overview

The line `**Verdict:** … · **Health score:** … · **Lines reviewed:** …` uses runs of plain spaces, which Markdown
collapses to one, so the items look cramped. Use em-space entities (`&emsp;`) around the separators.

## Functional Requirements

1. The verdict line separator becomes `&emsp;·&emsp;` in the review comment.
2. The Landing page sample uses the same separator.

## Non-Functional Requirements

- Renders on GitHub, in GitHub notification emails, and in the dashboard (`react-markdown` decodes entities).

## Sad Paths & Error States

- None.

## Edge Cases

- Already-posted and stored reviews keep the old spacing.

## Acceptance Criteria

- New review comments show visibly wider gaps between the three items.
- A reviewer test asserts the new separator.

## Out of Scope

- Changing the line's content, order or emoji.
