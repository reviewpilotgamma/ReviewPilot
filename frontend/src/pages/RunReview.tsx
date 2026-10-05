import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useWorkspace } from "@/hooks/useAuth";
import { ApiError } from "@/services/client";
import { reviewsApi } from "@/services/endpoints";

const DEFAULT_REPO = "local/manual";

export default function RunReview() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { repos, selectedRepo } = useWorkspace();
  const [repo, setRepo] = useState(selectedRepo || repos[0]?.full_name || DEFAULT_REPO);
  const [prNumber, setPrNumber] = useState("1");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [focusNote, setFocusNote] = useState("");
  const [diff, setDiff] = useState("");
  const [error, setError] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: reviewsApi.runManual,
    onSuccess: async (review) => {
      await queryClient.invalidateQueries({ queryKey: ["installations"] });
      await queryClient.invalidateQueries({ queryKey: ["reviews"] });
      await queryClient.invalidateQueries({ queryKey: ["metrics"] });
      navigate(`/history?review=${review.id}`);
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : "The review could not be completed");
    },
  });

  const number = Number(prNumber);
  const canSubmit = repo.includes("/") && title.trim().length > 0 && diff.trim().length > 0 && Number.isInteger(number) && number >= 1;

  const submit = () => {
    setError(null);
    run.mutate({
      repo: repo.trim(),
      pr_number: number,
      title: title.trim(),
      description: description.trim(),
      focus_note: focusNote.trim(),
      diff,
    });
  };

  return (
    <div className="mx-auto max-w-3xl">
      <Card
        title="Run a review"
        description="Paste a pull request diff. ReviewPilot runs the same pipeline a GitHub webhook will use later, then saves the result on this dashboard. Nothing is posted to GitHub."
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (canSubmit && !run.isPending) submit();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
            <div>
              <label htmlFor="run-repo" className="label">
                Repository
              </label>
              <input
                id="run-repo"
                className="input"
                list="run-repos"
                value={repo}
                onChange={(event) => setRepo(event.target.value)}
                placeholder="owner/name"
                autoComplete="off"
                required
              />
              <datalist id="run-repos">
                {repos.map((item) => (
                  <option key={item.full_name} value={item.full_name} />
                ))}
              </datalist>
            </div>
            <div>
              <label htmlFor="run-pr" className="label">
                PR number
              </label>
              <input
                id="run-pr"
                className="input"
                inputMode="numeric"
                value={prNumber}
                onChange={(event) => setPrNumber(event.target.value)}
                required
              />
            </div>
          </div>

          <div>
            <label htmlFor="run-title" className="label">
              Title
            </label>
            <input
              id="run-title"
              className="input"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Add retries to the payment client"
              required
            />
          </div>

          <div>
            <label htmlFor="run-description" className="label">
              Description
            </label>
            <textarea
              id="run-description"
              className="input min-h-20"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Optional. What this change is trying to do."
            />
          </div>

          <div>
            <label htmlFor="run-note" className="label">
              Focus note
            </label>
            <input
              id="run-note"
              className="input"
              value={focusNote}
              onChange={(event) => setFocusNote(event.target.value)}
              placeholder="Optional. For example: check idempotency on the charge call"
            />
          </div>

          <div>
            <label htmlFor="run-diff" className="label">
              Diff
            </label>
            <textarea
              id="run-diff"
              className="input min-h-64 font-mono text-xs leading-5"
              value={diff}
              onChange={(event) => setDiff(event.target.value)}
              placeholder={"diff --git a/payments/client.py b/payments/client.py\n+    response = requests.post(url)"}
              spellCheck={false}
              required
            />
          </div>

          {error && (
            <p role="alert" className="text-sm text-rose">
              {error}
            </p>
          )}

          <div className="flex justify-end">
            <Button type="submit" icon={<Sparkles className="h-4 w-4" />} loading={run.isPending} disabled={!canSubmit}>
              Run review
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
