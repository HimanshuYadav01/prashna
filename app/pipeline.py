"""The eight-node LangGraph pipeline. Exactly two nodes call the LLM (classify,
compose); everything authoritative is code. Early exits: refused, not_found,
clarification_needed, conflict_flagged."""
import re
import time
import uuid
from datetime import date
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END

from . import db, llm, tools as T
from .ingest import retrieve
from .precedence import resolve

NOT_FOUND_MSG = "I could not find this information in the authorised university sources."
SIM_THRESHOLD = 0.40  # min retrieval score (1 - cosine distance) to count as evidence


class S(TypedDict, total=False):
    question: str
    student_id: Optional[str]
    as_of_date: str
    trace_id: str
    classification: dict
    chunks: list
    kept: list
    conflicts: list
    upcoming: list
    tool_results: list
    applied_rules: list
    answer: str
    answer_type: str
    explanation: str
    audit: dict
    done: bool


def node_authorise(s: S) -> S:
    s["audit"]["steps"].append("authorise")
    sid = s.get("student_id")
    mentioned = None
    m = re.search(r"\b(S\d{4})\b", s["question"].upper())
    if m:
        mentioned = m.group(1)
    if mentioned and mentioned != (sid or ""):
        s.update(answer="I can only answer questions about your own records.",
                 answer_type="refused",
                 explanation="Request referenced another student's data.", done=True)
    return s


PERSONAL = {"personal_data", "personal_eligibility", "what_if"}


def node_classify(s: S) -> S:
    c, stats = llm.classify(s["question"])
    # deterministic arbitration: when the model and the regex heuristic disagree
    # on whether the question is personal, the heuristic wins — small models
    # over-read "do I need" as personal, which causes wrong refusals
    h = llm._heuristic_classify(s["question"])
    if (c["question_category"] in PERSONAL) != (h["question_category"] in PERSONAL):
        c = h
        stats["mode"] = stats.get("mode", "") + "+heuristic_override"
    # the flag is always derived from the final category, never trusted raw
    c["needs_personal_data"] = c["question_category"] in PERSONAL
    s["classification"] = c
    s["audit"]["classification"] = c
    s["audit"]["llm"]["calls"] += stats["llm_calls"]
    s["audit"]["llm"]["tokens"] += stats["tokens"]
    s["audit"]["llm"]["mode"] = stats["mode"]
    s["audit"]["steps"].append("classify")
    return s


def node_route(s: S) -> S:
    c = s["classification"]
    s["audit"]["steps"].append("route")
    # NOTE: a model verdict of "not_answerable" is never trusted on its own —
    # retrieval still runs, and the ground-check returns not_found only when
    # no evidence survives. Abstention is decided by code, not model opinion.
    if c["needs_personal_data"] and not s.get("student_id"):
        s.update(answer="Please sign in so I can look at your own records.",
                 answer_type="refused",
                 explanation="Personal question without identity (X-Student-Id).",
                 done=True)
        return s
    if c["question_category"] in ("personal_data", "personal_eligibility", "what_if") \
            and not c.get("course_code") \
            and any(w in s["question"].lower() for w in ("attendance", "eligible for the", "exam in", "supplementary")) \
            and "placement" not in s["question"].lower():
        s.update(answer="Which course do you mean? Please include the course code (for example CS201).",
                 answer_type="clarification_needed",
                 explanation="Course required but not specified.", done=True)
    return s


def node_retrieve(s: S) -> S:
    s["chunks"] = retrieve(s["question"], k=8)
    s["audit"]["retrieved"] = [
        {"doc_id": c["meta"]["doc_id"], "section": c["meta"].get("section"),
         "score": c["score"]} for c in s["chunks"]]
    s["audit"]["steps"].append("retrieve")
    return s


