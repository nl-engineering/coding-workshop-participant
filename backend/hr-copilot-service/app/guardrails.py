"""Guardrails: input and output validators, in the Guardrails AI style
(each validator returns pass/fail plus an on_fail action: fix | refrain | escalate).
If Guardrails AI is installed, these can be registered as custom validators; in
production the MLflow AI Gateway adds rate limits, key management and model routing
in front of the same calls.

INPUT : PII detection + masking, prompt-injection detection
OUTPUT: citations present & valid, groundedness, PII leakage, no advice on
        restricted topics, no unsupported promises
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from . import config
from .rag import tokenize

PII = {
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "EMAIL": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "PHONE": re.compile(r"(?<![\w-])\+?1?[\s(]*\d{3}[\s)\-.]*\d{3}[\s\-.]\d{4}\b"),
    "BANK_ACCOUNT": re.compile(r"(?i)(?:account|acct)(?:\s*(?:no\.?|number|#))?\s*[:#]?\s*(\d{6,17})"),
    "ROUTING": re.compile(r"(?i)routing(?:\s*(?:no\.?|number|#))?\s*[:#]?\s*(\d{9})"),
    "DOB": re.compile(r"(?i)(?:dob|date of birth)\s*[:#]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"),
}
INJECTION = [
    r"ignore (all |any |your )?(previous|prior|above) (instructions|rules|policies)", r"you are now", r"admin mode",
    r"developer mode", r"system prompt", r"disregard (the |your )?(rules|policy|policies|instructions)",
    r"reveal (the |your )?(prompt|instructions|salary bands|all)", r"act as (an? )?(admin|system)", r"jailbreak",
    r"bypass (the )?(approval|guardrails|checks)", r"approve .* immediately",
]


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    on_fail: str = "escalate"   # fix | refrain | escalate


def mask_pii(text: str) -> tuple[str, dict[str, str], list[str]]:
    vault, kinds, n = {}, [], 0
    for kind, pat in PII.items():
        def sub(m, kind=kind):
            nonlocal n
            n += 1
            val = m.group(1) if m.groups() else m.group(0)
            tok = f"[{kind}_{n}]"
            vault[tok] = val
            kinds.append(kind)
            return m.group(0).replace(val, tok)
        text = pat.sub(sub, text)
    return text, vault, sorted(set(kinds))


def check_input(text: str) -> tuple[str, dict, list[Check]]:
    masked, vault, kinds = mask_pii(text)
    hits = [p for p in INJECTION if re.search(p, text, re.I)]
    checks = [
        Check("PII masking", True, f"masked {len(vault)} item(s): {', '.join(kinds)}" if vault else "no PII detected", "fix"),
        Check("Prompt-injection screen", not hits,
              "suspicious instructions detected: " + "; ".join(h.replace("\\", "") for h in hits[:2]) if hits else "clean",
              "escalate"),
    ]
    return masked, vault, checks


RESTRICTED_ADVICE = {
    "medical": r"\b(you should|you must|i recommend|i advise)\b.*\b(surgery|treatment|doctor|medication)\b",
    "legal": r"\b(you have a (strong |good )?case|sue|lawsuit|legal advice)\b",
    "immigration": r"\b(you can (safely )?travel|your visa (is|will be) (fine|approved))\b",
}


def groundedness(answer: str, sources: list[dict]) -> float:
    """Share of the answer's content words that appear in the cited sources (lexical support)."""
    a = [t for t in tokenize(re.sub(r"\[\d+\]", " ", answer)) if not t.isdigit() or len(t) > 1]
    if not a:
        return 0.0
    src = set(tokenize(" ".join(s["text"] + " " + s["section"] + " " + s["title"] for s in sources)))
    return round(sum(t in src for t in a) / len(a), 2)


def check_output(answer: str, sources: list[dict], vault: dict) -> tuple[list[Check], dict]:
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
    valid = [n for n in cited if 1 <= n <= len(sources)]
    invalid = [n for n in cited if n not in valid]
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer.strip()) if len(s.split()) > 4
                 and not re.match(r"(?i)^(hi|hello|dear|thanks|thank you|best|kind regards|regards)\b", s)]
    uncited = [s for s in sentences if not re.search(r"\[\d+\]", s)]
    used = [sources[n - 1] for n in valid]
    g = groundedness(answer, used) if used else 0.0
    leaked = [v for v in vault.values() if v and v in answer]
    advice = [k for k, p in RESTRICTED_ADVICE.items() if re.search(p, answer, re.I)]
    checks = [
        Check("Citations present", bool(valid) and len(uncited) <= max(1, len(sentences) // 3),
              f"{len(valid)} source(s) cited; {len(uncited)} uncited factual sentence(s)", "refrain"),
        Check("Citations valid", not invalid, "all citations map to retrieved passages" if not invalid
              else f"unknown citation(s): {invalid}", "refrain"),
        Check("Grounded in sources", g >= config.MIN_GROUNDEDNESS, f"groundedness {g:.2f} (min {config.MIN_GROUNDEDNESS})", "escalate"),
        Check("No PII leakage", not leaked, "no personal identifiers in draft" if not leaked else "draft repeats masked PII", "fix"),
        Check("No restricted advice", not advice, "none" if not advice else f"possible {', '.join(advice)} advice", "escalate"),
    ]
    return checks, {"cited": valid, "groundedness": g}


def as_dicts(checks: list[Check]) -> list[dict]:
    return [asdict(c) for c in checks]
