import { CheckCircle2, GitPullRequest, Gauge, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ONBOARDING_DONE_KEY, OnboardingWizard } from "@/components/onboarding/OnboardingWizard";
import { ReviewsTable } from "@/components/reviews/ReviewsTable";
import { Card } from "@/components/ui/Card";
import { SegmentedControl } from "@/components/ui/Controls";
import { MetricCard } from "@/components/ui/MetricCard";
import { FullPageSpinner } from "@/components/ui/Spinner";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useWorkspace } from "@/hooks/useAuth";
import { useAppInfo } from "@/hooks/useInstallations";
import { useMetricsSummary, useMetricsTrend } from "@/hooks/useMetrics";
import { formatPercent, formatScore, scoreTone } from "@/lib/format";
import type { TrendPoint } from "@/types/api";

const PERIODS = [
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
] as const;

function readDone(): boolean {
  try {
    return localStorage.getItem(ONBOARDING_DONE_KEY) === "1";
  } catch {
    return false;
  }
}

function Sparkline({ points }: { points: TrendPoint[] }) {
  const max = Math.max(1, ...points.map((p) => p.reviews));
  const width = 100;
  const height = 28;
  const step = points.length > 1 ? width / (points.length - 1) : width;
  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(2)},${(height - (p.reviews / max) * height).toFixed(2)}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="h-10 w-full" aria-hidden>
      <path d={path} fill="none" stroke="#0f6e62" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { installations, isLoading: installsLoading, isError: installsError, refresh, selectedRepo } = useWorkspace();
  const { data: app, isLoading: appLoading } = useAppInfo();
  const [period, setPeriod] = useState<(typeof PERIODS)[number]["value"]>("30");
  const [onboardingDone, setOnboardingDone] = useState(readDone);
  const days = Number(period);
  const repo = selectedRepo || undefined;
  const summary = useMetricsSummary(repo, days);
  const trend = useMetricsTrend(repo, days);

  if (installsLoading || appLoading) return <FullPageSpinner />;
  if (installsError) return <ErrorState message="Could not load your GitHub installations." onRetry={() => void refresh()} />;

  const showWizard =
    !app?.local_mode && (installations.length === 0 || (!onboardingDone && summary.data?.total_reviews === 0));
  if (showWizard) return <OnboardingWizard onComplete={() => setOnboardingDone(true)} />;

  const data = summary.data;
  const loading = summary.isLoading;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          {repo ? <>Metrics for <span className="text-ink">{repo}</span></> : "Metrics across all your repositories"}
        </p>
        <SegmentedControl label="Period" value={period} onChange={setPeriod} options={[...PERIODS]} />
      </div>

      {summary.isError ? (
        <Card>
          <ErrorState onRetry={() => void summary.refetch()} />
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            label="PRs reviewed"
            value={data ? String(data.total_reviews) : "—"}
            icon={<GitPullRequest className="h-4 w-4" />}
            hint={`Last ${days} days`}
            loading={loading}
          />
          <MetricCard
            label="Avg. architecture health"
            value={formatScore(data?.avg_score)}
            tone={scoreTone(data?.avg_score)}
            icon={<Gauge className="h-4 w-4" />}
            hint="Mean review score"
            loading={loading}
          />
          <MetricCard
            label="Pass rate"
            value={formatPercent(data?.pass_rate)}
            icon={<CheckCircle2 className="h-4 w-4" />}
            hint="Reviews with a Passed verdict"
            loading={loading}
          />
          <MetricCard
            label="Helpful rate"
            value={formatPercent(data?.helpful_rate)}
            icon={<ThumbsUp className="h-4 w-4" />}
            hint="Developer acceptance"
            loading={loading}
          />
        </div>
      )}

      {trend.data && trend.data.some((p) => p.reviews > 0) && (
        <Card title="Review volume" description={`Reviews per day, last ${days} days`}>
          <Sparkline points={trend.data} />
        </Card>
      )}

      <Card title="Recent PR reviews">
        {data && data.recent.length === 0 ? (
          <EmptyState
            title="No reviews yet"
            description={
              <>
                Open a pull request or comment{" "}
                <code className="rounded bg-ink px-1.5 py-0.5 font-mono text-signal-ink">@review</code> on one to get
                your first architectural audit.
              </>
            }
          />
        ) : (
          <ReviewsTable
            reviews={data?.recent ?? []}
            loading={loading}
            onSelect={(id) => navigate(`/history?review=${id}`)}
          />
        )}
      </Card>
    </div>
  );
}
