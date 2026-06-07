# Leg: one-shot-boxed

**Status**: completed
**Flight**: [Agent-Selectable Execution Isolation (Boxed Mode)](../flight.md)

## Objective

Make the one-shot `shell` and `python_exec` tools **boxed by default** with a per-call
`host_access` escalation: when `host_access` is false (default), each call runs in a fresh
ephemeral scratch box (via leg 2's `_build_boxed_profile` + `_boxed_cwd_check`), cleaned up
when the call returns; when true, the existing host-workspace path runs unchanged.

## Context

- **DD1**: per-call `host_access: bool` (default false → boxed). `host_access=true`
  reproduces today's host-workspace behavior exactly.
- **DD3**: one-shot boxed = fresh ephemeral scratch **per call**, cleaned up on return (no
  cross-call state). Scratch root = `settings.data_dir / "boxes" / <uuid>` (DD3a — host-side
  real dir, NOT in-box tmpfs).
- **DD5**: on the boxed path the tool must put `HOME=scratch` into the **env dict** (not rely
  on `profile.home`) so passthrough honors it too (bubblewrap also sets it via `profile.home`
  — harmless overlap).
- Current `ShellTool.execute` (`tools/shell.py:58-108`): `_command_check` →
  `_cwd_check(cwd or $HOME, fs_cfg)` → `_build_tool_profile(fs_cfg, exec_cfg)` →
  `run_shell(command, timeout, env=_build_subprocess_env(), cwd, profile)`. `PythonExecTool`
  (`tools/python_exec.py:91`) mirrors with `run_python`. Both wrap a 3-clause
  ConstraintError→TimeoutError→Exception envelope.
- Leg 2 delivered `_build_boxed_profile(scratch)` + `_boxed_cwd_check(cwd, scratch)`.

## Inputs

- Legs 1 + 2 landed (backend isolation path, profile + cwd derivation helpers).
- `settings.data_dir` (`the_one/config.py:22`, `~/.the-one`).

## Outputs

- `host_access: bool` param on `shell` + `python_exec` (schema + `execute`), default false.
- A shared ephemeral-box-scratch context manager (in `tools/execution.py`).
- Boxed branch in both tools' `execute()`; host path unchanged when `host_access=true`.
- `@requires_bwrap` tests for boxed one-shot + host-mode-unchanged.

## Acceptance Criteria

- [x] `shell` and `python_exec` accept a per-call `host_access: bool` (default `false`) in
      both the `parameters` JSON schema and the `execute()` signature. (Schema description
      can be minimal here; the rich selection guidance is leg 5.)
- [x] **Default (boxed)**: a call with `host_access` false (or omitted) creates a fresh
      ephemeral scratch dir under `settings.data_dir/"boxes"/<uuid>`, builds the profile via
      `_build_boxed_profile(scratch)`, validates cwd via `_boxed_cwd_check(cwd, scratch)`
      (default cwd → scratch), sets `HOME=scratch` in the env dict, runs, and **removes the
      scratch dir on return** (success OR error — a `finally`).
- [x] **Escalated (`host_access=true`)**: the existing host-workspace path runs **unchanged**
      — `_cwd_check(cwd or $HOME, fs_cfg)` + `_build_tool_profile(fs_cfg, exec_cfg)` +
      `_build_subprocess_env()`. No behavior change vs pre-flight for this path.
- [x] The 3-clause error envelope (ConstraintError → TimeoutError → Exception) still wraps
      both paths; scratch cleanup happens even when an exception is raised.
- [x] **No cross-call state** for boxed one-shots: two sequential boxed calls get different
      scratch dirs; a file written in call 1 is gone in call 2.
- [x] `@requires_bwrap` tests: a boxed `shell`/`python_exec` call cannot read a planted host
      home-file; can write within its scratch; the scratch dir does NOT exist on the host
      after the call returns (cleanup). `host_access=true` call reads the host file (host
      mode intact). The python check uses `python_exec` (boxed), the shell check uses `shell`.
- [x] Full default suite + ruff green; existing host-mode `@requires_bwrap` tests
      (`test_builtin_tool_sandbox.py`) unaffected.

## Verification Steps

- `docker exec the-one python -m pytest -m requires_bwrap --timeout 120 -q` — green incl. new boxed one-shot tests.
- `docker exec the-one python -m pytest tests/test_builtin_tool_sandbox.py -m requires_bwrap --timeout 120 -q` — host-mode tests still pass.
- `docker exec the-one python -m pytest --timeout 60 -m "not requires_bwrap" -q` — no regressions.
- Confirm (test): after a boxed call, `settings.data_dir/boxes/<uuid>` is gone (no scratch leak).
- `docker exec the-one ruff check the_one/ tests/ && docker exec the-one ruff format --check the_one/tools/shell.py the_one/tools/python_exec.py the_one/tools/execution.py`.

## Implementation Guidance

1. **Shared scratch context manager** in `tools/execution.py` (so shell + python_exec don't
   duplicate it), e.g.:
   ```python
   @contextmanager
   def _ephemeral_box_scratch() -> Iterator[Path]:
       from the_one.config import settings   # FUNCTION-LOCAL (design-review)
       base = settings.data_dir / "boxes"
       base.mkdir(parents=True, exist_ok=True)
       scratch = base / uuid4().hex
       scratch.mkdir()
       try:
           yield scratch
       finally:
           shutil.rmtree(scratch, ignore_errors=True)
   ```
   **`settings` import MUST be function-local** (design-review): `execution.py` has no
   `the_one.config` import today; a module-level `from the_one.config import settings`
   eagerly instantiates `Settings()` at import and breaks env-monkeypatching tests. Mirror
   the precedent in `tools/connector_send.py` / `tools/connector_history.py` (function-local).
   Add `shutil`, `uuid4`, `contextmanager`, `Iterator` imports as needed.
2. **Branch `ShellTool.execute`** (`shell.py:90-100`): inside the `try`, after
   `_command_check`:
   ```python
   if host_access:
       canonical_cwd = _cwd_check(cwd or str(Path.home()), fs_cfg)
       profile = _build_tool_profile(fs_cfg, exec_cfg)
       env = _build_subprocess_env()
       stdout, stderr, rc = await run_shell(command, timeout=clipped_timeout, env=env, cwd=canonical_cwd, profile=profile)
   else:
       with _ephemeral_box_scratch() as scratch:
           canonical_cwd = _boxed_cwd_check(cwd, scratch)
           profile = _build_boxed_profile(scratch)
           env = _build_subprocess_env(); env["HOME"] = str(scratch)
           stdout, stderr, rc = await run_shell(command, timeout=clipped_timeout, env=env, cwd=canonical_cwd, profile=profile)
   ```
   Keep the `_truncate_output` + the 3-clause except exactly as-is (the boxed `with` block is
   inside the existing `try`, so cleanup + error handling compose). Add `host_access: bool =
   False` to the signature + import `_build_boxed_profile`, `_boxed_cwd_check`,
   `_ephemeral_box_scratch` from `tools.execution`.
3. **Mirror in `PythonExecTool.execute`** (`python_exec.py`) with `run_python`. **Preserve
   `python_exec`'s EXACT existing TimeoutError string** (`"[error] Timed out after {…}s"` —
   no `"Command "` prefix, `python_exec.py:104`); do NOT copy `shell`'s wording. Its
   `Config` is `PythonExecConfig` and the param is `code`, not `command`.
