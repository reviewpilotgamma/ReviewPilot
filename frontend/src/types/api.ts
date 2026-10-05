// TypeScript mirrors of the backend Pydantic schemas (backend/app/schemas).

export type Verdict = "passed" | "warning" | "critical";
export type Verbosity = "concise" | "detailed";
export type ReviewMode = "auto" | "on_demand";
export type Rating = "helpful" | "unhelpful";
export type EventStatus = "queued" | "processed" | "ignored" | "failed";
export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface User {
  id: number;
  github_id: number;
  username: string;
  avatar_url: string | null;
  email: string | null;
  is_admin: boolean;
}

export interface AppInfo {
  configured: boolean;
  slug: string;
  name: string;
  install_url: string;
  html_url: string;
  local_mode: boolean;
}

export interface Repo {
  full_name: string;
  private: boolean;
  html_url: string;
  has_rules: boolean;
}

export interface Installation {
  installation_id: number;
  account_login: string;
  account_type: string;
  avatar_url: string;
  repos: Repo[];
}

export interface RuleInput {
  custom_instructions: string;
  verbosity: Verbosity;
  review_mode: ReviewMode;
  enable_security: boolean;
}

export interface Rule extends RuleInput {
  repo_full_name: string;
  updated_at: string | null;
  is_default: boolean;
}

export interface Preset {
  id: string;
  name: string;
  description: string;
  instructions: string;
}

export interface Feedback {
  id: number;
  review_id: number;
  user_id: number | null;
  rating: Rating;
  notes: string;
  created_at: string;
}

export interface FeedbackCounts {
  helpful: number;
  unhelpful: number;
}

export interface ReviewListItem {
  id: number;
  repo_full_name: string;
  pr_number: number;
  pr_title: string;
  author: string;
  verdict: Verdict;
  score: number;
  lines_reviewed: number;
  summary: string;
  created_at: string;
  trigger: string;
  pr_url: string;
  feedback_counts: FeedbackCounts;
}

export interface ReviewDetail extends ReviewListItem {
  full_markdown: string;
  requester: string | null;
  diff_truncated: boolean;
  model: string;
  my_feedback: Feedback | null;
}

export interface ManualReviewInput {
  repo: string;
  pr_number: number;
  title: string;
  description: string;
  focus_note: string;
  diff: string;
}

export interface ReviewFilters {
  repo?: string;
  author?: string;
  verdict?: Verdict;
  q?: string;
  page?: number;
  page_size?: number;
}

export interface MetricsSummary {
  total_reviews: number;
  avg_score: number | null;
  pass_rate: number | null;
  helpful_rate: number | null;
  verdict_counts: Record<Verdict, number>;
  recent: ReviewListItem[];
}

export interface TrendPoint {
  date: string;
  reviews: number;
  avg_score: number | null;
}

export interface Job {
  id: number;
  kind: "review" | "welcome" | "plan";
  status: JobStatus;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  review_id: number | null;
  next_run_at: string;
  updated_at: string;
}

export interface WebhookEvent {
  id: number;
  delivery_id: string | null;
  event: string;
  action: string | null;
  repo: string | null;
  sender: string | null;
  payload_preview: string;
  status: EventStatus;
  error_message: string | null;
  created_at: string;
  jobs: Job[];
}

export interface EventFilters {
  status?: EventStatus;
  repo?: string;
  limit?: number;
  before_id?: number;
}

export interface Settings {
  github_app_id: string;
  github_app_slug: string;
  github_webhook_secret: string;
  github_private_key_path: string;
  github_private_key_present: boolean;
  github_client_id: string;
  github_client_secret: string;
  gemini_api_key: string;
  gemini_model: string;
  max_diff_chars: number;
  webhook_url: string;
  is_admin: boolean;
}

export type SettingsInput = Partial<
  Pick<
    Settings,
    | "github_app_id"
    | "github_app_slug"
    | "github_webhook_secret"
    | "github_private_key_path"
    | "github_client_id"
    | "github_client_secret"
    | "gemini_api_key"
    | "gemini_model"
  >
>;

export interface ValidationResult {
  ok: boolean;
  message: string;
  model?: string | null;
  app_name?: string | null;
  installations?: number | null;
}

export interface Replies {
  welcome: string;
  plan: string;
  error: string;
  empty_diff: string;
}
