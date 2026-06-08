# Flight Log: Host-Native Runtime Readiness

**Flight**: [Host-Native Runtime Readiness](flight.md)

## Summary

Planning complete. Flight specced from Mission 15's Flight-1 sketch, refreshed
against current code. Two pre-execution investigations shaped the plan: a
reconnaissance pass over the folded-in Mission-14 maintenance debt (most already
satisfied), and a design-time empirical verification of the load-bearing premise
(host-native bwrap containment on WSL2 — confirmed). Not yet started.

---

## Reconnaissance Report

Phase-1b verification of the Mission-14 end-of-mission maintenance items folded into
this flight, checked against current code. Source: M14 mission-debrief action items.

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| `SandboxError` "import-cycle inversion" out of `mcp/errors.py` | **confirmed-live** (as a *layering* inversion, not a literal cycle) | `the_one/mcp/errors.py:37` defines it; imports are one-way (`sandbox/* → mcp.errors`), so no runtime cycle — but a sandbox-domain error living in the MCP module means each new M15 backend imports its error from `mcp.errors` | Keep live. Relocate to a sandbox-domain module + back-compat re-export → Leg 1 |
| Non-merged-usr `--symlink` portability caveat in `SECURITY-MODEL.md` | **confirmed-live** (missing) | Not present in `SECURITY-MODEL.md` | Add to Boxed Execution section → Leg 7 |
| Fork-safety convention in `agents.md` | **confirmed-live** (missing) | `agents.md:751` mentions `pty.fork()` in passing only; no convention documented | Add to conventions → Leg 7 |
| Boxed-profile network-off note | **already-satisfied** | `SECURITY-MODEL.md:154-158` documents it explicitly | Retire (closed-with-evidence) |
| `_TOOL_CLASSES` cross-config note | **already-satisfied** | `agents.md:1137-1146` | Retire |
| `@requires_bwrap` workspace-under-`$HOME` constraint | **already-satisfied** | `agents.md:1156` + `CLAUDE.md:165` | Retire |
| PTY-echo sentinel footgun | **already-satisfied** | `agents.md:1154` + `CLAUDE.md:164` | Retire |
| Forward-proof: `network_allowed` param on `_build_boxed_profile` | **already-satisfied** (intentional hardcode) | `the_one/tools/execution.py:487-491`; docstring states network is off by definition in a box | Retire (no change wanted) |
| Forward-proof: boxed-session reaper cleanup test | **already-satisfied** | `tests/test_pty_sandbox.py:548` `test_boxed_pty_session_cleanup_on_explicit_close`; reaper tests in `tests/test_session_registry.py` | Retire |
| `test_connectors_e2e.py::test_e2e_full_lifecycle` flake | **needs-human-recheck** | `tests/test_connectors_e2e.py:121-173`; no obvious timing/external dep from source; possible aiosqlite teardown / pool-reaper async race | Run under repeat/load; fix or quarantine → Leg 7 |

**Net**: of the folded-in M14 debt, only **2 doc notes** are genuinely missing and
the **flake** needs a live recheck; everything else is already satisfied (retired in
the flight as closed-with-evidence, not silently dropped). The `SandboxError`
relocation stays live as a layering fix despite there being no literal import cycle.

**Classification override of note**: the recon agent initially called `SandboxError`
`already-satisfied` (no runtime cycle). Overridden to `confirmed-live` — the M14
debrief's word was "inversion", a layering concern that survives the absence of a
literal cycle and bites once three backends import the error from `mcp.errors`.

---

## Decisions

### Load-bearing DD verified empirically at design time
**Context**: M14's standout methodology lesson — verify the single DD that, if
wrong, breaks the flight, against reality *before* locking the plan. Here that DD is
"the Linux sandbox backend works host-native (no Docker)"; today bwrap only runs
inside the container with `SYS_ADMIN` + `seccomp:unconfined`.
**Decision**: Ran the check on the primary dev box (WSL2, kernel
6.6.114.1-microsoft-standard) before specing the sandbox leg.
**Impact**: Confirmed feasible — de-risks Leg 4 and corrected the probe design (the
procfs knob is absent, so the probe must be empirical). Transcript:

```
$ uname -r                         → 6.6.114.1-microsoft-standard-WSL2
$ which bwrap                      → /bin/bwrap            (present host-side)
$ cat /proc/sys/kernel/unprivileged_userns_clone → (absent — knob not exposed)
$ cat /proc/sys/user/max_user_namespaces         → 63333
$ unshare --user --map-root-user echo …          → userns OK: mapped to 1000
$ bwrap --unshare-all --ro-bind / / --proc /proc --dev /dev --tmpfs /tmp \
    sh -c 'echo test > /etc/should_fail; ping -c1 8.8.8.8'
   → write to /etc blocked (good); net unreachable (good); exit=0
```

---

### Design review incorporated (Phase 5b)
**Context**: Architect review of the draft flight against the codebase returned
"approve with changes" with one HIGH issue and three execution hazards.
**Decision**: Incorporated all findings before presenting the spec:
- **`SandboxError` (HIGH)** — the architect showed a back-compat re-export from
  `mcp/errors.py` would *manufacture* a circular import (the factory documents this
  exact deferral at `factory.py:62-64`; the contract test pins subclass + identity).
  Reframed Leg 1 to move the *definition* into `platform/sandbox/errors.py` with a
  **one-way** base import and **no back-edge**, updating the ~2 importers + the
  contract test. Added a documentational fallback if relocation proves thorny.
