# Mission: Unified Tool-Execution Sandbox

**Status**: active

> **Split rationale.** This mission was carved out of the original "Native Desktop
> Installers" scope (now Mission 15) so the heaviest, riskiest, and most
> conceptually distinct piece — unifying every tool spawn behind one sandbox
> boundary — gets its own focused mission, debrief, and validation *before* the
> distribution push. It also delivers security value on the **current** product
> independently of installers: built-in tools are unsandboxed today (see Context).
>
> **Architect viability (Phase 4b): feasible with caveats** (focused
> re-validation of this split, against the codebase). Confirmed: the existing
> `SpawnSpec(command, args, env, cwd)` / `SandboxProfile` abstraction generalizes
> cleanly to built-in tool spawns (three of four paths are mechanical retrofits);
> the **CLI already reaches the same platform spawn helpers** as the web path, so
> CLI parity needs no code change (only verification); and the Docker
> `SYS_ADMIN`/`seccomp:unconfined` grant already covers bwrap for all paths, so
> the "no deployment change" claim holds. The caveats are flight-design decisions,
> not scope changes — captured in Open Questions below. The non-Linux failure is
> at `BubblewrapSandbox.__init__` (raises when `bwrap` is absent,
> `bubblewrap.py:58`), and **there is no backend-selection factory today** — one
> must be created in Flight 1, not merely a guard. The PTY path is the heaviest
> (Flight 2) but the mechanism is well-defined.

## Outcome

Every subprocess GleepGlorp AI spawns — its built-in tools (shell, Python
interpreter, interactive PTY sessions) **and** external MCP servers — passes
through one shared sandboxing boundary. On Linux that boundary is enforced: a tool
process cannot read or write outside its permitted filesystem scope or reach the
network beyond policy. The boundary governs the web app and the CLI identically,
so neither face of the app is an unsandboxed back door. On platforms without a
sandbox backend yet, spawns still route through the same seam via a passthrough,
so future per-OS backends slot in behind it without re-plumbing every call site.

## Context

GleepGlorp AI (`the-one`) is a single-user, local-first AI agent platform whose
core value is letting agents *act* — run shells, execute Python, drive PTY
sessions, and call external MCP servers. Sandboxing that action surface is a
security cornerstone.

**The present gap (corrected by the architect review):** sandboxing today wraps
**only** MCP stdio servers — `BubblewrapSandbox` is invoked from a single site
(`mcp/transports/stdio.py:383`). The built-in tools — `ShellTool`,
`PythonExecTool`, and the PTY session tools — spawn subprocesses **directly and
unsandboxed** through `platform/shell.py`, `platform/interpreter.py`, and
`platform/pty.py`. In other words, an agent's built-in shell tool currently has
**no** filesystem or network containment, even in the Docker deployment. There is
no shared seam these paths funnel through — there are four independent spawn sites,
only one of which is sandboxed.

This mission closes that gap by **creating** the shared boundary and routing all
four spawn paths through it, then enforcing it on Linux (generalizing the existing
bubblewrap integration so it covers built-in tools, not just MCP). It also removes
a latent landmine: `BubblewrapSandbox()` is constructed unconditionally and raises
at construction time on macOS/Windows, so a passthrough/null backend plus a
platform guard is part of this mission — both to stop off-Linux from erroring and
to make the seam forward-compatible.

**Relationship to other missions.** This mission ships on the **current**
deployment and changes no distribution or runtime-platform story. It is a
prerequisite for **Mission 15 (Native Desktop Installers)**: once the seam exists,
M15 slots a macOS (Seatbelt) backend in behind it cheaply and adds a Windows PTY
backend through the same boundary. A later "secure the API" mission hardens the
network surface; keeping the boundary at the shared tool-execution layer (not the
web path) is what lets that future work reason cleanly about the CLI as a separate
door.

### Research summary (what shaped the decisions)

- **Build the seam once; swap backends behind it.** The expensive, hard-to-retrofit
  part is the single boundary every spawn passes through — the per-OS backends are
  comparatively cheap to add later. This mission does the expensive part.
- **Anthropic's `@anthropic-ai/sandbox-runtime`** (already referenced in
  `sandbox/base.py`) is the reference abstraction — one API, per-OS native backends
  (bubblewrap on Linux, Seatbelt on macOS), no Docker/root/VM. Whether to adopt it
  directly for the Linux backend or generalize the existing `BubblewrapSandbox` is
  an open question for flight planning; either way the macOS backend it provides is
  what Mission 15 will lean on.

## Success Criteria

- [ ] All four subprocess spawn paths — shell tool, Python interpreter tool, PTY
      sessions, and MCP stdio servers — route through **one shared sandboxing
      boundary**; no spawn site bypasses it.
- [ ] On **Linux**, a built-in tool process (shell or Python) **cannot read or
      write outside its permitted filesystem scope**, and its network access is
      constrained by policy. *(behavior-test-backed — includes escape attempts)*
- [ ] An interactive **PTY session** launched by a tool is governed by the same
      boundary on Linux. *(behavior-test-backed)*
