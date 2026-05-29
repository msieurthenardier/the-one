from __future__ import annotations

import asyncio
import contextlib
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

from the_one import __version__
from the_one.agent import Agent

# F6 L3: ContextVar definitions moved to the_one/agent/_context.py
# (canonical home). Re-exported here for back-compat with F5's
# existing set-sites at _spawn_message_processing (line ~236) and
# _resume_paused_session (line ~853). New consumers should import
# from the_one.agent._context directly.
from the_one.agent._context import (
    current_chat_session_id,  # noqa: F401  back-compat re-export
    current_tool_call_id,  # noqa: F401  re-export for future consumers
)
from the_one.agent.config import BASE_PROMPT
from the_one.agent.factory import (
    AgentFactory,
    AgentNotFoundError,
    ProviderNotConfiguredError,
    ProviderNotFoundError,
    set_factory as _set_module_factory,
)
from the_one.config import settings
from the_one.connectors import OPERATOR_VISIBILITY
from the_one.connectors._pool import shutdown_drain as _connector_pool_shutdown_drain
from the_one.connectors.visibility import tag_post_step_visibility
from the_one.db import close_connection, init_db
from the_one.db.codec import (
    decode_messages,
    encode_messages,
    messages_to_ui_events,
    pending_approvals_to_ui_events,
    truncate_for_event,
)
from the_one.db.connection import get_connection
from the_one.db.migration import migrate_json_to_sqlite
from the_one.db.models import ChatSession as ChatSessionModel
from the_one.db.repositories import (
    ChatSessionRepository,
    LLMProviderRepository,
    PendingApprovalRepository,
    SQLiteAgentStore,
)
from the_one.encryption import get_encryptor
from the_one.interfaces.web.api import router as api_router
from the_one.interfaces.web.middleware import OriginAllowlistMiddleware, build_default_allowlist
from the_one.llm.base import Message, Role
from the_one.mcp import shutdown_drain as _mcp_pool_shutdown_drain
from the_one.sessions import (
    add_subscriber,
    is_session_processing,
    remove_subscriber,
    session_locks,
    subscribers_for,
)
from the_one.tools._session_registry import shutdown_drain as _session_registry_shutdown_drain

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
    # M10 F8 L4: install the application factory into the module-level
    # accessor at ``the_one.agent.factory`` so gateway-listener handlers
    # (Discord's ``on_message`` in F8, Slack's event handler in F9, …)
    # spawned inside ``plugin.connect`` can resolve it without changing
    # the plugin contract. Teardown clears the slot below.
    _set_module_factory(_state["factory"])
    # F5 L2: start the OAuth pending-flow TTL sweep task. The
    # ``_state`` (OAuth) module is reached via the public lifespan
    # hooks ``start_periodic_sweep`` / ``stop_periodic_sweep`` — NOT
    # imported directly — to avoid shadowing this module's existing
    # ``_state: dict[str, Any]`` global at app.py:103.
    from the_one.mcp.oauth import start_periodic_sweep

    start_periodic_sweep()
    # M10 F2 L6: dev-mode-gated test-seam — when
    # THE_ONE_REGISTER_STUB_CONNECTOR=1 AND settings.dev_mode is True,
    # register the in-process StubPlugin as the 'stub' connector type so
    # browser tests running against an `app_clean` subprocess can exercise
    # the doctor-probe and create-and-test paths end-to-end. Production
    # never sets this env var; the dev-mode gate matches the precedent set
    # by the LLM mock provider and OpenRouter test-models seam. Mirrors
    # the test-seam contract documented in `_stub.py` (production code
    # MUST NOT import that module — but the test seam is the explicit
    # opt-in path).
    import os

    if settings.dev_mode and os.environ.get("THE_ONE_REGISTER_STUB_CONNECTOR") == "1":
        from the_one.connectors._stub import StubPlugin
        from the_one.connectors.registry import register_for_test

        register_for_test("stub", StubPlugin)
        logger.info(
            "Registered StubPlugin under 'stub' connector type via "
            "THE_ONE_REGISTER_STUB_CONNECTOR test seam (dev_mode=true)"
        )

    # M10 F8 L11 HAT: warm-acquire each connector account at startup so
    # the gateway listeners (e.g. Discord's on_message handler) spin up
    # immediately. Without this, accounts stay offline until the first
    # agent-initiated outbound triggers acquire — meaning inbound
    # traffic is silently missed until then.
    #
    # M11 F2 L2 (formerly M10 F8 L11 Fix #6): Walk all connector accounts
    # (not just those with attached agents) and acquire via the
    # account-shared ``account_acquire`` primitive. The earlier "first
    # alphabetical attached agent" probe is irrelevant once the pool
    # routes connector callers through one entry per account — full-stop.
    # We still skip accounts with no attached agents to avoid the
    # cost of warming a gateway that no agent will route through;
    # this is a policy choice, not a structural requirement.
    # Errors are logged but do NOT prevent the-one from starting —
    # a misbehaving connector must not take the rest of the system down.
    try:
        from the_one.connectors._pool import account_acquire
        from the_one.db.repositories import ConnectorRepository

        connector_repo = ConnectorRepository(conn, get_encryptor(settings.data_dir))
        accounts = await connector_repo.list()
        for account in accounts:
            try:
                attached = await store.list_by_connector_account(account.id)
                if not attached:
                    logger.info(
                        "Connector account %r (type=%r) has no attached agents; "
                        "skipping startup acquire",
                        account.id, account.type,
                    )
                    continue
                await account_acquire(account.id)
                logger.info(
                    "Warm-acquired connector account %r (type=%r) at startup "
                    "(account-shared pool entry; %d attached agent(s))",
                    account.id, account.type, len(attached),
                )
            except Exception:
                logger.exception(
                    "Failed to warm-acquire connector account %r (type=%r) at startup; "
                    "listener will spin up on first agent-initiated outbound instead",
                    account.id, account.type,
                )
    except Exception:
        logger.exception(
            "Connector-account warm-acquire pass at startup failed entirely; "
            "individual accounts may stay offline until first outbound triggers acquire"
        )

    yield
    # Drain the PTY session registry on shutdown — cancels the idle
    # reaper task and closes any live sessions. Wrapped in
    # ``try/except Exception`` (NOT ``BaseException``) so
    # ``CancelledError`` propagates while a misbehaving session.close()
    # only logs.
    # Cancel any in-flight per-message processing tasks. Each task
    # observes the cancel inside its `_spawn_message_processing` wrapper
    # and exits cleanly; the shared session lock (from
    # ``the_one.sessions``) is released by `async with` automatically.
    for task in list(_inflight_tasks):
        task.cancel()
    if _inflight_tasks:
        with contextlib.suppress(Exception):
            await asyncio.gather(*list(_inflight_tasks), return_exceptions=True)
    # F5 L3: drain in-flight resume tasks alongside the message-processing
    # tasks. Resume tasks are spawned by the OAuth-callback route via
    # ``asyncio.create_task(_resume_paused_session(...))``.
    for task in list(_inflight_resume_tasks):
        task.cancel()
    if _inflight_resume_tasks:
        with contextlib.suppress(Exception):
            await asyncio.gather(*list(_inflight_resume_tasks), return_exceptions=True)
    try:
        await _session_registry_shutdown_drain()
    except Exception:
        logger.exception("session registry shutdown failed")
    # Drain the MCP source pool AFTER PTY drain (PTY may have shell-tool
    # work that still needs MCP processes; let it complete first) and
    # BEFORE DB close (drain may need source config from DB; precautionary
    # — current design loads at register-time so this is forward-looking).
    # See flight §12 for the lifespan-ordering contract; the drain-order
    # spy test (#8) locks it against regression.
    try:
        await _mcp_pool_shutdown_drain()
    except Exception:
        logger.exception("MCP pool shutdown failed")
    # M10 F1 L6: drain the connector pool AFTER MCP pool drain. Like MCP,
    # connectors hold warm network connections; each subsystem's
    # ``shutdown_drain`` bounds its drain time at ~10s via parallel
    # gather, so sequential subsystem drains are fine. Connector pool
    # drain runs BEFORE the OAuth sweep stop (parallel to MCP's
    # ordering) and BEFORE DB close.
    try:
        await _connector_pool_shutdown_drain()
    except Exception:
        logger.exception("connector pool shutdown failed")
    # F5 L2: stop the OAuth pending-flow TTL sweep task. Runs AFTER the
    # MCP pool drain so any in-flight OAuth refreshes triggered by
    # pool teardown can complete first.
    from the_one.mcp.oauth import stop_periodic_sweep

    try:
        await stop_periodic_sweep()
    except Exception:
        logger.exception("OAuth periodic sweep shutdown failed")
    # M10 F8 L4: release the module-level factory reference so post-
    # shutdown ``get_factory()`` reads return None. Defensive — not
    # strictly required for correctness because the process is exiting,
    # but symmetric with the startup ``set_factory`` call and keeps
    # subsequent tests from observing a stale slot.
    _set_module_factory(None)
    await close_connection()


