import clsx from "clsx";
import { Activity, History, LayoutDashboard, Settings, SlidersHorizontal, Sparkles } from "lucide-react";
import { NavLink } from "react-router-dom";
import { Brand } from "./Brand";

export const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/run", label: "Run review", icon: Sparkles },
  { to: "/rules", label: "Rules", icon: SlidersHorizontal },
  { to: "/history", label: "Review History", icon: History },
  { to: "/activity", label: "Activity", icon: Activity },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export function Sidebar({ open, onNavigate }: { open: boolean; onNavigate: () => void }) {
  return (
    <aside
      className={clsx(
        "fixed inset-y-0 left-0 z-40 w-60 border-r border-border bg-surface/95 backdrop-blur-md transition-transform duration-200 md:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full",
      )}
    >
      <div className="flex h-16 items-center px-5">
        <Brand to="/dashboard" />
      </div>
      <nav aria-label="Main" className="mt-2 flex flex-col gap-1 px-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              clsx(
                "relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition duration-150",
                isActive
                  ? "bg-violet-soft text-text before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-violet"
                  : "text-muted hover:bg-border/40 hover:text-text",
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
