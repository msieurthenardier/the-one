"""Tests for all database repositories."""

from __future__ import annotations

import pytest

from the_one.agent.config import AgentConfig
from the_one.db.models import ChatSession, KBItem, KnowledgeBase, MCPSource
from the_one.db.repositories import (
    ChatSessionRepository,
    KBItemRepository,
    KnowledgeBaseRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)


@pytest.fixture
async def conn(tmp_path):
    """Create a fresh in-memory-like DB connection with schema applied."""
    import aiosqlite

    from the_one.db.schema import ensure_schema

    db_path = tmp_path / "test.db"
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(connection)
    yield connection
    await connection.close()


@pytest.fixture
def agent_store(conn):
    return SQLiteAgentStore(conn)


@pytest.fixture
def kb_repo(conn):
    return KnowledgeBaseRepository(conn)


@pytest.fixture
def kb_item_repo(conn):
    return KBItemRepository(conn)


@pytest.fixture
def mcp_repo(conn):
    return MCPSourceRepository(conn)


@pytest.fixture
def chat_repo(conn):
    return ChatSessionRepository(conn)


@pytest.fixture
def tool_config_repo(conn):
    return ToolConfigRepository(conn)


# ── Agent Store ───────────────────────────────────────────────────────────


class TestSQLiteAgentStore:
    async def test_save_and_load(self, agent_store: SQLiteAgentStore) -> None:
        cfg = AgentConfig(name="test", description="A test agent")
        await agent_store.save(cfg)
        loaded = await agent_store.load("test")
        assert loaded.name == "test"
        assert loaded.description == "A test agent"

    async def test_list_agents(self, agent_store: SQLiteAgentStore) -> None:
        for name in ("charlie", "alpha", "bravo"):
            await agent_store.save(AgentConfig(name=name))
        names = await agent_store.list_agents()
        assert names == ["alpha", "bravo", "charlie"]

    async def test_exists(self, agent_store: SQLiteAgentStore) -> None:
        assert await agent_store.exists("nope") is False
        await agent_store.save(AgentConfig(name="exists"))
        assert await agent_store.exists("exists") is True

    async def test_delete(self, agent_store: SQLiteAgentStore) -> None:
        await agent_store.save(AgentConfig(name="doomed"))
        await agent_store.delete("doomed")
        assert await agent_store.exists("doomed") is False

    async def test_delete_nonexistent_raises(self, agent_store: SQLiteAgentStore) -> None:
        with pytest.raises(KeyError):
            await agent_store.delete("ghost")

    async def test_load_nonexistent_raises(self, agent_store: SQLiteAgentStore) -> None:
        with pytest.raises(KeyError):
            await agent_store.load("missing")

    async def test_save_overwrites(self, agent_store: SQLiteAgentStore) -> None:
        await agent_store.save(AgentConfig(name="x", description="old"))
        await agent_store.save(AgentConfig(name="x", description="new"))
        loaded = await agent_store.load("x")
        assert loaded.description == "new"

    async def test_json_fields_round_trip(self, agent_store: SQLiteAgentStore) -> None:
        cfg = AgentConfig(
            name="json-test",
            enabled_tools=["tool_a", "tool_b"],
            disabled_tools=["tool_c"],
            kb_ids=["kb1", "kb2"],
            mcp_source_ids=["mcp1"],
        )
        await agent_store.save(cfg)
        loaded = await agent_store.load("json-test")
        assert loaded.enabled_tools == ["tool_a", "tool_b"]
        assert loaded.disabled_tools == ["tool_c"]
        assert loaded.kb_ids == ["kb1", "kb2"]
        assert loaded.mcp_source_ids == ["mcp1"]

    async def test_enabled_tools_none(self, agent_store: SQLiteAgentStore) -> None:
        cfg = AgentConfig(name="null-tools", enabled_tools=None)
        await agent_store.save(cfg)
        loaded = await agent_store.load("null-tools")
        assert loaded.enabled_tools is None

    async def test_tool_overrides_round_trip(self, agent_store: SQLiteAgentStore) -> None:
        """Saving an agent with `tool_overrides` set roundtrips through
        the SQLite store cleanly (Decision 1: dict[str, dict[str, Any]])."""
        cfg = AgentConfig(
            name="override-test",
            tool_overrides={"shell": {"timeout": 30}, "read_file": {"max_bytes": 1000}},
        )
        await agent_store.save(cfg)
        loaded = await agent_store.load("override-test")
        assert loaded.tool_overrides == {
            "shell": {"timeout": 30},
            "read_file": {"max_bytes": 1000},
        }

    async def test_tool_overrides_none_default(self, agent_store: SQLiteAgentStore) -> None:
        """An agent without `tool_overrides` set roundtrips as None
        (locked-down NULL semantic — Decision 1)."""
        cfg = AgentConfig(name="no-overrides")
        await agent_store.save(cfg)
        loaded = await agent_store.load("no-overrides")
        assert loaded.tool_overrides is None


