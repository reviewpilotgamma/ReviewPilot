import type {
  AppInfo,
  EventFilters,
  Feedback,
  Installation,
  InsightState,
  MetricsSummary,
  Page,
  Preset,
  PromptTemplate,
  Rating,
  Replies,
  ReviewDetail,
  ReviewFilters,
  ReviewListItem,
  RepoDocumentList,
  RepoDocumentUpload,
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
  login: (username: string, password: string) => http.post<User>("/auth/login", { username, password }),
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
  listDocuments: (repo: string) => http.get<RepoDocumentList>(`/rules${repoPath(repo)}/documents`),
  /** `warm: false` skips building the Gemini cache (use for all but the last file of a batch). */
  uploadDocument: (repo: string, file: File, { warm = true }: { warm?: boolean } = {}) => {
    const form = new FormData();
    form.append("file", file);
    const query = warm ? "" : "?warm=false";
    return http.upload<RepoDocumentUpload>(`/rules${repoPath(repo)}/documents${query}`, form);
  },
  deleteDocument: (repo: string, id: number) => http.delete<void>(`/rules${repoPath(repo)}/documents/${id}`),
};

export const promptApi = {
  get: () => http.get<PromptTemplate>("/prompt"),
  save: (template: string) => http.put<PromptTemplate>("/prompt", { template }),
  reset: () => http.delete<void>("/prompt"),
};

export const reviewsApi = {
  list: (filters: ReviewFilters) => http.get<Page<ReviewListItem>>("/reviews", { ...filters }),
  get: (id: number) => http.get<ReviewDetail>(`/reviews/${id}`),
  feedback: (id: number, rating: Rating, notes: string) =>
    http.post<Feedback>(`/reviews/${id}/feedback`, { rating, notes }),
};

export const insightsApi = {
  get: (repo: string) => http.get<InsightState>("/insights", { repo }),
  analyze: (repo: string, rebuild = false) =>
    http.post<InsightState>("/insights/analyze", { repo, rebuild }),
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
