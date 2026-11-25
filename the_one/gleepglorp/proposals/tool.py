"""``propose_change``: GleepGlorp's one write-shaped tool (Mission 36 F2 L2, DD5).

It records a proposal in ``gleepglorp_proposals`` and changes nothing else: no agent, rule,
routine or setting is written. The operator decides on the chat's card (Leg 6) and the
approval path applies it (Leg 4). The result is shipped text ("Proposal N is waiting..."),
so the tool is in ``TRUSTED_TOOL_NAMES``: one proposal never flags the next.

The taint is the same ``compute_taint`` the notes and routine tools use, read from the
conversation the model has seen; a ``read_app_config`` result that holds only operator-typed
fields (the mark ``is_trusted_result`` checks) does not flag it. The secret guard runs before
the taint and the insert (M36 F2 L3).
"""

from __future__ import annotations

import logging
from typing import Any

from the_one.agent._context import current_chat_session_id, current_tool_call_id, current_turn
from the_one.agent.taint import compute_taint
from the_one.gleepglorp import kinds, outside
from the_one.gleepglorp.proposals import guard, shape
from the_one.gleepglorp.proposals.events import push_proposal_changed
from the_one.gleepglorp.proposals.store import (
    GleepGlorpProposalRepository,
    NewProposal,
    ProposalOpen,
    proposal_view,
)
from the_one.tools.base import Tool

logger = logging.getLogger(__name__)

PROPOSE_CHANGE_TOOL_NAME = "propose_change"

NEEDS_CHAT = "Proposals need a chat."


class ProposeChangeTool(Tool):
    """Record one proposed change for the operator to approve."""

    name = PROPOSE_CHANGE_TOOL_NAME
    summary = "Proposes a change for the operator to approve; changes nothing itself."
    description = (
        "Propose one change; nothing changes until approved. "
        "kind: agent, rule, routine, mcp_server, provider, knowledge_base, secret, tool_config "
        "or app_settings. agent "
        "names the agent (for a new agent, put name in changes); rule is a rule's number from "
        "1, routine a routine's name; target is an existing MCP server's, provider's, "
        "knowledge base's or secret's id or name, or a built-in tool's name; app_settings "
        "takes none. "
        "Fields and shapes: read_app_config kind=fields name=<kind>."
    )
    parameters = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(kinds.KINDS)},
            "action": {"type": "string", "enum": list(shape.ACTIONS)},
            "agent": {"type": ["string", "null"]},
            "rule": {"type": ["integer", "null"]},
            "routine": {"type": ["string", "null"]},
            "target": {"type": ["string", "null"]},
            "changes": {"type": "object"},
        },
        "required": ["kind", "action", "changes"],
    }

    def __init__(self, agent_name: str | None = None) -> None:
        super().__init__(agent_name=agent_name)
        self._agent: Any = None

    def bind_agent(self, agent: Any) -> None:
        """Bind the owning Agent (the factory calls this after construction). An unbound
        tool fails closed: every proposal is flagged "unknown position"."""
        self._agent = agent

    async def execute(
        self,
        kind: Any = None,
        action: Any = None,
        agent: Any = None,
        rule: Any = None,
        routine: Any = None,
        changes: Any = None,
        target: Any = None,
        **_extra: Any,
    ) -> str:
        turn = current_turn.get()
        session_id = (turn.session_id if turn else None) or current_chat_session_id.get()
        if not session_id:
            return NEEDS_CHAT
        try:
            return await self._propose(
                session_id, turn, kind, action, agent, rule, routine, changes, target
            )
        except shape.ShapeError as e:
            return str(e)
        except Exception:  # noqa: BLE001 - the tool never raises into the loop
            logger.warning("propose_change failed", exc_info=True)
            return "Could not record that proposal right now."

    async def _propose(
        self,
        session_id: str,
        turn: Any,
        kind: Any,
        action: Any,
        agent: Any,
        rule: Any,
        routine: Any,
        changes: Any,
        target: Any = None,
    ) -> str:
        from the_one import time_zones
        from the_one.config import settings
        from the_one.db.connection import get_connection
        from the_one.encryption import get_encryptor

        conn = await get_connection()
        eff = await time_zones.load_effective_zone(conn)
        norm = await kinds.normalize(
            kind,
            action,
            kinds.target_args(kind, agent, rule, routine, target),
            changes,
            conn=conn,
            now=time_zones.utcnow(),
            zone=eff.tzinfo,
            enc=get_encryptor(settings.data_dir),
        )
        # The secret guard: after the shape accepts the change, before the taint and the insert.
        refusal = await guard.check(
            conn,
            get_encryptor(settings.data_dir),
            norm.changes,
            relaxed=kinds.get(norm.kind).relaxed_guard_keys,
        )
        if refusal is not None:
            return refusal
        untrusted, sources = compute_taint(self._agent, current_tool_call_id.get(), turn)
        if untrusted:
            # The outside-value guard (M36 F4 L3, DD7): after outside content, a link, address,
            # command or loader key the operator did not supply is refused (fails closed).
            refusal = outside.check(
                kinds.get(norm.kind),
                norm.changes,
                outside.collect(self._agent, current_tool_call_id.get(), turn),
                norm.base,
            )
            if refusal is not None:
                return refusal
        repo = GleepGlorpProposalRepository(conn)
        try:
            proposal_id = await repo.insert(
                NewProposal(
                    session_id=session_id,
                    tool_call_id=current_tool_call_id.get(),
                    kind=norm.kind,
                    action=norm.action,
                    agent_name=norm.agent_name,
                    target_id=norm.target_id,
                    target_key=norm.target_key,
                    changes=norm.changes,
                    base=norm.base,
                    untrusted=untrusted,
                    untrusted_sources=sources,
                )
            )
        except ProposalOpen as e:
            return (
                f"Proposal {e.open_id} is still waiting for the operator. "
                "Wait for their answer before the next step."
            )
        # The insert withdrew every open proposal it replaced (``result.by`` is the new id); push
        # each one's view so its card folds now, not at the next reload (squawk 0407).
        for old in await repo.list_for_session(session_id):
            if (
                old.status == "withdrawn"
                and old.result
                and old.result.get("reason") == "replaced"
                and old.result.get("by") == proposal_id
            ):
                await push_proposal_changed(session_id, await proposal_view(conn, old))
        stored = await repo.get(proposal_id)
        if stored is not None:
            await push_proposal_changed(session_id, await proposal_view(conn, stored))
        return f"Proposal {proposal_id} is waiting for the operator. Nothing has changed yet."
