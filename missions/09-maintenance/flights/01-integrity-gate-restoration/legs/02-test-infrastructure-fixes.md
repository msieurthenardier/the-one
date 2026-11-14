# Leg: 02-test-infrastructure-fixes

**Status**: completed
**Flight**: [Integrity Gate Restoration](../flight.md)

## Objective

Resolve the two test-infrastructure issues surfaced by the 2026-05-15 maintenance Inspector: `asgi-lifespan` declared-but-not-installed masks 6 MCP HTTP integration tests at collection time, and `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3`'s skip predicate is over-narrow (fails on common Linux dev hosts where user namespaces are permitted but `cap_add: SYS_ADMIN` is absent). Add a `make doctor` drift-detection target so missing dev extras fail loud rather than masking integration tests.

> **Scope pivot 2026-05-15**: Concourse is being removed in this flight's Leg 4. The original Leg 2 plan added `make doctor` as both a Makefile target AND a CI-inline `python -c` probe in `ci/pipeline.yml`. With CI going away, this leg keeps the `make doctor` Makefile target as a local-bench drift detector but drops the `ci/pipeline.yml` edit. The Makefile target is still valuable for catching `pip install -e .[dev]` drift before pytest collection time.

## Context

The maintenance report's Category 2 surfaced two Action Required test findings (2.1, 2.2) with a shared root: the test suite trusts its declared dev extras + skip predicates without verification. The `asgi-lifespan` case is the more dangerous one — it silently un-covers 6 MCP HTTP integration tests (`TestL3IntegrationSmoke::*`, `TestL4StreamableHttp::*`, `TestL6aHappyPath::*`, `TestL6bInputValidationIntegration::*`) because pytest reports them as collection errors that look like skips at a glance. CI doesn't see this issue because CI installs `.[dev]` fresh in an ephemeral container; only the developer's drifted venv shows the symptom — but the asymmetry is exactly the kind of "works on CI, broken on dev" problem that erodes confidence in the test suite.

The sandbox skip predicate (`_has_sys_admin()` at `test_mcp_sandbox_integration.py:491-511`) was written for the container case where `cap_add: SYS_ADMIN` flips the capability bit. On unprivileged Linux hosts (e.g., WSL2 with `kernel.unprivileged_userns_clone=1`, or stock Ubuntu), the capability check returns false but `unshare -U` still succeeds — so the sandbox creates user namespaces successfully and the EPERM the test expects never fires. The fix is to also probe `unshare -U` actually succeeding before deciding whether to skip.

Design decision from flight: drift-detection mechanism is a `make doctor` Makefile target that imports each declared dev extra inside a `python -c` and fails with a clear `ModuleNotFoundError` naming the missing extra. CI runs `make doctor` as the first step in the test task (before `ruff`), so a missing extra fails the pipeline before any test runs.

## Inputs

- `pyproject.toml` `[project.optional-dependencies].dev` list. **Starter probe set** (the floor; expand to mirror full `pyproject.toml` dev extras at execution time): `asgi_lifespan`, `pytest_asyncio`, `playwright` (via `importlib.util.find_spec` to avoid slow full import), `ruff` (also `find_spec`-checked). After Leg 3 lands `pip-audit`, also probe `pip_audit`. The `asgi-lifespan` probe is the mission criterion's hard requirement; the rest are nice-to-have.
- `tests/conftest.py:238` — `from asgi_lifespan import LifespanManager` import that fails at module load on the HOST venv (the container has `asgi-lifespan` installed via `pip install -e .[dev]` at image build time, so `docker exec the-one pytest` is unaffected; this leg targets the host venv specifically)
- `tests/test_mcp_sandbox_integration.py:175` — `_has_sys_admin()` helper (parses `/proc/self/status` CapEff bit-21, NOT `prctl`/`geteuid`)
- `tests/test_mcp_sandbox_integration.py:488-492` — the `@pytest.mark.skipif(_has_sys_admin(), reason="...")` decorator that needs to extend its predicate
- `tests/test_mcp_sandbox_integration.py:493` — the failing test body `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3`
- `Makefile` — current targets list
- `ci/pipeline.yml:22-24` — CI test task

