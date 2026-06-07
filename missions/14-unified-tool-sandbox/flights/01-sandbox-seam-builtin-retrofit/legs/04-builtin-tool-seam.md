# Leg: builtin-tool-seam

**Status**: completed
**Flight**: [Sandbox Seam + Built-in Tool Retrofit](../flight.md)

## Objective

Route the two built-in execution tools (`ShellTool`, `PythonExecTool`) through the
shared sandbox seam: add a shared `_build_tool_profile(fs_cfg, exec_cfg)` deriving a
**host-workspace** `SandboxProfile` (writable = filesystem allowlist; read-only
overlay = denylist; network from a new `ExecutionConfig.sandbox_network_allowed`;
real `$HOME`), thread an optional `profile` through `run_shell` / `run_python` so the
tool spawns go through `get_sandbox_backend().prepare_spawn(...)` +
`create_subprocess_exec` (ShellTool switching to `select_shell()` + exec per DD7),
pin the existing execution-tool unit tests to passthrough (DD9), and add
`@requires_bwrap` integration tests proving containment.

## Context

- **DD4 (flight):** built-in tools run a *host-workspace* profile — capable, with
  OS-enforced leakage prevention. `writable_paths` = the agent's `FilesystemConfig`
  allowlist; denylist enforced via the `readonly_overlay_paths` field (leg 2);
  `$HOME` = the real home (profile-driven HOME, leg 2).
- **DD6 (flight):** network deny-by-default, opt-in via a new
  `ExecutionConfig.sandbox_network_allowed: bool = False`. Migration-free (tool
  configs are a JSON blob validated `extra=ignore`).
- **DD7 (flight):** `run_shell` becomes an explicit `exec` under the wrapper —
  `select_shell()` (`(shell, ["-c"])`, honoring `$SHELL`) + `create_subprocess_exec`,
  replacing `create_subprocess_shell` *on the sandboxed path*. Behavior change:
  OS-chosen `/bin/sh` becomes `$SHELL`-honoring (falls back to `/bin/sh`).
- **DD10 (flight):** profile derivation is **one clean function**
  (`_build_tool_profile(fs_cfg, exec_cfg) → SandboxProfile`), shared by both tools —
  the hook Flight 4 (boxed mode) branches in.
- **DD9 (flight):** `tests/conftest.py` sets only `THE_ONE_TEST_MODE`, so once the
  tools route through the factory, `test_execution_tools.py` would silently run under
  bwrap in-container but passthrough on a bwrap-less host. Pin those unit tests to
  passthrough (`THE_ONE_SANDBOX_DISABLED=1`); add *new* `@requires_bwrap` tests for
  the real bwrap path.
- **DD11 (flight):** built-in-tool sandboxing is ON by default on Linux (gated only
  by backend availability); no enable/disable knob beyond the network field.
- **Prior legs:** Leg 2 produced `_build_tool_profile`'s building blocks
  (`readonly_overlay_paths`, `home`, the `--ro-bind` overlay, profile-driven HOME)
  and `get_sandbox_backend()`; Leg 3 wired MCP and established the
  `isinstance(backend, BubblewrapSandbox)` "is-it-wrapped" idiom.

### Flight-spec inconsistency resolved by the Flight Director (READ THIS)

The flight spec contradicts itself on what the denylist overlay does:
- **DD4** specifies `--ro-bind` and names the field `readonly_overlay_paths` —
  i.e. **read-only** (writes denied; the path stays *readable*). Its stated purpose
  is "prevent **accidental** leakage" (a tool clobbering / writing secrets).
- **DD5's parenthetical** ("the denylist overlay *does* block reads") and the
  flight's **Verification (b)** ("a denylisted secret path … is neither writable nor
  readable") claim the overlay blocks **reads**.

