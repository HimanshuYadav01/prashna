"""Generate synthetic students with the LLM against the Annex C schema (4.2).
The verbatim prompt lives in data/prompts/students_prompt.txt (a deliverable).
Falls back to deterministic generation if Ollama is unavailable."""
import csv
import json
import sys
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent.parent
PROMPT_FILE = BASE / "data" / "prompts" / "students_prompt.txt"
OUT = BASE / "data" / "generated_students.csv"

SCHEMA = {
    "type": "object",
    "properties": {"students": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "student_id": {"type": "string"},
            "full_name": {"type": "string"},
            "programme": {"type": "string", "enum": ["B.Tech CSE", "B.Tech ECE"]},
            "batch_year": {"type": "integer"},
            "current_semester": {"type": "integer"},
            "cgpa": {"type": "number"},
            "active_backlogs": {"type": "integer"},
        },
        "required": ["student_id", "full_name", "programme", "batch_year",
                     "current_semester", "cgpa", "active_backlogs"]}}},
    "required": ["students"],
}


def main():
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    try:
        r = httpx.post("http://localhost:11434/api/chat", timeout=600, json={
            "model": "qwen2.5:7b-instruct", "stream": False,
            "format": SCHEMA, "options": {"temperature": 0.7},
            "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        students = json.loads(r.json()["message"]["content"])["students"]
        src = "qwen2.5:7b-instruct"
    except Exception as e:
        print("Ollama unavailable, using deterministic fallback:", e)
        from random import Random
        rng = Random(7)
        students = [{
            "student_id": f"S11{i:02d}",
            "full_name": f"Student {i}",
            "programme": "B.Tech CSE" if i % 2 else "B.Tech ECE",
            "batch_year": 2023 if i <= 15 else 2024,
            "current_semester": 5 if i <= 15 else 3,
            "cgpa": round(rng.uniform(5.0, 9.5), 2),
            "active_backlogs": rng.choice([0, 0, 1]),
        } for i in range(1, 31)]
        src = "fallback"
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["student_id", "full_name", "programme",
                                          "batch_year", "current_semester",
                                          "cgpa", "active_backlogs"])
        w.writeheader()
        w.writerows(students)
    print(f"wrote {len(students)} students to {OUT} (generator: {src})")
    print("next: python scripts/validate_students.py", OUT)


if __name__ == "__main__":
    main()