4. **Schema + imports**: add `host_access` (boolean, default false) to both `parameters`
   dicts with a one-line description (leg 5 refines); do NOT mark it required. Add
   `host_access: bool = False` to both `execute` signatures (BEFORE `**kwargs` — the
   dispatcher at `agent/core.py:335` does `execute(**tool_call.arguments)`, so a named param
   before `**kwargs` binds correctly). Import `_build_boxed_profile`, `_boxed_cwd_check`,
   `_ephemeral_box_scratch` from `tools.execution` in both `shell.py` and `python_exec.py`'s
   existing import blocks.
5. Note for leg 4: `shell_session_*` gets the same `host_access` but with **per-session**
   (not per-call) scratch — do not generalize the per-call context manager to sessions here.
6. **`host_access` is the agent's per-call decision (intentional, trust model).** A capable
   agent can set `host_access=true` freely; box-by-default is least-privilege but the model
   is trusted to escalate when it needs host files (leg 5 guidance + leg 6 selection-decision
   test shape the behavior). An operator "force-box / disable escalation" config flag is OUT
   of scope for this flight (a future `ExecutionConfig` knob) — note, don't build.

## Edge Cases

- **Cleanup on exception**: the `with _ephemeral_box_scratch()` guarantees rmtree even if
  `run_shell` raises (the `with` is inside the `try`; `finally` in the CM fires before the
  except clauses format the error). Verify a boxed call that times out still removes scratch.
