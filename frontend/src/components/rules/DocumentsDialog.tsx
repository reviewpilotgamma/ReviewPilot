import { FileUp, Trash2 } from "lucide-react";
import { useRef } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Overlay";
import { ErrorState } from "@/components/ui/States";
import { useToast } from "@/hooks/useAuth";
import { useDeleteDocument, useRepoDocuments, useUploadDocument } from "@/hooks/useRules";
import { formatBytes } from "@/lib/rules";
import type { CacheStatus } from "@/types/api";

const CACHE_BADGES: Record<CacheStatus, { tone: "emerald" | "amber" | "gray"; label: string }> = {
  cached: { tone: "emerald", label: "Gemini cache ready" },
  pending: { tone: "amber", label: "Will be cached on next review" },
  inline: { tone: "gray", label: "Inline reference (below cache size)" },
  none: { tone: "gray", label: "No documents" },
};

interface DocumentsDialogProps {
  open: boolean;
  onClose: () => void;
  repo: string;
}

/** Popup for a repo's architecture and requirements documents; uploads and deletes apply immediately. */
export function DocumentsDialog({ open, onClose, repo }: DocumentsDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Architecture & requirements docs"
      description="Sent with the golden prompt as reference material; cached in Gemini when large."
    >
      <DocumentManager repo={repo} />
    </Dialog>
  );
}

function DocumentManager({ repo }: { repo: string }) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const { data, isLoading, isError, refetch } = useRepoDocuments(repo);
  const upload = useUploadDocument(repo);
  const remove = useDeleteDocument(repo);

  const onPick = (files: FileList | null) => {
    if (!files?.length) return;
    const picked = Array.from(files);
    void (async () => {
      for (const [index, file] of picked.entries()) {
        // Build the Gemini cache once, on the last file of the batch.
        const warm = index === picked.length - 1;
        try {
          const result = await upload.mutateAsync({ file, warm });
          if (result.cache_error) {
            toast.warning(`Uploaded ${file.name} — Gemini cache could not be built: ${result.cache_error}`);
          } else {
            toast.success(`Uploaded ${file.name}`);
          }
        } catch (error) {
          toast.error(error instanceof Error ? error.message : `Could not upload ${file.name}`);
        }
      }
      if (inputRef.current) inputRef.current.value = "";
    })();
  };

  return (
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
          {upload.isPending ? "Uploading & building cache…" : "Upload documents"}
        </Button>
        {data && <Badge tone={CACHE_BADGES[data.cache_status].tone}>{CACHE_BADGES[data.cache_status].label}</Badge>}
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
  );
}
