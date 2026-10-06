"""Judge loader: python scripts/load_students.py --dir test_students/
Validates each CSV (Annex C students schema) then loads into SQLite."""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db  # noqa: E402


def validate_row(r, i):
    errs = []
    sid = (r.get("student_id") or "").strip()
    if not (sid.startswith("S") and sid[1:].isdigit() and len(sid) == 5):
        errs.append(f"row {i}: student_id format (S####): {sid!r}")
    try:
        if not 0 <= float(r["cgpa"]) <= 10:
            errs.append(f"row {i}: cgpa out of range")
    except Exception:
        errs.append(f"row {i}: cgpa not a number")
    try:
        if not 1 <= int(r["current_semester"]) <= 10:
            errs.append(f"row {i}: semester must be 1-10")
    except Exception:
        errs.append(f"row {i}: semester not an int")
    try:
        if int(r["active_backlogs"]) < 0:
            errs.append(f"row {i}: backlogs negative")
    except Exception:
        errs.append(f"row {i}: backlogs not an int")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    con = db.connect()
    db.seed(con)
    for f in sorted(Path(args.dir).glob("*.csv")):
        rows = list(csv.DictReader(open(f, encoding="utf-8")))
        errs = [e for i, r in enumerate(rows, start=2) for e in validate_row(r, i)]
        if errs:
            print(f"{f.name}: REJECTED")
            print(" ", "\n  ".join(errs))
            continue
        for r in rows:
            con.execute("INSERT OR REPLACE INTO students VALUES (?,?,?,?,?,?,?)",
                        (r["student_id"].strip(), r["full_name"], r["programme"],
                         int(r["batch_year"]), int(r["current_semester"]),
                         float(r["cgpa"]), int(r["active_backlogs"])))
        con.commit()
        print(f"{f.name}: loaded {len(rows)} students")


if __name__ == "__main__":
    main()
