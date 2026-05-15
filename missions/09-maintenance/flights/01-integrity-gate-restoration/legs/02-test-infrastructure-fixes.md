# Leg: 02-test-infrastructure-fixes

**Status**: ready
**Flight**: [Integrity Gate Restoration](../flight.md)

## Objective

Resolve the two test-infrastructure issues surfaced by the 2026-05-15 maintenance Inspector: `asgi-lifespan` declared-but-not-installed masks 6 MCP HTTP integration tests at collection time, and `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3`'s skip predicate is over-narrow (fails on common Linux dev hosts where user namespaces are permitted but `cap_add: SYS_ADMIN` is absent). Add a `make doctor` drift-detection target so missing dev extras fail loud rather than masking integration tests.

## Context

The maintenance report's Category 2 surfaced two Action Required test findings (2.1, 2.2) with a shared root: the test suite trusts its declared dev extras + skip predicates without verification. The `asgi-lifespan` case is the more dangerous one — it silently un-covers 6 MCP HTTP integration tests (`TestL3IntegrationSmoke::*`, `TestL4StreamableHttp::*`, `TestL6aHappyPath::*`, `TestL6bInputValidationIntegration::*`) because pytest reports them as collection errors that look like skips at a glance. CI doesn't see this issue because CI installs `.[dev]` fresh in an ephemeral container; only the developer's drifted venv shows the symptom — but the asymmetry is exactly the kind of "works on CI, broken on dev" problem that erodes confidence in the test suite.

The sandbox skip predicate (`_has_sys_admin()` at `test_mcp_sandbox_integration.py:491-511`) was written for the container case where `cap_add: SYS_ADMIN` flips the capability bit. On unprivileged Linux hosts (e.g., WSL2 with `kernel.unprivileged_userns_clone=1`, or stock Ubuntu), the capability check returns false but `unshare -U` still succeeds — so the sandbox creates user namespaces successfully and the EPERM the test expects never fires. The fix is to also probe `unshare -U` actually succeeding before deciding whether to skip.

Design decision from flight: drift-detection mechanism is a `make doctor` Makefile target that imports each declared dev extra inside a `python -c` and fails with a clear `ModuleNotFoundError` naming the missing extra. CI runs `make doctor` as the first step in the test task (before `ruff`), so a missing extra fails the pipeline before any test runs.

## Inputs

- `pyproject.toml` `[project.optional-dependencies].dev` list. **Starter probe set** (the floor; expand to mirror full `pyproject.toml` dev extras at execution time): `asgi_lifespan`, `pytest_asyncio`, `playwright` (via `importlib.util.find_spec` to avoid slow full import), `ruff` (also `find_spec`-checked). After Leg 3 lands `pip-audit`, also probe `pip_audit`. The `asgi-lifespan` probe is the mission criterion's hard requirement; the rest are nice-to-have.
- `tests/conftest.py:238` — `from asgi_lifespan import LifespanManager` import that fails at module load
- `tests/test_mcp_sandbox_integration.py:491-511` — the failing test with its skip predicate
- `tests/test_mcp_sandbox_integration.py` — `_has_sys_admin()` helper definition (verify location)
- `Makefile` — current targets list
- `ci/pipeline.yml:22-24` — CI test task

## Outputs

- `asgi-lifespan` installed in the active venv
- `Makefile` gains a `doctor` target that imports each dev extra
- `ci/pipeline.yml` gains a `make doctor` invocation as the first sub-step of the test task
- `tests/test_mcp_sandbox_integration.py` — `_has_sys_admin()` (or equivalent skip predicate) tightened to also probe `unshare -U` success
- Broad pytest exits with code 0 (no errors at collection, no `test_sandbox_eperm_on_unshare` failure)

## Acceptance Criteria

- [ ] `pip show asgi-lifespan` reports the installed package
- [ ] `cd /home/cprch/projects/the-one && make doctor` exits 0 with a one-line confirmation per dev extra
- [ ] Deliberately uninstalling `asgi-lifespan` and running `make doctor` reports a clear `ModuleNotFoundError: No module named 'asgi_lifespan'` and exits non-zero
- [ ] `ci/pipeline.yml`'s test task runs `make doctor` BEFORE `ruff check` + `ruff format --check` + `pytest`
- [ ] On a Linux host where `unshare -U` succeeds, `pytest tests/test_mcp_sandbox_integration.py::test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3` reports SKIPPED (not FAILED)
- [ ] `cd /home/cprch/projects/the-one && pytest --tb=no -q` exits 0 (broad pytest clean exit)

