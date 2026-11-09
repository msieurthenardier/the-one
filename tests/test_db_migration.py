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
        await conn.execute("PRAGMA synchronous=OFF")
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

    async def test_skips_bad_body_name_with_warning(self, setup, caplog) -> None:
        store, agents_dir = setup
        agents_dir.mkdir(parents=True, exist_ok=True)
        cfg = AgentConfig(name="a/b")
        (agents_dir / "legacy.json").write_text(json.dumps(cfg.model_dump()))

        with caplog.at_level("WARNING", logger="the_one.db.migration"):
            count = await migrate_json_to_sqlite(store)

        assert count == 0
        assert not await store.exists("a/b")
        assert not await store.exists("legacy")
        assert any("legacy" in r.getMessage() for r in caplog.records)

    async def test_valid_body_is_stored_unchanged(self, setup) -> None:
        store, agents_dir = setup
        _write_json_config(agents_dir, "padded-ok", description="  keep  ")
        assert await migrate_json_to_sqlite(store) == 1
        assert (await store.load("padded-ok")).description == "  keep  "

    async def test_mismatched_stem_is_not_resaved_on_second_run(self, setup) -> None:
        store, agents_dir = setup
        cfg = AgentConfig(name="body-name", description="from json")
        (agents_dir / "other-stem.json").write_text(json.dumps(cfg.model_dump()))

        assert await migrate_json_to_sqlite(store) == 1
        await store.save(AgentConfig(name="body-name", description="edited later"))

        assert await migrate_json_to_sqlite(store) == 0
        assert (await store.load("body-name")).description == "edited later"


class TestSchemaV7:
    """Tests for the v7 migration that strips removed tool names."""

    async def test_v7_strips_removed_tool_names(self, tmp_path) -> None:
        """v6 → v7: removed tool names are stripped; NULL whitelist is preserved."""
        db_path = tmp_path / "v7-strip.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
            await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
            await conn.execute("PRAGMA synchronous=OFF")
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
            await conn.execute("PRAGMA synchronous=OFF")
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
            await conn.execute("PRAGMA synchronous=OFF")
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
            await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        # A fresh DB runs the ENTIRE migration chain, so ``MAX(version)``
        # (and CURRENT_VERSION) now lands at least at 40 — v40 (Flight 2 Leg
        # 1) added a step after this one, and later legs may add more. This
        # assertion is a sanity pin on the module constant, not a claim that
        # this test only exercises v39; TestSchemaV40/TestSchemaV41 below
        # are the version-specific shape/CHECK/AUTOINCREMENT coverage — the
        # newest block's test pins the exact value (house pattern).
        assert CURRENT_VERSION >= 40

        await conn.close()

    async def test_v39_upgrade_from_v38_db_preserves_connector_rows(self, tmp_path) -> None:
        """A v38-shaped database (v39 rewound) upgrades cleanly: an
        existing 'discord'-typed row survives the rewrite verbatim, and
        'telegram' becomes insertable post-migration."""
        db_path = tmp_path / "v39-from-v38.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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
        await conn.execute("PRAGMA synchronous=OFF")
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


async def _rewind_to_v39_kb_items(conn) -> None:
    """Recreate the exact pre-v40 (SCHEMA_V1, ``schema.py:72-80``)
    ``kb_items`` shape, seed three rows (one with a valid ``status``, one
    with ``status IS NULL``, one with a junk ``status``), and stamp the
    version back below 40 — the v39-shaped-DB fixture for the v40
    upgrade-preserves-rows test (AC-2).

    Mirrors ``_rewind_to_pre_v38``'s shape-then-stamp pattern.
    """
    await conn.execute("DROP TABLE kb_items")
    await conn.execute(
        "CREATE TABLE kb_items ("
        "    id TEXT PRIMARY KEY,"
        "    kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,"
        "    parent_id TEXT REFERENCES kb_items(id) ON DELETE CASCADE,"
        "    type TEXT NOT NULL CHECK (type IN ('file', 'url')),"
        "    path_or_url TEXT NOT NULL,"
        "    status TEXT DEFAULT 'pending',"
        "    created_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    await conn.execute(
        "INSERT INTO kb_items (id, kb_id, parent_id, type, path_or_url, status, created_at) "
        "VALUES ('item-pending', 'kb1', NULL, 'file', 'p1', 'pending', 'created-1')"
    )
    await conn.execute(
        "INSERT INTO kb_items (id, kb_id, parent_id, type, path_or_url, status, created_at) "
        "VALUES ('item-null', 'kb1', NULL, 'url', 'p2', NULL, 'created-2')"
    )
    await conn.execute(
        "INSERT INTO kb_items (id, kb_id, parent_id, type, path_or_url, status, created_at) "
        "VALUES ('item-garbage', 'kb1', NULL, 'file', 'p3', 'garbage', 'created-3')"
    )
    await conn.execute("DELETE FROM schema_version WHERE version >= 40")
    await conn.commit()


class TestSchemaV40:
    """Tests for the v40 migration (Flight 2 "Storage and Embedding
    Foundation", Leg 1, DD-5/DD-13) — the flight's one hard-to-reverse
    step: ``kb_items`` rebuilt with a constrained lifecycle, ``kb_chunks``
    with never-recycled ``AUTOINCREMENT`` ids, and an external-content
    FTS5 index (``kb_chunks_fts``).
    """

    async def test_v40_upgrade_from_fresh_db(self, tmp_path) -> None:
        """AC-1: a fresh DB lands v40 with the full expected shape —
        ``kb_items`` / ``kb_chunks`` columns, the FTS5 table, and the
        membership-style ``sqlite_master`` assertion (never an exact set —
        FTS5 shadow tables and ``sqlite_sequence`` also exist)."""
        db_path = tmp_path / "v40-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        async with conn.execute("PRAGMA table_info(kb_items)") as cur:
            kb_items_cols = {r["name"] for r in await cur.fetchall()}
        assert kb_items_cols == {
            "id",
            "kb_id",
            "parent_id",
            "type",
            "path_or_url",
            "status",
            "error",
            "content_hash",
            "size_bytes",
            "mtime",
            "created_at",
            "updated_at",
            "indexed_at",
        }, kb_items_cols

        async with conn.execute("PRAGMA table_info(kb_chunks)") as cur:
            kb_chunks_cols = {r["name"] for r in await cur.fetchall()}
        assert kb_chunks_cols == {
            "id",
            "item_id",
            "kb_id",
            "seq",
            "text",
            "char_start",
            "char_end",
            "created_at",
        }, kb_chunks_cols

        async with conn.execute("SELECT name FROM sqlite_master") as cur:
            names = {r["name"] for r in await cur.fetchall()}
        # Membership, never an exact set (house style) — FTS5 shadow
        # tables (_data/_idx/_docsize/_config) and sqlite_sequence also
        # exist and are not enumerated here.
        for expected in (
            "kb_items",
            "kb_chunks",
            "kb_chunks_fts",
            "sqlite_sequence",
            "idx_kb_items_kb_id",
            "idx_kb_items_kb_status",
            "idx_kb_chunks_kb_id",
        ):
            assert expected in names, f"{expected!r} missing from sqlite_master: {names}"

        async with conn.execute("PRAGMA foreign_keys") as cur:
            assert (await cur.fetchone())[0] == 1

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION
        assert CURRENT_VERSION >= 40

        await conn.close()

    async def test_v40_check_constraints(self, tmp_path) -> None:
        """AC-3: both CHECKs hold on a fresh DB — every ``KB_ITEM_TYPES`` /
        ``KB_ITEM_STATUSES`` member inserts; a bogus value on either column
        raises ``sqlite3.IntegrityError``. (Also covered behaviourally, in
        more depth, by ``tests/test_kb_types_consistency.py``.)"""
        import sqlite3

        db_path = tmp_path / "v40-check.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)
        await conn.execute("INSERT INTO knowledge_bases (id, name) VALUES ('kb1', 'KB1')")
        await conn.commit()

        await conn.execute(
            "INSERT INTO kb_items (id, kb_id, type, path_or_url) "
            "VALUES ('folder-1', 'kb1', 'folder', 'p1')"
        )
        await conn.execute(
            "INSERT INTO kb_items (id, kb_id, type, path_or_url, status) "
            "VALUES ('indexing-1', 'kb1', 'file', 'p2', 'indexing')"
        )
        await conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            await conn.execute(
                "INSERT INTO kb_items (id, kb_id, type, path_or_url) "
                "VALUES ('bad-type', 'kb1', 'blob', 'p3')"
            )
        await conn.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            await conn.execute(
                "INSERT INTO kb_items (id, kb_id, type, path_or_url, status) "
                "VALUES ('bad-status', 'kb1', 'file', 'p4', 'done')"
            )
        await conn.rollback()

        await conn.close()

    async def test_v40_upgrade_from_v39_db_preserves_kb_items_rows(self, tmp_path) -> None:
        """AC-2: upgrading a v39-shaped DB carrying three ``kb_items`` rows
        (status 'pending', status NULL, status 'garbage') preserves all
        three with ids, kb_id, parent_id, type, path_or_url, created_at
        intact; the NULL and 'garbage' rows read back as 'pending';
        updated_at equals created_at for migrated rows; PRAGMA
        foreign_keys is 1 afterwards."""
        db_path = tmp_path / "v40-from-v39.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)
        await conn.execute("INSERT INTO knowledge_bases (id, name) VALUES ('kb1', 'KB1')")
        await conn.commit()

        await _rewind_to_v39_kb_items(conn)

        await ensure_schema(conn)

        async with conn.execute("SELECT * FROM kb_items ORDER BY id") as cur:
            rows = {r["id"]: dict(r) for r in await cur.fetchall()}

        assert set(rows.keys()) == {"item-pending", "item-null", "item-garbage"}

        assert rows["item-pending"]["kb_id"] == "kb1"
        assert rows["item-pending"]["parent_id"] is None
        assert rows["item-pending"]["type"] == "file"
        assert rows["item-pending"]["path_or_url"] == "p1"
        assert rows["item-pending"]["created_at"] == "created-1"
        assert rows["item-pending"]["status"] == "pending"
        assert rows["item-pending"]["updated_at"] == "created-1"

        assert rows["item-null"]["type"] == "url"
        assert rows["item-null"]["path_or_url"] == "p2"
        assert rows["item-null"]["created_at"] == "created-2"
        assert rows["item-null"]["status"] == "pending"  # NULL -> pending
        assert rows["item-null"]["updated_at"] == "created-2"

        assert rows["item-garbage"]["type"] == "file"
        assert rows["item-garbage"]["path_or_url"] == "p3"
        assert rows["item-garbage"]["created_at"] == "created-3"
        assert rows["item-garbage"]["status"] == "pending"  # 'garbage' -> pending
        assert rows["item-garbage"]["updated_at"] == "created-3"

        async with conn.execute("PRAGMA foreign_keys") as cur:
            assert (await cur.fetchone())[0] == 1

        await conn.close()

    async def test_v40_idempotent_on_double_ensure(self, tmp_path) -> None:
        """ensure_schema twice on a fresh DB: v40 stamped exactly once."""
        db_path = tmp_path / "v40-double.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(40) == 1, f"v40 row should appear exactly once: {versions}"

        await conn.close()

    async def test_v40_tolerant_of_rewind_rerun(self, tmp_path) -> None:
        """The ``>= 7`` rewind-rerun pattern: deleting every schema_version
        row from 7 upward and re-running ensure_schema re-fires the entire
        chain incl. v40. Must not raise; the v40 shape (incl. the FTS5
        table, still queryable) survives intact."""
        db_path = tmp_path / "v40-rewind.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        await conn.execute("DELETE FROM schema_version WHERE version >= 7")
        await conn.commit()

        await ensure_schema(conn)  # must not raise

        async with conn.execute("PRAGMA table_info(kb_items)") as cur:
            kb_items_cols = {r["name"] for r in await cur.fetchall()}
        assert "content_hash" in kb_items_cols

        # kb_chunks_fts survived the re-run and is still queryable.
        async with conn.execute("SELECT COUNT(*) FROM kb_chunks_fts") as cur:
            assert (await cur.fetchone())[0] == 0

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()

    async def test_v40_stamp_only_rewind_short_circuits_rebuild_and_preserves_rows(
        self, tmp_path
    ) -> None:
        """AC-4: a stamp-only rewind (``DELETE … WHERE version >= 40``)
        re-runs without rebuilding — the column-absence guard short-
        circuits (``kb_items`` already carries ``content_hash``) — and
        preserves rows untouched, including a row whose ``content_hash``
        was already populated (the guard's own signal column)."""
        db_path = tmp_path / "v40-stamp-only-rewind.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)
        await conn.execute("INSERT INTO knowledge_bases (id, name) VALUES ('kb1', 'KB1')")
        await conn.execute(
            "INSERT INTO kb_items (id, kb_id, type, path_or_url, content_hash) "
            "VALUES ('item-1', 'kb1', 'file', 'p1', 'deadbeef')"
        )
        await conn.commit()

        await conn.execute("DELETE FROM schema_version WHERE version >= 40")
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute("SELECT content_hash FROM kb_items WHERE id = 'item-1'") as cur:
            row = await cur.fetchone()
        assert row["content_hash"] == "deadbeef"

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()

    async def test_v40_kb_chunks_ids_never_recycled(self, tmp_path) -> None:
        """AC-5: insert three ``kb_chunks`` rows, delete the last, insert
        again — the new id is greater than every id ever issued
        (``AUTOINCREMENT``, not a plain ``INTEGER PRIMARY KEY``)."""
        db_path = tmp_path / "v40-autoincrement.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)
        await conn.execute("INSERT INTO knowledge_bases (id, name) VALUES ('kb1', 'KB1')")
        await conn.execute(
            "INSERT INTO kb_items (id, kb_id, type, path_or_url) "
            "VALUES ('item-1', 'kb1', 'file', 'p1')"
        )
        await conn.commit()

        for seq in range(3):
            await conn.execute(
                "INSERT INTO kb_chunks (item_id, kb_id, seq, text, char_start, char_end) "
                "VALUES ('item-1', 'kb1', ?, ?, ?, ?)",
                (seq, f"chunk-{seq}", seq * 10, seq * 10 + 5),
            )
        await conn.commit()

        async with conn.execute("SELECT id FROM kb_chunks ORDER BY id") as cur:
            ids_before = [r[0] for r in await cur.fetchall()]
        assert len(ids_before) == 3

        await conn.execute("DELETE FROM kb_chunks WHERE id = ?", (ids_before[-1],))
        await conn.commit()

        await conn.execute(
            "INSERT INTO kb_chunks (item_id, kb_id, seq, text, char_start, char_end) "
            "VALUES ('item-1', 'kb1', 3, 'chunk-3', 30, 35)"
        )
        await conn.commit()

        async with conn.execute("SELECT id FROM kb_chunks ORDER BY id") as cur:
            ids_after = [r[0] for r in await cur.fetchall()]
        assert ids_after[-1] > max(ids_before), (
            f"new id {ids_after[-1]} did not exceed every prior id {ids_before} "
            "— AUTOINCREMENT is not taking effect"
        )

        await conn.close()


