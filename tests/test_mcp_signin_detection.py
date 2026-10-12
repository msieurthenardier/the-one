"""DD1: sign-in detection by a scoped, sequenced 401 record (Mission 29, mcp 2.x port).

mcp 2.x no longer surfaces HTTP 401 (a POST 401 becomes ``MCPError(INTERNAL_ERROR,
"Server returned an error response")`` and the headers are dropped), so
``MCPClient`` reads a record the transport's response hook keeps. Every test here
runs against a REAL HTTP server - the in-repo ``OAuthASStub`` over loopback or the
``Auth401Wrapper`` ASGI wrapper around the ``hello_server`` app - never an injected
``HTTPStatusError``.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx2
import pytest
from asgi_lifespan import LifespanManager

from tests._mcp_signin_helpers import build_provider, http_source
from tests.fixtures.mcp.asgi_401 import RESOURCE_METADATA, Auth401Wrapper
from tests.fixtures.mcp.hello_server import make_http_app
from tests.fixtures.oauth import OAuthASStub
from the_one.db.models import MCPSource
from the_one.mcp.client import MCPClient
from the_one.mcp.errors import MCPAuthRequired, MCPConnectionError
from the_one.mcp.transports import streamable_http as sh

ASGI_URL = "http://localhost/mcp"


def _asgi_source() -> MCPSource:
    return MCPSource(
        id="src-asgi",
        name="asgi",
        type="streamable-http",
        config={"url": ASGI_URL, "headers": {}},
        secrets={},
    )


@asynccontextmanager
async def _wrapped_asgi(monkeypatch, **wrapper_kwargs):
    """The hello_server ASGI app behind an ``Auth401Wrapper``, wired through the
    transport's test seam. Yields ``(wrapper, httpx2_client)``."""
    wrapper = Auth401Wrapper(make_http_app(), **wrapper_kwargs)
    async with LifespanManager(wrapper):
        client = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=wrapper), base_url="http://localhost"
        )
        monkeypatch.setattr(sh, "_test_http_client_override", client)
        try:
            yield wrapper, client
        finally:
            await client.aclose()


# ---------------------------------------------------------------------------
# AC7(a): a no-provider 401 yields MCPAuthRequired(resource_metadata_url=...)
# ---------------------------------------------------------------------------


async def test_connect_401_yields_auth_required_with_resource_metadata(monkeypatch) -> None:
    async with _wrapped_asgi(monkeypatch, fail_methods={"initialize"}) as (wrapper, _):
        c = MCPClient(_asgi_source())
        with pytest.raises(MCPAuthRequired) as exc_info:
            await c.connect()
    assert exc_info.value.source_id == "src-asgi"
    assert exc_info.value.resource_metadata_url == RESOURCE_METADATA
    assert exc_info.value.consent_url is None
    assert c.is_alive is False


async def test_list_tools_401_yields_auth_required_with_resource_metadata(monkeypatch) -> None:
    async with _wrapped_asgi(monkeypatch, fail_methods={"tools/list"}) as (wrapper, _):
        c = MCPClient(_asgi_source())
        await c.connect()
        try:
            with pytest.raises(MCPAuthRequired) as exc_info:
                await c.list_tools()
        finally:
            await c.disconnect()
    assert exc_info.value.resource_metadata_url == RESOURCE_METADATA


async def test_call_tool_401_yields_auth_required_with_resource_metadata(monkeypatch) -> None:
    async with _wrapped_asgi(monkeypatch, fail_methods={"tools/call"}) as (wrapper, _):
        c = MCPClient(_asgi_source())
        await c.connect()
        try:
            await c.list_tools()  # the tools/list POST passes; only tools/call 401s
            with pytest.raises(MCPAuthRequired) as exc_info:
                await c.call_tool("echo", {"message": "hi"})
        finally:
            await c.disconnect()
    assert exc_info.value.resource_metadata_url == RESOURCE_METADATA


async def test_401_with_json_rpc_error_body_still_yields_auth_required(monkeypatch) -> None:
    """A 401 whose body is a JSON-RPC error reaches the client as the server's
    own MCPError code (not INTERNAL_ERROR): DD1 must not gate on the code."""
    async with _wrapped_asgi(monkeypatch, fail_methods={"tools/list"}, json_rpc_body=True) as (
        wrapper,
        _,
    ):
        c = MCPClient(_asgi_source())
        await c.connect()
        try:
            with pytest.raises(MCPAuthRequired) as exc_info:
                await c.list_tools()
        finally:
            await c.disconnect()
    assert exc_info.value.resource_metadata_url == RESOURCE_METADATA


# ---------------------------------------------------------------------------
# AC7(b): a 401 recorded during an earlier operation does not misfire later
# ---------------------------------------------------------------------------


