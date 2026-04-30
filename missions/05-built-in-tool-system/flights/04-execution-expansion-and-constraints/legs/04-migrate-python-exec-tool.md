# Leg: 04-migrate-python-exec-tool

**Status**: landed
**Flight**: [Execution Expansion & Constraints](../flight.md)

## Objective

Migrate `PythonExecTool` to the F4 constraint surface following L3's pattern: declare `Config = ExecutionConfig`, `Requires = (FilesystemConfig,)`, route through `_command_check` / `_cwd_check` / `_truncate_output` / `_build_subprocess_env`, and clip agent-provided timeouts. Preserve the existing timeout-error wording (`"[error] Timed out after Ns"`) divergence from `ShellTool`. Adopt the `[exit code: N]` suffix that `_truncate_output` provides (deliberate alignment with `ShellTool`; updates one test).

## Context

- **L1a + L1b + L2 + L3 landed** (uncommitted). `_truncate_output` now inserts the `[stderr]` marker; ShellTool migrated to the F4 constraint surface; `run_shell` accepts `cwd`. `run_python` does NOT yet accept `cwd` — same widening needed.
- **F4 Decision 9 (`python_exec` retention + tweaks)**: retained, hardened, default timeout 60s → **90s**, description disambiguated from `shell_session_send`. Module-level denylist (`subprocess`, `os.system`, `socket`) explicitly OUT of scope for F4.
- **Per-tool default-timeout asymmetry**: Decision 1 sub-bullet — single shared `ExecutionConfig` for all execution tools; per-tool default-timeout asymmetry handled by description ("compute work; pass higher `timeout`"). The Config default is `30s`. Decision 9 wants Python's per-tool default at `90s`. Resolution: PythonExecTool subclasses `ExecutionConfig` to override the default field value, OR the Tool overrides the timeout-default lookup at the call site. Pragmatic choice: a tiny `PythonExecConfig(ExecutionConfig)` subclass with one overridden field default, declared `Config = PythonExecConfig`. The resolver's per-key narrowing still works because the overridden field carries the same `Annotated[int, Narrow, Field(...)]` annotation.
  - **Alternative considered**: keep `Config = ExecutionConfig` and ignore the `90s` default — let the agent pass explicit `timeout` for compute-heavy work (the description encourages it). This is simpler but slightly diverges from Decision 9's letter. **Choice for this leg**: subclass approach. The Config divergence is localized and documented; F6 admin UI will surface tool-level defaults per tool, so per-tool subclasses are the natural shape.
- **Two existing behavior divergences** in today's `PythonExecTool` to evaluate:
  - **Timeout-error wording**: today returns `"[error] Timed out after Ns"` (Shell returns `"[error] Command timed out after Ns"`). Test `test_timeout_returns_promptly` asserts the exact Python wording. **PRESERVE** this divergence — it's a deliberate (if minor) tool-identity signal in the error string.
  - **No `[exit code: N]` suffix on non-zero rc**: today's PythonExec discards `_` (the returncode) entirely. Test `test_nonzero_exit_no_exit_code_suffix` asserts `"[exit code" not in result`. **CHANGE** this — `_truncate_output` adds `[exit code: N]` for `rc != 0`, which is more diagnostic and aligns the two execution tools. Update the test to assert `"[exit code: 3]" in result` instead. This is a deliberate F4 alignment, justified by the helper-as-single-source-of-truth design and Decision 9's "constraint surface mostly mirrors `shell`".
- **L1b cross-Config dispatch**: `BuiltinToolProvider` resolves one `cross_configs` view per distinct non-empty Config (insertion-order). With `PythonExecConfig` (a subclass of `ExecutionConfig`), the provider treats it as a DISTINCT Config type — so `cross_configs` will have BOTH `ExecutionConfig` (from `ShellTool`) AND `PythonExecConfig` (from `PythonExecTool`). Both reference the same `_TOOL_CLASSES` insertion-order rows, but the resolver call for each is independent. **This is fine** — agent overrides on either Config are still keyed by tool name in `agent_overrides`. The cross_configs dict carries both entries; tools only consult `cross_configs[FilesystemConfig]` themselves.

## Inputs