class TestSchemaV41:
    """Tests for the v41 migration (Flight 2 "Storage and Embedding
    Foundation", Leg 6, DD-3/DD-9) — the operator's DD-9 decision
    (``usearch``, dtype ``f16``) moved ``kb_vector_index`` from store-owned
    DDL (``UsearchStore.open()``, Legs 4-5) into a versioned migration, and
    purges any stale ``sqlite-vec`` ``knowledge.vector_store`` record.
    """

    async def test_v41_upgrade_from_fresh_db(self, tmp_path) -> None:
        """AC-5a: a fresh DB lands v41 with ``kb_vector_index`` in
        ``sqlite_master`` and exactly the column set
        ``UsearchStore.open()`` created in Leg 4 (byte-for-byte, so a
        database where the store already made the table passes through
        unchanged)."""
        db_path = tmp_path / "v41-fresh.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        async with conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'") as cur:
            names = {r["name"] for r in await cur.fetchall()}
        assert "kb_vector_index" in names, f"kb_vector_index missing from sqlite_master: {names}"

        async with conn.execute("PRAGMA table_info(kb_vector_index)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert cols == {
            "kb_id",
            "path",
            "count",
            "generation",
            "dtype",
            "dim",
            "updated_at",
        }, cols

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION
        assert CURRENT_VERSION == 52

        await conn.close()

    async def test_v41_upgrade_preserves_existing_kb_vector_index_row(self, tmp_path) -> None:
        """AC-5b: a v40 database in which the store already created
        ``kb_vector_index`` (the Leg 4-5 store-owned DDL, ``CREATE TABLE
        IF NOT EXISTS``) with a row upgrades to v41 with the row intact —
        the migration's ``IF NOT EXISTS`` is a no-op against an
        already-present table."""
        db_path = tmp_path / "v41-preexisting-table.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        # Rewind to v40, as if the v41 migration had never run (the table
        # still exists from the ensure_schema call above via IF NOT
        # EXISTS — simulating a Leg 4/5 dev database where
        # UsearchStore.open() had already created it independently).
        await conn.execute("DELETE FROM schema_version WHERE version >= 41")
        await conn.commit()

        await conn.execute(
            "INSERT INTO kb_vector_index (kb_id, path, count, generation, dtype, dim, updated_at) "
            "VALUES ('kb1', '/tmp/kb1.usearch', 5, 2, 'f16', 512, 'ts-1')"
        )
        await conn.commit()

        await ensure_schema(conn)  # v41 re-fires; CREATE TABLE IF NOT EXISTS no-ops

        async with conn.execute("SELECT * FROM kb_vector_index WHERE kb_id = 'kb1'") as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["count"] == 5
        assert row["generation"] == 2
        assert row["dtype"] == "f16"

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()

    async def test_v41_purges_stale_sqlite_vec_vector_store_record(self, tmp_path) -> None:
        """AC-5c: a v40 database whose ``app_metadata`` holds a
        ``sqlite-vec`` ``knowledge.vector_store`` record (only a test or
        the benchmark script could have written one — ``save_vector_store_
        settings`` has no production caller) has the row removed after
        ``ensure_schema``."""
        db_path = tmp_path / "v41-purge-sqlite-vec.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)
        await conn.execute("DELETE FROM schema_version WHERE version >= 41")
        await conn.commit()

        await conn.execute(
            "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
            (
                "knowledge.vector_store",
                '{"backend": "sqlite-vec", "dtype": "float32", "dim": 512, '
                '"model_id": "potion-retrieval-32M"}',
            ),
        )
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute(
            "SELECT value FROM app_metadata WHERE key = 'knowledge.vector_store'"
        ) as cur:
            row = await cur.fetchone()
        assert row is None

        await conn.close()

    async def test_v41_keeps_usearch_vector_store_record(self, tmp_path) -> None:
        """AC-5c (the other half): a ``usearch`` ``knowledge.vector_store``
        record is untouched by the purge."""
        db_path = tmp_path / "v41-keep-usearch.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)
        await conn.execute("DELETE FROM schema_version WHERE version >= 41")
        await conn.commit()

        record = (
            '{"backend": "usearch", "dtype": "f16", "dim": 512, "model_id": "potion-retrieval-32M"}'
        )
        await conn.execute(
            "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
            ("knowledge.vector_store", record),
        )
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute(
            "SELECT value FROM app_metadata WHERE key = 'knowledge.vector_store'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["value"] == record

        await conn.close()

    async def test_v41_does_not_touch_kb_vectors_vec0_table(self, tmp_path) -> None:
        """The v41 block must never attempt to drop or alter ``kb_vectors``
        (the losing ``sqlite-vec`` backend's ``vec0`` virtual table) — a
        ``vec0`` table cannot be dropped without the extension loaded.
        Simulated here with a plain table of the same name (this host's
        `sqlite3` build does not load `vec0` for this test) — the point is
        that the migration source contains no `kb_vectors` statement, so
        any pre-existing table of that name survives ``ensure_schema``
        untouched regardless of its real shape."""
        db_path = tmp_path / "v41-kb-vectors-survives.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)
        await conn.execute("DELETE FROM schema_version WHERE version >= 41")
        await conn.commit()

        await conn.execute("CREATE TABLE IF NOT EXISTS kb_vectors (rowid INTEGER PRIMARY KEY)")
        await conn.execute("INSERT INTO kb_vectors (rowid) VALUES (1)")
        await conn.commit()

        await ensure_schema(conn)

        async with conn.execute("SELECT COUNT(*) FROM kb_vectors") as cur:
            assert (await cur.fetchone())[0] == 1

        await conn.close()

    async def test_v41_idempotent_on_double_ensure(self, tmp_path) -> None:
        """ensure_schema twice on a fresh DB: v41 stamped exactly once
        (mirrors ``TestSchemaV40.test_v40_idempotent_on_double_ensure``)."""
        db_path = tmp_path / "v41-double.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)

        async with conn.execute("SELECT version FROM schema_version ORDER BY version") as cur:
            versions = [r[0] for r in await cur.fetchall()]
        assert versions.count(41) == 1, f"v41 row should appear exactly once: {versions}"

        await conn.close()

    async def test_v41_tolerant_of_rewind_rerun(self, tmp_path) -> None:
        """The ``>= 7`` rewind-rerun pattern: deleting every schema_version
        row from 7 upward and re-running ensure_schema re-fires the entire
        chain incl. v41 (mirrors ``TestSchemaV40.test_v40_tolerant_of_
        rewind_rerun``). Asserts on both halves of the v41 migration: the
        ``kb_vector_index`` shape is present and a pre-existing row
        survives, and the sqlite-vec ``app_metadata`` purge still fires
        (a stale sqlite-vec record inserted before the rewind is gone
        afterward) while a non-sqlite-vec record is untouched."""
        db_path = tmp_path / "v41-rewind.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        await conn.execute(
            "INSERT INTO kb_vector_index (kb_id, path, count, generation, dtype, dim, updated_at) "
            "VALUES ('kb1', '/tmp/kb1.usearch', 5, 2, 'f16', 512, 'ts-1')"
        )
        await conn.execute(
            "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
            (
                "knowledge.vector_store",
                '{"backend": "sqlite-vec", "dtype": "float32", "dim": 512, '
                '"model_id": "potion-retrieval-32M"}',
            ),
        )
        await conn.commit()

        await conn.execute("DELETE FROM schema_version WHERE version >= 7")
        await conn.commit()

        await ensure_schema(conn)  # must not raise

        async with conn.execute("PRAGMA table_info(kb_vector_index)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        assert cols == {
            "kb_id",
            "path",
            "count",
            "generation",
            "dtype",
            "dim",
            "updated_at",
        }, cols

        async with conn.execute("SELECT * FROM kb_vector_index WHERE kb_id = 'kb1'") as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["count"] == 5
        assert row["generation"] == 2
        assert row["dtype"] == "f16"

        async with conn.execute(
            "SELECT value FROM app_metadata WHERE key = 'knowledge.vector_store'"
        ) as cur:
            purged_row = await cur.fetchone()
        assert purged_row is None, "stale sqlite-vec record should have been purged on rewind-rerun"

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()

    async def test_v41_app_metadata_absent_guard(self, tmp_path) -> None:
        """AC-5c's guard (``the_one/db/schema.py`` ~2603-2611): a hand-built
        fixture stamped past v31 with no ``app_metadata`` table at all must
        run ``ensure_schema`` through to v41 without raising. Without the
        ``app_metadata_exists`` guard, the unconditional ``DELETE FROM
        app_metadata ...`` raises ``sqlite3.OperationalError: no such
        table: app_metadata`` (verified by hand against a patched copy of
        the migration with the guard removed — reproduced separately, not
        exercised in-repo). ``TestSchemaV32``'s v31 fixture only covers
        this incidentally (it happens to omit ``app_metadata`` too, as a
        side effect of testing something else); this test targets the
        guard directly."""
        db_path = tmp_path / "v41-no-app-metadata.db"
        conn = await aiosqlite.connect(str(db_path))
        await conn.execute("PRAGMA synchronous=OFF")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Hand-built fixture: only schema_version, stamped 1..31, with no
        # other table at all — in particular no app_metadata (created by
        # the real v31 block, which this fixture bypasses entirely by
        # stamping directly).
        await conn.executescript("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        for v in range(1, 32):
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        await conn.commit()

        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='app_metadata'"
        ) as cur:
            assert (await cur.fetchone()) is None  # precondition: table absent

        await ensure_schema(conn)  # must not raise

        async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
            names = {r["name"] for r in await cur.fetchall()}
        assert "kb_vector_index" in names

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == CURRENT_VERSION

        await conn.close()


