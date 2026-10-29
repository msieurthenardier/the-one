"""The routine write rules, in one place (Mission 33 F2 L1, DD3).

The REST routes and (later) the agent's routine tools both write routines through
this module, so the operator's rules are enforced identically. It owns validation,
the create anchor and next run, and the update state machine. It never opens a
connection or builds an HTTP response: repositories, the chat repository and the
time zone come from the caller, and failures are typed errors
(``RoutineFieldError``, ``RoutineScheduleError``, ``RoutineLimitError``,
``RoutineNameTaken``, ``NameRuleError``) that the caller maps.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from typing import Any, Literal

from the_one.db.repositories import ChatSessionRepository
from the_one.naming import check_name
from the_one.routines import limits as routine_limits
from the_one.routines import runner as routine_runner
from the_one.routines import schedule as routine_schedule
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

ZoneLoader = Callable[[], Awaitable[tzinfo]]

MSG_ONCE_TOO_SOON = "A one-time routine must be at least a minute away."
MSG_SWITCH_OFF = "Routine tools are turned off for this agent."
MSG_NAMED_AGENT = "Routines need a named agent."

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def limits_view() -> dict[str, int]:
    return {
        "prompt_chars": routine_limits.ROUTINE_PROMPT_MAX_CHARS,
        "routines_per_agent": routine_limits.ROUTINES_PER_AGENT_MAX,
        "interval_hours_min": routine_limits.INTERVAL_HOURS_MIN,
        "interval_hours_max": routine_limits.INTERVAL_HOURS_MAX,
        "once_max_days": routine_limits.ONCE_MAX_AHEAD_DAYS,
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
) -> dict[str, Any]:
    """Validate a schedule from a request: ``once`` may carry ``in`` (converted to an
    absolute ``at``) or ``on`` (a local date and time in the operator zone, converted with
    the DST rules), and a ``once`` must lie in the future and within a year."""
    if isinstance(raw, dict) and raw.get("kind") == "once" and "on" in raw:
        spec = raw.get("on")
        if (
            set(raw) != {"kind", "on"}
            or not isinstance(spec, dict)
            or set(spec) != {"date", "time"}
        ):
            raise RoutineFieldError(
                "schedule", "A one-time schedule at a local time is {kind, on}."
            )
        date_text = spec.get("date")
        if not isinstance(date_text, str) or not _DATE_RE.match(date_text):
            raise RoutineFieldError("schedule", "The date must be written YYYY-MM-DD.")
        try:
            day = date.fromisoformat(date_text)
        except ValueError:
            raise RoutineFieldError("schedule", "That date doesn't exist.")
        try:
            hour, minute = routine_schedule._parse_hhmm(spec.get("time"))
        except RoutineScheduleError as e:
            raise RoutineFieldError("schedule", e.detail)
        try:
            at = routine_schedule.resolve_wall_time(day, hour, minute, zone)
        except (ValueError, OverflowError):
            raise RoutineFieldError("schedule", "That date doesn't exist.")
        raw = {"kind": "once", "at": at.isoformat()}
    if isinstance(raw, dict) and raw.get("kind") == "once" and "in" in raw:
        spec = raw.get("in")
        if set(raw) != {"kind", "in"} or not isinstance(spec, dict):
            raise RoutineFieldError("schedule", "A delayed one-time schedule is {kind, in}.")
        amount, unit = spec.get("amount"), spec.get("unit")
        if (
            isinstance(amount, bool)
            or not isinstance(amount, int)
            or amount < 1
            or unit not in ("minutes", "hours", "days")
            or set(spec) != {"amount", "unit"}
        ):
            raise RoutineFieldError(
                "schedule", "Give a whole number of minutes, hours or days, at least 1."
            )
        try:
            at = now + timedelta(**{unit: amount})
        except OverflowError:
            raise RoutineFieldError("schedule", routine_limits.MSG_TOO_FAR)
        raw = {"kind": "once", "at": at.isoformat()}
    try:
        sched = routine_schedule.validate(raw)
    except RoutineScheduleError as e:
        raise RoutineFieldError("schedule", e.detail)
    if sched["kind"] == "once":
        at = routine_schedule.parse_utc(sched["at"])
        if at <= now:
            raise RoutineFieldError("schedule", routine_limits.MSG_PAST)
        if min_ahead is not None and at - now < min_ahead:
            raise RoutineFieldError("schedule", MSG_ONCE_TOO_SOON)
        if at > now + timedelta(days=routine_limits.ONCE_MAX_AHEAD_DAYS):
            raise RoutineFieldError("schedule", routine_limits.MSG_TOO_FAR)
    return sched


async def resolve_target(
    raw: object, agent_name: str, chat_repo: ChatSessionRepository
) -> dict[str, Any]:
    """The target columns for a request ``target``; a ``chat`` snapshots the
    connector identity from that session row at write time (never refreshed)."""
    cols: dict[str, Any] = {
        "target_session_id": None,
        "target_platform": None,
        "target_connector_id": None,
        "target_channel_id": None,
        "target_thread_id": None,
        "target_peer_id": None,
    }
    if not isinstance(raw, dict) or raw.get("kind") not in ("chat", "new", "own"):
        raise RoutineFieldError("target", "The target must be a chat, a new chat or its own chat.")
    kind = raw["kind"]
    if kind != "chat":
        return {"target_kind": kind, **cols}
    sid = raw.get("session_id")
    if not isinstance(sid, str) or not sid:
        raise RoutineFieldError("target", "Pick a chat.")
    try:
        row = await chat_repo.get(sid)
    except KeyError:
        raise RoutineFieldError("target", "That chat doesn't exist.")
    if row.agent_name != agent_name:
        raise RoutineFieldError("target", "That chat belongs to another agent.")
    return {
        "target_kind": "chat",
        "target_session_id": row.id,
        "target_platform": row.platform,
        "target_connector_id": row.connector_id,
        "target_channel_id": row.channel_id,
        "target_thread_id": row.thread_id,
        "target_peer_id": row.peer_id,
    }


async def routine_view(
    routine: Any, run_repo: RoutineRunRepository, chat_repo: ChatSessionRepository
) -> dict[str, Any]:
    target: dict[str, Any] = {
        "kind": routine.target_kind,
        "session_id": routine.target_session_id,
        "title": None,
        "platform": routine.target_platform,
        "missing": False,
    }
    if routine.target_session_id:
        try:
            row = await chat_repo.get(routine.target_session_id)
            target["title"] = row.title
            target["platform"] = row.platform
        except KeyError:
            target["missing"] = routine.target_kind == "chat"
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
        "enabled": routine.enabled,
        "finished_at": routine.finished_at,
        "next_run_at": routine.next_run_at,
        "created_by": routine.created_by,
        "created_at": routine.created_at,
        "updated_at": routine.updated_at,
        "untrusted": routine.untrusted,
        "untrusted_sources": routine.untrusted_sources,
        "target": target,
        "last_run": last_run,
        "running": routine_runner.registry.is_running(routine.id),
    }


def _min_ahead(agent_caps: bool) -> timedelta | None:
    if not agent_caps:
        return None
    return timedelta(minutes=routine_limits.AGENT_ONCE_MIN_AHEAD_MINUTES)


async def create_routine(
    repo: AgentRoutineRepository,
    chat_repo: ChatSessionRepository,
    agent_name: str,
    data: dict[str, Any],
    *,
    now: datetime,
    zone: ZoneLoader,
    created_by: Literal["operator", "agent"] = "operator",
    agent_caps: bool = False,
    flag: Flag = None,
    proposal: ProposalOp | None = None,
) -> Any:
    """Validate ``data`` and store a new routine. Check order is name, prompt, schedule,
    target, enabled, so a body with several bad fields gets the first error.
    ``created_by``, ``agent_caps``, ``flag`` and ``proposal`` are for agent writes (the
    operator's callers pass none); the repository applies them in its one transaction."""
    routine_name = check_name(data.get("name"))
    prompt = validate_prompt(data.get("prompt"))
    tz = await zone()
    sched = validate_schedule(data.get("schedule"), now, tz, min_ahead=_min_ahead(agent_caps))
    target = await resolve_target(data.get("target"), agent_name, chat_repo)
    enabled = validate_enabled(data.get("enabled", True))
    anchor = now if sched["kind"] == "interval" else None
    next_at = (
        routine_schedule.next_run(sched, after=now, zone=tz, anchor=anchor) if enabled else None
    )
    routine = await repo.create(
        agent_name,
        {
            "name": routine_name,
            "prompt": prompt,
            "schedule": sched,
            "enabled": enabled,
            "next_run_at": next_at.isoformat() if next_at else None,
            "anchor_at": anchor.isoformat() if anchor else None,
            "created_by": created_by,
            **target,
        },
        agent_caps=agent_caps,
        flag=flag,
        proposal=proposal,
    )
    poke_scheduler()
    return routine


async def update_routine(
    repo: AgentRoutineRepository,
    chat_repo: ChatSessionRepository,
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
) -> Any:
    """Apply a partial update to ``current``. The zone loader is awaited only on a
    schedule change or a re-enable, so a name-only update never reads time settings.
    ``KeyError`` (routine gone) and ``RoutineNameTaken`` propagate."""
    cur = current
    fields: dict[str, Any] = {}
    if "name" in data:
        fields["name"] = check_name(data["name"])
    if "prompt" in data:
        fields["prompt"] = validate_prompt(data["prompt"])
    if "target" in data:
        fields.update(await resolve_target(data["target"], agent_name, chat_repo))
    enabled = cur.enabled
    if "enabled" in data:
        enabled = validate_enabled(data["enabled"])
    # Precedence (leg 1, AC13): any `schedule` key is a schedule change.
    schedule_changed = "schedule" in data
    sched = cur.schedule
    anchor = routine_schedule.parse_utc(cur.anchor_at) if cur.anchor_at else None
    finished_at = cur.finished_at
    if schedule_changed:
        sched = validate_schedule(
            data["schedule"], now, await zone(), min_ahead=_min_ahead(agent_caps)
        )
        fields["schedule"] = sched
        anchor = now if sched["kind"] == "interval" else None
        fields["anchor_at"] = anchor.isoformat() if anchor else None
        if finished_at is not None:
            finished_at = None
            fields["finished_at"] = None
    reenabled = "enabled" in data and enabled and not cur.enabled
    if "enabled" in data and enabled and finished_at is not None:
        raise RoutineFieldError("enabled", "Set a new time to run it again.")
    if reenabled and not schedule_changed and sched.get("kind") == "interval":
        anchor = now
        fields["anchor_at"] = now.isoformat()
    if "enabled" in data:
        fields["enabled"] = enabled
    if not enabled or finished_at is not None:
        fields["next_run_at"] = None
    elif schedule_changed or reenabled:
        nxt = routine_schedule.next_run(sched, after=now, zone=await zone(), anchor=anchor)
        fields["next_run_at"] = nxt.isoformat() if nxt else None
        if nxt is None and sched.get("kind") == "once":
            # A re-enabled one-off whose time has passed gets no catch-up: it is Done.
            fields["finished_at"] = now.isoformat()
    routine = await repo.update(
        agent_name,
        cur.id,
        fields,
        precheck=precheck,
        agent_caps=agent_caps,
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
    "enabled",
    "finished_at",
    "target_kind",
    "target_session_id",
)
# Which base keys a payload key touches (for the stale check).
_PAYLOAD_TO_BASE = {
    "name": ("name",),
    "prompt": ("prompt",),
    "schedule": ("schedule", "finished_at"),
    "enabled": ("enabled", "finished_at"),
    "target": ("target_kind", "target_session_id"),
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


def _target_body(cols: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {"kind": cols["target_kind"]}
    if cols["target_kind"] == "chat":
        body["session_id"] = cols["target_session_id"]
    return body


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
            target_kind=payload["target"]["kind"],
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
    if action == "update" and current is not None:
        upd: dict[str, Any] = {}
        for key in ("name", "prompt", "schedule", "enabled"):
            if key in payload:
                upd[key] = payload[key]
        if "schedule" in payload:
            upd["finished_at"] = None
            upd["next_run_at"] = None
        return current.model_copy(update=upd)
    return None


async def require_routine_tools_on(conn: Any, agent_name: str) -> bool:
    """Call-time gate shared by every agent routine tool (read and write): refuse for the
    ``default`` agent or when the Routines switch is off. Returns the approval flag."""
    if agent_name == "default":
        raise RoutineFieldError("routines", MSG_NAMED_AGENT)
    enabled_switch, requires_approval = await _agent_switches(conn, agent_name)
    if not enabled_switch:
        raise RoutineFieldError("routines", MSG_SWITCH_OFF)
    return requires_approval


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
    chat_repo = ChatSessionRepository(conn)
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
        payload["schedule"] = validate_schedule(
            data.get("schedule"), now, await zone(), min_ahead=_min_ahead(True)
        )
        payload["target"] = _target_body(
            await resolve_target(data.get("target"), agent_name, chat_repo)
        )
        payload["enabled"] = validate_enabled(data.get("enabled", True))
    elif action == "update":
        if "name" in data:
            payload["name"] = check_name(data["name"])
        if "prompt" in data:
            payload["prompt"] = validate_prompt(data["prompt"])
        if "schedule" in data:
            payload["schedule"] = validate_schedule(
                data["schedule"], now, await zone(), min_ahead=_min_ahead(True)
            )
        if "enabled" in data:
            payload["enabled"] = validate_enabled(data["enabled"])
        if "target" in data:
            payload["target"] = _target_body(
                await resolve_target(data["target"], agent_name, chat_repo)
            )
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
            routine_limits.check_agent_caps(before, after, now)

        proposal, replaced = await props.insert_pending(row, caps_check=caps_check)
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
            chat_repo,
            agent_name,
            payload,
            now=now,
            zone=zone,
            created_by="agent",
            agent_caps=True,
            flag=flag,
            proposal=op,
        )
    elif action == "update":
        assert current is not None
        routine = await update_routine(
            repo,
            chat_repo,
            agent_name,
            current,
            payload,
            now=now,
            zone=zone,
            agent_caps=True,
            flag=flag,
            proposal=op,
        )
    else:
        assert current is not None
        await delete_routine(repo, agent_name, current.id, proposal=op)
    return AgentChangeResult(
        pending=False,
        routine=routine,
        routine_id=routine.id if routine else (current.id if current else None),
    )


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
    """Apply a pending proposal. The zone and the target chat are resolved before the write
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
    chat_repo = ChatSessionRepository(conn)
    op = ProposalOp.resolve(proposal.id)
    flag: Flag = ("merge", list(proposal.untrusted_sources)) if proposal.untrusted else None
    if proposal.action == "create":
        await create_routine(
            repo,
            chat_repo,
            agent_name,
            dict(proposal.payload),
            now=now,
            zone=zone,
            created_by="agent",
            agent_caps=True,
            flag=flag,
            proposal=op,
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
                        chat_repo,
                        agent_name,
                        current,
                        dict(proposal.payload),
                        now=now,
                        zone=zone,
                        agent_caps=True,
                        flag=flag,
                        proposal=op,
                        precheck=precheck,
                    )
                else:
                    await delete_routine(
                        repo, agent_name, proposal.routine_id, precheck=precheck, proposal=op
                    )
            except KeyError:
                gone = True
        if gone:
            done = await props.mark_superseded(proposal.id)
            if proposal.action == "update":
                raise ProposalGoneError("That routine no longer exists.")
            return done
    got = await props.get(proposal.id)
    assert got is not None
    return got


async def dismiss_proposal(conn: Any, agent_name: str, proposal_id: str) -> RoutineProposal:
    props = RoutineProposalRepository(conn)
    proposal = await props.get(proposal_id)
    if proposal is None or proposal.agent_name != agent_name:
        raise KeyError(f"Proposal not found: {proposal_id}")
    return await props.mark_dismissed(proposal_id)
