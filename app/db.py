"""SQLite layer: Annex C schema, rule registry, audit records, seed data."""
import json
import os
import random
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("PRASHNA_DB", str(Path(__file__).resolve().parent.parent / "data" / "prashna.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
  student_id TEXT PRIMARY KEY,
  full_name TEXT NOT NULL,
  programme TEXT NOT NULL,
  batch_year INTEGER NOT NULL,
  current_semester INTEGER NOT NULL CHECK (current_semester BETWEEN 1 AND 10),
  cgpa REAL NOT NULL CHECK (cgpa BETWEEN 0 AND 10),
  active_backlogs INTEGER NOT NULL CHECK (active_backlogs >= 0)
);
CREATE TABLE IF NOT EXISTS courses (
  course_code TEXT PRIMARY KEY,
  course_name TEXT NOT NULL,
  programme TEXT NOT NULL,
  semester INTEGER,
  credits INTEGER
);
CREATE TABLE IF NOT EXISTS attendance (
  student_id TEXT NOT NULL REFERENCES students(student_id),
  course_code TEXT NOT NULL REFERENCES courses(course_code),
  classes_held INTEGER NOT NULL CHECK (classes_held > 0),
  classes_attended INTEGER NOT NULL CHECK (classes_attended >= 0),
  PRIMARY KEY (student_id, course_code)
);
CREATE TABLE IF NOT EXISTS results (
  student_id TEXT NOT NULL REFERENCES students(student_id),
  course_code TEXT NOT NULL REFERENCES courses(course_code),
  exam_session TEXT NOT NULL,
  exam_type TEXT NOT NULL CHECK (exam_type IN ('REGULAR','SUPPLEMENTARY')),
  internal_marks INTEGER NOT NULL,
  external_marks INTEGER NOT NULL,
  total_marks INTEGER NOT NULL,
  max_marks INTEGER NOT NULL,
  result TEXT NOT NULL CHECK (result IN ('PASS','FAIL','ABSENT','DETAINED'))
);
CREATE TABLE IF NOT EXISTS rule_registry (
  rule_id TEXT PRIMARY KEY,
  description TEXT NOT NULL,
  parameter TEXT NOT NULL,
  operator TEXT NOT NULL,
  value TEXT NOT NULL,
  scope_programmes TEXT NOT NULL DEFAULT 'ALL',
  scope_batches TEXT NOT NULL DEFAULT 'ALL',
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  source_doc_id TEXT NOT NULL,
  source_section TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_records (
  trace_id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  record TEXT NOT NULL
);
"""


def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


RULES = [
    # rule_id, description, parameter, op, value, scope_prog, scope_batch, from, to, doc, section
    ("ATT-MIN-01", "Minimum attendance to sit end-semester exams", "min_attendance_pct",
     ">=", "75", "ALL", "ALL", "2024-07-01", "2026-07-31", "ACAD-REG-2024", "7.2"),
    ("ATT-MIN-02", "Minimum attendance to sit end-semester exams (revised)", "min_attendance_pct",
     ">=", "80", "ALL", "ALL", "2026-08-01", None, "CIRC-ACAD-2026-08", "1"),
    ("PASS-MIN-01", "Minimum total marks to pass a course", "min_total_marks",
     ">=", "40", "ALL", "ALL", "2024-07-01", None, "ACAD-REG-2024", "9.1"),
    ("SUPP-01", "Supplementary exam allowed after FAIL or ABSENT", "supplementary_allowed_results",
     "in", "FAIL,ABSENT", "ALL", "ALL", "2024-07-01", None, "ACAD-REG-2024", "8.2"),
    ("PLACE-CGPA-01", "Minimum CGPA for placement registration", "min_cgpa",
     ">=", "6.0", "ALL", "ALL", "2025-01-10", None, "PLACE-POL-2025", "3.1"),
    ("PLACE-BKLG-01", "Maximum active backlogs for placement registration", "max_active_backlogs",
     "<=", "0", "ALL", "ALL", "2025-01-10", None, "PLACE-POL-2025", "3.2"),
]

COURSES = [
    ("CS201", "Data Structures", "B.Tech CSE", 3, 4),
    ("CS301", "Operating Systems", "B.Tech CSE", 5, 4),
    ("CS302", "Database Systems", "B.Tech CSE", 5, 4),
    ("MA201", "Mathematics III", "B.Tech CSE", 3, 4),
    ("EC201", "Digital Circuits", "B.Tech ECE", 3, 4),
    ("EC301", "Signals and Systems", "B.Tech ECE", 5, 4),
    ("EC302", "Communication Systems", "B.Tech ECE", 5, 4),
    ("HS201", "Economics", "B.Tech ECE", 3, 3),
]

FIRST = ["Aarav", "Diya", "Kabir", "Ira", "Vihaan", "Anaya", "Reyansh", "Myra",
         "Arjun", "Sara", "Dev", "Zoya", "Ishaan", "Tara", "Rudra", "Nitya"]
LAST = ["Sharma", "Verma", "Iyer", "Khan", "Das", "Mehta", "Reddy", "Nair"]


def seed(con):
    """Deterministic synthetic seed with the Annex-style edge cases baked in.

    Edge-case carriers (documented in data/data_card.md):
      S1007 attendance exactly above threshold (77.5% in CS201)
      S1008 attendance one class below 75% threshold
      S1009 marks one below pass mark (39/100 FAIL in CS201)
      S1010 ABSENT result in CS201
      S1011 DETAINED in CS201
      S1012 three active backlogs
      S1013 CGPA exactly at the 6.0 placement cut-off, zero backlogs
      S1014 failed CS201, otherwise placement-clean (the what-if student)
    """
    if con.execute("SELECT COUNT(*) c FROM students").fetchone()["c"]:
        return
    rng = random.Random(42)
    con.executemany("INSERT INTO courses VALUES (?,?,?,?,?)", COURSES)
    students = []
    for i in range(1, 33):
        sid = f"S10{i:02d}"
        prog = "B.Tech CSE" if i % 2 else "B.Tech ECE"
        batch = 2023 if i <= 16 else 2024
        cgpa = round(rng.uniform(5.0, 9.5), 2)
        backlogs = rng.choice([0, 0, 0, 1])
        students.append((sid, f"{rng.choice(FIRST)} {rng.choice(LAST)}", prog,
                         batch, 5 if batch == 2023 else 3, cgpa, backlogs))
    # pin edge cases
    def pin(sid, **kw):
        idx = next(i for i, s in enumerate(students) if s[0] == sid)
        s = list(students[idx])
        for k, v in kw.items():
            s[{"cgpa": 5, "active_backlogs": 6, "programme": 2}[k]] = v
        students[idx] = tuple(s)
    pin("S1012", active_backlogs=3)
    pin("S1013", cgpa=6.0, active_backlogs=0)
    pin("S1014", cgpa=7.1, active_backlogs=1)
    con.executemany("INSERT INTO students VALUES (?,?,?,?,?,?,?)", students)

    for (sid, _n, prog, *_rest) in students:
        my_courses = [c for c in COURSES if c[2] == prog][:4]
        for (code, *_c) in my_courses:
            held = 40
            att = rng.randint(28, 40)
            if sid == "S1007" and code == "CS201":
                att = 31          # 77.5% vs 75 → just eligible (pre-circular)
            if sid == "S1008" and code == "CS201":
                att = 29          # 72.5% → one class below 75%
            con.execute("INSERT INTO attendance VALUES (?,?,?,?)", (sid, code, held, att))
            internal = rng.randint(18, 30)
            external = rng.randint(15, 60)
            total = internal + external
            result = "PASS" if total >= 40 else "FAIL"
            if sid == "S1009" and code == "CS201":
                internal, external, total, result = 20, 19, 39, "FAIL"
            if sid == "S1010" and code == "CS201":
                internal, external, total, result = 22, 0, 22, "ABSENT"
            if sid == "S1011" and code == "CS201":
                internal, external, total, result = 0, 0, 0, "DETAINED"
            if sid == "S1014" and code == "CS201":
                internal, external, total, result = 21, 17, 38, "FAIL"
            con.execute("INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?)",
                        (sid, code, "2026-MAY", "REGULAR", internal, external,
                         total, 100, result))
    con.executemany(
        "INSERT INTO rule_registry VALUES (?,?,?,?,?,?,?,?,?,?,?)", RULES)
    con.commit()


def get_rule(con, parameter, as_of_date, programme="ALL", batch=None):
    """Pick the applicable rule row for a parameter on as_of_date (latest wins)."""
    rows = con.execute(
        """SELECT * FROM rule_registry WHERE parameter=?
           AND effective_from <= ?
           AND (effective_to IS NULL OR effective_to >= ?)
           ORDER BY effective_from DESC""",
        (parameter, as_of_date, as_of_date)).fetchall()
    for r in rows:
        if r["scope_programmes"] not in ("ALL", programme or "ALL"):
            continue
        return dict(r)
    return None


def write_audit(con, trace_id, ts, record: dict):
    con.execute("INSERT OR REPLACE INTO audit_records VALUES (?,?,?)",
                (trace_id, ts, json.dumps(record, ensure_ascii=False)))
    con.commit()


def read_audit(con, trace_id):
    row = con.execute("SELECT record FROM audit_records WHERE trace_id=?",
                      (trace_id,)).fetchone()
    return json.loads(row["record"]) if row else None


if __name__ == "__main__":
    c = connect()
    seed(c)
    print("DB ready:", DB_PATH,
          "| students:", c.execute("SELECT COUNT(*) c FROM students").fetchone()["c"],
          "| rules:", c.execute("SELECT COUNT(*) c FROM rule_registry").fetchone()["c"])
