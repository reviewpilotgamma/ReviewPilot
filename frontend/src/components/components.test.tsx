import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MarkdownView } from "@/components/diff/MarkdownView";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { Sidebar } from "@/components/layout/Sidebar";
import { FeedbackWidget } from "@/components/reviews/FeedbackWidget";
import { ReviewedWith } from "@/components/reviews/ReviewedWith";
import { StatusBadge, VerdictBadge } from "@/components/ui/Badge";
import { MetricCard } from "@/components/ui/MetricCard";
import { mockFetch, renderWithProviders } from "@/test/utils";

describe("MarkdownView", () => {
  it("renders raw HTML as text, never as elements", () => {
    const { container } = render(
      <MarkdownView markdown={'Hello <script>alert("x")</script> <img src=x onerror="alert(1)">'} />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders diff fences with coloured lines", () => {
    render(<MarkdownView markdown={"```diff\n+added\n-removed\n context\n```"} />);
    const block = screen.getByTestId("diff-block");
    expect(block).toHaveTextContent("+added");
    expect(screen.getByText("+added")).toHaveClass("text-emerald");
    expect(screen.getByText("-removed")).toHaveClass("text-rose");
  });

  it("opens links in a new tab safely", () => {
    render(<MarkdownView markdown="[PR](https://github.com/acme/api/pull/1)" />);
    const link = screen.getByRole("link", { name: "PR" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});

describe("badges and metric cards", () => {
  it("labels verdicts", () => {
    render(
      <>
        <VerdictBadge verdict="passed" />
        <VerdictBadge verdict="critical" />
        <StatusBadge status="failed" />
      </>,
    );
    expect(screen.getByText("Passed")).toBeInTheDocument();
    expect(screen.getByText("Critical Risk")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("shows an em dash and 'No data yet' for empty metrics", () => {
    render(<MetricCard label="Pass rate" value="—" icon={null} hint="hint" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("No data yet")).toBeInTheDocument();
  });
});

describe("ProtectedRoute", () => {
  it("redirects anonymous users to login with the current path", async () => {
    const { auth } = renderWithProviders(<ProtectedRoute />, { user: null, path: "/rules?repo=a" });
    await waitFor(() => expect(auth.login).toHaveBeenCalledWith("/rules?repo=a"));
    expect(screen.getByText(/Redirecting to GitHub/)).toBeInTheDocument();
  });
});

describe("Sidebar", () => {
  it("lists the main pages without Run review", () => {
    renderWithProviders(<Sidebar open onNavigate={() => undefined} />);
    const links = screen.getAllByRole("link").filter((link) => link.closest("nav"));
    expect(links.map((link) => link.textContent)).toEqual([
      "Dashboard",
      "Rules",
      "Review History",
      "Insights",
      "Activity",
      "Settings",
    ]);
    expect(screen.queryByRole("link", { name: "Run review" })).toBeNull();
  });
});

describe("FeedbackWidget", () => {
  it("submits a rating with notes", async () => {
    const fetchMock = mockFetch({
      "POST /api/v1/reviews/5/feedback": {
        id: 1, review_id: 5, user_id: 1, rating: "helpful", notes: "nice", created_at: "2026-01-01T00:00:00Z",
      },
      "GET /api/v1/reviews/5": () => new Response("{}", { status: 404 }),
    });
    const user = userEvent.setup();
    renderWithProviders(
      <FeedbackWidget reviewId={5} myFeedback={null} counts={{ helpful: 0, unhelpful: 0 }} />,
    );

    await user.click(screen.getByRole("button", { name: /Yes/ }));
    await user.type(screen.getByLabelText("Optional notes"), "nice");
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));

    await waitFor(() => expect(screen.getByText("Thanks for the feedback!")).toBeInTheDocument());
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/reviews/5/feedback"))!;
    expect(JSON.parse(String(call[1]?.body))).toEqual({ rating: "helpful", notes: "nice" });
  });

  it("highlights the user's existing rating", () => {
    renderWithProviders(
      <FeedbackWidget
        reviewId={5}
        myFeedback={{ id: 1, review_id: 5, user_id: 1, rating: "unhelpful", notes: "", created_at: "" }}
        counts={{ helpful: 2, unhelpful: 1 }}
      />,
    );
    expect(screen.getByRole("button", { name: /No/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Yes/ })).toHaveAttribute("aria-pressed", "false");
  });
});

describe("ReviewedWith", () => {
  it("summarises a custom prompt, instructions and cached documents without emojis", () => {
    const { container } = render(
      <ReviewedWith
        context={{
          prompt: "custom",
          prompt_updated_at: "2026-10-07T10:00:00Z",
          instructions_chars: 120,
          verbosity: "detailed",
          security: true,
          documents: ["arch.md", "reqs.pdf"],
          documents_mode: "cached",
          requester_note: false,
        }}
      />,
    );
    const line = screen.getByLabelText("Reviewed with");
    expect(line).toHaveTextContent("Golden prompt (edited Oct 7)");
    expect(line).toHaveTextContent("Instructions (Detailed · Security on)");
    expect(line).toHaveTextContent("2 documents (cached)");
    expect(container.textContent).not.toMatch(/\p{Extended_Pictographic}/u);
  });

  it("omits documents when none were used and renders nothing without context", () => {
    const { rerender } = render(
      <ReviewedWith
        context={{
          prompt: "default",
          prompt_updated_at: null,
          instructions_chars: 0,
          verbosity: "concise",
          security: false,
          documents: [],
          documents_mode: "none",
          requester_note: false,
        }}
      />,
    );
    const line = screen.getByLabelText("Reviewed with");
    expect(line).toHaveTextContent("No instructions (Concise · Security off)");
    expect(line).not.toHaveTextContent("document");
    rerender(<ReviewedWith context={null} />);
    expect(screen.queryByLabelText("Reviewed with")).toBeNull();
  });
});
