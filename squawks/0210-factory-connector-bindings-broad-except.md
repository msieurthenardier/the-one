# Squawk 0210: The factory's connector-bindings fail-open catches every exception

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: —

## Report
`AgentFactory.create` seeds the connector tools only for connector-mapped agents (Mission 30 DD7). If reading the bindings raises **any** exception, it seeds the pair as before (fail-open). The catch-all was added so `AsyncMock`-based factory tests keep passing, which lets test convenience shape production behaviour and could hide real bugs behind a warning log.

## Evidence
- `the_one/agent/factory.py`: `connector_bound = config.name in await agent_names_in_use(conn)` wrapped in `except Exception:  # noqa: BLE001 - fail open …`.

## Corrective Action
*(written at completion)* Narrow the `except` to database and parse errors (`sqlite3.Error`, `ValueError`, `TypeError`) and fix the factory test fixtures so they provide a real or stubbed connection.

## Verification

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
