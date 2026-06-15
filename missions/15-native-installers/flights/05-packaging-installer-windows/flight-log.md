# Flight Log: Packaging & Installer — Windows

**Flight**: [Packaging & Installer — Windows](flight.md)

## Summary

Flight planned 2026-06-14. Status: **`landed` 2026-06-14**. Windows-first packaging —
the cross-cutting freeze runtime seam (`clean_subprocess_env` child-env sanitizer,
frozen-detection, `resolve_python` frozen fix, unencoded-I/O audit, the `the-one
doctor` diagnostic) built here and reused by F6 (macOS) / F7 (Linux), plus the
PyInstaller `.spec`, the Inno Setup installer, and a CI packaged-smoke that proves
the frozen-app child-spawn fix against the packaged binary on a `windows-2022`
runner. **All 5 legs complete; the `windows-packaged-smoke` job is green (the frozen
child-spawn fix proven on the packaged binary, the Inno installer builds). Optional
operator HAT deferred to F9.** PR #112 (base `flight/04`).

---

## Leg Progress

### 2026-06-14 — Leg 1 (frozen-runtime-seam-and-doctor) → `landed`

**Changes made:**

- **`platform/env.py`** — added the freeze seam: `is_frozen()` (reads
  `sys.frozen`/`sys._MEIPASS`), `_bundle_dir()` (handles one-dir + one-file
  layouts), `strip_bundle_dir_from_path()` (removes the bundle dir from `PATH`
  anywhere it appears, `os.path.normcase`/`normpath`-normalized for Windows),
  and `clean_subprocess_env()` (fast no-op when not frozen; when frozen: strip +
  augment with platform-appropriate common runtime dirs and a
  `THE_ONE_EXTRA_PATH` operator override, de-duped order-preserving). Applied
  inside `_build_subprocess_env()` so every spawn path (MCP stdio, shell,
  python-exec, PTY) inherits the sanitized env with no per-call-site change.
- **`mcp/transports/stdio.py`** — re-applied `strip_bundle_dir_from_path()` at
  the caller (`_build_stdio_params`, ~line 430) *after* the `build_stdio_environ`
  merge, so an operator `PATH` in MCP config can't re-introduce the bundle dir
  (strip-always-wins). `build_stdio_environ` left pure (untouched).
- **`platform/interpreter.py`** — `resolve_python()` frozen branch: resolves a
  real external interpreter (`THE_ONE_PYTHON` override, else `python3`/`python`
  on the augmented PATH via `shutil.which`), raising the new
  `FrozenInterpreterError` (actionable, non-Docker) when none is found.
  Non-frozen behavior unchanged.
- **`platform/shell.py`** — `select_shell()` POSIX branch resolves a bare `$SHELL`
  to an absolute path (against the augmented PATH, fallback `/bin/sh`) when
  frozen, so the post-fork `execvp` in `pty_unix.py` (which consumes
  `select_shell()[0]`) doesn't bare-name-exec against a stripped PATH. Windows
  `cmd.exe` path untouched.
- **Encoding audit (DD4)** — added `encoding="utf-8"` to `agent/store.py`
  (4 read/write sites), `tools/filesystem.py:412,506` (writes),
  `interfaces/web/app.py:1631` (read). `sandbox/factory.py:104` carries the
  documented Linux-only/ASCII disposition comment. `errors="replace"` read sites
  left as-is. Grep confirms no remaining unencoded product text-I/O.
- **`.env` anchoring (DD8)** — `config._resolve_env_file()` (module-level, run at
  class-definition time) anchors `env_file` to the platformdirs data dir when
  frozen, else keeps relative `.env`. `THE_ONE_*` env vars unaffected.
- **`diagnostics.py` (new) + `main.py` `doctor` branch + `__main__.py` (new)** —
  `the-one doctor` (and `python -m the_one doctor`): builds the real spawn env,
  spawns a probe child (`sh -c echo` / `cmd /c echo`) through it and verifies
  round-trip, resolves the interpreter, runs a fresh `detect_runtimes()` presence
  check (reusing `_RUNTIME_INSTALL_HINTS` for messaging only), prints structured
  PASS/FAIL with a `child spawn: OK/FAIL` line, exits non-zero on failure. LLM-free.
- **Docs** — `CLAUDE.md` (commands block + a frozen-runtime-seam paragraph),
  `README.md` (usage line) updated for `the-one doctor`.
- **Tests (new/extended)** — `test_frozen_runtime_seam.py` (seam + allowlist
  invariant), `test_doctor.py`, extensions to `test_platform_interpreter.py`
  (frozen branch), `test_platform_shell.py` (frozen shell resolution),
  `test_mcp_stdio_sandbox.py` (purity + strip-survives-merge),
  `test_config_data_dir.py` (`.env` anchoring).

**Decisions (carried from DECIDED design points, no deviation):** MCP precedence
via caller-side `strip_bundle_dir_from_path`; overrides read from raw `os.environ`
(no `platform → config` import cycle); `build_stdio_environ` kept pure; no
restore-`*_ORIG` code — the allowlist invariant is asserted by a test instead.
Added a `the_one/__main__.py` so the leg's `python -m the_one doctor` verification
command works (console-script `the-one` already existed; this mirrors it).

