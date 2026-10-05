# Python Style Guide (backend)

- ruff is the source of truth (`backend/pyproject.toml`): line length 120, target py311, rules
  `E F W I B UP S ASYNC`.
- Respect the layers: `api/` (routers) → `services/` (logic) → `models/` (ORM). `schemas/` holds Pydantic I/O models,
  `core/` holds config, database, security, and HTTP.
- Read settings only through `app.core.config` and never call `os.environ` directly in services.
- Async code must not block. Use httpx async clients and keep blocking work off the event loop.
- Never log secrets, tokens, or full private keys.
- Put a type hint on every public function.
