"""The HR Ops Copilot pipeline: one governed path for every inquiry.

  input guardrails -> triage -> retrieve -> [transaction: extract, validate, diff]
  -> draft with citations -> output guardrails -> route -> persist + audit

Routes:
  READY           non-sensitive, grounded, cited: analyst reviews and sends in one click (self-service)
  NEEDS_APPROVAL  sensitive topic, security flag or failed quality check: specialist must approve
  TRANSACTION     changes employee/HR data: approver must approve before anything is written
  KNOWLEDGE_GAP   no grounded answer: routed to an SME and logged as a content gap
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import date

from . import answer, config, guardrails, hris, skills, store, telemetry
from .rag import Index

_INDEX: Index | None = None


def index() -> Index:
    global _INDEX
    if _INDEX is None:
        _INDEX = Index()
    return _INDEX


def reindex() -> dict:
    global _INDEX
    _INDEX = Index()
    return _INDEX.stats()


def process(inq: dict, persist: bool = True, today: date | None = None, use_adk: bool | None = None) -> dict:
    use_adk = (os.getenv("USE_ADK", "1") == "1") if use_adk is None else use_adk
    today = today or date.today()
    t0 = time.perf_counter()
    cid = "CASE-" + (inq["id"] if inq.get("id") else uuid.uuid4().hex[:8].upper())
    text = (f"{inq.get('subject', '')}. " if inq.get("subject") and not inq.get("body", "").startswith(inq.get("subject", "")[:40]) else "") \
        + inq.get("body", inq.get("text", ""))
    emp_id = inq.get("employee_id", "")
    emp = hris.employee(emp_id) if emp_id else None
    first = (emp or {}).get("first_name") or (inq.get("name") or "there").split()[0]
    tr = telemetry.Trace("hr_inquiry", {"case_id": cid, "channel": inq.get("channel", "")})
    res: dict = {"case_id": cid, "inquiry_id": inq.get("id"), "channel": inq.get("channel", "self-service"),
                 "employee_id": emp_id, "employee_name": (emp or {}).get("name", ""), "subject": inq.get("subject") or text[:70],
                 "question": text, "policy_version": config.POLICY_VERSION, "historical_tier": inq.get("tier"),
                 "employee": hris.public_profile(emp_id) if emp else None}
    try:
        with tr.step("input_guardrails") as s:
            masked, vault, in_checks = guardrails.check_input(text)
            injection = not in_checks[1].passed
            s["summary"] = f"{len(vault)} PII masked; injection={'YES' if injection else 'no'}"
        with tr.step("triage") as s:
            tri = skills.triage(masked, inq, emp)
            tri["label_tier"] = f"Tier {tri['tier']}"
            s["summary"] = f"{tri['label']} | Tier {tri['tier']} | {tri['country']} | {tri['method']}"
        with tr.step("retrieve", store=index().store.kind) as s:
            hits = index().search(masked, country=tri["country"], topics=tri["kb"])
            kb_srcs = [h for h in hits if h["score"] >= config.MIN_RETRIEVAL_SCORE]
            if tri["kb"]:  # known intent: only cite the policies that govern it (no "nearest paragraph" answers)
                kb_srcs = [h for h in kb_srcs if (h.get("meta") or {}).get("topic") in tri["kb"]]
            cov = answer.coverage(masked, kb_srcs)
            s["summary"] = f"{len(kb_srcs)} policy passages ({tri['country'] or 'all countries'}); top {hits[0]['score'] if hits else 0}; coverage {cov}"
        with tr.step("systems_of_record") as s:
            rec_srcs, facts = skills.records(tri, emp, text, emp_id) if not injection else ([], {})
            s["summary"] = f"{len(rec_srcs)} record(s): " + ", ".join(sorted({r['title'] for r in rec_srcs})) if rec_srcs else "none needed"
        srcs = rec_srcs + kb_srcs
        tx = None
        if not injection and tri["tier"] == 2 or tri.get("action") == "book_pto":
            with tr.step("prepare_action") as s:
                tx = skills.action(tri, emp, text, facts, today)
                s["summary"] = (f"{tx['type']} prepared; {sum(not c['passed'] for c in tx['validation'])} open item(s); NOT applied"
                                if tx else "no data change")
        with tr.step("draft") as s:
            topical = bool(kb_srcs) and (cov >= 0.34 or (tri["intent"] != "general_question" and cov >= 0.2) or bool(rec_srcs))
            if injection:
                txt, engine = (f"Hi {first},\n\nWe've received your message and passed it to an HR specialist, who will follow "
                               "up with you directly.\n\nBest regards,\nHR Operations"), "guardrail-template"
            elif tri.get("action") == "clarify":
                txt, engine = skills.clarify(first, tri["country"], index()), "clarifying-question"
            elif topical or rec_srcs:
                txt, engine = answer.draft(masked, first, srcs, tri["sensitive"], use_adk, tri["category"], tri.get("action"))
                if engine.startswith("offline"):
                    txt = skills.compose(masked, first, tri, srcs) or answer.NOT_FOUND
            else:
                txt, engine = answer.NOT_FOUND, "none"
            gap = txt.strip().startswith(answer.NOT_FOUND)
            if gap:
                txt = (f"Hi {first},\n\nThanks for your question. I couldn't find this in ACME's current HR policies, so I've passed it "
                       f"to the right specialist, who will reply directly.\n\nBest regards,\nHR Operations")
            s["summary"] = f"{engine}; {'no grounded answer' if gap else f'{len(txt.split())} words'}"
        with tr.step("output_guardrails") as s:
            skip = gap or injection or engine == "clarifying-question"
            out_checks, info = guardrails.check_output(txt, srcs, vault) if not skip else ([], {"cited": [], "groundedness": None})
            quality_ok = all(c.passed for c in out_checks)
            s["summary"] = "all passed" if quality_ok else "failed: " + ", ".join(c.name for c in out_checks if not c.passed)
        with tr.step("route") as s:
            reasons = []
            if injection:
                route = "NEEDS_APPROVAL"
                reasons.append("Security: possible prompt injection; no automated action taken")
            elif tri["tier"] == 3:
                route = "NEEDS_APPROVAL"
                reasons.append(f"Tier 3 sensitive: routed to {tri['team']} with a confidential brief; AI sends acknowledgement only after approval")
            elif tri["tier"] == 2:
                route = "TRANSACTION"
                reasons.append("Tier 2 maker/checker: AI prepared the work (maker); an analyst must approve (checker) before anything changes")
                if tri["sensitive"]:
                    reasons.append("Sensitive data (bank details): identity confirmation required")
            elif gap:
                route = "KNOWLEDGE_GAP"
                reasons.append("No current policy answers this: routed to an SME and logged as a content gap")
            elif not quality_ok:
                route = "NEEDS_APPROVAL"
                reasons.append("Quality check failed: " + "; ".join(c.detail for c in out_checks if not c.passed))
            else:
                route = "READY"
                reasons.append("Tier 1: grounded in current policy" + (" and your HR records" if rec_srcs else "") + ", cited: answered in real time")
            s["summary"] = route
        res.update({
            "triage": tri, "route": route, "route_reasons": reasons, "draft": txt, "engine": engine, "sources": srcs,
            "retrieval": {"coverage": cov, "top_score": hits[0]["score"] if hits else 0, "store": index().store.kind, "country": tri["country"]},
            "internal_guidance": answer.internal_guidance(kb_srcs), "groundedness": info["groundedness"],
            "cited": info["cited"], "guardrails": {"input": guardrails.as_dicts(in_checks), "output": guardrails.as_dicts(out_checks)},
            "transaction": tx, "brief": skills.brief(tri, emp, srcs, text) if tri["tier"] == 3 else None,
            "masked_question": masked, "trace": tr.steps,
            "sla": {"historical_median_min": config.ROI["resolution_min_today"].get(str(tri["tier"])), "ai_ms": None},
        })
    finally:
        tr.close()
    res["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    res["sla"]["ai_ms"] = res["total_ms"]
    if persist:
        store.save_case(res)
        store.audit(cid, "system", "INQUIRY_RECEIVED", {"inquiry": inq.get("id"), "channel": res["channel"]})
        store.audit(cid, f"ai:{res['engine']}", "TRIAGED_AND_DRAFTED",
                    {"route": res["route"], "intent": tri["intent"], "tier": tri["tier"], "cited": res["cited"],
                     "groundedness": res["groundedness"], "policy": config.POLICY_VERSION})
    return res


def decide(case_id: str, reviewer: str, decision: str, note: str, final_text: str | None) -> dict:
    case = store.get_case(case_id)
    if not case:
        return {"ok": False, "error": "case not found"}
    p = case["payload"]
    if decision not in ("SEND", "APPROVE", "REQUEST_INFO", "REJECT"):
        return {"ok": False, "error": "decision must be SEND, APPROVE, REQUEST_INFO or REJECT"}
    if decision == "SEND" and p["route"] != "READY":
        return {"ok": False, "error": "only READY drafts can be sent without approval"}
    if decision in ("APPROVE", "REJECT", "REQUEST_INFO") and not (note or "").strip():
        return {"ok": False, "error": "a rationale is required for approvals and rejections"}
    applied = None
    if decision == "APPROVE" and p.get("transaction"):
        tx = p["transaction"]
        if not tx["valid"] and "override" not in (note or "").lower():
            return {"ok": False, "error": "open items remain: use Request info, reject, or write 'override' plus a reason"}
        applied = {"type": tx["type"], "change": tx.get("diff"), "system": "HRIS (simulated write; systems of record are read-only in this prototype)"}
    status = store.decide(case_id, reviewer, decision, note, final_text or p.get("draft"))
    if status is None:
        return {"ok": False, "error": "case already closed"}
    store.audit(case_id, f"human:{reviewer}", f"{decision}", {"note": note, "edited": bool(final_text and final_text != p.get('draft')),
                                                              "applied": bool(applied)})
    return {"ok": True, "status": status, "applied_record": applied}
