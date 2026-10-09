"""Google ADK agent: the HR Ops Copilot as an LLM agent with tools.

Run standalone with the ADK dev UI (from the backend/ folder):
    adk web            -> pick "hr_agent"
The web app uses the same agent through hr_agent/runner.py.

Design: the agent may SEARCH and PROPOSE, never WRITE. Tools are read-only except
propose_hr_change, which only records a proposal for human approval.
"""
from __future__ import annotations

import contextvars
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.adk.agents import Agent  # noqa: E402

from app import answer, config, transactions  # noqa: E402

# Passages the agent has seen in this run; citations [n] index into this list.
SOURCES: contextvars.ContextVar[list] = contextvars.ContextVar("SOURCES")
_FALLBACK: list = []
PROPOSALS: list = []


def _sources() -> list:
    try:
        return SOURCES.get()
    except LookupError:
        return _FALLBACK


def search_hr_policies(query: str) -> dict:
    """Search ACME HR policies and runbooks. Returns numbered passages; cite them as [n] in the reply.

    Args:
        query: what to look for, e.g. "dependent add deadline after birth".
    """
    from app.pipeline import index
    src = _sources()
    known = {s["id"]: i for i, s in enumerate(src, 1)}
    out = []
    for h in index().search(query):
        if h["score"] < config.MIN_RETRIEVAL_SCORE:
            continue
        if h["id"] not in known:
            src.append(h)
            known[h["id"]] = len(src)
        out.append({"n": known[h["id"]], "title": h["title"], "section": h["section"], "text": h["text"]})
    return {"passages": out} if out else {"passages": [], "note": "No relevant policy found. Reply INSUFFICIENT_EVIDENCE."}


def lookup_employee(employee_id: str) -> dict:
    """Look up non-sensitive HR record fields (name, title, level, manager, location, status) for an employee ID like E1001.

    Args:
        employee_id: ACME employee ID.
    """
    e = transactions.hris().get(employee_id)
    if not e:
        return {"found": False}
    return {"found": True, **{k: e[k] for k in ("name", "title", "level", "manager_id", "location", "status")}}


def propose_hr_change(change_type: str, employee_id: str, details: str) -> dict:
    """Record a PROPOSED change to HR data for human approval. This never changes any record.

    Args:
        change_type: one of add_dependent, change_manager, create_requisition, update_direct_deposit.
        employee_id: the employee whose record would change.
        details: the requested change in plain words.
    """
    PROPOSALS.append({"type": change_type, "employee_id": employee_id, "details": details})
    return {"status": "PENDING_HUMAN_APPROVAL",
            "message": "Proposal recorded. Tell the employee it is pending approval; do NOT say it is done."}


def _model():
    p = config.provider()
    if p == "gemini":
        return config.GEMINI_MODEL
    from google.adk.models.lite_llm import LiteLlm  # requires `litellm`
    if p == "claude":
        return LiteLlm(model=f"anthropic/{config.ANTHROPIC_MODEL}")
    if p == "ollama":
        return LiteLlm(model=f"ollama_chat/{config.OLLAMA_MODEL}")
    return config.GEMINI_MODEL


root_agent = Agent(
    name="hr_ops_copilot",
    model=_model(),
    description="Drafts cited answers to HR inquiries for analyst review; proposes (never applies) HR data changes.",
    instruction=answer.SYSTEM + """
Tools:
- Passages already provided in the message are numbered; call search_hr_policies only if you need more.
  Its results keep their numbers; cite those numbers.
- Use lookup_employee only if the request needs record context.
- If the employee asks to change HR data, call propose_hr_change and say the request is pending approval.
Return ONLY the reply text to the employee.""",
    tools=[search_hr_policies, lookup_employee, propose_hr_change],
)
