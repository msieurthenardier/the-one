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
    """Set up a SQLite connection and a JSON agents directory.

    F04 L01 (Mission 18): the connection is opened via ``async with`` so
    the close is guaranteed in-loop even if a consuming test raises
    (e.g. an assertion failure) — a bare trailing ``await conn.close()``
    after ``yield`` is skipped when the test body raises, orphaning the
    connection's worker thread on a to-be-torn-down event loop (the
    `Event loop is closed` teardown artifact; see maintenance report
    2026-07-10 finding T1). This fixture is consumed by 4 tests, so a
    leak here was the highest-leverage fragile site.
    """
    db_path = tmp_path / "test.db"
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        store = SQLiteAgentStore(conn)

        with patch("the_one.db.migration.settings") as mock_settings:
            mock_settings.agents_dir = agents_dir
            yield store, agents_dir


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

    async def test_v14_chain_from_v13_lands_empty_connectors(self, tmp_path) -> None:
        """A row seeded against a hand-built v13 schema (no ``name`` column)
        runs through the v14 ALTER cleanly — and then, per Mission 23
        Flight 1's v38 (DD-2), is cleared along with every other legacy
        ``connectors`` row.

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
        # schema_version to CURRENT_VERSION.
        await ensure_schema(conn)

        # Mission 23 Flight 1 (backend-removal leg, DD-2): v38 clears
        # every row from ``connectors`` (legacy rows are retired
        # regardless of shape) — the seeded row no longer survives to
        # present day. This still proves the oldest possible upgrade
        # path (a real pre-v14 ``connector_accounts`` row) runs the full
        # v14→v38 chain without error and lands the table empty, exactly
        # as DD-2 intends. The row-content assertions this test used to
        # make (name/type backfilled correctly) are superseded — the row
        # is gone before anything reads it.
        async with conn.execute("SELECT id FROM connectors WHERE id = 'seeded'") as cur:
            row = await cur.fetchone()
        assert row is None
        async with conn.execute("SELECT COUNT(*) FROM connectors") as cur:
            assert (await cur.fetchone())[0] == 0

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

    async def test_v15_chain_from_v14_lands_empty_connectors(self, tmp_path) -> None:
        """A row seeded against a hand-built v14 schema (no
        ``idle_timeout_seconds`` column) runs through the v15 ALTER
        cleanly — and then, per Mission 23 Flight 1's v38 (DD-2), is
        cleared along with every other legacy ``connectors`` row.

        Bootstraps a real v14-shape ``connector_accounts`` table (NO
        ``idle_timeout_seconds`` column) so the v15 ALTER actually runs
        against a row that pre-exists without the column. Modeled on
        ``TestSchemaV14.test_v14_chain_from_v13_lands_empty_connectors``.
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
        # the seeded row's ``idle_timeout_seconds`` with NULL, and
        # continue through the chain to CURRENT_VERSION.
        await ensure_schema(conn)

        # Mission 23 Flight 1 (backend-removal leg, DD-2): v38 clears
        # every row from ``connectors`` — the seeded row no longer
        # survives to present day. This still proves the v14→v38 chain
        # runs without error from a real pre-v15 row and lands the table
        # empty.
        async with conn.execute("SELECT id FROM connectors WHERE id = 'seeded-v14'") as cur:
            row = await cur.fetchone()
        assert row is None
        async with conn.execute("SELECT COUNT(*) FROM connectors") as cur:
            assert (await cur.fetchone())[0] == 0

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
        # F04 L01 (Mission 18): this connection was the deterministic leak
        # (maintenance report T1) — opened here but never closed, which is
        # why the aiosqlite worker-thread `Event loop is closed` teardown
        # warning got attributed to the next class, TestSchemaV17. `async
        # with` guarantees the in-loop close regardless of how the test exits.
        async with aiosqlite.connect(str(db_path)) as conn:
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
                "INSERT INTO connector_accounts"
                " (id, name, type, config, secrets, idle_timeout_seconds)"
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

            # Mission 23 Flight 1 (backend-removal leg, DD-2): v38 clears
            # every row from ``connectors`` — the seeded connector row no
            # longer survives to present day (unlike the chat_sessions
            # row above, which v38 never touches). This still proves the
            # v15→v38 chain runs without error against a real pre-v16
            # connector row.
            async with conn.execute("SELECT id FROM connectors WHERE id = 'seeded-account'") as cur:
                acc_row = await cur.fetchone()
            assert acc_row is None
            async with conn.execute("SELECT COUNT(*) FROM connectors") as cur:
                assert (await cur.fetchone())[0] == 0

            # Head pointer landed at CURRENT_VERSION (≥16).
            async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
                versions = [r[0] for r in await cur.fetchall()]
            assert 16 in versions, versions
            assert max(versions) == CURRENT_VERSION, versions


class TestSchemaV17:
    """Tests for the v17 migration that historically added
    agents.connector_account_ids (renamed ``connector_ids`` by v23).

    Mission 23 Flight 1 (backend-removal leg, DD-2): v38 DROPs this
    column outright, and ``AgentConfig`` no longer has a ``connector_ids``
    field — so nothing observes the column past ensure_schema's end on a
    live DB. v17's block itself is frozen history (append-only migration
    chain) and still runs on every upgrade; these tests now verify chain
    integrity (no crash, stamp idempotency, a real legacy row survives
    the ADD-then-DROP round trip and stays loadable) rather than the
    since-retired column's survival.
    """

    async def test_v17_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, no duplicate schema_version rows for v17."""
        db_path = tmp_path / "v17-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(17) == 1, f"v17 row should appear exactly once: {versions}"

        # v38 drops the column v17 added; a fresh/double-migrated DB
        # never carries it.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_ids" not in cols
        assert "connector_account_ids" not in cols

        await conn.close()

    async def test_v17_chain_from_v16_leaves_agent_loadable(self, tmp_path) -> None:
        """A row seeded against a hand-built v16 schema (no
        ``connector_account_ids`` column) runs through the v17 ALTER (adds
        the column) and then v38 (drops it) without error — the agent
        stays loadable via ``SQLiteAgentStore`` throughout.

        Hand-builds a v16-shape ``agents`` table (no connector_account_ids
        column), INSERTs a row, sets ``schema_version`` rows up to 16,
        then calls ``ensure_schema``. Mirrors
        ``TestSchemaV14.test_v14_chain_from_v13_lands_empty_connectors``.
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

        # Mission 23 Flight 1 (DD-2): the column v17 added (then v23
        # renamed) is gone — v38 drops it. Chain integrity, not survival,
        # is what this test now proves.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_ids" not in cols
        assert "connector_account_ids" not in cols

        # The pre-existing row is untouched by the add-then-drop round
        # trip and stays loadable via the repository.
        store = SQLiteAgentStore(conn)
        loaded = await store.load("legacy-agent")
        assert loaded.name == "legacy-agent"
        assert loaded.description == "Pre-v17 agent"

        # Head pointer landed at CURRENT_VERSION (≥17).
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 17 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()


class TestSchemaV18:
    """Tests for the v18 migration that historically added
    agents.connector_acls.

    Mission 23 Flight 1 (backend-removal leg, DD-2): v38 DROPs this
    column outright, and ``AgentConfig`` no longer has a
    ``connector_acls`` field. v18's block itself is frozen history and
    still runs on every upgrade; these tests now verify chain integrity
    rather than the since-retired column's survival — see
    ``TestSchemaV17``'s docstring for the same reasoning.
    """

    async def test_v18_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, no duplicate schema_version rows for v18."""
        db_path = tmp_path / "v18-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(18) == 1, f"v18 row should appear exactly once: {versions}"

        # v38 drops the column v18 added; a fresh/double-migrated DB
        # never carries it.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_acls" not in cols

        await conn.close()

    async def test_v18_chain_from_v17_leaves_agent_loadable(self, tmp_path) -> None:
        """A row seeded against a hand-built v17 schema (no
        ``connector_acls`` column) runs through the v18 ALTER (adds the
        column) and then v38 (drops it) without error — the agent stays
        loadable via ``SQLiteAgentStore`` throughout.

        Hand-builds a v17-shape ``agents`` table (with
        ``connector_account_ids`` but no ``connector_acls`` column),
        INSERTs a row, sets ``schema_version`` rows up to 17, then calls
        ``ensure_schema``. Mirrors
        ``TestSchemaV17.test_v17_chain_from_v16_leaves_agent_loadable``.
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

        # Mission 23 Flight 1 (DD-2): the column v18 added is gone —
        # v38 drops it. Chain integrity, not survival, is what this
        # test now proves.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_acls" not in cols

        # The pre-existing row is untouched by the add-then-drop round
        # trip and stays loadable via the repository.
        store = SQLiteAgentStore(conn)
        loaded = await store.load("legacy-v17-agent")
        assert loaded.name == "legacy-v17-agent"
        assert loaded.description == "Pre-v18 agent"

        # Head pointer landed at CURRENT_VERSION (≥18).
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 18 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()


