"""The ``mcp_server`` kind (M36 F4 L4a, DD9): normalize, resolve, base, card, warnings, approve
through the MCP write service, and the guard cases (DD7 per kind) through the real
``propose_change`` on an untrusted turn."""

# ruff: noqa: E501, N802
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from tests._gleepglorp_seed import ARG_TOKEN, SEEDS, seed
from the_one.agent._context import TurnContext, current_tool_call_id, current_turn
from the_one.agent.service import AgentWriteDeps
from the_one.db import _write_lock
from the_one.db.models import MCPSource
from the_one.db.repositories import (
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.gleepglorp import kinds
from the_one.gleepglorp.kinds import mcp_server
from the_one.gleepglorp.proposals import apply as proposal_apply
from the_one.gleepglorp.proposals import guard
from the_one.gleepglorp.proposals.shape import ShapeError
from the_one.gleepglorp.proposals.store import (
    GleepGlorpProposalRepository,
    NewProposal,
    proposal_view,
)
from the_one.gleepglorp.proposals.tool import ProposeChangeTool
from the_one.llm.base import Message, ToolCall, ToolResult

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
H = "m-http"  # "Docs server": a Sensitive Authorization, OAuth tokens, plain X-Plain header
S = "m-stdio"  # "Local tool": a Sensitive DB_PASSWORD, plain PLAIN_ENV, runtime npx


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


async def norm(world, action, changes, target=None):
    return await kinds.normalize(
        "mcp_server",
        action,
        kinds.target_args("mcp_server", None, None, None, target),
        changes,
        conn=world.conn,
        now=NOW,
        zone=UTC,
        enc=world.enc,
    )


async def refused(world, action, changes, target=None) -> str:
    with pytest.raises(ShapeError) as e:
        await norm(world, action, changes, target)
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


def stdio_create(**kw) -> dict:
    return {
        "name": "Fetcher",
        "type": "stdio",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        **kw,
    }


def http_create(**kw) -> dict:
    return {"name": "Remote", "type": "streamable-http", "url": "https://mcp.acme.test/mcp", **kw}


# --- registered and described -----------------------------------------------------------


def test_the_kind_is_registered_last_and_fillable() -> None:
    # registered after the three agent kinds; the provider kind (Leg 5a) follows it
    assert kinds.REGISTRY[3] is mcp_server.KIND
    assert kinds.KINDS[3] == "mcp_server"
    assert "mcp_server" in kinds.FILLABLE and mcp_server.KIND.fillable == ("create", "change")
    assert mcp_server.KIND.operator_only == ("cwd", "sandbox", "secrets")
    assert mcp_server.KIND.relaxed_guard_keys == frozenset({"url", "command", "args"})
    # the unused hook was removed in Leg 5a: the provider kind reads ``mode`` instead
    assert not hasattr(mcp_server.KIND, "needs_secret")


def test_describe_shows_rows_and_address_markers_only_for_the_fields_that_have_them() -> None:
    by = {f["name"]: f for f in kinds.describe("mcp_server")["fields"]}
    assert by["env"]["shape"] == by["headers"]["shape"] == "an object of name → value"
    assert by["type"]["create_only"] is True and by["type"]["required_on_create"] is True
    for name in ("command", "args", "url", "env", "headers"):
        assert by[name]["provenance"] == "must come from you or a page you linked"
    assert "provenance" not in by["name"] and "shape" not in by["url"]
    for kind in ("agent", "rule", "routine"):  # their output is unchanged
        for f in kinds.describe(kind)["fields"]:
            assert "shape" not in f and "provenance" not in f, (kind, f["name"])


# --- normalize: every refusal -------------------------------------------------------------


@pytest.mark.parametrize("key", ["cwd", "sandbox", "secrets"])
async def test_operator_only_keys_are_refused_by_the_kind_and_the_dispatcher(world, key) -> None:
    with pytest.raises(ShapeError, match="operator"):
        await mcp_server.normalize(
            "change", {"target": H}, {key: "x"}, conn=world.conn, now=NOW, zone=UTC, enc=world.enc
        )
    with pytest.raises(ShapeError):
        await norm(world, "change", {key: "x"}, H)


async def test_an_unknown_key_is_refused(world) -> None:
    with pytest.raises(ShapeError, match="Allowed fields"):
        await mcp_server.normalize(
            "change", {"target": H}, {"colour": "x"}, conn=world.conn, now=NOW, zone=UTC
        )


async def test_the_type_of_an_existing_server_is_never_changed_from_here(world) -> None:
    msg = await refused(world, "change", {"type": "stdio", "url": "https://a.test/"}, H)
    assert "editor" in msg and "type" in msg
    with pytest.raises(ShapeError, match="editor"):  # the kind's own check
        await mcp_server.normalize(
            "change", {"target": H}, {"type": "stdio"}, conn=world.conn, now=NOW, zone=UTC
        )


async def test_the_other_transports_fields_are_refused_on_create_and_change(world) -> None:
    assert "url" in await refused(world, "create", stdio_create(url="https://a.test/"))
    assert "command" in await refused(world, "create", http_create(command="echo"))
    assert "env" in await refused(world, "create", http_create(env={"A": "b"}))
    assert "headers" in await refused(world, "create", stdio_create(headers={"A": "b"}))
    assert "command" in await refused(world, "change", {"command": "echo"}, H)  # by stored type
    assert "url" in await refused(world, "change", {"url": "https://a.test/"}, S)


async def test_a_create_needs_its_transports_address_and_a_valid_type(world) -> None:
    assert "needs command" in await refused(world, "create", {"name": "X", "type": "stdio"})
    assert "needs url" in await refused(world, "create", {"name": "X", "type": "streamable-http"})
    assert "type must be" in await refused(
        world, "create", {"name": "X", "type": "ftp", "url": "u"}
    )
    assert "needs name, type" in await refused(world, "create", {"url": "https://a.test/"})


@pytest.mark.parametrize(
    "url", ["ftp://a.test/x", "javascript:alert(1)", "not a url", "https://", "file:///etc/passwd"]
)
async def test_a_non_http_url_is_refused(world, url) -> None:
    assert "http or https" in await refused(world, "create", http_create(url=url))


async def test_args_must_be_text_items(world) -> None:
    assert "args" in await refused(world, "create", stdio_create(args=["-y", 3]))
    assert "args" in await refused(world, "create", stdio_create(args="-y pkg"))
    n = await norm(world, "create", stdio_create(args=["-y", "-y", "pkg"]))
    assert n.changes["args"] == ["-y", "-y", "pkg"]  # kept verbatim: no dedupe, no strip


async def test_a_surface_row_is_never_a_target_nor_a_name(world) -> None:
    assert "No MCP server" in await refused(
        world, "change", {"url": "http://127.0.0.1:1/"}, "m-surface"
    )
    assert "No MCP server" in await refused(
        world, "change", {"url": "http://127.0.0.1:1/"}, "self-configuration"
    )
    assert "reserved" in await refused(world, "create", http_create(name="self-configuration"))
    assert "reserved" in await refused(world, "change", {"name": "self-configuration"}, H)


async def test_names_are_checked_and_unique(world) -> None:
    assert "already exists" in await refused(world, "create", http_create(name="docs SERVER"))
    assert "already exists" in await refused(world, "change", {"name": "Local tool"}, H)
    n = await norm(world, "change", {"name": "Docs server"}, H)  # its own name is not a clash
    assert n.changes == {"name": "Docs server"}
    assert await refused(world, "create", http_create(name="  "))


@pytest.mark.parametrize(
    ("changes", "target", "fragment"),
    [
        ({"headers": {"X-Custom-Token": "abc"}}, H, "looks like a secret"),
        ({"headers": {"Authorization": "Bearer abc"}}, H, "stored as a Sensitive value"),
        ({"headers": {"authorization": "Bearer abc"}}, H, "stored as a Sensitive value"),
        ({"headers": {"bearer_token": "abc"}}, H, "stored as a Sensitive value"),
        ({"headers": {"access_token": "abc"}}, H, "managed by sign-in"),
        ({"headers": {"Access_Token": "abc"}}, H, "managed by sign-in"),
        ({"headers": {"Accept": ""}}, H, "empty row"),
        ({"headers": {"Authorization": ""}}, H, "stored as a Sensitive value"),  # no empty row
        ({"headers": {"bad name": "x"}}, H, "valid header name"),
        ({"headers": {}}, H, "headers"),
        ({"headers": {"A": 1}}, H, "must be text"),
        ({"env": {"DB_PASSWORD": "x1"}}, S, "stored as a Sensitive value"),  # exact
        ({"env": {"GITHUB_TOKEN": "x1"}}, S, "looks like a secret"),
        ({"env": {"PLAIN": ""}}, S, "empty row"),
        ({"env": {"A=B": "x"}}, S, "valid env name"),
        ({"args": ["--token=abc123"]}, S, "looks like a secret"),
        ({"args": ["--api-key", "abc123"]}, S, "looks like a secret"),
    ],
)
async def test_rows_that_could_hold_a_secret_are_refused(world, changes, target, fragment) -> None:
    assert fragment in await refused(world, "change", changes, target)


async def test_an_env_row_differing_only_in_case_from_a_sensitive_key_is_allowed(world) -> None:
    n = await norm(world, "change", {"env": {"Db_Setting": "x"}}, S)
    assert n.changes == {"env": {"Db_Setting": "x"}}


async def test_a_create_refuses_a_secret_looking_row_and_an_oauth_name_too(world) -> None:
    assert "looks like a secret" in await refused(
        world, "create", http_create(headers={"X-Api-Key": "k1"})
    )
    assert "managed by sign-in" in await refused(
        world, "create", http_create(headers={"access_token": "x"})
    )
    assert "looks like a secret" in await refused(
        world, "create", stdio_create(args=["--password=x"])
    )
    n = await norm(world, "create", http_create(headers={"Accept": "application/json"}))
    assert n.changes["headers"] == {"Accept": "application/json"}


async def test_a_header_differing_only_in_case_from_a_non_secret_looking_sensitive_key(
    world,
) -> None:
    await world.deps.mcp_repo.update_in_txn(
        H,
        lambda cur: cur.model_copy(
            update={"secrets": {**cur.secrets, "X-Tenant": "t-secret-1234"}}
        ),
    )
    for name in ("X-Tenant", "x-tenant", "X-TENANT"):
        assert "stored as a Sensitive value" in await refused(
            world, "change", {"headers": {name: "acme"}}, H
        )


# --- resolution ---------------------------------------------------------------------------


async def test_a_server_resolves_by_id_first_then_by_name(world) -> None:
    n = await norm(world, "change", {"url": "https://a.test/"}, H)
    assert n.target_id == H and n.target_key == f"mcp_server:{H}" and n.agent_name is None
    n = await norm(world, "change", {"url": "https://a.test/"}, "Docs server")
    assert n.target_id == H
    assert "No MCP server named" in await refused(
        world, "change", {"url": "https://a.test/"}, "Nope"
    )
    assert "give its name or id" in await refused(world, "change", {"url": "https://a.test/"}, None)


async def test_two_servers_with_one_name_are_refused_by_name_and_work_by_id(world) -> None:
    await world.deps.mcp_repo.create(
        MCPSource(
            id="m-twin",
            name="Docs server",
            type="streamable-http",
            config={"url": "https://t.test/"},
        )
    )
    msg = await refused(world, "change", {"url": "https://a.test/"}, "Docs server")
    assert "More than one" in msg and H in msg and "m-twin" in msg
    n = await norm(world, "change", {"url": "https://a.test/"}, "m-twin")
    assert n.target_id == "m-twin"


async def test_a_create_keys_on_its_name(world) -> None:
    n = await norm(world, "create", http_create())
    assert (n.kind, n.action, n.agent_name, n.target_id) == ("mcp_server", "create", None, None)
    assert n.target_key == "mcp_server:new:Remote" and n.base is None


# --- base ---------------------------------------------------------------------------------


async def test_base_holds_only_the_named_stored_values_and_only_existing_rows(world) -> None:
    src = await world.deps.mcp_repo.get(H)
    n = await norm(
        world,
        "change",
        {"url": "https://a.test/", "headers": {"x-plain": "v", "X-New": "1"}, "name": "Docs 2"},
        H,
    )
    assert n.base == {
        "url": src.config["url"],
        "name": "Docs server",
        "headers": {"x-plain": src.config["headers"]["X-Plain"]},  # X-New is absent: omitted
    }
    n = await norm(world, "change", {"headers": {"X-New": "1"}}, H)
    assert n.base == {"headers": {}}  # never None, and no row invented
    n = await norm(world, "change", {"args": ["-y", "p"], "env": {"PLAIN_ENV": "z"}}, S)
    src = await world.deps.mcp_repo.get(S)
    assert n.base == {
        "args": src.config["args"],
        "env": {"PLAIN_ENV": src.config["env"]["PLAIN_ENV"]},
    }


# --- the card -----------------------------------------------------------------------------


async def test_the_card_names_the_server_by_a_lookup_and_knows_when_it_is_gone(world) -> None:
    pid = await make(world, "create", http_create())
    view = await proposal_view(world.conn, await world.repo.get(pid))
    assert view["title"] == "Create MCP server “Remote”" and view["target_gone"] is False
    assert view["agent_name"] is None and view["warnings"] == []

    pid = await make(world, "change", {"url": "https://a.test/"}, H, session="s2")
    view = await proposal_view(world.conn, await world.repo.get(pid))
    assert view["title"] == "Change MCP server “Docs server”" and view["target_gone"] is False
    assert view["target_id"] == H and view["agent_name"] is None
    # No routine extras leak into this kind's card
    assert "schedule_text" not in view and "next_runs" not in view

    await world.deps.mcp_repo.delete(H)
    view = await proposal_view(world.conn, await world.repo.get(pid))
    assert view["target_gone"] is True and view["title"].startswith("Change MCP server")


async def test_the_other_kinds_cards_are_unchanged_and_carry_no_warnings(world) -> None:
    n = await kinds.normalize(
        "agent", "change", {"agent": "wide"}, {"description": "d"},
        conn=world.conn, now=NOW, zone=UTC, enc=world.enc,
    )  # fmt: skip
    pid = await world.repo.insert(
        NewProposal(
            session_id="s9", kind="agent", action="change", agent_name=n.agent_name,
            target_key=n.target_key, changes=n.changes, base=n.base,
        )
    )  # fmt: skip
    view = await proposal_view(world.conn, await world.repo.get(pid))
    assert view["warnings"] == [] and view["title"] == "Change agent “wide”"


# --- warnings -----------------------------------------------------------------------------


async def view_of(world, pid):
    return await proposal_view(world.conn, await world.repo.get(pid))


async def test_a_url_change_warns_when_sensitive_headers_or_tokens_are_stored(world) -> None:
    pid = await make(world, "change", {"url": "https://elsewhere.test/mcp"}, H)
    assert (await view_of(world, pid))["warnings"] == [mcp_server.WARN_URL]
    # the same URL: no change, no warning
    src = await world.deps.mcp_repo.get(H)
    pid2 = await make(world, "change", {"url": src.config["url"]}, H, session="s2")
    assert (await view_of(world, pid2))["warnings"] == []


async def test_a_command_or_args_change_warns_when_sensitive_env_is_stored(world) -> None:
    pid = await make(world, "change", {"command": "uvx"}, S)
    assert (await view_of(world, pid))["warnings"] == [mcp_server.WARN_COMMAND]
    pid = await make(world, "change", {"args": ["-y", "other"]}, S, session="s2")
    assert (await view_of(world, pid))["warnings"] == [mcp_server.WARN_COMMAND]


async def test_a_new_npx_or_pipx_server_notes_the_first_run_download(world) -> None:
    for command in ("npx", "pipx", "uvx"):
        pid = await make(world, "create", stdio_create(command=command), session=command)
        assert (await view_of(world, pid))["warnings"] == [mcp_server.WARN_DOWNLOAD], command
    pid = await make(world, "create", stdio_create(command="python"), session="py")
    assert (await view_of(world, pid))["warnings"] == []
    pid = await make(world, "create", http_create(), session="http")
    assert (await view_of(world, pid))["warnings"] == []


async def test_a_plain_change_has_no_warning(world) -> None:
    pid = await make(world, "change", {"headers": {"Accept": "a/b"}}, H)
    assert (await view_of(world, pid))["warnings"] == []
    pid = await make(world, "change", {"env": {"PLAIN_ENV": "z"}}, S, session="s2")
    assert (await view_of(world, pid))["warnings"] == []
    pid = await make(world, "change", {"name": "Renamed"}, H, session="s3")
    assert (await view_of(world, pid))["warnings"] == []


async def test_a_closed_card_carries_no_warnings(world, frames) -> None:
    pid = await make(world, "change", {"url": "https://elsewhere.test/mcp"}, H)
    assert (await view_of(world, pid))["warnings"]
    assert (await run(world, pid)).outcome == "applied"
    assert (await view_of(world, pid))["warnings"] == []  # applied: never describes the new state
    pid = await make(world, "create", stdio_create(), session="s2")
    await world.repo.mark(pid, "dismissed", from_statuses=("pending",))
    assert (await view_of(world, pid))["warnings"] == []


# --- approve ------------------------------------------------------------------------------


async def test_a_create_applies_through_the_service_with_the_pregenerated_id(world, frames) -> None:
    pid = await make(world, "create", stdio_create(env={"LOG_LEVEL": "debug"}))
    res = await run(world, pid)
    assert res.outcome == "applied"
    row = await world.repo.get(pid)
    new_id = row.result["target_id"]
    assert len(new_id) == 12 and row.result["summary"] == "Created MCP server Fetcher"
    stored = await world.deps.mcp_repo.get(new_id)
    assert (stored.name, stored.type) == ("Fetcher", "stdio")
    assert stored.config == {
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "env": {"LOG_LEVEL": "debug"},
    }
    assert stored.secrets == {}
    [frame] = frames.config
    assert frame["kind"] == "mcp_server" and frame["agent"] is None
    assert frame["target_id"] == new_id and frame["fields"] == [
        "name",
        "type",
        "command",
        "args",
        "env",
    ]
    # the card and a reload agree on the id after a create is applied
    assert res.view["target_id"] == new_id == (await view_of(world, pid))["target_id"]
    assert res.view["title"] == "Create MCP server “Fetcher”"


async def test_a_change_applies_only_its_fields_and_keeps_secrets_cache_and_tokens(
    world, frames
) -> None:
    before = await world.deps.mcp_repo.get(H)
    pid = await make(world, "change", {"headers": {"X-Plain": "new", "X-Added": "1"}}, H)
    res = await run(world, pid)
    assert res.outcome == "applied"
    after = await world.deps.mcp_repo.get(H)
    assert after.config["headers"]["X-Plain"] == "new" and after.config["headers"]["X-Added"] == "1"
    assert after.config["headers"]["X-Api-Key"] == before.config["headers"]["X-Api-Key"]
    assert after.config["url"] == before.config["url"]
    assert after.config["_cache"] == before.config["_cache"]  # the URL did not change
    assert after.secrets == before.secrets  # a proposal never touches secrets
    [frame] = frames.config
    assert frame["kind"] == "mcp_server" and frame["agent"] is None and frame["target_id"] == H
    assert (await world.repo.get(pid)).result[
        "summary"
    ] == "Changed Headers on MCP server Docs server"


async def test_a_stale_change_gives_the_rows_and_override_applies(world, frames) -> None:
    pid = await make(
        world, "change", {"url": "https://new.test/mcp", "headers": {"X-New": "mine"}}, H
    )
    await world.deps.mcp_repo.update_in_txn(
        H,
        lambda cur: cur.model_copy(
            update={
                "config": {
                    **cur.config,
                    "url": "https://hand-edited.test/mcp",
                    "headers": {**cur.config["headers"], "X-New": "theirs"},
                }
            }
        ),
    )
    res = await run(world, pid)
    assert res.outcome == "stale"
    by = {r["field"]: r for r in res.stale}
    assert by["url"]["current"] == "https://hand-edited.test/mcp" and by["url"]["label"] == "URL"
    assert by["headers.X-New"] == {
        "field": "headers.X-New",
        "label": "Header X-New",
        "current": "theirs",
        "proposed": "mine",
    }
    assert (await world.repo.get(pid)).status == "pending"
    assert (await world.deps.mcp_repo.get(H)).config["url"] == "https://hand-edited.test/mcp"
    assert (await run(world, pid, override=True)).outcome == "applied"
    assert (await world.deps.mcp_repo.get(H)).config["url"] == "https://new.test/mcp"


async def test_a_deleted_target_withdraws_the_proposal(world, frames) -> None:
    pid = await make(world, "change", {"url": "https://a.test/"}, H)
    await world.deps.mcp_repo.delete(H)
    res = await run(world, pid)
    assert res.outcome == "gone" and (await world.repo.get(pid)).status == "withdrawn"
    assert frames.config == []


async def test_a_failure_carries_the_services_items(world, frames) -> None:
    # a plain row proposed, then stored as Sensitive before the approval: the service refuses
    pid = await make(world, "change", {"headers": {"X-Plain": "v"}}, H)
    await world.deps.mcp_repo.update_in_txn(
        H,
        lambda cur: cur.model_copy(update={"secrets": {**cur.secrets, "X-Plain": "sensitive-now"}}),
    )
    res = await run(world, pid)
    assert res.outcome == "failed" and res.view["status"] == "failed"
    [err] = res.view["result"]["errors"]
    assert err["loc"] == ["headers", "X-Plain"] and "stored as a Sensitive value" in err["msg"]
    assert (await world.deps.mcp_repo.get(H)).config["headers"]["X-Plain"] != "v"
    assert frames.config == []


async def test_a_name_taken_since_the_proposal_still_applies(world, frames) -> None:
    # Names are not unique in the routes; the kind's own check is at propose time only.
    pid = await make(world, "create", http_create())
    await world.deps.mcp_repo.create(
        MCPSource(
            id="late", name="Remote", type="streamable-http", config={"url": "https://l.test/"}
        )
    )
    assert (await run(world, pid)).outcome == "applied"


@pytest.mark.parametrize("action", ["create", "change"])
async def test_two_concurrent_approves_apply_once(world, frames, action) -> None:
    if action == "create":
        pid = await make(world, "create", http_create())
    else:
        pid = await make(world, "change", {"headers": {"X-Plain": "once"}}, H)
    first, second = await asyncio.gather(run(world, pid), run(world, pid))
    assert sorted([first.outcome, second.outcome]) == ["already_applied", "applied"]
    assert len(frames.config) == 1
    names = [s.name for s in await world.deps.mcp_repo.list() if s.name == "Remote"]
    assert len(names) == (1 if action == "create" else 0)


async def test_the_status_mark_rides_in_the_write_a_lost_race_creates_nothing(
    world, frames, monkeypatch
) -> None:
    pid = await make(world, "create", http_create())
    monkeypatch.setattr(proposal_apply, "mark_op", _false)  # the mark finds the row resolved
    before = len(await world.deps.mcp_repo.list())
    res = await run(world, pid)
    assert res.outcome == "closed"
    assert len(await world.deps.mcp_repo.list()) == before  # the insert rolled back with it
    assert frames.config == []


async def _false(*args, **kwargs):
    return False


async def test_a_rename_by_proposal_carries_into_the_attached_agents_override_key(
    world, frames
) -> None:
    cfg = await world.deps.store.load("wide")
    assert "Docs server" in cfg.mcp_overrides
    pid = await make(world, "change", {"name": "Docs renamed"}, H)
    assert (await run(world, pid)).outcome == "applied"
    cfg = await world.deps.store.load("wide")
    assert "Docs renamed" in cfg.mcp_overrides and "Docs server" not in cfg.mcp_overrides


# --- the guard on MCP fields (DD7 per kind), through the real propose_change --------------


def U(text) -> Message:
    return Message.user(text)


def A(*calls) -> Message:
    return Message.assistant(
        "", tool_calls=[ToolCall(id=i, name=n, arguments=a) for i, n, a in calls]
    )


def T(cid, content) -> Message:
    return Message.tool(ToolResult(tool_call_id=cid, content=content))


def fake_agent(*messages):
    return SimpleNamespace(messages=list(messages))


PAGE_URL = "https://docs.acme.test/readme"
README = (
    "[200]\n# Setup\nAdd this to your config:\n"
    '{"mcpServers": {"acme": {"command": "npx", "args": ["-y", "@acme/mcp-server"]}}}\n'
    "Or use the hosted server at https://mcp.acme.test/mcp\n"
    "Set NODE_OPTIONS=--max-old-space-size=4096 for big repos.\n"
)


def linked_history() -> list[Message]:
    """The operator typed the page's URL; the page was fetched."""
    return [
        U(f"set up the acme server from {PAGE_URL}"),
        A(("f1", "fetch_url", {"url": PAGE_URL})),
        T("f1", README),
    ]


def unlinked_history() -> list[Message]:
    """The page was fetched but the operator never typed its URL."""
    return [U("set up the acme server"), A(("f1", "fetch_url", {"url": PAGE_URL})), T("f1", README)]


def search_history() -> list[Message]:
    body = "[results]\n1. Acme MCP: run `npx -y @acme/mcp-server` or https://mcp.acme.test/mcp"
    return [
        U("set up the acme server"),
        A(("s1", "web_search", {"query": "acme mcp"})),
        T("s1", body),
    ]


async def propose(world, history, args):
    tool = ProposeChangeTool(agent_name="GleepGlorp")
    agent = fake_agent(*history, A(("c1", "propose_change", args)))
    tool.bind_agent(agent)
    token = current_turn.set(TurnContext(session_id="s1"))
    ctoken = current_tool_call_id.set("c1")
    try:
        return await tool.execute(**args)
    finally:
        current_tool_call_id.reset(ctoken)
        current_turn.reset(token)


async def recorded(world):
    return await world.repo.list_for_session("s1")


def http_call(url="https://mcp.acme.test/mcp", **extra) -> dict:
    return {
        "kind": "mcp_server",
        "action": "create",
        "changes": {"name": "Acme", "type": "streamable-http", "url": url, **extra},
    }


def stdio_call(**extra) -> dict:
    return {
        "kind": "mcp_server",
        "action": "create",
        "changes": {
            "name": "Acme",
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@acme/mcp-server"],
            **extra,
        },
    }


async def test_a_url_from_a_linked_page_is_allowed_and_flagged(world) -> None:
    out = await propose(world, linked_history(), http_call())
    assert out.startswith("Proposal "), out
    [row] = await recorded(world)
    assert row.untrusted is True and row.agent_name is None


async def test_a_url_from_an_unlinked_page_is_refused(world) -> None:
    out = await propose(world, unlinked_history(), http_call())
    assert "Nothing was recorded" in out and "URL" in out
    assert await recorded(world) == []


async def test_a_stdio_command_and_args_from_a_linked_readme_are_allowed(world) -> None:
    out = await propose(world, linked_history(), stdio_call())
    assert out.startswith("Proposal "), out


async def test_a_command_from_a_search_result_is_refused(world) -> None:
    out = await propose(world, search_history(), stdio_call())
    assert "Nothing was recorded" in out
    out = await propose(world, search_history(), http_call())
    assert "Nothing was recorded" in out
    assert await recorded(world) == []


async def test_node_options_from_a_linked_page_is_refused_and_typed_is_allowed(world) -> None:
    call = stdio_call(env={"NODE_OPTIONS": "--max-old-space-size=4096"})
    out = await propose(world, linked_history(), call)
    assert "Nothing was recorded" in out and "Environment" in out
    assert await recorded(world) == []
    typed = [
        U(f"set up acme from {PAGE_URL} with NODE_OPTIONS=--max-old-space-size=4096"),
        *linked_history()[1:],
    ]
    out = await propose(world, typed, call)
    assert out.startswith("Proposal "), out


async def test_a_secret_looking_row_is_refused_before_anything_is_recorded(world) -> None:
    out = await propose(world, [U("add a header")], http_call(headers={"X-Api-Key": "abc123"}))
    assert "looks like a secret" in out and await recorded(world) == []


async def test_the_target_parameter_and_its_conflicts(world) -> None:
    call = {
        "kind": "mcp_server",
        "action": "change",
        "target": "Docs server",
        "changes": {"headers": {"Accept": "a/b"}},
    }
    out = await propose(world, [U("tweak it")], call)
    assert out.startswith("Proposal "), out
    [row] = await recorded(world)
    assert row.target_id == H and row.agent_name is None
    call2 = {**call, "agent": "wide"}
    assert "target, not agent" in await propose(world, [U("tweak it")], call2)
    rule = {
        "kind": "rule",
        "action": "create",
        "agent": "wide",
        "target": "x",
        "changes": {"text": "t"},
    }
    assert "target isn't used for a rule" in await propose(world, [U("a rule")], rule)
    routine = {"kind": "routine", "action": "change", "target": "x", "agent": "wide", "changes": {}}
    assert "target isn't used for a routine" in await propose(world, [U("r")], routine)


async def test_target_is_an_alias_for_agent_on_an_agent(world) -> None:
    call = {"kind": "agent", "action": "change", "target": "wide", "changes": {"description": "d"}}
    out = await propose(world, [U("change it")], call)
    assert out.startswith("Proposal "), out
    clash = {**call, "agent": "plain"}
    assert "different agents" in await propose(world, [U("change it")], clash)
    same = {**call, "agent": "wide"}
    assert (await propose(world, [U("change it")], same)).startswith("Proposal ")


# --- guard.check with the relaxed keys ------------------------------------------------------

RELAXED = frozenset({"url", "command", "args"})
SHA = "ghcr.io/acme/mcp@sha256:" + "ab12" * 16


@pytest.mark.parametrize(
    "changes",
    [
        {"command": "docker", "args": ["run", "--rm", SHA]},
        {"command": SHA},
        {"url": "https://x.test/mcp/3f2504e0-4f89-11d3-9a0c-0305e82c3301/sse"},
        {"url": "https://x.test/mcp/" + "0123456789abcdef" * 4 + "/sse"},
        {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]},
        {"command": "uvx", "args": ["mcp-server-fetch"]},
    ],
)
async def test_realistic_commands_and_urls_pass_with_the_relaxed_keys(world, changes) -> None:
    assert await guard.check(world.conn, world.enc, changes, relaxed=RELAXED) is None


