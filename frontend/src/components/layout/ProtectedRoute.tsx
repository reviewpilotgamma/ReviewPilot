import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { FullPageSpinner } from "@/components/ui/Spinner";
import { useAuth } from "@/hooks/useAuth";

export function ProtectedRoute() {
  const { user, isLoading, login } = useAuth();
  const location = useLocation();
  const redirecting = !isLoading && !user;

  useEffect(() => {
    if (redirecting) login(location.pathname + location.search);
  }, [redirecting, login, location.pathname, location.search]);

  if (isLoading) return <FullPageSpinner />;
  if (!user) return <FullPageSpinner label="Redirecting to GitHub sign-in…" />;
  return <Outlet />;
}
