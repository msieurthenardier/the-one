"""FastAPI lifespan integration tests.

Verifies that the PTY session registry is drained on shutdown — the
``shutdown_drain`` hook wired into ``the_one.interfaces.web.app.lifespan``
must cancel the reaper task and close any live sessions before the DB
connection closes.

Pattern: enter ``lifespan(app)`` directly via ``async with``. The
codebase's async-test idiom is ``httpx.AsyncClient + ASGITransport``
(see ``tests/test_db_api.py`` and ``tests/test_provider_api.py``); we
don't need HTTP routing here, but the lifespan context manager itself
runs the ``init_db`` + ``migrate_json_to_sqlite`` startup tasks, which
need a writable data dir.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from the_one.platform.pty import PtySession

# Every test in this module drives the real ``lifespan(app)`` through
# startup AND shutdown — reset the module-global shutdown latches after
# each so a later test's register()/acquire() doesn't see a stale
# "shutting down" state (see the fixture's docstring in conftest.py).
pytestmark = pytest.mark.usefixtures("reset_lifespan_singletons")


class _MockPtySession(PtySession):
    """In-memory ``PtySession`` for the lifespan drain test."""

    def __init__(self) -> None:
        self._alive = True
        self._last_activity = time.monotonic()
        self.close_count = 0

    async def start(self) -> None:  # pragma: no cover — unused here
        pass

    async def send(self, input: str, timeout: float = 30.0) -> bytes:  # noqa: A002
        return b""

    async def close(self) -> None:
        self.close_count += 1
        self._alive = False

    @property
    def is_alive(self) -> bool:
        return self._alive

    @property
    def last_activity(self) -> float:
        return self._last_activity


@pytest.fixture(autouse=True)
async def _registry_cleanup():
    """Reset registry state before AND after each test.

    Before: any earlier test that drives the real app lifespan to
    shutdown (e.g. ``with TestClient(app):``) latches the module-global
    ``_shutting_down = True``, and ``register()`` then raises
    ``RuntimeError: session registry is shutting down`` (the M17 F1 L4
    ordering flake). The offending modules now reset after themselves
    via the conftest ``reset_lifespan_singletons`` fixture; the pre-test
    clear here is defense in depth so this module never depends on
    suite ordering.

    After: in case the lifespan path didn't fully drain.
    """
    from the_one.tools._session_registry import _clear_for_test

    await _clear_for_test()
    yield
    await _clear_for_test()


@pytest.fixture
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the global ``settings`` at a tmp data dir AND reset the
    db-connection singleton so the lifespan's ``init_db`` /
    ``migrate_json_to_sqlite`` start with a clean slate.

    ``Settings`` reads env vars at import time (module-level instance),
    so ``setenv`` alone is insufficient — we have to mutate the live
    ``settings.data_dir`` field.
    """
    from the_one.config import settings
    from the_one.db import connection as db_connection

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    # The DB singleton may already be open from a prior test; force
    # reconnect against the new path.
    monkeypatch.setattr(db_connection, "_connection", None)
    yield tmp_path
    # Best-effort: close any connection the lifespan opened so the next
    # test's ``init_db`` reopens against a fresh path.
    monkeypatch.setattr(db_connection, "_connection", None)


async def test_lifespan_drains_session_registry(_isolated_data_dir) -> None:
    """Sessions registered inside the lifespan context are closed on
    exit, and the reaper task is cancelled."""
    from the_one.interfaces.web.app import app, lifespan
    from the_one.tools import _session_registry as reg
    from the_one.tools._session_registry import (
        count_for_agent,
        new_session_id,
        register,
    )

    sessions = [_MockPtySession() for _ in range(3)]

    async with lifespan(app):
        for session in sessions:
            await register("test-agent", new_session_id(), session, ttl_seconds=300)
        assert await count_for_agent("test-agent") == 3
        assert reg._reaper_task is not None

    # After lifespan exit:
    # - Every session was closed.
    # - Registry is empty (drained).
    # - Reaper task was cancelled and reset to None.
    for session in sessions:
        assert session.close_count == 1
    assert await count_for_agent("test-agent") == 0
    assert reg._reaper_task is None


async def test_lifespan_drain_with_no_sessions_is_clean(
    _isolated_data_dir,
) -> None:
    """Lifespan exit with no sessions / no reaper must not raise."""
    from the_one.interfaces.web.app import app, lifespan
    from the_one.tools import _session_registry as reg

    async with lifespan(app):
        # Don't register anything.
        assert reg._reaper_task is None

    # Still clean afterward.
    assert reg._reaper_task is None


# Mission 23 Flight 1 (backend-removal leg): the connector warm-acquire
# tests (test_lifespan_warm_acquires_connectors_per_account,
# test_lifespan_warm_acquire_skips_accounts_with_no_attached_agents,
# test_lifespan_warms_connector_with_attached_agent) and the deprecated-
# inference-env-var-warning tests
# (test_lifespan_warns_on_deprecated_inference_env_vars,
# test_lifespan_does_not_warn_when_inference_env_vars_unset) are deleted:
# DD-8 removes the lifespan's connector warm-acquire block and stub-
# plugin registration entirely, and the legacy
# THE_ONE_INFERENCE_PROVIDER_CONFIG_ID / THE_ONE_INFERENCE_MODEL
# deprecation-warning block goes with it (both lived in the same
# connector-adjacent lifespan section). The MCP evict/drain block these
# tests never touched (squawk 0025) is untouched.


# ─────────────────────────────────────────────────────────────────────────────
# M22 F01 L01 — encryption-key rotation sidecar reconcile at startup
# ─────────────────────────────────────────────────────────────────────────────


async def test_lifespan_reconciles_leftover_rotation_sidecar(
    _isolated_data_dir,
) -> None:
    """AC8: a `.next` sidecar leftover from an interrupted rotation, plus
    one provider row already encrypted under it, is promoted by the
    lifespan's startup reconcile — before `SQLiteAgentStore(conn)` (or any
    other encryptor-backed repository) is constructed. On exit from
    startup the canonical key file holds the new key and `.next` is gone.
    """
    from cryptography.fernet import Fernet

    from the_one.config import settings as _settings
    from the_one.db.connection import get_connection
    from the_one.db.models import LLMProviderConfig
    from the_one.db.repositories import LLMProviderRepository
    from the_one.db.schema import ensure_schema
    from the_one.encryption import Encryptor, _encryptor_cache

    tmp_path = _isolated_data_dir
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    (tmp_path / "encryption.key").write_bytes(old_key)
    (tmp_path / "encryption.key.next").write_bytes(new_key)

    conn = await get_connection()
    await ensure_schema(conn)

    # Seed a provider row already re-encrypted under the pending (new) key —
    # simulating a rotation whose commit succeeded before the crash.
    seed_encryptor = Encryptor(new_key)
    provider_repo = LLMProviderRepository(conn, seed_encryptor)
    await provider_repo.create(
        LLMProviderConfig(
            id="lifespan-reconcile-provider",
            name="Lifespan Reconcile Provider",
            type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-lifespanreconcile1234",
        )
    )

    _encryptor_cache.clear()

    from the_one.interfaces.web.app import app, lifespan

    async with lifespan(app):
        assert (tmp_path / "encryption.key").read_bytes() == new_key
        assert not (tmp_path / "encryption.key.next").exists()

    # Still true after shutdown.
    assert (tmp_path / "encryption.key").read_bytes() == new_key
    assert not (tmp_path / "encryption.key.next").exists()
    assert _settings.data_dir == tmp_path
