"""Tests for all database repositories."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db._kb_types import KB_ITEM_TRANSITIONS, ChunkRecord, KBItemTransitionError
from the_one.db.models import ChatSession, Connector, KBItem, KnowledgeBase, MCPSource
from the_one.db.repositories import (
    AgentRevisionRepository,
    AppMetadataRepository,
    ChatSessionRepository,
    ConnectorDirectoryRepository,
    ConnectorRepository,
    KBChunkRepository,
    KBItemRepository,
    KnowledgeBaseRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)


@pytest.fixture
async def conn(tmp_path):
    """Create a fresh in-memory-like DB connection with schema applied."""

    db_path = tmp_path / "test.db"
    connection = await connect_template_db(db_path)
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
def kb_chunk_repo(conn):
    return KBChunkRepository(conn)


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
def connector_directory_repo(conn):
    # No encryptor fixture (DD-4): connector_directory holds no secrets.
    return ConnectorDirectoryRepository(conn)


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

    async def test_list_by_kb_returns_only_agents_referencing_the_id(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        # L2-D6/AC-11: ordered by name, and an agent with an empty/absent
        # kb_ids contributes nothing.
        await agent_store.save(AgentConfig(name="charlie", kb_ids=["kb-x"]))
        await agent_store.save(AgentConfig(name="alpha", kb_ids=["kb-x", "kb-y"]))
        await agent_store.save(AgentConfig(name="bravo", kb_ids=["kb-y"]))
        await agent_store.save(AgentConfig(name="delta"))  # kb_ids default []
        assert await agent_store.list_by_kb("kb-x") == ["alpha", "charlie"]
        assert await agent_store.list_by_kb("kb-y") == ["alpha", "bravo"]
        assert await agent_store.list_by_kb("kb-z") == []

    async def test_list_by_kb_substring_id_not_falsely_matched(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        # L2-D6: the case a `LIKE '%<id>%'` implementation gets wrong —
        # "kb-1" is a substring of "kb-10", but must not match it.
        await agent_store.save(AgentConfig(name="has-kb-10", kb_ids=["kb-10"]))
        assert await agent_store.list_by_kb("kb-1") == []
        assert await agent_store.list_by_kb("kb-10") == ["has-kb-10"]

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
            " tool_overrides, mcp_overrides, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-agent",
                "",
                "mock-default",
                "",
                "[]",
                20,
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
            " tool_overrides, mcp_overrides, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-empty",
                "",
                "mock-default",
                "",
                "[]",
                20,
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
            " tool_overrides, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "corrupt-agent",
                "",
                "mock-default",
                "",
                "[]",
                20,
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
            " tool_overrides, mcp_overrides, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "empty-string-agent",
                "",
                "mock-default",
                "",
                "[]",
                20,
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

    # Mission 23 Flight 1 (backend-removal leg): the connector_ids /
    # connector_acls / connector_always_listen round-trip and
    # list_by_connector tests that used to live here are deleted along
    # with the fields and repository method themselves (DD-2, step 4) —
    # ``AgentConfig`` no longer has these fields, ``agents`` no longer
    # has these columns, and ``SQLiteAgentStore.list_by_connector`` no
    # longer exists.


# TestAgentConfigConnectorAclsValidator, TestPerAgentDmAllowedStrictRejection,
# and TestAgentConfigConnectorAlwaysListenValidator are deleted: Mission 23
# Flight 1 (backend-removal leg, step 4) removed the ``connector_acls`` and
# ``connector_always_listen`` fields (and their field validators) from
# ``AgentConfig`` entirely — there is nothing left to construct or validate.


# ── KnowledgeBase.id validation (Leg 5 review fix, BLOCKING 2) ────────────


class TestKnowledgeBaseIdValidation:
    """``KnowledgeBase.id`` is used verbatim to build a filesystem path in
    ``UsearchStore._path_for``, so it is restricted to a filename-safe
    charset at the model layer — see ``the_one/db/models.py``."""

    @pytest.mark.parametrize("kb_id", ["kb1", "kb-1", "a", "b", "a" * 64, "abc_DEF-123"])
    def test_conforming_ids_accepted(self, kb_id: str) -> None:
        kb = KnowledgeBase(id=kb_id, name="KB")
        assert kb.id == kb_id

    @pytest.mark.parametrize(
        "kb_id",
        [
            "../x",
            "../../etc/passwd",
            "a/b",
            "a\\b",
            "",
            "a" * 65,
            "kb id",  # space
            "kb.id",  # dot
        ],
    )
    def test_path_unsafe_or_out_of_range_ids_rejected(self, kb_id: str) -> None:
        with pytest.raises(ValidationError):
            KnowledgeBase(id=kb_id, name="KB")


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

    async def test_count(self, kb_repo: KnowledgeBaseRepository) -> None:
        """M24 F02 L03: the embedding warm-up gate reads this."""
        assert await kb_repo.count() == 0
        await kb_repo.create(KnowledgeBase(id="kb1", name="One"))
        assert await kb_repo.count() == 1
        await kb_repo.create(KnowledgeBase(id="kb2", name="Two"))
        assert await kb_repo.count() == 2
        await kb_repo.delete("kb1")
        assert await kb_repo.count() == 1


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

    async def test_delete_returns_removed_chunk_ids_and_syncs_fts(
        self,
        conn,
        kb_repo: KnowledgeBaseRepository,
        kb_item_repo: KBItemRepository,
        kb_chunk_repo: KBChunkRepository,
    ) -> None:
        """Flight 2 Leg 2, AC-6: ``KBItemRepository.delete`` now returns the
        chunk ids removed by the FK cascade, and syncs ``kb_chunks_fts``
        for them via the module-level ``_fts_delete_rows`` helper before
        the cascade fires."""
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(KBItem(id="i1", kb_id="kb1", type="file", path_or_url="/a"))
        chunk_ids = await kb_chunk_repo.replace_item_chunks(
            "i1",
            "kb1",
            [ChunkRecord(seq=0, text="zq7xkitemcascade text", char_start=0, char_end=10)],
        )

        removed = await kb_item_repo.delete("i1")

        assert removed == chunk_ids
        async with conn.execute("SELECT COUNT(*) FROM kb_chunks WHERE item_id = 'i1'") as cur:
            assert (await cur.fetchone())[0] == 0
        async with conn.execute(
            "SELECT COUNT(*) FROM kb_chunks_fts WHERE kb_chunks_fts MATCH 'zq7xkitemcascade'"
        ) as cur:
            assert (await cur.fetchone())[0] == 0
        assert await kb_chunk_repo.check_fts() is True

    async def test_cascade_delete_via_kb_also_syncs_chunk_fts(
        self,
        conn,
        kb_repo: KnowledgeBaseRepository,
        kb_item_repo: KBItemRepository,
        kb_chunk_repo: KBChunkRepository,
    ) -> None:
        """Flight 2 Leg 2, AC-6: ``KnowledgeBaseRepository.delete`` syncs
        ``kb_chunks_fts`` for every chunk the FK cascade is about to remove,
        so a subsequent ``check_fts()`` stays ``True``."""
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(KBItem(id="i1", kb_id="kb1", type="file", path_or_url="/a"))
        await kb_chunk_repo.replace_item_chunks(
            "i1", "kb1", [ChunkRecord(seq=0, text="zq7xkkbcascade text", char_start=0, char_end=10)]
        )

        await kb_repo.delete("kb1")

        async with conn.execute("SELECT COUNT(*) FROM kb_chunks") as cur:
            assert (await cur.fetchone())[0] == 0
        async with conn.execute(
            "SELECT COUNT(*) FROM kb_chunks_fts WHERE kb_chunks_fts MATCH 'zq7xkkbcascade'"
        ) as cur:
            assert (await cur.fetchone())[0] == 0
        assert await kb_chunk_repo.check_fts() is True

    async def test_create_writes_all_thirteen_columns(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        item = KBItem(
            id="i1",
            kb_id="kb1",
            parent_id=None,
            type="file",
            path_or_url="/a",
            status="pending",
            error=None,
            content_hash="deadbeef",
            size_bytes=42,
            mtime=1.5,
        )
        await kb_item_repo.create(item)
        loaded = await kb_item_repo.get("i1")
        assert loaded.content_hash == "deadbeef"
        assert loaded.size_bytes == 42
        assert loaded.mtime == 1.5
        assert loaded.status == "pending"
        assert loaded.error is None
        assert loaded.indexed_at is None
        assert loaded.created_at
        assert loaded.updated_at

    async def test_delete_folder_cleans_descendant_chunks_and_fts(
        self,
        conn,
        kb_repo: KnowledgeBaseRepository,
        kb_item_repo: KBItemRepository,
        kb_chunk_repo: KBChunkRepository,
    ) -> None:
        """Flight 3 Leg 1, AC-1: ``KBItemRepository.delete(folder_id)``
        returns every descendant chunk id, leaves zero ``kb_chunks``/
        ``kb_chunks_fts`` rows for the folder and both children, and
        ``check_fts()`` stays ``True``."""
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(
            KBItem(id="folder1", kb_id="kb1", type="folder", path_or_url="/root")
        )
        await kb_item_repo.create(
            KBItem(
                id="child1",
                kb_id="kb1",
                parent_id="folder1",
                type="file",
                path_or_url="/root/a.txt",
            )
        )
        await kb_item_repo.create(
            KBItem(
                id="child2",
                kb_id="kb1",
                parent_id="folder1",
                type="file",
                path_or_url="/root/b.txt",
            )
        )
        ids1 = await kb_chunk_repo.replace_item_chunks(
            "child1",
            "kb1",
            [ChunkRecord(seq=0, text="zq9folderchildone text", char_start=0, char_end=10)],
        )
        ids2 = await kb_chunk_repo.replace_item_chunks(
            "child2",
            "kb1",
            [ChunkRecord(seq=0, text="zq9folderchildtwo text", char_start=0, char_end=10)],
        )

        removed = await kb_item_repo.delete("folder1")

        assert set(removed) == set(ids1) | set(ids2)
        async with conn.execute("SELECT COUNT(*) FROM kb_chunks") as cur:
            assert (await cur.fetchone())[0] == 0
        async with conn.execute(
            "SELECT COUNT(*) FROM kb_chunks_fts WHERE kb_chunks_fts MATCH 'zq9folderchildone'"
        ) as cur:
            assert (await cur.fetchone())[0] == 0
        async with conn.execute(
            "SELECT COUNT(*) FROM kb_chunks_fts WHERE kb_chunks_fts MATCH 'zq9folderchildtwo'"
        ) as cur:
            assert (await cur.fetchone())[0] == 0
        assert await kb_chunk_repo.check_fts() is True
        assert await kb_item_repo.list("kb1") == []


# ── KB Item Repository bulk/listing/requeue surface (Flight 3 Leg 1) ──────


class TestKBItemRepositoryBulkAndListings:
    """AC-2 through AC-4: ``create_many``, ``list_children``,
    ``list_folders``, ``list_by_status``/``count_by_status`` keyword
    filters, ``requeue_stranded``, ``requeue_for_reindex``. Every method's
    first production consumer is Leg 3, so each is unit-tested directly
    here."""

    async def test_create_many_inserts_all_in_one_transaction(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        items = [
            KBItem(id=f"i{n}", kb_id="kb1", type="file", path_or_url=f"/f{n}") for n in range(5)
        ]
        await kb_item_repo.create_many(items)
        listed = await kb_item_repo.list("kb1")
        assert {i.id for i in listed} == {f"i{n}" for n in range(5)}

    async def test_create_many_empty_is_noop(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create_many([])
        assert await kb_item_repo.list("kb1") == []

    async def test_create_many_duplicate_id_rolls_back_whole_batch(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        import sqlite3

        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(KBItem(id="dup", kb_id="kb1", type="file", path_or_url="/x"))
        items = [
            KBItem(id="new1", kb_id="kb1", type="file", path_or_url="/y"),
            KBItem(id="dup", kb_id="kb1", type="file", path_or_url="/z"),
        ]
        with pytest.raises(sqlite3.IntegrityError):
            await kb_item_repo.create_many(items)
        listed = await kb_item_repo.list("kb1")
        assert {i.id for i in listed} == {"dup"}

    async def test_create_many_is_a_single_write_transaction(
        self, monkeypatch, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        """A commit-count spy on ``write_transaction`` proves ``create_many``
        opens exactly one transaction for the whole batch, not one per
        item."""
        import contextlib

        from the_one.db import repositories as repo_module

        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        calls = {"n": 0}
        real_write_transaction = repo_module.write_transaction

        @contextlib.asynccontextmanager
        async def _spy(conn):
            calls["n"] += 1
            async with real_write_transaction(conn):
                yield

        monkeypatch.setattr(repo_module, "write_transaction", _spy)
        items = [
            KBItem(id=f"i{n}", kb_id="kb1", type="file", path_or_url=f"/f{n}") for n in range(10)
        ]
        await kb_item_repo.create_many(items)
        assert calls["n"] == 1

    async def test_list_children_returns_items_with_parent_oldest_first(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(
            KBItem(id="folder1", kb_id="kb1", type="folder", path_or_url="/root")
        )
        await kb_item_repo.create(
            KBItem(id="c1", kb_id="kb1", parent_id="folder1", type="file", path_or_url="/root/a")
        )
        await kb_item_repo.create(
            KBItem(id="c2", kb_id="kb1", parent_id="folder1", type="file", path_or_url="/root/b")
        )
        await kb_item_repo.create(KBItem(id="other", kb_id="kb1", type="file", path_or_url="/z"))
        children = await kb_item_repo.list_children("folder1")
        assert [c.id for c in children] == ["c1", "c2"]

    async def test_list_children_unknown_id_returns_empty(
        self, kb_item_repo: KBItemRepository
    ) -> None:
        assert await kb_item_repo.list_children("nope") == []

    async def test_list_folders_returns_only_folder_type_oldest_first(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(KBItem(id="f1", kb_id="kb1", type="folder", path_or_url="/a"))
        await kb_item_repo.create(KBItem(id="file1", kb_id="kb1", type="file", path_or_url="/a/x"))
        await kb_item_repo.create(KBItem(id="f2", kb_id="kb1", type="folder", path_or_url="/b"))
        folders = await kb_item_repo.list_folders("kb1")
        assert [f.id for f in folders] == ["f1", "f2"]

    async def test_list_by_status_type_filter_and_limit(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(
            KBItem(id="folder1", kb_id="kb1", type="folder", path_or_url="/root", status="pending")
        )
        await kb_item_repo.create(
            KBItem(id="f1", kb_id="kb1", type="file", path_or_url="/a", status="pending")
        )
        await kb_item_repo.create(
            KBItem(id="f2", kb_id="kb1", type="file", path_or_url="/b", status="pending")
        )
        all_pending = await kb_item_repo.list_by_status("kb1", "pending")
        assert {i.id for i in all_pending} == {"folder1", "f1", "f2"}
        only_files = await kb_item_repo.list_by_status("kb1", "pending", type="file")
        assert {i.id for i in only_files} == {"f1", "f2"}
        limited = await kb_item_repo.list_by_status("kb1", "pending", type="file", limit=1)
        assert [i.id for i in limited] == ["f1"]

    async def test_list_by_status_positional_call_unchanged(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(
            KBItem(id="a", kb_id="kb1", type="file", path_or_url="/a", status="pending")
        )
        assert [i.id for i in await kb_item_repo.list_by_status("kb1", "pending")] == ["a"]

    async def test_count_by_status_type_filter(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(
            KBItem(id="folder1", kb_id="kb1", type="folder", path_or_url="/root", status="pending")
        )
        await kb_item_repo.create(
            KBItem(id="f1", kb_id="kb1", type="file", path_or_url="/a", status="pending")
        )
        counts_all = await kb_item_repo.count_by_status("kb1")
        assert counts_all["pending"] == 2
        counts_files = await kb_item_repo.count_by_status("kb1", type="file")
        assert counts_files["pending"] == 1

    async def test_requeue_stranded_scoped_and_unscoped(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_repo.create(KnowledgeBase(id="kb2", name="KB2"))
        await kb_item_repo.create(
            KBItem(
                id="a",
                kb_id="kb1",
                type="file",
                path_or_url="/a",
                status="indexing",
                error="boom",
            )
        )
        await kb_item_repo.create(
            KBItem(id="b", kb_id="kb1", type="folder", path_or_url="/b", status="indexing")
        )
        await kb_item_repo.create(
            KBItem(id="c", kb_id="kb2", type="file", path_or_url="/c", status="indexing")
        )
        await kb_item_repo.create(
            KBItem(id="d", kb_id="kb1", type="file", path_or_url="/d", status="pending")
        )

        n = await kb_item_repo.requeue_stranded(kb_id="kb1")
        assert n == 2
        a = await kb_item_repo.get("a")
        assert a.status == "pending"
        assert a.error is None
        assert (await kb_item_repo.get("b")).status == "pending"
        assert (await kb_item_repo.get("c")).status == "indexing"  # different KB, untouched

        n_all = await kb_item_repo.requeue_stranded()
        assert n_all == 1
        assert (await kb_item_repo.get("c")).status == "pending"

    async def test_requeue_for_reindex_moves_indexed_and_failed_file_only(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_repo.create(KnowledgeBase(id="kb2", name="KB2"))
        await kb_item_repo.create(
            KBItem(id="a", kb_id="kb1", type="file", path_or_url="/a", status="indexed")
        )
        await kb_item_repo.create(
            KBItem(
                id="b",
                kb_id="kb1",
                type="file",
                path_or_url="/b",
                status="failed",
                error="boom",
            )
        )
        await kb_item_repo.create(
            KBItem(id="c", kb_id="kb1", type="file", path_or_url="/c", status="indexing")
        )
        await kb_item_repo.create(
            KBItem(id="d", kb_id="kb1", type="folder", path_or_url="/d", status="indexed")
        )
        await kb_item_repo.create(
            KBItem(id="e", kb_id="kb2", type="file", path_or_url="/e", status="indexed")
        )

        n = await kb_item_repo.requeue_for_reindex("kb1")
        assert n == 2
        assert (await kb_item_repo.get("a")).status == "pending"
        b = await kb_item_repo.get("b")
        assert b.status == "pending"
        assert b.error is None
        assert (await kb_item_repo.get("c")).status == "indexing"
        assert (await kb_item_repo.get("d")).status == "indexed"
        assert (await kb_item_repo.get("e")).status == "indexed"

    async def test_requeue_for_reindex_zero_items_returns_zero_and_commits(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        assert await kb_item_repo.requeue_for_reindex("kb1") == 0


class TestKBItemRepositoryOrdering:
    """Squawk 0087 / Flight 7 Leg 2, AC-13/AC-14: ``list``,
    ``list_children``, ``list_folders`` all gain a ``, path_or_url``
    ASCENDING tiebreak on tied ``created_at`` rows (the common case, not
    the exotic one — a folder walk inserts every discovered file in one
    pass). Every item below shares one explicit ``created_at`` so SQLite
    has no timestamp to sort by at all; only the tiebreak can produce a
    deterministic order."""

    _TIED = "2026-01-01T00:00:00+00:00"

    async def test_list_orders_tied_rows_by_path_ascending_and_repeatably(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        # Inserted in a scrambled order on purpose — a correct result
        # depends on the ORDER BY, not on insertion order happening to
        # already match it.
        for item_id, path in [("c", "/z"), ("a", "/a"), ("b", "/m")]:
            await kb_item_repo.create(
                KBItem(
                    id=item_id,
                    kb_id="kb1",
                    type="file",
                    path_or_url=path,
                    created_at=self._TIED,
                )
            )
        expected = ["a", "b", "c"]
        # "Repeated reads" (leg Verification Steps): the same query run
        # twice must return the identical order both times.
        assert [i.id for i in await kb_item_repo.list("kb1")] == expected
        assert [i.id for i in await kb_item_repo.list("kb1")] == expected

    async def test_list_children_orders_tied_rows_by_path_ascending(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(
            KBItem(id="folder1", kb_id="kb1", type="folder", path_or_url="/root")
        )
        for item_id, path in [("c2", "/root/z"), ("c1", "/root/a")]:
            await kb_item_repo.create(
                KBItem(
                    id=item_id,
                    kb_id="kb1",
                    parent_id="folder1",
                    type="file",
                    path_or_url=path,
                    created_at=self._TIED,
                )
            )
        children = await kb_item_repo.list_children("folder1")
        assert [c.id for c in children] == ["c1", "c2"]

    async def test_list_folders_orders_tied_rows_by_path_ascending(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        for item_id, path in [("f2", "/z"), ("f1", "/a")]:
            await kb_item_repo.create(
                KBItem(
                    id=item_id,
                    kb_id="kb1",
                    type="folder",
                    path_or_url=path,
                    created_at=self._TIED,
                )
            )
        folders = await kb_item_repo.list_folders("kb1")
        assert [f.id for f in folders] == ["f1", "f2"]

    async def test_list_by_status_orders_tied_rows_by_path_and_pages_stably(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        """Squawk 0091: the indexing worker's page fetch must be repeatable."""
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        for item_id, path in [("d", "/q"), ("c", "/z"), ("a", "/a"), ("b", "/m")]:
            await kb_item_repo.create(
                KBItem(
                    id=item_id,
                    kb_id="kb1",
                    type="file",
                    path_or_url=path,
                    status="pending",
                    created_at=self._TIED,
                )
            )
        full = [i.id for i in await kb_item_repo.list_by_status("kb1", "pending")]
        assert full == ["a", "b", "d", "c"]
        for _ in range(2):
            page = await kb_item_repo.list_by_status("kb1", "pending", limit=2)
            assert [i.id for i in page] == ["a", "b"]


