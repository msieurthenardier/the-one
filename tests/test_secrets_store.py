"""Secrets storage (sortie 10, leg 1): the repository, agent grants, the refused set,
the MCP-rename carry and the eighth encrypted corpus."""

from __future__ import annotations

import json
import logging
import subprocess
import sys

import pytest
from cryptography.fernet import Fernet

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.encryption_corpora import count_items_with_secrets, gather_corpora
from the_one.db.models import MCPSource
from the_one.db.repositories import (
    SECRET_MASK,
    MCPSourceRepository,
    SecretInvalid,
    SecretNameConflict,
    SecretRepository,
    SQLiteAgentStore,
)
from the_one.encryption import Encryptor
from the_one.mcp.rename_references import carry_mcp_rename_into_secrets
from the_one.secret_store.refused import is_refused_tool

PLAIN_A = "p4ss\"wo'rd\\1"
PLAIN_B = "second-value-12345"


@pytest.fixture
async def conn(tmp_path):
    c = await connect_template_db(tmp_path / "t.db")
    yield c
    await c.close()


@pytest.fixture
def encryptor():
    return Encryptor(Fernet.generate_key())


@pytest.fixture
def repo(conn, encryptor):
    return SecretRepository(conn, encryptor)


async def _make(repo, name="Home", tools=("write_file",), pairs=None):
    pairs = pairs or [{"key": "a", "value": PLAIN_A}, {"key": "b", "value": PLAIN_B}]
    return await repo.create(name, "desc", list(tools), pairs)


