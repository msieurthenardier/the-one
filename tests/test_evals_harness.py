"""The harness: per-run setup, tool-free runs, clock, fixtures, containment, KB. Offline."""

from __future__ import annotations

import json
from pathlib import Path

import _evals_helpers as h
import pytest
from _evals_helpers import make_tree, run, simple_scenario

from evals import scripted
from evals.scripted import call, text

evals_isolation = h.evals_isolation
real_data_dir = h.real_data_dir


def records(run_dir: Path) -> list[dict]:
    return [json.loads(x) for x in (run_dir / "results.jsonl").read_text().splitlines() if x]


def transcript(run_dir: Path, stem: str) -> dict:
    return json.loads((run_dir / "transcripts" / f"{stem}.json").read_text())


def hook_for(factory):
    """A provider_hook built from ``factory(spec, base)`` that remembers each provider it made."""
    made: list[scripted.ScriptedProvider] = []

    def hook(spec, base):
        prov = scripted.ScriptedProvider(factory(spec, base))
        made.append(prov)
        return prov

    hook.made = made  # type: ignore[attr-defined]
    return hook


def refused(result: dict) -> bool:
    """Tools report a constraint refusal as an '[error] ...' result string."""
    return result["is_error"] or result["content"].startswith("[error]")


def tool_results(tr: dict) -> list[dict]:
    return [m["tool_result"] for t in tr["turns"] for m in t["messages"] if m["role"] == "tool"]


# ── the scripted provider (DD18) ──────────────────────────────────────────


async def test_three_step_script_search_fetch_final(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {}, with_fixtures=True)
    (sdir / "fetch-page.toml").write_text(
        (h.FIXTURE_ROOT / "scenarios" / "fetch-page.toml").read_text()
    )
    hook = hook_for(
        lambda spec, base: [
            call("search_tools", {"query": "fetch web page url"}, call_id="c1"),
            call("fetch_url", {"url": f"{base}/page.html"}, call_id="c2"),
            text("The ferry leaves at 07:45."),
        ]
    )
    code, run_dir = await run(tmp, sdir, hook, n=1)
    assert code == 0
    (rec,) = records(run_dir)
    assert rec["outcome"] == "pass", rec["checks"]
    assert [c["name"] for c in rec["checks"]] == [
        "search_tools_used",
        "tool_called",
        "reply_matches",
    ]
    assert rec["usage"]["calls"] == 3
    assert rec["usage"]["input_tokens"] == 30
    # the fixture server saw the fetch, and the transcript records it with the target
    assert rec["fetch_requests"] == ["GET /page.html"]
    tr = transcript(run_dir, "fetch-page__gpt-oss__f0p0__a1")
    calls = [tc for t in tr["turns"] for m in t["messages"] for tc in m.get("tool_calls", [])]
    assert [c["name"] for c in calls] == ["search_tools", "fetch_url"]
    assert calls[1]["arguments"]["url"].endswith("/page.html")
    assert "07:45" in tool_results(tr)[1]["content"]
    # scripted provider recorded every call, including the tool schemas it was offered
    (prov,) = hook.made
    assert len(prov.calls) == 3 and prov.remaining == 0
    first_tools = [t["name"] for t in prov.calls[0]["tools"]]
    assert first_tools[:2] == ["search_tools", "continue"] and "current_time" in first_tools