# ── KB Item Repository lifecycle (Flight 2 Leg 1, DD-5) ───────────────────


class TestKBItemRepositoryLifecycle:
    """AC-6/AC-7: ``update_status``'s transition table, ``set_content_identity``,
    ``list_by_status``, ``count_by_status``."""

    async def _make_item(
        self,
        kb_repo: KnowledgeBaseRepository,
        kb_item_repo: KBItemRepository,
        *,
        item_id: str = "i1",
        kb_id: str = "kb1",
        status: str = "pending",
    ) -> KBItem:
        if not await self._kb_exists(kb_repo, kb_id):
            await kb_repo.create(KnowledgeBase(id=kb_id, name=kb_id))
        item = KBItem(id=item_id, kb_id=kb_id, type="file", path_or_url="/a", status=status)
        await kb_item_repo.create(item)
        return item

    @staticmethod
    async def _kb_exists(kb_repo: KnowledgeBaseRepository, kb_id: str) -> bool:
        try:
            await kb_repo.get(kb_id)
            return True
        except KeyError:
            return False

    @pytest.mark.parametrize(
        ("start", "target"),
        [
            ("pending", "indexing"),
            ("indexing", "indexed"),
            ("indexing", "failed"),
            ("indexing", "pending"),
            ("failed", "pending"),
            ("indexed", "pending"),
        ],
    )
    async def test_update_status_allowed_transitions(
        self,
        kb_repo: KnowledgeBaseRepository,
        kb_item_repo: KBItemRepository,
        start: str,
        target: str,
    ) -> None:
        await self._make_item(kb_repo, kb_item_repo, status=start)
        updated = await kb_item_repo.update_status("i1", target)
        assert updated.status == target

    async def test_update_status_every_disallowed_pair_raises(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        from the_one.db._kb_types import KB_ITEM_STATUSES

        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        counter = 0
        for start in KB_ITEM_STATUSES:
            for target in KB_ITEM_STATUSES:
                if start in KB_ITEM_TRANSITIONS[target]:
                    continue
                counter += 1
                item_id = f"item-{counter}"
                await kb_item_repo.create(
                    KBItem(id=item_id, kb_id="kb1", type="file", path_or_url="/a", status=start)
                )
                with pytest.raises(KBItemTransitionError):
                    await kb_item_repo.update_status(item_id, target)

    async def test_update_status_unknown_id_raises_keyerror(
        self, kb_item_repo: KBItemRepository
    ) -> None:
        with pytest.raises(KeyError):
            await kb_item_repo.update_status("nope", "indexing")

    async def test_update_status_unknown_target_raises_valueerror(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await self._make_item(kb_repo, kb_item_repo, status="pending")
        with pytest.raises(ValueError):
            await kb_item_repo.update_status("i1", "not-a-status")

    async def test_failed_carries_error_and_clears_on_exit(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await self._make_item(kb_repo, kb_item_repo, status="indexing")
        failed = await kb_item_repo.update_status("i1", "failed", error="boom")
        assert failed.status == "failed"
        assert failed.error == "boom"

        retried = await kb_item_repo.update_status("i1", "pending")
        assert retried.status == "pending"
        assert retried.error is None

    async def test_reaching_indexed_stamps_indexed_at(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await self._make_item(kb_repo, kb_item_repo, status="indexing")
        item = await kb_item_repo.get("i1")
        assert item.indexed_at is None
        indexed = await kb_item_repo.update_status("i1", "indexed")
        assert indexed.indexed_at is not None
        assert indexed.indexed_at == indexed.updated_at

    async def test_every_transition_stamps_updated_at(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        item = await self._make_item(kb_repo, kb_item_repo, status="pending")
        updated = await kb_item_repo.update_status("i1", "indexing")
        assert updated.updated_at  # non-empty: the transition stamped it
        # created_at is untouched by the transition.
        assert updated.created_at == item.created_at

    async def test_set_content_identity(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await self._make_item(kb_repo, kb_item_repo, status="pending")
        await kb_item_repo.set_content_identity(
            "i1", content_hash="abc123", size_bytes=100, mtime=42.0
        )
        item = await kb_item_repo.get("i1")
        assert item.content_hash == "abc123"
        assert item.size_bytes == 100
        assert item.mtime == 42.0

    async def test_list_by_status(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(
            KBItem(id="a", kb_id="kb1", type="file", path_or_url="/a", status="pending")
        )
        await kb_item_repo.create(
            KBItem(id="b", kb_id="kb1", type="file", path_or_url="/b", status="indexed")
        )
        await kb_item_repo.create(
            KBItem(id="c", kb_id="kb1", type="file", path_or_url="/c", status="pending")
        )
        pending = await kb_item_repo.list_by_status("kb1", "pending")
        assert {i.id for i in pending} == {"a", "c"}
        indexed = await kb_item_repo.list_by_status("kb1", "indexed")
        assert {i.id for i in indexed} == {"b"}
        failed = await kb_item_repo.list_by_status("kb1", "failed")
        assert failed == []

    async def test_count_by_status_includes_zeros(
        self, kb_repo: KnowledgeBaseRepository, kb_item_repo: KBItemRepository
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="KB"))
        await kb_item_repo.create(
            KBItem(id="a", kb_id="kb1", type="file", path_or_url="/a", status="pending")
        )
        await kb_item_repo.create(
            KBItem(id="b", kb_id="kb1", type="file", path_or_url="/b", status="pending")
        )
        await kb_item_repo.create(
            KBItem(id="c", kb_id="kb1", type="file", path_or_url="/c", status="indexed")
        )
        counts = await kb_item_repo.count_by_status("kb1")
        assert counts == {"pending": 2, "indexing": 0, "indexed": 1, "failed": 0}


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
        # Mission 23 Flight 2 Leg 1 (DD-2): ``config`` now carries the
        # reserved-key schema (``default_agent``/``channel_map``/
        # ``allowlist``/``always_listen``) — the pre-reset ``"intent"``
        # key this test used is rejected by the new validator.
        account = Connector(
            id="a1", name="Test Bot", type="stub", config={"default_agent": "bot-1"}
        )
        await connector_repo.create(account)
        loaded = await connector_repo.get("a1")
        assert loaded.name == "Test Bot"
        assert loaded.config == {"default_agent": "bot-1"}

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
            config={"default_agent": "bot-1"},
            secrets={"BOT_TOKEN": "discord_secret_value_xyz"},
        )
        await connector_repo.create(account)
        fetched = await connector_repo.get("a1")
        assert fetched.config == {"default_agent": "bot-1"}
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
        account = Connector(id="a1", name="Test", type="stub", config={"default_agent": "bot-1"})
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

    # Mission 23 Flight 1 (backend-removal leg, step 4): the
    # ``idle_timeout_seconds`` bounds validator on ``Connector`` was
    # deleted along with the connector pool it protected — the field
    # is a plain unvalidated int now (round-trip is still covered by
    # the two tests above). The three validator-bounds tests that used
    # to live here are gone with it.


# TestConnectorConfigValidator + TestAllowlistGuildIdRequired (F6 L1b /
# M11 F12 L5) are deleted: Mission 23 Flight 1 (backend-removal leg, step
# 4) removed the ``Connector.config`` reserved-keys validator entirely —
# ``config["pairing"]``/``config["allowlist"]`` shape enforcement, and
# the guild_id-required-on-channels/roles rule it carried, no longer
# exist. Only the ``Connector`` model core survives; see
# ``TestConnectorRepository`` above for its remaining coverage.


# ── Connector Directory Repository (v39, Mission 23 Flight 4 Leg 1) ──────


class TestConnectorDirectoryRepository:
    """AC-3/AC-4/AC-8 coverage: upsert-on-change, exact-match ``get``,
    connector-level search scoping (incl. the breadth test), and the
    ``(connector_id, kind, platform_id)`` PK's peer/channel disambiguation.
    """

    async def test_upsert_then_get(
        self, connector_directory_repo: ConnectorDirectoryRepository
    ) -> None:
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Alice",
            username="alice99",
        )
        entry = await connector_directory_repo.get("c1", "peer", "p1")
        assert entry is not None
        assert entry.display_name == "Alice"
        assert entry.username == "alice99"
        assert entry.thread_id is None

    async def test_get_missing_returns_none(
        self, connector_directory_repo: ConnectorDirectoryRepository
    ) -> None:
        assert await connector_directory_repo.get("c1", "peer", "no-such-id") is None

    async def test_upsert_on_change_skips_identical_write(
        self, connector_directory_repo: ConnectorDirectoryRepository
    ) -> None:
        """The write-per-message guard: a second upsert with the SAME
        display_name+username does not touch ``last_seen`` (asserted via
        the row being byte-identical, not just semantically unchanged —
        a real UPDATE would still be a no-op value-wise but this proves
        the write itself was skipped, not merely idempotent)."""
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Alice",
            username="alice99",
        )
        first = await connector_directory_repo.get("c1", "peer", "p1")
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Alice",
            username="alice99",
        )
        second = await connector_directory_repo.get("c1", "peer", "p1")
        assert second.last_seen == first.last_seen

    async def test_upsert_on_change_writes_when_name_changes(
        self, connector_directory_repo: ConnectorDirectoryRepository
    ) -> None:
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Alice",
            username="alice99",
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Alice B.",
            username="alice99",
        )
        entry = await connector_directory_repo.get("c1", "peer", "p1")
        assert entry.display_name == "Alice B."

    async def test_same_platform_id_as_peer_and_channel_disambiguated_by_kind(
        self, connector_directory_repo: ConnectorDirectoryRepository
    ) -> None:
        """Edge case: Telegram DMs use chat ids that can collide with a
        channel id from the same connector — the ``kind`` column
        disambiguates and the composite PK covers both rows independently."""
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="123",
            thread_id=None,
            display_name="Peer One Two Three",
            username=None,
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="channel",
            platform_id="123",
            thread_id=None,
            display_name="Channel One Two Three",
            username=None,
        )
        peer_entry = await connector_directory_repo.get("c1", "peer", "123")
        channel_entry = await connector_directory_repo.get("c1", "channel", "123")
        assert peer_entry.display_name == "Peer One Two Three"
        assert channel_entry.display_name == "Channel One Two Three"

    async def test_thread_shape_stores_thread_id_alongside_platform_id(
        self, connector_directory_repo: ConnectorDirectoryRepository
    ) -> None:
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="channel",
            platform_id="thread-1",
            thread_id="thread-1",
            display_name="my-thread",
            username=None,
        )
        entry = await connector_directory_repo.get("c1", "channel", "thread-1")
        assert entry.thread_id == "thread-1"

    async def test_search_case_insensitive_substring_over_display_name_and_username(
        self,
        connector_repo: ConnectorRepository,
        connector_directory_repo: ConnectorDirectoryRepository,
    ) -> None:
        await connector_repo.create(
            Connector(id="c1", name="t", type="stub", config={"default_agent": "bot-1"})
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Alice Wonderland",
            username=None,
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p2",
            thread_id=None,
            display_name="Bob",
            username="ALICEFAN",
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p3",
            thread_id=None,
            display_name="Carl",
            username=None,
        )
        results = await connector_directory_repo.search("bot-1", "aLiCe")
        assert {r.platform_id for r in results} == {"p1", "p2"}

    async def test_search_literal_percent_query_matches_only_percent_names(
        self,
        connector_repo: ConnectorRepository,
        connector_directory_repo: ConnectorDirectoryRepository,
    ) -> None:
        """Squawk 0039: a query of ``%`` is a LIKE metacharacter — it must
        be escaped so it matches only names that literally contain
        ``%``, not every row in scope."""
        await connector_repo.create(
            Connector(id="c1", name="t", type="stub", config={"default_agent": "bot-1"})
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="100% Match",
            username=None,
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p2",
            thread_id=None,
            display_name="No Wildcard Here",
            username=None,
        )
        results = await connector_directory_repo.search("bot-1", "%")
        assert {r.platform_id for r in results} == {"p1"}

    async def test_search_literal_underscore_query_matches_only_underscore_names(
        self,
        connector_repo: ConnectorRepository,
        connector_directory_repo: ConnectorDirectoryRepository,
    ) -> None:
        """Squawk 0039: a query of ``_`` is a LIKE single-char wildcard —
        it must be escaped so it matches only names that literally
        contain ``_``, not every row in scope."""
        await connector_repo.create(
            Connector(id="c1", name="t", type="stub", config={"default_agent": "bot-1"})
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="under_score",
            username=None,
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p2",
            thread_id=None,
            display_name="No Wildcard Here",
            username=None,
        )
        results = await connector_directory_repo.search("bot-1", "_")
        assert {r.platform_id for r in results} == {"p1"}

    async def test_search_unbound_agent_returns_empty_not_error(
        self, connector_directory_repo: ConnectorDirectoryRepository
    ) -> None:
        assert await connector_directory_repo.search("no-such-agent", "anything") == []

    async def test_search_bounded_to_ten_newest_first(
        self,
        connector_repo: ConnectorRepository,
        connector_directory_repo: ConnectorDirectoryRepository,
    ) -> None:
        await connector_repo.create(
            Connector(id="c1", name="t", type="stub", config={"default_agent": "bot-1"})
        )
        for i in range(12):
            await connector_directory_repo.upsert(
                connector_id="c1",
                kind="peer",
                platform_id=f"p{i}",
                thread_id=None,
                display_name=f"Match {i}",
                username=None,
            )
        results = await connector_directory_repo.search("bot-1", "match")
        assert len(results) == 10
        # Every upsert commits immediately with its own ``now_iso()`` call
        # in insertion order, so the newest ten are the last-inserted ten.
        assert {r.platform_id for r in results} == {f"p{i}" for i in range(2, 12)}

    async def test_search_scoping_default_agent_positive(
        self,
        connector_repo: ConnectorRepository,
        connector_directory_repo: ConnectorDirectoryRepository,
    ) -> None:
        await connector_repo.create(
            Connector(id="c1", name="t", type="stub", config={"default_agent": "bot-1"})
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Match",
            username=None,
        )
        results = await connector_directory_repo.search("bot-1", "match")
        assert len(results) == 1

    async def test_search_scoping_negative_unbound_agent_on_a_real_connector(
        self,
        connector_repo: ConnectorRepository,
        connector_directory_repo: ConnectorDirectoryRepository,
    ) -> None:
        await connector_repo.create(
            Connector(id="c1", name="t", type="stub", config={"default_agent": "bot-1"})
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Match",
            username=None,
        )
        results = await connector_directory_repo.search("some-other-agent", "match")
        assert results == []

    async def test_search_connector_level_breadth_channel_map_agent_sees_other_channels_and_peers(
        self,
        connector_repo: ConnectorRepository,
        connector_directory_repo: ConnectorDirectoryRepository,
    ) -> None:
        """AC-3's breadth test: the designer ruling is CONNECTOR-level
        scoping, not per-target. An agent bound only via ONE
        ``channel_map`` entry (with a DIFFERENT ``default_agent``) still
        surfaces directory rows from the connector's OTHER channels and
        peers — an accidental per-target filter would fail this test by
        excluding ``ch-other``/``peer-1``."""
        await connector_repo.create(
            Connector(
                id="c1",
                name="t",
                type="stub",
                config={
                    "default_agent": "someone-else",
                    "channel_map": {"ch-mapped": "bot-1"},
                },
            )
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="channel",
            platform_id="ch-other",
            thread_id=None,
            display_name="Other Channel Match",
            username=None,
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="peer-1",
            thread_id=None,
            display_name="Other Peer Match",
            username=None,
        )
        results = await connector_directory_repo.search("bot-1", "match")
        assert {r.platform_id for r in results} == {"ch-other", "peer-1"}

    async def test_search_connector_id_filter_intersects_with_authorization(
        self,
        connector_repo: ConnectorRepository,
        connector_directory_repo: ConnectorDirectoryRepository,
    ) -> None:
        """An out-of-scope ``connector_id`` filter yields empty, never a
        bypass of the authorization scope."""
        await connector_repo.create(
            Connector(id="c1", name="t", type="stub", config={"default_agent": "bot-1"})
        )
        await connector_repo.create(
            Connector(id="c2", name="t2", type="stub", config={"default_agent": "someone-else"})
        )
        await connector_directory_repo.upsert(
            connector_id="c2",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Match",
            username=None,
        )
        results = await connector_directory_repo.search("bot-1", "match", connector_id="c2")
        assert results == []

    async def test_search_includes_connector_name_via_join(
        self,
        connector_repo: ConnectorRepository,
        connector_directory_repo: ConnectorDirectoryRepository,
    ) -> None:
        """Leg 3 (Mission 23 Flight 4, review HIGH fix): ``search``'s JOIN
        enriches each raw row with the connector's plaintext ``name`` — the
        only path to the lookup tool's "connector name included"
        requirement, since this repository holds no encryptor and never
        calls ``ConnectorRepository.get`` per candidate."""
        await connector_repo.create(
            Connector(id="c1", name="Ops Bot", type="stub", config={"default_agent": "bot-1"})
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Match",
            username=None,
        )
        results = await connector_directory_repo.search("bot-1", "match")
        assert len(results) == 1
        assert results[0].connector_name == "Ops Bot"

    async def test_get_does_not_enrich_connector_name(
        self,
        connector_repo: ConnectorRepository,
        connector_directory_repo: ConnectorDirectoryRepository,
    ) -> None:
        """Pin: only ``search``'s JOIN enriches ``connector_name`` — ``get``'s
        exact-match query stays a single-table read (DD-7's session-title
        consumer needs no connector name)."""
        await connector_repo.create(
            Connector(id="c1", name="Ops Bot", type="stub", config={"default_agent": "bot-1"})
        )
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Match",
            username=None,
        )
        entry = await connector_directory_repo.get("c1", "peer", "p1")
        assert entry is not None
        assert entry.connector_name is None

    async def test_delete_for_connector_removes_only_that_connectors_rows(
        self, connector_directory_repo: ConnectorDirectoryRepository
    ) -> None:
        await connector_directory_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Alice",
            username=None,
        )
        await connector_directory_repo.upsert(
            connector_id="c2",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Bob",
            username=None,
        )
        await connector_directory_repo.delete_for_connector("c1")
        assert await connector_directory_repo.get("c1", "peer", "p1") is None
        assert await connector_directory_repo.get("c2", "peer", "p1") is not None


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

    async def test_existing_ids(
        self, agent_store: SQLiteAgentStore, chat_repo: ChatSessionRepository
    ) -> None:
        await agent_store.save(AgentConfig(name="agent1"))
        await chat_repo.create(ChatSession(id="s1", agent_name="agent1"))
        await chat_repo.create(ChatSession(id="s2", agent_name="agent1"))
        assert await chat_repo.existing_ids(["s1", "gone", "s2", "s1", "", None]) == {"s1", "s2"}
        assert await chat_repo.existing_ids([]) == set()
        assert await chat_repo.existing_ids(["gone"]) == set()
        await chat_repo.delete("s1")
        assert await chat_repo.existing_ids(["s1", "s2"]) == {"s2"}
        # more ids than one query's variable budget
        many = [f"x{i}" for i in range(1200)] + ["s2"]
        assert await chat_repo.existing_ids(many) == {"s2"}

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

    # Mission 23 Flight 1 (backend-removal leg, step 4): the
    # ``session_continuation_seconds`` bounds validator on ``Connector``
    # was deleted along with the connector session-continuation resolver
    # it protected — the field is a plain unvalidated int now (round-trip
    # is still covered by the two tests above). The three validator-
    # bounds tests that used to live here are gone with it.


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


