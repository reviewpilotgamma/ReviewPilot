# Plan: Rules page — golden prompt first, instructions and documents in popups

## Context Snapshot

| Kind | Symbols |
| --- | --- |
| Existing | `pages/Rules.tsx` (`Rules`, `RuleEditor`, `DocumentPanel`, `CACHE_BADGES`, `formatBytes`, `toInput`, `sameRule`), `components/rules/PromptDrawer.tsx` (`PromptDrawer`, `PromptView`, `PromptEditor`, `SlotMark`), `components/rules/PromptRecipe.tsx`, `components/ui/Overlay.tsx` (`useDialog`, `Drawer`, `Modal`), `hooks/useRules.ts`, `hooks/usePrompt.ts`, `lib/directives.appendPreset`, `pages/pages.test.tsx` |
| New | `Overlay.tsx::Dialog`; `components/rules/GoldenPromptPanel.tsx`; `components/rules/InstructionsDialog.tsx`; `components/rules/DocumentsDialog.tsx`; `components/rules/RulesSidebar.tsx`; `lib/rules.ts` (`toInput`, `CACHE_LABELS`, `formatBytes`) |
| Modified | `Overlay.tsx::useDialog` (Esc only for the topmost dialog), `pages/Rules.tsx` (layout only), `pages/pages.test.tsx` |
| Removed | `components/rules/PromptDrawer.tsx`, `components/rules/PromptRecipe.tsx` |

### Hotspot map

| Requirement | Files / symbols |
| --- | --- |
| FR1 layout | `pages/Rules.tsx` |
| FR2 golden prompt | `components/rules/GoldenPromptPanel.tsx` (moved from `PromptDrawer.tsx`) |
| FR3 instructions popup | `components/rules/InstructionsDialog.tsx`, `Overlay.tsx::Dialog` |
| FR4 documents popup | `components/rules/DocumentsDialog.tsx` (moved from `Rules.tsx::DocumentPanel`) |
| FR5–FR7 sidebar | `components/rules/RulesSidebar.tsx` |

## Phase 1 — Popup primitive and redesigned Rules page

- [ ] 1.1 `Dialog` primitive
  - `Dialog({ open, onClose, title, description?, children, footer? })`: centered, `max-w-3xl`, `max-h-[90vh]`,
    header with close button, scrolling body, optional footer; uses `useDialog`.
  - `useDialog`: handle Escape only when the panel contains `document.activeElement`, so a confirm `Modal`
    stacked on a `Dialog` closes alone.
- [ ] 1.2 Rules page redesign
  - `lib/rules.ts`: `toInput(rule)`, `formatBytes`, `CACHE_LABELS`.
  - `GoldenPromptPanel`: `PromptDrawer` content as an inline `glass` section; props `repo`, `form` (saved
    `RuleInput`), `docs`, `prompt` query, `isAdmin`, `onDirtyChange`. Copy/Edit actions in the header.
  - `InstructionsDialog`: mounts its body only when open; draft from `rule.custom_instructions`; presets, tabs,
    counter; Save → `useSaveRule` with `{ ...toInput(rule), custom_instructions }`; dirty close → confirm
    `Modal`; `useBlocker` + `beforeunload` while dirty.
  - `DocumentsDialog`: `DocumentPanel` body inside `Dialog`.
  - `RulesSidebar`: repo name + Using defaults badge; option buttons with status lines; settings controls
    showing `save.variables` while pending, else saved values; Reset to defaults + confirm.
  - `Rules.tsx`: selector, grid `lg:grid-cols-[320px_minmax(0,1fr)]`, repo-switch confirm only for golden prompt
    edits.
  - Delete `PromptDrawer.tsx`, `PromptRecipe.tsx`; update `pages.test.tsx` (open popups before interacting,
    sidebar autosave test, discard confirm test, golden prompt inline).
  - Quality gate: `npm run lint`, `npm run typecheck`, `npm test` in `frontend/`.
