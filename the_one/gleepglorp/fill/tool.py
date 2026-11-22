"""``fill_form``: GleepGlorp's fill tool (Mission 36 F3 L5, DD6).

It records a fill in ``gleepglorp_fills`` and sends it to the operator's screen, where the
drawer that sent the turn writes the values into the agent editor as *unsaved edits*. It
changes nothing in the app's configuration. It works only in a turn sent from the drawer (the
turn carries a page); anywhere else GleepGlorp proposes instead. The result is shipped text,
so the tool is in ``TRUSTED_TOOL_NAMES``; the fill carries the same taint flag a proposal does.
"""

from __future__ import annotations

import logging
from typing import Any

from the_one.agent._context import current_chat_session_id, current_tool_call_id, current_turn
from the_one.agent.taint import compute_taint
from the_one.gleepglorp import kinds, outside
from the_one.gleepglorp.fill.events import push_fill_changed, push_fill_requested
from the_one.gleepglorp.fill.store import GleepGlorpFillRepository, NewFill, fill_view
from the_one.gleepglorp.proposals import guard, shape
from the_one.tools.base import Tool

logger = logging.getLogger(__name__)

FILL_FORM_TOOL_NAME = "fill_form"

NEEDS_CHAT = "Filling needs a chat."
NEEDS_PAGE = (
    "Filling works only when the operator asks from the drawer on an app page. "
    "Propose the change with propose_change instead."
)
NO_NOTES = "notes_enabled can't be filled: notes save at once and are not a form field."
FAILED = "Could not fill the form right now."


class FillFormTool(Tool):
    """Fill the operator's agent, MCP server or model provider editor with unsaved values.

    The description is platform prompt text: at most 90 tokens (o200k_base) and 440 characters
    (a test pins both). The cap rose from 360 for the provider kind (M36 F4 L5b).
    """

    name = FILL_FORM_TOOL_NAME
    summary = (
        "Fills the open agent, MCP server or provider editor with unsaved values; saves nothing."
    )
    description = (
        "Fill an agent, MCP server or provider editor with unsaved edits; the operator saves. "
        "Only from the drawer; else propose_change. "
        "create: changes holds name and fields (MCP or provider type too). "
        "change: agent, or target (MCP server or provider id or name); never an MCP type. "
        "Fields as propose_change, except notes_enabled. "
        'Leave a secret\'s value "" for the operator to enter; never a provider key.'
    )
    parameters = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(kinds.FILLABLE)},
            "action": {"type": "string", "enum": list(shape.ACTIONS)},
            "agent": {"type": ["string", "null"]},
            "target": {"type": ["string", "null"]},
            "changes": {"type": "object"},
        },
        "required": ["kind", "action", "changes"],
    }

    def __init__(self, agent_name: str | None = None) -> None:
        super().__init__(agent_name=agent_name)
        self._agent: Any = None

    def bind_agent(self, agent: Any) -> None:
        """Bind the owning Agent (the factory does, after construction). Unbound fails closed:
        every fill is flagged "unknown position"."""
        self._agent = agent

    async def execute(  # type: ignore[override]
        self,
        kind: Any = None,
        action: Any = None,
        agent: Any = None,
        changes: Any = None,
        target: Any = None,
        **_extra: Any,
    ) -> str:
        turn = current_turn.get()
        session_id = (turn.session_id if turn else None) or current_chat_session_id.get()
        if not session_id:
            return NEEDS_CHAT
        if turn is None or turn.page is None:
            return NEEDS_PAGE
        try:
            return await self._fill(session_id, turn, kind, action, agent, changes, target)
        except shape.ShapeError as e:
            return str(e)
        except Exception:  # noqa: BLE001 - the tool never raises into the loop
            logger.warning("fill_form failed", exc_info=True)
            return FAILED

    async def _fill(
        self,
        session_id: str,
        turn: Any,
        kind: Any,
        action: Any,
        agent: Any,
        changes: Any,
        target: Any = None,
    ) -> str:
        from the_one import time_zones
        from the_one.config import settings
        from the_one.db.connection import get_connection
        from the_one.encryption import get_encryptor

        if kind not in kinds.FILLABLE:
            raise shape.ShapeError(f"Only these kinds can be filled: {', '.join(kinds.FILLABLE)}.")
        if kind == "agent" and isinstance(changes, dict) and "notes_enabled" in changes:
            return NO_NOTES
        conn = await get_connection()
        eff = await time_zones.load_effective_zone(conn)
        enc = get_encryptor(settings.data_dir)
        norm = await kinds.normalize(
            kind,
            action,
            kinds.target_args(kind, agent, None, None, target),
            changes,
            conn=conn,
            now=time_zones.utcnow(),
            zone=eff.tzinfo,
            enc=enc,
            mode="fill",
        )
        refusal = await guard.check(
            conn, enc, norm.changes, relaxed=kinds.get(norm.kind).relaxed_guard_keys
        )
        if refusal is not None:
            return refusal
        untrusted, sources = compute_taint(self._agent, current_tool_call_id.get(), turn)
        if untrusted:
            # The outside-value guard (M36 F4 L3, DD7); see ``the_one/gleepglorp/outside.py``.
            refusal = outside.check(
                kinds.get(norm.kind),
                norm.changes,
                outside.collect(self._agent, current_tool_call_id.get(), turn),
            )
            if refusal is not None:
                return refusal
        repo = GleepGlorpFillRepository(conn)
        fill_id, replaced = await repo.insert(
            NewFill(
                session_id=session_id,
                kind=norm.kind,
                action=norm.action,
                agent_name=norm.agent_name,
                target_id=norm.target_id,
                target_key=norm.target_key,
                changes=norm.changes,
                base=norm.base,
                tool_call_id=current_tool_call_id.get(),
                untrusted=untrusted,
                untrusted_sources=sources,
            )
        )
        for old_id in replaced:
            old = await repo.get(old_id)
            if old is not None:
                await push_fill_changed(session_id, await fill_view(conn, old))
        stored = await repo.get(fill_id)
        warns: list[str] = []
        if stored is not None:
            view = await fill_view(conn, stored)
            warns = list(view.get("warnings") or [])
            await push_fill_requested(session_id, view)
        reply = (
            f"Fill {fill_id} is on the operator's screen as unsaved edits in the "
            f"{kinds.get(norm.kind).label} editor. "
            "Nothing is saved until they click Save."
        )
        if warns:
            reply += " Tell the operator: " + " ".join(warns)
        return reply
