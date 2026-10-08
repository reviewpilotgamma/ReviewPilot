import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Settings from "@/pages/Settings";
import { mockFetch, renderWithProviders } from "@/test/utils";
import type { Replies, Settings as SettingsData } from "@/types/api";

const SETTINGS: SettingsData = {
  github_app_id: "123",
  github_app_slug: "reviewpilot",
  github_webhook_secret: "••••cret",
  github_private_key_path: "secrets/key.pem",
  github_private_key_present: true,
  github_client_id: "Iv1.abc",
  github_client_secret: "••••1234",
  gemini_api_key: "••••wxyz",
  gemini_model: "gemini-2.0-flash",
  max_diff_chars: 120000,
  webhook_url: "https://rp.example.com/api/v1/webhooks/github",
  is_admin: true,
};

const REPLIES: Replies = {
  welcome: "Hi {author}",
  plan: "Fallback plan",
  error: "Failed: {reason}",
  empty_diff: "Nothing to review",
};

function json(body: unknown, status: number) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function routes(overrides: Record<string, unknown> = {}) {
  return {
    "GET /api/v1/settings": SETTINGS,
    "GET /api/v1/settings/replies": REPLIES,
    ...overrides,
  };
}

describe("Settings page", () => {
  it("shows the loaded settings and masks secrets until they are edited", async () => {
    mockFetch(routes());
    renderWithProviders(<Settings />);

    const appId = await screen.findByLabelText("App ID");
    expect(appId).toHaveValue("123");
    expect(screen.getByText(SETTINGS.webhook_url)).toBeInTheDocument();
    expect(screen.getByText("key file present")).toBeInTheDocument();
    expect(screen.getByText(/Reviews include up to 120,000 diff characters/)).toBeInTheDocument();

    const secret = screen.getByLabelText("Webhook secret");
    expect(secret).toHaveAttribute("type", "text");
    await userEvent.click(secret);
    await userEvent.keyboard("new-secret");
    expect(secret).toHaveValue("new-secret");
    expect(secret).toHaveAttribute("type", "password");
  });

  it("saves edited settings and discards unsaved changes", async () => {
    const fetch = mockFetch(
      routes({
        "PUT /api/v1/settings": (_url: URL, init: RequestInit) => ({
          ...SETTINGS,
          ...(JSON.parse(String(init.body)) as object),
        }),
      }),
    );
    renderWithProviders(<Settings />);

    const save = await screen.findByRole("button", { name: "Save settings" });
    const discard = screen.getByRole("button", { name: "Discard" });
    expect(save).toBeDisabled();

    const model = screen.getByLabelText("Model");
    await userEvent.clear(model);
    await userEvent.type(model, "gemini-2.5-pro");
    expect(save).toBeEnabled();
    await userEvent.click(discard);
    expect(model).toHaveValue("gemini-2.0-flash");

    await userEvent.type(screen.getByLabelText("App slug"), "-x");
    await userEvent.click(save);
    expect(await screen.findByText("Settings saved")).toBeInTheDocument();
    const put = fetch.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toMatchObject({ github_app_slug: "reviewpilot-x" });
  });

  it("shows the server error when saving fails", async () => {
    mockFetch(routes({ "PUT /api/v1/settings": () => json({ detail: "App ID must be numeric" }, 422) }));
    renderWithProviders(<Settings />);

    await userEvent.type(await screen.findByLabelText("App ID"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("App ID must be numeric")).toBeInTheDocument();
  });

  it("falls back to a generic message when a save fails without a reason", async () => {
    mockFetch(routes({ "PUT /api/v1/settings": () => new Response("", { status: 500, statusText: "" }) }));
    renderWithProviders(<Settings />);

    await userEvent.type(await screen.findByLabelText("App ID"), "9");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Request failed")).toBeInTheDocument();
  });

  it("tests the GitHub connection and validates the Gemini key", async () => {
    const fetch = mockFetch(
      routes({
        "POST /api/v1/settings/validate/github": {
          ok: true,
          message: "Connected",
          app_name: "ReviewPilot",
          installations: 2,
        },
        "POST /api/v1/settings/validate/gemini": { ok: false, message: "Invalid API key" },
      }),
    );
    renderWithProviders(<Settings />);

    await userEvent.click(await screen.findByRole("button", { name: "Test connection" }));
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("· ReviewPilot")).toBeInTheDocument();
    expect(screen.getByText("· 2 installation(s)")).toBeInTheDocument();

    // A masked key is not sent; the server keeps using the stored one.
    await userEvent.click(screen.getByRole("button", { name: "Validate key" }));
    expect(await screen.findByText("Invalid API key")).toBeInTheDocument();
    const masked = fetch.mock.calls.filter(([url]) => String(url).endsWith("/validate/gemini"));
    expect(JSON.parse(String(masked[0]?.[1]?.body))).toEqual({ model: "gemini-2.0-flash" });

    const key = screen.getByLabelText("API key");
    await userEvent.clear(key);
    await userEvent.type(key, "AIza-new");
    await userEvent.click(screen.getByRole("button", { name: "Validate key" }));
    await waitFor(() =>
      expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/validate/gemini"))).toHaveLength(2),
    );
    const typed = fetch.mock.calls.filter(([url]) => String(url).endsWith("/validate/gemini"))[1];
    expect(JSON.parse(String(typed?.[1]?.body))).toEqual({ api_key: "AIza-new", model: "gemini-2.0-flash" });
  });

  it("copies the webhook URL", async () => {
    mockFetch(routes());
    const writeText = vi.fn(async () => undefined);
    renderWithProviders(<Settings />);
    await screen.findByLabelText("App ID");
    // userEvent installs its own clipboard stub, so replace it after setup.
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });

    await userEvent.click(screen.getByRole("button", { name: "Copy webhook URL" }));
    expect(writeText).toHaveBeenCalledWith(SETTINGS.webhook_url);
    expect(await screen.findByText("Copied")).toBeInTheDocument();
  });

  it("is read-only for non-admins", async () => {
    mockFetch(routes({ "GET /api/v1/settings": { ...SETTINGS, is_admin: false, github_private_key_present: false } }));
    renderWithProviders(<Settings />);

    expect(await screen.findByText(/Only admins can change settings/)).toBeInTheDocument();
    expect(screen.getByLabelText("App ID")).toBeDisabled();
    expect(screen.getByText("key file missing")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save settings" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Test connection" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Validate key" })).not.toBeInTheDocument();
    expect(await screen.findByLabelText("Welcome (on-demand mode)")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save replies" })).not.toBeInTheDocument();
  });

  it("shows an error state with retry when settings fail to load", async () => {
    let calls = 0;
    mockFetch(
      routes({
        "GET /api/v1/settings": () => (++calls === 1 ? json({ detail: "boom" }, 500) : SETTINGS),
      }),
    );
    renderWithProviders(<Settings />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText("App ID")).toHaveValue("123");
  });
});

