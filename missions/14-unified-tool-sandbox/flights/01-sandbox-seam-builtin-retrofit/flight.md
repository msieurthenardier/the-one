# Flight: Sandbox Seam + Built-in Tool Retrofit

**Status**: completed
**Mission**: [Unified Tool-Execution Sandbox](../../mission.md)

## Contributing to Criteria
- [x] All subprocess spawn paths route through one shared sandboxing boundary
      *(this flight: shell, Python, MCP stdio — three of four; PTY is Flight 2)*
- [x] On Linux, a built-in tool process cannot **write** outside its permitted
      filesystem scope, cannot touch denylisted paths (secrets), and its network
      access is constrained by policy *(read-scoping deferred — see DD5)*
- [x] On a platform with no sandbox backend, the app runs through the shared seam
      via a passthrough and does not error at construction
- [x] The sandbox policy is applied uniformly to built-in tools and MCP servers
      from one policy source
- [x] Existing behavior preserved: MCP servers still launch, tests pass, ruff gate passes

---

## Pre-Flight

### Objective

Create the shared sandboxing boundary — a backend-selection factory plus a
passthrough backend — and route the three non-PTY spawn sites (ShellTool,
PythonExecTool, MCP stdio) through it. The seam enforces a *configurable policy*,
not a fixed cage: built-in tools land on a **host-workspace** profile — the
capable-assistant default — that lets the agent do real work within the operator's
filesystem allowlist while OS-enforcing leakage prevention (denylisted secrets
blocked, network opt-in). Off-Linux (and where `bwrap` is absent) the same seam
routes through a no-op passthrough so the app runs without erroring. The
MCP-prefixed abstraction is renamed in place to be platform-neutral. PTY retrofit,
macOS backend, read-scoping, CLI-parity verification, and agent-selectable boxed
mode (Flight 4) are explicitly out of scope — but the per-tool **profile
derivation is built as one clean function** so Flight 4's boxed profile is a branch
there, not a re-architecture.

### Open Questions
- [x] Network default for built-in tools → **deny by default, opt-in via config**
      (DD6)
- [x] Read containment this flight → **deferred; write + network + namespace +
      denylist-overlay only** (DD5)
- [x] Verification apparatus → **`@requires_bwrap` integration tests**, not the
      live-agent behavior-test apparatus
- [x] Rename the `MCP`-prefixed abstraction → **yes, rename in place** (DD8)
- [x] Denylist OS-enforcement → **yes, read-only overlay** (DD4)
- [x] `$HOME` inside a built-in-tool sandbox → **real home** (DD4)
- [x] `ExecutionConfig` migration → **none needed**; tool configs are a JSON blob
      (`tool_configs.config TEXT DEFAULT '{}'`) validated with Pydantic
      `extra=ignore`, so a new defaulted field reads back as its default
- [ ] `start_new_session=True` vs bwrap `--unshare-pid` — confirm the wrapped-spawn
      kill strategy in the `builtin-tool-seam` leg (proposed: rely on
      `--die-with-parent` + kill the bwrap PID for wrapped spawns; keep group-kill
      for the passthrough path). Validate with a `@requires_bwrap` timeout test.

### Design Decisions

**DD1 — The seam is the backend + `prepare_spawn` → `SpawnSpec`, applied per
spawn site; execution mechanics stay site-specific.**
- Rationale: the existing contract already models a wrapped spawn. MCP hands the
  result to the SDK (`StdioServerParameters`); built-in tools run it via
  `asyncio.create_subprocess_exec`. The uniform thing is the *policy + wrapping*,
  not the runner.

**DD2 — Backend selection via a `get_sandbox_backend()` factory.**
- Returns `BubblewrapSandbox` on Linux when `bwrap` is on `PATH`; returns
  `PassthroughSandbox` otherwise (non-Linux, or `bwrap` missing), and when the
  existing test double-flag bypass (`THE_ONE_SANDBOX_DISABLED=1` +
  `THE_ONE_TEST_MODE=1`) is set. Logs the selected backend **once at startup**.
- Centralizes the construct-time guard (today `BubblewrapSandbox()` is built
  directly at `stdio.py:412` and raises off-Linux) and the MCP-local
  `_sandbox_disabled_for_tests()` bypass into one place all sites share.

