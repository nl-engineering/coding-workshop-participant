"""Framework-neutral API handlers, used by both the FastAPI app and the stdlib fallback server."""
from __future__ import annotations

import json
from datetime import date

from . import config, hris, ingest_inquiries, pipeline, store, telemetry

_last_eval: dict = {}


def health():
    return {"ok": True, "provider": config.provider(), "model": config.model_name(), "policy": config.POLICY_VERSION,
            "kb": pipeline.index().stats(), "hris": hris.stats(), "telemetry": telemetry.status(), "adk": _adk_available()}


def _adk_available() -> bool:
    try:
        import google.adk  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def inquiries():
    done = {c["inquiry_id"] for c in store.list_cases() if c["inquiry_id"]}
    return [{**q, "processed": q["id"] in done} for q in ingest_inquiries.load()]


def process(body: dict):
    if body.get("inquiry_id"):
        q = next((x for x in ingest_inquiries.load() if x["id"] == body["inquiry_id"]), None)
        if not q:
            return {"error": "inquiry not found"}, 404
    else:
        if not (body.get("text") or "").strip():
            return {"error": "text is required"}, 400
        q = {"id": None, "channel": body.get("channel", "self-service"), "employee_id": body.get("employee_id", ""),
             "subject": body.get("subject", ""), "body": body["text"]}
    return pipeline.process(q), 200


def process_all(body: dict):
    out = []
    for q in ingest_inquiries.load()[: int(body.get("limit", 500))]:
        r = pipeline.process(q)
        out.append({"inquiry_id": q["id"], "case_id": r["case_id"], "route": r["route"]})
    return {"processed": len(out), "results": out}, 200


_synced = False


def _sync():
    global _synced
    if not _synced:
        _synced = True
        done = {c["inquiry_id"] for c in store.list_cases() if c["inquiry_id"]}
        for q in ingest_inquiries.load():
            if q["id"] not in done:
                pipeline.process(q)


def _ensure(cid):
    if store.get_case(cid) is None and cid.startswith("CASE-T"):
        q = next((x for x in ingest_inquiries.load() if x["id"] == cid[5:]), None)
        if q:
            pipeline.process(q)


def cases(status=None):
    if status:
        _sync()
    return store.list_cases(status)


def case(cid):
    _ensure(cid)
    c = store.get_case(cid)
    return (c, 200) if c else ({"error": "not found"}, 404)


def decision(cid, body):
    _ensure(cid)
    r = pipeline.decide(cid, body.get("reviewer") or "analyst", body.get("decision", ""), body.get("note", ""),
                        body.get("final_text"))
    return r, (200 if r.get("ok") else 400)


def feedback(cid, body):
    store.add_feedback(cid, int(body.get("rating", 0)), body.get("comment", ""))
    return {"ok": True}, 200


def kb():
    ix = pipeline.index()
    docs = {}
    for c in ix.chunks:
        m = c.meta or {}
        d = docs.setdefault(c.doc_id, {"doc_id": c.doc_id, "title": c.title, "source": c.source, "sections": [], "type": m.get("type"),
                                       "country": m.get("country"), "domain": m.get("domain"), "topic": m.get("topic"),
                                       "effective_date": m.get("effective_date"), "superseded": bool(m.get("is_conflict")),
                                       "flagged": c.doc_id in ix.flagged})
        d["sections"].append({"id": c.id, "section": c.section, "text": c.text})
    return {"stats": ix.stats(), "documents": sorted(docs.values(), key=lambda d: (d["type"] or "", d["domain"] or "", d["country"] or "")),
            "conflicts": ix.conflicts(), "content_issues": ix.content_issues(), "hris": hris.stats()}


def ticket_stats():
    p = config.DATA_DIR / "ticket_stats.json"
    return json.loads(p.read_text()) if p.exists() else {}


def metrics():
    rt = None
    if _last_eval.get("by_tier"):
        rt = _last_eval["realtime_rate"] / max(0.01, _last_eval["by_tier"][1]["n"] / _last_eval["cases"])
    return store.metrics(rt)


def search(q):
    return pipeline.index().search(q, 6)


def employee(eid):
    e = hris.public_profile(eid)
    return (e, 200) if e else ({"error": "not found"}, 404)


def run_evals(body=None):
    from evals.run_evals import run
    import os
    cap = int(os.getenv("EVAL_LIMIT_CAP", "30" if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else "100000"))
    res = run(persist=False, limit=min(int((body or {}).get("limit") or 1000), cap))
    _last_eval.clear()
    _last_eval.update(res)
    return res


def last_eval():
    if not _last_eval:
        f = config.DATA_DIR / "eval_last.json"
        if f.exists():
            _last_eval.update(json.loads(f.read_text()))
    return _last_eval


def reindex():
    return pipeline.reindex()


def init():
    store.init()
    pipeline.index()
    print(f"  knowledge base: {pipeline.index().stats()}")
    print(f"  LLM: {config.provider()} ({config.model_name()}) | telemetry: {telemetry.status()} | ADK: {_adk_available()}")


def dumps(o) -> bytes:
    return json.dumps(o, default=lambda x: x.isoformat() if isinstance(x, date) else str(x)).encode()
