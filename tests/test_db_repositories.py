"""Tests for all database repositories."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from the_one.agent.config import AgentConfig
from the_one.db.models import ChatSession, Connector, KBItem, KnowledgeBase, MCPSource
from the_one.db.repositories import (
    AgentRevisionRepository,
    AppMetadataRepository,
    ChatSessionRepository,
    ConnectorRepository,
    KBItemRepository,
    KnowledgeBaseRepository,
    MCPSourceRepository,
    PendingApprovalRepository,
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
def agent_store_encryptor(tmp_path):
    # Function-scoped (default). Do NOT promote to module/session scope —
    # would outlive the per-test `conn` fixture and create cross-test
    # state leakage on the encryptor's in-memory key. Mirrors
    # `mcp_repo_encryptor` / `connector_repo_encryptor` / `tool_config_repo_encryptor`.
    from cryptography.fernet import Fernet

    from the_one.encryption import Encryptor

    key = Fernet.generate_key()
    return Encryptor(key, key_path=tmp_path / "agent_store.key")


@pytest.fixture
def agent_store(conn, agent_store_encryptor):
    return SQLiteAgentStore(conn, agent_store_encryptor)


@pytest.fixture
def app_metadata_repo(conn):
    return AppMetadataRepository(conn)


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
    return ConnectorRepository(conn, connector_repo_encryptor)


@pytest.fixture
def chat_repo(conn):
    return ChatSessionRepository(conn)


@pytest.fixture
def tool_config_repo_encryptor(tmp_path):
    # Function-scoped (default). Do NOT promote to module/session scope —
    # would outlive the per-test `conn` fixture and create cross-test
    # state leakage on the encryptor's in-memory key.
    from cryptography.fernet import Fernet

    from the_one.encryption import Encryptor

    key = Fernet.generate_key()
    return Encryptor(key, key_path=tmp_path / "tool_config.key")


@pytest.fixture
def tool_config_repo(conn, tool_config_repo_encryptor):
    return ToolConfigRepository(conn, tool_config_repo_encryptor)


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

    async def test_self_revision_requires_approval_defaults_false(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        # M21 F02 L02 AC2 — default False round-trips (v35 backfill = 0).
        await agent_store.save(AgentConfig(name="default-approval"))
        loaded = await agent_store.load("default-approval")
        assert loaded.self_revision_requires_approval is False

    async def test_self_revision_requires_approval_round_trip_true(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        # M21 F02 L02 AC2 — True round-trips through all four save edit sites
        # + the plain _row_to_config read.
        cfg = AgentConfig(name="approval-on", self_revision_requires_approval=True)
        await agent_store.save(cfg)
        loaded = await agent_store.load("approval-on")
        assert loaded.self_revision_requires_approval is True
        # Flip back off via a full save (ON CONFLICT SET path).
        await agent_store.save(
            AgentConfig(name="approval-on", self_revision_requires_approval=False)
        )
        assert (await agent_store.load("approval-on")).self_revision_requires_approval is False

    async def test_set_self_revision_requires_approval_targeted_update(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        # M21 F02 L02 — the targeted UPDATE toggles only the flag, leaving
        # other fields untouched.
        await agent_store.save(AgentConfig(name="toggle", description="keep me"))
        await agent_store.set_self_revision_requires_approval("toggle", True)
        loaded = await agent_store.load("toggle")
        assert loaded.self_revision_requires_approval is True
        assert loaded.description == "keep me"
        await agent_store.set_self_revision_requires_approval("toggle", False)
        assert (await agent_store.load("toggle")).self_revision_requires_approval is False

    async def test_set_self_revision_requires_approval_missing_agent_raises(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        with pytest.raises(KeyError):
            await agent_store.set_self_revision_requires_approval("ghost", True)

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

    # ── M21 F01 L01: encryption-at-rest for the override columns ────────

    async def test_tool_overrides_and_mcp_overrides_stored_as_ciphertext(
        self, agent_store: SQLiteAgentStore, agent_store_encryptor, conn
    ) -> None:
        """AC1 — after save(), the raw columns are NOT valid JSON and DO
        decrypt under the store's encryptor to the original dicts."""
        cfg = AgentConfig(
            name="ciphertext-test",
            tool_overrides={"shell": {"timeout": 30}},
            mcp_overrides={"github": {"bearer_token": "tok-a"}},
        )
        await agent_store.save(cfg)

        async with conn.execute(
            "SELECT tool_overrides, mcp_overrides FROM agents WHERE name = ?",
            ("ciphertext-test",),
        ) as cur:
            row = await cur.fetchone()

        raw_tool = row["tool_overrides"]
        raw_mcp = row["mcp_overrides"]
        # Not valid JSON — proves it's ciphertext, not a plaintext blob.
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw_tool)
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw_mcp)
        # Decrypts under the store's own encryptor to the original dicts.
        assert json.loads(agent_store_encryptor.decrypt(raw_tool)) == {"shell": {"timeout": 30}}
        assert json.loads(agent_store_encryptor.decrypt(raw_mcp)) == {
            "github": {"bearer_token": "tok-a"}
        }

    async def test_none_stored_as_sql_null_not_encrypted(
        self, agent_store: SQLiteAgentStore, conn
    ) -> None:
        """AC1 — `None` is stored as SQL NULL, not an encrypted `null`."""
        cfg = AgentConfig(name="null-test")
        await agent_store.save(cfg)
        async with conn.execute(
            "SELECT tool_overrides, mcp_overrides FROM agents WHERE name = ?",
            ("null-test",),
        ) as cur:
            row = await cur.fetchone()
        assert row["tool_overrides"] is None
        assert row["mcp_overrides"] is None

    async def test_empty_dict_stored_encrypted_and_loads_as_empty_dict(
        self, agent_store: SQLiteAgentStore, agent_store_encryptor, conn
    ) -> None:
        """AC1 — `{}` IS encrypted (not treated as "empty, store NULL"),
        and decodes back to `{}`, preserving the None/`{}` distinction."""
        cfg = AgentConfig(name="empty-dict-test", tool_overrides={}, mcp_overrides={})
        await agent_store.save(cfg)

        async with conn.execute(
            "SELECT tool_overrides, mcp_overrides FROM agents WHERE name = ?",
            ("empty-dict-test",),
        ) as cur:
            row = await cur.fetchone()
        assert row["tool_overrides"] is not None
        assert json.loads(agent_store_encryptor.decrypt(row["tool_overrides"])) == {}
        assert json.loads(agent_store_encryptor.decrypt(row["mcp_overrides"])) == {}

        loaded = await agent_store.load("empty-dict-test")
        assert loaded.tool_overrides == {}
        assert loaded.mcp_overrides == {}

    async def test_legacy_plaintext_row_loads_and_next_save_rewrites_ciphertext(
        self, agent_store: SQLiteAgentStore, agent_store_encryptor, conn
    ) -> None:
        """AC2 — a row whose column holds plaintext JSON (pre-leg data)
        loads with its values intact via the tolerant decode, and the
        NEXT save() rewrites that column as ciphertext."""
        from the_one.db.models import now_iso

        now = now_iso()
        await conn.execute(
            "INSERT INTO agents (name, description, llm_model, system_prompt,"
            " disabled_tools, max_iterations, kb_ids, mcp_source_ids,"
            " connector_ids, tool_overrides, mcp_overrides, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-agent",
                "",
                "mock-default",
                "",
                "[]",
                20,
                "[]",
                "[]",
                "[]",
                json.dumps({"shell": {"timeout": 30}}),  # legacy plaintext
                json.dumps({"github": {"bearer_token": "legacy-tok"}}),  # legacy plaintext
                now,
                now,
            ),
        )
        await conn.commit()

        loaded = await agent_store.load("legacy-agent")
        assert loaded.tool_overrides == {"shell": {"timeout": 30}}
        assert loaded.mcp_overrides == {"github": {"bearer_token": "legacy-tok"}}

        # Next save() rewrites the columns as ciphertext.
        await agent_store.save(loaded)
        async with conn.execute(
            "SELECT tool_overrides, mcp_overrides FROM agents WHERE name = ?",
            ("legacy-agent",),
        ) as cur:
            row = await cur.fetchone()
        with pytest.raises(json.JSONDecodeError):
            json.loads(row["tool_overrides"])
        with pytest.raises(json.JSONDecodeError):
            json.loads(row["mcp_overrides"])
        assert json.loads(agent_store_encryptor.decrypt(row["tool_overrides"])) == {
            "shell": {"timeout": 30}
        }

    async def test_legacy_row_with_exactly_empty_json_object_loads_as_empty_dict(
        self, agent_store: SQLiteAgentStore, conn
    ) -> None:
        """Edge case: a legacy row holding exactly `"{}"` loads as `{}`,
        not `None`."""
        from the_one.db.models import now_iso

        now = now_iso()
        await conn.execute(
            "INSERT INTO agents (name, description, llm_model, system_prompt,"
            " disabled_tools, max_iterations, kb_ids, mcp_source_ids,"
            " connector_ids, tool_overrides, mcp_overrides, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-empty",
                "",
                "mock-default",
                "",
                "[]",
                20,
                "[]",
                "[]",
                "[]",
                "{}",
                "{}",
                now,
                now,
            ),
        )
        await conn.commit()

        loaded = await agent_store.load("legacy-empty")
        assert loaded.tool_overrides == {}
        assert loaded.mcp_overrides == {}

    async def test_legacy_row_with_non_json_plaintext_raises(
        self, agent_store: SQLiteAgentStore, conn
    ) -> None:
        """Edge case: ciphertext-shaped-but-undecryptable text that is
        ALSO not valid JSON raises — corruption is not masked, matching
        `_decrypt_secrets_blob`'s stance on `_decrypt_secrets_blob`-
        governed columns."""
        from the_one.db.models import now_iso

        now = now_iso()
        await conn.execute(
            "INSERT INTO agents (name, description, llm_model, system_prompt,"
            " disabled_tools, max_iterations, kb_ids, mcp_source_ids,"
            " connector_ids, tool_overrides, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "corrupt-agent",
                "",
                "mock-default",
                "",
                "[]",
                20,
                "[]",
                "[]",
                "[]",
                "not valid json at all",
                now,
                now,
            ),
        )
        await conn.commit()

        with pytest.raises(json.JSONDecodeError):
            await agent_store.load("corrupt-agent")

    async def test_empty_string_column_decodes_to_none(
        self, agent_store: SQLiteAgentStore, conn
    ) -> None:
        """Edge case: an empty-string column decodes to `None` (matches
        the pre-leg truthiness decode)."""
        from the_one.db.models import now_iso

        now = now_iso()
        await conn.execute(
            "INSERT INTO agents (name, description, llm_model, system_prompt,"
            " disabled_tools, max_iterations, kb_ids, mcp_source_ids,"
            " connector_ids, tool_overrides, mcp_overrides, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "empty-string-agent",
                "",
                "mock-default",
                "",
                "[]",
                20,
                "[]",
                "[]",
                "[]",
                "",
                "",
                now,
                now,
            ),
        )
        await conn.commit()

        loaded = await agent_store.load("empty-string-agent")
        assert loaded.tool_overrides is None
        assert loaded.mcp_overrides is None

    async def test_constructor_default_encryptor_still_works(self, conn) -> None:
        """AC7 — `SQLiteAgentStore(conn)` with no encryptor argument still
        works (resolves via `get_encryptor(settings.data_dir)`). The test
        run isolates `THE_ONE_DATA_DIR` to a temp dir (conftest.py), so
        this never touches the operator's real key file."""
        store = SQLiteAgentStore(conn)
        cfg = AgentConfig(name="default-encryptor-test", tool_overrides={"shell": {"timeout": 1}})
        await store.save(cfg)
        loaded = await store.load("default-encryptor-test")
        assert loaded.tool_overrides == {"shell": {"timeout": 1}}

    async def test_save_round_trips_connector_ids(self, agent_store: SQLiteAgentStore) -> None:
        """Saving an agent with ``connector_ids`` set roundtrips
        through the SQLite store (M10 F4 L5 v17 migration).

        Closes the F4 L4 leg-4 monkeypatch workaround: the field is now
        persisted to the new ``agents.connector_ids`` column
        (JSON-encoded list, TEXT). ``_row_to_config`` decodes via
        ``json.loads(row["connector_ids"] or "[]")``.
        """
        cfg = AgentConfig(
            name="connector-attached-agent",
            connector_ids=["acct-a", "acct-b"],
        )
        await agent_store.save(cfg)
        loaded = await agent_store.load("connector-attached-agent")
        assert loaded.connector_ids == ["acct-a", "acct-b"]

        # Upsert path: re-save with a different list. Confirms the
        # ON CONFLICT(name) DO UPDATE SET branch writes the new value
        # (a missing connector_ids in the update list would
        # silently retain the original value).
        cfg2 = AgentConfig(
            name="connector-attached-agent",
            connector_ids=["acct-c"],
        )
        await agent_store.save(cfg2)
        loaded2 = await agent_store.load("connector-attached-agent")
        assert loaded2.connector_ids == ["acct-c"]

    async def test_load_pre_v17_agent_has_empty_connector_ids(
        self, agent_store: SQLiteAgentStore, conn
    ) -> None:
        """A row written with the new column explicitly set to NULL (the
        pre-v17 row state after the v17 ALTER fires) decodes as an empty
        list via the ``or "[]"`` default in ``_row_to_config``.

        Back-compat anchor for production DBs upgraded from v16: the
        column exists post-migration but holds NULL until the next save.
        """
        # Hand-write a row with connector_ids = NULL — simulates
        # the post-migration state of a pre-v17 row before the next save.
        from the_one.db.models import now_iso

        now = now_iso()
        await conn.execute(
            "INSERT INTO agents (name, description, llm_model, system_prompt,"
            " disabled_tools, max_iterations, kb_ids, mcp_source_ids,"
            " connector_ids, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "pre-v17-agent",
                "",
                "mock-default",
                "",
                "[]",
                20,
                "[]",
                "[]",
                None,  # connector_ids NULL — simulates pre-v17 row
                now,
                now,
            ),
        )
        await conn.commit()

        loaded = await agent_store.load("pre-v17-agent")
        assert loaded.connector_ids == []

    async def test_save_round_trips_connector_acls(self, agent_store: SQLiteAgentStore) -> None:
        """Saving an agent with ``connector_acls`` set roundtrips through
        ``save`` and ``load``. Mirror of
        ``test_save_round_trips_connector_ids`` for the F6 L1c
        per-agent ACL field (M10 F6 L1c v18 migration).
        """
        # M11 F12 L3 — per-agent peers/channels use the structured-
        # tuple shape mirroring account-scope.
        config = AgentConfig(
            name="acl-agent",
            connector_acls={
                "acct-a": {
                    "peers": [
                        {"id": "u1"},
                        {"id": "u2"},
                    ],
                    "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
                },
                "acct-b": {"peers": [], "channels": []},
            },
        )
        await agent_store.save(config)
        loaded = await agent_store.load("acl-agent")
        assert loaded.connector_acls == {
            "acct-a": {
                "peers": [
                    {"id": "u1"},
                    {"id": "u2"},
                ],
                "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
            },
            "acct-b": {"peers": [], "channels": []},
        }

        # Upsert path: re-save with a different ACL. Confirms the
        # ON CONFLICT(name) DO UPDATE SET branch writes the new value
        # (a missing connector_acls in the update list would silently
        # retain the original value).
        cfg2 = AgentConfig(
            name="acl-agent",
            connector_acls={
                "acct-c": {
                    "peers": [{"id": "u9"}],
                    "channels": [],
                }
            },
        )
        await agent_store.save(cfg2)
        loaded2 = await agent_store.load("acl-agent")
        assert loaded2.connector_acls == {
            "acct-c": {
                "peers": [{"id": "u9"}],
                "channels": [],
            },
        }

    async def test_save_round_trips_connector_acls_none(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        """An agent without ``connector_acls`` set roundtrips as None
        (locked-down NULL semantic; default for agents without per-agent
        narrowing). Mirrors the ``tool_overrides`` / ``mcp_overrides``
        None-default test pattern.
        """
        cfg = AgentConfig(name="no-acls-agent", connector_acls=None)
        await agent_store.save(cfg)
        loaded = await agent_store.load("no-acls-agent")
        assert loaded.connector_acls is None

    async def test_save_round_trips_empty_outer_dict_connector_acls(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        """Saving an agent with an empty outer dict ``connector_acls={}``
        roundtrips verbatim — NOT collapsed to ``None``.

        Distinguishes the JSON-literal ``"{}"`` truthy-string path from
        the SQL-NULL falsy path in ``_row_to_config``'s
        ``if row["connector_acls"] else None`` decode: ``"{}"`` is a
        truthy non-empty string, so ``json.loads`` runs and returns
        ``{}``; SQL NULL deserializes as Python None, which is falsy and
        triggers the ``else None`` branch. See leg-1c Edge Cases.
        """
        cfg = AgentConfig(name="empty-acls-agent", connector_acls={})
        await agent_store.save(cfg)
        loaded = await agent_store.load("empty-acls-agent")
        assert loaded.connector_acls == {}
        # Belt-and-braces: confirm the round-trip preserved {}, not None.
        assert loaded.connector_acls is not None

    async def test_save_round_trips_connector_acls_with_admit_dms(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        """M11 F10 L1 — an agent with ``connector_acls[acct].admit_dms
        = False`` survives save → load round-trip. Pins the per-agent
        DM opt-out persistence.
        """
        config = AgentConfig(
            name="admit-dms-agent",
            connector_acls={
                "acct-a": {
                    "peers": None,
                    "channels": None,
                    "admit_dms": False,
                },
                "acct-b": {
                    "peers": None,
                    "channels": None,
                    "admit_dms": True,
                },
                "acct-c": {
                    "peers": None,
                    "channels": None,
                    "admit_dms": None,
                },
            },
        )
        await agent_store.save(config)
        loaded = await agent_store.load("admit-dms-agent")
        assert loaded.connector_acls == {
            "acct-a": {"peers": None, "channels": None, "admit_dms": False},
            "acct-b": {"peers": None, "channels": None, "admit_dms": True},
            "acct-c": {"peers": None, "channels": None, "admit_dms": None},
        }

    async def test_load_pre_v18_agent_has_none_connector_acls(
        self, agent_store: SQLiteAgentStore, conn
    ) -> None:
        """A row written with ``connector_acls`` explicitly NULL (the
        pre-v18 row state after the v18 ALTER fires) decodes as ``None``
        via the ``if row["connector_acls"] else None`` decode in
        ``_row_to_config``.

        Back-compat anchor for production DBs upgraded from v17: the
        column exists post-migration but holds NULL until the next save.
        """
        from the_one.db.models import now_iso

        now = now_iso()
        await conn.execute(
            "INSERT INTO agents (name, description, llm_model, system_prompt,"
            " disabled_tools, max_iterations, kb_ids, mcp_source_ids,"
            " connector_ids, connector_acls, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "pre-v18-agent",
                "",
                "mock-default",
                "",
                "[]",
                20,
                "[]",
                "[]",
                None,
                None,  # connector_acls NULL — simulates pre-v18 row
                now,
                now,
            ),
        )
        await conn.commit()

        loaded = await agent_store.load("pre-v18-agent")
        assert loaded.connector_acls is None

    async def test_empty_per_account_acl_round_trips_through_save_load(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        """Empty per-account ACL ``{"peers": [], "channels": []}`` survives
        the DB round-trip verbatim (does NOT collapse to an absent entry).
        Mirror of leg-1b's allowlist-round-trip discipline: explicit-empty
        is a SEMANTIC choice (L7 HAT redesign: peers = "no peer";
        channels = "DMs only", F8-deferred) and must survive the
        serialize → NULL? check → JSON load path intact.
        """
        config = AgentConfig(
            name="empty-per-acct-agent",
            connector_acls={"acct-a": {"peers": [], "channels": []}},
        )
        await agent_store.save(config)
        loaded = await agent_store.load("empty-per-acct-agent")
        assert loaded.connector_acls == {"acct-a": {"peers": [], "channels": []}}
        # Confirm the per-account entry survives (not just the outer dict).
        assert loaded.connector_acls is not None
        assert "acct-a" in loaded.connector_acls

    async def test_validator_fires_on_repo_read_path_connector_acls(
        self, agent_store: SQLiteAgentStore, conn
    ) -> None:
        """The ``_validate_connector_acls`` field validator fires when
        ``_row_to_config`` constructs ``AgentConfig(**kwargs)`` from a
        DB row whose ``connector_acls`` column holds malformed JSON
        (e.g. missing the ``"channels"`` inner key).

        Mirror of leg-1b's
        ``test_validator_fires_on_repo_read_path_account_config`` —
        confirms Pydantic v2 ``@field_validator(mode="after")`` runs on
        direct kwargs construction the same as ``model_validate``, so we
        don't need to widen ``_row_to_config`` to ``model_validate``.

        H2-closure: writes a valid row through the repo's ``save``, then
        UPDATEs the JSON column with malformed-inner-shape JSON via raw
        SQL, then calls ``load`` and asserts ``ValidationError``.
        """
        # Step 1: write a valid row via the repo.
        # M11 F12 L3 — per-agent peers use structured tuples.
        cfg = AgentConfig(
            name="validator-fires-agent",
            connector_acls={
                "acct-a": {
                    "peers": [{"id": "u1"}],
                    "channels": [],
                }
            },
        )
        await agent_store.save(cfg)

        # Step 2: UPDATE the row's connector_acls to malformed inner shape
        # (missing "channels"). Bypasses the Pydantic validator on the
        # write path — the column is raw TEXT at the SQL layer.
        import json

        malformed = json.dumps({"acct-a": {"peers": ["u1"]}})
        await conn.execute(
            "UPDATE agents SET connector_acls = ? WHERE name = ?",
            (malformed, "validator-fires-agent"),
        )
        await conn.commit()

        # Step 3: load — the validator MUST fire on _row_to_config's
        # direct kwargs construction and raise ValidationError.
        with pytest.raises(ValidationError):
            await agent_store.load("validator-fires-agent")

    # ── M11 F7 L6: connector_always_listen round-trip / back-compat ──────

    async def test_save_round_trips_connector_always_listen(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        """Saving an agent with ``connector_always_listen`` set roundtrips
        through ``save`` and ``load``. Mirror of
        ``test_save_round_trips_connector_acls`` for the F7 L6 per-agent
        always-listen toggle (M11 F7 L6 v20 migration).
        """
        config = AgentConfig(
            name="always-listen-agent",
            connector_always_listen={"acct-a": True, "acct-b": False},
        )
        await agent_store.save(config)
        loaded = await agent_store.load("always-listen-agent")
        assert loaded.connector_always_listen == {
            "acct-a": True,
            "acct-b": False,
        }

        # Upsert path: re-save with a different toggle dict. Confirms the
        # ON CONFLICT(name) DO UPDATE SET branch writes the new value
        # (a missing connector_always_listen in the update list would
        # silently retain the original value — the cycle-1 review's
        # specific bug shape).
        cfg2 = AgentConfig(
            name="always-listen-agent",
            connector_always_listen={"acct-c": True},
        )
        await agent_store.save(cfg2)
        loaded2 = await agent_store.load("always-listen-agent")
        assert loaded2.connector_always_listen == {"acct-c": True}

    async def test_save_round_trips_connector_always_listen_none(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        """An agent without ``connector_always_listen`` set roundtrips as
        None (locked-down NULL semantic; default for agents without per-
        agent overrides). Mirrors the ``connector_acls`` None-default
        round-trip test.
        """
        cfg = AgentConfig(name="no-always-listen-agent", connector_always_listen=None)
        await agent_store.save(cfg)
        loaded = await agent_store.load("no-always-listen-agent")
        assert loaded.connector_always_listen is None

    async def test_save_round_trips_empty_outer_dict_connector_always_listen(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        """Saving an agent with ``connector_always_listen={}`` roundtrips
        verbatim — NOT collapsed to ``None``.

        Distinguishes the JSON-literal ``"{}"`` truthy-string path from
        the SQL-NULL falsy path in ``_row_to_config``'s
        ``if row["connector_always_listen"] else None`` decode: ``"{}"``
        is a truthy non-empty string, so ``json.loads`` runs and returns
        ``{}``; SQL NULL deserializes as Python None, which is falsy and
        triggers the ``else None`` branch.
        """
        cfg = AgentConfig(name="empty-always-listen-agent", connector_always_listen={})
        await agent_store.save(cfg)
        loaded = await agent_store.load("empty-always-listen-agent")
        assert loaded.connector_always_listen == {}
        # Belt-and-braces: confirm the round-trip preserved {}, not None.
        assert loaded.connector_always_listen is not None

    async def test_load_pre_v20_agent_has_none_connector_always_listen(
        self, agent_store: SQLiteAgentStore, conn
    ) -> None:
        """A row written with ``connector_always_listen`` explicitly NULL
        (the pre-v20 row state after the v20 ALTER fires) decodes as
        ``None`` via the ``if row["connector_always_listen"] else None``
        decode in ``_row_to_config``.

        Back-compat anchor for production DBs upgraded from v19: the
        column exists post-migration but holds NULL until the next save.
        """
        from the_one.db.models import now_iso

        now = now_iso()
        await conn.execute(
            "INSERT INTO agents (name, description, llm_model, system_prompt,"
            " disabled_tools, max_iterations, kb_ids, mcp_source_ids,"
            " connector_ids, connector_acls,"
            " connector_always_listen, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "pre-v20-agent",
                "",
                "mock-default",
                "",
                "[]",
                20,
                "[]",
                "[]",
                None,
                None,
                None,  # connector_always_listen NULL — simulates pre-v20 row
                now,
                now,
            ),
        )
        await conn.commit()

        loaded = await agent_store.load("pre-v20-agent")
        assert loaded.connector_always_listen is None

    async def test_validator_fires_on_repo_read_path_connector_always_listen(
        self, agent_store: SQLiteAgentStore, conn
    ) -> None:
        """Pydantic's ``dict[str, bool] | None`` annotation fires on the
        read path when ``_row_to_config`` constructs ``AgentConfig(**kwargs)``
        from a DB row whose ``connector_always_listen`` column holds JSON
        whose inner values are not bool-coercible.

        Mirror of ``test_validator_fires_on_repo_read_path_connector_acls``
        — confirms Pydantic v2's field validation (annotation + custom
        validator) runs on direct kwargs construction the same as
        ``model_validate``, so we don't need to widen ``_row_to_config``
        to ``model_validate``.

        Writes a valid row via the repo's ``save``, then UPDATEs the JSON
        column with a non-bool-coercible inner value via raw SQL, then
        calls ``load`` and asserts ``ValidationError``. Uses an integer
        outside ``{0, 1}`` (Pydantic v2 strict-rejects general ints as
        bools — only ``0``/``1`` and specific bool-like strings coerce).
        """
        # Step 1: write a valid row via the repo.
        cfg = AgentConfig(
            name="al-validator-fires-agent",
            connector_always_listen={"acct-a": True},
        )
        await agent_store.save(cfg)

        # Step 2: UPDATE the row's connector_always_listen to a malformed
        # inner value (integer 42, which Pydantic v2 does NOT coerce to
        # bool). Bypasses the Pydantic validator on the write path — the
        # column is raw TEXT at the SQL layer.
        import json

        malformed = json.dumps({"acct-a": 42})
        await conn.execute(
            "UPDATE agents SET connector_always_listen = ? WHERE name = ?",
            (malformed, "al-validator-fires-agent"),
        )
        await conn.commit()

        # Step 3: load — Pydantic field validation MUST fire on
        # _row_to_config's direct kwargs construction and raise
        # ValidationError.
        with pytest.raises(ValidationError):
            await agent_store.load("al-validator-fires-agent")

    # ── M10 F7 L3: list_by_connector ─────────────────────────────

    async def test_list_by_connector_empty_for_unknown_account(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        """``list_by_connector`` returns ``[]`` for an unknown
        account id — no rows match, no error raised (M10 F7 L3).
        """
        # No agents seeded at all — empty table.
        assert await agent_store.list_by_connector("nonexistent") == []

        # Seed an agent attached to a different account — confirms
        # the filter excludes non-matching rows (rather than returning
        # all agents).
        await agent_store.save(AgentConfig(name="other", connector_ids=["acct-other"]))
        assert await agent_store.list_by_connector("nonexistent") == []

    async def test_list_by_connector_single_attached(self, agent_store: SQLiteAgentStore) -> None:
        """Seeding one agent attached to ``acct-1`` produces a single-
        element result (M10 F7 L3).
        """
        await agent_store.save(AgentConfig(name="solo", connector_ids=["acct-1"]))
        result = await agent_store.list_by_connector("acct-1")
        assert [cfg.name for cfg in result] == ["solo"]

    async def test_list_by_connector_multi_attached_alphabetical_order(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        """Three agents attached to the same account return in
        alphabetical order by name (M10 F7 L3). Pins the SQL-level
        ``ORDER BY name`` invariant.
        """
        for name in ("zebra", "alpha", "marlin"):
            await agent_store.save(AgentConfig(name=name, connector_ids=["acct-1"]))
        result = await agent_store.list_by_connector("acct-1")
        assert [cfg.name for cfg in result] == ["alpha", "marlin", "zebra"]

    async def test_list_by_connector_filters_by_account(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        """``list_by_connector`` filters rows by the requested
        account id; agents attached only to other accounts are excluded
        (M10 F7 L3).
        """
        await agent_store.save(AgentConfig(name="alice", connector_ids=["acct-1"]))
        await agent_store.save(AgentConfig(name="bob", connector_ids=["acct-2"]))
        result = await agent_store.list_by_connector("acct-1")
        assert [cfg.name for cfg in result] == ["alice"]

    async def test_list_by_connector_round_trips_full_config(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        """The returned ``AgentConfig`` carries every non-default field
        through ``_row_to_config`` byte-identically (M10 F7 L3).
        Validates that the helper does NOT degrade the full-config
        round-trip via ``_row_to_config``.
        """
        cfg = AgentConfig(
            name="full-config-agent",
            description="round-trip subject",
            llm_model="mock-default",
            system_prompt="you are a test",
            enabled_tools=["tool_a"],
            disabled_tools=["tool_b"],
            kb_ids=["kb1"],
            mcp_source_ids=["mcp1"],
            tool_overrides={"shell": {"timeout": 30}},
            connector_ids=["acct-1"],
            # M11 F13 L2 — per-agent peers are bare {"id": ...} dicts
            # (dm_allowed REJECTED at per-agent scope; channels keep
            # the structured-tuple shape).
            connector_acls={
                "acct-1": {
                    "peers": [{"id": "u1"}],
                    "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
                }
            },
        )
        await agent_store.save(cfg)
        result = await agent_store.list_by_connector("acct-1")
        assert len(result) == 1
        loaded = result[0]
        assert loaded.name == "full-config-agent"
        assert loaded.description == "round-trip subject"
        assert loaded.llm_model == "mock-default"
        assert loaded.system_prompt == "you are a test"
        assert loaded.enabled_tools == ["tool_a"]
        assert loaded.disabled_tools == ["tool_b"]
        assert loaded.kb_ids == ["kb1"]
        assert loaded.mcp_source_ids == ["mcp1"]
        assert loaded.tool_overrides == {"shell": {"timeout": 30}}
        assert loaded.connector_ids == ["acct-1"]
        assert loaded.connector_acls == {
            "acct-1": {
                "peers": [{"id": "u1"}],
                "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
            }
        }

    async def test_list_by_connector_single_agent_multi_attached(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        """One agent attached to multiple accounts appears in
        ``list_by_connector`` results for EACH attached account
        (M10 F7 L3 Edge Cases).
        """
        await agent_store.save(
            AgentConfig(
                name="multi-attached",
                connector_ids=["acct-1", "acct-2"],
            )
        )
        result_1 = await agent_store.list_by_connector("acct-1")
        result_2 = await agent_store.list_by_connector("acct-2")
        assert [cfg.name for cfg in result_1] == ["multi-attached"]
        assert [cfg.name for cfg in result_2] == ["multi-attached"]

    async def test_seed_provider_and_agent_default_attaches_to_acct_test(self, isolated_db) -> None:
        """Pinning test for M10 F7 L3 fixture-helper default change:
        bare-calling ``_seed_provider_and_agent()`` (no
        ``connector_ids`` kwarg) results in the seeded agent
        being attached to ``acct-test`` — the default account id used by
        ``_seed_stub_account`` and ``_envelope``.

        Lives here (in the canonical repository-test class) rather than
        the helper module itself so the default semantic has a stable
        regression anchor.

        Uses ``isolated_db`` (not ``conn``) because
        ``_seed_provider_and_agent`` resolves its connection via
        :func:`the_one.db.connection.get_connection` — the module-level
        singleton that ``isolated_db`` repoints at the per-test path.
        """
        from tests._connector_dispatch_helpers import _seed_provider_and_agent
        from the_one.db.connection import get_connection

        await _seed_provider_and_agent()
        conn = await get_connection()
        store = SQLiteAgentStore(conn)
        loaded = await store.load("agent-inbound")
        assert loaded.connector_ids == ["acct-test"]


# ── AgentConfig validator (direct construction) ─────────────────────────


class TestAgentConfigConnectorAclsValidator:
    """Direct-construction validator tests for ``AgentConfig.connector_acls``.

    M10 F6 L1c (semantic redesigned at L7 HAT — see flight-log
    "Deviations"). Sibling of ``TestSQLiteAgentStore``; tests the
    ``@field_validator("connector_acls", mode="after")`` invariants
    enforced at ``AgentConfig(**kwargs)`` time (no DB involved). The
    repo read-path validator-firing test is in ``TestSQLiteAgentStore``;
    these tests focus on the validator's invariants in isolation.

    Pydantic v2's ``dict[str, dict[str, list[str] | None]] | None``
    annotation enforces most invariants natively (non-string outer key,
    non-dict outer value, non-list/non-None inner value, non-string inner
    entry). The validator adds the ONE invariant the annotation cannot
    express: each inner dict must have EXACTLY the keys
    ``{"peers", "channels"}`` (no extra keys, no missing keys).

    Per-axis tri-state semantic (L7 HAT):
      - ``None`` → inherit account-scope
      - ``[]`` → explicit empty (peers: no peer; channels: DMs-only
        sentinel; outbound fails closed until F8 ships DM classification)
      - ``[items]`` → subset (intersected with account-scope)
    """

    def test_default_none_is_valid(self) -> None:
        """``connector_acls`` defaults to None (no per-agent narrowing)."""
        cfg = AgentConfig(name="agent")
        assert cfg.connector_acls is None

    def test_empty_outer_dict_is_valid(self) -> None:
        """``{}`` is valid (semantically same as None per leg-3 read rule)."""
        cfg = AgentConfig(name="agent", connector_acls={})
        assert cfg.connector_acls == {}

    def test_both_axes_none_is_valid(self) -> None:
        """``{"acct-a": {"peers": None, "channels": None}}`` is valid —
        both axes inherit account-scope (tri-state ``None``).
        """
        cfg = AgentConfig(
            name="agent",
            connector_acls={"acct-a": {"peers": None, "channels": None}},
        )
        assert cfg.connector_acls == {
            "acct-a": {"peers": None, "channels": None},
        }

    def test_empty_per_account_acl_is_valid(self) -> None:
        """``{"acct-a": {"peers": [], "channels": []}}`` is valid.

        L7 HAT semantic: explicit-empty on both axes — peers means "no
        peer permitted"; channels means "DMs-only" (F8 ships the
        classification — until then outbound fails closed).
        """
        cfg = AgentConfig(
            name="agent",
            connector_acls={"acct-a": {"peers": [], "channels": []}},
        )
        assert cfg.connector_acls == {"acct-a": {"peers": [], "channels": []}}

    def test_populated_per_account_acl_is_valid(self) -> None:
        """A populated per-account ACL with structured entries in both
        axes is valid (subset on both axes).

        M11 F13 L2 — per-agent peers are bare ``{"id": ...}`` dicts
        (``dm_allowed`` REJECTED at per-agent scope); channels keep
        the structured-tuple shape mirroring account-scope.
        """
        cfg = AgentConfig(
            name="agent",
            connector_acls={
                "acct-a": {
                    "peers": [
                        {"id": "u1"},
                        {"id": "u2"},
                    ],
                    "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
                },
            },
        )
        assert cfg.connector_acls == {
            "acct-a": {
                "peers": [
                    {"id": "u1"},
                    {"id": "u2"},
                ],
                "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
            },
        }

    def test_peers_none_channels_empty_is_valid(self) -> None:
        """Tri-state matrix: peers inherits, channels is DMs-only."""
        cfg = AgentConfig(
            name="agent",
            connector_acls={"acct-a": {"peers": None, "channels": []}},
        )
        assert cfg.connector_acls == {
            "acct-a": {"peers": None, "channels": []},
        }

    def test_peers_none_channels_subset_is_valid(self) -> None:
        """Tri-state matrix: peers inherits, channels narrows.

        M11 F12 L3 — channels uses the structured-tuple shape.
        """
        cfg = AgentConfig(
            name="agent",
            connector_acls={
                "acct-a": {
                    "peers": None,
                    "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
                }
            },
        )
        assert cfg.connector_acls == {
            "acct-a": {
                "peers": None,
                "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
            },
        }

    def test_peers_subset_channels_none_is_valid(self) -> None:
        """Tri-state matrix: peers narrows, channels inherits.

        M11 F13 L2 — per-agent peers are bare ``{"id": ...}`` dicts.
        """
        cfg = AgentConfig(
            name="agent",
            connector_acls={
                "acct-a": {
                    "peers": [{"id": "u1"}],
                    "channels": None,
                }
            },
        )
        assert cfg.connector_acls == {
            "acct-a": {
                "peers": [{"id": "u1"}],
                "channels": None,
            },
        }

    def test_peers_empty_channels_none_is_valid(self) -> None:
        """Tri-state matrix: peers explicit-empty, channels inherits."""
        cfg = AgentConfig(
            name="agent",
            connector_acls={"acct-a": {"peers": [], "channels": None}},
        )
        assert cfg.connector_acls == {
            "acct-a": {"peers": [], "channels": None},
        }

    def test_missing_channels_inner_key_raises(self) -> None:
        """Inner dict missing ``"channels"`` raises ValidationError —
        the validator enforces the exact-keys invariant. Operators must
        express per-axis intent via ``None`` vs ``[]`` vs ``[items]``,
        not by key omission.
        """
        with pytest.raises(ValidationError):
            AgentConfig(
                name="agent",
                connector_acls={"acct-a": {"peers": ["u1"]}},
            )

    def test_missing_peers_inner_key_raises(self) -> None:
        """Inner dict missing ``"peers"`` raises ValidationError."""
        with pytest.raises(ValidationError):
            AgentConfig(
                name="agent",
                connector_acls={"acct-a": {"channels": []}},
            )

    def test_extra_inner_key_raises(self) -> None:
        """Inner dict with an unexpected key raises ValidationError."""
        with pytest.raises(ValidationError):
            AgentConfig(
                name="agent",
                connector_acls={"acct-a": {"peers": [], "channels": [], "extra": []}},
            )

    def test_non_list_non_none_inner_value_raises(self) -> None:
        """Inner value that isn't a list and isn't None is rejected by
        Pydantic's annotation (``list_type`` / ``union_tag_invalid``
        error)."""
        with pytest.raises(ValidationError):
            AgentConfig(
                name="agent",
                connector_acls={"acct-a": {"peers": "not-a-list", "channels": []}},
            )

    def test_non_string_inner_entry_raises(self) -> None:
        """Non-string entry inside an inner list is rejected by Pydantic's
        annotation (``string_type`` error). Pydantic v2 does NOT coerce
        int → str under strict annotation modes for our list-of-string
        slot."""
        with pytest.raises(ValidationError):
            AgentConfig(
                name="agent",
                connector_acls={"acct-a": {"peers": [123], "channels": []}},
            )

    def test_non_dict_per_account_value_raises(self) -> None:
        """Per-account value that isn't a dict is rejected by Pydantic's
        annotation (``dict_type`` error)."""
        with pytest.raises(ValidationError):
            AgentConfig(
                name="agent",
                connector_acls={"acct-a": "not-a-dict"},
            )

    def test_non_string_outer_key_raises(self) -> None:
        """Non-string outer key is rejected by Pydantic's annotation
        (``string_type`` error). Pydantic v2 does NOT coerce int → str
        for the outer dict key under our annotation.
        """
        with pytest.raises(ValidationError):
            AgentConfig(
                name="agent",
                connector_acls={1: {"peers": [], "channels": []}},
            )

    # --- M10 F8 L8 — per-agent guilds + roles axes ---

    def test_per_agent_acl_4_axis_shape_validates(self) -> None:
        """All 4 axes (peers, channels, guilds, roles) on the per-agent
        inner dict round-trip verbatim — pins the L8 extension on the
        per-agent ACL surface.

        M11 F13 L2 — per-agent peers are bare ``{"id": ...}`` dicts
        (``dm_allowed`` REJECTED at per-agent scope); channels/roles
        use the structured-tuple shape mirroring account-scope; guilds
        stays as list[str].
        """
        cfg = AgentConfig(
            name="agent",
            connector_acls={
                "acct-a": {
                    "peers": [{"id": "u1"}],
                    "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
                    "guilds": ["g1"],
                    "roles": [{"guild_id": "g-test", "role_id": "r1"}],
                }
            },
        )
        assert cfg.connector_acls == {
            "acct-a": {
                "peers": [{"id": "u1"}],
                "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
                "guilds": ["g1"],
                "roles": [{"guild_id": "g-test", "role_id": "r1"}],
            }
        }

    def test_per_agent_acl_pre_l8_two_key_shape_still_validates(self) -> None:
        """Back-compat — pre-L8 ACL inner dicts with just
        ``{peers, channels}`` still validate (guilds + roles are
        OPTIONAL)."""
        cfg = AgentConfig(
            name="agent",
            connector_acls={"acct-a": {"peers": [], "channels": []}},
        )
        assert cfg.connector_acls == {"acct-a": {"peers": [], "channels": []}}

    def test_per_agent_acl_extra_key_outside_4_axes_raises(self) -> None:
        """Inner dict with a key outside the L8 4-axis allowed set still
        raises — extension widens to exactly
        ``{peers, channels, guilds, roles}``, no further."""
        with pytest.raises(ValidationError):
            AgentConfig(
                name="agent",
                connector_acls={
                    "acct-a": {
                        "peers": [],
                        "channels": [],
                        "guilds": [],
                        "roles": [],
                        "workspaces": [],  # not allowed
                    }
                },
            )


class TestPerAgentDmAllowedStrictRejection:
    """M11 F13 L2 — per-agent ``connector_acls[*].peers[*]`` entries
    REJECT ``dm_allowed`` post-v26 (F12 footgun retirement). The
    per-peer DM toggle is account-scope only per the F12 L3 DM
    Composition Truth Table.
    """

    def test_per_agent_peers_with_dm_allowed_key_rejected(self) -> None:
        """``AgentConfig(connector_acls={…peers carrying
        dm_allowed…})`` raises ValidationError citing the F12 footgun
        retirement.
        """
        with pytest.raises(ValidationError) as exc_info:
            AgentConfig(
                name="agent",
                connector_acls={
                    "acct-a": {
                        "peers": [{"id": "u1", "dm_allowed": True}],
                        "channels": [],
                    },
                },
            )
        msg = str(exc_info.value)
        assert "dm_allowed" in msg, msg
        assert "F12 footgun retirement" in msg or "F13 L2" in msg, msg

    def test_per_agent_peers_without_dm_allowed_key_accepted(
        self,
    ) -> None:
        """``AgentConfig(connector_acls={…peers as {id}…})``
        constructs cleanly and round-trips.
        """
        cfg = AgentConfig(
            name="agent",
            connector_acls={
                "acct-a": {
                    "peers": [{"id": "u1"}],
                    "channels": [],
                },
            },
        )
        assert cfg.connector_acls == {
            "acct-a": {"peers": [{"id": "u1"}], "channels": []},
        }


class TestAgentConfigConnectorAlwaysListenValidator:
    """Direct-construction validator tests for
    ``AgentConfig.connector_always_listen`` (M11 F7 L6).

    Sibling of ``TestAgentConfigConnectorAclsValidator``; tests the
    ``@field_validator("connector_always_listen", mode="after")``
    invariants enforced at ``AgentConfig(**kwargs)`` time (no DB
    involved). The repo read-path validator-firing test is in
    ``TestSQLiteAgentStore``; these tests focus on the validator's
    invariants in isolation.

    Pydantic v2's ``dict[str, bool] | None`` annotation enforces outer-
    key str shape and rejects non-bool inner values at the annotation
    layer in most cases. The validator's body adds the defensive inner-
    value bool invariant against any truthy-but-non-bool smuggling
    through the kv-table or raw-JSON edit paths.

    Per Flight DD §8: the validator does NOT cross-check against the
    L5 account-level ``Connector.config["always_listen"]`` switch
    or against ``connector_ids``; "accept-and-document is the
    lighter discipline" — orphan or structurally-inert entries are
    inert at runtime, not at validate time.
    """

    def test_default_none_is_valid(self) -> None:
        """``connector_always_listen`` defaults to None (no per-agent
        override).
        """
        cfg = AgentConfig(name="agent")
        assert cfg.connector_always_listen is None

    def test_empty_outer_dict_is_valid(self) -> None:
        """``{}`` is valid (semantically same as None at runtime; codec
        preserves the distinction for round-trip fidelity).
        """
        cfg = AgentConfig(name="agent", connector_always_listen={})
        assert cfg.connector_always_listen == {}

    def test_explicit_true_per_account_is_valid(self) -> None:
        """``{"acct-a": True}`` is valid — per-agent always-listen toggle
        flipped on for that account.
        """
        cfg = AgentConfig(name="agent", connector_always_listen={"acct-a": True})
        assert cfg.connector_always_listen == {"acct-a": True}

    def test_explicit_false_per_account_is_valid(self) -> None:
        """``{"acct-a": False}`` is valid — explicit False round-trips
        as-is (equivalent in runtime semantic to absent, but preserved
        by the codec so the operator's intent is retained).
        """
        cfg = AgentConfig(name="agent", connector_always_listen={"acct-a": False})
        assert cfg.connector_always_listen == {"acct-a": False}

    def test_mixed_true_false_per_account_is_valid(self) -> None:
        """``{"acct-a": True, "acct-b": False}`` validates — two accounts
        with different per-agent toggle states.
        """
        cfg = AgentConfig(
            name="agent",
            connector_always_listen={"acct-a": True, "acct-b": False},
        )
        assert cfg.connector_always_listen == {
            "acct-a": True,
            "acct-b": False,
        }

    def test_validator_rejects_non_bool_inner_value(self) -> None:
        """Non-bool-coercible inner value raises ValidationError — the
        ``dict[str, bool]`` annotation rejects values Pydantic v2 cannot
        coerce to bool (e.g. a list). Pydantic v2 DOES coerce specific
        bool-like strings (``"true"``, ``"false"``, ``"yes"``, ``"no"``)
        and ``0``/``1`` to bool; this test pins the rejection path for
        a value firmly outside that coercion table.
        """
        with pytest.raises(ValidationError):
            AgentConfig(
                name="agent",
                connector_always_listen={"acct-a": ["not", "a", "bool"]},
            )

    def test_validator_accepts_true_per_agent_toggle_without_cross_check_against_account(
        self,
    ) -> None:
        """``{"acct-a": True}`` validates cleanly with no account-level
        cross-check — locks the DD §8 "accept-and-document" discipline.

        The validator does NOT verify that the account-level
        ``always_listen`` switch (L5) is True. Composition happens at
        the L8 policy-gate consult site at runtime; per-agent True with
        account-level False is structurally inert (the account check
        short-circuits) but not a validation error.
        """
        cfg = AgentConfig(name="agent", connector_always_listen={"acct-a": True})
        assert cfg.connector_always_listen == {"acct-a": True}

    def test_orphan_account_id_toggle_validates_cleanly(self) -> None:
        """``{"acct-not-attached": True}`` validates fine even when
        ``connector_ids`` is empty — mirrors the
        ``connector_acls`` precedent: the validator does NOT cross-check
        against ``connector_ids``; orphan toggles are inert at
        runtime (L8 only consults the toggle when actually routing for
        that account).
        """
        cfg = AgentConfig(
            name="agent",
            connector_ids=[],
            connector_always_listen={"acct-not-attached": True},
        )
        assert cfg.connector_ids == []
        assert cfg.connector_always_listen == {"acct-not-attached": True}


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


class TestConnectorRepository:
    """CRUD coverage for ConnectorRepository.

    Mission 10 flight 01 leg 02 — sibling to ``TestMCPSourceRepository``,
    minus the ``merged_config`` test (the helper is deferred to flight 06
    per flight Design Decisions). The encryption envelope assertions and
    reference-not-copy invariant are exercised identically.
    """

    async def test_create_and_get(self, connector_repo: ConnectorRepository) -> None:
        account = Connector(
            id="a1", name="Test Bot", type="stub", config={"intent": "guild_messages"}
        )
        await connector_repo.create(account)
        loaded = await connector_repo.get("a1")
        assert loaded.name == "Test Bot"
        assert loaded.config == {"intent": "guild_messages"}

    async def test_list(self, connector_repo: ConnectorRepository) -> None:
        await connector_repo.create(Connector(id="b", name="Bravo Bot", type="stub"))
        await connector_repo.create(Connector(id="a", name="Alpha Bot", type="stub"))
        accounts = await connector_repo.list()
        assert [a.name for a in accounts] == ["Alpha Bot", "Bravo Bot"]

    async def test_update(self, connector_repo: ConnectorRepository) -> None:
        await connector_repo.create(Connector(id="a1", name="Old Name", type="stub"))
        account = await connector_repo.get("a1")
        account.name = "New Name"
        await connector_repo.update(account)
        loaded = await connector_repo.get("a1")
        assert loaded.name == "New Name"

    async def test_delete(self, connector_repo: ConnectorRepository) -> None:
        await connector_repo.create(Connector(id="a1", name="Doomed", type="stub"))
        await connector_repo.delete("a1")
        with pytest.raises(KeyError):
            await connector_repo.get("a1")

    async def test_secrets_round_trip(self, connector_repo: ConnectorRepository) -> None:
        """secrets dict round-trips through the encryption envelope."""
        account = Connector(
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

    async def test_secrets_encrypted_at_rest(self, connector_repo: ConnectorRepository) -> None:
        """Raw DB read of the secrets column yields ciphertext, NOT plaintext JSON."""
        import json

        account = Connector(
            id="a1",
            name="Test",
            type="stub",
            secrets={"TOKEN": "super-secret-value"},
        )
        await connector_repo.create(account)
        async with connector_repo.conn.execute(
            "SELECT secrets FROM connectors WHERE id = ?", ("a1",)
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

    async def test_empty_secrets_default(self, connector_repo: ConnectorRepository) -> None:
        """An account created without secrets= round-trips with secrets={}."""
        account = Connector(id="a1", name="Test", type="stub", config={"x": 1})
        await connector_repo.create(account)
        fetched = await connector_repo.get("a1")
        assert fetched.secrets == {}

    async def test_install_key_post_create_decrypts_via_same_instance(
        self, connector_repo: ConnectorRepository
    ) -> None:
        """Post install_key, the same repo instance decrypts new writes.

        Locks the reference-not-copy invariant: install_key() mutates the
        Encryptor in place; the repository's stored reference sees the
        mutation. Re-creates a row after the key swap and round-trips.
        """
        from cryptography.fernet import Fernet

        new_key = Fernet.generate_key()
        connector_repo.encryptor.install_key(new_key)

        account = Connector(
            id="a1",
            name="PostKey",
            type="stub",
            secrets={"K": "value-after-rotation"},
        )
        await connector_repo.create(account)
        fetched = await connector_repo.get("a1")
        assert fetched.secrets == {"K": "value-after-rotation"}

    async def test_idle_timeout_seconds_round_trips_real_value(
        self, connector_repo: ConnectorRepository
    ) -> None:
        """A real ``idle_timeout_seconds`` value round-trips through
        create → get → update → get.

        Mission 10 flight 02 leg 02: the per-account override surface.
        """
        account = Connector(
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
        self, connector_repo: ConnectorRepository
    ) -> None:
        """An account created without ``idle_timeout_seconds`` round-trips
        as ``None`` (the default — fall through to env-var / default in
        ``_resolve_ttl_seconds``) and survives a no-op update.
        """
        account = Connector(id="a1", name="No TTL", type="stub")
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
            Connector(id="a", name="x", type="stub", idle_timeout_seconds=0)
        assert "between 1 and 604800" in str(exc_info.value)

    async def test_idle_timeout_seconds_validator_rejects_one_week_plus_one(
        self,
    ) -> None:
        """Validator rejects 604801 (catches the ms-vs-s typo)."""
        import pytest

        with pytest.raises(ValueError) as exc_info:
            Connector(id="a", name="x", type="stub", idle_timeout_seconds=604801)
        assert "between 1 and 604800" in str(exc_info.value)

    async def test_idle_timeout_seconds_validator_accepts_bounds(self) -> None:
        """Validator accepts 1, 604800, and None (the default)."""
        # Lower bound: 1.
        a1 = Connector(id="a", name="x", type="stub", idle_timeout_seconds=1)
        assert a1.idle_timeout_seconds == 1
        # Upper bound: 604800 (7 days).
        a2 = Connector(id="b", name="x", type="stub", idle_timeout_seconds=604800)
        assert a2.idle_timeout_seconds == 604800
        # None — default; accepted, falls through to env-var / default.
        a3 = Connector(id="c", name="x", type="stub", idle_timeout_seconds=None)
        assert a3.idle_timeout_seconds is None


# ── Connector Account Config Validator (F6 L1b) ──────────────────────────


class TestConnectorConfigValidator:
    """F6 L1b — config["pairing"] + config["allowlist"] schema."""

    # --- Direct-construction (model-only) tests ---

    def test_empty_config_is_unchanged(self) -> None:
        account = Connector(id="a", name="n", type="stub")
        assert account.config == {}

    def test_non_reserved_keys_pass_through(self) -> None:
        account = Connector(
            id="a",
            name="n",
            type="stub",
            config={"intent": "guild_messages", "version": 2},
        )
        assert account.config == {"intent": "guild_messages", "version": 2}

    def test_valid_pairing_round_trips(self) -> None:
        pairing = {"code": "abc-123", "issued_at": "2026-05-18T00:00:00Z"}
        account = Connector(id="a", name="n", type="stub", config={"pairing": pairing})
        assert account.config["pairing"] == pairing

    def test_valid_allowlist_round_trips(self) -> None:
        # M11 F17 L8 (Leg D) — bare ``{id}`` peers post-v28.
        allowlist = {
            "peers": [
                {"id": "u1"},
                {"id": "u2"},
            ],
            "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
        }
        account = Connector(id="a", name="n", type="stub", config={"allowlist": allowlist})
        # The validator also inserts ``dm_admission`` default.
        assert account.config["allowlist"]["peers"] == allowlist["peers"]
        assert account.config["allowlist"]["channels"] == allowlist["channels"]

    def test_empty_allowlist_is_preserved_verbatim(self) -> None:
        """Distinct from absent allowlist: empty lists mean lockdown.

        M11 F10 L1: the validator inserts the ``dm_admission``
        fresh-account default when an allowlist is present but the
        key is absent — the empty ``peers``/``channels`` lists
        themselves are still preserved verbatim.

        M11 F12 L3: the default Literal value was renamed from
        ``"allowlisted-peers-only"`` to ``"admin-approved"``.
        """
        account = Connector(
            id="a",
            name="n",
            type="stub",
            config={"allowlist": {"peers": [], "channels": []}},
        )
        assert account.config["allowlist"] == {
            "peers": [],
            "channels": [],
            "dm_admission": "admin-approved",
        }

    def test_mixed_reserved_and_non_reserved_round_trips(self) -> None:
        config = {
            "pairing": {"code": "x", "issued_at": "2026-05-18T00:00:00Z"},
            "allowlist": {"peers": [], "channels": []},
            "intent": "guild_messages",
        }
        account = Connector(id="a", name="n", type="stub", config=config)
        assert account.config == config

    # --- Pairing malformed shape tests ---

    def test_pairing_must_be_dict(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"pairing": "not-a-dict"},
            )

    def test_pairing_missing_code_raises(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"pairing": {"issued_at": "2026-05-18T00:00:00Z"}},
            )

    def test_pairing_missing_issued_at_raises(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"pairing": {"code": "x"}},
            )

    def test_pairing_extra_key_raises(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={
                    "pairing": {
                        "code": "x",
                        "issued_at": "2026-05-18T00:00:00Z",
                        "extra": "field",
                    }
                },
            )

    def test_pairing_empty_code_raises(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"pairing": {"code": "", "issued_at": "2026-05-18T00:00:00Z"}},
            )

    def test_pairing_non_string_code_raises(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"pairing": {"code": 123, "issued_at": "2026-05-18T00:00:00Z"}},
            )

    def test_pairing_malformed_issued_at_raises(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"pairing": {"code": "x", "issued_at": "not-iso"}},
            )

    def test_pairing_date_only_issued_at_raises(self) -> None:
        """date-only strings parse via fromisoformat but lack time
        component — leg-4 Studio writer emits full timestamps.
        """
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"pairing": {"code": "x", "issued_at": "2026-05-18"}},
            )

    # --- Allowlist malformed shape tests ---

    def test_allowlist_must_be_dict(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"allowlist": ["not-a-dict"]},
            )

    def test_allowlist_missing_peers_raises(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"allowlist": {"channels": []}},
            )

    def test_allowlist_missing_channels_raises(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"allowlist": {"peers": []}},
            )

    def test_allowlist_extra_key_raises(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"allowlist": {"peers": [], "channels": [], "extra": []}},
            )

    def test_allowlist_non_list_peers_raises(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"allowlist": {"peers": "not-a-list", "channels": []}},
            )

    def test_allowlist_non_string_peer_raises(self) -> None:
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"allowlist": {"peers": [123], "channels": []}},
            )

    # --- M10 F8 L8 — 4-axis allowlist (guilds + roles) ---

    def test_allowlist_full_4_axis_shape_round_trips(self) -> None:
        """All 4 axes (peers, channels, guilds, roles) populate and
        round-trip verbatim — pins the L8 shape contract. Verifies the
        validator accepts ``guilds`` + ``roles`` as legal keys.

        M11 F12 L3 — peers/channels/roles use the structured-tuple
        shape; guilds stays as list[str].
        """
        # M11 F17 L8 (Leg D) — bare ``{id}`` peers post-v28.
        allowlist = {
            "peers": [
                {"id": "u1"},
                {"id": "u2"},
            ],
            "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
            "guilds": ["g1", "g2"],
            "roles": [{"guild_id": "g-test", "role_id": "r1"}],
        }
        account = Connector(id="a", name="n", type="stub", config={"allowlist": allowlist})
        for key in ("peers", "channels", "guilds", "roles"):
            assert account.config["allowlist"][key] == allowlist[key]

    def test_allowlist_partial_axes_round_trips(self) -> None:
        """Partial L8 shapes are accepted — ``guilds`` alone (no roles),
        ``roles`` alone (no guilds), and pre-L8 2-key shape all validate.
        Pins the back-compat invariant: guilds + roles are OPTIONAL.

        M11 F10 L1: validator now inserts ``dm_admission`` default
        when absent — the assertion includes the fresh-account default
        below.

        M11 F12 L3: default value renamed to ``"admin-approved"``;
        peers/channels/roles use the structured-tuple shape.
        """
        # 2-key shape still works.
        acc1 = Connector(
            id="a1",
            name="n",
            type="stub",
            config={"allowlist": {"peers": [], "channels": []}},
        )
        assert acc1.config["allowlist"] == {
            "peers": [],
            "channels": [],
            "dm_admission": "admin-approved",
        }
        # peers + channels + guilds only (no roles).
        acc2 = Connector(
            id="a2",
            name="n",
            type="stub",
            config={
                "allowlist": {
                    "peers": [],
                    "channels": [],
                    "guilds": ["G1"],
                }
            },
        )
        assert acc2.config["allowlist"]["guilds"] == ["G1"]
        assert "roles" not in acc2.config["allowlist"]
        # peers + channels + roles only (no guilds).
        acc3 = Connector(
            id="a3",
            name="n",
            type="stub",
            config={
                "allowlist": {
                    "peers": [],
                    "channels": [],
                    "roles": [{"guild_id": "g-test", "role_id": "R1"}],
                }
            },
        )
        assert acc3.config["allowlist"]["roles"] == [{"guild_id": "g-test", "role_id": "R1"}]
        assert "guilds" not in acc3.config["allowlist"]

    def test_allowlist_extra_key_still_rejected_after_l8(self) -> None:
        """The L8 4-axis allowed set is exactly
        ``{peers, channels, guilds, roles}`` — anything else still
        rejects. Pins the validator does NOT silently widen beyond the
        new axes."""
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={
                    "allowlist": {
                        "peers": [],
                        "channels": [],
                        "guilds": [],
                        "roles": [],
                        "workspaces": [],  # not in the 4-axis allowed set
                    }
                },
            )

    def test_allowlist_non_string_guild_or_role_raises(self) -> None:
        """Per-item-string validation applies uniformly to all 4 axes
        — ``guilds`` and ``roles`` reject non-string entries the same
        way ``peers`` and ``channels`` do."""
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={
                    "allowlist": {
                        "peers": [],
                        "channels": [],
                        "guilds": [42],
                    }
                },
            )
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={
                    "allowlist": {
                        "peers": [],
                        "channels": [],
                        "roles": [None],
                    }
                },
            )

    # --- Repository round-trip tests ---

    async def test_pairing_round_trips_through_repo(
        self, connector_repo: ConnectorRepository
    ) -> None:
        pairing = {"code": "abc", "issued_at": "2026-05-18T00:00:00Z"}
        account = Connector(id="a1", name="n", type="stub", config={"pairing": pairing})
        await connector_repo.create(account)
        loaded = await connector_repo.get("a1")
        assert loaded.config["pairing"] == pairing

    async def test_allowlist_round_trips_through_repo(
        self, connector_repo: ConnectorRepository
    ) -> None:
        # M11 F17 L8 (Leg D) — bare ``{id}`` peers post-v28.
        allowlist = {
            "peers": [{"id": "u1"}],
            "channels": [{"guild_id": "g-test", "channel_id": "c1"}],
        }
        account = Connector(id="a1", name="n", type="stub", config={"allowlist": allowlist})
        await connector_repo.create(account)
        loaded = await connector_repo.get("a1")
        assert loaded.config["allowlist"]["peers"] == allowlist["peers"]
        assert loaded.config["allowlist"]["channels"] == allowlist["channels"]

    async def test_empty_allowlist_round_trips_through_repo(
        self, connector_repo: ConnectorRepository
    ) -> None:
        """Empty-allowlist lockdown survives DB round-trip — does NOT
        become absent. Leg-4 Studio UI relies on this invariant.
        """
        empty = {"peers": [], "channels": []}
        account = Connector(id="a1", name="n", type="stub", config={"allowlist": empty})
        await connector_repo.create(account)
        loaded = await connector_repo.get("a1")
        assert loaded.config["allowlist"] == empty
        assert "allowlist" in loaded.config  # not erased

    async def test_v24_structured_shape_full_round_trip_through_sqlite(
        self, connector_repo: ConnectorRepository
    ) -> None:
        """M11 F12 L3 / M11 F17 L8 (Leg D) — SQLite JSON-column round-trip
        of the post-v28 structured shape (peers / channels / roles)
        preserves every field verbatim.

        Pydantic validates shape at the Python boundary; SQLite stores
        arbitrary JSON. This test catches accidental shape mutations
        inside the repository serialize/deserialize path that the
        validator would not otherwise notice (e.g. dict key reordering).
        Peers are bare ``{id}`` post-v28 (dm_allowed retired).
        """
        allowlist = {
            "peers": [
                {"id": "u1"},
                {"id": "u2"},
                {"id": "u3"},
            ],
            "channels": [
                {"guild_id": "g-test", "channel_id": "c-no-guild"},
                {"guild_id": "g-1", "channel_id": "c-bound"},
            ],
            "guilds": ["g-1", "g-2"],
            "roles": [
                {"guild_id": "g-test", "role_id": "r-global"},
                {"guild_id": "g-1", "role_id": "r-bound"},
            ],
            "dm_admission": "admin-approved",
        }
        original = Connector(
            id="a-v24-rt",
            name="v24-round-trip",
            type="stub",
            config={"allowlist": allowlist},
        )
        await connector_repo.create(original)
        loaded = await connector_repo.get("a-v24-rt")

        # Exact-equality check on every axis — no field reordering,
        # type coercion, or value drift.
        loaded_allowlist = loaded.config["allowlist"]
        assert loaded_allowlist["peers"] == allowlist["peers"]
        assert loaded_allowlist["channels"] == allowlist["channels"]
        assert loaded_allowlist["guilds"] == allowlist["guilds"]
        assert loaded_allowlist["roles"] == allowlist["roles"]
        assert loaded_allowlist["dm_admission"] == "admin-approved"
        # Belt-and-braces: bare peer entries have exactly one key.
        for peer_entry in loaded_allowlist["peers"]:
            assert set(peer_entry.keys()) == {"id"}, peer_entry

    async def test_dm_admission_round_trips_through_repo(
        self, connector_repo: ConnectorRepository
    ) -> None:
        """M11 F10 L1 — ``allowlist.dm_admission`` survives create →
        list → get → update → get verbatim.

        Pins the per-axis tri-state Literal value round-trip through
        the JSON column. Validates all three values
        (``"none"``, ``"admin-approved"``, ``"all"``).

        M11 F12 L3 — Literal value renamed from
        ``"allowlisted-peers-only"`` to ``"admin-approved"``; peers
        use the structured-tuple shape.
        """
        # Create with dm_admission = "all".
        # M11 F17 L8 (Leg D) — bare ``{id}`` peers post-v28.
        account = Connector(
            id="a1",
            name="n",
            type="stub",
            config={
                "allowlist": {
                    "peers": [{"id": "P1"}],
                    "channels": [],
                    "dm_admission": "all",
                }
            },
        )
        await connector_repo.create(account)

        # List sees the dm_admission value.
        listed = await connector_repo.list()
        listed_account = next(a for a in listed if a.id == "a1")
        assert listed_account.config["allowlist"]["dm_admission"] == "all"

        # Get round-trips it.
        loaded = await connector_repo.get("a1")
        assert loaded.config["allowlist"]["dm_admission"] == "all"

        # Update to "none".
        loaded.config["allowlist"]["dm_admission"] = "none"
        await connector_repo.update(loaded)
        reloaded = await connector_repo.get("a1")
        assert reloaded.config["allowlist"]["dm_admission"] == "none"

        # Update to "admin-approved".
        reloaded.config["allowlist"]["dm_admission"] = "admin-approved"
        await connector_repo.update(reloaded)
        final = await connector_repo.get("a1")
        assert final.config["allowlist"]["dm_admission"] == ("admin-approved")

    async def test_empty_allowlist_stored_as_lists_not_null(
        self, connector_repo: ConnectorRepository
    ) -> None:
        """Pin the storage-layer invariant — empty lists are stored
        literally as ``[]`` in the JSON column, NOT as ``null`` or
        absent. The Pydantic round-trip proves the model-level
        invariant; this proves the persistence-level invariant. Leg
        4's UI writer reads back through Pydantic, but a raw SQL
        inspection from a future operator tool or migration would
        otherwise be ambiguous.
        """
        import json

        empty = {"peers": [], "channels": []}
        account = Connector(id="a1", name="n", type="stub", config={"allowlist": empty})
        await connector_repo.create(account)
        async with connector_repo.conn.execute(
            "SELECT config FROM connectors WHERE id = ?", ("a1",)
        ) as cur:
            row = await cur.fetchone()
        raw = json.loads(row["config"])
        # M11 F10 L1 + M11 F12 L3: the validator inserts
        # ``dm_admission`` default ``"admin-approved"`` on construction
        # (renamed from ``"allowlisted-peers-only"`` in F12 L3), so
        # the serialized JSON carries it too.
        assert raw == {
            "allowlist": {
                "peers": [],
                "channels": [],
                "dm_admission": "admin-approved",
            }
        }
        # JSON null would deserialize as None; absent key would mean
        # "allowlist" not in raw. Neither is the case.
        assert raw["allowlist"]["peers"] == []
        assert raw["allowlist"]["channels"] == []

    async def test_validator_fires_on_repo_read_path(
        self, connector_repo: ConnectorRepository
    ) -> None:
        """Hand-write a malformed config — read MUST raise.

        Confirms the cycle-1 H2 concern is closed: Pydantic v2 fires
        ``@field_validator`` on direct ``BaseModel(**kwargs)`` (which
        is what ``_row_to_model`` does), so the read path is validated.

        Implementation: create a VALID row through the repository
        (so secrets ciphertext is well-formed), then UPDATE the
        ``config`` column with malformed JSON via raw SQL. This
        bypasses the model validator on write while leaving the
        secrets ciphertext intact so the read path reaches
        ``_validate_config_reserved_keys`` and raises there (not
        on secrets-decrypt).
        """
        import json

        account = Connector(id="bad", name="n", type="stub", secrets={"TOKEN": "x"})
        await connector_repo.create(account)
        malformed = json.dumps({"pairing": {"code": ""}})  # missing issued_at + empty code
        await connector_repo.conn.execute(
            "UPDATE connectors SET config = ? WHERE id = ?",
            (malformed, "bad"),
        )
        await connector_repo.conn.commit()
        with pytest.raises(ValidationError):
            await connector_repo.get("bad")

    # --- M11 F7 L5 — always_listen + legacy auto_relay_platform_replies strip ---

    def test_validate_config_accepts_always_listen_bool(self) -> None:
        """Explicit True and False both validate cleanly. Absent is
        equivalent to default-False at consume time (the policy gate
        applies the ``.get(..., False)`` default) but is also a valid
        on-disk shape — covered implicitly by every pre-F7 row.
        """
        account_true = Connector(
            id="a-true",
            name="n",
            type="stub",
            config={"always_listen": True},
        )
        assert account_true.config["always_listen"] is True

        account_false = Connector(
            id="a-false",
            name="n",
            type="stub",
            config={"always_listen": False},
        )
        assert account_false.config["always_listen"] is False

        account_absent = Connector(
            id="a-absent",
            name="n",
            type="stub",
            config={},
        )
        assert "always_listen" not in account_absent.config

    def test_validate_config_rejects_non_bool_always_listen(self) -> None:
        """A string "yes" / int 1 / None — none of these are accepted.
        Operators can't smuggle truthy/falsy non-bools through the
        kv-table editor path; the validator forces an explicit bool.
        """
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"always_listen": "yes"},
            )
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"always_listen": 1},
            )
        with pytest.raises(ValidationError):
            Connector(
                id="a",
                name="n",
                type="stub",
                config={"always_listen": None},
            )

    def test_validate_config_strips_legacy_auto_relay_platform_replies(
        self,
    ) -> None:
        """When the legacy key is in the input dict, the validator returns
        a dict that no longer contains it (regardless of the bool value).
        Auto-relay became invariant in F7; the legacy key carries no useful
        information and is migrated out on every validate cycle.
        """
        account_true = Connector(
            id="a-true",
            name="n",
            type="stub",
            config={"auto_relay_platform_replies": True},
        )
        assert "auto_relay_platform_replies" not in account_true.config

        account_false = Connector(
            id="a-false",
            name="n",
            type="stub",
            config={"auto_relay_platform_replies": False},
        )
        assert "auto_relay_platform_replies" not in account_false.config

    def test_validate_config_strips_legacy_auto_relay_with_always_listen_present(
        self,
    ) -> None:
        """Both keys in input: legacy stripped, always_listen retained.
        Mixed-state row migrates cleanly without losing the new key.
        """
        account = Connector(
            id="a",
            name="n",
            type="stub",
            config={
                "auto_relay_platform_replies": True,
                "always_listen": True,
            },
        )
        assert "auto_relay_platform_replies" not in account.config
        assert account.config["always_listen"] is True

    def test_validate_config_accepts_legacy_auto_relay_value_in_input_silently(
        self,
    ) -> None:
        """Input has ``auto_relay_platform_replies: "not-a-bool"`` (a
        corrupt non-bool value). The validator MUST NOT reject — the
        legacy key is stripped from the dict BEFORE the (now-removed)
        shape check would have run, so the row migrates cleanly even
        if the legacy value was somehow corrupt. Edge defense: the
        strip-then-return order matters.
        """
        account = Connector(
            id="a",
            name="n",
            type="stub",
            config={"auto_relay_platform_replies": "not-a-bool"},
        )
        assert "auto_relay_platform_replies" not in account.config


