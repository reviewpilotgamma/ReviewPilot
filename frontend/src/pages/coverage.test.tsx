import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "@/App";
import Activity from "@/pages/Activity";
import Dashboard from "@/pages/Dashboard";
import History from "@/pages/History";
import Insights from "@/pages/Insights";
import Rules from "@/pages/Rules";
import { promptFixture } from "@/test/prompt";
import { mockFetch, renderWithProviders, testUser } from "@/test/utils";
import type { InsightState, Job, MetricsSummary, Page, ReviewListItem, Rule, WebhookEvent } from "@/types/api";

function json(body: unknown, status: number) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** mockFetch, plus raw handlers (hanging or rejecting promises) for URLs containing a key. */
function mockFetchWith(routes: Parameters<typeof mockFetch>[0], raw: Record<string, () => Promise<Response>>) {
  const base = mockFetch(routes);
  const fn = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const hit = Object.keys(raw).find((key) => String(input).includes(key));
    return hit ? raw[hit]!() : base(input, init);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const APP_INFO = { configured: true, slug: "reviewpilot", name: "ReviewPilot", install_url: "", html_url: "" };

function review(id: number, overrides: Partial<ReviewListItem> = {}): ReviewListItem {
  return {
    id,
    repo_full_name: "acme/api",
    pr_number: id,
    pr_title: `PR ${id}`,
    author: "bob",
    verdict: "passed",
    score: 8,
    lines_reviewed: 10,
    summary: "s",
    created_at: "2026-10-08T00:00:00Z",
    trigger: "auto",
    pr_url: `https://github.com/acme/api/pull/${id}`,
    diff_truncated: false,
    feedback_counts: { helpful: 0, unhelpful: 0 },
    ...overrides,
  };
}

function summary(overrides: Partial<MetricsSummary> = {}): MetricsSummary {
  return {
    total_reviews: 1,
    avg_score: 8,
    pass_rate: 1,
    lines_reviewed: 10,
    verdict_counts: { passed: 1, warning: 0, critical: 0 },
    recent: [review(7)],
    ...overrides,
  };
}

describe("Dashboard", () => {
  it("explains a GitHub connect error from the URL once and removes it", async () => {
    mockFetch({
      "GET /api/v1/github/app": APP_INFO,
      "GET /api/v1/metrics/summary": summary(),
      "GET /api/v1/metrics/trend": [],
    });
    const { router } = renderWithProviders(<Dashboard />, { path: "/dashboard?github_error=state" });
    expect(await screen.findByText(/Connecting GitHub expired or was tampered with/)).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toBe(""));
  });

  it("falls back to a generic message for an unknown GitHub error", async () => {
    mockFetch({
      "GET /api/v1/github/app": APP_INFO,
      "GET /api/v1/metrics/summary": summary(),
      "GET /api/v1/metrics/trend": [],
    });
    renderWithProviders(<Dashboard />, { path: "/dashboard?github_error=weird" });
    expect(await screen.findByText("Could not connect GitHub, please try again.")).toBeInTheDocument();
  });

  it("offers a retry when installations fail to load", async () => {
    mockFetch({ "GET /api/v1/github/app": APP_INFO });
    const { workspace } = renderWithProviders(<Dashboard />, { workspace: { isError: true } });
    expect(await screen.findByText("Could not load your GitHub installations.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(workspace.refresh).toHaveBeenCalledTimes(1);
  });

  it("shows the install gate when the user has no installation", async () => {
    mockFetch({ "GET /api/v1/github/app": APP_INFO, "GET /api/v1/github/installations": [] });
    renderWithProviders(<Dashboard />, { workspace: { installations: [], repos: [] } });
    expect(await screen.findByText("Welcome to ReviewPilot")).toBeInTheDocument();
  });

  it("scopes metrics to the selected repo, draws the trend, switches period and opens a review", async () => {
    const fetch = mockFetch({
      "GET /api/v1/github/app": APP_INFO,
      "GET /api/v1/metrics/summary": summary(),
      "GET /api/v1/metrics/trend": [
        { date: "2026-10-07", reviews: 0, avg_score: null },
        { date: "2026-10-08", reviews: 3, avg_score: 7 },
      ],
    });
    const { router } = renderWithProviders(<Dashboard />, { workspace: { selectedRepo: "acme/api" } });

    expect(await screen.findByText("acme/api", { selector: "span" })).toBeInTheDocument();
    expect(await screen.findByText("Review volume")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("radio", { name: "7 days" }));
    await waitFor(() =>
      expect(fetch.mock.calls.some(([url]) => String(url).includes("/metrics/summary?repo=acme%2Fapi&days=7"))).toBe(
        true,
      ),
    );

    await userEvent.click(await screen.findByRole("row", { name: "Open review of PR #7" }));
    expect(router.state.location.pathname + router.state.location.search).toBe("/history?review=7");
  });

  it("shows an empty state before the first review and a retry when metrics fail", async () => {
    let fail = true;
    mockFetch({
      "GET /api/v1/github/app": APP_INFO,
      "GET /api/v1/metrics/summary": () =>
        fail ? json({ detail: "boom" }, 500) : summary({ total_reviews: 0, recent: [] }),
      "GET /api/v1/metrics/trend": [{ date: "2026-10-08", reviews: 0, avg_score: null }],
    });
    renderWithProviders(<Dashboard />);

    const alert = await screen.findByRole("alert");
    fail = false;
    await userEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No reviews yet")).toBeInTheDocument();
    expect(screen.queryByText("Review volume")).not.toBeInTheDocument();
  });
});

function reviewPage(items: ReviewListItem[], total = items.length, page = 1): Page<ReviewListItem> {
  return { items, total, page, page_size: 20 };
}

describe("History", () => {
  it("pages through results and opens a review from the table", async () => {
    const fetch = mockFetchWith(
      { "GET /api/v1/reviews": (url: URL) => reviewPage([review(Number(url.searchParams.get("page")) * 100)], 45) },
      { "/reviews/100": () => new Promise<Response>(() => undefined) },
    );
    const { router } = renderWithProviders(<History />, { path: "/history" });

    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
    expect(screen.getByText("45 reviews")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Page 2 of 3")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Previous" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => String(url).includes("page=2"))).toBe(true);

    await userEvent.click(await screen.findByRole("row", { name: "Open review of PR #100" }));
    await waitFor(() => expect(router.state.location.search).toContain("review=100"));
  });

  it("debounces author and search text into the URL and resets the page", async () => {
    mockFetch({ "GET /api/v1/reviews": reviewPage([review(1)], 1) });
    const { router } = renderWithProviders(<History />, { path: "/history?page=3&verdict=bogus" });

    await screen.findByText("1 review");
    await userEvent.type(screen.getByPlaceholderText("GitHub login"), " carol ");
    const param = (key: string) => new URLSearchParams(router.state.location.search).get(key);
    await waitFor(() => expect(param("author")).toBe("carol"), { timeout: 2000 });
    expect(param("page")).toBeNull();
    await userEvent.type(screen.getByPlaceholderText("e.g. payment retries"), "retries");
    await waitFor(() => expect(param("q")).toBe("retries"), { timeout: 2000 });

    await userEvent.selectOptions(screen.getByLabelText("Repository"), "acme/web");
    await waitFor(() => expect(param("repo")).toBe("acme/web"));
  });

  it("shows the plain empty state and a retry on error", async () => {
    let fail = true;
    mockFetch({ "GET /api/v1/reviews": () => (fail ? json({ detail: "boom" }, 500) : reviewPage([], 0)) });
    renderWithProviders(<History />, { path: "/history?review=abc" });

    const alert = await screen.findByRole("alert");
    fail = false;
    await userEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No reviews yet")).toBeInTheDocument();
    expect(screen.getByText("Reviews appear here once ReviewPilot audits a PR.")).toBeInTheDocument();
  });
});

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: 1,
    kind: "review",
    status: "done",
    attempts: 1,
    max_attempts: 3,
    last_error: null,
    error_code: null,
    review_id: 42,
    next_run_at: "2026-10-08T00:00:00Z",
    updated_at: "2026-10-08T00:00:00Z",
    ...overrides,
  } as Job;
}

