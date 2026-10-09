"""SQLite persistence (Postgres in production): cases, approvals, hash-chained audit,
knowledge gaps and analyst feedback."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()


@contextmanager
def conn():
    c = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()


def init():
    with _lock, conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, inquiry_id TEXT, created_at TEXT, channel TEXT,
          employee_id TEXT, subject TEXT, category TEXT, sensitive INT, route TEXT, status TEXT, payload TEXT,
          ms REAL, reviewer TEXT, decision TEXT, note TEXT, final_text TEXT, decided_at TEXT, edited INT DEFAULT 0);
        CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, case_id TEXT, actor TEXT,
          action TEXT, detail TEXT, prev TEXT, hash TEXT);
        CREATE TABLE IF NOT EXISTS gaps(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, case_id TEXT, question TEXT, category TEXT);
        CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, case_id TEXT, rating INT, comment TEXT);
        """)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _h(*parts):
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def audit(case_id, actor, action, detail):
    d = detail if isinstance(detail, str) else json.dumps(detail, sort_keys=True, default=str)
    with _lock, conn() as c:
        last = c.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev, ts = (last["hash"] if last else "GENESIS"), now()
        c.execute("INSERT INTO audit(ts,case_id,actor,action,detail,prev,hash) VALUES(?,?,?,?,?,?,?)",
                  (ts, case_id, actor, action, d, prev, _h(prev, ts, case_id, actor, action, d)))


def verify_chain():
    with conn() as c:
        rows = c.execute("SELECT * FROM audit ORDER BY seq").fetchall()
    prev = "GENESIS"
    for r in rows:
        if r["prev"] != prev or r["hash"] != _h(prev, r["ts"], r["case_id"], r["actor"], r["action"], r["detail"]):
            return {"valid": False, "entries": len(rows), "broken_at": r["seq"]}
        prev = r["hash"]
    return {"valid": True, "entries": len(rows), "head": prev[:16]}


