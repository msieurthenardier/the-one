# Flight Debrief: PTY Through the Seam

**Date**: 2026-06-07
**Flight**: [PTY Through the Seam](flight.md)
**Status**: landed
**Duration**: 2026-06-06 (plan) → 2026-06-07 (landed) — batched `/agentic-workflow` execution
**Legs Completed**: 4 of 4 autonomous + 1 optional HAT (accepted via behavior-test review)

## Outcome Assessment

### Objectives Achieved

The flight routed the fourth and last unsandboxed subprocess spawn path —
interactive PTY sessions (`pty.fork()` + child-side `execvp`) — through the shared
bubblewrap seam built in Flight 1. Landed:

- `UnixPtySession.start()` computes a `SpawnSpec` in the **parent** before
  `pty.fork()` (`pty.py:212-230`, fork-safe) and the forked child execs the wrapped
  command through `spec.command`/`spec.args`/`spec.env`/`spec.cwd` (`pty.py:251-255`).
  On Linux the child execs `bwrap`; under passthrough it execs the bare shell —
  **single-path**, retiring the dual-path debt Flight 1 carried in
  `shell.py`/`interpreter.py`.
- Teardown: `_close_blocking` keys on `self._wrapped = (spec.command == "bwrap")`
  (`pty.py:233`) — **single-pid SIGKILL-fast** on the wrapped path (bwrap doesn't
  forward SIGTERM; `--die-with-parent` + PID-namespace teardown reaps `setsid`'d
  grandchildren that killpg would miss), SIGTERM-first on passthrough. No in-`close()`
  settle (it's test-side).
- `ShellSessionStartTool.execute` builds the host-workspace profile via
  `_build_tool_profile(fs_cfg, exec_cfg)` (`sessions.py:137`) and threads it into
  `create_pty_session` — one policy source for all four spawn types.
- `@requires_bwrap` PTY containment suite (`tests/test_pty_sandbox.py`, 5 tests) +
  the live `/behavior-test pty-session-containment` run; docs updated.

**Operator-verified live**: the Sonnet agent in the running app drove a tool-launched
PTY session end-to-end — real `$HOME` writable (`/root`), `/etc` write blocked
("Read-only file system"), `~/.ssh/test_key` denylist-protected (host secret
unchanged), and the backgrounded `sleep` grandchild + the session's bwrap tree reaped
on `shell_session_close` — confirming kernel-level enforcement through the real tool
surface, not just argv shape.

### Mission Criteria Advanced

| Mission success criterion | This flight |
|---|---|
| All four spawn paths through one boundary | **Complete** (PTY was the fourth — shell/python/MCP landed in F1) |
| Interactive PTY session governed by the boundary on Linux | **Achieved** (behavior-test-backed; `@requires_bwrap` + live run) |
| No-backend platform routes via passthrough, no construction error | **Preserved** (single-path; passthrough reproduces today's behavior) |
| Uniform policy from one source (built-in + MCP + PTY) | **Achieved** (`_build_tool_profile` reused) |
| Existing behavior preserved (suite passes, ruff passes) | **Achieved** (no regressions) |
| CLI sandboxed identically to web | Not this flight (Flight 3) |
| Cannot **read** outside scope | Still open mission-level (read-scoping deferred since F1) |

### Checkpoints

All in-flight checkpoints met except the live behavior-test network checkpoint
(INCONCLUSIVE — see What Could Be Improved). The network-deny property is proven
deterministically by the `@requires_bwrap` suite, so the inconclusive is an apparatus
limitation, not an unmet criterion.

## What Went Well

- **Every Phase-5b/leg design decision held against real bwrap.** DD1 (parent-side
  SpawnSpec; slave-PTY fds + controlling tty survive `execvp("bwrap")` because bwrap
  keeps fds 0/1/2 and emits no `--new-session`), DD2 (single-path), DD3
  (`_build_tool_profile` reuse), DD5 (orphan-survival), and the resolved teardown
  (single-pid SIGKILL-fast + `--die-with-parent`) were all confirmed by the
  `@requires_bwrap` suite and the live run. The architect's planning-time prediction
  needed zero revision in composition shape.
- **Per-leg design review caught a ship-blocking bug before implementation.** The
  Leg-2 review identified that `test_session_tools.py`'s `create_pty_session` mock
  lambdas (`:67,93,113,134`) needed a `profile=None` signature fix — NOT
  passthrough-pinning; a literal reading of the original leg text would have shipped
  red tests (`TypeError`). This was the highest-value review catch of the flight.
- **Orphan-survival self-validated in the leg that wrote the kill code.** Moving the
  test into `pty-platform-seam` (a design-review correction) meant the teardown
  argument was tested where it was implemented — it passed first try
  (`pids_after_close=set()`).
- **The apparatus both-axes audit earned its keep.** Auditing act AND observe at
  planning (with code citations) confirmed the drive surface was real and the read
  path pre-existing — and correctly flagged the `~/.ssh` denylist fixture
  precondition (`--ro-bind-try` skips absent paths) that would otherwise have made
  the live denylist checkpoint a false-PASS.
- **Reviewer scaled to diff risk.** The Phase-2d code review used Sonnet (not the
  crew-default Haiku) for the security-critical sandbox diff — the standardized
  Flight-1 lesson applied again — and confirmed no path leaves a tool-launched PTY
  unsandboxed on a bwrap host.

## What Could Be Improved

### Process
- **The `test_end_to_end_real_pty_round_trip` pin permanence wasn't anticipated at
  planning.** Leg 1 pinned it to passthrough as a *temporary* measure expecting Leg 2
  to depin it once a real profile flowed through. Leg 2 discovered the pin must be
  **permanent**: bwrap's `--tmpfs /tmp` shadows any `pytest tmp_path` regardless of
  profile. The fix (rationale-comment update) was correct, but the `tmp_path` vs
  `--tmpfs /tmp` interaction should have been reasoned through at planning so Leg 2's
  scope was accurate from the start. **Lesson:** when a bwrap test touches a workspace,
  trace where the workspace lives against bwrap's mount table (`/tmp` is always a fresh
  tmpfs) before assuming it's reachable inside the sandbox.
- **The behavior-test network step was authored around agent cooperation, not an
  agent-safe observable.** The step drove a raw outbound socket connect through the
  agent; a safety-aligned agent refuses to open raw sockets even to prove the sandbox
  blocks them, yielding INCONCLUSIVE instead of PASS. The apparatus audit flagged the
  agent-cooperation *question* but the spec proceeded without committing to the
  namespace-isolation fallback. The spec was re-authored post-run, but it shouldn't
  have needed a post-run correction. **Lesson → standardized below.**

### Technical
- **`profile: object | None` typing debt** (`pty.py:170,558`): typed as `object` to
  avoid a module-level `SandboxProfile` import (the `tools→platform→tools` cycle). The
  function-level imports inside `start()` get the real type, but the public signature
  is type-checker-blind. **Resolve before Flight 4** (boxed mode changes the profile
  shape) via a `TYPE_CHECKING`-guarded module-level import + a `"SandboxProfile | None"`
  string annotation — zero runtime cost, restores type safety at the tool-layer call
  sites.
- **Inherited Flight-1 debts still open**: `SandboxError` still lives in
  `mcp/errors.py:37` (platform-wide now; `base.py:75-79` records the relocation debt);
  the `factory.py:61` docstring still says "until leg 3 reconciles" (long done); the
  `BubblewrapSandbox.__init__` message (`bubblewrap.py:69`) still reads "MCP sandbox
  setup failed" (now platform-wide, including PTY). Bundle into the end-of-mission
  maintenance pass.
- **Coverage gaps** (low risk, named for completeness): the `profile=None` strict-cage
  fallback on a bwrap host has no `@requires_bwrap` test; there's no end-to-end
  `ShellSessionStartTool → create_pty_session → real bwrap` test (only below the tool
  layer); the SIGTERM→1s→SIGKILL passthrough escalation isn't exercised through the
  full grace; the optional `profile=None`-on-bwrap `logging.warning` was not added.
- **Minor immutable-leg artifact**: Leg 2's acceptance-criteria line names
  `test_session_tools.py` twice (the second should read `test_session_lifecycle.py`) —
  a copy-paste slip in a completed leg; left as-is (legs immutable once in-flight).

### Documentation
- **Three patterns/constraints worth codifying are not yet in `agents.md`/`CLAUDE.md`:**
  the **spec-level teardown-dispatch** pattern (`self._wrapped = spec.command ==
  "bwrap"`); the **PTY-echo sentinel collision** footgun and its `"con"+"nected"`
  string-concat fix (discovered empirically in Leg 3, cost a test rewrite); and the
  **`@requires_bwrap` workspace-under-`$HOME`** constraint (`/tmp` is shadowed by the
  tmpfs) — currently only in a test module docstring.
- **Flight-1 doc action item still open**: document the `--ro-bind-try` silent-skip of
  absent denylist paths in `SECURITY-MODEL.md` (this flight re-hit it as a behavior-test
  precondition).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Confirm-reaped settle moved test-side (not in `close()`) | Keeps `close()` prompt; async namespace-teardown propagation to `/proc` is a test concern | Yes — production teardown shouldn't pay for test-observation latency |
| `test_end_to_end_real_pty_round_trip` passthrough pin made permanent | bwrap `--tmpfs /tmp` shadows `tmp_path` regardless of profile | N/A (spec fix) — but standardize the "trace workspace vs bwrap mount table" review check |
| Network-test sentinel encoded as `"con"+"nected"` | PTY echoes the input command; literal `connected` in the source contaminated the deny-path assertion | Yes — PTY string-in-output assertions must avoid token overlap between command and expected output |
| Orphan-survival test relocated into `pty-platform-seam` | Self-validate the kill code in the leg that writes it | Yes — co-locate the load-bearing test with the mechanism it gates |
| Phase-2d Reviewer on Sonnet (crew default Haiku) | Security-critical sandbox diff | Yes — already standardized in F1; reaffirmed |

## Key Learnings

- **Single-pid SIGKILL + `--die-with-parent` is strictly stronger than killpg for a
  PTY-in-a-PID-namespace.** When bwrap is PID 1 of the namespace, killing it triggers
  kernel teardown that reaps `setsid`'d grandchildren killpg would miss. The Flight-1
  killpg rationale did not transfer; the architect's resolution was correct on every
  testable claim.
- **Spec-level teardown dispatch (`spec.command`), not backend-name dispatch.** Keying
  the kill strategy on the actual wrapped command survives backend refactoring — a
  future backend with a different `name` but the same `bwrap` command is handled
  correctly. Worth standardizing.
- **Containment behavior tests must assert agent-safe observables.** A safety-aligned
  agent refuses to perform the "bad" action (raw socket, system-path write) even to
  prove the sandbox blocks it. Assert the *namespace/host state* the agent cooperates
  with (`/proc/net/dev` shows only `lo`; host file absent/unchanged; `pgrep` empty
  post-close) — never "perform the exploit and observe the error." This is the
  canonical lesson of the flight.
- **The apparatus both-axes audit prevents mid-flight scrambles.** Auditing observe (not
  just act) at planning surfaced the denylist-fixture precondition before the run, not
  during it.

### Test Metrics

| Metric | F1 baseline | F2 this run | Delta |
|--------|-------------|-------------|-------|
| Full suite passed | 3007 | **3008** | +1 (the `_build_tool_profile` unit test) |
| Skipped | 4 | 4 | 0 |
| Deselected | 552 | **557** | +5 (the new `@requires_bwrap` PTY tests) |
| Wall clock | 303.98s | **318.37s** | +14.39s (+4.7%; the 5 new passthrough PTY platform tests each fork a real shell) |
| `@requires_bwrap` passed | 7 | **12** | +5 |
| `@requires_bwrap` wall clock | 6.06s | 10.19s | +4.13s |

No regressions. The known pre-existing flake `test_connectors_e2e.py::test_e2e_full_lifecycle`
did **not** appear this run (this flight touches no connector code). The `@requires_bwrap`
tests validate real kernel enforcement (host-filesystem assertions, real TCP connect,
host `pgrep` process-table reads) — not argv shape; the denylist test's sibling-allowed
control proves the boundary is directional, not "everything read-only."

## Recommendations

1. **Standardize the agent-safe-observable rule for containment behavior tests.** Add
   it to `AUTHORING.md` (and reference in `agents.md`): containment checkpoints assert
   namespace/host state the agent cooperates with, never "perform the blocked action."
   The re-authored `pty-session-containment` network step is the template. Apply from
   the start in Flight 3 (CLI parity) and Flight 4 (boxed mode) specs.
2. **Resolve the `profile: object | None` typing debt before Flight 4** via a
   `TYPE_CHECKING`-guarded import + string annotation — boxed mode changes the profile
   shape and needs the type checker watching the tool-layer call sites.
3. **Elevate the `@requires_bwrap` workspace-under-`$HOME` constraint to a project-wide
   testing guideline** (CLAUDE.md Testing section or `agents.md`), plus document the
   PTY-echo sentinel footgun and the spec-level teardown-dispatch pattern — three
   non-obvious footguns currently living only in code/test comments.
4. **Close the carried doc/message debts in the end-of-mission maintenance pass**: the
   `--ro-bind-try` silent-skip note in `SECURITY-MODEL.md` (Flight-1 action item, re-hit
   here), the stale `factory.py:61` docstring, the `bubblewrap.py:69` "MCP sandbox setup
   failed" message, and the `SandboxError` relocation out of `mcp/errors.py`.
5. **Revisit the host-crash PTY-orphan window before mission close.** `--die-with-parent`
   ties the inner shell to bwrap-outer, but bwrap-outer isn't tied to the Python app; an
   app crash without `close()` relies on the registry reaper. Larger window for
   long-lived PTY than one-shot spawns — candidate fix: `PR_SET_PDEATHSIG` on bwrap-outer
   tied to the Python parent. Carry as a mission-level open item.

## Action Items
- [ ] Author the agent-safe-observable rule in `.claude/skills/behavior-test/AUTHORING.md`
      (mission-control side) and reference it in the-one's `agents.md` (next planning conversation).
- [ ] Flight 3 pre-flight: apply the both-axes apparatus audit to the **CLI** act-path;
      add a `@requires_bwrap` test that drives the CLI entry point (Flight-1 + F2 carry).
- [ ] Before Flight 4: resolve `profile: object | None` → `TYPE_CHECKING` import +
      `"SandboxProfile | None"`; decide boxed-mode namespace-flag defaults.
- [ ] End-of-mission maintenance: `--ro-bind-try` doc in `SECURITY-MODEL.md`; stale
      `factory.py`/`bubblewrap.py` messages; `SandboxError` relocation; add the
      `@requires_bwrap` workspace-under-`$HOME` + PTY-echo + teardown-dispatch notes to
      `agents.md`/`CLAUDE.md`.
- [ ] Carry to mission known-issues: host-crash PTY-orphan window; read-scoping (unmet
      mission criterion since F1).
- [ ] Optional (low pri): add a `logging.warning` when `create_pty_session` is called
      with `profile=None` on a bubblewrap host (silent strict-cage debuggability).
