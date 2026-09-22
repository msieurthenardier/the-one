from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import the_one.retention as retention
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
)
from the_one.agent.factory import (
    set_factory as _set_module_factory,
)
from the_one.api_credential import IdentifiedCaller, resolve_caller
from the_one.config import settings
from the_one.connectors.manager import ConnectorManager
from the_one.connectors.manager import set_manager as _set_module_connector_manager
from the_one.db import close_connection, init_db
from the_one.db.codec import (
    decode_messages,
    encode_messages,
    messages_to_ui_events,
    thinking_display_text,
    truncate_for_event,
)
from the_one.db.connection import get_connection
from the_one.db.key_reconcile import reconcile_pending_key
from the_one.db.migration import migrate_json_to_sqlite
from the_one.db.models import ChatSession as ChatSessionModel
from the_one.db.repositories import (
    AgentExternalCredentialRepository,
    ChatSessionRepository,
    ConnectorRepository,
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
)
from the_one.embeddings import schedule_warm_up as _schedule_embedding_warm_up
from the_one.encryption import get_encryptor
from the_one.interfaces.web.api import router as api_router
from the_one.interfaces.web.handoff_store import HANDOFF_QUERY_PARAM, mint_handoff_credential
from the_one.interfaces.web.middleware import (
    LIVENESS_PATH,
    CredentialGateMiddleware,
    OriginAllowlistMiddleware,
    build_default_allowlist,
)
from the_one.knowledge.manager import IndexingManager
from the_one.knowledge.manager import set_manager as _set_module_indexing_manager
from the_one.knowledge.watcher import WatchManager
from the_one.knowledge.watcher import set_manager as _set_module_watch_manager
from the_one.llm.base import (
    OPERATOR_VISIBILITY,
    ContentBlock,
    ImageContent,
    Message,
    Role,
    TextContent,
    content_to_text,
    tag_post_step_visibility,
)
from the_one.mcp import shutdown_drain as _mcp_pool_shutdown_drain
from the_one.self_configuration import external_credentials as _self_configuration_external
from the_one.self_configuration import manage as _self_configuration_manage
from the_one.self_configuration import pending as _self_configuration_pending
from the_one.self_configuration import surface as _self_configuration_surface
from the_one.self_configuration.constants import MOUNT_PATH as _SELF_CONFIGURATION_MOUNT_PATH
from the_one.self_configuration.credentials import register_credential_source_once
from the_one.sessions import (
    add_subscriber,
    is_session_processing,
    remove_subscriber,
    session_locks,
    subscribers_for,
)
from the_one.tools._session_registry import shutdown_drain as _session_registry_shutdown_drain
from the_one.vectors import close_vector_store

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# Matches ``src="/static/….js"`` / ``href="/static/….css"`` references so the
# index HTML can be version-scoped for cache-busting. Group ``pre`` is the
# attribute up to (and including) the asset path; group ``q`` captures any
# pre-existing query string (none today, but guarded per the leg spec).
_STATIC_ASSET_REF_RE = re.compile(r'((?:src|href)="/static/[^"]*?\.(?:js|css))(\?[^"]*)?"')


@functools.lru_cache(maxsize=1)
def _cache_busted_index_html() -> str:
    """Return ``index.html`` with ``?v={__version__}`` on every ``/static``
    JS/CSS reference.

    The version is fixed per process, so the rewrite is computed once and
    memoized. The rewrite is server-side only — ``index.html`` on disk is never
    modified. Non-``/static`` URLs and non-js/css references are left untouched.
    """
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    def _append_version(match: re.Match[str]) -> str:
        pre, existing_query = match.group(1), match.group(2)
        if existing_query:
            # Ref already carries a query string — extend it rather than
            # producing an invalid ``?x?v=``.
            return f'{pre}{existing_query}&v={__version__}"'
        return f'{pre}?v={__version__}"'

    return _STATIC_ASSET_REF_RE.sub(_append_version, html)


# ── Lifespan ──────────────────────────────────────────────────────────────

# M21 F01 L02: guards `session_manager.run()` to at most once per process —
# see `_self_configuration_session_scope` docstring below.
_self_configuration_session_manager_started = False


