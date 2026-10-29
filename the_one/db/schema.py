"""DDL definitions and schema versioning."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

import aiosqlite

from the_one.db._provider_types import PROVIDER_TYPES

logger = logging.getLogger(__name__)

CURRENT_VERSION = 48

# Render the provider-type CHECK constraint as a comma-separated SQL
# literal list, sourced from PROVIDER_TYPES. Both SCHEMA_V1 (fresh-DB
# path) and the v10 migration (existing-DB path) inject this so a future
# addition only needs to touch ``_provider_types.py``.
_PROVIDER_TYPES_SQL = ", ".join(f"'{t}'" for t in PROVIDER_TYPES)

# Mission 23 Flight 1 (backend-removal leg): ``db/_connector_types.py`` —
# and its ``CONNECTOR_TYPES``-derived ``_CONNECTOR_TYPES_SQL`` this module
# used to build — is deleted with the connector package. The v19 and v23
# ``CHECK (type IN ('discord', 'stub'))`` constraints below are now frozen
# inline literals: schema history is append-only, so they never change
# regardless of what Flight 2 does to the model's Literal. A future
# CHECK-changing migration (Flight 2 or later) adds a NEW constraint via
# the established table-rename ceremony — it does not edit these.

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
    secrets TEXT NOT NULL DEFAULT '{{}}',
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


# ── v48 (Mission 33 F3 DD6): the frozen schedule converter ────────────────
#
# Defined here, with its own parsing of the legacy five-kind shapes, so a later change to the
# live routine normalizer never changes what v48 did (schema history is append-only).

_V48_UPGRADE_FAILED = "upgrade_failed"
_V48_UPGRADE_FAILED_TEXT = (
    "This schedule could not be upgraded. Edit it to turn the routine back on."
)


def _v48_dt(value: object) -> datetime:
    """An aware datetime in UTC from an ISO string; ValueError on anything else."""
    if not isinstance(value, str):
        raise ValueError("not a time")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00") if value.endswith("Z") else value)
    if dt.tzinfo is None:
        raise ValueError("not aware")
    return dt.astimezone(timezone.utc)


def _v48_hhmm(value: object) -> str:
    if not isinstance(value, str) or not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", value):
        raise ValueError("bad time of day")
    return value


def _v48_render(instant: datetime, zone: tzinfo) -> dict[str, str]:
    local = instant.astimezone(zone)
    return {"date": local.date().isoformat(), "time": f"{local.hour:02d}:{local.minute:02d}"}


def _v48_is_canonical(schedule: object) -> bool:
    return isinstance(schedule, dict) and "start" in schedule and "kind" not in schedule


def _v48_convert(
    schedule: object,
    *,
    zone: tzinfo,
    next_run_at: str | None,
    anchor_at: str | None,
    live: bool,
    created_at: str | None,
) -> tuple[dict, datetime | None]:
    """A legacy schedule as the DD1 shape plus its anchor (None for wall-clock units).

    *live* is true for an enabled, unfinished routine with a ``next_run_at``: its local date
    (and an interval's exact next grid point) come from that value. Otherwise the date comes
    from ``created_at`` and an interval's anchor is ``anchor_at`` (or ``created_at``) plus one
    step. Raises ValueError for anything unreadable."""
    if not isinstance(schedule, dict):
        raise ValueError("not an object")
    kind = schedule.get("kind")
    never = {"kind": "never"}
    if kind == "once":
        at = _v48_dt(schedule.get("at"))
        return {"start": _v48_render(at, zone), "repeat": None, "ends": never}, at
    if kind == "interval":
        hours = schedule.get("hours")
        if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= 168:
            raise ValueError("bad hours")
        if live and next_run_at:
            anchor = _v48_dt(next_run_at)
        else:
            anchor = _v48_dt(anchor_at or created_at) + timedelta(hours=hours)
        sched = {
            "start": _v48_render(anchor, zone),
            "repeat": {"every": hours, "unit": "hour"},
            "ends": never,
        }
        return sched, anchor
    if kind not in ("daily", "weekdays", "weekly"):
        raise ValueError("unknown kind")
    time_text = _v48_hhmm(schedule.get("time"))
    if kind == "daily":
        repeat: dict = {"every": 1, "unit": "day"}
    elif kind == "weekdays":
        repeat = {"every": 1, "unit": "week", "days": [0, 1, 2, 3, 4]}
    else:
        days = schedule.get("days")
        if (
            not isinstance(days, list)
            or not days
            or any(isinstance(d, bool) or not isinstance(d, int) or not 0 <= d <= 6 for d in days)
        ):
            raise ValueError("bad days")
        repeat = {"every": 1, "unit": "week", "days": sorted(set(days))}
    basis = _v48_dt(next_run_at) if live and next_run_at else _v48_dt(created_at)
    start = {"date": basis.astimezone(zone).date().isoformat(), "time": time_text}
    return {"start": start, "repeat": repeat, "ends": never}, None


def _v48_anchor_text(anchor: datetime | None) -> str | None:
    return anchor.isoformat() if anchor is not None else None


def _v48_loads(raw: object) -> object:
    if raw is None:
        return None
    try:
        return json.loads(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


async def _v48_zone(conn: aiosqlite.Connection) -> tzinfo:
    """The zone the stored ``next_run_at`` values were computed in: the scheduler's
    ``routines_zone`` key, else the effective zone (imported lazily)."""
    async with conn.execute("SELECT value FROM app_metadata WHERE key = 'routines_zone'") as cur:
        row = await cur.fetchone()
    if row and row[0]:
        try:
            return ZoneInfo(str(row[0]))
        except Exception:  # noqa: BLE001 - a missing or invalid key falls back
            pass
    from the_one import time_zones

    return (await time_zones.load_effective_zone(conn)).tzinfo


async def _v48_rewrite_routines(conn: aiosqlite.Connection) -> None:
    """Rewrite every routine schedule and every proposal schedule to the DD1 shape."""
    from the_one import time_zones

    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('agent_routines', 'agent_routine_proposals', 'app_metadata')"
    ) as cur:
        tables = {r[0] for r in await cur.fetchall()}
    if "agent_routines" not in tables:
        return
    zone = (
        await _v48_zone(conn)
        if "app_metadata" in tables
        else ((await time_zones.load_effective_zone(conn)).tzinfo)
    )
    migrated: dict[str, tuple[object, dict, str | None]] = {}
    async with conn.execute(
        "SELECT id, schedule, enabled, finished_at, next_run_at, anchor_at, created_at "
        "FROM agent_routines"
    ) as cur:
        routines = await cur.fetchall()
    unreadable: list[str] = []
    for rid, raw, enabled, finished_at, next_run_at, anchor_at, created_at in routines:
        old = _v48_loads(raw)
        if _v48_is_canonical(old):
            continue
        try:
            sched, anchor = _v48_convert(
                old,
                zone=zone,
                next_run_at=next_run_at,
                anchor_at=anchor_at,
                live=bool(enabled) and finished_at is None and next_run_at is not None,
                created_at=created_at,
            )
        except (ValueError, OverflowError):
            unreadable.append(rid)
            continue
        anchor_text = _v48_anchor_text(anchor)
        migrated[rid] = (old, sched, anchor_text)
        await conn.execute(
            "UPDATE agent_routines SET schedule = ?, anchor_at = ? WHERE id = ?",
            (json.dumps(sched, sort_keys=True), anchor_text, rid),
        )
    now_iso = time_zones.utcnow().isoformat()
    for rid in unreadable:
        await conn.execute("UPDATE agent_routines SET enabled = 0 WHERE id = ?", (rid,))
        async with conn.execute(
            "SELECT 1 FROM agent_routine_runs WHERE routine_id = ? AND reason_code = ? LIMIT 1",
            (rid, _V48_UPGRADE_FAILED),
        ) as cur:
            seen = await cur.fetchone() is not None
        if not seen:
            await conn.execute(
                "INSERT INTO agent_routine_runs (id, routine_id, trigger_kind, outcome, reason, "
                "started_at, finished_at, reason_code) "
                "VALUES (?, ?, 'schedule', 'failed', ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    rid,
                    _V48_UPGRADE_FAILED_TEXT,
                    now_iso,
                    now_iso,
                    _V48_UPGRADE_FAILED,
                ),
            )
    if "agent_routine_proposals" not in tables:
        return
    async with conn.execute(
        "SELECT id, routine_id, payload, base, created_at FROM agent_routine_proposals"
    ) as cur:
        proposals = await cur.fetchall()
    for pid, routine_id, raw_payload, raw_base, created_at in proposals:
        payload, base = _v48_loads(raw_payload), _v48_loads(raw_base)
        changed = False
        if isinstance(payload, dict) and "schedule" in payload:
            if not _v48_is_canonical(payload["schedule"]):
                try:
                    sched, anchor = _v48_convert(
                        payload["schedule"],
                        zone=zone,
                        next_run_at=None,
                        anchor_at=None,
                        live=False,
                        created_at=created_at,
                    )
                    payload["schedule"] = sched
                    payload["anchor_at"] = _v48_anchor_text(anchor)
                    changed = True
                except (ValueError, OverflowError):
                    pass
        base_changed = False
        if isinstance(base, dict):
            if "schedule" in base and not _v48_is_canonical(base["schedule"]):
                match = migrated.get(routine_id) if routine_id else None
                if match is not None and match[0] == base["schedule"]:
                    base["schedule"], base["anchor_at"] = match[1], match[2]
                    base_changed = True
                else:
                    try:
                        sched, anchor = _v48_convert(
                            base["schedule"],
                            zone=zone,
                            next_run_at=None,
                            anchor_at=None,
                            live=False,
                            created_at=created_at,
                        )
                        base["schedule"] = sched
                        base["anchor_at"] = _v48_anchor_text(anchor)
                        base_changed = True
                    except (ValueError, OverflowError):
                        base.setdefault("anchor_at", None)
                        base_changed = True
            elif "anchor_at" not in base:
                base["anchor_at"] = None
                base_changed = True
        if changed or base_changed:
            await conn.execute(
                "UPDATE agent_routine_proposals SET payload = ?, base = ? WHERE id = ?",
                (
                    json.dumps(payload, sort_keys=True),
                    json.dumps(base, sort_keys=True) if base is not None else None,
                    pid,
                ),
            )


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
        # Atomicity (corrected — Flight 2 Leg 1, DD-13): under aiosqlite's
        # default isolation_level="" mode, the first DML statement opens a
        # transaction that stays open until an explicit `commit()` or
        # `rollback()` — DDL and PRAGMA do NOT auto-commit (that behavior was
        # removed in Python 3.6). What actually splits a migration block's
        # statements across transactions is a *different* coroutine's
        # `commit()` landing on the same shared connection in the gap between
        # two of this block's statements. `write_transaction`
        # (`the_one/db/_write_lock.py`) is what prevents that for every write
        # outside `ensure_schema` itself; migrations are exempt because they
        # run at `init_db()` before any request or background task exists, so
        # there is no other committer to race. Idempotency
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
        # CHECK set is a frozen inline literal (Mission 23 Flight 1 —
        # ``db/_connector_types.py`` and its derivation are gone; schema
        # history is append-only, so this block never changes again). A
        # future connector type does NOT flow in automatically — Flight 2
        # or later adds a NEW constraint via a fresh CHECK-changing
        # migration, it does not edit this one. ``'stub'`` is in the CHECK
        # per the M07 ``'mock'``-in-
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
            await conn.executescript("""\
PRAGMA foreign_keys=OFF;

CREATE TABLE connector_accounts_new (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),
    config TEXT DEFAULT '{}',
    secrets TEXT DEFAULT '{}',
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
        #    ``CHECK (type IN ('discord', 'stub'))`` constraint
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

            # Mission 23 Flight 1 (backend-removal leg) note: v38 drops
            # ``pending_approvals`` (whole table) and the ``agents``
            # connector-id column while leaving ``connectors`` itself
            # untouched (only its ROWS are cleared) — breaking the
            # assumption above that ``connectors`` existing implies
            # ``pending_approvals``/``agents`` are ALSO already in their
            # post-v23 shape. A schema_version-rewind re-run recreates
            # ``pending_approvals`` fresh (v21) and re-adds the agents
            # connector column (v17) in their OLD pre-v23 names while
            # ``connectors`` survives untouched from the prior pass.
            # Finish segment 2 / segment 4 here too if still needed —
            # same shape checks and DDL as the ``elif`` branch below,
            # just reachable when ``connectors`` already exists.
            # Cross-reference: this is the segment-2 pending_approvals
            # row-rewrite, duplicated from the ``elif`` branch's Segment 2
            # below — keep both copies in sync.
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_approvals'"
            ) as cursor:
                pa_present_here = (await cursor.fetchone()) is not None
            if pa_present_here:
                async with conn.execute("PRAGMA table_info(pending_approvals)") as cursor:
                    pa_cols_here = {r[1] for r in await cursor.fetchall()}
                if "connector_account_id" in pa_cols_here:
                    await conn.execute("PRAGMA foreign_keys=OFF")
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
                    await conn.execute("PRAGMA foreign_keys=ON")

            # Cross-reference: this is the segment-4 agents column rename,
            # duplicated from the ``elif`` branch's Segment 4 below — keep
            # both copies in sync.
            async with conn.execute("PRAGMA table_info(agents)") as cursor:
                ag_cols_here = {row[1] for row in await cursor.fetchall()}
            if "connector_account_ids" in ag_cols_here:
                await conn.execute(
                    "ALTER TABLE agents RENAME COLUMN connector_account_ids TO connector_ids"
                )
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
            await conn.executescript("""\
PRAGMA foreign_keys=OFF;

CREATE TABLE connectors_new (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),
    config TEXT DEFAULT '{}',
    secrets TEXT DEFAULT '{}',
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
            # Cross-reference: duplicated in the ``if post_v23_target_exists:``
            # branch above (Mission 23 Flight 1 note) — keep both copies in sync.
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
            # Cross-reference: duplicated in the ``if post_v23_target_exists:``
            # branch above (Mission 23 Flight 1 note) — keep both copies in sync.
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

    if version < 33:
        # M19 F01 L01 — rebuild llm_providers to (a) add the encrypted
        # OAuth-secrets column ``secrets TEXT NOT NULL DEFAULT '{}'`` for
        # the anthropic-plan provider type (DD-2: whole-dict Fernet blob;
        # managed keys access_token / refresh_token / token_expires_at /
        # scope / token_type) and (b) regenerate the ``type`` CHECK
        # constraint from PROVIDER_TYPES, picking up 'anthropic-plan'.
        # SQLite has no ALTER TABLE DROP CONSTRAINT, so one rebuild covers
        # both — the v12 ceremony verbatim: ``executescript`` is REQUIRED
        # (PRAGMA foreign_keys=OFF only holds within the same script as the
        # DROP/RENAME; ``agents.provider_config_id`` references this table),
        # ``DROP TABLE IF EXISTS llm_providers_new`` is the defensive
        # prelude for a crash between CREATE and RENAME, and INSERT OR
        # IGNORE INTO schema_version is LAST so a partial-apply leaves
        # version=32 and the next call retries cleanly. Existing rows carry
        # the plaintext '{}' column default — the repository's tolerant
        # InvalidToken decrypt reads that as empty secrets and the next
        # secrets write re-encrypts properly.
        #
        # Defensive: skip the rebuild when ``llm_providers`` is missing
        # (hand-built partial-schema test fixtures that don't run through
        # the full migration chain — the v29/v30 precedent).
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_providers'"
        ) as cursor:
            llm_providers_present = (await cursor.fetchone()) is not None
        if llm_providers_present:
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
    secrets TEXT NOT NULL DEFAULT '{{}}',
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
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (33,))
        await conn.commit()
        version = 33

    if version < 34:
        # M21 F02 L01 — the `agent_revisions` revision log. One
        # status-bearing table serves the applied-revision log (this leg),
        # the pending-approval queue (Leg 2), and restore provenance
        # (Leg 3): DD1. The full CHECK domain (all four `status` values,
        # both `source` values) ships now so later legs add code, not
        # migrations, against these values — this leg writes only
        # `status='applied', source='self'`.
        #
        # Brand-new table, so CREATE TABLE IF NOT EXISTS (idempotent /
        # partial-apply safe), then the index, then stamp the version with
        # INSERT OR IGNORE last, mirroring the v31 app_metadata template.
        # `agents` is created far earlier in-sequence, so the ON DELETE
        # CASCADE FK to `agents(name)` resolves; the self-FK
        # `restored_from -> agent_revisions(id)` resolves within the same
        # CREATE. No PRAGMA toggle / table-rebuild ceremony — nothing is
        # being rewritten.
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS agent_revisions ("
            "    id TEXT PRIMARY KEY,"
            "    agent_name TEXT NOT NULL REFERENCES agents(name) ON DELETE CASCADE,"
            "    field TEXT NOT NULL CHECK (field IN ('description', 'system_prompt')),"
            "    proposed_value TEXT NOT NULL,"
            "    base_value TEXT NOT NULL,"
            "    status TEXT NOT NULL"
            "        CHECK (status IN ('applied', 'pending', 'dismissed', 'superseded')),"
            "    source TEXT NOT NULL CHECK (source IN ('self', 'restore')),"
            "    restored_from TEXT REFERENCES agent_revisions(id) ON DELETE SET NULL,"
            "    created_at TEXT NOT NULL,"
            "    resolved_at TEXT"
            ")"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_revisions_agent_status "
            "ON agent_revisions (agent_name, status)"
        )
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (34,))
        await conn.commit()
        version = 34

    if version < 35:
        # M21 F02 L02 — per-agent approval mode. Add
        # `self_revision_requires_approval INTEGER NOT NULL DEFAULT 0` to
        # `agents`: the operator-owned flag that holds a self-revision in the
        # `agent_revisions` queue as `pending` instead of applying it. The
        # v30 chat_history_retention_days ADD COLUMN template verbatim:
        # idempotent ADD COLUMN guarded by PRAGMA table_info (no-op on
        # re-run / partial-apply), defensive skip when `agents` is missing
        # (hand-built partial-schema fixtures), and the INSERT OR IGNORE INTO
        # schema_version stamp LAST. The `NOT NULL DEFAULT 0` backfills every
        # existing row to `0` (approval mode off), so the load path reads a
        # plain non-null column with no absent/NULL case.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
        ) as cursor:
            agents_table_present = (await cursor.fetchone()) is not None
        if agents_table_present:
            async with conn.execute("PRAGMA table_info(agents)") as cursor:
                agent_cols = {row[1] for row in await cursor.fetchall()}
            if "self_revision_requires_approval" not in agent_cols:
                await conn.execute(
                    "ALTER TABLE agents ADD COLUMN "
                    "self_revision_requires_approval INTEGER NOT NULL DEFAULT 0"
                )
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (35,))
        await conn.commit()
        version = 35

    if version < 36:
        # M21 F03 L01 — the `agent_external_credentials` store (DD1/DD2/DD8).
        # One row per external-client grant: a distinct `ext_` principal
        # scoped to exactly one agent's surface, its secret Fernet-encrypted
        # at rest (DD2, secret-free projection built at the endpoint layer).
        #
        # The FK keys on the surface ROW, not `agent_name`: `source_id
        # REFERENCES mcp_sources(id) ON DELETE CASCADE` (leg design
        # refinement of DD2/DD9). Surface-disable and agent-delete both
        # delete the surface row, so the FK cascade auto-revokes every
        # external credential for that agent — an external principal never
        # outlives the operator closing the surface. Agent rename keeps the
        # row id stable, so `source_id`-keyed credentials survive a rename
        # with no work. Hard-revoke by row DELETE (no `revoked_at`); audit
        # of "which external principal tuned this agent" lives in the
        # revision log's `source_principal` (Leg 2), not here.
        #
        # Brand-new table, so CREATE TABLE IF NOT EXISTS (idempotent /
        # partial-apply safe), then the index on `source_id` (the cascade
        # and the per-surface list both scan by it), then stamp the version
        # with INSERT OR IGNORE last, mirroring the v34 template.
        # `mcp_sources` is created far earlier in-sequence (v10), so the FK
        # resolves. No PRAGMA toggle / table-rebuild ceremony — nothing is
        # being rewritten.
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS agent_external_credentials ("
            "    identifier TEXT PRIMARY KEY,"
            "    source_id TEXT NOT NULL REFERENCES mcp_sources(id) ON DELETE CASCADE,"
            "    secret TEXT NOT NULL,"
            "    label TEXT NOT NULL,"
            "    created_at TEXT NOT NULL"
            ")"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_external_credentials_source "
            "ON agent_external_credentials (source_id)"
        )
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (36,))
        await conn.commit()
        version = 36

    if version < 37:
        # M21 F03 L02 (DD3) — widen the `agent_revisions.source` CHECK domain
        # to admit `'external'` and add a nullable `source_principal TEXT`
        # column recording the external credential's identifier (NULL for
        # `self`/`restore`). SQLite cannot `ALTER … ADD CHECK`, so widening the
        # CHECK requires the table-rebuild ceremony — the v23 rebuild
        # (`if version < 23:`) is the precedent: `foreign_keys=OFF` envelope,
        # CREATE-new / INSERT-SELECT / DROP / RENAME, index recreate, version
        # stamp `INSERT OR IGNORE` LAST.
        #
        # The self-FK `restored_from` is the subtlety (flight DD3): it is
        # declared against the NEW table and `ALTER … RENAME TO` rewrites the
        # reference (modern `legacy_alter_table` OFF). The INSERT-SELECT names
        # all 10 existing columns EXPLICITLY on both sides (never positional) —
        # `source_principal` is absent from the SELECT and defaults to NULL for
        # every preserved row. Running under `foreign_keys=OFF` tolerates the
        # out-of-order self-referential rows during INSERT.
        #
        # Idempotency: guarded on `source_principal` column ABSENCE via PRAGMA
        # table_info. A schema-version rewind that leaves the column present
        # (stamp-only rewind) short-circuits the rebuild — the block only
        # stamps the version. This mirrors the ADD COLUMN guards elsewhere.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_revisions'"
        ) as cursor:
            agent_revisions_present = (await cursor.fetchone()) is not None
        needs_rebuild = False
        if agent_revisions_present:
            async with conn.execute("PRAGMA table_info(agent_revisions)") as cursor:
                revision_cols = {row[1] for row in await cursor.fetchall()}
            needs_rebuild = "source_principal" not in revision_cols
        if needs_rebuild:
            # ``executescript`` (like the v23 precedent) issues a COMMIT before
            # running, so ``PRAGMA foreign_keys=OFF`` takes effect (a PRAGMA
            # cannot change FK enforcement inside an open transaction). The
            # matching ``PRAGMA foreign_keys=ON`` after the script re-enables
            # enforcement (also outside a transaction). ``INSERT INTO … SELECT``
            # names all 10 existing columns explicitly on both sides;
            # ``source_principal`` is absent and defaults to NULL for every
            # preserved row. ``executescript`` is transactional in SQLite —
            # either the whole rebuild lands or none of it does.
            await conn.executescript(
                "PRAGMA foreign_keys=OFF;\n"
                "CREATE TABLE agent_revisions_new ("
                "    id TEXT PRIMARY KEY,"
                "    agent_name TEXT NOT NULL REFERENCES agents(name) ON DELETE CASCADE,"
                "    field TEXT NOT NULL CHECK (field IN ('description', 'system_prompt')),"
                "    proposed_value TEXT NOT NULL,"
                "    base_value TEXT NOT NULL,"
                "    status TEXT NOT NULL"
                "        CHECK (status IN ('applied', 'pending', 'dismissed', 'superseded')),"
                "    source TEXT NOT NULL CHECK (source IN ('self', 'restore', 'external')),"
                "    source_principal TEXT,"
                "    restored_from TEXT REFERENCES agent_revisions_new(id) ON DELETE SET NULL,"
                "    created_at TEXT NOT NULL,"
                "    resolved_at TEXT"
                ");\n"
                "INSERT INTO agent_revisions_new "
                "(id, agent_name, field, proposed_value, base_value, "
                " status, source, restored_from, created_at, resolved_at) "
                "SELECT id, agent_name, field, proposed_value, base_value, "
                " status, source, restored_from, created_at, resolved_at "
                "FROM agent_revisions;\n"
                "DROP TABLE agent_revisions;\n"
                "ALTER TABLE agent_revisions_new RENAME TO agent_revisions;\n"
                "CREATE INDEX IF NOT EXISTS idx_agent_revisions_agent_status "
                "ON agent_revisions (agent_name, status);\n"
            )
            await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (37,))
        await conn.commit()
        version = 37

    if version < 38:
        # Mission 23 Flight 1 (backend-removal leg, DD-2) — retire the
        # connector runtime's DB surface: the ``pending_approvals`` table
        # (+ its index), the three ``agents`` connector-attachment columns,
        # and every row in ``connectors`` (the table, ``ConnectorRepository``,
        # and encryption-rotation enrollment are KEPT — only legacy rows go;
        # Flight 2 rebuilds minimal CRUD over this same table). Follows the
        # ledger's idempotent presence-check pattern with
        # ``INSERT OR IGNORE INTO schema_version`` LAST. A plain
        # ``ALTER TABLE agents DROP COLUMN`` suffices for the three
        # columns — design review confirmed no index/CHECK entanglement on
        # any of them, so the table-rename ceremony (v10/v19/v23/v37
        # exemplars) is not needed here; SQLite's ``DROP COLUMN`` support
        # (3.35.0, 2021-03-12) is well within the Python ≥3.11 floor.
        #
        # 1. ``pending_approvals`` + its index. ``DROP INDEX``/``DROP
        #    TABLE ... IF EXISTS`` are themselves idempotent, so no PRAGMA
        #    presence check is needed here — a re-run after this block has
        #    already landed (schema_version rewind) is a no-op by
        #    construction.
        await conn.execute("DROP INDEX IF EXISTS idx_pending_approvals_connector_peer_status")
        await conn.execute("DROP TABLE IF EXISTS pending_approvals")

        # 2. The three ``agents`` connector-attachment columns. Guarded by
        #    PRAGMA table_info presence checks (mirrors the v32
        #    ``tool_configs.secrets`` ADD COLUMN idiom, inverted for DROP)
        #    so a schema-version-rewind re-run — where the columns are
        #    already gone — is a no-op per column, not just per block.
        #    ``existing_cols`` is empty only for a hand-built partial-schema
        #    fixture missing ``agents`` entirely; the guard tolerates that
        #    too (no ALTER attempted, no error).
        async with conn.execute("PRAGMA table_info(agents)") as cursor:
            agents_cols = {row[1] for row in await cursor.fetchall()}
        for _col in ("connector_ids", "connector_acls", "connector_always_listen"):
            if _col in agents_cols:
                await conn.execute(f"ALTER TABLE agents DROP COLUMN {_col}")

        # 3. Legacy connector rows. The table itself, its schema, and
        #    ``ConnectorRepository`` are KEPT (mission constraint) — only
        #    the rows go, since the REST surface that created them no
        #    longer exists and Flight 2's binding direction is the
        #    inverse (connector → default agent, stored in connector
        #    config JSON). Guarded on table presence for the same
        #    hand-built-fixture tolerance as step 2.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connectors'"
        ) as cursor:
            connectors_table_present = (await cursor.fetchone()) is not None
        if connectors_table_present:
            await conn.execute("DELETE FROM connectors")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (38,))
        await conn.commit()
        version = 38

    if version < 39:
        # Mission 23 Flight 4 Leg 1: v39 (mission RQ10). THE LAST migration
        # step this mission authorizes — RQ10's scope is exact (this block
        # ONLY), any further schema need is a new mission conversation.
        # Two payloads bundled into the one authorized step (DD-3):
        #
        # Segment 1 — ``connectors.type`` CHECK gains ``'telegram'`` via
        # the established table-rewrite ceremony (the v19 block at
        # schema.py:~745-825 documents the pattern this follows; v23's
        # ~:1147 row-rewrite is the CURRENT ``connectors`` shape this
        # segment rewrites again, verbatim except the CHECK set). Schema
        # history is append-only — this does NOT edit the v19/v23 blocks,
        # it adds a NEW constraint the same way every downstream
        # CHECK-changing migration has (per those blocks' own documented
        # successor-path comments).
        #
        # Unlike v19/v23, no PRAGMA rewind-tolerance guard is needed here:
        # those two needed one because the SOURCE table's NAME changed
        # across versions (``connector_accounts`` -> ``connectors``). v39's
        # source and target share the SAME name throughout
        # (``connectors`` -> ``connectors_new`` -> ``connectors``), so an
        # unconditional rewrite is naturally idempotent on a stamp-only
        # rewind re-run (cf. ``tests/test_db_migration.py::TestSchemaV7::
        # test_v7_strips_removed_tool_names``, which deletes
        # ``schema_version`` rows and re-runs ``ensure_schema``) — the
        # v38 "unconditional step, safe to repeat" precedent, not the
        # v19/v23 shape-detection dance. This is deliberately LESS
        # machinery than v19/v23 (leg spec edge-case note: don't
        # over-build what a same-name rewrite doesn't need).
        #
        # Table-presence guard (mirrors v38 step 3's "hand-built
        # partial-schema fixture missing the table" tolerance): a
        # ``schema_version``-seeded-at-N test fixture that hand-builds only
        # the tables its own migration under test needs (a real pattern in
        # ``tests/test_db_migration.py`` — e.g. a v29-shaped fixture with
        # only ``agents``/``schema_version``) never created ``connectors``
        # at all, since it starts past v13/v19/v23. Skipping the rewrite
        # when the table is absent is a no-op that changes nothing for a
        # real (monotonically-migrated) database, where ``connectors``
        # always exists by v39.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connectors'"
        ) as cursor:
            connectors_table_present = (await cursor.fetchone()) is not None
        if connectors_table_present:
            await conn.executescript("""\
PRAGMA foreign_keys=OFF;

CREATE TABLE connectors_new (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('discord', 'stub', 'telegram')),
    config TEXT DEFAULT '{}',
    secrets TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    name TEXT NOT NULL DEFAULT '',
    idle_timeout_seconds INTEGER NULL,
    session_continuation_seconds INTEGER NULL
);

