"""In-process, real-network tests for the self-configuration surface (M21
F01 L02) — AC3, AC8.

Mirrors the re-entrancy probe's mechanism (flight log Session Notes): one
asyncio event loop, one process, a real `uvicorn.Server` bound to an
OS-allocated port running as a background task, and the platform's own
client path (`AgentFactory.create` → `MCPToolProvider.get_tools_for_agent`
→ the F4 pool → the SDK's streamable-http client) dialing back into that
same server over loopback.

Why a FRESH `FastMCP` instance per test (not the process-wide
`the_one.interfaces.web.app.app` singleton): the SDK's
`StreamableHTTPSessionManager.run()` may be entered at most ONCE per
instance ever. By the time this file's tests run, many earlier tests in
the same pytest process have already cycled `the_one.interfaces.web.app
.app`'s lifespan via `TestClient` — `app.py`'s
`_self_configuration_session_scope` guard means only the FIRST such cycle
actually calls `.run()` on that shared instance, so it is long since
closed. `importlib.reload(the_one.self_configuration.surface)` yields a
brand-new `FastMCP` with an unstarted session manager (and a fresh
`@mcp.tool()` registration of the SAME two tool functions), which this
file's minimal test app mounts and wraps `.run()` around exactly once.
"""

from __future__ import annotations

import asyncio
import importlib
import socket
import time
from contextlib import asynccontextmanager

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from tests._credential_helpers import auth_headers
from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.config import settings
from the_one.db import init_db
from the_one.db.connection import close_connection, get_connection
from the_one.db.models import LLMProviderConfig
from the_one.db.repositories import LLMProviderRepository, MCPSourceRepository, SQLiteAgentStore
from the_one.encryption import get_encryptor
from the_one.interfaces.web.api import router as api_router
from the_one.interfaces.web.middleware import CredentialGateMiddleware
from the_one.mcp._tool_provider import MCPToolProvider
from the_one.self_configuration import credentials as sc_credentials
from the_one.self_configuration import manage as sc_manage


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _wait_ready(base_url: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.get(f"{base_url}/api/live", timeout=1.0)
                if resp.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.05)
    raise RuntimeError(f"server on {base_url} did not become ready within {timeout}s")


@pytest.fixture
async def running_surface(isolated_db, monkeypatch):
    """Spin up a fresh, minimal app (real gate + real API router + a freshly
    reloaded self-configuration surface) on an OS-allocated port, in this
    process. Yields the base_url. Tears down cleanly.
    """
    sc_credentials.clear_for_test()
    sc_credentials.reset_registration_for_test()

    from the_one.self_configuration import surface as surface_mod

    importlib.reload(surface_mod)

    port = _free_port()
    monkeypatch.setattr(settings, "port", port)
    monkeypatch.setattr(settings, "host", "127.0.0.1")

    @asynccontextmanager
    async def test_lifespan(app: FastAPI):
        await init_db()
        conn = await get_connection()
        async with surface_mod.mcp.session_manager.run():
            sc_credentials.register_credential_source_once()
            encryptor = get_encryptor(settings.data_dir)
            mcp_repo = MCPSourceRepository(conn, encryptor)
            agent_store = SQLiteAgentStore(conn, encryptor)
            await sc_manage.reconcile_on_startup(mcp_repo, agent_store)
            yield
        await close_connection()

    test_app = FastAPI(lifespan=test_lifespan)
    test_app.add_middleware(CredentialGateMiddleware)
    test_app.include_router(api_router)
    test_app.mount(surface_mod.MOUNT_PATH, surface_mod.mcp.streamable_http_app())

    @test_app.get("/api/live")
    async def _live() -> dict[str, str]:
        return {"status": "ok"}

    config = uvicorn.Config(test_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    base_url = f"http://127.0.0.1:{port}"
    try:
        await _wait_ready(base_url)
        yield base_url
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, timeout=10.0)
        sc_credentials.clear_for_test()
        sc_credentials.reset_registration_for_test()
        # `importlib.reload` mutates the module object IN PLACE (same
        # identity) — `the_one.interfaces.web.app`'s own
        # `_self_configuration_surface` name binding is that SAME object,
        # so it now points at whatever `.mcp` this reload leaves behind.
        # Reload ONE MORE TIME here so the shared module ends this test
        # with a FRESH, never-started `FastMCP`/session-manager — leaving
        # a just-used-and-closed one in place would make the real app's
        # own (or the next test's) first `lifespan` cycle crash with
        # the SDK's once-per-instance `RuntimeError` the moment it tries
        # `session_manager.run()`.
        importlib.reload(surface_mod)


