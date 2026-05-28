"""DDL definitions and schema versioning."""

from __future__ import annotations

import json

import aiosqlite

from the_one.db._connector_types import CONNECTOR_TYPES
from the_one.db._provider_types import PROVIDER_TYPES

CURRENT_VERSION = 22

# Render the provider-type CHECK constraint as a comma-separated SQL
# literal list, sourced from PROVIDER_TYPES. Both SCHEMA_V1 (fresh-DB
# path) and the v10 migration (existing-DB path) inject this so a future
# addition only needs to touch ``_provider_types.py``.
_PROVIDER_TYPES_SQL = ", ".join(f"'{t}'" for t in PROVIDER_TYPES)

# Build comma-separated quoted SQL literal list, sourced from
# CONNECTOR_TYPES. The v19 CHECK constraint (added by F8 L2's
# table-rename ceremony on ``connector_accounts.type``) references this;
# future connector types added to the tuple flow automatically into the
# constraint via the next CHECK-changing migration.
_CONNECTOR_TYPES_SQL = ", ".join(f"'{t}'" for t in CONNECTOR_TYPES)

SCHEMA_V1 = f"""\
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS llm_providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ({_PROVIDER_TYPES_SQL})),
    base_url TEXT NOT NULL,
    api_key TEXT,
    config TEXT DEFAULT '{{}}',
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
    config TEXT DEFAULT '{{}}',
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

    if version < 7:
        # Strip the seven removed self-modification tool names from every
        # agent's enabled_tools / disabled_tools JSON columns. The names
        # were valid in v6 but reference tools deleted in mission 5
        # flight 1. enabled_tools=NULL means "whitelist disabled, all
        # tools allowed" — preserve NULL as NULL; never coerce to [].
        # An empty whitelist after strip is the correct (locked-down)
        # interpretation: the operator wanted only a removed tool, so
        # widening their scope back to all-tools would be a silent
        # privilege escalation.
        removed = {
            "self_deploy",
            "rollback",
            "restart",
            "run_tests",
            "git",
            "memory",
            "mission_control",
        }
        async with conn.execute("SELECT name, enabled_tools, disabled_tools FROM agents") as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            name = row[0]
            enabled_json = row[1]
            disabled_json = row[2]
            enabled = json.loads(enabled_json) if enabled_json else None
            disabled = json.loads(disabled_json or "[]")
            new_enabled = [t for t in enabled if t not in removed] if enabled is not None else None
            new_disabled = [t for t in disabled if t not in removed]
            await conn.execute(
                "UPDATE agents SET enabled_tools = ?, disabled_tools = ? WHERE name = ?",
                (
                    json.dumps(new_enabled) if new_enabled is not None else None,
                    json.dumps(new_disabled),
                    name,
                ),
            )
        await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (7,))
        await conn.commit()
        version = 7

    if version < 8:
        # Tool-level config table (mirrors mcp_sources shape) plus a new
        # nullable `tool_overrides` JSON column on `agents` for per-agent
        # narrowing / substitution overrides. Both surfaces are read by
        # the F2 resolver; F2 itself does not populate them.
        #
        # Atomicity: aiosqlite's default isolation_level="" mode silently
        # COMMITs before any non-DML statement (CREATE/ALTER/DROP), so
        # each DDL effectively runs in its own auto-commit. Idempotency
        # is provided by `IF NOT EXISTS` + the `PRAGMA table_info` guard;
        # the `INSERT INTO schema_version` goes LAST so a partial apply
        # leaves version=7 and `ensure_schema` retries cleanly on the
        # next call. The INSERT uses `OR IGNORE` to neutralize the narrow
        # concurrent-`ensure_schema` PK-violation race window for v8;
        # older migrations (v3/v5/v6/v7) accept the same exposure with
        # bare INSERT and are not backported.
        #
        # Use individual `await conn.execute(...)` calls — NOT
        # `executescript`. The `executescript` form COMMITs before its
        # first DDL and would defeat the LAST-INSERT idempotency.
        await conn.execute("""\