async def test_fetch_to_another_host_is_refused_and_reported(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    hook = hook_for(
        lambda spec, base: [
            call("fetch_url", {"url": "http://example.com/x"}, call_id="c1"),
            call("fetch_url", {"url": f"{base}/page.html"}, call_id="c2"),
            text("hello"),
        ]
    )
    code, run_dir = await run(tmp, sdir, hook)
    (rec,) = records(run_dir)
    assert rec["off_fixture_fetches"] == ["http://example.com/x"]
    tr = transcript(run_dir, "demo__gpt-oss__f0p0__a1")
    results = tool_results(tr)
    assert refused(results[0]) and "example.com" in results[0]["content"]
    assert not refused(results[1])
    assert rec["fetch_requests"] == ["GET /page.html"]  # nothing reached any other host


# ── tool-free runs (DD6) ──────────────────────────────────────────────────


async def test_tools_off_run_carries_no_tools_chat_prompt_and_tool_free_date_line(evals_isolation):
    from the_one.agent.config import CHAT_ONLY_PROMPT

    tmp = evals_isolation
    sc = simple_scenario(
        "tf",
        agent="[agent]\ntools_off = true\n",
        checks='[[checks]]\nname = "date_line_present"\n',
    )
    sdir = make_tree(tmp, {"tf": sc})
    hook = hook_for(lambda spec, base: [text("It is Tuesday.")])
    code, run_dir = await run(tmp, sdir, hook)
    (rec,) = records(run_dir)
    assert rec["outcome"] == "pass", rec["checks"]
    (prov,) = hook.made
    first = prov.calls[0]
    assert first["tools"] is None
    assert first["messages"][0].content.startswith(CHAT_ONLY_PROMPT)
    assert "current_time" not in first["messages"][0].content  # the tool-free wording
    tr = transcript(run_dir, "tf__gpt-oss__f0p0__a1")
    assert tr["model_calls"][0]["tools"] == []
    assert tr["starting_schemas"] == []


async def test_tools_on_run_date_line_names_the_tool(evals_isolation):
    tmp = evals_isolation
    sc = simple_scenario("to", checks='[[checks]]\nname = "date_line_present"\n')
    sdir = make_tree(tmp, {"to": sc})
    hook = hook_for(lambda spec, base: [text("ok")])
    code, run_dir = await run(tmp, sdir, hook)
    (prov,) = hook.made
    assert "current_time" in prov.calls[0]["messages"][0].content
    assert records(run_dir)[0]["outcome"] == "pass"


# ── clock and zone (DD8) ──────────────────────────────────────────────────


async def test_each_run_uses_its_own_instant_and_zone_across_create_and_tool_calls(evals_isolation):
    tmp = evals_isolation
    clock_a = '[clock]\ninstant = "2026-03-02T15:00:00Z"\nzone = "Pacific/Kiritimati"\n'
    clock_b = '[clock]\ninstant = "2026-11-05T03:30:00Z"\nzone = "America/Los_Angeles"\n'
    checks = '[[checks]]\nname = "date_line_present"\n'
    sdir = make_tree(
        tmp,
        {
            "a": simple_scenario("clock-a", extra=clock_a, checks=checks),
            "b": simple_scenario("clock-b", extra=clock_b, checks=checks),
        },
    )
    hook = hook_for(
        lambda spec, base: [call("current_time", {}, call_id="t1"), text("done")],
    )
    code, run_dir = await run(tmp, sdir, hook)
    recs = records(run_dir)
    assert [r["outcome"] for r in recs] == ["pass", "pass"]
    by_scenario = {
        s: transcript(run_dir, f"{s}__gpt-oss__f0p0__a1") for s in ("clock-a", "clock-b")
    }
    a, b = by_scenario["clock-a"], by_scenario["clock-b"]
    # Kiritimati is UTC+14: 15:00Z on Mar 2 is 05:00 on Tuesday Mar 3
    assert "Tuesday, March 3, 2026" in a["system_prompts"][0]
    assert "Tuesday, March 3, 2026" in tool_results(a)[0]["content"]
    # Los Angeles in November is UTC-8: 03:30Z on Nov 5 is Nov 4, 7:30 PM
    assert "Wednesday, November 4, 2026" in b["system_prompts"][0]
    assert "Wednesday, November 4, 2026" in tool_results(b)[0]["content"]
    assert "March 3" not in b["system_prompts"][0]
    # restored after the run
    from the_one import time_zones

    assert time_zones.utcnow.__name__ == "utcnow"
    assert time_zones.detect_system_zone.__name__ == "detect_system_zone"


# ── per-run setup: notes, rules, isolation (DD3) ──────────────────────────

NOTES_SCENARIO = """
id = "notes"
class = "hold"

[agent]
notes_enabled = true
rules = ["Always answer in metric units."]
[[agent.seeded_notes]]
text = "Seeded: the user likes tea."

[[conversations]]
turns = ["I'm going to Lisbon."]

[[conversations]]
turns = ["Where am I going?"]

[[checks]]
name = "note_saved"
pattern = "Lisbon"

[[checks]]
name = "reply_matches"
pattern = "Lisbon"
"""


async def test_note_saved_in_conversation_one_reaches_conversation_twos_prompt(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"notes": NOTES_SCENARIO})
    hook = hook_for(
        lambda spec, base: [
            call("save_note", {"text": "User is going to Lisbon."}, call_id="n1"),
            text("Noted."),
            text("You are going to Lisbon."),
        ]
    )
    code, run_dir = await run(tmp, sdir, hook)
    (rec,) = records(run_dir)
    assert rec["outcome"] == "pass", rec["checks"]
    assert rec["notes_saved"] == 1  # the seeded note is not "saved this run"
    tr = transcript(run_dir, "notes__gpt-oss__f0p0__a1")
    p1, p2 = tr["system_prompts"]
    assert "Lisbon" not in p1 and "Seeded: the user likes tea." in p1
    assert "User is going to Lisbon." in p2  # a fresh create() re-read the notes
    assert "Always answer in metric units." in p1 and "Always answer in metric units." in p2
    assert tr["notes_saved"][0]["text"] == "User is going to Lisbon."
    assert [len(x) for x in (tr["first_call_system_prompts"],)] == [2]


