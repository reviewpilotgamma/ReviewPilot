import { AlertTriangle, Inbox } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./Button";

interface EmptyStateProps {
  title: string;
  description?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ title, description, icon, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <div className="mb-1 rounded-full bg-violet-soft p-3 text-violet">{icon ?? <Inbox className="h-6 w-6" />}</div>
      <h3 className="font-semibold">{title}</h3>
      {description && <p className="max-w-md text-sm text-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-2 px-6 py-10 text-center">
      <AlertTriangle className="h-6 w-6 text-rose" />
      <p className="text-sm text-muted">{message ?? "Something went wrong while loading this data."}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function SkeletonRows({ rows = 5, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r} className="border-t border-border">
          {Array.from({ length: cols }, (__, c) => (
            <td key={c} className="px-4 py-3">
              <div className="skeleton h-4 w-full max-w-[10rem]" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
