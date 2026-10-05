# Product Guidelines

## UX principles

- Primary actions stay on GitHub: `@review [note]` and `@bot plan`. The dashboard supports them; it does not
  replace them.
- The dashboard is simple and operator-focused: repositories, rules, review history, activity, and metrics.
- Webhooks are acknowledged immediately; review work happens in the background. Show status instead of
  making users wait.
- Failures are visible: a polite PR comment with a safe reason, and an entry in the Activity log.

## Review voice

- Write as a senior software architect: direct and specific, and always explain *why* something matters.
- Focus on architecture: module boundaries, async lifecycles, API contracts, failure modes, and security
  boundaries.
- No line-level style nitpicks unless they create an architectural or security risk.
- Every review has the same structure: score, verdict, and grouped findings.

## Visual and branding

- Tailwind CSS with lucide icons. The look is clean and minimal.
- There is no fixed brand kit yet. Keep colors and typography as Tailwind tokens so a brand can be applied later.

## Accessibility and usability

- Use semantic HTML and make every flow keyboard-navigable.
- Meet WCAG AA contrast.
- Never show secrets (webhook secret, private key, API keys, tokens) in full in the UI. Mask them.
