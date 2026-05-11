"""Factory: build an OAuthClientProvider for a source.

Centralizes the per-source provider construction that was sketched at L4 design
time and deferred via Option B. The factory reads ``source.secrets["dcr_credentials"]``
and dispatches:

  - Absent / no ``client_id`` → returns ``None`` (caller proceeds with no auth).
  - DCR-registered → standard SDK ``OAuthClientProvider``.

In both non-None cases the provider is wired with handlers from
``make_oauth_handlers`` (L2) and a ``MCPSourceTokenStorage`` instance (L2),
plus our standard ``OAuthClientMetadata`` (loopback redirect URI bound to
``settings.port``, ``token_endpoint_auth_method="none"`` per RFC 6749 §2.3.1
public-client guidance).

Design constraint (per L2's ``handlers.py`` async-context contract): this
factory MUST be invoked from inside an async context — ``make_oauth_handlers``
calls ``asyncio.get_running_loop().create_future()`` synchronously. The factory
itself is a sync function, so callers MUST be inside an async function (or
called from one) for the handlers to construct without a ``RuntimeError``.

Production callers (L5):
  - ``the_one.mcp._pool._entry_worker`` — invoked at pool spawn-time inside
    an async worker task. ``chat_session_id`` is read from the
    ``current_chat_session_id`` ContextVar (set by the agent dispatch
    wrapper); falls back to a sentinel string when unset.
  - ``the_one.interfaces.web.api.oauth_start`` — invoked from the new
    ``/api/oauth/start`` route to drive the SDK flow synchronously and
    broadcast the second ``auth_required`` event (carrying the real
    ``consent_url``).

F6 L3 retirement (2026-05-08): chat_session_id remains a positional
parameter, but the_one/mcp/_pool::_entry_worker now reads it from the
canonical the_one.agent._context ContextVar (set by Agent._execute_tool
at per-tool-dispatch entry). When the ContextVar is unset (e.g. pool
spawn outside a tool dispatch), this factory returns None — no provider
construction — and the lazy 401 path surfaces at the next call_tool
boundary, where csid IS bound. The F5 silent-fallback sentinel is
retired; multi-tab cross-routing bug is fixed.
"""

from __future__ import annotations

import asyncio

import httpx
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientMetadata

from the_one.config import settings
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.mcp.oauth.handlers import make_oauth_handlers
from the_one.mcp.oauth.storage import MCPSourceTokenStorage


def build_oauth_provider_for_source(
    source: MCPSource,
    repo: MCPSourceRepository,
    chat_session_id: str | None,
    source_id: str | None = None,
    tool_call_id: str | None = None,
    resource_metadata_url: str | None = None,
    *,
    consent_url_future: asyncio.Future[str] | None = None,
    allow_dcr_bootstrap: bool = False,
) -> httpx.Auth | None:
    """Construct the appropriate OAuthClientProvider for ``source``, or None.

    Returns ``None`` when ``source.secrets["dcr_credentials"]`` is absent or
    missing a ``client_id`` AND ``allow_dcr_bootstrap`` is False — callers
    then connect without an auth provider (the lazy-path 401 surfaces via
    L4's ``MCPAuthRequired`` translation).

    When ``dcr_credentials`` is populated, returns a standard
    ``OAuthClientProvider`` that goes through full RFC 9728 PRM + RFC 8414
    OASM + RFC 7591 DCR.

    When ``allow_dcr_bootstrap=True`` AND ``dcr_credentials`` is absent, the
    function still constructs an ``OAuthClientProvider``; the SDK's auth
    flow runs DCR on first request (``MCPSourceTokenStorage.get_client_info``
    returns None → SDK falls through to DCR registration). This is the F6.5
    L3 Test endpoint path: the operator clicks Test on a freshly-saved source
    with no creds, the SDK runs DCR + auth in one round-trip, tokens persist.

    The handlers + storage are constructed fresh per call (closure-capture
    invariant from L2's ``make_oauth_handlers`` — five concurrent flows
    register five distinct state tokens).

    ``consent_url_future`` is forwarded to ``make_oauth_handlers``; when
    supplied, the redirect_handler resolves it with the authorization_url.
    The F6.5 L3 Test endpoint uses this; production chat paths pass None.
    """
    # F6 L3: when no chat session is bound to the current task, no
    # provider can be constructed — the redirect_handler would have
    # nowhere to broadcast auth_required. Return None; the MCPClient
    # connects without auth and the lazy 401 path surfaces
    # MCPAuthRequired at next call_tool. That dispatch DOES have a
    # csid bound (via the agent layer's _execute_tool wrapper) and
    # routes correctly. This short-circuit MUST run BEFORE any
    # ``source.secrets.get`` / ``make_oauth_handlers`` work — handlers
    # parameterised on a None csid would have nowhere to broadcast.
    if chat_session_id is None:
        return None
    dcr = source.secrets.get("dcr_credentials")
    if (not dcr or not dcr.get("client_id")) and not allow_dcr_bootstrap:
        return None

    sid = source_id or source.id
    redirect_handler, callback_handler = make_oauth_handlers(
        chat_session_id=chat_session_id,
        source_id=sid,
        tool_call_id=tool_call_id,
        resource_metadata_url=resource_metadata_url,
        source_name=source.name,
        consent_url_future=consent_url_future,
    )
    storage = MCPSourceTokenStorage(repo, source.id)
    client_metadata = OAuthClientMetadata(
        client_name="the-one",
        redirect_uris=[f"http://127.0.0.1:{settings.port}/api/oauth/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )

    server_url = source.config.get("url", "")
    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )
