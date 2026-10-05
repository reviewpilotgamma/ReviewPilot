import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { vi } from "vitest";
import { AuthContext, type AuthState } from "@/context/AuthContext";
import { ToastProvider } from "@/context/ToastContext";
import { WorkspaceContext, type WorkspaceState } from "@/context/WorkspaceContext";
import type { Installation, User } from "@/types/api";

export const testUser: User = {
  id: 1,
  github_id: 1001,
  username: "alice",
  avatar_url: null,
  email: null,
  is_admin: false,
};

export const testInstallations: Installation[] = [
  {
    installation_id: 99,
    account_login: "acme",
    account_type: "Organization",
    avatar_url: "",
    repos: [
      { full_name: "acme/api", private: false, html_url: "https://github.com/acme/api", has_rules: false },
      { full_name: "acme/web", private: true, html_url: "https://github.com/acme/web", has_rules: true },
    ],
  },
];

type Handler = (url: URL, init: RequestInit) => unknown;

/** Minimal fetch mock: map "METHOD /path" to a handler returning JSON (or a Response). */
export function mockFetch(routes: Record<string, Handler | unknown>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://localhost");
    const key = `${(init.method ?? "GET").toUpperCase()} ${url.pathname}`;
    if (!(key in routes)) return new Response(JSON.stringify({ detail: `unmocked ${key}` }), { status: 404 });
    const route = routes[key];
    const result = typeof route === "function" ? (route as Handler)(url, init) : route;
    if (result instanceof Response) return result;
    return new Response(JSON.stringify(result), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

interface RenderOptions {
  path?: string;
  route?: string;
  user?: User | null;
  auth?: Partial<AuthState>;
  workspace?: Partial<WorkspaceState>;
}

export function renderWithProviders(ui: ReactElement, options: RenderOptions = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const auth: AuthState = {
    user: options.user === undefined ? testUser : options.user,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(async () => undefined),
    ...options.auth,
  };
  const repos = testInstallations.flatMap((i) => i.repos);
  const workspace: WorkspaceState = {
    installations: testInstallations,
    repos,
    isLoading: false,
    isError: false,
    selectedRepo: "",
    setSelectedRepo: vi.fn(),
    refresh: vi.fn(async () => undefined),
    ...options.workspace,
  };
  const router = createMemoryRouter(
    [
      { path: options.route ?? "*", element: ui },
      { path: "/other", element: <p>other page</p> },
    ],
    { initialEntries: [options.path ?? "/"] },
  );
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthContext.Provider value={auth}>
          <WorkspaceContext.Provider value={workspace}>
            <RouterProvider router={router} future={{ v7_startTransition: true }} />
          </WorkspaceContext.Provider>
        </AuthContext.Provider>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...utils, router, auth, workspace, queryClient };
}
