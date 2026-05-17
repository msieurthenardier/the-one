# Flight Log: Connector Plugin Contract and Lifecycle Foundation

**Flight**: [Connector Plugin Contract and Lifecycle Foundation](flight.md)

## Summary

_(populated during execution)_

---

## Flight Director Notes

Orchestration decisions made by the Flight Director (Mission Control) running the `/agentic-workflow` skill.

### Kickoff

- **Skill loaded**: `/agentic-workflow` invoked by the operator after Flight 1 spec landed on `main` at `cf17f40`
- **Crew file validated**: `the_one/.flightops/agent-crews/leg-execution.md` has all three required sections (`## Crew`, `## Interaction Protocol`, `## Prompts`) with fenced code blocks per prompt
- **Orchestration vs. crew file**: The crew file describes a per-leg review/commit pattern. The `/agentic-workflow` skill **overrides** that with flight-end batch review. Per-leg flow this flight: design (via `/leg`) → design review (Developer) → implementation (Developer, **no commit**) → next leg. After all 8 legs land: Reviewer across all uncommitted changes → optional fix-review-issues → single end-of-flight commit + PR.
- **Models**: Developer = Sonnet (design review + implementation), Reviewer = Haiku (final code review). Per the crew file; never Opus for Reviewer per skill guidance.
- **Test invocation**: `docker exec the-one pytest ... -x --timeout 30` per crew file's anti-TTY-hang guidance. Scope each leg's iterations to the test file(s) being changed; full suite at leg-end.
- **Flight status**: `ready` → `in-flight` at orchestration start
- **Feature branch**: `flight/01-connector-plugin-contract-and-lifecycle-foundation` created from `main` at `cf17f40`
- **Starting leg**: 1 of 8 — `schema-and-migration`

---

## Reconnaissance Report

Pre-flight reconnaissance against the cited locations in the mission's Flight 1 description and the architect's first/second review of the mission spec.

| Source item | Classification | Evidence | Recommendation |
|---|---|---|---|
| `mcp/_pool.py` worker-task-per-entry pattern | confirmed-live | `_RegistryEntry` L67-98; `_entry_worker` L148-248; `_pool` L102; `acquire` L431-517; `shutdown_drain` L387-428 | Mirror the pattern in `connectors/_pool.py`; do not share code (see flight Design Decisions) |
| `mcp/_pool.py` `_shutting_down` flag test-isolation debt | confirmed-live | Module-level `_shutting_down: bool = False` at L104; `_clear_for_test` resets at L561 but cross-test leakage observed under shared event loop | Connector pool fixes from the start; M07 debt remains deferred per Design Decisions |
| Encryption rotation single-pass transaction | confirmed-live | `interfaces/web/api.py:2770-2840` — single atomic commit covers LLM providers + MCP sources; try/except/rollback wrapper at L2819-2833 | Extend the same commit to cover `connector_accounts.secrets` in the schema-and-migration leg |
| `db/schema.py` v8/v9/v10 migration pattern | confirmed-live | Pattern at L300-430; v10 migration L363-410 shows the table-rename ceremony with `INSERT OR IGNORE INTO schema_version` last; `CURRENT_VERSION = 12` at L11 | Flight 1 introduces v13; follow v10 pattern exactly |
| Pydantic source-type config pattern | confirmed-live | `MCPSource` at `db/models.py:86-108`; `type: Literal[...]` + `config: dict[str, Any]` + `secrets: dict[str, Any]`; `merged_config()` at L97-107 | `ConnectorAccount` mirrors this shape exactly |
| Source repository pattern | confirmed-live | `MCPSourceRepository` at `db/repositories.py:291-425`; `__init__(conn, encryptor)`; encryptor is a reference (not copy) for rotation propagation; `_secrets_to_ciphertext` / `_ciphertext_to_secrets`; `_row_to_model` | `ConnectorAccountRepository` mirrors this exactly |
| MCP four-typed-exceptions contract | confirmed-live | `mcp/errors.py` defines 10 typed exceptions across a base hierarchy; held without erosion across 11 M07 flights (M07 debrief L62) | Mirror with 5 connector-type exceptions initially; grow deliberately |
| `agents.md` provider-type six-layer checklist | confirmed-live | `agents.md` L251-267 enumerates Pydantic Literal, `_PROVIDER_TYPE_MAP`, registry loaders, SQLite CHECK constraint, API gating, frontend tokens, optional `_init_provider_state` hook | Flight 1 adds the connector-type checklist parallel to this |
| `tools/builtins.py` enable/disable pattern (for Flight 4 reference) | confirmed-live | Built-in tools enable/disable surface at `tools/resolver.py` + `tools/builtins.py` | Out of Flight 1 scope; cited as the pattern Flight 4 inherits |
| M07 in-process test-stub strategy | confirmed-live | M07 tests use mock at the `ClientSession` level (no subprocess fixture); test seam is dependency injection per the `mock` LLM provider pattern | Stub plugin at `connectors/_stub.py` is in-process; no env-var test-mode seam |

**Conclusion**: All cited locations confirmed live; no drift. The mission's Flight 1 description was written against the current code shape. Design Decisions are grounded in real code paths. Proceed to leg planning.

---

## Design Adjustments

Adjustments to the flight spec discovered during leg planning/execution. Each
entry names the leg that surfaced the adjustment, what changed, and why.

### Leg 02 — `name` column on `connector_accounts` (v14 migration; Flight 8's CHECK migration renumbers to v15)

