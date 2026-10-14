"""Run outcomes, backoff policy, results, resume and transcripts (DD5).

Every run ends in one of four states:

- ``pass``: every check passed.
- ``fail``: a check failed, or the model's own behaviour broke the run
  (``max_iterations`` exhausted with no final reply, a tool-call timeout, or an
  Ollama 5xx whose error text reports a tool-call parse failure). Counted.
- ``cut-short``: only transport or quota problems, after bounded backoff.
  Excluded from pass rates; three in a row stop that model for the invocation.
- ``error``: anything else (a runner or fixture bug). Excluded.

``PlanTokenRejectedError`` (401) aborts the whole invocation. A safety-class check
that fails on database state turns the run into ``fail`` even when it would
otherwise be excluded, and such a run is never re-run.

Ollama error shapes (checked against ``the_one/llm/ollama_api.py``): both the
native ``/api/chat`` path (including ``chat_stream_native``'s separate error path)
and the ``/v1`` path raise ``httpx.HTTPStatusError`` whose text is
``"Ollama returned {status} from {url}: {detail}"``; connect and timeout paths
raise the builtin ``ConnectionError``. NOTE: no real tool-call parse failure
string exists in this repo today, so ``PARSE_ERROR_PATTERNS`` starts with the
documented "error parsing tool call" phrase only. The live smoke (leg 3) must
confirm or correct the pattern; add to the tuple, do not loosen it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from the_one.llm.base import Message, Role

PASS = "pass"
FAIL = "fail"
CUT_SHORT = "cut-short"
ERROR = "error"
COUNTED = (PASS, FAIL)
EXCLUDED = (CUT_SHORT, ERROR)

BACKOFF_SECONDS = (30.0, 120.0, 300.0)
CUT_SHORT_LIMIT = 3

PARSE_ERROR_PATTERNS = (re.compile(r"error parsing tool call", re.IGNORECASE),)


class AbortInvocationError(Exception):
    """The plan token was rejected: stop the whole invocation at once."""


@dataclass(frozen=True)
class Classification:
    kind: str  # "fail" | "transient" | "abort" | "error"
    reason: str


def _status_of(exc: BaseException) -> int | None:
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None)
    if isinstance(code, int):
        return code
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def classify_exception(exc: BaseException) -> Classification:
    """Map an exception raised while driving a run to a DD5 class."""
    import anthropic
    import httpx

    from the_one.llm.anthropic_plan_provider import (
        PlanRequestRefusedError,
        PlanTokenRejectedError,
    )

    name = type(exc).__name__
    if isinstance(exc, PlanTokenRejectedError):
        return Classification("abort", "the plan token was rejected (401)")
    if isinstance(exc, PlanRequestRefusedError):
        return Classification("transient", f"{name}: the plan refused the request")
    if isinstance(exc, (anthropic.RateLimitError, anthropic.APIConnectionError)):
        return Classification("transient", f"{name}: rate limit or connection problem")
    if isinstance(exc, ConnectionError):
        return Classification("transient", f"{name}: connection problem")
    if isinstance(exc, httpx.HTTPStatusError):
        status = _status_of(exc) or 0
        if status >= 500:
            text = str(exc)
            if any(p.search(text) for p in PARSE_ERROR_PATTERNS):
                return Classification("fail", f"HTTP {status}: model tool-call parse failure")
            return Classification("transient", f"HTTP {status} before any model output")
        return Classification("error", f"{name}: HTTP {status}")
    if isinstance(exc, anthropic.APIStatusError) and (_status_of(exc) or 0) >= 500:
        return Classification("transient", f"{name}: HTTP {_status_of(exc)}")
    return Classification("error", f"{name}")


class ModelBreaker:
    """Three consecutive ``cut-short`` runs stop that model for the invocation."""

    def __init__(self, limit: int = CUT_SHORT_LIMIT) -> None:
        self.limit = limit
        self._streak: dict[str, int] = {}

    def record(self, model: str, outcome: str) -> None:
        self._streak[model] = self._streak.get(model, 0) + 1 if outcome == CUT_SHORT else 0

    def tripped(self, model: str) -> bool:
        return self._streak.get(model, 0) >= self.limit


# ── Message and record serialisation ──────────────────────────────────────


def message_to_dict(m: Message) -> dict[str, Any]:
    out: dict[str, Any] = {"role": m.role.value}
    content = m.content
    if isinstance(content, list):
        content = [getattr(b, "text", None) or f"<{type(b).__name__}>" for b in content]
    out["content"] = content
    if m.tool_calls:
        out["tool_calls"] = [
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in m.tool_calls
        ]
    if m.tool_result is not None:
        out["tool_result"] = {
            "tool_call_id": m.tool_result.tool_call_id,
            "content": m.tool_result.content,
            "is_error": m.tool_result.is_error,
        }
    if m.usage is not None:
        out["usage"] = {
            "input_tokens": m.usage.input_tokens,
            "output_tokens": m.usage.output_tokens,
        }
    return out


def usage_totals(messages: Iterable[Message]) -> dict[str, Any]:
    calls = [m for m in messages if m.role == Role.ASSISTANT]
    first = next((m.usage.input_tokens for m in calls if m.usage), None)
    return {
        "calls": len(calls),
        "input_tokens": sum(m.usage.input_tokens for m in calls if m.usage),
        "output_tokens": sum(m.usage.output_tokens for m in calls if m.usage),
        "first_call_input_tokens": first,
    }


# ── results.jsonl, resume, transcripts ────────────────────────────────────

RunKey = tuple[str, str, str]  # (scenario, model, variant)


def record_key(rec: dict[str, Any]) -> RunKey:
    return (rec["scenario"], rec["model"], rec["variant"])


class ResultStore:
    """Append-only ``results.jsonl`` plus the resume view over it."""

    def __init__(self, run_dir: Path, redactor) -> None:
        self.run_dir = run_dir
        self.redactor = redactor
        self.path = run_dir / "results.jsonl"

    def append(self, record: dict[str, Any]) -> None:
        self.redactor.append_line(self.path, json.dumps(record, ensure_ascii=False, default=str))

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn final line from a killed process
        return out

    def finals(self) -> dict[RunKey, dict[str, Any]]:
        """Each variant is scored by its final (highest) attempt."""
        best: dict[RunKey, dict[str, Any]] = {}
        for rec in self.load():
            k = record_key(rec)
            if k not in best or rec["attempt"] >= best[k]["attempt"]:
                best[k] = rec
        return best

    def next_attempts(self, planned: Iterable[RunKey]) -> dict[RunKey, int | None]:
        """``None`` for a counted run (skip); else the attempt number to run next."""
        finals = self.finals()
        out: dict[RunKey, int | None] = {}
        for k in planned:
            rec = finals.get(k)
            if rec is None:
                out[k] = 1
            elif rec["outcome"] in COUNTED:
                out[k] = None
            else:
                out[k] = rec["attempt"] + 1
        return out


def write_transcript(run_dir: Path, redactor, stem: str, payload: dict[str, Any]) -> Path:
    d = run_dir / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{stem}.json"
    redactor.write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return path


def render_summary(
    finals: dict[RunKey, dict[str, Any]],
    *,
    stopped_models: Iterable[str] = (),
    aborted: str | None = None,
) -> str:
    """A minimal plain-text summary (the full report is a later leg)."""
    cells: dict[tuple[str, str], dict[str, int]] = {}
    for (scenario, model, _v), rec in sorted(finals.items()):
        c = cells.setdefault((scenario, model), {PASS: 0, FAIL: 0, CUT_SHORT: 0, ERROR: 0})
        c[rec["outcome"]] = c.get(rec["outcome"], 0) + 1
    lines = ["scenario  model  pass  fail  cut-short  error"]
    for (scenario, model), c in sorted(cells.items()):
        lines.append(f"{scenario}  {model}  {c[PASS]}  {c[FAIL]}  {c[CUT_SHORT]}  {c[ERROR]}")
    lines.append(f"runs: {len(finals)}")
    for m in stopped_models:
        lines.append(f"model stopped after {CUT_SHORT_LIMIT} consecutive cut-short runs: {m}")
    if aborted:
        lines.append(f"invocation aborted: {aborted}")
    return "\n".join(lines) + "\n"
