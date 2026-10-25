# packaging/macos - PyInstaller on macOS

**The macOS recipe (Mission 32 Flight 3). Ad-hoc signed; publishes nothing.** Everything product-shaped (names, id, versions,
minimum macOS) is read from `../product.toml` through `../render.py`.
It freezes GleepGlorp AI with PyInstaller on Python 3.11 into `GleepGlorp AI.app` and a `.dmg`.
It is built and checked by the dispatch-only workflow `.github/workflows/macos-packages.yml`
on a hosted `macos-15` (Apple Silicon) runner; it has never run on the operator's machine.

## Files

- `the-one.spec`: the collection contract of `../linux/the-one.spec` (itself from
  `../windows/the-one.spec`), minus the Linux parts, plus a `BUNDLE`. Reads the staged copy from
  `$M32_STAGE` (never the repo root). On macOS there is no gi or GTK: pywebview uses its Cocoa
  backend (`webview.platforms.cocoa`, the locked `pyobjc-*` packages) and there is no tray (the app
  lives in the Dock), so pystray is not collected. `BUNDLE` takes its name, identifier and versions from
  `$M32_PRODUCT_JSON` (`render.py --json`, written by `build.sh`). `excludes.txt` and `rthook_host_gtk.py` are Linux-only and are not used.
- `frozen_entry_mac.py`: the entry. `Contents/MacOS/the-one doctor|serve|version` still runs the CLI;
  a Finder/Dock launch passes no arguments (or only `-psn_*`), and the entry then appends `app`, so a
  double-click opens the window instead of the terminal `chat`. Recipe upkeep, not an app patch (DD4).
  When the `app` command starts without a terminal (Finder, Dock, `open`), stdout and stderr go to
  `~/Library/Logs/GleepGlorp AI/app.log` (append, line-buffered, truncated at start if over 10 MB).
  It calls `ensure_stdio_streams()` first, as the Windows GUI entry does, because the windowed
  bootloader (`console=False`) can leave `sys.stdout` as None.
- `info_plist.py`: the `Info.plist` dict as a pure function of the render values (unit-tested).
- `audit.py`: walks the built `.app`; every Mach-O must have an arm64 slice, link only to `/System/`,
  `/usr/lib/`, `@rpath/`, `@loader_path/` or `@executable_path/`, and have `minos` no higher than
  `min_os`. `audit.py APP --product-json product.json [--report-only]`.
- `checks.sh LABEL APP EXE LOGDIR` (its own workflow step; `M32_DMG`, `M32_PRODUCT_JSON`, `M32_AUDIT_ARGS`):
  `version`, strict `doctor` (the score, plus exact greps for `desktop shell: OK — Cocoa backend present`,
  `tray: dock` and a `path:` line), the interpreter doctor resolved, `serve` on a scratch port,
  `rotate-api-credential` against the default data dir (this is what creates the credential before
  `lifecycle.sh`'s first launch), the signature, the bundle audit (enforcing since dispatch 4; `M32_AUDIT_ARGS=--report-only`
  is the unset default) and the `.dmg` layout (`hdiutil attach -readonly -nobrowse
  -noverify -noautoopen -mountpoint`, then `GleepGlorp AI.app` and `Applications` -> `/Applications`;
  detached in a trap, `-force` on a retry). The window is not touched here.
- `lifecycle.sh APP_N APP_N1 APP_ID VERSION_N VERSION_N1 OUT_DIR`: the dock behaviour on the runner's
  GUI session (below). `lib.sh` holds the helpers it shares with `probe/probe.sh` (`tl`, `track`,
  `stop_pid`, `runrc`, `wait_exit`, `window_state`, ...).
