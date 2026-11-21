"""Mission 36 F4 L1b: the store kind gates, ``target_id``, the shared frame helper and the
id-targeted resolution helpers (``resolve_by_id_or_name``, ``target_key``, ``Kind.resolve_target``).
"""

from __future__ import annotations

import pytest

from tests._schema_template import connect_template_db
from the_one.gleepglorp import kinds
from the_one.gleepglorp.fill.store import Fill, GleepGlorpFillRepository, NewFill, fill_view
from the_one.gleepglorp.proposals.shape import ShapeError
from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository, NewProposal


@pytest.fixture
async def conn(tmp_path):
    c = await connect_template_db(tmp_path / "t.db")
    yield c
    await c.close()


def new_proposal(**kw) -> NewProposal:
    return NewProposal(
        session_id="s1",
        kind=kw.pop("kind", "agent"),
        action="change",
        agent_name=kw.pop("agent_name", "a"),
        target_key=kw.pop("target_key", "agent:a"),
        changes={"description": "d"},
        **kw,
    )


def new_fill(**kw) -> NewFill:
    return NewFill(
        session_id="s1",
        kind=kw.pop("kind", "agent"),
        action="change",
        agent_name=kw.pop("agent_name", "a"),
        target_key=kw.pop("target_key", "agent:a"),
        changes={"description": "d"},
        **kw,
    )


# --- the stores' kind gates --------------------------------------------------------------


async def test_the_proposal_store_refuses_an_unknown_kind_and_writes_nothing(conn) -> None:
    repo = GleepGlorpProposalRepository(conn)
    with pytest.raises(ValueError, match="unsupported proposal kind"):
        await repo.insert(new_proposal(kind="bogus"))
    async with conn.execute("SELECT COUNT(*) FROM gleepglorp_proposals") as cur:
        assert (await cur.fetchone())[0] == 0


@pytest.mark.parametrize("kind", ["agent", "rule", "routine"])
async def test_the_proposal_store_accepts_every_registered_kind(conn, kind) -> None:
    repo = GleepGlorpProposalRepository(conn)
    pid = await repo.insert(new_proposal(kind=kind, target_key=f"{kind}:x"))
    assert (await repo.get(pid)).kind == kind


async def test_the_proposal_store_follows_the_registry_not_a_fixed_list(conn, monkeypatch) -> None:
    repo = GleepGlorpProposalRepository(conn)
    monkeypatch.setattr(kinds, "KINDS", (*kinds.KINDS, "stub"))
    pid = await repo.insert(new_proposal(kind="stub", target_key="stub:1"))
    assert (await repo.get(pid)).kind == "stub"


@pytest.mark.parametrize("kind", ["rule", "routine", "bogus"])
async def test_the_fill_store_refuses_a_kind_that_is_not_fillable(conn, kind) -> None:
    repo = GleepGlorpFillRepository(conn)
    with pytest.raises(ValueError, match="unsupported fill kind"):
        await repo.insert(new_fill(kind=kind))
    async with conn.execute("SELECT COUNT(*) FROM gleepglorp_fills") as cur:
        assert (await cur.fetchone())[0] == 0


async def test_the_fill_store_follows_the_fillable_list(conn, monkeypatch) -> None:
    repo = GleepGlorpFillRepository(conn)
    monkeypatch.setattr(kinds, "FILLABLE", (*kinds.FILLABLE, "stub"))
    fid, _ = await repo.insert(new_fill(kind="stub", target_key="stub:1"))
    assert (await repo.get(fid)).kind == "stub"


# --- target_id and a nullable agent_name -------------------------------------------------


async def test_a_fill_round_trips_target_id_and_a_missing_agent(conn) -> None:
    repo = GleepGlorpFillRepository(conn)
    fid, _ = await repo.insert(new_fill(agent_name=None, target_id="srv-1", target_key="k"))
    fill = await repo.get(fid)
    assert (fill.agent_name, fill.target_id) == (None, "srv-1")
    assert [f.target_id for f in await repo.list_for_session("s1")] == ["srv-1"]
    async with conn.execute("SELECT target_id FROM gleepglorp_fills WHERE id = ?", (fid,)) as cur:
        assert (await cur.fetchone())[0] == "srv-1"


async def test_a_fill_without_target_id_stores_null(conn) -> None:
    repo = GleepGlorpFillRepository(conn)
    fid, _ = await repo.insert(new_fill())
    assert (await repo.get(fid)).target_id is None


async def test_the_fill_view_carries_target_id_and_survives_a_missing_agent(conn) -> None:
    fill = Fill(
        id=1,
        session_id="s1",
        tool_call_id=None,
        kind="agent",
        action="change",
        agent_name=None,
        target_id="srv-1",
        target_key="k",
        changes={"description": "d"},
        base={"description": "old"},
        status="sent",
        outcome=None,
        claim_token=None,
        untrusted=False,
        untrusted_sources=[],
        created_at="t",
        claimed_at=None,
        resolved_at=None,
    )
    view = await fill_view(conn, fill)
    assert view["target_id"] == "srv-1"
    assert view["agent_name"] is None
    assert view["target_gone"] is False
    assert view["stale"] == []
    assert "claim_token" not in view


async def test_a_proposal_round_trips_target_id(conn) -> None:
    repo = GleepGlorpProposalRepository(conn)
    pid = await repo.insert(new_proposal(agent_name=None, target_id="srv-2", target_key="k"))
    p = await repo.get(pid)
    assert (p.agent_name, p.target_id) == (None, "srv-2")


# --- the frame helper ---------------------------------------------------------------------


