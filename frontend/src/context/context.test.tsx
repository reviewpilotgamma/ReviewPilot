import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { InstallAppGate } from "@/components/onboarding/InstallAppGate";
import { Cell, Row, Table } from "@/components/ui/Table";
import { AuthProvider } from "@/context/AuthContext";
import { WorkspaceProvider } from "@/context/WorkspaceContext";
import { useAuth, useWorkspace } from "@/hooks/useAuth";
import { useSubmitFeedback } from "@/hooks/useReviews";
import { formatBytes } from "@/lib/rules";
import { http } from "@/services/client";
import { mockFetch, renderWithProviders, testInstallations, testUser } from "@/test/utils";
import type { ReviewDetail } from "@/types/api";

function json(body: unknown, status: number) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

function AuthProbe() {
  const { user, isLoading, login, signIn, logout } = useAuth();
  if (isLoading) return <p>loading</p>;
  return (
    <div>
      <p>user: {user?.username ?? "anonymous"}</p>
      <button onClick={() => login()}>login</button>
      <button onClick={() => login("/rules")}>login-next</button>
      <button onClick={() => void signIn("alice", "pw")}>sign-in</button>
      <button onClick={() => void logout().catch(() => undefined)}>logout</button>
      <button onClick={() => void http.get("/reviews").catch(() => undefined)}>expire</button>
    </div>
  );
}

function renderAuth(client = newClient()) {
  const router = createMemoryRouter(
    [
      {
        path: "*",
        element: (
          <AuthProvider>
            <AuthProbe />
          </AuthProvider>
        ),
      },
      { path: "/login", element: <p>login page</p> },
    ],
    { initialEntries: ["/dashboard"] },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </QueryClientProvider>,
  );
  return { router, client };
}

describe("AuthProvider", () => {
  it("treats a 401 from /auth/me as signed out", async () => {
    mockFetch({ "GET /api/v1/auth/me": () => json({ detail: "no session" }, 401) });
    renderAuth();
    expect(await screen.findByText("user: anonymous")).toBeInTheDocument();
  });

  it("surfaces other /auth/me failures as signed out without crashing", async () => {
    mockFetch({ "GET /api/v1/auth/me": () => json({ detail: "boom" }, 500) });
    renderAuth();
    expect(await screen.findByText("user: anonymous")).toBeInTheDocument();
  });

  it("loads the current user, and signs in", async () => {
    let signedIn = false;
    mockFetch({
      "GET /api/v1/auth/me": () => (signedIn ? testUser : json({}, 401)),
      "POST /api/v1/auth/login": () => {
        signedIn = true;
        return { ...testUser, username: "alice2" };
      },
    });
    renderAuth();
    await userEvent.click(await screen.findByRole("button", { name: "sign-in" }));
    expect(await screen.findByText("user: alice2")).toBeInTheDocument();
  });

  it("sends the user to the sign-in page with the return path", async () => {
    mockFetch({ "GET /api/v1/auth/me": testUser });
    const { router } = renderAuth();
    await userEvent.click(await screen.findByRole("button", { name: "login-next" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(router.state.location.search).toBe("?next=%2Frules");
  });

  it("defaults the return path to the current window location", async () => {
    mockFetch({ "GET /api/v1/auth/me": testUser });
    const { router } = renderAuth();
    await userEvent.click(await screen.findByRole("button", { name: "login" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe(window.location.pathname);
  });

  it("drops the session when any request returns 401", async () => {
    let expired = false;
    mockFetch({
      "GET /api/v1/auth/me": () => (expired ? json({}, 401) : testUser),
      "GET /api/v1/reviews": () => {
        expired = true;
        return json({}, 401);
      },
    });
    renderAuth();
    expect(await screen.findByText("user: alice")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "expire" }));
    expect(await screen.findByText("user: anonymous")).toBeInTheDocument();
  });

  it("clears cached data and leaves the app on logout, even if the request fails", async () => {
    const assign = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", { value: { ...original, assign }, configurable: true });
    try {
      const fetch = mockFetch({
        "GET /api/v1/auth/me": testUser,
        "POST /api/v1/auth/logout": () => json({ detail: "down" }, 503),
      });
      const client = newClient();
      client.setQueryData(["reviews"], { items: [] });
      renderAuth(client);
      await userEvent.click(await screen.findByRole("button", { name: "logout" }));
      await waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
      expect(fetch).toHaveBeenCalledWith("/api/v1/auth/logout", expect.anything());
      expect(client.getQueryData(["reviews"])).toBeUndefined();
    } finally {
      Object.defineProperty(window, "location", { value: original, configurable: true });
    }
  });
});

function WorkspaceProbe() {
  const { repos, selectedRepo, setSelectedRepo } = useWorkspace();
  return (
    <div>
      <p>repos: {repos.length}</p>
      <p>selected: {selectedRepo || "all"}</p>
      <button onClick={() => setSelectedRepo("acme/web")}>pick</button>
    </div>
  );
}

function renderWorkspace() {
  return render(
    <QueryClientProvider client={newClient()}>
      <WorkspaceProvider>
        <WorkspaceProbe />
      </WorkspaceProvider>
    </QueryClientProvider>,
  );
}

describe("WorkspaceProvider", () => {
  it("restores a remembered repository and remembers a new choice", async () => {
    localStorage.setItem("rp_selected_repo", "acme/api");
    mockFetch({ "GET /api/v1/github/installations": testInstallations });
    renderWorkspace();
    expect(await screen.findByText("repos: 2")).toBeInTheDocument();
    expect(screen.getByText("selected: acme/api")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "pick" }));
    expect(screen.getByText("selected: acme/web")).toBeInTheDocument();
    expect(localStorage.getItem("rp_selected_repo")).toBe("acme/web");
  });

  it("ignores a remembered repository the user can no longer see", async () => {
    localStorage.setItem("rp_selected_repo", "gone/repo");
    mockFetch({ "GET /api/v1/github/installations": testInstallations });
    renderWorkspace();
    expect(await screen.findByText("repos: 2")).toBeInTheDocument();
    expect(screen.getByText("selected: all")).toBeInTheDocument();
  });

  it("keeps working when storage is unavailable", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    mockFetch({ "GET /api/v1/github/installations": testInstallations });
    renderWorkspace();
    expect(await screen.findByText("selected: all")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "pick" }));
    expect(screen.getByText("selected: acme/web")).toBeInTheDocument();
  });
});

