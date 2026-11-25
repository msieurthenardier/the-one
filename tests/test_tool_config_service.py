"""The tool-config write service and its repository hook (Mission 36 F5 L4a, DD3, DD7).

``ToolConfigRepository.update_in_txn`` (the row is read inside the write transaction: the
lost-update race the old PUT had), ``replace`` / ``change`` / ``preview_impact`` in
``the_one/tools/config_service.py``, the secret-preserving merge, and the import boundary.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests._schema_template import connect_template_db
from the_one.db import _write_lock
from the_one.db._write_lock import write_transaction
from the_one.db.repositories import SQLiteAgentStore, ToolConfigRepository
from the_one.encryption import get_encryptor
from the_one.tools import config_service as svc

ROOT = Path(__file__).resolve().parent.parent

KEYS = {
    "google_pse_api_key": "pse-key-AAAAAAAAAAAA",
    "brave_api_key": "brave-key-BBBBBBBBBBB",
    "tavily_api_key": "tavily-key-CCCCCCCCCC",
}


@pytest.fixture
async def world(tmp_path):
    _write_lock.reset_for_test()
    conn = await connect_template_db(tmp_path / "tc.db")
    enc = get_encryptor(tmp_path)
    repo = ToolConfigRepository(conn, enc)
    store = SQLiteAgentStore(conn, enc)

    async def agent_store():
        return store

    deps = svc.ToolConfigWriteDeps(repo=repo, agent_store=agent_store)
    yield SimpleNamespace(conn=conn, enc=enc, repo=repo, store=store, deps=deps)
    await conn.close()


async def _raw(world, name):
    async with world.conn.execute(
        "SELECT config, enabled FROM tool_configs WHERE name = ?", (name,)
    ) as cur:
        return await cur.fetchone()


# --- the import boundary --------------------------------------------------------------------


def test_the_service_imports_no_interface_layer_and_no_repository_at_module_level() -> None:
    tree = ast.parse((ROOT / "the_one" / "tools" / "config_service.py").read_text())
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


def test_the_moved_helpers_keep_their_old_names_in_the_api_module() -> None:
    from the_one.interfaces.web import api

    assert api._merge_hidden_fields is svc.merge_hidden_fields
    assert api._secret_field_names is svc.secret_field_names
    assert api._narrowing_added is svc.narrowing_added
    assert api._impact_of is svc.impact_of


# --- update_in_txn ----------------------------------------------------------------------------


async def test_update_in_txn_creates_a_missing_row_and_reports_no_before(world) -> None:
    seen = []

    def mutate(current):
        seen.append(current)
        from the_one.db.models import ToolConfig

        return ToolConfig(name="shell", config={"timeout_seconds_max": 60}, enabled=False)

    before, after = await world.repo.update_in_txn("shell", mutate)
    assert seen == [None] and before is None
    assert after.enabled is False
    stored = await world.repo.get("shell")
    assert stored.config == {"timeout_seconds_max": 60} and stored.enabled is False


async def test_a_raise_from_mutate_or_on_commit_rolls_the_write_back(world) -> None:
    await world.repo.upsert("shell", {"timeout_seconds_max": 60})

    def boom(current):
        raise RuntimeError("no")

    with pytest.raises(RuntimeError):
        await world.repo.update_in_txn("shell", boom)

    async def mark(conn) -> None:
        raise RuntimeError("mark")

    with pytest.raises(RuntimeError):
        await world.repo.update_in_txn(
            "shell", lambda cur: cur.model_copy(update={"config": {"x": 1}}), on_commit=mark
        )
    assert (await world.repo.get("shell")).config == {"timeout_seconds_max": 60}


async def test_a_hook_that_opens_a_write_transaction_fails_loudly(world) -> None:
    async def nested(conn) -> None:
        async with write_transaction(conn):
            pass

    with pytest.raises(RuntimeError):
        await world.repo.update_in_txn("shell", lambda cur: cur or _row("shell"), on_commit=nested)


def _row(name, **kw):
    from the_one.db.models import ToolConfig

    return ToolConfig(name=name, **kw)


# --- AC1: the PUT race ------------------------------------------------------------------------


async def _wait_for_waiter(task: asyncio.Task) -> None:
    for _ in range(400):
        if task.done():
            raise AssertionError("the write finished without waiting for the lock")
        if getattr(_write_lock._lock, "_waiters", None):
            return
        await asyncio.sleep(0.005)
    raise AssertionError("the write never reached the lock")


async def test_a_value_committed_while_a_replace_waits_for_the_lock_survives(world) -> None:
    await world.repo.upsert("shell", {"timeout_seconds_max": 60})
    async with write_transaction(world.conn):
        task = asyncio.create_task(svc.replace_tool_config(world.deps, "shell", {"enabled": False}))
        await _wait_for_waiter(task)
        # a raw write commits a different timeout_seconds_max while the replace waits
        await world.conn.execute(
            "UPDATE tool_configs SET config = ? WHERE name = 'shell'",
            ('{"timeout_seconds_max": 77}',),
        )
    await task
    stored = await world.repo.get("shell")
    assert stored.config == {"timeout_seconds_max": 77}
    assert stored.enabled is False


async def test_a_value_committed_while_a_change_waits_for_the_lock_survives(world) -> None:
    await world.repo.upsert("shell", {"timeout_seconds_max": 60})
    async with write_transaction(world.conn):
        task = asyncio.create_task(
            svc.change_tool_config(world.deps, "shell", {"output_cap_bytes": 2048})
        )
        await _wait_for_waiter(task)
        await world.conn.execute(
            "UPDATE tool_configs SET config = ? WHERE name = 'shell'",
            ('{"timeout_seconds_max": 77}',),
        )
    await task
    stored = await world.repo.get("shell")
    assert stored.config["timeout_seconds_max"] == 77 and stored.config["output_cap_bytes"] == 2048


async def test_the_put_route_reads_inside_the_transaction_too(world) -> None:
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from tests._api_app import shared_app
    from tests._credential_helpers import auth_headers

    await world.repo.upsert("shell", {"timeout_seconds_max": 60})
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=world.conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=world.enc),
    ):
        transport = ASGITransport(app=shared_app())
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as client:
            async with write_transaction(world.conn):
                task = asyncio.create_task(
                    client.put("/api/tools/configs/shell", json={"enabled": False})
                )
                await _wait_for_waiter(task)
                await world.conn.execute(
                    "UPDATE tool_configs SET config = ? WHERE name = 'shell'",
                    ('{"timeout_seconds_max": 77}',),
                )
            resp = await task
    assert resp.status_code == 200, resp.text
    stored = await world.repo.get("shell")
    assert stored.config == {"timeout_seconds_max": 77} and stored.enabled is False


async def test_replace_keeps_the_puts_shape_and_statuses(world) -> None:
    after = await svc.replace_tool_config(
        world.deps, "shell", {"config": {"timeout_seconds_max": 90}}
    )
    assert after.config["timeout_seconds_max"] == 90 and after.enabled is True
    with pytest.raises(svc.ToolConfigWriteError) as e:
        await svc.replace_tool_config(
            world.deps,
            "shell",
            {"config": {"timeout_seconds_default": 100, "timeout_seconds_max": 50}},
        )
    assert e.value.status == 422 and isinstance(e.value.detail, list)
    with pytest.raises(svc.ToolConfigWriteError) as e:
        await svc.replace_tool_config(world.deps, "nope", {})
    assert e.value.status == 404 and e.value.detail == "Tool not found: nope"


# --- AC2: a change never drops a stored secret ---------------------------------------------


async def _web_search_row(world):
    await world.repo.upsert(
        "web_search",
        {"search_backend": "duckduckgo", "searxng_base_url": "", "google_pse_cse_id": ""},
        secrets=dict(KEYS),
    )


async def test_a_change_keeps_every_stored_secret(world) -> None:
    await _web_search_row(world)
    await svc.change_tool_config(world.deps, "web_search", {"search_backend": "brave"})
    row = await world.repo.get("web_search")
    assert row.secrets == KEYS and row.config["search_backend"] == "brave"
    await svc.change_tool_config(
        world.deps, "web_search", {"searxng_base_url": "https://s.example.com"}
    )
    assert (await world.repo.get("web_search")).secrets == KEYS
    # the number the leg names is not a web_search field: it validates, is ignored, drops nothing
    await svc.change_tool_config(world.deps, "web_search", {"timeout_seconds_max": 60})
    assert (await world.repo.get("web_search")).secrets == KEYS


async def test_a_replace_without_the_secrets_does_drop_them_which_a_change_must_not(world) -> None:
    """The PUT's own contract (a missing secret is cleared) is why ``change`` merges over
    ``{**config, **secrets}``."""
    await _web_search_row(world)
    await svc.replace_tool_config(world.deps, "web_search", {"config": {"search_backend": "brave"}})
    assert (await world.repo.get("web_search")).secrets == {}


async def test_a_config_change_on_a_never_saved_row_materialises_the_defaults(world) -> None:
    assert await _raw(world, "shell") is None
    await svc.change_tool_config(world.deps, "shell", {"timeout_seconds_max": 60})
    row = await world.repo.get("shell")
    assert row.config["timeout_seconds_max"] == 60
    assert {"timeout_seconds_default", "output_cap_bytes", "command_denylist"} <= set(row.config)


async def test_an_enabled_only_change_on_a_never_saved_row_leaves_config_empty(world) -> None:
    await svc.change_tool_config(world.deps, "shell", {"enabled": False})
    row = await world.repo.get("shell")
    assert row.config == {} and row.enabled is False
    # an empty-Config tool takes enabled alone
    await svc.change_tool_config(world.deps, "current_time", {"enabled": False})
    row = await world.repo.get("current_time")
    assert row.config == {} and row.enabled is False


async def test_enabled_is_the_top_level_column_and_never_enters_config(world) -> None:
    await svc.change_tool_config(world.deps, "shell", {"enabled": False, "output_cap_bytes": 4096})
    row = await world.repo.get("shell")
    assert row.enabled is False and "enabled" not in row.config
    assert row.config["output_cap_bytes"] == 4096


# --- effective values and the stale check ------------------------------------------------------


async def test_effective_values_are_the_stored_value_over_that_tools_own_default(world) -> None:
    eff = svc.effective_values("shell", None)
    assert eff["enabled"] is True and eff["timeout_seconds_default"] == 30
    from the_one.tools.execution import PythonExecConfig

    # the tool's OWN Config default, not the shared base class's
    assert (
        svc.effective_values("python_exec", None)["timeout_seconds_default"]
        == PythonExecConfig.model_fields["timeout_seconds_default"].default
    )
    await world.repo.upsert("shell", {"timeout_seconds_max": 55}, enabled=False)
    eff = svc.effective_values("shell", await world.repo.get("shell"))
    assert eff["enabled"] is False and eff["timeout_seconds_max"] == 55
    assert eff["timeout_seconds_default"] == 30
    # a secret field is never part of the effective values
    assert not (set(KEYS) & set(svc.effective_values("web_search", None)))


async def test_a_write_to_the_named_field_makes_the_change_stale_and_another_does_not(
    world,
) -> None:
    base = {"timeout_seconds_max": 120}
    await world.repo.upsert("shell", {"timeout_seconds_max": 120, "output_cap_bytes": 2048})
    # another field moved: not stale
    await world.repo.upsert("shell", {"timeout_seconds_max": 120, "output_cap_bytes": 4096})
    await svc.change_tool_config(world.deps, "shell", {"timeout_seconds_max": 60}, base=base)
    # the named field moved: stale, nothing written
    await world.repo.upsert("shell", {"timeout_seconds_max": 200})
    marks = []

    async def mark(conn) -> None:
        marks.append(1)

    with pytest.raises(svc.ToolConfigStaleError) as e:
        await svc.change_tool_config(
            world.deps, "shell", {"timeout_seconds_max": 30}, base=base, on_commit=mark
        )
    assert e.value.fields == [{"field": "timeout_seconds_max", "current": 200, "proposed": 30}]
    assert marks == [] and (await world.repo.get("shell")).config["timeout_seconds_max"] == 200
    await svc.change_tool_config(
        world.deps, "shell", {"timeout_seconds_max": 30}, base=base, override=True, on_commit=mark
    )
    assert marks == [1] and (await world.repo.get("shell")).config["timeout_seconds_max"] == 30


async def test_a_validation_failure_is_a_422_and_writes_nothing(world) -> None:
    with pytest.raises(svc.ToolConfigWriteError) as e:
        await svc.change_tool_config(
            world.deps, "shell", {"timeout_seconds_default": 100, "timeout_seconds_max": 50}
        )
    assert e.value.status == 422 and e.value.items
    assert await _raw(world, "shell") is None


# --- the impact preview ------------------------------------------------------------------------


async def test_the_impact_preview_returns_nothing_without_an_override(world) -> None:
    assert (
        await svc.preview_impact(world.deps, "shell", {"config": {"timeout_seconds_max": 30}}) == []
    )
    with pytest.raises(svc.ToolConfigWriteError):
        await svc.preview_impact(world.deps, "nope", {})
