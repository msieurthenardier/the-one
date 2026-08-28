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

import logging as _logging
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


@pytest.fixture(autouse=True)
async def _connector_pool_cleanup():
    """M10 F8 L11 HAT Fix #6: connector-pool tests in this file
    exercise the lifespan warm-acquire and leave entries in the
    module-level ``_pool`` dict. Clear after every test to avoid
    cross-test bleed.
    """
    from the_one.connectors._pool import _clear_for_test as _clear_connector_pool
    from the_one.connectors._stub import StubPlugin
    from the_one.connectors.registry import clear_for_test as _clear_registry

    StubPlugin.reset_for_test()
    yield
    await _clear_connector_pool()
    _clear_registry()
    StubPlugin.reset_for_test()


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


async def test_lifespan_warm_acquires_connectors_per_account(
    _isolated_data_dir,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M10 F8 L11 HAT Fix #6: lifespan warm-acquire walks connector
    accounts (not agents). With N agents attached to one connector
    account, ``account_acquire`` is called ONCE per account — yielding
    one gateway connection per bot. Pre-Fix-#6 the warm-acquire picked
    the "first alphabetical attached agent" and used the bare
    ``acquire(agent_name, account_id)``; with multiple agents that
    keying would still have produced one warm-acquire per account, but
    the dispatcher/tool/auto-relay paths would each create separate
    pool entries on first call — Fix #6 routes all paths through
    ``account_acquire`` so the warm entry is reused.

    This test sets up TWO agents attached to one connector account,
    spies on ``account_acquire``, enters the lifespan, and asserts
    one and only one warm-acquire call for the account.
    """
    from the_one.agent.config import AgentConfig
    from the_one.connectors import _pool as pool_mod
    from the_one.connectors._stub import StubPlugin
    from the_one.connectors.registry import register_for_test
    from the_one.db.connection import get_connection
    from the_one.db.models import Connector, LLMProviderConfig
    from the_one.db.repositories import (
        ConnectorRepository,
        LLMProviderRepository,
        SQLiteAgentStore,
    )
    from the_one.db.schema import ensure_schema
    from the_one.encryption import get_encryptor

    # Register the stub plugin so the warm-acquire's plugin.connect
    # resolves to something benign.
    register_for_test("stub", StubPlugin)

    # Pre-seed the DB before lifespan startup. The lifespan calls
    # init_db internally — but ensure_schema is idempotent, so we can
    # seed first and let the lifespan re-run ensure_schema harmlessly.
    from the_one.config import settings as _settings

    conn = await get_connection()
    await ensure_schema(conn)
    encryptor = get_encryptor(_settings.data_dir)

    # Seed account.
    acc_repo = ConnectorRepository(conn, encryptor)
    await acc_repo.create(
        Connector(
            id="acct-warm",
            name="Warm Account",
            type="stub",
            config={},
            secrets={},
        )
    )
    # Seed provider + two agents attached to the same account.
    provider_repo = LLMProviderRepository(conn, encryptor)
    await provider_repo.create(
        LLMProviderConfig(
            id="mock-provider",
            name="Mock Provider",
            type="mock",
            base_url="",
            config={"response": {"content": "ok"}},
        )
    )
    agent_store = SQLiteAgentStore(conn)
    for name in ("alpha", "bravo"):
        await agent_store.save(
            AgentConfig(
                name=name,
                provider_config_id="mock-provider",
                llm_model="mock-default",
                connector_ids=["acct-warm"],
            )
        )

    # Spy on account_acquire. The lifespan does a function-local
    # import (``from the_one.connectors._pool import account_acquire``)
    # at call time — so we patch the function on the module, which the
    # local import resolves to.
    acquire_calls: list[str] = []
    original_account_acquire = pool_mod.account_acquire

    async def _spying_acquire(account_id: str):
        acquire_calls.append(account_id)
        return await original_account_acquire(account_id)

    monkeypatch.setattr(pool_mod, "account_acquire", _spying_acquire)

    from the_one.interfaces.web.app import app, lifespan

    async with lifespan(app):
        # Inside the lifespan: warm-acquire should have fired exactly
        # once for the account, regardless of how many agents are
        # attached.
        assert acquire_calls == ["acct-warm"], acquire_calls
        # Pool reflects one sentinel-keyed entry.
        keys_for_account = [k for k in pool_mod._pool if k[1] == "acct-warm"]
        assert len(keys_for_account) == 1
        assert keys_for_account[0] == (
            pool_mod._ACCOUNT_POOL_AGENT_SLOT,
            "acct-warm",
        )

    # After lifespan exit the connector pool was drained.
    assert all(k[1] != "acct-warm" for k in pool_mod._pool)


async def test_lifespan_warm_acquire_skips_accounts_with_no_attached_agents(
    _isolated_data_dir,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M10 F8 L11 HAT Fix #6: lifespan policy preserves the
    skip-when-unattached behaviour — an account with no attached
    agents does NOT get a warm-acquire (no point warming a gateway
    that no agent will route through).
    """
    from the_one.connectors import _pool as pool_mod
    from the_one.connectors._stub import StubPlugin
    from the_one.connectors.registry import register_for_test
    from the_one.db.connection import get_connection
    from the_one.db.models import Connector
    from the_one.db.repositories import ConnectorRepository
    from the_one.db.schema import ensure_schema
    from the_one.encryption import get_encryptor

    register_for_test("stub", StubPlugin)

    from the_one.config import settings as _settings

    conn = await get_connection()
    await ensure_schema(conn)
    encryptor = get_encryptor(_settings.data_dir)

    acc_repo = ConnectorRepository(conn, encryptor)
    await acc_repo.create(
        Connector(
            id="acct-orphan",
            name="Orphan Account",
            type="stub",
            config={},
            secrets={},
        )
    )

    acquire_calls: list[str] = []
    original_account_acquire = pool_mod.account_acquire

    async def _spying_acquire(account_id: str):
        acquire_calls.append(account_id)
        return await original_account_acquire(account_id)

    monkeypatch.setattr(pool_mod, "account_acquire", _spying_acquire)

    from the_one.interfaces.web.app import app, lifespan

    async with lifespan(app):
        # The unattached account was skipped — no warm-acquire fired.
        assert acquire_calls == [], acquire_calls


# ─────────────────────────────────────────────────────────────────────────────
# M11 F13 L3 — deprecated inference env-var warning
# ─────────────────────────────────────────────────────────────────────────────


async def test_lifespan_warns_on_deprecated_inference_env_vars(
    _isolated_data_dir,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """M11 F13 L3 — when either of the legacy ``THE_ONE_INFERENCE_*``
    env vars is set in the environment at startup, the lifespan emits
    exactly one ``WARNING``-level log line directing the operator to
    the Studio connector editor. The env vars are no longer consumed
    (Settings.inference_* was removed at F13 L3); the warning is a
    one-time-at-startup deprecation surface.
    """
    from the_one.interfaces.web.app import app, lifespan

    monkeypatch.setenv("THE_ONE_INFERENCE_PROVIDER_CONFIG_ID", "p1")
    monkeypatch.delenv("THE_ONE_INFERENCE_MODEL", raising=False)

    with caplog.at_level(_logging.WARNING, logger="the_one.interfaces.web.app"):
        async with lifespan(app):
            pass

    matching = [
        r
        for r in caplog.records
        if r.levelno == _logging.WARNING
        and "THE_ONE_INFERENCE_PROVIDER_CONFIG_ID" in r.getMessage()
    ]
    assert len(matching) == 1, (
        "expected exactly one F13 L3 deprecation warning when "
        "THE_ONE_INFERENCE_PROVIDER_CONFIG_ID is set in the "
        f"environment; saw {len(matching)} matches in "
        f"{[r.getMessage() for r in caplog.records]}"
    )


async def test_lifespan_does_not_warn_when_inference_env_vars_unset(
    _isolated_data_dir,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """M11 F13 L3 — when neither legacy env var is set, the lifespan
    does NOT emit the deprecation warning. Verifies the warning is
    silent in the common (post-cleanup) case.
    """
    from the_one.interfaces.web.app import app, lifespan

    monkeypatch.delenv("THE_ONE_INFERENCE_PROVIDER_CONFIG_ID", raising=False)
    monkeypatch.delenv("THE_ONE_INFERENCE_MODEL", raising=False)

    with caplog.at_level(_logging.WARNING, logger="the_one.interfaces.web.app"):
        async with lifespan(app):
            pass

    matching = [
        r
        for r in caplog.records
        if r.levelno == _logging.WARNING
        and (
            "THE_ONE_INFERENCE_PROVIDER_CONFIG_ID" in r.getMessage()
            or "THE_ONE_INFERENCE_MODEL" in r.getMessage()
        )
    ]
    assert len(matching) == 0, (
        "expected zero F13 L3 deprecation warnings when both legacy "
        "env vars are unset; saw "
        f"{[r.getMessage() for r in matching]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# M11 F17 L4 — (B-boot) boot warm-up: connector WITH attached agent is acquired
# ─────────────────────────────────────────────────────────────────────────────


async def test_lifespan_warms_connector_with_attached_agent(
    _isolated_data_dir,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11 F17 L4 (B-boot): a connector account WITH ≥1 attached agent
    is warm-acquired via ``account_acquire`` at lifespan startup — the
    gateway connects automatically, no manual Test Connection required.

    Focuses specifically on the ≥1-attached-agent criterion that drives
    the lifespan warmup policy (``app.py:152-158``): the acquire fires
    for this connector because an agent is attached.
    """
    from the_one.agent.config import AgentConfig
    from the_one.config import settings as _settings
    from the_one.connectors import _pool as pool_mod
    from the_one.connectors._stub import StubPlugin
    from the_one.connectors.registry import register_for_test
    from the_one.db.connection import get_connection
    from the_one.db.models import Connector, LLMProviderConfig
    from the_one.db.repositories import (
        ConnectorRepository,
        LLMProviderRepository,
        SQLiteAgentStore,
    )
    from the_one.db.schema import ensure_schema
    from the_one.encryption import get_encryptor

    register_for_test("stub", StubPlugin)
    StubPlugin.reset_for_test()

    conn = await get_connection()
    await ensure_schema(conn)
    encryptor = get_encryptor(_settings.data_dir)

    # Seed one connector account.
    acc_repo = ConnectorRepository(conn, encryptor)
    await acc_repo.create(
        Connector(
            id="acct-boot",
            name="Boot Account",
            type="stub",
            config={},
            secrets={},
        )
    )
    # Seed provider + one attached agent.
    provider_repo = LLMProviderRepository(conn, encryptor)
    await provider_repo.create(
        LLMProviderConfig(
            id="mock-boot-provider",
            name="Mock Boot Provider",
            type="mock",
            base_url="",
            config={"response": {"content": "ok"}},
        )
    )
    agent_store = SQLiteAgentStore(conn)
    await agent_store.save(
        AgentConfig(
            name="boot-agent",
            provider_config_id="mock-boot-provider",
            llm_model="mock-default",
            connector_ids=["acct-boot"],
        )
    )

    from the_one.interfaces.web.app import app, lifespan

    async with lifespan(app):
        # The account-keyed sentinel entry must be warm after startup.
        account_key = (pool_mod._ACCOUNT_POOL_AGENT_SLOT, "acct-boot")
        assert account_key in pool_mod._pool, (
            "Expected warm pool entry for connector with attached agent; "
            f"pool keys = {list(pool_mod._pool.keys())}"
        )
        entry = pool_mod._pool[account_key]
        assert entry.client is not None, "Entry client must be populated (gateway connected)"


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