The flight spec calls for `ConnectorAccount` to "mirror MCPSource shape" but
the v13 schema (leg 01) omitted the `name` column that `MCPSource` has as a
first-class operator-visible identifier (`db/models.py:MCPSource.name`, line
90). Leg 02 adds v14: `ALTER TABLE connector_accounts ADD COLUMN name TEXT
NOT NULL DEFAULT ''`. Pydantic `ConnectorAccount.name: str` (no default —
required at create/update time, matching `MCPSource.name`'s shape).

Downstream impact: Flight 8 (Discord) was planned to land v14 (CHECK
constraint on `type` via table-rename ceremony — see flight spec Design
Decisions block "Schema version increments from 12 to 13; no CHECK constraint
on `type` in v13"). That migration now becomes **v15**. Flight spec text
updated accordingly in this leg (Design Decisions block + Technical Approach
bullet on `db/schema.py`).

Rationale: `MCPSource` has `name`; Flight 2's admin UI needs to identify
multiple Discord bots / Slack accounts visually; storing display name in
`config.name` (the alternative) would diverge from the MCP pattern this
flight intentionally mirrors. The v13-seeded-row case is handled by the
`NOT NULL DEFAULT ''` clause — in practice zero rows exist at v13 since the
table is new — verified by `TestSchemaV14.test_v14_preserves_v13_seeded_row_with_empty_name`.

Brittle-test bookkeeping: `TestSchemaV8.test_v8_fresh_db_includes_tool_configs_and_tool_overrides`
hardcoded `assert CURRENT_VERSION == 13` was bumped to 14 (expected churn on
every schema head bump, called out explicitly by the test's own comment).
`TestSchemaV13.test_v13_connector_accounts_has_expected_columns_and_no_check_constraint`
was updated to acknowledge that `name` is present in the post-`ensure_schema`
column set after v14 lands (the test asserts post-`ensure_schema` shape, not
"shape if we stopped at v13").

---

## Leg Progress

_(append entries as legs complete)_

### Leg 08: agents-md-and-package-readme

- **Status**: landed
- **Started**: 2026-05-16
- **Completed**: 2026-05-16
- **Changes Made** (documentation only — no code, no test changes):
  - `the_one/agents.md`: appended two new top-level sections after the
    existing "Provider type extension checklist":
    - **"Connector type extension checklist"** — 7-layer table parallel
      to the provider-type checklist at L251-267. Names which flight
      owns each subsequent coordination point (Flight 1 ships scaffolding;
      Flight 2 lands the admin REST surface; Flight 8 narrows the
      `Literal`, fills `CONNECTOR_TYPES`, extends
      `register_builtin_connectors`, and lands the v15 CHECK migration;
      Flight 9 lands the second connector). Layer 4's v14→v15 rationale
      cited (v14 is leg-02's `name` column).
    - **"Connector subsystem"** decisions-and-invariants section with 5
      subsections + a Known Issues subsection:
      - Typed-exception hierarchy (6 producer types in
        `connectors/errors.py`; grow-deliberately stance; clarifies that
        the "4-typed-exceptions" wording in the MCP section refers to the
        consumer-side surface, not the producer hierarchy).
      - Worker-task-per-entry pattern (`connectors/_pool.py:_entry_worker`;
        connect-and-disconnect-on-same-task contract; cycle-2 race-fix
        invariant for concurrent-acquire-same-key).
      - Parallel-pool-not-shared decision with the explicit **third
        network-keyed pool** extraction trigger AND the PTY-exclusion
        rationale (PTY at `tools/_session_registry.py` is
        process-lifecycle-keyed, not network-keyed — no warm-connection
        keep-alive, no heartbeat, no reconnect lifecycle).
      - Per-Protocol structural-satisfaction discipline (Plugin + Client
        in Flight 1; AllowlistResolver Flight 6; CommandHandler Flight 7;
        structural satisfaction is per-Protocol, not subsystem-wide).
      - Encryption-rotation invariant (three corpora atomic in
        `rotate_encryption_key`: `llm_providers.api_key`,
        `mcp_sources.secrets`, `connector_accounts.secrets`).
      - Known Issues subsection with 2 entries:
        - Deferred shared-pool extraction (trigger: third network-keyed
          pool).
        - Flight 3 acquire-per-inbound ratification needed for
          `last_activity` tracking — Flight 3 MUST call `acquire()`
          per inbound or amend with an explicit touch mechanism, else
          the reaper will prematurely evict actively-used gateway
          connections.
  - Created `the_one/connectors/README.md` (NEW, 201 lines) — structurally
    analogous to `the_one/mcp/README.md`. Top-of-file orientation +
    pointer to `agents.md`'s "Project Conventions" + pointer to the
    Connector subsystem section. 8 numbered sections:
    - §1. Package layout — tree of the 6 files with one-line each
    - §2. Public API entry points — `acquire`, `shutdown_drain`
    - §3. Protocol decomposition — Plugin + Client now;
      AllowlistResolver + CommandHandler Flight 6/7
    - §4. Test seams — `register_for_test`, `clear_for_test`,
      `restore_to_baseline_for_test`, `_clear_for_test`, `StubPlugin`
    - §5. The `'stub'` type name reservation — explicit warning that
      Flight 8's v15 CHECK migration MUST coordinate with this README
    - §6. Encryption envelope — Fernet via system-wide encryptor;
      reference-not-copy for rotation propagation
    - §7. Rotation invariant — three corpora atomic
    - §8. Cross-references — back to agents.md, mcp/README.md, project
      conventions
  - `the_one/connectors/__init__.py` LEFT UNCHANGED — the existing
    docstring already covers canonical-import discipline and the package's
    role; adding a README pointer would just duplicate. Leg artifact's
    Step 4 explicitly framed the touch as optional ("skip if docstring is
    already complete"); skipped per that guidance.
- **Verification**:
  - All cited symbols verified live via grep:
    - `connectors/_pool.py:_entry_worker` (L176),
      `acquire` (L396), `shutdown_drain` (L354), `_evict` (L220),
      `_reap_once` (L282), `_clear_for_test` (L472), `_RegistryEntry`
      (L86).
    - `connectors/registry.py`: `register_for_test` (L109),
      `clear_for_test` (L121), `restore_to_baseline_for_test` (L135),
      `register_builtin_connectors` (L147).
    - `connectors/errors.py`: all 6 types present (L15-69).
    - `interfaces/web/api.py:rotate_encryption_key` (L2745) — three
      `await conn.execute("UPDATE …")` loops feeding a single
      `await conn.commit()`; try/except runs `await conn.rollback()`
      and re-raises.
  - `make lint` → All checks passed.
  - `docker exec the-one pytest -x --timeout 30` → 1774 passed, 4
    skipped, 375 deselected, 2 pre-existing warnings (untouched
    `test_provider_api.py::TestModelDiscovery::test_ollama_models` —
    not caused by this leg). 100.19s wall.
- **Notes**:
  - Pure documentation leg — no code changes, no test changes, no
    `__init__.py` export changes.
  - The "third network-keyed pool" extraction trigger AND the
    PTY-exclusion rationale are stated in both `agents.md`'s
    "Parallel-pool-not-shared decision" subsection AND in its
    Known Issues entry (the README points readers to agents.md for the
    full discussion).
  - References use the `file:symbol` form (e.g.
    `connectors/_pool.py:_entry_worker`) rather than `file:line` so a
    future rename surfaces as a clearly-undefined reference rather than
    silent line drift.
  - Last leg of the flight. Flight artifact's status is NOT flipped by
    this leg — that's the agentic-workflow orchestrator's job after the
    batch review (per the leg artifact's Step 6 and the flight log's
    Kickoff entry).

### Leg 07: stub-plugin-and-end-to-end-fixture

- **Status**: landed
- **Started**: 2026-05-16
- **Completed**: 2026-05-16
- **Changes Made**:
  - Created `the_one/connectors/_stub.py` with the rich stub plugin + client:
    - `StubClient` (writable `_alive`; `is_alive()` returns `self._alive`).
    - `StubPlugin` structurally satisfies `ConnectorPlugin` (`connect`,
      `disconnect`, `doctor`, `normalize_session_key`).
    - Class-level recording buffers: `connect_calls`, `disconnect_calls`
      (typed `ClassVar[list[ConnectorClient]]` per the leg's design-review
      fix — no type-ignore needed), `doctor_calls`, `inbound_records`,
      `outbound_records`.
    - Class-level scenario knobs: `doctor_response: DoctorReport | None`
      (None → default `status="ok"` report), `connect_should_fail:
      BaseException | None` (None → return fresh client).
    - Classmethods: `reset_for_test()` (clears all buffers + knobs by
      reassigning fresh empty lists / None), `push_inbound(envelope)`,
      `record_outbound(target, content)`.
    - `disconnect` checks `isinstance(client, StubClient)` before flipping
      the writable `_alive` field (the `ConnectorClient` Protocol has no
      such field).
    - Module docstring explains: cross-flight regression-fixture role, the
      distinction from the narrow `_StubPlugin`/`_StubClient` in
      `tests/test_connectors_pool.py` (leg 5/6 helpers, kept untouched)
      and `_MinimalPlugin`/`_MinimalClient` in `tests/test_connectors.py`
      (leg 3/4 helpers, also kept untouched), and the "private — never
      registered via `register_builtin_connectors`" stance.
    - NOT re-exported from `the_one/connectors/__init__.py` (private —
      tests import directly from the canonical `_stub` path).
  - Created `tests/test_connectors_e2e.py` with 3 fixtures + 5 tests:
    - `_reset_stub_state` (autouse, sync): calls
      `StubPlugin.reset_for_test()` before AND after each test.
    - `_clear_pool_and_registry` (autouse, async; pytest-asyncio auto mode
      handles the sync/async pairing): `await _pool_clear_for_test()` +
      `restore_to_baseline_for_test()` after each test.
    - `isolated_db` (per-test): mirrors `tests/test_lifespan.py
      :_isolated_data_dir` — monkeypatch `settings.data_dir = tmp_path`,
      apply schema to `settings.db_path` (i.e. `tmp_path / "the-one.db"`)
      via a direct `aiosqlite.connect` that bypasses the singleton cache,
      then `monkeypatch.setattr(db_connection, "_connection", None)` to
      force `get_connection()` to re-open against the patched path on
      next call. Teardown explicitly `await close_connection()` so the
      per-connection `_connection_worker_thread` shuts down on the
      still-running event loop (without that, aiosqlite emits
      `RuntimeError: Event loop is closed` warnings from
      `call_soon_threadsafe` after the loop tears down).
    - 5 tests: `test_e2e_full_lifecycle` (the regression baseline —
      register account → save → acquire → simulate inbound → simulate
      outbound → age + reap → shutdown drain),
      `test_e2e_doctor_probe_returns_default_success` (no
      `doctor_response` → default `"ok"` / `"stub probe ok"`),
      `test_e2e_doctor_probe_returns_configured_response` (knob set →
      verbatim return), `test_e2e_connect_failure_propagates_to_acquire_caller`
      (knob set to `ConnectorConnectionError(...)` → `acquire` re-raises;
      pool empty afterwards), and `test_e2e_multiple_agents_on_same_account_reap_together`
      (two warm entries, `_evict_all_for_account` flushes both).
  - `pool_mod` imported at file top per the design-review fix (not
    function-local).
- **Notes**:
  - **Deviation from the leg artifact's code sample**: the artifact wrote
    schema to `tmp_path / "e2e.db"`. But `settings.db_path` resolves to
    `settings.data_dir / "the-one.db"` (`the_one/config.py:26-27`), so
    schema applied to `e2e.db` is invisible to subsequent
    `get_connection()` calls which open `the-one.db`. Fix: apply schema
    directly to `settings.db_path` (the resolved path) instead. The fixture
    docstring now calls this out explicitly.
  - **Aiosqlite event-loop-closed warnings**: the leg artifact did not
    flag this, but per-test `_connection` recycling without a clean
    `close_connection()` leaks the aiosqlite background worker thread,
    which then tries to call `call_soon_threadsafe` on the torn-down
    asyncio event loop and emits a noisy `PytestUnhandledThreadExceptionWarning`.
    Added `await close_connection()` in the fixture's teardown branch
    (after yield) so the worker thread shuts down on the current loop.
    The session-end fixture in `tests/conftest.py` already closes any
    singleton at session end as a backstop; this fixture closes
    per-test for hygiene.
  - **Lint**: ruff E501 (line-too-long) on the `test_e2e_multiple_agents_on_same_account_reap_together`
    docstring; tightened wording from "Two agents acquire the same account
    → two warm entries → _evict_all_for_account flushes both" to "Two
    agents on one account → two warm entries; _evict_all_for_account
    flushes both" to stay under 100 chars.
  - Verification probes pass:
    - `python -c "from the_one.connectors._stub import ...; assert isinstance(StubPlugin(), ConnectorPlugin); assert isinstance(StubClient(), ConnectorClient)"` → ok.
    - `python -c "from the_one.connectors.registry import types; assert 'stub' not in types()"` → ok.
  - Targeted suite green:
    `docker exec the-one pytest -x --timeout 30 tests/test_connectors_e2e.py`
    → 5 passed in 0.69s.
  - Regression sanity green (no regression in leg 3/4/5/6 surfaces or DB
    layer): `pytest -x --timeout 30 tests/test_connectors.py
    tests/test_connectors_pool.py tests/test_connectors_e2e.py
    tests/test_db_repositories.py tests/test_db_migration.py` →
    149 passed in 12.91s.
  - Full unit suite green: `make test` → 1774 passed, 4 skipped, 375
    deselected (1769 → 1774 = +5 e2e tests; the pre-existing 2 warnings
    in `test_provider_api.py::TestModelDiscovery::test_ollama_models` are
    untouched). 99.88s wall.
  - Lint clean: `make lint` → All checks passed.
  - No tests were skipped, xfailed, or paper-overed. No implementation
    deviations from the leg artifact's behavior contract beyond the two
    fixture refinements noted above.

### Leg 06: lifecycle-pool-reaper-and-drain

- **Status**: landed
- **Started**: 2026-05-16
- **Completed**: 2026-05-16
- **Changes Made**:
  - Extended `the_one/connectors/_pool.py` with the leg-6 surface, mirroring
    `the_one/mcp/_pool.py`'s reaper/drain pattern:
    - Module constants `_DEFAULT_TTL_SECONDS = 1800` (vs MCP's 300s — longer
      because gateway connections have meaningful reconnect cost per the
      flight Design Decisions) and `_REAPER_INTERVAL_SECONDS = 30.0`.
    - Module state `_reaper_task: asyncio.Task[None] | None = None`
      declared after `_shutting_down`.
    - `_RegistryEntry.last_activity: float` field added with
      `field(default_factory=time.monotonic)`. Required adding
      `field` to the existing `dataclasses` import and `os`/`time` to the
      import block. Deliberate divergence from MCP (which reads
      `client.last_activity` on `MCPClient`): the `ConnectorClient`
      Protocol has no such field, and widening the Protocol to add one
      would force every plugin to maintain platform-time tracking when
      the pool's reaper is the only consumer. The pool is the sole
      owner of the lifecycle clock; clients are platform-side opaque
      objects. The deliberate-divergence comment is locked above the
      field declaration.
    - `_resolve_ttl_seconds()` reads `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS`
      at call time (live-read invariant); returns the int when present and
      parseable; falls back to `_DEFAULT_TTL_SECONDS` (with `logger.warning`)
      on non-int. Mirrors `_resolve_ttl_seconds` in `mcp/_pool.py`.
    - `_ensure_reaper_running_locked()` spawns `_reap_loop()` as a Task
      when `_reaper_task is None or _reaper_task.done()`. MUST be called
      under `_lock` per docstring.
    - `_reap_once() -> list[tuple[str, str]]` snapshots expired keys
      under `_lock` (filter: `entry.client is not None and (now -
      entry.last_activity) > entry.ttl_seconds`); evicts each expired
      key OUTSIDE the lock in parallel via `asyncio.gather(...,
      return_exceptions=True)`; logs exceptions other than
      `CancelledError`; returns the list for test purchase.
    - `_reap_loop()` sleeps `_REAPER_INTERVAL_SECONDS`, calls
      `_reap_once()` wrapped in `try/except Exception` so one bad pass
      doesn't kill the loop; on `CancelledError` drains the registry
      concurrently then re-raises.
    - `shutdown_drain()` sets `_shutting_down = True` FIRST; cancels
      `_reaper_task` and awaits with suppressed `CancelledError`;
      belt-and-suspenders gathers `_evict(key)` for any remaining keys;
      resets `_reaper_task = None`.
  - Updated `acquire`: populates `entry.ttl_seconds =
    _resolve_ttl_seconds()` (was the `0` placeholder); calls `await
    _ensure_reaper_running_locked()` UNDER `_lock` after `_pool[key] =
    entry`; updates `entry.last_activity = time.monotonic()` on every
    successful resolution (warm AND cold paths converge in the return
    block).
  - Updated `_clear_for_test`: cancels reaper FIRST (with
    `contextlib.suppress(BaseException)` around the await) and resets
    `_reaper_task = None`, THEN proceeds with the leg-5 worker-cancel
    sequence. `_shutting_down = False` reset preserved at the end.
  - Wired the lifespan integration in `the_one/interfaces/web/app.py`:
    - Added `from the_one.connectors._pool import shutdown_drain as
      _connector_pool_shutdown_drain` in the import block (sorted
      alphabetically between `config` and `db` blocks per ruff I001).
    - Added a `try/except` wrapped `await _connector_pool_shutdown_drain()`
      call between the existing MCP pool drain block and the OAuth
      sweep stop. Comment on-site explains the ordering rationale
      (parallel to MCP; both hold warm network connections; drain
      BEFORE OAuth sweep stop because OAuth is shared infrastructure).
  - Updated `tests/test_connectors_pool.py`:
    - Renamed `test_entry_ttl_seconds_placeholder_is_zero` to
      `test_entry_ttl_seconds_is_resolved_at_acquire_time` and flipped
      the assertion to `entry.ttl_seconds == _DEFAULT_TTL_SECONDS`. This
      is the explicit leg-5 → leg-6 handoff signal called out in the
      leg-5 test's docstring.
    - Added 11 new tests covering the leg-6 contract:
      `test_resolve_ttl_seconds_default_is_1800`,
      `test_resolve_ttl_seconds_reads_env_override`,
      `test_resolve_ttl_seconds_non_int_falls_back`,
      `test_resolve_ttl_seconds_read_at_call_time`,
      `test_acquire_spawns_reaper`,
      `test_reap_once_evicts_idle_entries`,
      `test_reap_once_does_not_evict_fresh_entries`,
      `test_reap_once_skips_entries_mid_connect` (locks the mid-connect
      `client is None` guard),
      `test_acquire_updates_last_activity_on_warm_reuse` (50ms sleep
      between acquires to defeat coarse-clock CI environments — same
      WSL2-resilient pattern called out in the leg spec),
      `test_shutdown_drain_cancels_reaper_and_drains_pool` (asserts pool
      empty, reaper task None, `_shutting_down` True, subsequent acquire
      raises `RuntimeError`),
      `test_clear_for_test_cancels_reaper` (asserts reaper task is None
      after `_clear_for_test`; subsequent acquire spawns a fresh,
      distinct reaper task).
  - Extended `tests/test_mcp_pool.py:528`'s lifespan drain-order spy:
    renamed `test_lifespan_order_pty_drain_before_mcp_drain_before_db_close`
    to `test_lifespan_shutdown_drain_order`; added monkeypatches for
    `_connector_pool_shutdown_drain` AND for
    `the_one.mcp.oauth.start_periodic_sweep` /
    `stop_periodic_sweep` (function-locally imported inside `lifespan`
    so the stub must be on the source module); asserts the full order
    `["pty", "mcp", "connector", "oauth", "db"]`. Captures the OAuth
    sweep stop in the drain-order ordering for the first time —
    previous test only spanned `[pty, mcp, db]`.
- **Notes**:
  - Acceptance criteria met:
    - All 11 new tests + the renamed/flipped handoff test pass.
    - `docker exec the-one pytest -x --timeout 30
      tests/test_connectors_pool.py` → 24 passed (13 leg-5 + 11 leg-6).
    - `docker exec the-one pytest -x --timeout 30 tests/test_mcp_pool.py`
      → 23 passed, 2 deselected (bwrap integration). The renamed
      drain-order test passes with the new 5-step ordering.
    - Full suite green: `make test` → 1769 passed, 4 skipped, 375
      deselected (1758 → 1769 = +11 leg-6 tests; the leg-5 placeholder
      test was renamed in-place, not added). 96.64s wall.
    - Lint clean: `make lint` → All checks passed (one I001
      function-local import sort fix on `_reap_once, _RegistryEntry` —
      ruff sorts case-insensitively).
  - Lifespan integration timing: the flight.md Legs bullet for
    `lifecycle-pool-reaper-and-drain` says the lifespan wiring is
    "documented in code but **wired into `app.py` only in Flight 2**".
    The leg artifact (this leg's authoritative spec) supersedes that
    flight-bullet text — wiring happens this leg per the explicit
    Acceptance Criteria + Implementation Guidance Step 8 + Citation
    Audit entry. The Mission 10 working text on this is: lifespan
    integration belongs with the function that ships, not with the
    flight that first exercises it. The flight.md bullet text is
    superseded by the leg spec; no flight-spec edit needed since the
    bullet text is descriptive narrative, not a normative checklist.
  - `time` was already imported by leg 5's autouse fixture work, but
    was added to `_pool.py`'s import block in this leg (along with `os`
    for `os.environ.get`) since the module did not previously need
    either symbol at runtime.
  - The lifespan drain-order test's monkeypatch of
    `oauth_mod.start_periodic_sweep` to `lambda: None` matters: without
    it, the unmocked start would touch a real event loop and fail
    fast. The `stop_periodic_sweep` mock is the actual drain spy.
  - No tests were skipped, xfailed, or paper-overed. No implementation
    deviations from the leg artifact's behavior contract.

### Leg 05: lifecycle-pool-core

- **Status**: landed
- **Started**: 2026-05-16
- **Completed**: 2026-05-16
- **Changes Made**:
  - Created `the_one/connectors/_pool.py` mirroring `the_one/mcp/_pool.py`'s
    worker-task-per-entry pattern, scoped strictly to the leg-5 deliverable
    set (no `_resolve_ttl_seconds`, no reaper, no `shutdown_drain` — leg 6).
    Includes `_RegistryEntry` dataclass (with `ttl_seconds: int`, `worker`,
    `evict_event`, `client_ready`, `client`, `failure`); module-level
    `_pool: dict[tuple[str, str], _RegistryEntry]`, `_lock: asyncio.Lock`,
    `_shutting_down: bool = False`; and the six functions
    `_load_account(account_id, encryptor)`, `_entry_worker(plugin, account,
    encryptor, entry)`, `_evict(key)`, `_evict_all_for_account(account_id)`,
    `acquire(agent_name, account_id)`, and `_clear_for_test()`.
  - Applied the design-review fix: `acquire` resolves the encryptor ONCE
    via `get_encryptor(settings.data_dir)` and threads it through
    `_load_account(account_id, encryptor)` and `_entry_worker(..., encryptor,
    ...)` so we never double-call `get_encryptor` per acquire. This
    diverges intentionally from `mcp/_pool.py`'s shape where
    `_load_source()` self-resolves the encryptor — the connector divergence
    is documented in the function docstring.
  - Applied M07's test-isolation lesson from day one: `_clear_for_test`
    snapshots `_pool` items under `_lock`, clears, then cancels every
    worker task and awaits it under `contextlib.suppress(BaseException)`;
    sets `_shutting_down = False` at the end. The corresponding test
    (`test_clear_for_test_round_trips_across_iterations`) asserts the
    invariant explicitly.
  - Applied the M09 (cycle-2) race-handling invariant: `_load_account`
    runs OUTSIDE `_lock`; the lock-held branch checks `entry is None`;
    concurrent same-key acquires share the worker via
    `entry.client_ready.wait()` outside the lock; on connect failure the
    waiting caller pops idempotently with `existing is entry` identity
    check before raising. `test_load_account_runs_outside_lock` and
    `test_concurrent_acquire_with_failure_pops_once` lock these.
  - `_evict_all_for_account` snapshots matching keys under `_lock` and
    iterates `_evict` calls OUTSIDE the lock — each `_evict` re-acquires
    the lock for its own pop, so holding the lock across the loop would
    deadlock. Module docstring + the `_evict_all_for_account` body
    comment lock the invariant against future "simplification."
  - Created `tests/test_connectors_pool.py` with 13 tests covering the
    leg-5 contract: lazy-spawn, warm-reuse, concurrent-acquire-shares-
    one-worker (10 concurrent acquires, slow-plugin yields control so
    workers stack on `client_ready`), different-keys-spawn-independent-
    workers, connect-failure-propagates, concurrent-acquire-with-failure-
    pops-once, `_evict` idempotent on missing key, `_evict_all_for_account`
    flushes warm entries, `_clear_for_test` round-trips,
    `_load_account` runs outside lock, entry `ttl_seconds=0` placeholder
    (the leg-5 → leg-6 handoff signal), acquire unknown account type
    raises `ConnectorRegistrationError`, and acquire during shutdown
    raises `RuntimeError`. The 13 tests = the 11 from the leg-spec list
    + the 2 added by design review (`test_load_account_runs_outside_lock`,
    `test_entry_ttl_seconds_placeholder_is_zero`).
  - Autouse fixture `_clear_pool_after_each_test` calls
    `pool_mod._clear_for_test()` AND
    `restore_to_baseline_for_test()` so both pool state and registry
    state reset between tests.
  - Stub plugin (`_StubPlugin`) and stub client (`_StubClient`)
    structurally satisfy the `ConnectorPlugin` (4 methods) and
    `ConnectorClient` (1 method) Protocols without inheriting from them
    (per `agents.md` `structural-Protocol-satisfaction`).
    `_FailingPlugin` subclasses `_StubPlugin` to override only `connect`
    for failure-path scenarios.
- **Notes**:
  - **Deviation from the leg artifact's structural template**: the leg
    artifact code sample imports `the_one.db.connection.get_connection`
    and `the_one.db.repositories.ConnectorAccountRepository` at module
    scope. That triggers a hard ImportError at module-load time on this
    flight's branch: `_pool.py` → `db.repositories` → `agent/__init__.py`
    → `agent.core` → `mcp.errors` → `mcp/__init__.py` (forces loading
    `mcp/_pool.py`) → `mcp/_pool.py` → `db.repositories` which is
    mid-load. `mcp/_pool.py` only works because callers always import
    `the_one.mcp` first (priming the cycle); `connectors/_pool.py` is
    the FIRST module to touch `repositories` from its import chain, so
    the cycle surfaces. Fix: function-local import of
    `get_connection` and `ConnectorAccountRepository` inside
    `_load_account`. Mirrors the existing
    `from the_one.mcp.oauth import build_oauth_provider_for_source`
    function-local pattern at `mcp/_pool.py:196`. The change is
    documented inline in `_load_account`'s docstring.
  - Targeted suite green:
    `docker exec the-one pytest -x --timeout 30 tests/test_connectors_pool.py`
    → 13 passed in 0.09s.
  - Sanity suite green (no regression in MCP pool or connector
    foundation): `pytest -x --timeout 30 tests/test_connectors.py
    tests/test_connectors_pool.py tests/test_mcp_pool.py` → 65 passed,
    2 deselected (the 2 bwrap-only MCP integration tests).
  - Full unit suite green: `make test` → 1758 passed, 4 skipped, 375
    deselected (browser/live/pixel/bwrap, per default `addopts`) in
    103.01s. (1745 → 1758 = +13 new tests, all green.)
  - Lint clean: `make lint` → All checks passed.
  - No tests were skipped, xfailed, or paper-overed.

### Leg 04: registry

- **Status**: landed
- **Started**: 2026-05-16
- **Completed**: 2026-05-16
- **Changes Made**:
  - Created `the_one/connectors/registry.py` with the `ConnectorRegistry`
    class (instance methods `register`, `resolve`, `types`; private
    `_plugins: dict[str, type[ConnectorPlugin]]`). Module-level singleton
    `_registry = ConnectorRegistry()`. Module-level convenience functions
    `register`, `resolve`, `types` delegate to it. `resolve` defensively
    isinstance-checks the produced plugin against `ConnectorPlugin` —
    a class that doesn't structurally satisfy raises
    `ConnectorRegistrationError` (guard for protocol-widening flights).
  - Test seams (explicit functions per project convention, no env-var
    branching): `register_for_test` bypasses the collision check;
    `clear_for_test` HARD-empties `_plugins`; `restore_to_baseline_for_test`
    empties then re-runs `register_builtin_connectors`. Splitting "empty"
    from "production baseline" lets a test mean exactly one without leaking
    implementation knowledge of which builtins exist at this flight's
    checkpoint.
  - `register_builtin_connectors()` ships as a module-level function with
    an empty body in Flight 1 (Flight 8 adds discord, Flight 9 the second
    platform). Called once at module-import time so the singleton is in
    its baseline state from the first dispatch. Runtime import of
    `ConnectorPlugin` (no `TYPE_CHECKING` guard) — `base.py` does not
    import from `registry.py`, so no circular-import risk.
  - Updated `the_one/connectors/__init__.py`: re-exported
    `ConnectorRegistry` from `registry.py`; appended to `__all__` with
    a note that the module-level functions stay at
    `the_one.connectors.registry` (canonical-import discipline; convenience
    re-exports stay narrow).
  - Added `clean_registry` pytest fixture (explicit parameter, not
    autouse) to `tests/test_connectors.py`; uses
    `restore_to_baseline_for_test` before and after yield.
  - Added `TestConnectorRegistry` class (11 tests — the 9 acceptance
    criteria tests + `test_restore_to_baseline_re_runs_builtin_discovery`
    + `test_resolve_rejects_plugin_that_does_not_satisfy_protocol`)
    to `tests/test_connectors.py`. Tests cover: register/resolve round trip,
    unknown-type error, duplicate-register error, sorted types,
    register-for-test bypass, hard-clear semantics, baseline-restore
    semantics, module-level delegation + fresh-instance contract, fresh
    `ConnectorRegistry()` isolation from singleton,
    `register_builtin_connectors` idempotency, and defensive isinstance
    rejection for non-conforming plugins.
- **Notes**:
  - Targeted suite green: `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py` → 29 passed in 0.07s (18 from leg 3 + 11 new).
  - Full unit suite green: `docker exec the-one pytest -x --timeout 30` → 1745 passed, 4 skipped, 375 deselected (browser/live/pixel/bwrap, per default `addopts`) in 98.21s.
  - Lint clean: `docker exec the-one ruff check the_one/ tests/` → All checks passed.
  - Minor textual deviation from the leg artifact's code sample: the
    `reason=` argument inside `resolve`'s instance-check branch had an
    f-string with no placeholders in the artifact
    (`f"instance does not satisfy ConnectorPlugin protocol"`); dropped
    the `f` prefix to satisfy ruff F541. Semantically identical message.
  - No other implementation deviations from the leg artifact's behavior
    contract.

### Leg 03: errors-and-protocol

- **Status**: landed
- **Started**: 2026-05-16
- **Completed**: 2026-05-16
- **Changes Made**:
  - Created `the_one/connectors/` package directory (peer to `the_one/mcp/` and `the_one/tools/`).
  - Added `the_one/connectors/errors.py` with the 6 typed exception classes:
    `ConnectorClientError` (base), `ConnectorConfigError` (account_id +
    validation_message), `ConnectorConnectionError` (plain message),
    `ConnectorAuthRequired` (account_id + optional account_name; `noqa: N818`
    mirroring `MCPAuthRequired`), `ConnectorRegistrationError` (type_name +
    reason), `ConnectorRateLimitError` (account_id + optional
    retry_after_seconds, with two-branch message). Module docstring matches the
    `mcp/errors.py` shape and notes the "grow deliberately" stance.
  - Added `the_one/connectors/base.py` with the 4-method `@runtime_checkable`
    `ConnectorPlugin` Protocol (`connect`, `disconnect`, `doctor`,
    `normalize_session_key`), the 1-method `@runtime_checkable`
    `ConnectorClient` Protocol (`is_alive`), and the 4 supporting frozen-slotted
    dataclasses: `InboundEnvelope` (with `raw: dict[str, Any] = field(hash=False,
    compare=False)`), `OutboundTarget`, `SessionKey`, `DoctorReport` (with
    `details: dict[str, Any] = field(hash=False, compare=False)`). Module
    docstring documents structural-Protocol-satisfaction, the multi-Protocol
    decomposition plan (`AllowlistResolver` + `CommandHandler` lands in flights
    6/7), and the canonical-import discipline.
  - Added `the_one/connectors/__init__.py` with module docstring carrying the
    canonical-import discipline note, re-exports of the public surface, and
    `__all__` declaration listing every re-exported symbol (12 entries: 6
    Protocols/types + 6 exception classes).
  - Added `tests/test_connectors.py` with 4 test classes (18 tests total):
    `TestConnectorExceptions` (8 tests covering subclass chain + each
    exception's args and `__str__` shape), `TestConnectorPluginProtocol` (3
    tests: minimal satisfaction, missing-method failure, no-inheritance
    invariant), `TestConnectorClientProtocol` (2 tests), and
    `TestConnectorPackageExports` (5 tests covering `is`-identity for
    canonical+convenience imports, frozen+constructibility of all 4
    dataclasses, hashability of `InboundEnvelope` and `DoctorReport` despite
    dict fields, and the documented sync-method runtime_checkable limitation).
  - Lint-rule N813 fix: aliased the canonical-vs-convenience import targets in
    the package-exports test to `ViaPackage`/`ViaCanonical`/
    `ExcViaPackage`/`ExcViaCanonical` (CamelCase) rather than the leg
    artifact's lowercased `via_package` etc. Preserves spec intent
    (identity-check between aliased imports) while complying with the project's
    ruff N rule set.
- **Notes**:
  - Targeted suite green: `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py` → 18 passed in 0.04s.
  - Regression suite green: `pytest -x --timeout 30 tests/test_connectors.py tests/test_db_migration.py tests/test_db_repositories.py tests/test_provider_api.py tests/test_encryption.py tests/test_schema.py` → 271 passed in 29.28s.
  - Full unit suite green: `make test` → 1734 passed, 4 skipped, 375 deselected (browser/live/pixel/bwrap per default `addopts`) in 97.13s.
  - Lint clean: `make lint` → All checks passed.
  - Hashability invariant locked: `InboundEnvelope` and `DoctorReport` are
    hashable on their scalar fields (the design-review-caught
    `TypeError: unhashable type: 'dict'` regression has dedicated tests).
  - Known-limitation documented in the suite: a class with a sync
    `def connect(...)` falsely passes `isinstance(obj, ConnectorPlugin)` —
    runtime_checkable checks names only. Test exists so a future reader does
    not expect isinstance to catch async/sync mismatches.
  - No implementation deviations from the leg artifact's behavior contract.

### Leg 02: models-and-repository

- **Status**: landed
- **Started**: 2026-05-16
- **Completed**: 2026-05-16
- **Changes Made**:
  - Bumped `the_one/db/schema.py:CURRENT_VERSION` from 13 to 14.
  - Added v14 migration block in `ensure_schema` after the v13 block: PRAGMA-guarded `ALTER TABLE connector_accounts ADD COLUMN name TEXT NOT NULL DEFAULT ''`, mirroring the v11 ALTER pattern. `INSERT OR IGNORE INTO schema_version (version) VALUES (14)` is LAST before `await conn.commit()` per the v8/v9/v10/v11 idempotency contract.
  - Added `ConnectorAccount` Pydantic model in `the_one/db/models.py` (after `MCPSource`, before `ToolConfig`). Six fields: `id`, `name`, `type: str` (not `Literal` — `CONNECTOR_TYPES` is still empty so a `Literal[*()]` is invalid Python), `config`, `secrets`, `created_at`, `updated_at`. No `merged_config()` helper (deferred per flight Design Decisions). No `_normalize_*` validator (no `__MASKED__` handling at this layer). Module-level explanatory comment block before the class documents the deferred `Literal` narrowing for flight 08.
  - Added `ConnectorAccountRepository` in `the_one/db/repositories.py` (after `MCPSourceRepository`, before `ToolConfigRepository`). Mirror of MCP shape: `__init__(conn, encryptor)` with encryptor-as-reference; `_secrets_to_ciphertext` / `_ciphertext_to_secrets` (tolerant `InvalidToken → {}`, `JSONDecodeError` propagates); `list` (ORDER BY name), `get`, `create`, `update`, `delete` (raise `KeyError(f"Connector account not found: {account_id}")` on missing row); `_row_to_model`. No `find_by_runtime_package` analog. Added `ConnectorAccount` to the existing `from the_one.db.models import ...` block.
  - Added `TestSchemaV14` class (3 tests) to `tests/test_db_migration.py` at the end of the file: `test_v14_fresh_db_includes_name_column` (PRAGMA `notnull=1` and `dflt_value="''"` assertions); `test_v14_migration_idempotent_on_rerun` (second `ensure_schema` produces exactly one v14 schema_version row); `test_v14_preserves_v13_seeded_row_with_empty_name` (hand-builds a v13-shape `connector_accounts` table without `name`, seeds a row via SQL, runs `ensure_schema`, asserts `name == ''` post-migration — modeled on `TestMigrationV12.test_v12_real_v11_to_v12_upgrade`).
  - Added `connector_repo_encryptor` and `connector_repo` fixtures to `tests/test_db_repositories.py` after the corresponding MCP fixtures. Function-scoped per the same in-file comment guidance.
  - Added `TestConnectorAccountRepository` class (8 tests) to `tests/test_db_repositories.py` after `TestMCPSourceRepository`. Parallel to the MCP class minus the `merged_config` test (we don't ship that helper). Added `ConnectorAccount` + `ConnectorAccountRepository` to the existing import lines at the top of the file.
  - Expected-and-tracked brittle-test updates triggered by the `CURRENT_VERSION` bump:
    1. `tests/test_db_migration.py:227` — `TestSchemaV8` regression-loud-fail guard updated from `assert CURRENT_VERSION == 13` to `== 14`; message string and surrounding comment mention v14 = `name` column on `connector_accounts`. Tracked here (not as a "pre-existing brittle test surfaced" discovery) because the leg artifact called this out explicitly.
    2. `tests/test_db_migration.py:1166` — `TestSchemaV13.test_v13_connector_accounts_has_expected_columns_and_no_check_constraint` asserts post-`ensure_schema` column shape; the set now includes `name` (it asserts current-version shape, not "shape if we stopped at v13"). Test docstring updated to acknowledge the v14 addition and the v15 renumbering for Flight 8's CHECK migration.
  - Flight spec text updated: every reference to "v14 in Flight 8" / "v13 → v14 will need a table-rename ceremony in Flight 8" now reads "v15 in Flight 8" with a parenthetical noting that v14 is claimed by leg 02's `name` column. Three edit locations: Design Decisions block ("Schema version increments from 12 to 13"), the immediately-following trade-off bullet, and the Technical Approach bullet on `db/schema.py`.
- **Notes**:
  - Targeted suite green: `docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py::TestSchemaV14 tests/test_db_repositories.py::TestConnectorAccountRepository` → 11 passed in 1.43s.
  - Leg-1 rotation tests still green post-v14 (the raw-SQL `INSERT INTO connector_accounts (id, type, config, secrets)` falls through to the `name DEFAULT ''` clause cleanly — no test edits needed): `pytest -x --timeout 30 tests/test_provider_api.py::TestEncryptionRotation -k connector` → 2 passed.
  - Broader-targeted suite green: `pytest -x --timeout 30 tests/test_db_migration.py tests/test_db_repositories.py tests/test_provider_api.py tests/test_encryption.py tests/test_schema.py` → 253 passed in 29.89s.
  - Full unit suite green: `docker exec the-one pytest -x --timeout 30 tests/` → 1716 passed, 4 skipped, 375 deselected (browser/live/pixel/bwrap, per default `addopts`) in 100.09s.
  - Lint clean: `docker exec the-one ruff check the_one/ tests/` → All checks passed.
  - No implementation deviations from the leg artifact's behavior contract.

### Leg 01: schema-and-migration

- **Status**: landed
- **Started**: 2026-05-16
- **Completed**: 2026-05-16
- **Changes Made**:
  - Created `the_one/db/_connector_types.py` exporting `CONNECTOR_TYPES: tuple[str, ...] = ()` with the three-layer-agreement docstring mirroring `_provider_types.py`.
  - Bumped `the_one/db/schema.py:CURRENT_VERSION` from 12 to 13.
  - Added v13 migration block in `ensure_schema` creating the `connector_accounts` table (id TEXT PK, type TEXT NOT NULL [NO CHECK], config TEXT DEFAULT `'{}'`, secrets TEXT DEFAULT `'{}'`, created_at, updated_at). Individual `await conn.execute(...)` calls per the v10/v11 idempotency contract; `INSERT OR IGNORE INTO schema_version` LAST.
  - Extended `the_one/interfaces/web/api.py:rotate_encryption_key`: added SELECT/tolerant-decrypt loop for `connector_accounts.secrets` after the MCP path, added `reencrypted_connectors` list alongside `reencrypted_mcps`, added a third UPDATE loop inside the existing try/commit/except/rollback so all three corpora commit atomically under a single `conn.commit()`. Updated docstring to reference three corpora; updated the in-function comment from "BOTH tables" to "ALL THREE tables".
  - Added `TestSchemaV13` class (3 tests) to `tests/test_db_migration.py` modeled on `TestSchemaV11` — fresh-DB shape + no-CHECK verification (insert bogus type succeeds) + idempotent rerun.
  - Added two rotation tests to `tests/test_provider_api.py::TestEncryptionRotation`: `test_rotate_connector_account_secrets` (seed via raw SQL → rotate → verify ciphertext decrypts under new key) and `test_rotate_preserves_connector_secrets_on_db_failure` (seed all three corpora → patch `aiosqlite.Connection.commit` with `RuntimeError` → verify all three ciphertexts roll back byte-identical and the on-disk key file is unchanged).
  - Pre-existing test brittleness surfaced and fixed (not in the leg's Files Affected list, but a direct consequence of the CURRENT_VERSION bump):
    1. `tests/test_db_migration.py:226` (in `TestSchemaV8.test_v8_fresh_db_includes_tool_configs_and_tool_overrides`) had a hardcoded `assert CURRENT_VERSION == 12` — explicitly self-described as a regression-loud-fail guard meant to be updated on every schema bump. Updated to 13 and the docstring/comment now mentions the v13 connector_accounts migration.
    2. `tests/test_db_migration.py:1062` (in `TestMigrationV12.test_v12_recovers_from_partial_apply_with_orphan_temp_table`) deleted only `schema_version WHERE version = 12` to rewind, which worked while v12 was head but no longer rewinds the migration loop now that v13 exists (MAX(version) stays at 13). Changed to `WHERE version >= 12` mirroring the v11 rewind idiom; the orphan temp table is still produced and the v12 DROP-IF-EXISTS prelude is still exercised.
- **Notes**:
  - Targeted suite green: `pytest -x --timeout 30 tests/test_db_migration.py tests/test_provider_api.py tests/test_encryption.py tests/test_schema.py` → 190 passed in 23.04s.
  - Full unit suite green: `pytest -x --timeout 30 tests/` → 1705 passed, 4 skipped, 375 deselected (browser/live/pixel/bwrap, per default `addopts`) in 102.61s.
  - Lint clean: `ruff check the_one/ tests/` → All checks passed.
  - The v12 block ends the function (no explicit `return`), so the v13 block was appended as the final statement in `ensure_schema`.
  - Tolerant decrypt was added even though the table is brand new in v13 — kept symmetric with the MCP path per leg artifact guidance, so a future column-default migration on existing rows is already handled.
  - No tests were skipped, xfailed, or paper-overed; no implementation deviations from the leg artifact's behavior contract.

---

## Decisions

_(append runtime decisions not captured in the flight spec)_

---

## Deviations

_(append departures from the planned approach)_

---

## Anomalies

_(append unexpected issues encountered)_

---

## Session Notes

_(chronological notes during execution)_