async def _seed_agent_with_provider(agent_name: str) -> None:
    """Create a mock-provider-backed agent directly against the singleton
    DB connection the running test app's lifespan just opened (same
    process, same event loop — no cross-process DB access needed)."""
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    provider_repo = LLMProviderRepository(conn, encryptor)
    provider = LLMProviderConfig(
        id=f"prov-{agent_name}", name="mock-provider", type="mock", base_url=""
    )
    await provider_repo.create(provider)

    store = SQLiteAgentStore(conn, encryptor)
    cfg = AgentConfig(name=agent_name, provider_config_id=provider.id, llm_model="mock-default")
    await store.save(cfg)


async def _clear_surface_cache(source_id: str) -> None:
    """AC3's "with the cache cleared" — forces `MCPToolProvider.
    get_tools_for_agent` off the cache-first Path B and onto the real
    acquire()+list_tools() Path A, so the assertion actually proves the
    network round trip works rather than reading back what `enable()`
    wrote in-process."""
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    mcp_repo = MCPSourceRepository(conn, encryptor)
    row = await mcp_repo.get(source_id)
    new_config = dict(row.config)
    new_config.pop("_cache", None)
    await mcp_repo.update(row.model_copy(update={"config": new_config}))


class TestAC3ClientPresentsCredential:
    async def test_agent_build_reaches_surface_through_the_pool(self, running_surface: str) -> None:
        base_url = running_surface
        async with httpx.AsyncClient(base_url=base_url, headers=auth_headers()) as client:
            await _seed_agent_with_provider("a-pool")
            resp = await client.post("/api/agents/a-pool/self-configuration")
            assert resp.status_code == 200, resp.text
            agent = (await client.get("/api/agents/a-pool")).json()
            source_id = agent["mcp_source_ids"][0]

        await _clear_surface_cache(source_id)

        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        store = SQLiteAgentStore(conn, encryptor)
        factory = AgentFactory(store=store)
        agent_obj = await factory.create("a-pool")

        tool_names = set(agent_obj.tools.tool_names)
        assert any(name.endswith("get_my_configuration") for name in tool_names)
        assert any(name.endswith("describe_my_capabilities") for name in tool_names)

    async def test_gate_stamps_caller_from_self_configuration_source(
        self, running_surface: str
    ) -> None:
        """Directly drives `MCPToolProvider.get_tools_for_agent` (the exact
        function `AgentFactory.create` delegates MCP attach to) and asserts
        the round trip actually happened by checking the returned tool
        catalog matches the surface's own two-tool shape — the tools can
        only have been returned if the gate admitted the `agt` bearer and
        stamped a `source="self-configuration"` caller (any other outcome
        is a 401/403/error and `get_tools_for_agent` graceful-skips to an
        empty list for that source, per its documented failure classes)."""
        base_url = running_surface
        async with httpx.AsyncClient(base_url=base_url, headers=auth_headers()) as client:
            await _seed_agent_with_provider("a-gate")
            await client.post("/api/agents/a-gate/self-configuration")
            agent = (await client.get("/api/agents/a-gate")).json()
            source_id = agent["mcp_source_ids"][0]

        await _clear_surface_cache(source_id)

        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        store = SQLiteAgentStore(conn, encryptor)
        cfg = await store.load("a-gate")
        provider = MCPToolProvider()
        tools = await provider.get_tools_for_agent(cfg, agent_name="a-gate")
        names = {t.name for t in tools}
        assert any(n.endswith("get_my_configuration") for n in names)
        assert any(n.endswith("describe_my_capabilities") for n in names)