- **Migration into temp dirs (HIGH/MED)** — every test sets `THE_ONE_DATA_DIR` to a
  fresh temp dir; an unconditional move would rename the dev's real `~/.the-one`.
  Added the default-path-only guard as a Leg 2 acceptance criterion + test.
- **`@requires_bwrap` default-deselected (MED)** — `pyproject.toml:76` deselects it,
  so "green including bwrap" needed an explicit `-m requires_bwrap` invocation; added
  to Legs 5 and 6.
- **Leg 4 "replace the raise" (MED)** — reframed as additive userns probe in the
  factory selection; the `__init__` backstop + its test stay.
- Softened false leg dependencies (Leg 1 not a hard predecessor; Leg 5 not gated on
  Leg 4's probe) and noted non-test Docker call-sites (`smoke-runtimes`,
  `brand-assets`) that remain out of scope.
**Impact**: No new legs; all fixes fit existing leg boundaries. Second focused pass
requested on the revised Leg 1 cycle-avoidance design.

### Second design-review pass (Phase 5b, cycle 2)
**Context**: Focused re-review of the revised Leg 1 (SandboxError) + the migration,
Leg-4, and bwrap fixes.
**Decision**: Verdict "approve with changes" — the round-1 HIGH (circular import) is
**resolved in design** (`mcp/errors.py` confirmed a zero-import leaf; one-way base
import + no back-edge cannot cycle). Two MEDIUM leg-spec completeness fixes folded in:
- **Leg 1 import set was ~3× too short** — the architect produced the complete set
  (6 source importers incl. the missed `bubblewrap.py:35`, `_tool.py:35`,
  `_tool_provider.py:57`, `api.py:1542`; + 8 test files; + the exact
  `test_sandbox_contract.py:32` repoint). Now enumerated verbatim in Leg 1, with the
  note that missing any fails the suite at import.
- **Leg 4 probe must be monkeypatchable** — else the pure-unit
  `tests/test_sandbox_factory.py` bwrap-present cases (lines 56-66, 109-119, 162-181,
  251-254) become environment-dependent. Now specified as `_userns_available()` +
  stub-`True` in those tests.
- Optional notes folded into Legs 2/4 (platformdirs-resolver monkeypatch; pydantic
  `model_fields_set` signal).
**Impact**: Max 2 review cycles reached; spec is codebase-validated. No design rework
outstanding — remaining items were leg-spec completeness, now closed.

---

## Deviations

### Phase 2d fix — filesystem denylist security regression (Leg 2)

**Regression**: Leg 2 changed `DEFAULT_PATH_DENYLIST` entry `"~/.the-one/secrets"` →
`"<data_dir>/secrets"`, treating it as a documentation placeholder rather than a live
access-control entry.  `canonicalize("<data_dir>/secrets")` resolves it to a bogus
CWD-relative path (`<cwd>/<data_dir>/secrets`) that matches nothing.  Net effect: the
old `~/.the-one/secrets` protection was silently removed AND the new platformdirs-based
secrets directory is unprotected.  The test suite stayed green because there was no
test asserting the `_canonical_denylist` contained the real `data_dir/secrets` path.

**Root-cause fix** (three changes):

1. **`the_one/tools/filesystem.py` — `DEFAULT_PATH_DENYLIST`**: Removed the
   `"<data_dir>/secrets"` literal and replaced it with a comment explaining that
   `data_dir/secrets` is appended dynamically in `model_post_init`.

2. **`the_one/tools/filesystem.py` — `FilesystemConfig.model_post_init`**: After
   canonicalizing the configured `path_denylist`, appends
   `canonicalize(str(settings.data_dir / "secrets"))` using a function-local import of
   `settings` from `the_one.config` (following the pattern established in
   `execution.py`/`sessions.py`).  This guarantees the agent's secrets dir is denied
   wherever `data_dir` resolves — default platformdirs path or
   `THE_ONE_DATA_DIR`/init override — with no placeholder risk.

3. **`the_one/config.py` — `errno.EXDEV` style fix (non-blocking)**: Changed
   `exc.errno == 18  # errno.EXDEV` → `import errno; exc.errno == errno.EXDEV` for
   readability.

**Regression test** (`tests/test_filesystem_config.py` — `TestDataDirSecretsDenylist`,
3 new tests):

- `test_canonical_denylist_contains_data_dir_secrets`: asserts the
  `_canonical_denylist` of a default `FilesystemConfig()` includes
  `canonicalize(str(settings.data_dir / "secrets"))`.
- `test_canonical_denylist_tracks_data_dir_override`: sets `THE_ONE_DATA_DIR` to an
  alternate path, resets `_settings` cache, and verifies the new denylist entry tracks
  the override.
- `test_filesystem_check_blocks_access_to_data_dir_secrets`: exercises the full
  enforcement path — creates a file inside `data_dir/secrets` and asserts
  `_filesystem_check` raises `ConstraintError` with "inside denylist".

  Tests reset `_settings` cache and inject `THE_ONE_DATA_DIR` via monkeypatch per the
  hermetic pattern established in `test_config_data_dir.py`.

**Updated test** (`TestCachingInvariant.test_canonicalize_called_exactly_n_plus_m_times`):
Corrected expected call count from 7 → 8 (3 allowlist + 4 explicit denylist + 1
dynamic `data_dir/secrets`).

