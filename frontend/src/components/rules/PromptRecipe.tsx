import clsx from "clsx";
import { ArrowRight, FileText, GitPullRequest, ListChecks, Lock, Plus } from "lucide-react";
import type { ReactNode } from "react";
import { shortDate } from "@/lib/format";
import type { CacheStatus, PromptTemplate, RepoDocumentList, RuleInput } from "@/types/api";

const DOC_STATUS: Record<CacheStatus, string> = {
  cached: "Gemini cache ready",
  inline: "Inline reference",
  pending: "Will be cached on next review",
  none: "None uploaded",
};

interface TileProps {
  icon: ReactNode;
  title: string;
  detail: ReactNode;
  meta?: ReactNode;
  tone: "locked" | "active" | "empty";
  onClick: () => void;
  label: string;
}

function Tile({ icon, title, detail, meta, tone, onClick, label }: TileProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={clsx(
        "group flex min-w-0 items-start gap-3 rounded-xl border px-3.5 py-3 text-left transition duration-150",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-violet hover:border-violet/50",
        tone === "locked" && "border-border bg-ink/[0.03]",
        tone === "active" && "border-violet/30 bg-violet-soft",
        tone === "empty" && "border-dashed border-border",
      )}
    >
      <span
        className={clsx(
          "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border",
          tone === "empty" ? "border-dashed border-border text-muted" : "border-violet/25 bg-bg text-violet",
        )}
        aria-hidden
      >
        {icon}
      </span>
      <span className="min-w-0">
        <span className="flex items-center gap-1.5 text-sm font-semibold text-ink">{title}</span>
        <span className={clsx("block truncate text-xs", tone === "empty" ? "text-muted" : "text-ink/80")}>{detail}</span>
        {meta && <span className="mt-0.5 block text-xs text-muted">{meta}</span>}
      </span>
    </button>
  );
}

function Join({ children }: { children: ReactNode }) {
  return (
    <span className="flex items-center justify-center text-muted" aria-hidden>
      <span className="flex h-6 w-6 items-center justify-center rounded-full border border-border bg-bg">{children}</span>
    </span>
  );
}

interface PromptRecipeProps {
  form: RuleInput;
  dirty: boolean;
  docs: RepoDocumentList | undefined;
  docsError: boolean;
  prompt: PromptTemplate | undefined;
  onViewPrompt: () => void;
  onFocusInstructions: () => void;
  onFocusDocuments: () => void;
}

/** Golden prompt + this repo's instructions + documents → every PR review. */
export function PromptRecipe({
  form,
  dirty,
  docs,
  docsError,
  prompt,
  onViewPrompt,
  onFocusInstructions,
  onFocusDocuments,
}: PromptRecipeProps) {
  const lines = form.custom_instructions.split("\n").filter((line) => line.trim()).length;
  const settings = `${form.verbosity === "detailed" ? "Detailed" : "Concise"} · Security ${form.enable_security ? "on" : "off"}`;
  const docCount = docs?.total ?? 0;
  const docsDetail = docsError
    ? "Unavailable"
    : !docs
      ? "Loading…"
      : docCount === 0
        ? DOC_STATUS.none
        : `${docCount} ${docCount === 1 ? "file" : "files"} · ${DOC_STATUS[docs.cache_status]}`;

  return (
    <section aria-labelledby="prompt-recipe-title" className="glass p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="prompt-recipe-title" className="text-sm font-semibold text-ink">
          How every review is composed
        </h2>
        <p className="text-xs text-muted">Your instructions and documents are layered on top of the golden prompt.</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto_minmax(0,1fr)_auto_auto] sm:items-stretch">
        <Tile
          icon={<Lock className="h-3.5 w-3.5" />}
          title="Golden prompt"
          label="Golden prompt: view full prompt"
          tone="locked"
          detail="Architecture review protocol · always applied"
          meta={
            <span className="flex items-center gap-1.5">
              <span>{!prompt ? "Built-in" : prompt.is_default ? "Default" : `Edited ${prompt.updated_at ? shortDate(prompt.updated_at) : ""}`}</span>
              <span aria-hidden>·</span>
              <span className="font-medium text-violet group-hover:underline">View full prompt</span>
            </span>
          }
          onClick={onViewPrompt}
        />
        <Join>
          <Plus className="h-3 w-3" />
        </Join>
        <Tile
          icon={<ListChecks className="h-3.5 w-3.5" />}
          title="Custom instructions"
          label="Custom instructions: edit"
          tone={lines > 0 ? "active" : "empty"}
          detail={lines > 0 ? `${lines} ${lines === 1 ? "line" : "lines"} · ${settings}` : "Not set, defaults apply"}
          meta={
            dirty ? (
              <span className="flex items-center gap-1.5 text-amber">
                <span className="h-1.5 w-1.5 rounded-full bg-amber" aria-hidden />
                Unsaved
              </span>
            ) : lines > 0 ? undefined : (
              settings
            )
          }
          onClick={onFocusInstructions}
        />
        <Join>
          <Plus className="h-3 w-3" />
        </Join>
        <Tile
          icon={<FileText className="h-3.5 w-3.5" />}
          title="Documents"
          label="Documents: manage"
          tone={docCount > 0 ? "active" : "empty"}
          detail={docsDetail}
          onClick={onFocusDocuments}
        />
        <Join>
          <ArrowRight className="h-3 w-3" />
        </Join>
        <div className="flex items-center gap-2 rounded-xl border border-border px-3.5 py-3 text-sm font-medium text-ink">
          <GitPullRequest className="h-4 w-4 text-violet" aria-hidden />
          Every PR review
        </div>
      </div>
    </section>
  );
}
