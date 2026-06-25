"""Context-budget governor for tool results (M16 F08 L01 / DD1).

A single, direction-aware governor applied at the agent's tool-dispatch
boundary (``Agent._execute_tool``) so EVERY ``ToolResult.content`` — from any
tool — is bounded to a fraction of the active model's context window before it
enters the conversation. This retires the per-tool *LLM-facing* caps (the web
text cap; the model-sized role of ``output_cap_bytes`` on exec) while leaving
the transport/OOM safety caps untouched.

Pure helper, unit-testable in isolation — ``govern_tool_content`` constructs no
agent or LLM. Mirrors the existing ``_cap_tool_text`` / ``_truncate_output``
truncation idioms: byte-boundary slice + ``decode(errors="replace")`` so a
multibyte codepoint split at the boundary degrades to a replacement char rather
than raising.

**The truncation marker sits OUTSIDE the budget** — it is NOT counted against
``budget``; the returned text length may exceed ``budget`` by the marker. This
matches both retired caps' convention (``_cap_tool_text`` appends after the cap,
``_truncate_output`` prepends after the cap).
"""

from __future__ import annotations

import os
from typing import Literal

# Floor for ``max_context_tokens`` (LOW-2): a provider that mis-reports 0/None
# or an absurdly small window must not yield a 0-byte or runaway budget. Treat
# anything at/below this as the base default so the governor stays robust.
_MAX_CONTEXT_TOKENS_FLOOR = 128_000

# Env-overridable governor defaults. Kept here in one place so a reader tuning
# the budget finds all three together.
#
#   THE_ONE_TOOL_RESULT_BUDGET_FRACTION  — share of the window one result may
#                                          occupy (default 1/8).
#   THE_ONE_TOOL_RESULT_BUDGET_FLOOR     — absolute byte floor (default 8 KB).
#   THE_ONE_TOOL_RESULT_BUDGET_CEILING   — absolute byte ceiling (default
#                                          256 KB). NOTE: 262_144 equals the old
#                                          ``output_cap_bytes`` default — this is
#                                          a coincidence of sane sizing, not a
#                                          coupling; the two are independent
#                                          (output_cap_bytes is now a transport
#                                          safety ceiling, this is the LLM bound).
_FRACTION_ENV = "THE_ONE_TOOL_RESULT_BUDGET_FRACTION"
_FLOOR_ENV = "THE_ONE_TOOL_RESULT_BUDGET_FLOOR"
_CEILING_ENV = "THE_ONE_TOOL_RESULT_BUDGET_CEILING"

_DEFAULT_FRACTION = 1 / 8
_DEFAULT_FLOOR_BYTES = 8_192
_DEFAULT_CEILING_BYTES = 262_144

# The floor must stay comfortably above the truncation marker length so the
# marker can't blow past a tiny budget (Edge Case: "Budget < marker length").
_MIN_FLOOR_BYTES = 256


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return default


def governor_defaults() -> tuple[float, int, int]:
    """Resolve the env-overridable ``(fraction, floor, ceiling)`` triple.

    Read at call time so monkeypatching ``os.environ`` in tests is effective
    without reloading the module (mirrors ``_get_tool_call_timeout``). The
    floor is clamped above the marker size so the marker can never exceed a
    tiny budget.
    """
    fraction = _env_float(_FRACTION_ENV, _DEFAULT_FRACTION)
    floor = max(_env_int(_FLOOR_ENV, _DEFAULT_FLOOR_BYTES), _MIN_FLOOR_BYTES)
    ceiling = _env_int(_CEILING_ENV, _DEFAULT_CEILING_BYTES)
    # Defensive: a mis-set ceiling below the floor would invert the clamp.
    ceiling = max(ceiling, floor)
    return fraction, floor, ceiling


def govern_tool_content(
    content: str,
    max_context_tokens: int | None,
    *,
    fraction: float,
    floor: int,
    ceiling: int,
    direction: Literal["head", "tail"] = "head",
    bytes_per_token: float = 4.0,
) -> str:
    """Bound ``content`` to a fraction of the model's context window.

    ``budget = clamp(int(fraction * max_context_tokens * bytes_per_token),
    floor, ceiling)``. ``max_context_tokens`` ≤ 0 / None / absurdly-small is
    floored to ``_MAX_CONTEXT_TOKENS_FLOOR`` (128k) first (LOW-2).

    No-op when ``content`` already fits the budget. Otherwise the content is
    sliced on a BYTE boundary (``encode`` → slice → ``decode(errors="replace")``
    so a split codepoint becomes a replacement char, never an exception) in the
    requested direction:

    * ``"head"`` — keep the FIRST ``budget`` bytes; append a marker (prose,
      pages, file reads — the opening is the useful part).
    * ``"tail"`` — keep the LAST ``budget`` bytes; prepend a marker (shell/exec
      output — the ``[exit code: N]`` suffix + stderr tail are the diagnostic
      part and must survive).

    The truncation marker is appended/prepended AFTER the cap and is NOT counted
    against ``budget`` — the returned length may exceed ``budget`` by the marker.
    Pure: constructs no agent/LLM, reads no globals beyond its arguments.
    """
    if max_context_tokens is None or max_context_tokens < _MAX_CONTEXT_TOKENS_FLOOR:
        max_context_tokens = _MAX_CONTEXT_TOKENS_FLOOR

    budget = int(fraction * max_context_tokens * bytes_per_token)
    if budget < floor:
        budget = floor
    elif budget > ceiling:
        budget = ceiling

    raw = content.encode("utf-8")
    if len(raw) <= budget:
        return content

    dropped = len(raw) - budget
    if direction == "tail":
        tail = raw[-budget:].decode(errors="replace")
        marker = (
            f"[... governor truncated {dropped} bytes; showing last {budget} bytes "
            f"to fit the model context budget ...]\n"
        )
        return marker + tail
    # head (default)
    head = raw[:budget].decode(errors="replace")
    marker = (
        f"\n\n[... governor truncated {dropped} bytes; showing first {budget} bytes "
        f"to fit the model context budget ...]"
    )
    return head + marker
