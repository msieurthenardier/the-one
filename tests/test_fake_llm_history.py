"""Squawk 0218: ``FakeLLM`` rejects a history a real provider would reject.

A duplicate ``tool_result`` for one tool call id, and a result with no preceding
call, raise an ``AssertionError`` naming the id; ``strict_history=False`` opts out.
"""

from __future__ import annotations

import pytest
from conftest import FakeLLM

from the_one.llm.base import Message, ToolCall, ToolResult


def _call(cid: str) -> Message:
    return Message.assistant("", tool_calls=[ToolCall(id=cid, name="t", arguments={})])


def _result(cid: str, text: str = "ok") -> Message:
    return Message.tool(ToolResult(tool_call_id=cid, content=text))


async def test_a_paired_history_passes() -> None:
    llm = FakeLLM([Message.assistant("done")])
    history = [Message.user("go"), _call("c1"), _result("c1")]
    assert (await llm.complete(history)).content == "done"


async def test_a_duplicate_tool_result_raises_naming_the_id() -> None:
    llm = FakeLLM([Message.assistant("done")])
    history = [Message.user("go"), _call("c1"), _result("c1", "placeholder"), _result("c1")]
    with pytest.raises(AssertionError, match=r"duplicate tool_result.*'c1'"):
        await llm.complete(history)


async def test_an_orphan_tool_result_raises_naming_the_id() -> None:
    llm = FakeLLM([Message.assistant("done")])
    history = [Message.user("go"), _result("gone")]
    with pytest.raises(AssertionError, match=r"'gone'.*no preceding tool call"):
        await llm.complete(history)


async def test_a_result_before_its_call_is_an_orphan() -> None:
    llm = FakeLLM([Message.assistant("done")])
    with pytest.raises(AssertionError, match="'c1'"):
        await llm.complete([_result("c1"), _call("c1")])


async def test_the_opt_out_accepts_a_malformed_history() -> None:
    llm = FakeLLM([Message.assistant("a"), Message.assistant("b")], strict_history=False)
    dup = [Message.user("go"), _call("c1"), _result("c1"), _result("c1")]
    orphan = [Message.user("go"), _result("gone")]
    assert (await llm.complete(dup)).content == "a"
    assert (await llm.complete(orphan)).content == "b"


async def test_a_rejected_call_is_still_recorded() -> None:
    llm = FakeLLM([Message.assistant("done")])
    with pytest.raises(AssertionError):
        await llm.complete([_result("x")])
    assert len(llm.calls) == 1
