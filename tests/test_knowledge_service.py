"""The knowledge-base write service and its repository hooks (Mission 36 F5 L3a, DD3, DD5).

``update_in_txn`` (the row is read inside the write transaction: the lost-update race the old
PUT had), ``create`` / ``replace`` / ``change`` in ``the_one/knowledge/service.py``, the rename
carry, and the import boundary.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db import _write_lock
from the_one.db._write_lock import write_transaction
from the_one.db.models import KnowledgeBase
from the_one.db.repositories import KnowledgeBaseRepository, SQLiteAgentStore
from the_one.encryption import get_encryptor
from the_one.knowledge import service as svc

ROOT = Path(__file__).resolve().parent.parent

OLD_TOOL = "kb__Docs_old_ef7a30aa__search"
NEW_TOOL = "kb__Docs_new_ef7a30aa__search"


@pytest.fixture
async def world(tmp_path):
    _write_lock.reset_for_test()
    conn = await connect_template_db(tmp_path / "kb.db")
    repo = KnowledgeBaseRepository(conn)
    store = SQLiteAgentStore(conn, get_encryptor(tmp_path))
    calls = SimpleNamespace(warm_up=0, store=0)

    async def agent_store():
        calls.store += 1
        return store

    def warm_up():
        calls.warm_up += 1

    await repo.create(KnowledgeBase(id="kb1", name="Docs old", description="Company docs"))
    deps = svc.KbWriteDeps(repo=repo, agent_store=agent_store, warm_up=warm_up)
    yield SimpleNamespace(conn=conn, repo=repo, store=store, deps=deps, calls=calls)
    await conn.close()


# --- the import boundary --------------------------------------------------------------------


def test_the_service_imports_no_interface_layer_and_no_repository_at_module_level() -> None:
    tree = ast.parse((ROOT / "the_one" / "knowledge" / "service.py").read_text())
    banned = ("fastapi", "starlette", "the_one.interfaces", "the_one.gleepglorp")
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        assert not any(n == b or n.startswith(b + ".") for n in names for b in banned), names
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert "repositories" not in (getattr(node, "module", "") or ""), node.lineno


# --- create -------------------------------------------------------------------------------


async def test_create_generates_an_id_writes_the_row_and_schedules_the_warm_up(world) -> None:
    kb = await svc.create_knowledge_base(world.deps, {"name": "  Notes  ", "description": "d"})
    assert len(kb.id) == 12 and kb.name == "Notes"
    assert (await world.repo.get(kb.id)).description == "d"
    assert world.calls.warm_up == 1


async def test_create_refuses_a_bad_name_and_a_path_like_client_id_with_the_route_details(
    world,
) -> None:
    with pytest.raises(svc.KbWriteError) as e:
        await svc.create_knowledge_base(world.deps, {"name": "   "})
    assert e.value.status == 422 and e.value.detail[0]["loc"] == ["name"]
    with pytest.raises(svc.KbWriteError) as e:
        await svc.create_knowledge_base(world.deps, {"name": "ok", "id": "../../evil"})
    assert e.value.status == 422 and list(e.value.detail[0]["loc"]) == ["id"]
    assert world.calls.warm_up == 0
    assert [k.id for k in await world.repo.list()] == ["kb1"]


async def test_create_on_commit_rides_the_transaction_and_a_raise_rolls_back(world) -> None:
    seen: list[bool] = []

    async def mark(conn) -> None:
        seen.append(True)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await svc.create_knowledge_base(world.deps, {"name": "New", "id": "k2"}, on_commit=mark)
    assert seen == [True]
    assert [k.id for k in await world.repo.list()] == ["kb1"]


# --- replace (the PUT) ----------------------------------------------------------------------


async def test_replace_an_unknown_id_is_not_found_with_the_routes_sentence(world) -> None:
    with pytest.raises(svc.KbNotFound) as e:
        await svc.replace_knowledge_base(world.deps, "nope", {"name": "x"})
    assert str(e.value) == "Knowledge base not found: nope"


async def test_replace_returns_the_stored_row_including_updated_at(world) -> None:
    after = await svc.replace_knowledge_base(world.deps, "kb1", {"description": "new"})
    stored = await world.repo.get("kb1")
    assert after.description == "new" and after.updated_at == stored.updated_at


async def test_replace_refuses_a_bad_name_with_a_422_and_writes_nothing(world) -> None:
    with pytest.raises(svc.KbWriteError) as e:
        await svc.replace_knowledge_base(world.deps, "kb1", {"name": " "})
    assert e.value.status == 422
    assert (await world.repo.get("kb1")).name == "Docs old"


async def _wait_for_waiter(task) -> None:
    """Yield until ``task`` is blocked on the write lock the test holds."""
    for _ in range(400):
        if task.done():
            raise AssertionError("the write finished without waiting for the lock")
        if getattr(_write_lock._lock, "_waiters", None):
            return
        await asyncio.sleep(0.005)
    raise AssertionError("the write never reached the lock")


async def test_a_name_only_put_keeps_a_description_committed_while_it_waited(world) -> None:
    """The old PUT read the row outside the write and wrote it back whole: a description
    committed while it waited for the lock was lost. The row is now read under the lock."""
    async with write_transaction(world.conn):
        task = asyncio.create_task(
            svc.replace_knowledge_base(world.deps, "kb1", {"name": "Docs renamed"})
        )
        await _wait_for_waiter(task)
        await world.conn.execute("UPDATE knowledge_bases SET description='X' WHERE id='kb1'")
    after = await task
    stored = await world.repo.get("kb1")
    assert stored.name == "Docs renamed" and stored.description == "X"
    assert after.description == "X" and after.updated_at == stored.updated_at


# --- change (a proposal) --------------------------------------------------------------------


async def test_change_merges_the_named_fields_and_returns_the_row(world) -> None:
    after = await svc.change_knowledge_base(
        world.deps, "kb1", {"description": "Fresh"}, base={"description": "Company docs"}
    )
    assert after.description == "Fresh" and after.name == "Docs old"
    assert (await world.repo.get("kb1")).description == "Fresh"
    assert world.calls.store == 0  # no rename: no agent is examined


async def test_change_with_a_stale_base_raises_and_writes_nothing_and_override_applies(
    world,
) -> None:
    await world.conn.execute("UPDATE knowledge_bases SET description='Moved' WHERE id='kb1'")
    await world.conn.commit()
    with pytest.raises(svc.KbStaleError) as e:
        await svc.change_knowledge_base(
            world.deps, "kb1", {"description": "Mine"}, base={"description": "Company docs"}
        )
    assert e.value.fields == [{"field": "description", "current": "Moved", "proposed": "Mine"}]
    assert (await world.repo.get("kb1")).description == "Moved"
    await svc.change_knowledge_base(
        world.deps, "kb1", {"description": "Mine"}, base={"description": "Company docs"},
        override=True,
    )  # fmt: skip
    assert (await world.repo.get("kb1")).description == "Mine"


async def test_a_stale_base_is_read_inside_the_transaction(world) -> None:
    """The base is compared on the row read under the lock, not an earlier one."""
    async with write_transaction(world.conn):
        task = asyncio.create_task(
            svc.change_knowledge_base(
                world.deps, "kb1", {"name": "Docs new"}, base={"name": "Docs old"}
            )
        )
        await _wait_for_waiter(task)
        await world.conn.execute("UPDATE knowledge_bases SET name='Hand edit' WHERE id='kb1'")
    with pytest.raises(svc.KbStaleError):
        await task
    assert (await world.repo.get("kb1")).name == "Hand edit"


async def test_change_an_unknown_id_is_a_typed_not_found_not_a_bare_key_error(world) -> None:
    with pytest.raises(svc.KbNotFound):
        await svc.change_knowledge_base(world.deps, "nope", {"name": "x"}, base={})


async def test_change_on_commit_rides_the_transaction_and_a_raise_rolls_back(world) -> None:
    async def mark(conn) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await svc.change_knowledge_base(
            world.deps, "kb1", {"description": "Z"}, base={"description": "Company docs"},
            on_commit=mark,
        )  # fmt: skip
    assert (await world.repo.get("kb1")).description == "Company docs"


# --- the rename carry -----------------------------------------------------------------------


async def test_a_rename_carries_into_attached_agents_disabled_tools_after_the_commit(
    world,
) -> None:
    await world.store.save(AgentConfig(name="a1", kb_ids=["kb1"], disabled_tools=[OLD_TOOL, "x"]))
    await world.store.save(AgentConfig(name="a2", kb_ids=[], disabled_tools=[OLD_TOOL]))
    await svc.change_knowledge_base(
        world.deps, "kb1", {"name": "Docs new"}, base={"name": "Docs old"}
    )
    assert (await world.store.load("a1")).disabled_tools == [NEW_TOOL, "x"]
    assert (await world.store.load("a2")).disabled_tools == [OLD_TOOL]  # not attached


async def test_a_put_rename_carries_too(world) -> None:
    await world.store.save(AgentConfig(name="a1", kb_ids=["kb1"], disabled_tools=[OLD_TOOL]))
    await svc.replace_knowledge_base(world.deps, "kb1", {"name": "Docs new"})
    assert (await world.store.load("a1")).disabled_tools == [NEW_TOOL]


async def test_a_description_only_write_never_examines_an_agent(world) -> None:
    await svc.replace_knowledge_base(world.deps, "kb1", {"description": "d2"})
    assert world.calls.store == 0
