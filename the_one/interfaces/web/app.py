from __future__ import annotations

import json
import logging
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
from the_one.db.codec import decode_messages, encode_messages, messages_to_ui_events
from the_one.db.connection import get_connection
from the_one.db.migration import migrate_json_to_sqlite
from the_one.db.models import ChatSession as ChatSessionModel
from the_one.db.repositories import ChatSessionRepository, LLMProviderRepository, SQLiteAgentStore
from the_one.encryption import get_encryptor
from the_one.interfaces.web.api import router as api_router
from the_one.llm.base import Role

logger = logging.getLogger(__name__)

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
    agent_name: str | None = None
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
            "agent_name": self.agent_name,
            "message_count": len(self.history),
        }


_sessions: dict[str, Session] = {}


# ── DB helpers ────────────────────────────────────────────────────────────


async def _chat_repo() -> ChatSessionRepository:
    conn = await get_connection()
    return ChatSessionRepository(conn)


async def _create_session(
    agent_name: str | None = None,
    source: str = "web",
    session_id: str | None = None,
) -> Session:
    """Create a new session in both memory and DB."""
    sid = session_id or uuid.uuid4().hex[:12]
    # Normalize agent_name: "default" or empty -> None in DB (FK constraint)
    db_agent_name = None if (not agent_name or agent_name == "default") else agent_name
    factory = _get_factory()
    agent = await factory.create(agent_name or "default")
    now = datetime.now(timezone.utc).isoformat()
    session = Session(
        id=sid,
        agent=agent,
        created=now,
        source=source,
        agent_name=db_agent_name,
    )
    _sessions[sid] = session

    # Persist to DB
    try:
        repo = await _chat_repo()
        db_session = ChatSessionModel(
            id=sid,
            agent_name=db_agent_name,
            title=session.title,
            messages="[]",
            created_at=now,
            updated_at=now,
        )
        await repo.create(db_session)
    except Exception:
        logger.warning("Failed to persist new session %s to DB", sid, exc_info=True)

    return session


async def _restore_session(session_id: str) -> Session | None:
    """Load a session from DB into memory, rebuilding the agent."""
    try:
        repo = await _chat_repo()
        db_session = await repo.get(session_id)
    except KeyError:
        return None

    factory = _get_factory()
    agent_name_for_factory = db_session.agent_name or "default"
    try:
        agent = await factory.create(agent_name_for_factory)
    except KeyError:
        logger.warning(
            "Agent %r not found, falling back to default for session %s",
            db_session.agent_name, session_id,
        )
        agent = await factory.create("default")

    # Decode messages and inject into agent
    messages = decode_messages(db_session.messages)
    if messages:
        agent.messages = messages

    # Build UI events from stored messages
    ui_events = messages_to_ui_events(messages)

    session = Session(
        id=session_id,
        agent=agent,
        created=db_session.created_at,
        title=db_session.title,
        agent_name=db_session.agent_name,
        history=ui_events,
    )
    _sessions[session_id] = session
    return session


async def _get_or_restore_session(session_id: str) -> Session | None:
    """Check memory first, fall back to DB restore."""
    if session_id in _sessions:
        return _sessions[session_id]
    return await _restore_session(session_id)


async def _save_session_to_db(session: Session) -> None:
    """Persist current session state to DB."""
    try:
        repo = await _chat_repo()
        encoded = encode_messages(session.agent.messages)
        try:
            db_session = await repo.get(session.id)
        except KeyError:
            logger.warning("Session %s not found in DB during save", session.id)
            return
        updated = db_session.model_copy(update={
            "title": session.title,
            "messages": encoded,
        })
        await repo.update(updated)
    except Exception:
        logger.warning("Failed to save session %s to DB", session.id, exc_info=True)


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


async def _ensure_ollama_model_loaded(session: Session) -> None:
    """If the session's agent uses an Ollama provider, ensure its model is loaded.

    Sends a system message to subscribers when loading is needed.  Errors are
    logged but never propagated — a failed pre-load should not block the chat.
    """
    from the_one.llm import ollama_api

    try:
        # Resolve agent config from DB (Option B from leg spec)
        agent_name = session.agent_name or "default"
        conn = await get_connection()
        store = SQLiteAgentStore(conn)

        if not await store.exists(agent_name):
            return  # default agent without DB record — skip

        agent_config = await store.load(agent_name)

        if agent_config.provider_config_id is None:
            return

        encryptor = get_encryptor(settings.data_dir)
        provider_repo = LLMProviderRepository(conn, encryptor)
        provider_config = await provider_repo.get(agent_config.provider_config_id)

        if provider_config.type != "ollama":
            return

        # Check if model is already loaded
        running = await ollama_api.list_running(provider_config.base_url)
        model_name = agent_config.llm_model

        for m in running:
            running_name = m.get("name", "")
            # Exact match, or match ignoring :latest tag
            if running_name == model_name:
                return
            if running_name == f"{model_name}:latest":
                return
            if model_name == f"{running_name}:latest":
                return

        # Model not loaded — notify subscribers and trigger load
        await _send_to_session(
            session, {"type": "system", "content": "Loading model..."}
        )
        await ollama_api.load_model(provider_config.base_url, model_name)
        await _send_to_session(
            session, {"type": "system", "content": "Model loaded."}
        )

    except Exception:
        logger.warning(
            "Auto-load check failed for session %s", session.id, exc_info=True,
        )


