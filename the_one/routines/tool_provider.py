"""Per-agent routine tool provider (Mission 33 F2 L3, DD1).

Returns the four routine tools only while the agent's Routines item is on
(``config.routines_self_config_enabled``), and never for the ``default`` agent. Sibling
shape to :class:`the_one.notes.tool_provider.NotesToolProvider`. Each call builds fresh
tool instances, sharing nothing mutable.
"""

from __future__ import annotations

from the_one.agent.config import AgentConfig
from the_one.naming import is_reserved_agent_name
from the_one.routines.tools import (
    CancelRoutineTool,
    ChangeRoutineTool,
    ListMyRoutinesTool,
    ScheduleRoutineTool,
    _RoutineToolBase,
)
from the_one.tools.base import Tool


class RoutineToolProvider:
    async def get_tools_for_agent(self, config: AgentConfig, *, agent_name: str) -> list[Tool]:
        if is_reserved_agent_name(agent_name) or not config.routines_self_config_enabled:
            return []
        tools: list[_RoutineToolBase] = [
            ListMyRoutinesTool(agent_name),
            ScheduleRoutineTool(agent_name),
            ChangeRoutineTool(agent_name),
            CancelRoutineTool(agent_name),
        ]
        return list(tools)