**DD3 — `PassthroughSandbox` backend.**
- Satisfies the protocol; `prepare_spawn` returns `SpawnSpec(command, args, env,
  cwd)` unwrapped; namespace/network/writable/overlay fields accepted and ignored
  (forward-compat for the macOS backend's differing field set). Surfaces the
  unsandboxed state via a one-time WARNING, not per-spawn noise.

**DD4 — Built-in tools run a *host-workspace* profile: capable, with OS-enforced
leakage prevention.**
- `writable_paths` = the agent's `FilesystemConfig` allowlist (canonical; default
  `~`). The agent does real work there.
- **Denylist enforced at the OS layer**: add a `readonly_overlay_paths` field to
  `SandboxProfile`; the bubblewrap backend emits `--ro-bind` for canonical
  denylist entries that fall *under* a writable root (e.g. `~/.ssh`, `~/.aws`,
  the app's own `~/.the-one` secrets). This is the "prevent accidental leakage"
  guard — without it, mapping the allowlist to writable makes the whole home
  writable including secrets, since bwrap binds are additive.
- **`$HOME` = the real home** (allowlisted, writable), not the MCP servers'
  ephemeral `/tmp`. The shell tool's contract is "default cwd is `$HOME`"; `~`-
  relative writes must persist. Requires making the backend's hardcoded
  `HOME=/tmp` (`bubblewrap.py:92`) *profile-driven* (a profile flag / explicit
  HOME) so MCP keeps `/tmp` and built-in tools get the real home.
- Rationale: this is the "capable assistant + opt-in leakage prevention" posture —
  not a cage. Net change vs today: write scope shrinks from the whole filesystem
  to the allowlist; secrets become OS-protected; the agent still works freely in
  its workspace. (Full host reach lands when Mission 15 goes native; under Docker
  the allowlist is bounded by what's mounted.)

**DD5 — Read stays broad this flight (`--ro-bind / /`); read-scoping deferred.**
- A shell needs to read `/bin`,`/lib`,`/usr`; python needs its stdlib. True
  read-scoping diverges from the MCP backend and is partly intractable. This
  flight delivers write + network + namespace + denylist-overlay containment; the
  mission's "cannot read outside scope" criterion is carried to a later flight.
  (Note: the denylist overlay *does* block reads of overlaid secret paths.)

**DD6 — Network deny-by-default for built-in tools, opt-in via `ExecutionConfig`.**
- New field `sandbox_network_allowed: bool = False` (mirrors MCP). When False,
  the profile sets `network_allowed=False` → bwrap `--unshare-net`. The agent's
  dedicated web tools (fetch/download/search/http) are unaffected. Per-domain
  allowlist is future work. Migration-free (see Open Questions).

**DD7 — `run_shell` becomes an explicit `exec` under the wrapper.**
- ShellTool spawns via `select_shell()` (`(shell, ["-c"])`, honoring `$SHELL`) +
  `create_subprocess_exec`, wrapped by the backend, replacing
  `create_subprocess_shell`. `select_shell()` exists for exactly this. Behavior:
  OS-chosen `/bin/sh` becomes `$SHELL`-honoring (falls back to `/bin/sh`). Kill/
  timeout drain semantics preserved (see kill-strategy open question).

**DD8 — Rename the abstraction *in place* (not a relocation).**
- `MCPSandbox` → `ToolSandbox`; `MCPSandboxError` → `SandboxError`. **Keep the
  error's canonical home in `the_one/mcp/errors.py` and its `MCPClientError`
  parentage** — `client.py:511` (`except MCPClientError`) deliberately relies on
  that subclassing to propagate sandbox errors through MCP teardown; relocating the
  home out of `mcp/` would silently break that catch (or re-introduce a
  `platform→mcp` dependency). Relocation is deferred. This is a symbol rename, not
  a behavior change — *with* the explicit caveat that the home/hierarchy stay put.
- Blast radius is real (`MCPSandboxError`: ~18 files / ~106 refs incl. tests), so
  the rename is **its own first leg** (DD2/passthrough work then lands on the
  renamed names).

**DD9 — Test determinism for the existing execution-tool unit tests.**
- `tests/conftest.py` sets only `THE_ONE_TEST_MODE` — so once ShellTool/
  PythonExecTool route through the factory, `tests/test_execution_tools.py` would
  silently run under bwrap in-container but passthrough on a bwrap-less host (env
  surface, kill path, HOME all differ). Pin those unit tests to passthrough
  (set `THE_ONE_SANDBOX_DISABLED=1`, mirroring `test_mcp_stdio_sandbox.py`), and
  add *new* `@requires_bwrap` integration tests for the real bwrap path.

**DD10 — Profile derivation is one clean function** (`_build_tool_profile(fs_cfg,
exec_cfg) → SandboxProfile`), shared by ShellTool and PythonExecTool — **not**
inlined into `execute()`. This is the hook Flight 4 (boxed mode) branches in;
the seam already accepts any profile, so nothing downstream changes.

**DD11 — Built-in-tool sandboxing is ON by default on Linux** (gated only by
backend availability); no separate enable/disable knob beyond the network field.

### Prerequisites
- [x] `bwrap` present in the dev/test environment — Dockerfile installs
      `bubblewrap`; `@requires_bwrap` tests gate on its presence.
- [x] Current deployment grants bwrap's user-namespace needs — `docker-compose.yml`
      sets `cap_add: SYS_ADMIN` + `security_opt: seccomp:unconfined`.
- [x] Existing abstraction (`SpawnSpec`/`SandboxProfile`/protocol) + the
      `@requires_bwrap` integration-test pattern exist and are reusable;
      `ShellTool`/`PythonExecTool` already hold `FilesystemConfig` at spawn time
      via `self._cross_configs[FilesystemConfig]`.
- [x] **Verification caveat**: `requires_bwrap` is deselected by the default suite
      (`pyproject.toml` addopts), and there is **no pytest CI yet** (only
      `lint.yml`). Containment is proven by a deliberate `-m requires_bwrap` run on
      a bwrap host; automated CI coverage is a Mission 15 concern.

### Pre-Flight Checklist
- [x] All open questions resolved (kill-strategy resolved in Leg 4: killpg+proc.kill suffices)
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined (`@requires_bwrap` integration + unit tests)
- [x] Legs defined

---

## In-Flight

### Technical Approach

First rename the abstraction in place (`ToolSandbox`/`SandboxError`), preserving the
`MCPClientError` hierarchy and the `client.py:511` catch. Then add `PassthroughSandbox`
and `get_sandbox_backend()` in `the_one/platform/sandbox`, extend `SandboxProfile`
with `readonly_overlay_paths`, and make the backend's `HOME` policy profile-driven
(MCP keeps `/tmp`; built-in tools get the real home). Retrofit the MCP construction
site (`stdio.py:_build_stdio_params`) to obtain its backend from the factory,
folding the test bypass in. Then route ShellTool and PythonExecTool through a shared
`_build_tool_profile()` (writable = `FilesystemConfig` allowlist; overlay = denylist;
network from `ExecutionConfig.sandbox_network_allowed`; real HOME) → `prepare_spawn`
→ run the `SpawnSpec` via `create_subprocess_exec` (ShellTool switching to an explicit
`select_shell()` invocation). Pin the existing execution-tool unit tests to
passthrough and add `@requires_bwrap` integration tests proving containment.

### Checkpoints
- [x] Rename complete across importers (incl. docstrings); `MCPClientError`
      hierarchy + `client.py:511` catch preserved; suite + ruff green.
- [x] `PassthroughSandbox` + `get_sandbox_backend()` land; `readonly_overlay_paths`
      + profile-driven HOME in the backend; startup backend log; unit tests for
      selection (Linux+bwrap → bubblewrap; missing/non-Linux/test-bypass → passthrough).
- [x] MCP stdio path uses the factory; MCP integration tests green; MCP still gets
      `HOME=/tmp`; simulated bwrap-missing / non-Linux yields passthrough (no error).
- [x] ShellTool + PythonExecTool routed through `_build_tool_profile`;
      `@requires_bwrap` tests prove: write outside allowlist denied; a denylisted
      secret path (e.g. `~/.ssh`) is not **writable** (read-scoping deferred per DD5);
      network denied by default and enabled when `sandbox_network_allowed=true`;
      `~`-relative write persists (real HOME); timeout/kill returns promptly under bwrap.
- [x] `test_execution_tools.py` pinned to passthrough and green on a bwrap-less host
      *and* in-container.
- [x] Full suite + ruff green.

### Adaptation Criteria

**Divert if**:
- Wrapping shell/python in bwrap breaks execution in ways the host-workspace
  profile can't express (a binary needs a bind the model can't represent) —
  re-plan the profile shape.
- The rename's blast radius exceeds one leg in practice — it's already its own leg;
  if it still grows, split the test-file updates into a follow-on.

**Acceptable variations**:
- Keeping the `_sandbox_disabled_for_tests` helper name (semantics unchanged) if
  folding it into the factory reads better as a call than a move.
- Splitting `builtin-tool-seam` back into shell/python legs if the shared
  `_build_tool_profile` helper proves non-trivial.

### Legs

> **Note:** Tentative; legs are planned and created one at a time as the flight
> progresses.

- [x] `rename-sandbox-abstraction` - Rename `MCPSandbox`→`ToolSandbox`,
      `MCPSandboxError`→`SandboxError` across all importers (~18 files) + docstrings
      + tests; **keep the error's home in `mcp/errors.py` and its `MCPClientError`
      parentage**; verify `client.py:511` still catches. Pure symbol rename; suite green.
- [x] `sandbox-backend-factory` - Add `PassthroughSandbox` + `get_sandbox_backend()`
      (incl. the test double-flag bypass + startup backend log); add
      `readonly_overlay_paths` to `SandboxProfile` + the bubblewrap `--ro-bind`
      overlay; make the backend `HOME` policy profile-driven. Unit tests for
      selection and for passthrough never raising off-Linux.
- [x] `mcp-via-factory` - Retrofit `stdio.py:_build_stdio_params` to use the factory
      (fold the bypass in); confirm MCP still launches, keeps `HOME=/tmp`, and
      off-Linux routes to passthrough without erroring. `@requires_bwrap` + unit.
- [x] `builtin-tool-seam` - Add `_build_tool_profile()` (writable = allowlist;
      overlay = denylist; network from new `ExecutionConfig.sandbox_network_allowed`;
      real HOME). Route ShellTool (`select_shell()` + exec) and PythonExecTool
      through it; reconcile timeout/kill under bwrap. Pin `test_execution_tools.py`
      to passthrough; add `@requires_bwrap` tests (write-denied-outside-allowlist,
      denylist-secret-denied, network-deny + opt-in, real-HOME persistence,
      timeout-kill). Files: `tools/shell.py`, `tools/python_exec.py`,
      `tools/execution.py`, `platform/shell.py`, `platform/interpreter.py`,
      `tests/test_execution_tools.py`.
- [x] `verify-integration` - Full suite host-native + in-container; ruff gate;
      confirm passthrough (simulated bwrap-missing) does not error; run
      `-m requires_bwrap` on a bwrap host; update `CLAUDE.md`/`agents.md` notes
      describing the seam, the host-workspace profile, and the
      `sandbox_network_allowed` knob.

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing (incl. `-m requires_bwrap` containment run on a bwrap host)
- [x] Documentation updated (seam, host-workspace profile, `sandbox_network_allowed`)

### Verification
- `@requires_bwrap` integration tests prove, for built-in shell/python: (a) a write
  outside the `FilesystemConfig` allowlist is denied; (b) a denylisted secret path
  (e.g. `~/.ssh`) is **not writable** — the `--ro-bind-try` overlay enforces
  write-protection only; read-blocking is deferred to a later flight per DD5
  *(original draft said "neither writable nor readable" — the `--ro-bind` mechanism
  cannot block reads; this was a drafting error resolved by the Flight Director in
  Leg 4; see flight log)*; (c) network is denied by default and enabled when
  `sandbox_network_allowed` is true; (d) a `~`-relative write persists (real HOME);
  (e) a timed-out command is killed promptly under bwrap.
- Unit tests prove the factory selects bubblewrap on Linux+bwrap and passthrough
  otherwise (incl. the test double-flag), and that `PassthroughSandbox` never raises
  off-Linux.
- MCP integration tests confirm no regression (MCP still sandboxed, still `HOME=/tmp`).
- `ruff check` + `ruff format --check` pass; full default suite green.
- **Honest caveat**: the default `pytest` run does **not** exercise containment
  (`requires_bwrap` is deselected) and there is no pytest CI yet — containment is
  proven by the deliberate `-m requires_bwrap` run above; automated CI is Mission 15.
