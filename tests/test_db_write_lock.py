"""Tests for the shared-connection write-transaction guard (Flight 2 Leg 1,
DD-13): behaviour (atomicity, the realistic concurrent-interleave case,
same-task re-entry detection, two contending tasks both landing) plus the
AC-9 source guard proving ``.commit()`` / ``.rollback()`` are confined to
the guard itself and to ``schema.py``'s migrations.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import aiosqlite
import pytest

from the_one.db._write_lock import reset_for_test, write_transaction


@pytest.fixture(autouse=True)
def _reset_lock_state():
    """Reset the module-level lock/owner before and after each test.

    The lock and the current-owner are module-level state in
    ``the_one.db._write_lock``, shared across the whole test session (the
    same reason ``the_one/sessions/_locks.py`` ships
    ``clear_locks_for_test`` and the MCP pool ships ``_clear_for_test``).
    This module exercises unusual paths — concurrent tasks, re-entry — and
    must start and leave each test from a known-clean state. Deliberately
    module-local (the ``tests/test_sandbox_factory.py::_reset_log_guard``
    pattern), NOT a global conftest fixture: no other test module depends
    on this reset.
    """
    reset_for_test()
    yield
    reset_for_test()


@pytest.fixture
async def conn(tmp_path):
    """A real aiosqlite connection over a throwaway single-column table."""
    db_path = tmp_path / "write_lock_test.db"
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
    await connection.commit()
    yield connection
    await connection.close()


class _BoomError(Exception):
    """Marker exception for the failing-writer tests."""


async def _values(conn: aiosqlite.Connection) -> list[str]:
    async with conn.execute("SELECT value FROM t ORDER BY value") as cur:
        return [row[0] for row in await cur.fetchall()]


# ── AC-8(a): single-task failing insert leaves no rows ─────────────────────


async def test_single_task_failing_write_leaves_no_rows(conn):
    with pytest.raises(_BoomError):
        async with write_transaction(conn):
            await conn.execute("INSERT INTO t (value) VALUES ('a')")
            raise _BoomError("mid-write failure")
    assert await _values(conn) == []


async def test_single_task_success_commits(conn):
    async with write_transaction(conn):
        await conn.execute("INSERT INTO t (value) VALUES ('a')")
    assert await _values(conn) == ["a"]


# ── AC-8(b): the realistic concurrent-interleave case ───────────────────────


async def test_interleave_failing_task_rows_absent_plain_writer_rows_present(conn):
    """Task A inserts, yields, then raises; task B's single-statement write
    (itself going through ``write_transaction``, per the DD-13 rule that
    EVERY committer holds the lock) is attempted in the gap. Because the
    lock serialises them, B's write lands only once A has rolled back and
    released — proving A's row never survives and B's row is unaffected by
    A's failure, the realistic interleaving DD-13 protects against (a test
    whose second task never contends for the lock at all would prove
    nothing about this guard)."""
    a_inserted = asyncio.Event()

    async def task_a():
        with pytest.raises(_BoomError):
            async with write_transaction(conn):
                await conn.execute("INSERT INTO t (value) VALUES ('A')")
                a_inserted.set()
                # Yield to the loop so task B is scheduled and attempts to
                # acquire the lock WHILE A is still mid-transaction.
                await asyncio.sleep(0)
                raise _BoomError("A fails after its first statement")

    async def task_b():
        await a_inserted.wait()
        async with write_transaction(conn):
            await conn.execute("INSERT INTO t (value) VALUES ('B')")

    await asyncio.gather(task_a(), task_b())
    assert await _values(conn) == ["B"]


# ── AC-8(c): same-task re-entry is detected, not deadlocked ────────────────


async def test_reentry_by_same_task_raises_runtimeerror(conn):
    async with write_transaction(conn):
        await conn.execute("INSERT INTO t (value) VALUES ('outer')")
        with pytest.raises(RuntimeError):
            async with write_transaction(conn):
                pass  # pragma: no cover - never reached; detected before acquiring
    # The outer transaction is unaffected by the inner RuntimeError (caught
    # by pytest.raises inside the outer body) and still commits cleanly.
    assert await _values(conn) == ["outer"]


async def test_reentry_detected_before_acquiring_does_not_deadlock(conn):
    """A regression guard for the ordering itself: if the re-entry check
    ran AFTER acquiring the lock, this test would hang forever instead of
    raising. ``asyncio.wait_for`` turns a would-be hang into a prompt
    failure rather than a wedged test run."""

    async def reenter():
        async with write_transaction(conn):
            async with write_transaction(conn):
                pass  # pragma: no cover

    with pytest.raises(RuntimeError):
        await asyncio.wait_for(reenter(), timeout=5)


# ── AC-8(d): two contending tasks complete in sequence, both commits land ──


async def test_two_contending_tasks_both_commit(conn):
    async def writer(value: str) -> None:
        async with write_transaction(conn):
            await conn.execute("INSERT INTO t (value) VALUES (?)", (value,))

    await asyncio.gather(writer("x"), writer("y"))
    assert await _values(conn) == ["x", "y"]


# ── AC-9: source guard ──────────────────────────────────────────────────────


def test_commit_and_rollback_confined_to_write_lock_and_schema():
    """``.commit()`` / ``.rollback()`` on the shared connection may appear
    ONLY in ``the_one/db/_write_lock.py`` (the guard itself — the one place
    allowed to call them directly) and ``the_one/db/schema.py`` (its
    migrations run inside ``ensure_schema`` at ``init_db()``, BEFORE any
    request or background task exists — there is no concurrent committer
    on the connection yet, so the migrations' own per-block ``commit()``s
    need no lock; see the comment at ``schema.py``'s v8 migration block for
    the full argument). Every other write path in ``the_one/`` must go
    through ``write_transaction`` (DD-13) — this is the guard that keeps
    that true as the codebase grows (the rule decays silently otherwise).

    Walks the AST (not a text/substring scan) so a comment or docstring
    that merely mentions ``.commit()`` cannot trip the guard, and an
    aliased call (``c = self.conn; c.commit()``) is still caught, since
    it matches on the ``Call`` node's ``Attribute`` shape rather than on
    the receiver's spelling.
    """
    allowed = {
        Path("the_one") / "db" / "_write_lock.py",
        Path("the_one") / "db" / "schema.py",
    }
    watched_attrs = {"commit", "rollback"}
    offenders: list[str] = []
    for path in Path("the_one").rglob("*.py"):
        if path in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in watched_attrs
            ):
                offenders.append(f"{path}:{node.lineno}")
    assert offenders == [], (
        f"commit()/rollback() found outside the write-lock guard: {offenders} "
        "— every write must go through write_transaction() (DD-13)"
    )
