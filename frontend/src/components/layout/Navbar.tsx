import { LogOut, Menu } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Select } from "@/components/ui/Controls";
import { InstallAppButton } from "./GithubConnect";
import { useAuth, useWorkspace } from "@/hooks/useAuth";

export function Navbar({ title, onMenu }: { title: string; onMenu: () => void }) {
  const { user, logout } = useAuth();
  const { installations, isLoading: installsLoading, repos, selectedRepo, setSelectedRepo } = useWorkspace();
  const installed = installations.length > 0;
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-bg/80 px-4 backdrop-blur-md md:px-6">
      <button className="rounded-md p-2 text-muted hover:text-ink md:hidden" onClick={onMenu} aria-label="Open navigation">
        <Menu className="h-5 w-5" />
      </button>
      <h1 className="truncate text-lg font-semibold text-ink">{title}</h1>

      <div className="ml-auto flex items-center gap-3">
        {repos.length > 0 && (
          <Select
            aria-label="Repository scope"
            className="hidden w-56 sm:block"
            value={selectedRepo}
            onChange={(event) => setSelectedRepo(event.target.value)}
          >
            <option value="">All repositories</option>
            {repos.map((repo) => (
              <option key={repo.full_name} value={repo.full_name}>
                {repo.full_name}
              </option>
            ))}
          </Select>
        )}

        {!installsLoading && (
          <InstallAppButton
            size="sm"
            variant={installed ? "secondary" : "primary"}
            label={installed ? "Manage GitHub App" : "Install GitHub App"}
          />
        )}

        <div className="relative" ref={menuRef}>
          <button
            className="flex items-center gap-2 rounded-full border border-border p-0.5 pr-3 text-sm text-ink hover:border-violet/50"
            onClick={() => setMenuOpen((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            {user?.avatar_url ? (
              <img src={user.avatar_url} alt="" className="h-7 w-7 rounded-full" />
            ) : (
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-violet-soft text-violet">
                {user?.username.charAt(0).toUpperCase()}
              </span>
            )}
            <span className="hidden sm:inline">{user?.username}</span>
          </button>
          {menuOpen && (
            <div role="menu" className="glass absolute right-0 mt-2 w-48 bg-surface p-1 shadow-xl">
              <div className="px-3 py-2 text-xs text-muted">
                Signed in as <span className="font-medium text-ink">{user?.username}</span>
                {user?.is_admin && <span className="ml-1 text-violet">(admin)</span>}
                {user?.github_login && <span className="block">GitHub: @{user.github_login}</span>}
              </div>
              <button
                role="menuitem"
                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-ink hover:bg-border/50"
                onClick={() => void logout()}
              >
                <LogOut className="h-4 w-4" /> Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
