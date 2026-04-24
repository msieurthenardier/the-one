"""Tests for schema migrations (v1 -> v2 -> v3)."""

from __future__ import annotations

import aiosqlite
import pytest

from the_one.db.schema import ensure_schema

# The original V1 DDL before the provider migration, used to simulate
# pre-migration databases in v2→v3 tests.
_LEGACY_SCHEMA_V1 = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agents (
    name TEXT PRIMARY KEY,
    description TEXT DEFAULT '',
    llm_provider TEXT DEFAULT 'ollama',
    llm_model TEXT DEFAULT 'qwen2.5:7b',
    llm_base_url TEXT,
    system_prompt TEXT DEFAULT '',
    enabled_tools TEXT,
    disabled_tools TEXT DEFAULT '[]',
    max_iterations INTEGER DEFAULT 20,
    kb_ids TEXT DEFAULT '[]',
    mcp_source_ids TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS kb_items (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    parent_id TEXT REFERENCES kb_items(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('file', 'url')),
    path_or_url TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mcp_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('stdio', 'sse')),
    config TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL REFERENCES agents(name) ON DELETE CASCADE,
    title TEXT DEFAULT 'New chat',
    messages TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@pytest.fixture
async def fresh_db():
    """Return an in-memory connection with no schema applied."""
    conn = await aiosqlite.connect(":memory:")
    yield conn
    await conn.close()


@pytest.fixture
async def v2_db():
    """Return an in-memory connection at schema version 2."""
    conn = await aiosqlite.connect(":memory:")
    # Apply legacy V1 (with llm_provider/llm_base_url columns)
    await conn.executescript(_LEGACY_SCHEMA_V1)
    await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (1,))
    await conn.commit()

    # Apply V2 (rebuild chat_sessions to make agent_name nullable)
    await conn.executescript("""\
CREATE TABLE IF NOT EXISTS chat_sessions_new (
    id TEXT PRIMARY KEY,
    agent_name TEXT REFERENCES agents(name) ON DELETE CASCADE,
    title TEXT DEFAULT 'New chat',
    messages TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO chat_sessions_new (id, agent_name, title, messages, created_at, updated_at)
    SELECT id, agent_name, title, messages, created_at, updated_at FROM chat_sessions;

DROP TABLE chat_sessions;

ALTER TABLE chat_sessions_new RENAME TO chat_sessions;

CREATE INDEX idx_chat_sessions_agent ON chat_sessions(agent_name);
""")
    await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (2,))
    await conn.commit()

    yield conn
    await conn.close()


async def _get_columns(conn: aiosqlite.Connection, table: str) -> list[str]:
    """Return column names for a table."""
    async with conn.execute(f"PRAGMA table_info({table})") as cur:
        rows = await cur.fetchall()
    return [r[1] for r in rows]


async def _table_exists(conn: aiosqlite.Connection, table: str) -> bool:
    """Check if a table exists."""
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ) as cur:
        return await cur.fetchone() is not None


# ── Fresh database tests ──


@pytest.mark.asyncio
async def test_fresh_db_creates_all_tables(fresh_db):
    """ensure_schema on empty DB creates all tables including llm_providers."""
    await ensure_schema(fresh_db)

    for table in ("agents", "llm_providers", "chat_sessions", "knowledge_bases"):
        assert await _table_exists(fresh_db, table), f"{table} should exist"


@pytest.mark.asyncio
async def test_fresh_db_schema_version_is_3(fresh_db):
    """After full migration, schema version should be 3."""
    await ensure_schema(fresh_db)

    async with fresh_db.execute("SELECT MAX(version) FROM schema_version") as cur:
        row = await cur.fetchone()
    assert row[0] == 3


@pytest.mark.asyncio
async def test_fresh_db_agents_has_provider_config_id(fresh_db):
    """Fresh DB agents table should have provider_config_id after v3 migration."""
    await ensure_schema(fresh_db)
    cols = await _get_columns(fresh_db, "agents")
    assert "provider_config_id" in cols


@pytest.mark.asyncio
async def test_fresh_db_agents_no_llm_provider_or_base_url(fresh_db):
    """Fresh DB agents table should NOT have llm_provider or llm_base_url after v3."""
    await ensure_schema(fresh_db)
    cols = await _get_columns(fresh_db, "agents")
    assert "llm_provider" not in cols
    assert "llm_base_url" not in cols


# ── v2 -> v3 migration tests ──


@pytest.mark.asyncio
async def test_v2_to_v3_creates_llm_providers(v2_db):
    """v3 migration creates llm_providers table."""
    await ensure_schema(v2_db)
    assert await _table_exists(v2_db, "llm_providers")


