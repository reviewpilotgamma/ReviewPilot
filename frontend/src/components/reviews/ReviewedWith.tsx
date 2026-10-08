import { FileText, ListChecks, Lock } from "lucide-react";
import type { ReactNode } from "react";
import { shortDate } from "@/lib/format";
import type { ReviewContext } from "@/types/api";

function Part({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-violet" aria-hidden>
        {icon}
      </span>
      {children}
    </span>
  );
}

/** One quiet line: which golden prompt, instructions and documents this review used. */
export function ReviewedWith({ context }: { context: ReviewContext | null }) {
  if (!context) return null;
  const settings = `${context.verbosity === "detailed" ? "Detailed" : "Concise"} · Security ${context.security ? "on" : "off"}`;
  const docCount = context.documents.length;
  const parts: ReactNode[] = [
    <Part key="prompt" icon={<Lock className="h-3 w-3" />}>
      Golden prompt
      {context.prompt === "custom" && (
        <span className="text-muted">
          {" "}
          (edited{context.prompt_updated_at ? ` ${shortDate(context.prompt_updated_at)}` : ""})
        </span>
      )}
    </Part>,
    <Part key="instructions" icon={<ListChecks className="h-3 w-3" />}>
      {context.instructions_chars > 0 ? "Instructions" : "No instructions"}
      <span className="text-muted"> ({settings})</span>
    </Part>,
  ];
  if (docCount > 0 && context.documents_mode !== "none") {
    parts.push(
      <Part key="docs" icon={<FileText className="h-3 w-3" />}>
        <span title={context.documents.join(", ")}>
          {docCount} {docCount === 1 ? "document" : "documents"}
        </span>
        <span className="text-muted"> ({context.documents_mode})</span>
      </Part>,
    );
  }
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink/80" aria-label="Reviewed with">
      <span className="font-medium text-muted">Reviewed with</span>
      {parts.map((part, index) => (
        <span key={index} className="inline-flex items-center gap-2">
          {index > 0 && (
            <span className="text-muted" aria-hidden>
              +
            </span>
          )}
          {part}
        </span>
      ))}
    </p>
  );
}
