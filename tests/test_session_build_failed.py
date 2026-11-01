"""``build_failed``: any agent-build failure degrades a session instead of dropping it
(sortie 07 leg 2, DD7). The WebSocket ``join`` and ``start_session`` paths, the
``POST /api/chat`` code and the cache are covered here; the restore unit tests live in
``tests/test_session_lifecycle.py``, the routine and connector halves in
``tests/test_routines_runner.py`` and ``tests/test_inbound_session_updated.py``."""

from __future__ import annotations

import json
from types import SimpleNamespace

from tests import test_ws_start_session as _ws
from tests.test_ws_start_session import (
    Do,
    FakeWebSocket,
    WaitFrame,
    _drain_turns,
    _precreate,
    _run,
    _sid,
    _start,
)
from the_one.interfaces.web import app as app_module

# The autouse fixture of the WebSocket start tests (fake factory, isolated DB), reused as is.
recorder = _ws.recorder

SECRET_TEXT = "kaboom-secret-detail"


async def test_join_of_an_existing_session_degrades_and_keeps_the_socket(recorder, caplog):
    sid = _sid(70)
    caplog.set_level("ERROR", logger="the_one.interfaces.web.app")
    ws = FakeWebSocket(
        [
            _start(sid, "hi"),
            WaitFrame("done"),
            Do(_drain_turns),
            Do(lambda: setattr(recorder, "fail_create", RuntimeError(SECRET_TEXT))),
            {"action": "join", "session_id": sid},
            {"action": "list_sessions"},
        ]
    )
    await _run(ws)

    degraded = ws.frames("session_joined")[-1]
    assert degraded["status"] == "build_failed"
    assert degraded["reason"] == app_module.BUILD_FAILED_REASON
    texts = [e.get("content") for e in degraded["history"]]
    assert any("hi" in str(t) for t in texts) and any("reply to hi" in str(t) for t in texts)
    # The socket stays open: the next action is answered.
    assert ws.types()[-1] == "session_list"
    assert sid not in app_module._sessions
    # The exception text goes to the log only, once, with the agent name.
    assert SECRET_TEXT not in json.dumps(ws.sent)
    records = [r for r in caplog.records if "build_failed" in r.getMessage()]
    assert len(records) == 1
    assert "'alpha'" in records[0].getMessage()
    assert records[0].exc_info is not None


async def test_start_session_with_an_existing_id_gets_the_degraded_frame(recorder):
    sid = _sid(71)
    await _precreate(sid)
    recorder.fail_create = RuntimeError(SECRET_TEXT)
    ws = FakeWebSocket([_start(sid, "again"), {"action": "list_sessions"}])
    await _run(ws)

    frame = ws.frames("session_joined")[-1]
    assert frame["status"] == "build_failed"
    assert frame["reason"] == app_module.BUILD_FAILED_REASON
    assert ws.frames("start_failed") == []
    assert ws.types()[-1] == "session_list"
    assert SECRET_TEXT not in json.dumps(ws.sent)
    assert sid not in app_module._sessions
    assert recorder.steps == []


async def test_a_brand_new_chat_keeps_start_failed(recorder):
    """DD7: only an existing session degrades; a new chat's failure is still `start_failed`."""
    sid = _sid(72)
    recorder.fail_create = RuntimeError("no provider")
    ws = FakeWebSocket([_start(sid)])
    await _run(ws)
    assert ws.frames("start_failed")


async def test_post_api_chat_returns_the_code_only(recorder):
    sid = _sid(73)
    await _precreate(sid)
    recorder.fail_create = RuntimeError(SECRET_TEXT)

    async def body():
        return {"message": "hi", "session_id": sid}

    result = await app_module.chat(SimpleNamespace(json=body))
    assert result == {"error": "session_build_failed"}
    assert sid not in app_module._sessions
