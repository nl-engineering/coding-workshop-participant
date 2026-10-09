"""Provider-agnostic LLM client (stdlib HTTP, no SDK lock-in).
Claude, Gemini, local Gemma/Llama via Ollama, or the MLflow AI Gateway.
Every failure raises LLMError so the pipeline can degrade safely."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from . import config


class LLMError(RuntimeError):
    pass


def _post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT_S) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP {e.code}: {e.read()[:200]!r}") from e
    except Exception as e:  # noqa: BLE001
        raise LLMError(str(e)[:200]) from e


def chat(system: str, user: str, json_mode: bool = False, max_tokens: int = 1200) -> str:
    p = config.provider()
    if p == "offline":
        raise LLMError("offline mode")
    if p == "claude":
        d = _post("https://api.anthropic.com/v1/messages",
                  {"model": config.ANTHROPIC_MODEL, "max_tokens": max_tokens, "temperature": 0,
                   "system": system + ("\nRespond with a single JSON object only." if json_mode else ""),
                   "messages": [{"role": "user", "content": user}]},
                  {"x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01"})
        return "".join(b.get("text", "") for b in d.get("content", []))
    if p == "gemini":
        gen = {"temperature": 0, "maxOutputTokens": max_tokens}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        d = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent",
                  {"systemInstruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": gen},
                  {"x-goog-api-key": os.environ.get("GOOGLE_API_KEY", "")})
        try:
            return "".join(pt.get("text", "") for pt in d["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as e:
            raise LLMError(f"unexpected Gemini response: {str(d)[:200]}") from e
    if p == "ollama":
        body = {"model": config.OLLAMA_MODEL, "stream": False, "options": {"temperature": 0},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            body["format"] = "json"
        return _post(f"{config.OLLAMA_URL.rstrip('/')}/api/chat", body, {})["message"]["content"]
    if p == "gateway":  # MLflow AI Gateway (deployments server) chat endpoint
        d = _post(f"{config.MLFLOW_GATEWAY_URI.rstrip('/')}/endpoints/{config.GATEWAY_ENDPOINT}/invocations",
                  {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   "temperature": 0, "max_tokens": max_tokens}, {})
        return d["choices"][0]["message"]["content"]
    raise LLMError(f"unknown provider {p}")


def chat_json(system: str, user: str) -> dict:
    txt = chat(system, user, json_mode=True).strip()
    if txt.startswith("```"):
        txt = txt.strip("`").split("\n", 1)[1].rsplit("```", 1)[0] if "\n" in txt else txt
    s, e = txt.find("{"), txt.rfind("}")
    if s < 0:
        raise LLMError("no JSON in response")
    try:
        return json.loads(txt[s:e + 1])
    except json.JSONDecodeError as ex:
        raise LLMError(f"bad JSON: {ex}") from ex
