import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { settingsApi } from "@/services/endpoints";
import type { Replies, SettingsInput } from "@/types/api";

export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: settingsApi.get });

export const useReplies = () => useQuery({ queryKey: ["replies"], queryFn: settingsApi.replies });

export function useSaveSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SettingsInput) => settingsApi.save(body),
    onSuccess: (settings) => {
      queryClient.setQueryData(["settings"], settings);
      void queryClient.invalidateQueries({ queryKey: ["app"] });
    },
  });
}

export function useSaveReplies() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Replies) => settingsApi.saveReplies(body),
    onSuccess: (replies) => queryClient.setQueryData(["replies"], replies),
  });
}

export const useValidateGemini = () => useMutation({ mutationFn: settingsApi.validateGemini });
export const useValidateGithub = () => useMutation({ mutationFn: settingsApi.validateGithub });
