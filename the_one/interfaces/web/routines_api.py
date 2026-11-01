"""Routine routes (M33), split out of ``api.py`` in Flight 3 (DD9).

The router has no prefix; ``api.py`` attaches it to ``api.router`` (prefix ``/api``) at the
bottom of that module. Handlers reach ``api.py`` helpers through ``_api`` at call time, so
tests that patch ``the_one.interfaces.web.api.get_connection`` and friends still apply.
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
from itertools import islice
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, StrictBool

from the_one import time_zones
from the_one.naming import NameRuleError, name_rule_detail
from the_one.routines import limits as routine_limits
from the_one.routines import recurrence, recurrence_text
from the_one.routines import runner as routine_runner
from the_one.routines import service as routine_service
from the_one.routines.limits import (
    RoutineFieldError,
    RoutineLimitError,
    RoutineNameTaken,
)
from the_one.routines.proposals import (
    ProposalGoneError,
    ProposalStaleError,
    ProposalStateError,
    RoutineProposalRepository,
)
from the_one.routines.repository import AgentRoutineRepository, RoutineRunRepository

if TYPE_CHECKING:
    from the_one.agent.config import AgentConfig


class _ApiModule:
    """Call-time lookup of ``api.py`` names (no import at load: ``api`` imports this module)."""

    def __getattr__(self, name: str) -> Any:
        from the_one.interfaces.web import api

        return getattr(api, name)


_api = _ApiModule()

router = APIRouter()

# ── Routines (M33 F1) ───────────────────────────────────────────────────
#
# Operator-only: no agent-facing tool reaches these routes (Flight 2 adds the
# agent's own). The ``default`` agent cannot have routines (its chats store a
# null agent_name); the name is compared literally, as ``factory.py`` does.
# Bodies are parsed by hand so a 422 never echoes submitted text. Nothing here
# runs a routine: the runner, Run now and the scheduler poke come in later legs.

_DEFAULT_AGENT = "default"


def _routine_422(field: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=[{"type": "value_error", "loc": [field], "msg": message}],
    )


async def _routines_agent_or_404(name: str) -> None:
    if name == _DEFAULT_AGENT:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    await _api._load_agent_or_404(name)


async def _routines_repos() -> tuple[AgentRoutineRepository, RoutineRunRepository]:
    conn = await _api.get_connection()
    return AgentRoutineRepository(conn), RoutineRunRepository(conn)


async def _effective_zone() -> tzinfo:
    conn = await _api.get_connection()
    return (await time_zones.load_effective_zone(conn)).tzinfo


NEXT_RUNS_SHOWN = 3


def schedule_preview(
    schedule: dict[str, Any], anchor: datetime | None, zone: tzinfo, now: datetime
) -> dict[str, Any]:
    """The sentence, the next three runs, the last occurrence and the warnings for a
    normalized schedule, as the preview route returns them."""
    nxt = list(islice(recurrence.occurrences(schedule, anchor, zone, now), NEXT_RUNS_SHOWN))
    last = recurrence.last_occurrence(schedule, anchor, zone)
    return {
        "text": recurrence_text.describe(schedule, anchor, zone),
        "next_runs": [i.isoformat() for i in nxt],
        "last_occurrence": last.isoformat() if last else None,
        "warnings": recurrence_text.warnings(schedule),
    }


@router.post("/agents/{name}/routines/preview")
async def preview_agent_routine_schedule(name: str, request: Request) -> dict[str, Any]:
    """Preview a schedule (any accepted input) without writing anything (DD7): the same
    normalization and refusals as create, for the form's live line."""
    await _routines_agent_or_404(name)
    data = await _routine_body(request)
    now = time_zones.utcnow()
    zone = await _effective_zone()
    try:
        raw, immediate = routine_service.resolve_now_start(data.get("schedule"), now, zone)
        sched, anchor = routine_service.validate_schedule(raw, now, zone)
    except RoutineFieldError as e:
        raise _routine_422(e.field, e.message)
    after = now.replace(second=0, microsecond=0) - timedelta(microseconds=1) if immediate else now
    if not recurrence.has_future(sched, anchor, after, zone):
        raise _routine_422("schedule", recurrence.MSG_NO_RUNS_LEFT)
    out = schedule_preview(sched, anchor, zone, now)
    if immediate:
        # The first run is the save instant; the grid occurrences follow it.
        out["next_runs"] = [now.isoformat(), *out["next_runs"][: NEXT_RUNS_SHOWN - 1]]
    return {
        "schedule": sched,
        "anchor_at": anchor.isoformat() if anchor else None,
        "immediate": immediate,
        **out,
    }


