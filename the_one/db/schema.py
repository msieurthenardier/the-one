"""DDL definitions and schema versioning."""

from __future__ import annotations

import aiosqlite

CURRENT_VERSION = 6

SCHEMA_V1 = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS llm_providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('ollama', 'openai-compatible', 'openai', 'anthropic')),
    base_url TEXT NOT NULL,
    api_key TEXT,
    config TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agents (
    name TEXT PRIMARY KEY,
    description TEXT DEFAULT '',
    provider_config_id TEXT REFERENCES llm_providers(id) ON DELETE SET NULL,
    llm_model TEXT DEFAULT '',
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


async def _get_version(conn: aiosqlite.Connection) -> int:
    """Return current schema version, or 0 if no version table exists."""
    try:
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0
    except aiosqlite.OperationalError:
        return 0


async def ensure_schema(conn: aiosqlite.Connection) -> None:
    """Apply schema migrations up to CURRENT_VERSION."""
    version = await _get_version(conn)

    if version < 1:
        await conn.executescript(SCHEMA_V1)
        await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (1,))
        await conn.commit()
        version = 1

    if version < 2:
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

    if version < 3:
        await conn.executescript("""\
PRAGMA foreign_keys=OFF;

CREATE TABLE IF NOT EXISTS llm_providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('ollama', 'openai-compatible', 'openai', 'anthropic')),
    base_url TEXT NOT NULL,
    api_key TEXT,
    config TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agents_new (
    name TEXT PRIMARY KEY,
    description TEXT DEFAULT '',
    provider_config_id TEXT REFERENCES llm_providers(id) ON DELETE SET NULL,
    llm_model TEXT DEFAULT '',
    system_prompt TEXT DEFAULT '',
    enabled_tools TEXT,
    disabled_tools TEXT DEFAULT '[]',
    max_iterations INTEGER DEFAULT 20,
    kb_ids TEXT DEFAULT '[]',
    mcp_source_ids TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO agents_new (name, description, llm_model, system_prompt,
    enabled_tools, disabled_tools, max_iterations, kb_ids, mcp_source_ids,
    created_at, updated_at)
    SELECT name, description, llm_model, system_prompt,
    enabled_tools, disabled_tools, max_iterations, kb_ids, mcp_source_ids,
    created_at, updated_at FROM agents;

DROP TABLE agents;

ALTER TABLE agents_new RENAME TO agents;

PRAGMA foreign_keys=ON;
""")
        await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (3,))
        await conn.commit()
        version = 3

    if version < 4:
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agents_provider ON agents(provider_config_id)"
        )
        await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (4,))
        await conn.commit()
        version = 4

    if version < 5:
        # Drop the FK constraint on chat_sessions.agent_name so deleting an
        # agent does NOT cascade to its sessions. The column stays as TEXT
        # and retains the deleted agent's name as a free-text value, which
        # lets the session-health classifier surface `agent_deleted` to the
        # user (see Leg 02 design decision: sessions must survive agent
        # deletion so users can see actionable guidance, not silent loss).
        # SQLite has no `ALTER TABLE DROP CONSTRAINT`, so rebuild the table
        # following the same pattern as the v3 agents-table rebuild above.
        await conn.executescript("""\
PRAGMA foreign_keys=OFF;

CREATE TABLE chat_sessions_new (
    id TEXT PRIMARY KEY,
    agent_name TEXT,
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

PRAGMA foreign_keys=ON;
""")
        await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (5,))
        await conn.commit()
        version = 5

    if version < 6:
        # Extend llm_providers.type CHECK constraint to allow 'mock' (added
        # for the dev-mode mock LLM provider). SQLite has no `ALTER TABLE
        # DROP CONSTRAINT`, so rebuild the table following the v3 pattern.
        # Agents reference llm_providers via a FK; disable FK enforcement
        # during the rebuild so the rename doesn't break referential checks
        # (the FK is restored on the renamed table by SQLite automatically).
        await conn.executescript("""\
PRAGMA foreign_keys=OFF;

CREATE TABLE llm_providers_new (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (
        type IN ('ollama', 'openai-compatible', 'openai', 'anthropic', 'mock')
    ),
    base_url TEXT NOT NULL,
    api_key TEXT,
    config TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO llm_providers_new (id, name, type, base_url, api_key, config, created_at, updated_at)
    SELECT id, name, type, base_url, api_key, config, created_at, updated_at FROM llm_providers;

DROP TABLE llm_providers;

ALTER TABLE llm_providers_new RENAME TO llm_providers;

PRAGMA foreign_keys=ON;
""")
        await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (6,))
        await conn.commit()
        version = 6
