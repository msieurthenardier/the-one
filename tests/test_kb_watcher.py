"""Tests for ``the_one/knowledge/watcher.py`` (Flight 4 M24 F04 Leg 2,
DD-0/DD-1/DD-2/DD-3/DD-4): ``WatchManager``'s dedicated-thread
subscriptions, filter application, settle trigger with hold cap and
suppression, reconcile loop with re-subscribe, ``apply_settings``, the
64-subscription cap, and the accessor pair.

Every test drives the watch-factory seam with ``_QueueFactory`` — a fake
``WatchFactory`` reading a thread-safe ``queue.Queue`` per root, exercising
the same thread hop production uses — except AC-6's real-``watch``
integration test and the two AC-1/AC-12 source-level tests. Small real
settle/hold values (never a fake clock); the only ``time.sleep`` calls live
inside ``_QueueFactory``'s generator (on its own thread), mirroring
``tests/test_kb_manager.py``'s fake-slow-backend precedent. Waits for
something to happen use an ``asyncio.Event``; waits to prove nothing
further happens use a bounded ``asyncio.sleep`` — both patterns the leg
spec calls for explicitly (AC-3, AC-9).
"""

from __future__ import annotations

import asyncio
import errno
import inspect
import os
import queue
import re
import threading
import time
from pathlib import Path

import aiosqlite
import pytest
import watchfiles

from the_one.db.models import KBItem, KnowledgeBase
from the_one.db.repositories import KBItemRepository, KnowledgeBaseRepository
from the_one.db.schema import ensure_schema
from the_one.knowledge import watcher as watcher_mod
from the_one.knowledge.settings import MonitoringSettings
from the_one.knowledge.watcher import (
    WatchManager,
    get_manager,
    set_manager,
)

Change = watchfiles.Change


# ── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_manager_module():
    set_manager(None)
    yield
    set_manager(None)


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "test.db"
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(connection)
    yield connection
    await connection.close()


@pytest.fixture
def kb_repo(conn):
    return KnowledgeBaseRepository(conn)


@pytest.fixture
def item_repo(conn):
    return KBItemRepository(conn)


def _make_conn_factory(conn):
    async def _f():
        return conn

    return _f


async def _make_kb(kb_repo, kb_id: str = "kb1") -> KnowledgeBase:
    kb = KnowledgeBase(id=kb_id, name=kb_id)
    await kb_repo.create(kb)
    return kb


async def _make_folder(item_repo, kb_id: str, root: Path, item_id: str | None = None) -> KBItem:
    item = KBItem(
        id=item_id or f"folder-{kb_id}-{root.name}",
        kb_id=kb_id,
        type="folder",
        path_or_url=str(root),
    )
    await item_repo.create(item)
    return item


class _FakeIndexManager:
    """Records ``request_index`` calls and sets an ``asyncio.Event`` on
    every call so tests can await "a call happened" rather than polling."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.call_event = asyncio.Event()

    def request_index(self, kb_id: str) -> None:
        self.calls.append(kb_id)
        self.call_event.set()

    async def wait_for_call(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self.call_event.wait(), timeout)
        self.call_event.clear()


class _QueueFactory:
    """A ``WatchFactory`` test double: one ``queue.Queue`` per root. An
    item queued is either a ``set[tuple[Change, str]]`` (yielded —
    possibly empty, simulating a timeout yield) or a ``BaseException``
    instance (raised on the ``next()`` that consumes it). The generator
    polls with a short timeout so it honours ``stop_event`` promptly,
    exercising the same thread hop production uses. Records every
    ``(root, ignore_permission_denied)`` call for the two-step-rule ACs.
    """

    def __init__(self) -> None:
        self._queues: dict[Path, queue.Queue] = {}
        self.calls: list[tuple[Path, bool]] = []

    def queue_for(self, root: Path) -> queue.Queue:
        return self._queues.setdefault(root, queue.Queue())

    def __call__(self, root, watch_filter, stop_event, ignore_permission_denied):
        del watch_filter  # AC-2 exercises the filter directly, not via the queue
        self.calls.append((root, ignore_permission_denied))
        q = self.queue_for(root)
        return self._gen(q, stop_event)

    @staticmethod
    def _gen(q: queue.Queue, stop_event: threading.Event):
        while not stop_event.is_set():
            try:
                item = q.get(timeout=0.02)
            except queue.Empty:
                continue
            if isinstance(item, BaseException):
                raise item
            yield set(item)


def _wait_thread_gone(name: str, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(t.name == name for t in threading.enumerate()):
            return
        time.sleep(0.01)
    raise AssertionError(f"thread {name!r} still alive after {timeout}s")


async def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.01) -> None:
    """Poll-until helper reserved for state-word assertions where no event
    exists to await (state is plain attribute access, not queue-backed)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError("condition not met in time")


