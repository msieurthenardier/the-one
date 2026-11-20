"""The ``proposal_changed`` frame (Mission 36 F2 L2).

Pushed to the chat's subscribers when a proposal is created (here) and, in Leg 4, when its
status changes. The payload is :func:`the_one.gleepglorp.proposals.store.proposal_view`.
Zero subscribers is a clean no-op, and a client that does not know the frame ignores it.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PROPOSAL_CHANGED = "proposal_changed"


async def push_proposal_changed(session_id: str, view: dict[str, Any]) -> None:
    """Send ``{"type": "proposal_changed", "proposal": view}`` to the chat's sockets.

    Never raises: a push failure is logged and the proposal stays recorded.
    """
    from the_one.sessions._broadcast import broadcast_to_session

    try:
        await broadcast_to_session(
            session_id, {"type": PROPOSAL_CHANGED, "session_id": session_id, "proposal": view}
        )
    except Exception:  # noqa: BLE001
        logger.warning("proposal_changed push failed", exc_info=True)


PROPOSALS_SNAPSHOT = "proposals_snapshot"
SNAPSHOT_CAP = 200


async def snapshot_frame(
    conn: Any, session_id: str, agent_name: str | None
) -> dict[str, Any] | None:
    """The ``proposals_snapshot`` frame for a joining socket, or ``None`` (not a GleepGlorp
    chat, or the read failed: a join never fails over it).

    Keyed by ids, not a live ``Session``, so a degraded join (GleepGlorp off, no model, provider
    missing) can send it too. Every proposal of the chat, open and resolved, newest 200 in id
    order.
    """
    from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository, proposal_view
    from the_one.naming import GLEEPGLORP_AGENT_NAME

    if agent_name != GLEEPGLORP_AGENT_NAME:
        return None
    try:
        rows = await GleepGlorpProposalRepository(conn).list_for_session(session_id)
        views = [await proposal_view(conn, r) for r in rows[-SNAPSHOT_CAP:]]
    except Exception:  # noqa: BLE001
        logger.warning("proposals_snapshot read failed", exc_info=True)
        return None
    # M36 F3 L5: the chat's form fills ride along under their own key, read in their own try so
    # a fills failure never drops the proposals (and proposal-cards.js never sees a fill).
    try:
        from the_one.gleepglorp.fill.events import snapshot_fills

        fills = await snapshot_fills(conn, session_id)
    except Exception:  # noqa: BLE001
        logger.warning("fills snapshot read failed", exc_info=True)
        fills = []
    return {
        "type": PROPOSALS_SNAPSHOT,
        "session_id": session_id,
        "proposals": views,
        "fills": fills,
    }
