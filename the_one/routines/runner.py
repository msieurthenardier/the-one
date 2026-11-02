"""Run one routine unattended (Mission 33 F1 leg 4, DD6, DD8, DD9).

``run_routine`` starts a new web chat for the run, spawns the routine turn through
the registered ``TurnHost`` (the web app implements it, so this package never
imports ``interfaces/``), bounds the run with a time limit, classifies how it
ended and updates the chat and the run row once the session lock is released.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import Callable, Coroutine
from typing import Any, Protocol

from the_one.db.connection import get_connection
from the_one.db.models import now_iso
from the_one.db.repositories import ChatSessionRepository
from the_one.routines.models import Routine, RoutineRun
from the_one.routines.repository import (
    AgentRoutineRepository,
    RoutineRunRepository,
    _now_iso,
)

logger = logging.getLogger(__name__)

_TIMEOUT_ENV = "THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS"
_DEFAULT_TIMEOUT_SECONDS = 900.0
# Test override: the floor the env value is clamped to.
_TIMEOUT_FLOOR_SECONDS = 60.0
_CANCEL_WAIT_SECONDS = 5.0
_INTERRUPT_WAIT_SECONDS = 3.0


def routine_run_timeout_seconds() -> float:
    """The run's time limit, read at call time and clamped to the floor."""
    raw = os.environ.get(_TIMEOUT_ENV)
    value = _DEFAULT_TIMEOUT_SECONDS
    if raw is not None:
        try:
            value = float(raw)
        except ValueError:
            logger.warning("%s=%r is not a number; using the default", _TIMEOUT_ENV, raw)
    return max(_TIMEOUT_FLOOR_SECONDS, value)


# ── TurnHost ──────────────────────────────────────────────────────────────


class TurnHost(Protocol):
    """What the runner needs from the web app (registered in the lifespan)."""

    async def get_or_restore(self, sid: str) -> tuple[Any | None, str]: ...

    async def create_web_session(self, agent_name: str, title: str) -> str: ...

    def spawn_turn(self, session: Any, prompt: str, turn_info: dict[str, Any]) -> asyncio.Task: ...

    def mark_silent_and_cancel(self, task: asyncio.Task) -> None: ...

    def discard_silent(self, task: asyncio.Task) -> None: ...

    def mirror_metadata(self, sid: str, key: str, value: Any) -> None: ...

    async def broadcast(self, sid: str, payload: dict[str, Any]) -> None: ...


_host: TurnHost | None = None


def set_turn_host(host: TurnHost | None) -> None:
    global _host
    _host = host


# ── RunRegistry ───────────────────────────────────────────────────────────


