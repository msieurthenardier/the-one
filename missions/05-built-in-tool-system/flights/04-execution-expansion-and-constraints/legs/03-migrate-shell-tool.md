# Leg: 03-migrate-shell-tool

**Status**: landed
**Flight**: [Execution Expansion & Constraints](../flight.md)

## Objective

Migrate `ShellTool` to the F4 constraint surface: declare `Config = ExecutionConfig`, `Requires = (FilesystemConfig,)`, route through `_command_check` / `_cwd_check` / `_truncate_output` / `_build_subprocess_env`, and clip agent-provided timeouts against the resolved cap. Refine `_truncate_output` to insert the `[stderr]\n` marker between stdout and stderr — the existing F1 contract that the test suite asserts.

## Context

- **L1a + L1b + L2 landed** (uncommitted): `ConstraintError` and the widened `Tool.__init__` are in place; `ExecutionConfig` and the four helpers ship in `the_one/tools/execution.py`.
- **Today's `ShellTool`** (`the_one/tools/shell.py`): zero-arg constructible, takes `(command, timeout=120)`, calls `run_shell(command, timeout=timeout)` (no env arg → inherits parent env), formats stderr with `\n[stderr]\n{stderr_decoded}`, appends `[exit code: N]` for `rc != 0`, returns `(no output)` when stripped output is empty, returns `[error] Command timed out after Ns` on timeout.
- **F4 Decisions 1, 2, 3, 7, 10** all converge here:
  - Timeout: clip agent value to `[1, exec_cfg.timeout_seconds_max]`, default to `exec_cfg.timeout_seconds_default` when omitted.
  - Output cap: `_truncate_output` enforces tail-preserving cap.
  - Denylist: `_command_check` enforces substring match.
  - cwd scoping: `_cwd_check` reuses `FilesystemConfig.path_allowlist`/`path_denylist` via `cross_configs`.
  - Subprocess env: `_build_subprocess_env()` provides the hardcoded allowlist; passed via `run_shell(..., env=...)`.
