"""Unit tests for the streamable-http auth-posture probe (F9 L1 Shape C, A6).

The probe (`the_one.mcp.transports.streamable_http._probe_auth_posture`) is a
bare `httpx2.AsyncClient` POST that bypasses the MCP SDK entirely. Tests use
`httpx2.MockTransport` so each scenario is hermetic — no real network.

Coverage:
  - 200 OK → "no_auth"
  - 401 with WWW-Authenticate → "oauth"
  - 401 without WWW-Authenticate → "oauth" (broken-server tolerance)
  - 5xx → "error"
  - Network failure (httpx2.ConnectError) → "error"
  - Timeout → "error"
"""

from __future__ import annotations

import httpx2
import pytest

from the_one.mcp.transports import streamable_http as transport_mod


@pytest.fixture
def patch_async_client(monkeypatch):
    """Replace httpx2.AsyncClient inside the transport module with a factory
    that injects an arbitrary handler via httpx2.MockTransport.

    Tests pass a callable `handler(request) -> httpx2.Response` (or raises)
    and the fixture wraps it so the probe's bare-client construction
    transparently routes through the mock transport.
    """

    def _install(handler):
        original = httpx2.AsyncClient

        class _PatchedAsyncClient(original):  # type: ignore[misc, valid-type]
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = httpx2.MockTransport(handler)
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(transport_mod.httpx2, "AsyncClient", _PatchedAsyncClient)

    return _install


async def test_probe_returns_no_auth_on_200(patch_async_client) -> None:
    """200 OK on initialize → server processed the handshake → 'no_auth'."""
    captured = {}

    def _handler(request: httpx2.Request) -> httpx2.Response:
        captured["url"] = str(request.url)
        captured["accept"] = request.headers.get("accept")
        captured["content_type"] = request.headers.get("content-type")
        captured["authorization"] = request.headers.get("authorization")
        return httpx2.Response(
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
    # With no request_headers supplied, the probe carries no Authorization
    # header — the legacy no-auth detection path is unchanged.
    assert captured["authorization"] is None


async def test_probe_forwards_operator_headers_static_bearer(
    patch_async_client,
) -> None:
    """A static-bearer server returns 401 unauthenticated but 200 with the
    operator's Authorization header → probe must classify it as 'no_auth'.

    Regression for the misclassification that made a header-auth MCP server
    (no OAuth endpoints) get treated as 'oauth', triggering a doomed dynamic
    client registration flow. The probe must replay the operator's configured
    request headers so header-gated servers are recognised.
    """
    captured = {}

    def _handler(request: httpx2.Request) -> httpx2.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["accept"] = request.headers.get("accept")
        if request.headers.get("authorization") != "Bearer s3cret":
            return httpx2.Response(401, json={"error": "unauthorized"})
        return httpx2.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}},
        )

    patch_async_client(_handler)
    verdict = await transport_mod._probe_auth_posture(
        "https://example.com/mcp",
        request_headers={"Authorization": "Bearer s3cret"},
    )
    assert verdict == "no_auth"
    # Operator header forwarded, spec headers still present.
    assert captured["authorization"] == "Bearer s3cret"
    assert captured["accept"] == "application/json, text/event-stream"


async def test_probe_oauth_when_operator_headers_insufficient(
    patch_async_client,
) -> None:
    """If even the operator's headers don't satisfy the server (still 401),
    the verdict stays 'oauth' — genuine OAuth servers are unaffected."""

    def _handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"error": "unauthorized"})

    patch_async_client(_handler)
    verdict = await transport_mod._probe_auth_posture(
        "https://example.com/mcp",
        request_headers={"X-Api-Key": "wrong"},
    )
    assert verdict == "oauth"


async def test_probe_returns_oauth_on_401_with_www_authenticate(
    patch_async_client,
) -> None:
    """401 + WWW-Authenticate → server requires OAuth → 'oauth'."""

    def _handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
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

    def _handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401)

    patch_async_client(_handler)
    verdict = await transport_mod._probe_auth_posture("https://example.com/mcp")
    assert verdict == "oauth"


async def test_probe_returns_error_on_5xx(patch_async_client) -> None:
    """5xx → server error → 'error' (not no_auth, not oauth)."""

    def _handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, text="Internal server error")

    patch_async_client(_handler)
    verdict = await transport_mod._probe_auth_posture("https://example.com/mcp")
    assert verdict == "error"


async def test_probe_returns_error_on_network_failure(patch_async_client) -> None:
    """httpx2.ConnectError (DNS, TLS, refused) → 'error'."""

    def _handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("Connection refused")

    patch_async_client(_handler)
    verdict = await transport_mod._probe_auth_posture("https://example.com/mcp")
    assert verdict == "error"


async def test_probe_returns_error_on_timeout(patch_async_client) -> None:
    """A request that exceeds the timeout surfaces as 'error'.

    Modeled by the mock transport raising httpx2.ReadTimeout — the probe's
    except-clause covers httpx2.RequestError (timeouts subclass it) and
    asyncio.TimeoutError.
    """

    def _handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("Read timeout", request=request)

    patch_async_client(_handler)
    verdict = await transport_mod._probe_auth_posture("https://example.com/mcp", timeout=0.1)
    assert verdict == "error"
