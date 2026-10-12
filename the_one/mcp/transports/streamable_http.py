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

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, Literal

import httpx2
from mcp import ClientSession
from mcp.client.auth.utils import extract_field_from_www_auth
from mcp.client.streamable_http import streamable_http_client

from the_one.db.models import MCPSource
from the_one.mcp._signin_record import (
    _AUTH_RECORDS,
    MAX_SSE_EVENT_BYTES,
    AuthRecord,
    auth_record_for,
)
from the_one.mcp.oauth.storage import OAUTH_MANAGED_SECRET_KEYS

__all__ = [
    "MAX_SSE_EVENT_BYTES",
    "AuthRecord",
    "_probe_auth_posture",
    "auth_record_for",
    "build_request_headers",
    "connect_streamable_http",
]


def _origin(url: "httpx2.URL") -> tuple[str, str, int | None]:
    return (url.scheme, url.host, url.port)


def _make_auth_hook(
    endpoint_url: str, record: AuthRecord
) -> Callable[["httpx2.Response"], Awaitable[None]]:
    """Build the async, headers-only response hook that fills ``record``.

    Scope: only responses to an MCP POST (method POST, same origin as the
    endpoint, ``accept`` naming ``text/event-stream`` - the SDK's MCP POSTs
    carry ``application/json, text/event-stream``; the OAuth flow's token / DCR
    POSTs and discovery GETs do not). Never reads the body.
    """
    endpoint_origin = _origin(httpx2.URL(endpoint_url))

    async def _hook(response: httpx2.Response) -> None:
        request = response.request
        if request.method != "POST":
            return
        if _origin(request.url) != endpoint_origin:
            return
        if "text/event-stream" not in request.headers.get("accept", ""):
            return
        record.seq += 1
        record.last_status = response.status_code
        record.last_resource_metadata = (
            extract_field_from_www_auth(response, "resource_metadata")
            if response.status_code == 401
            else None
        )

    return _hook


def _attach_hook(client: "httpx2.AsyncClient", hook: Any, stack: AsyncExitStack | None) -> Any:
    """Append ``hook`` to ``client``'s response hooks; when ``stack`` is given,
    remove exactly that hook on stack exit (a shared seam client outlives the
    connection). Returns a remover for CM-style callers."""
    client.event_hooks["response"].append(hook)

    def _remove() -> None:
        try:
            client.event_hooks["response"].remove(hook)
        except ValueError:
            pass

    if stack is not None:
        stack.callback(_remove)
    return _remove


# Mirror of the SDK's ``create_mcp_http_client`` defaults (MCP_DEFAULT_TIMEOUT /
# MCP_DEFAULT_SSE_READ_TIMEOUT in the private ``mcp.shared._httpx_utils``). Kept
# as local constants rather than imported so we don't depend on a private module;
# ``tests/test_mcp_transport_timeouts.py`` asserts they stay equal to the SDK's.
_HTTP_TIMEOUT_SECONDS = 30.0
"""Connect/write/pool timeout for ordinary request-response MCP traffic."""

_SSE_READ_TIMEOUT_SECONDS = 300.0
"""Read timeout — MUST stay far longer than ``_HTTP_TIMEOUT_SECONDS``.

The streamable-HTTP client opens a standalone long-lived ``GET`` SSE stream
(started the moment ``notifications/initialized`` is sent) that carries
server-initiated messages. A server with nothing to push sends NOTHING on it,
possibly for its whole lifetime — so ``read`` governs how long we tolerate
silence on that stream, not how long a tool call may take (``call_tool`` has
its own ``asyncio.timeout`` budget in ``MCPClient``).

Setting a short flat timeout here is actively harmful: httpx raises
``ReadTimeout`` on the idle GET stream and tears the connection down, and a
server that reads GET-stream close as "client disconnected" then destroys the
whole MCP session. Every subsequent POST gets 404, which the SDK surfaces as
``Session terminated`` — an unrecoverable state until the pool entry is
evicted. Goldfinch (``mcp-server.js``) does exactly this, which is how a flat
30s timeout here broke every MCP session 30 seconds after it opened.
"""


# F5 L4: factory shape for the test seam — invoked with `headers` dict;
# returns a pre-constructed `httpx2.AsyncClient` (typically with `auth=`
# attached at construction time). OAuth-enabled tests use this shape
# because `auth=` MUST be set at httpx-client construction time and
# cannot be added via post-construction header mutation.
_HttpClientFactory = Callable[[dict[str, str]], httpx2.AsyncClient]