class TestAllowlistGuildIdRequired:
    """M11 F12 L5 — post-v25 the Pydantic validator rejects channel and
    role entries with null ``guild_id``. The hierarchical Server-as-
    parent UI emits guild-scoped tuples exclusively; null-``guild_id``
    is no longer a valid storage value.

    Companion tests at the migration level in
    ``test_db_migration.py::TestSchemaV25`` cover the v25 cleanup that
    deletes legacy orphan entries; these tests pin the validator
    boundary that prevents new ones from being written.
    """

    def test_null_guild_id_on_channel_rejected_with_clear_error(
        self,
    ) -> None:
        """Channel entry with ``guild_id=None`` raises
        ``ValidationError`` with an error message mentioning ``guild_id``
        and the L5 rationale (hierarchical Server-as-parent UI)."""
        with pytest.raises(Exception) as exc_info:
            Connector(
                id="a",
                name="n",
                type="stub",
                config={
                    "allowlist": {
                        "peers": [],
                        "channels": [
                            {"guild_id": None, "channel_id": "c1"},
                        ],
                    }
                },
            )
        msg = str(exc_info.value)
        assert "guild_id" in msg
        assert "non-null" in msg or "non null" in msg.lower() or "string" in msg

    def test_null_guild_id_on_role_rejected_with_clear_error(
        self,
    ) -> None:
        """Role entry with ``guild_id=None`` raises ``ValidationError``
        with an error message mentioning ``guild_id`` and the L5
        rationale."""
        with pytest.raises(Exception) as exc_info:
            Connector(
                id="a",
                name="n",
                type="stub",
                config={
                    "allowlist": {
                        "peers": [],
                        "channels": [],
                        "roles": [
                            {"guild_id": None, "role_id": "r1"},
                        ],
                    }
                },
            )
        msg = str(exc_info.value)
        assert "guild_id" in msg

    def test_missing_guild_id_on_channel_rejected(self) -> None:
        """Channel entry with no ``guild_id`` key (vs explicit None)
        also fails — guild_id is now a required field, not an optional
        one defaulted to None."""
        with pytest.raises(Exception) as exc_info:
            Connector(
                id="a",
                name="n",
                type="stub",
                config={
                    "allowlist": {
                        "peers": [],
                        "channels": [
                            {"channel_id": "c1"},
                        ],
                    }
                },
            )
        assert "guild_id" in str(exc_info.value)

    def test_wildcard_channel_id_accepted_with_concrete_guild_id(
        self,
    ) -> None:
        """The L5 wildcard sentinel ``"*"`` is a valid ``channel_id``
        string; the validator accepts it as long as ``guild_id`` is a
        concrete string."""
        account = Connector(
            id="a",
            name="n",
            type="stub",
            config={
                "allowlist": {
                    "peers": [],
                    "channels": [
                        {"guild_id": "g-1", "channel_id": "*"},
                    ],
                    "roles": [
                        {"guild_id": "g-1", "role_id": "*"},
                    ],
                }
            },
        )
        assert account.config["allowlist"]["channels"] == [{"guild_id": "g-1", "channel_id": "*"}]
        assert account.config["allowlist"]["roles"] == [{"guild_id": "g-1", "role_id": "*"}]


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
            connector_id="acc-1",
            channel_id="ch-1",
            thread_id=None,
            peer_id="peer-1",
            session_metadata={"routing": "default"},
            last_inbound_at="2026-05-17T00:00:00+00:00",
        )
        await chat_repo.create(session)
        loaded = await chat_repo.get("s-conn")
        assert loaded.platform == "discord"
        assert loaded.connector_id == "acc-1"
        assert loaded.channel_id == "ch-1"
        assert loaded.thread_id is None
        assert loaded.peer_id == "peer-1"
        assert loaded.session_metadata == {"routing": "default"}
        assert loaded.last_inbound_at == "2026-05-17T00:00:00+00:00"

    # ── M13 F02 L01: agent-wide chat-history purge ───────────────────────

    async def test_delete_all_for_agent_sweeps_interactive_and_connector(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """delete_all_for_agent removes BOTH an interactive session and a
        connector-keyed session (chat_sessions rows with agent_name set),
        returns the count, and leaves no sessions for that agent.
        """
        await agent_store.save(AgentConfig(name="a1"))
        await chat_repo.create(ChatSession(id="s-interactive", agent_name="a1"))
        await chat_repo.create(
            ChatSession(
                id="s-conn",
                agent_name="a1",
                platform="discord",
                connector_id="acc-1",
                channel_id="ch-1",
            )
        )
        deleted = await chat_repo.delete_all_for_agent("a1")
        assert deleted == 2
        assert await chat_repo.list(agent_name="a1") == []

    async def test_delete_all_for_agent_leaves_other_agents(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Cross-agent isolation: purging a1 must not touch a2's sessions."""
        await agent_store.save(AgentConfig(name="a1"))
        await agent_store.save(AgentConfig(name="a2"))
        await chat_repo.create(ChatSession(id="s1", agent_name="a1"))
        await chat_repo.create(ChatSession(id="s2", agent_name="a2"))
        deleted = await chat_repo.delete_all_for_agent("a1")
        assert deleted == 1
        survivors = await chat_repo.list(agent_name="a2")
        assert len(survivors) == 1
        assert survivors[0].id == "s2"

    async def test_delete_all_for_agent_empty_is_noop(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """An agent with no sessions returns 0 and does not raise."""
        await agent_store.save(AgentConfig(name="a1"))
        deleted = await chat_repo.delete_all_for_agent("a1")
        assert deleted == 0

    async def test_rename_then_purge_composition(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Rename re-points chat_sessions.agent_name in one transaction, so a
        name-keyed purge by the NEW name clears the renamed agent's sessions
        (interactive AND connector-keyed). The OLD name resolves to zero
        sessions because the cascade moved them, not because they were
        deleted under the old name. A bystander agent is left intact.
        """
        await agent_store.save(AgentConfig(name="a1"))
        await chat_repo.create(ChatSession(id="s-interactive", agent_name="a1"))
        await chat_repo.create(
            ChatSession(
                id="s-conn",
                agent_name="a1",
                platform="discord",
                connector_id="acc-1",
                channel_id="ch-1",
            )
        )
        await agent_store.save(AgentConfig(name="a2"))
        await chat_repo.create(ChatSession(id="s-bystander", agent_name="a2"))

        await agent_store.rename("a1", "a1-renamed")

        deleted = await chat_repo.delete_all_for_agent("a1-renamed")
        assert deleted == 2
        assert await chat_repo.list(agent_name="a1-renamed") == []
        assert await chat_repo.list(agent_name="a1") == []
        bystander = await chat_repo.list(agent_name="a2")
        assert len(bystander) == 1
        assert bystander[0].id == "s-bystander"

    # ── M13 F03 L02: age-filtered, id-returning purge ────────────────────
    #
    # Explicit ISO-8601-UTC strings pin the LEXICAL updated_at comparison
    # (DD3). aged < cutoff < recent lexically because all three share the
    # now_iso() shape (trailing +00:00); do not mix other timestamp shapes.

    async def test_delete_older_than_age_filter_and_returned_ids(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Deletes exactly the rows with updated_at < cutoff and returns
        their ids; rows at/after the cutoff are left.
        """
        aged = "2020-01-01T00:00:00+00:00"
        recent = "2099-01-01T00:00:00+00:00"
        cutoff = "2050-01-01T00:00:00+00:00"
        await agent_store.save(AgentConfig(name="a1"))
        await chat_repo.create(ChatSession(id="s-aged", agent_name="a1", updated_at=aged))
        await chat_repo.create(ChatSession(id="s-recent", agent_name="a1", updated_at=recent))
        deleted_ids = await chat_repo.delete_older_than("a1", cutoff)
        assert deleted_ids == ["s-aged"]
        survivors = await chat_repo.list(agent_name="a1")
        assert [s.id for s in survivors] == ["s-recent"]

    async def test_delete_older_than_connector_sweep_active_survives(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """A connector-keyed aged row is swept; a connector-keyed recent row
        (the active session's proxy) is kept — proving connector rows are
        subject to the same age filter and the active session survives.

        The "recent updated_at" here is the unit-level proxy for an active
        session; true most-recent-by-external-key resolution is Leg 4's
        behavior gate (DD4 coverage split) — not the real invariant.
        """
        aged = "2020-01-01T00:00:00+00:00"
        recent = "2099-01-01T00:00:00+00:00"
        cutoff = "2050-01-01T00:00:00+00:00"
        await agent_store.save(AgentConfig(name="a1"))
        await chat_repo.create(
            ChatSession(
                id="s-conn-aged",
                agent_name="a1",
                platform="discord",
                connector_id="acc-1",
                channel_id="ch-1",
                updated_at=aged,
            )
        )
        await chat_repo.create(
            ChatSession(
                id="s-conn-recent",
                agent_name="a1",
                platform="discord",
                connector_id="acc-1",
                channel_id="ch-1",
                updated_at=recent,
            )
        )
        deleted_ids = await chat_repo.delete_older_than("a1", cutoff)
        assert deleted_ids == ["s-conn-aged"]
        survivors = await chat_repo.list(agent_name="a1")
        assert [s.id for s in survivors] == ["s-conn-recent"]

    async def test_delete_older_than_leaves_other_agents(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Cross-agent isolation: sweeping a1 returns only a1's ids and never
        touches a2's aged row, regardless of its updated_at.
        """
        aged = "2020-01-01T00:00:00+00:00"
        cutoff = "2050-01-01T00:00:00+00:00"
        await agent_store.save(AgentConfig(name="a1"))
        await agent_store.save(AgentConfig(name="a2"))
        await chat_repo.create(ChatSession(id="s1", agent_name="a1", updated_at=aged))
        await chat_repo.create(ChatSession(id="s2", agent_name="a2", updated_at=aged))
        deleted_ids = await chat_repo.delete_older_than("a1", cutoff)
        assert deleted_ids == ["s1"]
        survivors = await chat_repo.list(agent_name="a2")
        assert [s.id for s in survivors] == ["s2"]

    async def test_delete_older_than_empty_and_all_recent_noop(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Returns [] for an agent with only recent rows (nothing matches)
        and for an agent with no rows at all — no error either way.
        """
        recent = "2099-01-01T00:00:00+00:00"
        cutoff = "2050-01-01T00:00:00+00:00"
        await agent_store.save(AgentConfig(name="a1"))
        await agent_store.save(AgentConfig(name="a2"))
        await chat_repo.create(ChatSession(id="s-recent", agent_name="a1", updated_at=recent))
        # All-recent agent: nothing predates the cutoff.
        assert await chat_repo.delete_older_than("a1", cutoff) == []
        assert [s.id for s in await chat_repo.list(agent_name="a1")] == ["s-recent"]
        # Agent with no rows at all.
        assert await chat_repo.delete_older_than("a2", cutoff) == []

    async def test_delete_older_than_boundary_at_cutoff_is_kept(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """The predicate is strict ``<``, so a row whose updated_at equals the
        cutoff exactly is KEPT (pins DD3's "predates the window" semantics).
        """
        cutoff = "2050-01-01T00:00:00+00:00"
        await agent_store.save(AgentConfig(name="a1"))
        await chat_repo.create(ChatSession(id="s-boundary", agent_name="a1", updated_at=cutoff))
        deleted_ids = await chat_repo.delete_older_than("a1", cutoff)
        assert deleted_ids == []
        assert [s.id for s in await chat_repo.list(agent_name="a1")] == ["s-boundary"]

    async def test_delete_older_than_rename_then_sweep_composition(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Rename re-points chat_sessions.agent_name in one transaction, so an
        age-filtered sweep by the NEW name removes the renamed agent's aged
        row, keeps its recent row, and leaves a bystander agent untouched.
        """
        aged = "2020-01-01T00:00:00+00:00"
        recent = "2099-01-01T00:00:00+00:00"
        cutoff = "2050-01-01T00:00:00+00:00"
        await agent_store.save(AgentConfig(name="a1"))
        await chat_repo.create(ChatSession(id="s-aged", agent_name="a1", updated_at=aged))
        await chat_repo.create(ChatSession(id="s-recent", agent_name="a1", updated_at=recent))
        await agent_store.save(AgentConfig(name="a2"))
        await chat_repo.create(ChatSession(id="s-bystander", agent_name="a2", updated_at=aged))

        await agent_store.rename("a1", "a1-renamed")

        deleted_ids = await chat_repo.delete_older_than("a1-renamed", cutoff)
        assert deleted_ids == ["s-aged"]
        assert [s.id for s in await chat_repo.list(agent_name="a1-renamed")] == ["s-recent"]
        bystander = await chat_repo.list(agent_name="a2")
        assert [s.id for s in bystander] == ["s-bystander"]

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
        assert loaded_plain.connector_id is None
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
            connector_id="acc-1",
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
                connector_id="acc-1",
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
            connector_id="acc-1",
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
                    connector_id="acc-1",
                    channel_id="ch-1",
                    thread_id=None,
                    created_at=ts,
                    updated_at=ts,
                    last_inbound_at=ts,
                )
            )
        result = await chat_repo.find_most_recent_by_external_key(
            platform="discord",
            connector_id="acc-1",
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
                connector_id="acc-1",
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
                connector_id="acc-1",
                channel_id="ch-1",
                thread_id="A",
                created_at="2026-05-02T00:00:00+00:00",
                updated_at="2026-05-02T00:00:00+00:00",
            )
        )

        # Query with thread_id=None matches the NULL row, NOT the "A" row.
        result_none = await chat_repo.find_most_recent_by_external_key(
            platform="discord",
            connector_id="acc-1",
            channel_id="ch-1",
            thread_id=None,
        )
        assert result_none is not None
        assert result_none.id == "s-null-thread"

        # Query with thread_id="A" matches the "A" row, NOT the NULL row.
        result_a = await chat_repo.find_most_recent_by_external_key(
            platform="discord",
            connector_id="acc-1",
            channel_id="ch-1",
            thread_id="A",
        )
        assert result_a is not None
        assert result_a.id == "s-thread-A"

    # ── M10 F06 L2: append_to_session_metadata ───────────────────────────

    async def test_append_to_session_metadata_initializes_null_to_dict(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """A session with NULL ``session_metadata`` → ``append_to_session_metadata``
        initialises it to ``{key: [value]}`` (NULL → ``{}`` → key absent → ``[]``
        → append).
        """
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(ChatSession(id="s1", agent_name="agent1"))
        # Sanity: the freshly-created row has NULL session_metadata.
        loaded = await chat_repo.get("s1")
        assert loaded.session_metadata is None

        entry = {"outcome": "permit", "peer_id": "p1", "ts": "t", "reason": None}
        await chat_repo.append_to_session_metadata("s1", "audit", entry)

        loaded = await chat_repo.get("s1")
        assert loaded.session_metadata == {"audit": [entry]}

    async def test_append_to_session_metadata_creates_list_for_absent_key(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """An existing ``session_metadata`` dict that lacks the target key
        → the key is created as a one-element list."""
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(
            ChatSession(
                id="s1",
                agent_name="agent1",
                session_metadata={"routing": "default"},
            )
        )

        entry = {"outcome": "deny", "peer_id": "p1", "ts": "t", "reason": "x"}
        await chat_repo.append_to_session_metadata("s1", "audit", entry)

        loaded = await chat_repo.get("s1")
        assert loaded.session_metadata == {
            "routing": "default",
            "audit": [entry],
        }

    async def test_append_to_session_metadata_appends_to_existing_list(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Two successive appends accumulate in insertion order on the
        same key."""
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(ChatSession(id="s1", agent_name="agent1"))

        e1 = {"outcome": "permit", "peer_id": "p1", "ts": "t1", "reason": None}
        e2 = {"outcome": "permit", "peer_id": "p2", "ts": "t2", "reason": None}
        await chat_repo.append_to_session_metadata("s1", "audit", e1)
        await chat_repo.append_to_session_metadata("s1", "audit", e2)

        loaded = await chat_repo.get("s1")
        assert loaded.session_metadata == {"audit": [e1, e2]}

    async def test_append_to_session_metadata_preserves_other_keys(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Other top-level keys in ``session_metadata`` are preserved
        verbatim across an append on a different key."""
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(
            ChatSession(
                id="s1",
                agent_name="agent1",
                session_metadata={
                    "routing": {"agent": "agent1"},
                    "other": ["a", "b"],
                },
            )
        )

        entry = {"outcome": "permit", "peer_id": "p", "ts": "t", "reason": None}
        await chat_repo.append_to_session_metadata("s1", "audit", entry)

        loaded = await chat_repo.get("s1")
        assert loaded.session_metadata == {
            "routing": {"agent": "agent1"},
            "other": ["a", "b"],
            "audit": [entry],
        }

    async def test_append_to_session_metadata_raises_keyerror_on_missing_session(
        self, chat_repo: ChatSessionRepository
    ) -> None:
        """Missing session id raises ``KeyError`` — mirrors
        :meth:`update_last_inbound` not-found semantics."""
        with pytest.raises(KeyError):
            await chat_repo.append_to_session_metadata(
                "no-such-session",
                "audit",
                {"outcome": "permit"},
            )

    # ── M10 F07 L5: set_session_metadata_key ─────────────────────────────

    async def test_set_session_metadata_key_writes_new_key(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """A session with NULL ``session_metadata`` → ``set_session_metadata_key``
        initialises to ``{key: value}`` (NULL → ``{}`` → overwrite)."""
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(ChatSession(id="s1", agent_name="agent1"))

        await chat_repo.set_session_metadata_key("s1", "foo", "bar")

        loaded = await chat_repo.get("s1")
        assert loaded.session_metadata == {"foo": "bar"}

    async def test_set_session_metadata_key_overwrites_existing_value(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Setting the same key twice keeps only the LAST writer's value —
        the last-writer-wins concurrency posture pinned by the docstring."""
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(ChatSession(id="s1", agent_name="agent1"))

        await chat_repo.set_session_metadata_key("s1", "foo", "bar")
        await chat_repo.set_session_metadata_key("s1", "foo", "baz")

        loaded = await chat_repo.get("s1")
        assert loaded.session_metadata == {"foo": "baz"}

    async def test_set_session_metadata_key_preserves_other_keys(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """Writes to one key preserve every other top-level key —
        last-writer-wins on the TARGET key + preserve-other invariant."""
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(ChatSession(id="s1", agent_name="agent1"))

        await chat_repo.set_session_metadata_key("s1", "foo", "bar")
        await chat_repo.set_session_metadata_key("s1", "other", [1, 2])
        await chat_repo.set_session_metadata_key("s1", "foo", "baz")

        loaded = await chat_repo.get("s1")
        assert loaded.session_metadata == {"foo": "baz", "other": [1, 2]}

    async def test_set_session_metadata_key_raises_on_unknown_session(
        self, chat_repo: ChatSessionRepository
    ) -> None:
        """Missing session id raises ``KeyError`` — mirrors
        :meth:`append_to_session_metadata` / :meth:`update_last_inbound`
        not-found semantics."""
        with pytest.raises(KeyError):
            await chat_repo.set_session_metadata_key("no-such-session", "foo", "bar")

    async def test_set_session_metadata_key_accepts_any_value_type(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        """JSON-serialisable scalar / list / dict / None all round-trip
        under the same primitive — the call site doesn't have to know
        the column's JSON-encoding shape."""
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(ChatSession(id="s1", agent_name="agent1"))

        await chat_repo.set_session_metadata_key("s1", "dict", {"a": 1})
        await chat_repo.set_session_metadata_key("s1", "list", [1, 2, 3])
        await chat_repo.set_session_metadata_key("s1", "string", "hello")
        await chat_repo.set_session_metadata_key("s1", "none", None)

        loaded = await chat_repo.get("s1")
        assert loaded.session_metadata == {
            "dict": {"a": 1},
            "list": [1, 2, 3],
            "string": "hello",
            "none": None,
        }


# ── M10 F03 L01: Connector session_continuation_seconds ───────────


class TestConnectorSessionContinuation:
    """Round-trip + validator coverage for the M10 F03 L01 field
    ``session_continuation_seconds`` on ``Connector``.

    Sibling to ``TestConnectorRepository`` 's
    ``idle_timeout_seconds`` tests; same shape, distinct concern (chat-
    session continuation window vs. pool warm-entry TTL).
    """

    async def test_session_continuation_seconds_round_trips_real_value(
        self, connector_repo: ConnectorRepository
    ) -> None:
        """A real ``session_continuation_seconds`` value round-trips
        through create → get → update → get."""
        account = Connector(
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
        self, connector_repo: ConnectorRepository
    ) -> None:
        """An account created without ``session_continuation_seconds`` round-
        trips as ``None`` (the default — fall through to resolver default)
        and survives a no-op update."""
        account = Connector(id="a1", name="No Continuation", type="stub")
        await connector_repo.create(account)
        fetched = await connector_repo.get("a1")
        assert fetched.session_continuation_seconds is None

        await connector_repo.update(fetched)
        refetched = await connector_repo.get("a1")
        assert refetched.session_continuation_seconds is None

    async def test_session_continuation_seconds_validator_rejects_zero(self) -> None:
        """Validator rejects 0 (would zero-out the continuation window)."""
        with pytest.raises(ValueError) as exc_info:
            Connector(id="a", name="x", type="stub", session_continuation_seconds=0)
        assert "between 1 and 604800" in str(exc_info.value)

    async def test_session_continuation_seconds_validator_rejects_one_week_plus_one(
        self,
    ) -> None:
        """Validator rejects 604801 (catches the ms-vs-s typo)."""
        with pytest.raises(ValueError) as exc_info:
            Connector(id="a", name="x", type="stub", session_continuation_seconds=604801)
        assert "between 1 and 604800" in str(exc_info.value)

    async def test_session_continuation_seconds_validator_accepts_bounds(
        self,
    ) -> None:
        """Validator accepts 1, 86400 (24h default), 604800 (7-day cap),
        and None (the default)."""
        a1 = Connector(id="a", name="x", type="stub", session_continuation_seconds=1)
        assert a1.session_continuation_seconds == 1
        a2 = Connector(id="b", name="x", type="stub", session_continuation_seconds=86400)
        assert a2.session_continuation_seconds == 86400
        a3 = Connector(id="c", name="x", type="stub", session_continuation_seconds=604800)
        assert a3.session_continuation_seconds == 604800
        a4 = Connector(id="d", name="x", type="stub", session_continuation_seconds=None)
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
        # The ISO-format now_iso() includes microseconds, but be safe.
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

    # ── M16 F08 L03: encrypted secrets split ──────────────────────────────

    async def test_secrets_round_trip_encrypt_on_write_decrypt_on_read(
        self, tool_config_repo: ToolConfigRepository, conn
    ) -> None:
        """upsert encrypts the secrets blob; get/list decrypt it back."""
        await tool_config_repo.upsert(
            "web_search",
            {"search_backend": "brave"},
            secrets={"brave_api_key": "BRAVE-SECRET-123"},
        )
        got = await tool_config_repo.get("web_search")
        assert got.config == {"search_backend": "brave"}
        assert got.secrets == {"brave_api_key": "BRAVE-SECRET-123"}

        # The on-disk column must be ciphertext — NOT the plaintext key.
        async with conn.execute(
            "SELECT secrets FROM tool_configs WHERE name = ?", ("web_search",)
        ) as cur:
            row = await cur.fetchone()
        stored = row["secrets"]
        assert "BRAVE-SECRET-123" not in stored
        assert stored not in ("{}", '{"brave_api_key": "BRAVE-SECRET-123"}')

    async def test_secrets_default_plaintext_decrypts_to_empty(
        self, tool_config_repo: ToolConfigRepository, conn
    ) -> None:
        """A pre-existing row whose secrets column holds the plaintext '{}'
        default (migration residue) decrypts to {} via InvalidToken
        tolerance, NOT a crash."""
        # Simulate the column default by writing the row WITHOUT going
        # through the encrypting upsert path.
        await conn.execute(
            "INSERT INTO tool_configs (name, config, secrets, enabled, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("legacy_tool", "{}", "{}", 1),
        )
        await conn.commit()
        got = await tool_config_repo.get("legacy_tool")
        assert got.secrets == {}

        # Next write re-encrypts the column.
        await tool_config_repo.upsert("legacy_tool", {}, secrets={"k": "v"})
        again = await tool_config_repo.get("legacy_tool")
        assert again.secrets == {"k": "v"}

    async def test_merged_config_folds_secrets_over_config(
        self, tool_config_repo: ToolConfigRepository
    ) -> None:
        """ToolConfig.merged_config() returns {**config, **secrets}."""
        await tool_config_repo.upsert(
            "web_search",
            {"search_backend": "tavily", "searxng_base_url": ""},
            secrets={"tavily_api_key": "TAVILY-XYZ"},
        )
        got = await tool_config_repo.get("web_search")
        merged = got.merged_config()
        assert merged == {
            "search_backend": "tavily",
            "searxng_base_url": "",
            "tavily_api_key": "TAVILY-XYZ",
        }

    async def test_upsert_without_secrets_kwarg_is_backward_compatible(
        self, tool_config_repo: ToolConfigRepository
    ) -> None:
        """Existing callers omitting `secrets` get an empty secrets blob."""
        await tool_config_repo.upsert("shell", {"timeout": 5}, enabled=True)
        got = await tool_config_repo.get("shell")
        assert got.secrets == {}
        assert got.merged_config() == {"timeout": 5}


# ── Pending Approval Repository ──────────────────────────────────────────


@pytest.fixture
def pending_approval_repo(conn):
    return PendingApprovalRepository(conn)


@pytest.fixture
async def _seed_connector(conn, connector_repo_encryptor):
    """Seed an ``acct-1`` connector account for FK-bound tests."""
    repo = ConnectorRepository(conn, connector_repo_encryptor)
    await repo.create(Connector(id="acct-1", name="Stub Account", type="stub"))
    await repo.create(Connector(id="acct-2", name="Stub Other", type="stub"))


class TestPendingApprovalRepository:
    """CRUD coverage for the M11 F9 L2 PendingApprovalRepository.

    Storage shape: one row per ``(connector_id, peer_id,
    status='pending')`` enforced by the upsert path; terminal-state
    transitions raise ``ValueError`` (idempotent on self-target).
    """

    async def test_upsert_creates_new_row(
        self,
        pending_approval_repo: PendingApprovalRepository,
        _seed_connector,
    ) -> None:
        appr, created = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hello",
        )
        assert created is True
        assert appr.connector_id == "acct-1"
        assert appr.peer_id == "peer-1"
        assert appr.peer_name == "Alice"
        assert appr.preview == "hello"
        assert appr.status == "pending"
        assert appr.resolved_at is None
        # id is the dispatcher-issued uuid (32 hex chars).
        assert len(appr.id) == 32
        # Round-trip via get().
        fetched = await pending_approval_repo.get(appr.id)
        assert fetched == appr

    async def test_upsert_dedup_updates_in_place(
        self,
        pending_approval_repo: PendingApprovalRepository,
        _seed_connector,
    ) -> None:
        """Two upserts for (acct-1, peer-1) while status='pending' →
        ONE row, second call returns the SAME id with refreshed
        peer_name / preview / received_at."""
        first, created_first = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hello",
        )
        assert created_first is True
        import asyncio

        await asyncio.sleep(0.005)
        second, created_second = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice Renamed",
            preview="hi again",
        )
        assert created_second is False
        assert second.id == first.id  # dedup → same row
        assert second.peer_name == "Alice Renamed"
        assert second.preview == "hi again"
        assert second.received_at >= first.received_at

        rows = await pending_approval_repo.list_for_account_peer("acct-1", "peer-1")
        assert len(rows) == 1, rows
        assert rows[0].id == first.id

    async def test_upsert_after_approve_creates_new_row(
        self,
        pending_approval_repo: PendingApprovalRepository,
        _seed_connector,
    ) -> None:
        """Upsert + mark_approved consumes the pending row; the next
        upsert with the same (account, peer) INSERTs a fresh row that
        coexists with the approved historical row."""
        first, created_first = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hello",
        )
        assert created_first is True
        await pending_approval_repo.mark_approved(first.id)
        second, created_second = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hello again",
        )
        assert created_second is True  # new pending row after the old one was approved
        assert second.id != first.id
        assert second.status == "pending"
        # Two rows now exist for this (account, peer).
        rows = await pending_approval_repo.list_for_account_peer("acct-1", "peer-1")
        assert {r.id for r in rows} == {first.id, second.id}
        statuses = {r.status for r in rows}
        assert statuses == {"approved", "pending"}

    async def test_get_raises_keyerror_for_unknown_id(
        self,
        pending_approval_repo: PendingApprovalRepository,
        _seed_connector,
    ) -> None:
        with pytest.raises(KeyError):
            await pending_approval_repo.get("does-not-exist")

    async def test_mark_approved_flips_status_and_sets_resolved_at(
        self,
        pending_approval_repo: PendingApprovalRepository,
        _seed_connector,
    ) -> None:
        appr, _ = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hello",
        )
        approved = await pending_approval_repo.mark_approved(appr.id)
        assert approved.id == appr.id
        assert approved.status == "approved"
        assert approved.resolved_at is not None
        assert isinstance(approved.resolved_at, str)
        assert len(approved.resolved_at) > 0

    async def test_mark_approved_idempotent_on_already_approved(
        self,
        pending_approval_repo: PendingApprovalRepository,
        _seed_connector,
    ) -> None:
        appr, _ = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hello",
        )
        once = await pending_approval_repo.mark_approved(appr.id)
        twice = await pending_approval_repo.mark_approved(appr.id)
        assert once == twice  # no further mutation

    async def test_mark_approved_on_dismissed_row_raises_valueerror(
        self,
        pending_approval_repo: PendingApprovalRepository,
        _seed_connector,
    ) -> None:
        appr, _ = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hello",
        )
        await pending_approval_repo.mark_dismissed(appr.id)
        with pytest.raises(ValueError, match="cannot transition to approved"):
            await pending_approval_repo.mark_approved(appr.id)

    async def test_mark_dismissed_mirrors(
        self,
        pending_approval_repo: PendingApprovalRepository,
        _seed_connector,
    ) -> None:
        appr, _ = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hello",
        )
        dismissed = await pending_approval_repo.mark_dismissed(appr.id)
        assert dismissed.status == "dismissed"
        assert dismissed.resolved_at is not None

        # Idempotent on self-target.
        once = dismissed
        twice = await pending_approval_repo.mark_dismissed(appr.id)
        assert once == twice

        # ValueError when trying to flip dismissed → approved is covered
        # by the dedicated test above. Cover the dismissed-on-approved
        # case here so dismiss is exercised symmetrically.
        other, _ = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-2",
            peer_name="Bob",
            preview="hi",
        )
        await pending_approval_repo.mark_approved(other.id)
        with pytest.raises(ValueError, match="cannot transition to dismissed"):
            await pending_approval_repo.mark_dismissed(other.id)

    async def test_list_for_account_peer_returns_oldest_first(
        self,
        pending_approval_repo: PendingApprovalRepository,
        _seed_connector,
    ) -> None:
        import asyncio

        first, _ = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hello",
        )
        await pending_approval_repo.mark_approved(first.id)
        await asyncio.sleep(0.005)
        second, _ = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="again",
        )
        rows = await pending_approval_repo.list_for_account_peer("acct-1", "peer-1")
        assert [r.id for r in rows] == [first.id, second.id]
        # received_at strictly non-decreasing.
        assert rows[0].received_at <= rows[1].received_at

    async def test_list_by_account_returns_all_for_account(
        self,
        pending_approval_repo: PendingApprovalRepository,
        _seed_connector,
    ) -> None:
        a1, _ = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hi",
        )
        a2, _ = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-2",
            peer_name="Bob",
            preview="hi",
        )
        # Different account — must NOT appear in acct-1's list.
        await pending_approval_repo.upsert_pending(
            connector_id="acct-2",
            peer_id="peer-3",
            peer_name="Carol",
            preview="hi",
        )
        rows = await pending_approval_repo.list_by_account("acct-1")
        ids = {r.id for r in rows}
        assert ids == {a1.id, a2.id}

    async def test_fk_cascade_via_connector_delete(
        self,
        pending_approval_repo: PendingApprovalRepository,
        _seed_connector,
        connector_repo: ConnectorRepository,
    ) -> None:
        """Deleting the parent connector removes the dependent
        pending_approvals rows via the v21 FK CASCADE."""
        await pending_approval_repo.upsert_pending(  # noqa: F841 — side-effect only
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hello",
        )
        # Sanity: row present.
        assert (len(await pending_approval_repo.list_by_account("acct-1"))) == 1
        await connector_repo.delete("acct-1")
        # Cascade removed the dependent row.
        assert (len(await pending_approval_repo.list_by_account("acct-1"))) == 0


