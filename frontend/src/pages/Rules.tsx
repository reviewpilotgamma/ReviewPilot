import { RotateCcw, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useBlocker } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Chip, SegmentedControl, Select, Toggle } from "@/components/ui/Controls";
import { MarkdownView } from "@/components/diff/MarkdownView";
import { Modal } from "@/components/ui/Overlay";
import { FullPageSpinner } from "@/components/ui/Spinner";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useToast, useWorkspace } from "@/hooks/useAuth";
import { usePresets, useResetRule, useRule, useSaveRule } from "@/hooks/useRules";
import { appendPreset, previewDirectives } from "@/lib/directives";
import type { Rule, RuleInput } from "@/types/api";

const MAX_CHARS = 10_000;

function toInput(rule: Rule): RuleInput {
  const { custom_instructions, verbosity, review_mode, enable_security } = rule;
  return { custom_instructions, verbosity, review_mode, enable_security };
}

function sameRule(a: RuleInput, b: RuleInput): boolean {
  return (
    a.custom_instructions === b.custom_instructions &&
    a.verbosity === b.verbosity &&
    a.review_mode === b.review_mode &&
    a.enable_security === b.enable_security
  );
}

interface RuleEditorProps {
  repo: string;
  rule: Rule;
  onDirtyChange: (dirty: boolean) => void;
}

