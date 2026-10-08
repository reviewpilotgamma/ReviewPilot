// Prompt strings (directives, placeholders, the golden prompt itself) come from GET /prompt; see lib/prompt.ts.

/** Append a preset to existing instructions, separated by a blank line; never duplicate it. */
export function appendPreset(current: string, preset: string): string {
  if (current.includes(preset)) return current;
  const trimmed = current.trimEnd();
  return trimmed ? `${trimmed}\n\n${preset}` : preset;
}
