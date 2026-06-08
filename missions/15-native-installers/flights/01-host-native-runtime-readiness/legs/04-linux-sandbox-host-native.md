# Leg: linux-sandbox-host-native

**Status**: completed
**Flight**: [Host-Native Runtime Readiness](../flight.md)

## Objective

Make the Linux sandbox backend selection robust host-native (no Docker) by probing
whether unprivileged user namespaces actually work, and gracefully degrading to the
passthrough backend with a distinct warning when they don't — without removing the
existing `BubblewrapSandbox.__init__` backstop.

## Context

- **Flight DDs** — "Sandbox userns probe is empirical, not the procfs knob" and "Userns
  probe is additive in the factory; the `__init__` backstop stays."
- **Design-time empirical finding** (flight log) — on the WSL2 dev kernel the
  `/proc/sys/kernel/unprivileged_userns_clone` knob is **absent**, yet unprivileged
  userns + host-native bwrap containment both work. So the probe must be **empirical**
  (attempt the real operation); the procfs knob is at most a fast-path hint.
- **Python 3.11 constraint** — `os.unshare()` is 3.12+, so the empirical probe runs a
  minimal **`bwrap` subprocess** (which the factory has already confirmed is on PATH).
  Using bwrap itself is the most faithful probe — it tests exactly the operation real
  spawns will perform.
- **Current selection** (`platform/sandbox/factory.py:70-122`): test-bypass → non-Linux →
  bwrap-missing(WARNING) → BubblewrapSandbox. The new userns check inserts as a step
  between bwrap-missing and the BubblewrapSandbox selection (after line 115, before 117).
- **Backstop stays** — `BubblewrapSandbox.__init__` still raises `SandboxError` when
  bwrap is absent (`bubblewrap.py:83-89`), guarded by a dedicated test
  (`tests/test_sandbox_bubblewrap.py`). This leg does **not** touch that — additive only.
- **Pure-unit factory tests** (`tests/test_sandbox_factory.py`) mock `shutil.which` and
  must not spawn real subprocesses; they need to stub the new probe `True` so they keep
  asserting bwrap-present → `BubblewrapSandbox` deterministically.
- Independent of Legs 1/2/3 (different surface), though it consumes Leg 1's relocated
  `SandboxError` indirectly via `bubblewrap.py` (already landed).

## Inputs

- `the_one/platform/sandbox/factory.py` `get_sandbox_backend()` with the four-step
  selection and the module-level log-once guard (`_LOGGED`, `_reset_selection_log_state`).
- `the_one/platform/sandbox/bubblewrap.py` `__init__` raise backstop (untouched).
- `tests/test_sandbox_factory.py` pure-unit cases asserting bwrap-present →
  `BubblewrapSandbox` (mock `shutil.which`).

## Outputs

- A module-level, **monkeypatchable** `_userns_available()` probe in `factory.py` that
  empirically tests unprivileged-userns support via a minimal `bwrap` subprocess
  (cached after the first real evaluation; reset hook for tests).
- A new selection step: bwrap present **but** userns unavailable → `PassthroughSandbox`
  with a WARNING that **distinguishes** this from the bwrap-missing case.
- Updated factory module docstring (selection order) reflecting the new step.
- `tests/test_sandbox_factory.py` bwrap-present cases stub `_userns_available` → `True`.
- New tests: enforced path (probe `True` → bubblewrap) and userns-degraded path (bwrap
  present, probe `False` → passthrough + distinct WARNING, exactly once).

## Acceptance Criteria

- [x] `_userns_available()` exists at module level in `factory.py`, is monkeypatchable,
      and empirically determines userns support without relying solely on the procfs knob
      (the knob may be consulted only as a fast-path hint). Its real result is cached so
      the probe subprocess runs at most once per process.
- [x] Selection: Linux + bwrap present + `_userns_available()` **True** → `BubblewrapSandbox`.
- [x] Selection: Linux + bwrap present + `_userns_available()` cleanly **False** (userns
      definitively unavailable) → `PassthroughSandbox`, with a **WARNING** distinct from
      the bwrap-missing WARNING (names "user namespaces unavailable", log-once key
      `passthrough:userns-unavailable`).
