"""The secret write service and its repository hooks (Mission 36 F5 L3a, DD3, DD6).

``parse_secret`` and its helpers (moved from the routes with their exact sentences), ``create`` /
``replace`` / ``change_secret_metadata`` in ``the_one/secret_store/service.py``, the
``precheck`` / ``on_commit`` hooks of ``SecretRepository.update``, the value-free change path
and the import boundary.
"""

from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests._schema_template import connect_template_db
from the_one.db import _write_lock
from the_one.db._write_lock import write_transaction
from the_one.db.repositories import SecretRepository
from the_one.encryption import get_encryptor
from the_one.secret_store import service as svc

ROOT = Path(__file__).resolve().parent.parent
VALUE = "plain-test-value-XYZZY-0f1e2d3c-aaaa"


@pytest.fixture
async def world(tmp_path):
    _write_lock.reset_for_test()
    conn = await connect_template_db(tmp_path / "secrets.db")
    repo = SecretRepository(conn, get_encryptor(tmp_path))
    first = await repo.create(
        "Github", "GitHub access", ["shell"], [{"key": "gh_token", "value": VALUE}]
    )
    deps = svc.SecretWriteDeps(repo=repo)
    yield SimpleNamespace(conn=conn, repo=repo, deps=deps, first=first)
    await conn.close()


async def values_of(world, secret_id) -> list[tuple[str, str]]:
    return await world.repo.get_values(secret_id)


# --- the import boundary --------------------------------------------------------------------


def test_the_service_imports_no_interface_layer_and_no_gleepglorp() -> None:
    tree = ast.parse((ROOT / "the_one" / "secret_store" / "service.py").read_text())
    banned = ("fastapi", "starlette", "the_one.interfaces", "the_one.gleepglorp")
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        assert not any(n == b or n.startswith(b + ".") for n in names for b in banned), names


def test_the_routes_hold_no_validation_logic() -> None:
    text = (ROOT / "the_one" / "interfaces" / "web" / "secrets_api.py").read_text()
    for name in ("_parse", "_check_values", "_check_allowed_tools", "KEY_PATTERN", "is_refused"):
        assert name not in text.replace("is_refused_tool", ""), name


# --- create and replace: the routes' behaviour ------------------------------------------------


async def test_create_validates_and_writes(world) -> None:
    s = await svc.create_secret(
        world.deps,
        {
            "name": " New one ",
            "allowed_tools": ["fetch_url", "fetch_url", " shell "],
            "values": [{"key": "api_key", "value": "v1"}],
        },
    )
    assert s.name == "New one" and s.allowed_tools == ["fetch_url", "shell"]
    assert s.description == "" and [v.key for v in s.values] == ["api_key"]


@pytest.mark.parametrize(
    ("data", "loc", "msg"),
    [
        ({"name": "x", "allowed_tools": [], "values": [{"key": "k", "value": "v"}]},
         ["allowed_tools"], "Choose at least one tool that may receive this secret."),
        ({"name": "x", "allowed_tools": ["a b"], "values": [{"key": "k", "value": "v"}]},
         ["allowed_tools", 0], "A tool name can't contain whitespace."),
        ({"name": "x", "allowed_tools": ["continue"], "values": [{"key": "k", "value": "v"}]},
         ["allowed_tools", 0],
         "continue stores or publishes what it receives, so it can't receive secrets."),
        ({"name": "x", "allowed_tools": ["t"], "values": []},
         ["values"], "Add at least one key and value."),
        ({"name": "x", "allowed_tools": ["t"], "values": [{"key": "bad key", "value": "v"}]},
         ["values", 0, "key"], "A key can use letters, digits, _ and -, 1 to 64 characters."),
        ({"name": "x", "allowed_tools": ["t"], "values": [{"key": "k", "value": "__MASKED__"}]},
         ["values", 0, "value"], "Enter the value; a masked value needs its pair id."),
        ({"name": "x", "description": 3, "allowed_tools": ["t"],
          "values": [{"key": "k", "value": "v"}]},
         ["description"], "A description must be text."),
    ],
)  # fmt: skip
async def test_create_refuses_each_check_with_the_routes_sentence(world, data, loc, msg) -> None:
    with pytest.raises(svc.SecretWriteError) as e:
        await svc.create_secret(world.deps, data)
    assert e.value.status == 422
    assert {"type": "value_error", "loc": loc, "msg": msg} in e.value.detail


