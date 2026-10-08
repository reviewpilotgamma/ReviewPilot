import type { Rule, RuleInput } from "@/types/api";

export const MAX_INSTRUCTION_CHARS = 10_000;

export function toInput(rule: Rule): RuleInput {
  const { custom_instructions, verbosity, review_mode, enable_security } = rule;
  return { custom_instructions, verbosity, review_mode, enable_security };
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
