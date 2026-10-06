"""Prashna Streamlit UI — thin window over the API; zero logic here."""
import json
import os

import httpx
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Prashna", page_icon="🎓", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 2.2rem; max-width: 1100px;}
.prashna-title {font-size: 2.3rem; font-weight: 700; color: #152238; margin-bottom: 0;}
.prashna-sub {color: #6a7179; margin-top: 2px; margin-bottom: 1rem;}
.badge {display: inline-block; padding: 3px 12px; border-radius: 999px;
        font-size: 0.78rem; font-weight: 600; letter-spacing: .3px;}
.badge-calculated {background: #e8f3ec; color: #1d6f42;}
.badge-retrieved_fact {background: #e8eef8; color: #1a3c6e;}
.badge-not_found {background: #f4f4f4; color: #555;}
.badge-refused {background: #fdecec; color: #a32020;}
.badge-clarification_needed {background: #fff6e0; color: #8a6d00;}
.badge-conflict_flagged {background: #f8e8dc; color: #be5a1f;}
.cite {background: #fafaf7; border: 1px solid #e3e6e0; border-radius: 10px;
       padding: 8px 14px; margin: 4px 0; font-size: 0.86rem; color: #2a3650;}
.conflict {background: #fdf6ef; border-left: 4px solid #be5a1f; border-radius: 6px;
           padding: 8px 14px; margin: 6px 0; font-size: 0.85rem; color: #6b4a2f;}
[data-testid="stSidebar"] {background: #152238;}
[data-testid="stSidebar"] * {color: #e8edf3 !important;}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="prashna-title">🎓 Prashna</p>', unsafe_allow_html=True)
st.markdown('<p class="prashna-sub">Every answer cited, computed by a tool, or an honest '
            '&ldquo;I don&rsquo;t know.&rdquo;</p>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Session")
    students = ["(anonymous)"] + [f"S10{i:02d}" for i in range(1, 33)]
    who = st.selectbox("Logged in as", students)
    as_of = st.text_input("as_of_date", "", placeholder="YYYY-MM-DD (blank = today)")
    st.caption("Identity travels only as the X-Student-Id header — never in the message.")
    st.divider()
    try:
        h = httpx.get(f"{API}/health", timeout=5).json()
        st.markdown("### Health")
        for k, v in h.items():
            icon = "🟢" if str(v).startswith("ok") or v == "mock" else "🔴"
            st.caption(f"{icon} {k}: {v}")
    except Exception:
        st.caption("🔴 API unreachable")

tab_ask, tab_admin = st.tabs(["💬  Ask", "🗂  Admin · Ingest"])

with tab_ask:
    if "history" not in st.session_state:
        st.session_state.history = []

    for item in st.session_state.history:
        with st.chat_message("user"):
            st.write(item["q"])
        with st.chat_message("assistant"):
            r = item["r"]
            st.markdown(
                f'<span class="badge badge-{r["answer_type"]}">{r["answer_type"]}</span>'
                f' &nbsp;<span style="color:#9aa0a6;font-size:.78rem">as_of {r["as_of_date"]}'
                f' · trace {r["trace_id"]}</span>', unsafe_allow_html=True)
            st.write(r["answer"])
            for c in r["citations"]:
                st.markdown(
                    f'<div class="cite">📄 <b>{c["doc_id"]}</b> §{c["section"]}'
                    f'{" · v" + c["version"] if c["version"] else ""}'
                    f' · effective {c["effective_from"]}</div>', unsafe_allow_html=True)
            for conf in r["conflicts_detected"][:4]:
                st.markdown(f'<div class="conflict">⚖️ {conf}</div>', unsafe_allow_html=True)
            if r["tools_invoked"]:
                with st.expander("🔧 Tools invoked"):
                    st.json(r["tools_invoked"])
            with st.expander(f"🔍 Audit record · {r['trace_id']}"):
                try:
                    st.json(httpx.get(f"{API}/audit/{r['trace_id']}", timeout=30).json())
                except Exception as e:
                    st.caption(str(e))

    q = st.chat_input("Ask about rules, fees, attendance, eligibility…")
    if q:
        with st.chat_message("user"):
            st.write(q)
        headers = {} if who == "(anonymous)" else {"X-Student-Id": who}
        body = {"question": q}
        if as_of.strip():
            body["as_of_date"] = as_of.strip()
        with st.chat_message("assistant"):
            with st.spinner("Retrieving, checking rules, composing…"):
                try:
                    resp = httpx.post(f"{API}/ask", json=body, headers=headers,
                                      timeout=240).json()
                except Exception as e:
                    st.error(f"API error: {e}")
                    resp = None
        if resp:
            st.session_state.history.append({"q": q, "r": resp})
            st.rerun()

with tab_admin:
    c_left, c_right = st.columns([3, 2])
    with c_left:
        st.subheader("Ingest a document — live, no restart")
        up = st.file_uploader("Document (.pdf / .md / .txt)")
        c1, c2, c3 = st.columns(3)
        doc_id = c1.text_input("doc_id", "CIRC-NEW-01")
        title = c2.text_input("title", "New circular")
        level = c3.selectbox("authority_level", [1, 2, 3, 4, 5], index=1)
        c4, c5, c6 = st.columns(3)
        eff = c4.text_input("effective_from", "2026-10-06")
        sup = c5.text_input("supersedes", "", placeholder="ACAD-REG-2024#7.2")
        dtype = c6.text_input("doc_type", "circular")
        if st.button("Ingest", type="primary") and up:
            meta = {"doc_id": doc_id, "title": title, "authority_level": level,
                    "doc_type": dtype, "effective_from": eff, "supersedes": sup,
                    "issuer": "live ingest", "scope_programmes": "ALL",
                    "scope_batches": "ALL", "version": "1.0",
                    "retrieved_on": eff, "synthetic": "Y", "provenance": "live upload"}
            r = httpx.post(f"{API}/ingest",
                           files={"file": (up.name, up.getvalue())},
                           data={"metadata": json.dumps(meta)}, timeout=300)
            (st.success if r.status_code == 200 else st.error)(r.text)
    with c_right:
        st.subheader("Source Register")
        try:
            st.dataframe(httpx.get(f"{API}/sources", timeout=30).json(),
                         use_container_width=True, height=360)
        except Exception as e:
            st.caption(str(e))
