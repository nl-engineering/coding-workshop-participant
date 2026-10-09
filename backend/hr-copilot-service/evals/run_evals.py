"""Evaluation on REAL historical tickets (data/eval_tickets.jsonl: 1,000 random tickets with the tier
HR Ops assigned). Logged to MLflow when MLFLOW_TRACKING_URI is set.

Metrics
  tier_accuracy        AI tier == historical tier
  tier3_recall         every sensitive (tier-3) ticket went to a specialist  (release gate: 100%)
  unsafe_auto          tier-2/3 tickets answered without a human            (release gate: 0)
  realtime_rate        share answered in real time (READY)
  grounded_t1          share of tier-1 tickets with a cited, grounded answer
  knowledge_gap_rate   share with no current policy -> content backlog
  avg_groundedness, citation validity, latency p50/p95

    python -m evals.run_evals            (add --limit 200 for a quick run)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, pipeline  # noqa: E402

TICKETS = config.DATA_DIR / "eval_tickets.jsonl"
ROUTE_TIER = {"READY": 1, "KNOWLEDGE_GAP": 1, "TRANSACTION": 2, "NEEDS_APPROVAL": 3}


def run(persist: bool = False, limit: int | None = None) -> dict:
    tickets = [json.loads(l) for l in TICKETS.read_text().splitlines() if l.strip()][:limit]
    rows = []
    for t in tickets:
        inq = {"id": t["ticket_id"], "channel": t["channel"], "employee_id": t["employee_id"], "country": t["country"],
               "subject": t["subject"], "body": t["body_text"], "tier": t["tier"]}
        r = pipeline.process(inq, persist=persist, today=date(2026, 9, 10), use_adk=False)
        out = r["guardrails"]["output"]
        rows.append({"id": t["ticket_id"], "subject": t["subject"][:90], "tier": t["tier"], "domain": t["domain"], "country": t["country"],
                     "route": r["route"], "ai_tier": r["triage"]["tier"], "intent": r["triage"]["intent"],
                     "tier_ok": r["triage"]["tier"] == t["tier"],
                     "unsafe": t["tier"] >= 2 and r["route"] == "READY",
                     "grounded": r["route"] == "READY" and all(c["passed"] for c in out),
                     "citations_valid": all(c["passed"] for c in out if c["name"] == "Citations valid") if out else None,
                     "groundedness": r["groundedness"], "ms": r["total_ms"], "historical_min": t["resolution_minutes"]})
    n = len(rows)
    t3 = [x for x in rows if x["tier"] == 3]
    t1 = [x for x in rows if x["tier"] == 1]
    g = [x["groundedness"] for x in rows if x["groundedness"] is not None]
    ms = sorted(x["ms"] for x in rows)
    by_tier = {k: {"n": sum(1 for x in rows if x["tier"] == k), "accuracy": round(sum(x["tier_ok"] for x in rows if x["tier"] == k) /
                                                                               max(1, sum(1 for x in rows if x["tier"] == k)), 3)} for k in (1, 2, 3)}
    res = {
        "cases": n, "model": config.model_name(), "source": "real historical tickets (random sample)",
        "tier_accuracy": round(sum(x["tier_ok"] for x in rows) / n, 3), "by_tier": by_tier,
        "tier3_recall": round(sum(x["ai_tier"] == 3 for x in t3) / len(t3), 3) if t3 else 1.0,
        "unsafe_auto": sum(x["unsafe"] for x in rows),
        "realtime_rate": round(sum(x["route"] == "READY" for x in rows) / n, 3),
        "grounded_t1": round(sum(x["grounded"] for x in t1) / len(t1), 3) if t1 else None,
        "knowledge_gap_rate": round(sum(x["route"] == "KNOWLEDGE_GAP" for x in rows) / n, 3),
        "citations_valid": round(sum(1 for x in rows if x["citations_valid"]) / max(1, sum(1 for x in rows if x["citations_valid"] is not None)), 3),
        "avg_groundedness": round(sum(g) / len(g), 3) if g else None,
        "latency_ms_p50": ms[n // 2], "latency_ms_p95": ms[int(n * .95)],
        "routes": dict(Counter(x["route"] for x in rows)),
        "rows": rows[:200],
    }
    try:
        import os
        if os.getenv("MLFLOW_TRACKING_URI"):
            import mlflow
            mlflow.set_experiment(os.getenv("MLFLOW_EXPERIMENT", "hr-ops-copilot"))
            with mlflow.start_run(run_name=f"eval-{config.model_name()}"):
                mlflow.log_params({"model": config.model_name(), "policy": config.POLICY_VERSION, "cases": n})
                mlflow.log_metrics({k: v for k, v in res.items() if isinstance(v, (int, float)) and k != "cases"})
                mlflow.log_dict({k: v for k, v in res.items() if k != "rows"}, "eval_summary.json")
            res["mlflow"] = "logged"
    except Exception as e:  # noqa: BLE001
        res["mlflow"] = f"not logged: {str(e)[:80]}"
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    r = run(limit=ap.parse_args().limit)
    for k, v in r.items():
        if k != "rows":
            print(f"  {k:20} {v}")
    sys.exit(1 if r["unsafe_auto"] or r["tier3_recall"] < 1 else 0)
