"""Tests for the F4 leg 2 platform-send built-in tool.

Covers:
- Registry presence in `_TOOL_CLASSES` and `BuiltinToolProvider.get_tools`
  on both the introspection path (zero-arg) and the factory path
  (kwarg-injected `connector_account_ids`).
- Zero-arg construction (`/api/tools` introspection contract).
- Target-shape validation (malformed `target` and `content`).
- Account-scope validation (`target.account_id` must be in
  `self._connector_account_ids`).
- Pool acquire failures (`KeyError`, `ConnectorRegistrationError`).
- `client.send` failures (`ConnectorRateLimitError`,
  `ConnectorConnectionError`).
- Happy path (`StubPlugin.outbound_records` capture, success-prefix
  sentinel, thread_id propagation).
- Architect-flagged "failure-envelope NEVER starts with the success
  prefix" sanity test — locks the dispatcher visibility-tagger contract.
- Content interpolation with peer-supplied bracket strings — confirms
  `repr()` escaping prevents cross-pollination of the visibility-tag
  matcher.

Fixtures (`isolated_db`, `_seed_stub_account`, autouse stub reset, autouse
pool/registry clear) replicate the F3 dispatcher pattern verbatim — the F3
debrief flagged "extract to shared helpers" as a leg-5 carry-forward, so
leg 2 ships its own copy.
"""

from __future__ import annotations

import aiosqlite
import pytest

from the_one.config import settings
from the_one.connectors import PLATFORM_SEND_OK_PREFIX
from the_one.connectors import _pool as pool_mod
from the_one.connectors._stub import StubPlugin
from the_one.connectors.base import OutboundTarget
from the_one.connectors.errors import (
    ConnectorConnectionError,
    ConnectorRateLimitError,
)
from the_one.connectors.registry import (
    clear_for_test as _registry_clear_for_test,
)
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.connection import get_connection
from the_one.db.models import ConnectorAccount
from the_one.db.repositories import ConnectorAccountRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import get_encryptor
from the_one.tools.builtins import _TOOL_CLASSES, BuiltinToolProvider
from the_one.tools.connector_send import SendToPlatformChannelTool

# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_stub_state():
    """Reset StubPlugin class-level recording buffers around each test."""
    StubPlugin.reset_for_test()
    yield
    StubPlugin.reset_for_test()


@pytest.fixture(autouse=True)
async def _clear_pool_and_registry():
    """Empty pool + restore baseline registry between tests."""
    yield
    await pool_mod._clear_for_test()
    _registry_clear_for_test()
    restore_to_baseline_for_test()


@pytest.fixture
async def isolated_db(tmp_path, monkeypatch):
    """Per-test sqlite DB at tmp_path. Mirrors
    `tests/test_connectors_e2e.py::isolated_db` and
    `tests/test_connectors_inbound.py::isolated_db`."""
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


async def _seed_stub_account(account_id: str = "acct-send") -> ConnectorAccount:
    """Persist a stub-typed ConnectorAccount via the repository."""
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    repo = ConnectorAccountRepository(conn, encryptor)
    account = ConnectorAccount(
        id=account_id,
        name="Stub Send Account",
        type="stub",
        config={},
        secrets={},
    )
    await repo.create(account)
    return account


# ─── Registry + introspection ────────────────────────────────────────────


class TestRegistry:
    def test_tool_registered_in_tool_classes(self) -> None:
        assert "send_to_platform_channel" in _TOOL_CLASSES
        assert _TOOL_CLASSES["send_to_platform_channel"] is SendToPlatformChannelTool

    def test_zero_arg_construction(self) -> None:
        # `/api/tools` introspection path calls `cls()` — must not raise.
        tool = SendToPlatformChannelTool()
        assert tool.name == "send_to_platform_channel"
        assert tool._connector_account_ids == []
        assert tool._agent_name is None

    def test_construction_with_none_connector_account_ids(self) -> None:
        # Explicit None coerces to empty list (not None).
        tool = SendToPlatformChannelTool(connector_account_ids=None)
        assert tool._connector_account_ids == []

    def test_construction_with_explicit_account_ids(self) -> None:
        tool = SendToPlatformChannelTool(connector_account_ids=["acc-1", "acc-2"])
        assert tool._connector_account_ids == ["acc-1", "acc-2"]

    def test_tool_schema_shape(self) -> None:
        tool = SendToPlatformChannelTool()
        params = tool.parameters
        assert params["type"] == "object"
        assert "target" in params["properties"]
        assert "content" in params["properties"]
        assert set(params["required"]) == {"target", "content"}
        target_props = params["properties"]["target"]["properties"]
        assert "account_id" in target_props
        assert "channel_id" in target_props
        assert "thread_id" in target_props
        assert set(params["properties"]["target"]["required"]) == {
            "account_id",
            "channel_id",
        }

    def test_config_is_empty_config(self) -> None:
        from the_one.tools.resolver import _EmptyConfig

        assert SendToPlatformChannelTool.Config is _EmptyConfig