function event(id: number, overrides: Partial<WebhookEvent> = {}): WebhookEvent {
  return {
    id,
    delivery_id: `d-${id}`,
    event: "pull_request",
    action: "opened",
    repo: "acme/api",
    sender: "bob",
    payload_preview: '{"a":1}',
    status: "processed",
    error_message: null,
    created_at: "2026-10-08T00:00:00Z",
    jobs: [job()],
    ...overrides,
  };
}

describe("Activity", () => {
  it("expands an event with the keyboard and links to its review", async () => {
    mockFetch({
      "GET /api/v1/webhooks/events": [
        event(1),
        event(2, { action: null, repo: null, sender: null, delivery_id: null, jobs: [], error_message: "bot sender" }),
        event(3, { jobs: [] }),
      ],
    });
    renderWithProviders(<Activity />, { path: "/activity" });

    const rows = await screen.findAllByRole("row", { expanded: false });
    fireEvent.keyDown(rows[0]!, { key: "Enter" });
    expect(await screen.findByText("Delivery d-1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "view review" })).toHaveAttribute("href", "/history?review=42");
    fireEvent.keyDown(screen.getByRole("row", { expanded: true }), { key: " " });
    expect(screen.queryByText("Delivery d-1")).not.toBeInTheDocument();
    fireEvent.keyDown(rows[0]!, { key: "x" });
    expect(screen.queryByText("Delivery d-1")).not.toBeInTheDocument();

    await userEvent.click(rows[1]!);
    expect(await screen.findByText("Ignored: bot sender")).toBeInTheDocument();
    await userEvent.click(rows[2]!);
    expect(await screen.findByText("No jobs")).toBeInTheDocument();
  });

  it("filters by status and repository", async () => {
    const fetch = mockFetch({ "GET /api/v1/webhooks/events": [event(1)] });
    renderWithProviders(<Activity />, { path: "/activity" });
    await screen.findAllByRole("row", { expanded: false });

    await userEvent.selectOptions(screen.getByLabelText("Filter by status"), "failed");
    await userEvent.selectOptions(screen.getByLabelText("Filter by repository"), "acme/web");
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([url]) => /status=failed/.test(String(url)) && /repo=acme%2Fweb/.test(String(url))),
      ).toBe(true),
    );
  });

  it("loads older pages until the server runs out", async () => {
    const live = Array.from({ length: 50 }, (_, i) => event(200 - i));
    const fetch = mockFetch({
      "GET /api/v1/webhooks/events": (url: URL) =>
        url.searchParams.get("before_id") ? [event(151), event(100), event(99)] : live,
    });
    renderWithProviders(<Activity />, { path: "/activity" });

    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
    await waitFor(() => expect(screen.getAllByRole("row", { expanded: false })).toHaveLength(52));
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => String(url).includes("before_id=151"))).toBe(true);
  });

  it("shows a retry when events fail to load", async () => {
    let fail = true;
    mockFetch({ "GET /api/v1/webhooks/events": () => (fail ? json({ detail: "boom" }, 500) : []) });
    renderWithProviders(<Activity />, { path: "/activity" });
    const alert = await screen.findByRole("alert");
    fail = false;
    await userEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No webhook events yet")).toBeInTheDocument();
  });
});

