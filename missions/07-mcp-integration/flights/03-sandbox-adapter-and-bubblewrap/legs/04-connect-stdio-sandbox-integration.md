# Leg: 04-connect-stdio-sandbox-integration

**Status**: completed
**Flight**: [Local MCP Sandbox — Adapter Contract + Bubblewrap Linux Backend](../flight.md)

## Objective

Wire `BubblewrapSandbox.prepare_spawn` into `the_one/mcp/transports/stdio.py::connect_stdio` so every stdio MCP source spawns sandboxed by default. Read `config.sandbox` from the source via `SandboxProfile.from_dict`; pass the operator-assembled env/command/args/cwd through `BubblewrapSandbox.prepare_spawn(...)` to obtain a `SpawnSpec`; feed `spec.command/args/env/cwd` into `StdioServerParameters` exactly as before. Implement the §10 double-flag bypass (`THE_ONE_SANDBOX_DISABLED=1` AND `THE_ONE_TEST_MODE=1`) as the ONLY sandbox-skip path. Translate sandbox-side errors (`MCPSandboxError` from `BubblewrapSandbox()` construction, `--bind` setup failures from bwrap) per §6's failure-mode boundary. Update `mcp_fixture_stdio_params` (shape unchanged) and add `mcp_fixture_sandbox_profile` co-fixture so F2's 8 stdio integration tests (1 raw-SDK smoke unaffected; 7 through MCPClient.connect → connect_stdio) pass under the new mandatory-sandbox path. Cover with 1 real-subprocess `/bin/echo` integration test + ~6 mocked tests covering CLI shape, double-flag-bypass directionality, error boundary, and SDK env preservation through `--clearenv`/`--setenv`.

## Context

- **Mandatory sandbox for stdio sources.** Per §6, every stdio MCP source spawns sandboxed; there is no unsandboxed-fallback path. The ONLY exception is the `THE_ONE_SANDBOX_DISABLED=1 AND THE_ONE_TEST_MODE=1` double-flag, set ONLY by `tests/conftest.py::pytest_configure` for the Playwright browser-test image where MCP isn't exercised. Per §10's operational guardrail, the double flag must NEVER appear in image-level env (Dockerfile/docker-compose/k8s) — verified by L1a's defensive grep, intact today.
- **Where the sandbox wrap happens.** Per F2's debrief recommendation, the wrap lives INSIDE `connect_stdio` (NOT a parallel function). The current `connect_stdio` flow:
  ```
  command = source.config["command"]
  args    = source.config.get("args", [])
  cwd     = source.config.get("cwd")
  env     = build_stdio_environ(source, _build_subprocess_env())
  params  = StdioServerParameters(command=command, args=args, env=env, cwd=cwd)
  async with stdio_client(params) as (read, write): ...
  ```
  Becomes:
  ```
  command, args, cwd, env  = <as today>
  if _sandbox_disabled_for_tests():
      params = StdioServerParameters(command=command, args=args, env=env, cwd=cwd)
  else:
      profile = SandboxProfile.from_dict(source.config.get("sandbox") or {})
      sandbox = BubblewrapSandbox()                             # may raise MCPSandboxError if bwrap missing
      spec    = sandbox.prepare_spawn(profile, command, args, env, cwd)
      params  = StdioServerParameters(command=spec.command, args=spec.args, env=spec.env, cwd=spec.cwd)
  async with stdio_client(params) as (read, write): ...
  ```
  Layout: pull the sandbox decision into a small private helper (`_build_stdio_params(source) -> StdioServerParameters`) so `connect_stdio`'s body stays compact. Keep `build_stdio_environ` + `_build_subprocess_env` calls EXACTLY as they are today — those landed in F2 and the sandbox layer is additive on top of them.
