# Spec: Architecture document upload + Gemini context caching

## Overview

Allow multiple architecture/requirements documents per repository on the Rules page.
Documents are stored in existing SQLite, served to PR reviews via Gemini explicit context
caching when eligible (fallback: inject into the system prompt). Remove the 120k review
diff character cap (0 = unlimited).

## Functional Requirements

1. Rules page: upload multiple files (txt, md, markdown, pdf), list, delete.
2. Persist extracted text + metadata in SQLite (`repo_documents`).
3. On upload/delete, invalidate and recreate Gemini CachedContent when possible.
4. Every review/plan uses the repo's documents as authoritative reference.
5. `MAX_DIFF_CHARS=0` (default) means no truncation for PR reviews.
6. No new infrastructure services.

## Non-Functional Requirements

- Prefer Gemini explicit cache to cut repeated input token cost.
- If cache create fails (too small / unsupported), inject docs inline.
- CSRF + tenant access same as existing rules API.
- Max per-file size 5 MB; max 20 files per repo.

## Acceptance Criteria

- [ ] Upload/list/delete docs on Rules for an accessible repo
- [ ] Review prompt includes documents (cached or inline)
- [ ] Diffs are not truncated at 120k by default
- [ ] Backend tests cover truncate unlimited + document hash/cache invalidation

## Out of Scope

- Vector embeddings / RAG
- LangSmith caching
- New database products