- [ ] A tool launched from the **CLI** is sandboxed identically to the same tool
      launched from the web app — the CLI is not an unsandboxed bypass.
      *(behavior-test-backed)*
- [ ] On a platform with no sandbox backend, the app **runs through the shared seam
      via a passthrough** and does not error at construction; the absence of
      enforcement is observable (logged), not silent.
- [ ] The sandbox policy (filesystem scope, network) is applied **uniformly** to
      built-in tools and MCP servers from one policy source.
- [ ] Existing behavior is preserved: MCP servers still launch and function, the
      test suite passes, and the ruff lint/format gate passes.

## Stakeholders

- **Project maintainer / security owner** — wants the agent's full action surface
  (not just MCP) under one enforced, auditable boundary, and wants the riskiest
  refactor validated in isolation.
- **Mission 15 (Native Desktop Installers)** — consumes this mission's seam to add
  macOS and Windows backends behind it without re-plumbing.
- **End users** — benefit from built-in tools being sandboxed, closing a gap that
  exists in the product today.

## Constraints

- **The boundary lives at the shared tool-execution layer, not the web request
  path** — so the CLI is sandboxed by the same boundary and cannot bypass it.
  Placing it on the web path would make the CLI a trivial unsandboxed escape.
  (Validated: the CLI and web app both reach the same `run_shell` /
  `run_python` / `create_pty_session` helpers via `AgentFactory` →
  `BuiltinToolProvider`, so the platform layer is the correct single chokepoint.)
- **Backend selection needs a factory, not just a guard.** No backend-selection
  point exists today (`BubblewrapSandbox()` is constructed directly at the one MCP
  call site). Flight 1 must introduce a factory that picks the bubblewrap backend
  on Linux where `bwrap` is present and a passthrough backend everywhere else.
- **No deployment or distribution change.** This mission ships on the current
  setup (Docker or host). Retiring Docker, native packaging, installers, and
  host-native sandbox validation belong to Mission 15.
- **Preserve and extend the existing `SandboxProfile` model.** Profile fields that
  a given backend cannot honor (e.g., Linux-namespace fields like `pid_unshare`
  have no passthrough/Seatbelt equivalent) must be silently ignored by that
  backend, never error — so Mission 15's macOS backend slots in without a breaking
  profile change.
- **No new external runtime requirement for built-in tools.** The shell/Python/PTY
  tools must not gain a new mandatory dependency to be sandboxed on Linux beyond
  what the project already uses (`bwrap`).
- **Planning produces documentation only.** Implementation happens via
  `/agentic-workflow`; this mission's planning artifacts never modify source.
- **Do not regress existing MCP sandboxing.**

## Environment Requirements

- **Development / test**: the project's current environment (Python 3.11+; the
  Linux sandbox backend exercised wherever bubblewrap is already available — the
  Docker deployment grants the necessary user-namespace capability today). No new
  platform is targeted by this mission.
- **Runtime**: unchanged from today. Linux enforcement requires a `bwrap` binary
  and unprivileged user namespaces (already satisfied in the current deployment).

## Open Questions

- [ ] **Seam API shape**: a single `spawn_sandboxed(cmd, policy)` function, or a
      small sandbox-context object the spawn sites acquire? Resolve in the first
      flight's design.
- [ ] **PTY composition**: how the boundary wraps a `pty.fork()` child that calls
      `execvp` (`platform/pty.py`) — wrap the child-side exec in the backend, or
      restructure the session. This is the heaviest design question.
- [ ] **Linux backend strategy**: generalize the existing `BubblewrapSandbox` to
      cover built-in tools, or adopt `sandbox-runtime` now? (Leaning: generalize
      existing; defer `sandbox-runtime` adoption to M15 when macOS needs it — but
      confirm during design.)
- [ ] **Passthrough semantics**: how loudly the unsandboxed state is surfaced
      (startup log, per-spawn debug, an operator-visible indicator).
- [ ] **Writable-path policy for built-in tools** *(most concrete leg-design
      question)*: bubblewrap mounts `--ro-bind / /` by default, so a tool's
      validated `cwd` must be added to the policy's writable paths automatically —
      otherwise `run_shell("… > out.txt", cwd=…)` silently fails to write. Decide
      whether the seam injects `cwd` into `writable_paths` at spawn time or the
      policy is fully caller-supplied.
- [ ] **`run_shell` shell-string vs exec**: `run_shell` uses
      `create_subprocess_shell` (OS-chosen `/bin/sh`) today; under bwrap it must
      become `create_subprocess_exec(bwrap, …, "--", <shell>, "-c", cmd)` with an
      explicit shell. This is a (small) behavioral change — confirm the intended
      shell resolution in Flight 1.
- [ ] **Naming**: rename `MCPSandbox` / `MCPSandboxError` to drop the now-misleading
      `MCP` prefix (the abstraction is platform-wide), or keep as-is for lower
      churn? Decide before Flight 1 legs are drafted to avoid mid-flight scope creep.
