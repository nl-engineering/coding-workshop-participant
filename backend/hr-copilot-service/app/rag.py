"""Retrieval-augmented generation: ingestion, chunking, embeddings, hybrid search.

* Ingest: Markdown / text / HTML / PDF (pypdf) / CSV / JSON(L) knowledge files.
* Chunk: by section heading (keeps citations meaningful: doc + section).
* Embed: 'hashing' (offline, deterministic) or Gemini / Ollama embeddings.
* Store: PostgreSQL + pgvector when DATABASE_URL is set, else in-memory.
* Search: hybrid = vector cosine + BM25 keyword, so exact policy terms
  ("HC-2026", "I-9", "31 days") are never missed.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config

STOP = set("""a an the and or of to in on for with at by from is are was were be been being it its this that these those
i me my we our you your he she they them their his her as if then than so do does did can could would should will may
might must have has had not no yes please thanks thank hi hello there what when where which who how about into over
any all also just get got am up out need know tell let""".split())
SYN = {  # small HR domain thesaurus to help the offline embedder; a real embedding model makes this unnecessary
    "vacation": "pto", "holiday": "holidays", "days off": "pto", "time off": "pto", "leave days": "pto",
    "boss": "manager", "supervisor": "manager", "reporting line": "manager", "salary": "compensation",
    "earn": "compensation", "earns": "compensation", "underpaid": "compensation pay", "raise": "merit",
    "baby": "birth", "newborn": "birth dependent", "daughter": "child dependent", "son": "child dependent",
    "husband": "spouse dependent", "wife": "spouse dependent", "married": "marriage spouse", "surgery": "medical disability",
    "sick": "medical", "master": "tuition degree", "masters": "tuition degree", "degree": "tuition", "course": "tuition",
    "allowance": "stipend", "quit": "resignation", "resign": "resignation", "resigning": "resignation",
    "bank": "direct deposit bank", "paid": "pay payday", "paycheck": "pay payday", "payday": "pay payday",
    "abroad": "another country", "lisbon": "another country", "portugal": "another country", "india": "another country",
    "h-1b": "visa immigration", "h1b": "visa immigration", "green card": "immigration", "harass": "harassment",
    "inappropriate": "harassment misconduct", "comments": "harassment", "retaliation": "retaliation non-retaliation",
    "req": "requisition", "hire": "hiring", "new hire": "onboarding", "i9": "i-9",
}


def tokenize(text: str) -> list[str]:
    t = text.lower()
    for k, v in SYN.items():
        if k in t:
            t += " " + v
    out = []
    for w in re.findall(r"[a-z0-9][a-z0-9\-]*", t):
        if w in STOP or len(w) < 2:
            continue
        for suf in ("ing", "ed", "es", "s"):
            if len(w) > 5 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    section: str
    text: str
    source: str
    meta: dict = field(default_factory=dict)


# ------------------------------------------------------------------ ingestion

def _doc_id(path: Path) -> str:
    m = re.match(r"([A-Za-z]+-\d+)", path.stem)
    return m.group(1).upper() if m else path.stem[:40]


def _split_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    lines = text.splitlines()
    title = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), "")
    secs, cur, buf = [], "Overview", []
    for l in lines:
        if l.startswith("## "):
            if "".join(buf).strip():
                secs.append((cur, "\n".join(buf).strip()))
            cur, buf = l[3:].strip(), []
        elif not l.startswith("# "):
            buf.append(l)
    if "".join(buf).strip():
        secs.append((cur, "\n".join(buf).strip()))
    if len(secs) == 1 and len(secs[0][1]) > 1500:  # unstructured: window by paragraphs
        paras, out, acc = re.split(r"\n\s*\n", secs[0][1]), [], ""
        for p in paras:
            if len(acc) + len(p) > 1000 and acc:
                out.append((f"Part {len(out) + 1}", acc.strip()))
                acc = ""
            acc += p + "\n\n"
        if acc.strip():
            out.append((f"Part {len(out) + 1}", acc.strip()))
        secs = out
    return title, secs


def _read(path: Path) -> list[tuple[str, str]]:
    """Returns [(title, text)] -- one or many docs per file."""
    ext = path.suffix.lower()
    if ext in (".md", ".txt"):
        return [("", path.read_text(errors="ignore"))]
    if ext in (".html", ".htm"):
        t = re.sub(r"<(script|style).*?</\1>", " ", path.read_text(errors="ignore"), flags=re.S | re.I)
        t = re.sub(r"<h[12][^>]*>(.*?)</h[12]>", r"\n## \1\n", t, flags=re.I | re.S)
        return [("", html.unescape(re.sub(r"<[^>]+>", " ", t)))]
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            return [("", "\n\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages))]
        except Exception:  # noqa: BLE001
            return []
    if ext in (".csv", ".json", ".jsonl"):
        rows = _rows(path)
        out = []
        for r in rows:
            low = {k.lower(): v for k, v in r.items()}
            body = next((low[k] for k in ("content", "body", "text", "article", "answer", "description") if low.get(k)), "")
            title = next((low[k] for k in ("title", "name", "question", "subject") if low.get(k)), "")
            if body:
                out.append((str(title), f"# {title}\n\n{body}" if title else str(body)))
        return out
    return []


def _rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with open(path, newline="", encoding="utf-8", errors="ignore") as f:
            return list(csv.DictReader(f))
    if path.suffix.lower() == ".jsonl":
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    d = json.loads(path.read_text())
    if isinstance(d, dict):
        d = next((v for v in d.values() if isinstance(v, list)), [d])
    return d


HEADER = re.compile(r"(?im)^\s*>?\s*(domain|country|effective date|status|last updated|owner|audience)\s*:.*$")


def _paragraphs(text: str) -> list[str]:
    """PDF/markdown body -> clean paragraphs (joins wrapped lines, drops header/meta lines)."""
    text = HEADER.sub("", text)
    text = re.sub(r"(?m)^\s*\*\*Domain:\*\*.*$", "", text)
    text = re.sub(r"(?m)^\s*⚠️.*$", "", text)
    out = []
    for block in re.split(r"\n\s*\n", text):
        b = re.sub(r"\s+", " ", block).strip()
        if len(b) > 25 and not b.startswith("#"):
            out.append(b)
        elif b.startswith("## "):
            out.append(b)
    return out


def load_manifest_chunks(folder: Path) -> list[Chunk]:
    """Workshop KB: one chunk per paragraph with manifest metadata (country, domain, topic, type, dates, conflicts)."""
    man = json.loads((folder / "manifest.json").read_text())
    chunks: list[Chunk] = []
    for d in man:
        f = folder / d.get("file", f"{d['doc_id']}.md")
        if not f.exists():
            continue
        raw = f.read_text(errors="ignore")
        title = next((l.lstrip("# ").strip() for l in raw.splitlines() if l.strip()), d["topic"])
        section, n = "Policy", 0
        units = []
        for para in _paragraphs(raw):
            if para.startswith("## ") or d["type"] == "runbook":
                units.append(para)
            else:  # policy / wiki: one sentence per chunk -> precise citations and conflict diffs
                units += [x.strip() for x in re.split(r"(?<=[.;])\s+(?=[A-Z])", para) if x.strip()]
        for para in units:
            if para.startswith("## "):
                section = para[3:].strip()
                continue
            if re.sub(r"\W", "", para.lower()) == re.sub(r"\W", "", title.lower()) or para.startswith("Step-by-step procedure for"):
                continue
            n += 1
            para = re.sub(r"^\d+\.\s*", "", para)
            chunks.append(Chunk(id=f"{d['doc_id']}#{n}", doc_id=d["doc_id"], title=title, section=section if d["type"] != "policy_pdf" else d["topic"],
                                text=para, source=d.get("path", f.name),
                                meta={k: d.get(k) for k in ("type", "domain", "topic", "country", "effective_date", "is_conflict", "conflict_of")}))
    return chunks


def load_chunks(folder: Path | None = None) -> list[Chunk]:
    folder = folder or config.KNOWLEDGE_DIR
    if (folder / "manifest.json").exists():
        return load_manifest_chunks(folder)
    chunks: list[Chunk] = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        for n, (t0, text) in enumerate(_read(path)):
            title, secs = _split_sections(text)
            title = title or t0 or path.stem.replace("_", " ")
            did = _doc_id(path) + (f"-{n + 1}" if n else "")
            for i, (sec, body) in enumerate(secs):
                chunks.append(Chunk(id=f"{did}#{i + 1}", doc_id=did, title=title, section=sec,
                                    text=re.sub(r"\s+", " ", body).strip(), source=path.name))
    return chunks


# ------------------------------------------------------------------ embeddings

def _hash_embed(text: str) -> list[float]:
    toks = tokenize(text)
    feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
    v = [0.0] * config.EMBED_DIM
    for f, c in Counter(feats).items():
        h = int(hashlib.md5(f.encode()).hexdigest(), 16)
        v[h % config.EMBED_DIM] += (1 + math.log(c)) * (1 if (h >> 9) & 1 else -1)
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def embed(text: str) -> list[float]:
    mode = config.EMBEDDINGS
    try:
        if mode == "gemini" and os.getenv("GOOGLE_API_KEY"):
            from .llm import _post
            d = _post("https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent",
                      {"content": {"parts": [{"text": text[:8000]}]}}, {"x-goog-api-key": os.environ["GOOGLE_API_KEY"]})
            return _fit(d["embedding"]["values"])
        if mode == "ollama":
            from .llm import _post
            d = _post(f"{config.OLLAMA_URL}/api/embeddings", {"model": "nomic-embed-text", "prompt": text}, {})
            return _fit(d["embedding"])
    except Exception:  # noqa: BLE001  -> deterministic fallback
        pass
    return _hash_embed(text)


def _fit(v: list[float]) -> list[float]:
    v = (v + [0.0] * config.EMBED_DIM)[: config.EMBED_DIM]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


# ------------------------------------------------------------------ stores

class MemoryStore:
    kind = "in-memory"

    def __init__(self):
        self.rows: list[tuple[Chunk, list[float]]] = []

    def upsert(self, chunks, vecs):
        self.rows = list(zip(chunks, vecs))

    def search(self, qv, k):
        sc = [(sum(a * b for a, b in zip(qv, v)), c) for c, v in self.rows]
        return sorted(sc, key=lambda x: -x[0])[:k]


class PgVectorStore:
    kind = "postgres+pgvector"

    def __init__(self, url: str):
        import psycopg  # psycopg[binary]
        self.conn = psycopg.connect(url, autocommit=True)
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(f"""CREATE TABLE IF NOT EXISTS kb_chunks(
                id text PRIMARY KEY, doc_id text, title text, section text, text text, source text,
                embedding vector({config.EMBED_DIM}))""")

    @staticmethod
    def _lit(v):
        return "[" + ",".join(f"{x:.6f}" for x in v) + "]"

    def upsert(self, chunks, vecs):
        with self.conn.cursor() as cur:
            cur.execute("TRUNCATE kb_chunks")
            for c, v in zip(chunks, vecs):
                cur.execute("INSERT INTO kb_chunks VALUES (%s,%s,%s,%s,%s,%s,%s::vector)",
                            (c.id, c.doc_id, c.title, c.section, c.text, c.source, self._lit(v)))

    def search(self, qv, k):
        with self.conn.cursor() as cur:
            cur.execute("""SELECT id, doc_id, title, section, text, source, 1 - (embedding <=> %s::vector)
                           FROM kb_chunks ORDER BY embedding <=> %s::vector LIMIT %s""",
                        (self._lit(qv), self._lit(qv), k))
            return [(float(r[6]), Chunk(*r[:6])) for r in cur.fetchall()]


# ------------------------------------------------------------------ index

class Index:
    def __init__(self, folder: Path | None = None):
        self.chunks = load_chunks(folder)
        self.store = MemoryStore()
        if config.DATABASE_URL:
            try:
                self.store = PgVectorStore(config.DATABASE_URL)
            except Exception as e:  # noqa: BLE001
                print(f"  [rag] pgvector unavailable ({str(e)[:80]}); using in-memory vectors")
        self.store.upsert(self.chunks, [embed(f"{c.title} {c.section} {c.text}") for c in self.chunks])
        self._bm25_prep()
        self.flagged: set[str] = set()
        self.flagged = {x["doc"] for x in self.content_issues()}  # unreliable content is never cited

    def _bm25_prep(self):
        self.toks = [tokenize(f"{c.title} {c.section} {c.text}") for c in self.chunks]
        self.df = Counter(t for ts in self.toks for t in set(ts))
        self.avg = sum(map(len, self.toks)) / max(1, len(self.toks))

    def _bm25(self, q: list[str], i: int, k1=1.4, b=0.75) -> float:
        tf, n, N = Counter(self.toks[i]), len(self.toks[i]), len(self.toks)
        s = 0.0
        for t in set(q):
            if t in tf:
                idf = math.log(1 + (N - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * n / self.avg))
        return s

    def search(self, query: str, k: int | None = None, country: str | None = None, topics: list[str] | None = None,
               include_conflicts: bool = False) -> list[dict]:
        """Hybrid search. country: only that country's policies + global docs. topics: boost the intent's policy topics.
        Superseded (legacy) pages are excluded unless include_conflicts."""
        k = k or config.TOP_K
        vec = {c.id: s for s, c in self.store.search(embed(query), 60)}
        q = tokenize(query)
        bm = {c.id: self._bm25(q, i) for i, c in enumerate(self.chunks)}
        top_bm = max(bm.values(), default=0) or 1.0
        scored = []
        for c in self.chunks:
            m = c.meta or {}
            if (m.get("is_conflict") and not include_conflicts) or c.doc_id in self.flagged:
                continue
            if country and m.get("country") and m["country"] != country:
                continue
            s = 0.5 * max(0.0, vec.get(c.id, 0.0)) + 0.5 * (bm[c.id] / top_bm) * min(1.0, top_bm / 6)
            if topics and m.get("topic") in topics:
                s += 0.35
            if m.get("topic") == "Domain Overview":
                continue  # index pages (lists of links) never answer a question
            scored.append((round(s, 3), c))
        scored.sort(key=lambda x: -x[0])
        return [{"score": s, **asdict(c)} for s, c in scored[:k]]

    def stats(self) -> dict:
        docs = {c.doc_id: c.meta or {} for c in self.chunks}
        return {"documents": len(docs), "chunks": len(self.chunks), "store": self.store.kind, "embeddings": config.EMBEDDINGS,
                "countries": sorted({m.get("country") for m in docs.values() if m.get("country")}),
                "superseded_pages": sum(1 for m in docs.values() if m.get("is_conflict"))}

    def conflicts(self) -> list[dict]:
        """Legacy wiki pages that contradict the current policy: sentence-level differences."""
        by_doc: dict[str, list[Chunk]] = {}
        for c in self.chunks:
            by_doc.setdefault(c.doc_id, []).append(c)
        out = []
        for did, cs in by_doc.items():
            m = cs[0].meta or {}
            if not m.get("is_conflict") or m.get("conflict_of") not in by_doc:
                continue
            cur = by_doc[m["conflict_of"]]
            norm = lambda t: re.sub(r"\W+", " ", t.lower()).strip()  # noqa: E731
            cur_set = {norm(c.text) for c in cur}
            diffs = []
            for c in cs:
                if norm(c.text) in cur_set:
                    continue
                best = max(cur, key=lambda x: len(set(tokenize(x.text)) & set(tokenize(c.text))))
                diffs.append({"legacy": c.text, "current": best.text, "current_chunk": best.id})
            out.append({"legacy_doc": did, "legacy_source": cs[0].source, "legacy_date": m.get("effective_date"),
                        "current_doc": m["conflict_of"], "current_date": (cur[0].meta or {}).get("effective_date"),
                        "topic": m.get("topic"), "country": m.get("country"), "differences": diffs})
        return out

    def content_issues(self) -> list[dict]:
        """Docs whose body does not match their title (e.g. a FAQ that contains requisition steps)."""
        by_doc: dict[str, list[Chunk]] = {}
        for c in self.chunks:
            by_doc.setdefault(c.doc_id, []).append(c)
        out = []
        for did, cs in by_doc.items():
            m = cs[0].meta or {}
            if m.get("type") != "runbook":
                continue
            title_t = set(tokenize(cs[0].title)) - {"runbook", "guide", "template", "hr", "operation"}
            body = " ".join(c.text for c in cs if c.section != "Purpose")
            if title_t and not (title_t & set(tokenize(body))):
                out.append({"doc": did, "title": cs[0].title, "issue": "Body does not match title: " + body[:140] + "…"})
        return out
