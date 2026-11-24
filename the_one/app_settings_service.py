"""The app-settings write service (Mission 36 Flight 5 Leg 4a, DD3, DD8).

The two app-wide settings pages GleepGlorp may propose changes to, as writes the routes and the
approve path share:

- **Date and time:** the ``time_zone`` record (``mode`` and ``zone``), validated by
  :class:`the_one.time_zones.TimeZoneSetting`;
- **Knowledge indexing:** the ``knowledge.chunking`` and ``knowledge.monitoring`` records.
  The embedding record and the vector store are fixed and never written here.

The routes stay thin (they keep their own body guards and one-sentence error mapping) and call
:func:`save_time_setting`. A proposal calls :func:`change_time_settings` or
:func:`change_knowledge_settings`, which write **only the records they change**, in one write
transaction, with the status mark riding ``on_commit``.

Post-commit side effects (never inside the transaction, never after a rollback, and never able
to fail a write that has committed, so an applied proposal is never reported as failed): the
scheduler poke after a time change, and the watcher's ``apply_settings`` after a monitoring
change. Both are injected through :class:`AppSettingsWriteDeps`; a raise from one is logged.

This module imports nothing from ``fastapi``, ``the_one.interfaces`` or ``the_one.gleepglorp``,
and keeps ``the_one.db.repositories`` out of its module-level imports (an ``ast`` test pins both).
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import aiosqlite
from pydantic import ValidationError

from the_one import time_zones
from the_one.agent.write_checks import validation_detail
from the_one.db._write_lock import write_transaction
from the_one.knowledge.settings import (
    CHUNKING_KEY,
    MONITORING_KEY,
    ChunkingSettings,
    KnowledgeSettings,
    MonitoringSettings,
    load_knowledge_settings,
)

logger = logging.getLogger(__name__)

OnCommit = Callable[[aiosqlite.Connection], Awaitable[None]]

#: The model-facing field -> ``(record, stored key)`` of each Knowledge indexing field.
KNOWLEDGE_FIELDS: dict[str, tuple[str, str]] = {
    "chunk_size_chars": ("chunking", "size_chars"),
    "chunk_overlap_chars": ("chunking", "overlap_chars"),
    "watch_enabled": ("monitoring", "watch_enabled"),
    "reconcile_interval_seconds": ("monitoring", "reconcile_interval_seconds"),
}
#: The model-facing field -> the ``TimeZoneSetting`` attribute of each Date and time field.
TIME_FIELDS: dict[str, str] = {"time_zone_mode": "mode", "time_zone": "zone"}


class AppSettingsWriteError(Exception):
    """A refused app-settings write: an HTTP-shaped ``status`` and ``detail``. It carries no
    HTTP type."""

    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(f"{status}: {detail!r}")
        self.status = status
        self.detail = detail

    @property
    def items(self) -> list[dict[str, Any]]:
        """``[{loc, msg}]`` for the approve path."""
        if isinstance(self.detail, list):
            out: list[dict[str, Any]] = []
            for d in self.detail:
                if isinstance(d, dict):
                    loc = [x if isinstance(x, (str, int)) else str(x) for x in d.get("loc", [])]
                    out.append({"loc": loc, "msg": str(d.get("msg", ""))})
                else:
                    out.append({"loc": [], "msg": str(d)})
            return out
        return [{"loc": [], "msg": str(self.detail)}]


class AppSettingsStaleError(Exception):
    """A touched field's stored value differs from the ``base`` the change was written
    against. ``fields`` is ``[{"field", "current", "proposed"}]``."""

    def __init__(self, fields: list[dict[str, Any]]) -> None:
        super().__init__("stale: " + ", ".join(str(f["field"]) for f in fields))
        self.fields = fields


@dataclass(frozen=True)
class AppSettingsWriteDeps:
    """What an app-settings write needs: the shared connection and the two post-commit hooks
    (``poke`` wakes the routine scheduler; ``apply_monitoring`` applies a saved monitoring
    change to the folder watcher live)."""

    conn: aiosqlite.Connection
    poke: Callable[[], Any]
    apply_monitoring: Callable[[MonitoringSettings], Awaitable[None]]


async def _after_commit(label: str, hook: Callable[[], Any]) -> None:
    """Run a post-commit hook; a raise is logged and never propagates (the write committed)."""
    try:
        result = hook()
        if inspect.isawaitable(result):
            await result
    except Exception:  # noqa: BLE001 - a committed write is never failed by its side effect
        logger.warning("app settings: the %s hook failed after the write", label, exc_info=True)


def _set_in_txn() -> Callable[[aiosqlite.Connection, str, str], Awaitable[None]]:
    from the_one.db.repositories import AppMetadataRepository

    return AppMetadataRepository.set_in_txn


def _stale(
    current: dict[str, Any], changes: dict[str, Any], base: dict[str, Any]
) -> list[dict[str, Any]]:
    """The touched fields whose stored value is not the ``base`` value."""
    out: list[dict[str, Any]] = []
    for key, proposed in changes.items():
        if key not in current:
            continue
        if key not in base or current[key] != base[key]:
            out.append({"field": key, "current": current[key], "proposed": proposed})
    return out


# --- Date and time ------------------------------------------------------------------------


def time_values(setting: time_zones.TimeZoneSetting) -> dict[str, Any]:
    """The Date and time fields' stored values, by model-facing name."""
    return {"time_zone_mode": setting.mode, "time_zone": setting.zone}


