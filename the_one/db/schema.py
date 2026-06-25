"""DDL definitions and schema versioning."""

from __future__ import annotations

import json
import logging

import aiosqlite

from the_one.db._connector_types import CONNECTOR_TYPES
from the_one.db._provider_types import PROVIDER_TYPES

logger = logging.getLogger(__name__)

CURRENT_VERSION = 32

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
        #
        # M11 F11 L1 v23 renamed ``connector_accounts`` → ``connectors``.
        # On a schema_version-rewind re-run after v23 has landed
        # (cf. ``TestSchemaV7::test_v7_strips_removed_tool_names``)
        # ``connector_accounts`` doesn't exist (it's been renamed); the
        # CREATE TABLE IF NOT EXISTS below would otherwise create an
        # empty ghost. Skip v13's CREATE when ``connectors`` already
        # exists — the post-v23 table is authoritative.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connectors'"
        ) as cursor:
            connectors_table_exists = await cursor.fetchone() is not None
        if not connectors_table_exists:
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
        # created through ConnectorRepository will always carry a real
        # `name` because the Pydantic model requires it (no default).
        #
        # Idempotency follows the v11 ALTER ADD COLUMN pattern (PRAGMA guard
        # + INSERT OR IGNORE on schema_version LAST).
        #
        # M11 F11 L1 v23 renamed ``connector_accounts`` → ``connectors``;
        # in a schema_version-rewind re-run after v23 has landed, the
        # source table doesn't exist. Skip the ALTER in that case —
        # the renamed table already has the ``name`` column from the
        # first ensure_schema's v14 run.
        async with conn.execute("PRAGMA table_info(connector_accounts)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if existing_cols and "name" not in existing_cols:
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
        #
        # M11 F11 L1 v23 renamed ``connector_accounts`` → ``connectors``;
        # in a schema_version-rewind re-run after v23 has landed, the
        # source table doesn't exist. The ``existing_cols and ...``
        # guard below short-circuits to skip the ALTER in that case.
        async with conn.execute("PRAGMA table_info(connector_accounts)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if existing_cols and "idle_timeout_seconds" not in existing_cols:
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
        # M11 F11 L1 v23 renamed ``chat_sessions.connector_account_id`` →
        # ``connector_id``. On a schema_version-rewind re-run after
        # v23 has landed (cf. ``TestSchemaV7::test_v7_strips_removed_tool_names``)
        # this v16 block re-fires against a table that already has the
        # renamed ``connector_id`` column. Skip the v23-renamed columns
        # in that case — re-adding them as new columns under the historical
        # name would leave a ghost duplicate.
        v23_renamed_present = "connector_id" in existing_chat_cols
        for col, ddl_type in (
            ("platform", "TEXT"),
            ("connector_account_id", "TEXT"),
            ("channel_id", "TEXT"),
            ("thread_id", "TEXT"),
            ("peer_id", "TEXT"),
            ("session_metadata", "TEXT"),
            ("last_inbound_at", "TEXT"),
        ):
            if col == "connector_account_id" and v23_renamed_present:
                continue
            if col not in existing_chat_cols:
                await conn.execute(f"ALTER TABLE chat_sessions ADD COLUMN {col} {ddl_type} NULL")

        # v23 may have renamed ``connector_accounts`` → ``connectors``
        # before this v16 re-fires; the guard below short-circuits in
        # that case (the renamed table already has the column).
        async with conn.execute("PRAGMA table_info(connector_accounts)") as cursor:
            existing_acc_cols = {row[1] for row in await cursor.fetchall()}
        if existing_acc_cols and "session_continuation_seconds" not in existing_acc_cols:
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
        # M11 F11 L1 v23 renamed ``agents.connector_account_ids`` →
        # ``connector_ids``. On a schema_version-rewind re-run after
        # v23 has landed (cf. ``TestSchemaV7::test_v7_strips_removed_tool_names``)
        # the renamed column already exists. Skip the ADD COLUMN in
        # that case so we don't leave a ghost duplicate.
        async with conn.execute("PRAGMA table_info(agents)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        if "connector_account_ids" not in existing_cols and "connector_ids" not in existing_cols:
            await conn.execute("ALTER TABLE agents ADD COLUMN connector_account_ids TEXT")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (17,))
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
            await conn.execute("ALTER TABLE agents ADD COLUMN connector_acls TEXT")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (18,))
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
        # ``Connector(type='stub')`` (the Pydantic class was renamed
        # from its historical *Account* form by M11 F11 L1 v23); the
        # production-purity
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
        #
        # M11 F11 L1 v23 renamed ``connector_accounts`` → ``connectors``;
        # on a schema-version-rewind re-run after v23 has landed
        # (cf. ``tests/test_db_migration.py::TestSchemaV7::
        # test_v7_strips_removed_tool_names`` which deletes
        # ``schema_version`` rows ≥ 7 and re-runs ``ensure_schema``),
        # the v19 source table no longer exists. Skip the row-rewrite
        # body in that case — the renamed table is already in its
        # post-v19 (CHECK-on-type) + post-v23 (renamed) shape via the
        # v23 migration's prior pass.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connector_accounts'"
        ) as cursor:
            pre_v23_source_exists = await cursor.fetchone() is not None

        if pre_v23_source_exists:
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

INSERT INTO connector_accounts_new (id, type, config, secrets, created_at, \
updated_at, name, idle_timeout_seconds, session_continuation_seconds)
    SELECT id, type, config, secrets, created_at, updated_at, name, \
idle_timeout_seconds, session_continuation_seconds FROM connector_accounts;

DROP TABLE connector_accounts;

ALTER TABLE connector_accounts_new RENAME TO connector_accounts;