# ── AC-2: filter at subscription ────────────────────────────────────────


class TestFilterAtSubscription:
    async def test_filter_passed_to_factory_matches_is_watch_candidate(self, tmp_path) -> None:
        root = tmp_path / "kb-root"
        root.mkdir()
        data_dir = root / "data"
        excluded = (data_dir,)

        captured: dict[str, object] = {}

        def _factory(r, watch_filter, stop_event, ignore_permission_denied):
            captured["filter"] = watch_filter

            def _gen():
                q: queue.Queue = queue.Queue()
                while not stop_event.is_set():
                    try:
                        yield q.get(timeout=0.02)
                    except queue.Empty:
                        continue

            return _gen()

        mgr = WatchManager(_FakeIndexManager(), watch_factory=_factory, excluded_roots=excluded)
        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        await _wait_until(lambda: "filter" in captured)
        filt = captured["filter"]

        assert filt(Change.added, str(root / "a.md")) is True
        assert filt(Change.added, str(root / "sub")) is True
        assert filt(Change.deleted, str(root)) is True
        assert filt(Change.added, str(root / ".git" / "x.md")) is False
        assert filt(Change.added, str(root / "node_modules" / "y.txt")) is False
        assert filt(Change.added, str(data_dir / "z.md")) is False
        assert filt(Change.added, str(root / "a.png")) is False

        await mgr.drain()


# ── AC-3: one request per window ────────────────────────────────────────


class TestOneRequestPerWindow:
    @pytest.fixture
    def small_manager(self):
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(
            idx,
            watch_factory=factory,
            excluded_roots=(),
            settle_seconds=0.05,
            hold_cap_seconds=0.2,
        )
        return mgr, idx, factory

    async def _start_and_consume_post_subscribe_trigger(self, mgr, idx, factory, root: Path):
        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        await _wait_until(lambda: factory.queue_for(root) is not None)
        factory.queue_for(root).put(set())  # first yield -> _Ready -> post-subscribe trigger
        await idx.wait_for_call()
        assert idx.calls == ["kb1"]
        idx.calls.clear()

    async def test_burst_in_one_window_is_one_call(self, tmp_path, small_manager) -> None:
        mgr, idx, factory = small_manager
        root = tmp_path / "root"
        root.mkdir()
        await self._start_and_consume_post_subscribe_trigger(mgr, idx, factory, root)

        q = factory.queue_for(root)
        for _ in range(5):
            q.put({(Change.added, str(root / "a.md"))})

        await idx.wait_for_call()
        await asyncio.sleep(4 * 0.05)
        assert idx.calls == ["kb1"]

        await mgr.drain()

    async def test_hold_cap_forces_extra_calls(self, tmp_path, small_manager) -> None:
        mgr, idx, factory = small_manager
        root = tmp_path / "root"
        root.mkdir()
        await self._start_and_consume_post_subscribe_trigger(mgr, idx, factory, root)

        q = factory.queue_for(root)

        async def _feed():
            for _ in range(10):
                q.put({(Change.added, str(root / "a.md"))})
                await asyncio.sleep(0.04)

        await _feed()
        await asyncio.sleep(0.1)  # let the trailing settle timer fire
        assert 2 <= len(idx.calls) <= 4

        await mgr.drain()

    async def test_empty_yields_never_trigger(self, tmp_path, small_manager) -> None:
        mgr, idx, factory = small_manager
        root = tmp_path / "root"
        root.mkdir()
        await self._start_and_consume_post_subscribe_trigger(mgr, idx, factory, root)

        q = factory.queue_for(root)
        for _ in range(10):
            q.put(set())
        await asyncio.sleep(4 * 0.05)
        assert idx.calls == []

        await mgr.drain()


# ── AC-4: root removal ──────────────────────────────────────────────────


