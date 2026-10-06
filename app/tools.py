"""Deterministic tools over SQLite + rule_registry. No LLM anywhere here (R5).
Every tool returns {ok, data|error, applied_rules[]} and never fabricates."""
from . import db


def _rule_ref(rule):
    return {"rule_id": rule["rule_id"],
            "value": f"{rule['operator']}{rule['value']}",
            "source_doc_id": rule["source_doc_id"],
            "source_section": rule["source_section"]}


def get_student_profile(con, student_id):
    row = con.execute("SELECT * FROM students WHERE student_id=?",
                      (student_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "student_not_found", "applied_rules": []}
    return {"ok": True, "data": dict(row), "applied_rules": []}


def get_attendance(con, student_id, course_code):
    row = con.execute(
        "SELECT * FROM attendance WHERE student_id=? AND course_code=?",
        (student_id, course_code)).fetchone()
    if not row:
        return {"ok": False, "error": "no_attendance_record", "applied_rules": []}
    pct = round(100.0 * row["classes_attended"] / row["classes_held"], 1)
    return {"ok": True, "applied_rules": [],
            "data": {"classes_held": row["classes_held"],
                     "classes_attended": row["classes_attended"],
                     "attendance_pct": pct}}


def check_exam_eligibility(con, student_id, course_code, as_of_date):
    att = get_attendance(con, student_id, course_code)
    if not att["ok"]:
        return att
    prof = get_student_profile(con, student_id)
    prog = prof["data"]["programme"] if prof["ok"] else None
    rule = db.get_rule(con, "min_attendance_pct", as_of_date, prog)
    if not rule:
        return {"ok": False, "error": "no_applicable_rule", "applied_rules": []}
    threshold = float(rule["value"])
    pct = att["data"]["attendance_pct"]
    eligible = pct >= threshold
    return {"ok": True, "applied_rules": [_rule_ref(rule)],
            "data": {"result": "ELIGIBLE" if eligible else "NOT_ELIGIBLE",
                     "attendance_pct": pct, "threshold": threshold,
                     "margin": round(pct - threshold, 1)}}


def get_results(con, student_id, course_code=None):
    q = "SELECT * FROM results WHERE student_id=?"
    args = [student_id]
    if course_code:
        q += " AND course_code=?"
        args.append(course_code)
    rows = [dict(r) for r in con.execute(q, args).fetchall()]
    if not rows:
        return {"ok": False, "error": "no_results", "applied_rules": []}
    return {"ok": True, "data": {"results": rows}, "applied_rules": []}


def check_supplementary_eligibility(con, student_id, course_code, as_of_date):
    res = get_results(con, student_id, course_code)
    if not res["ok"]:
        return res
    rule = db.get_rule(con, "supplementary_allowed_results", as_of_date)
    allowed = set((rule["value"] if rule else "FAIL,ABSENT").split(","))
    latest = res["data"]["results"][-1]
    ok = latest["result"] in allowed
    rules = [_rule_ref(rule)] if rule else []
    return {"ok": True, "applied_rules": rules,
            "data": {"result": "ELIGIBLE" if ok else "NOT_ELIGIBLE",
                     "course_result": latest["result"],
                     "allowed_after": sorted(allowed)}}


def check_placement_eligibility(con, student_id, as_of_date, overrides=None):
    """overrides e.g. {"CS201": "PASS"} — the what-if mechanism (R6)."""
    prof = get_student_profile(con, student_id)
    if not prof["ok"]:
        return prof
    p = prof["data"]
    cgpa_rule = db.get_rule(con, "min_cgpa", as_of_date, p["programme"])
    bklg_rule = db.get_rule(con, "max_active_backlogs", as_of_date, p["programme"])
    if not (cgpa_rule and bklg_rule):
        return {"ok": False, "error": "no_applicable_rule", "applied_rules": []}

    backlogs = p["active_backlogs"]
    assumptions = []
    if overrides:
        res = get_results(con, student_id)
        failed = {r["course_code"] for r in (res["data"]["results"] if res["ok"] else [])
                  if r["result"] in ("FAIL", "ABSENT")}
        for course, new in overrides.items():
            if new == "PASS" and course in failed and backlogs > 0:
                backlogs -= 1
                assumptions.append(f"assumed {course} supplementary result = PASS")

    failing = []
    if p["cgpa"] < float(cgpa_rule["value"]):
        failing.append(f"CGPA {p['cgpa']} < {cgpa_rule['value']} ({cgpa_rule['rule_id']})")
    if backlogs > int(bklg_rule["value"]):
        failing.append(f"active backlogs {backlogs} > {bklg_rule['value']} ({bklg_rule['rule_id']})")
    return {"ok": True,
            "applied_rules": [_rule_ref(cgpa_rule), _rule_ref(bklg_rule)],
            "data": {"result": "ELIGIBLE" if not failing else "NOT_ELIGIBLE",
                     "cgpa": p["cgpa"], "active_backlogs_considered": backlogs,
                     "failing_criteria": failing, "assumptions": assumptions}}


TOOLS = {
    "get_student_profile": get_student_profile,
    "get_attendance": get_attendance,
    "check_exam_eligibility": check_exam_eligibility,
    "get_results": get_results,
    "check_supplementary_eligibility": check_supplementary_eligibility,
    "check_placement_eligibility": check_placement_eligibility,
}
