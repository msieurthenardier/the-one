# Squawk 0431: `test_acquire_lazy_spawn_creates_worker_and_returns_client` fails under xdist

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-26
**Completed**: —

## Report
In sortie 20's closing unit tier (`make test-unit`, `-n 4`, load about 5), `tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client` failed once and passed when run alone. That suggests shared state between tests on the same xdist worker (the MCP pool's module-level registry), or a timing dependence. Sortie 20 did not touch the MCP pool. See `sorties/20-deleting-an-agent-deletes-its-chats/flight-debrief.md`, "Test metrics".

## Evidence
- `tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client` (`:119`): failed in the full `-n 4` run on `f7a86df1`, and passed alone.
- The parallel unit tier arrived with Mission 37 Flight 1 (#390), so this is a new way to fail.

## Corrective Action
*(written at completion)*

Suggested direction: reproduce with `-n 4 -p no:randomly` and `--dist load` on `tests/test_mcp_pool.py` plus its neighbours. Look for pool state a prior test leaves behind (a reset helper the test does not use) or a wall-clock wait.

## Verification
`make test-unit` passes it in three consecutive runs, and the file passes alone.

## Sign-Off
*(written at completion)*
**Reviewer**: —
**Verdict**: —
**Commit**: —
