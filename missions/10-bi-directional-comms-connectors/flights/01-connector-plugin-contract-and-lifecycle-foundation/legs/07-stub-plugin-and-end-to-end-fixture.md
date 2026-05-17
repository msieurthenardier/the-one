# Leg: stub-plugin-and-end-to-end-fixture

**Status**: landed
**Flight**: [Connector Plugin Contract and Lifecycle Foundation](../flight.md)

## Objective

Create `the_one/connectors/_stub.py` — the in-process stub plugin + client that satisfies the connector contract end-to-end, with recording buffers and scenario knobs. Create `tests/test_connectors_e2e.py` with the **regression-baseline test** that Flights 2-10 inherit: register → save → acquire → simulate inbound → drive outbound recording → reaper evict → shutdown drain.

## Context

This is leg 7 of Flight 1 of Mission 10. Legs 1-6 landed the persistence floor (1-2), the protocol contract (3), the registry (4), and the lifecycle pool (5-6). This leg lands the **test fixture and regression baseline** that exercises every layer end-to-end without invoking any real platform API. Subsequent flights (Flight 2 admin REST, Flight 3 session model, Flight 4 platform-send tool, etc.) re-use this stub plugin in their own tests.

### Stub plugin scope

The stub at `the_one/connectors/_stub.py` is the **rich** stub — it has class-level recording buffers, scenario knobs (doctor outcomes, connect-failure injection), and helper methods (`push_inbound`, `record_outbound`) that future tests will call to simulate platform events. This is intentionally heavier than the narrow `_StubPlugin` / `_StubClient` already present in `tests/test_connectors_pool.py` (leg 5+6 deliverables) — those are pool-internal helpers that don't need recording machinery.

**Co-existence decision**: leave the leg-5/6 narrow helpers in `tests/test_connectors_pool.py` untouched. They test pool internals; the rich stub in `_stub.py` tests cross-flight integration. Refactoring leg-5/6 tests to use the rich stub would be gold-plating — both have the right shape for their callers. Document the distinction in the new `_stub.py` module docstring.

### Test seam discipline

The stub plugin is private API (`_stub.py` with underscore prefix per flight Design Decisions). It is **never** registered via `register_builtin_connectors()` in production. Tests register it explicitly:

```python
from the_one.connectors._stub import StubPlugin
from the_one.connectors.registry import register_for_test

register_for_test("stub", StubPlugin)
```

The `'stub'` type name is reserved for tests. Production flights (8, 9) will add `'discord'`, the second connector's name, etc. via `register_builtin_connectors()`. The schema v13 has no CHECK constraint on `connector_accounts.type` (per leg 1's design), so storing `'stub'`-typed rows works at the persistence layer without polluting the production type registry.

### Class-level recording state + autouse fixture

The stub plugin records to **class-level** state (not instance state) so tests can read recording buffers after the pool has returned and the plugin instance is no longer accessible. Each test that uses the stub must reset class state in an autouse fixture — analogous to leg 5/6's `_clear_pool_after_each_test`.

### Regression baseline contract

The end-to-end test is the canonical answer to "does the connector subsystem work end-to-end?" Future flights MUST keep this test passing. Specifically:

- Flight 2 (admin REST) adds API endpoints but does not modify the e2e flow — the test continues to work via direct repository writes.
- Flight 3 (session model) adds visibility-layer fields to `chat_sessions` but the connector_accounts table and the pool API are unchanged — the test continues to pass.
- Flight 4 (platform-send tool) introduces the tool that pushes outbound; the e2e test could be enriched at that point to dispatch via the tool, but the leg-7 baseline (direct stub recording via `record_outbound`) remains the minimum-viable contract.
- Flights 5-10 build on this without disturbing the e2e baseline.

If any subsequent flight needs to weaken or modify the e2e contract, that's a flag — the flight's design decisions section must explicitly justify the change.

## Inputs

What exists before this leg runs:

- Legs 1-6 landed (uncommitted on the feature branch)
- `the_one/connectors/base.py` exports `ConnectorPlugin`, `ConnectorClient`, `InboundEnvelope`, `OutboundTarget`, `DoctorReport`, `SessionKey`
- `the_one/connectors/errors.py` exports the 6-type hierarchy
- `the_one/connectors/registry.py` exports `register_for_test`, `clear_for_test`, `restore_to_baseline_for_test`, plus the module-level `register`, `resolve`, `types`
- `the_one/connectors/_pool.py` exports `acquire`, `shutdown_drain`, `_reap_once`, `_clear_for_test`, plus the module-level state (`_pool`, `_lock`, `_shutting_down`, `_reaper_task`)
- `the_one/db/repositories.py` exports `ConnectorAccountRepository`
- Schema v14 supports `connector_accounts(id, name, type, config, secrets, created_at, updated_at)` with no CHECK on `type`
- `tests/test_connectors_pool.py` has narrow `_StubPlugin` / `_StubClient` helpers (kept untouched)
- `tests/test_connectors.py` has `_MinimalPlugin` / `_MinimalClient` helpers used in registry / protocol tests (also kept untouched)

## Outputs

What exists after this leg completes:

- New file `the_one/connectors/_stub.py` exporting:
  - `StubClient` — in-process `ConnectorClient` satisfying `is_alive()`
  - `StubPlugin` — in-process `ConnectorPlugin` satisfying `connect`, `disconnect`, `doctor`, `normalize_session_key`; class-level recording buffers (`connect_calls`, `disconnect_calls`, `doctor_calls`, `inbound_records`, `outbound_records`); class-level scenario knobs (`doctor_response`, `connect_should_fail`); class helpers (`reset_for_test`, `push_inbound`, `record_outbound`)
- New file `tests/test_connectors_e2e.py` with:
  - Autouse `_reset_stub_state` fixture that calls `StubPlugin.reset_for_test()` before/after each test
  - Autouse `_isolate_data_dir` fixture that monkeypatches `settings.data_dir` to `tmp_path` for DB + encryptor isolation
  - `test_e2e_full_lifecycle` — the regression baseline (the marquee test)
  - `test_e2e_doctor_probe_returns_configured_response` (success / degraded / failed)
  - `test_e2e_connect_failure_propagates_to_acquire_caller`
  - `test_e2e_multiple_agents_on_same_account` — two agents, one account, two warm entries, both reap on `_evict_all_for_account`
- `_stub.py` is NOT re-exported from `the_one/connectors/__init__.py` (private)
- `make test`, `make lint` clean
- Leg status `landed`
- Flight log gains `### Leg 07: stub-plugin-and-end-to-end-fixture` entry

## Acceptance Criteria

- [ ] `the_one/connectors/_stub.py` exists with:
    - Module docstring explaining the stub's role as cross-flight regression fixture, the distinction from `_StubPlugin` / `_MinimalPlugin` in test files, and the "private — never registered via `register_builtin_connectors`" stance
    - `StubClient` class with `is_alive(self) -> bool` (returns `self._alive`); `__init__` sets `self._alive = True`
    - `StubPlugin` class with class-level state:
        - `connect_calls: list[tuple[str, str]]` — populated by `connect()` with `(account.id, account.type)`
        - `disconnect_calls: list[StubClient]` — populated by `disconnect()` with the client
        - `doctor_calls: list[tuple[str, str]]` — populated by `doctor()`
        - `inbound_records: list[InboundEnvelope]` — populated by `push_inbound()`
        - `outbound_records: list[tuple[OutboundTarget, str]]` — populated by `record_outbound()`
        - `doctor_response: DoctorReport | None` — knob; when None, doctor returns a default success DoctorReport
        - `connect_should_fail: BaseException | None` — knob; when set, `connect()` raises this exception
    - `StubPlugin` class methods/static helpers:
        - `reset_for_test()` (classmethod) — clears all buffers; resets knobs to None
        - `push_inbound(envelope)` (classmethod) — test helper to simulate inbound message receipt
        - `record_outbound(target, content)` (classmethod) — test helper to simulate outbound dispatch (Flight 4 will replace direct usage with the platform-send tool)
    - `StubPlugin` instance methods (the Protocol surface):
        - `async def connect(account, encryptor) -> StubClient` — records call; raises `connect_should_fail` if set; otherwise returns a fresh `StubClient`
        - `async def disconnect(client) -> None` — records call; sets `client._alive = False`
        - `async def doctor(account, encryptor) -> DoctorReport` — records call; returns `doctor_response` if set, else default success
        - `def normalize_session_key(inbound) -> SessionKey` — returns a `SessionKey` with all populated fields from the inbound envelope (including thread_id and peer_id)
