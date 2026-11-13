"""Squawk 0353: a message history never keeps an unanswered tool call."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import the_one.interfaces.web.app as app_module
from tests._schema_template import connect_template_db
from tests.conftest import FakeLLM
from the_one.agent.core import Agent
from the_one.agent.history_repair import INTERRUPTED_TOOL_RESULT, repair_unanswered_tool_calls
from the_one.db.codec import encode_messages
from the_one.db.models import ChatSession as ChatSessionModel
from the_one.db.repositories import ChatSessionRepository
from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.base import Message, Role, ToolCall, ToolResult
from the_one.sessions import clear_for_test as _clear_session_registry
from the_one.tools.base import ToolRegistry


def _call(i: str) -> ToolCall:
    return ToolCall(id=i, name="shell", arguments={})


def _result(i: str, **kw) -> Message:
    return Message.tool(ToolResult(tool_call_id=i, content="ok", **kw))


def _ids(messages: list[Message]) -> list[tuple[str, str]]:
    out = []
    for m in messages:
        if m.role == Role.TOOL:
            out.append(("tool", m.tool_result.tool_call_id))
        else:
            out.append((m.role.value, m.content))
    return out


def test_single_unanswered_call_gets_error_result():
    msgs = [Message.user("go"), Message.assistant("", tool_calls=[_call("a")])]
    assert repair_unanswered_tool_calls(msgs) == 1
    assert [m.role for m in msgs] == [Role.USER, Role.ASSISTANT, Role.TOOL]
    tr = msgs[2].tool_result
    assert tr.tool_call_id == "a"
    assert tr.is_error is True
    assert tr.content == INTERRUPTED_TOOL_RESULT


def test_second_of_two_calls_unanswered_goes_after_existing_result():
    msgs = [
        Message.user("go"),
        Message.assistant("", tool_calls=[_call("a"), _call("b")]),
        _result("a"),
        Message.assistant("_[interrupted]_"),
    ]
    assert repair_unanswered_tool_calls(msgs) == 1
    assert _ids(msgs) == [
        ("user", "go"),
        ("assistant", ""),
        ("tool", "a"),
        ("tool", "b"),
        ("assistant", "_[interrupted]_"),
    ]


def test_missing_results_come_in_call_order():
    msgs = [
        Message.assistant("", tool_calls=[_call("a"), _call("b"), _call("c")]),
        _result("b"),
        Message.user("next"),
    ]
    repair_unanswered_tool_calls(msgs)
    assert [i for k, i in _ids(msgs) if k == "tool"] == ["b", "a", "c"]
    assert msgs[-1].role == Role.USER


def test_valid_history_is_unchanged_and_repair_is_idempotent():
    msgs = [
        Message.user("go"),
        Message.assistant("", tool_calls=[_call("a")]),
        _result("a"),
        Message.assistant("done"),
    ]
    before = list(msgs)
    assert repair_unanswered_tool_calls(msgs) == 0
    assert msgs == before

    broken = [Message.assistant("", tool_calls=[_call("a")]), Message.user("x")]
    assert repair_unanswered_tool_calls(broken) == 1
    snapshot = list(broken)
    assert repair_unanswered_tool_calls(broken) == 0
    assert broken == snapshot


def test_auth_placeholder_counts_as_answered():
    placeholder = _result("a", metadata={"is_auth_required": True})
    msgs = [Message.assistant("", tool_calls=[_call("a"), _call("b")]), placeholder]
    # The paused call "a" keeps its placeholder and is not duplicated; only the
    # later deferred call "b" has no result (the caller skips repair while a
    # pause is live, so resume_after_auth answers it instead).
    repair_unanswered_tool_calls(msgs)
    assert [i for k, i in _ids(msgs) if k == "tool"] == ["a", "b"]
    assert msgs[1] is placeholder


# ── stored broken history heals on resync ─────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
async def repo(tmp_path):
    conn = await connect_template_db(tmp_path / "t.db")
    yield ChatSessionRepository(conn)
    await conn.close()


@pytest.fixture
def _patched_repo(repo):
    async def _repo():
        return repo

    with patch.object(app_module, "_chat_repo", _repo):
        yield
    _clear_session_registry()


async def test_stored_broken_history_heals_on_resync_and_builds_valid_anthropic_request(
    repo, _patched_repo
):
    broken = [
        Message.system("sys"),
        Message.user("search"),
        Message.assistant("Let me look", tool_calls=[_call("toolu_1")]),
        Message.assistant("Let me look\n\n_[interrupted]_"),
        Message.user("hello again"),
    ]
    row = ChatSessionModel(
        id="s1",
        agent_name=None,
        title="t",
        messages="[]",
        created_at=_now(),
        updated_at=_now(),
    )
    await repo.create(row)
    session = app_module.Session(
        id="s1",
        agent=Agent(llm=FakeLLM([]), tools=ToolRegistry(), system_prompt="sys"),
        created=_now(),
        db_fingerprint=app_module._fingerprint(row.messages, row.title),
    )
    await repo.update(row.model_copy(update={"messages": encode_messages(broken)}))

    await app_module._resync_session_from_db(session)

    msgs = session.agent.messages
    assert [m.role for m in msgs] == [
        Role.SYSTEM,
        Role.USER,
        Role.ASSISTANT,
        Role.TOOL,
        Role.ASSISTANT,
        Role.USER,
    ]
    assert msgs[3].tool_result.tool_call_id == "toolu_1"
    assert msgs[3].tool_result.is_error is True

    provider = AnthropicProvider(model="claude-sonnet-4-6", api_key="test-key")
    api = provider._build_kwargs(msgs, None, 0.0, 100)["messages"]
    for i, m in enumerate(api):
        uses = [
            b["id"] for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        if not uses:
            continue
        nxt = {
            b["tool_use_id"]
            for b in api[i + 1]["content"]
            if isinstance(b, dict) and b.get("type") == "tool_result"
        }
        assert set(uses) <= nxt