async def test_stale_401_does_not_turn_a_later_failure_into_auth_required(monkeypatch) -> None:
    async with _wrapped_asgi(monkeypatch, fail_methods={"tools/list"}, remaining=1) as (
        wrapper,
        client,
    ):
        c = MCPClient(_asgi_source(), call_timeout_seconds=0.5)
        await c.connect()
        try:
            with pytest.raises(MCPAuthRequired):
                await c.list_tools()  # records a 401 (last status of that operation)
            # Next operation: the server stops 401-ing but the tools/call POST never
            # answers, so the call times out with NO new MCP-POST response. The 401
            # recorded earlier sits at/before the baseline, so it must not misfire.
            await c.list_tools()  # a clean 200 list refreshes the tool cache
            wrapper.hang_methods = {"tools/call"}
            with pytest.raises(MCPConnectionError, match="exceeded"):
                await c.call_tool("echo", {"message": "hi"})
        finally:
            await c.disconnect()


async def test_stale_401_before_baseline_with_no_new_response_does_not_misfire(
    monkeypatch,
) -> None:
    """Sharper form: the 401 is the LAST recorded response, but it precedes the
    next operation's baseline, and the next operation produces no response."""
    async with _wrapped_asgi(monkeypatch, fail_methods={"tools/list"}, remaining=1) as (
        wrapper,
        _,
    ):
        c = MCPClient(_asgi_source(), timeout_seconds=0.5)
        await c.connect()
        try:
            with pytest.raises(MCPAuthRequired):
                await c.list_tools()
            record = sh.auth_record_for(c._session)
            assert record is not None and record.last_status == 401
            wrapper.hang_methods = {"tools/list"}
            with pytest.raises(MCPConnectionError, match="exceeded"):
                await c.list_tools()
        finally:
            await c.disconnect()


# ---------------------------------------------------------------------------
# AC7(c)/(d): provider attached
# ---------------------------------------------------------------------------


async def test_signin_that_succeeds_mid_operation_then_rpc_error_is_not_auth_required() -> None:
    """tools/list is 401 until the provider signs in; once signed in the server
    answers an ordinary JSON-RPC error. The last response is not a 401, so the
    failure stays an ordinary connection error."""
    with OAuthASStub(auth_required_methods={"tools/list"}, mcp_after_signin="rpc_error") as stub:
        provider, storage = build_provider(stub.base_url)
        c = MCPClient(http_source(stub.base_url), auth_provider=provider, timeout_seconds=10)
        await c.connect()  # initialize does not need a token on this server
        try:
            with pytest.raises(MCPConnectionError, match="stub ordinary rpc error"):
                await c.list_tools()
        finally:
            await c.disconnect()
        assert storage.tokens is not None  # the sign-in really happened mid-operation
        assert ("tools/list", False) in stub.mcp_requests
        assert ("tools/list", True) in stub.mcp_requests


@pytest.mark.parametrize(
    ("label", "stub_kwargs", "iss"),
    [
        ("mismatched RFC 9207 issuer", {"iss_param_supported": True}, "https://evil.example"),
        (
            "authorization-server metadata issuer mismatch",
            {"metadata_issuer": "http://evil.example"},
            "match",
        ),
        ("token endpoint answers 400", {"token_status": 400}, "match"),
    ],
)
async def test_failed_signin_flow_yields_auth_required_end_to_end(label, stub_kwargs, iss) -> None:
    """With a provider attached, a sign-in that fails after the 401 leaves the 401
    as the last MCP-POST status (a 2.3.0 auth-flow failure can surface as a bare
    CancelledError rather than an OAuthFlowError), so ``connect`` reads sign-in
    required - proven through the real client, not an injected exception."""
    with OAuthASStub(**stub_kwargs) as stub:
        provider, _ = build_provider(stub.base_url, iss=iss)
        c = MCPClient(http_source(stub.base_url), auth_provider=provider, timeout_seconds=10)
        with pytest.raises(MCPAuthRequired):
            await c.connect()
        assert c.is_alive is False, label


async def test_successful_signin_through_the_real_client_connects_and_lists_tools() -> None:
    with OAuthASStub() as stub:
        provider, storage = build_provider(stub.base_url)
        c = MCPClient(http_source(stub.base_url), auth_provider=provider, timeout_seconds=10)
        await c.connect()
        try:
            tools = await c.list_tools()
        finally:
            await c.disconnect()
        assert [t.name for t in tools] == ["echo"]
        assert storage.tokens is not None and storage.tokens.access_token == "stub-access-token"


# ---------------------------------------------------------------------------
# AC7(e): auth-flow requests and the GET stream are not recorded
# ---------------------------------------------------------------------------


