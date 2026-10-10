"""Per-agent notes tool provider (Mission 27 Flight 2, DD3).

Builds the three notes tools when ``config.notes_enabled`` and returns ``[]``
(with no database call) otherwise. Sibling shape to
:class:`the_one.knowledge.tool_provider.KBToolProvider`: not a
``ToolProvider`` Protocol implementer. The three tools share one fallback
write counter (DD5) so ``save_note`` and ``update_note`` cannot get five
writes each when no turn context is set.
"""

from __future__ import annotations

from the_one.agent.config import AgentConfig
from the_one.notes.tools import (
    ForgetNoteTool,
    SaveNoteTool,
    UpdateNoteTool,
    _NotesToolBase,
    _WriteCounter,
)
from the_one.tools.base import Tool


class NotesToolProvider:
    async def get_tools_for_agent(self, config: AgentConfig, *, agent_name: str) -> list[Tool]:
        if not config.notes_enabled:
            return []
        counter = _WriteCounter()
        tools: list[_NotesToolBase] = [
            SaveNoteTool(agent_name, counter),
            UpdateNoteTool(agent_name, counter),
            ForgetNoteTool(agent_name, counter),
        ]
        return list(tools)