**Test results:** full host-native default unit suite green —
**3110 passed, 10 skipped, 589 deselected** (`-m 'not live and not browser and not
pixel and not requires_bwrap and not discord_hat'`). ruff check + format clean on
all touched files. `the-one doctor` exits 0 on the host with `child spawn: OK`.

**Anomalies:** none. (The aiosqlite "Event loop is closed" / forkpty
DeprecationWarnings in the suite output are pre-existing teardown noise, unrelated
to this leg.)

**Acceptance criteria:** all met. POSIX frozen-hardening (shell/execvp/resolve_python
POSIX side) is written + unit-tested per the leg's scope note — correctness coverage
for F7, not a Windows-smoke gate; the Windows `cmd.exe`/pywinpty path is unchanged.

### 2026-06-14 — Leg 2 (pyinstaller-windows-spec) → `landed`

**Changes made:**

- **`packaging/windows/the-one.spec` (new)** — checked-in PyInstaller **one-dir**
  spec (DD1: `COLLECT`, not one-file). Top-of-file `sys.path.insert(0, repo_root)`
  (computed two parents up from `SPECPATH`) runs *before* `from the_one import
  __version__`. `APP_VERSION` reads `the_one.__version__` (`0.2.0`, not the stale
  pyproject `0.1.0`) and is used for the EXE/dist-dir name + a build-log print
  only — **`EXE(version=)` is omitted** (a bare string breaks the build; it needs
  a `VSVersionInfo` resource). DD7 collection contract: `collect_all('uvicorn')`,
  `collect_submodules('mcp')`, `collect_dynamic_libs('winpty')` **plus `'winpty'`
  in `hiddenimports`** (the helper grabs binaries only, not the pure-Python
  submodules), the lazy app subpackages (`interfaces.cli`/`interfaces.web.app`/
  `interfaces.app`/`diagnostics`/`webview`), `aiosqlite`+`sqlite3`; cryptography
  & pywebview→pythonnet left to their contrib hooks. Static assets via
  `collect_data_files('the_one', includes=['interfaces/web/static/**/*'])` (78
  files, package-relative path preserved for `_MEIPASS` resolution, DD8).
  `excludes=['nacl']` (Discord voice unused). **Single multi-call EXE** (DD6):
  one `the-one.exe` dispatching all subcommands via `cli_entry()` on argv,
  `console=True`. Inline Leg-4 note for the `--add-binary` pywinpty fallback.
- **`packaging/windows/frozen_entry.py` (new)** — `multiprocessing.freeze_support()`
  **before** `cli_entry()` (DD7). Build artifact only.
- **`packaging/windows/README.md` (new)** — native-Windows-only (not WSL2) build
  caveat, prerequisites (`pip install -e ".[gui,all-llms]"` + `pip install
  pyinstaller`), build command, `dist/the-one/the-one.exe` output, version/PyNaCl/
  pywinpty notes.
- **`tests/test_frozen_entry.py` (new)** — loads the entry by path via `importlib`,
  asserts `freeze_support` runs before `cli_entry` (call-order recorded; both
  patched), plus the no-run-on-plain-import guard. 5 tests, host-native.
- **Docs** — one-line Windows-packaging pointers added to `CLAUDE.md` (after the
  frozen-runtime-seam paragraph) and `README.md` (after the desktop-window section).

**Verification:**

- `python -m py_compile packaging/windows/the-one.spec packaging/windows/frozen_entry.py`
  → OK (syntactically valid). `tests/test_frozen_entry.py` also compiles.
- `tests/test_frozen_entry.py` → **5 passed**. Broader unit suite (`-m 'not live
  and not browser and not pixel and not requires_bwrap and not discord_hat'`) →
  green (see results below).
- ruff `check` + `format` clean on the touched real Python modules
  (`frozen_entry.py`, `test_frozen_entry.py`). The `.spec` is a PyInstaller config
  file (not a `*.py` module) — ruff's default file discovery does not pick it up
  (`ruff check packaging/` passes), so its build-injected globals (`Analysis`/
  `PYZ`/`EXE`/`COLLECT`) never surface as lint errors in CI/pre-commit. No
  pyproject ruff-config change needed.
- Invariant confirmed: `the_one/` imports nothing under `packaging/` (grep clean).

**Deferred to Leg 4 (forward dependencies, not gates this leg):**

- The actual frozen-build + launch proof on `windows-2022` (PyInstaller + winpty/
  pywebview are Windows-native; cannot run on this Linux/WSL2 host) is performed by
  Leg 4's CI packaged-smoke, which consumes this `.spec`.
