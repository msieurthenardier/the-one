"""The fill frames (Mission 36 F3 L5, DD6).

``fill_requested`` is pushed once when a fill is recorded and ``fill_changed`` on every status
change (replacement, claim, outcome). Both go to the chat's subscribers, never raise, and a
zero-subscriber push is a clean no-op; a client that does not know a frame ignores it.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

FILL_REQUESTED = "fill_requested"
FILL_CHANGED = "fill_changed"
SNAPSHOT_CAP = 200


async def _push(session_id: str, frame_type: str, view: dict[str, Any]) -> None:
    from the_one.sessions._broadcast import broadcast_to_session

    try:
        await broadcast_to_session(
            session_id, {"type": frame_type, "session_id": session_id, "fill": view}
        )
    except Exception:  # noqa: BLE001
        logger.warning("%s push failed", frame_type, exc_info=True)


async def push_fill_requested(session_id: str, view: dict[str, Any]) -> None:
    await _push(session_id, FILL_REQUESTED, view)


async def push_fill_changed(session_id: str, view: dict[str, Any]) -> None:
    await _push(session_id, FILL_CHANGED, view)


async def snapshot_fills(conn: Any, session_id: str) -> list[dict[str, Any]]:
    """The newest 200 fill views of the chat, in id order."""
    from the_one.gleepglorp.fill.store import GleepGlorpFillRepository, fill_view

    rows = await GleepGlorpFillRepository(conn).list_for_session(session_id)
    return [await fill_view(conn, r) for r in rows[-SNAPSHOT_CAP:]]
