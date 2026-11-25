"""The ``tool_config`` kind (Mission 36 F5 L4a, DD7): the settable set per tool, normalize, the
operator-only refusals, the warnings, approve through the tool-config write service (stale, key
preservation, frames), the outside-value guard on the two address fields and the fill record.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests._gleepglorp_seed import seed
from the_one.agent._context import TurnContext, current_turn
from the_one.agent.service import AgentWriteDeps
from the_one.db import _write_lock
from the_one.db.repositories import (
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.gleepglorp import kinds, outside
from the_one.gleepglorp.fill.store import GleepGlorpFillRepository, fill_view
from the_one.gleepglorp.fill.tool import FillFormTool
from the_one.gleepglorp.kinds import tool_config as tc_kind
from the_one.gleepglorp.proposals import apply as proposal_apply
from the_one.gleepglorp.proposals import guard
from the_one.gleepglorp.proposals.shape import ShapeError
from the_one.gleepglorp.proposals.store import (
    GleepGlorpProposalRepository,
    NewProposal,
    proposal_view,
)
from the_one.gleepglorp.proposals.tool import ProposeChangeTool
from the_one.tools.builtins import _TOOL_CLASSES, builtin_tool_names

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
TOOLS_PAGE = "[Built-in tools](#settings/tools)"


async def _utc():
    return UTC


@pytest.fixture
async def world(tmp_path, monkeypatch, fast_builtin_tool_names):
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
    ns.tools = ToolConfigRepository(conn, enc)
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


async def norm(world, changes, target="shell", *, mode="propose", action="change"):
    return await kinds.normalize(
        "tool_config",
        action,
        kinds.target_args("tool_config", None, None, None, target),
        changes,
        conn=world.conn,
        now=NOW,
        zone=UTC,
        enc=world.enc,
        mode=mode,
    )


async def refused(world, changes, target="shell", *, mode="propose", action="change") -> str:
    with pytest.raises(ShapeError) as e:
        await norm(world, changes, target, mode=mode, action=action)
    return str(e.value)


async def make(world, changes, target="shell", *, session="s1") -> int:
    n = await norm(world, changes, target)
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


async def warns(world, changes, target="shell", *, mode="propose") -> list[str]:
    pid = await make(world, changes, target, session=f"w{abs(hash((target, str(changes)))) % 9999}")
    return await tc_kind.warnings(world.conn, world.enc, await world.repo.get(pid), mode)


# --- the kind's declaration ---------------------------------------------------------------


def test_the_kind_is_registered_eighth_and_declared() -> None:
    k = tc_kind.KIND
    assert kinds.REGISTRY[7] is k and kinds.KINDS[7] == "tool_config"
    assert k.addressing == "id" and k.target_noun == "A built-in tool"
    assert k.label == "built-in tool"
    assert k.actions == ("change",) and k.fillable == ("change",)
    assert k.keyerror_is_gone is False
    assert k.relaxed_guard_keys == frozenset({"searxng_base_url"})
    assert [f.name for f in k.fields] == ["enabled", *tc_kind.ALLOWLIST]
    assert "tool_config" in kinds.FILLABLE
    assert "\n" not in k.summary and len(k.summary) < 100


def test_the_fields_view_shows_which_tools_expose_each_field() -> None:
    by = {f["name"]: f for f in kinds.describe("tool_config")["fields"]}
    assert "applies_to" not in by["enabled"]
    assert by["timeout_seconds_max"]["applies_to"] == [
        "shell",
        "python_exec",
        "shell_session_send",
        "http_request",
        "fetch_url",
        "download_file",
    ]
    assert by["search_backend"]["applies_to"] == ["web_search"]
    assert by["pty_session_idle_ttl_seconds"]["applies_to"] == ["shell_session_start"]
    assert by["read_size_cap_bytes"]["applies_to"] == ["read_file", "edit_file", "grep"]
    # the five search choices are in the hint, since describe has no enum
    for choice in tc_kind.SEARCH_BACKENDS:
        assert choice in by["search_backend"]["hint"]
    hint = by["search_backend"]["hint"]
    assert "Built-in tools page" in hint
    assert hint.endswith("never repeat it")
    assert "Library" not in hint
    assert by["searxng_base_url"]["provenance"] == "must come from you or a page you linked"
    assert by["google_pse_cse_id"]["provenance"] == "must come from you or a page you linked"
    # every field's stored location is nested under config, except the top-level column
    paths = {f.name: f.path for f in tc_kind.KIND.fields}
    assert paths["enabled"] == ("enabled",)
    assert paths["timeout_seconds_max"] == ("config", "timeout_seconds_max")


# --- AC3: the settable set is pinned per tool --------------------------------------------------

_EXEC = {"timeout_seconds_default", "timeout_seconds_max", "output_cap_bytes"}
_WEB = {"timeout_seconds_default", "timeout_seconds_max", "response_size_cap_bytes"}
SETTABLE = {
    "shell": _EXEC,
    "python_exec": _EXEC,
    "shell_session_send": _EXEC,
    "shell_session_start": {"pty_session_idle_ttl_seconds", "max_concurrent_sessions"},
    "shell_session_close": set(),
    "shell_session_list": set(),
    "read_file": {"read_size_cap_bytes"},
    "edit_file": {"read_size_cap_bytes"},
    "grep": {"read_size_cap_bytes"},
    "write_file": set(),
    "delete_file": set(),
    "move_file": set(),
    "mkdir": set(),
    "glob": set(),
    "list_dir": set(),
    "http_request": _WEB,
    "fetch_url": _WEB,
    "download_file": _WEB,
    "web_search": {"search_backend", "searxng_base_url", "google_pse_cse_id"},
    "send_to_platform_channel": set(),
    "fetch_channel_history": set(),
    "find_platform_destination": set(),
    "current_time": set(),
}
_SAMPLE = {
    "search_backend": "searxng",
    "searxng_base_url": "",
    "google_pse_cse_id": "",
    "timeout_seconds_max": 600,  # above every tool's default, so the cross-field rule holds
}


def test_the_table_covers_every_built_in_tool() -> None:
    assert set(SETTABLE) == set(_TOOL_CLASSES) == set(builtin_tool_names())


@pytest.mark.parametrize("tool", sorted(SETTABLE))
async def test_each_tools_settable_set_is_exactly_the_table_plus_enabled(world, tool) -> None:
    by_applies = {f.name for f in tc_kind.KIND.fields if tool in f.applies_to}
    assert by_applies == SETTABLE[tool]
    n = await norm(world, {"enabled": True}, tool)
    assert n.changes == {"enabled": True}
    for field in tc_kind.ALLOWLIST:
        spec = next(f for f in tc_kind.KIND.fields if f.name == field)
        value = _SAMPLE.get(field, spec.min)
        if field in SETTABLE[tool]:
            n = await norm(world, {field: value}, tool)
            assert n.changes == {field: value}, (tool, field)
        else:
            msg = await refused(world, {field: value}, tool)
            assert msg == f"The {tool} tool has no {spec.label} setting.", (tool, field)


def test_the_operator_only_set_is_every_config_field_minus_the_allowlist() -> None:
    union = {f for cls in _TOOL_CLASSES.values() for f in cls.Config.model_fields}
    assert set(tc_kind.OPERATOR_ONLY) == union - set(tc_kind.ALLOWLIST)
    assert list(tc_kind.OPERATOR_ONLY) == sorted(tc_kind.OPERATOR_ONLY)
    assert len(set(tc_kind.OPERATOR_ONLY)) == len(tc_kind.OPERATOR_ONLY)
    assert {
        "path_allowlist",
        "path_denylist",
        "allow_binary_files",
        "command_denylist",
        "sandbox_network_allowed",
        "host_allowlist",
        "host_denylist",
        "extra_allowed_hosts",
        "default_user_agent",
        "redirect_cap",
        "google_pse_api_key",
        "brave_api_key",
        "tavily_api_key",
    } <= set(tc_kind.OPERATOR_ONLY)
    assert not set(tc_kind.OPERATOR_ONLY) & {f.name for f in tc_kind.KIND.fields}


def test_the_turn_on_warned_set_is_the_execution_web_and_file_writing_tools() -> None:
    """Parity with ``tool-categories.js`` (the categories exist only client-side)."""
    from tests.test_tool_categories import TABLE_JS, parse_table

    rows = {slug: tools for slug, _, tools in parse_table(TABLE_JS.read_text())}
    writers = {"write_file", "edit_file", "delete_file", "move_file", "mkdir"}
    assert writers <= set(rows["filesystem"])
    assert tc_kind.TURN_ON_WARNED == set(rows["execution"]) | set(rows["web"]) | writers


# --- normalize: the target, the action gate, the sentences --------------------------------------


async def test_a_tool_is_named_by_its_exact_name_after_strip_and_lower(world) -> None:
    n = await norm(world, {"enabled": False}, "  Shell ")
    assert (n.kind, n.action, n.agent_name, n.target_id) == ("tool_config", "change", None, "shell")
    assert n.target_key == "tool_config:shell"
    assert n.base == {"enabled": True}
    assert await refused(world, {"enabled": False}, "shel") == (
        "There is no built-in tool named shel."
    )
    assert "No" not in await refused(world, {"enabled": False}, "mcp__x__y")
    assert "Say which built-in tool" in await refused(world, {"enabled": False}, None)
    assert "Say which built-in tool" in await refused(world, {"enabled": False}, "  ")


def test_an_agent_argument_is_refused_with_the_noun() -> None:
    with pytest.raises(ShapeError) as e:
        kinds.target_args("tool_config", "plain", None, None, "shell")
    assert str(e.value) == "A built-in tool is named with target, not agent."


@pytest.mark.parametrize("mode", ["propose", "fill"])
async def test_create_is_refused_by_the_action_gate_in_both_modes(world, mode) -> None:
    msg = await refused(world, {"enabled": True}, "shell", mode=mode, action="create")
    verb = "by a proposal" if mode == "propose" else "by filling its form"
    assert msg == f"A built-in tool can't be created {verb}."


async def test_values_are_type_checked_before_the_dry_run(world) -> None:
    assert "whole number" in await refused(world, {"timeout_seconds_max": True})
    assert "whole number" in await refused(world, {"timeout_seconds_max": "30"})
    assert "true or false" in await refused(world, {"enabled": "yes"})
    assert "text" in await refused(world, {"searxng_base_url": 5}, "web_search")
    assert "from 1 to 3600" in await refused(world, {"timeout_seconds_max": 5000})
    assert "from 1024 to 104857600" in await refused(world, {"output_cap_bytes": 10})


async def test_a_bad_search_backend_is_refused_and_a_good_one_is_lowered(world) -> None:
    msg = await refused(world, {"search_backend": "bing"}, "web_search")
    assert msg == "search_backend must be one of: duckduckgo, searxng, google_pse, brave, tavily."
    n = await norm(world, {"search_backend": " DuckDuckGo "}, "web_search")
    assert n.changes == {"search_backend": "duckduckgo"}


async def test_the_dry_run_applies_the_cross_field_rule_with_the_models_message(world) -> None:
    msg = await refused(world, {"timeout_seconds_max": 10})  # below the effective default of 30
    assert "Value error" not in msg and "timeout" in msg.lower(), msg
    # both named, consistent: fine
    n = await norm(world, {"timeout_seconds_default": 5, "timeout_seconds_max": 10})
    assert n.changes == {"timeout_seconds_default": 5, "timeout_seconds_max": 10}
    # a default above the stored maximum
    await world.tools.upsert("shell", {"timeout_seconds_max": 40})
    assert await refused(world, {"timeout_seconds_default": 50})


async def test_an_unrelated_bad_stored_hidden_value_does_not_refuse_the_proposal(world) -> None:
    # command_denylist is hidden from shell_session_start's editor; a stored value that no longer
    # validates must not refuse an unrelated change (the PUT's own fallback)
    await world.tools.upsert("shell_session_start", {"command_denylist": 7})
    n = await norm(world, {"max_concurrent_sessions": 3}, "shell_session_start")
    assert n.changes == {"max_concurrent_sessions": 3}


async def test_the_base_holds_the_effective_values_of_the_named_fields(world) -> None:
    # never saved: the Config defaults, enabled on
    n = await norm(world, {"timeout_seconds_max": 60, "enabled": False})
    assert n.base == {"timeout_seconds_max": 120, "enabled": True}
    await world.tools.upsert("shell", {"timeout_seconds_max": 90}, enabled=False)
    n = await norm(world, {"timeout_seconds_max": 60, "output_cap_bytes": 4096, "enabled": True})
    assert n.base == {"timeout_seconds_max": 90, "output_cap_bytes": 262144, "enabled": False}
    # each tool's own Config default
    from the_one.tools.execution import PythonExecConfig

    n = await norm(world, {"timeout_seconds_default": 5}, "python_exec")
    assert n.base == {
        "timeout_seconds_default": PythonExecConfig.model_fields["timeout_seconds_default"].default
    }


async def test_an_unknown_field_names_the_allowed_ones(world) -> None:
    msg = await refused(world, {"color": "red"})
    assert "Allowed fields: enabled, timeout_seconds_default" in msg


# --- the operator-only sentences ---------------------------------------------------------------


@pytest.mark.parametrize("mode", ["propose", "fill"])
async def test_an_operator_only_field_is_refused_with_a_sentence_linking_the_page(
    world, mode
) -> None:
    for field in tc_kind.OPERATOR_ONLY:
        msg = await refused(world, {field: "x"}, "web_search", mode=mode)
        assert "Allowed fields" not in msg, field
        if field.endswith("_api_key"):
            assert (
                msg
                == f"Only you enter API keys, on the {TOOLS_PAGE} page. I never take or fill them."
            )
        else:
            assert msg.startswith("Only you can change “") and TOOLS_PAGE in msg, msg


async def test_operator_only_names_are_listed_by_title(world) -> None:
    msg = await refused(world, {"path_allowlist": ["/"], "path_denylist": []}, "read_file")
    assert (
        msg == f"Only you can change “Allowed paths” and “Denied paths”, on the {TOOLS_PAGE} page."
    )


async def test_a_key_named_beside_other_fields_gets_the_key_sentence(world) -> None:
    msg = await refused(world, {"search_backend": "brave", "brave_api_key": "k"}, "web_search")
    assert msg.startswith("Only you enter API keys")


# --- warnings -------------------------------------------------------------------------------


async def test_turning_a_tool_off_warns_that_it_leaves_every_agent(world) -> None:
    assert await warns(world, {"enabled": False}) == [
        "Turning shell off removes it from every agent until it is turned back on."
    ]
    assert await warns(world, {"enabled": False}, "current_time") == [
        "Turning current_time off removes it from every agent until it is turned back on."
    ]


async def test_turning_a_risky_tool_on_warns_only_when_it_is_off_now(world) -> None:
    assert await warns(world, {"enabled": True}) == []  # never saved: already on
    await world.tools.upsert("shell", {}, enabled=False)
    assert await warns(world, {"enabled": True}) == [
        "Turning shell on lets every agent that allows it use it."
    ]
    await world.tools.upsert("write_file", {}, enabled=False)
    assert await warns(world, {"enabled": True}, "write_file") == [
        "Turning write_file on lets every agent that allows it use it."
    ]
    # a tool outside the warned set never gets the sentence
    await world.tools.upsert("current_time", {}, enabled=False)
    assert await warns(world, {"enabled": True}, "current_time") == []
    await world.tools.upsert("read_file", {}, enabled=False)
    assert await warns(world, {"enabled": True}, "read_file") == []


async def test_a_keyed_backend_with_no_stored_key_hands_off_to_the_page(world) -> None:
    await world.tools.upsert("web_search", {"search_backend": "duckduckgo"}, enabled=True)
    for backend in ("google_pse", "brave", "tavily"):
        assert await warns(world, {"search_backend": backend}, "web_search") == [
            f"Enter the {backend} API key on the {TOOLS_PAGE} page; search fails until then."
        ]
    for backend in ("duckduckgo", "searxng"):
        assert await warns(world, {"search_backend": backend}, "web_search") == []


async def test_a_keyed_backend_with_its_key_stored_has_no_handoff(world) -> None:
    # the seed stores a brave key (and only that one) in the encrypted secrets
    assert await warns(world, {"search_backend": "brave"}, "web_search") == []
    assert len(await warns(world, {"search_backend": "tavily"}, "web_search")) == 1


async def test_a_private_searxng_address_warns_unless_the_shared_web_row_opens_it(world) -> None:
    for url in ("http://localhost:8080", "http://127.0.0.1:8888/search", "http://10.0.0.5"):
        [w] = await warns(world, {"searxng_base_url": url}, "web_search")
        assert "local or private address" in w and "Extra allowed hosts" in w and TOOLS_PAGE in w
    # a public address, an empty value and a hostname (no DNS) never warn
    for url in ("https://search.example.com", "", "http://nas.lan:8080"):
        assert await warns(world, {"searxng_base_url": url}, "web_search") == [], url
    # stored only on fetch_url's row: the provider reads http_request's, so it still warns
    await world.tools.upsert("fetch_url", {"extra_allowed_hosts": ["localhost"]})
    assert len(await warns(world, {"searxng_base_url": "http://localhost:8080"}, "web_search")) == 1
    # the row the provider resolves WebConfig from: the first tool in _TOOL_CLASSES with it
    assert tc_kind._web_config_tool() == "http_request"
    await world.tools.upsert("http_request", {"extra_allowed_hosts": ["localhost"]})
    assert await warns(world, {"searxng_base_url": "http://localhost:8080"}, "web_search") == []


async def _narrowed_agent(world) -> None:
    store = world.deps.store
    from the_one.agent.config import AgentConfig

    await store.save(
        AgentConfig(
            name="narrowed",
            provider_config_id="p-local",
            llm_model="m",
            tool_overrides={"shell": {"timeout_seconds_max": 60}},
        )
    )


class _LoadCounter:
    def __init__(self, monkeypatch) -> None:
        self.loads = 0
        real = SQLiteAgentStore.load

        async def load(store, name):
            self.loads += 1
            return await real(store, name)

        monkeypatch.setattr(SQLiteAgentStore, "load", load)


async def test_a_number_dropping_below_an_agents_override_names_the_agent(world) -> None:
    await _narrowed_agent(world)
    [w] = await warns(world, {"timeout_seconds_max": 30})
    assert w.startswith(
        "These agents hold their own value for this tool that the new setting narrows: "
    )
    assert "narrowed: Maximum timeout (60 would no longer apply)" in w
    assert w.endswith("They keep working; each shows a notice on its Tools tab.")


async def test_the_narrowing_preview_keeps_enabled_out_of_the_config(world, monkeypatch) -> None:
    from the_one.tools import config_service

    await _narrowed_agent(world)
    seen: list[dict] = []
    real = config_service.compute_tool_config_update

    def spy(cls, name, data, existing):
        seen.append({**data, "config": dict(data["config"])})  # copy: the real call may mutate
        return real(cls, name, data, existing)

    monkeypatch.setattr(config_service, "compute_tool_config_update", spy)
    ws = await warns(world, {"timeout_seconds_max": 30, "enabled": True})
    assert any("narrowed: Maximum timeout" in w for w in ws), ws
    assert seen and all("enabled" not in d["config"] for d in seen), seen
    assert all(d["enabled"] is True for d in seen)


def test_the_text_fields_are_bounded_by_their_specs() -> None:
    bounds = {f.name: f.max for f in tc_kind.TOOL_FIELDS if f.type == "text"}
    assert bounds == {"search_backend": 32, "searxng_base_url": 2048, "google_pse_cse_id": 128}
    from the_one.gleepglorp.proposals import shape

    spec = kinds.spec_for("tool_config", "searxng_base_url")
    assert shape._check_text(spec, "https://x.example/" + "a" * 100)
    with pytest.raises(ShapeError, match="limited to 2,048"):
        shape._check_text(spec, "h" * 2049)


async def test_the_impact_sentence_matches_the_editors_dialog_wording() -> None:
    js = (ROOT / "the_one/interfaces/web/static/js/areas/admin/tools-editor.js").read_text(
        encoding="utf-8"
    )
    assert "These agents hold their own value for this tool that the new setting narrows. " in js
    assert "They keep working; each shows a notice on its Tools tab." in js
    assert " would no longer apply)" in js and "was any host; it would take the app-wide list" in js
    sentence = tc_kind._impact_sentence(
        [
            {"agent": "a", "fields": [{"field_title": "Allowed hosts", "dropped": []}]},
            {"agent": "b", "fields": [{"field_title": "Maximum timeout", "dropped": [60, 90]}]},
        ]
    )
    assert "a: Allowed hosts (was any host; it would take the app-wide list)" in sentence
    assert "b: Maximum timeout (60, 90 would no longer apply)" in sentence


async def test_no_agent_is_loaded_unless_a_number_moves_below_its_current_value(
    world, monkeypatch
) -> None:
    await _narrowed_agent(world)
    counter = _LoadCounter(monkeypatch)
    # at or above the current value, enabled, the text fields: the warning never loads an agent
    for changes, tool in (
        ({"timeout_seconds_max": 200}, "shell"),
        ({"timeout_seconds_max": 120}, "shell"),
        ({"enabled": False}, "shell"),
        ({"search_backend": "searxng"}, "web_search"),
        ({"searxng_base_url": "https://s.example.com"}, "web_search"),
        ({"google_pse_cse_id": "cse"}, "web_search"),
    ):
        await warns(world, changes, tool)
    assert counter.loads == 0
    # a drop below loads them (every agent: ``tool_overrides`` is encrypted)
    await warns(world, {"timeout_seconds_max": 30})
    assert counter.loads > 0


async def test_the_narrowing_warning_is_proposal_only_and_a_fill_loads_no_agent(
    world, monkeypatch
) -> None:
    await _narrowed_agent(world)
    counter = _LoadCounter(monkeypatch)
    assert await warns(world, {"timeout_seconds_max": 30}, mode="fill") == []
    assert counter.loads == 0


async def test_a_card_and_a_fill_for_a_never_saved_tool_render_without_a_key_error(world) -> None:
    assert await _row_count(world) == 1  # only the seeded web_search row
    pid = await make(world, {"enabled": False})
    view = await view_of(world, pid)
    assert view["title"] == "Change the shell tool" and view["target_gone"] is False
    assert view["warnings"] == [
        "Turning shell off removes it from every agent until it is turned back on."
    ]
    assert view["base"] == {"enabled": True}
    for mode in ("propose", "fill"):
        await tc_kind.warnings(world.conn, world.enc, await world.repo.get(pid), mode)
    assert await _row_count(world) == 1


async def _row_count(world) -> int:
    async with world.conn.execute("SELECT COUNT(*) FROM tool_configs") as cur:
        return (await cur.fetchone())[0]


# --- the card, the summary --------------------------------------------------------------------


async def test_the_card_names_the_tool_never_an_agent(world) -> None:
    pid = await make(world, {"timeout_seconds_max": 60})
    view = await view_of(world, pid)
    assert view["title"] == "Change the shell tool" and view["agent_name"] is None
    assert view["target_id"] == "shell"
    assert view["labels"]["timeout_seconds_max"] == "Maximum timeout"
    assert tc_kind.KIND.title(await world.repo.get(pid)) == "change the shell tool"


# --- approve ----------------------------------------------------------------------------------


async def test_approve_writes_the_named_fields_enabled_is_the_column_and_frames_go_out(
    world, frames
) -> None:
    pid = await make(world, {"timeout_seconds_max": 60, "enabled": False})
    res = await run(world, pid)
    assert res.outcome == "applied"
    row = await world.tools.get("shell")
    assert row.enabled is False and row.config["timeout_seconds_max"] == 60
    assert "enabled" not in row.config
    assert res.view["result"]["summary"] == "Changed Maximum timeout, Enabled on the shell tool"
    assert (await world.repo.get(pid)).status == "applied"
    assert [c["kind"] for c in frames.config] == ["tool_config"]
    assert frames.config[0]["target_id"] == "shell" and frames.config[0]["agent"] is None


async def test_an_approved_change_keeps_every_stored_api_key(world, frames) -> None:
    before = (await world.tools.get("web_search")).secrets
    assert before  # the seeded brave key
    pid = await make(world, {"search_backend": "searxng"}, "web_search")
    assert (await run(world, pid)).outcome == "applied"
    after = await world.tools.get("web_search")
    assert after.secrets == before and after.config["search_backend"] == "searxng"


async def test_a_write_to_a_named_field_makes_it_stale_another_field_does_not(
    world, frames
) -> None:
    await world.tools.upsert("shell", {"timeout_seconds_max": 120, "output_cap_bytes": 2048})
    pid = await make(world, {"timeout_seconds_max": 60})
    await world.tools.upsert("shell", {"timeout_seconds_max": 120, "output_cap_bytes": 4096})
    # a write to ANOTHER field: still applies
    assert (await run(world, pid)).outcome == "applied"
    pid2 = await make(world, {"timeout_seconds_max": 30}, session="s2")
    await world.tools.upsert("shell", {"timeout_seconds_max": 100})
    res = await run(world, pid2)
    assert res.outcome == "stale"
    assert res.stale == [
        {"field": "timeout_seconds_max", "label": "Maximum timeout", "current": 100, "proposed": 30}
    ]
    assert (await world.repo.get(pid2)).status == "pending"
    assert (await world.tools.get("shell")).config["timeout_seconds_max"] == 100
    assert (await run(world, pid2, override=True)).outcome == "applied"
    assert (await world.tools.get("shell")).config["timeout_seconds_max"] == 30


async def test_a_service_refusal_carries_items_and_writes_nothing(world, frames) -> None:
    pid = await make(world, {"timeout_seconds_max": 60})
    # forge a stored change the normalizer would have refused
    await world.conn.execute(
        "UPDATE gleepglorp_proposals SET changes = ? WHERE id = ?",
        ('{"timeout_seconds_max": 5000}', pid),
    )
    await world.conn.commit()
    res = await run(world, pid, override=True)
    assert res.outcome == "failed" and res.view["result"]["errors"]
    assert await _row_count(world) == 1


async def test_a_bare_key_error_from_the_service_is_not_hidden_as_gone(
    world, frames, monkeypatch
) -> None:
    from the_one.tools import config_service

    async def boom(*a, **kw):
        raise KeyError("bug")

    monkeypatch.setattr(config_service, "change_tool_config", boom)
    pid = await make(world, {"timeout_seconds_max": 60})
    with pytest.raises(KeyError):
        await run(world, pid)
    assert (await world.repo.get(pid)).status == "pending"


async def test_a_proposal_writes_no_row_before_an_approve(world) -> None:
    tool = ProposeChangeTool(agent_name="GleepGlorp")
    tool.bind_agent(SimpleNamespace(messages=[]))
    token = current_turn.set(TurnContext(session_id="s1"))
    try:
        out = await tool.execute(
            kind="tool_config", action="change", target="shell", changes={"enabled": False}
        )
        assert out.startswith("Proposal "), out
        out = await tool.execute(kind="tool_config", action="create", changes={"enabled": False})
        assert not out.startswith("Proposal "), out
    finally:
        current_turn.reset(token)
    assert await _row_count(world) == 1


# --- the outside-value guard --------------------------------------------------------------------


def _sources(typed=(), linked=()):
    pages = [
        outside.Linked(
            url="https://docs.acme.test/p",
            host="docs.acme.test",
            raw=t,
            plain=t,
            urls={outside.normalize_url(u) for u in us},
        )
        for t, us in linked
    ]
    return outside.Sources(
        typed=list(typed),
        typed_urls={
            outside.normalize_url(u) for t in typed for u in re.findall(r"https?://\S+", t)
        },
        linked=pages,
    )


def test_both_address_fields_are_declared_and_only_searxng_is_relaxed() -> None:
    by = {f.name: f for f in tc_kind.KIND.fields}
    assert by["searxng_base_url"].address_or_command and by["google_pse_cse_id"].address_or_command
    assert tc_kind.KIND.relaxed_guard_keys == frozenset({"searxng_base_url"})


def test_searxng_url_from_outside_content_is_refused_typed_or_linked_passes() -> None:
    kind = tc_kind.KIND
    url = "https://search.acme.test/"
    changes = {"searxng_base_url": url}
    assert outside.check(kind, changes, None) is not None
    assert outside.check(kind, changes, _sources(typed=["use something else"])) is not None
    assert outside.check(kind, changes, _sources(typed=[f"use {url}"])) is None  # tier 1
    linked = _sources(
        typed=["read https://docs.acme.test/p"],
        linked=[(f"search at {url}", [url])],
    )
    assert outside.check(kind, changes, linked) is None  # tier 2: a page they linked


def test_google_pse_cse_id_from_outside_content_is_refused_typed_or_linked_passes() -> None:
    kind = tc_kind.KIND
    changes = {"google_pse_cse_id": "012345678901234567890:abcdefghijk"}
    assert outside.check(kind, changes, None) is not None
    assert outside.check(kind, changes, _sources(typed=["something else"])) is not None
    assert (
        outside.check(kind, changes, _sources(typed=[f"use {changes['google_pse_cse_id']}"]))
        is None
    )
    linked = _sources(
        typed=["read https://docs.acme.test/p"],
        linked=[(f"the engine id is {changes['google_pse_cse_id']}", [])],
    )
    assert outside.check(kind, changes, linked) is None


def test_numbers_booleans_and_the_backend_word_need_no_source() -> None:
    kind = tc_kind.KIND
    changes = {"timeout_seconds_max": 60, "enabled": False, "search_backend": "brave"}
    assert outside.check(kind, changes, None) is None


async def test_a_hex_path_in_the_searxng_address_is_not_a_key_but_a_prefix_still_is(world) -> None:
    hexed = {"searxng_base_url": "https://s.example.com/" + "a1b2c3d4e5f6" * 4}
    assert await guard.check(world.conn, world.enc, hexed) is not None
    assert (
        await guard.check(world.conn, world.enc, hexed, relaxed=tc_kind.KIND.relaxed_guard_keys)
        is None
    )
    prefixed = {"searxng_base_url": "https://s.example.com/sk-ant-api03-abcdefghijklmnopqrstuvwx"}
    assert (
        await guard.check(world.conn, world.enc, prefixed, relaxed=tc_kind.KIND.relaxed_guard_keys)
        is not None
    )


# --- the fill record ----------------------------------------------------------------------------


async def test_a_fill_of_enabled_and_a_number_records_with_the_tool_name(world) -> None:
    fill_tool = FillFormTool(agent_name="GleepGlorp")
    page = {
        "line": "Settings",
        "descriptor": {"destination": "settings", "section": "tools", "item": "shell"},
    }
    token = current_turn.set(TurnContext(session_id="s2", page=page))
    try:
        out = await fill_tool.execute(
            kind="tool_config",
            action="change",
            target="shell",
            changes={"enabled": False, "timeout_seconds_max": 90},
        )
        assert out.startswith("Fill "), out
        out = await fill_tool.execute(
            kind="tool_config", action="create", target="shell", changes={"enabled": True}
        )
        assert not out.startswith("Fill "), out
    finally:
        current_turn.reset(token)
    [fill] = await GleepGlorpFillRepository(world.conn).list_for_session("s2")
    assert (fill.kind, fill.action, fill.target_id) == ("tool_config", "change", "shell")
    assert fill.changes == {"enabled": False, "timeout_seconds_max": 90}
    assert fill.base == {"enabled": True, "timeout_seconds_max": 120}
    view = await fill_view(world.conn, fill)
    assert view["title"] == "Change the shell tool" and view["target_gone"] is False
    assert view["stale"] == [] and view["clears_key"] is False
    assert await _row_count(world) == 1  # a fill writes no row


async def test_a_fill_reports_stale_rows_when_the_stored_value_moved(world) -> None:
    from the_one.gleepglorp.fill.store import NewFill

    n = await norm(world, {"timeout_seconds_max": 90}, mode="fill")
    fills = GleepGlorpFillRepository(world.conn)
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
    await world.tools.upsert("shell", {"timeout_seconds_max": 50})
    view = await fill_view(world.conn, await fills.get(fill_id))
    assert view["stale"] == [
        {"field": "timeout_seconds_max", "label": "Maximum timeout", "current": 50, "proposed": 90}
    ]
