import { describe, expect, it } from "vitest";
import { appendPreset, NO_INSTRUCTIONS, previewDirectives, SECURITY_DISABLED } from "./directives";
import { formatPercent, formatScore, prettyJson, scoreTone } from "./format";

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

describe("previewDirectives", () => {
  it("mirrors backend directive mapping", () => {
    const text = previewDirectives({
      custom_instructions: "",
      verbosity: "detailed",
      review_mode: "on_demand",
      enable_security: false,
    });
    expect(text).toContain(NO_INSTRUCTIONS);
    expect(text).toContain("Be detailed");
    expect(text).toContain(SECURITY_DISABLED);
    expect(text).toContain("only when someone comments @review");
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
