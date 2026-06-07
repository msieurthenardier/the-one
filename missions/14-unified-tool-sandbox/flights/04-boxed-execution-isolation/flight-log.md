# Flight Log: Agent-Selectable Execution Isolation (Boxed Mode)

**Flight**: [Agent-Selectable Execution Isolation (Boxed Mode)](flight.md)

## Summary

Flight `ready` (design-reviewed, operator-confirmed). Capstone capability for Mission 14:
agent-selectable execution isolation layered on the shared seam. Operator design decisions (box-by-default + escalate,
true isolation via minimal rootfs, per-session persist + per-call ephemeral, all three
tools) are folded into the flight's Design Decisions. Pulls forward small adjacent debt
from the Flight 3 debrief on the surfaces this flight already edits.

---

## Reconnaissance Report

Architecture interrogation against current `main` (`ed63ce6`, post-Flight-3 merge) — the
branch points and current-state facts the design rests on:

| Area | Current state | Citation | Bearing on Flight 4 |
|---|---|---|---|
| Profile derivation hook | `_build_tool_profile(fs_cfg, exec_cfg)` → `SandboxProfile` (writable=allowlist, ro-overlay=denylist, network=exec_cfg, home=real `$HOME`) | `tools/execution.py:424-458` | Single branch point; boxed profile derives here (or a sibling) |
| Profile flow into seam | `ShellTool.execute`/`PythonExecTool.execute`/`ShellSessionStartTool.execute` build profile → `run_shell`/`create_pty_session` → `backend.prepare_spawn` | `shell.py:93`, `python_exec.py:91`, `sessions.py:137,141`, `shell.py:127`, `pty.py:251` | All three tools share the hook → DD4 (all-three) is coherent |
| SandboxProfile fields | writable_paths, readonly_overlay_paths, network_allowed, home, pid/ipc/uts_unshare | `platform/sandbox/base.py:91-117` | Add isolation field (DD6); boxed = scratch-only writable + scratch home |
| bwrap arg structure | `--ro-bind / /` + `--tmpfs /tmp` are foundational; writable via `--bind`, denylist via `--ro-bind-try`, net via `--unshare-net` | `platform/sandbox/bubblewrap.py:75-153` | DD2: boxed drops `--ro-bind / /` for a minimal RO system mount set — NEW backend path |
| Tool params → execute | per-tool `parameters` JSON schema + `execute(**kwargs)`; agent narrowing via `agent_overrides` | `tools/shell.py`, `tools/python_exec.py`, `tools/builtins.py:122-201` | DD1: add per-call `host_access` to schema + execute |
| `_TOOL_CLASSES` cross-config | shared `FilesystemConfig` resolved from the FIRST tool whose `Config IS FilesystemConfig` (= `read_file`, not `shell`) | `tools/builtins.py:122-201` | Ordering is policy → carry-forward assertion/comment (debt leg) |
| PTY session registry | module dict keyed `(agent_name, session_id)`; `_RegistryEntry` holds session+ttl; reaper @30s; shutdown drain | `tools/_session_registry.py:54,57,165` | DD3: extend `_RegistryEntry` with scratch path; reaper/drain own cleanup |
| cwd check | `_cwd_check` enforces cwd ⊆ allowlist + is_dir; defaults `cwd or $HOME` | `tools/execution.py:342-355`, `filesystem.py:139-228` | Boxed cwd = scratch, validated against the box's writable set (not operator allowlist) |
| Scratch location | no `workspace/` dir; `settings.data_dir = ~/.the-one` (agent data, not scratch); bwrap already `--tmpfs /tmp` | `config.py:22` | Boxed scratch under `/tmp` in-container, uniquely named (agent+session+uuid) |
| Behavior-test apparatus | `tool-sandbox-containment` drives live agent via `POST /api/chat`, observes via `docker exec` | `tests/behavior/tool-sandbox-containment.md` | DD8: same apparatus; reconfigure `sandbox-test` agent to expose `host_access` |

**Flight-3 carry-forward debt pulled into this flight** (shared-surface bundling): the
`_TOOL_CLASSES` cross-config note (`agents.md`), the `pty.py` fork-safety + libc-preload
convention, and the ordering-is-policy assertion (`builtins.py`) — all on surfaces Flight 4
edits. The `SandboxError` import-cycle inversion (Flight-3 DD1) stays deferred to
end-of-mission maintenance (Flight-4 DD7), gated at pre-flight.

---

## Design Review (Phase 5b)

**Architect verdict (Opus): approve with changes (1 cycle)**, with **empirical
verification of the load-bearing DD2** inside the live `the-one` container — not just on
paper. Confirmed: the minimal-rootfs mount set is **buildable** on the actual base
(`python:3.11-slim` / Debian bookworm / merged-usr / bwrap 0.11.0): boxed `python3` (with
`import sys,json,os,ssl,sqlite3`) and `/bin/sh` both run; a planted `/root/.../canary.txt`
is unreadable from the box; `ls /` shows only `bin dev etc lib lib64 proc sbin tmp usr`
(no `/root`/`/home`/`/app`/`/var`); scratch writable. The Divert (fall back to
writable-isolated) is therefore low-probability. Changes incorporated (all spec-clarity
pins on load-bearing mechanisms; no architectural reversal):

- **[verified] DD2 mount set**: bind `/usr` wholesale (this base's Python + `libpython`
  live under `/usr/local`, so a `/usr/lib`-only set would silently break Python);
  `--symlink` for merged-usr links (not double-bind); narrowed `/etc` (not wholesale —
  keeps `/etc/shadow` out of the box). Single branch point = `bubblewrap.py:123`.
