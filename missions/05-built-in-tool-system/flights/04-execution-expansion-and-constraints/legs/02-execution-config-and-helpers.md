# Leg: 02-execution-config-and-helpers

**Status**: landed
**Flight**: [Execution Expansion & Constraints](../flight.md)

## Objective

Define `ExecutionConfig` Pydantic model in a new `the_one/tools/execution.py` module along with the four module-level helpers (`_command_check`, `_cwd_check`, `_truncate_output`, `_build_subprocess_env`) that L3-L6 will call. No tool wiring in this leg — pure scaffolding with full unit coverage.

## Context

- **L1a + L1b landed** (uncommitted): `ConstraintError` lives in `the_one/tools/base.py`; `Tool` ABC takes `cross_configs` + `agent_name`; `FilesystemConfig` is frozen.
- **F4 Decisions 1, 2, 3, 5, 7, 10**: this leg materializes `ExecutionConfig` with **six** Narrow/NarrowSuperset fields (`timeout_seconds_default`, `timeout_seconds_max`, `output_cap_bytes`, `command_denylist`, `pty_session_idle_ttl_seconds`, `max_concurrent_sessions`), a `model_validator(mode="after")` cross-field invariant `default ≤ max`, and `frozen=True`. The constants `DEFAULT_COMMAND_DENYLIST` and `_ENV_ALLOWLIST` are defined here.
- **F4 Decision 7 (cross-Config dispatch)**: `_cwd_check` takes a `FilesystemConfig` arg and reuses `_filesystem_check` from `filesystem.py` — single source of truth for "is this path in scope?" Same `[constraint]` error surface as filesystem tools.
- **F4 Decision 2 (truncation)**: `_truncate_output` returns `tuple[str, bool]` — formatted text + `was_truncated` bool. Tail-preserving (drop FRONT, retain LAST cap bytes). Build/test output puts the actionable signal at the end. Marker line: `[... truncated N bytes; showing last M bytes of combined stdout+stderr ...]`.
- **F4 Decision 3 (denylist)**: substring match with trailing-space convention to avoid the `sudoku` false positive class. `command_denylist: Annotated[list[str], NarrowSuperset]`.
- **F4 Decision 10 (env allowlist)**: `_build_subprocess_env()` returns a dict containing only the eight allowlisted keys present in `os.environ`. The allowlist is a hardcoded module-level constant — NOT operator-configurable.
- **No tool changes in this leg**. L3 wires `ShellTool`; L4 wires `PythonExecTool`; L6 wires the four pty session tools. This leg only ships the contract and the helpers.

## Inputs

- `the_one/tools/base.py` — `ConstraintError` and `Tool` (post-L1a/L1b).
- `the_one/tools/filesystem.py` — `FilesystemConfig` (frozen, post-L1b) and `_filesystem_check(path, fs_cfg) -> Path` for `_cwd_check` to delegate to.
- `the_one/tools/resolver.py` — `Narrow` and `NarrowSuperset` markers; `_check_narrow` (used implicitly by the resolver, not directly by this leg).
- Pydantic v2 with `BaseModel`, `Field`, `ConfigDict`, `model_validator`.

## Outputs

