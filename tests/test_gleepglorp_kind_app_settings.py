"""The ``app_settings`` kind (Mission 36 F5 L4a, DD8): page addressing, the fields and their
validation, the zone-mode rule, the warnings, approve through the app-settings service (stale,
post-commit hooks, the ``config_changed`` frame) and the fill record for Knowledge indexing.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from tests._gleepglorp_seed import seed
from the_one import time_zones
from the_one.agent._context import TurnContext, current_turn
from the_one.agent.service import AgentWriteDeps
from the_one.db import _write_lock
from the_one.db.repositories import (
    AppMetadataRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.gleepglorp import kinds, views
from the_one.gleepglorp.fill.store import GleepGlorpFillRepository, NewFill, fill_view
from the_one.gleepglorp.fill.tool import FillFormTool
from the_one.gleepglorp.kinds import app_settings as app_kind
from the_one.gleepglorp.proposals import apply as proposal_apply
from the_one.gleepglorp.proposals.shape import ShapeError
from the_one.gleepglorp.proposals.store import (
    GleepGlorpProposalRepository,
    NewProposal,
    proposal_view,
)
from the_one.gleepglorp.proposals.tool import ProposeChangeTool
from the_one.knowledge.settings import (
    CHUNKING_KEY,
    EMBEDDING_KEY,
    MONITORING_KEY,
    load_knowledge_settings,
)

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
# The module's own hook, captured before the ``world`` fixture swaps in a stand-in.
_REAL_APPLY_MONITORING = app_kind._apply_monitoring
DT = "date-and-time"
KI = "knowledge-indexing"


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
    ns.deps = AgentWriteDeps(
        store=SQLiteAgentStore(conn, enc),
        mcp_repo=MCPSourceRepository(conn, enc),
        provider_repo=LLMProviderRepository(conn, enc),
        secret_repo=SecretRepository(conn, enc),
        tool_config_repo=ToolConfigRepository(conn, enc),
    )
    ns.repo = GleepGlorpProposalRepository(conn)
    ns.meta = AppMetadataRepository(conn)
    # explicit stored state: pin the mode, since ``system`` resolves from the host
    await time_zones.save_setting(
        conn, time_zones.TimeZoneSetting(mode="zone", zone="Europe/Paris")
    )
    await ns.meta.set(CHUNKING_KEY, json.dumps({"size_chars": 800, "overlap_chars": 100}))
    await ns.meta.set(
        MONITORING_KEY, json.dumps({"watch_enabled": True, "reconcile_interval_seconds": 600})
    )
    ns.hooks = SimpleNamespace(poke=0, monitoring=[], boom=False)

    def poke() -> None:
        ns.hooks.poke += 1

    async def apply_monitoring(monitoring) -> None:
        ns.hooks.monitoring.append(monitoring)
        if ns.hooks.boom:
            raise RuntimeError("watcher down")

    monkeypatch.setattr(app_kind, "_poke", poke)
    monkeypatch.setattr(app_kind, "_apply_monitoring", apply_monitoring)
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


async def norm(world, changes, *, mode="propose", action="change", agent=None, target=None):
    return await kinds.normalize(
        "app_settings",
        action,
        kinds.target_args("app_settings", agent, None, None, target),
        changes,
        conn=world.conn,
        now=NOW,
        zone=UTC,
        enc=world.enc,
        mode=mode,
    )


async def refused(world, changes, **kw) -> str:
    with pytest.raises(ShapeError) as e:
        await norm(world, changes, **kw)
    return str(e.value)


async def make(world, changes, *, session="s1") -> int:
    n = await norm(world, changes)
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


async def raw(world, key):
    return await world.meta.get(key)


# --- the kind's declaration ---------------------------------------------------------------


def test_the_kind_is_registered_last_and_declared() -> None:
    k = app_kind.KIND
    assert kinds.REGISTRY[-1] is k and kinds.KINDS[-1] == "app_settings"
    assert k.addressing == "page" and k.label == "app settings"
    assert k.actions == ("change",) and k.fillable == ("change",)
    assert k.keyerror_is_gone is False and k.resolve_target is None
    assert k.operator_only == (
        "embedding_backend",
        "embedding_model_id",
        "embedding_dim",
        "vector_store",
    )
    assert "app_settings" in kinds.FILLABLE
    assert "\n" not in k.summary and len(k.summary) < 100


def test_the_six_fields_each_name_their_page_and_stored_location() -> None:
    by = {f.name: f for f in app_kind.KIND.fields}
    assert list(by) == [
        "time_zone_mode",
        "time_zone",
        "chunk_size_chars",
        "chunk_overlap_chars",
        "watch_enabled",
        "reconcile_interval_seconds",
    ]
    assert {n: f.applies_to for n, f in by.items()} == {
        "time_zone_mode": (DT,),
        "time_zone": (DT,),
        "chunk_size_chars": (KI,),
        "chunk_overlap_chars": (KI,),
        "watch_enabled": (KI,),
        "reconcile_interval_seconds": (KI,),
    }
    assert {n: f.path for n, f in by.items()} == {
        "time_zone_mode": ("time_zone", "mode"),
        "time_zone": ("time_zone", "zone"),
        "chunk_size_chars": ("knowledge.chunking", "size_chars"),
        "chunk_overlap_chars": ("knowledge.chunking", "overlap_chars"),
        "watch_enabled": ("knowledge.monitoring", "watch_enabled"),
        "reconcile_interval_seconds": ("knowledge.monitoring", "reconcile_interval_seconds"),
    }
    assert (by["chunk_size_chars"].min, by["chunk_size_chars"].max) == (200, 2000)
    assert (by["reconcile_interval_seconds"].min, by["reconcile_interval_seconds"].max) == (
        10,
        86400,
    )
    refused_fill = "Date and time saves as soon as you choose; I'll propose it instead."
    assert {n for n, f in by.items() if f.fill_refused} == {"time_zone_mode", "time_zone"}
    assert by["time_zone"].fill_refused == refused_fill == by["time_zone_mode"].fill_refused


async def test_the_fields_view_shows_the_page_of_each_field_and_none_on_enabled(world) -> None:
    app = await views.read(world.conn, world.enc, "fields", "app_settings")
    pages = {f["name"]: f["applies_to"] for f in app["fields"]}
    assert pages["time_zone"] == [DT] and pages["watch_enabled"] == [KI]
    tool = await views.read(world.conn, world.enc, "fields", "tool_config")
    by = {f["name"]: f for f in tool["fields"]}
    assert "applies_to" not in by["enabled"] and by["search_backend"]["applies_to"] == [
        "web_search"
    ]


# --- page addressing ----------------------------------------------------------------------


async def test_the_page_comes_from_the_fields_named(world) -> None:
    n = await norm(world, {"chunk_size_chars": 900})
    assert (n.kind, n.action, n.agent_name, n.target_id) == ("app_settings", "change", None, KI)
    assert n.target_key == f"app_settings:{KI}"
    n = await norm(world, {"time_zone": "Asia/Tokyo"})
    assert n.target_id == DT and n.target_key == f"app_settings:{DT}"


async def test_fields_from_both_pages_are_refused(world) -> None:
    msg = await refused(world, {"time_zone": "Asia/Tokyo", "chunk_size_chars": 900})
    assert msg == (
        "One proposal changes one Settings page; propose Date and time and Knowledge indexing "
        "separately."
    )


def test_an_agent_or_target_is_refused_by_the_existing_sentence() -> None:
    for kw in ({"agent": "plain"}, {"target": "date-and-time"}):
        with pytest.raises(ShapeError) as e:
            kinds.target_args("app_settings", **kw)
        assert str(e.value) == "App settings take no agent or target; name the fields to change."


@pytest.mark.parametrize("mode", ["propose", "fill"])
async def test_create_is_refused_by_the_action_gate(world, mode) -> None:
    verb = "by a proposal" if mode == "propose" else "by filling its form"
    assert await refused(world, {"chunk_size_chars": 900}, action="create", mode=mode) == (
        f"A app settings can't be created {verb}."
    )


@pytest.mark.parametrize(
    "field", ["embedding_backend", "embedding_model_id", "embedding_dim", "vector_store"]
)
@pytest.mark.parametrize("mode", ["propose", "fill"])
async def test_the_fixed_embedding_settings_are_refused_with_the_sentence(
    world, field, mode
) -> None:
    msg = await refused(world, {field: "x"}, mode=mode)
    assert msg == "The embedding model and vector store are fixed; they can't be changed."


# --- validation at normalize --------------------------------------------------------------


async def test_the_zone_is_an_iana_name(world) -> None:
    msg = await refused(world, {"time_zone": "Mars/Olympus"})
    assert msg == "Unknown time zone 'Mars/Olympus'. Use an IANA name such as Asia/Tokyo."
    assert "text" in await refused(world, {"time_zone": 5})
    assert (
        await refused(world, {"time_zone_mode": "auto"}) == "time_zone_mode must be system or zone."
    )


async def test_zone_mode_with_no_zone_stored_or_named_is_refused(world) -> None:
    await time_zones.save_setting(world.conn, time_zones.TimeZoneSetting(mode="system"))
    msg = await refused(world, {"time_zone_mode": "zone"})
    assert msg == "Choose a time zone when time_zone_mode is zone."
    # with the zone named, or already stored, it is fine
    assert (await norm(world, {"time_zone_mode": "zone", "time_zone": "Asia/Tokyo"})).changes == {
        "time_zone_mode": "zone",
        "time_zone": "Asia/Tokyo",
    }
    await time_zones.save_setting(
        world.conn, time_zones.TimeZoneSetting(mode="system", zone="Asia/Tokyo")
    )
    assert (await norm(world, {"time_zone_mode": "zone"})).changes == {"time_zone_mode": "zone"}


async def test_switching_to_system_keeps_the_stored_zone(world) -> None:
    n = await norm(world, {"time_zone_mode": "system"})
    assert n.changes == {"time_zone_mode": "system"} and n.base == {"time_zone_mode": "zone"}


async def test_chunking_and_monitoring_validate_through_their_models(world) -> None:
    assert "from 200 to 2000" in await refused(world, {"chunk_size_chars": 100})
    assert "whole number" in await refused(world, {"chunk_size_chars": True})
    assert "whole number" in await refused(world, {"reconcile_interval_seconds": "60"})
    assert "from 10 to 86400" in await refused(world, {"reconcile_interval_seconds": 5})
    assert "true or false" in await refused(world, {"watch_enabled": "off"})
    # overlap is at most half the size: the model's message, in the model-facing names
    msg = await refused(world, {"chunk_overlap_chars": 500})
    assert msg == ("chunk_overlap_chars (500) must not exceed 50% of chunk_size_chars (800)")
    # a size that makes the STORED overlap too big is refused too
    await world.meta.set(CHUNKING_KEY, json.dumps({"size_chars": 800, "overlap_chars": 150}))
    msg = await refused(world, {"chunk_size_chars": 200})
    assert "chunk_overlap_chars (150)" in msg and "chunk_size_chars (200)" in msg


async def test_the_base_holds_the_stored_values_of_the_named_fields(world) -> None:
    n = await norm(world, {"chunk_size_chars": 900, "watch_enabled": False})
    assert n.base == {"chunk_size_chars": 800, "watch_enabled": True}
    n = await norm(world, {"time_zone": "Asia/Tokyo"})
    assert n.base == {"time_zone": "Europe/Paris"}  # the mode is not named, so not in the base


async def test_a_zone_alone_while_the_mode_is_system_also_sets_the_mode_to_zone(world) -> None:
    await time_zones.save_setting(world.conn, time_zones.TimeZoneSetting(mode="system"))
    n = await norm(world, {"time_zone": "Asia/Tokyo"})
    assert list(n.changes) == ["time_zone_mode", "time_zone"]
    assert n.changes == {"time_zone_mode": "zone", "time_zone": "Asia/Tokyo"}
    assert n.base == {"time_zone_mode": "system", "time_zone": None}
    pid = await make(world, {"time_zone": "Asia/Tokyo"})
    view = await view_of(world, pid)
    assert view["changes"] == {"time_zone_mode": "zone", "time_zone": "Asia/Tokyo"}
    assert view["labels"]["time_zone_mode"] == "Time zone mode"
    # in zone mode, the zone alone is the one row
    await time_zones.save_setting(
        world.conn, time_zones.TimeZoneSetting(mode="zone", zone="Europe/Paris")
    )
    assert (await norm(world, {"time_zone": "Asia/Tokyo"})).changes == {"time_zone": "Asia/Tokyo"}


# --- the card and the warnings -------------------------------------------------------------


async def test_the_card_title_is_the_pages_label(world) -> None:
    for i, (changes, title) in enumerate(
        (
            ({"time_zone": "Asia/Tokyo"}, "Change Date and time"),
            ({"chunk_size_chars": 900}, "Change Knowledge indexing"),
        )
    ):
        view = await view_of(world, await make(world, changes, session=f"card{i}"))
        assert view["title"] == title and view["target_gone"] is False
        assert view["agent_name"] is None


async def test_the_warnings(world) -> None:
    async def warns(changes, mode="propose"):
        pid = await make(world, changes, session=f"w{len(str(changes))}{hash(str(changes)) % 999}")
        return await app_kind.warnings(world.conn, world.enc, await world.repo.get(pid), mode)

    assert await warns({"time_zone": "Asia/Tokyo"}) == [
        "Routines' times follow the new zone from now on."
    ]
    assert await warns({"time_zone_mode": "system"}) == [
        "Routines' times follow the new zone from now on."
    ]
    chunk = (
        "This applies to files indexed from now on; reindex a knowledge base to apply it to "
        "existing files."
    )
    assert await warns({"chunk_size_chars": 900}) == [chunk]
    assert await warns({"chunk_overlap_chars": 50}) == [chunk]
    off = "Folders stop being watched; changes are picked up only by the periodic check."
    assert await warns({"watch_enabled": False}) == [off]
    assert await warns({"watch_enabled": True}) == []
    assert await warns({"reconcile_interval_seconds": 30}) == []
    assert await warns({"chunk_size_chars": 900, "watch_enabled": False}) == [chunk, off]
    pid = await make(world, {"watch_enabled": False}, session="open")
    assert (await view_of(world, pid))["warnings"] == [off]


# --- approve ----------------------------------------------------------------------------------


async def test_approve_a_time_change_writes_it_pokes_and_the_frame_carries_the_page(
    world, frames
) -> None:
    pid = await make(world, {"time_zone": "Asia/Tokyo"})
    res = await run(world, pid)
    assert res.outcome == "applied"
    setting = await time_zones.load_setting(world.conn)
    assert (setting.mode, setting.zone) == ("zone", "Asia/Tokyo")
    assert world.hooks.poke == 1 and world.hooks.monitoring == []
    assert res.view["result"]["summary"] == "Changed Time zone on Date and time"
    assert (await world.repo.get(pid)).status == "applied"
    assert frames.proposal and frames.proposal[-1][1] == "applied"
    [frame] = frames.config
    assert frame["kind"] == "app_settings" and frame["target_id"] == DT
    assert frame["agent"] is None and frame["fields"] == ["time_zone"]


async def test_approve_a_knowledge_change_writes_only_the_keys_it_changes(world, frames) -> None:
    emb_before = await raw(world, EMBEDDING_KEY)
    mon_before = await raw(world, MONITORING_KEY)
    pid = await make(world, {"chunk_size_chars": 1000, "chunk_overlap_chars": 120})
    res = await run(world, pid)
    assert res.outcome == "applied"
    assert json.loads(await raw(world, CHUNKING_KEY)) == {"size_chars": 1000, "overlap_chars": 120}
    assert await raw(world, EMBEDDING_KEY) == emb_before  # untouched, read raw
    assert await raw(world, MONITORING_KEY) == mon_before
    assert world.hooks.poke == 0 and world.hooks.monitoring == []  # chunking is not live
    assert frames.config[0]["target_id"] == KI
    assert (
        res.view["result"]["summary"] == "Changed Chunk size, Chunk overlap on Knowledge indexing"
    )


async def test_a_monitoring_change_applies_to_the_watcher_after_commit(world, frames) -> None:
    pid = await make(world, {"watch_enabled": False, "reconcile_interval_seconds": 60})
    assert (await run(world, pid)).outcome == "applied"
    [monitoring] = world.hooks.monitoring
    assert (monitoring.watch_enabled, monitoring.reconcile_interval_seconds) == (False, 60)
    assert world.hooks.poke == 0


async def test_the_real_hook_reaches_the_watch_manager(world, frames, monkeypatch) -> None:
    from the_one.knowledge import watcher

    applied = []

    class Manager:
        async def apply_settings(self, monitoring) -> None:
            applied.append(monitoring)

    monkeypatch.setattr(watcher, "get_manager", lambda: Manager())
    # the ``world`` fixture replaced the hook with a stand-in: put the module's own back
    monkeypatch.setattr(app_kind, "_apply_monitoring", _REAL_APPLY_MONITORING)
    pid = await make(world, {"watch_enabled": False})
    assert (await run(world, pid)).outcome == "applied"
    assert [m.watch_enabled for m in applied] == [False]


async def test_a_raising_post_commit_hook_still_yields_an_applied_proposal_with_its_frames(
    world, frames, caplog
) -> None:
    world.hooks.boom = True
    pid = await make(world, {"watch_enabled": False})
    with caplog.at_level(logging.WARNING, logger="the_one.app_settings_service"):
        res = await run(world, pid)
    assert res.outcome == "applied"  # never already_applied
    assert (await world.repo.get(pid)).status == "applied"
    assert frames.proposal and frames.proposal[-1][1] == "applied"
    [frame] = frames.config
    assert frame["kind"] == "app_settings" and frame["target_id"] == KI
    assert json.loads(await raw(world, MONITORING_KEY))["watch_enabled"] is False
    assert any("folder watcher" in r.getMessage() for r in caplog.records)


async def test_no_hook_runs_when_the_apply_is_stale_or_already_resolved(world, frames) -> None:
    pid = await make(world, {"time_zone": "Asia/Tokyo"})
    await time_zones.save_setting(
        world.conn, time_zones.TimeZoneSetting(mode="zone", zone="America/Denver")
    )
    res = await run(world, pid)
    assert res.outcome == "stale" and world.hooks.poke == 0
    assert (await time_zones.load_setting(world.conn)).zone == "America/Denver"
    assert (await run(world, pid, override=True)).outcome == "applied"
    assert world.hooks.poke == 1
    again = await run(world, pid)  # already resolved: nothing runs again
    assert again.outcome == "already_applied" and world.hooks.poke == 1
    assert len(frames.config) == 1


async def test_a_stale_knowledge_change_names_the_field_and_another_field_is_not_stale(
    world, frames
) -> None:
    pid = await make(world, {"chunk_size_chars": 1000, "watch_enabled": False})
    await world.meta.set(
        MONITORING_KEY, json.dumps({"watch_enabled": True, "reconcile_interval_seconds": 30})
    )  # another field of the same record moved: not stale
    await world.meta.set(CHUNKING_KEY, json.dumps({"size_chars": 700, "overlap_chars": 100}))
    res = await run(world, pid)
    assert res.outcome == "stale"
    assert res.stale == [
        {"field": "chunk_size_chars", "label": "Chunk size", "current": 700, "proposed": 1000}
    ]
    assert world.hooks.monitoring == []
    assert (await run(world, pid, override=True)).outcome == "applied"


async def test_a_zone_change_that_adds_the_mode_touches_and_bases_both(world, frames) -> None:
    await time_zones.save_setting(world.conn, time_zones.TimeZoneSetting(mode="system"))
    pid = await make(world, {"time_zone": "Asia/Tokyo"})
    # the mode moved to zone (with another zone) since: both touched fields are stale
    await time_zones.save_setting(
        world.conn, time_zones.TimeZoneSetting(mode="zone", zone="Europe/Paris")
    )
    res = await run(world, pid)
    assert res.outcome == "stale"
    assert {r["field"] for r in res.stale} == {"time_zone_mode", "time_zone"}
    assert (await run(world, pid, override=True)).outcome == "applied"
    setting = await time_zones.load_setting(world.conn)
    assert (setting.mode, setting.zone) == ("zone", "Asia/Tokyo")


async def test_a_service_refusal_carries_items_and_writes_nothing(world, frames) -> None:
    pid = await make(world, {"chunk_size_chars": 1000})
    await world.conn.execute(
        "UPDATE gleepglorp_proposals SET changes = ? WHERE id = ?",
        ('{"chunk_size_chars": 50}', pid),
    )
    await world.conn.commit()
    res = await run(world, pid, override=True)
    assert res.outcome == "failed" and res.view["result"]["errors"]
    assert json.loads(await raw(world, CHUNKING_KEY))["size_chars"] == 800


async def test_a_proposal_writes_nothing_before_an_approve(world) -> None:
    before = (await raw(world, CHUNKING_KEY), await raw(world, MONITORING_KEY))
    setting = await time_zones.load_setting(world.conn)
    tool = ProposeChangeTool(agent_name="GleepGlorp")
    tool.bind_agent(SimpleNamespace(messages=[]))
    token = current_turn.set(TurnContext(session_id="s1"))
    try:
        for changes in ({"chunk_size_chars": 900}, {"time_zone": "Asia/Tokyo"}):
            out = await tool.execute(kind="app_settings", action="change", changes=changes)
            assert out.startswith("Proposal "), out
        out = await tool.execute(
            kind="app_settings", action="change", target="date-and-time", changes={"time_zone": "x"}
        )
        assert "take no agent or target" in out
    finally:
        current_turn.reset(token)
    assert (await raw(world, CHUNKING_KEY), await raw(world, MONITORING_KEY)) == before
    assert await time_zones.load_setting(world.conn) == setting
    assert world.hooks.poke == 0


# --- the fill record ----------------------------------------------------------------------------


def _page(section):
    return {"line": "Settings", "descriptor": {"destination": "settings", "section": section}}


async def test_the_date_and_time_fields_are_not_fillable(world) -> None:
    fill_tool = FillFormTool(agent_name="GleepGlorp")
    token = current_turn.set(TurnContext(session_id="s2", page=_page("date-and-time")))
    try:
        for changes in ({"time_zone": "Asia/Tokyo"}, {"time_zone_mode": "system"}):
            out = await fill_tool.execute(kind="app_settings", action="change", changes=changes)
            assert out == "Date and time saves as soon as you choose; I'll propose it instead."
    finally:
        current_turn.reset(token)
    assert await GleepGlorpFillRepository(world.conn).list_for_session("s2") == []


async def test_a_knowledge_indexing_fill_records_with_the_page_key(world) -> None:
    fill_tool = FillFormTool(agent_name="GleepGlorp")
    token = current_turn.set(TurnContext(session_id="s3", page=_page("knowledge-indexing")))
    try:
        out = await fill_tool.execute(
            kind="app_settings",
            action="change",
            changes={"chunk_size_chars": 900, "watch_enabled": False},
        )
        assert out.startswith("Fill "), out
    finally:
        current_turn.reset(token)
    [fill] = await GleepGlorpFillRepository(world.conn).list_for_session("s3")
    assert (fill.kind, fill.action, fill.target_id) == ("app_settings", "change", KI)
    assert fill.target_key == f"app_settings:{KI}"
    assert fill.changes == {"chunk_size_chars": 900, "watch_enabled": False}
    view = await fill_view(world.conn, fill)
    assert view["title"] == "Change Knowledge indexing" and view["target_gone"] is False
    assert view["stale"] == []
    assert json.loads(await raw(world, CHUNKING_KEY))["size_chars"] == 800  # a fill writes nothing


async def test_a_knowledge_indexing_fill_reports_stale_rows_when_the_value_moved(world) -> None:
    fills = GleepGlorpFillRepository(world.conn)
    n = await norm(world, {"chunk_size_chars": 900}, mode="fill")
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
    assert (await fill_view(world.conn, await fills.get(fill_id)))["stale"] == []
    await world.meta.set(CHUNKING_KEY, json.dumps({"size_chars": 700, "overlap_chars": 100}))
    view = await fill_view(world.conn, await fills.get(fill_id))
    assert view["stale"] == [
        {"field": "chunk_size_chars", "label": "Chunk size", "current": 700, "proposed": 900}
    ]
    assert (await load_knowledge_settings(world.conn)).chunking.size_chars == 700


def test_the_time_zone_text_fields_are_bounded() -> None:
    from the_one.gleepglorp.proposals import shape

    assert kinds.spec_for("app_settings", "time_zone_mode").max == 16
    zone = kinds.spec_for("app_settings", "time_zone")
    assert zone.max == 64
    assert shape._check_text(zone, "America/Argentina/ComodRivadavia")
    with pytest.raises(ShapeError, match="limited to 64"):
        shape._check_text(zone, "Z" * 65)
