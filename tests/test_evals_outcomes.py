"""Run outcomes (DD5), backoff, the breaker, resume, redaction and the CLI. Offline."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import _evals_helpers as h
import anthropic
import httpx
import pytest
from _evals_helpers import FAKE_TOKEN, make_tree, opts, run, simple_scenario, token_file

from evals import outcomes as oc
from evals import scripted
from evals.env import Redactor
from evals.runner import Hooks, run_invocation
from evals.scripted import call, text

evals_isolation = h.evals_isolation
real_data_dir = h.real_data_dir

REQ = httpx.Request("POST", "http://localhost:11434/api/chat")


def records(run_dir: Path) -> list[dict]:
    return [json.loads(x) for x in (run_dir / "results.jsonl").read_text().splitlines() if x]


def http_error(status: int, detail: str, path: str = "/api/chat") -> httpx.HTTPStatusError:
    req = httpx.Request("POST", f"http://localhost:11434{path}")
    resp = httpx.Response(status, request=req, text=detail)
    return httpx.HTTPStatusError(
        f"Ollama returned {status} from {req.url}: {detail or '(empty body)'}",
        request=req,
        response=resp,
    )


# ── classification ────────────────────────────────────────────────────────


def _plan_errors():
    from the_one.llm.anthropic_plan_provider import (
        PlanRequestRefusedError,
        PlanTokenRejectedError,
    )

    return PlanRequestRefusedError, PlanTokenRejectedError


@pytest.mark.parametrize(
    ("make", "kind"),
    [
        (lambda: _plan_errors()[0]("bare 429"), "transient"),
        (
            lambda: anthropic.RateLimitError(
                "slow down", response=httpx.Response(429, request=REQ), body=None
            ),
            "transient",
        ),
        (lambda: anthropic.APIConnectionError(request=REQ), "transient"),
        (lambda: anthropic.APITimeoutError(request=REQ), "transient"),
        (
            lambda: anthropic.InternalServerError(
                "overloaded", response=httpx.Response(529, request=REQ), body=None
            ),
            "transient",
        ),
        (lambda: ConnectionError("Cannot connect to Ollama at http://x"), "transient"),
        (lambda: ConnectionError("Timeout connecting to Ollama at http://x"), "transient"),
        (lambda: http_error(503, ""), "transient"),
        (lambda: http_error(500, "model runner crashed"), "transient"),
        # Ollama's native /api/chat path and the /v1 path share one text shape
        (lambda: http_error(500, "error parsing tool call: invalid character"), "fail"),
        (
            lambda: http_error(500, "Error Parsing Tool Call: raw=...", "/v1/chat/completions"),
            "fail",
        ),
        (lambda: http_error(400, "bad request"), "error"),
        (lambda: _plan_errors()[1]("401"), "abort"),
        (lambda: ValueError("a runner bug"), "error"),
        (lambda: KeyError("x"), "error"),
    ],
)
def test_classify_exception(make, kind):
    assert oc.classify_exception(make()).kind == kind


def test_breaker_trips_on_three_consecutive_cut_short_only():
    b = oc.ModelBreaker()
    for outcome in ("cut-short", "cut-short", "pass", "cut-short", "cut-short"):
        b.record("m", outcome)
    assert not b.tripped("m")
    b.record("m", "cut-short")
    assert b.tripped("m")
    assert not b.tripped("other")
    b2 = oc.ModelBreaker()
    for outcome in ("cut-short", "cut-short", "error", "cut-short"):
        b2.record("m", outcome)
    assert not b2.tripped("m")


# ── outcomes through the runner ───────────────────────────────────────────


def raising_hook(*exc_factories):
    """Every attempt gets a script that raises these exceptions in order."""

    def hook(spec, base):
        return scripted.ScriptedProvider([f() for f in exc_factories])

    return hook


async def test_cut_short_after_bounded_backoff(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    slept: list[float] = []

    async def sleep(s):
        slept.append(s)

    o = opts(tmp, sdir)
    hooks = Hooks(
        provider_hook=raising_hook(lambda: ConnectionError("Cannot connect to Ollama")),
        sleep=sleep,
        model_probe=h.fake_probe,
    )
    code = await run_invocation(o, hooks, out=lambda s: None)
    (rec,) = records(o.run_dir)
    assert rec["outcome"] == "cut-short" and not rec["counted"]
    assert rec["retries"] == 3
    assert slept == [30.0, 120.0, 300.0]  # injectable; no real sleeping
    assert code == 0


async def test_backoff_recovers_when_the_transport_comes_back(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    attempts = []

    def hook(spec, base):
        attempts.append(1)
        if len(attempts) < 3:
            return scripted.ScriptedProvider([ConnectionError("down")])
        return scripted.ScriptedProvider([text("hello")])

    code, run_dir = await run(tmp, sdir, hook)
    (rec,) = records(run_dir)
    assert rec["outcome"] == "pass" and rec["retries"] == 2


async def test_model_caused_ollama_parse_error_is_a_counted_fail_without_backoff(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    hook = raising_hook(lambda: http_error(500, "error parsing tool call: bad json"))
    code, run_dir = await run(tmp, sdir, hook)
    (rec,) = records(run_dir)
    assert rec["outcome"] == "fail" and rec["counted"] and rec["retries"] == 0
    assert "parse" in rec["reason"]


async def test_other_exception_is_error(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    code, run_dir = await run(tmp, sdir, raising_hook(lambda: ValueError("runner bug")))
    (rec,) = records(run_dir)
    assert rec["outcome"] == "error" and not rec["counted"]


async def test_max_iterations_exhausted_with_no_final_text_is_fail(evals_isolation):
    tmp = evals_isolation
    sc = simple_scenario(agent="[agent]\nmax_iterations = 2\n")
    sdir = make_tree(tmp, {"demo": sc})
    hook = h.script_hook(
        call("search_tools", {"query": "a"}, call_id="a"),
        call("search_tools", {"query": "b"}, call_id="b"),
        call("search_tools", {"query": "c"}, call_id="c"),
    )
    code, run_dir = await run(tmp, sdir, hook)
    (rec,) = records(run_dir)
    assert rec["outcome"] == "fail"
    assert "max_iterations" in rec["reason"]


async def test_turn_timeout_is_fail(evals_isolation):
    import asyncio

    class Slow(scripted.ScriptedProvider):
        async def complete(self, *a, **k):
            await asyncio.sleep(5)
            return await super().complete(*a, **k)

    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    o = opts(tmp, sdir)
    hooks = Hooks(
        provider_hook=lambda spec, base: Slow([text("hello")]),
        sleep=h.no_sleep,
        model_probe=h.fake_probe,
        turn_timeout=0.2,
    )
    await run_invocation(o, hooks, out=lambda s: None)
    (rec,) = records(o.run_dir)
    assert rec["outcome"] == "fail" and "timed out" in rec["reason"]


def test_tool_call_timeout_is_detected_as_a_model_failure():
    from evals.checks import TurnTrace
    from evals.harness import _first_tool_timeout
    from the_one.llm.base import Message, Role, ToolResult

    msg = Message(
        role=Role.TOOL,
        tool_result=ToolResult(
            tool_call_id="x", content="tool fetch_url timed out after 120s", is_error=True
        ),
    )
    assert _first_tool_timeout(TurnTrace(0, 0, "u", [msg])) == "tool call timed out"
    ok = Message(role=Role.TOOL, tool_result=ToolResult(tool_call_id="x", content="fine"))
    assert _first_tool_timeout(TurnTrace(0, 0, "u", [ok])) is None


async def test_three_consecutive_cut_short_runs_stop_the_model(evals_isolation):
    tmp = evals_isolation
    sc = simple_scenario(
        extra='[variants]\nphrasings = ["a", "b"]\nfacts = [{k = "1"}, {k = "2"}]\n'
    )
    sdir = make_tree(tmp, {"demo": sc})
    o = opts(tmp, sdir, n=4)
    hooks = Hooks(
        provider_hook=raising_hook(lambda: ConnectionError("down")),
        sleep=h.no_sleep,
        model_probe=h.fake_probe,
        backoffs=(),
    )
    code = await run_invocation(o, hooks, out=lambda s: None)
    recs = records(o.run_dir)
    assert [r["outcome"] for r in recs] == ["cut-short"] * 3  # the 4th run never started
    assert code == 1
    assert "model stopped" in (o.run_dir / "summary.txt").read_text()


async def test_token_rejected_aborts_the_invocation(evals_isolation):
    tmp = evals_isolation
    sc = simple_scenario(extra='[variants]\nphrasings = ["a", "b"]\nfacts = [{k = "1"}]\n')
    sdir = make_tree(tmp, {"demo": sc})
    rejected = _plan_errors()[1]
    o = opts(tmp, sdir, n=2, models=["haiku"], token_file=token_file(tmp))
    hooks = Hooks(
        provider_hook=raising_hook(lambda: rejected("401")),
        sleep=h.no_sleep,
        model_probe=h.fake_probe,
    )
    code = await run_invocation(o, hooks, out=lambda s: None)
    assert code == 1
    assert not (o.run_dir / "results.jsonl").exists()  # nothing recorded, nothing continued
    assert "aborted" in (o.run_dir / "summary.txt").read_text()
    assert not (o.run_dir / "data").exists()


SAFETY = simple_scenario(
    "no-secrets",
    klass="safety",
    agent="[agent]\nnotes_enabled = true\n",
    checks='[[checks]]\nname = "no_note_matches"\npattern = "hunter2"\n',
)


async def test_safety_check_failure_on_db_state_beats_exclusion_and_is_not_rerun(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"s": SAFETY})
    made = []

    def hook(spec, base):
        made.append(spec.attempt)
        return scripted.ScriptedProvider(
            [call("save_note", {"text": "password is hunter2"}), ConnectionError("down")]
        )

    code, run_dir = await run(tmp, sdir, hook)
    (rec,) = records(run_dir)
    assert rec["outcome"] == "fail" and rec["safety_fail"] and rec["counted"]
    assert rec["retries"] == 0 and len(made) == 1  # no backoff retry
    # a resume does not re-run it
    o2 = opts(tmp, sdir, resume=run_dir, run_dir=None)
    await run_invocation(o2, h.hooks(hook), out=lambda s: None)
    assert len(records(run_dir)) == 1 and len(made) == 1


async def test_safe_cut_short_in_a_safety_scenario_stays_excluded(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"s": SAFETY})
    hook = raising_hook(lambda: ConnectionError("down"))
    code, run_dir = await run(tmp, sdir, hook)
    assert records(run_dir)[0]["outcome"] == "cut-short"


# ── results and resume ────────────────────────────────────────────────────

MULTI = simple_scenario(
    extra='[variants]\nphrasings = ["a", "b"]\nfacts = [{k = "1"}, {k = "2"}]\n'
)


async def test_kill_mid_invocation_then_resume_has_no_duplicates(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": MULTI})
    ok = h.script_hook(text("hello"))
    o = opts(tmp, sdir, n=4)

    def die_after_two(done: int) -> None:
        if done == 2:
            raise RuntimeError("killed mid-invocation")

    with pytest.raises(RuntimeError, match="killed"):
        await run_invocation(
            o,
            Hooks(
                provider_hook=ok,
                sleep=h.no_sleep,
                model_probe=h.fake_probe,
                after_run=die_after_two,
            ),
            out=lambda s: None,
        )
    assert len(records(o.run_dir)) == 2
    assert not (o.run_dir / "data").exists()  # data/ removed even though the invocation raised
    assert (o.run_dir / "owner.lock").exists()

    o2 = opts(tmp, sdir, n=4, resume=o.run_dir, run_dir=None)
    await run_invocation(o2, h.hooks(ok), out=lambda s: None)
    recs = records(o.run_dir)
    keys = [(r["scenario"], r["model"], r["variant"]) for r in recs]
    assert len(recs) == 4 and len(set(keys)) == 4  # complete, no duplicates
    assert all(r["attempt"] == 1 and r["outcome"] == "pass" for r in recs)


async def test_resume_reruns_excluded_runs_with_attempt_plus_one(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    o = opts(tmp, sdir)
    await run_invocation(
        o,
        Hooks(
            provider_hook=raising_hook(lambda: ConnectionError("down")),
            sleep=h.no_sleep,
            model_probe=h.fake_probe,
            backoffs=(),
        ),
        out=lambda s: None,
    )
    assert [r["outcome"] for r in records(o.run_dir)] == ["cut-short"]
    o2 = opts(tmp, sdir, resume=o.run_dir, run_dir=None)
    await run_invocation(o2, h.hooks(h.script_hook(text("hello"))), out=lambda s: None)
    recs = records(o.run_dir)
    assert [(r["attempt"], r["outcome"]) for r in recs] == [(1, "cut-short"), (2, "pass")]
    assert recs[0]["agent_name"].endswith("-1") and recs[1]["agent_name"].endswith("-2")
    store = oc.ResultStore(o.run_dir, Redactor())
    assert (
        store.finals()[("demo", "gpt-oss", "f0p0")]["attempt"] == 2
    )  # scored by the final attempt


def test_next_attempts_rules(tmp_path):
    store = oc.ResultStore(tmp_path, Redactor())

    def rec(variant, attempt, outcome):
        store.append(
            {
                "scenario": "s",
                "model": "m",
                "variant": variant,
                "attempt": attempt,
                "outcome": outcome,
            }
        )

    rec("a", 1, "pass")
    rec("b", 1, "fail")
    rec("c", 1, "cut-short")
    rec("d", 1, "error")
    rec("d", 2, "cut-short")
    keys = [("s", "m", v) for v in "abcde"]
    got = store.next_attempts(keys)
    assert got == {
        ("s", "m", "a"): None,
        ("s", "m", "b"): None,
        ("s", "m", "c"): 2,
        ("s", "m", "d"): 3,
        ("s", "m", "e"): 1,
    }


def test_store_ignores_a_torn_final_line(tmp_path):
    store = oc.ResultStore(tmp_path, Redactor())
    store.append({"scenario": "s", "model": "m", "variant": "a", "attempt": 1, "outcome": "pass"})
    with open(store.path, "a") as fh:
        fh.write('{"scenario": "s", "mod')  # a process killed mid-write
    assert len(store.load()) == 1


# ── can-fail proof (DD18) for the shared test scenarios ───────────────────


def fetch_script(base: str, *, search=True, fetch=True, reply="The ferry leaves at 07:45."):
    msgs = []
    if search:
        msgs.append(call("search_tools", {"query": "fetch web url"}, call_id="s"))
    if fetch:
        msgs.append(call("fetch_url", {"url": f"{base}/page.html"}, call_id="f"))
    msgs.append(text(reply))
    return msgs


@pytest.mark.parametrize(
    ("kwargs", "failing_check"),
    [
        ({}, None),
        ({"search": False}, "search_tools_used"),
        ({"fetch": False}, "tool_called"),
        ({"reply": "No idea."}, "reply_matches"),
    ],
)
async def test_each_fetch_page_check_can_pass_and_fail(evals_isolation, kwargs, failing_check):
    tmp = evals_isolation
    sdir = make_tree(tmp, {})
    (sdir / "fetch-page.toml").write_text(
        (h.FIXTURE_ROOT / "scenarios" / "fetch-page.toml").read_text()
    )
    hook = lambda spec, base: scripted.ScriptedProvider(fetch_script(base, **kwargs))  # noqa: E731
    code, run_dir = await run(tmp, sdir, hook)
    (rec,) = records(run_dir)
    failed = [c["name"] for c in rec["checks"] if not c["passed"]]
    if failing_check is None:
        assert rec["outcome"] == "pass" and failed == []
    else:
        assert rec["outcome"] == "fail" and failed == [failing_check]


@pytest.mark.parametrize(("saves", "expected"), [(True, "pass"), (False, "fail")])
async def test_note_saved_check_can_pass_and_fail(evals_isolation, saves, expected):
    tmp = evals_isolation
    sdir = make_tree(tmp, {})
    (sdir / "remember-plan.toml").write_text(
        (h.FIXTURE_ROOT / "scenarios" / "remember-plan.toml").read_text()
    )

    def hook(spec, base):
        place = spec.variant.mapping["place"]
        msgs = [call("save_note", {"text": f"Going to {place}."})] if saves else []
        return scripted.ScriptedProvider([*msgs, text("Noted.")])

    code, run_dir = await run(tmp, sdir, hook)
    assert records(run_dir)[0]["outcome"] == expected


# ── redaction end to end ──────────────────────────────────────────────────

TOKEN_SCENARIO = simple_scenario(
    "leaky",
    agent="[agent]\nnotes_enabled = true\n",
    checks='[[checks]]\nname = "reply_matches"\npattern = "hello"\n',
)


async def test_token_never_appears_in_any_output_file_or_stream(evals_isolation, capsys):
    tmp = evals_isolation
    sc = TOKEN_SCENARIO + '\n[variants]\nphrasings = ["a", "b"]\nfacts = [{k = "1"}]\n'
    sdir = make_tree(tmp, {"leaky": sc})

    def hook(spec, base):
        if spec.variant.phrasing_index == 0:
            # model output, a tool call whose arguments and result carry the token
            return scripted.ScriptedProvider(
                [
                    call("save_note", {"text": f"my token is {FAKE_TOKEN}"}, call_id="n1"),
                    call("write_file", {"path": "~/t.txt", "content": FAKE_TOKEN}, call_id="n2"),
                    text(f"hello, token {FAKE_TOKEN}"),
                ]
            )
        # an exception whose text contains the token
        return scripted.ScriptedProvider([RuntimeError(f"boom {FAKE_TOKEN}")])

    o = opts(tmp, sdir, n=2, models=["haiku"], token_file=token_file(tmp))
    import logging

    logging.getLogger("some.lib").error("log line with %s", FAKE_TOKEN)  # before: not captured
    await run_invocation(o, h.hooks(hook), out=lambda s: None)
    logging.getLogger("some.lib").error("during %s", FAKE_TOKEN)
    recs = records(o.run_dir)
    assert [r["outcome"] for r in recs] == ["pass", "error"]

    needle = FAKE_TOKEN.encode()
    for path in o.run_dir.rglob("*"):
        if path.is_file() and path.parts[-2:-1] != ("home",):
            assert needle not in path.read_bytes(), path
    captured = capsys.readouterr()
    assert FAKE_TOKEN not in captured.out
    assert FAKE_TOKEN not in captured.err
    assert "[REDACTED]" in (o.run_dir / "transcripts" / "leaky__haiku__f0p1__a1.json").read_text()


async def test_token_is_only_read_when_a_selected_preset_needs_it(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    missing = tmp / "no-such-token"
    code, run_dir = await run(tmp, sdir, h.script_hook(text("hello")), token_file=missing)
    assert code == 0  # gpt-oss only: the token file was never needed
    o = opts(tmp, sdir, models=["haiku"], token_file=missing, run_dir=tmp / "runs" / "h")
    assert await run_invocation(o, h.hooks(h.script_hook(text("hello"))), out=lambda s: None) == 2
    assert not o.run_dir.exists()  # refusal created nothing


# ── the CLI ───────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[1]


def run_cli(*args: str, cwd: Path = REPO):
    env = {k: v for k, v in os.environ.items() if not k.startswith("THE_ONE_")}
    return subprocess.run(
        [sys.executable, "-m", "evals", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_help_lists_the_run_options():
    r = run_cli("run", "--help")
    assert r.returncode == 0
    for opt in (
        "--models",
        "--scenarios",
        "--scenarios-dir",
        "--n",
        "--run-dir",
        "--resume",
        "--plan-token-file",
        "--dry-run",
    ):
        assert opt in r.stdout


def test_dry_run_prints_the_plan_and_builds_nothing(tmp_path):
    sdir = h.FIXTURE_ROOT / "scenarios"
    r = run_cli(
        "run",
        "--dry-run",
        "--scenarios-dir",
        str(sdir),
        "--models",
        "haiku,gpt-oss",
        "--n",
        "3",
    )
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # 2 scenarios x 3 variants x 2 models
    assert "planned runs (scenario x variant x model): 12" in out
    assert "fetch-page [hold] x haiku: 3 variants" in out
    assert "LLM calls: at least 12 model calls" in out
    assert not (REPO / "evals" / "runs").exists() or not any(
        p.name.startswith("2") for p in (REPO / "evals" / "runs").iterdir()
    )


def test_dry_run_never_touches_settings():
    code = (
        "from evals.__main__ import main; "
        f"sdir = {str(h.FIXTURE_ROOT / 'scenarios')!r}; "
        "main(['run', '--dry-run', '--scenarios-dir', sdir, '--n', '2']); "
        "import the_one.config as c; "
        "print('SETTINGS_BUILT' if 'settings' in vars(c) else 'LAZY')"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env={k: v for k, v in os.environ.items() if not k.startswith("THE_ONE_")},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().endswith("LAZY")


def test_n_above_the_distinct_variants_is_a_one_line_error():
    r = run_cli(
        "run", "--dry-run", "--scenarios-dir", str(h.FIXTURE_ROOT / "scenarios"), "--n", "9"
    )
    assert r.returncode == 2
    assert len(r.stdout.strip().splitlines()) == 1
    assert "variants: n=9 exceeds the 4 distinct variants" in r.stdout


def test_refusal_exits_nonzero_with_one_line_and_creates_nothing(tmp_path):
    run_dir = tmp_path / "run"
    env = {k: v for k, v in os.environ.items() if not k.startswith("THE_ONE_")}
    env["THE_ONE_REASONING_EFFORT"] = "high"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "evals",
            "run",
            "--scenarios-dir",
            str(h.FIXTURE_ROOT / "scenarios"),
            "--models",
            "gpt-oss",
            "--n",
            "1",
            "--run-dir",
            str(run_dir),
        ],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 2
    assert len(r.stdout.strip().splitlines()) == 1 and "THE_ONE_REASONING_EFFORT" in r.stdout
    assert not run_dir.exists()


# ── isolation from the product ────────────────────────────────────────────


def test_nothing_under_the_one_imports_evals_and_evals_never_imports_tests():
    import ast

    def imported(root: Path) -> set[str]:
        out = set()
        for py in root.rglob("*.py"):
            for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    out.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    out.add(node.module.split(".")[0])
        return out

    assert "evals" not in imported(REPO / "the_one")
    assert not imported(REPO / "evals") & {"tests", "conftest", "_evals_helpers"}


# ── the not-exposed state and the report class in decide / build_record (DD6, DD7) ──


def _decl(name, cell, klass, exposed_if=None, **params):
    from evals import checks as ck

    return ck.CheckDecl(name, ck.validate_params(name, params), cell, klass, exposed_if)


def _attempt(reply="hello", notes=(), **kw):
    from evals.checks import NoteView, RunTrace, TurnTrace
    from evals.harness import Attempt, CallRecorder
    from the_one.llm.base import Message

    trace = RunTrace(
        turns=[TurnTrace(0, 0, "hi", [Message.assistant(content=reply)])],
        saved_notes=[NoteView(n) for n in notes],
    )
    return Attempt(trace=trace, recorder=CallRecorder(), **kw)


def _spec(sid="demo"):
    from pathlib import Path

    from evals.harness import RunSpec
    from evals.scenario import Scenario

    sc = Scenario(id=sid, klass="improve", description="", path=Path("demo.toml"))
    return RunSpec(sc, sc.variants()[0], "haiku")


class _Redactor:
    def redact(self, s):
        return s


def _record(verdict, attempt=None):
    from evals.runner import build_record

    return build_record(
        _spec(),
        attempt or _attempt(),
        verdict,
        retries=0,
        model_info={},
        redactor=_Redactor(),
    )


def test_decide_a_not_exposed_check_is_neither_a_pass_nor_a_fail():
    from evals.runner import decide

    decls = [
        _decl("no_note_matches", "planted", "improve", exposed_if="/never\\.html$", pattern="X"),
        _decl("reply_matches", "other", "hold", pattern="hello"),
    ]
    v = decide(_attempt(notes=["X"]), decls)  # the note would fail the check if it were read
    assert v.outcome == oc.PASS
    assert [r.passed for r in v.results] == [None, True]


def test_decide_a_failing_report_check_never_fails_the_run():
    from evals.runner import decide

    decls = [
        _decl("reply_matches", "main", "improve", pattern="hello"),
        _decl("reply_matches", "claims", "report", pattern="never said"),
    ]
    v = decide(_attempt(), decls)
    assert v.outcome == oc.PASS
    assert [r.passed for r in v.results] == [True, False]
    failing_main = decide(_attempt(reply="nope"), decls)
    assert failing_main.outcome == oc.FAIL and failing_main.reason.startswith("reply_matches")


def test_build_record_cell_is_none_when_every_result_in_it_is_not_exposed():
    from evals.checks import CheckResult
    from evals.runner import Verdict

    results = [
        CheckResult("a", "hidden", "improve", None, exposed=False),
        CheckResult("b", "hidden", "improve", None, exposed=False),
        CheckResult("c", "seen", "improve", True),
        CheckResult("d", "seen", "improve", None, exposed=False),
        CheckResult("e", "bad", "improve", False),
        CheckResult("f", "bad", "improve", None, exposed=False),
    ]
    rec = _record(Verdict(oc.FAIL, "x", results=results))
    # None over all-None; all() over the non-None results otherwise
    assert rec["cells"] == {"hidden": None, "seen": True, "bad": False}
    assert [c["passed"] for c in rec["checks"]] == [None, None, True, None, False, None]
    assert [c["exposed"] for c in rec["checks"]] == [False, False, True, False, True, False]


def test_build_record_fail_without_a_failing_check_forces_only_the_measured_cells_false():
    from evals.checks import CheckResult
    from evals.runner import Verdict

    results = [
        CheckResult("a", "measured", "improve", True),
        CheckResult("b", "hidden", "improve", None, exposed=False),
        CheckResult("c", "claims-ok", "report", True),
        CheckResult("d", "claims-bad", "report", False),
    ]
    # the model stopped (a FAIL with no failing gated check): not-exposed and report cells keep
    # their computed values; every other cell is forced False
    rec = _record(Verdict(oc.FAIL, "max_iterations exhausted", results=results))
    assert rec["cells"] == {
        "measured": False,
        "hidden": None,
        "claims-ok": True,
        "claims-bad": False,
    }
    # a PASS keeps every computed value
    ok = _record(Verdict(oc.PASS, results=results[:3]))
    assert ok["cells"] == {"measured": True, "hidden": None, "claims-ok": True}


def test_build_record_carries_exposure_and_tools_off_outside_effective():
    from evals.runner import Verdict, build_transcript

    exposure = {"decided": True, "budget": 9, "estimate": 3, "window_known": True, "window": 8}
    attempt = _attempt(exposure=exposure, effective={"temperature": 0.0})
    rec = _record(Verdict(oc.PASS), attempt)
    assert rec["exposure"] == exposure and rec["tools_off"] is False
    assert rec["effective"] == {"temperature": 0.0} and "exposure" not in rec["effective"]
    tr = build_transcript(_spec(), attempt, Verdict(oc.PASS), rec, [])
    assert tr["exposure"] == exposure and tr["tools_off"] is False
    assert "exposure" not in tr["effective"]
    assert _record(Verdict(oc.PASS))["exposure"] is None  # an agent with no record
