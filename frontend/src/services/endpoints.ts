import type {
  AppInfo,
  EventFilters,
  Feedback,
  Installation,
  MetricsSummary,
  Page,
  Preset,
  Rating,
  Replies,
  ReviewDetail,
  ReviewFilters,
  ReviewListItem,
  Rule,
  RuleInput,
  Settings,
  SettingsInput,
  TrendPoint,
  User,
  ValidationResult,
  WebhookEvent,
} from "@/types/api";
import { http } from "./client";

/** `owner/repo` -> `/owner/repo` with each segment URL-encoded. */
const repoPath = (fullName: string) =>
  "/" + fullName.split("/").map(encodeURIComponent).join("/");

export const authApi = {
  me: () => http.get<User>("/auth/me"),
  logout: () => http.post<void>("/auth/logout"),
  devLogin: () => http.post<User>("/auth/dev-login"),
};

export const githubApi = {
  app: () => http.get<AppInfo>("/github/app"),
  installations: (refresh = false) =>
    http.get<Installation[]>("/github/installations", { refresh: refresh || undefined }),
};

export const rulesApi = {
  presets: () => http.get<Preset[]>("/rules/presets"),
  list: () => http.get<Rule[]>("/rules"),
  get: (repo: string) => http.get<Rule>(`/rules${repoPath(repo)}`),
  save: (repo: string, body: RuleInput) => http.put<Rule>(`/rules${repoPath(repo)}`, body),
  reset: (repo: string) => http.delete<void>(`/rules${repoPath(repo)}`),
};

export const reviewsApi = {
  list: (filters: ReviewFilters) => http.get<Page<ReviewListItem>>("/reviews", { ...filters }),
  get: (id: number) => http.get<ReviewDetail>(`/reviews/${id}`),
  feedback: (id: number, rating: Rating, notes: string) =>
    http.post<Feedback>(`/reviews/${id}/feedback`, { rating, notes }),
};

export const metricsApi = {
  summary: (repo: string | undefined, days: number) =>
    http.get<MetricsSummary>("/metrics/summary", { repo, days }),
  trend: (repo: string | undefined, days: number) =>
    http.get<TrendPoint[]>("/metrics/trend", { repo, days }),
};

export const eventsApi = {
  list: (filters: EventFilters) => http.get<WebhookEvent[]>("/webhooks/events", { ...filters }),
};

export const settingsApi = {
  get: () => http.get<Settings>("/settings"),
  save: (body: SettingsInput) => http.put<Settings>("/settings", body),
  validateGemini: (body: { api_key?: string; model?: string }) =>
    http.post<ValidationResult>("/settings/validate/gemini", body),
  validateGithub: () => http.post<ValidationResult>("/settings/validate/github"),
  replies: () => http.get<Replies>("/settings/replies"),
  saveReplies: (body: Replies) => http.put<Replies>("/settings/replies", body),
};
