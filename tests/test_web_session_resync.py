"""Turn-start re-sync of a cached web Session against its stored row (sortie 05 leg 1)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

import the_one.interfaces.web.app as app_module
from tests._schema_template import connect_template_db
from tests.conftest import FakeLLM
from the_one.agent.core import Agent
from the_one.db.codec import decode_messages, encode_messages
from the_one.db.models import ChatSession as ChatSessionModel
from the_one.db.repositories import ChatSessionRepository
from the_one.llm.base import Message, Role
from the_one.sessions import clear_for_test as _clear_session_registry
from the_one.tools.base import ToolRegistry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
async def repo(tmp_path):
    conn = await connect_template_db(tmp_path / "t.db")
    yield ChatSessionRepository(conn)
    await conn.close()


@pytest.fixture(autouse=True)
def _patched(repo):
    async def _repo():
        return repo

    with patch.object(app_module, "_chat_repo", _repo):
        yield
    _clear_session_registry()


def _agent(responses=None) -> Agent:
    return Agent(llm=FakeLLM(responses or []), tools=ToolRegistry(), system_prompt="sys")


async def _row(repo, sid="s1", messages="[]", title="New chat") -> ChatSessionModel:
    row = ChatSessionModel(
        id=sid,
        agent_name=None,
        title=title,
        messages=messages,
        created_at=_now(),
        updated_at=_now(),
    )
    await repo.create(row)
    return row


def _session(fp, agent=None, sid="s1") -> app_module.Session:
    return app_module.Session(id=sid, agent=agent or _agent(), created=_now(), db_fingerprint=fp)


def _enc(*texts: str) -> str:
    return encode_messages([Message(role=Role.USER, content=t) for t in texts])


async def test_none_fingerprint_replaces_nothing(repo):
    row = await _row(repo)
    await repo.update(row.model_copy(update={"messages": _enc("other")}))
    s = _session(None)
    await app_module._resync_session_from_db(s)
    assert len(s.agent.messages) == 1


async def test_changed_row_is_resynced_and_save_keeps_it(repo):
    row = await _row(repo)
    s = _session(app_module._fingerprint(row.messages, row.title))
    await repo.update(row.model_copy(update={"messages": _enc("from connector")}))
    await app_module._resync_session_from_db(s)
    assert [m.content for m in s.agent.messages[1:]] == ["from connector"]
    assert s.history
    s.agent.messages.append(Message(role=Role.USER, content="from web"))
    await app_module._save_session_to_db(s)
    stored = decode_messages((await repo.get("s1")).messages)
    assert [m.content for m in stored if m.role != Role.SYSTEM] == ["from connector", "from web"]


async def test_equal_fingerprint_does_nothing(repo):
    row = await _row(repo)
    s = _session(app_module._fingerprint(row.messages, row.title))
    marker = Message(role=Role.USER, content="local only")
    s.agent.messages.append(marker)
    await app_module._resync_session_from_db(s)
    assert s.agent.messages[-1] is marker


async def test_missing_row_no_change(repo):
    s = _session("anything", sid="ghost")
    await app_module._resync_session_from_db(s)
    assert len(s.agent.messages) == 1
    assert s.db_fingerprint == "anything"


async def test_failing_read_does_not_stop_the_turn(repo):
    await _row(repo)
    s = _session("x")
    called = []

    async def boom(_s):
        raise RuntimeError("read failed")

    async def fake_pb(sess, *a, **k):
        called.append(sess.id)

    with (
        patch.object(app_module, "_resync_session_from_db", boom),
        patch.object(app_module, "_process_and_broadcast", fake_pb),
    ):
        await app_module._locked_message_processing(s, "hi", "web", None)
    assert called == ["s1"]


async def test_fingerprint_matches_written_and_read_back(repo):
    await _row(repo)
    s = _session(None)
    s.title = ""
    s.agent.messages.append(Message(role=Role.USER, content="hello"))
    await app_module._save_session_to_db(s)
    row = await repo.get("s1")
    assert s.db_fingerprint == app_module._fingerprint(row.messages, row.title)


async def test_real_locked_turn_keeps_other_writers_messages(repo):
    row = await _row(repo)
    agent = _agent([Message(role=Role.ASSISTANT, content="web reply")])
    s = _session(app_module._fingerprint(row.messages, row.title), agent=agent)
    other = encode_messages(
        [
            Message(role=Role.USER, content="dm in"),
            Message(role=Role.ASSISTANT, content="connector reply"),
        ]
    )
    await repo.update(row.model_copy(update={"messages": other}))
    with patch.object(app_module, "_send_to_session", AsyncMock()):
        await app_module._locked_message_processing(s, "web hello", "web", None)
    texts = [m.content for m in decode_messages((await repo.get("s1")).messages)]
    assert "dm in" in texts and "connector reply" in texts
    assert "web hello" in texts and "web reply" in texts


async def test_cancelled_error_propagates(repo):
    s = _session("x")

    async def cancel(_s):
        raise asyncio.CancelledError

    with patch.object(app_module, "_resync_session_from_db", cancel):
        with pytest.raises(asyncio.CancelledError):
            await app_module._locked_message_processing(s, "hi", "web", None)
