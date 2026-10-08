import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import Activity from "@/pages/Activity";
import History from "@/pages/History";
import { mockFetch, renderWithProviders } from "@/test/utils";
import type { Job, ReviewDetail, WebhookEvent } from "@/types/api";

const REVIEW: ReviewDetail = {
  id: 1,
  repo_full_name: "acme/api",
  pr_number: 7,
  pr_title: "Huge refactor",
  author: "bob",
  verdict: "warning",
  score: 6.5,
  lines_reviewed: 12,
  summary: "s",
  created_at: new Date().toISOString(),
  trigger: "auto",
  pr_url: "https://github.com/acme/api/pull/7",
  diff_truncated: false,
  feedback_counts: { helpful: 0, unhelpful: 0 },
  full_markdown: "### Executive Summary\nBig change.",
  requester: null,
  model: "gemini-3.5-flash-lite",
  review_context: null,
  my_feedback: null,
};

function job(overrides: Partial<Job>): Job {
  return {
    id: 1,
    kind: "review",
    status: "failed",
    attempts: 1,
    max_attempts: 3,
    last_error: null,
    error_code: null,
    review_id: null,
    next_run_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

function event(id: number, jobs: Job[]): WebhookEvent {
  return {
    id,
    delivery_id: `d-${id}`,
    event: "pull_request",
    action: "opened",
    repo: "acme/api",
    sender: "bob",
    payload_preview: "{}",
    status: "failed",
    error_message: jobs[0]?.last_error ?? null,
    created_at: new Date().toISOString(),
    jobs,
  };
}

async function openFirstEvent() {
  const rows = await screen.findAllByRole("row", { expanded: false });
  await userEvent.click(rows[0]!);
}

describe("Activity: GitHub diff size limit", () => {
  it("explains a diff too large for GitHub and keeps the raw error behind Details", async () => {
    const raw = "DiffTooLargeError: GitHub 406: Sorry, the diff exceeded the maximum number of lines (20000)";
    mockFetch({
      "GET /api/v1/webhooks/events": [event(1, [job({ last_error: raw, error_code: "diff_too_large" })])],
    });
    renderWithProviders(<Activity />);
    await openFirstEvent();

    expect(await screen.findByText(/Diff too large for GitHub\. Not reviewed\./)).toBeInTheDocument();
    const details = screen.getByText("Details");
    expect(screen.getByText(raw)).not.toBeVisible();
    await userEvent.click(details);
    expect(screen.getByText(raw)).toBeVisible();
  });

  it("shows other errors as before", async () => {
    const raw = "GeminiPermanentError: Gemini 400: bad request";
    mockFetch({ "GET /api/v1/webhooks/events": [event(2, [job({ last_error: raw })])] });
    renderWithProviders(<Activity />);
    await openFirstEvent();

    expect(await screen.findByText(raw)).toBeVisible();
    expect(screen.queryByText(/Diff too large for GitHub/)).not.toBeInTheDocument();
  });
});

describe("History: partially reviewed badge", () => {
  it("marks partial reviews in the table and the drawer only", async () => {
    const partial = { ...REVIEW, diff_truncated: true };
    const whole = { ...REVIEW, id: 2, pr_number: 8, pr_title: "Small fix" };
    mockFetch({
      "GET /api/v1/reviews": { items: [partial, whole], total: 2, page: 1, page_size: 20 },
      "GET /api/v1/reviews/1": partial,
    });
    renderWithProviders(<History />, { path: "/history?review=1" });

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Partially reviewed")).toBeInTheDocument();
    const [first, second] = screen.getAllByRole("row", { name: /Open review of PR/ });
    expect(within(first!).getByText("Partially reviewed")).toBeInTheDocument();
    expect(within(second!).queryByText("Partially reviewed")).not.toBeInTheDocument();
  });
});
