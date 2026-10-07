import { FileUp, RotateCcw, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
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
import {
  useDeleteDocument,
  usePresets,
  useRepoDocuments,
  useResetRule,
  useRule,
  useSaveRule,
  useUploadDocument,
} from "@/hooks/useRules";
import { appendPreset, previewDirectives } from "@/lib/directives";
import type { Rule, RuleInput } from "@/types/api";

const MAX_CHARS = 10_000;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function DocumentPanel({ repo }: { repo: string }) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const { data, isLoading, isError, refetch } = useRepoDocuments(repo);
  const upload = useUploadDocument(repo);
  const remove = useDeleteDocument(repo);

  const onPick = (files: FileList | null) => {
    if (!files?.length) return;
    void (async () => {
      for (const file of Array.from(files)) {
        try {
          await upload.mutateAsync(file);
          toast.success(`Uploaded ${file.name}`);
        } catch (error) {
          toast.error(error instanceof Error ? error.message : `Could not upload ${file.name}`);
        }
      }
      if (inputRef.current) inputRef.current.value = "";
    })();
  };

  return (
    <Card
      title="Architecture & requirements docs"
      description="Uploaded documents are referenced on every PR review. Large packs use Gemini context caching to cut token cost."
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            multiple
            accept=".txt,.md,.markdown,.rst,.pdf,text/plain,text/markdown,application/pdf"
            onChange={(event) => onPick(event.target.files)}
          />
          <Button
            variant="secondary"
            icon={<FileUp className="h-4 w-4" />}
            loading={upload.isPending}
            onClick={() => inputRef.current?.click()}
          >
            Upload documents
          </Button>
          {data && (
            <Badge tone={data.cache_status === "cached" ? "emerald" : data.cache_status === "inline" ? "amber" : "gray"}>
              {data.cache_status === "cached"
                ? "Gemini cache ready"
                : data.cache_status === "inline"
                  ? "Inline reference (below cache size)"
                  : "No documents"}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted">Supports .txt, .md, .rst, .pdf · max 5 MB each · up to 20 files</p>
        {isLoading && <p className="text-sm text-muted">Loading documents…</p>}
        {isError && <ErrorState onRetry={() => void refetch()} />}
        {data && data.items.length === 0 && (
          <p className="text-sm text-muted">No documents yet. Upload your architecture or requirements pack.</p>
        )}
        {data && data.items.length > 0 && (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {data.items.map((doc) => (
              <li key={doc.id} className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium text-ink">{doc.filename}</p>
                  <p className="text-xs text-muted">
                    {formatBytes(doc.size_bytes)} · {doc.char_count.toLocaleString()} chars ·{" "}
                    {new Date(doc.uploaded_at).toLocaleString()}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Delete ${doc.filename}`}
                  icon={<Trash2 className="h-4 w-4" />}
                  loading={remove.isPending}
                  onClick={() =>
                    remove.mutate(doc.id, {
                      onSuccess: () => toast.success(`Removed ${doc.filename}`),
                      onError: (error) => toast.error(error.message || "Could not delete"),
                    })
                  }
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

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
                    className={tab === t ? "text-violet" : "text-muted hover:text-ink"}
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

      <DocumentPanel repo={repo} />

      <Card title="How rules are applied" description="Injected into every review of this repository.">
        <p className="mb-3 text-sm text-muted">
          Live preview of the directives ReviewPilot adds to the reviewer prompt for this configuration:
        </p>
        <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-bg p-3 text-xs text-ink/90">
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
