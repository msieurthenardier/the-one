"""Shared per-session lock registry.

Both the WS handler (operator-typed messages) and the F3
dispatcher (peer-inbound messages) acquire the SAME asyncio.Lock
per chat_sessions.id. Closes the mission Known Issue raised in
F3 planning where the two paths owned distinct lock identities
and would have raced on agent.messages.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

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


def clear_locks_for_test() -> None:
    """Drop all locks. Test fixtures only — production code never
    calls this. Mirrors the pre-existing ``_clear_for_test`` on the
    MCP pool module (and, before Mission 23 Flight 1 deleted the
    connector package, the connector pool and dispatcher modules).
    """
    session_locks.clear()