- [ ] `isinstance(StubPlugin(), ConnectorPlugin)` returns `True` (structural satisfaction)
- [ ] `isinstance(StubClient(), ConnectorClient)` returns `True` (structural satisfaction)
- [ ] `the_one/connectors/_stub.py` does NOT register itself via `register_builtin_connectors()` — verify by inspection
- [ ] `the_one/connectors/__init__.py` is NOT updated to re-export `StubPlugin` / `StubClient` — they remain at the canonical `the_one.connectors._stub` path only
- [ ] `tests/test_connectors_e2e.py` exists with the autouse fixtures and at minimum these tests passing:
    - `test_e2e_full_lifecycle` — the regression baseline:
        1. Creates a `ConnectorAccount` of type `'stub'` via `ConnectorAccountRepository` (real DB write under tmp_path)
        2. Registers `StubPlugin` via `register_for_test("stub", StubPlugin)`
        3. Calls `acquire("agent-e2e", "acct-e2e")` and asserts the returned client is a `StubClient` and `is_alive()` returns True
        4. Asserts `StubPlugin.connect_calls == [("acct-e2e", "stub")]`
        5. Calls `StubPlugin.push_inbound(envelope)` to simulate inbound; asserts `len(StubPlugin.inbound_records) == 1`
        6. Calls `StubPlugin.record_outbound(target, "reply")`; asserts `outbound_records` reflects the call
        7. Ages the pool entry via `entry.last_activity = 0.0`; calls `_reap_once()`; asserts the entry is evicted, pool is empty, `disconnect_calls` includes the original client
        8. Calls `shutdown_drain()`; asserts `_reaper_task is None`, `_shutting_down is True`
    - `test_e2e_doctor_probe_returns_default_success` — without setting `doctor_response`, doctor returns a `DoctorReport(status="ok", ...)`
    - `test_e2e_doctor_probe_returns_configured_response` — set `doctor_response = DoctorReport(status="failed", message="x", details={})`; verify doctor returns it
    - `test_e2e_connect_failure_propagates_to_acquire_caller` — set `connect_should_fail = ConnectorConnectionError("simulated")`; `acquire` re-raises; pool ends empty
    - `test_e2e_multiple_agents_on_same_account_reap_together` — acquire under `agent-a` and `agent-b` for the same `acct-e2e`; `_evict_all_for_account("acct-e2e")` evicts both
- [ ] Autouse fixtures in `tests/test_connectors_e2e.py`:
    - `_reset_stub_state` — calls `StubPlugin.reset_for_test()` before yield, and again after, so cross-test state cannot leak
    - `_clear_pool_and_registry` — calls `_clear_for_test()` (pool) and `restore_to_baseline_for_test()` (registry) after each test
- [ ] `tests/test_connectors_e2e.py` does NOT modify `the_one/connectors/_stub.py` from inside the test (no monkey-patches on the stub itself — knobs and methods are the contract)
- [ ] All previously landed connector tests still pass (no regression in `tests/test_connectors.py`, `tests/test_connectors_pool.py`, `tests/test_db_repositories.py`, `tests/test_db_migration.py`)
- [ ] `docker exec the-one pytest -x --timeout 30 tests/test_connectors_e2e.py` clean
- [ ] `docker exec the-one pytest -x --timeout 30` full suite clean
- [ ] `make lint` clean
- [ ] Leg status `landed`
- [ ] `stub-plugin-and-end-to-end-fixture` checkbox checked in flight.md's Legs section
- [ ] Flight log has `### Leg 07: stub-plugin-and-end-to-end-fixture` entry under `## Leg Progress`