- **`_truncate_output` refinement**: the L2 helper concatenates raw bytes (`stdout + stderr`) without the `[stderr]` marker. Today's ShellTool inserts `\n[stderr]\n{stderr_decoded}` between the streams; existing tests (`tests/test_execution_tools.py::TestShellTool::test_stderr_appended`) assert `"[stderr]" in result`. **L3 refines `_truncate_output` to insert the marker** so the helper remains the single source of truth for output formatting and L4's `PythonExecTool` (which has the same contract) inherits the fix for free. The L2 helper-tests update accordingly.
- **Three-clause `try/except` envelope** (deliberate F4 deviation from F3's two-clause filesystem pattern): F3 has `(ConstraintError, Exception)`; F4 execution tools add `asyncio.TimeoutError` between them because the timeout-message wording (`"[error] Command timed out after Ns"`) is asserted by an existing test (`test_timeout_returns_promptly`). `asyncio.TimeoutError` IS an `Exception` subclass, so order matters: `ConstraintError → asyncio.TimeoutError → Exception`. Document this in the L3 implementation as a deliberate deviation so L4 (PythonExecTool, same pattern) and L6 (pty session tools) follow the same shape.

## Inputs

- `the_one/tools/execution.py` — `ExecutionConfig`, `_command_check`, `_cwd_check`, `_truncate_output`, `_build_subprocess_env`.
- `the_one/tools/filesystem.py` — `FilesystemConfig`.
- `the_one/tools/base.py` — `ConstraintError`, `Tool` ABC with `cross_configs`/`agent_name`.
- `the_one/platform/shell.py` — `run_shell(command, *, timeout, env=None)` returns `(stdout, stderr, returncode)`. The `env` kwarg already exists and accepts a dict-replacement env.
- `the_one/tools/shell.py` — current `ShellTool` (will be rewritten).
- `tests/test_execution_tools.py::TestShellTool` — five existing tests must pass after migration (with construction shape updated).
- `tests/test_execution_helpers.py::TestTruncateOutput` — needs minor update for the `[stderr]` marker.
- `tests/test_builtins.py` — existing tests construct `ShellTool` indirectly via `BuiltinToolProvider`; the L1b change to provider already passes `cross_configs` and `agent_name`, so no test change is needed there for the new constraint surface other than confirming construction still works.

## Outputs

- `the_one/tools/execution.py`:
  - `_truncate_output` updated to insert `\n[stderr]\n{stderr_decoded}` between stdout and stderr when stderr is non-empty. Truncation still applies to the final formatted bytes (drop FRONT, retain LAST cap bytes). Documented in the helper docstring.
- `the_one/tools/shell.py`:
  - `ShellTool` declares `Config = ExecutionConfig`, `Requires = (FilesystemConfig,)`.
  - `description` updated to mention default cwd is `$HOME` and that absolute paths/cwd outside the allowlist are refused.
  - `parameters` adds optional `cwd: str` (description: "Working directory; defaults to $HOME if omitted. Refused if outside the path allowlist.").
  - `parameters.timeout.default` removed from the JSON Schema (the resolver-driven default supersedes it; the description says "uses the resolved default if omitted").
  - `execute(command, cwd=None, timeout=None)` rewritten:
    1. `exec_cfg = self._config` (typed `ExecutionConfig`).
    2. `fs_cfg = self._cross_configs[FilesystemConfig]`.
    3. Two-clause `try/except`:
       - `try`:
         - `_command_check(command, exec_cfg)` — denylist trip → `ConstraintError`.
         - `canonical_cwd = _cwd_check(cwd or str(Path.home()), fs_cfg)` — scope check + dir check.
         - Timeout: `if timeout is None: clipped = exec_cfg.timeout_seconds_default; else: clipped = min(timeout, exec_cfg.timeout_seconds_max); if clipped < 1: clipped = 1`. **Preserves float semantics** — agent passing `timeout=0.5` stays `0.5` (not floored to `1`); agent passing `timeout=0` or negative becomes `1`; agent passing `timeout=999` becomes `exec_cfg.timeout_seconds_max`. The `Field(ge=1)` constraint applies to the Config field only, not the agent kwarg. **Required to preserve** the existing test `test_timeout_returns_promptly` which uses `timeout=0.5` and asserts `"after 0.5s"`.
         - `stdout, stderr, rc = await run_shell(command, timeout=timeout, env=_build_subprocess_env(), cwd=canonical_cwd)`. **Wait** — `run_shell` does NOT currently accept `cwd`. See Implementation Guidance for the resolution.
         - `text, _ = _truncate_output(stdout, stderr, rc, exec_cfg)`; `return text`.
       - `except ConstraintError as e: return f"[error] [constraint] {e}"`.
       - `except asyncio.TimeoutError: return f"[error] Command timed out after {timeout}s"` (preserves the existing wording asserted by tests).
       - `except Exception as e: return f"[error] {e}"`.
- `the_one/platform/shell.py`:
  - `run_shell` widened to accept `cwd: str | Path | None = None`. Passed to `asyncio.create_subprocess_shell(..., cwd=cwd)`. Default `None` preserves today's behavior. F2 contract preserved (env=None still inherits).
- `tests/test_execution_tools.py::TestShellTool`:
  - All five existing tests updated to construct `ShellTool` with `ExecutionConfig` and `cross_configs={FilesystemConfig: FilesystemConfig()}`. (Today they call `ShellTool()` zero-arg.)
  - The shape required: `ShellTool(ExecutionConfig(), cross_configs={FilesystemConfig: FilesystemConfig()})`.
  - **Seven** new tests for the constraint surface:
    - `test_denylist_command_refused`: `ShellTool(ExecutionConfig(), cross_configs=...).execute(command="sudo whoami")` → `"[error] [constraint] command contains denylisted token 'sudo '"`.
    - `test_cwd_outside_allowlist_refused`: `.execute(command="ls", cwd="/etc")` → `"[error] [constraint] path '/etc' inside denylist '/etc'"` (or whichever the canonical message is — assert `"[error] [constraint]"` and `"/etc"` both present).
    - `test_cwd_default_is_home`: `.execute(command="pwd")` → output equals `str(Path.home())`.
    - `test_timeout_clipped_to_max`: with an `ExecutionConfig(timeout_seconds_max=2)`, `.execute(command="sleep 5", timeout=10)` returns `"[error] Command timed out after 2s"` (clipped from 10 to 2).
    - `test_output_truncated_at_cap`: with `ExecutionConfig(output_cap_bytes=1024)`, `.execute(command='for i in $(seq 1 200); do echo "line $i"; done')` returns text containing `[... truncated`.
    - `test_env_allowlist_invariant`: `.execute(command="env")` → output keys (after parsing) ⊆ `{PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ}`. Test must `monkeypatch.setenv("THE_ONE_TEST_LEAK", "secret")` first; assert `"THE_ONE_TEST_LEAK"` NOT in output. **Also assert `len(keys) > 0`** — guards against an empty-env false-pass where `set().issubset(expected)` is vacuously True.
    - `test_constraint_error_two_clause_envelope`: assert that `ConstraintError` raised inside `execute` produces the `"[error] [constraint] ..."` prefix exactly (not `"[error] ..."`).
- `tests/test_execution_helpers.py::TestTruncateOutput`:
  - **Tests that pass UNCHANGED post-refinement** (stderr is empty in these cases):
    - `test_below_cap_success` (stderr=`b""`)
    - `test_below_cap_failure_appends_exit_suffix` (stderr=`b""`, rc=1) — `(b"oops", b"", 1, cfg) → "oops\n[exit code: 1]"` still holds.
    - `test_above_cap_tail_preserved` (stderr=`b""`, large stdout) — math unchanged because `combined = stdout` when stderr is empty.
    - `test_empty_input_zero_rc` and `test_empty_input_nonzero_rc` (both pipes empty).
  - **Tests that need RECOMPUTE**:
    - `test_below_cap_with_stderr` (stdout=`b"hi"`, stderr=`b"warn"`): currently asserts `"hi" in text and "warn" in text`. Update to also assert the precise marker boundary `"hi\n[stderr]\nwarn"` substring or `"\n[stderr]\n"` literal substring.
    - `test_combined_cap_uses_concatenated_tail` (e.g., `stdout=b"X"*700`, `stderr=b"Y"*700`, cap=1024): under refinement, `combined = b"X"*700 + b"\n[stderr]\n"(10) + b"Y"*700 = 1410 bytes`, not 1400. Tail of 1024 bytes from a 1410-byte combined: drop FRONT 386 bytes (chops the leading `X`s), tail starts at byte 386 → `b"X"*314 + b"\n[stderr]\n" + b"Y"*700` (= 1024 bytes). Assertion must match this — including the embedded `\n[stderr]\n` marker now appearing in the truncated tail. Recompute the exact expected substring.
  - **New tests** to add:
    - `test_no_stderr_marker_when_stderr_empty`: stdout=`b"out"`, stderr=`b""` → `"[stderr]" not in text`.
    - `test_stderr_marker_inside_tail_when_truncated`: a small cap (1024) plus stdout/stderr combo where the marker survives in the tail. Pin the byte math.

## Acceptance Criteria

- [x] `ShellTool.Config is ExecutionConfig` and `ShellTool.Requires == (FilesystemConfig,)`.
- [x] `ShellTool.parameters` includes `cwd` (optional string) with a description mentioning `$HOME` default and allowlist enforcement.
- [x] `ShellTool.execute(command, cwd=None, timeout=None)` calls `_command_check`, `_cwd_check`, `_build_subprocess_env`, `run_shell(...)`, `_truncate_output` in that order.
- [x] `run_shell` accepts a `cwd: str | Path | None = None` kwarg (default preserves today's no-cwd behavior).
- [x] Subprocess env is the eight-key allowlist — verified by an end-to-end `ShellTool.execute(command="env")` test.
- [x] Timeout omitted by agent → uses `exec_cfg.timeout_seconds_default`.
- [x] Timeout > `exec_cfg.timeout_seconds_max` → clipped to max (no `ConstraintError`; clip is silent per Decision 1's "default-and-clip" intent).
- [x] cwd outside allowlist → `[error] [constraint] ...` (NOT `[error] ...`).
- [x] Denylisted command → `[error] [constraint] command contains denylisted token '...'`.
- [x] Output exceeding `exec_cfg.output_cap_bytes` → tail-preserved with marker line.
- [x] `_truncate_output` inserts `\n[stderr]\n{stderr_decoded}` between stdout and stderr when stderr is non-empty (single-source-of-truth helper now matches the existing `[stderr]` contract).
- [x] Existing `tests/test_execution_tools.py::TestShellTool` tests pass after construction shape update — `(no output)`, `[stderr]`, `[exit code: 7]`, timeout-prompt-return all preserved.
- [x] Existing `tests/test_execution_helpers.py::TestTruncateOutput` stderr tests updated to assert the marker; all pass.
- [x] Two-clause envelope intact: `ConstraintError → [error] [constraint] ...`; other `Exception → [error] {e}`; `asyncio.TimeoutError → [error] Command timed out after Ns`.
- [x] `BuiltinToolProvider().get_tools({}, {}, agent_name="x")` constructs `ShellTool` with the resolved `ExecutionConfig` and `cross_configs[FilesystemConfig]` populated — no regression in `tests/test_builtins.py`.
- [x] `make test-unit` (full suite) green modulo the pre-existing CSS-token red.
- [x] `ruff check the_one/ tests/` clean on touched files.

## Verification Steps

```bash
# Construction shape post-migration
docker exec the-one python -c "
from the_one.tools.shell import ShellTool
from the_one.tools.execution import ExecutionConfig
from the_one.tools.filesystem import FilesystemConfig
t = ShellTool(ExecutionConfig(), cross_configs={FilesystemConfig: FilesystemConfig()}, agent_name='test')
assert t.Config is ExecutionConfig
assert t.Requires == (FilesystemConfig,)
print('OK construction')
"

# Env allowlist invariant via the actual tool
docker exec the-one python -c "
import asyncio, os
os.environ['THE_ONE_TEST_LEAK'] = 'secret'
from the_one.tools.shell import ShellTool
from the_one.tools.execution import ExecutionConfig
from the_one.tools.filesystem import FilesystemConfig
async def main():
    t = ShellTool(ExecutionConfig(), cross_configs={FilesystemConfig: FilesystemConfig()})
    out = await t.execute(command='env')
    keys = {line.split('=', 1)[0] for line in out.splitlines() if '=' in line}
    expected = {'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TERM', 'TZ'}
    assert 'THE_ONE_TEST_LEAK' not in keys, f'leak: {keys}'
    assert keys.issubset(expected), f'extras: {keys - expected}'
    print('OK env allowlist')
asyncio.run(main())
"

# Denylist trip
docker exec the-one python -c "
import asyncio
from the_one.tools.shell import ShellTool
from the_one.tools.execution import ExecutionConfig
from the_one.tools.filesystem import FilesystemConfig
async def main():
    t = ShellTool(ExecutionConfig(), cross_configs={FilesystemConfig: FilesystemConfig()})
    out = await t.execute(command='sudo whoami')
    assert out.startswith('[error] [constraint]'), out
    assert \"'sudo '\" in out, out
    print('OK denylist')
asyncio.run(main())
"

# cwd default is HOME; out-of-scope is refused
docker exec the-one python -c "
import asyncio, os
from the_one.tools.shell import ShellTool
from the_one.tools.execution import ExecutionConfig
from the_one.tools.filesystem import FilesystemConfig
async def main():
    t = ShellTool(ExecutionConfig(), cross_configs={FilesystemConfig: FilesystemConfig()})
    pwd = await t.execute(command='pwd')
    assert pwd == os.path.expanduser('~'), pwd
    refused = await t.execute(command='ls', cwd='/etc')
    assert refused.startswith('[error] [constraint]'), refused
    print('OK cwd')
asyncio.run(main())
"

# Test suite
docker exec the-one pytest tests/test_execution_tools.py tests/test_execution_helpers.py tests/test_builtins.py tests/test_factory.py -x -q
docker exec the-one pytest -x -q

# Lint
docker exec the-one ruff check the_one/tools/shell.py the_one/tools/execution.py the_one/platform/shell.py tests/test_execution_tools.py tests/test_execution_helpers.py
```

## Implementation Guidance

1. **Refine `_truncate_output` (in `the_one/tools/execution.py`)** to insert the `[stderr]` marker:

   ```python
   def _truncate_output(stdout, stderr, returncode, cfg):
       if stderr:
           combined = stdout + b"\n[stderr]\n" + stderr
       else:
           combined = stdout
       cap = cfg.output_cap_bytes
       was_truncated = False
       if len(combined) > cap:
           dropped = len(combined) - cap
           tail = combined[-cap:]
           marker = (
               f"[... truncated {dropped} bytes; showing last {cap} bytes "
               f"of combined stdout+stderr ...]\n"
           )
           text = marker + tail.decode(errors="replace")
           was_truncated = True
       else:
           text = combined.decode(errors="replace")
       if returncode != 0:
           text += f"\n[exit code: {returncode}]"
       text = text.strip() or "(no output)"
       return text, was_truncated
   ```

   - **Update the helper's docstring** to distinguish the two markers:
     - **`\n[stderr]\n` marker** (NEW in L3) — inserted between stdout and stderr BEFORE capping. Marker bytes ARE part of `combined` and ARE counted against `cfg.output_cap_bytes`. Tail-preserving may chop into or past this marker.
     - **Truncation marker `[... truncated N bytes; ...]\n`** (existing) — prepended AFTER capping. NOT counted against the cap (intentional per F4 Decision 2 — cap is a "shape the agent's view" knob, not a hard byte budget). Returned text length can exceed `cap` by ~80 chars.
   - **Edge**: `b"\n[stderr]\n"` is 10 bytes. With a tiny cap (e.g., 1024) and tiny stdout/stderr, the marker will appear in the tail intact. With a bursting stderr, the marker may be at or before the truncation point — that's fine; tail-preserving means we may chop into the marker. Acceptable.

2. **Update `tests/test_execution_helpers.py::TestTruncateOutput`**:

   - The existing `with-stderr` below-cap test now asserts `"[stderr]" in text` and the precise `"\n[stderr]\n"` boundary.
   - The existing combined-cap test (`stdout=b"X"*N, stderr=b"Y"*M`) needs adjustment — `combined` is now `stdout + b"\n[stderr]\n" + stderr`. Recompute the assertion to match the new combined length.
   - Add a no-stderr-no-marker test: `stderr=b""` → no `[stderr]` substring in output.

3. **Widen `run_shell` in `the_one/platform/shell.py`** to accept `cwd`:

   ```python
   async def run_shell(
       command: str,
       *,
       timeout: float,
       env: dict[str, str] | None = None,
       cwd: str | Path | None = None,
   ) -> tuple[bytes, bytes, int]:
       ...
       popen_kwargs: dict[str, object] = {}
       if env is not None:
           popen_kwargs["env"] = env
       if cwd is not None:
           popen_kwargs["cwd"] = str(cwd)
       if os.name == "posix":
           popen_kwargs["start_new_session"] = True
       proc = await asyncio.create_subprocess_shell(
           command,
           stdout=asyncio.subprocess.PIPE,
           stderr=asyncio.subprocess.PIPE,
           **popen_kwargs,
       )
       ...
   ```

   - Default `cwd=None` preserves today's behavior (subprocess inherits the parent's cwd).
   - The `str(cwd)` conversion is necessary for Windows compatibility — `asyncio.create_subprocess_shell` accepts both, but Path → str is the safe default.

4. **Rewrite `the_one/tools/shell.py`**:

   ```python
   from __future__ import annotations

   import asyncio
   from pathlib import Path
   from typing import Any

   from the_one.platform import run_shell
   from the_one.tools.base import ConstraintError, Tool
   from the_one.tools.execution import (
       ExecutionConfig,
       _build_subprocess_env,
       _command_check,
       _cwd_check,
       _truncate_output,
   )
   from the_one.tools.filesystem import FilesystemConfig


   class ShellTool(Tool):
       name = "shell"
       description = (
           "Execute a shell command and return its output. Default cwd is $HOME; "
           "the cwd argument may narrow to any directory inside the path allowlist. "
           "Subprocess environment is a hardcoded minimal allowlist (no host secrets). "
           "Timeout is clipped to the operator-set max."
       )
       parameters = {
           "type": "object",
           "properties": {
               "command": {"type": "string", "description": "The shell command to execute."},
               "cwd": {
                   "type": "string",
                   "description": "Working directory; defaults to $HOME. "
                                  "Refused if outside the path allowlist.",
               },
               "timeout": {
                   "type": "integer",
                   "description": "Timeout in seconds. Uses the resolved default if omitted; "
                                  "clipped to the operator-set max.",
               },
           },
           "required": ["command"],
       }

       Config = ExecutionConfig
       Requires = (FilesystemConfig,)

       async def execute(
           self,
           command: str,
           cwd: str | None = None,
           timeout: int | None = None,
           **kwargs: Any,
       ) -> str:
           exec_cfg: ExecutionConfig = self._config  # type: ignore[assignment]
           fs_cfg: FilesystemConfig = self._cross_configs[FilesystemConfig]  # type: ignore[index]
           if timeout is None:
               clipped_timeout = exec_cfg.timeout_seconds_default
           else:
               clipped_timeout = min(timeout, exec_cfg.timeout_seconds_max)
               if clipped_timeout < 1:
                   clipped_timeout = 1
           # NB: float-preserving — agent passing `timeout=0.5` keeps 0.5;
           # only sub-1 values (incl. 0/negative) get floored to 1. The
           # `Field(ge=1)` constraint on the Config field doesn't apply
           # to the agent kwarg.
           try:
               _command_check(command, exec_cfg)
               canonical_cwd = _cwd_check(cwd or str(Path.home()), fs_cfg)
               stdout, stderr, returncode = await run_shell(
                   command,
                   timeout=clipped_timeout,
                   env=_build_subprocess_env(),
                   cwd=canonical_cwd,
               )
               text, _ = _truncate_output(stdout, stderr, returncode, exec_cfg)
               return text
           except ConstraintError as e:
               return f"[error] [constraint] {e}"
           except asyncio.TimeoutError:
               return f"[error] Command timed out after {clipped_timeout}s"
           except Exception as e:
               return f"[error] {e}"
   ```

   - Note `clipped_timeout` is computed BEFORE the `try` so the timeout-error message uses the clipped value (matches Decision 1's "agent passing 999 → clipped to 120 → timeout message says 120s").
   - The two-clause envelope (`ConstraintError` first, then generic `Exception`) matches the F3 filesystem pattern.

5. **Update `tests/test_execution_tools.py::TestShellTool`** — replace zero-arg `ShellTool()` constructions with the new shape, add the seven new tests listed in Outputs.

   - Tests construct with: `ShellTool(ExecutionConfig(), cross_configs={FilesystemConfig: FilesystemConfig()})`.
   - For tests that need a tighter cap or shorter timeout, construct with `ExecutionConfig(output_cap_bytes=1024)` or `ExecutionConfig(timeout_seconds_max=2, timeout_seconds_default=2)` (must satisfy the `default ≤ max` invariant).
   - For the env-allowlist test, use `monkeypatch.setenv("THE_ONE_TEST_LEAK", "secret")` so the test is hermetic.
   - For the cwd test, `Path.home()` resolves to the container's `$HOME` (typically `/root` for the dev container). Verify by reading `os.path.expanduser('~')` in the test.

6. **Run full test suite + ruff**.

## Edge Cases

- **`cwd="."`**: relative cwd. `_filesystem_check` canonicalizes via `Path.resolve()` which expands `.` against the FastAPI process's CWD (typically `/app` in the dev container, NOT in the default `path_allowlist=["~"]`). Result: `cwd="."` is **refused by default** in the container. Add a test `test_relative_cwd_refused_when_outside_allowlist` pinning this behavior. Operator can broaden the allowlist if they want `.`-style relative cwds; document in the ShellTool description that "absolute paths are recommended; relative paths resolve against the agent server's CWD."
- **Agent passes `cwd=` with a trailing slash or `~/...`**: `_filesystem_check` canonicalizes (expands `~`, normalizes), so both work consistently.
- **Agent passes `timeout=0` or negative**: `max(1, min(timeout, max))` floors to 1. Acceptable; the agent gets a 1-second timeout. Could refine to `[error] [constraint] timeout must be >= 1`, but silent clipping is consistent with Decision 1's "agent value clipped" framing.
- **`Path.home()` on the dev container**: typically `/root`. The default `FilesystemConfig.path_allowlist=["~"]` canonicalizes to `/root` in the container, so `cwd=Path.home()` always satisfies the allowlist. If a test runs as a different user, `~` still resolves correctly.
- **Container `$HOME` differs from operator's host `$HOME`**: this is intrinsic to the dev container; tests run inside the container with `/root` as `$HOME`. No special handling.
- **`run_shell` timeout subtype**: `asyncio.TimeoutError` is the helper's failure mode. `_command_check` and `_cwd_check` raise `ConstraintError` BEFORE `run_shell` is called — the timeout clause handles only the post-launch timeout.
- **Subprocess inherits cwd from parent if `cwd=None`**: the L3 ShellTool always passes `cwd=canonical_cwd` (never None). `run_shell`'s `cwd=None` default is for future callers (and back-compat for any test that calls `run_shell` directly without cwd).
- **F3 filesystem tools' tests use `BuiltinToolProvider`**: those tests should continue working — L1b's provider already passes `cross_configs` and `agent_name`. New L3 tests construct `ShellTool` directly to test the constraint surface in isolation.
- **`PythonExecTool` is NOT migrated in this leg**. L4 covers it. L4 inherits the `_truncate_output` refinement (the `[stderr]` marker) for free — confirms the helper-as-single-source-of-truth design.

## Files Affected

- `the_one/tools/execution.py` — refine `_truncate_output` to insert `[stderr]` marker.
- `the_one/tools/shell.py` — full rewrite for the F4 constraint surface.
- `the_one/platform/shell.py` — widen `run_shell` to accept `cwd`.
- `tests/test_execution_tools.py` — update `TestShellTool` constructions; add 7 new constraint tests.
- `tests/test_execution_helpers.py` — update `TestTruncateOutput` tests for the `[stderr]` marker; add no-marker-when-empty test.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
