"""Enable / disable / status / startup-reconcile / rename-cascade /
delete-cascade for the self-configuration surface.

Leg 2, Implementation Guidance #5. Reuses ``MCPSourceRepository`` and
``SQLiteAgentStore`` (with the api-module encryptor, per Leg 1) — this
module never opens its own connection or encryptor; every function takes
its repositories/store as keyword arguments so callers (``api.py``, the
lifespan hook, tests) control construction.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from the_one.agent.config import AgentConfig
from the_one.db.models import MCPSource
from the_one.db.repositories import (
    AgentRevisionRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
)
from the_one.self_configuration import external_credentials
from the_one.self_configuration.constants import (
    CREDENTIAL_SECRET_KEY,
    MOUNT_PATH,
    SURFACE_ROW_NAME,
    SURFACE_TOOL_PREFIX,
    is_surface_row,
)
from the_one.self_configuration.credentials import (
    credential_from_header,
    encode_for_header,
    mint,
    register,
    unregister,
)

logger = logging.getLogger(__name__)

# ``SURFACE_ROW_NAME`` (the one constant name every agent's surface row
# shares, reserved for the platform) lives in ``constants.py`` since sortie 08
# and is re-exported here for the existing ``manage.SURFACE_ROW_NAME`` users.
# An agent's ``mcp_overrides`` can carry no entry under it, and
# ``override_for`` ignores one at every build site.

# Squawk 0004: the predicate moved to ``constants.py`` (a leaf module both
# this module and ``credentials.py`` can import without a cycle) —
# ``is_surface_row`` is imported above rather than redefined here, so
# existing callers/tests referencing ``manage.is_surface_row`` are
# unaffected.


def owner_of(source: MCPSource) -> str | None:
    """The owning agent's name, or ``None`` if *source* is not a surface
    row (or the marker is malformed)."""
    marker = (source.config or {}).get("self_configuration")
    if isinstance(marker, dict):
        agent = marker.get("agent")
        if isinstance(agent, str) and agent:
            return agent
    return None


def surface_url() -> str:
    """LD3: always ``http://127.0.0.1:{settings.port}{MOUNT_PATH}/`` —
    never ``settings.host`` (may be ``0.0.0.0``), and always rebuilt from
    the CURRENT ``settings.port`` at call time, never persisted verbatim
    and trusted later."""
    from the_one.config import settings

    return f"http://127.0.0.1:{settings.port}{MOUNT_PATH}/"


async def find_surface_row(mcp_repo: MCPSourceRepository, agent_name: str) -> MCPSource | None:
    """The agent's surface row, if one exists — regardless of whether it is
    currently attached (``mcp_source_ids``). Linear scan: operator-scale
    source counts, mirroring the now-deleted
    ``SQLiteAgentStore.list_by_connector``'s precedent for "no join table
    needed yet"."""
    for source in await mcp_repo.list():
        if is_surface_row(source) and owner_of(source) == agent_name:
            return source
    return None


async def status(
    agent_name: str,
    *,
    agent_store: SQLiteAgentStore,
    mcp_repo: MCPSourceRepository,
) -> dict[str, Any]:
    """``{"enabled": bool}``, per AC1's exact shape for the common case.
    A row that exists but is no longer attached (legacy data or a crash
    between steps; an agent write can no longer detach it, sortie 08 DD2)
    reports ``enabled: false, orphaned_row: true`` — the next ``enable``
    reuses that row rather than minting a duplicate.
    Unknown agent also reports ``{"enabled": false}`` (the API layer 404s
    separately when the agent itself doesn't exist)."""
    try:
        config = await agent_store.load(agent_name)
    except KeyError:
        return {"enabled": False}
    # M21 F02 L02: surface the operator-owned approval-mode flag in EVERY
    # branch that has a loaded config, so the Studio tab renders the toggle
    # consistently regardless of surface state (the flag is independent of
    # the surface row — it only *bites* once the agent can propose). The
    # unknown-agent branch above has no config, so it omits it.
    requires_approval = config.self_revision_requires_approval
    row = await find_surface_row(mcp_repo, agent_name)
    if row is None:
        return {"enabled": False, "requires_approval": requires_approval}
    if row.id in config.mcp_source_ids:
        return {
            "enabled": True,
            "source_id": row.id,
            "requires_approval": requires_approval,
        }
    return {
        "enabled": False,
        "orphaned_row": True,
        "source_id": row.id,
        "requires_approval": requires_approval,
    }