async def _routine_body(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(status_code=422, detail="Request body must be JSON")
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object")
    return data


@router.get("/agents/{name}/routines")
async def list_agent_routines(name: str) -> dict[str, Any]:
    await _routines_agent_or_404(name)
    repo, run_repo = await _routines_repos()
    routines = await repo.list_for_agent(name)
    zone = await _effective_zone()
    return {
        "routines": [await routine_service.routine_view(r, run_repo, zone) for r in routines],
        "limits": routine_service.limits_view(),
    }


@router.post("/agents/{name}/routines", status_code=201)
async def create_agent_routine(name: str, request: Request) -> dict[str, Any]:
    if name == _DEFAULT_AGENT:
        raise HTTPException(status_code=422, detail="Routines need a named agent.")
    data = await _routine_body(request)
    await _api._load_agent_or_404(name)
    conn = await _api.get_connection()

    async def zone() -> tzinfo:
        return (await time_zones.load_effective_zone(conn)).tzinfo

    repo, run_repo = await _routines_repos()
    try:
        routine = await routine_service.create_routine(
            repo, name, data, now=time_zones.utcnow(), zone=zone
        )
    except NameRuleError as e:
        raise HTTPException(status_code=422, detail=name_rule_detail(e.message))
    except RoutineFieldError as e:
        raise _routine_422(e.field, e.message)
    except RoutineNameTaken as e:
        raise HTTPException(status_code=409, detail=_api._name_conflict_detail(e.detail))
    except RoutineLimitError as e:
        raise HTTPException(status_code=422, detail=e.detail)
    return await routine_service.routine_view(routine, run_repo, await zone())


@router.get("/agents/{name}/routines/{routine_id}")
async def get_agent_routine(name: str, routine_id: str) -> dict[str, Any]:
    await _routines_agent_or_404(name)
    repo, run_repo = await _routines_repos()
    routine = await repo.get(name, routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail=f"Routine not found: {routine_id}")
    return await routine_service.routine_view(routine, run_repo, await _effective_zone())


@router.put("/agents/{name}/routines/{routine_id}")
async def update_agent_routine(name: str, routine_id: str, request: Request) -> dict[str, Any]:
    await _routines_agent_or_404(name)
    data = await _routine_body(request)
    repo, run_repo = await _routines_repos()
    cur = await repo.get(name, routine_id)
    if cur is None:
        raise HTTPException(status_code=404, detail=f"Routine not found: {routine_id}")

    async def zone() -> tzinfo:
        conn = await _api.get_connection()
        return (await time_zones.load_effective_zone(conn)).tzinfo

    try:
        routine = await routine_service.update_routine(
            repo,
            name,
            cur,
            data,
            now=time_zones.utcnow(),
            zone=zone,
            # M33 F2 DD7: an operator prompt edit is the only thing that clears the flag.
            flag="clear" if "prompt" in data else None,
        )
    except NameRuleError as e:
        raise HTTPException(status_code=422, detail=name_rule_detail(e.message))
    except RoutineFieldError as e:
        raise _routine_422(e.field, e.message)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Routine not found: {routine_id}")
    except RoutineNameTaken as e:
        raise HTTPException(status_code=409, detail=_api._name_conflict_detail(e.detail))
    return await routine_service.routine_view(routine, run_repo, await zone())


@router.delete("/agents/{name}/routines/{routine_id}")
async def delete_agent_routine(name: str, routine_id: str) -> dict[str, str]:
    await _routines_agent_or_404(name)
    repo, _ = await _routines_repos()
    try:
        await routine_service.delete_routine(repo, name, routine_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Routine not found: {routine_id}")
    return {"status": "ok"}


# ── Agent-written routines: switches and proposals (M33 F2) ─────────────────


class _RoutinesSwitchesBody(BaseModel):
    enabled: StrictBool | None = None
    requires_approval: StrictBool | None = None


async def _routines_switch_agent(name: str) -> "AgentConfig":
    if name == _DEFAULT_AGENT:
        raise HTTPException(status_code=422, detail=routine_service.MSG_NAMED_AGENT)
    _store, config = await _api._load_agent_or_404(name)
    return config


async def _routines_switches_view(name: str, config: "AgentConfig") -> dict[str, Any]:
    conn = await _api.get_connection()
    return {
        "enabled": config.routines_self_config_enabled,
        "requires_approval": config.routines_require_approval,
        "pending_count": await RoutineProposalRepository(conn).pending_count(name),
    }


@router.get("/agents/{name}/self-configuration/routines")
async def get_agent_routines_switches(name: str) -> dict[str, Any]:
    config = await _routines_switch_agent(name)
    return await _routines_switches_view(name, config)


@router.put("/agents/{name}/self-configuration/routines")
async def set_agent_routines_switches(name: str, request: Request) -> dict[str, Any]:
    body = await _api._rules_body(request, _RoutinesSwitchesBody)
    config = await _routines_switch_agent(name)
    if body.enabled is None and body.requires_approval is None:
        raise HTTPException(status_code=422, detail="Give enabled or requires_approval.")
    store = await _api._agent_store()
    try:
        await store.set_routines_self_config(
            name, enabled=body.enabled, requires_approval=body.requires_approval
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    conn = await _api.get_connection()
    if body.enabled is False and config.routines_self_config_enabled:
        # Turning Routines off withdraws everything still waiting (DD5).
        await RoutineProposalRepository(conn).supersede_pending(name)
    _store, fresh = await _api._load_agent_or_404(name)
    return await _routines_switches_view(name, fresh)


@router.get("/agents/{name}/self-configuration/routines/proposals")
async def list_routine_proposals(
    name: str,
    status: Literal["pending", "applied", "dismissed", "superseded"] | None = None,
    limit: int = Query(50, ge=1, le=200),
    before: str | None = None,
) -> dict[str, Any]:
    await _routines_switch_agent(name)
    conn = await _api.get_connection()
    rows = await RoutineProposalRepository(conn).list(
        name, status=status, limit=limit, before=before
    )
    # One routines read per request, never a query per row.
    routines = {r.id: r for r in await AgentRoutineRepository(conn).list_for_agent(name)}
    zone = await _effective_zone()
    return {"proposals": [routine_service.proposal_view(r, routines, zone) for r in rows]}


@router.get("/agents/{name}/self-configuration/routines/proposals/pending-count")
async def get_routine_proposals_pending_count(name: str) -> dict[str, int]:
    await _routines_switch_agent(name)
    repo = RoutineProposalRepository(await _api.get_connection())
    return {"count": await repo.pending_count(name)}


@router.post("/agents/{name}/self-configuration/routines/proposals/{proposal_id}/approve")
async def approve_routine_proposal(
    name: str, proposal_id: str, override: bool = False
) -> dict[str, Any]:
    await _routines_switch_agent(name)
    conn = await _api.get_connection()

    async def zone() -> tzinfo:
        return (await time_zones.load_effective_zone(conn)).tzinfo

    try:
        done = await routine_service.approve_proposal(
            conn, name, proposal_id, override=override, now=time_zones.utcnow(), zone=zone
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    except ProposalStaleError as e:
        text = routine_service.values_schedule_text
        stale_zone = await zone()
        raise HTTPException(
            status_code=409,
            detail={
                "error": "stale",
                "current_value": e.current,
                "proposed_value": e.proposed,
                "base_value": e.base,
                "current_schedule_text": text(e.current, stale_zone),
                "proposed_schedule_text": text(e.proposed, stale_zone),
                "base_schedule_text": text(e.base, stale_zone),
            },
        )
    except ProposalGoneError:
        raise HTTPException(status_code=409, detail={"error": "gone"})
    except ProposalStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except NameRuleError as e:
        raise HTTPException(status_code=422, detail=name_rule_detail(e.message))
    except RoutineFieldError as e:
        raise _routine_422(e.field, e.message)
    except RoutineNameTaken as e:
        raise HTTPException(status_code=409, detail=_api._name_conflict_detail(e.detail))
    except RoutineLimitError as e:
        raise HTTPException(status_code=422, detail=e.detail)
    return done.model_dump()


@router.post("/agents/{name}/self-configuration/routines/proposals/{proposal_id}/dismiss")
async def dismiss_routine_proposal(name: str, proposal_id: str) -> dict[str, Any]:
    await _routines_switch_agent(name)
    try:
        done = await routine_service.dismiss_proposal(
            await _api.get_connection(), name, proposal_id
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    except ProposalStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return done.model_dump()


@router.post("/agents/{name}/routines/{routine_id}/run", status_code=202)
async def run_agent_routine_now(name: str, routine_id: str) -> dict[str, str]:
    """Run now (M33 F1 L4, DD9): starts one manual run in the background."""
    await _routines_agent_or_404(name)
    repo, _ = await _routines_repos()
    if await repo.get(name, routine_id) is None:
        raise HTTPException(status_code=404, detail=f"Routine not found: {routine_id}")
    task = routine_runner.registry.try_spawn(
        routine_id, lambda: routine_runner.run_routine(routine_id, "manual")
    )
    if task is None:
        raise HTTPException(status_code=409, detail="This routine is already running.")
    return {"status": "started"}


@router.get("/agents/{name}/routines/{routine_id}/runs")
async def list_agent_routine_runs(
    name: str,
    routine_id: str,
    limit: int = Query(routine_limits.RUNS_PAGE_DEFAULT, ge=1, le=routine_limits.RUNS_PAGE_MAX),
    before: str | None = None,
) -> dict[str, Any]:
    await _routines_agent_or_404(name)
    repo, run_repo = await _routines_repos()
    if await repo.get(name, routine_id) is None:
        raise HTTPException(status_code=404, detail=f"Routine not found: {routine_id}")
    runs = await run_repo.list(routine_id, limit, before)
    alive = await (await _api._chat_repo()).existing_ids(r.session_id for r in runs)
    return {"runs": [{**r.model_dump(), "chat_exists": r.session_id in alive} for r in runs]}