# ── v42 (Mission 27 Flight 1, DD3): agent_rules + agent_revisions rebuild ──


_V37_SHAPE_REVISIONS = (
    "PRAGMA foreign_keys=OFF;\n"
    "DROP TABLE agent_revisions;\n"
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
    "ALTER TABLE agent_revisions_new RENAME TO agent_revisions;\n"
    "CREATE INDEX IF NOT EXISTS idx_agent_revisions_agent_status "
    "ON agent_revisions (agent_name, status);\n"
)


async def _open(path) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(str(path))
    await conn.execute("PRAGMA synchronous=OFF")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def _fk_rows(conn, table: str) -> dict[str, aiosqlite.Row]:
    async with conn.execute(f"PRAGMA foreign_key_list({table})") as cur:
        return {r["from"]: r for r in await cur.fetchall()}


async def _rewind_to_v41(conn, *, legacy_alter: bool) -> None:
    """Make a populated v41-shaped database: ``agent_revisions`` in its v37
    shape (no ON UPDATE action), no ``agent_rules``, stamp 42 removed.
    ``legacy_alter`` leaves the self-FK naming ``agent_revisions_new`` the way
    a build with ``legacy_alter_table`` on would."""
    await conn.execute("DROP TABLE IF EXISTS agent_rules")
    await conn.commit()
    if legacy_alter:
        await conn.execute("PRAGMA legacy_alter_table=ON")
    await conn.executescript(_V37_SHAPE_REVISIONS)
    if legacy_alter:
        await conn.execute("PRAGMA legacy_alter_table=OFF")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.execute("DELETE FROM schema_version WHERE version >= 42")
    await conn.commit()


async def _seed_revisions(conn) -> None:
    await conn.execute(
        "INSERT INTO agents (name, description, system_prompt) VALUES ('alpha', '', '')"
    )
    rows = [
        ("r1", "alpha", "description", "p1", "b1", "applied", "self", None, None),
        ("r2", "alpha", "system_prompt", "p2", "b2", "applied", "external", "ext_x", None),
        ("r3", "alpha", "description", "b1", "p1", "applied", "restore", None, "r1"),
        ("r4", "alpha", "description", "p4", "b4", "pending", "self", None, None),
    ]
    for r in rows:
        await conn.execute(
            "INSERT INTO agent_revisions (id, agent_name, field, proposed_value, base_value, "
            "status, source, source_principal, restored_from, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 't')",
            r,
        )
    await conn.commit()


class TestSchemaV42:
    async def test_fresh_replay_has_agent_rules_and_cascading_revisions(self, tmp_path) -> None:
        """AC1, AC3: a fresh v0 replay (v34 creates, v37 rebuilds, v42
        rebuilds again) reaches v43 with the new table and FK shapes."""
        conn = await _open(tmp_path / "fresh.db")
        await ensure_schema(conn)

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == 52 == CURRENT_VERSION
        async with conn.execute("PRAGMA table_info(agent_rules)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        assert list(cols) == [
            "id",
            "agent_name",
            "text",
            "enabled",
            "position",
            "created_at",
            "updated_at",
        ]
        assert cols["enabled"]["dflt_value"] == "1"
        fk = (await _fk_rows(conn, "agent_rules"))["agent_name"]
        assert (fk["table"], fk["on_update"], fk["on_delete"]) == ("agents", "CASCADE", "CASCADE")
        async with conn.execute("PRAGMA index_info(idx_agent_rules_agent_position)") as cur:
            assert [r["name"] for r in await cur.fetchall()] == ["agent_name", "position"]

        fks = await _fk_rows(conn, "agent_revisions")
        assert (fks["agent_name"]["table"], fks["agent_name"]["on_update"]) == (
            "agents",
            "CASCADE",
        )
        assert fks["agent_name"]["on_delete"] == "CASCADE"
        assert fks["restored_from"]["table"] == "agent_revisions"
        assert fks["restored_from"]["on_delete"] == "SET NULL"
        await conn.close()

    @pytest.mark.parametrize("legacy_alter", [False, True])
    async def test_populated_v41_upgrade_keeps_rows_chain_and_index(
        self, tmp_path, legacy_alter
    ) -> None:
        """AC2, AC3: a populated v41 database (also one whose self-FK still
        names ``agent_revisions_new``) keeps every row, the restored_from
        chain and the index, and gains the cascading FKs."""
        conn = await _open(tmp_path / f"v41-{legacy_alter}.db")
        await ensure_schema(conn)
        await _rewind_to_v41(conn, legacy_alter=legacy_alter)
        before = await _fk_rows(conn, "agent_revisions")
        assert before["agent_name"]["on_update"] == "NO ACTION"
        if legacy_alter:
            assert before["restored_from"]["table"] == "agent_revisions_new"
        # The `_new`-named self-FK dangles, so seed with enforcement off.
        await conn.execute("PRAGMA foreign_keys=OFF")
        await _seed_revisions(conn)
        await conn.execute("PRAGMA foreign_keys=ON")
        async with conn.execute("SELECT * FROM agent_revisions ORDER BY id") as cur:
            rows_before = [tuple(r) for r in await cur.fetchall()]

        await ensure_schema(conn)

        async with conn.execute("SELECT * FROM agent_revisions ORDER BY id") as cur:
            assert [tuple(r) for r in await cur.fetchall()] == rows_before
        async with conn.execute("SELECT restored_from FROM agent_revisions WHERE id = 'r3'") as cur:
            assert (await cur.fetchone())[0] == "r1"
        async with conn.execute("PRAGMA index_list(agent_revisions)") as cur:
            assert "idx_agent_revisions_agent_status" in {r["name"] for r in await cur.fetchall()}
        fks = await _fk_rows(conn, "agent_revisions")
        assert (fks["agent_name"]["on_update"], fks["agent_name"]["on_delete"]) == (
            "CASCADE",
            "CASCADE",
        )
        assert fks["restored_from"]["table"] == "agent_revisions"
        assert fks["restored_from"]["on_delete"] == "SET NULL"
        async with conn.execute("PRAGMA foreign_keys") as cur:
            assert (await cur.fetchone())[0] == 1
        async with conn.execute("PRAGMA foreign_key_check") as cur:
            assert await cur.fetchall() == []
        # SET NULL still works on the rebuilt self-reference.
        await conn.execute("DELETE FROM agent_revisions WHERE id = 'r1'")
        async with conn.execute("SELECT restored_from FROM agent_revisions WHERE id = 'r3'") as cur:
            assert (await cur.fetchone())[0] is None
        await conn.close()

    async def test_rerun_on_v42_changes_nothing(self, tmp_path) -> None:
        """AC4: the guard — a second ensure_schema leaves the table alone."""
        conn = await _open(tmp_path / "rerun.db")
        await ensure_schema(conn)
        await _seed_revisions(conn)
        # Rewind only the stamp: the table already carries the cascade.
        await conn.execute("DELETE FROM schema_version WHERE version >= 42")
        await conn.commit()
        async with conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'agent_revisions'"
        ) as cur:
            sql_before = (await cur.fetchone())[0]
        await ensure_schema(conn)
        async with conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'agent_revisions'"
        ) as cur:
            assert (await cur.fetchone())[0] == sql_before
        async with conn.execute("SELECT COUNT(*) FROM agent_revisions") as cur:
            assert (await cur.fetchone())[0] == 4
        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 42") as cur:
            assert (await cur.fetchone())[0] == 1
        await conn.close()

    async def test_rename_carries_revisions_and_rules(self, tmp_path) -> None:
        """AC5: renaming an agent with revision AND rule rows succeeds and both
        follow. Without the v42 rebuild the same rename raises ``FOREIGN KEY
        constraint failed`` (Known Issue 1); the pre-rebuild half asserts it."""
        from the_one.db.repositories import AgentRuleRepository

        conn = await _open(tmp_path / "rename.db")
        await ensure_schema(conn)
        store = SQLiteAgentStore(conn, None)

        # Pre-v42 shape: the rename fails (this is what main did).
        await _rewind_to_v41(conn, legacy_alter=False)
        await _seed_revisions(conn)
        with pytest.raises(aiosqlite.IntegrityError, match="FOREIGN KEY"):
            await store.rename("alpha", "beta")
        await conn.rollback()

        # After the migration it succeeds and carries both tables.
        await ensure_schema(conn)
        await AgentRuleRepository(conn).create("alpha", "Rule one.")
        await store.rename("alpha", "beta")
        async with conn.execute("SELECT DISTINCT agent_name FROM agent_revisions") as cur:
            assert [r[0] for r in await cur.fetchall()] == ["beta"]
        async with conn.execute("SELECT agent_name, text FROM agent_rules") as cur:
            assert [tuple(r) for r in await cur.fetchall()] == [("beta", "Rule one.")]
        await conn.close()

    async def test_delete_agent_cascades_rules_and_revisions(self, tmp_path) -> None:
        from the_one.db.repositories import AgentRuleRepository

        conn = await _open(tmp_path / "delete.db")
        await ensure_schema(conn)
        await _seed_revisions(conn)
        await AgentRuleRepository(conn).create("alpha", "Rule one.")
        await SQLiteAgentStore(conn, None).delete("alpha")
        for table in ("agent_rules", "agent_revisions"):
            async with conn.execute(f"SELECT COUNT(*) FROM {table}") as cur:
                assert (await cur.fetchone())[0] == 0
        await conn.close()