def _fresh_cache(tools: list[dict[str, Any]]) -> dict[str, Any]:
    """LD6's ``_cache`` write shape — mirrors the ``test/connect`` shape in
    ``interfaces/web/api.py`` (``tools``, ``capabilities``, ``server_info``,
    ``instructions``, ``meta``, ``protocol_version``, ``last_updated``) plus
    ``auth_posture: "no_auth"`` so the pool never attempts DCR on a 401 for
    this source (probe constraint 3)."""
    return {
        "tools": tools,
        "capabilities": {},
        "server_info": None,
        "instructions": None,
        "meta": None,
        "protocol_version": None,
        "last_updated": time.time(),
        "auth_posture": "no_auth",
    }


async def enable(
    agent_name: str,
    *,
    agent_store: SQLiteAgentStore,
    mcp_repo: MCPSourceRepository,
) -> MCPSource:
    """AC2: mint (or reuse) + create/update the surface row + attach +
    register. Idempotent — a second call for an already-enabled agent
    returns the same row with no second credential minted.

    Raises ``KeyError`` if *agent_name* does not exist (caller maps to
    404).
    """
    from the_one.self_configuration import surface

    config = await agent_store.load(agent_name)  # KeyError propagates — 404

    existing_row = await find_surface_row(mcp_repo, agent_name)
    if existing_row is not None and existing_row.id in config.mcp_source_ids:
        # Already enabled — idempotent no-op. Still re-register (cheap,
        # correctness-preserving) in case a prior process crash left the
        # in-memory registry stale relative to this one's fresh start.
        credential = credential_from_header(existing_row.secrets.get(CREDENTIAL_SECRET_KEY))
        if credential is not None:
            register(existing_row.id, credential)
        return existing_row

    if existing_row is not None:
        # Orphaned row (Risk Checks: detached-but-present) — reuse it
        # rather than minting a duplicate credential/row.
        row = existing_row
        credential = credential_from_header(row.secrets.get(CREDENTIAL_SECRET_KEY))
        if credential is None:
            # Defensive: malformed/missing credential on the orphaned row.
            credential = mint()
            new_secrets = dict(row.secrets)
            new_secrets[CREDENTIAL_SECRET_KEY] = encode_for_header(credential)
            row = row.model_copy(update={"secrets": new_secrets})
    else:
        credential = mint()
        row = MCPSource(
            id=uuid.uuid4().hex[:12],
            name=SURFACE_ROW_NAME,
            type="streamable-http",
            config={},
            secrets={CREDENTIAL_SECRET_KEY: encode_for_header(credential)},
        )

    new_config = dict(row.config or {})
    new_config["url"] = surface_url()
    new_config["self_configuration"] = {"agent": agent_name}
    new_config["_cache"] = _fresh_cache(surface.list_surface_tools())
    row = row.model_copy(update={"config": new_config})

    if existing_row is not None:
        await mcp_repo.update(row)
    else:
        await mcp_repo.create(row)

    register(row.id, credential)

    if row.id not in config.mcp_source_ids:
        updated_config = config.model_copy(
            update={"mcp_source_ids": [*config.mcp_source_ids, row.id]}
        )
        await agent_store.save(updated_config)

    return row


async def disable(
    agent_name: str,
    *,
    agent_store: SQLiteAgentStore,
    mcp_repo: MCPSourceRepository,
    revisions_repo: "AgentRevisionRepository | None" = None,
) -> bool:
    """Full disable (AC10's DELETE-on-a-marked-row semantic): evict pool
    entries, drop the id from ``mcp_source_ids``, delete the row, unregister
    the credential. Returns ``True`` if a row was disabled, ``False`` if
    there was nothing to do (idempotent no-op — e.g. double-disable).

    M21 F02 L02 DD8: if ``revisions_repo`` is supplied, mark every
    outstanding ``pending`` revision for this agent ``superseded`` — a
    revision proposed under a since-revoked surface must not be approvable
    afterward. This runs ABOVE the ``row is None`` early-return so a disable
    always clears the queue, even when the surface row is already gone."""
    from the_one.mcp._pool import _evict_all_for_source

    if revisions_repo is not None:
        await revisions_repo.supersede_pending(agent_name)

    row = await find_surface_row(mcp_repo, agent_name)
    if row is None:
        return False

    await _evict_all_for_source(row.id)

    try:
        config = await agent_store.load(agent_name)
    except KeyError:
        config = None
    if config is not None and row.id in config.mcp_source_ids:
        updated_config = config.model_copy(
            update={"mcp_source_ids": [sid for sid in config.mcp_source_ids if sid != row.id]}
        )
        await agent_store.save(updated_config)

    try:
        await mcp_repo.delete(row.id)
    except KeyError:
        pass

    unregister(row.id)
    # M21 F03 L01 (DD9): deleting the surface row cascade-revokes every
    # external credential scoped to it (FK ON DELETE CASCADE removed the
    # store rows); evict their in-memory registry entries too, mirroring the
    # `agt` `unregister(row.id)` above — so an `ext_` token dies with the
    # surface on the next request, no restart.
    evicted = external_credentials.unregister(row.id)
    # Flight 01 Leg 2 (Q2): the row is gone before anything could read its
    # label, so this line carries identifiers (and a count), not labels —
    # the mint line already binds identifier -> label. No line when nothing
    # was evicted (nothing changed, nothing to report).
    if evicted:
        logger.info(
            "external-credential: surface %s for agent %r disabled; "
            "cascade-revoked %d external credential(s): %s",
            row.id,
            agent_name,
            len(evicted),
            evicted,
        )
    return True


