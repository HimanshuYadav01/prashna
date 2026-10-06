"""Acceptance test: the brief's own worked example (Annex A.3) + boundary date."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.precedence import resolve  # noqa: E402


def mk(doc_id, level, eff, supersedes="", text="x"):
    return {"text": text, "score": 0.9,
            "meta": {"doc_id": doc_id, "section": "7.2", "authority_level": level,
                     "effective_from": eff, "effective_to": "",
                     "supersedes": supersedes, "scope_programmes": "ALL"}}


REG = mk("ACAD-REG-2024", 1, "2024-07-01", text="minimum attendance 75 percent")
CIRC = mk("CIRC-ACAD-2026-08", 2, "2026-08-01",
          supersedes="ACAD-REG-2024#7.2", text="revised to 80 percent")
FAQ = mk("FAQ-DEPT-2026", 4, "2026-09-15", text="65 percent is enough")


def test_worked_example_circular_wins():
    d = resolve([REG, CIRC, FAQ], "2026-10-06")
    kept_docs = {c["meta"]["doc_id"] for c in d.kept}
    assert "CIRC-ACAD-2026-08" in kept_docs
    assert "ACAD-REG-2024" not in kept_docs          # superseded (step 2)
    assert any("supersedes" in l for l in d.log)
    top_docs = {c["meta"]["doc_id"] for c in d.top}
    assert top_docs == {"CIRC-ACAD-2026-08"}          # FAQ outranked (step 3)


def test_boundary_date_before_circular():
    d = resolve([REG, CIRC, FAQ], "2026-07-31")
    kept_docs = {c["meta"]["doc_id"] for c in d.kept}
    assert "ACAD-REG-2024" in kept_docs               # regulation still governs
    assert "CIRC-ACAD-2026-08" not in kept_docs       # not yet effective (step 1)
    assert any(c["meta"]["doc_id"] == "CIRC-ACAD-2026-08" for c in d.upcoming)


def test_level5_never_overrides():
    unofficial = mk("FORUM-POST", 5, "2026-09-01", text="no attendance needed")
    d = resolve([REG, unofficial], "2026-07-01")
    top_docs = {c["meta"]["doc_id"] for c in d.top}
    assert top_docs == {"ACAD-REG-2024"}