## Outputs

- `asgi-lifespan` installed in the active venv
- `Makefile` gains a `doctor` target that imports each dev extra
- `ci/pipeline.yml` gains a `make doctor` invocation as the first sub-step of the test task
- `tests/test_mcp_sandbox_integration.py` — `_has_sys_admin()` (or equivalent skip predicate) tightened to also probe `unshare -U` success
- Broad pytest exits with code 0 (no errors at collection, no `test_sandbox_eperm_on_unshare` failure)

## Acceptance Criteria

- [ ] `pip show asgi-lifespan` (HOST venv — `/bin/pip`, not `docker exec`) reports the installed package
- [ ] `cd ~/projects/the-one && make doctor` (HOST-side: target shells `python -c "..."` directly, NOT `docker exec`) exits 0 with a one-line confirmation
- [ ] Deliberately uninstalling `asgi-lifespan` on the host and running `make doctor` reports a clear `ModuleNotFoundError: No module named 'asgi_lifespan'` and exits non-zero
- [ ] (DROPPED — Concourse going away in Leg 4) ~~`ci/pipeline.yml`'s test task runs `make doctor` BEFORE `ruff check` + `ruff format --check` + `pytest`~~. `make doctor` ships as a host-bench target only.
- [ ] On the operator's HOST (WSL2, `unshare -U` succeeds without privilege), `cd ~/projects/the-one && pytest tests/test_mcp_sandbox_integration.py::test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3 -v` reports SKIPPED with a reason citing the new `_can_unshare_user_namespace()` branch. **Verification must run on HOST, not container** — the container has `cap_add: SYS_ADMIN` which short-circuits to the existing `_has_sys_admin()` branch and never exercises the new predicate.
- [ ] `cd ~/projects/the-one && pytest --tb=no -q` (HOST) exits 0 — proves the asgi-lifespan install + predicate fix engage on the operator's primary host pytest invocation point
- [ ] `docker exec the-one pytest --tb=no -q --ignore=tests/browser` (CONTAINER) still exits 0 — Leg 1's clean container baseline preserved

## Verification Steps

