"""Intent skills: what the copilot does for each of the 34 ticket types.

triage()   -> intent, tier, country, sensitivity
records()  -> facts from the systems of record, as citable sources (employee's OWN data only)
action()   -> PROPOSED change / report / case, validated against policy & runbook rules (never applied here)
compose()  -> offline answer: record facts + policy sentences, each with a citation
brief()    -> confidential tier-3 brief for the specialist team
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from . import hris, intents
from .rag import tokenize

BUSINESS_DAYS = lambda a, b: sum(1 for i in range((b - a).days) if (a + timedelta(i + 1)).weekday() < 5)  # noqa: E731


def triage(text: str, inq: dict, emp: dict | None) -> dict:
    it = intents.match(text)
    country = intents.mentioned_country(text) or inq.get("country") or (emp or {}).get("country")
    if it:
        t = {"intent": it["id"], "label": it["label"], "tier": it["tier"], "domain": it["domain"], "kb": it["kb"],
             "records": it["records"], "action": it.get("action"), "team": it.get("team"), "method": "intent catalogue (2M tickets)"}
    elif re.search(intents.SENSITIVE, text.lower()):
        t = {"intent": "unclassified_sensitive", "label": "Sensitive (unclassified)", "tier": 3, "domain": "Misc", "kb": [],
             "records": [], "action": None, "team": "HR Business Partner", "method": "sensitive-topic screen"}
    else:
        t = {"intent": "general_question", "label": "General policy question", "tier": 1, "domain": "Misc", "kb": [],
             "records": [], "action": None, "team": None, "method": "open question (RAG)"}
    t["country"] = country
    t["sensitive"] = t["tier"] == 3 or bool(it and it.get("sensitive_data"))
    t["sensitive_reasons"] = ([f"Tier 3: handled by {t['team']}"] if t["tier"] == 3 else []) + (["bank details"] if it and it.get("sensitive_data") else [])
    t["category"] = t["intent"]
    return t


def _src(rid, title, section, text, source):
    return {"id": rid, "doc_id": title, "title": title, "section": section, "text": text, "score": 1.0, "source": source,
            "meta": {"type": "record"}}


def records(tri: dict, emp: dict | None, text: str, requester: str) -> tuple[list[dict], dict]:
    if not emp:
        return [], {}
    eid, src, f = emp["employee_id"], [], {}
    for r in tri["records"]:
        if r == "payroll":
            stubs = hris.paystubs(eid, 3)
            f["paystubs"] = stubs
            show = {"paystub": 1, "next_pay_date": 0, "small_pay_error": 2, "unknown_deduction": 3, "bank_update": 0}.get(tri["intent"], 3)
            if tri["intent"] in ("next_pay_date", "bank_update") and len(stubs) >= 2:
                nxt = _next_pay(f)
                src.append(_src(f"HRIS:payroll:next:{eid}", "Payroll ledger", "Pay cadence",
                                f"Your last pay date was {stubs[0]['pay_date']} and the one before {stubs[1]['pay_date']}, so your next pay date is "
                                f"expected around {nxt} ({stubs[0]['currency']}).", "payroll_ledger.csv"))
            for s in stubs[:show]:
                src.append(_src(f"HRIS:payroll:{s['ledger_id']}", "Payroll ledger", f"Pay date {s['pay_date']}",
                                f"Payslip for {s['pay_period_start']} to {s['pay_period_end']}, paid {s['pay_date']}: gross {s['gross_pay']} "
                                f"{s['currency']}, deductions {s['deductions']} {s['currency']}, net {s['net_pay']} {s['currency']}.", "payroll_ledger.csv"))
        elif r == "pto":
            p = hris.pto(eid)
            f["pto"] = p
            if p:
                src.append(_src(f"HRIS:pto:{eid}", "PTO balances", f"{p['year']}",
                                f"PTO balance for {p['year']}: {p['accrued_days']} days accrued, {p['used_days']} used, {p['balance_days']} days "
                                f"remaining (as of {p['last_updated']}).", "pto_balances.csv"))
        elif r == "benefits":
            b = hris.benefits(eid)
            f["benefits"] = b
            if b:
                src.append(_src(f"HRIS:benefits:{eid}", "Benefits enrollment", "Current enrollment",
                                f"Current benefits enrollment: {b['plan_name']} ({b['enrollment_status']}), effective {b['effective_date']}.",
                                "benefits_enrollment.csv"))
        elif r == "dependents":
            d = hris.dependents(eid)
            f["dependents"] = d
            src.append(_src(f"HRIS:dependents:{eid}", "Dependents", "On file",
                            ("Dependents on file: " + "; ".join(f"{x['name']} ({x['relationship']}, born {x['date_of_birth']}, "
                                                                 f"{'covered' if x['covered_by_benefits'] == 'True' else 'not covered'})" for x in d) + ".")
                            if d else "No dependents on file.", "dependents.csv"))
        elif r == "employee":
            f["profile"] = {k: emp[k] for k in ("level", "country", "department")}
            src.append(_src(f"HRIS:employee:{eid}", "Employee record", "Profile",
                            f"Employee level {emp['level']}, country {emp['country']}, department {emp['department']}.", "employees.csv"))
        elif r == "org":
            oh = hris.org_health(eid)
            f["org"] = oh
            if oh.get("headcount"):
                src.append(_src(f"HRIS:org:{eid}", "Org structure", "Your organisation",
                                f"Your organisation has {oh['headcount']} people ({oh['active']} active, {oh['direct_reports']} direct reports), "
                                f"median tenure {oh['median_tenure_years']} years, {oh['new_joiners_12m']} joiners in the last 12 months.", "employees.csv"))
        elif r == "named_people":
            f["people"] = {}
            for n in intents.mentioned_people(text):
                cands = hris.find_by_name(n)
                mine = [c for c in cands if c["manager_id"] == requester or hris.is_in_org(requester, c["employee_id"])]
                f["people"][n] = {"candidates": cands[:5], "in_requester_org": mine[:5]}
                pick = (mine or cands or [None])[0]
                if pick:
                    src.append(_src(f"HRIS:employee:{pick['employee_id']}", "Employee record", n,
                                    f"{n}: employee {pick['employee_id']}, level {pick['level']}, {pick['department']}, {pick['country']}, "
                                    f"status {pick['status']}, manager {pick['manager_id']}"
                                    + (f" ({len(cands)} employees share this name)" if len(cands) > 1 else "") + ".", "employees.csv"))
    return src, f


# ------------------------------------------------------------------ actions (maker side of maker/checker)

def _rule(out, name, ok, detail, cite):
    out.append({"rule": name, "passed": bool(ok), "detail": detail, "policy": cite})


def _next_pay(f) -> date | None:
    st = f.get("paystubs") or []
    if len(st) >= 2:
        d0, d1 = date.fromisoformat(st[0]["pay_date"]), date.fromisoformat(st[1]["pay_date"])
        return d0 + (d0 - d1)
    return None


def action(tri: dict, emp: dict | None, text: str, f: dict, today: date) -> dict | None:
    a = tri.get("action")
    if not a or a == "clarify" or not emp:
        return None
    v: list[dict] = []
    c = tri["country"]
    pol = lambda topic: f"{topic} ({c})"  # noqa: E731
    if a == "book_pto":
        d = re.search(r"\d{4}-\d{2}-\d{2}", text)
        day = date.fromisoformat(d.group(0)) if d else None
        bal = float((f.get("pto") or {}).get("balance_days") or 0)
        _rule(v, "Date provided and in the future", day and day >= today, str(day) if day else "no date in request", pol("PTO / Annual Leave Policy"))
        _rule(v, "Sufficient PTO balance", bal >= 1, f"{bal} days available", "PTO balances")
        _rule(v, "Manager approval", True, "request goes to manager for approval per policy", pol("PTO / Annual Leave Policy"))
        return {"type": "book_pto", "proposal": {"employee_id": emp["employee_id"], "date": str(day) if day else None, "days": 1},
                "validation": v, "diff": {"record": emp["employee_id"], "field": "pto_requests", "before": f"balance {bal} days",
                                          "after": f"request {day} (1 day) pending manager approval → balance {bal - 1:.1f} days"},
                "valid": all(x["passed"] for x in v)}
    if a == "bank_change":
        nxt = _next_pay(f)
        bd = BUSINESS_DAYS(today, nxt) if nxt else None
        _rule(v, "Secondary confirmation (email/SMS)", False, "must be completed by the employee before the change is applied", pol("Direct Deposit & Bank Changes"))
        _rule(v, "Bank details via secure form only", False, "never accepted in email/chat; link sent to employee", pol("Direct Deposit & Bank Changes"))
        eff = ("next pay cycle" if bd is not None and bd >= 5 else "the following cycle") + (f" (next pay date {nxt}, {bd} business days away)" if nxt else "")
        _rule(v, "Payroll cutoff (5 business days)", True, f"effective {eff}", pol("Direct Deposit & Bank Changes"))
        return {"type": "update_direct_deposit", "proposal": {"employee_id": emp["employee_id"], "effective": eff}, "validation": v,
                "diff": {"record": emp["employee_id"], "field": "bank_account", "before": "•••• on file", "after": "new account after verification"},
                "valid": False}
    if a in ("add_dependent", "update_dependents"):
        b, deps = f.get("benefits") or {}, f.get("dependents") or []
        name = re.search(r"(?:daughter|son|newborn|baby)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", text)
        dob = re.search(r"\d{4}-\d{2}-\d{2}", text)
        _rule(v, "Dependent name and date of birth", bool(name and dob), "provided" if name and dob else "missing: request from employee", pol("Dependents & Enrollment"))
        _rule(v, "Supporting documentation", False, "birth certificate / proof of relationship to be uploaded", pol("Dependents & Enrollment"))
        plan = b.get("plan_name", "")
        new_plan = "Employee + Family" if a == "add_dependent" and plan in ("Employee Only", "Employee + Spouse") else plan
        _rule(v, "Coverage tier", True, f"{plan} → {new_plan}" if new_plan != plan else f"{plan} already covers children", "Benefits enrollment")
        return {"type": a, "proposal": {"employee_id": emp["employee_id"], "plan_change": [plan, new_plan]}, "validation": v,
                "diff": {"record": emp["employee_id"], "field": "dependents / plan", "before": [f"{d['name']} ({d['relationship']})" for d in deps] + [f"plan: {plan}"],
                         "after": [f"{d['name']} ({d['relationship']})" for d in deps] + (["+ newborn (name/DOB pending)"] if a == "add_dependent" else ["(changes pending employee input)"]) + [f"plan: {new_plan}"]},
                "valid": all(x["passed"] for x in v)}
    if a == "change_manager":
        ppl = f.get("people", {})
        names = list(ppl)
        if len(names) < 2:
            _rule(v, "Employee and new manager named", False, "could not identify both people", "Manager Reassignment Runbook")
            return {"type": "change_manager", "proposal": {}, "validation": v, "diff": None, "valid": False}
        e_info, m_info = ppl[names[0]], ppl[names[1]]
        self_req = next((x for x in e_info["candidates"] if x["employee_id"] == emp["employee_id"]), None)
        e = self_req or (e_info["in_requester_org"] or e_info["candidates"] or [None])[0]
        m = (m_info["candidates"] or [None])[0]
        if self_req:
            _rule(v, "Requester authorised", False, "request comes from the employee: needs current manager or HRBP sign-off", "Manager Reassignment Runbook step 1")
        else:
            _rule(v, "Employee identified in requester's team", bool(e_info["in_requester_org"]),
                  f"{e['employee_id']} ({len(e_info['candidates'])} named '{names[0]}')" if e else "not found", "Manager Reassignment Runbook step 1")
        _rule(v, "New manager exists and is a people manager", m and m["level"] != "IC" and m["status"] == "Active",
              f"{m['employee_id']} {m['level']} {m['status']}" + (f" ({len(m_info['candidates'])} share the name: checker must confirm)" if len(m_info['candidates']) > 1 else "") if m else "not found",
              "Manager Reassignment Runbook step 2")
        _rule(v, "New manager is not in the employee's own reporting line", e and m and not hris.is_in_org(e["employee_id"], m["employee_id"]),
              "no circular reporting", "Manager Reassignment Runbook step 2")
        _rule(v, "Same country / legal entity", e and m and e["country"] == m["country"],
              f"{e['country'] if e else '?'} → {m['country'] if m else '?'}" + ("" if e and m and e["country"] == m["country"] else ": escalate to HR Ops leadership"),
              "Manager Reassignment Runbook escalation")
        return {"type": "change_manager", "proposal": {"employee_id": e and e["employee_id"], "new_manager_id": m and m["employee_id"]},
                "validation": v, "diff": {"record": e and e["employee_id"], "field": "manager_id", "before": e and e["manager_id"], "after": m and m["employee_id"]},
                "valid": all(x["passed"] for x in v)}
    if a == "create_requisition":
        ppl = f.get("people", {})
        tpl = next(((p["in_requester_org"] or p["candidates"] or [None])[0] for p in ppl.values()), None)
        target = intents.mentioned_country(text) or c
        _rule(v, "Template employee found", tpl, f"{tpl['employee_id']} {tpl['level']} {tpl['department']}" if tpl else "not found", "Job Requisition Template Runbook step 1")
        _rule(v, "Headcount approval exists", False, "approval reference required before creation", "Job Requisition Template Runbook step 2")
        _rule(v, "Adapted for target country terms", True, f"target country {target}", "Job Requisition Template Runbook step 3")
        _rule(v, "Finance + HRBP approval before posting", True, "routed after checker approval", "Job Requisition Template Runbook step 4")
        draft = {"title": f"{tpl['level']} - {tpl['department']}" if tpl else None, "level": tpl and tpl["level"], "department": tpl and tpl["department"],
                 "country": target, "hiring_manager": emp["employee_id"], "template_employee": tpl and tpl["employee_id"]}
        return {"type": "create_requisition", "proposal": draft, "validation": v, "diff": {"record": "new requisition", "field": "requisition", "before": None, "after": draft},
                "valid": False}
    if a == "leave_case":
        p = f.get("pto") or {}
        _rule(v, "Notice period for leave", True, "per country parental leave policy (see sources)", pol("Parental Leave Policy"))
        return {"type": "leave_case", "proposal": {"employee_id": emp["employee_id"], "pto_balance": p.get("balance_days")}, "validation": v,
                "diff": {"record": emp["employee_id"], "field": "leave case", "before": None, "after": f"parental leave case + {p.get('balance_days', '?')} PTO days available to combine"},
                "valid": True}
    if a == "payroll_investigation":
        st = f.get("paystubs") or []
        ded = [float(s["deductions"]) for s in st]
        chg = (ded[0] - ded[1]) / ded[1] * 100 if len(ded) > 1 and ded[1] else 0
        _rule(v, "Deduction change vs previous payslip", abs(chg) < 5, f"{ded[0]:.2f} vs {ded[1]:.2f} ({chg:+.1f}%)" if len(ded) > 1 else "insufficient history", "Payroll ledger")
        return {"type": "payroll_investigation", "proposal": {"employee_id": emp["employee_id"], "deductions": ded}, "validation": v,
                "diff": {"record": emp["employee_id"], "field": "investigation", "before": None, "after": f"payroll case opened; latest deductions {ded[:3]}"},
                "valid": True}
    if a in ("report_org_health", "report_headcount"):
        rep = f.get("org") if a == "report_org_health" else hris.headcount_by_department(None, emp["employee_id"])
        own = bool((f.get("org") or {}).get("headcount"))
        _rule(v, "Requester manages an organisation", own or emp["level"] != "IC", f"{(f.get('org') or {}).get('headcount', 0)} people in scope", "Access control")
        _rule(v, "Aggregate data only (no individual pay)", True, "report contains counts only", "Data minimisation")
        return {"type": a, "proposal": {"report": rep}, "validation": v, "diff": {"record": "report", "field": "report", "before": None, "after": rep},
                "valid": all(x["passed"] for x in v)}
    if a == "bulk_change":
        _rule(v, "Employee list (CSV) attached", False, "request the list of employee IDs and effective date", "Bulk Data Change Runbook")
        _rule(v, "Dry-run validation before apply", True, "every row validated before any change", "Bulk Data Change Runbook")
        return {"type": "bulk_change", "proposal": {"target_country": intents.mentioned_country(text)}, "validation": v, "diff": None, "valid": False}
    return None


# ------------------------------------------------------------------ offline composer

def compose(question: str, first: str, tri: dict, sources: list[dict]) -> str:
    q = set(tokenize(question))
    lines = []
    for i, s in enumerate(sources, 1):
        if (s.get("meta") or {}).get("type") == "record" and tri["tier"] != 3:  # tier 3: records go to the brief, not the reply
            lines.append(f"{s['text'].rstrip('.')} [{i}].")
    kb = [(i, s) for i, s in enumerate(sources, 1) if (s.get("meta") or {}).get("type") != "record"]
    top = kb[0][1]["score"] if kb else 0
    cand = []
    for i, s in kb:
        if s["score"] < 0.55 * top:
            continue
        sc = len(q & set(tokenize(s["text"]))) + (0.6 if re.search(r"\d", s["text"]) else 0) + s["score"]
        cand.append((sc, i, s["text"].strip()))
    for _, i, t in sorted(sorted(cand, key=lambda x: -x[0])[:(1 if tri["tier"] == 3 else 3)], key=lambda x: x[1]):
        lines.append(f"{t.rstrip('.')} [{i}].")
    if not lines and tri["tier"] != 3:
        return ""
    opener = {1: "Here's what I found for you.", 2: "Thanks. I've prepared this for an HR analyst to confirm.",
              3: "Thank you for reaching out. A specialist will contact you directly and confidentially."}[tri["tier"]]
    return f"Hi {first},\n\n{opener} " + " ".join(lines) + "\n\nBest regards,\nHR Operations"


def clarify(first: str, country: str | None, index) -> str:
    topics = sorted({(c.meta or {}).get("topic") for c in index.chunks if (c.meta or {}).get("country") == country and (c.meta or {}).get("type") == "policy_pdf"})
    name = intents.COUNTRY_NAME.get(country or "", country or "your country")
    return (f"Hi {first},\n\nHappy to help with {name} policy. Which topic is it about? I can answer straight away on: "
            + ", ".join(t for t in topics if t) + ".\n\nBest regards,\nHR Operations")


def brief(tri: dict, emp: dict | None, sources: list[dict], text: str) -> dict:
    return {"team": tri.get("team"), "summary": f"{tri['label']} from {emp['name'] if emp else 'unknown'} ({(emp or {}).get('level', '?')}, {tri['country']}).",
            "relevant_policies": sorted({s["title"] for s in sources if (s.get("meta") or {}).get("type") != "record"}),
            "records_attached": [s["title"] for s in sources if (s.get("meta") or {}).get("type") == "record"],
            "sla": "Acknowledge within 4 business hours; resolve within 3 business days (current SLA)",
            "handling": "Confidential: visible to the specialist team only; no automated reply beyond acknowledgement."}