# ── v43 (Mission 27 Flight 2, DD1): agent_notes + notes columns ──


class TestSchemaV43:
    async def test_fresh_replay_has_agent_notes_and_columns(self, tmp_path) -> None:
        conn = await _open(tmp_path / "fresh43.db")
        await ensure_schema(conn)
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == 52 == CURRENT_VERSION
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            acols = {r["name"]: r for r in await cur.fetchall()}
        for name, default in (("notes_enabled", "0"), ("notes_next_number", "1")):
            col = acols[name]
            assert (col["type"], col["notnull"], str(col["dflt_value"])) == (
                "INTEGER",
                1,
                default,
            )
        async with conn.execute("PRAGMA table_info(agent_notes)") as cur:
            cols = [r["name"] for r in await cur.fetchall()]
        assert cols == [
            "id",
            "agent_name",
            "number",
            "text",
            "untrusted",
            "untrusted_sources",
            "origin_kind",
            "origin_session_id",
            "origin_label",
            "origin_platform",
            "origin_peer_id",
            "origin_peer_name",
            "created_at",
            "updated_at",
            "updated_by",
        ]
        fk = (await _fk_rows(conn, "agent_notes"))["agent_name"]
        assert (fk["table"], fk["on_update"], fk["on_delete"]) == ("agents", "CASCADE", "CASCADE")
        async with conn.execute("PRAGMA index_list(agent_notes)") as cur:
            idx = {r["name"]: r for r in await cur.fetchall()}
        assert idx["idx_agent_notes_agent_number"]["unique"] == 1
        # CHECK constraints
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO agent_notes (id, agent_name, number, text, origin_kind, "
                "created_at, updated_at, updated_by) VALUES ('1','a',1,'t','bogus','t','t','agent')"
            )
        await conn.close()

    async def test_rewound_to_v42_reruns_guards(self, tmp_path) -> None:
        """A v42 database with existing agents backfills the columns; a rewind
        that still has the table and columns re-runs without error."""
        conn = await _open(tmp_path / "v42.db")
        await ensure_schema(conn)
        await conn.execute("INSERT INTO agents (name) VALUES ('legacy')")
        await conn.commit()
        await conn.execute("DELETE FROM schema_version WHERE version >= 43")
        await conn.commit()
        await ensure_schema(conn)  # columns + table present: guards make it a no-op
        await ensure_schema(conn)
        async with conn.execute(
            "SELECT notes_enabled, notes_next_number FROM agents WHERE name='legacy'"
        ) as cur:
            assert tuple(await cur.fetchone()) == (0, 1)
        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 43") as cur:
            assert (await cur.fetchone())[0] == 1
        await conn.close()

    async def test_rename_carries_notes_and_counter_delete_removes(self, tmp_path) -> None:
        conn = await _open(tmp_path / "rename43.db")
        await ensure_schema(conn)
        store = SQLiteAgentStore(conn, None)
        await conn.execute("INSERT INTO agents (name, notes_enabled) VALUES ('alpha', 1)")
        await conn.execute(
            "INSERT INTO agent_notes (id, agent_name, number, text, untrusted, origin_kind, "
            "created_at, updated_at, updated_by) VALUES ('n1','alpha',3,'keep me',1,'web',"
            "'t','t','agent')"
        )
        await conn.execute("UPDATE agents SET notes_next_number = 4 WHERE name='alpha'")
        await conn.commit()
        await store.rename("alpha", "beta")
        async with conn.execute(
            "SELECT agent_name, number, text, untrusted FROM agent_notes"
        ) as cur:
            assert [tuple(r) for r in await cur.fetchall()] == [("beta", 3, "keep me", 1)]
        async with conn.execute(
            "SELECT notes_enabled, notes_next_number FROM agents WHERE name='beta'"
        ) as cur:
            assert tuple(await cur.fetchone()) == (1, 4)
        await store.delete("beta")
        async with conn.execute("SELECT COUNT(*) FROM agent_notes") as cur:
            assert (await cur.fetchone())[0] == 0
        await conn.close()


# ── v44 (Sortie 03, DD8): llm_providers CHECK admits anthropic-plan-token ──


_V43_LLM_PROVIDERS_REBUILD = """\
PRAGMA foreign_keys=OFF;
DROP TABLE IF EXISTS llm_providers_old;
CREATE TABLE llm_providers_old (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN
        ('ollama','openai-compatible','openai','anthropic','mock','openrouter','anthropic-plan')),
    base_url TEXT NOT NULL,
    api_key TEXT,
    config TEXT DEFAULT '{}',
    secrets TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO llm_providers_old SELECT id, name, type, base_url, api_key, config, secrets,
    created_at, updated_at FROM llm_providers;
DROP TABLE llm_providers;
ALTER TABLE llm_providers_old RENAME TO llm_providers;
PRAGMA foreign_keys=ON;
"""

_SECRETS_BLOB = "gAAAAABmFAKE-ciphertext-bytes-must-survive=="


class TestSchemaV44:
    async def _v43_db(self, tmp_path):
        """A database at v43: old CHECK, an OAuth plan row, an agent referencing it."""
        conn = await _open(tmp_path / "v43.db")
        await ensure_schema(conn)
        await conn.executescript(_V43_LLM_PROVIDERS_REBUILD)
        await conn.execute(
            "INSERT INTO llm_providers (id, name, type, base_url, api_key, config, secrets) "
            "VALUES ('p-plan', 'Plan', 'anthropic-plan', 'https://api.anthropic.com', NULL, "
            "'{}', ?)",
            (_SECRETS_BLOB,),
        )
        await conn.execute("INSERT INTO agents (name, provider_config_id) VALUES ('a', 'p-plan')")
        await conn.execute("DELETE FROM schema_version WHERE version >= 44")
        await conn.commit()
        # Prove the old CHECK rejects the new type.
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO llm_providers (id, name, type, base_url) "
                "VALUES ('x', 'X', 'anthropic-plan-token', 'u')"
            )
        return conn

    async def test_current_version_is_45(self) -> None:
        assert CURRENT_VERSION == 52

    async def test_v43_to_v44_preserves_rows_secrets_and_agent_link(self, tmp_path) -> None:
        conn = await self._v43_db(tmp_path)
        await ensure_schema(conn)
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == 52
        async with conn.execute(
            "SELECT id, name, type, base_url, api_key, config, secrets FROM llm_providers"
        ) as cur:
            rows = [tuple(r) for r in await cur.fetchall()]
        assert rows == [
            (
                "p-plan",
                "Plan",
                "anthropic-plan",
                "https://api.anthropic.com",
                None,
                "{}",
                _SECRETS_BLOB,
            )
        ]
        async with conn.execute("SELECT provider_config_id FROM agents WHERE name='a'") as cur:
            assert (await cur.fetchone())[0] == "p-plan"
        await conn.execute(
            "INSERT INTO llm_providers (id, name, type, base_url, api_key) "
            "VALUES ('p-tok', 'Tok', 'anthropic-plan-token', 'https://api.anthropic.com', 'k')"
        )
        await conn.commit()
        async with conn.execute("PRAGMA foreign_key_check") as cur:
            assert await cur.fetchall() == []
        await conn.close()

    async def test_secrets_decrypt_after_migration(self, tmp_path) -> None:
        from cryptography.fernet import Fernet

        from the_one.db.repositories import LLMProviderRepository
        from the_one.encryption import Encryptor

        conn = await self._v43_db(tmp_path)
        key = Fernet.generate_key()
        enc = Encryptor(key, key_path=tmp_path / "k.key")
        import json as _json

        blob = enc.encrypt(_json.dumps({"access_token": "A", "refresh_token": "R"}))
        await conn.execute("UPDATE llm_providers SET secrets = ? WHERE id = 'p-plan'", (blob,))
        await conn.commit()
        await ensure_schema(conn)
        row = await LLMProviderRepository(conn, enc).get("p-plan")
        assert row.secrets == {"access_token": "A", "refresh_token": "R"}
        await conn.close()

    async def test_fresh_database_admits_the_type(self, tmp_path) -> None:
        conn = await _open(tmp_path / "fresh44.db")
        await ensure_schema(conn)
        await conn.execute(
            "INSERT INTO llm_providers (id, name, type, base_url) "
            "VALUES ('t', 'T', 'anthropic-plan-token', 'u')"
        )
        await conn.commit()
        await conn.close()

    async def test_rerun_after_crash_between_create_and_rename_is_idempotent(
        self, tmp_path
    ) -> None:
        conn = await self._v43_db(tmp_path)
        # Simulate the crash: a stale llm_providers_new left behind.
        await conn.execute("CREATE TABLE llm_providers_new (id TEXT)")
        await conn.commit()
        await ensure_schema(conn)
        await ensure_schema(conn)
        async with conn.execute("SELECT secrets FROM llm_providers WHERE id='p-plan'") as cur:
            assert (await cur.fetchone())[0] == _SECRETS_BLOB
        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 44") as cur:
            assert (await cur.fetchone())[0] == 1
        await conn.close()


# ── v45 (Mission 33 F1 DD1): agent_routines and agent_routine_runs ─────────

# The columns after the whole chain (v49 dropped the target columns and `new_chat`).
_ROUTINE_COLS = [
    "id", "agent_name", "name", "prompt", "schedule", "enabled", "finished_at",
    "next_run_at", "anchor_at", "created_by", "created_at", "updated_at", "untrusted",
    "untrusted_sources",
]  # fmt: skip
_RUN_COLS = [
    "id", "routine_id", "trigger_kind", "outcome", "reason", "due_at", "started_at",
    "finished_at", "session_id", "repeats", "reason_code",
]  # fmt: skip


_DAILY_OLD = json.dumps({"kind": "daily", "time": "09:00"})


async def _insert_routine(conn, rid="r1", agent="a", name="Daily", **over) -> None:
    vals = {
        "id": rid,
        "agent_name": agent,
        "name": name,
        "prompt": "p",
        "schedule": _DAILY_OLD,
        "created_by": "operator",
        "created_at": "2026-10-01T00:00:00+00:00",
        "updated_at": "t",
        **over,
    }
    cols = ", ".join(vals)
    marks = ", ".join("?" for _ in vals)
    await conn.execute(
        f"INSERT INTO agent_routines ({cols}) VALUES ({marks})", tuple(vals.values())
    )


async def _insert_run(conn, rid="u1", routine="r1", **over) -> None:
    vals = {"id": rid, "routine_id": routine, "trigger_kind": "manual", "outcome": "ok", **over}
    cols = ", ".join(vals)
    marks = ", ".join("?" for _ in vals)
    await conn.execute(
        f"INSERT INTO agent_routine_runs ({cols}) VALUES ({marks})", tuple(vals.values())
    )