# PendingApprovalRepository CRUD coverage is deleted: Mission 23
# Flight 1 (backend-removal leg) deletes ``PendingApprovalRepository``
# itself along with the ``pending_approvals`` table (DD-2).


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

    async def test_delete_removes_a_present_key(
        self, app_metadata_repo: AppMetadataRepository
    ) -> None:
        """AC-11a (Flight 7 Leg 2): ``delete`` did not exist before this
        leg — DD-7's whole cleanup obligation (AC-11) is unsatisfiable
        without it."""
        await app_metadata_repo.set("k", "v")
        await app_metadata_repo.delete("k")
        assert await app_metadata_repo.get("k") is None

    async def test_delete_absent_key_is_a_noop(
        self, app_metadata_repo: AppMetadataRepository
    ) -> None:
        await app_metadata_repo.delete("nope")  # must not raise
        assert await app_metadata_repo.get("nope") is None

    async def test_delete_leaves_other_keys_untouched(
        self, app_metadata_repo: AppMetadataRepository
    ) -> None:
        await app_metadata_repo.set("keep", "1")
        await app_metadata_repo.set("gone", "2")
        await app_metadata_repo.delete("gone")
        assert await app_metadata_repo.get("keep") == "1"
        assert await app_metadata_repo.get("gone") is None


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