app = FastAPI(title="GleepGlorp AI", lifespan=lifespan)
# Origin allowlist must be registered BEFORE other middleware/routes so it
# intercepts WebSocket upgrades before the `/ws` route handler can call
# `ws.accept()` (Depends() runs after accept and is too late). See
# the_one/interfaces/web/middleware.py for the matching/closing semantics.
app.add_middleware(
    OriginAllowlistMiddleware,
    allowlist=build_default_allowlist(settings.host, settings.port),
)
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
    # M10 F05 L04: connector-attached sessions carry the platform
    # string ("stub", "discord", "slack", …) populated from
    # ChatSession.platform at restore time. Web-native sessions
    # carry None. The storage-edge shim in _process_and_broadcast
    # reads this field to gate operator-visibility tagging.
    platform: str | None = None

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

# Set of in-flight per-message processing tasks spawned by the WebSocket
# handler. Tracked so FastAPI's lifespan teardown can cancel them on
# shutdown (otherwise a `make rebuild` mid-tool-call would leave a
# detached coroutine). Tasks self-discard on completion via `add_done_callback`.
_inflight_tasks: set[asyncio.Task] = set()

# F5 L3: tasks driving ``_resume_paused_session`` after the OAuth-callback
# route resolves a paused agent. Tracked separately from ``_inflight_tasks``
# so the lifespan teardown can drain both in one pass; the OAuth-callback
# route adds tasks here via ``asyncio.create_task``.
_inflight_resume_tasks: set[asyncio.Task] = set()


async def _spawn_message_processing(
    session: Session,
    user_input: str,
    source: str,
    exclude_user_echo: WebSocket | None,
) -> None:
    """Run `_process_and_broadcast` under the session's lock.

    Wrapper used by the WebSocket handler so the receive loop is not
    blocked while the agent's tool calls run. The session lock prevents
    two messages on the same session from racing on `agent.messages`;
    a second message waits politely. Errors are caught and broadcast to
    the session's subscribers as a `system` event so the user sees them
    instead of silently dropping into a crashed task.
    """
    async with session_locks[session.id]:
        # F5 L5: bind the current chat_session_id into the per-task
        # ContextVar so any pool-spawned MCP OAuth provider construction
        # below (via ``_entry_worker`` → ``build_oauth_provider_for_source``)
        # can route ``auth_required`` broadcasts back to THIS session.
        token = current_chat_session_id.set(session.id)
        try:
            await _process_and_broadcast(
                session, user_input, source=source, exclude_user_echo=exclude_user_echo
            )
        except asyncio.CancelledError:
            # Lifespan-shutdown cancellation; let it propagate so the task
            # cleanup observes the cancel.
            raise
        except Exception:
            logger.exception("session %s processing failed", session.id)
            with contextlib.suppress(Exception):
                await _send_to_session(
                    session,
                    {
                        "type": "system",
                        "content": "An error occurred while processing your message.",
                    },
                )
        finally:
            current_chat_session_id.reset(token)


# ── Session health classification ────────────────────────────────────────

SESSION_STATUS_OK = "ok"
SESSION_STATUS_NOT_FOUND = "not_found"
SESSION_STATUS_AGENT_DELETED = "agent_deleted"
SESSION_STATUS_PROVIDER_MISSING = "provider_missing"


@dataclass
class RestoredSession:
    """Result of attempting to restore a session, with health classification.

    For ok-cache hits, db_session is None (we don't re-query the DB).
    For degraded states (agent_deleted, provider_missing), session is None
    and db_session carries the row so the caller can render history.
    """

    session: Session | None
    status: str
    db_session: ChatSessionModel | None = None

    @property
    def is_degraded(self) -> bool:
        return self.status in (
            SESSION_STATUS_AGENT_DELETED,
            SESSION_STATUS_PROVIDER_MISSING,
        )


