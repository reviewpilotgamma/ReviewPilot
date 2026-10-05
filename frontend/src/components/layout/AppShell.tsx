import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { WorkspaceProvider } from "@/context/WorkspaceContext";
import { Navbar } from "./Navbar";
import { NAV_ITEMS, Sidebar } from "./Sidebar";

export function AppShell() {
  const [navOpen, setNavOpen] = useState(false);
  const { pathname } = useLocation();
  const title = NAV_ITEMS.find((item) => pathname.startsWith(item.to))?.label ?? "ReviewPilot";

  return (
    <WorkspaceProvider>
      <Sidebar open={navOpen} onNavigate={() => setNavOpen(false)} />
      {navOpen && (
        <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={() => setNavOpen(false)} aria-hidden />
      )}
      <div className="md:pl-60">
        <Navbar title={title} onMenu={() => setNavOpen(true)} />
        <main className="mx-auto max-w-[1280px] p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </WorkspaceProvider>
  );
}
