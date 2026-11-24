"""The ``secret`` kind (Mission 36 F5 L3a, DD6): metadata only (name, description, allowed
tools), never a value. Normalize and its tool rules, the create refusal, targets ignoring case,
the operator-only refusals, the warnings, approve through the secret write service (stale, gone,
failure items) and that no proposal or fill touches a row or a value before an Approve.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from tests._gleepglorp_seed import SEEDS, seed
from the_one.agent._context import TurnContext, current_tool_call_id, current_turn
from the_one.agent.service import AgentWriteDeps
from the_one.db import _write_lock
from the_one.db.repositories import (
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.gleepglorp import kinds
from the_one.gleepglorp.fill.store import GleepGlorpFillRepository, NewFill, fill_view
from the_one.gleepglorp.fill.tool import FillFormTool
from the_one.gleepglorp.kinds import errors as kind_errors
from the_one.gleepglorp.kinds import secret as secret_kind
from the_one.gleepglorp.proposals import apply as proposal_apply
from the_one.gleepglorp.proposals.shape import ShapeError
from the_one.gleepglorp.proposals.store import (
    GleepGlorpProposalRepository,
    NewProposal,
    proposal_view,
)
from the_one.gleepglorp.proposals.tool import ProposeChangeTool
from the_one.llm.base import Message, ToolCall
from the_one.secret_store import service as secret_service

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
VALUE = SEEDS["library_secret_value"]
CREATE_REFUSAL = (
    "Create a secret on the [Secrets](#library/secrets/~new) page; I can fill its name, "
    "description and allowed tools there."
)


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
    ns.secrets = ns.deps.secret_repo
    ns.sid = ns.library_secret_id  # "github": key gh_token, allowed ["shell"], held by "wide"
    ns.repo = GleepGlorpProposalRepository(conn)
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
        "secret",
        action,
        kinds.target_args("secret", None, None, None, target),
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


async def make(world, changes, target, *, session="s1") -> int:
    n = await norm(world, "change", changes, target)
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


def test_the_kind_is_registered_seventh_and_declared() -> None:
    k = secret_kind.KIND
    assert kinds.REGISTRY[6] is k and kinds.KINDS[6] == "secret"
    assert k.addressing == "id" and k.target_noun == "A secret"
    assert k.actions == ("change",) and k.fillable == ("create", "change")
    assert k.keyerror_is_gone is False
    assert k.operator_only == ("values", "keys", "secret_ids")
    assert [f.name for f in k.fields] == ["name", "description", "allowed_tools"]
    tools = k.fields[2]
    assert tools.type == "names" and tools.typed_items is True
    assert k.relaxed_guard_keys == frozenset({"allowed_tools"})
    assert "\n" not in k.summary and len(k.summary) < 100
    by = {f["name"]: f for f in kinds.describe("secret")["fields"]}
    assert by["allowed_tools"]["provenance"] == "each tool you add must be named by you"
    assert "provenance" not in by["name"]


def test_no_value_field_exists_in_any_spec() -> None:
    names = {f.name for f in secret_kind.KIND.fields} | {f.stored for f in secret_kind.KIND.fields}
    for forbidden in ("values", "keys", "secret_ids", "value"):
        assert forbidden not in names


# --- the create refusal (DD6) ---------------------------------------------------------------


async def test_a_proposal_create_is_refused_with_the_page_handoff(world) -> None:
    assert await refused(world, "create", {"name": "x"}) == CREATE_REFUSAL
    # the create gate runs before the unknown-key check, so values get the same sentence
    assert await refused(world, "create", {"name": "x", "values": [1]}) == CREATE_REFUSAL
    tool = ProposeChangeTool(agent_name="GleepGlorp")
    tool.bind_agent(SimpleNamespace(messages=[]))
    token = current_turn.set(TurnContext(session_id="s1"))
    try:
        out = await tool.execute(kind="secret", action="create", changes={"name": "x"})
    finally:
        current_turn.reset(token)
    assert out == CREATE_REFUSAL
    assert await world.repo.list_for_session("s1") == []


async def test_a_fill_create_records_name_description_and_tools_only(world) -> None:
    n = await norm(
        world,
        "create",
        {"name": " Slack ", "description": "bot", "allowed_tools": ["fetch_url"]},
        mode="fill",
    )
    assert (n.action, n.target_id, n.base) == ("create", None, None)
    assert n.changes == {"name": "Slack", "description": "bot", "allowed_tools": ["fetch_url"]}
    assert n.target_key == "secret:new:Slack"
    n = await norm(world, "create", {"name": "Only a name"}, mode="fill")
    assert n.changes == {"name": "Only a name"}


async def test_a_fill_create_still_refuses_values_and_a_taken_name(world) -> None:
    msg = await refused(world, "create", {"name": "x", "values": [1]}, mode="fill")
    assert msg == secret_kind.VALUES_MESSAGE
    msg = await refused(world, "create", {"name": "GITHUB"}, mode="fill")
    assert msg == "A secret with this name already exists."


# --- normalize a change -------------------------------------------------------------------


async def test_a_change_reads_the_base_with_the_list_itself(world) -> None:
    n = await norm(world, "change", {"allowed_tools": ["shell", "fetch_url"]}, world.sid)
    assert n.target_id == world.sid and n.target_key == f"secret:{world.sid}"
    assert n.changes == {"allowed_tools": ["shell", "fetch_url"]}
    assert n.base == {"allowed_tools": ["shell"]}
    n = await norm(world, "change", {"description": "d2", "name": "Github 2"}, world.sid)
    assert n.base == {"description": "GitHub access", "name": "github"}


async def test_targets_match_a_name_ignoring_case_and_an_id_exactly(world) -> None:
    for ref in ("github", "GitHub", "GITHUB", world.sid):
        assert (await norm(world, "change", {"description": "x"}, ref)).target_id == world.sid
    assert "No secret named" in await refused(world, "change", {"description": "x"}, "gh")
    assert "Say which secret" in await refused(world, "change", {"description": "x"}, " ")
    assert "No secret named" in await refused(
        world, "change", {"description": "x"}, world.sid.upper()
    )


@pytest.mark.parametrize("tool", ["send_to_platform_channel", "continue", "search_tools"])
async def test_a_refused_tool_is_refused_with_the_routes_sentence(world, tool) -> None:
    msg = await refused(world, "change", {"allowed_tools": [tool]}, world.sid)
    assert msg == f"{tool} stores or publishes what it receives, so it can't receive secrets."
    assert await refused(world, "create", {"name": "x", "allowed_tools": [tool]}, mode="fill")


async def test_an_empty_list_whitespace_and_overlong_names_are_refused(world) -> None:
    assert "at least one tool" in await refused(world, "change", {"allowed_tools": []}, world.sid)
    assert "whitespace" in await refused(world, "change", {"allowed_tools": ["a b"]}, world.sid)
    assert "1 to 128" in await refused(world, "change", {"allowed_tools": ["a" * 129]}, world.sid)
    assert "must be text" in await refused(world, "change", {"allowed_tools": [3]}, world.sid)
    assert await refused(world, "change", {"allowed_tools": "shell"}, world.sid)


async def test_allowed_tools_are_trimmed_and_de_duplicated(world) -> None:
    n = await norm(world, "change", {"allowed_tools": [" shell ", "shell", "fetch_url"]}, world.sid)
    assert n.changes["allowed_tools"] == ["shell", "fetch_url"]


async def test_a_rename_to_another_secrets_name_is_refused_but_a_case_change_is_not(world) -> None:
    other = await world.secrets.create("Other", "", ["t"], [{"key": "o_key", "value": "v"}])
    assert "already exists" in await refused(world, "change", {"name": "OTHER"}, world.sid)
    n = await norm(world, "change", {"name": "GITHUB"}, world.sid)
    assert n.changes == {"name": "GITHUB"}
    assert other.id


@pytest.mark.parametrize("key", ["values", "keys", "secret_ids"])
@pytest.mark.parametrize("mode", ["propose", "fill"])
async def test_operator_only_fields_are_refused_with_the_values_sentence(world, key, mode) -> None:
    msg = await refused(world, "change", {key: ["x"]}, world.sid, mode=mode)
    assert msg == secret_kind.VALUES_MESSAGE
    msg = await refused(world, "change", {"description": "d", key: {"k": "v"}}, world.sid)
    assert msg == secret_kind.VALUES_MESSAGE


def test_the_values_sentence_says_never_to_repeat_the_value() -> None:
    assert "never take, fill or repeat" in secret_kind.VALUES_MESSAGE
    for field in ("name", "description", "allowed tools"):
        assert field in secret_kind.VALUES_MESSAGE
    assert set(secret_kind.VALUE_SYNONYMS) == {"value", "key", "secret", "secret_value"}
    assert not set(secret_kind.VALUE_SYNONYMS) & {f.name for f in secret_kind.SECRET_FIELDS}


@pytest.mark.parametrize("key", ["value", "key", "secret", "secret_value"])
@pytest.mark.parametrize("mode", ["propose", "fill"])
async def test_singular_value_names_get_the_values_sentence_and_never_echo(
    world, key, mode
) -> None:
    canary = "maple-harbor-k3m8w"
    msg = await refused(world, "change", {key: canary}, world.sid, mode=mode)
    assert msg == secret_kind.VALUES_MESSAGE
    assert canary not in msg
    msg = await refused(world, "create", {"name": "x", key: canary}, mode="fill")
    assert msg == secret_kind.VALUES_MESSAGE
    assert canary not in msg


async def test_an_unknown_field_names_the_allowed_ones(world) -> None:
    msg = await refused(world, "change", {"color": "red"}, world.sid)
    assert "Allowed fields: name, description, allowed_tools" in msg


# --- no row and no value before an approve --------------------------------------------------


def _typed_chat(tool_name: str) -> SimpleNamespace:
    """A chat with no outside content: the operator names the tools, then the call ``c1``."""
    return SimpleNamespace(
        messages=[
            Message.user("let it use fetch_url and shell"),
            Message.assistant("", tool_calls=[ToolCall(id="c1", name=tool_name, arguments={})]),
        ]
    )


async def _secret_rows(conn):
    async with conn.execute(
        "SELECT id, name, description, allowed_tools, updated_at FROM secrets ORDER BY id"
    ) as cur:
        rows = await cur.fetchall()
    async with conn.execute(
        "SELECT id, secret_id, key, value, position FROM secret_values ORDER BY id"
    ) as cur:
        return rows, await cur.fetchall()


async def test_a_proposal_and_a_fill_write_no_secret_row_and_return_no_value(world) -> None:
    before = await _secret_rows(world.conn)
    tool = ProposeChangeTool(agent_name="GleepGlorp")
    tool.bind_agent(_typed_chat("propose_change"))
    token = current_turn.set(TurnContext(session_id="s1"))
    ctoken = current_tool_call_id.set("c1")
    try:
        out = await tool.execute(
            kind="secret",
            action="change",
            target=world.sid,
            changes={"allowed_tools": ["shell", "fetch_url"], "description": "Proposed"},
        )
    finally:
        current_tool_call_id.reset(ctoken)
        current_turn.reset(token)
    assert out.startswith("Proposal "), out
    fill_tool = FillFormTool(agent_name="GleepGlorp")
    fill_tool.bind_agent(_typed_chat("fill_form"))
    page = {"line": "Library", "descriptor": {"destination": "library"}}
    token = current_turn.set(TurnContext(session_id="s2", page=page))
    ctoken = current_tool_call_id.set("c1")
    replies = []
    try:
        replies.append(
            await fill_tool.execute(
                kind="secret", action="change", target=world.sid, changes={"name": "Filled"}
            )
        )
        replies.append(
            await fill_tool.execute(
                kind="secret",
                action="create",
                changes={"name": "Fresh", "allowed_tools": ["fetch_url"]},
            )
        )
    finally:
        current_tool_call_id.reset(ctoken)
        current_turn.reset(token)
    assert all(r.startswith("Fill ") for r in replies), replies
    assert await _secret_rows(world.conn) == before
    fills = await GleepGlorpFillRepository(world.conn).list_for_session("s2")
    assert {f.kind for f in fills} == {"secret"}
    blob = repr([out, replies, fills, await world.repo.list_for_session("s1")])
    assert VALUE not in blob and VALUE[-4:] not in blob


# --- the card, the summary and the warnings ------------------------------------------------


async def test_the_card_names_the_secret_by_a_lookup_and_knows_when_it_is_gone(world) -> None:
    pid = await make(world, {"description": "x"}, world.sid)
    view = await view_of(world, pid)
    assert view["title"] == "Change secret “github”" and view["target_gone"] is False
    assert VALUE not in repr(view)
    await world.secrets.delete(world.sid)
    assert (await view_of(world, pid))["target_gone"] is True


async def test_adding_tools_warns_with_the_key_names_never_the_value(world) -> None:
    pid = await make(world, {"allowed_tools": ["shell", "fetch_url", "mcp__a__b"]}, world.sid)
    view = await view_of(world, pid)
    assert view["warnings"] == ["gh_token can then be sent to fetch_url, mcp__a__b."]
    assert VALUE not in repr(view)


async def test_removing_or_reordering_tools_carries_no_warning(world) -> None:
    await world.secrets.update(world.sid, allowed_tools=["shell", "fetch_url"])
    pid = await make(world, {"allowed_tools": ["fetch_url", "shell"]}, world.sid)
    assert (await view_of(world, pid))["warnings"] == []
    pid = await make(world, {"allowed_tools": ["shell"]}, world.sid, session="s2")
    assert (await view_of(world, pid))["warnings"] == []


async def test_a_rename_warns_that_agents_keep_the_secret(world) -> None:
    pid = await make(world, {"name": "Github 2"}, world.sid)
    assert (await view_of(world, pid))["warnings"] == [secret_kind.WARN_RENAME]
    assert "keys, not its name" in secret_kind.WARN_RENAME
    pid = await make(world, {"name": "github", "description": "d"}, world.sid, session="s2")
    assert (await view_of(world, pid))["warnings"] == []  # the name is not changed


# --- approve ------------------------------------------------------------------------------


async def test_approve_replaces_the_tools_whole_and_never_touches_the_values(world, frames) -> None:
    rows_before = (await _secret_rows(world.conn))[1]
    pid = await make(world, {"allowed_tools": ["fetch_url"], "description": "New"}, world.sid)
    res = await run(world, pid)
    assert res.outcome == "applied"
    s = await world.secrets.get(world.sid)
    assert s.allowed_tools == ["fetch_url"] and s.description == "New" and s.name == "github"
    assert (await _secret_rows(world.conn))[1] == rows_before  # ciphertext rows byte-identical
    assert await world.secrets.get_values(world.sid) == [("gh_token", VALUE)]
    assert res.view["result"]["summary"] == "Changed Description, Allowed tools on secret github"
    assert VALUE not in repr(res.view)
    assert (await world.repo.get(pid)).status == "applied"
    assert frames.config[0]["target_id"] == world.sid


async def test_approve_a_case_only_rename(world, frames) -> None:
    pid = await make(world, {"name": "GITHUB"}, world.sid)
    assert (await run(world, pid)).outcome == "applied"
    assert (await world.secrets.get(world.sid)).name == "GITHUB"


async def test_a_stale_change_gives_the_rows_and_override_applies(world, frames) -> None:
    pid = await make(world, {"allowed_tools": ["fetch_url"], "description": "Mine"}, world.sid)
    await world.secrets.update(world.sid, allowed_tools=["shell", "other_tool"])
    res = await run(world, pid)
    assert res.outcome == "stale"
    assert res.stale == [
        {
            "field": "allowed_tools",
            "label": "Allowed tools",
            "current": ["shell", "other_tool"],
            "proposed": ["fetch_url"],
        }
    ]
    assert (await world.repo.get(pid)).status == "pending"
    assert (await world.secrets.get(world.sid)).allowed_tools == ["shell", "other_tool"]
    assert (await run(world, pid, override=True)).outcome == "applied"
    assert (await world.secrets.get(world.sid)).allowed_tools == ["fetch_url"]


async def test_a_deleted_target_withdraws_the_proposal_as_gone(world, frames) -> None:
    pid = await make(world, {"description": "x"}, world.sid)
    await world.secrets.delete(world.sid)
    res = await run(world, pid)
    assert res.outcome == "gone" and (await world.repo.get(pid)).status == "withdrawn"
    assert frames.config == []


async def test_a_service_refusal_carries_items_and_writes_nothing(world, frames) -> None:
    pid = await make(world, {"description": "x"}, world.sid)
    await world.conn.execute(
        "UPDATE gleepglorp_proposals SET changes = ? WHERE id = ?",
        ('{"allowed_tools": ["continue"]}', pid),
    )
    await world.conn.commit()
    res = await run(world, pid, override=True)
    assert res.outcome == "failed"
    [err] = res.view["result"]["errors"]
    assert err["loc"] == ["allowed_tools", 0] and "can't receive secrets" in err["msg"]
    assert (await world.secrets.get(world.sid)).allowed_tools == ["shell"]


async def test_a_name_taken_after_the_proposal_is_items_on_the_name(world, frames) -> None:
    pid = await make(world, {"name": "Renamed"}, world.sid)
    await world.secrets.create("Renamed", "", ["t"], [{"key": "r_key", "value": "v"}])
    res = await run(world, pid, override=True)
    assert res.outcome == "failed"
    assert res.view["result"]["errors"] == [
        {"loc": ["name"], "msg": "A secret with this name already exists."}
    ]
    assert (await world.secrets.get(world.sid)).name == "github"


async def test_a_bare_key_error_from_the_service_is_not_hidden_as_gone(
    world, frames, monkeypatch
) -> None:
    async def boom(*a, **kw):
        raise KeyError("bug")

    monkeypatch.setattr(secret_service, "change_secret_metadata", boom)
    pid = await make(world, {"description": "x"}, world.sid)
    with pytest.raises(KeyError):
        await run(world, pid)
    assert (await world.repo.get(pid)).status == "pending"


# --- error translation (AC6b) -----------------------------------------------------------------


async def test_translate_maps_the_new_services_errors(world) -> None:
    from the_one.knowledge.service import KbNotFound, KbStaleError, KbWriteError

    pid = await make(world, {"description": "x"}, world.sid)
    p = await world.repo.get(pid)

    async def tr(exc):
        return await kind_errors.translate(exc, p, conn=world.conn, zone=_utc)

    err = await tr(secret_service.SecretNotFound("x"))
    assert err.gone is True
    err = await tr(secret_service.SecretWriteError(404, "Secret not found."))
    assert err.gone is True
    err = await tr(KbNotFound("x"))
    assert err.gone is True
    err = await tr(KbWriteError(404, "x"))
    assert err.gone is True
    err = await tr(secret_service.SecretWriteError(422, [{"loc": ["a", 0], "msg": "m"}]))
    assert err.items == [{"loc": ["a", 0], "msg": "m"}] and not err.gone
    err = await tr(secret_service.name_conflict())
    assert err.items == [{"loc": ["name"], "msg": "A secret with this name already exists."}]
    err = await tr(KbWriteError(422, [{"loc": ["name"], "msg": "bad"}]))
    assert err.items == [{"loc": ["name"], "msg": "bad"}]
    stale = [{"field": "description", "current": "a", "proposed": "b"}]
    err = await tr(secret_service.SecretStaleError(stale))
    assert err.stale == [
        {"field": "description", "label": "Description", "current": "a", "proposed": "b"}
    ]
    err = await tr(KbStaleError(stale))
    assert err.stale[0]["field"] == "description"
    boom = RuntimeError("unmapped")
    assert await tr(boom) is boom
    key_error = KeyError("bug")
    assert await tr(key_error) is key_error  # keyerror_is_gone is False for these kinds


# --- the fill view ------------------------------------------------------------------------


async def test_the_fill_view_has_a_title_and_stale_rows_of_the_metadata(world) -> None:
    fills = GleepGlorpFillRepository(world.conn)
    n = await norm(world, "change", {"description": "Mine"}, world.sid, mode="fill")
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
    assert view["stale"] == [] and view["title"] == "Change secret “github”"
    await world.secrets.update(world.sid, description="Moved")
    view = await fill_view(world.conn, await fills.get(fill_id))
    assert view["stale"] == [
        {"field": "description", "label": "Description", "current": "Moved", "proposed": "Mine"}
    ]
    assert VALUE not in repr(view)