class TestAC8PerToolControlThroughExistingMachinery:
    async def test_operator_disabled_tool_is_absent_via_get_tools_for_agent(
        self, running_surface: str
    ) -> None:
        base_url = running_surface
        async with httpx.AsyncClient(base_url=base_url, headers=auth_headers()) as client:
            await _seed_agent_with_provider("a-tool")
            await client.post("/api/agents/a-tool/self-configuration")
            agent = (await client.get("/api/agents/a-tool")).json()
            source_id = agent["mcp_source_ids"][0]
            source_name = "self-configuration"

            put_resp = await client.put(
                "/api/agents/a-tool",
                json={
                    "name": "a-tool",
                    "provider_config_id": agent["provider_config_id"],
                    "llm_model": agent["llm_model"],
                    "mcp_source_ids": agent["mcp_source_ids"],
                    "mcp_overrides": {
                        source_name: {"disabled_tools": ["describe_my_capabilities"]}
                    },
                },
            )
            assert put_resp.status_code == 200, put_resp.text

        await _clear_surface_cache(source_id)

        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        store = SQLiteAgentStore(conn, encryptor)
        cfg = await store.load("a-tool")
        provider = MCPToolProvider()
        tools = await provider.get_tools_for_agent(cfg, agent_name="a-tool")
        names = {t.name for t in tools}
        assert any(n.endswith("get_my_configuration") for n in names)
        assert not any(n.endswith("describe_my_capabilities") for n in names)


class TestAC4DD9InToolRefusal:
    """DD9: a registry entry that still resolves to *some* identity but
    whose row has been deleted underneath it, or whose owner's
    ``mcp_source_ids`` no longer contains it, is refused INSIDE THE TOOL
    (an error result, never a stack) — distinct from AC4's other half
    (the credential-registry-level refusal after a proper `disable()`,
    covered in `tests/test_self_configuration_api.py`). Both refusals are
    asserted here, not assumed."""

    async def test_owner_detached_but_row_present_is_refused_inside_tool(
        self, running_surface: str
    ) -> None:
        base_url = running_surface
        async with httpx.AsyncClient(base_url=base_url, headers=auth_headers()) as client:
            await _seed_agent_with_provider("a-dd9a")
            await client.post("/api/agents/a-dd9a/self-configuration")
            agent = (await client.get("/api/agents/a-dd9a")).json()
            source_id = agent["mcp_source_ids"][0]

        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        store = SQLiteAgentStore(conn, encryptor)
        mcp_repo = MCPSourceRepository(conn, encryptor)

        # Simulate a legitimate operator detach (PUT dropping the id from
        # mcp_source_ids) WITHOUT going through disable() — the row and
        # its registered credential are both still live; only the
        # ownership check should fail.
        cfg = await store.load("a-dd9a")
        await store.save(cfg.model_copy(update={"mcp_source_ids": []}))

        row = await mcp_repo.get(source_id)
        from the_one.mcp.client import MCPClient
        from the_one.mcp.errors import MCPCallError

        async with MCPClient(source=row, auth_provider=None) as mcp_client:
            with pytest.raises(MCPCallError, match="disabled"):
                await mcp_client.call_tool("get_my_configuration", {})

    async def test_row_deleted_underneath_registered_credential_is_refused(
        self, running_surface: str
    ) -> None:
        base_url = running_surface
        async with httpx.AsyncClient(base_url=base_url, headers=auth_headers()) as client:
            await _seed_agent_with_provider("a-dd9b")
            await client.post("/api/agents/a-dd9b/self-configuration")
            agent = (await client.get("/api/agents/a-dd9b")).json()
            source_id = agent["mcp_source_ids"][0]

        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        row = await mcp_repo.get(source_id)

        # Delete the row directly (bypassing disable()) — the credential
        # stays registered in the in-memory registry, but the row it
        # points at is gone.
        await mcp_repo.delete(source_id)

        from the_one.mcp.client import MCPClient
        from the_one.mcp.errors import MCPCallError

        async with MCPClient(source=row, auth_provider=None) as mcp_client:
            with pytest.raises(MCPCallError, match="disabled"):
                await mcp_client.call_tool("get_my_configuration", {})
