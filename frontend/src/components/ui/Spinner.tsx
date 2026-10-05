import clsx from "clsx";
import { Loader2 } from "lucide-react";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 aria-hidden className={clsx("animate-spin text-violet", className ?? "h-5 w-5")} />;
}

export function FullPageSpinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-muted" role="status">
      <Spinner className="h-8 w-8" />
      <span className="text-sm">{label}</span>
    </div>
  );
}
