# Leg: macos-probe-prepare

**Status**: completed
**Flight**: [Choose the packaging toolchain](../flight.md)

## Objective
Prepare everything the hosted macOS probe needs so that its first run is likely to succeed. That means candidate A's macOS spec, candidate B's macOS configuration and patch extension, the dispatch-only workflow, and a Windows stub workflow for the PR to `main`. Rehearse every part that can run on Linux, so the two-job budget is not spent discovering avoidable mistakes.

## Context
- **Flight decisions:** DD6 (one dispatched `macos-15` job building every surviving candidate; at most 2 macOS jobs in the flight; ad-hoc signing; `doctor` and `serve` proven on the runner, not the window; the paper items), DD2 (strict gates), DD3 (staging and the pinned closure), DD4 (staged patches only). Read them before starting.
- **Both candidates survived Linux** (the Evidence Table): A's `.deb`, and B's `.deb` with patches 01 and 02. So the macOS probe builds both.
- **This leg is the first half of a split** (Flight Director). This leg prepares and rehearses, autonomously. Then the Flight Director, with the operator's go:
  1. commits and pushes the flight branch;
  2. opens the `.github/`-only PR to `main` with the two workflow files from this leg;
  3. merges it once `pr-lint` passes;
  4. dispatches the run with `gh workflow run packaging-probe-macos.yml --ref flight/01-choose-packaging-toolchain`.

  Leg 5 (`macos-probe-run`) reads the run's results. **This leg never pushes, opens a PR, or dispatches.**
- **Cost:** the repo is private, and each macOS minute is billed at 10×. The workflow must cap itself with job `timeout-minutes`, and must not upload bundles; only logs, listings and `doctor` outputs.
- **Candidate A on macOS:**
  - PyInstaller's `BUNDLE` produces `GleepGlorp AI.app`.
  - Reuse `packaging/linux/the-one.spec`'s collection contract, which reads the staged copy (`M32_STAGE`), and its `gi.overrides` lesson in the opposite direction: on macOS there is no gi or GTK. pywebview uses its Cocoa backend (pyobjc: `webview.platforms.cocoa` and the five locked `pyobjc-*` packages), and pystray uses `pystray._darwin`.
  - `excludes.txt` and `rthook_host_gtk.py` are Linux-only and must not be used.
  - The `.app`'s main executable is the CLI and accepts the same subcommands (`Contents/MacOS/the-one doctor`).
  - The Finder launch of the `.app` (no arguments) would start the terminal `chat`, not the window. For A, set the bundle's launch to run `app` through PyInstaller's `argv` handling or a tiny GUI entry, as `packaging/windows/frozen_entry_gui.py` does. That is recipe upkeep, not an app patch. Record which.
  - An `.icns` icon generated from `icon-512.png` (Pillow can write ICNS; `iconutil` exists on the runner).
  - `Info.plist`: `CFBundleName`/`CFBundleDisplayName` "GleepGlorp AI", `CFBundleIdentifier` `ai.gleepglorp.the-one`, the staged version, and `NSHighResolutionCapable`.
- **Candidate B on macOS:**
  - `briefcase create/build/package macOS app --adhoc-sign` (pinned 0.4.6), from the same staging.
  - Briefcase's macOS app ships its own Python support package, so the app's `sys.executable` is the app binary (`…/Contents/MacOS/GleepGlorp AI`), and `app_packages` sits under `Contents/Resources/`.
  - Patch 02's marker is Linux-specific (`<prefix>/lib/<name>/app_packages` beside the launcher). **Extend it additively for the macOS layout** (for example, `sys.executable`'s `../Resources/app_packages` exists), leaving the Linux clause byte-identical, so the Linux evidence stays valid. `_bundle_dir()` for the macOS Briefcase layout must return the `Contents/MacOS` directory (it is a bundle there, unlike `/usr/bin`). Log the reasoning.
  - Patch 01 (bare start opens the window) applies unchanged.
  - The macOS config section needs no system requirements. Keep `allow_subprocesses = true`, `--no-deps --require-hashes`, and the same exported closure; the export carries macOS wheel hashes, and the planning audit found every macOS dependency has an arm64 or universal2 wheel except pure-Python `proxy-tools`.
  - If Briefcase's macOS `requires` handling or Python version (its support package's Python, likely not 3.11) differs from Linux, log it.