- `the_one/tools/execution.py` (NEW file):
  - `_ENV_ALLOWLIST: tuple[str, ...]` constant (8 entries: `PATH`, `HOME`, `USER`, `LOGNAME`, `LANG`, `LC_ALL`, `TERM`, `TZ`).
  - `DEFAULT_COMMAND_DENYLIST: tuple[str, ...]` constant (per Decision 3 list).
  - `class ExecutionConfig(BaseModel)`:
    - `model_config = ConfigDict(frozen=True)`.
    - Fields: `timeout_seconds_default`, `timeout_seconds_max`, `output_cap_bytes`, `command_denylist`, `pty_session_idle_ttl_seconds`, `max_concurrent_sessions` (all `Annotated[..., Narrow]` or `NarrowSuperset` with `Field(...)` describing bounds + `json_schema_extra={"ui_hint": "dropdown", "ui_choices": [...]}` per Decisions 1/2/5).
    - `@model_validator(mode="after")` `_default_le_max` enforcing `timeout_seconds_default ≤ timeout_seconds_max`.
  - `def _command_check(command: str, cfg: ExecutionConfig) -> None` — raises `ConstraintError` if any token in `cfg.command_denylist` is a substring of `command`.
  - `def _cwd_check(cwd: str | Path, fs_cfg: FilesystemConfig) -> Path` — delegates to `_filesystem_check(cwd, fs_cfg)`, then asserts result is a directory; raises `ConstraintError` otherwise.
  - `def _truncate_output(stdout: bytes, stderr: bytes, returncode: int, cfg: ExecutionConfig) -> tuple[str, bool]` — combine stdout + stderr, decode with `errors="replace"`, tail-preserve the last `cfg.output_cap_bytes` bytes (drop front), prepend truncation marker if truncated, append `[exit code: N]` if `returncode != 0`. Return `(text, was_truncated)`.
  - `def _build_subprocess_env() -> dict[str, str]` — return `{k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}`.
- `tests/test_execution_config.py` (NEW file):
  - Default-construction test (all fields take their declared defaults).
  - Each field's `Field(ge=..., le=...)` bound enforced (Pydantic raises `ValidationError`).
  - `_default_le_max` invariant: constructing with `default > max` raises; equal succeeds; less succeeds.
  - `frozen=True` — attribute assignment raises `pydantic.ValidationError`.
  - **`command_denylist` default-factory returns a list** (NOT tuple): `assert isinstance(ExecutionConfig().command_denylist, list)`.
  - **`command_denylist` Pydantic coercion**: `ExecutionConfig(command_denylist=("a", "b")).command_denylist == ["a", "b"]` and is a list.
  - **Resolver default-factory fallback path** for `command_denylist`: when `tool_config` omits the key (e.g. `{}` or `None`), the resolver's `merged.get(key, field_info.default)` returns `field_info.default`, which for default-factory fields is `PydanticUndefined`. The implementer must verify what the resolver actually does in this case (probably raises `NotImplementedError` from `_check_narrow_superset` because `PydanticUndefined` isn't a list). **Test contract**: pass an explicit `tool_config={"command_denylist": list(DEFAULT_COMMAND_DENYLIST)}` for any narrowing test on this field — never rely on the default-factory fallback through the resolver. If you discover the resolver handles `PydanticUndefined` gracefully (unlikely), document the actual behavior in the flight log instead. This limitation only affects the cross-Config dispatch path: in production, `BuiltinToolProvider` always passes the operator's stored `tool_configs` row; if the operator hasn't set one, `tool_configs.get(name)` returns `None`, the resolver's `merged = dict(tool_config or {})` becomes `{}`, and the agent override path on `command_denylist` fails. **Real-world impact is low**: a tool ships defaults; an operator setting agent overrides on `command_denylist` should also set the tool-level row. Document and move on.
  - Resolver-narrowing per field (use `the_one.tools.resolver.resolve(ExecutionConfig, tool_dict, agent_dict)` and assert narrowing succeeds, widening raises `ValueError`):
    - `timeout_seconds_default` (Narrow int): tool=30, agent=10 narrows; agent=60 raises.
    - `timeout_seconds_max` (Narrow int): tool=120, agent=60 narrows; agent=180 raises.
    - `output_cap_bytes` (Narrow int): tool=262144, agent=65536 narrows; agent=524288 raises.
    - `command_denylist` (NarrowSuperset list): tool=`["sudo "]`, agent=`["sudo ", "rm -rf"]` narrows; agent=`["rm -rf"]` (missing tool entry) raises.
    - `pty_session_idle_ttl_seconds` (Narrow int): tool=300, agent=60 narrows; agent=600 raises.
    - `max_concurrent_sessions` (Narrow int): tool=5, agent=3 narrows; agent=10 raises.
  - Cross-field invariant interacts correctly with narrowing: tool `default=30, max=120`; agent narrows `max=20`. Per the resolver's order (per-key dispatch then `model_validate`), `max_after_narrow=20 < default=30` triggers `_default_le_max` → `ValueError`. Test asserts this is caught (this is the documented "agent can't widen `default` past a narrowed `max`" guarantee from Decision 1).