class RunRegistry:
    """Owns every runner task (Run now, scheduled and catch-up)."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._closed = False

    def reopen(self) -> None:
        """Accept spawns again (the lifespan calls it at startup)."""
        self._closed = False

    def try_spawn(
        self, routine_id: str, factory: Callable[[], Coroutine[Any, Any, Any]]
    ) -> asyncio.Task | None:
        """Check and add synchronously. ``None`` (and no coroutine created) when running."""
        if self._closed or routine_id in self._tasks:
            return None
        task = asyncio.create_task(factory())
        self._tasks[routine_id] = task
        task.add_done_callback(lambda t: self._finished(routine_id, t))
        return task

    def _finished(self, routine_id: str, task: asyncio.Task) -> None:
        if self._tasks.get(routine_id) is task:
            del self._tasks[routine_id]
        if not task.cancelled() and task.exception() is not None:
            logger.error("routine run %s crashed", routine_id, exc_info=task.exception())

    def is_running(self, routine_id: str) -> bool:
        return routine_id in self._tasks

    async def drain(self, timeout: float = 5.0) -> None:
        self._closed = True  # a Run now after this refuses (leg 5)
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    def reset_for_test(self) -> None:
        self._tasks.clear()
        self._closed = False


registry = RunRegistry()


# ── classify ──────────────────────────────────────────────────────────────


NO_TURN_REASON = "The routine's message was never sent to the agent."
NOT_SAVED_REASON = "The routine's message was not saved to its chat."


async def _message_saved(chats: ChatSessionRepository, sid: str) -> bool:
    """True when the chat's stored messages hold a user message (the routine's prompt)."""
    from the_one.db.codec import decode_messages
    from the_one.llm.base import Role

    try:
        row = await chats.get(sid)
    except KeyError:
        return True  # the chat was deleted meanwhile: nothing to judge
    try:
        return any(m.role == Role.USER for m in decode_messages(row.messages))
    except Exception:  # noqa: BLE001
        return True  # unreadable: do not invent a failure


def _minutes(seconds: float) -> int:
    return max(1, round(seconds / 60))


def _plural_minutes(seconds: float) -> str:
    n = _minutes(seconds)
    return f"{n} minute" if n == 1 else f"{n} minutes"


def classify(
    state: str,
    turn_info: dict[str, Any],
    *,
    timed_out: bool,
    timeout_seconds: float,
) -> tuple[str, str | None]:
    """Map how a run ended to ``(outcome, reason)``. ``state`` is ``done``,
    ``cancelled`` (the turn task was cancelled) or ``interrupted`` (the runner was)."""
    if state == "interrupted":
        return "interrupted", "The app stopped during this run."
    if timed_out:
        return "failed", f"The run took longer than {_plural_minutes(timeout_seconds)}."
    if state == "cancelled" or turn_info.get("cancelled"):
        return "stopped", "Stopped from the chat."
    if turn_info.get("paused"):
        return (
            "failed",
            f"Needs a sign-in to {turn_info['paused']}. "
            "Sign in on its page in Library, then run it again.",
        )
    if turn_info.get("error"):
        return "failed", str(turn_info["error"])
    if not turn_info.get("started"):
        # Fail closed (F-H1-1): a turn that never began has no message and no reply.
        return "failed", NO_TURN_REASON
    if turn_info.get("step_limit"):
        return "ok", "Stopped at the step limit."
    return "ok", None


# ── run_routine ───────────────────────────────────────────────────────────


async def _finish_row(runs: RoutineRunRepository, run_id: str, *args: Any, **kw: Any) -> None:
    try:
        await runs.finish(run_id, *args, **kw)
    except Exception:
        logger.warning("could not finish routine run %s", run_id, exc_info=True)


async def _fail_early(
    runs: RoutineRunRepository,
    routine: Routine,
    trigger_kind: str,
    due_at: str | None,
    outcome: str,
    reason: str,
) -> None:
    try:
        row = await runs.insert(
            RoutineRun(
                routine_id=routine.id,
                trigger_kind=trigger_kind,  # type: ignore[arg-type]
                outcome=outcome,  # type: ignore[arg-type]
                reason=reason,
                due_at=due_at,
                finished_at=_now_iso(),
            )
        )
        logger.info(
            "routine run=%s routine=%s agent=%r session=none trigger=%s outcome=%s reason=%r",
            row.id,
            routine.id,
            routine.agent_name,
            trigger_kind,
            outcome,
            reason,
        )
    except Exception:
        logger.warning("could not record routine run for %s", routine.id, exc_info=True)


async def run_routine(routine_id: str, trigger_kind: str, due_at: str | None = None) -> None:
    host = _host
    if host is None:
        logger.warning("routine run %s: no turn host registered", routine_id)
        return
    conn = await get_connection()
    routines = AgentRoutineRepository(conn)
    runs = RoutineRunRepository(conn)
    chats = ChatSessionRepository(conn)

    routine = await routines.get_by_id(routine_id)
    if routine is None:
        return

    # 1. Every run starts a new web chat titled with the routine's name.
    try:
        sid = await host.create_web_session(routine.agent_name, routine.name)
    except Exception:
        logger.warning("routine %s: could not create its chat", routine_id, exc_info=True)
        await _fail_early(
            runs, routine, trigger_kind, due_at, "failed", "Couldn't find or create the chat."
        )
        return

    # 2. Insert the running row.
    try:
        run = await runs.insert(
            RoutineRun(
                routine_id=routine_id,
                trigger_kind=trigger_kind,  # type: ignore[arg-type]
                due_at=due_at,
                session_id=sid,
            )
        )
    except Exception:
        logger.warning("routine %s: could not record its run", routine_id, exc_info=True)
        return

    logger.info(
        "routine run=%s routine=%s agent=%r session=%s trigger=%s started",
        run.id,
        routine_id,
        routine.agent_name,
        sid,
        trigger_kind,
    )

    async def end(outcome: str, reason: str | None) -> None:
        await _finish_row(runs, run.id, outcome, reason, sid)
        logger.info(
            "routine run=%s routine=%s agent=%r session=%s trigger=%s outcome=%s reason=%r",
            run.id,
            routine_id,
            routine.agent_name,
            sid,
            trigger_kind,
            outcome,
            reason,
        )

    # 3. Restore.
    session, status = await host.get_or_restore(sid)
    if session is None:
        if status == "provider_missing":
            await end("failed", "The agent's model provider is missing.")
        elif status == "agent_deleted":
            await end("failed", "The agent no longer exists.")
        elif status == "build_failed":
            await end(
                "failed",
                "The agent could not be set up. Check the agent's settings; "
                "the app log has the details.",
            )
        else:
            await end("failed", "The chat is no longer available.")
        return

    # 4. turn_info, 5. spawn.
    turn_info: dict[str, Any] = {
        "routine": {
            "id": routine.id,
            "name": routine.name,
            # M33 F2 L3 (DD7): the flag at run time. The turn's context and the saved
            # message snapshot both read it, so later edits of the routine change neither.
            "untrusted_sources": list(routine.untrusted_sources) if routine.untrusted else [],
        }
    }
    task = host.spawn_turn(session, routine.prompt, turn_info)
    timeout = routine_run_timeout_seconds()
    timed_out = False
    try:
        # 6. Wait and classify.
        done, _ = await asyncio.wait({task}, timeout=timeout)
        if not done:
            timed_out = True
            if turn_info.get("started"):
                task.cancel()
            else:
                host.mark_silent_and_cancel(task)
            await asyncio.wait({task}, timeout=_CANCEL_WAIT_SECONDS)
        state = "done"
        if task.done():
            if task.cancelled():
                state = "cancelled"
            elif task.exception() is not None:
                logger.warning("routine %s: turn crashed", routine_id, exc_info=task.exception())
                turn_info.setdefault("error", "An error occurred while running the routine.")
        else:
            state = "cancelled"
        outcome, reason = classify(
            state,
            turn_info,
            timed_out=timed_out,
            timeout_seconds=timeout,
        )
        await _post_steps(host, chats, routine, sid, turn_info)
        if outcome == "ok" and not await _message_saved(chats, sid):
            outcome, reason = "failed", NOT_SAVED_REASON
        await end(outcome, reason)
    except asyncio.CancelledError:
        # The runner itself was cancelled (drain or shutdown).
        if not task.done():
            if turn_info.get("started"):
                task.cancel()
            else:
                host.mark_silent_and_cancel(task)
        with contextlib.suppress(Exception):
            await asyncio.wait({task}, timeout=_INTERRUPT_WAIT_SECONDS)
        with contextlib.suppress(Exception):
            await _post_steps(host, chats, routine, sid, turn_info)
        outcome, reason = classify("interrupted", turn_info, timed_out=False, timeout_seconds=0)
        await end(outcome, reason)
        raise
    finally:
        host.discard_silent(task)


async def _post_steps(
    host: TurnHost,
    chats: ChatSessionRepository,
    routine: Routine,
    sid: str,
    turn_info: dict[str, Any],
) -> None:
    """After the lock is released, for a run whose turn started. Each step is
    idempotent and tolerates a deleted chat."""
    if not turn_info.get("started"):
        return
    when = now_iso()
    value = {"id": routine.id, "name": routine.name, "last_run_at": when}
    try:
        await chats.set_session_metadata_key(sid, "routine", value)
        host.mirror_metadata(sid, "routine", value)
    except KeyError:
        logger.info("routine chat %s is gone; skipped its metadata", sid)
    except Exception:
        logger.warning("routine metadata write failed for %s", sid, exc_info=True)
    try:
        await host.broadcast(sid, {"type": "session_updated", "session_id": sid})
    except Exception:
        logger.warning("session_updated broadcast failed for %s", sid, exc_info=True)
