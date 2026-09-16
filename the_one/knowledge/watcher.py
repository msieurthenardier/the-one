"""``WatchManager`` — one supervised, dedicated-thread ``watchfiles``
subscription per registered folder ``KBItem`` (Flight 4 M24 F04 Leg 2,
DD-0/DD-1/DD-2/DD-3/DD-4).

Modelled on ``the_one/knowledge/manager.py``'s ``IndexingManager`` — a
``dict[folder_id, _WatchEntry]``, a module-level singleton published via
:func:`set_manager` / resolved via :func:`get_manager` — and, per
``agents.md``'s ``supervised-per-entity-worker`` convention, a third
instance of the shape ``the_one/connectors/manager.py::ConnectorManager``
established. **What this module shares with that convention**: one
supervised unit of work per entity, an accessor pair, constructor-keyword
overrides for every constant/factory, a state word read through a sync
accessor. **What it deliberately does not share**: the wake/idle event
pair and the ``shield`` + ``wait_for`` cooperative-stop dance those two
managers use — a watch subscription has no in-flight pass to let finish;
the ``threading.Event`` stop signal ends it within one ``step`` (DD-1),
so ``stop()`` here is a plain bounded wait with a cancel fallback, not a
cooperative handshake.

**The watcher is a latency optimisation, never a source of truth.** It
takes no lock, never opens the database beyond listing knowledge bases and
folder items (``start_all``/``apply_settings``/the reconcile tick), never
``stat``s a path, and never classifies a change beyond "does this path
matter" (DD-2's :func:`~the_one.knowledge.walk.is_watch_candidate`). Every
trigger — from an event, from the post-subscribe first yield, or from the
periodic reconcile tick — is exactly one call to
``index_manager.request_index(kb_id)``, itself synchronous and coalescing
(``manager.py``); the walk that call eventually runs is what decides what
actually changed. Lock order (``manager.py``'s module docstring): this
module never acquires the manager lock or a store per-KB lock, so the
invariant is never in play here.

**DD-0 — every ``watchfiles.watch`` keyword is pinned explicitly, no
library or environment default is inherited.** ``force_polling=False``,
``raise_interrupt=False``, ``debug=False``, ``poll_delay_ms=300`` (inert,
pinned so an env var cannot reach it), ``recursive=True``, and an explicit
``debounce``/``step``/``rust_timeout`` — see :func:`_default_watch_factory`.
``ignore_permission_denied`` follows a **two-step rule**
(:meth:`WatchManager._two_step_subscribe`): subscribe with ``False``
first; only on ``PermissionError`` — caught **before** ``OSError``, since
it is a subclass and an ``OSError`` clause written first would silently
remove the retry — and only when the root itself is readable
(``os.access(root, R_OK | X_OK)``, checked once at subscribe time, never
in the event path), retry with ``True``. An unreadable root goes
``unavailable`` with a reason naming it, visibly, rather than silently
retrying with a value that would construct a zero-watch subscription the
first empty yield then reports as ``watching``.

**Message protocol** (thread → task, one ``asyncio.Queue`` per entry): a
dedicated ``threading.Thread`` runs the sync ``watchfiles.watch`` generator
and posts ``_Ready`` (once, after the first yield of a successful two-step
subscribe), ``_Changes`` (once per non-empty yielded set), ``_Error`` (a
construction or mid-iteration failure — the whole generator body is
wrapped, not only construction), and a terminal ``_Done`` posted from a
``finally`` — the task's *only* termination path; without it every
``stop``/``drain``/``apply_settings(False)`` would block for its full
timeout. Every post goes through :meth:`WatchManager._post`:
``loop.call_soon_threadsafe`` guarded by ``loop.is_closed()`` and
``try/except RuntimeError``, because a thread abandoned past the drain
timeout may post after the loop has closed.

**State words** (:meth:`WatchManager.state`): ``"off"`` — no entry (the
watcher is disabled, the manager is not installed, or the folder was never
started). ``"starting"`` — an entry exists but its subscription has not
yet reported a first yield. ``"watching"`` — reported **only** after the
first yield (an empty timeout yield counts — it proves the subscription is
established). ``"unavailable"`` — the entry exists but the subscription is
down; :meth:`WatchManager.error` names why.

**Trigger semantics (DD-3)**: :meth:`WatchManager._schedule` arms or
re-arms a **per-knowledge-base** ``loop.call_later`` for ``settle_seconds``
after the most recent qualifying event, clamped to at most
``hold_cap_seconds`` after the *first* event of the current burst — a
folder that never stops changing is still indexed at least once per hold
cap. :meth:`WatchManager.suppress` is an ``asynccontextmanager`` a delete
route holds across ``stop → delete → request_index`` (Leg 3, DD-8): it
cancels the knowledge base's armed timer and, for the duration, makes
``_schedule``, the timer callback, and the reconcile tick skip that
knowledge base — closing the race Flight 3 AC-10 closed for indexing
alone.

**The reconcile loop (DD-4)** runs unconditionally — whether or not the
watcher is enabled, since with it off the loop is the only way a change is
ever reflected. Each tick calls ``request_index`` for every knowledge base
that has at least one folder and is not suppressed (a synchronous check
immediately before the call, with no ``await`` in between — the listing
itself is async, and a check taken before it would re-open the suppression
window mid-iteration), then :meth:`WatchManager._resubscribe_unavailable`,
which retries every ``unavailable`` entry (root removed, a construction
error, a folder that lost its cap slot) against a **snapshot** of the
entries dict, since a concurrent route ``stop`` can pop entries while the
tick awaits.

**The cap (DD-1)**: at most ``max_watched`` live subscriptions
(``MAX_WATCHED_FOLDERS = 64`` by default). A folder past the cap gets an
entry with no thread and no task, ``unavailable`` with a reason naming the
limit; the reconcile tick promotes it once a slot frees.

**Root removal (DD-1)**: the native backend reports exactly one
``deleted <root>`` on removal or rename, then silence — the subscription
is dead without saying so. The task recognises a ``Change.deleted`` whose
path equals the root itself (compared via ``os.path.normcase`` on both
sides, never a raw string compare — see
:func:`~the_one.knowledge.walk.is_watch_candidate`'s docstring for why),
schedules one final trigger (so the next walk marks the folder ``failed``,
Flight 3 DD-3), stops the thread, and marks the entry ``unavailable``. A
plain ``modified <root>`` (an ordinary directory modification — a file
created or removed inside it) is deliberately survivable and never tears
the watch down.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import os
import threading
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path, PurePath
from typing import TYPE_CHECKING

import watchfiles

from the_one.config import settings
from the_one.db.connection import get_connection
from the_one.db.models import KBItem
from the_one.db.repositories import KBItemRepository, KnowledgeBaseRepository
from the_one.knowledge.extractors import supported_extensions
from the_one.knowledge.settings import MonitoringSettings, load_knowledge_settings
from the_one.knowledge.walk import is_watch_candidate
from the_one.platform.paths import canonicalize

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)

# ── Constants (constructor-overridable for tests) ──────────────────────────

SETTLE_SECONDS = 5.0
HOLD_CAP_SECONDS = 60.0
MAX_WATCHED_FOLDERS = 64
WATCH_DRAIN_TIMEOUT = 5.0
RUST_TIMEOUT_MS = 1000
DEBOUNCE_MS = 1600
STEP_MS = 50

__all__ = [
    "WatchManager",
    "WatchFactory",
    "SETTLE_SECONDS",
    "HOLD_CAP_SECONDS",
    "MAX_WATCHED_FOLDERS",
    "WATCH_DRAIN_TIMEOUT",
    "RUST_TIMEOUT_MS",
    "DEBOUNCE_MS",
    "STEP_MS",
    "set_manager",
    "get_manager",
]

# The fourth positional argument is ignore_permission_denied — DD-0's
# two-step rule made observable through the seam (Leg 2 design review
# widened DD-1's three-argument seam by one; flight-log note).
WatchFactory = Callable[
    [Path, Callable[["watchfiles.Change", str], bool], threading.Event, bool],
    Iterator["set[tuple[watchfiles.Change, str]]"],
]


def _default_watch_factory(
    root: Path,
    watch_filter: Callable[["watchfiles.Change", str], bool],
    stop_event: threading.Event,
    ignore_permission_denied: bool,
) -> Iterator["set[tuple[watchfiles.Change, str]]"]:
    """Every DD-0 keyword explicit. A plain function returning
    ``watchfiles.watch(...)`` — a generator whose Rust-side notifier
    construction runs on the first ``next()``, never at call time."""
    return watchfiles.watch(
        root,
        watch_filter=watch_filter,
        stop_event=stop_event,
        debounce=DEBOUNCE_MS,
        step=STEP_MS,
        rust_timeout=RUST_TIMEOUT_MS,
        yield_on_timeout=True,
        force_polling=False,
        raise_interrupt=False,
        debug=False,
        poll_delay_ms=300,
        recursive=True,
        ignore_permission_denied=ignore_permission_denied,
    )


def _make_watch_filter(
    root: Path, excluded_roots: tuple[Path, ...]
) -> Callable[["watchfiles.Change", str], bool]:
    """The DD-2 trigger filter bound to one subscription's root and
    extension set — ``supported_extensions()`` is read once per
    subscription (Leg 1's rule: a new extractor registered later needs a
    restart to be watched for, same as the walk)."""
    extensions = supported_extensions()

    def _filt(change: "watchfiles.Change", path: str) -> bool:
        del change  # DD-2: the filter decides on the path alone
        return is_watch_candidate(
            path, root=root, extensions=extensions, excluded_roots=excluded_roots
        )

    return _filt


def _normcase_path(path: str) -> PurePath:
    return PurePath(os.path.normcase(path))


def _is_root_path(path: str, root: Path) -> bool:
    return _normcase_path(path) == _normcase_path(str(root))


def _contains_root_deletion(
    root: Path, changes: "frozenset[tuple[watchfiles.Change, str]]"
) -> bool:
    return any(
        change == watchfiles.Change.deleted and _is_root_path(path, root)
        for change, path in changes
    )


# ── Thread -> task message protocol ─────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class _Ready:
    pass


@dataclasses.dataclass(frozen=True)
class _Changes:
    changes: "frozenset[tuple[watchfiles.Change, str]]"


@dataclasses.dataclass(frozen=True)
class _Error:
    reason: str


@dataclasses.dataclass(frozen=True)
class _Done:
    pass


@dataclasses.dataclass
class _WatchEntry:
    """Per-folder watch bookkeeping, keyed by folder item id (not
    knowledge base — folders are registered and deleted one at a time).
    ``task``/``thread`` are ``None`` for an entry the cap created without
    a subscription; ``stop``/``drain``/``apply_settings`` handle such
    entries without error."""

    task: asyncio.Task | None
    thread: threading.Thread | None
    stop: threading.Event
    queue: "asyncio.Queue"
    loop: asyncio.AbstractEventLoop
    kb_id: str
    root: Path
    state: str
    error: str | None


class WatchManager:
    """One supervised dedicated-thread ``watchfiles`` subscription per
    registered folder ``KBItem``. See the module docstring for the full
    contract."""

    def __init__(
        self,
        index_manager,
        *,
        conn_factory: Callable[[], Awaitable["aiosqlite.Connection"]] = get_connection,
        settings_loader: Callable[[], Awaitable[MonitoringSettings]] | None = None,
        watch_factory: WatchFactory = _default_watch_factory,
        excluded_roots: tuple[Path, ...] | None = None,
        settle_seconds: float = SETTLE_SECONDS,
        hold_cap_seconds: float = HOLD_CAP_SECONDS,
        max_watched: int = MAX_WATCHED_FOLDERS,
        drain_timeout: float = WATCH_DRAIN_TIMEOUT,
    ) -> None:
        self._index_manager = index_manager
        self._conn_factory = conn_factory
        self._settings_loader = settings_loader
        self._watch_factory = watch_factory
        self._excluded_roots = (
            excluded_roots if excluded_roots is not None else (canonicalize(settings.data_dir),)
        )
        self._settle_seconds = settle_seconds
        self._hold_cap_seconds = hold_cap_seconds
        self._max_watched = max_watched
        self._drain_timeout = drain_timeout

        self._entries: dict[str, _WatchEntry] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._timer_first_event: dict[str, float] = {}
        self._suppressed: set[str] = set()
        self._lifecycle_lock = asyncio.Lock()
        self._settings_changed = asyncio.Event()
        self._reconcile_task: asyncio.Task | None = None
        # Initial default before the first start_all()/apply_settings()
        # call — matches MonitoringSettings.watch_enabled's own default.
        self._enabled = True

    # ── per-folder lifecycle ─────────────────────────────────────────────

    def start(self, kb_id: str, folder: KBItem) -> None:
        """Create ``folder``'s watch entry (and, if a slot is free under
        the cap, its thread and task) if absent. A no-op if a live task
        already exists. A no-op, creating no entry, if the watcher is
        disabled (the folder then reads ``"off"``). Requires a running
        event loop (``asyncio.get_running_loop()``), like
        ``IndexingManager.start``."""
        if not self._enabled:
            return
        folder_id = folder.id
        existing = self._entries.get(folder_id)
        if existing is not None and existing.task is not None and not existing.task.done():
            return

        loop = asyncio.get_running_loop()
        live = sum(1 for e in self._entries.values() if e.task is not None and not e.task.done())
        entry = _WatchEntry(
            task=None,
            thread=None,
            stop=threading.Event(),
            queue=asyncio.Queue(),
            loop=loop,
            kb_id=kb_id,
            root=Path(folder.path_or_url),
            state="starting",
            error=None,
        )
        # Always create the entry before the task (DD-1).
        self._entries[folder_id] = entry
        if live >= self._max_watched:
            entry.state = "unavailable"
            entry.error = f"watch limit reached ({self._max_watched})"
            return
        self._start_entry(folder_id, entry)

    def _start_entry(self, folder_id: str, entry: _WatchEntry) -> None:
        thread = threading.Thread(
            target=self._subscribe_and_pump,
            args=(folder_id, entry),
            name=f"the-one-watch-{folder_id}",
            daemon=True,
        )
        entry.thread = thread
        entry.task = asyncio.create_task(self._run(folder_id, entry))
        thread.start()

    def state(self, folder_id: str) -> str:
        entry = self._entries.get(folder_id)
        if entry is None:
            return "off"
        return entry.state

    def error(self, folder_id: str) -> str | None:
        entry = self._entries.get(folder_id)
        if entry is None:
            return None
        return entry.error

    async def stop(self, folder_id: str) -> None:
        """Stop and forget ``folder_id``'s entry. A no-op for an unknown
        id or one with no task (a cap-created entry). Bounded by
        ``drain_timeout`` with a cancel fallback — not the cooperative
        ``shield``+``wait_for`` dance ``IndexingManager.stop`` uses, since
        a watch has no in-flight pass to let finish; the sentinel makes
        this return promptly in the common case."""
        entry = self._entries.pop(folder_id, None)
        if entry is None:
            return
        entry.stop.set()
        if entry.task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(entry.task), self._drain_timeout)
        except TimeoutError:
            entry.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await entry.task

    async def stop_kb(self, kb_id: str) -> None:
        """Cancel ``kb_id``'s armed timer and stop every one of its
        folder entries concurrently."""
        timer = self._timers.pop(kb_id, None)
        if timer is not None:
            timer.cancel()
        self._timer_first_event.pop(kb_id, None)
        folder_ids = [fid for fid, entry in self._entries.items() if entry.kb_id == kb_id]
        await asyncio.gather(*(self.stop(fid) for fid in folder_ids), return_exceptions=True)

    # ── thread body ──────────────────────────────────────────────────────

    def _two_step_subscribe(
        self,
        root: Path,
        watch_filter: Callable[["watchfiles.Change", str], bool],
        stop_event: threading.Event,
    ) -> tuple[
        Iterator["set[tuple[watchfiles.Change, str]]"], "set[tuple[watchfiles.Change, str]]"
    ]:
        """DD-0's two-step subscribe. Subscribe with
        ``ignore_permission_denied=False``; on ``PermissionError`` —
        caught before ``OSError``, since it is a subclass — retry with
        ``True`` only when the root itself is readable. Returns the
        generator and its already-consumed first yield (possibly an empty
        set). Construction errors surface only on the generator's first
        ``next()`` (the factory call itself never raises), so this method
        never wraps the factory call in a ``try``."""
        gen = self._watch_factory(root, watch_filter, stop_event, False)
        try:
            first = next(gen)
        except PermissionError:
            gen.close()
            if not os.access(root, os.R_OK | os.X_OK):
                raise PermissionError(f"root not readable: {root}") from None
            gen = self._watch_factory(root, watch_filter, stop_event, True)
            first = next(gen)
            return gen, first
        except OSError:
            raise
        return gen, first

    def _post(self, entry: _WatchEntry, msg: object) -> None:
        """Every post to the entry's queue goes through here: a
        ``loop.is_closed()`` guard plus ``try/except RuntimeError``,
        because a thread abandoned past the drain timeout may post after
        the loop has closed."""
        if entry.loop.is_closed():
            return
        try:
            entry.loop.call_soon_threadsafe(entry.queue.put_nowait, msg)
        except RuntimeError:
            pass

    def _subscribe_and_pump(self, folder_id: str, entry: _WatchEntry) -> None:
        """Thread body (DD-1). Runs the two-step subscribe, then pumps
        every yielded non-empty change set to the entry's queue. The
        whole body — construction and every iteration — is wrapped in one
        ``try/except Exception``, since ``WatchfilesRustInternalError``
        can be raised from any iteration, not only construction. Always
        posts a terminal ``_Done`` from ``finally`` — the task's only
        termination path."""
        del folder_id  # thread name already carries it; kept for symmetry
        watch_filter = _make_watch_filter(entry.root, self._excluded_roots)
        gen: Iterator["set[tuple[watchfiles.Change, str]]"] | None = None
        try:
            gen, first = self._two_step_subscribe(entry.root, watch_filter, entry.stop)
            self._post(entry, _Ready())
            if first:
                self._post(entry, _Changes(frozenset(first)))
            for changes in gen:
                if changes:
                    self._post(entry, _Changes(frozenset(changes)))
        except Exception as exc:  # noqa: BLE001 — reported to the task, never crashes the thread
            self._post(entry, _Error(f"{type(exc).__name__}: {exc}"))
        finally:
            if gen is not None:
                with contextlib.suppress(Exception):
                    gen.close()
            self._post(entry, _Done())

    # ── task body ────────────────────────────────────────────────────────

    async def _run(self, folder_id: str, entry: _WatchEntry) -> None:
        """Consume the entry's queue until ``_Done``. Never opens the
        database, never ``stat``s, never takes a lock (AC-12)."""
        draining = False
        while True:
            msg = await entry.queue.get()
            if isinstance(msg, _Done):
                return
            if draining:
                # A message after root removal or an error: the entry is
                # already draining to _Done, ignore it.
                continue
            if isinstance(msg, _Ready):
                entry.state = "watching"
                entry.error = None
                self._schedule(entry.kb_id)
            elif isinstance(msg, _Changes):
                if _contains_root_deletion(entry.root, msg.changes):
                    self._schedule(entry.kb_id)
                    entry.stop.set()
                    entry.state = "unavailable"
                    entry.error = "root removed"
                    draining = True
                else:
                    self._schedule(entry.kb_id)
            elif isinstance(msg, _Error):
                logger.warning(
                    "folder %s (kb %s): watch error: %s", folder_id, entry.kb_id, msg.reason
                )
                entry.state = "unavailable"
                entry.error = msg.reason
                draining = True

    # ── trigger (DD-3) ───────────────────────────────────────────────────

    def _schedule(self, kb_id: str) -> None:
        if kb_id in self._suppressed:
            return
        loop = asyncio.get_running_loop()
        now = loop.time()
        if kb_id not in self._timers:
            self._timer_first_event[kb_id] = now
        else:
            self._timers[kb_id].cancel()
        first_event_at = self._timer_first_event[kb_id]
        delay = max(
            0.0, min(now + self._settle_seconds, first_event_at + self._hold_cap_seconds) - now
        )
        self._timers[kb_id] = loop.call_later(delay, self._fire, kb_id)

    def _fire(self, kb_id: str) -> None:
        self._timers.pop(kb_id, None)
        self._timer_first_event.pop(kb_id, None)
        if kb_id in self._suppressed:
            return
        self._index_manager.request_index(kb_id)

    @contextlib.asynccontextmanager
    async def suppress(self, kb_id: str):
        """Cancel ``kb_id``'s armed timer and, for the duration, make
        ``_schedule``, the timer callback and the reconcile tick skip it.
        Releases in ``finally`` — a delete route's 404 may fire inside the
        guarded region."""
        timer = self._timers.pop(kb_id, None)
        if timer is not None:
            timer.cancel()
        self._timer_first_event.pop(kb_id, None)
        self._suppressed.add(kb_id)
        try:
            yield
        finally:
            self._suppressed.discard(kb_id)

    # ── settings + reconcile loop (DD-4/DD-5) ───────────────────────────

    async def _load_settings(self) -> MonitoringSettings:
        try:
            if self._settings_loader is not None:
                return await self._settings_loader()
            conn = await self._conn_factory()
            return (await load_knowledge_settings(conn)).monitoring
        except Exception:
            logger.warning(
                "watch manager: failed to load monitoring settings; using defaults", exc_info=True
            )
            return MonitoringSettings()

    def _ensure_reconcile_task(self) -> None:
        if self._reconcile_task is None or self._reconcile_task.done():
            self._reconcile_task = asyncio.create_task(self._reconcile_loop())

    async def _reconcile_loop(self) -> None:
        while True:
            try:
                m = await self._load_settings()
                try:
                    await asyncio.wait_for(
                        self._settings_changed.wait(), timeout=m.reconcile_interval_seconds
                    )
                except TimeoutError:
                    await self._tick()
                else:
                    self._settings_changed.clear()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("watch manager: reconcile loop iteration failed")

    async def _tick(self) -> None:
        try:
            conn = await self._conn_factory()
            kb_repo = KnowledgeBaseRepository(conn)
            item_repo = KBItemRepository(conn)
            for kb in await kb_repo.list():
                has_folder = bool(await item_repo.list_folders(kb.id))
                if not has_folder:
                    continue
                # Synchronous check, no await between it and the call —
                # DD-3: the listings above are async, so a check taken
                # before them would re-open the suppression window
                # mid-iteration.
                if kb.id in self._suppressed:
                    continue
                self._index_manager.request_index(kb.id)
            await self._resubscribe_unavailable()
        except Exception:
            logger.exception("watch manager: reconcile tick failed")

    async def _resubscribe_unavailable(self) -> None:
        if not self._enabled:
            return
        for folder_id, entry in list(self._entries.items()):
            if self._entries.get(folder_id) is not entry:
                continue  # removed (or replaced) since the snapshot
            if entry.state != "unavailable":
                continue
            live = sum(
                1 for e in self._entries.values() if e.task is not None and not e.task.done()
            )
            if live >= self._max_watched:
                continue
            entry.stop = threading.Event()
            entry.queue = asyncio.Queue()
            entry.state = "starting"
            entry.error = None
            self._start_entry(folder_id, entry)

    # ── whole-manager lifecycle ──────────────────────────────────────────

    async def _subscribe_all_folders(self) -> None:
        conn = await self._conn_factory()
        kb_repo = KnowledgeBaseRepository(conn)
        item_repo = KBItemRepository(conn)
        for kb in await kb_repo.list():
            for folder in await item_repo.list_folders(kb.id):
                self.start(kb.id, folder)

    async def _disable_locked(self) -> None:
        for timer in list(self._timers.values()):
            timer.cancel()
        self._timers.clear()
        self._timer_first_event.clear()
        await asyncio.gather(
            *(self.stop(folder_id) for folder_id in list(self._entries)), return_exceptions=True
        )

    async def _apply_locked(self, m: MonitoringSettings) -> None:
        self._enabled = m.watch_enabled
        # The reconcile loop runs whether or not the watcher is enabled
        # (DD-4) — it is the only way changes are reflected when it is off.
        self._ensure_reconcile_task()
        if self._enabled:
            await self._subscribe_all_folders()
        else:
            await self._disable_locked()

    async def start_all(self) -> None:
        """Lifespan startup (DD-7): load settings, start the reconcile
        loop, and (if enabled) subscribe every folder of every knowledge
        base. Idempotent — a second call changes nothing, since ``start``
        no-ops on a live task and the reconcile task is only (re)created
        when absent or done."""
        async with self._lifecycle_lock:
            m = await self._load_settings()
            await self._apply_locked(m)

    async def apply_settings(self, m: MonitoringSettings) -> None:
        """Live-apply a settings change (DD-5): disabled -> stop and
        forget every entry and cancel every timer; enabled -> subscribe
        every folder of every knowledge base. Always wakes the reconcile
        loop so a changed interval applies immediately rather than after
        one old interval. Runs under the same lock as ``start_all`` and
        ``drain`` so two concurrent calls cannot interleave a disable
        with an enable."""
        async with self._lifecycle_lock:
            await self._apply_locked(m)
        self._settings_changed.set()

    async def drain(self) -> None:
        """Shutdown (DD-7): cancel every armed timer, cancel the
        reconcile loop, then stop every entry concurrently (each bounded
        by ``drain_timeout``)."""
        async with self._lifecycle_lock:
            for timer in list(self._timers.values()):
                timer.cancel()
            self._timers.clear()
            self._timer_first_event.clear()
            if self._reconcile_task is not None:
                self._reconcile_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._reconcile_task
                self._reconcile_task = None
            await asyncio.gather(
                *(self.stop(folder_id) for folder_id in list(self._entries)), return_exceptions=True
            )


_manager: WatchManager | None = None


def set_manager(manager: WatchManager | None) -> None:
    """Install the application :class:`WatchManager`. Lifespan-only."""
    global _manager
    _manager = manager


def get_manager() -> WatchManager | None:
    """Return the running :class:`WatchManager`, or ``None`` pre-startup."""
    return _manager
