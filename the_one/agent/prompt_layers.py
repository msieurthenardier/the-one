"""Load an agent's prompt layers and compose its system prompt (M27 F1, DD2).

The one async place that reads stored layers (the agent's enabled
rules, and its notes when its notes switch is on) and hands them to the pure
:func:`the_one.agent.config.compose_system_prompt`. Shared by
``AgentFactory.create`` and the ``next_turn`` settle path
(``self_configuration/pending.py``) so no second composition can drift.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from the_one import time_zones
from the_one.agent.config import RenderedNote, compose_system_prompt
from the_one.agent.platform_prompt import Capabilities, render_platform, render_tool_free

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)

# M28 F1 L2 (DD5): cap on the provider's ``supports_tools()`` probe. Read at
# call time so a test can monkeypatch it.
SUPPORTS_TOOLS_TIMEOUT_S = 2.0


async def time_tool_available(registry: Any, llm: Any) -> bool:
    """Whether the date layer should name ``current_time`` (M28 F1, DD5).

    False when the registry is missing/broken or lacks the tool; otherwise the
    provider's ``supports_tools()`` answer, failing CLOSED (False) on timeout or
    any provider error (squawk 0182). This predicate only chooses the prompt's
    WORDING, which must be true under every fallback: if the turn-time probe
    later says the model has no tools, a date line naming ``current_time``
    would be false. The tool stays registered and seeded either way. Never raises.
    """
    try:
        if registry is None:
            return False
        try:
            if time_zones.CURRENT_TIME_TOOL_NAME not in registry.tool_names:
                return False
        except Exception:  # noqa: BLE001 - a broken registry means the tool is absent
            return False
        try:
            return bool(
                await asyncio.wait_for(llm.supports_tools(), timeout=SUPPORTS_TOOLS_TIMEOUT_S)
            )
        except Exception:  # noqa: BLE001 - fail closed (wording), including TimeoutError
            return False
    except Exception:  # noqa: BLE001 - the helper never raises
        return False


@dataclass(frozen=True)
class SystemPrompts:
    """The two system prompts built for one agent at build time.

    ``tool_capable`` is the prompt a tool-capable model gets; ``tool_free`` is the
    same persona, rules, notes and date layers on the tool-free platform prompt, sent
    in its place when the model has no native tool support (``Agent`` swaps it in for
    ``messages[0]`` on the degraded path, with no prefix recovery).
    """

    tool_capable: str
    tool_free: str


async def build_system_prompts(
    agent_name: str,
    persona: str,
    *,
    conn: "aiosqlite.Connection | None" = None,
    tool_available: bool = False,
    now: Any = None,
    knowledge: bool = True,
    time_tool: bool | None = None,
    exec_tools: bool = True,
) -> SystemPrompts:
    """Return both system prompts: platform + persona + rules + notes + date line.

    The date layer (M28 F1, DD4) is last; ``tool_available`` selects whether it
    names ``current_time``. ``knowledge``, ``time_tool`` (default: ``tool_available``)
    and ``exec_tools`` are the capabilities the platform prompt renders from; their
    defaults keep today's text.

    ``conn`` defaults to the process connection. An agent with no stored row
    has no rules and no notes (``notes=None``), so the result is platform +
    persona. Notes load only when the agent's ``notes_enabled`` switch is on
    (M27 F2, DD9); on with none saved yields the empty-notes block.
    """
    from the_one.db.repositories import AgentNoteRepository, AgentRuleRepository

    if conn is None:
        from the_one.db.connection import get_connection

        conn = await get_connection()
    rules = await AgentRuleRepository(conn).list_for_agent(agent_name, enabled_only=True)
    stored = await AgentNoteRepository(conn).list_if_enabled(agent_name)
    notes = (
        None if stored is None else [RenderedNote(n.number, n.text, n.untrusted) for n in stored]
    )
    date_line: str | None = None
    date_line_tool_free: str | None = None
    try:
        eff = await time_zones.load_effective_zone(conn)
        when = now or time_zones.utcnow()
        date_line = time_zones.date_line(when, eff, tool_available=tool_available)
        # The tool-free prompt never names ``current_time`` (it has no tools).
        date_line_tool_free = time_zones.date_line(when, eff, tool_available=False)
    except Exception:  # noqa: BLE001 - omit the layer rather than fail the build
        logger.warning("Could not build the date layer; omitting it", exc_info=True)
    caps = Capabilities(
        tools=True,
        knowledge=knowledge,
        notes=notes is not None,
        rules=bool(rules),
        time_tool=tool_available if time_tool is None else time_tool,
        exec_tools=exec_tools,
    )
    layers = {"rules": [r.text for r in rules], "notes": notes}
    return SystemPrompts(
        tool_capable=compose_system_prompt(
            render_platform(caps), persona, date_line=date_line, **layers
        ),
        tool_free=compose_system_prompt(
            render_tool_free(caps), persona, date_line=date_line_tool_free, tools=False, **layers
        ),
    )


async def build_system_prompt(
    agent_name: str,
    persona: str,
    *,
    conn: "aiosqlite.Connection | None" = None,
    tool_available: bool = False,
    now: Any = None,
    knowledge: bool = True,
    time_tool: bool | None = None,
    exec_tools: bool = True,
) -> str:
    """The tool-capable system prompt (see :func:`build_system_prompts`)."""
    return (
        await build_system_prompts(
            agent_name,
            persona,
            conn=conn,
            tool_available=tool_available,
            now=now,
            knowledge=knowledge,
            time_tool=time_tool,
            exec_tools=exec_tools,
        )
    ).tool_capable