async def test_the_same_values_are_refused_without_the_relaxation(world) -> None:
    # falsification of the relaxation itself: a three-argument caller keeps every heuristic
    assert await guard.check(world.conn, world.enc, {"command": SHA}) is not None
    assert await guard.check(world.conn, world.enc, {"args": ["run", SHA]}) is not None


async def test_the_relaxed_keys_still_refuse_a_stored_secret_and_a_token_prefix(world) -> None:
    stored = SEEDS["mcp_secret_authorization"]
    changes = {"url": f"https://x.test/mcp?api_key={stored}"}
    assert await guard.check(world.conn, world.enc, changes, relaxed=RELAXED) == guard.REFUSAL
    prefixed = {"url": "https://x.test/mcp?k=sk-ant-" + "a1b2c3d4e5f6a7b8c9" * 2}
    assert await guard.check(world.conn, world.enc, prefixed, relaxed=RELAXED) == guard.REFUSAL
    assert await guard.check(
        world.conn, world.enc, {"args": ["--k", "ghp_" + "x" * 30]}, relaxed=RELAXED
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"headers": {"X-Custom": "sk-ant-" + "a1b2c3d4e5f6a7b8c9" * 2}},
        {"headers": {"X-Custom": "0123456789abcdef0123456789abcdef01234567"}},
        {"env": {"BENIGN": "0123456789abcdef0123456789abcdef01234567"}},
        {"headers": {"X-Custom": "Zk3Qp9Lm2Xv7Rt5Wn8Yb4Hc6Jd1Fg0Sa"}},  # high entropy run
    ],
)
async def test_rows_keep_every_heuristic_even_beside_relaxed_fields(world, changes) -> None:
    both = {"url": "https://x.test/mcp", **changes}
    assert await guard.check(world.conn, world.enc, both, relaxed=RELAXED) == guard.REFUSAL


