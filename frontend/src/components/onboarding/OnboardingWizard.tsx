import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, Copy, ExternalLink, GitPullRequest, RefreshCw, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SegmentedControl, Toggle } from "@/components/ui/Controls";
import { useToast, useWorkspace } from "@/hooks/useAuth";
import { useEvents } from "@/hooks/useEvents";
import { useAppInfo, useInstallations } from "@/hooks/useInstallations";
import { useReviews } from "@/hooks/useReviews";
import { usePresets, useSaveRule } from "@/hooks/useRules";
import { relativeTime } from "@/lib/format";
import { githubApi } from "@/services/endpoints";
import type { RuleInput } from "@/types/api";

const STEP_KEY = "rp_onboarding_step";
export const ONBOARDING_DONE_KEY = "rp_onboarding_done";
const STEPS = ["Install the App", "Pick a repository", "Configure rules", "Trigger a review"];

function readStep(): number {
  try {
    return Number(localStorage.getItem(STEP_KEY) ?? "1") || 1;
  } catch {
    return 1;
  }
}

function persist(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* non-critical */
  }
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="ghost"
      size="sm"
      aria-label="Copy"
      icon={copied ? <Check className="h-3.5 w-3.5 text-emerald" /> : <Copy className="h-3.5 w-3.5" />}
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        });
      }}
    />
  );
}

function InstallStep() {
  const { data: app } = useAppInfo();
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  useInstallations({ pollWhileEmpty: true });

  const refresh = async () => {
    setRefreshing(true);
    try {
      queryClient.setQueryData(["installations"], await githubApi.installations(true));
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        Install the ReviewPilot GitHub App on the repositories you want reviewed. ReviewPilot only sees repositories
        you grant it access to.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          icon={<ExternalLink className="h-4 w-4" />}
          disabled={!app?.install_url}
          onClick={() => app?.install_url && window.open(app.install_url, "_blank", "noopener,noreferrer")}
        >
          Install GitHub App
        </Button>
        <Button variant="secondary" loading={refreshing} icon={<RefreshCw className="h-4 w-4" />} onClick={refresh}>
          I've installed it — refresh
        </Button>
      </div>
      {!app?.install_url && (
        <p className="text-xs text-amber">The GitHub App is not configured yet. Ask an admin to complete Settings.</p>
      )}
      <p className="text-xs text-muted">This page checks for new installations every 10 seconds.</p>
    </div>
  );
}

function RepoStep({ onNext }: { onNext: () => void }) {
  const { installations, selectedRepo, setSelectedRepo } = useWorkspace();
  return (
    <div className="space-y-4">
      {installations.map((inst) => (
        <div key={inst.installation_id}>
          <div className="mb-2 flex items-center gap-2 text-sm font-medium">
            {inst.avatar_url && <img src={inst.avatar_url} alt="" className="h-5 w-5 rounded" />}
            {inst.account_login}
            <span className="text-xs text-muted">({inst.account_type})</span>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {inst.repos.map((repo) => (
              <button
                key={repo.full_name}
                type="button"
                onClick={() => setSelectedRepo(repo.full_name)}
                className={clsx(
                  "rounded-lg border px-3 py-2 text-left text-sm transition duration-150",
                  selectedRepo === repo.full_name
                    ? "border-violet bg-violet-soft"
                    : "border-border hover:border-violet/50",
                )}
              >
                {repo.full_name}
                {repo.private && <span className="ml-2 text-xs text-muted">private</span>}
              </button>
            ))}
          </div>
        </div>
      ))}
      <Button disabled={!selectedRepo} onClick={onNext}>
        Continue
      </Button>
    </div>
  );
}

function RulesStep({ onNext }: { onNext: () => void }) {
  const { selectedRepo } = useWorkspace();
  const { data: presets } = usePresets();
  const save = useSaveRule(selectedRepo);
  const toast = useToast();
  const [presetId, setPresetId] = useState<string>("");
  const [rule, setRule] = useState<RuleInput>({
    custom_instructions: "",
    verbosity: "concise",
    review_mode: "auto",
    enable_security: true,
  });

  const choose = (id: string) => {
    setPresetId(id);
    const preset = presets?.find((p) => p.id === id);
    setRule((current) => ({ ...current, custom_instructions: preset?.instructions ?? "" }));
  };

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted">
        Pick a starting point for <span className="font-medium text-ink">{selectedRepo}</span>. You can refine it any
        time on the Rules page.
      </p>
      <div className="grid gap-3 md:grid-cols-4">
        {[...(presets ?? []), { id: "", name: "Start blank", description: "General architectural standards." }].map(
          (preset) => (
            <button
              key={preset.id || "blank"}
              type="button"
              onClick={() => choose(preset.id)}
              aria-pressed={presetId === preset.id}
              className={clsx(
                "rounded-xl border p-4 text-left transition duration-150",
                presetId === preset.id ? "border-violet bg-violet-soft" : "border-border hover:border-violet/50",
              )}
            >
              <p className="text-sm font-semibold">{preset.name}</p>
              <p className="mt-1 text-xs text-muted">{preset.description}</p>
            </button>
          ),
        )}
      </div>
      <div className="flex flex-wrap gap-6">
        <SegmentedControl
          label="Verbosity"
          value={rule.verbosity}
          onChange={(verbosity) => setRule({ ...rule, verbosity })}
          options={[
            { value: "concise", label: "Concise" },
            { value: "detailed", label: "Detailed" },
          ]}
        />
        <SegmentedControl
          label="Mode"
          value={rule.review_mode}
          onChange={(review_mode) => setRule({ ...rule, review_mode })}
          options={[
            { value: "auto", label: "Auto on PR open" },
            { value: "on_demand", label: "On-demand @review only" },
          ]}
        />
        <Toggle
          label="Security audit"
          checked={rule.enable_security}
          onChange={(enable_security) => setRule({ ...rule, enable_security })}
        />
      </div>
      <Button
        loading={save.isPending}
        onClick={() =>
          save.mutate(rule, {
            onSuccess: () => {
              toast.success("Rules saved");
              onNext();
            },
            onError: () => toast.error("Could not save rules"),
          })
        }
      >
        Save rules
      </Button>
    </div>
  );
}

