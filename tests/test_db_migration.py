"""Tests for JSON → SQLite migration."""

from __future__ import annotations

import json
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
        # v12 extended llm_providers.type CHECK to allow 'openrouter'.
        assert CURRENT_VERSION == 12, (
            f"CURRENT_VERSION must be 12 after openrouter v12 migration (got {CURRENT_VERSION})"
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
        await conn.execute("DELETE FROM schema_version WHERE version = 12")
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
