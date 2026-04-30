# Leg: 06-pty-session-tools

**Status**: landed
**Flight**: [Execution Expansion & Constraints](../flight.md)

## Objective

Ship the four PTY session tools — `shell_session_start`, `shell_session_send`, `shell_session_close`, `shell_session_list` — wiring them to the L5a `UnixPtySession` and the L5b registry. Register all four in `_TOOL_CLASSES` and Studio's `TOOL_CATEGORIES`. Per-call denylist enforcement on `shell_session_send` (Decision 11).

## Context

- **L1a-L5b landed** (uncommitted). All scaffolding ready: `ExecutionConfig`, `_command_check`, `_cwd_check`, `_truncate_output`, `_build_subprocess_env`, `UnixPtySession`, `create_pty_session`, `_session_registry` with `register/get/close/list_for_agent/count_for_agent/new_session_id`.
- **F4 Decision 4 (4 tools)**: `shell_session_start`, `shell_session_send`, `shell_session_close`, `shell_session_list`. All four ship in F4. Total `_TOOL_CLASSES` count after L6: `13 + 4 = 17`.
- **F4 Decision 11 (per-call denylist)**: `shell_session_send` re-checks `input` against `cfg.command_denylist` BEFORE writing to the pty. False-positive surface (e.g., `echo "do not run sudo"`) is accepted intentionally — documented in tool description.
- **F4 Decision 6 (discrete tools)**: each tool has its own description; small-model-friendly affordances. F3 set the precedent (`read_file`/`write_file`/`edit_file` discrete, not `file(action=...)`).
- **`agent_name` plumbing** (from L1b): `self._agent_name` is available in each session tool. The registry keys on `(agent_name, session_id)` — cross-agent leakage is prevented at the registry layer.
- **Three-clause try/except envelope** (per L3/L4): `ConstraintError → asyncio.TimeoutError → Exception`. PTY tools follow the same shape.
- **Output formatting**: `shell_session_send` returns the bytes from `await session.send(input, timeout)`. Apply `_truncate_output` for cap enforcement and consistent format (with stderr-marker, but in PTY both streams are merged into stdout — so stderr will always be empty here; truncation marker still applies for oversized outputs).
- **What about `agent_name is None`?**: the introspection path (`/api/tools` zero-arg) produces tools with `agent_name=None`. Session tools must reject calls with `None` agent_name (no real agent context — can't register cross-agent-isolated state). Return `[error] [constraint] session tools require an agent context`.

## Inputs

- `the_one/tools/execution.py` — `ExecutionConfig`, `PythonExecConfig` (NOT used here), `_command_check`, `_cwd_check`, `_truncate_output`.
- `the_one/tools/filesystem.py` — `FilesystemConfig`.
- `the_one/tools/base.py` — `ConstraintError`, `Tool`.
- `the_one/platform/pty.py` — `create_pty_session(cwd, shell)`.
- `the_one/tools/_session_registry.py` — registry helpers.
- `the_one/tools/builtins.py` — `_TOOL_CLASSES` (13 entries, post-L4).
- `the_one/interfaces/web/static/js/areas/studio.js` — `TOOL_CATEGORIES` (line 151).

## Outputs

- `the_one/tools/sessions.py` (NEW):
  - Module docstring referencing F4 Decision 4 (4 tools), 6 (discrete), 11 (per-call denylist).
  - **`ShellSessionStartTool(Tool)`**:
    - `name = "shell_session_start"`.
    - `description = "Start a new interactive shell session and return a session_id token. Use shell_session_send to run commands; shell_session_close to terminate; shell_session_list to recover handles. Default cwd is $HOME; refused if outside the path allowlist. Sessions persist across agent turns and idle-reap after the operator-set TTL (default 5 min)."`.
    - `parameters`:
      ```python
      {
          "type": "object",
          "properties": {
              "cwd": {
                  "type": "string",
                  "description": "Working directory; defaults to $HOME. "
                                 "Refused if outside the path allowlist.",
              },
          },
          "required": [],
      }
      ```
    - `Config = ExecutionConfig`.
    - `Requires = (FilesystemConfig,)`.
    - `execute(self, cwd=None, **kwargs) -> str`:
      - Reject if `self._agent_name is None`.
      - `exec_cfg = self._config`; `fs_cfg = self._cross_configs[FilesystemConfig]`.
      - `try`:
        - Check max-concurrent: `count = await _session_registry.count_for_agent(self._agent_name); if count >= exec_cfg.max_concurrent_sessions: raise ConstraintError(f"max concurrent sessions reached ({exec_cfg.max_concurrent_sessions}); close an existing session first")`.
        - `canonical_cwd = _cwd_check(cwd, fs_cfg) if cwd is not None else _cwd_check(str(Path.home()), fs_cfg)` — always validate (even the `$HOME` default), passing through `_cwd_check` which returns a `Path`.
        - `session = create_pty_session(cwd=canonical_cwd)` — pass `Path` directly (no `str()` conversion; matches `create_pty_session(cwd: Path | None, ...)` signature from L5a).
        - `await session.start()`.
        - `sid = _session_registry.new_session_id()`.
        - `await _session_registry.register(self._agent_name, sid, session, ttl_seconds=exec_cfg.pty_session_idle_ttl_seconds)`.
        - `return sid`.
      - `except ConstraintError as e: return f"[error] [constraint] {e}"`.
      - `except Exception as e: return f"[error] {e}"`.
      - Note: no `asyncio.TimeoutError` clause needed — `start()` has its own internal 2s cap and returns the drained bytes, doesn't raise TimeoutError on the start path.
  - **`ShellSessionSendTool(Tool)`**:
    - `name = "shell_session_send"`.
    - `description = "Send input to an interactive shell session and return the output. session_id from shell_session_start. Inputs are filtered against the same denylist as one-shot shell. Echoing or printing denylisted tokens (e.g. 'sudo') requires writing them through a file (echo $S > /tmp/x after setting S outside the denylist) — this is intentional, not a bug. Output is capped (tail-preserved). Timeout in seconds; clipped to operator-set max."`.
    - `parameters`: `session_id: string (required)`, `input: string (required)`, `timeout: integer (optional)`.
    - `Config = ExecutionConfig`.
    - `Requires = (FilesystemConfig,)` (declared for consistency, though not directly used in send).
    - `execute(self, session_id, input, timeout=None, **kwargs) -> str`:
      - Reject if `self._agent_name is None`.
      - `exec_cfg = self._config`.
      - Float-preserving timeout clip (matches L3/L4 pattern).
      - `try`:
        - `_command_check(input, exec_cfg)` — per-call denylist (Decision 11).
        - `session = await _session_registry.get(self._agent_name, session_id)`.
        - If `session is None`: `raise ConstraintError(f"session '{session_id}' not owned by this agent or does not exist")`.
        - `output = await session.send(input, timeout=clipped_timeout)`. (Returns bytes.)
        - PTY-specific call to `_truncate_output`: pass `output` as stdout, `b""` as stderr, returncode `0` (PTY doesn't surface a per-command rc — assume 0 for cap-formatting purposes; the agent observes shell errors via the output text itself).
        - `text, _ = _truncate_output(output, b"", 0, exec_cfg)`.
        - `return text`.
      - `except ConstraintError as e: return f"[error] [constraint] {e}"`.
      - `except asyncio.TimeoutError: return f"[error] Send timed out after {clipped_timeout}s"` (note wording — distinct from one-shot Shell's "Command timed out" / Python's "Timed out").
      - `except Exception as e: return f"[error] {e}"`.
  - **`ShellSessionCloseTool(Tool)`**:
    - `name = "shell_session_close"`.
    - `description = "Terminate an interactive shell session. session_id from shell_session_start."`.
    - `parameters`: `session_id: string (required)`.
    - `Config = ExecutionConfig`.
    - `Requires = ()` — no cross-Config needed.
    - `execute(self, session_id, **kwargs) -> str`:
      - Reject if `self._agent_name is None`.
      - `try`:
        - `closed = await _session_registry.close(self._agent_name, session_id)`.
        - If `closed`: `return f"closed {session_id}"`.
        - Else: `raise ConstraintError(f"session '{session_id}' not owned by this agent or does not exist")`.
      - `except ConstraintError as e: return f"[error] [constraint] {e}"`.
      - `except Exception as e: return f"[error] {e}"`.
  - **`ShellSessionListTool(Tool)`**:
    - `name = "shell_session_list"`.
    - `description = "List session_ids of all open interactive shell sessions for this agent. Useful after long context windows when the agent has forgotten its handles."`.
    - `parameters`: `{ "type": "object", "properties": {}, "required": [] }`.
    - `Config = ExecutionConfig`.
    - `Requires = ()`.
    - `execute(self, **kwargs) -> str`:
      - Reject if `self._agent_name is None`.
      - `try`:
        - `sids = await _session_registry.list_for_agent(self._agent_name)`.
        - If empty: `return "(no open sessions)"`.
        - Else: `return "\n".join(sids)`.
      - `except Exception as e: return f"[error] {e}"`.
- `the_one/tools/builtins.py`:
  - Update imports: `from the_one.tools.sessions import (ShellSessionStartTool, ShellSessionSendTool, ShellSessionCloseTool, ShellSessionListTool)`.
  - Add to `_TOOL_CLASSES` (insert AFTER `python_exec`, BEFORE web tools):
    ```python
    "shell_session_start": ShellSessionStartTool,
    "shell_session_send": ShellSessionSendTool,
    "shell_session_close": ShellSessionCloseTool,
    "shell_session_list": ShellSessionListTool,
    ```
  - Total: 17 tools.
- `the_one/interfaces/web/static/js/areas/studio.js`:
  - Update `TOOL_CATEGORIES` (line 151) to add a new `'Sessions'` group:
    ```javascript
    var TOOL_CATEGORIES = {
      'Filesystem': ['read_file', ..., 'list_dir'],
      'Execution': ['shell', 'python_exec'],
      'Sessions': ['shell_session_start', 'shell_session_send', 'shell_session_close', 'shell_session_list'],
      'Web': ['http_request', 'web_search']
    };
    ```
- `tests/conftest.py` (or `tests/_pty_fixtures.py`): **Promote `MockPtySession` from L5b's `tests/test_session_registry.py`** to a shared location so L6 can import it without `from tests.test_session_registry import MockPtySession` (cross-test-module imports are fragile under pytest's collection ordering). Move; update L5b's tests to import from the shared location.
- `tests/test_session_tools.py` (NEW):
  - Test `ShellSessionStartTool.execute(cwd=...)` returns a `pty-...` session_id.
  - Test reject with `agent_name=None` → `[error] [constraint] session tools require an agent context`.
  - Test `cwd` outside allowlist → `[error] [constraint] ...`.
  - Test max-concurrent: register 5 mock sessions for agent A; 6th `start` returns `[error] [constraint] max concurrent sessions reached (5); close an existing session first`.
  - Test `ShellSessionSendTool` happy path: start (real PTY), send `"echo hello"`, output contains `b"hello"`.
  - Test `ShellSessionSendTool` denylist trip: send `"sudo whoami"` → `[error] [constraint] command contains denylisted token 'sudo '`.
  - Test `ShellSessionSendTool` cross-agent: agent A starts session; agent B's send tool tries to `get` it → `[error] [constraint] session '...' not owned by this agent`.
  - Test `ShellSessionSendTool` unknown session → same error.
  - Test `ShellSessionCloseTool` closes a session and removes from registry.
  - Test `ShellSessionListTool` returns sids.
  - Test `ShellSessionListTool` empty → `(no open sessions)`.
  - Use `MockPtySession` from L5b's test fixtures (move to a shared `tests/fixtures/mock_pty.py` if reused across files, or duplicate inline).
  - At least ONE end-to-end test using a real `UnixPtySession` to verify the full chain works.
- `tests/test_builtins.py`:
  - Update `_TOOL_CLASSES` count assertions at three sites (lines ~56, 63, 104): 13 → 17.
  - Update name-set assertions to include the four new tools.
  - **Cross-Config dispatch assertion** (`test_cross_configs_contains_three_distinct_configs`) does NOT need updating — all four session tools share `ExecutionConfig`, already in the set `{FilesystemConfig, ExecutionConfig, PythonExecConfig}`.

## Acceptance Criteria

- [x] `the_one/tools/sessions.py` exists with the four Tool classes.
- [x] All four tools declare `Config = ExecutionConfig`. Start + Send declare `Requires = (FilesystemConfig,)`; Close + List declare `Requires = ()`.
- [x] All four tools reject calls with `agent_name=None` returning `[error] [constraint] session tools require an agent context`.
- [x] `ShellSessionStartTool` enforces `count_for_agent < max_concurrent_sessions`; emits the documented error.
- [x] `ShellSessionStartTool` returns a `pty-{36 hex chars}` session_id on success.
- [x] `ShellSessionStartTool` validates cwd via `_cwd_check` (FilesystemConfig path scope + dir check).
- [x] `ShellSessionSendTool` runs `_command_check(input, exec_cfg)` BEFORE `session.send` (Decision 11 — per-call denylist).
- [x] `ShellSessionSendTool` rejects unknown / cross-agent session_id with `[error] [constraint] session '...' not owned by this agent or does not exist`.
- [x] `ShellSessionSendTool` clips timeout (float-preserving) and emits `[error] Send timed out after Ns` on timeout.
- [x] `ShellSessionSendTool` applies `_truncate_output` to the result (cap-enforced).
- [x] `ShellSessionCloseTool` calls `_session_registry.close`; reports success or unknown-session error.
- [x] `ShellSessionListTool` returns newline-joined sids; `(no open sessions)` when empty.
- [x] `_TOOL_CLASSES` has 17 entries post-L6 (13 + 4 new sessions tools).
- [x] Studio `TOOL_CATEGORIES` includes a `'Sessions'` group with the four new tool names.
- [x] Three-clause try/except envelope on Send: `ConstraintError → asyncio.TimeoutError → Exception`. Two-clause (no timeout) on Start/Close/List.
- [x] Existing `test_builtins.py` count/name assertions updated to 17.
- [x] At least one end-to-end test uses a real `UnixPtySession` round-trip through the tool layer.
- [x] Full unit suite green (modulo CSS-token red).
- [x] `ruff check` clean on touched files.
- [x] Browser tests still pass (Studio `TOOL_CATEGORIES` change should not break browser tests, but verify).
  - Note: Playwright browser binaries not installed in container (pre-existing env issue unrelated to this leg). The TOOL_CATEGORIES JS literal is syntactically valid and matches the documented layout (verified by direct file read). Browser-suite teardown errors all originate from `BrowserType.launch` failing — none reference `TOOL_CATEGORIES` or session tools.

## Verification Steps

```bash
# Tool count and registration
docker exec the-one python -c "
from the_one.tools.builtins import _TOOL_CLASSES
assert len(_TOOL_CLASSES) == 17, f'count {len(_TOOL_CLASSES)}'
for n in ['shell_session_start', 'shell_session_send', 'shell_session_close', 'shell_session_list']:
    assert n in _TOOL_CLASSES, n
print('OK 17 tools')
"

# End-to-end round trip via real UnixPtySession
docker exec the-one python -c "
import asyncio
from the_one.tools.sessions import (
    ShellSessionStartTool, ShellSessionSendTool,
    ShellSessionCloseTool, ShellSessionListTool,
)
from the_one.tools.execution import ExecutionConfig
from the_one.tools.filesystem import FilesystemConfig
from the_one.tools._session_registry import _clear_for_test
async def main():
    cfg = ExecutionConfig()
    cross = {FilesystemConfig: FilesystemConfig()}
    start = ShellSessionStartTool(cfg, cross_configs=cross, agent_name='alpha')
    send = ShellSessionSendTool(cfg, cross_configs=cross, agent_name='alpha')
    close = ShellSessionCloseTool(cfg, cross_configs=cross, agent_name='alpha')
    listt = ShellSessionListTool(cfg, cross_configs=cross, agent_name='alpha')
    sid = await start.execute(cwd='/tmp')
    assert sid.startswith('pty-'), sid
    out = await send.execute(session_id=sid, input='echo hello-pty')
    assert 'hello-pty' in out, out
    sids = await listt.execute()
    assert sid in sids, sids
    closed = await close.execute(session_id=sid)
    assert sid in closed, closed
    await _clear_for_test()
    print('OK round-trip')
asyncio.run(main())
"

# Cross-agent isolation
docker exec the-one python -c "
import asyncio
from the_one.tools.sessions import ShellSessionStartTool, ShellSessionSendTool
from the_one.tools.execution import ExecutionConfig
from the_one.tools.filesystem import FilesystemConfig
from the_one.tools._session_registry import _clear_for_test
async def main():
    cfg = ExecutionConfig()
    cross = {FilesystemConfig: FilesystemConfig()}
    start_a = ShellSessionStartTool(cfg, cross_configs=cross, agent_name='alpha')
    send_b = ShellSessionSendTool(cfg, cross_configs=cross, agent_name='beta')
    sid = await start_a.execute(cwd='/tmp')
    out = await send_b.execute(session_id=sid, input='echo')
    assert out.startswith('[error] [constraint]'), out
    assert 'not owned' in out or 'does not exist' in out, out
    await _clear_for_test()
    print('OK cross-agent isolation')
asyncio.run(main())
"

# Tests
docker exec the-one pytest tests/test_session_tools.py tests/test_builtins.py tests/test_session_registry.py -x -q
docker exec the-one pytest -x -q

# Browser smoke (Studio TOOL_CATEGORIES change)
docker exec the-one make test-browser 2>&1 | tail -20

# Lint
docker exec the-one ruff check the_one/tools/sessions.py the_one/tools/builtins.py tests/test_session_tools.py
```

## Implementation Guidance

1. **Build `the_one/tools/sessions.py`** following L3/L4's tool template:
   - One module-level docstring referencing F4 Decisions 4, 6, 11.
   - Imports: `asyncio`, `Path`, `typing.Any`, the F4 helpers, `_session_registry`, `create_pty_session`.
   - One class per tool. Reuse the L3/L4 envelope pattern.
   - Reject `agent_name is None` at the top of every `execute` (DRY: pull into a helper `_require_agent_name(self) -> str` that returns the name or raises `ConstraintError`).

2. **Wire `_TOOL_CLASSES`** in `the_one/tools/builtins.py`:
   - Insert the four entries after `python_exec` and before web tools.
   - Maintain insertion order for the cross-Config dispatch's deterministic-first-tool semantics.

3. **Update Studio `TOOL_CATEGORIES`**:
   - Add `'Sessions': [...]` entry between `'Execution'` and `'Web'`.
   - **Browser tests**: this is a JS-only change but tests/browser/test_studio.py may have assertions on the categories — verify and update if needed.

4. **Build tests** in `tests/test_session_tools.py`:
   - Use `pytest-asyncio` auto mode (no decorators).
   - For unit tests: import `MockPtySession` from `tests/test_session_registry.py` (or move to a shared fixture file). Inject by monkeypatching `the_one.tools.sessions.create_pty_session` to return the mock.
   - For end-to-end: spawn `UnixPtySession`, full chain through the tool layer.
   - Always `await _clear_for_test()` after each test (autouse fixture).

5. **Carefully verify the `_truncate_output` for PTY** — passing `b""` for stderr means no `[stderr]` marker is inserted (since the L3 refinement only inserts when `stderr` is non-empty). The output is just the PTY bytes plus optional truncation marker.

6. **Run tests + ruff + browser**.

## Edge Cases

- **`shell_session_send` with input that produces no shell output**: e.g., `cd /tmp` (silent on success). The PTY's idle-mark detection in `session.send` waits for ANY output, then idle for 100ms. If the only output is the prompt re-displaying, the prompt bytes are returned. The agent sees the prompt (e.g., `bash$ `). Acceptable noise — agents tolerate this.
- **`shell_session_send` with input that takes longer than timeout but produces some output**: idle-mark returns the partial output without raising `TimeoutError`. Agent sees what was produced. Acceptable.
- **`shell_session_send` after the underlying shell process has exited** (e.g., agent sent `exit`): `session.send` may raise `OSError(EIO)` or return empty. Handled by the generic `Exception` clause → `[error] OSError: ...`. Agent should observe this and `shell_session_close` to clean up.
- **`shell_session_close` on already-closed session**: `_session_registry.close` returns `False` (entry not present). Tool emits `[error] [constraint] session 'pty-xxx' not owned by this agent or does not exist`. Agent retries the close which is harmless.
- **Idle reaper closes a session between `get` and `send`**: the reaper acquires the registry lock, closes, removes. If `send` already captured the session reference before the reap, the `await session.send` may raise `OSError(EIO)` (master_fd closed). Handled by the `Exception` clause. Acceptable race; the reaper is best-effort cleanup.
- **`agent_name=None` in introspection mode**: `BuiltinToolProvider().get_tools()` (zero-arg) creates tools with `agent_name=None` for `/api/tools`. These tools' `execute` returns the constraint error if invoked — consistent with "introspection-only, not invocable". The agent factory always passes a real `agent_name`.
- **`max_concurrent_sessions` race** — **DECIDED for L6: accept the race**. Agent makes 5 concurrent `start` calls (asyncio gather). Each checks `count < 5`; all see count=4; all proceed; registry now has 6. Small-model agents in M05 do NOT pipeline tool calls — they emit one tool call per turn, await response, then emit the next. The cap is therefore a soft limit (operator-set guideline). For F6+ if/when an HTTP API exposes parallel agent invocations, the registry can grow a `register_if_under_cap()` helper that does count+insert under one lock acquisition. Document this as known acceptable for F4.
- **Description for `shell_session_send` is long** (~150 words). Acceptable for small models — the false-positive surface needs explicit explanation.
- **Studio `TOOL_CATEGORIES` ordering**: insert `'Sessions'` between `'Execution'` and `'Web'` to group execution-family tools together. Cosmetic, but good UX.

## Files Affected

- `the_one/tools/sessions.py` — NEW; four Tool classes.
- `the_one/tools/builtins.py` — register four tools in `_TOOL_CLASSES`.
- `the_one/interfaces/web/static/js/areas/studio.js` — add `'Sessions'` group to `TOOL_CATEGORIES`.
- `tests/test_session_tools.py` — NEW.
- `tests/test_builtins.py` — update count/name assertions to 17.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
