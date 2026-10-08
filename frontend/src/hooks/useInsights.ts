import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { insightsApi } from "@/services/endpoints";

export const useInsights = (repo: string | undefined) =>
  useQuery({
    queryKey: ["insights", repo ?? ""],
    queryFn: () => insightsApi.get(repo as string),
    enabled: Boolean(repo),
  });

export function useAnalyzeInsights(repo: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (rebuild: boolean) => insightsApi.analyze(repo as string, rebuild),
    onSuccess: (data) => {
      if (repo) queryClient.setQueryData(["insights", repo], data);
    },
  });
}
