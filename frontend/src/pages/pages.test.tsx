import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { routes } from "@/App";
import Activity from "@/pages/Activity";
import Dashboard from "@/pages/Dashboard";
import History from "@/pages/History";
import Insights from "@/pages/Insights";
import Rules from "@/pages/Rules";
import { promptFixture } from "@/test/prompt";
import { mockFetch, renderWithProviders, testUser } from "@/test/utils";
import type { CacheStatus, InsightState, RepoDocument, RepoDocumentList, ReviewDetail, Rule } from "@/types/api";

const PRESETS = [
  { id: "security", name: "Strict Security", description: "d", instructions: "- Check OWASP" },
  { id: "performance", name: "Performance & Async", description: "d", instructions: "- No blocking IO" },
];

const DEFAULT_RULE: Rule = {
  repo_full_name: "acme/api",
  custom_instructions: "",
  verbosity: "concise",
  review_mode: "auto",
  enable_security: true,
  updated_at: null,
  is_default: true,
};

const REVIEW: ReviewDetail = {
  id: 1,
  repo_full_name: "acme/api",
  pr_number: 7,
  pr_title: "Add payment retries",
  author: "bob",
  verdict: "warning",
  score: 6.5,
  lines_reviewed: 12,
  summary: "s",
  created_at: new Date().toISOString(),
  trigger: "comment",
  pr_url: "https://github.com/acme/api/pull/7",
  feedback_counts: { helpful: 0, unhelpful: 0 },
  full_markdown: "## ✈️ ReviewPilot Architectural Audit\n\n### Executive Summary\nRetries need idempotency.",
  requester: "alice",
  diff_truncated: false,
  model: "gemini-2.0-flash",
  review_context: null,
  my_feedback: null,
};

describe("Dashboard KPIs", () => {
  it("shows lines reviewed in place of the helpful rate", async () => {
    mockFetch({
      "GET /api/v1/github/app": { configured: true, slug: "reviewpilot", name: "ReviewPilot", install_url: "", html_url: "" },
      "GET /api/v1/metrics/summary": { total_reviews: 3, lines_reviewed: 12480, recent: [] },
      "GET /api/v1/metrics/trend": [],
    });
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("Lines reviewed")).toBeInTheDocument();
    expect(await screen.findByText((12480).toLocaleString())).toBeInTheDocument();
    expect(screen.getByText("Diff lines read by the AI")).toBeInTheDocument();
    expect(screen.queryByText("Helpful rate")).not.toBeInTheDocument();
  });
});