# ── DB helpers ────────────────────────────────────────────────────────────


async def _chat_repo() -> ChatSessionRepository:
    conn = await get_connection()
    return ChatSessionRepository(conn)


async def _pending_approval_repo() -> PendingApprovalRepository:
    """M11 F9 L4 — app.py-local PendingApproval repository factory.

    Mirrors ``_chat_repo`` (line above). ``api.py:86`` ships its own copy
    for the L3 approve/dismiss endpoints; both call the same
    ``PendingApprovalRepository(conn)`` shape and operate against the
    same singleton ``get_connection()``. The two factories are
    intentionally independent — app.py and api.py do not share local
    factory scope. See leg-04 Sub-step B.
    """
    conn = await get_connection()
    return PendingApprovalRepository(conn)


async def _merge_pending_approvals_into_history(
    ui_events: list[dict[str, Any]],
    db_session: ChatSessionModel,
) -> list[dict[str, Any]]:
    """M11 F9 L4 — merge pending-approval rows into the history stream.

    Shared by ``_restore_session`` (healthy path) and
    ``_build_session_joined_degraded`` (degraded path). Sessions without
    connector context (``connector_id is None or peer_id is None``)
    short-circuit — no DB query, return ``ui_events`` unchanged.

    Merge ordering is by sort-key
    ``(e.get("ts") or e.get("received_at") or "")`` ascending. Messages
    use ``ts`` (live broadcast) or are missing it entirely (replay rows
    decoded by ``messages_to_ui_events``); pending-approvals use
    ``received_at``. ISO8601 strings sort lexicographically. Messages
    without an explicit ts float to the top — acceptable per leg spec.
    """
    if db_session.connector_id is None or db_session.peer_id is None:
        return ui_events
    pending_repo = await _pending_approval_repo()
    pending_rows = await pending_repo.list_for_account_peer(
        db_session.connector_id, db_session.peer_id
    )
    if not pending_rows:
        return ui_events
    pending_events = pending_approvals_to_ui_events(pending_rows)
    combined = ui_events + pending_events
    combined.sort(
        key=lambda e: e.get("ts") or e.get("received_at") or ""
    )
    return combined


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


async def _restore_session(session_id: str) -> RestoredSession:
    """Load a session from DB and (re)build the Agent from CURRENT config.

    Health is re-evaluated on every call. If a Session is already cached for
    this id, the existing object is updated in place — preserving identity —
    but its `.agent` is replaced with a freshly-constructed one
    from the current agent_config row. This way edits to system_prompt, model,
    or tools propagate at the next join, and deletions surface as agent_deleted
    on the next join.

    Subscriber preservation is implicit: the WS subscriber registry lives in
    ``the_one.sessions`` and is keyed by session id, so a refresh of the
    cached ``Session`` dataclass does not perturb the subscriber set.

    Degraded states (agent_deleted, provider_missing) drop the entry from the
    cache so the next successful join starts clean.
    """
    try:
        repo = await _chat_repo()
        db_session = await repo.get(session_id)
    except KeyError:
        # If we had a cached session for this id, drop it — the row is gone.
        _sessions.pop(session_id, None)
        return RestoredSession(None, SESSION_STATUS_NOT_FOUND, None)

    # If a message is actively being processed on this session, skip the
    # rebuild: the in-memory `Session.agent`/`history` are mid-mutation by
    # the spawned task, and the DB snapshot is stale (the user's message
    # and any in-flight assistant chunks haven't been persisted yet).
    # Replacing history with the empty DB snapshot would render the chat
    # blank on rejoin (bug surfaced post-F4 HAT). The "rebind agent for
    # config edits" property of restore is intentionally suspended for the
    # duration of the in-flight turn — the next join after the turn
    # completes will pick up any config edits as before.
    cached = _sessions.get(session_id)
    if cached is not None and is_session_processing(session_id):
        return RestoredSession(cached, SESSION_STATUS_OK, db_session)

    factory = _get_factory()
    agent_name_for_factory = db_session.agent_name or "default"
    try:
        agent = await factory.create(agent_name_for_factory)
    except ProviderNotFoundError as exc:
        logger.warning(
            "Session %s degraded: status=provider_missing agent=%r exc=%s",
            session_id,
            db_session.agent_name,
            exc,
        )
        _sessions.pop(session_id, None)
        return RestoredSession(None, SESSION_STATUS_PROVIDER_MISSING, db_session)
    except ProviderNotConfiguredError as exc:
        logger.warning(
            "Session %s degraded: status=provider_missing agent=%r exc=%s",
            session_id,
            db_session.agent_name,
            exc,
        )
        _sessions.pop(session_id, None)
        return RestoredSession(None, SESSION_STATUS_PROVIDER_MISSING, db_session)
    except AgentNotFoundError as exc:
        logger.warning(
            "Session %s degraded: status=agent_deleted agent=%r exc=%s",
            session_id,
            db_session.agent_name,
            exc,
        )
        _sessions.pop(session_id, None)
        return RestoredSession(None, SESSION_STATUS_AGENT_DELETED, db_session)

    messages = decode_messages(db_session.messages)
    if messages:
        # Keep the freshly-built Agent's system message (reflects current
        # agent_config); append only the non-system messages from the DB.
        # Without this, the persisted-at-session-creation system prompt
        # would clobber the freshly-built one and edits to the system
        # prompt in Studio would never take effect.
        non_system = [m for m in messages if m.role != Role.SYSTEM]
        agent.messages = agent.messages[:1] + non_system
    ui_events = messages_to_ui_events(messages)

    # M11 F9 L4: merge any pending-approval rows for this connector-keyed
    # session into the history stream so the operator sees pending banners
    # on rejoin. Sessions without connector context (operator-typed) get
    # no DB query.
    ui_events = await _merge_pending_approvals_into_history(
        ui_events, db_session
    )

    if session_id in _sessions:
        # Update existing Session in place — keeps identity. Subscribers
        # live in the neutral session registry keyed by session id, so
        # the in-place update preserves the subscriber set implicitly.
        existing = _sessions[session_id]
        existing.agent = agent
        existing.title = db_session.title
        existing.agent_name = db_session.agent_name
        existing.history = ui_events
        # M10 F05 L04: refresh the cached platform field from the DB row
        # so connector-attachment state stays in sync with the persisted
        # truth across rejoins. Drives the WS storage-edge shim gate in
        # ``_process_and_broadcast`` + ``_resume_paused_session``.
        existing.platform = db_session.platform
        return RestoredSession(existing, SESSION_STATUS_OK, db_session)

    session = Session(
        id=session_id,
        agent=agent,
        created=db_session.created_at,
        title=db_session.title,
        agent_name=db_session.agent_name,
        history=ui_events,
        # M10 F05 L04: surface the persisted connector-attachment state to
        # the in-memory Session so the WS storage-edge shim can gate on it.
        platform=db_session.platform,
    )
    _sessions[session_id] = session
    return RestoredSession(session, SESSION_STATUS_OK, db_session)


