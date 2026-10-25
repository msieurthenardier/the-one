# Leg: macos-recipe

**Status**: in-flight
**Flight**: [macOS app](../flight.md)

## Objective
Turn Flight 1's macOS prototype into the product recipe:
- the `.app` is built from `packaging/product.toml` through `render.py`, with the unified app id and `min_os = 14.0`;
- it ships in a drag-to-Applications `.dmg`;
- a bundle audit runs;
- `macos-packages.yml`'s `full` and `lifecycle` modes build, check and upload it;
- `lifecycle` drives leg 4's dock behaviour on the runner through `lifecycle.sh`.

Everything is rehearsed by execution on Linux before leg 7 spends a dispatch.

## Context
- **Flight DDs:** DD8 (metadata, versions, Info.plist, the `.dmg`, signing, the audit; `min_os` is now **14.0**, by operator decision after leg 3), DD10 (the workflow, artifacts, budget), DD13 (the hosted verification layers, `lifecycle.sh`'s steps). DD5 and leg 3b: replacing the app while it runs crashes the old copy, so `lifecycle.sh`'s upgrade step **quits N first**, as the guide will say.
- **The apparatus is settled** (legs 3 and 3b):
  - Accessibility keystrokes, the quit Apple event, `open --env`, `lsappinfo front` and `screencapture` all work;
  - there is no local-network prompt for the product;
  - Cmd-Q is path T;
  - no test seam is needed (DD9).
- **Leg 4 is concurrent** (`the_one/interfaces/desktop/`). Its AC5 table names the log lines and state fields `lifecycle.sh` reads, which is why Phase B starts after leg 4 lands.
- **Linux must not change** (DD8): Linux's AppStream id becomes `app_id`, with the same value. Its rendered files must be byte-identical before and after.
- **The workflow's `on:` block is frozen** (it must equal `main`'s stub).

## Phases
- **Phase A** (can run beside leg 4; files are disjoint): `product.toml`, `render.py`, the Linux templates' key rename, the macOS spec and Info.plist, `build.sh`'s CLI, the `.dmg`, `audit.py`, unit tests, the Linux no-change proof.
- **Phase B** (after leg 4 lands): the workflow's `full`/`lifecycle` modes, `lifecycle.sh`, `checks.sh` updates, and the rehearsal by execution.

## Outputs
### Phase A
- **`packaging/product.toml`:**
  - a top-level `app_id = "ai.gleepglorp.GleepGlorpAI"`;
  - `[linux] metainfo_id` removed;
  - a `[macos]` section: `bundle_name = "GleepGlorp AI"`, `bundle_executable = "the-one"`, `dmg_file_stem = "GleepGlorp_AI"`, `min_os = "14.0"`, `bundle_category = "public.app-category.productivity"`.
- **`packaging/render.py`:**
  - `load()` raises `RenderError` on a key repeated across sections, or between a section and the top level;
  - it derives `bundle_short_version` (the PEP 440 release triplet) and `bundle_version` (`major.minor.(patch × 10000 + n)`, with 9999 for a final release), refusing `a`/`b`/`rc`/`.postN` and a dev number of 9999 or more.
