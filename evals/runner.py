"""The invocation: plan, start up, run every planned run, shut down.

One process runs sequentially (DD3). Each finished run is appended to
``results.jsonl`` immediately; ``--resume`` skips counted runs and re-runs
``cut-short`` / ``error`` ones with attempt + 1.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from evals import outcomes as oc
from evals.checks import CheckDecl, CheckResult, evaluate_all, safety_failures
from evals.env import EvalEnv, EvalRefusalError, StartupOptions, shutdown, startup
from evals.fixtures import FixtureServer, KBFixtures
from evals.harness import (
    EXECUTION_TOOLS_STATE,
    Attempt,
    Harness,
    RunSpec,
    now_iso,
    off_fixture_fetches,
)
from evals.judge import JudgeError
from evals.models import (
    Preset,
    PresetError,
    load_presets,
    ollama_server_info,
    select_presets,
)
from evals.scenario import Scenario, ScenarioError, load_scenarios

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_SCENARIOS_DIR = PACKAGE_DIR / "scenarios"
DEFAULT_RUNS_DIR = PACKAGE_DIR / "runs"
DEFAULT_N = 20


@dataclass
class RunOptions:
    models: list[str] | None = None
    scenarios: list[str] | None = None
    scenarios_dir: Path = DEFAULT_SCENARIOS_DIR
    fixtures_dir: Path | None = None
    n: int = DEFAULT_N
    run_dir: Path | None = None
    resume: Path | None = None
    token_file: Path | None = None
    models_file: Path | None = None
    dry_run: bool = False


@dataclass
class Hooks:
    """Seams for tests; the CLI uses the defaults."""

    provider_hook: Callable[[RunSpec, str], Any] | None = None
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    backoffs: tuple[float, ...] = oc.BACKOFF_SECONDS
    after_run: Callable[[int], None] | None = None
    model_probe: Callable[[Preset], Awaitable[dict[str, Any]]] | None = None
    turn_timeout: float = 900.0
    index_timeout: float = 900.0
    environ: Any = None
    judge_client: Any = None


@dataclass
class Plan:
    presets: list[Preset]
    scenarios: list[Scenario]
    specs: list[RunSpec]
    fixtures_root: Path
    all_presets: dict[str, Preset] = field(default_factory=dict)

    @property
    def needs_token(self) -> bool:
        return any(p.needs_token for p in self.presets) or any(
            r["name"] == "judge" for s in self.scenarios for r in s.raw_checks
        )

    def llm_calls(self) -> tuple[int, int]:
        """(lower bound on model calls: one per user turn, judge calls)."""
        turns = judge = 0
        for sp in self.specs:
            inst = sp.scenario.instantiate(sp.variant, "")
            turns += sum(len(c) for c in inst.conversations)
            judge += sum(1 for d in inst.checks if d.name == "judge")
        return turns, judge


def build_plan(opts: RunOptions) -> Plan:
    fixtures_root = opts.fixtures_dir or opts.scenarios_dir.parent / "fixtures"
    all_presets = load_presets(opts.models_file)
    presets = select_presets(all_presets, opts.models)
    scenarios = load_scenarios(
        opts.scenarios_dir, ids=opts.scenarios, n=opts.n, fixtures_root=fixtures_root
    )
    if not scenarios:
        raise ScenarioError(f"{opts.scenarios_dir}: no scenarios found")
    specs = [
        RunSpec(sc, v, p.name) for p in presets for sc in scenarios for v in sc.variants()[: opts.n]
    ]
    return Plan(presets, scenarios, specs, fixtures_root, all_presets)


def print_dry_run(plan: Plan, out: Callable[[str], None] = print) -> None:
    out(f"planned runs (scenario x variant x model): {len(plan.specs)}")
    for p in plan.presets:
        for sc in plan.scenarios:
            n = sum(1 for s in plan.specs if s.model == p.name and s.scenario is sc)
            out(f"  {sc.id} [{sc.klass}] x {p.name}: {n} variants")
    turns, judge = plan.llm_calls()
    out(f"LLM calls: at least {turns} model calls (one per user turn) + {judge} judge calls")
    out("dry run: no agent was built and nothing was written")


# ── Verdicts ──────────────────────────────────────────────────────────────


@dataclass
class Verdict:
    outcome: str
    reason: str = ""
    transient: bool = False
    safety: bool = False
    results: list[CheckResult] = field(default_factory=list)


def decide(attempt: Attempt, decls: list[CheckDecl]) -> Verdict:
    """The DD5 outcome for one attempt. Raises ``AbortInvocationError`` on a 401."""
    trace = attempt.trace
    base: str | None = None  # None | "fail" | "transient" | "error"
    reason = ""
    if attempt.exc is not None:
        cls = oc.classify_exception(attempt.exc)
        if cls.kind == "abort":
            raise oc.AbortInvocationError(cls.reason)
        base, reason = cls.kind, cls.reason
    elif attempt.model_failure:
        base, reason = "fail", attempt.model_failure

    if base in (None, "fail"):
        try:
            results = evaluate_all(decls, trace)
        except JudgeError as exc:
            return Verdict(oc.ERROR, str(exc))
        except Exception as exc:  # noqa: BLE001 - a broken check is a runner bug
            return Verdict(oc.ERROR, f"a check raised {type(exc).__name__}: {exc}")
        if base == "fail":
            return Verdict(oc.FAIL, reason, results=results)
        failed = [r for r in results if not r.passed]
        if failed:
            return Verdict(oc.FAIL, f"{failed[0].name}: {failed[0].detail}", results=results)
        return Verdict(oc.PASS, results=results)

    # transient / error: excluded, unless a safety check fails on database state
    try:
        unsafe = safety_failures(decls, trace)
    except Exception:  # noqa: BLE001
        unsafe = []
    if unsafe:
        return Verdict(
            oc.FAIL, f"safety: {unsafe[0].name}: {unsafe[0].detail}", safety=True, results=unsafe
        )
    if base == "transient":
        return Verdict(oc.CUT_SHORT, reason, transient=True)
    return Verdict(oc.ERROR, reason)


def build_record(
    spec: RunSpec,
    attempt: Attempt,
    verdict: Verdict,
    *,
    retries: int,
    model_info: dict[str, Any],
    redactor,
) -> dict[str, Any]:
    msgs = [m for t in attempt.trace.turns for m in t.messages]
    cells: dict[str, bool] | None = None
    if verdict.outcome in oc.COUNTED:
        names = {r.cell for r in verdict.results} or {spec.scenario.id}
        cells = {c: all(r.passed for r in verdict.results if r.cell == c) for c in names}
        if verdict.outcome == oc.FAIL and not any(not r.passed for r in verdict.results):
            cells = {c: False for c in names}
    return {
        "run_key": "/".join(spec.key),
        "scenario": spec.scenario.id,
        "class": spec.scenario.klass,
        "cell_names": spec.scenario.cells(),
        "cell_classes": spec.scenario.cell_classes(),
        "model": spec.model,
        "variant": spec.variant.id,
        "phrasing_index": spec.variant.phrasing_index,
        "fact_index": spec.variant.fact_index,
        "attempt": spec.attempt,
        "agent_name": spec.agent_name,
        "outcome": verdict.outcome,
        "counted": verdict.outcome in oc.COUNTED,
        "reason": redactor.redact(verdict.reason),
        "safety_fail": verdict.safety,
        "retries": retries,
        "checks": [r.to_dict() for r in verdict.results],
        "cells": cells,
        "timings": {"wall_s": attempt.wall_s, "turn_s": attempt.turn_s},
        "usage": oc.usage_totals(msgs),
        "effective": attempt.effective,
        "model_info": model_info,
        "execution_tools": EXECUTION_TOOLS_STATE,
        "tool_calls": len(attempt.trace.tool_calls()),
        "notes_saved": len(attempt.trace.saved_notes),
        "fetch_requests": [f"{m} {p}" for m, p in attempt.fixture_requests],
        "off_fixture_fetches": off_fixture_fetches(attempt.trace),
        "finished_at": now_iso(),
    }


def build_transcript(
    spec: RunSpec,
    attempt: Attempt,
    verdict: Verdict,
    record: dict[str, Any],
    decls: list[CheckDecl],
) -> dict[str, Any]:
    rec = attempt.recorder
    return {
        "run": {k: record[k] for k in ("run_key", "attempt", "agent_name", "outcome", "reason")},
        "system_prompts": attempt.trace.system_prompts,
        "first_call_system_prompts": rec.systems,
        "starting_schemas": rec.starting_schemas,
        "model_calls": rec.calls,
        "turns": [
            {
                "conversation": t.conversation,
                "user": t.user,
                "messages": [oc.message_to_dict(m) for m in t.messages],
            }
            for t in attempt.trace.turns
        ],
        "notes_saved": attempt.notes,
        "fetch_requests": record["fetch_requests"],
        "checks": record["checks"],
        "error": f"{type(attempt.exc).__name__}: {attempt.exc}" if attempt.exc else None,
        "effective": attempt.effective,
    }


async def execute_run(
    harness: Harness, spec: RunSpec, hooks: Hooks, redactor, model_info: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one spec with bounded backoff on transient failures; return (record, transcript)."""
    inst = spec.scenario.instantiate(spec.variant, harness.fixture_base)
    waits = list(hooks.backoffs)
    retries = 0
    while True:
        attempt = await harness.run_once(spec)
        verdict = decide(attempt, inst.checks)
        if verdict.transient and waits:
            await harness.discard_agent(spec.agent_name)
            await hooks.sleep(waits.pop(0))
            retries += 1
            continue
        break
    record = build_record(
        spec, attempt, verdict, retries=retries, model_info=model_info, redactor=redactor
    )
    transcript = build_transcript(spec, attempt, verdict, record, inst.checks)
    return record, transcript


