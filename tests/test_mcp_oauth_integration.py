"""F5 L4 streamable-http OAuth integration tests.

Covers acceptance criteria A2-A9 from
``missions/07-mcp-integration/flights/05-oauth-pkce-remote-mcp/legs/04-streamable-http-oauth-integration.md``.

Tests target three surfaces:
  - ``_build_production_httpx_kwargs`` helper (A2/A3/A4)
  - ``_test_http_client_override`` factory-callable seam (A6/A7)
  - ``MCPClient.call_tool`` SDK auth-exception translation (A8a/A8b)
  - the no-provider 401 translation (A9 — now DD1's response-hook record,
    proven against a real 401 in tests/test_mcp_signin_detection.py)

Per Implementation Guidance §4 the stake-test probe surfaced
``ExceptionGroup wrapping httpx2.HTTPStatusError`` on the no-provider 401 path,
so A9 ships as a working test using ``except*`` semantics.
"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import AsyncMock

import httpx2
import pytest
from mcp.client.auth.exceptions import OAuthFlowError, OAuthTokenError

from the_one.db.models import MCPSource
from the_one.mcp.client import MCPClient
from the_one.mcp.oauth.errors import MCPAuthRequired
from the_one.mcp.transports import streamable_http as sh
from the_one.mcp.types import MCPTool


def _http_source(source_id: str = "src-1") -> MCPSource:
    return MCPSource(
        id=source_id,
        name="x",
        type="streamable-http",
        config={"url": "https://example.com/mcp", "headers": {}},
        secrets={},
    )


# ---------------------------------------------------------------------------
# A2/A3 — _build_production_httpx_kwargs unit tests
# ---------------------------------------------------------------------------


class TestBuildProductionHttpxKwargs:
    def test_no_auth_provider_returns_auth_none(self) -> None:
        """A2: auth_provider=None → kwargs['auth'] is None.

        Headers and timeout are preserved verbatim.
        """
        kwargs = sh._build_production_httpx_kwargs(headers={"X-Foo": "bar"}, auth_provider=None)
        assert kwargs["auth"] is None
        assert kwargs["headers"] == {"X-Foo": "bar"}
        assert "follow_redirects" not in kwargs  # DD12.1: inert under mcp 2.x
        assert kwargs["timeout"] == httpx2.Timeout(30.0, read=300.0)

    def test_with_auth_provider_returns_auth_stub(self) -> None:
        """A3: auth_provider=stub → kwargs['auth'] is stub (identity)."""

        class StubAuth(httpx2.Auth):
            def auth_flow(self, request):  # type: ignore[no-untyped-def]
                yield request

        stub = StubAuth()
        kwargs = sh._build_production_httpx_kwargs(headers={}, auth_provider=stub)
        assert kwargs["auth"] is stub
        assert kwargs["headers"] == {}
        assert "follow_redirects" not in kwargs  # DD12.1: inert under mcp 2.x
        assert kwargs["timeout"] == httpx2.Timeout(30.0, read=300.0)


# ---------------------------------------------------------------------------
# A4 — Both transport functions invoke _build_production_httpx_kwargs
# ---------------------------------------------------------------------------


def test_both_transport_functions_call_build_production_httpx_kwargs() -> None:
    """A4: single source of truth for production-path kwargs.

    ``connect_streamable_http`` is a thin ``@asynccontextmanager`` over
    ``_open_streamable_http_transport_stack`` (Mission 29: one implementation
    of the three client branches, so the DD1 hook cannot drift), and the stack
    helper builds the production client through the kwargs helper. Source-string
    inspection keeps both facts grep-checkable from the test surface.
    """
    cm_src = inspect.getsource(sh.connect_streamable_http)
    stack_src = inspect.getsource(sh._open_streamable_http_transport_stack)
    assert "_open_streamable_http_transport_stack" in cm_src
    assert "_build_production_httpx_kwargs" in stack_src


# ---------------------------------------------------------------------------
# A5 — MCPClient.__init__ threads auth_provider to the transport
# ---------------------------------------------------------------------------


async def test_mcp_client_threads_auth_provider_to_streamable_http_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A5: MCPClient(source, auth_provider=stub).connect() reaches the
    streamable-http transport with stub.

    Spy on ``_open_streamable_http_transport_stack`` and capture its
    keyword arguments at the dispatcher layer. The actual SDK is not
    invoked — the spy raises a sentinel that ``MCPClient.connect``
    surfaces as ``MCPConnectionError``; the assertion fires on the
    captured spy state regardless.
    """
    captured: dict[str, Any] = {}

    class _SentinelError(Exception):
        pass

    async def _fake_open(
        source: MCPSource,
        *,
        http_client: httpx2.AsyncClient | None = None,
        auth_provider: httpx2.Auth | None = None,
    ) -> tuple[Any, Any]:
        captured["source_id"] = source.id
        captured["auth_provider"] = auth_provider
        raise _SentinelError("spy")

    monkeypatch.setattr(
        "the_one.mcp.transports.streamable_http._open_streamable_http_transport_stack",
        _fake_open,
    )

    class StubAuth(httpx2.Auth):
        def auth_flow(self, request):  # type: ignore[no-untyped-def]
            yield request

    stub = StubAuth()
    source = _http_source()
    client = MCPClient(source, auth_provider=stub)
    # connect() will translate the sentinel into MCPConnectionError, but
    # the spy has already captured the auth_provider kwarg.
    with pytest.raises(Exception):
        await client.connect()
    assert captured["source_id"] == "src-1"
    assert captured["auth_provider"] is stub


# ---------------------------------------------------------------------------
# A6 — Test seam factory pattern
# ---------------------------------------------------------------------------


