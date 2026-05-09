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

from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator, Callable

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from the_one.db.models import MCPSource

__all__ = ["build_request_headers", "connect_streamable_http"]


# F5 L4: factory shape for the test seam — invoked with `headers` dict;
# returns a pre-constructed `httpx.AsyncClient` (typically with `auth=`
# attached at construction time). OAuth-enabled tests use this shape
# because `auth=` MUST be set at httpx-client construction time and
# cannot be added via post-construction header mutation.
_HttpClientFactory = Callable[[dict[str, str]], httpx.AsyncClient]


# TEST-ONLY seam — integration test fixtures monkeypatch this to inject
# an ASGI-transport httpx.AsyncClient so tests can run against the
# in-process FastMCP fixture (no real network). Production code paths
# NEVER read or write this attribute outside `connect_streamable_http`.
# Excluded from `__all__` AND underscore-prefixed; do not promote.
#
# F5 L4: extended type to also accept a factory callable
# `Callable[[dict[str, str]], httpx.AsyncClient]`. The transport
# detects the type at use-time:
#   - pre-constructed `httpx.AsyncClient` → legacy path (mutate
#     headers post-construction).
#   - factory callable → invoke with headers; factory owns construction
#     (including `auth=` if needed by OAuth-enabled tests).
#   - None → production path; transport constructs its own client.
_test_http_client_override: httpx.AsyncClient | _HttpClientFactory | None = None


def build_request_headers(source: MCPSource) -> dict[str, str]:
    """Materialize the HTTP request headers for a streamable-http MCP source.

    Flat-merge of source.config.get("headers", {}) and source.secrets, with
    secrets winning on collision. Mirrors the env-var-assembly pattern
    in transports/stdio.py (L5).

    Trusts F1's API validator to have gated the shape — does not re-validate.
    """
    config_headers: dict[str, str] = source.config.get("headers", {}) or {}
    return {**config_headers, **source.secrets}


def _build_production_httpx_kwargs(
    headers: dict[str, str], auth_provider: httpx.Auth | None
) -> dict[str, Any]:
    """Build the kwargs dict used to construct the production-path httpx.AsyncClient.

    Extracted as a unit-testable helper (F5 L4: AC A2/A3/A4 unit-test
    this helper directly without entering streamable_http_client's
    async-with body, which would attempt real HTTP).

    F5 L4: auth_provider is provided pre-built by the caller; provider
    construction (factory function that reads secrets["dcr_credentials"]
    and instantiates OAuthClientProvider with
    handlers) is L6's scope. L6 builds the factory and the agent-layer
    wiring that calls it.
    """
    return {
        "headers": headers,
        "follow_redirects": True,
        "timeout": httpx.Timeout(30.0),
        "auth": auth_provider,  # None when no provider is supplied
    }