@asynccontextmanager
async def _self_configuration_session_scope() -> AsyncIterator[None]:
    """Wrap `session_manager.run()` around the caller's body EXACTLY ONCE
    per process (LD4 / probe constraint 1: the SDK's
    `StreamableHTTPSessionManager.run()` raises `RuntimeError` if called a
    second time on the same instance — "can only be called once per
    instance").

    A real server process enters `lifespan` exactly once, so this guard is
    a no-op there. It matters for the test suite: hundreds of existing
    tests instantiate `TestClient(app)` against the same process-wide
    `app` singleton, each cycling `lifespan` start/stop — without this
    guard, the SECOND such cycle in a pytest process would raise and break
    every test that runs after the first. Later cycles skip the wrap (no
    self-configuration serving on that cycle); a test that specifically
    needs the surface actually serving spins up its own fresh OS process
    (`tests/test_self_configuration_surface.py`, mirroring the existing
    browser-test/AIAT convention of a per-test uvicorn subprocess) rather
    than reusing this in-process singleton after other tests have already
    cycled it.
    """
    global _self_configuration_session_manager_started
    if _self_configuration_session_manager_started:
        yield
        return
    _self_configuration_session_manager_started = True
    async with _self_configuration_surface.mcp.session_manager.run():
        yield


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize DB on startup, close on shutdown."""
    from the_one.logging_config import configure_logging

    configure_logging()
    # M21 F01 L02 / LD4 / probe constraint 1: the mounted self-configuration
    # sub-app's lifespan never runs on its own — wrap its session_manager
    # around the WHOLE existing lifespan body (startup through shutdown).
    # `session_manager` is created lazily by `streamable_http_app()`, called
    # at module load when the sub-app is mounted below (before this function
    # ever runs); `.run()` is once-per-instance, so this `async with` must
    # wrap the entire body, not just the yield point. See
    # `_self_configuration_session_scope` for the test-suite-driven guard.
    async with _self_configuration_session_scope():
        logger.info("the-one starting; log_level=%s", settings.log_level)
        # M14 F4 L7: prune orphaned box scratch dirs before any sessions start.
        # Every child of data_dir/"boxes"/ is an orphan from a prior ungraceful exit
        # (SIGKILL/OOM) — this process has no live boxed sessions yet. Single-process
        # assumption applies; concurrent web+CLI sharing the same data_dir is unsupported.
        from the_one.tools.execution import prune_box_scratch

        prune_box_scratch()
        await init_db()
        conn = await get_connection()
        # Reconcile a leftover rotation sidecar (encryption.key.next) before any
        # encryptor-backed repository is constructed below — repositories hold
        # the encryptor by reference, and this mutates it in place
        # (`install_key` / `discard_pending_key`), so the ordering is what
        # makes the by-reference propagation sufficient. See flight Design
        # Decision Q1 / `the_one.db.key_reconcile`.
        _reconcile_outcome = await reconcile_pending_key(conn, get_encryptor(settings.data_dir))
        if _reconcile_outcome != "absent":
            logger.info("encryption key sidecar reconciled at startup: %s", _reconcile_outcome)
        store = SQLiteAgentStore(conn)
        await migrate_json_to_sqlite(store)
        # M21 F01 L02: register the self-configuration credential source behind
        # the Mission 20 gate seam, then reconcile every marked MCP-source row
        # against the CURRENT settings.port (LD3) and load their credentials
        # into the in-memory registry (LD2) — must run before any request can
        # reach the mounted surface below. M21 F01 L03 (LD7): reconcile also
        # refreshes `_cache.tools` unconditionally and renames any legacy-
        # template row to the constant name, migrating its owner's
        # `mcp_overrides` key along with it — needs `store` for that.
        register_credential_source_once()
        _self_configuration_mcp_repo = MCPSourceRepository(conn, get_encryptor(settings.data_dir))
        await _self_configuration_manage.reconcile_on_startup(_self_configuration_mcp_repo, store)
        # M21 F03 L01 (DD1/DD8): register the EXTERNAL credential source on the
        # same gate seam and rebuild its in-memory registry from the store —
        # a persisted `ext_` credential must resolve again after a restart
        # (DD8), and the source must re-register idempotently across the
        # `api_credential._sources` swaps test fixtures perform (DD1). Must
        # run before any request can reach the mounted surface below.
        _self_configuration_external.register_credential_source_once()
        _self_configuration_ext_repo = AgentExternalCredentialRepository(
            conn, get_encryptor(settings.data_dir)
        )
        _self_configuration_external.load_from_rows(await _self_configuration_ext_repo.load_all())
        _state["factory"] = AgentFactory(store=store)
        # M10 F8 L4: install the application factory into the module-level
        # accessor at ``the_one.agent.factory`` so the connector inbound
        # pipeline (``the_one/connectors/inbound.py::dispatch_inbound``,
        # invoked from a plugin's ``on_inbound`` callback) can resolve it
        # without changing the plugin contract — exercised today through
        # the stub plugin's test seams; Discord (Flight 3) and later
        # platforms (Flight 4) will drive the same path through a real
        # gateway listener. Teardown clears the slot below.
        _set_module_factory(_state["factory"])
        # F5 L2: start the OAuth pending-flow TTL sweep task. The
        # ``_state`` (OAuth) module is reached via the public lifespan
        # hooks ``start_periodic_sweep`` / ``stop_periodic_sweep`` — NOT
        # imported directly — to avoid shadowing this module's existing
        # ``_state: dict[str, Any]`` global at app.py:103.
        from the_one.mcp.oauth import start_periodic_sweep

        start_periodic_sweep()
        # F05 L01: start the web-session idle reaper just after the OAuth sweep.
        global _web_session_reaper_task
        _web_session_reaper_task = asyncio.create_task(_web_session_reap_loop())
        # M13 F03 L3: start the daily chat-history purge loop just after the
        # reaper start. Due-based catch-up on entry, then sleep+recheck.
        global _chat_history_purge_task
        _chat_history_purge_task = asyncio.create_task(_chat_history_purge_loop())
        # M16 F05 L02: start the daily model-catalog refresh loop just after the
        # purge-loop start. Due-based catch-up on entry, then sleep+recheck.
        global _catalog_refresh_task
        _catalog_refresh_task = asyncio.create_task(_model_catalog_refresh_loop())
        # Mission 23 Flight 2 Leg 2 (design review Q1, resolved): dual-gated
        # stub-registration startup hook — the new-gate successor to the
        # retired THE_ONE_REGISTER_STUB_CONNECTOR hook. Own guarded block,
        # entirely separate from squawk-0025's MCP evict/drain block AND
        # from the Leg 1 connector-manager start/drain hooks immediately
        # below. Without this, nothing ever registers the stub plugin in a
        # LIVE process — the leg-3 behavior test (and a Studio-created stub
        # connector on the dev instance) would have no working listener to
        # connect to. Registered BEFORE the manager's start_all below so an
        # already-persisted stub connector row finds its plugin at startup,
        # not just on the next save. Symmetric teardown lives in shutdown,
        # after the manager drain (see below).
        global _stub_connector_registered_by_hook
        _stub_connector_registered_by_hook = False
        if settings.dev_mode and os.environ.get("THE_ONE_STUB_TEST_ENDPOINT") == "1":
            from the_one.connectors import registry as _connector_registry
            from the_one.connectors.stub import StubPlugin as _StubPlugin

            _connector_registry.register_for_test("stub", _StubPlugin())
            _stub_connector_registered_by_hook = True

        # Mission 23 Flight 3 Leg 1: unconditional production Discord
        # registration — unlike the stub hook just above (dual-gated,
        # dev/test only), Discord is a real platform and always available.
        # Own guarded try/except block (a registration failure must not
        # kill app startup, mirroring the other startup blocks), separate
        # from the stub hook above and the manager start below. Registered
        # BEFORE the manager's start_all so an already-persisted Discord
        # connector row finds its plugin at startup, not just on the next
        # save. Symmetric unregistration at shutdown, mirroring the stub
        # hook's hygiene (see below).
        try:
            from the_one.connectors.discord import register as _register_discord

            _register_discord()
        except Exception:
            logger.exception("discord connector registration failed")

        # Mission 23 Flight 4 Leg 2: unconditional production Telegram
        # registration, same block pattern as Discord immediately above
        # (own guarded try/except, registered before the manager's
        # start_all, symmetric unregistration at shutdown below).
        try:
            from the_one.connectors.telegram import register as _register_telegram

            _register_telegram()
        except Exception:
            logger.exception("telegram connector registration failed")

        # Mission 23 Flight 2 Leg 1: start the connector listener manager
        # just before the yield, mirroring the OAuth-sweep/reaper/purge/
        # catalog starts above. Wrapped in its own try/except (a connector
        # startup failure must not kill app startup, mirroring the other
        # startup blocks) — squawk-0025's MCP evict/drain block below is
        # UNCHANGED by this addition; the manager's own drain is placed in
        # shutdown well clear of it (see below).
        global _connector_manager
        _connector_manager = ConnectorManager()
        try:
            _connector_encryptor = get_encryptor(settings.data_dir)
            _connector_repo = ConnectorRepository(await get_connection(), _connector_encryptor)
            await _connector_manager.start_all(_connector_repo, _connector_encryptor)
            _set_module_connector_manager(_connector_manager)
        except Exception:
            logger.exception("connector manager startup failed")

        # M24 F02 L03, DD-1: kick the embedding warm-up AFTER the connector
        # manager start above, gated on at least one knowledge base already
        # existing — an operator who never creates a KB never pays the
        # ~250 MiB model load. Own try/except (a scheduling failure must not
        # kill app startup, mirroring the other startup blocks); `warm_up()`
        # itself also never raises (it logs a loader failure internally), so
        # this only guards the `count()` read and the `create_task` call.
        # Squawk 0055: the task handle is held inside
        # ``the_one.embeddings`` (not discarded here) so it can't be
        # garbage-collected mid-flight.
        try:
            if await KnowledgeBaseRepository(await get_connection()).count() > 0:
                _schedule_embedding_warm_up()
        except Exception:
            logger.exception("embedding warm-up scheduling failed")

        # M24 F03 L03, DD-7: construct the indexing manager and publish it
        # via the module accessor BEFORE start_all runs (not after, unlike
        # the connector-manager block above) — the shutdown drain below
        # reads the local `_indexing_manager` global, not the accessor, so
        # publishing early just means a route reaching the manager mid-
        # startup sees a real (if not yet fully started) instance rather
        # than None. Own try/except around start_all only, mirroring the
        # other startup blocks (a requeue/settings-write failure must not
        # kill app startup).
        global _indexing_manager
        _indexing_manager = IndexingManager()
        _set_module_indexing_manager(_indexing_manager)
        try:
            await _indexing_manager.start_all()
        except Exception:
            logger.exception("indexing manager startup failed")

        # M24 F04 L03, DD-7: construct the watch manager and publish it via
        # the module accessor BEFORE its own guarded start_all runs — the
        # same shape as the indexing-manager block above. Own try/except
        # around start_all only (a subscribe/settings-load failure must not
        # kill app startup); an operator with no folders pays one sleeping
        # reconcile-loop task.
        global _watch_manager
        _watch_manager = WatchManager(index_manager=_indexing_manager)
        _set_module_watch_manager(_watch_manager)
        try:
            await _watch_manager.start_all()
        except Exception:
            logger.exception("watch manager startup failed")
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
        # M24 F04 L03, DD-7: drain the watch manager immediately before the
        # indexing manager's own drain below — no `request_index` can land
        # on an indexing manager that is stopping workers. Own try/except
        # (a subscription that hangs must not kill the rest of shutdown);
        # the two cleanup lines sit outside the try/except, mirroring the
        # indexing-manager block below, so the accessor is cleared even
        # when `drain()` raises.
        if _watch_manager is not None:
            try:
                await _watch_manager.drain()
            except Exception:
                logger.exception("watch manager shutdown failed")
            _set_module_watch_manager(None)
            _watch_manager = None
        # M24 F03 L03, DD-7: drain the indexing manager right after the
        # in-flight/resume task gathers and before the reaper drain — a KB
        # worker mid-item gets its cooperative-stop-then-flush budget
        # before any other shutdown work begins. Concurrent per-KB stop
        # inside `drain()` bounds this to 20s + 20s regardless of KB count.
        # M24 F07 L01, AC-6a: captured INSIDE this `if` block, before the
        # two lines below null both the module accessor and this local —
        # a read taken after this block sees only `None`/empty. Threaded
        # into the close_vector_store() call near close_connection() below.
        _cancel_report_kb_ids: frozenset[str] = frozenset()
        if _indexing_manager is not None:
            try:
                await _indexing_manager.drain()
            except Exception:
                logger.exception("indexing manager shutdown failed")
            _cancel_report_kb_ids = _indexing_manager.cancelled_kb_ids()
            _set_module_indexing_manager(None)
            _indexing_manager = None
        # F05 L01: drain the web-session idle reaper after in-flight task drains
        # and before the PTY session registry drain. Cancels the reaper task and
        # closes all remaining in-memory sessions.
        try:
            await _web_session_reaper_shutdown_drain()
        except Exception:
            logger.exception("web-session reaper shutdown failed")
        # M13 F03 L3: drain the daily chat-history purge loop beside the
        # web-session reaper drain. Cancels the task and suppresses CancelledError.
        try:
            await _chat_history_purge_shutdown_drain()
        except Exception:
            logger.exception("daily purge shutdown failed")
        # M16 F05 L02: drain the daily model-catalog refresh loop beside the
        # purge drain. Cancels the task and suppresses CancelledError.
        try:
            await _model_catalog_refresh_shutdown_drain()
        except Exception:
            logger.exception("model-catalog refresh shutdown failed")
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
        # M21 F01 L02 / probe constraint 2: proactively evict every marked
        # (self-configuration) row's pool entries BEFORE the general drain
        # below closes the listener — the re-entrancy probe found that a
        # loopback session torn down AFTER the listener closes logs a benign
        # but noisy WARNING. Evicting here first, while the listener is still
        # up, lets those sessions terminate cleanly.
        try:
            from the_one.mcp._pool import _evict_all_for_source

            _self_configuration_conn = await get_connection()
            _self_configuration_repo = MCPSourceRepository(
                _self_configuration_conn, get_encryptor(settings.data_dir)
            )
            for _row in await _self_configuration_repo.list():
                if _self_configuration_manage.is_surface_row(_row):
                    await _evict_all_for_source(_row.id)
        except Exception:
            logger.exception("self-configuration surface pool eviction failed")
        try:
            await _mcp_pool_shutdown_drain()
        except Exception:
            logger.exception("MCP pool shutdown failed")
        # F5 L2: stop the OAuth pending-flow TTL sweep task. Runs AFTER the
        # MCP pool drain so any in-flight OAuth refreshes triggered by
        # pool teardown can complete first.
        from the_one.mcp.oauth import stop_periodic_sweep

        try:
            await stop_periodic_sweep()
        except Exception:
            logger.exception("OAuth periodic sweep shutdown failed")
        # Mission 23 Flight 2 Leg 1: drain the connector manager's listener
        # tasks. Placed AFTER the OAuth sweep stop (clear of squawk 0025's
        # MCP evict/drain block above, which stays byte-identical) and
        # BEFORE the factory-reference release below — the manager's
        # supervisor tasks call ``dispatch_inbound``, which resolves the
        # module-level factory, so draining first keeps that resolvable
        # for any in-flight inbound. (``global _connector_manager`` was
        # already declared once above, at the startup site — a SECOND
        # ``global`` statement for the same name later in this function
        # is a SyntaxError, not a harmless repeat.)
        if _connector_manager is not None:
            try:
                await _connector_manager.drain()
            except Exception:
                logger.exception("connector manager shutdown failed")
            _set_module_connector_manager(None)
            _connector_manager = None
        # Mission 23 Flight 2 Leg 2: symmetric teardown for the dual-gated
        # stub-registration startup hook above. Unregisters "stub" ONLY if
        # THIS process's hook is what registered it — a test's own direct
        # ``registry.register_for_test("stub", ...)`` call never sets this
        # flag, so it is never clobbered by a lifespan cycle that didn't
        # register anything. Without this, a later ``TestClient(app)``
        # lifespan cycle in the same process (unit-test suite) could
        # inherit a stale "stub" registration from an earlier cycle where
        # the gate happened to be open.
        if _stub_connector_registered_by_hook:
            from the_one.connectors import registry as _connector_registry

            _connector_registry.unregister("stub")
            _stub_connector_registered_by_hook = False
        # Mission 23 Flight 3 Leg 1: symmetric teardown for the
        # unconditional Discord registration above — every lifespan cycle
        # that registers it also unregisters it, so a later cycle in the
        # same process (unit-test suite) never inherits a stale "discord"
        # registration.
        from the_one.connectors import registry as _connector_registry

        _connector_registry.unregister("discord")
        # Mission 23 Flight 4 Leg 2: symmetric teardown for the
        # unconditional Telegram registration above, mirroring Discord's
        # own hygiene immediately above.
        _connector_registry.unregister("telegram")
        # M10 F8 L4: release the module-level factory reference so post-
        # shutdown ``get_factory()`` reads return None. Defensive — not
        # strictly required for correctness because the process is exiting,
        # but symmetric with the startup ``set_factory`` call and keeps
        # subsequent tests from observing a stale slot.
        _set_module_factory(None)
        # M24 F07 L01, DD-3/DD-3a: close the vector store AFTER the
        # indexing-manager drain above (that drain flushes each worker's
        # own knowledge base) and BEFORE close_connection() below
        # (UsearchStore.flush() writes through self.conn via
        # _upsert_registry_row()). Called UNCONDITIONALLY (AC-6b) — a store
        # can exist and be dirty with no indexing manager at all (e.g. the
        # item-delete route's direct write, api.py's _vector_store()); when
        # there is no manager, `_cancel_report_kb_ids` is the empty
        # frozenset set above and nothing is skipped for that reason. Never
        # builds a store to close it (close_vector_store()'s own no-op
        # when `_store is None`).
        try:
            await close_vector_store(skip_kb_ids=_cancel_report_kb_ids)
        except Exception:
            logger.exception("vector store shutdown failed")
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
# Mission 20 / Flight 1 / Leg 4 (`enforce-gate`) — DD4: the credential gate
# must be registered AFTER OriginAllowlistMiddleware so it wraps it.
# Starlette's `add_middleware` inserts at index 0, so the last-added
# middleware is outermost and runs first. That ordering gives
# 401-before-origin (an unauthenticated request is refused before the
# origin check ever runs) and 403 for a valid-credential-wrong-origin
# request (it reaches the inner Origin middleware and is rejected there).
# See `the_one/interfaces/web/middleware.py::CredentialGateMiddleware` for
# the full layering rationale.
app.add_middleware(CredentialGateMiddleware)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api_router)
# M21 F01 L02 (DD1/LD4): the self-configuration MCP surface, mounted on the
# existing app and port — no new port, no new listener. Mounted AFTER the
# API router per leg Implementation Guidance #6. `streamable_http_app()`
# must be called here (module load, not per-request) so `mcp.session_manager`
# exists by the time `lifespan` above wraps `.run()` around its body — the
# SDK creates the session manager lazily on first call to this method.
app.mount(_SELF_CONFIGURATION_MOUNT_PATH, _self_configuration_surface.mcp.streamable_http_app())


# ── State ─────────────────────────────────────────────────────────────────

_state: dict[str, Any] = {}

# Mission 23 Flight 2 Leg 1: the running connector manager. Mirrors
# `_state["factory"]`'s pattern of also installing into a module-level
# accessor (`_set_module_connector_manager`) for non-web-layer consumers
# (the send/history tools; ``the_one.connectors.manager.get_manager``).
_connector_manager: ConnectorManager | None = None

# M24 F03 L03: the running indexing manager. Mirrors `_connector_manager`
# above — the lifespan's own local global (what shutdown's drain reads)
# alongside the module-level accessor (`_set_module_indexing_manager`,
# what routes reach via `the_one.knowledge.manager.get_manager`).
_indexing_manager: IndexingManager | None = None

# M24 F04 L03, DD-7: the running watch manager. Same shape as
# `_indexing_manager` above — the lifespan's own local global (what
# shutdown's drain reads) alongside the module-level accessor
# (`_set_module_watch_manager`, what routes reach via
# `the_one.knowledge.watcher.get_manager`).
_watch_manager: WatchManager | None = None

# Mission 23 Flight 2 Leg 2: True for the lifetime of a lifespan cycle iff
# THIS process's dual-gated startup hook registered the "stub" connector
# type — read at shutdown so the symmetric teardown only unregisters when
# it's the one that registered (see the startup/shutdown blocks above).
_stub_connector_registered_by_hook: bool = False


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
    # M11 F13 L5: routing-audit-inspector hydration. The dispatcher's
    # session_metadata["routing"] writes go to the DB via
    # ChatSessionRepository.append_to_session_metadata. The Chat UI
    # routing-audit panel reads from this in-memory snapshot via the
    # session_joined WS payload; Refresh button re-fetches from REST.
    session_metadata: dict[str, Any] | None = None
    # F05 L01: monotonic timestamp of the most recent activity on this
    # session (create, restore, message send, chat_reset, WS disconnect).
    # Used by the web-session idle reaper to determine when a zero-
    # subscriber session qualifies for eviction. Defaults to construction
    # time so new/restored sessions start with a fresh clock.
    last_activity: float = field(default_factory=time.monotonic)

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

# F05 L01: shared lock that serializes all read-modify-write operations on
# ``_sessions`` (create, restore, delete, reaper eviction). The reaper is
# two-phase: select+pop under this lock, then ``await agent.aclose()``
# OUTSIDE it (avoids holding the lock across async I/O).
_sessions_lock: asyncio.Lock = asyncio.Lock()

# F05 L01: web-session idle reaper task reference (started in lifespan,
# cancelled on shutdown). Mirrors ``_reaper_task`` in
# ``tools/_session_registry.py``.
_web_session_reaper_task: asyncio.Task[None] | None = None

# M13 F03 L3: daily chat-history purge loop task reference (started in
# lifespan just after the reaper, cancelled on shutdown). Mirrors
# ``_web_session_reaper_task`` above.
_chat_history_purge_task: asyncio.Task[None] | None = None

# F05 L01: reaper wake interval — a fraction of the TTL, floored at 30s.
# Computed lazily at startup relative to the configured TTL so tests can
# monkeypatch the env var and get a sensible interval.
_WEB_SESSION_REAPER_INTERVAL_SECONDS = 30.0

# Set of in-flight per-message processing tasks spawned by the WebSocket
# handler. Tracked so FastAPI's lifespan teardown can cancel them on
# shutdown (otherwise a `make restart` mid-tool-call would leave a
# detached coroutine). Tasks self-discard on completion via `add_done_callback`.
_inflight_tasks: set[asyncio.Task] = set()

# F7 L03 (cancel-backend) / F09-03: per-session in-flight task set.
# Maps session_id → the set of tasks running _spawn_message_processing
# for that session. With the queue-depth-1 pattern (leg 4) a running
# task and a queued (lock-blocked) task can coexist on one session, so
# the set holds BOTH. A WS `cancel` action cancels every not-done task
# in the set — "stop = stop everything" (F07 DD4). The done-callback
# discards the finished task and deletes the key when the set empties.
_session_inflight: dict[str, set[asyncio.Task]] = {}

# F5 L3: tasks driving ``_resume_paused_session`` after the OAuth-callback
# route resolves a paused agent. Tracked separately from ``_inflight_tasks``
# so the lifespan teardown can drain both in one pass; the OAuth-callback
# route adds tasks here via ``asyncio.create_task``.
_inflight_resume_tasks: set[asyncio.Task] = set()


# M18 F02 L02: defense-in-depth caps on chat image attachments, not a
# strict security boundary — the provider enforces its own, stricter,
# per-image limit. These bound self-inflicted memory pressure from an
# unbounded client payload. Per-image ~10 MB is generous (covers typical
# photo/screenshot attachments); max count 10 is a round, permissive
# default. No separate total-payload cap: count x per-image (~100 MB
# worst case) already bounds the total, so a third constant would be
# redundant (documented decision, M18 F02 L02).
IMAGE_ATTACHMENT_CAP_BYTES = 10 * 1024 * 1024  # ~10 MB per image (decoded size)
IMAGE_ATTACHMENT_MAX_COUNT = 10  # max attachments per turn


def _approx_image_bytes(img: dict[str, Any]) -> int:
    """Approximate the decoded byte size of an image dict's base64 payload.

    Base64 inflates raw bytes by ~4/3, so decoded size ≈ ``len(data) * 3/4``
    (M18 F02 L02 design review: exact-enough for a defense-in-depth cap,
    no need to actually decode). Images specified via ``url`` (no `data`)
    carry no client-supplied size to check — the provider fetches those
    directly — so this returns 0 for them (unbounded by this cap; the
    provider enforces its own per-image limit for URL-sourced images).

    Defensive backstop: a non-dict ``img`` (shouldn't reach here — the
    caller validates shape first) returns 0 rather than raising, so this
    stays safe to call directly.
    """
    if not isinstance(img, dict):
        return 0
    data = img.get("data")
    if not isinstance(data, str):
        return 0
    return (len(data) * 3) // 4


def _build_user_content(
    user_input: str, images: list[dict[str, Any]] | None
) -> str | list[ContentBlock]:
    """Build the WS user-turn content: plain ``str`` when no images are
    attached (text-only path is byte-identical to pre-L08 behaviour), else
    ``list[ContentBlock]``.

    Text + images -> ``[TextContent(text=user_input), *ImageContent(**img)
    for img in images]``. Images with no text -> ``[ImageContent(**img) for
    img in images]`` — deliberately **no** empty ``TextContent``: Anthropic
    400s on an empty-text content block ("text content blocks must contain
    non-whitespace text").
    """
    if not images:
        return user_input
    blocks: list[ContentBlock] = []
    if user_input:
        blocks.append(TextContent(text=user_input))
    blocks.extend(ImageContent(**img) for img in images)
    return blocks


async def _spawn_message_processing(
    session: Session,
    user_input: str | list[ContentBlock],
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
        # F05 L01: touch last_activity at the start of message processing
        # so the reaper clock advances on every new user turn.
        session.last_activity = time.monotonic()
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


# ── Web-session idle reaper ───────────────────────────────────────────────


def _get_web_session_idle_ttl() -> int:
    """Read ``THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS`` at call time.

    F05 L01: mirrors the ``THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS``
    reader in ``connectors/_pool.py``: ``os.environ.get`` at call time
    with int-parse and a fallback to the default (1800s = 30 min).
    Reading at call time (rather than at module-import time) lets tests
    monkeypatch the env var without reloading the module.
    """
    raw = os.environ.get("THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS")
    default = 1800
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS=%r is not an int; falling back to %d",
            raw,
            default,
        )
        return default


async def _reap_web_sessions_once() -> list[str]:
    """Run one idle-reaper pass over ``_sessions``.

    F05 L01: two-phase — select+pop under ``_sessions_lock``, then call
    ``agent.aclose()`` outside the lock so async I/O doesn't block
    concurrent create/restore paths. Also pops the evicted ids from
    ``session_locks`` to prevent the lock map from growing unboundedly.

    SAFETY invariant: sessions with ≥1 live subscriber OR currently
    processing are NEVER evicted, regardless of their idle age.

    Returns the list of evicted session ids (for test purchase and
    log output).
    """
    ttl = _get_web_session_idle_ttl()
    now = time.monotonic()

    evicted: list[tuple[str, Agent]] = []
    async with _sessions_lock:
        for sid, session in list(_sessions.items()):
            if subscribers_for(sid):
                continue  # open chat tab — never reap
            if is_session_processing(sid):
                continue  # mid-turn tool call — belt-and-suspenders
            if (now - session.last_activity) <= ttl:
                continue  # not idle yet
            evicted.append((sid, session.agent))
            _sessions.pop(sid)

    evicted_ids: list[str] = []
    for sid, agent in evicted:
        evicted_ids.append(sid)
        # Pop the session lock to prevent unbounded lock-map growth.
        # Must be outside _sessions_lock (we already released it above).
        session_locks.pop(sid, None)
        try:
            await agent.aclose()
        except Exception:
            logger.exception("agent.aclose() raised during web-session reap: sid=%r", sid)

    if evicted_ids:
        logger.info("web-session reaper evicted %d session(s): %s", len(evicted_ids), evicted_ids)
    return evicted_ids


async def _web_session_reap_loop() -> None:
    """Background loop: sleep, reap, repeat.

    F05 L01: mirrors ``_reap_loop`` in ``tools/_session_registry.py``.
    The reaper interval is a fraction of the TTL, floored at 30s.
    On cancellation, drains all remaining zero-subscriber sessions
    before re-raising ``CancelledError``.
    """
    try:
        while True:
            ttl = _get_web_session_idle_ttl()
            interval = max(30, ttl // 10)
            await asyncio.sleep(interval)
            try:
                await _reap_web_sessions_once()
            except Exception:
                logger.exception("web-session reap pass raised; continuing")
    except asyncio.CancelledError:
        # Drain remaining sessions on shutdown. Does NOT unconditionally
        # reap all sessions — only those with zero subscribers (open tabs
        # would still be in the subscriber registry but the server is
        # shutting down, so the WS connections will close anyway).
        # This is belt-and-suspenders: the shutdown drain below handles
        # the rest.
        raise


async def _web_session_reaper_shutdown_drain() -> None:
    """Cancel the reaper task and close all remaining sessions.

    F05 L01: wired into the FastAPI ``lifespan`` shutdown branch, after
    the in-flight/resume task drains and before the PTY session registry
    drain. Mirrors ``shutdown_drain()`` in ``tools/_session_registry.py``.
    After this runs, any late-arriving join will recreate sessions via
    the DB restore path — nothing is lost, only the warm cache is torn down.
    """
    global _web_session_reaper_task

    task = _web_session_reaper_task
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # Belt-and-suspenders drain of any remaining sessions.
    async with _sessions_lock:
        snapshot = list(_sessions.items())
        _sessions.clear()

    for sid, session in snapshot:
        session_locks.pop(sid, None)
        try:
            await session.agent.aclose()
        except Exception:
            logger.exception("agent.aclose() raised during web-session shutdown drain: sid=%r", sid)

    _web_session_reaper_task = None


# ── Daily chat-history purge ──────────────────────────────────────────────


def _get_purge_check_interval() -> int:
    """THE_ONE_PURGE_CHECK_INTERVAL_SECONDS at call time; default 3600
    (coarse — the due-check gates the actual 24h purge). Floored at 60s
    so a 0/negative value can't tight-loop."""
    raw = os.environ.get("THE_ONE_PURGE_CHECK_INTERVAL_SECONDS")
    if raw is None:
        return 3600
    try:
        return max(60, int(raw))
    except ValueError:
        logger.warning("THE_ONE_PURGE_CHECK_INTERVAL_SECONDS=%r not an int; using 3600", raw)
        return 3600


async def _purge_due() -> bool:
    conn = await get_connection()
    last = await retention.get_last_purge_at(conn)
    return retention.is_purge_due(last, datetime.now(timezone.utc))


async def _run_purge_sweep_and_evict() -> dict:
    """Run the DB sweep, then evict swept ids from the in-memory
    _sessions registry (DD4). Three-phase, reaper shape (app.py:485–509):
    pop under _sessions_lock; close + lock-map-pop outside it."""
    conn = await get_connection()
    result = await retention.run_purge_sweep(conn)
    ids = result["ids"]
    if not ids:
        return result
    evicted: list[tuple[str, Agent]] = []
    async with _sessions_lock:
        for sid in ids:
            sess = _sessions.pop(sid, None)
            if sess is not None:
                evicted.append((sid, sess.agent))
    for sid, agent in evicted:  # outside the lock (reaper hygiene)
        session_locks.pop(sid, None)
        try:
            await agent.aclose()
        except Exception:
            logger.exception("agent.aclose() raised during purge eviction: sid=%r", sid)
    logger.info(
        "daily purge swept %d session(s); evicted %d from _sessions",
        len(ids),
        len(evicted),
    )
    return result


async def _chat_history_purge_loop() -> None:
    """Due-based daily purge. Catch-up on entry, then sleep+recheck.
    M13 F03 — mirrors the F05 web-session reaper loop/start/drain."""

    async def _maybe_purge() -> None:
        try:
            if await _purge_due():
                await _run_purge_sweep_and_evict()
        except Exception:
            logger.exception("daily purge pass raised; continuing")

    await _maybe_purge()  # startup catch-up (guarded)
    while True:
        await asyncio.sleep(_get_purge_check_interval())
        await _maybe_purge()


async def _chat_history_purge_shutdown_drain() -> None:
    global _chat_history_purge_task
    task = _chat_history_purge_task
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    _chat_history_purge_task = None


# ── Daily model-catalog refresh ───────────────────────────────────────────

_catalog_refresh_task: asyncio.Task | None = None


def _get_catalog_refresh_check_interval() -> int:
    """THE_ONE_CATALOG_REFRESH_CHECK_INTERVAL_SECONDS at call time; default 3600
    (coarse — the due-check gates the actual 24h refresh). Floored at 60s
    so a 0/negative value can't tight-loop."""
    raw = os.environ.get("THE_ONE_CATALOG_REFRESH_CHECK_INTERVAL_SECONDS")
    if raw is None:
        return 3600
    try:
        return max(60, int(raw))
    except ValueError:
        logger.warning(
            "THE_ONE_CATALOG_REFRESH_CHECK_INTERVAL_SECONDS=%r not an int; using 3600", raw
        )
        return 3600


async def _model_catalog_refresh_loop() -> None:
    """Due-based daily model-catalog refresh. Catch-up on entry, then sleep+recheck.
    M16 F05 L02 — mirrors _chat_history_purge_loop (F03 L3)."""
    from the_one.llm.model_catalog import _refresh_due, refresh_catalog_cache

    async def _maybe_refresh() -> None:
        try:
            if _refresh_due():
                await refresh_catalog_cache()
        except Exception:
            logger.exception("model-catalog refresh pass raised; continuing")

    await _maybe_refresh()  # startup catch-up (guarded)
    while True:
        await asyncio.sleep(_get_catalog_refresh_check_interval())
        await _maybe_refresh()


async def _model_catalog_refresh_shutdown_drain() -> None:
    global _catalog_refresh_task
    task = _catalog_refresh_task
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    _catalog_refresh_task = None


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
        last_activity=time.monotonic(),
    )
    async with _sessions_lock:
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
        async with _sessions_lock:
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
        cached.last_activity = time.monotonic()  # F05 L01: touch on restore
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
        async with _sessions_lock:
            _sessions.pop(session_id, None)
        return RestoredSession(None, SESSION_STATUS_PROVIDER_MISSING, db_session)
    except ProviderNotConfiguredError as exc:
        logger.warning(
            "Session %s degraded: status=provider_missing agent=%r exc=%s",
            session_id,
            db_session.agent_name,
            exc,
        )
        async with _sessions_lock:
            _sessions.pop(session_id, None)
        return RestoredSession(None, SESSION_STATUS_PROVIDER_MISSING, db_session)
    except AgentNotFoundError as exc:
        logger.warning(
            "Session %s degraded: status=agent_deleted agent=%r exc=%s",
            session_id,
            db_session.agent_name,
            exc,
        )
        async with _sessions_lock:
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

    async with _sessions_lock:
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
            # M11 F13 L5: refresh the routing-audit snapshot from the DB row
            # so the next session_joined payload carries the latest entries
            # the dispatcher has written via append_to_session_metadata.
            existing.session_metadata = db_session.session_metadata
            existing.last_activity = time.monotonic()  # F05 L01: touch on restore
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
            # M11 F13 L5: surface session_metadata so _build_session_joined_ok
            # can ship the routing-audit entries in the join payload without a
            # separate REST round-trip.
            session_metadata=db_session.session_metadata,
            last_activity=time.monotonic(),  # F05 L01: touch on restore
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


