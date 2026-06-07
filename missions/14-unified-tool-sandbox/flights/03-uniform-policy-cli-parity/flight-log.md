# Flight Log: Uniform Policy, CLI Parity & Seam Hardening

**Flight**: [Uniform Policy, CLI Parity & Seam Hardening](flight.md)

## Summary

Flight **landed 2026-06-07**. All 4 core legs completed (`cli-parity`,
`containment-behavior-suite`, `debt-and-docs`, `verify-integration`); optional
`uat-and-alignment` HAT skipped (operator: no UI changed). Verification: 14/14
`@requires_bwrap`, 3015 default-suite passed (0 regressions), ruff clean, and the live
`tool-sandbox-containment` behavior test 6/6 PASS. Sources carry-forwards from the
Flight 1 & 2 debriefs. The Reconnaissance Report below classifies every cited item
against `main` (`ddef8bb`, post-Flight-2 merge); operator scope decisions are folded
into the flight's Design Decisions.

---

## Reconnaissance Report

Walked each cited debt/follow-up from the Flight-2 debrief (top-5 recs + action
items) and the still-open Flight-1 action items against current `main`.

| Item | Classification | Evidence | Recommendation / disposition |
|---|---|---|---|
| `profile: object | None` typing | confirmed-live | `pty.py:170,558` (`# SandboxProfile | None (avoid import…)`) | **In scope** — `seam-hardening` leg (TYPE_CHECKING fix) |
| `SandboxError` relocation / import-cycle inversion | confirmed-live | `mcp/errors.py:37` (`class SandboxError(MCPClientError)`); `client.py:511 except MCPClientError` + the `:499` comment naming SandboxError; 4 function-level imports (`pty.py:212`, `interpreter.py:110`, `execution.py:451`, `shell.py:123`) | **Deferred** to end-of-mission maintenance (operator decision, DD1) — entangled dependency inversion, not a move |
| `factory.py` stale docstring | confirmed-live | `factory.py:61` ("until leg 3 reconciles both to this factory") | **In scope** — `debt-and-docs` |
| `bubblewrap.py` stale error message | confirmed-live | `bubblewrap.py:69` ("MCP sandbox setup failed…") — now platform-wide incl. PTY | **In scope** — `debt-and-docs` |
| `--ro-bind-try` doc in `SECURITY-MODEL.md` | **partially-satisfied** | `SECURITY-MODEL.md:81` documents the `--ro-bind-try` *mechanism* (read-only bind) but NOT the **silent-skip-of-absent-paths** caveat (the fixture footgun) | **Scope down** — add only the silent-skip caveat (`debt-and-docs`) |
| CLI sandboxed identically to web | confirmed-live (needs verification + test) | CLI `interfaces/cli.py:38` and web `interfaces/web/app.py:97` both `AgentFactory(store=store)` — shared path, no parity test exists | **In scope** — `cli-parity` leg |
| Host-crash PTY-orphan window | **already-mitigated** (revised at design review) | Architect empirically verified (bwrap 0.9.0): bwrap's own `--die-with-parent` calls `prctl(PR_SET_PDEATHSIG, SIGKILL)` tied to its parent = the Python process, so bwrap-outer dies ~300ms after an app crash. The F2-debrief premise ("bwrap-outer not tied to the app") was wrong. | **Reframed** (DD4): the window is a non-issue; `seam-hardening` adds a regression test locking the invariant + optional cheap pre-exec pdeathsig defense-in-depth. Mission known-issue → mitigated. |
| Footgun docs (teardown-dispatch, PTY-echo, workspace-under-$HOME) | confirmed-live | only in code/test comments (`pty.py` teardown comment; `test_pty_sandbox.py` docstring) | **In scope** — `debt-and-docs` |
| Agent-safe-observable rule → AUTHORING.md | confirmed-live (cross-repo) | mission-control `.claude/skills/behavior-test/AUTHORING.md` — not a the-one artifact | **Out of scope here** (cross-repo follow-up, DD6); the rule is *applied* on the the-one side via DD3 |
| Read-scoping ("cannot read outside scope") | confirmed-live (unmet mission criterion) | deferred since Flight 1 DD5; needs `ldd`/overlayfs | **Out of scope** — its own future flight; carried as mission known-issue |