class TestSchemaV45:
    async def test_current_version_is_46_or_later(self) -> None:
        assert CURRENT_VERSION >= 45

    async def test_fresh_replay_columns_and_fks(self, tmp_path) -> None:
        conn = await _open(tmp_path / "fresh.db")
        await ensure_schema(conn)
        async with conn.execute("PRAGMA table_info(agent_routines)") as cur:
            assert [r["name"] for r in await cur.fetchall()] == _ROUTINE_COLS
        async with conn.execute("PRAGMA table_info(agent_routine_runs)") as cur:
            assert [r["name"] for r in await cur.fetchall()] == _RUN_COLS
        fk = (await _fk_rows(conn, "agent_routines"))["agent_name"]
        assert (fk["table"], fk["on_update"], fk["on_delete"]) == ("agents", "CASCADE", "CASCADE")
        fk = (await _fk_rows(conn, "agent_routine_runs"))["routine_id"]
        assert (fk["table"], fk["on_delete"]) == ("agent_routines", "CASCADE")
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == 52
        await conn.close()

    async def test_v44_database_migrates(self, tmp_path) -> None:
        conn = await _open(tmp_path / "v44.db")
        await ensure_schema(conn)
        await conn.execute("DROP TABLE agent_routine_proposals")
        await conn.execute("DROP TABLE agent_routine_runs")
        await conn.execute("DROP TABLE agent_routines")
        await conn.execute("DELETE FROM schema_version WHERE version >= 45")
        await conn.commit()
        await ensure_schema(conn)
        await ensure_schema(conn)  # idempotent
        async with conn.execute("PRAGMA table_info(agent_routines)") as cur:
            assert [r["name"] for r in await cur.fetchall()] == _ROUTINE_COLS
        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 45") as cur:
            assert (await cur.fetchone())[0] == 1
        await conn.close()

    async def test_rewind_rerun_keeps_rows(self, tmp_path) -> None:
        conn = await _open(tmp_path / "rewind.db")
        await ensure_schema(conn)
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        await _insert_routine(conn)
        await _insert_run(conn)
        await conn.execute("DELETE FROM schema_version WHERE version >= 45")
        await conn.commit()
        await ensure_schema(conn)
        await ensure_schema(conn)
        async with conn.execute("SELECT COUNT(*) FROM agent_routines") as cur:
            assert (await cur.fetchone())[0] == 1
        async with conn.execute("SELECT COUNT(*) FROM agent_routine_runs") as cur:
            assert (await cur.fetchone())[0] == 1
        await conn.close()

    async def test_unique_name_per_agent_nocase_and_checks(self, tmp_path) -> None:
        conn = await _open(tmp_path / "u.db")
        await ensure_schema(conn)
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        await conn.execute("INSERT INTO agents (name) VALUES ('b')")
        await _insert_routine(conn, "r1", "a", "Daily")
        with pytest.raises(aiosqlite.IntegrityError):
            await _insert_routine(conn, "r2", "a", "daily")
        await _insert_routine(conn, "r3", "b", "daily")  # same name, another agent
        with pytest.raises(aiosqlite.IntegrityError):
            await _insert_routine(conn, "r5", "a", "y", created_by="robot")
        with pytest.raises(aiosqlite.IntegrityError):
            await _insert_run(conn, "u1", "r1", trigger_kind="cron")
        with pytest.raises(aiosqlite.IntegrityError):
            await _insert_run(conn, "u2", "r1", outcome="weird")
        await conn.close()

    async def test_rename_carries_routines_and_runs_delete_removes_both(self, tmp_path) -> None:
        conn = await _open(tmp_path / "c.db")
        await ensure_schema(conn)
        store = SQLiteAgentStore(conn)
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        await _insert_routine(conn)
        await _insert_run(conn)
        await conn.commit()
        await store.rename("a", "renamed")
        async with conn.execute("SELECT agent_name FROM agent_routines") as cur:
            assert [r[0] for r in await cur.fetchall()] == ["renamed"]
        async with conn.execute("SELECT routine_id FROM agent_routine_runs") as cur:
            assert [r[0] for r in await cur.fetchall()] == ["r1"]
        await store.delete("renamed")
        for table in ("agent_routines", "agent_routine_runs"):
            async with conn.execute(f"SELECT COUNT(*) FROM {table}") as cur:
                assert (await cur.fetchone())[0] == 0
        await conn.close()

    async def test_agent_upsert_leaves_routines_untouched(self, tmp_path) -> None:
        from the_one.agent.config import AgentConfig

        conn = await _open(tmp_path / "up.db")
        await ensure_schema(conn)
        store = SQLiteAgentStore(conn)
        await store.save(AgentConfig(name="a"))
        await _insert_routine(conn)
        await _insert_run(conn)
        await conn.commit()
        await store.save(AgentConfig(name="a", description="changed"))
        for table in ("agent_routines", "agent_routine_runs"):
            async with conn.execute(f"SELECT COUNT(*) FROM {table}") as cur:
                assert (await cur.fetchone())[0] == 1
        await conn.close()


# ── v46 (Mission 33 F2 DD4): routine switches, flag, proposals ─────────────


class TestSchemaV46:
    async def test_current_version_is_46_or_later(self) -> None:
        assert CURRENT_VERSION >= 46

    async def test_fresh_columns_defaults_table_and_index(self, tmp_path) -> None:
        conn = await _open(tmp_path / "fresh46.db")
        await ensure_schema(conn)
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        assert cols["routines_self_config_enabled"]["dflt_value"] == "0"
        assert cols["routines_require_approval"]["dflt_value"] == "1"
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        async with conn.execute(
            "SELECT routines_self_config_enabled, routines_require_approval FROM agents"
        ) as cur:
            assert tuple(await cur.fetchone()) == (0, 1)
        await _insert_routine(conn)
        async with conn.execute("SELECT untrusted, untrusted_sources FROM agent_routines") as cur:
            assert tuple(await cur.fetchone()) == (0, None)
        async with conn.execute("PRAGMA table_info(agent_routine_proposals)") as cur:
            assert [r["name"] for r in await cur.fetchall()] == [
                "id", "agent_name", "routine_id", "routine_name", "action", "payload", "base",
                "status", "untrusted", "untrusted_sources", "session_id", "created_at",
                "resolved_at",
            ]  # fmt: skip
        fks = await _fk_rows(conn, "agent_routine_proposals")
        assert (fks["agent_name"]["on_update"], fks["agent_name"]["on_delete"]) == (
            "CASCADE",
            "CASCADE",
        )
        assert fks["routine_id"]["on_delete"] == "SET NULL"
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'idx_agent_routine_proposals_agent_status'"
        ) as cur:
            assert await cur.fetchone() is not None
        base = ("p1", "a", None, "n", "create", "{}", None, "pending", 0, None, None, "t", None)
        sql = "INSERT INTO agent_routine_proposals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
        await conn.execute(sql, base)
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(sql, ("p2", "a", None, "n", "bogus", *base[5:]))
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                sql, ("p3", "a", None, "n", "create", "{}", None, "weird", *base[8:])
            )
        await conn.close()

    async def test_v45_database_migrates_and_keeps_rows(self, tmp_path) -> None:
        conn = await _open(tmp_path / "v45.db")
        await ensure_schema(conn)
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        await _insert_routine(conn)
        await conn.execute("DROP TABLE agent_routine_proposals")
        await conn.execute("ALTER TABLE agents DROP COLUMN routines_self_config_enabled")
        await conn.execute("ALTER TABLE agents DROP COLUMN routines_require_approval")
        await conn.execute("ALTER TABLE agent_routines DROP COLUMN untrusted")
        await conn.execute("ALTER TABLE agent_routines DROP COLUMN untrusted_sources")
        await conn.execute("DELETE FROM schema_version WHERE version >= 46")
        await conn.commit()
        await ensure_schema(conn)
        await ensure_schema(conn)
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == 52
        async with conn.execute(
            "SELECT routines_self_config_enabled, routines_require_approval FROM agents"
        ) as cur:
            assert tuple(await cur.fetchone()) == (0, 1)
        async with conn.execute("PRAGMA table_info(agent_routines)") as cur:
            assert [r["name"] for r in await cur.fetchall()] == _ROUTINE_COLS
        async with conn.execute("SELECT COUNT(*) FROM agent_routines") as cur:
            assert (await cur.fetchone())[0] == 1
        await conn.close()


# ── v47 (Mission 33 F3 DD11): run repeats and reason code ──────────────────


