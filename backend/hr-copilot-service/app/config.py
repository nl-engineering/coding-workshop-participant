"""Settings. Everything is optional: with nothing configured the app runs fully offline
(extractive answers, hashing embeddings, in-memory vectors, SQLite).

LLM_PROVIDER: auto | claude | gemini | ollama | gateway | offline
  claude  -> ANTHROPIC_API_KEY            (Commercial: Claude)
  gemini  -> GOOGLE_API_KEY               (Commercial: Gemini)
  ollama  -> local Gemma / Llama via Ollama (Open source, data never leaves the machine)
  gateway -> MLflow AI Gateway endpoint   (MLFLOW_GATEWAY_URI + GATEWAY_ENDPOINT)
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            v = v.split(" #")[0].strip().strip('"').strip("'")
            if v:
                os.environ.setdefault(k.strip(), v)

DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", DATA_DIR / "kb" if (DATA_DIR / "kb").exists() else DATA_DIR / "knowledge"))
INQUIRIES_PATH = Path(os.getenv("INQUIRIES_PATH", DATA_DIR / "inquiries.jsonl"))
HRIS_PATH = Path(os.getenv("HRIS_PATH", DATA_DIR / "hris" / "employees.json"))
DB_PATH = Path(os.getenv("APP_DB", ROOT / "hr_copilot.db"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3")
MLFLOW_GATEWAY_URI = os.getenv("MLFLOW_GATEWAY_URI", "")
GATEWAY_ENDPOINT = os.getenv("GATEWAY_ENDPOINT", "chat")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "60"))

# Retrieval
DATABASE_URL = os.getenv("DATABASE_URL", "")        # postgresql://... enables pgvector
EMBEDDINGS = os.getenv("EMBEDDINGS", "hashing")      # hashing | gemini | ollama
EMBED_DIM = 512
TOP_K = int(os.getenv("TOP_K", "4"))
MIN_RETRIEVAL_SCORE = float(os.getenv("MIN_RETRIEVAL_SCORE", "0.22"))

# Guardrails / routing policy (owned by the business, versioned)
POLICY_VERSION = "HROPS-AI-POL-1.0"
MIN_GROUNDEDNESS = float(os.getenv("MIN_GROUNDEDNESS", "0.55"))

# Business case (replace with discovery numbers)
# Business case. Volumes and tier mix are MEASURED from 2M historical tickets (data/ticket_stats.json);
# analyst effort minutes are assumptions to confirm with the Head of HR Ops.
ROI = {
    "tickets_per_year": int(os.getenv("TICKETS_PER_YEAR", "500000")),        # measured: 500k/yr 2023-2026
    "tier_mix": {"1": 0.50, "2": 0.30, "3": 0.20},                           # measured
    "effort_min_today": {"1": float(os.getenv("EFFORT_T1", "10")), "2": float(os.getenv("EFFORT_T2", "30")), "3": float(os.getenv("EFFORT_T3", "60"))},
    "effort_min_with_ai": {"1": float(os.getenv("EFFORT_AI_T1", "1")), "2": float(os.getenv("EFFORT_AI_T2", "12")), "3": float(os.getenv("EFFORT_AI_T3", "45"))},
    "resolution_min_today": {"1": 65, "2": 330, "3": 2341},                  # measured medians (elapsed)
    "sla_days": 3,
    "loaded_cost_per_hour": float(os.getenv("COST_PER_HOUR", "55")),
    "productive_hours_per_fte": 1700,
}


def provider() -> str:
    if LLM_PROVIDER != "auto":
        return LLM_PROVIDER
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    if os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    if MLFLOW_GATEWAY_URI:
        return "gateway"
    return "offline"


def model_name() -> str:
    return {"claude": ANTHROPIC_MODEL, "gemini": GEMINI_MODEL, "ollama": OLLAMA_MODEL,
            "gateway": f"gateway:{GATEWAY_ENDPOINT}"}.get(provider(), "offline-extractive")
