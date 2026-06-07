# Leg: verify-integration

**Status**: completed
**Flight**: [PTY Through the Seam](../flight.md)

## Objective

Prove the flight whole: run the full suite + ruff gate, the `-m requires_bwrap` PTY
containment run, and a passthrough no-error check; then update the security/architecture
docs to reflect that PTY is now sandboxed (the fourth spawn path), the single-path
seam, the `--die-with-parent` teardown, and the deliberate absence of `--new-session`
(+ its `TIOCSTI` tradeoff). The live `/behavior-test pty-session-containment` run is the
**Flight Director's** responsibility (the run skill orchestrates its own crew) and is
NOT performed by the implementing agent — see "Behavior test" below.

## Context

- **Design decisions** (from `flight.md`): DD6 (verify both ways), and the docs the
  Flight-1 debrief asked Flight 2 to land (the `platform/sandbox/` agents.md subsection;
  PTY-now-sandboxed corrections).
- **Depends on Legs 1-3 (landed):** the seam routing (L1), tool wiring (L2), and the
  `@requires_bwrap` containment suite incl. orphan-survival (L1 + L3).
- This is the final autonomous leg. Per the batched workflow, review + commit happen
  after this leg (Phase 2d, Flight-Director-driven) — this leg still does **not** commit.

## Inputs

What exists before this leg runs:
- All Legs 1-3 changes (uncommitted on `flight/02-pty-through-seam`).
- `SECURITY-MODEL.md` — "Tool Execution Boundary" section; the env-allowlist bullet
  (~lines 71-73) currently claims "`pty.py::UnixPtySession` calls it directly (PTY
  sessions are not yet wired through the seam)" — **now false**; the "OS-level execution
  fence (M14 F1)" bullet (~lines 74-87) lists only `shell` + `python_exec`.
- `the_one/agents.md` — conventions/architecture doc; has **no** `platform/sandbox/`
  subsection yet (Flight-1 debrief action item).
- `CLAUDE.md` — referenced by SECURITY-MODEL.md for the tool-config layer; check for any
  now-false "PTY unsandboxed" claim.
- `tests/behavior/pty-session-containment.md` — the behavior-test spec (status `draft`).

## Outputs

What exists after this leg completes:
- Confirmed-green full suite + ruff; `-m requires_bwrap` PTY run green; passthrough
  no-error confirmed.
- `SECURITY-MODEL.md`, `the_one/agents.md`, and (if needed) `CLAUDE.md` updated to
  reflect PTY-through-the-seam.

## Acceptance Criteria
- [x] **Full suite green** in-container: `docker exec the-one pytest --timeout 60`
      (default deselects `requires_bwrap`/`live`/`browser`/`pixel`/`discord_hat`). Record
      the pass/skip/deselect counts and compare to the Flight-1 debrief baseline
      (3007 passed / 4 skipped / 552 deselected) — note the delta from this flight's new
      tests; no regressions. **Result: 3008 passed, 4 skipped, 557 deselected.**
- [x] **`-m requires_bwrap` green**: `docker exec the-one pytest -m requires_bwrap
      --timeout 90` — the PTY containment suite (`tests/test_pty_sandbox.py`, 5 tests)
      plus the pre-existing built-in/MCP bwrap tests all pass. **Result: 12 passed.**
- [x] **ruff gate clean**: `docker exec the-one ruff check .` and `docker exec the-one
      ruff format --check .` both pass.
- [x] **Passthrough no-error confirmed**: with the double-flag bypass
      (`THE_ONE_SANDBOX_DISABLED=1` + `THE_ONE_TEST_MODE=1`), a PTY session still
      starts / sends / closes (this is what the pinned `test_pty_session.py` already
      exercises — cite it; no new test needed). Confirm no construction-time error off
      the bwrap path. **Confirmed: 16 passed, 1 skipped in `test_pty_session.py` under
      the passthrough pin (the autouse fixture sets both flags).**
