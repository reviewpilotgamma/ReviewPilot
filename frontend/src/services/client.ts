const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    /** Individual reasons when the server sends ``{"detail": {"errors": [...]}}``. */
    public readonly details: string[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();

/** Subscribe to 401 responses (used by AuthContext to reset state and redirect). */
export function onUnauthorized(listener: Listener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

export type QueryParams = Record<string, string | number | boolean | undefined | null>;

export function buildQuery(params?: QueryParams): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

/** Full-page navigation that installs the GitHub App (or authorizes, when already installed) and links GitHub. */
export function githubConnectUrl(mode: "install" | "authorize" = "install"): string {
  return `${API_BASE}/auth/github/connect${buildQuery({ mode })}`;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Requested-With", "ReviewPilot");
  // Let the browser set multipart boundary when body is FormData.
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...init,
    headers,
  });

  if (response.status === 401) {
    unauthorizedListeners.forEach((listener) => listener());
    throw new ApiError(401, "Unauthorized");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    const errors = (body.detail as { errors?: unknown } | undefined)?.errors;
    const details = Array.isArray(errors) ? errors.map(String) : [];
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : details.length
          ? details.join(" ")
          : Array.isArray(body.detail)
            ? "Validation failed"
            : response.statusText || "Request failed";
    throw new ApiError(response.status, detail, details);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const http = {
  get: <T>(path: string, params?: QueryParams) => api<T>(`${path}${buildQuery(params)}`),
  post: <T>(path: string, body?: unknown) =>
    api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(path: string) => api<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) => api<T>(path, { method: "POST", body: form }),
};
