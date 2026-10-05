import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { metricsApi } from "@/services/endpoints";

export const useMetricsSummary = (repo: string | undefined, days: number) =>
  useQuery({
    queryKey: ["metrics", "summary", repo ?? "", days],
    queryFn: () => metricsApi.summary(repo, days),
    placeholderData: keepPreviousData,
  });

export const useMetricsTrend = (repo: string | undefined, days: number) =>
  useQuery({
    queryKey: ["metrics", "trend", repo ?? "", days],
    queryFn: () => metricsApi.trend(repo, days),
    placeholderData: keepPreviousData,
  });