def node_precedence(s: S) -> S:
    prog = None
    if s.get("student_id"):
        con = db.connect()
        p = T.get_student_profile(con, s["student_id"])
        prog = p["data"]["programme"] if p["ok"] else None
    strong = [c for c in s["chunks"] if c["score"] >= SIM_THRESHOLD]
    d = resolve(strong, s["as_of_date"], prog)
    # compose and cite from official sources (levels 1-2) when any exist;
    # handbooks/FAQs only surface when nothing official matched (Annex A step 3)
    official = [c for c in d.kept if int(c["meta"].get("authority_level", 5)) <= 2]
    s["kept"] = official if official else d.kept
    s["conflicts"] = list(dict.fromkeys(d.log))
    s["upcoming"] = [c["meta"]["doc_id"] for c in d.upcoming]
    s["audit"]["precedence_decisions"] = d.log
    s["audit"]["steps"].append("precedence")
    return s


def node_tools(s: S) -> S:
    s["audit"]["steps"].append("tools")
    c = s["classification"]
    cat = c["question_category"]
    if cat not in ("personal_data", "personal_eligibility", "what_if"):
        return s
    con = db.connect()
    sid, course = s["student_id"], c.get("course_code")
    ql = s["question"].lower()
    calls = []

    def call(name, **kw):
        fn = T.TOOLS[name]
        out = fn(con, **kw)
        calls.append({"tool": name, "input": kw,
                      "output": out.get("data", {"error": out.get("error")})})
        if out.get("applied_rules"):
            s["applied_rules"].extend(out["applied_rules"])
        return out

    if cat == "what_if" or "placement" in ql:
        overrides = {}
        if cat == "what_if" and course:
            overrides = {course: "PASS"}
        call("check_placement_eligibility", student_id=sid,
             as_of_date=s["as_of_date"], overrides=overrides or None)
        if course:
            call("check_supplementary_eligibility", student_id=sid,
                 course_code=course, as_of_date=s["as_of_date"])
    elif cat == "personal_eligibility":
        if "supplementary" in ql and course:
            call("check_supplementary_eligibility", student_id=sid,
                 course_code=course, as_of_date=s["as_of_date"])
        elif course:
            call("check_exam_eligibility", student_id=sid, course_code=course,
                 as_of_date=s["as_of_date"])
        else:
            call("get_student_profile", student_id=sid)
    else:  # personal_data
        if "attendance" in ql and course:
            call("get_attendance", student_id=sid, course_code=course)
        elif any(w in ql for w in ("marks", "result", "grade")):
            call("get_results", student_id=sid, course_code=course)
        else:
            call("get_student_profile", student_id=sid)

    s["tool_results"] = calls
    s["audit"]["tools_invoked"] = calls
    return s


STRONG_EVIDENCE = 0.55  # above this, a NOT_IN_SOURCES verdict triggers one forced retry


def node_compose(s: S) -> S:
    s["audit"]["steps"].append("compose")
    kept = s.get("kept", [])
    answer, stats = llm.compose(s["question"], kept,
                                s.get("tool_results", []), s.get("applied_rules", []))
    s["audit"]["llm"]["calls"] += stats["llm_calls"]
    s["audit"]["llm"]["tokens"] += stats["tokens"]
    top = max((c["score"] for c in kept), default=0.0)
    if "NOT_IN_SOURCES" in answer and (top >= STRONG_EVIDENCE or s.get("tool_results")):
        # strong evidence contradicts the abstention verdict: one forced retry
        answer, stats = llm.compose(s["question"], kept, s.get("tool_results", []),
                                    s.get("applied_rules", []), force=True)
        s["audit"]["llm"]["calls"] += stats["llm_calls"]
        s["audit"]["llm"]["tokens"] += stats["tokens"]
        s["audit"]["steps"].append("compose_forced_retry")
    s["answer"] = answer
    return s