class TestRootRemoval:
    def _manager(self):
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(
            idx, watch_factory=factory, excluded_roots=(), settle_seconds=0.05, hold_cap_seconds=0.2
        )
        return mgr, idx, factory

    async def _start(
        self, mgr, idx, factory, root: Path, folder_id: str = "f1", kb_id: str = "kb1"
    ):
        folder = KBItem(id=folder_id, kb_id=kb_id, type="folder", path_or_url=str(root))
        mgr.start(kb_id, folder)
        await _wait_until(lambda: mgr._entries.get(folder_id) is not None)
        factory.queue_for(root).put(set())  # first (empty) yield -> watching
        await idx.wait_for_call()  # the post-subscribe trigger
        return folder

    @pytest.mark.parametrize("dirname", ["root", "notes.d"])
    async def test_deleted_root_marks_unavailable(self, tmp_path, dirname) -> None:
        mgr, idx, factory = self._manager()
        root = tmp_path / dirname
        root.mkdir()
        await self._start(mgr, idx, factory, root)
        idx.calls.clear()

        q = factory.queue_for(root)
        q.put({(Change.deleted, str(root))})

        await idx.wait_for_call()
        await _wait_until(lambda: mgr.state("f1") == "unavailable")
        assert mgr.error("f1") == "root removed"
        assert idx.calls == ["kb1"]

        entry = mgr._entries["f1"]
        assert entry.thread is not None
        entry.thread.join(timeout=1.0)
        assert not entry.thread.is_alive()
        await entry.task
        assert entry.task.done()

        await mgr.drain()

    async def test_modified_root_survives(self, tmp_path) -> None:
        mgr, idx, factory = self._manager()
        root = tmp_path / "root"
        root.mkdir()
        await self._start(mgr, idx, factory, root)
        idx.calls.clear()

        q = factory.queue_for(root)
        q.put({(Change.modified, str(root))})

        await idx.wait_for_call()
        assert idx.calls == ["kb1"]
        assert mgr.state("f1") == "watching"

        await mgr.drain()


# ── AC-5: error records ─────────────────────────────────────────────────


class TestErrorRecords:
    def _manager(self, factory):
        idx = _FakeIndexManager()
        mgr = WatchManager(idx, watch_factory=factory, excluded_roots=(), settle_seconds=0.05)
        return mgr, idx

    @pytest.mark.parametrize(
        "exc,expected_name",
        [
            (FileNotFoundError("no such root"), "FileNotFoundError"),
            (OSError(errno.ENOSPC, "no space"), "OSError"),
            (RuntimeError("watchfiles internal error"), "RuntimeError"),
        ],
    )
    async def test_construction_error_is_unavailable(
        self, tmp_path, caplog, exc, expected_name
    ) -> None:
        factory = _QueueFactory()
        mgr, idx = self._manager(factory)
        root = tmp_path / "root"
        root.mkdir()
        factory.queue_for(root).put(exc)

        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        with caplog.at_level("WARNING", logger="the_one.knowledge.watcher"):
            mgr.start("kb1", folder)
            await _wait_until(lambda: mgr.state("f1") == "unavailable")

        assert expected_name in mgr.error("f1")
        entry = mgr._entries["f1"]
        await entry.task
        assert entry.task.done()
        assert sum(1 for r in caplog.records if "watch error" in r.message) == 1

        await mgr.drain()

    async def test_error_after_first_yield_is_unavailable(self, tmp_path) -> None:
        factory = _QueueFactory()
        mgr, idx = self._manager(factory)
        root = tmp_path / "root"
        root.mkdir()
        q = factory.queue_for(root)
        q.put(set())  # first successful (empty) yield -> watching
        q.put(RuntimeError("boom mid-iteration"))

        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        # Both items may be drained before the test observes the transient
        # "watching" state (the thread posts both messages back-to-back) —
        # only the eventual outcome is asserted.
        await _wait_until(lambda: mgr.state("f1") == "unavailable")
        assert "RuntimeError" in mgr.error("f1")

        await mgr.drain()

    async def test_permission_error_retries_and_watches_on_readable_root(self, tmp_path) -> None:
        factory = _QueueFactory()
        mgr, idx = self._manager(factory)
        root = tmp_path / "root"
        root.mkdir()
        q = factory.queue_for(root)
        q.put(PermissionError("subtree denied"))
        q.put(set())

        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        await _wait_until(lambda: mgr.state("f1") == "watching")
        assert factory.calls == [(root, False), (root, True)]

        await mgr.drain()

    @pytest.mark.skipif(
        os.name != "posix" or os.geteuid() == 0,
        reason="chmod-based permission test needs a non-root POSIX user",
    )
    async def test_permission_error_on_unreadable_root_is_unavailable(self, tmp_path) -> None:
        factory = _QueueFactory()
        mgr, idx = self._manager(factory)
        root = tmp_path / "root"
        root.mkdir()
        root.chmod(0o000)
        try:
            q = factory.queue_for(root)
            q.put(PermissionError("root itself denied"))

            folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
            mgr.start("kb1", folder)
            await _wait_until(lambda: mgr.state("f1") == "unavailable")
            assert "not readable" in mgr.error("f1")
            assert factory.calls == [(root, False)]

            await mgr.drain()
        finally:
            root.chmod(0o755)