## Verification Steps

- `cd /home/cprch/projects/the-one && pip show asgi-lifespan | head -3` — shows installed version ≥ 2.0
- `cd /home/cprch/projects/the-one && make doctor` — exit 0
- `cd /home/cprch/projects/the-one && pip uninstall -y asgi-lifespan && make doctor; pip install asgi-lifespan` — `make doctor` should exit non-zero before reinstall, exit 0 after
- `cd /home/cprch/projects/the-one && grep -A3 "make doctor" ci/pipeline.yml` — invocation present before lint/test
- `cd /home/cprch/projects/the-one && pytest tests/test_mcp_sandbox_integration.py::test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3 -v` — the predicate covers three host shapes: (A) `cap_add: SYS_ADMIN` present → SKIPPED (unchanged from current behavior); (B) `cap_add: SYS_ADMIN` absent AND `unshare -U` succeeds (e.g., WSL2, stock Ubuntu — was FAILED pre-leg, now SKIPPED post-leg); (C) `cap_add: SYS_ADMIN` absent AND `unshare -U` fails (locked-down container) → PASSED (the test's intended path: EPERM actually fires, test asserts the error correctly). On the operator's WSL2 host the expected outcome is SKIPPED (case B); confirm in flight log which host shape the verification ran against.
- `cd /home/cprch/projects/the-one && pytest --tb=no -q` — exits 0; reports 1683+ collected; no errors at collection time; remaining tests pass or skip as expected
- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/` — still 0 errors (Leg 1's work not regressed by this leg)

## Implementation Guidance

1. **Install `asgi-lifespan`**
   - `cd /home/cprch/projects/the-one && pip install asgi-lifespan` (or `pip install -e .[dev]` which should pick it up)
   - Verify: `pip show asgi-lifespan` returns version ≥ 2.0

2. **Add the `doctor` Makefile target**
   - Inspect existing `Makefile` to match the style and indentation conventions
   - Add a target like:
     ```make
     .PHONY: doctor
     doctor:  ## Verify all declared dev extras are importable
     	@python -c "import asgi_lifespan, pytest_asyncio; import importlib.util; assert importlib.util.find_spec('playwright'), 'missing playwright'; assert importlib.util.find_spec('ruff') or True, 'ruff is a binary, not import'; print('doctor: ok')"
     ```
   - Rely on Python's non-zero exit code on `ImportError` / `AssertionError`. Do NOT use the `tee /dev/stderr | grep` pattern — it can false-positive if a probed package's import emits the string "OK" on stderr noise (per Architect design-review suggestion).
   - The exact import list should mirror what `pyproject.toml`'s `[project.optional-dependencies].dev` declares; verify each by inspecting `pyproject.toml`. Floor: `asgi_lifespan` is the mission criterion's hard requirement; the rest are nice-to-have.
   - Add a help-section comment (`## ...`) following the project's existing Makefile convention (look at sibling targets for the comment style)
   - For packages that are slow or environment-sensitive to import (e.g., `playwright`), use `importlib.util.find_spec(...)` which doesn't trigger module init
   - **Note**: when Leg 3 lands `pip-audit`, this target gets `pip_audit` added to the import list. Keep the Makefile target and the inline CI probe (step 3 below) in sync.

3. **Add doctor check to CI** (NOT via `make` — the CI image may not include it)
   - Architect spot-check (Phase 4b mission validation) noted: `mcr.microsoft.com/playwright/python:v1.58.0-jammy` is a minimal Ubuntu jammy image and does NOT ship `make` by default (Ubuntu's `make` is part of `build-essential`, not the base image).
   - Edit `ci/pipeline.yml`'s test task command sequence. Currently the chain is:
     ```
     cp -r /src /work && cd /work && pip install --no-cache-dir '.[dev]' -q && ruff check the_one/ tests/ && ruff format --check the_one/ tests/ && pytest ...
     ```
   - **Two options**:
     - **Option A (recommended)**: inline the doctor probe as a `python -c` directly in the pipeline `sh -c`, skipping the Makefile target for the CI path while keeping `make doctor` for dev-bench use:
       ```
       cp -r /src /work && cd /work && pip install --no-cache-dir '.[dev]' -q && python -c "import asgi_lifespan, pytest_asyncio, importlib.util; assert importlib.util.find_spec('playwright')" && ruff check the_one/ tests/ && ruff format --check the_one/ tests/ && pytest ...
       ```
     - **Option B**: prepend `apt-get install -y make` to the `sh -c`:
       ```
       cp -r /src /work && cd /work && apt-get install -y make >/dev/null && pip install --no-cache-dir '.[dev]' -q && make doctor && ruff check ...
       ```
   - Pick Option A — keeps the CI command terse and self-contained, avoids dependency on apt-get reachability in the build environment, and the Makefile target is still useful for developers running locally
   - The inline `python -c` should mirror what `make doctor` checks; keep the two in sync

4. **Tighten the sandbox skip predicate**
   - Locate `_has_sys_admin()` in `tests/test_mcp_sandbox_integration.py` (search around line 491)
   - The current predicate likely uses `os.geteuid() == 0` or a capability-bit check via `prctl`. Add an alternative branch that probes `unshare -U` success at module import time. Approximate shape:
     ```python
     import subprocess
     def _can_unshare_user_namespace() -> bool:
         try:
             result = subprocess.run(
                 ["unshare", "-U", "-r", "true"],
                 capture_output=True,
                 timeout=2,
                 check=False,
             )
             return result.returncode == 0
         except (FileNotFoundError, subprocess.TimeoutExpired):
             return False

     _SHOULD_SKIP_EPERM_TESTS = _has_sys_admin() or _can_unshare_user_namespace()
     ```
   - Update the test decorator(s) to skip when `_SHOULD_SKIP_EPERM_TESTS` is true rather than only when `_has_sys_admin()` is true
   - The leg's intent is "skip when the EPERM error path cannot be exercised in this environment" — clearer name + comment helps the next reader

5. **Verify broad pytest passes**
   - `cd /home/cprch/projects/the-one && pytest --tb=no -q`
   - Should report 1683+ collected, 0 errors at collection, no failures
   - If `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3` reports FAILED still, the skip predicate needs further refinement (likely the `unshare -U` probe shape is wrong on this host); iterate

6. **Verify the gate from Leg 1 still passes**
   - `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/` — both should exit 0
   - If this leg's Makefile or pipeline.yml edits introduce ruff violations, fix them inline

7. **Commit**
   - `git add Makefile ci/pipeline.yml tests/test_mcp_sandbox_integration.py`
   - Note: `pip install asgi-lifespan` is a local venv operation — no file change to commit for the install itself. But `pyproject.toml` already declares it; nothing to add there.
   - Commit message: `chore(tests): install asgi-lifespan + make doctor drift-detection + tighten sandbox skip predicate`

## Edge Cases

- **`make` not available** (some minimal containers): the CI test task uses `pip install` + chained commands explicitly rather than `make` for portability; `make doctor` works because the test task runs in a Playwright Python image that includes make. Verify by inspecting the image's apt list or running `which make` in a sandbox build.
- **`unshare` not available** (slim distros): the `_can_unshare_user_namespace()` probe's `FileNotFoundError` catch handles this. Result: probe returns False → predicate may not skip → test may run → test may pass or fail depending on environment. On hosts without `unshare`, the test should pass (no namespace creation = EPERM = test asserts correctly).
- **WSL2-specific behavior**: WSL2 supports user namespaces by default; the probe should return True there, leading to the test being skipped. Verify the operator's environment is WSL2 (per Mission Control environment notes).
- **Pytest collection errors from other root causes**: this leg targets `asgi-lifespan`; if `make doctor` surfaces additional missing extras, list them in the flight log and decide whether to install all here (low risk) or scope down to only `asgi-lifespan` (preferable if drift is non-trivial).
- **`make doctor` imports slow on cold venv**: the doctor target should be fast enough not to dominate CI time (<1s); if any single import is slow (`playwright` is a candidate), consider `python -c "import importlib.util; assert importlib.util.find_spec('playwright')"` as a no-import alternative.

## Files Affected

- `Makefile` — new `doctor` target
- `ci/pipeline.yml` — `make doctor &&` inserted into test task command chain at L24
- `tests/test_mcp_sandbox_integration.py` — `_has_sys_admin()` augmented with `_can_unshare_user_namespace()` probe; affected test decorator(s) updated
- `.venv/` — `asgi-lifespan` installed (not tracked, but state change is real)
- `flight-log.md` — Leg Progress entry added on completion

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing — broad pytest exits 0 (clean, not `-x`-terminated)
- [ ] `make doctor` proven to detect a missing extra (uninstall-then-doctor experiment)
- [ ] Update `flight-log.md` with leg progress entry
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in `flight.md`
- [ ] Commit all changes together (Makefile + ci/pipeline.yml + tests + flight artifacts)