CREATE TABLE IF NOT EXISTS tool_configs (
    name TEXT PRIMARY KEY,
    config TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)""")

        # Idempotent ADD COLUMN: skip if the column already exists.
        # NOTE: omit `DEFAULT NULL` — SQLite columns are nullable by
        # default, and an explicit `DEFAULT NULL` clause would surface
        # in PRAGMA table_info as the literal string "NULL" rather than
        # Python None.
        async with conn.execute("PRAGMA table_info(agents)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if "tool_overrides" not in existing_cols:
            await conn.execute("ALTER TABLE agents ADD COLUMN tool_overrides TEXT")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (8,))
        await conn.commit()
        version = 8

    if version < 9:
        # Add `enabled` column to tool_configs so the F6 admin UI can
        # operator-disable a tool without touching per-agent allow/deny
        # lists. Default 1 (true) keeps every pre-v9 row enabled.
        #
        # Idempotency follows the v8 pattern: PRAGMA-check the column
        # presence so a re-run after partial-apply is a no-op, and
        # leave the schema_version INSERT for LAST. Use individual
        # `await conn.execute(...)` calls (NOT `executescript`) so the
        # implicit COMMIT stays out of the way.
        async with conn.execute("PRAGMA table_info(tool_configs)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if "enabled" not in existing_cols:
            await conn.execute(
                "ALTER TABLE tool_configs ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1"
            )

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (9,))
        await conn.commit()
        version = 9

    if version < 10:
        # Rebuild mcp_sources to (a) replace the deprecated 'sse' transport
        # literal with the spec-aligned 'streamable-http' in the CHECK
        # constraint, and (b) add the `secrets TEXT DEFAULT '{}'` column
        # for field-segregated encryption (mission 07 flight 01 design).
        # SQLite has no ALTER TABLE DROP CONSTRAINT, so this is a v3/v5/v6-
        # style table-rename ceremony — but built from individual
        # `await conn.execute(...)` calls (NOT executescript) and with
        # `INSERT OR IGNORE INTO schema_version` LAST, mirroring v8/v9's
        # idempotency contract.
        #
        # The 'sse' → 'streamable-http' rename happens via CASE-WHEN in
        # the INSERT-SELECT step, NOT a pre-rebuild UPDATE — the still-
        # active CHECK on the old table is `type IN ('stdio', 'sse')`,
        # which would reject the literal 'streamable-http'.
        #
        # Defensive DROP IF EXISTS on mcp_sources_new clears any stale
        # state from a prior partial-apply (the v8/v9 pattern's stronger
        # idempotency standard).
        await conn.execute("DROP TABLE IF EXISTS mcp_sources_new")

        await conn.execute("""\
CREATE TABLE mcp_sources_new (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('stdio', 'streamable-http')),
    config TEXT DEFAULT '{}',
    secrets TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)""")

        await conn.execute("""\
INSERT INTO mcp_sources_new (id, name, type, config, secrets, created_at, updated_at)
    SELECT id, name,
           CASE WHEN type = 'sse' THEN 'streamable-http' ELSE type END,
           config,
           '{}',
           created_at,
           updated_at
    FROM mcp_sources""")

        await conn.execute("DROP TABLE mcp_sources")
        await conn.execute("ALTER TABLE mcp_sources_new RENAME TO mcp_sources")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (10,))
        await conn.commit()
        version = 10

    if version < 11:
        # Add `mcp_overrides` JSON column to `agents` for per-agent MCP
        # source override dispatch (mission 07 flight 06 leg 01 design).
        # Mirrors the v8 ALTER pattern for `tool_overrides` — TEXT column,
        # nullable, NO `DEFAULT NULL` clause (the explicit clause would
        # surface in PRAGMA table_info as the literal string "NULL"
        # rather than Python None — see v8 comment block).
        #
        # Idempotency: PRAGMA-check the column presence so a re-run after
        # partial-apply is a no-op. `INSERT OR IGNORE` on schema_version
        # LAST, mirroring the v8/v9/v10 pattern.
        async with conn.execute("PRAGMA table_info(agents)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if "mcp_overrides" not in existing_cols:
            await conn.execute("ALTER TABLE agents ADD COLUMN mcp_overrides TEXT")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (11,))
        await conn.commit()
        version = 11

    if version < 12:
        # Extend llm_providers.type CHECK constraint to allow 'openrouter'.
        # SQLite has no `ALTER TABLE DROP CONSTRAINT`, so rebuild the table
        # following the v6 pattern (which added 'mock'). FK enforcement is
        # ON at connection-time (connection.py:20) and `agents.provider_config_id`
        # references this table — the OFF/ON bracket prevents the DROP from
        # tripping referential integrity. INSERT OR IGNORE INTO schema_version
        # is LAST so a partial-apply leaves version=11 and the next call retries
        # cleanly.
        #
        # ``executescript`` (vs the v9/v10 individual-execute pattern documented
        # in CLAUDE.md) is REQUIRED here: ``PRAGMA foreign_keys=OFF`` only
        # takes effect within the same script as the DROP/RENAME — separate
        # ``conn.execute`` calls re-evaluate FK state between statements.
        # ``DROP TABLE IF EXISTS llm_providers_new`` is the defensive prelude
        # that makes a re-run after a crash AFTER ``CREATE TABLE
        # llm_providers_new`` (but BEFORE the rename) recover cleanly.
        await conn.executescript(f"""\
PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS llm_providers_new;

CREATE TABLE llm_providers_new (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ({_PROVIDER_TYPES_SQL})),
    base_url TEXT NOT NULL,
    api_key TEXT,
    config TEXT DEFAULT '{{}}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO llm_providers_new
    (id, name, type, base_url, api_key, config, created_at, updated_at)
    SELECT id, name, type, base_url, api_key, config, created_at, updated_at
    FROM llm_providers;

DROP TABLE llm_providers;
ALTER TABLE llm_providers_new RENAME TO llm_providers;

PRAGMA foreign_keys=ON;
""")
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (12,))
        await conn.commit()
        version = 12

    if version < 13:
        # Add connector_accounts table (mission 10 flight 01) for
        # bi-directional communication connector identities (Discord bot,
        # Slack workspace app, etc.). Sibling to mcp_sources at the
        # persistence-layer level.
        #
        # No CHECK constraint on `type` in v13 (in contrast to mcp_sources
        # which had `CHECK (type IN ('stdio', 'streamable-http'))` from v3).
        # v19 (F8 L2 — landed) added the CHECK via table-rename ceremony per
        # the table-rebuild precedent used in v3/v6 for `llm_providers`. v13
        # deliberately deferred the CHECK because `CONNECTOR_TYPES` was empty
        # at v13 landing; the v3/v6 precedent (CHECK in CREATE TABLE from
        # day one + later extension via rebuild) doesn't apply because there
        # was nothing to constrain initially. v14 was claimed by F1 L2's
        # `name` column on connector_accounts; v15 by F2 L2's
        # `idle_timeout_seconds`; v16 by F3 L1's chat_sessions external-key
        # columns + `session_continuation_seconds`; v17 by F4 L5's
        # `agents.connector_account_ids` persistence; v18 by F6 L1c's
        # `agents.connector_acls` persistence; v19 by F8 L2's CHECK
        # constraint table-rename ceremony. The _connector_types.py tuple is
        # the canonical source of truth — empty in v13, populated to
        # `("discord", "stub")` in F8 L2.
        #
        # Idempotency follows the v10/v11 contract: individual
        # `await conn.execute(...)` calls (NOT executescript), CREATE TABLE
        # IF NOT EXISTS makes the table creation a no-op on rerun, and the
        # `INSERT OR IGNORE INTO schema_version` is LAST so a partial-apply
        # leaves version=12 and the next call retries cleanly.
        await conn.execute("""\
