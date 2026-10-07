# Plan: Apply static/ palette to current UI

## Context Snapshot

| Kind | Symbols / files |
| --- | --- |
| Existing | `frontend/tailwind.config.ts` color tokens; `frontend/src/index.css`; `frontend/index.html` `dark` class; accent usages of `violet` across UI |
| Source of truth | `static/app.css` `:root` vars + `.sky` gradient |
| Modified | Theme tokens, base CSS background, hardcoded purple hex in Button/Dashboard |
| Unchanged | Page structure, hooks, API types, copy |

## Phase 1 — Token remap

- [x] 1. Update `frontend/tailwind.config.ts` colors to static palette (`bg`/`surface`/`border`/`text`/`muted`/`violet`/`emerald`/`rose`/`amber` + soft variants).
- [x] 2. Update `frontend/src/index.css` to light `color-scheme`, sky-style background, and focus/input accents using signal.
- [x] 3. Remove `dark` from `frontend/index.html`.
- [x] 4. Replace hardcoded purple in `Button.tsx` glow and `Dashboard.tsx` chart stroke.
- [x] 5. Run frontend quality gate (`npm run typecheck`, `npm run lint`).