# ── The invocation ────────────────────────────────────────────────────────


def default_run_dir() -> Path:
    return DEFAULT_RUNS_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")


async def _model_info(preset: Preset, hooks: Hooks) -> dict[str, Any]:
    if hooks.model_probe is not None:
        return await hooks.model_probe(preset)
    if preset.type == "ollama":
        return await ollama_server_info(preset.base_url, preset.model)
    return {}


async def run_invocation(
    opts: RunOptions, hooks: Hooks | None = None, out: Callable[[str], None] = print
) -> int:
    """Return the process exit code: 0 ok, 1 a model stopped or the run aborted, 2 refused."""
    hooks = hooks or Hooks()
    try:
        plan = build_plan(opts)
    except (ScenarioError, PresetError) as exc:
        print(str(exc), flush=True)
        return 2
    if opts.dry_run:
        print_dry_run(plan, out)
        return 0
    if opts.run_dir and opts.resume:
        print("--run-dir and --resume are mutually exclusive", flush=True)
        return 2
    if opts.resume and not opts.resume.is_dir():
        print(f"--resume: {opts.resume} is not a directory", flush=True)
        return 2
    run_dir = opts.resume or opts.run_dir or default_run_dir()
    try:
        env = await startup(
            StartupOptions(
                run_dir=run_dir,
                need_token=plan.needs_token,
                token_file=opts.token_file,
                environ=hooks.environ,
            )
        )
    except EvalRefusalError as exc:
        print(str(exc), flush=True)
        return 2
    try:
        write_fingerprints(env.run_dir, opts, plan, resume=bool(opts.resume))
    except EvalRefusalError as exc:
        await shutdown(env)
        print(str(exc), flush=True)
        return 2
    return await _run_with_env(env, plan, hooks)