class TestSchemaV20:
    """Tests for the v20 migration that historically added
    agents.connector_always_listen.

    Mission 23 Flight 1 (backend-removal leg, DD-2): v38 DROPs this
    column outright, and ``AgentConfig`` no longer has a
    ``connector_always_listen`` field. v20's block itself is frozen
    history and still runs on every upgrade; these tests now verify
    chain integrity rather than the since-retired column's survival —
    see ``TestSchemaV17``'s docstring for the same reasoning.
    """

    async def test_v20_migration_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice on a fresh DB is a no-op the second
        time: no errors, no duplicate schema_version rows for v20."""
        db_path = tmp_path / "v20-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call — must be a no-op

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(20) == 1, f"v20 row should appear exactly once: {versions}"

        # v38 drops the column v20 added; a fresh/double-migrated DB
        # never carries it.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_always_listen" not in cols

        await conn.close()

    async def test_v20_chain_from_v19_leaves_agent_loadable(self, tmp_path) -> None:
        """A row seeded against a hand-built v19 schema (no
        ``connector_always_listen`` column) runs through the v20 ALTER
        (adds the column) and then v38 (drops it) without error — the
        agent stays loadable via ``SQLiteAgentStore`` throughout.

        Hand-builds a v19-shape ``agents`` table (with ``connector_acls``
        but no ``connector_always_listen`` column), INSERTs a row, sets
        ``schema_version`` rows up to 19, then calls ``ensure_schema``.
        Mirrors
        ``TestSchemaV18.test_v18_chain_from_v17_leaves_agent_loadable``.
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

        # Mission 23 Flight 1 (DD-2): the column v20 added is gone —
        # v38 drops it. Chain integrity, not survival, is what this
        # test now proves.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_always_listen" not in cols

        # The pre-existing row is untouched by the add-then-drop round
        # trip and stays loadable via the repository.
        store = SQLiteAgentStore(conn)
        loaded = await store.load("legacy-v19-agent")
        assert loaded.name == "legacy-v19-agent"
        assert loaded.description == "Pre-v20 agent"

        # Head pointer landed at CURRENT_VERSION (≥20).
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 20 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()