CREATE TABLE IF NOT EXISTS connector_accounts (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    config TEXT DEFAULT '{}',
    secrets TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)""")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (13,))
        await conn.commit()
        version = 13

    if version < 14:
        # Add `name` column to connector_accounts. Caught during leg 02 of
        # mission 10 flight 01: the flight spec said "mirror MCPSource shape"
        # but the v13 migration omitted the column. MCPSource has `name: str`
        # as a first-class column for operator-visible identification
        # (Studio agent editor + MCP admin surface both render `name`).
        # Connector accounts inherit the same display surface in flight 2.
        #
        # NOT NULL DEFAULT '' lets the ALTER succeed against any v13-seeded
        # row (in practice zero — the table was empty at v13). New rows
        # created through ConnectorAccountRepository will always carry a real
        # `name` because the Pydantic model requires it (no default).
        #
        # Idempotency follows the v11 ALTER ADD COLUMN pattern (PRAGMA guard
        # + INSERT OR IGNORE on schema_version LAST).
        async with conn.execute("PRAGMA table_info(connector_accounts)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if "name" not in existing_cols:
            await conn.execute(
                "ALTER TABLE connector_accounts ADD COLUMN name TEXT NOT NULL DEFAULT ''"
            )

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (14,))
        await conn.commit()
        version = 14

    if version < 15:
        # Add `idle_timeout_seconds` column to connector_accounts. Mission 10
        # flight 02 leg 02: operator-configurable per-account pool idle TTL.
        # Nullable INTEGER — NULL means "use _resolve_ttl_seconds default /
        # env-var override" (the existing pre-flight-02 behaviour). Bounded
        # at the Pydantic layer (1 ≤ value ≤ 604800) to catch the
        # milliseconds-vs-seconds typo.
        #
        # Downstream: flight 08 (Discord) previously planned a v15 CHECK
        # migration; that renumbers to v19 (v18 is claimed by F6 L1c —
        # `agents.connector_acls`). See _connector_types.py docstring +
        # tests/test_db_migration.py TestSchemaV14 docstring.
        #
        # Idempotency follows the v11/v14 ALTER ADD COLUMN pattern (PRAGMA
        # guard + INSERT OR IGNORE on schema_version LAST).
        async with conn.execute("PRAGMA table_info(connector_accounts)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if "idle_timeout_seconds" not in existing_cols:
            await conn.execute(
                "ALTER TABLE connector_accounts ADD COLUMN idle_timeout_seconds INTEGER NULL"
            )

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (15,))
        await conn.commit()
        version = 15

    if version < 16:
        # Mission 10 Flight 3 Leg 1: chat-session connector keying + session
        # continuation timeout.
        #
        # ADDs seven nullable columns to chat_sessions that hold the external
        # conversation identity (platform, connector_account_id, channel_id,
        # thread_id, peer_id), plus a JSON metadata column (session_metadata;
        # F7 routing-decision logs piggyback so we only migrate once) and a
        # timestamp column (last_inbound_at) for the resolver's
        # continuation-window check. All NULL on non-connector sessions; the
        # partial index below makes the lookup fast for connector-keyed rows
        # without paying for the (much larger) non-connector set.
        #
        # ADDs session_continuation_seconds to connector_accounts (sibling
        # to v15's idle_timeout_seconds — the per-connector chat-session
        # continuation window; defaults to 86400=24h via the resolver, NOT
        # via a column DEFAULT, so NULL means "use resolver default").
        #
        # CREATEs the partial expression index for the external-key lookup.
        # SQLite ≥3.9 supports expression indexes; COALESCE in the indexed
        # expression list normalises NULL thread_id matches against the
        # resolver's COALESCE(?, '') WHERE clause.
        #
        # Downstream: flight 08 (Discord) previously planned a v16 CHECK
        # migration; that renumbers to v19 (v18 is claimed by F6 L1c —
        # `agents.connector_acls`). See _connector_types.py docstring +
        # tests/test_db_migration.py TestSchemaV14 docstring + agents.md
        # connector-type checklist item 4.
        #
        # Idempotency follows the v11/v14/v15 ALTER ADD COLUMN pattern
        # (PRAGMA guard per column + CREATE INDEX IF NOT EXISTS + INSERT OR
        # IGNORE on schema_version LAST).
        async with conn.execute("PRAGMA table_info(chat_sessions)") as cursor:
            existing_chat_cols = {row[1] for row in await cursor.fetchall()}
        for col, ddl_type in (
            ("platform", "TEXT"),
            ("connector_account_id", "TEXT"),
            ("channel_id", "TEXT"),
            ("thread_id", "TEXT"),
            ("peer_id", "TEXT"),
            ("session_metadata", "TEXT"),
            ("last_inbound_at", "TEXT"),
        ):
            if col not in existing_chat_cols:
                await conn.execute(
                    f"ALTER TABLE chat_sessions ADD COLUMN {col} {ddl_type} NULL"
                )

        async with conn.execute("PRAGMA table_info(connector_accounts)") as cursor:
            existing_acc_cols = {row[1] for row in await cursor.fetchall()}
        if "session_continuation_seconds" not in existing_acc_cols:
            await conn.execute(
                "ALTER TABLE connector_accounts"
                " ADD COLUMN session_continuation_seconds INTEGER NULL"
            )

        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_sessions_external_key "
            "ON chat_sessions(platform, connector_account_id, channel_id, COALESCE(thread_id, '')) "
            "WHERE platform IS NOT NULL"
        )

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (16,))
        await conn.commit()
        version = 16

    if version < 17:
        # Mission 10 Flight 4 Leg 5: AgentConfig.connector_account_ids
        # persistence. F4 L1 added the Pydantic field but missed the DB
        # column — leg 4 surfaced the gap when e2e tests had to monkey-
        # patch _row_to_config to re-inject. Adds a nullable TEXT column
        # storing the JSON-encoded list of attached connector_account_id
        # values; NULL is decoded as [] (back-compat for pre-v17 rows).
        #
        # Downstream: flight 08 (Discord) previously planned a v17 CHECK
        # migration; that renumbers to **v19** (v18 is claimed by F6 L1c —
        # `agents.connector_acls`). See _connector_types.py docstring +
        # tests/test_db_migration.py TestSchemaV14/V15/V16
        # downstream-renumber docstrings + agents.md connector-type
        # checklist item 4.
        #
        # Idempotency follows the v8/v9/v10/v11/v14/v15 ALTER ADD COLUMN
        # pattern (PRAGMA guard + INSERT OR IGNORE on schema_version LAST).
        async with conn.execute("PRAGMA table_info(agents)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if "connector_account_ids" not in existing_cols:
            await conn.execute(
                "ALTER TABLE agents ADD COLUMN connector_account_ids TEXT"
            )

        await conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (17,)
        )
        await conn.commit()
        version = 17

    if version < 18:
        # Mission 10 Flight 6 Leg 1c: AgentConfig.connector_acls persistence.
        # F6 L1c lands the per-agent ACL atomically — Pydantic field +
        # ALTER TABLE + repository round-trip in one leg, per F4 debrief
        # rec #1 ("a Pydantic field intended to persist ships its migration
        # in the SAME leg"). Adds a nullable TEXT column storing the JSON-
        # encoded outer dict {account_id: {"peers": [...], "channels": [...]}}
        # or NULL when no per-agent narrowing exists (back-compat for pre-v18
        # rows; matches connector_account_ids pre-v17 default decode).
        #
        # Downstream: flight 08 (Discord) previously planned v18 for its
        # CHECK constraint; that renumbers to v19. See _connector_types.py
        # docstring + tests/test_db_migration.py TestSchemaV{14,15,16,17}
        # downstream-renumber docstrings + agents.md connector-type
        # checklist item 4.
        #
        # Idempotency follows the v8/v9/v10/v11/v14/v15/v17 ALTER ADD COLUMN
        # pattern (PRAGMA guard + INSERT OR IGNORE on schema_version LAST).
        async with conn.execute("PRAGMA table_info(agents)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if "connector_acls" not in existing_cols:
            await conn.execute(
                "ALTER TABLE agents ADD COLUMN connector_acls TEXT"
            )

        await conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (18,)
        )
        await conn.commit()
        version = 18

    if version < 19:
        # Mission 10 Flight 8 Leg 2: add the
        # ``CHECK (type IN ('discord', 'stub'))`` constraint to
        # ``connector_accounts.type`` via the table-rename ceremony
        # established by v6 (``llm_providers`` ``'mock'`` extension) and
        # v12. F8 L2 lands layer 4 of the connector-type 6-layer extension
        # checklist documented in ``agents.md:299-306``.
        #
        # CHECK set is sourced from ``_CONNECTOR_TYPES_SQL`` (defined at
        # module top, mirroring ``_PROVIDER_TYPES_SQL``) so future
        # connector types added to ``CONNECTOR_TYPES`` flow automatically
        # into the next CHECK-changing migration without editing this
        # block. ``'stub'`` is in the CHECK per the M07 ``'mock'``-in-
        # PROVIDER_TYPES precedent — 69+ test sites construct
        # ``ConnectorAccount(type='stub')``; the production-purity
        # invariant ("no production code path inserts a stub-typed row")
        # is enforced by ``_stub.py:18-19``'s import-time guard +
        # ``register_builtin_connectors`` registering ``'discord'`` only,
        # NOT by the CHECK.
        #
        # Preserves all 9 columns of the v13/v14/v15/v16 incrementally-
        # evolved ``connector_accounts`` shape: ``id``, ``type``,
        # ``config``, ``secrets``, ``created_at``, ``updated_at``,
        # ``name``, ``idle_timeout_seconds``,
        # ``session_continuation_seconds``.
        #
        # Idempotency: ``if version < 19:`` short-circuits on re-run.
        # ``executescript`` is transactional in SQLite — either the whole
        # block lands or none of it does, so partial-apply tolerance
        # matches the v6 pattern. ``INSERT OR IGNORE INTO schema_version``
        # is LAST so a partial-apply leaves version=18 and the next
        # ``ensure_schema`` call retries cleanly.
        await conn.executescript(f"""\
