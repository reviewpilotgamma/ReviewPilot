1. Backend - Auth, DB, Encryption, Core module 
2. Deploy the backend - vercel, render, free one's. 
3. Frontend
4. Minimal, proper UI UX for custom instruction 
5. Core Logic 
    - Auth 
    - Github Auth
    - User raises PR
    - Comments command @---
    - Request lands on system 
        - Git Diff (if data is too large, process must be batched)
        - AI Pipeline Invoked
            User Custom Instruction, req doc (prompt), project specific
            Parse, process the input docs, data
            LLM reviews the PR against the grounded data
        - o/p Reviewed PR comment
    - Response as a comment in Github
    - Dashboard for user wise data on repo's, PR's, historical data analysis. 


6. New Email, new github account separately for Review Pilot. 
7. Remove run review modal from the dashboard page. 
8. A meaningful comment remains in a single pr, whereas if we have a summarizer who can summarize all teh senior comments  - analysis on the comments of the pr raised to get good insights. 
9. input - requirement and architecture doc as to comment well on the pr raised 
- semantic search over the doc.


        