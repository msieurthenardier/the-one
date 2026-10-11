"""The ``current_time`` built-in tool (M28 F1 L2, DD1)."""

from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo

import pytest
from conftest import FakeLLM

from the_one import time_zones as tz
from the_one.agent.core import Agent
from the_one.llm.base import Message, Role, ToolCall
from the_one.tools.base import ToolRegistry
from the_one.tools.builtins import _TOOL_CLASSES, BuiltinToolProvider
from the_one.tools.time_tool import CURRENT_TIME_TOOL_NAME, CurrentTimeTool

LA = tz.EffectiveZone("America/Los_Angeles", ZoneInfo("America/Los_Angeles"))
TOKYO = tz.EffectiveZone("Asia/Tokyo", ZoneInfo("Asia/Tokyo"))


def test_shape() -> None:
    t = CurrentTimeTool()
    assert t.name == CURRENT_TIME_TOOL_NAME == "current_time"
    assert "current date, time and UTC offset" in t.description
    assert t.parameters == {
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


def test_registered_last_in_builtins() -> None:
    assert list(_TOOL_CLASSES)[-1] == "current_time"
    assert len(_TOOL_CLASSES) == 23
    assert len(BuiltinToolProvider().get_tools()) == 23


@pytest.fixture
def tool(frozen_clock):
    async def src():
        return LA

    return CurrentTimeTool(zone_source=src)


async def test_default_output_for_operator_zone(tool, frozen_clock) -> None:
    expected = "\n".join(tz.tool_lines(frozen_clock, LA))
    assert expected.splitlines()[0] == "2026-10-10T15:45:12-07:00 (America/Los_Angeles)"
    for kwargs in ({}, {"zone": None}, {"zone": ""}, {"zone": "America/Los_Angeles"}):
        assert await tool.execute(**kwargs) == expected


async def test_other_zone_appends_operator_block(tool, frozen_clock) -> None:
    out = await tool.execute(zone="Asia/Tokyo")
    expected = "\n".join(
        [
            *tz.tool_lines(frozen_clock, TOKYO),
            "",
            "Operator's time zone:",
            *tz.tool_lines(frozen_clock, LA),
        ]
    )
    assert out == expected
    assert out.splitlines()[0] == "2026-10-11T07:45:12+09:00 (Asia/Tokyo)"


async def test_alias_is_labelled_with_requested_key(tool) -> None:
    out = await tool.execute(zone="US/Pacific")
    assert out.splitlines()[0].endswith("(US/Pacific)")
    assert "Operator's time zone:" in out


@pytest.mark.parametrize("bad", ["Mars/Olympus_Mons", "localtime", "../etc/passwd"])
async def test_unknown_zone_raises(tool, bad) -> None:
    with pytest.raises(ValueError) as e:
        await tool.execute(zone=bad)
    assert str(e.value) == (
        f"Unknown time zone '{bad}'. Use an IANA name such as Asia/Tokyo or Europe/Paris."
    )


async def test_echo_is_truncated_and_non_string_is_invalid(tool) -> None:
    with pytest.raises(ValueError) as e:
        await tool.execute(zone="x" * 200)
    assert f"'{'x' * 64}'" in str(e.value) and "x" * 65 not in str(e.value)
    with pytest.raises(ValueError) as e2:
        await tool.execute(zone=5)  # type: ignore[arg-type]
    assert "'<invalid>'" in str(e2.value)


async def test_unnamed_system_zone_label(frozen_clock) -> None:
    async def src():
        return tz.EffectiveZone(None, timezone.utc)

    out = await CurrentTimeTool(zone_source=src).execute()
    assert out.splitlines()[0] == "2026-10-10T22:45:12+00:00 (system time zone, UTC+00:00)"


async def test_seams_are_looked_up_at_call_time(isolated_db, frozen_clock, monkeypatch) -> None:
    """No injected seams: the real loader reads the system zone via the module seams."""
    out = await CurrentTimeTool().execute()
    assert out.splitlines()[0] == "2026-10-10T15:45:12-07:00 (America/Los_Angeles)"
    monkeypatch.setattr(tz, "detect_system_zone", lambda: "Asia/Kolkata")
    out2 = await CurrentTimeTool().execute()
    assert out2.splitlines()[0].endswith("(Asia/Kolkata)")


async def test_value_error_becomes_error_result_through_the_loop(tool) -> None:
    reg = ToolRegistry()
    reg.register(tool)
    call = ToolCall(id="c1", name="current_time", arguments={"zone": "Mars/X"})
    llm = FakeLLM([Message.assistant("", tool_calls=[call]), Message.assistant("done")])
    agent = Agent(llm=llm, tools=reg, system_prompt="sys")
    out = [m async for m in agent.step("what time")]
    results = [m.tool_result for m in out if m.role == Role.TOOL and m.tool_result]
    assert results[0].is_error
    assert "Unknown time zone 'Mars/X'" in results[0].content
