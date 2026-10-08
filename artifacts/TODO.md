# TODO

Original backlog notes, with status checked against the code on 8 October 2026.
✅ done · 🟡 partly done · ⬜ not started · ➖ not a code task

1. ✅ Backend - Auth, DB, Encryption, Core module
   (seeded accounts with roles, SQLite + Alembic, Fernet-encrypted GitHub tokens, `backend/app/core/`)
2. ⬜ Deploy the backend - vercel, render, free one's.
   (no deployment config in the repo yet; see ARCHITECTURE.md §12 for the single-process constraint)
3. ✅ Frontend (React + Vite app in `frontend/`)
4. ✅ Minimal, proper UI UX for custom instruction (Rules page: instructions, presets, documents, golden prompt)
5. Core Logic
    - ✅ Auth
    - ✅ Github Auth (GitHub App JWT and installation tokens; user GitHub linked through the App install)
    - ✅ User raises PR (auto mode reviews on open; on-demand mode posts a welcome)
    - ✅ Comments command @--- (`@review [note]`, `@bot plan`)
    - ✅ Request lands on system (signed webhook → durable job → worker)
        - ✅ Git Diff (if data is too large, process must be batched) (diff batching, merged into one review)
        - ✅ AI Pipeline Invoked
            ✅ User Custom Instruction, req doc (prompt), project specific
            ✅ Parse, process the input docs, data (txt, md, rst, pdf; Gemini context cache)
            ✅ LLM reviews the PR against the grounded data
        - ✅ o/p Reviewed PR comment
    - ✅ Response as a comment in Github
    - ✅ Dashboard for user wise data on repo's, PR's, historical data analysis.


6. ➖ New Email, new github account separately for Review Pilot.
7. 🟡 A meaningful comment remains in a single pr, whereas if we have a summarizer who can summarize all teh senior comments  - analysis on the comments of the pr raised to get good insights.
   (Insights summarizes recurring themes across ReviewPilot's own reviews. Human reviewers' PR comments are not
   collected or analyzed yet.)
8. 🟡 input - requirement and architecture doc as to comment well on the pr raised
   - ✅ requirement and architecture documents per repository
   - ⬜ semantic search over the doc. (documents are injected whole, or via the Gemini cache; no retrieval)
