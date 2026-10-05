import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useEffect, useMemo, type ReactNode } from "react";
import { ApiError, loginUrl, onUnauthorized } from "@/services/client";
import { authApi } from "@/services/endpoints";
import type { User } from "@/types/api";

export interface AuthState {
  user: User | null;
  isLoading: boolean;
  login: (next?: string) => void;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export const ME_QUERY_KEY = ["me"] as const;

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
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
        // Session expired or GitHub token revoked: drop cached data, ProtectedRoute will redirect.
        queryClient.setQueryData(ME_QUERY_KEY, null);
        queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== ME_QUERY_KEY[0] });
      }),
    [queryClient],
  );

  const login = useCallback((next?: string) => {
    window.location.assign(loginUrl(next ?? window.location.pathname + window.location.search));
  }, []);

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
    () => ({ user: data ?? null, isLoading, login, logout }),
    [data, isLoading, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