async def _process_and_broadcast(
    session: Session,
    user_input: str,
    source: str = "web",
    exclude_user_echo: WebSocket | None = None,
) -> list[dict[str, Any]]:
    """Run agent step, broadcast all events, return message list for API."""
    # Auto-load Ollama model if needed (fast check, safe to run every message)
    await _ensure_ollama_model_loaded(session)

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

    # Save to DB after each complete exchange
    try:
        await _save_session_to_db(session)
    except Exception:
        logger.warning("Failed to save session %s after exchange", session.id, exc_info=True)

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


@app.post("/api/chat")
async def chat(request: Request) -> dict[str, Any]:
    """Chat endpoint for programmatic access."""
    payload = await request.json()
    user_input = payload.get("message", "")
    source = payload.get("source", "api")
    session_id = payload.get("session_id")
    agent_name = payload.get("agent_name")

    if not user_input:
        return {"error": "no message provided"}

    # Resolve or create session
    session: Session | None = None
    if session_id:
        session = await _get_or_restore_session(session_id)
    if session is None:
        session = await _create_session(agent_name=agent_name, source=source, session_id=session_id)

    if user_input == "/reset":
        session.agent.reset()
        session.history.clear()
        session.title = "New chat"
        await _send_to_session(session, {"type": "system", "content": "Context cleared."})
        await _save_session_to_db(session)
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
        await _save_session_to_db(s)
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
                if session_id:
                    session = await _get_or_restore_session(session_id)
                if session is None:
                    session = await _create_session()
                if ws not in session.subscribers:
                    session.subscribers.add(ws)
                await ws.send_json({
                    "type": "session_joined",
                    "session_id": session.id,
                    "title": session.title,
                    "agent_name": session.agent_name,
                    "history": session.history,
                })
                continue

            if action == "list_sessions":
                try:
                    repo = await _chat_repo()
                    db_sessions = await repo.list()
                    sessions_list = [
                        {
                            "id": s.id,
                            "title": s.title,
                            "agent_name": s.agent_name,
                            "created_at": s.created_at,
                            "updated_at": s.updated_at,
                        }
                        for s in db_sessions
                    ]
                except Exception:
                    logger.warning("Failed to list sessions from DB", exc_info=True)
                    sessions_list = []
                await ws.send_json({
                    "type": "session_list",
                    "sessions": sessions_list,
                })
                continue

            if action == "new_session":
                # Leave current session
                if session:
                    session.subscribers.discard(ws)
                agent_name = payload.get("agent_name")
                session = await _create_session(agent_name=agent_name)
                session.subscribers.add(ws)
                await ws.send_json({
                    "type": "session_joined",
                    "session_id": session.id,
                    "title": session.title,
                    "agent_name": session.agent_name,
                    "history": [],
                })
                continue

            if action == "delete_session":
                sid = payload.get("session_id")
                if sid:
                    # Remove from memory
                    if sid in _sessions:
                        if session and session.id == sid:
                            session.subscribers.discard(ws)
                            session = None
                        del _sessions[sid]
                    # Remove from DB
                    try:
                        repo = await _chat_repo()
                        await repo.delete(sid)
                    except KeyError:
                        pass
                    except Exception:
                        logger.warning("Failed to delete session %s from DB", sid, exc_info=True)
                await ws.send_json({"type": "session_deleted", "session_id": sid})
                continue

            # Regular message
            user_input = payload.get("message", "")
            if not user_input:
                continue

            # Auto-join a session if none active
            if not session:
                session = await _create_session()
                session.subscribers.add(ws)
                await ws.send_json({
                    "type": "session_joined",
                    "session_id": session.id,
                    "title": session.title,
                    "agent_name": session.agent_name,
                    "history": [],
                })

            if user_input == "/reset":
                session.agent.reset()
                session.history.clear()
                session.title = "New chat"
                await _send_to_session(session, {"type": "system", "content": "Context cleared."})
                await _save_session_to_db(session)
                continue

            # Process message — exclude echoing user msg back to sender
            await _process_and_broadcast(session, user_input, source="web", exclude_user_echo=ws)

    except WebSocketDisconnect:
        if session:
            session.subscribers.discard(ws)