# ── AC-6: real watch ─────────────────────────────────────────────────────


class TestRealWatch:
    def _self_probe_delivers(self, tmp_path: Path) -> bool:
        gen = watchfiles.watch(
            str(tmp_path),
            watch_filter=None,
            debounce=50,
            step=25,
            rust_timeout=200,
            yield_on_timeout=True,
            force_polling=False,
            ignore_permission_denied=False,
            raise_interrupt=False,
            debug=False,
            poll_delay_ms=300,
            recursive=True,
        )
        delivered = False
        n = 0
        try:
            start = time.monotonic()
            for changes in gen:
                if changes:
                    delivered = True
                    break
                if time.monotonic() - start > 1.0:
                    break
                n += 1
                (tmp_path / f"self-probe-{n}.txt").write_text("x")
        finally:
            gen.close()
        return delivered

    async def test_real_watch_change_triggers_request_index(self, tmp_path) -> None:
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir()
        if not self._self_probe_delivers(probe_dir):
            pytest.skip(
                "this host/filesystem does not deliver native change "
                "notification events within the self-probe deadline"
            )

        root = tmp_path / "watched"
        root.mkdir()
        idx = _FakeIndexManager()
        mgr = WatchManager(idx, excluded_roots=(), settle_seconds=0.5, hold_cap_seconds=2.0)
        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        await _wait_until(lambda: mgr.state("f1") == "watching")

        (root / "a.md").write_text("hello")
        await idx.wait_for_call(timeout=5.0)
        assert "kb1" in idx.calls

        await mgr.drain()

    async def test_real_watch_root_removal(self, tmp_path) -> None:
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir()
        if not self._self_probe_delivers(probe_dir):
            pytest.skip(
                "this host/filesystem does not deliver native change "
                "notification events within the self-probe deadline"
            )

        root = tmp_path / "watched2"
        root.mkdir()
        idx = _FakeIndexManager()
        mgr = WatchManager(idx, excluded_roots=(), settle_seconds=0.5, hold_cap_seconds=2.0)
        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        await _wait_until(lambda: mgr.state("f1") == "watching")

        import shutil

        shutil.rmtree(root)
        await _wait_until(lambda: mgr.state("f1") == "unavailable", timeout=5.0)
        assert mgr.error("f1") == "root removed"

        await mgr.drain()

    async def test_real_watch_missing_root_is_unavailable(self, tmp_path) -> None:
        root = tmp_path / "does-not-exist"
        idx = _FakeIndexManager()
        mgr = WatchManager(idx, excluded_roots=())
        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        await _wait_until(lambda: mgr.state("f1") == "unavailable", timeout=5.0)
        assert "FileNotFoundError" in mgr.error("f1")
        assert mgr.state("f1") != "watching"

        await mgr.drain()


# ── AC-7: cap ────────────────────────────────────────────────────────────


