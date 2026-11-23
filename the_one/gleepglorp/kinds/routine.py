"""The ``routine`` kind: add or change one of an agent's routines (M36 F4 L1a, DD2)."""

from __future__ import annotations

import json
from datetime import datetime, tzinfo
from typing import Any

import aiosqlite

from the_one.gleepglorp.kinds.agent import existing_agent
from the_one.gleepglorp.kinds.base import Kind, changed_labels
from the_one.gleepglorp.kinds.deps import KindDeps
from the_one.gleepglorp.kinds.errors import reraise
from the_one.gleepglorp.proposals.shape import (
    FieldSpec,
    Normalized,
    ShapeError,
    _bad,
    _check_schedule,
    _q,
)
from the_one.gleepglorp.proposals.store import Proposal
from the_one.naming import NameRuleError, check_name
from the_one.routines import recurrence
from the_one.routines import service as routine_service
from the_one.routines.describe import schedule_sentence
from the_one.routines.limits import RoutineFieldError
from the_one.routines.repository import AgentRoutineRepository, Flag

#: One weekday schedule (Monday to Friday at 08:00); the date is a placeholder the model replaces.
#: A test round-trips it (with a real date) through the routine service's schedule validation.
SCHEDULE_EXAMPLE: dict[str, Any] = {
    "start": {"date": "YYYY-MM-DD", "time": "08:00"},
    "repeat": {"every": 1, "unit": "week", "days": [0, 1, 2, 3, 4]},
}


def _schedule_hint() -> str:
    """The full canonical schedule shape, built from the recurrence module's own constants."""
    units = "|".join(recurrence.UNITS)
    nth = ", ".join(str(n) for n in recurrence.NTH_VALUES)
    rel = "|".join(recurrence._REL_UNITS)
    return (
        'start: {date: "YYYY-MM-DD", time: "HH:MM"} or {in: {amount, unit: '
        f"{rel}}}}}; repeat (omit for once): {{every: N, unit: {units}, "
        "days: [0-6, 0 = Monday] (required for week only), "
        f"month_by: {{by: day}} or {{by: weekday, nth: {nth}}} (month only)}}; "
        "ends (default never): {kind: never} or {kind: on, date} or {kind: after, count}. "
        f"Weekdays at 8: {json.dumps(SCHEDULE_EXAMPLE)}"
    )


ROUTINE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", "text", "Name", "name", create_required=True),
    FieldSpec("prompt", "text", "Prompt", "prompt", create_required=True),
    FieldSpec(
        "schedule",
        "schedule",
        "Schedule",
        "schedule",
        hint=_schedule_hint(),
        create_required=True,
    ),
    FieldSpec("enabled", "boolean", "On", "enabled"),
)


async def normalize(
    action: str,
    target: dict[str, Any],
    changes: dict[str, Any],
    *,
    conn: Any,
    now: datetime,
    zone: tzinfo,
    enc: Any = None,
    mode: str = "propose",
) -> Normalized:
    agent = await existing_agent(conn, target.get("agent"))
    repo = AgentRoutineRepository(conn)
    stored: dict[str, Any] = {}
    for f in ROUTINE_FIELDS:
        if f.name not in changes:
            continue
        value = changes[f.name]
        if f.name == "name":
            try:
                stored["name"] = check_name(value)
            except NameRuleError as e:
                raise ShapeError(e.message) from None
        elif f.name == "prompt":
            try:
                stored["prompt"] = routine_service.validate_prompt(value)
            except RoutineFieldError as e:
                raise ShapeError(e.message) from None
        elif f.name == "schedule":
            stored.update(_check_schedule(f, value, now, zone))
        else:
            if not isinstance(value, bool):
                raise _bad(f, "true or false")
            stored["enabled"] = value
    if action == "create":
        if await repo.get_by_name(agent, stored["name"]) is not None:
            raise ShapeError(f"{agent} already has a routine named {stored['name']}.")
        return Normalized(
            "routine",
            "create",
            agent,
            None,
            f"routine:{agent}:new:{stored['name']}",
            stored,
            None,
        )
    rname = target.get("routine")
    if not isinstance(rname, str) or not rname.strip():
        raise ShapeError("Say which routine: give routine, its name.")
    routine = await repo.get_by_name(agent, rname.strip())
    if routine is None:
        raise ShapeError(f"{agent} has no routine named {_q(rname.strip())}.")
    if "name" in stored:
        other = await repo.get_by_name(agent, stored["name"])
        if other is not None and other.id != routine.id:
            raise ShapeError(f"{agent} already has a routine named {stored['name']}.")
    base: dict[str, Any] = {}
    for f in stored:
        base[f] = getattr(routine, f)
    return Normalized(
        "routine", "change", agent, routine.id, f"routine:{agent}:{routine.id}", stored, base
    )