async def reconcile_on_startup(
    mcp_repo: MCPSourceRepository,
    agent_store: SQLiteAgentStore,
) -> None:
    """Lifespan startup hook (Implementation Guidance #4/#6), extended by
    LD6/LD7. Runs UNCONDITIONALLY for every marked row on every startup —
    not gated on the URL-staleness check below:

    - Rewrites ``config.url`` from the CURRENT ``settings.port`` (LD3 — a
      port change between runs must not strand a row).
    - Rewrites ``config._cache.tools`` from ``surface.list_surface_tools()``
      (LD6) so a row enabled before a catalog change (e.g. this leg's two
      new write tools) picks them up on the next start.
    - Renames a legacy-template row (``"self-configuration (<agent>)"``,
      Leg 2's template) to the constant :data:`SURFACE_ROW_NAME` (LD7). The
      owner's ``mcp_overrides`` are left alone: a per-agent entry for the
      surface is ignored at build and removed by
      :func:`strip_surface_overrides`.

    Persists a row only when something actually changed. Rebuilds the
    in-memory credential registry from every marked row afterward (Edge
    Case: "registry and DB disagree" recovery).
    """
    from the_one.self_configuration import surface
    from the_one.self_configuration.credentials import load_from_rows

    sources = await mcp_repo.list()
    fresh_url = surface_url()
    fresh_tools = surface.list_surface_tools()
    marked: list[MCPSource] = []
    for source in sources:
        if not is_surface_row(source):
            continue

        changed = False
        new_config = dict(source.config or {})

        if new_config.get("url") != fresh_url:
            new_config["url"] = fresh_url
            changed = True

        cache = dict(new_config.get("_cache") or {})
        if cache.get("tools") != fresh_tools:
            cache["tools"] = fresh_tools
            new_config["_cache"] = cache
            changed = True

        new_name = source.name
        if source.name != SURFACE_ROW_NAME:
            new_name = SURFACE_ROW_NAME
            changed = True

        if changed:
            source = source.model_copy(update={"name": new_name, "config": new_config})
            await mcp_repo.update(source)
        marked.append(source)
    load_from_rows(marked)


async def strip_surface_overrides(agent_store: SQLiteAgentStore) -> None:
    """Sortie 08 DD4/DD7 startup cleanup. For EVERY agent, remove the
    ``mcp_overrides["self-configuration"]`` entry (``None`` when the map
    becomes empty) and every ``mcp__self-configuration__*`` entry from
    ``disabled_tools``: nothing per agent can withhold the surface's tools.

    Scans every agent by name (``manage.disable`` leaves ``mcp_overrides``
    behind, so owners of a marked row are not the only candidates). Saves
    through ``agent_store.save`` only when something changed, with one INFO
    line per changed agent. Each agent is guarded on its own (an undecryptable
    column makes ``load`` raise); never raises. A legacy
    ``"self-configuration (<agent>)"`` key is not touched: it matches no
    source and is already inert.
    """
    try:
        names = await agent_store.list_agents()
    except Exception:
        logger.warning("self-configuration override cleanup could not list agents", exc_info=True)
        return
    for name in names:
        try:
            config = await agent_store.load(name)
            update: dict[str, Any] = {}
            overrides = config.mcp_overrides
            if overrides and SURFACE_ROW_NAME in overrides:
                remaining = {k: v for k, v in overrides.items() if k != SURFACE_ROW_NAME}
                update["mcp_overrides"] = remaining or None
            disabled = config.disabled_tools
            if disabled:
                kept = [
                    t
                    for t in disabled
                    if not (isinstance(t, str) and t.startswith(SURFACE_TOOL_PREFIX))
                ]
                if len(kept) != len(disabled):
                    update["disabled_tools"] = kept
            if not update:
                continue
            await agent_store.save(config.model_copy(update=update))
            logger.info(
                "self-configuration: removed a per-agent withhold of the surface's tools "
                "from agent %r (%s)",
                name,
                ", ".join(sorted(update)),
            )
        except Exception:
            logger.warning(
                "self-configuration override cleanup failed for agent %r; skipped",
                name,
                exc_info=True,
            )


