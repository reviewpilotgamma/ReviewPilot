import clsx from "clsx";
import type { ReactNode } from "react";

const TONES = {
  emerald: "text-emerald",
  amber: "text-amber",
  rose: "text-rose",
  violet: "text-violet",
  muted: "text-text",
} as const;

interface MetricCardProps {
  label: string;
  value: string;
  icon: ReactNode;
  tone?: keyof typeof TONES;
  hint?: string;
  loading?: boolean;
}

export function MetricCard({ label, value, icon, tone = "muted", hint, loading }: MetricCardProps) {
  const empty = value === "—";
  return (
    <div className="glass p-5 transition duration-150 hover:border-violet/40">
      <div className="flex items-center justify-between text-muted">
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
        <span className="text-violet">{icon}</span>
      </div>
      {loading ? (
        <div className="skeleton mt-3 h-8 w-24" />
      ) : (
        <p className={clsx("mt-2 text-3xl font-semibold tabular-nums", TONES[tone])}>{value}</p>
      )}
      <p className="mt-1 text-xs text-muted">{empty && !loading ? "No data yet" : hint}</p>
    </div>
  );
}