- **Linux:** `packaging/linux/{build.env.in,metainfo.xml.in}` and `build-inner.sh` read `@APP_ID@`/`$APP_ID` instead of `METAINFO_ID`.
- **`packaging/macos/the-one.spec`:** `build.sh` runs `render.py --repo "$REPO" --json --set version=$VERSION > "$WORK/product.json"`. (The staged copy holds only `the_one/` and the icon, so `--repo STAGE` would fail, and `--repo REPO` without `--set version` would read the tree's version.) It passes the file to the spec as `M32_PRODUCT_JSON`, like `M32_STAGE`/`M32_ICNS`.
  - The `BUNDLE` takes `name`, `bundle_identifier`, `version` and `info_plist` from it. The Info.plist dict comes from a small importable helper, `packaging/macos/info_plist.py` (a pure function of the render values), loaded through `sys.path.insert(0, SPECPATH)`.
  - The spec drops pystray: `pystray_hidden` **and** the `pystray._base`/`_darwin`/`_util` `hiddenimports` entries. That is safe because leg 5's darwin `desktop shell` gate checks Cocoa, not pystray.
  - The stale spec docstring is updated. `info_plist` holds:
  - `CFBundleName` and `CFBundleDisplayName`;
  - `CFBundleShortVersionString` and `CFBundleVersion`;
  - `LSMinimumSystemVersion` `14.0`;
  - `LSApplicationCategoryType`;
  - `NSHumanReadableCopyright` ("Copyright © GleepGlorp AI contributors. MIT License.");
  - `NSHighResolutionCapable`;
  - `LSAppNapIsDisabled`;
  - `NSAppTransportSecurity` `{NSAllowsLocalNetworking: true}`.
- **`packaging/macos/build.sh`:**
  - the CLI is `build.sh [--version X] [--from-head]` (positional `<version>` still accepted, with a warning, like Linux's);
  - it writes `build.env` (`VERSION`, `APP_ID`, `APP`, `DMG` paths);
  - `SOURCE_DATE_EPOCH` is set from the last commit;
  - **it no longer runs `checks.sh`:** the workflow owns the checks;
  - `M32_SKIP_DMG=1` skips the `.dmg` (the N+1 build and probe mode), and `M32_SKIP_CHECKS` stays as an alias that the probe-mode step still sets;
  - `M32_REUSE_VENV=1` keeps an existing build venv instead of `rm -rf` plus a full closure reinstall, so the N+1 build doesn't pay twice.
- **`packaging/macos/frozen_entry_mac.py`:** for the `app` command (a Finder or Dock launch, or a bare launch) when stderr is not a TTY, stdout and stderr are redirected to `~/Library/Logs/GleepGlorp AI/app.log` (created if needed; append, line-buffered; truncated at start if over 10 MB). `launch_args()` stays pure, and the redirect is a separate, unit-tested function.
  - **Why:** a Finder-launched app's output goes nowhere today, so contributors would have no log to send back, and `lifecycle.sh` needs one stable place to read the drain lines.
  - The guide (leg 7) names the file.
- **The `.dmg`:** staged in a folder with the `.app` plus an `Applications` → `/Applications` symlink; `hdiutil create -volname "GleepGlorp AI" -fs HFS+ -format UDZO` (HFS+ is conventional for UDZO and fine on macOS 15); the file is `GleepGlorp_AI-<version>-arm64.dmg`; one bounded retry. Ad-hoc signing (`codesign --force --deep -s -`) happens before the `.dmg`. The inert notarization hook stays a comment.
- **`packaging/macos/audit.py`** (new, stdlib, unit-tested on canned `otool`/`lipo` output). It walks the `.app` and runs `otool -arch arm64 -L` and `otool -arch arm64 -l` on every Mach-O. It fails on:
  - a load path outside `/System/`, `/usr/lib/`, `@rpath/`, `@loader_path/` or `@executable_path/`;
  - **a Mach-O with no arm64 slice.** Universal2 files (pyobjc, Pillow, cryptography) are fat, so they are listed in the summary but do not fail;
  - an `LC_BUILD_VERSION` minos above `--min-os`, which comes from `product.json` (14.0). A file with no `LC_BUILD_VERSION` (an older `LC_VERSION_MIN_MACOSX`) reads it from that command, or is reported "unknown" without failing.

  It prints a summary (files, fat files, max minos, problems). It exits 1 on any problem, unless `--report-only` is given. **The first hosted run uses `--report-only`,** so a false positive can't burn a dispatch; leg 7 flips it to enforcing once a real bundle's report is clean.
- **Tests:**
  - `tests/test_packaging_metadata.py`: `app_id`, the collisions, the version mapping against PEP 440 order, the refusals, the `[macos]` keys;
  - `tests/test_packaging_macos_audit.py`: canned `otool`/`lipo` outputs, pass and each failure kind;
  - `info_plist.py`: the keys are exactly the list above, and the values come from the render values;
  - `render.py`: collisions between sections and with the top level, the derived keys, and an **N+1 helper** (`render.py --next-version V`, or a function the workflow calls). A dev version gets its dev number plus one; a final version gets the next patch's `.dev1` (so `0.11.8` → `0.11.9.dev1`, `CFBundleVersion` `0.11.90001` > `0.11.89999`). The output round-trips through `render.py` and sorts above N;
  - `tests/test_packaging_metadata.py`: `REQUIRED` drops `metainfo_id` and gains `app_id`;
  - the `frozen_entry_mac.py` log redirect (a TTY means no redirect; a non-TTY means the file is used; the truncation; a failure falls back to the current streams).
- **Linux no-change proof:** `git archive e21d219 packaging/` into a scratch dir and render with the old `render.py` and old `product.toml`; render this tree's with the new ones; both with `--set version=… --set release_date=…`. Diff `build.env`, `metainfo.xml`, both `.desktop` files, `AppRun` and `control`. The only allowed difference is the `build.env` key rename (`METAINFO_ID` → `APP_ID`), whose value is identical. Record the diff.

### Phase B
- **Phase B starts from leg 4's AC5 table,** quoted in this leg's flight-log section: the exact log line text and the `/api/window/state` fields (`visible`, `tray`, `pid`, `version`, `mode`) per lifecycle step.
- **`.github/workflows/macos-packages.yml`** (the `on:` block untouched):
  - **`full`:**
    1. build N (`build.sh --version` from the input or `__version__`);
    2. `checks.sh`, run as its own step (`!cancelled()`): strict `doctor` with explicit greps for `desktop shell: OK — Cocoa backend present`, `tray: dock` and a `path:` line; gate 2; serve; gate 4; the signature; the audit (`--report-only` on the first hosted run); the `.dmg` layout;
    3. upload the `.dmg` as an artifact (7 days) and the logs.
  - **`lifecycle`:** `full`, then an N+1 build (`M32_REUSE_VENV=1 M32_SKIP_DMG=1`, version from the N+1 helper), then `lifecycle.sh`, under a global bound of about 20 min so it writes its summary before the job timeout. `lifecycle.sh` **runs even when `checks.sh` had failures,** as long as the `.app` exists (dispatches are scarce).
  - **`probe`:** keeps working with the new `build.sh` CLI and passes the **new** bundle id to `probe.sh` (from `build.env`/`product.json`, not hard-coded).
  - **The Summary step and the final check** cover `A/SUMMARY.txt` and `lifecycle/SUMMARY.txt`. The final check matches anchored `^FAIL`, so evidence text that contains "FAIL" never trips it, and lifecycle mode fails if the lifecycle summary is missing.
  - `checks.sh`'s old best-effort `open` block is removed (`lifecycle.sh` supersedes it).
  - **The `.dmg` layout check:** `hdiutil attach -readonly -nobrowse -noverify -noautoopen -mountpoint DIR` (bounded); assert `GleepGlorp AI.app` exists, and that `Applications` is a symlink whose `readlink` is `/Applications`; detach in a trap, with one `-force` retry.
  - Timeouts sized from Flight 1's and the probe runs' measures; the job timeout stays 50 min.
- **`packaging/macos/lifecycle.sh`** (new). It drives DD13's steps against the installed N in `/Applications`, then N+1. Each step writes a `SUMMARY.txt` row of PASS or FAIL, with evidence:
  1. **Launch** (`open -a "/Applications/GleepGlorp AI.app"`), with the first-paint screenshot series at +1, +3, +5 s; `/api/window/state` `visible: true`, `tray: "dock"`.
  2. **Close:** System Events `click button 1 of window 1 of (first process whose unix id is <pid>)` (AXPress on the close button: no coordinates). Expect `visible: false`, the pid alive, `/api/live` 200. A Cmd-W row is informational only (it did nothing on the probe app).
  3. **Reopen** (`open -a`): `visible: true`, the same pid, and `lsappinfo front` is the app.
  4. **Second process** (`open -n`): the frontmost app is GleepGlorp AI; there's no second listener; the second pid exits.
  5. **Geometry:** read the screen size first, and choose a target frame that fits it (the runner's display is likely about 1024×768). Set it with System Events (`set position`/`set size` of window 1 of the pid's process), read the AX frame back, Cmd-Q, relaunch, and read the AX frame again. Compare AX against AX: size ±2, position within a clamp tolerance. Separately assert only that `window-state.json` exists and changed from the default. System Events' frame includes the title bar, and pywebview's may not, so the two are never compared.
  6. **Quit Apple event** (`tell application id "ai.gleepglorp.GleepGlorpAI"`, sent only after asserting that just the `/Applications` copy is running; the build-dir copies are never launched): the log shows terminate received, the drain started and done, and reply sending; the process exits within 70 s; `/api/live` is refused; no new crash report. **Crash reports:** list `~/Library/Logs/DiagnosticReports/*the-one*.ips` (and `Retired/`) before and after, with a few seconds' settle after each quit.
  7. **`the-one quit --wait`:** the same drain lines, exit 0.
  8. **Cmd-Q keystroke:** path T lines as in step 6.
  9. **Upgrade:** seed data through the API. That's verified to work without dev mode: `POST /api/providers` `{name, type: "ollama", base_url}` (no URL validation), `POST /api/agents` `{name, …}`, `POST /api/chat/sessions` `{agent_name, title}`. Then quit, replace the `.app` with N+1 (remove, then `ditto`), and launch. The version from **`/api/info`** is N+1 (the plist's short version is the same for both), and the seeded rows are present. The credential's `loc_<id>` prefix is unchanged; the credential already existed before the first launch, created by `checks.sh` gate 4, which is recorded.
  10. **Trash:** quit, remove the `.app`; the data dir still holds the database and `api-credential`.

  Rules:
  - **Logs:** read from `~/Library/Logs/GleepGlorp AI/app.log` (the entry shim's redirect), by byte offset per step.
  - **Apps are addressed by path** (`open -a "/Applications/GleepGlorp AI.app"`), and System Events targets `first process whose unix id is <pid>` (the process name may be `the-one`).
  - **The port and data dir are parameters** (`M32_PRODUCT_PORT`, default 8484; the default data dir on the runner), so the Linux rehearsal's fake app never uses 8484/8485.
  - **Helpers** `tl`, `track`, `stop_pid`, `runrc`, `wait_exit` and `window_state` are reused from `probe.sh` (factor them into `packaging/macos/lib.sh` and source it from both), not rewritten.
  - Every external call is bounded (`tl`).
  - Pids are tracked from `/api/window/state`'s `pid` and stopped only by that pid.
  - The log lines read are exactly leg 4's AC5 table.
  - Each step quits cleanly before the next unless the step is a quit.
- **Rehearsal by execution on Linux** (the leg 2 kit, extended): `lifecycle.sh` against a fake app (a small Python server answering `/api/live`, `/api/window/state`, `/api/info` and the quit route, writing the drain log lines) plus shims for `open`, `osascript`, `lsappinfo`, `screencapture`, `ditto`, `hdiutil`, `codesign`, `otool`, `lipo`. Three scenarios:
  - all pass;
  - one step's expectation fails (the summary shows FAIL and the script continues);
  - an `osascript` hang (the bound fires);
  - `open -n` returns a second listening pid (step 4 FAIL);
  - the drain log lines are missing (step 6 FAIL).

  Also: `shellcheck`, bash 3.2 `-n`, `actionlint`, and the workflow's steps extracted and run against a fake `RUNNER_TEMP`.

## Acceptance Criteria
- [ ] **AC1 (A):** the metadata, render, Linux key rename, spec, `build.sh` and `.dmg` changes as listed. Unit tests pass, `make test-unit` passes with 12 skips, ruff is clean.
- [ ] **AC2 (A):** the Linux no-change proof is recorded, with only the allowed difference. A Linux `.deb` and AppImage build (`M32_BUILD=$HOME/the-one-m32-build/f3 packaging/linux/build.sh --version 0.11.9.dev31`) succeeds and its audit passes.
- [ ] **AC3 (A):** `audit.py` and its tests; the spec's PyInstaller Analysis still runs on Linux against the build venv.
- [ ] **AC4 (B):** the workflow's `full`/`lifecycle` modes and `lifecycle.sh` as listed. `actionlint` and `shellcheck` are clean, and the `on:` block equals the stub.
- [ ] **AC5 (B):** the three rehearsal scenarios run and are recorded. The worst-case wall time of `lifecycle` mode is estimated, and it fits the 50 min job.
- [ ] **AC6:** hygiene: no 8484/8485 on this host, the operator data dir unchanged, only recorded pids killed, only `m32-*` containers (none left), no root-owned files left.

## Files Affected
- `packaging/{product.toml,render.py}`, `packaging/linux/{build.env.in,metainfo.xml.in,build-inner.sh}`
- `packaging/macos/{the-one.spec,build.sh,checks.sh,README.md,frozen_entry_mac.py,audit.py (new),info_plist.py (new),lifecycle.sh (new),lib.sh (new)}`, `packaging/macos/probe/probe.sh` (sources `lib.sh`)
- `packaging/macos/README.md` (the bundle id, `LSMinimumSystemVersion` 14.0, the `build.sh` CLI, the log file)
- `.github/workflows/macos-packages.yml`
- tests: `tests/test_packaging_metadata.py`, new `tests/test_packaging_macos_audit.py` (and the spec test)

### Citation Audit
Checked at `c2db6f1`:
- `render.py::load` flattens sections with `values.update`, and `render.py::render` with its `RESERVED` names;
- `METAINFO_ID` users: `packaging/linux/build.env.in:9`, `build-inner.sh:136,152`, `metainfo.xml.in:3`, `tests/test_packaging_metadata.py:53`;
- the macOS spec's `M32_STAGE`/`M32_ICNS` and `APP_VERSION` from the staged copy;
- `build.sh`'s hdiutil `-srcfolder "$APP"` and `M32_SKIP_CHECKS`.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
