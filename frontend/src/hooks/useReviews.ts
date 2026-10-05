import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { reviewsApi } from "@/services/endpoints";
import type { Rating, ReviewDetail, ReviewFilters } from "@/types/api";

export const useReviews = (filters: ReviewFilters, options: { refetchInterval?: number } = {}) =>
  useQuery({
    queryKey: ["reviews", filters],
    queryFn: () => reviewsApi.list(filters),
    placeholderData: keepPreviousData,
    refetchInterval: options.refetchInterval,
  });

export const useReview = (id: number | null) =>
  useQuery({
    queryKey: ["review", id],
    queryFn: () => reviewsApi.get(id as number),
    enabled: id !== null,
  });

export function useSubmitFeedback(reviewId: number) {
  const queryClient = useQueryClient();
  const key = ["review", reviewId];
  return useMutation({
    mutationFn: ({ rating, notes }: { rating: Rating; notes: string }) =>
      reviewsApi.feedback(reviewId, rating, notes),
    // Optimistic update so the selected rating is highlighted immediately.
    onMutate: async ({ rating, notes }) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<ReviewDetail>(key);
      if (previous) {
        const counts = { ...previous.feedback_counts };
        if (previous.my_feedback) counts[previous.my_feedback.rating] -= 1;
        counts[rating] += 1;
        queryClient.setQueryData<ReviewDetail>(key, {
          ...previous,
          feedback_counts: counts,
          my_feedback: {
            id: previous.my_feedback?.id ?? -1,
            review_id: reviewId,
            user_id: previous.my_feedback?.user_id ?? null,
            rating,
            notes,
            created_at: new Date().toISOString(),
          },
        });
      }
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: key });
      void queryClient.invalidateQueries({ queryKey: ["reviews"] });
      void queryClient.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
}