- [ ] **Process-group / session interaction**: `start_new_session=True` on the
      shell/python paths interacts with bwrap's `--unshare-pid`; reconcile the
      timeout-kill path (`killpg` vs `proc.kill`) in Flight 1's design.
- [ ] **Boxed-mode default direction** *(Flight 4)*: does isolation point
      opt-in-to-box (host-workspace default, agent adds a "box this" flag) or
      box-by-default (agent must explicitly escalate "out of the box" for host
      access)? Leaning **box-by-default + explicit escalation** — concrete decision
      for the model, least-privilege default. Note: Flight 1 ships host-workspace as
      the single mode (no selection surface yet); Flight 4 introduces the box and
      may flip the experienced default. Also decide the boxed-workspace lifecycle
      (ephemeral per-call vs per-session vs per-agent; investigate the repo's
      `workspace/` dir as the scratch location).

## Known Issues

### Host-crash PTY-orphan window — MITIGATED

**Summary**: when the Python process is killed without calling `session.close()`, bwrap-wrapped
PTY grandchild processes (e.g. a backgrounded `sleep 30` inside the shell) could in principle
be orphaned if bwrap's own parent-death signal is not firing.

**Finding**: the orphan window does **not exist** in practice. bwrap's `--die-with-parent` flag
calls `prctl(PR_SET_PDEATHSIG, SIGKILL)` tied to the Python parent process at bwrap startup.
When the Python process is killed, bwrap-outer receives SIGKILL within ~300ms (verified empirically,
bwrap 0.9.0). bwrap's own PID-namespace teardown then reaps the entire namespace, including
`setsid`'d grandchildren.

**Additional defense**: `UnixPtySession.start()` also calls `prctl(PR_SET_PDEATHSIG, SIGKILL)` in
the fork child immediately before `execvp("bwrap", ...)` — this closes the microsecond startup race
window before bwrap registers its own handler. Safe because `/bin/bwrap` is not setuid/setcap on
this host (pdeathsig is cleared on execve only for setuid/setcap executables).

**Locked by**: `tests/test_pty_sandbox.py::test_pty_app_crash_reaps_grandchild`
(`@requires_bwrap`) — proves that killing the driver process (bwrap's direct parent) without
calling `session.close()` reaps the grandchild PID within ~1s. The test first probes that
`/bin/bwrap` is not setuid/setcap so a passing reap is not silently attributable to pdeathsig
being cleared.

**Resolution**: F3 L3 (`debt-and-docs`). Status: **mitigated**.

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned
> and created one at a time as work progresses.

- [x] Flight 1: **Seam + built-in tool retrofit** — create the shared sandboxing
      boundary; route the shell tool, Python interpreter tool, and the existing MCP
      stdio path through it; add a passthrough/null backend + selection factory so
      non-Linux runs through the seam without erroring at construction. Built-in
      tools default to a **host-workspace** profile (writable = filesystem allowlist,
      denylist protected, network opt-in, real `$HOME`). Containment verified via
      `@requires_bwrap` integration tests.
- [x] Flight 2: **PTY through the seam** — retrofit the `pty.fork()`/`execvp` path
      so interactive sessions are sandboxed by the same boundary on Linux.
      Behavior-test PTY-session containment. *(Heaviest flight.)* — **landed
      2026-06-07**; single-path seam, single-pid SIGKILL teardown; 12 `@requires_bwrap`
      tests + live behavior test (6/7 PASS); PR #104.
- [x] Flight 3: **Uniform policy & CLI parity** — ensure the `SandboxProfile`
      applies uniformly across all four spawn types from one policy source; verify a
      CLI-launched tool is sandboxed identically to the web path; consolidate the
      containment / escape-attempt behavior-test suite. — **landed 2026-06-07**;
      CLI-parity `@requires_bwrap` test + unified `tool-sandbox-containment` behavior
      test (6/6 live) + `_sandbox_fixtures.py` consolidation + seam-hardening regression
      test (host-crash orphan window proven mitigated) + debt/docs cleared.
- [ ] Flight 4: **Agent-selectable execution isolation (boxed mode)** — layer a
      runtime isolation choice on top of the seam so the agent can run untrusted /
      self-generated code in a **disposable box** (no host FS/network, scratch
      workspace) distinct from host-workspace execution. Scope: the selection
      surface, the boxed-workspace lifecycle (the hard part — persistence across
      multi-step calls), model guidance, and behavior-test verification of the
      agent's selection decisions. **Leading design direction** (see Open
      Questions): a single `shell`/`python` tool that is **boxed by default** with
      an explicit optional param to *escalate out* of the box (request host access),
      rather than separate `shell`/`shell_boxed` tools — because "do I need the
      user's real files/network?" is a more concrete decision for the model than
      "is this risky enough to box?", and box-by-default is least-privilege /
      leakage-safe. Depends on Flight 1's seam + the clean profile-derivation hook.
- [ ] Flight 5 *(optional)*: **Alignment** — hands-on review of sandbox behavior and
      policy ergonomics, with judgment-call adjustments that benefit from human
      feedback.