- **Leg 4's freeze job MUST `pip install -e ".[gui,all-llms]"` then `pip install
  pyinstaller`** — the existing `windows` job in `test.yml` installs only
  `.[all-llms,dev]` (no `[gui]`); without `[gui]` the spec's pywebview→pythonnet
  collection import-fails at build time. (Recorded in the leg artifact + README.)

**Decisions/deviations:** none beyond the DECIDED design points. Made `APP_VERSION`
load-bearing via a build-log `print` (so it isn't a comment-only/unused import).

**Anomalies:** none.

**Acceptance criteria:** all locally-verifiable criteria met; the two
`windows-2022` build/launch criteria are recorded as Leg-4 forward dependencies.

### 2026-06-14 — Leg 3 (inno-windows-installer) → `landed`

**Changes made:**

- **`packaging/windows/the-one.iss` (new)** — the Inno Setup installer script.
  `[Setup]`: frozen hardcoded `AppId={{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}`
  (the upgrade/uninstall identity — never regenerate); `AppName=GleepGlorp AI`,
  `AppVerName=GleepGlorp AI {#AppVersion}`; `DefaultDirName={autopf}\GleepGlorp AI`;
  `PrivilegesRequired=admin` (Program Files install — per-user `lowest` alternative
  documented as out-of-scope); `ArchitecturesAllowed`/`ArchitecturesInstallIn64BitMode
  =x64compatible` (Inno ≥6.3, pinned by Leg 4; `x64` fallback noted in a comment, not
  left live); `OutputBaseFilename=the-one-setup-{#AppVersion}`; `OutputDir=Output`
  (→ `packaging/windows/Output/`); `SetupIconFile=installer-assets\the-one.ico`;
  `UninstallDisplayIcon={app}\the-one.ico` (branded — the exe has no embedded icon
  resource); `Compression=lzma2`/`SolidCompression=yes`; `WizardStyle=modern`. Version
  via `#ifndef AppVersion` guard defaulting `"0.2.0"`, overridable by
  `iscc /DAppVersion=`. `[Files]` recursively sources `..\..\dist\the-one\*` → `{app}`
  (`recursesubdirs createallsubdirs ignoreversion`) plus the `.ico` into `{app}`.
  `[Tasks]` `desktopicon` checkbox; `[Icons]` Start-menu + (gated) Desktop shortcuts
  → `{app}\the-one.exe` `Parameters: "app"` `IconFilename: {app}\the-one.ico`, plus an
  Uninstall shortcut. `[Run]` optional post-install launch (`nowait postinstall
  skipifsilent`). Inert/commented `SignTool=`/`SignedUninstaller` hook for future
  signing (no rework). Inno default uninstaller (no custom `[UninstallDelete]`).
- **`packaging/windows/installer-assets/the-one.ico` (new)** — byte-identical `cp`
  of `the_one/interfaces/web/static/brand/favicon.ico` (sha256
  `3032a53d…09ad8f9`, 6977 bytes), so the installer doesn't reach into the app's live
  static tree and a future icon swap is localized.
- **`packaging/windows/README.md`** — extended with the installer section: build
  command (`iscc packaging\windows\the-one.iss`, `/DAppVersion=` override), the
  native-Windows-only `iscc` caveat, the `packaging\windows\Output\the-one-setup-*.exe`
  artifact path, the display-name/slug split callout, the icon-source note, the
  admin/per-user privilege rationale, and the **SmartScreen unsigned-app workaround**
  ("Windows protected your PC → More info → Run anyway") for F9 to inherit.

**Verification:**

- `.iss` statically reviewed against the leg's directive list — every `[Setup]`
  directive present and correctly spelled; `AppId` is a single hardcoded GUID
  (`grep -c "^AppId=" → 1`); `[Icons]` pass `Parameters: "app"`; `#define AppVersion`
  guarded by `#ifndef` and referenced as `{#AppVersion}` in `AppVersion` +
  `OutputBaseFilename` (so `/D` wins); `[Files]` `Source` is `..\..\dist\the-one\*`
  (resolves from the `.iss` to the repo-root `dist/`); only `x64compatible` is live
  (`x64` appears solely in a comment).
- **`iscc` NOT run** — it is Windows-only and unavailable on this Linux/WSL2 host. No
  compile attempted; the `.exe` build is a Leg-4 CI forward dependency. `dist/` is
  absent on this host (expected — built by Leg 4 before `iscc`).
- Copied `.ico` confirmed byte-identical via `cmp` (identical) and `sha256sum` (match).
- No edits under `the_one/` from this leg — `git status the_one/` shows only the Leg 1/2
  changes; Leg 3 touched only `packaging/`. Installer is pure packaging.
- Host-native unit suite green (see results below).

**Deferred to Leg 4 (forward dependency, not a gate this leg):**

- The `iscc` build of `the-one-setup-*.exe` runs in Leg 4's `windows-2022` CI (Inno
  Setup ≥6.3 pinned), after the one-dir is built:
  `iscc /DAppVersion=<the_one.__version__> packaging\windows\the-one.iss`, uploading
  `packaging/windows/Output/the-one-setup-*.exe` as an artifact (see Decisions entry).

**Decisions/deviations:** none beyond the DECIDED design points. AppId GUID frozen at
`CAEEFB46-2698-4048-AD9F-0120D0B7174A`.

**Anomalies:** none.

**Acceptance criteria:** all locally-verifiable criteria met; the `iscc`-produces-`.exe`
milestone is recorded as the Leg-4 forward dependency.

### 2026-06-14 — Leg 4 (packaged-smoke-ci) → `landed`

**Changes made:**

- **`.github/workflows/test.yml`** — added a new `windows-packaged-smoke` job
  (`runs-on: windows-2022`, `defaults.run.shell: bash` for Git Bash). The
  existing `test`/`browser`/`windows`/`bwrap` jobs are **byte-unchanged** (the
  diff is purely additive — `git diff` shows no removed lines). Steps, in order:
  - **Path-filter** (`changes` step, mirrors the `browser` job's inline
    git-diff): `fetch-depth: 0` checkout; PR base = `pull_request.base.sha`,
    push base = `github.event.before`; missing/unreachable base → `run=true`
    (conservative). Regex filters `packaging/` + the seam files
    (`platform/env|interpreter|shell`, `mcp/transports/stdio`, `diagnostics`,
    `main`, `interfaces/app`) + the smoke's pass-criteria files
    (`interfaces/web/app`, `config`, `__init__`) + `pyproject.toml`. Every
    subsequent step is gated on `steps.changes.outputs.run == 'true'`.
  - **Install**: `pip install -e ".[gui,all-llms]"` then `pip install
    pyinstaller` (the `[gui]` extra is required — the existing `windows` job's
    `.[all-llms,dev]` omits it and the spec's pywebview collection would
    import-fail).
  - **Build**: `pyinstaller --noconfirm packaging/windows/the-one.spec` +
    `test -f dist/the-one/the-one.exe`.
  - **Proof (a) frozen doctor**: `set -eo pipefail`;
    `./dist/the-one/the-one.exe doctor | tee doctor.out`; grep both
    `child spawn: OK` and `RESULT: PASS` (the doctor's own exit code is the gate,
    `pipefail` keeps `tee` from masking it).
  - **Proof (b) frozen serve → /api/info**: background the frozen `serve`, poll
    with an `httpx` Python probe (not `curl`) for 200 + `version ==
    the_one.__version__`, 30s timeout.
  - **Proof (c) single-instance + teardown**: `python -c "... _select_port(...);
    assert ours ..."` (run from source, proving the decision input the second
    `app` launch keys on), then best-effort `taskkill //F //IM the-one.exe ||
    true`.
  - **Inno build (after the smoke)**: `choco install innosetup --version=6.3.3
    -y` (verified a real published chocolatey version, ≥6.3 for the
    `x64compatible` token); `VER=$(python -c "import the_one;
    print(the_one.__version__)")`; `iscc //DAppVersion=$VER
    packaging/windows/the-one.iss` (the `//D` MSYS double-slash escape is
    commented); `test -f packaging/windows/Output/the-one-setup-$VER.exe`.
  - **Upload**: `actions/upload-artifact@v4`, name `the-one-windows-installer`,
    path `packaging/windows/Output/*.exe`.
  - Matched the file's commenting culture — the backgrounding, the
    `taskkill`/best-effort teardown, the `//D` escape, the Divert-signal framing,
    and the "add a new seam file here" maintenance note are all inline-documented.
- **`packaging/windows/README.md`** — extended (Legs 1–3 work otherwise
  untouched) with a **CI packaged-smoke** subsection: what the job proves
  (the DD2 spawn fix on the real frozen binary, proofs a/b/c), how to read a
  failure (a red frozen-`doctor` step is the flight's **Divert** signal), the
  path-filter behavior, and the observed-green-run-on-PR honesty note.

**Verification (host-native — this leg authors CI YAML, its real proof runs on
the `windows-2022` runner post-push):**

- **YAML lint**: `actionlint` not installed on this host; the leg's fallback —
  `python -c "import yaml; yaml.safe_load(...)"` — parses clean, and the 5 jobs
  enumerate as `test`, `browser`, `windows`, `bwrap`, `windows-packaged-smoke`.
  Sanity-checked the `${{ }}` expressions, the `if: steps.changes.outputs.run ==
  'true'` gating on every post-filter step, and bash-`-n` syntax-checked the
  serve/teardown/path-filter run blocks (all OK). Verified the path-filter regex
  matches every intended path and rejects unrelated ones (e.g. `pyproject.toml`
  matches, `pyproject.toml.bak` does not — `$`-anchored).
- **Existing jobs unchanged**: `git diff .github/workflows/test.yml` shows zero
  removed lines (additive only).
- **No `the_one/` source edits** from this leg — it touched only
  `.github/workflows/test.yml`, `packaging/windows/README.md`, this flight-log,
  and the leg artifact's status. (The `the_one/` modifications in `git status`
  are all pre-existing Legs 1–3 work.)
- **Host-native unit suite green**: **3115 passed, 10 skipped, 589 deselected**
  (`-m 'not live and not browser and not pixel and not requires_bwrap and not
  discord_hat'`, `--timeout 60`), matching the post-Leg-1 baseline (no runtime
  code added). The aiosqlite "Event loop is closed" / forkpty
  DeprecationWarnings are the same pre-existing teardown noise noted in Leg 1.

**Forward-dependency closure:** this leg discharges the Leg-2 (build the frozen
one-dir) and Leg-3 (`iscc` build the installer) forward dependencies. The
**observed green run lands when this flight's PR opens** and CI executes on
`windows-2022` — GitHub Actions cannot run on this Linux host, so the design is
authored + statically validated here, not executed. A red frozen-`doctor` step
on the PR is the flight's central-risk Divert signal.

**Decisions/deviations:** none beyond the DECIDED design points. Confirmed the
Inno `6.3.3` chocolatey pin is a real published version (chocolatey OData feed:
6.3.0–6.3.3 published, latest 6.7.1) before committing to it.

**Anomalies:** none.

**Acceptance criteria:** all locally-verifiable criteria met; the
observed-green-run criterion is recorded as dependent on the PR's CI.

### 2026-06-14 — Flight review (Legs 1–4 batch) → `[HANDOFF:confirmed]`

Per the agentic-workflow batched model, a single Reviewer evaluated **all**
uncommitted changes (~1033 insertions across 18 files + new packaging/diagnostics/
tests) against the four legs' acceptance criteria, with no knowledge of the
developers' reasoning. **Model choice (Flight Director):** the crew file specifies the
Reviewer at Haiku for routine per-leg review; this batched review covers ~1000 lines
of **security-relevant subprocess-env / spawn-path** code, so the Reviewer was run on
**Sonnet** (the skill forbids only Opus for the Reviewer — Sonnet is permitted, and a
Haiku floor is a project default, not a ceiling). Recorded as a deliberate
Flight-Director judgment for an unusually critical batch.

**Outcome:** `[HANDOFF:confirmed]` — **no blocking issues.** Reviewer re-ran the suites:
68/68 targeted seam tests; **3115 passed / 10 skipped / 589 deselected** full default
suite; `py_compile` clean on the `.spec`/`frozen_entry`; YAML parse clean on the
workflow; `.iss` sound by inspection; host `the-one doctor` exits 0 with `child spawn:
OK` + `RESULT: PASS`. Independently verified the load-bearing items: the non-frozen
fast-path is a true no-op (`return env`, same object — tested `result is original`),
the allowlist invariant holds (no loader vars, no restore code), the MCP caller-side
re-strip preserves strip-always-wins, and `resolve_python()`'s frozen branch raises the
actionable `FrozenInterpreterError`. Two **non-blocking** observations (a redundant-but-
harmless freeze-order test whose real contract is covered by the adjacent exec-guard
test; the intentional two-name `python`/`python3` probe) — neither warrants a fix cycle.
No fix/re-review loop needed. Proceeding to commit + draft PR.

### 2026-06-14 — CI packaged-smoke closeout (PR #112)

The autonomous batch committed (`22da0f4`); draft PR #112 opened (base `flight/04`,
scoped to this flight). The `windows-2022` `windows-packaged-smoke` job — the
spawn-fix's only real proof — went green after **three CI-surfaced fixes**, each a
latent build issue that can only manifest on a real Windows freeze (exactly why DD5
made this CI the gate):

