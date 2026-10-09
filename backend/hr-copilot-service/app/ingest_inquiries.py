"""Loads the inquiry dataset in whatever shape it arrives (CSV, JSON, JSONL, or a folder of
.txt/.eml files) and normalises to {id, channel, employee_id, subject, body, received_at}.
Column names are matched loosely so the workshop dataset works without code changes;
add aliases below if needed."""
from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path

from . import config

ALIASES = {
    "id": ["id", "inquiry_id", "ticket_id", "case_id", "ticket", "case_number", "number"],
    "channel": ["channel", "source", "medium", "type"],
    "employee_id": ["employee_id", "emp_id", "requester_id", "employee", "user_id", "requester"],
    "subject": ["subject", "title", "summary", "short_description"],
    "body": ["body", "text", "message", "description", "inquiry", "content", "question", "query", "details", "thread"],
    "received_at": ["received_at", "created_at", "date", "timestamp", "created", "opened_at"],
}


def _norm(row: dict, i: int) -> dict:
    low = {str(k).strip().lower(): v for k, v in row.items()}
    out = {}
    for k, names in ALIASES.items():
        out[k] = next((str(low[n]) for n in names if low.get(n) not in (None, "")), "")
    if not out["body"]:  # fall back to the longest text field
        out["body"] = max((str(v) for v in low.values() if isinstance(v, str)), key=len, default="")
    out["id"] = out["id"] or f"INQ-{i + 1:04d}"
    out["channel"] = (out["channel"] or "email").lower()
    return out


@lru_cache
def load(path: str | None = None) -> list[dict]:
    p = Path(path or config.INQUIRIES_PATH)
    if not p.exists():
        return []
    rows: list = []
    if p.is_dir():
        for i, f in enumerate(sorted(x for x in p.rglob("*") if x.suffix.lower() in (".txt", ".eml", ".md"))):
            t = f.read_text(errors="ignore")
            subj = next((l[8:].strip() for l in t.splitlines() if l.lower().startswith("subject:")), f.stem)
            rows.append({"id": f.stem, "subject": subj, "body": t})
    elif p.suffix.lower() == ".csv":
        with open(p, newline="", encoding="utf-8", errors="ignore") as fh:
            rows = list(csv.DictReader(fh))
    elif p.suffix.lower() == ".jsonl":
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    else:
        d = json.loads(p.read_text())
        rows = d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), [d])
    return [_norm(r, i) for i, r in enumerate(rows)]
