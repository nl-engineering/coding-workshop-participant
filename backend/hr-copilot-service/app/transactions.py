"""HR data transactions: extract -> validate against runbook rules -> PROPOSE.
Nothing is written to the HR system until a human approves (store.approve -> apply()).
Each validation rule cites the runbook / policy passage it comes from."""
from __future__ import annotations

import copy
import json
import re
import threading
from datetime import date, datetime

from . import config, llm

_lock = threading.Lock()
_HRIS: dict | None = None
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}


def hris() -> dict:
    global _HRIS
    if _HRIS is None:
        _HRIS = json.loads(config.HRIS_PATH.read_text()) if config.HRIS_PATH.exists() else {}
    return _HRIS


def reset_hris():
    global _HRIS
    _HRIS = None


def _date(text: str) -> str | None:
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1)
    m = re.search(r"(?i)\b(" + "|".join(MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})", text)
    if m:
        return f"{m.group(3)}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return None


def _find_emp(token: str) -> str | None:
    if re.fullmatch(r"E\d{4}", token or ""):
        return token
    for eid, e in hris().items():
        if token and e["name"].lower() == token.lower():
            return eid
    return None


# ------------------------------------------------------------------ extraction

def extract(tx_type: str, text: str, sender_id: str, masked: str | None = None) -> dict:
    """Rules see the raw text (to keep e.g. only the last 4 digits); the LLM only ever sees masked text."""
    p = _rules_extract(tx_type, text, sender_id)
    text = masked or text
    try:
        j = llm.chat_json(
            "Extract the requested HR data change as JSON. Use only facts in the text. Dates YYYY-MM-DD. "
            "Schemas: add_dependent {employee_id, dependent_name, relationship (child|spouse|domestic_partner), "
            "event_date}; change_manager {employee_id, new_manager_id, effective_date}; create_requisition "
            "{job_title, level, location, hiring_manager_id, budget_code, req_type (backfill|new)}; "
            "update_direct_deposit {employee_id, account_last4, effective}. Use null for unknown fields.",
            f"tx_type={tx_type}; sender_employee_id={sender_id}\n<request>{text}</request>")
        for k, v in j.items():
            if v not in (None, "") and not p.get(k):
                p[k] = v
    except Exception:  # noqa: BLE001
        pass
    return p


def _rules_extract(t: str, text: str, sender: str) -> dict:
    ids = re.findall(r"\bE\d{4}\b", text)
    if t == "add_dependent":
        rel = "child" if re.search(r"(?i)daughter|son|child|baby|newborn", text) else \
              "spouse" if re.search(r"(?i)husband|wife|spouse|married", text) else "domestic_partner"
        name = None
        for pat in (r"(?:daughter|son|child|baby|husband|wife|spouse|partner)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
                    r"(?:married|named)\s+(?:on [\d-]+ )?(?:to\s+)?([A-Z][a-z]+\s[A-Z][a-z]+)"):
            m = re.search(pat, text)
            if m:
                name = m.group(1)
                break
        return {"employee_id": sender, "dependent_name": name, "relationship": rel, "event_date": _date(text)}
    if t == "change_manager":
        emp = ids[0] if ids else sender
        return {"employee_id": emp, "new_manager_id": ids[1] if len(ids) > 1 else None, "effective_date": _date(text)}
    if t == "create_requisition":
        g = lambda p: (re.search(p, text, re.I) or [None, None])[1]  # noqa: E731
        return {"job_title": g(r"requisition for (?:a |an )?([A-Z][\w ]+?),"), "level": g(r"\b(L\d|M\d)\b"),
                "location": g(r"location\s+([A-Z][a-zA-Z ]+?)[,.]"), "hiring_manager_id": g(r"hiring manager\s+(E\d{4})"),
                "budget_code": g(r"\b(HC-\d{4}-\d{4})\b"),
                "req_type": "backfill" if re.search(r"(?i)backfill", text) else "new"}
    if t == "update_direct_deposit":
        acct = re.search(r"\[BANK_ACCOUNT_\d+\]|\b\d{6,17}\b", text)
        return {"employee_id": sender, "account_last4": (acct.group(0)[-4:] if acct and acct.group(0).isdigit() else "masked"),
                "effective": "next pay cycle"}
    return {}


# ------------------------------------------------------------------ validation (policy-as-code)

