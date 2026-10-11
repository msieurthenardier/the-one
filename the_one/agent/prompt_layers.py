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
from typing import TYPE_CHECKING, Any

from the_one import time_zones
from the_one.agent.config import BASE_PROMPT, RenderedNote, compose_system_prompt

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)

# M28 F1 L2 (DD5): cap on the provider's ``supports_tools()`` probe. Read at
# call time so a test can monkeypatch it.
SUPPORTS_TOOLS_TIMEOUT_S = 2.0


async def time_tool_available(registry: Any, llm: Any) -> bool:
    """Whether the date layer should name ``current_time`` (M28 F1, DD5).

    False when the registry is missing/broken or lacks the tool; otherwise the
    provider's ``supports_tools()`` answer, failing OPEN (True) on timeout or
    any provider error, as the agent loop does. Never raises.
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
        except Exception:  # noqa: BLE001 - fail open, including TimeoutError
            return True
    except Exception:  # noqa: BLE001 - the helper never raises
        return False


async def build_system_prompt(
    agent_name: str,
    persona: str,
    *,
    conn: "aiosqlite.Connection | None" = None,
    tool_available: bool = False,
    now: Any = None,
) -> str:
    """Return base + persona + the agent's enabled rules + its notes + date line.

    The date layer (M28 F1, DD4) is last; ``tool_available`` selects whether it
    names ``current_time``.

    ``conn`` defaults to the process connection. An agent with no stored row
    has no rules and no notes (``notes=None``), so the result is base +
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
    try:
        eff = await time_zones.load_effective_zone(conn)
        date_line = time_zones.date_line(
            now or time_zones.utcnow(), eff, tool_available=tool_available
        )
    except Exception:  # noqa: BLE001 - omit the layer rather than fail the build
        logger.warning("Could not build the date layer; omitting it", exc_info=True)
    return compose_system_prompt(
        BASE_PROMPT,
        persona,
        rules=[r.text for r in rules],
        notes=notes,
        date_line=date_line,
    )