describe("Canned replies", () => {
  it("edits and saves the replies, and blocks saving an empty template", async () => {
    const fetch = mockFetch(
      routes({ "PUT /api/v1/settings/replies": (_url: URL, init: RequestInit) => JSON.parse(String(init.body)) }),
    );
    renderWithProviders(<Settings />);

    const welcome = await screen.findByLabelText("Welcome (on-demand mode)");
    expect(welcome).toHaveValue("Hi {author}");
    const save = screen.getByRole("button", { name: "Save replies" });

    await userEvent.clear(welcome);
    expect(save).toBeDisabled();
    await userEvent.type(welcome, "Hello {{author}");
    expect(save).toBeEnabled();
    await userEvent.click(save);

    expect(await screen.findByText("Replies saved")).toBeInTheDocument();
    const put = fetch.mock.calls.find(([url, init]) => String(url).endsWith("/replies") && init?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({ ...REPLIES, welcome: "Hello {author}" });
  });

  it("shows the error when saving replies fails", async () => {
    mockFetch(routes({ "PUT /api/v1/settings/replies": () => json({ detail: "Template too long" }, 422) }));
    renderWithProviders(<Settings />);

    await userEvent.type(await screen.findByLabelText("Fallback execution plan"), "!");
    await userEvent.click(screen.getByRole("button", { name: "Save replies" }));
    expect(await screen.findByText("Template too long")).toBeInTheDocument();
  });

  it("falls back to a generic message when saving replies fails without a reason", async () => {
    mockFetch(
      routes({ "PUT /api/v1/settings/replies": () => new Response("", { status: 500, statusText: "" }) }),
    );
    renderWithProviders(<Settings />);

    await userEvent.type(await screen.findByLabelText("Empty diff"), "!");
    await userEvent.click(screen.getByRole("button", { name: "Save replies" }));
    expect(await screen.findByText("Request failed")).toBeInTheDocument();
  });
});