async def test_two_runs_never_see_each_others_notes(evals_isolation):
    tmp = evals_isolation
    sc = NOTES_SCENARIO.replace('[[conversations]]\nturns = ["Where am I going?"]\n\n', "")
    sc = sc.replace(
        'pattern = "Lisbon"\n\n[[checks]]\nname = "reply_matches"\npattern = "Lisbon"',
        'pattern = "Lisbon"',
    )
    sc += '\n[variants]\nphrasings = ["I go to {p}.", "Off to {p}."]\nfacts = [{p = "Lisbon"}]\n'
    sc = sc.replace('turns = ["I\'m going to Lisbon."]', 'turns = ["{phrasing}"]')
    sdir = make_tree(tmp, {"notes": sc})
    hook = hook_for(
        lambda spec, base: [
            call("save_note", {"text": f"Lisbon note {spec.variant.id}."}),
            text("ok"),
        ]
    )
    code, run_dir = await run(tmp, sdir, hook, n=2)
    recs = records(run_dir)
    assert [r["outcome"] for r in recs] == ["pass", "pass"]
    t0 = transcript(run_dir, "notes__gpt-oss__f0p0__a1")
    t1 = transcript(run_dir, "notes__gpt-oss__f0p1__a1")
    assert [n["text"] for n in t0["notes_saved"]] == ["Lisbon note f0p0."]
    assert [n["text"] for n in t1["notes_saved"]] == ["Lisbon note f0p1."]
    assert "Lisbon note f0p0." not in t1["system_prompts"][0]
    assert recs[0]["agent_name"] != recs[1]["agent_name"]


def test_agent_name_is_deterministic_valid_and_bounded():
    import re

    from evals.harness import RunSpec
    from evals.scenario import Scenario, Variant

    sc = Scenario(id="x" * 50, klass="hold", description="", path=Path("x.toml"))
    spec = RunSpec(sc, Variant("f10p3", 3, 10, {}), "gpt-oss", 2)
    name = spec.agent_name
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) and len(name) == 64
    assert name == RunSpec(sc, Variant("f10p3", 3, 10, {}), "gpt-oss", 2).agent_name
    assert name != RunSpec(sc, Variant("f10p3", 3, 10, {}), "gpt-oss", 3).agent_name
    short = RunSpec(
        Scenario("a", "hold", "", Path("a.toml")), Variant("f0p0", 0, 0, {}), "haiku", 1
    )
    assert short.agent_name == "ev-a-haiku-f0p0-1"


# ── containment (DD19) ────────────────────────────────────────────────────

EXEC_NAMES = (
    "shell",
    "python_exec",
    "shell_session_start",
    "shell_session_send",
    "shell_session_close",
    "shell_session_list",
)


