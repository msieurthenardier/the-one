# Squawk 0388: Falsify the reserved-name tests from Mission 36 Flight 1 Leg 2

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: 2026-11-19

## Report
Leg 2 (`retire-default-agent`) added tests for the reserved agent names `default` and `GleepGlorp`. The flight log lists several of them as never falsified, so none has been shown to fail without the code it pins. The names guard a security-adjacent boundary: a stored agent must never take GleepGlorp's identity.

The unfalsified tests:
- the startup rename;
- the connector binding 422s;
- the inbound drop;
- `start_session`'s refusal;
- the routines guards;
- schema v53's idempotency and fresh-database cases.

Falsify each test: break its guard, see the test fail, revert, and record the result. Fix any test that passes vacuously.

## Evidence
- `missions/36-gleepglorp-assistant/flights/01-gleepglorp-exists-and-answers/flight-log.md`: Leg 2 entry, "not falsified" list.
- Code under test: `the_one/naming.py:check_agent_name`, `the_one/db/name_repair.py`, and the v53 step in `the_one/db/schema.py`.
- Debrief, "Technical": "Security-adjacent tests were not falsified".

## Corrective Action
Falsification found three vacuous tests; all fixed (tests only, no product change):
- `tests/test_routines_api.py::test_reserved_names_in_any_case_are_refused`: passed with the `_routines_agent_or_404` guard removed, because the agent lookup 404s for a missing row anyway. It now inserts stored `Default`/`GleepGlorp`/`gleepglorp` rows first, so the guard itself is what refuses.
- `tests/test_routines_self_config_api.py`: the `_routines_switch_agent` guard (GET/PUT switches, proposals list) had no test. Added `test_reserved_names_have_no_routines_switches_even_with_a_stored_row`.
- `tests/test_db_migration.py::TestSchemaV53::test_replay_is_a_no_op_and_keeps_the_counter`: a second `ensure_schema` skips the v53 step entirely (version row present), so idempotency was never exercised. It now deletes the v53 `schema_version` row so the step body reruns over migrated data.

## Verification
Each guard was broken by Edit, the test run, then reverted by Edit. `git diff --stat -- the_one` at the end shows no change to product code (only `the_one/agents.md`, from another squawk).

| Test | Guard broken | Failed? | Fix |
|---|---|---|---|
| `test_name_repair::test_reserved_agent_names_are_renamed_once_and_carry_references` | `is_reserved_agent_name` dropped from the repair condition in `name_repair._repair_agents` | yes | none |
| `test_connector_routes::test_create_refuses_reserved_agent_bindings` | `default_agent` branch of `_reject_reserved_binding` disabled | yes | none |
| same | `channel_map` branch disabled | yes | none |
| same | `_reject_reserved_binding` call removed from create | yes | none |
| `test_connector_routes::test_update_revalidates_every_binding` | call removed from update | yes | none |
| `test_connectors_inbound::test_inbound_bound_to_a_reserved_agent_is_dropped_with_no_chat_row` (3 params) | reserved check in `dispatch_inbound` disabled | yes (3) | none |
| `test_ws_start_session::test_start_session_rejects_and_creates_nothing` (4 reserved params) | reserved check in the `start_session` handler disabled | yes (4) | none |
| `test_routines_api::test_reserved_names_in_any_case_are_refused` | `_routines_agent_or_404` guard disabled | NO (vacuous) | seeded stored rows; re-falsified: yes |
| `test_routines_api::test_default_agent_refused_even_with_stored_row` / same | create-routine guard disabled | yes (2) | none |
| new `test_routines_self_config_api::test_reserved_names_have_no_routines_switches_even_with_a_stored_row` | `_routines_switch_agent` guard disabled | no test existed (existing 148 passed) | added test; falsified: yes |
| `test_routines_service::test_call_time_switch` | `require_routine_tools_on` reserved check disabled | yes | none |
| `test_routine_tools::test_provider_returns_four_tools_only_when_on_and_not_default` | reserved check in `RoutineToolProvider` removed | yes | none |
| `TestSchemaV53::test_replay_is_a_no_op_and_keeps_the_counter` | counter seed `INSERT OR IGNORE` changed to `OR REPLACE` | NO (vacuous: step skipped on replay) | rewind `schema_version` row; re-falsified: yes |
| `TestSchemaV53::test_fresh_database_runs_v53` | counter seed value changed 1 to 9 | yes | none |

Final run (`-x -q`) of `test_name_repair`, `test_connector_routes`, `test_connectors_inbound`, `test_ws_start_session`, `test_routines_api`, `test_routines_self_config_api`, `test_routines_service`, `test_routine_tools`, `test_db_migration`: 516 passed. `ruff check` and `ruff format --check` clean on the three touched test files.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0386-0390
**Verdict**: confirmed (fixed tests now hit the reserved-name guard itself; no product change)
**Commit**: `squawk: turnaround 2026-11-19` on flight/01-gleepglorp-exists-and-answers (PR #380)
