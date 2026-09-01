# Squawk 0025: Evict-before-drain order in the lifespan shutdown branch is not pinned against the real code

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-29
**Completed**: 2026-09-01

## Report

The self-configuration shutdown-drain mitigation depends on the lifespan evicting every marked
surface row's pool entries *before* `_mcp_pool_shutdown_drain()`. Squawk 0005's under-load test
proves the sequence terminates cleanly with a live connection, but its `order == ["evict",
"drain"]` assertion is driven by the test's own helper calling the two functions in a literal
order — it never executes `app.py`'s shutdown branch. The pre-existing
`tests/test_mcp_pool.py::test_lifespan_shutdown_drain_order` treats the MCP drain as one atomic
step and never spies inside it either. Reordering the two `try` blocks in `app.py` would go
undetected. Add a test that drives the real `lifespan(app)` (the `tests/test_lifespan.py`
idiom) with spies on `_evict_all_for_source` and `shutdown_drain` and asserts the recorded
call order.

## Evidence

- `the_one/interfaces/web/app.py:lifespan` shutdown branch (~`:404-417`) — the two `try` blocks whose order is the mitigation
- `tests/test_self_configuration_surface.py::TestSquawk0005ShutdownDrainUnderLoad` — `_shutdown_sequence()` helper hardcodes evict-then-drain
- `tests/test_mcp_pool.py::test_lifespan_shutdown_drain_order` — atomic-drain granularity
- Raised by the independent Reviewer of turnaround 2026-08-29 (non-blocking finding on squawk 0005)

## Corrective Action

Line refs in the report predate Missions 23 F1/F2; re-located the shutdown branch in
`the_one/interfaces/web/app.py:lifespan` — the two `try` blocks now sit at lines 356-371
(evict block, then `_mcp_pool_shutdown_drain()`), unchanged by either mission.

Extended `tests/test_mcp_pool.py::test_lifespan_shutdown_drain_order` (already the test that
drives the real `lifespan(app)` and pins cross-subsystem ordering) rather than adding a
parallel test, since its startup/shutdown mocking scaffold was already in place:

- Monkeypatched `app_mod.MCPSourceRepository` to a fake whose `list()` returns `[]` on its
  first call (the startup self-configuration reconcile, matching the empty-list behavior the
  test already got for free from the unmocked `_fake_conn`-backed repository) and a single
  surface-marked `MCPSource` row on its second call (the shutdown eviction branch).
- The surface marker (`config={"self_configuration": {"agent": "test-agent"}}`) is read by
  the REAL `_self_configuration_manage.is_surface_row` predicate — left unmocked — so the
  shutdown branch's `if is_surface_row(_row):` check genuinely passes and the branch reaches
  `_evict_all_for_source`.
- `_evict_all_for_source` is imported function-locally inside `lifespan` (`from
  the_one.mcp._pool import _evict_all_for_source`), so — mirroring the existing pattern for
  `stop_periodic_sweep` on `oauth_mod` — it's monkeypatched on `pool_mod` (the source module)
  as a spy appending `"evict"` to the shared `calls` list; the local import re-resolves to
  the spy at call time.
- The existing `_mcp_pool_shutdown_drain` spy (`"mcp"`) was left as-is.
- `drain_steps` now asserts `"evict"` immediately precedes `"mcp"` in the full recorded
  sequence: `["connector_start", "pty", "evict", "mcp", "oauth", "connector_drain", "db"]`.

Both spies are invoked from inside `app.py`'s real shutdown branch as it executes — the
recorded order is an observation of the real code path, not a value the test hardcodes —
so reordering the two `try` blocks in `app.py` would flip `"evict"` and `"mcp"` in `calls`
and fail the assertion. `app.py` itself was not modified (confirmed via `git diff --stat`);
the existing order is correct and this change only pins it.

## Verification

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_mcp_pool.py -x --timeout 30`
→ 27 passed, 2 deselected (full file, no regressions).

Before landing on the fake-repository/two-call-count approach, confirmed the naive version
(patching `MCPSourceRepository` globally to always return the surface row) breaks the
startup self-configuration reconcile — `reconcile_on_startup` then takes the rename branch
and calls `agent_store.load(...)` against the test's mocked (non-async-aware) `store`,
raising `TypeError: object MagicMock can't be used in 'await' expression`. This confirmed
the fake needs to keep startup's `list()` call returning `[]`, which the two-call-count
gating does.

Did not modify `the_one/interfaces/web/app.py` to swap-and-revert the two `try` blocks as a
manual falsification check — editing app.py is out of scope for this squawk (order is
already correct) and was blocked by the harness's auto-mode classifier when attempted;
confidence that the test pins the order instead rests on the mechanism itself: `calls` is
populated in real time by spies invoked from inside the real shutdown branch as it executes,
not hardcoded by the test, so the recorded order is whichever `try` block genuinely runs
first.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet), squawk/turnaround-2026-09-01
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-01 batch commit (PR follows)
