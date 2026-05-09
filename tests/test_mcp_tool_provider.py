"""Tests for ``the_one/mcp/_tool.py`` and ``the_one/mcp/_tool_provider.py``.

Coverage groups:

* ``TestMCPClientTool`` — wrapper instantiation, name shape, 64-char
  ceiling, ``execute`` dispatch + failure-class #3 envelope.
* ``TestApplyOverride`` — stdio overlay-merge vs streamable-http
  REPLACE; schema-mismatch propagation.
* ``TestMCPToolProvider`` — empty-source-ids fast-path,
  failure classes #1/#2/#4 + #1 sub-case, orphan-override warn,
  override application end-to-end.
* ``TestAgentFactoryMCPIntegration`` — ``mcp_provider=None`` skip path,
  default construction, full create() path with MCP attach.

Project-level pytest-asyncio is in ``auto`` mode, so ``async def
test_*`` functions run on the asyncio event loop without per-test
decorators. Per L1 anomaly A2 process learning, every test in this
file uses targeted mocks (no DB, no real pool, no bwrap) so a
``--timeout=15`` per-test cap holds.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import FakeLLM, StubTool
from pydantic import ValidationError

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.db.models import LLMProviderConfig, MCPSource
from the_one.mcp import _pool as pool_mod
from the_one.mcp import _tool_provider as provider_mod
from the_one.mcp._tool import (
    MCPClientTool,
    _normalize_source_name,
)
from the_one.mcp._tool_provider import (
    MCPToolProvider,
    _apply_override,
)
from the_one.mcp.errors import (
    MCPAuthRequired,
    MCPConnectionError,
    MCPRegistrationError,
    MCPSandboxError,
)
from the_one.mcp.types import MCPTool, MCPToolResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_mcp_tool(
    name: str = "do_thing",
    description: str = "Do a thing.",
    input_schema: dict | None = None,
) -> MCPTool:
    return MCPTool(
        name=name,
        description=description,
        input_schema=(
            input_schema if input_schema is not None else {"type": "object", "properties": {}}
        ),
        output_schema=None,
        annotations=None,
    )


def _stub_source(
    source_id: str = "src-1",
    name: str = "github",
    type: str = "stdio",
    config: dict | None = None,
    secrets: dict | None = None,
) -> MCPSource:
    return MCPSource(
        id=source_id,
        name=name,
        type=type,  # type: ignore[arg-type]
        config=config or {},
        secrets=secrets or {},
    )


@pytest.fixture(autouse=True)
async def _clear_pool_after_each_test():
    """Tests below patch ``_pool.acquire`` directly, but a few use the
    real pool path. Always clear after each test to avoid stale entries
    leaking into the next test (mirrors test_mcp_pool.py's autouse).
    """
    yield
    await pool_mod._clear_for_test()


# ===========================================================================
# TestMCPClientTool
# ===========================================================================


class TestMCPClientTool:
    def test_prefixed_name_format(self) -> None:
        mt = _stub_mcp_tool(name="do_thing")
        src = _stub_source(name="github")
        tool = MCPClientTool(
            mt,
            source_id="src-1",
            source_name="github",
            agent_name="agent-a",
            effective_source=src,
        )
        assert tool.name == "mcp__github__do_thing"

    def test_normalize_replaces_invalid_chars(self) -> None:
        # Helper test
        assert _normalize_source_name("My Source/v2") == "My_Source_v2"
        assert _normalize_source_name("normal-name_123") == "normal-name_123"
        # Ensure prefixed name uses normalized form.
        mt = _stub_mcp_tool(name="do_thing")
        src = _stub_source(name="My Source/v2")
        tool = MCPClientTool(
            mt,
            source_id="src-1",
            source_name="My Source/v2",
            agent_name="agent-a",
            effective_source=src,
        )
        assert tool.name == "mcp__My_Source_v2__do_thing"

    def test_64_char_ceiling_raises(self) -> None:
        # source_name long enough that even a short tool name overflows.
        # "mcp__" (5) + 50-char source + "__" (2) + 10-char tool = 67 chars.
        long_source = "s" * 50
        mt = _stub_mcp_tool(name="t" * 10)
        src = _stub_source(name=long_source)
        with pytest.raises(MCPRegistrationError, match="exceeds 64-character limit"):
            MCPClientTool(
                mt,
                source_id="src-1",
                source_name=long_source,
                agent_name="a",
                effective_source=src,
            )

    def test_64_char_ceiling_at_limit_passes(self) -> None:
        # "mcp__" (5) + "__" (2) = 7 chars overhead.
        # Total 64 chars: source_name + tool_name = 57 chars.
        # Use 30-char source + 27-char tool.
        source_name = "s" * 30
        tool_name = "t" * 27
        mt = _stub_mcp_tool(name=tool_name)
        src = _stub_source(name=source_name)
        tool = MCPClientTool(
            mt,
            source_id="src-1",
            source_name=source_name,
            agent_name="a",
            effective_source=src,
        )
        assert len(tool.name) == 64

    def test_description_falls_back_to_empty(self) -> None:
        mt = MCPTool(
            name="do_thing",
            description=None,  # type: ignore[arg-type]
            input_schema={"type": "object", "properties": {}},
            output_schema=None,
            annotations=None,
        )
        src = _stub_source()
        tool = MCPClientTool(
            mt,
            source_id="src-1",
            source_name="github",
            agent_name="a",
            effective_source=src,
        )
        assert tool.description == ""

    def test_parameters_falls_back_to_empty_schema(self) -> None:
        # input_schema=None → fallback.
        mt = MCPTool(
            name="do_thing",
            description="d",
            input_schema=None,  # type: ignore[arg-type]
            output_schema=None,
            annotations=None,
        )
        src = _stub_source()
        tool = MCPClientTool(
            mt,
            source_id="src-1",
            source_name="github",
            agent_name="a",
            effective_source=src,
        )
        assert tool.parameters == {"type": "object", "properties": {}}
        # input_schema={} → also fallback.
        mt2 = _stub_mcp_tool(input_schema={})
        tool2 = MCPClientTool(
            mt2,
            source_id="src-1",
            source_name="github",
            agent_name="a",
            effective_source=src,
        )
        assert tool2.parameters == {"type": "object", "properties": {}}

    async def test_execute_acquires_and_calls(self, monkeypatch) -> None:
        """Mock acquire to return stub MCPClient; verify call_tool invoked
        with original_tool_name + kwargs; verify return is result.text;
        verify acquire was called with source_override=effective_source."""
        mt = _stub_mcp_tool(name="do_thing")
        src = _stub_source(name="github")
        tool = MCPClientTool(
            mt,
            source_id="src-1",
            source_name="github",
            agent_name="agent-a",
            effective_source=src,
        )

        stub_client = MagicMock()
        stub_client.call_tool = AsyncMock(
            return_value=MCPToolResult(
                text="ok-result",
                raw=[],
                structured=None,
                is_error=False,
            )
        )

        captured_kwargs: dict[str, Any] = {}

        async def _stub_acquire(agent_name, source_id, **kwargs):
            captured_kwargs["agent_name"] = agent_name
            captured_kwargs["source_id"] = source_id
            captured_kwargs["source_override"] = kwargs.get("source_override")
            return stub_client

        # Patch the symbol bound INTO _tool.py's module namespace.
        monkeypatch.setattr("the_one.mcp._tool.acquire", _stub_acquire)

        result = await tool.execute(arg1=1, arg2="x")

        assert result == "ok-result"
        stub_client.call_tool.assert_awaited_once_with("do_thing", {"arg1": 1, "arg2": "x"})
        assert captured_kwargs["agent_name"] == "agent-a"
        assert captured_kwargs["source_id"] == "src-1"
        # Cycle-1 low #5 lock-in: the override is passed through.
        assert captured_kwargs["source_override"] is src

    async def test_execute_handles_acquire_failure(self, monkeypatch) -> None:
        mt = _stub_mcp_tool(name="do_thing")
        src = _stub_source(name="github")
        tool = MCPClientTool(
            mt,
            source_id="src-1",
            source_name="github",
            agent_name="agent-a",
            effective_source=src,
        )

        async def _failing_acquire(*args, **kwargs):
            raise MCPSandboxError("bwrap missing")

        monkeypatch.setattr("the_one.mcp._tool.acquire", _failing_acquire)

        result = await tool.execute()
        assert result.startswith("[error]")
        assert "github" in result
        assert "MCPSandboxError" in result

    async def test_execute_propagates_mcp_auth_required(self, monkeypatch) -> None:
        """Cycle-1 test gap #1: MCPAuthRequired must NOT be swallowed
        by the failure-class #3 catch — the agent loop's _execute_tool
        catches it and translates to ToolResult.metadata."""
        mt = _stub_mcp_tool(name="do_thing")
        src = _stub_source(name="github")
        tool = MCPClientTool(
            mt,
            source_id="src-1",
            source_name="github",
            agent_name="agent-a",
            effective_source=src,
        )

        stub_client = MagicMock()
        stub_client.call_tool = AsyncMock(
            side_effect=MCPAuthRequired("src-1")
        )

        async def _stub_acquire(*args, **kwargs):
            return stub_client

        monkeypatch.setattr("the_one.mcp._tool.acquire", _stub_acquire)

        with pytest.raises(MCPAuthRequired):
            await tool.execute()


# ===========================================================================
# TestApplyOverride
# ===========================================================================


class TestApplyOverride:
    def test_apply_override_stdio_overlay_merge(self) -> None:
        # F2 contract: source.secrets IS the flat env kv table for
        # stdio (transports/stdio.py::build_stdio_environ at line 224-225).
        # NOT nested under "env". Test post-HAT-A4 fix.
        src = _stub_source(
            type="stdio",
            secrets={"A": "1", "B": "2"},
        )
        override_payload = {"env": {"B": "3", "C": "4"}}
        result = _apply_override(src, override_payload)
        # operator-only keys preserve; agent wins on collisions; agent-only added.
        assert result.secrets == {"A": "1", "B": "3", "C": "4"}
        # Source unchanged (model_copy returns NEW).
        assert src.secrets == {"A": "1", "B": "2"}

    def test_apply_override_stdio_no_payload_returns_unchanged(self) -> None:
        src = _stub_source(
            type="stdio",
            secrets={"A": "1"},
        )
        # None payload.
        result = _apply_override(src, None)
        assert result is src
        # Empty payload.
        result2 = _apply_override(src, {})
        assert result2 is src

    def test_apply_override_streamable_http_overlays_headers(self) -> None:
        # F2 contract: source.secrets IS the flat header kv table for
        # streamable-http (transports/streamable_http.py::build_request_headers
        # at line 68-69). NOT nested under "headers". Test post-HAT-A4 fix.
        # Overlay-merge — operator-only headers preserve; agent wins on
        # collisions. Cycle-1 medium #3's "REPLACE" disposition was
        # structurally unsafe against the F2 contract; corrected inline.
        src = _stub_source(
            type="streamable-http",
            secrets={"X-Operator": "true", "X-Tenant": "acme"},
        )
        override_payload = {"headers": {"X-Agent": "true", "X-Tenant": "agent-acme"}}
        result = _apply_override(src, override_payload)
        # operator-only X-Operator preserves; X-Tenant collision goes to agent;
        # agent-only X-Agent added.
        assert result.secrets == {
            "X-Operator": "true",
            "X-Tenant": "agent-acme",
            "X-Agent": "true",
        }

    def test_apply_override_streamable_http_bearer_token_becomes_authorization(
        self,
    ) -> None:
        # bearer_token translates to a flat Authorization: Bearer <token>
        # header in source.secrets (post-HAT-A4 fix).
        src = _stub_source(
            type="streamable-http",
            secrets={"X-Op": "true"},
        )
        override_payload = {"bearer_token": "agent-token"}
        result = _apply_override(src, override_payload)
        assert result.secrets["Authorization"] == "Bearer agent-token"
        # X-Op preserved (operator-only).
        assert result.secrets["X-Op"] == "true"

    def test_apply_override_streamable_http_partial_keeps_other_secrets(self) -> None:
        # Operator-only secrets preserve under partial overlay; agent's
        # `headers` override overlays flat without touching unrelated keys.
        src = _stub_source(
            type="streamable-http",
            secrets={
                "X-Op": "true",
                "extra_secret": "preserve_me",
            },
        )
        override_payload = {"headers": {"X-Agent": "yes"}}
        result = _apply_override(src, override_payload)
        # Operator's X-Op + extra_secret preserve; agent's X-Agent added.
        assert result.secrets == {
            "X-Op": "true",
            "extra_secret": "preserve_me",
            "X-Agent": "yes",
        }

    def test_apply_override_schema_mismatch_propagates(self) -> None:
        # Operator put a streamable-http key (bearer_token) under a stdio source.
        src = _stub_source(type="stdio", secrets={"env": {}})
        # `bearer_token` is not a valid stdio override field; Pydantic
        # `extra="ignore"` (project default) silently drops it. We
        # cannot trivially trigger ValidationError on stdio — but we
        # CAN by passing a non-dict env value.
        override_payload = {"env": "not-a-dict"}
        with pytest.raises(ValidationError):
            _apply_override(src, override_payload)


# ===========================================================================
# TestMCPToolProvider
# ===========================================================================


@pytest.fixture
def patch_provider_deps(monkeypatch):
    """Patch get_connection / get_encryptor / MCPSourceRepository
    inside the _tool_provider module so tests don't hit the real DB.

    Returns the mock repo so tests can configure ``get`` per-source.
    """
    mock_conn = AsyncMock()
    mock_encryptor = MagicMock()
    mock_repo = AsyncMock()

    async def _fake_get_connection():
        return mock_conn

    monkeypatch.setattr(provider_mod, "get_connection", _fake_get_connection)
    monkeypatch.setattr(provider_mod, "get_encryptor", lambda _data_dir: mock_encryptor)
    monkeypatch.setattr(provider_mod, "MCPSourceRepository", lambda c, e: mock_repo)
    return mock_repo


def _stub_mcp_client(tools: list[MCPTool] | Exception):
    """Build a stub client whose list_tools returns ``tools`` (list)
    or raises (Exception)."""
    client = MagicMock()
    if isinstance(tools, Exception):
        client.list_tools = AsyncMock(side_effect=tools)
    else:
        client.list_tools = AsyncMock(return_value=tools)
    return client


class TestMCPToolProvider:
    async def test_empty_source_ids_returns_empty_list_no_db_calls(
        self, monkeypatch
    ) -> None:
        """Empty mcp_source_ids early-returns BEFORE any DB call."""
        called = {"get_connection": False}

        async def _spy_get_connection():
            called["get_connection"] = True
            return AsyncMock()

        monkeypatch.setattr(provider_mod, "get_connection", _spy_get_connection)

        cfg = AgentConfig(name="a", mcp_source_ids=[])
        result = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="a")
        assert result == []
        assert called["get_connection"] is False

    async def test_empty_source_ids_with_orphan_overrides_logs_warning(
        self, monkeypatch, caplog
    ) -> None:
        """Cycle-1 medium #4 fix: orphan-warn fires even when
        mcp_source_ids is empty."""
        cfg = AgentConfig(
            name="a",
            mcp_source_ids=[],
            mcp_overrides={"foo": {"env": {"X": "1"}}},
        )
        with caplog.at_level(logging.WARNING, logger="the_one.mcp._tool_provider"):
            result = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="a")
        assert result == []
        assert any("'foo'" in rec.getMessage() and "unknown source name" in rec.getMessage()
                   for rec in caplog.records)

    async def test_single_source_no_overrides_produces_prefixed_tools(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        src = _stub_source(source_id="src-1", name="github")
        patch_provider_deps.get = AsyncMock(return_value=src)

        client = _stub_mcp_client([
            _stub_mcp_tool("do_a"),
            _stub_mcp_tool("do_b"),
        ])

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(name="a", mcp_source_ids=["src-1"])
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        assert sorted(t.name for t in tools) == ["mcp__github__do_a", "mcp__github__do_b"]

    async def test_two_sources_no_collision_both_register(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        src1 = _stub_source(source_id="src-1", name="github")
        src2 = _stub_source(source_id="src-2", name="gitlab")

        async def _get(source_id):
            return {"src-1": src1, "src-2": src2}[source_id]

        patch_provider_deps.get = AsyncMock(side_effect=_get)

        client1 = _stub_mcp_client([_stub_mcp_tool("do_a")])
        client2 = _stub_mcp_client([_stub_mcp_tool("do_b")])

        async def _stub_acquire(agent_name, source_id, **kwargs):
            return {"src-1": client1, "src-2": client2}[source_id]

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(name="a", mcp_source_ids=["src-1", "src-2"])
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        names = sorted(t.name for t in tools)
        assert names == ["mcp__github__do_a", "mcp__gitlab__do_b"]

    async def test_failure_class_1_deleted_source_skipped(
        self, patch_provider_deps, monkeypatch, caplog
    ) -> None:
        src2 = _stub_source(source_id="src-2", name="gitlab")

        async def _get(source_id):
            if source_id == "src-deleted":
                raise KeyError(f"MCP source not found: {source_id}")
            return src2

        patch_provider_deps.get = AsyncMock(side_effect=_get)
        client = _stub_mcp_client([_stub_mcp_tool("do_b")])

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(name="a", mcp_source_ids=["src-deleted", "src-2"])
        with caplog.at_level(logging.WARNING, logger="the_one.mcp._tool_provider"):
            tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        assert [t.name for t in tools] == ["mcp__gitlab__do_b"]
        assert any("references deleted MCP source" in rec.getMessage() for rec in caplog.records)

    async def test_failure_class_2_acquire_raises_skipped(
        self, patch_provider_deps, monkeypatch, caplog
    ) -> None:
        src1 = _stub_source(source_id="src-1", name="github")
        src2 = _stub_source(source_id="src-2", name="gitlab")
        patch_provider_deps.get = AsyncMock(
            side_effect=lambda sid: {"src-1": src1, "src-2": src2}[sid]
        )

        client2 = _stub_mcp_client([_stub_mcp_tool("do_b")])

        async def _stub_acquire(agent_name, source_id, **kwargs):
            if source_id == "src-1":
                raise MCPSandboxError("bwrap missing")
            return client2

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(name="a", mcp_source_ids=["src-1", "src-2"])
        with caplog.at_level(logging.WARNING, logger="the_one.mcp._tool_provider"):
            tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        assert [t.name for t in tools] == ["mcp__gitlab__do_b"]
        assert any("failed to connect" in rec.getMessage() and "github" in rec.getMessage()
                   for rec in caplog.records)

    async def test_failure_class_2_list_tools_raises_skipped(
        self, patch_provider_deps, monkeypatch, caplog
    ) -> None:
        src1 = _stub_source(source_id="src-1", name="github")
        patch_provider_deps.get = AsyncMock(return_value=src1)

        client = _stub_mcp_client(MCPConnectionError("network down"))

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(name="a", mcp_source_ids=["src-1"])
        with caplog.at_level(logging.WARNING, logger="the_one.mcp._tool_provider"):
            tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        assert tools == []
        assert any("failed to connect" in rec.getMessage() and "github" in rec.getMessage()
                   for rec in caplog.records)

    async def test_get_tools_for_agent_graceful_skips_on_mcp_auth_required(
        self, patch_provider_deps, monkeypatch, caplog
    ) -> None:
        """F6.5 L2: MCPAuthRequired during list_tools skips the source with the
        AUTH discriminator log line; other sources' tools are still returned."""
        src1 = _stub_source(source_id="src-1", name="github")
        src2 = _stub_source(source_id="src-2", name="filesystem")

        async def _get(source_id):
            return {"src-1": src1, "src-2": src2}[source_id]

        patch_provider_deps.get = AsyncMock(side_effect=_get)

        # src-1 raises MCPAuthRequired on list_tools; src-2 returns one tool.
        client1 = _stub_mcp_client(MCPAuthRequired(source_id="src-1"))
        client2 = _stub_mcp_client([_stub_mcp_tool("read_file")])

        async def _stub_acquire(agent_name, source_id, **kwargs):
            return {"src-1": client1, "src-2": client2}[source_id]

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(name="a", mcp_source_ids=["src-1", "src-2"])
        with caplog.at_level(logging.WARNING, logger="the_one.mcp._tool_provider"):
            tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")

        # Only the healthy source's tool is present.
        assert len(tools) == 1
        assert tools[0].name == "mcp__filesystem__read_file"

        # Log line carries the AUTH discriminator, not the generic "failed to connect".
        auth_log = [
            r for r in caplog.records
            if "auth_required" in r.getMessage()
        ]
        assert len(auth_log) == 1
        assert "github" in auth_log[0].getMessage()
        # The connect-failure discriminator must NOT appear for the auth-required source.
        assert not any(
            "failed to connect" in r.getMessage() and "github" in r.getMessage()
            for r in caplog.records
        )

    async def test_failure_class_4_prefix_collision_first_wins(
        self, patch_provider_deps, monkeypatch, caplog
    ) -> None:
        # Both sources normalize to ``github``: name="github" and name="github"
        # is too obvious; use casing differences. _normalize_source_name only
        # replaces non-[a-zA-Z0-9_-] chars, so case is preserved. The cleanest
        # collision is two sources with identical names (operator created
        # both).
        src1 = _stub_source(source_id="src-1", name="github")
        src2 = _stub_source(source_id="src-2", name="github")

        async def _get(source_id):
            return {"src-1": src1, "src-2": src2}[source_id]

        patch_provider_deps.get = AsyncMock(side_effect=_get)

        client1 = _stub_mcp_client([_stub_mcp_tool("do_a")])
        client2 = _stub_mcp_client([_stub_mcp_tool("do_a")])

        async def _stub_acquire(agent_name, source_id, **kwargs):
            return {"src-1": client1, "src-2": client2}[source_id]

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(name="a", mcp_source_ids=["src-1", "src-2"])
        with caplog.at_level(logging.WARNING, logger="the_one.mcp._tool_provider"):
            tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        # Only first source's tools register.
        assert [t.name for t in tools] == ["mcp__github__do_a"]
        assert any("collision" in rec.getMessage() for rec in caplog.records)

    async def test_failure_class_4_collision_drops_partial_first_source_tools(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        """Source B has [tool_A, tool_B, tool_C]; tool_B collides with
        source A's mcp__github__tool_B; ENTIRE source B is dropped
        (NOT just tool_B and after — locks the source_tools.clear() +
        break behavior)."""
        src1 = _stub_source(source_id="src-1", name="github")
        src2 = _stub_source(source_id="src-2", name="github")

        async def _get(source_id):
            return {"src-1": src1, "src-2": src2}[source_id]

        patch_provider_deps.get = AsyncMock(side_effect=_get)

        client1 = _stub_mcp_client([_stub_mcp_tool("tool_B")])
        client2 = _stub_mcp_client([
            _stub_mcp_tool("tool_A"),  # would NOT collide individually
            _stub_mcp_tool("tool_B"),  # collides with src-1's tool_B
            _stub_mcp_tool("tool_C"),  # would NOT collide individually
        ])

        async def _stub_acquire(agent_name, source_id, **kwargs):
            return {"src-1": client1, "src-2": client2}[source_id]

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(name="a", mcp_source_ids=["src-1", "src-2"])
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        # source_tools.clear() + break drops ALL of src-2's tools
        # (including tool_A which preceded the collision) — the
        # collision is per-source, not per-tool.
        assert [t.name for t in tools] == ["mcp__github__tool_B"]

    async def test_failure_class_1_sub_case_64_char_ceiling_drops_one_tool(
        self, patch_provider_deps, monkeypatch, caplog
    ) -> None:
        """Source with 2 tools; one over the limit, the other fine.
        Non-violating tool registers; violating drops with WARNING."""
        # Use a long source name so a long tool name overflows.
        long_source_name = "s" * 50
        src = _stub_source(source_id="src-1", name=long_source_name)
        patch_provider_deps.get = AsyncMock(return_value=src)

        # short tool: "mcp__" + 50-char source + "__" + 5 = 62 chars (OK)
        # long tool:  "mcp__" + 50-char source + "__" + 20 = 77 chars (FAIL)
        client = _stub_mcp_client([
            _stub_mcp_tool("short"),
            _stub_mcp_tool("t" * 20),
        ])

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(name="a", mcp_source_ids=["src-1"])
        with caplog.at_level(logging.WARNING, logger="the_one.mcp._tool_provider"):
            tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        # The short tool registers; the long tool dropped with WARNING.
        assert len(tools) == 1
        assert tools[0].name == f"mcp__{long_source_name}__short"
        assert any("exceeds 64-char limit" in rec.getMessage() for rec in caplog.records)

    async def test_orphan_override_logs_warning_for_each_unknown_key(
        self, patch_provider_deps, monkeypatch, caplog
    ) -> None:
        """Cycle-1 test gap #2: per-key warnings, NOT
        early-exit-on-first-orphan."""
        src = _stub_source(source_id="src-1", name="github")
        patch_provider_deps.get = AsyncMock(return_value=src)
        client = _stub_mcp_client([])

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(
            name="a",
            mcp_source_ids=["src-1"],
            mcp_overrides={
                "unknown1": {"env": {"X": "1"}},
                "unknown2": {"env": {"Y": "2"}},
            },
        )
        with caplog.at_level(logging.WARNING, logger="the_one.mcp._tool_provider"):
            await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")

        unknown_warnings = [
            rec.getMessage() for rec in caplog.records
            if "unknown source name" in rec.getMessage()
        ]
        # TWO warnings — one per orphan key.
        assert len(unknown_warnings) == 2
        assert any("'unknown1'" in m for m in unknown_warnings)
        assert any("'unknown2'" in m for m in unknown_warnings)

    async def test_duplicate_source_id_registers_once(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        """Cycle-1 test gap #3: mcp_source_ids=[sid, sid] → tools register
        only once via the prefix-collision dedup path."""
        src = _stub_source(source_id="src-1", name="github")
        patch_provider_deps.get = AsyncMock(return_value=src)

        # Each acquire call returns a fresh stub client with the same
        # tool list (the production behavior — list_tools returns the
        # server's tools, which are the same regardless of caller).
        def _make_client():
            return _stub_mcp_client([_stub_mcp_tool("do_a"), _stub_mcp_tool("do_b")])

        clients = [_make_client(), _make_client()]
        client_iter = iter(clients)

        async def _stub_acquire(*args, **kwargs):
            return next(client_iter)

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(name="a", mcp_source_ids=["src-1", "src-1"])
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        # N tools, NOT 2N — collision path drops the second iteration's tools.
        names = sorted(t.name for t in tools)
        assert names == ["mcp__github__do_a", "mcp__github__do_b"]

    # ===========================================================================
    # F8 L1 — per-source tool allow/deny filter tests
    # ===========================================================================

    async def test_get_tools_for_agent_applies_enabled_tools_allowlist(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        """L1.5: enabled_tools allowlist: only the named tool passes the filter."""
        src = _stub_source(source_id="src-1", name="src", type="stdio")
        patch_provider_deps.get = AsyncMock(return_value=src)

        client = _stub_mcp_client([
            _stub_mcp_tool("read"),
            _stub_mcp_tool("write"),
            _stub_mcp_tool("delete"),
        ])

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(
            name="a",
            mcp_source_ids=["src-1"],
            mcp_overrides={"src": {"enabled_tools": ["read"]}},
        )
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        names = [t.name for t in tools]
        assert names == ["mcp__src__read"]

    async def test_get_tools_for_agent_applies_disabled_tools_denylist(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        """L1.5: disabled_tools denylist: named tool removed, others pass."""
        src = _stub_source(source_id="src-1", name="src", type="stdio")
        patch_provider_deps.get = AsyncMock(return_value=src)

        client = _stub_mcp_client([
            _stub_mcp_tool("read"),
            _stub_mcp_tool("write"),
            _stub_mcp_tool("delete"),
        ])

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(
            name="a",
            mcp_source_ids=["src-1"],
            mcp_overrides={"src": {"disabled_tools": ["delete"]}},
        )
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        names = sorted(t.name for t in tools)
        assert names == ["mcp__src__read", "mcp__src__write"]

    async def test_get_tools_for_agent_applies_intersection_filter(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        """L1.5: intersection — enabled_tools + disabled_tools overlap: disabled wins."""
        src = _stub_source(source_id="src-1", name="src", type="stdio")
        patch_provider_deps.get = AsyncMock(return_value=src)

        client = _stub_mcp_client([
            _stub_mcp_tool("read"),
            _stub_mcp_tool("write"),
            _stub_mcp_tool("delete"),
        ])

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(
            name="a",
            mcp_source_ids=["src-1"],
            mcp_overrides={"src": {"enabled_tools": ["read", "write"], "disabled_tools": ["write"]}},
        )
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        names = [t.name for t in tools]
        assert names == ["mcp__src__read"]

    async def test_get_tools_for_agent_empty_enabled_list_drops_all(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        """L1.5: empty enabled_tools list filters out ALL tools from the source."""
        src = _stub_source(source_id="src-1", name="src", type="stdio")
        patch_provider_deps.get = AsyncMock(return_value=src)

        client = _stub_mcp_client([
            _stub_mcp_tool("read"),
            _stub_mcp_tool("write"),
        ])

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(
            name="a",
            mcp_source_ids=["src-1"],
            mcp_overrides={"src": {"enabled_tools": []}},
        )
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        assert tools == []

    async def test_get_tools_for_agent_disabled_unknown_tool_is_noop(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        """L1.5: disabled_tools naming a non-existent tool: no-op, no error."""
        src = _stub_source(source_id="src-1", name="src", type="stdio")
        patch_provider_deps.get = AsyncMock(return_value=src)

        client = _stub_mcp_client([
            _stub_mcp_tool("read"),
            _stub_mcp_tool("write"),
        ])

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(
            name="a",
            mcp_source_ids=["src-1"],
            mcp_overrides={"src": {"disabled_tools": ["nonexistent_tool"]}},
        )
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        names = sorted(t.name for t in tools)
        assert names == ["mcp__src__read", "mcp__src__write"]

    async def test_get_tools_for_agent_no_override_entry_passes_through_full_list(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        """L1.5: no override entry for the source → full tool list registered (current behavior preserved)."""
        src = _stub_source(source_id="src-1", name="src", type="stdio")
        patch_provider_deps.get = AsyncMock(return_value=src)

        client = _stub_mcp_client([
            _stub_mcp_tool("read"),
            _stub_mcp_tool("write"),
            _stub_mcp_tool("delete"),
        ])

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(
            name="a",
            mcp_source_ids=["src-1"],
            # No mcp_overrides for "src"
        )
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        names = sorted(t.name for t in tools)
        assert names == ["mcp__src__delete", "mcp__src__read", "mcp__src__write"]

    async def test_get_tools_for_agent_filter_uses_unprefixed_names(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        """L1.2: filter matches un-prefixed mt.name (e.g. 'read_file', NOT 'mcp__src__read_file')."""
        src = _stub_source(source_id="src-1", name="src", type="stdio")
        patch_provider_deps.get = AsyncMock(return_value=src)

        client = _stub_mcp_client([
            _stub_mcp_tool("read_file"),
            _stub_mcp_tool("write_file"),
        ])

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(
            name="a",
            mcp_source_ids=["src-1"],
            # Using un-prefixed name in allowlist
            mcp_overrides={"src": {"enabled_tools": ["read_file"]}},
        )
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        assert len(tools) == 1
        assert tools[0].name == "mcp__src__read_file"

    async def test_get_tools_for_agent_filter_with_streamable_http_source(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        """L1.5: filter applies to streamable-http sources, not just stdio."""
        src = _stub_source(
            source_id="src-1", name="src", type="streamable-http",
            secrets={"dcr_credentials": {"client_id": "x"}, "access_token": "tok"},
        )
        patch_provider_deps.get = AsyncMock(return_value=src)

        client = _stub_mcp_client([
            _stub_mcp_tool("search"),
            _stub_mcp_tool("fetch"),
            _stub_mcp_tool("embed"),
        ])

        async def _stub_acquire(*args, **kwargs):
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(
            name="a",
            mcp_source_ids=["src-1"],
            mcp_overrides={"src": {"enabled_tools": ["search", "fetch"]}},
        )
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")
        names = sorted(t.name for t in tools)
        assert names == ["mcp__src__fetch", "mcp__src__search"]

    async def test_override_applies_correctly(
        self, patch_provider_deps, monkeypatch
    ) -> None:
        """``acquire`` was called with ``source_override`` reflecting
        the agent's override (env merged for stdio)."""
        # F2 contract (post-HAT-A4): source.secrets IS the flat env kv
        # table for stdio. NOT nested under "env".
        src = _stub_source(
            source_id="src-1",
            name="github",
            type="stdio",
            secrets={"OPERATOR": "1"},
        )
        patch_provider_deps.get = AsyncMock(return_value=src)

        client = _stub_mcp_client([_stub_mcp_tool("do_a")])

        captured: dict[str, Any] = {}

        async def _stub_acquire(agent_name, source_id, **kwargs):
            captured["source_override"] = kwargs.get("source_override")
            return client

        monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)

        cfg = AgentConfig(
            name="a",
            mcp_source_ids=["src-1"],
            mcp_overrides={"github": {"env": {"AGENT": "2"}}},
        )
        await MCPToolProvider().get_tools_for_agent(cfg, agent_name="agent-a")

        override = captured["source_override"]
        # operator preserved + agent merged in flat at top level
        # (post-HAT-A4 fix; matches transports/stdio.py:224-225 contract).
        assert override.secrets == {"OPERATOR": "1", "AGENT": "2"}


# ===========================================================================
# TestAgentFactoryMCPIntegration
# ===========================================================================


def _fake_get_provider(name: str, **kwargs: Any) -> FakeLLM:
    return FakeLLM(responses=[])


def _make_provider_config(provider_id: str = "test-provider") -> LLMProviderConfig:
    return LLMProviderConfig(
        id=provider_id,
        name="Test Provider",
        type="ollama",
        base_url="http://localhost:11434/v1",
    )


class _InMemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, AgentConfig] = {}

    async def list_agents(self) -> list[str]:
        return sorted(self._data.keys())

    async def load(self, name: str) -> AgentConfig:
        if name not in self._data:
            raise KeyError(name)
        return self._data[name]

    async def save(self, config: AgentConfig) -> None:
        self._data[config.name] = config

    async def exists(self, name: str) -> bool:
        return name in self._data


class _StubToolProvider:
    @property
    def name(self) -> str:
        return "stub"

    def get_tools(
        self, tool_configs=None, agent_overrides=None, agent_name=None
    ):
        return [StubTool("tool_a", agent_name=agent_name)]


class TestAgentFactoryMCPIntegration:
    async def test_factory_with_mcp_provider_none_skips_mcp_wiring(
        self, monkeypatch
    ) -> None:
        """``mcp_provider=None`` — defaults to a fresh MCPToolProvider
        instance. With empty ``mcp_source_ids`` the create() path skips
        the MCP attach branch (no get_tools_for_agent call) per the
        locked guard ``self.mcp_provider is not None and
        config.mcp_source_ids``."""
        store = _InMemoryStore()
        cfg = AgentConfig(
            name="custom",
            provider_config_id="test-provider",
            llm_model="m",
            mcp_source_ids=[],  # empty → MCP attach branch skipped
        )
        await store.save(cfg)

        # Spy on get_tools_for_agent to verify it's NOT called.
        called = {"n": 0}

        async def _spy_get_tools_for_agent(self, cfg, *, agent_name):
            called["n"] += 1
            return []

        monkeypatch.setattr(
            MCPToolProvider, "get_tools_for_agent", _spy_get_tools_for_agent
        )

        mock_repo = AsyncMock()
        mock_repo.get = AsyncMock(return_value=_make_provider_config())
        mock_tool_repo = AsyncMock()
        mock_tool_repo.list = AsyncMock(return_value=[])

        with (
            patch("the_one.agent.factory.get_provider", _fake_get_provider),
            patch("the_one.agent.factory.settings") as mock_settings,
            patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
            patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
            patch("the_one.db.repositories.LLMProviderRepository", return_value=mock_repo),
            patch("the_one.db.repositories.ToolConfigRepository", return_value=mock_tool_repo),
        ):
            mock_settings.agents_dir = Path("/tmp/test-agents")
            mock_settings.data_dir = Path("/tmp/test-data")
            mock_settings.ensure_dirs = lambda: None

            factory = AgentFactory(
                store=store,
                tool_providers=[_StubToolProvider()],
                mcp_provider=None,
            )
            agent = await factory.create("custom")
            # mcp_provider defaults to a fresh instance.
            assert isinstance(factory.mcp_provider, MCPToolProvider)
            # Empty mcp_source_ids → create() skips the MCP attach branch.
            assert called["n"] == 0
            # Built-in tool still wired.
            assert "tool_a" in agent.tools.tool_names

    async def test_factory_default_mcp_provider_constructs(self) -> None:
        """Fresh AgentFactory() has a MCPToolProvider instance."""
        factory = AgentFactory()
        assert isinstance(factory.mcp_provider, MCPToolProvider)

    async def test_factory_create_with_mcp_attached_registers_tools(
        self, monkeypatch
    ) -> None:
        """Full path: AgentConfig with mcp_source_ids; mock MCP path;
        assert prefixed tools in registry; verify disabled_tools filter."""
        store = _InMemoryStore()
        cfg = AgentConfig(
            name="mcp-agent",
            provider_config_id="test-provider",
            llm_model="m",
            mcp_source_ids=["src-1"],
            disabled_tools=["mcp__github__bar"],
        )
        await store.save(cfg)

        # Patch MCPToolProvider.get_tools_for_agent to return
        # pre-baked MCPClientTool instances.
        src = _stub_source(source_id="src-1", name="github")
        tool_foo = MCPClientTool(
            _stub_mcp_tool("foo"),
            source_id="src-1",
            source_name="github",
            agent_name="mcp-agent",
            effective_source=src,
        )
        tool_bar = MCPClientTool(
            _stub_mcp_tool("bar"),
            source_id="src-1",
            source_name="github",
            agent_name="mcp-agent",
            effective_source=src,
        )

        async def _stub_get_tools_for_agent(self, cfg, *, agent_name):
            return [tool_foo, tool_bar]

        monkeypatch.setattr(
            MCPToolProvider, "get_tools_for_agent", _stub_get_tools_for_agent
        )

        mock_repo = AsyncMock()
        mock_repo.get = AsyncMock(return_value=_make_provider_config())
        mock_tool_repo = AsyncMock()
        mock_tool_repo.list = AsyncMock(return_value=[])

        with (
            patch("the_one.agent.factory.get_provider", _fake_get_provider),
            patch("the_one.agent.factory.settings") as mock_settings,
            patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
            patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
            patch("the_one.db.repositories.LLMProviderRepository", return_value=mock_repo),
            patch("the_one.db.repositories.ToolConfigRepository", return_value=mock_tool_repo),
        ):
            mock_settings.agents_dir = Path("/tmp/test-agents")
            mock_settings.data_dir = Path("/tmp/test-data")
            mock_settings.ensure_dirs = lambda: None

            factory = AgentFactory(
                store=store,
                tool_providers=[_StubToolProvider()],
            )
            agent = await factory.create("mcp-agent")

        # foo registered; bar filtered out via disabled_tools.
        assert "mcp__github__foo" in agent.tools.tool_names
        assert "mcp__github__bar" not in agent.tools.tool_names
