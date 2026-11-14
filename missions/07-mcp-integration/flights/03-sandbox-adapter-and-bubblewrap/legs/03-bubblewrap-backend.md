# Leg: 03-bubblewrap-backend

**Status**: completed
**Flight**: [Local MCP Sandbox — Adapter Contract + Bubblewrap Linux Backend](../flight.md)

## Objective

Replace `BubblewrapSandbox.prepare_spawn`'s `NotImplementedError` stub with a real bwrap argv compiler that turns `(SandboxProfile, command, args, env, cwd)` into a `SpawnSpec(command="bwrap", args=[...wrapped...], env=<assembled_env_with_HOME_override>, cwd=cwd)`. Validate `bwrap` presence at `__init__` time via `shutil.which("bwrap")`, raising `MCPSandboxError` per §6's catalog if missing. Apply the §13 `HOME → /tmp` override unconditionally. Cover with ~14 unit tests of the argv compilation — pure logic, **no real subprocess in any test** (L1a's 5-assertion probe already stake-tested that the argv shape we compile here actually executes; L4's `/bin/echo` integration test is the next-leg surface).

## Context

- **Pure arg-compilation leg.** No subprocess.Popen, no real bwrap exec, no `connect_stdio` integration. Tests build `SandboxProfile` + command/args/env/cwd inputs, call `prepare_spawn`, and assert on the returned `SpawnSpec.command/args/env/cwd` shape. Real bwrap behaviour was already verified in L1a's probe (5 assertions, including `--chdir /tmp` cwd-handling stake-test and `--unshare-net` network-refusal stake-test); L3 only needs to prove the argv we emit matches what L1a proved works.
- **Eager validation at `__init__` time.** Per flight §6's error catalog, `shutil.which("bwrap")` is checked once at `BubblewrapSandbox()` construction. If missing → raise `MCPSandboxError` with the exact §6 message verbatim ("MCP sandbox setup failed: bubblewrap binary not found in PATH. Install with: apt-get install bubblewrap. In test environments only, set THE_ONE_SANDBOX_DISABLED=1 with THE_ONE_TEST_MODE=1."). This catches deployment misconfiguration immediately rather than at first-spawn time. The L4 double-flag bypass (`THE_ONE_SANDBOX_DISABLED=1 + THE_ONE_TEST_MODE=1`) is L4's surface — L3 simply raises if bwrap is missing; L4 decides whether to even instantiate `BubblewrapSandbox` based on the double flag.
- **Argv structure (flight Technical Approach)**: the compiled bwrap argv MUST contain in this order:
  1. `--die-with-parent` (always; process-supervision floor)
  2. `--unshare-user` (always; namespace isolation floor)
  3. `--unshare-pid` IF `profile.pid_unshare` (default True)
  4. `--unshare-ipc` IF `profile.ipc_unshare` (default True)
  5. `--unshare-uts` IF `profile.uts_unshare` (default True)
  6. `--unshare-net` IF NOT `profile.network_allowed`
  7. `--clearenv` (always; env-allowlist enforcement)
  8. `--setenv KEY VALUE` for each entry of the assembled env (with HOME forced to `/tmp`); deterministic ordering (sorted by key) so tests can stake on it
  9. `--ro-bind / /` (always; read-only rootfs floor)
  10. `--bind PATH PATH` for each entry of `profile.writable_paths` (preserves operator order; relative-path semantics are bwrap's problem at exec time per "trust the runtime")
  11. `--proc /proc` (always; minimal /proc furniture)
  12. `--dev /dev` (always; minimal /dev furniture)
  13. `--tmpfs /tmp` (always; fresh ephemeral tmpfs — note operators wanting persistent /tmp must add /tmp to writable_paths)
  14. `--chdir cwd` IF cwd is provided
  15. `--` (separator)
  16. `command` then `*args` (the operator's target binary)
- **§13 HOME override**: the operator's env dict is copy-mutated to set `HOME = "/tmp"`, regardless of whatever HOME the operator supplied (or didn't). This applies BEFORE generating `--setenv` flags. Operators cannot override HOME via the kv-table — sandbox policy, not operator-configurable. Documented in `prepare_spawn` docstring.
- **`SpawnSpec.env` semantics**: the returned `SpawnSpec.env` is the assembled env (operator's env with HOME forced to /tmp). When L4's `connect_stdio` feeds `spec.env` into `mcp.client.stdio.StdioServerParameters(env=spec.env)`, that env becomes the parent env of the bwrap process itself. Inside bwrap, `--clearenv` + `--setenv` then sets the child's env to the same assembled env. The double-pass is intentional and harmless — bwrap clears its parent-inherited env and rebuilds the child env from `--setenv` flags. Tests assert `spec.env == assembled_env_with_HOME=/tmp`.
- **`SpawnSpec.cwd` semantics**: the returned `SpawnSpec.cwd` is whatever the operator supplied (passed through unchanged). bwrap's `--chdir cwd` flag is what actually sets the child's cwd; the SpawnSpec.cwd is what subprocess.Popen would set as the bwrap process's cwd (mostly irrelevant since bwrap doesn't care about its own cwd, but consistent with the L4 contract that StdioServerParameters consumes spec.cwd).
- **Why no validation of `writable_paths` entries' existence in this leg**: per F3 §6, "writable_paths entry {path!r} does not exist" is bwrap's runtime error (bwrap will exit non-zero from `--bind` setup). L4 catches that and translates to `MCPSandboxError` with the §6 catalog message. L3 emits the `--bind PATH PATH` flag verbatim; trust-the-runtime preserved.
- **Sorted env iteration for test-determinism**: when emitting `--setenv KEY VALUE` flags, iterate the assembled env's keys in `sorted()` order. Real bwrap doesn't care about flag order (each `--setenv` independently sets one var), but tests need a stable assertion target. Document in the implementation comment.
- **§13 wrinkle: HOME override applies even when env is empty**: `prepare_spawn(profile, "/bin/echo", [], env={}, cwd=None)` should still produce `--setenv HOME /tmp` in the args. The HOME override is unconditional. Tests cover the empty-env case.
- **Per-leg lint gate**: `ruff check the_one/ tests/` clean before `[HANDOFF:review-needed]`.
- **Citation style**: anchor by symbol-name. The existing test file `tests/test_sandbox_contract.py` (L2) is the closest style reference; the L3 tests live in a NEW file `tests/test_sandbox_bubblewrap.py` to keep the "contract tests" (L2) cleanly separated from the "backend tests" (L3).

## Inputs

- L1a, L1b, L2 all `completed`. Dev container has `bwrap 0.11.0`. F3 contracts in CLAUDE.md / agents.md. `the_one/platform/sandbox/{__init__.py, base.py, bubblewrap.py}` exist; `MCPSandboxError` lives at `the_one/mcp/errors.py`.
- `the_one/platform/sandbox/bubblewrap.py::BubblewrapSandbox` has `name: str = "bubblewrap"` class attribute, empty-body `__init__` (with docstring), and `prepare_spawn` raising `NotImplementedError("L3 implements BubblewrapSandbox.prepare_spawn")`.
- `the_one/platform/sandbox/base.py::SandboxProfile` (frozen dataclass): fields `writable_paths: list[str]`, `network_allowed: bool`, `pid_unshare: bool`, `ipc_unshare: bool`, `uts_unshare: bool` with strict-floor defaults.
- `the_one/platform/sandbox/base.py::SpawnSpec` (frozen dataclass): `command: str`, `args: list[str]`, `env: dict[str, str]`, `cwd: str | None`, `creation_flags: int = 0`, `attribute_list: dict | None = None`.
- `the_one/mcp/errors.py::MCPSandboxError(MCPClientError)` — bare class, accepts a single message string per the F2 pattern.
- `the_one/platform/env.py::_ENV_ALLOWLIST` exists (8-key tuple) — L3 does NOT depend on it (the operator's env is already-assembled by L4 before reaching L3); referenced here only for documentation completeness.
- `tests/test_sandbox_contract.py` (L2) demonstrates the test-file style: pytest function tests, `pytest.raises(...)`, simple assertions on dataclass fields.
- L1a flight log captures the actual-bwrap argv shape (5-assertion probe verbatim) — the compiler's output should match the shape that L1a proved works.

## Outputs

- **`the_one/platform/sandbox/bubblewrap.py` rewritten**:
  - Module-level imports: `from __future__ import annotations`; `import shutil`; `from the_one.mcp.errors import MCPSandboxError`; `from the_one.platform.sandbox.base import SandboxProfile, SpawnSpec`.
  - `BubblewrapSandbox.__init__` validates bwrap via `shutil.which("bwrap")`. If `None`, raises `MCPSandboxError` with the §6 catalog message verbatim.
  - `BubblewrapSandbox.prepare_spawn` compiles the bwrap argv per the §Context structure.
  - Module docstring updated: removes "L2 stub" framing, replaces with "Linux backend; L3 lands prepare_spawn implementation; L4 wires it via connect_stdio."
  - Class docstring updated: removes "L2 lands the stub; L3 implements" framing, replaces with the actual contract semantics (HOME override, argv structure summary, error-message catalog reference).

- **`tests/test_sandbox_bubblewrap.py`** — NEW file. ~10 unit tests covering:
  1. `test_init_raises_when_bwrap_missing` — monkeypatch `shutil.which` to return `None`; instantiating `BubblewrapSandbox()` raises `MCPSandboxError`. Assert the FULL §6 verbatim message ("MCP sandbox setup failed: bubblewrap binary not found in PATH. Install with: apt-get install bubblewrap. In test environments only, set THE_ONE_SANDBOX_DISABLED=1 with THE_ONE_TEST_MODE=1.") via `assert str(exc_info.value) == EXPECTED_MSG`. Locks the verbatim invariant against future text drift.
  2. `test_init_succeeds_when_bwrap_present` — monkeypatch `shutil.which` to return `"/usr/bin/bwrap"`; `BubblewrapSandbox()` constructs without raising.
  3. `test_prepare_spawn_default_profile_argv_shape` — strict-floor `SandboxProfile()` with `command="/bin/echo"`, `args=["hello"]`, `env={"PATH": "/usr/bin"}`, `cwd=None`. Assert `SpawnSpec.command == "bwrap"`; `SpawnSpec.args` contains `--die-with-parent`, `--unshare-user`, `--unshare-pid`, `--unshare-ipc`, `--unshare-uts`, `--unshare-net`, `--clearenv`, `--setenv HOME /tmp` (HOME override even when not in operator env), `--setenv PATH /usr/bin`, `--ro-bind / /`, `--proc /proc`, `--dev /dev`, `--tmpfs /tmp`, `--`, `/bin/echo`, `hello` — IN THIS ORDER. (Use index assertions for the absolute-positional flags; for the variable-length blocks like `--setenv` use `in args` checks.)
  4. `test_prepare_spawn_with_writable_paths` — `SandboxProfile(writable_paths=["/data", "/cache"])` produces argv with `--bind /data /data` and `--bind /cache /cache` adjacent to the `--ro-bind / /` block. Operator order preserved (`/data` before `/cache`).
  5. `test_prepare_spawn_with_network_allowed` — `SandboxProfile(network_allowed=True)` produces argv WITHOUT `--unshare-net`.
  6. `test_prepare_spawn_namespace_flags_individually_disabled` — three sub-cases (or three tests): `pid_unshare=False` omits `--unshare-pid`; `ipc_unshare=False` omits `--unshare-ipc`; `uts_unshare=False` omits `--unshare-uts`. Default `True` for all.
  7. `test_prepare_spawn_cwd_is_set` — `cwd="/workdir"` produces argv with `--chdir /workdir` immediately before the `--` separator. `SpawnSpec.cwd == "/workdir"`.
  8. `test_prepare_spawn_cwd_is_none` — `cwd=None` produces argv WITHOUT any `--chdir`. `SpawnSpec.cwd is None`.
  9. `test_prepare_spawn_home_override_unconditional` — operator supplies `env={"HOME": "/operator/home"}`. The compiled argv contains `--setenv HOME /tmp` (NOT `--setenv HOME /operator/home`). `SpawnSpec.env["HOME"] == "/tmp"`. The operator's `/operator/home` is silently overridden.
  10. `test_prepare_spawn_empty_env_still_emits_home` — operator supplies `env={}`. Compiled argv still contains `--setenv HOME /tmp`. `SpawnSpec.env == {"HOME": "/tmp"}`.
  11. `test_prepare_spawn_setenv_sorted_for_determinism` — operator supplies `env={"PATH": "/p", "USER": "u", "TERM": "xterm"}`. The `--setenv` flags appear in alphabetical order: HOME (forced), PATH, TERM, USER. Locks the deterministic-ordering invariant.
  12. `test_prepare_spawn_command_and_args_at_end` — compiled argv ends with `--`, `command`, `*args` (in that order). For `command="/bin/echo"`, `args=["hello", "world"]`, the last 4 elements are `["--", "/bin/echo", "hello", "world"]`.
  13. `test_prepare_spawn_writable_paths_with_relative_path` — `SandboxProfile(writable_paths=["data/foo"])` produces `--bind data/foo data/foo` verbatim — relative-path semantics are bwrap's problem at exec time. Trust-the-runtime invariant.
  14. `test_prepare_spawn_returns_spawnspec_with_correct_field_types` — assert `isinstance(spec, SpawnSpec)`, `spec.command == "bwrap"`, `spec.creation_flags == 0`, `spec.attribute_list is None` (Linux-only fields untouched).

  All tests use a `_bwrap_present` autouse fixture that monkeypatches `shutil.which("bwrap")` to return `"/usr/bin/bwrap"` for every test EXCEPT `test_init_raises_when_bwrap_missing`, so the construction succeeds and tests can focus on argv compilation. The `test_init_raises_when_bwrap_missing` test re-monkeypatches `shutil.which` locally to return `None`; pytest's `MonkeyPatch` instance is shared between fixture and test body, so the test-body's `setattr` stacks on top and wins for that test's duration.

  **Critical: `tests/test_sandbox_contract.py` ALSO needs the same `_bwrap_present` autouse fixture.** Two L2 tests instantiate `BubblewrapSandbox()`:
  - `test_mcpsandbox_protocol_runtime_check_bubblewrap` — needs the fixture so construction succeeds in environments without bwrap installed.
  - `test_bubblewrap_sandbox_prepare_spawn_not_implemented` — being DELETED in this leg (per Implementation Guidance §3) since the method is no longer NotImplementedError.

  Without the fixture in `test_sandbox_contract.py`, the contract tests would fail in any environment where `which bwrap` returns None — even though the contract logic is bwrap-independent. Add the fixture at module level; mirrors `test_sandbox_bubblewrap.py` exactly.

- **Flight artifacts**:
  - `flight-log.md` gets `### L3 Bubblewrap Backend` under `## Leg Progress`.
  - `flight.md` checkbox ticked under `### Legs`.
  - `legs/03-bubblewrap-backend.md` Status flipped to `completed`.

## Acceptance Criteria

- [ ] **`BubblewrapSandbox.__init__` validates bwrap presence**: calls `shutil.which("bwrap")`; raises `MCPSandboxError` with the §6 catalog message verbatim ("MCP sandbox setup failed: bubblewrap binary not found in PATH. Install with: apt-get install bubblewrap. In test environments only, set THE_ONE_SANDBOX_DISABLED=1 with THE_ONE_TEST_MODE=1.") when `which` returns `None`.
- [ ] **`BubblewrapSandbox.prepare_spawn` compiles correct argv**: returned `SpawnSpec.command == "bwrap"`; `SpawnSpec.args` contains the flags listed in §Context's argv-structure list, in the listed order; `SpawnSpec.env` is the assembled env with HOME forced to `/tmp`; `SpawnSpec.cwd` is the operator's cwd passed through (or None).
- [ ] **HOME override is unconditional**: regardless of whether the operator's env contains HOME, the compiled `--setenv HOME /tmp` appears in argv and `spec.env["HOME"] == "/tmp"`. Operator-supplied HOME values are silently overridden.
- [ ] **Namespace flags respect SandboxProfile fields**: `--unshare-user` always present; `--unshare-pid`/`--unshare-ipc`/`--unshare-uts` present iff the corresponding `*_unshare` field is `True`; `--unshare-net` present iff `network_allowed` is `False`.
- [ ] **Writable paths emit `--bind PATH PATH`**: each entry of `profile.writable_paths` produces one `--bind <path> <path>` pair; operator order preserved; relative paths emitted verbatim ("trust the runtime").
- [ ] **cwd handling**: `cwd is None` → no `--chdir` flag; `cwd is not None` → `--chdir <cwd>` immediately before `--`; `spec.cwd` equals the operator's input.
- [ ] **`--setenv` ordering is deterministic** (sorted by key) so tests can stake on it.
- [ ] **`tests/test_sandbox_bubblewrap.py` ~14 tests all pass**: covers init validation (both directions), argv compilation (default + writable + network + namespaces + cwd + HOME override + empty env + sorted setenv + command/args at end + relative path), and SpawnSpec field-type sanity.
- [ ] **No real subprocess in any test**: `tests/test_sandbox_bubblewrap.py` does not call `subprocess.run`, `subprocess.Popen`, `os.execvp`, or any actual shell. Verifiable by `grep -E "subprocess\\.|execvp|os.system" tests/test_sandbox_bubblewrap.py` returning no matches.
- [ ] **L2 contract tests still pass** (`tests/test_sandbox_contract.py`): the L2 stub-tests asserted `prepare_spawn` raises `NotImplementedError` with "L3 implements" in the message — that test must be UPDATED to reflect L3's reality. Either (a) delete the test (the contract is now implemented; NotImplementedError no longer applies), or (b) replace it with a test that asserts `prepare_spawn` returns a `SpawnSpec` of the right shape (mocking `shutil.which`). Recommend (a) — delete from L2 file, since L3's new test file covers the same surface more thoroughly. Document the test-relocation in the flight log.
- [ ] **F2 + F1 tests still green**: no import-path break.
- [ ] **Lint clean**: `ruff check the_one/ tests/` exits 0.
- [ ] **No source changes outside `bubblewrap.py` + the new test file** (and the L2-stub-test deletion in `tests/test_sandbox_contract.py`).
- [ ] **No `connect_stdio` integration**: `the_one/mcp/transports/stdio.py` is NOT modified — that's L4's surface.
- [ ] **Flight log + flight + leg-status updates** per the per-leg checklist.

## Verification Steps

```bash
cd ~/projects/the-one

# --- 1. Diff scope ---
git status --porcelain
# Expect modifications under:
#   the_one/platform/sandbox/bubblewrap.py     (M)
#   tests/test_sandbox_bubblewrap.py           (??)
#   tests/test_sandbox_contract.py             (M — stub-test removal)
#   missions/.../flight.md                      (M)
#   missions/.../flight-log.md                  (M)
#   missions/.../legs/03-...md                  (M, status flip)
# No other modifications.

# --- 2. New backend tests pass ---
docker compose exec -T the-one python -m pytest tests/test_sandbox_bubblewrap.py -v
# Expect: ~14 passed; <1s wall clock.

# --- 3. L2 contract tests still pass (with stub-test removed/replaced) ---
docker compose exec -T the-one python -m pytest tests/test_sandbox_contract.py -v
# Expect: count went from ~14 (L2) to ~13 (L2 minus the stub test, if deleted).
# If replaced rather than deleted, count stays ~14.

# --- 4. Manual smoke: BubblewrapSandbox compiles a known argv shape ---
docker compose exec -T the-one python -c "
from the_one.platform.sandbox import BubblewrapSandbox, SandboxProfile
sb = BubblewrapSandbox()
spec = sb.prepare_spawn(SandboxProfile(), '/bin/echo', ['hello'], {'PATH': '/usr/bin'}, cwd=None)
assert spec.command == 'bwrap'
assert '--die-with-parent' in spec.args
assert '--unshare-user' in spec.args
assert '--unshare-net' in spec.args
assert '--clearenv' in spec.args
assert '--ro-bind' in spec.args
assert '--tmpfs' in spec.args
assert '--' in spec.args
assert spec.env['HOME'] == '/tmp'
print('smoke ok')
"
# Expect: 'smoke ok'.

# --- 5. F2/F1 regression suites ---
docker compose exec -T the-one python -m pytest tests/test_mcp_integration.py tests/test_db_api.py::TestMCPSourceAPI -v
# Expect: all green.

# --- 6. Lint ---
docker compose exec -T the-one ruff check the_one/ tests/
# Expect: All checks passed.

# --- 7. No real-subprocess in the new test file ---
grep -E "subprocess\.|execvp|os\.system" tests/test_sandbox_bubblewrap.py
# Expect: no matches.

# --- 8. connect_stdio untouched ---
git diff the_one/mcp/transports/stdio.py
# Expect: empty diff (L4's surface).
```

If any verification fails:
1. Do NOT signal `[COMPLETE:leg]`.
2. Capture failing output in flight log under `## Anomalies`.
3. Diagnose: most likely (a) `--setenv` order non-deterministic (need sorted iteration), (b) `--unshare-net` emitted when `network_allowed=True`, (c) HOME override missing when operator env is empty, (d) `--chdir` emitted when `cwd is None`, (e) `MCPSandboxError` message text doesn't match §6 catalog verbatim, (f) `shutil.which` mock doesn't propagate (autouse fixture scope issue).

## Implementation Guidance

1. **Rewrite `the_one/platform/sandbox/bubblewrap.py`** with the real implementation. Module structure:

   ```python
   """Bubblewrap-backed Linux sandbox (F3 §8 + §11).

   Implements ``MCPSandbox.prepare_spawn`` by compiling a ``SandboxProfile``
   plus operator-supplied (command, args, env, cwd) into a bwrap-wrapped
   ``SpawnSpec``. L4's ``connect_stdio`` feeds the result into
   ``mcp.client.stdio.StdioServerParameters`` for the SDK's transport layer.

   Trust contract:
     * ``--clearenv`` + per-key ``--setenv`` enforces the env-allowlist invariant.
     * ``--ro-bind / /`` + per-path ``--bind`` defines the FS scope.
     * ``--unshare-net`` (when ``network_allowed`` is False) defines network policy.
     * ``--die-with-parent`` defines process supervision.

   §13 HOME override: HOME is unconditionally set to ``/tmp`` regardless of
   operator-supplied env. Operators cannot override HOME via the kv-table —
   sandbox policy, not operator-configurable.
   """

   from __future__ import annotations

   import shutil

   from the_one.mcp.errors import MCPSandboxError
   from the_one.platform.sandbox.base import SandboxProfile, SpawnSpec


   class BubblewrapSandbox:
       """Linux sandbox backend using bubblewrap (``bwrap``).

       Validates ``bwrap`` presence at construction; ``prepare_spawn`` compiles
       a ``SandboxProfile`` plus operator command/args/env/cwd into a
       bwrap-wrapped ``SpawnSpec``. HOME is unconditionally overridden to
       ``/tmp``.
       """

       name: str = "bubblewrap"

       def __init__(self) -> None:
           if shutil.which("bwrap") is None:
               raise MCPSandboxError(
                   "MCP sandbox setup failed: bubblewrap binary not found "
                   "in PATH. Install with: apt-get install bubblewrap. "
                   "In test environments only, set THE_ONE_SANDBOX_DISABLED=1 "
                   "with THE_ONE_TEST_MODE=1."
               )

       def prepare_spawn(
           self,
           profile: SandboxProfile,
           command: str,
           args: list[str],
           env: dict[str, str],
           cwd: str | None = None,
       ) -> SpawnSpec:
           """Compile a bwrap-wrapped SpawnSpec.

           Argv structure (in order):
               --die-with-parent, --unshare-user, [--unshare-pid],
               [--unshare-ipc], [--unshare-uts], [--unshare-net],
               --clearenv, --setenv KEY VALUE per assembled-env entry,
               --ro-bind / /, --bind PATH PATH per writable_paths entry,
               --proc /proc, --dev /dev, --tmpfs /tmp,
               [--chdir cwd], --, command, *args.

           HOME is unconditionally overridden to /tmp (sandbox policy).
           --setenv flags are emitted in sorted-by-key order for test
           determinism; bwrap itself doesn't care about order.
           """
           assembled_env = dict(env)
           assembled_env["HOME"] = "/tmp"

           bwrap_args: list[str] = ["--die-with-parent", "--unshare-user"]
           if profile.pid_unshare:
               bwrap_args.append("--unshare-pid")
           if profile.ipc_unshare:
               bwrap_args.append("--unshare-ipc")
           if profile.uts_unshare:
               bwrap_args.append("--unshare-uts")
           if not profile.network_allowed:
               bwrap_args.append("--unshare-net")
           bwrap_args.append("--clearenv")
           for key in sorted(assembled_env):
               bwrap_args.extend(["--setenv", key, assembled_env[key]])
           bwrap_args.extend(["--ro-bind", "/", "/"])
           for path in profile.writable_paths:
               bwrap_args.extend(["--bind", path, path])
           bwrap_args.extend(["--proc", "/proc"])
           bwrap_args.extend(["--dev", "/dev"])
           bwrap_args.extend(["--tmpfs", "/tmp"])
           if cwd is not None:
               bwrap_args.extend(["--chdir", cwd])
           bwrap_args.append("--")
           bwrap_args.append(command)
           bwrap_args.extend(args)

           return SpawnSpec(
               command="bwrap",
               args=bwrap_args,
               env=assembled_env,
               cwd=cwd,
           )
   ```

2. **Write `tests/test_sandbox_bubblewrap.py`**. Style: pytest function tests; use `monkeypatch` to mock `shutil.which`; use module-level autouse fixture for the bwrap-present mock; opt out via `request.keywords` or by having the "bwrap missing" test override the mock locally. Sketch:

   ```python
   """Unit tests for BubblewrapSandbox.prepare_spawn (F3 L3).

   Pure arg-compilation testing — no real subprocess executes in any test.
   L1a's 5-assertion probe stake-tested that the argv shape compiled here
   actually executes inside the dev container; L4's /bin/echo integration
   test is the next-leg surface.
   """

   from __future__ import annotations

   import shutil

   import pytest

   from the_one.mcp.errors import MCPSandboxError
   from the_one.platform.sandbox import (
       BubblewrapSandbox,
       SandboxProfile,
       SpawnSpec,
   )

   _BWRAP_NOT_FOUND_MSG = (
       "MCP sandbox setup failed: bubblewrap binary not found in PATH. "
       "Install with: apt-get install bubblewrap. "
       "In test environments only, set THE_ONE_SANDBOX_DISABLED=1 "
       "with THE_ONE_TEST_MODE=1."
   )


   @pytest.fixture(autouse=True)
   def _bwrap_present(monkeypatch: pytest.MonkeyPatch) -> None:
       """Pretend bwrap is installed for every test except the missing-bwrap one."""
       monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)


   def test_init_raises_when_bwrap_missing(monkeypatch: pytest.MonkeyPatch) -> None:
       monkeypatch.setattr(shutil, "which", lambda name: None)
       with pytest.raises(MCPSandboxError) as exc_info:
           BubblewrapSandbox()
       assert str(exc_info.value) == _BWRAP_NOT_FOUND_MSG  # verbatim §6 invariant


   def test_init_succeeds_when_bwrap_present() -> None:
       sb = BubblewrapSandbox()
       assert sb.name == "bubblewrap"


   def test_prepare_spawn_default_profile_argv_shape() -> None:
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(
           SandboxProfile(),
           "/bin/echo",
           ["hello"],
           {"PATH": "/usr/bin"},
       )
       assert spec.command == "bwrap"
       a = spec.args
       # Floor flags (always present)
       assert "--die-with-parent" in a
       assert "--unshare-user" in a
       assert "--unshare-pid" in a
       assert "--unshare-ipc" in a
       assert "--unshare-uts" in a
       assert "--unshare-net" in a  # network OFF by default
       assert "--clearenv" in a
       # HOME forced to /tmp even though operator didn't supply HOME
       assert "--setenv" in a
       home_idx = a.index("HOME")
       assert a[home_idx + 1] == "/tmp"
       # PATH from operator env round-trips
       path_idx = a.index("PATH")
       assert a[path_idx + 1] == "/usr/bin"
       # Floor mounts
       assert "--ro-bind" in a
       assert "--proc" in a
       assert "--dev" in a
       assert "--tmpfs" in a
       # Command + args at end
       assert a[-3] == "--"
       assert a[-2] == "/bin/echo"
       assert a[-1] == "hello"
       # SpawnSpec invariants
       assert spec.env["HOME"] == "/tmp"
       assert spec.cwd is None


   def test_prepare_spawn_with_writable_paths() -> None:
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(
           SandboxProfile(writable_paths=["/data", "/cache"]),
           "/bin/echo",
           [],
           {},
       )
       a = spec.args
       # Each writable path emits --bind PATH PATH
       d_idx = a.index("/data")
       assert a[d_idx - 1] == "--bind"
       assert a[d_idx + 1] == "/data"
       c_idx = a.index("/cache")
       assert a[c_idx - 1] == "--bind"
       assert a[c_idx + 1] == "/cache"
       # Operator order preserved
       assert d_idx < c_idx


   def test_prepare_spawn_with_network_allowed() -> None:
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(
           SandboxProfile(network_allowed=True),
           "/bin/echo",
           [],
           {},
       )
       assert "--unshare-net" not in spec.args


   @pytest.mark.parametrize(
       ("field", "flag"),
       [
           ("pid_unshare", "--unshare-pid"),
           ("ipc_unshare", "--unshare-ipc"),
           ("uts_unshare", "--unshare-uts"),
       ],
   )
   def test_prepare_spawn_namespace_flags_individually_disabled(field: str, flag: str) -> None:
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(
           SandboxProfile(**{field: False}),
           "/bin/echo",
           [],
           {},
       )
       assert flag not in spec.args


   def test_prepare_spawn_cwd_is_set() -> None:
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(
           SandboxProfile(),
           "/bin/echo",
           [],
           {},
           cwd="/workdir",
       )
       chdir_idx = spec.args.index("--chdir")
       assert spec.args[chdir_idx + 1] == "/workdir"
       # --chdir comes before --
       sep_idx = spec.args.index("--")
       assert chdir_idx < sep_idx
       assert spec.cwd == "/workdir"


   def test_prepare_spawn_cwd_is_none() -> None:
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(SandboxProfile(), "/bin/echo", [], {}, cwd=None)
       assert "--chdir" not in spec.args
       assert spec.cwd is None


   def test_prepare_spawn_home_override_unconditional() -> None:
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(
           SandboxProfile(),
           "/bin/echo",
           [],
           {"HOME": "/operator/home"},
       )
       a = spec.args
       home_idx = a.index("HOME")
       assert a[home_idx + 1] == "/tmp", "HOME override must win over operator-supplied HOME"
       assert spec.env["HOME"] == "/tmp"
       # Verify only ONE --setenv HOME pair
       home_count = sum(1 for i, x in enumerate(a) if x == "HOME" and i > 0 and a[i - 1] == "--setenv")
       assert home_count == 1


   def test_prepare_spawn_empty_env_still_emits_home() -> None:
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(SandboxProfile(), "/bin/echo", [], {})
       assert "HOME" in spec.args
       assert spec.env == {"HOME": "/tmp"}


   def test_prepare_spawn_setenv_sorted_for_determinism() -> None:
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(
           SandboxProfile(),
           "/bin/echo",
           [],
           {"PATH": "/p", "USER": "u", "TERM": "xterm"},
       )
       # Collect --setenv KEY pairs in order
       a = spec.args
       setenv_keys: list[str] = []
       for i, tok in enumerate(a):
           if tok == "--setenv" and i + 1 < len(a):
               setenv_keys.append(a[i + 1])
       # Sorted alphabetically — HOME forced first, then PATH, TERM, USER
       assert setenv_keys == sorted(setenv_keys)
       assert "HOME" in setenv_keys
       assert "PATH" in setenv_keys
       assert "TERM" in setenv_keys
       assert "USER" in setenv_keys


   def test_prepare_spawn_command_and_args_at_end() -> None:
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(
           SandboxProfile(),
           "/bin/echo",
           ["hello", "world"],
           {},
       )
       assert spec.args[-4:] == ["--", "/bin/echo", "hello", "world"]


   def test_prepare_spawn_writable_paths_with_relative_path() -> None:
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(
           SandboxProfile(writable_paths=["data/foo"]),
           "/bin/echo",
           [],
           {},
       )
       # Trust-the-runtime: relative path emitted verbatim
       idx = spec.args.index("data/foo")
       assert spec.args[idx - 1] == "--bind"
       assert spec.args[idx + 1] == "data/foo"


   def test_prepare_spawn_returns_spawnspec_with_correct_field_types() -> None:
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(SandboxProfile(), "/bin/echo", [], {})
       assert isinstance(spec, SpawnSpec)
       assert spec.command == "bwrap"
       assert spec.creation_flags == 0
       assert spec.attribute_list is None
   ```

3. **Update `tests/test_sandbox_contract.py`**: the L2 stub-test (`test_bubblewrap_sandbox_prepare_spawn_not_implemented`) asserts `prepare_spawn` raises `NotImplementedError`. After L3, this test will FAIL because the method now succeeds. **Decision: delete the test from `test_sandbox_contract.py`**. The new `test_sandbox_bubblewrap.py` covers the same surface (and more) with the real implementation. Document the deletion in the flight log entry under "Test relocation: L2's stub-NotImplementedError test deleted; L3's argv-compilation tests in `tests/test_sandbox_bubblewrap.py` cover the surface."

   The L2 test that asserts `BubblewrapSandbox()` instantiates successfully (`test_mcpsandbox_protocol_runtime_check_bubblewrap`) might also break after L3 because `BubblewrapSandbox()` now requires bwrap to be on PATH. **Fix**: in `test_sandbox_contract.py`, add a module-level autouse fixture that monkeypatches `shutil.which("bwrap")` to return a fake path (mirrors the new test file's fixture). This keeps L2's contract tests independent of bwrap's actual installation state.

4. **Run all Verification Steps** before signalling `[HANDOFF:review-needed]`. Lint must be clean.

## Edge Cases

- **Operator-supplied `args` list is empty**: argv ends with `--`, `command`. No trailing args. Test #12 covers.
- **Operator-supplied `env` is empty**: HOME=/tmp is still emitted. Test #10.
- **Operator's env contains other reserved-like keys (e.g., `PWD`, `_`)**: passed through verbatim per --setenv. No filtering. Operator's responsibility per "trust the runtime."
- **`writable_paths` contains duplicate entries**: each entry emits a separate `--bind PATH PATH`. bwrap accepts duplicates as a no-op for the second; not the compiler's concern to deduplicate.
- **`writable_paths` contains an empty string**: `--bind '' ''` is emitted. bwrap will fail at exec time; trust-the-runtime.
- **`cwd` is an empty string**: `--chdir ''` is emitted. bwrap will fail at exec time. Test does NOT cover this — too pathological; trust-the-runtime.
- **`command` contains shell metacharacters (e.g., `"echo $HOME"`)**: passed through verbatim as a single argv entry. bwrap exec with no shell interpretation. Operator's responsibility if they want shell expansion (use `bash -c`).
- **`shutil.which` mocked but module-level import order matters**: Python imports `shutil` once; monkeypatch replaces `shutil.which` for the test's duration. The autouse fixture handles all tests in this file.
- **L2's contract test that uses `BubblewrapSandbox()` directly**: needs the same monkeypatch (see Implementation Guidance §3). Without it, L2's contract tests would fail in environments without bwrap installed (which is fine for the dev container post-L1a, but breaks if someone runs tests on a host without bwrap).
- **`SpawnSpec.env` mutability**: `frozen=True` on the dataclass freezes attribute assignment but the dict itself is mutable. `dict(env)` creates a copy at the start of `prepare_spawn`, so the operator's input dict is not mutated by HOME override.

## Files Affected

- `the_one/platform/sandbox/bubblewrap.py` — REWRITE the class body (replace stub with real implementation; update docstrings).
- `tests/test_sandbox_bubblewrap.py` — NEW (~14 unit tests).
- `tests/test_sandbox_contract.py` — REMOVE the L2 stub-NotImplementedError test; ADD a module-level autouse fixture that monkeypatches `shutil.which("bwrap")` so `BubblewrapSandbox()` can construct without real bwrap.
- `missions/.../flight-log.md` — append `### L3 Bubblewrap Backend` under `## Leg Progress`.
- `missions/.../flight.md` — tick L3 checkbox.
- `missions/.../legs/03-bubblewrap-backend.md` — flip Status.

**Explicitly NOT modified**: `the_one/platform/sandbox/__init__.py` (re-exports unchanged), `the_one/platform/sandbox/base.py` (Protocol/dataclasses unchanged), `the_one/mcp/errors.py` (`MCPSandboxError` already added in L2), `the_one/mcp/transports/stdio.py` (L4), `the_one/interfaces/web/api.py`, `tests/conftest.py`, `tests/fixtures/mcp/`, JS, Dockerfile, docker-compose.yml, Makefile, pyproject.toml, CLAUDE.md, agents.md.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] `BubblewrapSandbox.prepare_spawn` compiles correct bwrap argv per §Context structure
- [ ] `BubblewrapSandbox.__init__` raises `MCPSandboxError` with verbatim §6 message when bwrap missing
- [ ] HOME override is unconditional and always overrides operator-supplied HOME
- [ ] `--setenv` flags emitted in sorted-by-key order
- [ ] `tests/test_sandbox_bubblewrap.py` ~14 tests all pass; no real subprocess in any test
- [ ] `tests/test_sandbox_contract.py` updated (L2 stub-test removed; bwrap-which monkeypatch added)
- [ ] F2 + F1 regression suites green
- [ ] `ruff check the_one/ tests/` exit 0
- [ ] `git status --porcelain` shows only the leg-allowed paths
- [ ] No `connect_stdio` or other L4-surface changes
- [ ] Update flight-log.md with `### L3 Bubblewrap Backend` under `## Leg Progress` (Started/Completed + 3-line summary + test counts + test-relocation note)
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in flight.md (under `### Legs`)
- [ ] **Do NOT commit** — agentic-workflow batches commits at flight end
