"""Wire shapes under mcp 2.x (Mission 29): DD5 aliases, DD6 versions, DD8 SSE cap,
DD12 redirects - all against REAL servers (the hello_server fixture over stdio and
the in-process ASGI transport), never mock results."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx2
import pytest
from asgi_lifespan import LifespanManager
from mcp import types as mcp_types
from mcp.shared.exceptions import MCPError

from tests.fixtures.mcp.hello_server import make_http_app, make_mcp_app
from the_one.db.models import MCPSource
from the_one.mcp import _era
from the_one.mcp import client as client_mod
from the_one.mcp.client import MCPClient, _is_sse_cap_error
from the_one.mcp.errors import MCPCallError, MCPConnectionError
from the_one.mcp.transports import streamable_http as sh

ASGI_URL = "http://localhost/mcp"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _http_source() -> MCPSource:
    return MCPSource(
        id="src-wire",
        name="wire",
        type="streamable-http",
        config={"url": ASGI_URL, "headers": {}},
        secrets={},
    )


def _stdio_source() -> MCPSource:
    return MCPSource(
        id="src-stdio",
        name="stdio",
        type="stdio",
        config={
            "command": sys.executable,
            "args": ["-m", "tests.fixtures.mcp.hello_server", "--stdio"],
            "env": {"PYTHONPATH": str(_PROJECT_ROOT)},
        },
        secrets={},
    )


@asynccontextmanager
async def _asgi(monkeypatch, **app_kwargs):
    app = make_http_app(**app_kwargs)
    async with LifespanManager(app):
        client = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://localhost"
        )
        monkeypatch.setattr(sh, "_test_http_client_override", client)
        try:
            yield client
        finally:
            await client.aclose()


# ---------------------------------------------------------------------------
# AC6 (DD6, DD7): the negotiated revision and server metadata from the session
# ---------------------------------------------------------------------------


async def test_asgi_connection_reports_the_modern_era_version(monkeypatch) -> None:
    """The 2.x server serves both eras; the negotiating client lands on the
    modern era (Mission 29 Flight 2)."""
    async with _asgi(monkeypatch, website_url="https://hello.example"):
        c = MCPClient(_http_source())
        await c.connect()
        try:
            assert c.negotiated_protocol_version == "2026-07-28"
            assert c.server_info is not None and c.server_info["name"] == "hello"
        finally:
            await c.disconnect()


async def test_stdio_connection_reports_the_modern_era_version() -> None:
    c = MCPClient(_stdio_source(), timeout_seconds=30)
    await c.connect()
    try:
        assert c.negotiated_protocol_version == "2026-07-28"
        assert c.server_capabilities["tools"] is not None
        assert {t.name for t in await c.list_tools()} == {"echo", "add"}
        result = await c.call_tool("echo", {"message": "hi"})
        assert result.text == "hi"
    finally:
        await c.disconnect()


def test_version_gate_uses_the_handshake_registry() -> None:
    from mcp.types.version import (
        HANDSHAKE_PROTOCOL_VERSIONS,
        LATEST_HANDSHAKE_VERSION,
        LATEST_MODERN_VERSION,
    )

    from the_one import mcp as the_one_mcp

    assert the_one_mcp._HANDSHAKE_OFFER_VERSION == "2025-11-25"
    assert the_one_mcp._HANDSHAKE_OFFER_VERSION == LATEST_HANDSHAKE_VERSION
    assert "2025-11-25" in HANDSHAKE_PROTOCOL_VERSIONS
    assert LATEST_MODERN_VERSION == "2026-07-28"


# ---------------------------------------------------------------------------
# AC5 (DD5): camelCase keys survive at every boundary
# ---------------------------------------------------------------------------


async def test_cached_server_info_and_capabilities_keep_camelcase_keys(monkeypatch) -> None:
    async with _asgi(monkeypatch, website_url="https://hello.example"):
        c = MCPClient(_http_source())
        await c.connect()
        try:
            info = c.server_info
            caps = c.server_capabilities
        finally:
            await c.disconnect()
    # The agent editor reads info.websiteUrl; 2.x models dump snake_case by default.
    assert info is not None
    assert info["websiteUrl"] == "https://hello.example"
    assert "website_url" not in info
    # Capabilities dump by alias too (listChanged, not list_changed).
    assert "listChanged" in caps["tools"]
    assert "list_changed" not in caps["tools"]
    assert all("_" not in k or k == "_meta" for k in caps)


def _fake_session(*, tools, call_tool=None):
    """A handshaken fake ``ClientSession`` carrying REAL ``mcp.types`` models."""
    from unittest.mock import AsyncMock, MagicMock

    session = MagicMock()
    caps = mcp_types.ServerCapabilities(tools=mcp_types.ToolsCapability())
    session.initialize = AsyncMock(
        return_value=mcp_types.InitializeResult(
            protocol_version="2025-11-25",
            capabilities=caps,
            server_info=mcp_types.Implementation(name="fake", version="1"),
        )
    )
    session.send_discover = AsyncMock(
        side_effect=MCPError(mcp_types.METHOD_NOT_FOUND, "Method not found")
    )
    session.adopt = MagicMock()
    session.initialize_result = session.initialize.return_value
    session.discover_result = None
    session.protocol_version = "2025-11-25"
    session.server_capabilities = caps
    session.server_info = None
    session.instructions = None
    session.list_tools = AsyncMock(return_value=mcp_types.ListToolsResult(tools=tools))
    if call_tool is not None:
        session.call_tool = call_tool
    return session


@asynccontextmanager
async def _client_over(session):
    @asynccontextmanager
    async def transport(source):
        yield session

    orig = client_mod._transport_connect
    client_mod._transport_connect = lambda source: transport(source)
    c = MCPClient(MCPSource(id="s", name="n", type="stdio", config={"command": "x"}, secrets={}))
    try:
        await c.connect()
        try:
            yield c
        finally:
            await c.disconnect()
    finally:
        client_mod._transport_connect = orig


async def test_tool_result_blocks_keep_camelcase_keys() -> None:
    """The content blocks an agent receives dump by alias: ``mimeType``, not
    ``mime_type`` (and ``_meta`` where 1.x dumped ``meta`` - accepted)."""
    from unittest.mock import AsyncMock

    session = _fake_session(
        tools=[mcp_types.Tool(name="img", input_schema={"type": "object"})],
        call_tool=AsyncMock(
            return_value=mcp_types.CallToolResult(
                content=[mcp_types.ImageContent(type="image", data="abc", mime_type="image/png")],
                structured_content={"k": 1},
                is_error=False,
            )
        ),
    )
    async with _client_over(session) as c:
        result = await c.call_tool("img", {})
    assert result.raw[0]["mimeType"] == "image/png"
    assert "mime_type" not in result.raw[0]
    assert result.structured == {"k": 1}
    assert result.text == "[image: 3 bytes, mime=image/png]"


async def test_tool_annotations_dump_by_alias() -> None:
    session = _fake_session(
        tools=[
            mcp_types.Tool(
                name="t",
                input_schema={"type": "object"},
                annotations=mcp_types.ToolAnnotations(read_only_hint=True),
            )
        ]
    )
    async with _client_over(session) as c:
        tools = await c.list_tools()
    assert tools[0].annotations["readOnlyHint"] is True
    assert "read_only_hint" not in tools[0].annotations


# ---------------------------------------------------------------------------
# AC10 (DD8): the 1 MiB SSE event cap
# ---------------------------------------------------------------------------


async def test_oversized_tool_result_event_is_a_plain_call_error_and_keeps_the_client(
    monkeypatch,
) -> None:
    """Handshake-era pin: a modern-era server answers a single response as plain
    JSON (no SSE), so the event cap cannot fire there. Seed the era memory so
    ``connect`` takes the handshake shortcut and the server streams SSE."""
    _era.remember_era(_http_source().id, "2025-11-25")
    async with _asgi(monkeypatch):
        c = MCPClient(_http_source(), call_timeout_seconds=30)
        await c.connect()
        try:
            big = "x" * (1024 * 1024 + 1024)
            with pytest.raises(MCPCallError) as exc_info:
                await c.call_tool("echo", {"message": big})
            msg = str(exc_info.value)
            assert "1048576-byte" in msg and "limit" in msg
            assert "\n" not in msg
            # one bad response, not a dead connection
            assert c.is_alive is True
            result = await c.call_tool("echo", {"message": "still fine"})
            assert result.text == "still fine"
        finally:
            await c.disconnect()


async def test_oversized_tools_list_event_is_a_plain_connection_error(monkeypatch) -> None:
    """Handshake-era pin (see the call_tool twin above): the modern era answers
    plain JSON, so the SSE cap is exercised on the handshake shortcut."""
    _era.remember_era(_http_source().id, "2025-11-25")
    async with _asgi(monkeypatch, oversized_description=True):
        c = MCPClient(_http_source(), timeout_seconds=30)
        await c.connect()
        try:
            with pytest.raises(MCPConnectionError) as exc_info:
                await c.list_tools()
            msg = str(exc_info.value)
            assert "1048576-byte" in msg and "limit" in msg
            assert c.is_alive is True
        finally:
            await c.disconnect()


def test_sse_cap_match_requires_code_prefix_and_marker() -> None:
    cap = MCPError(-32000, "SSE stream failed: Server-sent event exceeded the 1048576 byte limit.")
    assert _is_sse_cap_error(cap) is True
    # A different -32000 error is not matched ...
    assert _is_sse_cap_error(MCPError(-32000, "SSE stream ended without a response")) is False
    assert _is_sse_cap_error(MCPError(-32000, "SSE stream failed: connection reset")) is False
    # ... nor the same text under another code, nor a non-MCPError.
    assert _is_sse_cap_error(MCPError(-32603, cap.message)) is False
    assert _is_sse_cap_error(RuntimeError(cap.message)) is False


async def test_a_different_minus_32000_error_is_an_ordinary_call_error() -> None:
    from unittest.mock import AsyncMock

    session = _fake_session(
        tools=[mcp_types.Tool(name="t", input_schema={"type": "object"})],
        call_tool=AsyncMock(side_effect=MCPError(-32000, "SSE stream ended without a response")),
    )
    async with _client_over(session) as c:
        with pytest.raises(MCPCallError) as exc_info:
            await c.call_tool("t", {})
    assert "SSE stream ended without a response" in str(exc_info.value)
    assert "byte" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# AC11 (DD12.1): a cross-origin redirect on the MCP path fails plainly
# ---------------------------------------------------------------------------


async def test_cross_origin_redirect_fails_with_a_plain_connection_error(monkeypatch) -> None:
    async def redirecting_app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        body = b""
        more = True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)
        await send(
            {
                "type": "http.response.start",
                "status": 307,
                "headers": [
                    (b"location", b"http://evil.example/mcp"),
                    (b"content-length", b"0"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    client = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=redirecting_app), base_url="http://localhost"
    )
    monkeypatch.setattr(sh, "_test_http_client_override", client)
    try:
        c = MCPClient(_http_source(), timeout_seconds=10)
        with pytest.raises(MCPConnectionError) as exc_info:
            await c.connect()
    finally:
        await client.aclose()
    assert "not followed" in str(exc_info.value)
    assert c.is_alive is False


def test_hello_server_factory_still_registers_only_the_hello_tools() -> None:
    import asyncio

    tools = asyncio.run(make_mcp_app().list_tools())
    assert {t.name for t in tools} == {"echo", "add"}


# ---------------------------------------------------------------------------
# AC12 (DD9): httpx2 verifies against the OS trust store unless SSL_CERT_* is set
# ---------------------------------------------------------------------------


def test_httpx2_uses_the_os_trust_store_unless_overridden(monkeypatch, tmp_path) -> None:
    """Documents the split SECURITY-MODEL.md records: ``httpx2`` (the MCP path) uses
    ``truststore`` (the OS store) by default and honours ``SSL_CERT_FILE`` /
    ``SSL_CERT_DIR``; the rest of the app (``httpx``) uses certifi. Clears both
    variables explicitly, since the choice depends on them."""
    import platform
    import ssl

    import truststore

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    default_ctx = httpx2.create_ssl_context()
    if platform.system() in ("Windows", "Darwin"):
        assert isinstance(default_ctx, truststore.SSLContext)
    else:
        # httpx2 >= 2.14 (httpcore2.default_ssl_context) uses truststore only
        # on Windows and macOS; elsewhere it loads the OS's own CA paths into a
        # plain ssl context. Older releases used truststore everywhere.
        if not isinstance(default_ctx, truststore.SSLContext):
            assert isinstance(default_ctx, ssl.SSLContext)
            assert default_ctx.cert_store_stats()["x509"] > 0

    import certifi

    monkeypatch.setenv("SSL_CERT_FILE", certifi.where())
    overridden = httpx2.create_ssl_context()
    assert not isinstance(overridden, truststore.SSLContext)
    assert isinstance(overridden, ssl.SSLContext)
    monkeypatch.delenv("SSL_CERT_FILE")