class TestAppMetadataRepository:
    """Tests for the global app_metadata kv store (schema v31)."""

    async def test_get_absent_key_returns_none(
        self, app_metadata_repo: AppMetadataRepository
    ) -> None:
        assert await app_metadata_repo.get("last_purge_at") is None

    async def test_set_then_get_roundtrips(self, app_metadata_repo: AppMetadataRepository) -> None:
        await app_metadata_repo.set("last_purge_at", "2026-06-06T00:00:00Z")
        assert await app_metadata_repo.get("last_purge_at") == "2026-06-06T00:00:00Z"

    async def test_set_twice_upserts_latest_value(
        self, app_metadata_repo: AppMetadataRepository
    ) -> None:
        await app_metadata_repo.set("last_purge_at", "2026-06-06T00:00:00Z")
        # Second set on the same key must not raise (no PRIMARY KEY violation)
        # and the latest value wins.
        await app_metadata_repo.set("last_purge_at", "2026-06-07T12:30:00Z")
        assert await app_metadata_repo.get("last_purge_at") == "2026-06-07T12:30:00Z"

    async def test_empty_string_value_distinct_from_absent(
        self, app_metadata_repo: AppMetadataRepository
    ) -> None:
        # `value TEXT NOT NULL` permits '' but not SQL NULL; get returns None
        # only for an absent row, '' for a present-but-empty value.
        await app_metadata_repo.set("k", "")
        assert await app_metadata_repo.get("k") == ""