PRAGMA foreign_keys=OFF;

CREATE TABLE connector_accounts_new (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ({_CONNECTOR_TYPES_SQL})),
    config TEXT DEFAULT '{{}}',
    secrets TEXT DEFAULT '{{}}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    name TEXT NOT NULL DEFAULT '',
    idle_timeout_seconds INTEGER NULL,
    session_continuation_seconds INTEGER NULL
);

INSERT INTO connector_accounts_new (id, type, config, secrets, created_at, updated_at, name, idle_timeout_seconds, session_continuation_seconds)
    SELECT id, type, config, secrets, created_at, updated_at, name, idle_timeout_seconds, session_continuation_seconds FROM connector_accounts;

DROP TABLE connector_accounts;

ALTER TABLE connector_accounts_new RENAME TO connector_accounts;

PRAGMA foreign_keys=ON;
""")
        await conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (19,)
        )
        await conn.commit()
        version = 19

    if version < 20:
        # Mission 11 Flight 7 Leg 6: AgentConfig.connector_always_listen
        # persistence. Per-agent ``always_listen`` toggle keyed by account_id
        # (``dict[str, bool] | None``); NULL pre-v20 rows AND new agents
        # without per-agent overrides decode to None. Idempotent ALTER ADD
        # COLUMN pattern mirrors v18's connector_acls migration (PRAGMA
        # guard + INSERT OR IGNORE on schema_version LAST).
        async with conn.execute("PRAGMA table_info(agents)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if "connector_always_listen" not in existing_cols:
            await conn.execute(
                "ALTER TABLE agents ADD COLUMN connector_always_listen TEXT"
            )

        await conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (20,)
        )
        await conn.commit()
        version = 20

    if version < 21:
        # Mission 11 Flight 9 Leg 2: pending_approvals table for the
        # Discord-native peer-approval flow. New table (no ALTER, no
        # rename ceremony). FK CASCADE on connector_account_id mirrors
        # the kb_items / chat_sessions precedent (schema lines 69, 88).
        # CHECK constraint pins the three-state lifecycle to surface
        # data corruption immediately rather than letting it propagate
        # silently. Idempotent: ``CREATE TABLE IF NOT EXISTS`` + the
        # ``if version < 21:`` short-circuit guarantee re-runs are no-ops.
        # PRAGMA foreign_keys is NOT toggled here — no existing FK
        # behavior changes, no table-rename ceremony.
        await conn.executescript("""\
