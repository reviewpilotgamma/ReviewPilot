import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { routes } from "@/App";
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

describe("Rules page", () => {
  it("appends preset chips without duplicates and enables Save when dirty", async () => {
    let saved: unknown = null;
    mockFetch({
      "GET /api/v1/rules/presets": PRESETS,
      "GET /api/v1/rules/acme/api": DEFAULT_RULE,
      "GET /api/v1/prompt": promptFixture(),
      "PUT /api/v1/rules/acme/api": (_url: URL, init: RequestInit) => {
        saved = JSON.parse(String(init.body));
        return { ...DEFAULT_RULE, ...(saved as object), is_default: false, updated_at: "2026-10-01T00:00:00Z" };
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });

    const textarea = await screen.findByLabelText("Custom instructions");
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    expect(screen.getByText("Using defaults")).toBeInTheDocument();

    const chip = await screen.findByRole("button", { name: "+ Strict Security" });
    await user.click(chip);
    await user.click(chip);
    expect(textarea).toHaveValue("- Check OWASP");
    await user.click(screen.getByRole("button", { name: "+ Performance & Async" }));
    expect(textarea).toHaveValue("- Check OWASP\n\n- No blocking IO");

    await user.click(screen.getByRole("radio", { name: "Detailed" }));
    expect(save).toBeEnabled();
    // The recipe strip reflects unsaved edits live.
    expect(screen.getByText("2 lines · Detailed · Security on")).toBeInTheDocument();

    await user.click(save);
    await waitFor(() =>
      expect(saved).toEqual({
        custom_instructions: "- Check OWASP\n\n- No blocking IO",
        verbosity: "detailed",
        review_mode: "auto",
        enable_security: true,
      }),
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeDisabled());
  });

  it("asks for confirmation before resetting to defaults", async () => {
    let deleted = false;
    mockFetch({
      "GET /api/v1/rules/presets": PRESETS,
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
};

function fileInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("file input not rendered");
  return input;
}

describe("Rules documents panel", () => {
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
    renderWithProviders(<Rules />, { path: "/rules" });
    expect(await screen.findByText(label)).toBeInTheDocument();
  });

  it("builds the cache only on the last file of a batch", async () => {
    const uploads: string[] = [];
    mockFetch({
      ...RULES_ROUTES,
      "GET /api/v1/rules/acme/api/documents": docList("none", []),
      "POST /api/v1/rules/acme/api/documents": (url: URL) => {
        uploads.push(url.search);
        return { ...DOC, cache_status: url.search ? "pending" : "cached", cache_error: null };
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });
    await screen.findByText("No documents");

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
    await screen.findByText("Will be cached on next review");

    await user.upload(fileInput(), new File(["# a"], "arch.md", { type: "text/markdown" }));

    expect(
      await screen.findByText("Uploaded arch.md — Gemini cache could not be built: Gemini 503: overloaded"),
    ).toBeInTheDocument();
  });
});

const EMOJI = /\p{Extended_Pictographic}/u;

describe("Prompt recipe and golden prompt drawer", () => {
  it("shows how the golden prompt, instructions and documents combine", async () => {
    mockFetch({
      ...RULES_ROUTES,
      "GET /api/v1/rules/acme/api/documents": docList("cached", [DOC, { ...DOC, id: 2, filename: "reqs.pdf" }]),
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });

    const strip = await screen.findByRole("region", { name: "How every review is composed" });
    expect(within(strip).getByText("Golden prompt")).toBeInTheDocument();
    expect(within(strip).getByText("Not set, defaults apply")).toBeInTheDocument();
    expect(await within(strip).findByText("2 files · Gemini cache ready")).toBeInTheDocument();
    expect(await within(strip).findByText("Default")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Custom instructions"), "- Keep services isolated");
    expect(within(strip).getByText("1 line · Concise · Security on")).toBeInTheDocument();
    expect(within(strip).getByText("Unsaved")).toBeInTheDocument();
    expect(strip.textContent).not.toMatch(EMOJI);
  });

  it("opens the assembled prompt with this repo's unsaved instructions highlighted", async () => {
    mockFetch({ ...RULES_ROUTES, "GET /api/v1/rules/acme/api/documents": docList("inline") });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules" });

    await user.type(await screen.findByLabelText("Custom instructions"), "- Idempotency keys on retries");
    await user.click(screen.getByRole("button", { name: "Golden prompt: view full prompt" }));

    const dialog = await screen.findByRole("dialog");
    const slot = dialog.querySelector('mark[data-slot="custom_instructions"]');
    expect(slot?.textContent).toContain("- Idempotency keys on retries");
    expect(dialog.querySelector('mark[data-slot="verbosity_directive"]')?.textContent).toContain("Be concise.");
    expect(within(dialog).getByText("arch.md")).toBeInTheDocument();
    expect(within(dialog).getByText("Appended to the end of this prompt.")).toBeInTheDocument();
    expect(within(dialog).getByText("Only admins can edit the golden prompt.")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Edit golden prompt" })).toBeNull();
    expect(dialog.textContent).not.toMatch(EMOJI);
  });

  it("lets an admin edit the golden prompt with validation before saving", async () => {
    let saved: string | null = null;
    mockFetch({
      ...RULES_ROUTES,
      "GET /api/v1/rules/acme/api/documents": docList("none", []),
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

    await user.click(await screen.findByRole("button", { name: "Golden prompt: view full prompt" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Edit golden prompt" }));

    expect(within(dialog).getByRole("note")).toHaveTextContent("Applies to every repository's reviews");
    const editor = within(dialog).getByLabelText("Golden prompt");
    const save = within(dialog).getByRole("button", { name: "Save golden prompt" });
    expect(save).toBeDisabled(); // unchanged

    await user.clear(editor);
    await user.type(editor, "Review strictly. reviewpilot-meta ");
    expect(within(dialog).getByText(/Missing \{\{custom_instructions\}\}/)).toBeInTheDocument();
    expect(save).toBeDisabled();

    await user.click(within(dialog).getByRole("button", { name: /^\{\{custom_instructions\}\}/ }));
    await waitFor(() => expect(save).toBeEnabled());
    await user.click(save);

    await waitFor(() => expect(saved).toBe("Review strictly. reviewpilot-meta {{custom_instructions}}"));
    expect(await screen.findByText(/Golden prompt saved/)).toBeInTheDocument();
  });

  it("shows the server's reasons when a save is rejected", async () => {
    mockFetch({
      ...RULES_ROUTES,
      "GET /api/v1/rules/acme/api/documents": docList("none", []),
      "PUT /api/v1/prompt": () =>
        new Response(JSON.stringify({ detail: { errors: ["Server says no."] } }), { status: 422 }),
    });
    const user = userEvent.setup();
    renderWithProviders(<Rules />, { path: "/rules", user: { ...testUser, is_admin: true } });

    await user.click(await screen.findByRole("button", { name: "Golden prompt: view full prompt" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Edit golden prompt" }));
    await user.type(within(dialog).getByLabelText("Golden prompt"), " More.");
    await user.click(within(dialog).getByRole("button", { name: "Save golden prompt" }));

    expect(await within(dialog).findByText("Server says no.")).toBeInTheDocument();
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