@pytest.mark.asyncio
async def test_v2_to_v3_agents_has_provider_config_id(v2_db):
    """v3 migration adds provider_config_id to agents."""
    await ensure_schema(v2_db)
    cols = await _get_columns(v2_db, "agents")
    assert "provider_config_id" in cols


@pytest.mark.asyncio
async def test_v2_to_v3_agents_drops_old_columns(v2_db):
    """v3 migration removes llm_provider and llm_base_url from agents."""
    # Verify they exist before migration
    cols_before = await _get_columns(v2_db, "agents")
    assert "llm_provider" in cols_before
    assert "llm_base_url" in cols_before

    await ensure_schema(v2_db)

    cols_after = await _get_columns(v2_db, "agents")
    assert "llm_provider" not in cols_after
    assert "llm_base_url" not in cols_after


@pytest.mark.asyncio
async def test_v2_to_v3_preserves_agent_data(v2_db):
    """Existing agent data is preserved through the v3 rebuild."""
    # Insert a test agent at v2
    await v2_db.execute(
        "INSERT INTO agents (name, description, llm_model, system_prompt) VALUES (?, ?, ?, ?)",
        ("test-agent", "A test agent", "gpt-4", "You are helpful."),
    )
    await v2_db.commit()

    await ensure_schema(v2_db)

    async with v2_db.execute(
        "SELECT name, description, llm_model, system_prompt, provider_config_id "
        "FROM agents WHERE name = ?",
        ("test-agent",),
    ) as cur:
        row = await cur.fetchone()

    assert row is not None
    assert row[0] == "test-agent"
    assert row[1] == "A test agent"
    assert row[2] == "gpt-4"
    assert row[3] == "You are helpful."
    assert row[4] is None  # provider_config_id is NULL for migrated rows


@pytest.mark.asyncio
async def test_v2_to_v3_chat_sessions_survive(v2_db):
    """Chat sessions referencing agents survive the v3 migration."""
    # Insert an agent and a chat session at v2
    await v2_db.execute(
        "INSERT INTO agents (name, description) VALUES (?, ?)",
        ("my-agent", "desc"),
    )
    await v2_db.execute(
        "INSERT INTO chat_sessions (id, agent_name, title) VALUES (?, ?, ?)",
        ("sess-001", "my-agent", "Hello"),
    )
    await v2_db.commit()

    # Verify chat session exists before migration
    async with v2_db.execute("SELECT COUNT(*) FROM chat_sessions") as cur:
        count_before = (await cur.fetchone())[0]
    assert count_before == 1

    await ensure_schema(v2_db)

    # Verify chat session still exists after migration
    async with v2_db.execute(
        "SELECT id, agent_name, title FROM chat_sessions WHERE id = ?",
        ("sess-001",),
    ) as cur:
        row = await cur.fetchone()

    assert row is not None
    assert row[0] == "sess-001"
    assert row[1] == "my-agent"
    assert row[2] == "Hello"


@pytest.mark.asyncio
async def test_v2_to_v3_empty_agents_table(v2_db):
    """Migration works with an empty agents table."""
    await ensure_schema(v2_db)

    async with v2_db.execute("SELECT COUNT(*) FROM agents") as cur:
        count = (await cur.fetchone())[0]
    assert count == 0


@pytest.mark.asyncio
async def test_v2_to_v3_multiple_agents_preserved(v2_db):
    """Multiple agents are all preserved through migration."""
    for i in range(3):
        await v2_db.execute(
            "INSERT INTO agents (name, description) VALUES (?, ?)",
            (f"agent-{i}", f"desc-{i}"),
        )
    await v2_db.commit()

    await ensure_schema(v2_db)

    async with v2_db.execute("SELECT COUNT(*) FROM agents") as cur:
        count = (await cur.fetchone())[0]
    assert count == 3


@pytest.mark.asyncio
async def test_llm_providers_type_check_constraint(fresh_db):
    """llm_providers table enforces CHECK constraint on type column."""
    await ensure_schema(fresh_db)

    with pytest.raises(aiosqlite.IntegrityError):
        await fresh_db.execute(
            "INSERT INTO llm_providers (id, name, type, base_url) VALUES (?, ?, ?, ?)",
            ("p1", "bad", "invalid-type", "http://localhost"),
        )


@pytest.mark.asyncio
async def test_idempotent_ensure_schema(fresh_db):
    """Calling ensure_schema twice is safe (idempotent)."""
    await ensure_schema(fresh_db)
    await ensure_schema(fresh_db)

    async with fresh_db.execute("SELECT MAX(version) FROM schema_version") as cur:
        row = await cur.fetchone()
    assert row[0] == 3