def validate(t: str, p: dict, today: date | None = None) -> list[dict]:
    today = today or date.today()
    H, out = hris(), []

    def rule(name, ok, detail, cite):
        out.append({"rule": name, "passed": bool(ok), "detail": detail, "policy": cite})

    if t == "add_dependent":
        e = H.get(p.get("employee_id") or "")
        rule("Employee exists & active", e and e["status"] == "active", e["name"] if e else "unknown employee", "KB-04")
        rule("Dependent name provided", p.get("dependent_name"), p.get("dependent_name") or "missing", "KB-04")
        ev = p.get("event_date")
        if ev:
            days = (today - date.fromisoformat(ev)).days
            rule("Within 31 days of life event", 0 <= days <= 31, f"event {ev}, {days} days ago (limit 31)", "KB-04 Adding a dependent")
        else:
            rule("Within 31 days of life event", False, "event date missing", "KB-04 Adding a dependent")
        rule("Documentation due", True, "birth certificate / marriage certificate required within 60 days", "KB-04 Required documentation")
    elif t == "change_manager":
        e, m = H.get(p.get("employee_id") or ""), H.get(p.get("new_manager_id") or "")
        rule("Employee exists & active", e and e["status"] == "active", e["name"] if e else "unknown employee", "KB-06")
        rule("New manager active at M1+", m and m["status"] == "active" and m["level"].startswith("M"),
             f"{m['name']} ({m['level']})" if m else "unknown manager", "KB-06 Validation rules")
        ed = p.get("effective_date")
        rule("Effective date is 1st or 16th", ed and ed[-2:] in ("01", "16"), ed or "missing", "KB-06 Required information")
    elif t == "create_requisition":
        for f in ("job_title", "level", "location", "hiring_manager_id", "budget_code"):
            rule(f"{f.replace('_', ' ').capitalize()} provided", p.get(f), p.get(f) or "missing", "KB-07 Required information")
        rule("Budget code format HC-YYYY-NNNN", re.fullmatch(r"HC-\d{4}-\d{4}", p.get("budget_code") or ""),
             p.get("budget_code") or "missing", "KB-07 Required information")
        lvl = p.get("level") or ""
        if re.match(r"L([5-9])", lvl):
            rule("VP approval required (L5+)", True, f"{lvl}: route to VP after HR Ops approval", "KB-07 Approvals")
    elif t == "update_direct_deposit":
        rule("Identity verified by phone", False, "required before any bank change; email is not accepted", "KB-05 Direct deposit changes")
    return out


def diff(t: str, p: dict) -> dict:
    H = hris()
    e = H.get(p.get("employee_id") or "", {})
    if t == "add_dependent":
        new = {"name": p.get("dependent_name"), "relationship": p.get("relationship"), "dob" if p.get("relationship") == "child" else "event_date": p.get("event_date")}
        return {"record": p.get("employee_id"), "field": "dependents", "before": e.get("dependents", []),
                "after": e.get("dependents", []) + [new]}
    if t == "change_manager":
        old, new = e.get("manager_id"), p.get("new_manager_id")
        nm = lambda i: f"{H.get(i, {}).get('name', '?')} ({i})" if i else "—"  # noqa: E731
        return {"record": p.get("employee_id"), "field": "manager_id", "before": nm(old), "after": nm(new),
                "effective": p.get("effective_date")}
    if t == "create_requisition":
        return {"record": "new requisition", "field": "requisition", "before": None, "after": p}
    if t == "update_direct_deposit":
        return {"record": p.get("employee_id"), "field": "direct_deposit", "before": "•••• (on file)",
                "after": f"•••• {p.get('account_last4')}"}
    return {}


def apply(t: str, p: dict) -> dict:
    """Called ONLY from an approved case. Writes to the (mock) HRIS."""
    with _lock:
        H = hris()
        if t == "add_dependent":
            H[p["employee_id"]].setdefault("dependents", []).append(
                {"name": p.get("dependent_name"), "relationship": p.get("relationship"), "dob": p.get("event_date")})
        elif t == "change_manager":
            H[p["employee_id"]]["manager_id"] = p["new_manager_id"]
        elif t == "create_requisition":
            H.setdefault("_requisitions", []).append({**p, "id": f"REQ-{datetime.now():%y%m%d%H%M%S}", "status": "pending VP/Finance"})
        elif t == "update_direct_deposit":
            raise ValueError("bank changes are completed by Payroll after phone verification")
        return copy.deepcopy(H.get(p.get("employee_id"), {}))
