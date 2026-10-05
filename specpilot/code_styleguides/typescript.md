# TypeScript Style Guide (frontend)

- ESLint (`frontend/eslint.config.js`) and `tsc -b --noEmit` must pass.
- Use strict types and avoid `any`. Put API response types next to the client in `src/services/`.
- Fetch server state with TanStack Query only. Do not fetch data ad hoc inside `useEffect`.
- Style with Tailwind utility classes and use `clsx` for conditional classes.
- Write function components and hooks. Keep components small, and move logic into hooks so it can be tested.
- Never put secrets in `VITE_*` variables, because they ship to the browser.
