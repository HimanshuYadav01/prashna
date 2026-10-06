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
    load_corpus()


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


@app.post("/ingest")
async def post_ingest(file: UploadFile = File(...), metadata: str = Form(...)):
    meta = json.loads(metadata)
    required = ["doc_id", "title", "authority_level", "effective_from"]
    missing = [k for k in required if not meta.get(k)]
    if missing:
        raise HTTPException(422, f"metadata missing fields: {missing}")
    raw = await file.read()
    return ingest_document(file.filename, raw, meta)


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
    return {"inserted": inserted, "violations": report, "status": "ok" if not report else "partial"}
