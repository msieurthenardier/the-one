# Squawk 0439: five self-configuration surface tests fail in the unit tier under load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-27
**Completed**: —

## Report

During squawk 0438's verification, `THE_ONE_TEST_NETNS=1 make test-unit` at load 20 to 23 failed six tests:
- the known 0431 `test_mcp_pool` flake;
- five tests in `tests/test_self_configuration_surface.py`.

Re-run alone at load 23, both files passed (45 passed). The five were not failing in the 0434 and 0428 unit runs at load 7 to 19. The failure messages were not kept, so the first step is to capture them.

## Evidence
- `squawks/0438-browser-app-spawn-ready-timeout-under-load.md`, Verification (the unit-run line).
- `tests/test_self_configuration_surface.py::_wait_ready` polls `/api/live` with a fixed `timeout: float = 10.0` for an in-process uvicorn task on the test's own event loop. That is a suspect, not a confirmed cause.

## Corrective Action
*(written at completion)* First, capture the failure messages from a loaded unit run. The per-test timeout from 0435 gives stacks. Do not generate load to reproduce. If the cause is the 10 s ready wait, align it with the 0438 knob (`THE_ONE_TEST_APP_READY_TIMEOUT`) or raise it. Otherwise, fix the actual race.

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
