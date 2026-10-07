import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { routes } from "@/App";
import History from "@/pages/History";
import Landing from "@/pages/Landing";
import Rules from "@/pages/Rules";
import { mockFetch, renderWithProviders } from "@/test/utils";
import type { CacheStatus, RepoDocument, RepoDocumentList, ReviewDetail, Rule } from "@/types/api";

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
  my_feedback: null,
};

const APP_LOCAL = {
  configured: false,
  slug: "",
  name: "ReviewPilot",
  install_url: "",
  html_url: "",
  local_mode: true,
};

describe("Landing page", () => {
  it("offers local sign-in when the API is in local mode", async () => {
    mockFetch({ "GET /api/v1/github/app": APP_LOCAL });
    renderWithProviders(<Landing />, { user: null });
    expect(await screen.findAllByRole("button", { name: "Continue locally" })).toHaveLength(2);
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

describe("Rules page", () => {
  it("appends preset chips without duplicates and enables Save when dirty", async () => {
    let saved: unknown = null;
    mockFetch({
      "GET /api/v1/rules/presets": PRESETS,
      "GET /api/v1/rules/acme/api": DEFAULT_RULE,
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
    expect(screen.getByText(/Be detailed/)).toBeInTheDocument(); // live directive preview

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

const RULES_ROUTES = { "GET /api/v1/rules/presets": PRESETS, "GET /api/v1/rules/acme/api": DEFAULT_RULE };

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
});