- **The workflow** `.github/workflows/packaging-probe-macos.yml`:
  - `on: workflow_dispatch` only, with one input, `candidates` (default `A B`).
  - One job on `macos-15`, `timeout-minutes: 45`, `permissions: contents: read`.
  - Steps:
    1. checkout;
    2. print the runner, the Xcode `python3` and the arch;
    3. `actions/setup-python` 3.11;
    4. pinned `uv`; `uv export` with the same arguments as Linux, into a requirements file;
    5. for each candidate in `candidates`, a step with `continue-on-error: true` (so A failing does not lose B's data) that stages, builds, ad-hoc signs (`codesign --force --deep -s -`; Briefcase does this with `--adhoc-sign`), makes a `.dmg` with `hdiutil create` (A only, cheap evidence; B's `package` makes its own), then runs the checks below, teeing everything to a log;
    6. a final step uploading the logs directory as one artifact (`retention-days: 7`), and nothing else.
  - **The checks, per candidate:**
    - `codesign -dv` on the `.app`;
    - the bundle size and a top-level listing;
    - `the-one version`;
    - `doctor`, scored by `packaging/spike/score.py`. It is the same strict rule. `PYSTRAY_BACKEND` is irrelevant on darwin, so the unpinned run is the only run, and window chrome's "skipped (not Windows)" is the only allowed skip;
    - gate 2: the resolved interpreter run with `-c 'import sys; print(sys.executable, sys.prefix)'`, where the expected answer is the `setup-python` toolcache or another system Python, never the bundle;
    - `serve`, on port 8490 with a scratch `THE_ONE_DATA_DIR` under `$RUNNER_TEMP`, polled at `GET /api/live` (no credential needed), then stopped by PID;
    - a data-dir probe, `rotate-api-credential` with no override, showing a path under `~/Library/Application Support/the-one/`. The runner is disposable, so no override is needed; the operator's machine is never involved.
  - No secrets are used.
  - Nothing is published.
- **`.github/workflows/packaging-probe-windows.yml` (stub):** `on: workflow_dispatch`, one job on `windows-2022` that only echoes that leg `windows-cost` will fill it on the flight branch. It exists so the single PR to `main` makes both workflows dispatchable (DD6, DD7).
- **The paper items** go in the flight log under `macos-probe-prepare`, each with a code citation:
  - `/usr/bin/python3` on a fresh Mac is the Xcode command-line-tools stub, and `interpreter.py::_is_store_alias` has no macOS equivalent;
  - a Finder-launched `.app` gets launchd's minimal `PATH`, which `env.py::_common_runtime_dirs` partly covers (`/opt/homebrew/bin`, `/usr/local/bin`) but not NVM or fnm;
  - `DesktopSession` has no darwin lifecycle (no Dock reopen, Cmd-Q or close-keeps-running);
  - `_webview_available` returns `True` on darwin without probing.