All commands run on the HOST unless explicitly prefixed `docker exec`.
- `pip show asgi-lifespan | head -3` (HOST) — shows installed version ≥ 2.0
- `cd ~/projects/the-one && make doctor` — exit 0; one-line per probed extra
- `cd ~/projects/the-one && pip uninstall -y asgi-lifespan && make doctor; pip install asgi-lifespan` (HOST) — `make doctor` should exit non-zero before reinstall, exit 0 after
- ~~`grep -A3 "make doctor" ci/pipeline.yml`~~ DROPPED — Concourse going away in Leg 4
- `cd ~/projects/the-one && pytest tests/test_mcp_sandbox_integration.py::test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3 -v` (HOST) — the predicate covers three host shapes: (A) `cap_add: SYS_ADMIN` present → SKIPPED (the container branch — verified via `docker exec` if desired); (B) WSL2/stock-Ubuntu host where `unshare -U` succeeds without privilege — was FAILED pre-leg, now SKIPPED post-leg via the new `_can_unshare_user_namespace()` branch (this is the operator's primary path); (C) locked-down host where `unshare -U` fails — PASSED (test's intended path: EPERM fires, test asserts correctly). On the operator's WSL2 host the expected outcome is **case B → SKIPPED**; document the observed case in flight log.
- `cd ~/projects/the-one && pytest --tb=no -q` (HOST) — exits 0; reports 1683+ collected; no errors at collection time; remaining tests pass or skip as expected
- `docker exec the-one pytest --tb=no -q --ignore=tests/browser` (CONTAINER) — exits 0; preserves Leg 1's clean baseline (1679 passed)
- `cd ~/projects/the-one && ruff check the_one/ tests/` — still 0 errors (Leg 1's work not regressed by this leg)

## Implementation Guidance

1. **Install `asgi-lifespan` on the HOST venv**
   - The container already has it (verified Leg 1: clean collection); this step targets the host venv where the operator runs `pytest` directly.
   - `pip install asgi-lifespan` (NOT `docker exec` — host pip)
   - Verify: `pip show asgi-lifespan` returns version ≥ 2.0

2. **Add the `doctor` Makefile target — HOST-side, not container**
   - Note: `make lint` / `make format` in this project run via `docker exec the-one` (container-first). `make doctor` is DELIBERATELY different — it probes host-venv drift, which is exactly the case that motivated Leg 1's `asgi-lifespan` discovery (host missing, container fine). Add a section-header comment block: `# ── Drift detection (host-side) ──`.
   - Add the target:
     ```make
     .PHONY: doctor
     doctor:  ## Verify all declared dev extras are importable on the host venv
     	@python -c "import asgi_lifespan, pytest_asyncio, pytest_timeout, pytest_playwright, pixelmatch; from PIL import Image; import importlib.util; assert importlib.util.find_spec('playwright'), 'missing playwright'; import ruff; print('doctor: ok')"
     ```
   - Important name mismatches to get right:
     - `pillow` package → `from PIL import ...` (NOT `import pillow`)
     - `playwright` — slow init; use `find_spec` not direct `import`
     - `ruff` — IS importable as `import ruff` (don't `or True` it; drop the no-op)
   - Rely on Python's non-zero exit code on `ImportError` / `AssertionError`. Do NOT use the `tee /dev/stderr | grep` pattern — it can false-positive if a probed package's import emits the string "OK" on stderr noise.
   - The full probe set should mirror `pyproject.toml`'s `[project.optional-dependencies].dev`:
     - `pytest>=8.0` (assumed present; not probed — running pytest implies presence)
     - `pytest-asyncio>=0.24` → probe as `import pytest_asyncio`
     - `pytest-timeout>=2.4` → `import pytest_timeout`
     - `ruff>=0.6` → `import ruff`
     - `playwright==1.58.0` → `find_spec('playwright')` (slow init)
     - `pytest-playwright>=0.5` → `import pytest_playwright`
     - `pillow>=10.0` → `from PIL import Image`
     - `pixelmatch>=0.3` → `import pixelmatch`
     - `asgi-lifespan>=2.0` → `import asgi_lifespan`
   - Floor: `asgi_lifespan` is the mission criterion's hard requirement; the rest catch broader drift.
   - **Leg 3 will add**: `pip_audit` — when Leg 3 lands, append `import pip_audit` to this target's probe.

4. **Tighten the sandbox skip predicate**
   - Helper currently at `tests/test_mcp_sandbox_integration.py:175`: `_has_sys_admin()` parses `/proc/self/status` for the CapEff line and checks bit 21 (SYS_ADMIN). Decorator at `:488-492`: `@pytest.mark.skipif(_has_sys_admin(), reason="...")`. Test body at `:493+`.
   - Add a sibling helper that probes whether the host can create user namespaces without privilege (WSL2, stock Ubuntu — kernel allows `unshare -U` for unprivileged users):
     ```python
     import subprocess
     def _can_unshare_user_namespace() -> bool:
         try:
             result = subprocess.run(
                 ["unshare", "-U", "-r", "true"],
                 timeout=2,
                 check=False,
             )
             return result.returncode == 0
         except (FileNotFoundError, subprocess.TimeoutExpired):
             return False

     _SHOULD_SKIP_EPERM_TESTS = _has_sys_admin() or _can_unshare_user_namespace()
     ```
   - Update the decorator at L488 from `_has_sys_admin()` to `_SHOULD_SKIP_EPERM_TESTS`. Update the reason text to cite both branches: `reason="Test exercises the no-privilege-grants path; skip when SYS_ADMIN is granted (container) OR when unshare -U succeeds without privilege (WSL2, stock Ubuntu host)"`.
   - The leg's intent is "skip when the EPERM error path cannot be exercised in this environment" — clearer name + comment helps the next reader.
   - HOST PROBE CONFIRMED during design review: on the operator's WSL2 host, `unshare -U -r true` exits 0, so the new branch will trigger and the test will SKIP (not FAIL) on host runs.

5. **Verify broad pytest passes — on HOST**
   - `cd ~/projects/the-one && pytest --tb=no -q` (HOST — proves asgi-lifespan install + predicate fix both engage)
   - Should report 1683+ collected, 0 collection errors, 0 failures
   - If `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3` reports FAILED still, the skip predicate needs refinement; iterate
   - Also: `docker exec the-one pytest --tb=no -q --ignore=tests/browser` (CONTAINER) — should still exit 0 (1679 passed per Leg 1); confirms no regression

6. **Verify the Leg 1 baseline still passes**
   - `cd ~/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/` — both should exit 0
   - If this leg's Makefile or test-file edits introduce ruff violations, fix them inline

7. **Commit**
   - `git add Makefile tests/test_mcp_sandbox_integration.py` (NOT `ci/pipeline.yml` — that file is gone in Leg 4; NOT `-A` — explicit paths only)
   - Note: `pip install asgi-lifespan` is a host-venv operation — no file change to commit for the install itself. `pyproject.toml` already declares it; nothing to add there.
   - Commit on the flight branch with a heredoc commit message (matching Leg 1's `flight/01:` convention):
     ```bash
     git commit -m "$(cat <<'EOF'
     flight/01: install asgi-lifespan + make doctor (host) + tighten sandbox skip predicate

     Mission: 09
     EOF
     )"
     ```
   - Do NOT push.
   - Update leg status `ready` → `in-flight` at the start of implementation; → `landed` at the end (NOT `completed` — flight close handles that).
   - Update `flight-log.md` with a Leg 2 Progress entry.
   - Signal `[HANDOFF:review-needed]` when done.

## Edge Cases

- **`make` not available** (some minimal containers): the CI test task uses `pip install` + chained commands explicitly rather than `make` for portability; `make doctor` works because the test task runs in a Playwright Python image that includes make. Verify by inspecting the image's apt list or running `which make` in a sandbox build.
- **`unshare` not available** (slim distros): the `_can_unshare_user_namespace()` probe's `FileNotFoundError` catch handles this. Result: probe returns False → predicate may not skip → test may run → test may pass or fail depending on environment. On hosts without `unshare`, the test should pass (no namespace creation = EPERM = test asserts correctly).
- **WSL2-specific behavior**: WSL2 supports user namespaces by default; the probe should return True there, leading to the test being skipped. Verify the operator's environment is WSL2 (per Mission Control environment notes).
- **Pytest collection errors from other root causes**: this leg targets `asgi-lifespan`; if `make doctor` surfaces additional missing extras, list them in the flight log and decide whether to install all here (low risk) or scope down to only `asgi-lifespan` (preferable if drift is non-trivial).
- **`make doctor` imports slow on cold venv**: the doctor target should be fast enough not to dominate CI time (<1s); if any single import is slow (`playwright` is a candidate), consider `python -c "import importlib.util; assert importlib.util.find_spec('playwright')"` as a no-import alternative.

## Files Affected

- `Makefile` — new `doctor` target (host-side; see step 2 for section-header convention)
- `tests/test_mcp_sandbox_integration.py` — sibling helper `_can_unshare_user_namespace()` added; `_SHOULD_SKIP_EPERM_TESTS` constant added; the L488 `@pytest.mark.skipif` decorator's predicate + reason updated
- host pip env — `asgi-lifespan>=2.0` installed (not tracked, state change is real)
- `flight-log.md` — Leg Progress entry added on completion

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Host pytest exits 0 (asgi-lifespan installed); container pytest still exits 0
- [ ] `make doctor` proven to detect a missing extra (uninstall-then-doctor experiment on host)
- [ ] Update `flight-log.md` with leg progress entry
- [ ] Set this leg's status to `landed` (NOT `completed` — flight close handles that)
- [ ] Commit (Makefile + tests/test_mcp_sandbox_integration.py + flight artifacts) with the heredoc-formatted `flight/01:` prefix message