class TestCap:
    async def test_third_folder_over_cap_is_unavailable(self, tmp_path) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(idx, watch_factory=factory, excluded_roots=(), max_watched=2)

        roots = [tmp_path / f"r{i}" for i in range(3)]
        for r in roots:
            r.mkdir()

        for i, r in enumerate(roots):
            folder = KBItem(id=f"f{i}", kb_id="kb1", type="folder", path_or_url=str(r))
            mgr.start("kb1", folder)

        await _wait_until(lambda: mgr.state("f2") == "unavailable")
        assert mgr.error("f2") == "watch limit reached (2)"
        assert mgr._entries["f2"].task is None

        # f0/f1 are live subscriptions under the cap — give each a first
        # yield so `stop` below ends a real subscription, not one still
        # blocked on its very first `next()`.
        factory.queue_for(roots[0]).put(set())
        factory.queue_for(roots[1]).put(set())
        await _wait_until(lambda: mgr.state("f0") == "watching" and mgr.state("f1") == "watching")

        await mgr.stop("f0")
        await mgr._resubscribe_unavailable()
        factory.queue_for(roots[2]).put(set())
        await _wait_until(lambda: mgr.state("f2") == "watching")

        await mgr.drain()

    async def test_stop_and_drain_on_cap_created_entry_no_error(self, tmp_path) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(idx, watch_factory=factory, excluded_roots=(), max_watched=0)

        root = tmp_path / "r0"
        root.mkdir()
        folder = KBItem(id="f0", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        assert mgr.state("f0") == "unavailable"
        assert mgr._entries["f0"].task is None

        await mgr.stop("f0")  # must not raise

        mgr.start("kb1", folder)
        await mgr.drain()  # must not raise


# ── AC-8: post-subscribe trigger and states ─────────────────────────────


class TestPostSubscribeTriggerAndStates:
    async def test_start_twice_is_idempotent(self, tmp_path) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(idx, watch_factory=factory, excluded_roots=(), settle_seconds=0.05)
        root = tmp_path / "root"
        root.mkdir()
        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))

        mgr.start("kb1", folder)
        first_entry = mgr._entries["f1"]
        mgr.start("kb1", folder)
        assert mgr._entries["f1"] is first_entry

        factory.queue_for(root).put(set())
        await _wait_until(lambda: mgr.state("f1") == "watching")
        await idx.wait_for_call()
        assert idx.calls == ["kb1"]  # exactly one post-subscribe trigger

        await mgr.drain()

    async def test_start_all_twice_is_no_op(self, conn, kb_repo, item_repo, tmp_path) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(
            idx,
            watch_factory=factory,
            conn_factory=_make_conn_factory(conn),
            excluded_roots=(),
            settings_loader=lambda: _const_settings(True, 300),
        )
        kb = await _make_kb(kb_repo, "kb1")
        root = tmp_path / "root"
        root.mkdir()
        await _make_folder(item_repo, kb.id, root, "f1")

        await mgr.start_all()
        entry_after_first = mgr._entries["f1"]
        await mgr.start_all()
        assert mgr._entries["f1"] is entry_after_first

        await mgr.drain()

    async def test_states_starting_then_watching_then_off(self, tmp_path) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(idx, watch_factory=factory, excluded_roots=())
        root = tmp_path / "root"
        root.mkdir()
        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))

        assert mgr.state("unknown-folder") == "off"
        mgr.start("kb1", folder)
        assert mgr.state("f1") == "starting"

        factory.queue_for(root).put(set())
        await _wait_until(lambda: mgr.state("f1") == "watching")

        await mgr.drain()

    async def test_apply_settings_disable_stops_everything(
        self, conn, kb_repo, item_repo, tmp_path
    ) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(
            idx,
            watch_factory=factory,
            conn_factory=_make_conn_factory(conn),
            excluded_roots=(),
            settle_seconds=0.05,
        )
        kb = await _make_kb(kb_repo, "kb1")
        root = tmp_path / "root"
        root.mkdir()
        await _make_folder(item_repo, kb.id, root, "f1")

        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        factory.queue_for(root).put(set())
        await _wait_until(lambda: mgr.state("f1") != "starting")
        thread_name = "the-one-watch-f1"
        assert any(t.name == thread_name for t in threading.enumerate())
        await idx.wait_for_call()  # drain the post-subscribe trigger

        await mgr.apply_settings(MonitoringSettings(watch_enabled=False))
        assert mgr.state("f1") == "off"
        _wait_thread_gone(thread_name)

        idx.calls.clear()
        await asyncio.sleep(0.2)
        assert idx.calls == []  # no late trigger from a stale timer

        await mgr.drain()

    async def test_apply_settings_enable_resubscribes_all_folders(
        self, conn, kb_repo, item_repo, tmp_path
    ) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(
            idx, watch_factory=factory, conn_factory=_make_conn_factory(conn), excluded_roots=()
        )
        kb1 = await _make_kb(kb_repo, "kb1")
        kb2 = await _make_kb(kb_repo, "kb2")
        r1 = tmp_path / "r1"
        r1.mkdir()
        r2 = tmp_path / "r2"
        r2.mkdir()
        r3 = tmp_path / "r3"
        r3.mkdir()
        await _make_folder(item_repo, kb1.id, r1, "f1")
        await _make_folder(item_repo, kb1.id, r2, "f2")
        await _make_folder(item_repo, kb2.id, r3, "f3")

        await mgr.apply_settings(MonitoringSettings(watch_enabled=True))
        await _wait_until(lambda: all(mgr.state(f) == "starting" for f in ("f1", "f2", "f3")))

        await mgr.drain()

    async def test_concurrent_apply_settings_consistent_end_state(
        self, conn, kb_repo, item_repo, tmp_path
    ) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(
            idx, watch_factory=factory, conn_factory=_make_conn_factory(conn), excluded_roots=()
        )
        kb = await _make_kb(kb_repo, "kb1")
        root = tmp_path / "root"
        root.mkdir()
        await _make_folder(item_repo, kb.id, root, "f1")

        await asyncio.gather(
            mgr.apply_settings(MonitoringSettings(watch_enabled=False)),
            mgr.apply_settings(MonitoringSettings(watch_enabled=True)),
        )
        # Whichever call ran last determines the end state; either is
        # consistent (every folder watching/starting, or every folder off).
        state = mgr.state("f1")
        assert state in ("off", "starting", "watching")

        await mgr.drain()


