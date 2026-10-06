# Synthetic Data Card (Annex E)

**Purpose:** test data exercising every rule path: attendance thresholds (old and
revised), pass marks, supplementary eligibility, placement criteria, what-ifs.

**Generator:** seed data is deterministic Python (random seed 42) for
reproducibility; `scripts/generate_students.py` additionally generates students
with qwen2.5:7b-instruct (temperature 0.7, 1 call, JSON-schema-constrained).

**Prompts:** verbatim in `data/prompts/students_prompt.txt`.

**Schema enforcement:** Ollama structured output (JSON schema) + CSV validation
(`scripts/validate_students.py`); the loader re-validates before insert.

**Row counts:** 32 students · 2 programmes (B.Tech CSE/ECE) · 2 batches
(2023/2024) · 8 courses · 4 attendance rows and 4 result rows per student.

**Edge cases and carrier IDs:**
| Student | Edge case |
|---|---|
| S1007 | attendance 77.5% in CS201 — just above the 75% threshold (below the revised 80%) |
| S1008 | attendance 72.5% in CS201 — one class below the 75% threshold |
| S1009 | 39/100 in CS201 — one mark below the pass mark |
| S1010 | ABSENT in CS201 |
| S1011 | DETAINED in CS201 |
| S1012 | 3 active backlogs |
| S1013 | CGPA exactly 6.0 (placement cut-off), 0 backlogs |
| S1014 | failed CS201, 1 backlog — the what-if student |

**Validation results:** 0 violations on the shipped seed (run
`python scripts/validate_students.py data/generated_students.csv` for LLM output).

**What the LLM got wrong (observed during generation):** occasionally repeats
student IDs and drifts CGPA above 10 — both caught by the validator; we regenerate
or fix rows and record it here.

**Known limitations:** attendance/results exist only for 4 courses per student;
names are synthetic; no semester-wise GPA history.
