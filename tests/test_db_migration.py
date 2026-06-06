"""Tests for JSON → SQLite migration."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest

from the_one.agent.config import AgentConfig
from the_one.db.migration import migrate_json_to_sqlite
from the_one.db.repositories import SQLiteAgentStore
from the_one.db.schema import CURRENT_VERSION, ensure_schema


@pytest.fixture
async def setup(tmp_path):
    """Set up a SQLite connection and a JSON agents directory."""
    db_path = tmp_path / "test.db"
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    store = SQLiteAgentStore(conn)

    with patch("the_one.db.migration.settings") as mock_settings:
        mock_settings.agents_dir = agents_dir
        yield store, agents_dir

    await conn.close()


def _write_json_config(agents_dir: Path, name: str, **overrides) -> None:
    cfg = AgentConfig(name=name, **overrides)
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.json").write_text(json.dumps(cfg.model_dump(), indent=2))


class TestMigration:
    async def test_migrates_json_configs(self, setup) -> None:
        store, agents_dir = setup
        _write_json_config(agents_dir, "agent-a", description="Agent A")
        _write_json_config(agents_dir, "agent-b", llm_model="gpt-4o")

        count = await migrate_json_to_sqlite(store)
        assert count == 2

        a = await store.load("agent-a")
        assert a.description == "Agent A"
        b = await store.load("agent-b")
        assert b.llm_model == "gpt-4o"

    async def test_skips_existing(self, setup) -> None:
        store, agents_dir = setup
        await store.save(AgentConfig(name="existing", description="DB version"))
        _write_json_config(agents_dir, "existing", description="JSON version")

        count = await migrate_json_to_sqlite(store)
        assert count == 0

        loaded = await store.load("existing")
        assert loaded.description == "DB version"

    async def test_no_json_files(self, setup) -> None:
        store, _ = setup
        count = await migrate_json_to_sqlite(store)
        assert count == 0

    async def test_preserves_all_fields(self, setup) -> None:
        store, agents_dir = setup
        _write_json_config(
            agents_dir,
            "full",
            description="Full config",
            provider_config_id=None,
            llm_model="claude-sonnet-4-6",
            system_prompt="Be helpful",
            enabled_tools=["shell", "read_file"],
            disabled_tools=["shell"],
            max_iterations=10,
            kb_ids=["kb1"],
            mcp_source_ids=["mcp1"],
        )
        count = await migrate_json_to_sqlite(store)
        assert count == 1

        loaded = await store.load("full")
        assert loaded.provider_config_id is None
        assert loaded.enabled_tools == ["shell", "read_file"]
        assert loaded.kb_ids == ["kb1"]
        assert loaded.max_iterations == 10


class TestSchemaV7:
    """Tests for the v7 migration that strips removed tool names."""

    async def test_v7_strips_removed_tool_names(self, tmp_path) -> None:
        """v6 → v7: removed tool names are stripped; NULL whitelist is preserved."""
        db_path = tmp_path / "v7-strip.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Migrate fresh DB straight to current (v7).
        await ensure_schema(conn)

        # Seed four v6-shaped agent rows that simulate legacy data.
        # The v7 strip is a row-content migration, not a DDL change, so
        # column types are identical between v6 and v7. Inserting these
        # rows post-v7-migration and then rewinding schema_version to 6
        # exercises the exact same code path the migration would hit
        # against a real legacy DB.
        await conn.execute(
            "INSERT INTO agents (name, enabled_tools, disabled_tools) VALUES (?, ?, ?)",
            (
                "mixed",
                json.dumps(["self_deploy", "git", "memory", "shell"]),
                json.dumps(["self_deploy", "shell"]),
            ),
        )
        await conn.execute(
            "INSERT INTO agents (name, enabled_tools, disabled_tools) VALUES (?, ?, ?)",
            ("nullwhitelist", None, json.dumps(["git"])),
        )
        await conn.execute(
            "INSERT INTO agents (name, enabled_tools, disabled_tools) VALUES (?, ?, ?)",
            (
                "removedonly",
                json.dumps(["self_deploy"]),
                json.dumps([]),
            ),
        )
        # All-kept row — proves the migration doesn't over-strip.
        await conn.execute(
            "INSERT INTO agents (name, enabled_tools, disabled_tools) VALUES (?, ?, ?)",
            (
                "allkept",
                json.dumps(["shell", "read_file", "write_file"]),
                json.dumps(["python_exec"]),
            ),
        )
        # Rewind schema_version so ensure_schema sees v6 and reruns v7.
        # (Delete v7+ markers; _get_version returns MAX(version), so we
        # must clear every row above the rewind target — v8 was added in
        # F2/L2 and lives above v7.)
        await conn.execute("DELETE FROM schema_version WHERE version >= 7")
        await conn.commit()

        # Run the v7 migration.
        await ensure_schema(conn)

        # Assertion 1: mixed row — kept names survive, removed names gone.
        async with conn.execute(
            "SELECT enabled_tools, disabled_tools FROM agents WHERE name = 'mixed'"
        ) as cur:
            row = await cur.fetchone()
        assert json.loads(row["enabled_tools"]) == ["shell"]
        assert json.loads(row["disabled_tools"]) == ["shell"]

        # Assertion 2: NULL whitelist preserved as NULL (not coerced to []).
        async with conn.execute(
            "SELECT enabled_tools, disabled_tools FROM agents WHERE name = 'nullwhitelist'"
        ) as cur:
            row = await cur.fetchone()
        assert row["enabled_tools"] is None
        assert json.loads(row["disabled_tools"]) == []

        # Assertion 3: whitelist of only removed names becomes empty list
        # (locked-down — never widened to NULL).
        async with conn.execute(
            "SELECT enabled_tools, disabled_tools FROM agents WHERE name = 'removedonly'"
        ) as cur:
            row = await cur.fetchone()
        assert json.loads(row["enabled_tools"]) == []
        assert json.loads(row["disabled_tools"]) == []

        # Assertion 4: all-kept row — pass-through (proves no over-strip).
        async with conn.execute(
            "SELECT enabled_tools, disabled_tools FROM agents WHERE name = 'allkept'"
        ) as cur:
            row = await cur.fetchone()
        assert json.loads(row["enabled_tools"]) == ["shell", "read_file", "write_file"]
        assert json.loads(row["disabled_tools"]) == ["python_exec"]

        # Assertion 5: schema_version reaches CURRENT_VERSION (was 7 at
        # design time; advanced to 8 in F2/L2 — the v7 strip ran AND the
        # later migrations followed).
        from the_one.db.schema import CURRENT_VERSION

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        assert row[0] == CURRENT_VERSION

        await conn.close()


class TestSchemaV8:
    """Tests for the v8 migration that adds tool_configs + agents.tool_overrides."""

    async def test_v8_fresh_db_includes_tool_configs_and_tool_overrides(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v8 surfaces exist.

        Acts as the regression-loud-fail guard: if a future bump to
        CURRENT_VERSION = 9 silently drops the v8 block, this test
        will fail with explicit messages naming both `tool_configs`
        and `tool_overrides`.
        """
        from the_one.db.schema import CURRENT_VERSION

        db_path = tmp_path / "v8-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        # CURRENT_VERSION assertion — pins that v8 surfaces are present at
        # the current version. v11 added agents.mcp_overrides (M07 F06 L01);
        # v12 extended llm_providers.type CHECK to allow 'openrouter';
        # v13 added connector_accounts (M10 F01 L01); v14 added
        # connector_accounts.name (M10 F01 L02); v15 added
        # connector_accounts.idle_timeout_seconds (M10 F02 L02); v16 added
        # chat_sessions external-key columns +
        # connector_accounts.session_continuation_seconds (M10 F03 L01);
        # v17 added agents.connector_account_ids (M10 F04 L05 — closes the
        # F4 L1/L4 monkeypatch workaround for the AgentConfig field's
        # missing DB persistence);
        # v18 added agents.connector_acls (M10 F06 L1c — per-agent ACL
        # persistence; F4 debrief rec #1 atomic shape);
        # v19 added CHECK (type IN ('discord', 'stub')) on
        # connector_accounts.type via the table-rename ceremony (M10 F08
        # L02 — first real connector type registered);
        # v20 added agents.connector_always_listen (M11 F07 L06 —
        # per-agent always_listen toggle persistence);
        # v21 added pending_approvals table (M11 F09 L02 —
        # Discord-native peer-approval storage);
        # v22 added dm_admission to connector_accounts.config.allowlist
        # via row-rewrite (M11 F10 L01 — DM admission axis split);
        # v23 renamed connector_accounts → connectors + dependent FK
        # column renames (M11 F11 L01 — connector terminology rename);
        # v24 introduced structured-tuple storage for allowlist
        # channels + roles + per-peer dm_allowed + renamed the
        # dm_admission Literal value "allowlisted-peers-only" →
        # "admin-approved" + renamed the pending_approvals index
        # (M11 F12 L03 — hierarchical allowlist axes).
        # v25 deletes orphan null-``guild_id`` channel/role entries
        # and tightens the Pydantic validator to reject null guild_id
        # going forward (M11 F12 L05 — hierarchical Server-as-parent
        # UI alignment).
        # v26 adds inference_provider_config_id + inference_model keys to
        # every connector.config and strips per-agent peers[*].dm_allowed
        # (M11 F13 L02 — per-connector inference LLM + F12 footgun
        # retirement).
        # v27 unifies guild scoping onto config.allowlist.guilds: folds
        # any top-level config.guilds ("Scope to servers") into
        # config.allowlist.guilds and removes the top-level key
        # (M11 F14 L02 — slash-sync reads allowlist.guilds).
        assert CURRENT_VERSION >= 27, (
            "CURRENT_VERSION must be >= 27 after the M11 F14 L02 — "
            "guild-scoping unification onto config.allowlist.guilds "
            f"v27 migration (got {CURRENT_VERSION})"
        )
        # M11 F17 L8 (Leg D): v28 drops dm_allowed from account-scope
        # peers; CURRENT_VERSION is now 28.
        assert CURRENT_VERSION >= 28, (
            "CURRENT_VERSION must be >= 28 after the M11 F17 L8 (Leg D) "
            f"dm-allowlist-simplify v28 migration (got {CURRENT_VERSION})"
        )
        # M11 F17 L10 (Leg F): v29 adds replay-context columns to
        # pending_approvals; CURRENT_VERSION is now at least 29.
        assert CURRENT_VERSION >= 29, (
            "CURRENT_VERSION must be >= 29 after the M11 F17 L10 (Leg F) "
            f"respond-on-approval v29 migration (got {CURRENT_VERSION})"
        )

        # tool_configs table must exist.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tool_configs'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None, (
            "v8 migration missing: table `tool_configs` does not exist after "
            "ensure_schema on a fresh DB"
        )

        # agents.tool_overrides column must exist, be TEXT, nullable, no DEFAULT.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            agent_cols = {r["name"]: r for r in await cur.fetchall()}
        assert "tool_overrides" in agent_cols, (
            "v8 migration missing: column `tool_overrides` does not exist on "
            "`agents` after ensure_schema on a fresh DB"
        )
        col = agent_cols["tool_overrides"]
        assert col["type"] == "TEXT", col["type"]
        # notnull == 0 means the column is nullable.
        assert col["notnull"] == 0, col["notnull"]
        # No explicit DEFAULT clause — dflt_value must be Python None,
        # not the literal string "NULL".
        assert col["dflt_value"] is None, col["dflt_value"]

        # tool_configs must be empty on a fresh DB.
        async with conn.execute("SELECT * FROM tool_configs") as cur:
            rows = await cur.fetchall()
        assert rows == [], rows

        # schema_version row for v8 exists; the head pointer lands at
        # CURRENT_VERSION (which advances past 8 in later legs — the
        # invariant this test guards is "v8 migration ran", not "no
        # later migration ran").
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 8 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v8_migration_on_v7_fixture_db_preserves_existing_rows(self, tmp_path) -> None:
        """v7 → v8: existing agent rows survive with tool_overrides=NULL,
        tool_configs is created empty, schema_version lands at 8."""
        db_path = tmp_path / "v8-from-v7.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Migrate fresh DB straight to current.
        await ensure_schema(conn)

        # Seed a v7-shaped agent row with enabled_tools set.
        await conn.execute(
            "INSERT INTO agents (name, enabled_tools, disabled_tools) VALUES (?, ?, ?)",
            ("seed", json.dumps(["shell", "read_file"]), json.dumps([])),
        )

        # Rewind schema_version so ensure_schema sees v7 and reruns v8
        # (and any later migrations layered on top — delete >= 8 so the
        # MAX() head pointer drops to 7 and the migration loop re-enters
        # the v8 block).
        await conn.execute("DELETE FROM schema_version WHERE version >= 8")
        await conn.commit()

        # Re-run the v8 migration on a v7-shaped DB. Note: the seeded
        # row pre-existed because the fresh ensure_schema already added
        # the tool_overrides column; we still exercise the migration's
        # idempotent guard (PRAGMA table_info skips the ALTER) and the
        # CREATE TABLE IF NOT EXISTS path.
        await ensure_schema(conn)

        # Assertion (a): the agents row survives with tool_overrides=NULL.
        async with conn.execute(
            "SELECT name, enabled_tools, disabled_tools, tool_overrides "
            "FROM agents WHERE name = 'seed'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert json.loads(row["enabled_tools"]) == ["shell", "read_file"]
        assert json.loads(row["disabled_tools"]) == []
        assert row["tool_overrides"] is None

        # Assertion (b): tool_configs is present and empty.
        async with conn.execute("SELECT * FROM tool_configs") as cur:
            rows = await cur.fetchall()
        assert rows == []

        # Assertion (c): v8 ran (schema_version contains 8). The head
        # pointer is CURRENT_VERSION since later legs may have added
        # subsequent migrations on top.
        from the_one.db.schema import CURRENT_VERSION

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 8 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v8_migration_is_idempotent(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, no duplicate schema_version rows for v8."""
        db_path = tmp_path / "v8-idempotent.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        # Exactly one schema_version row for v8.
        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 8") as cur:
            row = await cur.fetchone()
        assert row[0] == 1

        # Surfaces still present after the second call.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "tool_overrides" in cols
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tool_configs'"
        ) as cur:
            assert (await cur.fetchone()) is not None

        await conn.close()

    async def test_v6_to_v7_to_v8_chained_migration(self, tmp_path) -> None:
        """v6 → v7 → v8: rewinding schema_version to 6 forces both v7
        (row-content strip) and v8 (DDL) to apply in sequence; agents
        land in a sensible state, both 7 and 8 rows are present, and
        schema_version is 8."""
        db_path = tmp_path / "v8-chain.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        # Seed an agent row with a removed tool name in enabled_tools so
        # the v7 strip has something to do.
        await conn.execute(
            "INSERT INTO agents (name, enabled_tools, disabled_tools) VALUES (?, ?, ?)",
            (
                "chained",
                json.dumps(["self_deploy", "shell"]),
                json.dumps(["git", "read_file"]),
            ),
        )

        # Rewind to 6 (delete both the 7 and 8 markers).
        await conn.execute("DELETE FROM schema_version WHERE version >= 7")
        await conn.commit()

        await ensure_schema(conn)

        # Assertion (a): the v7 strip ran — removed names gone, kept ones
        # remain.
        async with conn.execute(
            "SELECT enabled_tools, disabled_tools, tool_overrides "
            "FROM agents WHERE name = 'chained'"
        ) as cur:
            row = await cur.fetchone()
        assert json.loads(row["enabled_tools"]) == ["shell"]
        assert json.loads(row["disabled_tools"]) == ["read_file"]

        # Assertion (b): the v8 DDL ran — tool_overrides column exists
        # and the seeded row has NULL (no overrides set).
        assert row["tool_overrides"] is None
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tool_configs'"
        ) as cur:
            assert (await cur.fetchone()) is not None

        # Assertion (c): both 7 and 8 are present in schema_version,
        # MAX(version) is CURRENT_VERSION (later legs may layer more
        # migrations on top; the v7→v8 chain still applies cleanly).
        from the_one.db.schema import CURRENT_VERSION

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 7 in versions, versions
        assert 8 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()


class TestSchemaV9:
    """Tests for the v9 migration that adds tool_configs.enabled."""

    async def test_v9_fresh_db_has_enabled_column_with_default_1(self, tmp_path) -> None:
        from the_one.db.schema import CURRENT_VERSION

        db_path = tmp_path / "v9-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Pin that v9 surfaces are present at the current version (the v9
        # block itself was not removed when later migrations bumped the
        # number).
        assert CURRENT_VERSION >= 9, CURRENT_VERSION

        async with conn.execute("PRAGMA table_info(tool_configs)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        assert "enabled" in cols
        col = cols["enabled"]
        assert col["type"] == "INTEGER", col["type"]
        assert col["notnull"] == 1, col["notnull"]
        # SQLite stores the literal text of the DEFAULT clause.
        # Stringify to avoid aiosqlite-version-dependent type quirks.
        assert str(col["dflt_value"]) == "1", col["dflt_value"]

        # Behavioural cross-check: an INSERT that omits `enabled`
        # lands on 1 via the column DEFAULT. The PRAGMA assertion
        # is the schema; this is the contract.
        await conn.execute(
            "INSERT INTO tool_configs (name, config) VALUES (?, ?)",
            ("default-check", json.dumps({})),
        )
        await conn.commit()
        async with conn.execute(
            "SELECT enabled FROM tool_configs WHERE name = 'default-check'"
        ) as cur:
            r = await cur.fetchone()
        assert r["enabled"] == 1, r["enabled"]

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        assert row[0] == CURRENT_VERSION  # ensure_schema advances to CURRENT_VERSION

        await conn.close()

    async def test_v9_migration_on_v8_fixture_db_preserves_existing_rows(self, tmp_path) -> None:
        from the_one.db.schema import CURRENT_VERSION

        db_path = tmp_path / "v9-from-v8.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Seed a tool_configs row directly (4-column-shaped INSERT
        # would have been the v8 form; on v9 the column default
        # supplies enabled=1 for an INSERT that omits it).
        await conn.execute(
            "INSERT INTO tool_configs (name, config) VALUES (?, ?)",
            ("preexisting", json.dumps({"timeout_sec_default": 30.0})),
        )

        # Rewind to v8.
        await conn.execute("DELETE FROM schema_version WHERE version >= 9")
        await conn.commit()

        # Re-run — idempotent guard skips ALTER, INSERT OR IGNORE skips dup.
        await ensure_schema(conn)

        async with conn.execute(
            "SELECT name, config, enabled FROM tool_configs WHERE name = 'preexisting'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert json.loads(row["config"]) == {"timeout_sec_default": 30.0}
        assert row["enabled"] == 1

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        assert row[0] == CURRENT_VERSION  # ensure_schema advances to CURRENT_VERSION

        await conn.close()

    async def test_v9_migration_is_idempotent(self, tmp_path) -> None:
        db_path = tmp_path / "v9-idempotent.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 9") as cur:
            row = await cur.fetchone()
        assert row[0] == 1

        async with conn.execute("PRAGMA table_info(tool_configs)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "enabled" in cols

        await conn.close()

    async def test_v8_to_v9_chained_migration(self, tmp_path) -> None:
        """Rewind to v8, seed a v8-shaped row (no enabled column at
        insert time logically — the column default supplies 1), then
        run the v9 ADD COLUMN. The seeded row must have enabled=1."""
        db_path = tmp_path / "v9-chain.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        await conn.execute(
            "INSERT INTO tool_configs (name, config) VALUES (?, ?)",
            ("chained", json.dumps({})),
        )
        await conn.execute("DELETE FROM schema_version WHERE version >= 9")
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute("SELECT enabled FROM tool_configs WHERE name = 'chained'") as cur:
            row = await cur.fetchone()
        assert row["enabled"] == 1

        await conn.close()


class TestSchemaV10:
    """Tests for the v10 migration that rebuilds mcp_sources with a new CHECK
    constraint (type IN ('stdio', 'streamable-http')) and a secrets column."""

    async def test_v10_fresh_db_has_secrets_column_and_streamable_http_check(
        self, tmp_path
    ) -> None:
        db_path = tmp_path / "v10-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        async with conn.execute("PRAGMA table_info(mcp_sources)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        assert "secrets" in cols
        col = cols["secrets"]
        assert col["type"] == "TEXT", col["type"]

        # Behavioural cross-check: INSERT with type='streamable-http' and no
        # secrets value succeeds and lands secrets='{}' via the column DEFAULT.
        await conn.execute(
            "INSERT INTO mcp_sources (id, name, type, config) VALUES (?, ?, ?, ?)",
            ("sh-1", "StreamableHTTP", "streamable-http", "{}"),
        )
        await conn.commit()
        async with conn.execute("SELECT secrets FROM mcp_sources WHERE id = 'sh-1'") as cur:
            r = await cur.fetchone()
        assert r["secrets"] == "{}", r["secrets"]

        # Behavioural cross-check: INSERT with type='sse' raises IntegrityError.
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO mcp_sources (id, name, type, config) VALUES (?, ?, ?, ?)",
                ("sse-1", "OldSSE", "sse", "{}"),
            )
            await conn.commit()

        # schema_version reaches v10 (further migrations may bump higher).
        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 10") as cur:
            row = await cur.fetchone()
        assert row[0] == 1

        await conn.close()

    async def test_v10_migration_on_v9_fixture_db_preserves_existing_rows(self, tmp_path) -> None:
        db_path = tmp_path / "v10-from-v9.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Programmatic rewind to v9 state: drop v10 mcp_sources, recreate with
        # the v1 CHECK shape (type IN ('stdio', 'sse')), remove v10+ version
        # rows so MAX(version) drops to 9 and ensure_schema re-enters the v10
        # block. (Mirrors the v8 precedent's `>= 8` filter — using `= 10`
        # leaves v11+ intact and ensure_schema skips v10.)
        await conn.execute("DROP TABLE mcp_sources")
        await conn.execute("""\
CREATE TABLE mcp_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('stdio', 'sse')),
    config TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)""")
        await conn.execute("DELETE FROM schema_version WHERE version >= 10")
        await conn.commit()

        # Seed two rows: one 'sse' with non-empty config, one 'stdio' with non-empty config.
        await conn.execute(
            "INSERT INTO mcp_sources (id, name, type, config, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                "sse-row",
                "SSE Source",
                "sse",
                '{"url": "http://example.com/sse"}',
                "2025-01-01T00:00:00",
                "2025-01-02T00:00:00",
            ),
        )
        await conn.execute(
            "INSERT INTO mcp_sources (id, name, type, config, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                "stdio-row",
                "STDIO Source",
                "stdio",
                '{"command": "python"}',
                "2025-01-03T00:00:00",
                "2025-01-04T00:00:00",
            ),
        )
        await conn.commit()

        # Re-run ensure_schema — should apply v10.
        await ensure_schema(conn)

        # Assert 'sse' row migrated to 'streamable-http'.
        async with conn.execute(
            "SELECT id, name, type, config, secrets, created_at, updated_at"
            " FROM mcp_sources WHERE id = 'sse-row'"
        ) as cur:
            sse = await cur.fetchone()
        assert sse is not None
        assert sse["type"] == "streamable-http", sse["type"]
        assert sse["secrets"] == "{}", sse["secrets"]
        assert sse["name"] == "SSE Source"
        assert json.loads(sse["config"]) == {"url": "http://example.com/sse"}
        assert sse["created_at"] == "2025-01-01T00:00:00"
        assert sse["updated_at"] == "2025-01-02T00:00:00"

        # Assert 'stdio' row type is unchanged.
        async with conn.execute(
            "SELECT id, name, type, config, secrets, created_at, updated_at"
            " FROM mcp_sources WHERE id = 'stdio-row'"
        ) as cur:
            stdio = await cur.fetchone()
        assert stdio is not None
        assert stdio["type"] == "stdio", stdio["type"]
        assert stdio["secrets"] == "{}", stdio["secrets"]
        assert stdio["name"] == "STDIO Source"
        assert json.loads(stdio["config"]) == {"command": "python"}
        assert stdio["created_at"] == "2025-01-03T00:00:00"
        assert stdio["updated_at"] == "2025-01-04T00:00:00"

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        # ensure_schema re-applies v10 and any later migrations (v11
        # mcp_overrides, v12 openrouter) since the rewind dropped them.
        assert row[0] == CURRENT_VERSION

        await conn.close()

    async def test_v10_migration_is_idempotent(self, tmp_path) -> None:
        db_path = tmp_path / "v10-idempotent.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 10") as cur:
            row = await cur.fetchone()
        assert row[0] == 1

        async with conn.execute("PRAGMA table_info(mcp_sources)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "secrets" in cols

        await conn.close()

    async def test_v9_to_v10_chained_migration(self, tmp_path) -> None:
        """Rewind to v9 with an 'sse' row seeded, then run v10. The seeded
        row must emerge as type='streamable-http' with secrets='{}'."""
        db_path = tmp_path / "v10-chain.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Rewind to v9 state. Delete `>= 10` so MAX(version) drops to 9
        # and ensure_schema re-enters the v10 block (using `= 10` would
        # leave v11+ intact and the loop would skip v10).
        await conn.execute("DROP TABLE mcp_sources")
        await conn.execute("""\
