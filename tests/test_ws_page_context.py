"""The page context over the chat WebSocket (M36 F3 L4, AC5).

Drives the real ``websocket_endpoint`` against a fake socket, on the harness of
``tests/test_ws_start_session.py`` (reused, not copied). The fake GleepGlorp agent takes the
``page`` keyword like ``Agent.step``; every other agent is the harness's ``_FakeAgent``,
whose ``step`` takes no such keyword (so a call that passes one fails the turn).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import pytest

from tests.test_ws_start_session import (
    Do,
    FakeWebSocket,
    Wait,
    WaitFrame,
    _FakeAgent,
    _FakeFactory,
    _gleepglorp,
    _precreate,
    _Recorder,
    _repo,
    _reset_state,
    _row_ids,
    _run,
    _sid,
    _start,
)
from the_one.agent._context import current_turn
from the_one.db.codec import decode_messages
from the_one.interfaces.web import app as app_module
from the_one.llm.base import Message, Role, content_to_text

PAGE = {"destination": "library", "section": "mcp", "create": True}
# What the server builds for PAGE (a create page): the label plus its route.
LINE = "Library › MCP servers › New MCP server (#library/mcp/~new)"


class _PageAgent(_FakeAgent):
    """A GleepGlorp stand-in whose step takes ``page=`` like ``Agent.step``."""

    async def step(
        self,
        user_input: Any,
        on_chunk: Any = None,  # noqa: ARG002
        on_usage: Any = None,  # noqa: ARG002
        page: dict | None = None,
    ) -> AsyncIterator[Message]:
        text = content_to_text(user_input)
        ctx = current_turn.get()
        self._recorder.steps.append((self._name, text))
        self._recorder.pages.append(page)
        self._recorder.turn_pages.append(ctx.page if ctx is not None else "no-context")
        msg = Message.user(text)
        if page is not None:
            msg.page = page
        self.messages.append(msg)
        reply = Message(role=Role.ASSISTANT, content=f"reply to {text}")
        self.messages.append(reply)
        yield reply


class _PageFactory(_FakeFactory):
    async def create(self, name: str) -> _FakeAgent:
        agent = await super().create(name)
        if name == "GleepGlorp":
            paged = _PageAgent(self._recorder, name)
            paged.messages = agent.messages
            return paged
        return agent


@pytest.fixture(autouse=True)
async def recorder(isolated_db, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Recorder]:  # noqa: ARG001
    """The start-session harness's recorder fixture, with the page-aware factory."""
    rec = _Recorder()
    rec.pages = []  # type: ignore[attr-defined]
    rec.turn_pages = []  # type: ignore[attr-defined]
    factory = _PageFactory(rec)
    monkeypatch.setattr(app_module, "_get_factory", lambda: factory)
    _reset_state()
    yield rec
    for t in list(app_module._inflight_tasks):
        t.cancel()
    if app_module._inflight_tasks:
        await asyncio.gather(*list(app_module._inflight_tasks), return_exceptions=True)
    _reset_state()


async def _stored_pages(sid: str) -> list[dict | None]:
    row = await (await _repo()).get(sid)
    return [m.page for m in decode_messages(row.messages) if m.role == Role.USER]