# ── AgentExternalCredentialRepository (M21 F03 L01) ───────────────────────


@pytest.fixture
def ext_cred_repo(conn, mcp_repo_encryptor):
    from the_one.db.repositories import AgentExternalCredentialRepository

    return AgentExternalCredentialRepository(conn, mcp_repo_encryptor)


async def _seed_surface_row(mcp_repo, source_id: str) -> None:
    """Create a parent mcp_sources row so the external-credential FK
    resolves."""
    await mcp_repo.create(
        MCPSource(
            id=source_id,
            name="self-configuration",
            type="streamable-http",
            config={"self_configuration": {"agent": "a"}},
            secrets={},
        )
    )


class TestAgentExternalCredentialRepository:
    async def test_create_then_get_is_secret_free(self, ext_cred_repo, mcp_repo) -> None:
        await _seed_surface_row(mcp_repo, "src-1")
        await ext_cred_repo.create(
            source_id="src-1", label="my tool", identifier="id-1", secret="topsecret"
        )
        got = await ext_cred_repo.get("id-1")
        assert got is not None
        assert got["identifier"] == "id-1"
        assert got["source_id"] == "src-1"
        assert got["label"] == "my tool"
        assert "secret" not in got  # secret-free projection (DD2)

    async def test_get_missing_returns_none(self, ext_cred_repo) -> None:
        assert await ext_cred_repo.get("nope") is None

    async def test_secret_encrypted_at_rest(self, ext_cred_repo, mcp_repo, conn) -> None:
        """AC2: the raw stored `secret` column never equals the plaintext;
        `load_all` decrypts it back to the original."""
        await _seed_surface_row(mcp_repo, "src-1")
        plaintext = "a-known-literal-secret-value"
        await ext_cred_repo.create(
            source_id="src-1", label="l", identifier="id-1", secret=plaintext
        )

        async with conn.execute(
            "SELECT secret FROM agent_external_credentials WHERE identifier = 'id-1'"
        ) as cur:
            stored = (await cur.fetchone())["secret"]
        assert stored != plaintext, "secret stored in the clear"
        assert plaintext not in stored

        loaded = await ext_cred_repo.load_all()
        assert loaded == [("id-1", "src-1", plaintext)]

    async def test_list_for_source_is_secret_free(self, ext_cred_repo, mcp_repo) -> None:
        """AC4: list projection carries identifier/label/created_at, never
        the secret."""
        await _seed_surface_row(mcp_repo, "src-1")
        await ext_cred_repo.create(
            source_id="src-1", label="one", identifier="id-1", secret="s3cr3t-literal"
        )
        rows = await ext_cred_repo.list_for_source("src-1")
        assert len(rows) == 1
        assert set(rows[0]) == {"identifier", "label", "created_at"}
        assert "s3cr3t-literal" not in json.dumps(rows)

    async def test_list_for_source_scoped_to_that_source(self, ext_cred_repo, mcp_repo) -> None:
        await _seed_surface_row(mcp_repo, "src-1")
        await _seed_surface_row(mcp_repo, "src-2")
        await ext_cred_repo.create(source_id="src-1", label="a", identifier="id-a", secret="x")
        await ext_cred_repo.create(source_id="src-2", label="b", identifier="id-b", secret="y")
        ids = {r["identifier"] for r in await ext_cred_repo.list_for_source("src-1")}
        assert ids == {"id-a"}

    async def test_delete_returns_bool_and_is_idempotent(self, ext_cred_repo, mcp_repo) -> None:
        await _seed_surface_row(mcp_repo, "src-1")
        await ext_cred_repo.create(source_id="src-1", label="l", identifier="id-1", secret="x")
        assert await ext_cred_repo.delete("id-1") is True
        assert await ext_cred_repo.delete("id-1") is False
        assert await ext_cred_repo.get("id-1") is None


