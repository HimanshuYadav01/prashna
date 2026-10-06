"""FastAPI — the fixed Section 6 contract."""
import csv
import io
import json
from typing import Optional

from fastapi import FastAPI, Header, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from . import db, llm
from .ingest import ingest_document, register_rows, load_corpus, collection
from .pipeline import ask

app = FastAPI(title="Prashna", description="AI University Student Services Assistant")


@app.on_event("startup")
def _startup():
    con = db.connect()
    db.seed(con)
    db.seed_credentials(con)
    load_corpus()


class LoginRequest(BaseModel):
    student_id: str
    password: str


@app.post("/auth/login")
def login(req: LoginRequest):
    """UI-layer authentication. Passwords are stored only as salted PBKDF2-SHA256
    hashes in SQLite (credentials table) — never plaintext. Note: the /ask
    identity contract remains the X-Student-Id header per the brief (Section 6);
    this endpoint gates the student UI, it does not replace the API contract."""
    con = db.connect()
    if not db.verify_password(con, req.student_id.strip(), req.password):
        raise HTTPException(401, "Invalid student ID or password")
    row = con.execute("SELECT student_id, full_name, programme FROM students "
                      "WHERE student_id=?", (req.student_id.strip(),)).fetchone()
    return {"ok": True, "student_id": row["student_id"],
            "full_name": row["full_name"], "programme": row["programme"]}


class AskRequest(BaseModel):
    question: str
    as_of_date: Optional[str] = None


class Citation(BaseModel):
    doc_id: str
    title: str = ""
    section: str = ""
    page: Optional[int] = None
    version: str = ""
    effective_from: str = ""


class AskResponse(BaseModel):
    trace_id: str
    answer: str
    answer_type: str
    citations: list[Citation] = []
    tools_invoked: list[dict] = []
    applied_rules: list[dict] = []
    conflicts_detected: list[str] = []
    explanation: str = ""
    as_of_date: str


@app.post("/ask", response_model=AskResponse)
def post_ask(req: AskRequest, x_student_id: Optional[str] = Header(default=None)):
    return ask(req.question, x_student_id, req.as_of_date)


class ResetRequest(BaseModel):
    student_id: str


class ResetConfirm(BaseModel):
    student_id: str
    code: str
    new_password: str


@app.post("/auth/reset_request")
def reset_request(req: ResetRequest):
    """Issues a one-time 15-minute reset code. The response is identical whether
    or not the student exists (no account enumeration). In production the code
    would be emailed; in this demo the admin panel is the delivery channel."""
    db.create_reset(db.connect(), req.student_id.strip())
    return {"ok": True, "message": "If the ID exists, a reset code has been issued. "
            "Collect it from the Academic Section (admin panel in this demo)."}


@app.post("/auth/reset_confirm")
def reset_confirm(req: ResetConfirm):
    con = db.connect()
    if len(req.new_password) < 6:
        raise HTTPException(422, "Password must be at least 6 characters")
    if not db.consume_reset(con, req.student_id.strip(), req.code):
        raise HTTPException(401, "Invalid or expired reset code")
    db.set_password(con, req.student_id.strip(), req.new_password)
    return {"ok": True, "message": "Password updated. You can sign in now."}


@app.get("/admin/reset_requests")
def reset_requests(x_admin_pin: Optional[str] = Header(default=None)):
    import os as _os
    if x_admin_pin != _os.environ.get("ADMIN_PIN", "prashna"):
        raise HTTPException(401, "Admin PIN required")
    rows = db.connect().execute(
        "SELECT student_id, code, expires_at FROM password_resets").fetchall()
    return [dict(r) for r in rows]


@app.post("/ingest")
async def post_ingest(file: UploadFile = File(...), metadata: str = Form(...)):
    meta = json.loads(metadata)
    required = ["doc_id", "title", "authority_level", "effective_from"]
    missing = [k for k in required if not meta.get(k)]
    if missing:
        raise HTTPException(422, f"metadata missing fields: {missing}")
    raw = await file.read()
    try:
        return ingest_document(file.filename, raw, meta)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/health")
def health():
    out = {"api": "ok"}
    try:
        con = db.connect()
        con.execute("SELECT 1")
        out["sqlite"] = "ok"
    except Exception as e:
        out["sqlite"] = f"error: {e}"
    try:
        out["chroma"] = f"ok ({collection().count()} chunks)"
    except Exception as e:
        out["chroma"] = f"error: {e}"
    if llm.MOCK:
        out["llm"] = "mock"
    else:
        try:
            import httpx
            r = httpx.get(f"{llm.OLLAMA_URL}/api/tags", timeout=5)
            out["llm"] = "ok" if r.status_code == 200 else f"status {r.status_code}"
        except Exception as e:
            out["llm"] = f"error: {e}"
    return out


@app.get("/audit/{trace_id}")
def get_audit(trace_id: str):
    rec = db.read_audit(db.connect(), trace_id)
    if not rec:
        raise HTTPException(404, "trace_id not found")
    return rec


@app.get("/sources")
def get_sources():
    return register_rows()


@app.post("/admin/load_students")
async def load_students(file: UploadFile = File(...)):
    """Judge loader: CSV in the Annex C students schema; validates then inserts."""
    raw = (await file.read()).decode("utf-8", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    con = db.connect()
    report, inserted = [], 0
    for i, r in enumerate(rows):
        try:
            sid = r["student_id"].strip()
            assert sid and sid[0] == "S" and sid[1:].isdigit(), "bad student_id"
            cgpa = float(r["cgpa"]); assert 0 <= cgpa <= 10, "cgpa out of range"
            sem = int(r["current_semester"]); assert 1 <= sem <= 10, "semester 1-10"
            bk = int(r["active_backlogs"]); assert bk >= 0, "backlogs >= 0"
            con.execute(
                "INSERT OR REPLACE INTO students VALUES (?,?,?,?,?,?,?)",
                (sid, r["full_name"], r["programme"], int(r["batch_year"]),
                 sem, cgpa, bk))
            inserted += 1
        except Exception as e:
            report.append(f"row {i + 2}: {e}")
    con.commit()
    created = db.seed_credentials(con)  # judge-loaded students get hashed default creds too
    return {"inserted": inserted, "credentials_created": created,
            "violations": report, "status": "ok" if not report else "partial"}
