import { Copy, FileText, Info, Lock, PencilLine, RotateCcw, Save } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Drawer, Modal } from "@/components/ui/Overlay";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/States";
import { useToast } from "@/hooks/useAuth";
import { useResetPrompt, useSavePrompt } from "@/hooks/usePrompt";
import { shortDate } from "@/lib/format";
import { type AssembledPart, assembledText, assemblePrompt, insertAt, validateTemplate } from "@/lib/prompt";
import { ApiError } from "@/services/client";
import type { CacheStatus, PromptTemplate, RepoDocumentList, RuleInput } from "@/types/api";

const COLLAPSE_LINES = 20;

const DOC_DELIVERY: Record<CacheStatus, string> = {
  cached: "Sent as Gemini cached context alongside this prompt.",
  inline: "Appended to the end of this prompt.",
  pending: "Appended to the end of this prompt until the Gemini cache is built.",
  none: "No documents uploaded.",
};

interface PromptQuery {
  data: PromptTemplate | undefined;
  isLoading: boolean;
  isError: boolean;
  refetch: () => unknown;
}

interface PromptDrawerProps {
  open: boolean;
  onClose: () => void;
  repo: string;
  form: RuleInput;
  docs: RepoDocumentList | undefined;
  prompt: PromptQuery;
  isAdmin: boolean;
}

function SlotMark({ part }: { part: Extract<AssembledPart, { kind: "slot" }> }) {
  const [expanded, setExpanded] = useState(false);
  const lines = part.text.split("\n");
  const collapsible = part.name === "custom_instructions" && lines.length > COLLAPSE_LINES;
  const shown = collapsible && !expanded ? lines.slice(0, COLLAPSE_LINES).join("\n") : part.text;
  return (
    <mark data-slot={part.name} className="rounded-md bg-violet-soft px-1 py-0.5 text-ink ring-1 ring-violet/25">
      <span className="mr-1.5 select-none rounded bg-bg px-1.5 py-px font-sans text-[10px] font-semibold uppercase tracking-wide text-violet">
        {part.label}
      </span>
      {shown}
      {collapsible && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="ml-1 font-sans text-[11px] font-medium text-violet hover:underline"
        >
          {expanded ? "Show less" : `Show all (${lines.length} lines)`}
        </button>
      )}
    </mark>
  );
}

function PromptView({ prompt, form, docs }: { prompt: PromptTemplate; form: RuleInput; docs?: RepoDocumentList }) {
  const parts = useMemo(() => assemblePrompt(prompt, form), [prompt, form]);
  const docStatus = docs?.cache_status ?? "none";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <span>Highlighted parts come from this repository:</span>
        {prompt.slots.map((slot) => (
          <span key={slot.name} className="rounded bg-violet-soft px-1.5 py-0.5 font-semibold uppercase tracking-wide text-violet">
            {slot.label}
          </span>
        ))}
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl border border-border bg-bg p-4 font-mono text-xs leading-relaxed text-ink/90">
        {parts.map((part, index) =>
          part.kind === "text" ? <span key={index}>{part.text}</span> : <SlotMark key={index} part={part} />,
        )}
      </pre>
      <section aria-label="Documents" className="rounded-xl border border-border p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
          <FileText className="h-4 w-4 text-violet" aria-hidden /> Plus documents
        </h3>
        <p className="mt-1 text-xs text-muted">{DOC_DELIVERY[docs && docs.total > 0 ? docStatus : "none"]}</p>
        {docs && docs.items.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {docs.items.map((doc) => (
              <li key={doc.id} className="rounded-md border border-border px-2 py-0.5 text-xs text-ink">
                {doc.filename}
              </li>
            ))}
          </ul>
        )}
      </section>
      <p className="text-xs text-muted">Then the pull request's title, description and diff are sent as the message to review.</p>
    </div>
  );
}

interface EditorProps {
  prompt: PromptTemplate;
  draft: string;
  setDraft: (value: string) => void;
  serverErrors: string[];
}

function PromptEditor({ prompt, draft, setDraft, serverErrors }: EditorProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const { errors, warnings } = validateTemplate(draft, prompt);
  const insert = (token: string) => {
    const el = ref.current;
    const start = el?.selectionStart ?? draft.length;
    const end = el?.selectionEnd ?? draft.length;
    const next = insertAt(draft, start, end, token);
    setDraft(next.value);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(next.caret, next.caret);
    });
  };
  const shownErrors = serverErrors.length ? serverErrors : errors;
  return (
    <div className="space-y-4">
      <div role="note" className="flex gap-2.5 rounded-xl border border-amber/30 bg-amber-soft px-3.5 py-3 text-sm text-ink">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber" aria-hidden />
        <p>
          Applies to every repository's reviews. Each repository's instructions and documents are still added where
          the placeholders below appear.
        </p>
      </div>
      <div>
        <span className="label">Placeholders — click to insert at the cursor</span>
        <div className="flex flex-wrap gap-1.5">
          {prompt.slots.map((slot) => (
            <button
              key={slot.name}
              type="button"
              onClick={() => insert(`{{${slot.name}}}`)}
              className="rounded-full border border-border px-2.5 py-1 font-mono text-[11px] text-ink transition hover:border-violet/50 hover:text-violet"
              title={slot.label + (slot.required ? " (required)" : "")}
            >
              {`{{${slot.name}}}`}
              {slot.required && <span className="ml-1 font-sans text-muted">required</span>}
            </button>
          ))}
        </div>
      </div>
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <label htmlFor="golden-prompt" className="label mb-0">
            Golden prompt
          </label>
          <span className="text-xs text-muted">{draft.length.toLocaleString()} / 20,000</span>
        </div>
        <textarea
          id="golden-prompt"
          ref={ref}
          className="input min-h-[420px] font-mono text-xs leading-relaxed"
          spellCheck={false}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          aria-invalid={shownErrors.length > 0}
          aria-describedby="golden-prompt-checks"
        />
      </div>
      <div id="golden-prompt-checks" aria-live="polite" className="space-y-1.5">
        {shownErrors.map((error) => (
          <p key={error} className="text-xs text-rose">
            {error}
          </p>
        ))}
        {warnings.map((warning) => (
          <p key={warning} className="text-xs text-amber">
            {warning}
          </p>
        ))}
      </div>
    </div>
  );
}