class TestRepository:
    async def test_create_get_list_never_decrypt_or_return_values(self, repo, conn) -> None:
        s = await _make(repo)
        assert [v.key for v in s.values] == ["a", "b"]
        assert len(s.id) == 32
        assert not hasattr(s.values[0], "value")
        assert (await repo.get(s.id)).values == s.values
        assert [x.id for x in await repo.list()] == [s.id]
        async with conn.execute("SELECT value FROM secret_values") as cur:
            stored = [r[0] for r in await cur.fetchall()]
        assert all(PLAIN_A not in v and PLAIN_B not in v for v in stored)

    async def test_get_values_decrypts_in_position_order(self, repo) -> None:
        s = await _make(repo)
        assert await repo.get_values(s.id) == [("a", PLAIN_A), ("b", PLAIN_B)]
        assert await repo.all_values() == [(s.id, "a", PLAIN_A), (s.id, "b", PLAIN_B)]

    async def test_name_unique_ignoring_case(self, repo) -> None:
        await _make(repo, name="Home address")
        with pytest.raises(SecretNameConflict):
            await _make(repo, name="home ADDRESS", pairs=[{"key": "z", "value": "zz"}])

    async def test_rename_to_own_name_in_another_case_allowed(self, repo) -> None:
        s = await _make(repo, name="Home")
        updated = await repo.update(s.id, name="HOME")
        assert updated.name == "HOME"

    async def test_key_owned_by_another_secret_is_refused_on_create_and_update(self, repo) -> None:
        await _make(repo, name="One", pairs=[{"key": "Shared", "value": "v1v1"}])
        with pytest.raises(SecretInvalid) as exc:
            await repo.create(
                "Two", "", ["t"], [{"key": "ok", "value": "x"}, {"key": "SHARED", "value": "y"}]
            )
        assert exc.value.details[0]["loc"] == ["values", 1, "key"]
        two = await repo.create("Two", "", ["t"], [{"key": "mine", "value": "y"}])
        with pytest.raises(SecretInvalid) as exc:
            await repo.update(two.id, values=[{"key": "shared", "value": "y"}])
        assert exc.value.details[0]["loc"] == ["values", 0, "key"]
        assert [v.key for v in (await repo.get(two.id)).values] == ["mine"]

    async def test_update_keep_replace_delete_reorder_rename_swap(self, repo) -> None:
        s = await _make(repo)
        a, b = s.values
        # keep a (masked), replace b, add c
        s2 = await repo.update(
            s.id,
            values=[
                {"id": a.id, "key": "a", "value": SECRET_MASK},
                {"id": b.id, "key": "b", "value": "new-b-value"},
                {"key": "c", "value": "c-value"},
            ],
        )
        assert [v.key for v in s2.values] == ["a", "b", "c"]
        assert await repo.get_values(s.id) == [
            ("a", PLAIN_A),
            ("b", "new-b-value"),
            ("c", "c-value"),
        ]
        ids = {v.key: v.id for v in s2.values}
        assert ids["a"] == a.id  # a kept pair keeps its id
        # reorder + delete b + key rename with kept value
        s3 = await repo.update(
            s.id,
            values=[
                {"id": ids["c"], "key": "c", "value": SECRET_MASK},
                {"id": ids["a"], "key": "renamed", "value": SECRET_MASK},
            ],
        )
        assert [v.key for v in s3.values] == ["c", "renamed"]
        assert await repo.get_values(s.id) == [("c", "c-value"), ("renamed", PLAIN_A)]
        # two-key swap in one update
        c, r = s3.values
        s4 = await repo.update(
            s.id,
            values=[
                {"id": c.id, "key": "renamed", "value": SECRET_MASK},
                {"id": r.id, "key": "c", "value": SECRET_MASK},
            ],
        )
        assert await repo.get_values(s.id) == [("renamed", "c-value"), ("c", PLAIN_A)]
        assert [v.key for v in s4.values] == ["renamed", "c"]

    async def test_masked_with_foreign_or_missing_id_is_refused_and_nothing_written(
        self, repo
    ) -> None:
        s = await _make(repo, name="One")
        other = await _make(repo, name="Two", pairs=[{"key": "x", "value": "xval-1"}])
        with pytest.raises(SecretInvalid) as exc:
            await repo.update(
                s.id, values=[{"id": other.values[0].id, "key": "a", "value": SECRET_MASK}]
            )
        assert exc.value.details[0]["loc"] == ["values", 0, "value"]
        with pytest.raises(SecretInvalid):
            await repo.update(s.id, values=[{"key": "a", "value": SECRET_MASK}])
        assert await repo.get_values(s.id) == [("a", PLAIN_A), ("b", PLAIN_B)]

    async def test_partial_update_keeps_omitted_fields(self, repo) -> None:
        s = await _make(repo)
        u = await repo.update(s.id, description="new")
        assert (u.name, u.allowed_tools, [v.key for v in u.values]) == (
            "Home",
            ["write_file"],
            ["a", "b"],
        )
        assert await repo.get_values(s.id) == [("a", PLAIN_A), ("b", PLAIN_B)]

    async def test_update_unknown_is_keyerror(self, repo) -> None:
        with pytest.raises(KeyError):
            await repo.update("nope", description="x")
        with pytest.raises(KeyError):
            await repo.delete("nope")

    async def test_delete_cascades_values_and_scrubs_grants_in_one_transaction(
        self, repo, conn, encryptor
    ) -> None:
        s = await _make(repo)
        keep = await _make(repo, name="Keep", pairs=[{"key": "k", "value": "kval-1"}])
        store = SQLiteAgentStore(conn, encryptor)
        await store.save(AgentConfig(name="a1", secret_ids=[keep.id, s.id]))
        await store.save(AgentConfig(name="a2", secret_ids=[s.id]))
        await store.save(AgentConfig(name="a3", secret_ids=[keep.id]))
        async with conn.execute("SELECT updated_at FROM agents WHERE name = 'a1'") as cur:
            before = (await cur.fetchone())[0]
        scrubbed = await repo.delete(s.id)
        assert scrubbed == ["a1", "a2"]
        assert (await store.load("a1")).secret_ids == [keep.id]  # order of the rest kept
        assert (await store.load("a2")).secret_ids == []
        assert (await store.load("a3")).secret_ids == [keep.id]
        async with conn.execute("SELECT updated_at FROM agents WHERE name = 'a1'") as cur:
            assert (await cur.fetchone())[0] == before  # no bump
        async with conn.execute(
            "SELECT COUNT(*) FROM secret_values WHERE secret_id = ?", (s.id,)
        ) as cur:
            assert (await cur.fetchone())[0] == 0  # foreign_keys=ON cascade
        assert await repo.get(s.id) is None

    async def test_exists_many(self, repo) -> None:
        s = await _make(repo)
        assert await repo.exists_many([s.id, "ghost"]) == {s.id}
        assert await repo.exists_many([]) == set()


