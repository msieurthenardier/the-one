# Leg: verify-integration

**Status**: completed
**Flight**: [Uniform Policy, CLI Parity & Seam Hardening](../flight.md)

## Objective

Run the full verification matrix over the accumulated (uncommitted) changes from legs
01–03 — default suite host-native + in-container, ruff, the `-m requires_bwrap` arm,
the live `/behavior-test tool-sandbox-containment`, the CLI-parity test, and a
passthrough no-error confirmation — and record the consolidated result before the
flight's batch review + commit.

## Context

- This is a **verification leg** — no source changes. It validates the cumulative diff
  before Phase 2d (single code review + commit).
- Designed lightweight; **no design-review agent** (the work is running commands, not
  implementing code — review adds no value here). Recorded in the Flight Director Notes.
- The hermetic arms (suite/ruff/bwrap/passthrough) are deterministic and free. The
  **live behavior test** needs apparatus (running instance + an agent with
  `shell`/`python_exec`/`shell_session_*` tools on a capable model + `~/.ssh` denylist
  fixture) and bills a real LLM provider — gated on operator confirmation (flight
  prerequisite "behavior-test apparatus — re-confirmed before run" was still open).

## Acceptance Criteria

- [x] **Default suite** green in-container (`-m "not requires_bwrap"`): **3015 passed**,
      5 failed / 486 errored — all confirmed PRE-EXISTING (486 errors = Playwright/Chromium
      not installed in the image; 4 failures = live-LLM AIAT tests; 1 = Playwright smoke).
      **0 flight-introduced regressions** (classified via the hermetic verification pass).
      Host-native run not performed (no host venv); the container run is authoritative —
      honest caveat: no pytest CI yet (flight Verification note).
- [x] **`-m requires_bwrap`** arm green in-container: **14 passed / 0 failed** (built-in +
      PTY + MCP + CLI-parity + the new app-crash regression test).
- [x] **`ruff check`** + **`ruff format --check`** clean across `the_one/` + `tests/`
      (one cosmetic `tests/test_pty_sandbox.py` format nit was fixed before commit).
- [x] **CLI-parity** test (`tests/test_cli_sandbox_parity.py`) green — bwrap assertion (a)
      + non-bwrap assertion (b) both pass.
- [x] **Passthrough no-error**: `test_sandbox_factory.py` + `test_sandbox_contract.py`
      **27 passed** — factory selects passthrough cleanly, no construction error.
- [x] **Live `/behavior-test tool-sandbox-containment`** run (operator-approved): **6/6
      checkpoints PASS** (Witnessed, re-spawn mode). Run log at
      `tests/behavior/tool-sandbox-containment/runs/2026-06-07-15-29-51.md`. Spec promoted
      `draft` → `active`. The `uat-and-alignment` HAT was **skipped** (operator: no UI
      changed this flight — confirmed; automated tests + live behavior test suffice).
- [x] Consolidated result recorded in the flight log.

## Verification Steps

- In-container default suite: `docker exec the-one python -m pytest --timeout 60 -m "not requires_bwrap" -q`
- bwrap arm: `docker exec the-one python -m pytest -m requires_bwrap --timeout 120 -q`
- ruff: `docker exec the-one ruff check the_one/ tests/ && docker exec the-one ruff format --check the_one/ tests/`
- CLI parity: `docker exec the-one python -m pytest tests/test_cli_sandbox_parity.py --timeout 60 -m requires_bwrap`
- Passthrough: `docker exec the-one python -m pytest tests/test_sandbox_factory.py tests/test_sandbox_contract.py --timeout 60 -q`
- Live behavior test: `/behavior-test tool-sandbox-containment` (after apparatus confirmed).
- Host-native suite: run on host if a host venv is available; otherwise note the
  container run is the authoritative one (honest caveat — the flight notes there is no
  pytest CI yet).

## Files Affected

- None (verification only). Produces a behavior-test run log under
  `tests/behavior/tool-sandbox-containment/runs/` if the live test runs.

---

## Post-Completion Checklist

> Verification leg in a batched-commit flight. After this leg's matrix passes, proceed to
> Phase 2d (Reviewer over all uncommitted changes → commit).

- [ ] Hermetic matrix green (suite/ruff/bwrap/CLI-parity/passthrough)
- [ ] Live behavior test run + logged, OR deferral recorded with rationale
- [ ] Update flight-log.md with the consolidated verification result
- [ ] Set this leg's status to `landed`
