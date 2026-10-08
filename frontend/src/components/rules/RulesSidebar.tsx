import clsx from "clsx";
import { ChevronRight, FileText, ListChecks, RotateCcw } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SegmentedControl, Toggle } from "@/components/ui/Controls";
import { Modal } from "@/components/ui/Overlay";
import { useToast } from "@/hooks/useAuth";
import { useRepoDocuments, useResetRule, useSaveRule } from "@/hooks/useRules";
import { toInput } from "@/lib/rules";
import type { CacheStatus, Rule, RuleInput } from "@/types/api";

const DOC_STATUS: Record<CacheStatus, string> = {
  cached: "Gemini cache ready",
  inline: "Inline reference",
  pending: "Will be cached on next review",
  none: "None uploaded",
};

interface OptionProps {
  icon: ReactNode;
  title: string;
  status: string;
  active: boolean;
  label: string;
  onClick: () => void;
}

function Option({ icon, title, status, active, label, onClick }: OptionProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={clsx(
        "group flex w-full items-center gap-3 rounded-xl border px-3.5 py-3 text-left transition duration-150",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-violet hover:border-violet/50",
        active ? "border-violet/30 bg-violet-soft" : "border-dashed border-border",
      )}
    >
      <span
        className={clsx(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
          active ? "border-violet/25 bg-bg text-violet" : "border-dashed border-border text-muted",
        )}
        aria-hidden
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold text-ink">{title}</span>
        <span className="block truncate text-xs text-muted">{status}</span>
      </span>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted transition group-hover:text-violet" aria-hidden />
    </button>
  );
}

interface RulesSidebarProps {
  repo: string;
  rule: Rule;
  onOpenInstructions: () => void;
  onOpenDocuments: () => void;
}

/** What this repo adds to the golden prompt: popup launchers, review settings (saved on change), reset. */
export function RulesSidebar({ repo, rule, onOpenInstructions, onOpenDocuments }: RulesSidebarProps) {
  const toast = useToast();
  const docs = useRepoDocuments(repo);
  const save = useSaveRule(repo);
  const reset = useResetRule(repo);
  const [confirmReset, setConfirmReset] = useState(false);

  // Show the pending value while saving; a failed save falls back to the stored rule.
  const settings = save.isPending && save.variables ? save.variables : toInput(rule);
  const change = (update: Partial<RuleInput>) =>
    save.mutate(
      { ...toInput(rule), ...update },
      {
        onSuccess: () => toast.success("Settings saved"),
        onError: (error) => toast.error(error.message || "Could not save settings"),
      },
    );

  const lines = rule.custom_instructions.split("\n").filter((line) => line.trim()).length;
  const docCount = docs.data?.total ?? 0;
  const docsStatus = docs.isError
    ? "Unavailable"
    : !docs.data
      ? "Loading…"
      : docCount === 0
        ? DOC_STATUS.none
        : `${docCount} ${docCount === 1 ? "file" : "files"} · ${DOC_STATUS[docs.data.cache_status]}`;

  return (
    <aside aria-label="Repository rules" className="glass space-y-5 p-5">
      <div>
        <h2 className="flex flex-wrap items-center gap-2 text-base font-semibold text-ink">
          <span className="truncate">{repo}</span>
          {rule.is_default && <Badge>Using defaults</Badge>}
        </h2>
        <p className="mt-0.5 text-sm text-muted">Added to the golden prompt on every review.</p>
      </div>

      <div className="space-y-2">
        <Option
          icon={<ListChecks className="h-4 w-4" />}
          title="Custom instructions"
          label="Edit custom instructions"
          status={lines > 0 ? `${lines} ${lines === 1 ? "line" : "lines"}` : "Not set, defaults apply"}
          active={lines > 0}
          onClick={onOpenInstructions}
        />
        <Option
          icon={<FileText className="h-4 w-4" />}
          title="Documents"
          label="Manage documents"
          status={docsStatus}
          active={docCount > 0}
          onClick={onOpenDocuments}
        />
      </div>

      <div className="space-y-4 border-t border-border pt-4">
        <SegmentedControl
          label="Verbosity"
          value={settings.verbosity}
          disabled={save.isPending}
          onChange={(verbosity) => change({ verbosity })}
          options={[
            { value: "concise", label: "Concise" },
            { value: "detailed", label: "Detailed" },
          ]}
        />
        <SegmentedControl
          label="Mode"
          value={settings.review_mode}
          disabled={save.isPending}
          onChange={(review_mode) => change({ review_mode })}
          options={[
            { value: "auto", label: "Auto on PR open" },
            { value: "on_demand", label: "@review only" },
          ]}
        />
        <Toggle
          label="Security audit"
          checked={settings.enable_security}
          disabled={save.isPending}
          onChange={(enable_security) => change({ enable_security })}
          description="OWASP, secret leaks and trust boundaries"
        />
      </div>

      <div className="border-t border-border pt-4">
        <Button
          variant="secondary"
          className="w-full"
          icon={<RotateCcw className="h-4 w-4" />}
          disabled={rule.is_default}
          onClick={() => setConfirmReset(true)}
        >
          Reset to defaults
        </Button>
      </div>

      <Modal
        open={confirmReset}
        onClose={() => setConfirmReset(false)}
        title="Reset rules to defaults?"
        actions={
          <>
            <Button variant="ghost" onClick={() => setConfirmReset(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={reset.isPending}
              onClick={() =>
                reset.mutate(undefined, {
                  onSuccess: () => {
                    setConfirmReset(false);
                    toast.success("Rules reset to defaults");
                  },
                  onError: () => toast.error("Could not reset rules"),
                })
              }
            >
              Reset
            </Button>
          </>
        }
      >
        Custom instructions for <strong>{repo}</strong> will be deleted and default settings used.
      </Modal>
    </aside>
  );
}
