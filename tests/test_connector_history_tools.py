"""Tests for the F7 L10 channel-context built-in tools.

Covers:

- Registry presence in ``_TOOL_CLASSES`` and the introspection /
  factory paths through ``BuiltinToolProvider.get_tools``.
- The four tool surfaces' four failure modes (outside-connector;
  ACL-denied; missing plugin hook; hook-raised exception) and happy
  path for each.
- ``list_visible_channels`` cache-preferred / live-fallback / missing-
  hook semantics + the ``fetched_at`` drop.
- Cycle-1 additions: session lookup failure path returns the same
  outside-connector envelope; ``fetched_at`` is omitted from the
  list_visible_channels response.

Fixtures (`isolated_db`, `_clear_pool_and_registry`, `_reset_stub_state`)
mirror :mod:`tests.test_connector_send_tool` verbatim — F7 L10
re-uses the same scaffolding for parity with the F4 L2 precedent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import aiosqlite
import pytest

from the_one.agent._context import current_chat_session_id
from the_one.config import settings
from the_one.connectors import _pool as pool_mod
from the_one.connectors._stub import StubPlugin
from the_one.connectors.base import (
    DiscoverableEntities,
    DiscoverableEntity,
    FetchedMessage,
)
from the_one.connectors.registry import (
    clear_for_test as _registry_clear_for_test,
)
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.connection import get_connection
from the_one.db.models import ChatSession, Connector
from the_one.db.repositories import (
    ChatSessionRepository,
    ConnectorRepository,
)
from the_one.db.schema import ensure_schema
from the_one.encryption import get_encryptor
from the_one.tools.builtins import _TOOL_CLASSES, BuiltinToolProvider
from the_one.tools.connector_history import (
    FetchChannelHistoryTool,
    FetchDmHistoryTool,
    FetchThreadHistoryTool,
    ListVisibleChannelsTool,
)

# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_stub_state():
    StubPlugin.reset_for_test()
    yield
    StubPlugin.reset_for_test()


@pytest.fixture(autouse=True)
async def _clear_pool_and_registry():
    yield
    await pool_mod._clear_for_test()
    _registry_clear_for_test()
    restore_to_baseline_for_test()


@pytest.fixture(autouse=True)
def _reset_csid():
    """Reset ``current_chat_session_id`` between tests.

    Tests that set the ContextVar reset it locally via ``.reset(token)``
    in their own finally blocks; this autouse fixture is a belt-and-
    suspenders default for the no-token path.
    """
    token = current_chat_session_id.set(None)
    yield
    current_chat_session_id.reset(token)


@pytest.fixture
async def isolated_db(tmp_path, monkeypatch):
    from the_one.db import connection as db_connection

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    db_path = settings.db_path

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    await conn.close()

    monkeypatch.setattr(db_connection, "_connection", None)
    yield db_path

    if db_connection._connection is not None:
        await db_connection.close_connection()


async def _seed_stub_account(
    account_id: str = "acct-hist", config: dict | None = None
) -> Connector:
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    repo = ConnectorRepository(conn, encryptor)
    account = Connector(
        id=account_id,
        name=f"Stub {account_id}",
        type="stub",
        config=config or {},
        secrets={},
    )
    await repo.create(account)
    return account


async def _seed_connector_session(
    session_id: str = "cs-history",
    account_id: str = "acct-hist",
    channel_id: str = "ch-1",
    thread_id: str | None = None,
    peer_id: str = "peer-1",
) -> str:
    """Persist a connector-attached chat session row and return its id.

    The tools resolve the connector account via
    ``ChatSessionRepository.get(current_chat_session_id.get())`` then
    read ``session.connector_id``. This helper sets up that
    chain end-to-end.
    """
    conn = await get_connection()
    repo = ChatSessionRepository(conn)
    await repo.create(
        ChatSession(
            id=session_id,
            agent_name="agent-hist",
            title="connector session",
            platform="stub",
            connector_id=account_id,
            channel_id=channel_id,
            thread_id=thread_id,
            peer_id=peer_id,
            messages="[]",
        )
    )
    return session_id


def _bind_csid(session_id: str | None):
    """Return a token; caller is responsible for ``.reset(token)``."""
    return current_chat_session_id.set(session_id)


def _sample_fetched_messages() -> list[FetchedMessage]:
    return [
        FetchedMessage(
            peer_id="user-1",
            peer_name="alice",
            content="hello",
            ts="2026-01-01T00:00:00+00:00",
            thread_id=None,
        ),
        FetchedMessage(
            peer_id="user-2",
            peer_name="bob",
            content="hi back",
            ts="2026-01-01T00:00:01+00:00",
            thread_id=None,
        ),
    ]


# Test-only helpers grafted onto the StubPlugin per-test via setattr.
# StubPlugin is a class object; we install methods on instances/classes
# locally so the missing-hook tests (which use the bare class) still
# exercise the ``getattr(plugin, ..., None)`` sentinel path.


class _StubPluginWithFetch(StubPlugin):
    """Subclass that implements the L10 fetch hooks for happy-path tests."""

    fetch_history_calls: list[tuple[Any, str, str | None, int]] = []
    fetch_dm_history_calls: list[tuple[Any, str, int]] = []
    fetch_should_raise: BaseException | None = None
    fetch_dm_should_raise: BaseException | None = None
    fetch_response: list[FetchedMessage] | None = None
    fetch_dm_response: list[FetchedMessage] | None = None
    enumerate_response: DiscoverableEntities | None = None

    @classmethod
    def reset_local(cls) -> None:
        cls.fetch_history_calls = []
        cls.fetch_dm_history_calls = []
        cls.fetch_should_raise = None
        cls.fetch_dm_should_raise = None
        cls.fetch_response = None
        cls.fetch_dm_response = None
        cls.enumerate_response = None

    async def fetch_history(
        self,
        client: Any,
        channel_id: str,
        thread_id: str | None,
        limit: int,
    ) -> list[FetchedMessage]:
        type(self).fetch_history_calls.append((client, channel_id, thread_id, limit))
        if type(self).fetch_should_raise is not None:
            raise type(self).fetch_should_raise
        if type(self).fetch_response is None:
            return _sample_fetched_messages()
        return type(self).fetch_response

    async def fetch_dm_history(
        self,
        client: Any,
        peer_id: str,
        limit: int,
    ) -> list[FetchedMessage]:
        type(self).fetch_dm_history_calls.append((client, peer_id, limit))
        if type(self).fetch_dm_should_raise is not None:
            raise type(self).fetch_dm_should_raise
        if type(self).fetch_dm_response is None:
            return _sample_fetched_messages()
        return type(self).fetch_dm_response

    def enumerate_discoverable_entities(
        self, client: Any
    ) -> DiscoverableEntities:
        if type(self).enumerate_response is not None:
            return type(self).enumerate_response
        return DiscoverableEntities(
            peers=[DiscoverableEntity(id="user-1", label="@alice")],
            channels=[DiscoverableEntity(id="ch-1", label="#general")],
            groups=[DiscoverableEntity(id="g-1", label="Guild")],
            roles=[DiscoverableEntity(id="r-1", label="@everyone")],
            fetched_at=datetime.now(UTC).isoformat(),
        )


@pytest.fixture(autouse=True)
def _reset_local_stub():
    _StubPluginWithFetch.reset_local()
    yield
    _StubPluginWithFetch.reset_local()


# ─── Tool-registration tests ─────────────────────────────────────────────


class TestRegistry:
    def test_builtin_provider_includes_four_history_tools(self) -> None:
        # Both via _TOOL_CLASSES and via the introspection path.
        for name in (
            "fetch_channel_history",
            "fetch_thread_history",
            "fetch_dm_history",
            "list_visible_channels",
        ):
            assert name in _TOOL_CLASSES, name

        tools = BuiltinToolProvider().get_tools()
        tool_names = {t.name for t in tools}
        assert {
            "fetch_channel_history",
            "fetch_thread_history",
            "fetch_dm_history",
            "list_visible_channels",
        }.issubset(tool_names)

    def test_factory_path_threads_connector_kwargs_to_history_tools(
        self,
    ) -> None:
        # The factory path must inject ``connector_ids`` and
        # ``connector_acls`` into the four new tools (same as
        # SendToPlatformChannelTool).
        acls = {"acct-hist": {"channels": ["ch-1"], "peers": None}}
        tools = BuiltinToolProvider().get_tools(
            {},
            {},
            agent_name="agent-a",
            connector_ids=["acct-hist"],
            connector_acls=acls,
        )
        for tool_name in (
            "fetch_channel_history",
            "fetch_thread_history",
            "fetch_dm_history",
            "list_visible_channels",
        ):
            tool = next(t for t in tools if t.name == tool_name)
            assert tool._connector_ids == ["acct-hist"]
            assert tool._connector_acls == acls
            assert tool._agent_name == "agent-a"


# ─── fetch_channel_history tests ─────────────────────────────────────────


class TestFetchChannelHistory:
    async def test_fetch_channel_history_outside_connector_returns_error(
        self,
    ) -> None:
        # current_chat_session_id is None (autouse fixture).
        tool = FetchChannelHistoryTool()
        result = await tool.execute(channel_id="ch-1")
        assert result == [
            {
                "error": (
                    "this tool is only available in a connector-attached session"
                )
            }
        ]

    async def test_fetch_channel_history_denied_by_agent_acl_returns_error(
        self, isolated_db
    ) -> None:
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()

        # M11 F12 L3 — channels use structured tuples.
        acls = {
            "acct-hist": {
                "channels": [{"guild_id": None, "channel_id": "ch-other"}],
                "peers": None,
            }
        }
        tool = FetchChannelHistoryTool(
            connector_ids=["acct-hist"],
            connector_acls=acls,
        )

        token = _bind_csid(sid)
        try:
            result = await tool.execute(channel_id="ch-1")
        finally:
            current_chat_session_id.reset(token)
        assert len(result) == 1
        assert "error" in result[0]
        assert "agent not permitted to read channel ch-1" in result[0]["error"]

    async def test_fetch_channel_history_missing_plugin_hook_returns_error(
        self, isolated_db
    ) -> None:
        # Base StubPlugin doesn't implement fetch_history → missing-hook
        # error envelope.
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)
        sid = await _seed_connector_session()

        tool = FetchChannelHistoryTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute(channel_id="ch-1")
        finally:
            current_chat_session_id.reset(token)
        assert result == [
            {"error": "this plugin does not support history fetch"}
        ]

    async def test_fetch_channel_history_returns_messages(
        self, isolated_db
    ) -> None:
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()

        tool = FetchChannelHistoryTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute(channel_id="ch-1", limit=5)
        finally:
            current_chat_session_id.reset(token)
        assert len(result) == 2
        assert result[0] == {
            "peer_id": "user-1",
            "peer_name": "alice",
            "content": "hello",
            "ts": "2026-01-01T00:00:00+00:00",
            "thread_id": None,
        }
        # Hook called with (client, channel_id, thread_id=None, limit).
        assert len(_StubPluginWithFetch.fetch_history_calls) == 1
        _client, ch, th, lim = _StubPluginWithFetch.fetch_history_calls[0]
        assert ch == "ch-1"
        assert th is None
        assert lim == 5

    async def test_fetch_channel_history_plugin_exception_returns_error_dict(
        self, isolated_db
    ) -> None:
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()
        _StubPluginWithFetch.fetch_should_raise = RuntimeError("boom")

        tool = FetchChannelHistoryTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute(channel_id="ch-1")
        finally:
            current_chat_session_id.reset(token)
        assert len(result) == 1
        assert "error" in result[0]
        assert "fetch_history failed" in result[0]["error"]
        assert "RuntimeError" in result[0]["error"]
        assert "boom" in result[0]["error"]


# ─── fetch_thread_history tests ──────────────────────────────────────────


class TestFetchThreadHistory:
    async def test_fetch_thread_history_outside_connector_returns_error(
        self,
    ) -> None:
        tool = FetchThreadHistoryTool()
        result = await tool.execute(channel_id="ch-1", thread_id="t-1")
        assert result == [
            {
                "error": (
                    "this tool is only available in a connector-attached session"
                )
            }
        ]

    async def test_fetch_thread_history_denied_by_agent_acl_returns_error(
        self, isolated_db
    ) -> None:
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()

        # M11 F12 L3 — channels use structured tuples.
        acls = {
            "acct-hist": {
                "channels": [{"guild_id": None, "channel_id": "ch-other"}],
                "peers": None,
            }
        }
        tool = FetchThreadHistoryTool(
            connector_ids=["acct-hist"], connector_acls=acls
        )
        token = _bind_csid(sid)
        try:
            result = await tool.execute(channel_id="ch-1", thread_id="t-1")
        finally:
            current_chat_session_id.reset(token)
        assert len(result) == 1
        assert "agent not permitted to read channel ch-1" in result[0]["error"]

    async def test_fetch_thread_history_missing_plugin_hook_returns_error(
        self, isolated_db
    ) -> None:
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)
        sid = await _seed_connector_session()

        tool = FetchThreadHistoryTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute(channel_id="ch-1", thread_id="t-1")
        finally:
            current_chat_session_id.reset(token)
        assert result == [
            {"error": "this plugin does not support history fetch"}
        ]

    async def test_fetch_thread_history_returns_messages(
        self, isolated_db
    ) -> None:
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()

        tool = FetchThreadHistoryTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute(
                channel_id="ch-1", thread_id="t-1", limit=3
            )
        finally:
            current_chat_session_id.reset(token)
        assert len(result) == 2
        # Hook was called with thread_id="t-1" (NOT None).
        assert len(_StubPluginWithFetch.fetch_history_calls) == 1
        _client, ch, th, lim = _StubPluginWithFetch.fetch_history_calls[0]
        assert ch == "ch-1"
        assert th == "t-1"
        assert lim == 3

    async def test_fetch_thread_history_plugin_exception_returns_error_dict(
        self, isolated_db
    ) -> None:
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()
        _StubPluginWithFetch.fetch_should_raise = ValueError("bad thread")

        tool = FetchThreadHistoryTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute(channel_id="ch-1", thread_id="t-1")
        finally:
            current_chat_session_id.reset(token)
        assert "fetch_history failed" in result[0]["error"]
        assert "ValueError" in result[0]["error"]


# ─── fetch_dm_history tests ──────────────────────────────────────────────


class TestFetchDmHistory:
    async def test_fetch_dm_history_outside_connector_returns_error(
        self,
    ) -> None:
        tool = FetchDmHistoryTool()
        result = await tool.execute(peer_id="user-9")
        assert result == [
            {
                "error": (
                    "this tool is only available in a connector-attached session"
                )
            }
        ]

    async def test_fetch_dm_history_denied_by_agent_peer_acl_returns_error(
        self, isolated_db
    ) -> None:
        # Per-agent peers axis is explicitly empty → deny (NOT a DMs-only
        # sentinel; that's channels=[]).
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()

        acls = {"acct-hist": {"channels": None, "peers": []}}
        tool = FetchDmHistoryTool(
            connector_ids=["acct-hist"], connector_acls=acls
        )
        token = _bind_csid(sid)
        try:
            result = await tool.execute(peer_id="user-9")
        finally:
            current_chat_session_id.reset(token)
        assert len(result) == 1
        assert "agent not permitted to read peer user-9" in result[0]["error"]

    async def test_fetch_dm_history_account_scope_peers_denies(
        self, isolated_db
    ) -> None:
        # Account-scope allowlist.peers narrows to "user-1" only; the
        # tool asks for "user-9" → deny.
        # M11 F17 L8 (Leg D) — peers stored as bare ``{id}`` post-v28.
        await _seed_stub_account(
            config={"allowlist": {
                "peers": [{"id": "user-1"}],
                "channels": [],
            }}
        )
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()

        tool = FetchDmHistoryTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute(peer_id="user-9")
        finally:
            current_chat_session_id.reset(token)
        assert "agent not permitted to read peer user-9" in result[0]["error"]

    async def test_fetch_dm_history_missing_plugin_hook_returns_error(
        self, isolated_db
    ) -> None:
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)
        sid = await _seed_connector_session()

        tool = FetchDmHistoryTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute(peer_id="user-1")
        finally:
            current_chat_session_id.reset(token)
        assert result == [
            {"error": "this plugin does not support history fetch"}
        ]

    async def test_fetch_dm_history_returns_messages(self, isolated_db) -> None:
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()

        tool = FetchDmHistoryTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute(peer_id="user-1", limit=2)
        finally:
            current_chat_session_id.reset(token)
        assert len(result) == 2
        assert result[0]["peer_id"] == "user-1"
        assert len(_StubPluginWithFetch.fetch_dm_history_calls) == 1
        _client, pid, lim = _StubPluginWithFetch.fetch_dm_history_calls[0]
        assert pid == "user-1"
        assert lim == 2

    async def test_fetch_dm_history_plugin_exception_returns_error_dict(
        self, isolated_db
    ) -> None:
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()
        _StubPluginWithFetch.fetch_dm_should_raise = RuntimeError("dm boom")

        tool = FetchDmHistoryTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute(peer_id="user-1")
        finally:
            current_chat_session_id.reset(token)
        assert "fetch_dm_history failed" in result[0]["error"]
        assert "RuntimeError" in result[0]["error"]
        assert "dm boom" in result[0]["error"]


# ─── list_visible_channels tests ─────────────────────────────────────────


class TestListVisibleChannels:
    async def test_list_visible_channels_outside_connector_returns_error_dict(
        self,
    ) -> None:
        tool = ListVisibleChannelsTool()
        result = await tool.execute()
        assert result == {
            "error": (
                "this tool is only available in a connector-attached session"
            ),
            "peers": [],
            "channels": [],
            "groups": [],
            "roles": [],
        }

    async def test_list_visible_channels_uses_cache_snapshot_when_present(
        self, isolated_db, monkeypatch
    ) -> None:
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()

        # Inject a cache snapshot directly via monkeypatching
        # ``_get_account_cache_snapshot`` so we don't have to drive
        # the full pool warmup path. The function is on
        # the_one.connectors._pool; the tool imports it function-locally.
        cached = DiscoverableEntities(
            peers=[DiscoverableEntity(id="user-cached", label="@cached")],
            channels=[DiscoverableEntity(id="ch-cached", label="#cached")],
            groups=[],
            roles=[],
            fetched_at="2026-01-01T00:00:00+00:00",
        )

        class _Snap:
            cache = cached
            stale_carry = None
            fetched_at_monotonic = 0.0
            account_type = "stub"

        async def _fake_snapshot(account_id: str):
            return _Snap()

        monkeypatch.setattr(
            pool_mod, "_get_account_cache_snapshot", _fake_snapshot
        )

        tool = ListVisibleChannelsTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute()
        finally:
            current_chat_session_id.reset(token)

        assert "error" not in result
        assert result["peers"] == [
            {"id": "user-cached", "label": "@cached", "group": None, "metadata": {}}
        ]
        assert result["channels"] == [
            {"id": "ch-cached", "label": "#cached", "group": None, "metadata": {}}
        ]
        assert result["groups"] == []
        assert result["roles"] == []
        # ``fetched_at`` is intentionally omitted from the response.
        assert "fetched_at" not in result

    async def test_list_visible_channels_falls_back_to_live_hook_when_cache_empty(
        self, isolated_db, monkeypatch
    ) -> None:
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()

        # Snapshot returns None → tool falls back to the plugin hook.
        async def _fake_snapshot(account_id: str):
            return None

        monkeypatch.setattr(
            pool_mod, "_get_account_cache_snapshot", _fake_snapshot
        )

        _StubPluginWithFetch.enumerate_response = DiscoverableEntities(
            peers=[DiscoverableEntity(id="live-user", label="@live")],
            channels=[],
            groups=[],
            roles=[],
            fetched_at="2026-01-01T00:00:00+00:00",
        )

        tool = ListVisibleChannelsTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute()
        finally:
            current_chat_session_id.reset(token)
        assert result["peers"] == [
            {"id": "live-user", "label": "@live", "group": None, "metadata": {}}
        ]
        assert "fetched_at" not in result

    async def test_list_visible_channels_missing_hook_returns_error_dict(
        self, isolated_db, monkeypatch
    ) -> None:
        await _seed_stub_account()
        # Base StubPlugin lacks enumerate_discoverable_entities.
        register_for_test("stub", StubPlugin)
        sid = await _seed_connector_session()

        async def _fake_snapshot(account_id: str):
            return None

        monkeypatch.setattr(
            pool_mod, "_get_account_cache_snapshot", _fake_snapshot
        )

        tool = ListVisibleChannelsTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute()
        finally:
            current_chat_session_id.reset(token)
        assert result == {
            "error": "this plugin does not support entity enumeration",
            "peers": [],
            "channels": [],
            "groups": [],
            "roles": [],
        }


# ─── Cycle-1 additions ───────────────────────────────────────────────────


class TestCycle1Additions:
    async def test_fetch_channel_history_session_lookup_failure_returns_error(
        self, isolated_db
    ) -> None:
        # current_chat_session_id is set but the session row does not
        # exist → ChatSessionRepository.get raises KeyError → tool
        # returns the outside-connector error envelope gracefully.
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)

        tool = FetchChannelHistoryTool(connector_ids=["acct-hist"])
        token = _bind_csid("cs-does-not-exist")
        try:
            result = await tool.execute(channel_id="ch-1")
        finally:
            current_chat_session_id.reset(token)
        assert result == [
            {
                "error": (
                    "this tool is only available in a connector-attached session"
                )
            }
        ]

    async def test_list_visible_channels_drops_fetched_at_field(
        self, isolated_db, monkeypatch
    ) -> None:
        await _seed_stub_account()
        register_for_test("stub", _StubPluginWithFetch)
        sid = await _seed_connector_session()

        cached = DiscoverableEntities(
            peers=[],
            channels=[],
            groups=[],
            roles=[],
            fetched_at="2026-05-25T13:00:00+00:00",
        )

        class _Snap:
            cache = cached
            stale_carry = None
            fetched_at_monotonic = 0.0
            account_type = "stub"

        async def _fake_snapshot(account_id: str):
            return _Snap()

        monkeypatch.setattr(
            pool_mod, "_get_account_cache_snapshot", _fake_snapshot
        )

        tool = ListVisibleChannelsTool(connector_ids=["acct-hist"])
        token = _bind_csid(sid)
        try:
            result = await tool.execute()
        finally:
            current_chat_session_id.reset(token)
        # All four axes present; fetched_at absent.
        assert set(result.keys()) == {"peers", "channels", "groups", "roles"}
        assert "fetched_at" not in result
