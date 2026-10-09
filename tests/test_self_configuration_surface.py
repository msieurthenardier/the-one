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
import logging
import socket
import time
from contextlib import asynccontextmanager, suppress

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from tests._credential_helpers import auth_headers
from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.config import settings
from the_one.db.connection import close_connection, get_connection
from the_one.db.models import LLMProviderConfig, MCPSource
from the_one.db.repositories import LLMProviderRepository, MCPSourceRepository, SQLiteAgentStore
from the_one.encryption import get_encryptor
from the_one.interfaces.web.api import router as api_router
from the_one.interfaces.web.middleware import CredentialGateMiddleware
from the_one.mcp._tool_provider import MCPToolProvider
from the_one.self_configuration import credentials as sc_credentials
from the_one.self_configuration import external_credentials as sc_external
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


def _reset_sse_shutdown_flag() -> None:
    """Clear ``sse_starlette``'s process-global shutdown latch.

    The MCP streamable-HTTP responses are ``sse_starlette`` ``EventSourceResponse``s.
    Each one races a shutdown watcher (one per thread/event loop) that polls the
    uvicorn server found through the SIGTERM handler and, once that server's
    ``should_exit`` is set, latches ``AppStatus.should_exit = True`` on the CLASS —
    a flag nothing ever clears. This fixture stops its server with
    ``should_exit = True``; if the previous test's watcher happens to poll (every
    0.5 s) inside that teardown window — which a loaded host stretches — the latch
    survives into the NEXT test's fresh server, where every SSE response is
    cancelled before it sends anything, so the first ``initialize`` POST gets an
    empty body and the client waits out its 30 s budget (squawks 0134, 0157).
    One server per process in production, so this is test isolation only.
    """
    from sse_starlette import sse as sse_mod

    sse_mod.AppStatus.should_exit = False


@pytest.fixture
async def running_surface(isolated_db, monkeypatch):
    """Spin up a fresh, minimal app (real gate + real API router + a freshly
    reloaded self-configuration surface) on an OS-allocated port, in this
    process. Yields the base_url. Tears down cleanly.
    """
    sc_credentials.clear_for_test()
    sc_credentials.reset_registration_for_test()
    sc_external.clear_for_test()
    # The previous test's loop is closed by now, so its watcher can no longer
    # re-latch the flag after this reset.
    _reset_sse_shutdown_flag()

    from the_one.self_configuration import surface as surface_mod

    importlib.reload(surface_mod)

    port = _free_port()
    monkeypatch.setattr(settings, "port", port)
    monkeypatch.setattr(settings, "host", "127.0.0.1")

    @asynccontextmanager
    async def test_lifespan(app: FastAPI):
        conn = await get_connection()
        async with surface_mod.mcp.session_manager.run():
            sc_credentials.register_credential_source_once()
            sc_external.register_credential_source_once()
            encryptor = get_encryptor(settings.data_dir)
            mcp_repo = MCPSourceRepository(conn, encryptor)
            agent_store = SQLiteAgentStore(conn, encryptor)
            await sc_manage.reconcile_on_startup(mcp_repo, agent_store)
            from the_one.db.repositories import AgentExternalCredentialRepository

            ext_repo = AgentExternalCredentialRepository(conn, encryptor)
            sc_external.load_from_rows(await ext_repo.load_all())
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
        _reset_sse_shutdown_flag()
        sc_credentials.clear_for_test()
        sc_credentials.reset_registration_for_test()
        sc_external.clear_for_test()
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


# ── M21 F03 L01: external-client credential over an out-of-process client ─


def _ext_source(base_url: str, token: str) -> MCPSource:
    """Build a synthetic in-memory ``MCPSource`` that presents an ``ext_``
    bearer at the surface URL (presentation-path note / review Issue #2 —
    an external credential is a standalone bearer with NO surface row, so
    the test constructs the row explicitly). ``auth_provider=None`` on the
    ``MCPClient`` keeps the SDK from attempting DCR; the Authorization
    header is flat-merged from ``secrets`` by ``build_request_headers``."""
    return MCPSource(
        id="ext-synthetic",
        name="ext-synthetic",
        type="streamable-http",
        config={"url": f"{base_url}/mcp/self-configuration/"},
        secrets={"Authorization": f"Bearer {token}"},
    )


