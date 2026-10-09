"""Systems of record (read-only): employees, PTO balances, dependents, benefits, payroll.
Backed by data/hris.db (built by scripts/prepare_dataset.py from the workshop CSVs).
Every fact returned carries a record id so answers can cite it like a policy passage."""
from __future__ import annotations

import sqlite3
import threading
from collections import Counter
from datetime import date

from . import config

_local = threading.local()
DB = config.DATA_DIR / "hris.db"


def _c():
    if not DB.exists():
        return None
    if getattr(_local, "c", None) is None:
        _local.c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)
        _local.c.row_factory = sqlite3.Row
    return _local.c


def available() -> bool:
    return DB.exists()


def _one(q, *a):
    c = _c()
    r = c.execute(q, a).fetchone() if c else None
    return dict(r) if r else None


def _all(q, *a):
    c = _c()
    return [dict(r) for r in c.execute(q, a).fetchall()] if c else []


def employee(eid: str) -> dict | None:
    e = _one("SELECT * FROM employees WHERE employee_id=?", eid)
    if e:
        e["name"] = f"{e['first_name']} {e['last_name']}"
    return e


def public_profile(eid: str) -> dict | None:
    """Non-sensitive fields only (no salary, no email)."""
    e = employee(eid)
    return e and {k: e[k] for k in ("employee_id", "name", "country", "department", "level", "manager_id", "hire_date", "work_city", "status")}


def find_by_name(name: str) -> list[dict]:
    parts = name.split()
    if len(parts) < 2:
        return []
    rows = _all("SELECT employee_id, first_name, last_name, country, department, level, manager_id, status FROM employees "
                "WHERE lower(first_name)=lower(?) AND lower(last_name)=lower(?)", parts[0], " ".join(parts[1:]))
    for r in rows:
        r["name"] = f"{r['first_name']} {r['last_name']}"
    return rows


def pto(eid: str) -> dict | None:
    return _one("SELECT * FROM pto_balances WHERE employee_id=? ORDER BY year DESC LIMIT 1", eid)


def paystubs(eid: str, n: int = 3) -> list[dict]:
    return _all("SELECT * FROM payroll_ledger WHERE employee_id=? ORDER BY pay_date DESC LIMIT ?", eid, n)


def dependents(eid: str) -> list[dict]:
    return _all("SELECT dependent_id, name, relationship, date_of_birth, covered_by_benefits FROM dependents WHERE employee_id=?", eid)


def benefits(eid: str) -> dict | None:
    return _one("SELECT * FROM benefits_enrollment WHERE employee_id=?", eid)


def direct_reports(mid: str) -> list[dict]:
    return _all("SELECT employee_id, first_name, last_name, department, level, country, hire_date, status FROM employees WHERE manager_id=?", mid)


def org(mid: str, max_depth: int = 4) -> list[dict]:
    out, frontier = [], [mid]
    for _ in range(max_depth):
        nxt = []
        for m in frontier:
            for r in direct_reports(m):
                out.append(r)
                nxt.append(r["employee_id"])
        frontier = nxt
        if not frontier or len(out) > 5000:
            break
    return out


def org_health(mid: str, today: date | None = None) -> dict:
    today = today or date.today()
    people = org(mid)
    if not people:
        return {"headcount": 0}
    active = [p for p in people if p["status"] == "Active"]
    ten = sorted((today - date.fromisoformat(p["hire_date"])).days / 365 for p in active) if active else [0]
    return {"headcount": len(people), "active": len(active), "inactive": len(people) - len(active),
            "direct_reports": len(direct_reports(mid)), "by_level": dict(Counter(p["level"] for p in active)),
            "by_department": dict(Counter(p["department"] for p in active).most_common(8)),
            "by_country": dict(Counter(p["country"] for p in active)),
            "median_tenure_years": round(ten[len(ten) // 2], 1), "new_joiners_12m": sum(1 for t in ten if t < 1)}


def headcount_by_department(country: str | None = None, mid: str | None = None) -> dict:
    if mid:
        people = [p for p in org(mid) if p["status"] == "Active"]
        if people:
            return {"scope": f"organisation of {mid}", "rows": dict(Counter(p["department"] for p in people).most_common())}
    rows = _all("SELECT department, COUNT(*) n FROM employees WHERE status='Active' AND (? IS NULL OR country=?) GROUP BY department ORDER BY n DESC",
                country, country)
    return {"scope": f"all active employees{' in ' + country if country else ''}", "rows": {r["department"]: r["n"] for r in rows}}


def is_in_org(mid: str, eid: str) -> bool:
    """True if eid reports (directly or indirectly) to mid."""
    seen, cur = set(), employee(eid)
    while cur and cur.get("manager_id") and cur["employee_id"] not in seen:
        seen.add(cur["employee_id"])
        if cur["manager_id"] == mid:
            return True
        cur = employee(cur["manager_id"])
    return False


def stats() -> dict:
    if not available():
        return {"available": False}
    return {"available": True, **{t: _one(f"SELECT COUNT(*) n FROM {t}")["n"] for t in
                                  ("employees", "pto_balances", "dependents", "benefits_enrollment", "payroll_ledger")}}
