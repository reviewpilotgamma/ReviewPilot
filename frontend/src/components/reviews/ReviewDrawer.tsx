import { ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import { MarkdownView } from "@/components/diff/MarkdownView";
import { FollowUpBadge, PartialBadge, VerdictBadge } from "@/components/ui/Badge";
import { Drawer } from "@/components/ui/Overlay";
import { ErrorState } from "@/components/ui/States";
import { Spinner } from "@/components/ui/Spinner";
import { useReview } from "@/hooks/useReviews";
import { absoluteTime, formatScore } from "@/lib/format";
import type { ReviewDetail } from "@/types/api";
import { FeedbackWidget } from "./FeedbackWidget";
import { ReviewedWith } from "./ReviewedWith";

function triggerText(review: ReviewDetail): string {
  const followUp = review.previous_review_id != null;
  if (review.trigger === "push") return followUp ? "Follow-up after push" : "Review after push";
  if (review.trigger === "auto") return "Auto review on open";
  const requester = `@${review.requester ?? "unknown"}`;
  return followUp ? `Follow-up requested by ${requester}` : `Requested by ${requester}`;
}

export function ReviewDrawer({ reviewId, onClose }: { reviewId: number | null; onClose: () => void }) {
  const { data: review, isLoading, isError, refetch } = useReview(reviewId);

  const title = review ? (
    <div className="space-y-1.5">
      <p className="text-xs text-muted">
        {review.repo_full_name} · #{review.pr_number}
      </p>
      <h2 className="text-lg font-semibold leading-snug">{review.pr_title}</h2>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <VerdictBadge verdict={review.verdict} />
        {review.previous_review_id != null && <FollowUpBadge />}
        {review.diff_truncated && <PartialBadge />}
        <span className="font-medium text-ink">{formatScore(review.score)}</span>
        <span>·</span>
        <span>{absoluteTime(review.created_at)}</span>
        <span>·</span>
        <span>{triggerText(review)}</span>
        {review.previous_review_id != null && (
          <Link to={`/history?review=${review.previous_review_id}`} className="text-violet hover:underline">
            Previous review
          </Link>
        )}
        <a
          href={review.pr_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-violet hover:underline"
        >
          Open on GitHub <ExternalLink className="h-3 w-3" />
        </a>
      </div>
      <ReviewedWith context={review.review_context} />
    </div>
  ) : (
    <h2 className="text-lg font-semibold">Review</h2>
  );

  return (
    <Drawer
      open={reviewId !== null}
      onClose={onClose}
      title={title}
      footer={
        review && (
          <FeedbackWidget
            key={review.id}
            reviewId={review.id}
            myFeedback={review.my_feedback}
            counts={review.feedback_counts}
          />
        )
      }
    >
      {isLoading && (
        <div className="flex justify-center py-16">
          <Spinner className="h-6 w-6" />
        </div>
      )}
      {isError && <ErrorState message="Could not load this review." onRetry={() => void refetch()} />}
      {review && <MarkdownView markdown={review.full_markdown} />}
    </Drawer>
  );
}
