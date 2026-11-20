"""The eval scenario's page turn (M36 F3 L4, AC9). Offline: scripted provider, no model."""

from __future__ import annotations

import json
from pathlib import Path

import _evals_helpers as h
import pytest
from _evals_helpers import make_tree, run, simple_scenario

from evals import scripted
from evals.checks import RunTrace, TurnTrace
from evals.scenario import PageTurn, ScenarioError, StepTurn, is_user_turn, parse_scenario
from evals.scripted import text
from the_one.agent._context import current_turn
from the_one.agent.core import Agent
from the_one.llm.base import Role

evals_isolation = h.evals_isolation
real_data_dir = h.real_data_dir

BASE = """
id = "paged"
class = "hold"

[[conversations]]
turns = {turns}

[[checks]]
name = "reply_matches"
pattern = "hello"
"""
LINE = "Library › MCP servers › New MCP server"


def write(tmp_path: Path, turns: str) -> Path:
    p = tmp_path / "paged.toml"
    p.write_text(BASE.format(turns=turns), encoding="utf-8")
    return p


def test_a_page_turn_parses_with_and_without_a_descriptor(tmp_path):
    sc = parse_scenario(
        write(
            tmp_path,
            '["plain", {text = "what is this?", page = {line = "' + LINE + '"}},'
            ' {text = "fill it", page = {line = "' + LINE + '", descriptor = '
            '{destination = "library", section = "mcp", create = true}}}]',
        )
    )
    turns = sc.conversations[0]
    assert turns[0] == "plain"
    assert turns[1] == PageTurn("what is this?", {"line": LINE})
    assert turns[2].page["descriptor"] == {
        "destination": "library",
        "section": "mcp",
        "create": True,
    }
    assert is_user_turn(turns[1]) and is_user_turn("x") and not is_user_turn(StepTurn("approve"))


def test_a_page_turn_may_open_a_conversation(tmp_path):
    sc = parse_scenario(write(tmp_path, '[{text = "go", page = {line = "L"}}]'))
    assert isinstance(sc.conversations[0][0], PageTurn)


@pytest.mark.parametrize(
    ("turns", "message"),
    [
        ('["x", {text = "a"}]', "turns[1].page: is required"),
        ('["x", {page = {line = "L"}}]', "turns[1].text: is required"),
        ('["x", {text = "a", page = {}}]', "turns[1].page.line: is required"),
        ('["x", {text = "a", page = {line = ""}}]', "turns[1].page.line: is required"),
        ('["x", {text = "a", page = {line = "L", extra = 1}}]', "turns[1].page.extra: unknown"),
        ('["x", {text = "a", page = {line = "L"}, more = 1}]', "turns[1].more: unknown"),
        (
            '["x", {text = "a", page = {line = "L", descriptor = {destination = "chats"}}}]',
            "turns[1].page.descriptor: ",
        ),
        (
            '["x", {text = "a", page = {line = "L", descriptor = {bogus = 1}}}]',
            "turns[1].page.descriptor: unknown page key",
        ),
    ],
)
def test_a_bad_page_turn_is_refused_with_the_file_and_the_field(tmp_path, turns, message):
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(write(tmp_path, turns))
    assert str(exc.value).startswith("paged.toml: ") and message in str(exc.value)


def test_instantiate_expands_text_and_line_and_leaves_a_string_turn_alone(tmp_path):
    body = (
        BASE.format(
            turns='["{phrasing}", {text = "{phrasing} here", page = {line = "On {phrasing}"}}]'
        )
        + '\n[variants]\nphrasings = ["alpha"]\n'
    )
    p = tmp_path / "paged.toml"
    p.write_text(body, encoding="utf-8")
    sc = parse_scenario(p)
    inst = sc.instantiate(sc.variants()[0], "")
    assert inst.conversations[0][0] == "alpha"
    assert inst.conversations[0][1] == PageTurn("alpha here", {"line": "On alpha"})


def test_conversation_messages_carry_the_page():
    tt = TurnTrace(0, 0, "a", page={"line": LINE, "descriptor": {"destination": "library"}})
    plain = TurnTrace(0, 1, "b")
    msgs = RunTrace(turns=[tt, plain]).conversation_messages(0)
    users = [m for m in msgs if m.role == Role.USER]
    assert users[0].page == {"line": LINE}
    assert users[1].page is None


async def test_a_page_turn_reaches_step_the_context_and_the_provider(evals_isolation, monkeypatch):
    tmp = evals_isolation
    seen: list[tuple] = []
    orig = Agent.step

    def spy(self, user_input, *a, **kw):
        ctx = current_turn.get()
        seen.append((user_input, kw.get("page"), ctx.page if ctx else "none"))
        return orig(self, user_input, *a, **kw)

    monkeypatch.setattr(Agent, "step", spy)
    desc = '{destination = "library", section = "mcp", create = true}'
    turns = (
        '["say hello", {text = "and now hello", page = {line = "'
        + LINE
        + '", descriptor = '
        + desc
        + "}}]"
    )
    sdir = make_tree(tmp, {"demo": simple_scenario(turns=turns)})
    made: list[scripted.ScriptedProvider] = []

    def hook(spec, base):
        prov = scripted.ScriptedProvider([text("hello"), text("hello again")])
        made.append(prov)
        return prov

    code, run_dir = await run(tmp, sdir, hook, n=1)
    assert code == 0
    # a str turn: no keyword, no page on the context
    assert seen[0] == ("say hello", None, None)
    # a page turn: the line to step, the line and descriptor on the context
    text_, page_kw, ctx_page = seen[1]
    assert text_ == "and now hello" and page_kw == {"line": LINE}
    assert ctx_page["line"] == LINE and ctx_page["descriptor"]["section"] == "mcp"
    # the provider's request carries the page on that user message only
    sent = [m for m in made[0].calls[1]["messages"] if m.role == Role.USER]
    assert [m.page for m in sent] == [None, {"line": LINE}]
    # the transcript records the page; the plan counts both turns
    tr = json.loads((run_dir / "transcripts" / "demo__gpt-oss__f0p0__a1.json").read_text())
    assert "page" not in tr["turns"][0] and tr["turns"][1]["page"]["line"] == LINE
    assert tr["turns"][1]["user"] == "and now hello"


def test_llm_calls_counts_page_turns(tmp_path):
    from evals.harness import RunSpec
    from evals.runner import Plan

    sc = parse_scenario(
        write(tmp_path, '["a", {text = "b", page = {line = "L"}}, {approve = true}]')
    )
    plan = Plan([], [sc], [RunSpec(sc, sc.variants()[0], "m")], tmp_path)
    assert plan.llm_calls()[0] == 2
