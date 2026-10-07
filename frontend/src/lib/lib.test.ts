import { describe, expect, it } from "vitest";
import { promptFixture } from "@/test/prompt";
import { appendPreset } from "./directives";
import { formatPercent, formatScore, prettyJson, scoreTone } from "./format";
import { assembledText, assemblePrompt, insertAt, validateTemplate } from "./prompt";

describe("appendPreset", () => {
  it("inserts into empty instructions", () => {
    expect(appendPreset("", "- rule")).toBe("- rule");
  });
  it("appends with a blank line separator", () => {
    expect(appendPreset("mine\n\n", "- rule")).toBe("mine\n\n- rule");
  });
  it("never duplicates a preset", () => {
    const once = appendPreset("mine", "- rule");
    expect(appendPreset(once, "- rule")).toBe(once);
  });
});

describe("assemblePrompt", () => {
  const form = { custom_instructions: "", verbosity: "detailed", review_mode: "on_demand", enable_security: false } as const;

  it("fills slots with the repo's values in template order", () => {
    const parts = assemblePrompt(promptFixture(), form);
    const slots = parts.filter((part) => part.kind === "slot");
    expect(slots.map((part) => part.kind === "slot" && part.label)).toEqual([
      "Your instructions",
      "Verbosity",
      "Security",
      "Requester note",
    ]);
    const text = assembledText(parts);
    expect(text).toContain("(none — apply general architectural standards)");
    expect(text).toContain("Verbosity: Be detailed.");
    expect(text).toContain("Security: Security mode disabled.");
    expect(text).toContain("(filled from the @review note)");
    expect(text).not.toContain("{{");
  });

  it("uses unsaved instructions verbatim", () => {
    const text = assembledText(assemblePrompt(promptFixture(), { ...form, custom_instructions: "  - Use {braces}  " }));
    expect(text).toContain("Rules:\n- Use {braces}\n");
  });
});

describe("validateTemplate", () => {
  const prompt = promptFixture();

  it("accepts the fixture template", () => {
    expect(validateTemplate(prompt.template, prompt)).toEqual({ errors: [], warnings: [] });
  });

  it("mirrors the server's blocking rules", () => {
    expect(validateTemplate("   ", prompt).errors).toEqual(["The prompt cannot be empty."]);
    const { errors } = validateTemplate("Review {{tone}}", prompt);
    expect(errors).toHaveLength(3);
    expect(errors.join(" ")).toContain("Missing {{custom_instructions}}");
    expect(errors.join(" ")).toContain("{{tone}}");
    expect(errors.join(" ")).toContain("reviewpilot-meta");
    expect(validateTemplate(`{{custom_instructions}} reviewpilot-meta ${"x".repeat(20_000)}`, prompt).errors[0]).toContain(
      "longer than 20,000",
    );
  });

  it("only warns about unused optional slots", () => {
    const result = validateTemplate("{{custom_instructions}}\nreviewpilot-meta", prompt);
    expect(result.errors).toEqual([]);
    expect(result.warnings).toHaveLength(3);
  });
});

describe("insertAt", () => {
  it("replaces the selection and moves the caret after the insert", () => {
    expect(insertAt("abcdef", 2, 4, "{{x}}")).toEqual({ value: "ab{{x}}ef", caret: 7 });
  });
});

describe("format helpers", () => {
  it("formats nullable values with an em dash", () => {
    expect(formatScore(null)).toBe("—");
    expect(formatScore(8.66)).toBe("8.7/10");
    expect(formatPercent(undefined)).toBe("—");
    expect(formatPercent(88.2)).toBe("88.2%");
    expect(formatPercent(94)).toBe("94%");
  });
  it("bands scores by verdict ranges", () => {
    expect(scoreTone(8)).toBe("emerald");
    expect(scoreTone(5)).toBe("amber");
    expect(scoreTone(4.9)).toBe("rose");
    expect(scoreTone(null)).toBe("muted");
  });
  it("pretty prints JSON and tolerates invalid input", () => {
    expect(prettyJson('{"a":1}')).toBe('{\n  "a": 1\n}');
    expect(prettyJson("nope")).toBe("nope");
  });
});
