"""Carry an MCP-server rename into the agents attached to it (sortie 06, DD8).

An agent's per-server settings (``AgentConfig.mcp_overrides``) are keyed by the
source's **name**, and its ``disabled_tools`` entries for the server's tools
start ``mcp__{normalized name}__``. Renaming the source row without moving
those leaves the overrides unreachable and the disabled tools silently
**re-enabled**. :func:`carry_mcp_rename` moves both for every agent whose
``mcp_source_ids`` holds the renamed source.

**Ordering is forced** (same reason as ``knowledge/kb_rename.py``):
``write_transaction`` raises on re-entry by the same task, so the source row
and the agent saves cannot be one atomic unit. The caller
(``interfaces/web/api.py::update_mcp_source``) writes the source row first and
calls this after, so the renamed source already holds the new name when the
"does another attached source still use the old name" checks run.

**Never a raw ``UPDATE``**: ``mcp_overrides`` lives in an encrypted column, so
every change goes through ``SQLiteAgentStore.load``/``save``.

**Names are not unique** (``mcp_sources.name`` has no UNIQUE constraint). When
another source attached to the same agent still carries the old name
(overrides compare raw names) or still normalises to the old prefix, the
override is copied and the disabled-tool entries are added rather than moved,
so that source keeps its settings. An existing ``mcp_overrides[new]`` is never
clobbered. Known limit: ``mcp__foo__`` also prefixes the tools of a source
named ``foo__bar``, so a prefix rewrite can touch those entries.

**Never raises** (as ``rename_kb_tool_references``): the enumeration and each
agent's load/modify/save are wrapped, a failure logs a WARNING naming the
source and the agent, and the rest continue. Acquiring the store is the
caller's job.
"""

from __future__ import annotations

import logging

from the_one.mcp._tool import _normalize_source_name

logger = logging.getLogger(__name__)


async def carry_mcp_rename_into_secrets(
    old_name: str,
    new_name: str,
    *,
    secret_repo,  # SecretRepository — untyped to avoid a repositories<->mcp cycle
    mcp_repo,  # MCPSourceRepository
) -> None:
    """Move ``mcp__{old}__`` entries of every secret's ``allowed_tools`` to the new
    prefix (sortie 10, DD3), so a secret keeps working after its server is renamed.

    Global, not agent-scoped: secrets are attached to no agent, and MCP names are not
    unique, so a no-op when another source still normalises to the old name. The
    renamed row is already saved under its new name. One write transaction; never
    raises (a failure logs a WARNING naming the two names).
    """
    try:
        old_norm = _normalize_source_name(old_name)
        new_norm = _normalize_source_name(new_name)
        if old_norm == new_norm:
            return
        for source in await mcp_repo.list():
            if _normalize_source_name(source.name) == old_norm:
                return
        await secret_repo.rewrite_tool_prefix(f"mcp__{old_norm}__", f"mcp__{new_norm}__")
    except Exception:
        logger.warning(
            "MCP server rename %r -> %r: failed to carry the rename into secrets' "
            "allowed tools; they may still list the old name",
            old_name,
            new_name,
            exc_info=True,
        )


async def carry_mcp_rename(
    source_id: str,
    old_name: str,
    new_name: str,
    *,
    agent_store,  # SQLiteAgentStore — untyped to avoid a repositories<->mcp cycle
    mcp_repo,  # MCPSourceRepository
) -> list[str]:
    """Move ``mcp_overrides[old_name]`` and the ``mcp__{old}__`` disabled-tool
    entries to the new name for every agent attached to ``source_id``.

    An agent with nothing to change is not saved. Returns the names of agents
    whose carry failed (an enumeration failure returns an empty list; check the
    WARNING).
    """
    if old_name == new_name:
        return []
    try:
        agent_names = await agent_store.list_by_mcp_source(source_id)
    except Exception:
        logger.warning(
            "MCP source %r rename %r -> %r: failed to enumerate attached agents; "
            "the source has already been renamed, but no agent could be examined, "
            "so overrides and disabled_tools may still reference the old name",
            source_id,
            old_name,
            new_name,
            exc_info=True,
        )
        return []
    old_prefix = f"mcp__{_normalize_source_name(old_name)}__"
    new_prefix = f"mcp__{_normalize_source_name(new_name)}__"
    failed: list[str] = []
    for agent_name in agent_names:
        try:
            cfg = await agent_store.load(agent_name)
            others = []
            for other_id in dict.fromkeys(cfg.mcp_source_ids):
                if other_id == source_id:
                    continue
                try:
                    others.append(await mcp_repo.get(other_id))
                except KeyError:
                    continue
            changed = False

            overrides = cfg.mcp_overrides
            if overrides and old_name in overrides:
                if new_name in overrides:
                    logger.info(
                        "MCP source %r rename: agent %r already has an override "
                        "entry for %r; leaving %r in place",
                        source_id,
                        agent_name,
                        new_name,
                        old_name,
                    )
                else:
                    moved = dict(overrides)
                    if any(o.name == old_name for o in others):
                        moved[new_name] = moved[old_name]
                    else:
                        moved[new_name] = moved.pop(old_name)
                    cfg.mcp_overrides = moved
                    changed = True

            if old_prefix != new_prefix and any(
                e.startswith(old_prefix) for e in cfg.disabled_tools
            ):
                keep_old = any(
                    _normalize_source_name(o.name) == _normalize_source_name(old_name)
                    for o in others
                )
                rewritten: list[str] = []
                for entry in cfg.disabled_tools:
                    if entry.startswith(old_prefix):
                        if keep_old:
                            rewritten.append(entry)
                        rewritten.append(new_prefix + entry[len(old_prefix) :])
                    else:
                        rewritten.append(entry)
                cfg.disabled_tools = list(dict.fromkeys(rewritten))
                changed = True

            if changed:
                await agent_store.save(cfg)
        except Exception:
            logger.warning(
                "MCP source %r rename %r -> %r: failed to carry the rename into "
                "agent %r; its overrides and disabled_tools may still reference "
                "the old name",
                source_id,
                old_name,
                new_name,
                agent_name,
                exc_info=True,
            )
            failed.append(agent_name)
    return failed