INSERT INTO connectors_new (id, type, config, secrets, created_at, updated_at, \
name, idle_timeout_seconds, session_continuation_seconds)
    SELECT id, type, config, secrets, created_at, updated_at, name, \
idle_timeout_seconds, session_continuation_seconds FROM connectors;

DROP TABLE connectors;

ALTER TABLE connectors_new RENAME TO connectors;

PRAGMA foreign_keys=ON;
""")

        # Segment 2 — ``connector_directory`` (DD-4 schema): a brand-new
        # table, so it follows the v21 ``pending_approvals`` precedent
        # (schema.py:~867, ``CREATE TABLE IF NOT EXISTS``) rather than the
        # rewrite ceremony above — there is no prior shape to preserve,
        # and ``IF NOT EXISTS`` is already idempotent on any re-run. No FK
        # to ``connectors``: a deleted connector's rows are removed by one
        # deterministic DELETE wired into the connector delete route
        # (DD-1g), not cascade. ``platform_id`` is always the
        # send-addressable channel/peer id; ``thread_id`` is carried
        # alongside (NULL for peers and plain channels) exactly as
        # ``ChannelTarget`` expects it, so copy-the-ids stays literal for
        # thread entries too. Plaintext — names are the same sensitivity
        # class as chat history, not secrets: no encryptor, no ciphertext
        # column.
        await conn.execute("""\
