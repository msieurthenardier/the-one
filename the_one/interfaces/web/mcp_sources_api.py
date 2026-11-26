"""MCP source CRUD routes, split out of ``api.py`` (Mission 37 F2 L1).

The router has no prefix; ``api.py`` attaches it to ``api.router`` (prefix ``/api``) at the
bottom of that module. Handlers reach ``api.py`` helpers through ``_api`` at call time, so
tests that patch ``the_one.interfaces.web.api.get_connection`` and friends still apply.
``/mcp-sources/types`` is declared before ``/mcp-sources/{source_id}``: routes match in
declaration order.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request

from the_one.mcp import service as mcp_service
from the_one.mcp._era import forget_era
from the_one.mcp.oauth.storage import OAUTH_MANAGED_SECRET_KEYS as _OAUTH_MANAGED_SECRET_KEYS
from the_one.self_configuration import manage as self_configuration_manage

if TYPE_CHECKING:
    from the_one.db.models import MCPSource


class _ApiModule:
    """Call-time lookup of ``api.py`` names (no import at load: ``api`` imports this module)."""

    def __getattr__(self, name: str) -> Any:
        from the_one.interfaces.web import api

        return getattr(api, name)


_api = _ApiModule()

router = APIRouter()


def _mcp_source_response(source: MCPSource) -> dict[str, Any]:
    """Render an MCPSource into the masked HTTP response shape.

    Mirrors ``_provider_response`` — the response contains masked
    secret values per ``_mask_secrets``; ``config`` is passed through
    unchanged (operator-marked-non-sensitive).

    INVARIANT: ``model_dump()`` populates ``data["secrets"]`` with the
    decrypted plaintext dict; we OVERWRITE that key with the masked
    form before returning. Any future refactor that removes the
    overwrite would leak plaintext via the API. The
    ``test_list_returns_masked_secrets`` assertion
    ``"ghp_realsecretvalue" not in resp.text`` is the regression net.

    OAuth-managed keys (F5 §5) are STRIPPED from the visible payload
    BEFORE masking — the four token/credential keys must not surface
    via the API at all (not even as masked values). The unmodified
    source dict remains in memory; only the response payload is
    stripped. Tests:
    ``tests/test_oauth_secrets_api.py::test_get_strips_managed_keys``.
    """
    data = source.model_dump()
    visible = {k: v for k, v in source.secrets.items() if k not in _OAUTH_MANAGED_SECRET_KEYS}
    data["secrets"] = _api._mask_secrets(visible)
    # F9 L1 (vibing): expose a presence-only flag so the editor can decide
    # whether to render the "Reset connection" Danger-Zone button without
    # leaking the OAuth-managed secret values themselves. True iff ANY
    # OAuth-managed key is present in the persisted row's secrets.
    data["oauth_active"] = any(k in source.secrets for k in _OAUTH_MANAGED_SECRET_KEYS)
    # F4 L3 (M08 popup-loop fix): expose access_token presence specifically.
    # The Studio MCP-test post-OAuth race needs this — `oauth_active` flips
    # when `dcr_credentials` writes, which precedes token exchange. The
    # frontend polls this flag to know when tokens are actually persisted
    # before firing the Phase 2 re-POST. Presence-only (boolean), never the
    # value; mirrors the `oauth_active` exposure pattern.
    data["has_access_token"] = "access_token" in source.secrets
    return data


@router.get("/mcp-sources")
async def list_mcp_sources(include_agent_surfaces: str | None = None) -> list[dict[str, Any]]:
    """DD3: per-agent self-configuration surface rows are hidden from the
    admin MCP Sources listing by default — the operator manages them from
    the owning agent's own tabs, not this screen. The agent editor's fetch
    passes ``?include_agent_surfaces=1`` so its Tools tab (and the
    self-configuration tab) can still see them. The filter is a
    request-level switch, not a repository change (DD3's constraint: both
    screens call this same endpoint today).
    """
    repo = await _api._mcp_repo()
    sources = await repo.list()
    if include_agent_surfaces != "1":
        sources = [s for s in sources if not self_configuration_manage.is_surface_row(s)]
    return [_mcp_source_response(s) for s in sources]


@router.get("/mcp-sources/types")
async def list_mcp_source_types() -> list[dict[str, str]]:
    """Return the list of MCP source transport types selectable in the UI.

    NOTE: This route MUST be registered BEFORE ``/mcp-sources/{source_id}``
    because FastAPI matches routes in registration order. If reordered, a
    GET to ``/mcp-sources/types`` would resolve to ``get_mcp_source`` with
    ``source_id="types"`` and 404. Mirrors the provider precedent at
    ``list_provider_types``.
    """
    return [
        {"value": "stdio", "label": "Local program (stdio)"},
        {"value": "streamable-http", "label": "Remote server (HTTP)"},
    ]


@router.get("/mcp-sources/{source_id}")
async def get_mcp_source(source_id: str) -> dict[str, Any]:
    repo = await _api._mcp_repo()
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
    return _mcp_source_response(source)


@router.post("/mcp-sources", status_code=201)
async def create_mcp_source(request: Request) -> dict[str, Any]:
    data = await _api._read_json(request)
    with _api._mcp_write_errors():
        source = await mcp_service.create_mcp_source(await _api._mcp_write_deps(), data)
    return _mcp_source_response(source)


@router.put("/mcp-sources/{source_id}")
async def update_mcp_source(source_id: str, request: Request) -> dict[str, Any]:
    data = await _api._read_json(request)
    with _api._mcp_write_errors():
        updated = await mcp_service.replace_mcp_source(
            await _api._mcp_write_deps(), source_id, data
        )
    return _mcp_source_response(updated)


@router.delete("/mcp-sources/{source_id}")
async def delete_mcp_source(source_id: str) -> dict[str, str]:
    """Delete an MCP source and reclaim its lazy-install runtime cache.

    F9 L2 vibing follow-up: stdio sources whose ``config.command`` is a
    lazy-install runtime (``uvx``, ``npx``, ``pipx run``) leave behind a
    package cache under ``/root/.cache/uv/environments-v2`` or
    ``/root/.npm/_npx`` after first spawn. Without cleanup, deleting the
    source orphans that cache indefinitely. This handler:

    1. Reads the source so we can decode its (runtime, package) BEFORE
       the row is gone.
    2. Evicts every pool entry referencing the source so the next
       ``acquire`` doesn't hand out a stale client.
    3. Refcounts: if any OTHER source decodes to the same (runtime,
       package), we skip cleanup — the survivor still needs the cache.
    4. DELETEs the row.
    5. Best-effort cache cleanup AFTER the delete commits, so a hung
       ``uv cache clean`` cannot regress the user-facing delete signal.
       :func:`cleanup_runtime_cache` swallows all exceptions and bounds
       itself with an internal ``asyncio.wait_for(10.0)`` ceiling.

    Sources whose runtime is unknown (python/node/bash/Custom) skip
    cleanup entirely — there is no reliably-locatable cache slot to
    reclaim for those.
    """
    from the_one.mcp._pool import _evict_all_for_source
    from the_one.mcp.cache_cleanup import cleanup_runtime_cache, extract_runtime_package

    repo = await _api._mcp_repo()

    # Step 1: Read the source first so we can decode the runtime+package
    # BEFORE the row is gone. A 404 on read short-circuits with the
    # existing semantics — no eviction, no cleanup.
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")

    # DD3 / AC10: DELETE on a marked (self-configuration) row performs the
    # FULL disable (detach from the owner's mcp_source_ids, unregister the
    # credential, evict the pool) rather than the ordinary lazy-install
    # cache-cleanup path below, which knows nothing about the ownership
    # marker or the credential registry.
    if self_configuration_manage.is_surface_row(source):
        agent_name = self_configuration_manage.owner_of(source)
        if agent_name is not None:
            agent_store = await _api._agent_store()
            # M21 F02 L02 DD8: deleting the surface row directly is also a
            # surface-disable — supersede the agent's outstanding pending
            # revisions here too (same concern as the DELETE
            # /self-configuration endpoint).
            revisions_repo = await _api._agent_revisions_repo()
            await self_configuration_manage.disable(
                agent_name,
                agent_store=agent_store,
                mcp_repo=repo,
                revisions_repo=revisions_repo,
            )
        else:
            # Malformed marker (no agent name) — fall back to a bare
            # evict + delete so the row doesn't become permanently stuck.
            # M21 F03 L01 (Edge Case): this bare path skips
            # `manage.disable`'s external-registry eviction. Harmless today
            # — minting an external credential requires a non-`None` owner
            # (`_enabled_surface_id_or_409` → `status()` → `owner_of`), so no
            # external credential can exist for an owner-less row, and the FK
            # cascade cleans the store rows regardless. If mint's gate ever
            # changes to admit an owner-less surface, add
            # `external_credentials.unregister(source_id)` here.
            from the_one.mcp._pool import _evict_all_for_source

            await _evict_all_for_source(source_id)
            with contextlib.suppress(KeyError):
                await repo.delete(source_id)
        forget_era(source_id)
        return {"status": "ok"}

    cfg = source.config or {}
    command = cfg.get("command", "") if isinstance(cfg.get("command", ""), str) else ""
    args = cfg.get("args", []) or []
    runtime, package = (None, None)
    if isinstance(args, list):
        runtime, package = extract_runtime_package(command, args)

    # Step 2: Evict pool entries for this source.
    await _evict_all_for_source(source_id)

    # Step 3: Refcount cleanup — query before delete so the to-be-deleted
    # row is excluded by id.
    skip_reason: str | None = None
    if runtime and package:
        siblings = await repo.find_by_runtime_package(runtime, package, source_id)
        if siblings:
            sibling_ids = ", ".join(s.id for s in siblings)
            skip_reason = (
                f"cache for ({runtime}, {package}) still referenced by "
                f"source(s) {sibling_ids}; skipped"
            )

    # Step 4: DB delete (existing semantics).
    try:
        await repo.delete(source_id)
    except KeyError:
        # Race: someone deleted the row between our get() and delete().
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
    forget_era(source_id)

    # Step 5: Best-effort cleanup post-delete. The helper has its own
    # 10s ceiling and swallows every exception — this await cannot
    # raise.
    #
    # Logs use WARNING (not INFO) so cleanup outcomes surface under
    # uvicorn's default root-logger threshold without operators
    # lowering the bar globally. WARNING is semantically loose here
    # ("operation succeeded normally") but it's the simplest visibility
    # fix; the alternative is structured response fields, which the
    # architect ruled out (silent UX).
    if not (runtime and package):
        # Unsupported runtime — nothing to reclaim.
        _api.logger.warning(
            "delete_mcp_source(%s): no cleanup applicable for command %r",
            source_id,
            command,
        )
    elif skip_reason:
        # Refcount survivor — log and skip. The shared cache stays put
        # for the surviving source.
        _api.logger.warning("delete_mcp_source(%s): %s", source_id, skip_reason)
    else:
        await cleanup_runtime_cache(runtime, package)

    return {"status": "ok"}