PRAGMA foreign_keys=ON;
""")
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (19,))
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
            await conn.execute("ALTER TABLE agents ADD COLUMN connector_always_listen TEXT")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (20,))
        await conn.commit()
        version = 20

    if version < 21:
        # Mission 11 Flight 9 Leg 2: pending_approvals table for the
        # Discord-native peer-approval flow. New table (no ALTER, no
        # rename ceremony). FK CASCADE on connector_account_id mirrors
        # the kb_items / chat_sessions precedent (schema lines 69, 88).
        # (M11 F11 L1: the FK column was later renamed to ``connector_id``
        # and re-pointed at ``connectors(id)`` by v23. The v21 body
        # below documents the original v21 shape — the v23 row-rewrite
        # supplants the column and FK reference at migration time.)
        # (M11 F12 L3: v24 renamed the index
        # ``idx_pending_approvals_account_peer_status`` →
        # ``idx_pending_approvals_connector_peer_status``. The CREATE
        # INDEX statement below was split into two segments and gated
        # against the actual ``pending_approvals`` column shape so the
        # v7-strip rewind+rerun scenario doesn't fire a CREATE INDEX
        # against the post-v23 column name with the pre-v23 column
        # reference.)
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
""")
        # Defensive CREATE INDEX — gate on the actual column shape of
        # ``pending_approvals`` so the rewind+rerun scenario (where v23
        # already renamed ``connector_account_id`` → ``connector_id``
        # AND v24 already renamed the index) doesn't fire a CREATE
        # against the old column name with the old index name. The
        # ``CREATE INDEX IF NOT EXISTS`` is otherwise a no-op when the
        # index already exists.
        async with conn.execute("PRAGMA table_info(pending_approvals)") as cursor:
            pa_cols = {r[1] for r in await cursor.fetchall()}
        if "connector_account_id" in pa_cols:
            # Pre-v23 column shape (fresh-migration path or hand-built
            # legacy fixture).
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS "
                "idx_pending_approvals_account_peer_status "
                "ON pending_approvals "
                "(connector_account_id, peer_id, status)"
            )
        elif "connector_id" in pa_cols:
            # Post-v23 column shape (rewind+rerun path — v23 already
            # ran in a prior ensure_schema call and renamed the column).
            # The index may or may not exist depending on whether v24
            # ran in the prior call too; ``IF NOT EXISTS`` handles both.
            # M11 F12 L3 — use the v24 index name (the v24 block below
            # will DROP the old name + CREATE the new name idempotently,
            # but if we're in a rewind state where v24 already ran,
            # ``IF NOT EXISTS`` short-circuits both branches).
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS "
                "idx_pending_approvals_connector_peer_status "
                "ON pending_approvals (connector_id, peer_id, status)"
            )
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (21,))
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
        #
        # M11 F11 L1 v23 renamed ``connector_accounts`` → ``connectors``;
        # the original v22 source-table reference becomes a "no such
        # table" error on a schema-version-rewind re-run after v23 has
        # landed (cf. ``tests/test_db_migration.py::TestSchemaV7::
        # test_v7_strips_removed_tool_names`` which deletes
        # ``schema_version`` rows ≥ 7 and re-runs ``ensure_schema``).
        # The defensive guard below selects the source table name at
        # runtime so the loop targets whichever name is current.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('connector_accounts', 'connectors')"
        ) as cursor:
            tables = {r[0] for r in await cursor.fetchall()}
        source_table = "connector_accounts" if "connector_accounts" in tables else "connectors"
        async with conn.execute(f"SELECT id, config FROM {source_table}") as cursor:
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
                f"UPDATE {source_table} SET config = ? WHERE id = ?",
                (json.dumps(config), account_id),
            )
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (22,))
        await conn.commit()
        version = 22

    if version < 23:
        # Mission 11 Flight 11 Leg 1: connector-terminology rename.
        # The Pydantic class historically named after the "connector
        # account" concept is now ``Connector`` (the historical class
        # name is documented in the F11 flight log for posterity); this
        # migration brings the schema into line with the renamed class.
        # F11 chose "full consistency" over
        # "table-only with historical column-name residue", so this
        # migration renames the parent table AND the FK columns + JSON
        # column on dependent tables:
        #
        #   - ``connector_accounts`` table → ``connectors``
        #   - ``pending_approvals.connector_account_id`` column →
        #     ``connector_id`` (FK target re-pointed to ``connectors``)
        #   - ``chat_sessions.connector_account_id`` column →
        #     ``connector_id``
        #   - ``agents.connector_account_ids`` column → ``connector_ids``
        #
        # Two ceremonies in one migration:
        #
        # 1. Parent + FK-target row-rewrite (``connector_accounts`` and
        #    ``pending_approvals``): SQLite cannot rewrite an FK target
        #    in place, so the v6/v12/v19 ``executescript`` row-rewrite
        #    precedent applies — CREATE NEW with the renamed FK
        #    reference, INSERT FROM OLD, DROP OLD, ALTER RENAME. The
        #    ``CHECK (type IN ({_CONNECTOR_TYPES_SQL}))`` constraint
        #    on the parent ``type`` column is preserved verbatim from
        #    v19; the 9-column shape is otherwise unchanged.
        # 2. Column-rename on ``chat_sessions`` + ``agents`` (no FK on
        #    those columns): ``ALTER TABLE ... RENAME COLUMN ...``
        #    (SQLite ≥3.25, 2018-09; host + container both modern).
        #    The partial indexes
        #    ``idx_chat_sessions_external_key`` (on
        #    ``chat_sessions(connector_account_id, ...)`` per v15) and
        #    ``idx_pending_approvals_account_peer_status`` (on
        #    ``pending_approvals(connector_account_id, ...)`` per v21)
        #    are dropped + recreated against the renamed column
        #    expressions. The pending_approvals index dies implicitly
        #    when the parent table is dropped; the chat_sessions index
        #    is dropped explicitly before recreation.
        #
        # PRAGMA foreign_keys=OFF / =ON envelopes the whole block —
        # required by the FK-target row-rewrite (per v6/v12/v19
        # precedent). ``INSERT OR IGNORE INTO schema_version`` lands
        # LAST so a partial-apply leaves version=22 and the next
        # ``ensure_schema`` call retries cleanly. ``executescript`` is
        # transactional in SQLite — either the whole block lands or
        # none of it does.
        #
        # Index name ``idx_pending_approvals_account_peer_status`` is
        # retained even though it says "account" — renaming an index
        # name is a separate concern from renaming the column it
        # indexes; index naming is internal SQLite metadata and not
        # required for correctness here. L3 housekeeping is the
        # appropriate venue if a cosmetic-rename pass is desired.
        #
        # F11 L1 lands the rename; F11 L2 follows with the API URL
        # path swap + frontend DOM string swap.
        #
        # Defensive guard for "schema_version rewound past v23 without
        # also dropping the post-v23 tables" — the v7 strip-test
        # pattern (``tests/test_db_migration.py::TestSchemaV7::
        # test_v7_strips_removed_tool_names``) deletes
        # ``schema_version`` rows ≥ 7 and re-runs ``ensure_schema`` so
        # that v7's row-rewrite runs against the originally-seeded
        # rows. By the time the loop reaches v23 in the re-run, the
        # post-v23 tables (``connectors`` etc.) already exist from the
        # initial fresh-DB call. Also: v13's
        # ``CREATE TABLE IF NOT EXISTS connector_accounts`` recreates
        # an empty ``connector_accounts`` during the re-run because
        # the original v13 source table is gone (renamed to
        # ``connectors`` by v23). v14-v19 then ALTER + row-rewrite the
        # empty shell. So the v23 re-entry sees BOTH ``connector_accounts``
        # (empty, recreated) AND ``connectors`` (the real data from
        # the first pass).
        #
        # Strategy on re-entry: if ``connectors`` already exists, the
        # post-v23 final shape is in place. DROP the empty ``connector_accounts``
        # (and matching ``pending_approvals`` no-op — that table is
        # idempotent via v21's ``CREATE TABLE IF NOT EXISTS``) and
        # skip the row-rewrite. Otherwise, run the row-rewrite from
        # the original ``connector_accounts``.
        async with conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name IN ('connectors', 'connector_accounts')"
        ) as cursor:
            tables_present = {r[0] for r in await cursor.fetchall()}

        post_v23_target_exists = "connectors" in tables_present
        pre_v23_source_exists = "connector_accounts" in tables_present

        if post_v23_target_exists:
            # Already past v23 (likely a schema_version-rewind re-run).
            # If a ghost ``connector_accounts`` exists from v13's
            # ``CREATE TABLE IF NOT EXISTS`` re-firing, drop it so the
            # post-v23 shape is the single source of truth.
            if pre_v23_source_exists:
                await conn.execute("DROP TABLE connector_accounts")
                await conn.commit()
        elif pre_v23_source_exists:
            # Per-segment Python-level guards (NOT a single
            # executescript) because the hand-built ``TestSchemaVNN_*_
            # legacy_v(N-1)_row_decodes_*`` tests build a partial
            # schema — they create ``agents`` + ``connector_accounts``
            # but skip ``chat_sessions`` and ``pending_approvals``
            # (those tables are only created by ensure_schema's
            # SCHEMA_V1 path and v21, neither of which fires when the
            # test starts at version >= 13). Each rename below needs
            # to noop on a missing source table.
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('pending_approvals', 'chat_sessions', 'agents')"
            ) as cursor:
                v23_present = {r[0] for r in await cursor.fetchall()}

            # Segment 1: connector_accounts → connectors row-rewrite
            # (always runs in this branch — pre_v23_source_exists is True).
            await conn.executescript(f"""\
PRAGMA foreign_keys=OFF;

CREATE TABLE connectors_new (
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

INSERT INTO connectors_new (id, type, config, secrets, created_at, updated_at, \
name, idle_timeout_seconds, session_continuation_seconds)
    SELECT id, type, config, secrets, created_at, updated_at, name, \
idle_timeout_seconds, session_continuation_seconds FROM connector_accounts;

DROP TABLE connector_accounts;

ALTER TABLE connectors_new RENAME TO connectors;
""")

            # Segment 2: pending_approvals row-rewrite (FK target
            # repoint + FK column rename). Skip if the table doesn't
            # exist (partial-shape test scenario).
            if "pending_approvals" in v23_present:
                await conn.executescript("""\
CREATE TABLE pending_approvals_new (
    id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL
        REFERENCES connectors(id) ON DELETE CASCADE,
    peer_id TEXT NOT NULL,
    peer_name TEXT NOT NULL,
    preview TEXT NOT NULL,
    received_at TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'approved', 'dismissed')),
    resolved_at TEXT
);

INSERT INTO pending_approvals_new (id, connector_id, peer_id, peer_name, \
preview, received_at, status, resolved_at)
    SELECT id, connector_account_id, peer_id, peer_name, preview, \
received_at, status, resolved_at FROM pending_approvals;

DROP TABLE pending_approvals;

ALTER TABLE pending_approvals_new RENAME TO pending_approvals;

CREATE INDEX IF NOT EXISTS idx_pending_approvals_account_peer_status
    ON pending_approvals (connector_id, peer_id, status);
""")

            # Segment 3: chat_sessions column rename + index recreate.
            # Skip if table missing OR if column already renamed.
            if "chat_sessions" in v23_present:
                async with conn.execute("PRAGMA table_info(chat_sessions)") as cursor:
                    cs_cols = {r[1] for r in await cursor.fetchall()}
                if "connector_account_id" in cs_cols:
                    await conn.executescript("""\
ALTER TABLE chat_sessions RENAME COLUMN connector_account_id TO connector_id;

DROP INDEX IF EXISTS idx_chat_sessions_external_key;

CREATE INDEX idx_chat_sessions_external_key
    ON chat_sessions(platform, connector_id, channel_id, COALESCE(thread_id, ''))
    WHERE platform IS NOT NULL;
""")

            # Segment 4: agents column rename. Skip if table missing
            # OR if column already renamed.
            if "agents" in v23_present:
                async with conn.execute("PRAGMA table_info(agents)") as cursor:
                    ag_cols = {r[1] for r in await cursor.fetchall()}
                if "connector_account_ids" in ag_cols:
                    await conn.execute(
                        "ALTER TABLE agents RENAME COLUMN connector_account_ids TO connector_ids"
                    )

            await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (23,))
        await conn.commit()
        version = 23

    if version < 24:
        # Mission 11 Flight 12 Leg 3: structured-tuple storage for
        # channels + roles, per-peer ``dm_allowed`` for DM admission
        # gating under the ``admin-approved`` policy mode, and the
        # ``dm_admission`` Literal-value rename
        # ``"allowlisted-peers-only"`` → ``"admin-approved"``
        # (operator-vocabulary alignment).
        #
        # Row-rewrites BOTH ``connectors.config.allowlist`` AND
        # ``agents.connector_acls`` JSON column contents in a single
        # transaction. The transformation is offline-safe (no network);
        # ``guild_id`` is backfilled to NULL for legacy channel/role
        # entries (ACL treats NULL as "any guild" = legacy-permissive
        # backward-compat).
        #
        # Also renames the index
        # ``idx_pending_approvals_account_peer_status`` →
        # ``idx_pending_approvals_connector_peer_status`` (bundled per
        # F12 operator decision; F12 L1 explicitly deferred the index
        # rename to this leg).
        #
        # Idempotency: ``if version < 24:`` short-circuit + segment-
        # level re-entry guards (skip the per-row transformation if the
        # row is already in the post-v24 shape). The v7-strip-test
        # scenario (tests rewinding ``schema_version`` and re-running
        # ``ensure_schema``) is handled by the segment guards.
        #
        # DM Admission collapse rule (per the F12 L3 leg spec):
        #   - ``dm_admission == "none"`` → per-peer ``dm_allowed=False``
        #   - ``dm_admission == "all"`` → per-peer ``dm_allowed=True``
        #   - ``dm_admission == "allowlisted-peers-only"`` (explicit OR
        #     absent-but-allowlist-present) → per-peer
        #     ``dm_allowed=True`` AND the ``dm_admission`` Literal value
        #     rewritten to ``"admin-approved"``
        #   - ``dm_admission == "admin-approved"`` (pre-existing —
        #     defensive net for manual edits) → keep value; per-peer
        #     ``dm_allowed=True`` default

        # ---- Transform connectors.config.allowlist ----
        async with conn.execute("SELECT id, config FROM connectors") as cursor:
            connector_rows = await cursor.fetchall()
        for row in connector_rows:
            connector_id = row[0]
            config_json = row[1] or "{}"
            config = json.loads(config_json)
            allowlist = config.get("allowlist")
            if allowlist is None:
                continue
            # Segment guard: skip if already in v24 shape (any peer is
            # already a structured dict).
            peers = allowlist.get("peers", [])
            if peers and isinstance(peers[0], dict):
                continue
            # Determine the dm_allowed default from the old dm_admission
            # value. Bare ``.get("dm_admission")`` (no default) — we
            # must distinguish ABSENT (treat as F10 default
            # ``"allowlisted-peers-only"``) from explicit
            # ``"admin-approved"`` (pre-existing migrated value or
            # manual operator edit; defensive net).
            dm_admission_raw = allowlist.get("dm_admission")
            dm_admission_old = (
                dm_admission_raw if dm_admission_raw is not None else "allowlisted-peers-only"
            )
            if dm_admission_old == "none":
                dm_allowed_default = False
            else:
                # "all", "allowlisted-peers-only", "admin-approved", or
                # absent (→ defaulted to allowlisted-peers-only above).
                dm_allowed_default = True
            # Rewrite peers: list[str] → list[{id, dm_allowed}].
            allowlist["peers"] = [
                {"id": peer_id, "dm_allowed": dm_allowed_default} for peer_id in peers
            ]
            # Rewrite channels: list[str] → list[{guild_id, channel_id}]
            # with NULL guild_id (legacy-permissive backward-compat).
            allowlist["channels"] = [
                {"guild_id": None, "channel_id": ch_id} for ch_id in allowlist.get("channels", [])
            ]
            # Rewrite roles: list[str] → list[{guild_id, role_id}] with
            # NULL guild_id (only when the axis is present — roles is
            # optional in the pre-v24 shape).
            if "roles" in allowlist:
                allowlist["roles"] = [
                    {"guild_id": None, "role_id": role_id} for role_id in allowlist["roles"]
                ]
            # Rename / normalize dm_admission Literal value.
            # dm_admission_old already collapsed ABSENT →
            # ``"allowlisted-peers-only"`` at the default above, so one
            # branch suffices:
            #   (a) was ``"allowlisted-peers-only"`` (explicit or
            #       absent-defaulted) → rewrite to ``"admin-approved"``
            #   (b) was ``"all"`` / ``"none"`` / pre-existing
            #       ``"admin-approved"`` → unchanged
            if dm_admission_old == "allowlisted-peers-only":
                allowlist["dm_admission"] = "admin-approved"
            config["allowlist"] = allowlist
            await conn.execute(
                "UPDATE connectors SET config = ? WHERE id = ?",
                (json.dumps(config), connector_id),
            )

        # ---- Transform agents.connector_acls ----
        # ``connector_acls`` is a JSON column whose value is
        # ``dict[str, dict]`` keyed by account_id. Each account's
        # payload mirrors the account-scope shape for peers/channels/
        # roles; ``admit_dms`` stays as-is per per-agent overlay design.
        #
        # Defensive: skip the agents block entirely when the table
        # doesn't exist (hand-built partial-schema test fixtures —
        # mirrors the v23 ``v23_present`` pattern). The connector_acls
        # column itself was added by v18; pre-v18 hand-built fixtures
        # also need this guard.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
        ) as cursor:
            agents_table_present = (await cursor.fetchone()) is not None
        if not agents_table_present:
            agent_rows = []
        else:
            async with conn.execute("PRAGMA table_info(agents)") as cursor:
                agents_cols = {r[1] for r in await cursor.fetchall()}
            if "connector_acls" not in agents_cols:
                agent_rows = []
            else:
                async with conn.execute("SELECT name, connector_acls FROM agents") as cursor:
                    agent_rows = await cursor.fetchall()
        for row in agent_rows:
            agent_name = row[0]
            acls_str = row[1]
            if not acls_str:
                continue
            acls = json.loads(acls_str)
            if not isinstance(acls, dict) or not acls:
                continue
            # Segment guard: skip the ENTIRE row only if ANY account's
            # peers list is already structured-dict shape (a partial
            # state would indicate corruption — we treat any-already-
            # migrated as whole-row-migrated). Detect by scanning for
            # the first non-empty peers list whose head is a dict.
            any_v24_shape = False
            for payload in acls.values():
                if not isinstance(payload, dict):
                    continue
                payload_peers = payload.get("peers")
                if (
                    isinstance(payload_peers, list)
                    and payload_peers
                    and isinstance(payload_peers[0], dict)
                ):
                    any_v24_shape = True
                    break
            if any_v24_shape:
                continue
            for acct_id, payload in acls.items():
                if not isinstance(payload, dict):
                    continue
                # Transform peers (per-agent dm_allowed defaults True;
                # the per-agent overlay is a narrowing layer and does
                # not own DM-admission semantics — ACL helpers consult
                # ONLY account-scope per-peer dm_allowed per the F12 L3
                # DM Composition Truth Table).
                if isinstance(payload.get("peers"), list):
                    payload["peers"] = [
                        {"id": peer_id, "dm_allowed": True} for peer_id in payload["peers"]
                    ]
                # Transform channels (NULL guild_id backfill).
                if isinstance(payload.get("channels"), list):
                    payload["channels"] = [
                        {"guild_id": None, "channel_id": ch_id} for ch_id in payload["channels"]
                    ]
                # Transform roles (NULL guild_id backfill; if present).
                if isinstance(payload.get("roles"), list):
                    payload["roles"] = [
                        {"guild_id": None, "role_id": role_id} for role_id in payload["roles"]
                    ]
                # ``admit_dms`` stays as-is (per-agent overlay design).
            await conn.execute(
                "UPDATE agents SET connector_acls = ? WHERE name = ?",
                (json.dumps(acls), agent_name),
            )

        # ---- Rename pending_approvals index ----
        # SQLite ``DROP INDEX`` + ``CREATE INDEX`` is atomic from the
        # app's perspective (single connection during migration).
        # Defensive: skip when the pending_approvals table is missing
        # (hand-built partial-schema test fixtures — mirrors the
        # agents-table guard above and the v23 ``v23_present`` pattern).
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_approvals'"
        ) as cursor:
            pa_table_present = (await cursor.fetchone()) is not None
        if pa_table_present:
            await conn.execute("DROP INDEX IF EXISTS idx_pending_approvals_account_peer_status")
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS "
                "idx_pending_approvals_connector_peer_status "
                "ON pending_approvals (connector_id, peer_id, status)"
            )

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (24,))
        await conn.commit()
        version = 24

    if version < 25:
        # M11 F12 L5 — hierarchical server-parent UI alignment.
        # Delete orphaned null-``guild_id`` channel/role entries from
        # ``connectors.config.allowlist`` AND ``agents.connector_acls``.
        # These legacy entries are leftovers from v24's permissive backfill
        # (channel/role tuples with ``guild_id=None``); post-L5 the UI
        # always emits guild-scoped tuples (Server-as-parent layout) and
        # the Pydantic validator tightens to reject null ``guild_id``.
        # Operator framing at L5 planning: app is not live, just enforce
        # going forward; no data preservation needed.
        #
        # Idempotent: the per-row UPDATE only fires when a row actually
        # changes (``len(filtered) != len(original)``); re-running this
        # block against an already-cleaned DB is a no-op without needing
        # a separate segment marker (cf. v21's CREATE INDEX pattern).
        #
        # Row access uses POSITIONAL indexing (mirrors v24) so the
        # migration works against hand-built test fixtures that don't
        # configure ``conn.row_factory = aiosqlite.Row``.
        import json as _json

        # ---- Delete orphan null-guild_id from connectors.config.allowlist
        # Defensive: skip when the connectors table is missing
        # (hand-built partial-schema test fixtures — pre-v9 fixtures may
        # not have this table; pre-v23 fixtures have ``connector_accounts``
        # which is renamed to ``connectors`` by v23, so by the time
        # v25 runs the rename has been applied).
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connectors'"
        ) as cursor:
            connectors_table_present = (await cursor.fetchone()) is not None
        if connectors_table_present:
            async with conn.execute("SELECT id, config FROM connectors") as cursor:
                connector_rows = await cursor.fetchall()
            for row in connector_rows:
                connector_id = row[0]
                config_str = row[1] or "{}"
                config = _json.loads(config_str)
                allowlist = config.get("allowlist")
                if allowlist is None:
                    continue
                changed = False
                if "channels" in allowlist and isinstance(allowlist["channels"], list):
                    original = allowlist["channels"]
                    filtered = [
                        c for c in original if isinstance(c, dict) and c.get("guild_id") is not None
                    ]
                    if len(filtered) != len(original):
                        allowlist["channels"] = filtered
                        changed = True
                if "roles" in allowlist and isinstance(allowlist["roles"], list):
                    original = allowlist["roles"]
                    filtered = [
                        r for r in original if isinstance(r, dict) and r.get("guild_id") is not None
                    ]
                    if len(filtered) != len(original):
                        allowlist["roles"] = filtered
                        changed = True
                if changed:
                    config["allowlist"] = allowlist
                    await conn.execute(
                        "UPDATE connectors SET config = ? WHERE id = ?",
                        (_json.dumps(config), connector_id),
                    )

        # ---- Same for agents.connector_acls per-account payloads ----
        # Defensive: skip when the agents table is missing OR when the
        # ``connector_acls`` column is absent (hand-built partial-schema
        # test fixtures — mirrors the v24 connector_acls-column guard).
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
        ) as cursor:
            agents_table_present = (await cursor.fetchone()) is not None
        if agents_table_present:
            async with conn.execute("PRAGMA table_info(agents)") as cursor:
                agents_cols = {r[1] for r in await cursor.fetchall()}
        else:
            agents_cols = set()
        if agents_table_present and "connector_acls" in agents_cols:
            async with conn.execute("SELECT name, connector_acls FROM agents") as cursor:
                agent_rows = await cursor.fetchall()
            for row in agent_rows:
                agent_name = row[0]
                acls_str = row[1]
                if not acls_str:
                    continue
                acls = _json.loads(acls_str)
                if not isinstance(acls, dict):
                    continue
                changed = False
                for _acct_id, payload in acls.items():
                    if not isinstance(payload, dict):
                        continue
                    if "channels" in payload and isinstance(payload["channels"], list):
                        original = payload["channels"]
                        filtered = [
                            c
                            for c in original
                            if isinstance(c, dict) and c.get("guild_id") is not None
                        ]
                        if len(filtered) != len(original):
                            payload["channels"] = filtered
                            changed = True
                    if "roles" in payload and isinstance(payload["roles"], list):
                        original = payload["roles"]
                        filtered = [
                            r
                            for r in original
                            if isinstance(r, dict) and r.get("guild_id") is not None
                        ]
                        if len(filtered) != len(original):
                            payload["roles"] = filtered
                            changed = True
                if changed:
                    await conn.execute(
                        "UPDATE agents SET connector_acls = ? WHERE name = ?",
                        (_json.dumps(acls), agent_name),
                    )

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (25,))
        await conn.commit()
        version = 25

    if version < 26:
        # Mission 11 Flight 13 Leg 2 — connector-scope inference LLM
        # configuration substrate + per-agent ``peers[*].dm_allowed``
        # retirement (F12 footgun). Bundled into a single migration
        # since both touch the same JSON columns (connectors.config and
        # agents.connector_acls respectively).
        #
        # Pass A: connectors.config row-rewrites
        #   - Add ``inference_provider_config_id: None`` and
        #     ``inference_model: None`` to each row's config if absent.
        #     Operator edits per-connector via the Studio connector
        #     editor post-migration (F13 L4); the ``None`` defaults
        #     fall through to the routed agent's LLM at the dispatcher
        #     policy gate (F13 L3).
        #   - For each connector with ``config.get("always_listen") is
        #     True``, emit a ``logger.info`` line naming the connector
        #     ID + label so the operator sees the runtime-behavior
        #     shift at startup post-migration. Connectors with
        #     ``always_listen=false`` or absent are NOT logged (they
        #     don't run the inference gate).
        #
        # Pass B: agents.connector_acls row-rewrites
        #   - Iterate each per-account payload's ``peers`` list and
        #     ``entry.pop("dm_allowed", None)`` per entry. Idempotent
        #     (``dict.pop(key, None)`` is safe on re-run). The F12
        #     "structurally uniform but not consulted by ACL" footgun
        #     is retired: per-agent peers entries are now bare
        #     ``{id: str}`` dicts. Account-scope ``dm_allowed`` stays
        #     (DM admission is account-scope per the F12 L3 DM
        #     Composition Truth Table; the F13 L2 Pydantic validator
        #     enforces the per-agent rejection going forward).
        #
        # Note on intra-pipeline interaction with v24: the v24 block
        # at schema.py:~1370 still WRITES ``dm_allowed: True`` to
        # per-agent peer entries when rewriting pre-v24 rows. Under a
        # single ``ensure_schema`` pipeline running through v26, v24
        # writes the field then v26 strips it. The v24 block is
        # intentionally NOT modified (immutable post-land per Flight
        # Control discipline); the same-pipeline write-then-strip is
        # cheap and the alternative is editing landed migrations.
        #
        # Idempotency: per-row UPDATE only fires when ``changed``
        # (mirrors the v25 UPDATE-only-when-changed pattern at
        # schema.py:1463-1474). Re-running ``ensure_schema`` after
        # v26 is a no-op without needing a separate segment marker.
        #
        # Row access uses POSITIONAL indexing (mirrors v24 + v25) so
        # the migration works against hand-built test fixtures that
        # don't configure ``conn.row_factory = aiosqlite.Row``.
        import json as _json

        # ---- Pass A: connectors.config row-rewrites ----
        # Defensive: skip when the connectors table is missing
        # (hand-built partial-schema test fixtures — pre-v9 fixtures
        # may not have this table; pre-v23 fixtures have
        # ``connector_accounts`` which is renamed to ``connectors`` by
        # v23, so by the time v26 runs the rename has been applied).
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connectors'"
        ) as cursor:
            connectors_table_present = (await cursor.fetchone()) is not None
        if connectors_table_present:
            # Determine whether the ``name`` column exists (added at
            # v17 per recon; absent in pre-v17 hand-built fixtures).
            async with conn.execute("PRAGMA table_info(connectors)") as cursor:
                connector_cols = {r[1] for r in await cursor.fetchall()}
            has_name = "name" in connector_cols
            select_sql = (
                "SELECT id, config, name FROM connectors"
                if has_name
                else "SELECT id, config FROM connectors"
            )
            async with conn.execute(select_sql) as cursor:
                connector_rows = await cursor.fetchall()
            for row in connector_rows:
                connector_id = row[0]
                config_str = row[1] or "{}"
                connector_label = row[2] if has_name else connector_id
                config = _json.loads(config_str)
                changed = False
                if "inference_provider_config_id" not in config:
                    config["inference_provider_config_id"] = None
                    changed = True
                if "inference_model" not in config:
                    config["inference_model"] = None
                    changed = True
                if changed and config.get("always_listen") is True:
                    logger.info(
                        "v26: connector %s (%s) inherits None inference "
                        "defaults; edit per-connector via Studio "
                        "connector editor",
                        connector_id,
                        connector_label,
                    )
                if changed:
                    await conn.execute(
                        "UPDATE connectors SET config = ? WHERE id = ?",
                        (_json.dumps(config), connector_id),
                    )

        # ---- Pass B: agents.connector_acls row-rewrites ----
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
        ) as cursor:
            agents_table_present = (await cursor.fetchone()) is not None
        if agents_table_present:
            async with conn.execute("PRAGMA table_info(agents)") as cursor:
                agents_cols = {r[1] for r in await cursor.fetchall()}
        else:
            agents_cols = set()
        if agents_table_present and "connector_acls" in agents_cols:
            async with conn.execute("SELECT name, connector_acls FROM agents") as cursor:
                agent_rows = await cursor.fetchall()
            for row in agent_rows:
                agent_name = row[0]
                acls_str = row[1]
                if not acls_str:
                    continue
                acls = _json.loads(acls_str)
                if not isinstance(acls, dict):
                    continue
                changed = False
                for _acct_id, payload in acls.items():
                    if not isinstance(payload, dict):
                        continue
                    peers = payload.get("peers")
                    if not isinstance(peers, list):
                        continue
                    for entry in peers:
                        if isinstance(entry, dict) and "dm_allowed" in entry:
                            entry.pop("dm_allowed", None)
                            changed = True
                if changed:
                    await conn.execute(
                        "UPDATE agents SET connector_acls = ? WHERE name = ?",
                        (_json.dumps(acls), agent_name),
                    )

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (26,))
        await conn.commit()
        version = 26

    if version < 27:
        # M11 F14 L02 — unify guild scoping onto ``allowlist.guilds``.
        # The standalone top-level "Scope to servers" guilds key (the
        # Runtime Config field) is retired in favor of a single source
        # of truth: ``config.allowlist.guilds`` (the inbound-admission
        # ACL "Servers" axis) now ALSO scopes slash-command registration
        # (``_sync_slash_commands``). This migration folds every
        # connector row's top-level guilds list into
        # ``config.allowlist.guilds`` (order-preserving dedup-union),
        # then removes the top-level key. The operator's diagnostically
        # added top-level ``guilds`` (F13 L6 PUT) is moved automatically.
        #
        # Idempotency: ``cfg.pop("guilds", None)`` yields ``None`` once
        # the top-level key is gone, so re-running ``ensure_schema``
        # after v27 leaves rows unchanged (the per-row UPDATE only fires
        # when ``changed``). The ``.pop`` idiom (vs a membership-test
        # branch) also keeps the source grep gate at 0 top-level
        # guilds-key references.
        #
        # Partial-apply safe: the schema_version INSERT is LAST, so a
        # crash mid-loop re-folds the remaining rows on the next run
        # (already-folded rows are no-ops via the pop-yields-None path).
        #
        # Row access uses POSITIONAL indexing (mirrors v24/v25/v26) so
        # the migration works against hand-built test fixtures that
        # don't configure ``conn.row_factory = aiosqlite.Row``.
        import json as _json

        # Defensive: skip when the connectors table is missing
        # (hand-built partial-schema test fixtures; pre-v23 fixtures
        # have ``connector_accounts`` which is renamed to ``connectors``
        # by v23, so by the time v27 runs the rename has been applied).
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connectors'"
        ) as cursor:
            connectors_table_present = (await cursor.fetchone()) is not None
        if connectors_table_present:
            async with conn.execute("SELECT id, config FROM connectors") as cursor:
                connector_rows = await cursor.fetchall()
            for row in connector_rows:
                connector_id = row[0]
                config_str = row[1] or "{}"
                config = _json.loads(config_str)
                had_key = "guilds" in config
                popped = config.pop("guilds", None)
                if not had_key:
                    # No top-level ``guilds`` key at all — nothing to do
                    # (idempotent re-run path once v27 has folded a row).
                    continue
                if not popped:
                    # An empty/None top-level ``guilds`` was present and
                    # has now been popped: persist its removal but don't
                    # gratuitously create an empty allowlist on rows that
                    # never had guilds to fold.
                    await conn.execute(
                        "UPDATE connectors SET config = ? WHERE id = ?",
                        (_json.dumps(config), connector_id),
                    )
                    continue
                # Create the allowlist only when there's a top-level
                # ``guilds`` to fold. A fresh allowlist must carry the
                # validator-required ``peers``/``channels`` axes (empty)
                # so the folded row still passes
                # ``Connector.model_validate`` (db/models.py requires
                # both keys whenever ``allowlist`` is present). Existing
                # allowlists already carry them.
                allowlist = config.setdefault("allowlist", {"peers": [], "channels": []})
                allowlist.setdefault("peers", [])
                allowlist.setdefault("channels", [])
                existing = allowlist.get("guilds") or []
                # Order-preserving dedup-union: existing first, then
                # newly folded ids, skipping duplicates.
                seen: set = set()
                merged: list = []
                for g in [*existing, *popped]:
                    if g not in seen:
                        seen.add(g)
                        merged.append(g)
                allowlist["guilds"] = merged
                await conn.execute(
                    "UPDATE connectors SET config = ? WHERE id = ?",
                    (_json.dumps(config), connector_id),
                )

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (27,))
        await conn.commit()
        version = 27

    if version < 28:
        # M11 F17 L8 (Leg D) — drop ``dm_allowed`` from account-scope
        # ``connectors.config.allowlist.peers`` entries.
        #
        # Post-F16 the account-scope ``peers`` axis gates DMs only, so
        # membership in the list already means "this person may DM."
        # The per-peer ``dm_allowed`` flag (introduced by F12 L3 v24)
        # is a redundant two-step that confuses operators: approve adds
        # ``{id, dm_allowed:False}`` then the operator must flip a
        # toggle before the peer can actually DM. This migration strips
        # ``dm_allowed`` → bare ``{id: str}`` so in-list == can-DM.
        #
        # Semantic effect: any peer that was previously approved but had
        # ``dm_allowed=False`` (stuck in limbo) is now admitted under
        # ``dm_admission="admin-approved"`` after the migration. This is
        # the intended fix for the F3a / F16-parked Known Issue.
        #
        # Target shape: ``{id: str}`` bare dicts — parallel to the
        # post-v26 per-agent peers shape; NOT plain strings — avoids a
        # future migration + matches precedent.
        #
        # Idempotency: skip a row if ``peers`` is empty OR the first
        # entry has no ``"dm_allowed"`` key (already in the bare
        # ``{id}`` shape). Mirror v24's guard at schema.py:1252.
        #
        # Defensive: skip when the ``connectors`` table is missing
        # (hand-built partial-schema test fixtures) — mirrors
        # v25/v26/v27 defensive pattern.
        #
        # Note: per-agent ``connector_acls.peers`` was already stripped
        # of ``dm_allowed`` by v26; only ``connectors.config`` needs
        # touching here.
        #
        # Row access uses POSITIONAL indexing (mirrors v24/v25/v26/v27)
        # so the migration works against hand-built test fixtures that
        # don't configure ``conn.row_factory = aiosqlite.Row``.
        import json as _json

        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connectors'"
        ) as cursor:
            connectors_table_present = (await cursor.fetchone()) is not None
        if connectors_table_present:
            async with conn.execute("SELECT id, config FROM connectors") as cursor:
                connector_rows = await cursor.fetchall()
            for row in connector_rows:
                connector_id = row[0]
                config_str = row[1] or "{}"
                config = _json.loads(config_str)
                allowlist = config.get("allowlist")
                if allowlist is None:
                    continue
                peers = allowlist.get("peers", [])
                # Idempotency guard: skip if already in bare ``{id}``
                # shape (no ``dm_allowed`` key on first entry).
                if not peers or "dm_allowed" not in peers[0]:
                    continue
                # Strip ``dm_allowed`` from every entry; retain ``id``
                # and any other future keys.
                allowlist["peers"] = [
                    {k: v for k, v in entry.items() if k != "dm_allowed"}
                    for entry in peers
                    if isinstance(entry, dict)
                ]
                config["allowlist"] = allowlist
                await conn.execute(
                    "UPDATE connectors SET config = ? WHERE id = ?",
                    (_json.dumps(config), connector_id),
                )

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (28,))
        await conn.commit()
        version = 28

    if version < 29:
        # M11 F17 L10 (Leg F) — respond-on-approval: persist the full
        # original message and enough envelope context to re-dispatch it
        # when the operator approves the peer.
        #
        # Four additive nullable columns on ``pending_approvals``:
        #   - ``original_message TEXT``  — the full ``envelope.text``
        #     (NOT the truncated ``preview``), used to reconstruct the
        #     inbound replay after approval.
        #   - ``channel_id TEXT``        — the DM channel id from the
        #     original inbound envelope; needed to reconstruct the
        #     ``InboundEnvelope`` at replay time.
        #   - ``thread_id TEXT``         — the thread id (NULL for top-
        #     level DM messages, which is the normal DM case).
        #   - ``is_dm INTEGER``          — 1 if the original message was
        #     a direct message (used in the replay envelope's ``raw``
        #     dict); stored as INTEGER per SQLite bool convention.
        #
        # Simple additive ALTER ADD COLUMN — no row-rewrite ceremony
        # needed. Follows the v8/v9/v11/v14/v15/v17/v18/v20 ALTER ADD
        # COLUMN pattern (PRAGMA guard per column + INSERT OR IGNORE on
        # schema_version LAST). Nullable = no DEFAULT clause required
        # (SQLite columns are nullable by default; an explicit DEFAULT
        # NULL would appear as the literal string "NULL" in PRAGMA
        # table_info — see v8 comment block).
        #
        # Defensive: skip when ``pending_approvals`` is missing (hand-
        # built partial-schema test fixtures that don't run through v21).
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_approvals'"
        ) as cursor:
            pa_table_present = (await cursor.fetchone()) is not None
        if pa_table_present:
            async with conn.execute("PRAGMA table_info(pending_approvals)") as cursor:
                pa_cols = {row[1] for row in await cursor.fetchall()}
            if "original_message" not in pa_cols:
                await conn.execute("ALTER TABLE pending_approvals ADD COLUMN original_message TEXT")
            if "channel_id" not in pa_cols:
                await conn.execute("ALTER TABLE pending_approvals ADD COLUMN channel_id TEXT")
            if "thread_id" not in pa_cols:
                await conn.execute("ALTER TABLE pending_approvals ADD COLUMN thread_id TEXT")
            if "is_dm" not in pa_cols:
                await conn.execute("ALTER TABLE pending_approvals ADD COLUMN is_dm INTEGER")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (29,))
        await conn.commit()
        version = 29

    if version < 30:
        # M13 F01 L01 — per-agent chat-history retention. Additive NOT NULL
        # column with a constant DEFAULT 30, which backfills existing agents
        # to the default 30-day policy (mission Open Q resolved). PRAGMA guard
        # + INSERT OR IGNORE last (partial-apply safe), mirroring v29.
        # Defensive: skip when ``agents`` is missing (hand-built partial-
        # schema test fixtures that don't run through the full migration chain).
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
        ) as cursor:
            agents_table_present = (await cursor.fetchone()) is not None
        if agents_table_present:
            async with conn.execute("PRAGMA table_info(agents)") as cursor:
                agent_cols = {row[1] for row in await cursor.fetchall()}
            if "chat_history_retention_days" not in agent_cols:
                await conn.execute(
                    "ALTER TABLE agents ADD COLUMN "
                    "chat_history_retention_days INTEGER NOT NULL DEFAULT 30"
                )
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (30,))
        await conn.commit()
        version = 30

    if version < 31:
        # M13 F03 L01 — global app-metadata kv store. Holds the daily
        # purge's `last_purge_at` (Leg 3). Brand-new table, so CREATE TABLE
        # IF NOT EXISTS (idempotent / partial-apply safe), then stamp the
        # version with INSERT OR IGNORE last, mirroring v21/v30.
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS app_metadata ("
            "    key TEXT PRIMARY KEY,"
            "    value TEXT NOT NULL"
            ")"
        )
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (31,))
        await conn.commit()
        version = 31

    if version < 32:
        # M16 F08 L03 — add the `secrets TEXT DEFAULT '{}'` column to
        # tool_configs for field-segregated encryption of built-in tool
        # secrets (web_search's keyed-engine API keys). Mirrors the v10
        # mcp_sources-secrets precedent: idempotent ADD COLUMN guarded by
        # PRAGMA table_info so a re-run after partial-apply is a no-op, with
        # the INSERT OR IGNORE INTO schema_version LAST. A pre-existing row's
        # plaintext '{}' default decrypts to {} via the repository's
        # InvalidToken tolerance; the next write re-encrypts the column.
        async with conn.execute("PRAGMA table_info(tool_configs)") as cursor:
            existing_cols = {row[1] for row in await cursor.fetchall()}
        # `existing_cols` is empty when `tool_configs` doesn't exist (a
        # hand-built pre-v8 schema rewound past the v8 CREATE). Only ALTER
        # when the table is present AND lacks the column — guarding the
        # table-missing case the same way v9's `enabled` ADD COLUMN relies
        # on v8 having created the table in-sequence.
        if existing_cols and "secrets" not in existing_cols:
            await conn.execute("ALTER TABLE tool_configs ADD COLUMN secrets TEXT DEFAULT '{}'")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (32,))
        await conn.commit()
        version = 32