async def test_a_bad_name_is_the_name_rule_422(world) -> None:
    with pytest.raises(svc.SecretWriteError) as e:
        await svc.create_secret(world.deps, {"name": " ", "allowed_tools": ["t"], "values": []})
    assert e.value.status == 422 and e.value.detail[0]["loc"] == ["name"]
    assert e.value.detail[0]["type"] == "name_rule"


async def test_a_duplicate_name_is_the_409_ignoring_case(world) -> None:
    with pytest.raises(svc.SecretWriteError) as e:
        await svc.create_secret(
            world.deps,
            {"name": "GITHUB", "allowed_tools": ["t"], "values": [{"key": "k2", "value": "v"}]},
        )
    assert e.value.status == 409
    assert e.value.detail == [
        {
            "type": "name_conflict",
            "loc": ["name"],
            "msg": "A secret with this name already exists.",
        }
    ]
    assert e.value.items == [{"loc": ["name"], "msg": "A secret with this name already exists."}]


async def test_a_repeated_key_in_another_secret_is_the_repositorys_422(world) -> None:
    with pytest.raises(svc.SecretWriteError) as e:
        await svc.create_secret(
            world.deps,
            {
                "name": "Other",
                "allowed_tools": ["t"],
                "values": [{"key": "GH_TOKEN", "value": "v"}],
            },
        )
    assert e.value.status == 422 and e.value.detail[0]["loc"] == ["values", 0, "key"]


async def test_replace_is_partial_and_the_404_precedes_the_422(world) -> None:
    s = await svc.replace_secret(world.deps, world.first.id, {"description": "Changed"})
    assert s.description == "Changed" and s.name == "Github" and s.allowed_tools == ["shell"]
    assert await values_of(world, s.id) == [("gh_token", VALUE)]  # values untouched
    with pytest.raises(svc.SecretNotFound):
        await svc.replace_secret(world.deps, "nope", {"allowed_tools": []})  # would be a 422
    with pytest.raises(svc.SecretWriteError) as e:
        await svc.replace_secret(world.deps, world.first.id, {"allowed_tools": []})
    assert e.value.status == 422


# --- change_secret_metadata -------------------------------------------------------------------


async def test_a_change_replaces_allowed_tools_whole_and_never_touches_values(world) -> None:
    before = await world.repo.get_values(world.first.id)
    s = await svc.change_secret_metadata(
        world.deps,
        world.first.id,
        {"allowed_tools": ["fetch_url", "mcp__goldfinch__captureScreenshot"]},
        base={"allowed_tools": ["shell"]},
    )
    assert s.allowed_tools == ["fetch_url", "mcp__goldfinch__captureScreenshot"]
    assert s.name == "Github" and s.description == "GitHub access"
    assert await values_of(world, s.id) == before == [("gh_token", VALUE)]


async def test_a_change_refuses_a_refused_tool_and_an_empty_list_with_the_routes_sentences(
    world,
) -> None:
    with pytest.raises(svc.SecretWriteError) as e:
        await svc.change_secret_metadata(
            world.deps, world.first.id, {"allowed_tools": ["send_to_platform_channel"]}, base={}
        )
    assert e.value.items[0]["msg"] == (
        "send_to_platform_channel stores or publishes what it receives, so it can't receive "
        "secrets."
    )
    with pytest.raises(svc.SecretWriteError) as e:
        await svc.change_secret_metadata(world.deps, world.first.id, {"allowed_tools": []}, base={})
    assert e.value.items == [
        {"loc": ["allowed_tools"], "msg": "Choose at least one tool that may receive this secret."}
    ]
    assert (await world.repo.get(world.first.id)).allowed_tools == ["shell"]