/** The exact golden prompt with this repo's additions in place; admins can edit the org-wide template. */
export function PromptDrawer({ open, onClose, repo, form, docs, prompt: query, isAdmin }: PromptDrawerProps) {
  const toast = useToast();
  const save = useSavePrompt();
  const reset = useResetPrompt();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [serverErrors, setServerErrors] = useState<string[]>([]);
  const [confirmReset, setConfirmReset] = useState(false);
  const prompt = query.data;
  const dirty = editing && prompt !== undefined && draft !== prompt.template;
  const clientErrors = prompt && editing ? validateTemplate(draft, prompt).errors : [];

  const leaveEditor = () => {
    if (dirty && !window.confirm("Discard your changes to the golden prompt?")) return false;
    setEditing(false);
    setServerErrors([]);
    return true;
  };
  const close = () => {
    if (editing && !leaveEditor()) return;
    onClose();
  };
  const startEditing = () => {
    if (!prompt) return;
    setDraft(prompt.template);
    setServerErrors([]);
    setEditing(true);
  };
  const copy = async () => {
    if (!prompt) return;
    try {
      await navigator.clipboard.writeText(assembledText(assemblePrompt(prompt, form)));
      toast.success("Prompt copied");
    } catch {
      toast.error("Could not copy the prompt");
    }
  };
  const submit = () =>
    save.mutate(draft, {
      onSuccess: () => {
        setEditing(false);
        setServerErrors([]);
        toast.success("Golden prompt saved. It applies to the next review of every repository.");
      },
      onError: (error) => {
        if (error instanceof ApiError && error.details.length) setServerErrors(error.details);
        else toast.error(error.message || "Could not save the golden prompt");
      },
    });

  const title = (
    <div className="space-y-1">
      <h2 className="flex flex-wrap items-center gap-2 text-lg font-semibold text-ink">
        <Lock className="h-4 w-4 text-violet" aria-hidden />
        {editing ? "Edit golden prompt" : "Golden prompt"}
        {prompt && (
          <Badge tone={prompt.is_default ? "gray" : "violet"}>
            {prompt.is_default
              ? "Default"
              : `Edited${prompt.updated_at ? ` ${shortDate(prompt.updated_at)}` : ""}${prompt.updated_by ? ` by ${prompt.updated_by}` : ""}`}
          </Badge>
        )}
      </h2>
      <p className="text-sm text-muted">
        {editing
          ? "The system prompt behind every PR review, for all repositories."
          : `The exact system prompt sent for every PR review of ${repo}, including unsaved changes on this page.`}
      </p>
    </div>
  );

  const footer = prompt && (
    <div className="flex flex-wrap items-center justify-between gap-2">
      {editing ? (
        <>
          <Button
            variant="ghost"
            icon={<RotateCcw className="h-4 w-4" />}
            disabled={prompt.is_default}
            onClick={() => setConfirmReset(true)}
          >
            Reset to default
          </Button>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={leaveEditor}>
              Cancel
            </Button>
            <Button
              icon={<Save className="h-4 w-4" />}
              disabled={!dirty || clientErrors.length > 0}
              loading={save.isPending}
              onClick={submit}
            >
              Save golden prompt
            </Button>
          </div>
        </>
      ) : (
        <>
          <Button variant="secondary" icon={<Copy className="h-4 w-4" />} onClick={() => void copy()}>
            Copy
          </Button>
          {isAdmin ? (
            <Button icon={<PencilLine className="h-4 w-4" />} onClick={startEditing}>
              Edit golden prompt
            </Button>
          ) : (
            <span className="text-xs text-muted">Only admins can edit the golden prompt.</span>
          )}
        </>
      )}
    </div>
  );

  return (
    <>
      <Drawer open={open} onClose={close} title={title} footer={footer}>
        {query.isLoading && (
          <div className="flex justify-center py-16">
            <Spinner className="h-6 w-6" />
          </div>
        )}
        {query.isError && <ErrorState message="Could not load the golden prompt." onRetry={() => void query.refetch()} />}
        {prompt &&
          (editing ? (
            <PromptEditor
              prompt={prompt}
              draft={draft}
              setDraft={(value) => {
                setDraft(value);
                setServerErrors([]);
              }}
              serverErrors={serverErrors}
            />
          ) : (
            <PromptView prompt={prompt} form={form} docs={docs} />
          ))}
      </Drawer>
      <Modal
        open={confirmReset}
        onClose={() => setConfirmReset(false)}
        title="Reset the golden prompt?"
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
                    setEditing(false);
                    toast.success("Golden prompt reset to the built-in default");
                  },
                  onError: () => toast.error("Could not reset the golden prompt"),
                })
              }
            >
              Reset
            </Button>
          </>
        }
      >
        Every repository's reviews will use the built-in ReviewPilot prompt again. Your edited version is deleted.
      </Modal>
    </>
  );
}
