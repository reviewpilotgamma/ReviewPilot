import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/layout/AppShell";
import { Navbar } from "@/components/layout/Navbar";
import Dashboard from "@/pages/Dashboard";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import { ApiError } from "@/services/client";
import { mockFetch, renderWithProviders, testUser } from "@/test/utils";
import type { AppInfo, User } from "@/types/api";

const APP: AppInfo = {
  configured: true,
  slug: "reviewpilot",
  name: "ReviewPilot",
  install_url: "https://github.com/apps/reviewpilot/installations/new",
  html_url: "https://github.com/apps/reviewpilot",
};

const UNLINKED: User = { ...testUser, username: "dev", github_id: null, github_login: null, github_linked: false };

describe("Landing page", () => {
  it("offers only a Sign in link for anonymous visitors", () => {
    renderWithProviders(<Landing />, { user: null });
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    for (const name of ["Install GitHub App", "Sign in with GitHub", "Continue locally"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it("links signed-in users to the dashboard", () => {
    renderWithProviders(<Landing />);
    expect(screen.getByRole("button", { name: "Go to dashboard" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
  });
});

describe("Login page", () => {
  it("signs in and goes to the requested page", async () => {
    const signIn = vi.fn(async () => testUser);
    const { router } = renderWithProviders(<Login />, {
      user: null,
      path: "/login?next=/other",
      auth: { signIn },
    });
    const user = userEvent.setup();
    const submit = screen.getByRole("button", { name: "Sign in" });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText("Username"), "admin");
    await user.type(screen.getByLabelText("Password"), "admin12345");
    await user.click(submit);
    expect(signIn).toHaveBeenCalledWith("admin", "admin12345");
    await waitFor(() => expect(router.state.location.pathname).toBe("/other"));
  });

  it("shows a generic error for bad credentials", async () => {
    const signIn = vi.fn(async () => {
      throw new ApiError(401, "Unauthorized");
    });
    renderWithProviders(<Login />, { user: null, path: "/login", auth: { signIn } });
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Username"), "dev");
    await user.type(screen.getByLabelText("Password"), "nope");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
  });

  it("ignores off-site next targets", async () => {
    const { router } = renderWithProviders(<Login />, { path: "/login?next=//evil.example.com" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/dashboard"));
  });
});

describe("Install GitHub App", () => {
  it("is in the navbar and starts the install flow", async () => {
    mockFetch({ "GET /api/v1/github/app": APP });
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    renderWithProviders(<Navbar title="Dashboard" onMenu={() => undefined} />, {
      user: UNLINKED,
      workspace: { installations: [], repos: [] },
    });
    const button = await screen.findByRole("button", { name: "Install GitHub App" });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(assign).toHaveBeenCalledWith("/api/v1/auth/github/connect?mode=install");
    vi.unstubAllGlobals();
  });

  it("reads Manage GitHub App once installed", async () => {
    mockFetch({ "GET /api/v1/github/app": APP });
    renderWithProviders(<Navbar title="Dashboard" onMenu={() => undefined} />);
    expect(await screen.findByRole("button", { name: "Manage GitHub App" })).toBeInTheDocument();
  });

  it("is disabled when the App is not configured", async () => {
    mockFetch({ "GET /api/v1/github/app": { ...APP, configured: false } });
    renderWithProviders(<Navbar title="Dashboard" onMenu={() => undefined} />, {
      user: UNLINKED,
      workspace: { installations: [], repos: [] },
    });
    const button = await screen.findByRole("button", { name: "Install GitHub App" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "GitHub App not configured — ask an admin");
  });
});

describe("First sign-in gate", () => {
  it("tells a new user to install the GitHub App before the dashboard shows data", async () => {
    mockFetch({
      "GET /api/v1/github/app": APP,
      "GET /api/v1/github/installations": [],
      "GET /api/v1/metrics/summary": { total_reviews: 0, recent: [] },
      "GET /api/v1/metrics/trend": [],
    });
    renderWithProviders(<Dashboard />, { user: UNLINKED, workspace: { installations: [], repos: [] } });
    expect(await screen.findByText("Install the GitHub App first to see your data on the dashboard.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Install GitHub App" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Already installed? Connect GitHub" })).toBeInTheDocument();
  });

  it("shows a banner on other pages while nothing is installed", async () => {
    mockFetch({ "GET /api/v1/github/app": APP, "GET /api/v1/github/installations": [] });
    renderWithProviders(<AppShell />, { user: UNLINKED, path: "/rules" });
    const banner = await screen.findByRole("status");
    expect(within(banner).getByText(/Install the GitHub App to see your repositories/)).toBeInTheDocument();
  });

  it("reports a failed GitHub connection", async () => {
    mockFetch({
      "GET /api/v1/github/app": APP,
      "GET /api/v1/metrics/summary": { total_reviews: 0, recent: [] },
      "GET /api/v1/metrics/trend": [],
    });
    const { router } = renderWithProviders(<Dashboard />, { path: "/dashboard?github_error=exchange" });
    expect(await screen.findByText("GitHub did not confirm the connection. Please try again.")).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toBe(""));
  });
});