async def _hook_client(url: str, handler):
    record = sh.AuthRecord()
    hook = sh._make_auth_hook(url, record)
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler), event_hooks={"response": [hook]}
    )
    return record, client


async def test_hook_records_mcp_post_401_with_resource_metadata() -> None:
    def handler(request):
        return httpx2.Response(
            401, headers={"www-authenticate": 'Bearer resource_metadata="https://rm.example/x"'}
        )

    record, client = await _hook_client("https://srv.example/mcp", handler)
    async with client:
        await client.post(
            "https://srv.example/mcp",
            headers={"accept": "application/json, text/event-stream"},
            json={},
        )
    assert (record.seq, record.last_status, record.last_resource_metadata) == (
        1,
        401,
        "https://rm.example/x",
    )


async def test_hook_does_not_record_token_dcr_or_get_stream_responses() -> None:
    def handler(request):
        return httpx2.Response(401, headers={"www-authenticate": "Bearer"})

    record, client = await _hook_client("https://srv.example/mcp", handler)
    async with client:
        # token / refresh POST: form-encoded, no event-stream accept.
        await client.post(
            "https://srv.example/token",
            data={"grant_type": "refresh_token", "refresh_token": "x"},
        )
        # DCR POST: JSON, no event-stream accept.
        await client.post("https://srv.example/register", json={"client_name": "the-one"})
        # Even on the MCP URL, an auth-flow POST without the MCP accept header is out.
        await client.post("https://srv.example/mcp", data={"grant_type": "refresh_token"})
        # The standalone GET stream.
        await client.get("https://srv.example/mcp", headers={"accept": "text/event-stream"})
        # Discovery GET.
        await client.get("https://srv.example/.well-known/oauth-protected-resource")
        # A different origin never counts.
        await client.post(
            "https://other.example/mcp",
            headers={"accept": "application/json, text/event-stream"},
            json={},
        )
    assert record.seq == 0 and record.last_status is None


async def test_hook_keeps_a_same_origin_redirected_post_in_scope() -> None:
    """DD12.1: the origin rule (not an exact-URL match) keeps a 401 behind a
    same-origin redirect (e.g. /mcp -> /mcp/) recorded."""
    record = sh.AuthRecord()
    hook = sh._make_auth_hook("https://srv.example/mcp", record)

    def handler(request):
        return httpx2.Response(401, headers={"www-authenticate": "Bearer"})

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler), event_hooks={"response": [hook]}
    ) as client:
        await client.post(
            "https://srv.example/mcp/",
            headers={"accept": "application/json, text/event-stream"},
            json={},
        )
    assert record.last_status == 401


# ---------------------------------------------------------------------------
# AC7(f): the hook is on every client branch of both entry points; the seam
# client's hook is removed on exit
# ---------------------------------------------------------------------------


def _hook_names(client) -> list[str]:
    return [h.__name__ for h in client.event_hooks["response"]]


def _spy_sdk(monkeypatch, captured: dict) -> None:
    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    @asynccontextmanager
    async def fake_streamable_http_client(url, *, http_client, **kwargs):
        captured["hooks"] = _hook_names(http_client)
        captured["client"] = http_client
        captured["kwargs"] = kwargs
        yield (object(), object())

    monkeypatch.setattr(sh, "streamable_http_client", fake_streamable_http_client)
    monkeypatch.setattr(sh, "ClientSession", lambda read, write: _FakeSession())


async def _open_via(entry: str, source, **kw):
    """Run one entry point to completion, returning nothing (the spy captures)."""
    if entry == "cm":
        async with sh.connect_streamable_http(source, **kw):
            pass
    else:
        _session, stack = await sh._open_streamable_http_transport_stack(source, **kw)
        await stack.aclose()


@pytest.mark.parametrize("entry", ["cm", "stack"])
@pytest.mark.parametrize("branch", ["production", "seam_client", "factory"])
async def test_hook_present_on_every_client_branch_and_seam_hook_removed(
    monkeypatch, entry, branch
) -> None:
    captured: dict = {}
    _spy_sdk(monkeypatch, captured)
    source = _asgi_source()
    seam = None
    if branch == "production":
        monkeypatch.setattr(sh, "_test_http_client_override", None)
    elif branch == "seam_client":
        seam = httpx2.AsyncClient()

        # a pre-existing hook on the shared seam client must survive the connection
        async def preexisting(response):  # pragma: no cover
            return None

        seam.event_hooks["response"].append(preexisting)
        monkeypatch.setattr(sh, "_test_http_client_override", seam)
    else:
        made: list = []

        def factory(headers):
            made.append(httpx2.AsyncClient())
            return made[0]

        monkeypatch.setattr(sh, "_test_http_client_override", factory)

    await _open_via(entry, source)

    assert "_hook" in captured["hooks"], f"{entry}/{branch}: DD1 hook missing"
    assert captured["kwargs"]["max_sse_event_size"] == sh.MAX_SSE_EVENT_BYTES
    if seam is not None:
        # exactly the hook this connection added is gone; the other stays
        assert _hook_names(seam) == ["preexisting"]
        await seam.aclose()
    for c in made if branch == "factory" else []:
        await c.aclose()