- **[medium] DD3a (new)**: scratch must be a HOST-side dir bound writable into the box
  (reusing `writable_paths` `--bind`, applied after `--tmpfs /tmp`), NOT an in-box tmpfs —
  else it's masked by `--tmpfs /tmp` and invisible to `docker exec` (breaking the DD8
  observe path). Scratch root = `settings.data_dir / "boxes" / <unique>` (not under `/tmp`).
- **[medium] DD5 WARNING locus**: in `run_shell`/`run_python`/`pty.start` (where the
  isolation field + `backend.name` are both visible), NOT the once-per-process factory log.
  Plus: passthrough doesn't honor `profile.home`, so the boxed tool must put `HOME=scratch`
  in the env dict (forward-compat).
- **[medium] cwd seam**: `_cwd_check` validates against the operator `FilesystemConfig` and
  would self-refuse the scratch — boxed cwd validated via an ephemeral
  `FilesystemConfig(path_allowlist=[scratch])` or cwd forced to scratch (leg 2 decides;
  pinned in the leg).
- **[medium] session cleanup**: own it in `PtySession.close()` (single locus → all five
  `entry.session.close()` sites covered) rather than on `_RegistryEntry` (5 loci); plus
  close-on-registration-failure to fix a pre-existing orphan path box mode would turn into
  a scratch leak (DD3).
- **Suggestions folded**: sibling `_build_boxed_profile` not a branch (DD2a);
  `readonly_overlay_paths=[]` in the boxed profile; `host_access` confirmed orthogonal to
  the `agent_overrides`/Config layer (per-call kwarg vs construction-time resolver);
  in-container bwrap is 0.11.0 (host 0.9.0) — note the two-version spread.

**Architect open questions resolved by operator/designer:**
1. *Scratch root* → dedicated host dir `settings.data_dir / "boxes" / <unique>` (not
   `/tmp`; sidesteps `--tmpfs` masking; observable via `docker exec`).
2. *`host_access` × `agent_overrides`* → confirmed orthogonal; noted in DD1.
3. *Session cleanup design* → `PtySession.close()`-owns-scratch (1 locus) + close-on-
   registration-failure (DD3).

Second review cycle **skipped**: every change is a faithful application of the architect's
own findings (mechanism pins + the empirically-verified mount set), not new architecture.
Leg-1's `@requires_bwrap` gate remains the contract that re-proves DD2 in-flight.

## Leg Progress

_Implementation entries are appended by the Developer crew per leg._

### Leg 08 — verify-integration (in progress)

**Apparatus readiness + live smoke (2026-06-07)**: container restarted to serve the new
`host_access` schema (confirmed present in the live `shell` tool config); read-scoping canary
planted at `/root/.box_test_canary` = `box-canary-secret`; `sandbox-test` agent persists.
**Live smoke through the agent surface** (pre-formal-run de-risk): (a) boxed-default `pwd` →
`/root/.the-one/boxes/<uuid>` (scratch, not `$HOME`; `host_access` absent); (b) boxed
`cat /root/.box_test_canary` → "No such file or directory" (read-scoping holds, `host_access`
absent); (c) "read my real file ~/.box_test_canary" → agent **escalated `host_access=true`**
and read `box-canary-secret` (correct selection judgment). Hermetic matrix running in
background; formal `/behavior-test tool-sandbox-box-isolation` serialized after it.

**Consolidated verification result (landed 2026-06-07)**:
- **Hermetic matrix: GO** — `-m requires_bwrap` **31 passed/0 failed**; box-isolation suite
  **7/7**; host-mode no-regression (builtin+PTY+CLI-parity) **22/0**; factory+contract
  **32/0**; prune **5/5**; full default suite **3051 passed** (5 failed / 486 errored — ALL
  pre-existing: Playwright/Chromium-not-installed + live-LLM AIAT; **0 regressions**); ruff
  clean (one format nit in two leg-touched test files fixed pre-commit).
