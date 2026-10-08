import { useMemo, useState } from "react";
import { Select } from "@/components/ui/Controls";
import { FullPageSpinner } from "@/components/ui/Spinner";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { DocumentsDialog } from "@/components/rules/DocumentsDialog";
import { GoldenPromptPanel } from "@/components/rules/GoldenPromptPanel";
import { InstructionsDialog } from "@/components/rules/InstructionsDialog";
import { RulesSidebar } from "@/components/rules/RulesSidebar";
import { useAuth, useWorkspace } from "@/hooks/useAuth";
import { usePrompt } from "@/hooks/usePrompt";
import { useRepoDocuments, useRule } from "@/hooks/useRules";
import { toInput } from "@/lib/rules";
import type { Rule } from "@/types/api";

interface RulesWorkspaceProps {
  repo: string;
  rule: Rule;
  onDirtyChange: (dirty: boolean) => void;
}

function RulesWorkspace({ repo, rule, onDirtyChange }: RulesWorkspaceProps) {
  const { user } = useAuth();
  const prompt = usePrompt();
  const docs = useRepoDocuments(repo);
  const [open, setOpen] = useState<"instructions" | "documents" | null>(null);
  const form = useMemo(() => toInput(rule), [rule]);
  const close = () => setOpen(null);

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)] lg:items-start">
      <RulesSidebar
        repo={repo}
        rule={rule}
        onOpenInstructions={() => setOpen("instructions")}
        onOpenDocuments={() => setOpen("documents")}
      />
      <GoldenPromptPanel
        repo={repo}
        form={form}
        docs={docs.data}
        prompt={prompt}
        isAdmin={Boolean(user?.is_admin)}
        onDirtyChange={onDirtyChange}
      />
      <InstructionsDialog open={open === "instructions"} onClose={close} repo={repo} rule={rule} />
      <DocumentsDialog open={open === "documents"} onClose={close} repo={repo} />
    </div>
  );
}

export default function Rules() {
  const { repos, selectedRepo, isLoading } = useWorkspace();
  const [repo, setRepo] = useState("");
  const active = repo || selectedRepo || repos[0]?.full_name || "";
  const { data: rule, isLoading: ruleLoading, isError, refetch } = useRule(active);
  // Unsaved golden prompt edits; instruction edits live in a modal popup, so they can't outlive a repo switch.
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
          // The workspace is keyed by repo, so switching discards edits: confirm first.
          if (dirty && !window.confirm("Discard your changes to the golden prompt?")) return;
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
      {rule && <RulesWorkspace key={active} repo={active} rule={rule} onDirtyChange={setDirty} />}
    </div>
  );
}
