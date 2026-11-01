"""The agent-facing notes tools and the untrusted-content scan
(Mission 27 Flight 2, DD3/DD5/DD6/DD7/DD8).

Three tools write an agent's saved notes. Every write records where it came
from (DD7) and whether content not from the operator was in the conversation
the model had seen (DD6). The scan reads the owning ``Agent``'s own message
list, so ``the_one/agent/core.py`` stays untouched.

Refusals RAISE (never return a string): the loop's generic handler turns the
exception into ``ToolResult(is_error=True)`` carrying the exact text, so the
tool stream shows an error, not a success.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from the_one.agent._context import current_chat_session_id, current_tool_call_id, current_turn
from the_one.agent.taint import (  # noqa: F401  (re-exports: the canonical home is taint.py)
    TRUSTED_TOOL_NAMES,
    UNKNOWN_CONTEXT,
    UNKNOWN_POSITION,
    UNKNOWN_TOOL,
    _add_source,
    compute_taint,
)
from the_one.agent.tool_names import (  # noqa: F401  (re-exports: the canonical home)
    FORGET_NOTE_TOOL_NAME,
    NOTES_TOOL_NAMES,
    SAVE_NOTE_TOOL_NAME,
    UPDATE_NOTE_TOOL_NAME,
)
from the_one.db._notes import (
    NOTE_WRITES_PER_TURN,
    NoteDuplicateError,
    NoteLimitError,
    NotesDisabledError,
)
from the_one.tools.base import Tool

if TYPE_CHECKING:
    from the_one.agent._context import TurnContext
    from the_one.agent.core import Agent

logger = logging.getLogger(__name__)

BUDGET_REFUSAL = f"Note limit for this turn reached ({NOTE_WRITES_PER_TURN} writes)."


class _WriteCounter:
    """Fallback write budget shared by one Agent's three notes tools, used
    only when no :class:`TurnContext` is set (DD5)."""

    def __init__(self) -> None:
        self.writes = 0


class _NotesToolBase(Tool):
    parameters: dict[str, Any]

    def __init__(self, agent_name: str | None, counter: _WriteCounter | None = None) -> None:
        super().__init__(agent_name=agent_name)
        self._agent: Agent | None = None
        self._counter = counter if counter is not None else _WriteCounter()

    def bind_agent(self, agent: Agent) -> None:
        """Bind the owning Agent (called by the factory after construction).
        An unbound tool fails closed: every write is flagged "unknown position"."""
        self._agent = agent

    # -- budget -----------------------------------------------------------

    def _writes(self) -> int:
        turn = current_turn.get()
        return turn.writes if turn is not None else self._counter.writes

    def _check_budget(self) -> None:
        if self._writes() >= NOTE_WRITES_PER_TURN:
            raise ValueError(BUDGET_REFUSAL)

    def _count_write(self) -> None:
        turn = current_turn.get()
        if turn is not None:
            turn.writes += 1  # mutate, never set (DD5)
        else:
            self._counter.writes += 1

    # -- helpers ----------------------------------------------------------

    def _name(self) -> str:
        if not self._agent_name:
            raise ValueError("Notes are unavailable: this tool is not attached to an agent.")
        return self._agent_name

    @staticmethod
    def _coerce_number(value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("number must be an integer.")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
        raise ValueError("number must be an integer.")

    @staticmethod
    def _coerce_text(value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("text must be a string.")
        return value

    @staticmethod
    async def _repo():
        from the_one.db.connection import get_connection
        from the_one.db.repositories import AgentNoteRepository

        return AgentNoteRepository(await get_connection())


async def _origin(turn: TurnContext | None) -> dict[str, Any]:
    """DD7: the origin columns for a new note."""
    session_id = (turn.session_id if turn is not None else None) or current_chat_session_id.get()
    peer = turn.peer if turn is not None else None
    if peer is not None:
        kind = "connector"
    elif session_id:
        kind = "web"
    else:
        kind = "other"
    label: str | None = None
    if session_id:
        try:
            from the_one.db.connection import get_connection

            conn = await get_connection()
            async with conn.execute(
                "SELECT title FROM chat_sessions WHERE id = ?", (session_id,)
            ) as cur:
                row = await cur.fetchone()
            label = row[0] if row and row[0] else None
        except Exception:
            logger.debug("notes: could not read the origin session title", exc_info=True)
    return {
        "origin_kind": kind,
        "origin_session_id": session_id,
        "origin_label": label,
        "origin_platform": peer.platform if peer is not None else None,
        "origin_peer_id": peer.peer_id if peer is not None else None,
        "origin_peer_name": peer.peer_name if peer is not None else None,
    }


class SaveNoteTool(_NotesToolBase):
    name = SAVE_NOTE_TOOL_NAME
    description = (
        "Save a note for later conversations: something the person told you about their "
        "life (a preference, plan or circumstance), worded as they told it. Never save "
        "passwords, keys or other secrets."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "The note, one short line."}},
        "required": ["text"],
    }

    async def execute(self, text: str) -> str:
        name = self._name()
        text = self._coerce_text(text)
        self._check_budget()
        turn = current_turn.get()
        untrusted, sources = compute_taint(self._agent, current_tool_call_id.get(), turn)
        origin = await _origin(turn)
        repo = await self._repo()
        try:
            note, created = await repo.create(
                name, text, untrusted=untrusted, sources=sources, **origin
            )
        except (NotesDisabledError, NoteLimitError) as e:
            raise ValueError(e.detail) from None
        if not created:
            return f"Already saved as note [{note.number}]."
        self._count_write()
        return f"Saved note [{note.number}]."


class UpdateNoteTool(_NotesToolBase):
    name = UPDATE_NOTE_TOOL_NAME
    description = "Replace a saved note's text, by its number."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "number": {"type": "integer", "description": "The note's number."},
            "text": {"type": "string", "description": "The new text, one short line."},
        },
        "required": ["number", "text"],
    }

    async def execute(self, number: Any, text: str) -> str:
        name = self._name()
        num = self._coerce_number(number)
        text = self._coerce_text(text)
        self._check_budget()
        untrusted, sources = compute_taint(
            self._agent, current_tool_call_id.get(), current_turn.get()
        )
        repo = await self._repo()
        try:
            note, changed = await repo.update_by_agent(
                name, num, text, untrusted=untrusted, sources=sources
            )
        except KeyError:
            raise ValueError(f"No note [{num}].") from None
        except (NotesDisabledError, NoteLimitError, NoteDuplicateError) as e:
            raise ValueError(e.detail) from None
        if not changed:
            return f"Note [{note.number}] is unchanged."
        self._count_write()
        return f"Updated note [{note.number}]."


class ForgetNoteTool(_NotesToolBase):
    name = FORGET_NOTE_TOOL_NAME
    description = "Delete a saved note, by its number."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"number": {"type": "integer", "description": "The note's number."}},
        "required": ["number"],
    }

    async def execute(self, number: Any) -> str:
        name = self._name()
        num = self._coerce_number(number)
        repo = await self._repo()
        try:
            note = await repo.forget_by_agent(name, num)
        except KeyError:
            raise ValueError(f"No note [{num}].") from None
        except NotesDisabledError as e:
            raise ValueError(e.detail) from None
        return f"Forgot note [{note.number}]."
