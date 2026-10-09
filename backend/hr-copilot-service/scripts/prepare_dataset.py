"""Prepare the workshop dataset for the copilot (run once, ~1 minute):

    python scripts/prepare_dataset.py /path/to/ai-fde-sample-employee-inquiries-unzipped

Produces in data/:
  kb/<doc_id>.md + kb/manifest.json   policy PDFs / wiki / runbooks as text, with manifest metadata
  hris.db                             SQLite copy of the systems of record (employees, PTO, dependents, benefits, payroll)
  inquiries.jsonl                     demo inbox: real tickets covering every question type
  eval_tickets.jsonl                  1,000 random tier-labelled tickets for evaluation
  ticket_stats.json                   baseline volumes, tier mix and resolution times (full 2M scan)
"""
from __future__ import annotations

import csv
import json
import random
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data"


def pdf_text(p: Path) -> str:
    try:
        from pypdf import PdfReader
        return "\n\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
    except Exception:  # noqa: BLE001
        return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout


def build_kb(kb: Path):
    out = OUT / "kb"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    man = json.loads((kb / "manifest.json").read_text())
    seen = set()
    for d in man:
        src = kb / d["path"]
        seen.add(d["path"])
        text = pdf_text(src) if src.suffix == ".pdf" else src.read_text(errors="ignore")
        (out / f"{d['doc_id']}.md").write_text(text.strip() + "\n")
        d["file"] = f"{d['doc_id']}.md"
    for p in sorted(kb.rglob("*")):  # files not in the manifest (e.g. runbooks) still get indexed
        rel = str(p.relative_to(kb))
        if p.is_file() and p.suffix in (".md", ".pdf") and rel not in seen:
            did = ("runbook-" if "runbook" in rel else "doc-") + p.stem
            text = pdf_text(p) if p.suffix == ".pdf" else p.read_text(errors="ignore")
            (out / f"{did}.md").write_text(text.strip() + "\n")
            dom = re.search(r"Domain:\**\s*([^\n*]+)", text)
            man.append({"doc_id": did, "type": "runbook" if "runbook" in rel else "doc", "domain": dom.group(1).strip() if dom else "Misc",
                        "topic": p.stem.replace("-", " ").title(), "country": None, "path": rel, "effective_date": None,
                        "is_conflict": False, "conflict_of": None, "file": f"{did}.md"})
    (out / "manifest.json").write_text(json.dumps(man, indent=1))
    print(f"  kb: {len(man)} documents")


def build_hris(sor: Path):
    db = OUT / "hris.db"
    db.unlink(missing_ok=True)
    c = sqlite3.connect(db)
    for name in ("employees", "pto_balances", "dependents", "benefits_enrollment", "payroll_ledger"):
        with open(sor / f"{name}.csv", newline="") as f:
            r = csv.reader(f)
            cols = next(r)
            c.execute(f"CREATE TABLE {name} ({', '.join(cols)})")
            c.executemany(f"INSERT INTO {name} VALUES ({','.join('?' * len(cols))})", r)
    for idx in ("employees(employee_id)", "employees(manager_id)", "employees(last_name, first_name)", "pto_balances(employee_id)",
                "dependents(employee_id)", "benefits_enrollment(employee_id)", "payroll_ledger(employee_id, pay_date)"):
        c.execute(f"CREATE INDEX IF NOT EXISTS ix_{re.sub(r'[^a-z]', '_', idx)} ON {idx}")
    c.commit()
    print("  hris.db:", {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
                         ("employees", "pto_balances", "dependents", "benefits_enrollment", "payroll_ledger")})
    c.close()


def scan_tickets(path: Path):
    sys.path.insert(0, str(ROOT / "backend"))
    from app.intents import match  # the same catalogue the app uses
    random.seed(42)
    tier, chan, dom, cty, status, yr = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    mins = defaultdict(list)
    by_intent: dict[str, list] = defaultdict(list)
    sample = []
    n = 0
    with open(path) as f:
        for line in f:
            t = json.loads(line)
            n += 1
            tier[t["tier"]] += 1; chan[t["channel"]] += 1; dom[t["domain"]] += 1; cty[t["country"]] += 1
            status[t["status"]] += 1; yr[t["created_at"][:4]] += 1
            if t["resolution_minutes"] is not None and len(mins[t["tier"]]) < 300000:
                mins[t["tier"]].append(t["resolution_minutes"])
            if random.random() < 0.0006:
                sample.append(t)
            it = match(t["subject"] + " " + t["body_text"])
            key = it["id"] if it else "unmatched"
            if len(by_intent[key]) < 3 and t["created_at"] >= "2026":
                by_intent[key].append(t)
    stats = {"tickets": n, "years": dict(sorted(yr.items())), "tier": {str(k): v for k, v in sorted(tier.items())},
             "channel": dict(chan), "domain": dict(dom.most_common()), "country": dict(cty.most_common()), "status": dict(status),
             "resolution_minutes": {str(k): {"median": statistics.median(v), "p90": sorted(v)[int(.9 * len(v))]} for k, v in sorted(mins.items())}}
    (OUT / "ticket_stats.json").write_text(json.dumps(stats, indent=1))
    demo = []
    for k, v in sorted(by_intent.items()):
        if k != "unmatched":
            demo.append(v[0])
    demo.sort(key=lambda t: (t["tier"], t["domain"]))
    with open(OUT / "inquiries.jsonl", "w") as f:
        for t in demo:
            f.write(json.dumps({"id": t["ticket_id"], "channel": t["channel"], "employee_id": t["employee_id"], "country": t["country"],
                                "subject": t["subject"], "body": t["body_text"], "received_at": t["created_at"], "tier": t["tier"],
                                "domain": t["domain"]}) + "\n")
    with open(OUT / "eval_tickets.jsonl", "w") as f:
        for t in sample[:1000]:
            f.write(json.dumps(t) + "\n")
    print(f"  tickets: {n:,} scanned · demo inbox {len(demo)} · eval {min(1000, len(sample))} · unmatched seen: {'unmatched' in by_intent}")


if __name__ == "__main__":
    base = Path(sys.argv[1])
    only = sys.argv[2] if len(sys.argv) > 2 else "all"     # all | hris
    if len(sys.argv) > 3:
        OUT = Path(sys.argv[3])
    OUT.mkdir(parents=True, exist_ok=True)
    if only == "all":
        build_kb(base / "ai-fde-ground-truth-kb")
    build_hris(base / "ai-fde-hr-systems-of-record")
    if only == "all":
        scan_tickets(base / "ai-fde-sample-employee-inquiries" / "tickets.jsonl")
