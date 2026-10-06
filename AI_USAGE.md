# AI-Usage Disclosure

AI coding assistants (Claude) were used throughout, as the hackathon rules allow
and encourage. What was generated and how we verified it:

| Part | AI-generated? | Verified by |
|---|---|---|
| Precedence engine (app/precedence.py) | Yes, from our design | pytest: the brief's Annex A.3 worked example + boundary dates + level-5 test |
| Deterministic tools (app/tools.py) | Yes, from our design | eval questions with hand-computed expected values (e.g. 31/40 = 77.5%) |
| Pipeline (app/pipeline.py) | Yes, from our design | end-to-end eval set (25 questions, all six answer types) |
| API contract (app/main.py) | Yes | manual curl of every endpoint + /docs schema review |
| Synthetic documents & student seed | Yes | validate_students.py; register rows marked synthetic=Y |
| Eval set & runner | Yes | expected answers hand-checked against the documents |

Design decisions (single workflow, LLM-only-for-language, rule registry,
code-side citations) are ours and predate the code: see DESIGN_DOCUMENT.md.
Every member has walked through the modules they own and can modify them live.