A `--ro-bind` (read-only bind) **cannot block reads** — the path remains readable
(and everything is readable anyway under DD5's `--ro-bind / /`). The two claims are
irreconcilable with the chosen mechanism.

**Resolution (Flight Director):** honor **DD4** — the overlay is read-only
(write-protection), matching the field name and leg-2's landed code. Read-blocking is
**not** delivered this flight (consistent with DD5's explicit read-scoping deferral).
The acceptance test asserts a denylisted secret is **not writable**; it does **not**
assert unreadable. DD5's "blocks reads" parenthetical and Verification (b)'s "nor
readable" overstate the mechanism and are treated as drafting errors. Recorded in the
flight log; leg 5 / flight Post-Flight verification must use the write-only wording.

## Inputs

What exists before this leg runs (post-leg-3, landed):
- `the_one/tools/shell.py` — `ShellTool.execute`: builds `exec_cfg`/`fs_cfg`, clips
  timeout, `_command_check`, `canonical_cwd = _cwd_check(cwd or str(Path.home()),
  fs_cfg)`, then `run_shell(command, timeout=…, env=_build_subprocess_env(),
  cwd=canonical_cwd)` (`shell.py:92`).
- `the_one/tools/python_exec.py` — `PythonExecTool.execute`: same shape, calls
  `run_python(code, timeout=…, env=_build_subprocess_env(), cwd=canonical_cwd)`
  (`python_exec.py:90`).
- `the_one/tools/execution.py` — `ExecutionConfig` (frozen Pydantic; fields are
  `Annotated[..., Narrow/NarrowSuperset, Field(...)]`), `PythonExecConfig`
  subclass, `_command_check`, `_cwd_check`, `_truncate_output`. `_build_subprocess_env`
  re-exported here from `platform/env.py`.
- `the_one/tools/filesystem.py` — `FilesystemConfig` (frozen): `path_allowlist`
  (default `["~"]`), `path_denylist` (default `DEFAULT_PATH_DENYLIST` — many entries
  are optional secret locations like `~/.aws`, `~/.kube` that **often don't exist**).
  Eager canonical caches `_canonical_allowlist: list[Path]` /
  `_canonical_denylist: list[Path]` (PrivateAttr, set in `model_post_init` via
  `canonicalize`).
- `the_one/platform/shell.py` — `select_shell() -> (shell, ["-c"])`;
  `run_shell(command, *, timeout, env=None, cwd=None)` using
  `create_subprocess_shell`; `_kill_process_tree` (killpg-then-proc.kill);
  `start_new_session=True` on POSIX.
- `the_one/platform/interpreter.py` — `resolve_python()`; `run_python(code, *,
  timeout, env=None, cwd=None)` using `create_subprocess_exec(python, "-c", code)`;
  same kill/session pattern.
- `the_one/platform/env.py` — `_ENV_ALLOWLIST` (includes `HOME`, `PATH`, `USER`, …);
  `_build_subprocess_env()` returns the allowlist keys present in `os.environ`.
- `the_one/platform/sandbox/` — `get_sandbox_backend()`, `BubblewrapSandbox`,
  `PassthroughSandbox`, `SandboxProfile` (with `writable_paths`,
  `readonly_overlay_paths`, `network_allowed`, `home`, the three `*_unshare` flags).
- Tests: `tests/test_execution_tools.py` (375 lines, the tool unit tests — assert
  output formatting, timeout messages, env, cwd, denylist); `tests/test_platform_shell.py`
  + `tests/test_platform_interpreter.py` (call `run_shell`/`run_python` **directly,
  with no profile** — must stay untouched); `tests/conftest.py` (sets
  `THE_ONE_TEST_MODE`, not `THE_ONE_SANDBOX_DISABLED`).

## Outputs

After this leg:
- `ExecutionConfig` gains `sandbox_network_allowed: Annotated[bool, Narrow] = False`
  (inherited by `PythonExecConfig`).
- `_build_tool_profile(fs_cfg, exec_cfg) -> SandboxProfile` in `tools/execution.py`.
- `run_shell` / `run_python` accept an optional keyword `profile: SandboxProfile |
  None = None`. `profile is None` → **unchanged legacy spawn** (keeps the platform
  tests and any raw caller working). `profile is not None` → seam path:
  `get_sandbox_backend().prepare_spawn(...)` + `create_subprocess_exec(spec)`, shell
  via `select_shell()`.
- `ShellTool` / `PythonExecTool` build the profile via `_build_tool_profile` and pass
  it to the platform helper (always — the factory decides passthrough vs bubblewrap).
- The bubblewrap overlay emits `--ro-bind-try` (not `--ro-bind`) so absent denylist
  paths don't crash the spawn (leg-2 code refined; leg-2 overlay test updated).
- `test_execution_tools.py` pinned to passthrough via an autouse fixture.
- New `tests/test_builtin_tool_sandbox.py` — `@requires_bwrap` containment tests.
- Full default suite + ruff green; `@requires_bwrap` built-in containment tests green.

## Acceptance Criteria

- [x] `ExecutionConfig.sandbox_network_allowed` exists (`bool`, default `False`,
      `Annotated[bool, Narrow]` with a description), inherited by `PythonExecConfig`.
      A tool config JSON blob lacking the key reads back `False` (migration-free).
- [x] `_build_tool_profile(fs_cfg, exec_cfg)` returns a `SandboxProfile` with:
      `writable_paths` = the canonical allowlist (`fs_cfg._canonical_allowlist` as
      str); `readonly_overlay_paths` = the canonical denylist; `network_allowed` =
      `exec_cfg.sandbox_network_allowed`; `home` = the real home (`str(Path.home())`);
      namespace flags at their `SandboxProfile` defaults. Shared by both tools (one
      definition, not inlined).
- [x] `run_shell` / `run_python` accept `profile: SandboxProfile | None = None`.
      With `profile is None`, behavior is byte-for-byte today's (platform tests
      unchanged). With a profile, they obtain `get_sandbox_backend()`, call
      `prepare_spawn`, and spawn the resulting `SpawnSpec` via
      `create_subprocess_exec`; `run_shell`'s sandboxed path uses `select_shell()`
      + exec (not `create_subprocess_shell`).
- [x] `ShellTool` and `PythonExecTool` pass `profile=_build_tool_profile(fs_cfg,
      exec_cfg)` to the platform helper on every call. No other behavior
      (timeout clipping, `_command_check`, `_cwd_check`, `_truncate_output`, the
      three-clause error envelope and its exact messages) changes.
- [x] The bubblewrap backend's overlay loop emits `--ro-bind-try PATH PATH` (so a
      non-existent denylist path is skipped, not fatal). Leg-2's overlay test updated
      to expect `--ro-bind-try`.
- [x] `tests/test_execution_tools.py` runs under passthrough deterministically (an
      autouse fixture sets `THE_ONE_SANDBOX_DISABLED=1`) and stays green — on a
      bwrap host *and* in-container.
- [x] `tests/test_platform_shell.py` and `tests/test_platform_interpreter.py` are
      unchanged and green (legacy no-profile path).
- [x] New `@requires_bwrap` tests in `tests/test_builtin_tool_sandbox.py` prove, for
      the real bwrap path (workspaces created **outside `/tmp`** — see Edge Cases):
      (a) a write outside the `FilesystemConfig` allowlist is denied; (b) a write to
      a denylisted secret path *under* a writable root is denied while a sibling
      allowlisted write succeeds (write-only per the resolution above); (c) network
      is denied by default and reachable when `sandbox_network_allowed=True`; (d) a
      `~`-relative write persists (real HOME, writable); (e) a timed-out command is
      killed promptly *and leaves no orphan* under bwrap.
- [x] Full default suite (`docker exec the-one pytest -x --timeout 30`) green;
      `docker exec the-one pytest -m requires_bwrap tests/test_builtin_tool_sandbox.py
      tests/test_sandbox_bubblewrap.py --timeout 60` green; `ruff check .` +
      `ruff format --check .` pass.

## Verification Steps

- `docker exec the-one pytest tests/test_execution_tools.py tests/test_platform_shell.py tests/test_platform_interpreter.py tests/test_sandbox_bubblewrap.py -x --timeout 30`
- `docker exec the-one pytest -m requires_bwrap tests/test_builtin_tool_sandbox.py tests/test_sandbox_bubblewrap.py --timeout 60`
- `docker exec the-one pytest -x --timeout 30` (full default suite).
- `ruff check . && ruff format --check .`.

## Implementation Guidance

1. **Add `sandbox_network_allowed`** to `ExecutionConfig` (`tools/execution.py`).
   Mirror the simple-bool pattern of `FilesystemConfig.allow_binary_files`:
   `sandbox_network_allowed: Annotated[bool, Narrow] = False` with a `Field(...)`
   description ("Allow the sandboxed tool subprocess network access (deny-by-default;
   the agent's dedicated web tools are unaffected)."). `PythonExecConfig` inherits it
   (don't re-declare — it has no per-field UI metadata to preserve).

2. **`_build_tool_profile(fs_cfg, exec_cfg) -> SandboxProfile`** in
   `tools/execution.py` (import `SandboxProfile` from `the_one.platform.sandbox`):
   ```
   return SandboxProfile(
       writable_paths=[str(p) for p in fs_cfg._canonical_allowlist],
       readonly_overlay_paths=[str(p) for p in fs_cfg._canonical_denylist],
       network_allowed=exec_cfg.sandbox_network_allowed,
       home=str(Path.home()),
   )
   ```
   - Use the **canonical** cached lists (already `expanduser`+`resolve`'d) — bwrap
     binds need real absolute paths. Accessing the `_canonical_*` PrivateAttrs from
     this same-package helper is acceptable; if you prefer, add trivial passthrough
     properties on `FilesystemConfig` (returning the cached list — O(1), NOT a
     recomputing `@computed_field`). Either is fine; don't recompute `canonicalize`.
   - `home` = `str(Path.home())`. This is the real home; the shell tool's default
     cwd is `$HOME` and `~`-relative writes must persist (DD4).
   - cwd is **not** separately injected into `writable_paths`: `_cwd_check` already
     constrains cwd to the allowlist, and the whole allowlist is writable, so cwd ⊆
     writable by construction. (Resolves the flight's "inject cwd?" open question:
     no injection needed.)

3. **Thread `profile` through the platform helpers.**
   - `run_shell(command, *, timeout, env=None, cwd=None, profile: SandboxProfile |
     None = None)`. Keep the existing legacy body for `profile is None`. For a
     non-None profile, take the seam path:
     ```
     # function-level import to avoid any platform↔platform.sandbox import cycle
     from the_one.platform.sandbox import BubblewrapSandbox, get_sandbox_backend
     shell_exe, prefix = select_shell()
     backend = get_sandbox_backend()
     spec = backend.prepare_spawn(profile, shell_exe, [*prefix, command],
                                  env or {}, str(cwd) if cwd is not None else None)
     # spawn spec.command + spec.args via create_subprocess_exec; same
     # start_new_session / timeout / kill+second-communicate lifecycle as today.
     proc = await asyncio.create_subprocess_exec(
         spec.command, *spec.args, stdout=PIPE, stderr=PIPE,
         env=spec.env, cwd=spec.cwd, **session_kwargs)
     ```
   - `run_python`: identical pattern, but the seam exe/args are
     `resolve_python(), ["-c", code]` → `prepare_spawn(profile, resolve_python(),
     ["-c", code], env or {}, …)`.
   - **Kill/timeout under bwrap (resolves the flight open question):** keep
     `start_new_session=True` and the **existing** `_kill_process_tree` (killpg →
     proc.kill fallback) for **both** paths. With bwrap as the group leader, the
     existing group-kill reaps the wrapped tree; `--die-with-parent` is the backstop.
     Do **not** add a separate bwrap-only kill branch unless the `@requires_bwrap`
     timeout test (criterion e) proves an orphan survives — in which case add an
     explicit SIGKILL of the bwrap pid. The test is the gate; prefer the no-change
     path. Factor the post-spawn `wait_for`/timeout/kill/second-`communicate` block
     into a small shared helper if it reads cleaner, but you may also duplicate it.
   - Update the module docstrings to describe the optional `profile` seam path.

4. **Wire the tools.** In `ShellTool.execute` and `PythonExecTool.execute`, after
   computing `fs_cfg`/`exec_cfg`/`canonical_cwd`, build
   `profile = _build_tool_profile(fs_cfg, exec_cfg)` and pass `profile=profile` to
   `run_shell` / `run_python`. Everything else (timeout clipping, the three-clause
   try/except with its exact messages) stays. Import `_build_tool_profile` from
   `tools.execution`.

5. **Overlay `--ro-bind` → `--ro-bind-try`** in
   `the_one/platform/sandbox/bubblewrap.py`. The denylist baseline contains optional
   secret locations that frequently don't exist (`~/.aws`, `~/.kube`, `~/.mozilla`,
   …); `--ro-bind` fails the whole spawn if the source path is missing, so the
   overlay loop must use `--ro-bind-try` (bind if present, else skip).
   - **Change ONLY the overlay loop's flag.** The base mount `--ro-bind / /` stays
     `--ro-bind` (it must exist). Update leg-2's overlay test
     (`test_sandbox_bubblewrap.py::test_prepare_spawn_readonly_overlay_after_writable_bind_before_proc`,
     ~lines 322–340): change the overlay-entry search token from `"--ro-bind"` to
     `"--ro-bind-try"`. Do **NOT** global-replace `--ro-bind` in the test file —
     `test_prepare_spawn_default_profile_argv_shape`'s `assert "--ro-bind" in a`
     (the base `--ro-bind / /` mount) must stay unchanged.
   - **Keep `--proc /proc` and `--dev /dev` AFTER the overlay loop.** `DEFAULT_PATH_DENYLIST`
     includes `/proc`, `/dev`, `/etc`, `/sys`, `/boot`, `/var/log`, so the overlay
     loop emits `--ro-bind-try /proc /proc` etc. Because `--proc /proc` and
     `--dev /dev` come *after* the overlay loop, they correctly replace the bind for
     those two (last-wins) and procfs/devfs work normally. `/etc`,`/sys`,`/boot`,`/var/log`
     get a harmless redundant read-only re-assertion (already ro under `--ro-bind / /`).
     Do not reorder `--proc`/`--dev` before the overlay loop.
   - (Writable `--bind` stays as-is — allowlist roots and the validated cwd exist;
     absent-path tolerance is only needed for the optional-secret denylist.)

6. **Pin `test_execution_tools.py` to passthrough.** Add an autouse, function-scoped
   fixture at the top of the file:
   ```
   @pytest.fixture(autouse=True)
   def _force_passthrough(monkeypatch):
       monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")  # TEST_MODE set by conftest
   ```
   This makes the factory return passthrough for every test in this file regardless
   of whether bwrap is present, so the tool unit tests assert today's unwrapped
   behavior deterministically (mirrors `test_mcp_stdio_sandbox.py`'s bypass usage).
   Verify the suite stays green — under passthrough the shell now runs via
   `select_shell()`+exec (`$SHELL`-honoring) instead of `create_subprocess_shell`; if
   any test depends on `$SHELL` being a non-POSIX value, neutralize it
   (`monkeypatch.delenv("SHELL", raising=False)` falls back to `/bin/sh`).

7. **New `@requires_bwrap` containment tests** — `tests/test_builtin_tool_sandbox.py`
   (a NEW file, so the passthrough autouse fixture above does NOT apply). Each test:
   `@pytest.mark.requires_bwrap`, ensures `THE_ONE_SANDBOX_DISABLED` is unset
   (`monkeypatch.delenv(..., raising=False)`) so the factory selects bubblewrap, and
   drives the real `ShellTool`/`PythonExecTool` (or `run_shell`/`run_python` with a
   profile). Build hermetic workspaces **outside `/tmp`** (see Edge Cases). The five
   tests (criteria a–e):
   - (a) **write outside allowlist denied:** allowlist=[workspace]; tool runs a write
     to a path outside workspace and not under /tmp (e.g. `<workspace>/../sibling` or
     `/usr/...`) → write fails / file absent.
   - (b) **denylist secret write denied:** allowlist=[workspace],
     denylist=[workspace/secret]; create `workspace/secret/key` first; tool write to
     `workspace/secret/key` fails (read-only overlay) but write to `workspace/ok`
     succeeds. (Write-only per the resolution; do NOT assert unreadable.)
   - (c) **network deny/allow:** start a hermetic TCP server on the host's
     `127.0.0.1` (test fixture). With `sandbox_network_allowed=False`
     (→ `--unshare-net`), a connect from the sandboxed tool to that server **fails**
     — not because loopback is down (under `--unshare-net`, `lo` is up) but because
     the sandbox has its **own isolated network namespace**: its `127.0.0.1` is a
     *different* loopback from the host's, so the host server is unreachable
     (expect `ECONNREFUSED`, not `ENETUNREACH` — do not branch the test on a specific
     errno). With `sandbox_network_allowed=True` (no `--unshare-net`, host net
     shared), the same connect **succeeds**.
   - (d) **real-HOME persistence:** `monkeypatch.setenv("HOME", str(workspace))`
     (on Linux `Path.home()` reads `HOME`, so no separate `Path.home` patch is
     needed — `_build_tool_profile` calls `str(Path.home())` at tool-call time, so it
     picks up the patched value), allowlist=[workspace]; tool runs `echo x > $HOME/f`
     (or `~/f`); assert `workspace/f` exists afterward and HOME inside the sandbox is
     the workspace.
   - (e) **timeout kills + no orphan:** tool runs `sleep 30` with `timeout=1`; assert
     it returns within a couple seconds AND the contained process is reaped (no
     orphan). Prefer a robustness-tolerant orphan check: capture a process snapshot
     before/after and assert no new surviving `sleep` remains; `pgrep -f 'sleep 30'`
     works but bwrap may alter the visible cmdline, so don't hard-depend on an exact
     cmdline match — falling back to "prompt return + proc reaped" is acceptable.
     This is the gate for the kill-strategy decision in step 3.

8. **Run** the targeted suites, the `@requires_bwrap` set, the full default suite,
   and ruff. Fix fallout.

## Edge Cases

- **bwrap `--tmpfs /tmp` shadows `/tmp`.** The bubblewrap argv mounts a fresh empty
  tmpfs at `/tmp`, so any host path under `/tmp` is **invisible/empty** inside the
  sandbox. `tempfile.mkdtemp()` defaults to `/tmp` → such a workspace would not exist
  in the sandbox and the writable-allowlist tests would be meaningless. **Create
  `@requires_bwrap` test workspaces outside `/tmp`** — e.g. under `Path.home()` or a
  dedicated dir you bind via the allowlist. (This does not affect passthrough tests.)
- **DD4/DD5 read-vs-write (resolved above).** Overlay = write-protection only;
  criterion (b) asserts not-writable, never unreadable. Do not write a read-blocking
  assertion — `--ro-bind-try` cannot deliver it.
- **`profile is None` must stay byte-for-byte legacy.** The platform tests
  (`test_platform_shell.py`, `test_platform_interpreter.py`) call the helpers with no
  profile and assert exact behavior (e.g. `run_shell("echo $FOO", env={"FOO":"bar"})`).
  Do not route the None path through the seam; do not change `create_subprocess_shell`
  on that path.
- **`env or {}` on the seam path.** Tools always pass `env=_build_subprocess_env()`
  (a dict incl. real HOME), so the seam path always has a dict. `prepare_spawn`
  requires a dict; guard with `env or {}`.
- **`$SHELL` divergence (DD7).** Switching the sandboxed shell to `select_shell()`
  means `$SHELL` is honored (fallback `/bin/sh`). In CI/containers `$SHELL` is
  usually unset → `/bin/sh`, matching today. If a passthrough-pinned tool test sets a
  weird `$SHELL`, neutralize per step 6.
- **Frozen configs.** `ExecutionConfig` is `frozen=True`; appending a defaulted field
  is safe. No call site constructs it positionally past the existing fields.
- **PrivateAttr access.** `_canonical_allowlist`/`_canonical_denylist` are populated
  in `model_post_init`; a `FilesystemConfig()` built normally has them. If a test
  constructs `FilesystemConfig` and reads the canonical lists, ensure it's a real
  instance (not `model_construct`, which skips `model_post_init`).
- **Don't touch PTY.** `platform/pty.py` and the pty session tools are Flight 2.
  This leg is shell + python only.
- **Pre-existing failure.** `tests/test_connectors_e2e.py::test_e2e_full_lifecycle`
  is a known pre-existing failure unrelated to this flight; if it is the only
  failure, it is not a regression.

## Files Affected

- `the_one/tools/execution.py` — add `sandbox_network_allowed`; add
  `_build_tool_profile`.
- `the_one/tools/shell.py` — build + pass `profile`.
- `the_one/tools/python_exec.py` — build + pass `profile`.
- `the_one/platform/shell.py` — optional `profile` seam path (`select_shell()`+exec);
  docstring.
- `the_one/platform/interpreter.py` — optional `profile` seam path; docstring.
- `the_one/platform/sandbox/bubblewrap.py` — overlay `--ro-bind` → `--ro-bind-try`;
  docstring.
- `tests/test_execution_tools.py` — autouse passthrough-pin fixture; any `$SHELL`
  neutralization.
- `tests/test_sandbox_bubblewrap.py` — overlay test expects `--ro-bind-try`.
- `tests/test_builtin_tool_sandbox.py` — new `@requires_bwrap` containment tests.
- `pyproject.toml` — update the stale `requires_bwrap=N` count comment (line ~75):
  this leg adds 5 `@requires_bwrap` tests (2 → 7). Comment-only; not a gate.
- (Possibly) `the_one/tools/filesystem.py` — optional trivial canonical-list
  accessors if you choose properties over PrivateAttr access.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (incl. `-m requires_bwrap` containment)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight: (N/A — leg 4 of 5)
- [x] Commit all changes together (code + artifacts)

> **Note (batched flight):** Implementing Developer does **not** commit and does
> **not** signal `[COMPLETE:leg]` — set the leg to `landed`, update the flight log,
> signal `[HANDOFF:review-needed]`. Status → `completed` and the commit happen in the
> flight-level review/commit phase (2d).
