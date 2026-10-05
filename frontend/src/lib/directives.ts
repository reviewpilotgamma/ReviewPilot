// Client-side mirror of backend/app/services/prompts.py so the Rules page can preview
// exactly how a configuration is turned into prompt directives.
import type { RuleInput } from "@/types/api";

export const VERBOSITY_DIRECTIVES = {
  concise:
    "Be concise: use short bullet points, at most ~5 findings, one or two sentences each. Skip minor issues.",
  detailed:
    "Be detailed: for each finding, trace the affected code path, explain the failure scenario, reference the specific files/hunks, and give a concrete remediation.",
} as const;

export const SECURITY_ENABLED =
  "SECURITY MODE ENABLED: explicitly check OWASP Top 10 risks (injection, broken auth/access control, SSRF, insecure deserialization), hardcoded secrets/token leakage in code, logs or config, missing input validation/sanitization, and trust-boundary violations. Report each as a finding with severity.";
export const SECURITY_DISABLED = "Security mode disabled: only flag security issues if they are Critical.";
export const NO_INSTRUCTIONS = "(none — apply general architectural standards)";

export function previewDirectives(rule: RuleInput): string {
  return [
    "Custom Repository Rules to Enforce:",
    rule.custom_instructions.trim() || NO_INSTRUCTIONS,
    "",
    `Verbosity: ${VERBOSITY_DIRECTIVES[rule.verbosity]}`,
    `Security Mode: ${rule.enable_security ? SECURITY_ENABLED : SECURITY_DISABLED}`,
    "",
    `Trigger: ${rule.review_mode === "auto" ? "automatic review when a PR is opened, plus @review" : "only when someone comments @review"}`,
  ].join("\n");
}

/** Append a preset to existing instructions, separated by a blank line; never duplicate it. */
export function appendPreset(current: string, preset: string): string {
  if (current.includes(preset)) return current;
  const trimmed = current.trimEnd();
  return trimmed ? `${trimmed}\n\n${preset}` : preset;
}