CREATE TABLE IF NOT EXISTS connector_directory (
    connector_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('peer', 'channel')),
    platform_id TEXT NOT NULL,
    thread_id TEXT NULL,
    display_name TEXT NOT NULL,
    username TEXT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (connector_id, kind, platform_id)
)
""")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (39,))
        await conn.commit()
        version = 39

    if version < 40:
        # Flight 2 ("Storage and Embedding Foundation") Leg 1, DD-5/DD-13
        # (missions/24-knowledge-bases/flights/02-storage-and-embedding-
        # foundation/flight.md) — the flight's one hard-to-reverse step.
        #
        # Segment 1 — ``kb_items`` rebuild: adds a constrained lifecycle
        # (``status`` CHECK), a ``folder`` type, and identity/error-tracking
        # columns (``error``, ``content_hash``, ``size_bytes``, ``mtime``,
        # ``updated_at``, ``indexed_at``). Follows the v37 same-name rebuild
        # template: ``DROP TABLE IF EXISTS kb_items_new`` defensive prelude,
        # guarded on column absence (``"content_hash" not in PRAGMA
        # table_info(kb_items)`` — the v37 guard shape, not v39's
        # unconditional-rewrite shape, because a rewind-rerun should not
        # re-copy the table every time). Both CHECKs (``type``, ``status``)
        # are FROZEN INLINE LITERALS, never derived from
        # ``the_one/db/_kb_types.py`` — see the comment at this module's
        # v8 migration block (schema.py:22-28's sibling rule for CHECKs:
        # schema history is append-only, so a CHECK must never change out
        # from under a database that already ran it). ``_kb_types.py``'s
        # tuples pin the Pydantic ``Literal``s and the transition table
        # only. Existing rows migrate with a ``CASE`` mapping any
        # non-vocabulary ``status`` (including legacy NULL — the old column
        # was unconstrained) to ``'pending'``. ``parent_id`` is carried
        # through unchanged, self-referential against ``kb_items_new``
        # exactly as the v37 rebuild declares ``restored_from`` — the
        # ``RENAME`` rewrites the reference. Columns are named explicitly
        # on both sides of the INSERT-SELECT, never positional.
        #
        # ``PRAGMA foreign_keys=OFF`` takes effect only within the same
        # script as the DROP/RENAME (``executescript`` commits any open
        # transaction first); the matching ``PRAGMA foreign_keys=ON`` is
        # re-issued as its OWN ``execute`` after the script, for
        # consistency with the v37 comment (schema.py's v37 block) — this
        # is load-bearing: forgetting it leaves the singleton connection
        # with FKs off for the rest of the process. The ``executescript``
        # here also requires no open transaction touching the FTS table —
        # true today because every migration block commits before the
        # next runs.
        #
        # Segment 2 — ``kb_chunks``: a brand-new table, so it follows the
        # v36 new-table template (``CREATE TABLE IF NOT EXISTS``, plain
        # ``execute``, idempotent on any re-run). ``id INTEGER PRIMARY KEY
        # AUTOINCREMENT`` is LOAD-BEARING (DD-5, Architect, high): a plain
        # ``INTEGER PRIMARY KEY`` recycles the highest deleted rowid, and
        # the chunk repository (Leg 2) deletes-and-reinserts a chunk set on
        # every re-index, so a sidecar vector store one generation behind
        # (or a missed delete) could map a recycled id to different chunk
        # text — a silent wrong answer no generation check could catch.
        # With ``AUTOINCREMENT``, a stale id can only ever be a deleted
        # one. Cost: one ``sqlite_sequence`` row. Integer ids are
        # deliberate: FTS5 external-content tables and both candidate
        # vector backends key on integer rowids.
        #
        # Segment 3 — ``kb_chunks_fts``: an EXTERNAL-CONTENT FTS5 index
        # (``content='kb_chunks', content_rowid='id'``) so chunk text is
        # stored once. Sync is EXPLICIT in the chunk repository (Leg 2),
        # never via triggers — a dangling FTS trigger makes ``ALTER TABLE …
        # RENAME`` fail on ANY unrelated table, so one orphaned trigger
        # would break every future migration's rebuild ceremony, not only
        # a rebuild touching this table (DD-5, Architect S1).
        #
        # Ordering: the ``kb_items`` rebuild script first, then
        # ``kb_chunks``, then the FTS table, then the three indexes, then
        # the version stamp LAST (``INSERT OR IGNORE``, partial-apply-safe
        # like every migration since v8).
        await conn.execute("DROP TABLE IF EXISTS kb_items_new")
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kb_items'"
        ) as cursor:
            kb_items_present = (await cursor.fetchone()) is not None
        if not kb_items_present:
            # Defensive branch, not a real-chain path: every real database
            # reaches this block via version 0 -> `if version < 1:
            # SCHEMA_V1`, which always creates `kb_items` (schema.py:72-80).
            # The only way to arrive here with `kb_items` absent is a test
            # fixture that hand-builds a partial schema and stamps
            # `schema_version` directly at some version > 0 without ever
            # running SCHEMA_V1 (the same class of fixture the v39 block's
            # `connectors`-table-presence comment documents) — for that
            # case, create the table fresh in its v40 shape rather than
            # rebuilding from a v39 shape there is nothing to preserve of.
            await conn.execute("""\
