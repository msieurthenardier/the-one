"""The Chats-list change signal, list_summaries, the socket registry and the
coalescing `sessions_changed` push (sortie 05 leg 2)."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import the_one.interfaces.web.app as app_module
from tests._schema_template import connect_template_db
from the_one.db import _session_changes
from the_one.db.models import ChatSession as ChatSessionModel
from the_one.db.repositories import ChatSessionRepository
from the_one.sessions import _broadcast


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(sid="s1", agent="a", messages="[]", title="T", updated=None) -> ChatSessionModel:
    return ChatSessionModel(
        id=sid,
        agent_name=agent,
        title=title,
        messages=messages,
        created_at=_now(),
        updated_at=updated or _now(),
    )


@pytest.fixture(autouse=True)
def _clean():
    _session_changes.clear_for_test()
    _broadcast.clear_subscribers_for_test()
    yield
    _session_changes.clear_for_test()
    _broadcast.clear_subscribers_for_test()


@pytest.fixture
async def repo(tmp_path):
    conn = await connect_template_db(tmp_path / "t.db")
    yield ChatSessionRepository(conn)
    await conn.close()


class Recorder:
    """A listener that counts calls and (optionally) reads the row back."""

    def __init__(self, repo=None, sid=None):
        self.calls = 0
        self.repo = repo
        self.sid = sid
        self.seen: list = []
        self._loop = None

    def __call__(self):
        self.calls += 1


# ── the signal module ───────────────────────────────────────────────────────


def test_notify_with_no_listener_is_a_noop():
    _session_changes.notify_sessions_changed()


def test_listener_exceptions_are_contained_and_others_still_run():
    ran = []

    def bad():
        raise RuntimeError("boom")

    _session_changes.add_listener(bad)
    _session_changes.add_listener(lambda: ran.append(1))
    _session_changes.notify_sessions_changed()
    assert ran == [1]


def test_remove_listener_stops_calls_and_tolerates_absence():
    rec = Recorder()
    _session_changes.add_listener(rec)
    _session_changes.notify_sessions_changed()
    _session_changes.remove_listener(rec)
    _session_changes.remove_listener(rec)
    _session_changes.notify_sessions_changed()
    assert rec.calls == 1


# ── repository notifications ────────────────────────────────────────────────


async def test_create_notifies_once_after_commit(repo):
    seen: list[bool] = []

    def listener():
        # Called after the transaction block exited: the row is committed and
        # no transaction is open on the connection.
        seen.append(not repo.conn.in_transaction)

    _session_changes.add_listener(listener)
    await repo.create(_row())
    assert seen == [True]
    assert (await repo.get("s1")).id == "s1"


async def test_each_write_method_notifies_exactly_once(repo):
    await repo.create(_row("s1"))
    await repo.create(_row("s2", agent="b", updated="2000-01-01T00:00:00+00:00"))
    rec = Recorder()
    _session_changes.add_listener(rec)

    await repo.update(_row("s1", title="new"))
    assert rec.calls == 1
    await repo.purge_messages("s1")
    assert rec.calls == 2
    await repo.update_last_inbound("s1", _now())
    assert rec.calls == 3
    await repo.delete("s1")
    assert rec.calls == 4
    assert await repo.delete_all_for_agent("b") == 1
    assert rec.calls == 5


async def test_delete_older_than_notifies_only_when_it_deleted(repo):
    await repo.create(_row("old", updated="2000-01-01T00:00:00+00:00"))
    rec = Recorder()
    _session_changes.add_listener(rec)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert await repo.delete_older_than("nobody", cutoff) == []
    assert rec.calls == 0
    assert await repo.delete_older_than("a", cutoff) == ["old"]
    assert rec.calls == 1


async def test_delete_all_for_agent_with_nothing_does_not_notify(repo):
    rec = Recorder()
    _session_changes.add_listener(rec)
    assert await repo.delete_all_for_agent("nobody") == 0
    assert rec.calls == 0


async def test_metadata_methods_do_not_notify(repo):
    await repo.create(_row("s1"))
    rec = Recorder()
    _session_changes.add_listener(rec)
    await repo.append_to_session_metadata("s1", "k", {"v": 1})
    await repo.set_session_metadata_key("s1", "j", "v")
    assert rec.calls == 0


async def test_failing_calls_do_not_notify(repo):
    rec = Recorder()
    _session_changes.add_listener(rec)
    for call in (
        repo.update(_row("missing")),
        repo.delete("missing"),
        repo.purge_messages("missing"),
        repo.update_last_inbound("missing", _now()),
    ):
        with pytest.raises(KeyError):
            await call
    assert rec.calls == 0


async def test_agent_rename_notifies(tmp_path):
    from the_one.agent.config import AgentConfig
    from the_one.db.repositories import SQLiteAgentStore

    conn = await connect_template_db(tmp_path / "r.db")
    try:
        store = SQLiteAgentStore(conn)
        await store.save(AgentConfig(name="old-name", description="d"))
        rec = Recorder()
        _session_changes.add_listener(rec)
        await store.rename("old-name", "new-name")
        assert rec.calls == 1
    finally:
        await conn.close()


# ── list_summaries ──────────────────────────────────────────────────────────


async def test_list_summaries_matches_list_without_reading_messages(repo):
    await repo.create(_row("s1", messages="SENTINEL-HISTORY", updated="2001-01-01T00:00:00+00:00"))
    await repo.create(_row("s2", updated="2002-01-01T00:00:00+00:00"))
    await repo.create(_row("s3", updated="2003-01-01T00:00:00+00:00"))
    full = await repo.list()
    summaries = await repo.list_summaries()
    assert [s.id for s in summaries] == [s.id for s in full] == ["s3", "s2", "s1"]
    assert all(s.messages == "[]" for s in summaries)
    assert all(s.session_metadata is None for s in summaries)
    assert [app_module._session_to_list_payload(s) for s in summaries] == [
        app_module._session_to_list_payload(s) for s in full
    ]


# ── socket registry ─────────────────────────────────────────────────────────


class FakeWS:
    def __init__(self, fail=False):
        self.sent: list = []
        self.texts: list = []
        self.fail = fail

    async def send_json(self, payload):
        if self.fail:
            raise RuntimeError("closed")
        self.sent.append(payload)

    async def send_text(self, text):
        if self.fail:
            raise RuntimeError("closed")
        self.texts.append(text)
        self.sent.append(json.loads(text))


async def test_broadcast_to_all_encodes_once_for_every_socket(monkeypatch):
    sockets = [FakeWS(), FakeWS(), FakeWS()]
    for ws in sockets:
        _broadcast.add_socket(ws)
    calls = []
    real = json.dumps

    def counting(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(_broadcast.json, "dumps", counting)
    payload = {"type": "sessions_changed", "name": "café", "n": [1, 2]}
    await _broadcast.broadcast_to_all(payload)
    assert len(calls) == 1
    expected = real(payload, separators=(",", ":"), ensure_ascii=False)
    for ws in sockets:
        assert ws.texts == [expected]
    assert len({id(ws.texts[0]) for ws in sockets}) == 1
    for ws in sockets:
        _broadcast.remove_socket(ws)


async def test_broadcast_to_all_unencodable_payload_sends_nothing_and_keeps_sockets():
    ws = FakeWS()
    _broadcast.add_socket(ws)
    await _broadcast.broadcast_to_all({"bad": object()})
    assert ws.texts == []
    assert _broadcast.all_sockets() == {ws}
    _broadcast.remove_socket(ws)


async def test_broadcast_to_all_sends_and_drops_dead_sockets():
    good, dead = FakeWS(), FakeWS(fail=True)
    _broadcast.add_socket(good)
    _broadcast.add_socket(dead)
    await _broadcast.broadcast_to_all({"type": "x"})
    assert good.sent == [{"type": "x"}]
    assert _broadcast.all_sockets() == {good}
    _broadcast.remove_socket(good)
    _broadcast.remove_socket(good)
    assert _broadcast.all_sockets() == set()


def test_clear_subscribers_for_test_clears_sockets():
    _broadcast.add_socket(FakeWS())
    _broadcast.clear_subscribers_for_test()
    assert _broadcast.all_sockets() == set()


# ── the coalescing listener ─────────────────────────────────────────────────


class CountingRepo:
    def __init__(self, rows=None, fail=False, on_read=None):
        self.reads = 0
        self.rows = rows or []
        self.fail = fail
        self.on_read = on_read

    async def list_summaries(self):
        self.reads += 1
        if self.on_read:
            await self.on_read()
        if self.fail:
            raise RuntimeError("db down")
        return self.rows


def _listener(repo, window=0.05):
    async def _repo():
        return repo

    patcher = patch.object(app_module, "_chat_repo", _repo)
    patcher.start()
    listener = app_module._SessionsPushListener(asyncio.get_running_loop())
    listener.WINDOW = window
    return listener, patcher


async def test_signals_inside_the_window_fold_into_one_push():
    repo = CountingRepo([_row("s1")])
    ws1, ws2 = FakeWS(), FakeWS()
    _broadcast.add_socket(ws1)
    _broadcast.add_socket(ws2)
    listener, patcher = _listener(repo)
    try:
        for _ in range(5):
            listener.notify()
        await asyncio.sleep(0.3)
        assert repo.reads == 1
        for ws in (ws1, ws2):
            assert len(ws.sent) == 1
            assert ws.sent[0]["type"] == "sessions_changed"
            assert [s["id"] for s in ws.sent[0]["sessions"]] == ["s1"]
    finally:
        await listener.close()
        patcher.stop()


async def test_a_signal_during_the_read_arms_a_second_push():
    holder: dict = {}

    async def on_read():
        if repo.reads == 1:
            holder["l"].notify()

    repo = CountingRepo([_row("s1")], on_read=on_read)
    ws = FakeWS()
    _broadcast.add_socket(ws)
    listener, patcher = _listener(repo)
    holder["l"] = listener
    try:
        listener.notify()
        await asyncio.sleep(0.4)
        assert repo.reads == 2
        assert len(ws.sent) == 2
    finally:
        await listener.close()
        patcher.stop()


async def test_no_sockets_means_no_read():
    repo = CountingRepo()
    listener, patcher = _listener(repo)
    try:
        listener.notify()
        await asyncio.sleep(0.2)
        assert repo.reads == 0
    finally:
        await listener.close()
        patcher.stop()


async def test_a_failed_read_sends_nothing():
    repo = CountingRepo(fail=True)
    ws = FakeWS()
    _broadcast.add_socket(ws)
    listener, patcher = _listener(repo)
    try:
        listener.notify()
        await asyncio.sleep(0.2)
        assert repo.reads == 1
        assert ws.sent == []
    finally:
        await listener.close()
        patcher.stop()


async def test_a_signal_after_close_pushes_nothing_even_when_queued():
    repo = CountingRepo([_row("s1")])
    ws = FakeWS()
    _broadcast.add_socket(ws)
    listener, patcher = _listener(repo)
    try:
        # A queued schedule callback that runs after close does nothing.
        listener.loop.call_soon(listener._schedule)
        await listener.close()
        await asyncio.sleep(0.2)
        listener.notify()
        await asyncio.sleep(0.2)
        assert repo.reads == 0 and ws.sent == []
    finally:
        patcher.stop()


async def test_close_cancels_a_pending_push():
    repo = CountingRepo([_row("s1")])
    ws = FakeWS()
    _broadcast.add_socket(ws)
    listener, patcher = _listener(repo, window=0.2)
    try:
        listener.notify()
        await asyncio.sleep(0)
        await listener.close()
        await asyncio.sleep(0.4)
        assert repo.reads == 0 and ws.sent == []
    finally:
        patcher.stop()


async def test_removed_listener_is_not_called_by_the_signal():
    repo = CountingRepo([_row("s1")])
    ws = FakeWS()
    _broadcast.add_socket(ws)
    listener, patcher = _listener(repo)
    try:
        _session_changes.add_listener(listener.notify)
        _session_changes.remove_listener(listener.notify)
        _session_changes.notify_sessions_changed()
        await asyncio.sleep(0.2)
        assert repo.reads == 0
    finally:
        await listener.close()
        patcher.stop()


async def test_a_signal_from_another_thread_is_marshalled_to_the_loop():
    repo = CountingRepo([_row("s1")])
    ws = FakeWS()
    _broadcast.add_socket(ws)
    listener, patcher = _listener(repo)
    try:
        t = threading.Thread(target=listener.notify)
        t.start()
        t.join()
        await asyncio.sleep(0.3)
        assert repo.reads == 1 and len(ws.sent) == 1
    finally:
        await listener.close()
        patcher.stop()