async def test_an_args_flag_that_names_a_secret_is_refused_by_the_kind(world) -> None:
    assert "looks like a secret" in await refused(
        world, "create", stdio_create(args=["--token=abc123"])
    )
    assert ARG_TOKEN  # the seeded server stores a token in its args; it is shown as written


async def test_agent_text_with_a_hex_run_is_still_refused(world) -> None:
    changes = {"system_prompt": "use 0123456789abcdef0123456789abcdef01234567 always"}
    assert await guard.check(world.conn, world.enc, changes) == guard.REFUSAL
    out = await propose(
        world,
        [U("make an agent")],
        {"kind": "agent", "action": "create", "changes": {"name": "Hexy", **changes}},
    )
    assert "looks like a key or token" in out and await recorded(world) == []


# --- fill mode (Leg 4b): the handoff row, the type, the view ------------------------------

FILL_PAGE = {"line": "Library › MCP servers", "descriptor": {"destination": "library"}}


async def fill_mcp(world, args, *, said="set up acme at https://mcp.acme.test/mcp"):
    from the_one.gleepglorp.fill.tool import FillFormTool

    tool = FillFormTool(agent_name="GleepGlorp")
    tool.bind_agent(fake_agent(U(said), A(("c1", "fill_form", args))))
    token = current_turn.set(TurnContext(session_id="s1", page=FILL_PAGE))
    ctoken = current_tool_call_id.set("c1")
    try:
        return await tool.execute(**args)
    finally:
        current_tool_call_id.reset(ctoken)
        current_turn.reset(token)