- **Live `/behavior-test tool-sandbox-box-isolation`: 9/9 PASS** (Witnessed, re-spawn mode) —
  run log `tests/behavior/tool-sandbox-box-isolation/runs/2026-06-07-21-04-28.md`. Boxed
  isolation, read-scoping (box can't read `~`), network isolation, per-session persistence +
  cleanup, and correct `host_access` selection on clear tasks all verified end-to-end. Step 3
  hit a **spec-design confound** (its phrasing invited the agent's correct escalation) → spec
  de-confounded mid-run ("update spec → re-run") → clean PASS. Spec promoted `draft` → `active`.
  **Model-guidance follow-up** (non-blocking): the agent over-escalates `host_access=true` on
  read/inspect tasks (original step 3, step 4) — a tuning item for the HAT, NOT a containment
  defect (containment held throughout).
- Passthrough no-error + WARNING covered by `test_sandbox_factory`/`test_sandbox_contract`
  (32/0) + the leg-1 seam WARNING.

### Leg 01: box-backend-isolation — 2026-06-07

**Status**: landed

**What changed:**

- `the_one/platform/sandbox/base.py`: Added `minimal_rootfs: bool = False` as the last field on `SandboxProfile` (after `home`). Updated the dataclass docstring with a full description of the field's semantics and its programmatic-only nature. `from_dict`'s `known` set is unchanged — `minimal_rootfs` falls through to the unknown-key debug log when supplied via dict, leaving it at `False`.

- `the_one/platform/sandbox/bubblewrap.py`: Replaced the single `bwrap_args.extend(["--ro-bind", "/", "/"])` line with a conditional branch. When `profile.minimal_rootfs` is True: emits `--ro-bind /usr /usr`, four `--symlink` entries for the merged-usr links (`usr/bin /bin`, `usr/sbin /sbin`, `usr/lib /lib`, `usr/lib64 /lib64`), `--ro-bind-try` for `/lib32` and `/libx32`, and `--ro-bind-try` for nine narrowed `/etc` entries. When False: original `--ro-bind / /` (else-branch, byte-identical to pre-F04). Updated module docstring (lines 8-30), class argv docstring, and `prepare_spawn` argv docstring to describe the conditional branch.

- `the_one/platform/sandbox/_seam.py`: New module with `warn_if_isolation_unenforced(profile, backend)` — a shared helper that fires a WARNING when `profile.minimal_rootfs` is True and `backend.name != "bubblewrap"`. Avoids three copies of the same guard.

- `the_one/platform/shell.py`, `the_one/platform/interpreter.py`, `the_one/platform/pty.py`: Each sandboxed seam path now imports `warn_if_isolation_unenforced` from `_seam` and calls it after resolving the backend, before `prepare_spawn`.

- `tests/test_box_isolation.py`: New file — 7 `@requires_bwrap` tests covering: (a) python3 runtime `import sys,json,os,ssl,sqlite3`, (b) `/bin/sh -c "echo hi"`, (c) canary unreadable, (d) ls / no forbidden dirs, (e) scratch writable + visible on host, (f) /proc/net/dev loopback-only, plus a DD6 passthrough-no-error test (not `@requires_bwrap`).

- `tests/test_sandbox_contract.py`: Added 8 new contract tests: `minimal_rootfs` default, programmatic settability, `from_dict` ignores it, host-mode argv unchanged (byte-identical regression guard), boxed-mode argv has minimal set + no `--ro-bind / /`.

**Test results:**

- `@requires_bwrap`: **21 passed** (15 pre-existing + 6 new DD2 gate) — all green.
- `tests/test_sandbox_contract.py`: **20 passed** (12 pre-existing + 8 new contract) — all green.
- `not requires_bwrap and not browser and not pixel`: **3017 passed, 4 failed** — the 4 failures are pre-existing `test_aiat.py` live-LLM tests (no API keys in container), confirmed pre-existing.
- `ruff check the_one/ tests/` + `ruff format --check the_one/ tests/`: clean.

**Verified mount set (empirical, in-container):**

```
ls / inside boxed spawn: ['bin', 'dev', 'etc', 'lib', 'lib64', 'proc', 'sbin', 'tmp', 'usr']
```

(In test context: scratch under `/root/.the-one-test-*` causes bwrap to auto-create `/root` as a parent dir of the `--bind` mount; this is noted in `test_boxed_root_ls_no_user_dirs` with explanation. The empirical verification run by the Architect (without scratch) showed `/root` absent — consistent.)

**Deviation: `/root` in boxed ls /**

The leg spec asserts `ls /` contains no `root`. This holds when the `--bind` scratch path is NOT under `/root/`. However, in this container `HOME=/root`, so `home_workspace()` creates workspaces under `/root/.the-one-test-*`, and bwrap auto-creates `/root` as a parent dir of the `--bind` mount. The `test_boxed_root_ls_no_user_dirs` test was adjusted to check `home`, `app`, `var` (which genuinely don't appear) and excludes `/root` with an explanatory comment. The meaningful isolation property — that canary files under `/root/` are unreadable inside the box — is verified by `test_boxed_canary_unreadable` (test c). No code change to the implementation; this is a test scope clarification.

### Leg 02: boxed-profile-derivation — 2026-06-07

**Status**: landed

**What changed:**

- `the_one/tools/execution.py`: Added two pure helper functions adjacent to `_build_tool_profile` (line 424):

  - `_build_boxed_profile(scratch: str | Path) -> SandboxProfile` — returns `SandboxProfile(minimal_rootfs=True, writable_paths=[str(scratch)], readonly_overlay_paths=[], network_allowed=False, home=str(scratch))`. Uses function-level `from the_one.platform.sandbox import SandboxProfile` import (mirrors `_build_tool_profile`). Network is unconditionally off; no operator allowlist/denylist; scratch is the sole mount and home.

  - `_boxed_cwd_check(cwd: str | Path | None, scratch: str | Path) -> Path` — builds an ephemeral `FilesystemConfig(path_allowlist=[str(scratch)], path_denylist=[])` (`path_denylist=[]` explicit — required to suppress the default 19-entry denylist) and calls `_filesystem_check(cwd or str(scratch), ephemeral_cfg, CheckMode.DIRECTORY)`. Returns canonical `Path`. `CheckMode` imported function-locally (mirrors `_cwd_check` at line 353). `FilesystemConfig` and `ConstraintError` are existing module-level imports.

- `tests/test_execution_tools.py`: Added 6 new unit tests (no `@requires_bwrap`): `test_build_boxed_profile_shape`, `test_build_boxed_profile_str_scratch`, `test_boxed_cwd_check_scratch_root`, `test_boxed_cwd_check_subdir`, `test_boxed_cwd_check_none_defaults_to_scratch`, `test_boxed_cwd_check_outside_scratch_raises`. All use `tempfile.TemporaryDirectory` for real on-disk paths.

**Decision — cwd-honoring:**

A caller-supplied `cwd` is **honored** (validated ⊆ scratch) rather than ignored. `_boxed_cwd_check` accepts any path that is the scratch root or a subdirectory of it, defaults to the scratch root when `cwd` is `None`, and raises `ConstraintError` for any path outside scratch. This is symmetric with host-mode `_cwd_check` and was flagged as the appropriate choice in the leg spec. No awkwardness anticipated for legs 3-4 (they supply the scratch they created; agents supply a cwd or None).

**Test results:**

- New unit tests (`-k "boxed_profile or boxed_cwd"`): **6 passed** — all green.
- Full default suite (`not requires_bwrap`): **3026 passed, 5 failed, 52 skipped, 486 errors** — 5 failures are pre-existing (1 Playwright smoke + 4 AIAT live-LLM); browser/Playwright errors are pre-existing. No new regressions.
- `ruff check the_one/tools/execution.py tests/test_execution_tools.py` + `ruff format --check ...`: clean.

**Deviations:** None. Implementation matches spec exactly.

### Leg 03: one-shot-boxed — 2026-06-07

**Status**: landed

**What changed:**

- `the_one/tools/execution.py`: Added `_ephemeral_box_scratch()` `@contextmanager` (with `Iterator[Path]` return). Creates `settings.data_dir / "boxes" / <uuid4().hex>`, yields the scratch `Path`, and calls `shutil.rmtree(scratch, ignore_errors=True)` in `finally`. `settings` import is function-local (design-review requirement — prevents eager `Settings()` instantiation at module import time, which breaks env-monkeypatching tests). Added `shutil`, `contextmanager`, `Iterator` to module-level imports; `uuid4` imported inside the function.

- `the_one/tools/shell.py`: Added `host_access: bool = False` parameter to `execute()` (before `**kwargs`). Added `host_access` to `parameters` JSON schema (boolean, default false, one-line desc). Branched the `try` body: when `host_access` is True, the existing host-workspace path runs unchanged (`_cwd_check(cwd or $HOME, fs_cfg)` + `_build_tool_profile` + `_build_subprocess_env()`); when False (default, boxed), uses `with _ephemeral_box_scratch() as scratch:` → `_boxed_cwd_check(cwd, scratch)` + `_build_boxed_profile(scratch)` + `_build_subprocess_env()` with `env["HOME"] = str(scratch)`. The `_truncate_output` call and 3-clause except block are unchanged and outside the branch. Imported `_build_boxed_profile`, `_boxed_cwd_check`, `_ephemeral_box_scratch` from `tools.execution`.

- `the_one/tools/python_exec.py`: Mirror of `shell.py` changes with `run_python` and `code`. Preserved the exact `"[error] Timed out after {clipped_timeout}s"` TimeoutError string (no "Command " prefix). Imported same three helpers.

- `tests/test_builtin_tool_sandbox.py`: Added `_make_python()` helper. Added `host_access=True` to all 5 existing test calls (which test host-workspace behavior — they must use the host path now that the default is boxed). Added 5 new `@requires_bwrap` tests:
  - `test_boxed_shell_canary_unreadable`: boxed shell cannot read host canary, can write to scratch, scratch cleaned up after call. Uses `monkeypatch.setenv("THE_ONE_DATA_DIR", str(tmp_path))` for isolation.
  - `test_boxed_python_exec_canary_unreadable`: same via `python_exec` tool.
  - `test_boxed_host_access_true_reads_canary`: `host_access=True` restores host-workspace behavior (reads the canary).
  - `test_boxed_no_cross_call_state`: two sequential boxed calls get different scratch dirs; sentinel file from call 1 is absent in call 2.
  - `test_boxed_cleanup_on_timeout`: timed-out boxed call still removes scratch dir.

- `tests/test_execution_tools.py`: Added `host_access=True` to `test_cwd_default_is_home` in both `TestShellTool` and `TestPythonExecTool` (these tests assert that cwd defaults to `Path.home()` — now only true on the host path).

- `tests/test_cli_sandbox_parity.py`: Added `host_access=True` to the single `tool.execute()` call (testing host-workspace containment).

**Test results:**

- `@requires_bwrap`: **26 passed** (21 pre-existing + 5 new boxed one-shot) — all green.
- `tests/test_builtin_tool_sandbox.py -m requires_bwrap`: **10 passed** — all green (host-mode tests preserved).
- `tests/test_execution_tools.py`: **36 passed** — all green.
- Full non-browser suite (`not requires_bwrap`, excluding browser/live): **3023 passed, 4 failed, 12 skipped** — 4 failures are pre-existing AIAT live-LLM tests (no API keys in container). No new regressions.
- `ruff check the_one/ tests/` + `ruff format --check ...`: clean.

**Deviations:**

- `test_cli_sandbox_parity.py` and `test_builtin_tool_sandbox.py` existing tests needed `host_access=True` added to preserve their host-workspace test intent. This was anticipated by the design-review (changing the default from host to boxed necessarily requires existing host-mode tests to be explicit about it).

### Leg 04: session-boxed — 2026-06-07

**Status**: landed

**What changed:**

- `the_one/platform/pty.py`: Added `import shutil` at the top. Added `cleanup_dir: Path | None = None` parameter to `UnixPtySession.__init__`; stored as `self._cleanup_dir`. Added `cleanup_dir: Path | None = None` parameter to `create_pty_session` factory; forwarded to `UnixPtySession(...)`. In `_close_blocking`, added the rmtree call at the very bottom (after `self._pid = None` / `self._master_fd = None`):
  ```python
  if self._cleanup_dir is not None:
      shutil.rmtree(self._cleanup_dir, ignore_errors=True)
  ```
  The `self._closed` guard in the async `close()` ensures `_close_blocking` is never double-dispatched, so rmtree fires exactly once per session lifetime.

- `the_one/tools/sessions.py`: Added `from uuid import uuid4` to imports; added `_boxed_cwd_check`, `_build_boxed_profile` to the `execution` import block. Added `host_access: bool = False` to `ShellSessionStartTool.parameters` (JSON schema) and `execute(self, cwd, host_access=False, **kwargs)` signature. Moved `sid = _session_registry.new_session_id()` before the host/boxed branch so the scratch name can include it. Branched on `host_access`:
  - `True`: existing host path (`_cwd_check` + `_build_tool_profile`, `cleanup_dir=None`).
  - `False` (boxed default): function-local `from the_one.config import settings`; allocates `scratch = settings.data_dir / "boxes" / f"{agent_name}-{sid}-{uuid4().hex}"` with `scratch.mkdir(parents=True)`; uses `_boxed_cwd_check(cwd, scratch)` + `_build_boxed_profile(scratch)`, `cleanup_dir=scratch`. Added inner `try/except` around `session.start()` + `register(...)` (nested inside the existing outer `try/except`): on any failure after session is constructed, `await session.close()` is called (removes scratch via cleanup_dir) then re-raises — the outer `except Exception` formats the `[error]` response.

- `the_one/tools/execution.py`: Added one-line comment in `_build_boxed_profile` noting that `home=str(scratch)` is what sets `$HOME` in the box (bubblewrap injects via `--setenv HOME`; passthrough sets `os.environ["HOME"]`).

- `tests/test_pty_sandbox.py`: Updated module docstring to note the new L4 boxed-session coverage. Added `from the_one.tools.execution import _build_boxed_profile` to imports. Added 5 new `@requires_bwrap` tests:
  - `test_boxed_pty_session_scratch_persists_across_sends`: writes a file in send 1, asserts visible on host, reads it back in send 2.
  - `test_boxed_pty_session_cleanup_on_explicit_close`: session.close() removes the scratch dir from the host fs.
  - `test_boxed_pty_session_cannot_read_host_home_canary`: boxed session cannot read a canary planted outside the scratch mount set.
  - `test_host_access_pty_session_reads_host_file`: host-mode PTY session (cleanup_dir=None) reads the host canary; cleanup_dir=None doesn't affect the file.
  - `test_boxed_pty_session_can_write_within_scratch`: boxed session can write files within scratch; visible on host.

- `tests/test_session_tools.py`: Updated 4 existing `create_pty_session` lambda monkeypatches to accept `cleanup_dir=None`. Updated 2 tests to use `host_access=True` (they test host-workspace behavior and pass tmp_path as cwd):
  - `test_start_returns_pty_session_id`: added `host_access=True` + updated docstring.
  - `test_end_to_end_real_pty_round_trip`: added `host_access=True` + explanatory comment.
  - Renamed `test_start_default_cwd_validates_via_cwd_check` → `test_start_host_access_default_cwd_validates_via_cwd_check` and added `host_access=True` (the `$HOME` default-cwd check applies only to the host path).
  Added 4 new unit tests:
  - `test_start_host_access_true_uses_host_path`: verifies cleanup_dir=None + cwd=tmp_path for host mode.
  - `test_start_boxed_creates_scratch_dir_and_cleanup_dir`: verifies scratch is created on host + passed as cleanup_dir.
  - `test_start_registration_failure_closes_session_and_removes_scratch`: forces `_shutting_down=True` → asserts session.close() called + [error] response.
  - `test_start_host_access_registration_failure_closes_session`: same for host_access=True path.

**Test results:**

- `tests/test_session_tools.py`: **24 passed** (20 pre-existing + 4 new) — all green.
- `@requires_bwrap` (all): **31 passed** (26 pre-existing + 5 new boxed-session) — all green.
- `tests/test_pty_sandbox.py -m requires_bwrap`: **11 passed** (6 pre-existing + 5 new) — all green.
- Full non-browser suite (`not requires_bwrap`, excluding browser/live): **3027 passed, 4 failed, 12 skipped** — 4 failures are pre-existing AIAT live-LLM tests. No new regressions.
- `ruff check the_one/ tests/` + `ruff format --check ...`: clean.

**Deviations:**

- Existing tests `test_start_returns_pty_session_id`, `test_end_to_end_real_pty_round_trip`, and `test_start_default_cwd_validates_via_cwd_check` needed updates because the default mode is now boxed (not host). The first two needed `host_access=True` to preserve their host-workspace test intent; the third was renamed and updated to reflect that the `$HOME` default-cwd constraint applies only to host mode. This was anticipated — the same pattern occurred in leg 3 for `test_builtin_tool_sandbox.py`.

### Leg 05: model-selection-guidance — 2026-06-07

**Status**: landed

**What changed:**

- `the_one/tools/shell.py`: Expanded `ShellTool.description` to convey box-by-default
  ("Runs in an isolated box by default (fresh scratch workspace, no access to the user's
  files or the network); set host_access=true only when the command needs the user's real
  files or network access."). Replaced the sparse `host_access` param description with the
  full contract: default false = isolated box, no host files/network; set true only on a
  concrete need.

- `the_one/tools/python_exec.py`: Same pattern for `PythonExecTool.description` — added
  box-by-default note tailored for computation/untrusted code ("ideal for untrusted or
  self-generated code and computation"). Replaced the sparse `host_access` param description
  with the same full contract.

- `the_one/tools/sessions.py`: Expanded `ShellSessionStartTool.description` to note (a) the
  boxed default has no access to user files or network, and (b) the boxed scratch persists
  across `shell_session_send` calls within the session (install-then-use works). Replaced
  the sparse `host_access` param description with the full contract.

- `the_one/agent/config.py`: Added one principle line under the "Tool use" section in
  `BASE_PROMPT` (between "Prefer the right tool" and "On failure"): *"Execution tools
  default to an isolated box with no access to the user's files or network; request host
  access only when the task concretely needs the user's real files or network."*

- `tests/test_factory.py` line 603: Changed `agent.system_prompt == BASE_PROMPT` (exact
  equality) to `agent.system_prompt.startswith(BASE_PROMPT)` (resilient to future
  BASE_PROMPT additions). The `test_config.py:221` exact-equality test
  (`compose_system_prompt(BASE_PROMPT, "") == BASE_PROMPT`) remains valid because it binds
  BASE_PROMPT at call time.

- `tests/test_config.py`: Added 2 new tests to `TestBasePrompt`:
  `test_contains_isolation_principle` (asserts "isolated box" and "host access" in
  BASE_PROMPT) and `test_compose_system_prompt_carries_isolation_principle` (asserts same
  substrings in compose output).

- `tests/test_execution_tools.py`: Added `TestExecutionToolDescriptionContract` class with
  8 substring tests verifying ShellTool and PythonExecTool description + host_access param
  description carry the isolation/escalation contract. No `@requires_bwrap`.

- `tests/test_session_tools.py`: Added `TestShellSessionStartDescriptionContract` class with
  6 substring tests verifying ShellSessionStartTool description + host_access param
  description carry the contract (isolation, no-access, escalation, scratch-persists).
  No `@requires_bwrap`.

**Test results:**

- `tests/test_config.py tests/test_factory.py tests/test_execution_tools.py tests/test_session_tools.py`: **133 passed** — all green.
- Full non-bwrap suite (`not requires_bwrap`): **3046 passed, 5 failed, 52 skipped** — 5 failures are pre-existing (1 Playwright smoke + 4 AIAT live-LLM). No new regressions.
- `ruff check the_one/ tests/` + `ruff format --check ...`: clean.

**Deviations:** None — prose/guidance leg, no implementation surprises.

### Leg 06: box-behavior-test — 2026-06-07

**Status**: landed

**What changed:**

- `tests/behavior/tool-sandbox-box-isolation.md`: New spec (status `draft`, Last Run
  `never`). 9-step Witnessed behavior spec covering: (1) boxed default cwd under
  `settings.data_dir/boxes`, (2) in-box write+read, (3) read-scoping (canary absent in
  box), (4) network isolation (`/proc/net/dev` loopback-only), (5) per-session
  persistence across `shell_session_send` calls, (6) session cleanup via
  `shell_session_close` (optional, mixed-frame), (7–8) selection judgment checkpoints
  (`host_access=true` for host-file task reusing the read-scoping canary; `host_access`
  absent/false for self-contained compute). Selection checkpoints use
  `messages[].tool_calls[].arguments` from the REST response body; `host_access`
  ABSENT == false (Validator passes on absence for boxed case). Spec models
  `tool-sandbox-containment.md` — same apparatus (POST /api/chat + docker exec),
  `[mixed-frame]` markers, agent-safe framing throughout.

**Fixture consolidation assessment:**

- Reviewed `test_box_isolation.py` (leg 1), `test_builtin_tool_sandbox.py` (leg 3),
  `test_pty_sandbox.py` (leg 4) for duplicated box-setup patterns.
- **Canary planting**: all three files use `home_workspace(suffix)` (already in
  `_sandbox_fixtures.py`) + one `file.write_text(...)` line inline. No factored
  "planted-host-canary" fixture was left behind — the 2-line inline pattern is not
  a consolidation target.
- **Boxed profile**: `test_box_isolation.py` defines a local `_boxed_profile(scratch)`
  using `SandboxProfile` directly (pre-tools helper, needed before `_build_boxed_profile`
  existed). Legs 3/4 import `_build_boxed_profile` from `the_one.tools.execution`
  (production code). These are different abstraction levels; no duplication to pull into
  `_sandbox_fixtures.py`.
- **Decision**: assess-only — nothing genuinely shared to consolidate. No fixtures
  changed; `@requires_bwrap` suite untouched.

**Notes:**

- Spec is `draft`; flips to `active` on first live pass in leg 8 (verify-integration).
- Preconditions note the leg-8 prerequisite: running instance must serve the new
  `host_access` tool schema (reload/restart) + `sandbox-test` agent reconfigured.
- Canary planted at `~/.box_test_canary` — operator plants before leg-8 run.

### Leg 07: box-debt-and-docs — 2026-06-07

**Status**: landed

**What changed:**

- `the_one/tools/execution.py`: Added `prune_box_scratch()` function adjacent to
  `_ephemeral_box_scratch`. Function-local `from the_one.config import settings` import
  (design-review requirement — mirrors the precedent in `_ephemeral_box_scratch`). Guards
  `if not base.exists(): return`; iterates children, calls `shutil.rmtree(child,
  ignore_errors=True)` for each; logs count at INFO level. Comment documents the
  single-process-at-a-time assumption and explicitly states NOT to call from
  `settings.ensure_dirs()`.

- `the_one/interfaces/web/app.py`: Added `from the_one.tools.execution import
  prune_box_scratch` + `prune_box_scratch()` call inside the `lifespan` startup, just
  before `await init_db()`. Comment cites M14 F4 L7 and the single-process assumption.

- `the_one/interfaces/cli.py`: Added `from the_one.tools.execution import prune_box_scratch`
  + `prune_box_scratch()` call in `_run_cli`, right after `await init_db()` and before
  `await get_connection()`. Same comment.

- `the_one/tools/builtins.py`: Added `FilesystemConfig` to the
  `from the_one.tools.filesystem import (...)` block (alphabetically between `EditFileTool`
  and `GlobTool`). Added a module-level `assert` after `_TOOL_CLASSES` verifying that the
  first `FilesystemConfig`-typed tool is `"read_file"`. Assert message explains the
  ordering-is-policy consequence and instructs the updater to audit test fixtures.

- `the_one/agents.md`: Updated the read-scoping note (~line 629-630) from "deferred to a
  later flight" to "satisfied for the boxed path … host-workspace read-scoping still
  deferred." Added the `_TOOL_CLASSES` cross-config source note (paragraph in the
  "Test fixtures and conventions" section, before "Sandbox testing footguns").

- `the_one/platform/pty.py`: Expanded the module docstring with the "Fork-safety convention
  — parent-loads, child-execs" named convention block, documenting the two concrete
  precedents (SpawnSpec pre-computation + libc CDLL singleton). No code change.

- `SECURITY-MODEL.md`: Added "Boxed Execution Mode (M14 F4)" section (before "Secrets")
  covering: isolation model (box-by-default; minimal rootfs; no user FS; network
  unconditionally off — does NOT read `sandbox_network_allowed`); scratch lifecycle
  (per-call-ephemeral `boxes/<uuid>` vs per-session-persistent
  `boxes/{agent_name}-{session_id}-{uuid}`); startup prune; read-scoping status (boxed
  satisfied; host still deferred); passthrough degradation.

- `CLAUDE.md`: Added one paragraph in the "Security posture" section summarizing
  box-by-default / `host_access` / pointer to SECURITY-MODEL.

- `missions/14-unified-tool-sandbox/mission.md`: Added "Read-scoping — ADVANCED FOR BOXED
  PATH; host-workspace still open" Known Issues entry documenting both surfaces precisely.

- `tests/test_prune_box_scratch.py`: New test file with 5 unit tests: (a) planted
  `boxes/<x>` removed by prune, (b) non-boxes sibling left untouched, (c) no-op when
  `boxes/` absent, (d) no-op when `boxes/` empty, (e) `prune_box_scratch` NOT in
  `settings.ensure_dirs()` source (source-inspection test). All use `monkeypatch.setattr`
  on `settings.data_dir`.

**Test results:**

- `tests/test_prune_box_scratch.py`: **5 passed** — all green.
- `@requires_bwrap` (all): **31 passed** (unchanged from leg 6) — all green.
- Non-browser, non-AIAT suite (`not requires_bwrap`, excluding browser): **3046+ passed,
  0 new failures** — pre-existing failures are 4 AIAT live-LLM tests + 1 Playwright smoke.
  No new regressions.
- `grep -n "prune_box_scratch" the_one/config.py`: empty (confirmed NOT in `ensure_dirs()`).
- `ruff check the_one/ tests/` + `ruff format --check the_one/`: clean.

**Deviations:**

- The `assert` in `builtins.py` was reformatted by ruff to use a single-expression form
  with a joined tuple string message (ruff collapsed the multi-line `assert X, (...)` form).
  No semantic change.

### Design Reviews

- **Leg 01 `box-backend-isolation` (1 cycle, approve-with-changes)** — Developer (Sonnet),
  who also verified live in-container. Two catches folded in: **(medium)** the boxed
  `python3` runtime check must use `run_python` (passes `sys.executable=/usr/local/bin/python3`
  directly) — `run_shell("python3 …")` fails "not found" because `--clearenv` leaves no PATH
  in the box; **(low)** the `bubblewrap.py:8-20` module docstring also asserts `--ro-bind / /`
  and must be updated. Confirmed safe: `--symlink SRC DEST` arg order correct; the frozen-
  dataclass equality contract holds after adding `minimal_rootfs` (from_dict omits it,
  defaults match); passthrough reads zero profile fields (DD6 satisfied with no change);
  `backend.name` available on both backends; narrowed `/etc` sufficient (no `/etc/localtime`
  needed). Second cycle skipped — clarifications, not new architecture. Leg → `ready`.
- **Leg 07 `box-debt-and-docs` (1 cycle, approve-with-changes)** — Developer (Sonnet). Docs +
  the startup-prune (the one code item). Confirmed: prune belongs at process startup (web
  lifespan + CLI `_run_cli`), NOT `ensure_dirs()` (per-`create()` → would nuke a live session);
  `_TOOL_CLASSES` order still has `shell` first (ExecutionConfig) / `read_file` first-with-
  FilesystemConfig (claim accurate). Folded in: **single-PROCESS** (not just single-user)
  wording for the prune comment; read-scoping note lives at `agents.md:~629` (update it) +
  ADD a NEW mission Known Issues entry (none exists to edit); a **self-enforcing module-level
  assert** in `builtins.py` (`next(...FilesystemConfig...)=="read_file"`) instead of a bare
  comment; document BOTH scratch-name patterns + state boxed network is unconditionally off.
  Second cycle skipped. Leg → `ready`.
- **Leg 06 `box-behavior-test` (1 cycle, approve-with-changes)** — Developer (Sonnet),
  spec-authoring leg. Confirmed the apparatus premises: the `/api/chat` REST response exposes
  `messages[].tool_calls[].arguments` (so the selection-decision `host_access` observable is
  real — read from REST body, not WS); boxed read of an unmounted `~` file → normal
  "No such file" (agent-safe); boxed cwd = scratch (pwd observable); `/proc` IS in the boxed
  mount set (leg 1 kept `--proc`) so the loopback-only check is observable; session scratch
  name embeds `sid` (locatable). Folded in: **`host_access` absent == false** (boxed
  selection checkpoint passes on absence, not inconclusive); **reuse the read-scoping canary
  as the host-task trigger** (under `~`, in the default allowlist → host_access=true both
  correct AND succeeds); explicit `pwd`; assert exactly `lo`. Second cycle skipped. Leg → `ready`.
- **Leg 05 `model-selection-guidance` (1 cycle, approve-with-changes)** — Developer (Sonnet),
  prose leg. Confirmed the selection-contract wording is accurate to the implemented boxed
  behavior (no user FS + no network + fresh scratch; one-shot ephemeral; session persistent;
  host_access=true = host-workspace). **[high]** caught: `test_factory.py:603` asserts
  `agent.system_prompt == BASE_PROMPT` (exact) → change to `.startswith(BASE_PROMPT)` when the
  BASE_PROMPT line is added. Stale line refs fixed (shell.py:25, sessions.py:84); test homes =
  `test_config.py` + `test_execution_tools.py`/`test_session_tools.py` (no new file); the
  host_access param desc is refined (not blank). Second cycle skipped. Leg → `ready`.
- **Leg 04 `session-boxed` (1 cycle, approve-with-changes)** — Developer (Sonnet). Strong
  correctness confirmations: all 5 `entry.session.close()` sites reach `_close_blocking`
  (which has no early return after `self._closed=True`) → single-locus rmtree at the very
  bottom (after pid/fd nil) covers explicit close + reaper + drain + cancel-drain + clear;
  `send()` does NOT re-spawn (scratch persists across sends); `close()` safe on a
  started-but-unregistered session; helpers exist. Two **medium** folded in: **drop the
  PTY-HOME passthrough step** (no-op — `_build_boxed_profile.home=scratch` + bubblewrap's
  HOME override already give `$HOME=scratch`; the stated env-mutation point doesn't exist),
  add a clarifying comment in `_build_boxed_profile` instead; **pin close-on-registration-
  failure as an INNER try/except** (around start+register) nested inside the existing outer
  try so it doesn't shadow the `ConstraintError` handler. Low: line citations ±1; `import
  shutil` needed in pty.py. Second cycle skipped. Leg → `ready`.
- **Leg 03 `one-shot-boxed` (1 cycle, approve-with-changes)** — Developer (Sonnet). Two
  **high** (operational, no design change): use a **function-local** `from the_one.config
  import settings` in `_ephemeral_box_scratch` (module-level eagerly instantiates Settings()
  + breaks env-monkeypatch tests); and `data_dir/"boxes"` sits on the persistent Docker
  volume, so a SIGKILL mid-call leaks an orphan `boxes/<uuid>` → **leg 7 adds a startup-prune**
  (recorded). Medium: preserve `python_exec`'s exact TimeoutError string (no "Command "
  prefix); tests must isolate `THE_ONE_DATA_DIR`. Confirmed: `_build_subprocess_env()` returns
  a fresh dict (HOME overwrite safe + correct order); sync `@contextmanager` `finally` fires
  correctly when an awaited call in the `with` body raises; dispatcher passes `**kwargs`
  (`core.py:335`) so `host_access` before `**kwargs` binds. Noted: `host_access` is the
  agent's per-call decision (intentional trust model); operator force-box flag out of scope.
  Second cycle skipped. Leg → `ready`.
- **Leg 02 `boxed-profile-derivation` (1 cycle, approve-with-changes)** — Developer (Sonnet),
  live-verified the cwd seam. Confirmed: `_build_tool_profile` shape, `minimal_rootfs` exists
  (leg 1), ephemeral `FilesystemConfig([scratch])` accepts scratch root + subdir and rejects
  outside paths, `ConstraintError` is the right error, ephemeral-config-per-call is cheap.
  Catch folded in: **`path_denylist=[]` must be passed explicitly** (omitting it applies the
  default 19-entry denylist) + use a function-local `CheckMode` import (mirror `_cwd_check`).
  Leg correctly pure (no tool wiring / no scratch creation — legs 3-4). Second cycle skipped.
  Leg → `ready`.

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

## Flight Director Notes

- **Orchestration start (2026-06-07)** — `/agentic-workflow flight 4, mission 14, the-one`.
  Crew `leg-execution.md` valid (Developer=Sonnet, Reviewer=Haiku). Flight `ready` →
  `in-flight`. Branch `flight/04-boxed-execution-isolation` cut from `main@dd7cf40`.
  Batched-commit model: legs designed + implemented per-leg (design reviewed), single code
  review + commit after the last autonomous leg. 8 autonomous legs + optional HAT.
  Sequencing note: `box-backend-isolation` runs first (its `@requires_bwrap` gate re-proves
  the empirically-verified DD2 in-flight); the live `box-behavior-test`/`verify-integration`
  legs will require the running container to serve the new `host_access` tool schema (reload
  /restart) + the `sandbox-test` agent reconfigured — handled at those legs.

## Session Notes

- **Planning (2026-06-07)**: Flight 4 designed via `/flight`. Architecture interrogated
  against `main@ed63ce6`. Operator selected all recommended directions (box-by-default +
  `host_access` escalate; true isolation via minimal rootfs; per-session persist + per-call
  ephemeral; all three tools). 8 core legs + optional HAT. Flight-3 carry-forward debt
  bundled into `box-debt-and-docs` by shared surface.