function RuleEditor({ repo, rule, onDirtyChange }: RuleEditorProps) {
  const toast = useToast();
  const { data: presets } = usePresets();
  const save = useSaveRule(repo);
  const reset = useResetRule(repo);
  const [form, setForm] = useState<RuleInput>(() => toInput(rule));
  const [tab, setTab] = useState<"edit" | "preview">("edit");
  const [confirmReset, setConfirmReset] = useState(false);
  const saved = useMemo(() => toInput(rule), [rule]);
  const dirty = !sameRule(form, saved);

  // Re-sync only when the stored rule actually changes (save/reset), so background
  // refetches never wipe in-progress edits.
  const version = `${rule.updated_at ?? "default"}`;
  useEffect(() => setForm(saved), [version]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const patch = (update: Partial<RuleInput>) => setForm((current) => ({ ...current, ...update }));

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
      <Card
        title={
          <span className="flex items-center gap-2">
            {repo} {rule.is_default && <Badge>Using defaults</Badge>}
            {dirty && <Badge tone="amber">Unsaved changes</Badge>}
          </span>
        }
        description={rule.updated_at ? `Last updated ${new Date(rule.updated_at).toLocaleString()}` : undefined}
      >
        <div className="space-y-5">
          <div>
            <span className="label">Presets — click to insert</span>
            <div className="flex flex-wrap gap-2">
              {presets?.map((preset) => (
                <Chip
                  key={preset.id}
                  active={form.custom_instructions.includes(preset.instructions)}
                  onClick={() =>
                    patch({ custom_instructions: appendPreset(form.custom_instructions, preset.instructions) })
                  }
                >
                  + {preset.name}
                </Chip>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <div role="tablist" className="flex gap-3 text-xs font-medium uppercase tracking-wide">
                {(["edit", "preview"] as const).map((t) => (
                  <button
                    key={t}
                    role="tab"
                    aria-selected={tab === t}
                    onClick={() => setTab(t)}
                    className={tab === t ? "text-violet" : "text-muted hover:text-text"}
                  >
                    {t === "edit" ? "Custom instructions" : "Preview"}
                  </button>
                ))}
              </div>
              <span className={form.custom_instructions.length > MAX_CHARS ? "text-xs text-rose" : "text-xs text-muted"}>
                {form.custom_instructions.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}
              </span>
            </div>
            {tab === "edit" ? (
              <textarea
                aria-label="Custom instructions"
                className="input min-h-[280px] font-mono text-xs leading-relaxed"
                rows={12}
                maxLength={MAX_CHARS}
                placeholder="e.g. Strict check on idempotency keys in payment flows. Focus on async lifecycles and auth boundaries."
                value={form.custom_instructions}
                onChange={(event) => patch({ custom_instructions: event.target.value })}
              />
            ) : (
              <div className="min-h-[280px] rounded-lg border border-border bg-bg/60 p-4">
                {form.custom_instructions.trim() ? (
                  <MarkdownView markdown={form.custom_instructions} />
                ) : (
                  <p className="text-sm text-muted">Nothing to preview yet.</p>
                )}
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-6">
            <SegmentedControl
              label="Verbosity"
              value={form.verbosity}
              onChange={(verbosity) => patch({ verbosity })}
              options={[
                { value: "concise", label: "Concise" },
                { value: "detailed", label: "Detailed" },
              ]}
            />
            <SegmentedControl
              label="Mode"
              value={form.review_mode}
              onChange={(review_mode) => patch({ review_mode })}
              options={[
                { value: "auto", label: "Auto on PR open" },
                { value: "on_demand", label: "On-demand @review only" },
              ]}
            />
            <Toggle
              label="Security audit"
              checked={form.enable_security}
              onChange={(enable_security) => patch({ enable_security })}
              description="OWASP, secret leaks and trust boundaries"
            />
          </div>

          <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
            <Button
              variant="secondary"
              icon={<RotateCcw className="h-4 w-4" />}
              disabled={rule.is_default}
              onClick={() => setConfirmReset(true)}
            >
              Reset to defaults
            </Button>
            <Button
              icon={<Save className="h-4 w-4" />}
              disabled={!dirty}
              loading={save.isPending}
              onClick={() =>
                save.mutate(form, {
                  onSuccess: () => toast.success("Rules saved"),
                  onError: (error) => toast.error(error.message || "Could not save rules"),
                })
              }
            >
              Save
            </Button>
          </div>
        </div>
      </Card>

      <Card title="How rules are applied" description="Injected into every review of this repository.">
        <p className="mb-3 text-sm text-muted">
          Live preview of the directives ReviewPilot adds to the reviewer prompt for this configuration:
        </p>
        <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-bg p-3 text-xs text-text/90">
          {previewDirectives(form)}
        </pre>
      </Card>

      <Modal
        open={blocker.state === "blocked"}
        onClose={() => blocker.reset?.()}
        title="Discard unsaved changes?"
        actions={
          <>
            <Button variant="ghost" onClick={() => blocker.reset?.()}>
              Keep editing
            </Button>
            <Button variant="danger" onClick={() => blocker.proceed?.()}>
              Discard
            </Button>
          </>
        }
      >
        Your edits to the rules for <strong>{repo}</strong> have not been saved.
      </Modal>

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
    </div>
  );
}

export default function Rules() {
  const { repos, selectedRepo, isLoading } = useWorkspace();
  const [repo, setRepo] = useState("");
  const active = repo || selectedRepo || repos[0]?.full_name || "";
  const { data: rule, isLoading: ruleLoading, isError, refetch } = useRule(active);
  const [dirty, setDirty] = useState(false);

  if (isLoading) return <FullPageSpinner />;
  if (repos.length === 0) {
    return (
      <EmptyState
        title="No repositories yet"
        description="Install the ReviewPilot GitHub App on a repository to configure its review rules."
      />
    );
  }

  return (
    <div className="space-y-6">
      <Select
        label="Repository"
        className="max-w-sm"
        value={active}
        onChange={(event) => {
          // The editor is keyed by repo, so switching discards edits: confirm first.
          if (dirty && !window.confirm("Discard unsaved changes?")) return;
          setDirty(false);
          setRepo(event.target.value);
        }}
      >
        {repos.map((r) => (
          <option key={r.full_name} value={r.full_name}>
            {r.full_name}
            {r.has_rules ? "" : " (defaults)"}
          </option>
        ))}
      </Select>
      {ruleLoading && <FullPageSpinner />}
      {isError && <ErrorState onRetry={() => void refetch()} />}
      {rule && <RuleEditor key={active} repo={active} rule={rule} onDirtyChange={setDirty} />}
    </div>
  );
}
