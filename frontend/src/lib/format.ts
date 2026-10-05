import { formatDistanceToNowStrict } from "date-fns";
import type { Verdict } from "@/types/api";

export function relativeTime(iso: string): string {
  return formatDistanceToNowStrict(new Date(iso), { addSuffix: true });
}

export function absoluteTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

export function formatScore(score: number | null | undefined): string {
  return score === null || score === undefined ? "—" : `${score.toFixed(1)}/10`;
}

export function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(1).replace(/\.0$/, "")}%`;
}

/** Score colour band: ≥8 emerald, 5–7.9 amber, <5 rose. */
export function scoreTone(score: number | null | undefined): "emerald" | "amber" | "rose" | "muted" {
  if (score === null || score === undefined) return "muted";
  if (score >= 8) return "emerald";
  if (score >= 5) return "amber";
  return "rose";
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  passed: "Passed",
  warning: "Warning",
  critical: "Critical Risk",
};

export function prettyJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}