function insight(overrides: Partial<InsightState> = {}): InsightState {
  return {
    repo_full_name: "acme/api",
    snapshot: null,
    total_reviews: 1,
    pending_count: 1,
    pending_capped: false,
    ran_model: false,
    ...overrides,
  };
}

const SNAPSHOT = {
  id: 1,
  repo_full_name: "acme/api",
  through_review_id: 4,
  included_count: 10,
  pending_analyzed_count: 10,
  summary_markdown: "Summary text",
  themes: [],
  new_this_period: [],
  still_showing: ["Logging"],
  model: "gemini-2.0-flash",
  created_at: "2026-10-07T12:00:00Z",
  created_by: "alice",
};

describe("Insights", () => {
  const scoped = { path: "/insights", workspace: { selectedRepo: "acme/api" } };

  it("describes the first run for one review, capped runs, and no reviews", async () => {
    let state = insight();
    mockFetch({ "GET /api/v1/insights": () => state });
    const first = renderWithProviders(<Insights />, scoped);
    expect(await screen.findByText("1 ReviewPilot review is ready to analyze.")).toBeInTheDocument();
    expect(screen.getByText("No analysis yet")).toBeInTheDocument();
    first.unmount();

    state = insight({ pending_count: 120, pending_capped: true, total_reviews: 120 });
    const capped = renderWithProviders(<Insights />, scoped);
    expect(await screen.findByText("120 ReviewPilot comments are ready. This run will include the oldest 50.")).toBeInTheDocument();
    capped.unmount();

    state = insight({ total_reviews: 0, pending_count: 0 });
    renderWithProviders(<Insights />, scoped);
    expect(await screen.findByText("No reviews yet")).toBeInTheDocument();
    expect(screen.getByText("0 ReviewPilot reviews are ready to analyze.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze" })).toBeDisabled();
  });

  it("describes follow-up runs and a snapshot without themes", async () => {
    let state = insight({ snapshot: SNAPSHOT, pending_count: 0, total_reviews: 10 });
    mockFetch({ "GET /api/v1/insights": () => state });
    const done = renderWithProviders(<Insights />, scoped);
    expect(await screen.findByText("No new reviews since the last analysis.")).toBeInTheDocument();
    expect(screen.getByText("The last run did not return structured themes.")).toBeInTheDocument();
    expect(screen.getByText("Still showing")).toBeInTheDocument();
    expect(screen.queryByText("New this period")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze 0 new reviews" })).toBeDisabled();
    done.unmount();

    state = insight({ snapshot: SNAPSHOT, pending_count: 80, pending_capped: true, total_reviews: 90 });
    const capped = renderWithProviders(<Insights />, scoped);
    expect(await screen.findByText("80 new reviews since the last analysis. This run will include the next 50.")).toBeInTheDocument();
    capped.unmount();

    state = insight({ snapshot: SNAPSHOT, pending_count: 1, total_reviews: 11 });
    renderWithProviders(<Insights />, scoped);
    expect(await screen.findByRole("button", { name: "Analyze 1 new review" })).toBeEnabled();
  });

  it("regenerates from scratch after confirmation and reports when nothing ran", async () => {
    const fetch = mockFetch({
      "GET /api/v1/insights": insight({ snapshot: SNAPSHOT, total_reviews: 10 }),
      "POST /api/v1/insights/analyze": insight({ snapshot: SNAPSHOT, ran_model: false }),
    });
    renderWithProviders(<Insights />, scoped);

    await userEvent.click(await screen.findByRole("button", { name: "Regenerate from scratch" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Regenerate from scratch" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Regenerate" }));
    expect(await screen.findByText("Nothing new to analyze.")).toBeInTheDocument();
    const post = fetch.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ repo: "acme/api", rebuild: true });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows the server error when analysis fails, and a retry when loading fails", async () => {
    let fail = false;
    mockFetch({
      "GET /api/v1/insights": () => (fail ? json({ detail: "boom" }, 500) : insight()),
      "POST /api/v1/insights/analyze": () => json({ detail: "Gemini quota exceeded" }, 429),
    });
    const { queryClient } = renderWithProviders(<Insights />, scoped);

    await userEvent.click(await screen.findByRole("button", { name: "Analyze" }));
    expect(await screen.findByText("Gemini quota exceeded")).toBeInTheDocument();

    fail = true;
    await queryClient.resetQueries({ queryKey: ["insights"] });
    const alert = await screen.findByRole("alert");
    fail = false;
    await userEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No analysis yet")).toBeInTheDocument();
  });

  it("uses a generic message when analysis fails without an API error", async () => {
    mockFetchWith(
      { "GET /api/v1/insights": insight() },
      { "/insights/analyze": () => Promise.reject(new TypeError("network down")) },
    );
    renderWithProviders(<Insights />, scoped);
    await userEvent.click(await screen.findByRole("button", { name: "Analyze" }));
    expect(await screen.findByText("Insight generation failed.")).toBeInTheDocument();
  });
});

