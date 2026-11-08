"""``python -m evals cache-probe``: prove prompt caching and its telemetry live (sortie 14 DD4).

A developer tool, like the rest of ``evals/``: it builds one ``haiku`` agent through the app's real
factory (padded persona, so the prompt passes the model's cache minimum in ``CACHE_MINIMUMS``), runs
one turn that asks for the current time, and reads each model call's usage from the turn trace.
It spends a few thousand plan-quota tokens per run and is never run by CI or the test gate.

The verdict is a pure function (``decide``) over the per-call usage records, so it is tested
offline on hand-built inputs. Exit codes: 0 pass, 1 fail, 2 refused (a start-up refusal, printed by
the command), 3 inconclusive (a precondition did not hold), 4 run error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

PACKAGE_DIR = Path(__file__).resolve().parent
SCENARIO_PATH = PACKAGE_DIR / "cache_probe_data" / "cache-probe.toml"
PROBE_MODEL = "haiku"
PROVIDER_LOGGER = "the_one.llm.anthropic_provider"

# The cache minimum in tokens, keyed by the model id the preset resolves to. A model not listed
# is refused before any call: add it here once its minimum is known.
CACHE_MINIMUMS = {
    "claude-haiku-4-5-20251001": 4096,
    "claude-haiku-5-5": 512,
}
# Headroom over the minimum, so a prompt just over it is not trusted.
FLOOR_HEADROOM = 256
# How much of a request may stay uncached (token-count rounding and the last few tokens).
MARGIN = 32


def cache_minimum(model: str) -> int:
    """The cache minimum for ``model``; ``EvalRefusalError`` (one line) when it is not listed."""
    from evals.env import EvalRefusalError

    try:
        return CACHE_MINIMUMS[model]
    except KeyError:
        raise EvalRefusalError(
            f"cache-probe: no cache minimum known for model {model!r}; "
            "add it to CACHE_MINIMUMS in evals/cache_probe.py"
        ) from None


def precondition_floor(model: str) -> int:
    return cache_minimum(model) + FLOOR_HEADROOM


PASS, FAIL, REFUSED, INCONCLUSIVE, RUN_ERROR = 0, 1, 2, 3, 4
VERDICT_NAMES = {
    PASS: "PASS",
    FAIL: "FAIL",
    REFUSED: "REFUSED",
    INCONCLUSIVE: "INCONCLUSIVE",
    RUN_ERROR: "RUN ERROR",
}


class CallUsage(NamedTuple):
    """One model call's mapped usage: the whole prompt, and its cache read/write parts."""

    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int

    @property
    def uncached(self) -> int:
        return self.input_tokens - self.cache_read_tokens - self.cache_write_tokens

    @property
    def total(self) -> int:
        # The whole prompt. ``max`` keeps a broken input_tokens mapping (collapsed to the
        # uncached remainder) from reading as a small prompt and hiding the failure as
        # "inconclusive"; with a correct mapping the two are equal.
        return max(self.input_tokens, self.cache_read_tokens + self.cache_write_tokens)


def decide(
    calls: list[CallUsage],
    *,
    tool_called: bool,
    strip_fired: bool,
    run_error: str | None,
    minimum: int,
    margin: int = MARGIN,
) -> tuple[int, list[str]]:
    """The verdict and its reasons. Precedence: run error (4), inconclusive preconditions (3),
    failing rules (1), pass (0). A cache strip that fired fails (1) only when the preconditions
    hold; otherwise the result is 3."""
    if run_error:
        return RUN_ERROR, [f"run error: {run_error}"]

    pre: list[str] = []
    if len(calls) < 2:
        pre.append(f"fewer than two model calls ({len(calls)})")
    if not tool_called:
        pre.append("the agent made no tool call")
    floor = minimum + FLOOR_HEADROOM
    if calls and calls[0].total <= floor:
        pre.append(
            f"call 1's prompt is {calls[0].total} tokens, at or below {floor} "
            f"(the {minimum}-token cache minimum plus headroom)"
        )
    if pre:
        return INCONCLUSIVE, pre

    c1, c2 = calls[0], calls[1]
    bad: list[str] = []
    for i, c in ((1, c1), (2, c2)):
        if c.uncached > margin:
            bad.append(
                f"call {i}: {c.uncached} tokens were not cached "
                f"(input {c.input_tokens} - read {c.cache_read_tokens} - write "
                f"{c.cache_write_tokens}), more than the margin {margin}"
            )
    if c2.cache_read_tokens < c1.input_tokens - margin:
        bad.append(
            f"call 2 read {c2.cache_read_tokens} tokens, fewer than call 1's whole prompt "
            f"{c1.input_tokens} less the margin {margin}"
        )
    for i, c in enumerate(calls, 1):
        if c.input_tokens < c.cache_read_tokens + c.cache_write_tokens:
            bad.append(
                f"call {i}: input_tokens {c.input_tokens} is below read + write "
                f"{c.cache_read_tokens + c.cache_write_tokens} (the usage mapping is broken)"
            )
    if c2.input_tokens < c1.input_tokens:
        bad.append(f"call 2's prompt {c2.input_tokens} is smaller than call 1's {c1.input_tokens}")
    if strip_fired:
        bad.append("a cache strip fired: the endpoint or SDK refused cache_control")
    if bad:
        return FAIL, bad
    return PASS, ["every rule held"]


