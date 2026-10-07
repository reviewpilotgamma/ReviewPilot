# Plan: Make the prompt composition visible, and the golden prompt editable

## Context Snapshot

| Kind | Symbols |
| --- | --- |
| Existing | `prompts.REVIEW_SYSTEM_TEMPLATE`, `build_review_system_prompt`, `VERBOSITY_DIRECTIVES`, `SECURITY_*_DIRECTIVE`, `NO_INSTRUCTIONS`, `NO_NOTE`; `reviewer.handle_review`, `_docs_for_prompt`, `_load_rules`; `documents.list_documents`; `PRReview`; `schemas/reviews.ReviewDetail`; `api/deps.AdminUser`/`CurrentUser`; `main.create_app` router loop; frontend `Rules.tsx` (`RuleEditor`, `DocumentPanel`, "How rules are applied" card), `lib/directives.ts`, `Drawer`/`Modal`, `ReviewDrawer.tsx`, `useAuth().user.is_admin` |
| New | `models/review_prompt.py::ReviewPrompt`; migration `0003_prompt_and_context.py`; `services/golden_prompt.py` (`DEFAULT_TEMPLATE`, `SLOTS`, `REQUIRED_SLOTS`, `TOKEN_RE`, `render`, `segments`, `validate_template`, `load_effective`, `save_template`, `reset_template`); `api/prompt.py` (`GET/PUT/DELETE /prompt`); `schemas/prompt.py`; `ReviewContext` schema; frontend `types` (`PromptTemplate`, `ReviewContext`), `promptApi`, `hooks/usePrompt.ts`, `components/rules/PromptRecipe.tsx`, `components/rules/PromptDrawer.tsx`, `components/reviews/ReviewedWith.tsx` |
| Modified | `prompts.build_review_system_prompt` (renders the effective template via `golden_prompt.render`), `reviewer.handle_review` (records `review_context`), `_docs_for_prompt` (also returns filenames), `PRReview` (+`review_context`), `ReviewDetail` (+`review_context`), `models/__init__`, `main.py` (router), `Rules.tsx`, `ReviewDrawer.tsx`, `lib/directives.ts` (only `appendPreset` kept), `pages.test.tsx`, `lib.test.ts` |

### Hotspot map

| Requirement | Files / symbols |
| --- | --- |
| FR4 template syntax, validation, storage | `services/golden_prompt.py`, `models/review_prompt.py`, `alembic/versions/0003_prompt_and_context.py` |
| FR5 API | `api/prompt.py`, `schemas/prompt.py`, `main.py` |
| FR6 effective prompt | `services/prompts.py::build_review_system_prompt` (signature unchanged; reads the override via its own session) |
| FR7 review context | `reviewer.handle_review`, `_docs_for_prompt`, `models/pr_review.py`, `schemas/reviews.py` |
| FR1–FR3 Rules UI | `components/rules/PromptRecipe.tsx`, `components/rules/PromptDrawer.tsx`, `pages/Rules.tsx` |
| FR4 editor UI | `components/rules/PromptDrawer.tsx` (edit mode), `hooks/usePrompt.ts` |
| FR7 UI | `components/reviews/ReviewedWith.tsx`, `ReviewDrawer.tsx` |

### Design notes

- **Token syntax:** `TOKEN_RE = r"\{\{\s*([a-z_]+)\s*\}\}"`. `render(template, values)` substitutes known tokens
  only. `DEFAULT_TEMPLATE` is `REVIEW_SYSTEM_TEMPLATE` with `{name}` → `{{name}}` and the escaped meta braces
  `{{ }}` → literal `{ }`. A regression test asserts `render(DEFAULT_TEMPLATE, v) ==
  REVIEW_SYSTEM_TEMPLATE.format(**v)` for both verbosities and both security settings.
- **Segments:** `segments(template) -> list[{"type": "text", "text"} | {"type": "slot", "name"}]`, produced by
  splitting on `TOKEN_RE`. The frontend renders these with the current form values, so the drawer reflects
  unsaved edits without a round trip.