def _const_settings(watch_enabled: bool, reconcile_interval_seconds):
    async def _f():
        return MonitoringSettings.model_construct(
            watch_enabled=watch_enabled, reconcile_interval_seconds=reconcile_interval_seconds
        )

    return _f()


# ── AC-9: suppression and concurrency ───────────────────────────────────


class TestSuppressionAndConcurrency:
    async def test_stop_kb_concurrent_with_tick_no_runtime_error(
        self, conn, kb_repo, item_repo, tmp_path
    ) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(
            idx, watch_factory=factory, conn_factory=_make_conn_factory(conn), excluded_roots=()
        )
        kb = await _make_kb(kb_repo, "kb1")
        root = tmp_path / "root"
        root.mkdir()
        await _make_folder(item_repo, kb.id, root, "f1")
        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        factory.queue_for(root).put(set())
        await _wait_until(lambda: mgr.state("f1") != "starting")

        await asyncio.gather(mgr.stop_kb("kb1"), mgr._tick())
        assert "f1" not in mgr._entries

        await mgr.drain()

    async def test_suppress_silences_schedule_and_changes(self, tmp_path) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(
            idx, watch_factory=factory, excluded_roots=(), settle_seconds=0.05, hold_cap_seconds=0.2
        )
        root = tmp_path / "root"
        root.mkdir()
        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        factory.queue_for(root).put(set())
        await idx.wait_for_call()
        idx.calls.clear()

        async with mgr.suppress("kb1"):
            mgr._schedule("kb1")
            factory.queue_for(root).put({(Change.added, str(root / "a.md"))})
            await asyncio.sleep(0.15)
            assert idx.calls == []
            # A reconcile tick also skips a suppressed KB.
            await mgr._tick()
            assert idx.calls == []

        factory.queue_for(root).put({(Change.added, str(root / "b.md"))})
        await idx.wait_for_call()
        assert idx.calls == ["kb1"]

        await mgr.drain()

    async def test_suppress_releases_on_exception(self, tmp_path) -> None:
        idx = _FakeIndexManager()
        mgr = WatchManager(idx, excluded_roots=())

        with pytest.raises(ValueError):
            async with mgr.suppress("kb1"):
                raise ValueError("boom")

        assert "kb1" not in mgr._suppressed
        await mgr.drain()

    async def test_suppress_cancels_previously_armed_timer(self, tmp_path) -> None:
        idx = _FakeIndexManager()
        mgr = WatchManager(idx, excluded_roots=(), settle_seconds=0.05)
        mgr._schedule("kb1")
        assert "kb1" in mgr._timers

        async with mgr.suppress("kb1"):
            assert "kb1" not in mgr._timers

        await asyncio.sleep(0.1)
        assert idx.calls == []
        await mgr.drain()


# ── AC-10: reconcile loop ───────────────────────────────────────────────


