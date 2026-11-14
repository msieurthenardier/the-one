# Leg: 05a-fixture-extension-and-integration-tests

**Status**: completed
**Flight**: [Local MCP Sandbox — Adapter Contract + Bubblewrap Linux Backend](../flight.md)

## Objective

Extend `tests/fixtures/mcp/hello_server.py` with three TEST-ONLY escape-attempt tools (`write_outside_sandbox`, `dump_env`, `try_connect`) and add ~10 integration tests in a new `tests/test_mcp_sandbox_integration.py` file that drive `MCPClient.call_tool` through the L4 sandbox-wrapped `connect_stdio` path against a real bwrap-spawned subprocess. Tests prove the sandbox enforces the F3 invariants: FS scope refusal, env-allowlist invariant (8-key allowlist via `_build_subprocess_env` + bwrap `--clearenv` defense-in-depth), and network refusal under `--unshare-net`. Plus 1 in-process unit test on the opt-in registration mechanism. These are the integration-level proofs that the sandbox actually does what L3's argv-compilation tests assume it does.

## Context

- **Real-subprocess integration tests.** Unlike L3 (pure arg-compilation) and L4's mocked tests + 1 real `/bin/cat` smoke, L5a runs the FastMCP hello server INSIDE the bwrap-wrapped subprocess and calls the new escape-attempt tools through `MCPClient`. Each tool is designed to FAIL under the sandbox in a way the test can observe — verifying the sandbox actually fenced the operation, not just that bwrap was invoked.
- **TEST-ONLY tool marker (per flight §9).** Each new tool MUST carry a comment marker `# TEST-ONLY (F3 escape-attempt fixture): DO NOT REMOVE OR PROMOTE TO PRODUCTION` so that future readers / refactoring agents don't accidentally repurpose them. The marker is enforced by acceptance-criteria grep.
- **The three escape-attempt tools (per flight §9):**
  - `write_outside_sandbox(path: str, content: str) -> str` — calls `Path(path).write_text(content)`. Under the strict-floor sandbox (`writable_paths=[]`), every host path outside `/tmp` is read-only via `--ro-bind / /`; the `write_text` will raise `OSError` (errno EROFS or EACCES) inside the FastMCP runtime, which surfaces as a tool-call error to the MCP client. Test asserts `MCPCallError` (F2's `tools/call isError=true` translation) when targeting `/etc/test_escape`.
  - `dump_env() -> dict[str, str]` — returns `dict(os.environ)`. Used to verify the env-allowlist invariant. **Filtering attribution** (corrected per design review): `_build_subprocess_env()` at `the_one/platform/env.py` filters `os.environ` to the 8-key allowlist (`PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ`) BEFORE the env reaches `BubblewrapSandbox.prepare_spawn`. So `PYTEST_CURRENT_TEST` / `LD_PRELOAD` / `PYTHONHOME` / etc. are dropped by the platform-env allowlist — bwrap's `--clearenv` is defense-in-depth (it strips bwrap's own inherited env, plus re-asserts the allowlist via `--setenv`). Test asserts the returned dict's keys are a subset of (allowlist ∪ operator-supplied keys ∪ `{HOME}`), and `HOME == "/tmp"`.
  - `try_connect(host: str, port: int) -> str` — calls `socket.create_connection((host, port), timeout=2.0)`; returns either "connected" or a formatted error. Under default `network_allowed=False` + `--unshare-net`, network calls fail with `OSError` (errno ENETUNREACH or similar) — test asserts the error message contains "Network is unreachable" / "ENETUNREACH" / similar. Under `network_allowed=True`, the call succeeds (test conditional on CI env actually having outbound — gate via `pytest.mark.skipif`).