# ── Knowledge Base Repository ─────────────────────────────────────────────


class TestKnowledgeBaseRepository:
    async def test_create_and_get(self, kb_repo: KnowledgeBaseRepository) -> None:
        kb = KnowledgeBase(id="kb1", name="Test KB", description="desc")
        await kb_repo.create(kb)
        loaded = await kb_repo.get("kb1")
        assert loaded.name == "Test KB"

    async def test_list(self, kb_repo: KnowledgeBaseRepository) -> None:
        await kb_repo.create(KnowledgeBase(id="b", name="Bravo"))
        await kb_repo.create(KnowledgeBase(id="a", name="Alpha"))
        kbs = await kb_repo.list()
        assert [kb.name for kb in kbs] == ["Alpha", "Bravo"]

    async def test_update(self, kb_repo: KnowledgeBaseRepository) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="Old"))
        kb = await kb_repo.get("kb1")
        kb.name = "New"
        await kb_repo.update(kb)
        loaded = await kb_repo.get("kb1")
        assert loaded.name == "New"

    async def test_delete(self, kb_repo: KnowledgeBaseRepository) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="Doomed"))
        await kb_repo.delete("kb1")
        with pytest.raises(KeyError):
            await kb_repo.get("kb1")

    async def test_get_nonexistent_raises(self, kb_repo: KnowledgeBaseRepository) -> None:
        with pytest.raises(KeyError):
            await kb_repo.get("nope")


# ── KB Item Repository ────────────────────────────────────────────────────