CREATE TABLE kb_items (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    parent_id TEXT REFERENCES kb_items(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('file', 'url', 'folder')),
    path_or_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'indexing', 'indexed', 'failed')),
    error TEXT,
    content_hash TEXT,
    size_bytes INTEGER,
    mtime REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    indexed_at TEXT
)""")
            kb_items_needs_rebuild = False
        else:
            async with conn.execute("PRAGMA table_info(kb_items)") as cursor:
                kb_items_cols = {row[1] for row in await cursor.fetchall()}
            kb_items_needs_rebuild = "content_hash" not in kb_items_cols
        if kb_items_needs_rebuild:
            await conn.executescript("""\
PRAGMA foreign_keys=OFF;

CREATE TABLE kb_items_new (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    parent_id TEXT REFERENCES kb_items_new(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('file', 'url', 'folder')),
    path_or_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'indexing', 'indexed', 'failed')),
    error TEXT,
    content_hash TEXT,
    size_bytes INTEGER,
    mtime REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    indexed_at TEXT
);

INSERT INTO kb_items_new (id, kb_id, parent_id, type, path_or_url, status, created_at, updated_at)
    SELECT id, kb_id, parent_id, type, path_or_url,
           CASE WHEN status IN ('pending', 'indexing', 'indexed', 'failed')
                THEN status ELSE 'pending' END,
           created_at, created_at
    FROM kb_items;