# TEST-ONLY seam — integration test fixtures monkeypatch this to inject
# an ASGI-transport httpx2.AsyncClient so tests can run against the
# in-process MCPServer fixture (no real network). Production code paths
# NEVER read or write this attribute outside `connect_streamable_http`.
# Excluded from `__all__` AND underscore-prefixed; do not promote.
#
# F5 L4: extended type to also accept a factory callable
# `Callable[[dict[str, str]], httpx2.AsyncClient]`. The transport
# detects the type at use-time:
#   - pre-constructed `httpx2.AsyncClient` → legacy path (mutate
#     headers post-construction).
#   - factory callable → invoke with headers; factory owns construction
#     (including `auth=` if needed by OAuth-enabled tests).
#   - None → production path; transport constructs its own client.
_test_http_client_override: httpx2.AsyncClient | _HttpClientFactory | None = None


def build_request_headers(source: MCPSource) -> dict[str, str]:
    """Materialize the HTTP request headers for a streamable-http MCP source.

    Flat-merge of source.config.get("headers", {}) and the operator-supplied
    subset of source.secrets, with secrets winning on collision. OAuth-managed
    secret keys (access_token, refresh_token, token_expires_at, dcr_credentials)
    are FILTERED OUT — they are token state, not request headers, and several
    have non-string types (token_expires_at is a float; dcr_credentials is a
    dict) that would crash httpx with ``TypeError: Header value must be str
    or bytes``. The Authorization header is injected separately by the
    SDK's OAuthClientProvider via ``httpx2.AsyncClient(auth=provider, ...)``.

    Mirrors the env-var-assembly pattern in transports/stdio.py (L5).

    Trusts F1's API validator to have gated the operator-supplied shape —
    does not re-validate.

    Surrounding whitespace on string keys/values is stripped: an operator who
    pastes ``Bearer xxx `` with a trailing space (a common kv-table typo) would
    otherwise produce a header value that h11 rejects, crashing the outgoing
    httpx request with a LocalProtocolError BEFORE it reaches the server — which
    the auth-posture probe then miscategorises as a connection error. HTTP OWS
    semantics treat surrounding whitespace as insignificant anyway, so stripping
    is lossless. Non-string values (defensive) pass through untouched.
    """
    config_headers: dict[str, str] = source.config.get("headers", {}) or {}
    operator_secrets = {
        k: v for k, v in source.secrets.items() if k not in OAUTH_MANAGED_SECRET_KEYS
    }
    merged = {**config_headers, **operator_secrets}
    return {
        (k.strip() if isinstance(k, str) else k): (v.strip() if isinstance(v, str) else v)
        for k, v in merged.items()
    }