class TestAgentGrants:
    async def test_round_trip_and_list_by_secret(self, conn, encryptor) -> None:
        store = SQLiteAgentStore(conn, encryptor)
        await store.save(AgentConfig(name="a", secret_ids=["s1", "s2"]))
        await store.save(AgentConfig(name="b", secret_ids=["s2"]))
        await store.save(AgentConfig(name="c"))
        assert (await store.load("a")).secret_ids == ["s1", "s2"]
        assert (await store.load("c")).secret_ids == []
        assert await store.list_by_secret("s2") == ["a", "b"]
        assert await store.list_by_secret("s") == []  # not a substring match


class TestRefusedSet:
    def test_predicate(self) -> None:
        from the_one.agent import tool_names
        from the_one.self_configuration.constants import SURFACE_TOOL_PREFIX

        for name in ("send_to_platform_channel", "continue", "search_tools"):
            assert is_refused_tool(name)
        for name in (*tool_names.NOTES_TOOL_NAMES, *tool_names.ROUTINE_TOOL_NAMES):
            assert is_refused_tool(name)
        assert is_refused_tool(SURFACE_TOOL_PREFIX + "update_my_description")
        assert not is_refused_tool("write_file")
        assert not is_refused_tool("mcp__goldfinch__typeText")
        assert not is_refused_tool("current_time")

    def test_every_notes_and_routine_name_in_tool_names_is_refused(self) -> None:
        from the_one.agent import tool_names

        names: set[str] = set()
        for attr in tool_names.__all__:
            if attr == "CURRENT_TIME_TOOL_NAME":
                continue
            value = getattr(tool_names, attr)
            names |= {value} if isinstance(value, str) else set(value)
        assert names
        missed = {n for n in names if not is_refused_tool(n)}
        assert not missed, f"tool_names gained names the refused set misses: {missed}"

    def test_importing_refused_in_a_fresh_interpreter_pulls_in_no_agent_package(self) -> None:
        code = (
            "import sys, the_one.secret_store.refused;"
            "assert 'the_one.agent' not in sys.modules, 'agent imported at load';"
            "from the_one.secret_store.refused import is_refused_tool;"
            "assert is_refused_tool('save_note');"
            "print('ok')"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == "ok"


class TestRenameCarry:
    async def _setup(self, conn, encryptor, repo, old="Gold finch"):
        mcp = MCPSourceRepository(conn, encryptor)
        src = MCPSource(id="src1", name=old, type="stdio", config={"command": "x"})
        await mcp.create(src)
        await _make(
            repo,
            tools=("mcp__Gold_finch__typeText", "write_file", "mcp__Other__t"),
        )
        return mcp, src

    async def test_entries_move_and_other_entries_stay(self, conn, encryptor, repo) -> None:
        mcp, src = await self._setup(conn, encryptor, repo)
        await mcp.update(src.model_copy(update={"name": "Goldfinch"}))
        await carry_mcp_rename_into_secrets(
            "Gold finch", "Goldfinch", secret_repo=repo, mcp_repo=mcp
        )
        (s,) = await repo.list()
        assert s.allowed_tools == ["mcp__Goldfinch__typeText", "write_file", "mcp__Other__t"]

    async def test_dedup_keeps_first(self, conn, encryptor, repo) -> None:
        mcp, src = await self._setup(conn, encryptor, repo)
        (s,) = await repo.list()
        await repo.update(
            s.id,
            allowed_tools=["mcp__Goldfinch__typeText", "mcp__Gold_finch__typeText", "write_file"],
        )
        await mcp.update(src.model_copy(update={"name": "Goldfinch"}))
        await carry_mcp_rename_into_secrets(
            "Gold finch", "Goldfinch", secret_repo=repo, mcp_repo=mcp
        )
        assert (await repo.list())[0].allowed_tools == ["mcp__Goldfinch__typeText", "write_file"]

    async def test_noop_when_the_normalised_prefix_is_unchanged(
        self, conn, encryptor, repo
    ) -> None:
        mcp, src = await self._setup(conn, encryptor, repo)
        await mcp.update(src.model_copy(update={"name": "Gold_finch"}))
        await carry_mcp_rename_into_secrets(
            "Gold finch", "Gold_finch", secret_repo=repo, mcp_repo=mcp
        )
        assert (await repo.list())[0].allowed_tools[0] == "mcp__Gold_finch__typeText"

    async def test_noop_when_another_source_still_has_the_old_name(
        self, conn, encryptor, repo
    ) -> None:
        mcp, src = await self._setup(conn, encryptor, repo)
        await mcp.create(
            MCPSource(id="src2", name="Gold finch", type="stdio", config={"command": "y"})
        )
        await mcp.update(src.model_copy(update={"name": "Renamed"}))
        await carry_mcp_rename_into_secrets("Gold finch", "Renamed", secret_repo=repo, mcp_repo=mcp)
        assert (await repo.list())[0].allowed_tools[0] == "mcp__Gold_finch__typeText"

    async def test_never_raises_and_warns(self, conn, encryptor, repo, caplog) -> None:
        class Boom:
            async def list(self):
                raise RuntimeError("db down")

        with caplog.at_level(logging.WARNING):
            await carry_mcp_rename_into_secrets("a", "b", secret_repo=repo, mcp_repo=Boom())
        assert any(
            "failed to carry the rename into secrets" in r.getMessage() for r in caplog.records
        )


class TestCorpus:
    async def test_gather_decrypts_and_count_is_per_secret(self, conn, encryptor, repo) -> None:
        await _make(repo, name="One")
        await _make(repo, name="Two", pairs=[{"key": "x", "value": "xval-1"}])
        c = await gather_corpora(conn, encryptor, strict=True)
        assert sorted(v for _, v in c.secret_values) == sorted([PLAIN_A, PLAIN_B, "xval-1"])
        assert count_items_with_secrets(c) == 2

    async def test_rotation_reencrypts_and_the_value_still_decrypts(
        self, tmp_path, conn, encryptor, repo
    ) -> None:
        from unittest.mock import patch

        from httpx import ASGITransport, AsyncClient

        from tests._api_app import shared_app
        from tests._credential_helpers import auth_headers

        key_path = tmp_path / "k.key"
        key_path.write_bytes(encryptor._key)
        enc = Encryptor(encryptor._key, key_path=key_path)
        repo = SecretRepository(conn, enc)
        s = await _make(repo)
        async with conn.execute("SELECT value FROM secret_values ORDER BY position") as cur:
            before = [r[0] for r in await cur.fetchall()]
        with (
            patch("the_one.interfaces.web.api.get_connection", return_value=conn),
            patch("the_one.interfaces.web.api.get_encryptor", return_value=enc),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=shared_app()),
                base_url="http://t",
                headers=auth_headers(),
            ) as client:
                resp = await client.post("/api/encryption/rotate")
        assert resp.status_code == 200, resp.text
        async with conn.execute("SELECT value FROM secret_values ORDER BY position") as cur:
            after = [r[0] for r in await cur.fetchall()]
        assert after != before
        # the installed key is the new one; the repository's internal read decrypts
        assert await repo.get_values(s.id) == [("a", PLAIN_A), ("b", PLAIN_B)]
        assert json.dumps(after).find(PLAIN_B) == -1
