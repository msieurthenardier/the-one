"""F2 integration tests — real SDK round-trips against the in-repo FastMCP fixture.

L3: 2 smoke tests verifying both transports work via the bare SDK (no MCPClient).
L4: adds MCPClient-flavored streamable-http tests.
L5: adds MCPClient-flavored stdio tests.
L6a/b: extends with list_tools/call_tool error-path tests.
"""

from __future__ import annotations

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from the_one.db.models import MCPSource
from the_one.mcp.client import MCPClient
from the_one.mcp.errors import MCPArgumentError, MCPConnectionError


class TestL3IntegrationSmoke:
    async def test_stdio_smoke_via_raw_sdk(self, mcp_fixture_stdio_params: dict) -> None:
        params = StdioServerParameters(**mcp_fixture_stdio_params)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init_result = await session.initialize()
                assert init_result.protocolVersion == "2025-11-25"
                assert init_result.capabilities.tools is not None

                tools_result = await session.list_tools()
                assert len(tools_result.tools) == 2
                assert {t.name for t in tools_result.tools} == {"echo", "add"}

                echo_result = await session.call_tool("echo", {"message": "hi"})
                assert echo_result.isError is False
                # SDK returns content blocks; first block should be text "hi"
                assert echo_result.content[0].text == "hi"

    async def test_streamable_http_smoke_via_raw_sdk(self, mcp_fixture_http_client) -> None:
        client, url = mcp_fixture_http_client
        async with streamable_http_client(url, http_client=client) as (
            read,
            write,
            _get_session_id,
        ):
            async with ClientSession(read, write) as session:
                init_result = await session.initialize()
                assert init_result.protocolVersion == "2025-11-25"
                assert init_result.capabilities.tools is not None

                tools_result = await session.list_tools()
                assert len(tools_result.tools) == 2
                assert {t.name for t in tools_result.tools} == {"echo", "add"}

                echo_result = await session.call_tool("echo", {"message": "hi"})
                assert echo_result.isError is False
                assert echo_result.content[0].text == "hi"


class TestL4StreamableHttp:
    async def test_connect_via_mcpclient_against_asgi_fixture(
        self, mcp_fixture_http_client, monkeypatch
    ) -> None:
        client_httpx, url = mcp_fixture_http_client
        monkeypatch.setattr(
            "the_one.mcp.transports.streamable_http._test_http_client_override",
            client_httpx,
        )
        source = MCPSource(
            id="src-1",
            name="hello",
            type="streamable-http",
            config={"url": url, "headers": {}},
            secrets={},
        )
        client = MCPClient(source)
        await client.connect()
        try:
            assert client.is_alive
            assert client.negotiated_protocol_version == "2025-11-25"
            caps = client.server_capabilities
            assert isinstance(caps["tools"], dict)
            assert "listChanged" in caps["tools"]
        finally:
            await client.disconnect()
        assert not client.is_alive

    async def test_connect_with_secrets_does_not_break_connection(
        self, mcp_fixture_http_client, monkeypatch
    ) -> None:
        # NOTE: this test does NOT verify the bearer header reaches the wire
        # — that gap is closed by test_production_path_constructs_client_with_assembled_headers
        # in TestConnectStreamableHttpProduction (Option C unit test). This integration test
        # only proves end-to-end positive completion with secrets present
        # (i.e., the test branch's effective_client.headers.update(headers)
        # mutation doesn't break the in-process ASGI transport).
        client_httpx, url = mcp_fixture_http_client
        monkeypatch.setattr(
            "the_one.mcp.transports.streamable_http._test_http_client_override",
            client_httpx,
        )
        source = MCPSource(
            id="src-2",
            name="hello-with-auth",
            type="streamable-http",
            config={"url": url, "headers": {}},
            secrets={"Authorization": "Bearer test-token"},
        )
        client = MCPClient(source)
        await client.connect()
        try:
            assert client.is_alive
        finally:
            await client.disconnect()

    async def test_connect_already_connected_via_real_transport(
        self, mcp_fixture_http_client, monkeypatch
    ) -> None:
        client_httpx, url = mcp_fixture_http_client
        monkeypatch.setattr(
            "the_one.mcp.transports.streamable_http._test_http_client_override",
            client_httpx,
        )
        source = MCPSource(
            id="src-3",
            name="hello-double-connect",
            type="streamable-http",
            config={"url": url, "headers": {}},
            secrets={},
        )
        client = MCPClient(source)
        await client.connect()
        try:
            with pytest.raises(MCPConnectionError, match="already connected"):
                await client.connect()
        finally:
            await client.disconnect()


