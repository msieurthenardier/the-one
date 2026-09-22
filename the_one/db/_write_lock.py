"""The single write-transaction guard for the shared SQLite connection.

Flight 2 Leg 1, DD-13. ``aiosqlite`` serialises individual statements on
its one shared connection, not transactions — a coroutine's ``commit()``
commits whatever is currently open on that connection, including another
coroutine's partial multi-statement write. A lock scoped to only
multi-statement writers does NOT protect against this: a plain
single-statement self-committing method is itself a committer, and its
``commit()`` can land inside another writer's partial transaction just as
easily as a second multi-statement writer's can (the Architect modelled the
narrower scoping in cycle 1 and it destroyed a concurrent writer's rows).

The rule this module enforces: **every code path that calls
``conn.commit()`` on the shared connection holds this lock while it does
so** — not only multi-statement writers. ``write_transaction`` is the only
place ``commit()``/``rollback()`` may be called directly outside
``the_one/db/schema.py`` (whose migrations run at ``init_db()``, before any
request or background task exists, so there is no concurrent committer to
race — see the comment at ``schema.py``'s v8 migration block). Guarded by
``tests/test_db_write_lock.py``'s source-scan test.

No explicit ``BEGIN``: under aiosqlite's default ``isolation_level=""``,
the first DML statement inside the block already opens a transaction; an
explicit ``BEGIN`` would raise "cannot start a transaction within a
transaction" whenever another coroutine's DML is mid-flight on the shared
connection — exactly under the concurrency this guard exists for.

Not re-entrant, and re-entry is DETECTED rather than allowed to deadlock:
a second ``write_transaction`` entered by the SAME asyncio task before the
first exits raises ``RuntimeError`` immediately (checked BEFORE acquiring
the lock — acquiring first would deadlock the task against itself, which is
exactly the failure mode the check exists to turn into a clean error).
Compose multi-step writes as sequential transactions, never nested ones —
this is also why callers must never wrap a call into another component
(e.g. the vector store) that itself acquires this lock inside their own
``write_transaction`` block.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

import aiosqlite

_lock = asyncio.Lock()
_owner: asyncio.Task | None = None


@contextlib.asynccontextmanager
async def write_transaction(conn: aiosqlite.Connection) -> AsyncIterator[None]:
    """Async context manager: acquire the module-level write lock, yield,
    then commit on clean exit or roll back if the body raised.

    ``conn`` is accepted (rather than closing over a module-level
    connection) so every repository passes its own ``self.conn`` — there is
    exactly one live connection per process in practice, but the guard
    itself stays connection-agnostic.
    """
    global _owner
    task = asyncio.current_task()
    if _owner is task:
        raise RuntimeError(
            "write_transaction re-entered by its own task — compose as "
            "sequential transactions, never nested"
        )
    async with _lock:
        _owner = task
        try:
            yield
            await conn.commit()
        except BaseException:
            # Rollback on BaseException (not just Exception) so a
            # CancelledError mid-write does not leave an open transaction
            # for the next lock holder to commit by accident.
            await conn.rollback()
            raise
        finally:
            _owner = None


def reset_for_test() -> None:
    """Clear the owner and replace the lock. Test fixtures only.

    The lock and owner are module-level state shared across the whole test
    session (mirrors ``the_one/sessions/_locks.py``'s
    ``clear_locks_for_test`` and ``the_one/mcp/_pool.py``'s
    ``_clear_for_test``) — a test that crashes mid-transaction or that
    exercises the re-entry guard must not leak state into the next test.
    """
    global _lock, _owner
    _lock = asyncio.Lock()
    _owner = None