- **Test-tool registration: split into a `register_naughty_tools()` helper.** The three escape-attempt tools must be available ONLY when explicitly requested (so they don't leak into other F2/F3 tests that use the hello fixture for innocent purposes). Decision:
  - Add a function `register_naughty_tools(app: FastMCP) -> None` to `hello_server.py` that registers the three tools on a passed-in FastMCP app.
  - DO NOT call `register_naughty_tools` automatically in `make_mcp_app()` — it's opt-in.
  - Add a CLI flag `--with-naughty-tools` (or equivalent env var like `F3_HELLO_REGISTER_NAUGHTY_TOOLS=1`) that the L5a tests can set when launching the stdio subprocess. When the flag/env is present in `main()`, call `register_naughty_tools(mcp_app)` before `mcp_app.run("stdio")`.
  - **Cleaner**: a `--with-naughty-tools` CLI flag is more discoverable than an env var. The L5a test fixture builds `args = ["-m", "tests.fixtures.mcp.hello_server", "--stdio", "--with-naughty-tools"]` and passes it via `MCPSource.config["args"]`.
  - F2's existing tests that use the hello fixture (`echo` / `add` only) keep working — they don't pass `--with-naughty-tools` so the naughty tools aren't registered.
- **MCPSource construction in tests.** Each L5a test builds an `MCPSource` with:
  - `command = sys.executable`
  - `args = ["-m", "tests.fixtures.mcp.hello_server", "--stdio", "--with-naughty-tools"]`
  - `env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(_PROJECT_ROOT)}` (so the subprocess can find Python and the fixture)
  - `cwd = None`
  - `config["sandbox"] = ...` — varies per test
  - The `config["env"]` MUST include `PYTHONPATH` so the subprocess running INSIDE the sandbox can import the test fixture (the dev container's site-packages aren't on the bwrap-wrapped Python's path otherwise — actually wait, `--ro-bind / /` makes them visible; the issue is the fixture path `tests/fixtures/...` requires PYTHONPATH = the project root).
- **PYTHONPATH leakage concern.** The `dump_env` test will show that PYTHONPATH is in the assembled env (operator-supplied via `config.env`). That's correct — it's an operator-controlled value, not host-env leakage. The test asserts the env contains EXACTLY the operator + allowlist + HOME-override keys, NOT that it's empty.
- **Tool-call error translation (F2's `MCPCallError`).** When a tool raises an exception (e.g., `OSError` from `write_text` failing), FastMCP returns `tools/call` with `isError: true` and the error message in content. F2's `MCPClient.call_tool` translates `isError=true` to `MCPCallError`. Tests catch `MCPCallError` and inspect the message.
- **Per-leg lint gate** + lint check on the fixture file (it's the only Python source change outside tests).
- **No new bwrap argv work.** L3+L4 already cover the wrap. L5a only changes the test fixture and adds new integration tests.
- **Flight §10 + L1a + L4 prerequisites.** The dev container has bwrap; the `THE_ONE_SANDBOX_DISABLED + THE_ONE_TEST_MODE` double-flag bypass is NOT active in normal pytest runs (only `TEST_MODE` is set; `SANDBOX_DISABLED` is not). So when L5a tests call `connect_stdio`, the real sandbox runs.

## Inputs

- L1a, L1b, L2, L3, L4 all `completed`. `BubblewrapSandbox` operational; `connect_stdio` wraps every stdio source via `BubblewrapSandbox.prepare_spawn` unless the double-flag bypass is set.
- `tests/fixtures/mcp/hello_server.py` exists per F2: defines `make_mcp_app()` returning a FastMCP with `echo` and `add` tools; `mcp_app` module-level instance; `main()` handles `--stdio` and `--http` modes.
- F2's `tests/test_mcp_integration.py` is the existing integration-test home (14 tests, including 7 stdio tests via MCPClient that already pick up the L4 sandbox path).
- F2's `MCPClient.call_tool` translates `tools/call` `isError=true` to `MCPCallError`.
- `MCPCallError` exists at `the_one/mcp/errors.py` with `__init__(tool_name, server_message)`.
- `_ENV_ALLOWLIST` (8-key tuple) at `the_one/platform/env.py` defines the host-env allowlist that gets baked into every assembled env.

## Outputs

- **`tests/fixtures/mcp/hello_server.py` extended**:
  - New function `register_naughty_tools(app: FastMCP) -> None` that registers three TEST-ONLY tools on the passed-in app:
    - `write_outside_sandbox(path: str, content: str) -> str` — calls `Path(path).write_text(content)`; returns `"wrote {len} bytes"` on success. Marker comment above the `@app.tool()` decorator.
    - `dump_env() -> dict[str, str]` — returns `dict(os.environ)`. Marker comment.
    - `try_connect(host: str, port: int) -> str` — calls `socket.create_connection((host, port), timeout=2.0)`; returns `"connected"` on success, formatted error message string otherwise (does NOT raise). Marker comment.
  - `main()` gains handling for a new `--with-naughty-tools` CLI flag that, when present, calls `register_naughty_tools(mcp_app)` before `mcp_app.run("stdio")`.
  - Existing `make_mcp_app()` and `echo`/`add` tools UNCHANGED.

- **`tests/test_mcp_sandbox_integration.py`** — NEW test file (separate from `test_mcp_integration.py` to keep F2's regression suite distinct from L5a's sandbox-specific integration tests). Tests:
  1. `test_sandbox_refuses_fs_write_outside_writable_paths` (real subprocess) — strict-floor profile (`writable_paths=[]`); call `write_outside_sandbox(path="/etc/test_escape", content="x")`; assert `MCPCallError` raised; assert error message contains "Read-only" OR "Permission denied" (Python's `OSError.__str__` uses strerror text, not symbolic names like EROFS/EACCES — so substring match against the strerror forms only).
  2. `test_sandbox_allows_fs_write_when_path_in_writable_paths` (real subprocess) — uses a session-scoped fixture that creates a unique `/var/tmp/sandbox_l5a_<uuid>/` subdir on the HOST (so bwrap's `--bind` source path exists) and removes it in teardown (parallel-safe via uuid for pytest-xdist). Profile with `writable_paths=["/var/tmp/sandbox_l5a_<uuid>"]`; call `write_outside_sandbox(path="/var/tmp/sandbox_l5a_<uuid>/probe", content="hello")`; assert success message. Then read the file from the HOST filesystem via `Path("/var/tmp/sandbox_l5a_<uuid>/probe").read_text() == "hello"` to prove the write actually persisted to the host-visible bind mount.

     **Edge case documented**: L3's argv compilation emits `--bind` BEFORE `--tmpfs /tmp`, so `writable_paths=["/tmp/foo"]` would be shadowed by the later `--tmpfs /tmp` (the bind mount becomes invisible). Test #2 uses `/var/tmp/...` to avoid this. Operators wanting persistent writable scratch must use paths outside `/tmp`. Documented in flight log + a future routine-maintenance candidate to reorder L3's argv (move `--tmpfs /tmp` before the bind loop so per-path binds win).
  3. `test_sandbox_env_allowlist_invariant_with_home_override` (real subprocess) — strict-floor profile; operator `config.env = {"PYTHONPATH": str(_PROJECT_ROOT)}`; call `dump_env()`; assert returned dict's `HOME == "/tmp"` (the §13 override); `PATH` is present (from `_ENV_ALLOWLIST`); `PYTHONPATH` is present (from `config.env`); SOME host-env-only keys (e.g., `PWD`, `PYTEST_CURRENT_TEST`) are NOT present (proving the `_build_subprocess_env` 8-key allowlist filter PLUS bwrap's `--clearenv` defense-in-depth fired correctly).
  4. `test_sandbox_network_refused_under_unshare_net` (real subprocess) — strict-floor profile (`network_allowed=False`); call `try_connect(host="8.8.8.8", port=53)`; assert returned string contains "Network is unreachable" / "ENETUNREACH" / similar (use IP-literal NOT hostname to avoid DNS resolution being the failure cause). The tool returns the error as a string (not a raised exception) so we can assert on the value directly.
  5. `test_sandbox_network_allowed_when_network_allowed_true` (real subprocess + `pytest.mark.skipif` on outbound network availability) — `network_allowed=True`; call `try_connect(host="8.8.8.8", port=53)`; assert "connected". Skip if `socket.create_connection(("8.8.8.8", 53), timeout=2)` from the test process itself (no sandbox) fails — proves the test-runner has outbound network in the first place.
  6. `test_sandbox_writable_paths_nonexistent_raises_at_connect` (real subprocess) — profile with `writable_paths=["/var/does/not/exist_<uuid>"]`; expect `MCPConnectionError` per L4's Anomaly A02 (bwrap-side errors NOT translated to `MCPSandboxError` in this flight; they surface as F2's `MCPConnectionError` via MCPClient.connect's `except Exception` translation). Empirically verified at design review: bwrap exits non-zero with stderr `bwrap: Can't find source path /var/does/not/exist_<uuid>` → stdio_client sees broken pipe → SDK initialize() raises → MCPClient.connect catches → translates to `MCPConnectionError`. Test assertion: `pytest.raises(MCPConnectionError)`; assert NOT `MCPSandboxError`. Locks the deferred-translation gap as a positive test (rather than skipping). The substring assertion on bwrap stderr is omitted (depends on whether stderr propagates up the stdio_client chain to the exception message — empirically variable).
  7. `test_sandbox_dump_env_no_secret_leakage_via_test_runner_env` (real subprocess) — set a process-env-only sentinel key in the test (e.g., via `monkeypatch.setenv("F3_TEST_LEAK_SENTINEL", "should_not_leak")` — this propagates to the test process but NOT to `config.env`; `--clearenv` should drop it). Strict-floor profile; call `dump_env()`; assert `"F3_TEST_LEAK_SENTINEL" not in returned_env`. Locks the env-allowlist invariant against host-env leakage.
  8. `test_sandbox_with_naughty_tools_flag_registers_three_tools` (real subprocess) — list_tools on a fresh client with `--with-naughty-tools`; assert all three tools present (`write_outside_sandbox`, `dump_env`, `try_connect`) PLUS the original `echo` / `add`. Locks the opt-in registration mechanism.
  9. `test_sandbox_without_naughty_tools_flag_omits_naughty_tools` (real subprocess) — list_tools WITHOUT `--with-naughty-tools`; assert only `echo` and `add` are present. Locks the opt-in mechanism's directionality.
  10. `test_register_naughty_tools_in_process` (in-process unit test, NO subprocess, NO sandbox) — call `register_naughty_tools(make_mcp_app())` directly; introspect the FastMCP instance's tool list via `app._tool_manager.list_tools()` (or equivalent); assert all three naughty tools present. Then construct a SECOND `make_mcp_app()` instance WITHOUT calling `register_naughty_tools`; assert ONLY `echo` and `add` present. Fast (<10ms) — gives early CI signal for accidental autoregistration regressions before the slow integration tests run.

  Total: ~10 tests. Tests 1-9 marked `@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bwrap required")` (test #10 is in-process and runs unconditionally). Use a session-scoped fixture for test #2's writable path setup (`/var/tmp/sandbox_l5a_<uuid>` with reliable teardown). All real-subprocess tests build their own `MCPSource` inline via `_build_naughty_source(...)` helper; `mcp_fixture_sandbox_profile` fixture (added in L4) is consumed by tests that use the strict floor.

- **Flight artifacts**:
  - `flight-log.md` gets `### L5a Fixture Extension and Integration Tests` under `## Leg Progress`.
  - `flight.md` checkbox ticked.
  - `legs/05a-...md` Status flipped to `completed`.

## Acceptance Criteria

- [ ] **`hello_server.py` extended with three TEST-ONLY tools** registered via opt-in `register_naughty_tools(app)` helper. Each tool has the `# TEST-ONLY (F3 escape-attempt fixture): DO NOT REMOVE OR PROMOTE TO PRODUCTION` marker comment immediately above its `@app.tool()` decorator. Verifiable: `grep -c "TEST-ONLY (F3 escape-attempt fixture)" tests/fixtures/mcp/hello_server.py` returns ≥ 3.
- [ ] **`--with-naughty-tools` CLI flag works**: passing the flag registers the three escape-attempt tools BEFORE `mcp_app.run("stdio")`. Without the flag, only `echo` / `add` are registered.
- [ ] **Existing F2 hello tests unaffected**: `tests/test_mcp_integration.py` still passes (the existing 14 tests don't pass `--with-naughty-tools`, so naughty tools don't appear in their tool list).
- [ ] **`tests/test_mcp_sandbox_integration.py` ~10 tests all pass** (9 real-subprocess + 1 in-process; some may be skipped appropriately when bwrap / network unavailable).
- [ ] **FS-escape refusal**: test #1 proves `write_outside_sandbox(/etc/...)` raises `MCPCallError` with errno text indicating read-only filesystem.
- [ ] **Writable-path mechanism**: test #2 proves a `writable_paths` entry actually grants write access. Uses a path OUTSIDE `/tmp` to avoid `--tmpfs /tmp` shadowing.
- [ ] **Env-allowlist invariant**: test #3 proves `dump_env()` returns only allowlist + operator-config + `HOME=/tmp` keys; host-only keys (e.g., `PYTEST_CURRENT_TEST`) are filtered.
- [ ] **Network refusal**: test #4 proves `try_connect(8.8.8.8, 53)` returns a network-unreachable error string under `network_allowed=False`.
- [ ] **Network allowed**: test #5 proves `try_connect` succeeds under `network_allowed=True`. Skip if test-runner has no outbound network.
- [ ] **No host-env leakage**: test #7 proves a process-env-only sentinel key is filtered by `--clearenv`.
- [ ] **`--with-naughty-tools` opt-in mechanism**: tests #8 and #9 prove directionality.
- [ ] **Lint clean**: `ruff check the_one/ tests/` exits 0 (the new fixture imports + tests must comply).
- [ ] **No source changes outside `hello_server.py` + `test_mcp_sandbox_integration.py`** + flight artifacts.
- [ ] **F1/F2/L2/L3/L4 regression**: all prior test files still green.
- [ ] **Edge case documented**: the `--bind /tmp/...` shadowing by `--tmpfs /tmp` is documented in the flight log as a known interaction (operators must use writable_paths OUTSIDE /tmp for persistent scratch).

## Verification Steps

```bash
cd ~/projects/the-one

# --- 1. Diff scope ---
git status --porcelain
# Expect modifications under:
#   tests/fixtures/mcp/hello_server.py    (M)
#   tests/test_mcp_sandbox_integration.py  (??)
#   missions/.../flight.md                  (M)
#   missions/.../flight-log.md              (M)
#   missions/.../legs/05a-...md             (M)

# --- 2. New L5a integration tests pass ---
docker compose exec -T the-one python -m pytest tests/test_mcp_sandbox_integration.py -v
# Expect: ~9 tests pass (some may be skipped — network test, deferred-translation test)

# --- 3. F2 hello regression ---
docker compose exec -T the-one python -m pytest tests/test_mcp_integration.py -v
# Expect: all 14 pass; tool-list assertions for the existing tests don't see naughty tools

# --- 4. L4 + L3 + L2 regression ---
docker compose exec -T the-one python -m pytest tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -v
# Expect: all green

# --- 5. F1 API regression ---
docker compose exec -T the-one python -m pytest tests/test_db_api.py::TestMCPSourceAPI -v
# Expect: 16 passed

# --- 6. TEST-ONLY markers present ---
grep -c "TEST-ONLY (F3 escape-attempt fixture)" tests/fixtures/mcp/hello_server.py
# Expect: ≥ 3

# --- 7. Lint ---
docker compose exec -T the-one ruff check the_one/ tests/
# Expect: All checks passed.

# --- 8. Manual: list_tools with naughty-tools flag ---
docker compose exec -T the-one python -c "
import asyncio, sys
from pathlib import Path
from the_one.db.models import MCPSource
from the_one.mcp.client import MCPClient
PROJECT_ROOT = '<repo>'  # the repository root (placeholder)
src = MCPSource(name='probe', type='stdio', config={
    'command': sys.executable,
    'args': ['-m', 'tests.fixtures.mcp.hello_server', '--stdio', '--with-naughty-tools'],
    'env': {'PATH': '/usr/bin:/usr/local/bin', 'PYTHONPATH': PROJECT_ROOT},
    'cwd': PROJECT_ROOT,
    'sandbox': {'writable_paths': [], 'network_allowed': False},
}, secrets={})
async def run():
    async with MCPClient(src) as client:
        tools = await client.list_tools()
        names = sorted(t.name for t in tools)
        print('tools:', names)
        assert 'write_outside_sandbox' in names
        assert 'dump_env' in names
        assert 'try_connect' in names
        assert 'echo' in names
        assert 'add' in names
asyncio.run(run())
"
# Expect: tools list contains all 5; assertions pass
```

If any verification fails:
1. Capture failing output.
2. Diagnose: most likely (a) PYTHONPATH not propagated → fixture import fails → MCPConnectionError instead of expected error, (b) errno text varies by kernel — broaden the assertion's allowed substrings, (c) `--bind` shadowing by `--tmpfs /tmp` — use a path outside /tmp for test #2, (d) FastMCP serialization of OSError doesn't preserve errno — assert on whatever message FastMCP propagates.

## Implementation Guidance

1. **Extend `tests/fixtures/mcp/hello_server.py`**: add `register_naughty_tools` and the `--with-naughty-tools` CLI flag handling. Sketch:

   ```python
   import os
   import socket
   from pathlib import Path

   def register_naughty_tools(app: FastMCP) -> None:
       """Register TEST-ONLY escape-attempt tools on the app (F3 L5a).

       These tools exist solely to verify the F3 sandbox enforces its
       documented invariants (FS scope, env-allowlist, network policy).
       NEVER call this from production paths.
       """

       # TEST-ONLY (F3 escape-attempt fixture): DO NOT REMOVE OR PROMOTE TO PRODUCTION
       @app.tool()
       def write_outside_sandbox(path: str, content: str) -> str:
           """Write content to path. Used to verify FS scope refusal under sandbox."""
           Path(path).write_text(content)
           return f"wrote {len(content)} bytes to {path}"

       # TEST-ONLY (F3 escape-attempt fixture): DO NOT REMOVE OR PROMOTE TO PRODUCTION
       @app.tool()
       def dump_env() -> dict[str, str]:
           """Return os.environ. Used to verify env-allowlist invariant under sandbox."""
           return dict(os.environ)

       # TEST-ONLY (F3 escape-attempt fixture): DO NOT REMOVE OR PROMOTE TO PRODUCTION
       @app.tool()
       def try_connect(host: str, port: int) -> str:
           """Attempt TCP connect. Used to verify network policy under sandbox."""
           try:
               with socket.create_connection((host, port), timeout=2.0):
                   return "connected"
           except OSError as e:
               return f"connect failed: {type(e).__name__}: {e}"
   ```

   And in `main()`:
   ```python
   def main(argv: list[str] | None = None) -> int:
       args = list(argv if argv is not None else sys.argv[1:])
       with_naughty = "--with-naughty-tools" in args
       args = [a for a in args if a != "--with-naughty-tools"]
       mode = args[0] if args else "--stdio"

       if mode == "--stdio":
           if with_naughty:
               register_naughty_tools(mcp_app)
           mcp_app.run("stdio")
           return 0
       # ... rest unchanged
   ```

2. **Write `tests/test_mcp_sandbox_integration.py`** with the ~9 tests. Style: pytest async function tests using `pytest.mark.asyncio`; use `MCPClient` (which internally uses sandbox-wrapped `connect_stdio`); module-level skipif on bwrap absence.

   Helpers:
   ```python
   _PROJECT_ROOT = Path(__file__).resolve().parent.parent

   def _build_naughty_source(*, sandbox: dict[str, Any] | None = None, extra_env: dict[str, str] | None = None) -> MCPSource:
       env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(_PROJECT_ROOT)}
       if extra_env:
           env.update(extra_env)
       config: dict[str, Any] = {
           "command": sys.executable,
           "args": ["-m", "tests.fixtures.mcp.hello_server", "--stdio", "--with-naughty-tools"],
           "env": env,
           "cwd": str(_PROJECT_ROOT),
       }
       if sandbox is not None:
           config["sandbox"] = sandbox
       return MCPSource(name="naughty", type="stdio", config=config, secrets={})
   ```

3. **Test-by-test guidance**:
   - **#1 FS refusal**: catch `MCPCallError`; assert message contains one of `["EROFS", "Read-only", "EACCES", "Permission denied"]`.
   - **#2 Writable mechanism**: pre-create `/var/tmp/sandbox_l5a_writable` (or use `tmp_path_factory.mktemp("sandbox_writable", numbered=False)` — but tmp_path is under `/tmp` which gets `--tmpfs`'d; use a `tmpdir` outside `/tmp`). Simplest: hardcode `/var/tmp/sandbox_l5a_test`, create+cleanup in a fixture.
   - **#3 Env allowlist**: assert HOME=="/tmp", PATH and PYTHONPATH present, host-only keys NOT present. Use `os.environ.setdefault` to set `PYTEST_CURRENT_TEST`-like sentinel, then verify it's filtered.
   - **#4 Network refusal**: target `8.8.8.8:53` IP-literal (NOT hostname); under `--unshare-net`, OS-level network namespace is empty so connect raises ENETUNREACH or similar. Tool returns string; assert on it.
   - **#5 Network allowed**: skip if `socket.create_connection(("8.8.8.8", 53), timeout=2)` from test process fails. If it works, run with `network_allowed=True` and assert "connected".
   - **#6 Writable path nonexistent**: per A02, expect `MCPConnectionError` (deferred bwrap-side translation). Assert ConnectionError NOT MCPSandboxError. Document deferral in the test docstring.
   - **#7 Sentinel leakage**: monkeypatch.setenv a unique key in TEST PROCESS; do NOT add it to `config.env`; call `dump_env()`; assert sentinel NOT in returned dict.
   - **#8/#9 Tool list directionality**: list_tools with/without `--with-naughty-tools` flag.

4. **Edge case handling**: The `--bind /tmp/...` shadowing by `--tmpfs /tmp` is a real bwrap behaviour. L3's argv compiler emits `--bind` BEFORE `--tmpfs /tmp`, so any writable_paths entry under `/tmp` gets shadowed. Document this in the flight log + add a note to the `BubblewrapSandbox.prepare_spawn` docstring or the F3 contracts in CLAUDE.md.

5. **Run all Verification Steps**. Lint must be clean.

## Edge Cases

- **`/tmp` shadowing by `--tmpfs`**: a `writable_paths=["/tmp/foo"]` entry is shadowed by the later `--tmpfs /tmp`. Document and route operators to use paths outside `/tmp`. May warrant a future routine-maintenance fix to L3's argv compiler (re-order: `--tmpfs /tmp` BEFORE `--bind` so per-path binds win), but out of scope for L5a.
- **PYTHONPATH propagation**: the fixture subprocess needs PYTHONPATH set to import `tests.fixtures.mcp.hello_server`. The operator-supplied `config.env` provides this. Tests fail-fast if this isn't set.
- **`MCPCallError` vs FastMCP error format**: FastMCP wraps tool exceptions and returns them as text content with `isError=true`. The exact error text depends on FastMCP's serialization. If a test's substring assertion fails, broaden to multiple alternative substrings.
- **Test #6 deferred behaviour**: writable_paths nonexistent → bwrap exits non-zero → stdio_client sees broken pipe → SDK initialize() fails → `MCPConnectionError`. NOT `MCPSandboxError` per L4's deferral. Document.
- **Subprocess cleanup**: each test enters/exits an `MCPClient` context; the bwrap subprocess gets SIGTERM via `--die-with-parent`. No orphan processes expected. Verify with `pgrep` if any test seems to leak.
- **Test ordering**: tests are independent; don't share state across tests.

## Files Affected

- `tests/fixtures/mcp/hello_server.py` — add `register_naughty_tools` helper + `--with-naughty-tools` CLI flag handling. Existing `make_mcp_app`/`echo`/`add`/`mcp_app` UNCHANGED.
- `tests/test_mcp_sandbox_integration.py` — NEW (~9 integration tests).
- `missions/.../flight-log.md` — append `### L5a Fixture Extension and Integration Tests`.
- `missions/.../flight.md` — tick L5a checkbox.
- `missions/.../legs/05a-...md` — flip Status.

**Explicitly NOT modified**: `the_one/` (no production code changes), `tests/conftest.py`, `tests/test_mcp_integration.py` (F2's regression), `tests/test_mcp_stdio_sandbox.py` (L4's), `tests/test_sandbox_*.py` (L2/L3's), Dockerfile, docker-compose.yml, JS, pyproject.toml, CLAUDE.md, agents.md.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] `register_naughty_tools` + `--with-naughty-tools` flag in `hello_server.py`
- [ ] Three TEST-ONLY tools with marker comments
- [ ] `tests/test_mcp_sandbox_integration.py` ~9 tests pass (some may skip)
- [ ] FS refusal proven; writable mechanism proven; env-allowlist proven; network policy proven
- [ ] No host-env leakage proven (sentinel test)
- [ ] `--with-naughty-tools` opt-in directionality proven
- [ ] F2/L2/L3/L4/F1 regression all green
- [ ] `--bind` under `/tmp` shadowing edge case documented in flight log
- [ ] `ruff check the_one/ tests/` exit 0
- [ ] Update flight-log.md with `### L5a Fixture Extension and Integration Tests`
- [ ] Set leg status to `completed`
- [ ] Tick L5a in flight.md
- [ ] **Do NOT commit** — agentic-workflow batches at flight end