async def fills(world):
    from the_one.gleepglorp.fill.store import GleepGlorpFillRepository

    return await GleepGlorpFillRepository(world.conn).list_for_session("s1")


def http_fill(**rows) -> dict:
    return {
        "kind": "mcp_server",
        "action": "create",
        "changes": {
            "name": "Acme",
            "type": "streamable-http",
            "url": "https://mcp.acme.test/mcp",
            **rows,
        },
    }


async def test_a_fill_accepts_an_empty_secret_looking_row_and_a_proposal_does_not(world) -> None:
    out = await fill_mcp(world, http_fill(headers={"X-Api-Key": ""}))
    assert out.startswith("Fill ") and "MCP server editor" in out, out
    [row] = await fills(world)
    assert row.changes["headers"] == {"X-Api-Key": ""} and row.agent_name is None
    # the proposal path (the default mode) still refuses the same row
    assert "empty row" in await refused(
        world, "create", {**http_fill(headers={"X-Api-Key": ""})["changes"]}
    )


async def test_a_fill_still_refuses_an_empty_row_for_a_plain_key(world) -> None:
    out = await fill_mcp(world, http_fill(headers={"Accept": ""}))
    assert "empty row" in out and not out.startswith("Fill ")
    assert await fills(world) == []


async def test_a_fill_keeps_the_oauth_and_sensitive_collision_refusals(world) -> None:
    out = await fill_mcp(
        world,
        {
            "kind": "mcp_server",
            "action": "change",
            "target": H,
            "changes": {"headers": {"Authorization": ""}},
        },
    )
    assert "stored as a Sensitive value" in out and await fills(world) == []
    out = await fill_mcp(world, http_fill(headers={"access_token": ""}))
    assert "managed by sign-in" in out and await fills(world) == []