const PRESETS = [{ id: "security", name: "Strict Security", description: "d", instructions: "- Check OWASP" }];
const RULE: Rule = {
  repo_full_name: "acme/api",
  custom_instructions: "",
  verbosity: "concise",
  review_mode: "auto",
  enable_security: true,
  updated_at: null,
  is_default: true,
};

describe("Rules", () => {
  it("shows a spinner while repositories load and an empty state without any", () => {
    mockFetch({});
    const loading = renderWithProviders(<Rules />, { workspace: { isLoading: true } });
    expect(screen.queryByLabelText("Repository")).not.toBeInTheDocument();
    loading.unmount();

    renderWithProviders(<Rules />, { workspace: { installations: [], repos: [] } });
    expect(screen.getByText("No repositories yet")).toBeInTheDocument();
  });

  it("asks before switching repositories with unsaved golden prompt edits", async () => {
    mockFetch({
      "GET /api/v1/rules/presets": PRESETS,
      "GET /api/v1/rules/acme/api": RULE,
      "GET /api/v1/rules/acme/web": { ...RULE, repo_full_name: "acme/web" },
      "GET /api/v1/prompt": promptFixture(),
      "GET /api/v1/rules/acme/api/documents": { items: [], total: 0, cache_status: "none" },
      "GET /api/v1/rules/acme/web/documents": { items: [], total: 0, cache_status: "none" },
    });
    renderWithProviders(<Rules />, { path: "/rules", user: { ...testUser, is_admin: true } });

    const select = await screen.findByLabelText("Repository");
    await userEvent.click(await screen.findByRole("button", { name: "Edit golden prompt" }));
    const editor = screen.getByLabelText("Golden prompt");
    await userEvent.type(editor, " more");

    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    await userEvent.selectOptions(select, "acme/web");
    expect(select).toHaveValue("acme/api");
    await userEvent.selectOptions(select, "acme/web");
    expect(select).toHaveValue("acme/web");
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it("shows a retry when the rule fails to load", async () => {
    let fail = true;
    mockFetch({
      "GET /api/v1/rules/presets": PRESETS,
      "GET /api/v1/rules/acme/api": () => (fail ? json({ detail: "boom" }, 500) : RULE),
      "GET /api/v1/prompt": promptFixture(),
      "GET /api/v1/rules/acme/api/documents": { items: [], total: 0, cache_status: "none" },
    });
    renderWithProviders(<Rules />, { path: "/rules" });
    const alert = await screen.findByRole("alert");
    fail = false;
    await userEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });
});

describe("App", () => {
  it("renders the landing page for anonymous visitors", async () => {
    mockFetch({ "GET /api/v1/auth/me": () => json({}, 401) });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <App />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("link", { name: /sign in/i })).toBeInTheDocument();
  });
});
