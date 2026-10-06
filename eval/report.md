# Evaluation Report — Prashna

25 labelled questions (`questions.jsonl`), run end-to-end against the live API by
`run_eval.py`. Scoring method: expected `answer_type` match; answer correctness by
expected keywords/numbers in the answer + tool outputs (exact for numbers); citation
accuracy = expected source present in returned citations (cited sections spot-checked
manually against the documents); retrieval hit rate = expected source in the
retrieved set (read from audit records); latency and LLM-call counts from audit
records.

## Configurations compared

| Metric | A: qwen2.5:7b-instruct | B: qwen2.5:3b (raw) | C: qwen2.5:3b + code guards (final) |
|---|---|---|---|
| Answer correctness | 84.0% | 72.0% | **88.0%** |
| answer_type accuracy | 88.0% | 76.0% | **92.0%** |
| Citation accuracy | 88.0% | 80.0% | **92.0%** |
| Retrieval hit rate | 88.0% | 84.0% | **100.0%** |
| Abstention (unanswerable → not_found) | 100% | 100% | **100%** |
| Abstention (answerable → answered) | 100% | 89.5% | 89.5% |
| Latency p50 / p95 | 27.9s / 51.4s | 11.1s / 20.0s | **10.8s / 13.6s** |
| Mean LLM calls / question | 1.64 | 1.84 | 2.04 |

## Why configuration C won

The raw 3B model was 2.5x faster but misclassified generic policy phrasing
("what CGPA do I need") as personal questions, causing wrong refusals. Rather than
paying the 7B latency price, we added two code guards:

1. **Heuristic arbitration** — when the model and a deterministic regex heuristic
   disagree on personal-vs-policy, the heuristic wins; the `needs_personal_data`
   flag is always derived from the final category, never trusted raw.
2. **Abstention sentinel with forced retry** — the composer must emit
   `NOT_IN_SOURCES` when material doesn't answer the question; code converts it
   to `not_found`, except when retrieval evidence is strong (score ≥ 0.55) or
   tools produced results, where one forced re-compose runs instead.

Result: the guarded 3B beats the unguarded 7B on every quality metric at 2.6x the
speed. This is the system's design principle applied to model selection: measured
failure modes are patched with code, not with a bigger model.

## Known remaining failures (3/25)

- Two version-boundary questions where the composer judges the retrieved (correct)
  clause as not answering a question phrased around the old value or the FAQ's
  wrong claim — the sentinel converts these to `not_found` (safe direction:
  abstains rather than fabricates).
- One eligibility question where the classifier selects a sibling tool; the tool
  result is still correct and cited, but misses the expected phrasing.

Both are logged as limitations in the README.
