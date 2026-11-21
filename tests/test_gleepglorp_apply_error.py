"""The ``ApplyError`` protocol between a kind's apply and ``apply_proposal`` (M36 F4 L1a, DD3).

A stub kind substituted through ``kinds.get`` tests the folding independently of any service.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from tests._gleepglorp_seed import seed
from the_one.agent.service import AgentWriteDeps
from the_one.db.repositories import (
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.gleepglorp import kinds
from the_one.gleepglorp.kinds.deps import KindDeps
from the_one.gleepglorp.kinds.errors import ApplyError, translate
from the_one.gleepglorp.proposals import apply as proposal_apply
from the_one.gleepglorp.proposals.store import (
    GleepGlorpProposalRepository,
    NewProposal,
    Proposal,
)

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


async def _utc():
    return UTC


@pytest.fixture
async def world(tmp_path):
    from the_one.db import _write_lock

    _write_lock.reset_for_test()
    ns = await seed(tmp_path)
    conn, enc = ns.conn, ns.enc
    ns.agent_deps = AgentWriteDeps(
        store=SQLiteAgentStore(conn, enc),
        mcp_repo=MCPSourceRepository(conn, enc),
        provider_repo=LLMProviderRepository(conn, enc),
        secret_repo=SecretRepository(conn, enc),
        tool_config_repo=ToolConfigRepository(conn, enc),
    )
    ns.repo = GleepGlorpProposalRepository(conn)
    yield ns
    await conn.close()


@pytest.fixture(autouse=True)
def frames(monkeypatch):
    out = SimpleNamespace(proposal=[], config=[])

    async def push(session_id, view):
        out.proposal.append((session_id, view["status"]))

    async def broadcast(payload):
        out.config.append(payload)

    monkeypatch.setattr(proposal_apply, "push_proposal_changed", push)
    monkeypatch.setattr("the_one.sessions._broadcast.broadcast_to_all", broadcast)
    return out


async def _proposal(world) -> int:
    return await world.repo.insert(
        NewProposal(
            session_id="s1",
            kind="agent",
            action="change",
            agent_name="plain",
            target_key="agent:plain",
            changes={"description": "Proposed"},
            base={"description": "x"},
        )
    )


def _stub(monkeypatch, apply, *, exists=True):
    """Substitute the agent kind with one whose ``apply`` is ``apply``."""
    real = kinds.get("agent")

    async def _exists(conn, deps, p):
        return exists

    stub = replace(real, apply=apply, exists=_exists)
    monkeypatch.setattr(kinds, "get", lambda name: stub if name == "agent" else real)
    return stub


async def _run(world, pid, deps=None):
    return await proposal_apply.apply_proposal(
        world.conn,
        deps or world.agent_deps,
        pid,
        override=False,
        now=NOW,
        zone=_utc,
        continue_chat=False,
    )


async def test_apply_error_with_stale_rows_gives_stale_and_leaves_the_row_open(
    world, monkeypatch
) -> None:
    rows = [{"field": "description", "label": "Description", "current": "a", "proposed": "b"}]

    async def apply(*a, **kw):
        raise ApplyError(stale=rows)

    _stub(monkeypatch, apply)
    pid = await _proposal(world)
    res = await _run(world, pid)
    assert res.outcome == "stale" and res.stale == rows
    assert (await world.repo.get(pid)).status == "pending"


async def test_apply_error_gone_withdraws_the_proposal(world, monkeypatch) -> None:
    async def apply(*a, **kw):
        raise ApplyError(gone=True)

    _stub(monkeypatch, apply)
    pid = await _proposal(world)
    res = await _run(world, pid)
    assert res.outcome == "gone"
    row = await world.repo.get(pid)
    assert row.status == "withdrawn" and row.result == {"reason": "gone"}


async def test_apply_error_items_mark_the_proposal_failed_with_those_items(
    world, monkeypatch
) -> None:
    items = [{"loc": ["description"], "msg": "too long"}]

    async def apply(*a, **kw):
        raise ApplyError(items)

    _stub(monkeypatch, apply)
    pid = await _proposal(world)
    res = await _run(world, pid)
    assert res.outcome == "failed"
    row = await world.repo.get(pid)
    assert row.status == "failed" and row.result == {"errors": items}


async def test_an_error_that_is_not_an_apply_error_propagates(world, monkeypatch) -> None:
    async def apply(*a, **kw):
        raise RuntimeError("boom")

    _stub(monkeypatch, apply)
    pid = await _proposal(world)
    with pytest.raises(RuntimeError, match="boom"):
        await _run(world, pid)
    assert (await world.repo.get(pid)).status == "pending"


async def test_already_resolved_passes_through_to_the_existing_handling(world, monkeypatch) -> None:
    pid = await _proposal(world)

    async def apply(conn, deps, p, **kw):
        # Another call dismisses the row after the first read; the kind's mark hook then
        # finds it no longer open and raises the private _AlreadyResolved, which a kind
        # never catches.
        await world.repo.mark(pid, "dismissed", from_statuses=("pending", "failed"))
        await kw["mark"](conn)

    _stub(monkeypatch, apply)
    res = await _run(world, pid)
    assert res.outcome == "closed" and res.status == "dismissed"


async def test_apply_proposal_accepts_agent_write_deps_and_kind_deps(world, monkeypatch) -> None:
    seen = []

    async def apply(conn, deps, p, **kw):
        seen.append(deps)
        raise ApplyError(gone=True)

    _stub(monkeypatch, apply)
    for deps in (world.agent_deps, KindDeps(agent=world.agent_deps)):
        pid = await _proposal(world)
        assert (await _run(world, pid, deps)).outcome == "gone"
    assert all(isinstance(d, KindDeps) and d.agent is world.agent_deps for d in seen)
    assert len(seen) == 2


def test_kind_deps_of_wraps_once() -> None:
    deps = SimpleNamespace()
    wrapped = KindDeps.of(deps)  # type: ignore[arg-type]
    assert wrapped.agent is deps and KindDeps.of(wrapped) is wrapped


# --- translate -------------------------------------------------------------------------------


def _p(kind, action, **kw) -> Proposal:
    return Proposal(
        id=1,
        session_id="s1",
        tool_call_id=None,
        kind=kind,
        action=action,
        agent_name="plain",
        target_id=kw.get("target_id"),
        target_key="k",
        changes=kw.get("changes", {}),
        base=None,
        status="pending",
        result=None,
        untrusted=False,
        untrusted_sources=[],
        created_at="",
        resolved_at=None,
    )


@pytest.mark.parametrize("kind", ["rule", "routine"])
async def test_translate_a_create_integrity_error_is_gone_for_rule_and_routine(kind) -> None:
    exc = sqlite3.IntegrityError("FOREIGN KEY constraint failed")
    err = await translate(exc, _p(kind, "create"), conn=None, zone=_utc)  # type: ignore[arg-type]
    assert isinstance(err, ApplyError) and err.gone


async def test_translate_an_agent_create_integrity_error_is_returned_unchanged() -> None:
    exc = sqlite3.IntegrityError("UNIQUE constraint failed")
    err = await translate(exc, _p("agent", "create"), conn=None, zone=_utc)  # type: ignore[arg-type]
    assert err is exc


async def test_translate_a_key_error_is_gone() -> None:
    err = await translate(KeyError("x"), _p("routine", "change"), conn=None, zone=_utc)  # type: ignore[arg-type]
    assert isinstance(err, ApplyError) and err.gone


async def test_a_routine_change_whose_target_vanished_raises_gone(world) -> None:
    p = _p("routine", "change", target_id="missing", changes={"prompt": "x"})
    kind = kinds.get("routine")
    with pytest.raises(ApplyError) as info:
        await kind.apply(
            world.conn,
            KindDeps.of(world.agent_deps),
            p,
            changes=p.changes,
            base={},
            override=False,
            now=NOW,
            zone=_utc,
            mark=None,
            runner=None,
            result={},
        )
    assert info.value.gone


async def test_an_agent_create_integrity_error_propagates_out_of_apply_proposal(
    world, monkeypatch
) -> None:
    from the_one.agent import service as agent_service

    async def boom(*a, **kw):
        raise sqlite3.IntegrityError("UNIQUE constraint failed: agents.name")

    monkeypatch.setattr(agent_service, "create_agent", boom)
    pid = await world.repo.insert(
        NewProposal(
            session_id="s1",
            kind="agent",
            action="create",
            agent_name="Brand new",
            target_key="agent:Brand new",
            changes={"name": "Brand new"},
        )
    )
    with pytest.raises(sqlite3.IntegrityError):
        await _run(world, pid)