- **Storage:** a single-row table (`id = 1`). `load_effective(db) -> (template, row | None)`.
  `build_review_system_prompt` opens its own `SessionLocal()`, keeping the current call signature (it is pure
  today; the reviewer runs it on the event loop, and the read is one small primary-key lookup).
- **Review context:** captured in `handle_review` from the loaded rules, the cache result (`cached` when
  `cached_content`, `inline` when inline docs, else `none`), document filenames, the requester note, and
  `load_effective` metadata. Serialized to `review_context` as JSON.

## Phase 1 — Backend: golden prompt service, storage, API [checkpoint: bc0f865]

- [x] 1.1 Golden prompt service + model + migration `4954872`
  - `models/review_prompt.py::ReviewPrompt` (`id` int PK, `template` Text, `updated_at` UTCDateTime, `updated_by`
    String(100)); register it in `models/__init__`.
  - Migration `0003_prompt_and_context`: create `review_prompt`; add `pr_reviews.review_context` Text nullable;
    the downgrade drops both.
  - `services/golden_prompt.py`:
    - `SLOTS = ("custom_instructions", "verbosity_directive", "security_directive", "requester_note")`,
      `REQUIRED_SLOTS = ("custom_instructions",)`, `META_MARKER = "reviewpilot-meta"`, `MAX_TEMPLATE_CHARS =
      20_000`.
    - `DEFAULT_TEMPLATE`, `render`, `segments`.
    - `validate_template(text) -> tuple[list[str], list[str]]` (errors, warnings).
    - `load_effective(db)`, `save_template(db, text, username)` (raises `PromptValidationError(errors)`),
      `reset_template(db)`.
  - `prompts.build_review_system_prompt`: render the effective template with `golden_prompt.render`. Keep
    `REVIEW_SYSTEM_TEMPLATE` as the source of `DEFAULT_TEMPLATE`.
  - Tests `tests/test_golden_prompt.py`:
    - default render equals today's `.format` output (4 combinations)
    - literal braces survive
    - repeated tokens are rendered
    - validation: missing `{{custom_instructions}}`, missing meta, unknown token, empty, too long → errors;
      missing optional slots → warnings
    - save/load/reset round trip
    - `build_review_system_prompt` uses the override
- [x] 1.2 Prompt API — `schemas/prompt.py`, `api/prompt.py`, `main.py` `a22c679`
  - `PromptOut(template, is_default, updated_at, updated_by, segments, slots: list[{name, required, label}],
    directives: {verbosity: {concise, detailed}, security: {enabled, disabled}}, placeholders: {no_instructions,
    no_note})`. `PromptIn(template: str = Field(max_length=20_000))`.
  - Routes: `GET /prompt` (`CurrentUser`), `PUT /prompt` (`AdminUser`; 422 `{"detail": {"errors": [...]}}`),
    `DELETE /prompt` (`AdminUser`, 204). Router dependencies: `csrf_protect`.
  - Tests `tests/test_prompt_api.py`:
    - GET shape and defaults
    - PUT as admin (`login("admin-user")`) → `is_default=false`, `updated_by="admin-user"`
    - PUT invalid → 422 with reasons
    - PUT/DELETE as non-admin → 403
    - DELETE → default again
    - unauthenticated → 401
- [x] 1.3 Quality gate: `ruff check .`, `pytest`. `a22c679`

## Phase 2 — Backend: review context

- [x] 2.1 Record and expose `review_context` `83ccf79`
  - `_docs_for_prompt` returns `(cached, inline, filenames)`; update its callers in `handle_review`/`handle_plan`.
  - `handle_review` builds the context dict (see Design notes) and sets `PRReview.review_context =
    json.dumps(...)`. `PRReview` gets `review_context: Mapped[str | None]`.
  - `schemas/reviews.py`:
    - `ReviewContext(prompt: Literal["default","custom"], prompt_updated_at: datetime | None,
      instructions_chars: int, verbosity: str, security: bool, documents: list[str], documents_mode:
      Literal["cached","inline","none"], requester_note: bool)`.
    - `ReviewDetail.review_context: ReviewContext | None`, via a validator parsing the JSON string (`None` on
      bad JSON).
  - Tests:
    - `tests/test_reviewer.py`: a review with rules + inline docs records the context; a corrupt JSON row →
      `review_context` null in `GET /reviews/{id}`.
    - E2E `tests/e2e/test_prompt_flow.py`: an admin saves a custom golden prompt via `PUT /prompt` → the next
      review's Gemini system prompt contains the custom text and the repo instructions, and
      `review_context.prompt == "custom"`; large docs → `documents_mode == "cached"`; reset → `"default"`.
