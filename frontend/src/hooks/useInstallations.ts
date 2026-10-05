import { useQuery } from "@tanstack/react-query";
import { githubApi } from "@/services/endpoints";

export const useInstallations = (options: { pollWhileEmpty?: boolean } = {}) =>
  useQuery({
    queryKey: ["installations"],
    queryFn: () => githubApi.installations(),
    staleTime: 60_000,
    refetchInterval: (query) =>
      options.pollWhileEmpty && (query.state.data?.length ?? 0) === 0 ? 10_000 : false,
  });

export const useAppInfo = () =>
  useQuery({ queryKey: ["app"], queryFn: githubApi.app, staleTime: 10 * 60_000 });
