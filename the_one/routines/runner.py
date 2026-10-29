"""Run one routine unattended (Mission 33 F1 leg 4, DD6, DD8, DD9).

``run_routine`` pre-checks a connector target, resolves the target chat, honours
a chat paused for a sign-in, spawns the routine turn through the registered
``TurnHost`` (the web app implements it, so this package never imports
``interfaces/``), bounds the run with a time limit, classifies how it ended and
updates the chat and the run row once the session lock is released.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, Protocol

from the_one.config import settings
from the_one.connectors.base import keying_to_target
from the_one.connectors.delivery import authorized_agent_for
from the_one.connectors.inbound import _resolve_continuation_seconds, is_continuable
from the_one.connectors.manager import get_manager
from the_one.db.connection import get_connection
from the_one.db.models import ChatSession, now_iso
from the_one.db.repositories import ChatSessionRepository, ConnectorRepository
from the_one.encryption import get_encryptor
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

NEW_CHAT_GONE = "The chosen chat was gone, so this run started a new chat."


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

    def peek_session(self, sid: str) -> Any | None: ...

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
    """Owns every runner task (Run now, scheduled and catch-up) and the memory of
    which chat each routine's own run left paused."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._pauses: dict[str, str] = {}
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

    def remember_pause(self, routine_id: str, sid: str) -> None:
        self._pauses[routine_id] = sid

    def own_pause(self, routine_id: str) -> str | None:
        return self._pauses.get(routine_id)

    def clear_pause(self, routine_id: str) -> None:
        self._pauses.pop(routine_id, None)

    async def drain(self, timeout: float = 5.0) -> None:
        self._closed = True  # a Run now after this refuses (leg 5)
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    def reset_for_test(self) -> None:
        self._tasks.clear()
        self._pauses.clear()
        self._closed = False


registry = RunRegistry()


# ── classify ──────────────────────────────────────────────────────────────


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
    connector_name: str | None = None,
) -> tuple[str, str | None]:
    """Map how a run ended to ``(outcome, reason)``. ``state`` is ``done``,
    ``cancelled`` (the turn task was cancelled) or ``interrupted`` (the runner was)."""
    if state == "interrupted":
        return "interrupted", "The app stopped during this run."
    if timed_out:
        if not turn_info.get("started"):
            return "skipped", f"The chat stayed busy for {_plural_minutes(timeout_seconds)}."
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
    delivery = turn_info.get("delivery")
    status = getattr(delivery, "status", None)
    if status in ("send_failed", "no_client"):
        who = connector_name or "the connector"
        why = getattr(delivery, "error", None) or "not connected"
        return "failed", f"Couldn't send to {who}: {why}."
    if status == "no_text":
        return "ok", "The agent gave no reply to send."
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
        await runs.insert(
            RoutineRun(
                routine_id=routine.id,
                trigger_kind=trigger_kind,  # type: ignore[arg-type]
                outcome=outcome,  # type: ignore[arg-type]
                reason=reason,
                due_at=due_at,
                finished_at=_now_iso(),
            )
        )
    except Exception:
        logger.warning("could not record routine run for %s", routine.id, exc_info=True)