- `tests/test_execution_helpers.py` (NEW file):
  - `_command_check`:
    - Empty denylist → never raises.
    - `command="ls"`, denylist=`["sudo "]` → no raise.
    - `command="sudoku"`, denylist=`["sudo "]` → NO raise (trailing-space convention works).
    - `command="sudo whoami"`, denylist=`["sudo "]` → raises `ConstraintError` with `"command contains denylisted token 'sudo '"`.
    - `command='bash -c "sudo whoami"'`, denylist=`["sudo "]` → RAISES (substring catches the wrapped form per Decision 3 rationale).
    - Multiple denylist entries: first match wins; error message names the matched token.
  - `_cwd_check`:
    - `cwd="~"` with default FilesystemConfig (allowlist=`["~"]`) → returns canonical Path equal to `Path.home()`.
    - `cwd="/etc"` with default FilesystemConfig → raises `ConstraintError` (matches the `_filesystem_check` denylist hit, since `/etc` is in `DEFAULT_PATH_DENYLIST`).
    - `cwd=` pointing at an existing FILE (not a directory) inside the allowlist → raises `ConstraintError` with `"is not a directory"`.
    - `cwd=` pointing at a nonexistent path inside the allowlist → raises `ConstraintError` with `"does not exist or is not a directory"` (`Path.is_dir()` returns False for both nonexistent and non-directory paths; combine in error message for small-model clarity).
  - `_truncate_output`:
    - Below cap, success: stdout=`b"hello"`, stderr=`b""`, rc=0, cap=1024 → returns `("hello", False)`.
    - Below cap, success with stderr: stdout=`b"hi"`, stderr=`b"warn"`, rc=0 → both present in output, no `[exit code]` since rc=0, returns `(..., False)`.
    - Below cap, failure: rc=1 → output ends with `\n[exit code: 1]`.
    - Above cap, tail-preserved: stdout=`b"A" * 2000`, stderr=`b""`, cap=512 → returns `(text, True)` where text starts with the truncation marker `[... truncated 1488 bytes; showing last 512 bytes of combined stdout+stderr ...]\n` and ends with the LAST 512 `A` characters.
    - Above cap with non-zero exit: text contains `[exit code: 1]` AFTER the truncated tail.
    - Combined cap (stdout + stderr together): stdout=`b"X" * 300`, stderr=`b"Y" * 300`, cap=512 → tail preserves the LAST 512 bytes of `stdout + stderr` concatenated.
    - Empty output: stdout=`b""`, stderr=`b""`, rc=0 → returns `("(no output)", False)` to match existing ShellTool conventions (this matches today's ShellTool).
  - `_build_subprocess_env`:
    - Returns dict with only allowlisted keys present in current `os.environ`.
    - Dummy variable `THE_ONE_TEST_LEAK=secret` set via `monkeypatch.setenv` → not in returned dict.
    - All eight allowlisted keys ARE in dict if present in environ (verify with `monkeypatch.setenv("LANG", "C.UTF-8")`).
    - Missing allowlist key (e.g., `monkeypatch.delenv("TZ", raising=False)`) → key absent from returned dict (no KeyError).

## Acceptance Criteria

- [x] `the_one/tools/execution.py` exists with the constants, `ExecutionConfig`, and four helpers as described.
- [x] `_ENV_ALLOWLIST == ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM", "TZ")` (exact tuple).
- [x] `DEFAULT_COMMAND_DENYLIST` matches Decision 3's list verbatim — including the trailing-space convention on `"sudo "`, `"su "`, `"doas "`.
- [x] `ExecutionConfig` is frozen — mutation raises `pydantic.ValidationError`.
- [x] `ExecutionConfig` declares all six Narrow/NarrowSuperset fields per Decisions 1, 2, 3, 5 with their declared defaults: `timeout_seconds_default=30`, `timeout_seconds_max=120`, `output_cap_bytes=262_144`, `command_denylist=Field(default_factory=lambda: list(DEFAULT_COMMAND_DENYLIST))` (default-factory returns a `list`, NOT the underlying tuple — required because the resolver's `_check_narrow_superset` uses `isinstance(tool_val, list)`), `pty_session_idle_ttl_seconds=300`, `max_concurrent_sessions=5`.
- [x] `ExecutionConfig().command_denylist` is a `list[str]` instance (proves Pydantic stored the default as a list, not a tuple).
- [x] `ExecutionConfig(command_denylist=("a", "b")).command_denylist == ["a", "b"]` and `isinstance(..., list)` (Pydantic coerces tuple input to list per the `list[str]` annotation).
- [x] All bound `Field(ge=, le=)` constraints on each field work (Pydantic raises `ValidationError` for out-of-bound construction).
- [x] All Narrow/NarrowSuperset fields have `json_schema_extra={"ui_hint": "dropdown", "ui_choices": [...]}` per Decisions 1, 2, 3, 5 (F6 admin UI consumes this; this leg ships the metadata).
- [x] `_default_le_max` `model_validator(mode="after")` raises when `timeout_seconds_default > timeout_seconds_max`.
- [x] Resolver narrowing works for each Narrow field: agent value `<= tool` succeeds, `> tool` raises.
- [x] Resolver narrowing works for `command_denylist` (NarrowSuperset semantics: agent must contain every tool entry).
- [x] Cross-field invariant survives narrowing: agent narrowing `max` below `default` raises `ValueError` from Pydantic (caught by the resolver as part of `model_validate`).
- [x] `_command_check` substring match works (including the wrapped-bash case `bash -c "sudo ..."`).
- [x] `_command_check` rejects `"sudoku"` ⇒ no raise (trailing-space catches `sudo` correctly).
- [x] `_command_check` error message format: `command contains denylisted token '{token}'`.
- [x] `_cwd_check` returns a canonical `Path` when in scope and is a directory; raises `ConstraintError` with `"does not exist or is not a directory"` when path is in-scope but `Path.is_dir()` is False; delegates allowlist/denylist check to `_filesystem_check`.
- [x] `_truncate_output` returns `tuple[str, bool]`; tail-preserving truncation; combined cap; exit code suffix when `rc != 0`; empty input returns `"(no output)"`.
- [x] `_truncate_output` truncation marker is `[... truncated N bytes; showing last M bytes of combined stdout+stderr ...]\n` exactly.
- [x] `_build_subprocess_env` returns ONLY allowlisted keys present in `os.environ`; never raises on missing keys.
- [x] All new tests pass.
- [x] No existing tests regress: `docker exec the-one pytest -x -q` is green (modulo the pre-existing CSS-token red).
- [x] `ruff check the_one/tools/execution.py tests/test_execution_config.py tests/test_execution_helpers.py` clean.

## Verification Steps

```bash
# Module exists and exports the right names
docker exec the-one python -c "
from the_one.tools.execution import (
    ExecutionConfig, DEFAULT_COMMAND_DENYLIST,
    _ENV_ALLOWLIST, _command_check, _cwd_check,
    _truncate_output, _build_subprocess_env,
)
assert _ENV_ALLOWLIST == ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TERM', 'TZ')
print('OK exports')
"

# Defaults
docker exec the-one python -c "
from the_one.tools.execution import ExecutionConfig
c = ExecutionConfig()
assert c.timeout_seconds_default == 30
assert c.timeout_seconds_max == 120
assert c.output_cap_bytes == 262_144
assert c.pty_session_idle_ttl_seconds == 300
assert c.max_concurrent_sessions == 5
assert 'sudo ' in c.command_denylist
print('OK defaults')
"

# Frozen
docker exec the-one python -c "
import pydantic
from the_one.tools.execution import ExecutionConfig
c = ExecutionConfig()
try:
    c.timeout_seconds_default = 1
    raise SystemExit('FAIL')
except pydantic.ValidationError:
    print('OK frozen')
"

# Cross-field invariant
docker exec the-one python -c "
import pydantic
from the_one.tools.execution import ExecutionConfig
try:
    ExecutionConfig(timeout_seconds_default=200, timeout_seconds_max=120)
    raise SystemExit('FAIL')
except pydantic.ValidationError as e:
    assert 'must be <=' in str(e), str(e)
    print('OK cross-field')
"

# Resolver narrowing on a Narrow field
docker exec the-one python -c "
from the_one.tools.execution import ExecutionConfig
from the_one.tools.resolver import resolve
ok = resolve(ExecutionConfig, {'output_cap_bytes': 262144}, {'output_cap_bytes': 65536})
assert ok.output_cap_bytes == 65536
try:
    resolve(ExecutionConfig, {'output_cap_bytes': 262144}, {'output_cap_bytes': 524288})
    raise SystemExit('FAIL')
except ValueError as e:
    assert 'widens' in str(e)
    print('OK narrowing')
"

# Tests
docker exec the-one pytest tests/test_execution_config.py tests/test_execution_helpers.py -x -q
docker exec the-one pytest -x -q

# Lint
docker exec the-one ruff check the_one/tools/execution.py tests/test_execution_config.py tests/test_execution_helpers.py
```

## Implementation Guidance

1. **Create `the_one/tools/execution.py`** with a module docstring describing F4 Decision references and the four helpers' shared `ExecutionConfig` contract.

2. **Define constants**:
   ```python
   _ENV_ALLOWLIST: tuple[str, ...] = (
       "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM", "TZ",
   )

   DEFAULT_COMMAND_DENYLIST: tuple[str, ...] = (
       "sudo ", "su ", "doas ",
       "rm -rf /", "rm -rf ~", "rm -rf $HOME",
       "mkfs", "dd if=", "dd of=/dev/",
       "shutdown", "reboot", "halt", "poweroff", "init 0", "init 6",
       ":(){ :|:& };:",
       "insmod ", "rmmod ", "modprobe ",
       "iptables -F",
   )
   ```

3. **Define `ExecutionConfig`** following the F3 `FilesystemConfig` pattern verbatim: `model_config = ConfigDict(frozen=True)` first, then six `Annotated[type, Marker, Field(...)]` fields with `ge`/`le` bounds + `json_schema_extra` dropdown choices. The exact field declarations come from Decisions 1, 2, 3, 5 (use the snippets in the flight spec).

4. **Cross-field validator**:
   ```python
   @model_validator(mode="after")
   def _default_le_max(self) -> "ExecutionConfig":
       if self.timeout_seconds_default > self.timeout_seconds_max:
           raise ValueError(
               f"timeout_seconds_default ({self.timeout_seconds_default}s) "
               f"must be <= timeout_seconds_max ({self.timeout_seconds_max}s)"
           )
       return self
   ```

5. **`_command_check`**:
   ```python
   def _command_check(command: str, cfg: ExecutionConfig) -> None:
       for token in cfg.command_denylist:
           if token in command:
               raise ConstraintError(f"command contains denylisted token '{token}'")
   ```

6. **`_cwd_check`**:
   ```python
   def _cwd_check(cwd: str | Path, fs_cfg: FilesystemConfig) -> Path:
       canonical = _filesystem_check(cwd, fs_cfg)
       if not canonical.is_dir():
           raise ConstraintError(f"cwd '{canonical}' does not exist or is not a directory")
       return canonical
   ```
   Import `_filesystem_check` and `FilesystemConfig` from `the_one.tools.filesystem`.

7. **`_truncate_output`**:
   ```python
   def _truncate_output(
       stdout: bytes, stderr: bytes, returncode: int, cfg: ExecutionConfig
   ) -> tuple[str, bool]:
       """Combine stdout + stderr, tail-preserve to the cap, append exit suffix.

       NOTE: the truncation marker line is prepended AFTER capping, so the
       returned text length can exceed cfg.output_cap_bytes by the marker's
       ~80 chars. Cap is a "shape the agent's view" knob, not a hard byte
       budget. This is intentional per F4 Decision 2 — do not "fix" by
       counting marker bytes against the cap.
       """
       combined = stdout + stderr
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

   **Empty-output behavior**: matches today's `ShellTool.execute`. `(b"", b"", 0)` returns `"(no output)"`; `(b"", b"", 1)` returns `"[exit code: 1]"` (the exit suffix is appended before `.strip()`, so the text isn't empty). No regression vs F3.

8. **`_build_subprocess_env`**:
   ```python
   def _build_subprocess_env() -> dict[str, str]:
       return {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
   ```

9. **Tests** in two files:
   - `tests/test_execution_config.py` — Pydantic-side tests (defaults, bounds, freeze, cross-field, resolver narrowing).
   - `tests/test_execution_helpers.py` — helper-function tests (denylist, cwd, truncation, env).
   - Use `pathlib.Path` and `tempfile.TemporaryDirectory` for `_cwd_check` tests that need real directories/files.
   - Use `monkeypatch.setenv`/`monkeypatch.delenv` for `_build_subprocess_env` tests.

10. **Run the full suite** to confirm no regressions in F1-F3 surfaces. The new helpers don't replace anything yet — pure addition.

## Edge Cases

- **`_truncate_output` empty-output case**: matches today's `ShellTool` behavior verbatim. `(b"", b"", 0)` → `"(no output)"`; `(b"", b"", 1)` → `"[exit code: 1]"` (exit suffix appended before `.strip()`, so text isn't empty). No regression vs F3.

- **Bounds on dropdown choices**: each `ui_choices` entry must satisfy the `ge`/`le` bounds. Verify by constructing `ExecutionConfig(output_cap_bytes=choice_value)` for each choice; tests can iterate the dropdown via `ExecutionConfig.model_fields["output_cap_bytes"].metadata` if desired (low-priority assertion).

- **Tail-preserving with byte-boundary multibyte chars**: tail-slicing on raw bytes can split a UTF-8 codepoint mid-sequence; `errors="replace"` handles this gracefully (replacement char ◦). No special handling needed.

- **Marker bytes counted in cap?**: NO — the cap applies to the original combined output. The marker is prepended AFTER truncation. This means total returned text length can exceed `cap` by the marker's length (~80 chars). Documented as accepted; the operator cap is a "shape the agent's view" knob, not a hard byte budget.

- **`_command_check` with empty `command`**: empty string contains nothing, so no denylist token matches. No raise. Acceptable.

- **`_cwd_check` on a symlink**: `_filesystem_check` already canonicalizes via `Path.resolve()`, so a symlink resolves to its target before the directory check. Symlink pointing outside scope → caught by `_filesystem_check`.

- **`_build_subprocess_env` with unusual `os.environ` state in tests**: tests should use `monkeypatch.setenv/delenv` (which scope per-test) rather than directly mutating `os.environ` to avoid cross-test pollution.

## Files Affected

- `the_one/tools/execution.py` — NEW; contains constants, `ExecutionConfig`, four helpers.
- `tests/test_execution_config.py` — NEW.
- `tests/test_execution_helpers.py` — NEW.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