# ── AgentRevisionRepository (M21 F02 L01 — AC3/AC4/AC8) ──────────────────


@pytest.fixture
def agent_revision_repo(conn) -> AgentRevisionRepository:
    return AgentRevisionRepository(conn)


async def _seed_agent_row(conn, name: str) -> None:
    """Insert a bare agents row so the ON DELETE CASCADE FK resolves."""
    await conn.execute("INSERT INTO agents (name) VALUES (?)", (name,))
    await conn.commit()


async def _append_applied(
    repo: AgentRevisionRepository,
    agent_name: str,
    *,
    field="description",
    proposed="p",
    base="b",
    created_at="2026-08-24T00:00:00+00:00",
):
    return await repo.append(
        agent_name=agent_name,
        field=field,
        proposed_value=proposed,
        base_value=base,
        source="self",
        status="applied",
        restored_from=None,
        created_at=created_at,
        resolved_at=created_at,
    )


class TestAgentRevisionRepository:
    async def test_append_returns_row_and_get_roundtrips(self, agent_revision_repo, conn) -> None:
        await _seed_agent_row(conn, "a")
        row = await _append_applied(
            agent_revision_repo, "a", field="system_prompt", proposed="new", base="old"
        )
        assert row.agent_name == "a"
        assert row.field == "system_prompt"
        assert row.proposed_value == "new"
        assert row.base_value == "old"
        assert row.status == "applied"
        assert row.source == "self"
        assert row.restored_from is None
        assert row.resolved_at == row.created_at
        assert len(row.id) == 32  # uuid4().hex

        fetched = await agent_revision_repo.get(row.id)
        assert fetched == row

    async def test_get_missing_raises_keyerror(self, agent_revision_repo) -> None:
        with pytest.raises(KeyError):
            await agent_revision_repo.get("does-not-exist")

    async def test_list_for_agent_newest_first(self, agent_revision_repo, conn) -> None:
        await _seed_agent_row(conn, "a")
        r1 = await _append_applied(agent_revision_repo, "a", created_at="2026-08-24T00:00:01+00:00")
        r2 = await _append_applied(agent_revision_repo, "a", created_at="2026-08-24T00:00:02+00:00")
        r3 = await _append_applied(agent_revision_repo, "a", created_at="2026-08-24T00:00:03+00:00")

        rows = await agent_revision_repo.list_for_agent("a")
        assert [r.id for r in rows] == [r3.id, r2.id, r1.id]

    async def test_list_for_agent_same_timestamp_tiebreak_is_id_desc(
        self, agent_revision_repo, conn
    ) -> None:
        await _seed_agent_row(conn, "a")
        ts = "2026-08-24T00:00:00+00:00"
        made = [await _append_applied(agent_revision_repo, "a", created_at=ts) for _ in range(4)]
        rows = await agent_revision_repo.list_for_agent("a")
        expected = sorted((r.id for r in made), reverse=True)
        assert [r.id for r in rows] == expected

    async def test_list_for_agent_scoped_to_agent(self, agent_revision_repo, conn) -> None:
        await _seed_agent_row(conn, "a")
        await _seed_agent_row(conn, "b")
        await _append_applied(agent_revision_repo, "a")
        await _append_applied(agent_revision_repo, "b")
        assert len(await agent_revision_repo.list_for_agent("a")) == 1
        assert len(await agent_revision_repo.list_for_agent("b")) == 1

    async def test_fk_cascade_deletes_agent_revisions(self, agent_revision_repo, conn) -> None:
        # AC8 — must run against a foreign_keys=ON connection or the cascade
        # silently does not fire. Assert the pragma before relying on it.
        async with conn.execute("PRAGMA foreign_keys") as cur:
            assert (await cur.fetchone())[0] == 1, "cascade test needs PRAGMA foreign_keys=ON"

        await _seed_agent_row(conn, "a")
        await _append_applied(agent_revision_repo, "a")
        await _append_applied(agent_revision_repo, "a")
        assert len(await agent_revision_repo.list_for_agent("a")) == 2

        await conn.execute("DELETE FROM agents WHERE name = ?", ("a",))
        await conn.commit()

        assert await agent_revision_repo.list_for_agent("a") == []