**Operator scope decisions** (recorded in flight DD1/DD3/DD4): SandboxError relocation
deferred; host-crash hardening included; one unified containment behavior test. No
items were silently dropped — deferred items are retained with disposition above.

---

## Design Review (Phase 5b)

**Architect verdict**: *approve with changes* (1 cycle), with **empirical verification**
of the load-bearing DD4 claim. Changes incorporated:
- **[high] DD4 rationale was factually wrong** — the host-crash orphan window the F2
  debrief feared does not exist: bwrap's own `--die-with-parent` already
  `prctl(PR_SET_PDEATHSIG, SIGKILL)`-ties bwrap-outer to the Python parent (verified,
  ~300ms reap). DD4 reframed: `seam-hardening` now locks the invariant with a
  regression test + optional cheap pre-exec pdeathsig defense-in-depth (must probe
  `/bin/bwrap` is not setuid/setcap, else pdeathsig clears on `execve`). Mission
  known-issue → mitigated.
- **[medium] DD2 profile-equality was tautological** — CLI and web both use the same
  `AgentFactory(store=store)` → same `_build_tool_profile` inputs. Reframed: the
  CLI-parity test asserts (a) real containment under bwrap via the `AgentFactory` path
  and (b) the factory wires a non-empty `FilesystemConfig` — not profile-equality.
- **[medium] DD3 MCP consolidation overstated** — `test_mcp_sandbox_integration.py`
  uses `/var/tmp` + its own fixture + drives `MCPClient`; scoped the
  `_sandbox_fixtures.py` consolidation to `test_builtin_tool_sandbox.py` +
  `test_pty_sandbox.py`, assess-only for MCP.
- **Suggestions folded:** probe bwrap-not-setuid in the hardening test; behavior-spec
  step 6 captures the bwrap PID right after step 5 (avoids the close-vs-capture race);
  `factory.py:61` docstring → note the MCP copy is intentionally preserved (relocation
  deferred), not pending.

Second review cycle **skipped**: changes are faithful applications of the architect's
own findings (rationale corrections, assertion reframes, scope-downs), not new
architecture.

## Leg Progress

_Implementation entries are appended by the Developer crew per leg._

### Leg 01 — cli-parity (landed 2026-06-07)

**Status**: landed

**What was built**: `tests/test_cli_sandbox_parity.py` — two test functions:

- `test_factory_path_wires_real_filesystem_config` (no bwrap): assertion (b) — builds a
  `ShellTool` via `BuiltinToolProvider().get_tools(tool_configs_by_name, {}, agent_name="default")`
  with a `"read_file"`-keyed `FilesystemConfig` carrying a distinctive workspace path under
  `$HOME`, then asserts `shell_tool._cross_configs[FilesystemConfig].path_allowlist` contains
  that distinctive path (not the default `["~"]`).

- `test_write_outside_allowlist_contained_via_factory_path` (`@requires_bwrap`): assertion (a) —
  creates the workspace dir under `$HOME` as `cwd`, then invokes `execute()` to write a file into
  a sibling dir not in the allowlist, and asserts the host file does not exist afterward (real
  containment proof via bwrap; does not parse error text).

The load-bearing detail was honored: `FilesystemConfig` fields are keyed under `"read_file"` (the
first `_TOOL_CLASSES` entry whose `Config IS FilesystemConfig`), not under `"shell"` (whose
`Config` is `ExecutionConfig` — keying there would route the fields into `ExecutionConfig`,
silently drop them, and leave the shared cross-config at the default `["~"]` — a vacuous pass for
assertion (b)).