async def save_time_setting(
    deps: AppSettingsWriteDeps, setting: time_zones.TimeZoneSetting
) -> None:
    """The route's write: the record, in one transaction, then the scheduler poke."""
    async with write_transaction(deps.conn):
        await _set_in_txn()(deps.conn, time_zones.SETTING_KEY, setting.model_dump_json())
    await _after_commit("scheduler poke", deps.poke)


async def change_time_settings(
    deps: AppSettingsWriteDeps,
    changes: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
    override: bool = False,
    on_commit: OnCommit | None = None,
) -> time_zones.TimeZoneSetting:
    """Apply a proposal's ``time_zone_mode`` and/or ``time_zone`` to the stored setting, inside
    one write transaction. ``base`` is compared on the setting read inside the transaction
    unless ``override``: a mismatch raises :class:`AppSettingsStaleError` and nothing is
    written. The scheduler is poked after the commit. Returns the written setting."""
    async with write_transaction(deps.conn):
        current = await time_zones.load_setting(deps.conn)
        if not override and base is not None:
            stale = _stale(time_values(current), changes, base)
            if stale:
                raise AppSettingsStaleError(stale)
        merged = {"mode": current.mode, "zone": current.zone}
        for key, attr in TIME_FIELDS.items():
            if key in changes:
                merged[attr] = changes[key]
        try:
            setting = time_zones.TimeZoneSetting.model_validate(merged)
        except ValidationError as e:
            raise AppSettingsWriteError(422, validation_detail(e)) from None
        await _set_in_txn()(deps.conn, time_zones.SETTING_KEY, setting.model_dump_json())
        if on_commit is not None:
            await on_commit(deps.conn)
    await _after_commit("scheduler poke", deps.poke)
    return setting


# --- Knowledge indexing -------------------------------------------------------------------


def knowledge_values(current: KnowledgeSettings) -> dict[str, Any]:
    """The Knowledge indexing fields' stored values, by model-facing name."""
    out: dict[str, Any] = {}
    for name, (record, key) in KNOWLEDGE_FIELDS.items():
        out[name] = getattr(getattr(current, record), key)
    return out


async def change_knowledge_settings(
    deps: AppSettingsWriteDeps,
    changes: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
    override: bool = False,
    on_commit: OnCommit | None = None,
) -> KnowledgeSettings:
    """Apply a proposal's Knowledge indexing fields, inside one write transaction.

    Only the records a field belongs to are written (``knowledge.chunking`` and/or
    ``knowledge.monitoring``); the embedding record is never touched. ``base`` is compared on
    the settings read inside the transaction unless ``override``: a mismatch raises
    :class:`AppSettingsStaleError` and nothing is written. After the commit, a monitoring change
    is applied to the folder watcher. Returns the written settings."""
    touched = {KNOWLEDGE_FIELDS[k][0] for k in changes if k in KNOWLEDGE_FIELDS}
    async with write_transaction(deps.conn):
        current = await load_knowledge_settings(deps.conn)
        if not override and base is not None:
            stale = _stale(knowledge_values(current), changes, base)
            if stale:
                raise AppSettingsStaleError(stale)
        chunking = current.chunking.model_dump()
        monitoring = current.monitoring.model_dump()
        records = {"chunking": chunking, "monitoring": monitoring}
        for name, (record, key) in KNOWLEDGE_FIELDS.items():
            if name in changes:
                records[record][key] = changes[name]
        try:
            updated = KnowledgeSettings(
                embedding=current.embedding,
                chunking=ChunkingSettings.model_validate(chunking),
                monitoring=MonitoringSettings.model_validate(monitoring),
            )
        except ValidationError as e:
            raise AppSettingsWriteError(422, validation_detail(e)) from None
        set_in_txn = _set_in_txn()
        if "chunking" in touched:
            await set_in_txn(deps.conn, CHUNKING_KEY, updated.chunking.model_dump_json())
        if "monitoring" in touched:
            await set_in_txn(deps.conn, MONITORING_KEY, updated.monitoring.model_dump_json())
        if on_commit is not None:
            await on_commit(deps.conn)
    if "monitoring" in touched:
        await _after_commit("folder watcher", lambda: deps.apply_monitoring(updated.monitoring))
    return updated