async def _probe_auth_posture(
    server_url: str,
    *,
    request_headers: dict[str, str] | None = None,
    timeout: float = 5.0,
) -> Literal["no_auth", "oauth", "error"]:
    """HTTP-level auth-posture probe — bypasses the MCP SDK entirely.

    Issues a single ``initialize`` JSON-RPC POST carrying the operator's
    configured request headers (``request_headers`` — typically
    ``build_request_headers(source)``), then inspects the status code:

    * ``200`` → server processed the initialize handshake → ``"no_auth"``.
      This INCLUDES static-bearer / custom-header auth: if the operator's
      headers already satisfy the server, no OAuth flow is needed and the
      SDK simply replays those headers on every request. Probing WITHOUT
      the operator headers would 401 here and misclassify a header-auth
      server as ``"oauth"``, triggering a doomed dynamic-client-registration
      flow against a server that has no OAuth endpoints.
    * ``401`` → the server still rejects the request even with the operator's
      headers applied → genuine OAuth (regardless of whether
      ``WWW-Authenticate`` is present — broken servers without RFC 9728
      metadata are still treated as ``"oauth"``) → ``"oauth"``.
    * Anything else (5xx, transport errors, timeouts) → ``"error"``.

    Why a bare ``httpx2.AsyncClient`` (and NOT the MCP SDK) is used here:

    * F9 L1 Anomaly A6 (Shape C resolution): engaging
      ``mcp.client.streamable_http`` for auth detection leaks an anyio
      cross-task cancel-scope error that propagates as ``CancelledError``
      up to the FastAPI handler. A bare ``httpx`` POST has no SDK
      transport stack to clean up — zero anyio surface.
    * The MCP spec's auth middleware short-circuits 401 BEFORE the
      streamable-http handler runs (otherwise auth-required servers
      would need to validate Accept headers before they could enforce
      auth). So a 401 is a definitive verdict; we don't need the
      Accept negotiation to succeed first.
    * No-auth servers, however, DO require the spec'd Accept and
      Content-Type headers — without them, a compliant server returns
      ``406 Not Acceptable`` or ``415 Unsupported Media Type`` which we
      would miscategorize as ``"error"``. The headers below mirror what
      the SDK's own client always sends per
      ``mcp/client/streamable_http.py`` (the ``MCP-Protocol-Version`` /
      ``Accept`` / ``Content-Type`` bundle).

    Reads ``the_one.mcp._PINNED_PROTOCOL_VERSION`` at call time (NOT at
    import time) so test monkeypatches stick — same convention as
    ``MCPClient.connect``.

    The 5s default timeout is tighter than ``_TEST_CONNECT_TIMEOUT``'s
    15s ceiling — a stuck network surfaces as ``"error"`` faster, and
    the caller still has 10s of headroom for the subsequent SDK round
    trip if the probe verdict is ``"oauth"`` and Phase B fires.

    Args:
        server_url: The streamable-http MCP server URL.
        timeout: Request timeout in seconds (default 5).

    Returns:
        ``"no_auth"``, ``"oauth"``, or ``"error"``.
    """
    # Lazy import — keeps test monkeypatches on the_one.mcp namespace
    # alive (read-at-call-time per F2 convention).
    from the_one import mcp as the_one_mcp

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": the_one_mcp._PINNED_PROTOCOL_VERSION,
            "clientInfo": {"name": "the-one", "version": "0.1"},
            "capabilities": {},
        },
    }
    # Spec'd negotiation headers first, then the operator's configured
    # request headers (static bearer, etc.) layered on top so a header-auth
    # server is recognised as no_auth rather than misread as oauth. Operator
    # headers win on collision — but they would not collide with Accept /
    # Content-Type in practice.
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        **(request_headers or {}),
    }
    try:
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(timeout)) as client:
            resp = await client.post(server_url, json=payload, headers=headers)
    except (httpx2.RequestError, asyncio.TimeoutError):
        return "error"
    except Exception:
        # Defensive — anything else (URL parse errors, etc.) → "error".
        return "error"

    if resp.status_code == 200:
        return "no_auth"
    if resp.status_code == 401:
        return "oauth"
    return "error"


