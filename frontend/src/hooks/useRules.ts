import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { rulesApi } from "@/services/endpoints";
import type { RuleInput } from "@/types/api";

export const usePresets = () =>
  useQuery({ queryKey: ["presets"], queryFn: rulesApi.presets, staleTime: Infinity });

export const useRule = (repo: string) =>
  useQuery({ queryKey: ["rule", repo], queryFn: () => rulesApi.get(repo), enabled: Boolean(repo) });

export const useRepoDocuments = (repo: string) =>
  useQuery({
    queryKey: ["repo-documents", repo],
    queryFn: () => rulesApi.listDocuments(repo),
    enabled: Boolean(repo),
  });

export function useSaveRule(repo: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RuleInput) => rulesApi.save(repo, body),
    onSuccess: (rule) => {
      queryClient.setQueryData(["rule", repo], rule);
      void queryClient.invalidateQueries({ queryKey: ["rules"] });
      void queryClient.invalidateQueries({ queryKey: ["installations"] });
    },
  });
}

export function useResetRule(repo: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => rulesApi.reset(repo),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["rule", repo] });
      void queryClient.invalidateQueries({ queryKey: ["rules"] });
      void queryClient.invalidateQueries({ queryKey: ["installations"] });
    },
  });
}

export function useUploadDocument(repo: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => rulesApi.uploadDocument(repo, file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repo-documents", repo] });
    },
  });
}

export function useDeleteDocument(repo: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => rulesApi.deleteDocument(repo, id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repo-documents", repo] });
    },
  });
}
