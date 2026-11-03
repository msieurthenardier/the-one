"""Sortie 09 leg 1: resolve-at-connect (DD7), eviction hooks, and the end-to-end proof.

The end-to-end tests drive real saves through the API app on this test's own event
loop (never the sync TestClient: ``_evict`` awaits a worker task on this loop) against
the in-process key-checking server, reached through the FACTORY form of the
transport's test seam (a fresh client per connection, so an old key never leaks
across reconnects).
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import patch

import httpx2
import pytest
from asgi_lifespan import LifespanManager
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from tests.fixtures.mcp.key_server import make_key_app
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository, SQLiteAgentStore
from the_one.encryption import Encryptor
from the_one.mcp import _pool
from the_one.mcp._tool_provider import MCPToolProvider, make_source_resolver
from the_one.mcp.errors import MCPConnectionError
from the_one.mcp.transports import streamable_http as sh

SECRET = "distinctive-secret-value-98765"
SID = "src-keyed"
KEY1, KEY2, KEY3 = "alpha-key-1", "beta-key-22", "gamma-key-333"
TAIL1, TAIL2, TAIL3 = KEY1[-4:], KEY2[-4:], KEY3[-4:]


@pytest.fixture(autouse=True)
async def _clear_pool():
    await _pool._clear_for_test()
    yield
    await _pool._clear_for_test()


@pytest.fixture(autouse=True)
def _long_ttl(monkeypatch):
    monkeypatch.setattr(_pool, "_resolve_ttl_seconds", lambda: 3600)
    monkeypatch.setattr(_pool, "_WORKER_TEARDOWN_TIMEOUT_SECONDS", 2.0)


# --- AC9: acquire(resolve_source=...) ---------------------------------------------


def _plain_source(url="http://localhost/mcp") -> MCPSource:
    return MCPSource(id=SID, name="srv", type="streamable-http", config={"url": url})


class _FakeClient:
    def __init__(self, source, auth_provider=None, **kw):
        self.source = source
        self.is_alive = True
        self.last_activity = 0.0

    async def connect(self):
        return None

    async def disconnect(self):
        return None

    def _touch_activity(self):
        return None


async def test_resolver_runs_once_per_connection_never_on_a_warm_entry(monkeypatch):
    seen_sources = []

    class Client(_FakeClient):
        def __init__(self, source, auth_provider=None, **kw):
            super().__init__(source, auth_provider)
            seen_sources.append(source)

    monkeypatch.setattr(_pool, "MCPClient", Client)
    monkeypatch.setattr("the_one.mcp.oauth.build_oauth_provider_for_source", lambda *a, **k: None)
    calls = []
    resolved = _plain_source("http://resolved/mcp")

    async def resolver():
        calls.append(1)
        return resolved

    build_time = _plain_source("http://build-time/mcp")
    for _ in range(3):
        await _pool.acquire("a", SID, source_override=build_time, resolve_source=resolver)
    assert calls == [1]
    assert seen_sources == [resolved]  # the connection opened with the RESOLVED source


async def test_a_resolver_that_raises_fails_every_waiter_and_hangs_none(monkeypatch):
    monkeypatch.setattr(_pool, "MCPClient", _FakeClient)

    async def boom():
        await asyncio.sleep(0.05)  # let the second acquire join the same entry
        raise MCPConnectionError("resolver said no")

    async def one():
        return await _pool.acquire("a", SID, source_override=_plain_source(), resolve_source=boom)

    results = await asyncio.wait_for(
        asyncio.gather(one(), one(), return_exceptions=True), timeout=5
    )
    assert all(isinstance(r, MCPConnectionError) for r in results), results
    assert ("a", SID) not in _pool._pool  # the failed entry was popped


async def test_an_oauth_provider_build_failure_is_a_failure_not_a_hang(monkeypatch):
    monkeypatch.setattr(_pool, "MCPClient", _FakeClient)

    def bad_factory(*a, **k):
        raise RuntimeError("provider build exploded")

    monkeypatch.setattr("the_one.mcp.oauth.build_oauth_provider_for_source", bad_factory)
    with patch("the_one.mcp._pool.get_connection", return_value=object()):
        with patch("the_one.mcp._pool.get_encryptor", return_value=object()):
            with pytest.raises(RuntimeError, match="provider build exploded"):
                await asyncio.wait_for(
                    _pool.acquire("a", SID, source_override=_plain_source()), timeout=5
                )


async def test_evict_all_for_agent_evicts_every_source_of_that_agent_only(monkeypatch):
    monkeypatch.setattr(_pool, "MCPClient", _FakeClient)
    monkeypatch.setattr("the_one.mcp.oauth.build_oauth_provider_for_source", lambda *a, **k: None)
    for agent, sid in (("a", "s1"), ("a", "s2"), ("b", "s1")):
        src = _plain_source().model_copy(update={"id": sid})
        await _pool.acquire(agent, sid, source_override=src)
    await _pool._evict_all_for_agent("a")
    assert set(_pool._pool) == {("b", "s1")}
    await _pool._evict_all_for_agent("nobody")  # idempotent on no match


# --- API + in-process key server fixture ------------------------------------------


@pytest.fixture
async def world(tmp_path, monkeypatch):
    conn = await connect_template_db(tmp_path / "w.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "w.key")
    repo = MCPSourceRepository(conn, encryptor)
    key_app = make_key_app(
        "X-Api-Key", {KEY1: ["echo"], KEY2: ["echo", "add"], KEY3: ["echo", "add"]}
    )

    def factory(headers):
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=key_app),
            base_url="http://localhost",
            headers=headers,
        )

    monkeypatch.setattr(sh, "_test_http_client_override", factory)
    await repo.create(
        MCPSource(
            id=SID,
            name="srv",
            type="streamable-http",
            config={"url": "http://localhost/mcp", "headers": {"X-Api-Key": ""}},
        )
    )
    patches = [patch(f"{mod}.get_connection", return_value=conn) for mod in _MODULES] + [
        patch(f"{mod}.get_encryptor", return_value=encryptor) for mod in _MODULES
    ]
    for p in patches:
        p.start()
    try:
        async with LifespanManager(key_app):
            async with AsyncClient(
                transport=ASGITransport(app=shared_app()),
                base_url="http://test",
                headers=auth_headers(),
            ) as api:
                yield api, repo, key_app, conn, encryptor
    finally:
        for p in patches:
            p.stop()
        await conn.close()


_MODULES = (
    "the_one.interfaces.web.api",
    "the_one.mcp._tool_provider",
    "the_one.mcp._pool",
)


async def _save_agent(api, name, key=None, *, method="post"):
    body = {"name": name, "mcp_source_ids": [SID]}
    if key is not None:
        body["mcp_overrides"] = {"srv": {"headers": {"X-Api-Key": key}}}
    if method == "post":
        resp = await api.post("/api/agents", json=body)
        assert resp.status_code == 201, resp.text
    else:
        resp = await api.put(f"/api/agents/{name}", json=body)
        assert resp.status_code == 200, resp.text


async def _tools_for(conn, encryptor, name):
    cfg = await SQLiteAgentStore(conn, encryptor).load(name)
    tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name=name)
    return {t.name: t for t in tools}


def _calls(key_app):
    return [e["key_tail"] for e in key_app.log if e["method"] == "tools/call"]


async def test_a_saved_key_reaches_the_next_call_of_the_same_open_tool(world):
    """AC12: the open chat's own tool instance sends the NEW key after a save."""
    api, _, key_app, conn, enc = world
    await _save_agent(api, "a", KEY1)
    tools = await _tools_for(conn, enc, "a")
    echo = tools["mcp__srv__echo"]
    assert "hi" in await echo.execute(message="hi")
    assert _calls(key_app) == [TAIL1]

    await _save_agent(api, "a", KEY2, method="put")  # the connection is evicted here
    assert "again" in await echo.execute(message="again")  # the SAME tool object
    assert _calls(key_app) == [TAIL1, TAIL2]
    # and a further call reuses the new warm connection
    await echo.execute(message="third")
    assert _calls(key_app) == [TAIL1, TAIL2, TAIL2]


