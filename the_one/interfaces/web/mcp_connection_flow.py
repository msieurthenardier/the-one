"""The MCP connection check's two large functions, split out of ``api.py`` (Mission 37 F2 L1).

A plain module, not a router: ``mcp_connection_api.py`` holds the routes and the builders and
imports this module; this module reaches the builders through ``mcp_connection_api`` at call
time (so a patch on a builder there applies here too, and there is no import cycle at load).
``api.py`` helpers are reached through ``_api`` at call time, as in ``routines_api.py``, so a
``patch("the_one.interfaces.web.api.httpx2")`` still applies.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any, Literal

from fastapi import HTTPException, Request

from the_one.db.models import MCPSource
from the_one.mcp._overrides import configured_names, missing_values
from the_one.mcp.oauth.storage import OAUTH_MANAGED_SECRET_KEYS as _OAUTH_MANAGED_SECRET_KEYS
from the_one.secret_mask import MASKED_API_KEY_SENTINEL as _MASKED_API_KEY_SENTINEL

if TYPE_CHECKING:
    from the_one.db.repositories import MCPSourceRepository


class _ApiModule:
    """Call-time lookup of ``api.py`` names (no import at load: ``api`` imports this module)."""

    def __getattr__(self, name: str) -> Any:
        from the_one.interfaces.web import api

        return getattr(api, name)


_api = _ApiModule()


async def _connect_with_tokens(
    source: MCPSource,
    source_id: str,
    repo: MCPSourceRepository,
    *,
    record_era: bool,
    cache_write: Literal["none", "shared", "shared_no_posture"] = "shared",
) -> dict[str, Any]:
    """Run :func:`_connect_with_tokens_inner` on its OWN task (sortie 22).

    A refused sign-in (``interactive=False``) fails the SDK's transport task group at
    once; ``MCPClient`` then abandons the transport stack, which leaves the cancelled
    anyio scope entered on the task that ran ``connect``. That task would receive a
    ``CancelledError`` at its next ``await``. The pool avoids it by connecting on a
    worker task that simply ends; this does the same, so the route's own task (which
    goes on to clear tokens and run Phase B) is never left inside a cancelled scope.
    Awaiting the task directly keeps cancellation flowing outer -> inner.
    """
    return await asyncio.ensure_future(
        _connect_with_tokens_inner(
            source, source_id, repo, record_era=record_era, cache_write=cache_write
        )
    )


async def _connect_with_tokens_inner(
    source: MCPSource,
    source_id: str,
    repo: MCPSourceRepository,
    *,
    record_era: bool,
    cache_write: Literal["none", "shared", "shared_no_posture"] = "shared",
) -> dict[str, Any]:
    """Phase A of the Library Test, shared with the per-agent test route (sortie 09 DD6).

    Tokens present: build the OAuth provider WITHOUT a consent future (this path
    never kicks a flow) and connect + list_tools with it. MUST thread the provider
    through ``MCPClient`` or the SDK has no way to apply the cached tokens (a bare
    client sends Bearer-less requests and always 401s).

    ``cache_write``: ``"shared"`` and ``"shared_no_posture"`` both write today's
    fields into ``source.config._cache`` (this block never wrote ``auth_posture``);
    ``"none"`` writes nothing. The write is best-effort and happens INSIDE the
    ``async with`` after ``list_tools()`` succeeds, so a failed listing does not
    pollute the cache.

    Returns ``{status: "ok", tools, capabilities}``. Errors are RE-RAISED untouched
    (``MCPAuthRequired``, ``MCPConnectionError``, ``MCPVersionMismatch``) so the
    caller decides: the Library Test clears stale tokens and falls through to
    Phase B; the per-agent route reports them and never touches tokens. The
    imports stay function-local because tests patch ``the_one.mcp.client.MCPClient``.
    """
    from the_one.mcp.client import MCPClient
    from the_one.mcp.oauth import build_oauth_provider_for_source

    provider_a = build_oauth_provider_for_source(
        source,
        repo,
        f"test:{source_id}",
        source_id=source_id,
        tool_call_id=None,
        resource_metadata_url=None,
        consent_url_future=None,  # Phase A doesn't kick a flow
        interactive=False,  # a dead refresh token falls through to Phase B at once
    )
    async with MCPClient(
        source=source,
        auth_provider=provider_a,
        fresh_negotiation=True,
        record_era=record_era,
    ) as client:
        tools = await client.list_tools()
        capabilities = client.server_capabilities  # F8 L1: snapshot inside async-with
        # F4 L2 (M08): server-declared identity + free-form prose, both
        # spec-optional and snapshotted inside the async-with for the
        # same reason as capabilities (post-disconnect reads raise).
        server_info = client.server_info
        instructions = client.instructions
        # F4 L3 (M08): _meta — same snapshot-inside-async-with rule.
        meta = client.meta
        protocol_version = client.negotiated_protocol_version
        # F9 L1 (vibing): persist tools+capabilities to source.config._cache so the
        # editor can render the cached state on mount. Plaintext: tools, capabilities
        # and the timestamp are not secrets. The cache is keyed on the persisted row,
        # not the operator's transient form values.
        tools_cache_payload = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]
        if cache_write != "none":
            try:
                await repo.merge_cache(
                    source_id,
                    {
                        "tools": tools_cache_payload,
                        "capabilities": capabilities,
                        "server_info": server_info,
                        "instructions": instructions,
                        "meta": meta,
                        "protocol_version": protocol_version,
                        "last_updated": time.time(),
                    },
                    delete=("protocol_fallback",),
                )
            except Exception:
                # Best-effort persistence: a write failure must not break the
                # response contract; the cache simply won't populate this round.
                pass
    return {
        "status": "ok",
        "tools": tools_cache_payload,
        "capabilities": capabilities,
    }


async def _test_mcp_connection_inner(
    source_id: str, request: Request
) -> tuple[dict[str, Any], bool]:
    """Connect + list_tools probe; kicks OAuth flow if needed via popup-callback dance.

    Behavior:
      - 404 if source not found
      - {status: "ok", tools: [...]} if connect + list_tools succeed
      - {status: "auth_required", consent_url} if creds absent or
        MCPAuthRequired raised; SDK's auth flow runs as a background
        task waiting for /oauth/callback to deliver the code
      - {status: "error", error} for other failures (transport, version
        mismatch, non-streamable-http source, consent_url_timeout)

    Two-call dance: UI POSTs once; on auth_required opens a popup, waits
    for popup close, re-POSTs. The second POST hits the {status: "ok"}
    path because tokens have landed via the SDK's callback_handler.

    F8 L4 — accepts an optional request body shaped like the PUT payload
    (`{type, config, secrets}`); if present, the operator's in-flight
    form values override the persisted source for the connection test.
    OAuth-managed secret keys (`access_token`, `dcr_credentials`, etc.)
    are ALWAYS sourced from the persisted DB row — only the OAuth flow
    writes them. `source_id` is preserved for OAuth callback routing
    and token persistence regardless of the override.

    F6.5 L3 — see flight artifact Design Decision §2 for the protocol.
    """
    from the_one.interfaces.web import mcp_connection_api as _conn
    from the_one.interfaces.web.app import _inflight_resume_tasks
    from the_one.mcp._pool import _evict_all_for_source
    from the_one.mcp.errors import (
        TOKEN_FAILURE_MARKERS,
        MCPAuthRequired,
        MCPConnectionError,
        MCPCredentialsRejected,
        MCPVersionMismatch,
    )
    from the_one.mcp.oauth import build_oauth_provider_for_source

    repo = await _api._mcp_repo()
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
    persisted_source = source
    # F8 L4: optionally override the persisted source with operator's
    # in-flight form values. Mirrors the PUT endpoint's secrets-resolution
    # logic (per-key __MASKED__ → existing; OAUTH-managed → always
    # preserved from existing). Body is optional — empty body preserves
    # the prior single-arg behavior verbatim.
    try:
        body_bytes = await request.body()
    except Exception:
        body_bytes = b""
    # Only a body-less Test is the saved server under test, so only it is recorded as
    # ``last_check`` (the client sends a body only when its form is dirty). This is NOT
    # ``record_era`` below: a body that changes only secrets still records the era but
    # never ``last_check``. Deliberately different gates; do not unify them.
    recordable = not body_bytes
    if body_bytes:
        try:
            payload = json.loads(body_bytes)
        except Exception as e:
            return {"status": "error", "error": f"invalid JSON body: {e}"}, recordable
        if not isinstance(payload, dict):
            return {"status": "error", "error": "request body must be a JSON object"}, recordable
        override_type = payload.get("type")
        override_config = payload.get("config")
        override_secrets = payload.get("secrets")
        if override_type and override_type != source.type:
            # Test against the operator's in-flight type. Build a
            # transient MCPSource shape; preserve id + name.
            source = MCPSource(
                id=source.id,
                name=source.name,
                type=override_type,
                config=override_config if isinstance(override_config, dict) else {},
                secrets=dict(source.secrets),
                created_at=source.created_at,
                updated_at=source.updated_at,
            )
        elif isinstance(override_config, dict):
            source = source.model_copy(update={"config": override_config})
        if isinstance(override_secrets, dict):
            resolved_secrets: dict[str, Any] = {}
            for k, v in override_secrets.items():
                if v == _MASKED_API_KEY_SENTINEL:
                    if k in source.secrets:
                        resolved_secrets[k] = source.secrets[k]
                else:
                    resolved_secrets[k] = v
            # OAuth-managed keys ALWAYS come from the persisted row.
            for k in _OAUTH_MANAGED_SECRET_KEYS:
                if k in source.secrets:
                    resolved_secrets[k] = source.secrets[k]
                elif k in resolved_secrets:
                    del resolved_secrets[k]
            source = source.model_copy(update={"secrets": resolved_secrets})

    # DD2: the editor sends its form body only when the form is dirty, so "an override was
    # applied" means the server under test differs from the saved row (type or
    # config, ignoring the `_cache`). Secrets are not compared: a changed
    # credential does not change which server is under test. An override Test
    # must not record the era against the saved source id.
    def _config_sans_cache(src: MCPSource) -> dict[str, Any]:
        return {k: v for k, v in (src.config or {}).items() if k != "_cache"}

    override_applied = source.type != persisted_source.type or _config_sans_cache(
        source
    ) != _config_sans_cache(persisted_source)
    record_era = not override_applied

    # F9 L2 D1: dispatch stdio sources to their dedicated transient-client
    # path. Stdio has no OAuth concept (no Phase 0 / Phase A / Phase B), so
    # the workflow is a straight connect → list_tools → cache → return.
    # Other unsupported transports continue to surface a clear error.
    if source.type == "stdio":
        return (
            await _conn._build_and_test_stdio_mcp(source, source_id, repo, record_era=record_era)
        ), recordable
    if source.type != "streamable-http":
        return (
            {
                "status": "error",
                "error": f"Test only supports streamable-http and stdio; got {source.type!r}",
            }
        ), False

    # Phase 0: HTTP-level auth-posture probe (Shape C — A6 resolution).
    # Before engaging the SDK, ask the server itself: "do you require auth?"
    # Persisted result lives at source.config._cache.auth_posture so
    # subsequent calls skip the probe entirely.
    #
    # Skip the probe when live tokens are present — Phase A is the right
    # path for token-bearing OAuth sources (no extra round trip).
    from the_one.mcp.transports.streamable_http import (
        _probe_auth_posture,
        build_request_headers,
    )

    signin_via_discover = False
    # True when Phase B was entered from THIS request's operator-header requests
    # getting 401 (probe verdict "oauth", or DD9's fall-through): the rejection
    # evidence for DD4 path (c). Phase A's stale-token fall-through leaves it False.
    rejection_evidence = False
    cached_posture = (source.config.get("_cache") or {}).get("auth_posture")
    has_live_tokens = bool(
        source.secrets.get("dcr_credentials") and source.secrets.get("access_token")
    )

    # Sortie 09 DD3: a source with a configured-but-blank header ("Set per agent")
    # takes this path BEFORE the cached-posture return and Phase 0's probe. With
    # live sign-in tokens, Phase A runs as today. Without them: the no-auth helper
    # runs without writing `auth_posture`, and only a 401 that names a sign-in
    # (`MCPAuthRequired`) goes on to Phase B -- a bare 401 is a plain
    # "needs a value" error, and no client registration runs.
    missing_entered = False
    if not has_live_tokens and missing_values(source, source):
        missing_result = await _conn._build_and_test_no_auth_mcp(
            source,
            source_id,
            repo,
            record_era=record_era,
            from_fallthrough=True,
            cache_write="shared_no_posture",
            classify=True,
        )
        if missing_result is not _conn._SIGNIN_REQUIRED:
            return missing_result, recordable
        missing_entered = True
        # No `_persist_oauth_posture` here and `rejection_evidence` stays False:
        # the 401 was to a request that lacked the blank header.
        signin_via_discover = True

    if cached_posture == "no_auth" and not has_live_tokens and not missing_entered:
        return (
            await _conn._build_and_test_no_auth_mcp(source, source_id, repo, record_era=record_era)
        ), recordable

    # Re-probe both on a cold cache (None) AND on a cached "oauth" hint when
    # there are no live OAuth tokens. The latter re-validation matters because
    # an operator may have ADDED static-bearer / custom-header auth after an
    # earlier probe cached "oauth" (e.g. a header-auth server first misread as
    # oauth). Re-probing with the operator's headers lets such a source flip to
    # no_auth instead of being permanently pinned to a doomed OAuth flow by the
    # stale cache. A genuine OAuth server simply re-probes to "oauth" again
    # (one cheap round trip on this operator-initiated test path) and falls
    # through to Phase B exactly as before.
    if cached_posture in (None, "oauth") and not has_live_tokens and not missing_entered:
        server_url = source.config.get("url", "")
        # Pass the operator's configured headers (static bearer, custom
        # key/value rows) so a header-auth server probes as no_auth instead
        # of being misclassified as oauth and kicking a doomed DCR flow.
        posture = await _probe_auth_posture(
            server_url, request_headers=build_request_headers(source)
        )
        if posture == "no_auth":
            return (
                await _conn._build_and_test_no_auth_mcp(
                    source, source_id, repo, record_era=record_era
                )
            ), recordable
        if posture == "error":
            return {"status": "error", "error": "connection probe failed"}, recordable
        if posture == "unexpected_status":
            # DD9: the server answered the probe's bare `initialize` with a
            # status that is neither 200 nor 401 (e.g. 400 from a server that
            # speaks only 2026-07-28). Let the negotiating SDK path decide.
            result = await _conn._build_and_test_no_auth_mcp(
                source, source_id, repo, record_era=record_era, from_fallthrough=True
            )
            if result is not _conn._SIGNIN_REQUIRED:
                return result, recordable
            # The SDK path hit a 401: persist `oauth` (as for a probe `oauth`)
            # and sign in. The server already rejects `initialize`, so Phase B
            # triggers sign-in with `server/discover` (DD10 amendment).
            await _conn._persist_oauth_posture(repo, source_id)
            signin_via_discover = True
            rejection_evidence = True
        else:
            # posture == "oauth": persist the hint BEFORE Phase B fires so a
            # Phase B failure still leaves a definitive signal for the pool
            # worker (rather than inferring auth-required from dcr_credentials
            # presence). Then fall through to Phase B below.
            await _conn._persist_oauth_posture(repo, source_id)
            rejection_evidence = True

    # Phase A: tokens present → build provider WITH consent_url_future=None
    # (test path doesn't kick the OAuth flow yet) and try connect + list_tools.
    # MUST thread auth_provider through MCPClient or the SDK has no way to
    # apply the cached tokens — bare MCPClient sends Bearer-less requests
    # and always 401s, defeating the "tokens present" fast path.
    if source.secrets.get("dcr_credentials") and source.secrets.get("access_token"):
        try:
            return (
                await _connect_with_tokens(
                    source, source_id, repo, record_era=record_era, cache_write="shared"
                )
            ), recordable
        except MCPAuthRequired:
            # Token expired/revoked. Bust pool cache BEFORE Phase B builds
            # a fresh provider so the F4 cache doesn't hand out an MCPClient
            # with the stale auth_provider mid-refresh.
            source = await _conn._clear_stale_oauth_secrets(repo, source_id, source)
            await _evict_all_for_source(source_id)
            # fall through to Phase B
        except MCPConnectionError as e:
            # F8 L4 (Anomaly A6): Phase A's connect can hang/time out when
            # refresh_token is no longer accepted by the AS (refresh token
            # rotation, IdP invalidation, server-side revoke). The SDK's
            # auth flow doesn't reliably surface this as MCPAuthRequired —
            # it manifests as an initialize timeout. Treat as "tokens are
            # stale, kick a fresh OAuth flow" by clearing the stored OAuth
            # state and falling through to Phase B.
            #
            # IMPORTANT: only clear tokens when the error message matches
            # the initialize-timeout / cleanup-deadlock signature.
            # MCPConnectionError is also raised for transient network
            # failures (DNS NXDOMAIN, ECONNREFUSED, httpx transport
            # errors) — clearing tokens on those would destroy valid
            # OAuth sessions for an operator on a flaky link.
            err_msg = str(e).lower()
            looks_like_token_failure = any(m in err_msg for m in TOKEN_FAILURE_MARKERS)
            if looks_like_token_failure:
                source = await _conn._clear_stale_oauth_secrets(repo, source_id, source)
                await _evict_all_for_source(source_id)
                # fall through to Phase B
            else:
                return {"status": "error", "error": f"{type(e).__name__}: {e}"}, recordable
        except MCPVersionMismatch as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}, recordable

    # A6 (no-auth MCP detection) is now handled by Phase 0 above (Shape C):
    # bare httpx probe inspects auth posture before SDK engagement, persists
    # the verdict in _cache.auth_posture for subsequent calls. F8 deferred,
    # F9 L1 resolved.

    # Phase B: kick OAuth flow with consent_url_future. Pass
    # allow_dcr_bootstrap=True so the factory constructs a provider even
    # when dcr_credentials is absent — the SDK runs DCR + auth in one
    # round-trip via MCPSourceTokenStorage.get_client_info → None →
    # OAuthClientProvider's discovery + DCR fallback. This is the
    # source-creation-time happy path: operator saves a fresh source,
    # clicks Test, SDK does the registration + consent + token exchange.
    consent_url_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    test_csid = f"test:{source_id}"

    provider = build_oauth_provider_for_source(
        source,
        repo,
        test_csid,
        source_id=source_id,
        tool_call_id=None,
        resource_metadata_url=None,
        consent_url_future=consent_url_future,
        allow_dcr_bootstrap=True,
    )
    if provider is None:
        # With allow_dcr_bootstrap=True, the only way provider is None is
        # chat_session_id is None — but we passed a synthetic test_csid,
        # so this branch is unreachable. Defensive return.
        return {"status": "error", "error": "OAuth provider construction failed"}, recordable

    await _evict_all_for_source(source_id)

    server_url = source.config.get("url", "")

    def _is_credentials_rejection(exc: Exception) -> bool:
        """DD4 path (c): a failed ``/register`` with no discovered OAuth metadata, after
        this request's operator-header requests already got 401."""
        from mcp.client.auth import OAuthClientProvider, OAuthRegistrationError

        if not rejection_evidence or not configured_names(source):
            return False
        if not isinstance(exc, OAuthRegistrationError):
            return False
        if not str(exc).startswith("Registration failed:"):
            return False
        if not isinstance(provider, OAuthClientProvider):
            return False
        ctx = provider.context
        return ctx.protected_resource_metadata is None and ctx.oauth_metadata is None

    async def _drive_flow_test() -> None:
        """Hit the source URL with the provider attached; SDK runs auth flow."""
        # Lazy import; both versions are read at call time (DD10).
        from mcp.types.version import LATEST_MODERN_VERSION

        from the_one import mcp as the_one_mcp

        if signin_via_discover:
            # DD10 amendment: entered from DD9's fall-through, so the server
            # already rejected `initialize` — trigger sign-in with discover.
            version = LATEST_MODERN_VERSION
            body: dict[str, Any] = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "server/discover",
                "params": {},
            }
        else:
            version = the_one_mcp._HANDSHAKE_OFFER_VERSION
            body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": version,
                    "clientInfo": {"name": "the-one", "version": "0.1"},
                    "capabilities": {},
                },
            }
        try:
            async with _api.httpx2.AsyncClient(auth=provider, timeout=30.0) as client:
                await client.post(
                    server_url, json=body, headers=_api._oauth_driver_headers(version)
                )
        except Exception as exc:
            if not consent_url_future.done():
                if _is_credentials_rejection(exc):
                    consent_url_future.set_exception(_conn._CredentialsRejectedSignal())
                else:
                    consent_url_future.set_exception(
                        RuntimeError(f"auth flow failed before consent_url surfaced: {exc}")
                    )

    task = asyncio.create_task(_drive_flow_test())
    _inflight_resume_tasks.add(task)
    task.add_done_callback(_inflight_resume_tasks.discard)

    try:
        consent_url = await asyncio.wait_for(
            asyncio.shield(consent_url_future), timeout=_api._TEST_CONNECT_TIMEOUT
        )
    except asyncio.TimeoutError:
        return {"status": "error", "error": "consent_url_timeout"}, recordable
    except _conn._CredentialsRejectedSignal:
        await _conn._clear_auth_posture(repo, source_id)
        rejected = MCPCredentialsRejected(source_id=source_id, source_name=source.name)
        return {"status": "error", "error": f"MCPCredentialsRejected: {rejected}"}, recordable
    except Exception as e:
        return {"status": "error", "error": f"auth_flow_error: {e}"}, recordable

    return {"status": "auth_required", "consent_url": consent_url}, recordable
