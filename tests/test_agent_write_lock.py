"""Squawk 0327: writers to one agent are serialized by ``agent_write_lock``.

Each pair runs two writers concurrently against the real store. An await point between a
writer's load and its save is gated on an ``asyncio.Event`` (no sleeps): the first writer
parks there, the second starts, and the test waits until the second either reached its own
await point (no lock: both loaded the old row) or is queued on the lock (lock held), then
releases both. Both changes must survive.
"""

from __future__ import annotations

import asyncio
import dataclasses
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.agent import service as agent_service
from the_one.agent import write_checks
from the_one.agent.service import agent_write_lock
from the_one.db.models import MCPSource
from the_one.db.repositories import AgentRevisionRepository, MCPSourceRepository, SQLiteAgentStore
from the_one.encryption import Encryptor
from the_one.interfaces.web import api as api_module

NAME = "a"
SECRET = "distinctive-secret-value-12345"


@pytest.fixture
async def world(tmp_path):
    conn = await connect_template_db(tmp_path / "t.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "t.key")
    mcp_repo = MCPSourceRepository(conn, encryptor)
    await mcp_repo.create(
        MCPSource(
            id="gh-id",
            name="gh",
            type="streamable-http",
            config={"url": "http://localhost/mcp", "headers": {}},
            secrets={},
        )
    )
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as client:
            resp = await client.post(
                "/api/agents", json={"name": NAME, "description": "orig", "system_prompt": "sp"}
            )
            assert resp.status_code == 201, resp.text
            yield client, conn, encryptor
    await conn.close()


class Gate:
    """A parked await point: ``reached`` is set on entry, then it waits for ``release``."""

    def __init__(self) -> None:
        self.reached = asyncio.Event()
        self.release = asyncio.Event()

    def wrap(self, original):
        async def gated(*args, **kwargs):
            self.reached.set()
            await self.release.wait()
            return await original(*args, **kwargs)

        return gated


async def _queued_or_reached(second: Gate) -> None:
    """Return once the second writer is parked at its gate (unlocked) or queued on the lock."""
    while not second.reached.is_set():
        entry = agent_service._agent_locks.get(NAME)
        if entry is not None and entry[1] >= 2:
            return
        await asyncio.sleep(0)


async def _race(first_coro, first_gate: Gate, second_coro, second_gate: Gate):
    t1 = asyncio.create_task(first_coro)
    await asyncio.wait_for(first_gate.reached.wait(), 10)
    t2 = asyncio.create_task(second_coro)
    await asyncio.wait_for(_queued_or_reached(second_gate), 10)
    first_gate.release.set()
    second_gate.release.set()
    return await asyncio.wait_for(asyncio.gather(t1, t2), 20)


@contextmanager
def _gate_post_validation(gate: Gate):
    with patch.object(
        agent_service, "_post_validation_checks", gate.wrap(agent_service._post_validation_checks)
    ):
        yield


@contextmanager
def _gate_put_credential_validation(gate: Gate):
    """A point only ``replace_agent`` reaches (``change_agent`` never validates incoming
    credentials), for pairs where the other writer shares ``_post_validation_checks``."""
    with patch.object(
        write_checks,
        "validate_mcp_override_credentials",
        gate.wrap(write_checks.validate_mcp_override_credentials),
    ):
        yield


@contextmanager
def _gate_credentials_validation(gate: Gate):
    with patch.object(
        api_module,
        "_validate_mcp_override_credentials",
        gate.wrap(api_module._validate_mcp_override_credentials),
    ):
        yield


async def _stored(conn, encryptor):
    return await SQLiteAgentStore(conn, encryptor).load(NAME)


def _put(client, body):
    return client.put(f"/api/agents/{NAME}", json={"name": NAME, **body})


def _creds(client):
    return client.put(
        f"/api/agents/{NAME}/mcp-overrides/gh-id/credentials",
        json={"headers": {"X-Key": SECRET}},
    )


# --- the registry ---------------------------------------------------------------------


async def test_registry_entry_is_dropped_when_idle():
    async with agent_write_lock("x"):
        assert agent_service._agent_locks["x"][1] == 1
    assert "x" not in agent_service._agent_locks


async def test_registry_releases_on_error_and_cancellation():
    with pytest.raises(RuntimeError):
        async with agent_write_lock("x"):
            raise RuntimeError("boom")
    assert agent_service._agent_locks == {}

    held = asyncio.Event()

    async def holder():
        async with agent_write_lock("x"):
            held.set()
            await asyncio.Event().wait()

    t = asyncio.create_task(holder())
    await held.wait()
    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t
    assert agent_service._agent_locks == {}
    async with agent_write_lock("x"):
        pass


async def test_different_agents_do_not_block_each_other():
    async with agent_write_lock("x"):
        async with agent_write_lock("y"):
            assert set(agent_service._agent_locks) == {"x", "y"}


# --- credentials save + whole-agent PUT (the falsification target) ----------------------


async def test_credentials_then_put_both_survive(world):
    client, conn, encryptor = world
    g_creds, g_put = Gate(), Gate()
    with _gate_credentials_validation(g_creds), _gate_post_validation(g_put):
        r_creds, r_put = await _race(
            _creds(client),
            g_creds,
            _put(client, {"description": "orig", "system_prompt": "new"}),
            g_put,
        )
    assert r_creds.status_code == 200, r_creds.text
    assert r_put.status_code == 200, r_put.text
    stored = await _stored(conn, encryptor)
    assert stored.system_prompt == "new"
    assert stored.mcp_overrides["gh"]["headers"] == {"X-Key": SECRET}


async def test_put_then_credentials_both_survive(world):
    client, conn, encryptor = world
    g_put, g_creds = Gate(), Gate()
    with _gate_post_validation(g_put), _gate_credentials_validation(g_creds):
        r_put, r_creds = await _race(
            _put(client, {"description": "orig", "system_prompt": "new"}),
            g_put,
            _creds(client),
            g_creds,
        )
    assert r_put.status_code == 200, r_put.text
    assert r_creds.status_code == 200, r_creds.text
    stored = await _stored(conn, encryptor)
    assert stored.system_prompt == "new"
    assert stored.mcp_overrides["gh"]["headers"] == {"X-Key": SECRET}


# --- revision approve + whole-agent PUT --------------------------------------------------


@contextmanager
def _gate_revisions_repo(gate: Gate):
    with patch.object(
        api_module, "_agent_revisions_repo", gate.wrap(api_module._agent_revisions_repo)
    ):
        yield


async def _pending_revision(conn):
    rev, _ = await AgentRevisionRepository(conn).upsert_pending_revision(
        agent_name=NAME, field="description", proposed_value="approved", base_value="orig"
    )
    return rev


async def test_put_then_approve_both_survive(world):
    client, conn, encryptor = world
    rev = await _pending_revision(conn)
    g_put, g_appr = Gate(), Gate()
    with _gate_post_validation(g_put), _gate_revisions_repo(g_appr):
        r_put, r_appr = await _race(
            _put(client, {"description": "orig", "rich_visuals": True}),
            g_put,
            client.post(f"/api/agents/{NAME}/self-configuration/revisions/{rev.id}/approve"),
            g_appr,
        )
    assert r_put.status_code == 200, r_put.text
    assert r_appr.status_code == 200, r_appr.text
    stored = await _stored(conn, encryptor)
    assert stored.description == "approved"
    assert stored.rich_visuals is True


async def test_approve_then_put_both_survive(world):
    client, conn, encryptor = world
    rev = await _pending_revision(conn)
    g_appr, g_put = Gate(), Gate()
    with _gate_revisions_repo(g_appr), _gate_post_validation(g_put):
        r_appr, r_put = await _race(
            client.post(f"/api/agents/{NAME}/self-configuration/revisions/{rev.id}/approve"),
            g_appr,
            _put(client, {"description": "approved", "rich_visuals": True}),
            g_put,
        )
    assert r_appr.status_code == 200, r_appr.text
    assert r_put.status_code == 200, r_put.text
    stored = await _stored(conn, encryptor)
    assert stored.description == "approved"
    assert stored.rich_visuals is True


# --- change_agent + whole-agent PUT (regression guard) ------------------------------------


class _GatedMCPRepo:
    """Delegates to the real repository; ``list`` parks on the gate first."""

    def __init__(self, inner, gate: Gate) -> None:
        self._inner = inner
        self._gate = gate

    async def list(self, *args, **kwargs):
        self._gate.reached.set()
        await self._gate.release.wait()
        return await self._inner.list(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._inner, item)


async def _change(world_, gate: Gate):
    deps = await api_module._agent_write_deps()
    deps = dataclasses.replace(deps, mcp_repo=_GatedMCPRepo(deps.mcp_repo, gate))
    return await agent_service.change_agent(deps, NAME, {"rich_visuals": True})


async def test_change_then_put_both_survive(world):
    client, conn, encryptor = world
    g_change, g_put = Gate(), Gate()
    with _gate_put_credential_validation(g_put):
        _, r_put = await _race(
            _change(world, g_change), g_change, _put(client, {"description": "put-desc"}), g_put
        )
    assert r_put.status_code == 200, r_put.text
    stored = await _stored(conn, encryptor)
    assert stored.rich_visuals is True
    assert stored.description == "put-desc"


async def test_put_then_change_both_survive(world):
    client, conn, encryptor = world
    g_put, g_change = Gate(), Gate()
    with _gate_put_credential_validation(g_put):
        r_put, _ = await _race(
            _put(client, {"description": "put-desc"}), g_put, _change(world, g_change), g_change
        )
    assert r_put.status_code == 200, r_put.text
    stored = await _stored(conn, encryptor)
    assert stored.rich_visuals is True
    assert stored.description == "put-desc"