async def test_the_frame_helper_builds_the_frame_and_never_raises(monkeypatch) -> None:
    import the_one.sessions._broadcast as broadcast
    from the_one.gleepglorp.status_rows import push_session_frame

    sent: list[tuple[str, dict]] = []

    async def fake(session_id, frame):
        sent.append((session_id, frame))

    monkeypatch.setattr(broadcast, "broadcast_to_session", fake)
    await push_session_frame("s9", "x_changed", "thing", {"id": 1}, "x_changed")
    assert sent == [("s9", {"type": "x_changed", "session_id": "s9", "thing": {"id": 1}})]

    async def boom(session_id, frame):
        raise RuntimeError("socket gone")

    monkeypatch.setattr(broadcast, "broadcast_to_session", boom)
    await push_session_frame("s9", "x_changed", "thing", {"id": 1}, "x_changed")


# --- ids in the reads ----------------------------------------------------------------------


@pytest.fixture
async def world(tmp_path):
    from tests._gleepglorp_seed import seed

    ns = await seed(tmp_path)
    yield ns
    await ns.conn.close()


async def _read(ns, kind, name=None):
    from the_one.gleepglorp import views

    return await views.read(ns.conn, ns.enc, kind, name)


async def test_mcp_server_and_provider_reads_carry_ids(world) -> None:
    from the_one.self_configuration.constants import SURFACE_ROW_NAME

    servers = await _read(world, "mcp_servers")
    by_name = {e["name"]: e for e in servers}
    assert by_name["Docs server"]["id"] == "m-http"
    assert by_name["Local tool"]["id"] == "m-stdio"
    # The synthetic self-configuration entry has no id.
    assert "id" not in by_name[SURFACE_ROW_NAME]
    detail = await _read(world, "mcp_servers", "Docs server")
    assert detail["id"] == "m-http"
    providers = {e["name"]: e for e in await _read(world, "providers")}
    assert providers["OpenAI main"]["id"] == "p-openai"
    assert (await _read(world, "providers", "OpenAI main"))["id"] == "p-openai"


async def test_other_kinds_get_no_id(world) -> None:
    for kind in ("agents", "knowledge_bases", "connectors", "secrets", "built_in_tools"):
        assert all("id" not in e for e in await _read(world, kind)), kind


async def test_a_read_by_id_reaches_the_second_of_two_same_named_servers(world) -> None:
    from the_one.db.models import MCPSource
    from the_one.db.repositories import MCPSourceRepository

    await MCPSourceRepository(world.conn, world.enc).create(
        MCPSource(
            id="m-twin",
            name="Docs server",
            type="stdio",
            config={"command": "twin-cmd", "args": []},
        )
    )
    # By name: the first (as before); by id: the one asked for.
    assert (await _read(world, "mcp_servers", "Docs server"))["id"] in {"m-http", "m-twin"}
    twin = await _read(world, "mcp_servers", "m-twin")
    assert (twin["id"], twin["type"], twin["command"]) == ("m-twin", "stdio", "twin-cmd")
    original = await _read(world, "mcp_servers", "m-http")
    assert original["id"] == "m-http" and original["type"] == "streamable-http"


async def test_an_unknown_name_or_id_is_still_a_plain_refusal(world) -> None:
    from the_one.gleepglorp.views import PlainMessage

    with pytest.raises(PlainMessage, match="No MCP server named"):
        await _read(world, "mcp_servers", "nope")


# --- Kind.resolve_target and target_key ----------------------------------------------------


async def test_the_agent_kind_resolves_an_existing_name_to_name_and_name(conn) -> None:
    await conn.execute("INSERT INTO agents (name) VALUES ('Trip Planner')")
    await conn.commit()
    resolve = kinds.get("agent").resolve_target
    assert await resolve(conn, "Trip Planner") == ("Trip Planner", "Trip Planner")
    with pytest.raises(ShapeError, match=r"No agent named Nope\."):
        await resolve(conn, "Nope")


def test_rule_and_routine_have_no_resolve_target() -> None:
    assert kinds.get("rule").resolve_target is None
    assert kinds.get("routine").resolve_target is None


def test_target_key_is_for_id_targeted_kinds() -> None:
    assert kinds.target_key("mcp_server", "change", "abc", "ignored") == "mcp_server:abc"
    assert kinds.target_key("mcp_server", "create", None, "Docs") == "mcp_server:new:Docs"


class _Stub:
    """A stub id-targeted kind's resolver: what Leg 4's real resolvers do over real tables."""

    def __init__(self, entries):
        self.entries = entries

    def resolve(self, ref):
        return kinds.resolve_by_id_or_name(self.entries, ref, "stub thing")


ENTRIES = [("id-1", "Docs"), ("id-2", "Docs"), ("id-3", "Mail"), ("Mail", "id-collision")]


def test_an_id_wins_over_a_name() -> None:
    # The ref "Mail" is both the id of the last entry and the name of id-3: the id wins.
    assert _Stub(ENTRIES).resolve("Mail") == ("Mail", "id-collision")
    assert _Stub(ENTRIES).resolve("id-2") == ("id-2", "Docs")


def test_a_unique_name_resolves() -> None:
    assert _Stub(ENTRIES[:3]).resolve("Mail") == ("id-3", "Mail")


def test_a_shared_name_is_refused_listing_each_match_as_name_and_id() -> None:
    with pytest.raises(ShapeError) as err:
        _Stub(ENTRIES).resolve("Docs")
    msg = str(err.value)
    assert "Docs (id-1)" in msg and "Docs (id-2)" in msg
    assert "id" in msg.lower()


def test_an_unknown_ref_and_a_blank_ref_are_refused() -> None:
    with pytest.raises(ShapeError, match=r"No stub thing named Ghost\."):
        _Stub(ENTRIES).resolve("Ghost")
    with pytest.raises(ShapeError, match="Say which stub thing"):
        _Stub(ENTRIES).resolve("  ")
