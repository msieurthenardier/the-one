"""The app-settings write service and its repository setter (Mission 36 F5 L4a, DD3, DD8).

``AppMetadataRepository.set_in_txn``, ``save_knowledge_settings`` in one transaction, and the
Date and time and Knowledge indexing changes in ``the_one/app_settings_service.py``: only the
records changed are written, one transaction, the status mark rides ``on_commit``, the post-commit
hooks never run after a refusal and never fail a committed write, and the import boundary.
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests._schema_template import connect_template_db
from the_one import app_settings_service as svc
from the_one import time_zones
from the_one.db import _write_lock
from the_one.db._write_lock import write_transaction
from the_one.db.repositories import AppMetadataRepository
from the_one.knowledge.settings import (
    CHUNKING_KEY,
    EMBEDDING_KEY,
    MONITORING_KEY,
    ChunkingSettings,
    EmbeddingSettings,
    KnowledgeSettings,
    MonitoringSettings,
    load_knowledge_settings,
    save_knowledge_settings,
)

ROOT = Path(__file__).resolve().parent.parent

# Stored with spaces, so a rewrite (which dumps compact JSON) is visible byte for byte.
RAW_EMBEDDING = json.dumps(EmbeddingSettings().model_dump(), indent=1)
RAW_CHUNKING = json.dumps({"size_chars": 800, "overlap_chars": 100}, indent=1)
RAW_MONITORING = json.dumps({"watch_enabled": True, "reconcile_interval_seconds": 600}, indent=1)


@pytest.fixture
async def world(tmp_path):
    _write_lock.reset_for_test()
    conn = await connect_template_db(tmp_path / "as.db")
    repo = AppMetadataRepository(conn)
    await repo.set(EMBEDDING_KEY, RAW_EMBEDDING)
    await repo.set(CHUNKING_KEY, RAW_CHUNKING)
    await repo.set(MONITORING_KEY, RAW_MONITORING)
    calls = SimpleNamespace(poke=0, monitoring=[], boom=False)

    def poke() -> None:
        calls.poke += 1

    async def apply_monitoring(monitoring) -> None:
        calls.monitoring.append(monitoring)
        if calls.boom:
            raise RuntimeError("watcher down")

    deps = svc.AppSettingsWriteDeps(conn=conn, poke=poke, apply_monitoring=apply_monitoring)
    yield SimpleNamespace(conn=conn, repo=repo, deps=deps, calls=calls)
    await conn.close()


async def raw(world, key):
    return await world.repo.get(key)


# --- the import boundary --------------------------------------------------------------------


def test_the_service_imports_no_interface_layer_and_no_repository_at_module_level() -> None:
    tree = ast.parse((ROOT / "the_one" / "app_settings_service.py").read_text())
    banned = ("fastapi", "starlette", "the_one.interfaces", "the_one.gleepglorp")
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        assert not any(n == b or n.startswith(b + ".") for n in names for b in banned), names
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert "repositories" not in (getattr(node, "module", "") or ""), node.lineno


# --- the setter and the one-transaction save -----------------------------------------------


async def test_set_in_txn_writes_inside_an_open_transaction(world) -> None:
    async with write_transaction(world.conn):
        await AppMetadataRepository.set_in_txn(world.conn, "k1", "v1")
        await AppMetadataRepository.set_in_txn(world.conn, "k1", "v2")
    assert await raw(world, "k1") == "v2"


async def test_save_knowledge_settings_writes_all_three_records_in_one_transaction(
    world, monkeypatch
) -> None:
    current = await load_knowledge_settings(world.conn)
    updated = KnowledgeSettings(
        embedding=current.embedding,
        chunking=ChunkingSettings(size_chars=900, overlap_chars=90),
        monitoring=MonitoringSettings(watch_enabled=False, reconcile_interval_seconds=60),
    )
    await save_knowledge_settings(world.conn, updated)
    assert (await load_knowledge_settings(world.conn)) == updated
    # a failure part-way leaves none of the three written
    calls = []
    real = AppMetadataRepository.set_in_txn

    async def flaky(conn, key, value):
        calls.append(key)
        if len(calls) == 3:
            raise RuntimeError("disk full")
        await real(conn, key, value)

    monkeypatch.setattr(AppMetadataRepository, "set_in_txn", staticmethod(flaky))
    again = updated.model_copy(update={"chunking": ChunkingSettings(size_chars=1200)})
    with pytest.raises(RuntimeError):
        await save_knowledge_settings(world.conn, again)
    monkeypatch.setattr(AppMetadataRepository, "set_in_txn", staticmethod(real))
    assert (await load_knowledge_settings(world.conn)) == updated


# --- Knowledge indexing ---------------------------------------------------------------------


async def test_a_change_writes_only_the_records_it_changes_and_never_the_embedding(world) -> None:
    out = await svc.change_knowledge_settings(world.deps, {"chunk_size_chars": 1000})
    assert out.chunking.size_chars == 1000 and out.chunking.overlap_chars == 100
    assert json.loads(await raw(world, CHUNKING_KEY)) == {"size_chars": 1000, "overlap_chars": 100}
    # untouched keys are not rewritten: byte for byte
    assert await raw(world, EMBEDDING_KEY) == RAW_EMBEDDING
    assert await raw(world, MONITORING_KEY) == RAW_MONITORING
    # a chunking-only change never touches the watcher
    assert world.calls.monitoring == [] and world.calls.poke == 0


async def test_a_monitoring_change_applies_to_the_watcher_after_the_commit(world) -> None:
    out = await svc.change_knowledge_settings(
        world.deps, {"watch_enabled": False, "reconcile_interval_seconds": 30}
    )
    assert out.monitoring.watch_enabled is False
    assert world.calls.monitoring == [out.monitoring]
    assert await raw(world, CHUNKING_KEY) == RAW_CHUNKING
    assert json.loads(await raw(world, MONITORING_KEY)) == {
        "watch_enabled": False,
        "reconcile_interval_seconds": 30,
    }


async def test_both_records_commit_together_or_not_at_all(world) -> None:
    async def mark(conn) -> None:
        raise RuntimeError("mark")

    with pytest.raises(RuntimeError):
        await svc.change_knowledge_settings(
            world.deps, {"chunk_size_chars": 1000, "watch_enabled": False}, on_commit=mark
        )
    assert await raw(world, CHUNKING_KEY) == RAW_CHUNKING
    assert await raw(world, MONITORING_KEY) == RAW_MONITORING
    assert world.calls.monitoring == []  # never after a rollback


async def test_a_stale_change_writes_nothing_and_runs_no_hook(world) -> None:
    base = {"chunk_size_chars": 800, "watch_enabled": True}
    await world.repo.set(CHUNKING_KEY, json.dumps({"size_chars": 700, "overlap_chars": 100}))
    marks = []

    async def mark(conn) -> None:
        marks.append(1)

    with pytest.raises(svc.AppSettingsStaleError) as e:
        await svc.change_knowledge_settings(
            world.deps, {"chunk_size_chars": 900, "watch_enabled": False}, base=base, on_commit=mark
        )
    assert e.value.fields == [{"field": "chunk_size_chars", "current": 700, "proposed": 900}]
    assert marks == [] and world.calls.monitoring == []
    assert await raw(world, MONITORING_KEY) == RAW_MONITORING
    # another field moving is not stale; override writes
    out = await svc.change_knowledge_settings(
        world.deps, {"watch_enabled": False}, base={"watch_enabled": True}
    )
    assert out.monitoring.watch_enabled is False
    await svc.change_knowledge_settings(
        world.deps, {"chunk_size_chars": 900}, base=base, override=True, on_commit=mark
    )
    assert marks == [1]


async def test_a_validation_failure_is_a_422_and_writes_nothing(world) -> None:
    with pytest.raises(svc.AppSettingsWriteError) as e:
        await svc.change_knowledge_settings(world.deps, {"chunk_overlap_chars": 500})
    assert e.value.status == 422 and e.value.items
    assert await raw(world, CHUNKING_KEY) == RAW_CHUNKING


async def test_a_raising_hook_is_logged_and_never_fails_the_committed_write(world, caplog) -> None:
    world.calls.boom = True
    with caplog.at_level(logging.WARNING, logger="the_one.app_settings_service"):
        out = await svc.change_knowledge_settings(world.deps, {"watch_enabled": False})
    assert out.monitoring.watch_enabled is False
    assert json.loads(await raw(world, MONITORING_KEY))["watch_enabled"] is False
    assert any("folder watcher" in r.getMessage() for r in caplog.records)


# --- Date and time --------------------------------------------------------------------------


async def test_save_time_setting_writes_one_record_and_pokes(world) -> None:
    setting = time_zones.TimeZoneSetting(mode="zone", zone="Asia/Tokyo")
    await svc.save_time_setting(world.deps, setting)
    assert (await time_zones.load_setting(world.conn)) == setting
    assert world.calls.poke == 1


async def test_a_time_change_merges_over_the_stored_setting_and_pokes_after_the_commit(
    world,
) -> None:
    await time_zones.save_setting(
        world.conn, time_zones.TimeZoneSetting(mode="zone", zone="Europe/Paris")
    )
    out = await svc.change_time_settings(world.deps, {"time_zone": "Asia/Tokyo"})
    assert (out.mode, out.zone) == ("zone", "Asia/Tokyo") and world.calls.poke == 1
    out = await svc.change_time_settings(world.deps, {"time_zone_mode": "system"})
    assert (out.mode, out.zone) == ("system", "Asia/Tokyo")  # the model keeps the zone
    assert world.calls.poke == 2


async def test_a_stale_or_refused_time_change_pokes_nothing(world) -> None:
    await time_zones.save_setting(
        world.conn, time_zones.TimeZoneSetting(mode="zone", zone="Europe/Paris")
    )
    with pytest.raises(svc.AppSettingsStaleError):
        await svc.change_time_settings(
            world.deps, {"time_zone": "Asia/Tokyo"}, base={"time_zone": "America/Denver"}
        )
    with pytest.raises(svc.AppSettingsWriteError):
        await svc.change_time_settings(world.deps, {"time_zone": "Not/AZone"})

    async def mark(conn) -> None:
        raise RuntimeError("mark")

    with pytest.raises(RuntimeError):
        await svc.change_time_settings(world.deps, {"time_zone": "Asia/Tokyo"}, on_commit=mark)
    assert world.calls.poke == 0
    assert (await time_zones.load_setting(world.conn)).zone == "Europe/Paris"


async def test_a_raising_poke_never_fails_a_committed_time_change(world, caplog) -> None:
    def poke() -> None:
        raise RuntimeError("no scheduler")

    deps = svc.AppSettingsWriteDeps(
        conn=world.conn, poke=poke, apply_monitoring=world.deps.apply_monitoring
    )
    with caplog.at_level(logging.WARNING, logger="the_one.app_settings_service"):
        out = await svc.change_time_settings(deps, {"time_zone": "Asia/Tokyo"})
    assert out.zone == "Asia/Tokyo"
    assert any("scheduler poke" in r.getMessage() for r in caplog.records)
