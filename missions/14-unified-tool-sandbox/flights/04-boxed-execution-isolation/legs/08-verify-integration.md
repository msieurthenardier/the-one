# Leg: verify-integration

**Status**: completed
**Flight**: [Agent-Selectable Execution Isolation (Boxed Mode)](../flight.md)

## Objective

Run the full verification matrix over the accumulated (uncommitted) legs 1–7 — default suite
+ ruff + `-m requires_bwrap` (incl. the new box suite), the live
`/behavior-test tool-sandbox-box-isolation`, a re-run of `tool-sandbox-containment`
(no host-mode regression), and the passthrough no-error + WARNING check — before the flight's
batch review + commit.

## Context

- Verification leg — no source changes. Designed lightweight; **no design-review agent**
  (recorded in Flight Director Notes).
- The live behavior test needs the running instance to serve the **new `host_access` tool
  schema** (legs 3–5) — the container must be on the flight's code (reload/restart; repo is
  bind-mounted). The startup-prune (leg 7) runs on that restart. The `sandbox-test` agent
  (Flight-3 apparatus) persists on the volume; the read-scoping canary must be planted under
  the agent's `$HOME` (`/root/.box_test_canary`) before the run.

## Acceptance Criteria

- [ ] **`-m requires_bwrap`** arm green in-container (box isolation suite + builtin + PTY +
      MCP + CLI-parity + Flight-3 regression).
- [ ] **Default suite** green in-container (`-m "not requires_bwrap"`), modulo the known
      pre-existing failures (Playwright/Chromium; live-LLM AIAT) — confirmed pre-existing.
- [ ] **`ruff check`** + **`ruff format --check`** clean across `the_one/` + `tests/`.
- [ ] **No host-mode regression**: `tool-sandbox-containment` (Flight 3) re-run live still
      passes; host-mode `@requires_bwrap` PTY/builtin tests green.
- [ ] **Passthrough**: with `THE_ONE_SANDBOX_DISABLED=1`, the factory selects passthrough,
      boxed profiles run without error, and the no-enforcement WARNING fires (the seam check
      from leg 1). Confirm via the existing passthrough/contract tests + a targeted check.
- [ ] **Live `/behavior-test tool-sandbox-box-isolation`** (operator-gated): apparatus
      re-confirmed (container reloaded to serve `host_access`; canary planted); run captured a
      log at `tests/behavior/tool-sandbox-box-isolation/runs/{ts}.md`; verdict recorded; spec
      promoted `draft` → `active` on pass. If apparatus unavailable/declined, deferral recorded
      (to the HAT or a follow-up) — NOT silently skipped.
- [ ] Consolidated result recorded in the flight log.

## Verification Steps

- In-container default suite: `docker exec the-one python -m pytest --timeout 60 -m "not requires_bwrap" -q`
- bwrap arm: `docker exec the-one python -m pytest -m requires_bwrap --timeout 120 -q`
- ruff: `docker exec the-one ruff check the_one/ tests/ && docker exec the-one ruff format --check the_one/ tests/`
- Host-mode no-regression: `/behavior-test tool-sandbox-containment` (re-run) + `docker exec the-one python -m pytest tests/test_builtin_tool_sandbox.py tests/test_pty_sandbox.py -m requires_bwrap --timeout 120 -q`
- Passthrough: `docker exec the-one python -m pytest tests/test_sandbox_factory.py tests/test_sandbox_contract.py --timeout 60 -q` + a targeted boxed-passthrough-no-error + WARNING check.
- Reload the instance (`docker restart the-one` or rely on auto-reload) so it serves the new
  `host_access` schema; plant `/root/.box_test_canary`; re-confirm `sandbox-test` agent.
- Live boxed behavior test: `/behavior-test tool-sandbox-box-isolation`.

## Files Affected

- None (verification only). Produces a behavior-test run log under
  `tests/behavior/tool-sandbox-box-isolation/runs/`.

---

## Post-Completion Checklist

> Verification leg in a batched-commit flight. After the matrix passes, proceed to Phase 2d
> (Reviewer over all uncommitted changes → commit).

- [ ] Hermetic matrix green (suite/ruff/bwrap-box/passthrough)
- [ ] Host-mode no-regression confirmed (containment re-run + host bwrap tests)
- [ ] Live boxed behavior test run + logged, OR deferral recorded
- [ ] Update flight-log.md with the consolidated verification result
- [ ] Set this leg's status to `landed`
