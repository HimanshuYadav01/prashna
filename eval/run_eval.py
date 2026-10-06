"""Run the labelled eval set against the live API and report the six metrics."""
import json
import statistics
import sys
from pathlib import Path

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
QUESTIONS = Path(__file__).parent / "questions.jsonl"


def main():
    rows = [json.loads(l) for l in open(QUESTIONS, encoding="utf-8") if l.strip()]
    results, latencies, llm_calls = [], [], []
    for q in rows:
        headers = {"X-Student-Id": q["student_id"]} if q["student_id"] else {}
        r = httpx.post(f"{API}/ask", headers=headers, timeout=300,
                       json={"question": q["question"], "as_of_date": q["as_of_date"]})
        resp = r.json()
        audit = httpx.get(f"{API}/audit/{resp['trace_id']}", timeout=30).json()
        latencies.append(audit.get("latency_ms", 0))
        llm_calls.append(audit.get("llm", {}).get("calls", 0))

        type_ok = resp["answer_type"] in q["expect_type"]
        blob = (resp["answer"] + " " + json.dumps(resp["tools_invoked"])).lower()
        ans_ok = all(k.lower() in blob for k in q["expect_contains"])
        cite_ok = (q["expect_source"] is None or
                   any(c["doc_id"] == q["expect_source"] for c in resp["citations"]))
        hit_ok = (q["expect_source"] is None or
                  any(c["doc_id"] == q["expect_source"]
                      for c in audit.get("retrieved", [])))
        results.append({"id": q["id"], "cat": q["category"], "type_ok": type_ok,
                        "ans_ok": ans_ok, "cite_ok": cite_ok, "hit_ok": hit_ok,
                        "got_type": resp["answer_type"]})
        mark = "PASS" if (type_ok and ans_ok and cite_ok) else "FAIL"
        print(f"[{mark}] #{q['id']:>2} {q['category']:<16} type={resp['answer_type']:<20}"
              f" ans_ok={ans_ok} cite_ok={cite_ok}")

    n = len(results)
    def pct(key): return round(100 * sum(r[key] for r in results) / n, 1)
    sourced = [r for r in results if r["hit_ok"] is not None]
    unans = [r for r in results if r["cat"] in ("unanswerable",)]
    answerable = [r for r in results if r["cat"] not in ("unanswerable", "cross_student", "no_identity")]
    abst_unans = round(100 * sum(r["got_type"] == "not_found" for r in unans) / max(len(unans), 1), 1)
    abst_ans = round(100 * sum(r["got_type"] != "not_found" for r in answerable) / max(len(answerable), 1), 1)
    lat = sorted(latencies)
    print("\n===== REPORT =====")
    print(f"questions: {n}")
    print(f"answer correctness:   {pct('ans_ok')}%")
    print(f"answer_type accuracy: {pct('type_ok')}%")
    print(f"citation accuracy:    {pct('cite_ok')}%")
    print(f"retrieval hit rate:   {pct('hit_ok')}%")
    print(f"abstention accuracy:  unanswerable->not_found {abst_unans}% | answerable->answered {abst_ans}%")
    print(f"latency p50: {lat[n // 2]} ms | p95: {lat[int(n * 0.95) - 1]} ms | "
          f"mean LLM calls/question: {round(statistics.mean(llm_calls), 2)}")


if __name__ == "__main__":
    main()
