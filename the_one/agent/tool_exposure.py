"""The record of how an agent's tools were offered (sortie 11, DD1).

A leaf module: it imports nothing from ``the_one``. The agent factory (a later leg)
records on each agent whether its enabled tool schemas were sent up front or left to
``search_tools`` discovery, and the numbers behind that decision. The prompt evals read
it back as the ``exposure`` key of a run record.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


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