class TestL5Stdio:
    """MCPClient end-to-end tests over the real stdio transport.

    Each test wrapped in `@pytest.mark.timeout(15)` so a hung subprocess
    (broken pipe, missing PYTHONPATH typo, FastMCP deadlock) fails fast at
    15s instead of stalling the suite. Real cold-start is ~0.5-0.8s per L3
    measurements; 15s is well above the steady-state but tight enough to
    surface a wedge.
    """

    @pytest.mark.timeout(15)
    async def test_connect_via_mcpclient_against_stdio_fixture(
        self, mcp_fixture_stdio_params
    ) -> None:
        params_dict = mcp_fixture_stdio_params
        source = MCPSource(
            id="src-stdio-1",
            name="hello-stdio",
            type="stdio",
            config={
                "command": params_dict["command"],
                "args": params_dict["args"],
                "env": params_dict["env"],
                "cwd": params_dict["cwd"],
            },
            secrets={},
        )
        client = MCPClient(source)
        await client.connect()
        try:
            assert client.is_alive
            assert client.negotiated_protocol_version == "2025-11-25"
            caps = client.server_capabilities
            assert isinstance(caps["tools"], dict)
            assert "listChanged" in caps["tools"]
        finally:
            await client.disconnect()
        assert not client.is_alive

    @pytest.mark.timeout(15)
    async def test_connect_with_extra_env_passes_through(self, mcp_fixture_stdio_params) -> None:
        # Extend the fixture's env with an extra plaintext key AND add a
        # secret. FastMCP's hello fixture doesn't read these vars, but the
        # round-trip proves the env is materialized without breaking spawn.
        params_dict = mcp_fixture_stdio_params
        extended_env = {**params_dict["env"], "MY_PLAIN": "hello"}
        source = MCPSource(
            id="src-stdio-2",
            name="hello-stdio-with-env",
            type="stdio",
            config={
                "command": params_dict["command"],
                "args": params_dict["args"],
                "env": extended_env,
                "cwd": params_dict["cwd"],
            },
            secrets={"MY_SECRET": "shh"},
        )
        client = MCPClient(source)
        await client.connect()
        try:
            assert client.is_alive
        finally:
            await client.disconnect()

    @pytest.mark.timeout(15)
    async def test_connect_already_connected_via_stdio_transport(
        self, mcp_fixture_stdio_params
    ) -> None:
        params_dict = mcp_fixture_stdio_params
        source = MCPSource(
            id="src-stdio-3",
            name="hello-stdio-double",
            type="stdio",
            config={
                "command": params_dict["command"],
                "args": params_dict["args"],
                "env": params_dict["env"],
                "cwd": params_dict["cwd"],
            },
            secrets={},
        )
        client = MCPClient(source)
        await client.connect()
        try:
            with pytest.raises(MCPConnectionError, match="already connected"):
                await client.connect()
        finally:
            await client.disconnect()


