import { ThumbsDown, ThumbsUp } from "lucide-react";
import { PartialBadge, VerdictBadge } from "@/components/ui/Badge";
import { Cell, Row, Table } from "@/components/ui/Table";
import { SkeletonRows } from "@/components/ui/States";
import { absoluteTime, formatScore, relativeTime, scoreTone } from "@/lib/format";
import type { ReviewListItem } from "@/types/api";

const TONE_TEXT = { emerald: "text-emerald", amber: "text-amber", rose: "text-rose", muted: "text-muted" } as const;

interface ReviewsTableProps {
  reviews: ReviewListItem[];
  loading?: boolean;
  onSelect: (id: number) => void;
  showFeedback?: boolean;
}

export function ReviewsTable({ reviews, loading, onSelect, showFeedback = false }: ReviewsTableProps) {
  const head = ["Date", "Repository", "Pull request", "Author", "Verdict", "Score", "Lines"];
  if (showFeedback) head.push("Feedback");
  return (
    <Table head={head}>
      {loading ? (
        <SkeletonRows cols={head.length} />
      ) : (
        reviews.map((review) => (
          <Row key={review.id} onClick={() => onSelect(review.id)} label={`Open review of PR #${review.pr_number}`}>
            <Cell className="whitespace-nowrap text-muted">
              <time dateTime={review.created_at} title={absoluteTime(review.created_at)}>
                {relativeTime(review.created_at)}
              </time>
            </Cell>
            <Cell className="whitespace-nowrap text-muted">{review.repo_full_name}</Cell>
            <Cell>
              <a
                href={review.pr_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(event) => event.stopPropagation()}
                className="font-medium text-violet hover:underline"
              >
                #{review.pr_number}
              </a>{" "}
              <span className="line-clamp-1 inline">{review.pr_title}</span>
            </Cell>
            <Cell className="text-muted">@{review.author}</Cell>
            <Cell>
              <div className="flex flex-wrap items-center gap-1.5">
                <VerdictBadge verdict={review.verdict} />
                {review.diff_truncated && <PartialBadge />}
              </div>
            </Cell>
            <Cell className={`font-medium tabular-nums ${TONE_TEXT[scoreTone(review.score)]}`}>
              {formatScore(review.score)}
            </Cell>
            <Cell className="tabular-nums text-muted">{review.lines_reviewed.toLocaleString()}</Cell>
            {showFeedback && (
              <Cell className="whitespace-nowrap text-xs text-muted">
                <span className="mr-3 inline-flex items-center gap-1">
                  <ThumbsUp className="h-3 w-3" /> {review.feedback_counts.helpful}
                </span>
                <span className="inline-flex items-center gap-1">
                  <ThumbsDown className="h-3 w-3" /> {review.feedback_counts.unhelpful}
                </span>
              </Cell>
            )}
          </Row>
        ))
      )}
    </Table>
  );
}