class TestBuiltinProviderIntegration:
    def test_introspection_path_includes_tool(self) -> None:
        # Zero-arg `get_tools()` (the `/api/tools` shape) must include the
        # new tool — preserves admin-grid surface.
        tools = BuiltinToolProvider().get_tools()
        send_tools = [t for t in tools if t.name == "send_to_platform_channel"]
        assert len(send_tools) == 1
        assert isinstance(send_tools[0], SendToPlatformChannelTool)
        # Introspection path → no kwargs injected.
        assert send_tools[0]._connector_account_ids == []

    def test_factory_path_threads_account_ids(self) -> None:
        tools = BuiltinToolProvider().get_tools(
            {}, {}, agent_name="agent-a", connector_account_ids=["acc-1"]
        )
        send_tool = next(t for t in tools if t.name == "send_to_platform_channel")
        assert isinstance(send_tool, SendToPlatformChannelTool)
        assert send_tool._connector_account_ids == ["acc-1"]
        assert send_tool._agent_name == "agent-a"

    def test_factory_path_without_account_ids_defaults_empty(self) -> None:
        # Backward-compat: existing factory callers that don't pass
        # `connector_account_ids` still get an instance with `[]`.
        tools = BuiltinToolProvider().get_tools({}, {}, agent_name="agent-a")
        send_tool = next(t for t in tools if t.name == "send_to_platform_channel")
        assert send_tool._connector_account_ids == []
        assert send_tool._agent_name == "agent-a"


# ─── Target-shape validation ─────────────────────────────────────────────


class TestTargetValidation:
    async def test_non_dict_target(self) -> None:
        tool = SendToPlatformChannelTool(connector_account_ids=["acc-1"])
        result = await tool.execute(target="not-a-dict", content="x")
        assert result.startswith("[error]")
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)

    async def test_missing_account_id(self) -> None:
        tool = SendToPlatformChannelTool(connector_account_ids=["acc-1"])
        result = await tool.execute(target={"channel_id": "c1"}, content="x")
        assert result.startswith("[error]")
        assert "account_id" in result
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)

    async def test_missing_channel_id(self) -> None:
        tool = SendToPlatformChannelTool(connector_account_ids=["acc-1"])
        result = await tool.execute(
            target={"account_id": "acc-1"}, content="x"
        )
        assert result.startswith("[error]")
        assert "channel_id" in result
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)

    async def test_non_string_account_id(self) -> None:
        tool = SendToPlatformChannelTool(connector_account_ids=["acc-1"])
        result = await tool.execute(
            target={"account_id": 123, "channel_id": "c1"}, content="x"
        )
        assert result.startswith("[error]")
        assert "account_id" in result
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)

    async def test_non_string_channel_id(self) -> None:
        tool = SendToPlatformChannelTool(connector_account_ids=["acc-1"])
        result = await tool.execute(
            target={"account_id": "acc-1", "channel_id": 7}, content="x"
        )
        assert result.startswith("[error]")
        assert "channel_id" in result
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)

    async def test_non_string_thread_id(self) -> None:
        tool = SendToPlatformChannelTool(connector_account_ids=["acc-1"])
        result = await tool.execute(
            target={"account_id": "acc-1", "channel_id": "c1", "thread_id": 42},
            content="x",
        )
        assert result.startswith("[error]")
        assert "thread_id" in result
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)

    async def test_non_string_content(self) -> None:
        tool = SendToPlatformChannelTool(connector_account_ids=["acc-1"])
        result = await tool.execute(
            target={"account_id": "acc-1", "channel_id": "c1"},
            content=123,
        )
        assert result.startswith("[error]")
        assert "content" in result
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)


