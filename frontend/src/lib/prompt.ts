// Assembling the golden prompt for display, and the client-side mirror of the server's template validation
// (backend/app/services/golden_prompt.py). The server stays authoritative; this only gives instant feedback.
import type { PromptSlotName, PromptTemplate, RuleInput } from "@/types/api";

export const TOKEN_RE = /\{\{\s*([a-z_]+)\s*\}\}/g;
export const META_MARKER = "reviewpilot-meta";
export const MAX_TEMPLATE_CHARS = 20_000;
export const REQUESTER_NOTE_HINT = "filled from the @review note";

export type AssembledPart = { kind: "text"; text: string } | { kind: "slot"; name: PromptSlotName; label: string; text: string };

export function slotValues(prompt: PromptTemplate, form: RuleInput): Record<PromptSlotName, string> {
  return {
    custom_instructions: form.custom_instructions.trim() || prompt.placeholders.no_instructions,
    verbosity_directive: prompt.directives.verbosity[form.verbosity],
    security_directive: form.enable_security ? prompt.directives.security.enabled : prompt.directives.security.disabled,
    requester_note: `(${REQUESTER_NOTE_HINT})`,
  };
}

/** The golden prompt with this repo's values filled into its slots, in order. */
export function assemblePrompt(prompt: PromptTemplate, form: RuleInput): AssembledPart[] {
  const values = slotValues(prompt, form);
  const labels = Object.fromEntries(prompt.slots.map((slot) => [slot.name, slot.label])) as Record<PromptSlotName, string>;
  return prompt.segments.map((segment) =>
    segment.type === "text"
      ? { kind: "text", text: segment.text }
      : { kind: "slot", name: segment.name, label: labels[segment.name] ?? segment.name, text: values[segment.name] },
  );
}

export function assembledText(parts: AssembledPart[]): string {
  return parts.map((part) => part.text).join("");
}

export function validateTemplate(template: string, prompt: PromptTemplate): { errors: string[]; warnings: string[] } {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!template.trim()) return { errors: ["The prompt cannot be empty."], warnings };
  if (template.length > MAX_TEMPLATE_CHARS) {
    errors.push(`The prompt is longer than ${MAX_TEMPLATE_CHARS.toLocaleString("en-US")} characters.`);
  }
  const used = new Set(Array.from(template.matchAll(TOKEN_RE), (match) => match[1]!));
  const known = new Set<string>(prompt.slots.map((slot) => slot.name));
  for (const slot of prompt.slots) {
    if (slot.required && !used.has(slot.name)) {
      errors.push(`Missing {{${slot.name}}}: repository instructions would be ignored.`);
    }
  }
  const unknown = [...used].filter((name) => !known.has(name)).sort();
  if (unknown.length) errors.push(`Unknown placeholder(s): ${unknown.map((name) => `{{${name}}}`).join(", ")}.`);
  if (!template.includes(META_MARKER)) {
    errors.push(`Keep the '${META_MARKER}' output line: the score and verdict are read from it.`);
  }
  for (const slot of prompt.slots) {
    if (!slot.required && !used.has(slot.name)) warnings.push(`{{${slot.name}}} is not used; that setting will have no effect.`);
  }
  return { errors, warnings };
}

/** Insert ``text`` at the textarea selection and return the new value and caret position. */
export function insertAt(value: string, start: number, end: number, text: string): { value: string; caret: number } {
  return { value: value.slice(0, start) + text + value.slice(end), caret: start + text.length };
}
