"""FastAPI application (primary). Run:  uvicorn app.api:app --reload --port 8000   (from backend/)
OpenAPI docs at /docs. Serves the built React app (frontend/dist) at /."""
from __future__ import annotations

from typing import Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, service

app = FastAPI(title="ACME HR Ops Copilot", version="1.0",
              description="Grounded, cited HR answers with human-in-the-loop approval for sensitive topics and HR data changes.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    service.init()


def _r(res):
    body, code = res if isinstance(res, tuple) else (res, 200)
    if code >= 400:
        raise HTTPException(code, body.get("error", "error"))
    return JSONResponse(content=__import__("json").loads(service.dumps(body)))


@app.get("/api/health")
def health():
    return _r(service.health())


@app.get("/api/inquiries")
def inquiries():
    return _r(service.inquiries())


@app.post("/api/process")
def process(body: dict = Body(...)):
    return _r(service.process(body))


@app.post("/api/process_all")
def process_all(body: dict = Body(default={})):
    return _r(service.process_all(body))


@app.get("/api/cases")
def cases(status: Optional[str] = None):
    return _r(service.cases(status))


@app.get("/api/cases/{cid}")
def case(cid: str):
    return _r(service.case(cid))


@app.post("/api/cases/{cid}/decision")
def decision(cid: str, body: dict = Body(...)):
    return _r(service.decision(cid, body))


@app.post("/api/cases/{cid}/feedback")
def feedback(cid: str, body: dict = Body(...)):
    return _r(service.feedback(cid, body))


@app.get("/api/metrics")
def metrics():
    return _r(service.metrics())


@app.get("/api/gaps")
def gaps():
    return _r(service.store.gaps())


@app.get("/api/audit")
def audit():
    return _r(service.store.audit_log())


@app.get("/api/audit/verify")
def verify():
    return _r(service.store.verify_chain())


@app.get("/api/kb")
def kb():
    return _r(service.kb())


@app.get("/api/search")
def search(q: str):
    return _r(service.search(q))


@app.get("/api/employees/{eid}")
def employee(eid: str):
    return _r(service.employee(eid))


@app.post("/api/evals")
def evals(body: dict = Body(default={})):
    return _r(service.run_evals(body))


@app.get("/api/ticket_stats")
def ticket_stats():
    return _r(service.ticket_stats())


@app.get("/api/evals/last")
def last_eval():
    return _r(service.last_eval())


@app.post("/api/reindex")
def reindex():
    return _r(service.reindex())


_dist = config.ROOT / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = _dist / path
        return FileResponse(f if path and f.is_file() else _dist / "index.html")