async def test_seam_client_shared_across_connections_gets_one_hook_each(monkeypatch) -> None:
    """Two connections over one shared seam client: each adds and removes its own
    hook, never clearing the list."""
    captured: dict = {}
    _spy_sdk(monkeypatch, captured)
    seam = httpx2.AsyncClient()
    monkeypatch.setattr(sh, "_test_http_client_override", seam)
    source = _asgi_source()
    async with sh.connect_streamable_http(source):
        assert _hook_names(seam) == ["_hook"]
        async with sh.connect_streamable_http(source):
            assert _hook_names(seam) == ["_hook", "_hook"]
        assert _hook_names(seam) == ["_hook"]
    assert _hook_names(seam) == []
    await seam.aclose()


async def test_session_is_hashable_and_weakly_referenceable_in_the_side_table() -> None:
    """DD1's side table relies on ``ClientSession`` being a valid WeakKeyDictionary
    key (the premise behind the [BLOCKED:dd1-side-table] stop)."""
    import weakref

    from mcp import ClientSession

    assert ClientSession.__eq__ is object.__eq__ or "__eq__" not in ClientSession.__dict__
    read = object()
    write = object()
    session = ClientSession(read, write)  # type: ignore[arg-type]
    ref = weakref.ref(session)
    assert ref() is session
    table: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
    table[session] = sh.AuthRecord()
    assert sh.auth_record_for(session) is None  # a session the transport did not open
    sh._AUTH_RECORDS[session] = sh.AuthRecord(seq=3)
    assert sh.auth_record_for(session).seq == 3
    del session
    import gc

    gc.collect()
    assert len(sh._AUTH_RECORDS) == 0 or all(
        isinstance(v, sh.AuthRecord) for v in sh._AUTH_RECORDS.values()
    )
    _ = asyncio  # keep the import used on all paths


# ---------------------------------------------------------------------------
# AC9 (DD2): the RFC 9207 issuer carried from the callback to the SDK
# ---------------------------------------------------------------------------


async def test_advertised_iss_matching_signs_in() -> None:
    with OAuthASStub(iss_param_supported=True) as stub:
        provider, storage = build_provider(stub.base_url, iss="match")
        c = MCPClient(http_source(stub.base_url), auth_provider=provider, timeout_seconds=10)
        await c.connect()
        try:
            assert [t.name for t in await c.list_tools()] == ["echo"]
        finally:
            await c.disconnect()
        assert storage.tokens is not None


async def test_advertised_iss_missing_fails_sign_in() -> None:
    with OAuthASStub(iss_param_supported=True) as stub:
        provider, storage = build_provider(stub.base_url, iss=None)
        c = MCPClient(http_source(stub.base_url), auth_provider=provider, timeout_seconds=10)
        with pytest.raises(MCPAuthRequired):
            await c.connect()
        assert storage.tokens is None


async def test_iss_mismatch_fails_sign_in() -> None:
    with OAuthASStub(iss_param_supported=True) as stub:
        provider, storage = build_provider(stub.base_url, iss="https://evil.example")
        c = MCPClient(http_source(stub.base_url), auth_provider=provider, timeout_seconds=10)
        with pytest.raises(MCPAuthRequired):
            await c.connect()
        assert storage.tokens is None


async def test_a_registration_stored_by_1x_without_an_issuer_still_loads() -> None:
    """DD2/DD12.2: client registrations persisted by mcp 1.x carry no ``issuer``;
    2.x treats them as unbound, so they must still validate and load."""
    from unittest.mock import AsyncMock, MagicMock

    from the_one.mcp.oauth.storage import MCPSourceTokenStorage

    one_x_payload = {
        "redirect_uris": ["http://127.0.0.1:8484/api/oauth/callback"],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "client_name": "the-one",
        "client_id": "stored-by-1x",
    }
    source = MCPSource(
        id="src-1x",
        name="x",
        type="streamable-http",
        config={"url": "https://x.example/mcp"},
        secrets={"dcr_credentials": one_x_payload},
    )
    repo = MagicMock()
    repo.get = AsyncMock(return_value=source)
    info = await MCPSourceTokenStorage(repo, "src-1x").get_client_info()
    assert info is not None
    assert info.client_id == "stored-by-1x"
    assert info.issuer is None
