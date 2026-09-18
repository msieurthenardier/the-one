"""Rewrite ``disabled_tools`` entries across attached agents on a
knowledge-base rename (Mission 24, Flight 6, Leg 2; DD-5, L2-D7).

A knowledge base's derived search-tool name is a function of
``(kb.name, kb.id)`` (``the_one/knowledge/tool_provider.py::compute_tool_names``,
DD-17) — so renaming a knowledge base moves the name a ``disabled_tools``
entry has to match exactly, or that entry goes stale and the tool silently
**re-enables**. This module holds the one remaining rewrite this leg makes
safe: it performs L2-D7's step 3 (the per-agent rewrite) once the caller has
already computed both derived names and written the knowledge-base row.

**Ordering is forced, not a style choice** (L2-D7): ``write_transaction``
raises on re-entry by the same task, so the knowledge-base update and the
agent saves cannot be one atomic unit. The caller (``interfaces/web/api.py::
update_knowledge_base``) computes both derived names in memory, writes the
knowledge-base row, and only then calls :func:`rename_kb_tool_references`
here — never the reverse.

**Never a raw ``UPDATE``** (L2-D8): :meth:`SQLiteAgentStore.load` /
:meth:`~the_one.db.repositories.SQLiteAgentStore.save` round-trip
``mcp_overrides`` through the encryptor; a targeted ``UPDATE agents SET
disabled_tools = ?`` would bypass it entirely. Go through the store.

**``enabled_tools`` is never touched** (AC-9): ``kb__`` is in
``UNGATED_TOOL_PREFIXES`` (``the_one/agent/config.py``), so
``is_tool_enabled`` never consults ``enabled_tools`` for a ``kb__`` name —
an entry there is inert, and the v7 schema-migration precedent that rewrites
both columns does not transfer.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def rename_kb_tool_references(
    store,  # SQLiteAgentStore — untyped here to avoid a repositories<->knowledge cycle
    kb_id: str,
    old_tool_name: str,
    new_tool_name: str,
) -> list[str]:
    """Rewrite the ``disabled_tools`` entry equal to ``old_tool_name`` into
    ``new_tool_name``, for every agent :meth:`SQLiteAgentStore.list_by_kb`
    reports attached to ``kb_id`` (L2-D7 step 3).

    An agent with no ``disabled_tools`` entry equal to ``old_tool_name`` is
    left alone and is **not** re-saved (AC-8) — this is the normal, expected
    case for most attached agents and is not a failure.

    An agent whose ``disabled_tools`` holds ``old_tool_name`` **more than
    once** (possible via the API) has every occurrence replaced, with
    duplicates collapsed rather than leaving a stale second copy (Edge
    Case).

    **Each agent's load + replace + save is individually wrapped** in
    ``try/except Exception`` (AC-12): a failure — an encryptor round-trip
    error, a constraint, anything — logs a WARNING naming the agent and the
    exception, and rewriting continues to the next agent. Nothing
    propagates out of this function; the knowledge-base row has already
    been renamed by the time this runs, so an unhandled exception here
    would surface as an unhandled 500 *after* the rename already
    committed. This fails open: an agent whose rewrite fails keeps the old,
    now-stale ``disabled_tools`` entry, which is a stated limitation (each
    such agent is named in the WARNING so the condition is diagnosable),
    not an oversight.

    Returns the names of agents whose rewrite failed.
    """
    agent_names = await store.list_by_kb(kb_id)
    failed: list[str] = []
    for agent_name in agent_names:
        try:
            cfg = await store.load(agent_name)
            if old_tool_name not in cfg.disabled_tools:
                continue
            rewritten: list[str] = []
            seen: set[str] = set()
            for entry in cfg.disabled_tools:
                new_entry = new_tool_name if entry == old_tool_name else entry
                if new_entry in seen:
                    continue
                seen.add(new_entry)
                rewritten.append(new_entry)
            cfg.disabled_tools = rewritten
            await store.save(cfg)
        except Exception:
            logger.warning(
                "knowledge base %r rename: failed to rewrite disabled_tools "
                "entry %r -> %r for agent %r; it may still reference the "
                "old tool name",
                kb_id,
                old_tool_name,
                new_tool_name,
                agent_name,
                exc_info=True,
            )
            failed.append(agent_name)
    return failed
