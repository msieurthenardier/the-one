"""Load an agent's prompt layers and compose its system prompt (M27 F1, DD2).

The one async place that reads stored layers (the agent's enabled
rules, and its notes when its notes switch is on) and hands them to the pure
:func:`the_one.agent.config.compose_system_prompt`. Shared by
``AgentFactory.create`` and the ``next_turn`` settle path
(``self_configuration/pending.py``) so no second composition can drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from the_one.agent.config import BASE_PROMPT, RenderedNote, compose_system_prompt

if TYPE_CHECKING:
    import aiosqlite


async def build_system_prompt(
    agent_name: str,
    persona: str,
    *,
    conn: "aiosqlite.Connection | None" = None,
) -> str:
    """Return base + persona + the agent's enabled rules + its notes.

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
    return compose_system_prompt(BASE_PROMPT, persona, rules=[r.text for r in rules], notes=notes)