class TestGleepGlorpCarriesThePage:
    async def test_start_session_stores_and_sends_the_line_to_the_sender_only(
        self, recorder: _Recorder
    ) -> None:
        sid = _sid(300)
        await _gleepglorp()
        ws = FakeWebSocket(
            [_start(sid, "what is this?", agent="GleepGlorp", page=PAGE), WaitFrame("done")]
        )
        await _run(ws)
        assert recorder.pages == [{"line": LINE}]  # type: ignore[attr-defined]
        turn = recorder.turn_pages[0]  # type: ignore[attr-defined]
        assert turn["line"] == LINE and turn["descriptor"] == PAGE
        assert [f["line"] for f in ws.frames("page_line")] == [LINE]
        assert ws.frames("page_line")[0]["session_id"] == sid
        assert ws.frames("user") == []
        assert await _stored_pages(sid) == [{"line": LINE}]
        assert "[Page:" not in (await (await _repo()).get(sid)).title

    async def test_message_stores_the_page_and_the_other_subscriber_sees_it(
        self, recorder: _Recorder
    ) -> None:
        sid = _sid(301)
        await _gleepglorp()
        await _precreate(sid, "GleepGlorp")
        joined = asyncio.Event()
        other = FakeWebSocket(
            [{"action": "join", "session_id": sid}, Do(joined.set), WaitFrame("done")]
        )
        sender = FakeWebSocket(
            [
                Wait(joined),
                {"action": "join", "session_id": sid},
                {"action": "message", "message": "hello", "page": PAGE},
                WaitFrame("done"),
            ]
        )
        await _run(other, sender)
        users = other.frames("user")
        assert [u["page"] for u in users] == [{"line": LINE}]
        assert users[0]["content"] == "hello"
        assert [f["line"] for f in sender.frames("page_line")] == [LINE]
        assert sender.frames("user") == []
        assert await _stored_pages(sid) == [{"line": LINE}]
        assert recorder.pages == [{"line": LINE}]  # type: ignore[attr-defined]

    async def test_a_value_fault_keeps_the_message_and_drops_the_page(
        self, recorder: _Recorder, caplog: pytest.LogCaptureFixture
    ) -> None:
        sid = _sid(302)
        await _gleepglorp()
        bad = {"destination": "library", "section": "nowhere"}
        with caplog.at_level(logging.WARNING, logger=app_module.logger.name):
            ws = FakeWebSocket([_start(sid, "hi", agent="GleepGlorp", page=bad), WaitFrame("done")])
            await _run(ws)
        assert recorder.steps == [("GleepGlorp", "hi")]
        assert recorder.pages == [None]  # type: ignore[attr-defined]
        assert ws.frames("page_line") == []
        assert await _stored_pages(sid) == [None]
        warnings = [r for r in caplog.records if "Dropped page context" in r.getMessage()]
        assert len(warnings) == 1

    async def test_at_the_existing_site_the_page_follows_the_restored_sessions_agent(
        self, recorder: _Recorder
    ) -> None:
        sid = _sid(303)
        await _gleepglorp()
        await _precreate(sid, "GleepGlorp")
        # The start names an ordinary agent, but the stored session is GleepGlorp's.
        ws = FakeWebSocket([_start(sid, "hi", agent="alpha", page=PAGE), WaitFrame("done")])
        await _run(ws)
        assert recorder.pages == [{"line": LINE}]  # type: ignore[attr-defined]
        assert [f["line"] for f in ws.frames("page_line")] == [LINE]

    async def test_at_the_existing_site_an_ordinary_session_drops_the_page(
        self, recorder: _Recorder
    ) -> None:
        sid = _sid(304)
        await _gleepglorp()
        await _precreate(sid, "alpha")
        ws = FakeWebSocket([_start(sid, "hi", agent="GleepGlorp", page=PAGE), WaitFrame("done")])
        await _run(ws)
        assert recorder.steps == [("alpha", "hi")]
        assert ws.frames("page_line") == []