DROP TABLE kb_items;

ALTER TABLE kb_items_new RENAME TO kb_items;
""")
            await conn.execute("PRAGMA foreign_keys=ON")

        await conn.execute("""\
CREATE TABLE IF NOT EXISTS kb_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL REFERENCES kb_items(id) ON DELETE CASCADE,
    kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (item_id, seq)
)""")

        await conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5("
            "text, content='kb_chunks', content_rowid='id', "
            "tokenize='porter unicode61')"
        )

        await conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_items_kb_id ON kb_items (kb_id)")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_kb_items_kb_status ON kb_items (kb_id, status)"
        )
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_chunks_kb_id ON kb_chunks (kb_id)")

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (40,))
        await conn.commit()
        version = 40

    if version < 41:
        # Flight 2 ("Storage and Embedding Foundation") Leg 6, DD-3/DD-9
        # (missions/24-knowledge-bases/flights/02-storage-and-embedding-
        # foundation/flight.md) — the operator chose `usearch` as the one
        # vector store at the DD-9 decision checkpoint (flight-log.md,
        # "DD-9 decision checkpoint (2026-09-15)"). DD-3 kept
        # `kb_vector_index` store-owned (created by `UsearchStore.open()`)
        # until the choice was made — store-owned until the decision,
        # migration-owned after — specifically so a losing backend would
        # never leave a dead table in a frozen migration forever; now that
        # `usearch` has won, the DDL moves here so the fresh-DB shape tests
        # own it, and `UsearchStore.open()` no longer issues any DDL.
        #
        # Column set is byte-for-byte what `UsearchStore.open()` created in
        # Leg 4, so a database where the store already made this table
        # (any Leg 4/5 dev database) passes through unchanged via
        # `IF NOT EXISTS`.
        #
        # This block must NOT touch `kb_vectors` (the removed candidate
        # backend's virtual table, a `vec0` type): a `vec0` table cannot be
        # dropped without its extension module loaded (`DROP TABLE` raises
        # `OperationalError: no such module: vec0`), verified at Leg 6
        # design — do not add a `DROP TABLE kb_vectors` here or to any
        # later migration. A dev database that opened the removed backend
        # between Leg 4 and Leg 6 keeps an inert `kb_vectors` table
        # forever — no release ever shipped it, and every other statement
        # on the connection (including this migration) works fine with the
        # table present and the extension absent.
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS kb_vector_index ("
            "kb_id TEXT PRIMARY KEY, "
            "path TEXT NOT NULL, "
            "count INTEGER NOT NULL, "
            "generation INTEGER NOT NULL, "
            "dtype TEXT NOT NULL, "
            "dim INTEGER NOT NULL, "
            "updated_at TEXT NOT NULL)"
        )

        # Belt-and-braces purge of a stale `knowledge.vector_store` record
        # naming the removed backend: `save_vector_store_settings` has no
        # production caller (verified at Leg 6 design — only a test or the
        # benchmark script could have written one), so this only ever
        # fires against a dev database. A `usearch` record — or any other
        # backend value — is left untouched. `json_extract` is available
        # on this host's SQLite (3.45.1) and JSON1 is built into every
        # SQLite >= 3.38, so no LIKE-based fallback is needed.
        #
        # `app_metadata` is guarded on presence (the same class of hazard
        # Leg 1 documented for `kb_items`): a hand-built partial-schema test
        # fixture that stamps `schema_version` rows directly up through 31
        # without ever running the real v31 block (`schema.py`'s
        # `app_metadata` CREATE) reaches this point with no `app_metadata`
        # table at all (`tests/test_db_migration.py::TestSchemaV32`'s v31
        # fixture is exactly this shape) — a real database always has it
        # from v31 onward.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='app_metadata'"
        ) as cursor:
            app_metadata_exists = await cursor.fetchone() is not None
        if app_metadata_exists:
            await conn.execute(
                "DELETE FROM app_metadata WHERE key = 'knowledge.vector_store' "
                "AND json_extract(value, '$.backend') = 'sqlite-vec'"
            )

        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (41,))
        await conn.commit()
        version = 41

    if version < 42:
        # Mission 27 Flight 1 (DD3) — per-agent rules, and `agent_revisions`
        # rebuilt so its `agent_name` foreign key follows a rename.
        #
        # `agent_rules` is brand new (CREATE IF NOT EXISTS). Its foreign key
        # carries ON UPDATE CASCADE so `SQLiteAgentStore.rename` (a plain
        # UPDATE of agents.name) carries the rows over. Any future
        # agent-keyed table must declare ON UPDATE CASCADE too.
        #
        # `agent_revisions` (v34/v37) declared `REFERENCES agents(name) ON
        # DELETE CASCADE` with no update action, so renaming an agent that
        # had revision rows failed with FOREIGN KEY constraint failed. The
        # rebuild follows the v37 ceremony with two corrections: the
        # self-reference names the FINAL table (correct whether or not
        # `legacy_alter_table` is on), and the guard reads
        # PRAGMA foreign_key_list so a database already carrying the cascade
        # (or a stamp-only rewind) skips the rebuild.
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS agent_rules ("
            "    id TEXT PRIMARY KEY,"
            "    agent_name TEXT NOT NULL REFERENCES agents(name)"
            "        ON DELETE CASCADE ON UPDATE CASCADE,"
            "    text TEXT NOT NULL,"
            "    enabled INTEGER NOT NULL DEFAULT 1,"
            "    position INTEGER NOT NULL,"
            "    created_at TEXT NOT NULL,"
            "    updated_at TEXT NOT NULL"
            ")"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_rules_agent_position "
            "ON agent_rules (agent_name, position)"
        )
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_revisions'"
        ) as cursor:
            revisions_present = (await cursor.fetchone()) is not None
        needs_fk_rebuild = False
        if revisions_present:
            async with conn.execute("PRAGMA foreign_key_list(agent_revisions)") as cursor:
                fk_rows = await cursor.fetchall()
            # foreign_key_list columns: id, seq, table, from, to, on_update, on_delete, match
            needs_fk_rebuild = any(
                row[2] == "agents" and str(row[5]).upper() != "CASCADE" for row in fk_rows
            )
        if needs_fk_rebuild:
            await conn.executescript(
                "PRAGMA foreign_keys=OFF;\n"
                "DROP TABLE IF EXISTS agent_revisions_new;\n"
                "CREATE TABLE agent_revisions_new ("
                "    id TEXT PRIMARY KEY,"
                "    agent_name TEXT NOT NULL REFERENCES agents(name)"
                "        ON DELETE CASCADE ON UPDATE CASCADE,"
                "    field TEXT NOT NULL CHECK (field IN ('description', 'system_prompt')),"
                "    proposed_value TEXT NOT NULL,"
                "    base_value TEXT NOT NULL,"
                "    status TEXT NOT NULL"
                "        CHECK (status IN ('applied', 'pending', 'dismissed', 'superseded')),"
                "    source TEXT NOT NULL CHECK (source IN ('self', 'restore', 'external')),"
                "    source_principal TEXT,"
                "    restored_from TEXT REFERENCES agent_revisions(id) ON DELETE SET NULL,"
                "    created_at TEXT NOT NULL,"
                "    resolved_at TEXT"
                ");\n"
                "INSERT INTO agent_revisions_new "
                "(id, agent_name, field, proposed_value, base_value, status, source, "
                " source_principal, restored_from, created_at, resolved_at) "
                "SELECT id, agent_name, field, proposed_value, base_value, status, source, "
                " source_principal, restored_from, created_at, resolved_at "
                "FROM agent_revisions;\n"
                "DROP TABLE agent_revisions;\n"
                "ALTER TABLE agent_revisions_new RENAME TO agent_revisions;\n"
                "CREATE INDEX IF NOT EXISTS idx_agent_revisions_agent_status "
                "ON agent_revisions (agent_name, status);\n"
            )
            await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (42,))
        await conn.commit()
        version = 42

    if version < 43:
        # Mission 27 Flight 2 (DD1) — per-agent notes. `agents` gains the
        # operator-owned `notes_enabled` switch (default off) and the
        # `notes_next_number` counter (never part of AgentConfig or the save
        # upsert, so a stale whole-row save cannot reuse a number). Both
        # ADD COLUMNs are guarded by PRAGMA table_info; `agent_notes` and its
        # unique index are idempotent. The FK carries ON UPDATE CASCADE so a
        # rename carries the notes, and ON DELETE CASCADE removes them.
        async with conn.execute("PRAGMA table_info(agents)") as cursor:
            agent_cols = {row[1] for row in await cursor.fetchall()}
        if agent_cols and "notes_enabled" not in agent_cols:
            await conn.execute(
                "ALTER TABLE agents ADD COLUMN notes_enabled INTEGER NOT NULL DEFAULT 0"
            )
        if agent_cols and "notes_next_number" not in agent_cols:
            await conn.execute(
                "ALTER TABLE agents ADD COLUMN notes_next_number INTEGER NOT NULL DEFAULT 1"
            )
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS agent_notes ("
            "    id TEXT PRIMARY KEY,"
            "    agent_name TEXT NOT NULL REFERENCES agents(name)"
            "        ON DELETE CASCADE ON UPDATE CASCADE,"
            "    number INTEGER NOT NULL,"
            "    text TEXT NOT NULL,"
            "    untrusted INTEGER NOT NULL DEFAULT 0,"
            "    untrusted_sources TEXT NOT NULL DEFAULT '[]',"
            "    origin_kind TEXT NOT NULL CHECK (origin_kind IN ('web', 'connector', 'other')),"
            "    origin_session_id TEXT,"
            "    origin_label TEXT,"
            "    origin_platform TEXT,"
            "    origin_peer_id TEXT,"
            "    origin_peer_name TEXT,"
            "    created_at TEXT NOT NULL,"
            "    updated_at TEXT NOT NULL,"
            "    updated_by TEXT NOT NULL CHECK (updated_by IN ('agent', 'operator'))"
            ")"
        )
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_notes_agent_number "
            "ON agent_notes (agent_name, number)"
        )
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (43,))
        await conn.commit()
        version = 43

    if version < 44:
        # Sortie 03 (DD8) — rebuild llm_providers so the ``type`` CHECK admits
        # 'anthropic-plan-token'. The v33 ceremony, except that v44 copies
        # EVERY column including ``secrets`` (the encrypted OAuth token set
        # must survive byte-for-byte). Idempotent: DROP ... IF EXISTS prelude,
        # schema_version row last. Skipped when the table is absent.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_providers'"
        ) as cursor:
            llm_providers_present = (await cursor.fetchone()) is not None
        if llm_providers_present:
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
    secrets TEXT NOT NULL DEFAULT '{{}}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO llm_providers_new
    (id, name, type, base_url, api_key, config, secrets, created_at, updated_at)
    SELECT id, name, type, base_url, api_key, config, secrets, created_at, updated_at
    FROM llm_providers;

DROP TABLE llm_providers;
ALTER TABLE llm_providers_new RENAME TO llm_providers;

PRAGMA foreign_keys=ON;
""")
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (44,))
        await conn.commit()
        version = 44

    if version < 45:
        # Mission 33 Flight 1 (DD1) — operator routines. Two tables, both
        # idempotent (CREATE ... IF NOT EXISTS). Any future agent-keyed table
        # must declare ON UPDATE CASCADE too, so a rename carries it.
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS agent_routines ("
            "    id TEXT PRIMARY KEY,"
            "    agent_name TEXT NOT NULL REFERENCES agents(name)"
            "        ON DELETE CASCADE ON UPDATE CASCADE,"
            "    name TEXT NOT NULL,"
            "    prompt TEXT NOT NULL,"
            "    schedule TEXT NOT NULL,"
            "    enabled INTEGER NOT NULL DEFAULT 1,"
            "    finished_at TEXT,"
            "    target_kind TEXT NOT NULL CHECK (target_kind IN ('chat', 'new', 'own')),"
            "    target_session_id TEXT,"
            "    target_platform TEXT,"
            "    target_connector_id TEXT,"
            "    target_channel_id TEXT,"
            "    target_thread_id TEXT,"
            "    target_peer_id TEXT,"
            "    next_run_at TEXT,"
            "    anchor_at TEXT,"
            "    created_by TEXT NOT NULL DEFAULT 'operator'"
            "        CHECK (created_by IN ('operator', 'agent')),"
            "    created_at TEXT NOT NULL,"
            "    updated_at TEXT NOT NULL,"
            "    UNIQUE (agent_name, name COLLATE NOCASE)"
            ")"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_routines_due "
            "ON agent_routines (enabled, next_run_at)"
        )
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS agent_routine_runs ("
            "    id TEXT PRIMARY KEY,"
            "    routine_id TEXT NOT NULL REFERENCES agent_routines(id) ON DELETE CASCADE,"
            "    trigger_kind TEXT NOT NULL"
            "        CHECK (trigger_kind IN ('schedule', 'catch_up', 'manual')),"
            "    outcome TEXT NOT NULL CHECK (outcome IN "
            "        ('running', 'ok', 'failed', 'skipped', 'missed', 'interrupted', 'stopped')),"
            "    reason TEXT,"
            "    due_at TEXT,"
            "    started_at TEXT,"
            "    finished_at TEXT,"
            "    session_id TEXT,"
            "    new_chat INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_routine_runs_routine "
            "ON agent_routine_runs (routine_id, started_at DESC)"
        )
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (45,))
        await conn.commit()
        version = 45

    if version < 46:
        # Mission 33 Flight 2 (DD4) — agents schedule their own routines. `agents`
        # gains the two operator-owned Routines switches (never in `save`'s upsert);
        # `agent_routines` gains the untrusted flag; `agent_routine_proposals` holds
        # every agent routine change (applied, pending, dismissed, superseded).
        # Every ALTER is guarded by PRAGMA table_info; the table and index are idempotent.
        async with conn.execute("PRAGMA table_info(agents)") as cursor:
            agent_cols = {row[1] for row in await cursor.fetchall()}
        if agent_cols and "routines_self_config_enabled" not in agent_cols:
            await conn.execute(
                "ALTER TABLE agents ADD COLUMN "
                "routines_self_config_enabled INTEGER NOT NULL DEFAULT 0"
            )
        if agent_cols and "routines_require_approval" not in agent_cols:
            await conn.execute(
                "ALTER TABLE agents ADD COLUMN routines_require_approval INTEGER NOT NULL DEFAULT 1"
            )
        async with conn.execute("PRAGMA table_info(agent_routines)") as cursor:
            routine_cols = {row[1] for row in await cursor.fetchall()}
        if routine_cols and "untrusted" not in routine_cols:
            await conn.execute(
                "ALTER TABLE agent_routines ADD COLUMN untrusted INTEGER NOT NULL DEFAULT 0"
            )
        if routine_cols and "untrusted_sources" not in routine_cols:
            await conn.execute("ALTER TABLE agent_routines ADD COLUMN untrusted_sources TEXT")
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS agent_routine_proposals ("
            "    id TEXT PRIMARY KEY,"
            "    agent_name TEXT NOT NULL REFERENCES agents(name)"
            "        ON DELETE CASCADE ON UPDATE CASCADE,"
            "    routine_id TEXT REFERENCES agent_routines(id) ON DELETE SET NULL,"
            "    routine_name TEXT NOT NULL,"
            "    action TEXT NOT NULL CHECK (action IN ('create', 'update', 'delete')),"
            "    payload TEXT NOT NULL,"
            "    base TEXT,"
            "    status TEXT NOT NULL"
            "        CHECK (status IN ('applied', 'pending', 'dismissed', 'superseded')),"
            "    untrusted INTEGER NOT NULL DEFAULT 0,"
            "    untrusted_sources TEXT,"
            "    session_id TEXT,"
            "    created_at TEXT NOT NULL,"
            "    resolved_at TEXT"
            ")"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_routine_proposals_agent_status "
            "ON agent_routine_proposals (agent_name, status)"
        )
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (46,))
        await conn.commit()
        version = 46

    if version < 47:
        # Mission 33 Flight 3 (DD11) — skipped runs carry a stable reason code, and a run
        # of consecutive "still running" skips collapses into one row counting `repeats`.
        # Guarded ALTERs; existing rows are not backfilled.
        async with conn.execute("PRAGMA table_info(agent_routine_runs)") as cursor:
            run_cols = {row[1] for row in await cursor.fetchall()}
        if run_cols and "repeats" not in run_cols:
            await conn.execute(
                "ALTER TABLE agent_routine_runs ADD COLUMN repeats INTEGER NOT NULL DEFAULT 1"
            )
        if run_cols and "reason_code" not in run_cols:
            await conn.execute("ALTER TABLE agent_routine_runs ADD COLUMN reason_code TEXT")
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (47,))
        await conn.commit()
        version = 47

    if version < 48:
        # Mission 33 Flight 3 (DD6) — every stored routine schedule, and the schedules in
        # every proposal's payload and base, are rewritten to the calendar recurrence
        # shape by the frozen converter above. `next_run_at` is not recomputed. A schedule
        # that cannot be read is left, its routine is turned off and one guarded
        # `upgrade_failed` run row says so. Idempotent: canonical schedules are skipped.
        await _v48_rewrite_routines(conn)
        await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (48,))
        await conn.commit()
        version = 48
