# Flight Debrief: Sandbox Seam + Built-in Tool Retrofit

**Date**: 2026-06-06
**Flight**: [Sandbox Seam + Built-in Tool Retrofit](flight.md)
**Status**: landed → completed
**Duration**: 2026-06-06 (single session, batched `/agentic-workflow` execution)
**Legs Completed**: 5 of 5

## Outcome Assessment

### Objectives Achieved

The flight created the shared tool-execution sandbox boundary and routed the three
non-PTY spawn sites through it. Concretely, landed:

- A backend-selection factory (`get_sandbox_backend()`) over `BubblewrapSandbox`
  (Linux+bwrap) and a new `PassthroughSandbox` (everywhere else / bwrap-missing /
  test-bypass), logged once with the selection reason.
- `SandboxProfile` extended with `readonly_overlay_paths` and a programmatic-only
  `home`; bubblewrap emits a `--ro-bind-try` denylist overlay and a profile-driven
  HOME.
- MCP stdio retrofitted to obtain its backend from the factory (no construction-time
  error off-Linux/bwrap-missing).
- Built-in `shell` and `python_exec` routed through the seam via one shared
  `_build_tool_profile()` (host-workspace profile: writable allowlist, read-only
  denylist overlay, real `$HOME`, network deny-by-default via
  `ExecutionConfig.sandbox_network_allowed`).
- The `MCP`-prefixed abstraction renamed in place to `ToolSandbox` / `SandboxError`,
  preserving the `MCPClientError` hierarchy and `client.py`'s teardown catch.

**Operator-verified live**: a Sonnet agent in the running app demonstrated the
host-workspace profile end to end — real `$HOME` writable, `/etc` write blocked
("Read-only file system"), and outbound network blocked at the OS layer
(`ENETUNREACH` from a `python_exec` socket) — confirming kernel-level enforcement,
not a userspace check.

### Mission Criteria Advanced

| Mission success criterion | This flight |
|---|---|
| All four spawn paths through one boundary | **3 of 4** (shell, python, MCP stdio); PTY is Flight 2 |
| Linux built-in tool cannot **write** outside scope; network policy-constrained | **Achieved** (write + network + namespace; read-scoping deferred — DD5) |
| PTY governed by the boundary | Not this flight (Flight 2) |
| CLI sandboxed identically to web | Not this flight (Flight 3 — code already shares the spawn helpers; verification pending) |
| No-backend platform routes via passthrough, no construction error, observable | **Achieved** (factory + one-time WARNING) |
| Uniform policy from one source for built-in + MCP | **Achieved** (one `SandboxProfile` model; `_build_tool_profile` + `from_dict`) |
| Existing behavior preserved (MCP launches, suite passes, ruff passes) | **Achieved** |

## What Went Well

- **The seam abstraction (DD1) held perfectly.** `prepare_spawn → SpawnSpec` with
  site-specific runners required zero revision; MCP feeds `StdioServerParameters`,
  built-in tools feed `create_subprocess_exec`. The uniform thing really was just
  policy+wrapping.
- **`_build_tool_profile` is a genuinely clean Flight-4 hook (DD10).** A pure
  `(FilesystemConfig, ExecutionConfig) → SandboxProfile` function reading already-
  canonicalized paths; boxed mode is a profile-shape branch, not a re-architecture.
- **Per-leg design review caught real, code-verified issues *before* implementation**
  every time: class-name-as-rendered-string test assertions (leg 1), the
  monkeypatch object-form + stale `agents.md` HOME claim (leg 2), the factory's
  lazy-import breaking the old test-patch pattern (leg 3), the `--ro-bind-try`
  absent-path requirement + network-test rationale (leg 4), and five now-false doc
  claims (leg 5). The 1-cycle "approve with changes, skip second review" pattern was
  the right call — findings were self-verifying with file/line citations.