- [x] **Split fail-direction (security review)**: on probe **error/timeout** (cannot
      determine — `OSError`/`TimeoutExpired`), still degrade to `PassthroughSandbox` (never
      raise, never hang — subprocess `timeout`), but log at **ERROR** with a *distinct*
      message + log-once key (`passthrough:userns-probe-error`) so operators can tell
      "kernel known-unsupported" from "probe mechanism broken". The clean-`False` path
      stays WARNING; the error path is ERROR.
- [x] `BubblewrapSandbox.__init__` backstop and its test are **unchanged** and still pass.
- [x] The 4 bwrap-present cases in `tests/test_sandbox_factory.py` and the one in
      `tests/test_mcp_stdio_sandbox.py` (line 392) stub `_userns_available` → `"ok"`; both
      modules stay pure-unit (no real subprocess) and green.
- [x] New tests cover all three probe outcomes: `"ok"` → bubblewrap; `"unavailable"` →
      passthrough + one-time WARNING; `"error"` → passthrough + one-time ERROR (distinct
      key). Reset both the log guard and the probe cache per test.
- [x] Factory module docstring selection-order list updated to include the new step.
- [x] `@requires_bwrap` sandbox tests still pass (the real probe succeeds in the bwrap
      environment); full suite + `ruff` clean.

## Verification Steps

- `docker exec the-one pytest -x --timeout 30 tests/test_sandbox_factory.py tests/test_sandbox_bubblewrap.py` → green.
- `docker exec the-one pytest -x --timeout 60 -m requires_bwrap` → green (the real probe
  returns True in the bwrap-capable container, so selection still yields BubblewrapSandbox).
- `docker exec the-one python -c "from the_one.platform.sandbox.factory import _userns_available; print('userns:', _userns_available())"` → prints `True` in the container.
- Degraded-path test: stub `_userns_available` → False, assert `get_sandbox_backend()`
  returns `PassthroughSandbox` and the distinct WARNING fires once.
- Full suite + `ruff` at leg-end.

## Implementation Guidance

1. **Add `_userns_available()`** (module level in `factory.py`) returning a 2-state
   outcome the caller can branch on — either a `bool` plus a separate "errored" signal,
   or a small enum/`Literal["ok","unavailable","error"]`. Simplest: return `bool` and have
   the function set a module flag / raise-internally-caught so the caller distinguishes
   clean-False from error. Recommended shape: return one of `"ok" | "unavailable" | "error"`.
   - Optional fast-path: if `/proc/sys/kernel/unprivileged_userns_clone` exists and reads
     `0` → `"unavailable"` (definitive negative). Any other value or **absent** → fall
     through to the empirical probe (the WSL2 case — absent must NOT be treated as negative).
   - Empirical probe: run `bwrap --unshare-user --ro-bind / / /usr/bin/true` with
     `subprocess.run(..., capture_output=True, timeout=5)`; `returncode == 0` → `"ok"`,
     else `"unavailable"`. Log the first real probe at DEBUG (`returncode=…`).
   - `try/except` (`OSError`, `subprocess.TimeoutExpired`, `subprocess.SubprocessError`) →
     `"error"` (never raise out).
   - **Cache** the real result in a module global (e.g. `_USERNS_PROBE`). **Hard
     requirement**: the cache reset MUST be folded into `_reset_selection_log_state()`
     (not a separate hook) — the autouse `_reset_log_guard` fixture
     (`tests/test_sandbox_factory.py:39`) calls exactly that, so extending it auto-covers
     every test; a sibling hook would leak stale probe state into the log-once tests.