async def test_test_seam_factory_callable_invoked_with_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A6: when ``_test_http_client_override`` is a callable factory, the
    transport invokes it with the source's headers and uses the
    returned client. Headers are NOT mutated post-construction.

    The factory raises a sentinel after capture so we don't enter the
    SDK's async-with body (which would attempt real protocol I/O).
    """
    captured: dict[str, Any] = {}

    class _SentinelError(Exception):
        pass

    def factory(headers: dict[str, str]) -> httpx2.AsyncClient:
        captured["headers"] = dict(headers)
        # Raise so we don't enter streamable_http_client's body.
        raise _SentinelError("captured")

    monkeypatch.setattr(sh, "_test_http_client_override", factory)

    source = MCPSource(
        id="src-fact",
        name="x",
        type="streamable-http",
        config={"url": "https://example.com/mcp", "headers": {"X-Test": "1"}},
        secrets={"X-Secret": "shh"},
    )

    with pytest.raises(_SentinelError):
        async with sh.connect_streamable_http(source):
            pass

    # Headers passed to factory are the build_request_headers merge
    # (config + secrets, secrets winning).
    assert captured["headers"] == {"X-Test": "1", "X-Secret": "shh"}


# ---------------------------------------------------------------------------
# A7 — Test seam legacy pre-constructed client preserved
# ---------------------------------------------------------------------------


async def test_test_seam_legacy_pre_constructed_client_path_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A7: when ``_test_http_client_override`` is a pre-constructed
    ``httpx2.AsyncClient``, the transport detects type via ``isinstance``
    and uses the legacy path: headers are mutated post-construction.

    Mirrors the existing ``tests/test_mcp_integration.py`` pattern.
    """

    class _SentinelError(Exception):
        pass

    # Pre-constructed client — capture the ID so we know it (not a fresh
    # client from any factory) was used.
    pre_client = httpx2.AsyncClient()
    pre_id = id(pre_client)

    monkeypatch.setattr(sh, "_test_http_client_override", pre_client)

    captured: dict[str, Any] = {}

    # Patch streamable_http_client to capture the http_client kwarg
    # without entering the SDK's body.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _spy_streamable(url: str, http_client: httpx2.AsyncClient, **kwargs):  # type: ignore[no-untyped-def]
        captured["client_id"] = id(http_client)
        captured["client_headers"] = dict(http_client.headers)
        raise _SentinelError("captured")
        yield  # pragma: no cover  (unreachable; documents generator shape)

    monkeypatch.setattr(sh, "streamable_http_client", _spy_streamable)

    source = MCPSource(
        id="src-legacy",
        name="x",
        type="streamable-http",
        config={"url": "https://example.com/mcp", "headers": {"X-Legacy": "1"}},
        secrets={},
    )

    with pytest.raises(_SentinelError):
        async with sh.connect_streamable_http(source):
            pass

    # Same pre-constructed client used (NOT a fresh factory client)
    assert captured["client_id"] == pre_id
    # Headers were mutated on the pre-constructed client
    assert captured["client_headers"].get("x-legacy") == "1"

    await pre_client.aclose()


# ---------------------------------------------------------------------------
# A8 — MCPClient.call_tool translates SDK auth exceptions to MCPAuthRequired
# ---------------------------------------------------------------------------


async def test_call_tool_translates_oauth_token_error_to_mcp_auth_required() -> None:
    """A8a: stub session.call_tool raises OAuthTokenError → MCPAuthRequired."""
    source = _http_source()
    client = MCPClient(source)
    # Plug in connected state without invoking real connect().
    client._is_alive = True
    client._session = AsyncMock()
    client._session.call_tool.side_effect = OAuthTokenError("refresh failed")
    # Pre-populate _tools_cache so call_tool's lazy list_tools() doesn't fire.
    client._tools_cache = [
        MCPTool(
            name="t",
            description="x",
            input_schema={"type": "object", "properties": {}},
            output_schema=None,
            annotations=None,
        )
    ]

    with pytest.raises(MCPAuthRequired) as exc_info:
        await client.call_tool("t", {})
    assert exc_info.value.source_id == "src-1"
    assert exc_info.value.resource_metadata_url is None
    assert exc_info.value.consent_url is None
    assert str(exc_info.value) == "Authorization required for MCP source src-1"


async def test_call_tool_translates_oauth_flow_error_to_mcp_auth_required() -> None:
    """A8b: stub session.call_tool raises OAuthFlowError → MCPAuthRequired."""
    source = _http_source(source_id="src-2")
    client = MCPClient(source)
    client._is_alive = True
    client._session = AsyncMock()
    client._session.call_tool.side_effect = OAuthFlowError("discovery failed")
    client._tools_cache = [
        MCPTool(
            name="t",
            description="x",
            input_schema={"type": "object", "properties": {}},
            output_schema=None,
            annotations=None,
        )
    ]

    with pytest.raises(MCPAuthRequired) as exc_info:
        await client.call_tool("t", {})
    assert exc_info.value.source_id == "src-2"
    assert exc_info.value.resource_metadata_url is None
    assert exc_info.value.consent_url is None


# ---------------------------------------------------------------------------
# A9 — the no-provider 401 -> MCPAuthRequired translation
# ---------------------------------------------------------------------------
#
# The synthetic ``ExceptionGroup(httpx2.HTTPStatusError)`` test that lived here
# is gone: mcp 2.x no longer raises HTTPStatusError for a 401 (it becomes
# ``MCPError(INTERNAL_ERROR, "Server returned an error response")`` and drops
# the headers), so the translation now reads the transport's response-hook
# record (DD1). It is proven against a REAL 401 over HTTP in
# ``tests/test_mcp_signin_detection.py``.
