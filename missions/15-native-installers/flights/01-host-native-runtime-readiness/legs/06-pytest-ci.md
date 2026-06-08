# Leg: pytest-ci

**Status**: completed
**Flight**: [Host-Native Runtime Readiness](../flight.md)

## Objective

Stand up a host-native pytest CI on GitHub Actions: a default-suite job on
`ubuntu-latest` and a dedicated bwrap-provisioned job that runs `-m requires_bwrap` so the
sandbox boundary is exercised in CI — with no Docker and the existing lint workflow kept.

## Context

- **Flight DDs** — "Flight-1 CI scope is Linux host-native pytest (+ bwrap job); per-OS
  test matrix rides with later flights." Installer-build/signing CI is **Flight 6** — out
  of scope here.
- Today the only workflow is **lint-only** (`.github/workflows/lint.yml`: ruff check +
  format on `ubuntu-latest`, Python 3.11). There is **no pytest CI**.
- Leg 5 made the suite run host-native; this leg runs it in CI the same way (no `.venv` in
  CI — the Makefile `PY` var falls back to `python3`, and CI installs deps fresh).
- **Python floor 3.11** (`pyproject.toml:5`, `requires-python = ">=3.11"`); lint CI already
  pins 3.11. Use **3.11** in the test CI as the supported floor (local dev validated 3.12).
- **Deps**: `pip install -e ".[all-llms,dev]"` — `dev` includes `playwright==1.58.0` +
  `pytest-playwright`; `all-llms` adds the provider SDKs. Browser tests need
  `THE_ONE_DEV_MODE=true` and a provisioned Chromium; the browser conftest spawns its own
  host-native uvicorn (no running server needed).
- **`@requires_bwrap` is default-deselected** (`pyproject.toml:76`) — the bwrap job must
  invoke `-m requires_bwrap` explicitly. `ubuntu-latest` runners have unprivileged user
  namespaces enabled, so Leg 4's probe returns "ok" and `BubblewrapSandbox` is selected →
  containment tests run for real. *(Confirmed on first CI run; the flight's divert
  criterion covers the unlikely case ubuntu-latest disables userns.)*
- Independent of other legs in code; depends on Leg 5's host-native targets existing.

## Inputs

- `.github/workflows/lint.yml` (kept as-is; conventions to mirror).
- `pyproject.toml` extras (`all-llms`, `dev`) and pytest config (default-deselect markers).
- Leg 5's host-native Makefile targets (`make test`, `make test-bwrap`) and
  `scripts/run-tests.sh`.

## Outputs

- A new `.github/workflows/test.yml` with **three** jobs on `ubuntu-latest`, Python 3.11:
  - **`test`**: install deps, run the default host-native suite (unit; browser/live/pixel/
    bwrap are addopts-deselected). No Chromium needed here.
  - **`browser`**: install deps + Chromium (`playwright install --with-deps chromium`), run
    `-m browser tests/browser/` with `THE_ONE_DEV_MODE=true`.
  - **`bwrap`**: `apt-get install -y bubblewrap`, install deps, run `-m requires_bwrap`.
