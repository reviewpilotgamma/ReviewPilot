# Replace "Helpful rate" KPI with "Lines reviewed" — Specification

## Overview

The dashboard's fourth KPI card, **Helpful rate**, usually shows "No data yet" because developers rarely rate reviews. Replace it with **Lines reviewed**: the total number of diff lines ReviewPilot reviewed in the selected repos and period, read from `PRReview.lines_reviewed`. The review feedback feature (Yes/No buttons, counts, and insights filtering) is not changed.

## Functional Requirements

1. `GET /api/v1/metrics/summary` returns `lines_reviewed: int`, the sum of `PRReview.lines_reviewed` for reviews in the requested repos and inside the `days` window. This is the same scope `total_reviews` uses.
2. `helpful_rate` is removed from `MetricsSummary`, in both the backend schema and the frontend type.
3. The dashboard's fourth card is labelled **"Lines reviewed"** and uses the lucide `FileCode2` icon. The value uses thousands separators (`12,480`), and the hint reads "Diff lines read by the AI".

## Non-Functional Requirements

- The total comes from the existing aggregate query, so there is no extra round trip.
- No migration is needed.

## Sad Paths & Error States

- No repos or no reviews in the window: the API returns `lines_reviewed: 0` and the card shows `0`.
- The response is missing the field (old cached response or partial mock): the card shows "—" / "No data yet".
- The summary request fails: the existing ErrorState card appears, with no change.

## Edge Cases

- Reviews older than the window and reviews in other repos are excluded.
- Large totals are formatted for the user's locale.

## Acceptance Criteria

- Changing the period to 7, 30, or 90 days updates Lines reviewed to match the sum for that window.
- Helpful rate appears nowhere on the dashboard or in the summary API.
- Feedback buttons, feedback counts in the reviews table, and insights filtering behave exactly as before.
- Backend (ruff, pytest) and frontend (lint, typecheck, Vitest) gates pass.

## Out of Scope

- Removing or changing the review feedback feature.
- A lines-per-day trend line.
- Editing the original design docs in `artifacts/`.