def save_case(res: dict):
    status = {"READY": "DRAFT_READY", "KNOWLEDGE_GAP": "NEEDS_SME"}.get(res["route"], "PENDING_APPROVAL")
    with _lock, conn() as c:
        c.execute("""INSERT OR REPLACE INTO cases(id,inquiry_id,created_at,channel,employee_id,subject,category,sensitive,
                     route,status,payload,ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (res["case_id"], res.get("inquiry_id"), now(), res.get("channel"), res.get("employee_id"),
                   res.get("subject"), res["triage"]["category"], int(res["triage"]["sensitive"]), res["route"], status,
                   json.dumps(res, default=str), res["total_ms"]))
        if res["route"] == "KNOWLEDGE_GAP":
            c.execute("INSERT INTO gaps(ts,case_id,question,category) VALUES(?,?,?,?)",
                      (now(), res["case_id"], res.get("question", "")[:300], res["triage"]["category"]))


def decide(case_id, reviewer, decision, note, final_text):
    with _lock, conn() as c:
        row = c.execute("SELECT payload,status FROM cases WHERE id=?", (case_id,)).fetchone()
        if not row or row["status"] in ("SENT", "APPLIED", "REJECTED", "AWAITING_EMPLOYEE"):
            return None
        draft = json.loads(row["payload"]).get("draft", "")
        status = {"APPROVE": "APPLIED" if json.loads(row["payload"]).get("transaction") else "SENT",
                  "REJECT": "REJECTED", "SEND": "SENT", "REQUEST_INFO": "AWAITING_EMPLOYEE"}.get(decision, "PENDING_APPROVAL")
        c.execute("UPDATE cases SET reviewer=?,decision=?,note=?,final_text=?,decided_at=?,status=?,edited=? WHERE id=?",
                  (reviewer, decision, note, final_text, now(), status, int(bool(final_text) and final_text.strip() != draft.strip()),
                   case_id))
        return status


def list_cases(status=None):
    q, a = "SELECT id,inquiry_id,created_at,channel,employee_id,subject,category,sensitive,route,status,ms,reviewer,decision,edited FROM cases", []
    if status:
        q += " WHERE status IN (%s)" % ",".join("?" * len(status.split(",")))
        a = status.split(",")
    with conn() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY created_at DESC, rowid DESC", a)]


def get_case(case_id):
    with conn() as c:
        r = c.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["payload"] = json.loads(d["payload"])
    return d


def audit_log(limit=300):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY seq DESC LIMIT ?", (limit,))]


def gaps():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM gaps ORDER BY id DESC")]


def add_feedback(case_id, rating, comment):
    with _lock, conn() as c:
        c.execute("INSERT INTO feedback(ts,case_id,rating,comment) VALUES(?,?,?,?)", (now(), case_id, rating, comment))


def business_case(realtime_share_t1: float = 0.75) -> dict:
    """Annual effort today vs with the copilot. Volumes/mix measured; effort minutes are assumptions (see config.ROI)."""
    R = config.ROI
    n, mix, e0, e1 = R["tickets_per_year"], R["tier_mix"], R["effort_min_today"], R["effort_min_with_ai"]
    today = {t: n * mix[t] * e0[t] / 60 for t in mix}
    ai = {"1": n * mix["1"] * (realtime_share_t1 * e1["1"] + (1 - realtime_share_t1) * e0["1"]) / 60,
          "2": n * mix["2"] * e1["2"] / 60, "3": n * mix["3"] * e1["3"] / 60}
    h0, h1 = sum(today.values()), sum(ai.values())
    gain = 1 - h1 / h0
    return {"tickets_per_year": n, "realtime_share_t1": round(realtime_share_t1, 3),
            "hours_today": round(h0), "hours_with_ai": round(h1), "efficiency_gain_pct": round(gain * 100),
            "fte_today": round(h0 / R["productive_hours_per_fte"], 1), "fte_with_ai": round(h1 / R["productive_hours_per_fte"], 1),
            "fte_capacity_freed": round((h0 - h1) / R["productive_hours_per_fte"], 1), "capacity_freed_pct": round(gain * 100),
            "cost_saved_year": round((h0 - h1) * R["loaded_cost_per_hour"]),
            "realtime_tickets_year": round(n * mix["1"] * realtime_share_t1),
            "by_tier": {t: {"hours_today": round(today[t]), "hours_ai": round(ai[t])} for t in mix}, "assumptions": R}


def metrics(realtime_share_t1: float | None = None):
    rows = list_cases()
    n = len(rows) or 1
    cnt = lambda k, v: sum(1 for r in rows if r[k] == v)  # noqa: E731
    by_route = {k: cnt("route", k) for k in ("READY", "NEEDS_APPROVAL", "TRANSACTION", "KNOWLEDGE_GAP")}
    t1 = [r for r in rows if r["route"] in ("READY", "KNOWLEDGE_GAP")]
    rt = realtime_share_t1 if realtime_share_t1 is not None else (by_route["READY"] / len(t1) if t1 else 0.75)
    with conn() as c:
        fb = c.execute("SELECT AVG(rating) a, COUNT(*) n FROM feedback").fetchone()
    decided = [r for r in rows if r["decision"]]
    return {
        "cases": len(rows), "by_route": by_route,
        "by_category": {k: sum(1 for r in rows if r["category"] == k) for k in sorted({r["category"] for r in rows})},
        "pending": sum(1 for r in rows if r["status"] in ("PENDING_APPROVAL", "DRAFT_READY", "NEEDS_SME")),
        "avg_ms": round(sum(r["ms"] or 0 for r in rows) / n, 1),
        "decided": len(decided), "rejected": sum(1 for r in decided if r["decision"] == "REJECT"),
        "edited": sum(1 for r in decided if r["edited"]),
        "drafts_sent_unedited": sum(1 for r in decided if r["decision"] in ("SEND", "APPROVE") and not r["edited"]),
        "knowledge_gaps": len(gaps()), "feedback_avg": round(fb["a"], 2) if fb["a"] else None, "feedback_n": fb["n"],
        "business_case": business_case(min(1.0, rt)),
    }
