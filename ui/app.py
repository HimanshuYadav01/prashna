"""Prashna UI — three roles: Guest (no login), Student (ID), Admin (PIN)."""
import json
import os
import time

import httpx
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")
ADMIN_PIN = os.environ.get("ADMIN_PIN", "prashna")

NAVY = "#152238"
ORANGE = "#BE5A1F"

st.set_page_config(page_title="Prashna", page_icon="🎓", layout="centered")

st.markdown(f"""
<style>
.block-container {{padding-top: 1.2rem; max-width: 900px;}}
.hero {{background: linear-gradient(120deg, {NAVY}, #1c3254); border-radius: 14px;
       padding: 22px 28px; margin-bottom: 1.1rem; color: #f3f5f0;}}
.hero h1 {{margin: 0; font-size: 1.9rem; color: #ffffff;}}
.hero p {{margin: 4px 0 0 0; color: #c6d0cb; font-size: .95rem;}}
.hero .role {{float: right; background: {ORANGE}; color: #fff; padding: 4px 14px;
             border-radius: 999px; font-size: .8rem; font-weight: 600; margin-top: 6px;}}
.badge {{display:inline-block; padding:2px 10px; border-radius:999px;
        font-size:.75rem; font-weight:600;}}
.badge-calculated {{background:#e8f3ec; color:#1d6f42;}}
.badge-retrieved_fact {{background:#e8eef8; color:#1a3c6e;}}
.badge-not_found {{background:#f1f1f1; color:#555;}}
.badge-refused {{background:#fdecec; color:#a32020;}}
.badge-clarification_needed {{background:#fff6e0; color:#8a6d00;}}
.badge-conflict_flagged {{background:#f8e8dc; color:{ORANGE};}}
.cite {{border-left:3px solid {NAVY}; background:#f7f9fc; padding:6px 12px;
       margin:4px 0; font-size:.84rem; color:#2a3650; border-radius:0 8px 8px 0;}}
.conflict {{border-left:3px solid {ORANGE}; background:#fdf6ef; padding:6px 12px;
           margin:4px 0; font-size:.82rem; color:#6b4a2f; border-radius:0 8px 8px 0;}}
[data-testid="stChatMessage"] {{background:#ffffff; border:1px solid #e7e7e1;
                                border-radius:12px; padding:10px 14px;}}
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li {{color:#17233B;}}
.hero p {{color:#c6d0cb !important;}}
div.stButton > button[kind="primary"] {{background:{ORANGE}; border:none;}}
[data-testid="stSidebar"] {{border-right: 3px solid {NAVY};}}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=60, show_spinner=False)
def get_health():
    try:
        return httpx.get(f"{API}/health", timeout=5).json()
    except Exception as e:
        return {"api": f"error: {e}"}


@st.cache_data(ttl=30, show_spinner=False)
def get_sources():
    return httpx.get(f"{API}/sources", timeout=30).json()


# ---------- sidebar: role selection ----------
with st.sidebar:
    st.markdown(f"<h2 style='color:{NAVY}'>🎓 Prashna</h2>", unsafe_allow_html=True)
    role = st.radio("Continue as", ["🙋 Guest", "🧑‍🎓 Student", "🛠 Admin"])
    role = role.split(" ", 1)[1]
    st.divider()

    who = None
    as_of = ""
    if role == "Guest":
        st.caption("No login needed. Ask about rules, fees, procedures and "
                   "scholarships. Personal questions need a student login.")
        as_of = st.text_input("as_of_date", "", placeholder="YYYY-MM-DD · blank = today")
    elif role == "Student":
        if not st.session_state.get("student"):
            sid_in = st.text_input("Student ID", placeholder="S1007")
            pw_in = st.text_input("Password", type="password",
                                  placeholder="demo: nsut@<your ID>")
            if st.button("Sign in", type="primary"):
                try:
                    r = httpx.post(f"{API}/auth/login", timeout=10,
                                   json={"student_id": sid_in.strip(),
                                         "password": pw_in})
                    if r.status_code == 200:
                        st.session_state.student = r.json()
                        st.rerun()
                    else:
                        st.error("Invalid student ID or password")
                except Exception as e:
                    st.error(f"API error: {e}")
            st.caption("Passwords are verified against salted PBKDF2 hashes — "
                       "never stored in plaintext.")
            with st.expander("Forgot password?"):
                r_sid = st.text_input("Your Student ID", key="rst_sid",
                                      placeholder="S1007")
                if st.button("Request reset code"):
                    try:
                        rr = httpx.post(f"{API}/auth/reset_request", timeout=10,
                                        json={"student_id": r_sid.strip()})
                        st.info(rr.json().get("message", rr.text))
                    except Exception as e:
                        st.error(str(e))
                r_code = st.text_input("Reset code", key="rst_code",
                                       placeholder="6-digit code from admin")
                r_pw = st.text_input("New password", type="password", key="rst_pw")
                if st.button("Set new password"):
                    try:
                        rc = httpx.post(f"{API}/auth/reset_confirm", timeout=10,
                                        json={"student_id": r_sid.strip(),
                                              "code": r_code.strip(),
                                              "new_password": r_pw})
                        if rc.status_code == 200:
                            st.success("Password updated — sign in above.")
                        else:
                            st.error(rc.json().get("detail", rc.text))
                    except Exception as e:
                        st.error(str(e))
        else:
            sdata = st.session_state.student
            who = sdata["student_id"]
            st.success(f"{sdata['full_name']} · {who}")
            st.caption(sdata["programme"])
            if st.button("Sign out"):
                st.session_state.student = None
                st.rerun()
            as_of = st.text_input("as_of_date", "",
                                  placeholder="YYYY-MM-DD · blank = today")
            st.caption("Your identity travels only as the X-Student-Id header; "
                       "you can only query your own records.")
    else:
        if not st.session_state.get("admin_ok"):
            pin = st.text_input("Admin PIN", type="password")
            if st.button("Sign in", type="primary"):
                if pin == ADMIN_PIN:
                    st.session_state.admin_ok = True
                    st.rerun()
                else:
                    st.error("Wrong PIN")
        else:
            st.success("Signed in as admin")
            if st.button("Sign out"):
                st.session_state.admin_ok = False
                st.rerun()

    st.divider()
    h = get_health()
    st.caption("  ".join(
        f"{'🟢' if str(v).startswith(('ok', 'mock')) else '🔴'}{k}" for k, v in h.items()))

# ---------- hero header ----------
subtitle = {"Guest": "Ask about rules, fees, procedures and notices — no login needed.",
            "Student": (f"Signed in as {who} — personal answers come from your records."
                        if who else "Sign in from the sidebar to ask about your own records."),
            "Admin": "Manage documents and inspect audit records."}[role]
st.markdown(f"""<div class="hero"><span class="role">{role}</span>
<h1>Prashna</h1><p>{subtitle}</p></div>""", unsafe_allow_html=True)

# ---------- GUEST + STUDENT: chat ----------
if role == "Student" and not who:
    st.info("Please sign in from the sidebar. You can still ask general questions as a Guest.")
    st.stop()
if role in ("Guest", "Student"):
    hist_key = f"history_{role}_{who or 'guest'}"
    if hist_key not in st.session_state:
        st.session_state[hist_key] = []

    for item in st.session_state[hist_key]:
        with st.chat_message("user"):
            st.write(item["q"])
        with st.chat_message("assistant"):
            r = item["r"]
            st.markdown(
                f'<span class="badge badge-{r["answer_type"]}">{r["answer_type"]}</span>'
                f' <span style="color:#9aa0a6;font-size:.75rem"> as_of {r["as_of_date"]}'
                f' · {item.get("secs","?")}s</span>', unsafe_allow_html=True)
            st.write(r["answer"])
            for c in r["citations"]:
                st.markdown(f'<div class="cite">📄 <b>{c["doc_id"]}</b> §{c["section"]}'
                            f' · effective {c["effective_from"]}</div>',
                            unsafe_allow_html=True)
            for conf in r["conflicts_detected"][:3]:
                st.markdown(f'<div class="conflict">⚖️ {conf}</div>', unsafe_allow_html=True)
            if r["tools_invoked"] or item.get("audit"):
                with st.expander(f"Details · trace {r['trace_id']}"):
                    if r["tools_invoked"]:
                        st.caption("Tools invoked")
                        st.json(r["tools_invoked"], expanded=False)
                    if item.get("audit"):
                        st.caption("Audit record")
                        st.json(item["audit"], expanded=False)

    placeholder = ("e.g. What is the tuition fee per semester?" if role == "Guest"
                   else "e.g. Am I eligible for the end-semester exam in CS201?")
    q = st.chat_input(placeholder)
    if q:
        headers = {} if who is None else {"X-Student-Id": who}
        body = {"question": q}
        if as_of.strip():
            body["as_of_date"] = as_of.strip()
        t0 = time.time()
        with st.chat_message("user"):
            st.write(q)
        with st.chat_message("assistant"):
            with st.spinner("Checking the rules…"):
                try:
                    resp = httpx.post(f"{API}/ask", json=body, headers=headers,
                                      timeout=240).json()
                    audit = httpx.get(f"{API}/audit/{resp['trace_id']}",
                                      timeout=15).json()
                except Exception as e:
                    st.error(f"API error: {e}")
                    resp, audit = None, None
        if resp:
            st.session_state[hist_key].append(
                {"q": q, "r": resp, "audit": audit,
                 "secs": round(time.time() - t0, 1)})
            st.rerun()

# ---------- ADMIN ----------
else:
    if not st.session_state.get("admin_ok"):
        st.info("Sign in with the admin PIN in the sidebar.")
        st.stop()

    st.subheader("Ingest a document")
    st.caption("Live — indexed and queryable immediately, no restart.")
    up = st.file_uploader("Document (.pdf / .md / .txt)")
    c1, c2, c3 = st.columns(3)
    doc_id = c1.text_input("doc_id", "CIRC-NEW-01")
    title = c2.text_input("title", "New circular")
    level = c3.selectbox("authority_level", [1, 2, 3, 4, 5], index=1)
    c4, c5, c6 = st.columns(3)
    eff = c4.text_input("effective_from", "2026-10-06")
    sup = c5.text_input("supersedes", "", placeholder="ACAD-REG-2024#7.2")
    dtype = c6.text_input("doc_type", "circular")
    if st.button("Ingest", type="primary", disabled=up is None):
        meta = {"doc_id": doc_id, "title": title, "authority_level": level,
                "doc_type": dtype, "effective_from": eff, "supersedes": sup,
                "issuer": "live ingest", "scope_programmes": "ALL",
                "scope_batches": "ALL", "version": "1.0",
                "retrieved_on": eff, "synthetic": "Y", "provenance": "live upload"}
        with st.spinner("Chunking and embedding…"):
            r = httpx.post(f"{API}/ingest",
                           files={"file": (up.name, up.getvalue())},
                           data={"metadata": json.dumps(meta)}, timeout=300)
        if r.status_code == 200:
            st.success(r.json())
            get_sources.clear()
        else:
            st.error(r.text)

    st.divider()
    st.subheader("Source Register")
    try:
        st.dataframe(get_sources(), use_container_width=True, height=300)
    except Exception as e:
        st.caption(str(e))

    st.divider()
    st.subheader("Password reset requests")
    st.caption("Stands in for the email channel: hand the code to the student "
               "after identity verification. Codes are one-time, 15-minute.")
    if st.button("Refresh requests"):
        try:
            rr = httpx.get(f"{API}/admin/reset_requests", timeout=10,
                           headers={"X-Admin-Pin": ADMIN_PIN})
            data = rr.json()
            if data:
                st.dataframe(data, use_container_width=True)
            else:
                st.caption("No pending reset requests.")
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("Audit lookup")
    tid = st.text_input("trace_id")
    if tid.strip():
        r = httpx.get(f"{API}/audit/{tid.strip()}", timeout=15)
        st.json(r.json() if r.status_code == 200 else {"error": r.text})