async def _persist_last_usage(
    session: Session,
    input_tokens: int,
    output_tokens: int,
    context_tokens: int,
) -> None:
    """Persist per-turn usage snapshot to session_metadata["last_usage"].

    M16 F06 L01 — shared helper called from both turn-settle sites:
    the non-paused settle in ``_process_and_broadcast`` and the resume
    settle in ``_resume_paused_session``.

    Writes ``{"input_tokens", "output_tokens", "context_tokens"}`` to the
    DB via ``set_session_metadata_key`` (overwrite semantic, preserves
    sibling keys like ``routing``) and mirrors the write in-memory so a
    same-process reopen doesn't need a DB round-trip.

    The in-memory update mirrors the repo's read-modify-write:
    ``session.session_metadata or {}`` handles a fresh session where the
    field is ``None``, and we spread existing siblings so concurrent writes
    to other keys survive (e.g. a ``routing`` key written by the dispatcher
    between the DB call and the in-memory update won't be clobbered here).
    """
    snapshot = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "context_tokens": context_tokens,
    }
    try:
        repo = await _chat_repo()
        await repo.set_session_metadata_key(session.id, "last_usage", snapshot)
    except Exception:
        logger.warning("Failed to persist last_usage for session %s", session.id, exc_info=True)
        return
    # Mirror in-memory so same-process reopens see the value without a DB round-trip.
    session.session_metadata = {**(session.session_metadata or {}), "last_usage": snapshot}


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
        # M11 F13 L5: ship the routing-audit snapshot so the Chat UI
        # panel renders on join without a separate REST round-trip.
        "session_metadata": session.session_metadata,
        # M23 F02 L03 (behavior-test fix): surface the connector platform
        # (None for a web-native session) so the Chat UI can distinguish
        # "no visibility key on this tool_result because there's no
        # operator/peer distinction at all" (non-connector session) from
        # "no visibility key because this tool_result is genuinely
        # peer-visible" (connector session) — needed to gate promoting a
        # delivered tool result to a top-level bubble instead of collapsing
        # it into the "Tool activity" accordion.
        "platform": session.platform,
    }


async def _build_session_joined_degraded(restored: RestoredSession) -> dict[str, Any]:
    """Build a session_joined payload for a degraded (agent_deleted/provider_missing) session.

    History is decoded from the DB row directly — there is no in-memory
    Session for degraded states. Stays ``async`` (no ``await`` left in
    the body since the M23 F01 pending-approval merge was removed) so
    its call site (an async WS handler) doesn't need to change.
    """
    db = restored.db_session
    assert db is not None, "degraded RestoredSession must carry db_session"
    ui_events = messages_to_ui_events(decode_messages(db.messages))
    return {
        "type": "session_joined",
        "session_id": db.id,
        "status": restored.status,
        "title": db.title,
        "agent_name": db.agent_name,
        "history": ui_events,
        # M11 F13 L5: ship the routing-audit snapshot on the degraded
        # path too — db: ChatSessionModel already carries the field.
        "session_metadata": db.session_metadata,
        # M23 F02 L03: mirror _build_session_joined_ok's platform field —
        # db: ChatSessionModel already carries it too.
        "platform": db.platform,
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
    from the_one.llm.ollama_provider import effective_num_ctx

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

        model_name = agent_config.llm_model

        # The runtime window we want the runner loaded at. Ollama defaults
        # num_ctx to 4096 and the /v1 chat endpoint can't raise it, so a model
        # already running at the wrong window must be RELOADED at ``desired``
        # before generation — otherwise the conversation truncates at 4096
        # tokens and dies. ``desired`` is None when the model's advertised
        # window is unknown, in which case we leave Ollama's default untouched.
        advertised = await ollama_api.get_model_context_length(provider_config.base_url, model_name)
        # Thread the per-provider ``config.num_ctx`` (if set) through so the
        # preloaded runner is loaded at the same window the provider will
        # generate with. effective_num_ctx coerces a stray value to None.
        desired = effective_num_ctx(advertised, provider_config.config.get("num_ctx"))

        def _name_matches(running_name: str) -> bool:
            # Exact match, or match ignoring a :latest tag on either side.
            return (
                running_name == model_name
                or running_name == f"{model_name}:latest"
                or model_name == f"{running_name}:latest"
            )

        # Already loaded AT THE RIGHT WINDOW? Then nothing to do. A name match
        # with the wrong ``context_length`` falls through to a reload.
        for m in await ollama_api.list_running(provider_config.base_url):
            if _name_matches(m.get("name", "")):
                if desired is None or m.get("context_length") == desired:
                    return
                break  # loaded at the wrong num_ctx — reload below

        # Not loaded (or loaded at the wrong window) — notify + (re)load at the
        # desired runtime window. ``num_ctx`` is passed via the native API; a
        # later /v1 chat request reuses this runner.
        await _send_to_session(session, {"type": "system", "content": "Loading model..."})
        await ollama_api.load_model(provider_config.base_url, model_name, num_ctx=desired)
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
    user_input: str | list[ContentBlock],
    source: str = "web",
    exclude_user_echo: WebSocket | None = None,
) -> list[dict[str, Any]]:
    """Run agent step, broadcast all events, return message list for API."""
    # Auto-load Ollama model if needed (fast check, safe to run every message)
    await _ensure_ollama_model_loaded(session)

    # Broadcast user message. M16 F12 L08: project through content_to_text —
    # user_input may be a list[ContentBlock] (image-bearing turn); the live
    # WS event and session.add_event's title-slice both require a plain str.
    # Without this projection, list content reaches ws.send_json (stdlib
    # json.dumps, no custom encoder) and raises TypeError, which
    # _send_to_session's try/except silently swallows as a "dead" socket —
    # desyncing the sender from their own session on the very first image
    # send (never sees the assistant reply).
    user_event: dict[str, Any] = {
        "type": "user",
        "content": content_to_text(user_input),
        "source": source,
    }
    # M10 F06 L6: close the F5 live-broadcast carry-forward. The
    # operator-typed message on a connector-attached session must
    # carry the visibility tag at LIVE broadcast time (the refresh
    # path's post-step Message-level tagging at L997-1004 handles
    # the persistence side; this site handles the live side). Mirrors
    # the codec's projection rule at db/codec.py:173-176 — only emit
    # the key when the value is meaningful. The session_locks[session.id]
    # acquired by ``_spawn_message_processing`` (this module) serializes
    # against ``the_one.connectors.inbound.dispatch_inbound``'s own
    # ``async with session_locks[session_row.id]:`` block (Mission 23
    # Flight 2 Leg 1 — the kept ``the_one/sessions/`` lock registry is the
    # SAME dict both paths acquire from), so there is no race.
    #
    # M11 F06 L03: this path does NOT acquire a ``peer_name`` key — the
    # operator IS the source; there is no peer to attribute. Peer-
    # attributed user events would flow via the dispatcher path
    # (``the_one.connectors.inbound``) if/when that path binds
    # ``peer_name`` post-step — not yet done as of Flight 2 Leg 1.
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

    # F7 L03 (cancel-backend): accumulate streamed text so it can be
    # persisted as an interrupted assistant Message if the task is
    # cancelled mid-stream. The partial_text accumulator is read inside
    # the except asyncio.CancelledError block below.
    partial_text = ""

    async def _broadcast_chunk(content: str) -> None:
        nonlocal chunks_seen, partial_text
        chunks_seen = True
        partial_text += content
        chunk_event: dict[str, Any] = {"type": "assistant_chunk", "content": content}
        # M23 F02 L03 (behavior-test fix): assistant text on a connector-
        # attached session is UNCONDITIONALLY OPERATOR_VISIBILITY per
        # ``tag_post_step_visibility``'s rule (Role.ASSISTANT is never the
        # successful-platform-send exception, which is TOOL-only) — no need
        # to wait for that post-step pass (which runs after this whole
        # step loop) to know the value live. Closes the live-vs-reload
        # rendering gap the streaming path used to carry (see the removed
        # "known limitation" note this replaces, and the equivalent fix
        # below for the legacy `assistant`/`thinking`/`tool_call` events and
        # the nuanced `tool_result` case).
        if session.platform is not None:
            chunk_event["visibility"] = OPERATOR_VISIBILITY
        await _send_to_session(session, chunk_event)

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
                    # M23 F02 L03: same deterministic tag as _broadcast_chunk
                    # above — an ASSISTANT message on a connector-attached
                    # session is always OPERATOR_VISIBILITY, so this can be
                    # set live rather than waiting for the post-step
                    # tag_post_step_visibility pass below. Fixes the
                    # live-vs-reload marker inconsistency (the [operator-only]
                    # prefix used to appear only after reload).
                    if session.platform is not None:
                        event["visibility"] = OPERATOR_VISIBILITY
                    session.add_event(event)
                    if not chunks_seen:
                        # Direct-action / non-streaming path — broadcast the
                        # legacy event so the client still renders. When chunks
                        # were broadcast, the client already has the text via
                        # the chunk path; suppress the duplicate broadcast.
                        await _send_to_session(session, event)

                # M16 F10 L05 (DD2 reveal-after): surface captured thinking as a
                # broadcast-only ``thinking`` event once the answer has settled
                # (fires as the assistant msg is processed, after its content /
                # chunks already streamed). BROADCAST-ONLY — no session.add_event:
                # thinking is a projection DERIVED from msg.thinking, like the
                # interim usage event above. session.history is fully rebuilt from
                # the codec on every join (messages_to_ui_events), which re-derives
                # the thinking event from the persisted msg.thinking — so adding it
                # here would only inflate message_count for an entry immediately
                # overwritten on the next join. Kept out of result_messages (below).
                _thinking_text = thinking_display_text(msg.thinking)
                if _thinking_text:
                    # DOC1 (Mission 18 F04 L02): mirror codec.py's replay
                    # projection visibility handling (``vis = {"visibility":
                    # msg.visibility} if msg.visibility is not None else {}``,
                    # codec.py ~332/383-388) so the live broadcast carries the
                    # same shape as the persisted-replay event: same key,
                    # omitted (not null) when visibility is None.
                    #
                    # M23 F02 L03 (behavior-test fix): thinking is always
                    # emitted by an ASSISTANT message, which — like the
                    # `assistant`/`assistant_chunk` events above — is
                    # unconditionally OPERATOR_VISIBILITY on a connector-
                    # attached session (Role.ASSISTANT is never the
                    # successful-platform-send exception in
                    # tag_post_step_visibility, which is TOOL-only). Set it
                    # deterministically here rather than waiting on
                    # msg.visibility, which the post-step pass below hasn't
                    # set yet at this point in the loop — this used to be a
                    # documented "live parity only after rejoin" limitation
                    # (closed the F10 action item at the time); it is now
                    # exact live too. Non-connector sessions keep the
                    # msg.visibility fallback (always None today, forward-
                    # compat with any future non-connector visibility use).
                    thinking_event: dict[str, Any] = {
                        "type": "thinking",
                        "content": _thinking_text,
                    }
                    if session.platform is not None:
                        thinking_event["visibility"] = OPERATOR_VISIBILITY
                    elif msg.visibility is not None:
                        thinking_event["visibility"] = msg.visibility
                    await _send_to_session(session, thinking_event)
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
                        # M23 F02 L03: a tool_call is emitted by the same
                        # ASSISTANT message as above — always
                        # OPERATOR_VISIBILITY on a connector-attached
                        # session (a tool CALL is never itself the
                        # successful-platform-send exception; only its
                        # eventual TOOL result can be). Same live-vs-reload
                        # fix as `assistant`/`assistant_chunk`/`thinking`.
                        if session.platform is not None:
                            tc_event["visibility"] = OPERATOR_VISIBILITY
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
                # M23 F02 L03: unlike ASSISTANT above, a TOOL result's
                # visibility is NOT deterministic from `session.platform`
                # alone — it depends on whether THIS result is the
                # successful `send_to_platform_channel` exception
                # (tag_post_step_visibility's rule in llm/base.py). Tag now
                # (not after the whole turn settles, as the pre-existing
                # post-step call below still does for persistence) so the
                # live broadcast + in-memory session.history carry the same
                # value the DB-persisted / reload render will show — closes
                # the same live-vs-reload gap as the ASSISTANT-side events
                # above. Safe to call repeatedly: idempotent over the
                # already-yielded messages[pre_step_len:] slice, and the
                # parent ASSISTANT message (with its tool_calls) was
                # appended earlier this same turn, so the send-tool-name
                # lookup already has what it needs.
                if session.platform is not None:
                    tag_post_step_visibility(session.agent.messages, pre_step_len)
                tr_event = {
                    "type": "tool_result",
                    "content": truncate_for_event(msg.tool_result.content),
                    "is_error": msg.tool_result.is_error,
                    "parent_message_id": current_turn_parent_id,
                    "tool_call_id": msg.tool_result.tool_call_id,
                }
                if msg.visibility is not None:
                    tr_event["visibility"] = msg.visibility
                session.add_event(tr_event)
                await _send_to_session(session, tr_event)
                result_messages.append(
                    {
                        "role": "tool",
                        "content": truncate_for_event(msg.tool_result.content),
                        "is_error": msg.tool_result.is_error,
                    }
                )
    except asyncio.CancelledError:
        # F7 L03 (cancel-backend): operator cancelled the task (or lifespan
        # shutdown is tearing down). CancelledError is a BaseException — it
        # is NOT caught by the sibling `except Exception` below, so these
        # two handlers are SIBLINGS, not a catch-all pair.
        #
        # NOTE FOR REVIEWERS: `except Exception` at the sibling block below
        # does NOT catch CancelledError (CancelledError inherits BaseException
        # directly in Python ≥ 3.8). If a future refactor changes that to
        # `except BaseException`, cancel's lock-release semantics would
        # silently break — the lock is released by _spawn_message_processing's
        # `async with session_locks[session.id]` only if CancelledError
        # propagates out of this function.
        #
        # Persist partial output only if any text was streamed before cancel.
        # If cancel fired mid-tool-call with no preamble, skip the synthetic
        # message (empty-content Message is noise; the next turn starts clean).
        if partial_text:
            interrupted_msg = Message.assistant(content=partial_text + "\n\n_[interrupted]_")
            session.agent.messages.append(interrupted_msg)
        # Best-effort save and notify — wrapped in suppress so lifespan
        # teardown (closing DB / sockets) can't turn a clean shutdown
        # cancel into an unhandled exception. Re-raise preserves the
        # lock-release semantics in _spawn_message_processing (:455-458).
        with contextlib.suppress(Exception):
            await _save_session_to_db(session)
        with contextlib.suppress(Exception):
            await _send_to_session(session, {"type": "cancelled"})
        raise
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

        # M16 F06 L01: persist per-turn usage snapshot at the non-paused
        # settle. ``last_input`` starts at 0 and is only updated when an
        # assistant message with usage arrives, so ``if last_input`` is the
        # zero-usage guard: a turn that errored before any usage event
        # leaves the prior snapshot intact rather than writing misleading zeros.
        if last_input:
            await _persist_last_usage(
                session,
                input_tokens=total_input,
                output_tokens=total_output,
                context_tokens=last_input,
            )

        # M21 F01 L03 (LD1): apply any pending next_turn self-revision at
        # THIS turn's exit — the only non-paused settle site in this
        # function. `or "default"` is load-bearing: Session.agent_name is
        # None for the default agent while the pending registry (and
        # _calling_agent) key on the literal "default"; a skip-on-None
        # guard would silently degrade next_turn to next_session for
        # single-agent installs.
        _self_configuration_pending.apply_pending_revision(
            session.agent_name or "default", session.agent
        )

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

    # M16 F06 L01: resume-path usage accumulator. Initialise before the
    # loop so the settle write (outside the try/except) sees accumulated
    # totals regardless of whether the loop completed normally or raised.
    # ``resume_last_input`` doubles as the zero-usage guard: it stays 0
    # when no assistant usage event arrived, and ``if resume_last_input``
    # suppresses the write to avoid overwriting a prior snapshot with zeros.
    resume_input = 0
    resume_output = 0
    resume_last_input = 0

    try:
        re_paused = False
        async for msg in session.agent.resume_after_auth():
            await _broadcast_one(session, msg, source="resumed")
            # M16 F06 L01: accumulate usage from each resumed assistant
            # message. ``context_tokens`` is the LAST assistant message's
            # ``input_tokens`` (not the sum) — mirrors ``_broadcast_one``'s
            # ``"context_tokens": msg.usage.input_tokens`` at :1290 and the
            # non-paused path's ``last_input`` at :1444.
            if msg.role == Role.ASSISTANT and msg.usage:
                resume_input += msg.usage.input_tokens
                resume_output += msg.usage.output_tokens
                resume_last_input = msg.usage.input_tokens
            if _is_auth_required_pause(msg):
                re_paused = True
                break
        if not re_paused:
            # M21 F01 L03 (LD1): the resumed turn is genuinely settling now
            # — apply any pending next_turn self-revision here too. NOT in
            # the unconditional tail below `_save_session_to_db`, which
            # also runs when the resume re-pauses (that is not a settle).
            _self_configuration_pending.apply_pending_revision(
                session.agent_name or "default", session.agent
            )
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

    # M16 F06 L01: persist the resume-segment usage snapshot. Placed
    # outside the try/except (next to _save_session_to_db) so a partial
    # resume exception still persists whatever usage accumulated before it.
    # ``resume_last_input`` is the zero-usage guard — 0 means no assistant
    # usage event arrived; we leave the prior snapshot intact in that case.
    if resume_last_input:
        await _persist_last_usage(
            session,
            input_tokens=resume_input,
            output_tokens=resume_output,
            context_tokens=resume_last_input,
        )


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
async def index() -> HTMLResponse:
    # Version-scope the /static asset URLs so an in-place upgrade forces the
    # WebView to fetch fresh JS/CSS, and mark the HTML itself no-store so the
    # newly versioned URLs are always picked up. See F09-07.
    return HTMLResponse(
        content=_cache_busted_index_html(),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/info")
async def info() -> dict[str, Any]:
    return {"version": __version__, "base_prompt": BASE_PROMPT}


@app.get(LIVENESS_PATH)
async def liveness() -> dict[str, str]:
    """Minimal unauthenticated liveness probe — Mission 20 / Flight 1 / Leg 2
    (DD5). The credential gate's sole exemption once
    `enforce-and-migrate-harness` registers it; additive and unauthenticated
    here regardless, since nothing about this endpoint enforces anything.

    Returns liveness and nothing else — no version, no prompt, no build
    info, no data directory. It is reachable by any local process by
    design (that is the whole point: bootstrap callers that only need "is
    it up" before they can hold a credential), so anything in this body is
    public to every local process. `/api/info` above stays credentialed
    for exactly this reason (DD5: it returns `base_prompt`).
    """
    return {"status": "ok"}


async def _require_long_lived_caller(request: Request) -> IdentifiedCaller:
    """FastAPI dependency requiring the long-lived credential via
    ``Authorization: Bearer`` — new ground in this codebase (leg
    Implementation Guidance #8): no existing `Depends()`-based header-auth
    pattern exists to match; `Authorization` is otherwise read manually.

    Resolves through `resolve_caller`, the same single entry point the gate
    middleware uses — no separate parsing logic to drift out of sync. This
    is deliberately NOT a check against the gate middleware (which is not
    registered on this app until `enforce-and-migrate-harness`) and NOT a
    check against the session cookie or a handoff credential: a handoff
    token is a structurally different value that never resolves here — so a
    handoff credential cannot be used to mint another one (LD2's closing
    constraint), with no special-casing required to enforce it.

    As of Mission 21, `resolve_caller` also walks the `agt_`/`ext_`
    self-configuration sources, not just the `file` one — so a resolved
    caller alone no longer implies "holds the long-lived credential." The
    confinement middleware (`CredentialGateMiddleware`'s
    `CONFINED_SOURCE_PATHS` check, `middleware.py:377-382`) is the first
    line of defense keeping those sources off this route; the explicit
    `source == "file"` check below is the second, so the property holds by
    construction rather than resting solely on that external control.
    """
    header = request.headers.get("authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        raise HTTPException(status_code=401, detail="Local API credential missing or invalid")
    caller = resolve_caller(header[len(prefix) :])
    if caller is None:
        raise HTTPException(status_code=401, detail="Local API credential missing or invalid")
    if caller.source != "file":
        raise HTTPException(status_code=401, detail="Local API credential missing or invalid")
    return caller


@app.post("/api/session/handoff")
async def mint_session_handoff(
    request: Request,
    caller: IdentifiedCaller = Depends(_require_long_lived_caller),
) -> dict[str, str]:
    """Mint a one-time browser-handoff credential and return a usable
    handoff URL — Mission 20 / Flight 1 / Leg 2 (LD2).

    Authenticated in-route via `_require_long_lived_caller` above, NOT via
    the gate middleware (not registered on this app yet — an unauthenticated
    mint endpoint must not exist even transiently on this branch). Serves
    callers that hold the long-lived credential but run outside this
    server's process and so cannot call `mint_handoff_credential()`
    in-process the way the desktop launcher does (see
    `the_one/interfaces/web/handoff_store.py`) — the browser-test harness
    and the behavior-test runner, per the leg's Reconnaissance Findings.

    Does not weaken the posture: *caller* already holds the long-lived
    credential; this converts it into a strictly weaker, single-use,
    short-lived one.
    """
    del caller  # authentication only — the minted token is not scoped to caller
    token = mint_handoff_credential()
    base_url = str(request.base_url).rstrip("/")
    return {"url": f"{base_url}/?{HANDOFF_QUERY_PARAM}={token}"}


@app.post("/api/window/focus")
async def window_focus() -> dict[str, Any]:
    # Lazy import: the web app must stay importable without the GUI stack
    # (serve mode, CI). The desktop module pulls pywebview only when present.
    from the_one.interfaces.desktop.shell import focus_window

    return {"focused": focus_window()}


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
        s.last_activity = time.monotonic()  # F05 L01: touch on reset
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
                except Exception as exc:
                    # Surface ANY create failure to the UI instead of letting it
                    # escape the WS loop and drop the socket silently. A
                    # provider that can't load (e.g. a tree-shaken provider
                    # module in a frozen build raises ImportError, NOT
                    # ValueError/KeyError) used to crash here → silent chat
                    # death. Catch broadly, log, and tell the client.
                    logger.exception("Failed to auto-create session")
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
                except Exception as exc:
                    # Broad catch (see auto-create note above): a provider whose
                    # module is missing from a frozen bundle raises ImportError,
                    # which is neither ValueError nor KeyError. Letting it escape
                    # crashes the WS handler and drops the socket with no event —
                    # the silent "Ollama agent fails after ~5s" symptom.
                    logger.exception("Failed to create session for agent %r", agent_name)
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
                    # Remove from memory — under _sessions_lock to serialize
                    # with the reaper. F05 L01.
                    async with _sessions_lock:
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

            # F7 L03 (cancel-backend) / F09-03: operator cancel action.
            # Cancels every not-done task for the bound session — both the
            # running turn and any queued (lock-blocked) turn — so "stop"
            # stops everything (F07 DD4). No-op if no session is bound, no
            # tasks are registered, or all tasks already finished — covers
            # the race with natural completion.
            if action == "cancel":
                if session is not None:
                    for t in tuple(_session_inflight.get(session.id, ())):
                        if not t.done():
                            t.cancel()
                continue

            # Regular message. M16 F12 L08: `images` is an optional list of
            # {data, media_type} dicts staged by the frontend attach control.
            # The empty-guard accepts text-OR-images so an image-only turn
            # (empty text box) is not silently dropped.
            user_input = payload.get("message", "")
            images = payload.get("images") or []
            if not user_input and not images:
                continue

            # M18 F02 L02: reject an over-count/over-size images payload
            # BEFORE the auto-join block below — an oversized attachment
            # should not spin up an unnecessary session. Reuses the Leg-1
            # error-surfacing shape (system event + continue) so the loop
            # stays alive.
            if images:
                # Review fix (post-L02): validate SHAPE before the
                # count/size logic below touches it. A non-list `images`
                # (e.g. an int) blows up `len(images)`; a list containing
                # non-dict items (e.g. a bare string, or `images` itself
                # being a string so iteration hands out individual chars)
                # blows up `_approx_image_bytes`'s `.get(...)` call. Both
                # used to propagate out of the `while True` loop, killing
                # the connection — the exact crash class Leg 1 fixes.
                # Reject with the same system-event + continue shape used
                # everywhere else in this handler.
                if not isinstance(images, list) or not all(isinstance(img, dict) for img in images):
                    logger.warning(
                        "Rejected message: malformed images payload (expected a list of objects)"
                    )
                    await ws.send_json(
                        {
                            "type": "system",
                            "content": (
                                "Malformed images payload; expected a list of image objects."
                            ),
                        }
                    )
                    continue
                if len(images) > IMAGE_ATTACHMENT_MAX_COUNT:
                    logger.warning(
                        "Rejected message: %d images exceeds max count %d",
                        len(images),
                        IMAGE_ATTACHMENT_MAX_COUNT,
                    )
                    await ws.send_json(
                        {
                            "type": "system",
                            "content": (
                                f"Too many images attached ({len(images)}); "
                                f"max is {IMAGE_ATTACHMENT_MAX_COUNT}."
                            ),
                        }
                    )
                    continue
                oversized = next(
                    (
                        img
                        for img in images
                        if _approx_image_bytes(img) > IMAGE_ATTACHMENT_CAP_BYTES
                    ),
                    None,
                )
                if oversized is not None:
                    cap_mb = IMAGE_ATTACHMENT_CAP_BYTES // (1024 * 1024)
                    logger.warning(
                        "Rejected message: image exceeds per-image cap of %d bytes",
                        IMAGE_ATTACHMENT_CAP_BYTES,
                    )
                    notice = f"An attached image exceeds the {cap_mb} MB per-image limit."
                    await ws.send_json({"type": "system", "content": notice})
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
            try:
                content = _build_user_content(user_input, images)
            except Exception as exc:
                # M18 F02 L01: NARROW guard around just the content-build
                # call — a malformed image dict (unexpected key -> TypeError
                # from ImageContent(**img); both data/url absent -> the
                # ImageContent guard) used to propagate out of the `while
                # True` loop and drop the connection. The outer `try`
                # (below) already handles WebSocketDisconnect; this inner
                # guard must stay scoped to content-build only so it does
                # not also swallow that disconnect. Mirrors the sibling
                # auto-create except block above (log + system event +
                # continue), using the WS-loop-local `session` directly
                # rather than `_send_to_session` (which broadcasts to every
                # subscriber — wrong call site for a per-connection error).
                logger.exception("Failed to build user content from images payload")
                await ws.send_json({"type": "system", "content": f"Cannot process message: {exc}"})
                continue
            task = asyncio.create_task(_spawn_message_processing(session, content, "web", ws))
            _inflight_tasks.add(task)
            task.add_done_callback(_inflight_tasks.discard)
            # F7 L03 (cancel-backend) / F09-03: add the task to the
            # per-session set so a WS `cancel` action can locate every
            # in-flight task (running + queued). The done-callback discards
            # this task and removes the key once the set is empty.
            _session_inflight.setdefault(session.id, set()).add(task)
            _sid_for_clear = session.id

            def _clear_session_inflight(t: asyncio.Task, _sid: str = _sid_for_clear) -> None:
                tasks = _session_inflight.get(_sid)
                if tasks is None:
                    return
                tasks.discard(t)
                if not tasks:
                    del _session_inflight[_sid]

            task.add_done_callback(_clear_session_inflight)

    except WebSocketDisconnect:
        if session:
            remove_subscriber(session.id, ws)
            # F05 L01: touch last_activity at disconnect so the idle clock
            # starts from the moment the tab is closed, not from the last
            # message. A disconnected session with zero subscribers will be
            # reaped after TTL seconds of inactivity from this point.
            session.last_activity = time.monotonic()