1. **`mcp.cli`/typer** (`a170f7b`): `collect_submodules("mcp")` imported mcp's optional
   CLI subpackage (needs `typer`/`mcp[cli]`, unused) → `ModuleNotFoundError` aborted the
   freeze. Fixed: `filter` out `mcp.cli` + `on_error="warn"`.
2. **Inno pre-installed** (`8e6449b`): `choco install innosetup --version=6.3.3` failed —
   the runner ships Inno 6.7.1 (≥6.3, `x64compatible`-capable), so choco refused the
   downgrade. Fixed: drop the pin, use the pre-installed `ISCC.exe`.
3. **Artifact quota** (`359e44e`): the installer `.exe` built fine but
   `actions/upload-artifact` hit the **account-level** storage quota (recalculates
   6–12h). Made the upload `continue-on-error` — the build + three proofs are the job's
   gates; the artifact is an optional-HAT convenience.

**Final green run (`359e44e`, run 27505987491):** freeze build ✓; frozen
`the-one doctor` exit 0 + `child spawn: OK` + `RESULT: PASS` ✓ (the DD2 spawn fix proven
on the *packaged* binary — `uv` correctly reported absent-but-advisory, not a gate);
frozen `serve` → `/api/info` 200 + version match ✓; single-instance probe ✓; Inno
installer `.exe` built ✓. Other lanes green: `test`, `windows`, `bwrap`, `lint`.
`browser` runs (the encoding fix touched `interfaces/web/app.py`) — an unrelated UI
regression net.