- **The `@requires_bwrap` containment tests prove real OS enforcement**, not argv
  shape: write-denied-outside-allowlist, denylist-secret-write-denied (with sibling-
  allowed control), network deny/allow via a real loopback server, real-HOME
  persistence, and timeout-kill-no-orphan. All 7 green in 6.06s.
- **Kill strategy validated empirically.** Keeping `start_new_session=True` + killpg
  for both paths (bwrap as group leader) reaped the wrapped tree; the pre-flight
  open question ("need a bwrap-pid SIGKILL branch?") was definitively answered *no*
  by the timeout-kill test.

## What Could Be Improved

### Process
- **Leg 4 was too heavy** — 8 files across 3 layers (tool wiring + platform
  subprocess behavior + a retroactive `--ro-bind` → `--ro-bind-try` fix to leg-2
  code + a 340-line new test file). It landed cleanly, but a 4a (profile fn + tool
  wiring) / 4b (platform sandboxed path + kill + containment tests) split would have
  isolated the cross-leg dependency. **Lesson:** when a leg wires the tool layer
  *and* changes platform subprocess behavior, make the platform changes their own
  leg.
- **A flight-spec contradiction (DD4 vs DD5/Verification)** required a Flight-
  Director ruling mid-flight: DD4 said `--ro-bind` (write-protection, readable) while
  DD5's parenthetical and Verification (b) claimed the overlay "blocks reads" — which
  `--ro-bind` cannot do under a `--ro-bind / /` base. **Lesson:** when a flight
  design specifies a denylist mechanism, state explicitly whether it's write-/read-/
  both-blocking and trace what the base mount already permits (the base sets the read
  floor).

### Technical
- **Two-codepath `profile`-opt-in split** in `platform/shell.py` /
  `platform/interpreter.py` (legacy `profile is None` vs seam path) is acceptable
  pragmatism (keeps the platform tests untouched) but is permanent dual-path debt.
  Flight 2 (PTY) faces the same choice and should decide it in the spec, not during
  a leg review.