**Test results**:
- `pytest tests/test_cli_sandbox_parity.py -x --timeout 60` (non-bwrap only): 1 passed, 1 deselected
- `pytest tests/test_cli_sandbox_parity.py -x --timeout 60 -m requires_bwrap`: 1 passed, 1 deselected
- `ruff check` + `ruff format --check`: all checks passed

**No production source files modified.**

**Deviations**: none.

---

### Leg 02 — containment-behavior-suite (landed 2026-06-07)

**Status**: landed

**What was extracted**:

- `tests/_sandbox_fixtures.py` (new) — four shared helpers:
  - `sleep_pids()` — module-level, matching the PTY copy's form (verbatim `pgrep -f "sleep 30"`).
  - `home_workspace(suffix)` — `@contextmanager`; creates `~/.the-one-test-{suffix}`, yields the
    `Path`, `shutil.rmtree(ignore_errors=True)` on exit.
  - `loopback_server()` — `@contextmanager`; binds `127.0.0.1:0`, starts a daemon accept-thread
    sending `b"hello"`, yields the port, sets the stop event + closes socket + joins thread on exit.
    Wraps only the server — not the workspace cleanup.
  - `make_denylist_secret(workspace)` — creates `workspace/secret/key` = `"original-content"`,
    returns `(secret_dir, secret_file)`. Canonical `--ro-bind-try` footgun warning in the
    docstring: the dir MUST pre-exist before bwrap launch or the silent-skip false-passes.

- `test_builtin_tool_sandbox.py` refactored: inline `_sleep_pids` inner function removed (replaced
  by import + call); loopback TCP server block removed (replaced by `with loopback_server()`);
  per-test `workspace.mkdir` / `shutil.rmtree` blocks removed (replaced by `with home_workspace()`);
  `make_denylist_secret` used in denylist test. Two-dir test (`allowlist-denied` + `allowlist-sibling`)
  nests two `home_workspace` CMs. `monkeypatch.delenv` stays inline.

- `test_pty_sandbox.py` refactored: module-level `_sleep_pids` function removed (replaced by
  import); loopback TCP server block removed (replaced by `with loopback_server()`); per-test
  `workspace.mkdir` / `shutil.rmtree` blocks removed (replaced by `with home_workspace()`);
  `make_denylist_secret` used in denylist test. Two-dir test nests two `home_workspace` CMs.
  `"con"+"nected"` echo-avoidance trick preserved verbatim. `monkeypatch.delenv` stays inline.

**MCP test assessment**: `test_mcp_sandbox_integration.py` left unchanged. Confirmed it uses
`/var/tmp` + `writable_scratch_dir` pytest fixture + `MCPClient` driven subprocess + external DNS
probe (`8.8.8.8:53`). No loopback server, no `$HOME`-shaped workspace. None of the four extracted
helpers apply. Decision: assess-only, no change.

**Behavior spec verification**: `tests/behavior/tool-sandbox-containment.md` — Steps table present
(6 rows, agent-safe observables throughout), status `draft` (unchanged), Out of Scope section
references `tests/test_cli_sandbox_parity.py` which now exists (created in Leg 01). Spec is
coherent. No content change made.

**Test results**:
- `pytest tests/test_builtin_tool_sandbox.py tests/test_pty_sandbox.py -m requires_bwrap --timeout 120`: **10 passed** (5 + 5)
- `pytest tests/test_builtin_tool_sandbox.py tests/test_pty_sandbox.py -m "not requires_bwrap" --timeout 60`: 10 deselected, no errors (clean deselect)
- `pytest tests/test_mcp_sandbox_integration.py --timeout 120`: 10 passed, 3 skipped (pre-existing skips for F6-A5-deadlock tests + EPERM/SYS_ADMIN gate); no collateral
- `ruff check tests/` + `ruff format --check` on touched files: all checks passed

**Boilerplate grep** (`_sleep_pids|SO_REUSEADDR|workspace.mkdir|shutil.rmtree` in the two test
files): no matches — all extracted patterns removed from call sites; only import + call sites remain.