function TriggerStep({ onDone }: { onDone: () => void }) {
  const { selectedRepo } = useWorkspace();
  const { data: events } = useEvents({ repo: selectedRepo, limit: 5 }, Boolean(selectedRepo));
  const { data: reviews } = useReviews({ repo: selectedRepo, page_size: 1 }, { refetchInterval: 5_000 });
  const firstReview = reviews?.items[0];

  return (
    <div className="space-y-5">
      <ol className="space-y-3 text-sm">
        <li className="flex gap-3">
          <GitPullRequest className="mt-0.5 h-4 w-4 shrink-0 text-violet" />
          <span>
            <strong>Open a new pull request</strong> in {selectedRepo}. In auto mode ReviewPilot reviews it
            immediately.
          </span>
        </li>
        <li className="flex gap-3">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-violet" />
          <span className="flex flex-wrap items-center gap-1">
            <strong>Or comment on any open PR:</strong>
            <code className="rounded bg-ink px-1.5 py-0.5 font-mono text-signal-ink">@review focus on auth boundaries</code>
            <CopyButton text="@review focus on auth boundaries" />
          </span>
        </li>
        <li className="pl-7 text-muted">
          Tip: <code className="rounded bg-ink px-1.5 py-0.5 font-mono text-signal-ink">@bot plan</code> posts a pre-merge execution
          checklist.
        </li>
      </ol>

      <div className="rounded-xl border border-border bg-bg/50 p-4">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Live activity for {selectedRepo}</p>
        {events && events.length > 0 ? (
          <ul className="space-y-2 text-sm">
            {events.map((event) => (
              <li key={event.id} className="flex items-center justify-between gap-2">
                <span>
                  {event.event}
                  {event.action ? `.${event.action}` : ""} <span className="text-muted">by @{event.sender}</span>
                </span>
                <span className="flex items-center gap-2 text-xs text-muted">
                  {relativeTime(event.created_at)} <StatusBadge status={event.status} />
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">Waiting for the first webhook event…</p>
        )}
      </div>

      {firstReview ? (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-emerald/40 bg-emerald-soft p-4">
          <Check className="h-5 w-5 text-emerald" />
          <span className="text-sm">Your first review is ready!</span>
          <Link to={`/history?review=${firstReview.id}`} onClick={onDone}>
            <Button size="sm">View review</Button>
          </Link>
        </div>
      ) : (
        <Button variant="ghost" size="sm" onClick={onDone}>
          Skip for now
        </Button>
      )}
    </div>
  );
}

export function OnboardingWizard({ onComplete }: { onComplete: () => void }) {
  const { installations } = useWorkspace();
  const [stored, setStored] = useState(readStep);
  const step = installations.length === 0 ? 1 : Math.max(2, stored);

  const goTo = (next: number) => {
    setStored(next);
    persist(STEP_KEY, String(next));
  };
  const finish = () => {
    persist(ONBOARDING_DONE_KEY, "1");
    onComplete();
  };

  return (
    <Card title="Welcome to ReviewPilot" description="Four quick steps to your first architectural review.">
      <ol className="mb-6 flex flex-wrap gap-2" aria-label="Onboarding progress">
        {STEPS.map((label, index) => {
          const number = index + 1;
          const done = number < step;
          return (
            <li
              key={label}
              aria-current={number === step ? "step" : undefined}
              className={clsx(
                "flex items-center gap-2 rounded-full border px-3 py-1 text-xs",
                number === step && "border-violet bg-violet-soft text-ink",
                done && "border-emerald/40 text-emerald",
                !done && number !== step && "border-border text-muted",
              )}
            >
              {done ? <Check className="h-3 w-3" /> : <span>{number}</span>}
              {label}
            </li>
          );
        })}
      </ol>
      {step === 1 && <InstallStep />}
      {step === 2 && <RepoStep onNext={() => goTo(3)} />}
      {step === 3 && <RulesStep onNext={() => goTo(4)} />}
      {step >= 4 && <TriggerStep onDone={finish} />}
      {step > 2 && (
        <button className="mt-4 text-xs text-muted hover:text-ink" onClick={() => goTo(step - 1)}>
          ← Back
        </button>
      )}
    </Card>
  );
}
