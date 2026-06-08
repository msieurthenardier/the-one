# Leg: de-docker-makefile

**Status**: completed
**Flight**: [Host-Native Runtime Readiness](../flight.md)

## Objective

Convert the Makefile **test** flow from `docker exec the-one …` to host-native `pytest`
invocation (using the repo `.venv` when present), provision Playwright/Chromium on the
host, add an explicit `-m requires_bwrap` target, and prove the full suite green
host-native with no Docker.

## Context

- **Flight DD** — this is the apparatus pivot: after this leg, the dev/test loop runs
  host-native; Leg 6 (CI) and the Phase-2d final review build on it.
- **Host environment confirmed** (Flight Director probe): host has `python3` 3.12.3, an
  editable `the-one` install, `bwrap` at `/bin/bwrap`, and a working **`.venv`**
  (gitignored; has `pytest` + `playwright` + `the_one`). The only gap is host
  Chromium provisioning.
- **Current Makefile test targets** all shell into the container:
  - `test`, `test-unit`, `test-browser`, `test-pixel` → `docker exec the-one bash
    /app/scripts/run-tests.sh …`
  - `test-live`, `test-discord-hat` → `docker exec the-one pytest …`
  - `_ensure-playwright` → installs Chromium **in the container**.
- **`scripts/run-tests.sh`** is already host-portable (setsid process-group kill) **except**
  it hardcodes `setsid python -m pytest` (line 46) — host has `python3`/`.venv/bin/python`,
  not bare `python`. Make the interpreter configurable.
- **`@requires_bwrap` is default-deselected** (`pyproject.toml:76`) — needs an explicit
  `-m requires_bwrap` target or it runs zero bwrap tests (design-review finding).
- **Out of scope (stay on Docker this leg)** — non-test container-management targets:
  `reset-db`, `restart`, `logs`, `shell`, `verify-serving`, `brand-assets`,
  `smoke-runtimes`. The mission retires those across later flights; the grep-based AC
  is scoped to the **test** targets only.
