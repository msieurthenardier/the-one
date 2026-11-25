"""The ``knowledge_base`` kind (Mission 36 F5 L3a, DD5): normalize, targets, the operator-only
refusals, the card and its warnings, approve through the knowledge-base write service (stale,
gone, rename carry, failure items) and that a proposal or fill writes no row before an Approve.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from tests._gleepglorp_seed import seed
from the_one.agent._context import TurnContext, current_turn
from the_one.agent.service import AgentWriteDeps
from the_one.db import _write_lock
from the_one.db.models import KnowledgeBase
from the_one.db.repositories import (
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.gleepglorp import kinds
from the_one.gleepglorp.fill.store import GleepGlorpFillRepository
from the_one.gleepglorp.fill.tool import FillFormTool
from the_one.gleepglorp.kinds import knowledge_base as kb_kind
from the_one.gleepglorp.proposals import apply as proposal_apply
from the_one.gleepglorp.proposals.shape import ShapeError
from the_one.gleepglorp.proposals.store import (
    GleepGlorpProposalRepository,
    NewProposal,
    proposal_view,
)
from the_one.gleepglorp.proposals.tool import ProposeChangeTool
from the_one.knowledge import service as kb_service

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
KB = "kb1"  # "Docs KB", "Company docs", attached to the agent "wide"


async def _utc():
    return UTC


@pytest.fixture
async def world(tmp_path, monkeypatch):
    _write_lock.reset_for_test()
    ns = await seed(tmp_path)
    conn, enc = ns.conn, ns.enc

    async def _conn():
        return conn

    from the_one.config import settings

    monkeypatch.setattr("the_one.db.connection.get_connection", _conn)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    ns.warm_ups = []
    monkeypatch.setattr(kb_kind, "schedule_warm_up", lambda: ns.warm_ups.append(1))
    ns.deps = AgentWriteDeps(
        store=SQLiteAgentStore(conn, enc),
        mcp_repo=MCPSourceRepository(conn, enc),
        provider_repo=LLMProviderRepository(conn, enc),
        secret_repo=SecretRepository(conn, enc),
        tool_config_repo=ToolConfigRepository(conn, enc),
    )
    ns.repo = GleepGlorpProposalRepository(conn)
    ns.kbs = KnowledgeBaseRepository(conn)
    yield ns
    await conn.close()


@pytest.fixture
def frames(monkeypatch):
    out = SimpleNamespace(proposal=[], config=[])

    async def push(session_id, view):
        out.proposal.append((session_id, view["status"]))

    async def broadcast(payload):
        out.config.append(payload)

    monkeypatch.setattr(proposal_apply, "push_proposal_changed", push)
    monkeypatch.setattr("the_one.sessions._broadcast.broadcast_to_all", broadcast)
    return out


async def norm(world, action, changes, target=None, *, mode="propose"):
    return await kinds.normalize(
        "knowledge_base",
        action,
        kinds.target_args("knowledge_base", None, None, None, target),
        changes,
        conn=world.conn,
        now=NOW,
        zone=UTC,
        enc=world.enc,
        mode=mode,
    )


async def refused(world, action, changes, target=None, *, mode="propose") -> str:
    with pytest.raises(ShapeError) as e:
        await norm(world, action, changes, target, mode=mode)
    return str(e.value)


async def make(world, action, changes, target=None, *, session="s1") -> int:
    n = await norm(world, action, changes, target)
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
        )
    )


async def run(world, pid, *, override=False):
    return await proposal_apply.apply_proposal(
        world.conn, world.deps, pid, override=override, now=NOW, zone=_utc
    )


async def view_of(world, pid):
    return await proposal_view(world.conn, await world.repo.get(pid))


# --- the kind's declaration ---------------------------------------------------------------


def test_the_kind_is_registered_after_provider_and_declared() -> None:
    assert kinds.REGISTRY[5] is kb_kind.KIND and kinds.KINDS[5] == "knowledge_base"
    k = kb_kind.KIND
    assert k.addressing == "id" and k.target_noun == "A knowledge base"
    assert k.actions == ("create", "change") and k.fillable == ("create", "change")
    assert k.keyerror_is_gone is False
    assert k.operator_only == ("folders", "items", "path")
    assert [f.name for f in k.fields] == ["name", "description"]
    assert [f.name for f in k.fields if f.create_required] == ["name"]
    assert "knowledge_base" in kinds.FILLABLE
    assert [f["name"] for f in kinds.describe("knowledge_base")["fields"]] == [
        "name",
        "description",
    ]
    assert "\n" not in k.summary and len(k.summary) < 100


# --- normalize ----------------------------------------------------------------------------


async def test_a_create_normalizes_the_name_and_description(world) -> None:
    n = await norm(world, "create", {"name": "  Handbook ", "description": "HR"})
    assert (n.kind, n.action, n.target_id, n.base) == ("knowledge_base", "create", None, None)
    assert n.changes == {"name": "Handbook", "description": "HR"}
    assert n.target_key == "knowledge_base:new:Handbook"


async def test_a_create_needs_a_name_and_the_name_rule_applies(world) -> None:
    assert "needs name" in await refused(world, "create", {"description": "d"})
    assert await refused(world, "create", {"name": "   "})
    assert "text" in await refused(world, "create", {"name": "x", "description": 3})


async def test_a_change_reads_the_base_of_the_named_fields_only(world) -> None:
    n = await norm(world, "change", {"description": "Fresh"}, KB)
    assert n.target_id == KB and n.target_key == f"knowledge_base:{KB}"
    assert n.changes == {"description": "Fresh"} and n.base == {"description": "Company docs"}
    n = await norm(world, "change", {"name": "Docs 2", "description": "x"}, "Docs KB")
    assert n.target_id == KB and n.base == {"name": "Docs KB", "description": "Company docs"}


async def test_targets_by_id_or_name_and_an_ambiguous_name_lists_name_and_id(world) -> None:
    await world.kbs.create(KnowledgeBase(id="kb2", name="Docs KB", description="Twin"))
    assert "No knowledge base named" in await refused(world, "change", {"name": "x"}, "Nope")
    assert "Say which knowledge base" in await refused(world, "change", {"name": "x"}, None)
    msg = await refused(world, "change", {"description": "x"}, "Docs KB")
    assert "Docs KB (kb1)" in msg and "Docs KB (kb2)" in msg and "id instead" in msg
    n = await norm(world, "change", {"description": "x"}, "kb2")
    assert n.target_id == "kb2"


async def test_a_change_to_a_name_another_base_has_is_allowed(world) -> None:
    await world.kbs.create(KnowledgeBase(id="kb2", name="Other"))
    n = await norm(world, "change", {"name": "Other"}, KB)
    assert n.changes == {"name": "Other"}


@pytest.mark.parametrize("key", ["folders", "items", "path"])
@pytest.mark.parametrize("mode", ["propose", "fill"])
async def test_operator_only_fields_are_refused_with_a_sentence_linking_the_page(
    world, key, mode
) -> None:
    for action, target in (("create", None), ("change", KB)):
        changes = {"name": "x", key: ["/home/me/docs"]}
        msg = await refused(world, action, changes, target, mode=mode)
        assert "[Library](#library)" in msg and "only by the operator" in msg, msg
        assert "Allowed fields" not in msg


async def test_an_unknown_field_names_the_allowed_ones(world) -> None:
    msg = await refused(world, "change", {"color": "red"}, KB)
    assert "Allowed fields: name, description" in msg


# --- no row before an approve --------------------------------------------------------------


async def _counts(conn) -> tuple[int, ...]:
    out = []
    for table in ("knowledge_bases", "secrets", "kb_items"):
        async with conn.execute(f"SELECT COUNT(*) FROM {table}") as cur:  # noqa: S608
            out.append((await cur.fetchone())[0])
    return tuple(out)


async def test_a_proposal_and_a_fill_write_no_knowledge_base_row(world) -> None:
    before = await _counts(world.conn)
    snapshot = [(k.id, k.name, k.description) for k in await world.kbs.list()]
    tool = ProposeChangeTool(agent_name="GleepGlorp")
    tool.bind_agent(SimpleNamespace(messages=[]))
    token = current_turn.set(TurnContext(session_id="s1"))
    try:
        for args in (
            {"kind": "knowledge_base", "action": "create", "changes": {"name": "Brand new"}},
            {
                "kind": "knowledge_base",
                "action": "change",
                "target": KB,
                "changes": {"description": "Proposed"},
            },
        ):
            out = await tool.execute(**args)
            assert out.startswith("Proposal "), out
    finally:
        current_turn.reset(token)
    fill_tool = FillFormTool(agent_name="GleepGlorp")
    page = {"line": "Library", "descriptor": {"destination": "library"}}
    token = current_turn.set(TurnContext(session_id="s2", page=page))
    try:
        out = await fill_tool.execute(
            kind="knowledge_base", action="change", target=KB, changes={"name": "Filled"}
        )
        assert out.startswith("Fill "), out
        out = await fill_tool.execute(
            kind="knowledge_base", action="create", changes={"name": "Filled new"}
        )
        assert out.startswith("Fill "), out
    finally:
        current_turn.reset(token)
    assert await _counts(world.conn) == before
    assert [(k.id, k.name, k.description) for k in await world.kbs.list()] == snapshot
    fills = await GleepGlorpFillRepository(world.conn).list_for_session("s2")
    assert {f.kind for f in fills} == {"knowledge_base"}


# --- the card, the summary and the warnings ------------------------------------------------


async def test_the_card_names_the_base_by_a_lookup_and_knows_when_it_is_gone(world) -> None:
    pid = await make(world, "create", {"name": "Fresh"})
    view = await view_of(world, pid)
    assert view["title"] == "Create knowledge base “Fresh”" and view["target_gone"] is False
    pid = await make(world, "change", {"description": "x"}, KB, session="s2")
    view = await view_of(world, pid)
    assert view["title"] == "Change knowledge base “Docs KB”" and view["target_gone"] is False
    await world.kbs.delete(KB)
    assert (await view_of(world, pid))["target_gone"] is True


async def test_a_create_warns_about_folders_in_each_mode(world) -> None:
    pid = await make(world, "create", {"name": "Fresh"})
    p = await world.repo.get(pid)
    assert await kb_kind.warnings(world.conn, world.enc, p) == [
        "Add its folders on the page after approving."
    ]
    assert await kb_kind.warnings(world.conn, world.enc, p, "fill") == [
        "Add its folders on the page after saving."
    ]
    assert (await view_of(world, pid))["warnings"] == [
        "Add its folders on the page after approving."
    ]


async def test_a_rename_of_a_base_that_agents_use_names_them(world) -> None:
    pid = await make(world, "change", {"name": "Docs 2"}, KB)
    [warning] = (await view_of(world, pid))["warnings"]
    assert "(wide)" in warning and "new name" in warning and "keeps it off" in warning
    # a description-only change, or a rename of an unused base, carries no warning
    pid = await make(world, "change", {"description": "x"}, KB, session="s2")
    assert (await view_of(world, pid))["warnings"] == []
    await world.kbs.create(KnowledgeBase(id="kb9", name="Unused"))
    pid = await make(world, "change", {"name": "Unused 2"}, "kb9", session="s3")
    assert (await view_of(world, pid))["warnings"] == []


# --- approve ------------------------------------------------------------------------------


async def test_approve_a_create_writes_the_row_with_a_generated_id_and_warms_up(
    world, frames
) -> None:
    pid = await make(world, "create", {"name": "Fresh", "description": "New docs"})
    res = await run(world, pid)
    assert res.outcome == "applied"
    kb_id = res.view["target_id"]
    assert len(kb_id) == 12
    kb = await world.kbs.get(kb_id)
    assert (kb.name, kb.description) == ("Fresh", "New docs")
    assert world.warm_ups == [1]
    assert res.view["result"]["summary"] == "Created knowledge base Fresh"
    assert frames.config and frames.config[0]["target_id"] == kb_id


async def test_approve_a_change_writes_the_named_fields_and_marks_in_the_transaction(
    world, frames
) -> None:
    pid = await make(world, "change", {"description": "Updated"}, KB)
    res = await run(world, pid)
    assert res.outcome == "applied"
    assert (await world.kbs.get(KB)).description == "Updated"
    assert (await world.kbs.get(KB)).name == "Docs KB"
    assert res.view["result"]["summary"] == "Changed Description on knowledge base Docs KB"
    assert (await world.repo.get(pid)).status == "applied"
    assert world.warm_ups == []


async def test_approve_a_rename_carries_into_the_agents_disabled_tools(world, frames) -> None:
    from the_one.knowledge.tool_provider import compute_tool_names

    old = compute_tool_names([KnowledgeBase(id=KB, name="Docs KB")], agent_name="x")[KB]
    new = compute_tool_names([KnowledgeBase(id=KB, name="Handbook")], agent_name="x")[KB]
    wide = await world.deps.store.load("wide")
    await world.deps.store.save(wide.model_copy(update={"disabled_tools": [old, "shell"]}))
    pid = await make(world, "change", {"name": "Handbook"}, KB)
    assert (await run(world, pid)).outcome == "applied"
    assert (await world.deps.store.load("wide")).disabled_tools == [new, "shell"]
    assert (await world.kbs.get(KB)).name == "Handbook"


async def test_a_stale_change_gives_the_rows_and_override_applies(world, frames) -> None:
    pid = await make(world, "change", {"name": "Mine", "description": "Mine too"}, KB)
    await world.conn.execute("UPDATE knowledge_bases SET name='Hand-edited' WHERE id=?", (KB,))
    await world.conn.commit()
    res = await run(world, pid)
    assert res.outcome == "stale"
    assert res.stale == [
        {"field": "name", "label": "Name", "current": "Hand-edited", "proposed": "Mine"}
    ]
    assert (await world.repo.get(pid)).status == "pending"
    assert (await world.kbs.get(KB)).name == "Hand-edited"
    assert (await run(world, pid, override=True)).outcome == "applied"
    assert (await world.kbs.get(KB)).name == "Mine"


async def test_a_deleted_target_withdraws_the_proposal_as_gone(world, frames) -> None:
    pid = await make(world, "change", {"description": "x"}, KB)
    await world.kbs.delete(KB)
    res = await run(world, pid)
    assert res.outcome == "gone" and (await world.repo.get(pid)).status == "withdrawn"
    assert frames.config == []


async def test_a_service_refusal_carries_items_and_writes_nothing(world, frames) -> None:
    pid = await make(world, "change", {"name": "Fine"}, KB)
    # forge a stored change the normalizer would have refused
    await world.conn.execute(
        "UPDATE gleepglorp_proposals SET changes = ? WHERE id = ?", ('{"name": "   "}', pid)
    )
    await world.conn.commit()
    res = await run(world, pid, override=True)
    assert res.outcome == "failed"
    [err] = res.view["result"]["errors"]
    assert err["loc"] == ["name"]
    assert (await world.kbs.get(KB)).name == "Docs KB"


async def test_a_bare_key_error_from_the_service_is_not_hidden_as_gone(
    world, frames, monkeypatch
) -> None:
    """``keyerror_is_gone`` stays ``False``: the services raise typed not-found errors, so a
    stray ``KeyError`` is a bug that must surface."""

    async def boom(*a, **kw):
        raise KeyError("bug")

    monkeypatch.setattr(kb_service, "change_knowledge_base", boom)
    pid = await make(world, "change", {"description": "x"}, KB)
    with pytest.raises(KeyError):
        await run(world, pid)
    assert (await world.repo.get(pid)).status == "pending"


async def test_the_guard_runs_and_names_stay_free_text_guarded(world) -> None:
    from the_one.gleepglorp.proposals import guard

    changes = {"description": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"}
    assert await guard.check(world.conn, world.enc, changes) is not None
    assert kb_kind.KIND.relaxed_guard_keys == frozenset()


async def test_a_change_gives_a_stale_row_in_the_fill_view(world) -> None:
    fills = GleepGlorpFillRepository(world.conn)
    from the_one.gleepglorp.fill.store import NewFill, fill_view

    n = await norm(world, "change", {"description": "Mine"}, KB, mode="fill")
    fill_id, _ = await fills.insert(
        NewFill(
            session_id="s1",
            kind=n.kind,
            action=n.action,
            agent_name=None,
            target_id=n.target_id,
            target_key=n.target_key,
            changes=n.changes,
            base=n.base,
            tool_call_id=None,
            untrusted=False,
            untrusted_sources=[],
        )
    )
    view = await fill_view(world.conn, await fills.get(fill_id))
    assert view["stale"] == [] and view["title"] == "Change knowledge base “Docs KB”"
    await world.conn.execute("UPDATE knowledge_bases SET description='Moved' WHERE id=?", (KB,))
    await world.conn.commit()
    view = await fill_view(world.conn, await fills.get(fill_id))
    assert view["stale"] == [
        {"field": "description", "label": "Description", "current": "Moved", "proposed": "Mine"}
    ]