async def cascade_rename(
    old_name: str,
    new_name: str,
    *,
    mcp_repo: MCPSourceRepository,
) -> None:
    """AC11 / LD7: renaming an agent updates its surface row's ownership
    marker only. The row's *name* is the constant :data:`SURFACE_ROW_NAME`
    shared by every agent's surface row, so there is nothing left to
    rename there. No-op if the agent has no surface row. The row's id (and
    therefore the credential registry, which keys on source id) is
    unaffected — no re-registration needed."""
    row = await find_surface_row(mcp_repo, old_name)
    if row is None:
        return
    new_config = dict(row.config or {})
    new_config["self_configuration"] = {"agent": new_name}
    updated = row.model_copy(update={"config": new_config})
    await mcp_repo.update(updated)


async def cascade_delete(
    agent_name: str,
    *,
    mcp_repo: MCPSourceRepository,
) -> None:
    """AC11: deleting an agent removes its surface row and unregisters the
    credential. No-op if the agent has no surface row. Does NOT touch
    ``agent_store`` — the agent row is already gone (or about to be) by the
    time this runs."""
    from the_one.mcp._pool import _evict_all_for_source

    row = await find_surface_row(mcp_repo, agent_name)
    if row is None:
        return
    await _evict_all_for_source(row.id)
    try:
        await mcp_repo.delete(row.id)
    except KeyError:
        pass
    unregister(row.id)
    # M21 F03 L01 (DD9): agent-delete cascade-revokes its external
    # credentials (FK ON DELETE CASCADE removed the store rows); evict the
    # in-memory registry entries too, mirroring the `agt` `unregister` above.
    evicted = external_credentials.unregister(row.id)
    # Flight 01 Leg 2 (Q2): mirrors the `disable` cascade line above, cause
    # "removed with the agent" instead of "disabled".
    if evicted:
        logger.info(
            "external-credential: surface %s for agent %r removed with the agent; "
            "cascade-revoked %d external credential(s): %s",
            row.id,
            agent_name,
            len(evicted),
            evicted,
        )


async def reject_foreign_surface_attachments(
    config: AgentConfig,
    *,
    mcp_repo: MCPSourceRepository,
) -> str | None:
    """LD1's ownership guard: return a human-readable error string if any
    of *config*'s ``mcp_source_ids`` is another agent's surface row, else
    ``None``. Callers (``create_agent`` / ``update_agent``) raise a 422
    with this string.
    """
    for source_id in config.mcp_source_ids:
        try:
            source = await mcp_repo.get(source_id)
        except KeyError:
            continue
        if not is_surface_row(source):
            continue
        owner = owner_of(source)
        if owner != config.name:
            return (
                f"mcp_source_ids references {source_id!r}, which is the "
                f"self-configuration surface for agent {owner!r}, not "
                f"{config.name!r}"
            )
    return None


SURFACE_OVERRIDE_REFUSAL = (
    "The self-configuration server can't be set per agent. "
    "Turn Agent prompt on or off on the Self-configuration tab."
)


async def carry_surface_attachment(
    name: str,
    incoming_ids: list[str],
    stored_ids: list[str],
    *,
    mcp_repo: MCPSourceRepository,
) -> list[str]:
    """Sortie 08 DD2: an agent write never changes the self-configuration
    attachment. Returns *incoming_ids* with the agent's OWN surface row id(s)
    removed, then each one that is attached in *stored_ids* put back at its
    stored position, ``min(stored_index, len(result))``. A create passes
    ``stored_ids=[]``. A foreign agent's surface id is left in place for
    :func:`reject_foreign_surface_attachments` to refuse."""
    own_ids = {s.id for s in await mcp_repo.list() if is_surface_row(s) and owner_of(s) == name}
    if not own_ids:
        return list(incoming_ids)
    result = [i for i in incoming_ids if i not in own_ids]
    for index, stored_id in enumerate(stored_ids):
        if stored_id in own_ids:
            result.insert(min(index, len(result)), stored_id)
    return result