class TestReconcileLoop:
    async def test_periodic_tick_indexes_only_kb_with_folder(
        self, conn, kb_repo, item_repo, tmp_path
    ) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        kb_with_folder = await _make_kb(kb_repo, "kb-folder")
        await _make_kb(kb_repo, "kb-empty")
        root = tmp_path / "root"
        root.mkdir()
        await _make_folder(item_repo, kb_with_folder.id, root, "f1")

        mgr = WatchManager(
            idx,
            watch_factory=factory,
            conn_factory=_make_conn_factory(conn),
            excluded_roots=(),
            settings_loader=lambda: _const_settings(True, 0.05),
        )
        await mgr.start_all()

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and idx.calls.count("kb-folder") < 2:
            await asyncio.sleep(0.02)

        assert idx.calls.count("kb-folder") >= 2
        assert "kb-empty" not in idx.calls

        await mgr.drain()

    async def test_apply_settings_wakes_loop_for_new_interval(
        self, conn, kb_repo, item_repo, tmp_path
    ) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        loader_state = {"interval": 0.05}

        async def _loader():
            return MonitoringSettings.model_construct(
                watch_enabled=True, reconcile_interval_seconds=loader_state["interval"]
            )

        kb = await _make_kb(kb_repo, "kb1")
        root = tmp_path / "root"
        root.mkdir()
        await _make_folder(item_repo, kb.id, root, "f1")

        mgr = WatchManager(
            idx,
            watch_factory=factory,
            conn_factory=_make_conn_factory(conn),
            excluded_roots=(),
            settings_loader=_loader,
        )
        await mgr.start_all()
        await idx.wait_for_call()  # the tick or the post-subscribe trigger

        loader_state["interval"] = 10.0
        idx.calls.clear()
        await mgr.apply_settings(
            MonitoringSettings.model_construct(watch_enabled=True, reconcile_interval_seconds=10.0)
        )
        idx.calls.clear()
        await asyncio.sleep(0.3)
        assert "kb1" not in idx.calls

        await mgr.drain()

    async def test_tick_resubscribes_unavailable_entry_once_factory_recovers(
        self, conn, kb_repo, item_repo, tmp_path
    ) -> None:
        idx = _FakeIndexManager()
        root = tmp_path / "root"
        root.mkdir()

        state = {"calls": 0}

        def _flaky_factory(r, watch_filter, stop_event, ignore_permission_denied):
            state["calls"] += 1
            if state["calls"] == 1:
                raise FileNotFoundError("first attempt fails")

            def _gen():
                yield set()
                while not stop_event.is_set():
                    time.sleep(0.02)

            return _gen()

        kb = await _make_kb(kb_repo, "kb1")
        await _make_folder(item_repo, kb.id, root, "f1")

        mgr = WatchManager(
            idx,
            watch_factory=_flaky_factory,
            conn_factory=_make_conn_factory(conn),
            excluded_roots=(),
            settings_loader=lambda: _const_settings(True, 0.05),
        )
        await mgr.start_all()
        await _wait_until(lambda: mgr.state("f1") == "unavailable", timeout=2.0)
        await _wait_until(lambda: mgr.state("f1") == "watching", timeout=2.0)

        await mgr.drain()


# ── AC-11: stop and drain ───────────────────────────────────────────────


