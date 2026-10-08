# Rules page: golden prompt first, instructions and documents in popups

## Overview

The Rules page opens on the **golden prompt**, rendered inline in the main area (no drawer). A **left sidebar**
holds two option buttons, **Custom instructions** and **Documents**, each with a status line, plus the always
visible **review settings** (Verbosity, Mode, Security audit) and **Reset to defaults**. Clicking an option opens
its popup; nothing opens until clicked. The recipe strip, inline editor card, documents card and prompt drawer are
removed.

## Functional Requirements

1. **Layout.** The repository selector stays on top. Below it, a two-column grid: sidebar (about 320px) on the
   left, golden prompt on the right. On narrow screens the sidebar stacks above the prompt.
2. **Golden prompt (main area, default view).** The assembled prompt for the selected repo with the repo's slot
   highlighting, the "Plus documents" delivery note, the default/edited badge and **Copy**. Admins get
   **Edit golden prompt**, which switches the main area in place to the existing editor (placeholders,
   validation, server errors, Save, Cancel, Reset to default with confirmation). Non-admins see "Only admins can
   edit the golden prompt." The prompt reflects **saved** rules.
3. **Custom instructions option.** Status line "N lines" or "Not set, defaults apply". Click opens a large popup
   with preset chips, Custom instructions / Preview tabs, the 10,000-char counter, **Cancel** and **Save**. Save
   persists the instructions with the current saved settings, toasts, and closes the popup.
4. **Documents option.** Status line "N files · <cache status>" or "None uploaded". Click opens a popup with the
   upload button (multi-file, warm the cache on the last file only), cache badge, format/limit hints, file list
   with delete, and the existing toasts (including the cache-failure warning). Changes apply immediately.
5. **Sidebar settings.** Verbosity, Mode and Security audit are always visible. Each change **saves
   immediately** (PUT with the saved instructions plus the new value) and toasts "Settings saved". Controls are
   disabled while a save is pending.
6. **Reset to defaults** in the sidebar, disabled when the repo uses defaults, with the existing confirmation.
7. **Using defaults** badge next to the repo name in the sidebar header.

## Non-Functional Requirements

- Reuse `useDialog` (Esc, focus trap, scroll lock, focus restore) via a new wide `Dialog` primitive in
  `Overlay.tsx`; `Modal` stays for confirmations. Esc only closes the topmost dialog.
- No emoji; existing theme tokens (`glass`, `violet`, `muted`).
- Vitest coverage for the new flows; `npm run lint`, `npm run typecheck`, `npm test` pass.

## Sad Paths & Error States

- Instructions save fails: popup stays open, edits kept, error toast.
- Settings save fails: control reverts to the saved value, error toast.
- Prompt load fails: `ErrorState` with Retry in the main area.
- Documents load fails: sidebar status "Unavailable"; popup shows `ErrorState` with Retry.
- One upload fails: error toast for that file; the rest of the batch continues.

## Edge Cases

- Closing the instructions popup with unsaved edits (X, Esc, backdrop, Cancel) asks "Discard unsaved changes?";
  confirming discards and closes. Navigating away with unsaved popup edits is blocked with the same question.
- A settings change while on defaults creates a saved rule ("Using defaults" disappears).
- Switching repos needs no instructions guard (the popup is modal); an admin with unsaved golden prompt edits
  gets a discard confirm.
- Instructions over 10,000 chars: counter turns red, Save disabled.

## Acceptance Criteria

- On load the golden prompt is visible in the main area and no dialog is open.
- Clicking **Custom instructions** opens a popup with presets and the editor; Save persists all four fields and
  the sidebar status updates. Closing with unsaved edits asks for confirmation.
- Clicking **Documents** opens a popup where upload, delete and the cache badge work as before.
- Toggling a sidebar setting sends a PUT immediately with the saved instructions.
- The recipe strip and `PromptDrawer` are gone; admin prompt editing works inline.

## Out of Scope

- Backend/API changes, golden prompt template or validation changes, preset changes.
