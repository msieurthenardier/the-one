"""The per-agent connection test (sortie 09, DD6).

``POST /api/mcp-sources/{source_id}/test/agent`` connects to an MCP source with an
agent's own credentials (stored, unsaved, or both) and reports the tool list that
agent would see. It is the Library Test's sibling, not a variant of it: it never
runs the auth-posture probe or the sign-in flow, never clears or refreshes tokens,
never evicts a pool connection and never writes ``auth_posture`` or ``last_check``.

The logic lives here and the route in ``api.py`` is a one-line delegate. The
``api.py`` helpers it reuses are reached through a call-time proxy (``api`` imports
the router layer, so a module-top import would be a cycle), the precedent set by
``routines_api.py``.

Security: no credential value appears in a response, an error string or a log line.
Header and environment NAMES do (``needs_values``).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request

from the_one.db.repositories import AgentMcpToolCacheRepository
from the_one.mcp._overrides import (
    MCP_OVERRIDE_CREDENTIAL_KEYS,
    has_credential_override,
    missing_values,
)
from the_one.mcp.override_validation import validate_mcp_overrides
from the_one.self_configuration import manage as self_configuration_manage
from the_one.self_configuration.constants import override_for

logger = logging.getLogger(__name__)


class _ApiModule:
    """Call-time lookup of ``api.py`` names (no import at load: ``api`` imports this module)."""

    def __getattr__(self, name: str) -> Any:
        from the_one.interfaces.web import api

        return getattr(api, name)


_api = _ApiModule()


def _bad_body(field: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=[{"loc": ["body", field], "msg": message, "type": "value_error"}],
    )


def _credentials_of(entry: Any) -> dict[str, Any]:
    """The non-empty credential keys of one override entry (for equality only)."""
    if not isinstance(entry, dict):
        return {}
    return {k: entry[k] for k in MCP_OVERRIDE_CREDENTIAL_KEYS if entry.get(k) not in (None, {}, "")}


def _has_live_tokens(source: Any) -> bool:
    return bool(source.secrets.get("dcr_credentials") and source.secrets.get("access_token"))


async def run_agent_test(source_id: str, request: Request) -> dict[str, Any]:
    """The route body. See the module docstring and the flight's DD6."""
    body = await _api._read_json(request)
    agent_name = body.get("agent")
    overrides = body.get("overrides")
    if agent_name is not None and not (isinstance(agent_name, str) and agent_name.strip()):
        raise _bad_body("agent", "The agent must be a name or null.")
    if overrides is not None and not isinstance(overrides, dict):
        raise _bad_body("overrides", "The overrides must be an object or null.")

    repo = await _api._mcp_repo()
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}") from None
    if self_configuration_manage.is_surface_row(source):
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["source_id"],
                    "msg": "This server is managed by the Self-configuration tab and "
                    "takes no per-agent credentials.",
                    "type": "value_error",
                }
            ],
        )

    stored_entry: dict[str, Any] = {}
    agent_updated_at: str | None = None
    cache_repo = AgentMcpToolCacheRepository(repo.conn)
    if agent_name is not None:
        store = await _api._agent_store()
        try:
            agent = await store.load(agent_name)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Agent not found: {agent_name}") from None
        stored_entry = dict(override_for(agent.mcp_overrides, source) or {})
        # Read before connecting: the per-agent row is written only while the
        # agent's `updated_at` is still this value.
        agent_updated_at = await cache_repo.agent_updated_at(agent_name)

    # Resolve like a build does: stored entry, merged with the body (Studio's mask
    # sentinel keeps a stored value), then the save-time checks on the incoming entry.
    if overrides is None:
        entry = dict(stored_entry)
    else:
        details = validate_mcp_overrides(
            {source.name: overrides}, {source.name: source}, _api._looks_masked
        )
        if details:
            raise HTTPException(status_code=422, detail=details)
        merged = _api._merge_preserved_mcp_credentials(
            {source.name: overrides}, {source.name: stored_entry} if stored_entry else None
        )
        entry = dict((merged or {}).get(source.name) or {})

    from the_one.mcp._tool_provider import _apply_override

    effective = _apply_override(source, entry)

    missing = missing_values(source, effective)
    if missing:
        return {"status": "needs_values", "missing": missing}

    # Persistence mode, decided BEFORE connecting: are the tested credentials the
    # stored ones? (`agent: null` with no credential key in the body counts as yes.)
    if agent_name is None:
        same = overrides is None or not _credentials_of(overrides)
    else:
        same = _credentials_of(entry) == _credentials_of(stored_entry)
    per_agent_write = (
        same
        and agent_name is not None
        and agent_updated_at is not None
        and has_credential_override(stored_entry, source)
    )
    if per_agent_write:
        cache_write = "none"
    elif same and not has_credential_override(stored_entry, source):
        cache_write = "shared_no_posture"
    else:
        cache_write = "none"

    result = await _connect(effective, source_id, repo, cache_write)

    if per_agent_write and result.get("status") == "ok":
        try:
            await cache_repo.put_if_unchanged(
                agent_name,  # type: ignore[arg-type]
                source_id,
                result.get("tools") or [],
                agent_updated_at,
            )
        except Exception:
            logger.warning("could not store the per-agent tool list", exc_info=False)
    return result


async def _connect(effective: Any, source_id: str, repo: Any, cache_write: str) -> dict[str, Any]:
    """Connect with ``effective`` and map every outcome to the Library Test's shapes
    (``ok``, ``auth_required`` without a consent URL, ``error``)."""
    from the_one.mcp.errors import MCPAuthRequired, MCPConnectionError, MCPVersionMismatch

    if effective.type == "stdio":
        return await _api._build_and_test_stdio_mcp(
            effective, source_id, repo, cache_write=cache_write, record_era=False
        )
    if effective.type != "streamable-http":
        return {
            "status": "error",
            "error": f"Test only supports streamable-http and stdio; got {effective.type!r}",
        }
    if _has_live_tokens(effective):
        try:
            return await _api._connect_with_tokens(
                effective, source_id, repo, record_era=False, cache_write=cache_write
            )
        except MCPAuthRequired:
            return {"status": "auth_required"}
        except (MCPConnectionError, MCPVersionMismatch) as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
        except Exception as e:
            return {"status": "error", "error": type(e).__name__}
    result = await _api._build_and_test_no_auth_mcp(
        effective,
        source_id,
        repo,
        record_era=False,
        from_fallthrough=True,
        cache_write=cache_write,
        classify=True,
    )
    if result is _api._SIGNIN_REQUIRED:
        return {"status": "auth_required"}
    return result
