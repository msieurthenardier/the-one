"""Load an agent's prompt layers and compose its system prompt (M27 F1, DD2).

The one async place that reads stored layers (today: the agent's enabled
rules; Flight 2 adds notes) and hands them to the pure
:func:`the_one.agent.config.compose_system_prompt`. Shared by
``AgentFactory.create`` and the ``next_turn`` settle path
(``self_configuration/pending.py``) so no second composition can drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from the_one.agent.config import BASE_PROMPT, compose_system_prompt

if TYPE_CHECKING:
    import aiosqlite


async def build_system_prompt(
    agent_name: str,
    persona: str,
    *,
    conn: "aiosqlite.Connection | None" = None,
) -> str:
    """Return base + persona + the agent's enabled rules (position order).

    ``conn`` defaults to the process connection. An agent with no stored row
    has no rules, so the result is base + persona.
    """
    from the_one.db.repositories import AgentRuleRepository

    if conn is None:
        from the_one.db.connection import get_connection

        conn = await get_connection()
    rules = await AgentRuleRepository(conn).list_for_agent(agent_name, enabled_only=True)
    return compose_system_prompt(BASE_PROMPT, persona, rules=[r.text for r in rules])