2. **Insert the selection step** in `get_sandbox_backend()` after the `bwrap`-missing
   block (after line 115), before the BubblewrapSandbox selection — branching on the
   3-state result:
   ```
   probe = _userns_available()            # "ok" | "unavailable" | "error"
   if probe == "unavailable":
       key = "passthrough:userns-unavailable"     # log-once WARNING
       <WARNING: "bwrap present but unprivileged user namespaces are unavailable —
        tool spawns are NOT sandboxed; enable unprivileged userns (e.g. sysctl
        kernel.unprivileged_userns_clone=1 on kernels that expose it)">
       return PassthroughSandbox()
   if probe == "error":
       key = "passthrough:userns-probe-error"      # log-once ERROR (distinct)
       <ERROR: "userns probe errored — cannot determine sandbox capability; degrading
        to passthrough (tool spawns NOT sandboxed); investigate the probe environment">
       return PassthroughSandbox()
   # probe == "ok" → fall through to BubblewrapSandbox
   ```
   Keep the existing `_LOGGED` log-once pattern.

3. **Update the module docstring** selection-order list (lines 4-15) to include the new
   step 4 (bwrap present but userns unavailable → passthrough WARNING) and renumber.

4. **Do NOT touch** `bubblewrap.py.__init__` or `tests/test_sandbox_bubblewrap.py` — the
   backstop stays.

5. **Patch the bwrap-present tests to stub the probe → "ok"** (design review verified the
   exact set):
   - `tests/test_sandbox_factory.py` — **4** functions assert bwrap-present →
     `BubblewrapSandbox` and reach the probe: `test_factory_returns_bubblewrap_on_linux_with_bwrap`
     (line 56), `test_factory_no_bypass_when_only_one_flag_set` (109),
     `test_factory_logs_once_bubblewrap` (162), `test_factory_backend_name_bubblewrap` (251).
     (NOT `test_factory_returns_passthrough_on_test_bypass` at line 95 — the test-bypass
     short-circuits before the probe.) Stub
     `monkeypatch.setattr(factory_module, "_userns_available", lambda: "ok")`.
   - `tests/test_mcp_stdio_sandbox.py` — `test_connect_stdio_sdk_default_env_preserved_through_setenv`
     (line 392) drives the **real** factory with a bwrap-present `shutil.which` mock and
     will reach the probe; without the stub it breaks wherever userns is unavailable.
     Add the same `_userns_available` → `"ok"` stub alongside its existing
     `factory_module.shutil.which` patch. (Leave `test_connect_stdio_real_subprocess_cat_integration`
     at line 446 — it's `@requires_bwrap` and is meant to run the real probe.)

6. **Add new tests** — enforced path (`_userns_available` → True, bwrap present →
   `BubblewrapSandbox`) and degraded path (`_userns_available` → False, bwrap present →
   `PassthroughSandbox` + WARNING once via caplog). Reset the log + probe caches per test.

7. **Run `ruff` + full suite + `-m requires_bwrap`**.

## Edge Cases

- **procfs knob absent** (WSL2) — must fall through to the empirical probe, not assume
  negative. (This is the design-time finding; a knob-only implementation would wrongly
  degrade WSL2.)
- **Probe subprocess hangs** — `timeout=5` + treat `TimeoutExpired` as `False`.
- **bwrap present but a different failure** (e.g. seccomp) — probe returns nonzero →
  degrade; acceptable (the env can't sandbox anyway).
- **Repeated `get_sandbox_backend()` calls** — probe cached; selection still re-evaluated
  each call (factory contract), only the probe + log are deduped.
- **Container/CI with userns working** — probe returns True; behavior unchanged
  (BubblewrapSandbox selected), so `@requires_bwrap` tests are unaffected.

## Files Affected

- `the_one/platform/sandbox/factory.py` — `_userns_available()` 3-state probe + cache +
  reset folded into `_reset_selection_log_state`; new selection branch (WARNING for
  unavailable, ERROR for probe-error); docstring update.
- `tests/test_sandbox_factory.py` — stub `_userns_available` → `"ok"` in the 4
  bwrap-present cases; new tests for all three outcomes.
- `tests/test_mcp_stdio_sandbox.py` — stub `_userns_available` → `"ok"` in
  `test_connect_stdio_sdk_default_env_preserved_through_setenv` (line 392).

---
