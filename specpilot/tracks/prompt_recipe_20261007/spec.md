# Make the prompt composition visible, and the golden prompt editable

## Overview

Every review uses one **golden prompt**, the architecture review protocol (`REVIEW_SYSTEM_TEMPLATE`). Each repo's
custom instructions and uploaded documents are added on top of it, but the UI never shows that relationship.

This track adds:

- a slim **recipe strip** on the Rules page: Golden prompt + Instructions + Documents → Every PR review;
- a **prompt drawer** showing the assembled prompt, with the repo's additions highlighted where they are inserted;
- **admin editing of the golden prompt** in that drawer, with validation and reset to default;
- a **"Reviewed with"** line on each review, showing the context it actually used.

The UI uses the existing design system (paper/ink, signal teal, `glass` cards, lucide icons) and **no emojis**.

## Functional Requirements

1. **Recipe strip (`PromptRecipe`)**, shown above the editors on the Rules page. Three connected tiles with `+`
   separators and a trailing "→ Every PR review":
   - **Golden prompt** (lucide `Lock`): subtitle "Architecture review protocol · always applied", and "Default"
     or "Edited {date}"; the action is "View full prompt".
   - **Custom instructions**: live from the form, including unsaved edits — "N lines · Concise · Security on", or
     "Not set, defaults apply". An amber "Unsaved" dot shows when the form is dirty.
   - **Documents**: "2 files · Gemini cache ready" / "Inline reference" / "Will be cached on next review" /
     "None uploaded".

   Contributing tiles get a signal-soft tint; empty tiles a dashed border and muted text. Clicking the Instructions
   or Documents tile scrolls to and focuses its editor. On narrow screens the tiles stack vertically.
2. **Card hints.** The instructions card description becomes "Added to the golden prompt on every review of
   {repo}". The documents card description becomes "Sent with the golden prompt as reference material; cached in
   Gemini when large". The old "How rules are applied" card is removed, since the drawer replaces it.
3. **Prompt drawer (view).** Read-only, monospace, the full golden prompt with the repo's values filled into its
   slots (custom instructions, verbosity, security, and the requester note shown as "filled from the @review
   note"). Each slot is highlighted with a signal-soft background and a small label chip ("Your instructions",
   "Verbosity", "Security", "Requester note"). A final "+ Documents" block lists filenames and the delivery mode
   (Gemini cache / inline); document content is never shown. The view follows the current form, including unsaved
   edits. A "Copy" button copies the assembled text. An instructions slot longer than ~20 lines collapses behind
   "Show all".
4. **Golden prompt editing (admins).**
   - Admins see "Edit golden prompt" in the drawer. It switches to an editor with a notice ("Applies to every
     repository's reviews"), the raw template, a slot reference with insert-chips for `{{custom_instructions}}`,
     `{{verbosity_directive}}`, `{{security_directive}}` and `{{requester_note}}`, Save, Cancel, and "Reset to
     default" (with confirmation).
   - Non-admins see the view only, with the hint "Only admins can edit the golden prompt".
   - Validation, on the server and mirrored in the client:
     - `{{custom_instructions}}` must appear (otherwise repo instructions would be silently dropped);
     - the `reviewpilot-meta` output line must remain (the score/verdict parser depends on it);
     - unknown `{{tokens}}` are rejected;
     - maximum 20,000 characters, and the prompt cannot be empty.

     Missing optional slots (verbosity, security, requester note) are allowed, with a non-blocking warning.
   - The edited prompt is stored in the database with `updated_at` and `updated_by`. The default stays in code;
     "Reset" deletes the override.
   - Template syntax: only `{{name}}` tokens are substituted; every other character, including `{` and `}`, is
     literal. The built-in default is converted to this syntax with identical rendered output.
5. **API.**
   - `GET /api/v1/prompt` (any signed-in user) returns: `template` (raw text), `is_default`, `updated_at`,
     `updated_by`, `segments` (ordered text and slot segments of the template), `slots` (the allowed names and
     which are required), `directives` (verbosity and security texts), and `placeholders` (no-instructions and
     no-note texts).
   - `PUT /api/v1/prompt` (admin) takes `{template}`, validates it, and returns the same shape; 422 with reasons on
     failure.
   - `DELETE /api/v1/prompt` (admin) resets to the default; 204.
   - This is the frontend's only source for these strings: `lib/directives.ts` keeps only `appendPreset`.
6. **Reviews use the effective prompt.** `build_review_system_prompt` renders the stored override when one exists,
   otherwise the default. Plan prompts are unchanged.
7. **Reviewed with.** Each new review stores `review_context`:
   - `prompt`: `default` or `custom`, with the override's `updated_at`;
   - `instructions_chars`, `verbosity`, `security`;
   - `documents` (filenames) and `documents_mode` (`cached | inline | none`);
   - `requester_note` (bool).

   `GET /reviews/{id}` returns it. The review drawer shows one quiet line under the title: "Reviewed with  Golden
   prompt (edited Oct 7) · Instructions (Concise · Security on) · 2 documents (cached)", using lucide icons and no
   emojis. Older reviews have no context and show no line.

## Non-Functional Requirements

- One Alembic migration (`0003`): a nullable `pr_reviews.review_context` text (JSON) column, and a single-row
  `review_prompt` table (`id`, `template`, `updated_at`, `updated_by`). Existing rows are untouched.
- No new dependencies. No emojis in any new UI text or component.
- Keyboard accessible: the tiles are buttons; the drawer traps focus and closes with Esc; WCAG AA contrast.
- Document content never appears in the drawer, the API or the review context.
- Rendering the default template produces exactly today's prompt (regression test).

## Sad Paths & Error States

- Template fetch fails: the drawer shows `ErrorState` with retry; the strip still renders, showing "Golden
  prompt" without the default/edited detail.
- Save rejected (422): the editor shows the server's reasons inline and keeps the text.
- A non-admin calls PUT/DELETE: 403.
- The documents list fails: the Documents tile shows "Unavailable".
- A corrupt `review_context`: the line is hidden.

## Edge Cases

- Leaving the editor with unsaved edits asks for confirmation.
- A prompt saved while a review is running: the review uses whichever prompt it loaded; its `review_context`
  records which one.
- Repeated slot tokens are rendered at each occurrence.
- Switching repos updates the strip immediately.
- Plan jobs store no review context.

## Acceptance Criteria

- On the Rules page, a user sees at a glance that the golden prompt always applies, and what this repo's
  instructions and documents add.
- "View full prompt" shows the real effective prompt with the user's edits highlighted in place.
- An admin can edit, save and reset the golden prompt; invalid templates are refused with clear reasons; the next
  review uses the saved prompt (E2E).
- A new review's drawer shows "Reviewed with…", matching what was sent.
- No emojis appear in the new UI.
- `ruff`, `pytest`, `npm run lint`, `npm run typecheck` and `npm test` pass, with tests for the API, validation,
  rendering, context recording, the strip, the drawer and the editor.

## Out of Scope

- Per-repo golden prompts or a version history of edits.
- Editing the plan prompt.
- Removing emojis from existing PR comments or bot replies (separate decision).
- Showing document content.
