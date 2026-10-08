import type { PromptTemplate } from "@/types/api";

/** A small golden prompt fixture shaped like GET /prompt. */
export function promptFixture(overrides: Partial<PromptTemplate> = {}): PromptTemplate {
  const template =
    "You are ReviewPilot.\nRules:\n{{custom_instructions}}\nVerbosity: {{verbosity_directive}}\n" +
    "Security: {{security_directive}}\nNote: {{requester_note}}\n<!-- reviewpilot-meta: {} -->";
  return {
    template,
    is_default: true,
    updated_at: null,
    updated_by: null,
    segments: [
      { type: "text", text: "You are ReviewPilot.\nRules:\n" },
      { type: "slot", name: "custom_instructions" },
      { type: "text", text: "\nVerbosity: " },
      { type: "slot", name: "verbosity_directive" },
      { type: "text", text: "\nSecurity: " },
      { type: "slot", name: "security_directive" },
      { type: "text", text: "\nNote: " },
      { type: "slot", name: "requester_note" },
      { type: "text", text: "\n<!-- reviewpilot-meta: {} -->" },
    ],
    slots: [
      { name: "custom_instructions", label: "Your instructions", required: true },
      { name: "verbosity_directive", label: "Verbosity", required: false },
      { name: "security_directive", label: "Security", required: false },
      { name: "requester_note", label: "Requester note", required: false },
    ],
    directives: {
      verbosity: { concise: "Be concise.", detailed: "Be detailed." },
      security: { enabled: "SECURITY MODE ENABLED.", disabled: "Security mode disabled." },
    },
    placeholders: { no_instructions: "(none — apply general architectural standards)", no_note: "(none)" },
    warnings: [],
    ...overrides,
  };
}