- [x] 2.2 Quality gate: `ruff check .`, `pytest`. `83ccf79`

## Phase 3 — Frontend: recipe strip, prompt drawer, editor, reviewed-with

- [ ] 3.1 Types, API and hooks — `types/api.ts` (`PromptTemplate`, `PromptSegment`, `ReviewContext`, and
  `ReviewDetail.review_context`), `services/endpoints.ts::promptApi` (`get`, `save`, `reset`),
  `hooks/usePrompt.ts` (`usePrompt`, `useSavePrompt`, `useResetPrompt`; invalidate `["prompt"]`).
  `lib/directives.ts`: remove the mirrored strings and `previewDirectives`, keep `appendPreset`; update
  `lib.test.ts`.
- [ ] 3.2 `components/rules/PromptRecipe.tsx`
  - Props: `rule form`, `dirty`, `docs: RepoDocumentList | undefined`, `docsError`, `prompt`, `onViewPrompt`,
    `onFocusInstructions`, `onFocusDocuments`.
  - Three `button` tiles in a `grid sm:grid-cols-[1fr_auto_1fr_auto_1fr_auto]` with `Plus` and `ArrowRight`
    separators. Lucide icons: `Lock`, `ListChecks`, `FileText`. Active tiles use
    `border-violet/40 bg-violet-soft`; empty tiles use `border-dashed text-muted`.
  - No emojis.
- [ ] 3.3 `components/rules/PromptDrawer.tsx`
  - View mode:
    - render `segments` with values from the form and `directives`; slots are a `mark` styled
      `bg-violet-soft rounded px-1` with a label chip
    - the requester note slot shows "filled from the @review note"
    - a "+ Documents" block with filenames and mode
    - "Copy" uses `navigator.clipboard`
    - "Show all" for long instructions
  - Edit mode (admins only):
    - a notice bar, a `textarea` (mono), insert-chips per slot, and live client validation mirroring the server
      (errors block Save; warnings shown)
    - Save, Cancel (confirm if dirty), "Reset to default" (`Modal` confirm)
    - server 422 reasons are shown inline
  - Non-admins see "Only admins can edit the golden prompt".
- [ ] 3.4 `Rules.tsx` wiring
  - Render `PromptRecipe` above the grid. Lift `DocumentPanel`'s query (the hook is already shared by query key)
    and refs for focus/scroll; pass the form state from `RuleEditor` up via a callback (`onFormChange`).
  - Update the card descriptions (FR2) and remove the "How rules are applied" card.
- [ ] 3.5 `components/reviews/ReviewedWith.tsx` + `ReviewDrawer.tsx`
  - One line under the title, rendered only when `review_context` is set:
    - `Lock` "Golden prompt" (+ "(edited Mon D)" when custom)
    - `ListChecks` "Instructions (Concise · Security on)", or "No instructions"
    - `FileText` "N documents (cached|inline)", or omitted when none
  - Muted text, separators `·`, no emojis.
- [ ] 3.6 Tests — `pages.test.tsx` and `components.test.tsx`:
  - the strip reflects instructions/doc states and the unsaved dot
  - "View full prompt" opens the drawer with the highlighted instructions slot showing unsaved edits
  - an admin edit → client validation blocks a template without `{{custom_instructions}}` → a valid save calls
    PUT
  - a non-admin sees no Edit button
  - `ReviewedWith` renders the line for a custom prompt + cached docs and nothing for a null context
  - an assertion that the new components render no emoji characters (`/\p{Extended_Pictographic}/u`)
- [ ] 3.7 Quality gate: `npm run lint`, `npm run typecheck`, `npm test`.

## Implementation Notes

_(filled in during implementation)_