- **The Linux rehearsal** proves everything Linux can before any minute is spent:
  - `actionlint` (pinned binary, checksum logged) and a YAML parse on both workflows;
  - `bash -n` on every script the workflow calls;
  - `python -m py_compile` on the macOS spec;
  - `stage.py --candidate briefcase` with the extended patch 02 applied cleanly, and the staged `env.py` imported and exercised by a short throwaway test under a faked macOS layout (a temp dir shaped like `X.app/Contents/{MacOS,Resources/app_packages}`, with `sys.executable` monkeypatched). That test is spike verification kept under `packaging/briefcase/` (or run inline and logged), not added to `tests/`;
  - a check that the Linux clause of patch 02 is unchanged (diff the old and new patch's Linux hunk);
  - a dry listing of the exact commands the workflow will run, per candidate.

- **Findings from the leg design review (folded in; these override anything above that conflicts):**
  1. **B's macOS build would fail on `proxy-tools`.** Briefcase sets `require_binary_installs = True` for macOS and passes `--only-binary :all:` with `--platform <macosx tag>`. `proxy-tools` (a pywebview dependency on every platform) is sdist-only. Add `"--no-binary", "proxy-tools"` to the macOS section's `requirement_installer_args` only; the Linux args stay as they are.
     - Prove it in the rehearsal (item 2).
     - If pip refuses it, the fallback is a pure-Python wheel of `proxy-tools` built on Linux and passed with `--find-links`. Its hash differs from the sdist's, so drop `proxy-tools` from the hashed closure file for macOS only, install it unhashed, and log the deviation.
  2. **Rehearse B's macOS pip resolution on Linux**, with no runner minutes: `pip download --dest <scratch> --platform macosx_<V>_arm64 --python-version <B's support Python> --only-binary :all: --no-binary proxy-tools --no-deps --require-hashes -r closure.txt`, at V = `11_0`, `12_0` and `14_0`. Also at `--python-version 3.11` for A's sake, though A installs natively on the runner.
     - A wheel tagged only for a newer macOS (usearch, numkong, pyobjc, watchfiles or similar) fails at the lower tags.
     - Set `min_os_version` explicitly in B's macOS section to the lowest V at which the whole closure resolves, and log the per-tag result.
  3. **The cost guard is layered:**
     - job `timeout-minutes: 30`;
     - each candidate step `timeout-minutes: 15`;
     - a `concurrency:` group with `cancel-in-progress: false`;
     - the `candidates` input is a `type: choice` with the options `A B`, `A` and `B`;
     - inside the scripts, `doctor`, `serve` start-up and `hdiutil` are wrapped in a time limit (`perl -e 'alarm N; exec @ARGV' --`, since macOS has no GNU `timeout`);
     - `serve` runs in the background with `trap 'kill $PID' EXIT`.
  4. **A's Finder launch: one entry script.** `packaging/macos/frozen_entry_mac.py` calls `freeze_support()`. If `sys.argv[1:]`, ignoring any `-psn_*`, is empty, it appends `app`, then calls `cli_entry()`. So `Contents/MacOS/the-one doctor|serve|version` still work.
     - Do not use a forced-`app` GUI exe as the bundle's main executable, since that would break the checks.
     - Use `console=False`, with `ensure_stdio_streams()` as the Windows GUI entry does.
     - This is recipe upkeep, not an app patch.
  5. **Scoring on macOS.** Reuse only `score.py`'s `score_doctor`; its `main()` is Linux-specific. `macos-checks.sh` appends `rc=$?` after `doctor`, as `inner.sh` does, and calls `score_doctor` through `python -c`. Gate 2 is checked in `macos-checks.sh`: the resolved interpreter's `sys.executable` and `sys.prefix` must contain neither `.app/` nor `Contents`. The expected location is the runner's toolcache or `/usr/bin`/`/Library/Frameworks`.
  6. **B's executable name has a space** (`Contents/MacOS/GleepGlorp AI`). Quote it everywhere: the scripts, the workflow and every probe. Add a `shellcheck` pass, if available, besides `bash -n`.
  7. **Briefcase on macOS:** use `--no-input` on every command. The runner has no `.venv`, so `pip install pillow` into the tool venv for icon generation. Supply `icon.icns`, plus PNG sizes if Briefcase wants them.
  8. **Patch 02's macOS clause** matches only when `exe.parent.name == "MacOS"` and `exe.parent.parent / "Resources" / "app_packages"` is a directory. `_bundle_dir()` returns `None` for it, as for Linux: nothing prepends `Contents/MacOS` to `PATH`, so `None` is equally correct and lower risk. This supersedes Context's "return the `Contents/MacOS` directory". The faked-layout check asserts that a child process's `PATH` is unchanged.
  9. **B's macOS stub behaviour is from memory**, unconfirmed by the review: `sys.executable` is the stub, `app_packages` is under `Contents/Resources/`, and argv is forwarded. So `macos-checks.sh` prints `sys.executable`, `sys.frozen` and `sys.prefix` from inside B's app first, before the other checks, so leg 5 can confirm or refute them.
  10. **Evidence on the runner:** print `sw_vers`, `uname -m`, `pip --version`, `uv --version` and `/usr/bin/python3 --version` first. Check the signature with `codesign --verify --deep --strict -vv` as well as `codesign -dv`, logging both exit codes. Retry `hdiutil create` once.
  11. **The Windows stub** declares the same `workflow_dispatch` input names it will need in `windows-cost` (at least `candidates`), so a dispatch against the flight branch validates against what `main` declares.
- **The budget:** the GitHub billing API is not readable with this `gh` token (no `user` scope). The Flight Director asks the operator to confirm remaining minutes before dispatch.

## Inputs
- Legs 1-3's harness and recipes (`packaging/spike/`, `packaging/linux/`, `packaging/briefcase/`), the Evidence Table, and the review checkpoint's fixes (if any) applied.
- `gh` authenticated (re-verify with `gh auth status`; read only).

## Outputs
- `packaging/macos/`: `the-one.spec` (A's `BUNDLE`), any GUI entry for A, `build.sh` (A's macOS build, run on the runner), the icon generation, and `README.md` (spike prototype; pinned tools).
- `packaging/briefcase/`: a `[tool.briefcase.app.the-one.macOS]` section in `pyproject.toml.in`; patch 02 extended for the macOS layout (the Linux clause unchanged); `build.sh` gains a macOS mode or a sibling `build-macos.sh`.
- `.github/workflows/packaging-probe-macos.yml` (complete) and `.github/workflows/packaging-probe-windows.yml` (stub).
- The flight log: a `### macos-probe-prepare` entry with the rehearsal results and the paper items.

## Acceptance Criteria
- [ ] **AC1 — Workflows are dispatch-only, capped, and publish nothing.**
  - Both files have `on: workflow_dispatch` as their only trigger, with matching input names, and `candidates` as a `choice`.
  - The macOS job pins `runs-on: macos-15`, with a job `timeout-minutes` of 40 or less (the Flight Director raised it from 30 after the review because the worst-case estimate of about 36 minutes sat at the cap), a `timeout-minutes` of 15 or less on each candidate step, and a `concurrency:` group. The scripts time-limit `doctor`, `serve` and `hdiutil`.
  - Permissions are read-only.
  - The only upload is a logs artifact with `retention-days` of 7 or less.
  - No secrets are referenced.
  - `actionlint` reports no errors on both.
- [ ] **AC2 — A's macOS recipe.** `packaging/macos/the-one.spec` builds a `BUNDLE` named `GleepGlorp AI.app` from the staged copy (never the repo root), with the Info.plist keys and the `.icns` named in Context, the Cocoa/pyobjc and `pystray._darwin` hidden imports, and no Linux-only hook or exclude. A Finder launch runs `app`. It passes `py_compile`, and every macOS-only line has a comment saying why.
- [ ] **AC3 — B's macOS recipe.**
  - The macOS config section exists, and patch 02 recognises the Briefcase macOS layout with `_bundle_dir()` returning `Contents/MacOS` there.
  - The patch's Linux clause is byte-identical to the version leg 3 measured (shown by a diff of the hunks).
  - The faked-layout check passes for macOS (frozen true, `_bundle_dir()` returning `None`, a child `PATH` unchanged), Linux (as before), and a plain source install (frozen false), including a macOS-shaped path whose parent is not `MacOS` (frozen false).
  - The macOS section carries `--no-binary proxy-tools` (or the logged fallback) and an explicit `min_os_version` from the rehearsal.
- [ ] **AC4 — The rehearsal.** The flight log records the output of: the macOS `pip download` resolution per tag (finding 2), and per Python for B and A; `shellcheck` (if available); `actionlint`; the YAML parse; `bash -n` on every called script; `py_compile`; `stage.py --candidate briefcase` with all patches applying; the faked-layout check; and the per-candidate command listing.
- [ ] **AC5 — The paper items** are written in the flight log with citations (Context).
- [ ] **AC6 — Nothing outward-facing happened.** No push, no PR, no `gh workflow run`. `git status` shows changes only under `packaging/`, `.github/workflows/` (the two new files) and `missions/`. `ruff check packaging/` and `ruff format --check packaging/` pass.

## Verification Steps
- AC1: `grep -n -A3 '^on:' .github/workflows/packaging-probe-*.yml`; the pinned `actionlint` output; `grep -n 'timeout-minutes\|runs-on\|permissions\|upload-artifact\|retention-days\|secrets\.' …`.
- AC2: `python -m py_compile packaging/macos/the-one.spec`; reading the spec.
- AC3: `diff` of the Linux hunk between the old patch (from `git show HEAD:…`, or the review-checkpoint commit) and the new one; the check's output.
- AC4-AC5: the flight-log entry.
- AC6: `git status --porcelain`; the ruff commands; the shell history shows no `git push`, `gh pr` or `gh workflow run`.

## Implementation Guidance
1. Re-read the flight log's legs 1-3 entries and the review-checkpoint outcome. Run `gh auth status` (read only).
2. Write A's macOS spec and `build.sh`. Mirror the Linux spec's contract: the staged path from `M32_STAGE`, and a pinned PyInstaller (the same version as Linux, 6.22.3, unless it lacks a needed fix; log it).
3. Extend B: the config section, the patch 02 macOS clause, and the macOS build script (`briefcase create macOS app`, `build`, `package --adhoc-sign`, writing the logs).
4. Write the macOS workflow so that each candidate is one script invocation: `packaging/macos/build.sh` for A, `packaging/briefcase/build-macos.sh` for B, plus a shared `packaging/spike/macos-checks.sh` that runs the checks against an `.app` path. The YAML stays thin, and the scripts are rehearsable with `bash -n`.
5. Write the Windows stub workflow.
6. Run the rehearsal (AC4) and write the paper items (AC5). Update the flight log and set the leg to `landed`.

## Edge Cases
- **`hdiutil` or `codesign` behaviour differs on `macos-15`**: keep each in its own command with its exit code logged, and never let it abort the candidate's later checks (`|| echo "…rc=$?"`).
- **The runner image's Python 3.11 lacks a needed universal2 or arm64 wheel**: the audit says no. If the build step fails on a wheel, the log must show the package name. Make pip's output verbose enough to show it.
- **`doctor`'s file-watcher round trip or embedding gate behaves differently on macOS (FSEvents)**: nothing to do here. Leg 5 scores it.
- **Briefcase's macOS app needs a different `requires` form**: keep the hashed file if it works on Linux. If the macOS support package's Python version has no wheel for a pin, the run will show it. Do not pre-emptively loosen pins.

## Files Affected
- `packaging/macos/` (new), `packaging/briefcase/` (config, patch 02, the macOS build script), and `packaging/spike/macos-checks.sh` (new).
- `.github/workflows/packaging-probe-macos.yml` and `.github/workflows/packaging-probe-windows.yml` (new; these two files are also the content of the PR to `main`).
- The flight log.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked on 2026-10-23:
- `packaging/briefcase/patches/02-briefcase-counts-as-frozen.diff`: the Linux marker is `(exe.parent.parent / "lib" / exe.name / "app_packages").is_dir()`, and `_bundle_dir()` returns `None` for it.
- `packaging/briefcase/pyproject.toml.in`: `allow_subprocesses = true`, `requirement_installer_args = ["--no-deps", "--require-hashes"]`, and the Linux system sections.
- `packaging/windows/frozen_entry_gui.py` exists (the windowed-entry pattern for A's Finder launch).
- `the_one/platform/interpreter.py::_is_store_alias` (Windows only), `env.py::_common_runtime_dirs` (POSIX list), and `shell.py::_webview_available` (darwin returns `True`), all cited in the flight's Citation Audit.
