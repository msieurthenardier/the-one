"""Step-limit frame on the web turn paths and the REST result (M31 F6 leg 06, DD8)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from conftest import FakeLLM, StubTool

from tests.test_agent import AuthRequiredStubTool, _install_auth_required_executor
from the_one.agent.core import Agent
from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import Session, _process_and_broadcast, _resume_paused_session
from the_one.llm.base import Message, ToolCall
from the_one.tools.base import ToolRegistry


def _call(i: int, name: str = "tool_a") -> Message:
    return Message.assistant("", tool_calls=[ToolCall(id=f"c{i}", name=name, arguments={})])


def _agent(responses: list[Message], max_iterations: int, *tools: Any) -> Agent:
    reg = ToolRegistry()
    for t in tools or (StubTool("tool_a"),):
        reg.register(t)
    return Agent(
        llm=FakeLLM(responses), tools=reg, system_prompt="t", max_iterations=max_iterations
    )


@pytest.fixture
def sink(monkeypatch) -> list[tuple[str, dict[str, Any]]]:
    """Capture broadcasts and saves in one ordered list."""
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))

    async def save(session):  # noqa: ARG001
        events.append(("save", {}))

    async def send(session, payload, exclude=None):  # noqa: ARG001
        events.append(("send", payload))

    monkeypatch.setattr(web_app, "_save_session_to_db", save)
    monkeypatch.setattr(web_app, "_send_to_session", send)
    return events


def _types(events: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [p["type"] if k == "send" else "<save>" for k, p in events]


def _session(agent: Agent) -> Session:
    return Session(id="sl-1", agent=agent, created="2026-10-27T00:00:00+00:00")


async def test_step_path_sends_step_limit_after_save_before_done(sink) -> None:
    session = _session(_agent([_call(1), _call(2)], 2))
    info: dict[str, Any] = {}
    await _process_and_broadcast(session, "go", turn_info=info)
    types = _types(sink)
    assert types[-2:] == ["step_limit", "done"]
    assert types.index("<save>") < types.index("step_limit")
    frame = [p for k, p in sink if k == "send" and p["type"] == "step_limit"]
    assert frame == [{"type": "step_limit", "steps": 2}]
    assert info == {"step_limit": True}


async def test_step_limit_is_broadcast_only(sink) -> None:
    session = _session(_agent([_call(1), _call(2)], 2))
    await _process_and_broadcast(session, "go")
    assert all(e.get("type") != "step_limit" for e in session.history)
    # No stored message carries the notice either.
    assert all("step limit" not in (m.content or "").lower() for m in session.agent.messages)


async def test_normal_turn_sends_no_step_limit(sink) -> None:
    session = _session(_agent([Message.assistant("hi")], 2))
    info: dict[str, Any] = {}
    await _process_and_broadcast(session, "go", turn_info=info)
    assert "step_limit" not in _types(sink)
    assert _types(sink)[-1] == "done"
    assert info == {"step_limit": False}


async def test_agent_error_sends_no_step_limit(sink) -> None:
    agent = _agent([], 2)

    async def boom(*a, **k):
        raise RuntimeError("provider down")
        yield  # pragma: no cover

    agent.step = boom  # type: ignore[method-assign]
    agent.stopped_at_step_limit = True  # stale value must not leak
    session = _session(agent)
    await _process_and_broadcast(session, "go")
    assert "step_limit" not in _types(sink)


async def test_resume_with_zero_budget_sends_step_limit_before_done(sink) -> None:
    auth = AuthRequiredStubTool(name="tool_b", auth_required_calls=1)
    agent = _agent([_call(1, "tool_b")], 1, auth)
    _install_auth_required_executor(agent, {"tool_b": auth})
    session = _session(agent)
    await _process_and_broadcast(session, "go")
    assert "done" not in _types(sink)
    sink.clear()
    await _resume_paused_session(session)
    types = _types(sink)
    assert types.index("step_limit") == types.index("done") - 1
    frame = [p for k, p in sink if k == "send" and p["type"] == "step_limit"]
    assert frame == [{"type": "step_limit", "steps": 1}]


async def test_re_paused_resume_sends_no_step_limit(sink) -> None:
    auth = AuthRequiredStubTool(name="tool_b", auth_required_calls=2)
    agent = _agent([_call(1, "tool_b")], 1, auth)
    _install_auth_required_executor(agent, {"tool_b": auth})
    session = _session(agent)
    await _process_and_broadcast(session, "go")
    sink.clear()
    await _resume_paused_session(session)
    assert "step_limit" not in _types(sink)
    assert "done" not in _types(sink)


class _Req:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._p = payload

    async def json(self) -> dict[str, Any]:
        return self._p


async def test_rest_chat_result_carries_step_limit_key(sink, monkeypatch) -> None:
    session = _session(_agent([_call(1), _call(2)], 2))
    monkeypatch.setattr(web_app, "_create_session", AsyncMock(return_value=session))
    result = await web_app.chat(_Req({"message": "go"}))  # type: ignore[arg-type]
    assert result["step_limit"] is True
    assert result["session_id"] == "sl-1"


async def test_rest_chat_result_has_no_key_otherwise(sink, monkeypatch) -> None:
    session = _session(_agent([Message.assistant("hi")], 2))
    monkeypatch.setattr(web_app, "_create_session", AsyncMock(return_value=session))
    result = await web_app.chat(_Req({"message": "go"}))  # type: ignore[arg-type]
    assert "step_limit" not in result