# ─── Account-scope validation ────────────────────────────────────────────


class TestAccountScopeValidation:
    async def test_unattached_account_returns_constraint_error(self) -> None:
        tool = SendToPlatformChannelTool(connector_account_ids=["acc-A"])
        result = await tool.execute(
            target={"account_id": "acc-B", "channel_id": "c1"},
            content="x",
        )
        # Verbatim format from the leg artifact's design decisions:
        # `[error] [constraint] account_id 'acc-B' is not attached to this agent`
        assert result == (
            "[error] [constraint] account_id 'acc-B' is "
            "not attached to this agent"
        )
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)

    async def test_empty_account_list_rejects_any_account(self) -> None:
        tool = SendToPlatformChannelTool()  # empty account list
        result = await tool.execute(
            target={"account_id": "acc-X", "channel_id": "c1"},
            content="x",
        )
        assert result.startswith("[error] [constraint]")
        assert "acc-X" in result
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)


# ─── Pool dispatch happy path ────────────────────────────────────────────


class TestPoolDispatch:
    async def test_happy_path(self, isolated_db) -> None:
        await _seed_stub_account("acct-send")
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
        )
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c1"},
            content="hello peers",
        )
        assert result.startswith(PLATFORM_SEND_OK_PREFIX)
        assert "acct-send:c1" in result
        assert "msg_id=stub-msg-id" in result
        assert StubPlugin.outbound_records == [
            (OutboundTarget(channel_id="c1", thread_id=None), "hello peers")
        ]

    async def test_happy_path_with_thread_id(self, isolated_db) -> None:
        await _seed_stub_account("acct-send")
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
        )
        result = await tool.execute(
            target={
                "account_id": "acct-send",
                "channel_id": "c1",
                "thread_id": "t1",
            },
            content="threaded reply",
        )
        assert result.startswith(PLATFORM_SEND_OK_PREFIX)
        assert "(thread t1)" in result
        assert StubPlugin.outbound_records == [
            (OutboundTarget(channel_id="c1", thread_id="t1"), "threaded reply")
        ]

    async def test_empty_string_thread_id_coerced_to_none(self, isolated_db) -> None:
        await _seed_stub_account("acct-send")
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
        )
        result = await tool.execute(
            target={
                "account_id": "acct-send",
                "channel_id": "c1",
                "thread_id": "",
            },
            content="x",
        )
        assert result.startswith(PLATFORM_SEND_OK_PREFIX)
        # Empty-string thread_id coerced to None — no `(thread )` clause.
        assert "(thread" not in result
        assert StubPlugin.outbound_records == [
            (OutboundTarget(channel_id="c1", thread_id=None), "x")
        ]


# ─── Pool acquire failures ───────────────────────────────────────────────


class TestPoolAcquireFailures:
    async def test_unknown_account_id_returns_constraint_envelope(
        self, isolated_db
    ) -> None:
        # Account is in the tool's attached list but NOT persisted in the
        # DB. Post-leg-3, the per-call `ConnectorAccountRepository.get`
        # at the channel-ACL consult site raises `KeyError` first and the
        # defensive catch surfaces a constraint envelope BEFORE
        # `pool_acquire`. (Pre-leg-3 the same case surfaced
        # `[error] KeyError:` from `_load_account`; the F6 consult now
        # intercepts it earlier with a friendlier envelope.)
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-missing"],
        )
        result = await tool.execute(
            target={"account_id": "acct-missing", "channel_id": "c1"},
            content="x",
        )
        assert result == (
            "[error] [constraint] account_id 'acct-missing' not found"
        )
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)
        assert StubPlugin.outbound_records == []

    async def test_unregistered_plugin_type_returns_registration_error(
        self, isolated_db
    ) -> None:
        # Account is persisted (type="stub") but registry is cleared so
        # "stub" is unregistered — `_resolve_plugin` raises
        # `ConnectorRegistrationError`.
        await _seed_stub_account("acct-send")
        # Clear registry unconditionally at test-body start (the autouse
        # restore-baseline runs at PREVIOUS test teardown, not this test's
        # setup — so the baseline may already have "stub" registered from
        # builtin connectors).
        _registry_clear_for_test()

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
        )
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c1"},
            content="x",
        )
        assert result.startswith("[error] ConnectorRegistrationError:")
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)
        assert StubPlugin.outbound_records == []