async def test_execution_and_download_and_search_tools_are_absent(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    hook = hook_for(
        lambda spec, base: [
            call("search_tools", {"query": ""}, call_id="s1"),
            call("search_tools", {"query": "terminal interpreter script sandbox"}, call_id="s2"),
            call("shell", {"command": "echo hi", "host_access": True}, call_id="s3"),
            text("hello"),
        ]
    )
    code, run_dir = await run(tmp, sdir, hook)
    tr = transcript(run_dir, "demo__gpt-oss__f0p0__a1")
    listing, query, shell = tool_results(tr)
    for name in (*EXEC_NAMES, "web_search", "download_file"):
        assert name not in listing["content"], name
        assert name not in query["content"], name
    assert "read_file" in listing["content"] and "fetch_url" in listing["content"]
    assert refused(shell)  # the tool is not registered at all
    starting = {s["name"] for s in tr["starting_schemas"]}
    assert not starting & set(EXEC_NAMES)
    assert records(run_dir)[0]["execution_tools"] == "disabled"


async def test_write_file_home_lands_in_scratch_home_and_outside_is_refused(
    evals_isolation, tmp_path
):
    tmp = evals_isolation
    outside = tmp / "outside.txt"
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    hook = hook_for(
        lambda spec, base: [
            call("write_file", {"path": "~/x.txt", "content": "inside"}, call_id="w1"),
            call("write_file", {"path": str(outside), "content": "nope"}, call_id="w2"),
            call("read_file", {"path": "/etc/hostname"}, call_id="w3"),
            text("hello"),
        ]
    )
    code, run_dir = await run(tmp, sdir, hook)
    assert (run_dir / "home" / "x.txt").read_text() == "inside"
    assert not outside.exists()
    tr = transcript(run_dir, "demo__gpt-oss__f0p0__a1")
    r1, r2, r3 = tool_results(tr)
    assert not refused(r1)
    assert refused(r2) and refused(r3)
    # the real $HOME was never written to
    assert not (tmp / "fake-real-home" / "x.txt").exists()


async def test_agent_override_cannot_widen_the_narrowed_allowlist(evals_isolation):
    from evals.env import StartupOptions, shutdown, startup
    from evals.harness import Harness
    from evals.models import load_presets
    from the_one.agent.config import AgentConfig
    from the_one.agent.factory import AgentFactory
    from the_one.db.connection import get_connection
    from the_one.db.repositories import SQLiteAgentStore

    tmp = evals_isolation
    env = await startup(StartupOptions(run_dir=tmp / "runs" / "w"))
    try:
        presets = {"gpt-oss": load_presets()["gpt-oss"]}
        await Harness(env, presets).setup()
        conn = await get_connection()
        store = SQLiteAgentStore(conn)
        await store.save(
            AgentConfig(
                name="widen",
                provider_config_id="ev-gpt-oss",
                llm_model="gpt-oss:20b",
                tool_overrides={"read_file": {"path_allowlist": ["/"]}},
            )
        )
        with pytest.raises(ValueError, match="widens FilesystemConfig.path_allowlist"):
            await AgentFactory(store=store).create("widen")
        # an agent that only narrows further is fine, and the effective allowlist is the home
        await store.save(
            AgentConfig(
                name="narrow",
                provider_config_id="ev-gpt-oss",
                llm_model="gpt-oss:20b",
                tool_overrides={"read_file": {"path_allowlist": [str(env.home / "workspace")]}},
            )
        )
        agent = await AgentFactory(store=store).create("narrow")
        assert agent.tools.get("read_file") is not None
    finally:
        await shutdown(env)


async def test_provider_patch_overrides_real_path_and_is_scoped_to_create():
    from evals.harness import CallRecorder, provider_patch
    from the_one.agent import factory

    fake = scripted.ScriptedProvider([])
    original = factory.get_provider
    try:
        factory.get_provider = lambda name, **kw: fake
        before = factory.get_provider
        with provider_patch(tools_off=True, scripted=None, recorder=CallRecorder()):
            assert factory.get_provider is not before
            llm = factory.get_provider("ollama")
            assert llm is fake
            assert await llm.supports_tools() is False  # an async override, not a bool
        assert factory.get_provider is before  # restored
    finally:
        factory.get_provider = original


async def test_provider_patch_is_restored_after_a_run_and_a_failed_create(evals_isolation):
    from the_one.agent import factory

    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    before = factory.get_provider
    await run(tmp, sdir, hook_for(lambda spec, base: [text("hello")]))
    assert factory.get_provider is before


async def test_tool_config_rows_restrict_the_web_tools_and_narrow_the_filesystem(evals_isolation):
    from evals.env import StartupOptions, shutdown, startup
    from evals.harness import DISABLED_TOOLS, FS_TOOLS, Harness
    from evals.models import load_presets
    from the_one.config import settings
    from the_one.db.connection import get_connection
    from the_one.db.repositories import ToolConfigRepository
    from the_one.encryption import get_encryptor

    env = await startup(StartupOptions(run_dir=evals_isolation / "runs" / "rows"))
    try:
        await Harness(env, {"gpt-oss": load_presets()["gpt-oss"]}).setup()
        repo = ToolConfigRepository(await get_connection(), get_encryptor(settings.data_dir))
        rows = {c.name: c for c in await repo.list()}
        for name in ("http_request", "fetch_url"):
            assert rows[name].config["extra_allowed_hosts"] == ["127.0.0.1"]
            assert rows[name].config["host_allowlist"] == ["127.0.0.1"]
        for name in FS_TOOLS:
            assert rows[name].config["path_allowlist"] == [str(env.home)]
        for name in DISABLED_TOOLS:
            assert rows[name].enabled is False
        assert {"web_search", "download_file", "shell", "python_exec"} <= set(DISABLED_TOOLS)
    finally:
        await shutdown(env)