class TestStopAndDrain:
    async def test_stop_returns_promptly_via_sentinel(self, tmp_path) -> None:
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(idx, watch_factory=factory, excluded_roots=(), drain_timeout=5.0)
        root = tmp_path / "root"
        root.mkdir()
        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        factory.queue_for(root).put(set())
        await _wait_until(lambda: mgr.state("f1") != "starting")

        start = time.monotonic()
        await mgr.stop("f1")
        assert time.monotonic() - start < 1.0

    async def test_drain_three_live_entries_stops_via_sentinel_not_timeout(self, tmp_path) -> None:
        # The property: drain() ends each watch through its stop sentinel, never by
        # running into ``drain_timeout`` (the cancel fallback). A drain that waited on
        # a watcher ignoring the sentinel would take the full 30 s timeout; the bound
        # is half of it, so host load (the watchers poll every 20 ms) cannot reach it.
        drain_timeout = 30.0
        idx = _FakeIndexManager()
        factory = _QueueFactory()
        mgr = WatchManager(
            idx, watch_factory=factory, excluded_roots=(), drain_timeout=drain_timeout
        )
        roots = []
        for i in range(3):
            r = tmp_path / f"r{i}"
            r.mkdir()
            roots.append(r)
            folder = KBItem(id=f"f{i}", kb_id="kb1", type="folder", path_or_url=str(r))
            mgr.start("kb1", folder)
            factory.queue_for(r).put(set())
        await _wait_until(lambda: all(mgr.state(f"f{i}") != "starting" for i in range(3)))

        thread_names = [f"the-one-watch-f{i}" for i in range(3)]
        start = time.monotonic()
        await mgr.drain()
        assert time.monotonic() - start < drain_timeout / 2
        # The task ends when the thread posts its terminal ``_Done``, a moment before
        # the thread itself is reaped, so wait for the exit instead of sampling it.
        for name in thread_names:
            _wait_thread_gone(name, timeout=10.0)
        assert not any(t.name in thread_names for t in threading.enumerate())
        assert mgr._timers == {}
        assert mgr._reconcile_task is None

    async def test_stop_bounded_by_drain_timeout_when_factory_ignores_stop(self, tmp_path) -> None:
        root = tmp_path / "root"
        root.mkdir()

        def _stuck_factory(r, watch_filter, stop_event, ignore_permission_denied):
            def _gen():
                yield set()
                time.sleep(3.0)
                yield set()

            return _gen()

        idx = _FakeIndexManager()
        mgr = WatchManager(idx, watch_factory=_stuck_factory, excluded_roots=(), drain_timeout=0.3)
        folder = KBItem(id="f1", kb_id="kb1", type="folder", path_or_url=str(root))
        mgr.start("kb1", folder)
        await _wait_until(lambda: mgr.state("f1") == "watching")

        start = time.monotonic()
        await mgr.stop("f1")
        elapsed = time.monotonic() - start
        assert 0.25 <= elapsed < 2.0


# ── AC-1 / AC-12: source-level contract tests ───────────────────────────


class TestKnobsAndContract:
    def _source(self) -> str:
        return inspect.getsource(watcher_mod)

    def test_default_factory_pins_every_dd0_keyword(self) -> None:
        source = inspect.getsource(watcher_mod._default_watch_factory)
        for needle in (
            "force_polling=False",
            "raise_interrupt=False",
            "debug=False",
            "poll_delay_ms=",
            "recursive=True",
            "debounce=",
            "step=",
            "rust_timeout=",
            "yield_on_timeout=True",
            "ignore_permission_denied=",
        ):
            assert needle in source, f"missing DD-0 keyword {needle!r}"

    def test_permission_error_precedes_os_error_in_two_step_subscribe(self) -> None:
        source = inspect.getsource(watcher_mod.WatchManager._two_step_subscribe)
        perm_idx = source.index("except PermissionError")
        os_idx = source.index("except OSError")
        assert perm_idx < os_idx

    def test_no_lock_no_repository_beyond_kb_and_item(self) -> None:
        """Review fix (Flight 4 Leg 3): the forbidden set is derived
        programmatically from every ``*Repository`` class currently
        defined in ``the_one/db/repositories.py``, rather than a
        hand-picked pair — so a repository added after this test was
        written is still caught if ``watcher.py`` starts referencing it.
        """
        source = self._source()
        assert "write_transaction" not in source
        assert "_embed_lock" not in source

        from the_one.db import repositories as repositories_mod

        repo_source = inspect.getsource(repositories_mod)
        all_repo_classes = set(re.findall(r"^class (\w+Repository)", repo_source, re.MULTILINE))
        allowed = {"KnowledgeBaseRepository", "KBItemRepository"}
        forbidden = all_repo_classes - allowed
        assert forbidden, "sanity: repositories.py should define repos beyond the two allowed"
        for name in sorted(forbidden):
            assert name not in source, f"watcher.py references forbidden repository {name!r}"

    def test_run_awaits_no_repository_or_store_method(self) -> None:
        """``_run`` awaits exactly one thing: its own queue. It never
        awaits a repository or store method (AC-12)."""
        run_source = inspect.getsource(watcher_mod.WatchManager._run)
        awaits = [line.strip() for line in run_source.splitlines() if "await " in line]
        assert awaits == ["msg = await entry.queue.get()"]


class TestAccessorPair:
    def test_set_and_get_manager(self) -> None:
        assert get_manager() is None
        mgr = WatchManager(_FakeIndexManager())
        set_manager(mgr)
        assert get_manager() is mgr
        set_manager(None)
        assert get_manager() is None