class TestEveryoneElseNeverSeesAPage:
    async def test_a_valid_page_on_an_ordinary_agent_is_dropped(self, recorder: _Recorder) -> None:
        sid = _sid(310)
        ws = FakeWebSocket([_start(sid, "hi", agent="alpha", page=PAGE), WaitFrame("done")])
        await _run(ws)
        # The harness agent's `step` takes no `page` keyword: a call that passed one fails.
        assert recorder.steps == [("alpha", "hi")]
        assert ws.frames("page_line") == []
        assert ws.frames("system") == []
        assert await _stored_pages(sid) == [None]

    async def test_a_message_without_a_page_never_passes_the_keyword(
        self, recorder: _Recorder
    ) -> None:
        sid = _sid(311)
        await _gleepglorp()
        ws = FakeWebSocket([_start(sid, "hi", agent="GleepGlorp"), WaitFrame("done")])
        await _run(ws)
        assert recorder.pages == [None]  # type: ignore[attr-defined]
        assert recorder.turn_pages == [None]  # type: ignore[attr-defined]
        assert ws.frames("page_line") == []

    @pytest.mark.parametrize(
        "turn_info",
        [
            {"routine": {"id": "r1", "name": "Daily", "untrusted_sources": []}},
            {"proposal": {"id": 1, "event": "approved"}},
        ],
    )
    async def test_routine_and_proposal_turns_have_no_page(
        self, recorder: _Recorder, turn_info: dict
    ) -> None:
        await _gleepglorp()
        session = await app_module._create_session(agent_name="GleepGlorp")
        await app_module._process_and_broadcast(
            session, "go", source="routine", turn_info=dict(turn_info)
        )
        assert recorder.pages == [None]  # type: ignore[attr-defined]
        assert recorder.turn_pages == [None]  # type: ignore[attr-defined]


class TestAMalformedPageRefusesTheMessage:
    BAD = [
        "text",
        {"destination": "library", "extra": 1},
        {"destination": "library", "item": 5},
        {"destination": "library", "section": "mcp", "item": "x" * 300},
    ]

    @pytest.mark.parametrize("bad", BAD)
    @pytest.mark.parametrize("agent", ["GleepGlorp", "alpha"])
    async def test_start_session_is_refused_and_creates_nothing(
        self, recorder: _Recorder, agent: str, bad: Any
    ) -> None:
        sid = _sid(320)
        await _gleepglorp()
        ws = FakeWebSocket([_start(sid, "hi", agent=agent, page=bad), {"action": "list_sessions"}])
        await _run(ws)
        assert [f["error"] for f in ws.frames("start_failed")] == ["Malformed page context."]
        assert recorder.steps == [] and recorder.creates == []
        assert await _row_ids() == set()

    @pytest.mark.parametrize("bad", BAD)
    async def test_a_message_is_refused_with_one_system_frame(
        self, recorder: _Recorder, bad: Any
    ) -> None:
        ws = FakeWebSocket(
            [
                {"action": "message", "message": "hi", "page": bad},
                {"action": "list_sessions"},
            ]
        )
        await _run(ws)
        assert [f["content"] for f in ws.frames("system")] == ["Malformed page context."]
        assert recorder.steps == [] and recorder.creates == []
        assert app_module._sessions == {} and await _row_ids() == set()

    async def test_reset_with_a_malformed_page_is_refused(self, recorder: _Recorder) -> None:
        sid = _sid(321)
        await _precreate(sid, "alpha")
        ws = FakeWebSocket(
            [
                {"action": "join", "session_id": sid},
                {"action": "message", "message": "/reset", "page": {"bogus": 1}},
            ]
        )
        await _run(ws)
        assert [f["content"] for f in ws.frames("system")] == ["Malformed page context."]

    async def test_reset_with_a_valid_page_ignores_the_page(self, recorder: _Recorder) -> None:
        sid = _sid(322)
        await _precreate(sid, "alpha")
        ws = FakeWebSocket(
            [
                {"action": "join", "session_id": sid},
                {"action": "message", "message": "/reset", "page": PAGE},
            ]
        )
        await _run(ws)
        assert [f["content"] for f in ws.frames("system")] == ["Context cleared."]
        assert ws.frames("page_line") == []

    async def test_an_empty_message_with_a_malformed_page_stays_empty(
        self, recorder: _Recorder
    ) -> None:
        ws = FakeWebSocket(
            [
                {"action": "message", "message": "", "page": {"bogus": 1}},
                {"action": "list_sessions"},
            ]
        )
        await _run(ws)
        assert ws.frames("system") == []
        assert ws.frames("start_failed") == []