def _build_production_httpx_kwargs(
    headers: dict[str, str],
    auth_provider: httpx2.Auth | None,
    response_hook: Callable[..., Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Build the kwargs dict used to construct the production-path httpx2.AsyncClient.

    Extracted as a unit-testable helper (F5 L4: AC A2/A3/A4 unit-test
    this helper directly without entering streamable_http_client's
    async-with body, which would attempt real HTTP).

    F5 L4: auth_provider is provided pre-built by the caller; provider
    construction (factory function that reads secrets["dcr_credentials"]
    and instantiates OAuthClientProvider with
    handlers) is L6's scope. L6 builds the factory and the agent-layer
    wiring that calls it.

    The timeout MUST keep ``read`` separate from the general timeout — see
    ``_SSE_READ_TIMEOUT_SECONDS``.

    No ``follow_redirects`` (Mission 29, DD12.1): the mcp 2.x transport follows
    only same-origin, method-preserving redirects itself and never consults the
    client's ``follow_redirects`` setting, so the old ``True`` was inert.

    ``response_hook`` is the DD1 sign-in record hook, installed at construction.
    """
    kwargs: dict[str, Any] = {
        "headers": headers,
        "timeout": httpx2.Timeout(_HTTP_TIMEOUT_SECONDS, read=_SSE_READ_TIMEOUT_SECONDS),
        "auth": auth_provider,  # None when no provider is supplied
    }
    if response_hook is not None:
        kwargs["event_hooks"] = {"response": [response_hook]}
    return kwargs


@asynccontextmanager
async def connect_streamable_http(
    source: MCPSource,
    *,
    http_client: httpx2.AsyncClient | None = None,
    # F5 L4: auth_provider is provided pre-built by the caller; provider
    # construction (factory function that reads secrets["dcr_credentials"]
    # and instantiates OAuthClientProvider with
    # handlers) is L6's scope. L6 builds the factory and the agent-layer
    # wiring that calls it.
    auth_provider: httpx2.Auth | None = None,
) -> AsyncIterator[ClientSession]:
    """Open an entered ClientSession over streamable-http transport.

    Yields a fully-entered ClientSession (initialize() NOT called — the
    caller — typically MCPClient.connect — runs the handshake). The
    session, transport, and (production-path-only) owned httpx2 client
    close in correct LIFO order on context exit.

    Headers from build_request_headers(source) are applied to the
    outgoing requests:
      - Production path (effective_client is None): the helper builds
        an httpx2.AsyncClient with headers set at construction.
      - Test path (effective_client is not None — typically the L3
        ASGI fixture's client via the _test_http_client_override seam):
        the helper mutates effective_client.headers via dict.update()
        before yielding. The L3 fixture is per-test fresh so the
        mutation does not pollute later tests.
      - Test factory path (effective_client is callable): invoke the
        factory with headers; factory owns construction (including
        `auth=`); F5 L4 OAuth-enabled tests use this path.

    All three branches install the DD1 sign-in record hook; the seam client's
    hook is removed on exit (the client is shared across connections).
    """
    session, stack = await _open_streamable_http_transport_stack(
        source, http_client=http_client, auth_provider=auth_provider
    )
    try:
        yield session
    finally:
        await stack.aclose()


async def _open_streamable_http_transport_stack(
    source: MCPSource,
    *,
    http_client: httpx2.AsyncClient | None = None,
    # F5 L4: auth_provider is provided pre-built by the caller; provider
    # construction (factory function that reads secrets["dcr_credentials"]
    # and instantiates OAuthClientProvider with
    # handlers) is L6's scope. L6 builds the factory and the agent-layer
    # wiring that calls it.
    auth_provider: httpx2.Auth | None = None,
) -> tuple[ClientSession, AsyncExitStack]:
    """Open an entered ClientSession + return the AsyncExitStack that owns it.

    SAME-TASK CONTRACT: caller MUST drive ``stack.aclose()`` from the same task.
    The F4 pool's ``_entry_worker`` wraps everything in one task naturally.

    The dispatcher (``_transport_connect``) consumes this helper. Per F5 L1
    speculative-mechanism framing: this MAY retire the F4-HAT-Finding-#1
    warning for F4-pool-routed (same-task) disconnects by collapsing the
    dispatcher's the-one-owned ``@asynccontextmanager`` wrapper layer.
    Empirical verification at F5 L6 HAT.

    ``connect_streamable_http`` is now a thin ``@asynccontextmanager`` over this
    helper, so there is ONE implementation of the three client branches (and of
    the DD1 hook installation).
    """
    url: str = source.config["url"]
    headers = build_request_headers(source)

    # Test-injected client takes precedence ONLY when caller-supplied
    # http_client is None — mirrors the legacy CM's seam contract.
    effective_client: httpx2.AsyncClient | _HttpClientFactory | None = http_client
    if effective_client is None:
        effective_client = _test_http_client_override

    record = AuthRecord()
    hook = _make_auth_hook(url, record)

    stack = AsyncExitStack()
    try:
        if isinstance(effective_client, httpx2.AsyncClient):
            # Legacy test path: apply headers to the seam-injected client; the
            # client is shared across connections, so the hook is removed on exit.
            effective_client.headers.update(headers)
            _attach_hook(effective_client, hook, stack)
            client = effective_client
        elif callable(effective_client):
            # F5 L4 factory test path: factory owns construction (incl. auth=).
            client = effective_client(headers)
            _attach_hook(client, hook, stack)
        else:
            # Production path: own the httpx2 lifecycle so headers + defaults
            # are applied at client-construction time.
            kwargs = _build_production_httpx_kwargs(headers, auth_provider, hook)
            client = await stack.enter_async_context(httpx2.AsyncClient(**kwargs))
        read, write = await stack.enter_async_context(
            streamable_http_client(url, http_client=client, max_sse_event_size=MAX_SSE_EVENT_BYTES)
        )
        session = await stack.enter_async_context(ClientSession(read, write))
        _AUTH_RECORDS[session] = record
        return session, stack
    except BaseException:
        await stack.aclose()
        raise
