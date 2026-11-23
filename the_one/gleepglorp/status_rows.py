"""The pieces the proposal and fill stores share (Mission 36 F4 L1b).

Both stores keep one status-bearing row per item in a table with no foreign keys and push a
frame to the chat's sockets. Only what is genuinely common lives here: the JSON helpers, a
generic ``get`` / ``list_for_session`` over a table, a column list and a row decoder, and the
frame push. Status transitions (``mark_op``, the fills' ``claim`` and ``record_outcome``) and each
store's ``insert`` stay in their own stores: their rules differ (one open proposal per chat,
claim tokens and leases for fills).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any, TypeVar

import aiosqlite

logger = logging.getLogger(__name__)

T = TypeVar("T")


def loads(raw: Any, default: Any = None) -> Any:
    """``json.loads`` that returns ``default`` for ``None`` or unreadable text."""
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def dumps(value: Any) -> str:
    """Compact, non-ASCII-escaped JSON: how both stores write ``changes`` and ``base``."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


async def get_row(
    conn: aiosqlite.Connection,
    table: str,
    cols: str,
    decode: Callable[[Any], T],
    row_id: int,
) -> T | None:
    async with conn.execute(
        f"SELECT {cols} FROM {table} WHERE id = ?",  # noqa: S608 - fixed table and columns
        (row_id,),
    ) as cur:
        row = await cur.fetchone()
    return decode(row) if row else None


async def list_for_session_rows(
    conn: aiosqlite.Connection,
    table: str,
    cols: str,
    decode: Callable[[Any], T],
    session_id: str,
) -> list[T]:
    async with conn.execute(
        f"SELECT {cols} FROM {table} WHERE session_id = ? ORDER BY id",  # noqa: S608
        (session_id,),
    ) as cur:
        return [decode(r) for r in await cur.fetchall()]


async def push_session_frame(
    session_id: str, frame_type: str, payload_key: str, view: dict[str, Any], log_label: str
) -> None:
    """Send ``{"type": frame_type, "session_id": ..., payload_key: view}`` to the chat's sockets.

    Never raises: a push failure is logged under ``log_label`` and the row stays recorded.
    ``broadcast_to_session`` is imported here, not at module level, because tests patch
    ``the_one.sessions._broadcast.broadcast_to_session``.
    """
    from the_one.sessions._broadcast import broadcast_to_session

    try:
        await broadcast_to_session(
            session_id, {"type": frame_type, "session_id": session_id, payload_key: view}
        )
    except Exception:  # noqa: BLE001
        logger.warning("%s push failed", log_label, exc_info=True)