@asynccontextmanager
async def connect_streamable_http(
    source: MCPSource,
    *,
    http_client: httpx.AsyncClient | None = None,
    # F5 L4: auth_provider is provided pre-built by the caller; provider
    # construction (factory function that reads secrets["dcr_credentials"]
    # and instantiates OAuthClientProvider with
    # handlers) is L6's scope. L6 builds the factory and the agent-layer
    # wiring that calls it.
    auth_provider: httpx.Auth | None = None,
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
      - Test factory path (effective_client is callable): invoke the
        factory with headers; factory owns construction (including
        `auth=`); F5 L4 OAuth-enabled tests use this path.
    """
    url: str = source.config["url"]
    headers = build_request_headers(source)

    # Test-injected client takes precedence ONLY when caller-supplied
    # http_client is None. F4 warm-pool callers (when they land) will
    # pass an explicit client and bypass the seam.
    effective_client: httpx.AsyncClient | _HttpClientFactory | None = http_client
    if effective_client is None:
        effective_client = _test_http_client_override

    # Type checks ordered: pre-constructed AsyncClient FIRST (it has a
    # __call__-shaped attribute lookup quirk on some httpx versions —
    # the explicit isinstance check disambiguates), THEN callable, THEN
    # None.
    if isinstance(effective_client, httpx.AsyncClient):
        # Legacy test path: apply headers to the seam-injected client.
        effective_client.headers.update(headers)
        async with streamable_http_client(
            url, http_client=effective_client
        ) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                yield session
    elif callable(effective_client):
        # F5 L4 factory test path: factory owns construction (incl. auth=).
        fresh_client = effective_client(headers)
        async with streamable_http_client(
            url, http_client=fresh_client
        ) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                yield session
    else:
        # Production path: own the httpx lifecycle so headers + defaults
        # are applied at client-construction time. Defaults mirror the
        # SDK's create_mcp_http_client without depending on the private
        # mcp.shared._httpx_utils module.
        kwargs = _build_production_httpx_kwargs(headers, auth_provider)
        async with httpx.AsyncClient(**kwargs) as owned_client:
            async with streamable_http_client(
                url, http_client=owned_client
            ) as (read, write, _get_session_id):
                async with ClientSession(read, write) as session:
                    yield session


async def _open_streamable_http_transport_stack(
    source: MCPSource,
    *,
    http_client: httpx.AsyncClient | None = None,
    # F5 L4: auth_provider is provided pre-built by the caller; provider
    # construction (factory function that reads secrets["dcr_credentials"]
    # and instantiates OAuthClientProvider with
    # handlers) is L6's scope. L6 builds the factory and the agent-layer
    # wiring that calls it.
    auth_provider: httpx.Auth | None = None,
) -> tuple[ClientSession, AsyncExitStack]:
    """Open an entered ClientSession + return the AsyncExitStack that owns it.

    SAME-TASK CONTRACT: caller MUST drive ``stack.aclose()`` from the same task.
    The F4 pool's ``_entry_worker`` wraps everything in one task naturally.

    The dispatcher (``_transport_connect``) consumes this helper. Per F5 L1
    speculative-mechanism framing: this MAY retire the F4-HAT-Finding-#1
    warning for F4-pool-routed (same-task) disconnects by collapsing the
    dispatcher's the-one-owned ``@asynccontextmanager`` wrapper layer.
    Empirical verification at F5 L6 HAT.

    The existing ``connect_streamable_http`` ``@asynccontextmanager`` continues
    to exist for back-compat with its 1 prior async-CM caller
    (``tests/test_mcp_client.py::TestConnectStreamableHttpProduction``).
    """
    url: str = source.config["url"]
    headers = build_request_headers(source)

    # Test-injected client takes precedence ONLY when caller-supplied
    # http_client is None — mirrors the legacy CM's seam contract.
    effective_client: httpx.AsyncClient | _HttpClientFactory | None = http_client
    if effective_client is None:
        effective_client = _test_http_client_override

    stack = AsyncExitStack()
    try:
        if isinstance(effective_client, httpx.AsyncClient):
            # Legacy test path: apply headers to the seam-injected client.
            effective_client.headers.update(headers)
            read, write, _get_session_id = await stack.enter_async_context(
                streamable_http_client(url, http_client=effective_client)
            )
        elif callable(effective_client):
            # F5 L4 factory test path: factory owns construction (incl. auth=).
            fresh_client = effective_client(headers)
            read, write, _get_session_id = await stack.enter_async_context(
                streamable_http_client(url, http_client=fresh_client)
            )
        else:
            # Production path: own the httpx lifecycle so headers + defaults
            # are applied at client-construction time. Defaults mirror the
            # legacy CM's settings.
            kwargs = _build_production_httpx_kwargs(headers, auth_provider)
            owned_client = await stack.enter_async_context(
                httpx.AsyncClient(**kwargs)
            )
            read, write, _get_session_id = await stack.enter_async_context(
                streamable_http_client(url, http_client=owned_client)
            )
        session = await stack.enter_async_context(ClientSession(read, write))
        return session, stack
    except BaseException:
        await stack.aclose()
        raise