- **Double-flag bypass helper.** Define a module-level `_sandbox_disabled_for_tests() -> bool` that returns `os.environ.get("THE_ONE_SANDBOX_DISABLED") == "1" and os.environ.get("THE_ONE_TEST_MODE") == "1"`. This function is the ONLY caller of `os.environ` for either flag in production code — keeps the double-flag invariant centralized. Tests assert directionality (both flags → bypass; only one flag → no bypass).
- **`tests/conftest.py::pytest_configure` sets `THE_ONE_TEST_MODE=1`.** Per §10, this is the ONLY place the flag is set. We add the line; we do NOT set `THE_ONE_SANDBOX_DISABLED=1` here — that would force ALL pytest runs to skip sandbox, which would defeat the purpose. `THE_ONE_SANDBOX_DISABLED=1` is set only in the Playwright browser-test CI workflow (NOT image-level env, NOT docker-compose, NOT pytest config — only the workflow's `pytest -m browser` invocation). For unit-and-integration tests inside the dev container (where bwrap is present), the bypass DOES NOT fire and the sandbox path runs.
- **`SandboxProfile.from_dict` is L2's surface.** L4 simply calls `SandboxProfile.from_dict(source.config.get("sandbox") or {})`. The `or {}` handles the case where `config.sandbox` is `None`/missing (returns strict-floor profile).
- **Failure-mode boundary (§6).**
  - `BubblewrapSandbox()` raises `MCPSandboxError` if bwrap binary missing → propagates out of `connect_stdio`. Caller (MCPClient) sees `MCPSandboxError`, knows it's a setup failure.
  - `SandboxProfile.from_dict(...)` raises `ValueError` on type-mismatched fields (per L2 §12 contract). L4 does NOT catch this — it propagates as a programmer/operator-validator error. In production, L1b's API validator should have caught it BEFORE persistence; tests that bypass the API layer (constructing `MCPSource` directly) reveal this propagation, which is the correct boundary: profile-shape errors are programmer errors, not sandbox setup errors.
  - `BubblewrapSandbox.prepare_spawn(...)` is pure logic and never raises (its `__init__` already validated bwrap presence; argv compilation has no I/O).
  - `stdio_client(params)` failures: bwrap exits non-zero from `--bind` setup (writable_paths nonexistent, etc.), or namespace creation refused (`EPERM` on `unshare`), or seccomp denies a syscall — these surface as `stdio_client` failing to connect, OR as the SDK's initialize handshake timing out. **Per §6**, these *should* be translated into `MCPSandboxError` (catalog messages: "bubblewrap exited with code {n}", "namespace creation refused (EPERM on unshare)"). However, distinguishing "bwrap exited from setup" vs "wrapped target exited from its own bug" inside `stdio_client`'s error paths is not reliably possible without scraping stderr or exit codes — and L3 already validated bwrap presence at construction. **Decision for this leg (deferred work)**: L4 does NOT add bwrap-side error translation; post-spawn failures continue to surface via F2's existing `MCPConnectionError` translation in `MCPClient.connect()`. The §6 catalog's "bwrap exited with code {n}" / "EPERM on unshare" messages are NOT emitted by L4. **This is a deviation from §6's letter**, documented as a known gap to be addressed in a follow-up routine-maintenance pass via stderr scraping or bwrap exit-code inspection. Recorded in the flight log as a Known Issue / Anomaly entry.
- **Test fixture sandbox-aware shape.** Per flight spec:
  - `mcp_fixture_stdio_params` return-shape is **unchanged** (still a dict compatible with `StdioServerParameters(**params)`). The fixture's role is to spell out what command/args/env/cwd to send the SDK; whether the SDK gets a bwrap-wrapped or bare-shape depends on the test's caller. Tests that drive `stdio_client(StdioServerParameters(**fixture))` DIRECTLY (bypassing `connect_stdio`) continue to spawn unsandboxed — they're testing the SDK's wire-shape, not the sandbox. Tests that drive `connect_stdio(source)` (e.g., via MCPClient) automatically pick up the sandbox.
  - Add a NEW fixture `mcp_fixture_sandbox_profile` returning the strict-floor `SandboxProfile()` — empty `writable_paths`, `network_allowed=False`, all `*_unshare=True`. Tests that need writable paths or network extend the profile per-test (e.g., `mcp_fixture_sandbox_profile.replace(writable_paths=["/tmp"])` — but `replace()` is from `dataclasses`, not from the fixture; tests can construct `SandboxProfile(writable_paths=...)` directly).
  - **F2 stdio test path (verified at design time)**: `tests/test_mcp_integration.py` has 8 stdio tests. **1 test (`test_stdio_smoke_via_raw_sdk`) drives `stdio_client(StdioServerParameters(**fixture))` directly** — it tests the SDK wire-shape, not the sandbox; remains unsandboxed and unaffected by L4. **7 tests go through `MCPClient(source).connect()` → `connect_stdio`** — they will pick up the sandbox path automatically under L4. Their in-test `MCPSource` instances have no `config.sandbox` block, so each gets the strict-floor profile via `SandboxProfile.from_dict({})`. The hello fixture (FastMCP echo+add) does not write to disk and does not make network calls — strict-floor profile (read-only FS, no network) should suffice.
  - **If a sandboxed F2 test fails**: investigate root cause. Most likely fix is to add `config["sandbox"] = {"writable_paths": ["/tmp/some/scratch"]}` to the in-test `MCPSource`, OR (less likely) the FastMCP runtime needs `network_allowed=True`. Document any required test changes in the flight log entry.
- **Test list for L4** (per flight Adaptation Criteria):
  - 1 **real-subprocess integration test** using `/bin/echo` — verifies the compiled bwrap argv actually runs end-to-end inside the dev container. This is the integration-boundary test L3 deferred. Mark `@pytest.mark.integration` so it can be skipped in environments without bwrap (e.g., HAT-on-host fallback).
  - ~6 **mocked tests** covering:
    - (a) bwrap CLI shape correctness — `connect_stdio` reads `config.sandbox` and passes the right profile to `prepare_spawn`. Mock `BubblewrapSandbox.prepare_spawn` and assert the args it received.
    - (b) Double-flag bypass WORKS — `THE_ONE_SANDBOX_DISABLED=1 + THE_ONE_TEST_MODE=1` set → `BubblewrapSandbox` not instantiated; `stdio_client` gets the bare params.
    - (c) Double-flag bypass DOES NOT trigger when only `THE_ONE_SANDBOX_DISABLED=1` is set.
    - (d) Double-flag bypass DOES NOT trigger when only `THE_ONE_TEST_MODE=1` is set.
    - (e) `MCPSandboxError` boundary — when `BubblewrapSandbox()` raises (mock `shutil.which` to return None, AND ensure double-flag is NOT set), `connect_stdio` re-raises `MCPSandboxError` (does NOT swallow or translate to `MCPConnectionError`).
    - (f) **SDK default env preservation** — mock `stdio_client` and assert that `StdioServerParameters.env` passed in includes the SDK's `get_default_environment()` keys + the operator's allowlist + operator env. The bwrap `--clearenv` + per-key `--setenv` round-trip preserves all of them. (This is the §11 question Q4 from the architect cycle that L4 is on the hook to verify.)
- **Real-subprocess integration test details.** Spawn `/bin/cat` (NOT `/bin/echo` — `/bin/cat` reads stdin indefinitely and won't exit before stdio_client's first read, avoiding a race condition where `/bin/echo` exits faster than stdio_client opens its read end). Synthetic `MCPSource(type="stdio", config={"command": "/bin/cat", "args": []})`. Drive via `connect_stdio(source)` directly (NOT MCPClient — MCPClient.connect translates exceptions to `MCPConnectionError`; `connect_stdio` itself does NOT). Test assertion shape:
  ```python
  with pytest.raises(BaseException) as exc_info:
      async with connect_stdio(source) as session:
          # initialize() will fail because cat isn't a real MCP server,
          # but we should at least get into this body if the sandbox wrap worked
          await asyncio.wait_for(session.initialize(), timeout=2.0)
  assert not isinstance(exc_info.value, MCPSandboxError), \
      f"Sandbox setup failed: {exc_info.value}"
  ```
  Success criterion: any exception EXCEPT `MCPSandboxError`. The handshake will fail (cat isn't JSON-RPC); we don't care. Whatever `stdio_client` raises (likely `anyio.BrokenResourceError`, `ExceptionGroup`, or `TimeoutError`) is acceptable — those are post-spawn errors proving the sandbox boundary was crossed. Mark `@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bwrap not available")` since the test requires real bwrap. (Don't use `@pytest.mark.integration` — that marker isn't registered in `pyproject.toml`'s test config and would warn.)
- **Per-leg lint gate**: `ruff check the_one/ tests/` clean.
- **Citation style**: anchor by symbol-name. F2's `connect_stdio`, `build_stdio_environ`, `_build_subprocess_env` are the prerequisites; L2's `BubblewrapSandbox`, `SandboxProfile`, `SpawnSpec`, `MCPSandboxError` are the integration target.

## Inputs

- L1a, L1b, L2, L3 all `completed`. Dev container has `bwrap 0.11.0`. F3 contracts in CLAUDE.md / agents.md. `BubblewrapSandbox.__init__` validates bwrap; `prepare_spawn` compiles correct argv.
- `the_one/mcp/transports/stdio.py::connect_stdio` exists per F2; current shape spawns subprocess directly via `stdio_client(StdioServerParameters(...))` with no sandbox.
- `the_one/mcp/transports/stdio.py::build_stdio_environ` exists per F2; flat-merges allowlist + config.env + secrets. L4 does NOT modify this function.
- `the_one/platform/env.py::_build_subprocess_env` exists per F4 (mission 04 / 06 — different mission F4, not THIS flight's F4). L4 does NOT modify.
- `the_one/platform/sandbox/{__init__.py, base.py, bubblewrap.py}` exist per L2/L3.
- `tests/conftest.py::mcp_fixture_stdio_params` exists per F2 L3; returns a dict for `StdioServerParameters(**fixture)`.
- `tests/conftest.py` does NOT currently have a `pytest_configure` hook OR `THE_ONE_TEST_MODE` setter — L4 adds the hook.
- `tests/test_mcp_integration.py` exists per F2 with ~14 stdio integration tests (count to be verified at implementation time). At least some go through `MCPClient` (and hence `connect_stdio`) — those are the ones that pick up the sandbox path automatically and need to keep passing.

## Outputs

- **`the_one/mcp/transports/stdio.py` modified**:
  - Module-level imports gain: `import os`, `from the_one.mcp.errors import MCPSandboxError` (canonical home — already exists), `from the_one.platform.sandbox import BubblewrapSandbox, SandboxProfile`.
  - New module-level helper `_sandbox_disabled_for_tests() -> bool`:
    ```python
    def _sandbox_disabled_for_tests() -> bool:
        """Test-only sandbox bypass per §10. Returns True ONLY when BOTH flags
        are set (belt-and-suspenders against accidental production activation).
        Production sets neither flag.
        """
        return (
            os.environ.get("THE_ONE_SANDBOX_DISABLED") == "1"
            and os.environ.get("THE_ONE_TEST_MODE") == "1"
        )
    ```
  - New private helper `_build_stdio_params(source: MCPSource) -> StdioServerParameters` that encapsulates the env-build + sandbox-decision + StdioServerParameters construction. `connect_stdio` calls this helper.
  - `connect_stdio`'s body becomes:
    ```python
    @asynccontextmanager
    async def connect_stdio(source: MCPSource) -> AsyncIterator[ClientSession]:
        params = _build_stdio_params(source)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                yield session
    ```
  - Module docstring updated: appends a paragraph describing the sandbox wrap, the double-flag bypass, and §6's failure-mode boundary.

- **`tests/conftest.py` modified**:
  - Add `pytest_configure(config)` hook (or extend an existing one if present) that sets `os.environ["THE_ONE_TEST_MODE"] = "1"`. Per §10, this is the ONLY place the flag is set in non-production code.
  - Add a NEW fixture `mcp_fixture_sandbox_profile` returning `SandboxProfile()` (strict-floor — empty writable_paths, network_allowed=False, all unshare flags True). Tests that need network/writable extend per-test by constructing a SandboxProfile inline.
  - `mcp_fixture_stdio_params` shape unchanged.

- **`tests/test_mcp_stdio_sandbox.py`** — NEW test file. ~7 tests:
  1. `test_connect_stdio_invokes_bubblewrap_when_flag_off` (mocked) — patch `BubblewrapSandbox` with a mock; assert it's instantiated and `prepare_spawn` called with the operator's command/args/env/cwd plus a strict-floor `SandboxProfile`.
  2. `test_connect_stdio_passes_config_sandbox_to_profile` (mocked) — set `source.config["sandbox"] = {"writable_paths": ["/data"], "network_allowed": True}`; assert the `SandboxProfile` passed to `prepare_spawn` reflects it.
  3. `test_connect_stdio_double_flag_bypass_skips_sandbox` (mocked) — set BOTH `THE_ONE_SANDBOX_DISABLED=1` AND `THE_ONE_TEST_MODE=1` via monkeypatch; mock `BubblewrapSandbox` so we'd notice if it were called; assert the mock was NOT called and `stdio_client` got the bare params.
  4. `test_connect_stdio_only_sandbox_disabled_flag_does_not_bypass` (mocked) — set `THE_ONE_SANDBOX_DISABLED=1` but NOT `THE_ONE_TEST_MODE`; assert `BubblewrapSandbox` IS called.
  5. `test_connect_stdio_only_test_mode_flag_does_not_bypass` (mocked) — set `THE_ONE_TEST_MODE=1` but NOT `THE_ONE_SANDBOX_DISABLED`; assert `BubblewrapSandbox` IS called. (Note: by default `tests/conftest.py::pytest_configure` SETS `THE_ONE_TEST_MODE=1` for all tests; this test is asserting that the flag-alone is insufficient to bypass — which is the conftest baseline behaviour anyway. Test uses the conftest-set TEST_MODE and verifies sandbox runs.)
  6. `test_connect_stdio_propagates_mcpsandbox_error_when_bwrap_missing` (mocked) — patch `shutil.which` to return None AND ensure bypass flags are off; assert `connect_stdio(source)` raises `MCPSandboxError` (does NOT swallow or translate).
  7. `test_connect_stdio_sdk_default_env_preserved_through_setenv` (mocked) — mock `stdio_client` to capture the StdioServerParameters it receives; assert the env dict contains the operator's allowlist+config keys (HOME=/tmp from sandbox override). The "SDK default env" question (architect Q4): the SDK's `get_default_environment()` is applied INSIDE `stdio_client` to whatever env we pass; `stdio_client(params)` sees `params.env` (which is the bwrap-wrapped post-setenv env). The SDK then layers ITS defaults UNDER our env. Assertion: our env (operator + allowlist + HOME=/tmp) survives the round-trip.
  8. `test_connect_stdio_real_subprocess_cat_integration` (REAL subprocess, `@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bwrap not available")`) — `MCPSource(type="stdio", config={"command": "/bin/cat", "args": []})`; `async with connect_stdio(source)` is expected to fail (cat isn't a real MCP server) with ANY exception OTHER than `MCPSandboxError`. The success criterion is "the sandbox boundary was crossed" — see Real-subprocess integration test details in §Context for the assertion shape.
  9. `test_connect_stdio_propagates_sandbox_profile_validation_error` (mocked at the SandboxProfile boundary) — operator submits `MCPSource(config={"command": "/bin/echo", "sandbox": {"network_allowed": 42}})`; assert `connect_stdio(source)` propagates `ValueError` from `SandboxProfile.from_dict` (NOT translated to `MCPSandboxError`). Anchors the boundary: profile-shape errors are programmer/validator errors at the API edge; sandbox-setup errors are `MCPSandboxError`. (In production, the L1b API validator catches malformed `config.sandbox` before it reaches `connect_stdio`; in-test bypass-the-validator MCPSources reveal this propagation.)

  Tests use the existing `mcp_fixture_stdio_params` for command/args base values; build `MCPSource` instances in-test for the various configs (sandbox sub-block variations, edge cases). Note: the new `mcp_fixture_sandbox_profile` fixture is added in this leg per the flight spec but is NOT consumed by L4's tests — it's a forward-looking fixture for L5a's integration tests, where it will be used to compose strict-floor + per-test profile overrides. Documenting up-front so reviewers don't flag it as dead code.

- **`tests/test_mcp_integration.py` may need a tweak**: F2's existing 14 stdio tests. Reconnaissance at implementation time:
  - If they all use `stdio_client(StdioServerParameters(**fixture))` directly (bypassing `connect_stdio`), no change needed — they're not exercising the sandbox.
  - If any go through `MCPClient.connect()` (which internally calls `connect_stdio`), they will pick up the sandbox path. Most likely outcome: the strict-floor profile suffices for the hello fixture (no writes, no network), and tests pass without modification. If a test DOES need writable paths or network, set `config.sandbox` on the in-test MCPSource.
  - If tests fail under the new sandbox path, debug case-by-case. Document any test changes in the flight log.

- **Flight artifacts**:
  - `flight-log.md` gets `### L4 connect_stdio Sandbox Integration` under `## Leg Progress`.
  - `flight.md` checkbox ticked under `### Legs`.
  - `legs/04-...md` Status flipped to `completed`.

## Acceptance Criteria

- [ ] **`connect_stdio` wraps via `BubblewrapSandbox.prepare_spawn`**: when bypass flags are NOT both set, `BubblewrapSandbox()` is instantiated and `prepare_spawn(profile, command, args, env, cwd)` is called with `profile = SandboxProfile.from_dict(source.config.get("sandbox") or {})`. The returned `SpawnSpec.command/args/env/cwd` are passed to `StdioServerParameters`.
- [ ] **Double-flag bypass works**: `THE_ONE_SANDBOX_DISABLED=1 AND THE_ONE_TEST_MODE=1` → `BubblewrapSandbox` is NOT instantiated; `stdio_client` receives the bare `command/args/env/cwd`.
- [ ] **Single-flag does not bypass**: only `THE_ONE_SANDBOX_DISABLED=1` (without TEST_MODE) → sandbox runs. Only `THE_ONE_TEST_MODE=1` (without SANDBOX_DISABLED) → sandbox runs.
- [ ] **`MCPSandboxError` propagates**: when `BubblewrapSandbox()` raises (bwrap missing AND bypass not active), `connect_stdio` propagates `MCPSandboxError` to the caller without swallowing or translating.
- [ ] **SDK env preservation**: the env passed into `stdio_client` (via `StdioServerParameters.env`) is the operator-assembled env with HOME forced to `/tmp` (when sandbox is active) or the operator-assembled env unchanged (when bypass is active). In both cases, the operator's allowlist + config.env + secrets are present.
- [ ] **`tests/conftest.py::pytest_configure` sets `THE_ONE_TEST_MODE=1`**: verifiable by `os.environ.get("THE_ONE_TEST_MODE")` returning `"1"` inside any test. This is the ONLY place the flag is set; no Dockerfile/docker-compose/k8s/scripts reference per L1a's defensive grep (still intact).
- [ ] **`mcp_fixture_sandbox_profile` co-fixture exists**: returns strict-floor `SandboxProfile()` (empty writable_paths, network_allowed=False, all unshare True).
- [ ] **`mcp_fixture_stdio_params` shape unchanged**: still returns a dict compatible with `StdioServerParameters(**fixture)` per F2's contract.
- [ ] **`tests/test_mcp_stdio_sandbox.py` ~9 tests all pass** (8 mocked + 1 real-subprocess integration test, the latter skipped if bwrap unavailable on the test runner).
- [ ] **F2's `tests/test_mcp_integration.py` regression**: ALL 14+ existing stdio integration tests still pass under the new mandatory-sandbox path. If any test required modification (e.g., adding a sandbox sub-block to an in-test MCPSource), document the change in the flight log entry.
- [ ] **`tests/test_sandbox_bubblewrap.py` (L3) and `tests/test_sandbox_contract.py` (L2) regression**: still green.
- [ ] **Lint clean**: `ruff check the_one/ tests/` exits 0.
- [ ] **`THE_ONE_TEST_MODE` operational guardrail intact**: `grep -RIn 'THE_ONE_TEST_MODE' Dockerfile docker-compose.yml scripts/ Makefile 2>/dev/null` returns no matches.
- [ ] **No source-code changes outside the leg-allowed paths**: `git status --porcelain` shows only `the_one/mcp/transports/stdio.py`, `tests/conftest.py`, `tests/test_mcp_stdio_sandbox.py`, optionally `tests/test_mcp_integration.py` (only if F2 tests required modification — document the change in the flight log), plus flight artifacts.
- [ ] **Flight log + flight + leg-status updates** per the per-leg checklist.

## Verification Steps

```bash
cd /home/cprch/projects/the-one

# --- 1. Diff scope ---
git status --porcelain
# Expect modifications under:
#   the_one/mcp/transports/stdio.py            (M)
#   tests/conftest.py                           (M)
#   tests/test_mcp_stdio_sandbox.py             (??)
#   tests/test_mcp_integration.py               (M, only if F2 tests required modification)
#   missions/.../flight.md                      (M)
#   missions/.../flight-log.md                  (M)
#   missions/.../legs/04-...md                  (M)
# No other modifications.

# --- 2. New L4 tests pass ---
docker compose exec -T the-one python -m pytest tests/test_mcp_stdio_sandbox.py -v
# Expect: ~6 mocked tests pass; 1 integration test passes (or is skipped if bwrap unavailable).

# --- 3. F2 stdio regression (14 tests) still passes ---
docker compose exec -T the-one python -m pytest tests/test_mcp_integration.py -v
# Expect: all green; count unchanged from F2.

# --- 4. L2 + L3 regression ---
docker compose exec -T the-one python -m pytest tests/test_sandbox_contract.py tests/test_sandbox_bubblewrap.py -v
# Expect: all green.

# --- 5. F1 API regression ---
docker compose exec -T the-one python -m pytest tests/test_db_api.py::TestMCPSourceAPI -v
# Expect: 16 passed (per L1b).

# --- 6. THE_ONE_TEST_MODE operational guardrail ---
grep -RIn 'THE_ONE_TEST_MODE' Dockerfile docker-compose.yml scripts/ Makefile 2>/dev/null
# Expect: no matches.

# --- 7. THE_ONE_TEST_MODE set by conftest (verified internally by test #5) ---
# The test_connect_stdio_only_test_mode_flag_does_not_bypass test internally
# verifies that THE_ONE_TEST_MODE=1 (set by conftest's pytest_configure) plus
# absence of THE_ONE_SANDBOX_DISABLED still results in sandbox running.
# No external grep needed.

# --- 8. Lint ---
docker compose exec -T the-one ruff check the_one/ tests/
# Expect: All checks passed.

# --- 9. Manual smoke: real bwrap-wrapped /bin/echo subprocess starts ---
docker compose exec -T the-one python -c "
import asyncio
from the_one.db.models import MCPSource
from the_one.mcp.transports.stdio import connect_stdio
from the_one.mcp.errors import MCPSandboxError, MCPConnectionError

src = MCPSource(name='smoke', type='stdio', config={'command': '/bin/echo', 'args': ['hello']}, secrets={})

async def run():
    try:
        async with connect_stdio(src) as session:
            print('past sandbox boundary')
    except MCPSandboxError as e:
        print(f'SANDBOX ERROR: {e}')
        raise
    except Exception as e:
        # Any post-spawn error is acceptable (echo isn't an MCP server)
        print(f'expected post-spawn error: {type(e).__name__}: {e}')

asyncio.run(run())
"
# Expect: 'expected post-spawn error: ...' (NOT 'SANDBOX ERROR'); the bwrap wrap completed.

# --- 10. connect_stdio uses sandbox by default in dev container ---
docker compose exec -T the-one python -c "
import os
# Default dev container has TEST_MODE=1 from conftest, but TEST_MODE alone doesn't bypass.
# Production has neither flag.
print('SANDBOX_DISABLED:', os.environ.get('THE_ONE_SANDBOX_DISABLED', '<unset>'))
print('TEST_MODE:', os.environ.get('THE_ONE_TEST_MODE', '<unset>'))
"
```

If any verification fails:
1. Do NOT signal `[COMPLETE:leg]`.
2. Capture failing output in flight log under `## Anomalies`.
3. Diagnose: most likely (a) `os.environ` check happens at module import time instead of call time (cache the function result?? — NO, must be call-time for the bypass to be testable via monkeypatch), (b) `tests/conftest.py::pytest_configure` doesn't actually run for the test session (need to verify hook discovery), (c) F2 stdio tests fail because the hello fixture needs a writable_paths entry (e.g., `/tmp` for FastMCP's internal state) — fix by adding to `mcp_fixture_sandbox_profile` if so, OR document as a test-modification case, (d) the SDK env preservation test fails because the SDK's `get_default_environment()` injects keys we didn't account for (architect Q4 — investigate at impl time and document).

## Implementation Guidance

1. **Read the full F2 `connect_stdio`** before editing. Confirm the current body matches the L4 leg's expected pre-state.

2. **Add module-level imports** to `the_one/mcp/transports/stdio.py`:
   ```python
   import os

   from the_one.platform.sandbox import BubblewrapSandbox, SandboxProfile
   ```
   Note: do NOT import `MCPSandboxError` directly — L4 doesn't raise it (the constructor `BubblewrapSandbox()` raises it; the call propagates without re-raising). Importing it would trigger ruff's `F401` unused-import. The error class is named in the module docstring's failure-mode prose for human readers, but ruff doesn't track docstring references.

3. **Add `_sandbox_disabled_for_tests`** helper above `_build_stdio_params`:
   ```python
   def _sandbox_disabled_for_tests() -> bool:
       """Test-only sandbox bypass per F3 §10.

       Returns True ONLY when BOTH `THE_ONE_SANDBOX_DISABLED=1` AND
       `THE_ONE_TEST_MODE=1` are present in the process env. The double flag
       is belt-and-suspenders: production sets neither; pytest sets only
       `THE_ONE_TEST_MODE` (via tests/conftest.py); the Playwright browser-test
       CI workflow sets both for its `pytest -m browser` invocation only.

       Per §10's operational guardrail, `THE_ONE_TEST_MODE` MUST NOT appear
       in any Dockerfile, docker-compose, entrypoint script, k8s manifest, or
       CI variable — its presence outside pytest is a deployment defect.
       """
       return (
           os.environ.get("THE_ONE_SANDBOX_DISABLED") == "1"
           and os.environ.get("THE_ONE_TEST_MODE") == "1"
       )
   ```

4. **Refactor `connect_stdio` body**: extract the env-build + sandbox-decision + params-construction into `_build_stdio_params(source)`. Sketch:

   ```python
   def _build_stdio_params(source: MCPSource) -> StdioServerParameters:
       """Build StdioServerParameters for an MCPSource, applying sandbox wrap
       unless the F3 §10 double-flag bypass is set.
       """
       command: str = source.config["command"]
       args: list[str] = source.config.get("args", [])
       cwd: str | None = source.config.get("cwd")
       env = build_stdio_environ(source, _build_subprocess_env())

       if _sandbox_disabled_for_tests():
           return StdioServerParameters(command=command, args=args, env=env, cwd=cwd)

       profile = SandboxProfile.from_dict(source.config.get("sandbox") or {})
       sandbox = BubblewrapSandbox()  # may raise MCPSandboxError if bwrap missing
       spec = sandbox.prepare_spawn(profile, command, args, env, cwd)
       return StdioServerParameters(
           command=spec.command,
           args=spec.args,
           env=spec.env,
           cwd=spec.cwd,
       )


   @asynccontextmanager
   async def connect_stdio(source: MCPSource) -> AsyncIterator[ClientSession]:
       """Open an entered ClientSession over (sandboxed) stdio transport.

       (... existing docstring; append paragraph on sandbox wrap ...)
       """
       params = _build_stdio_params(source)
       async with stdio_client(params) as (read, write):
           async with ClientSession(read, write) as session:
               yield session
   ```

5. **Update `__all__`**: add `_sandbox_disabled_for_tests` and `_build_stdio_params` ONLY if they're meant to be public — they're underscore-prefixed so probably NOT in `__all__`. Keep `__all__ = ["build_stdio_environ", "connect_stdio"]` unchanged (the helpers are private).

6. **Update module docstring**: append a paragraph after the existing "See flight 02 design decision §11" line:

   > **F3 sandbox wrap (mission 07 flight 03 L4)**: every stdio MCP source spawns
   > sandboxed via `BubblewrapSandbox.prepare_spawn`. The wrap reads
   > `MCPSource.config["sandbox"]` (optional dict; defaults to strict-floor) and
   > applies bwrap's `--clearenv` + `--setenv` env-allowlist enforcement,
   > `--ro-bind / /` + `--bind PATH PATH` filesystem scope, `--unshare-net`
   > network policy (when `network_allowed=False`), and `--die-with-parent`
   > process supervision. The ONLY skip path is the
   > `THE_ONE_SANDBOX_DISABLED=1 AND THE_ONE_TEST_MODE=1` double-flag bypass
   > (set by tests/conftest.py + Playwright CI only). `MCPSandboxError` from
   > sandbox setup propagates; post-spawn errors continue to surface as F2's
   > `MCPConnectionError`.

7. **Modify `tests/conftest.py`**:
   - Add `pytest_configure(config)` hook (or add to one if present):
     ```python
     def pytest_configure(config: pytest.Config) -> None:
         """Set THE_ONE_TEST_MODE=1 for all pytest runs (F3 §10).

         The companion flag THE_ONE_SANDBOX_DISABLED is NOT set here — it's set
         only by the Playwright browser-test CI workflow's `pytest -m browser`
         invocation. With only THE_ONE_TEST_MODE=1, the sandbox wrap stays
         active for unit + integration tests in environments where bwrap is
         present (dev container post-L1a).
         """
         os.environ.setdefault("THE_ONE_TEST_MODE", "1")
     ```
     Use `setdefault` so existing values are preserved (the CI workflow may set both flags before pytest runs).
   - Add new fixture below `mcp_fixture_stdio_params`:
     ```python
     @pytest.fixture
     def mcp_fixture_sandbox_profile() -> SandboxProfile:
         """Strict-floor SandboxProfile for L4+ sandbox-aware integration tests.

         Tests needing writable paths or network construct a SandboxProfile inline.
         """
         from the_one.platform.sandbox import SandboxProfile
         return SandboxProfile()
     ```
     Or import `SandboxProfile` at top-of-file with the other imports.

8. **Write `tests/test_mcp_stdio_sandbox.py`** with the ~7 tests from §Outputs. Use `monkeypatch` for env-flag manipulation, `unittest.mock.patch` for `BubblewrapSandbox` substitution, `unittest.mock.AsyncMock` or pytest's mocker for async-context-manager mocking around `stdio_client`. Mark the integration test with `@pytest.mark.integration` (the project may already have this marker; check `pyproject.toml::tool.pytest.ini_options.markers`).

9. **Run F2 `tests/test_mcp_integration.py`** to surface any sandbox-related regressions. Expected outcomes:
   - Tests that DON'T go through `connect_stdio` (use `stdio_client` directly): unaffected.
   - Tests that DO go through `connect_stdio` via `MCPClient.connect()`: now run sandboxed. The hello fixture is a FastMCP server that doesn't write to disk and doesn't make network calls — strict-floor profile should suffice. If a test fails:
     - First, investigate: is the failure due to `bwrap` not being where expected? `MCPSandboxError`? bwrap exit non-zero from setup?
     - Most likely fix: the in-test `MCPSource` needs a `config.sandbox` block. For example, if FastMCP needs a writable scratch dir, set `config.sandbox = {"writable_paths": ["/tmp/mcp-test"]}` and `os.makedirs("/tmp/mcp-test", exist_ok=True)` in the fixture or test setup.
     - Document any test changes in the flight log entry.

10. **Manual smoke** the real-subprocess path with `/bin/echo` per Verification Steps §9.

11. **Run all Verification Steps** before signalling `[HANDOFF:review-needed]`.

## Edge Cases

- **`source.config.get("sandbox")` is `None`**: `or {}` falls through to empty dict; `SandboxProfile.from_dict({})` returns strict-floor profile. Behaviour: sandbox is active with safe defaults.
- **`source.config["sandbox"]` is empty dict**: same as above (strict-floor). Verified by L2's `from_dict` tests.
- **Operator's env contains `THE_ONE_SANDBOX_DISABLED=1` but operator IS a real production user**: the §10 operational guardrail and L1a's defensive grep make this nearly impossible — but if a malicious actor managed to set this flag, the second check (`THE_ONE_TEST_MODE`) would still need to be true. Production never sets `TEST_MODE`. Defense-in-depth.
- **`os.environ` modified mid-test by another fixture**: `_sandbox_disabled_for_tests()` reads at call time, so the most-recent values win. Tests using monkeypatch get the expected behaviour.
- **`BubblewrapSandbox()` slow construction**: not slow today (just `shutil.which`); future routine maintenance might cache the validation result. L4 doesn't optimize.
- **Concurrency**: `connect_stdio` is async-context-manager; multiple concurrent `connect_stdio` calls each create their own `BubblewrapSandbox()` instance and `prepare_spawn` invocation. No shared state; no concurrency bug.
- **F2 test that exercises `connect_stdio` and fails under sandbox**: investigate root cause empirically (the FastMCP fixture's exact write/network needs are not pre-known). The strict-floor profile is the working hypothesis; if it's insufficient, the most likely fixes are (a) add a writable scratch path to the in-test `MCPSource.config["sandbox"]["writable_paths"]`, or (b) discover the test depends on host network reachability. Document observations in the flight log.
- **`tests/browser/conftest.py` already has a `pytest_configure` hook** (snapshot-update bridge). pytest collects both top-level and browser-subdir conftest hooks; both run in turn. No interaction between L4's hook (sets `THE_ONE_TEST_MODE`) and the existing browser hook. No conflict.
- **L4's mocked tests vs. the L1a-verified bwrap behaviour**: mocked tests verify `connect_stdio` makes the right CALLS into the sandbox layer; the real-subprocess test verifies the calls actually run end-to-end. L1a's 5-assertion probe verified bwrap itself works in the dev container. L3's argv-compilation tests verified the compiler emits the right shape. Together: contract → compiler → integration. No gap.

## Files Affected

- `the_one/mcp/transports/stdio.py` — extend with `_sandbox_disabled_for_tests`, `_build_stdio_params` helpers; refactor `connect_stdio` body to call `_build_stdio_params`. Update module docstring.
- `tests/conftest.py` — add `pytest_configure` hook setting `THE_ONE_TEST_MODE=1`; add `mcp_fixture_sandbox_profile` fixture.
- `tests/test_mcp_stdio_sandbox.py` — NEW (~7 tests).
- `tests/test_mcp_integration.py` — CONDITIONAL modification (only if F2 tests require sandbox-block additions; document any change in the flight log).
- `missions/.../flight-log.md` — append `### L4 connect_stdio Sandbox Integration`.
- `missions/.../flight.md` — tick L4 checkbox.
- `missions/.../legs/04-connect-stdio-sandbox-integration.md` — flip Status.

**Explicitly NOT modified**: `the_one/platform/sandbox/` (L2/L3 done), `the_one/mcp/errors.py`, `the_one/interfaces/web/api.py`, `tests/fixtures/mcp/hello_server.py` (L5a's surface), JS, Dockerfile, docker-compose.yml, Makefile, pyproject.toml, CLAUDE.md, agents.md.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] `connect_stdio` wraps via `BubblewrapSandbox` when bypass not active
- [ ] Double-flag bypass works (both flags); single-flag does not
- [ ] `MCPSandboxError` propagates from sandbox setup failures
- [ ] SDK env preservation verified through `--clearenv`/`--setenv` round-trip
- [ ] `pytest_configure` sets `THE_ONE_TEST_MODE=1` (one place only)
- [ ] `mcp_fixture_sandbox_profile` co-fixture exists; strict-floor
- [ ] `mcp_fixture_stdio_params` shape unchanged
- [ ] `tests/test_mcp_stdio_sandbox.py` ~7 tests pass (mocked + 1 real-subprocess integration)
- [ ] F2 `tests/test_mcp_integration.py` regression: ALL existing tests still pass; document any required test changes
- [ ] L2 + L3 contract/backend tests still green
- [ ] F1 API tests still green
- [ ] `ruff check the_one/ tests/` exit 0
- [ ] `THE_ONE_TEST_MODE` operational guardrail intact (no image-level env references)
- [ ] `git status --porcelain` shows only the leg-allowed paths
- [ ] Update flight-log.md with `### L4 connect_stdio Sandbox Integration` (Started/Completed + 4-line summary + test counts + any F2-regression-test-modifications + lint clean + bwrap-error-translation deferral note)
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in flight.md (under `### Legs`)
- [ ] **Do NOT commit** — agentic-workflow batches commits at flight end