- Independent of Legs 1-4, but its *validation* exercises their changes host-native (esp.
  Leg 4's userns probe and Leg 2's data-dir under the host's real `~/.the-one`/XDG).

## Inputs

- `Makefile` test targets (`test`, `test-unit`, `test-browser`, `test-pixel`,
  `test-live`, `test-discord-hat`, `_ensure-playwright`).
- `scripts/run-tests.sh` with the hardcoded `python` interpreter.
- The repo `.venv` (host test environment) and `pyproject.toml` pytest config
  (default-deselect markers).

## Outputs

- Test targets invoke host-native `pytest` (no `docker exec`), via a Makefile-level
  interpreter variable that prefers `.venv/bin/python` and falls back to `python3`.
- `scripts/run-tests.sh` interpreter is configurable (`PYTHON` env, default `python3`),
  group-kill semantics intact host-native.
- A new explicit `test-bwrap` target running `-m requires_bwrap`.
- `_ensure-playwright` provisions Chromium on the **host** cache (idempotent).
- Documented evidence that the full default suite + `-m requires_bwrap` + the browser
  subset pass host-native with no Docker.

## Acceptance Criteria

- [x] `make test`, `make test-unit`, `make test-browser`, `make test-pixel`,
      `make test-live`, `make test-discord-hat` run host-native `pytest` — **no
      `docker exec`** in any test target. `grep -nE "docker (exec|compose)" Makefile`
      shows hits only in the out-of-scope non-test targets listed in Context.
- [x] A Makefile interpreter variable (e.g. `PY`) resolves to `.venv/bin/python` when
      present, else `python3`, and is overridable on the command line.
- [x] `scripts/run-tests.sh` uses `"${PYTHON:-python3}" -m pytest` (not bare `python`);
      the Makefile passes the resolved interpreter; group-kill/watchdog behavior unchanged.
- [x] A new `test-bwrap` target runs `-m requires_bwrap` host-native (these are
      default-deselected, so the default targets don't cover them).
- [x] `_ensure-playwright` checks/install Chromium on the host Playwright cache
      (idempotent; no container), and `make test-browser` passes host-native.
- [x] **Full default suite passes host-native** (`make test` or direct `.venv` pytest),
      **including a separate `-m requires_bwrap` run** — both green, no Docker involved.
- [x] `ruff check`/`ruff format` clean (run host-native via the `.venv`).
- [x] The five Known Host-Native Failures below are resolved at root cause: boxed-mode
      interpreter fix (containment tests still green), boxed forbidden-path assertion,
      PTY timing determinism, `.pytest_cache` cleanup, and the `test-live` note. No
      `xfail`/`skip` papering; escalate in the flight log only if genuinely unfixable.
- [x] After the boxed-interpreter fix, **all `@requires_bwrap` containment tests still
      pass** — the box cannot read host files (`test_boxed_python_exec_canary_unreadable`),
      network is off, no host FS leak. The fix must not widen the box.

## Verification Steps

- `grep -nE "docker (exec|compose)" Makefile` → hits only in `reset-db`/`restart`/`logs`/
  `shell`/`verify-serving`/`brand-assets`/`smoke-runtimes` (non-test).
- Host-native full suite: `.venv/bin/python -m pytest --timeout 60 -q` (or `make test`) →
  green; record pass/skip/deselect counts.
- Host-native bwrap: `.venv/bin/python -m pytest -m requires_bwrap --timeout 60 -q` (or
  `make test-bwrap`) → green (real userns probe returns "ok" on this host).
- Host-native browser: `make test-browser` after `_ensure-playwright` → green.
- `.venv/bin/ruff check . && .venv/bin/ruff format --check .` → clean.

## Implementation Guidance

1. **Add an interpreter variable** near the top of the Tests section (or Makefile head):
   `PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)`
   (overridable: `make test PY=python3.11`).

2. **Make `run-tests.sh` interpreter-configurable** — change line 46 from
   `setsid python -m pytest "$@"` to `setsid "${PYTHON:-python3}" -m pytest "$@"`. No other
   logic changes (the setsid/process-group/watchdog mechanism is host-portable as-is).

3. **Rewrite the test targets** to host-native, dropping `docker exec` and the `/app/`
   path prefix (run from repo root):
   - `test` → `PYTHON=$(PY) bash scripts/run-tests.sh tests/ -v --tb=short`
   - `test-unit` → `PYTHON=$(PY) bash scripts/run-tests.sh tests/ -m 'not browser and not live and not pixel' -v --tb=short`
   - `test-browser` → `_ensure-playwright` then `PYTHON=$(PY) bash scripts/run-tests.sh -m browser tests/browser/ -v --tb=short`
   - `test-pixel` → likewise host-native
   - `test-live` → `$(PY) -m pytest -m live tests/test_aiat.py -v --tb=short`
   - `test-discord-hat` → `$(PY) -m pytest -m discord_hat tests/live/discord_hat/ -v --tb=short`

4. **Add `test-bwrap`** target:
   `test-bwrap: ## Run @requires_bwrap sandbox tests host-native`
   → `$(PY) -m pytest -m requires_bwrap tests/ -v --tb=short` (note: `-m requires_bwrap`
   on the CLI overrides the default-deselect in `pyproject.toml`).

5. **Convert `_ensure-playwright`** to host: check the host Playwright cache and install
   if missing — `$(PY) -m playwright install chromium` is idempotent (skips when present).
   (System `install-deps` may need sudo; on this WSL2/Ubuntu host the Chromium deps are
   typically already present — only run `install-deps` if a browser-launch failure shows
   missing libs, and note it as a host-setup prerequisite rather than failing the leg.)

6. **Run the full host-native suite and fix host-specific breakage at root cause.** Expect
   possible differences vs the container (Python 3.12 vs 3.11; real host `~/.the-one`/XDG
   paths interacting with Leg 2's migration — the conftest `THE_ONE_DATA_DIR` override
   should keep migration from firing, but verify; real host `bwrap`/userns via Leg 4).
   Fix root causes; do not skip. Record counts in the flight log.

7. **Run `ruff` host-native via `.venv`.**

## Known Host-Native Failures to Fix (from design review — a host slice was run)

The design-review Developer ran a host-native slice and found these concrete failures;
fix each at root cause (the AC forbids `xfail`/`skip`):

1. **Boxed-mode interpreter outside `/usr` (HIGH, security-sensitive)** — `python_exec`
   in **boxed** mode passes `sys.executable` to bwrap, which on the host is
   `.venv/bin/python` (under `/home`). Boxed mode mounts only `/usr`
   (`bubblewrap.py:154`), so bwrap fails `execvp …/python: No such file or directory`.
   Affected: `tests/test_box_isolation.py:56-155` (4 tests) +
   `tests/test_builtin_tool_sandbox.py::test_boxed_python_exec_canary_unreadable` (line 365).
   **Fix (minimal, safe)**: for boxed spawns, resolve the interpreter to its real path —
   `Path(sys.executable).resolve()` — and use that; on this host `.venv/bin/python`
   symlinks into `/usr` (merged-usr), so the resolved path is already inside the box and
   needs **no new bind**. Only if the resolved path still falls outside `/usr` should a
   **read-only** bind of the interpreter be added. The likely locus is
   `the_one/platform/interpreter.py:46` (`resolve_python()`) and/or the boxed branch in
   `bubblewrap.py`. **Guardrail — containment must not regress**: every box-isolation
   containment assertion must stay green, especially `test_boxed_python_exec_canary_unreadable`
   (the box must still NOT read host files) and the network-off / no-host-FS assertions.
   Run `-m requires_bwrap` and confirm all pass after the fix.
2. **Boxed `ls /` forbidden-path assertion (LOW, follow-on)** — `test_box_isolation.py:126`
   forbids `"root"` in the boxed root listing (a container-ism). Host-native, the writable
   workspace lives under `/home`, so `/home` may appear; update the forbidden-set to be
   correct host-native (parallel the `"root"` exclusion) **without** weakening the real
   containment check. Verify only after fix #1 lands.
3. **PTY timing tests (HIGH)** — `tests/test_pty_session.py:140` and `:265`
   (`test_send_timeout_raises_when_no_output`, `test_select_timeout_clamped_when_budget_exhausted`)
   assume container/3.11 PTY-echo timing and don't raise on WSL2/3.12. Make them
   deterministic (a command that provably yields zero PTY output with echo verified off,
   and/or a tighter timeout) so they assert the real property regardless of host. If
   genuinely unfixable in scope, escalate in the flight log with rationale — not a skip.
4. **`.pytest_cache` owned by root (MED, host setup)** — a leftover from container runs;
   each host run warns `[Errno 13] Permission denied`. Clear it (`rm -rf .pytest_cache`
   or chown) as a one-time host cleanup — no code change.
5. **`test-live` `/app/` paths (LOW, note only)** — `tests/test_aiat.py:125,162` pass
   literal `/app/...` paths to a live agent; these are `-m live` (excluded from the default
   suite) and require a host-native uvicorn. Out of default-suite scope; note in the flight
   log that `make test-live` now needs a host-native server and the `/app/` paths won't
   resolve on the host.

## Edge Cases

- **`python` vs `python3`** — the host lacks bare `python`; the `PYTHON` env + `.venv`
  resolution handles it. Don't assume `python`.
- **Leg 2 migration under host run** — the suite sets `THE_ONE_DATA_DIR` (conftest), so
  migration must NOT fire and must NOT touch the real `~/.the-one`. Confirm the dev's real
  data dir is untouched after a full host run.
- **Chromium deps missing** — surface as a clear host-setup message, not a silent browser
  hang; `run-tests.sh`'s watchdog bounds any hang.
- **`.venv` absent on another machine** — the `PY` fallback to `python3` keeps targets
  working if the developer uses a different env; document the `.venv` assumption.
- **CI reuse** — Leg 6 will reuse these host-native targets; keep them CI-friendly
  (no interactive prompts, deterministic interpreter resolution).

## Files Affected

- `Makefile` — interpreter variable; rewrite `test`/`test-unit`/`test-browser`/
  `test-pixel`/`test-live`/`test-discord-hat`/`_ensure-playwright`; add `test-bwrap`.
- `scripts/run-tests.sh` — configurable interpreter (line 46).
- `the_one/platform/interpreter.py` and/or `the_one/platform/sandbox/bubblewrap.py` —
  boxed-mode interpreter resolution fix (known failure #1; security-sensitive).
- `tests/test_box_isolation.py` — forbidden-path assertion host-correctness (known #2).
- `tests/test_pty_session.py` — deterministic timeout tests (known #3).
- (Possibly) other small host-compat fixes if the full host run surfaces more
  container-only assumptions — recorded in the flight log.

---
