"""Shared per-session lock registry.

Both the WS handler (operator-typed messages) and the F3
dispatcher (peer-inbound messages) acquire the SAME asyncio.Lock
per chat_sessions.id. Closes the mission Known Issue raised in
F3 planning where the two paths owned distinct lock identities
and would have raced on agent.messages.
"""

from __future__ import annotations

import asyncio
import secrets
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# Module-level defaultdict. Locks created lazily on first use.
# F10 hardening flag inherited from F3 _inbound.py:46-50: locks
# accumulate monotonically with session count over process
# lifetime; WeakValueDictionary / TTL / LRU is deferred until
# growth matters.
session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def is_session_processing(session_id: str) -> bool:
    """True iff a lock exists for this session AND is currently held.

    MUST NOT trigger the defaultdict's lazy-create — uses .get(),
    not the [] indexer. Consumed by the WS handler's
    _restore_session and _build_session_joined_ok read paths.
    """
    lock = session_locks.get(session_id)
    return lock is not None and lock.locked()


# Web turns spawned but not yet holding the lock (Mission 31 F6 L10b). Moved here
# from the web app so the REST projection can answer ``is_session_busy`` without
# an import cycle. ONE dict object: ``app.py`` imports it under its old name and
# never rebinds it; ``clear_locks_for_test`` does not touch it.
_session_inflight: dict[str, set[asyncio.Task]] = {}

# Process-local turn counters behind the Chats list's "new reply" marker. Never
# pruned, like ``session_locks``. ``_BOOT_ID`` makes a restart visible to clients.
_BOOT_ID = secrets.token_hex(4)
_turn_counts: dict[str, int] = {}


def is_session_busy(session_id: str) -> bool:
    """True iff a turn holds the session lock OR a web turn is spawned for it."""
    return is_session_processing(session_id) or bool(_session_inflight.get(session_id))


def turn_seq(session_id: str) -> str:
    """``"{boot_id}:{n}"``; ``n`` counts the turns that have finished here."""
    return f"{_BOOT_ID}:{_turn_counts.get(session_id, 0)}"


class TurnHandle:
    """Yielded by :func:`track_turn`; the body sets ``ran`` once a turn really starts."""

    __slots__ = ("ran",)

    def __init__(self) -> None:
        self.ran = False


def _notify_sessions_changed() -> None:
    # Lazy: the leaf module lives under ``the_one.db``; keep this module import-light.
    from the_one.db._session_changes import notify_sessions_changed

    notify_sessions_changed()


@asynccontextmanager
async def track_turn(session_id: str) -> AsyncIterator[TurnHandle]:
    """Acquire the session lock for a turn and tell the Chats list about it.

    Notifies once the lock is held (start). In a ``finally`` OUTSIDE the lock,
    always notifies again once the start push went out (so an early return or an
    exception before ``turn.ran`` still clears the busy state), and bumps the
    session's turn counter only when the body set ``turn.ran``. The end push
    never reads a held lock. A cancel while waiting for the lock neither bumps
    nor notifies.
    """
    turn = TurnHandle()
    entered = False
    try:
        async with session_locks[session_id]:
            entered = True
            _notify_sessions_changed()
            yield turn
    finally:
        if turn.ran:
            _turn_counts[session_id] = _turn_counts.get(session_id, 0) + 1
        if entered:
            _notify_sessions_changed()


def clear_locks_for_test() -> None:
    """Drop all locks. Test fixtures only — production code never
    calls this. Mirrors the pre-existing ``_clear_for_test`` on the
    MCP pool module (and, before Mission 23 Flight 1 deleted the
    connector package, the connector pool and dispatcher modules).
    """
    session_locks.clear()