async def _get_or_restore_session(session_id: str) -> RestoredSession:
    """Always rebuild via _restore_session.

    Earlier versions short-circuited to the in-memory cache, which froze the
    Agent at restore time and meant edits to the agent config (system_prompt,
    model, tools) and agent deletions did not propagate until process restart.
    Now every join rebinds the cached Session's `.agent` to the current config.
    """
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
        updated = db_session.model_copy(
            update={
                "title": session.title,
                "messages": encoded,
            }
        )
        await repo.update(updated)
    except Exception:
        logger.warning("Failed to save session %s to DB", session.id, exc_info=True)


def _session_to_list_payload(s: ChatSessionModel) -> dict[str, Any]:
    """Project a ChatSession DB row into the `session_list` per-row payload.

    M10 F05 L01: extended beyond the pre-F5 five-field projection to include
    the six connector-keying fields already on `ChatSession`. All six default
    `None` for non-connector (web-native) sessions, so pre-F5 clients ignoring
    the new fields keep working byte-identically. `session_metadata` is
    intentionally NOT projected — it's free-form dict content with no F5
    consumer and may carry sensitive routing data we shouldn't expose
    unfiltered.
    """
    return {
        "id": s.id,
        "title": s.title,
        "agent_name": s.agent_name,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "platform": s.platform,
        "connector_id": s.connector_id,
        "channel_id": s.channel_id,
        "thread_id": s.thread_id,
        "peer_id": s.peer_id,
        "last_inbound_at": s.last_inbound_at,
    }


def _build_session_joined_ok(session: Session) -> dict[str, Any]:
    """Build a session_joined payload for a healthy in-memory session.

    `is_processing` reflects whether a turn is currently in flight on
    this session — the client uses it to size the send-button enabled
    state and the thinking indicator on rejoin (otherwise switching
    away from an in-flight session and back leaves the UI's per-WS
    busy flag stale).
    """
    is_processing = is_session_processing(session.id)
    return {
        "type": "session_joined",
        "session_id": session.id,
        "status": SESSION_STATUS_OK,
        "title": session.title,
        "agent_name": session.agent_name,
        "history": session.history,
        "is_processing": is_processing,
    }


async def _build_session_joined_degraded(restored: RestoredSession) -> dict[str, Any]:
    """Build a session_joined payload for a degraded (agent_deleted/provider_missing) session.

    History is decoded from the DB row directly — there is no in-memory
    Session for degraded states.

    M11 F9 L4: merges pending-approval banners into the replay history
    via ``_merge_pending_approvals_into_history`` (same shape as the
    healthy path in ``_restore_session``). Now ``async`` because the
    merge does a DB query; degraded path is reached from an async WS
    handler so the await is structurally safe.
    """
    db = restored.db_session
    assert db is not None, "degraded RestoredSession must carry db_session"
    ui_events = messages_to_ui_events(decode_messages(db.messages))
    ui_events = await _merge_pending_approvals_into_history(ui_events, db)
    return {
        "type": "session_joined",
        "session_id": db.id,
        "status": restored.status,
        "title": db.title,
        "agent_name": db.agent_name,
        "history": ui_events,
    }


async def _send_to_session(
    session: Session,
    payload: dict[str, Any],
    exclude: WebSocket | None = None,
) -> None:
    """Send a JSON payload to all websocket subscribers of a session."""
    dead: list[WebSocket] = []
    for ws in subscribers_for(session.id):
        if ws is exclude:
            continue
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        remove_subscriber(session.id, ws)


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
        await _send_to_session(session, {"type": "system", "content": "Loading model..."})
        await ollama_api.load_model(provider_config.base_url, model_name)
        await _send_to_session(session, {"type": "system", "content": "Model loaded."})

    except Exception:
        logger.warning(
            "Auto-load check failed for session %s",
            session.id,
            exc_info=True,
        )


def _parent_message_id_for(session: "Session", msg_index: int) -> str:
    """Stable structural id for the assistant Message at agent.messages[msg_index].

    F5 L02: used as the ``parent_message_id`` discriminator on
    ``tool_call`` / ``tool_result`` / ``auth_required`` events so the
    frontend (L03) can group all tool activity for a single assistant
    turn under a per-turn trace shell.

    Structural, NOT identity-bearing: the id encodes WHICH assistant
    turn owns the activity, not a persistent record id. Rejoining a
    session from DB regenerates ids deterministically from the same
    ``agent.messages`` order. The codec replay path uses an analogous
    ``"replay-msg-N"`` namespace prefix; namespaces are disjoint by
    design (live broadcast vs replay) so the frontend's opaque-key
    grouping cannot falsely merge them.
    """
    return f"{session.id}-msg-{msg_index}"


def _find_parent_assistant_index(messages: list[Message]) -> int:
    """Walk backwards to find the index of the most recent Role.ASSISTANT message with tool_calls.

    F5 L02: used by ``_broadcast_one`` (resume path) and
    ``_send_pause_snapshot_if_needed`` to derive the
    ``parent_message_id`` for a tool message when the caller hasn't
    pre-computed one. Returns -1 if no assistant message with
    tool_calls exists in the list.
    """
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m.role == Role.ASSISTANT and m.tool_calls:
            return i
    return -1


