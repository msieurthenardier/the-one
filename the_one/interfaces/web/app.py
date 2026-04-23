from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from the_one.agent import Agent
from the_one.agent.factory import AgentFactory
from the_one.config import settings
from the_one.db import close_connection, init_db
from the_one.db.connection import get_connection
from the_one.db.migration import migrate_json_to_sqlite
from the_one.db.repositories import SQLiteAgentStore
from the_one.interfaces.web.api import router as api_router
from the_one.llm.base import Role

STATIC_DIR = Path(__file__).parent / "static"


# ── Lifespan ──────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize DB on startup, close on shutdown."""
    await init_db()
    conn = await get_connection()
    store = SQLiteAgentStore(conn)
    await migrate_json_to_sqlite(store)
    _state["factory"] = AgentFactory(store=store)
    yield
    await close_connection()


app = FastAPI(title="the-one", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api_router)


# ── State ─────────────────────────────────────────────────────────────────

_state: dict[str, Any] = {}


def _get_factory() -> AgentFactory:
    return _state.get("factory") or AgentFactory()


# ── Sessions ─────────────────────────────────────────────────────────────


@dataclass
class Session:
    id: str
    agent: Agent
    created: str
    source: str = "web"
    title: str = "New chat"
    history: list[dict[str, Any]] = field(default_factory=list)
    subscribers: set[WebSocket] = field(default_factory=set, repr=False)

    def add_event(self, event: dict[str, Any]) -> None:
        self.history.append(event)
        # Update title from first user message
        if self.title == "New chat" and event.get("type") == "user":
            self.title = event["content"][:50]

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created": self.created,
            "source": self.source,
            "message_count": len(self.history),
        }


_sessions: dict[str, Session] = {}


async def _get_session(session_id: str | None = None, source: str = "web") -> Session:
    if session_id and session_id in _sessions:
        return _sessions[session_id]
    # Create new session
    sid = session_id or uuid.uuid4().hex[:12]
    factory = _get_factory()
    session = Session(
        id=sid,
        agent=await factory.create(),
        created=datetime.now(timezone.utc).isoformat(),
        source=source,
    )
    _sessions[sid] = session
    return session


async def _send_to_session(
    session: Session,
    payload: dict[str, Any],
    exclude: WebSocket | None = None,
) -> None:
    """Send a JSON payload to all websocket subscribers of a session."""
    dead: list[WebSocket] = []
    for ws in session.subscribers:
        if ws is exclude:
            continue
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        session.subscribers.discard(ws)


async def _process_and_broadcast(
    session: Session,
    user_input: str,
    source: str = "web",
    exclude_user_echo: WebSocket | None = None,
) -> list[dict[str, Any]]:
    """Run agent step, broadcast all events, return message list for API."""
    # Broadcast user message
    user_event = {"type": "user", "content": user_input, "source": source}
    session.add_event(user_event)
    await _send_to_session(session, user_event, exclude=exclude_user_echo)

    total_input = 0
    total_output = 0
    last_input = 0
    max_context = session.agent.llm.max_context_tokens

    result_messages: list[dict[str, Any]] = []
    async for msg in session.agent.step(user_input):
        if msg.role == Role.ASSISTANT:
            if msg.usage:
                total_input += msg.usage.input_tokens
                total_output += msg.usage.output_tokens
                last_input = msg.usage.input_tokens
                usage_event = {
                    "type": "usage",
                    "input_tokens": total_input,
                    "output_tokens": total_output,
                    "context_tokens": last_input,
                    "max_context_tokens": max_context,
                }
                await _send_to_session(session, usage_event)

            if msg.content:
                event: dict[str, Any] = {"type": "assistant", "content": msg.content}
                session.add_event(event)
                await _send_to_session(session, event)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_event = {"type": "tool_call", "name": tc.name, "arguments": tc.arguments}
                    session.add_event(tc_event)
                    await _send_to_session(session, tc_event)

            entry: dict[str, Any] = {"role": "assistant"}
            if msg.content:
                entry["content"] = msg.content
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {"name": tc.name, "arguments": tc.arguments}
                    for tc in msg.tool_calls
                ]
            result_messages.append(entry)

        elif msg.role == Role.TOOL and msg.tool_result:
            tr_event = {
                "type": "tool_result",
                "content": msg.tool_result.content[:2000],
                "is_error": msg.tool_result.is_error,
            }
            session.add_event(tr_event)
            await _send_to_session(session, tr_event)
            result_messages.append({
                "role": "tool",
                "content": msg.tool_result.content[:4000],
                "is_error": msg.tool_result.is_error,
            })

    await _send_to_session(session, {"type": "done"})
    return result_messages


# ── Routes ───────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC_DIR / "index.html").read_text()


@app.get("/api/info")
async def info() -> dict[str, Any]:
    import json as _json

    result: dict[str, Any] = {
        "version": "0.1.0",
        "provider": settings.llm_provider,
        "model": settings.llm_model,
    }

    status_file = settings.workspace_dir / ".deploy-status.json"
    if status_file.exists():
        try:
            result["deploy"] = _json.loads(status_file.read_text())
        except Exception:
            pass

    return result


