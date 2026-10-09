"""AWS Lambda entry point for the workshop template (Lambda behind API Gateway / Function URL / CloudFront).
Handles API Gateway REST (v1) and HTTP API / Function URL (v2) events and routes them to the
same handlers as the FastAPI and stdlib servers. The core is stdlib-only, so no packaging of
dependencies is required.

Handler name:  lambda_handler.handler   (alias: lambda_handler.lambda_handler)
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
    os.environ.setdefault("APP_DB", "/tmp/hr_copilot.db")  # only writable path in Lambda
    if not os.getenv("DATA_DIR") and (HERE / "data").exists():
        os.environ["DATA_DIR"] = str(HERE / "data")    # data bundled next to the handler

from app import service  # noqa: E402
from app.server_std import GET, POST  # noqa: E402

_ready = False
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": "*", "Content-Type": "application/json"}
PREFIX = os.getenv("API_PREFIX", "")  # e.g. "/hr-copilot" if the gateway path includes the service name


def _resp(code: int, body) -> dict:
    return {"statusCode": code, "headers": CORS, "body": service.dumps(body).decode()}


def handler(event, context=None):
    global _ready
    if not _ready:
        service.init()
        _ready = True
    event = event or {}
    method = (event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod") or "GET").upper()
    path = event.get("rawPath") or event.get("path") or "/"
    if PREFIX and path.startswith(PREFIX):
        path = path[len(PREFIX):] or "/"
    known = lambda x: any(re.fullmatch(pat, x) for pat, _ in GET + POST)  # noqa: E731
    m = re.search(r".*(/api/.*)$", path)  # tolerate stage/service prefixes: /prod/api/hr/api/health -> /api/health
    if m and known(m.group(1)):
        path = m.group(1)
    elif not known(path):  # /api/<service>/health, /<service>/health, /health -> /api/health
        segs = [x for x in path.split("/") if x]
        for i in range(len(segs)):
            cand = "/api/" + "/".join(segs[i:])
            if any(re.fullmatch(pat, cand) for pat, _ in GET + POST):
                path = cand
                break
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": CORS, "body": ""}
    q = event.get("queryStringParameters") or {}
    if not q and event.get("rawQueryString"):
        q = {k: v[0] for k, v in parse_qs(event["rawQueryString"]).items()}
    raw = event.get("body") or ""
    if raw and event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return _resp(400, {"error": "invalid JSON"})
    for pat, fn in (GET if method == "GET" else POST):
        mm = re.fullmatch(pat, path)
        if mm:
            try:
                res = fn(mm, q if method == "GET" else body)
                b, code = res if isinstance(res, tuple) else (res, 200)
                return _resp(code, b)
            except Exception as e:  # noqa: BLE001
                return _resp(500, {"error": str(e)})
    if path in ("/", "/api", "/api/"):
        return _resp(200, service.health())
    return _resp(404, {"error": f"no route {method} {path}"})


lambda_handler = handler
