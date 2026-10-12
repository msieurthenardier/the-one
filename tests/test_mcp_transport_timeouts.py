"""Timeout configuration for the streamable-HTTP transport.

The production httpx client MUST keep its ``read`` timeout separate from (and
much longer than) the general timeout. The streamable-HTTP client opens a
standalone long-lived ``GET`` SSE stream for server-initiated messages; a
server with nothing to push sends nothing on it, so ``read`` governs how long
we tolerate silence there.

A flat ``httpx2.Timeout(30.0)`` — which is what this shipped with until the
0.5.0 fix — makes httpx raise ``ReadTimeout`` on that idle stream after 30s and
tear the connection down. Servers that read a dropped GET stream as "client
disconnected" (Goldfinch is one) then destroy the whole MCP session, and every
subsequent POST 404s as ``Session terminated``. These tests are the regression
net for that.
"""

from __future__ import annotations

import httpx2

from the_one.mcp.transports.streamable_http import (
    _HTTP_TIMEOUT_SECONDS,
    _SSE_READ_TIMEOUT_SECONDS,
    _build_production_httpx_kwargs,
)


class TestProductionTimeouts:
    def test_read_timeout_is_not_the_general_timeout(self) -> None:
        """The regression this file exists for: read must NOT collapse to 30s."""
        timeout = _build_production_httpx_kwargs({}, None)["timeout"]
        assert isinstance(timeout, httpx2.Timeout)
        assert timeout.read == _SSE_READ_TIMEOUT_SECONDS
        assert timeout.read > timeout.connect
        assert timeout.read == 300.0

    def test_non_read_timeouts_stay_at_the_general_value(self) -> None:
        timeout = _build_production_httpx_kwargs({}, None)["timeout"]
        assert timeout.connect == _HTTP_TIMEOUT_SECONDS
        assert timeout.write == _HTTP_TIMEOUT_SECONDS
        assert timeout.pool == _HTTP_TIMEOUT_SECONDS

    def test_matches_the_sdk_recommended_defaults(self) -> None:
        """Drift tripwire against the SDK's ``create_mcp_http_client`` values.

        We deliberately do not import the private ``mcp.shared._httpx_utils``
        in production code, so this test is what keeps the local copies honest.
        If the SDK retunes its recommended timeouts, this fails and the
        constants in ``streamable_http.py`` get updated to match.
        """
        from mcp.shared._httpx_utils import (
            MCP_DEFAULT_SSE_READ_TIMEOUT,
            MCP_DEFAULT_TIMEOUT,
        )

        assert _HTTP_TIMEOUT_SECONDS == MCP_DEFAULT_TIMEOUT
        assert _SSE_READ_TIMEOUT_SECONDS == MCP_DEFAULT_SSE_READ_TIMEOUT

    def test_other_production_kwargs_are_preserved(self) -> None:
        """The timeout fix must not have disturbed the rest of the bag."""
        auth = httpx2.BasicAuth("u", "p")
        kwargs = _build_production_httpx_kwargs({"Authorization": "Bearer x"}, auth)
        assert kwargs["headers"] == {"Authorization": "Bearer x"}
        # DD12.1: the inert follow_redirects=True is gone (mcp 2.x follows only
        # same-origin, method-preserving redirects itself and never reads it).
        assert "follow_redirects" not in kwargs
        assert kwargs["auth"] is auth
        assert "event_hooks" not in kwargs  # only when a sign-in hook is supplied

    def test_sign_in_hook_is_installed_at_construction(self) -> None:
        async def hook(response):  # pragma: no cover - never invoked
            return None

        kwargs = _build_production_httpx_kwargs({}, None, hook)
        assert kwargs["event_hooks"] == {"response": [hook]}

    def test_sse_event_cap_is_explicit_and_equals_the_sdk_default(self) -> None:
        """DD8: the 1 MiB cap is a named the-one constant, passed explicitly, and
        pinned to the SDK default so an SDK change shows up as a failing diff."""
        from mcp.client.streamable_http import DEFAULT_MAX_SSE_EVENT_SIZE

        from the_one.mcp.transports.streamable_http import MAX_SSE_EVENT_BYTES

        assert MAX_SSE_EVENT_BYTES == 1024 * 1024
        assert MAX_SSE_EVENT_BYTES == DEFAULT_MAX_SSE_EVENT_SIZE
