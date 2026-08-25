"""Tests for the two read projections (M21 F01 L02, LD5) — AC6, AC7.

Pure-function tests over an isolated SQLite connection + encryptor, no HTTP
layer. The regression net mirrors ``test_list_returns_masked_secrets``: an
assertion on ``json.dumps(result)`` TEXT, not on which fields a masking
helper touches.
"""

from __future__ import annotations

import json

import aiosqlite
import pytest
from cryptography.fernet import Fernet

from the_one.agent.config import AgentConfig
from the_one.db.models import Connector, KnowledgeBase, LLMProviderConfig, MCPSource
from the_one.db.repositories import (
    ConnectorRepository,
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    ToolConfigRepository,
)
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.self_configuration.projection import (
    build_describe_my_capabilities,
    build_get_my_configuration,
)


@pytest.fixture
async def db(tmp_path):
    conn = await aiosqlite.connect(str(tmp_path / "test.db"))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    test_key = Fernet.generate_key()
    encryptor = Encryptor(test_key, key_path=tmp_path / "test.key")
    yield conn, encryptor
    await conn.close()


# ── AC6 — get_my_configuration is secret-free by construction ───────────


class TestGetMyConfigurationSecretFree:
    async def test_projection_contains_no_seeded_secrets(self, db) -> None:
        conn, encryptor = db
        provider_repo = LLMProviderRepository(conn, encryptor)
        kb_repo = KnowledgeBaseRepository(conn)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        connector_repo = ConnectorRepository(conn, encryptor)

        provider = LLMProviderConfig(
            id="prov-1",
            name="My Anthropic",
            type="anthropic",
            base_url="https://api.anthropic.com",
            api_key="sk-ant-SUPERSECRETKEY",
        )
        await provider_repo.create(provider)

        kb = KnowledgeBase(id="kb-1", name="My KB", description="")
        await kb_repo.create(kb)

        mcp_source = MCPSource(
            id="mcp-1",
            name="github",
            type="streamable-http",
            config={"url": "https://example.com/mcp"},
            secrets={"Authorization": "Bearer MCP_SOURCE_SECRET_TOKEN"},
        )
        await mcp_repo.create(mcp_source)

        connector = Connector(
            id="conn-1",
            name="My Discord",
            type="stub",
            secrets={"token": "CONNECTOR_SUPER_SECRET_TOKEN"},
        )
        await connector_repo.create(connector)

        config = AgentConfig(
            name="secret-agent",
            provider_config_id="prov-1",
            kb_ids=["kb-1"],
            mcp_source_ids=["mcp-1"],
            connector_ids=["conn-1"],
            mcp_overrides={
                "github": {
                    "bearer_token": "OVERRIDE_BEARER_SECRET",
                    "headers": {"X-Api-Key": "OVERRIDE_HEADER_SECRET"},
                }
            },
        )

        result = await build_get_my_configuration(
            config, provider_repo=provider_repo, kb_repo=kb_repo
        )
        text = json.dumps(result)

        for secret in (
            "sk-ant-SUPERSECRETKEY",
            "MCP_SOURCE_SECRET_TOKEN",
            "CONNECTOR_SUPER_SECRET_TOKEN",
            "OVERRIDE_BEARER_SECRET",
            "OVERRIDE_HEADER_SECRET",
        ):
            assert secret not in text

        assert set(result.keys()) == {
            "name",
            "description",
            "system_prompt",
            "llm_model",
            "provider",
            "max_iterations",
            "chat_history_retention_days",
            "enabled_tools",
            "disabled_tools",
            "knowledge_bases",
        }
        assert result["provider"] == {"name": "My Anthropic", "type": "anthropic"}
        assert result["knowledge_bases"] == ["My KB"]

    async def test_provider_none_when_agent_has_no_provider(self, db) -> None:
        conn, encryptor = db
        provider_repo = LLMProviderRepository(conn, encryptor)
        kb_repo = KnowledgeBaseRepository(conn)
        config = AgentConfig(name="no-provider-agent")
        result = await build_get_my_configuration(
            config, provider_repo=provider_repo, kb_repo=kb_repo
        )
        assert result["provider"] is None


# ── AC7 — describe_my_capabilities reflects the operator's controls ─────