CREATE TABLE IF NOT EXISTS pending_approvals (
    id TEXT PRIMARY KEY,
    connector_account_id TEXT NOT NULL
        REFERENCES connector_accounts(id) ON DELETE CASCADE,
    peer_id TEXT NOT NULL,
    peer_name TEXT NOT NULL,
    preview TEXT NOT NULL,
    received_at TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'approved', 'dismissed')),
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_approvals_account_peer_status
    ON pending_approvals (connector_account_id, peer_id, status);
""")
        await conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (21,)
        )
        await conn.commit()
        version = 21

    if version < 22:
        # Mission 11 Flight 10 Leg 1: dm_admission axis on
        # connector_accounts.config.allowlist. Row-rewrite migration
        # (NOT ALTER ADD COLUMN — the column is JSON-encoded TEXT, so
        # the schema change is shape-only and lives inside the JSON).
        # Legacy-preservation rule:
        #   - allowlist.channels empty/absent → dm_admission="all"
        #     (existing behavior admitted all DMs)
        #   - allowlist.channels non-empty → dm_admission="none"
        #     (existing behavior denied all DMs against channels mismatch)
        # Rows without an allowlist key are untouched; the Pydantic
        # validator default handles them at read time.
        # Mirrors the v7 row-rewrite precedent at schema.py:286-303.
        async with conn.execute(
            "SELECT id, config FROM connector_accounts"
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            account_id = row[0]
            config_json = row[1] or "{}"
            config = json.loads(config_json)
            allowlist = config.get("allowlist")
            if allowlist is None or "dm_admission" in allowlist:
                continue  # skip rows without allowlist or already migrated
            channels = allowlist.get("channels") or []
            allowlist["dm_admission"] = "all" if not channels else "none"
            config["allowlist"] = allowlist
            await conn.execute(
                "UPDATE connector_accounts SET config = ? WHERE id = ?",
                (json.dumps(config), account_id),
            )
        await conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (22,)
        )
        await conn.commit()
        version = 22
