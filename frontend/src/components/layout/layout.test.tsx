import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Navbar } from "@/components/layout/Navbar";
import { mockFetch, renderWithProviders, testUser } from "@/test/utils";

const APP = { configured: true, slug: "reviewpilot", name: "ReviewPilot", install_url: "", html_url: "" };

describe("Navbar", () => {
  it("opens the account menu, closes it on an outside click, and logs out", async () => {
    mockFetch({ "GET /api/v1/github/app": APP });
    const { auth } = renderWithProviders(<Navbar title="Dashboard" onMenu={() => undefined} />, {
      user: { ...testUser, is_admin: true, avatar_url: "https://avatars.example.com/a.png" },
    });

    const account = screen.getByRole("button", { name: "alice" });
    expect(account.querySelector("img")).toHaveAttribute("src", "https://avatars.example.com/a.png");
    await userEvent.click(account);
    const menu = screen.getByRole("menu");
    expect(menu).toHaveTextContent("Signed in as alice(admin)GitHub: @alice");
    expect(account).toHaveAttribute("aria-expanded", "true");

    fireEvent.mouseDown(menu);
    expect(screen.getByRole("menu")).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await userEvent.click(account);
    await userEvent.click(screen.getByRole("menuitem", { name: "Logout" }));
    expect(auth.logout).toHaveBeenCalledTimes(1);
  });

  it("shows an initial for users without an avatar or GitHub link", async () => {
    mockFetch({ "GET /api/v1/github/app": APP });
    renderWithProviders(<Navbar title="Dashboard" onMenu={() => undefined} />, {
      user: { ...testUser, github_login: null, github_linked: false },
    });
    expect(screen.getByText("A")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "A alice" }));
    expect(screen.getByRole("menu")).not.toHaveTextContent("GitHub:");
    expect(screen.getByRole("menu")).not.toHaveTextContent("(admin)");
  });

  it("scopes the app to a repository and opens the mobile navigation", async () => {
    mockFetch({ "GET /api/v1/github/app": APP });
    const onMenu = vi.fn();
    const { workspace } = renderWithProviders(<Navbar title="Rules" onMenu={onMenu} />);

    await userEvent.selectOptions(screen.getByLabelText("Repository scope"), "acme/web");
    expect(workspace.setSelectedRepo).toHaveBeenCalledWith("acme/web");
    await userEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    expect(onMenu).toHaveBeenCalledTimes(1);
  });

  it("hides the repository picker and install button while nothing is loaded", () => {
    mockFetch({ "GET /api/v1/github/app": APP });
    renderWithProviders(<Navbar title="Rules" onMenu={() => undefined} />, {
      workspace: { installations: [], repos: [], isLoading: true },
    });
    expect(screen.queryByLabelText("Repository scope")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /GitHub App/ })).not.toBeInTheDocument();
  });
});
