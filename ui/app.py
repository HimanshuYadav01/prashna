"""Prashna UI — Student and Admin as separate, clean views. Zero logic here."""
import json
import os

import httpx
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")
ADMIN_PIN = os.environ.get("ADMIN_PIN", "prashna")

st.set_page_config(page_title="Prashna", page_icon="🎓", layout="centered")

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 880px;}
.badge {display:inline-block; padding:2px 10px; border-radius:999px;
        font-size:.75rem; font-weight:600;}
.badge-calculated {background:#e8f3ec; color:#1d6f42;}
.badge-retrieved_fact {background:#e8eef8; color:#1a3c6e;}
.badge-not_found {background:#f1f1f1; color:#555;}
.badge-refused {background:#fdecec; color:#a32020;}
.badge-clarification_needed {background:#fff6e0; color:#8a6d00;}
.badge-conflict_flagged {background:#f8e8dc; color:#be5a1f;}
.cite {border-left:3px solid #1a3c6e; background:#f7f9fc; padding:6px 12px;
       margin:4px 0; font-size:.84rem; color:#2a3650; border-radius:0 8px 8px 0;}
.conflict {border-left:3px solid #be5a1f; background:#fdf6ef; padding:6px 12px;
           margin:4px 0; font-size:.82rem; color:#6b4a2f; border-radius:0 8px 8px 0;}
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


# ---------- sidebar: role switch ----------
with st.sidebar:
    st.markdown("## 🎓 Prashna")
    role = st.radio("View", ["Student", "Admin"], label_visibility="collapsed")
    st.divider()
    if role == "Student":
        students = ["(anonymous)"] + [f"S10{i:02d}" for i in range(1, 33)]
        who = st.selectbox("Logged in as", students)
        as_of = st.text_input("as_of_date", "", placeholder="YYYY-MM-DD · blank = today")
        st.caption("Identity is sent only as the X-Student-Id header.")
    else:
        if not st.session_state.get("admin_ok"):
            pin = st.text_input("Admin PIN", type="password")
            if st.button("Sign in"):
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
    st.caption("  ·  ".join(
        f"{'🟢' if str(v).startswith(('ok', 'mock')) else '🔴'} {k}" for k, v in h.items()))

# ---------- STUDENT VIEW ----------
if role == "Student":
    st.title("Ask Prashna")
    st.caption("Cited answers from authorised NSUT documents — or an honest “not found.”")

    if "history" not in st.session_state:
        st.session_state.history = []

    for item in st.session_state.history:
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

    q = st.chat_input("e.g. What is the minimum attendance for end-semester exams?")
    if q:
        headers = {} if who == "(anonymous)" else {"X-Student-Id": who}
        body = {"question": q}
        if as_of.strip():
            body["as_of_date"] = as_of.strip()
        import time
        t0 = time.time()
        with st.spinner("Checking the rules…"):
            try:
                resp = httpx.post(f"{API}/ask", json=body, headers=headers,
                                  timeout=240).json()
                audit = httpx.get(f"{API}/audit/{resp['trace_id']}", timeout=15).json()
            except Exception as e:
                st.error(f"API error: {e}")
                resp, audit = None, None
        if resp:
            st.session_state.history.append(
                {"q": q, "r": resp, "audit": audit,
                 "secs": round(time.time() - t0, 1)})
            st.rerun()

# ---------- ADMIN VIEW ----------
else:
    st.title("Admin")
    if not st.session_state.get("admin_ok"):
        st.info("Sign in with the admin PIN in the sidebar to manage documents.")
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
        st.dataframe(get_sources(), use_container_width=True, height=320)
    except Exception as e:
        st.caption(str(e))

    st.divider()
    st.subheader("Audit lookup")
    tid = st.text_input("trace_id")
    if tid.strip():
        r = httpx.get(f"{API}/audit/{tid.strip()}", timeout=15)
        st.json(r.json() if r.status_code == 200 else {"error": r.text})