- **`settings.data_dir/boxes` creation race**: `mkdir(parents=True, exist_ok=True)` on the
  base is safe under concurrency; the per-call `uuid4` subdir is unique.
- **HOME override**: set `env["HOME"]=str(scratch)` on the boxed path so passthrough (no
  `--setenv`) still lands `~` in the scratch (DD5). Bubblewrap overrides from `profile.home`
  anyway — consistent.
- **cwd outside scratch**: `_boxed_cwd_check` raises `ConstraintError` → caught by the
  existing envelope → `[error] [constraint] …`. Good.
- **Do not leak the boxes base**: only the per-call `<uuid>` subdir is removed; the `boxes`
  parent persists (cheap, reused). Acceptable.
- **Orphan-on-crash (design-review)**: `data_dir/"boxes"` lives on the persistent Docker
  volume `the_one_data` (`~/.the-one`). Normal exit cleans up via the CM `finally`, but a
  SIGKILL/OOM mid-call leaves an orphan `boxes/<uuid>` on the volume that accumulates across
  restarts. **Leg 7 (`box-debt-and-docs`) adds a startup-prune of `data_dir/"boxes"`
  orphans** (e.g. at lifespan startup / `ensure_dirs`). Out of scope for this leg beyond the
  per-call cleanup; recorded here so it isn't lost.
- **Test isolation (design-review)**: leg-3 tests drive `ShellTool.execute`/`PythonExecTool.execute`
  which go through `settings.data_dir` — `monkeypatch.setenv("THE_ONE_DATA_DIR", tmp)` (or a
  tmp data_dir) so scratch doesn't land on the real `~/.the-one`; the cleanup AC (scratch
  gone post-call) also guards this.

## Files Affected

- `the_one/tools/execution.py` — `_ephemeral_box_scratch` context manager (+ imports).
- `the_one/tools/shell.py` — `host_access` param + boxed branch.
- `the_one/tools/python_exec.py` — `host_access` param + boxed branch.
- `tests/test_builtin_tool_sandbox.py` (or `tests/test_box_isolation.py`) — boxed one-shot
  `@requires_bwrap` tests + host-mode-unchanged + scratch-cleanup + no-cross-call-state.

---

## Post-Completion Checklist

> **Batched-commit flight**: implement, update the flight log, set leg status to `landed`,
> signal `[HANDOFF:review-needed]`. No commit here.

- [x] All acceptance criteria verified (boxed default + host escalation + cleanup + no cross-call state)
- [x] Host-mode tests unaffected; full suite + ruff green
- [x] Update flight-log.md with this leg's progress entry
- [x] Set this leg's status to `landed` (NOT `completed`)
- [x] Do NOT commit; do NOT check off the leg in flight.md
