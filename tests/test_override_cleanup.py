"""Sortie 07 leg 4 - the one-time cleanup of copied tool-override values (DD13)."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db, copy_template
from the_one.agent.config import AgentConfig
from the_one.db.override_cleanup import MARKER_KEY, cleanup_copied_overrides
from the_one.db.repositories import (
    AppMetadataRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.encryption import Encryptor


@pytest.fixture
async def env(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    enc = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    ns = SimpleNamespace(
        conn=conn,
        store=SQLiteAgentStore(conn, enc),
        tools=ToolConfigRepository(conn, enc),
        meta=AppMetadataRepository(conn),
    )
    yield ns
    await conn.close()


async def _agent(env, name: str, overrides) -> None:
    await env.store.save(AgentConfig(name=name, tool_overrides=overrides))


async def _overrides(env, name: str):
    return (await env.store.load(name)).tool_overrides


async def _run(env) -> None:
    await cleanup_copied_overrides(env.conn, env.store, env.tools, env.meta)


async def test_drops_fields_equal_to_the_app_wide_value(env) -> None:
    await env.tools.upsert("shell", {"timeout_seconds_max": 60})
    await _agent(
        env,
        "a",
        {
            # default (30) and the redirect-free fields equal the schema defaults;
            # the max equals the stored row; output cap differs and stays.
            "shell": {
                "timeout_seconds_default": 30,
                "timeout_seconds_max": 60,
                "output_cap_bytes": 1000,
                "sandbox_network_allowed": False,
            }
        },
    )
    await _run(env)
    assert await _overrides(env, "a") == {"shell": {"output_cap_bytes": 1000}}


async def test_lists_compare_as_sets_and_deny_lists_lose_app_wide_entries(env) -> None:
    await env.tools.upsert("read_file", {"path_allowlist": ["/a", "/b"], "path_denylist": ["/x"]})
    await _agent(
        env,
        "a",
        {
            "read_file": {
                "path_allowlist": ["/b", "/a"],  # same set as the app-wide list
                "path_denylist": ["/x", "/mine"],  # the app-wide entry goes, the agent's stays
            }
        },
    )
    await _run(env)
    assert await _overrides(env, "a") == {"read_file": {"path_denylist": ["/mine"]}}


async def test_deny_list_of_only_app_wide_entries_and_emptied_tools_go(env) -> None:
    await env.tools.upsert("read_file", {"path_denylist": ["/x"]})
    await _agent(
        env,
        "a",
        {"read_file": {"path_denylist": ["/x"]}, "shell": {"timeout_seconds_default": 30}},
    )
    await _run(env)
    assert await _overrides(env, "a") is None


async def test_dead_keys_and_unknown_tools(env) -> None:
    await _agent(
        env,
        "a",
        {
            "fetch_url": {"redirect_cap": 3, "timeout_seconds_max": 5},
            "no_such_tool": {"x": 1},
        },
    )
    await _run(env)
    assert await _overrides(env, "a") == {
        "fetch_url": {"timeout_seconds_max": 5},
        "no_such_tool": {"x": 1},
    }


async def test_a_value_the_operator_changed_since_stays_a_pin(env) -> None:
    await env.tools.upsert("shell", {"timeout_seconds_max": 60})
    await _agent(env, "a", {"shell": {"timeout_seconds_max": 120}})
    await _run(env)
    assert await _overrides(env, "a") == {"shell": {"timeout_seconds_max": 120}}


async def test_encrypted_mcp_overrides_round_trip(env) -> None:
    cfg = AgentConfig(
        name="a",
        tool_overrides={"shell": {"timeout_seconds_default": 30, "output_cap_bytes": 5}},
        mcp_overrides={"srv": {"env": {"TOKEN": "sekret"}}},
    )
    await env.store.save(cfg)
    await _run(env)
    got = await env.store.load("a")
    assert got.tool_overrides == {"shell": {"output_cap_bytes": 5}}
    assert got.mcp_overrides == {"srv": {"env": {"TOKEN": "sekret"}}}


async def test_marker_written_and_second_start_changes_nothing(env) -> None:
    await _agent(env, "a", {"shell": {"timeout_seconds_default": 30}})
    await _run(env)
    assert await env.meta.get(MARKER_KEY) is not None
    assert await _overrides(env, "a") is None
    # a deliberate own value equal to the app-wide value, saved later, survives a second run
    await _agent(env, "a", {"shell": {"timeout_seconds_default": 30}})
    await _run(env)
    assert await _overrides(env, "a") == {"shell": {"timeout_seconds_default": 30}}


async def test_per_agent_failure_is_logged_by_name_and_marker_written(
    env, monkeypatch, caplog
) -> None:
    await _agent(env, "bad", {"shell": {"timeout_seconds_default": 30}})
    await _agent(env, "good", {"shell": {"timeout_seconds_default": 30}})
    real_load = env.store.load

    async def load(name):
        if name == "bad":
            raise RuntimeError("boom")
        return await real_load(name)

    monkeypatch.setattr(env.store, "load", load)
    with caplog.at_level(logging.WARNING):
        await _run(env)
    assert any("'bad'" in r.getMessage() for r in caplog.records)
    assert await env.meta.get(MARKER_KEY) is not None
    monkeypatch.undo()
    assert await _overrides(env, "bad") == {"shell": {"timeout_seconds_default": 30}}
    assert await _overrides(env, "good") is None


async def test_failure_partway_through_the_loop_still_writes_the_marker(env, monkeypatch) -> None:
    await _agent(env, "a", {"shell": {"timeout_seconds_default": 30}})

    class Exploding:
        # iteration fails after one agent: an error outside the per-agent guard
        def __iter__(self):
            yield "a"
            raise KeyError("loop")

    async def names():
        return Exploding()

    monkeypatch.setattr(env.store, "list_agents", names)
    await _run(env)
    assert await env.meta.get(MARKER_KEY) is not None
    assert await _overrides(env, "a") is None


async def test_failure_before_the_loop_writes_no_marker_and_next_start_retries(
    env, monkeypatch
) -> None:
    await _agent(env, "a", {"shell": {"timeout_seconds_default": 30}})

    async def broken():
        raise RuntimeError("cannot list")

    monkeypatch.setattr(env.store, "list_agents", broken)
    await _run(env)
    assert await env.meta.get(MARKER_KEY) is None
    monkeypatch.undo()
    await _run(env)
    assert await _overrides(env, "a") is None
    assert await env.meta.get(MARKER_KEY) is not None


async def test_tool_config_read_failure_before_the_loop_writes_no_marker(env, monkeypatch) -> None:
    await _agent(env, "a", {"shell": {"timeout_seconds_default": 30}})

    async def broken():
        raise RuntimeError("cannot read tool configs")

    monkeypatch.setattr(env.tools, "list", broken)
    await _run(env)
    assert await env.meta.get(MARKER_KEY) is None


async def test_marker_write_failure_never_raises(env, monkeypatch) -> None:
    async def broken(*_a, **_k):
        raise RuntimeError("disk")

    monkeypatch.setattr(env.meta, "set", broken)
    await _run(env)  # no exception


async def test_marker_read_failure_never_raises(env, monkeypatch) -> None:
    async def broken(*_a, **_k):
        raise RuntimeError("disk")

    monkeypatch.setattr(env.meta, "get", broken)
    await _run(env)


# -- startup ------------------------------------------------------------------


@pytest.fixture
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from the_one.config import settings
    from the_one.db import connection as db_connection

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    copy_template(settings.db_path)
    monkeypatch.setattr(db_connection, "_connection", None)
    yield tmp_path
    monkeypatch.setattr(db_connection, "_connection", None)


async def _seed(path, overrides_json: str) -> None:
    import aiosqlite

    async with aiosqlite.connect(str(path)) as db:
        await db.execute(
            "INSERT INTO agents (name, tool_overrides) VALUES ('a', ?)", (overrides_json,)
        )
        await db.commit()


@pytest.mark.usefixtures("reset_lifespan_singletons")
async def test_lifespan_runs_the_cleanup_once_and_a_failure_never_stops_startup(
    _isolated_data_dir, monkeypatch
) -> None:
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from the_one.config import settings
    from the_one.interfaces.web import app as app_module
    from the_one.interfaces.web.app import app

    await _seed(
        settings.db_path, '{"shell": {"timeout_seconds_default": 30, "output_cap_bytes": 9}}'
    )
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://127.0.0.1", headers=auth_headers()
        ) as client:
            got = (await client.get("/api/agents/a")).json()
            assert got["tool_overrides"] == {"shell": {"output_cap_bytes": 9}}

    # a raising cleanup is guarded at the call site: startup still serves
    async def boom(*_a, **_k):
        raise RuntimeError("injected")

    monkeypatch.setattr(app_module, "cleanup_copied_overrides", boom)
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://127.0.0.1", headers=auth_headers()
        ) as client:
            assert (await client.get("/api/agents/a")).status_code == 200