# ─── client.send failures ────────────────────────────────────────────────


class TestClientSendFailures:
    async def test_rate_limit_error_envelope(self, isolated_db) -> None:
        await _seed_stub_account("acct-send")
        register_for_test("stub", StubPlugin)
        StubPlugin.send_should_raise = ConnectorRateLimitError(
            "acct-send", retry_after_seconds=60.0
        )

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
        )
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c1"},
            content="x",
        )
        assert result.startswith("[error] ConnectorRateLimitError:")
        assert "rate-limited" in result
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)
        assert StubPlugin.outbound_records == []

    async def test_connection_error_envelope(self, isolated_db) -> None:
        await _seed_stub_account("acct-send")
        register_for_test("stub", StubPlugin)
        StubPlugin.send_should_raise = ConnectorConnectionError("gateway closed")

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
        )
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c1"},
            content="x",
        )
        assert result.startswith("[error] ConnectorConnectionError:")
        assert "gateway closed" in result
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)
        assert StubPlugin.outbound_records == []


# ─── Architect-flagged sanity tests ──────────────────────────────────────


class TestPrefixSentinelSanity:
    """The dispatcher's visibility-tagger keys on
    ``startswith(PLATFORM_SEND_OK_PREFIX)``. Any failure envelope that
    accidentally starts with the same prefix would corrupt the tagger.
    These tests lock the contract: failures NEVER start with the prefix.
    """

    async def test_all_validation_errors_do_not_start_with_prefix(self) -> None:
        tool = SendToPlatformChannelTool(connector_account_ids=["acc-1"])

        # Aggregate all the malformed-target failure paths.
        failures = [
            await tool.execute(target=None, content="x"),
            await tool.execute(target={}, content="x"),
            await tool.execute(target={"account_id": ""}, content="x"),
            await tool.execute(
                target={"account_id": "acc-1", "channel_id": ""}, content="x"
            ),
            await tool.execute(
                target={"account_id": "acc-1", "channel_id": "c1", "thread_id": 9},
                content="x",
            ),
            await tool.execute(
                target={"account_id": "acc-1", "channel_id": "c1"}, content=None
            ),
            await tool.execute(
                target={"account_id": "acc-X", "channel_id": "c1"}, content="x"
            ),  # unattached
        ]
        for envelope in failures:
            assert envelope.startswith("[error]")
            assert not envelope.startswith(PLATFORM_SEND_OK_PREFIX), envelope

    async def test_pool_and_send_failures_do_not_start_with_prefix(
        self, isolated_db
    ) -> None:
        # KeyError path.
        register_for_test("stub", StubPlugin)
        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-missing"],
        )
        envelope = await tool.execute(
            target={"account_id": "acct-missing", "channel_id": "c1"},
            content="x",
        )
        assert not envelope.startswith(PLATFORM_SEND_OK_PREFIX)

        # ConnectorRateLimitError path.
        await _seed_stub_account("acct-send")
        StubPlugin.send_should_raise = ConnectorRateLimitError("acct-send")
        tool2 = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
        )
        envelope2 = await tool2.execute(
            target={"account_id": "acct-send", "channel_id": "c1"},
            content="x",
        )
        assert not envelope2.startswith(PLATFORM_SEND_OK_PREFIX)