async def _resolve_target(
    routine: Routine,
    connector: Any | None,
    chats: ChatSessionRepository,
    host: TurnHost,
) -> tuple[ChatSession, bool, str | None]:
    """DD8: the stored chat row this run uses, whether it was created, and a note."""

    async def existing(sid: str | None, *, agent_must_match: bool) -> ChatSession | None:
        if not sid:
            return None
        try:
            row = await chats.get(sid)
        except KeyError:
            return None
        if agent_must_match and row.agent_name != routine.agent_name:
            return None
        return row

    async def new_web_chat() -> ChatSession:
        sid = await host.create_web_session(routine.agent_name, routine.name)
        return await chats.get(sid)

    kind = routine.target_kind
    if connector is not None and kind == "chat":
        prev = await chats.find_most_recent_by_external_key(
            platform=routine.target_platform or "",
            connector_id=routine.target_connector_id or "",
            channel_id=routine.target_channel_id or "",
            thread_id=routine.target_thread_id,
        )
        from datetime import datetime, timezone

        seconds = _resolve_continuation_seconds(connector.session_continuation_seconds)
        if (
            prev is not None
            and prev.agent_name == routine.agent_name
            and is_continuable(prev, seconds, datetime.now(timezone.utc))
        ):
            return prev, False, None
        stamp = now_iso()
        row = ChatSession(
            id=uuid.uuid4().hex,
            agent_name=routine.agent_name,
            title=(prev.title if prev is not None else None)
            or routine.target_channel_id
            or routine.name,
            messages="[]",
            created_at=stamp,
            updated_at=stamp,
            platform=routine.target_platform,
            connector_id=routine.target_connector_id,
            channel_id=routine.target_channel_id,
            thread_id=routine.target_thread_id,
            peer_id=routine.target_peer_id,
            session_metadata=None,
            last_inbound_at=stamp,
        )
        await chats.create(row)
        return await chats.get(row.id), True, None
    if kind == "chat":
        row = await existing(routine.target_session_id, agent_must_match=True)
        if row is not None:
            return row, False, None
        return await new_web_chat(), True, NEW_CHAT_GONE
    if kind == "own":
        row = await existing(routine.target_session_id, agent_must_match=False)
        if row is not None:
            return row, False, None
        return await new_web_chat(), True, None
    return await new_web_chat(), True, None  # "new"


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

    # 1. Pre-checks (a connector target), before any chat is created.
    connector = None
    if routine.target_connector_id:
        try:
            connector = await ConnectorRepository(conn, get_encryptor(settings.data_dir)).get(
                routine.target_connector_id
            )
        except KeyError:
            connector = None
        manager = get_manager()
        if connector is None or manager is None or manager.client_for(connector.id) is None:
            name = connector.name if connector is not None else routine.target_connector_id
            await _fail_early(
                runs, routine, trigger_kind, due_at, "failed", f"{name} isn't connected."
            )
            return
        authorized = authorized_agent_for(connector, channel_id=routine.target_channel_id)
        if authorized != routine.agent_name:
            where = routine.target_channel_id or "This channel"
            await _fail_early(
                runs,
                routine,
                trigger_kind,
                due_at,
                "failed",
                f"{where} is now answered by {authorized or 'no agent'}.",
            )
            return

    # 2. Target resolution.
    try:
        row, new_chat, note = await _resolve_target(routine, connector, chats, host)
    except Exception:
        logger.warning("routine %s: could not resolve its chat", routine_id, exc_info=True)
        await _fail_early(
            runs, routine, trigger_kind, due_at, "failed", "Couldn't find or create the chat."
        )
        return
    sid = row.id
    if routine.target_session_id != sid:
        await routines.set_target_session(routine_id, sid)

    # 3. Insert the running row.
    try:
        run = await runs.insert(
            RoutineRun(
                routine_id=routine_id,
                trigger_kind=trigger_kind,  # type: ignore[arg-type]
                due_at=due_at,
                session_id=sid,
                new_chat=new_chat,
            )
        )
    except Exception:
        logger.warning("routine %s: could not record its run", routine_id, exc_info=True)
        return

    async def end(outcome: str, reason: str | None) -> None:
        await _finish_row(runs, run.id, outcome, reason, sid, new_chat)

    # 4. The paused peek, before any restore.
    cached = host.peek_session(sid)
    if (
        cached is not None
        and getattr(cached.agent, "_deferred_tool_calls", None) is not None
        and registry.own_pause(routine_id) != sid
    ):
        await end("skipped", "The chat is waiting for a sign-in.")
        return
    registry.clear_pause(routine_id)

    # 5. Restore.
    session, status = await host.get_or_restore(sid)
    if session is None:
        if status == "provider_missing":
            await end("failed", "The agent's model provider is missing.")
        elif status == "agent_deleted":
            await end("failed", "The agent no longer exists.")
        else:
            await end("failed", "The chat is no longer available.")
        return

    # 6. turn_info, 7. spawn.
    turn_info: dict[str, Any] = {
        "routine": {
            "id": routine.id,
            "name": routine.name,
            "target": keying_to_target(row),
            "connector_id": row.connector_id,
            # M33 F2 L3 (DD7): the flag at run time. The turn's context and the saved
            # message snapshot both read it, so later edits of the routine change neither.
            "untrusted_sources": list(routine.untrusted_sources) if routine.untrusted else [],
        }
    }
    task = host.spawn_turn(session, routine.prompt, turn_info)
    timeout = routine_run_timeout_seconds()
    timed_out = False
    try:
        # 8. Wait and classify.
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
            connector_name=connector.name if connector is not None else None,
        )
        if outcome == "failed" and turn_info.get("paused"):
            registry.remember_pause(routine_id, sid)
        await _post_steps(host, chats, routine, sid, turn_info, outcome)
        if note:
            reason = f"{reason} {note}" if reason else note
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
            await _post_steps(host, chats, routine, sid, turn_info, "interrupted")
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
    outcome: str,
) -> None:
    """After the lock is released, for a run whose turn started. Each step is
    idempotent and tolerates a deleted chat."""
    if not turn_info.get("started"):
        return
    when = now_iso()
    status = getattr(turn_info.get("delivery"), "status", None)
    if status in ("delivered", "already_sent"):
        try:
            await chats.update_last_inbound(sid, when)
        except KeyError:
            logger.info("routine chat %s is gone; skipped last_inbound update", sid)
        except Exception:
            logger.warning("last_inbound update failed for %s", sid, exc_info=True)
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