- **`SandboxError` location debt (DD8 deferred):** the error is now platform-wide but
  still canonically lives in `the_one/mcp/errors.py` (to preserve
  `client.py`'s `except MCPClientError`). New sandbox errors should go to
  `platform/sandbox/` immediately; a future flight should invert the dependency.
- **`tools → platform → tools` cycle** is avoided via function-level imports in the
  platform helpers — a known boundary smell. A clean `platform/sandbox` package with
  no upward dependency would remove the workaround.
- **Test metrics:** full suite **3007 passed / 4 skipped / 552 deselected / 303.98s**
  (`@requires_bwrap`: 7 passed / 6.06s). Growth vs the prior debrief (M13 F03:
  2990 passed / 298.85s) is **+17 passed, +5.13s (+1.7%)** — proportional to the 24
  new tests (12 factory + 3 bubblewrap + contract additions + 5 bwrap-gated), no
  per-test slowdown. Skip count fell 9 → 4 (test-isolation improvement). No
  regressions.
- **Pre-existing non-deterministic failure:** `test_connectors_e2e.py::test_e2e_full_lifecycle`
  (a pool-reaping assertion) appeared in the leg-1 run and was absent thereafter.
  Unrelated to this flight, but its flakiness makes it an unreliable CI signal —
  worth a routine-maintenance investigation.

### Documentation
- Doc-sync was thorough this flight (agents.md, mcp/README.md, SECURITY-MODEL.md,
  README.md, CLAUDE.md, pyproject.toml all corrected, including several now-false
  claims). Residual nits: `factory.py`'s docstring still says "until leg 3
  reconciles" (reconciliation done); `BubblewrapSandbox.__init__`'s error message
  still reads "MCP sandbox setup failed" (now platform-wide); `agents.md` could use a
  dedicated `### the_one/platform/sandbox/` subsection now that the sub-package has
  four modules.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| DD3 WARNING moved from `PassthroughSandbox` into the factory | Factory is the single selection locus and knows the reason → level; avoids per-instance global state | Yes — log selection at the selection locus |
| DD4/DD5 read-vs-write contradiction resolved to write-protection only | `--ro-bind` cannot block reads under `--ro-bind / /`; honored DD4 + DD5's read-scoping deferral | N/A (spec fix) — but standardize the "characterize denylist mechanism explicitly" review check |
| Overlay `--ro-bind` → `--ro-bind-try` | Denylist has ~optional secret paths that often don't exist; hard bind aborts the spawn | Yes — denylist overlays should tolerate absent paths |
| Optional-`profile` seam split (legacy path preserved) | Keep `test_platform_shell`/`_interpreter` untouched | Decide per flight; revisit for PTY |
| Reviewer on Sonnet (crew default Haiku) | Security-critical 14-file diff exceeds Haiku's competence | Standardize: scale Reviewer model to diff risk/size (never Opus) |

## Key Learnings

- **A `prepare_spawn → SpawnSpec` seam generalizes cleanly across heterogeneous
  runners** (SDK transport vs `create_subprocess_exec`). Keep the policy uniform,
  let runners stay site-specific.
- **bwrap is a per-execution policy dial, not an outer cage.** The host-workspace
  profile (capable in workspace, OS-enforced leakage prevention) is the right default
  posture; the operator-verified `ENETUNREACH`/read-only-fs behavior shows the
  enforcement is kernel-level.
- **Read-scoping is genuinely hard and was correctly deferred** — a shell needs
  `/bin`/`/lib`/`/usr`, python needs its stdlib; a real read allowlist diverges from
  the MCP backend and likely needs `ldd`-derived binds or overlayfs. The mission
  criterion "cannot read outside scope" remains an open mission-level item.
- **Lazy-import factories defeat module-level test patching.** Tests must patch
  `get_sandbox_backend` (or env/`shutil.which`), not the backend class — document the
  pattern.

## Recommendations

1. **Flight 2 (PTY) pre-flight must settle the hard questions up front**: the
   `profile`-opt-in split for the long-lived PTY path; PTY + `--unshare-pid` init/
   reaping behavior; a dedicated `@requires_bwrap` PTY orphan-survival-after-close
   test; and reuse `_build_tool_profile` so PTY gets the real `$HOME` (not `/tmp`).
2. **Adopt a flight-design review check**: any denylist/containment mechanism must
   state write-/read-/both semantics and trace the base-mount floor (prevents the
   DD4/DD5 class of contradiction).
3. **Split platform-subprocess changes into their own leg** when a leg also wires the
   tool layer (the Leg 4 lesson).
4. **Track read-scoping as a mission-level open item** — the "cannot read outside
   scope" criterion is unmet and needs its own flight with an `ldd`/overlayfs
   approach.
5. **Pay down the small debts**: `SandboxError` relocation (DD8), the
   `tools↔platform` import-cycle workaround, and the stale `factory.py` docstring /
   `BubblewrapSandbox` error message — fold into the end-of-mission maintenance pass.

## Action Items
- [ ] Flight 2 pre-flight: resolve PTY profile-split + kill strategy + add PTY
      orphan-survival `@requires_bwrap` test (carry into Flight 2 design).
- [ ] Add unit tests: `_build_tool_profile(FilesystemConfig(), ExecutionConfig())`
      (default-allowlist production path); `sandbox_network_allowed` resolver/narrowing
      contract; cwd-through-sandbox containment.
- [ ] Update `factory.py` docstring ("until leg 3 reconciles" → done) and
      `BubblewrapSandbox.__init__` error message ("MCP sandbox setup failed" →
      platform-neutral).
- [ ] Document `--ro-bind-try` silent-skip of absent denylist paths in
      `SECURITY-MODEL.md`.
- [ ] Add an `### the_one/platform/sandbox/` subsection to `agents.md`.
- [ ] Investigate `test_connectors_e2e.py::test_e2e_full_lifecycle` non-determinism
      (routine maintenance).
- [ ] Carry read-scoping + `SandboxError` relocation as mission/maintenance open
      items.