def _auth_required_event_from_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Build the ``auth_required`` WebSocket event payload from ``ToolResult.metadata``.

    Used by ``_broadcast_one`` (lazy-path step + resume) and the
    WebSocket reconnect snapshot. Field set must match L2's
    ``redirect_handler`` payload in
    ``the_one/mcp/oauth/handlers.py`` — they share the UI consumer.

    F5 L3 cross-leg seam (cycle-1 D10): the lazy path MAY emit
    ``consent_url=None`` because the SDK flow has not yet constructed
    the authorize URL when the pause fires. The chat UI renders a
    "Login required" button on the first event; clicking it triggers
    L4's SDK flow, which routes through L2's ``redirect_handler`` and
    broadcasts a SECOND ``auth_required`` event with the real
    ``consent_url``. The UI uses the second event's URL to open the
    consent tab. L4 + L5 lock the trigger mechanism (likely a new POST
    endpoint owned by L4).
    """
    return {
        "type": "auth_required",
        "source_id": meta.get("source_id"),
        "source_name": meta.get("source_name"),
        "resource_metadata_url": meta.get("resource_metadata_url"),
        "tool_call_id": meta.get("tool_call_id"),
        "consent_url": meta.get("consent_url"),  # MAY be None on lazy path
    }


def _is_auth_required_pause(msg: Message) -> bool:
    """Return True if a yielded message is the auth_required pause surface."""
    return bool(
        msg.role == Role.TOOL
        and msg.tool_result is not None
        and msg.tool_result.metadata
        and msg.tool_result.metadata.get("is_auth_required")
    )


async def _broadcast_one(
    session: Session,
    msg: Message,
    source: str = "step",
    chunks_seen: bool = False,
) -> None:
    """Translate a single yielded ``Message`` to its WebSocket event(s).

    Used by both ``_process_and_broadcast`` (step path) and
    ``_resume_paused_session`` (resume path). For the auth_required
    pause surface, broadcasts the ``auth_required`` event INSTEAD of
    ``tool_result``; callers must check ``_is_auth_required_pause(msg)``
    after invoking this helper to decide whether to skip the trailing
    ``done`` event.

    ``chunks_seen``: assistant-streaming flag from the caller. When
    True (chunks already fanned out via ``assistant_chunk``), the
    legacy ``assistant`` event is suppressed to avoid a duplicate
    render in the chat UI.

    ``source``: included in the user event for chat-UI provenance
    (only forwarded into the user echo by ``_process_and_broadcast``;
    ``_broadcast_one`` itself only handles assistant + tool messages).
    """
    # F5 L02: resolve parent_message_id for any tool_call/tool_result on
    # this msg. For ASSISTANT messages with tool_calls: the parent is THIS
    # message (just-yielded → agent.messages[-1] per the append-before-yield
    # invariant in the_one/agent/core.py:195-196). For TOOL messages: walk
    # agent.messages backwards for the most recent ASSISTANT with tool_calls.
    parent_idx: int = -1
    if msg.role == Role.ASSISTANT and msg.tool_calls:
        parent_idx = len(session.agent.messages) - 1
    elif msg.role == Role.TOOL and msg.tool_result is not None:
        parent_idx = _find_parent_assistant_index(session.agent.messages)
    parent_id: str | None = _parent_message_id_for(session, parent_idx) if parent_idx >= 0 else None

    if msg.role == Role.ASSISTANT:
        if msg.usage:
            usage_event = {
                "type": "usage",
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
                "context_tokens": msg.usage.input_tokens,
                "max_context_tokens": session.agent.llm.max_context_tokens,
            }
            await _send_to_session(session, usage_event)

        if msg.content:
            event: dict[str, Any] = {"type": "assistant", "content": msg.content}
            session.add_event(event)
            if not chunks_seen:
                await _send_to_session(session, event)
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tc_event = {
                    "type": "tool_call",
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "parent_message_id": parent_id,
                    "tool_call_id": tc.id,
                }
                session.add_event(tc_event)
                await _send_to_session(session, tc_event)

    elif msg.role == Role.TOOL and msg.tool_result is not None:
        meta = msg.tool_result.metadata
        if meta and meta.get("is_auth_required"):
            # F5 L3: pause path — broadcast ``auth_required`` INSTEAD of
            # ``tool_result``. Caller is responsible for skipping the
            # trailing ``done`` event (the step is paused, not finished).
            # F5 L02: inject parent_message_id (Option A — caller-side
            # injection keeps the helper signature stable; the discriminator
            # is caller context, not part of ToolResult.metadata).
            event = _auth_required_event_from_metadata(meta)
            event["parent_message_id"] = parent_id
            await _send_to_session(session, event)
            return
        tr_event = {
            "type": "tool_result",
            "content": truncate_for_event(msg.tool_result.content),
            "is_error": msg.tool_result.is_error,
            "parent_message_id": parent_id,
            "tool_call_id": msg.tool_result.tool_call_id,
        }
        session.add_event(tr_event)
        await _send_to_session(session, tr_event)


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
    user_event: dict[str, Any] = {"type": "user", "content": user_input, "source": source}
    # M10 F06 L6: close the F5 live-broadcast carry-forward. The
    # operator-typed message on a connector-attached session must
    # carry the visibility tag at LIVE broadcast time (the refresh
    # path's post-step Message-level tagging at L997-1004 handles
    # the persistence side; this site handles the live side). Mirrors
    # the codec's projection rule at db/codec.py:173-176 — only emit
    # the key when the value is meaningful. The session_locks[session.id]
    # at L258 serializes against connectors/_inbound.py:155's
    # dispatch_inbound, so there is no race.
    #
    # M11 F06 L03: this path does NOT acquire a ``peer_name`` key — the
    # operator IS the source; there is no peer to attribute. Peer-
    # attributed user events flow via the dispatcher path
    # (connectors/_inbound.py) where the codec spreads ``peer_name``
    # from the ``Message.peer_name`` field at projection time.
    if session.platform is not None:
        user_event["visibility"] = OPERATOR_VISIBILITY
    session.add_event(user_event)
    await _send_to_session(session, user_event, exclude=exclude_user_echo)

    total_input = 0
    total_output = 0
    last_input = 0
    # M08 F6.5 L04 HAT fix: do NOT capture max_context_tokens here. The
    # L01 lazy resolver runs at the top of the FIRST `complete()` /
    # `stream()` call, which `agent.step()` triggers below. Reading the
    # attribute live at usage-event emission (line ~793) picks up the
    # resolved value on the first turn instead of the class default.
    # Pinned by tests/test_process_and_broadcast_live_read.py (M08 F7 L05).

    result_messages: list[dict[str, Any]] = []
    # Streaming wire-up: chunks fan out via WS as `assistant_chunk` events.
    # `chunks_seen` is a per-iteration flag that distinguishes the streaming
    # path (chunks were broadcast → the client already has the text → skip
    # the legacy `assistant` event) from the direct-action shortcut path
    # (no chunks → broadcast the legacy `assistant` event so the client
    # still renders). Reset UNCONDITIONALLY at the end of each Role.ASSISTANT
    # block so iteration N+1 starts clean (multi-iteration agent loops).
    chunks_seen = False
    paused = False
    # F5 L02: per-turn discriminator. Set when an ASSISTANT message with
    # tool_calls arrives; reused for the subsequent Role.TOOL messages
    # (including the auth_required pause path) until the next assistant
    # turn arrives. Depends on the agent/core.py:195-196, 250-251
    # append-before-yield + assistant-before-tools iteration invariant.
    current_turn_parent_id: str | None = None

    async def _broadcast_chunk(content: str) -> None:
        nonlocal chunks_seen
        chunks_seen = True
        await _send_to_session(session, {"type": "assistant_chunk", "content": content})

    async def _broadcast_usage(usage: Any) -> None:
        # F7 L04: interim mid-stream usage broadcast. Mirrors the final-
        # usage event shape at line ~793 (this same _process_and_broadcast)
        # but adds ``is_interim: True`` so frontend can disambiguate if it
        # cares. Frontend's updateTelemetry is last-write-wins on the
        # cumulative fields. The provider-emitted usage carries
        # CUMULATIVE output_tokens (byte-heuristic accumulator), so each
        # interim broadcast is a strictly-increasing progress indicator.
        # Not appended to session.history (projection-only event).
        interim_event = {
            "type": "usage",
            "input_tokens": total_input + usage.input_tokens,
            "output_tokens": total_output + usage.output_tokens,
            "context_tokens": last_input or usage.input_tokens,
            "max_context_tokens": session.agent.llm.max_context_tokens,
            "is_interim": True,
        }
        await _send_to_session(session, interim_event)

    # F5 L4: storage-edge shim for operator-visibility tagging.
    # On a connector-attached session, every WS-typed message is
    # operator-only by default. The agent's responses to that
    # message (and any intermediate tool calls/results) stay in
    # operator-console-only mode UNLESS the agent explicitly
    # invokes send_to_platform_channel — that tool's successful
    # tool_result is the only path to visibility=None / peer-
    # visible from this WS write path.
    pre_step_len = len(session.agent.messages)

    try:
        async for msg in session.agent.step(
            user_input,
            on_chunk=_broadcast_chunk,
            on_usage=_broadcast_usage,
        ):
            if msg.role == Role.ASSISTANT:
                if msg.usage:
                    # Per-step usage accumulators are tracked here (NOT in
                    # ``_broadcast_one``) because they are step-scoped —
                    # resume re-enters the iteration loop with a fresh
                    # ``_broadcast_one`` that emits per-iteration usage
                    # events without double-counting.
                    total_input += msg.usage.input_tokens
                    total_output += msg.usage.output_tokens
                    last_input = msg.usage.input_tokens
                    usage_event = {
                        "type": "usage",
                        "input_tokens": total_input,
                        "output_tokens": total_output,
                        "context_tokens": last_input,
                        "max_context_tokens": session.agent.llm.max_context_tokens,
                    }
                    await _send_to_session(session, usage_event)

                if msg.content:
                    event: dict[str, Any] = {"type": "assistant", "content": msg.content}
                    session.add_event(event)
                    if not chunks_seen:
                        # Direct-action / non-streaming path — broadcast the
                        # legacy event so the client still renders. When chunks
                        # were broadcast, the client already has the text via
                        # the chunk path; suppress the duplicate broadcast.
                        await _send_to_session(session, event)
                if msg.tool_calls:
                    # F5 L02: project parent_message_id for this turn from
                    # the just-yielded assistant Message's index. Per the
                    # append-before-yield invariant, this is the last item
                    # in agent.messages at broadcast time.
                    current_turn_parent_id = _parent_message_id_for(
                        session, len(session.agent.messages) - 1
                    )
                    for tc in msg.tool_calls:
                        tc_event = {
                            "type": "tool_call",
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "parent_message_id": current_turn_parent_id,
                            "tool_call_id": tc.id,
                        }
                        session.add_event(tc_event)
                        await _send_to_session(session, tc_event)

                entry: dict[str, Any] = {"role": "assistant"}
                if msg.content:
                    entry["content"] = msg.content
                if msg.tool_calls:
                    entry["tool_calls"] = [
                        {"name": tc.name, "arguments": tc.arguments} for tc in msg.tool_calls
                    ]
                result_messages.append(entry)
                # UNCONDITIONAL reset at end-of-iteration. Resetting inside
                # `if msg.content:` would skip the reset on tool-call-only
                # iterations and incorrectly carry chunks_seen=True into
                # iteration N+1.
                chunks_seen = False

            elif msg.role == Role.TOOL and msg.tool_result:
                meta = msg.tool_result.metadata
                if meta and meta.get("is_auth_required"):
                    # F5 L3 pause path: broadcast ``auth_required`` INSTEAD
                    # of ``tool_result``; do NOT append to result_messages
                    # (the API caller would otherwise see a partial result
                    # set with no clear pause signal); SKIP the trailing
                    # ``done`` event below — the WS subscribers are still
                    # awaiting the auth resolution.
                    # F5 L02: inject parent_message_id (Option A) so the
                    # frontend can render the consent surface INSIDE the
                    # right trace shell.
                    event = _auth_required_event_from_metadata(meta)
                    event["parent_message_id"] = current_turn_parent_id
                    await _send_to_session(session, event)
                    paused = True
                    break
                tr_event = {
                    "type": "tool_result",
                    "content": truncate_for_event(msg.tool_result.content),
                    "is_error": msg.tool_result.is_error,
                    "parent_message_id": current_turn_parent_id,
                    "tool_call_id": msg.tool_result.tool_call_id,
                }
                session.add_event(tr_event)
                await _send_to_session(session, tr_event)
                result_messages.append(
                    {
                        "role": "tool",
                        "content": truncate_for_event(msg.tool_result.content),
                        "is_error": msg.tool_result.is_error,
                    }
                )
    except Exception as exc:
        # Surface the failure to the UI so the client can drop its "thinking…"
        # indicator and re-enable the input. Without this, an exception in
        # `agent.step` (e.g. a provider 4xx) would propagate up and crash the
        # WS handler before the closing `done` event fires.
        logger.exception("Agent step failed for session %s", session.id)
        await _send_to_session(
            session,
            {"type": "system", "content": f"Agent error: {exc}"},
        )

    # F5 L4: apply visibility tagging if this is a connector-
    # attached session. Runs whether agent.step succeeded or
    # raised — partial messages still need tagging because
    # _save_session_to_db persists whatever is in agent.messages.
    if session.platform is not None:
        tag_post_step_visibility(session.agent.messages, pre_step_len)
        # The helper SKIPS USER messages; override the WS-typed
        # operator input at pre_step_len explicitly. Bounds-checked
        # in case agent.step raised before its internal
        # Message.user(...) append landed.
        if pre_step_len < len(session.agent.messages):
            session.agent.messages[pre_step_len].visibility = OPERATOR_VISIBILITY

    # Save to DB after each complete exchange
    try:
        await _save_session_to_db(session)
    except Exception:
        logger.warning("Failed to save session %s after exchange", session.id, exc_info=True)

    if not paused:
        # F5 L3: do NOT broadcast ``done`` when paused — the chat UI is
        # still awaiting auth resolution; the resume path will broadcast
        # ``done`` after re-dispatching the deferred tool calls.
        await _send_to_session(session, {"type": "done"})
    return result_messages


async def _resume_paused_session(session: Session) -> None:
    """Drive ``Agent.resume_after_auth`` and broadcast its yielded messages.

    Called from the OAuth-callback route via ``asyncio.create_task``.
    Guarded by the caller — only invoked when the session's agent has
    ``_deferred_tool_calls != None`` — but we re-check on entry for
    race protection (cycle-1 D13: another resume may have cleared the
    state between the route's ``create_task`` and this coroutine
    actually running).

    Cycle-2 NEW-M3: ``_ensure_ollama_model_loaded`` is called before
    re-issuing LLM calls. Operator may have walked away long enough
    for Ollama to evict the model; without this, the resume's first
    ``stream()`` would hit an unloaded model and return a slow first
    chunk while the runtime spins up.
    """
    if session.agent._deferred_tool_calls is None:
        return  # race protection — another resume already cleared state

    # Operator may have been away long enough for Ollama to evict the
    # model. Re-load before resume re-enters the iteration loop.
    await _ensure_ollama_model_loaded(session)

    # F5 L4: capture pre-resume length so we can tag any
    # messages appended during resume_after_auth on a connector-
    # attached session. Mirrors the shim in
    # _process_and_broadcast — same helper, no USER override
    # (resume has no new WS-typed USER message).
    pre_resume_len = len(session.agent.messages)

    # F5 L5: bind chat_session_id for any pool / OAuth provider construction
    # the resumed tool dispatch may trigger. Symmetric with
    # ``_spawn_message_processing``'s set/reset pattern.
    csid_token = current_chat_session_id.set(session.id)
    try:
        re_paused = False
        async for msg in session.agent.resume_after_auth():
            await _broadcast_one(session, msg, source="resumed")
            if _is_auth_required_pause(msg):
                re_paused = True
                break
        if not re_paused:
            await _send_to_session(session, {"type": "done"})
    except Exception:
        logger.exception("Resume after auth failed for session %s", session.id)
        with contextlib.suppress(Exception):
            await _send_to_session(
                session,
                {
                    "type": "system",
                    "content": "Failed to resume after authentication. "
                    "Please re-trigger the action.",
                },
            )
    finally:
        current_chat_session_id.reset(csid_token)

    # F5 L4: symmetric storage-edge shim for the resume path.
    # No USER override here — resume has no new WS-typed USER message;
    # the original USER was tagged in the initial-step shim.
    if session.platform is not None:
        tag_post_step_visibility(session.agent.messages, pre_resume_len)

    # Persist the resumed exchange so re-joiners see the new messages.
    try:
        await _save_session_to_db(session)
    except Exception:
        logger.warning("Failed to save session %s after resume", session.id, exc_info=True)


async def _send_pause_snapshot_if_needed(session: Session, websocket: WebSocket) -> None:
    """Send the cached ``auth_required`` event to a NEW subscriber.

    Called immediately after ``add_subscriber(session.id, websocket)`` in
    any branch (join, new_session, auto-create). No-op if the session's
    agent has no pending pause. Existing subscribers don't receive
    duplicates because the send targets only the new websocket.

    Walks ``agent.messages`` BACKWARDS to find the last tool message
    with ``metadata.is_auth_required`` (cycle-1 D12 + suggestion: the
    agent is the single source of truth; no per-session cached field).
    The walk-backwards (NOT ``messages[-1]``) handles the case where
    additional non-tool messages were appended between the pause and
    the reconnect.
    """
    if session.agent._deferred_tool_calls is None:
        return
    # F5 L02: walk via enumerate(reversed(...)) so we preserve the
    # original first-hit-wins reverse-walk semantics while also knowing
    # the forward-index of the matched tool_msg — needed to derive the
    # parent assistant's parent_message_id from the slice of
    # agent.messages preceding the tool.
    msgs = session.agent.messages
    for rev_i, past_msg in enumerate(reversed(msgs)):
        if (
            past_msg.role == Role.TOOL
            and past_msg.tool_result is not None
            and past_msg.tool_result.metadata
            and past_msg.tool_result.metadata.get("is_auth_required")
        ):
            tool_idx = len(msgs) - 1 - rev_i
            parent_idx = _find_parent_assistant_index(msgs[:tool_idx])
            parent_id: str | None = (
                _parent_message_id_for(session, parent_idx) if parent_idx >= 0 else None
            )
            try:
                event = _auth_required_event_from_metadata(past_msg.tool_result.metadata)
                event["parent_message_id"] = parent_id
                await websocket.send_json(event)
            except (RuntimeError, WebSocketDisconnect):
                # New subscriber's WS broke before snapshot delivery —
                # nothing to clean up; the existing dead-subscriber
                # detection in ``_send_to_session`` will catch it on
                # the next broadcast.
                pass
            return


# ── Routes ───────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC_DIR / "index.html").read_text()


@app.get("/api/info")
async def info() -> dict[str, Any]:
    return {"version": __version__, "base_prompt": BASE_PROMPT}


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
        async for msg in agent.step("Read the file /app/pyproject.toml"):
            if msg.role == Role.TOOL and msg.tool_result and not msg.tool_result.is_error:
                got_tool_result = True
        detail = "read_file executed" if got_tool_result else "no tool result"
        checks.append(
            {
                "name": "tool_use",
                "pass": got_tool_result,
                "detail": detail,
            }
        )
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
        restored = await _get_or_restore_session(session_id)
        if restored.is_degraded:
            return {"error": f"session_{restored.status}"}
        session = restored.session  # None for not_found, real Session for ok
    if session is None:
        try:
            session = await _create_session(
                agent_name=agent_name, source=source, session_id=session_id
            )
        except (ValueError, KeyError) as exc:
            return {"error": f"Cannot start chat: {exc}"}

    if user_input == "/reset":
        session.agent.reset()
        session.history.clear()
        session.title = "New chat"
        await _send_to_session(session, {"type": "system", "content": "Context cleared."})
        await _save_session_to_db(session)
        return {
            "session_id": session.id,
            "messages": [{"role": "system", "content": "Context cleared."}],
        }

    result = await _process_and_broadcast(session, user_input, source=source)
    return {"session_id": session.id, "messages": result}


@app.post("/api/chat/reset")
async def chat_reset(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type")
    payload = await request.json() if content_type == "application/json" else {}
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
                    # Leave any prior session before joining a new one.
                    # Without this, broadcasts to the old session (e.g. an
                    # in-flight "Loading model..." or assistant message)
                    # surface in the new session's UI after a switch.
                    if session and session.id != session_id:
                        remove_subscriber(session.id, ws)
                    restored = await _get_or_restore_session(session_id)
                    if restored.status == SESSION_STATUS_OK:
                        # `session` here is the WS-loop-scoped variable;
                        # restored.session is the dataclass field.
                        session = restored.session
                        assert session is not None
                        if ws not in subscribers_for(session.id):
                            add_subscriber(session.id, ws)
                        await ws.send_json(_build_session_joined_ok(session))
                        # F5 L3: replay a cached auth_required event to
                        # the new subscriber if the session is paused.
                        await _send_pause_snapshot_if_needed(session, ws)
                        continue
                    if restored.is_degraded:
                        # Don't operate on a degraded session in this connection.
                        session = None
                        await ws.send_json(await _build_session_joined_degraded(restored))
                        continue
                    # status == not_found → fall through to auto-create below.
                elif session is not None:
                    # No session_id supplied AND outer session is already bound —
                    # preserve today's idempotent re-bind behavior.
                    if ws not in subscribers_for(session.id):
                        add_subscriber(session.id, ws)
                    await ws.send_json(_build_session_joined_ok(session))
                    # F5 L3: replay a cached auth_required event on
                    # idempotent re-bind too.
                    await _send_pause_snapshot_if_needed(session, ws)
                    continue
                # else: no session_id AND no outer session → auto-create below.

                # Auto-create: either no session_id was supplied AND no outer
                # session, or the supplied session_id was not_found.
                try:
                    session = await _create_session()
                except (ValueError, KeyError) as exc:
                    await ws.send_json({"type": "system", "content": f"Cannot start chat: {exc}"})
                    continue
                if ws not in subscribers_for(session.id):
                    add_subscriber(session.id, ws)
                await ws.send_json(_build_session_joined_ok(session))
                # F5 L3: brand-new session has no pause state — the helper
                # is a no-op here, included for code-pattern consistency.
                await _send_pause_snapshot_if_needed(session, ws)
                continue

            if action == "list_sessions":
                try:
                    repo = await _chat_repo()
                    db_sessions = await repo.list()
                    sessions_list = [_session_to_list_payload(s) for s in db_sessions]
                except Exception:
                    logger.warning("Failed to list sessions from DB", exc_info=True)
                    sessions_list = []
                await ws.send_json(
                    {
                        "type": "session_list",
                        "sessions": sessions_list,
                    }
                )
                continue

            if action == "new_session":
                # Leave current session
                if session:
                    remove_subscriber(session.id, ws)
                agent_name = payload.get("agent_name")
                try:
                    session = await _create_session(agent_name=agent_name)
                except (ValueError, KeyError) as exc:
                    await ws.send_json({"type": "system", "content": f"Cannot start chat: {exc}"})
                    continue
                add_subscriber(session.id, ws)
                await ws.send_json(_build_session_joined_ok(session))
                # F5 L3: brand-new session — no-op, included for code-
                # pattern consistency.
                await _send_pause_snapshot_if_needed(session, ws)
                continue

            if action == "delete_session":
                sid = payload.get("session_id")
                if sid:
                    # Remove from memory
                    if sid in _sessions:
                        if session and session.id == sid:
                            remove_subscriber(session.id, ws)
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
                try:
                    session = await _create_session()
                except (ValueError, KeyError) as exc:
                    await ws.send_json({"type": "system", "content": f"Cannot start chat: {exc}"})
                    continue
                add_subscriber(session.id, ws)
                await ws.send_json(_build_session_joined_ok(session))
                # F5 L3: brand-new session — no-op, included for code-
                # pattern consistency.
                await _send_pause_snapshot_if_needed(session, ws)

            if user_input == "/reset":
                session.agent.reset()
                session.history.clear()
                session.title = "New chat"
                await _send_to_session(session, {"type": "system", "content": "Context cleared."})
                await _save_session_to_db(session)
                continue

            # Process message in a background task so the WebSocket receive
            # loop stays responsive — switching conversations, listing
            # sessions, etc. should not block on a long agent tool call
            # (e.g. a `sleep 200` clipped to 120s by the F4 timeout cap).
            # The shared per-session lock (from ``the_one.sessions``)
            # serializes successive messages on the same session;
            # broadcasts go to all current subscribers.
            task = asyncio.create_task(_spawn_message_processing(session, user_input, "web", ws))
            _inflight_tasks.add(task)
            task.add_done_callback(_inflight_tasks.discard)

    except WebSocketDisconnect:
        if session:
            remove_subscriber(session.id, ws)