**No production source files modified.**

**Deviations**: CM-based cleanup in the PTY orphan test incidentally hardens teardown (the
`finally` now covers session close via the `home_workspace` CM even if `session.start()` throws).
This is an acceptable improvement per the leg spec — no assertion changes.

---

## Flight Director Notes

- **Orchestration start (2026-06-07)** — `/agentic-workflow flight 3, mission 14,
  the-one`. Loaded `leg-execution.md` crew (Developer=Sonnet, Reviewer=Haiku;
  structure valid). Flight `ready` → `in-flight`. Branch
  `flight/03-uniform-policy-cli-parity` cut from `main@c2253aa`. Batched-commit model:
  legs designed + implemented per-leg (design reviewed), single code review + commit
  after the last autonomous leg. Four core legs + optional HAT.
- **Recon finding (pre-design)** — `tests/behavior/tool-sandbox-containment.md` is
  **already authored** (status `draft`, committed in the plan commit). So
  `containment-behavior-suite`'s spec-authoring is satisfied at planning; that leg's
  live work is the `_sandbox_fixtures.py` consolidation. Mission Known Issues is empty
  ("None yet") — `debt-and-docs` will *add* the host-crash-orphan-mitigated record
  rather than flip an existing one. bwrap 0.9.0 present, `/bin/bwrap` not setuid/setcap
  (pdeathsig survives `execvp`).
- **Leg 01 `cli-parity` design review (1 cycle, approve-with-changes)** — Developer
  (Sonnet) found a load-bearing trap: the shared `FilesystemConfig` cross-config is
  resolved from the **first** `_TOOL_CLASSES` tool whose `Config` is `FilesystemConfig`
  = `read_file` (not `shell`, whose `Config` is `ExecutionConfig`). Keying the test
  config under `"shell"` would route the keys into `ExecutionConfig` (dropped) and pass
  assertion (b) vacuously on the default `["~"]`. Corrections incorporated: key under
  `"read_file"`; assert via `shell_tool._cross_configs[FilesystemConfig].path_allowlist`;
  workspace `cwd` must exist + be in-allowlist before `execute()`; `@requires_bwrap`
  marker already registered (`pyproject.toml:11`) so no conftest change; (b) is
  bwrap-free and may be its own test fn. Second cycle **skipped** — changes are faithful
  applications of the reviewer's own evidence, not new architecture (Flight-2 precedent).
  Leg → `ready`.
- **Leg 02 `containment-behavior-suite` design review (1 cycle, approve-with-changes)** —
  Developer (Sonnet) confirmed the duplicated-pattern citations and the assess-only MCP
  call (`test_mcp_sandbox_integration.py` probes external DNS `8.8.8.8:53`, no loopback
  server, `/var/tmp` + `MCPClient` shape — nothing shared to pull). Medium clarifications
  incorporated: `_sleep_pids` extract as module-level (PTY form), builtin inline def
  replaced by import; the loopback-CM wraps only socket+thread (the co-located
  `shutil.rmtree` belongs to the workspace CM); the two-dir allowlist tests
  (workspace+sibling) nest two `home_workspace` CMs or keep sibling inline; canonical
  `--ro-bind-try` footgun docstring lives on `make_denylist_secret`; narrowed the
  no-duplication grep (drop the suffix string, which legitimately persists as a CM arg);
  CM-based cleanup may incidentally harden teardown as long as no assertion changes.
  Confirmed: conftest has no autouse fixture touching `THE_ONE_SANDBOX_DISABLED`, so
  `monkeypatch.delenv` stays at call sites; leading-underscore module is not collected.
  Second cycle **skipped** — clarifications, not new architecture. Leg → `ready`.
