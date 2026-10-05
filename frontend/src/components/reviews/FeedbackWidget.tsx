import clsx from "clsx";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/hooks/useAuth";
import { useSubmitFeedback } from "@/hooks/useReviews";
import type { Feedback, FeedbackCounts, Rating } from "@/types/api";

interface FeedbackWidgetProps {
  reviewId: number;
  myFeedback: Feedback | null;
  counts: FeedbackCounts;
}

const MAX_NOTES = 2000;

export function FeedbackWidget({ reviewId, myFeedback, counts }: FeedbackWidgetProps) {
  const toast = useToast();
  const mutation = useSubmitFeedback(reviewId);
  const [pending, setPending] = useState<Rating | null>(null);
  const [notes, setNotes] = useState(myFeedback?.notes ?? "");
  const selected = pending ?? myFeedback?.rating ?? null;

  const submit = (rating: Rating) => {
    mutation.mutate(
      { rating, notes: notes.trim() },
      {
        onSuccess: () => {
          setPending(null);
          toast.success("Thanks for the feedback!");
        },
        onError: () => toast.error("Could not save feedback. Please try again."),
      },
    );
  };

  const option = (rating: Rating, label: string, Icon: typeof ThumbsUp, count: number) => (
    <button
      type="button"
      aria-pressed={selected === rating}
      onClick={() => setPending(rating)}
      className={clsx(
        "inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition duration-150",
        selected === rating
          ? rating === "helpful"
            ? "border-emerald bg-emerald-soft text-emerald"
            : "border-rose bg-rose-soft text-rose"
          : "border-border text-muted hover:text-text",
      )}
    >
      <Icon className="h-4 w-4" /> {label}
      <span className="text-xs opacity-70">{count}</span>
    </button>
  );

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">Was this review helpful?</span>
        {option("helpful", "Yes", ThumbsUp, counts.helpful)}
        {option("unhelpful", "No", ThumbsDown, counts.unhelpful)}
      </div>
      {pending && (
        <div className="mt-3 space-y-2">
          <label htmlFor="feedback-notes" className="label">
            Optional notes
          </label>
          <textarea
            id="feedback-notes"
            className="input min-h-[80px]"
            maxLength={MAX_NOTES}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="What was useful or missing?"
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setPending(null)}>
              Cancel
            </Button>
            <Button size="sm" loading={mutation.isPending} onClick={() => submit(pending)}>
              Submit feedback
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