**Verification**: targeted subset (`filesystem or denylist or data_dir`) — **169 passed**
(includes all 3 new regression tests); full default suite via `scripts/run-tests.sh` —
**3065 passed, 4 skipped, 576 deselected** (exit 0, +3 vs Leg-7 baseline of 3062);
`ruff check . && ruff format --check .` — clean (342 files).

---

## Anomalies

_None yet._

---

### Flight Director Notes

- **Phase 1 (context loading)** — Loaded `leg-execution.md` crew (Developer=Sonnet,
  Reviewer=Haiku; structure valid). Flight `ready` → `in-flight`. Branch
  `flight/01-host-native-runtime-readiness` created off `main` (carries the
  uncommitted planning artifacts). Git strategy: `branch`. Execution order
  1→2→3→4→5→6→7; review + commit deferred to Phase 2d (single batched review).
- **Test-apparatus decision (overrides crew prompt)** — The `leg-execution.md`
  "Implement" prompt hardcodes `docker exec the-one pytest`, but this flight retires
  that flow. Per the skill–project boundary (SKILL.md is the protocol; crew files are
  modifiable scaffolding), the Flight Director issues the test instruction per-spawn:
  legs **1–4** validate via the existing `docker exec the-one pytest -x --timeout 30`
  flow (container verified **up/healthy**); **Leg 5** establishes + validates the
  host-native invocation; **legs 6–7** and the Phase-2d final review run host-native
  (with `docker exec` still available as a fallback while the container exists).

## Leg Progress

### relocate-sandbox-error (Leg 1)

**Changes Made**

- Created `the_one/platform/sandbox/errors.py` — new canonical home for `SandboxError(MCPClientError)`, with a one-way import of `MCPClientError` from `the_one.mcp.errors`.
- Removed `SandboxError` class from `the_one/mcp/errors.py` (stays a zero-import leaf).
- Updated `the_one/platform/sandbox/__init__.py` — re-exports `SandboxError` from `.errors` instead of `the_one.mcp.errors`; updated docstring canonical-home reference.
- Updated `the_one/platform/sandbox/base.py` — rewrote "Error class" docstring to name `the_one/platform/sandbox/errors.py` as canonical.
- Updated `the_one/platform/sandbox/bubblewrap.py` — repointed `SandboxError` import to `.errors`.
- Updated `the_one/mcp/transports/stdio.py` — removed `SandboxError` from `mcp.errors` import; added to existing `the_one.platform.sandbox` import block.
- Updated `the_one/mcp/_tool.py` — removed top-level `SandboxError` import; added lazy import inside `execute()` to avoid circular import (see Notes).
- Updated `the_one/mcp/_tool_provider.py` — removed top-level `SandboxError` import; added lazy import inside `get_tools_for_agent()` Path-A branch for the same reason.
- Updated `the_one/interfaces/web/api.py` — repointed function-local `SandboxError` import to `the_one.platform.sandbox.errors`.
- Updated `the_one/agents.md:40` — rewrote the `canonical-import + convenience-re-export` pattern example to name `the_one.platform.sandbox.errors` as canonical.
- Removed stale import-cycle-inversion note from `the_one/platform/sandbox/factory.py:62-64`.
- Repointed all 8 test files: `test_sandbox_contract.py`, `test_sandbox_bubblewrap.py`, `test_mcp_stdio_error_translation.py`, `test_mcp_pool.py`, `test_mcp_stdio_sandbox.py`, `test_mcp_sandbox_integration.py`, `test_mcp_tool_provider.py`, `test_mcp_stdio_test_connect.py`.

**Notes**

A latent circular-import path was exposed by the move: `platform.sandbox.__init__` → `platform.sandbox.errors` → `mcp.errors` (triggers `mcp/__init__`) → `mcp._tool` → `platform.sandbox.errors` (partially initialized). This is a pre-existing loading hazard that only manifests once `platform.sandbox.errors` becomes a real module. Fixed by making the `SandboxError` import lazy (inside the function body) in both `mcp/_tool.py` and `mcp/_tool_provider.py` — these files are imported by `mcp/__init__` at package load time, so a top-level `SandboxError` import there would always trigger the cycle. The lazy import is safe because `SandboxError` is only used in `except` clauses (evaluated at runtime, not at class-body parse time).

**Results**

- Targeted tests (8 files, 146 selected): **143 passed, 3 skipped** — green.
- Full suite: **3045 passed, 4 skipped, 576 deselected** — green (pre-existing warnings only: `aiosqlite` event-loop teardown in `test_db_migration.py`, `StarletteDeprecationWarning` in `test_origin_allowlist.py`).
- `ruff check .` — clean (0 errors after import-order auto-fix).
- `ruff format --check .` — clean (446 files already formatted).
- All verification steps pass: residual `from the_one.mcp.errors import ... SandboxError` grep returns zero hits; identity+subclass one-liner exits OK; both cold-import checks exit 0.

---

### os-conventional-data-dir (Leg 2)

**Changes Made**