def node_groundcheck(s: S) -> S:
    s["audit"]["steps"].append("groundcheck")
    kept, tools_used = s.get("kept", []), s.get("tool_results", [])
    if not kept and not tools_used:
        s.update(answer=NOT_FOUND_MSG, answer_type="not_found",
                 explanation="No authorised source or record covers this.")
        return s
    if "NOT_IN_SOURCES" in s.get("answer", ""):
        # composer judged the retrieved material off-target; code confirms by
        # replacing with the mandated abstention (R3)
        s.update(answer=NOT_FOUND_MSG, answer_type="not_found", kept=[],
                 explanation="Retrieved material did not answer the question.")
        return s
    if tools_used:
        s["answer_type"] = "calculated"
        s["explanation"] = "Computed by deterministic tools; thresholds from the rule registry."
    else:
        s["answer_type"] = "retrieved_fact"
        s["explanation"] = "Answer grounded in the cited document extracts."
    if s.get("upcoming"):
        s["answer"] += f" (Note: upcoming change in {', '.join(set(s['upcoming']))}.)"
    return s


def _after(node_name):
    def chooser(s: S):
        return END if s.get("done") else node_name
    return chooser


_graph = StateGraph(S)
for name, fn in [("authorise", node_authorise), ("classify", node_classify),
                 ("route", node_route), ("retrieve", node_retrieve),
                 ("precedence", node_precedence), ("tools", node_tools),
                 ("compose", node_compose), ("groundcheck", node_groundcheck)]:
    _graph.add_node(name, fn)
_graph.set_entry_point("authorise")
_graph.add_conditional_edges("authorise", _after("classify"))
_graph.add_edge("classify", "route")
_graph.add_conditional_edges("route", _after("retrieve"))
_graph.add_edge("retrieve", "precedence")
_graph.add_edge("precedence", "tools")
_graph.add_edge("tools", "compose")
_graph.add_edge("compose", "groundcheck")
_graph.add_edge("groundcheck", END)
PIPELINE = _graph.compile()


def ask(question: str, student_id: str | None, as_of_date: str | None):
    t0 = time.time()
    trace_id = uuid.uuid4().hex[:8]
    as_of = as_of_date or date.today().isoformat()
    state: S = {
        "question": question, "student_id": student_id, "as_of_date": as_of,
        "trace_id": trace_id, "chunks": [], "kept": [], "conflicts": [],
        "upcoming": [], "tool_results": [], "applied_rules": [],
        "audit": {"trace_id": trace_id, "timestamp": None, "steps": [],
                  "student_id": None, "llm": {"calls": 0, "tokens": 0, "mode": ""},
                  "model": llm.MODEL if not llm.MOCK else "mock"},
        "done": False,
    }
    out = PIPELINE.invoke(state)
    latency = int((time.time() - t0) * 1000)

    citations = [{
        "doc_id": c["meta"]["doc_id"], "title": c["meta"].get("title", ""),
        "section": c["meta"].get("section", ""), "page": None,
        "version": c["meta"].get("version", ""),
        "effective_from": c["meta"].get("effective_from", ""),
    } for c in (out.get("kept") or [])[:4]] if out.get("answer_type") in (
        "retrieved_fact", "calculated", "conflict_flagged") else []
    # de-dup citations by doc+section
    seen, uniq = set(), []
    for c in citations:
        k = (c["doc_id"], c["section"])
        if k not in seen:
            seen.add(k); uniq.append(c)

    audit = out["audit"]
    audit["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    audit["student_id"] = student_id if out.get("classification", {}).get(
        "needs_personal_data") else None
    audit["question_category"] = out.get("classification", {}).get("question_category")
    audit["answer_type"] = out.get("answer_type")
    audit["latency_ms"] = latency
    con = db.connect()
    db.write_audit(con, trace_id, audit["timestamp"], audit)

    return {
        "trace_id": trace_id,
        "answer": out.get("answer", NOT_FOUND_MSG),
        "answer_type": out.get("answer_type", "not_found"),
        "citations": uniq,
        "tools_invoked": out.get("tool_results", []),
        "applied_rules": out.get("applied_rules", []),
        "conflicts_detected": out.get("conflicts", []),
        "explanation": out.get("explanation", ""),
        "as_of_date": as_of,
    }