class TestSchemaV47:
    async def test_current_version_is_47_or_later(self) -> None:
        assert CURRENT_VERSION >= 47

    async def test_fresh_replay_columns_and_defaults(self, tmp_path) -> None:
        conn = await _open(tmp_path / "fresh47.db")
        await ensure_schema(conn)
        async with conn.execute("PRAGMA table_info(agent_routine_runs)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        assert list(cols) == _RUN_COLS
        assert cols["repeats"]["dflt_value"] == "1" and cols["repeats"]["notnull"] == 1
        assert cols["reason_code"]["notnull"] == 0
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        await _insert_routine(conn)
        await _insert_run(conn)
        async with conn.execute("SELECT repeats, reason_code FROM agent_routine_runs") as cur:
            assert tuple(await cur.fetchone()) == (1, None)
        await conn.close()

    async def test_v46_database_migrates_keeps_rows_and_is_idempotent(self, tmp_path) -> None:
        conn = await _open(tmp_path / "v46.db")
        await ensure_schema(conn)
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        await _insert_routine(conn, schedule=_DAILY_OLD)
        await _insert_run(conn, reason="old")
        await conn.execute("ALTER TABLE agent_routine_runs DROP COLUMN repeats")
        await conn.execute("ALTER TABLE agent_routine_runs DROP COLUMN reason_code")
        await conn.execute("DELETE FROM schema_version WHERE version >= 47")
        await conn.commit()
        await ensure_schema(conn)
        await ensure_schema(conn)
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == 52
        async with conn.execute("PRAGMA table_info(agent_routine_runs)") as cur:
            assert [r["name"] for r in await cur.fetchall()] == _RUN_COLS
        async with conn.execute(
            "SELECT reason, repeats, reason_code FROM agent_routine_runs"
        ) as cur:
            assert tuple(await cur.fetchone()) == ("old", 1, None)
        await conn.close()


# ── v48 (Mission 33 F3 DD6): the schedule rewrite ──────────────────────────

_LA = "America/Los_Angeles"


async def _v47_db(path, *, zone_key=_LA):
    """A migrated database rewound to just before v48, holding one agent."""
    conn = await _open(path)
    await ensure_schema(conn)
    await conn.execute("INSERT INTO agents (name) VALUES ('a')")
    if zone_key is not None:
        await conn.execute(
            "INSERT OR REPLACE INTO app_metadata (key, value) VALUES ('routines_zone', ?)",
            (zone_key,),
        )
    await conn.commit()
    return conn


async def _rewind_48(conn) -> None:
    await conn.execute("DELETE FROM schema_version WHERE version >= 48")
    await conn.commit()
    await ensure_schema(conn)


async def _routine(conn, rid="r1"):
    async with conn.execute(
        "SELECT schedule, anchor_at, next_run_at, enabled, finished_at "
        "FROM agent_routines WHERE id = ?",
        (rid,),
    ) as cur:
        row = await cur.fetchone()
    return json.loads(row["schedule"]), row["anchor_at"], row["next_run_at"], row["enabled"], row


def _legacy(**kw) -> str:
    return json.dumps(kw)


class TestSchemaV48:
    async def test_current_version_is_48_or_later(self) -> None:
        assert CURRENT_VERSION >= 48

    async def test_daily_weekdays_weekly_on_and_off(self, tmp_path) -> None:
        conn = await _v47_db(tmp_path / "a.db")
        # 2026-10-12 is a Monday; 16:00Z is 09:00 PDT.
        nxt = "2026-10-12T16:00:00+00:00"
        await _insert_routine(
            conn, "d", name="d", schedule=_legacy(kind="daily", time="09:00"), next_run_at=nxt
        )
        await _insert_routine(
            conn, "wd", name="wd", schedule=_legacy(kind="weekdays", time="09:00"), next_run_at=nxt
        )
        await _insert_routine(
            conn,
            "w",
            name="w",
            schedule=_legacy(kind="weekly", days=[3, 1, 1], time="09:30"),
            next_run_at=nxt,
        )
        await _insert_routine(
            conn,
            "off",
            name="off",
            schedule=_legacy(kind="daily", time="08:15"),
            enabled=0,
            created_at="2026-09-01T03:00:00+00:00",
        )
        await conn.commit()
        await _rewind_48(conn)
        ends = {"kind": "never"}
        sched, anchor, got_next, _e, _r = await _routine(conn, "d")
        assert sched == {
            "start": {"date": "2026-10-12", "time": "09:00"},
            "repeat": {"every": 1, "unit": "day"},
            "ends": ends,
        }
        assert anchor is None and got_next == nxt
        sched, *_ = await _routine(conn, "wd")
        assert sched["repeat"] == {"every": 1, "unit": "week", "days": [0, 1, 2, 3, 4]}
        sched, *_ = await _routine(conn, "w")
        assert sched["repeat"] == {"every": 1, "unit": "week", "days": [1, 3]}
        assert sched["start"] == {"date": "2026-10-12", "time": "09:30"}
        # Off: the date is the local date of created_at (Aug 31 evening in LA).
        sched, anchor, got_next, enabled, _r = await _routine(conn, "off")
        assert sched["start"] == {"date": "2026-08-31", "time": "08:15"}
        assert anchor is None and got_next is None and enabled == 0
        await conn.close()

    async def test_spring_forward_daily_keeps_its_wall_time(self, tmp_path) -> None:
        conn = await _v47_db(tmp_path / "gap.db")
        # 02:30 does not exist on 2027-03-14 in LA; next_run_at is 03:00 PDT = 10:00Z.
        nxt = "2027-03-14T10:00:00+00:00"
        await _insert_routine(
            conn, "g", name="g", schedule=_legacy(kind="daily", time="02:30"), next_run_at=nxt
        )
        await conn.commit()
        await _rewind_48(conn)
        sched, _a, got_next, *_ = await _routine(conn, "g")
        assert sched["start"] == {"date": "2027-03-14", "time": "02:30"}
        assert got_next == nxt
        await conn.close()

    async def test_interval_keeps_its_exact_anchor(self, tmp_path) -> None:
        conn = await _v47_db(tmp_path / "i.db")
        nxt = "2026-10-12T16:05:07.123456+00:00"
        await _insert_routine(
            conn, "on", name="on", schedule=_legacy(kind="interval", hours=3), next_run_at=nxt
        )
        # Off: anchor_at + hours, so the grid is the same either way.
        await _insert_routine(
            conn,
            "off",
            name="off",
            schedule=_legacy(kind="interval", hours=3),
            enabled=0,
            anchor_at="2026-10-12T13:05:07.123456+00:00",
        )
        await conn.commit()
        await _rewind_48(conn)
        sched, anchor, got_next, *_ = await _routine(conn, "on")
        assert anchor == nxt and got_next == nxt
        assert sched["repeat"] == {"every": 3, "unit": "hour"}
        assert sched["start"] == {"date": "2026-10-12", "time": "09:05"}
        _s, anchor, *_ = await _routine(conn, "off")
        assert anchor == nxt
        await conn.close()

    async def test_once_keeps_its_instant(self, tmp_path) -> None:
        conn = await _v47_db(tmp_path / "o.db")
        at = "2026-11-02T01:30:15+00:00"
        await _insert_routine(
            conn, "o", name="o", schedule=_legacy(kind="once", at=at), next_run_at=at
        )
        await _insert_routine(
            conn,
            "done",
            name="done",
            schedule=_legacy(kind="once", at=at),
            enabled=1,
            finished_at="2026-11-02T01:31:00+00:00",
        )
        await conn.commit()
        await _rewind_48(conn)
        sched, anchor, got_next, *_ = await _routine(conn, "o")
        assert sched == {
            "start": {"date": "2026-11-01", "time": "17:30"},
            "repeat": None,
            "ends": {"kind": "never"},
        }
        assert anchor == at and got_next == at
        _s, anchor, got_next, *_ = await _routine(conn, "done")
        assert anchor == at and got_next is None
        await conn.close()

    async def test_without_routines_zone_the_effective_zone_decides(
        self, tmp_path, frozen_clock
    ) -> None:
        # frozen_clock pins the system zone to America/Los_Angeles by default.
        conn = await _v47_db(tmp_path / "nz.db", zone_key=None)
        # 04:00Z on Oct 13 is Oct 12 in LA, Oct 13 in UTC.
        await _insert_routine(
            conn,
            "d",
            name="d",
            schedule=_legacy(kind="daily", time="21:00"),
            next_run_at="2026-10-13T04:00:00+00:00",
        )
        await conn.commit()
        await _rewind_48(conn)
        sched, *_ = await _routine(conn, "d")
        assert sched["start"] == {"date": "2026-10-12", "time": "21:00"}
        await conn.close()

    async def test_invalid_zone_key_falls_back(self, tmp_path, frozen_clock) -> None:
        conn = await _v47_db(tmp_path / "bad.db", zone_key="Not/AZone")
        await _insert_routine(
            conn,
            "d",
            name="d",
            schedule=_legacy(kind="daily", time="21:00"),
            next_run_at="2026-10-13T04:00:00+00:00",
        )
        await conn.commit()
        await _rewind_48(conn)
        sched, *_ = await _routine(conn, "d")
        assert sched["start"]["date"] == "2026-10-12"
        await conn.close()

    async def test_proposals_are_rewritten_pending_and_resolved(self, tmp_path) -> None:
        conn = await _v47_db(tmp_path / "p.db")
        nxt = "2026-10-12T16:00:00+00:00"
        old = {"kind": "daily", "time": "09:00"}
        await _insert_routine(conn, "r1", schedule=json.dumps(old), next_run_at=nxt)

        async def prop(pid, status, routine_id, action, payload, base):
            await conn.execute(
                "INSERT INTO agent_routine_proposals (id, agent_name, routine_id, routine_name, "
                "action, payload, base, status, created_at) VALUES (?, 'a', ?, 'x', ?, ?, ?, ?, ?)",
                (
                    pid,
                    routine_id,
                    action,
                    json.dumps(payload),
                    json.dumps(base) if base is not None else None,
                    status,
                    "2026-10-10T23:00:00+00:00",
                ),
            )

        # A matching base takes the routine's migrated schedule verbatim.
        await prop(
            "p1",
            "pending",
            "r1",
            "update",
            {"schedule": {"kind": "interval", "hours": 2}},
            {"schedule": old, "name": "Daily"},
        )
        # A stale base is converted alone.
        await prop(
            "p2",
            "applied",
            "r1",
            "update",
            {"schedule": {"kind": "once", "at": "2026-10-20T10:00:00+00:00"}},
            {"schedule": {"kind": "daily", "time": "07:00"}},
        )
        # A create has no base; a delete's base gains anchor_at.
        await prop(
            "p3",
            "pending",
            None,
            "create",
            {"schedule": {"kind": "weekdays", "time": "10:00"}, "name": "n"},
            None,
        )
        await prop("p4", "dismissed", "r1", "delete", {}, {"schedule": old, "name": "Daily"})
        await conn.commit()
        await _rewind_48(conn)
        routine_sched, routine_anchor, *_ = await _routine(conn, "r1")

        async def get(pid):
            async with conn.execute(
                "SELECT payload, base FROM agent_routine_proposals WHERE id = ?", (pid,)
            ) as cur:
                r = await cur.fetchone()
            return json.loads(r["payload"]), json.loads(r["base"]) if r["base"] else None

        payload, base = await get("p1")
        assert base["schedule"] == routine_sched and base["anchor_at"] is None
        # Payload: an interval from the proposal's created_at, exactly two hours on.
        assert payload["anchor_at"] == "2026-10-11T01:00:00+00:00"
        assert payload["schedule"]["repeat"] == {"every": 2, "unit": "hour"}
        payload, base = await get("p2")
        assert payload["anchor_at"] == "2026-10-20T10:00:00+00:00"
        assert payload["schedule"]["repeat"] is None
        assert base["schedule"]["start"] == {"date": "2026-10-10", "time": "07:00"}
        assert base["anchor_at"] is None
        payload, base = await get("p3")
        assert base is None
        assert payload["schedule"]["repeat"]["days"] == [0, 1, 2, 3, 4]
        assert payload["anchor_at"] is None
        payload, base = await get("p4")
        assert base["schedule"] == routine_sched and "anchor_at" in base
        assert routine_anchor is None
        await conn.close()

    async def test_matching_interval_base_takes_the_routine_anchor(self, tmp_path) -> None:
        conn = await _v47_db(tmp_path / "pi.db")
        nxt = "2026-10-12T16:05:07.500000+00:00"
        old = {"kind": "interval", "hours": 4}
        await _insert_routine(conn, "r1", schedule=json.dumps(old), next_run_at=nxt)
        await conn.execute(
            "INSERT INTO agent_routine_proposals (id, agent_name, routine_id, routine_name, "
            "action, payload, base, status, created_at) VALUES "
            "('p', 'a', 'r1', 'x', 'update', '{\"enabled\": false}', ?, 'pending', 't')",
            (json.dumps({"schedule": old, "enabled": True}),),
        )
        await conn.commit()
        await _rewind_48(conn)
        async with conn.execute("SELECT base FROM agent_routine_proposals") as cur:
            base = json.loads((await cur.fetchone())["base"])
        assert base["anchor_at"] == nxt
        assert base["schedule"]["repeat"] == {"every": 4, "unit": "hour"}
        await conn.close()

    async def test_unreadable_schedules_turn_the_routine_off_with_one_run_row(
        self, tmp_path, frozen_clock
    ) -> None:
        conn = await _v47_db(tmp_path / "u.db")
        bads = {
            "j": "not json",
            "e": "{}",
            "k": _legacy(kind="monthly"),
            "t": _legacy(kind="daily", time="9am"),
            "h": _legacy(kind="interval", hours=0),
        }
        for rid, raw in bads.items():
            await _insert_routine(
                conn, rid, name=rid, schedule=raw, next_run_at="2026-10-12T16:00:00+00:00"
            )
        await _insert_routine(conn, "ok", name="ok", schedule=_DAILY_OLD)
        await conn.commit()
        await _rewind_48(conn)
        await _rewind_48(conn)  # a rewind re-run adds no duplicate
        for rid, raw in bads.items():
            async with conn.execute(
                "SELECT schedule, enabled FROM agent_routines WHERE id = ?", (rid,)
            ) as cur:
                row = await cur.fetchone()
            assert row["schedule"] == raw and row["enabled"] == 0
            async with conn.execute(
                "SELECT trigger_kind, outcome, reason, reason_code, started_at, finished_at "
                "FROM agent_routine_runs WHERE routine_id = ?",
                (rid,),
            ) as cur:
                runs = await cur.fetchall()
            assert len(runs) == 1
            r = runs[0]
            assert (r["trigger_kind"], r["outcome"], r["reason_code"]) == (
                "schedule",
                "failed",
                "upgrade_failed",
            )
            assert r["reason"] == (
                "This schedule could not be upgraded. Edit it to turn the routine back on."
            )
            assert r["started_at"] == r["finished_at"] == frozen_clock.isoformat()
        sched, *_ = await _routine(conn, "ok")
        assert sched["repeat"] == {"every": 1, "unit": "day"}
        await conn.close()

    async def test_rewind_is_idempotent(self, tmp_path) -> None:
        conn = await _v47_db(tmp_path / "idem.db")
        await _insert_routine(
            conn,
            "d",
            name="d",
            schedule=_legacy(kind="daily", time="09:00"),
            next_run_at="2026-10-12T16:00:00+00:00",
        )
        await conn.commit()
        await _rewind_48(conn)
        first = await _routine(conn, "d")
        await _rewind_48(conn)
        second = await _routine(conn, "d")
        assert first[:4] == second[:4]
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == 52
        await conn.close()

    async def test_database_without_routine_tables_migrates(self, tmp_path) -> None:
        conn = await _open(tmp_path / "bare.db")
        await ensure_schema(conn)
        await conn.execute("DROP TABLE agent_routine_proposals")
        await conn.execute("DROP TABLE agent_routine_runs")
        await conn.execute("DROP TABLE agent_routines")
        await conn.execute("DELETE FROM schema_version WHERE version >= 45")
        await conn.commit()
        await ensure_schema(conn)
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == 52
        await conn.close()


# ── v49 (Mission 33 F4): routines lose their target ────────────────────────

_V48_ROUTINES_DDL = (
    "CREATE TABLE agent_routines ("
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
    "    untrusted INTEGER NOT NULL DEFAULT 0,"
    "    untrusted_sources TEXT,"
    "    UNIQUE (agent_name, name COLLATE NOCASE)"
    ")"
)
_V48_RUNS_DDL = (
    "CREATE TABLE agent_routine_runs ("
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
    "    new_chat INTEGER NOT NULL DEFAULT 0,"
    "    repeats INTEGER NOT NULL DEFAULT 1,"
    "    reason_code TEXT"
    ")"
)
_V49_TARGET_COLS = (
    "target_kind", "target_session_id", "target_platform", "target_connector_id",
    "target_channel_id", "target_thread_id", "target_peer_id",
)  # fmt: skip


async def _v48_db(path):
    """A database in the exact v48 shape (target columns, `new_chat`, version 48), with
    agents `a` and `b`."""
    conn = await _open(path)
    await ensure_schema(conn)
    await conn.execute("INSERT INTO agents (name) VALUES ('a')")
    await conn.execute("INSERT INTO agents (name) VALUES ('b')")
    await conn.execute("DROP TABLE agent_routine_proposals")
    await conn.execute("DROP TABLE agent_routine_runs")
    await conn.execute("DROP TABLE agent_routines")
    await conn.execute(_V48_ROUTINES_DDL)
    await conn.execute(
        "CREATE INDEX idx_agent_routines_due ON agent_routines (enabled, next_run_at)"
    )
    await conn.execute(_V48_RUNS_DDL)
    await conn.execute(
        "CREATE INDEX idx_agent_routine_runs_routine "
        "ON agent_routine_runs (routine_id, started_at DESC)"
    )
    await conn.execute(
        "CREATE TABLE agent_routine_proposals ("
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
        "CREATE INDEX idx_agent_routine_proposals_agent_status "
        "ON agent_routine_proposals (agent_name, status)"
    )
    await conn.execute("DELETE FROM schema_version WHERE version >= 49")
    await conn.commit()
    return conn


async def _v48_routine(conn, rid, agent="a", name=None, **over) -> None:
    vals = {
        "id": rid,
        "agent_name": agent,
        "name": name or rid,
        "prompt": f"prompt {rid}",
        "schedule": json.dumps({"start": {"date": "2026-10-11", "time": "09:00"}}),
        "enabled": 1,
        "finished_at": None,
        "target_kind": "chat",
        "target_session_id": "sess-1",
        "target_platform": "stub",
        "target_connector_id": "c1",
        "target_channel_id": "ch1",
        "target_thread_id": "th1",
        "target_peer_id": "p1",
        "next_run_at": "2026-10-11T16:00:00+00:00",
        "anchor_at": "2026-10-11T16:00:00+00:00",
        "created_by": "agent",
        "created_at": "2026-10-01T00:00:00+00:00",
        "updated_at": "2026-10-02T00:00:00+00:00",
        "untrusted": 1,
        "untrusted_sources": '["web_fetch"]',
        **over,
    }
    await conn.execute(
        f"INSERT INTO agent_routines ({', '.join(vals)}) VALUES ({', '.join('?' for _ in vals)})",
        tuple(vals.values()),
    )


async def _v48_proposal(conn, pid, *, action, status, payload, base, routine_id=None) -> None:
    await conn.execute(
        "INSERT INTO agent_routine_proposals (id, agent_name, routine_id, routine_name, action, "
        "payload, base, status, created_at, resolved_at) "
        "VALUES (?, 'a', ?, 'n', ?, ?, ?, ?, '2026-10-01T00:00:00+00:00', ?)",
        (
            pid,
            routine_id,
            action,
            payload if isinstance(payload, str) else json.dumps(payload),
            base if base is None or isinstance(base, str) else json.dumps(base),
            status,
            "2026-10-02T00:00:00+00:00" if status in ("applied", "dismissed") else None,
        ),
    )


async def _proposal_row(conn, pid):
    async with conn.execute(
        "SELECT payload, base, status, resolved_at FROM agent_routine_proposals WHERE id = ?",
        (pid,),
    ) as cur:
        return await cur.fetchone()


class TestSchemaV49:
    async def test_current_version_is_at_least_49(self) -> None:
        assert CURRENT_VERSION >= 49

    async def test_target_columns_and_new_chat_are_dropped_and_the_rest_kept(
        self, tmp_path
    ) -> None:
        conn = await _v48_db(tmp_path / "v48.db")
        await _v48_routine(conn, "r1")
        await _v48_routine(conn, "r2", name="Other", target_kind="own", target_session_id=None)
        await _insert_run(conn, "u1", "r1", session_id="sess-1", new_chat=1, repeats=3)
        await _insert_run(conn, "u2", "r2", reason_code="still_running", reason="why")
        await conn.commit()
        async with conn.execute("SELECT * FROM agent_routines ORDER BY id") as cur:
            before = [dict(r) for r in await cur.fetchall()]
        await ensure_schema(conn)
        async with conn.execute("PRAGMA table_info(agent_routines)") as cur:
            assert [r["name"] for r in await cur.fetchall()] == _ROUTINE_COLS
        async with conn.execute("PRAGMA table_info(agent_routine_runs)") as cur:
            assert [r["name"] for r in await cur.fetchall()] == _RUN_COLS
        async with conn.execute("SELECT * FROM agent_routines ORDER BY id") as cur:
            after = [dict(r) for r in await cur.fetchall()]
        for old, new in zip(before, after, strict=True):
            assert new == {k: v for k, v in old.items() if k not in _V49_TARGET_COLS}
        async with conn.execute("SELECT * FROM agent_routine_runs ORDER BY id") as cur:
            runs = [dict(r) for r in await cur.fetchall()]
        assert [(r["id"], r["session_id"], r["repeats"], r["reason_code"]) for r in runs] == [
            ("u1", "sess-1", 3, None),
            ("u2", None, 1, "still_running"),
        ]
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == 52
        await conn.close()

    async def test_indexes_unique_checks_and_foreign_keys_survive(self, tmp_path) -> None:
        conn = await _v48_db(tmp_path / "idx.db")
        await _v48_routine(conn, "r1", name="Daily")
        await conn.commit()
        await ensure_schema(conn)
        async with conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'") as cur:
            names = {r["name"] for r in await cur.fetchall()}
        assert {
            "idx_agent_routines_due",
            "idx_agent_routine_runs_routine",
            "idx_agent_routine_proposals_agent_status",
        } <= names
        # the UNIQUE (agent_name, name NOCASE) and the created_by CHECK still bite
        with pytest.raises(aiosqlite.IntegrityError):
            await _insert_routine(conn, "r2", "a", "daily")
        await _insert_routine(conn, "r3", "b", "daily")
        with pytest.raises(aiosqlite.IntegrityError):
            await _insert_routine(conn, "r4", "a", "x", created_by="robot")
        async with conn.execute("PRAGMA foreign_key_check") as cur:
            assert await cur.fetchall() == []
        fk = (await _fk_rows(conn, "agent_routines"))["agent_name"]
        assert (fk["table"], fk["on_update"], fk["on_delete"]) == ("agents", "CASCADE", "CASCADE")
        await conn.close()

    async def test_deleting_a_routine_still_cascades_runs_and_nulls_proposals(
        self, tmp_path
    ) -> None:
        conn = await _v48_db(tmp_path / "fk.db")
        await _v48_routine(conn, "r1")
        await _insert_run(conn, "u1", "r1")
        await _v48_proposal(
            conn, "p1", action="update", status="applied", payload={"prompt": "x"}, base={},
            routine_id="r1",
        )  # fmt: skip
        await conn.commit()
        await ensure_schema(conn)
        fks = await _fk_rows(conn, "agent_routine_runs")
        assert fks["routine_id"]["on_delete"] == "CASCADE"
        fks = await _fk_rows(conn, "agent_routine_proposals")
        assert fks["routine_id"]["on_delete"] == "SET NULL"
        await conn.execute("DELETE FROM agent_routines WHERE id = 'r1'")
        await conn.commit()
        async with conn.execute("SELECT COUNT(*) FROM agent_routine_runs") as cur:
            assert (await cur.fetchone())[0] == 0
        async with conn.execute("SELECT routine_id FROM agent_routine_proposals") as cur:
            assert [r[0] for r in await cur.fetchall()] == [None]
        async with conn.execute("PRAGMA foreign_key_check") as cur:
            assert await cur.fetchall() == []
        await conn.close()

    async def test_proposals_lose_their_target(self, tmp_path) -> None:
        conn = await _v48_db(tmp_path / "prop.db")
        await _v48_routine(conn, "r1")
        base = {
            "name": "n", "prompt": "p", "schedule": {}, "anchor_at": None, "enabled": True,
            "finished_at": None, "target_kind": "chat", "target_session_id": "sess-1",
        }  # fmt: skip
        tgt = {"kind": "chat", "session_id": "sess-1"}
        await _v48_proposal(  # a pending create that carried a target: still approvable
            conn, "create", action="create", status="pending",
            payload={"name": "n", "prompt": "p", "schedule": {}, "target": tgt, "enabled": True},
            base=None,
        )  # fmt: skip
        await _v48_proposal(  # a pending update that only changed the target
            conn, "only", action="update", status="pending", payload={"target": tgt},
            base=base, routine_id="r1",
        )  # fmt: skip
        await _v48_proposal(  # a pending update that also changed the prompt
            conn, "mixed", action="update", status="pending",
            payload={"prompt": "new", "target": {"kind": "new"}}, base=base, routine_id="r1",
        )  # fmt: skip
        await _v48_proposal(  # applied history is stripped but keeps its status and time
            conn, "done", action="update", status="applied",
            payload={"name": "z", "target": {"kind": "own"}}, base=base, routine_id="r1",
        )  # fmt: skip
        await _v48_proposal(  # a pending delete: no target in its payload, base is stripped
            conn, "del", action="delete", status="pending", payload={}, base=base,
            routine_id="r1",
        )  # fmt: skip
        await _v48_proposal(  # unreadable JSON is left exactly as it is
            conn, "junk", action="update", status="pending", payload="{not json", base="also bad",
            routine_id="r1",
        )  # fmt: skip
        await conn.commit()
        await ensure_schema(conn)

        row = await _proposal_row(conn, "create")
        assert json.loads(row["payload"]) == {
            "name": "n", "prompt": "p", "schedule": {}, "enabled": True,
        }  # fmt: skip
        assert row["status"] == "pending"

        row = await _proposal_row(conn, "only")
        assert json.loads(row["payload"]) == {}
        assert row["status"] == "superseded" and row["resolved_at"]
        assert "target_kind" not in json.loads(row["base"])

        row = await _proposal_row(conn, "mixed")
        assert json.loads(row["payload"]) == {"prompt": "new"}
        assert row["status"] == "pending" and row["resolved_at"] is None
        stripped = json.loads(row["base"])
        assert "target_kind" not in stripped and "target_session_id" not in stripped
        assert stripped["name"] == "n" and stripped["prompt"] == "p"

        row = await _proposal_row(conn, "done")
        assert json.loads(row["payload"]) == {"name": "z"}
        assert row["status"] == "applied" and row["resolved_at"] == "2026-10-02T00:00:00+00:00"

        row = await _proposal_row(conn, "del")
        assert json.loads(row["payload"]) == {} and row["status"] == "pending"
        assert "target_kind" not in json.loads(row["base"])

        row = await _proposal_row(conn, "junk")
        assert (row["payload"], row["base"], row["status"]) == (
            "{not json", "also bad", "pending",
        )  # fmt: skip
        await conn.close()

    async def test_rerunning_the_migration_changes_nothing(self, tmp_path) -> None:
        conn = await _v48_db(tmp_path / "idem49.db")
        await _v48_routine(conn, "r1")
        await _v48_proposal(
            conn, "only", action="update", status="pending",
            payload={"target": {"kind": "new"}}, base={"target_kind": "new", "name": "n"},
            routine_id="r1",
        )  # fmt: skip
        await conn.commit()
        await ensure_schema(conn)
        first = [
            tuple(r) for r in await (await conn.execute("SELECT * FROM agent_routines")).fetchall()
        ]
        first_p = tuple(await _proposal_row(conn, "only"))
        await conn.execute("DELETE FROM schema_version WHERE version >= 49")
        await conn.commit()
        await ensure_schema(conn)  # the guards find nothing left to drop or rewrite
        again = [
            tuple(r) for r in await (await conn.execute("SELECT * FROM agent_routines")).fetchall()
        ]
        assert again == first and tuple(await _proposal_row(conn, "only")) == first_p
        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 49") as cur:
            assert (await cur.fetchone())[0] == 1
        await conn.close()


class TestSchemaV50:
    """Sortie 09 DD5: the per-agent MCP tool cache table."""

    async def _seed(self, conn) -> None:
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        await conn.execute("INSERT INTO mcp_sources (id, name, type) VALUES ('s1', 'S', 'stdio')")
        await conn.execute(
            "INSERT INTO agent_mcp_tool_cache (agent_name, source_id, tools, fetched_at) "
            "VALUES ('a', 's1', '[]', 'now')"
        )
        await conn.commit()

    async def test_fresh_replay_has_the_table_and_shape(self, tmp_path) -> None:
        conn = await _open(tmp_path / "fresh50.db")
        await ensure_schema(conn)
        assert CURRENT_VERSION >= 50
        async with conn.execute("PRAGMA table_info(agent_mcp_tool_cache)") as cur:
            rows = await cur.fetchall()
        assert [r["name"] for r in rows] == ["agent_name", "source_id", "tools", "fetched_at"]
        assert {r["name"] for r in rows if r["pk"]} == {"agent_name", "source_id"}
        fks = await _fk_rows(conn, "agent_mcp_tool_cache")
        assert (fks["agent_name"]["table"], fks["agent_name"]["on_update"]) == (
            "agents",
            "CASCADE",
        )
        assert fks["agent_name"]["on_delete"] == "CASCADE"
        assert (fks["source_id"]["table"], fks["source_id"]["on_delete"]) == (
            "mcp_sources",
            "CASCADE",
        )
        await conn.close()

    async def test_rewound_to_v49_reruns_idempotently(self, tmp_path) -> None:
        conn = await _open(tmp_path / "v49.db")
        await ensure_schema(conn)
        await self._seed(conn)
        await conn.execute("DELETE FROM schema_version WHERE version >= 50")
        await conn.commit()
        await ensure_schema(conn)
        await ensure_schema(conn)
        async with conn.execute("SELECT COUNT(*) FROM agent_mcp_tool_cache") as cur:
            assert (await cur.fetchone())[0] == 1
        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 50") as cur:
            assert (await cur.fetchone())[0] == 1
        await conn.close()

    async def test_rename_moves_rows_and_deletes_cascade(self, tmp_path) -> None:
        conn = await _open(tmp_path / "fk50.db")
        await ensure_schema(conn)
        await self._seed(conn)
        await conn.execute("UPDATE agents SET name = 'b' WHERE name = 'a'")
        await conn.commit()
        async with conn.execute("SELECT agent_name FROM agent_mcp_tool_cache") as cur:
            assert [r[0] for r in await cur.fetchall()] == ["b"]
        await conn.execute("DELETE FROM mcp_sources WHERE id = 's1'")
        await conn.commit()
        async with conn.execute("SELECT COUNT(*) FROM agent_mcp_tool_cache") as cur:
            assert (await cur.fetchone())[0] == 0
        await conn.execute("INSERT INTO mcp_sources (id, name, type) VALUES ('s2', 'T', 'stdio')")
        await conn.execute(
            "INSERT INTO agent_mcp_tool_cache (agent_name, source_id, tools, fetched_at) "
            "VALUES ('b', 's2', '[]', 'now')"
        )
        await conn.commit()
        await conn.execute("DELETE FROM agents WHERE name = 'b'")
        await conn.commit()
        async with conn.execute("SELECT COUNT(*) FROM agent_mcp_tool_cache") as cur:
            assert (await cur.fetchone())[0] == 0
        await conn.close()


class TestSchemaV51:
    """Sortie 10 DD4: secrets, secret_values and agents.secret_ids."""

    async def test_fresh_replay_has_the_tables_and_column(self, tmp_path) -> None:
        conn = await _open(tmp_path / "fresh51.db")
        await ensure_schema(conn)
        assert CURRENT_VERSION >= 51
        async with conn.execute("PRAGMA table_info(secrets)") as cur:
            rows = await cur.fetchall()
        assert [r["name"] for r in rows] == [
            "id",
            "name",
            "description",
            "allowed_tools",
            "created_at",
            "updated_at",
        ]
        async with conn.execute("PRAGMA table_info(secret_values)") as cur:
            rows = await cur.fetchall()
        assert [r["name"] for r in rows] == ["id", "secret_id", "key", "value", "position"]
        fks = await _fk_rows(conn, "secret_values")
        assert (fks["secret_id"]["table"], fks["secret_id"]["on_delete"]) == (
            "secrets",
            "CASCADE",
        )
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        assert cols["secret_ids"]["notnull"] == 1
        assert cols["secret_ids"]["dflt_value"] == "'[]'"
        await conn.close()

    async def test_names_and_keys_are_unique_ignoring_case(self, tmp_path) -> None:
        conn = await _open(tmp_path / "nocase51.db")
        await ensure_schema(conn)
        await conn.execute(
            "INSERT INTO secrets (id, name, created_at, updated_at) VALUES ('1', 'Home', 'n', 'n')"
        )
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO secrets (id, name, created_at, updated_at) "
                "VALUES ('2', 'home', 'n', 'n')"
            )
        await conn.execute(
            "INSERT INTO secret_values (id, secret_id, key, value, position) "
            "VALUES ('a', '1', 'Key', 'x', 0)"
        )
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO secret_values (id, secret_id, key, value, position) "
                "VALUES ('b', '1', 'KEY', 'x', 1)"
            )
        await conn.close()

    async def test_v50_agents_migrate_with_empty_secret_ids(self, tmp_path) -> None:
        conn = await _open(tmp_path / "v50.db")
        await ensure_schema(conn)
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        await conn.execute("DROP TABLE secret_values")
        await conn.execute("DROP TABLE secrets")
        await conn.execute("ALTER TABLE agents DROP COLUMN secret_ids")
        await conn.execute("DELETE FROM schema_version WHERE version >= 51")
        await conn.commit()
        await ensure_schema(conn)
        await ensure_schema(conn)
        async with conn.execute("SELECT secret_ids FROM agents WHERE name = 'a'") as cur:
            assert (await cur.fetchone())[0] == "[]"
        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 51") as cur:
            assert (await cur.fetchone())[0] == 1
        await conn.close()