- `pyproject.toml` — added `platformdirs>=4.0` to `[project] dependencies`.
- `the_one/config.py` — replaced the hardcoded `data_dir: Path = Path.home() / ".the-one"` with `data_dir: Path = Field(default_factory=_default_data_dir)` where `_default_data_dir()` returns `Path(platformdirs.user_data_dir("the-one", appauthor=False))`. Added `import platformdirs`, `from pydantic import Field`, `import logging`, `import shutil`. Rewrote `ensure_dirs()` to call `_maybe_migrate_legacy()` before the `mkdir`; implemented the guarded migration with all four guards: (1) `"data_dir" not in self.model_fields_set`, (2) legacy exists and is a real directory (not symlink), (3) target does not already exist, (4) paths differ. EXDEV (cross-device) errors fall back to `shutil.copytree` + `rmtree`; all other `OSError`s are logged at WARNING and silently continued — `ensure_dirs()` never raises.
- `the_one/tools/filesystem.py` — changed the `DEFAULT_PATH_DENYLIST` doc example from `"~/.the-one/secrets"` to `"<data_dir>/secrets"` (comment/doc only; no behavior change).
- `the_one/platform/tempdirs.py` — added a clarifying comment to `user_config_dir()` noting that `the_one/config.py` via `platformdirs` is the canonical app data-directory resolver and this helper is a separate legacy path; deferred any consolidation to a later maintenance pass.
- `tests/test_config_data_dir.py` (new module) — 7 tests covering: (1) default resolution matches patched platformdirs resolver and `"data_dir" not in model_fields_set`; (2) migration moves a populated legacy dir and contents arrive; (3a) explicit `Settings(data_dir=...)` init override → legacy untouched; (3b) explicit `THE_ONE_DATA_DIR` env override → legacy untouched; (4) idempotency — two `ensure_dirs()` calls, single move, no error; (5) target already exists → no migration; (6) paths equal → no migration. Each test resets `_settings` cache and removes `THE_ONE_DATA_DIR` env var before constructing a fresh `Settings()`. Patching strategy: `monkeypatch.setattr("the_one.config.platformdirs.user_data_dir", ...)` reaches the factory call site regardless of the pydantic Field's captured function reference.

**Notes**

The patching approach required one non-obvious choice: pydantic captures the `default_factory` function object at class-definition time (the `Field(default_factory=_default_data_dir)` reference). Patching `the_one.config._default_data_dir` at the module level does not reach the already-captured factory. The correct patch target is `the_one.config.platformdirs.user_data_dir`, which is called inside `_default_data_dir()` via the module-level `platformdirs` reference — this always reaches the live call site. `Path.home()` inside `_maybe_migrate_legacy` is patched by replacing `the_one.config.Path` with a thin proxy class that overrides `.home()` only.

The full suite grew from 3045 to 3052 selected tests (+7 new, same 4 skipped, same 576 deselected).

**Results**

- New tests (7): **7 passed** — green.
- Full suite: **3052 passed, 4 skipped, 576 deselected** — green (pre-existing warnings only: aiosqlite event-loop teardown in `test_db_migration.py`, `StarletteDeprecationWarning` in `test_origin_allowlist.py`).
- `ruff check .` — clean (0 errors).
- `ruff format --check .` — clean (447 files already formatted after auto-format pass on `config.py`).
- Verification step: `docker exec -e THE_ONE_DATA_DIR="" the-one python -c "..."` with cache reset → prints `/root/.local/share/the-one`, matches `platformdirs.user_data_dir(...)`, `"data_dir" not in model_fields_set`.

---

### external-runtime-detection (Leg 3)

**Changes Made**

