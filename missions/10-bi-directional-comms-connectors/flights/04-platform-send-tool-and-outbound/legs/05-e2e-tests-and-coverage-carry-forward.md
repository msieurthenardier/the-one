# Leg: e2e-tests-and-coverage-carry-forward

**Status**: completed
**Flight**: [Platform-Send Built-in Tool and Outbound Routing](../flight.md)

## Objective

Land the F4 e2e coverage and three carry-forward maintenance items, AND close the `AgentConfig.connector_account_ids` persistence gap discovered in leg 4. Specifically:

1. **(NEW — leg-4 deviation closure)** Add a v17 schema migration `ALTER TABLE agents ADD COLUMN connector_account_ids TEXT` and wire `SQLiteAgentStore.save` + `_row_to_config` to round-trip the field. Renumber Flight 8's planned CHECK migration from v17 to v18. Remove the leg-4 monkeypatch workaround in `_make_scripted_factory`.
2. **(F4 mandate)** Pin both mission-mandated invariants end-to-end via a new `tests/test_connectors_e2e_platform_send.py`: enabled-state platform-send delivers; disabled-state preserves operator-only inbound flow.
3. **(F4 mandate)** Add three regression nets: target validation rejects unattached accounts; pool dispatch happy path with `last_activity` touch verification; plugin-resolve-failure regression net (F1 debrief carry-forward — the dispatcher's "deliberately redundant" plugin-resolve catch at `_inbound.py:147-156` becomes covered).
4. **(F3 debrief carry-forward)** Extract the in-file helpers (`isolated_db`, `_seed_provider_and_agent`, `_seed_stub_account`, `_make_factory`, `_envelope`, `_ScriptedProvider`, `_make_scripted_factory`) from `tests/test_connectors_inbound.py` and `tests/test_connectors_e2e_session.py` into a new `tests/_connector_dispatch_helpers.py` module so the new `test_connectors_e2e_platform_send.py` is the THIRD consumer (the F3 debrief explicitly flagged this trigger).
5. **(Sixth-consecutive-flight carry-forward)** Verify whether the 2 `AsyncMock-never-awaited` warnings on `tests/test_provider_api.py::TestModelDiscovery::test_ollama_models` still fire — if yes, fix; if no (already silently closed by F5 L01.5's short-circuit), retire the carry-forward at the test docstring.

## Context

### Leg-4 deviation: `AgentConfig.connector_account_ids` persistence gap

- Leg 4's flight-log Deviation block describes the gap: F4 L1 added `connector_account_ids: list[str] = Field(default_factory=list)` to the Pydantic model BUT did NOT extend the `agents` SQLite table or `SQLiteAgentStore.save`/`_row_to_config`. Leg 4's tests worked around this by monkey-patching `SQLiteAgentStore._row_to_config` to re-inject the field after the DB read.
- F8 (Discord) cannot ship without this persistence: an operator attaching a Discord account to an agent via the Studio UI will see the change discarded on every save/load round-trip.
- Leg 5 is the natural home because (a) leg 5 already writes new e2e tests against `SQLiteAgentStore`-backed agents, (b) leaving the monkeypatch in place after leg 4 is a known-debt anti-pattern, (c) the schema renumber is a single migration with established v8/v9/v10 idempotency pattern, (d) the alternative — punting to a maintenance leg between F4 and F5 — adds an out-of-flight migration that disrupts the agentic-workflow batched-review model.
- Schema-version arithmetic: F3 L1 landed v16. F4 L5 (this leg) takes v17. Flight 8's CHECK migration (previously v17 per the F3 plan, after F2 bumped it from v16) renumbers to **v18**. Renumber sites enumerated by full grep (`grep -n 'v17' the_one/ tests/`): `agents.md:290` checklist item 4; `_connector_types.py:12, 16` docstring; `tests/test_db_migration.py:233` (CURRENT_VERSION assertion); `tests/test_db_migration.py:1170, 1178` (TestSchemaV13 docstring — reviewer-surfaced; missed in initial design); `tests/test_db_migration.py:1261, 1424, 1592` (TestSchemaV14/V15/V16 downstream-renumber docstrings); plus the comments in `the_one/db/schema.py:547, 587`. The leg-5 implementer runs `grep -n 'v17\|v18' the_one/ tests/` post-edit as a final sweep to catch any drift.

### F4 mission-mandated invariants (`flight.md` criteria #13 + #14)

The mission text:
- **Criterion #13** (enabled state): "The platform-send capability is a built-in tool ... When enabled, the tool is auto-available to any agent attached to a connector account ... when disabled, no agent on the system can send to any platform."
- **Criterion #14** (disabled state): "When the platform-send tool is disabled but a connector account is otherwise wired up, inbound platform messages are still received, persisted to the session, and visible to the operator in Chat ... but no mechanism exists to send anything back to the platform. From the peer's perspective the bot is silent; from the operator's perspective the inbound flow is intact. Re-enabling the tool restores outbound without re-configuring the connector account or restarting any session."

Both states require end-to-end exercise — the existing leg-3 factory tests cover the carve-out at the registry level; the leg-4 dispatcher tests cover the visibility tagging; leg 5 ties them together via real `agent.step()` driving a real `SendToPlatformChannelTool.execute()` against the F1 pool against the StubPlugin.

### F1 debrief carry-forward: "deliberately redundant" plugin-resolve catch

`_inbound.py:147-156` carries a defensive second `try/except ConnectorRegistrationError:` block — the comment explicitly says "Do NOT 'simplify' by removing." The path is dead in the happy case (pool_acquire would have raised on unknown type already), but flips active if a future refactor changes the pool's error surface. F1 debrief recommendation #6 flagged this as uncovered; leg 5 adds the regression net.

### F3 debrief carry-forward: test-helper extraction

F3 debrief action item: "Extract leg-4 + leg-6 test helpers (`isolated_db`, `_seed_provider_and_agent`, `_seed_stub_account`, `_make_factory`, `_envelope`, autouse cleanup) to `tests/conftest.py` or a `tests/connectors_dispatch_helpers.py` module. Leg-6 divergence (`session_continuation_seconds` kwarg) is the leading indicator." F4 L4 added `_ScriptedProvider` and `_make_scripted_factory`, increasing the divergence pressure. Leg 5 (the THIRD consumer) is the natural extraction point.

### AsyncMock-never-awaited carry-forward

The architect at flight-design time surfaced that an F5 L01.5 short-circuit at `tests/test_provider_api.py:1294-1298` may have silently closed the 2 RuntimeWarnings. Leg 5 verifies with `-W error::RuntimeWarning` before applying any fix. Two outcomes:
- **Warning still fires**: apply the smaller fix (`await mock(...)` or replace AsyncMock with MagicMock); pin via docstring.
- **Warning gone**: formally retire the carry-forward at the test docstring with a comment retraction AND a `[methodology]` note in the flight debrief noting it was silently closed by an intervening fix.

### Other contextual decisions

- **State-machine reachability audit**: the v17 migration adds an OPTIONAL TEXT column on `agents`. No existing tests assert "agents table has exactly N columns" (verified via grep). The brittle `TestSchemaV8::test_v8_fresh_db_includes_tool_configs_and_tool_overrides` asserts `CURRENT_VERSION == 16` — must bump to 17. `TestSchemaV16` and earlier `TestSchemaV*` classes use `assert max(versions) == CURRENT_VERSION` which dynamically tracks the head — those continue to pass.
- **Cache freshness contract**: the `agents` row is read on every `AgentFactory.create()` call (per F2/F3 session-bound freshness contract). After leg 5, the operator's Studio attach change to `connector_account_ids` takes effect at the NEXT `factory.create()` — matching MCP attachment mid-session-change semantics that leg 3's design documented.
- **`SQLiteAgentStore.save` is upsert via `ON CONFLICT(name) DO UPDATE SET`** (verified at `db/repositories.py:104-116`). The new column needs to be in both the INSERT column list AND the `ON CONFLICT` update list. Mirror the existing `mcp_source_ids` handling at L113, L128.
- **The factory's `_load_config` calls `store.load(name)` which returns the `AgentConfig` via `_row_to_config`** (verified at `factory.py:_load_config`). After leg 5, `factory.create()` sees the persisted `connector_account_ids` on every invocation — no monkeypatch needed.
- **Tests that hand-build pre-v17 schema fixtures**: per the F3 debrief two-pass-planning-grep convention's ALTER-on-previously-untouched-table addendum (codified post-F3), check whether any tests build the `agents` table by hand. Grep `tests/` for `CREATE TABLE agents` and `INSERT INTO agents` to enumerate.

## Inputs

State that must exist before this leg runs:

- F4 branch `flight/04-platform-send-tool-and-outbound`; legs 1+2+3+4 uncommitted work in place.
- `the_one/agent/config.py:AgentConfig.connector_account_ids` field exists (leg 1 output).
- `the_one/tools/connector_send.py:SendToPlatformChannelTool` exists (leg 2 output).
- `the_one/agent/factory.py:AgentFactory.create()` has the F10 baseline carve-out logic for the platform-send tool (leg 3 output).
- `the_one/connectors/_inbound.py:dispatch_inbound` performs post-step visibility tagging (leg 4 output).
- `the_one/db/schema.py:11 — "CURRENT_VERSION = 16"` — F3 L1's head version.
- `the_one/db/repositories.py:SQLiteAgentStore.save` (~L94-135) — current INSERT/UPDATE statement without `connector_account_ids`.
- `the_one/db/repositories.py:_row_to_config` (~L188-207) — current read path without `connector_account_ids`.
- `the_one/db/_connector_types.py:12, 16` — docstring v17 references.
- `the_one/db/schema.py:547, 587` — comments mentioning Flight 8 → v17.
- `the_one/agents.md:290` — connector-type checklist item 4 mentioning v17.
- `tests/test_db_migration.py:233 — "assert CURRENT_VERSION == 16"` — brittle assertion.
- `tests/test_db_migration.py:1261, 1424, 1592` — TestSchemaV14/V15/V16 downstream-renumber docstrings.
- `tests/test_connectors_inbound.py` has the leg-4 monkeypatch in `_make_scripted_factory` for `SQLiteAgentStore._row_to_config` re-injection of `connector_account_ids`.
- `tests/test_connectors_inbound.py` `_ScriptedProvider`, `_make_scripted_factory` from leg 4 — to be extracted to `_connector_dispatch_helpers.py`.
- `tests/test_connectors_inbound.py` in-file helpers (`isolated_db`, `_seed_provider_and_agent`, `_seed_stub_account`, `_make_factory`, `_envelope`) from F3 L4.
- `tests/test_connectors_e2e_session.py` — current 8-test file consuming the same helpers via copy-paste from F3 leg 4.
- `tests/test_provider_api.py:1275-1311 (test_ollama_models)` — sixth-consecutive-flight AsyncMock-warning carry-forward.
- `the_one/connectors/_pool.py:acquire (L407)` — touches `last_activity` per call; leg 5's pool-touch test snapshots before/after.

## Outputs

State that must exist after this leg completes:

### Sub-leg A — Agent persistence gap fix (v17 migration)

- `the_one/db/schema.py`: `CURRENT_VERSION` bumped to 17; new `if version < 17:` migration block adds `ALTER TABLE agents ADD COLUMN connector_account_ids TEXT` with the v8/v9/v10/v11/v14/v15 PRAGMA-guarded ALTER ADD COLUMN idempotency pattern. `INSERT OR IGNORE INTO schema_version (version) VALUES (17)` LAST.
- `the_one/db/repositories.py:SQLiteAgentStore.save`: extends the INSERT column list with `connector_account_ids`; extends the VALUES list with `json.dumps(config.connector_account_ids)`; extends the `ON CONFLICT DO UPDATE SET` block with `connector_account_ids=excluded.connector_account_ids`. Mirror `mcp_source_ids` (L113, L128).
- `the_one/db/repositories.py:SQLiteAgentStore._row_to_config`: extends the `AgentConfig(...)` constructor with `connector_account_ids=json.loads(row["connector_account_ids"] or "[]")`. Mirror the `mcp_source_ids` line at L200.
- `the_one/db/_connector_types.py:12, 16`: v17 → v18 in docstring (Flight 8's CHECK migration renumbered).
- `the_one/db/schema.py:547, 587`: v17 → v18 in inline comments referencing Flight 8.
- `the_one/agents.md:290`: connector-type checklist item 4 updated. v17 → v18 for Flight 8's CHECK. Add a new line for F4 L5's v17.
- `tests/test_db_migration.py:233`: `assert CURRENT_VERSION == 16` → `assert CURRENT_VERSION == 17`; error-message string mentions F4 L5's v17 migration.
- `tests/test_db_migration.py:1261, 1424, 1592`: TestSchemaV14/V15/V16 docstrings updated to "renumbers to v18".
- NEW `tests/test_db_migration.py::TestSchemaV17` class mirroring `TestSchemaV16`'s shape:
  - `test_v17_fresh_db_includes_agents_connector_account_ids_column` — fresh DB at v17 has the column.
  - `test_v17_legacy_v16_row_decodes_with_empty_connector_account_ids` — a v16 row migrated to v17 has the column nullable and the `_row_to_config` reads it as `[]`.
  - `test_v17_idempotent_re_apply` — re-running v17 against v17 is a no-op.
- `tests/test_db_repositories.py` — extended with `test_save_round_trips_connector_account_ids` and `test_load_pre_v17_agent_has_empty_connector_account_ids` (the back-compat case for agents persisted before the migration ran).
- Leg-4 monkeypatch removal: `tests/test_connectors_inbound.py` (or wherever `_make_scripted_factory` lands after sub-leg C) NO LONGER monkeypatches `SQLiteAgentStore._row_to_config`. The `connector_account_ids` kwarg on `_seed_provider_and_agent` now flows through to the persisted row naturally.

### Sub-leg B — E2E tests (`tests/test_connectors_e2e_platform_send.py`)

NEW test file with the following test functions:

- `test_e2e_enabled_state_platform_send_delivers` (mission criterion #13):
  - Seed agent with `connector_account_ids=["acct-test"]`; tool operator-enabled (default since no `ToolConfig` row inserted); register StubPlugin; stub account in DB.
  - Use `_ScriptedProvider` returning ONE tool_call to `send_to_platform_channel` with valid args, then a plain-text end response.
  - Dispatch an inbound envelope.
  - Assert: `StubPlugin.outbound_records` contains exactly `(OutboundTarget(channel_id="c1", thread_id=None), "<expected content>")`.
  - Assert: in the persisted session history, the assistant tool_call message has `visibility=OPERATOR_VISIBILITY`; the tool_result message has `visibility=None`.
  - Assert: the agent's loaded schemas (snapshot at factory time) include `send_to_platform_channel`. (Sanity check that leg 3's carve-out fired.)
  - Assert: the agent's system prompt (snapshot at factory time) contains the enabled-tool directive substring.
- `test_e2e_disabled_state_inbound_received_no_outbound` (mission criterion #14):
  - Seed agent with `connector_account_ids=["acct-test"]`; `ToolConfig(name="send_to_platform_channel", enabled=False)` injected (operator-disabled); register StubPlugin; stub account in DB.
  - Use `_ScriptedProvider` returning ONE plain-text response (the agent can't call the tool because it's not in the registry).
  - Dispatch an inbound envelope.
  - Assert: `StubPlugin.outbound_records` is EMPTY (no platform delivery).
  - Assert: the inbound user message is persisted with `visibility=None` (peer-visible — the operator sees it in Chat).
  - Assert: the agent's assistant reply is persisted with `visibility=OPERATOR_VISIBILITY` (operator console only).
  - Assert: the agent's loaded schemas (snapshot at factory time) does NOT include `send_to_platform_channel`.
  - Assert: the agent's system prompt (snapshot at factory time) contains the DISABLED-tool directive substring.
- `test_e2e_disabled_to_enabled_re_dispatch_restores_outbound` (mission criterion #14 — "Re-enabling the tool restores outbound without re-configuring the connector account or restarting any session"):
  - Start with operator-disabled state. Dispatch one inbound; verify zero outbound.
  - Mid-test, flip the operator switch: update `ToolConfigRepository` to set `enabled=True` for `send_to_platform_channel`.
  - Dispatch a SECOND inbound (which rebuilds the agent via `factory.create()` per F3 L4).
  - Assert: the second inbound's agent has `send_to_platform_channel` in its loaded schemas; the agent now calls it; `outbound_records` captures the delivery.
  - No restart of the StubPlugin, no re-seeding of the account, no monkey-patching mid-test.
- `test_e2e_target_validation_rejects_unattached_account` (mission criterion #15):
  - Seed agent with `connector_account_ids=["acct-A"]`; seed TWO stub accounts (`acct-A` and `acct-B`); register StubPlugin.
  - Use `_ScriptedProvider` returning a tool_call where `target.account_id = "acct-B"` (the unattached one).
  - Dispatch an inbound for `acct-A`.
  - Assert: the tool_result content starts with `[error] [constraint] account_id 'acct-B' is not attached to this agent`.
  - Assert: NO pool acquire was attempted on `acct-B` (monkeypatch `connectors._pool.acquire` to count calls; assert calls for `acct-A` only).
  - Assert: `StubPlugin.outbound_records` does NOT contain the failed-target's content.
- `test_e2e_pool_acquire_touches_last_activity_on_outbound`:
  - Seed agent with `connector_account_ids=["acct-test"]`; tool enabled.
  - Use `_ScriptedProvider` with tool_call response.
  - Snapshot the pool entry's `last_activity` BEFORE dispatch.
  - Dispatch an inbound; the agent calls the tool; the tool calls `pool_acquire`.
  - Snapshot AFTER dispatch.
  - Assert: `after > before`. This is the F3 ratification's additive verification for the outbound path (the F3 inbound path's `last_activity` touch is already verified in `test_connectors_inbound.py::test_dispatch_inbound_touches_pool_last_activity`).
- `test_e2e_plugin_resolve_failure_dispatcher_logs_and_returns` (F1 debrief carry-forward — covers the dispatcher's "deliberately redundant" plugin-resolve catch at `_inbound.py:147-156`):
  - Seed agent + stub account; register StubPlugin (so pool acquire succeeds).
  - Mock `connectors._inbound.registry.resolve` (the second-pass resolve at `_inbound.py:148`) to raise `ConnectorRegistrationError("test failure")`.
  - Dispatch an inbound.
  - Assert: the function returns cleanly (no exception bubbles up to caller).
  - Assert: a WARNING/ERROR log entry mentioning the failed resolve type was emitted (use `caplog`).
  - Assert: NO new chat_sessions row is created (the dispatcher returned before reaching the session-resolution step).

### Sub-leg C — Test-helper extraction to `tests/_connector_dispatch_helpers.py`

NEW module `tests/_connector_dispatch_helpers.py` containing:
- `isolated_db` (pytest fixture)
- `_seed_provider_and_agent(...)` (helper function with the `connector_account_ids` kwarg)
- `_seed_stub_account(...)` (helper function)
- `_make_factory()` (helper function)
- `_envelope(...)` (helper function)
- `_ScriptedProvider(LLMProvider)` (stateful test-only provider class)
- `_make_scripted_factory(...)` (helper function — leg-4 monkeypatch removed once sub-leg A lands the real persistence)
- Any autouse cleanup fixtures (`_reset_stub_state`, `_clear_pool_locks_registry`) that the three consumer test files share

Three consumer files update their imports:
- `tests/test_connectors_inbound.py` — remove the in-file definitions; `from tests._connector_dispatch_helpers import (...)` instead.
- `tests/test_connectors_e2e_session.py` — remove the copy-pasted definitions; `from tests._connector_dispatch_helpers import (...)` instead.
- `tests/test_connectors_e2e_platform_send.py` (new this leg) — import from the new helpers module.

**Pytest fixture-discovery note**: a fixture defined in a non-`conftest.py` module is NOT auto-discovered by pytest. The helpers module exposes the fixture as a function `isolated_db` decorated `@pytest.fixture`; each consumer test file imports it directly and uses it as a function argument. If pytest fails to register the fixture (verify on first run), fall back to defining the fixture in `tests/conftest.py` and the helper functions in `_connector_dispatch_helpers.py` separately. Either shape works.

### Sub-leg D — AsyncMock-warning carry-forward closure

- Run `docker exec the-one pytest tests/test_provider_api.py::TestModelDiscovery::test_ollama_models -W error::RuntimeWarning` to verify warning state.
- **If warning still fires** (`AsyncMockMixin._execute_mock_call` reports never-awaited):
  - Apply the smallest fix: either `await mock(...)` in the test body OR replace `AsyncMock` with `MagicMock` where no await is expected.
  - Pin the contract with a docstring comment so future flights don't reintroduce the warning.
- **If warning is gone**:
  - Retire the carry-forward at the test docstring with a comment retraction.
  - Add a `[methodology]` note in the flight log explaining the F5 L01.5 short-circuit closed the warning silently.
- Flight log entry captures the outcome regardless.

### Flight log + status

- Flight log gains a "Leg Progress: e2e-tests-and-coverage-carry-forward" entry covering all four sub-legs.
- Leg status flipped to `landed`.

## Acceptance Criteria

### Sub-leg A — Persistence

- [ ] `the_one/db/schema.py:CURRENT_VERSION` is `17` (was 16).
- [ ] A new `if version < 17:` migration block exists in `ensure_schema` adding `connector_account_ids TEXT` to `agents` table via the PRAGMA-guarded ALTER ADD COLUMN pattern.
- [ ] Migration block has `INSERT OR IGNORE INTO schema_version (version) VALUES (17)` LAST before commit.
- [ ] `SQLiteAgentStore.save` includes `connector_account_ids` in the INSERT column list, VALUES list, and ON CONFLICT update list.
- [ ] `SQLiteAgentStore._row_to_config` reads `connector_account_ids=json.loads(row["connector_account_ids"] or "[]")`.
- [ ] `tests/test_db_migration.py::TestSchemaV8::test_v8_*` assertion `assert CURRENT_VERSION == 16` updated to `== 17`; error message references the F4 L5 migration.
- [ ] `tests/test_db_migration.py::TestSchemaV13` docstring (L1170, L1178) updated for the v17 → v18 renumber.
- [ ] `tests/test_db_migration.py::TestSchemaV14`, `TestSchemaV15`, `TestSchemaV16` docstrings updated for the v17 → v18 renumber.
- [ ] `the_one/db/_connector_types.py:12, 16` docstring updated: v17 → v18 (Flight 8's CHECK migration).
- [ ] `the_one/db/schema.py:547, 587` inline comments updated: v17 → v18.
- [ ] `the_one/agents.md:290` connector-type checklist item 4: v17 → v18 for Flight 8's CHECK; F4 L5's v17 added as a new bullet.
- [ ] NEW `TestSchemaV17` class in `tests/test_db_migration.py` with at least three tests: fresh-DB column presence, legacy-v16-row decodes with empty list, idempotent re-apply.
- [ ] NEW `test_save_round_trips_connector_account_ids` + `test_load_pre_v17_agent_has_empty_connector_account_ids` in `tests/test_db_repositories.py`.
- [ ] Leg-4 monkeypatch on `SQLiteAgentStore._row_to_config` REMOVED from `_make_scripted_factory`.

### Sub-leg B — E2E tests

- [ ] NEW `tests/test_connectors_e2e_platform_send.py` exists with 6 tests: enabled-state, disabled-state, disabled-to-enabled re-dispatch, target-validation, pool-acquire-touches-last_activity, plugin-resolve-failure.
- [ ] Each test passes via `docker exec the-one pytest tests/test_connectors_e2e_platform_send.py -x --timeout 30`.
- [ ] The enabled-state test asserts: `StubPlugin.outbound_records` populated, tool_result `visibility=None`, assistant `visibility=OPERATOR_VISIBILITY`, enabled-directive in system prompt.
- [ ] The disabled-state test asserts: `outbound_records` EMPTY, inbound user `visibility=None`, assistant reply `visibility=OPERATOR_VISIBILITY`, disabled-directive in system prompt, schema NOT in loaded set.
- [ ] The re-enable test asserts the second inbound's outbound delivery without any in-test restart or re-registration.
- [ ] The target-validation test asserts `[error] [constraint]` envelope, no pool acquire on the wrong account, empty `outbound_records`.
- [ ] The pool-touch test asserts `after > before` on `last_activity`.
- [ ] The plugin-resolve-failure test asserts clean return + log entry + no session row created.

### Sub-leg C — Helper extraction

- [ ] NEW `tests/_connector_dispatch_helpers.py` exists with the seven helper symbols (plus fixtures).
- [ ] `tests/test_connectors_inbound.py` imports the helpers from `_connector_dispatch_helpers`; the in-file definitions are REMOVED.
- [ ] `tests/test_connectors_e2e_session.py` imports the helpers; the copy-pasted definitions are REMOVED.
- [ ] `tests/test_connectors_e2e_platform_send.py` imports the helpers (no in-file copies).
- [ ] No regression: `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_e2e_platform_send.py -x --timeout 30` passes.

### Sub-leg D — AsyncMock-warning closure

- [ ] EITHER: the warning is verified-still-firing AND fixed (await applied OR AsyncMock replaced); or: the warning is verified-already-closed AND the carry-forward formally retired (test docstring updated).
- [ ] `docker exec the-one pytest tests/test_provider_api.py::TestModelDiscovery::test_ollama_models -W "error::RuntimeWarning:unittest.mock" -x --timeout 30` passes.
- [ ] Flight log captures the outcome (fix-applied or retired-silently).

### Overall

- [ ] `docker exec the-one pytest -x --timeout 30` (full suite) passes. No regression on F1/F2/F3/F4 surfaces, legs 1-4 surfaces.
- [ ] `docker exec the-one ruff check the_one tests` clean.
- [ ] Flight log gains a "Leg Progress: e2e-tests-and-coverage-carry-forward" entry covering all four sub-legs.
- [ ] Leg `**Status**` → `landed`.

## Verification Steps

- `docker exec the-one pytest tests/test_db_migration.py::TestSchemaV17 -v -x --timeout 30` — new v17 tests pass.
- `docker exec the-one pytest tests/test_db_migration.py::TestSchemaV8 tests/test_db_migration.py::TestSchemaV14 tests/test_db_migration.py::TestSchemaV15 tests/test_db_migration.py::TestSchemaV16 -v -x --timeout 30` — existing brittle assertions updated, all pass.
- `docker exec the-one pytest tests/test_db_repositories.py -v -x --timeout 30` — new persistence round-trip tests pass.
- `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_e2e_platform_send.py -v -x --timeout 30` — helper extraction + new e2e tests pass.
- `docker exec the-one pytest tests/test_provider_api.py::TestModelDiscovery::test_ollama_models -W error::RuntimeWarning -x --timeout 30` — passes (warning verified fixed OR confirmed-gone).
- `docker exec the-one pytest -x --timeout 30` — full suite green.
- `docker exec the-one ruff check the_one tests` — clean.
- `grep -n 'v17\|v18' the_one/db/_connector_types.py the_one/agents.md the_one/db/schema.py tests/test_db_migration.py | head -20` — verify the renumber landed coherently.
- `grep -n 'monkeypatch\.setattr.*_row_to_config' tests/` — should return ZERO matches (the leg-4 workaround is gone).

## Implementation Guidance

1. **Sub-leg A.1 — Schema migration** (in `the_one/db/schema.py`):
   - Update `CURRENT_VERSION = 16` → `CURRENT_VERSION = 17`.
   - At L547 and L587, update inline comments mentioning Flight 8 v17 → v18.
   - Add the v17 migration block AFTER the existing v16 block (search for `if version < 16:` and add `if version < 17:` after its `version = 16` line):
     ```python
     if version < 17:
         # Mission 10 Flight 4 Leg 5: AgentConfig.connector_account_ids
         # persistence. F4 L1 added the Pydantic field but missed the DB
         # column — leg 4 surfaced the gap when e2e tests had to monkey-
         # patch _row_to_config to re-inject. Adds a nullable TEXT column
         # storing the JSON-encoded list of attached connector_account_id
         # values; NULL is decoded as [] (back-compat for pre-v17 rows).
         #
         # Downstream: flight 08 (Discord) previously planned a v17 CHECK
         # migration; that renumbers to **v18**. See _connector_types.py
         # docstring + tests/test_db_migration.py TestSchemaV14/V15/V16
         # downstream-renumber docstrings + agents.md connector-type
         # checklist item 4.
         #
         # Idempotency follows the v8/v9/v10/v11/v14/v15 ALTER ADD COLUMN
         # pattern (PRAGMA guard + INSERT OR IGNORE on schema_version LAST).
         async with conn.execute("PRAGMA table_info(agents)") as cursor:
             existing_cols = {row[1] for row in await cursor.fetchall()}
         if "connector_account_ids" not in existing_cols:
             await conn.execute(
                 "ALTER TABLE agents ADD COLUMN connector_account_ids TEXT"
             )

         await conn.execute(
             "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (17,)
         )
         await conn.commit()
         version = 17
     ```

2. **Sub-leg A.2 — Repository round-trip** (in `the_one/db/repositories.py`):
   - In `SQLiteAgentStore.save` (~L94-135):
     - Extend the INSERT column list with `, connector_account_ids` (after `mcp_overrides`, before `created_at`).
     - Extend the VALUES placeholder count to 15 (was 14).
     - Extend the parameter tuple (~L118-133) with `json.dumps(config.connector_account_ids)` (mirror the `json.dumps(config.mcp_source_ids)` line at L128).
     - Extend the `ON CONFLICT DO UPDATE SET` block (~L104-116) with `connector_account_ids=excluded.connector_account_ids,` (after `mcp_overrides=excluded.mcp_overrides,`).
   - In `SQLiteAgentStore._row_to_config` (~L188-207):
     - Add `connector_account_ids=json.loads(row["connector_account_ids"] or "[]"),` to the `AgentConfig(...)` call (after `mcp_source_ids=...` at L200).
     - The `row["connector_account_ids"] or "[]"` defends against both NULL (pre-v17 rows) and empty-string (the column-default case).

3. **Sub-leg A.3 — Renumber the v18 sites**:
   - `the_one/db/_connector_types.py`: docstring L12 (`v17 table-rename ceremony` → `v18`) and L16 (`v17 is Flight 8's CHECK constraint` → `v18`). Add an L16-adjacent line documenting `v17 → AgentConfig.connector_account_ids (F4 L5)`.
   - `the_one/agents.md:290`: connector-type checklist item 4 — update the existing v17 reference to v18, add a v17 line for F4 L5.
   - `tests/test_db_migration.py:233`: `assert CURRENT_VERSION == 16` → `assert CURRENT_VERSION == 17`; error message string updated to cite F4 L5.
   - `tests/test_db_migration.py:1170, 1178`: TestSchemaV13 docstring v17 → v18 (reviewer-surfaced; missed in initial design).
   - `tests/test_db_migration.py:1261, 1424, 1592`: TestSchemaV14/V15/V16 docstrings updated `renumbers to v17` → `renumbers to v18`.
   - **Final sweep**: `grep -n 'v17\|v18' the_one/ tests/` to confirm coherent renumber and catch any drift.

4. **Sub-leg A.4 — Add TestSchemaV17 + repository tests**:
   - Mirror `TestSchemaV16` (at L1579) for the column-existence + idempotency tests.
   - Test fresh-DB at v17 has the column (PRAGMA table_info check).
   - Test legacy-v16-row decodes — build a v16-state DB by hand (insert a v16 schema_version row + pre-existing agent rows) then run `ensure_schema`; assert the column is added and the existing rows decode with `connector_account_ids == []`.
   - Test idempotent re-apply (run v17 against a v17 DB; assert no-op).
   - Add `test_save_round_trips_connector_account_ids` + `test_load_pre_v17_agent_has_empty_connector_account_ids` to `tests/test_db_repositories.py` (use the existing test setup in that file).

5. **Sub-leg B — E2E tests** (`tests/test_connectors_e2e_platform_send.py`):
   - Use the helpers from `tests/_connector_dispatch_helpers.py` (created in sub-leg C — implement sub-leg C BEFORE sub-leg B to avoid forward-import).
   - Each test follows the F3 e2e pattern: fixture setup → scripted-provider config → dispatch → assertion.
   - The plugin-resolve-failure test uses `monkeypatch.setattr` to replace `the_one.connectors._inbound.registry.resolve` with a function that raises `ConnectorRegistrationError`. Use `caplog` to capture log entries.
   - For the re-enable test: use `ToolConfigRepository.upsert(name="send_to_platform_channel", config={}, enabled=False)` then `enabled=True` to flip the operator switch mid-test. **Note** (reviewer-surfaced footgun): `upsert`'s `ON CONFLICT` writes `config=excluded.config`, so passing `config={}` on the re-enable call overwrites any pre-existing config dict to empty. For `send_to_platform_channel` there is no operator-tunable config (Config = `_EmptyConfig`), so `config={}` is safe — but document this inline in the test so a future flight that adds a real config payload doesn't accidentally wipe it.
   - **Plugin-resolve test patch target** (reviewer-surfaced subtlety): `monkeypatch.setattr(the_one.connectors._inbound, "registry", mock_registry_with_failing_resolve)` patches the dispatcher's module-local `registry` binding (acquired via `_inbound.py:34 — "from the_one.connectors import ... registry"`). The pool's `_resolve_plugin` at `_pool.py:62 — "from the_one.connectors.registry import resolve as _resolve_plugin"` captured the original `resolve` function reference at import time — that binding is unaffected by the patch. Net effect: pool acquire succeeds (real plugin resolved); the dispatcher's `registry.resolve(account.type)` at `_inbound.py:144` hits the patched version and raises. This is the intended isolation that proves the "deliberately redundant" catch is reachable. Use `monkeypatch.setattr` on the MODULE (`the_one.connectors._inbound.registry`), NOT on the registry module's `resolve` function directly — patching the function attribute would affect every call site at call time.
   - The pool-touch test reads `_pool._pool[("agent-inbound", "acct-test")].last_activity` before/after dispatch.

6. **Sub-leg C — Helper extraction** (`tests/_connector_dispatch_helpers.py`):
   - Create the new module with the seven helpers + autouse fixtures.
   - Imports: `from the_one.connectors._stub import StubPlugin`, `from the_one.connectors._pool import _clear_for_test`, etc.
   - In `tests/test_connectors_inbound.py`: delete the in-file definitions of the seven helpers; add `from tests._connector_dispatch_helpers import (...)`.
   - In `tests/test_connectors_e2e_session.py`: same.
   - In `tests/test_connectors_e2e_platform_send.py`: import only.
   - **Pytest fixture-discovery**: pytest does NOT auto-discover fixtures from arbitrary modules (only `conftest.py`). For the `isolated_db` fixture specifically, the cleanest path is: define `isolated_db` in `tests/conftest.py` AND export the helper FUNCTIONS from `_connector_dispatch_helpers.py`. Alternatively, leave the `isolated_db` fixture in each consumer file as a thin wrapper that delegates to the helper module's implementation. The leg-5 implementer chooses based on what works on first test run.
   - After extraction, REMOVE the leg-4 monkeypatch on `SQLiteAgentStore._row_to_config` from `_make_scripted_factory` — the column round-trip is real now.

7. **Sub-leg D — AsyncMock-warning closure**:
   - First: `docker exec the-one pytest tests/test_provider_api.py::TestModelDiscovery::test_ollama_models -W "error::RuntimeWarning:unittest.mock" -x --timeout 30`. The scoped filter (`:unittest.mock`) avoids false positives from unrelated RuntimeWarnings (asyncio task destruction, etc.) that might fire during teardown — only AsyncMock-never-awaited warnings will error.
   - If exit code = 0: warning is gone. Retire by updating the test docstring with a comment retraction noting the F5 L01.5 short-circuit closed the warning. Add a [methodology] note in the flight log.
   - If exit code ≠ 0: warning still fires. Read the test to identify the AsyncMock that's not awaited. Apply the smaller of two fixes: (a) add the missing `await mock(...)` call somewhere in the test body, OR (b) replace `AsyncMock` with `MagicMock` if no await is logically expected. Re-run with `-W error::RuntimeWarning` to confirm.

8. **Run targeted then full tests** (in order):
   - `docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py -x --timeout 30` — verify sub-leg A.
   - `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py -x --timeout 30` — verify sub-leg C didn't regress F3 L4/L6.
   - `docker exec the-one pytest tests/test_connectors_e2e_platform_send.py -x --timeout 30` — verify sub-leg B.
   - `docker exec the-one pytest tests/test_provider_api.py::TestModelDiscovery::test_ollama_models -W error::RuntimeWarning -x --timeout 30` — verify sub-leg D.
   - `docker exec the-one pytest -x --timeout 30` — full suite green.
   - `docker exec the-one ruff check the_one tests` — clean.

9. **Update flight log** with a "Leg Progress: e2e-tests-and-coverage-carry-forward" entry. Capture: files modified across the four sub-legs, test count delta from leg-4 baseline (1934), any deviations, any anomalies.

10. **Flip leg status to `landed`**. Do NOT commit.

## Edge Cases

- **Pre-v17 agent rows with `connector_account_ids` column NULL**: the `or "[]"` default in `_row_to_config` handles NULL cleanly. Test `test_load_pre_v17_agent_has_empty_connector_account_ids` pins this.

- **Pre-v17 agent rows persisted via the leg-4 monkeypatch**: those rows exist only in test DBs (leg 4 never persisted to production). The monkeypatch removal in sub-leg C cleans up; production DBs are unaffected.

- **A new connector account ID with embedded JSON-unsafe characters** (e.g. `"acct'-1"`): `json.dumps` handles escaping; `json.loads` reverses it. No SQL injection risk because the column is parameterized in the INSERT.

- **The brittle `TestSchemaV8::CURRENT_VERSION == 16` assertion**: bumping to 17 in sub-leg A.3 is part of the leg. Without the bump, the test fails on the next run after the migration lands.

- **`SQLiteAgentStore.save` upsert idempotency**: the `ON CONFLICT(name) DO UPDATE SET` block must include the new column; otherwise repeated saves would NOT update `connector_account_ids` on existing rows. Mirror the `mcp_source_ids=excluded.mcp_source_ids` line at L113.

- **Pytest fixture-discovery for the new helpers module**: pytest only auto-discovers fixtures in `conftest.py`. The leg-5 implementer either splits (fixtures in `conftest.py`, helper functions in `_connector_dispatch_helpers.py`) or imports the `isolated_db` fixture explicitly in each consumer file. Document the chosen approach in the leg log.

- **The plugin-resolve-failure test's `caplog` setup**: pytest's `caplog` fixture captures log records by default at WARNING level. The dispatcher logs at WARNING for unknown-type (`_inbound.py:148-156`). Check that `caplog.set_level(logging.WARNING, logger="the_one.connectors._inbound")` (or similar) is in place if the test doesn't see the record.

- **The re-enable test's `factory.create()` mid-test**: each dispatch call invokes `factory.create()` fresh (per F3 L4 dispatcher design). The second `factory.create()` sees the updated `ToolConfig.enabled=True` and re-applies the carve-out. No agent-cache to invalidate.

- **`_ScriptedProvider.__init__` extra kwargs**: leg 4 documented these (`model`, `base_url`, `api_key`, `config`). Leg 5 inherits the shape via the helper extraction. No new compatibility concerns.

- **The AsyncMock-warning check might pass on the first run by happenstance** (e.g. the warning depends on async-task scheduling). Run 3x to confirm. If flaky, treat as still-firing and apply the fix.

## Files Affected

- `the_one/db/schema.py` — v17 migration block; `CURRENT_VERSION = 17`; renumber comments at L547, L587
- `the_one/db/repositories.py` — `SQLiteAgentStore.save` extension; `_row_to_config` extension
- `the_one/db/_connector_types.py` — docstring v17→v18; add F4 L5's v17 line
- `the_one/agents.md` — connector-type checklist item 4 updated
- `tests/test_db_migration.py` — `CURRENT_VERSION == 16` → `== 17`; `TestSchemaV14/V15/V16` docstring renumber; new `TestSchemaV17` class
- `tests/test_db_repositories.py` — new persistence round-trip tests
- `tests/_connector_dispatch_helpers.py` (new) — extracted helpers
- `tests/test_connectors_inbound.py` — helpers removed; imported from new module; leg-4 monkeypatch removed
- `tests/test_connectors_e2e_session.py` — helpers removed; imported from new module
- `tests/test_connectors_e2e_platform_send.py` (new) — 6 e2e tests
- `tests/test_provider_api.py` — AsyncMock-warning closure (fix or retire)
- `missions/.../flight-log.md` — leg-progress entry
- `missions/.../legs/05-e2e-tests-and-coverage-carry-forward.md` — flip status to `landed`

---

## Post-Completion Checklist

**Per agentic-workflow batched-review model: do NOT commit; defer to flight-end.**

- [ ] All acceptance criteria verified across sub-legs A, B, C, D
- [ ] Full test suite passes
- [ ] Lint clean
- [ ] Update `flight-log.md` with a "Leg Progress: e2e-tests-and-coverage-carry-forward" entry
- [ ] Set this leg's `**Status**` to `landed`
- [ ] Signal `[HANDOFF:review-needed]` — do NOT commit

---

## Citation Audit

22 code-location citations verified against current code at leg design time. All OK:

| Citation | Status | Evidence |
|---|---|---|
| `the_one/db/schema.py:11 — "CURRENT_VERSION = 16"` | OK | Verified at L11 |
| `the_one/db/schema.py:547, 587 (Flight 8 v17 comments)` | OK | Verified earlier |
| `the_one/db/schema.py:563 — "if version < 16:"` (v16 block) | OK | Verified at L563 |
| `the_one/db/repositories.py:88-94 (SQLiteAgentStore.load)` | OK | Verified earlier |
| `the_one/db/repositories.py:94-135 (SQLiteAgentStore.save)` | OK | Verified earlier |
| `the_one/db/repositories.py:104-116 (ON CONFLICT update list)` | OK | Verified earlier |
| `the_one/db/repositories.py:113 (mcp_source_ids in update list)` | OK | Verified — `mcp_source_ids=excluded.mcp_source_ids` at L113 |
| `the_one/db/repositories.py:128 (mcp_source_ids json.dumps)` | OK | Verified earlier |
| `the_one/db/repositories.py:188-207 (_row_to_config)` | OK | Verified earlier |
| `the_one/db/repositories.py:200 (mcp_source_ids read)` | OK | Verified — `mcp_source_ids=json.loads(row["mcp_source_ids"] or "[]")` |
| `the_one/db/_connector_types.py:12, 16 (v17 docstring refs)` | OK | Verified earlier |
| `the_one/agents.md:290 (checklist item 4)` | OK | Verified earlier |
| `tests/test_db_migration.py:233 — "assert CURRENT_VERSION == 16"` | OK | Verified earlier |
| `tests/test_db_migration.py:1261, 1424, 1592 (renumber docstrings)` | OK | Verified earlier |
| `tests/test_db_migration.py:1579 (TestSchemaV16 class)` | OK | Verified earlier |
| `tests/test_db_migration.py:1596 (test_v16_fresh_db_includes_chat_session_external_key_columns)` | OK | Verified at L1596 |
| `the_one/connectors/_inbound.py:147-156 (dispatcher's redundant plugin-resolve catch)` | OK | Verified earlier (F1 debrief citation, still extant post-leg-4) |
| `the_one/connectors/_pool.py:407 (acquire signature)` | OK | Verified earlier |
| `tests/test_connectors_inbound.py (in-file helpers: _seed_provider_and_agent, _seed_stub_account, _make_factory, _envelope, _ScriptedProvider, _make_scripted_factory)` | OK | Verified across leg 1-4 audits |
| `tests/test_connectors_inbound.py::test_dispatch_inbound_touches_pool_last_activity` (existing F3 test that this leg's pool-touch test parallels for outbound) | OK | Verified at L425 (F3 leg 4) |
| `tests/test_provider_api.py:1275-1311 (test_ollama_models)` | OK | Verified at leg-4 audit |
| `tests/test_provider_api.py:1294-1298 (F5 L01.5 get_model_capabilities short-circuit)` | OK | Verified at leg-4 audit (the architect-surfaced site) |
