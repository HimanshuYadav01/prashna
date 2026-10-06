"""Validation script (4.2): enforces Annex C schema + logical constraints and
reports violations. Usage: python scripts/validate_students.py <students.csv>"""
import csv
import sys


def main(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    errs = []
    seen = set()
    for i, r in enumerate(rows, start=2):
        sid = (r.get("student_id") or "").strip()
        if not (len(sid) == 5 and sid[0] == "S" and sid[1:].isdigit()):
            errs.append(f"row {i}: student_id must be S#### ({sid!r})")
        if sid in seen:
            errs.append(f"row {i}: duplicate student_id {sid}")
        seen.add(sid)
        if sid and "S9000" <= sid <= "S9999":
            errs.append(f"row {i}: {sid} is in the judge-reserved range")
        try:
            if not 0 <= float(r["cgpa"]) <= 10:
                errs.append(f"row {i}: cgpa out of 0-10")
        except Exception:
            errs.append(f"row {i}: cgpa not numeric")
        try:
            if not 1 <= int(r["current_semester"]) <= 10:
                errs.append(f"row {i}: current_semester out of 1-10")
        except Exception:
            errs.append(f"row {i}: current_semester not an int")
        try:
            if int(r["active_backlogs"]) < 0:
                errs.append(f"row {i}: active_backlogs negative")
        except Exception:
            errs.append(f"row {i}: active_backlogs not an int")
        if not (r.get("full_name") or "").strip():
            errs.append(f"row {i}: empty full_name")
    print(f"checked {len(rows)} rows: {len(errs)} violation(s)")
    for e in errs:
        print(" -", e)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main(sys.argv[1])
