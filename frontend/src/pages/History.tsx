import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ReviewDrawer } from "@/components/reviews/ReviewDrawer";
import { ReviewFilters, type FilterValues } from "@/components/reviews/ReviewFilters";
import { ReviewsTable } from "@/components/reviews/ReviewsTable";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useWorkspace } from "@/hooks/useAuth";
import { useDebounce } from "@/hooks/useDebounce";
import { useReviews } from "@/hooks/useReviews";
import type { Verdict } from "@/types/api";

const PAGE_SIZE = 20;
const VERDICTS: Verdict[] = ["passed", "warning", "critical"];

export default function History() {
  const [params, setParams] = useSearchParams();
  const { repos } = useWorkspace();

  const verdictParam = params.get("verdict") as Verdict | null;
  const urlFilters: FilterValues = {
    repo: params.get("repo") ?? "",
    author: params.get("author") ?? "",
    verdict: verdictParam && VERDICTS.includes(verdictParam) ? verdictParam : "",
    q: params.get("q") ?? "",
  };
  const page = Math.max(1, Number(params.get("page") ?? "1") || 1);
  const reviewParam = params.get("review");
  const openReview = reviewParam && /^\d+$/.test(reviewParam) ? Number(reviewParam) : null;

  // Text inputs are edited locally and pushed to the URL after a 300 ms debounce.
  const [author, setAuthor] = useState(urlFilters.author);
  const [q, setQ] = useState(urlFilters.q);
  const debouncedAuthor = useDebounce(author);
  const debouncedQ = useDebounce(q);

  const update = (patch: Record<string, string>, resetPage = true) => {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [key, value] of Object.entries(patch)) {
          if (value) next.set(key, value);
          else next.delete(key);
        }
        if (resetPage) next.delete("page");
        return next;
      },
      { replace: true },
    );
  };

  useEffect(() => {
    if (debouncedAuthor !== urlFilters.author || debouncedQ !== urlFilters.q) {
      update({ author: debouncedAuthor.trim(), q: debouncedQ.trim() });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedAuthor, debouncedQ]);

  const query = useMemo(
    () => ({
      repo: urlFilters.repo || undefined,
      author: urlFilters.author || undefined,
      verdict: urlFilters.verdict || undefined,
      q: urlFilters.q || undefined,
      page,
      page_size: PAGE_SIZE,
    }),
    [urlFilters.repo, urlFilters.author, urlFilters.verdict, urlFilters.q, page],
  );
  const { data, isLoading, isError, refetch, isFetching } = useReviews(query);
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const hasFilters = Boolean(urlFilters.repo || urlFilters.author || urlFilters.verdict || urlFilters.q);

  return (
    <div className="space-y-6">
      <Card>
        <ReviewFilters
          values={{ ...urlFilters, author, q }}
          repos={repos}
          onChange={(patch) => {
            if (patch.author !== undefined) setAuthor(patch.author);
            if (patch.q !== undefined) setQ(patch.q);
            if (patch.repo !== undefined) update({ repo: patch.repo });
            if (patch.verdict !== undefined) update({ verdict: patch.verdict });
          }}
        />
      </Card>

      <Card
        title="PR reviews"
        description={data ? `${data.total.toLocaleString()} review${data.total === 1 ? "" : "s"}` : undefined}
      >
        {isError ? (
          <ErrorState onRetry={() => void refetch()} />
        ) : data && data.items.length === 0 ? (
          <EmptyState
            title={hasFilters ? "No reviews match these filters" : "No reviews yet"}
            description={hasFilters ? "Try clearing a filter." : "Reviews appear here once ReviewPilot audits a PR."}
          />
        ) : (
          <ReviewsTable
            reviews={data?.items ?? []}
            loading={isLoading}
            showFeedback
            onSelect={(id) => update({ review: String(id) }, false)}
          />
        )}

        {data && data.total > PAGE_SIZE && (
          <div className="mt-4 flex items-center justify-between text-sm text-muted">
            <span>
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1 || isFetching}
                icon={<ChevronLeft className="h-4 w-4" />}
                onClick={() => update({ page: String(page - 1) }, false)}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= totalPages || isFetching}
                onClick={() => update({ page: String(page + 1) }, false)}
              >
                Next <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </Card>

      <ReviewDrawer reviewId={openReview} onClose={() => update({ review: "" }, false)} />
    </div>
  );
}
