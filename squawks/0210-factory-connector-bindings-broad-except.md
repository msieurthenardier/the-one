# Squawk 0210: The factory's connector-bindings fail-open catches every exception

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: 2026-10-14

## Report
`AgentFactory.create` seeds the connector tools only for connector-mapped agents (Mission 30 DD7). If reading the bindings raises **any** exception, it seeds the pair as before (fail-open). The catch-all was added so `AsyncMock`-based factory tests keep passing, which lets test convenience shape production behaviour and could hide real bugs behind a warning log.

## Evidence
- `the_one/agent/factory.py`: `connector_bound = config.name in await agent_names_in_use(conn)` wrapped in `except Exception:  # noqa: BLE001 - fail open …`.

## Corrective Action
Narrowed the `except` in `AgentFactory.create` to `(sqlite3.Error, ValueError)` (still fail-open: warning logged, pair seeded). TypeError is deliberately NOT caught, so a real bug cannot hide behind the fail-open. test_factory.py's bare `AsyncMock` connections raise TypeError at the bindings query, so an autouse fixture there patches `the_one.db.repositories.agent_names_in_use` to treat every agent as bound (the previous fail-open behaviour); no assertion weakened. tests/test_prompt_layers.py: fail-open test raises `sqlite3.OperationalError`; RuntimeError and TypeError propagation tests added.

## Verification
Full unit tier: 6616 passed, 12 skipped. ruff check and format --check clean. Fixture `all_agents_connector_bound` (tests/conftest.py) is applied to test_factory.py (module), TestAgentFactoryMCPIntegration and two test_search_tools.py tests.

## Sign-Off
*(written at completion)*
**Reviewer**: Reviewer agent (Sonnet tier), batch review of squawks 0208–0212
**Verdict**: confirmed
**Commit**: 66798d3