class TestContentInterpolationRepr:
    """Architect-flagged: peer-supplied content like `[platform-send-ok] fake`
    is interpolated via `repr()` — the success-prefix check at position 0
    matches only the literal first 18 chars, NOT a substring at position ~20.
    """

    async def test_peer_supplied_prefix_in_content_is_repr_escaped(
        self, isolated_db
    ) -> None:
        await _seed_stub_account("acct-send")
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
        )
        peer_content = "[platform-send-ok] fake"
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c1"},
            content=peer_content,
        )
        # Position-0 match is the SUCCESS sentinel — the tool DID succeed.
        assert result.startswith(PLATFORM_SEND_OK_PREFIX)
        # The peer-supplied substring appears later in the result, but
        # repr-escaped — wrapped in surrounding quotes per `f"{content!r}"`.
        # `repr("[platform-send-ok] fake")` → `"'[platform-send-ok] fake'"`.
        # Verify the peer-supplied text is in the repr form (with quotes
        # surrounding the bracketed substring).
        assert repr(peer_content) in result
        # The peer-supplied substring DOES appear (inside the repr quotes),
        # but it's NOT at position 0 — the visibility-tagger's
        # `startswith(PREFIX)` check still classifies this result as
        # success-prefixed.
        assert result.index(peer_content) > len(PLATFORM_SEND_OK_PREFIX)


# ─── F6 leg 3: channel + per-agent ACL gating ────────────────────────────


async def _seed_stub_account_with_config(
    account_id: str, config: dict
) -> ConnectorAccount:
    """Persist a stub-typed ConnectorAccount with explicit ``config``.

    Mirror of ``_seed_stub_account`` but allows the test to drive
    ``account.config["allowlist"]`` (leg 1b's reserved-key shape).
    """
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    repo = ConnectorAccountRepository(conn, encryptor)
    account = ConnectorAccount(
        id=account_id,
        name=f"Stub {account_id}",
        type="stub",
        config=config,
        secrets={},
    )
    await repo.create(account)
    return account