def calls_from_trace(trace: Any) -> tuple[list[CallUsage], bool]:
    """The first turn's per-call usage, in order, and whether any assistant message called a tool.

    An assistant message with ``usage is None`` is skipped."""
    from the_one.llm.base import Role

    calls: list[CallUsage] = []
    tool_called = False
    turns = getattr(trace, "turns", None) or []
    if not turns:
        return calls, tool_called
    for m in turns[0].messages:
        if m.role != Role.ASSISTANT:
            continue
        if m.tool_calls:
            tool_called = True
        if m.usage is not None:
            calls.append(
                CallUsage(
                    m.usage.input_tokens,
                    getattr(m.usage, "cache_read_tokens", 0),
                    getattr(m.usage, "cache_write_tokens", 0),
                )
            )
    return calls, tool_called


class _WarningCapture(logging.Handler):
    """Collects WARNING records of the provider logger for the duration of the run."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())

    @property
    def strip_fired(self) -> bool:
        return any("cache_control" in m for m in self.messages)


@dataclass
class ProbeOptions:
    token_file: Path | None = None
    run_dir: Path | None = None
    models_file: Path | None = None
    environ: Any = None


def render(
    calls: list[CallUsage],
    *,
    exposure: Any,
    thinking: Any,
    strip_fired: bool,
    code: int,
    reasons: list[str],
) -> str:
    lines = [
        f"{'call':>4} {'input_tokens':>13} {'cache_read':>11} {'cache_write':>12} {'uncached':>9}"
    ]
    for i, c in enumerate(calls, 1):
        lines.append(
            f"{i:>4} {c.input_tokens:>13} {c.cache_read_tokens:>11} "
            f"{c.cache_write_tokens:>12} {c.uncached:>9}"
        )
    lines.append(f"exposure: {exposure}")
    lines.append(f"effective thinking: {thinking}")
    lines.append(f"cache strip fired: {'yes' if strip_fired else 'no'}")
    lines.append(f"verdict: {VERDICT_NAMES[code]} (exit {code})")
    lines += [f"  - {r}" for r in reasons]
    return "\n".join(lines) + "\n"


async def run_probe(opts: ProbeOptions) -> int:
    """Run the probe. Raises ``EvalRefusalError``, ``PresetError`` or ``ScenarioError`` on a
    start-up refusal (the command turns those into exit 2); returns 0, 1, 3 or 4."""
    from evals.env import StartupOptions, shutdown, startup
    from evals.harness import Harness, RunSpec
    from evals.models import load_presets, select_presets
    from evals.scenario import parse_scenario

    presets = select_presets(load_presets(opts.models_file), [PROBE_MODEL])
    preset = presets[0]
    minimum = cache_minimum(preset.model)  # refuses an unknown model before anything is spent
    scenario = parse_scenario(SCENARIO_PATH)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = opts.run_dir or (PACKAGE_DIR / "runs" / f"cache-probe-{stamp}")
    env = await startup(
        StartupOptions(
            run_dir=run_dir,
            need_token=preset.needs_token,
            token_file=opts.token_file,
            environ=opts.environ,
        )
    )
    logger = logging.getLogger(PROVIDER_LOGGER)
    capture = _WarningCapture()
    old_level = logger.level
    logger.addHandler(capture)
    logger.setLevel(min(old_level, logging.WARNING) if old_level else logging.WARNING)
    harness = None
    try:
        env.say(f"cache-probe: run directory {env.run_dir}")
        harness = Harness(env, {preset.name: preset})
        await harness.setup()
        attempt = await harness.run_once(RunSpec(scenario, scenario.variants()[0], preset.name))
        run_error: str | None = None
        if attempt.exc is not None:
            run_error = f"{type(attempt.exc).__name__}: {attempt.exc}"
        elif attempt.model_failure:
            run_error = str(attempt.model_failure)
        if run_error is not None:
            run_error = env.redactor.redact(run_error)
        calls, tool_called = calls_from_trace(attempt.trace)
        code, reasons = decide(
            calls,
            tool_called=tool_called,
            strip_fired=capture.strip_fired,
            run_error=run_error,
            minimum=minimum,
        )
        env.say(
            render(
                calls,
                exposure=attempt.exposure,
                thinking=(attempt.effective or {}).get("thinking"),
                strip_fired=capture.strip_fired,
                code=code,
                reasons=reasons,
            )
        )
        return code
    except Exception as exc:  # noqa: BLE001 - a failure of the run itself, kept apart from 3
        env.say(f"cache-probe: run error: {type(exc).__name__}: {exc}")
        return RUN_ERROR
    finally:
        logger.removeHandler(capture)
        logger.setLevel(old_level)
        if harness is not None:
            harness.close()
        await shutdown(env)
