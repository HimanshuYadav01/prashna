# Prashna — AI University Student Services Assistant

HCLTech Future Ready AI Engineer Hackathon · NSUT · Team of 4

Answers student academic-service questions from authorised university documents
(cited), computes personal answers with deterministic tools over student records,
and never fabricates — unanswerable questions return
"I could not find this information in the authorised university sources."

## Architecture

```
Streamlit UI / judges' curl
        │
FastAPI + Pydantic v2 (fixed Section 6 contract)
        │
LangGraph pipeline — 8 nodes, max 2 LLM calls:
authorise → classify(LLM) → route → retrieve → precedence → tools → compose(LLM) → ground-check
        │                │                │
   ChromaDB (disk)    SQLite (students, rule_registry, audit)    Ollama (host)
```

Design principle: **the LLM does language; code does everything that must be
correct.** Eligibility, arithmetic, document precedence (Annex A) and citations
are deterministic code. The LLM only classifies the question (schema-constrained
JSON) and phrases the final answer. We claim capability level 4 (tool-using AI)
deliberately — no step here benefits from autonomous agents, and the brief's
scoring principle rewards the simplest justified design.

## Run (local, no Docker)

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8000           # API  (seeds SQLite + ingests corpus on first start)
streamlit run ui/app.py                     # UI   (http://localhost:8501)
```

Ollama must be running with the model pulled: `ollama pull qwen2.5:7b-instruct`.

## Run (Docker)

```bash
docker compose up --build    # api :8000, ui :8501; Ollama stays on the host
```

ChromaDB and SQLite live on named volumes — restarts do not re-ingest (R11/stack note).

## Configuration (env vars)

| Var | Default | Meaning |
|---|---|---|
| MOCK_LLM | false | true = run the whole pipeline without the model (deterministic classifier + template composer) |
| OLLAMA_URL | http://localhost:11434 | where Ollama lives |
| OLLAMA_MODEL | qwen2.5:7b-instruct | local model (llama3.1:8b also allowed) |
| EMBED_MODEL | all-MiniLM-L6-v2 | sentence-transformers model |

Cloud LLM fallback: not enabled by default; the switch point is `app/llm.py::_ollama_chat`
(disclosed here per the brief — demo runs fully local).

## API (Section 6 contract)

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/ask -H "Content-Type: application/json" \
  -d '{"question":"What is the minimum attendance required for end-semester exams?"}'
curl -s -X POST localhost:8000/ask -H "Content-Type: application/json" -H "X-Student-Id: S1007" \
  -d '{"question":"Am I eligible for the end-semester exam in CS201?","as_of_date":"2026-07-01"}'
curl -s -X POST localhost:8000/ingest -F file=@newdoc.pdf \
  -F 'metadata={"doc_id":"CIRC-X","title":"New circular","authority_level":2,"effective_from":"2026-10-06","supersedes":"","doc_type":"circular"}'
curl -s localhost:8000/audit/<trace_id>
curl -s localhost:8000/sources
python scripts/load_students.py --dir test_students/    # judge loader
```

Answer types: retrieved_fact · calculated · not_found · clarification_needed · refused · conflict_flagged.

## Evaluation

```bash
python eval/run_eval.py          # 25 labelled questions, six metrics
pytest tests/                    # precedence engine: the brief's worked example + boundary dates
```

## Data

- `data/documents/` + `data/source_register.csv` (Annex B). **The starter corpus is
  synthetic (marked synthetic=Y) so the system runs end-to-end immediately. Before
  judging, replace/augment with ≥3 real public NSUT documents via POST /ingest or
  the UI admin tab — the brief permits at most 2 synthetic documents.**
- Synthetic students: `scripts/generate_students.py` (LLM, verbatim prompt in
  `data/prompts/`), `scripts/validate_students.py`, loader `scripts/load_students.py`.
  Edge-case carriers documented in `data/data_card.md`.
- Reserved for judges (never used in our data): student IDs S9000–S9999, JDG course codes.

## Assumptions and limitations

- Attendance % computed by tools, never stored (Annex C).
- Thresholds live only in `rule_registry`, every row linked to source_doc_id+section;
  a new circular = a new row with its own effective_from — zero code change.
- CPU inference (~7 tok/s): max 2 LLM calls/question; p50/p95 reported by the eval.
- Known limits: single-course entity extraction per question; condonation (clause 7.3)
  is retrievable policy text but not modelled as a tool.