describe("ProtectedRoute", () => {
  it("shows a spinner while the session loads", () => {
    mockFetch({});
    renderWithProviders(<ProtectedRoute />, { auth: { isLoading: true } });
    expect(screen.queryByText("Redirecting to sign in…")).not.toBeInTheDocument();
  });

  it("redirects anonymous visitors to sign in with the requested path", async () => {
    mockFetch({});
    const { auth } = renderWithProviders(<ProtectedRoute />, { user: null, path: "/history?page=2" });
    expect(screen.getByText("Redirecting to sign in…")).toBeInTheDocument();
    await waitFor(() => expect(auth.login).toHaveBeenCalledWith("/history?page=2"));
  });
});

describe("InstallAppGate", () => {
  it("explains what to do for a linked user and refreshes installations on demand", async () => {
    const fetch = mockFetch({
      "GET /api/v1/github/app": { configured: true, slug: "reviewpilot", name: "ReviewPilot", install_url: "", html_url: "" },
      "GET /api/v1/github/installations": [],
    });
    renderWithProviders(<InstallAppGate />);
    expect(await screen.findByText(/Your GitHub account @alice is connected/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() =>
      expect(fetch.mock.calls.some(([url]) => String(url).includes("/github/installations?refresh=true"))).toBe(true),
    );
    expect(screen.queryByText(/not configured yet/)).not.toBeInTheDocument();
  });

  it("asks unlinked users to connect GitHub and warns when the app is not configured", async () => {
    mockFetch({
      "GET /api/v1/github/app": { configured: false, slug: "", name: "", install_url: "", html_url: "" },
      "GET /api/v1/github/installations": [],
    });
    renderWithProviders(<InstallAppGate />, {
      user: { ...testUser, github_linked: false, github_login: null },
    });
    expect(await screen.findByText(/Your dashboard stays empty until you install/)).toBeInTheDocument();
    expect(await screen.findByText(/The GitHub App is not configured yet/)).toBeInTheDocument();
  });

  it("shows an error and stops the spinner when the refresh fails", async () => {
    mockFetch({
      "GET /api/v1/github/app": { configured: true, slug: "reviewpilot", name: "ReviewPilot", install_url: "", html_url: "" },
      "GET /api/v1/github/installations": (url: URL) =>
        url.searchParams.has("refresh") ? json({ detail: "GitHub down" }, 502) : [],
    });
    renderWithProviders(<InstallAppGate />);
    await userEvent.click(await screen.findByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("GitHub down")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeEnabled();
  });
});

describe("Table rows", () => {
  it("activates clickable rows with Enter and Space only", () => {
    const onClick = vi.fn();
    render(
      <Table head={["Name"]}>
        <Row onClick={onClick} label="Open review">
          <Cell>one</Cell>
        </Row>
        <Row>
          <Cell>static</Cell>
        </Row>
      </Table>,
    );
    const row = screen.getByRole("row", { name: "Open review" });
    fireEvent.keyDown(row, { key: "Enter" });
    fireEvent.keyDown(row, { key: " " });
    fireEvent.keyDown(row, { key: "a" });
    fireEvent.click(row);
    expect(onClick).toHaveBeenCalledTimes(3);
    expect(row).toHaveAttribute("tabindex", "0");

    const staticRow = screen.getByText("static").closest("tr");
    expect(staticRow).not.toHaveAttribute("tabindex");
    fireEvent.keyDown(staticRow as HTMLElement, { key: "Enter" });
    expect(onClick).toHaveBeenCalledTimes(3);
  });
});

describe("formatBytes", () => {
  it("formats bytes, kilobytes and megabytes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});

const REVIEW: ReviewDetail = {
  id: 5,
  repo_full_name: "acme/api",
  pr_number: 1,
  pr_title: "t",
  author: "bob",
  verdict: "passed",
  score: 9,
  lines_reviewed: 1,
  summary: "s",
  created_at: "2026-10-08T00:00:00Z",
  trigger: "auto",
  pr_url: "",
  feedback_counts: { helpful: 2, unhelpful: 1 },
  full_markdown: "",
  requester: null,
  diff_truncated: false,
  model: "gemini-2.0-flash",
  review_context: null,
  my_feedback: { id: 3, review_id: 5, user_id: 1, rating: "unhelpful", notes: "", created_at: "2026-10-08T00:00:00Z" },
};

describe("useSubmitFeedback", () => {
  function wrapper(client: QueryClient) {
    return ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  }

  it("moves the user's vote optimistically", async () => {
    let release: () => void = () => undefined;
    const base = mockFetch({ "GET /api/v1/reviews/5": REVIEW });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
        init?.method === "POST"
          ? new Promise<Response>((resolve) => {
              release = () => resolve(json({ id: 3, review_id: 5, rating: "helpful" }, 200));
            })
          : base(input, init),
      ),
    );
    const client = newClient();
    client.setQueryData(["review", 5], REVIEW);
    const { result } = renderHook(() => useSubmitFeedback(5), { wrapper: wrapper(client) });

    act(() => result.current.mutate({ rating: "helpful", notes: "nice" }));
    await waitFor(() =>
      expect(client.getQueryData<ReviewDetail>(["review", 5])?.feedback_counts).toEqual({ helpful: 3, unhelpful: 0 }),
    );
    expect(client.getQueryData<ReviewDetail>(["review", 5])?.my_feedback).toMatchObject({
      id: 3,
      rating: "helpful",
      notes: "nice",
    });
    act(() => release());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it("creates a first vote optimistically and rolls back when the request fails", async () => {
    mockFetch({
      "POST /api/v1/reviews/5/feedback": () => json({ detail: "nope" }, 500),
    });
    const client = newClient();
    const first = { ...REVIEW, my_feedback: null, feedback_counts: { helpful: 0, unhelpful: 0 } };
    client.setQueryData(["review", 5], first);
    const { result } = renderHook(() => useSubmitFeedback(5), { wrapper: wrapper(client) });

    act(() => result.current.mutate({ rating: "unhelpful", notes: "" }));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(client.getQueryData<ReviewDetail>(["review", 5])).toEqual(first);
  });

  it("does nothing optimistic when the review is not cached", async () => {
    mockFetch({ "POST /api/v1/reviews/5/feedback": () => json({ detail: "nope" }, 500) });
    const client = newClient();
    const { result } = renderHook(() => useSubmitFeedback(5), { wrapper: wrapper(client) });
    act(() => result.current.mutate({ rating: "helpful", notes: "" }));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(client.getQueryData(["review", 5])).toBeUndefined();
  });
});