async def test_a_fill_names_the_editor_for_a_type_change_and_takes_a_type_on_create(world) -> None:
    out = await fill_mcp(
        world,
        {"kind": "mcp_server", "action": "change", "target": H, "changes": {"type": "stdio"}},
    )
    assert "editor" in out and not out.startswith("Fill ")
    assert (await fill_mcp(world, http_fill())).startswith("Fill ")


async def test_a_fill_for_an_mcp_server_refuses_agent_and_notes_enabled(world) -> None:
    args = {**http_fill(), "agent": "plain"}
    assert "target, not agent" in await fill_mcp(world, args)
    args = http_fill()
    args["changes"]["notes_enabled"] = True
    out = await fill_mcp(world, args)
    assert not out.startswith("Fill ")
    assert await fills(world) == []


async def test_the_fill_view_of_a_change_carries_the_name_gone_and_stale(world) -> None:
    from the_one.gleepglorp.fill.store import fill_view

    args = {
        "kind": "mcp_server",
        "action": "change",
        "target": H,
        "changes": {"headers": {"X-Plain": "new"}, "name": "Docs renamed"},
    }
    assert (await fill_mcp(world, args, said="rename Docs server")).startswith("Fill ")
    [row] = await fills(world)
    view = await fill_view(world.conn, row)
    assert view["title"].endswith("“Docs server”") and view["target_gone"] is False
    assert view["stale"] == []
    assert view["changes"]["Header X-Plain"] == "new"
    # a named field changes after the fill was made
    await world.conn.execute("UPDATE mcp_sources SET name = 'Elsewhere' WHERE id = ?", (H,))
    await world.conn.commit()
    view = await fill_view(world.conn, row)
    assert [s["field"] for s in view["stale"]] == ["name"]
    assert view["stale"][0]["label"] == "Name" and view["stale"][0]["current"] == "Elsewhere"
    # the server is deleted: gone, and nothing is stale
    await world.conn.execute("DELETE FROM mcp_sources WHERE id = ?", (H,))
    await world.conn.commit()
    view = await fill_view(world.conn, row)
    assert view["target_gone"] is True and view["stale"] == []


async def test_the_outside_guard_skips_an_empty_row_value() -> None:
    from the_one.gleepglorp import outside

    assert outside.check(mcp_server.KIND, {"headers": {"X-Api-Key": ""}}, None) is None
