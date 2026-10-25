"""The ``current_time`` built-in tool (M28 F1 L2, DD1).

Returns the current date, time and UTC offset in the operator's time zone, or
in an optional named IANA zone (followed by the operator's zone for contrast).
The clock and zone loader are looked up on ``the_one.time_zones`` at call time
so tests can monkeypatch the module seams.
"""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from the_one import time_zones
from the_one.time_zones import CURRENT_TIME_TOOL_NAME
from the_one.tools.base import Tool

__all__ = ["CURRENT_TIME_TOOL_NAME", "CurrentTimeTool"]

_ECHO_CAP = 64


class CurrentTimeTool(Tool):
    name = CURRENT_TIME_TOOL_NAME
    summary = "Tells the current date and time."
    description = (
        "Returns the current date, time and UTC offset in the operator's time zone, "
        "or in an optional named IANA time zone."
    )
    parameters = {
        "type": "object",
        "properties": {
            "zone": {
                "type": "string",
                "description": (
                    "Optional IANA time zone name, e.g. Asia/Tokyo. "
                    "Omit for the operator's time zone."
                ),
            }
        },
        "required": [],
    }

    def __init__(
        self,
        config=None,
        cross_configs=None,
        agent_name=None,
        *,
        now=None,
        zone_source=None,
    ) -> None:
        super().__init__(config, cross_configs, agent_name)
        self._now = now
        self._zone_source = zone_source

    async def execute(self, zone: str | None = None, **kwargs: Any) -> str:
        now = self._now() if self._now is not None else time_zones.utcnow()
        source = self._zone_source or time_zones.load_effective_zone
        operator = await source()
        if zone is None or zone == "":
            return "\n".join(time_zones.tool_lines(now, operator))
        if not time_zones.is_known_zone(zone):
            echoed = zone[:_ECHO_CAP] if isinstance(zone, str) else "<invalid>"
            raise ValueError(
                f"Unknown time zone '{echoed}'. "
                "Use an IANA name such as Asia/Tokyo or Europe/Paris."
            )
        requested = time_zones.EffectiveZone(zone, ZoneInfo(zone))
        lines = time_zones.tool_lines(now, requested)
        if operator.key != zone:
            lines += ["", "Operator's time zone:", *time_zones.tool_lines(now, operator)]
        return "\n".join(lines)
