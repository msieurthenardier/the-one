# Squawk 0025: Evict-before-drain order in the lifespan shutdown branch is not pinned against the real code

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-29
**Completed**: —

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
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