@app.get("/api/selftest")
async def selftest() -> dict[str, Any]:
    """Run a quick smoke test: can the agent chat and use tools?"""
    from fastapi.responses import JSONResponse

    checks: list[dict[str, Any]] = []
    factory = _get_factory()
    agent = await factory.create()

    # Check 1: basic chat
    try:
        reply_parts = []
        async for msg in agent.step("Reply with exactly: SELFTEST_OK"):
            if msg.role == Role.ASSISTANT and msg.content:
                reply_parts.append(msg.content)
        reply = " ".join(reply_parts)
        ok = len(reply) > 0
        checks.append({"name": "chat", "pass": ok, "detail": reply[:100]})
    except Exception as e:
        checks.append({"name": "chat", "pass": False, "detail": str(e)[:200]})

    agent.reset()

    # Check 2: tool use
    try:
        got_tool_result = False
        async for msg in agent.step("Read the file /workspace/pyproject.toml"):
            if msg.role == Role.TOOL and msg.tool_result and not msg.tool_result.is_error:
                got_tool_result = True
        detail = (
            "read_file executed" if got_tool_result
            else "no tool result"
        )
        checks.append({
            "name": "tool_use",
            "pass": got_tool_result,
            "detail": detail,
        })
    except Exception as e:
        checks.append({"name": "tool_use", "pass": False, "detail": str(e)[:200]})

    all_passed = all(c["pass"] for c in checks)
    result = {"status": "pass" if all_passed else "fail", "checks": checks}

    if not all_passed:
        return JSONResponse(content=result, status_code=500)
    return result


@app.get("/api/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    return [s.summary() for s in sorted(_sessions.values(), key=lambda s: s.created, reverse=True)]


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    if session_id not in _sessions:
        return {"error": "session not found"}
    s = _sessions[session_id]
    return {**s.summary(), "history": s.history}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    if session_id in _sessions:
        del _sessions[session_id]
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(request: Request) -> dict[str, Any]:
    """Chat endpoint for programmatic access."""
    payload = await request.json()
    user_input = payload.get("message", "")
    source = payload.get("source", "api")
    session_id = payload.get("session_id")

    if not user_input:
        return {"error": "no message provided"}

    session = await _get_session(session_id, source=source)

    if user_input == "/reset":
        session.agent.reset()
        session.history.clear()
        session.title = "New chat"
        await _send_to_session(session, {"type": "system", "content": "Context cleared."})
        return {
            "session_id": session.id,
            "messages": [
                {"role": "system", "content": "Context cleared."}
            ],
        }

    result = await _process_and_broadcast(session, user_input, source=source)
    return {"session_id": session.id, "messages": result}


@app.post("/api/chat/reset")
async def chat_reset(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type")
    payload = (
        await request.json()
        if content_type == "application/json"
        else {}
    )
    session_id = payload.get("session_id")
    if session_id and session_id in _sessions:
        s = _sessions[session_id]
        s.agent.reset()
        s.history.clear()
        s.title = "New chat"
        await _send_to_session(s, {"type": "system", "content": "Context cleared."})
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    session: Session | None = None

    try:
        while True:
            data = await ws.receive_text()
            payload = json.loads(data)
            action = payload.get("action", "message")

            # Session management actions
            if action == "join":
                session_id = payload.get("session_id")
                session = await _get_session(session_id)
                if ws not in session.subscribers:
                    session.subscribers.add(ws)
                await ws.send_json({
                    "type": "session_joined",
                    "session_id": session.id,
                    "title": session.title,
                    "history": session.history,
                })
                continue

            if action == "list_sessions":
                await ws.send_json({
                    "type": "session_list",
                    "sessions": [
                        s.summary()
                        for s in sorted(
                            _sessions.values(),
                            key=lambda s: s.created,
                            reverse=True,
                        )
                    ],
                })
                continue

            if action == "new_session":
                # Leave current session
                if session:
                    session.subscribers.discard(ws)
                session = await _get_session()
                session.subscribers.add(ws)
                await ws.send_json({
                    "type": "session_joined",
                    "session_id": session.id,
                    "title": session.title,
                    "history": [],
                })
                continue

            if action == "delete_session":
                sid = payload.get("session_id")
                if sid and sid in _sessions:
                    if session and session.id == sid:
                        session.subscribers.discard(ws)
                        session = None
                    del _sessions[sid]
                await ws.send_json({"type": "session_deleted", "session_id": sid})
                continue

            # Regular message
            user_input = payload.get("message", "")
            if not user_input:
                continue

            # Auto-join a session if none active
            if not session:
                session = await _get_session()
                session.subscribers.add(ws)
                await ws.send_json({
                    "type": "session_joined",
                    "session_id": session.id,
                    "title": session.title,
                    "history": [],
                })

            if user_input == "/reset":
                session.agent.reset()
                session.history.clear()
                session.title = "New chat"
                await _send_to_session(session, {"type": "system", "content": "Context cleared."})
                continue

            # Process message — exclude echoing user msg back to sender
            await _process_and_broadcast(session, user_input, source="web", exclude_user_echo=ws)

    except WebSocketDisconnect:
        if session:
            session.subscribers.discard(ws)