## Verification Steps

1. **Stub plugin module loads cleanly**:
   - `docker exec the-one python -c "from the_one.connectors._stub import StubPlugin, StubClient; from the_one.connectors.base import ConnectorPlugin, ConnectorClient; assert isinstance(StubPlugin(), ConnectorPlugin); assert isinstance(StubClient(), ConnectorClient); print('ok')"`

2. **Stub plugin is NOT in the production registry**:
   - `docker exec the-one python -c "from the_one.connectors.registry import types; assert 'stub' not in types(); print('ok')"`

3. **E2E test passes**:
   - `tests/test_connectors_e2e.py::test_e2e_full_lifecycle` is the canonical verifier

4. **No regression**:
   - Full suite green; `make lint` clean

## Implementation Guidance

### Step 1: Create `the_one/connectors/_stub.py`

```python
"""In-process stub plugin + client — cross-flight regression fixture.

This stub is the canonical end-to-end test fixture for Mission 10. Flights
2-10 import :class:`StubPlugin` and register it via
:func:`the_one.connectors.registry.register_for_test` to exercise their
own pipelines without invoking real platform APIs.

Distinct from the narrow ``_StubPlugin`` / ``_StubClient`` helpers in
:mod:`tests.test_connectors_pool` (leg 5/6 deliverables, which test pool
internals only) and ``_MinimalPlugin`` / ``_MinimalClient`` in
:mod:`tests.test_connectors` (leg 3/4 deliverables, which test the protocol
and registry surfaces). The stub here has class-level recording buffers and
scenario knobs that those narrow helpers don't carry — appropriate for
cross-flight integration tests, overkill for internal-protocol tests.

Underscore-prefixed module (private API). NOT registered via
:func:`the_one.connectors.registry.register_builtin_connectors` — tests
register it explicitly via :func:`register_for_test`. Production code MUST
NOT import this module.

The ``'stub'`` type name is reserved for tests. Production flights register
real connector types (``'discord'`` in Flight 8, the second platform in
Flight 9). Schema v13 has no CHECK constraint on ``connector_accounts.type``,
so persisting a ``'stub'``-typed account in tests works at the DB layer.
"""

from __future__ import annotations

from typing import ClassVar

from the_one.connectors.base import (
    ConnectorClient,
    DoctorReport,
    InboundEnvelope,
    OutboundTarget,
    SessionKey,
)
from the_one.db.models import ConnectorAccount
from the_one.encryption import Encryptor


class StubClient:
    """In-process :class:`ConnectorClient` — structurally satisfies the Protocol."""

    def __init__(self) -> None:
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive


class StubPlugin:
    """In-process :class:`ConnectorPlugin` — cross-flight regression fixture.

    Class-level recording buffers and scenario knobs let tests assert what
    flowed through and inject failure scenarios. Each test that uses the
    stub MUST call :meth:`reset_for_test` (or rely on an autouse fixture
    that does so) to prevent cross-test state leakage.
    """

    # ── Recording buffers (class-level) ────────────────────────────────
    connect_calls: ClassVar[list[tuple[str, str]]] = []
    """List of ``(account.id, account.type)`` tuples; one per :meth:`connect` call."""

    disconnect_calls: ClassVar[list[ConnectorClient]] = []
    """List of clients passed to :meth:`disconnect`.

    Typed as :class:`ConnectorClient` (the Protocol), not :class:`StubClient`,
    because that's the parameter type on :meth:`disconnect`. At runtime
    the appended values are always :class:`StubClient` instances in this
    stub, but the buffer type matches the contract.
    """

    doctor_calls: ClassVar[list[tuple[str, str]]] = []
    """List of ``(account.id, account.type)`` tuples; one per :meth:`doctor` call."""

    inbound_records: ClassVar[list[InboundEnvelope]] = []
    """Inbound envelopes pushed via :meth:`push_inbound` (test helper)."""

    outbound_records: ClassVar[list[tuple[OutboundTarget, str]]] = []
    """``(target, content)`` tuples pushed via :meth:`record_outbound` (test helper).

    Flight 4 will land the real platform-send tool that produces these
    records; until then, tests call :meth:`record_outbound` directly to
    simulate the tool's behaviour.
    """

    # ── Scenario knobs (class-level) ───────────────────────────────────
    doctor_response: ClassVar[DoctorReport | None] = None
    """When set, :meth:`doctor` returns this instead of a default success report."""

    connect_should_fail: ClassVar[BaseException | None] = None
    """When set, :meth:`connect` raises this instead of returning a client."""

    # ── Test-side helpers ──────────────────────────────────────────────
    @classmethod
    def reset_for_test(cls) -> None:
        """Reset all class-level state. Call from an autouse fixture."""
        cls.connect_calls = []
        cls.disconnect_calls = []
        cls.doctor_calls = []
        cls.inbound_records = []
        cls.outbound_records = []
        cls.doctor_response = None
        cls.connect_should_fail = None

    @classmethod
    def push_inbound(cls, envelope: InboundEnvelope) -> None:
        """Simulate the plugin's gateway receiving an inbound message.

        In production this would be driven by the platform's event loop
        (Discord gateway dispatch, Slack Socket Mode receive, etc.).
        Tests push directly to exercise the downstream dispatch.
        """
        cls.inbound_records.append(envelope)

    @classmethod
    def record_outbound(cls, target: OutboundTarget, content: str) -> None:
        """Simulate the agent dispatching outbound through this plugin.

        Flight 4's platform-send tool will produce these records when it
        lands; until then, tests call this directly to simulate the
        tool's behaviour.
        """
        cls.outbound_records.append((target, content))

    # ── Protocol surface ──────────────────────────────────────────────
    async def connect(
        self,
        account: ConnectorAccount,
        encryptor: Encryptor,
    ) -> StubClient:
        type(self).connect_calls.append((account.id, account.type))
        if type(self).connect_should_fail is not None:
            raise type(self).connect_should_fail
        return StubClient()

    async def disconnect(self, client: ConnectorClient) -> None:
        type(self).disconnect_calls.append(client)
        # Stub-specific: the production ConnectorClient Protocol has no
        # writable `_alive` field; this stub's StubClient does, so flip it
        # when disconnect is called to make `is_alive()` return False.
        if isinstance(client, StubClient):
            client._alive = False

    async def doctor(
        self,
        account: ConnectorAccount,
        encryptor: Encryptor,
    ) -> DoctorReport:
        type(self).doctor_calls.append((account.id, account.type))
        if type(self).doctor_response is not None:
            return type(self).doctor_response
        return DoctorReport(
            status="ok",
            message="stub probe ok",
            details={},
        )

    def normalize_session_key(self, inbound: InboundEnvelope) -> SessionKey:
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
            thread_id=inbound.thread_id,
            peer_id=inbound.peer_id,
        )
```