### 2026-06-14 — Leg 5 (docs-and-verify) → `completed` & flight `landed`

- **Tree-kill disposition (DD/Open-Q carry):** the `run_shell` Windows tree-kill is held
  **OUT** of Flight 5 (more than a one-liner; robustness gap, not a freeze blocker;
  Windows unsandboxed per DD9) → **carried to F7/maintenance**. Annotated on the mission
  Known Issue.
- **Docs:** confirmed `the-one doctor` (CLAUDE.md + README.md) and the Windows
  build/installer/SmartScreen/CI-smoke docs (`packaging/windows/README.md`) all landed
  across Legs 1–4. No gaps.
- **Verification gate:** host-native unit suite green (3115 passed); the `windows-2022`
  packaged-smoke green (the spawn-fix proof); `serve`/`chat`/`app`/`version` unchanged
  (Reviewer-confirmed + exercised by the frozen `serve` smoke).
- **Optional operator HAT:** **deferred to F9** (the comprehensive installer HAT). It is
  explicitly optional/early-preview; the CI artifact upload hit the account storage quota
  this run so the real `.exe` isn't downloadable from it, and per the M14 carried-forward
  operator preference (decide routine lifecycle calls with the sensible default) the
  early-preview HAT is deferred rather than gating the landing.
- Flight → `landed`; Flight 5 checked off in mission.md. `[COMPLETE:flight]`.

---

## Post-Landing

Items discovered/landed **after** the flight was marked `landed` — kept here as
append-only ground truth (the flight does not re-open; these inform F6/F7 and a future
debrief). The flight's `landed` status stands.

### 2026-06-15 — Operator HAT finding: stray console window on GUI launch (FIXED)