class TestL6aHappyPath:
    """MCPClient.list_tools() + call_tool() end-to-end against the FastMCP fixture.

    Mirrors L4/L5 transport tests but extends past `connect()` into the real
    tool-list and tool-call round-trips. Verifies the L6a projection:
    `MCPTool` from the SDK's `Tool` shape and `MCPToolResult` from the SDK's
    `CallToolResult` (text-block flattening + structuredContent passthrough).

    Stdio tests are wrapped in `@pytest.mark.timeout(15)` per the L5 pattern
    so a hung subprocess fails fast.
    """

    async def test_list_tools_streamable_http(self, mcp_fixture_http_client, monkeypatch) -> None:
        client_httpx, url = mcp_fixture_http_client
        monkeypatch.setattr(
            "the_one.mcp.transports.streamable_http._test_http_client_override",
            client_httpx,
        )
        source = MCPSource(
            id="src-4",
            name="hello-list-tools",
            type="streamable-http",
            config={"url": url, "headers": {}},
            secrets={},
        )
        client = MCPClient(source)
        await client.connect()
        try:
            tools = await client.list_tools()
            assert len(tools) == 2
            by_name = {t.name: t for t in tools}
            assert set(by_name) == {"echo", "add"}
            for tool in tools:
                # MCPTool dataclass shape (frozen); input_schema is non-empty
                # (echo's required `message` and add's `a`/`b` per fixture).
                assert isinstance(tool.input_schema, dict)
                assert tool.input_schema  # non-empty dict
        finally:
            await client.disconnect()

    async def test_call_tool_echo_streamable_http(
        self, mcp_fixture_http_client, monkeypatch
    ) -> None:
        client_httpx, url = mcp_fixture_http_client
        monkeypatch.setattr(
            "the_one.mcp.transports.streamable_http._test_http_client_override",
            client_httpx,
        )
        source = MCPSource(
            id="src-4",
            name="hello-call-echo",
            type="streamable-http",
            config={"url": url, "headers": {}},
            secrets={},
        )
        client = MCPClient(source)
        await client.connect()
        try:
            result = await client.call_tool("echo", {"message": "hello"})
            assert result.is_error is False
            assert result.text == "hello"
            # raw is the SDK's content-block dump list (one text block here).
            assert isinstance(result.raw, list)
            assert len(result.raw) == 1
        finally:
            await client.disconnect()

    @pytest.mark.timeout(15)
    async def test_list_tools_stdio(self, mcp_fixture_stdio_params) -> None:
        params_dict = mcp_fixture_stdio_params
        source = MCPSource(
            id="src-stdio-4",
            name="hello-stdio-list-tools",
            type="stdio",
            config={
                "command": params_dict["command"],
                "args": params_dict["args"],
                "env": params_dict["env"],
                "cwd": params_dict["cwd"],
            },
            secrets={},
        )
        client = MCPClient(source)
        await client.connect()
        try:
            tools = await client.list_tools()
            assert len(tools) == 2
            by_name = {t.name: t for t in tools}
            assert set(by_name) == {"echo", "add"}
            for tool in tools:
                assert isinstance(tool.input_schema, dict)
                assert tool.input_schema  # non-empty dict
        finally:
            await client.disconnect()

    @pytest.mark.timeout(15)
    async def test_call_tool_add_stdio(self, mcp_fixture_stdio_params) -> None:
        params_dict = mcp_fixture_stdio_params
        source = MCPSource(
            id="src-stdio-5",
            name="hello-stdio-call-add",
            type="stdio",
            config={
                "command": params_dict["command"],
                "args": params_dict["args"],
                "env": params_dict["env"],
                "cwd": params_dict["cwd"],
            },
            secrets={},
        )
        client = MCPClient(source)
        await client.connect()
        try:
            result = await client.call_tool("add", {"a": 2, "b": 3})
            assert result.is_error is False
            # FastMCP's @mcp.tool returns int 5; SDK projects structuredContent
            # as {"result": 5} and coerces the text content block to "5"
            # (no trailing newline) — confirmed by in-container probe at L6a
            # implementation time.
            assert result.structured == {"result": 5}
            assert result.text == "5"
        finally:
            await client.disconnect()


class TestL6bInputValidationIntegration:
    """L6b end-to-end input-validation tests against the FastMCP fixture.

    Exercises jsonschema validation against the real `echo` tool's
    inputSchema (required `message` field). MCPArgumentError raised BEFORE
    wire call — closes the integration loop opened by the unit-mocked
    `TestCallToolInputValidation` class.
    """

    async def test_call_tool_invalid_args_via_streamable_http(
        self, mcp_fixture_http_client, monkeypatch
    ) -> None:
        client_httpx, url = mcp_fixture_http_client
        monkeypatch.setattr(
            "the_one.mcp.transports.streamable_http._test_http_client_override",
            client_httpx,
        )
        source = MCPSource(
            id="src-6",
            name="hello-invalid-args-http",
            type="streamable-http",
            config={"url": url, "headers": {}},
            secrets={},
        )
        client = MCPClient(source)
        await client.connect()
        try:
            # echo's inputSchema requires `message`; missing -> MCPArgumentError
            with pytest.raises(MCPArgumentError):
                await client.call_tool("echo", {})
        finally:
            await client.disconnect()

    @pytest.mark.timeout(15)
    async def test_call_tool_invalid_args_via_stdio(self, mcp_fixture_stdio_params) -> None:
        params_dict = mcp_fixture_stdio_params
        source = MCPSource(
            id="src-stdio-6",
            name="hello-invalid-args-stdio",
            type="stdio",
            config={
                "command": params_dict["command"],
                "args": params_dict["args"],
                "env": params_dict["env"],
                "cwd": params_dict["cwd"],
            },
            secrets={},
        )
        client = MCPClient(source)
        await client.connect()
        try:
            with pytest.raises(MCPArgumentError):
                await client.call_tool("echo", {})
        finally:
            await client.disconnect()
