"""Prashna Streamlit UI — thin window over the API; zero logic here."""
import json
import os

import httpx
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Prashna", page_icon="❓", layout="wide")
st.title("Prashna — University Student Services Assistant")

students = ["(anonymous)"] + [f"S10{i:02d}" for i in range(1, 33)]
who = st.sidebar.selectbox("Logged in as", students)
as_of = st.sidebar.text_input("as_of_date (YYYY-MM-DD, blank = today)", "")
st.sidebar.caption("Identity is sent only as the X-Student-Id header.")

tab_ask, tab_admin = st.tabs(["Ask", "Admin · Ingest"])

with tab_ask:
    q = st.text_input("Your question", placeholder="What is the minimum attendance for end-semester exams?")
    if st.button("Ask", type="primary") and q.strip():
        headers = {} if who == "(anonymous)" else {"X-Student-Id": who}
        body = {"question": q}
        if as_of.strip():
            body["as_of_date"] = as_of.strip()
        with st.spinner("Thinking..."):
            r = httpx.post(f"{API}/ask", json=body, headers=headers, timeout=180)
        if r.status_code != 200:
            st.error(r.text)
        else:
            resp = r.json()
            st.markdown(f"**{resp['answer']}**")
            st.caption(f"answer_type: `{resp['answer_type']}` · as_of: {resp['as_of_date']}")
            for c in resp["citations"]:
                st.caption(f"📄 {c['doc_id']} §{c['section']}"
                           f"{' v' + c['version'] if c['version'] else ''}"
                           f" (effective {c['effective_from']})")
            if resp["conflicts_detected"]:
                st.warning("Conflicts: " + " | ".join(resp["conflicts_detected"]))
            with st.expander(f"Audit · {resp['trace_id']}"):
                a = httpx.get(f"{API}/audit/{resp['trace_id']}", timeout=30)
                st.json(a.json() if a.status_code == 200 else {"error": a.text})

with tab_admin:
    st.subheader("Ingest a document (live, no restart)")
    up = st.file_uploader("Document (.pdf / .md / .txt)")
    c1, c2, c3 = st.columns(3)
    doc_id = c1.text_input("doc_id", "CIRC-NEW-01")
    title = c2.text_input("title", "New circular")
    level = c3.selectbox("authority_level", [1, 2, 3, 4, 5], index=1)
    c4, c5, c6 = st.columns(3)
    eff = c4.text_input("effective_from", "2026-10-06")
    sup = c5.text_input("supersedes (e.g. ACAD-REG-2024#7.2)", "")
    dtype = c6.text_input("doc_type", "circular")
    if st.button("Ingest") and up:
        meta = {"doc_id": doc_id, "title": title, "authority_level": level,
                "doc_type": dtype, "effective_from": eff, "supersedes": sup,
                "issuer": "live ingest", "scope_programmes": "ALL",
                "scope_batches": "ALL", "version": "1.0",
                "retrieved_on": eff, "synthetic": "Y", "provenance": "live upload"}
        r = httpx.post(f"{API}/ingest",
                       files={"file": (up.name, up.getvalue())},
                       data={"metadata": json.dumps(meta)}, timeout=300)
        st.json(r.json() if r.status_code == 200 else {"error": r.text})
    st.divider()
    st.subheader("Source Register")
    if st.button("Refresh sources"):
        st.dataframe(httpx.get(f"{API}/sources", timeout=30).json())