- [x] **SECURITY-MODEL.md updated**: the env-allowlist bullet no longer says PTY is
      unwired — state that `UnixPtySession` now routes `_build_subprocess_env()` through
      the seam like `ShellTool`/`PythonExecTool`. The "OS-level execution fence" bullet
      names **all four** spawn paths (shell, python_exec, MCP stdio, **PTY sessions**)
      and notes: PTY teardown reaps the bwrap PID namespace via `--die-with-parent` +
      single-pid SIGKILL; the seam deliberately omits `--new-session` to preserve the
      controlling tty for interactive use, leaving the `TIOCSTI` input-injection surface
      open as a recorded tradeoff.
- [x] **`the_one/agents.md` updated** (four spots — reviewer found three beyond the new
      subsection):
      - add a `### the_one/platform/sandbox/` subsection (Flight-1 debrief action item)
        describing the four-module package (base / factory / bubblewrap / passthrough),
        the `prepare_spawn → SpawnSpec` contract, and that all four spawn paths route
        through `get_sandbox_backend()`;
      - the "Scope (M14 F1)" heading (~`agents.md:605`) → "M14 F1+F2";
      - the scope sentence (~`:607-610`) "Three spawn paths … PTY sessions wired in
        Flight 2" → "Four spawn paths …", dropping the future-tense forward reference;
      - the "Subprocess environment invariant / Call sites" bullet for
        `pty.py::UnixPtySession` — "not yet wired" → now wired (parent-side
        `_build_subprocess_env()` through the seam).
- [x] **CLAUDE.md** updated: fix any now-false "PTY/shell-session unsandboxed" statement,
      AND correct the stale `requires_bwrap` count at ~`CLAUDE.md:131` ("**7 tests**: 5
      built-in containment + 2 MCP pool integration") → "**12 tests**: 5 built-in
      containment + 2 MCP pool integration + **5 PTY containment** (`test_pty_sandbox.py`)".
      No other stale PTY claim found in CLAUDE.md (noted in flight log).
- [x] **`pyproject.toml:75` deselect-math comment** corrected: `requires_bwrap=7 …
      total=552` → `requires_bwrap=12 … total=557`.
- [x] Flight log updated; leg status `landed`. **No commit** (Phase 2d handles it).

## Verification Steps
- `docker exec the-one pytest --timeout 60` — full default suite green; record counts.
- `docker exec the-one pytest -m requires_bwrap --timeout 90` — all bwrap tests green.
- `docker exec the-one ruff check .` + `docker exec the-one ruff format --check .` — clean.
- `grep -n "not yet wired\|not wired through the seam" SECURITY-MODEL.md` — returns
  nothing after the edit (the stale claim is gone).
- `grep -rn "not yet wired\|wired in Flight 2\|Three spawn paths" the_one/agents.md` —
  returns nothing after the edits.
- `grep -n "platform/sandbox" the_one/agents.md` — the new subsection is present.
- `grep -n "requires_bwrap" CLAUDE.md pyproject.toml` — counts read 12 / total 557.

## Implementation Guidance

1. **Run the deterministic gates first** (suite, bwrap, ruff) and capture the numbers
   for the flight log before touching docs — so a doc edit never masks a test failure.
2. **SECURITY-MODEL.md** (`## Tool Execution Boundary`):
   - In the **Subprocess environment** bullet, replace the parenthetical "(PTY sessions
     are not yet wired through the seam)" — now `UnixPtySession` builds
     `_build_subprocess_env()` in the parent and passes it through
     `get_sandbox_backend().prepare_spawn(...)`, identical in spirit to the one-shot
     tools (M14 F2).
   - In the **OS-level execution fence (M14 F1)** bullet, broaden it to **M14 F1+F2**:
     all four spawn paths (`shell`, `python_exec`, MCP stdio, and PTY `shell_session_*`)
     route through the factory seam. Add one sentence on PTY teardown
     (`--die-with-parent` + single-pid SIGKILL → kernel PID-namespace teardown reaps
     `setsid`'d grandchildren) and one on the deliberate `--new-session` omission
     (keeps the controlling tty; the `TIOCSTI` input-injection surface is the accepted
     tradeoff).
   - Keep the doc's existing voice/format; do not restructure sections.
3. **`the_one/agents.md`** (four edits): (a) add `### the_one/platform/sandbox/` under
   the architecture/conventions area — the four modules + roles, the
   `prepare_spawn(profile, command, args, env, cwd) → SpawnSpec` contract, backend
   selection via `get_sandbox_backend()` (bubblewrap on Linux+bwrap, passthrough
   otherwise), and that all four spawn sites now funnel through it; (b) `~:605` heading
   "Scope (M14 F1)" → "M14 F1+F2"; (c) `~:607-610` "Three spawn paths … PTY sessions
   wired in Flight 2" → "Four spawn paths …" (drop the future tense); (d) `~:718-720`
   the `pty.py::UnixPtySession` call-sites bullet "not yet wired" → now wired. Match the
   file's existing style. (Line numbers approximate — grep `not yet wired`,
   `wired in Flight 2`, `Three spawn paths` to locate.)
