"""The prompt-caching probe's verdict, argument handling and refusal path (sortie 14 DD4).

Offline: ``decide`` is a pure function over hand-built usage records, and nothing here calls a
network or a model.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from evals import cache_probe as cp
from evals.__main__ import build_parser, main
from evals.cache_probe import CallUsage, decide
from the_one.llm.base import Message, TokenUsage, ToolCall

# A passing shape: call 1 writes a 6000-token prompt, call 2 reads all of it and writes 400 more.
GOOD = [CallUsage(6000, 0, 6000), CallUsage(6400, 6000, 400)]


def verdict(calls=GOOD, *, tool_called=True, strip_fired=False, run_error=None):
    return decide(calls, tool_called=tool_called, strip_fired=strip_fired, run_error=run_error)


def test_pass():
    code, reasons = verdict()
    assert code == cp.PASS
    assert reasons


def test_pass_with_a_third_call():
    assert verdict([*GOOD, CallUsage(6500, 6400, 100)])[0] == cp.PASS


@pytest.mark.parametrize(
    "calls,needle",
    [
        # call 1 left the user message uncached (system marker only, no automatic tail)
        ([CallUsage(6000, 0, 5000), CallUsage(6400, 6000, 400)], "call 1"),
        # call 2 left its tail uncached
        ([CallUsage(6000, 0, 6000), CallUsage(6400, 6000, 100)], "call 2"),
        # call 2 read only the system prefix, not call 1's whole prompt
        ([CallUsage(6000, 0, 6000), CallUsage(6400, 5000, 1400)], "read 5000"),
        # the DD2 mapping collapsed input_tokens to the uncached remainder
        ([CallUsage(3, 0, 6000), CallUsage(3, 6000, 400)], "mapping is broken"),
        # the prompt shrank within a turn
        ([CallUsage(6000, 0, 6000), CallUsage(5900, 5900, 0)], "smaller than call 1"),
    ],
)
def test_each_fail_rule(calls, needle):
    code, reasons = verdict(calls)
    assert code == cp.FAIL
    assert any(needle in r for r in reasons), reasons


def test_the_sum_invariant_applies_to_every_call():
    calls = [*GOOD, CallUsage(5, 6400, 100)]
    code, reasons = verdict(calls)
    assert code == cp.FAIL
    assert any("call 3" in r and "mapping is broken" in r for r in reasons)


def test_a_strip_that_fired_fails_when_the_preconditions_hold():
    code, reasons = verdict(strip_fired=True)
    assert code == cp.FAIL
    assert any("cache strip fired" in r for r in reasons)


def test_a_strip_with_a_failed_precondition_is_inconclusive_not_a_fail():
    assert verdict([GOOD[0]], strip_fired=True)[0] == cp.INCONCLUSIVE


@pytest.mark.parametrize(
    "kwargs,needle",
    [
        ({"calls": [GOOD[0]]}, "fewer than two"),
        ({"calls": []}, "fewer than two"),
        ({"tool_called": False}, "no tool call"),
        (
            {"calls": [CallUsage(4352, 0, 4352), CallUsage(4400, 4352, 48)]},
            "at or below 4352",
        ),
    ],
)
def test_each_inconclusive_precondition(kwargs, needle):
    code, reasons = verdict(**kwargs)
    assert code == cp.INCONCLUSIVE
    assert any(needle in r for r in reasons), reasons


def test_one_token_over_the_floor_is_conclusive():
    assert verdict([CallUsage(4353, 0, 4353), CallUsage(4400, 4353, 47)])[0] == cp.PASS


def test_run_error_outranks_everything():
    code, reasons = verdict([], tool_called=False, strip_fired=True, run_error="429 rate limit")
    assert code == cp.RUN_ERROR
    assert "429" in reasons[0]


def test_a_collapsed_mapping_on_call_one_is_a_fail_not_inconclusive():
    # input_tokens collapsed to 3, but read + write show a 6000-token prompt.
    assert verdict([CallUsage(3, 0, 6000), CallUsage(3, 6000, 400)])[0] == cp.FAIL


# ── reading the trace ─────────────────────────────────────────────────────


def _turn(*messages):
    return SimpleNamespace(turns=[SimpleNamespace(messages=list(messages))])


def test_calls_come_from_assistant_messages_with_usage_in_order_and_skip_none():
    tc = ToolCall(id="1", name="current_time", arguments={})
    trace = _turn(
        Message.user("hi"),
        Message.assistant("", tool_calls=[tc], usage=TokenUsage(6000, 5, 0, 6000)),
        Message.assistant("no usage here"),
        Message.assistant("done", usage=TokenUsage(6400, 9, 6000, 400)),
    )
    calls, tool_called = cp.calls_from_trace(trace)
    assert calls == GOOD
    assert tool_called is True


def test_no_tool_call_and_no_turns():
    calls, tool_called = cp.calls_from_trace(_turn(Message.assistant("x", usage=TokenUsage(1, 1))))
    assert calls == [CallUsage(1, 0, 0)] and tool_called is False
    assert cp.calls_from_trace(SimpleNamespace(turns=[])) == ([], False)


def test_strip_capture_reads_cache_control_warnings():
    cap = cp._WarningCapture()
    import logging

    def rec(msg):
        return logging.LogRecord("x", logging.WARNING, "f", 1, msg, None, None)

    cap.emit(rec("unrelated warning"))
    assert cap.strip_fired is False
    cap.emit(rec("anthropic: the endpoint refused cache_control; retrying"))
    assert cap.strip_fired is True


def test_render_lists_every_call_and_the_verdict():
    text = cp.render(
        GOOD, exposure={"decided": True}, thinking=False, strip_fired=False, code=0, reasons=["ok"]
    )
    assert "6400" in text and "verdict: PASS (exit 0)" in text
    assert "cache strip fired: no" in text


# ── the scenario file and the command ─────────────────────────────────────


def test_the_probe_scenario_parses_and_is_padded():
    from evals.scenario import parse_scenario

    sc = parse_scenario(cp.SCENARIO_PATH)
    assert sc.id == "cache-probe"
    assert len(sc.persona) > 8000
    assert "{" not in sc.persona
    assert cp.SCENARIO_PATH.parent.name == "cache_probe_data"


def test_cache_probe_is_registered_with_its_arguments():
    args = build_parser().parse_args(
        ["cache-probe", "--plan-token-file", "/tmp/t", "--run-dir", "/tmp/r"]
    )
    assert args.command == "cache-probe"
    assert str(args.token_file) == "/tmp/t" and str(args.run_dir) == "/tmp/r"


def test_cache_probe_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as ei:
        main(["cache-probe", "--help"])
    assert ei.value.code == 0
    assert "--plan-token-file" in capsys.readouterr().out


def test_a_pinned_env_refusal_is_exit_two(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", "1")
    rc = main(["cache-probe", "--run-dir", str(tmp_path / "run")])
    assert rc == 2
    assert capsys.readouterr().err.strip()
    assert not (tmp_path / "run").exists()


def test_a_missing_plan_token_is_exit_two(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    rc = main(
        [
            "cache-probe",
            "--run-dir",
            str(tmp_path / "run"),
            "--plan-token-file",
            str(tmp_path / "no-such-token"),
        ]
    )
    assert rc == 2
    assert "plan token" in capsys.readouterr().err