async def test_two_agents_on_one_source_each_reach_it_with_their_own_key(world):
    api, _, key_app, conn, enc = world
    await _save_agent(api, "a", KEY1)
    await _save_agent(api, "b", KEY2)
    ta = await _tools_for(conn, enc, "a")
    tb = await _tools_for(conn, enc, "b")
    assert set(ta) == {"mcp__srv__echo"}  # each listing was made with its own key
    assert set(tb) == {"mcp__srv__echo", "mcp__srv__add"}
    await ta["mcp__srv__echo"].execute(message="x")
    await tb["mcp__srv__echo"].execute(message="y")
    await tb["mcp__srv__add"].execute(a=1, b=2)
    assert _calls(key_app) == [TAIL1, TAIL2, TAIL2]


async def test_an_unchanged_save_keeps_the_warm_connection(world):
    api, _, key_app, conn, enc = world
    await _save_agent(api, "a", KEY1)
    echo = (await _tools_for(conn, enc, "a"))["mcp__srv__echo"]
    await echo.execute(message="1")
    entry = _pool._pool[("a", SID)]
    # a Save that round-trips the masked value changes no credential
    resp = await api.get("/api/agents/a")
    body = resp.json()
    assert (await api.put("/api/agents/a", json=body)).status_code == 200
    assert _pool._pool[("a", SID)] is entry
    await echo.execute(message="2")
    assert _pool._pool[("a", SID)] is entry


async def test_the_resolver_is_what_carries_the_new_key_after_an_eviction(world):
    """With the eviction kept but the resolver bypassed, the call would still use
    the build-time copy; pin that the resolver (not the eviction alone) does it."""
    api, _, key_app, conn, enc = world
    await _save_agent(api, "a", KEY1)
    echo = (await _tools_for(conn, enc, "a"))["mcp__srv__echo"]
    await echo.execute(message="1")
    await _save_agent(api, "a", KEY2, method="put")
    seen = []
    real = make_source_resolver

    def spy(agent, sid, fallback):
        inner = real(agent, sid, fallback)

        async def _r():
            src = await inner()
            seen.append(sorted(src.secrets.items()))
            return src

        return _r

    with patch("the_one.mcp._tool_provider.make_source_resolver", spy):
        await echo.execute(message="2")
    assert seen == [[("X-Api-Key", KEY2)]]


