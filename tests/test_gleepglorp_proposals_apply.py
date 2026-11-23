"""Applying and dismissing a GleepGlorp proposal (M36 F2 L4, DD3, DD4, DD7, DD9, DD10)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from tests._gleepglorp_seed import seed
from the_one.agent.service import AgentWriteDeps
from the_one.db.repositories import (
    AgentRuleRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.gleepglorp.proposals import apply as proposal_apply
from the_one.gleepglorp.proposals import shape
from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository, NewProposal, mark_op
from the_one.routines.repository import AgentRoutineRepository

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


async def _utc():
    return UTC


@pytest.fixture
async def world(tmp_path):
    from the_one.db import _write_lock

    _write_lock.reset_for_test()  # the lock binds to the first loop that contends for it
    ns = await seed(tmp_path)
    conn, enc = ns.conn, ns.enc
    ns.deps = AgentWriteDeps(
        store=SQLiteAgentStore(conn, enc),
        mcp_repo=MCPSourceRepository(conn, enc),
        provider_repo=LLMProviderRepository(conn, enc),
        secret_repo=SecretRepository(conn, enc),
        tool_config_repo=ToolConfigRepository(conn, enc),
    )
    ns.repo = GleepGlorpProposalRepository(conn)
    yield ns
    await conn.close()


@pytest.fixture
def frames(monkeypatch):
    """Every ``proposal_changed`` push and ``config_changed`` broadcast, in order."""
    out = SimpleNamespace(proposal=[], config=[])

    async def push(session_id, view):
        out.proposal.append((session_id, view["status"]))

    async def broadcast(payload):
        out.config.append(payload)

    monkeypatch.setattr(proposal_apply, "push_proposal_changed", push)
    monkeypatch.setattr("the_one.sessions._broadcast.broadcast_to_all", broadcast)
    return out


async def make(
    world, kind, action, changes, *, session="s1", untrusted=False, sources=(), **target
) -> int:
    n = await shape.normalize(
        kind, action, target, changes, conn=world.conn, now=NOW, zone=UTC, enc=world.enc
    )
    return await world.repo.insert(
        NewProposal(
            session_id=session,
            kind=n.kind,
            action=n.action,
            agent_name=n.agent_name,
            target_key=n.target_key,
            changes=n.changes,
            target_id=n.target_id,
            base=n.base,
            untrusted=untrusted,
            untrusted_sources=list(sources),
        )
    )


async def run(world, pid, *, override=False):
    return await proposal_apply.apply_proposal(
        world.conn, world.deps, pid, override=override, now=NOW, zone=_utc
    )


async def status_of(world, pid) -> str:
    return (await world.repo.get(pid)).status


def _in(hours: int) -> dict:
    return {"start": {"in": {"amount": hours, "unit": "hours"}}}


def _routine_new(name="Weekly") -> dict:
    return {"name": name, "prompt": "Do the thing.", "schedule": _in(5)}


# --- each kind applies exactly its fields -----------------------------------------------


async def test_an_agent_change_applies_exactly_its_fields(world) -> None:
    before = (await world.deps.store.load("wide")).model_dump()
    pid = await make(world, "agent", "change", {"description": "New words"}, agent="wide")
    res = await run(world, pid)
    assert res.outcome == "applied" and res.view["status"] == "applied"
    after = (await world.deps.store.load("wide")).model_dump()
    expected = dict(before, description="New words")
    assert after == expected  # switches, mcp_overrides, tool_overrides, secret_ids untouched
    assert (await world.repo.get(pid)).result["summary"] == "Changed Description on wide"


async def test_an_agent_change_resolves_names_to_ids(world) -> None:
    pid = await make(
        world,
        "agent",
        "change",
        {"provider": "Local", "model": "m2", "knowledge_bases": []},
        agent="wide",
    )
    assert (await run(world, pid)).outcome == "applied"
    cfg = await world.deps.store.load("wide")
    assert (cfg.provider_config_id, cfg.llm_model, cfg.kb_ids) == ("p-local", "m2", [])
    assert cfg.mcp_overrides  # the stored credential override is intact


async def test_an_agent_create_applies(world) -> None:
    pid = await make(
        world,
        "agent",
        "create",
        {"name": "Fresh", "description": "d", "provider": "Local", "model": "m"},
    )
    res = await run(world, pid)
    assert res.outcome == "applied"
    cfg = await world.deps.store.load("Fresh")
    assert (cfg.description, cfg.provider_config_id) == ("d", "p-local")
    assert (await world.repo.get(pid)).result["summary"] == "Created agent Fresh"


async def test_a_rule_create_appends_and_position_one_goes_first(world) -> None:
    rules = AgentRuleRepository(world.conn)
    pid = await make(world, "rule", "create", {"text": "Second."}, agent="wide")
    assert (await run(world, pid)).outcome == "applied"
    assert [r.text for r in await rules.list_for_agent("wide")][-1] == "Second."
    # 1-based position 1 is the front (0-based 0 must not read as "append").
    pid = await make(
        world, "rule", "create", {"text": "First.", "position": 1}, agent="wide", session="s2"
    )
    assert (await run(world, pid)).outcome == "applied"
    assert [r.text for r in await rules.list_for_agent("wide")][0] == "First."


async def test_a_rule_change_applies_exactly_its_fields(world) -> None:
    rules = AgentRuleRepository(world.conn)
    before = (await rules.list_for_agent("wide"))[0]
    pid = await make(world, "rule", "change", {"enabled": False}, agent="wide", rule=1)
    assert (await run(world, pid)).outcome == "applied"
    after = (await rules.list_for_agent("wide"))[0]
    assert (after.text, after.enabled) == (before.text, False)


async def test_a_routine_create_is_stored_as_the_operators_and_flagged_when_untrusted(
    world,
) -> None:
    pid = await make(
        world,
        "routine",
        "create",
        _routine_new(),
        agent="plain",
        untrusted=True,
        sources=["read_app_config"],
    )
    res = await run(world, pid)
    assert res.outcome == "applied"
    r = await AgentRoutineRepository(world.conn).get_by_name("plain", "Weekly")
    assert r.created_by == "operator"
    assert r.untrusted is True and r.untrusted_sources == ["read_app_config"]
    assert (await world.repo.get(pid)).result["routine_id"] == r.id
    assert (await world.repo.get(pid)).result["schedule"]  # the sentence


async def test_a_trusted_routine_proposal_is_not_flagged(world) -> None:
    pid = await make(world, "routine", "create", _routine_new(), agent="plain")
    assert (await run(world, pid)).outcome == "applied"
    r = await AgentRoutineRepository(world.conn).get_by_name("plain", "Weekly")
    assert r.untrusted is False and r.untrusted_sources == []


async def test_a_routine_change_applies_its_fields_only(world) -> None:
    repo = AgentRoutineRepository(world.conn)
    before = await repo.get_by_name("wide", "Morning digest")
    pid = await make(
        world,
        "routine",
        "change",
        {"prompt": "A new prompt.", "schedule": _in(6)},
        agent="wide",
        routine="Morning digest",
        untrusted=True,
        sources=["web_fetch"],
    )
    assert (await run(world, pid)).outcome == "applied"
    after = await repo.get_by_name("wide", "Morning digest")
    assert after.prompt == "A new prompt." and after.schedule != before.schedule
    assert (after.name, after.enabled) == (before.name, before.enabled)
    assert after.untrusted is True and "web_fetch" in after.untrusted_sources


# --- stale and override ------------------------------------------------------------------


async def test_a_stale_agent_proposal_is_refused_with_labels_and_nothing_written(world) -> None:
    pid = await make(world, "agent", "change", {"description": "Proposed"}, agent="plain")
    cfg = await world.deps.store.load("plain")
    await world.deps.store.save(cfg.model_copy(update={"description": "Changed by hand"}))
    res = await run(world, pid)
    assert res.outcome == "stale"
    assert res.stale == [
        {
            "field": "description",
            "label": "Description",
            "current": "Changed by hand",
            "proposed": "Proposed",
        }
    ]
    assert await status_of(world, pid) == "pending"
    assert (await world.deps.store.load("plain")).description == "Changed by hand"
    res = await run(world, pid, override=True)
    assert res.outcome == "applied"
    assert (await world.deps.store.load("plain")).description == "Proposed"


async def test_a_stale_agent_id_field_is_shown_as_a_name(world) -> None:
    pid = await make(world, "agent", "change", {"knowledge_bases": []}, agent="wide")
    cfg = await world.deps.store.load("wide")
    await world.deps.store.save(cfg.model_copy(update={"kb_ids": []}))
    # base was ["kb1"]; the stored value is now [] -> stale, current shown as names
    res = await run(world, pid)
    assert res.outcome == "stale"
    assert res.stale[0]["current"] == [] and res.stale[0]["proposed"] == []


async def test_a_stale_rule_proposal_is_refused_and_override_applies(world) -> None:
    rules = AgentRuleRepository(world.conn)
    pid = await make(world, "rule", "change", {"text": "Proposed rule."}, agent="wide", rule=1)
    rule = (await rules.list_for_agent("wide"))[0]
    await rules.update("wide", rule.id, text="Hand edit.", enabled=None)
    res = await run(world, pid)
    assert res.outcome == "stale" and res.stale[0]["field"] == "text"
    assert res.stale[0]["label"] == "Rule" and res.stale[0]["current"] == "Hand edit."
    assert await status_of(world, pid) == "pending"
    assert (await run(world, pid, override=True)).outcome == "applied"
    assert (await rules.list_for_agent("wide"))[0].text == "Proposed rule."


async def test_a_stale_routine_proposal_is_refused_and_override_applies(world) -> None:
    repo = AgentRoutineRepository(world.conn)
    pid = await make(
        world, "routine", "change", {"prompt": "Mine."}, agent="wide", routine="Morning digest"
    )
    routine = await repo.get_by_name("wide", "Morning digest")
    await repo.update("wide", routine.id, {"prompt": "Edited by the operator."})
    res = await run(world, pid)
    assert res.outcome == "stale"
    assert res.stale == [
        {
            "field": "prompt",
            "label": "Prompt",
            "current": "Edited by the operator.",
            "proposed": "Mine.",
        }
    ]
    assert await status_of(world, pid) == "pending"
    assert (await run(world, pid, override=True)).outcome == "applied"
    assert (await repo.get_by_name("wide", "Morning digest")).prompt == "Mine."


# --- applied once ---------------------------------------------------------------------------


async def _agent_change(world) -> int:
    return await make(world, "agent", "change", {"description": "Once"}, agent="plain")


async def _agent_create(world) -> int:
    return await make(world, "agent", "create", {"name": "Twice"})


async def _routine_create(world) -> int:
    return await make(world, "routine", "create", _routine_new("Once"), agent="plain")


async def _rule_create(world) -> int:
    return await make(world, "rule", "create", {"text": "Only once."}, agent="plain")


async def _count(world, kind) -> int:
    if kind == "agent_create":
        return 1 if await world.deps.store.exists("Twice") else 0
    if kind == "routine_create":
        return len(await AgentRoutineRepository(world.conn).list_for_agent("plain"))
    if kind == "rule_create":
        return len(await AgentRuleRepository(world.conn).list_for_agent("plain"))
    return 1


MAKERS = {
    "agent_change": _agent_change,
    "agent_create": _agent_create,
    "routine_create": _routine_create,
    "rule_create": _rule_create,
}


@pytest.mark.parametrize("kind", list(MAKERS))
async def test_a_second_sequential_approve_answers_already_applied(world, frames, kind) -> None:
    pid = await MAKERS[kind](world)
    assert (await run(world, pid)).outcome == "applied"
    again = await run(world, pid)
    assert again.outcome == "already_applied" and again.view["status"] == "applied"
    assert await _count(world, kind) == 1
    assert len(frames.config) == 1


@pytest.mark.parametrize("kind", list(MAKERS))
async def test_two_concurrent_approves_apply_once(world, frames, kind) -> None:
    pid = await MAKERS[kind](world)
    first, second = await asyncio.gather(run(world, pid), run(world, pid))
    assert sorted([first.outcome, second.outcome]) == ["already_applied", "applied"]
    assert await status_of(world, pid) == "applied"
    assert await _count(world, kind) == 1
    assert len(frames.config) == 1
    assert "failed" not in [s for _, s in frames.proposal]


async def test_a_failed_mark_never_overwrites_applied(world) -> None:
    pid = await _agent_change(world)
    assert (await run(world, pid)).outcome == "applied"
    assert not await world.repo.mark(
        pid, "failed", result={"errors": []}, from_statuses=("pending", "failed")
    )
    assert await status_of(world, pid) == "applied"
    assert not await mark_op(
        world.conn, pid, "applied", result={}, from_statuses=("pending", "failed")
    )


async def test_a_create_for_a_deleted_agent_is_gone(world, frames) -> None:
    rule_pid = await make(world, "rule", "create", {"text": "R."}, agent="plain", session="s1")
    routine_pid = await make(
        world, "routine", "create", _routine_new(), agent="plain", session="s2"
    )
    await world.deps.store.delete("plain")
    for pid in (rule_pid, routine_pid):
        res = await run(world, pid)
        assert res.outcome == "gone"
        row = await world.repo.get(pid)
        assert row.status == "withdrawn" and row.result == {"reason": "gone"}
    assert frames.config == []


# --- failures and retries ------------------------------------------------------------------


async def test_a_name_taken_since_the_proposal_is_failed_and_a_retry_applies(world, frames) -> None:
    pid = await _agent_create(world)
    from the_one.agent.config import AgentConfig

    await world.deps.store.save(AgentConfig(name="Twice", provider_config_id="p-local"))
    res = await run(world, pid)
    assert res.outcome == "failed" and res.view["status"] == "failed"
    errors = res.view["result"]["errors"]
    assert errors and errors[0]["loc"] == ["name"] and errors[0]["msg"]
    assert set(errors[0]) == {"loc", "msg"}
    assert frames.config == []
    assert frames.proposal[-1][1] == "failed"
    await world.deps.store.delete("Twice")
    res = await run(world, pid)  # Try again
    assert res.outcome == "applied" and await world.deps.store.exists("Twice")
    assert len(frames.config) == 1


async def test_a_routine_name_taken_is_failed_with_the_name_loc(world) -> None:
    pid = await make(world, "routine", "create", _routine_new("Clash"), agent="plain")
    await AgentRoutineRepository(world.conn).create(
        "plain",
        {
            "name": "Clash",
            "prompt": "x",
            "schedule": shape.routine_service.validate_schedule(_in(9), NOW, UTC)[0],
        },
    )
    res = await run(world, pid)
    assert res.outcome == "failed"
    assert res.view["result"]["errors"][0]["loc"] == ["name"]


async def test_the_rule_total_limit_is_a_failed_apply_with_its_detail(world) -> None:
    pid = await make(world, "rule", "create", {"text": "Short."}, agent="plain")
    from the_one.db import _rules

    rules = AgentRuleRepository(world.conn)
    for _ in range(_rules.RULES_TOTAL_MAX_CHARS // _rules.RULE_MAX_CHARS):
        await rules.create("plain", "x" * _rules.RULE_MAX_CHARS)
    res = await run(world, pid)
    assert res.outcome == "failed"
    assert "in total" in res.view["result"]["errors"][0]["msg"]
    assert len(await rules.list_for_agent("plain")) == 8


# --- refusals ---------------------------------------------------------------------------------


async def test_a_deleted_rule_target_is_gone_and_withdrawn(world, frames) -> None:
    rules = AgentRuleRepository(world.conn)
    pid = await make(world, "rule", "change", {"text": "Nope."}, agent="wide", rule=1)
    await rules.delete("wide", (await rules.list_for_agent("wide"))[0].id)
    res = await run(world, pid)
    assert res.outcome == "gone"
    assert (await world.repo.get(pid)).status == "withdrawn"
    assert frames.config == [] and frames.proposal[-1][1] == "withdrawn"


async def test_a_deleted_routine_target_is_gone(world) -> None:
    repo = AgentRoutineRepository(world.conn)
    pid = await make(
        world, "routine", "change", {"enabled": False}, agent="wide", routine="Morning digest"
    )
    await repo.delete("wide", (await repo.get_by_name("wide", "Morning digest")).id)
    assert (await run(world, pid)).outcome == "gone"


async def test_a_busy_chat_is_refused_and_nothing_is_written(world, monkeypatch, frames) -> None:
    monkeypatch.setattr("the_one.sessions._locks.is_session_busy", lambda sid: sid == "s1")
    pid = await _agent_change(world)
    assert (await run(world, pid)).outcome == "busy"
    assert await status_of(world, pid) == "pending"
    assert (await world.deps.store.load("plain")).description == ""
    assert (await proposal_apply.dismiss_proposal(world.conn, pid)).outcome == "busy"
    assert await status_of(world, pid) == "pending"
    assert frames.config == [] and frames.proposal == []


async def test_a_dismissed_or_withdrawn_row_is_closed(world, frames) -> None:
    pid = await _agent_change(world)
    d = await proposal_apply.dismiss_proposal(world.conn, pid)
    assert d.outcome == "dismissed" and d.view["status"] == "dismissed"
    assert frames.proposal == [("s1", "dismissed")] and frames.config == []
    res = await run(world, pid)
    assert res.outcome == "closed" and res.status == "dismissed"
    assert (await proposal_apply.dismiss_proposal(world.conn, pid)).outcome == "closed"
    assert (await world.deps.store.load("plain")).description == ""


async def test_a_dismiss_of_an_applied_row_is_closed(world) -> None:
    pid = await _agent_change(world)
    await run(world, pid)
    res = await proposal_apply.dismiss_proposal(world.conn, pid)
    assert res.outcome == "closed" and res.status == "applied"


async def test_an_unknown_id_raises_not_found(world) -> None:
    with pytest.raises(proposal_apply.ProposalNotFound):
        await run(world, 999)
    with pytest.raises(proposal_apply.ProposalNotFound):
        await proposal_apply.dismiss_proposal(world.conn, 999)


async def test_an_unexpected_exception_is_not_caught_or_marked(world, monkeypatch) -> None:
    async def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(proposal_apply.agent_service, "change_agent", boom)
    pid = await _agent_change(world)
    with pytest.raises(RuntimeError):
        await run(world, pid)
    assert await status_of(world, pid) == "pending"


# --- frames --------------------------------------------------------------------------------------


async def test_config_changed_is_broadcast_once_per_apply_after_the_proposal_frame(
    world, frames
) -> None:
    pid = await make(
        world, "agent", "change", {"description": "d", "max_iterations": 9}, agent="plain"
    )
    await run(world, pid)
    assert frames.proposal == [("s1", "applied")]
    assert frames.config == [
        {
            "type": "config_changed",
            "kind": "agent",
            "agent": "plain",
            "target_id": None,
            "fields": ["description", "max_iterations"],
            "session_id": "s1",
            "proposal_id": pid,
            "at": NOW.isoformat(),
        }
    ]
    await run(world, pid)  # already applied: no second frame
    assert len(frames.config) == 1 and len(frames.proposal) == 1


async def test_a_routine_apply_hides_the_anchor_key_from_the_fields(world, frames) -> None:
    pid = await _routine_create(world)
    await run(world, pid)
    assert frames.config[0]["fields"] == ["name", "prompt", "schedule"]
