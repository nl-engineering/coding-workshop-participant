"""Runs the ADK agent for one inquiry and returns the reply text.
Sources the agent retrieves via tools are appended to `sources` so citation
guardrails validate against everything the agent actually saw."""
from __future__ import annotations

import asyncio

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app import answer

from .agent import SOURCES, root_agent

APP = "hr_ops_copilot"
_sessions = InMemorySessionService()
_runner = Runner(agent=root_agent, app_name=APP, session_service=_sessions)


async def _run(prompt: str) -> str:
    sess = _sessions.create_session(app_name=APP, user_id="analyst")
    if asyncio.iscoroutine(sess):  # async in ADK >= 1.0
        sess = await sess
    final = ""
    msg = types.Content(role="user", parts=[types.Part(text=prompt)])
    async for ev in _runner.run_async(user_id="analyst", session_id=sess.id, new_message=msg):
        if ev.is_final_response() and ev.content and ev.content.parts:
            final = "".join(p.text or "" for p in ev.content.parts)
    return final


def run_agent(question: str, first_name: str, sources: list) -> str:
    token = SOURCES.set(sources)
    try:
        prompt = (f"SOURCES:\n{answer.sources_block(sources)}\n\nEMPLOYEE FIRST NAME: {first_name}\n"
                  f"<employee_message>\n{question}\n</employee_message>")
        return asyncio.run(_run(prompt))
    finally:
        SOURCES.reset(token)