The deferred operator HAT (DD5 / F9) was effectively run early — the operator installed
the real `.exe` on a Windows box and launched it from the Start-menu shortcut. **Defect:**
a blank console window appeared alongside the app window.

- **Cause:** the single multi-call `the-one.exe` is a console-subsystem binary
  (`.spec` `console=True`, the DD6 pin). Windows always allocates a console window for
  such a binary, so even the windowed `app` path popped a stray `cmd` window. The CI/
  Concourse packaged-smoke never caught this — it exercises `the-one.exe doctor`/`serve`
  (where a console is wanted), not the *rendered-window* GUI launch (the apparatus DD5
  explicitly deferred).
- **Fix (commit `a4fce19`):** build **two exes** in the one-dir instead of one —
  `the-one.exe` (`console=True`, unchanged — the CLI + the smoke target) and a new
  **`the-one-app.exe`** (`console=False`, windowed) built from
  `packaging/windows/frozen_entry_gui.py` (forces the `app` path). `MERGE` de-dupes the
  shared native payload. The Inno shortcuts (Start-menu / Desktop / post-install launch)
  now point at `the-one-app.exe` (no params). This supersedes the DD6 "single multi-call
  exe / no second exe" pin; DD6's intent (CLI in the same bundle) is preserved — the CLI
  is still `the-one.exe` in the same install dir.
- **Trade-off:** bundle grew ~38 MB → ~56 MB (two PYZ bytecode archives; `MERGE` de-dupes
  binaries/data, not the per-exe pure-Python archive). Accepted. A leaner single-windowed-
  exe + parent-console re-attach (`AttachConsole`) is the alternative if size matters
  later — recorded for F6/F7, which inherit this `.spec` shape.
- **Verification:** rebuilt via the Concourse pipeline (below), build #3 — frozen
  `doctor` smoke still `RESULT: PASS` / `child spawn: OK` (the console `the-one.exe`
  intact), installer republished. Files touched: `packaging/windows/the-one.spec`,
  `packaging/windows/frozen_entry_gui.py` (new), `packaging/windows/the-one.iss`.
  **Operator re-test of the rendered window (no console) is the confirming step.**

### 2026-06-15 — Concourse pipeline-as-code for the Windows installer build

