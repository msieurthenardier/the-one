"""The agent write services (Mission 36 Flight 2 Leg 1, DD3/DD4/DD12).

`the_one/agent/service.py` holds create, replace and the field-level `change_agent`;
`write_checks.py` the validation they share with the routes. The route behaviour itself is
pinned by the existing agent tests; this file covers what is new: the field-level change, the
stale check, the retry, the save hooks and the import boundary.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.agent import service
from the_one.agent.config import AgentConfig
from the_one.agent.service import (
    AgentStaleError,
    AgentWriteDeps,
    AgentWriteError,
    change_agent,
    create_agent,
)
from the_one.db.repositories import (
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.encryption import Encryptor
from the_one.self_configuration import credentials as sc_credentials
from the_one.self_configuration import manage


@pytest.fixture(autouse=True)
def _isolated_registry():
    sc_credentials.clear_for_test()
    sc_credentials.register_credential_source_once()
    yield
    sc_credentials.clear_for_test()


@pytest.fixture
async def env(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    enc = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    store = SQLiteAgentStore(conn, enc)
    mcp = MCPSourceRepository(conn, enc)
    deps = AgentWriteDeps(
        store=store,
        mcp_repo=mcp,
        provider_repo=LLMProviderRepository(conn, enc),
        secret_repo=SecretRepository(conn, enc),
        tool_config_repo=ToolConfigRepository(conn, enc),
    )
    from types import SimpleNamespace

    yield SimpleNamespace(conn=conn, enc=enc, store=store, mcp=mcp, deps=deps)
    await conn.close()


def _full_agent(name: str = "a") -> AgentConfig:
    """An agent with (nearly) every persisted field set to a non-default value."""
    return AgentConfig(
        name=name,
        description="old description",
        llm_model="some-model",
        system_prompt="old prompt",
        enabled_tools=["shell", "web_search"],
        disabled_tools=["python_exec"],
        max_iterations=7,
        kb_ids=["kb-1", "kb-2"],
        secret_ids=["sec-1"],
        mcp_source_ids=["src-1"],
        tool_overrides={"shell": {"timeout": 5}},
        mcp_overrides={"gh": {"headers": {"X-Key": "secret-value-123"}, "enabled_tools": ["x"]}},
        chat_history_retention_days=11,
        self_revision_requires_approval=True,
        notes_enabled=True,
        rich_visuals=False,
    )


_FIELDS = (
    "description",
    "provider_config_id",
    "llm_model",
    "system_prompt",
    "enabled_tools",
    "disabled_tools",
    "max_iterations",
    "kb_ids",
    "mcp_source_ids",
    "tool_overrides",
    "mcp_overrides",
    "chat_history_retention_days",
    "secret_ids",
    "rich_visuals",
    "self_revision_requires_approval",
    "notes_enabled",
)


async def _seed(env, name: str = "a") -> AgentConfig:
    cfg = _full_agent(name)
    await env.store.save(cfg)
    return await env.store.load(name)


# ── change_agent writes only what it is told to ──────────────────────────


async def test_change_agent_writes_only_the_named_fields(env) -> None:
    before = await _seed(env)
    cfg = await change_agent(env.deps, "a", {"description": "new description"})
    after = await env.store.load("a")
    assert cfg.description == after.description == "new description"
    for field in _FIELDS:
        if field != "description":
            assert getattr(after, field) == getattr(before, field), field
    # The stored credential is kept as stored (not masked, not re-validated).
    assert after.mcp_overrides["gh"]["headers"] == {"X-Key": "secret-value-123"}


async def test_change_agent_keeps_switches_and_lists_when_changing_another_field(env) -> None:
    before = await _seed(env)
    await change_agent(env.deps, "a", {"system_prompt": "new prompt", "max_iterations": 9})
    after = await env.store.load("a")
    assert (after.system_prompt, after.max_iterations) == ("new prompt", 9)
    assert after.notes_enabled is True
    assert after.self_revision_requires_approval is True
    assert after.rich_visuals is False
    assert after.kb_ids == before.kb_ids
    assert after.secret_ids == before.secret_ids


async def test_change_agent_on_a_missing_agent_is_a_404(env) -> None:
    with pytest.raises(AgentWriteError) as exc:
        await change_agent(env.deps, "nope", {"description": "x"})
    assert (exc.value.status, exc.value.detail) == (404, "Agent not found: nope")


@pytest.mark.parametrize(
    "key,value",
    [
        ("name", "other"),
        ("mcp_overrides", {"gh": {"headers": {"X": "y"}}}),
        ("routines_self_config_enabled", True),
        ("routines_require_approval", True),
    ],
)
async def test_refused_keys_are_a_422_on_their_loc(env, key, value) -> None:
    await _seed(env)
    with pytest.raises(AgentWriteError) as exc:
        await change_agent(env.deps, "a", {"description": "ok", key: value})
    assert exc.value.status == 422
    assert [d["loc"] for d in exc.value.detail] == [[key]]
    assert (await env.store.load("a")).description == "old description"


async def test_a_model_failure_is_the_pydantic_422_without_an_input_echo(env) -> None:
    await _seed(env)
    with pytest.raises(AgentWriteError) as exc:
        await change_agent(env.deps, "a", {"max_iterations": "not-a-number-SECRET"})
    assert exc.value.status == 422
    assert "SECRET" not in repr(exc.value.detail)
    assert all("input" not in d for d in exc.value.detail)


# ── the stale check ──────────────────────────────────────────────────────


async def test_a_touched_field_changed_since_base_is_stale_and_nothing_is_written(env) -> None:
    await _seed(env)
    with pytest.raises(AgentStaleError) as exc:
        await change_agent(
            env.deps,
            "a",
            {"description": "mine", "system_prompt": "mine too"},
            base={"description": "what I saw", "system_prompt": "old prompt"},
        )
    assert exc.value.fields == [
        {"field": "description", "current": "old description", "proposed": "mine"}
    ]
    after = await env.store.load("a")
    assert (after.description, after.system_prompt) == ("old description", "old prompt")


async def test_override_applies_a_stale_change(env) -> None:
    await _seed(env)
    await change_agent(
        env.deps, "a", {"description": "mine"}, base={"description": "what I saw"}, override=True
    )
    assert (await env.store.load("a")).description == "mine"


async def test_a_matching_base_applies(env) -> None:
    await _seed(env)
    await change_agent(
        env.deps, "a", {"description": "mine"}, base={"description": "old description"}
    )
    assert (await env.store.load("a")).description == "mine"


async def test_a_base_of_none_means_no_touched_field_compare(env) -> None:
    await _seed(env)
    await change_agent(env.deps, "a", {"description": "mine"}, base=None)
    assert (await env.store.load("a")).description == "mine"


# ── a different field changing between load and save ─────────────────────


def _interfering_load(store: SQLiteAgentStore, interfere):
    """Patch ``store.load`` so the FIRST call returns the row it read and THEN runs
    ``interfere`` (a write landing between the load and the save); later calls are plain."""
    real = store.load
    calls = {"n": 0}

    async def load(name: str):
        row = await real(name)
        calls["n"] += 1
        if calls["n"] == 1:
            await interfere()
        return row

    return patch.object(store, "load", load), calls


async def test_a_concurrent_write_to_an_untouched_field_is_kept_and_the_change_converges(
    env,
) -> None:
    await _seed(env)

    async def interfere() -> None:
        latest = await env.store.load("a")
        await env.store.save(latest.model_copy(update={"system_prompt": "someone else's"}))

    patcher, _ = _interfering_load(env.store, interfere)
    with patcher:
        await change_agent(env.deps, "a", {"description": "mine"})
    after = await env.store.load("a")
    assert after.description == "mine"
    assert after.system_prompt == "someone else's"  # never written over


async def test_a_concurrent_approval_switch_write_is_kept(env) -> None:
    await _seed(env)

    async def interfere() -> None:
        await env.store.set_self_revision_requires_approval("a", False)

    patcher, _ = _interfering_load(env.store, interfere)
    with patcher:
        await change_agent(env.deps, "a", {"description": "mine"})
    after = await env.store.load("a")
    assert after.description == "mine"
    assert after.self_revision_requires_approval is False


async def test_a_concurrent_notes_switch_write_is_kept(env) -> None:
    await _seed(env)

    async def interfere() -> None:
        await env.store.set_notes_enabled("a", False)

    patcher, _ = _interfering_load(env.store, interfere)
    with patcher:
        await change_agent(env.deps, "a", {"description": "mine"})
    after = await env.store.load("a")
    assert after.description == "mine"
    assert after.notes_enabled is False


async def test_a_change_that_never_settles_is_a_409_after_two_retries(env) -> None:
    await _seed(env)
    real = env.store.load
    counter = {"n": 0}

    async def load(name: str):
        row = await real(name)
        counter["n"] += 1
        # Interfere after every plan-time load, but not after the precheck's own re-read:
        # the loads alternate plan, precheck, plan, precheck, ...
        if counter["n"] % 2 == 1:
            latest = await real(name)
            await env.store.save(latest.model_copy(update={"max_iterations": counter["n"] + 20}))
        return row

    with patch.object(env.store, "load", load), pytest.raises(AgentWriteError) as exc:
        await change_agent(env.deps, "a", {"description": "mine"})
    assert exc.value.status == 409
    assert exc.value.detail == [{"loc": [], "msg": service.MSG_CHANGED_WHILE_APPLYING}]
    assert (await real("a")).description == "old description"


# ── on_commit is inside the transaction ──────────────────────────────────


async def test_a_raise_from_on_commit_rolls_back_the_agent_write(env) -> None:
    await _seed(env)

    async def boom(conn) -> None:
        await conn.execute("UPDATE agents SET description = 'in-hook' WHERE name = 'a'")
        raise RuntimeError("hook failed")

    with pytest.raises(RuntimeError, match="hook failed"):
        await change_agent(env.deps, "a", {"description": "mine"}, on_commit=boom)
    assert (await env.store.load("a")).description == "old description"


async def test_on_commit_runs_after_the_upsert_in_the_same_transaction(env) -> None:
    await _seed(env)
    seen: list[str] = []

    async def hook(conn) -> None:
        async with conn.execute("SELECT description FROM agents WHERE name = 'a'") as cur:
            seen.append((await cur.fetchone())[0])

    await change_agent(env.deps, "a", {"description": "mine"}, on_commit=hook)
    assert seen == ["mine"]


async def test_save_without_hooks_is_the_plain_upsert(env) -> None:
    await env.store.save(_full_agent("plain"))
    assert (await env.store.load("plain")).description == "old description"


async def test_a_precheck_raise_rolls_back_and_sees_none_for_a_missing_row(env) -> None:
    seen: list[AgentConfig | None] = []

    def precheck(current):
        seen.append(current)
        raise ValueError("no")

    with pytest.raises(ValueError):
        await env.store.save(_full_agent("fresh"), precheck=precheck)
    assert seen == [None]
    assert not await env.store.exists("fresh")


# ── the self-configuration surface id ────────────────────────────────────


async def test_the_surface_id_is_carried_and_ignored_in_the_source_ids_compare(env) -> None:
    await env.store.save(AgentConfig(name="a", description="d"))
    surface = await manage.enable("a", agent_store=env.store, mcp_repo=env.mcp)
    stored = await env.store.load("a")
    assert surface.id in stored.mcp_source_ids

    # A change that does not touch the list keeps the surface id.
    await change_agent(env.deps, "a", {"description": "mine"})
    assert surface.id in (await env.store.load("a")).mcp_source_ids

    # A change that sets the list without it keeps it too, and a base without the id matches
    # the stored list (which has it): not stale.
    await change_agent(env.deps, "a", {"mcp_source_ids": []}, base={"mcp_source_ids": []})
    assert (await env.store.load("a")).mcp_source_ids == [surface.id]


async def test_a_stale_source_ids_payload_has_no_surface_id(env) -> None:
    await env.store.save(AgentConfig(name="a", description="d"))
    surface = await manage.enable("a", agent_store=env.store, mcp_repo=env.mcp)
    with pytest.raises(AgentStaleError) as exc:
        await change_agent(
            env.deps, "a", {"mcp_source_ids": ["x"]}, base={"mcp_source_ids": ["something-else"]}
        )
    (field,) = exc.value.fields
    assert field["field"] == "mcp_source_ids"
    assert surface.id not in field["current"] and surface.id not in field["proposed"]


# ── create ───────────────────────────────────────────────────────────────


async def test_create_agent_returns_the_config_and_rows(env) -> None:
    cfg, rows = await create_agent(env.deps, {"name": "  fresh  ", "description": "d"})
    assert cfg.name == "fresh"
    assert rows == {}
    assert (await env.store.load("fresh")).description == "d"


async def test_create_racing_an_existing_name_gets_the_409_under_the_lock(env) -> None:
    await env.store.save(AgentConfig(name="taken", description="first"))
    # The cheap check-then-write exists() sees nothing (the race); the lock-held precheck does.
    with (
        patch.object(env.store, "exists", return_value=False),
        pytest.raises(AgentWriteError) as exc,
    ):
        await create_agent(env.deps, {"name": "taken", "description": "second"})
    assert exc.value.status == 409
    assert exc.value.detail[0]["loc"] == ["name"]
    assert (await env.store.load("taken")).description == "first"


async def test_create_with_an_existing_name_is_the_plain_409(env) -> None:
    await env.store.save(AgentConfig(name="taken"))
    with pytest.raises(AgentWriteError) as exc:
        await create_agent(env.deps, {"name": "taken"})
    assert exc.value.status == 409


# ── the route still returns the same 422 shape ───────────────────────────


async def test_the_route_returns_the_422_json_without_an_input_echo(tmp_path) -> None:
    conn = await connect_template_db(tmp_path / "r.db")
    enc = Encryptor(Fernet.generate_key(), key_path=tmp_path / "r.key")
    try:
        with (
            patch("the_one.interfaces.web.api.get_connection", return_value=conn),
            patch("the_one.interfaces.web.api.get_encryptor", return_value=enc),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=shared_app()),
                base_url="http://test",
                headers=auth_headers(),
            ) as client:
                resp = await client.post(
                    "/api/agents", json={"name": "bad", "max_iterations": "ECHO-ME-NOT"}
                )
                assert resp.status_code == 422
                body = resp.json()
                assert "ECHO-ME-NOT" not in resp.text
                assert all("input" not in d for d in body["detail"])
                assert body["detail"][0]["loc"] == ["max_iterations"]
                # A name refusal is the same list shape on loc ["name"].
                resp = await client.post("/api/agents", json={"name": "a/b"})
                assert resp.status_code == 422
                assert resp.json()["detail"][0]["loc"] == ["name"]
    finally:
        await conn.close()


# ── the import boundary ──────────────────────────────────────────────────

_SERVICE_FILES = ("service.py", "write_checks.py", "rules_service.py")


def test_the_services_import_nothing_from_the_interface_layer() -> None:
    root = Path(service.__file__).parent
    offenders: list[str] = []
    for name in _SERVICE_FILES:
        tree = ast.parse((root / name).read_text())
        for node in ast.walk(tree):  # top level AND function-level imports
            if isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            elif isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            else:
                continue
            offenders += [f"{name}:{node.lineno} {m}" for m in modules if "interfaces" in m]
    assert offenders == []
