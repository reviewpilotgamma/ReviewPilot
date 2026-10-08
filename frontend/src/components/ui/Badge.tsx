import clsx from "clsx";
import { FileWarning, History } from "lucide-react";
import type { ReactNode } from "react";
import { VERDICT_LABEL } from "@/lib/format";
import type { EventStatus, JobStatus, Verdict } from "@/types/api";

type Tone = "emerald" | "amber" | "rose" | "violet" | "gray";

const TONES: Record<Tone, string> = {
  emerald: "bg-emerald-soft text-emerald border-emerald/30",
  amber: "bg-amber-soft text-amber border-amber/30",
  rose: "bg-rose-soft text-rose border-rose/30",
  violet: "bg-violet-soft text-violet border-violet/30",
  gray: "bg-border/40 text-muted border-border",
};

export function Badge({ tone = "gray", pulse, children }: { tone?: Tone; pulse?: boolean; children: ReactNode }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium",
        TONES[tone],
      )}
    >
      {pulse && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {children}
    </span>
  );
}

const VERDICT_TONES: Record<Verdict, Tone> = { passed: "emerald", warning: "amber", critical: "rose" };

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <Badge tone={VERDICT_TONES[verdict]}>{VERDICT_LABEL[verdict]}</Badge>;
}

/** Shown when part of a PR's diff was not reviewed (cut, failed batch, or time limit). */
export function PartialBadge() {
  return (
    <span title="Part of this PR's diff was not reviewed. The review lists the files.">
      <Badge tone="amber">
        <FileWarning className="h-3 w-3" aria-hidden />
        Partially reviewed
      </Badge>
    </span>
  );
}

const STATUS_TONES: Record<EventStatus | JobStatus, Tone> = {
  queued: "violet",
  running: "violet",
  processed: "emerald",
  succeeded: "emerald",
  ignored: "gray",
  failed: "rose",
};

/** Shown on a review that follows up an earlier review of the same PR. */
export function FollowUpBadge() {
  return (
    <span title="Compares the updated PR with the previous review: fixed, still open and new findings.">
      <Badge tone="violet">
        <History className="h-3 w-3" aria-hidden />
        Follow-up
      </Badge>
    </span>
  );
}

export function StatusBadge({ status }: { status: EventStatus | JobStatus }) {
  return (
    <Badge tone={STATUS_TONES[status]} pulse={status === "queued" || status === "running"}>
      {status}
    </Badge>
  );
}