- **Leg 03 `debt-and-docs` design review (1 cycle, approve-with-changes)** — Developer
  (Sonnet) scrutinized the production-code items. One **high** + three **medium** folded
  in: (high) the optional pre-`execvp` pdeathsig must NOT `import ctypes`/`dlopen` in the
  post-fork child (deadlock risk per the module's DD1 fork-safety rule) — load libc in the
  **parent before `pty.fork()`**, child only calls the preloaded `libc.prctl`; (med) the
  bwrap-not-setuid/setcap probe must use stdlib `os.getxattr(..., "security.capability")`,
  NOT `getcap` (absent in the container); (med) the `bubblewrap.py` message change breaks
  `test_sandbox_bubblewrap.py`'s verbatim `_BWRAP_NOT_FOUND_MSG` lock — added an AC to
  update that test + docstring; (med) the verification grep narrowed to
  `the_one/platform/` since the three "MCP sandbox setup failed" strings in
  `mcp/transports/stdio.py` are intentionally MCP-scoped and stay; (low) the driver
  subprocess needs an explicit `asyncio.run(main())` wrapper (no top-level await).
  Confirmed safe: TYPE_CHECKING import for `SandboxProfile` (no pydantic/dataclass/
  get_type_hints on these classes; `from __future__ import annotations` present); the
  crash test is meaningfully distinct from the existing close test; pdeathsig doesn't
  interfere with the close path. Second cycle **skipped** — every change is the reviewer's
  own concrete fix; the implementing Developer exercises the code and the optional
  pdeathsig is droppable per the Divert criterion. Leg → `ready`.
- **Leg 04 `verify-integration` — verification leg, no design review.** Run directly by the
  Flight Director (running test matrix + driving the behavior-test crew is not code
  implementation, so a design-review agent adds no value). Hermetic matrix delegated to a
  background Developer (read-only): GO — 14/14 bwrap, 3015 default-suite passed, 0
  regressions (5 failures all pre-existing infra/live-LLM), ruff clean after one cosmetic
  format fix.
- **Live behavior-test apparatus + operator gate.** The running instance (port 8484) had an
  Anthropic provider but no execution-tools agent. Operator chose "Configure + run now"
  (AskUserQuestion). A Developer stood up agent `sandbox-test` (Sonnet 4.6, shell +
  python_exec + shell_session_* at default policy) + the `~/.ssh/id_test` denylist fixture
  inside the container, and smoke-proved end-to-end containment before the formal run. The
  Flight Director then ran `/behavior-test tool-sandbox-containment` → **6/6 PASS** (Witnessed,
  re-spawn mode; two Executor batches [steps 1–4, 5–6] each judged by an independent Validator
  — batching documented in the run log's Orchestrator Notes).
- **Optional HAT (`uat-and-alignment`) SKIPPED — operator decision.** Operator: "I don't think
  anything changed in the UI, right? If not, the automated tests are fine." Confirmed: this
  flight touched only tests, `pty.py` (PTY teardown/typing), sandbox factory/bubblewrap
  messages, docs, and the mission artifact — **no frontend/UI changes**. HAT skipped; the
  `@requires_bwrap` suite + the live behavior test cover acceptance.

---

### Leg 03 — debt-and-docs (landed 2026-06-07)

**Status**: landed

**What was built** (all 5 sub-items completed):

1. **Invariant regression test** (`test_pty_app_crash_reaps_grandchild` in `tests/test_pty_sandbox.py`):
   - Probes `/bin/bwrap` with stdlib-only checks: `os.stat` S_ISUID + `os.getxattr("security.capability")`;
     `ENODATA`/`ENOTSUP` ⇒ no caps ⇒ proceed; skips otherwise.
   - Launches a driver subprocess via `subprocess.Popen`, waits for `READY` line, captures pre-test
     baseline PIDs before driver starts, confirms new `sleep 30` PID captured, SIGKILLs driver
     (without calling `session.close()`), waits ~1s, asserts grandchild gone.
   - Reuses `sleep_pids`, `home_workspace` from `tests/_sandbox_fixtures.py`;
     `monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)`.
   - Honest docstring: proves the invariant (tree reaped on parent death), does not attribute to
     our code vs bwrap's `--die-with-parent`; regression guard only.

2. **Optional pdeathsig — INCLUDED** (rationale: host bwrap confirmed not setuid/setcap; cost
   is trivial, closes the microsecond startup race window before bwrap registers its own handler):
   - `import ctypes` added at module level; `libc = ctypes.CDLL("libc.so.6", use_errno=True)` and
     `_pr_set_pdeathsig = 1` loaded in the **parent before `pty.fork()`** (fork-safety per DD1).
   - Child calls `_libc.prctl(_pr_set_pdeathsig, signal.SIGKILL)` immediately before `os.execvp`.
   - Honest comment in code explaining primary coverage is bwrap's `--die-with-parent`; this is
     defense-in-depth only.

3. **Typing fix**: `TYPE_CHECKING` block added to `the_one/platform/pty.py` importing `SandboxProfile`
   from `the_one.platform.sandbox.base`. Both `profile: object | None` annotations at `pty.py:170`
   and `pty.py:558` changed to `profile: SandboxProfile | None`; stale comments removed.

4. **Doc/message debts**:
   - `factory.py`: `_sandbox_disabled_for_tests` docstring updated — "until leg 3 reconciles" →
     "intentionally preserved for the import-cycle workaround (deferred to maintenance)".
   - `bubblewrap.py`: `__init__` error message → "sandbox setup failed: …" (dropped "MCP" prefix);
     the 3 MCP-scoped messages in `mcp/transports/stdio.py` preserved as designed.
   - `tests/test_sandbox_bubblewrap.py`: `_BWRAP_NOT_FOUND_MSG` constant and test docstring updated
     to new platform-neutral text; all 20 bubblewrap tests pass.
   - `SECURITY-MODEL.md`: `--ro-bind-try` silent-skip-of-absent-paths caveat added (~:81 area).
   - `the_one/agents.md`: "Sandbox testing footguns" subsection added in Testing patterns section
     (3 footguns: teardown-dispatch, PTY-echo sentinel, workspace-under-$HOME).
   - `CLAUDE.md`: "Sandbox testing footguns" summary block added in Testing section, pointing to
     `agents.md` for full documentation.

5. **Mission known-issue**: `missions/14-unified-tool-sandbox/mission.md` Known Issues section
   updated — replaced "None yet" with documented entry: host-crash PTY-orphan window investigated
   and found mitigated by bwrap's `--die-with-parent` (~300ms reap, bwrap 0.9.0), locked by
   regression test `test_pty_app_crash_reaps_grandchild`. Status: mitigated.

**Test results**:
- `pytest tests/test_pty_sandbox.py -m requires_bwrap --timeout 120`: **6 passed** (incl. new test)
- `pytest tests/test_sandbox_bubblewrap.py --timeout 60`: **20 passed**
- `pytest --timeout 60 -m "not requires_bwrap" -q`: 3015 passed, 52 skipped (pre-existing failures:
  Playwright Chromium not installed + 4 AIAT live LLM tests — confirmed pre-existing by `git stash` verification)
- `ruff check the_one/ tests/`: all checks passed
- `ruff format --check the_one/platform/pty.py`: already formatted

**Verification greps**:
- `grep "object | None" the_one/platform/pty.py`: no matches (both annotations replaced) ✓
- `grep "MCP sandbox setup failed" the_one/platform/`: no matches ✓
- `grep "until leg 3 reconciles" the_one/`: no matches ✓

**Optional pdeathsig**: INCLUDED (see rationale in sub-item 2 above).

**Deviations**: none.

---

### Leg 04 — verify-integration (landed 2026-06-07)

**Status**: landed (Flight-Director-driven verification leg; no Developer-implemented code)

**Hermetic matrix** (over the accumulated legs 01–03 diff, run in the `the-one` container):
- `-m requires_bwrap`: **14 passed / 0 failed** (built-in + PTY + MCP + CLI-parity + the new
  app-crash regression test).
- Full default suite (`-m "not requires_bwrap"`): **3015 passed**, 5 failed / 486 errored —
  **all confirmed PRE-EXISTING** (486 errors = Playwright/Chromium not installed in the image;
  4 failures = live-LLM AIAT tests; 1 = Playwright smoke). **0 flight-introduced regressions.**
- CLI parity (`test_cli_sandbox_parity.py`): both assertions green.
- Passthrough no-error (`test_sandbox_factory.py` + `test_sandbox_contract.py`): **27 passed** —
  factory selects passthrough cleanly, no construction error.
- `ruff check` clean; `ruff format --check` clean after fixing one cosmetic nit in
  `tests/test_pty_sandbox.py` (`ruff format` applied; host file is bind-mounted).
- Host-native run not performed (no host venv) — container run is authoritative; honest caveat:
  no pytest CI yet.

**Live behavior test** — `/behavior-test tool-sandbox-containment` (operator-approved): **6/6
checkpoints PASS** (Witnessed pattern, re-spawn-per-checkpoint mode — `SendMessage` unavailable).
Run log: `tests/behavior/tool-sandbox-containment/runs/2026-06-07-15-29-51.md`. All checkpoints
agent-safe (result-state observables, no exploit-and-read-error). Spec promoted `draft` →
`active`. Apparatus: agent `sandbox-test` (Sonnet 4.6) with shell/python_exec/shell_session_*
at default sandbox policy; observed container-side via `docker exec the-one` (the agent's tools
spawn under bwrap inside the container, `$HOME=/root`); denylist fixture `/root/.ssh/id_test`.

**Deviations**: verification leg run directly by the Flight Director (not a Developer agent) —
its work is running the matrix + driving the behavior-test crew, not implementing code. The live
behavior-test apparatus (agent `sandbox-test`, `~/.ssh/id_test` fixture) was created on the
running instance and left in place for re-runnability; transient canary files removed.

---

## Decisions

_Runtime decisions not in the original plan will be recorded here._

---

## Deviations

_Departures from the planned approach will be recorded here._

---

## Anomalies

_Unexpected issues will be recorded here._

---

## Session Notes

- **Debrief (2026-06-07)**: Flight debriefed (`flight-debrief.md`) — Developer + Architect
  interviews + test-metrics capture. Outcome: objective achieved, all checkpoints met, 0
  regressions. Top finding: the optional pdeathsig made `ctypes.CDLL("libc.so.6")`
  unconditional in `start()` with no macOS guard — a latent non-Linux regression.
  **Fixed post-debrief** (operator-approved): `pty.py` libc load now gated on
  `sys.platform == "linux"` via a module-level lazy `_get_libc()` singleton (loaded in the
  parent, child uses the inherited handle; child-side prctl skipped + return intentionally
  unchecked off-Linux). bwrap arm still 6/6 green; ruff clean. Flight status `landed` →
  `completed`. Remaining action items (agents.md cross-config note, fork-safety convention,
  DD6 cross-repo AUTHORING.md rule, DD1 SandboxError inversion → maintenance) carried in the
  debrief.
- **Planning (2026-06-07) — post-review**: After the DD4 finding (orphan window
  already mitigated by bwrap's `--die-with-parent`), operator folded the standalone
  `seam-hardening` leg into `debt-and-docs` — it shrank to a regression test + the
  typing fix + optional pdeathsig, not worth its own slot. Flight now 4 core legs
  (`cli-parity`, `containment-behavior-suite`, `debt-and-docs`, `verify-integration`)
  + optional HAT. Flight marked `ready`.
- **Planning (2026-06-07)**: Flight created from the Flight 1 & 2 debrief
  carry-forwards. Operator scope: defer SandboxError relocation (→ maintenance);
  include host-crash orphan hardening; one unified agent-safe containment behavior
  test + keep `@requires_bwrap` hermetic. Read-scoping flagged out of scope (its own
  flight). Recon run against `main@ddef8bb`.
