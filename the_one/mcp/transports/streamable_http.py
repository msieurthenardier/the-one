"""Streamable-HTTP transport for MCPClient.

Implements the wire-shape glue between F1's MCPSource model and the
official mcp SDK's streamable_http_client. The transport itself is a
single async-context-manager (`connect_streamable_http`) that yields a
fully-entered `ClientSession`; MCPClient only sees the session, never
the (read, write) stream tuple.

Headers are assembled from the operator's kv-table at request time:
non-sensitive rows live in `source.config.headers` (plaintext at rest);
sensitive rows in `source.secrets` (Fernet-encrypted at rest). The two
are flat-merged with secrets winning on collision. Static-bearer auth
emerges from the kv-table — the operator types
`Authorization | Bearer xxx | sensitive=true` as one row.

See flight 02 design decision §11 for the env-var-assembly precedent
that this helper mirrors structurally.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from the_one.db.models import MCPSource

__all__ = ["build_request_headers", "connect_streamable_http"]


# TEST-ONLY seam — integration test fixtures monkeypatch this to inject
# an ASGI-transport httpx.AsyncClient so tests can run against the
# in-process FastMCP fixture (no real network). Production code paths
# NEVER read or write this attribute outside `connect_streamable_http`.
# Excluded from `__all__` AND underscore-prefixed; do not promote.
_test_http_client_override: httpx.AsyncClient | None = None


def build_request_headers(source: MCPSource) -> dict[str, str]:
    """Materialize the HTTP request headers for a streamable-http MCP source.

    Flat-merge of source.config.get("headers", {}) and source.secrets, with
    secrets winning on collision. Mirrors the env-var-assembly pattern
    in transports/stdio.py (L5).

    Trusts F1's API validator to have gated the shape — does not re-validate.
    """
    config_headers: dict[str, str] = source.config.get("headers", {}) or {}
    return {**config_headers, **source.secrets}


@asynccontextmanager
async def connect_streamable_http(
    source: MCPSource,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> AsyncIterator[ClientSession]:
    """Open an entered ClientSession over streamable-http transport.

    Yields a fully-entered ClientSession (initialize() NOT called — the
    caller — typically MCPClient.connect — runs the handshake). The
    session, transport, and (production-path-only) owned httpx client
    close in correct LIFO order on context exit.

    Headers from build_request_headers(source) are applied to the
    outgoing requests:
      - Production path (effective_client is None): the helper builds
        an httpx.AsyncClient with headers set at construction.
      - Test path (effective_client is not None — typically the L3
        ASGI fixture's client via the _test_http_client_override seam):
        the helper mutates effective_client.headers via dict.update()
        before yielding. The L3 fixture is per-test fresh so the
        mutation does not pollute later tests.
    """
    url: str = source.config["url"]
    headers = build_request_headers(source)

    # Test-injected client takes precedence ONLY when caller-supplied
    # http_client is None. F4 warm-pool callers (when they land) will
    # pass an explicit client and bypass the seam.
    effective_client = http_client
    if effective_client is None:
        effective_client = _test_http_client_override

    if effective_client is not None:
        # Test path: apply headers to the seam-injected client.
        effective_client.headers.update(headers)
        async with streamable_http_client(
            url, http_client=effective_client
        ) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                yield session
    else:
        # Production path: own the httpx lifecycle so headers + defaults
        # are applied at client-construction time. Defaults mirror the
        # SDK's create_mcp_http_client without depending on the private
        # mcp.shared._httpx_utils module.
        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
        ) as owned_client:
            async with streamable_http_client(
                url, http_client=owned_client
            ) as (read, write, _get_session_id):
                async with ClientSession(read, write) as session:
                    yield session