async def exists(conn: aiosqlite.Connection, deps: KindDeps, p: Proposal) -> bool:
    if not p.agent_name or not await deps.agent.store.exists(p.agent_name):
        return False
    if p.action == "create":
        return True
    return (
        p.target_id is not None
        and await AgentRoutineRepository(conn).get(p.agent_name, p.target_id) is not None
    )


def _sched(changes: dict[str, Any]) -> dict[str, Any]:
    return {"schedule": changes["schedule"]} if "schedule" in changes else {}


async def apply(
    conn: aiosqlite.Connection,
    deps: KindDeps,
    p: Proposal,
    *,
    changes: dict[str, Any],
    base: dict[str, Any],
    override: bool,
    now: datetime,
    zone: Any,
    mark: Any,
    runner: Any,
    result: dict[str, Any],
) -> str | None:
    """Run a routine create or change through the routine service as the operator would
    (``created_by="operator"``, no agent caps); the stored schedule pair is passed so the
    schedule is not re-derived. An untrusted proposal's flag is carried onto the routine.
    ``runner`` marks the proposal applied inside the routine write's transaction. Returns
    the routine's name as proposed (``None`` if the change did not rename it)."""
    try:
        assert p.agent_name is not None
        repo = AgentRoutineRepository(conn)
        flag: Flag = ("merge", list(p.untrusted_sources)) if p.untrusted else None
        data: dict[str, Any] = {
            k: changes[k] for k in ("name", "prompt", "enabled") if k in changes
        }
        pair = (
            await routine_service.approval_pair(
                {"schedule": changes["schedule"], "anchor_at": changes.get("anchor_at")}, zone
            )
            if "schedule" in changes
            else None
        )
        if p.action == "create":
            data.setdefault("enabled", True)
            await routine_service.create_routine(
                repo,
                p.agent_name,
                data,
                now=now,
                zone=zone,
                created_by="operator",
                agent_caps=False,
                flag=flag,
                proposal=runner,
                schedule_pair=pair,
            )
            return changes.get("name")
        assert p.target_id is not None
        current = await repo.get(p.agent_name, p.target_id)
        if current is None:
            raise KeyError(p.target_id)
        result["routine"] = data.get("name", current.name)
        touched = [
            k
            for k in routine_service._touched_base_keys("update", data | _sched(changes))
            if k in base
        ]
        precheck = routine_service.stale_precheck_for(base, touched, override, changes)
        await routine_service.update_routine(
            repo,
            p.agent_name,
            current,
            data,
            now=now,
            zone=zone,
            flag=flag,
            proposal=runner,
            precheck=precheck,
            schedule_pair=pair,
        )
        return changes.get("name")
    except Exception as exc:  # noqa: BLE001 - translated, or re-raised unchanged
        await reraise(exc, p, conn=conn, zone=zone)


async def summary_text(p: Proposal, zone: Any) -> dict[str, Any]:
    labels = changed_labels(ROUTINE_FIELDS, p)
    agent = p.agent_name or ""
    name = p.changes.get("name")
    sentence: str | None = None
    tz = await zone()
    if "schedule" in p.changes:
        sentence = schedule_sentence(p.changes["schedule"], p.changes.get("anchor_at"), tz)
    shown = name or ""
    text = (
        f"Added routine {shown} to {agent}"
        if p.action == "create"
        else f"Changed routine {shown} of {agent}: {', '.join(labels)}"
    )
    out: dict[str, Any] = {"summary": text, "agent": agent, "fields": labels, "routine": name}
    if sentence is not None:
        out["schedule"] = sentence
    return out


def title(p: Proposal) -> str:
    """The card title's wording; a routine is named with its agent, e.g.
    ``change routine Digest of wide``."""
    name = p.agent_name or ""
    if p.changes.get("name"):
        name = f"{p.changes['name']} of {name}"
    return f"{p.action} {p.kind} {name}".strip()


KIND = Kind(
    name="routine",
    label="routine",
    summary="Add or change one of an agent's routines",
    fields=ROUTINE_FIELDS,
    normalize=normalize,
    exists=exists,
    apply=apply,
    summary_text=summary_text,
    title=title,
)
