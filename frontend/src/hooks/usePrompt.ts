import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { promptApi } from "@/services/endpoints";

const KEY = ["prompt"] as const;

export const usePrompt = () => useQuery({ queryKey: KEY, queryFn: promptApi.get, staleTime: 60_000 });

export function useSavePrompt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (template: string) => promptApi.save(template),
    onSuccess: (prompt) => queryClient.setQueryData(KEY, prompt),
  });
}

export function useResetPrompt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => promptApi.reset(),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
  });
}
