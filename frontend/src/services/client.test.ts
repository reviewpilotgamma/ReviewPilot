import { describe, expect, it, vi } from "vitest";
import { mockFetch } from "@/test/utils";
import { api, ApiError, buildQuery, http, loginUrl, onUnauthorized } from "./client";

describe("api client", () => {
  it("sends credentials and the CSRF header", async () => {
    const fetchMock = mockFetch({ "PUT /api/v1/rules/acme/api": { ok: true } });
    await http.put("/rules/acme/api", { verbosity: "concise" });
    const [, init] = fetchMock.mock.calls[0]!;
    expect(init?.credentials).toBe("include");
    const headers = new Headers(init?.headers);
    expect(headers.get("X-Requested-With")).toBe("ReviewPilot");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init?.body).toBe(JSON.stringify({ verbosity: "concise" }));
  });

  it("skips Content-Type for FormData uploads so the browser sets the boundary", async () => {
    const fetchMock = mockFetch({ "POST /api/v1/rules/acme/api/documents": { id: 1 } });
    const form = new FormData();
    form.append("file", new Blob(["hello"], { type: "text/plain" }), "arch.md");
    await http.upload("/rules/acme/api/documents", form);
    const [, init] = fetchMock.mock.calls[0]!;
    const headers = new Headers(init?.headers);
    expect(headers.get("X-Requested-With")).toBe("ReviewPilot");
    expect(headers.get("Content-Type")).toBeNull();
    expect(init?.body).toBe(form);
  });

  it("notifies listeners and throws on 401", async () => {
    mockFetch({ "GET /api/v1/auth/me": () => new Response("{}", { status: 401 }) });
    const listener = vi.fn();
    const unsubscribe = onUnauthorized(listener);
    await expect(api("/auth/me")).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledOnce();
    unsubscribe();
  });

  it("surfaces backend error details", async () => {
    mockFetch({
      "GET /api/v1/reviews/9": () => new Response(JSON.stringify({ detail: "Review not found" }), { status: 404 }),
    });
    const error = await api("/reviews/9").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("Review not found");
  });

  it("exposes structured validation reasons", async () => {
    mockFetch({
      "PUT /api/v1/prompt": new Response(JSON.stringify({ detail: { errors: ["Missing slot.", "Bad token."] } }), {
        status: 422,
      }),
    });
    const error = await http.put("/prompt", { template: "x" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).details).toEqual(["Missing slot.", "Bad token."]);
    expect((error as ApiError).message).toBe("Missing slot. Bad token.");
  });

  it("returns undefined for 204", async () => {
    mockFetch({ "DELETE /api/v1/rules/a/b": () => new Response(null, { status: 204 }) });
    await expect(http.delete("/rules/a/b")).resolves.toBeUndefined();
  });

  it("builds query strings without empty values", () => {
    expect(buildQuery({ a: "1", b: undefined, c: "", d: 0, e: null })).toBe("?a=1&d=0");
    expect(buildQuery({})).toBe("");
    expect(loginUrl("/rules?x=1")).toBe("/api/v1/auth/login?next=%2Frules%3Fx%3D1");
  });
});