CREATE TABLE mcp_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('stdio', 'sse')),
    config TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)""")
        await conn.execute("DELETE FROM schema_version WHERE version >= 10")
        await conn.commit()

        # Seed an 'sse' row.
        await conn.execute(
            "INSERT INTO mcp_sources (id, name, type, config)"
            " VALUES ('seed', 'Test', 'sse', '{\"command\": \"python\"}')",
        )
        await conn.commit()

        # Re-run ensure_schema — should apply v10.
        await ensure_schema(conn)

        async with conn.execute(
            "SELECT type, secrets, config FROM mcp_sources WHERE id = 'seed'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["type"] == "streamable-http", row["type"]
        assert row["secrets"] == "{}", row["secrets"]
        assert json.loads(row["config"]) == {"command": "python"}

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        # After re-running ensure_schema all subsequent migrations should
        # have applied (v10 mcp_sources, v11 mcp_overrides, v12 openrouter).
        assert row[0] == CURRENT_VERSION

        await conn.close()


class TestSchemaV11:
    """Tests for the v11 migration that adds agents.mcp_overrides."""

    async def test_v11_fresh_db_includes_mcp_overrides_column(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v11 surfaces exist.

        Acts as the regression-loud-fail guard: if a future bump to
        CURRENT_VERSION silently drops the v11 block, this test
        will fail with an explicit message naming `mcp_overrides`.
        """
        db_path = tmp_path / "v11-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 11, CURRENT_VERSION

        # agents.mcp_overrides column must exist, be TEXT, nullable, no DEFAULT.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            agent_cols = {r["name"]: r for r in await cur.fetchall()}
        assert "mcp_overrides" in agent_cols, (
            "v11 migration missing: column `mcp_overrides` does not exist on "
            "`agents` after ensure_schema on a fresh DB"
        )
        col = agent_cols["mcp_overrides"]
        assert col["type"] == "TEXT", col["type"]
        # notnull == 0 means the column is nullable.
        assert col["notnull"] == 0, col["notnull"]
        # No explicit DEFAULT clause — dflt_value must be Python None,
        # not the literal string "NULL".
        assert col["dflt_value"] is None, col["dflt_value"]

        # schema_version row for v11 exists; the head pointer lands at
        # CURRENT_VERSION.
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 11 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v11_migration_on_v10_fixture_db_preserves_existing_rows(self, tmp_path) -> None:
        """v10 → v11: existing agent rows survive with mcp_overrides=NULL,
        tool_overrides column from v8 still present + populated, schema_version
        lands at CURRENT_VERSION."""
        db_path = tmp_path / "v11-from-v10.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Migrate fresh DB straight to current.
        await ensure_schema(conn)

        # Seed an agent row with tool_overrides set so we can verify the
        # v8 column survives the v11 migration.
        await conn.execute(
            "INSERT INTO agents (name, enabled_tools, disabled_tools, tool_overrides) "
            "VALUES (?, ?, ?, ?)",
            (
                "seed",
                json.dumps(["shell", "read_file"]),
                json.dumps([]),
                json.dumps({"shell": {"timeout": 30}}),
            ),
        )

        # Rewind schema_version so ensure_schema sees v10 and reruns v11.
        # Mirrors the v8 precedent: delete >= 11 so the MAX() head pointer
        # drops to 10 and the migration loop re-enters the v11 block.
        await conn.execute("DELETE FROM schema_version WHERE version >= 11")
        await conn.commit()

        # Re-run the v11 migration. The seeded row pre-existed because the
        # fresh ensure_schema already added the mcp_overrides column; we
        # still exercise the migration's idempotent guard (PRAGMA table_info
        # skips the ALTER) and the INSERT OR IGNORE on schema_version.
        await ensure_schema(conn)

        # Assertion (a): the agent row survives with mcp_overrides=NULL,
        # and the tool_overrides v8 column is still present + populated.
        async with conn.execute(
            "SELECT name, enabled_tools, disabled_tools, tool_overrides, mcp_overrides "
            "FROM agents WHERE name = 'seed'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert json.loads(row["enabled_tools"]) == ["shell", "read_file"]
        assert json.loads(row["disabled_tools"]) == []
        assert json.loads(row["tool_overrides"]) == {"shell": {"timeout": 30}}
        assert row["mcp_overrides"] is None

        # Assertion (b): v11 ran (schema_version contains 11). The head
        # pointer is CURRENT_VERSION.
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 11 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v11_migration_is_idempotent(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, no duplicate schema_version rows for v11."""
        db_path = tmp_path / "v11-idempotent.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        # Exactly one schema_version row for v11.
        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 11") as cur:
            row = await cur.fetchone()
        assert row[0] == 1

        # Surface still present after the second call.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "mcp_overrides" in cols

        await conn.close()


class TestMigrationV12:
    """v11→v12: extend llm_providers.type CHECK to include 'openrouter'."""

    async def test_v12_accepts_openrouter_type(self, tmp_path) -> None:
        """A fresh schema (CURRENT_VERSION>=12) must accept openrouter rows."""
        db_path = tmp_path / "v11.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        await conn.execute(
            "INSERT INTO llm_providers (id, name, type, base_url) VALUES (?, ?, ?, ?)",
            ("p1", "OpenRouter", "openrouter", "https://openrouter.ai/api/v1"),
        )
        await conn.commit()

        async with conn.execute("SELECT type FROM llm_providers WHERE id = ?", ("p1",)) as cursor:
            row = await cursor.fetchone()
        assert row["type"] == "openrouter"
        await conn.close()

    async def test_v12_idempotent_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second time."""
        from the_one.db.schema import CURRENT_VERSION

        db_path = tmp_path / "idem.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call must not raise

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cursor:
            row = await cursor.fetchone()
        assert row[0] == CURRENT_VERSION
        await conn.close()

    async def test_v12_real_v11_to_v12_upgrade(self, tmp_path) -> None:
        """Bootstrap an actual pre-v12 schema (5-type CHECK on
        llm_providers, no openrouter), seed a provider + agent FK, run
        ensure_schema, and verify:

        - existing rows + FK references survive the table rebuild
        - the new CHECK constraint accepts ``openrouter``
        - the new CHECK constraint still rejects bogus types
        - schema_version reaches CURRENT_VERSION
        """
        from the_one.db.schema import CURRENT_VERSION

        db_path = tmp_path / "v11_to_v12.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build a real pre-v12 schema. The only difference from v12
        # in the llm_providers table is the CHECK constraint — pre-v12
        # accepts 5 types, v12 accepts 6. The hand-built agents table
        # already carries `mcp_overrides` so v11 is a no-op (PRAGMA guard).
        await conn.executescript("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE llm_providers (
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
            CREATE TABLE agents (
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
                mcp_overrides TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE mcp_sources (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('stdio', 'streamable-http')),
                config TEXT DEFAULT '{}',
                secrets TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE chat_sessions (
                id TEXT PRIMARY KEY,
                agent_name TEXT,
                title TEXT DEFAULT 'New chat',
                messages TEXT DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        for v in range(1, 12):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))

        # Seed pre-migration data: provider + agent that references it.
        await conn.execute(
            "INSERT INTO llm_providers (id, name, type, base_url) VALUES (?, ?, ?, ?)",
            ("v11-prov", "Legacy", "anthropic", "https://api.anthropic.com"),
        )
        await conn.execute(
            "INSERT INTO agents (name, provider_config_id) VALUES (?, ?)",
            ("legacy-agent", "v11-prov"),
        )
        await conn.commit()

        # Pre-condition: pre-v12 CHECK rejects 'openrouter'.
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO llm_providers (id, name, type, base_url) VALUES (?, ?, ?, ?)",
                ("rejected", "x", "openrouter", "https://openrouter.ai/api/v1"),
            )
        await conn.rollback()

        # Run the migration. ensure_schema needs ALL prereq schema-version
        # objects to exist; we already created mcp_sources/agents above so
        # v10/v11 are no-ops and v12 runs cleanly.
        await ensure_schema(conn)

        # Existing row survived the rebuild.
        async with conn.execute(
            "SELECT id, name, type FROM llm_providers WHERE id = ?", ("v11-prov",)
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None and row["type"] == "anthropic"

        # FK reference survived.
        async with conn.execute(
            "SELECT name, provider_config_id FROM agents WHERE name = ?", ("legacy-agent",)
        ) as cursor:
            agent = await cursor.fetchone()
        assert agent is not None and agent["provider_config_id"] == "v11-prov"

        # Post-condition: the new CHECK accepts openrouter.
        await conn.execute(
            "INSERT INTO llm_providers (id, name, type, base_url) VALUES (?, ?, ?, ?)",
            ("p-or", "OR", "openrouter", "https://openrouter.ai/api/v1"),
        )
        await conn.commit()

        # ...and still rejects bogus types.
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO llm_providers (id, name, type, base_url) VALUES (?, ?, ?, ?)",
                ("evil", "x", "not-a-real-type", "http://x"),
            )
        await conn.rollback()

        # schema_version reached CURRENT_VERSION.
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cursor:
            row = await cursor.fetchone()
        assert row[0] == CURRENT_VERSION

        await conn.close()

    async def test_v12_recovers_from_partial_apply_with_orphan_temp_table(self, tmp_path) -> None:
        """Defensive ``DROP TABLE IF EXISTS llm_providers_new`` prelude:
        if a previous run crashed AFTER the temp table was created but
        BEFORE the rename, re-running ensure_schema must succeed (without
        the prelude, ``CREATE TABLE llm_providers_new`` would fail with
        'table already exists')."""
        from the_one.db.schema import CURRENT_VERSION

        db_path = tmp_path / "partial.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        # Rewind schema_version to BEFORE 12 so the v12 block re-enters on
        # the next ensure_schema call. Mirrors the v11 rewind pattern:
        # delete every row >= 12 so MAX() drops to 11 and the migration
        # loop replays v12 (the block we're testing the orphan-recovery
        # prelude on) and every later block (v13+) idempotently.
        await conn.execute("DELETE FROM schema_version WHERE version >= 12")
        # Synthesize the orphan temp table left by a crashed prior run.
        await conn.execute("CREATE TABLE llm_providers_new (id TEXT, junk TEXT)")
        await conn.commit()

        # Re-run must complete cleanly thanks to DROP IF EXISTS prelude.
        await ensure_schema(conn)

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cursor:
            row = await cursor.fetchone()
        assert row[0] == CURRENT_VERSION
        # llm_providers_new is fully consumed (renamed); the orphan cleared.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_providers_new'"
        ) as cursor:
            assert await cursor.fetchone() is None
        await conn.close()

    async def test_v12_check_constraint_accepts_each_known_type(self, tmp_path) -> None:
        """Each PROVIDER_TYPES member inserts cleanly post-migration."""
        from the_one.db._provider_types import PROVIDER_TYPES

        db_path = tmp_path / "types.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await ensure_schema(conn)

        for i, ptype in enumerate(PROVIDER_TYPES):
            await conn.execute(
                "INSERT INTO llm_providers (id, name, type, base_url) VALUES (?, ?, ?, ?)",
                (f"p-{i}", f"Test{i}", ptype, "http://localhost"),
            )
        await conn.commit()

        async with conn.execute("SELECT COUNT(*) AS c FROM llm_providers") as cursor:
            row = await cursor.fetchone()
        assert row["c"] == len(PROVIDER_TYPES)
        await conn.close()


class TestSchemaV13:
    """Tests for the v13 migration that adds the connectors table.

    Mission 10 flight 01: persistence-layer foundation for bi-directional
    communication connectors (Discord bot, Slack workspace app, etc.).
    Mirrors TestSchemaV11 in shape — fresh-DB surfaces, idempotent re-run,
    column-shape verification with explicit assertion that no CHECK
    constraint pins `type` (deferred to v19 in flight 8 when 'discord' is
    a real type to constrain).

    Post-v23 (M11 F11 L1): the table is now ``connectors`` (renamed from
    ``connector_accounts``). These fresh-DB tests assert against the
    final-shape table name.
    """

    async def test_v13_fresh_db_includes_connectors_table(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v13 surfaces exist (post-v23 renamed
        to ``connectors``).

        Regression-loud-fail guard: if a future bump silently drops the v13
        block, this test fails with an explicit message naming
        ``connectors`` (the post-v23 name).
        """
        db_path = tmp_path / "v13-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 13, CURRENT_VERSION

        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connectors'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None, (
            "v13 migration missing: `connectors` table does not exist "
            "after ensure_schema on a fresh DB (post-v23 renamed from "
            "`connector_accounts`)"
        )

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 13 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v13_connectors_has_expected_columns_and_v19_check_constraint(
        self, tmp_path
    ) -> None:
        """connectors has the expected columns; type is NOT NULL and
        now constrained by the v19 CHECK clause (F8 L2).

        Asserts the post-``ensure_schema`` shape — the ``name`` column was
        added in v14 (M10 F01 L02) to mirror MCPSource; the
        ``idle_timeout_seconds`` column was added in v15 (M10 F02 L02) as
        the per-account pool idle TTL override; the
        ``session_continuation_seconds`` column was added in v16 (M10 F03
        L01) as the per-account chat-session continuation window; the
        CHECK constraint on ``type`` landed in v19 (F8 L2) via the table-
        rename ceremony (admits ``'discord'`` and ``'stub'`` per the M07
        ``'mock'``-in-PROVIDER_TYPES precedent); the table itself was
        renamed ``connector_accounts`` → ``connectors`` by v23 (M11 F11 L1).
        """
        db_path = tmp_path / "v13-cols.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        async with conn.execute("PRAGMA table_info(connectors)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}

        assert set(cols) == {
            "id",
            "name",
            "type",
            "config",
            "secrets",
            "idle_timeout_seconds",
            "session_continuation_seconds",
            "created_at",
            "updated_at",
        }, cols

        assert cols["id"]["type"] == "TEXT" and cols["id"]["pk"] == 1
        assert cols["type"]["type"] == "TEXT" and cols["type"]["notnull"] == 1
        assert cols["config"]["type"] == "TEXT" and cols["config"]["dflt_value"] == "'{}'"
        assert cols["secrets"]["type"] == "TEXT" and cols["secrets"]["dflt_value"] == "'{}'"

        # CHECK constraint on type — present after v19 (F8 L2). Verify by
        # inserting a bogus type and asserting it raises (would NOT raise
        # if the CHECK were missing).
        import sqlite3

        with pytest.raises(sqlite3.IntegrityError):
            await conn.execute(
                "INSERT INTO connectors (id, type) VALUES (?, ?)",
                ("test-id", "bogus-type-not-in-connector-types"),
            )
        await conn.rollback()

        # Valid types round-trip cleanly.
        await conn.execute(
            "INSERT INTO connectors (id, type) VALUES (?, ?)",
            ("discord-id", "discord"),
        )
        await conn.execute(
            "INSERT INTO connectors (id, type) VALUES (?, ?)",
            ("stub-id", "stub"),
        )
        await conn.commit()

        async with conn.execute("SELECT id, type FROM connectors ORDER BY id") as cur:
            rows = [(r["id"], r["type"]) for r in await cur.fetchall()]
        assert rows == [("discord-id", "discord"), ("stub-id", "stub")]

        await conn.close()

    async def test_v13_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, no duplicate schema_version rows for v13."""
        db_path = tmp_path / "v13-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(13) == 1, f"v13 row should appear exactly once: {versions}"

        # Table still present after the second call (post-v23 renamed to
        # ``connectors``).
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connectors'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None

        await conn.close()


class TestSchemaV14:
    """Tests for the v14 migration that adds connector_accounts.name.

    Mission 10 flight 01 leg 02: design adjustment caught at leg planning.
    The flight spec called for the ``Connector`` Pydantic class
    (renamed by M11 F11 L1; previously the connector-account class) to
    mirror ``MCPSource`` shape, but the v13 migration omitted the
    ``name`` column. v14 adds it
    via ``ALTER TABLE … ADD COLUMN name TEXT NOT NULL DEFAULT ''`` so
    pre-existing rows (zero in practice) survive with empty name. New rows
    are required to carry a real name by the Pydantic model (no default).

    Downstream: flight 08 (Discord)'s CHECK constraint now lands at v19
    (v14 claimed by this F1 L2 leg — ``name`` column; v15 by F2 L2 —
    ``idle_timeout_seconds``; v16 by F3 L1 — chat_sessions external-key
    + ``session_continuation_seconds``; v17 by F4 L5 —
    ``agents.connector_account_ids``; v18 by F6 L1c —
    ``agents.connector_acls``).
    See flight log ``## Design Adjustments``.
    """

    async def test_v14_fresh_db_includes_name_column(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v14 surfaces exist (post-v23 the
        table is named ``connectors``)."""
        db_path = tmp_path / "v14-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 14, CURRENT_VERSION

        async with conn.execute("PRAGMA table_info(connectors)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}

        assert "name" in cols, (
            "v14 migration missing: connectors.name does not exist "
            "after ensure_schema on a fresh DB (post-v23 table renamed "
            "from connector_accounts)"
        )
        name_col = cols["name"]
        assert name_col["type"] == "TEXT", name_col["type"]
        assert name_col["notnull"] == 1, name_col["notnull"]
        assert name_col["dflt_value"] == "''", name_col["dflt_value"]

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 14 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v14_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, no duplicate schema_version rows for v14."""
        db_path = tmp_path / "v14-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(14) == 1, f"v14 row should appear exactly once: {versions}"

        # The `name` column is still present after the second call
        # (post-v23 the table is named ``connectors``).
        async with conn.execute("PRAGMA table_info(connectors)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "name" in cols

        await conn.close()

    async def test_v14_preserves_v13_seeded_row_with_empty_name(self, tmp_path) -> None:
        """A row seeded against a hand-built v13 schema (no ``name`` column)
        survives the v14 ALTER with ``name=''``.

        Bootstraps a real v13-shape ``connector_accounts`` table (NO
        ``name`` column) so the v14 ALTER actually runs against a row that
        pre-exists without the column. Modeled on
        ``TestMigrationV12.test_v12_real_v11_to_v12_upgrade`` — hand-build
        the pre-migration schema, INSERT rows, set ``schema_version``,
        then call ``ensure_schema``.
        """
        db_path = tmp_path / "v14-from-real-v13.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build the v13 schema for ``connector_accounts`` (no ``name``
        # column) and a ``schema_version`` table. We seed
        # schema_version with versions 1..13 so the migration loop's MAX()
        # head pointer is 13 and the v14 block enters cleanly without
        # earlier blocks attempting to recreate prerequisite tables they
        # already think exist.
        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 14):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connector_accounts ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL,"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        # v13-era chat_sessions shape (post-v5 — no FK on agent_name, no v16
        # connector-keyed columns yet). Needed so the v16 ALTER block in
        # ``ensure_schema`` finds the table to ADD COLUMN against.
        await conn.execute(
            "CREATE TABLE chat_sessions ("
            "    id TEXT PRIMARY KEY,"
            "    agent_name TEXT,"
            "    title TEXT DEFAULT 'New chat',"
            "    messages TEXT DEFAULT '[]',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        # v13-era agents shape (post-v11 — has mcp_overrides, no v17
        # connector_account_ids). Needed so the v17 ALTER block in
        # ``ensure_schema`` finds the table to ADD COLUMN against.
        await conn.execute(
            "CREATE TABLE agents ("
            "    name TEXT PRIMARY KEY,"
            "    description TEXT DEFAULT '',"
            "    provider_config_id TEXT,"
            "    llm_model TEXT DEFAULT '',"
            "    system_prompt TEXT DEFAULT '',"
            "    enabled_tools TEXT,"
            "    disabled_tools TEXT DEFAULT '[]',"
            "    max_iterations INTEGER DEFAULT 20,"
            "    kb_ids TEXT DEFAULT '[]',"
            "    mcp_source_ids TEXT DEFAULT '[]',"
            "    tool_overrides TEXT,"
            "    mcp_overrides TEXT,"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        # Seed a row against the v13 shape (no name).
        await conn.execute(
            "INSERT INTO connector_accounts (id, type, config, secrets) VALUES (?, ?, ?, ?)",
            ("seeded", "stub", "{}", "{}"),
        )
        await conn.commit()

        # Now run ensure_schema — this should hit the v14 block, run the
        # ALTER (the PRAGMA check sees no ``name`` column), populate the
        # seeded row's ``name`` with the DEFAULT '', and bump
        # schema_version to 14.
        await ensure_schema(conn)

        # Row survived with empty name (post-v23 the table is named
        # ``connectors``; the v23 row-rewrite preserves the seeded row).
        async with conn.execute("SELECT id, name, type FROM connectors WHERE id = 'seeded'") as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["name"] == "", f"expected empty name from DEFAULT '', got {row['name']!r}"
        assert row["type"] == "stub"

        # Head pointer landed at CURRENT_VERSION (≥14).
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 14 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()


class TestSchemaV15:
    """Tests for the v15 migration that adds connector_accounts.idle_timeout_seconds.

    Mission 10 flight 02 leg 02: operator-configurable per-account pool
    idle TTL. Nullable INTEGER (NULL = "use _resolve_ttl_seconds env-var /
    default"). Bounded at the Pydantic layer (1 ≤ value ≤ 604800).

    Downstream: flight 08 (Discord)'s CHECK constraint now lands at v19
    (v15 claimed by this F2 L2 leg — ``idle_timeout_seconds``; v16 by
    F3 L1 — chat_sessions external-key + ``session_continuation_seconds``;
    v17 by F4 L5 — ``agents.connector_account_ids``; v18 by F6 L1c —
    ``agents.connector_acls``).
    See flight log ``## Design Adjustments``.
    """

    async def test_v15_fresh_db_includes_idle_timeout_seconds_column(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v15 surfaces exist."""
        db_path = tmp_path / "v15-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 15, CURRENT_VERSION

        async with conn.execute("PRAGMA table_info(connectors)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}

        assert "idle_timeout_seconds" in cols, (
            "v15 migration missing: connectors.idle_timeout_seconds "
            "does not exist after ensure_schema on a fresh DB (post-v23 "
            "table renamed from connector_accounts)"
        )
        ttl_col = cols["idle_timeout_seconds"]
        assert ttl_col["type"] == "INTEGER", ttl_col["type"]
        # notnull == 0 means the column is nullable.
        assert ttl_col["notnull"] == 0, ttl_col["notnull"]
        # No explicit DEFAULT clause — dflt_value must be Python None.
        assert ttl_col["dflt_value"] is None, ttl_col["dflt_value"]

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 15 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v15_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, no duplicate schema_version rows for v15."""
        db_path = tmp_path / "v15-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(15) == 1, f"v15 row should appear exactly once: {versions}"

        # The `idle_timeout_seconds` column is still present after the
        # second call (post-v23 table renamed to ``connectors``).
        async with conn.execute("PRAGMA table_info(connectors)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "idle_timeout_seconds" in cols

        await conn.close()

    async def test_v15_legacy_v14_row_decodes_with_none_idle_timeout(self, tmp_path) -> None:
        """A row seeded against a hand-built v14 schema (no
        ``idle_timeout_seconds`` column) survives the v15 ALTER with
        ``idle_timeout_seconds IS NULL``.

        Bootstraps a real v14-shape ``connector_accounts`` table (NO
        ``idle_timeout_seconds`` column) so the v15 ALTER actually runs
        against a row that pre-exists without the column. Modeled on
        ``TestSchemaV14.test_v14_preserves_v13_seeded_row_with_empty_name``.
        """
        db_path = tmp_path / "v15-from-real-v14.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build the v14 schema for ``connector_accounts`` (no
        # ``idle_timeout_seconds`` column) and a ``schema_version`` table.
        # Seed schema_version with versions 1..14 so the migration loop's
        # MAX() head pointer is 14 and the v15 block enters cleanly.
        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 15):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connector_accounts ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL,"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT ''"
            ")"
        )
        # v14-era chat_sessions shape (post-v5 — no v16 connector-keyed
        # columns). Needed so the v16 ALTER block in ``ensure_schema`` finds
        # the table to ADD COLUMN against.
        await conn.execute(
            "CREATE TABLE chat_sessions ("
            "    id TEXT PRIMARY KEY,"
            "    agent_name TEXT,"
            "    title TEXT DEFAULT 'New chat',"
            "    messages TEXT DEFAULT '[]',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        # v14-era agents shape (post-v11 — has mcp_overrides, no v17
        # connector_account_ids). Needed so the v17 ALTER block in
        # ``ensure_schema`` finds the table to ADD COLUMN against.
        await conn.execute(
            "CREATE TABLE agents ("
            "    name TEXT PRIMARY KEY,"
            "    description TEXT DEFAULT '',"
            "    provider_config_id TEXT,"
            "    llm_model TEXT DEFAULT '',"
            "    system_prompt TEXT DEFAULT '',"
            "    enabled_tools TEXT,"
            "    disabled_tools TEXT DEFAULT '[]',"
            "    max_iterations INTEGER DEFAULT 20,"
            "    kb_ids TEXT DEFAULT '[]',"
            "    mcp_source_ids TEXT DEFAULT '[]',"
            "    tool_overrides TEXT,"
            "    mcp_overrides TEXT,"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        # Seed a row against the v14 shape (no idle_timeout_seconds).
        await conn.execute(
            "INSERT INTO connector_accounts (id, name, type, config, secrets)"
            " VALUES (?, ?, ?, ?, ?)",
            ("seeded-v14", "Legacy Bot", "stub", "{}", "{}"),
        )
        await conn.commit()

        # Run ensure_schema — should hit the v15 block, run the ALTER (the
        # PRAGMA check sees no ``idle_timeout_seconds`` column), populate
        # the seeded row's ``idle_timeout_seconds`` with NULL, and bump
        # schema_version to 15.
        await ensure_schema(conn)

        # Row survived with NULL idle_timeout_seconds (post-v23 table
        # renamed to ``connectors``; v23 row-rewrite preserves the row).
        async with conn.execute(
            "SELECT id, name, idle_timeout_seconds FROM connectors WHERE id = 'seeded-v14'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["name"] == "Legacy Bot"
        assert row["idle_timeout_seconds"] is None, (
            f"expected NULL idle_timeout_seconds, got {row['idle_timeout_seconds']!r}"
        )

        # Head pointer landed at CURRENT_VERSION (≥15).
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 15 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()


class TestSchemaV16:
    """Tests for the v16 migration that adds chat_sessions connector-keying
    columns + connector_accounts.session_continuation_seconds.

    Mission 10 flight 03 leg 01: per-row nullable columns on chat_sessions
    hold the external conversation identity for connector-driven sessions;
    a non-unique partial expression index on
    (platform, connector_account_id, channel_id, COALESCE(thread_id, ''))
    supports the resolver's most-recent-by-updated_at lookup.
    session_continuation_seconds on connector_accounts is the per-account
    continuation window consumed by the resolver (F3 L3).

    Downstream: flight 08 (Discord)'s CHECK constraint now lands at v19
    (v17 claimed by F4 L5 — ``agents.connector_account_ids`` ALTER;
    v18 by F6 L1c — ``agents.connector_acls`` ALTER). See flight log
    ``## Design Adjustments`` and _connector_types.py docstring.
    """

    async def test_v16_fresh_db_includes_chat_session_external_key_columns(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v16 surfaces exist."""
        db_path = tmp_path / "v16-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 16, CURRENT_VERSION

        # All seven new chat_sessions columns are present and nullable.
        # Post-v23 (M11 F11 L1): ``connector_account_id`` renamed to
        # ``connector_id``.
        async with conn.execute("PRAGMA table_info(chat_sessions)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        for expected in (
            "platform",
            "connector_id",
            "channel_id",
            "thread_id",
            "peer_id",
            "session_metadata",
            "last_inbound_at",
        ):
            assert expected in cols, (
                f"v16 migration missing: chat_sessions.{expected} does not exist"
            )
            assert cols[expected]["type"] == "TEXT", cols[expected]["type"]
            assert cols[expected]["notnull"] == 0, cols[expected]["notnull"]
            assert cols[expected]["dflt_value"] is None, cols[expected]["dflt_value"]

        # connectors.session_continuation_seconds is present (post-v23
        # table renamed from connector_accounts).
        async with conn.execute("PRAGMA table_info(connectors)") as cur:
            acc_cols = {r["name"]: r for r in await cur.fetchall()}
        assert "session_continuation_seconds" in acc_cols
        sc = acc_cols["session_continuation_seconds"]
        assert sc["type"] == "INTEGER", sc["type"]
        assert sc["notnull"] == 0, sc["notnull"]
        assert sc["dflt_value"] is None, sc["dflt_value"]

        # The partial expression index exists.
        async with conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name='idx_chat_sessions_external_key'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None, (
            "v16 migration missing: idx_chat_sessions_external_key does not exist"
        )

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 16 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v16_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, no duplicate schema_version rows for v16, all
        seven chat_sessions columns + the connectors column + the
        index still present. Post-v23: chat_sessions uses ``connector_id``
        and the parent table is ``connectors``."""
        db_path = tmp_path / "v16-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(16) == 1, f"v16 row should appear exactly once: {versions}"

        async with conn.execute("PRAGMA table_info(chat_sessions)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        for expected in (
            "platform",
            "connector_id",
            "channel_id",
            "thread_id",
            "peer_id",
            "session_metadata",
            "last_inbound_at",
        ):
            assert expected in cols
        async with conn.execute("PRAGMA table_info(connectors)") as cur:
            acc_cols = {r["name"] for r in await cur.fetchall()}
        assert "session_continuation_seconds" in acc_cols

        await conn.close()

    async def test_v16_legacy_v15_row_decodes_with_null_external_key_columns(
        self, tmp_path
    ) -> None:
        """Rows seeded against a hand-built v15 schema (no v16 columns)
        survive the v16 ALTERs with NULLs on all new columns.

        Hand-builds the v15 shape of both chat_sessions AND
        connector_accounts so the v16 ALTERs actually run against pre-
        existing rows without the new columns. Modeled on
        ``TestSchemaV15.test_v15_legacy_v14_row_decodes_with_none_idle_timeout``.
        """
        db_path = tmp_path / "v16-from-real-v15.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 16):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        # v15-shape chat_sessions (no v16 columns).
        await conn.execute(
            "CREATE TABLE chat_sessions ("
            "    id TEXT PRIMARY KEY,"
            "    agent_name TEXT,"
            "    title TEXT DEFAULT 'New chat',"
            "    messages TEXT DEFAULT '[]',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        # v15-shape connector_accounts (no session_continuation_seconds).
        await conn.execute(
            "CREATE TABLE connector_accounts ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL,"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL"
            ")"
        )
        # v15-era agents shape (post-v11 — has mcp_overrides, no v17
        # connector_account_ids). Needed so the v17 ALTER block in
        # ``ensure_schema`` finds the table to ADD COLUMN against.
        await conn.execute(
            "CREATE TABLE agents ("
            "    name TEXT PRIMARY KEY,"
            "    description TEXT DEFAULT '',"
            "    provider_config_id TEXT,"
            "    llm_model TEXT DEFAULT '',"
            "    system_prompt TEXT DEFAULT '',"
            "    enabled_tools TEXT,"
            "    disabled_tools TEXT DEFAULT '[]',"
            "    max_iterations INTEGER DEFAULT 20,"
            "    kb_ids TEXT DEFAULT '[]',"
            "    mcp_source_ids TEXT DEFAULT '[]',"
            "    tool_overrides TEXT,"
            "    mcp_overrides TEXT,"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        # Seed rows against the v15 shape.
        await conn.execute(
            "INSERT INTO chat_sessions (id, agent_name, title) VALUES (?, ?, ?)",
            ("seeded-session", "test-agent", "Pre-v16 session"),
        )
        await conn.execute(
            "INSERT INTO connector_accounts (id, name, type, config, secrets, idle_timeout_seconds)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("seeded-account", "stub-account", "stub", "{}", "{}", 1800),
        )
        await conn.commit()

        await ensure_schema(conn)

        # Seeded chat_sessions row survived with NULLs on all v16 columns
        # (post-v23 the column is ``connector_id``, renamed by v23 via
        # ``ALTER TABLE chat_sessions RENAME COLUMN``).
        async with conn.execute(
            "SELECT id, agent_name, title, platform, connector_id,"
            " channel_id, thread_id, peer_id, session_metadata, last_inbound_at"
            " FROM chat_sessions WHERE id = 'seeded-session'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["agent_name"] == "test-agent"
        assert row["title"] == "Pre-v16 session"
        for col in (
            "platform",
            "connector_id",
            "channel_id",
            "thread_id",
            "peer_id",
            "session_metadata",
            "last_inbound_at",
        ):
            assert row[col] is None, f"{col} should be NULL on legacy row, got {row[col]!r}"

        # Seeded connectors row survived with idle_timeout preserved
        # and session_continuation_seconds=NULL (post-v23 table renamed
        # from connector_accounts via row-rewrite).
        async with conn.execute(
            "SELECT id, idle_timeout_seconds, session_continuation_seconds"
            " FROM connectors WHERE id = 'seeded-account'"
        ) as cur:
            acc_row = await cur.fetchone()
        assert acc_row is not None
        assert acc_row["idle_timeout_seconds"] == 1800
        assert acc_row["session_continuation_seconds"] is None

        # Head pointer landed at CURRENT_VERSION (≥16).
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 16 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions


class TestSchemaV17:
    """Tests for the v17 migration that adds agents.connector_account_ids.

    Mission 10 Flight 4 Leg 5: closes the AgentConfig.connector_account_ids
    persistence gap surfaced by F4 L4 (the e2e tests worked around the
    missing DB column via a monkeypatch on
    ``SQLiteAgentStore._row_to_config``). v17 adds the column as a
    nullable TEXT field storing the JSON-encoded list; NULL on pre-v17
    rows decodes to ``[]`` via the ``or "[]"`` default in ``_row_to_config``.

    Downstream: flight 08 (Discord) previously planned a v17 CHECK
    migration; that renumbers to v19 (v18 is claimed by F6 L1c —
    ``agents.connector_acls``).
    """

    async def test_v17_fresh_db_includes_agents_connector_ids_column(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v17 surfaces exist (post-v23 the
        column was renamed ``connector_account_ids`` → ``connector_ids``
        via ``ALTER TABLE agents RENAME COLUMN``)."""
        db_path = tmp_path / "v17-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 17, CURRENT_VERSION

        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}

        assert "connector_ids" in cols, (
            "v17 migration missing: agents.connector_ids does not "
            "exist after ensure_schema on a fresh DB (post-v23 column "
            "renamed from connector_account_ids)"
        )
        col = cols["connector_ids"]
        assert col["type"] == "TEXT", col["type"]
        # notnull == 0 means the column is nullable (we read NULL → []
        # in `_row_to_config` via the `or "[]"` default).
        assert col["notnull"] == 0, col["notnull"]
        # No explicit DEFAULT clause; dflt_value is Python None.
        assert col["dflt_value"] is None, col["dflt_value"]

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 17 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v17_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, no duplicate schema_version rows for v17, the
        column is still present."""
        db_path = tmp_path / "v17-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(17) == 1, f"v17 row should appear exactly once: {versions}"

        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        # Post-v23: column renamed ``connector_account_ids`` → ``connector_ids``.
        assert "connector_ids" in cols

        await conn.close()

    async def test_v17_legacy_v16_row_decodes_with_empty_connector_ids(self, tmp_path) -> None:
        """A row seeded against a hand-built v16 schema (no
        ``connector_account_ids`` column) survives the v17 ALTER with the
        column added as NULL; the repository's ``_row_to_config`` reads
        NULL → ``[]``.

        Hand-builds a v16-shape ``agents`` table (no connector_account_ids
        column), INSERTs a row, sets ``schema_version`` rows up to 16,
        then calls ``ensure_schema``. Mirrors
        ``TestSchemaV14.test_v14_preserves_v13_seeded_row_with_empty_name``.
        """
        from the_one.db.repositories import SQLiteAgentStore

        db_path = tmp_path / "v17-from-real-v16.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build a minimal schema_version table and seed v1..v16.
        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 17):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        # v16-shape agents (no connector_account_ids). Mirrors the
        # post-v11/v8 agents columns. We need only the columns the
        # repository's `_row_to_config` reads, plus the PK.
        await conn.execute(
            "CREATE TABLE agents ("
            "    name TEXT PRIMARY KEY,"
            "    description TEXT DEFAULT '',"
            "    provider_config_id TEXT,"
            "    llm_model TEXT DEFAULT '',"
            "    system_prompt TEXT DEFAULT '',"
            "    enabled_tools TEXT,"
            "    disabled_tools TEXT DEFAULT '[]',"
            "    max_iterations INTEGER DEFAULT 20,"
            "    kb_ids TEXT DEFAULT '[]',"
            "    mcp_source_ids TEXT DEFAULT '[]',"
            "    tool_overrides TEXT,"
            "    mcp_overrides TEXT,"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        await conn.execute(
            "INSERT INTO agents (name, description, llm_model) VALUES (?, ?, ?)",
            ("legacy-agent", "Pre-v17 agent", "mock-default"),
        )
        # v16-shape connector_accounts (9 cols, no CHECK on type). v19
        # (F8 L2) rebuilds this via the table-rename ceremony and would
        # error on "no such table" if absent — hand-build the v16 shape
        # so the v19 INSERT INTO _new SELECT * source exists. No row
        # seeded (the test exercises agents.connector_account_ids, not
        # connector_accounts data preservation).
        await conn.execute(
            "CREATE TABLE connector_accounts ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL,"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        await conn.commit()

        await ensure_schema(conn)

        # The column now exists (post-v23 renamed to ``connector_ids``).
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_ids" in cols

        # The pre-existing row has NULL on the new column (post-v23 the
        # column is named ``connector_ids``; v23 renames in place via
        # ``ALTER TABLE agents RENAME COLUMN`` preserving the row's
        # value).
        async with conn.execute(
            "SELECT connector_ids FROM agents WHERE name = 'legacy-agent'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["connector_ids"] is None

        # _row_to_config decodes NULL → []. Post-v23: Pydantic field also
        # renamed ``connector_account_ids`` → ``connector_ids``.
        store = SQLiteAgentStore(conn)
        loaded = await store.load("legacy-agent")
        assert loaded.connector_ids == []

        # Head pointer landed at CURRENT_VERSION (≥17).
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 17 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

        await conn.close()


class TestSchemaV18:
    """Tests for the v18 migration that adds agents.connector_acls.

    Mission 10 Flight 6 Leg 1c: per-agent ACL persistence. Atomic shape
    per F4 debrief rec #1 — Pydantic field + ALTER TABLE + repository
    round-trip ship in one leg. The column is a nullable TEXT field
    storing the JSON-encoded outer dict
    ``{account_id: {"peers": [...], "channels": [...]}}`` or NULL when
    no per-agent narrowing exists. Pre-v18 rows decode NULL → ``None``
    via the ``if row["connector_acls"] else None`` decode in
    ``SQLiteAgentStore._row_to_config``.

    Downstream: flight 08 (Discord)'s CHECK constraint now lands at v19.
    """

    async def test_v18_fresh_db_includes_agents_connector_acls_column(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v18 surfaces exist."""
        db_path = tmp_path / "v18-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 18, CURRENT_VERSION

        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}

        assert "connector_acls" in cols, (
            "v18 migration missing: agents.connector_acls does not "
            "exist after ensure_schema on a fresh DB"
        )
        col = cols["connector_acls"]
        assert col["type"] == "TEXT", col["type"]
        # notnull == 0 means the column is nullable (we read NULL → None
        # in `_row_to_config` via the `if row["X"] else None` decode).
        assert col["notnull"] == 0, col["notnull"]
        # No explicit DEFAULT clause; dflt_value is Python None.
        assert col["dflt_value"] is None, col["dflt_value"]

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 18 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v18_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, no duplicate schema_version rows for v18, the
        column is still present."""
        db_path = tmp_path / "v18-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(18) == 1, f"v18 row should appear exactly once: {versions}"

        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_acls" in cols

        await conn.close()

    async def test_v18_legacy_v17_row_decodes_with_none_connector_acls(self, tmp_path) -> None:
        """A row seeded against a hand-built v17 schema (no
        ``connector_acls`` column) survives the v18 ALTER with the column
        added as NULL; the repository's ``_row_to_config`` reads
        NULL → ``None`` (distinguishing it from ``{}``, which round-trips
        verbatim).

        Hand-builds a v17-shape ``agents`` table (with
        ``connector_account_ids`` but no ``connector_acls`` column),
        INSERTs a row, sets ``schema_version`` rows up to 17, then calls
        ``ensure_schema``. Mirrors
        ``TestSchemaV17.test_v17_legacy_v16_row_decodes_with_empty_connector_account_ids``.
        """
        from the_one.db.repositories import SQLiteAgentStore

        db_path = tmp_path / "v18-from-real-v17.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build a minimal schema_version table and seed v1..v17.
        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 18):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        # v17-shape agents (with connector_account_ids, no connector_acls).
        # We need only the columns the repository's `_row_to_config` reads,
        # plus the PK.
        await conn.execute(
            "CREATE TABLE agents ("
            "    name TEXT PRIMARY KEY,"
            "    description TEXT DEFAULT '',"
            "    provider_config_id TEXT,"
            "    llm_model TEXT DEFAULT '',"
            "    system_prompt TEXT DEFAULT '',"
            "    enabled_tools TEXT,"
            "    disabled_tools TEXT DEFAULT '[]',"
            "    max_iterations INTEGER DEFAULT 20,"
            "    kb_ids TEXT DEFAULT '[]',"
            "    mcp_source_ids TEXT DEFAULT '[]',"
            "    tool_overrides TEXT,"
            "    mcp_overrides TEXT,"
            "    connector_account_ids TEXT,"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        await conn.execute(
            "INSERT INTO agents (name, description, llm_model) VALUES (?, ?, ?)",
            ("legacy-v17-agent", "Pre-v18 agent", "mock-default"),
        )
        # v17-shape connector_accounts (9 cols, no CHECK on type). v19
        # (F8 L2) rebuilds this via the table-rename ceremony and would
        # error on "no such table" if absent — hand-build the v17 shape
        # so the v19 INSERT INTO _new SELECT * source exists. No row
        # seeded (the test exercises agents.connector_acls, not
        # connector_accounts data preservation).
        await conn.execute(
            "CREATE TABLE connector_accounts ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL,"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        await conn.commit()

        await ensure_schema(conn)

        # The column now exists.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_acls" in cols

        # The pre-existing row has NULL on the new column.
        async with conn.execute(
            "SELECT connector_acls FROM agents WHERE name = 'legacy-v17-agent'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["connector_acls"] is None

        # _row_to_config decodes NULL → None.
        store = SQLiteAgentStore(conn)
        loaded = await store.load("legacy-v17-agent")
        assert loaded.connector_acls is None

        # Head pointer landed at CURRENT_VERSION (≥18).
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 18 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()


class TestSchemaV20:
    """Tests for the v20 migration that adds agents.connector_always_listen.

    Mission 11 Flight 7 Leg 6: per-agent always_listen toggle persistence.
    Atomic shape per F4 debrief rec #1 — Pydantic field + ALTER TABLE +
    repository round-trip ship in one leg. The column is a nullable TEXT
    field storing the JSON-encoded outer dict ``{account_id: bool}`` or
    NULL when no per-agent override exists. Pre-v20 rows decode
    NULL → ``None`` via the
    ``if row["connector_always_listen"] else None`` decode in
    ``SQLiteAgentStore._row_to_config``.

    Mirrors the v18 ``TestSchemaV18`` shape (connector_acls migration).
    """

    async def test_v20_fresh_db_includes_agents_connector_always_listen_column(
        self, tmp_path
    ) -> None:
        """Fresh DB → ensure_schema → v20 surfaces exist."""
        db_path = tmp_path / "v20-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 20, CURRENT_VERSION

        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}

        assert "connector_always_listen" in cols, (
            "v20 migration missing: agents.connector_always_listen "
            "does not exist after ensure_schema on a fresh DB"
        )
        col = cols["connector_always_listen"]
        assert col["type"] == "TEXT", col["type"]
        # notnull == 0 means the column is nullable (we read NULL → None
        # in `_row_to_config` via the `if row["X"] else None` decode).
        assert col["notnull"] == 0, col["notnull"]
        # No explicit DEFAULT clause; dflt_value is Python None.
        assert col["dflt_value"] is None, col["dflt_value"]

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 20 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v20_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, no duplicate schema_version rows for v20, the
        column is still present."""
        db_path = tmp_path / "v20-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(20) == 1, f"v20 row should appear exactly once: {versions}"

        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_always_listen" in cols

        await conn.close()

    async def test_v20_legacy_v19_row_decodes_with_none_connector_always_listen(
        self, tmp_path
    ) -> None:
        """A row seeded against a hand-built v19 schema (no
        ``connector_always_listen`` column) survives the v20 ALTER with
        the column added as NULL; the repository's ``_row_to_config``
        reads NULL → ``None`` (distinguishing it from ``{}``, which
        round-trips verbatim).

        Hand-builds a v19-shape ``agents`` table (with ``connector_acls``
        but no ``connector_always_listen`` column), INSERTs a row, sets
        ``schema_version`` rows up to 19, then calls ``ensure_schema``.
        Mirrors
        ``TestSchemaV18.test_v18_legacy_v17_row_decodes_with_none_connector_acls``.
        """
        from the_one.db.repositories import SQLiteAgentStore

        db_path = tmp_path / "v20-from-real-v19.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build a minimal schema_version table and seed v1..v19.
        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 20):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        # v19-shape agents (with connector_acls, no connector_always_listen).
        # We need only the columns the repository's `_row_to_config` reads,
        # plus the PK.
        await conn.execute(
            "CREATE TABLE agents ("
            "    name TEXT PRIMARY KEY,"
            "    description TEXT DEFAULT '',"
            "    provider_config_id TEXT,"
            "    llm_model TEXT DEFAULT '',"
            "    system_prompt TEXT DEFAULT '',"
            "    enabled_tools TEXT,"
            "    disabled_tools TEXT DEFAULT '[]',"
            "    max_iterations INTEGER DEFAULT 20,"
            "    kb_ids TEXT DEFAULT '[]',"
            "    mcp_source_ids TEXT DEFAULT '[]',"
            "    tool_overrides TEXT,"
            "    mcp_overrides TEXT,"
            "    connector_account_ids TEXT,"
            "    connector_acls TEXT,"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        await conn.execute(
            "INSERT INTO agents (name, description, llm_model) VALUES (?, ?, ?)",
            ("legacy-v19-agent", "Pre-v20 agent", "mock-default"),
        )
        # v19-shape connector_accounts (post-v19 CHECK shape — required
        # so the v19 block does NOT re-run; ensure_schema sees
        # schema_version already at 19 and skips. No row seeded.
        await conn.execute(
            "CREATE TABLE connector_accounts ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        await conn.commit()

        await ensure_schema(conn)

        # The column now exists.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_always_listen" in cols

        # The pre-existing row has NULL on the new column.
        async with conn.execute(
            "SELECT connector_always_listen FROM agents WHERE name = 'legacy-v19-agent'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["connector_always_listen"] is None

        # _row_to_config decodes NULL → None.
        store = SQLiteAgentStore(conn)
        loaded = await store.load("legacy-v19-agent")
        assert loaded.connector_always_listen is None

        # Head pointer landed at CURRENT_VERSION (≥20).
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 20 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()


class TestSchemaV21:
    """Tests for the v21 migration that adds the pending_approvals table.

    Mission 11 Flight 9 Leg 2: Discord-native peer-approval storage.
    Fresh table (no ALTER, no rename ceremony). FK CASCADE on
    ``connector_account_id`` mirrors the kb_items / chat_sessions
    precedent. CHECK constraint pins the three-state lifecycle
    (``pending``, ``approved``, ``dismissed``).

    Post-v23 (M11 F11 L1): the FK column was renamed
    ``connector_account_id`` → ``connector_id`` and the FK target
    re-pointed from ``connector_accounts`` to ``connectors`` via the
    v23 row-rewrite ceremony. Post-v24 (M11 F12 L3): the supporting
    index was renamed ``idx_pending_approvals_account_peer_status`` →
    ``idx_pending_approvals_connector_peer_status`` (cosmetic-rename
    deferred from v23 per the F12 housekeeping decision). The fresh-DB
    tests below assert against the post-v24 final-shape names.

    Mirrors the v18 / v20 ``TestSchemaVNN`` shapes.
    """

    async def test_v21_fresh_db_includes_pending_approvals_table(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v21 surfaces exist: table, columns,
        FK constraint, CHECK constraint, supporting index, schema_version
        row at 21."""
        db_path = tmp_path / "v21-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 21, CURRENT_VERSION

        # Table exists with the expected columns. Post-v23 (M11 F11 L1):
        # FK column ``connector_account_id`` renamed to ``connector_id``
        # via the v23 row-rewrite ceremony; FK target re-pointed at
        # ``connectors(id)``.
        async with conn.execute("PRAGMA table_info(pending_approvals)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        expected_cols = {
            "id",
            "connector_id",
            "peer_id",
            "peer_name",
            "preview",
            "received_at",
            "status",
            "resolved_at",
        }
        assert expected_cols.issubset(cols.keys()), (
            f"missing columns: {expected_cols - cols.keys()}"
        )

        # ``id`` is PRIMARY KEY.
        assert cols["id"]["pk"] == 1, cols["id"]

        # NOT NULL on every non-PK column except ``resolved_at``.
        # (SQLite's PRAGMA table_info reports notnull=0 for PRIMARY KEY
        # columns even when NOT NULL is implied; ``id`` is the PK here
        # so we don't assert notnull on it.)
        for nn_col in (
            "connector_id",
            "peer_id",
            "peer_name",
            "preview",
            "received_at",
            "status",
        ):
            assert cols[nn_col]["notnull"] == 1, (nn_col, cols[nn_col])
        assert cols["resolved_at"]["notnull"] == 0, cols["resolved_at"]

        # FK ON DELETE CASCADE on connector_id (post-v23 column rename
        # + FK target re-pointed at ``connectors``).
        async with conn.execute("PRAGMA foreign_key_list(pending_approvals)") as cur:
            fks = [dict(r) for r in await cur.fetchall()]
        assert len(fks) == 1, fks
        fk = fks[0]
        assert fk["table"] == "connectors", fk
        assert fk["from"] == "connector_id", fk
        assert fk["to"] == "id", fk
        assert fk["on_delete"].upper() == "CASCADE", fk

        # Supporting index for the upsert-dedup query path.
        # M11 F12 L3 — v24 renamed the index from
        # ``idx_pending_approvals_account_peer_status`` to
        # ``idx_pending_approvals_connector_peer_status``. Under full
        # ``ensure_schema`` the v24 name is what we observe.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='pending_approvals'"
        ) as cur:
            index_names = {r["name"] for r in await cur.fetchall()}
        assert "idx_pending_approvals_connector_peer_status" in index_names, index_names

        # schema_version row for v21 exists; head pointer lands at
        # CURRENT_VERSION.
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 21 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v21_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, the v21 row appears exactly once, the table is
        still well-formed."""
        db_path = tmp_path / "v21-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(21) == 1, f"v21 row should appear exactly once: {versions}"

        async with conn.execute("PRAGMA table_info(pending_approvals)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "id" in cols and "status" in cols, cols

        await conn.close()

    async def test_v21_fk_cascade_deletes_dependent_rows(self, tmp_path) -> None:
        """Deleting a row from connectors removes its dependent
        pending_approvals rows. Verifies FK CASCADE wiring with
        ``PRAGMA foreign_keys=ON``. Post-v23 (M11 F11 L1): parent
        table renamed ``connector_accounts`` → ``connectors`` and FK
        column renamed ``connector_account_id`` → ``connector_id``."""
        db_path = tmp_path / "v21-cascade.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Seed a connector + a dependent pending_approval row.
        await conn.execute(
            "INSERT INTO connectors (id, name, type) VALUES (?, ?, ?)",
            ("acct-1", "Test", "stub"),
        )
        await conn.execute(
            "INSERT INTO pending_approvals "
            "(id, connector_id, peer_id, peer_name, preview, "
            " received_at, status, resolved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL)",
            (
                "appr-1",
                "acct-1",
                "peer-1",
                "Peer One",
                "hello",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        await conn.commit()

        # Pre-condition: one row.
        async with conn.execute("SELECT COUNT(*) FROM pending_approvals") as cur:
            (count_before,) = await cur.fetchone()
        assert count_before == 1, count_before

        # Delete the parent.
        await conn.execute("DELETE FROM connectors WHERE id = ?", ("acct-1",))
        await conn.commit()

        # Cascade removed the dependent row.
        async with conn.execute("SELECT COUNT(*) FROM pending_approvals") as cur:
            (count_after,) = await cur.fetchone()
        assert count_after == 0, count_after

        await conn.close()

    async def test_v21_check_constraint_rejects_bad_status(self, tmp_path) -> None:
        """INSERTing a pending_approvals row with ``status='banana'``
        raises ``aiosqlite.IntegrityError``. We assert on the exception
        class only — CHECK-constraint failure messages vary across SQLite
        versions and are not stable."""
        db_path = tmp_path / "v21-check.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Post-v23 (M11 F11 L1): parent table renamed to ``connectors``,
        # FK column to ``connector_id``.
        await conn.execute(
            "INSERT INTO connectors (id, name, type) VALUES (?, ?, ?)",
            ("acct-1", "Test", "stub"),
        )
        await conn.commit()

        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO pending_approvals "
                "(id, connector_id, peer_id, peer_name, preview, "
                " received_at, status, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'banana', NULL)",
                (
                    "appr-bad",
                    "acct-1",
                    "peer-1",
                    "Peer One",
                    "hi",
                    "2026-01-01T00:00:00+00:00",
                ),
            )

        await conn.close()


class TestSchemaV22:
    """Tests for the v22 migration that adds the ``dm_admission`` axis
    on ``connector_accounts.config.allowlist`` via row-rewrite.

    Mission 11 Flight 10 Leg 1: DM-admission axis split. Row-rewrite
    migration (NOT ALTER ADD COLUMN — the column is JSON-encoded TEXT,
    so the schema change lives inside the JSON). Legacy-preservation
    rule:

      - ``allowlist.channels`` empty/absent → ``dm_admission="all"``
      - ``allowlist.channels`` non-empty → ``dm_admission="none"``

    Rows without an ``allowlist`` key are untouched; the Pydantic
    validator default handles them at read time.

    Mirrors the v7 row-rewrite precedent at ``schema.py:286-303``.
    """

    async def test_v22_fresh_db_has_no_legacy_rewrite(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v22 surfaces exist; no rows in
        ``connectors`` (post-v23 renamed from ``connector_accounts``),
        so the row-rewrite loop is a no-op and only the schema_version
        row appears.
        """
        db_path = tmp_path / "v22-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 22, CURRENT_VERSION

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 22 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        # No connectors rows on a fresh DB; the loop is a no-op.
        # Post-v23: table renamed from ``connector_accounts``.
        async with conn.execute("SELECT COUNT(*) FROM connectors") as cur:
            (count,) = await cur.fetchone()
        assert count == 0, count

        await conn.close()

    async def test_v22_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the
        second time: no errors, the v22 row appears exactly once, the
        idempotency guard (``if "dm_admission" in allowlist: continue``)
        prevents double-rewrites of legacy rows.
        """
        db_path = tmp_path / "v22-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(22) == 1, f"v22 row should appear exactly once: {versions}"

        await conn.close()

    async def test_v22_legacy_row_with_empty_channels_gets_dm_admission_all(self, tmp_path) -> None:
        """A legacy v21 row whose ``allowlist.channels`` is empty/absent
        gets ``dm_admission="all"`` inserted by the v22 row-rewrite
        (pre-L1 behavior admitted all DMs against an empty channels
        list).
        """
        db_path = tmp_path / "v22-legacy-empty-channels.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build schema_version + minimal connector_accounts shape
        # up to v21 (post-v19 rename ceremony, no dm_admission yet).
        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 22):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connector_accounts ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        # Seed a row with allowlist.peers populated, channels empty.
        legacy_config = json.dumps(
            {
                "allowlist": {"peers": ["P1"], "channels": []},
            }
        )
        await conn.execute(
            "INSERT INTO connector_accounts (id, name, type, config) VALUES (?, ?, ?, ?)",
            ("legacy-acct-1", "Legacy", "stub", legacy_config),
        )
        await conn.commit()

        await ensure_schema(conn)

        # Post-v23 (M11 F11 L1): table renamed ``connector_accounts`` →
        # ``connectors``; the v23 row-rewrite preserves the seeded legacy
        # row's config JSON verbatim.
        async with conn.execute(
            "SELECT config FROM connectors WHERE id = ?",
            ("legacy-acct-1",),
        ) as cur:
            row = await cur.fetchone()
        cfg = json.loads(row["config"])
        # M11 F12 L3 — v24 row-rewrote peers and channels into the
        # structured-tuple shape. dm_admission "all" stays "all".
        # M11 F17 L8 (Leg D) — v28 stripped dm_allowed; bare {id}.
        assert cfg["allowlist"]["peers"] == [{"id": "P1"}]
        assert cfg["allowlist"]["channels"] == []
        assert cfg["allowlist"]["dm_admission"] == "all"

        # Head pointer landed at CURRENT_VERSION.
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 22 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v22_legacy_row_with_non_empty_channels_gets_dm_admission_none(
        self, tmp_path
    ) -> None:
        """A legacy v21 row whose ``allowlist.channels`` is non-empty
        gets ``dm_admission="none"`` inserted by the v22 row-rewrite
        (pre-L1 behavior denied all DMs against a channels mismatch).
        """
        db_path = tmp_path / "v22-legacy-nonempty-channels.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 22):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connector_accounts ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        legacy_config = json.dumps(
            {
                "allowlist": {"peers": ["P1"], "channels": ["C1"]},
            }
        )
        await conn.execute(
            "INSERT INTO connector_accounts (id, name, type, config) VALUES (?, ?, ?, ?)",
            ("legacy-acct-2", "Legacy", "stub", legacy_config),
        )
        await conn.commit()

        await ensure_schema(conn)

        # Post-v23 (M11 F11 L1): table renamed ``connector_accounts`` →
        # ``connectors``; the v23 row-rewrite preserves the seeded legacy
        # row's config JSON verbatim.
        async with conn.execute(
            "SELECT config FROM connectors WHERE id = ?",
            ("legacy-acct-2",),
        ) as cur:
            row = await cur.fetchone()
        cfg = json.loads(row["config"])
        # M11 F12 L3 — v24 row-rewrote peers + channels into the
        # structured-tuple shape. dm_admission "none" stays "none".
        # M11 F12 L5: v25 cleanup deletes orphan-null-guild_id channels;
        # post-pipeline channels is empty.
        # M11 F17 L8 (Leg D) — v28 stripped dm_allowed; bare {id}.
        assert cfg["allowlist"]["peers"] == [{"id": "P1"}]
        assert cfg["allowlist"]["channels"] == []
        assert cfg["allowlist"]["dm_admission"] == "none"

        await conn.close()

    async def test_v22_legacy_row_without_allowlist_untouched(self, tmp_path) -> None:
        """A legacy v21 row whose config has NO ``allowlist`` key is
        left untouched by the v22 row-rewrite. The Pydantic validator
        default handles it at read time.
        """
        db_path = tmp_path / "v22-legacy-no-allowlist.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 22):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connector_accounts ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        legacy_config = json.dumps({"intent": "guild_messages"})
        await conn.execute(
            "INSERT INTO connector_accounts (id, name, type, config) VALUES (?, ?, ?, ?)",
            ("legacy-acct-3", "Legacy", "stub", legacy_config),
        )
        await conn.commit()

        await ensure_schema(conn)

        # Post-v23 (M11 F11 L1): table renamed ``connector_accounts`` →
        # ``connectors``; the v23 row-rewrite preserves the seeded legacy
        # row's config JSON verbatim.
        async with conn.execute(
            "SELECT config FROM connectors WHERE id = ?",
            ("legacy-acct-3",),
        ) as cur:
            row = await cur.fetchone()
        cfg = json.loads(row["config"])
        # No allowlist key was added (untouched legacy row — the v22
        # row-rewrite only mutates rows that HAVE an allowlist).
        assert "allowlist" not in cfg
        # The legacy ``intent`` key is preserved verbatim. Post-v26
        # (M11 F13 L02), every connector also carries
        # ``inference_provider_config_id`` + ``inference_model`` keys
        # (defaulted to None at v26 backfill); the v22-untouched
        # assertion shifts from strict equality to "intent preserved
        # AND no allowlist added" — the v26 keys are additive to
        # EVERY config regardless of allowlist presence.
        assert cfg["intent"] == "guild_messages"
        assert cfg.get("inference_provider_config_id") is None
        assert cfg.get("inference_model") is None

        await conn.close()


class TestSchemaV23:
    """Tests for the v23 migration that renames the connector-account
    terminology across the schema.

    Mission 11 Flight 11 Leg 1: F11 chose "full consistency" over
    "table-only with historical column-name residue". The migration:

    - Row-rewrites ``connector_accounts`` → ``connectors`` (v6/v12/v19
      ceremony — CREATE NEW, INSERT FROM OLD, DROP OLD, ALTER RENAME)
      so the parent table picks up its new name.
    - Row-rewrites ``pending_approvals`` to repoint the FK target at
      ``connectors`` and rename the FK column
      ``connector_account_id`` → ``connector_id``. The supporting
      index ``idx_pending_approvals_account_peer_status`` dies with
      the parent DROP and is recreated against the renamed column.
    - ``ALTER TABLE chat_sessions RENAME COLUMN connector_account_id
      TO connector_id`` (no FK on the column, so ALTER RENAME COLUMN
      suffices). The partial expression index
      ``idx_chat_sessions_external_key`` is dropped + recreated
      against the renamed column expression.
    - ``ALTER TABLE agents RENAME COLUMN connector_account_ids TO
      connector_ids`` (JSON-encoded list column; no FK).

    The Pydantic class is renamed (historical *Account*-suffixed form
    → ``Connector``)
    in the same leg (and the field
    ``AgentConfig.connector_account_ids`` → ``connector_ids``,
    ``PendingApproval.connector_account_id`` → ``connector_id``,
    ``ChatSession.connector_account_id`` → ``connector_id``). The
    grep-gate carve-out documented in the leg artifact explicitly
    permits historical column names inside this migration's body and
    inside prior migrations' bodies (v16/v17/v21) — the v23 SQL is the
    FROM side of the row-rewrite + the source of the ALTER RENAME
    COLUMN statements.

    Mirrors the v19 / v22 ``TestSchemaVNN`` shapes (fresh-DB final-
    shape assertions + legacy-row preservation + idempotency).
    """

    async def test_v23_fresh_db_has_renamed_tables_and_columns(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v23 final-shape surfaces exist:

        - ``connectors`` table exists, ``connector_accounts`` does not.
        - ``chat_sessions.connector_id`` column exists,
          ``connector_account_id`` does not.
        - ``pending_approvals.connector_id`` column exists with FK
          pointing at ``connectors(id)``; ``connector_account_id``
          does not.
        - ``agents.connector_ids`` column exists,
          ``connector_account_ids`` does not.
        - Both partial indexes are present and reference the renamed
          column names.
        """
        db_path = tmp_path / "v23-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 23, CURRENT_VERSION

        # ``connectors`` table exists; old ``connector_accounts`` does not.
        async with conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name IN ('connectors', 'connector_accounts')"
        ) as cur:
            tables = {r["name"] for r in await cur.fetchall()}
        assert "connectors" in tables, tables
        assert "connector_accounts" not in tables, tables

        # ``chat_sessions.connector_id`` exists; old column does not.
        async with conn.execute("PRAGMA table_info(chat_sessions)") as cur:
            cs_cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_id" in cs_cols, cs_cols
        assert "connector_account_id" not in cs_cols, cs_cols

        # ``agents.connector_ids`` exists; old column does not.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            ag_cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_ids" in ag_cols, ag_cols
        assert "connector_account_ids" not in ag_cols, ag_cols

        # ``pending_approvals.connector_id`` exists; old column does not.
        # FK points at ``connectors(id)`` (not ``connector_accounts(id)``).
        async with conn.execute("PRAGMA table_info(pending_approvals)") as cur:
            pa_cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_id" in pa_cols, pa_cols
        assert "connector_account_id" not in pa_cols, pa_cols
        async with conn.execute("PRAGMA foreign_key_list(pending_approvals)") as cur:
            fks = [dict(r) for r in await cur.fetchall()]
        assert len(fks) == 1, fks
        fk = fks[0]
        assert fk["table"] == "connectors", fk
        assert fk["from"] == "connector_id", fk
        assert fk["to"] == "id", fk
        assert fk["on_delete"].upper() == "CASCADE", fk

        # Both partial indexes exist and reference the renamed columns.
        # M11 F12 L3 — v24 renamed the pending_approvals index name
        # from ``idx_pending_approvals_account_peer_status`` to
        # ``idx_pending_approvals_connector_peer_status`` (v23 deferred
        # the cosmetic-rename to the v24 housekeeping sweep). Under
        # full ``ensure_schema`` the v24 index name is what we observe;
        # this assertion is updated to match. The COLUMN expression
        # the index covers (``connector_id``) was set in v23 and is
        # unchanged.
        async with conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' "
            "AND name IN ('idx_chat_sessions_external_key', "
            "'idx_pending_approvals_connector_peer_status')"
        ) as cur:
            indexes = {r["name"]: r["sql"] for r in await cur.fetchall()}
        assert "idx_chat_sessions_external_key" in indexes, indexes
        assert "idx_pending_approvals_connector_peer_status" in indexes, indexes
        # The chat_sessions index references the renamed ``connector_id``.
        assert "connector_id" in indexes["idx_chat_sessions_external_key"], indexes[
            "idx_chat_sessions_external_key"
        ]
        # The pending_approvals index references the renamed column.
        assert "connector_id" in indexes["idx_pending_approvals_connector_peer_status"], indexes[
            "idx_pending_approvals_connector_peer_status"
        ]

        # Head pointer landed at CURRENT_VERSION.
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 23 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v23_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the
        second time: the v23 ``if version < 23:`` guard short-circuits,
        the schema_version table has v23 exactly once, and the renamed
        tables + columns + indexes are still in place."""
        db_path = tmp_path / "v23-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(23) == 1, f"v23 row should appear exactly once: {versions}"

        # Renamed surfaces still present after the second call.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'connectors'"
        ) as cur:
            assert await cur.fetchone() is not None
        async with conn.execute("PRAGMA table_info(chat_sessions)") as cur:
            cs_cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_id" in cs_cols
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            ag_cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_ids" in ag_cols

        await conn.close()

    async def test_v23_legacy_v22_rows_migrate_with_content_preserved(self, tmp_path) -> None:
        """Rows seeded against a hand-built v22-shape DB
        (``connector_accounts`` + ``chat_sessions.connector_account_id``
        + ``pending_approvals.connector_account_id`` +
        ``agents.connector_account_ids``) survive the v23 row-rewrite
        + ALTER RENAME COLUMN with all row content preserved under the
        renamed table + column names.

        Hand-builds a v22-shape schema (post-v22 row-rewrite has no
        schema-shape change vs v21 — the dm_admission rewrite lives
        inside the JSON config column), INSERTs rows into all four
        connector-touching surfaces, sets ``schema_version`` rows up
        to 22, then calls ``ensure_schema`` to apply v23.
        """
        db_path = tmp_path / "v23-from-real-v22.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build schema_version table and seed v1..v22.
        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 23):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))

        # v22-shape connector_accounts (post-v19 CHECK on type).
        await conn.execute(
            "CREATE TABLE connector_accounts ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        # v22-shape chat_sessions (v16-introduced connector-keying
        # columns + v3 base shape).
        await conn.execute(
            "CREATE TABLE chat_sessions ("
            "    id TEXT PRIMARY KEY,"
            "    agent_name TEXT,"
            "    title TEXT DEFAULT 'New chat',"
            "    messages TEXT DEFAULT '[]',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    platform TEXT,"
            "    connector_account_id TEXT,"
            "    channel_id TEXT,"
            "    thread_id TEXT,"
            "    peer_id TEXT,"
            "    session_metadata TEXT,"
            "    last_inbound_at TEXT"
            ")"
        )
        # Partial index that the v23 block drops + recreates.
        await conn.execute(
            "CREATE INDEX idx_chat_sessions_external_key "
            "ON chat_sessions(platform, connector_account_id, channel_id, "
            "COALESCE(thread_id, '')) WHERE platform IS NOT NULL"
        )
        # v22-shape agents (with connector_account_ids, connector_acls,
        # connector_always_listen).
        await conn.execute(
            "CREATE TABLE agents ("
            "    name TEXT PRIMARY KEY,"
            "    description TEXT DEFAULT '',"
            "    provider_config_id TEXT,"
            "    llm_model TEXT DEFAULT '',"
            "    system_prompt TEXT DEFAULT '',"
            "    enabled_tools TEXT,"
            "    disabled_tools TEXT DEFAULT '[]',"
            "    max_iterations INTEGER DEFAULT 20,"
            "    kb_ids TEXT DEFAULT '[]',"
            "    mcp_source_ids TEXT DEFAULT '[]',"
            "    tool_overrides TEXT,"
            "    mcp_overrides TEXT,"
            "    connector_account_ids TEXT,"
            "    connector_acls TEXT,"
            "    connector_always_listen TEXT,"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        # v21-shape pending_approvals (FK to connector_accounts(id)).
        await conn.execute(
            "CREATE TABLE pending_approvals ("
            "    id TEXT PRIMARY KEY,"
            "    connector_account_id TEXT NOT NULL"
            "        REFERENCES connector_accounts(id) ON DELETE CASCADE,"
            "    peer_id TEXT NOT NULL,"
            "    peer_name TEXT NOT NULL,"
            "    preview TEXT NOT NULL,"
            "    received_at TEXT NOT NULL,"
            "    status TEXT NOT NULL"
            "        CHECK (status IN ('pending', 'approved', 'dismissed')),"
            "    resolved_at TEXT"
            ")"
        )
        await conn.execute(
            "CREATE INDEX idx_pending_approvals_account_peer_status "
            "ON pending_approvals (connector_account_id, peer_id, status)"
        )

        # Seed rows into each table so the v23 row-rewrite has content
        # to preserve.
        await conn.execute(
            "INSERT INTO connector_accounts "
            "(id, name, type, config, secrets, idle_timeout_seconds, "
            " session_continuation_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "acct-1",
                "Pre-v23 stub",
                "stub",
                json.dumps({"allowlist": {"channels": [], "dm_admission": "all"}}),
                json.dumps({"BOT_TOKEN": "encrypted-cipher"}),
                900,
                3600,
            ),
        )
        await conn.execute(
            "INSERT INTO agents (name, description, llm_model, connector_account_ids) "
            "VALUES (?, ?, ?, ?)",
            ("agent-1", "Pre-v23 agent", "mock-default", json.dumps(["acct-1"])),
        )
        await conn.execute(
            "INSERT INTO chat_sessions "
            "(id, agent_name, title, platform, connector_account_id, "
            " channel_id, thread_id, peer_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "sess-1",
                "agent-1",
                "Pre-v23 session",
                "stub",
                "acct-1",
                "C1",
                None,
                "P1",
            ),
        )
        await conn.execute(
            "INSERT INTO pending_approvals "
            "(id, connector_account_id, peer_id, peer_name, preview, "
            " received_at, status, resolved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL)",
            (
                "appr-1",
                "acct-1",
                "P1",
                "Peer One",
                "hello",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        await conn.commit()

        # Apply v23.
        await ensure_schema(conn)

        # Connector row survived under the renamed table; all 9 columns
        # round-tripped.
        async with conn.execute(
            "SELECT id, name, type, config, secrets, idle_timeout_seconds, "
            " session_continuation_seconds "
            " FROM connectors WHERE id = 'acct-1'"
        ) as cur:
            acct = await cur.fetchone()
        assert acct is not None
        assert acct["name"] == "Pre-v23 stub"
        assert acct["type"] == "stub"
        assert json.loads(acct["config"])["allowlist"]["dm_admission"] == "all"
        assert json.loads(acct["secrets"])["BOT_TOKEN"] == "encrypted-cipher"
        assert acct["idle_timeout_seconds"] == 900
        assert acct["session_continuation_seconds"] == 3600

        # Agent row survived; connector_ids list preserved verbatim.
        async with conn.execute("SELECT connector_ids FROM agents WHERE name = 'agent-1'") as cur:
            agent = await cur.fetchone()
        assert agent is not None
        assert json.loads(agent["connector_ids"]) == ["acct-1"]

        # Chat-session row survived; connector_id holds the previous
        # value verbatim.
        async with conn.execute(
            "SELECT id, platform, connector_id, channel_id, peer_id "
            "FROM chat_sessions WHERE id = 'sess-1'"
        ) as cur:
            sess = await cur.fetchone()
        assert sess is not None
        assert sess["platform"] == "stub"
        assert sess["connector_id"] == "acct-1"
        assert sess["channel_id"] == "C1"
        assert sess["peer_id"] == "P1"

        # Pending-approval row survived; connector_id holds the previous
        # value; FK to connectors(id) preserved.
        async with conn.execute(
            "SELECT id, connector_id, peer_id, peer_name, preview, status "
            "FROM pending_approvals WHERE id = 'appr-1'"
        ) as cur:
            appr = await cur.fetchone()
        assert appr is not None
        assert appr["connector_id"] == "acct-1"
        assert appr["peer_id"] == "P1"
        assert appr["peer_name"] == "Peer One"
        assert appr["preview"] == "hello"
        assert appr["status"] == "pending"

        # Head pointer landed at CURRENT_VERSION.
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 23 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        # FK CASCADE still works against the renamed FK target: deleting
        # the parent removes the dependent approval.
        await conn.execute("DELETE FROM connectors WHERE id = ?", ("acct-1",))
        await conn.commit()
        async with conn.execute("SELECT COUNT(*) FROM pending_approvals") as cur:
            (count,) = await cur.fetchone()
        assert count == 0, count

        await conn.close()


class TestSchemaV24:
    """Tests for the v24 migration that introduces structured-tuple
    storage for allowlist channels + roles, per-peer ``dm_allowed`` for
    DM-admission gating, and renames the ``dm_admission`` Literal value
    ``"allowlisted-peers-only"`` → ``"admin-approved"`` (operator-
    vocabulary alignment).

    Mission 11 Flight 12 Leg 3. The migration:

    - Row-rewrites ``connectors.config.allowlist`` JSON for every row:
      ``peers: list[str]`` → ``peers: list[{id, dm_allowed}]``;
      ``channels: list[str]`` → ``channels: list[{guild_id=None, channel_id}]``;
      ``roles: list[str]`` → ``roles: list[{guild_id=None, role_id}]``;
      ``dm_admission`` Literal-value rename ``"allowlisted-peers-only"``
      → ``"admin-approved"``.
    - Row-rewrites ``agents.connector_acls`` JSON the same way in
      lockstep (per-agent shape mirrors account-scope).
    - DROP + CREATE the ``pending_approvals`` index:
      ``idx_pending_approvals_account_peer_status`` →
      ``idx_pending_approvals_connector_peer_status``.

    DM Admission collapse rule per the F12 L3 leg spec:

    - ``dm_admission == "all"`` → all peers get ``dm_allowed=True``
    - ``dm_admission == "none"`` → all peers get ``dm_allowed=False``
    - ``dm_admission`` set to ``"allowlisted-peers-only"`` OR absent-
      but-allowlist-present → all peers get ``dm_allowed=True`` AND
      ``dm_admission`` rewritten to ``"admin-approved"``
    - ``allowlist`` absent entirely → no peers to migrate

    Mirrors the v22 / v23 ``TestSchemaVNN`` shapes (fresh-DB final-
    shape assertions + legacy-row preservation + idempotency).
    """

    async def test_v24_fresh_db_shape(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v24 final shape:

        - A connector created through the Pydantic validator with
          structured-tuple allowlist round-trips through SQLite.
        - The pre-v24 flat shape is REJECTED by the validator.
        - The renamed index ``idx_pending_approvals_connector_peer_status``
          exists; the old name does not.
        - Head pointer at ``CURRENT_VERSION``.
        """
        db_path = tmp_path / "v24-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        assert CURRENT_VERSION >= 24, CURRENT_VERSION

        # Renamed index exists; old name does not.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_pending_approvals_%_peer_status'"
        ) as cur:
            indexes = {r["name"] for r in await cur.fetchall()}
        assert "idx_pending_approvals_connector_peer_status" in indexes, indexes
        assert "idx_pending_approvals_account_peer_status" not in indexes, indexes

        # Validator accepts post-v28 bare ``{id}`` peers.
        # M11 F12 L5: post-v25 the validator REQUIRES non-null
        # ``guild_id`` on channel/role entries. M11 F17 L8 (Leg D):
        # post-v28 peers are bare ``{id}``; ``dm_allowed`` is rejected.
        from the_one.db.models import Connector

        accepted = Connector.model_validate(
            {
                "id": "acct-x",
                "name": "x",
                "type": "stub",
                "config": {
                    "allowlist": {
                        "peers": [{"id": "U1"}],
                        "channels": [{"guild_id": "G1", "channel_id": "C1"}],
                        "roles": [{"guild_id": "G1", "role_id": "R1"}],
                        "dm_admission": "admin-approved",
                    }
                },
            }
        )
        assert accepted.config["allowlist"]["peers"] == [{"id": "U1"}]

        # Validator REJECTS ``{id, dm_allowed}`` shape (post-v28).
        with pytest.raises(Exception):
            Connector.model_validate(
                {
                    "id": "acct-dm",
                    "name": "dm",
                    "type": "stub",
                    "config": {
                        "allowlist": {
                            "peers": [{"id": "U1", "dm_allowed": True}],
                            "channels": [],
                        }
                    },
                }
            )

        # Validator REJECTS the pre-v24 flat shape.
        with pytest.raises(Exception):  # pydantic ValidationError
            Connector.model_validate(
                {
                    "id": "acct-y",
                    "name": "y",
                    "type": "stub",
                    "config": {
                        "allowlist": {
                            "peers": ["U1"],
                            "channels": [],
                        }
                    },
                }
            )

        # Validator REJECTS the pre-rename Literal value.
        with pytest.raises(Exception):
            Connector.model_validate(
                {
                    "id": "acct-z",
                    "name": "z",
                    "type": "stub",
                    "config": {
                        "allowlist": {
                            "peers": [],
                            "channels": [],
                            "dm_admission": "allowlisted-peers-only",
                        }
                    },
                }
            )

        # Head pointer landed at CURRENT_VERSION.
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 24 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v24_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ``ensure_schema`` twice on a fresh DB is a no-op the
        second time: the v24 ``if version < 24:`` guard short-circuits,
        and ``schema_version`` has v24 exactly once."""
        db_path = tmp_path / "v24-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(24) == 1, f"v24 row should appear exactly once: {versions}"

        # Renamed index still present after the second call.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name = 'idx_pending_approvals_connector_peer_status'"
        ) as cur:
            assert await cur.fetchone() is not None

        await conn.close()

    async def test_v24_legacy_v23_row_migration_preserves_data(self, tmp_path) -> None:
        """v23-shape connector rows with the flat 5-axis allowlist
        migrate to v24 with all data preserved per the collapse rules.

        Sub-cases (one row each):
          (a) ``dm_admission="all"`` → peers get ``dm_allowed=True``;
              dm_admission stays ``"all"``.
          (b) ``dm_admission="none"`` → peers get ``dm_allowed=False``;
              dm_admission stays ``"none"``.
          (c) ``dm_admission="allowlisted-peers-only"`` → peers get
              ``dm_allowed=True``; dm_admission rewritten to
              ``"admin-approved"``.
          (d) ``dm_admission`` ABSENT but allowlist present → defaulted
              to ``"allowlisted-peers-only"`` then rewritten to
              ``"admin-approved"``; peers get ``dm_allowed=True``.
        """
        db_path = tmp_path / "v24-from-v23.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build schema_version table and seed v1..v23.
        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 24):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))

        # v23-shape connectors table (post-v23 rename + post-v19 CHECK).
        await conn.execute(
            "CREATE TABLE connectors ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        # v23-shape pending_approvals (FK to connectors(id), index with
        # the pre-v24 name).
        await conn.execute(
            "CREATE TABLE pending_approvals ("
            "    id TEXT PRIMARY KEY,"
            "    connector_id TEXT NOT NULL"
            "        REFERENCES connectors(id) ON DELETE CASCADE,"
            "    peer_id TEXT NOT NULL,"
            "    peer_name TEXT NOT NULL,"
            "    preview TEXT NOT NULL,"
            "    received_at TEXT NOT NULL,"
            "    status TEXT NOT NULL"
            "        CHECK (status IN ('pending', 'approved', 'dismissed')),"
            "    resolved_at TEXT"
            ")"
        )
        await conn.execute(
            "CREATE INDEX idx_pending_approvals_account_peer_status "
            "ON pending_approvals (connector_id, peer_id, status)"
        )
        # v23-shape agents table for the parallel rewrite.
        await conn.execute(
            "CREATE TABLE agents ("
            "    name TEXT PRIMARY KEY,"
            "    description TEXT DEFAULT '',"
            "    provider_config_id TEXT,"
            "    llm_model TEXT DEFAULT '',"
            "    system_prompt TEXT DEFAULT '',"
            "    enabled_tools TEXT,"
            "    disabled_tools TEXT DEFAULT '[]',"
            "    max_iterations INTEGER DEFAULT 20,"
            "    kb_ids TEXT DEFAULT '[]',"
            "    mcp_source_ids TEXT DEFAULT '[]',"
            "    tool_overrides TEXT,"
            "    mcp_overrides TEXT,"
            "    connector_ids TEXT,"
            "    connector_acls TEXT,"
            "    connector_always_listen TEXT,"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )

        # Seed four connector rows covering the dm_admission sub-cases.
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-all",
                "All",
                "stub",
                json.dumps(
                    {
                        "allowlist": {
                            "peers": ["U1", "U2"],
                            "channels": ["C1"],
                            "roles": ["R1"],
                            "dm_admission": "all",
                        }
                    }
                ),
            ),
        )
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-none",
                "None",
                "stub",
                json.dumps(
                    {
                        "allowlist": {
                            "peers": ["U3"],
                            "channels": [],
                            "dm_admission": "none",
                        }
                    }
                ),
            ),
        )
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-apo",
                "APO",
                "stub",
                json.dumps(
                    {
                        "allowlist": {
                            "peers": ["U4"],
                            "channels": ["C2"],
                            "dm_admission": "allowlisted-peers-only",
                        }
                    }
                ),
            ),
        )
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-absent",
                "Absent",
                "stub",
                json.dumps(
                    {
                        "allowlist": {
                            "peers": ["U5"],
                            "channels": [],
                        }
                    }
                ),
            ),
        )
        await conn.commit()

        # Apply v24.
        await ensure_schema(conn)

        # Sub-cases (a)–(d) check the post-full-pipeline state.
        # v24 writes ``{id, dm_allowed}`` from flat strings;
        # v25 strips orphan-null channels/roles;
        # v28 strips ``dm_allowed`` from account-scope peers.
        # Post-pipeline: bare ``{id}`` peers regardless of
        # the original dm_admission value.
        #
        # M11 F12 L5: the v24 migration emits channel/role entries with
        # ``guild_id=None`` (legacy-permissive backfill); the chained v25
        # cleanup that runs IN THE SAME ``ensure_schema`` call then
        # deletes those orphan-null entries. Post-pipeline the channels
        # and roles lists are empty for these v23-shape rows.
        # M11 F17 L8 (Leg D): v28 strips dm_allowed from all account-scope
        # peer entries (intentional: any approved peer = can-DM now).

        # Sub-case (a): dm_admission == "all".
        async with conn.execute("SELECT config FROM connectors WHERE id = 'acct-all'") as cur:
            row = await cur.fetchone()
        config = json.loads(row["config"])
        allowlist = config["allowlist"]
        assert allowlist["dm_admission"] == "all", allowlist
        assert allowlist["peers"] == [
            {"id": "U1"},
            {"id": "U2"},
        ], allowlist
        assert allowlist["channels"] == [], allowlist
        assert allowlist["roles"] == [], allowlist

        # Sub-case (b): dm_admission == "none" → peers bare {id}.
        async with conn.execute("SELECT config FROM connectors WHERE id = 'acct-none'") as cur:
            row = await cur.fetchone()
        config = json.loads(row["config"])
        allowlist = config["allowlist"]
        assert allowlist["dm_admission"] == "none", allowlist
        assert allowlist["peers"] == [{"id": "U3"}], allowlist

        # Sub-case (c): "allowlisted-peers-only" → rewritten to
        # "admin-approved"; peers get bare {id} (v28 stripped dm_allowed).
        async with conn.execute("SELECT config FROM connectors WHERE id = 'acct-apo'") as cur:
            row = await cur.fetchone()
        config = json.loads(row["config"])
        allowlist = config["allowlist"]
        assert allowlist["dm_admission"] == "admin-approved", allowlist
        assert allowlist["peers"] == [{"id": "U4"}], allowlist
        # M11 F12 L5: v25 cleanup deletes the orphan-null-guild_id
        # channel entry emitted by v24's legacy-permissive backfill.
        assert allowlist["channels"] == [], allowlist

        # Sub-case (d): dm_admission absent → defaulted then rewritten
        # to "admin-approved"; peers bare {id} (v28 stripped dm_allowed).
        async with conn.execute("SELECT config FROM connectors WHERE id = 'acct-absent'") as cur:
            row = await cur.fetchone()
        config = json.loads(row["config"])
        allowlist = config["allowlist"]
        assert allowlist["dm_admission"] == "admin-approved", allowlist
        assert allowlist["peers"] == [{"id": "U5"}], allowlist

        # Head pointer landed at CURRENT_VERSION.
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 24 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v24_agents_connector_acls_rewrite(self, tmp_path) -> None:
        """``agents.connector_acls`` JSON column row-rewrite works in
        lockstep with the connectors rewrite. Per-agent ``peers`` get
        ``dm_allowed=True`` by default (structural uniformity);
        ``admit_dms`` stays as-is."""
        db_path = tmp_path / "v24-agents-acls.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 24):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connectors ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        await conn.execute(
            "CREATE TABLE pending_approvals ("
            "    id TEXT PRIMARY KEY,"
            "    connector_id TEXT NOT NULL"
            "        REFERENCES connectors(id) ON DELETE CASCADE,"
            "    peer_id TEXT NOT NULL,"
            "    peer_name TEXT NOT NULL,"
            "    preview TEXT NOT NULL,"
            "    received_at TEXT NOT NULL,"
            "    status TEXT NOT NULL"
            "        CHECK (status IN ('pending', 'approved', 'dismissed')),"
            "    resolved_at TEXT"
            ")"
        )
        await conn.execute(
            "CREATE INDEX idx_pending_approvals_account_peer_status "
            "ON pending_approvals (connector_id, peer_id, status)"
        )
        await conn.execute(
            "CREATE TABLE agents ("
            "    name TEXT PRIMARY KEY,"
            "    description TEXT DEFAULT '',"
            "    provider_config_id TEXT,"
            "    llm_model TEXT DEFAULT '',"
            "    system_prompt TEXT DEFAULT '',"
            "    enabled_tools TEXT,"
            "    disabled_tools TEXT DEFAULT '[]',"
            "    max_iterations INTEGER DEFAULT 20,"
            "    kb_ids TEXT DEFAULT '[]',"
            "    mcp_source_ids TEXT DEFAULT '[]',"
            "    tool_overrides TEXT,"
            "    mcp_overrides TEXT,"
            "    connector_ids TEXT,"
            "    connector_acls TEXT,"
            "    connector_always_listen TEXT,"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        # Seed a single agent row carrying a v23-shape connector_acls
        # JSON keyed by 2 accounts, with mixed axes populated.
        await conn.execute(
            "INSERT INTO agents (name, connector_acls) VALUES (?, ?)",
            (
                "agent-1",
                json.dumps(
                    {
                        "acct-1": {
                            "peers": ["U1", "U2"],
                            "channels": ["C1"],
                            "roles": ["R1"],
                            "admit_dms": False,
                        },
                        "acct-2": {
                            "peers": None,
                            "channels": [],
                        },
                    }
                ),
            ),
        )
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute("SELECT connector_acls FROM agents WHERE name = 'agent-1'") as cur:
            row = await cur.fetchone()
        acls = json.loads(row["connector_acls"])
        # acct-1 — populated axes get structured shape; admit_dms stays
        # False. M11 F12 L5: the v25 cleanup that runs IN THE SAME
        # ``ensure_schema`` call deletes the orphan-null-guild_id
        # channel/role entries emitted by v24's legacy-permissive
        # backfill. Post-pipeline these per-agent-acl lists are empty
        # for v23-shape seeded rows.
        #
        # M11 F13 L2: v24 writes per-agent peers with
        # ``dm_allowed=True`` default (structural uniformity); the v26
        # block running in the SAME ``ensure_schema`` pipeline then
        # strips the field from per-agent peers (F12 footgun
        # retirement). Post-pipeline assertion reflects the stripped
        # shape — per-agent peers entries are bare ``{"id": ...}``
        # dicts.
        assert acls["acct-1"]["peers"] == [
            {"id": "U1"},
            {"id": "U2"},
        ]
        assert acls["acct-1"]["channels"] == []
        assert acls["acct-1"]["roles"] == []
        assert acls["acct-1"]["admit_dms"] is False
        # acct-2 — None peers stay None; empty channels list stays
        # empty (but is now a list of dicts — i.e. empty list).
        assert acls["acct-2"]["peers"] is None
        assert acls["acct-2"]["channels"] == []

        await conn.close()

    async def test_v24_index_rename(self, tmp_path) -> None:
        """After v24, the old index name is gone and the new one
        exists with the correct column expression."""
        db_path = tmp_path / "v24-index-rename.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        async with conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_pending_approvals_%_peer_status'"
        ) as cur:
            indexes = {r["name"]: r["sql"] for r in await cur.fetchall()}
        assert "idx_pending_approvals_account_peer_status" not in indexes, indexes
        assert "idx_pending_approvals_connector_peer_status" in indexes, indexes
        sql = indexes["idx_pending_approvals_connector_peer_status"]
        # The new index references connector_id, peer_id, status.
        assert "connector_id" in sql, sql
        assert "peer_id" in sql, sql
        assert "status" in sql, sql

        await conn.close()


class TestSchemaV25:
    """Tests for the v25 migration that deletes orphan null-``guild_id``
    channel/role entries from ``connectors.config.allowlist`` AND
    ``agents.connector_acls``.

    Mission 11 Flight 12 Leg 5 — hierarchical Server-as-parent UI
    alignment. The migration backs the L5 substrate tightening: post-
    v25 the Pydantic validators on both ``Connector.config`` and
    ``AgentConfig.connector_acls`` REJECT null-``guild_id`` channel and
    role entries. The hierarchical UI emits guild-scoped tuples
    exclusively (Server-as-parent layout); the v24 legacy-permissive
    backfill (``guild_id=None`` for entries from pre-v24 flat shape)
    is no longer accepted.

    Operator framing at L5 planning (recorded in flight log): "app is
    not live, just enforce going forward" — no data preservation for
    the orphan-null entries.

    Migration semantics:

    - Row-rewrite ``connectors.config.allowlist``: delete entries from
      the ``channels`` and ``roles`` lists where ``guild_id is None``.
      All other entries (including the new ``"*"`` wildcard sentinel
      for ``channel_id`` / ``role_id``) are preserved.
    - Row-rewrite ``agents.connector_acls``: same deletion across each
      per-account payload.
    - Idempotent: the per-row UPDATE only fires when the list shape
      changes; re-running ``ensure_schema`` is a no-op (no separate
      segment marker needed — unlike v21's CREATE INDEX pattern).
    """

    async def test_v25_deletes_orphan_null_guild_id_channels_and_roles(self, tmp_path) -> None:
        """Seed a v24-shape DB with mixed null + structured channel/role
        entries; verify v25 deletes the null-``guild_id`` orphans and
        preserves everything else (including the new ``"*"`` wildcard
        sentinel and concrete-guild entries).
        """
        db_path = tmp_path / "v25-orphan-deletion.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build a v24-shape DB (schema_version v1..v24 seeded;
        # connectors + pending_approvals + agents tables present).
        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 25):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connectors ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        await conn.execute(
            "CREATE TABLE pending_approvals ("
            "    id TEXT PRIMARY KEY,"
            "    connector_id TEXT NOT NULL"
            "        REFERENCES connectors(id) ON DELETE CASCADE,"
            "    peer_id TEXT NOT NULL,"
            "    peer_name TEXT NOT NULL,"
            "    preview TEXT NOT NULL,"
            "    received_at TEXT NOT NULL,"
            "    status TEXT NOT NULL"
            "        CHECK (status IN ('pending', 'approved', 'dismissed')),"
            "    resolved_at TEXT"
            ")"
        )
        await conn.execute(
            "CREATE INDEX idx_pending_approvals_connector_peer_status "
            "ON pending_approvals (connector_id, peer_id, status)"
        )

        # Seed a connector with a mix of null + structured + wildcard
        # entries across channels and roles.
        # Note: the peers entry uses ``{id, dm_allowed}`` shape (pre-v28
        # storage) to test that v28 strips it in the same pipeline.
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-mixed",
                "Mixed",
                "stub",
                json.dumps(
                    {
                        "allowlist": {
                            "peers": [{"id": "U1", "dm_allowed": True}],
                            "channels": [
                                # Orphan — should be deleted.
                                {"guild_id": None, "channel_id": "C-legacy"},
                                # Concrete — preserved.
                                {"guild_id": "G1", "channel_id": "C-keep"},
                                # Wildcard sentinel — preserved.
                                {"guild_id": "G2", "channel_id": "*"},
                            ],
                            "roles": [
                                # Orphan — deleted.
                                {"guild_id": None, "role_id": "R-legacy"},
                                # Concrete — preserved.
                                {"guild_id": "G1", "role_id": "R-keep"},
                                # Wildcard sentinel — preserved.
                                {"guild_id": "G2", "role_id": "*"},
                            ],
                            "guilds": ["G1", "G2"],
                            "dm_admission": "admin-approved",
                        }
                    }
                ),
            ),
        )
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute("SELECT config FROM connectors WHERE id = 'acct-mixed'") as cur:
            row = await cur.fetchone()
        cfg = json.loads(row["config"])
        allowlist = cfg["allowlist"]

        # Channels: orphan deleted, concrete + wildcard preserved.
        assert allowlist["channels"] == [
            {"guild_id": "G1", "channel_id": "C-keep"},
            {"guild_id": "G2", "channel_id": "*"},
        ], allowlist["channels"]

        # Roles: orphan deleted, concrete + wildcard preserved.
        assert allowlist["roles"] == [
            {"guild_id": "G1", "role_id": "R-keep"},
            {"guild_id": "G2", "role_id": "*"},
        ], allowlist["roles"]

        # Peers: v28 stripped dm_allowed; bare {id} post-pipeline.
        # M11 F17 L8 (Leg D).
        assert allowlist["peers"] == [{"id": "U1"}]
        assert allowlist["guilds"] == ["G1", "G2"]
        assert allowlist["dm_admission"] == "admin-approved"

        # Head pointer landed at CURRENT_VERSION.
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 25 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v25_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ``ensure_schema`` twice on a fresh DB is a no-op the
        second time: the v25 ``if version < 25:`` guard short-circuits,
        and ``schema_version`` has v25 exactly once. Also covers the
        case where a row already has only guild-scoped entries: the
        per-row UPDATE only fires when the filtered list differs from
        the original (natural idempotency without a separate segment
        marker)."""
        db_path = tmp_path / "v25-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(25) == 1, f"v25 row should appear exactly once: {versions}"

        await conn.close()

    async def test_v25_agents_connector_acls_orphan_deletion(self, tmp_path) -> None:
        """``agents.connector_acls`` JSON column row-rewrite deletes the
        same orphan-null-``guild_id`` entries across each per-account
        payload, in lockstep with the connectors rewrite. Wildcard and
        concrete entries are preserved.
        """
        db_path = tmp_path / "v25-agents-orphan-deletion.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 25):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connectors ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        await conn.execute(
            "CREATE TABLE pending_approvals ("
            "    id TEXT PRIMARY KEY,"
            "    connector_id TEXT NOT NULL"
            "        REFERENCES connectors(id) ON DELETE CASCADE,"
            "    peer_id TEXT NOT NULL,"
            "    peer_name TEXT NOT NULL,"
            "    preview TEXT NOT NULL,"
            "    received_at TEXT NOT NULL,"
            "    status TEXT NOT NULL"
            "        CHECK (status IN ('pending', 'approved', 'dismissed')),"
            "    resolved_at TEXT"
            ")"
        )
        await conn.execute(
            "CREATE INDEX idx_pending_approvals_connector_peer_status "
            "ON pending_approvals (connector_id, peer_id, status)"
        )
        await conn.execute(
            "CREATE TABLE agents ("
            "    name TEXT PRIMARY KEY,"
            "    description TEXT DEFAULT '',"
            "    provider_config_id TEXT,"
            "    llm_model TEXT DEFAULT '',"
            "    system_prompt TEXT DEFAULT '',"
            "    enabled_tools TEXT,"
            "    disabled_tools TEXT DEFAULT '[]',"
            "    max_iterations INTEGER DEFAULT 20,"
            "    kb_ids TEXT DEFAULT '[]',"
            "    mcp_source_ids TEXT DEFAULT '[]',"
            "    tool_overrides TEXT,"
            "    mcp_overrides TEXT,"
            "    connector_ids TEXT,"
            "    connector_acls TEXT,"
            "    connector_always_listen TEXT,"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        await conn.execute(
            "INSERT INTO agents (name, connector_acls) VALUES (?, ?)",
            (
                "agent-1",
                json.dumps(
                    {
                        "acct-A": {
                            "peers": [{"id": "U1", "dm_allowed": True}],
                            "channels": [
                                # Orphan — deleted.
                                {"guild_id": None, "channel_id": "C-old"},
                                # Concrete — preserved.
                                {"guild_id": "G1", "channel_id": "C-keep"},
                            ],
                            "roles": [
                                # Wildcard — preserved.
                                {"guild_id": "G1", "role_id": "*"},
                                # Orphan — deleted.
                                {"guild_id": None, "role_id": "R-old"},
                            ],
                        },
                        "acct-B": {
                            # Already clean — no UPDATE fires for this
                            # payload (idempotency at the per-payload level).
                            "peers": None,
                            "channels": [
                                {"guild_id": "G2", "channel_id": "*"},
                            ],
                        },
                    }
                ),
            ),
        )
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute("SELECT connector_acls FROM agents WHERE name = 'agent-1'") as cur:
            row = await cur.fetchone()
        acls = json.loads(row["connector_acls"])

        # acct-A: orphans deleted, concrete + wildcard preserved.
        assert acls["acct-A"]["channels"] == [
            {"guild_id": "G1", "channel_id": "C-keep"},
        ]
        assert acls["acct-A"]["roles"] == [
            {"guild_id": "G1", "role_id": "*"},
        ]
        # M11 F13 L2 — per-agent peers entries are stripped of
        # ``dm_allowed`` by the v26 migration running in the SAME
        # ``ensure_schema`` pipeline (F12 footgun retirement). The
        # seed above carries the field (legitimate post-v25 stored
        # data); post-pipeline assertion reflects the v26 strip.
        assert acls["acct-A"]["peers"] == [{"id": "U1"}]

        # acct-B: untouched (already clean).
        assert acls["acct-B"]["peers"] is None
        assert acls["acct-B"]["channels"] == [
            {"guild_id": "G2", "channel_id": "*"},
        ]

        await conn.close()

    async def test_v25_validator_rejects_null_guild_id_channel(self, tmp_path) -> None:
        """Post-v25 the Pydantic validator on ``Connector.config``
        REJECTS channel/role entries with null ``guild_id`` (the L3
        ``str | None`` annotation is tightened to ``str``). This
        complements the migration: any subsequent write attempting to
        re-introduce orphan-null entries fails fast at the Pydantic
        boundary. The wildcard sentinel ``"*"`` is the storage shape
        for "any channel of this guild" — the null is no longer a
        valid storage value.
        """
        from the_one.db.models import Connector

        # Null guild_id on a channel entry → rejected.
        with pytest.raises(Exception):  # pydantic ValidationError
            Connector.model_validate(
                {
                    "id": "acct-bad-channel",
                    "name": "bad",
                    "type": "stub",
                    "config": {
                        "allowlist": {
                            "peers": [],
                            "channels": [{"guild_id": None, "channel_id": "C1"}],
                        }
                    },
                }
            )

        # Null guild_id on a role entry → rejected.
        with pytest.raises(Exception):
            Connector.model_validate(
                {
                    "id": "acct-bad-role",
                    "name": "bad",
                    "type": "stub",
                    "config": {
                        "allowlist": {
                            "peers": [],
                            "channels": [],
                            "roles": [{"guild_id": None, "role_id": "R1"}],
                        }
                    },
                }
            )

        # Wildcard ``channel_id="*"`` with concrete guild_id is
        # accepted (the L5 "any channel of this guild" semantic).
        accepted = Connector.model_validate(
            {
                "id": "acct-wildcard",
                "name": "ok",
                "type": "stub",
                "config": {
                    "allowlist": {
                        "peers": [],
                        "channels": [{"guild_id": "G1", "channel_id": "*"}],
                        "roles": [{"guild_id": "G1", "role_id": "*"}],
                    }
                },
            }
        )
        assert accepted.config["allowlist"]["channels"] == [{"guild_id": "G1", "channel_id": "*"}]
        assert accepted.config["allowlist"]["roles"] == [{"guild_id": "G1", "role_id": "*"}]


class TestSchemaV26:
    """Tests for the v26 migration that (a) adds the connector-scope
    inference LLM keys to ``connectors.config`` with ``None`` defaults
    and logs always_listen=true connectors at migration time, and
    (b) strips ``dm_allowed`` from per-agent ``connector_acls[*].
    peers[*]`` entries (F12 footgun retirement).

    Mission 11 Flight 13 Leg 2.
    """

    async def test_v26_fresh_db_shape(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v26 final shape:

        - Head pointer at CURRENT_VERSION (>= 26).
        - A connector with the two new keys round-trips via Pydantic.
        - A per-agent peers entry WITHOUT ``dm_allowed`` validates.
        - A per-agent peers entry WITH ``dm_allowed`` is REJECTED.
        """
        db_path = tmp_path / "v26-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert max(versions) == CURRENT_VERSION, versions
        assert CURRENT_VERSION >= 26, CURRENT_VERSION

        from the_one.db.models import Connector

        connector = Connector.model_validate(
            {
                "id": "acct-v26",
                "name": "v26",
                "type": "stub",
                "config": {
                    "inference_provider_config_id": "p1",
                    "inference_model": "m1",
                },
            }
        )
        assert connector.config["inference_provider_config_id"] == "p1"
        assert connector.config["inference_model"] == "m1"

        cfg_ok = AgentConfig(
            name="agent-ok",
            connector_acls={
                "acct-a": {"peers": [{"id": "u1"}], "channels": []},
            },
        )
        assert cfg_ok.connector_acls == {
            "acct-a": {"peers": [{"id": "u1"}], "channels": []},
        }

        with pytest.raises(Exception):  # pydantic ValidationError
            AgentConfig(
                name="agent-bad",
                connector_acls={
                    "acct-a": {
                        "peers": [{"id": "u1", "dm_allowed": True}],
                        "channels": [],
                    },
                },
            )

        await conn.close()

    async def test_v26_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ``ensure_schema`` twice leaves v26 in
        ``schema_version`` exactly once (UPDATE-only-when-changed
        short-circuits the second pass)."""
        db_path = tmp_path / "v26-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(26) == 1, f"v26 row should appear exactly once: {versions}"

        await conn.close()

    async def test_v26_legacy_v25_row_migration_strips_dm_allowed(self, tmp_path) -> None:
        """Hand-build a v25-shape DB with ``agents.connector_acls``
        payloads carrying per-agent peer entries with ``dm_allowed``
        keys (True and False); run ``ensure_schema``; assert each
        per-agent peer entry post-pipeline has NO ``dm_allowed`` key.
        """
        db_path = tmp_path / "v26-strip-dm-allowed.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 26):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connectors ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        await conn.execute(
            "CREATE TABLE pending_approvals ("
            "    id TEXT PRIMARY KEY,"
            "    connector_id TEXT NOT NULL"
            "        REFERENCES connectors(id) ON DELETE CASCADE,"
            "    peer_id TEXT NOT NULL,"
            "    peer_name TEXT NOT NULL,"
            "    preview TEXT NOT NULL,"
            "    received_at TEXT NOT NULL,"
            "    status TEXT NOT NULL"
            "        CHECK (status IN ('pending', 'approved', 'dismissed')),"
            "    resolved_at TEXT"
            ")"
        )
        await conn.execute(
            "CREATE INDEX idx_pending_approvals_connector_peer_status "
            "ON pending_approvals (connector_id, peer_id, status)"
        )
        await conn.execute(
            "CREATE TABLE agents ("
            "    name TEXT PRIMARY KEY,"
            "    description TEXT DEFAULT '',"
            "    provider_config_id TEXT,"
            "    llm_model TEXT DEFAULT '',"
            "    system_prompt TEXT DEFAULT '',"
            "    enabled_tools TEXT,"
            "    disabled_tools TEXT DEFAULT '[]',"
            "    max_iterations INTEGER DEFAULT 20,"
            "    kb_ids TEXT DEFAULT '[]',"
            "    mcp_source_ids TEXT DEFAULT '[]',"
            "    tool_overrides TEXT,"
            "    mcp_overrides TEXT,"
            "    connector_ids TEXT,"
            "    connector_acls TEXT,"
            "    connector_always_listen TEXT,"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        await conn.execute(
            "INSERT INTO agents (name, connector_acls) VALUES (?, ?)",
            (
                "agent-strip",
                json.dumps(
                    {
                        "acct-A": {
                            "peers": [
                                {"id": "U1", "dm_allowed": True},
                                {"id": "U2", "dm_allowed": False},
                            ],
                            "channels": [],
                        },
                        "acct-B": {
                            # Already clean (no dm_allowed) — no UPDATE
                            # should fire for this payload but the agent
                            # row's other payload triggers the UPDATE
                            # anyway; the assertion confirms acct-B is
                            # untouched.
                            "peers": [{"id": "U3"}],
                            "channels": [],
                        },
                    }
                ),
            ),
        )
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute(
            "SELECT connector_acls FROM agents WHERE name = 'agent-strip'"
        ) as cur:
            row = await cur.fetchone()
        acls = json.loads(row["connector_acls"])
        assert acls["acct-A"]["peers"] == [
            {"id": "U1"},
            {"id": "U2"},
        ], acls
        assert acls["acct-B"]["peers"] == [{"id": "U3"}], acls

        await conn.close()

    async def test_v26_connector_config_inference_fields_added(self, tmp_path) -> None:
        """Hand-build a v25-shape DB with ``connectors.config`` rows
        lacking the inference keys; run ``ensure_schema``; assert each
        connector's config has the two new keys with None defaults.
        """
        db_path = tmp_path / "v26-inference-keys.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 26):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connectors ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            ("acct-1", "Account 1", "stub", json.dumps({})),
        )
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-2",
                "Account 2",
                "stub",
                json.dumps({"intent": "guild_messages"}),
            ),
        )
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute("SELECT id, config FROM connectors ORDER BY id") as cur:
            rows = [(r["id"], json.loads(r["config"])) for r in await cur.fetchall()]
        for connector_id, config in rows:
            assert "inference_provider_config_id" in config, (connector_id, config)
            assert config["inference_provider_config_id"] is None, (connector_id, config)
            assert "inference_model" in config, (connector_id, config)
            assert config["inference_model"] is None, (connector_id, config)

        # The non-inference key on acct-2 is preserved.
        cfg_2 = dict(rows)["acct-2"]
        assert cfg_2["intent"] == "guild_messages"

        await conn.close()

    async def test_v26_logs_affected_always_listen_connectors(self, tmp_path, caplog) -> None:
        """Seed a v25-shape DB with two connectors: one with
        ``always_listen=true``, one with ``always_listen=false``. Run
        ``ensure_schema`` under
        ``caplog.at_level(logging.INFO, logger="the_one.db.schema")``;
        assert EXACTLY one ``logger.info`` line fired and that it
        mentions the always_listen=true connector's ID and label.
        """
        db_path = tmp_path / "v26-always-listen-log.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 26):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connectors ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-loud",
                "Loud Bot",
                "stub",
                json.dumps({"always_listen": True}),
            ),
        )
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-quiet",
                "Quiet Bot",
                "stub",
                json.dumps({"always_listen": False}),
            ),
        )
        await conn.commit()

        with caplog.at_level(logging.INFO, logger="the_one.db.schema"):
            await ensure_schema(conn)

        v26_records = [
            r
            for r in caplog.records
            if r.name == "the_one.db.schema" and "v26: connector" in r.getMessage()
        ]
        assert len(v26_records) == 1, [(r.name, r.getMessage()) for r in v26_records]
        msg = v26_records[0].getMessage()
        assert "acct-loud" in msg, msg
        assert "Loud Bot" in msg, msg
        assert "acct-quiet" not in msg, msg
        assert "Quiet Bot" not in msg, msg

        await conn.close()

    # ── v27: unify guild scoping onto config.allowlist.guilds ───────
    # M11 F14 L02 — the standalone top-level config.guilds ("Scope to
    # servers") is folded into config.allowlist.guilds (order-preserving
    # dedup-union) and the top-level key removed. The allowlist "Servers"
    # axis is now the single source of truth for both inbound-admission
    # ACL and slash-command registration.

    async def test_v27_fresh_db_shape(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v27 final shape:

        - Head pointer at CURRENT_VERSION (== max(versions), >= 27).
        - A connector with config.allowlist.guilds round-trips via
          Pydantic and carries no top-level ``guilds`` key.
        """
        db_path = tmp_path / "v27-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert max(versions) == CURRENT_VERSION, versions
        assert CURRENT_VERSION >= 27, CURRENT_VERSION

        from the_one.db.models import Connector

        connector = Connector.model_validate(
            {
                "id": "acct-v27",
                "name": "v27",
                "type": "stub",
                "config": {
                    "allowlist": {
                        "guilds": ["G1", "G2"],
                        "peers": [],
                        "channels": [],
                    }
                },
            }
        )
        assert connector.config["allowlist"]["guilds"] == ["G1", "G2"]
        assert "guilds" not in connector.config

        await conn.close()

    async def test_v27_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ``ensure_schema`` twice leaves v27 in
        ``schema_version`` exactly once (the pop-yields-None path
        short-circuits the second pass once top-level ``guilds`` is
        gone)."""
        db_path = tmp_path / "v27-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(27) == 1, f"v27 row should appear exactly once: {versions}"

        await conn.close()

    async def test_v27_folds_top_level_guilds_into_allowlist(self, tmp_path) -> None:
        """Hand-build a v26-shape DB with connector rows carrying a
        top-level ``config.guilds``; run ``ensure_schema``; assert each
        row's top-level ``guilds`` is gone and the ids landed in
        ``config.allowlist.guilds`` as an order-preserving dedup-union.

        Covered rows:
        - ``acct-union``: both top-level guilds AND a populated
          allowlist.guilds with an overlapping id → union, dedup,
          order preserved.
        - ``acct-only-top``: top-level guilds, no allowlist → allowlist
          created with the folded ids.
        - ``acct-empty-top``: top-level ``guilds=[]`` → key dropped, no
          allowlist created.
        - ``acct-none``: no top-level guilds at all → row untouched.

        Round-trips every post-migration config through
        ``Connector.model_validate`` to prove no top-level ``guilds``
        survives the fold and the allowlist.guilds list[str] guard
        accepts the result.
        """
        db_path = tmp_path / "v27-fold.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 27):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connectors ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-union",
                "Union Bot",
                "stub",
                json.dumps(
                    {
                        "guilds": ["111", "222"],
                        "allowlist": {
                            "guilds": ["222", "333"],
                            "peers": [],
                            "channels": [],
                        },
                    }
                ),
            ),
        )
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-only-top",
                "Only Top Bot",
                "stub",
                json.dumps({"guilds": ["444", "555"]}),
            ),
        )
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-empty-top",
                "Empty Top Bot",
                "stub",
                json.dumps({"guilds": [], "intent": "guild_messages"}),
            ),
        )
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-none",
                "No Guilds Bot",
                "stub",
                json.dumps({"intent": "guild_messages"}),
            ),
        )
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute("SELECT id, config FROM connectors ORDER BY id") as cur:
            rows = {r["id"]: json.loads(r["config"]) for r in await cur.fetchall()}

        # Union: existing-first order preserved, folded ids appended,
        # duplicate "222" not repeated.
        assert "guilds" not in rows["acct-union"], rows["acct-union"]
        assert rows["acct-union"]["allowlist"]["guilds"] == ["222", "333", "111"], rows[
            "acct-union"
        ]

        # Only top-level: allowlist created with the folded ids and the
        # validator-required (empty) peers/channels axes.
        assert "guilds" not in rows["acct-only-top"], rows["acct-only-top"]
        assert rows["acct-only-top"]["allowlist"]["guilds"] == ["444", "555"], rows["acct-only-top"]
        assert rows["acct-only-top"]["allowlist"]["peers"] == [], rows["acct-only-top"]
        assert rows["acct-only-top"]["allowlist"]["channels"] == [], rows["acct-only-top"]

        # Empty top-level: key dropped, no allowlist gratuitously created.
        assert "guilds" not in rows["acct-empty-top"], rows["acct-empty-top"]
        assert "allowlist" not in rows["acct-empty-top"], rows["acct-empty-top"]
        assert rows["acct-empty-top"]["intent"] == "guild_messages"

        # No guilds at all: row untouched.
        assert "guilds" not in rows["acct-none"], rows["acct-none"]
        assert "allowlist" not in rows["acct-none"], rows["acct-none"]
        assert rows["acct-none"]["intent"] == "guild_messages"

        # Every post-migration config round-trips via Pydantic with no
        # top-level ``guilds`` surviving the fold.
        from the_one.db.models import Connector

        for connector_id, config in rows.items():
            validated = Connector.model_validate(
                {
                    "id": connector_id,
                    "name": connector_id,
                    "type": "stub",
                    "config": config,
                }
            )
            assert "guilds" not in validated.config, (connector_id, validated.config)

        await conn.close()


# ── M11 F17 L8 (Leg D) ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSchemaV28:
    """Tests for the v28 migration that strips ``dm_allowed`` from
    account-scope ``connectors.config.allowlist.peers`` entries.

    Mission 11 Flight 17 Leg 8 (dm-allowlist-simplify).
    """

    async def test_v28_fresh_db_shape(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v28 final shape:

        - Head pointer at CURRENT_VERSION (== 28).
        - The post-v28 Pydantic validator ACCEPTS bare ``{id}`` peers.
        - The validator REJECTS ``{id, dm_allowed}`` shape.
        """
        db_path = tmp_path / "v28-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert max(versions) == CURRENT_VERSION, versions
        # v28 must have run (CURRENT_VERSION advances past 28 in later legs).
        assert CURRENT_VERSION >= 28, CURRENT_VERSION
        assert 28 in versions, versions

        from the_one.db.models import Connector

        # Bare {id} peers: accepted.
        ok = Connector.model_validate(
            {
                "id": "acct-v28",
                "name": "v28",
                "type": "stub",
                "config": {
                    "allowlist": {
                        "peers": [{"id": "P1"}, {"id": "P2"}],
                        "channels": [],
                        "dm_admission": "admin-approved",
                    }
                },
            }
        )
        assert ok.config["allowlist"]["peers"] == [{"id": "P1"}, {"id": "P2"}]

        # {id, dm_allowed} peers: rejected by v28 validator.
        with pytest.raises(Exception):  # pydantic ValidationError
            Connector.model_validate(
                {
                    "id": "acct-bad",
                    "name": "bad",
                    "type": "stub",
                    "config": {
                        "allowlist": {
                            "peers": [{"id": "P1", "dm_allowed": True}],
                            "channels": [],
                        }
                    },
                }
            )

        await conn.close()

    async def test_v28_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ``ensure_schema`` twice leaves v28 in
        ``schema_version`` exactly once."""
        db_path = tmp_path / "v28-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(28) == 1, f"v28 row should appear exactly once: {versions}"

        await conn.close()

    async def test_v28_strips_dm_allowed_from_legacy_rows(self, tmp_path) -> None:
        """Hand-build a v27-shape DB with ``connectors.config`` rows
        carrying ``{id, dm_allowed}`` peers; run ``ensure_schema``;
        assert each peer entry post-pipeline is a bare ``{id}`` dict.

        Covers the main v28 transform path: idempotency guard skips
        already-bare rows; update-when-changed fires only for rows
        with ``dm_allowed`` present.
        """
        db_path = tmp_path / "v28-strip-dm-allowed.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await conn.execute(
            "CREATE TABLE schema_version ("
            "    version INTEGER PRIMARY KEY,"
            "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        for v in range(1, 28):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "CREATE TABLE connectors ("
            "    id TEXT PRIMARY KEY,"
            "    type TEXT NOT NULL CHECK (type IN ('discord', 'stub')),"
            "    config TEXT DEFAULT '{}',"
            "    secrets TEXT DEFAULT '{}',"
            "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "    name TEXT NOT NULL DEFAULT '',"
            "    idle_timeout_seconds INTEGER NULL,"
            "    session_continuation_seconds INTEGER NULL"
            ")"
        )

        # Row with {id, dm_allowed} peers (pre-v28 shape).
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-strip",
                "Strip",
                "stub",
                json.dumps(
                    {
                        "allowlist": {
                            "peers": [
                                {"id": "U1", "dm_allowed": True},
                                {"id": "U2", "dm_allowed": False},
                            ],
                            "channels": [],
                            "dm_admission": "admin-approved",
                        }
                    }
                ),
            ),
        )

        # Row already in bare {id} shape (idempotency path — no UPDATE).
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-already-bare",
                "AlreadyBare",
                "stub",
                json.dumps(
                    {
                        "allowlist": {
                            "peers": [{"id": "U3"}],
                            "channels": [],
                            "dm_admission": "all",
                        }
                    }
                ),
            ),
        )

        # Row with no allowlist (should be skipped entirely).
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config) VALUES (?, ?, ?, ?)",
            (
                "acct-no-allowlist",
                "NoAllowlist",
                "stub",
                json.dumps({"intent": "dm_only"}),
            ),
        )

        await conn.commit()
        await ensure_schema(conn)

        # acct-strip: dm_allowed stripped; peers bare {id}.
        async with conn.execute("SELECT config FROM connectors WHERE id = 'acct-strip'") as cur:
            row = await cur.fetchone()
        cfg = json.loads(row["config"])
        assert cfg["allowlist"]["peers"] == [
            {"id": "U1"},
            {"id": "U2"},
        ], cfg["allowlist"]["peers"]
        assert cfg["allowlist"]["dm_admission"] == "admin-approved"

        # acct-already-bare: idempotent — no change.
        async with conn.execute(
            "SELECT config FROM connectors WHERE id = 'acct-already-bare'"
        ) as cur:
            row = await cur.fetchone()
        cfg = json.loads(row["config"])
        assert cfg["allowlist"]["peers"] == [{"id": "U3"}], cfg
        assert cfg["allowlist"]["dm_admission"] == "all"

        # acct-no-allowlist: untouched.
        async with conn.execute(
            "SELECT config FROM connectors WHERE id = 'acct-no-allowlist'"
        ) as cur:
            row = await cur.fetchone()
        cfg = json.loads(row["config"])
        assert "allowlist" not in cfg, cfg
        assert cfg["intent"] == "dm_only"

        # Head pointer at 28.
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 28 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()


