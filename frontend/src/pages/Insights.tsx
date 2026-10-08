import { RefreshCw, ScanSearch } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { MarkdownView } from "@/components/diff/MarkdownView";
import { VerdictBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Overlay";
import { FullPageSpinner } from "@/components/ui/Spinner";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useToast, useWorkspace } from "@/hooks/useAuth";
import { useAnalyzeInsights, useInsights } from "@/hooks/useInsights";
import { absoluteTime } from "@/lib/format";
import { ApiError } from "@/services/client";
import type { InsightState, InsightTheme } from "@/types/api";

function pendingCopy(state: InsightState): string {
  const n = state.pending_count;
  const reviewWord = n === 1 ? "review" : "reviews";
  if (!state.snapshot) {
    if (state.pending_capped) {
      return `${n.toLocaleString()} ReviewPilot comments are ready. This run will include the oldest 50.`;
    }
    return `${n.toLocaleString()} ReviewPilot ${reviewWord} ${n === 1 ? "is" : "are"} ready to analyze.`;
  }
  if (n === 0) return "No new reviews since the last analysis.";
  if (state.pending_capped) {
    return `${n.toLocaleString()} new reviews since the last analysis. This run will include the next 50.`;
  }
  return `${n.toLocaleString()} new ${reviewWord} since the last analysis (${state.total_reviews.toLocaleString()} total in this repo).`;
}

function ThemeCard({ theme }: { theme: InsightTheme }) {
  return (
    <article className="rounded-xl border border-border bg-surface/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">{theme.title}</h3>
        <div className="flex items-center gap-2">
          <VerdictBadge verdict={theme.severity} />
          <span className="text-xs text-muted">Seen {theme.count} times</span>
        </div>
      </div>
      {theme.evidence && <p className="mt-2 text-sm text-muted">{theme.evidence}</p>}
      {theme.example_review_ids.length > 0 && (
        <p className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs">
          {theme.example_review_ids.map((id) => (
            <Link key={id} to={`/history?review=${id}`} className="text-violet hover:underline">
              Review {id}
            </Link>
          ))}
        </p>
      )}
    </article>
  );
}

export default function Insights() {
  const { selectedRepo } = useWorkspace();
  const toast = useToast();
  const { data, isLoading, isError, refetch } = useInsights(selectedRepo || undefined);
  const analyze = useAnalyzeInsights(selectedRepo || undefined);
  const [rebuildOpen, setRebuildOpen] = useState(false);

  const run = (rebuild: boolean) => {
    analyze.mutate(rebuild, {
      onSuccess: (state) => {
        setRebuildOpen(false);
        if (!state.ran_model) toast.info("Nothing new to analyze.");
        else toast.success("Insights updated.");
      },
      onError: (error) => {
        toast.error(error instanceof ApiError ? error.message : "Insight generation failed.");
      },
    });
  };

  if (!selectedRepo) {
    return (
      <Card>
        <EmptyState
          icon={<ScanSearch className="h-6 w-6" />}
          title="Select a repository"
          description="Insights are per repository. Choose one in the header to analyze its ReviewPilot comments."
        />
      </Card>
    );
  }

  if (isLoading && !data) return <FullPageSpinner />;

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted">
        Recurring themes from stored ReviewPilot reviews for <span className="text-ink">{selectedRepo}</span>.
        New runs merge the last summary with only the comments added since then.
      </p>

      {isError ? (
        <Card>
          <ErrorState onRetry={() => void refetch()} />
        </Card>
      ) : data ? (
        <>
          <Card
            title="Analyze comments"
            description={pendingCopy(data)}
            actions={
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  loading={analyze.isPending && !rebuildOpen}
                  disabled={
                    analyze.isPending ||
                    data.total_reviews === 0 ||
                    (data.pending_count === 0 && Boolean(data.snapshot))
                  }
                  icon={<ScanSearch className="h-4 w-4" />}
                  onClick={() => run(false)}
                >
                  {data.snapshot
                    ? `Analyze ${data.pending_count} new review${data.pending_count === 1 ? "" : "s"}`
                    : "Analyze"}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={analyze.isPending || data.total_reviews === 0}
                  icon={<RefreshCw className="h-4 w-4" />}
                  onClick={() => setRebuildOpen(true)}
                >
                  Regenerate from scratch
                </Button>
              </div>
            }
          />

          {!data.snapshot ? (
            <Card>
              <EmptyState
                icon={<ScanSearch className="h-6 w-6" />}
                title={data.total_reviews === 0 ? "No reviews yet" : "No analysis yet"}
                description={
                  data.total_reviews === 0
                    ? "Insights appear after ReviewPilot has reviewed pull requests in this repository."
                    : "Run Analyze to extract recurring architectural themes from the stored comments."
                }
              />
            </Card>
          ) : (
            <>
              <Card
                title="Summary"
                description={`Last run ${absoluteTime(data.snapshot.created_at)} by @${data.snapshot.created_by} · ${data.snapshot.included_count} reviews covered · ${data.snapshot.model}`}
              >
                <MarkdownView markdown={data.snapshot.summary_markdown} />
                {(data.snapshot.new_this_period.length > 0 || data.snapshot.still_showing.length > 0) && (
                  <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                    {data.snapshot.new_this_period.length > 0 && (
                      <div>
                        <dt className="text-xs font-medium uppercase tracking-wide text-muted">New this period</dt>
                        <dd className="mt-1 text-ink">{data.snapshot.new_this_period.join(", ")}</dd>
                      </div>
                    )}
                    {data.snapshot.still_showing.length > 0 && (
                      <div>
                        <dt className="text-xs font-medium uppercase tracking-wide text-muted">Still showing</dt>
                        <dd className="mt-1 text-ink">{data.snapshot.still_showing.join(", ")}</dd>
                      </div>
                    )}
                  </dl>
                )}
              </Card>
              <Card title="Themes" description={`${data.snapshot.themes.length} recurring issue${data.snapshot.themes.length === 1 ? "" : "s"}`}>
                {data.snapshot.themes.length === 0 ? (
                  <p className="text-sm text-muted">The last run did not return structured themes.</p>
                ) : (
                  <div className="grid gap-3">
                    {data.snapshot.themes.map((theme) => (
                      <ThemeCard key={`${theme.title}-${theme.last_seen_review_id}`} theme={theme} />
                    ))}
                  </div>
                )}
              </Card>
            </>
          )}
        </>
      ) : null}

      <Modal
        open={rebuildOpen}
        onClose={() => setRebuildOpen(false)}
        title="Regenerate from scratch?"
        actions={
          <>
            <Button variant="ghost" size="sm" onClick={() => setRebuildOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" loading={analyze.isPending} onClick={() => run(true)}>
              Regenerate
            </Button>
          </>
        }
      >
        This ignores the previous summary and re-analyzes up to the 50 most recent reviews in {selectedRepo}.
      </Modal>
    </div>
  );
}