- `the_one/tools/execution.py` — `ExecutionConfig`, helpers (post-L3 refined `_truncate_output`).
- `the_one/tools/filesystem.py` — `FilesystemConfig`.
- `the_one/tools/base.py` — `ConstraintError`, `Tool` ABC.
- `the_one/platform/interpreter.py` — `run_python(code, *, timeout, env=None)`. Needs `cwd` widening.
- `the_one/tools/python_exec.py` — current `PythonExecTool` (will be rewritten).
- `tests/test_execution_tools.py::TestPythonExecTool` — five existing tests.

## Outputs

- `the_one/tools/execution.py`:
  - Add `class PythonExecConfig(ExecutionConfig)` with `timeout_seconds_default: Annotated[int, Narrow, Field(...)] = 90` (re-declared with same annotation but `90` default in place of `30`). All other fields inherit from `ExecutionConfig`. `model_config = ConfigDict(frozen=True)` inherits.
  - Verify the `_default_le_max` validator is also inherited and still valid (`90 ≤ 120`). YES — the validator is class-level and runs on any subclass.
- `the_one/tools/python_exec.py`:
  - `PythonExecTool` declares `Config = PythonExecConfig`, `Requires = (FilesystemConfig,)`.
  - `description` updated per Decision 9: `"Execute Python code in a one-shot subprocess. Prefer this over shell for computation, parsing, or any multi-line Python; use shell_session_send for interactive REPL work. Default cwd is $HOME; subprocess environment is a hardcoded minimal allowlist."`
  - `parameters` adds optional `cwd: str` (same description shape as ShellTool).
  - `parameters.timeout.default` removed from JSON Schema (resolver-driven).
  - `execute(code, cwd=None, timeout=None)` rewritten to mirror L3's ShellTool, with these specific differences:
    - `_command_check(code, exec_cfg)` — same denylist (Decision 9 confirms shared denylist; `import subprocess` is NOT denylisted because the subprocess will already be the `_build_subprocess_env`-bound one; module-level Python denylists are out of scope).
    - `await run_python(code, timeout=clipped, env=_build_subprocess_env(), cwd=canonical_cwd)`.
    - `text, _ = _truncate_output(stdout, stderr, returncode, exec_cfg)`. **Important**: today's tool discards returncode (`stdout, stderr, _ = await run_python(...)`); migration captures it for the helper.
    - `except asyncio.TimeoutError: return f"[error] Timed out after {clipped_timeout}s"` (PRESERVES wording divergence — note no `"Command "` prefix).
    - `except ConstraintError`, `except Exception` clauses identical in shape to L3.
- `the_one/platform/interpreter.py`:
  - `run_python` widened to accept `cwd: str | Path | None = None`. Same shape as `run_shell`'s widening: `popen_kwargs["cwd"] = str(cwd) if cwd is not None else (omitted)`.
