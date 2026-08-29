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

# LD7 (leg 03) / Anomaly A11 / flight-log Decision D6: every agent's surface
# row shares this ONE constant name (`mcp_sources.name` carries no UNIQUE
# constraint — ownership is the marker, overrides are keyed per agent), so
# the prefixed tool-name budget is fixed and known: `mcp__self-
# configuration__{tool}` is 45-49 chars for the surface's four tools, well
# under the 64-char ceiling `mcp/_tool.py` enforces, regardless of agent
# name length. Was `SURFACE_ROW_NAME_TEMPLATE = "self-configuration
# ({name})"`, which left as little as ~11 chars of agent name before a
# tool silently dropped off the catalog (Anomaly A11). The literal name is
# RESERVED — `api.py`'s `create_mcp_source`/`update_mcp_source` 409 a
# non-surface source with this exact name (AC8b) — because override
# application is keyed by source *name* (`_tool_provider.py`, mirrored in
# `mcps-tab.js`), so a same-named ordinary source on the same agent would
# collide with the platform-managed surface row.
SURFACE_ROW_NAME = "self-configuration"

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
    source counts, mirrors ``SQLiteAgentStore.list_by_connector``'s
    precedent for "no join table needed yet"."""
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
    A row that exists but is no longer attached (a legitimate operator
    detach via ``PUT /api/agents/{name}`` dropping the id from
    ``mcp_source_ids``) reports ``enabled: false, orphaned_row: true`` —
    the next ``enable`` reuses that row rather than minting a duplicate.
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
      new write tools) picks them up on the next start, and the operator's
      per-tool checkboxes on the MCPs tab show them.
    - Renames a legacy-template row (``"self-configuration (<agent>)"``,
      Leg 2's template) to the constant :data:`SURFACE_ROW_NAME` (LD7), and
      migrates the owner's ``mcp_overrides[old_name]`` entry to the new key
      so per-tool checkboxes set under Leg 2 survive — skipped (and
      logged) if the constant key already exists on that agent, rather
      than clobbering it.

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
            old_name = source.name
            new_name = SURFACE_ROW_NAME
            changed = True
            agent_name = owner_of(source)
            if agent_name is not None:
                await _migrate_override_key(agent_name, old_name, new_name, agent_store=agent_store)

        if changed:
            source = source.model_copy(update={"name": new_name, "config": new_config})
            await mcp_repo.update(source)
        marked.append(source)
    load_from_rows(marked)


async def _migrate_override_key(
    agent_name: str,
    old_name: str,
    new_name: str,
    *,
    agent_store: SQLiteAgentStore,
) -> None:
    """LD7: move ``config.mcp_overrides[old_name]`` to ``[new_name]`` for
    *agent_name*, so an operator's per-tool checkboxes set under the old
    row name survive the rename. Skips (and logs) if *new_name* already has
    an entry — never clobbers a live override."""
    try:
        config = await agent_store.load(agent_name)
    except KeyError:
        return
    overrides = config.mcp_overrides
    if not overrides or old_name not in overrides:
        return
    if new_name in overrides:
        logger.info(
            "self-configuration: reconcile skipped mcp_overrides migration for "
            "agent %r — %r already has an override entry; leaving %r in place",
            agent_name,
            new_name,
            old_name,
        )
        return
    new_overrides = dict(overrides)
    new_overrides[new_name] = new_overrides.pop(old_name)
    await agent_store.save(config.model_copy(update={"mcp_overrides": new_overrides}))
    logger.info(
        "self-configuration: reconcile migrated mcp_overrides[%r] to [%r] for agent %r",
        old_name,
        new_name,
        agent_name,
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


async def reject_surface_credential_overrides(
    config: AgentConfig,
    *,
    mcp_repo: MCPSourceRepository,
) -> str | None:
    """Leg Edge Case guard: an agent's ``mcp_overrides`` entry targeting its
    OWN (or any) self-configuration surface row must not carry a credential
    key (``MCP_OVERRIDE_CREDENTIAL_KEYS`` — ``env``/``headers``/
    ``bearer_token``). The overlay would replace the platform-minted
    credential on the wire, which the gate would then 401 on — reject at
    the API boundary (422) rather than let it fail silently at connect
    time.
    """
    if not config.mcp_overrides:
        return None
    # Function-local import: `mcp/_overrides.py` transitively imports
    # `the_one.tools.resolver` — kept out of this leaf-ish module's
    # top-level import surface per the codebase's function-local-import
    # convention for imports only a single guard needs.
    from the_one.mcp._overrides import MCP_OVERRIDE_CREDENTIAL_KEYS

    sources_by_name = {s.name: s for s in await mcp_repo.list()}
    for source_name, entry in config.mcp_overrides.items():
        source = sources_by_name.get(source_name)
        if source is None or not is_surface_row(source):
            continue
        if not isinstance(entry, dict):
            continue
        offending = sorted(k for k in MCP_OVERRIDE_CREDENTIAL_KEYS if entry.get(k))
        if offending:
            return (
                f"mcp_overrides[{source_name!r}] sets {offending}, but "
                f"{source_name!r} is a self-configuration surface row — its "
                "credential is minted by the platform and cannot be "
                "overridden via mcp_overrides"
            )
    return None
