"""Tests for all database repositories."""

from __future__ import annotations

import pytest

from the_one.agent.config import AgentConfig
from the_one.db.models import ChatSession, ConnectorAccount, KBItem, KnowledgeBase, MCPSource
from the_one.db.repositories import (
    ChatSessionRepository,
    ConnectorAccountRepository,
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
def mcp_repo_encryptor(tmp_path):
    # Function-scoped (default). Do NOT promote to module/session scope —
    # would outlive the per-test `conn` fixture and create cross-test
    # state leakage on the encryptor's in-memory key.
    from cryptography.fernet import Fernet

    from the_one.encryption import Encryptor

    key = Fernet.generate_key()
    return Encryptor(key, key_path=tmp_path / "mcp.key")


@pytest.fixture
def mcp_repo(conn, mcp_repo_encryptor):
    return MCPSourceRepository(conn, mcp_repo_encryptor)


@pytest.fixture
def connector_repo_encryptor(tmp_path):
    # Function-scoped (default). Do NOT promote to module/session scope —
    # would outlive the per-test `conn` fixture and create cross-test
    # state leakage on the encryptor's in-memory key.
    from cryptography.fernet import Fernet

    from the_one.encryption import Encryptor

    key = Fernet.generate_key()
    return Encryptor(key, key_path=tmp_path / "connector.key")


@pytest.fixture
def connector_repo(conn, connector_repo_encryptor):
    return ConnectorAccountRepository(conn, connector_repo_encryptor)


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

    async def test_mcp_overrides_round_trip(self, agent_store: SQLiteAgentStore) -> None:
        """Saving an agent with `mcp_overrides` set roundtrips through
        the SQLite store cleanly (F6 §1: dict[str, dict[str, Any]] keyed
        by source name)."""
        cfg = AgentConfig(
            name="mcp-override-test",
            mcp_overrides={
                "github": {"bearer_token": "tok-a"},
                "filesystem": {"env": {"ROOT": "/srv"}},
            },
        )
        await agent_store.save(cfg)
        loaded = await agent_store.load("mcp-override-test")
        assert loaded.mcp_overrides == {
            "github": {"bearer_token": "tok-a"},
            "filesystem": {"env": {"ROOT": "/srv"}},
        }

    async def test_mcp_overrides_none_default(self, agent_store: SQLiteAgentStore) -> None:
        """An agent without `mcp_overrides` set roundtrips as None
        (locked-down NULL semantic, mirrors tool_overrides)."""
        cfg = AgentConfig(name="no-mcp-overrides")
        await agent_store.save(cfg)
        loaded = await agent_store.load("no-mcp-overrides")
        assert loaded.mcp_overrides is None


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
        await mcp_repo.create(MCPSource(id="b", name="Bravo", type="streamable-http"))
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
        await mcp_repo.create(MCPSource(id="s1", name="Doomed", type="streamable-http"))
        await mcp_repo.delete("s1")
        with pytest.raises(KeyError):
            await mcp_repo.get("s1")

    async def test_secrets_round_trip(self, mcp_repo: MCPSourceRepository) -> None:
        """secrets dict round-trips through the encryption envelope."""
        source = MCPSource(
            id="s1",
            name="GitHub MCP",
            type="stdio",
            config={"command": "github-mcp"},
            secrets={"GITHUB_TOKEN": "ghp_secret_value_123"},
        )
        await mcp_repo.create(source)
        fetched = await mcp_repo.get("s1")
        assert fetched.config == {"command": "github-mcp"}
        assert fetched.secrets == {"GITHUB_TOKEN": "ghp_secret_value_123"}

    async def test_secrets_encrypted_at_rest(self, mcp_repo: MCPSourceRepository) -> None:
        """Raw DB read of the secrets column yields a ciphertext, NOT plaintext JSON."""
        import json

        source = MCPSource(
            id="s1",
            name="Test",
            type="stdio",
            secrets={"TOKEN": "super-secret-value"},
        )
        await mcp_repo.create(source)
        async with mcp_repo.conn.execute(
            "SELECT secrets FROM mcp_sources WHERE id = ?", ("s1",)
        ) as cur:
            row = await cur.fetchone()
        raw = row["secrets"]
        assert raw is not None
        assert "super-secret-value" not in raw
        assert "TOKEN" not in raw
        # Fernet ciphertext is base64; sanity-check it decrypts back via the
        # repo's encryptor.
        decrypted = mcp_repo.encryptor.decrypt(raw)
        assert json.loads(decrypted) == {"TOKEN": "super-secret-value"}

    async def test_empty_secrets_default(self, mcp_repo: MCPSourceRepository) -> None:
        """A source created without secrets= round-trips with secrets={}."""
        source = MCPSource(id="s1", name="Test", type="stdio", config={"x": 1})
        await mcp_repo.create(source)
        fetched = await mcp_repo.get("s1")
        assert fetched.secrets == {}

    async def test_install_key_post_create_decrypts_via_same_instance(
        self, mcp_repo: MCPSourceRepository
    ) -> None:
        """Post install_key, the same repo instance decrypts new writes.

        Locks the reference-not-copy invariant: install_key() mutates the
        Encryptor in place; the repository's stored reference sees the
        mutation. Re-creates a row after the key swap and round-trips.
        """
        from cryptography.fernet import Fernet

        new_key = Fernet.generate_key()
        mcp_repo.encryptor.install_key(new_key)

        source = MCPSource(
            id="s1",
            name="PostKey",
            type="stdio",
            secrets={"K": "value-after-rotation"},
        )
        await mcp_repo.create(source)
        fetched = await mcp_repo.get("s1")
        assert fetched.secrets == {"K": "value-after-rotation"}

    def test_merged_config_overlays_secrets_on_config(self) -> None:
        """secrets win on key collision; non-overlapping keys merge."""
        source = MCPSource(
            id="s1",
            name="T",
            type="stdio",
            config={"command": "x", "TOKEN": "plaintext-default"},
            secrets={"TOKEN": "encrypted-real"},
        )
        merged = source.merged_config()
        assert merged == {"command": "x", "TOKEN": "encrypted-real"}


# ── Connector Account Repository ─────────────────────────────────────────


class TestConnectorAccountRepository:
    """CRUD coverage for ConnectorAccountRepository.

    Mission 10 flight 01 leg 02 — sibling to ``TestMCPSourceRepository``,
    minus the ``merged_config`` test (the helper is deferred to flight 06
    per flight Design Decisions). The encryption envelope assertions and
    reference-not-copy invariant are exercised identically.
    """

    async def test_create_and_get(
        self, connector_repo: ConnectorAccountRepository
    ) -> None:
        account = ConnectorAccount(
            id="a1", name="Test Bot", type="stub", config={"intent": "guild_messages"}
        )
        await connector_repo.create(account)
        loaded = await connector_repo.get("a1")
        assert loaded.name == "Test Bot"
        assert loaded.config == {"intent": "guild_messages"}

    async def test_list(self, connector_repo: ConnectorAccountRepository) -> None:
        await connector_repo.create(
            ConnectorAccount(id="b", name="Bravo Bot", type="stub")
        )
        await connector_repo.create(
            ConnectorAccount(id="a", name="Alpha Bot", type="stub")
        )
        accounts = await connector_repo.list()
        assert [a.name for a in accounts] == ["Alpha Bot", "Bravo Bot"]

    async def test_update(self, connector_repo: ConnectorAccountRepository) -> None:
        await connector_repo.create(
            ConnectorAccount(id="a1", name="Old Name", type="stub")
        )
        account = await connector_repo.get("a1")
        account.name = "New Name"
        await connector_repo.update(account)
        loaded = await connector_repo.get("a1")
        assert loaded.name == "New Name"

    async def test_delete(self, connector_repo: ConnectorAccountRepository) -> None:
        await connector_repo.create(
            ConnectorAccount(id="a1", name="Doomed", type="stub")
        )
        await connector_repo.delete("a1")
        with pytest.raises(KeyError):
            await connector_repo.get("a1")

    async def test_secrets_round_trip(
        self, connector_repo: ConnectorAccountRepository
    ) -> None:
        """secrets dict round-trips through the encryption envelope."""
        account = ConnectorAccount(
            id="a1",
            name="Discord Bot",
            type="stub",
            config={"intent": "guild_messages"},
            secrets={"BOT_TOKEN": "discord_secret_value_xyz"},
        )
        await connector_repo.create(account)
        fetched = await connector_repo.get("a1")
        assert fetched.config == {"intent": "guild_messages"}
        assert fetched.secrets == {"BOT_TOKEN": "discord_secret_value_xyz"}

    async def test_secrets_encrypted_at_rest(
        self, connector_repo: ConnectorAccountRepository
    ) -> None:
        """Raw DB read of the secrets column yields ciphertext, NOT plaintext JSON."""
        import json

        account = ConnectorAccount(
            id="a1",
            name="Test",
            type="stub",
            secrets={"TOKEN": "super-secret-value"},
        )
        await connector_repo.create(account)
        async with connector_repo.conn.execute(
            "SELECT secrets FROM connector_accounts WHERE id = ?", ("a1",)
        ) as cur:
            row = await cur.fetchone()
        raw = row["secrets"]
        assert raw is not None
        assert "super-secret-value" not in raw
        assert "TOKEN" not in raw
        # Fernet ciphertext is base64; sanity-check it decrypts back via the
        # repo's encryptor.
        decrypted = connector_repo.encryptor.decrypt(raw)
        assert json.loads(decrypted) == {"TOKEN": "super-secret-value"}

    async def test_empty_secrets_default(
        self, connector_repo: ConnectorAccountRepository
    ) -> None:
        """An account created without secrets= round-trips with secrets={}."""
        account = ConnectorAccount(id="a1", name="Test", type="stub", config={"x": 1})
        await connector_repo.create(account)
        fetched = await connector_repo.get("a1")
        assert fetched.secrets == {}

    async def test_install_key_post_create_decrypts_via_same_instance(
        self, connector_repo: ConnectorAccountRepository
    ) -> None:
        """Post install_key, the same repo instance decrypts new writes.

        Locks the reference-not-copy invariant: install_key() mutates the
        Encryptor in place; the repository's stored reference sees the
        mutation. Re-creates a row after the key swap and round-trips.
        """
        from cryptography.fernet import Fernet

        new_key = Fernet.generate_key()
        connector_repo.encryptor.install_key(new_key)

        account = ConnectorAccount(
            id="a1",
            name="PostKey",
            type="stub",
            secrets={"K": "value-after-rotation"},
        )
        await connector_repo.create(account)
        fetched = await connector_repo.get("a1")
        assert fetched.secrets == {"K": "value-after-rotation"}

    async def test_idle_timeout_seconds_round_trips_real_value(
        self, connector_repo: ConnectorAccountRepository
    ) -> None:
        """A real ``idle_timeout_seconds`` value round-trips through
        create → get → update → get.

        Mission 10 flight 02 leg 02: the per-account override surface.
        """
        account = ConnectorAccount(
            id="a1",
            name="TTL Bot",
            type="stub",
            idle_timeout_seconds=600,
        )
        await connector_repo.create(account)
        loaded = await connector_repo.get("a1")
        assert loaded.idle_timeout_seconds == 600

        loaded.idle_timeout_seconds = 60
        await connector_repo.update(loaded)
        reloaded = await connector_repo.get("a1")
        assert reloaded.idle_timeout_seconds == 60

    async def test_idle_timeout_seconds_round_trips_none(
        self, connector_repo: ConnectorAccountRepository
    ) -> None:
        """An account created without ``idle_timeout_seconds`` round-trips
        as ``None`` (the default — fall through to env-var / default in
        ``_resolve_ttl_seconds``) and survives a no-op update.
        """
        account = ConnectorAccount(id="a1", name="No TTL", type="stub")
        await connector_repo.create(account)
        fetched = await connector_repo.get("a1")
        assert fetched.idle_timeout_seconds is None

        # No-op update preserves None.
        await connector_repo.update(fetched)
        refetched = await connector_repo.get("a1")
        assert refetched.idle_timeout_seconds is None

    async def test_idle_timeout_seconds_validator_rejects_zero(self) -> None:
        """Validator rejects 0 (would make warm entries immediately reapable)."""
        import pytest

        with pytest.raises(ValueError) as exc_info:
            ConnectorAccount(id="a", name="x", type="stub", idle_timeout_seconds=0)
        assert "between 1 and 604800" in str(exc_info.value)

    async def test_idle_timeout_seconds_validator_rejects_one_week_plus_one(
        self,
    ) -> None:
        """Validator rejects 604801 (catches the ms-vs-s typo)."""
        import pytest

        with pytest.raises(ValueError) as exc_info:
            ConnectorAccount(
                id="a", name="x", type="stub", idle_timeout_seconds=604801
            )
        assert "between 1 and 604800" in str(exc_info.value)

    async def test_idle_timeout_seconds_validator_accepts_bounds(self) -> None:
        """Validator accepts 1, 604800, and None (the default)."""
        # Lower bound: 1.
        a1 = ConnectorAccount(id="a", name="x", type="stub", idle_timeout_seconds=1)
        assert a1.idle_timeout_seconds == 1
        # Upper bound: 604800 (7 days).
        a2 = ConnectorAccount(
            id="b", name="x", type="stub", idle_timeout_seconds=604800
        )
        assert a2.idle_timeout_seconds == 604800
        # None — default; accepted, falls through to env-var / default.
        a3 = ConnectorAccount(
            id="c", name="x", type="stub", idle_timeout_seconds=None
        )
        assert a3.idle_timeout_seconds is None


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

    # ── M10 F03 L01: connector-keyed session round-trip ──────────────────

    async def test_create_and_get_with_connector_identity(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Mission 10 Flight 3 Leg 1: ChatSession with all seven connector-
        identity columns set round-trips through create → get byte-
        identically (including the JSON-encoded session_metadata dict).
        """
        await agent_store.save(AgentConfig(name="agent1"))
        session = ChatSession(
            id="s-conn",
            agent_name="agent1",
            title="Discord #engineering",
            platform="discord",
            connector_account_id="acc-1",
            channel_id="ch-1",
            thread_id=None,
            peer_id="peer-1",
            session_metadata={"routing": "default"},
            last_inbound_at="2026-05-17T00:00:00+00:00",
        )
        await chat_repo.create(session)
        loaded = await chat_repo.get("s-conn")
        assert loaded.platform == "discord"
        assert loaded.connector_account_id == "acc-1"
        assert loaded.channel_id == "ch-1"
        assert loaded.thread_id is None
        assert loaded.peer_id == "peer-1"
        assert loaded.session_metadata == {"routing": "default"}
        assert loaded.last_inbound_at == "2026-05-17T00:00:00+00:00"

    async def test_round_trip_session_metadata_dict_and_none(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """All seven new fields default to None for non-connector sessions
        (back-compat); an empty dict round-trips as {} (distinct from NULL).
        """
        await agent_store.save(AgentConfig(name="agent1"))
        # Default — all seven new fields are None.
        plain = ChatSession(id="s-plain", agent_name="agent1", title="Plain")
        await chat_repo.create(plain)
        loaded_plain = await chat_repo.get("s-plain")
        assert loaded_plain.platform is None
        assert loaded_plain.connector_account_id is None
        assert loaded_plain.channel_id is None
        assert loaded_plain.thread_id is None
        assert loaded_plain.peer_id is None
        assert loaded_plain.session_metadata is None
        assert loaded_plain.last_inbound_at is None

        # Empty-dict metadata round-trips as {} (NOT collapsed to None).
        empty_meta = ChatSession(
            id="s-empty-meta",
            agent_name="agent1",
            title="EmptyMeta",
            platform="discord",
            connector_account_id="acc-1",
            channel_id="ch-1",
            session_metadata={},
        )
        await chat_repo.create(empty_meta)
        loaded_empty = await chat_repo.get("s-empty-meta")
        assert loaded_empty.session_metadata == {}

    async def test_round_trip_session_metadata_corrupt_non_dict_collapses_to_none(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Defensive normalization on `_row_to_model`: a non-dict JSON value
        (corruption / external tampering) decodes as `session_metadata=None`
        rather than raising — the model annotation requires dict; silently
        degrading is safer than raising in the read path. F7 is the only
        intended writer and only writes dicts.
        """
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(
            ChatSession(
                id="s-corrupt",
                agent_name="agent1",
                title="Corrupt",
                platform="discord",
                connector_account_id="acc-1",
                channel_id="ch-1",
            )
        )
        # Hand-tamper the column with a JSON literal string (not a dict).
        await chat_repo.conn.execute(
            "UPDATE chat_sessions SET session_metadata = ? WHERE id = ?",
            ('"hello"', "s-corrupt"),
        )
        await chat_repo.conn.commit()

        loaded = await chat_repo.get("s-corrupt")
        assert loaded.session_metadata is None

    # ── M10 F03 L03: find_most_recent_by_external_key ────────────────────

    async def test_find_most_recent_by_external_key_returns_none_on_no_match(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """No matching row → returns None (resolver treats as first contact)."""
        await agent_store.save(AgentConfig(name="agent1"))
        result = await chat_repo.find_most_recent_by_external_key(
            platform="discord",
            connector_account_id="acc-1",
            channel_id="ch-1",
            thread_id=None,
        )
        assert result is None

    async def test_find_most_recent_by_external_key_returns_most_recent_by_updated_at(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Three rows for the same external key with different ``updated_at`` —
        the most recent is returned (ORDER BY updated_at DESC LIMIT 1)."""
        await agent_store.save(AgentConfig(name="agent1"))
        for ix, ts in enumerate(
            [
                "2026-05-01T00:00:00+00:00",
                "2026-05-02T00:00:00+00:00",
                "2026-05-03T00:00:00+00:00",
            ]
        ):
            await chat_repo.create(
                ChatSession(
                    id=f"s-{ix}",
                    agent_name="agent1",
                    title=f"row-{ix}",
                    platform="discord",
                    connector_account_id="acc-1",
                    channel_id="ch-1",
                    thread_id=None,
                    created_at=ts,
                    updated_at=ts,
                    last_inbound_at=ts,
                )
            )
        result = await chat_repo.find_most_recent_by_external_key(
            platform="discord",
            connector_account_id="acc-1",
            channel_id="ch-1",
            thread_id=None,
        )
        assert result is not None
        assert result.id == "s-2"
        assert result.title == "row-2"

    async def test_find_most_recent_by_external_key_coalesce_null_thread_id(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """COALESCE handling: a row with ``thread_id=NULL`` matches a query
        with ``thread_id=None``; a row with ``thread_id="A"`` does NOT match
        a query with ``thread_id=None``."""
        await agent_store.save(AgentConfig(name="agent1"))
        # Row with NULL thread_id.
        await chat_repo.create(
            ChatSession(
                id="s-null-thread",
                agent_name="agent1",
                platform="discord",
                connector_account_id="acc-1",
                channel_id="ch-1",
                thread_id=None,
                created_at="2026-05-01T00:00:00+00:00",
                updated_at="2026-05-01T00:00:00+00:00",
            )
        )
        # Row with thread_id="A".
        await chat_repo.create(
            ChatSession(
                id="s-thread-A",
                agent_name="agent1",
                platform="discord",
                connector_account_id="acc-1",
                channel_id="ch-1",
                thread_id="A",
                created_at="2026-05-02T00:00:00+00:00",
                updated_at="2026-05-02T00:00:00+00:00",
            )
        )

        # Query with thread_id=None matches the NULL row, NOT the "A" row.
        result_none = await chat_repo.find_most_recent_by_external_key(
            platform="discord",
            connector_account_id="acc-1",
            channel_id="ch-1",
            thread_id=None,
        )
        assert result_none is not None
        assert result_none.id == "s-null-thread"

        # Query with thread_id="A" matches the "A" row, NOT the NULL row.
        result_a = await chat_repo.find_most_recent_by_external_key(
            platform="discord",
            connector_account_id="acc-1",
            channel_id="ch-1",
            thread_id="A",
        )
        assert result_a is not None
        assert result_a.id == "s-thread-A"


# ── M10 F03 L01: ConnectorAccount session_continuation_seconds ───────────


class TestConnectorAccountSessionContinuation:
    """Round-trip + validator coverage for the M10 F03 L01 field
    ``session_continuation_seconds`` on ``ConnectorAccount``.

    Sibling to ``TestConnectorAccountRepository`` 's
    ``idle_timeout_seconds`` tests; same shape, distinct concern (chat-
    session continuation window vs. pool warm-entry TTL).
    """

    async def test_session_continuation_seconds_round_trips_real_value(
        self, connector_repo: ConnectorAccountRepository
    ) -> None:
        """A real ``session_continuation_seconds`` value round-trips
        through create → get → update → get."""
        account = ConnectorAccount(
            id="a1",
            name="Continuation Bot",
            type="stub",
            session_continuation_seconds=86400,
        )
        await connector_repo.create(account)
        loaded = await connector_repo.get("a1")
        assert loaded.session_continuation_seconds == 86400

        loaded.session_continuation_seconds = 3600
        await connector_repo.update(loaded)
        reloaded = await connector_repo.get("a1")
        assert reloaded.session_continuation_seconds == 3600

    async def test_session_continuation_seconds_round_trips_none(
        self, connector_repo: ConnectorAccountRepository
    ) -> None:
        """An account created without ``session_continuation_seconds`` round-
        trips as ``None`` (the default — fall through to resolver default)
        and survives a no-op update."""
        account = ConnectorAccount(id="a1", name="No Continuation", type="stub")
        await connector_repo.create(account)
        fetched = await connector_repo.get("a1")
        assert fetched.session_continuation_seconds is None

        await connector_repo.update(fetched)
        refetched = await connector_repo.get("a1")
        assert refetched.session_continuation_seconds is None

    async def test_session_continuation_seconds_validator_rejects_zero(self) -> None:
        """Validator rejects 0 (would zero-out the continuation window)."""
        with pytest.raises(ValueError) as exc_info:
            ConnectorAccount(
                id="a", name="x", type="stub", session_continuation_seconds=0
            )
        assert "between 1 and 604800" in str(exc_info.value)

    async def test_session_continuation_seconds_validator_rejects_one_week_plus_one(
        self,
    ) -> None:
        """Validator rejects 604801 (catches the ms-vs-s typo)."""
        with pytest.raises(ValueError) as exc_info:
            ConnectorAccount(
                id="a", name="x", type="stub", session_continuation_seconds=604801
            )
        assert "between 1 and 604800" in str(exc_info.value)

    async def test_session_continuation_seconds_validator_accepts_bounds(
        self,
    ) -> None:
        """Validator accepts 1, 86400 (24h default), 604800 (7-day cap),
        and None (the default)."""
        a1 = ConnectorAccount(
            id="a", name="x", type="stub", session_continuation_seconds=1
        )
        assert a1.session_continuation_seconds == 1
        a2 = ConnectorAccount(
            id="b", name="x", type="stub", session_continuation_seconds=86400
        )
        assert a2.session_continuation_seconds == 86400
        a3 = ConnectorAccount(
            id="c", name="x", type="stub", session_continuation_seconds=604800
        )
        assert a3.session_continuation_seconds == 604800
        a4 = ConnectorAccount(
            id="d", name="x", type="stub", session_continuation_seconds=None
        )
        assert a4.session_continuation_seconds is None


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