- `the_one/mcp/transports/stdio.py` — added a reusable `_RUNTIME_INSTALL_HINTS` mapping
  (`node`/`npx` → Node.js; `uv`/`uvx` → uv; `python`/`python3` → Python 3.11+) with a
  generic fallback, and rewrote the Pattern-1 `FileNotFoundError` message from the
  Docker-flavored "not available in the container / Add it to the Dockerfile / `make
  rebuild` / `docker compose exec`" text to host-native guidance: *"The command `<x>`
  was not found on PATH. <install-hint>. For one-off Python/JS MCPs, prefer the
  runtime-fetch shape: command=uvx … / command=npx …"*. Updated the stale Pattern-1
  catalog comment that quoted the old Docker text; left the bwrap-discriminator
  architectural docstrings intact. Patterns 2 & 3 unchanged.
- `tests/test_mcp_stdio_error_translation.py` — rewrote the Pattern-1 assertions (the
  `"Dockerfile"`/`"make rebuild"` asserts replaced by host-native-shape + Docker-token-
  absent asserts; `"uvx"` runtime-fetch assert preserved); added a case per known runtime
  + the generic fallback; updated the module docstring.

**Notes**

- **Surfacing confirmed** (design review): `MCPConnectionError.message` reaches the
  operator verbatim at the web MCP test/connect route (`interfaces/web/api.py:1590` →
  `mcp-server-editor.js:1942`) and the agent tool-call route (`mcp/_tool.py:166` →
  `cli.py:92`). No reformatting/swallowing.
- **FD note** — the implementing Developer agent stalled mid-run (returned before its
  final wrap-up). The Flight Director verified the work directly (targeted tests green;
  per-runtime message check Docker-free and names each runtime; `stdio.py` carries zero
  Docker tokens), ran the full suite to completion, and completed the leg wrap-up
  (status → landed, criteria checked, this entry). No code was authored by the FD — only
  verification + artifact closeout.

**Results**

- Targeted tests (`test_mcp_stdio_error_translation.py`): **18 passed** — green.
- Full suite: **3059 passed, 4 skipped, 576 deselected** in 317s — green (+7 new
  per-runtime cases; pre-existing warnings only).
- `ruff check .` — clean; `ruff format --check .` — clean (447 files).
- Tightened grep AC on `stdio.py` (`not available in the container` / `add it to the
  dockerfile` / `make rebuild` / `docker compose exec`) → zero hits.

---

### linux-sandbox-host-native (Leg 4)

**Changes Made**

- `the_one/platform/sandbox/factory.py` — Added module-level `_USERNS_PROBE` cache variable (type `Literal["ok", "unavailable", "error"] | None`). Added `_userns_available()` function: fast-path reads `/proc/sys/kernel/unprivileged_userns_clone` (absent = WSL2 case, not treated as negative); empirical probe via `subprocess.run(["bwrap", "--unshare-user", "--ro-bind", "/", "/", "/usr/bin/true"], timeout=5)`; `returncode==0` → `"ok"`, nonzero → `"unavailable"`, `OSError`/`TimeoutExpired`/`SubprocessError` → `"error"`; first real probe logged at DEBUG. Extended `_reset_selection_log_state()` to also reset `_USERNS_PROBE = None` (no separate hook). Inserted the new selection step in `get_sandbox_backend()` after the bwrap-missing block: `"unavailable"` → `PassthroughSandbox` + WARNING once (key `passthrough:userns-unavailable`); `"error"` → `PassthroughSandbox` + ERROR once (key `passthrough:userns-probe-error`); `"ok"` falls through to `BubblewrapSandbox`. Updated module docstring selection-order list from 4 steps to 6 steps (new steps 4 and 5 for userns-unavailable and userns-probe-error paths). Added `import subprocess` and `Literal` to imports.
- `tests/test_sandbox_factory.py` — Added `monkeypatch.setattr(factory_module, "_userns_available", lambda: "ok")` stub to 4 bwrap-present pure-unit tests: `test_factory_returns_bubblewrap_on_linux_with_bwrap`, `test_factory_no_bypass_when_only_one_flag_set`, `test_factory_logs_once_bubblewrap`, `test_factory_backend_name_bubblewrap`. Added 3 new tests: `test_factory_userns_ok_selects_bubblewrap`, `test_factory_userns_unavailable_selects_passthrough_with_warning` (asserts PassthroughSandbox + one-time WARNING with text "user namespaces unavailable"), `test_factory_userns_error_selects_passthrough_with_error_log` (asserts PassthroughSandbox + one-time ERROR, confirms log key `passthrough:userns-probe-error` present and `passthrough:userns-unavailable` absent).
- `tests/test_mcp_stdio_sandbox.py` — Added `monkeypatch.setattr(factory_module, "_userns_available", lambda: "ok")` stub to `test_connect_stdio_sdk_default_env_preserved_through_setenv` alongside its existing `factory_module.shutil.which` patch.

**Notes**

- Ruff caught `N806` (uppercase variable in function body) on the `_KNOB` local variable in `_userns_available()`; renamed to `_knob`.
- Cache reset is folded into `_reset_selection_log_state()` as required — the existing autouse `_reset_log_guard` fixture at `tests/test_sandbox_factory.py:39` calls exactly that function, so all tests (old and new) automatically reset the probe cache between tests with no fixture changes.
- `bubblewrap.py` and `tests/test_sandbox_bubblewrap.py` left entirely untouched per spec — backstop unchanged.

**Results**

- Targeted tests (`tests/test_sandbox_factory.py`, `tests/test_sandbox_bubblewrap.py`, `tests/test_mcp_stdio_sandbox.py`): **44 passed** — green.
- `docker exec the-one python -c "from the_one.platform.sandbox.factory import _userns_available; print(_userns_available())"` → **`ok`** (empirical probe succeeds in the bwrap-capable container).
- `-m requires_bwrap` suite: **31 passed, 3611 deselected** — green (real probe returns `"ok"`, BubblewrapSandbox selected, all bwrap integration tests pass).
- Full default suite: **3062 passed, 4 skipped, 576 deselected** in 355s — green (pre-existing warnings only: aiosqlite event-loop teardown in `test_db_migration.py`, `StarletteDeprecationWarning` in `test_origin_allowlist.py`).
- `ruff check .` — clean (after `_KNOB` → `_knob` rename); `ruff format --check .` — clean (447 files).

---

### de-docker-makefile (Leg 5)

**Changes Made**

- `Makefile` — Added `PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)` host-interpreter variable (command-line-overridable). Rewrote `_ensure-playwright` to host-native: `$(PY) -m playwright install chromium` (idempotent, no container). Converted all test targets to host-native (no `docker exec`): `test`, `test-unit`, `test-browser`, `test-pixel`, `test-live`, `test-discord-hat` now use `PYTHON=$(PY) bash scripts/run-tests.sh …` or `$(PY) -m pytest …`. Added new `test-bwrap` target: `$(PY) -m pytest -m requires_bwrap tests/ -v --tb=short`. Converted `lint`, `format`, `format-check` to host-native via `$(PY) -m ruff …`. Non-test container-management targets (`reset-db`, `restart`, `logs`, `shell`, `verify-serving`, `brand-assets`, `smoke-runtimes`) left on Docker as out-of-scope per spec. `grep -nE "docker (exec|compose)" Makefile` shows only non-test targets as required.
- `scripts/run-tests.sh` — Line 46: `setsid python -m pytest "$@"` → `setsid "${PYTHON:-python3}" -m pytest "$@"`. No other logic changes; group-kill/watchdog semantics intact.
- `the_one/platform/interpreter.py` — `resolve_python()` now returns `str(Path(sys.executable).resolve())` instead of bare `sys.executable`. On this host, `.venv/bin/python` is a symlink to `/usr/bin/python3.12` (merged-usr), so the resolved path is inside `/usr` and visible inside the boxed bwrap namespace without any new bind-mount. The docstring explains the merged-usr rationale and the edge-case guardrail (if a future host resolves outside `/usr`, the box fails clearly at execvp rather than silently widening). No new bind added.
- `tests/test_box_isolation.py:126` — Updated `test_boxed_root_ls_no_user_dirs`: removed `"home"` from the unconditional forbidden-dir set. On the host, the scratch workspace lives under `/home/<user>/`, so bwrap auto-creates `/home` as a parent of the writable `--bind` mount (analogous to how `/root` was auto-created in the container run). `"root"` was already excluded; `"home"` is now also excluded. Forbidden set is now `("app", "var")` — the entries that no bind forces into existence. The meaningful containment check (canary unreadable) is covered by `test_boxed_canary_unreadable`. Docstring updated to explain both container-/root/ and host-/home/ cases.
- `tests/test_pty_session.py:140,265` — `test_send_timeout_raises_when_no_output` and `test_select_timeout_clamped_when_budget_exhausted`: switched from `/bin/bash` to `/bin/sh` (dash). On WSL2, bash emits bracketed-paste-mode control sequences (`\x1b[?2004l`) when a command is submitted, even with `stty -echo` active. These bytes fill the PTY buffer and cause `send()` to return on idle-mark before the `TimeoutError` is raised — the test was masking the actual code path it was designed to pin. Dash has no readline/bracketed-paste integration and produces zero output for `read x` with echo off, making the tests deterministic across host environments. Docstring explains the WSL2 bash behavior.
- `tests/test_pty_sandbox.py:379` — `test_pty_network_denied_by_default_allowed_when_enabled`: added `await session.send("stty -echo")` before the network-probe `send()` call in both the deny and allow branches. On WSL2/Python 3.12, the PTY's 100ms idle window fires on the echoed command bytes before the python3 subprocess has time to connect and produce output, causing `send()` to return only the echo. With echo disabled, the buffer is empty until the command result arrives, ensuring reliable output capture. The `2>/dev/null && true || echo 'failed'` pipeline was also simplified to `2>/dev/null || echo 'failed'` (the redundant `&& true` removed).
- `.pytest_cache` — Root-owned container artifact; removed one-time via docker volume mount trick (`docker run --rm -v … alpine rm …`). Pytest re-creates it as the current user on next run. No code change.

**Notes**

1. **Boxed-mode interpreter fix** (`resolve_python()` → resolve symlink): The critical finding was that `sys.executable` on the host is `.venv/bin/python` — a symlink residing under `/home`, which is not bound inside a `minimal_rootfs=True` bwrap spawn (only `/usr` is bound). `Path(sys.executable).resolve()` follows the symlink chain to `/usr/bin/python3.12`. This path IS inside the box. No new bind added. GUARDRAIL confirmed: all `@requires_bwrap` containment tests pass after the fix, including `test_boxed_python_exec_canary_unreadable` (box cannot read host files), network-isolation, and no-host-FS-leak assertions. The fix is minimally scoped to the single `resolve_python()` call site.

2. **Forbidden-path assertion fix** (known failure #2): The `/home` directory appears in `ls /` inside the box because bwrap auto-creates parent directories of `--bind` targets — the scratch workspace (under `$HOME`) forces `/home` into existence, exactly as `/root` was forced in the container. The fix correctly excludes `/home` from the forbidden set while keeping `"app"` and `"var"` as the meaningful isolation check.

3. **PTY timing determinism** (known failure #3): The root cause was WSL2 bash readline emitting bracketed-paste control sequences even with echo off. Switching to `/bin/sh` (dash) eliminates this. The fix is deterministic across host environments. Not a timing hack — addresses the actual behavioral difference.

4. **`.pytest_cache` cleanup** (known failure #4): Removed via docker volume mount (no sudo available in this session). Pytest re-creates under current user ownership on next run.

5. **`test-live` `/app/` paths** (known failure #5 — note only): `tests/test_aiat.py:125,162` pass literal `/app/…` paths to a live agent. These are `-m live` (excluded from the default suite) and require a host-native running uvicorn instance. The `/app/` paths will not resolve on the host. `make test-live` now targets host-native pytest + host-native server. Noted in the `test-live` Makefile comment. No code change required; tracked for a future leg that updates the AIAT test paths.

**Results**

- `grep -nE "docker (exec|compose)" Makefile` → hits only in non-test out-of-scope targets: container lifecycle (`up`, `down`, `rebuild`, `rebuild-clean`, `reset-db`, `restart`, `logs`, `shell`) + `brand-assets` + `smoke-runtimes`. Zero hits in any test target.
- Host-native `make test-bwrap`: **31 passed, 3611 deselected** — green (all 5 `test_box_isolation.py` + 2 `test_mcp_pool.py` + 5 `test_builtin_tool_sandbox.py` + 5 `test_pty_sandbox.py` bwrap tests, plus 14 other `requires_bwrap` tests).
- Host-native `make test` (full default suite): **3062 passed, 4 skipped, 576 deselected** — green (confirmed via two independent runs; exit code 0).
- `ruff check . && ruff format --check .` → clean (342 files checked, all formatted).
- Real `~/.the-one` untouched: files unchanged (last-modified dates all pre-June; conftest `THE_ONE_DATA_DIR` override worked correctly — Leg 2 migration did NOT fire).
- CLAUDE.md update (testing section to reference host-native `.venv/bin/python -m pytest`): blocked by auto-mode classifier (self-modification guard). Noted for batched code review phase.

---

### pytest-ci (Leg 6)

**Changes Made**

- `.github/workflows/test.yml` (new) — three jobs on `ubuntu-latest`, Python 3.11,
  `cache: pip`, triggers `pull_request` + `push:main`, concurrency
  `test-${{ github.ref }}`: **`test`** (default suite, `python -m pytest tests/
  --timeout=300`), **`browser`** (`playwright install --with-deps chromium` +
  `THE_ONE_DEV_MODE=true … -m browser tests/browser/ --timeout=300`), **`bwrap`**
  (`apt-get install -y bubblewrap` + `-m requires_bwrap tests/ --timeout=300`). Lint
  workflow untouched. No Docker. YAML validated via `yaml.safe_load`.

**Browser-suite host-native investigation (the important part)**

A first host-native browser run reported **4 failures / 474 passed**
(`test_flow_new_chat`, `test_flow_studio_navigation`, `test_flow_studio_openrouter_picker`,
`test_oauth_modal_flow`). Root-caused — and the cause was **not** the tests:

- That run was launched with **bare `python -m pytest`**, bypassing
  `scripts/run-tests.sh`'s `setsid` process-group kill. When it was interrupted, its
  per-test **uvicorn subprocesses orphaned** (re-parented to `/init`) and kept running —
  5 of them, pegging a CPU core for 20-56 min.
- The accumulated load **starved the 4 browser tests** into timeout-failures (a
  resource-contention pseudo-deadlock — the "something else / undetected deadlock" the
  operator flagged).
- **Each of the 4 passes in isolation** (run via the wrapper: `4 passed in 7.51s`).
- After killing the 5 orphans, a **clean full run via the group-kill wrapper**
  (`TEST_TIMEOUT=900 … run-tests.sh -m browser tests/browser/ --timeout=90`) →
  **478 passed, 35 skipped, 0 failed** in 638s, exit 0, **0 orphans** after.

**Operational lesson (for the debrief)**: browser tests MUST run via
`scripts/run-tests.sh` (or any process-group-killing wrapper), **never bare
`python -m pytest`** host-native — bare pytest orphans the uvicorn/Chromium subtree on
any interruption, and the leaked load then fails *other* tests, masquerading as flakiness.
The FD hit this initially (CPU peg + false failures); corrected by routing through the
wrapper with a hard `TEST_TIMEOUT` cap. (CI's browser job runs on an ephemeral runner
where orphans die with the runner, so bare pytest + `--timeout` is acceptable there.)

**Notes**

- **Known pre-existing coverage gap** (not introduced here): ~12 bwrap-dependent
  integration tests in `tests/test_mcp_sandbox_integration.py` and
  `tests/test_mcp_stdio_sandbox.py:447` gate on a local `skipif(shutil.which("bwrap") is
  None)` rather than `@pytest.mark.requires_bwrap`, so `-m requires_bwrap` doesn't select
  them (they skip on the no-bwrap `test` job → no CI coverage). The 31 marked containment
  tests still give strong boundary coverage. Recorded for a future re-marking pass.
- CLAUDE.md still references `docker exec the-one pytest` (Leg 5 agent's edit was blocked
  by the self-modification guard) — FD to update in the documentation phase.

**Results**

- Full browser suite host-native (clean, wrapped): **478 passed, 35 skipped, 0 failed**;
  0 orphans after.
- Default suite **3062 passed** + `-m requires_bwrap` **31 passed** (Leg 5, unchanged).
- `test.yml` YAML valid; zero Docker references; lint workflow intact. First authoritative
  CI run lands on the PR (integration proof).

---

### m14-debt-closeout (Leg 7)

**Changes Made**

- `SECURITY-MODEL.md` — Added "Merged-usr portability caveat" subsection in the Boxed
  Execution Mode section (after "Read-scoping status", before "Passthrough degradation").
  Documents that the boxed `minimal_rootfs` `--symlink` entries (`usr/bin → /bin`,
  `usr/sbin → /sbin`, `usr/lib → /lib`, `usr/lib64 → /lib64`) in
  `the_one/platform/sandbox/bubblewrap.py` assume a merged-usr host layout. States the
  failure mode on non-merged-usr hosts (dangling symlinks, broken dynamic linker) and
  the portability note (deployment target is merged-usr only — bookworm/Ubuntu 22.04+).
- `the_one/agents.md` — Added "Fork-safety convention (PTY spawn path)" paragraph
  immediately after the `_build_subprocess_env` call-sites block (near line 751 where
  `pty.fork()` is already referenced). Documents: only async-signal-safe operations
  between `fork()` and `execvp()`; no Python allocator/logging/lock/import/asyncio;
  multi-threaded-parent hazard (child inherits only forking thread's stack, all other
  threads' locks remain held); safe today because exec follows fork immediately; audit
  warning for any future work added between fork and exec.

**Flake Characterization — `test_connectors_e2e.py::test_e2e_full_lifecycle`**

- `pytest-repeat` not available; used a bash for-loop of 30 iterations.
- Command: `for i in $(seq 1 30); do … TEST_TIMEOUT=60 … run-tests.sh test_e2e_full_lifecycle --timeout=30 -p no:cacheprovider -q; done`
- Result: **30/30 passed, 0 failed** — flake NOT reproducible under load.
- Verdict: No root cause to fix; no quarantine warranted (do not quarantine a test that
  isn't actually flaking). The suspected aiosqlite event-loop-teardown / pool-reaper
  async race may already be mitigated by earlier legs' changes. Leaving as-is.

**M14 Already-Satisfied Items — Closed with Evidence**

| Item | Evidence (satisfying location) | Status |
|------|--------------------------------|--------|
| Boxed-profile network-off note | `SECURITY-MODEL.md:154-158` — "Network unconditionally off" subsection documents that `_build_boxed_profile` in `the_one/tools/execution.py` hardcodes `network_allowed=False` | Retired |
| `_TOOL_CLASSES` cross-config note | `the_one/agents.md:1137-1146` — cross-Config `_TOOL_CLASSES` dispatch note present | Retired |
| `@requires_bwrap` workspace-under-`$HOME` constraint | `the_one/agents.md:1156` + `CLAUDE.md:165` — "Sandbox testing footguns" item 3 documents that bwrap mounts a fresh tmpfs at `/tmp`, making `/tmp`-rooted workspaces invisible; use `home_workspace()` | Retired |
| PTY-echo sentinel footgun | `the_one/agents.md:1154` + `CLAUDE.md:164` — "Sandbox testing footguns" item 2 documents the PTY-echo sentinel and the `"con"+"nected"` string-concat trick | Retired |
| `network_allowed` hardcode in boxed profile | `the_one/tools/execution.py:487-491` — `_build_boxed_profile` hardcodes `network_allowed=False`; docstring states network is off by definition in a box | Retired |
| Boxed-session reaper cleanup test | `tests/test_pty_sandbox.py:548` — `test_boxed_pty_session_cleanup_on_explicit_close` + reaper tests in `tests/test_session_registry.py` | Retired |

**Results**

- `grep -in "merged-usr\|symlink" SECURITY-MODEL.md` → 9 hits (lines 196-209) — caveat present.
- `grep -in "fork-safe\|fork safety\|async-signal" the_one/agents.md` → 3 hits (lines 758, 760, 769) — convention present.
- Flake characterization: 30/30 passes; no fix or quarantine needed.
- Full default suite: **3062 passed, 4 skipped, 576 deselected** in 369s — green.
- `ruff check . && ruff format --check .` — clean (342 files, 0 errors).

---

## Session Notes

- **Planning session** — Flight refreshed from the Mission-15 sketch. Codebase recon
  mapped every scope area to a concrete change site (data-dir `config.py:22`,
  Docker-flavored MCP error `stdio.py:287-293`, bwrap-only `__init__`
  `bubblewrap.py:81-89`, all-`docker exec` Makefile `110-135`, lint-only CI). Three
  scope forks resolved with the operator: keep as one flight; `~/.the-one` migration
  = move/rename; provision bwrap in a dedicated Linux CI job. M14 maintenance recon
  and the host-native bwrap verification (above) completed before legs were locked.

---

## Flight Closeout (Phase 2d / 3)

- **Batched review** (Sonnet, scaled to the security-critical sandbox diff): one
  BLOCKING finding — `DEFAULT_PATH_DENYLIST`'s `"<data_dir>/secrets"` was a dead entry
  (the Leg-2 spec wrongly called a live access-control guard a "doc example"). Fixed at
  root cause: removed the bogus literal, append `canonicalize(settings.data_dir/"secrets")`
  in `FilesystemConfig.model_post_init` so the agent's secrets dir is denied wherever
  `data_dir` resolves (default or override) + 3 regression tests. Re-review: confirmed.
- **Commits** (branch `flight/01-host-native-runtime-readiness`):
  - `42d27da` flight/01: host-native runtime readiness — 44 files (Flight-1 + artifacts).
  - `68e3cce` fix(ui): recover orphaned chat/studio working-tree fixes — 2 JS files that
    were found uncommitted in the working tree (unrelated to M15), included at operator
    request as a separate, clearly-labeled commit.
- **PR**: draft #109 → main. First authoritative run of the new `test.yml` (test / browser
  / bwrap jobs) executes on this PR.
- **Statuses**: 7 legs → completed; flight → landed; Flight 1 checked in mission.md.
- **Open follow-ups** (carried, not silently dropped):
  1. `CLAUDE.md` testing section still says `docker exec the-one pytest` — host-native
     update blocked by the auto-mode self-modification guard; needs operator authorization.
  2. ~12 bwrap integration tests use `skipif(which("bwrap"))` not `@requires_bwrap`, so the
     bwrap CI job doesn't select them — future re-marking pass.
  3. `test-live` `test_aiat.py` `/app/...` paths assume a container; need host-native paths.
  4. Non-test Docker Makefile targets (`smoke-runtimes`, `brand-assets`, container
     lifecycle) remain — later flights retire Docker fully.
- **Operational lesson** (for the debrief): browser tests must run via
  `scripts/run-tests.sh` (group-kill), never bare `python -m pytest` — bare pytest orphans
  the uvicorn/Chromium subtree, and the leaked CPU load fails *other* tests as false flakes.

[COMPLETE:flight]
