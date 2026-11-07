"""The record of how an agent's tools were offered (sortie 11, DD1).

A leaf module: it imports nothing from ``the_one``. The agent factory (a later leg)
records on each agent whether its enabled tool schemas were sent up front or left to
``search_tools`` discovery, and the numbers behind that decision. The prompt evals read
it back as the ``exposure`` key of a run record.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Env-overridable exposure defaults (sortie 11 DD1, DD13). Read from the process
# environment at call time, as ``_governor.governor_defaults`` does, never from ``.env``.
FRACTION_ENV = "THE_ONE_TOOL_EXPOSURE_FRACTION"
CEILING_ENV = "THE_ONE_TOOL_EXPOSURE_CEILING_TOKENS"
DEFAULT_FRACTION = 0.25
DEFAULT_CEILING_TOKENS = 8000


def _env_fraction() -> float:
    raw = os.environ.get(FRACTION_ENV, "")
    if not raw:
        return DEFAULT_FRACTION
    try:
        value = float(raw)
    except ValueError:
        value = -1.0
    if not (value >= 0.0):  # also rejects NaN
        logger.warning("%s=%r is not a number >= 0; using %s", FRACTION_ENV, raw, DEFAULT_FRACTION)
        return DEFAULT_FRACTION
    return min(value, 1.0)


def _env_ceiling() -> int:
    raw = os.environ.get(CEILING_ENV, "")
    if not raw:
        return DEFAULT_CEILING_TOKENS
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if value < 0:
        logger.warning(
            "%s=%r is not an integer >= 0; using %d", CEILING_ENV, raw, DEFAULT_CEILING_TOKENS
        )
        return DEFAULT_CEILING_TOKENS
    return value


def exposure_defaults() -> tuple[float, int]:
    """The ``(fraction, ceiling_tokens)`` pair, resolved from the environment now."""
    return _env_fraction(), _env_ceiling()


@dataclass(frozen=True)
class ToolExposure:
    """The tool-exposure decision for one built agent.

    ``decided`` is True when every enabled tool schema is offered up front. ``budget`` is
    the token budget the estimate was compared against (``None`` when no budget could be
    computed). ``estimate`` is the estimated size of the full schema set. ``window_known``
    says whether the provider's context window was resolved, and ``window`` is that window
    (``None`` when unknown).
    """

    decided: bool
    budget: int | None
    estimate: int
    window_known: bool
    window: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_tokens(schemas: list[dict], bytes_per_token: float) -> int:
    """Estimated size in tokens of a tool-schema list as sent: JSON bytes over density."""
    size = len(json.dumps(schemas).encode())
    return math.ceil(size / (bytes_per_token if bytes_per_token > 0 else 4.0))


def decide_exposure(
    *,
    window_known: bool,
    window: int | None,
    bytes_per_token: float,
    starting: list[dict],
    candidates: list[dict],
    fraction: float | None = None,
    ceiling: int | None = None,
) -> tuple[ToolExposure, list[dict]]:
    """Decide whether to offer every candidate schema up front (sortie 11, DD1).

    ``starting`` is every schema the model sees without exposure (``search_tools``,
    ``continue`` and today's seeds); ``candidates`` the remaining enabled tools in
    registry order. The estimate covers both. The agent is exposed iff the window is
    known, the fraction is above 0 and the estimate fits
    ``min(int(fraction * window), ceiling)``. Returns the record and the schemas to
    append (empty when not exposed). ``budget`` and ``window`` are ``None`` when the
    window is unknown; ``estimate`` is always computed.
    """
    if fraction is None or ceiling is None:
        env_fraction, env_ceiling = exposure_defaults()
        fraction = env_fraction if fraction is None else fraction
        ceiling = env_ceiling if ceiling is None else ceiling
    estimate = estimate_tokens(list(starting) + list(candidates), bytes_per_token)
    if not window_known or window is None or window <= 0:
        return ToolExposure(False, None, estimate, False, None), []
    budget = min(int(fraction * window), ceiling)
    decided = fraction > 0 and estimate <= budget
    exposure = ToolExposure(decided, budget, estimate, True, window)
    return exposure, (list(candidates) if decided else [])