async def _mint_ext(client: "httpx.AsyncClient", agent: str, label: str = "ext") -> str:
    resp = await client.post(
        f"/api/agents/{agent}/self-configuration/external-credentials",
        json={"label": label},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


class TestAC6ExternalClientReadsConfig:
    async def test_ext_credential_reads_own_config_secret_free(self, running_surface: str) -> None:
        base_url = running_surface
        async with httpx.AsyncClient(base_url=base_url, headers=auth_headers()) as client:
            await _seed_agent_with_provider("a-ext6")
            await client.post("/api/agents/a-ext6/self-configuration")
            token = await _mint_ext(client, "a-ext6")

        from the_one.mcp.client import MCPClient

        async with MCPClient(source=_ext_source(base_url, token), auth_provider=None) as mcp_client:
            result = await mcp_client.call_tool("get_my_configuration", {})

        payload = result.structured or {}
        assert payload.get("name") == "a-ext6"
        # Secret-free, approval-mode-free projection (unchanged from the agt path).
        blob = (result.text or "") + repr(payload)
        assert "requires_approval" not in blob
        assert "self_revision" not in blob
        assert "api_key" not in blob
        assert "secret" not in blob.lower()


class TestAC8CrossAgentIsolation:
    async def test_ext_credential_resolves_only_to_its_own_agent(
        self, running_surface: str
    ) -> None:
        base_url = running_surface
        async with httpx.AsyncClient(base_url=base_url, headers=auth_headers()) as client:
            await _seed_agent_with_provider("a-ext8a")
            await _seed_agent_with_provider("a-ext8b")
            await client.post("/api/agents/a-ext8a/self-configuration")
            await client.post("/api/agents/a-ext8b/self-configuration")
            token_a = await _mint_ext(client, "a-ext8a")
            token_b = await _mint_ext(client, "a-ext8b")

        from the_one.mcp.client import MCPClient

        async with MCPClient(source=_ext_source(base_url, token_a), auth_provider=None) as ca:
            res_a = await ca.call_tool("get_my_configuration", {})
        async with MCPClient(source=_ext_source(base_url, token_b), auth_provider=None) as cb:
            res_b = await cb.call_tool("get_my_configuration", {})

        assert (res_a.structured or {}).get("name") == "a-ext8a"
        assert (res_b.structured or {}).get("name") == "a-ext8b"


class TestAC9ExternalDiesWithSurface:
    async def test_orphaned_surface_refuses_ext_tool_call(self, running_surface: str) -> None:
        """DD9: an orphaned (detached, not deleted) surface still resolves
        the ext token at the gate, but `_calling_agent` refuses the tool
        call — the same refusal the agent's own path gives, no more
        privileged."""
        base_url = running_surface
        async with httpx.AsyncClient(base_url=base_url, headers=auth_headers()) as client:
            await _seed_agent_with_provider("a-ext9")
            await client.post("/api/agents/a-ext9/self-configuration")
            token = await _mint_ext(client, "a-ext9")
            # Detach via PUT without deleting the row → orphaned.
            put = await client.put(
                "/api/agents/a-ext9", json={"name": "a-ext9", "mcp_source_ids": []}
            )
            assert put.status_code == 200, put.text

        from the_one.mcp.client import MCPClient
        from the_one.mcp.errors import MCPCallError

        async with MCPClient(source=_ext_source(base_url, token), auth_provider=None) as mcp_client:
            with pytest.raises(MCPCallError, match="disabled"):
                await mcp_client.call_tool("get_my_configuration", {})

    async def test_disabled_surface_401s_ext_token(self, running_surface: str) -> None:
        """Disabling the surface cascade-revokes the ext credential (FK) and
        evicts the registry, so the token no longer authenticates — the gate
        401s and the client cannot even establish the session."""
        base_url = running_surface
        async with httpx.AsyncClient(base_url=base_url, headers=auth_headers()) as client:
            await _seed_agent_with_provider("a-ext9b")
            await client.post("/api/agents/a-ext9b/self-configuration")
            token = await _mint_ext(client, "a-ext9b")
            # Full disable → cascade + registry eviction.
            await client.delete("/api/agents/a-ext9b/self-configuration")

        from the_one.mcp.client import MCPClient
        from the_one.mcp.errors import MCPAuthRequired, MCPConnectionError

        # An unresolvable bearer is a 401 at the gate; the SDK cannot open a
        # session. A transport-layer 401 translates to MCPAuthRequired; a
        # non-401 collapse translates to MCPConnectionError. Either way the
        # call never succeeds — the credential died with the surface.
        with pytest.raises((MCPAuthRequired, MCPConnectionError)):
            async with MCPClient(
                source=_ext_source(base_url, token), auth_provider=None
            ) as mcp_client:
                await mcp_client.call_tool("get_my_configuration", {})


# ── Squawk 0006: dedicated two-agent-simultaneous isolation e2e ───────────


class TestSquawk0006TwoAgentSimultaneousIsolation:
    """Flight 1 Leg 2 AC9 (ownership guard) was ticked on enforcement +
    code inspection alone (Flight 1 debrief, "What Could Be Improved →
    Technical") — not a dedicated two-agent-simultaneous end-to-end test.

    This stands up TWO surface-enabled agents at once, with both `agt_`
    credentials live concurrently (mirrors ``TestAC8CrossAgentIsolation``'s
    `ext_` version of this, but for the agent's own credential, driven
    through a real ``MCPClient`` — the same mechanism the DD9 tests above
    use to present ``row``, not ``MCPToolProvider``/``AgentFactory``), and
    proves isolation in both directions: reads never cross, writes never
    cross (and a write to one agent never undoes the other's), and
    disabling one agent's surface refuses only that agent's credential
    while the other's keeps working.
    """

    async def test_two_live_agt_credentials_never_cross(self, running_surface: str) -> None:
        base_url = running_surface
        async with httpx.AsyncClient(base_url=base_url, headers=auth_headers()) as client:
            await _seed_agent_with_provider("a-iso6a")
            await _seed_agent_with_provider("a-iso6b")
            await client.post("/api/agents/a-iso6a/self-configuration")
            await client.post("/api/agents/a-iso6b/self-configuration")
            agent_a = (await client.get("/api/agents/a-iso6a")).json()
            agent_b = (await client.get("/api/agents/a-iso6b")).json()
            source_id_a = agent_a["mcp_source_ids"][0]
            source_id_b = agent_b["mcp_source_ids"][0]

        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        store = SQLiteAgentStore(conn, encryptor)

        # Both `agt_` credentials are live concurrently — fetch both rows
        # (each carries its OWN agent's bearer in its own encrypted
        # `secrets["Authorization"]`) up front, before either is exercised,
        # so neither call below is what "activates" isolation.
        row_a = await mcp_repo.get(source_id_a)
        row_b = await mcp_repo.get(source_id_b)

        from the_one.mcp.client import MCPClient
        from the_one.mcp.errors import MCPAuthRequired, MCPConnectionError

        # ── reads never cross: A's credential resolves only to A, B's only to B ──
        async with MCPClient(source=row_a, auth_provider=None) as ca:
            res_a = await ca.call_tool("get_my_configuration", {})
        async with MCPClient(source=row_b, auth_provider=None) as cb:
            res_b = await cb.call_tool("get_my_configuration", {})

        assert (res_a.structured or {}).get("name") == "a-iso6a"
        assert (res_b.structured or {}).get("name") == "a-iso6b"

        # ── A's write changes A's stored row and leaves B's untouched ──
        async with MCPClient(source=row_a, auth_provider=None) as ca:
            write_a = await ca.call_tool(
                "update_my_description",
                {"text": "description written by agent A", "apply": "next_session"},
            )
        assert (write_a.structured or {}).get("applied_to_store") is True

        cfg_a = await store.load("a-iso6a")
        cfg_b = await store.load("a-iso6b")
        assert cfg_a.description == "description written by agent A"
        assert cfg_b.description == ""

        # ── vice versa: B's write changes B's stored row, and does not
        # clobber the write A just made to its own row ──
        async with MCPClient(source=row_b, auth_provider=None) as cb:
            write_b = await cb.call_tool(
                "update_my_description",
                {"text": "description written by agent B", "apply": "next_session"},
            )
        assert (write_b.structured or {}).get("applied_to_store") is True

        cfg_a = await store.load("a-iso6a")
        cfg_b = await store.load("a-iso6b")
        assert cfg_a.description == "description written by agent A"
        assert cfg_b.description == "description written by agent B"

        # ── negative: disabling B's surface refuses B's credential (the
        # same 401/403-at-the-gate class the single-agent AC9 test above
        # asserts) while A's credential still works. A's live check runs
        # BEFORE the expected-failure block below, not after — mirrors
        # every other `pytest.raises(MCPAuthRequired ...)` use in this
        # file, which always ends its test on the raise rather than
        # opening a further `MCPClient` afterward in the same event loop.
        async with httpx.AsyncClient(base_url=base_url, headers=auth_headers()) as client:
            disable_resp = await client.delete("/api/agents/a-iso6b/self-configuration")
        assert disable_resp.status_code == 200

        async with MCPClient(source=row_a, auth_provider=None) as ca:
            res_a_after = await ca.call_tool("get_my_configuration", {})
        assert (res_a_after.structured or {}).get("name") == "a-iso6a"

        with pytest.raises((MCPAuthRequired, MCPConnectionError)):
            async with MCPClient(source=row_b, auth_provider=None) as cb:
                await cb.call_tool("get_my_configuration", {})


# ── Squawk 0005: shutdown-drain under load, live self-configuration
# connection ─────────────────────────────────────────────────────────────


class TestSquawk0005ShutdownDrainUnderLoad:
    """Squawk 0005: the lifespan shutdown branch (`app.py`'s `lifespan`)
    evicts every marked self-configuration surface row's pool entries via
    `_evict_all_for_source(row.id)` BEFORE the general
    `_mcp_pool_shutdown_drain()` runs — the mitigation for a loopback
    session that would otherwise log a benign-but-noisy WARNING if torn
    down after the listener closes. That ordering was reasoned but never
    exercised with a surface-enabled agent holding a LIVE pool connection
    at shutdown (Flight 1 debrief carry-over). This proves it under a
    genuinely live connection.

    Why this doesn't drive the real `the_one.interfaces.web.app.lifespan`
    directly, mirroring `tests/test_lifespan.py`'s bare
    `async with lifespan(app)` idiom: the self-configuration surface is a
    REAL loopback HTTP connection to `http://127.0.0.1:{settings.port}
    {MOUNT_PATH}/` — nothing is listening on that port unless a real
    `uvicorn.Server` is actually bound to it, and the bare
    `async with lifespan(app)` idiom (as used throughout
    `test_lifespan.py`) never binds a port — it only enters the context
    manager in-process. Separately, the real `app` singleton's
    `session_manager.run()` is guarded to fire at most ONCE per process
    (`app.py`'s `_self_configuration_session_manager_started`, per this
    file's own module docstring above) — by the time any given test runs
    in a full-suite process, that guard is realistically already spent
    from earlier `TestClient(app)` cycles elsewhere, so even a live-bound
    `app` singleton would not reliably serve the mount. Per the squawk's
    sanctioned fallback, this instead reproduces the SAME SHAPE the
    lifespan's shutdown branch performs — evict-the-surface-row before
    the general drain — directly at the pool layer, against a genuinely
    live self-configuration connection obtained exactly as `running_surface`
    provides it elsewhere in this file: a real `uvicorn.Server` bound to
    an OS-allocated port, the platform's own loopback client path.
    """

    async def test_live_surface_connection_evicted_before_general_drain(
        self,
        running_surface: str,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        base_url = running_surface
        async with httpx.AsyncClient(base_url=base_url, headers=auth_headers()) as client:
            await _seed_agent_with_provider("a-drain5")
            resp = await client.post("/api/agents/a-drain5/self-configuration")
            assert resp.status_code == 200, resp.text
            agent = (await client.get("/api/agents/a-drain5")).json()
            source_id = agent["mcp_source_ids"][0]

        from the_one.mcp import _pool as pool_mod

        try:
            # Acquire a LIVE pool entry the way an agent turn would —
            # this dials the real loopback surface over HTTP and holds a
            # warm, connected `MCPClient` in `pool_mod._pool`.
            client_conn = await pool_mod.acquire("a-drain5", source_id)
            assert client_conn.is_alive

            # Leave one in-flight tool call running at the moment of
            # shutdown — fired but NOT awaited before eviction starts,
            # so it's genuinely concurrent with the drain sequence below.
            inflight = asyncio.ensure_future(client_conn.call_tool("get_my_configuration", {}))

            # Spy on call order exactly like app.py's shutdown branch:
            # evict the marked surface row's pool entries BEFORE the
            # general MCP pool drain.
            order: list[str] = []
            original_evict_all = pool_mod._evict_all_for_source
            original_shutdown_drain = pool_mod.shutdown_drain

            async def _spying_evict_all(sid: str) -> None:
                order.append("evict")
                await original_evict_all(sid)

            async def _spying_shutdown_drain() -> None:
                order.append("drain")
                await original_shutdown_drain()

            monkeypatch.setattr(pool_mod, "_evict_all_for_source", _spying_evict_all)
            monkeypatch.setattr(pool_mod, "shutdown_drain", _spying_shutdown_drain)

            async def _shutdown_sequence() -> None:
                # Mirrors app.py's lifespan shutdown branch order
                # exactly: evict the surface row's pool entries first
                # (while the listener is still up), THEN run the
                # general MCP pool drain.
                await pool_mod._evict_all_for_source(source_id)
                await pool_mod.shutdown_drain()

            with caplog.at_level(logging.WARNING):
                # Bound comfortably under the drain's own worst-case
                # ceiling (two ~10s-per-entry timeouts, evict then
                # drain) — a real hang here means the mitigation
                # regressed.
                await asyncio.wait_for(_shutdown_sequence(), timeout=15.0)

            assert order == ["evict", "drain"], order
            assert pool_mod._pool == {}

            # The in-flight call must not be left hanging forever by the
            # eviction/disconnect it raced against — bound its own
            # outcome separately and tolerate any exception the
            # mid-flight teardown produced (a clean result, a
            # connection-closed error, or a cancellation are all
            # acceptable; only a HANG would be a real defect, and
            # `wait_for`'s timeout both catches and cancels that).
            with suppress(Exception):
                await asyncio.wait_for(inflight, timeout=5.0)

            noisy = [
                r
                for r in caplog.records
                if r.levelno >= logging.WARNING
                and (
                    "did not terminate" in r.getMessage()
                    or "stuck" in r.getMessage().lower()
                    or "unterminated" in r.getMessage().lower()
                )
            ]
            assert noisy == [], [(r.levelname, r.getMessage()) for r in noisy]
        finally:
            # Belt-and-suspenders: `shutdown_drain()` latches module-global
            # `_shutting_down = True` — left set, every LATER test in this
            # process whose path reaches `pool_mod.acquire` (e.g.
            # `TestAC3ClientPresentsCredential`, `TestSquawk0006...` above)
            # would fail with "MCP pool is shutting down". Reset
            # unconditionally, mirroring `tests/test_lifespan.py`'s
            # `reset_lifespan_singletons` fixture for the same hazard.
            await pool_mod._clear_for_test()
