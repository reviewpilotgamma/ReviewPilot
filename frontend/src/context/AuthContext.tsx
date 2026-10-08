import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useEffect, useMemo, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, onUnauthorized } from "@/services/client";
import { authApi } from "@/services/endpoints";
import type { User } from "@/types/api";

export interface AuthState {
  user: User | null;
  isLoading: boolean;
  /** Go to the sign-in page, returning to ``next`` (default: the current location) afterwards. */
  login: (next?: string) => void;
  signIn: (username: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export const ME_QUERY_KEY = ["me"] as const;

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: async () => {
      try {
        return await authApi.me();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: 5 * 60_000,
  });

  useEffect(
    () =>
      onUnauthorized(() => {
        // Session expired: drop cached data, ProtectedRoute will redirect to the sign-in page.
        queryClient.setQueryData(ME_QUERY_KEY, null);
        queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== ME_QUERY_KEY[0] });
      }),
    [queryClient],
  );

  const login = useCallback(
    (next?: string) => {
      const target = next ?? window.location.pathname + window.location.search;
      navigate(`/login?${new URLSearchParams({ next: target }).toString()}`, { replace: true });
    },
    [navigate],
  );

  const signIn = useCallback(
    async (username: string, password: string) => {
      const user = await authApi.login(username, password);
      queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== ME_QUERY_KEY[0] });
      queryClient.setQueryData(ME_QUERY_KEY, user);
      return user;
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      queryClient.clear();
      queryClient.setQueryData(ME_QUERY_KEY, null);
      window.location.assign("/");
    }
  }, [queryClient]);

  const value = useMemo<AuthState>(
    () => ({ user: data ?? null, isLoading, login, signIn, logout }),
    [data, isLoading, login, signIn, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