describe("Removed Run review route", () => {
  it("shows Not Found at /run", async () => {
    mockFetch({});
    const router = createMemoryRouter(routes, { initialEntries: ["/run"] });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <RouterProvider router={router} future={{ v7_startTransition: true }} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
});

const DOC: RepoDocument = {
  id: 1,
  repo_full_name: "acme/api",
  filename: "arch.md",
  content_type: "text/markdown",
  size_bytes: 2048,
  sha256: "abc",
  char_count: 2000,
  uploaded_at: "2026-10-07T00:00:00Z",
};

function docList(cache_status: CacheStatus, items: RepoDocument[] = [DOC]): RepoDocumentList {
  return { items, total: items.length, cache_status };
}

const RULES_ROUTES = {
  "GET /api/v1/rules/presets": PRESETS,
  "GET /api/v1/rules/acme/api": DEFAULT_RULE,
  "GET /api/v1/prompt": promptFixture(),
  "GET /api/v1/rules/acme/api/documents": docList("none", []),
};

function fileInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("file input not rendered");
  return input;
}

const EMOJI = /\p{Extended_Pictographic}/u;

describe("Rules page", () => {
  it("opens on the golden prompt with the options in the sidebar and no popup", async () => {
    mockFetch({
      ...RULES_ROUTES,
      "GET /api/v1/rules/acme/api/documents": docList("cached", [DOC, { ...DOC, id: 2, filename: "reqs.pdf" }]),
    });
    renderWithProviders(<Rules />, { path: "/rules" });

    const sidebar = await screen.findByRole("complementary", { name: "Repository rules" });
    expect(within(sidebar).getByText("Using defaults")).toBeInTheDocument();
    expect(within(sidebar).getByText("Not set, defaults apply")).toBeInTheDocument();
    expect(await within(sidebar).findByText("2 files · Gemini cache ready")).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector('mark[data-slot="custom_instructions"]')).not.toBeNull());
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByLabelText("Custom instructions")).toBeNull();
    expect(document.body.textContent).not.toMatch(EMOJI);
  });

  it("edits custom instructions in a popup and saves them with the saved settings", async () => {
    let saved: unknown = null;
    mockFetch({
      ...RULES_ROUTES,
      "PUT /api/v1/rules/acme/api": (_url: URL, init: RequestInit) => {
        saved = JSON.parse(String(init.body));
        return { ...DEFAULT_RULE, ...(saved as object), is_default: false, updated_at: "2026-10-01T00:00:00Z" };
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });

    await user.click(await screen.findByRole("button", { name: "Edit custom instructions" }));
    const dialog = screen.getByRole("dialog", { name: "Custom instructions" });
    const textarea = within(dialog).getByLabelText("Custom instructions");
    const save = within(dialog).getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();

    const chip = await within(dialog).findByRole("button", { name: "+ Strict Security" });
    await user.click(chip);
    await user.click(chip);
    expect(textarea).toHaveValue("- Check OWASP");
    await user.click(within(dialog).getByRole("button", { name: "+ Performance & Async" }));
    expect(textarea).toHaveValue("- Check OWASP\n\n- No blocking IO");

    await user.click(save);
    await waitFor(() =>
      expect(saved).toEqual({
        custom_instructions: "- Check OWASP\n\n- No blocking IO",
        verbosity: "concise",
        review_mode: "auto",
        enable_security: true,
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByText("2 lines")).toBeInTheDocument();
    expect(document.querySelector('mark[data-slot="custom_instructions"]')?.textContent).toContain("- No blocking IO");
  });

  it("asks before discarding unsaved instructions", async () => {
    mockFetch(RULES_ROUTES);
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });

    await user.click(await screen.findByRole("button", { name: "Edit custom instructions" }));
    await user.type(screen.getByRole("textbox", { name: "Custom instructions" }), "- Draft");
    await user.keyboard("{Escape}");
    const confirm = screen.getByRole("dialog", { name: "Discard unsaved changes?" });
    await user.click(within(confirm).getByRole("button", { name: "Keep editing" }));
    expect(screen.getByRole("textbox", { name: "Custom instructions" })).toHaveValue("- Draft");

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(within(screen.getByRole("dialog", { name: "Discard unsaved changes?" })).getByRole("button", { name: "Discard" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("saves a sidebar setting as soon as it changes", async () => {
    let saved: unknown = null;
    mockFetch({
      ...RULES_ROUTES,
      "PUT /api/v1/rules/acme/api": (_url: URL, init: RequestInit) => {
        saved = JSON.parse(String(init.body));
        return { ...DEFAULT_RULE, ...(saved as object), is_default: false, updated_at: "2026-10-01T00:00:00Z" };
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });

    await user.click(await screen.findByRole("radio", { name: "Detailed" }));
    await waitFor(() =>
      expect(saved).toEqual({ custom_instructions: "", verbosity: "detailed", review_mode: "auto", enable_security: true }),
    );
    expect(await screen.findByText("Settings saved")).toBeInTheDocument();
    expect(screen.queryByText("Using defaults")).toBeNull();
    expect(screen.getByRole("radio", { name: "Detailed" })).toHaveAttribute("aria-checked", "true");
  });

  it("reverts a sidebar setting when saving fails", async () => {
    mockFetch({
      ...RULES_ROUTES,
      "PUT /api/v1/rules/acme/api": () => new Response(JSON.stringify({ detail: "Database unavailable" }), { status: 500 }),
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });

    await user.click(await screen.findByRole("switch", { name: "Security audit" }));
    expect(await screen.findByText(/Database unavailable|Could not save settings/)).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Security audit" })).toHaveAttribute("aria-checked", "true");
  });

  it("asks for confirmation before resetting to defaults", async () => {
    let deleted = false;
    mockFetch({
      ...RULES_ROUTES,
      "GET /api/v1/rules/acme/api": () =>
        deleted ? DEFAULT_RULE : { ...DEFAULT_RULE, is_default: false, custom_instructions: "x", updated_at: "t" },
      "DELETE /api/v1/rules/acme/api": () => {
        deleted = true;
        return new Response(null, { status: 204 });
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });

    await user.click(await screen.findByRole("button", { name: "Reset to defaults" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/will be deleted/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Reset" }));
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Using defaults")).toBeInTheDocument();
  });
});

describe("Rules documents popup", () => {
  async function openDocuments(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: "Manage documents" }));
    return screen.getByRole("dialog", { name: "Architecture & requirements docs" });
  }

  it.each([
    ["cached", "Gemini cache ready"],
    ["pending", "Will be cached on next review"],
    ["inline", "Inline reference (below cache size)"],
    ["none", "No documents"],
  ] as const)("shows the %s cache badge", async (status, label) => {
    mockFetch({
      ...RULES_ROUTES,
      "GET /api/v1/rules/acme/api/documents": docList(status, status === "none" ? [] : [DOC]),
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });
    const dialog = await openDocuments(user);
    expect(await within(dialog).findByText(label)).toBeInTheDocument();
  });

  it("builds the cache only on the last file of a batch", async () => {
    const uploads: string[] = [];
    mockFetch({
      ...RULES_ROUTES,
      "POST /api/v1/rules/acme/api/documents": (url: URL) => {
        uploads.push(url.search);
        return { ...DOC, cache_status: url.search ? "pending" : "cached", cache_error: null };
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });
    const dialog = await openDocuments(user);
    await within(dialog).findByText("No documents");

    await user.upload(fileInput(), [
      new File(["# a"], "a.md", { type: "text/markdown" }),
      new File(["# b"], "b.md", { type: "text/markdown" }),
    ]);

    await waitFor(() => expect(uploads).toEqual(["?warm=false", ""]));
    expect(await screen.findByText("Uploaded b.md")).toBeInTheDocument();
  });

  it("warns when the document saved but the Gemini cache failed", async () => {
    mockFetch({
      ...RULES_ROUTES,
      "GET /api/v1/rules/acme/api/documents": docList("pending"),
      "POST /api/v1/rules/acme/api/documents": { ...DOC, cache_status: "pending", cache_error: "Gemini 503: overloaded" },
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });
    const dialog = await openDocuments(user);
    await within(dialog).findByText("Will be cached on next review");

    await user.upload(fileInput(), new File(["# a"], "arch.md", { type: "text/markdown" }));

    expect(
      await screen.findByText("Uploaded arch.md — Gemini cache could not be built: Gemini 503: overloaded"),
    ).toBeInTheDocument();
  });
});

describe("Golden prompt panel", () => {
  it("shows the assembled prompt with this repo's saved instructions highlighted", async () => {
    mockFetch({
      ...RULES_ROUTES,
      "GET /api/v1/rules/acme/api": {
        ...DEFAULT_RULE,
        is_default: false,
        custom_instructions: "- Idempotency keys on retries",
        updated_at: "t",
      },
      "GET /api/v1/rules/acme/api/documents": docList("inline"),
    });
    renderWithProviders(<Rules />, { path: "/rules" });

    expect(await screen.findByText("Appended to the end of this prompt.")).toBeInTheDocument();
    const slot = document.querySelector('mark[data-slot="custom_instructions"]');
    expect(slot?.textContent).toContain("- Idempotency keys on retries");
    expect(document.querySelector('mark[data-slot="verbosity_directive"]')?.textContent).toContain("Be concise.");
    expect(screen.getAllByText("arch.md").length).toBeGreaterThan(0);
    expect(screen.getByText("Only admins can edit the golden prompt.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit golden prompt" })).toBeNull();
  });

  it("expands the golden prompt into a wide popup and back", async () => {
    mockFetch(RULES_ROUTES);
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });

    await user.click(await screen.findByRole("button", { name: "Expand golden prompt" }));
    const dialog = screen.getByRole("dialog", { name: "Golden prompt" });
    expect(dialog.querySelector('mark[data-slot="custom_instructions"]')).not.toBeNull();
    expect(within(dialog).getByRole("button", { name: "Copy" })).toBeInTheDocument();
    expect(screen.getByText("Showing in the expanded view.")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.querySelector('mark[data-slot="custom_instructions"]')).not.toBeNull();
  });

  it("lets an admin edit the golden prompt inline with validation before saving", async () => {
    let saved: string | null = null;
    mockFetch({
      ...RULES_ROUTES,
      "PUT /api/v1/prompt": (_url: URL, init: RequestInit) => {
        saved = (JSON.parse(String(init.body)) as { template: string }).template;
        return promptFixture({
          template: saved,
          is_default: false,
          updated_at: "2026-10-07T10:00:00Z",
          updated_by: "admin",
        });
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules", user: { ...testUser, is_admin: true } });

    await user.click(await screen.findByRole("button", { name: "Edit golden prompt" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("note")).toHaveTextContent("Applies to every repository's reviews");
    const editor = screen.getByLabelText("Golden prompt");
    const save = screen.getByRole("button", { name: "Save golden prompt" });
    expect(save).toBeDisabled(); // unchanged

    await user.clear(editor);
    await user.type(editor, "Review strictly. reviewpilot-meta ");
    expect(screen.getByText(/Missing \{\{custom_instructions\}\}/)).toBeInTheDocument();
    expect(save).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /^\{\{custom_instructions\}\}/ }));
    await waitFor(() => expect(save).toBeEnabled());
    await user.click(save);

    await waitFor(() => expect(saved).toBe("Review strictly. reviewpilot-meta {{custom_instructions}}"));
    expect(await screen.findByText(/Golden prompt saved/)).toBeInTheDocument();
  });

  it("shows the server's reasons when a save is rejected", async () => {
    mockFetch({
      ...RULES_ROUTES,
      "PUT /api/v1/prompt": () =>
        new Response(JSON.stringify({ detail: { errors: ["Server says no."] } }), { status: 422 }),
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules", user: { ...testUser, is_admin: true } });

    await user.click(await screen.findByRole("button", { name: "Edit golden prompt" }));
    await user.type(screen.getByLabelText("Golden prompt"), " More.");
    await user.click(screen.getByRole("button", { name: "Save golden prompt" }));

    expect(await screen.findByText("Server says no.")).toBeInTheDocument();
  });
});

describe("History page", () => {
  it("opens the review drawer from the ?review= deep link", async () => {
    mockFetch({
      "GET /api/v1/reviews": { items: [REVIEW], total: 1, page: 1, page_size: 20 },
      "GET /api/v1/reviews/1": REVIEW,
    });
    renderWithProviders(<History />, { path: "/history?review=1" });
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Retries need idempotency.")).toBeInTheDocument();
    expect(within(dialog).getByText("Was this review helpful?")).toBeInTheDocument();
  });

  it("syncs the verdict filter to the URL and query", async () => {
    const fetchMock = mockFetch({
      "GET /api/v1/reviews": { items: [REVIEW], total: 1, page: 1, page_size: 20 },
    });
    const user = userEvent.setup();
    const { router } = renderWithProviders(<History />, { path: "/history" });
    await screen.findByText("Add payment retries");

    await user.click(screen.getByRole("button", { name: "Warning" }));
    await waitFor(() => expect(router.state.location.search).toContain("verdict=warning"));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("verdict=warning"))).toBe(true),
    );
  });

  it("shows an empty state when filters match nothing", async () => {
    mockFetch({ "GET /api/v1/reviews": { items: [], total: 0, page: 1, page_size: 20 } });
    renderWithProviders(<History />, { path: "/history?verdict=critical" });
    expect(await screen.findByText("No reviews match these filters")).toBeInTheDocument();
  });

  it("links to Insights", async () => {
    mockFetch({ "GET /api/v1/reviews": { items: [REVIEW], total: 1, page: 1, page_size: 20 } });
    renderWithProviders(<History />, { path: "/history" });
    expect(await screen.findByRole("link", { name: "Insights" })).toHaveAttribute("href", "/insights");
  });
});

const INSIGHT: InsightState = {
  repo_full_name: "acme/api",
  snapshot: {
    id: 1,
    repo_full_name: "acme/api",
    through_review_id: 4,
    included_count: 10,
    pending_analyzed_count: 10,
    summary_markdown: "## Recurring issues\nIdempotency keeps showing up.",
    themes: [
      {
        title: "Missing idempotency",
        severity: "warning",
        count: 4,
        last_seen_review_id: 4,
        example_review_ids: [1, 4],
        evidence: "Retries without keys on the payment path.",
      },
    ],
    new_this_period: ["Missing idempotency"],
    still_showing: [],
    model: "gemini-2.0-flash",
    created_at: "2026-10-07T12:00:00Z",
    created_by: "alice",
  },
  total_reviews: 12,
  pending_count: 2,
  pending_capped: false,
  ran_model: false,
};

describe("Insights page", () => {
  it("asks for a repository when none is selected", () => {
    renderWithProviders(<Insights />, { path: "/insights" });
    expect(screen.getByText("Select a repository")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(EMOJI);
  });

  it("shows the latest snapshot and pending count", async () => {
    mockFetch({ "GET /api/v1/insights": INSIGHT });
    renderWithProviders(<Insights />, { path: "/insights", workspace: { selectedRepo: "acme/api" } });
    expect(await screen.findByText("2 new reviews since the last analysis (12 total in this repo).")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Missing idempotency" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review 4" })).toHaveAttribute("href", "/history?review=4");
    expect(screen.getByText("Idempotency keeps showing up.")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(EMOJI);
  });

  it("runs incremental analyze", async () => {
    const fetchMock = mockFetch({
      "GET /api/v1/insights": INSIGHT,
      "POST /api/v1/insights/analyze": { ...INSIGHT, pending_count: 0, ran_model: true },
    });
    const user = userEvent.setup();
    renderWithProviders(<Insights />, { path: "/insights", workspace: { selectedRepo: "acme/api" } });
    await screen.findByRole("heading", { name: "Missing idempotency" });
    await user.click(screen.getByRole("button", { name: "Analyze 2 new reviews" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url, init]) => String(url).includes("/insights/analyze") && init?.method === "POST")).toBe(
        true,
      ),
    );
    expect(await screen.findByText("Insights updated.")).toBeInTheDocument();
  });
});

describe("Activity page", () => {
  it("hides bot events by default and requests them when toggled", async () => {
    const fetchMock = mockFetch({ "GET /api/v1/webhooks/events": [] });
    const user = userEvent.setup();
    renderWithProviders(<Activity />, { path: "/activity" });
    await screen.findByText("No webhook events yet");
    const eventCalls = () => fetchMock.mock.calls.map(([url]) => String(url)).filter((u) => u.includes("/webhooks/events"));
    expect(eventCalls().every((u) => !u.includes("include_bot"))).toBe(true);

    await user.click(screen.getByRole("checkbox", { name: "Show bot events" }));
    await waitFor(() => expect(eventCalls().some((u) => u.includes("include_bot=true"))).toBe(true));
  });
});
