"""The provider write service and its repository hooks (Mission 36 F4 L5a, DD10).

``update_in_txn`` (re-read inside the write transaction), ``create`` / ``replace`` / ``change``
in ``the_one/llm/provider_service.py``, the OAuth-refresh race the re-read fixes (service and
route), the type-change rules, and the import boundary.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.db import _write_lock
from the_one.db._write_lock import write_transaction
from the_one.db.models import LLMProviderConfig
from the_one.db.repositories import LLMProviderRepository, _encrypt_secrets_blob
from the_one.encryption import get_encryptor
from the_one.llm import provider_service as svc

ROOT = Path(__file__).resolve().parent.parent
OAUTH = {
    "access_token": "access-1",
    "refresh_token": "refresh-1",
    "token_expires_at": 1893456000,
    "scope": "user:inference",
    "token_type": "Bearer",
}


@pytest.fixture
async def world(tmp_path):
    _write_lock.reset_for_test()
    conn = await connect_template_db(tmp_path / "svc.db")
    enc = get_encryptor(tmp_path)
    repo = LLMProviderRepository(conn, enc)
    ns = SimpleNamespace(conn=conn, enc=enc, repo=repo, deps=svc.ProviderWriteDeps(repo=repo))
    yield ns
    await conn.close()


async def make(world, **kw) -> LLMProviderConfig:
    body = {
        "id": "p1",
        "name": "Main",
        "type": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-stored-key-1234567890",
        "config": {"reasoning_effort": "low", "stop": ["END"]},
    }
    body.update(kw)
    provider = LLMProviderConfig.model_validate(body)
    await world.repo.create(provider)
    return provider


async def make_plan(world, **kw) -> LLMProviderConfig:
    return await make(
        world,
        type="anthropic-plan",
        base_url="https://api.anthropic.com",
        api_key=None,
        config={"thinking_enabled": True},
        secrets=dict(OAUTH),
        **kw,
    )


async def make_token(world, **kw) -> LLMProviderConfig:
    return await make(
        world,
        type="anthropic-plan-token",
        base_url="https://api.anthropic.com",
        api_key="sk-ant-oat01-stored",
        config={"thinking_enabled": True},
        secrets={"token_set_at": "2026-01-01T00:00:00+00:00"},
        **kw,
    )


# --- the import boundary --------------------------------------------------------------------


def test_the_service_imports_no_interface_layer_and_no_repository_at_module_level() -> None:
    tree = ast.parse((ROOT / "the_one" / "llm" / "provider_service.py").read_text())
    banned = ("fastapi", "starlette", "the_one.interfaces", "the_one.gleepglorp")
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        assert not any(n == b or n.startswith(b + ".") for n in names for b in banned), names
    # the repository is behind TYPE_CHECKING only (plan_credentials stays DB-free at import)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert "repositories" not in (getattr(node, "module", "") or ""), node.lineno


# --- AC3: update_in_txn -----------------------------------------------------------------------


async def test_update_in_txn_rereads_so_a_refreshed_token_survives(world) -> None:
    await make_plan(world)
    stale = await world.repo.get("p1")
    await world.repo.update_secrets("p1", {**OAUTH, "refresh_token": "refresh-2"})
    assert stale.secrets["refresh_token"] == "refresh-1"
    await svc.change_provider(world.deps, "p1", {"name": "Renamed"})
    stored = await world.repo.get("p1")
    assert stored.name == "Renamed"
    assert stored.secrets["refresh_token"] == "refresh-2"


async def test_update_in_txn_returns_before_and_after_and_moves_updated_at(world) -> None:
    src = await make(world)
    before, after = await world.repo.update_in_txn(
        "p1", lambda cur: cur.model_copy(update={"name": "Main 2"})
    )
    assert before.name == "Main" and after.name == "Main 2"
    assert after.updated_at != src.updated_at and after.updated_at >= src.updated_at
    stored = await world.repo.get("p1")
    assert stored.updated_at == after.updated_at
    assert stored.api_key == "sk-stored-key-1234567890"  # still encrypted/decrypted as update does


async def test_a_mutator_exception_writes_nothing(world) -> None:
    await make(world)

    def boom(cur):
        raise ValueError("no")

    with pytest.raises(ValueError):
        await world.repo.update_in_txn("p1", boom)
    assert (await world.repo.get("p1")).name == "Main"


async def test_on_commit_runs_inside_the_transaction_and_rolls_back_with_it(world) -> None:
    await make(world)
    seen: list[str] = []

    async def hook(conn):
        async with conn.execute("SELECT name FROM llm_providers WHERE id = 'p1'") as cur:
            seen.append((await cur.fetchone())[0])

    await world.repo.update_in_txn(
        "p1", lambda cur: cur.model_copy(update={"name": "Main 2"}), on_commit=hook
    )
    assert seen == ["Main 2"]

    async def failing(conn):
        raise RuntimeError("late")

    with pytest.raises(RuntimeError):
        await world.repo.update_in_txn(
            "p1", lambda cur: cur.model_copy(update={"name": "Main 3"}), on_commit=failing
        )
    assert (await world.repo.get("p1")).name == "Main 2"


async def test_create_on_commit_rolls_the_insert_back(world) -> None:
    async def failing(conn):
        raise RuntimeError("late")

    p = LLMProviderConfig(id="n1", name="New", type="ollama", base_url="http://localhost:11434/v1")
    with pytest.raises(RuntimeError):
        await world.repo.create(p, on_commit=failing)
    with pytest.raises(KeyError):
        await world.repo.get("n1")


async def test_a_hook_that_opens_a_write_transaction_fails_loudly(world) -> None:
    await make(world)

    async def nested(conn):
        async with write_transaction(conn):
            pass

    with pytest.raises(RuntimeError, match="re-entered"):
        await world.repo.update_in_txn("p1", lambda cur: cur, on_commit=nested)


async def test_update_in_txn_of_an_unknown_id_is_a_key_error(world) -> None:
    with pytest.raises(KeyError):
        await world.repo.update_in_txn("nope", lambda cur: cur)


# --- AC2: the race (service and route) ----------------------------------------------------------


async def _wait_for_waiter(task: asyncio.Task) -> None:
    """Yield until ``task`` is blocked on the write lock the test holds. The test then writes a
    new refresh token with raw SQL (``update_secrets`` would trip the re-entrancy guard)."""
    for _ in range(400):
        if task.done():
            raise AssertionError("the write finished without waiting for the lock")
        if getattr(_write_lock._lock, "_waiters", None):
            return
        await asyncio.sleep(0.005)
    raise AssertionError("the write never reached the lock")


async def test_a_refresh_written_while_a_replace_waits_for_the_lock_survives(world) -> None:
    await make_plan(world)
    # the lock is held by the test before the write starts
    async with write_transaction(world.conn):
        task = asyncio.create_task(
            svc.replace_provider(
                world.deps,
                "p1",
                {
                    "name": "Renamed",
                    "type": "anthropic-plan",
                    "base_url": "https://api.anthropic.com",
                },
                dev_mode=False,
            )
        )
        await _wait_for_waiter(task)
        await world.conn.execute(
            "UPDATE llm_providers SET secrets=? WHERE id='p1'",
            (_encrypt_secrets_blob(world.enc, {**OAUTH, "refresh_token": "refresh-NEW"}),),
        )
    after = await task
    stored = await world.repo.get("p1")
    assert stored.name == "Renamed"
    assert stored.secrets["refresh_token"] == "refresh-NEW"
    assert after.secrets["refresh_token"] == "refresh-NEW"


async def test_a_refresh_written_while_a_change_waits_for_the_lock_survives(world) -> None:
    await make_plan(world)
    async with write_transaction(world.conn):
        task = asyncio.create_task(svc.change_provider(world.deps, "p1", {"name": "Renamed"}))
        await _wait_for_waiter(task)
        await world.conn.execute(
            "UPDATE llm_providers SET secrets=? WHERE id='p1'",
            (_encrypt_secrets_blob(world.enc, {**OAUTH, "refresh_token": "refresh-NEW"}),),
        )
    await task
    stored = await world.repo.get("p1")
    assert stored.name == "Renamed"
    assert stored.secrets["refresh_token"] == "refresh-NEW"


async def test_a_refresh_written_while_a_put_waits_for_the_lock_survives(world) -> None:
    """The route: an operator save racing an OAuth refresh keeps the fresh token."""
    await make_plan(world)
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
                    client.put(
                        "/api/providers/p1",
                        json={
                            "name": "Renamed",
                            "type": "anthropic-plan",
                            "base_url": "https://api.anthropic.com",
                        },
                    )
                )
                await _wait_for_waiter(task)
                await world.conn.execute(
                    "UPDATE llm_providers SET secrets=? WHERE id='p1'",
                    (_encrypt_secrets_blob(world.enc, {**OAUTH, "refresh_token": "refresh-NEW"}),),
                )
            resp = await task
    assert resp.status_code == 200, resp.text
    stored = await world.repo.get("p1")
    assert stored.name == "Renamed"
    assert stored.secrets["refresh_token"] == "refresh-NEW"
    assert "secrets" not in resp.json()


async def test_a_put_response_carries_the_written_updated_at(world) -> None:
    src = await make(world)
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=world.conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=world.enc),
    ):
        transport = ASGITransport(app=shared_app())
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as client:
            resp = await client.put("/api/providers/p1", json={"name": "Main 2"})
    stored = await world.repo.get("p1")
    assert resp.json()["updated_at"] == stored.updated_at != src.updated_at


# --- create / replace -------------------------------------------------------------------------


async def test_create_provider_seeds_thinking_stamps_the_token_and_checks_the_url(world) -> None:
    p = await svc.create_provider(
        world.deps,
        {
            "name": "Claude",
            "type": "anthropic-plan-token",
            "base_url": "https://api.anthropic.com",
            "api_key": "sk-ant-oat01-x",
        },
        dev_mode=False,
    )
    assert p.config["thinking_enabled"] is True and "token_set_at" in p.secrets
    with pytest.raises(svc.ProviderWriteError) as e:
        await svc.create_provider(
            world.deps,
            {"name": "Bad", "type": "openai", "base_url": "http://example.com", "api_key": "k"},
            dev_mode=False,
        )
    assert e.value.status == 422 and "cleartext" in e.value.detail
    with pytest.raises(svc.ProviderWriteError) as e:
        await svc.create_provider(
            world.deps, {"name": "M", "type": "mock", "base_url": ""}, dev_mode=False
        )
    assert e.value.status == 400
    ok = await svc.create_provider(
        world.deps, {"name": "M", "type": "mock", "base_url": ""}, dev_mode=True
    )
    assert ok.type == "mock"


async def test_create_provider_on_commit_failure_rolls_back(world) -> None:
    async def failing(conn):
        raise RuntimeError("late")

    with pytest.raises(RuntimeError):
        await svc.create_provider(
            world.deps,
            {"id": "c1", "name": "O", "type": "ollama", "base_url": "http://localhost:11434/v1"},
            dev_mode=False,
            on_commit=failing,
        )
    with pytest.raises(KeyError):
        await world.repo.get("c1")


async def test_replace_provider_unknown_id_is_not_found_before_the_mock_gate(world) -> None:
    with pytest.raises(svc.ProviderNotFound):
        await svc.replace_provider(world.deps, "nope", {"type": "mock"}, dev_mode=False)


async def test_replace_provider_preserves_a_masked_key(world) -> None:
    await make(world)
    await svc.replace_provider(
        world.deps,
        "p1",
        {"name": "Main 2", "api_key": "__MASKED__", "base_url": "https://api.openai.com/v1"},
        dev_mode=False,
    )
    assert (await world.repo.get("p1")).api_key == "sk-stored-key-1234567890"


# --- AC4: change_provider ---------------------------------------------------------------------


async def test_change_merges_config_per_key_and_keeps_the_key(world) -> None:
    await make(world)
    after = await svc.change_provider(world.deps, "p1", {"reasoning_effort": "high"})
    stored = await world.repo.get("p1")
    assert stored.config == {"reasoning_effort": "high", "stop": ["END"]}
    assert stored.api_key == "sk-stored-key-1234567890"
    assert after.config == stored.config


async def test_change_stores_an_empty_reasoning_effort_as_the_editor_does(world) -> None:
    await make(world)
    await svc.change_provider(world.deps, "p1", {"reasoning_effort": ""})
    assert (await world.repo.get("p1")).config["reasoning_effort"] == ""


async def test_a_stale_change_writes_nothing_and_override_skips_the_check(world) -> None:
    await make(world)
    base = {"name": "Old name"}
    with pytest.raises(svc.ProviderStaleError) as e:
        await svc.change_provider(world.deps, "p1", {"name": "New"}, base=base)
    assert e.value.fields == [{"field": "name", "current": "Main", "proposed": "New"}]
    assert (await world.repo.get("p1")).name == "Main"
    await svc.change_provider(world.deps, "p1", {"name": "New"}, base=base, override=True)
    assert (await world.repo.get("p1")).name == "New"


async def test_an_option_absent_at_proposal_and_present_now_is_stale(world) -> None:
    await make(
        world,
        type="ollama",
        base_url="http://localhost:11434/v1",
        api_key=None,
        config={"num_ctx": 2048},
    )
    with pytest.raises(svc.ProviderStaleError):
        await svc.change_provider(world.deps, "p1", {"num_ctx": 4096}, base={})


async def test_into_ollama_clears_the_key_seeds_num_ctx_and_takes_the_default_url(world) -> None:
    await make(world)
    with patch("the_one.llm.plan_credentials.evict_credential_source") as evict:
        await svc.change_provider(world.deps, "p1", {"type": "ollama"})
    stored = await world.repo.get("p1")
    assert stored.type == "ollama" and stored.api_key is None
    assert stored.base_url == "http://localhost:11434/v1"
    assert stored.config["num_ctx"] == svc.DEFAULT_NUM_CTX == 32768
    assert stored.config["stop"] == ["END"]
    evict.assert_called_once_with("p1")


async def test_into_ollama_takes_a_named_url(world) -> None:
    await make(world)
    await svc.change_provider(
        world.deps, "p1", {"type": "ollama", "base_url": "http://gpu-box:11434/v1", "num_ctx": 8192}
    )
    stored = await world.repo.get("p1")
    assert stored.base_url == "http://gpu-box:11434/v1" and stored.config["num_ctx"] == 8192


async def test_into_anthropic_plan_clears_the_key_and_the_token_stamp(world) -> None:
    await make(world, type="ollama", base_url="http://localhost:11434/v1", api_key=None)
    await svc.change_provider(world.deps, "p1", {"type": "anthropic-plan"})
    stored = await world.repo.get("p1")
    assert stored.type == "anthropic-plan" and stored.api_key is None
    assert stored.base_url == "https://api.anthropic.com"
    assert stored.config["thinking_enabled"] is True
    assert stored.secrets == {}


async def test_token_type_into_anthropic_plan_drops_the_token_and_stamp(world) -> None:
    await make_token(world)
    await svc.change_provider(world.deps, "p1", {"type": "anthropic-plan"})
    stored = await world.repo.get("p1")
    assert stored.api_key is None and stored.secrets == {}


async def test_staying_anthropic_plan_keeps_the_oauth_keys(world) -> None:
    await make_plan(world)
    await svc.change_provider(world.deps, "p1", {"name": "Renamed", "thinking_enabled": False})
    stored = await world.repo.get("p1")
    assert stored.secrets == OAUTH and stored.config["thinking_enabled"] is False


async def test_out_of_anthropic_plan_drops_the_oauth_secrets(world) -> None:
    await make_plan(world)
    await svc.change_provider(world.deps, "p1", {"type": "ollama"})
    stored = await world.repo.get("p1")
    assert stored.type == "ollama" and stored.secrets == {} and stored.api_key is None


async def test_keyless_to_key_taking_is_allowed_and_leaves_no_key(world) -> None:
    await make_plan(world)
    await svc.change_provider(world.deps, "p1", {"type": "anthropic"})
    stored = await world.repo.get("p1")
    assert stored.type == "anthropic" and stored.api_key is None and stored.secrets == {}


@pytest.mark.parametrize(
    "start,target",
    [("openai", "anthropic"), ("openai", "openrouter"), ("token", "anthropic")],
)
async def test_key_taking_to_a_different_key_taking_type_is_refused(world, start, target) -> None:
    if start == "token":
        await make_token(world)
    else:
        await make(world)
    before = await world.repo.get("p1")
    with pytest.raises(svc.ProviderWriteError) as e:
        await svc.change_provider(world.deps, "p1", {"type": target})
    assert e.value.status == 422 and svc.KEY_TYPE_CHANGE_DETAIL in str(e.value.detail)
    assert await world.repo.get("p1") == before


async def test_a_change_into_the_token_type_is_refused(world) -> None:
    await make(world, type="ollama", base_url="http://localhost:11434/v1", api_key=None)
    with pytest.raises(svc.ProviderWriteError) as e:
        await svc.change_provider(world.deps, "p1", {"type": "anthropic-plan-token"})
    assert e.value.status == 422


async def test_a_token_type_change_that_keeps_the_type_keeps_the_key_and_stamp(world) -> None:
    await make_token(world)
    await svc.change_provider(world.deps, "p1", {"name": "Renamed", "reasoning_effort": "high"})
    stored = await world.repo.get("p1")
    assert stored.api_key == "sk-ant-oat01-stored"
    assert stored.secrets == {"token_set_at": "2026-01-01T00:00:00+00:00"}
    assert stored.config["reasoning_effort"] == "high"


async def test_openai_compatible_needs_a_named_address(world) -> None:
    await make_plan(world)
    with pytest.raises(svc.ProviderWriteError) as e:
        await svc.change_provider(world.deps, "p1", {"type": "openai-compatible"})
    assert "base_url" in str(e.value.detail)
    await svc.change_provider(
        world.deps, "p1", {"type": "openai-compatible", "base_url": "https://llm.example.com/v1"}
    )
    assert (await world.repo.get("p1")).base_url == "https://llm.example.com/v1"


async def test_a_hidden_address_type_refuses_a_named_base_url(world) -> None:
    await make(world, type="ollama", base_url="http://localhost:11434/v1", api_key=None)
    with pytest.raises(svc.ProviderWriteError):
        await svc.change_provider(
            world.deps, "p1", {"type": "anthropic", "base_url": "https://evil.example.com"}
        )
    await make(world, id="p2", name="Second")
    with pytest.raises(svc.ProviderWriteError):  # same type, hidden address
        await svc.change_provider(world.deps, "p2", {"base_url": "https://evil.example.com"})


async def test_options_the_type_does_not_show_are_refused(world) -> None:
    await make(world)  # openai
    for changes in ({"num_ctx": 4096}, {"thinking_enabled": True}):
        with pytest.raises(svc.ProviderWriteError) as e:
            await svc.change_provider(world.deps, "p1", changes)
        assert "doesn't apply" in str(e.value.detail)


@pytest.mark.parametrize(
    "changes",
    [{"reasoning_effort": "extreme"}, {"reasoning_effort": 3}, {"name": ""}, {"secrets": {}}],
)
async def test_bad_values_and_operator_only_keys_are_refused(world, changes) -> None:
    await make(world)
    with pytest.raises(svc.ProviderWriteError):
        await svc.change_provider(world.deps, "p1", changes)


async def test_a_mock_target_or_a_change_to_mock_is_refused(world) -> None:
    await make(world, id="m1", name="Mock", type="mock", base_url="", api_key=None)
    with pytest.raises(svc.ProviderWriteError):
        await svc.change_provider(world.deps, "m1", {"name": "Other"})
    await make(world)
    with pytest.raises(svc.ProviderWriteError):
        await svc.change_provider(world.deps, "p1", {"type": "mock"})


async def test_the_url_check_applies_on_a_change(world) -> None:
    await make(
        world,
        type="openai-compatible",
        base_url="https://llm.example.com/v1",
    )
    with pytest.raises(svc.ProviderWriteError) as e:
        await svc.change_provider(world.deps, "p1", {"base_url": "http://example.com/v1"})
    assert "cleartext" in e.value.detail
    assert (await world.repo.get("p1")).base_url == "https://llm.example.com/v1"


async def test_the_name_rule_applies_on_a_change(world) -> None:
    await make(world)
    with pytest.raises(svc.ProviderWriteError) as e:
        await svc.change_provider(world.deps, "p1", {"name": "   "})
    assert e.value.status == 422 and e.value.detail[0]["loc"] == ["name"]


async def test_change_of_an_unknown_id_is_not_found(world) -> None:
    with pytest.raises(svc.ProviderNotFound):
        await svc.change_provider(world.deps, "nope", {"name": "x"})


async def test_eviction_does_not_run_when_the_write_fails(world) -> None:
    await make(world)
    with patch("the_one.llm.plan_credentials.evict_credential_source") as evict:
        with pytest.raises(svc.ProviderWriteError):
            await svc.change_provider(world.deps, "p1", {"num_ctx": 5})
    evict.assert_not_called()


async def test_on_commit_failure_rolls_a_change_back(world) -> None:
    await make(world)

    async def failing(conn):
        raise RuntimeError("late")

    with pytest.raises(RuntimeError):
        await svc.change_provider(world.deps, "p1", {"name": "New"}, on_commit=failing)
    assert (await world.repo.get("p1")).name == "Main"