- `make-icns.py`: writes the `.icns` from the staged 512 px icon with Pillow.
- `build.sh [--version X] [--from-head]` (a positional version still works, with a warning): render
  `product.json`, stage, venv, hash-pinned closure install (`--require-hashes --no-deps`), pinned
  PyInstaller, freeze, `codesign --force --deep -s -`, then the `.dmg` (the `.app` beside an
  `Applications` symlink, `hdiutil create -fs HFS+ -format UDZO`, one retry, 300 s limit). It writes
  `macos-<version>/build.env` (`VERSION`, `APP_ID`, `APP`, `DMG`; source it) and does **not** run
  `checks.sh`: the workflow does. `M32_SKIP_DMG=1` (alias `M32_SKIP_CHECKS=1`) skips the `.dmg`;
  `M32_REUSE_VENV=1` keeps an existing build venv. `SOURCE_DATE_EPOCH` is the last commit's.
  `../render.py --next-version V` prints the next dev version (the upgrade rehearsal's N+1).

## Pinned tools

| tool | version |
|---|---|
| PyInstaller | 6.22.3 (same as Linux) |
| pyinstaller-hooks-contrib | 2026.8 (same as Linux) |
| Python | 3.11 (`actions/setup-python`) |
| uv (closure export) | 0.10.0 |

## Notes

- `Info.plist`: `CFBundleName`/`CFBundleDisplayName` "GleepGlorp AI", `CFBundleIdentifier`
  `ai.gleepglorp.GleepGlorpAI` (`app_id`, shared with Linux's AppStream id),
  `CFBundleShortVersionString` (the release triplet), `CFBundleVersion` (`major.minor.(patch*10000+n)`,
  n = the dev number, 9999 for a final release), `LSMinimumSystemVersion` 14.0 (the bundled numpy's
  arm64 extensions need macOS 14), `LSApplicationCategoryType`, `NSHumanReadableCopyright`,
  `NSHighResolutionCapable`, `LSAppNapIsDisabled`, `NSAppTransportSecurity` local networking.
- The executable is `Contents/MacOS/the-one` (the `.app` folder carries the display name).
- Bare `the-one` typed in a shell now opens the window (the entry cannot tell a shell from Finder),
  unlike Linux's `.deb`, where bare `the-one` is the terminal chat.
- Linux rehearsal: `py_compile`, and the spec runs through Analysis against a staged copy on Linux
  (its `BUNDLE` is a no-op there). The macOS-only parts are first exercised by the hosted run.

## Probe mode

`.github/workflows/macos-packages.yml` with `-f mode=probe` builds this app with `M32_SKIP_CHECKS=1` (skips
the `.dmg`; the workflow runs `checks.sh` separately, and probe mode does not, so the default data dir and credential do not exist before the first-launch premise), freezes the
minimal probe app and runs `probe/probe.sh`. See `probe/README.md`.

## Full and lifecycle modes

`-f mode=full` builds N (`build.sh --version`), runs `checks.sh` as its own `!cancelled()` step and uploads the
`.dmg` (artifact `macos-dmg`, 7 days) and the logs (`macos-packages-logs`). `-f mode=lifecycle` adds the N+1
build (`render.py --next-version`, `M32_REUSE_VENV=1 M32_SKIP_DMG=1`, logs under `logs/n1/`) and `lifecycle.sh`,
which runs even when `checks.sh` failed, as long as both `.app` bundles exist. The job reads red when a line of
`A/SUMMARY.txt` or `lifecycle/SUMMARY.txt` starts with `FAIL` (anchored: evidence text that says "FAIL" never
trips it), when a build step failed, or when the lifecycle summary is missing in lifecycle mode.

`lifecycle.sh` installs N in `/Applications` the way a user does (attaches the N `.dmg` read-only, `ditto`s the `.app` out of the volume, detaches; `M32_DMG_N`; without a `.dmg` it copies from the build dir and the L0 row says so; N+1 has no `.dmg`, so L9 copies it from the build dir), checks that the crash-report directories are readable (an unreadable one is `FAIL LCRASH`), then runs ten steps, each as a child under its own cap and
each writing one `PASS`/`FAIL` row with its evidence (a step that finds no app running starts one and says so).
It reads leg 4's observables: the log `~/Library/Logs/GleepGlorp AI/app.log` by byte offset per step, and
`GET /api/window/state` (`visible`, `tray`, `pid`, `version`, `mode`).

| step | does | asserts | cap (s) |
|---|---|---|---|
| L1 | `open -a` the installed app; screenshots at +1, +3, +5 s | `macos dock: delegate installed (route=subclass, ...)` first; `macos: main window shown after page load` (the "fallback (page not loaded)" line fails the step); (waited up to 35 s from the launch mark: a cold start can spend the 15 s server wait plus the 12 s fallback); `visible: true`, `tray: "dock"`, version N, pid is a process under the install path | 110 |
| L2 | System Events `click button 1 of window 1` of the process by pid | `visible: false`, pid alive, `/api/live` 200, `dock: window hidden on close` | 50 |
| L3 | `open -a` again; then Cmd-W (information only) | `visible: true`, same pid, `lsappinfo front` is the app, `reopen: decision=show` | 70 |
| L4 | `open -n -a` | frontmost is the app, one listener (the first pid), the second process (if seen) exits | 50 |
| L5 | resize through System Events, Cmd-Q, relaunch | `window-state.json` written and changed; System Events frame vs System Events frame: size +-2 px, position +-40 px | 200 |
| L6 | `tell application id "<APP_ID>" to quit`, after asserting no build-directory copy runs | received, drain started, drain done, reply sending (in order); exits within 70 s; `/api/live` refused; no new `.ips` | 130 |
| L7 | `the-one quit --wait` | the same lines, exit 0 | 120 |
| L8 | Cmd-Q keystroke | the same lines | 130 |
| L9 | seed a provider, agent and chat; quit; remove and `ditto` N+1; launch | `/api/info` version N+1, seeded rows present, credential `loc_<id>` prefix unchanged | 190 |
| L10 | quit; remove the app | `the-one.db` and `api-credential` still there | 70 |

The driver skips a step once `M32_BUDGET` seconds have passed (`FAIL Ln skipped`; default 850; the workflow
passes the step's bound minus 200 s). No step's cap exceeds 200 s, so a step that starts runs out before the
bound. The port is `M32_PRODUCT_PORT` (default 8484) and the data directory `M32_DATA_DIR` (default the user's),
so the Linux rehearsal never touches 8484/8485.

**Time budget (60-minute job).** Typical about 15 min (setup and N build with `.dmg` 3, checks 3, N+1 build 1,
lifecycle 5-8, uploads 1). The caps are layered: the job is 60 min; the step caps before lifecycle are checkout 2,
paths 1, runner evidence 2, setup-python 3, versions 1, export 5, build 12, checks 10, N+1 build 6 (42 min in all);
after it, Summary 1, log upload 3, `.dmg` upload 2 and the final check 1 (7 min). The Paths step records
`M32_T0`; the Lifecycle step computes `B = 3600 - elapsed - 420`, caps it at 1200 s, and if `B < 300` writes
`FAIL L0 no time left` and skips. Otherwise it runs lifecycle.sh under a `B` second bound with
`M32_BUDGET=B-200`. Worst case, every pre-lifecycle step at its cap: 42 min used, `B = 660 s`, lifecycle ends by
53 min, and 7 min remain for Summary, uploads and the final check; with more time left the reserve is larger,
never smaller than 7 min. The step's own `timeout-minutes` is 21, above the 1200 s maximum bound. A step that
hits its cap is already a failed run whose logs the `always()` steps upload.