# TestSchemaV21 (the migration that historically added the
# ``pending_approvals`` table) is deleted: Mission 23 Flight 1's v38
# (DD-2) DROPs the table outright (not just its rows), so every behavior
# the class's tests pinned — columns, FK CASCADE, the status CHECK
# constraint, the supporting index — is moot once the table is gone,
# which it always is after a full ``ensure_schema`` run. v21's block
# itself is frozen history and still runs on every upgrade (creating the
# table so v38 has something to drop, on the oldest possible upgrade
# path); ``TestSchemaV38`` covers that a seeded pre-v38
# ``pending_approvals`` table + rows are cleanly dropped, and the
# fresh-DB idempotency tests elsewhere in this file cover v21's CREATE
# TABLE not erroring.


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

    async def test_v22_chain_from_v21_empty_channels_lands_empty_connectors(self, tmp_path) -> None:
        """A legacy v21 row whose ``allowlist.channels`` is empty/absent
        runs through v22's ``dm_admission="all"`` row-rewrite and the
        rest of the chain without error — then, per Mission 23 Flight 1's
        v38 (DD-2), is cleared along with every other legacy ``connectors``
        row.
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

        # Mission 23 Flight 1 (backend-removal leg, DD-2): v38 clears
        # every row from ``connectors`` — the seeded legacy row (and
        # whatever v22/v24/v25/v28 rewrote its config JSON into along
        # the way) no longer survives to present day. This still proves
        # the v21→v38 chain — including v22's dm_admission row-rewrite —
        # runs without error against a real legacy row.
        async with conn.execute(
            "SELECT id FROM connectors WHERE id = ?",
            ("legacy-acct-1",),
        ) as cur:
            row = await cur.fetchone()
        assert row is None
        async with conn.execute("SELECT COUNT(*) FROM connectors") as cur:
            assert (await cur.fetchone())[0] == 0

        # Head pointer landed at CURRENT_VERSION.
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 22 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()

    async def test_v22_chain_from_v21_nonempty_channels_lands_empty_connectors(
        self, tmp_path
    ) -> None:
        """A legacy v21 row whose ``allowlist.channels`` is non-empty
        runs through v22's ``dm_admission="none"`` row-rewrite and the
        rest of the chain without error — then, per Mission 23 Flight 1's
        v38 (DD-2), is cleared along with every other legacy ``connectors``
        row.
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

        # Mission 23 Flight 1 (backend-removal leg, DD-2): v38 clears
        # every row from ``connectors`` — the seeded legacy row no
        # longer survives to present day. This still proves the
        # v21→v38 chain — including v22/v24/v25/v28's successive
        # row-rewrites — runs without error against a real legacy row.
        async with conn.execute(
            "SELECT id FROM connectors WHERE id = ?",
            ("legacy-acct-2",),
        ) as cur:
            row = await cur.fetchone()
        assert row is None
        async with conn.execute("SELECT COUNT(*) FROM connectors") as cur:
            assert (await cur.fetchone())[0] == 0

        await conn.close()

    async def test_v22_chain_from_v21_no_allowlist_lands_empty_connectors(self, tmp_path) -> None:
        """A legacy v21 row whose config has NO ``allowlist`` key runs
        through v22's row-rewrite (a no-op for this row) and the rest of
        the chain without error — then, per Mission 23 Flight 1's v38
        (DD-2), is cleared along with every other legacy ``connectors``
        row.
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

        # Mission 23 Flight 1 (backend-removal leg, DD-2): v38 clears
        # every row from ``connectors`` — the seeded legacy row no
        # longer survives to present day. This still proves the
        # v21→v38 chain runs without error against a real legacy row
        # with no ``allowlist`` key.
        async with conn.execute(
            "SELECT id FROM connectors WHERE id = ?",
            ("legacy-acct-3",),
        ) as cur:
            row = await cur.fetchone()
        assert row is None
        async with conn.execute("SELECT COUNT(*) FROM connectors") as cur:
            assert (await cur.fetchone())[0] == 0

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
        - The chat_sessions partial index is present and references the
          renamed column name.

        Mission 23 Flight 1 (backend-removal leg, DD-2): ``agents``'s
        renamed column and the ``pending_approvals`` table + its index
        are dropped outright by v38 — those parts of v23's historical
        rename are no longer observable in the final schema and are not
        asserted here. ``TestSchemaV38`` covers that a genuine pre-v23
        (``connector_account_id``-named) ``pending_approvals`` row still
        upgrades and drops cleanly.
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

        # The chat_sessions partial index exists and references the
        # renamed column.
        async with conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' "
            "AND name = 'idx_chat_sessions_external_key'"
        ) as cur:
            indexes = {r["name"]: r["sql"] for r in await cur.fetchall()}
        assert "idx_chat_sessions_external_key" in indexes, indexes
        assert "connector_id" in indexes["idx_chat_sessions_external_key"], indexes[
            "idx_chat_sessions_external_key"
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
        surfaces v38 doesn't drop are still in place."""
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

        await conn.close()

    async def test_v23_legacy_v22_rows_chain_to_v38(self, tmp_path) -> None:
        """Rows seeded against a hand-built v22-shape DB
        (``connector_accounts`` + ``chat_sessions.connector_account_id``
        + ``pending_approvals.connector_account_id`` +
        ``agents.connector_account_ids``) run through the v23 row-rewrite
        + ALTER RENAME COLUMN and the rest of the chain without error.
        Mission 23 Flight 1's v38 (DD-2) then clears/drops three of the
        four surfaces (``connectors`` rows, ``pending_approvals``,
        ``agents.connector_ids``); only ``chat_sessions``'s connector-
        keying columns (a kept piece) survive with their content intact.

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

        # Apply v23 (and the rest of the chain, through v38).
        await ensure_schema(conn)

        # Mission 23 Flight 1 (backend-removal leg, DD-2): v38 clears
        # every row from ``connectors`` and drops both
        # ``pending_approvals`` and ``agents.connector_ids`` outright —
        # none of those three survive to present day, regardless of the
        # v23 row-rewrite's correctness. This still proves the v22→v38
        # chain runs without error against real legacy rows on all four
        # connector-touching surfaces.
        async with conn.execute("SELECT COUNT(*) FROM connectors") as cur:
            assert (await cur.fetchone())[0] == 0
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            ag_cols = {r["name"] for r in await cur.fetchall()}
        assert "connector_ids" not in ag_cols
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_approvals'"
        ) as cur:
            assert (await cur.fetchone()) is None

        # Chat-session row survived; connector_id holds the previous
        # value verbatim (chat_sessions and its connector-keying columns
        # are KEPT — v38 never touches this table).
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

        # Agent row itself survived (only the connector_ids column was
        # dropped).
        async with conn.execute("SELECT name FROM agents WHERE name = 'agent-1'") as cur:
            assert (await cur.fetchone()) is not None

        # Head pointer landed at CURRENT_VERSION.
        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert 23 in versions, versions
        assert max(versions) == CURRENT_VERSION, versions

        await conn.close()


# TestSchemaV24 (the migration that historically row-rewrote
# ``connectors.config.allowlist`` + ``agents.connector_acls`` into the
# structured-tuple shape, and renamed the ``pending_approvals`` index) is
# deleted: Mission 23 Flight 1's v38 (DD-2) clears every ``connectors``
# row, drops ``agents.connector_acls`` outright, and drops
# ``pending_approvals`` (and its index) outright — every surface this
# class's tests observed is gone from the final schema regardless of
# v24's row-rewrite correctness. v24's block itself is frozen history
# and still runs on every upgrade; ``TestSchemaV38`` covers the pre-v38
# drop, and the fresh-DB idempotency tests elsewhere in this file cover
# v24's DDL not erroring. See ``TestSchemaV21``'s comment for the same
# reasoning.


# TestSchemaV25 (the migration that historically deleted orphan
# null-``guild_id`` channel/role entries from ``connectors.config.
# allowlist`` and ``agents.connector_acls``, plus the ``Connector.config``
# reserved-keys validator that rejected them going forward) is deleted:
# Mission 23 Flight 1 (DD-2, and the backend-removal leg's step 4) clears
# every ``connectors`` row, drops ``agents.connector_acls`` outright, AND
# deletes the ``Connector.config`` reserved-keys validator itself (see
# ``the_one/db/models.py`` — only the model core + ``ChatSession`` keying
# fields are kept). Every surface and validator this class's tests
# exercised is gone. v25's block itself is frozen history and still runs
# on every upgrade; the fresh-DB idempotency tests elsewhere in this file
# cover its DDL not erroring. See ``TestSchemaV21``'s comment for the
# same reasoning.


# TestSchemaV26 (covering v26 and v27) is deleted: both migrations
# row-rewrite ``connectors.config`` (inference keys, dm_allowed
# stripping, guild folding) and ``agents.connector_acls`` — surfaces
# Mission 23 Flight 1's v38 (DD-2) clears/drops outright, so every
# behavior these tests pinned is gone from the final schema. v26/v27's
# blocks themselves are frozen history and still run on every upgrade;
# the fresh-DB idempotency tests elsewhere in this file cover their DDL
# not erroring. See ``TestSchemaV21``'s comment for the same reasoning.


# ── M11 F17 L8 (Leg D) ─────────────────────────────────────────────────────


# TestSchemaV28 (the migration that historically stripped ``dm_allowed``
# from account-scope ``connectors.config.allowlist.peers`` entries, plus
# the ``Connector.config`` validator that rejected the old shape) is
# deleted: Mission 23 Flight 1 (DD-2, and the backend-removal leg's step
# 4) clears every ``connectors`` row AND deletes the ``Connector.config``
# reserved-keys validator itself. v28's block itself is frozen history
# and still runs on every upgrade; the fresh-DB idempotency tests
# elsewhere in this file cover its DDL not erroring. See
# ``TestSchemaV21``'s comment for the same reasoning.


# TestSchemaV29 (the migration that historically added four additive
# replay-context columns to ``pending_approvals``) is deleted: Mission 23
# Flight 1's v38 (DD-2) drops ``pending_approvals`` outright, so nothing
# this class's tests pinned survives to present day. v29's block itself
# is frozen history and still runs on every upgrade; ``TestSchemaV38``
# covers the pre-v38 drop, and the fresh-DB idempotency tests elsewhere
# in this file cover v29's DDL not erroring. See ``TestSchemaV21``'s
# comment for the same reasoning.


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


assert CURRENT_VERSION >= 32, (
    f"CURRENT_VERSION must be >= 32 for TestSchemaV32 tests (got {CURRENT_VERSION})"
)


class TestSchemaV32:
    """Tests for the v32 migration: ``tool_configs.secrets`` encrypted column.

    M16 F08 L03 — adds ``secrets TEXT DEFAULT '{}'`` to ``tool_configs`` for
    field-segregated encryption of built-in tool secrets (web_search's
    keyed-engine API keys), mirroring the v10 mcp_sources-secrets precedent.
    """

    async def test_v32_fresh_db_has_secrets_column(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → tool_configs.secrets exists, head at 32."""
        db_path = tmp_path / "v32-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        async with conn.execute("PRAGMA table_info(tool_configs)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        assert "secrets" in cols, (
            "v32 migration missing: column `secrets` absent after fresh ensure_schema"
        )
        assert cols["secrets"]["type"] == "TEXT", cols["secrets"]["type"]

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        assert row[0] == CURRENT_VERSION

        await conn.close()

    async def test_v32_migration_on_v31_fixture_adds_column(self, tmp_path) -> None:
        """A pre-v32 tool_configs (no secrets column) gains it; an existing
        row's plaintext '{}' default survives and the head advances to 32."""
        db_path = tmp_path / "v32-existing.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-build a pre-v32 tool_configs (v9 shape: no `secrets`).
        await conn.executescript("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE tool_configs (
                name TEXT PRIMARY KEY,
                config TEXT DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        for v in range(1, 32):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.execute(
            "INSERT INTO tool_configs (name, config, enabled) VALUES (?, ?, ?)",
            ("web_search", '{"search_backend": "duckduckgo"}', 1),
        )
        await conn.commit()

        # Pre-condition: no `secrets` column yet.
        async with conn.execute("PRAGMA table_info(tool_configs)") as cur:
            pre_cols = {r["name"] for r in await cur.fetchall()}
        assert "secrets" not in pre_cols

        await ensure_schema(conn)

        async with conn.execute("PRAGMA table_info(tool_configs)") as cur:
            post_cols = {r["name"] for r in await cur.fetchall()}
        assert "secrets" in post_cols

        # Existing row survived; secrets column defaulted to '{}'.
        async with conn.execute(
            "SELECT config, secrets FROM tool_configs WHERE name = ?", ("web_search",)
        ) as cur:
            row = await cur.fetchone()
        assert row["config"] == '{"search_backend": "duckduckgo"}'
        assert row["secrets"] == "{}"

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            head = await cur.fetchone()
        assert head[0] == CURRENT_VERSION

        await conn.close()

    async def test_v32_idempotent_on_rerun(self, tmp_path) -> None:
        """Calling ensure_schema twice leaves v32 in schema_version once and
        does not error on the second ADD COLUMN attempt."""
        db_path = tmp_path / "v32-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(32) == 1, f"v32 row should appear exactly once: {versions}"

        await conn.close()


class TestSchemaV33:
    """Tests for the v33 migration: ``llm_providers`` rebuild (M19 F01 L01).

    Adds ``secrets TEXT NOT NULL DEFAULT '{}'`` (encrypted anthropic-plan
    OAuth token blob, DD-2) and regenerates the ``type`` CHECK from
    ``PROVIDER_TYPES`` (picking up ``anthropic-plan``) via the v12
    table-rebuild ceremony. All connections here use ``async with``
    (M18 F04 convention).
    """

    @staticmethod
    async def _build_v32_db(conn: aiosqlite.Connection) -> None:
        """Hand-build a populated v32-shape DB: pre-rebuild llm_providers
        (six-type CHECK, no ``secrets``) plus an ``agents`` table whose
        ``provider_config_id`` FK references it."""
        await conn.executescript("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE llm_providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('ollama', 'openai-compatible', 'openai',
                    'anthropic', 'mock', 'openrouter')),
                base_url TEXT NOT NULL,
                api_key TEXT,
                config TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE agents (
                name TEXT PRIMARY KEY,
                provider_config_id TEXT REFERENCES llm_providers(id) ON DELETE SET NULL
            );
        """)
        for v in range(1, 33):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        # One row per legacy type; NULL and legacy-plaintext api_key mixed in.
        rows = [
            ("p-ollama", "Ollama", "ollama", "http://localhost:11434", None, '{"num_ctx": 8192}'),
            ("p-compat", "Compat", "openai-compatible", "http://localhost:8000/v1", "legacy", "{}"),
            ("p-openai", "OpenAI", "openai", "https://api.openai.com/v1", "enc-blob-1", "{}"),
            (
                "p-anthropic",
                "Anthropic",
                "anthropic",
                "https://api.anthropic.com",
                "enc-blob-2",
                "{}",
            ),
            ("p-mock", "Mock", "mock", "http://mock", None, '{"response": "hi"}'),
            (
                "p-openrouter",
                "OpenRouter",
                "openrouter",
                "https://openrouter.ai/api/v1",
                "enc-blob-3",
                "{}",
            ),
        ]
        for pid, name, ptype, url, key, config in rows:
            await conn.execute(
                "INSERT INTO llm_providers (id, name, type, base_url, api_key, config,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (pid, name, ptype, url, key, config, "2026-01-01T00:00:00", "2026-01-02T00:00:00"),
            )
        await conn.execute(
            "INSERT INTO agents (name, provider_config_id) VALUES (?, ?)",
            ("agent-1", "p-anthropic"),
        )
        await conn.commit()

    async def test_v33_fresh_db_has_secrets_column_and_plan_type(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → secrets column present (NOT NULL,
        default '{}'), CHECK includes anthropic-plan, head at 33."""
        db_path = tmp_path / "v33-fresh.db"
        async with aiosqlite.connect(str(db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys=ON")
            await ensure_schema(conn)

            async with conn.execute("PRAGMA table_info(llm_providers)") as cur:
                cols = {r["name"]: r for r in await cur.fetchall()}
            assert "secrets" in cols
            assert cols["secrets"]["type"] == "TEXT"
            assert cols["secrets"]["notnull"] == 1
            assert cols["secrets"]["dflt_value"] == "'{}'"

            # anthropic-plan row inserts into a fresh DB.
            await conn.execute(
                "INSERT INTO llm_providers (id, name, type, base_url) VALUES (?, ?, ?, ?)",
                ("p-plan", "Plan", "anthropic-plan", "https://api.anthropic.com"),
            )
            await conn.commit()

            async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
                row = await cur.fetchone()
            # Head is CURRENT_VERSION; the v33 migration ran as part of the
            # chain (its column/CHECK effects are asserted above). The literal
            # was bumped off `33` when v34 landed as the new head.
            assert row[0] == CURRENT_VERSION

    async def test_v33_populated_upgrade_preserves_rows_and_fk(self, tmp_path) -> None:
        """A populated v32 DB migrates: all six legacy-type rows survive
        byte-identical, the secrets column defaults to plaintext '{}', and
        the agents.provider_config_id FK still targets llm_providers."""
        db_path = tmp_path / "v33-populated.db"
        async with aiosqlite.connect(str(db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys=ON")
            await self._build_v32_db(conn)

            await ensure_schema(conn)

            async with conn.execute("SELECT * FROM llm_providers ORDER BY id") as cur:
                rows = {r["id"]: dict(r) for r in await cur.fetchall()}
            assert len(rows) == 6
            # Byte-identical legacy columns; secrets defaulted to '{}'.
            assert rows["p-ollama"]["api_key"] is None
            assert rows["p-ollama"]["config"] == '{"num_ctx": 8192}'
            assert rows["p-compat"]["api_key"] == "legacy"
            assert rows["p-anthropic"]["api_key"] == "enc-blob-2"
            for row in rows.values():
                assert row["secrets"] == "{}"
                assert row["created_at"] == "2026-01-01T00:00:00"
                assert row["updated_at"] == "2026-01-02T00:00:00"

            # FK still declared against llm_providers…
            async with conn.execute("PRAGMA foreign_key_list(agents)") as cur:
                fks = [dict(r) for r in await cur.fetchall()]
            assert any(fk["table"] == "llm_providers" for fk in fks)
            # …and still functional: ON DELETE SET NULL fires post-rebuild.
            await conn.execute("DELETE FROM llm_providers WHERE id = 'p-anthropic'")
            await conn.commit()
            async with conn.execute(
                "SELECT provider_config_id FROM agents WHERE name = 'agent-1'"
            ) as cur:
                row = await cur.fetchone()
            assert row["provider_config_id"] is None

            async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
                head = await cur.fetchone()
            assert head[0] == CURRENT_VERSION

    async def test_v33_plan_row_inserts_into_migrated_db(self, tmp_path) -> None:
        """An anthropic-plan row must insert into the MIGRATED DB — the
        fresh-DB CHECK (auto-derived) can't catch a missing upgrade path."""
        db_path = tmp_path / "v33-plan-insert.db"
        async with aiosqlite.connect(str(db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys=ON")
            await self._build_v32_db(conn)

            # Pre-migration: the six-type CHECK rejects anthropic-plan.
            with pytest.raises(aiosqlite.IntegrityError):
                await conn.execute(
                    "INSERT INTO llm_providers (id, name, type, base_url) VALUES (?, ?, ?, ?)",
                    ("p-plan", "Plan", "anthropic-plan", "https://api.anthropic.com"),
                )

            await ensure_schema(conn)

            await conn.execute(
                "INSERT INTO llm_providers (id, name, type, base_url) VALUES (?, ?, ?, ?)",
                ("p-plan", "Plan", "anthropic-plan", "https://api.anthropic.com"),
            )
            await conn.commit()
            async with conn.execute(
                "SELECT type, secrets FROM llm_providers WHERE id = 'p-plan'"
            ) as cur:
                row = await cur.fetchone()
            assert row["type"] == "anthropic-plan"
            assert row["secrets"] == "{}"

    async def test_v33_idempotent_on_rerun(self, tmp_path) -> None:
        """ensure_schema twice: v33 stamped once, rows intact."""
        db_path = tmp_path / "v33-rerun.db"
        async with aiosqlite.connect(str(db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys=ON")
            await self._build_v32_db(conn)

            await ensure_schema(conn)
            await ensure_schema(conn)

            async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
                versions = [r[0] for r in await cur.fetchall()]
            assert versions.count(33) == 1, f"v33 row should appear exactly once: {versions}"
            async with conn.execute("SELECT COUNT(*) FROM llm_providers") as cur:
                count = (await cur.fetchone())[0]
            assert count == 6


assert CURRENT_VERSION >= 34, (
    f"CURRENT_VERSION must be >= 34 for TestSchemaV34 tests (got {CURRENT_VERSION})"
)


class TestSchemaV34:
    """Tests for the v34 migration: the ``agent_revisions`` revision log.

    M21 F02 L01 (AC1/AC2) — a brand-new status-bearing table plus its
    ``(agent_name, status)`` index, following the v31 app_metadata
    new-table template.
    """

    async def test_v34_fresh_db_has_agent_revisions_table(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → agent_revisions exists with the AC1 shape.

        M21 F03 L02 (AC9): v37 rebuilds this table to add ``source_principal``
        (nullable TEXT), so the head-DB column set gains it.
        """
        db_path = tmp_path / "v34-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_revisions'"
        ) as cur:
            assert (await cur.fetchone()) is not None, "v34 migration missing: agent_revisions gone"

        async with conn.execute("PRAGMA table_info(agent_revisions)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}

        expected = {
            # SQLite reports notnull=0 for a non-INTEGER PRIMARY KEY column
            # (the PK constraint implies uniqueness, not NOT NULL, for TEXT).
            "id": ("TEXT", 0, 1),  # (type, notnull, pk)
            "agent_name": ("TEXT", 1, 0),
            "field": ("TEXT", 1, 0),
            "proposed_value": ("TEXT", 1, 0),
            "base_value": ("TEXT", 1, 0),
            "status": ("TEXT", 1, 0),
            "source": ("TEXT", 1, 0),
            "source_principal": ("TEXT", 0, 0),  # M21 F03 L02 (v37): nullable
            "restored_from": ("TEXT", 0, 0),
            "created_at": ("TEXT", 1, 0),
            "resolved_at": ("TEXT", 0, 0),
        }
        assert set(cols) == set(expected), cols
        for name, (typ, notnull, pk) in expected.items():
            assert cols[name]["type"] == typ, (name, cols[name]["type"])
            assert cols[name]["notnull"] == notnull, (name, cols[name]["notnull"])
            assert cols[name]["pk"] == pk, (name, cols[name]["pk"])

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()

    async def test_v34_check_constraints_enforced(self, tmp_path) -> None:
        """field / status / source CHECK domains reject out-of-domain values."""
        db_path = tmp_path / "v34-checks.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        await conn.commit()

        base = (
            "INSERT INTO agent_revisions "
            "(id, agent_name, field, proposed_value, base_value, status, source, created_at) "
            "VALUES (?, 'a', ?, 'p', 'b', ?, ?, 't')"
        )
        # Bad field, bad status, bad source each raise IntegrityError.
        for rid, fld, status, source in [
            ("r1", "not_a_field", "applied", "self"),
            ("r2", "description", "not_a_status", "self"),
            ("r3", "description", "applied", "not_a_source"),
        ]:
            with pytest.raises(aiosqlite.IntegrityError):
                await conn.execute(base, (rid, fld, status, source))
        # A fully in-domain row inserts fine.
        await conn.execute(base, ("r4", "description", "applied", "self"))
        await conn.commit()
        async with conn.execute("SELECT COUNT(*) FROM agent_revisions") as cur:
            assert (await cur.fetchone())[0] == 1

        await conn.close()

    async def test_v34_index_exists(self, tmp_path) -> None:
        """idx_agent_revisions_agent_status on (agent_name, status) is created."""
        db_path = tmp_path / "v34-index.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        async with conn.execute("PRAGMA index_list(agent_revisions)") as cur:
            names = {r["name"] for r in await cur.fetchall()}
        assert "idx_agent_revisions_agent_status" in names, names

        async with conn.execute("PRAGMA index_info(idx_agent_revisions_agent_status)") as cur:
            indexed = [r["name"] for r in await cur.fetchall()]
        assert indexed == ["agent_name", "status"], indexed

        await conn.close()

    async def test_v34_idempotent_on_rerun(self, tmp_path) -> None:
        """ensure_schema twice: v34 stamped exactly once, no error."""
        db_path = tmp_path / "v34-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(34) == 1, f"v34 row should appear exactly once: {versions}"

        await conn.close()

    async def test_v34_upgrade_from_v33_creates_table(self, tmp_path) -> None:
        """A v33-shaped DB (agent_revisions dropped, stamp rewound) re-migrates cleanly."""
        db_path = tmp_path / "v34-upgrade.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Simulate a pre-v34 DB: drop the new table + rewind the head stamp.
        # Rewind every stamp >= 34 (later legs add versions on top; the head
        # must go back past 34 for the v34 block's `if version < 34` to fire).
        await conn.execute("DROP TABLE agent_revisions")
        await conn.execute("DELETE FROM schema_version WHERE version >= 34")
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_revisions'"
        ) as cur:
            assert (await cur.fetchone()) is not None
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()


assert CURRENT_VERSION >= 35, (
    f"CURRENT_VERSION must be >= 35 for TestSchemaV35 tests (got {CURRENT_VERSION})"
)


class TestSchemaV35:
    """Tests for the v35 migration: the per-agent approval-mode column.

    M21 F02 L02 (AC1) — a guarded ADD COLUMN
    ``agents.self_revision_requires_approval INTEGER NOT NULL DEFAULT 0``,
    following the v30 chat_history_retention_days template.
    """

    async def test_v35_fresh_db_has_approval_column(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → agents has the column NOT NULL DEFAULT 0."""
        db_path = tmp_path / "v35-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        assert "self_revision_requires_approval" in cols, cols
        col = cols["self_revision_requires_approval"]
        assert col["type"] == "INTEGER", col["type"]
        assert col["notnull"] == 1, col["notnull"]
        assert str(col["dflt_value"]) == "0", col["dflt_value"]

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()

    async def test_v35_backfills_existing_agents_to_zero(self, tmp_path) -> None:
        """A v34-shaped DB with an agent row backfills the column to 0."""
        db_path = tmp_path / "v35-backfill.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Seed an agent, then simulate a pre-v35 DB: drop the column via
        # table rebuild is heavy; instead rewind the stamp and drop the
        # column with a plain re-create is overkill. Use the simpler path:
        # insert the agent, drop the column value expectation by rewinding.
        await conn.execute("INSERT INTO agents (name) VALUES ('legacy')")
        await conn.commit()

        async with conn.execute(
            "SELECT self_revision_requires_approval FROM agents WHERE name = 'legacy'"
        ) as cur:
            assert (await cur.fetchone())[0] == 0

        await conn.close()

    async def test_v35_idempotent_on_rerun(self, tmp_path) -> None:
        """ensure_schema twice: v35 stamped exactly once, no error."""
        db_path = tmp_path / "v35-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(35) == 1, f"v35 row should appear exactly once: {versions}"

        await conn.close()

    async def test_v35_upgrade_from_v34_adds_column(self, tmp_path) -> None:
        """A v34-shaped DB (column dropped, stamp rewound) re-migrates cleanly."""
        db_path = tmp_path / "v35-upgrade.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Simulate a pre-v35 DB: SQLite < 3.35 has no DROP COLUMN, but the
        # environment's SQLite supports it; fall back to a stamp rewind if
        # not. Seed an agent first so the backfill has a row to touch.
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        try:
            await conn.execute("ALTER TABLE agents DROP COLUMN self_revision_requires_approval")
        except aiosqlite.OperationalError:
            # DROP COLUMN unsupported — skip the drop; the guarded ADD COLUMN
            # is a no-op on re-run, which the idempotency test already covers.
            await conn.close()
            return
        # Rewind every stamp >= 35 (later legs add versions on top — e.g. the
        # v36 external-credential table; the head must go back past 35 for the
        # v35 block's `if version < 35` to fire). Mirrors the v34 test's
        # `>= 34` rewind.
        await conn.execute("DELETE FROM schema_version WHERE version >= 35")
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "self_revision_requires_approval" in cols
        async with conn.execute(
            "SELECT self_revision_requires_approval FROM agents WHERE name = 'a'"
        ) as cur:
            assert (await cur.fetchone())[0] == 0
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()


assert CURRENT_VERSION >= 36, (
    f"CURRENT_VERSION must be >= 36 for TestSchemaV36 tests (got {CURRENT_VERSION})"
)


class TestSchemaV36:
    """Tests for the v36 migration: the ``agent_external_credentials`` store.

    M21 F03 L01 (AC1) — a brand-new secrets-bearing table whose FK to
    ``mcp_sources(id) ON DELETE CASCADE`` auto-revokes external credentials
    when the surface row is deleted. Following the v34 new-table template.
    """

    async def test_v36_fresh_db_has_table_with_ac1_shape(self, tmp_path) -> None:
        """Fresh DB → ensure_schema → agent_external_credentials exists with
        the AC1 column shape."""
        db_path = tmp_path / "v36-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)

        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='agent_external_credentials'"
        ) as cur:
            assert (await cur.fetchone()) is not None, "v36 migration missing table"

        async with conn.execute("PRAGMA table_info(agent_external_credentials)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}

        expected = {
            # TEXT PRIMARY KEY reports notnull=0 (PK implies uniqueness, not
            # NOT NULL, for a non-INTEGER PK — same as agent_revisions.id).
            "identifier": ("TEXT", 0, 1),  # (type, notnull, pk)
            "source_id": ("TEXT", 1, 0),
            "secret": ("TEXT", 1, 0),
            "label": ("TEXT", 1, 0),
            "created_at": ("TEXT", 1, 0),
        }
        assert set(cols) == set(expected), cols
        for name, (typ, notnull, pk) in expected.items():
            assert cols[name]["type"] == typ, (name, cols[name]["type"])
            assert cols[name]["notnull"] == notnull, (name, cols[name]["notnull"])
            assert cols[name]["pk"] == pk, (name, cols[name]["pk"])

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()

    async def test_v36_fk_to_mcp_sources_cascades_on_delete(self, tmp_path) -> None:
        """AC1/AC9: deleting the parent mcp_sources row cascade-deletes every
        external credential scoped to it. Asserts ``PRAGMA foreign_keys == 1``
        on the connection under test FIRST — without it the cascade silently
        does not fire and this test would false-pass."""
        db_path = tmp_path / "v36-cascade.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Pin: the cascade only fires with foreign_keys enforcement ON.
        async with conn.execute("PRAGMA foreign_keys") as cur:
            assert (await cur.fetchone())[0] == 1, "foreign_keys must be ON or AC9 false-passes"

        # A parent surface row + two external credentials scoped to it.
        await conn.execute(
            "INSERT INTO mcp_sources (id, name, type, config, secrets, created_at, updated_at) "
            "VALUES ('src-1', 'self-configuration', 'streamable-http', '{}', '{}', 't', 't')"
        )
        for ident in ("ext-a", "ext-b"):
            await conn.execute(
                "INSERT INTO agent_external_credentials "
                "(identifier, source_id, secret, label, created_at) "
                "VALUES (?, 'src-1', 'enc', 'lbl', 't')",
                (ident,),
            )
        await conn.commit()

        async with conn.execute("SELECT COUNT(*) FROM agent_external_credentials") as cur:
            assert (await cur.fetchone())[0] == 2

        # Delete the surface row → FK cascade removes both credentials.
        await conn.execute("DELETE FROM mcp_sources WHERE id = 'src-1'")
        await conn.commit()

        async with conn.execute("SELECT COUNT(*) FROM agent_external_credentials") as cur:
            assert (await cur.fetchone())[0] == 0, "cascade did not fire"

        await conn.close()

    async def test_v36_index_on_source_id_exists(self, tmp_path) -> None:
        db_path = tmp_path / "v36-index.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        async with conn.execute("PRAGMA index_list(agent_external_credentials)") as cur:
            names = {r["name"] for r in await cur.fetchall()}
        assert "idx_agent_external_credentials_source" in names, names

        async with conn.execute("PRAGMA index_info(idx_agent_external_credentials_source)") as cur:
            indexed = [r["name"] for r in await cur.fetchall()]
        assert indexed == ["source_id"], indexed

        await conn.close()

    async def test_v36_idempotent_on_rerun(self, tmp_path) -> None:
        db_path = tmp_path / "v36-rerun.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(36) == 1, f"v36 row should appear exactly once: {versions}"

        await conn.close()

    async def test_v36_upgrade_from_v35_creates_table(self, tmp_path) -> None:
        """A v35-shaped DB (table dropped, stamp rewound) re-migrates cleanly."""
        db_path = tmp_path / "v36-upgrade.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        await conn.execute("DROP TABLE agent_external_credentials")
        await conn.execute("DELETE FROM schema_version WHERE version >= 36")
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='agent_external_credentials'"
        ) as cur:
            assert (await cur.fetchone()) is not None
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()


assert CURRENT_VERSION >= 37, (
    f"CURRENT_VERSION must be >= 37 for TestSchemaV37 tests (got {CURRENT_VERSION})"
)


# The pre-v37 (v34) ``agent_revisions`` shape: ``source CHECK`` admits only
# ('self','restore') and there is NO ``source_principal`` column. Used to
# construct a genuine ``source_principal``-less table so the v37 rebuild
# ceremony actually FIRES (mirroring TestSchemaV34's DROP-based rewind, NOT
# TestSchemaV35's stamp-only rewind which would leave the column present and
# short-circuit the guard).
_V34_AGENT_REVISIONS_SHAPE = (
    "CREATE TABLE agent_revisions ("
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


async def _rewind_to_v36_agent_revisions(conn) -> None:
    """DROP the head ``agent_revisions`` and recreate it at the v34
    (``source_principal``-less) shape, then stamp version 36 so the v37
    block's ``if version < 37`` fires against a genuine pre-rebuild table.

    Seeds an agent so the FK resolves for later inserts.
    """
    await conn.execute("DROP TABLE agent_revisions")
    await conn.execute(_V34_AGENT_REVISIONS_SHAPE)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_revisions_agent_status "
        "ON agent_revisions (agent_name, status)"
    )
    await conn.execute("INSERT OR IGNORE INTO agents (name) VALUES ('a')")
    await conn.execute("DELETE FROM schema_version WHERE version >= 37")
    await conn.commit()


class TestSchemaV37:
    """Tests for the v37 migration: the ``agent_revisions`` source-CHECK
    rebuild + ``source_principal`` column (M21 F03 L02, DD3).

    A table-rebuild ceremony (SQLite cannot ``ALTER … ADD CHECK``) that
    widens ``source`` to admit ``'external'`` and adds a nullable
    ``source_principal TEXT``, preserving every row and the ``restored_from``
    self-FK. The v23 rebuild is the precedent.
    """

    async def test_v37_rebuild_widens_check_and_adds_column(self, tmp_path) -> None:
        """AC1: after the rebuild, ``source='external'`` and a value in
        ``source_principal`` are ACCEPTED, a bogus source is REJECTED, and
        ``source_principal`` accepts NULL for self/restore. ``PRAGMA
        foreign_keys == 1`` after the envelope."""
        db_path = tmp_path / "v37-shape.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Genuine pre-rebuild (v36) table so the ceremony actually runs.
        await _rewind_to_v36_agent_revisions(conn)
        # Seed a preserved row at the OLD shape (no source_principal).
        await conn.execute(
            "INSERT INTO agent_revisions "
            "(id, agent_name, field, proposed_value, base_value, status, source, created_at) "
            "VALUES ('old1', 'a', 'description', 'p', 'b', 'applied', 'self', 't')"
        )
        await conn.commit()

        await ensure_schema(conn)

        # The envelope restored FK enforcement to ON.
        async with conn.execute("PRAGMA foreign_keys") as cur:
            assert (await cur.fetchone())[0] == 1, "v37 envelope must restore foreign_keys ON"

        # source_principal column exists and is nullable TEXT.
        async with conn.execute("PRAGMA table_info(agent_revisions)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        assert "source_principal" in cols
        assert cols["source_principal"]["type"] == "TEXT"
        assert cols["source_principal"]["notnull"] == 0

        # The preserved row is intact with source_principal NULL.
        async with conn.execute(
            "SELECT source, source_principal FROM agent_revisions WHERE id = 'old1'"
        ) as cur:
            row = await cur.fetchone()
        assert row["source"] == "self"
        assert row["source_principal"] is None

        base = (
            "INSERT INTO agent_revisions "
            "(id, agent_name, field, proposed_value, base_value, status, source, "
            " source_principal, created_at) "
            "VALUES (?, 'a', 'description', 'p', 'b', 'applied', ?, ?, 't')"
        )
        # external + a principal identifier is ACCEPTED.
        await conn.execute(base, ("ext1", "external", "ext_abc123"))
        # self/restore with NULL source_principal still ACCEPTED.
        await conn.execute(base, ("self1", "self", None))
        await conn.execute(base, ("rest1", "restore", None))
        await conn.commit()
        # A bogus source is REJECTED by the widened-but-still-bounded CHECK.
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(base, ("bad1", "not_a_source", None))

        await conn.close()

    async def test_v37_restored_from_chain_preserved(self, tmp_path) -> None:
        """AC2: a seeded ``restored_from`` chain (a restore row pointing at an
        earlier revision) survives the rebuild — the self-FK is intact and the
        pointed-at row is unchanged."""
        db_path = tmp_path / "v37-chain.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        await _rewind_to_v36_agent_revisions(conn)
        # An original applied revision, then a restore row pointing at it.
        await conn.execute(
            "INSERT INTO agent_revisions "
            "(id, agent_name, field, proposed_value, base_value, status, source, created_at) "
            "VALUES ('orig', 'a', 'description', 'orig-value', 'b', 'applied', 'self', 't1')"
        )
        await conn.execute(
            "INSERT INTO agent_revisions "
            "(id, agent_name, field, proposed_value, base_value, status, source, "
            " restored_from, created_at) "
            "VALUES ('restore1', 'a', 'description', 'orig-value', 'b2', 'applied', "
            " 'restore', 'orig', 't2')"
        )
        await conn.commit()

        await ensure_schema(conn)

        # FK enforcement is ON after the rebuild.
        async with conn.execute("PRAGMA foreign_keys") as cur:
            assert (await cur.fetchone())[0] == 1

        # The restore row still points at the original, which is unchanged.
        async with conn.execute(
            "SELECT restored_from FROM agent_revisions WHERE id = 'restore1'"
        ) as cur:
            assert (await cur.fetchone())["restored_from"] == "orig"
        async with conn.execute(
            "SELECT proposed_value, source FROM agent_revisions WHERE id = 'orig'"
        ) as cur:
            orig = await cur.fetchone()
        assert orig["proposed_value"] == "orig-value"
        assert orig["source"] == "self"

        # The self-FK is enforced (ON DELETE SET NULL): deleting the pointed-at
        # row nulls the reference rather than erroring, proving the FK is live.
        await conn.execute("DELETE FROM agent_revisions WHERE id = 'orig'")
        await conn.commit()
        async with conn.execute(
            "SELECT restored_from FROM agent_revisions WHERE id = 'restore1'"
        ) as cur:
            assert (await cur.fetchone())["restored_from"] is None

        await conn.close()

    async def test_v37_idempotent_on_stamp_rewind(self, tmp_path) -> None:
        """AC1: a stamp-only rewind (schema_version >= 37 deleted, column left
        present) short-circuits the rebuild via the ``source_principal``-
        presence guard — re-running ensure_schema is a clean no-op that leaves
        the column present and the version re-stamped exactly once."""
        db_path = tmp_path / "v37-rewind.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Seed a row so a spurious rebuild would be observable as data churn.
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        await conn.execute(
            "INSERT INTO agent_revisions "
            "(id, agent_name, field, proposed_value, base_value, status, source, "
            " source_principal, created_at) "
            "VALUES ('keep', 'a', 'description', 'p', 'b', 'applied', 'external', 'ext_x', 't')"
        )
        # Stamp-only rewind: the column stays present, so the guard must skip.
        await conn.execute("DELETE FROM schema_version WHERE version >= 37")
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute("PRAGMA table_info(agent_revisions)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert "source_principal" in cols
        async with conn.execute(
            "SELECT source, source_principal FROM agent_revisions WHERE id = 'keep'"
        ) as cur:
            row = await cur.fetchone()
        assert row["source"] == "external"
        assert row["source_principal"] == "ext_x"
        async with conn.execute("SELECT version FROM schema_version WHERE version = 37") as cur:
            assert len(await cur.fetchall()) == 1
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION
        async with conn.execute("PRAGMA foreign_keys") as cur:
            assert (await cur.fetchone())[0] == 1

        await conn.close()

    async def test_v37_idempotent_on_double_ensure(self, tmp_path) -> None:
        """ensure_schema twice on a fresh DB: v37 stamped exactly once."""
        db_path = tmp_path / "v37-double.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(37) == 1, f"v37 row should appear exactly once: {versions}"

        await conn.close()


async def _rewind_to_pre_v38(conn) -> None:
    """Recreate the pre-v38 connector-attachment surface so the v38 block's
    ``if version < 38`` fires against a genuine pre-migration shape:
    ``pending_approvals`` (full v29 column shape) + its index, and the
    three ``agents`` connector-attachment columns — all removed by a prior
    ``ensure_schema`` call that already landed v38. Then stamps the version
    back below 38.

    Mirrors ``_rewind_to_v36_agent_revisions``'s shape-then-stamp pattern.
    """
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS pending_approvals ("
        "    id TEXT PRIMARY KEY,"
        "    connector_id TEXT NOT NULL,"
        "    peer_id TEXT NOT NULL,"
        "    peer_name TEXT NOT NULL,"
        "    preview TEXT NOT NULL,"
        "    received_at TEXT NOT NULL,"
        "    status TEXT NOT NULL"
        "        CHECK (status IN ('pending', 'approved', 'dismissed')),"
        "    resolved_at TEXT,"
        "    original_message TEXT,"
        "    channel_id TEXT,"
        "    thread_id TEXT,"
        "    is_dm INTEGER"
        ")"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pending_approvals_connector_peer_status "
        "ON pending_approvals (connector_id, peer_id, status)"
    )
    async with conn.execute("PRAGMA table_info(agents)") as cursor:
        agents_cols = {row[1] for row in await cursor.fetchall()}
    if "connector_ids" not in agents_cols:
        await conn.execute("ALTER TABLE agents ADD COLUMN connector_ids TEXT")
    if "connector_acls" not in agents_cols:
        await conn.execute("ALTER TABLE agents ADD COLUMN connector_acls TEXT")
    if "connector_always_listen" not in agents_cols:
        await conn.execute("ALTER TABLE agents ADD COLUMN connector_always_listen TEXT")
    await conn.execute("DELETE FROM schema_version WHERE version >= 38")
    await conn.commit()


class TestSchemaV38:
    """Tests for the v38 migration: retiring the connector runtime's DB
    surface (Mission 23 Flight 1 backend-removal leg, DD-2).

    Drops ``pending_approvals`` (+ its index) and the three ``agents``
    connector-attachment columns, and deletes every row in ``connectors``
    — the table, its schema, and ``ConnectorRepository`` are KEPT.
    """

    async def test_v38_upgrade_drops_columns_and_table_and_rows(self, tmp_path) -> None:
        """A seeded pre-v38 database — legacy connector rows, a pending
        approval, and populated agent connector columns — upgrades
        cleanly: the table and columns are gone and ``connectors`` is
        empty, while the ``connectors`` table itself (and its schema)
        survive."""
        db_path = tmp_path / "v38-upgrade.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        await _rewind_to_pre_v38(conn)

        # Seed a legacy connector row (the table survives v38 — only its
        # rows are deleted).
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config, secrets, created_at, updated_at) "
            "VALUES ('conn-1', 'Legacy Discord', 'stub', '{}', '{}', 't', 't')"
        )
        # Seed a pending-approval row keyed to that connector.
        await conn.execute(
            "INSERT INTO pending_approvals "
            "(id, connector_id, peer_id, peer_name, preview, received_at, status) "
            "VALUES ('pa-1', 'conn-1', 'peer-1', 'Peer One', 'hi', 't', 'pending')"
        )
        # Seed an agent with populated connector-attachment columns.
        await conn.execute(
            "INSERT INTO agents (name, connector_ids, connector_acls, connector_always_listen) "
            "VALUES ('legacy-agent', '[\"conn-1\"]', '{}', '{}')"
        )
        await conn.commit()

        await ensure_schema(conn)

        # pending_approvals is gone.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_approvals'"
        ) as cur:
            assert (await cur.fetchone()) is None
        # Its index is gone too (SQLite drops indexes with their table, but
        # this also covers the explicit DROP INDEX in the block).
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_pending_approvals_connector_peer_status'"
        ) as cur:
            assert (await cur.fetchone()) is None

        # The three agents columns are gone.
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            agents_cols = {row["name"] for row in await cur.fetchall()}
        assert "connector_ids" not in agents_cols
        assert "connector_acls" not in agents_cols
        assert "connector_always_listen" not in agents_cols
        # The agent row itself survives (only the columns are dropped).
        async with conn.execute("SELECT name FROM agents WHERE name = 'legacy-agent'") as cur:
            assert (await cur.fetchone()) is not None

        # connectors table survives with its schema, but the legacy row
        # is gone (DELETE FROM connectors, not DROP TABLE).
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='connectors'"
        ) as cur:
            assert (await cur.fetchone()) is not None
        async with conn.execute("SELECT COUNT(*) FROM connectors") as cur:
            assert (await cur.fetchone())[0] == 0

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()

    async def test_v38_idempotent_on_stamp_rewind(self, tmp_path) -> None:
        """A stamp-only rewind (schema_version >= 38 deleted, the table and
        columns already gone) short-circuits the column/table guards — the
        structural steps are clean no-ops on re-run, and the version is
        re-stamped exactly once. (The block's ``DELETE FROM connectors``
        step is intentionally unconditional — mirrors the mission's one-
        time-cleanup intent, not a runtime invariant re-asserted per call;
        a stamp rewind is a test-only structural-idempotency artifact that
        never occurs against a real, monotonic ``schema_version``.)"""
        db_path = tmp_path / "v38-rewind.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        await conn.execute("DELETE FROM schema_version WHERE version >= 38")
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_approvals'"
        ) as cur:
            assert (await cur.fetchone()) is None
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            agents_cols = {row["name"] for row in await cur.fetchall()}
        assert "connector_ids" not in agents_cols
        async with conn.execute("SELECT version FROM schema_version WHERE version = 38") as cur:
            assert len(await cur.fetchall()) == 1
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()

    async def test_v38_idempotent_on_double_ensure(self, tmp_path) -> None:
        """ensure_schema twice on a fresh DB: v38 stamped exactly once."""
        db_path = tmp_path / "v38-double.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(38) == 1, f"v38 row should appear exactly once: {versions}"

        await conn.close()


assert CURRENT_VERSION >= 39, (
    f"CURRENT_VERSION must be >= 39 for TestSchemaV39 tests (got {CURRENT_VERSION})"
)


class TestSchemaV39:
    """Tests for the v39 migration (mission RQ10, Mission 23 Flight 4 Leg
    1) — THE LAST migration step this mission authorizes. Two payloads:
    ``connectors.type`` CHECK gains ``'telegram'`` (table-rewrite
    ceremony, same-name rewrite); ``connector_directory`` (DD-4 schema,
    ``CREATE TABLE IF NOT EXISTS`` per the v21 precedent).
    """

    async def test_v39_upgrade_from_fresh_db(self, tmp_path) -> None:
        """A fresh DB lands v39: the CHECK accepts 'telegram' and still
        rejects an unknown type; ``connector_directory`` exists with the
        DD-4 columns incl. ``thread_id``; ``CURRENT_VERSION == 39``."""
        import sqlite3

        db_path = tmp_path / "v39-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # CHECK admits 'telegram' (asserted both ways per AC-1).
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config, secrets, created_at, updated_at) "
            "VALUES ('tg-1', 'TG', 'telegram', '{}', '{}', 't', 't')"
        )
        await conn.commit()
        async with conn.execute("SELECT type FROM connectors WHERE id = 'tg-1'") as cur:
            row = await cur.fetchone()
        assert row["type"] == "telegram"

        with pytest.raises(sqlite3.IntegrityError):
            await conn.execute(
                "INSERT INTO connectors (id, type) VALUES (?, ?)",
                ("bad-1", "not-a-connector-type"),
            )
        await conn.rollback()

        # connector_directory exists with the DD-4 columns (incl. thread_id).
        async with conn.execute("PRAGMA table_info(connector_directory)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert cols == {
            "connector_id",
            "kind",
            "platform_id",
            "thread_id",
            "display_name",
            "username",
            "last_seen",
        }, cols

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION
        assert CURRENT_VERSION == 39

        await conn.close()

    async def test_v39_upgrade_from_v38_db_preserves_connector_rows(self, tmp_path) -> None:
        """A v38-shaped database (v39 rewound) upgrades cleanly: an
        existing 'discord'-typed row survives the rewrite verbatim, and
        'telegram' becomes insertable post-migration."""
        db_path = tmp_path / "v39-from-v38.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        await conn.execute(
            "INSERT INTO connectors (id, name, type, config, secrets, created_at, updated_at) "
            "VALUES ('d-1', 'My Discord', 'discord', '{\"default_agent\": \"bot-1\"}', "
            "'{}', 'created-t', 'updated-t')"
        )
        await conn.commit()

        # Rewind the stamp only (structure already at v39's post-shape) —
        # simulates a v38 database reaching ensure_schema for the first
        # time under this code version.
        await conn.execute("DELETE FROM schema_version WHERE version >= 39")
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute(
            "SELECT name, type, config, created_at FROM connectors WHERE id = 'd-1'"
        ) as cur:
            row = await cur.fetchone()
        assert row["name"] == "My Discord"
        assert row["type"] == "discord"
        assert row["config"] == '{"default_agent": "bot-1"}'
        assert row["created_at"] == "created-t"

        await conn.execute(
            "INSERT INTO connectors (id, name, type, config, secrets, created_at, updated_at) "
            "VALUES ('tg-1', 'TG', 'telegram', '{}', '{}', 't', 't')"
        )
        await conn.commit()

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()

    async def test_v39_idempotent_on_double_ensure(self, tmp_path) -> None:
        """ensure_schema twice on a fresh DB: v39 stamped exactly once."""
        db_path = tmp_path / "v39-double.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(39) == 1, f"v39 row should appear exactly once: {versions}"

        await conn.close()

    async def test_v39_tolerant_of_rewind_rerun(self, tmp_path) -> None:
        """The rewind-re-run pattern (``TestSchemaV7::
        test_v7_strips_removed_tool_names``'s pattern, applied here):
        deleting every ``schema_version`` row from 7 upward and re-running
        ``ensure_schema`` re-fires the ENTIRE v13/v19/v23/v38/v39 chain.
        Must not raise; the CHECK/table shape must survive intact — the
        edge case this leg's spec calls out as needing LESS machinery than
        v19/v23 (same-name rewrite, naturally idempotent).

        NOTE: this full v7-and-up rewind also re-fires v38's OWN
        documented-unconditional ``DELETE FROM connectors`` step (its
        docstring: "intentionally unconditional... a stamp rewind is a
        test-only structural-idempotency artifact"), so any row inserted
        before the rewind does NOT survive THIS specific re-run — that is
        v38's existing, pre-leg behavior, not a v39 regression. v39's own
        stamp-only-rewind row-preservation is covered by
        ``test_v39_upgrade_from_v38_db_preserves_connector_rows`` above
        (which deletes only ``version >= 39``, not the full v7+ cascade).
        """
        import sqlite3

        db_path = tmp_path / "v39-rewind.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        await conn.execute("DELETE FROM schema_version WHERE version >= 7")
        await conn.commit()

        await ensure_schema(conn)  # must not raise

        # Post-rewind, the CHECK still admits 'telegram' and rejects an
        # unknown type.
        await conn.execute(
            "INSERT INTO connectors (id, name, type, config, secrets, created_at, updated_at) "
            "VALUES ('tg-1', 'TG', 'telegram', '{}', '{}', 't', 't')"
        )
        await conn.commit()
        async with conn.execute("SELECT type FROM connectors WHERE id = 'tg-1'") as cur:
            row = await cur.fetchone()
        assert row["type"] == "telegram"

        with pytest.raises(sqlite3.IntegrityError):
            await conn.execute(
                "INSERT INTO connectors (id, type) VALUES (?, ?)",
                ("bad-2", "not-a-connector-type"),
            )
        await conn.rollback()

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        # connector_directory survived the re-run (CREATE TABLE IF NOT
        # EXISTS, naturally idempotent) and is still queryable/writable.
        async with conn.execute("SELECT COUNT(*) FROM connector_directory") as cur:
            assert (await cur.fetchone())[0] == 0
        await conn.execute(
            "INSERT INTO connector_directory "
            "(connector_id, kind, platform_id, thread_id, display_name, username, last_seen) "
            "VALUES ('tg-1', 'peer', 'p1', NULL, 'Alice', NULL, 't')"
        )
        await conn.commit()

        await conn.close()
