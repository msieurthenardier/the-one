"""PTY session registry + idle reaper (F4 Decisions 4 + 5).

This module is the storage layer behind the four ``shell_session_*`` tools
(wired in L6). It owns:

* The module-level ``(agent_name, session_id) -> _RegistryEntry`` mapping.
* An ``asyncio.Lock`` that serializes mutations to that mapping.
* A lazily-spawned idle-reaper ``asyncio.Task`` that periodically closes
  sessions whose ``last_activity`` is older than the per-session
  ``ttl_seconds``.
* A ``shutdown_drain()`` hook wired into the FastAPI ``lifespan`` so a
  graceful container shutdown cancels the reaper and drains all live
  sessions.

Design references:

* **F4 Decision 4** — per-explicit-handle session addressing. Registry is
  keyed on ``(agent_name, session_id)``; ``session_id`` formatted as
  ``f"pty-{uuid4().hex}"``. Cross-agent isolation falls out of the keying:
  agent B looking up agent A's session_id misses the dict naturally.
* **F4 Decision 5** — 5-minute idle TTL + 5 max concurrent + process-
  lifetime persistence + FastAPI-lifespan-registered reaper. Per-agent
  TTL narrowing is honored by storing the resolved
  ``pty_session_idle_ttl_seconds`` alongside the session at register time.

Lock-and-await deadlock avoidance:
    ``close()`` and ``_reap_once()`` both follow the snapshot-under-lock /
    close-after-release pattern. Holding ``_lock`` across the ~1s
    SIGTERM-to-SIGKILL ladder inside ``session.close()`` would block all
    other registry operations for that window — unacceptable for a
    multi-agent surface.

Module imports ``PtySession`` from ``the_one.platform.pty``, which now
imports cleanly on all platforms (M15 F3 Leg 1 split-module refactor).
The registry therefore collects on Windows too; the concrete Windows PTY
backend (``WindowsPtySession``) lands with Leg 2, after which the registry
becomes fully exercisable on Windows.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from uuid import uuid4

from the_one.platform.pty import PtySession

logger = logging.getLogger(__name__)

# Reaper wake interval. The reaper sleeps this long between sweeps; tests
# monkeypatch it down for fast integration runs (or call ``_reap_once()``
# directly for deterministic single-pass tests).
_REAPER_INTERVAL_SECONDS = 30.0


@dataclass
class _RegistryEntry:
    """A single live PTY session with its resolved idle TTL.

    NOTE: ``agent_name`` is intentionally NOT stored here. The registry
    dict is keyed on ``(agent_name, session_id)``; duplicating
    ``agent_name`` on the entry would create drift risk if the two ever
    fell out of sync.
    """

    session: PtySession
    ttl_seconds: int


# Module-level state. All mutations (other than the lazy lock construction
# itself) go through ``_lock``.
_sessions: dict[tuple[str, str], _RegistryEntry] = {}
_lock: asyncio.Lock = asyncio.Lock()
_reaper_task: asyncio.Task[None] | None = None
_shutting_down: bool = False


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────


def new_session_id() -> str:
    """Return a fresh ``pty-<uuid4hex>`` session id (40 chars total)."""
    return f"pty-{uuid4().hex}"


async def register(
    agent_name: str,
    session_id: str,
    session: PtySession,
    ttl_seconds: int,
) -> None:
    """Insert ``session`` under ``(agent_name, session_id)`` and ensure
    the reaper is running.

    Raises ``RuntimeError`` if ``shutdown_drain()`` has already been
    called — better to fail loudly than silently orphan a session that
    the reaper will never visit.
    """
    if _shutting_down:
        raise RuntimeError("session registry is shutting down")
    async with _lock:
        _sessions[(agent_name, session_id)] = _RegistryEntry(
            session=session,
            ttl_seconds=ttl_seconds,
        )
        await _ensure_reaper_running_locked()


async def get(agent_name: str, session_id: str) -> PtySession | None:
    """Return the session for ``(agent_name, session_id)``, or ``None``.

    Cross-agent isolation: a key miss is the natural result of one agent
    requesting another agent's session_id — they're keyed separately.
    """
    async with _lock:
        entry = _sessions.get((agent_name, session_id))
        return entry.session if entry is not None else None


async def close(agent_name: str, session_id: str) -> bool:
    """Remove the entry, then ``await session.close()`` outside the lock.

    Returns ``True`` if a session was found and closed, ``False`` if no
    session matched the key.

    The two-phase pattern is mandatory: ``session.close()`` performs a
    SIGTERM → 1s wait → SIGKILL ladder via ``run_in_executor``. Holding
    ``_lock`` across that window would freeze every other registry
    operation. Snapshot under lock, release, then await is the only safe
    sequencing.
    """
    async with _lock:
        entry = _sessions.pop((agent_name, session_id), None)
    if entry is None:
        return False
    try:
        await entry.session.close()
    except Exception:
        # ``close()`` is idempotent on ``UnixPtySession`` and shouldn't
        # raise, but a rogue subclass could. Log and continue — the
        # entry has already been removed from the registry.
        logger.exception(
            "session.close() raised during registry close: agent=%r session=%r",
            agent_name,
            session_id,
        )
    return True


async def list_for_agent(agent_name: str) -> list[str]:
    """Return the session ids owned by ``agent_name`` (any order)."""
    async with _lock:
        return [sid for (an, sid) in _sessions if an == agent_name]


async def count_for_agent(agent_name: str) -> int:
    """Return the count of live sessions owned by ``agent_name``."""
    async with _lock:
        return sum(1 for (an, _sid) in _sessions if an == agent_name)


async def shutdown_drain() -> None:
    """Cancel the reaper task and close every remaining session.

    Wired into the FastAPI ``lifespan`` shutdown branch. After this runs,
    ``register()`` raises ``RuntimeError`` so any late-arriving session
    creation fails loudly rather than orphaning a process.

    Belt-and-suspenders: drains the registry directly even if the reaper
    was never spawned (e.g. ``shutdown_drain`` called with no sessions
    ever registered).
    """
    global _reaper_task, _shutting_down
    _shutting_down = True

    task = _reaper_task
    if task is not None and not task.done():
        task.cancel()
        # ``contextlib.suppress`` swallows the ``CancelledError`` that the
        # awaiter receives when a cancelled task is awaited. The reap
        # loop's own ``CancelledError`` handler runs the registry drain
        # before the task actually finishes; we just need to wait for it.
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # Belt-and-suspenders drain. If the reaper drained the registry
    # already (the common path), the snapshot below is empty and this is
    # a no-op. If the reaper never spawned (no sessions ever registered),
    # this still cleans up any leftover entries.
    async with _lock:
        snapshot = list(_sessions.items())
        _sessions.clear()
    for key, entry in snapshot:
        try:
            await entry.session.close()
        except Exception:
            logger.exception(
                "session.close() raised during shutdown_drain: key=%r",
                key,
            )

    _reaper_task = None


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────


async def _ensure_reaper_running_locked() -> None:
    """Spawn the reaper task if it isn't already running. Must be called
    under ``_lock`` to avoid a double-spawn race."""
    global _reaper_task
    if _reaper_task is None or _reaper_task.done():
        _reaper_task = asyncio.create_task(_reap_loop())


async def _reap_once() -> list[PtySession]:
    """Run a single reap pass: close every session whose ``last_activity``
    is older than its ``ttl_seconds``. Returns the closed sessions (for
    test purchase).

    Uses the same snapshot-under-lock / close-after-release pattern as
    ``close()`` to avoid serializing on the SIGTERM-to-SIGKILL ladder.
    """
    now = time.monotonic()
    async with _lock:
        expired: list[tuple[tuple[str, str], PtySession]] = []
        for key, entry in list(_sessions.items()):
            if (now - entry.session.last_activity) > entry.ttl_seconds:
                expired.append((key, entry.session))
        for key, _session in expired:
            _sessions.pop(key, None)

    closed: list[PtySession] = []
    for key, session in expired:
        try:
            await session.close()
        except Exception:
            # One bad ``close()`` must not block reaping the rest.
            logger.exception(
                "session.close() raised during reap pass: key=%r",
                key,
            )
        closed.append(session)
    return closed


async def _reap_loop() -> None:
    """Background loop: sleep, reap, repeat. Drains the registry on
    cancellation, then re-raises ``CancelledError`` to let the awaiter
    see the cancel."""
    try:
        while True:
            await asyncio.sleep(_REAPER_INTERVAL_SECONDS)
            try:
                await _reap_once()
            except Exception:
                # Defensive: an unexpected error inside ``_reap_once``
                # must not kill the loop. Log and continue; the next
                # tick will retry.
                logger.exception("reap pass raised; continuing")
    except asyncio.CancelledError:
        # Drain the entire registry before re-raising. Same snapshot+
        # close pattern as ``_reap_once`` / ``close()``.
        async with _lock:
            snapshot = list(_sessions.items())
            _sessions.clear()
        for key, entry in snapshot:
            try:
                await entry.session.close()
            except Exception:
                logger.exception(
                    "session.close() raised during reap drain: key=%r",
                    key,
                )
        raise


async def _clear_for_test() -> None:
    """Test seam: tear down the reaper and empty the registry.

    Tests must call this in an ``autouse=True`` fixture AFTER each test;
    otherwise the next test inherits a stale ``_reaper_task`` reference
    bound to a torn-down event loop. Resets ``_shutting_down`` so each
    test starts fresh.
    """
    global _reaper_task, _shutting_down

    task = _reaper_task
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    _reaper_task = None
    _shutting_down = False

    async with _lock:
        snapshot = list(_sessions.items())
        _sessions.clear()
    for key, entry in snapshot:
        try:
            await entry.session.close()
        except Exception:
            logger.exception(
                "session.close() raised during test clear: key=%r",
                key,
            )
