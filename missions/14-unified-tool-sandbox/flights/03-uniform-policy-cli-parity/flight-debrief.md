# Flight Debrief: Uniform Policy, CLI Parity & Seam Hardening

**Date**: 2026-06-07
**Flight**: [Uniform Policy, CLI Parity & Seam Hardening](flight.md)
**Status**: landed
**Duration**: 2026-06-07 (single execution session — planning, 4 legs, verification, commit)
**Legs Completed**: 4 of 4 core (`cli-parity`, `containment-behavior-suite`, `debt-and-docs`, `verify-integration`); optional `uat-and-alignment` HAT skipped by operator (no UI changed)

## Outcome Assessment

### Objectives Achieved

The flight finished and hardened the shared tool-execution sandbox seam now that all four spawn paths route through it. All three planned threads landed:

1. **CLI parity** — `tests/test_cli_sandbox_parity.py` proves a tool built the CLI/factory way (`BuiltinToolProvider.get_tools`) is (a) write-contained under real bwrap and (b) wired with a real, non-empty `FilesystemConfig`. The CLI is demonstrably not an unsandboxed bypass.
2. **Containment consolidation** — the unified `tool-sandbox-containment` behavior test ran live (6/6 PASS) across shell / python_exec / PTY through the agent surface; the `@requires_bwrap` setup is consolidated behind `tests/_sandbox_fixtures.py`.
3. **Seam hardening + debt** — the host-crash PTY-orphan window is locked by a regression test (and proven already-mitigated by bwrap's `--die-with-parent`); the `profile: object` typing debt, the stale bubblewrap/factory messages, the `--ro-bind-try` caveat, and the footgun docs are all cleared.

### Mission Criteria Advanced

- **CLI sandboxed identically to web** — met (behavior-test-backed + `@requires_bwrap`).
- **Uniform policy from one source** — reinforced: a parity test + the unified behavior test now assert it, not just structure (`_build_tool_profile` is the single hook).
- **Existing behavior preserved** — 14/14 `@requires_bwrap`, 3015 default-suite passed, 0 regressions, ruff clean.
- **Mission known-issue retired**: the host-crash PTY-orphan window is recorded as *mitigated* (bwrap's `--die-with-parent`, empirically verified), not open.

All flight checkpoints met.

## What Went Well

- **Design-review caught two vacuous-pass / unsafe traps before implementation.** The leg-01 review found the shared `FilesystemConfig` cross-config is keyed under `read_file` (not `shell`) — keying under `shell` would have passed assertion (b) vacuously on the default `["~"]`. The leg-03 review caught the fork-safety defect in the optional pdeathsig (don't `import`/`dlopen` in the post-fork child). Both are exactly the failures the design-review cycle exists to catch.
- **DD4's empirical reframe paid off.** Proving the orphan window was already covered by bwrap's own `prctl(PR_SET_PDEATHSIG)` shrank a standalone leg into a regression guard + optional belt-and-suspenders — less code, honest framing.
- **The agent-safe-observable rule held throughout the live behavior test.** All 6 checkpoints rested on result state (file present/absent/unchanged, reported interface list, process gone) — none on "perform the exploit and read the error." 6/6 PASS with no inconclusive checkpoints (contrast the F2 network-checkpoint inconclusive).
- **Pre-flight recon prevented wasted work.** Discovering the behavior spec was already committed reframed leg-02 as fixture-consolidation only; the architect's MCP assess-only scoping meant zero wasted effort forcing the `$HOME` shape onto a `/var/tmp` test.
- **Apparatus smoke-test before the formal run** de-risked the live behavior test — end-to-end containment was proven once cheaply before spending the Witnessed run.

## What Could Be Improved

### Process

- **One fork-safety constraint should have been front-loaded at flight-design time, not leg-design time.** The flight spec said "add a pre-`execvp` `prctl` in the fork child" without noting the fork-safety constraint on shared-state init (ctypes/locks/logging) — even though the module's own DD1 already documents exactly that rule for the SpawnSpec. The leg review caught it cleanly, but for future fork-child work the constraint belongs in the flight spec.
- **`debt-and-docs` was at the upper bound of single-leg complexity** (5 sub-items, production code + new test + 5 doc surfaces, one review cycle). It landed clean, but it's a complexity ceiling worth respecting.

### Technical

- **Latent macOS regression introduced this flight (highest-priority follow-up).** The pdeathsig change loads `ctypes.CDLL("libc.so.6", ...)` **unconditionally** in `UnixPtySession.start()`. The module guards Windows at import (`os.name == "nt"`) but **not macOS** (`os.name == "posix"`). On macOS, `start()` would now raise `OSError: dlopen(libc.so.6...)` on every PTY open — where pre-flight it ran (passthrough). Harmless today (the app runs in a Linux container; bwrap is Linux-only), but it must be guarded with `if sys.platform == "linux"` before Flight 4 / Mission 15, which may run on macOS dev machines.
- **`ctypes.CDLL` is reloaded on every `start()` call**, not once at module level — a small per-session `dlopen` cost and a hardcoded `libc.so.6` assumption in the hot path. Low priority; fold the platform guard + a module-level lazy singleton together.
- **The child-side `prctl` return value is ignored** (correct for optional defense-in-depth) but undocumented as a deliberate no-check — a one-line comment would make it auditable.
- **Driver-subprocess regression test has no explicit `readline()` timeout** — if the driver dies before printing `READY` the test relies on the pytest `--timeout` to fail rather than failing fast. Latent fragility, not a bug.

#### Test metrics (this flight seeds/extends the baseline)

Full default suite (`-m "not requires_bwrap"`, container): **3015 passed**, 52 skipped, **5 failed / 486 errored — all pre-existing** (486 = Playwright/Chromium not installed; 4 = live-LLM AIAT; 1 = Playwright smoke). `@requires_bwrap` arm: **14 passed**, 12.50s.

Deltas vs the F2 debrief's recorded numbers: full-suite passing **3008 → 3015 (+7)** (2 CLI-parity tests + 1 app-crash regression + fixture-consolidation surfacing previously-deselected bodies); `@requires_bwrap` **12 → 14 (+2)** (the two new bwrap tests), wall-clock 10.19s → 12.50s (+2.31s, dominated by the app-crash test's deliberate ~1s reap settle). The full-suite wall clock read 318s → 430s, but the bwrap arm (compute-bound, stable) moved only +2.3s and the per-leg hermetic runs showed no per-test slowdown — the full-suite delta is almost certainly Docker/host-load noise during this run, not a regression. Recommend a warm re-run if the number matters for CI planning. **0 new failures.**

### Documentation

- The `_TOOL_CLASSES` cross-config resolution rule (first tool whose `Config IS FilesystemConfig` wins → `read_file`) is documented only in the new test's module docstring. It's a real gotcha for future tool-config tests and belongs as a two-line note in the sandbox-testing section of `agents.md`.
- The read-scoping mission known-issue should record its specific technical blocker (`ldd`/overlayfs) and which future flight would own it, so it doesn't read as indefinitely "just open."

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Optional pre-`execvp` pdeathsig INCLUDED | Host bwrap confirmed not setuid/setcap; cheap belt-and-suspenders for the startup race | Yes — but gate the libc load on `sys.platform == "linux"` and document the pattern in `pty.py` |
| `uat-and-alignment` HAT skipped | Operator: no UI changed this flight; automated tests + live behavior test suffice | Yes — skip the HAT when a flight has no user-facing surface |
| `verify-integration` run directly by the Flight Director (no Developer agent, no design review) | A verification leg runs the matrix + drives the behavior-test crew; it implements no code | Yes — verification legs don't need a design-review cycle |
| Live behavior test run in re-spawn mode as two Executor batches (steps 1–4, 5–6) | `SendMessage` unavailable; the PTY lifecycle (steps 5–6) is coupled and must not split across re-spawned agents | Yes — couple stateful checkpoints into one Executor batch in re-spawn mode; keep Validators independent |
| CM-based test cleanup incidentally hardened PTY-orphan-test teardown | `home_workspace`/CM `finally` now covers `session.start()` throws | Acceptable improvement (no assertion change) |

## Key Learnings

- **Cross-config resolution order is policy.** `get_tools` resolves a shared `FilesystemConfig` from the first `_TOOL_CLASSES` entry whose `Config IS FilesystemConfig`. Any test or future tool that assumes "`shell` carries the FS policy" is wrong. Flight 4 must not reorder `_TOOL_CLASSES` (or must add a defensive assertion) — a new FS-Config tool inserted before `read_file` would silently change which config the shell/python tools read.
- **Fork-safety is a recurring constraint in `pty.py`.** This is the second time the module's DD1 rule mattered (SpawnSpec-in-parent, now libc-in-parent). It deserves promotion from inline comments to a named module-level convention so future fork-child work doesn't rediscover it.
- **A live behavior test authored agent-safe from the start passes cleanly.** The F2 lesson (no exploit-and-read-error steps) was applied in the spec and produced 0 inconclusive checkpoints — the design discipline directly bought a clean run.
- **Empirically verifying a load-bearing premise can delete scope.** DD4's measurement (bwrap's own `--die-with-parent`) turned a feared orphan window into a non-issue and a standalone leg into a few lines.

## Recommendations

1. **Guard the `ctypes.CDLL` load with `sys.platform == "linux"`** (and move it to a module-level lazy singleton). Small, latent macOS regression introduced this flight; fix before Flight 4 / Mission 15 touches non-Linux. *(Critical for non-Linux; harmless on the current Linux-container deployment.)*
2. **Promote the fork-safety + libc-preload pattern to a named convention** in `pty.py`'s module docstring (and a line in `agents.md`), and front-load the fork-safety constraint into any future flight spec that touches the fork child. *(Important — prevents rediscovery / re-introduction of the dlopen-in-child anti-pattern.)*
3. **Document the `_TOOL_CLASSES` cross-config resolution rule** in `agents.md`'s sandbox-testing section, and add a defensive comment in `builtins.py` that ordering has policy consequences. *(Important for Flight 4.)*
4. **Resolve the deferred `SandboxError` import-cycle inversion (DD1) in end-of-mission maintenance before Flight 4 lands** — Flight 4 may add new `platform/sandbox` error paths; don't let a fifth function-level-import workaround accrete. *(Important.)*
5. **Put read-scoping on Flight 4's scope-decision table explicitly** (record the `ldd`/overlayfs blocker on the mission known-issue) so the unmet "cannot read outside scope" criterion is owned, not perpetually deferred. *(Minor — process hygiene.)*

## Action Items

- [ ] **Guard `ctypes.CDLL("libc.so.6")` with `sys.platform == "linux"`** in `the_one/platform/pty.py` (+ module-level lazy singleton); add a one-line comment that the child-side `prctl` return is intentionally unchecked. *(Critical — do before Flight 4.)*
- [ ] Add a two-line note to `the_one/agents.md` sandbox-testing section on `_TOOL_CLASSES` cross-config resolution order (`read_file` carries the shared `FilesystemConfig`).
- [ ] Promote the `pty.py` fork-safety + libc-preload pattern to a named module-docstring convention.
- [ ] **Cross-repo follow-up (DD6)**: land the agent-safe-observable rule in mission-control's `.claude/skills/behavior-test/AUTHORING.md` (the rule was *applied* this flight; the doc change is still open).
- [ ] Carry to end-of-mission maintenance: `SandboxError` relocation / import-cycle inversion (DD1); update the read-scoping known-issue with its `ldd`/overlayfs blocker + owning flight.
- [ ] Optional: warm re-run of the full suite if the 318s→430s wall-clock figure matters for CI planning (suspected host-load noise, not a regression).
- [ ] Cleanup (optional): delete the `sandbox-test` agent + `~/.ssh/id_test` fixture left on the running instance for behavior-test re-runs, when no longer needed.