# ── SQLiteAgentStore.compare_and_set_field (M21 F03 L02 — AC5/AC6/DD5) ────


class TestCompareAndSetField:
    """The field-scoped compare-and-swap that closes the direct-write clobber."""

    async def test_cas_hit_writes_only_that_field_and_returns_true(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        await agent_store.save(AgentConfig(name="a", description="d0", system_prompt="s0"))
        ok = await agent_store.compare_and_set_field("a", "description", "d0", "d1")
        assert ok is True
        after = await agent_store.load("a")
        assert after.description == "d1"
        assert after.system_prompt == "s0"  # the other field is untouched

    async def test_cas_miss_on_drift_returns_false_and_writes_nothing(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        await agent_store.save(AgentConfig(name="a", description="current"))
        # base_value no longer matches the stored value → no row updated.
        ok = await agent_store.compare_and_set_field("a", "description", "stale-base", "mine")
        assert ok is False
        assert (await agent_store.load("a")).description == "current"  # untouched

    async def test_cas_does_not_clobber_concurrent_other_field_write(
        self, agent_store: SQLiteAgentStore, conn
    ) -> None:
        # AC5 — capture base_value for description, let a concurrent whole-row
        # writer change the OTHER field (system_prompt), then run the CAS on
        # description; the concurrent change to system_prompt must survive
        # (the CAS writes only the one column).
        await agent_store.save(AgentConfig(name="a", description="d0", system_prompt="s0"))
        base_value = (await agent_store.load("a")).description  # 'd0'

        # Concurrent whole-row write to the OTHER field between capture and CAS.
        concurrent = (await agent_store.load("a")).model_copy(
            update={"system_prompt": "s1-concurrent"}
        )
        await agent_store.save(concurrent)

        ok = await agent_store.compare_and_set_field("a", "description", base_value, "d1")
        assert ok is True
        after = await agent_store.load("a")
        assert after.description == "d1"  # the CAS applied
        assert after.system_prompt == "s1-concurrent"  # concurrent change NOT clobbered

    async def test_cas_rejects_field_not_in_whitelist(self, agent_store: SQLiteAgentStore) -> None:
        # The column name is interpolated; a non-whitelisted field must never
        # reach the SQL (defense in depth alongside the tool-boundary Literal).
        # A ValueError (not an assert) enforces this so the guard survives
        # ``python -O``.
        await agent_store.save(AgentConfig(name="a"))
        with pytest.raises(ValueError):
            await agent_store.compare_and_set_field("a", "llm_model", "x", "y")


# ── AgentRevision provenance touch-points (M21 F03 L02 — AC7/DD3) ─────────


class TestAgentRevisionProvenance:
    async def test_row_to_model_roundtrips_external_row(self, agent_revision_repo, conn) -> None:
        # AC7 — an external row round-trips through _row_to_model into an
        # AgentRevision without error (the widened Literal admits 'external').
        await _seed_agent_row(conn, "a")
        row = await agent_revision_repo.append(
            agent_name="a",
            field="description",
            proposed_value="p",
            base_value="b",
            source="external",
            source_principal="ext_abc",
            status="applied",
            restored_from=None,
            created_at="2026-08-27T00:00:00+00:00",
            resolved_at="2026-08-27T00:00:00+00:00",
        )
        assert row.source == "external"
        assert row.source_principal == "ext_abc"
        fetched = await agent_revision_repo.get(row.id)
        assert fetched == row
        # list_for_agent returns it with provenance intact.
        listed = await agent_revision_repo.list_for_agent("a")
        assert listed[0].source == "external"
        assert listed[0].source_principal == "ext_abc"

    async def test_append_defaults_source_principal_to_null(
        self, agent_revision_repo, conn
    ) -> None:
        await _seed_agent_row(conn, "a")
        row = await _append_applied(agent_revision_repo, "a")
        assert row.source == "self"
        assert row.source_principal is None

    async def test_repropose_by_different_principal_updates_provenance(
        self, agent_revision_repo, conn
    ) -> None:
        # AC7 — a re-propose of the same (agent, field) pending row by a
        # DIFFERENT principal updates source/source_principal on the deduped
        # row (the UPDATE branch of upsert_pending_revision, not just insert).
        await _seed_agent_row(conn, "a")
        first, created1 = await agent_revision_repo.upsert_pending_revision(
            agent_name="a",
            field="description",
            proposed_value="p1",
            base_value="b1",
            source="self",
            source_principal=None,
        )
        assert created1 is True
        assert first.source == "self"
        assert first.source_principal is None

        second, created2 = await agent_revision_repo.upsert_pending_revision(
            agent_name="a",
            field="description",
            proposed_value="p2",
            base_value="b2",
            source="external",
            source_principal="ext_new",
        )
        assert created2 is False  # deduped onto the same row
        assert second.id == first.id
        assert second.source == "external"
        assert second.source_principal == "ext_new"
        assert second.proposed_value == "p2"
        # Still exactly one pending row for the pair.
        assert await agent_revision_repo.count_pending("a") == 1