class TestSchemaV29:
    """Tests for the v29 migration: additive replay-context columns on
    ``pending_approvals``.

    M11 F17 L10 (Leg F) — respond-on-approval. Four nullable TEXT/INTEGER
    columns: ``original_message``, ``channel_id``, ``thread_id``, ``is_dm``.
    """

    async def test_v29_fresh_db_has_replay_columns(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → v29 columns exist on pending_approvals."""
        db_path = tmp_path / "v29-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        # CURRENT_VERSION is now at least 29.
        assert CURRENT_VERSION >= 29, (
            f"CURRENT_VERSION must be >= 29 after Leg F v29 migration (got {CURRENT_VERSION})"
        )

        # All four replay-context columns are present, TEXT or INTEGER, nullable.
        async with conn.execute("PRAGMA table_info(pending_approvals)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}

        for col_name, expected_type in (
            ("original_message", "TEXT"),
            ("channel_id", "TEXT"),
            ("thread_id", "TEXT"),
            ("is_dm", "INTEGER"),
        ):
            assert col_name in cols, (
                f"v29 migration missing: column `{col_name}` absent on "
                "pending_approvals after fresh ensure_schema"
            )
            col = cols[col_name]
            assert col["type"] == expected_type, (col_name, col["type"])
            # notnull == 0 means nullable — all four must be nullable for
            # back-compat with pre-v29 rows.
            assert col["notnull"] == 0, (col_name, col["notnull"])
            # No explicit DEFAULT — dflt_value is Python None (not string "NULL").
            assert col["dflt_value"] is None, (col_name, col["dflt_value"])

        # schema_version contains 29.
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        assert row[0] == CURRENT_VERSION

        await conn.close()

    async def test_v29_migration_on_v28_fixture_adds_columns_preserves_rows(self, tmp_path) -> None:
        """Hand-build a v28-shaped DB with a pending_approvals row (no
        replay-context columns yet), rewind to v28, run ensure_schema, and
        verify the four columns exist and the existing row reads back with
        NULLs for the new fields."""
        db_path = tmp_path / "v29-from-v28.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Bootstrap the full schema to v28 shape.
        await ensure_schema(conn)

        # Insert a pre-v29 pending_approvals row (omitting the new columns).
        # Use a bare connector row first (pending_approvals has an FK cascade).
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config, secrets) VALUES (?, ?, ?, ?, ?)",
            ("c-v28", "v28connector", "stub", "{}", "{}"),
        )
        await conn.execute(
            "INSERT INTO pending_approvals "
            "(id, connector_id, peer_id, peer_name, preview, received_at, status) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), 'pending')",
            ("pa-v28", "c-v28", "U-pre29", "PreUser", "hello"),
        )
        await conn.commit()

        # Rewind schema_version to v28 to simulate an upgrade path.
        await conn.execute("DELETE FROM schema_version WHERE version >= 29")
        await conn.commit()

        # Re-run ensure_schema — only v29 fires (v28 is already in the table).
        await ensure_schema(conn)

        # All four columns now exist.
        async with conn.execute("PRAGMA table_info(pending_approvals)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        for col_name in ("original_message", "channel_id", "thread_id", "is_dm"):
            assert col_name in cols, f"column {col_name!r} missing after v29 migration"

        # The pre-v29 row reads back with NULLs for the new fields.
        async with conn.execute(
            "SELECT original_message, channel_id, thread_id, is_dm "
            "FROM pending_approvals WHERE id = 'pa-v28'"
        ) as cur:
            row = await cur.fetchone()
        assert row["original_message"] is None
        assert row["channel_id"] is None
        assert row["thread_id"] is None
        assert row["is_dm"] is None

        # Head pointer at CURRENT_VERSION.
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        assert row[0] == CURRENT_VERSION

        await conn.close()

    async def test_v29_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice leaves v29 in schema_version exactly once."""
        db_path = tmp_path / "v29-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(29) == 1, f"v29 row should appear exactly once: {versions}"

        await conn.close()


assert CURRENT_VERSION >= 30, (
    f"CURRENT_VERSION must be >= 30 for TestSchemaV30 tests (got {CURRENT_VERSION})"
)


class TestSchemaV30:
    """Tests for the v30 migration: additive chat-history retention column on
    ``agents``.

    M13 F01 L01 — per-agent chat-history retention. One NOT NULL INTEGER column
    with DEFAULT 30: ``chat_history_retention_days``.
    """

    async def test_v30_fresh_db_has_retention_column(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → chat_history_retention_days exists on agents."""
        db_path = tmp_path / "v30-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        # Column present, correct type, NOT NULL, default 30.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}

        assert "chat_history_retention_days" in cols, (
            "v30 migration missing: column `chat_history_retention_days` absent on "
            "agents after fresh ensure_schema"
        )
        col = cols["chat_history_retention_days"]
        assert col["type"] == "INTEGER", col["type"]
        assert col["notnull"] == 1, col["notnull"]
        assert col["dflt_value"] == "30", col["dflt_value"]

        # schema_version head pointer at CURRENT_VERSION (30).
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        assert row[0] == CURRENT_VERSION

        await conn.close()

    async def test_v30_migration_on_v29_fixture_adds_column_backfills_rows(self, tmp_path) -> None:
        """Hand-build a v29-shaped DB with an existing agent row (no
        chat_history_retention_days column yet), run ensure_schema, and verify
        the column exists and the existing agent row reads back with 30 (the
        DEFAULT backfill)."""
        db_path = tmp_path / "v30-from-v29.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build a minimal v29-shaped schema (agents table WITHOUT the new
        # column, schema_version seeded at 29). This is a fresh file, so there
        # is no table to skip with IF NOT EXISTS.
        await conn.execute(
            """
            CREATE TABLE agents (
                name TEXT PRIMARY KEY,
                description TEXT,
                provider_config_id TEXT,
                llm_model TEXT,
                system_prompt TEXT,
                enabled_tools TEXT,
                disabled_tools TEXT NOT NULL DEFAULT '[]',
                max_iterations INTEGER NOT NULL DEFAULT 20,
                kb_ids TEXT NOT NULL DEFAULT '[]',
                mcp_source_ids TEXT NOT NULL DEFAULT '[]',
                tool_overrides TEXT,
                mcp_overrides TEXT,
                connector_ids TEXT NOT NULL DEFAULT '[]',
                connector_acls TEXT,
                connector_always_listen TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        await conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
        await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (29,))
        # Insert an agent row before migration (no chat_history_retention_days column).
        await conn.execute(
            "INSERT INTO agents (name, disabled_tools, kb_ids, mcp_source_ids, connector_ids, "
            "created_at, updated_at) VALUES (?, '[]', '[]', '[]', '[]', datetime('now'), "
            "datetime('now'))",
            ("pre-v30-agent",),
        )
        await conn.commit()

        # Run ensure_schema — only v30 fires (v29 is already in schema_version).
        await ensure_schema(conn)

        # Column now exists.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "chat_history_retention_days" in cols, (
            "column `chat_history_retention_days` missing after v30 migration"
        )

        # Existing agent row reads back with 30 (DEFAULT backfill).
        async with conn.execute(
            "SELECT chat_history_retention_days FROM agents WHERE name = 'pre-v30-agent'"
        ) as cur:
            row = await cur.fetchone()
        assert row[0] == 30, f"expected 30 (DEFAULT backfill), got {row[0]}"

        # Head pointer at CURRENT_VERSION.
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        assert row[0] == CURRENT_VERSION

        await conn.close()

    async def test_v30_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice leaves v30 in schema_version exactly once."""
        db_path = tmp_path / "v30-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(30) == 1, f"v30 row should appear exactly once: {versions}"

        await conn.close()


class TestSchemaV31:
    """Tests for the v31 migration: global ``app_metadata`` kv store.

    M13 F03 L01 — brand-new ``app_metadata (key TEXT PRIMARY KEY, value TEXT
    NOT NULL)`` table created via CREATE TABLE IF NOT EXISTS. Holds the daily
    purge's ``last_purge_at`` (wired up by Leg 3). The fresh-DB path runs every
    migration block in sequence and so exercises the new block.
    """

    async def test_v31_fresh_db_has_app_metadata_table(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → app_metadata exists, schema_version at 31."""
        db_path = tmp_path / "v31-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        # app_metadata table present.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='app_metadata'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None, (
            "v31 migration missing: table `app_metadata` absent after fresh ensure_schema"
        )

        # Columns: key TEXT PRIMARY KEY, value TEXT NOT NULL.
        async with conn.execute("PRAGMA table_info(app_metadata)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        assert "key" in cols and "value" in cols, cols
        assert cols["key"]["pk"] == 1, cols["key"]
        assert cols["value"]["type"] == "TEXT", cols["value"]["type"]
        assert cols["value"]["notnull"] == 1, cols["value"]["notnull"]

        # schema_version head pointer at CURRENT_VERSION (31).
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        assert row[0] == CURRENT_VERSION

        await conn.close()

    async def test_v31_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice leaves v31 in schema_version exactly once."""
        db_path = tmp_path / "v31-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(31) == 1, f"v31 row should appear exactly once: {versions}"

        await conn.close()