- All pytest invocations carry `--timeout=300` (no global pytest-timeout default exists,
  so a hang would otherwise run to GitHub's 6-hour cap).
- The existing lint workflow unchanged and still running.

**Design-review corrections folded in:**
- The default suite **excludes** browser tests (`pyproject.toml` addopts), so a single
  job + `playwright install` would never run them — browser coverage needs its own
  `-m browser` job (matches the mission's "provision Playwright/Chromium on runners" env
  requirement).
- `--timeout=300` added because there is no `timeout =` default in
  `[tool.pytest.ini_options]`; only a few tests carry `@pytest.mark.timeout`.
- **Known pre-existing gap (note, not fixed here)**: ~12 bwrap-dependent integration
  tests in `tests/test_mcp_sandbox_integration.py` and `tests/test_mcp_stdio_sandbox.py:447`
  gate on a local `skipif(shutil.which("bwrap") is None)` rather than the
  `@pytest.mark.requires_bwrap` marker, so `-m requires_bwrap` does not select them and
  they skip on the no-bwrap `test` job — leaving them without CI coverage. Pre-existing
  (not introduced by this flight). Recorded for a future maintenance pass to re-mark them;
  the 31 marked containment tests still give strong boundary coverage in the `bwrap` job.

## Acceptance Criteria

- [x] `.github/workflows/test.yml` exists, triggers on `pull_request` and `push` to
      `main` (mirroring lint), with a concurrency group cancelling in-progress runs.
- [x] **`test` job**: `ubuntu-latest`, `actions/setup-python@v5` Python 3.11,
      `pip install -e ".[all-llms,dev]"`, runs the default suite host-native
      (`python -m pytest tests/ --timeout=300 --tb=short`). No Chromium, no
      `THE_ONE_DEV_MODE`, no `docker`.
- [x] **`browser` job**: same base, provisions Chromium
      (`python -m playwright install --with-deps chromium`), runs
      `THE_ONE_DEV_MODE=true python -m pytest -m browser tests/browser/ --timeout=300 --tb=short`.
      Browser suite validated host-native: **478 passed, 0 failed** (clean wrapped run).
- [x] **`bwrap` job**: `apt-get install -y bubblewrap`, same Python + deps, runs
      `python -m pytest -m requires_bwrap tests/ --timeout=300 --tb=short`. Exercises real
      containment (probe → "ok" → BubblewrapSandbox); count matches local (31).
- [x] Every pytest invocation carries `--timeout=300`.
- [x] The lint workflow (`.github/workflows/lint.yml`) is untouched and still present.
- [x] No Docker anywhere in the new workflow.
- [x] Workflow YAML is valid (parses; jobs/steps well-formed) — validated via
      `yaml.safe_load`; the first real CI run on the PR confirms green (integration proof).
- [x] `ruff` remains clean (no source changes expected beyond the workflow file).

## Verification Steps

- `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/test.yml')); print('yaml ok')"`.
- Local dry equivalents (already green from Leg 5): `make test` and `make test-bwrap`
  host-native — the CI mirrors these commands.
- `grep -i docker .github/workflows/test.yml` → no hits.
- First CI run on the PR: both jobs green (recorded in flight log / debrief as the
  integration proof). The bwrap job's `requires_bwrap` count should match local (31).

## Implementation Guidance

1. **Create `.github/workflows/test.yml`** mirroring `lint.yml` conventions (3 jobs):
   ```yaml
   name: test
   on:
     pull_request:
     push:
       branches: [main]
   concurrency:
     group: test-${{ github.ref }}
     cancel-in-progress: true
   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.11"
             cache: pip
         - run: pip install -e ".[all-llms,dev]"
         - name: Run default suite (host-native)
           run: python -m pytest tests/ --timeout=300 --tb=short
     browser:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.11"
             cache: pip
         - run: pip install -e ".[all-llms,dev]"
         - name: Provision Chromium
           run: python -m playwright install --with-deps chromium
         - name: Run browser tests (host-native)
           env:
             THE_ONE_DEV_MODE: "true"
           run: python -m pytest -m browser tests/browser/ --timeout=300 --tb=short
     bwrap:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - name: Install bubblewrap
           run: sudo apt-get update && sudo apt-get install -y bubblewrap
         - uses: actions/setup-python@v5
           with:
             python-version: "3.11"
             cache: pip
         - run: pip install -e ".[all-llms,dev]"
         - name: Run @requires_bwrap sandbox tests
           run: python -m pytest -m requires_bwrap tests/ --timeout=300 --tb=short
   ```
   (Direct `python -m pytest` avoids a Make dependency in CI and lets each job carry its
   own `--timeout`. Equivalent `make test`/`make test-bwrap` calls are acceptable but the
   direct form is preferred here.)

2. **Three single-purpose jobs** — `test` (fast unit signal, no Chromium), `browser`
   (Chromium + `-m browser`), `bwrap` (bubblewrap + `-m requires_bwrap`). They run in
   parallel; each installs deps once. Do not collapse `test` and `browser` into one job —
   the default suite excludes browser, so browser needs its own `-m browser` invocation.

3. **`--timeout=300` on every pytest call** — there is no global pytest-timeout default,
   so this bounds any hang well under GitHub's 6-hour job cap. (`pytest-timeout` is already
   a dev dep.)

4. **Do NOT** add installer-build, signing, or per-OS (macOS/Windows) test jobs — those
   are Flights 2/3/6. **Do NOT** chase the pre-existing skipif-integration coverage gap
   here (note it in the flight log for a future re-marking pass).

5. **Validate the YAML locally** (`yaml.safe_load`) and confirm no Docker references.

## Edge Cases

- **ubuntu-latest userns disabled** (unlikely) — the bwrap job's containment tests would
  fail (probe degrades to passthrough). Flight divert criterion: re-plan the bwrap job
  (privileged step / self-hosted) — but ubuntu-latest enables unprivileged userns by
  default, so this is a noted low risk confirmed on first run.
- **Chromium system deps** — `playwright install --with-deps chromium` pulls the apt libs
  via the runner's sudo; no manual lib list needed.
- **Browser tests flaky in CI** — `run-tests.sh`'s watchdog isn't used in the direct
  `python -m pytest` form; rely on `pytest-timeout` (already configured) to bound hangs.
  If using `make test`, the setsid watchdog applies.
- **First-run cost** — two jobs install deps twice; acceptable. Caching mitigates.

## Files Affected

- `.github/workflows/test.yml` — **new**.

---