async def test_agent_not_in_the_store_uses_the_build_time_source(world):
    _, repo, key_app, conn, enc = world
    src = await repo.get(SID)
    effective = src.model_copy(update={"secrets": {"X-Api-Key": KEY1}})
    resolver = make_source_resolver("ghost-agent", SID, effective)
    assert await resolver() is effective


async def test_resolver_failure_is_a_plain_tool_error_without_exception_text(world, caplog):
    api, repo, key_app, conn, enc = world
    await _save_agent(api, "a", KEY1)
    echo = (await _tools_for(conn, enc, "a"))["mcp__srv__echo"]
    await _pool._evict(("a", SID))
    await repo.delete(SID)  # a deleted source: the resolver cannot load it
    caplog.set_level(logging.DEBUG)
    out = await echo.execute(message="x")
    assert out.startswith("[error] MCP source 'srv' unavailable: MCPConnectionError: ")
    assert KEY1 not in out and KEY1 not in caplog.text

    # and an arbitrary exception whose text carries a value is not echoed either
    async def exploding_load(self, name):
        raise RuntimeError(f"db blew up near {SECRET}")

    with patch.object(SQLiteAgentStore, "load", exploding_load):
        resolver = make_source_resolver("a", SID, _plain_source())
        with pytest.raises(MCPConnectionError) as exc:
            await resolver()
    assert SECRET not in str(exc.value) and SECRET not in caplog.text


# --- AC11: eviction hooks ---------------------------------------------------------


@pytest.fixture
def evictions():
    log = []

    async def ev(key):
        log.append(("key", key))

    async def ev_src(sid):
        log.append(("source", sid))

    async def ev_agent(name):
        log.append(("agent", name))

    with (
        patch("the_one.mcp._pool._evict", ev),
        patch("the_one.mcp._pool._evict_all_for_source", ev_src),
        patch("the_one.mcp._pool._evict_all_for_agent", ev_agent),
    ):
        yield log


async def test_agent_save_evicts_only_sources_whose_credentials_changed(world, evictions):
    api, repo, *_ = world
    await repo.create(
        MCPSource(id="other", name="other", type="streamable-http", config={"url": "http://x/y"})
    )
    await _save_agent(api, "a", KEY1)
    assert evictions == [("key", ("a", SID))]  # create evicts what carries credentials
    evictions.clear()

    # unchanged: masked value round-trip and a tool-filter-only change
    body = (await api.get("/api/agents/a")).json()
    body["mcp_overrides"]["srv"]["enabled_tools"] = ["echo"]
    assert (await api.put("/api/agents/a", json=body)).status_code == 200
    assert evictions == []

    # changed value
    await _save_agent(api, "a", KEY2, method="put")
    assert evictions == [("key", ("a", SID))]
    evictions.clear()

    # a credential cleared
    body = (await api.get("/api/agents/a")).json()
    body["mcp_overrides"]["srv"]["headers"] = None
    assert (await api.put("/api/agents/a", json=body)).status_code == 200
    assert evictions == [("key", ("a", SID))]


async def test_agent_rename_and_delete_evict_every_key_of_the_agent(world, evictions):
    api, *_ = world
    await _save_agent(api, "a")
    resp = await api.post("/api/agents/a/rename", json={"new_name": "b"})
    assert resp.status_code == 200, resp.text
    assert evictions == [("agent", "a")]
    evictions.clear()
    assert (await api.delete("/api/agents/b")).status_code == 200
    assert evictions == [("agent", "b")]


async def test_source_update_evicts_on_type_config_or_secrets_change_only(world, evictions):
    api, repo, *_ = world
    src = (await api.get(f"/api/mcp-sources/{SID}")).json()

    # rename only: the pool key is the source id
    body = dict(src, name="srv-renamed")
    assert (await api.put(f"/api/mcp-sources/{SID}", json=body)).status_code == 200
    assert evictions == []
    # unchanged masked secrets round-trip
    stored = await repo.get(SID)
    await repo.update(stored.model_copy(update={"secrets": {"X-Other": "keep-this-value"}}))
    body = (await api.get(f"/api/mcp-sources/{SID}")).json()
    assert (await api.put(f"/api/mcp-sources/{SID}", json=body)).status_code == 200
    assert evictions == []

    # config change (headers)
    body["config"] = dict(body["config"], headers={"X-Api-Key": "", "X-New": ""})
    assert (await api.put(f"/api/mcp-sources/{SID}", json=body)).status_code == 200
    assert evictions == [("source", SID)]
    evictions.clear()

    # secret change
    body = (await api.get(f"/api/mcp-sources/{SID}")).json()
    body["secrets"] = {"X-Other": "a-different-value"}
    assert (await api.put(f"/api/mcp-sources/{SID}", json=body)).status_code == 200
    assert evictions == [("source", SID)]
