import { createContext, useCallback, useMemo, useState, type ReactNode } from "react";
import { useInstallations } from "@/hooks/useInstallations";
import type { Installation, Repo } from "@/types/api";

const STORAGE_KEY = "rp_selected_repo";

export interface WorkspaceState {
  installations: Installation[];
  repos: Repo[];
  isLoading: boolean;
  isError: boolean;
  /** Selected repository (lowercase owner/repo) or "" for all repositories. */
  selectedRepo: string;
  setSelectedRepo: (repo: string) => void;
  refresh: () => Promise<unknown>;
}

export const WorkspaceContext = createContext<WorkspaceState | null>(null);

function readStored(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { data, isLoading, isError, refetch } = useInstallations();
  const [stored, setStored] = useState(readStored);

  const installations = useMemo(() => data ?? [], [data]);
  const repos = useMemo(() => installations.flatMap((i) => i.repos), [installations]);
  // Ignore a remembered repo the user can no longer access.
  const selectedRepo = repos.some((r) => r.full_name === stored) ? stored : "";

  const setSelectedRepo = useCallback((repo: string) => {
    setStored(repo);
    try {
      localStorage.setItem(STORAGE_KEY, repo);
    } catch {
      /* storage unavailable: selection is still kept in memory */
    }
  }, []);

  const value = useMemo<WorkspaceState>(
    () => ({ installations, repos, isLoading, isError, selectedRepo, setSelectedRepo, refresh: refetch }),
    [installations, repos, isLoading, isError, selectedRepo, setSelectedRepo, refetch],
  );
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}
