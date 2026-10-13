"""Real-server proofs of automatic negotiation (Mission 29 Flight 2, DD8/DD13).

Everything here talks to a REAL server: the ``hello_server`` fixture as a stdio
subprocess (dual-era by default, handshake-only with ``--legacy-only[=rev]``) or the
in-process ASGI app. HTTP caveat: the wrapper in ``asgi_legacy`` intercepts only
``server/discover`` and passes ``initialize`` to the dual-era app, so HTTP proves
the 2025-11-25 handshake after a failed discover, not a handshake-only HTTP server.

Latency is proven structurally: a spy on ``ClientSession.send_discover`` (the client
is in-process even when the server is a subprocess) must see ZERO calls on the
second connect of a source whose era was remembered.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession

from tests._mcp_signin_helpers import serve_asgi
from tests.fixtures.mcp.asgi_legacy import LegacyDiscoverWrapper
from tests.fixtures.mcp.hello_server import make_http_app
from the_one.db.models import MCPSource
from the_one.mcp import _era
from the_one.mcp import client as client_mod
from the_one.mcp.client import MCPClient
from the_one.mcp.errors import MCPCallError, MCPConnectionError

_ROOT = Path(__file__).resolve().parent.parent
ASGI_URL = "http://localhost/mcp"


def _stdio(*flags: str, source_id: str = "src-neg") -> MCPSource:
    return MCPSource(
        id=source_id,
        name="neg",
        type="stdio",
        config={
            "command": sys.executable,
            "args": ["-m", "tests.fixtures.mcp.hello_server", "--stdio", *flags],
            "env": {"PYTHONPATH": str(_ROOT)},
        },
        secrets={},
    )


def _http(source_id: str = "src-neg-http") -> MCPSource:
    return MCPSource(
        id=source_id,
        name="neg-http",
        type="streamable-http",
        config={"url": ASGI_URL, "headers": {}},
        secrets={},
    )


@pytest.fixture
def discover_spy(monkeypatch):
    """Count ``ClientSession.send_discover`` calls made in this process."""
    calls: list[str] = []
    original = ClientSession.send_discover

    async def spy(self, *args, **kwargs):
        calls.append("discover")
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(ClientSession, "send_discover", spy)
    return calls


async def _connect_list_echo(source: MCPSource) -> str:
    c = MCPClient(source, timeout_seconds=30)
    await c.connect()
    try:
        assert c.is_alive is True
        tools = {t.name for t in await c.list_tools()}
        assert {"echo", "add"} <= tools
        result = await c.call_tool("echo", {"message": "hi"})
        assert result.text == "hi"
        return c.negotiated_protocol_version
    finally:
        await c.disconnect()


# ---------------------------------------------------------------------------
# AC7: input-required over a real modern-era connection
# ---------------------------------------------------------------------------


async def test_input_required_tool_over_stdio_modern_era() -> None:
    c = MCPClient(_stdio("--with-input-required", source_id="src-ir"))
    await c.connect()
    try:
        assert c.negotiated_protocol_version == "2026-07-28"
        with pytest.raises(MCPCallError) as exc_info:
            await c.call_tool("needs_input", {})
        assert exc_info.value.tool_name == "needs_input"
        assert exc_info.value.server_message == client_mod._INPUT_REQUIRED_MESSAGE
        assert str(exc_info.value) == (
            "MCP tool 'needs_input' returned an error: "
            "the server asked for extra input, which the-one can't provide yet"
        )
    finally:
        await c.disconnect()


async def test_input_required_tool_over_http_modern_era(monkeypatch) -> None:
    async with serve_asgi(monkeypatch, make_http_app(input_required=True)):
        c = MCPClient(_http("src-ir-http"))
        await c.connect()
        try:
            assert c.negotiated_protocol_version == "2026-07-28"
            with pytest.raises(MCPCallError) as exc_info:
                await c.call_tool("needs_input", {})
            assert exc_info.value.server_message == client_mod._INPUT_REQUIRED_MESSAGE
        finally:
            await c.disconnect()


# ---------------------------------------------------------------------------
# AC8: every older revision on a real handshake-only server
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("revision", ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"])
async def test_legacy_only_server_negotiates_its_own_revision_over_stdio(revision) -> None:
    version = await _connect_list_echo(
        _stdio(f"--legacy-only={revision}", source_id=f"s-{revision}")
    )
    assert version == revision
    assert _era.era_for(f"s-{revision}") == revision


async def test_legacy_only_default_revision_is_2025_11_25() -> None:
    assert await _connect_list_echo(_stdio("--legacy-only", source_id="s-default")) == "2025-11-25"


async def test_dual_era_server_negotiates_modern_over_stdio() -> None:
    assert await _connect_list_echo(_stdio(source_id="s-dual")) == "2026-07-28"
    assert _era.era_for("s-dual") == "2026-07-28"


@pytest.mark.parametrize("mode", ["fast400", "bare404", "drop"])
async def test_2025_11_25_over_http_after_failed_discover(monkeypatch, mode) -> None:
    """HTTP legacy proof (see module docstring: the wrapper fails ONLY discover)."""
    monkeypatch.setattr("mcp.client.session.DISCOVER_TIMEOUT_SECONDS", 0.5)
    wrapper = LegacyDiscoverWrapper(make_http_app(), mode=mode)
    async with serve_asgi(monkeypatch, wrapper):
        async with asyncio.timeout(60):
            version = await _connect_list_echo(_http(f"h-{mode}"))
    assert version == "2025-11-25"
    assert wrapper.discover_calls == 1
    assert wrapper.initialize_calls == 1
    assert _era.era_for(f"h-{mode}") == "2025-11-25"


# ---------------------------------------------------------------------------
# AC9 + AC10: fallback modes, then a second connect that never sends discover
# ---------------------------------------------------------------------------


async def _second_connect_sends_no_discover(source: MCPSource, spy: list[str]) -> None:
    spy.clear()
    c = MCPClient(source, timeout_seconds=30)
    await c.connect()
    try:
        assert c.negotiated_protocol_version == _era.era_for(source.id)
        assert (await c.call_tool("echo", {"message": "again"})).text == "again"
    finally:
        await c.disconnect()
    assert spy == [], "the second connect must go straight to initialize"


async def test_stdio_fast_error_falls_back_and_second_connect_skips_discover(discover_spy) -> None:
    source = _stdio("--legacy-only", source_id="fb-fast")
    assert await _connect_list_echo(source) == "2025-11-25"
    assert discover_spy == ["discover"]
    await _second_connect_sends_no_discover(source, discover_spy)


async def test_stdio_silent_drop_falls_back_and_second_connect_skips_discover(
    monkeypatch, discover_spy
) -> None:
    monkeypatch.setattr("mcp.client.session.DISCOVER_TIMEOUT_SECONDS", 0.5)
    source = _stdio("--legacy-only", "--drop-discover", source_id="fb-drop")
    async with asyncio.timeout(60):
        assert await _connect_list_echo(source) == "2025-11-25"
    assert discover_spy == ["discover"]
    await _second_connect_sends_no_discover(source, discover_spy)


async def test_stdio_pipe_close_fails_plainly_as_connection_error(discover_spy) -> None:
    """ACCEPTED limitation: a server that exits on ``server/discover`` is
    indistinguishable from a crashed server, so connect fails (no fallback)."""
    c = MCPClient(_stdio("--close-on-discover", source_id="fb-close"))
    with pytest.raises(MCPConnectionError):
        await c.connect()
    assert c.is_alive is False
    assert _era.era_for("fb-close") is None
    assert discover_spy == ["discover"]


@pytest.mark.parametrize("mode", ["fast400", "bare404", "drop"])
async def test_http_fallback_modes_second_connect_skips_discover(
    monkeypatch, discover_spy, mode
) -> None:
    monkeypatch.setattr("mcp.client.session.DISCOVER_TIMEOUT_SECONDS", 0.5)
    wrapper = LegacyDiscoverWrapper(make_http_app(), mode=mode)
    async with serve_asgi(monkeypatch, wrapper):
        async with asyncio.timeout(60):
            source = _http(f"hf-{mode}")
            assert await _connect_list_echo(source) == "2025-11-25"
            assert discover_spy == ["discover"]
            await _second_connect_sends_no_discover(source, discover_spy)
    assert wrapper.discover_calls == 1  # the second connect never reached the wrapper


# ---------------------------------------------------------------------------
# AC11: dual-era real servers
# ---------------------------------------------------------------------------


async def test_hello_server_http_negotiates_modern(monkeypatch) -> None:
    async with serve_asgi(monkeypatch, make_http_app()):
        assert await _connect_list_echo(_http("dual-http")) == "2026-07-28"


async def test_fresh_negotiation_ignores_a_remembered_handshake_era(
    monkeypatch, discover_spy
) -> None:
    """A remembered handshake revision would shortcut; a Test connection must not."""
    _era.remember_era("dual-fresh", "2025-11-25")
    async with serve_asgi(monkeypatch, make_http_app()):
        c = MCPClient(_http("dual-fresh"), fresh_negotiation=True)
        await c.connect()
        try:
            assert c.negotiated_protocol_version == "2026-07-28"
        finally:
            await c.disconnect()
    assert discover_spy == ["discover"]