- `tests/test_execution_tools.py::TestPythonExecTool`:
  - All five existing tests updated to construct `PythonExecTool` with `PythonExecConfig` and `cross_configs={FilesystemConfig: FilesystemConfig()}`.
  - **Test behavior changes**:
    - `test_nonzero_exit_no_exit_code_suffix` → renamed `test_nonzero_exit_appends_exit_code_suffix`, body asserts `"[exit code: 3]" in result` (the new behavior). Old comment "Deliberate divergence — PythonExecTool does NOT append" replaced with "F4 alignment — both Python and Shell now append [exit code: N] for diagnostic clarity."
  - **Seven new tests** for the constraint surface (mirrors L3 ShellTool list, adapted for code argument):
    - `test_denylist_command_refused`: `code="import os; os.system('sudo whoami')"` — but `_command_check` checks `code` for `"sudo "` substring; `os.system('sudo whoami')` contains `"sudo "` → raises ConstraintError. Asserts `[error] [constraint] command contains denylisted token 'sudo '`.
    - `test_cwd_outside_allowlist_refused`: `.execute(code="import os; print(os.getcwd())", cwd="/etc")` → `[error] [constraint]` with `/etc`.
    - `test_cwd_default_is_home`: `.execute(code="import os; print(os.getcwd())")` → equals `str(Path.home())`.
    - `test_timeout_clipped_to_max`: `PythonExecConfig(timeout_seconds_max=2, timeout_seconds_default=2)`, code=`"import time; time.sleep(5)"`, agent passes `timeout=10` → returns `"[error] Timed out after 2s"` (clipped to 2; preserves Python's wording).
    - (Move `test_default_timeout_is_90` to `tests/test_execution_config.py` — it's a Pydantic model unit test, not a tool-execution test. Add a companion test there asserting the inherited cross-field invariant: `PythonExecConfig(timeout_seconds_default=200, timeout_seconds_max=120)` raises. Also assert `PythonExecConfig().command_denylist == ExecutionConfig().command_denylist` (denylist inheritance) and `model_json_schema()` for `timeout_seconds_default` includes `ui_choices` (drift guard).)
    - `test_output_truncated_at_cap`: `PythonExecConfig(output_cap_bytes=1024)`, code=`"for i in range(200): print('line', i)"` → contains `"[... truncated"`.
    - `test_env_allowlist_invariant`: `monkeypatch.setenv("THE_ONE_TEST_LEAK", "secret")` first; then `code=`"import os; print('\\n'.join(f'{k}={v}' for k, v in sorted(os.environ.items())))"` → assert `"THE_ONE_TEST_LEAK"` NOT in keys, `len(keys) > 0`, and `keys.issubset({"PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM", "TZ", "PWD", "_"})` (allow `PWD` because `cwd=` causes the C runtime to set it; allow `_` because exec sometimes injects). The strict-equality assertion is reserved for the actual security invariant — `THE_ONE_TEST_LEAK` absent + subset check is sufficient.
    - `test_constraint_error_two_clause_envelope`: `_command_check` ConstraintError → `[error] [constraint] ...` prefix exactly.
- `tests/test_builtins.py`:
  - Existing tests counting `_TOOL_CLASSES` (currently 13) stay valid — L4 doesn't add a new tool entry.
  - **Update stale comment** in `test_cross_configs_skips_empty_config`: post-L4, only `web` tools (`http_request`, `web_search`) carry `_EmptyConfig`. The comment "(web tools, shell, python_exec in L1b)" is wrong — fix.
  - **Add a positive cross-Config-set assertion test** locking in the post-L4 dispatch shape: a tool from `BuiltinToolProvider({}, {})` has `cross_configs` with EXACTLY these three keys: `{FilesystemConfig, ExecutionConfig, PythonExecConfig}`. Guards against future drift if a new Config sneaks in (or one of these gets removed).
  - **Update `test_python_exec_zero_arg_empty_config`** → rename to `test_python_exec_zero_arg_uses_python_exec_config`; assert `tool._config` is a `PythonExecConfig` instance (not `_EmptyConfig`). Mirror the L3 `test_shell_zero_arg_uses_execution_config`.

## Acceptance Criteria

- [x] `PythonExecTool.Config is PythonExecConfig` and `PythonExecTool.Requires == (FilesystemConfig,)`.
- [x] `PythonExecConfig` is defined as `class PythonExecConfig(ExecutionConfig)` in `the_one/tools/execution.py` with `timeout_seconds_default = 90` (overridden default; `Annotated[int, Narrow, Field(ge=1, le=3600)]` annotation preserved).
- [x] `PythonExecConfig().timeout_seconds_default == 90`; `PythonExecConfig().timeout_seconds_max == 120` (inherited).
- [x] `_default_le_max` cross-field validator inherited; `PythonExecConfig(timeout_seconds_default=200, timeout_seconds_max=120)` raises.
- [x] `PythonExecConfig` is frozen (inherited).
- [x] `PythonExecTool.parameters` includes optional `cwd` (same shape as ShellTool's).
- [x] `PythonExecTool.parameters` no longer carries `timeout.default`.
- [x] `PythonExecTool.description` includes the F4 disambiguation per Decision 9 (mentions one-shot, prefer over shell for compute, refer to `shell_session_send` for REPL).
- [x] `PythonExecTool.execute(code, cwd=None, timeout=None)` calls `_command_check`, `_cwd_check`, `_build_subprocess_env`, `run_python`, `_truncate_output` in that order.
- [x] `run_python` accepts `cwd: str | Path | None = None` (default preserves today's behavior).
- [x] **Timeout wording preserved**: `[error] Timed out after Ns` (NOT `Command timed out`). Pin with test.
- [x] **Exit-code suffix added**: `_truncate_output` appends `[exit code: N]` for `rc != 0`. The previously-asserted-not-present behavior is now asserted-present. Test renamed and rewritten.
- [x] Three-clause try/except envelope: `ConstraintError → asyncio.TimeoutError → Exception` (same as L3).
- [x] Subprocess env is the eight-key allowlist — verified by an end-to-end test in Python (parses `os.environ` from the subprocess's view).
- [x] cwd outside allowlist → `[error] [constraint] ...`.
- [x] Denylisted code → `[error] [constraint] command contains denylisted token '...'`.
- [x] Output exceeding `output_cap_bytes` → tail-preserved with marker.
- [x] `BuiltinToolProvider` constructs `PythonExecTool` with the resolved `PythonExecConfig` and populated `cross_configs[FilesystemConfig]` — no regression in `test_builtins.py`.
- [x] `cross_configs` dict (post-L4) contains BOTH `ExecutionConfig` AND `PythonExecConfig` AND `FilesystemConfig` — three distinct Config types from `_TOOL_CLASSES`.
- [x] Full unit suite green (modulo pre-existing CSS-token red).
- [x] `ruff check` clean on touched files.

## Verification Steps

```bash
# Construction shape
docker exec the-one python -c "
from the_one.tools.python_exec import PythonExecTool
from the_one.tools.execution import PythonExecConfig, ExecutionConfig
from the_one.tools.filesystem import FilesystemConfig
t = PythonExecTool(
    PythonExecConfig(),
    cross_configs={FilesystemConfig: FilesystemConfig()},
    agent_name='test',
)
assert t.Config is PythonExecConfig
assert t.Requires == (FilesystemConfig,)
assert t._config.timeout_seconds_default == 90
assert t._config.timeout_seconds_max == 120
assert isinstance(t._config, ExecutionConfig)  # subclass
print('OK construction')
"

# Env allowlist via subprocess
docker exec the-one python -c "
import asyncio, os
os.environ['THE_ONE_TEST_LEAK'] = 'secret'
from the_one.tools.python_exec import PythonExecTool
from the_one.tools.execution import PythonExecConfig
from the_one.tools.filesystem import FilesystemConfig
async def main():
    t = PythonExecTool(PythonExecConfig(), cross_configs={FilesystemConfig: FilesystemConfig()})
    out = await t.execute(code=\"import os; print('\\\\n'.join(f'{k}={v}' for k,v in sorted(os.environ.items())))\")
    keys = {line.split('=', 1)[0] for line in out.splitlines() if '=' in line}
    expected = {'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TERM', 'TZ'}
    assert 'THE_ONE_TEST_LEAK' not in keys, f'leak: {keys}'
    assert len(keys) > 0, 'empty env'
    assert keys.issubset(expected), f'extras: {keys - expected}'
    print('OK env allowlist')
asyncio.run(main())
"

# Exit code suffix now present (F4 alignment with ShellTool)
docker exec the-one python -c "
import asyncio
from the_one.tools.python_exec import PythonExecTool
from the_one.tools.execution import PythonExecConfig
from the_one.tools.filesystem import FilesystemConfig
async def main():
    t = PythonExecTool(PythonExecConfig(), cross_configs={FilesystemConfig: FilesystemConfig()})
    out = await t.execute(code='import sys; sys.exit(3)')
    assert '[exit code: 3]' in out, out
    print('OK exit code suffix')
asyncio.run(main())
"

# Tests
docker exec the-one pytest tests/test_execution_tools.py tests/test_builtins.py tests/test_factory.py tests/test_execution_helpers.py tests/test_execution_config.py -x -q
docker exec the-one pytest -x -q

# Lint
docker exec the-one ruff check the_one/tools/python_exec.py the_one/tools/execution.py the_one/platform/interpreter.py tests/test_execution_tools.py
```

## Implementation Guidance

1. **Hoist the `timeout_seconds_default` `ui_choices` to a module-level constant** in `the_one/tools/execution.py` (place near the other module-level constants, before `ExecutionConfig`). Pydantic v2 does NOT inherit `json_schema_extra` when a field is re-declared; without re-stating it, `PythonExecConfig` would lose F6 admin UI metadata. The constant lets both Configs reference the same list:

   ```python
   _TIMEOUT_DEFAULT_UI_CHOICES = [
       {"value": 5,   "label": "5s — quick commands only"},
       {"value": 30,  "label": "30s — default (shell)"},
       {"value": 60,  "label": "60s — modest compute"},
       {"value": 90,  "label": "90s — default (python)"},
       {"value": 120, "label": "120s — long jobs"},
       {"value": 300, "label": "5m — extended"},
   ]
   ```

   (Use the existing `ExecutionConfig.timeout_seconds_default` `ui_choices` as the source of truth — extract into the constant and replace the inline list with `_TIMEOUT_DEFAULT_UI_CHOICES`. Whatever values are currently shipped, hoist verbatim.)

2. **Add `PythonExecConfig` subclass** (place AFTER `ExecutionConfig`):

   ```python
   class PythonExecConfig(ExecutionConfig):
       """ExecutionConfig variant with a 90-second default timeout for
       PythonExecTool (F4 Decision 9). Python is more often used for
       compute (numerics, parsing) than shell is; the higher default
       reduces friction for typical workloads. The cap (`timeout_seconds_max`)
       and all other constraints are inherited unchanged.

       Note: with the inherited `timeout_seconds_max=120`, this gives
       agents only 30s of headroom above the new default. Operators
       running heavy compute should also raise `timeout_seconds_max`.
       """

       timeout_seconds_default: Annotated[
           int,
           Narrow,
           Field(
               ge=1,
               le=3600,
               description="Default timeout (PythonExec: 90s vs Shell: 30s).",
               json_schema_extra={
                   "ui_hint": "dropdown",
                   "ui_choices": _TIMEOUT_DEFAULT_UI_CHOICES,
               },
           ),
       ] = 90
   ```

   - `model_config = ConfigDict(frozen=True)` is inherited — no re-declaration needed.
   - The `_default_le_max` validator is inherited — no re-declaration needed.

   - Verify via test that `PythonExecConfig().command_denylist` is still the full denylist (inherited).
   - Verify `PythonExecConfig(timeout_seconds_default=200, timeout_seconds_max=120)` raises (cross-field validator inherited).

2. **Widen `run_python` in `the_one/platform/interpreter.py`** to accept `cwd`:

   ```python
   async def run_python(
       code: str,
       *,
       timeout: float,
       env: dict[str, str] | None = None,
       cwd: str | Path | None = None,
   ) -> tuple[bytes, bytes, int]:
       popen_kwargs: dict[str, object] = {}
       if env is not None:
           popen_kwargs["env"] = env
       if cwd is not None:
           popen_kwargs["cwd"] = str(cwd)
       if os.name == "posix":
           popen_kwargs["start_new_session"] = True
       proc = await asyncio.create_subprocess_exec(
           resolve_python(), "-c", code,
           stdout=asyncio.subprocess.PIPE,
           stderr=asyncio.subprocess.PIPE,
           **popen_kwargs,
       )
       ...
   ```

   - Add `from pathlib import Path` import if absent.

3. **Rewrite `the_one/tools/python_exec.py`** following L3's ShellTool template:

   ```python
   from __future__ import annotations

   import asyncio
   from pathlib import Path
   from typing import Any

   from the_one.platform import run_python
   from the_one.tools.base import ConstraintError, Tool
   from the_one.tools.execution import (
       PythonExecConfig,
       _build_subprocess_env,
       _command_check,
       _cwd_check,
       _truncate_output,
   )
   from the_one.tools.filesystem import FilesystemConfig


   class PythonExecTool(Tool):
       name = "python_exec"
       description = (
           "Execute Python code in a one-shot subprocess. Prefer this over `shell` "
           "for computation, parsing, or any multi-line Python; use `shell_session_send` "
           "for interactive REPL work. Default cwd is $HOME; subprocess environment is a "
           "hardcoded minimal allowlist (no host secrets). Timeout is clipped to the "
           "operator-set max."
       )
       parameters = {
           "type": "object",
           "properties": {
               "code": {"type": "string", "description": "Python code to execute."},
               "cwd": {
                   "type": "string",
                   "description": "Working directory; defaults to $HOME. "
                                  "Refused if outside the path allowlist.",
               },
               "timeout": {
                   "type": "integer",
                   "description": "Timeout in seconds. Uses the resolved default "
                                  "(90s for python_exec) if omitted; clipped to "
                                  "the operator-set max.",
               },
           },
           "required": ["code"],
       }

       Config = PythonExecConfig
       Requires = (FilesystemConfig,)

       async def execute(
           self,
           code: str,
           cwd: str | None = None,
           timeout: int | None = None,
           **kwargs: Any,
       ) -> str:
           exec_cfg: PythonExecConfig = self._config  # type: ignore[assignment]
           fs_cfg: FilesystemConfig = self._cross_configs[FilesystemConfig]  # type: ignore[index]
           if timeout is None:
               clipped_timeout = exec_cfg.timeout_seconds_default
           else:
               clipped_timeout = min(timeout, exec_cfg.timeout_seconds_max)
               if clipped_timeout < 1:
                   clipped_timeout = 1
           try:
               _command_check(code, exec_cfg)
               canonical_cwd = _cwd_check(cwd or str(Path.home()), fs_cfg)
               stdout, stderr, returncode = await run_python(
                   code,
                   timeout=clipped_timeout,
                   env=_build_subprocess_env(),
                   cwd=canonical_cwd,
               )
               text, _ = _truncate_output(stdout, stderr, returncode, exec_cfg)
               return text
           except ConstraintError as e:
               return f"[error] [constraint] {e}"
           except asyncio.TimeoutError:
               return f"[error] Timed out after {clipped_timeout}s"
           except Exception as e:
               return f"[error] {e}"
   ```

4. **Update `tests/test_execution_tools.py::TestPythonExecTool`**:

   - Replace zero-arg `PythonExecTool()` constructions with the F4 shape.
   - Rename `test_nonzero_exit_no_exit_code_suffix` to `test_nonzero_exit_appends_exit_code_suffix` and flip the assertion.
   - Add the seven new constraint-surface tests (see Outputs).
   - Update the timeout test to assert `"[error] Timed out after 0.5s"` (or whatever the clipped value is) — note: the existing test uses `timeout=0.5`, asserts that wording. PRESERVE.
   - Use `Pythonexecconfig` (not `ExecutionConfig`) in test constructions so `Config` matches.

5. **Run full suite + ruff**.

## Edge Cases

- **`code` containing `[stderr]`**: a Python program that prints `[stderr]` literally to stdout would conflict with the new marker convention. The agent receives a single text blob and must rely on visual context. Acceptable; this is a small-model UX cost we accept for unifying the format.
- **`run_python` and shell-injected env vars**: `create_subprocess_exec` doesn't go through a shell, so `PWD`/`SHLVL` aren't shell-injected. But the C runtime may set `PWD` based on `cwd`. Verify in-container; if `PWD` appears, allow it in the env-allowlist test (matches the L3 ShellTool test's posture).
- **Module-level imports inside `code`**: a denylist substring like `"sudo "` matching `import sudoku` is the same false-positive class as ShellTool. The trailing space catches `sudo ` but not `sudoku`. Same trade-off.
- **`os.environ` mutation inside `code`**: the agent could `os.environ["PATH"] = "/sneaky"` inside the subprocess. That mutation is local to the subprocess (since env is passed by value to `create_subprocess_exec`); it does NOT affect the parent agent process. Acceptable.
- **`PythonExecConfig` is a distinct Config type from `ExecutionConfig` in cross_configs**: `BuiltinToolProvider` will resolve BOTH and add both to the dict. `cross_configs[ExecutionConfig]` (from ShellTool's lookup) is the parent class instance; `cross_configs[PythonExecConfig]` (from PythonExecTool's lookup) is the subclass instance. Consumers using `cross_configs[FilesystemConfig]` are unaffected. Tests should not assert exact dict size unless they account for both.

## Files Affected

- `the_one/tools/execution.py` — add `PythonExecConfig` subclass.
- `the_one/tools/python_exec.py` — full rewrite for F4 constraint surface.
- `the_one/platform/interpreter.py` — widen `run_python` to accept `cwd`.
- `tests/test_execution_tools.py` — update `TestPythonExecTool` constructions; rename one test; add 7 new constraint tests.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