class TestF6OutboundGating:
    """Channel + per-agent ACL consultation matrix.

    The consult happens AFTER account-scope validation (existing F4
    fast-path stays the cheap denial) and BEFORE pool_acquire. Two
    independent gates intersect:

    1. Account-scope channel gate: ``account.config["allowlist"]["channels"]``
       (absent ``allowlist`` key → permit).
    2. Per-agent ACL channel gate: ``self._connector_acls[account_id]
       ["channels"]`` (account_id key absent OR empty channels list →
       inherit/permit).

    Denials return ``[error] [constraint] channel_id <id> ...`` envelopes;
    permits proceed to the existing pool-acquire + client.send path.
    """

    async def test_permit_when_no_allowlist_no_acl(self, isolated_db) -> None:
        # Account has no allowlist key; tool has no per-agent ACL.
        # Both gates default-permit → success.
        await _seed_stub_account_with_config("acct-send", config={})
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
        )
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c1"},
            content="hello",
        )
        assert result.startswith(PLATFORM_SEND_OK_PREFIX)
        assert "acct-send:c1" in result

    async def test_permit_when_channel_in_account_allowlist_no_acl(
        self, isolated_db
    ) -> None:
        # Account allowlist includes c1; per-agent ACL absent → inherit.
        await _seed_stub_account_with_config(
            "acct-send",
            config={"allowlist": {"peers": [], "channels": ["c1"]}},
        )
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
        )
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c1"},
            content="hello",
        )
        assert result.startswith(PLATFORM_SEND_OK_PREFIX)

    async def test_deny_when_channel_not_in_account_allowlist(
        self, isolated_db
    ) -> None:
        # Account allowlist includes c1 only; tool tries c2 → denial.
        await _seed_stub_account_with_config(
            "acct-send",
            config={"allowlist": {"peers": [], "channels": ["c1"]}},
        )
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
        )
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c2"},
            content="hello",
        )
        assert result == (
            "[error] [constraint] channel_id 'c2' "
            "is not reachable on account 'acct-send'"
        )
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)
        # Denial returns BEFORE pool.acquire — no outbound recorded.
        assert StubPlugin.outbound_records == []

    async def test_deny_when_channel_in_account_but_not_in_per_agent_acl(
        self, isolated_db
    ) -> None:
        # Account allows c1 + c2; per-agent ACL narrows to c1 only;
        # tool tries c2 → per-agent denial.
        await _seed_stub_account_with_config(
            "acct-send",
            config={"allowlist": {"peers": [], "channels": ["c1", "c2"]}},
        )
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
            connector_acls={
                "acct-send": {"peers": [], "channels": ["c1"]},
            },
        )
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c2"},
            content="hello",
        )
        assert result == (
            "[error] [constraint] channel_id 'c2' is not reachable "
            "for this agent on account 'acct-send'"
        )
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)
        assert StubPlugin.outbound_records == []

    async def test_permit_when_per_agent_acl_has_empty_channels_list(
        self, isolated_db
    ) -> None:
        # Per-agent ACL entry has empty channels list → inherit
        # account-scope (no agent-level narrowing). Account allowlist
        # absent → permit overall.
        await _seed_stub_account_with_config("acct-send", config={})
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
            connector_acls={
                "acct-send": {"peers": [], "channels": []},
            },
        )
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c1"},
            content="hello",
        )
        assert result.startswith(PLATFORM_SEND_OK_PREFIX)

    async def test_permit_when_per_agent_acl_account_id_absent(
        self, isolated_db
    ) -> None:
        # `connector_acls` is present but missing this account_id →
        # inherit (no narrowing for this account).
        await _seed_stub_account_with_config("acct-send", config={})
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
            connector_acls={
                "other-acct": {"peers": [], "channels": ["x"]},
            },
        )
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c1"},
            content="hello",
        )
        assert result.startswith(PLATFORM_SEND_OK_PREFIX)

    async def test_permit_when_channel_in_both_account_allowlist_and_per_agent_acl(
        self, isolated_db
    ) -> None:
        # Intersection-positive: both axes permit c1 → success.
        # Mirror of the deny-by-intersection test but on the success path.
        await _seed_stub_account_with_config(
            "acct-send",
            config={"allowlist": {"peers": [], "channels": ["c1", "c2"]}},
        )
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
            connector_acls={
                "acct-send": {"peers": [], "channels": ["c1"]},
            },
        )
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c1"},
            content="hello",
        )
        assert result.startswith(PLATFORM_SEND_OK_PREFIX)
        assert "acct-send:c1" in result

    async def test_keyerror_on_mid_call_account_deletion_returns_constraint(
        self, isolated_db
    ) -> None:
        # The account-scope check at L125 passes (id is in the tool's
        # attached set), but the per-call repository fetch raises
        # KeyError because the account row was deleted mid-call. The
        # defensive catch returns the constraint envelope.
        register_for_test("stub", StubPlugin)
        # NOTE: no account seeded; the tool's attached-set still permits
        # account-scope, but the DB fetch will raise KeyError.
        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-deleted"],
        )
        result = await tool.execute(
            target={"account_id": "acct-deleted", "channel_id": "c1"},
            content="hello",
        )
        assert result == (
            "[error] [constraint] account_id 'acct-deleted' not found"
        )
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)
        assert StubPlugin.outbound_records == []

    async def test_f4_account_scope_denial_still_works(self, isolated_db) -> None:
        # REGRESSION PIN: F4's existing account-scope envelope is
        # byte-identical. Leg 3 only inserts the new consultation block
        # AFTER this check. The denial returns BEFORE the per-call
        # account fetch, so no DB hit occurs.
        register_for_test("stub", StubPlugin)
        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-A"],
            connector_acls={
                "acct-A": {"peers": [], "channels": ["c1"]},
            },
        )
        result = await tool.execute(
            target={"account_id": "acct-B", "channel_id": "c1"},
            content="hello",
        )
        assert result == (
            "[error] [constraint] account_id 'acct-B' is "
            "not attached to this agent"
        )
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)
        assert StubPlugin.outbound_records == []

    async def test_empty_channels_lockdown_denies(self, isolated_db) -> None:
        # Edge case from leg 1b: `allowlist = {"peers": [], "channels": []}`
        # is empty-list LOCKDOWN, not absence. channel_id never in [] →
        # denial via the account-scope branch.
        await _seed_stub_account_with_config(
            "acct-send",
            config={"allowlist": {"peers": [], "channels": []}},
        )
        register_for_test("stub", StubPlugin)

        tool = SendToPlatformChannelTool(
            agent_name="test-agent",
            connector_account_ids=["acct-send"],
        )
        result = await tool.execute(
            target={"account_id": "acct-send", "channel_id": "c1"},
            content="hello",
        )
        assert result == (
            "[error] [constraint] channel_id 'c1' "
            "is not reachable on account 'acct-send'"
        )
        assert not result.startswith(PLATFORM_SEND_OK_PREFIX)
        assert StubPlugin.outbound_records == []
