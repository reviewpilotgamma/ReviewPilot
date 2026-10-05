# Spec: Apply static/ palette to current UI

## Overview

Remap the React + Tailwind design tokens to the color system defined in `static/app.css`, without changing layout, components, copy, or data.

## Functional Requirements

1. Map Tailwind theme colors to static CSS variables: ink, muted, signal, signal-ink, line, warn, panel, paper.
2. Switch the app from dark mode to light mode so the paper/sky palette reads correctly.
3. Replace purple accent usage (token `violet`) with signal teal `#0f6e62`; keep the token name so component class names stay unchanged.
4. Map success (`emerald`) to signal teal; danger (`rose`) to warn `#9c3218`; mid/warning (`amber`) to a warm earth tone consistent with the sky palette.
5. Update page background gradients to the static sky wash (color only; no layout rebuild).
6. Fix hardcoded purple values (e.g. chart stroke, button glow) to signal/ink equivalents.

## Non-Functional Requirements

- WCAG AA contrast intent for body text on paper and primary CTA on ink/signal.
- No runtime or API behavior changes.
- No new dependencies.

## Sad Paths & Error States

- Unchanged; badges/toasts only change color tokens.

## Edge Cases

- `violet` class name remains for accent; only hex values change.
- Semi-transparent panel/border colors must remain readable over the sky background.

## Acceptance Criteria

- [ ] Landing, dashboard, settings, drawers use light paper/ink/signal colors from `static/app.css`.
- [ ] No purple (`#8b5cf6`) remains in theme tokens or hardcoded UI strokes/glows.
- [ ] Layout, routing, and API-driven content are unchanged.
- [ ] Frontend typecheck/lint still pass.

## Out of Scope

- Rebuilding pages to match static HTML class structure (`.mast`, `.cockpit`, etc.).
- Changing fonts to Sora/Source Serif (colors only).
- Changing border-radius or spacing system.
- Backend or webhook changes.
