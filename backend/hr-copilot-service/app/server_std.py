"""Zero-dependency fallback server (stdlib) with the same API as app/api.py.
Used automatically by run.py when FastAPI/uvicorn are not installed."""
from __future__ import annotations

import json
import mimetypes
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config, service

DIST = config.ROOT / "frontend" / "dist"
GET = [
    (r"/api/health", lambda m, q: service.health()),
    (r"/api/inquiries", lambda m, q: service.inquiries()),
    (r"/api/cases", lambda m, q: service.cases(q.get("status"))),
    (r"/api/cases/([\w-]+)", lambda m, q: service.case(m.group(1))),
    (r"/api/metrics", lambda m, q: service.metrics()),
    (r"/api/gaps", lambda m, q: service.store.gaps()),
    (r"/api/audit", lambda m, q: service.store.audit_log()),
    (r"/api/audit/verify", lambda m, q: service.store.verify_chain()),
    (r"/api/kb", lambda m, q: service.kb()),
    (r"/api/search", lambda m, q: service.search(q.get("q", ""))),
    (r"/api/employees/(E\d+)", lambda m, q: service.employee(m.group(1))),
    (r"/api/evals/last", lambda m, q: service.last_eval()),
    (r"/api/ticket_stats", lambda m, q: service.ticket_stats()),
]
POST = [
    (r"/api/process", lambda m, b: service.process(b)),
    (r"/api/process_all", lambda m, b: service.process_all(b)),
    (r"/api/cases/([\w-]+)/decision", lambda m, b: service.decision(m.group(1), b)),
    (r"/api/cases/([\w-]+)/feedback", lambda m, b: service.feedback(m.group(1), b)),
    (r"/api/evals", lambda m, b: service.run_evals(b)),
    (r"/api/reindex", lambda m, b: service.reindex()),
]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, table, arg):
        path = urlparse(self.path).path
        for pat, fn in table:
            m = re.fullmatch(pat, path)
            if m:
                try:
                    res = fn(m, arg)
                    body, code = res if isinstance(res, tuple) else (res, 200)
                    return self._send(code, service.dumps(body))
                except Exception as e:  # noqa: BLE001
                    traceback.print_exc()
                    return self._send(500, service.dumps({"error": str(e)}))
        return None

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                     "Access-Control-Allow-Headers": "*"}.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if self._dispatch(GET, {k: v[0] for k, v in parse_qs(u.query).items()}) is not None or u.path.startswith("/api/"):
            return
        f = DIST / u.path.lstrip("/")
        if not (u.path != "/" and f.is_file()):
            f = DIST / "index.html"
        if f.is_file():
            return self._send(200, f.read_bytes(), mimetypes.guess_type(str(f))[0] or "application/octet-stream")
        self._send(200, b"<h3>API running. Build the UI: cd frontend && npm install && npm run build</h3>", "text/html")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, b'{"error":"invalid JSON"}')
        if self._dispatch(POST, body) is None:
            self._send(404, b'{"error":"not found"}')


def serve(port: int):
    service.init()
    print(f"\n  HR Ops Copilot API (stdlib server) -> http://localhost:{port}\n")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