### Step 2: Create `tests/test_connectors_e2e.py`

```python
"""End-to-end regression baseline for the connector subsystem (mission 10 flight 1).

This file's `test_e2e_full_lifecycle` is the canonical answer to "does the
connector subsystem work end-to-end?" Future flights MUST keep this passing.
"""

from __future__ import annotations

import aiosqlite
import pytest

from the_one.config import settings
from the_one.connectors import _pool as pool_mod
from the_one.connectors._pool import (
    _clear_for_test as _pool_clear_for_test,
    _evict_all_for_account,
    _reap_once,
    acquire,
    shutdown_drain,
)
from the_one.connectors._stub import StubClient, StubPlugin
from the_one.connectors.base import (
    DoctorReport,
    InboundEnvelope,
    OutboundTarget,
)
from the_one.connectors.errors import ConnectorConnectionError
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.connection import get_connection
from the_one.db.models import ConnectorAccount
from the_one.db.repositories import ConnectorAccountRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import get_encryptor


@pytest.fixture(autouse=True)
def _reset_stub_state():
    """Reset StubPlugin class-level state before AND after each test."""
    StubPlugin.reset_for_test()
    yield
    StubPlugin.reset_for_test()


@pytest.fixture(autouse=True)
async def _clear_pool_and_registry():
    """Empty pool, reset registry to production baseline. Pairs with the
    stub-state fixture for full per-test isolation."""
    yield
    await _pool_clear_for_test()
    restore_to_baseline_for_test()


@pytest.fixture
async def isolated_db(tmp_path, monkeypatch):
    """Per-test sqlite DB at tmp_path. Mirrors `tests/test_lifespan.py:_isolated_data_dir`.

    `get_connection()` in `the_one.db.connection` returns a module-level
    SINGLETON keyed only on first call — not on `settings.db_path`. The
    session-wide `THE_ONE_DATA_DIR` env var (set in `tests/conftest.py`)
    pins the singleton to the session tmp_dir at first use. To get per-test
    isolation we MUST also null `_connection` so the next `get_connection()`
    re-opens against the patched `settings.data_dir`.

    The encryptor cache (`the_one/encryption.py:get_encryptor`) is keyed on
    the resolved path, so per-`tmp_path` isolation is automatic there — no
    cache reset needed.
    """
    from the_one.db import connection as db_connection

    db_path = tmp_path / "e2e.db"
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    # Apply schema with a direct connection (bypasses the cache).
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    await conn.close()

    # CRITICAL: null the connection singleton so the next get_connection()
    # call (e.g. from the pool's `_load_account` or from `_seed_stub_account`)
    # opens against this test's tmp_path. monkeypatch restores the previous
    # value at teardown, which avoids leaking this test's connection into
    # the next.
    monkeypatch.setattr(db_connection, "_connection", None)

    yield db_path


async def _seed_stub_account(account_id: str = "acct-e2e") -> ConnectorAccount:
    """Helper: persist a stub-typed ConnectorAccount via the repository."""
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    repo = ConnectorAccountRepository(conn, encryptor)
    account = ConnectorAccount(
        id=account_id,
        name="E2E Test Bot",
        type="stub",
        config={"some": "config"},
        secrets={"BOT_TOKEN": "test-token-xyz"},
    )
    await repo.create(account)
    return account


async def test_e2e_full_lifecycle(isolated_db) -> None:
    """The regression baseline. Flights 2-10 inherit this; it must keep passing."""
    # 1. Persist a stub-typed connector account.
    await _seed_stub_account()

    # 2. Register the stub plugin into the connector registry.
    register_for_test("stub", StubPlugin)

    # 3. Acquire — triggers plugin.connect().
    client = await acquire("agent-e2e", "acct-e2e")
    assert isinstance(client, StubClient)
    assert client.is_alive()
    assert StubPlugin.connect_calls == [("acct-e2e", "stub")]

    # 4. Simulate inbound.
    envelope = InboundEnvelope(
        platform="stub",
        account_id="acct-e2e",
        channel_id="chan-1",
        thread_id=None,
        peer_id="peer-x",
        peer_name="Peer X",
        text="hello",
        raw={},
    )
    StubPlugin.push_inbound(envelope)
    assert len(StubPlugin.inbound_records) == 1
    assert StubPlugin.inbound_records[0].text == "hello"

    # 5. Simulate outbound (Flight 4 will produce these via the platform-send tool).
    target = OutboundTarget(channel_id="chan-1")
    StubPlugin.record_outbound(target, "agent reply")
    assert StubPlugin.outbound_records == [(target, "agent reply")]

    # 6. Age the pool entry; verify reaper evicts.
    entry = pool_mod._pool[("agent-e2e", "acct-e2e")]
    entry.last_activity = 0.0  # ancient
    expired = await _reap_once()
    assert ("agent-e2e", "acct-e2e") in expired
    assert pool_mod._pool == {}
    assert StubPlugin.disconnect_calls == [client]
    assert not client.is_alive()  # disconnect set _alive = False

    # 7. shutdown_drain returns cleanly even on empty pool.
    await shutdown_drain()
    assert pool_mod._reaper_task is None
    assert pool_mod._shutting_down is True

    # The autouse `_clear_pool_and_registry` fixture resets _shutting_down
    # for the next test.


async def test_e2e_doctor_probe_returns_default_success(isolated_db) -> None:
    """Without setting doctor_response, doctor returns a DoctorReport with status='ok'."""
    account = await _seed_stub_account()
    plugin = StubPlugin()
    encryptor = get_encryptor(settings.data_dir)
    report = await plugin.doctor(account, encryptor)
    assert report.status == "ok"
    assert "stub" in report.message.lower()
    assert StubPlugin.doctor_calls == [("acct-e2e", "stub")]


async def test_e2e_doctor_probe_returns_configured_response(isolated_db) -> None:
    """Setting doctor_response makes doctor() return it verbatim."""
    account = await _seed_stub_account()
    StubPlugin.doctor_response = DoctorReport(
        status="failed",
        message="simulated failure",
        details={"reason": "test"},
    )
    plugin = StubPlugin()
    encryptor = get_encryptor(settings.data_dir)
    report = await plugin.doctor(account, encryptor)
    assert report.status == "failed"
    assert report.message == "simulated failure"
    assert report.details == {"reason": "test"}


async def test_e2e_connect_failure_propagates_to_acquire_caller(isolated_db) -> None:
    """Setting connect_should_fail makes acquire re-raise the configured exception."""
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    StubPlugin.connect_should_fail = ConnectorConnectionError("simulated connect failure")

    with pytest.raises(ConnectorConnectionError, match="simulated connect failure"):
        await acquire("agent-e2e", "acct-e2e")

    # Pool empty after failure (idempotent pop).
    assert pool_mod._pool == {}


async def test_e2e_multiple_agents_on_same_account_reap_together(isolated_db) -> None:
    """Two agents acquire the same account → two warm entries → _evict_all_for_account flushes both."""
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    c1 = await acquire("agent-a", "acct-e2e")
    c2 = await acquire("agent-b", "acct-e2e")
    assert StubPlugin.connect_calls == [
        ("acct-e2e", "stub"),
        ("acct-e2e", "stub"),
    ]
    assert len(pool_mod._pool) == 2

    await _evict_all_for_account("acct-e2e")

    assert pool_mod._pool == {}
    assert len(StubPlugin.disconnect_calls) == 2
    assert not c1.is_alive()
    assert not c2.is_alive()
```

