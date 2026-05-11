# F10 Regression Sweep

**Date**: 2026-05-10
**Flight**: F10 (Lazy tool discovery — search-tools / search-mcps as the only catalog entries)
**Baseline**: F8 (1376 unit / 255 browser / 43 pre-existing browser flakes)
**L4 post-landing baseline**: 1505 unit (1376 F8 + 74 F9 L1-L3 net new + 55 F10 L1-L4 net new = 1505 total)

---

## Unit suite

**Command**: `docker exec the-one pytest -q --timeout 120 --ignore=tests/test_mcp_pool.py`

**Result**: 1505 pass / 2 fail / 2 skip / 344 deselect

**Delta vs L4 post-landing baseline (1505)**: ±0 — L5 adds documentation artifacts only; no production or test code changes.

**Delta vs F8 baseline (1376)**: +129 net new tests across F9 L1-L3 (74) + F10 L1-L4 (55).

**Net-new failures since F8 baseline**: None

**Pre-existing flakes confirmed unchanged**:
- `tests/test_mcp_sandbox_integration.py::test_sandbox_writable_paths_nonexistent_raises_at_connect` — bwrap unavailable in test container; pre-existing on main before F9/F10.
- `tests/test_mcp_sandbox_integration.py::test_sandbox_bwrap_unrecognised_exit_code_raises_msc_sandbox_error_msg2` — bwrap unavailable in test container; pre-existing on main before F9/F10.

Count: 2 — matches F8/F9/F10 L1-L4 baseline; no change.

---

## Browser suite

**Command**: `docker exec the-one pytest tests/browser/ -q --timeout 120 -m browser`

**Result**: 283 pass / 43 fail / 12 deselect

**Delta vs F8 baseline (255 pass / 43 fail)**:
- Pass count: +28 (F9 L1-L3 added new browser tests that pass; not F10 additions — F10 deferred Studio UI browser coverage to a follow-up flight per Design Decision §8)
- Fail count: ±0 — still exactly 43 pre-existing flakes; no net-new failures

**Net-new failures**: None

**Pre-existing flake summary (43 failures)**:

Failures are concentrated in tests that rely on application state that is not available in the test container environment. Representative failing modules from the run:
- `tests/browser/test_flow_dirty_confirm.py` — 13 failures (confirm-dialog UX tests; pre-existing flake set)
- `tests/browser/test_flow_hash_routing.py` — 2 failures
- `tests/browser/test_flow_new_chat.py` — 1 failure
- `tests/browser/test_flow_provider_grid.py` — 2 failures
- `tests/browser/test_flow_provider_setup.py` — 1 failure
- Additional pre-existing failures across other test modules — 24 failures

All 43 match the F8 + F9 known-flake set. None are F10-introduced.

---

## Caplog gate

**Command**: `docker compose logs --tail 500 the-one 2>&1 | grep -c "MCPClient.disconnect"`

**Result**: 0

**Target**: 0

Gate passes. The F6.6 `_open_*_transport_stack` fix + F6 worker-task-per-entry pattern hold across the full F10 working tree.

---

## Summary

| Metric | F8 baseline | Post-F10 L5 | Delta |
|--------|-------------|-------------|-------|
| Unit pass | 1376 | 1505 | +129 |
| Unit fail (pre-existing flakes) | 2 | 2 | 0 |
| Browser pass | 255 | 283 | +28 |
| Browser fail (pre-existing flakes) | 43 | 43 | 0 |
| Caplog MCPClient.disconnect | 0 | 0 | 0 |

**Verdict**: No net-new failures. F10 is regression-clean against the F8 baseline. Phase 2d Reviewer can proceed.