Standing infrastructure added so the installer rebuilds on push without the GitHub
Actions artifact-storage quota that blocked the F4-era CI upload (an account-level limit,
unrelated to this flight's code).

- **What:** `ci/windows-installer.pipeline.yml` + `ci/tasks/windows-installer-build.yml`
  — a pipeline in the project's dedicated **the-one Concourse team**. A `git` resource
  (read-only deploy key) polls the branch and auto-triggers; the build runs on a
  `platform: windows` worker (choco-provisions Python 3.11 + Inno Setup → PyInstaller
  freeze → frozen-`doctor` smoke gate → `iscc`); the `.exe` is published to a local
  **minio** (S3) bucket via an `mc` task.
- **Two environment gotchas solved (both reusable for F6/F7 if they go this route):**
  1. The Concourse `s3` resource **hangs** uploading to minio (aws-sdk path-style/checksum
     vs minio) — replaced with a native `mc cp` task.
  2. Concourse build containers use **external DNS (8.8.8.8)**, so the compose service
     name `minio` does not resolve inside them — `mc` must address minio by its
     compose-network **IP** (sourced from a Vault var; same pattern the `epipen`
     pipelines use). If `docker compose down/up` reassigns the IP, that Vault value needs
     updating.
- **Secrets** (deploy key, minio creds) live in Vault, not the repo. This is local-dev
  CI infrastructure; the pipeline is the build apparatus, not part of the shipped product.
- The fix→rebuild→publish loop is ~5–7 min end-to-end, which is how the console-window
  fix above was turned around quickly.

---

## Decisions

### iscc installer build consolidated into Leg 4's CI
**Context**: The flight.md Verification section parenthetically attributed the `iscc`
`.exe` build to "(Leg 5)", while Leg 4's flight description (the CI leg) enumerates only
the frozen-one-dir packaged-smoke and doesn't mention `iscc` — a cross-reference
ambiguity surfaced at Leg 3 design review.
**Decision**: Leg 4's `windows-2022` CI owns the `iscc` build — it already provisions
the Windows runner and builds the one-dir the installer consumes, so adding the
`iscc` step there avoids a second Windows job. Leg 4's CI pins **Inno Setup ≥6.3**
(so the `.iss`'s `x64compatible` arch token compiles) and runs
`iscc /DAppVersion=<the_one.__version__> packaging\windows\the-one.iss`, uploading
`packaging/windows/Output/the-one-setup-*.exe` as an artifact.
**Impact**: flight.md body left as its planning snapshot (it's `in-flight`/frozen);
this log entry is ground truth. Leg 4's design will explicitly include the Inno-install
+ `iscc` step. The Leg-3 artifact's forward-dependency text points at Leg 4 to match.

---

## Deviations

_(departures from the planned approach will be recorded here)_

---

## Anomalies

### 2026-06-14 — CI freeze failure: mcp.cli / typer optional-extra (Leg 2)

The `windows-packaged-smoke` CI job (PR #112) failed at the **Build frozen one-dir
(PyInstaller)** step with `ModuleNotFoundError: No module named 'typer'`. Root cause:
`packaging/windows/the-one.spec` called `collect_submodules("mcp")`, and PyInstaller's
isolated submodule walk recursively imported mcp's optional CLI subpackage
(`mcp.cli`), whose `__init__` imports `typer` (the `mcp[cli]` extra). `typer` is not
installed and the app does not use the mcp CLI, so the isolated collection subprocess
raised `ModuleNotFoundError` and aborted the whole `.spec`.

**Fix:** changed the call to
`collect_submodules("mcp", filter=lambda name: not name.startswith("mcp.cli"), on_error="warn")`.
The `filter` stops PyInstaller importing/recursing into `mcp.cli` (so `typer` is never
imported); `on_error="warn"` is a belt-and-suspenders so any other optional `mcp`
submodule that fails to import warns instead of aborting. Did **not** add
`typer`/`mcp[cli]` to project deps — the app doesn't use the mcp CLI and we don't want
it in the bundle. Spec-only change (and its comment). Verified by the CI re-run of the
`windows-packaged-smoke` job on PR #112.

### 2026-06-14 — CI Inno installer failure: version pin downgrade (Leg 4)

Second CI fix on PR #112: the **Build Inno installer** step failed because `windows-2022` already ships Inno Setup 6.7.1 and `choco install innosetup --version=6.3.3` refused the downgrade and exited 1. Fix: dropped the version pin (tolerant `choco install innosetup -y --no-progress || true`) and used the pre-installed compiler, locating `ISCC.exe` explicitly rather than assuming PATH. Workflow-only change.

### 2026-06-14 — CI installer-artifact upload: account artifact-storage quota (Leg 4)

The **Upload installer artifact** step (`actions/upload-artifact@v4`) failed on PR #112 with an account-level "Artifact storage quota has been hit" condition (recalculated every 6-12h) — not a code/workflow defect; the freeze build and all three packaged-smoke proofs (the job's gates) plus the Inno installer build all passed. Disposition: marked the upload step `continue-on-error: true` (best-effort) since the artifact is an operator-HAT convenience deferred to F9; build+smoke remain green and gate the job, and the upload still attempts (will succeed once quota frees up). Workflow-only change.

_(further unexpected issues will be recorded here)_

---

## Session Notes

### 2026-06-14 — Flight Director: execution started

- Loaded `/agentic-workflow` for Flight 5 (mission 15, the-one). Crew file
  `leg-execution.md` validated (Crew / Interaction Protocol / Prompts present, all
  prompts fenced). Branched `flight/05-packaging-installer-windows` off the
  flight/04 HEAD (Flight 5 depends on Flight 4's `the-one app` entry; flights 02–04
  are stacked, not yet merged to main — following the established stacked-branch
  pattern). Flight `ready` → `in-flight`.
- Plan: 4 autonomous legs (1 frozen-runtime-seam-and-doctor, 2 pyinstaller-windows-spec,
  3 inno-windows-installer, 4 packaged-smoke-ci) implemented without per-leg commit;
  single flight review + commit after Leg 4. Leg 5 (docs-and-verify + optional HAT)
  has an interactive component — handled operator-guided at flight close.

### Flight Director Notes

**Leg 1 design (frozen-runtime-seam-and-doctor).** Designed via `/leg` workflow.
Ran a dedicated read-only recon (Explore) of all touch points before authoring —
caught two flight-spec citation drifts (`select_shell`/`_kill_process_tree` live in
`platform/shell.py` not `tools/shell.py`; `build_stdio_environ` in
`mcp/transports/stdio.py:366-391` not `mcp/stdio.py:391`) and corrected them in the
leg. One design-review cycle (Developer): **approve with changes**, all spot-checked
citations verified `OK`, DD2 premise confirmed correct against real code. Incorporated
all medium/low items and resolved the reviewer's two open questions toward their own
recommendations: (1) MCP PATH-precedence → keep `build_stdio_environ` pure, export
`strip_bundle_dir_from_path` and re-apply at the caller (`stdio.py:430`) so the MCP
transport stays uncoupled from the freeze seam; (2) operator overrides
(`THE_ONE_EXTRA_PATH`/`THE_ONE_PYTHON`) read from raw `os.environ` to avoid a
`platform → config` import cycle. Also: noted the duplicate `_kill_process_tree`
(out of scope), pre-empted the `api.py:4534`/`app.py:135` encoding-grep
false-positives, flagged the `.env`-anchoring class-definition-time chicken-and-egg,
and scoped POSIX frozen-hardening as unit-test-only (not a Windows-smoke gate).
Changes were clarifications aligned with the reviewer's recommendations, not new
architecture → **no second review cycle** (per skill: re-review only on substantive
change). Leg 1 → `ready`. `[HANDOFF:review-needed]` (design finalized).

**Leg 2 design (pyinstaller-windows-spec).** Recon (Explore) of the post-Leg-1 tree
for packaging facts (pyproject extras/scripts/package-data, `__version__ = "0.2.0"`
vs stale pyproject `0.1.0`, the existing `windows-2022` job in `test.yml`, no
`freeze_support`/`.spec`/`packaging` dir). Designed the leg as **author + static-
validate the `.spec` locally, defer the real freeze build to Leg-4 CI** — PyInstaller
can't run on this Linux/WSL2 host (winpty/pywebview are Windows-native). One design-
review cycle (Developer): **approve with changes**, all citations verified `OK`, the
defer-split judged sound (not a hidden gap). Caught **two high-severity PyInstaller-
API build-breakers** and fixed both: (1) `EXE(version=)` needs a `VSVersionInfo`
resource, not a bare string → omit `version=`, use `__version__` for naming only;
(2) the existing `windows` job installs `.[all-llms,dev]` (no `[gui]`) so the
pywebview→pythonnet collection would import-fail → recorded an explicit Leg-4 forward
dependency to install `.[gui,all-llms]` + pyinstaller in the freeze job. Also: add
`winpty` to `hiddenimports` (collect_dynamic_libs grabs binaries only); standardize
the static glob to `interfaces/web/static/**/*`; `sys.path.insert` before the top-of-
spec version import; `excludes=['nacl']`; pinned the **single multi-call EXE** (DD6).
Fixes adopt the reviewer's recommendations (corrections, not new architecture) →
**no second review cycle**. Leg 2 → `ready`. `[HANDOFF:review-needed]`.

**Leg 3 design (inno-windows-installer).** Direct recon: `favicon.ico` (6977 bytes,
16/32/48) is the only `.ico`; Leg-2 spec set no `EXE(icon=)`. Designed the Inno `.iss`
with the same author-locally / build-in-Leg-4-CI defer-split as Leg 2 (`iscc` is
Windows-only). One design-review cycle (Developer): **approve with changes**, all Inno
directives + the `..\..\dist\the-one\*` source path + the `the-one.exe app` shortcut +
the `#ifndef`/`/D` version override verified correct. Resolved: (1) the iscc-owner
cross-reference conflict → consolidated into Leg 4 (logged under Decisions); (2) the
arch-token AC-vs-guidance contradiction → standardized on `x64compatible` with Leg 4
pinning Inno ≥6.3; (3) `UninstallDisplayIcon` → `{app}\the-one.ico` (branded); (4)
added the GleepGlorp-AI-display / the-one-slug callout; (5) anchored `OutputDir=Output`
to `packaging/windows/Output/` for Leg 4's artifact glob. Icon adequacy (no 256px)
confirmed fine for an unsigned installer; copying to `installer-assets/the-one.ico`
keeps the installer out of the app's live static tree. Fixes adopt reviewer
recommendations → **no second review cycle**. Leg 3 → `ready`. `[HANDOFF:review-needed]`.

**Leg 4 design (packaged-smoke-ci).** The final autonomous leg + the flight's central
verification. Read the existing `test.yml` (4 jobs) and the single-instance mechanism
(`_select_port` GETs `/api/info`, matches `version`). Designed a new
`windows-packaged-smoke` job that builds the frozen one-dir, proves the spawn-fix
against the *packaged* binary (frozen `doctor`, `serve`→`/api/info`, single-instance),
and builds+uploads the Inno installer (absorbing the iscc build per the logged
Decision). Author-locally / observe-green-on-PR split (same honesty as Legs 2/3 — no
Windows runner here). One design-review cycle (Developer): **approve with changes**,
all citations verified (`_select_port` signature, `/api/info` version field, `doctor`
output, port 8484). Hardened the central-proof job against infra-flake (the reviewer's
core concern): (1) `httpx` Python poll instead of `curl` (kills the Git-Bash-curl
assumption, exercises the product's real polling path); (2) `taskkill //F //IM` teardown
instead of `kill` (unreliable on a native `.exe` under Git Bash); (3) tightened proof-c
wording — it proves the *decision input* (frozen instance advertises our-version
`/api/info`), with the frozen binary's own `_select_port` deferred to the F9 HAT;
(4) added `grep RESULT: PASS` to cover the frozen interpreter gate; (5) widened the
path-filter to the smoke's pass-criteria files (`__init__.py`/`config.py`/`web/app.py`);
(6) concrete Inno pin `6.3.3`. Fixes adopt reviewer recommendations → **no second
review cycle**. Leg 4 → `ready`. `[HANDOFF:review-needed]`.

---

### 2026-06-14 — Flight planned

- Split from the original single "Packaging & installers" flight into one packaging
  flight per OS (Windows-first); mission flight tail reshaped (release pipeline →
  Flight 8). Operator-confirmed scope (Windows-first) and verification (CI
  packaged-smoke on the Windows runner).
- Planning recon: PyInstaller one-dir confirmed; the `.spec` hidden-import contract
  sourced from PyInstaller official docs; six unencoded-I/O sites + the
  `resolve_python`/`sys.executable` frozen footgun confirmed against current code.
- Two design-review cycles (Architect). Cycle 1 corrected the load-bearing DD2
  premise: `_build_subprocess_env` builds children from a strict allowlist, so the
  loader-path vars (`LD_LIBRARY_PATH`/`DYLD_*`/`*_ORIG`) never leak — the only
  mutated allowlisted var is `PATH`, so the spawn-fix is scoped to PATH-cleaning
  (strip the `_MEIPASS`/bundle dir + augment), no dead restore-`_ORIG` code. Also
  added DD8 (`.env`-discovery anchoring), the `factory.py:104` encoding disposition,
  the MCP `build_stdio_environ` PATH-precedence flag, the `detect_runtimes()`
  factoring note, and `freeze_support()`. Cycle 2 confirmed the corrections and
  caught one stale phrase (now fixed). Spec is codebase-validated.
- Flight marked `ready` 2026-06-14.
