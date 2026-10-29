"""The agent-facing routine tools (Mission 33 Flight 2 Leg 3, DD1/DD2/DD7/DD8/DD9).

Four native tools let an agent whose Routines item is on schedule its own follow-ups.
Every write goes through :func:`the_one.routines.service.agent_change`, which owns the
call-time switch check, validation, caps, the proposals record and the flag merge; these
tools add only the turn context, the untrusted-content flag (``compute_taint``), the
per-turn write counter, argument coercion and the result wording.

DD7: a write tool echoes only the routine id and the text the agent itself passed, never a
stored name or prompt, and ``describe.py`` never emits a chat title, so a trusted tool's
result can never carry planted text. ``list_my_routines`` is the one tool that returns
stored text; it puts ``FLAGGED_CONTENT_MARK`` on its first line when anything it lists is
flagged, and ``compute_taint`` reads that sentinel from the stored result.

Refusals RAISE ``ValueError`` (the loop turns that into an error result).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from the_one import time_zones
from the_one.agent._context import current_chat_session_id, current_tool_call_id, current_turn
from the_one.agent.taint import FLAGGED_CONTENT_MARK, compute_taint
from the_one.agent.tool_names import (
    CANCEL_ROUTINE_TOOL_NAME,
    CHANGE_ROUTINE_TOOL_NAME,
    LIST_ROUTINES_TOOL_NAME,
    SCHEDULE_ROUTINE_TOOL_NAME,
)
from the_one.naming import NameRuleError
from the_one.routines import service
from the_one.routines.describe import describe_next, describe_schedule, describe_target
from the_one.routines.limits import (
    AGENT_ACTIVE_ROUTINES_MAX,
    AGENT_ROUTINE_WRITES_PER_TURN,
    AGENT_RUNS_PER_DAY_MAX,
    RoutineFieldError,
    RoutineLimitError,
    RoutineNameTaken,
    RoutineScheduleError,
)
from the_one.routines.proposals import RoutineProposalRepository
from the_one.routines.repository import AgentRoutineRepository
from the_one.tools.base import Tool

if TYPE_CHECKING:
    from the_one.agent._context import TurnContext
    from the_one.agent.core import Agent

NO_TURN_REFUSAL = "Routine changes need a chat turn."
BUDGET_REFUSAL = (
    f"Routine change limit for this turn reached ({AGENT_ROUTINE_WRITES_PER_TURN} changes)."
)
NO_CHAT_REFUSAL = "There's no chat to target here; use new_chat or own_chat."
SHAPE_REFUSAL = "That isn't in the expected shape; pass it as an object, not text."
TARGET_REFUSAL = 'The target must be "this_chat", "new_chat", "own_chat" or {"chat_id": "..."}.'
MAX_JSON_ARG_CHARS = 2000
FLAGGED_NOTE = " It was flagged for your operator to check."

_LIMITS_SENTENCE = (
    f"At most {AGENT_ACTIVE_ROUTINES_MAX} active routines, {AGENT_RUNS_PER_DAY_MAX} runs a day "
    f"and {AGENT_ROUTINE_WRITES_PER_TURN} changes a turn. Your operator may need to approve."
)
_TIMES = "Times are wall-clock in the operator's time zone."
_SCHEDULE_SHAPES = (
    '{"kind":"once","in":{"amount":N,"unit":"minutes|hours|days"}}, '
    '{"kind":"once","on":{"date":"YYYY-MM-DD","time":"HH:MM"}}, '
    '{"kind":"daily"|"weekdays","time":"HH:MM"}, '
    '{"kind":"weekly","days":[0-6, 0 is Monday],"time":"HH:MM"} or '
    '{"kind":"interval","hours":N}.'
)
_TARGET_SHAPES = (
    '"this_chat" (default), "new_chat", "own_chat" or {"chat_id": "<one of your chats>"}.'
)

_SCHEDULE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "When to run. " + _SCHEDULE_SHAPES,
}
_TARGET_SCHEMA: dict[str, Any] = {
    "type": ["string", "object"],
    "description": "Where it runs: " + _TARGET_SHAPES,
}


def echo_name(name: Any) -> str:
    """The name as the agent passed it: trimmed, cut at 64 characters with an ellipsis."""
    text = str(name).strip()
    return text if len(text) <= 64 else text[:64] + "…"


def _json_arg(value: Any) -> Any:
    """A weak model may pass an object as JSON text; accept a short string that parses
    as a JSON object, otherwise refuse."""
    if not isinstance(value, str):
        return value
    if len(value) > MAX_JSON_ARG_CHARS:
        raise ValueError(SHAPE_REFUSAL)
    try:
        parsed = json.loads(value)
    except ValueError:
        raise ValueError(SHAPE_REFUSAL) from None
    if not isinstance(parsed, dict):
        raise ValueError(SHAPE_REFUSAL)
    return parsed


def coerce_schedule(value: Any) -> Any:
    return _json_arg(value)


def coerce_target(value: Any) -> dict[str, Any]:
    """Map the tool target onto the REST ``{kind, session_id}`` body (the session id of
    ``this_chat`` is resolved by the caller)."""
    if isinstance(value, str) and value.strip().startswith("{"):
        value = _json_arg(value)
    if isinstance(value, str):
        key = value.strip().lower()
        if key == "this_chat":
            return {"kind": "chat", "session_id": None, "_this": True}
        if key == "new_chat":
            return {"kind": "new"}
        if key == "own_chat":
            return {"kind": "own"}
        raise ValueError(TARGET_REFUSAL)
    if isinstance(value, dict) and set(value) == {"chat_id"} and isinstance(value["chat_id"], str):
        return {"kind": "chat", "session_id": value["chat_id"].strip()}
    raise ValueError(TARGET_REFUSAL)


def coerce_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise ValueError("enabled must be true or false.")


class _RoutineToolBase(Tool):
    parameters: dict[str, Any]

    def __init__(self, agent_name: str | None) -> None:
        super().__init__(agent_name=agent_name)
        self._agent: Agent | None = None

    def bind_agent(self, agent: Agent) -> None:
        """Bind the owning Agent (the factory calls this after construction). An unbound
        tool fails closed: every write is flagged "unknown position"."""
        self._agent = agent

    def _name(self) -> str:
        if not self._agent_name:
            raise ValueError("Routines are unavailable: this tool is not attached to an agent.")
        return self._agent_name

    @staticmethod
    async def _conn() -> Any:
        from the_one.db.connection import get_connection

        return await get_connection()

    # -- the per-turn counter (DD8): no fallback without a TurnContext ----------

    @staticmethod
    def _turn_for_write() -> TurnContext:
        turn = current_turn.get()
        if turn is None:
            raise ValueError(NO_TURN_REFUSAL)
        if turn.routine_writes >= AGENT_ROUTINE_WRITES_PER_TURN:
            raise ValueError(BUDGET_REFUSAL)
        return turn

    @staticmethod
    def _count_write(turn: TurnContext) -> None:
        turn.routine_writes += 1  # mutate, never set (the notes rule)

    @staticmethod
    def _session_id(turn: TurnContext) -> str | None:
        return turn.session_id or current_chat_session_id.get()

    def _resolve_target(self, raw: Any, session_id: str | None) -> dict[str, Any]:
        body = coerce_target(raw)
        if body.pop("_this", False):
            if not session_id:
                raise ValueError(NO_CHAT_REFUSAL)
            body["session_id"] = session_id
        return body

    async def _change(
        self,
        action: str,
        data: dict[str, Any],
        turn: TurnContext,
        session_id: str | None,
    ) -> tuple[service.AgentChangeResult, bool, Any]:
        """Run one write through ``agent_change``; map its typed errors to one sentence.
        Returns ``(result, flagged, tzinfo)``."""
        name = self._name()
        conn = await self._conn()
        untrusted, sources = compute_taint(self._agent, current_tool_call_id.get(), turn)
        eff = await time_zones.load_effective_zone(conn)

        async def zone() -> Any:
            return eff.tzinfo

        try:
            result = await service.agent_change(
                conn,
                name,
                action,  # type: ignore[arg-type]
                data,
                now=time_zones.utcnow(),
                zone=zone,
                taint=(untrusted, sources),
                session_id=session_id,
            )
        except (RoutineFieldError, NameRuleError) as e:
            raise ValueError(e.message) from None
        except (RoutineScheduleError, RoutineLimitError, RoutineNameTaken) as e:
            raise ValueError(e.detail) from None
        self._count_write(turn)
        return result, untrusted, eff.tzinfo


class ListMyRoutinesTool(_RoutineToolBase):
    name = LIST_ROUTINES_TOOL_NAME
    description = (
        "List your routines (scheduled follow-ups) and any changes waiting for your "
        "operator's approval. Listing a flagged routine marks what follows as needing "
        "your operator's check."
    )
    parameters: dict[str, Any] = {"type": "object", "properties": {}}
    truncation_direction = "head"

    async def execute(self) -> str:
        name = self._name()
        conn = await self._conn()
        try:
            await service.require_routine_tools_on(conn, name)
        except RoutineFieldError as e:
            raise ValueError(e.message) from None
        turn = current_turn.get()
        session_id = (
            turn.session_id if turn is not None else None
        ) or current_chat_session_id.get()
        eff = await time_zones.load_effective_zone(conn)
        zone = eff.tzinfo
        now = time_zones.utcnow()
        routines = await AgentRoutineRepository(conn).list_for_agent(name)
        pending = await RoutineProposalRepository(conn).list(name, status="pending", limit=50)
        if not routines and not pending:
            return "You have no routines."
        flagged = any(r.untrusted for r in routines) or any(p.untrusted for p in pending)
        lines: list[str] = [FLAGGED_CONTENT_MARK] if flagged else []
        for r in routines:
            if r.finished_at is not None:
                state = "done"
            else:
                state = "on" if r.enabled else "off"
            made = "you" if r.created_by == "agent" else "your operator"
            lines.append(f"Routine '{r.name}' (id {r.id}), made by {made}, {state}.")
            lines.append(f"  Schedule: {describe_schedule(r.schedule, zone)}.")
            if r.finished_at is None and r.enabled:
                lines.append(f"  Next run: {describe_next(r.next_run_at, zone, now=now)}.")
            lines.append(f"  Runs in: {describe_target(r, session_id)}.")
            if r.untrusted:
                srcs = ", ".join(r.untrusted_sources) or "unknown"
                lines.append(f"  Flagged for your operator to check (sources: {srcs}).")
            lines.append(f"  Prompt: {r.prompt}")
        for p in pending:
            lines.append(f"Waiting for approval: {_proposal_words(p, zone, session_id, now)}")
            if p.untrusted:
                srcs = ", ".join(p.untrusted_sources) or "unknown"
                lines.append(f"  Flagged for your operator to check (sources: {srcs}).")
        return "\n".join(lines)


def _proposal_words(p: Any, zone: Any, session_id: str | None, now: Any) -> str:
    payload = p.payload or {}
    label = f"'{p.routine_name}'"
    if p.action == "delete":
        return f"cancel routine {label}."
    if p.action == "create":
        bits = []
        if "schedule" in payload:
            bits.append(describe_schedule(payload["schedule"], zone))
        if "target" in payload:
            bits.append("in " + describe_target(payload, session_id))
        if payload.get("enabled") is False:
            bits.append("starting off")
        prompt = payload.get("prompt")
        tail = f" Prompt: {prompt}" if prompt else ""
        return f"create routine {label}" + (f" ({', '.join(bits)})." if bits else ".") + tail
    changes = []
    if "name" in payload:
        changes.append(f"rename to '{payload['name']}'")
    if "prompt" in payload:
        changes.append(f"new prompt: {payload['prompt']}")
    if "schedule" in payload:
        changes.append(f"schedule {describe_schedule(payload['schedule'], zone)}")
    if "target" in payload:
        changes.append("run in " + describe_target(payload, session_id))
    if "enabled" in payload:
        changes.append("turn on" if payload["enabled"] else "turn off")
    return f"change routine {label}: " + "; ".join(changes or ["no fields"]) + "."


class ScheduleRoutineTool(_RoutineToolBase):
    name = SCHEDULE_ROUTINE_TOOL_NAME
    description = (
        "Schedule a prompt to run later, for a follow-up the person asked for or one you "
        "need (such as checking back on something). "
        + _TIMES
        + " Schedule: "
        + _SCHEDULE_SHAPES
        + " "
        + _LIMITS_SENTENCE
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "A short name, unique among your routines."},
            "prompt": {"type": "string", "description": "What to do when it runs."},
            "schedule": _SCHEDULE_SCHEMA,
            "target": _TARGET_SCHEMA,
            "enabled": {"type": "boolean", "description": "Start on (default true)."},
        },
        "required": ["name", "prompt", "schedule"],
    }

    async def execute(
        self,
        name: Any,
        prompt: Any,
        schedule: Any,
        target: Any = "this_chat",
        enabled: Any = True,
    ) -> str:
        turn = self._turn_for_write()
        session_id = self._session_id(turn)
        data = {
            "name": name,
            "prompt": prompt,
            "schedule": coerce_schedule(schedule),
            "target": self._resolve_target(target, session_id),
            "enabled": coerce_enabled(enabled),
        }
        result, flagged, zone = await self._change("create", data, turn, session_id)
        label = echo_name(name)
        if result.pending:
            return f"Asked your operator to approve '{label}'. It won't run until they do."
        r = result.routine
        text = (
            f"Scheduled '{label}' (id {r.id}) for "
            f"{describe_next(r.next_run_at, zone)} in {describe_target(r, session_id)}."
        )
        return text + (FLAGGED_NOTE if flagged else "")


class ChangeRoutineTool(_RoutineToolBase):
    name = CHANGE_ROUTINE_TOOL_NAME
    description = (
        "Change one of your routines, by name or id. Pass only what changes. "
        + _TIMES
        + " Schedule: "
        + _SCHEDULE_SHAPES
        + " "
        + _LIMITS_SENTENCE
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "routine": {"type": "string", "description": "The routine's name or id."},
            "name": {"type": "string", "description": "A new name."},
            "prompt": {"type": "string", "description": "A new prompt."},
            "schedule": _SCHEDULE_SCHEMA,
            "target": _TARGET_SCHEMA,
            "enabled": {"type": "boolean", "description": "Turn it on or off."},
        },
        "required": ["routine"],
    }

    async def execute(
        self,
        routine: Any,
        name: Any = None,
        prompt: Any = None,
        schedule: Any = None,
        target: Any = None,
        enabled: Any = None,
    ) -> str:
        turn = self._turn_for_write()
        session_id = self._session_id(turn)
        data: dict[str, Any] = {"routine": routine}
        if name is not None:
            data["name"] = name
        if prompt is not None:
            data["prompt"] = prompt
        if schedule is not None:
            data["schedule"] = coerce_schedule(schedule)
        if target is not None:
            data["target"] = self._resolve_target(target, session_id)
        if enabled is not None:
            data["enabled"] = coerce_enabled(enabled)
        if len(data) == 1:
            raise ValueError("Say what to change.")
        result, flagged, _zone = await self._change("update", data, turn, session_id)
        if result.pending:
            text = (
                f"Asked your operator to approve the change to routine {result.routine_id}. "
                "It won't take effect until they do."
            )
            if result.replaced:
                text += " This replaces your earlier pending change to that routine."
            return text
        return f"Changed routine {result.routine_id}." + (FLAGGED_NOTE if flagged else "")


class CancelRoutineTool(_RoutineToolBase):
    name = CANCEL_ROUTINE_TOOL_NAME
    description = (
        "Cancel (delete) one of your routines, by name or id. Your operator may need to approve."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"routine": {"type": "string", "description": "The routine's name or id."}},
        "required": ["routine"],
    }

    async def execute(self, routine: Any) -> str:
        turn = self._turn_for_write()
        session_id = self._session_id(turn)
        result, _flagged, _zone = await self._change(
            "delete", {"routine": routine}, turn, session_id
        )
        if result.pending:
            return (
                f"Asked your operator to approve cancelling routine {result.routine_id}. "
                "It stays until they do."
            )
        return f"Cancelled routine {result.routine_id}."