class TestSchemaV52:
    """M35 F1 DD11: agents.rich_visuals, on for every agent."""

    async def test_fresh_replay_has_the_column(self, tmp_path) -> None:
        conn = await _open(tmp_path / "fresh52.db")
        await ensure_schema(conn)
        assert CURRENT_VERSION == 52
        async with conn.execute("PRAGMA table_info(agents)") as cur:
            cols = {r["name"]: r for r in await cur.fetchall()}
        assert cols["rich_visuals"]["notnull"] == 1
        assert cols["rich_visuals"]["dflt_value"] == "1"
        await conn.close()

    async def test_v51_agents_migrate_on_and_replay_is_a_no_op(self, tmp_path) -> None:
        conn = await _open(tmp_path / "v51.db")
        await ensure_schema(conn)
        await conn.execute("INSERT INTO agents (name) VALUES ('a')")
        await conn.execute("INSERT INTO agents (name) VALUES ('b')")
        await conn.execute("ALTER TABLE agents DROP COLUMN rich_visuals")
        await conn.execute("DELETE FROM schema_version WHERE version >= 52")
        await conn.commit()
        await ensure_schema(conn)
        await ensure_schema(conn)
        async with conn.execute("SELECT name, rich_visuals FROM agents ORDER BY name") as cur:
            assert [(r[0], r[1]) for r in await cur.fetchall()] == [("a", 1), ("b", 1)]
        async with conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 52") as cur:
            assert (await cur.fetchone())[0] == 1
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            assert (await cur.fetchone())[0] == 52
        await conn.close()
