"""Unit tests for the streamable-http auth-posture probe (F9 L1 Shape C, A6).

The probe (`the_one.mcp.transports.streamable_http._probe_auth_posture`) is a
bare `httpx.AsyncClient` POST that bypasses the MCP SDK entirely. Tests use
`httpx.MockTransport` so each scenario is hermetic — no real network.

Coverage:
  - 200 OK → "no_auth"
  - 401 with WWW-Authenticate → "oauth"
  - 401 without WWW-Authenticate → "oauth" (broken-server tolerance)
  - 5xx → "error"
  - Network failure (httpx.ConnectError) → "error"
  - Timeout → "error"
"""

from __future__ import annotations

import httpx
import pytest

from the_one.mcp.transports import streamable_http as transport_mod


@pytest.fixture
def patch_async_client(monkeypatch):
    """Replace httpx.AsyncClient inside the transport module with a factory
    that injects an arbitrary handler via httpx.MockTransport.

    Tests pass a callable `handler(request) -> httpx.Response` (or raises)
    and the fixture wraps it so the probe's bare-client construction
    transparently routes through the mock transport.
    """

    def _install(handler):
        original = httpx.AsyncClient

        class _PatchedAsyncClient(original):  # type: ignore[misc, valid-type]
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = httpx.MockTransport(handler)
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(transport_mod.httpx, "AsyncClient", _PatchedAsyncClient)

    return _install


async def test_probe_returns_no_auth_on_200(patch_async_client) -> None:
    """200 OK on initialize → server processed the handshake → 'no_auth'."""
    captured = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["accept"] = request.headers.get("accept")
        captured["content_type"] = request.headers.get("content-type")
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "serverInfo": {"name": "stub", "version": "0.1"},
                },
            },
        )

    patch_async_client(_handler)
    verdict = await transport_mod._probe_auth_posture("https://example.com/mcp")
    assert verdict == "no_auth"
    # Probe MUST send the spec-mandated Accept + Content-Type headers
    # (otherwise compliant no-auth servers respond 406 / 415).
    assert captured["accept"] == "application/json, text/event-stream"
    assert captured["content_type"] == "application/json"
    # Probe MUST NOT carry an Authorization header — auth-required
    # detection depends on the absence of auth.
    assert captured["authorization"] is None


async def test_probe_returns_oauth_on_401_with_www_authenticate(
    patch_async_client,
) -> None:
    """401 + WWW-Authenticate → server requires OAuth → 'oauth'."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            headers={
                "WWW-Authenticate": (
                    'Bearer resource_metadata="https://example.com/'
                    '.well-known/oauth-protected-resource"'
                )
            },
        )

    patch_async_client(_handler)
    verdict = await transport_mod._probe_auth_posture("https://example.com/mcp")
    assert verdict == "oauth"


async def test_probe_returns_oauth_on_401_without_www_authenticate(
    patch_async_client,
) -> None:
    """401 with no WWW-Authenticate → still 'oauth' (broken-server tolerance).

    Some MCP servers do not implement RFC 9728 metadata and therefore omit
    WWW-Authenticate. The probe must not gate on the header presence — a
    bare 401 is sufficient evidence that auth is required.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    patch_async_client(_handler)
    verdict = await transport_mod._probe_auth_posture("https://example.com/mcp")
    assert verdict == "oauth"


async def test_probe_returns_error_on_5xx(patch_async_client) -> None:
    """5xx → server error → 'error' (not no_auth, not oauth)."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal server error")

    patch_async_client(_handler)
    verdict = await transport_mod._probe_auth_posture("https://example.com/mcp")
    assert verdict == "error"


async def test_probe_returns_error_on_network_failure(patch_async_client) -> None:
    """httpx.ConnectError (DNS, TLS, refused) → 'error'."""

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    patch_async_client(_handler)
    verdict = await transport_mod._probe_auth_posture("https://example.com/mcp")
    assert verdict == "error"


async def test_probe_returns_error_on_timeout(patch_async_client) -> None:
    """A request that exceeds the timeout surfaces as 'error'.

    Modeled by the mock transport raising httpx.ReadTimeout — the probe's
    except-clause covers httpx.RequestError (timeouts subclass it) and
    asyncio.TimeoutError.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timeout", request=request)

    patch_async_client(_handler)
    verdict = await transport_mod._probe_auth_posture("https://example.com/mcp", timeout=0.1)
    assert verdict == "error"