4. **CLAUDE.md**: grep for PTY/`shell_session`/sandbox claims; correct now-false
   statements AND the stale `requires_bwrap` count at `~:131` (7 → 12, adding the 5 PTY
   containment tests). If nothing else is stale, record "CLAUDE.md: count fixed, no other
   stale PTY claim" in the flight log.
5. **`pyproject.toml:75`**: update the deselect-math comment `requires_bwrap=7 …
   total=552` → `requires_bwrap=12 … total=557`. Comment-only; do NOT touch the
   `addopts` line itself.
6. Re-run `ruff check .` once at the end to be safe (doc/`.toml` edits don't affect ruff,
   but a final clean check is cheap).

## Behavior test (Flight-Director-run, NOT this agent)

Do **not** run `/behavior-test pty-session-containment` from this implementation agent —
the run skill spawns its own Executor + Validator crew and is driven by the Flight
Director. This leg's job is the deterministic gates + docs. The Flight Director will,
after this leg: probe the behavior-test apparatus (running instance + an agent with the
`shell_session_*` tools + a confirmed drive surface — the prerequisite the flight
flags), then either run the live test or, if the apparatus needs operator setup, surface
it to the operator. The `@requires_bwrap` suite (Legs 1+3) already proves PTY containment
hermetically; the live test is the mission's additional behavior-test-backed gate.

## Edge Cases
- **Pre-existing flake** (Flight-1 debrief): `test_connectors_e2e.py::test_e2e_full_lifecycle`
  is non-deterministic. If it fails, re-run once to confirm it's the known flake (not a
  regression from this flight — this flight touches no connector code) and note it in the
  log; do not chase it here.
- **Doc-only edits don't affect tests** — but run the suite BEFORE editing docs so a
  green result is attributable to code, not interleaved with doc churn.
- **No source changes expected** beyond docs — if a doc-driven realization surfaces a
  real code gap, STOP and signal `[BLOCKED:reason]` rather than expanding scope.

## Files Affected
- `SECURITY-MODEL.md` — PTY-through-seam corrections; teardown + `--new-session` note.
- `the_one/agents.md` — new `### the_one/platform/sandbox/` subsection + three stale-line
  fixes (`~605`, `~607-610`, `~718-720`).
- `CLAUDE.md` — stale-PTY-claim fix (if any) + the `requires_bwrap` count (7 → 12).
- `pyproject.toml` — deselect-math comment (`requires_bwrap=12 … total=557`); comment only.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (suite + bwrap + ruff green; docs updated)
- [x] Update flight-log.md with a leg progress entry (append) incl. final test counts
      and the suite-delta vs the Flight-1 baseline
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off the leg in flight.md, do NOT land the flight, **do NOT commit** —
      the Flight Director runs Phase 2d (review + commit) and the behavior test.
      Signal `[HANDOFF:review-needed]`.
