import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MarkdownView } from "@/components/diff/MarkdownView";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { Sidebar } from "@/components/layout/Sidebar";
import { FeedbackWidget } from "@/components/reviews/FeedbackWidget";
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