def write_fingerprints(run_dir: Path, opts: RunOptions, plan: Plan, *, resume: bool) -> dict:
    """Record the ``scenarios`` hash and the preset definitions (DD15) in the run directory.

    The ``models`` hash needs each model's effective values, known only after runs, so
    it is computed from the records when a report is built (``evals.report``).
    """
    import json

    from evals.fingerprint import preset_dict, scenarios_fingerprint

    data = {
        "scenarios": scenarios_fingerprint(opts.scenarios_dir, plan.fixtures_root),
        "presets": {p.name: preset_dict(p) for p in plan.presets},
    }
    path = run_dir / "fingerprints.json"
    if resume and path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old = {}
        if old.get("scenarios") not in (None, data["scenarios"]):
            raise EvalRefusalError(
                "--resume: the scenarios, fixtures or judge files changed since this run started"
            )
        data["presets"] = {**old.get("presets", {}), **data["presets"]}
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


async def _prepare_judge(env: EvalEnv, plan: Plan, hooks: Hooks) -> None:
    """Score the labelled set once per invocation that selects a judge-scored scenario."""
    import json

    from evals import judge as judge_mod

    judged = [s for s in plan.scenarios if any(r["name"] == "judge" for r in s.raw_checks)]
    if not judged:
        judge_mod.configure(None, validated=False)
        return
    client = hooks.judge_client or (judge_mod.AnthropicJudge(env.token) if env.token else None)
    if client is None:
        judge_mod.configure(None, validated=False)
        return
    agreement, ok = await asyncio.to_thread(judge_mod.validate, client, env.say)
    judge_mod.configure(client, validated=ok, agreement=agreement)
    data = {**agreement.to_dict(), "validated": ok, "floor": judge_mod.AGREEMENT_FLOOR}
    (env.run_dir / "judge.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if not ok:
        env.warn("judge-unvalidated: judge-scored runs will be excluded")


async def _run_with_env(env: EvalEnv, plan: Plan, hooks: Hooks) -> int:
    store = oc.ResultStore(env.run_dir, env.redactor)
    breaker = oc.ModelBreaker()
    stopped: list[str] = []
    aborted: str | None = None
    server: FixtureServer | None = None
    code = 0
    try:
        web_dir = plan.fixtures_root / "web"
        if web_dir.is_dir():
            server = FixtureServer(web_dir).start()
        presets = {p.name: p for p in plan.presets}
        info = {p.name: await _model_info(p, hooks) for p in plan.presets}
        harness = Harness(
            env,
            presets,
            fixture_server=server,
            kb=KBFixtures(env, plan.fixtures_root, index_timeout=hooks.index_timeout),
            model_info=info,
            provider_hook=hooks.provider_hook,
            turn_timeout=hooks.turn_timeout,
        )
        await harness.setup()
        await _prepare_judge(env, plan, hooks)
        nexts = store.next_attempts(s.key for s in plan.specs)
        done = 0
        for spec in plan.specs:
            attempt_no = nexts[spec.key]
            if attempt_no is None:
                continue
            if breaker.tripped(spec.model):
                continue
            spec = RunSpec(spec.scenario, spec.variant, spec.model, attempt_no)
            record, transcript = await execute_run(
                harness, spec, hooks, env.redactor, info.get(spec.model, {})
            )
            oc.write_transcript(env.run_dir, env.redactor, spec.stem, transcript)
            store.append(record)
            breaker.record(spec.model, record["outcome"])
            if breaker.tripped(spec.model) and spec.model not in stopped:
                stopped.append(spec.model)
            done += 1
            env.say(
                f"{record['outcome'].upper():9} {spec.scenario.id} {spec.model} "
                f"{spec.variant.id} a{spec.attempt} {record['timings']['wall_s']}s "
                f"{record['reason']}".rstrip()
            )
            if hooks.after_run is not None:
                hooks.after_run(done)
        if stopped:
            code = 1
    except oc.AbortInvocationError as exc:
        aborted = str(exc)
        env.warn(f"invocation aborted: {aborted}")
        code = 1
    finally:
        if server is not None:
            server.stop()
        summary = oc.render_summary(store.finals(), stopped_models=stopped, aborted=aborted)
        env.redactor.write_text(env.run_dir / "summary.txt", summary)
        await shutdown(env)
    return code
