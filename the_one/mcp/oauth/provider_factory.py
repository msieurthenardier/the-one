"""Factory: build an OAuthClientProvider (or ManualOAuthClientProvider) for a source.

Centralizes the per-source provider construction that was sketched at L4 design
time and deferred via Option B. The factory reads ``source.secrets["dcr_credentials"]``
and dispatches:

  - Absent / no ``client_id`` → returns ``None`` (caller proceeds with no auth).
  - ``registration_method == "manual"`` → ``ManualOAuthClientProvider`` with
    operator-supplied ``client_id`` + auth/token endpoints.
  - Else (DCR-registered) → standard SDK ``OAuthClientProvider``.

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

Architectural debt (carried to F6): the factory takes ``chat_session_id`` as
a positional parameter because L5 has no agent-layer plumbing for per-tool-
dispatch session routing. F6 will replace this with a ContextVar set inside
``Agent._execute_tool`` so the factory can read it without parameter
threading. See L5 flight log A17 notes.
"""

from __future__ import annotations

import httpx
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientMetadata

from the_one.config import settings
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.mcp.oauth.handlers import make_oauth_handlers
from the_one.mcp.oauth.manual_metadata import ManualOAuthClientProvider, ManualOAuthMetadata
from the_one.mcp.oauth.storage import MCPSourceTokenStorage


def build_oauth_provider_for_source(
    source: MCPSource,
    repo: MCPSourceRepository,
    chat_session_id: str,
    source_id: str | None = None,
    tool_call_id: str | None = None,
    resource_metadata_url: str | None = None,
) -> httpx.Auth | None:
    """Construct the appropriate OAuthClientProvider for ``source``, or None.

    Returns ``None`` when ``source.secrets["dcr_credentials"]`` is absent or
    missing a ``client_id`` — callers then connect without an auth provider
    (the lazy-path 401 surfaces via L4's ``MCPAuthRequired`` translation).

    When ``dcr_credentials`` is populated:
      - ``registration_method == "manual"`` returns a
        ``ManualOAuthClientProvider`` (skips RFC 7591 DCR + RFC 8414 OASM
        discovery; uses the operator-supplied auth + token endpoints).
      - Anything else returns a standard ``OAuthClientProvider`` that goes
        through full RFC 9728 PRM + RFC 8414 OASM + RFC 7591 DCR.

    The handlers + storage are constructed fresh per call (closure-capture
    invariant from L2's ``make_oauth_handlers`` — five concurrent flows
    register five distinct state tokens).
    """
    dcr = source.secrets.get("dcr_credentials")
    if not dcr or not dcr.get("client_id"):
        return None

    sid = source_id or source.id
    redirect_handler, callback_handler = make_oauth_handlers(
        chat_session_id=chat_session_id,
        source_id=sid,
        tool_call_id=tool_call_id,
        resource_metadata_url=resource_metadata_url,
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
    if dcr.get("registration_method") == "manual":
        manual = ManualOAuthMetadata(
            client_id=dcr["client_id"],
            auth_endpoint=dcr["auth_endpoint"],
            token_endpoint=dcr["token_endpoint"],
        )
        return ManualOAuthClientProvider(
            server_url=server_url,
            client_metadata=client_metadata,
            storage=storage,
            redirect_handler=redirect_handler,
            callback_handler=callback_handler,
            manual_metadata=manual,
        )
    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )
