"""Sortie 22 leg 1: nothing waits for a sign-in no one can give.

Every pool connection and Test connection's saved-tokens phase (Phase A) builds its
OAuth provider with ``interactive=False``: when the stored refresh token fails, the
redirect handler refuses the interactive step at once (``SignInNotAvailable``), so a
chat tool call, a routine run and a connector turn pause immediately instead of
after the 30 s connect timeout.

The timing tests drive the REAL path (a real ``Agent`` with ``FakeLLM`` scripting a
tool call to a real ``MCPClientTool``, which reaches ``_pool.acquire``, then
``_entry_worker``, then the factory) against ``OAuthASStub``. A real hex csid is
bound; without one ``_entry_worker`` substitutes an ``agent_build:`` csid, which
squawk 0422 already refuses, and the tests would pass with the fix removed.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import time
from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from mcp.client.auth.exceptions import OAuthFlowError
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._mcp_pool_helpers import (
    AGENT_NAME,
    CSID,
    SOURCE_ID,
    TOOL_NAME,
    build_registry,
    build_tool,
    oauth_source,
    pool_db,
    reset_pool_state,
    stale_secrets,
    tool_call_script,
)
from tests._mcp_signin_helpers import MemoryStorage, build_provider, http_source
from tests.conftest import FakeLLM
from tests.fixtures.oauth import OAuthASStub
from the_one.agent.core import Agent
from the_one.config import settings
from the_one.connectors import registry
from the_one.connectors.base import InboundEnvelope
from the_one.connectors.inbound import dispatch_inbound
from the_one.connectors.manager import ConnectorManager, set_manager
from the_one.connectors.stub import StubPlugin
from the_one.db.codec import decode_messages
from the_one.db.connection import get_connection
from the_one.db.models import Connector
from the_one.db.repositories import ChatSessionRepository, ConnectorRepository, MCPSourceRepository
from the_one.encryption import get_encryptor
from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import (
    Session,
    _inflight_tasks,
    _session_inflight,
    _silent_cancel,
    _spawn_routine_turn,
)
from the_one.llm.base import Role
from the_one.mcp import _pool
from the_one.mcp.client import MCPClient
from the_one.mcp.errors import MCPAuthRequired
from the_one.mcp.oauth import _state
from the_one.mcp.oauth._log_filter import (
    SDK_OAUTH_LOGGER_NAME,
    SignInRefusalFilter,
    install_sign_in_refusal_filter,
)
from the_one.mcp.oauth.errors import SignInNotAvailable
from the_one.mcp.oauth.handlers import agent_build_csid, make_oauth_handlers
from the_one.mcp.oauth.provider_factory import build_oauth_provider_for_source
from the_one.routines import runner as routine_runner
from the_one.sessions import clear_for_test as _clear_session_registry

SHAPES = ["expired", "revoked"]
"""``expired``: the squawk 0444 refresh-first path. ``revoked``: locally valid,
server-rejected, then a 401 starts the flow."""

AUTHORIZE_URL = "http://127.0.0.1:1/authorize?state=abc"


@pytest.fixture(autouse=True)
async def _clean_pool_state(monkeypatch):
    # A real timeout, well above the assertions: a refusal that is NOT immediate fails
    # the timing asserts instead of racing the connect timeout.
    monkeypatch.setattr("the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS", 10.0)
    await reset_pool_state()
    yield
    await reset_pool_state()
    for t in list(_inflight_tasks):
        t.cancel()
    if _inflight_tasks:
        await asyncio.gather(*list(_inflight_tasks), return_exceptions=True)
    _inflight_tasks.clear()
    _session_inflight.clear()
    _silent_cancel.clear()
    _clear_session_registry()


@pytest.fixture
def chat_frames(monkeypatch):
    """A Session registered under ``CSID``; every frame sent to it is captured."""
    frames: list[dict] = []

    async def capture(session, payload, exclude=None):
        frames.append(payload)

    monkeypatch.setattr(web_app, "_send_to_session", capture)
    sess = Session(id=CSID, agent=None, created=datetime.now(timezone.utc).isoformat())  # type: ignore[arg-type]
    web_app._sessions[CSID] = sess
    try:
        yield frames
    finally:
        web_app._sessions.pop(CSID, None)


def _oauth_stub(**extra) -> OAuthASStub:
    return OAuthASStub(refresh_status=400, **extra)


def _make_agent(source) -> Agent:
    tool = build_tool(source)
    return Agent(FakeLLM(tool_call_script(tool)), build_registry(tool), "sys")


async def _run_turn(agent: Agent, csid: str = CSID) -> list:
    from the_one.agent._context import current_chat_session_id

    token = current_chat_session_id.set(csid)
    try:
        return [m async for m in agent.step("go")]
    finally:
        current_chat_session_id.reset(token)


def _assert_paused(agent: Agent, messages: list) -> None:
    tool_msgs = [m for m in messages if m.role == Role.TOOL]
    assert tool_msgs and tool_msgs[-1].tool_result.metadata["is_auth_required"] is True
    assert agent._deferred_tool_calls is not None


# --- the handlers ------------------------------------------------------------------------


def test_interactive_is_a_keyword_only_parameter_that_defaults_true() -> None:
    for fn in (make_oauth_handlers, build_oauth_provider_for_source):
        param = inspect.signature(fn).parameters["interactive"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY
        assert param.default is True


def test_the_refusal_is_an_oauth_flow_error() -> None:
    assert issubclass(SignInNotAvailable, OAuthFlowError)  # MCPClient's except* arms catch it


async def test_non_interactive_redirect_refuses_without_registering_or_broadcasting(
    chat_frames,
) -> None:
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    redirect, _callback = make_oauth_handlers(
        chat_session_id=CSID,
        source_id="src",
        tool_call_id="tc",
        resource_metadata_url=None,
        consent_url_future=future,
        interactive=False,
    )
    with pytest.raises(SignInNotAvailable):
        await redirect(AUTHORIZE_URL)
    assert not _state._pending
    assert chat_frames == []
    assert not future.done()  # the consent future stays unresolved


async def test_agent_build_csid_raises_the_same_refusal() -> None:
    redirect, _ = make_oauth_handlers(
        chat_session_id=agent_build_csid("src"),
        source_id="src",
        tool_call_id=None,
        resource_metadata_url=None,
    )
    with pytest.raises(SignInNotAvailable):
        await redirect(AUTHORIZE_URL)
    assert not _state._pending


async def test_interactive_redirect_still_registers_broadcasts_and_resolves(chat_frames) -> None:
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    redirect, _ = make_oauth_handlers(
        chat_session_id=CSID,
        source_id="src",
        tool_call_id="tc",
        resource_metadata_url=None,
        consent_url_future=future,
    )
    await redirect(AUTHORIZE_URL)
    assert "abc" in _state._pending
    assert future.result() == AUTHORIZE_URL
    assert [f["type"] for f in chat_frames] == ["auth_required"]


# --- a pool connection refuses at once ------------------------------------------------------


@pytest.mark.parametrize("shape", SHAPES)
async def test_pool_acquire_refuses_at_once(tmp_path, monkeypatch, chat_frames, shape) -> None:
    from the_one.agent._context import current_chat_session_id

    with _oauth_stub() as stub:
        source = oauth_source(stub.base_url, shape)
        async with pool_db(tmp_path, monkeypatch, source):
            token = current_chat_session_id.set(CSID)
            try:
                started = time.monotonic()
                with pytest.raises(MCPAuthRequired):
                    await _pool.acquire(AGENT_NAME, SOURCE_ID, source_override=source)
                elapsed = time.monotonic() - started
            finally:
                current_chat_session_id.reset(token)
    assert elapsed < 2.0
    assert not _state._pending  # no flow registered
    assert [f for f in chat_frames if f.get("type") == "auth_required"] == []


@pytest.mark.parametrize("shape", SHAPES)
async def test_chat_tool_call_pauses_at_once(tmp_path, monkeypatch, chat_frames, shape) -> None:
    with _oauth_stub() as stub:
        source = oauth_source(stub.base_url, shape)
        async with pool_db(tmp_path, monkeypatch, source):
            agent = _make_agent(source)
            started = time.monotonic()
            messages = await _run_turn(agent)
            elapsed = time.monotonic() - started
    assert elapsed < 2.0
    _assert_paused(agent, messages)
    assert not _state._pending


# --- a routine run -----------------------------------------------------------------------------


@pytest.mark.parametrize("shape", SHAPES)
async def test_routine_run_ends_needing_a_sign_in(tmp_path, monkeypatch, shape) -> None:
    frames: list[dict] = []

    async def fake_send(sess, payload, exclude=None):
        frames.append(payload)

    async def noop(sess):
        pass

    monkeypatch.setattr(web_app, "_send_to_session", fake_send)
    monkeypatch.setattr(web_app, "_save_session_to_db", noop)
    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", noop)
    monkeypatch.setattr(web_app, "_resync_session_from_db", noop)

    with _oauth_stub() as stub:
        source = oauth_source(stub.base_url, shape)
        async with pool_db(tmp_path, monkeypatch, source):
            agent = _make_agent(source)
            session = Session(
                id="s-routine-signin",
                agent=agent,
                created=datetime.now(timezone.utc).isoformat(),
            )
            info: dict[str, Any] = {"routine": {"id": "r1", "name": "x"}}
            started = time.monotonic()
            task = _spawn_routine_turn(session, "go", info)
            await asyncio.wait_for(task, timeout=8)
            elapsed = time.monotonic() - started
    assert elapsed < 5.0
    assert info["paused"] == "pool-stub"
    outcome, reason = routine_runner.classify("done", info, timed_out=False, timeout_seconds=60.0)
    assert outcome == "failed"
    assert reason.startswith("Needs a sign-in to pool-stub")


# --- a connector turn -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_connector_registry():
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    yield
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    from the_one.agent.factory import set_factory

    set_factory(None)
    set_manager(None)


@pytest.mark.parametrize("shape", SHAPES)
async def test_connector_turn_ends_paused(isolated_db, monkeypatch, shape) -> None:
    from the_one.agent.config import AgentConfig
    from the_one.agent.factory import set_factory
    from the_one.db.repositories import SQLiteAgentStore

    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    await SQLiteAgentStore(conn).save(AgentConfig(name="bot"))
    connector = Connector(
        id="conn-1",
        name="Test",
        type="stub",
        config={"default_agent": "bot", "allowlist": {"peers": ["peer-1"]}},
    )
    await ConnectorRepository(conn, encryptor).create(connector)
    registry.register_for_test("stub", StubPlugin())
    mgr = ConnectorManager()

    with _oauth_stub() as stub:
        source = oauth_source(stub.base_url, shape)
        await MCPSourceRepository(conn, encryptor).create(source)
        agents: list[Agent] = []

        class _Factory:
            async def create(self, name: str):
                agent = _make_agent(source)
                agents.append(agent)
                return agent

        set_factory(_Factory())  # type: ignore[arg-type]
        envelope = InboundEnvelope(
            platform="stub",
            connector_id="conn-1",
            channel_id="dm-1",
            thread_id=None,
            peer_id="peer-1",
            peer_name="Alice",
            text="go",
            is_dm=True,
            mentions_bot=False,
        )
        started = time.monotonic()
        await asyncio.wait_for(dispatch_inbound("conn-1", envelope, manager=mgr), timeout=8)
        elapsed = time.monotonic() - started

    assert elapsed < 5.0
    assert len(agents) == 1
    assert agents[0]._deferred_tool_calls is not None
    sessions = await ChatSessionRepository(conn).list()
    persisted = decode_messages(sessions[0].messages)
    assert persisted[-1].role == Role.TOOL
    assert persisted[-1].tool_result.metadata["is_auth_required"] is True


# --- a warm pooled connection ---------------------------------------------------------


async def test_warm_connection_pauses_when_the_server_revokes_its_token(
    tmp_path, monkeypatch, chat_frames
) -> None:
    from the_one.agent._context import current_chat_session_id

    with OAuthASStub() as stub:
        source = oauth_source(stub.base_url, "revoked")
        source.secrets["access_token"] = "stub-access-token"  # the stub's valid token
        async with pool_db(tmp_path, monkeypatch, source) as (_conn, repo):
            token = current_chat_session_id.set(CSID)
            try:
                client = await _pool.acquire(AGENT_NAME, SOURCE_ID, source_override=source)
                assert (await client.call_tool(TOOL_NAME, {})).text == "ok"
            finally:
                current_chat_session_id.reset(token)

            # The server now revokes the grant: the old token is rejected, refresh fails,
            # and the stored token is past its expiry.
            stub.config["valid_token"] = "rotated-token"
            stub.config["refresh_status"] = 400
            stored = await repo.get(SOURCE_ID)
            stored.secrets["token_expires_at"] = time.time() - 100
            await repo.update(stored)

            agent = _make_agent(source)
            started = time.monotonic()
            messages = await _run_turn(agent)
            elapsed = time.monotonic() - started
    assert elapsed < 2.0  # well under the 30 s tool timeout that could otherwise mask it
    _assert_paused(agent, messages)
    assert not _state._pending


# --- Test connection's saved-tokens phase (Phase A) -----------------------------------


@pytest.fixture
async def api_world(tmp_path, monkeypatch):
    from unittest.mock import patch

    from cryptography.fernet import Fernet

    from tests._schema_template import connect_template_db
    from the_one.encryption import Encryptor

    conn = await connect_template_db(tmp_path / "phase-a.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as client:
            yield client, repo
    await conn.close()


def _library_source(base_url: str, sid: str) -> Any:
    from the_one.db.models import MCPSource

    return MCPSource(
        id=sid,
        name="phase-a",
        type="streamable-http",
        config={"url": f"{base_url}/mcp", "_cache": {"auth_posture": "oauth"}},
        secrets=stale_secrets("revoked"),
    )


async def test_library_test_falls_through_to_phase_b_without_the_connect_wait(api_world) -> None:
    client, repo = api_world
    with _oauth_stub() as stub:
        await repo.create(_library_source(stub.base_url, "src-a"))
        started = time.monotonic()
        resp = await client.post("/api/mcp-sources/src-a/test/connect")
        elapsed = time.monotonic() - started
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "auth_required", body
        assert body["consent_url"].startswith(f"{stub.base_url}/authorize")  # Phase B registered it
    assert elapsed < 5.0  # Phase A did not park for the 10 s connect timeout
    assert _state._pending  # Phase B (interactive) registered a flow


async def test_per_agent_test_returns_auth_required_fast_and_touches_no_tokens(api_world) -> None:
    client, repo = api_world
    with _oauth_stub() as stub:
        await repo.create(_library_source(stub.base_url, "src-b"))
        before = (await repo.get("src-b")).secrets
        started = time.monotonic()
        resp = await client.post("/api/mcp-sources/src-b/test/agent", json={"agent": None})
        elapsed = time.monotonic() - started
        assert resp.status_code == 200
        assert resp.json() == {"status": "auth_required"}
        assert (await repo.get("src-b")).secrets == before
    assert elapsed < 5.0
    assert not _state._pending


# --- the log filter -------------------------------------------------------------------


def _stale_provider(base_url: str, *, interactive: bool):
    redirect, callback = make_oauth_handlers(
        chat_session_id=CSID,
        source_id="src-oauth",
        tool_call_id=None,
        resource_metadata_url=None,
        interactive=interactive,
    )
    storage = MemoryStorage(
        OAuthToken(
            access_token="expired-access-token",
            token_type="Bearer",
            refresh_token="revoked-refresh-token",
            expires_in=3600,
        )
    )
    storage.client_info = OAuthClientInformationFull(
        client_id="stub-client-1",
        redirect_uris=["http://127.0.0.1:1/api/oauth/callback"],
        token_endpoint_auth_method="none",
    )
    from mcp.client.auth import OAuthClientProvider

    provider = OAuthClientProvider(
        server_url=f"{base_url}/mcp",
        client_metadata=OAuthClientMetadata(
            client_name="the-one",
            redirect_uris=["http://127.0.0.1:1/api/oauth/callback"],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
        ),
        storage=storage,
        redirect_handler=redirect,
        callback_handler=callback,
    )
    provider.context.token_expiry_time = time.time() + 3600
    return provider


def _flow_error_records(caplog) -> list[logging.LogRecord]:
    return [
        r for r in caplog.records if r.name == SDK_OAUTH_LOGGER_NAME and r.levelno >= logging.ERROR
    ]


async def test_a_refusal_logs_no_error_record(caplog) -> None:
    caplog.set_level(logging.ERROR, SDK_OAUTH_LOGGER_NAME)
    with _oauth_stub() as stub:
        client = MCPClient(
            http_source(stub.base_url),
            auth_provider=_stale_provider(stub.base_url, interactive=False),
        )
        with pytest.raises(MCPAuthRequired):
            await client.connect()
    assert _flow_error_records(caplog) == []


async def test_the_refusal_reaches_the_sdk_log_call_unwrapped(caplog) -> None:
    """Without the filter the SDK logs the refusal itself: the exception on the record
    is the bare ``SignInNotAvailable`` (so the filter's ``isinstance`` check is sound)."""
    sdk_logger = logging.getLogger(SDK_OAUTH_LOGGER_NAME)
    ours = [f for f in sdk_logger.filters if isinstance(f, SignInRefusalFilter)]
    for f in ours:
        sdk_logger.removeFilter(f)
    try:
        caplog.set_level(logging.ERROR, SDK_OAUTH_LOGGER_NAME)
        with _oauth_stub() as stub:
            client = MCPClient(
                http_source(stub.base_url),
                auth_provider=_stale_provider(stub.base_url, interactive=False),
            )
            with pytest.raises(MCPAuthRequired):
                await client.connect()
        records = _flow_error_records(caplog)
        assert records and records[0].getMessage() == "OAuth flow error"
        assert type(records[0].exc_info[1]) is SignInNotAvailable
    finally:
        for f in ours:
            sdk_logger.addFilter(f)


async def test_another_oauth_error_still_logs(caplog) -> None:
    caplog.set_level(logging.ERROR, SDK_OAUTH_LOGGER_NAME)
    with OAuthASStub(token_status=500) as stub:
        provider, _storage = build_provider(stub.base_url)
        client = MCPClient(http_source(stub.base_url), auth_provider=provider)
        with contextlib.suppress(Exception):
            await client.connect()
    records = _flow_error_records(caplog)
    assert records, "a token endpoint 500 must still log"
    assert not isinstance(records[0].exc_info[1], SignInNotAvailable)


def test_the_filter_is_installed_once() -> None:
    sdk_logger = logging.getLogger(SDK_OAUTH_LOGGER_NAME)
    install_sign_in_refusal_filter()
    install_sign_in_refusal_filter()
    assert len([f for f in sdk_logger.filters if isinstance(f, SignInRefusalFilter)]) == 1
