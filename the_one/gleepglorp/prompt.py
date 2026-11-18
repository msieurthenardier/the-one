"""GleepGlorp's system prompt (M36 F1 L03; L06 notes layer; L08 the text): the prompt, its
notes and the date line.

GleepGlorp does not go through ``build_system_prompts``'
platform layer, so no platform text, rules, persona or secrets reach it. Its notes layer
(its own table, behind the ``memory`` setting) sits after the prompt text and before the
date line.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from the_one import time_zones
from the_one.agent.prompt_layers import SystemPrompts

logger = logging.getLogger(__name__)

# Version 1 (M36 F1 L08), one short constant per section so Leg 9's evals can tune one at a
# time. The must-keep sections (scope, limits, secrets) are never trimmed for size.
IDENTITY = (
    "You are GleepGlorp, the assistant built into this app. "
    "You help the operator set up and use it."
)

SCOPE = (
    "You only help with this app. If asked about anything else, decline in one sentence "
    "and suggest one of the operator's own agents."
)

LIMITS = (
    "You cannot change anything. The operator makes every change in the app. "
    "Never say or imply that you changed something. Never promise an ability you do not have."
)

SECRETS = (
    "Never ask for, repeat or write a secret. If the operator pastes something that looks "
    "like a key, do not repeat it; say it belongs in Library > Secrets, or in the model "
    "provider's own key field."
)

ANSWERING_TOOLS = (
    "To explain how something works, call get_app_guide first. To see what is configured, "
    "call read_app_config. Use the web only for facts outside the app. If you are unsure, say so."
)

ANSWERING_TOOL_FREE = "Answer from what you know of the app. If you are unsure, say so."

LINKS = (
    "Link to a page as [text](#route), and only with these routes:\n"
    "- [Library](#library)\n"
    "- [Add a model provider](#library/providers/~new)\n"
    "- [Add an MCP server](#library/mcp/~new)\n"
    "- [Add a knowledge base](#library/knowledge/~new)\n"
    "- [Add a connector](#library/connectors/~new)\n"
    "- [Add a secret](#library/secrets/~new)\n"
    "- [New agent](#agents/~new)\n"
    "- [Built-in tools](#settings/tools)\n"
    "- [GleepGlorp settings](#settings/gleepglorp)"
)

STYLE = "Reply briefly, in Markdown."


def base_prompt(*, tools: bool = True) -> str:
    """The prompt's own text (no notes, no date line): the sections joined by blank lines."""
    answering = ANSWERING_TOOLS if tools else ANSWERING_TOOL_FREE
    return "\n\n".join([IDENTITY, SCOPE, LIMITS, SECRETS, answering, LINKS, STYLE])


def compose(
    *, notes_block: str | None = None, date_line: str | None = None, base: str | None = None
) -> str:
    """The prompt text: the base, then the notes layer, then the date line."""
    parts = [base_prompt() if base is None else base]
    if notes_block:
        parts.append(notes_block)
    if date_line:
        parts.append(date_line)
    return "\n\n".join(parts)


def notes_blocks(notes: Sequence[Any] | None) -> tuple[str | None, str | None]:
    """``(tool-capable block, tool-free block)``; both ``None`` when memory is off."""
    if notes is None:
        return None, None
    from the_one.db._notes import render_notes_block
    from the_one.gleepglorp.notes import (
        GLEEPGLORP_NOTES_HEADING,
        GLEEPGLORP_NOTES_HEADING_TOOL_FREE,
    )

    return (
        render_notes_block(notes, tools=True, heading=GLEEPGLORP_NOTES_HEADING),
        render_notes_block(notes, tools=False, heading=GLEEPGLORP_NOTES_HEADING_TOOL_FREE),
    )


async def build_prompts(conn, *, tool_available: bool, now=None) -> SystemPrompts:
    from the_one.gleepglorp.notes import GleepGlorpNoteRepository

    notes = await GleepGlorpNoteRepository(conn).list_if_enabled()
    block, block_tool_free = notes_blocks(notes)
    date_line: str | None = None
    date_line_tool_free: str | None = None
    try:
        eff = await time_zones.load_effective_zone(conn)
        when = now or time_zones.utcnow()
        date_line = time_zones.date_line(when, eff, tool_available=tool_available)
        date_line_tool_free = time_zones.date_line(when, eff, tool_available=False)
    except Exception:  # noqa: BLE001 - omit the layer rather than fail the build
        logger.warning("Could not build the date layer; omitting it", exc_info=True)

    return SystemPrompts(
        tool_capable=compose(notes_block=block, date_line=date_line),
        tool_free=compose(
            notes_block=block_tool_free,
            date_line=date_line_tool_free,
            base=base_prompt(tools=False),
        ),
    )
