"""The routine write rules, in one place (Mission 33 F2 L1, DD3).

The REST routes and (later) the agent's routine tools both write routines through
this module, so the operator's rules are enforced identically. It owns validation,
the create anchor and next run, and the update state machine. It never opens a
connection or builds an HTTP response: repositories and the
time zone come from the caller, and failures are typed errors
(``RoutineFieldError``, ``RoutineScheduleError``, ``RoutineLimitError``,
``RoutineNameTaken``, ``NameRuleError``) that the caller maps.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Any, Literal

from the_one.naming import check_name, is_reserved_agent_name
from the_one.routines import limits as routine_limits
from the_one.routines import recurrence
from the_one.routines import runner as routine_runner
from the_one.routines.describe import schedule_sentence
from the_one.routines.limits import RoutineFieldError, RoutineScheduleError
from the_one.routines.models import Routine
from the_one.routines.proposals import (
    ProposalGoneError,
    ProposalOp,
    ProposalStaleError,
    ProposalStateError,
    RoutineProposal,
    RoutineProposalRepository,
)
from the_one.routines.repository import (
    AgentRoutineRepository,
    Flag,
    RoutineRunRepository,
)
from the_one.routines.scheduler import get_scheduler

logger = logging.getLogger(__name__)

ZoneLoader = Callable[[], Awaitable[tzinfo]]


def _log_proposal(
    proposal_id: str | None,
    agent_name: str,
    action: str,
    decision: str,
    flagged: bool,
    routine_id: str | None,
) -> None:
    """One INFO line per proposal decision: ids bare, the agent name repr-quoted, never the
    payload (a routine's name, prompt or schedule)."""
    logger.info(
        "routine proposal=%s agent=%r action=%s decision=%s flagged=%s routine=%s",
        proposal_id or "none",
        agent_name,
        action,
        decision,
        flagged,
        routine_id or "none",
    )


MSG_NO_RUNS_LEFT = recurrence.MSG_NO_RUNS_LEFT
MSG_UPGRADE_FAILED = "This schedule could not be upgraded. Edit it to turn the routine back on."
MSG_SWITCH_OFF = "Routine tools are turned off for this agent."
MSG_NAMED_AGENT = "Routines need a named agent."


def limits_view() -> dict[str, int]:
    return {
        "prompt_chars": routine_limits.ROUTINE_PROMPT_MAX_CHARS,
        "active_max": routine_limits.ROUTINES_ACTIVE_MAX,
        "open_max": routine_limits.ROUTINES_OPEN_MAX,
        "interval_hours_min": 1,
        "interval_hours_max": recurrence.EVERY_MAX["hour"],
        "once_max_days": recurrence.START_MAX_AHEAD_DAYS,
        "run_timeout_seconds": int(routine_runner.routine_run_timeout_seconds()),
    }


def poke_scheduler() -> None:
    """Wake the routine scheduler after a routine write; no-op without one."""
    sched = get_scheduler()
    if sched is not None:
        sched.poke()


def validate_prompt(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoutineFieldError("prompt", "The prompt cannot be empty.")
    text = value.strip()
    if len(text) > routine_limits.ROUTINE_PROMPT_MAX_CHARS:
        raise RoutineFieldError(
            "prompt",
            f"The prompt is limited to {routine_limits.ROUTINE_PROMPT_MAX_CHARS:,} characters; "
            f"this one is {len(text):,} characters.",
        )
    return text


def validate_enabled(value: object) -> bool:
    if not isinstance(value, bool):
        raise RoutineFieldError("enabled", "Enabled must be true or false.")
    return value


def validate_schedule(
    raw: object, now: datetime, zone: tzinfo, *, min_ahead: timedelta | None = None
) -> tuple[dict[str, Any], datetime | None]:
    """Normalize a schedule from a request (the canonical shape, with a date-and-time
    start or the relative start) to ``(schedule, anchor)``. A thin wrapper over
    ``recurrence.normalize``; it does not check that a run is left (see :func:`_require_future`)."""
    try:
        return recurrence.normalize(raw, zone=zone, now=now, min_ahead=min_ahead)
    except RoutineScheduleError as e:
        raise RoutineFieldError("schedule", e.detail)


def check_schedule_pair(schedule: object, anchor: datetime | None) -> dict[str, Any]:
    """A stored (canonical) schedule and its anchor, taken verbatim: no start-limit and no
    agent minimum lead (those were applied when the pair was made)."""
    try:
        return recurrence.check(schedule, anchor)
    except RoutineScheduleError as e:
        raise RoutineFieldError("schedule", e.detail)


def parse_anchor(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def resolve_now_start(raw: object, now: datetime, zone: tzinfo) -> tuple[object, bool]:
    """An operator's "Immediately" start (Mission 33 F4 L4). ``{"start": {"now": true}, ...}``
    (exact dict equality on the start) is rewritten to the canonical ``{date, time}`` of the
    floor minute of *now* in *zone*, so the grid is "save minute plus k periods"; everything
    else is returned unchanged with ``False``. Operator routes only: the agent path never
    calls this, so ``normalize`` refuses the now-start there."""
    if isinstance(raw, dict) and raw.get("start") == {"now": True}:
        floor = now.replace(second=0, microsecond=0)
        return {**raw, "start": recurrence.render_start(floor, zone)}, True
    return raw, False


def _require_now_start(
    schedule: dict[str, Any], anchor: datetime | None, now: datetime, zone: tzinfo, field: str
) -> datetime:
    """Check that a now-start schedule has a run at or after its save minute (an ``ends``
    already past is "no runs left") and return the exact save instant as the first run."""
    floor = now.replace(second=0, microsecond=0)
    if (
        recurrence.next_occurrence(schedule, anchor, floor - timedelta(microseconds=1), zone)
        is None
    ):
        raise RoutineFieldError(field, MSG_NO_RUNS_LEFT)
    return now


def _require_future(
    schedule: dict[str, Any], anchor: datetime | None, now: datetime, zone: tzinfo, field: str
) -> datetime:
    """The next occurrence after *now*; a schedule with none is "no runs left"."""
    nxt = recurrence.next_occurrence(schedule, anchor, now, zone)
    if nxt is None:
        raise RoutineFieldError(field, MSG_NO_RUNS_LEFT)
    return nxt


async def routine_view(
    routine: Any,
    run_repo: RoutineRunRepository,
    zone: tzinfo,
) -> dict[str, Any]:
    last = await run_repo.latest(routine.id)
    last_run = (
        {
            "outcome": last.outcome,
            "reason": last.reason,
            "trigger_kind": last.trigger_kind,
            "finished_at": last.finished_at,
            "session_id": last.session_id,
        }
        if last
        else None
    )
    return {
        "id": routine.id,
        "agent_name": routine.agent_name,
        "name": routine.name,
        "prompt": routine.prompt,
        "schedule": routine.schedule,
        "schedule_text": schedule_sentence(routine.schedule, routine.anchor_at, zone),
        "enabled": routine.enabled,
        "finished_at": routine.finished_at,
        "next_run_at": routine.next_run_at,
        "created_by": routine.created_by,
        "created_at": routine.created_at,
        "updated_at": routine.updated_at,
        "untrusted": routine.untrusted,
        "untrusted_sources": routine.untrusted_sources,
        "last_run": last_run,
        "running": routine_runner.registry.is_running(routine.id),
    }


def _min_ahead(agent_caps: bool) -> timedelta | None:
    if not agent_caps:
        return None
    return timedelta(minutes=routine_limits.AGENT_ONCE_MIN_AHEAD_MINUTES)


async def create_routine(
    repo: AgentRoutineRepository,
    agent_name: str,
    data: dict[str, Any],
    *,
    now: datetime,
    zone: ZoneLoader,
    created_by: Literal["operator", "agent"] = "operator",
    agent_caps: bool = False,
    flag: Flag = None,
    proposal: ProposalOp | None = None,
    schedule_pair: tuple[Any, datetime | None] | None = None,
) -> Any:
    """Validate ``data`` and store a new routine. Check order is name, prompt, schedule,
    enabled, so a body with several bad fields gets the first error.
    ``created_by``, ``agent_caps``, ``flag`` and ``proposal`` are for agent writes (the
    operator's callers pass none); the repository applies them in its one transaction.
    ``schedule_pair`` is an already-normalized ``(schedule, anchor)`` (an agent change made
    its start when it was proposed): it is checked and stored verbatim, with no agent lead
    time or start limit applied again. A schedule with no run left is refused whether the
    routine is on or off."""
    routine_name = check_name(data.get("name"))
    prompt = validate_prompt(data.get("prompt"))
    tz = await zone()
    is_now = False
    if schedule_pair is not None:
        sched = check_schedule_pair(*schedule_pair)
        anchor = schedule_pair[1]
    else:
        raw_schedule = data.get("schedule")
        if not agent_caps:
            raw_schedule, is_now = resolve_now_start(raw_schedule, now, tz)
        sched, anchor = validate_schedule(raw_schedule, now, tz, min_ahead=_min_ahead(agent_caps))
    if is_now:
        nxt = _require_now_start(sched, anchor, now, tz, "schedule")
    else:
        nxt = _require_future(sched, anchor, now, tz, "schedule")
    enabled = validate_enabled(data.get("enabled", True))
    routine = await repo.create(
        agent_name,
        {
            "name": routine_name,
            "prompt": prompt,
            "schedule": sched,
            "enabled": enabled,
            "next_run_at": nxt.isoformat() if enabled else None,
            "anchor_at": anchor.isoformat() if anchor else None,
            "created_by": created_by,
        },
        flag=flag,
        proposal=proposal,
    )
    poke_scheduler()
    return routine


async def update_routine(
    repo: AgentRoutineRepository,
    agent_name: str,
    current: Any,
    data: dict[str, Any],
    *,
    now: datetime,
    zone: ZoneLoader,
    agent_caps: bool = False,
    flag: Flag = None,
    proposal: ProposalOp | None = None,
    precheck: Callable[[Routine | None], None] | None = None,
    schedule_pair: tuple[Any, datetime | None] | None = None,
) -> Any:
    """Apply a partial update to ``current``. The zone loader is awaited only on a
    schedule change or a re-enable, so a name-only update never reads time settings.
    ``schedule_pair`` is as for :func:`create_routine` and counts as a schedule change.
    A schedule or a re-enable that leaves no run is refused (``schedule`` / ``enabled``).
    ``KeyError`` (routine gone) and ``RoutineNameTaken`` propagate."""
    cur = current
    fields: dict[str, Any] = {}
    if "name" in data:
        fields["name"] = check_name(data["name"])
    if "prompt" in data:
        fields["prompt"] = validate_prompt(data["prompt"])
    enabled = cur.enabled
    if "enabled" in data:
        enabled = validate_enabled(data["enabled"])
    # Precedence (leg 1, AC13): any `schedule` key is a schedule change.
    schedule_changed = "schedule" in data or schedule_pair is not None
    sched = cur.schedule
    anchor = parse_anchor(cur.anchor_at)
    finished_at = cur.finished_at
    tz: tzinfo | None = None
    now_start: datetime | None = None
    if schedule_changed:
        tz = await zone()
        is_now = False
        if schedule_pair is not None:
            sched = check_schedule_pair(*schedule_pair)
            anchor = schedule_pair[1]
        else:
            raw_schedule = data["schedule"]
            if not agent_caps:
                raw_schedule, is_now = resolve_now_start(raw_schedule, now, tz)
            sched, anchor = validate_schedule(
                raw_schedule, now, tz, min_ahead=_min_ahead(agent_caps)
            )
        if is_now:
            now_start = _require_now_start(sched, anchor, now, tz, "schedule")
        else:
            _require_future(sched, anchor, now, tz, "schedule")
        fields["schedule"] = sched
        fields["anchor_at"] = anchor.isoformat() if anchor else None
        if finished_at is not None:
            finished_at = None
            fields["finished_at"] = None
    reenabled = "enabled" in data and enabled and not cur.enabled
    if "enabled" in data and enabled and finished_at is not None:
        raise RoutineFieldError("enabled", "Set a new time to run it again.")
    if "enabled" in data:
        fields["enabled"] = enabled
    if not enabled or finished_at is not None:
        fields["next_run_at"] = None
    elif schedule_changed or reenabled:
        tz = tz or await zone()
        if not schedule_changed:
            # Re-enabling continues the stored grid (DD2); a stored schedule that cannot be
            # read (v48's upgrade_failed) must be edited first.
            try:
                sched = recurrence.check(sched, anchor)
            except (RoutineScheduleError, KeyError, TypeError, ValueError):
                raise RoutineFieldError("enabled", MSG_UPGRADE_FAILED)
        if now_start is not None:
            # An "Immediately" save: the exact save instant is due now (checked above).
            fields["next_run_at"] = now_start.isoformat()
        else:
            fields["next_run_at"] = _require_future(sched, anchor, now, tz, "enabled").isoformat()
    routine = await repo.update(
        agent_name,
        cur.id,
        fields,
        precheck=precheck,
        flag=flag,
        proposal=proposal,
    )
    poke_scheduler()
    return routine


async def delete_routine(
    repo: AgentRoutineRepository,
    agent_name: str,
    routine_id: str,
    *,
    precheck: Callable[[Routine | None], None] | None = None,
    proposal: ProposalOp | None = None,
) -> None:
    """Delete a routine. ``KeyError`` when it does not exist."""
    await repo.delete(agent_name, routine_id, precheck=precheck, proposal=proposal)
    poke_scheduler()


# ── Agent routine changes (Mission 33 F2, DD4-DD8) ──────────────────────────

_BASE_KEYS = (
    "name",
    "prompt",
    "schedule",
    "anchor_at",
    "enabled",
    "finished_at",
)
# Which base keys a payload key touches (for the stale check).
_PAYLOAD_TO_BASE = {
    "name": ("name",),
    "prompt": ("prompt",),
    "schedule": ("schedule", "anchor_at", "finished_at"),
    "enabled": ("enabled", "finished_at"),
}


@dataclass
class AgentChangeResult:
    pending: bool
    replaced: bool = False
    routine: Any = None
    proposal_id: str | None = None
    routine_id: str | None = None


def _base_of(routine: Routine) -> dict[str, Any]:
    return {k: getattr(routine, k) for k in _BASE_KEYS}


def _touched_base_keys(action: str, payload: dict[str, Any]) -> list[str]:
    if action == "delete":
        return [k for k in _BASE_KEYS if k != "finished_at"]
    keys: list[str] = []
    for pk in payload:
        for bk in _PAYLOAD_TO_BASE.get(pk, ()):
            if bk not in keys:
                keys.append(bk)
    return keys


async def _agent_switches(conn: Any, agent_name: str) -> tuple[bool, bool]:
    async with conn.execute(
        "SELECT routines_self_config_enabled, routines_require_approval FROM agents WHERE name = ?",
        (agent_name,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return False, True
    return bool(row[0]), bool(row[1])


async def _resolve_routine(
    repo: AgentRoutineRepository,
    props: RoutineProposalRepository,
    agent_name: str,
    ref: object,
) -> Routine:
    if not isinstance(ref, str) or not ref.strip():
        raise RoutineFieldError("routine", "Say which routine, by name or id.")
    found = await repo.get(agent_name, ref) or await repo.get_by_name(agent_name, ref.strip())
    if found is not None:
        return found
    if await props.pending_create_named(agent_name, ref.strip()):
        raise RoutineFieldError(
            "routine",
            "That routine is still waiting for your operator's approval, so it can't be "
            "changed yet.",
        )
    raise RoutineFieldError("routine", f"There's no routine called '{ref}'.")


def _hypothetical(
    action: str, payload: dict[str, Any], agent_name: str, current: Routine | None, now: datetime
) -> Routine | None:
    """The routine as it would stand after a proposal, for the proposal-time caps check."""
    if action == "create":
        return Routine(
            id="pending",
            agent_name=agent_name,
            name=payload["name"],
            prompt=payload["prompt"],
            schedule=payload["schedule"],
            enabled=payload.get("enabled", True),
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
    if action == "update" and current is not None:
        upd: dict[str, Any] = {}
        for key in ("name", "prompt", "schedule", "enabled"):
            if key in payload:
                upd[key] = payload[key]
        if "schedule" in payload:
            upd["anchor_at"] = payload.get("anchor_at")
            upd["finished_at"] = None
            upd["next_run_at"] = None
        return current.model_copy(update=upd)
    return None


async def require_routine_tools_on(conn: Any, agent_name: str) -> bool:
    """Call-time gate shared by every agent routine tool (read and write): refuse for the
    ``default`` agent or when the Routines switch is off. Returns the approval flag."""
    if is_reserved_agent_name(agent_name):
        raise RoutineFieldError("routines", MSG_NAMED_AGENT)
    enabled_switch, requires_approval = await _agent_switches(conn, agent_name)
    if not enabled_switch:
        raise RoutineFieldError("routines", MSG_SWITCH_OFF)
    return requires_approval


async def _agent_schedule(raw: object, now: datetime, zone: ZoneLoader) -> dict[str, Any]:
    """An agent's schedule input made once: normalized with the agent's minimum lead, checked
    for a run left, and returned as the payload keys ``schedule`` and ``anchor_at`` (ISO or
    null). The proposal row and the stored routine both carry this exact pair (DD5)."""
    tz = await zone()
    sched, anchor = validate_schedule(raw, now, tz, min_ahead=_min_ahead(True))
    _require_future(sched, anchor, now, tz, "schedule")
    return {"schedule": sched, "anchor_at": anchor.isoformat() if anchor else None}


def _payload_pair(payload: dict[str, Any]) -> tuple[Any, datetime | None]:
    return payload["schedule"], parse_anchor(payload.get("anchor_at"))


async def _approval_pair(
    payload: dict[str, Any], zone: ZoneLoader
) -> tuple[dict[str, Any], datetime | None]:
    """A proposal's stored pair for approval: applied verbatim (the anchor is never
    re-derived), with ``start`` re-rendered in the current zone so a zone change while the
    proposal waited leaves no stale display start."""
    sched, anchor = _payload_pair(payload)
    sched = check_schedule_pair(sched, anchor)
    return recurrence.rezone(sched, anchor, await zone()), anchor


async def agent_change(
    conn: Any,
    agent_name: str,
    action: Literal["create", "update", "delete"],
    data: dict[str, Any],
    *,
    now: datetime,
    zone: ZoneLoader,
    taint: tuple[bool, list[str]],
    session_id: str | None,
) -> AgentChangeResult:
    """One agent routine change: validated exactly as the operator's, then applied at
    once (approval off) or held as a pending proposal (approval on)."""
    requires_approval = await require_routine_tools_on(conn, agent_name)
    repo = AgentRoutineRepository(conn)
    props = RoutineProposalRepository(conn)
    untrusted, sources = taint
    sources = list(sources)

    current: Routine | None = None
    payload: dict[str, Any] = {}
    base: dict[str, Any] | None = None
    if action in ("update", "delete"):
        current = await _resolve_routine(repo, props, agent_name, data.get("routine"))
        base = _base_of(current)
    if action == "create":
        payload["name"] = check_name(data.get("name"))
        payload["prompt"] = validate_prompt(data.get("prompt"))
        payload.update(await _agent_schedule(data.get("schedule"), now, zone))
        payload["enabled"] = validate_enabled(data.get("enabled", True))
    elif action == "update":
        if "name" in data:
            payload["name"] = check_name(data["name"])
        if "prompt" in data:
            payload["prompt"] = validate_prompt(data["prompt"])
        if "schedule" in data:
            payload.update(await _agent_schedule(data["schedule"], now, zone))
        if "enabled" in data:
            payload["enabled"] = validate_enabled(data["enabled"])
        if not payload:
            raise RoutineFieldError("routine", "Say what to change.")

    row = {
        "agent_name": agent_name,
        "routine_id": current.id if current else None,
        "routine_name": payload["name"] if action == "create" else current.name,  # type: ignore[union-attr]
        "action": action,
        "payload": payload,
        "base": base,
        "untrusted": untrusted,
        "untrusted_sources": sources,
        "session_id": session_id,
    }
    if requires_approval:
        hypo = _hypothetical(action, payload, agent_name, current, now)

        def caps_check(before: list[Routine]) -> None:
            if hypo is None:
                return
            after = (
                [*before, hypo]
                if action == "create"
                else [hypo if r.id == hypo.id else r for r in before]
            )
            routine_limits.check_routine_caps(before, after)

        proposal, replaced = await props.insert_pending(row, caps_check=caps_check)
        _log_proposal(
            proposal.id,
            agent_name,
            action,
            "pending",
            untrusted,
            current.id if current else None,
        )
        return AgentChangeResult(
            pending=True,
            replaced=replaced,
            proposal_id=proposal.id,
            routine_id=current.id if current else None,
        )

    op = ProposalOp.insert_applied(row)
    flag: Flag = ("merge", sources) if untrusted else None
    routine: Any = None
    if action == "create":
        routine = await create_routine(
            repo,
            agent_name,
            payload,
            now=now,
            zone=zone,
            created_by="agent",
            agent_caps=True,
            flag=flag,
            proposal=op,
            schedule_pair=_payload_pair(payload),
        )
    elif action == "update":
        assert current is not None
        routine = await update_routine(
            repo,
            agent_name,
            current,
            payload,
            now=now,
            zone=zone,
            agent_caps=True,
            flag=flag,
            proposal=op,
            schedule_pair=_payload_pair(payload) if "schedule" in payload else None,
        )
    else:
        assert current is not None
        await delete_routine(repo, agent_name, current.id, proposal=op)
    applied_id = routine.id if routine else (current.id if current else None)
    _log_proposal(op.applied_id, agent_name, action, "applied", untrusted, applied_id)
    return AgentChangeResult(
        pending=False,
        routine=routine,
        routine_id=applied_id,
    )


def values_schedule_text(values: Any, zone: tzinfo) -> str | None:
    """The sentence for the ``schedule`` (with its ``anchor_at``) in a dict of proposal or
    routine values; None when the dict holds no schedule or it cannot be read."""
    if not isinstance(values, dict) or "schedule" not in values:
        return None
    return schedule_sentence(values["schedule"], values.get("anchor_at"), zone)


def proposal_view(
    proposal: RoutineProposal, routines: dict[str, Routine], zone: tzinfo
) -> dict[str, Any]:
    """A proposal as the REST dict, plus the sentences for its payload, base and current
    schedule (null where there is none). *routines* is the agent's routines by id."""
    out = proposal.model_dump()
    current = routines.get(proposal.routine_id) if proposal.routine_id else None
    out["payload_schedule_text"] = values_schedule_text(proposal.payload, zone)
    out["base_schedule_text"] = values_schedule_text(proposal.base, zone)
    out["current_schedule_text"] = (
        schedule_sentence(current.schedule, current.anchor_at, zone) if current else None
    )
    return out


def _stale_precheck(proposal: RoutineProposal, override: bool) -> Callable[[Routine | None], None]:
    def check(row: Routine | None) -> None:
        if row is None or override:
            return
        base = proposal.base or {}
        current = _base_of(row)
        touched = _touched_base_keys(proposal.action, proposal.payload)
        if any(current.get(k) != base.get(k) for k in touched):
            raise ProposalStaleError(
                {k: current.get(k) for k in touched},
                proposal.payload,
                {k: base.get(k) for k in touched},
            )

    return check


async def approve_proposal(
    conn: Any,
    agent_name: str,
    proposal_id: str,
    *,
    override: bool,
    now: datetime,
    zone: ZoneLoader,
) -> RoutineProposal:
    """Apply a pending proposal. The zone is resolved before the write
    lock; the name, caps and stale checks run inside the repository's transaction against a
    routine re-read at approval."""
    props = RoutineProposalRepository(conn)
    proposal = await props.get(proposal_id)
    if proposal is None or proposal.agent_name != agent_name:
        raise KeyError(f"Proposal not found: {proposal_id}")
    if proposal.status == "applied":
        return proposal
    if proposal.status != "pending":
        raise ProposalStateError(f"That change is {proposal.status}.")
    repo = AgentRoutineRepository(conn)
    op = ProposalOp.resolve(proposal.id)
    flag: Flag = ("merge", list(proposal.untrusted_sources)) if proposal.untrusted else None
    if proposal.action == "create":
        await create_routine(
            repo,
            agent_name,
            dict(proposal.payload),
            now=now,
            zone=zone,
            created_by="agent",
            agent_caps=True,
            flag=flag,
            proposal=op,
            schedule_pair=await _approval_pair(proposal.payload, zone),
        )
    else:
        current = await repo.get(agent_name, proposal.routine_id) if proposal.routine_id else None
        gone = current is None
        if not gone:
            precheck = _stale_precheck(proposal, override)
            try:
                if proposal.action == "update":
                    assert current is not None
                    await update_routine(
                        repo,
                        agent_name,
                        current,
                        dict(proposal.payload),
                        now=now,
                        zone=zone,
                        agent_caps=True,
                        flag=flag,
                        proposal=op,
                        precheck=precheck,
                        schedule_pair=(
                            await _approval_pair(proposal.payload, zone)
                            if "schedule" in proposal.payload
                            else None
                        ),
                    )
                else:
                    await delete_routine(
                        repo, agent_name, proposal.routine_id, precheck=precheck, proposal=op
                    )
            except KeyError:
                gone = True
        if gone:
            done = await props.mark_superseded(proposal.id)
            _log_proposal(
                proposal.id,
                agent_name,
                proposal.action,
                "superseded",
                proposal.untrusted,
                proposal.routine_id,
            )
            if proposal.action == "update":
                raise ProposalGoneError("That routine no longer exists.")
            return done
    got = await props.get(proposal.id)
    assert got is not None
    _log_proposal(
        proposal.id,
        agent_name,
        proposal.action,
        "approved",
        proposal.untrusted,
        got.routine_id or proposal.routine_id,
    )
    return got


async def dismiss_proposal(conn: Any, agent_name: str, proposal_id: str) -> RoutineProposal:
    props = RoutineProposalRepository(conn)
    proposal = await props.get(proposal_id)
    if proposal is None or proposal.agent_name != agent_name:
        raise KeyError(f"Proposal not found: {proposal_id}")
    dismissed = await props.mark_dismissed(proposal_id)
    _log_proposal(
        proposal_id,
        agent_name,
        proposal.action,
        "dismissed",
        proposal.untrusted,
        proposal.routine_id,
    )
    return dismissed