class TestDescribeMyCapabilities:
    async def test_operator_disabled_builtin_tool_is_absent(self, db) -> None:
        conn, encryptor = db
        tool_config_repo = ToolConfigRepository(conn, encryptor)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        connector_repo = ConnectorRepository(conn, encryptor)

        await tool_config_repo.upsert("shell", {}, enabled=False)

        config = AgentConfig(name="operator-disabled-agent")
        result = await build_describe_my_capabilities(
            config,
            tool_config_repo=tool_config_repo,
            mcp_repo=mcp_repo,
            connector_repo=connector_repo,
        )
        names = {t["name"] for t in result["builtin_tools"]}
        assert "shell" not in names
        assert "read_file" in names  # sanity: other tools still present

    async def test_agent_disabled_builtin_tool_is_absent(self, db) -> None:
        conn, encryptor = db
        tool_config_repo = ToolConfigRepository(conn, encryptor)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        connector_repo = ConnectorRepository(conn, encryptor)

        config = AgentConfig(name="agent-disabled-agent", disabled_tools=["shell"])
        result = await build_describe_my_capabilities(
            config,
            tool_config_repo=tool_config_repo,
            mcp_repo=mcp_repo,
            connector_repo=connector_repo,
        )
        names = {t["name"] for t in result["builtin_tools"]}
        assert "shell" not in names

    async def test_mcp_tools_disabled_per_agent_are_absent_via_filter(self, db) -> None:
        """AC7's binding assertion: the filter is exercised, not bypassed
        — this test would pass even with a broken filter unless it
        specifically confirms the operator-disabled tool is missing."""
        conn, encryptor = db
        tool_config_repo = ToolConfigRepository(conn, encryptor)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        connector_repo = ConnectorRepository(conn, encryptor)

        source = MCPSource(
            id="mcp-2",
            name="github",
            type="streamable-http",
            config={
                "url": "https://example.com/mcp",
                "_cache": {
                    "tools": [
                        {"name": "list_issues", "description": "", "input_schema": {}},
                        {"name": "delete_repo", "description": "", "input_schema": {}},
                    ]
                },
            },
        )
        await mcp_repo.create(source)

        config = AgentConfig(
            name="mcp-filter-agent",
            mcp_source_ids=["mcp-2"],
            mcp_overrides={"github": {"disabled_tools": ["delete_repo"]}},
        )
        result = await build_describe_my_capabilities(
            config,
            tool_config_repo=tool_config_repo,
            mcp_repo=mcp_repo,
            connector_repo=connector_repo,
        )
        github_entry = next(s for s in result["mcp_sources"] if s["name"] == "github")
        assert github_entry["tools"] == ["list_issues"]
        assert github_entry["tools_known"] is True

    async def test_self_configuration_source_itself_is_listed(self, db) -> None:
        conn, encryptor = db
        tool_config_repo = ToolConfigRepository(conn, encryptor)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        connector_repo = ConnectorRepository(conn, encryptor)

        source = MCPSource(
            id="mcp-self",
            name="self-configuration (listing-agent)",
            type="streamable-http",
            config={
                "url": "http://127.0.0.1:9999/mcp/self-configuration/",
                "self_configuration": {"agent": "listing-agent"},
                "_cache": {
                    "tools": [
                        {"name": "get_my_configuration", "description": "", "input_schema": {}},
                        {
                            "name": "describe_my_capabilities",
                            "description": "",
                            "input_schema": {},
                        },
                    ]
                },
            },
        )
        await mcp_repo.create(source)

        config = AgentConfig(name="listing-agent", mcp_source_ids=["mcp-self"])
        result = await build_describe_my_capabilities(
            config,
            tool_config_repo=tool_config_repo,
            mcp_repo=mcp_repo,
            connector_repo=connector_repo,
        )
        entry = next(
            s for s in result["mcp_sources"] if s["name"] == "self-configuration (listing-agent)"
        )
        assert set(entry["tools"]) == {"get_my_configuration", "describe_my_capabilities"}

    async def test_no_source_config_url_header_or_secret_in_result_text(self, db) -> None:
        conn, encryptor = db
        tool_config_repo = ToolConfigRepository(conn, encryptor)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        connector_repo = ConnectorRepository(conn, encryptor)

        source = MCPSource(
            id="mcp-3",
            name="secret-source",
            type="streamable-http",
            config={
                "url": "https://internal.example.com/leaky-path",
                "headers": {"X-Custom": "not-a-secret-but-should-not-leak-either"},
                "_cache": {"tools": [{"name": "do_thing", "description": "", "input_schema": {}}]},
            },
            secrets={"Authorization": "Bearer MUST_NOT_LEAK"},
        )
        await mcp_repo.create(source)

        connector = Connector(
            id="conn-2",
            name="secret-connector",
            type="stub",
            secrets={"token": "CONNECTOR_MUST_NOT_LEAK"},
        )
        await connector_repo.create(connector)

        config = AgentConfig(
            name="no-leak-capabilities-agent",
            mcp_source_ids=["mcp-3"],
            connector_ids=["conn-2"],
        )
        result = await build_describe_my_capabilities(
            config,
            tool_config_repo=tool_config_repo,
            mcp_repo=mcp_repo,
            connector_repo=connector_repo,
        )
        text = json.dumps(result)
        assert "internal.example.com" not in text
        assert "leaky-path" not in text
        assert "not-a-secret-but-should-not-leak-either" not in text
        assert "MUST_NOT_LEAK" not in text
        assert "CONNECTOR_MUST_NOT_LEAK" not in text
        assert set(result.keys()) == {"builtin_tools", "mcp_sources", "connectors"}
        assert result["connectors"] == [{"name": "secret-connector", "type": "stub"}]

    async def test_source_with_no_cache_reports_tools_known_false(self, db) -> None:
        conn, encryptor = db
        tool_config_repo = ToolConfigRepository(conn, encryptor)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        connector_repo = ConnectorRepository(conn, encryptor)

        source = MCPSource(
            id="mcp-4",
            name="never-connected",
            type="streamable-http",
            config={"url": "https://example.com/mcp"},
        )
        await mcp_repo.create(source)

        config = AgentConfig(name="uncached-agent", mcp_source_ids=["mcp-4"])
        result = await build_describe_my_capabilities(
            config,
            tool_config_repo=tool_config_repo,
            mcp_repo=mcp_repo,
            connector_repo=connector_repo,
        )
        entry = next(s for s in result["mcp_sources"] if s["name"] == "never-connected")
        assert entry == {
            "name": "never-connected",
            "type": "streamable-http",
            "tools": [],
            "tools_known": False,
        }