### Step 3: Run tests + lint + update artifacts

```bash
docker exec the-one pytest -x --timeout 30 tests/test_connectors_e2e.py
docker exec the-one pytest -x --timeout 30 tests/test_connectors.py tests/test_connectors_pool.py tests/test_connectors_e2e.py
docker exec the-one pytest -x --timeout 30
docker exec the-one bash -c "cd /workspace && make lint"
```

Append `### Leg 07: stub-plugin-and-end-to-end-fixture` to flight-log.md. Check off `stub-plugin-and-end-to-end-fixture` in flight.md. Set this leg's status to `landed`. Signal `[HANDOFF:review-needed]`. Do NOT commit.

## Edge Cases

- **`isolated_db` fixture and the connection cache** — `get_connection()` in `the_one/db/connection.py` returns a module-level singleton (`_connection`). The session-wide `THE_ONE_DATA_DIR` env var set in `tests/conftest.py` pins the singleton to the session tmp_dir at first use. The leg's `isolated_db` fixture mirrors `tests/test_lifespan.py:_isolated_data_dir` exactly: patch `settings.data_dir`, apply schema with a direct connection (bypasses the cache), then `monkeypatch.setattr(db_connection, "_connection", None)` to force `get_connection()` to re-open against the patched path. `monkeypatch` auto-restores at teardown, so the next test's connection state is clean.
- **Encryptor cache is path-keyed** — `get_encryptor(settings.data_dir)` caches in `_encryptor_cache` by resolved path (`the_one/encryption.py:93`). Per-test `tmp_path` gives each test its own Encryptor automatically; no explicit reset needed. The seed-time and acquire-time Encryptors are guaranteed to match because they resolve to the same path.
- **`StubPlugin` class state and parallel test execution** — pytest-asyncio in auto mode runs tests on a single event loop per session; class-level state is fine if the autouse fixture resets between tests. If a future flight enables pytest-xdist parallelism, this stub's class-state pattern WILL race; the parallelism flight would need to refactor stub state to be instance-level. Note for forward awareness.
- **`record_outbound` is a test helper, NOT a Protocol method** — calling it doesn't trigger any real send; the records are just stored for test inspection. When Flight 4 lands the platform-send tool, the tool's `execute()` will call the stub plugin's outbound mechanism (TBD by Flight 4's design); at that point, `record_outbound` could either be removed or kept as the direct test-call interface.
- **`StubPlugin.normalize_session_key` populates all fields** — including `thread_id` and `peer_id` from the inbound envelope. Real connectors (Flight 8 Discord, Flight 9) may choose to collapse threads or DMs into broader session keys per their `SessionKey` design — the stub returns the maximal key for test purposes. Future tests that need a specific normalization can use a SubclassedStubPlugin if needed.
- **`asyncio.Lock` and pytest-asyncio** — leg 6 pool tests verified the lock pattern works under pytest-asyncio's auto-mode. The e2e tests don't add any new lock-or-event behaviour; they exercise the existing surface.
- **`reset_for_test` is a classmethod that reassigns class attributes** — this works because Python looks up `cls.connect_calls` as `type(cls).connect_calls` at access time. Setting `cls.connect_calls = []` creates a new list bound to the class, replacing any previous list. Tests reading `StubPlugin.connect_calls` see the new list.
- **The acceptance criterion "no monkey-patches on the stub itself"** — tests use knob attributes (`StubPlugin.connect_should_fail = exc`) and helper methods (`StubPlugin.reset_for_test()`, `push_inbound`, `record_outbound`). They do NOT call `monkeypatch.setattr(StubPlugin, "connect", ...)` to swap behaviour. Knob-based scenarios are the contract; monkey-patching is the escape hatch when the contract is insufficient — flag if a future test needs to monkey-patch.