class TestKBItemRepository:
    async def test_create_and_list(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        item = KBItem(id="item1", kb_id="kb1", type="file", path_or_url="/tmp/x")
        await kb_item_repo.create(item)
        items = await kb_item_repo.list("kb1")
        assert len(items) == 1
        assert items[0].path_or_url == "/tmp/x"

    async def test_delete(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(KBItem(id="i1", kb_id="kb1", type="url", path_or_url="http://x"))
        await kb_item_repo.delete("i1")
        items = await kb_item_repo.list("kb1")
        assert len(items) == 0

    async def test_cascade_delete(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(KBItem(id="i1", kb_id="kb1", type="file", path_or_url="/a"))
        await kb_repo.delete("kb1")
        items = await kb_item_repo.list("kb1")
        assert len(items) == 0


# ── MCP Source Repository ─────────────────────────────────────────────────


class TestMCPSourceRepository:
    async def test_create_and_get(self, mcp_repo: MCPSourceRepository) -> None:
        source = MCPSource(id="s1", name="Test", type="stdio", config={"command": "python"})
        await mcp_repo.create(source)
        loaded = await mcp_repo.get("s1")
        assert loaded.name == "Test"
        assert loaded.config == {"command": "python"}

    async def test_list(self, mcp_repo: MCPSourceRepository) -> None:
        await mcp_repo.create(MCPSource(id="b", name="Bravo", type="sse"))
        await mcp_repo.create(MCPSource(id="a", name="Alpha", type="stdio"))
        sources = await mcp_repo.list()
        assert [s.name for s in sources] == ["Alpha", "Bravo"]

    async def test_update(self, mcp_repo: MCPSourceRepository) -> None:
        await mcp_repo.create(MCPSource(id="s1", name="Old", type="stdio"))
        source = await mcp_repo.get("s1")
        source.name = "New"
        await mcp_repo.update(source)
        loaded = await mcp_repo.get("s1")
        assert loaded.name == "New"

    async def test_delete(self, mcp_repo: MCPSourceRepository) -> None:
        await mcp_repo.create(MCPSource(id="s1", name="Doomed", type="sse"))
        await mcp_repo.delete("s1")
        with pytest.raises(KeyError):
            await mcp_repo.get("s1")


# ── Chat Session Repository ──────────────────────────────────────────────


class TestChatSessionRepository:
    async def test_create_and_get(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        await agent_store.save(AgentConfig(name="agent1"))
        session = ChatSession(id="s1", agent_name="agent1", title="Hello")
        await chat_repo.create(session)
        loaded = await chat_repo.get("s1")
        assert loaded.title == "Hello"

    async def test_list(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(ChatSession(id="s1", agent_name="agent1"))
        await chat_repo.create(ChatSession(id="s2", agent_name="agent1"))
        sessions = await chat_repo.list()
        assert len(sessions) == 2

    async def test_list_by_agent(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        await agent_store.save(AgentConfig(name="a1"))
        await agent_store.save(AgentConfig(name="a2"))
        await chat_repo.create(ChatSession(id="s1", agent_name="a1"))
        await chat_repo.create(ChatSession(id="s2", agent_name="a2"))
        sessions = await chat_repo.list(agent_name="a1")
        assert len(sessions) == 1
        assert sessions[0].agent_name == "a1"

    async def test_update(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(ChatSession(id="s1", agent_name="agent1", title="Old"))
        session = await chat_repo.get("s1")
        session.title = "New"
        await chat_repo.update(session)
        loaded = await chat_repo.get("s1")
        assert loaded.title == "New"

    async def test_delete(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(ChatSession(id="s1", agent_name="agent1"))
        await chat_repo.delete("s1")
        with pytest.raises(KeyError):
            await chat_repo.get("s1")

    async def test_purge_messages(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        await agent_store.save(AgentConfig(name="agent1"))
        session = ChatSession(id="s1", agent_name="agent1", messages='[{"role":"user"}]')
        await chat_repo.create(session)
        await chat_repo.purge_messages("s1")
        loaded = await chat_repo.get("s1")
        assert loaded.messages == "[]"

    async def test_agent_delete_does_not_cascade_to_sessions(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Deleting an agent must NOT delete its sessions (schema v5).

        Per Leg 02 design intent (Flight 05): users must keep seeing the
        session in the list with an actionable `agent_deleted` banner,
        not silently lose the chat history. The schema v5 migration
        dropped the FK CASCADE on chat_sessions.agent_name; this test is
        the regression guard at the repository layer.
        """
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(ChatSession(id="s1", agent_name="agent1"))
        await agent_store.delete("agent1")
        sessions = await chat_repo.list(agent_name="agent1")
        assert len(sessions) == 1
        assert sessions[0].id == "s1"
        # agent_name must remain set to the deleted agent's name
        # (free-text), not nulled or removed.
        assert sessions[0].agent_name == "agent1"


# ── Tool Config Repository ───────────────────────────────────────────────


class TestToolConfigRepository:
    """CRUD coverage for ToolConfigRepository (the resolver-feeding store)."""

    async def test_upsert_inserts_then_lists(self, tool_config_repo: ToolConfigRepository) -> None:
        await tool_config_repo.upsert("shell", {"timeout": 30})
        items = await tool_config_repo.list()
        assert len(items) == 1
        assert items[0].name == "shell"
        assert items[0].config == {"timeout": 30}

    async def test_list_orders_by_name(self, tool_config_repo: ToolConfigRepository) -> None:
        await tool_config_repo.upsert("shell", {})
        await tool_config_repo.upsert("read_file", {})
        await tool_config_repo.upsert("python_exec", {})
        items = await tool_config_repo.list()
        assert [i.name for i in items] == ["python_exec", "read_file", "shell"]

    async def test_list_all_returns_dict_shape(
        self, tool_config_repo: ToolConfigRepository
    ) -> None:
        """list_all is the resolver-facing read — returns {name: config}."""
        await tool_config_repo.upsert("shell", {"timeout": 30})
        await tool_config_repo.upsert("read_file", {"max_bytes": 1000})
        result = await tool_config_repo.list_all()
        assert result == {
            "shell": {"timeout": 30},
            "read_file": {"max_bytes": 1000},
        }

    async def test_list_all_empty_when_no_rows(
        self, tool_config_repo: ToolConfigRepository
    ) -> None:
        assert await tool_config_repo.list_all() == {}

    async def test_get_returns_row(self, tool_config_repo: ToolConfigRepository) -> None:
        await tool_config_repo.upsert("shell", {"timeout": 30})
        item = await tool_config_repo.get("shell")
        assert item.name == "shell"
        assert item.config == {"timeout": 30}

    async def test_get_missing_raises(self, tool_config_repo: ToolConfigRepository) -> None:
        with pytest.raises(KeyError):
            await tool_config_repo.get("nope")

    async def test_upsert_updates_existing_row_and_bumps_updated_at(
        self, tool_config_repo: ToolConfigRepository
    ) -> None:
        await tool_config_repo.upsert("shell", {"timeout": 30})
        first = await tool_config_repo.get("shell")
        # Tiny sleep to ensure updated_at differs at second granularity.
        # The ISO-format _now_iso() includes microseconds, but be safe.
        import asyncio

        await asyncio.sleep(0.01)
        await tool_config_repo.upsert("shell", {"timeout": 60})
        updated = await tool_config_repo.get("shell")
        assert updated.config == {"timeout": 60}
        # created_at preserved on update; updated_at bumped.
        assert updated.created_at == first.created_at
        assert updated.updated_at >= first.updated_at

    async def test_delete_removes_row(self, tool_config_repo: ToolConfigRepository) -> None:
        await tool_config_repo.upsert("shell", {})
        await tool_config_repo.delete("shell")
        assert await tool_config_repo.exists("shell") is False

    async def test_delete_missing_raises(self, tool_config_repo: ToolConfigRepository) -> None:
        with pytest.raises(KeyError):
            await tool_config_repo.delete("ghost")

    async def test_exists(self, tool_config_repo: ToolConfigRepository) -> None:
        assert await tool_config_repo.exists("shell") is False
        await tool_config_repo.upsert("shell", {})
        assert await tool_config_repo.exists("shell") is True

    # ── L0: enabled flag round-trips ───────────────────────────────

    async def test_upsert_default_enabled_true(
        self, tool_config_repo: ToolConfigRepository
    ) -> None:
        await tool_config_repo.upsert("shell", {})
        items = await tool_config_repo.list()
        assert len(items) == 1
        assert items[0].enabled is True

    async def test_upsert_persists_enabled_false(
        self, tool_config_repo: ToolConfigRepository
    ) -> None:
        await tool_config_repo.upsert("shell", {}, enabled=False)
        got = await tool_config_repo.get("shell")
        assert got.enabled is False

    async def test_upsert_round_trips_enabled_true_after_false(
        self, tool_config_repo: ToolConfigRepository
    ) -> None:
        await tool_config_repo.upsert("shell", {}, enabled=False)
        await tool_config_repo.upsert("shell", {}, enabled=True)
        got = await tool_config_repo.get("shell")
        assert got.enabled is True

    async def test_list_all_omits_enabled(self, tool_config_repo: ToolConfigRepository) -> None:
        # The resolver-facing list_all() must stay {name: config_dict}.
        # Admin read path in L1 uses list() (which returns full models).
        await tool_config_repo.upsert("shell", {"timeout": 1}, enabled=False)
        result = await tool_config_repo.list_all()
        assert result == {"shell": {"timeout": 1}}
        # Explicit guard: enabled must not leak into the resolver dict.
        assert "enabled" not in result["shell"]

    async def test_pydantic_coerces_int_to_bool_for_enabled(self) -> None:
        # Insurance for any future code path that builds ToolConfig
        # from a raw row tuple instead of an aiosqlite.Row.
        from the_one.db.models import ToolConfig

        m = ToolConfig(name="x", enabled=1)
        assert m.enabled is True
