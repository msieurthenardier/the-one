"""MCP connection routes and the connection builders, split out of ``api.py`` (Mission 37 F2 L1).

The router has no prefix; ``api.py`` attaches it to ``api.router`` (prefix ``/api``) at the
bottom of that module. Handlers reach ``api.py`` helpers through ``_api`` at call time, so
tests that patch ``the_one.interfaces.web.api.get_connection`` or ``.httpx2`` and friends still
apply. The two large connection-check functions (``_connect_with_tokens`` and
``_test_mcp_connection_inner``) live in ``mcp_connection_flow.py``, which reaches the builders
below through this module at call time.

The names tests and ``mcp_agent_test.py`` reach here by identity or patch: ``_SIGNIN_REQUIRED``
(defined once), ``_build_and_test_no_auth_mcp``, ``_build_and_test_stdio_mcp``,
``_persist_oauth_posture`` and ``_clear_auth_posture``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, HTTPException, Request

from the_one.db.models import MCPSource
from the_one.interfaces.web.mcp_connection_flow import _test_mcp_connection_inner
from the_one.mcp._era import forget_era
from the_one.mcp.oauth.storage import OAUTH_MANAGED_SECRET_KEYS as _OAUTH_MANAGED_SECRET_KEYS

if TYPE_CHECKING:
    from the_one.db.repositories import MCPSourceRepository


class _ApiModule:
    """Call-time lookup of ``api.py`` names (no import at load: ``api`` imports this module)."""

    def __getattr__(self, name: str) -> Any:
        from the_one.interfaces.web import api

        return getattr(api, name)


_api = _ApiModule()

router = APIRouter()


@router.delete("/mcp-sources/{source_id}/connection")
async def reset_mcp_connection(source_id: str) -> dict[str, str]:
    """Clear OAuth tokens + tools cache for a streamable-http MCP source.

    F9 L1 (vibing) — operator-facing affordance for "this connection is
    in a weird state, start over from a fresh login". Strips every key
    in ``OAUTH_MANAGED_SECRET_KEYS`` from ``source.secrets`` (access_token,
    refresh_token, token_expires_at, token_type, scope, dcr_credentials),
    drops ``source.config["_cache"]`` if present, evicts the F4 pool so
    the next acquire reconstructs a fresh client, and persists the result.
    Returns ``{"status": "ok"}`` on success.

    On the next /test/connect, since both ``access_token`` and
    ``dcr_credentials`` are gone, the endpoint skips Phase A and runs
    Phase B's full DCR + consent + token-exchange flow — a fresh
    OAuth session, not a silent token rotation.

    Idempotent: calling on a source that already lacks OAuth state and
    cache is a no-op (zero keys to strip; ``repo.update`` writes the
    unchanged shape; eviction is idempotent on no-match).

    Out-of-scope: stdio sources have no OAuth state; calling on a stdio
    source is harmless (zero keys match). The editor's Forget tools list button
    uses this route for a local-command source with a stored tools list (the
    cache, per-agent tool lists and remembered protocol are dropped).
    """
    from the_one.mcp._pool import _evict_all_for_source

    repo = await _api._mcp_repo()
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")

    new_secrets = {k: v for k, v in source.secrets.items() if k not in _OAUTH_MANAGED_SECRET_KEYS}
    new_config = dict(source.config or {})
    new_config.pop("_cache", None)
    updated_source = source.model_copy(update={"secrets": new_secrets, "config": new_config})
    await _evict_all_for_source(source_id)
    await repo.update(updated_source)
    await _api._drop_source_agent_tool_cache(repo, source_id)
    forget_era(source_id)
    return {"status": "ok"}


# Returned by ``_build_and_test_no_auth_mcp`` (only when ``from_fallthrough``) when
# the negotiating SDK path hit a 401: the route then continues into Phase B.
_SIGNIN_REQUIRED: Any = object()


async def _persist_oauth_posture(repo: MCPSourceRepository, source_id: str) -> None:
    """Persist ``_cache.auth_posture = "oauth"`` (best-effort).

    Shared by Phase 0's probe-``oauth`` branch and DD9's fall-through when the
    SDK path hits a 401, so a Phase B failure still leaves a definitive signal
    for the pool worker.
    """
    try:
        await repo.merge_cache(source_id, {"auth_posture": "oauth"})
    except Exception:
        # Best-effort; falling through to Phase B regardless.
        pass


async def _clear_auth_posture(repo: MCPSourceRepository, source_id: str) -> None:
    """Remove ``_cache.auth_posture`` (best-effort).

    Used when Phase B proves a rejected key and no request ever succeeded: the app
    does not know what the server is, so the next Test classifies it fresh.
    """
    try:
        await repo.merge_cache(source_id, {}, delete=("auth_posture",))
    except Exception:
        pass


class _CredentialsRejectedSignal(Exception):  # noqa: N818
    """Private sentinel set on Phase B's ``consent_url_future`` when its failed ``/register``
    plus the absence of any discovered OAuth metadata proves the server rejected the operator's
    headers and offers no sign-in (DD4 path (c))."""


async def _build_and_test_no_auth_mcp(
    source: MCPSource,
    source_id: str,
    repo: MCPSourceRepository,
    *,
    record_era: bool = True,
    from_fallthrough: bool = False,
    cache_write: Literal["none", "shared", "shared_no_posture"] = "shared",
    classify: bool = False,
) -> dict[str, Any]:
    """Connect + list_tools against a no-auth streamable-http MCP source.

    F9 L1 Shape C helper: extracted so both Phase 0 success branches
    (probe-verdict no_auth AND cached-hint no_auth) share one code path.
    Mirrors the Phase A success branch's persistence shape — tools +
    capabilities + last_updated + auth_posture all land in
    ``source.config._cache``.

    NEVER engages Phase B from this helper: a no_auth verdict is
    definitive; if MCPClient still raises (transport down, capability
    missing, version mismatch), surface the error inline.

    Args:
        source: The (possibly body-overridden) MCPSource to test.
        source_id: The persisted source id used for cache writebacks.
        repo: The repo for cache persistence.
        record_era: False when the Test used a body override (DD2): the
            server under test is not the saved one, so its era is not
            remembered.
        from_fallthrough: True only when entered from the DD9 fall-through
            (probe verdict ``unexpected_status``). A 401 then returns the
            ``_SIGNIN_REQUIRED`` sentinel instead of the race-branch error.
        cache_write: Sortie 09 DD6. ``"shared"`` (default) writes the shared
            ``_cache`` fields including ``auth_posture: "no_auth"``;
            ``"shared_no_posture"`` writes the same fields without
            ``auth_posture``; ``"none"`` writes nothing.
        classify: Sortie 09 DD3. With ``from_fallthrough`` also true, only an
            ``MCPAuthRequired`` returns ``_SIGNIN_REQUIRED``; an
            ``MCPCredentialsRejected`` (a bare 401 to configured headers) is the
            normal error dict. False keeps the fold of both into the sentinel.

    Returns:
        ``{status: "ok", tools, capabilities}`` on success, or
        ``{status: "error", error}`` on any failure.
    """
    from the_one.mcp.client import MCPClient
    from the_one.mcp.errors import (
        MCPAuthRequired,
        MCPCapabilityMissing,
        MCPConnectionError,
        MCPCredentialsRejected,
        MCPVersionMismatch,
    )

    try:
        async with MCPClient(
            source=source, auth_provider=None, fresh_negotiation=True, record_era=record_era
        ) as client:
            tools = await client.list_tools()
            capabilities = client.server_capabilities
            # F4 L2 (M08): capture spec-optional serverInfo + instructions
            # alongside tools/capabilities so the Tools tab can render a
            # server-declared subtitle line + hover-tooltip without re-probing.
            server_info = client.server_info
            instructions = client.instructions
            # F4 L3 (M08): also capture _meta — arbitrary server-supplied
            # metadata, persisted alongside the other initialize() fields.
            meta = client.meta
            protocol_version = client.negotiated_protocol_version
            tools_cache_payload = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]
            if cache_write != "none":
                cache_fields: dict[str, Any] = {
                    "tools": tools_cache_payload,
                    "capabilities": capabilities,
                    "server_info": server_info,
                    "instructions": instructions,
                    "meta": meta,
                    "protocol_version": protocol_version,
                    "last_updated": time.time(),
                }
                if cache_write == "shared":
                    cache_fields["auth_posture"] = "no_auth"
                try:
                    await repo.merge_cache(source_id, cache_fields, delete=("protocol_fallback",))
                except Exception:
                    # Best-effort persistence — a write failure must not break the
                    # response contract (mirrors the Phase A persistence pattern).
                    pass
        return {
            "status": "ok",
            "tools": tools_cache_payload,
            "capabilities": capabilities,
        }
    except (MCPAuthRequired, MCPCredentialsRejected) as e:
        if from_fallthrough and not (classify and isinstance(e, MCPCredentialsRejected)):
            # A bare 401 from a server that may still be OAuth-only (2026-07-28 with no
            # metadata): Phase B decides with its own discovery evidence.
            return _SIGNIN_REQUIRED
        if isinstance(e, MCPCredentialsRejected):
            # Path (a): cached no_auth, key now rejected. Posture stays no_auth.
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
        # Defensive: probe said no_auth but server now wants auth (race).
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    except (MCPConnectionError, MCPVersionMismatch, MCPCapabilityMissing) as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    except Exception as e:
        # F9 L2 vibing: defense-in-depth catch-all. Any exception escaping the
        # typed catches above (e.g. asyncio.CancelledError leaking from
        # MCPClient cleanup, or any other unexpected runtime error) is
        # converted to a 200-response error envelope rather than allowed to
        # escape the route as a 500 with HTML body. The frontend's resp.ok
        # check is a parallel guard; this ensures the JSON contract holds.
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def _protocol_fallback_of(client: Any) -> str | None:
    """``"no_answer"`` only when the client reports exactly that (sortie 19, DD4).

    Fakes with no such attribute, and mocks that return a mock, give ``None``.
    """
    value = getattr(client, "negotiation_fallback", None)
    return value if isinstance(value, str) and value == "no_answer" else None


async def _build_and_test_stdio_mcp(
    source: MCPSource,
    source_id: str,
    repo: MCPSourceRepository,
    *,
    record_era: bool = True,
    cache_write: Literal["none", "shared", "shared_no_posture"] = "shared",
) -> dict[str, Any]:
    """Connect + list_tools against a stdio MCP source.

    ``cache_write`` (sortie 09 DD6): ``"none"`` writes no cache field; both
    ``"shared"`` and ``"shared_no_posture"`` write today's fields (stdio never
    writes ``auth_posture``).

    F9 L2 D1 sibling of ``_build_and_test_no_auth_mcp``: stdio has no
    OAuth concept (no Phase 0 / Phase A / Phase B), so the Test path is
    structurally a single transient-client lifecycle. Mirrors the
    no-auth-http helper's persistence shape for tools + capabilities +
    last_updated. Does NOT write ``auth_posture`` — that field is an
    HTTP-path concept (Shape C) that does not generalize to stdio (no
    HTTP probe surface; "no auth" is the only stdio mode).

    The transient client teardown path runs through the F4/F6.6
    lifecycle that has been verified clean post-F6.6 cleanup-deadlock
    fix; caplog is expected to be free of ``MCPClient.disconnect``
    warnings across this path.

    Args:
        source: The (possibly body-overridden) MCPSource to test.
        source_id: The persisted source id used for cache writebacks.
        repo: The repo for cache persistence.

    Returns:
        ``{status: "ok", tools, capabilities}`` on success, or
        ``{status: "error", error}`` on any failure.
    """
    from the_one.mcp.client import MCPClient
    from the_one.mcp.errors import (
        MCPAuthRequired,
        MCPCapabilityMissing,
        MCPConnectionError,
        MCPVersionMismatch,
    )
    from the_one.platform.sandbox.errors import SandboxError

    try:
        async with MCPClient(
            source=source, auth_provider=None, fresh_negotiation=True, record_era=record_era
        ) as client:
            tools = await client.list_tools()
            capabilities = client.server_capabilities
            # F4 L2 (M08): capture spec-optional serverInfo + instructions
            # alongside tools/capabilities — see _build_and_test_no_auth_mcp.
            server_info = client.server_info
            instructions = client.instructions
            # F4 L3 (M08): _meta — see _build_and_test_no_auth_mcp.
            meta = client.meta
            protocol_version = client.negotiated_protocol_version
            protocol_fallback = _protocol_fallback_of(client)
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
                    fields: dict[str, Any] = {
                        "tools": tools_cache_payload,
                        "capabilities": capabilities,
                        "server_info": server_info,
                        "instructions": instructions,
                        "meta": meta,
                        "protocol_version": protocol_version,
                        "last_updated": time.time(),
                    }
                    if protocol_fallback is not None:
                        fields["protocol_fallback"] = protocol_fallback
                        await repo.merge_cache(source_id, fields)
                    else:
                        await repo.merge_cache(source_id, fields, delete=("protocol_fallback",))
                except Exception:
                    # Best-effort persistence — a write failure must not break the
                    # response contract (mirrors the http no-auth helper).
                    pass
        return {
            "status": "ok",
            "tools": tools_cache_payload,
            "capabilities": capabilities,
        }
    except MCPAuthRequired as e:
        # Defensive: stdio shouldn't surface auth-required, but if a server
        # somehow does, surface it as a regular error rather than crashing.
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    except (MCPConnectionError, MCPVersionMismatch, MCPCapabilityMissing, SandboxError) as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    except Exception as e:
        # F9 L2 vibing: defense-in-depth catch-all. Stdio teardown can leak
        # asyncio.CancelledError from MCPClient._safe_cleanup under certain
        # failure modes (Architect is fixing that root cause separately).
        # Until then — and as a permanent guard against any other unexpected
        # runtime error — convert escaping exceptions into a 200-response
        # error envelope so the route's JSON contract holds and the frontend
        # can render a useful message instead of choking on an HTML 500.
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


async def _clear_stale_oauth_secrets(
    repo: MCPSourceRepository, source_id: str, source: MCPSource
) -> MCPSource:
    """Strip the four OAuth-managed secrets (stale tokens) before a fresh sign-in.

    Re-reads the STORED row, strips only those keys and writes that row back, so
    a request-body override (which may carry the operator's unsaved URL or
    headers) is never persisted. Returns ``source`` (the possibly-overridden
    in-memory shape Phase B needs, e.g. its ``config["url"]``) with the same keys
    stripped from its secrets. The in-memory strip happens even if the re-read or
    the write raises (a source deleted mid-Test raises ``KeyError``).
    """
    stripped_source = source.model_copy(
        update={
            "secrets": {
                k: v for k, v in source.secrets.items() if k not in _OAUTH_MANAGED_SECRET_KEYS
            }
        }
    )
    try:
        persisted = await repo.get(source_id)
        await repo.update(
            persisted.model_copy(
                update={
                    "secrets": {
                        k: v
                        for k, v in persisted.secrets.items()
                        if k not in _OAUTH_MANAGED_SECRET_KEYS
                    }
                }
            )
        )
    except Exception:
        pass
    return stripped_source


@router.post("/mcp-sources/{source_id}/test/agent")
async def test_mcp_connection_as_agent(source_id: str, request: Request) -> dict[str, Any]:
    """Sortie 09 DD6: connect with an agent's own credentials; see
    ``interfaces/web/mcp_agent_test.py``."""
    from the_one.interfaces.web.mcp_agent_test import run_agent_test

    return await run_agent_test(source_id, request)


@router.post("/mcp-sources/{source_id}/test/connect")
async def test_mcp_connection(source_id: str, request: Request) -> dict[str, Any]:
    """Run a connection check and record its outcome (``_cache.last_check``).

    The one write point for the record: the inner function returns
    ``(result, recordable)``, ``recordable`` being true only for a body-less Test of
    the saved server that was an actual connection check. See
    :func:`_test_mcp_connection_inner` for the check itself.
    """
    result, recordable = await _test_mcp_connection_inner(source_id, request)
    if recordable and result.get("status") in _RECORDED_CHECK_STATUSES:
        try:
            repo = await _api._mcp_repo()
            await repo.merge_cache(
                source_id,
                {"last_check": {"status": result["status"], "at": time.time()}},
            )
        except Exception:
            # Best-effort, like every other cache write: the response contract wins.
            _api.logger.debug("could not record last_check for %s", source_id, exc_info=True)
    return result


_RECORDED_CHECK_STATUSES = frozenset({"ok", "error", "auth_required"})
