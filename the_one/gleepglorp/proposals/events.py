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
        await broadcast_to_session(session_id, {"type": PROPOSAL_CHANGED, "proposal": view})
    except Exception:  # noqa: BLE001
        logger.warning("proposal_changed push failed", exc_info=True)