async def test_a_change_ignores_values_in_its_changes(world) -> None:
    await svc.change_secret_metadata(
        world.deps,
        world.first.id,
        {"description": "d2", "values": [{"key": "evil", "value": "x"}]},
        base={"description": "GitHub access"},
    )
    assert await values_of(world, world.first.id) == [("gh_token", VALUE)]


async def test_a_stale_change_raises_writes_nothing_and_override_applies(world) -> None:
    await world.repo.update(world.first.id, description="Moved")
    with pytest.raises(svc.SecretStaleError) as e:
        await svc.change_secret_metadata(
            world.deps, world.first.id, {"description": "Mine"},
            base={"description": "GitHub access"},
        )  # fmt: skip
    assert e.value.fields == [{"field": "description", "current": "Moved", "proposed": "Mine"}]
    assert (await world.repo.get(world.first.id)).description == "Moved"
    await svc.change_secret_metadata(
        world.deps, world.first.id, {"description": "Mine"},
        base={"description": "GitHub access"}, override=True,
    )  # fmt: skip
    assert (await world.repo.get(world.first.id)).description == "Mine"


async def _wait_for_waiter(task) -> None:
    for _ in range(400):
        if task.done():
            raise AssertionError("the write finished without waiting for the lock")
        if getattr(_write_lock._lock, "_waiters", None):
            return
        await asyncio.sleep(0.005)
    raise AssertionError("the write never reached the lock")


async def test_the_base_is_compared_on_the_row_read_inside_the_transaction(world) -> None:
    async with write_transaction(world.conn):
        task = asyncio.create_task(
            svc.change_secret_metadata(
                world.deps,
                world.first.id,
                {"description": "Mine"},
                base={"description": "GitHub access"},
            )  # fmt: skip
        )
        await _wait_for_waiter(task)
        await world.conn.execute(
            "UPDATE secrets SET description='Raced' WHERE id=?", (world.first.id,)
        )
    with pytest.raises(svc.SecretStaleError):
        await task
    assert (await world.repo.get(world.first.id)).description == "Raced"


async def test_an_unknown_id_is_a_typed_not_found(world) -> None:
    with pytest.raises(svc.SecretNotFound):
        await svc.change_secret_metadata(world.deps, "nope", {"description": "x"}, base={})


async def test_a_rename_that_differs_only_by_case_is_allowed(world) -> None:
    s = await svc.change_secret_metadata(
        world.deps, world.first.id, {"name": "GITHUB"}, base={"name": "Github"}
    )
    assert s.name == "GITHUB"


async def test_a_rename_to_another_secrets_name_is_the_409(world) -> None:
    other = await world.repo.create("Other", "", ["t"], [{"key": "o_key", "value": "v"}])
    with pytest.raises(svc.SecretWriteError) as e:
        await svc.change_secret_metadata(
            world.deps, other.id, {"name": "github"}, base={"name": "Other"}
        )
    assert e.value.status == 409 and e.value.items[0]["loc"] == ["name"]


async def test_on_commit_rides_the_transaction_and_a_raise_rolls_back(world) -> None:
    async def mark(conn) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await svc.change_secret_metadata(
            world.deps, world.first.id, {"description": "Z"},
            base={"description": "GitHub access"}, on_commit=mark,
        )  # fmt: skip
    assert (await world.repo.get(world.first.id)).description == "GitHub access"


# --- the change path reads no value -----------------------------------------------------------


def test_the_change_path_and_the_kind_never_call_a_value_reader() -> None:
    """A grep pin: no ``get_values`` / ``all_values`` and no ``values=`` argument to the
    repository in the service's change path or anywhere in the secret kind."""
    kind = (ROOT / "the_one" / "gleepglorp" / "kinds" / "secret.py").read_text()
    assert not re.search(r"get_values|all_values", kind)
    service = (ROOT / "the_one" / "secret_store" / "service.py").read_text()
    assert not re.search(r"get_values|all_values", service)
    change = service[service.index("async def change_secret_metadata") :]
    assert "values=" not in change.replace("values=...", "")
