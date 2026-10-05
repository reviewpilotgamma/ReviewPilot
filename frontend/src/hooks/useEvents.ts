import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/services/endpoints";
import type { EventFilters } from "@/types/api";

export const EVENTS_POLL_MS = 5_000;

/** Live activity feed: polls every 5 s while the tab is visible. */
export const useEvents = (filters: EventFilters, enabled = true) =>
  useQuery({
    queryKey: ["events", filters],
    queryFn: () => eventsApi.list(filters),
    enabled,
    refetchInterval: EVENTS_POLL_MS,
    refetchIntervalInBackground: false,
  });
