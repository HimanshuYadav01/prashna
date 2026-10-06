"""Ingestion + retrieval: clause-aware chunking, ChromaDB (persisted), Source Register.
POST /ingest and the startup corpus load use the same code path (R11)."""
import csv
import os
import re
from pathlib import Path

import chromadb

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
REGISTER = DATA / "source_register.csv"
CHROMA_DIR = os.environ.get("CHROMA_DIR", str(DATA / "chroma"))

REG_FIELDS = ["doc_id", "title", "issuer", "authority_level", "doc_type",
              "version", "effective_from", "effective_to", "supersedes",
              "scope_programmes", "scope_batches", "provenance",
              "retrieved_on", "synthetic"]

_client = None
_collection = None
_embedder = None


def collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _client.get_or_create_collection(
            "university_docs", metadata={"hnsw:space": "cosine"})
    return _collection


def embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(
            os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2"))
    return _embedder


CLAUSE_RE = re.compile(r"^(#{1,3}\s+|(\d+(?:\.\d+)*)\s+)(.+)$")


def chunk_text(text: str, max_len=800, overlap=100):
    """Split on clause/heading boundaries first, cap length with overlap inside."""
    lines = text.splitlines()
    sections, cur, cur_sec = [], [], "intro"
    for ln in lines:
        m = CLAUSE_RE.match(ln.strip())
        # numeric clause lines ("7.2 A student must...") start a section at any
        # length; markdown headings only when short (they are titles)
        if m and (m.group(2) or len(ln.strip()) < 120):
            if cur:
                sections.append((cur_sec, "\n".join(cur).strip()))
            cur_sec = m.group(2).strip() if m.group(2) else "intro"
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        sections.append((cur_sec, "\n".join(cur).strip()))
    chunks = []
    for sec, body in sections:
        if not body:
            continue
        start = 0
        while start < len(body):
            piece = body[start:start + max_len]
            chunks.append((sec, piece))
            if start + max_len >= len(body):
                break
            start += max_len - overlap
    return chunks


def register_rows():
    if not REGISTER.exists():
        return []
    with open(REGISTER, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_register(meta: dict):
    exists = REGISTER.exists()
    REGISTER.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTER, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REG_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow({k: meta.get(k, "") for k in REG_FIELDS})


def extract_text(filename: str, raw: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader
        import io
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(raw)).pages)
    return raw.decode("utf-8", errors="replace")


def ingest_document(filename: str, raw: bytes, meta: dict) -> dict:
    """The one ingestion path: register row -> chunk -> embed -> immediately queryable."""
    text = extract_text(filename, raw)
    doc_id = meta["doc_id"]
    col = collection()
    # replace any previous version of this doc_id
    try:
        col.delete(where={"doc_id": doc_id})
    except Exception:
        pass
    pieces = chunk_text(text)
    if not pieces:
        return {"doc_id": doc_id, "chunks_indexed": 0, "status": "empty"}
    texts = [p[1] for p in pieces]
    embs = embedder().encode(texts, show_progress_bar=False).tolist()
    col.add(
        ids=[f"{doc_id}::{i}" for i in range(len(pieces))],
        embeddings=embs,
        documents=texts,
        metadatas=[{
            "doc_id": doc_id, "section": sec,
            "title": meta.get("title", ""), "issuer": meta.get("issuer", ""),
            "authority_level": int(meta.get("authority_level", 5)),
            "doc_type": meta.get("doc_type", ""), "version": meta.get("version", ""),
            "effective_from": meta.get("effective_from", ""),
            "effective_to": meta.get("effective_to", "") or "",
            "supersedes": meta.get("supersedes", "") or "",
            "scope_programmes": meta.get("scope_programmes", "ALL") or "ALL",
            "synthetic": meta.get("synthetic", "N"),
        } for (sec, _t) in pieces],
    )
    if not any(r["doc_id"] == doc_id for r in register_rows()):
        append_register(meta)
    return {"doc_id": doc_id, "chunks_indexed": len(pieces), "status": "indexed"}


def retrieve(query: str, k=8):
    col = collection()
    if col.count() == 0:
        return []
    emb = embedder().encode([query], show_progress_bar=False).tolist()
    res = col.query(query_embeddings=emb, n_results=min(k, col.count()))
    out = []
    for text, meta, dist in zip(res["documents"][0], res["metadatas"][0],
                                res["distances"][0]):
        out.append({"text": text, "meta": meta, "score": round(1 - dist, 3)})
    return out


def load_corpus():
    """Load every document in data/documents/ using rows from the Source Register."""
    docs_dir = DATA / "documents"
    if not docs_dir.exists():
        return 0
    reg = {r["doc_id"]: r for r in register_rows()}
    col = collection()
    existing = col.count()
    if existing > 0:
        return existing  # persisted — do not re-ingest on restart
    n = 0
    for f in sorted(docs_dir.iterdir()):
        doc_id = f.stem
        meta = reg.get(doc_id)
        if not meta:
            continue
        ingest_document(f.name, f.read_bytes(), meta)
        n += 1
    return n
