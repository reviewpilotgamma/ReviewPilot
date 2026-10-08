import { Save } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useBlocker } from "react-router-dom";
import { MarkdownView } from "@/components/diff/MarkdownView";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Controls";
import { Dialog, Modal } from "@/components/ui/Overlay";
import { useToast } from "@/hooks/useAuth";
import { usePresets, useSaveRule } from "@/hooks/useRules";
import { appendPreset } from "@/lib/directives";
import { MAX_INSTRUCTION_CHARS, toInput } from "@/lib/rules";
import type { Rule } from "@/types/api";

interface InstructionsDialogProps {
  open: boolean;
  onClose: () => void;
  repo: string;
  rule: Rule;
}

/** Popup editor for a repo's custom instructions; the draft lives only while it is open. */
export function InstructionsDialog({ open, ...props }: InstructionsDialogProps) {
  return open ? <InstructionsEditor {...props} /> : null;
}

function InstructionsEditor({ onClose, repo, rule }: Omit<InstructionsDialogProps, "open">) {
  const toast = useToast();
  const { data: presets } = usePresets();
  const save = useSaveRule(repo);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [draft, setDraft] = useState(rule.custom_instructions);
  const [tab, setTab] = useState<"edit" | "preview">("edit");
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const dirty = draft !== rule.custom_instructions;
  const tooLong = draft.length > MAX_INSTRUCTION_CHARS;

  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  useEffect(() => textareaRef.current?.focus(), []);

  const requestClose = () => (dirty ? setConfirmDiscard(true) : onClose());
  const keepEditing = () => {
    setConfirmDiscard(false);
    blocker.reset?.();
  };
  const discard = () => {
    if (blocker.state === "blocked") blocker.proceed();
    else onClose();
  };
  const submit = () =>
    save.mutate(
      { ...toInput(rule), custom_instructions: draft },
      {
        onSuccess: () => {
          toast.success("Custom instructions saved");
          onClose();
        },
        onError: (error) => toast.error(error.message || "Could not save custom instructions"),
      },
    );

  return (
    <>
      <Dialog
        open
        onClose={requestClose}
        title="Custom instructions"
        description={`Added to the golden prompt on every review of ${repo}.`}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={requestClose}>
              Cancel
            </Button>
            <Button
              icon={<Save className="h-4 w-4" />}
              disabled={!dirty || tooLong}
              loading={save.isPending}
              onClick={submit}
            >
              Save
            </Button>
          </div>
        }
      >
        <div className="space-y-5">
          <div>
            <span className="label">Presets — click to insert</span>
            <div className="flex flex-wrap gap-2">
              {presets?.map((preset) => (
                <Chip
                  key={preset.id}
                  active={draft.includes(preset.instructions)}
                  onClick={() => setDraft(appendPreset(draft, preset.instructions))}
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
              <span className={tooLong ? "text-xs text-rose" : "text-xs text-muted"}>
                {draft.length.toLocaleString()} / {MAX_INSTRUCTION_CHARS.toLocaleString()}
              </span>
            </div>
            {tab === "edit" ? (
              <textarea
                ref={textareaRef}
                aria-label="Custom instructions"
                className="input min-h-[320px] font-mono text-xs leading-relaxed"
                rows={14}
                maxLength={MAX_INSTRUCTION_CHARS}
                placeholder="e.g. Strict check on idempotency keys in payment flows. Focus on async lifecycles and auth boundaries."
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
              />
            ) : (
              <div className="min-h-[320px] rounded-lg border border-border bg-bg/60 p-4">
                {draft.trim() ? <MarkdownView markdown={draft} /> : <p className="text-sm text-muted">Nothing to preview yet.</p>}
              </div>
            )}
          </div>
        </div>
      </Dialog>

      <Modal
        open={confirmDiscard || blocker.state === "blocked"}
        onClose={keepEditing}
        title="Discard unsaved changes?"
        actions={
          <>
            <Button variant="ghost" onClick={keepEditing}>
              Keep editing
            </Button>
            <Button variant="danger" onClick={discard}>
              Discard
            </Button>
          </>
        }
      >
        Your edits to the custom instructions for <strong>{repo}</strong> have not been saved.
      </Modal>
    </>
  );
}