## Files Affected

- `the_one/connectors/_stub.py` (NEW) — stub plugin + client + recording buffers + scenario knobs
- `tests/test_connectors_e2e.py` (NEW) — autouse fixtures + 5 e2e tests
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md` — check off `stub-plugin-and-end-to-end-fixture`
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight-log.md` — append `### Leg 07` entry
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/legs/07-stub-plugin-and-end-to-end-fixture.md` (this file) — status to `landed`

**NOT affected**:
- `the_one/connectors/__init__.py` — stub is private; not re-exported
- `the_one/connectors/registry.py` — `register_builtin_connectors()` body remains empty in Flight 1
- Existing tests in `test_connectors.py`, `test_connectors_pool.py` — left untouched (they have their own narrow stubs)

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] All listed tests passing
- [ ] `make lint` clean
- [ ] Flight log + flight artifact updated
- [ ] Leg status `landed`
- [ ] `[HANDOFF:review-needed]`; do NOT commit

---

## Citation Audit

8 citations verified against current code at leg design time:

| Citation | Verification |
|---|---|
| `the_one/connectors/base.py` Protocols + supporting types (leg 3) | OK — landed |
| `the_one/connectors/errors.py` 6-type hierarchy (leg 3) | OK — landed |
| `the_one/connectors/registry.py:register_for_test, restore_to_baseline_for_test` (leg 4) | OK — landed |
| `the_one/connectors/_pool.py:acquire, _reap_once, shutdown_drain, _clear_for_test` (legs 5+6) | OK — landed |
| `the_one/db/repositories.py:ConnectorAccountRepository` (leg 2) | OK — landed |
| `the_one/db/schema.py:CURRENT_VERSION = 14` (leg 2) | OK — landed |
| `tests/test_connectors_pool.py:_StubPlugin, _StubClient` (leg 5/6, narrow helpers) | OK — kept untouched |
| `tests/test_connectors.py:_MinimalPlugin, _MinimalClient` (leg 3/4, narrow helpers) | OK — kept untouched |