# ── AgentRevisionRepository queue methods (M21 F02 L02 — AC5/AC6/AC9/AC10/AC12) ──


class TestAgentRevisionQueueMethods:
    async def test_count_pending_scoped_to_agent(self, agent_revision_repo, conn) -> None:
        await _seed_agent_row(conn, "a")
        await _seed_agent_row(conn, "b")
        await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="description", proposed_value="p1", base_value="b1"
        )
        await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="system_prompt", proposed_value="p2", base_value="b2"
        )
        await agent_revision_repo.upsert_pending_revision(
            agent_name="b", field="description", proposed_value="p3", base_value="b3"
        )
        assert await agent_revision_repo.count_pending("a") == 2
        assert await agent_revision_repo.count_pending("b") == 1
        assert await agent_revision_repo.count_pending("nobody") == 0

    async def test_upsert_creates_then_dedups_same_field(self, agent_revision_repo, conn) -> None:
        await _seed_agent_row(conn, "a")
        rev1, created1 = await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="description", proposed_value="first", base_value="base1"
        )
        assert created1 is True
        assert rev1.status == "pending"
        assert rev1.source == "self"
        assert rev1.resolved_at is None

        rev2, created2 = await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="description", proposed_value="second", base_value="base2"
        )
        assert created2 is False
        assert rev2.id == rev1.id  # same row updated in place
        assert rev2.proposed_value == "second"
        assert rev2.base_value == "base2"
        assert await agent_revision_repo.count_pending("a") == 1

    async def test_upsert_different_fields_separate_rows(self, agent_revision_repo, conn) -> None:
        await _seed_agent_row(conn, "a")
        r1, _ = await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="description", proposed_value="d", base_value="b"
        )
        r2, _ = await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="system_prompt", proposed_value="s", base_value="b"
        )
        assert r1.id != r2.id
        assert await agent_revision_repo.count_pending("a") == 2

    async def test_mark_applied_transitions_and_idempotent(self, agent_revision_repo, conn) -> None:
        await _seed_agent_row(conn, "a")
        rev, _ = await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="description", proposed_value="p", base_value="b"
        )
        applied = await agent_revision_repo.mark_applied(rev.id)
        assert applied.status == "applied"
        assert applied.resolved_at is not None
        # Idempotent on self-target.
        again = await agent_revision_repo.mark_applied(rev.id)
        assert again.status == "applied"

    async def test_mark_dismissed_transitions(self, agent_revision_repo, conn) -> None:
        await _seed_agent_row(conn, "a")
        rev, _ = await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="description", proposed_value="p", base_value="b"
        )
        dismissed = await agent_revision_repo.mark_dismissed(rev.id)
        assert dismissed.status == "dismissed"
        assert dismissed.resolved_at is not None

    async def test_transition_illegal_raises_valueerror(self, agent_revision_repo, conn) -> None:
        await _seed_agent_row(conn, "a")
        rev, _ = await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="description", proposed_value="p", base_value="b"
        )
        await agent_revision_repo.mark_applied(rev.id)
        # applied → dismissed is illegal.
        with pytest.raises(ValueError):
            await agent_revision_repo.mark_dismissed(rev.id)

    async def test_transition_missing_raises_keyerror(self, agent_revision_repo) -> None:
        with pytest.raises(KeyError):
            await agent_revision_repo.mark_applied("nope")

    async def test_update_base_value(self, agent_revision_repo, conn) -> None:
        await _seed_agent_row(conn, "a")
        rev, _ = await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="description", proposed_value="p", base_value="old"
        )
        updated = await agent_revision_repo.update_base_value(rev.id, "current")
        assert updated.base_value == "current"
        assert updated.status == "pending"  # unchanged

    async def test_supersede_pending_bulk(self, agent_revision_repo, conn) -> None:
        await _seed_agent_row(conn, "a")
        await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="description", proposed_value="p", base_value="b"
        )
        await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="system_prompt", proposed_value="p", base_value="b"
        )
        n = await agent_revision_repo.supersede_pending("a")
        assert n == 2
        assert await agent_revision_repo.count_pending("a") == 0
        rows = await agent_revision_repo.list_for_agent("a")
        assert all(r.status == "superseded" and r.resolved_at is not None for r in rows)

    async def test_supersede_leaves_terminal_rows_untouched(
        self, agent_revision_repo, conn
    ) -> None:
        await _seed_agent_row(conn, "a")
        rev, _ = await agent_revision_repo.upsert_pending_revision(
            agent_name="a", field="description", proposed_value="p", base_value="b"
        )
        await agent_revision_repo.mark_applied(rev.id)
        n = await agent_revision_repo.supersede_pending("a")
        assert n == 0
        assert (await agent_revision_repo.get(rev.id)).status == "applied"
