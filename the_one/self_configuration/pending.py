"""In-process registry for deferred ``next_turn`` self-revisions (LD1-LD3).

The write tool runs inside the loopback request's own task, so the
contextvars the web layer sets around ``agent.step`` (``current_chat_
session_id`` / ``current_tool_call_id``) are not visible to it, and the
``Agent`` object has no name of its own. A ``next_turn`` revision is
therefore recorded here, KEYED BY AGENT NAME, and consumed (awaited) by the two
non-paused turn-settle sites in ``the_one/interfaces/web/app.py``
(``_process_and_broadcast``'s ``if not paused:`` block and
``_resume_paused_session``'s ``if not re_paused:`` block) via
:func:`apply_pending_revision`.

The tool has ALREADY persisted the revision to the stored row (LD2) before
it ever reaches this module — this registry only carries the IN-MEMORY
deferral for the currently-open conversation. If the entry is never
consumed (no live session, or a rebuild discarded it — LD3), nothing is
lost: the stored row is the source of truth and a rebuilt agent always
reads it fresh.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from the_one.agent.config import compose_system_prompt
from the_one.agent.platform_prompt import (
    capabilities_from_registry,
    render_platform,
    render_tool_free,
)
from the_one.agent.prompt_layers import (
    SystemPrompts,
    build_system_prompts,
    load_secrets_block,
    time_tool_available,
)
from the_one.llm.base import Message
from the_one.notes.tools import SAVE_NOTE_TOOL_NAME

if TYPE_CHECKING:
    from the_one.agent.core import Agent

logger = logging.getLogger(__name__)

# agent_name -> {"system_prompt": ..., "description": ...} — only the
# revised fields are present; `record()` MERGES into any existing entry so
# two different-field revisions in the same turn both apply at the same
# settle (leg Edge Cases).
_pending: dict[str, dict[str, str]] = {}

# agent_name -> count of next_turn revisions recorded this process (LD5:
# "the leg does not rate-limit revisions... this leg records the count...
# so a loop is at least visible").
_revision_counts: dict[str, int] = {}


def record(
    agent_name: str,
    *,
    system_prompt: str | None = None,
    description: str | None = None,
) -> None:
    """Record a ``next_turn`` revision for *agent_name*, merging into any
    existing pending entry (two different-field revisions in one turn both
    apply at the same settle; two same-field revisions — the second
    overwrites the first, both already persisted in order by the caller).
    """
    entry = _pending.setdefault(agent_name, {})
    fields: list[str] = []
    if system_prompt is not None:
        entry["system_prompt"] = system_prompt
        fields.append("system_prompt")
    if description is not None:
        entry["description"] = description
        fields.append("description")

    _revision_counts[agent_name] = _revision_counts.get(agent_name, 0) + 1
    logger.info(
        "self-configuration: agent %r recorded a next_turn revision to %s "
        "(revision #%d for this agent this process)",
        agent_name,
        fields,
        _revision_counts[agent_name],
    )


def _has_tool(registry: object, name: str) -> bool:
    try:
        return name in registry.tool_names  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - a missing/broken registry has no tools
        return False


async def apply_pending_revision(agent_name: str, agent: "Agent") -> bool:
    """Pop and apply the pending entry for *agent_name* onto the LIVE
    *agent* object, if one exists.

    Async since M27 F1: a ``system_prompt`` entry is recomposed as base +
    persona + the agent's enabled rules (one indexed read).

    Mutates ``agent.system_prompt`` and replaces ``agent.messages[0]``
    (always the system message — see ``Agent.__init__``/``reset``) with a
    fresh ``Message.system(...)``; never touches the rest of ``agent.
    messages`` (no history wipe). ``description`` is store-only — nothing
    in the live conversation reflects it, so there is nothing to mutate for
    that field here.

    Returns ``True`` iff an entry existed and was applied (a second call
    for the same agent with no new revision is a no-op returning
    ``False`` — the entry is consumed by the first settle to reach it).
    """
    entry = _pending.pop(agent_name, None)
    if entry is None:
        return False

    system_prompt = entry.get("system_prompt")
    if system_prompt is not None:
        # M27 F1 (DD2): the entry carries only the raw persona; recompose
        # base + persona + enabled rules so the base prompt is never lost
        # (Known Issue 2). A failed rules read must not break the turn that
        # is about to send ``done``: fall back to base + persona.
        try:
            tool_available = await time_tool_available(
                getattr(agent, "tools", None), getattr(agent, "llm", None)
            )
        except Exception:  # noqa: BLE001 - must never break the turn
            tool_available = False
        registry = getattr(agent, "tools", None)
        caps = capabilities_from_registry(
            registry,
            notes=_has_tool(registry, SAVE_NOTE_TOOL_NAME),
            rules=True,
            time_tool=tool_available,
        )
        try:
            prompts = await build_system_prompts(
                agent_name,
                system_prompt,
                tool_available=tool_available,
                knowledge=caps.knowledge,
                time_tool=caps.time_tool,
                exec_tools=caps.exec_tools,
            )
        except Exception:
            logger.warning(
                "self-configuration: could not load rules for agent %r at settle; "
                "applying platform prompt + persona without rules",
                agent_name,
                exc_info=True,
            )
            # Sortie 10 DD8: try to keep the secrets layer; never raise from here.
            try:
                from the_one.db.connection import get_connection

                secrets_block = await load_secrets_block(await get_connection(), agent_name)
            except Exception:  # noqa: BLE001 - the fallback must never raise
                secrets_block = ""
            prompts = SystemPrompts(
                tool_capable=compose_system_prompt(
                    render_platform(caps), system_prompt, secrets=secrets_block
                ),
                tool_free=compose_system_prompt(render_tool_free(caps), system_prompt, tools=False),
            )
        composed = prompts.tool_capable
        agent.degraded_system_prompt = prompts.tool_free
        agent.system_prompt = composed
        agent.messages[0] = Message.system(composed)
        logger.info(
            "self-configuration: applied pending system_prompt revision for agent %r",
            agent_name,
        )
    if entry.get("description") is not None:
        logger.info(
            "self-configuration: consumed pending description revision for agent %r "
            "(store-only, nothing to apply to the live conversation)",
            agent_name,
        )
    return True


def clear_for_test() -> None:
    """Wipe both the pending registry and the revision counters. Test-only
    seam — mirrors ``the_one.self_configuration.credentials.clear_for_test``'s
    naming convention."""
    _pending.clear()
    _revision_counts.clear()


__all__ = ["record", "apply_pending_revision", "clear_for_test"]
