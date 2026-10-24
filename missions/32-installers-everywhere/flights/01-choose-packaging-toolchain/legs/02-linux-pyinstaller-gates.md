# Leg: linux-pyinstaller-gates

**Status**: completed
**Flight**: [Choose the packaging toolchain](../flight.md)

## Objective
Measure candidate A's four Linux packages (from leg 1) against every DD2 hard gate and soft criterion in fresh Ubuntu 26.04 and Debian 13 containers, and record the result as the flight log's Evidence Table, which leg 3 (`linux-briefcase`) extends.

## Context
- **The second half of the split.** Leg 1 (`linux-pyinstaller-build`) built the packages and the container images. Read its flight-log entry first: package paths, image tags, image contents, and anything it could not exclude.
- **Flight decisions:** DD2 (the gates, strictly defined) and DD5 (apparatus, pinned backends, upgrade, safety). Read them before starting.
- **Leg 1's findings that shape this leg** (from its flight-log entry):
  - Neither stock baseline has the Ayatana AppIndicator typelib.
  - Debian 13's baseline also lacks `libgirepository-2.0-0`, which the bundled PyGObject 3.56 needs at runtime, so the AppImage may fail outright on Debian's stock desktop. That is a real result; record it.
  - The bundle no longer carries `libstdc++`/`libgcc_s` (the `.deb` depends on them).
  - On the build host, `doctor` passed with `PYSTRAY_BACKEND=gtk PYWEBVIEW_GUI=gtk` and failed unpinned.
  - `M32_DEBUG_ENV=1` makes the runtime hook print its environment.
  - The operator's default data dir is `/home/cprch/.local/share/the-one`.
- **The pinned tray backend is `gtk`, not `appindicator`** (Flight Director call, after leg 1). A pin to `appindicator` fails on every stock baseline and measures nothing. `PYSTRAY_BACKEND=gtk` measures whether the rest of the desktop shell loads, and the unpinned run measures what a user gets. Read "pinned" below as `PYSTRAY_BACKEND=gtk`.
- **The tray, decided by measurement, not by choice:**
  - The `baseline` image is whatever the distro's desktop metapackage installs (leg 1, AC2).
  - The AppImage cannot declare a dependency, so its unpinned `doctor` result on `baseline` is the truth for a stock desktop. If the Ayatana typelib is absent, `import pystray` raises `ValueError` and the frozen desktop-shell gate fails. That is scored FAIL, with the note "needs the host's AppIndicator typelib".
  - The `.deb`'s declared dependencies are proven on the `bare` image, where `apt` has to pull every one of them.
- **Doctor output format** (`the_one/diagnostics.py::run_doctor`):
  - each gate prints as `  <name>: OK — <detail>` or `FAIL — …`;
  - the interpreter gate reads `python interpreter: OK — resolved to <path>`;
  - the advisory runtimes print indented under a `runtimes:` heading.
  - PyInstaller sets `sys.frozen`, so the frozen-only gates are exercised.
- **Single-instance mechanics** (`the_one/interfaces/desktop/shell.py`, `run()` with `_select_port`):
  - A second `the-one app` reads `/api/info` on the configured port. If the port belongs to the same version with the same credential, it `POST`s `/api/window/focus` and returns. It logs nothing on success.
  - Both launches must share `THE_ONE_PORT` and `THE_ONE_DATA_DIR`.
  - `/api/window/focus` answers `{"focused": true}` only when the first instance is `the-one app` with a registered window.
- **The container window, a Flight Director call:**
  - The window runs under `dbus-run-session`, with `GDK_BACKEND=x11`, `PYWEBVIEW_GUI=gtk` and `DISPLAY=:0`, and `/mnt/wslg/.X11-unix` mounted at `/tmp/.X11-unix`.
  - Docker blocks the user namespaces WebKit's own sandbox needs. So the container window runs set `WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1` (and `WEBKIT_DISABLE_COMPOSITING_MODE=1` if there is no `/dev/dri`), and record both in the evidence. WebKit's sandbox on a real desktop is Flight 2's check.
  - Never use `--privileged` or `--network host` (host networking would put the container on the dev host's ports).
- **Safety (CLAUDE.md):**
  - every app instance uses a port of 8490 or higher and a scratch `THE_ONE_DATA_DIR`, except gate 4, which runs with no override, inside a container only;
  - nothing runs on 8484 or 8485;
  - the operator's default data dir (path recorded in leg 1) is never used;
  - kill only PIDs you recorded, or whole containers you started.

## Inputs
- Leg 1's four packages under `$M32_BUILD`, and its images `m32/ubuntu-26.04:{bare,baseline}` and `m32/debian-13:{bare,baseline}`.
- Leg 1's flight-log entry.

## Outputs
- `packaging/spike/`:
  - `check.sh` (or `check.py`), the candidate-neutral gate runner: one container session per package × image, writing evidence under `$M32_EVIDENCE/<candidate>/<format>/<distro>/`;
  - `score.py`, which scores the `doctor` output and the `/proc/<pid>/maps` evidence mechanically;
  - the README updated.
- The flight log: a `### linux-pyinstaller-gates` entry, and a new `## Evidence Table` section (after Leg Progress, before Decision) with A's rows and an upkeep paragraph.

## Acceptance Criteria
- [ ] **AC1 — Gate 1, mechanically scored.**
  - For each format × distro on `baseline`, plus the `.deb` on `bare`, the evidence holds the full `doctor` output of the installed or extracted N+1 build: once with `PYSTRAY_BACKEND=gtk`, once with it unset.
  - `score.py` marks a run PASS only if the exit code is 0 and no gate line's detail contains `skipped`, other than `window chrome: OK — skipped (not Windows)`. Lines under `runtimes:` are excluded.
  - The table shows both runs.
- [ ] **AC2 — Gate 2.**
  - For each format × distro, the `resolved to <path>` interpreter is run as `<path> -c 'import sys; print(sys.executable, sys.prefix)'`. The output shows a system Python outside the bundle and the AppImage mount.
  - The system Python version of each distro is recorded.
- [ ] **AC3 — Gate 3.**
  - For each distro, with `the-one app` open (in the container if the forwarded display works, otherwise the DD5 fallback on the dev host, marked directional):
    - the UI process's `/proc/<pid>/maps` has exactly one mapped copy each of `libglib-2.0`, `libgobject-2.0`, `libgtk-3`, `libgirepository-2.0`, `libwebkit2gtk-4.1`, `libstdc++` and `libgcc_s`, all under `/usr/lib` (or `/lib`, which is the same directory on merged-usr distros);
    - every `WebKitWebProcess` has at most one copy of each, all under `/usr/lib`;
    - `score.py` counts these from the maps evidence.
  - A screenshot of the window is saved under `$M32_EVIDENCE`, and its path is logged.
  - A format that fails is scored FAIL with the evidence and goes no further, except that its gate 1 and gate 2 results are still recorded.
- [ ] **AC4 — Gate 4.** In a container with no `THE_ONE_DATA_DIR` set, before seeding anything:
  - `the-one rotate-api-credential` prints `Local API credential created at <path>`, with the path under `~/.local/share/the-one/`;
  - `serve` starts on a port of 8490 or higher;
  - `ls ~/.local/share/the-one/` shows the database and the credential file.
- [ ] **AC5 — The upgrade, in one container session per format × distro.**
  1. Install N (`apt install ./…_0.11.8_amd64.deb`, or place the N AppImage). `the-one version` contains `v0.11.8`.
  2. Start `serve`, seed one agent through the API, and record the credential's `loc_<id>` prefix only, never the secret.
  3. Stop N by PID.
  4. Install N+1 (`apt install ./…_0.11.9~dev1_amd64.deb`, or replace the AppImage file). `the-one version` contains `v0.11.9.dev1`.
  5. Start `serve` again. The seeded agent reads back, and the credential prefix is unchanged.

  Each step's output is in the evidence.
- [ ] **AC6 — Single-instance, when the window works.**
  - Start `the-one app` with a fixed `THE_ONE_PORT` (8490 or higher) and a scratch `THE_ONE_DATA_DIR`. Wait for the window.
  - Start a second `the-one app` with the same two values.
  - The second exits with code 0 within 10 seconds.
  - A process listing shows one server.
  - `curl -X POST /api/window/focus` with the bearer credential returns `{"focused": true}`.
  - If the window does not work in the container, this is scored N/A, or directional under the fallback.
- [ ] **AC7 — The remaining soft criteria.** A's rows and upkeep paragraph record:
  - **tray:** whether the pinned backend and the Ayatana typelib are present and load inside the bundle, per format × distro (a visible icon is not scored);
  - **sizes:** the bundle, the AppImage and the `.deb` (from leg 1's outputs), and the cold build time (from leg 1's log);
  - **upkeep:** the files and lines under `packaging/linux/`, the places the version and name live, one `.deb` serving both distros, and the CLI arrangement;
  - **sandbox:** what `doctor` or a tool call reports for `bwrap` inside the container, noted as not representative of a desktop.
- [ ] **AC8 — The Evidence Table exists.**
  - `## Evidence Table` has one row per candidate × format × distro (plus the `.deb` on `bare`).
  - Its columns are: G1 pinned, G1 unpinned, G2, G3, G4, upgrade, single-instance, tray, sandbox, size, notes.
  - Every cell is PASS, FAIL, N/A or directional, with a pointer to its evidence file.
  - The table carries a legend and the environment variables that every run set.
- [ ] **AC9 — Safety and the forbidden paths.**
  - The flight log states that no instance ran on 8484 or 8485, that every host-side instance used a scratch data dir, and that no container used `--privileged` or `--network host`.
  - The newest mtime under the operator's default data dir is the same before and after the leg.
  - `git diff --stat mission/32-installers` shows changes only under `packaging/` and `missions/`.
  - `ruff check` and `ruff format --check` on `packaging/` pass.

## Verification Steps
- AC1-AC6: the gate runner's evidence files, plus `score.py`'s summary output pasted into the log.
- AC7-AC8: the Evidence Table section.
- AC9: the log's safety statement; `find <default data dir> -printf '%T@\n' | sort -n | tail -1` before and after; `git diff --stat mission/32-installers`; `ruff check packaging/ && ruff format --check packaging/`.

## Implementation Guidance

1. **Re-verify the environment.** Check the Docker daemon, that the leg 1 images (`docker image ls 'm32/*'`) and packages (`$HOME/the-one-m32-build/packages/` with its `SHA256SUMS`) exist, and that the WSLg socket is at `/mnt/wslg/.X11-unix/X0`. Record the default data dir's newest mtime.
2. **Probe the forwarded display first.** Run a throwaway container from `m32/ubuntu-26.04:baseline` with the display flags (Context), and run `xdpyinfo` or a GTK hello-world. If it fails under Docker Desktop, switch to the DD5 fallback for AC3 and AC6:
   - extract the AppImage (`--appimage-extract`), or unpack the `.deb` (`dpkg-deb -x`), under `$M32_BUILD`;
   - run it on the dev host's WSLg, with a scratch data dir, a port of 8490 or higher, and a scratch cwd;
   - mark the results directional (24.04 host). Log which path was used.
3. **Write the gate runner.**
   - One container session per (package, image).
   - Run as a non-root user with a real `HOME`.
   - The order: install or extract; gate 4 (no override); `doctor` pinned and unpinned; gate 2; the upgrade (N then N+1; AC5 needs the N package too, so install N first and treat N+1 as the upgrade); the window, maps, screenshot and single-instance checks under the display flags, with a scratch data dir.
   - Everything goes to the evidence directory.
   - Use `docker run --rm` with `--name m32-<…>`, and stop only containers you named.
4. **Write `score.py`**, stdlib only: parse the `doctor` output per AC1, and the maps files per AC3, and emit one summary line per run.
5. **Run the matrix:**
   - AppImage on `baseline` × 2 distros;
   - `.deb` on `baseline` × 2 distros;
   - `.deb` on `bare` × 2 distros (gate 1, gate 2 and installability only; no window on `bare`).
6. **Fill the Evidence Table and the upkeep paragraph.** Run the AC9 checks, update the flight log, and set the leg to `landed`.

## Edge Cases
- **`apt install ./x.deb` on `bare` fails on an unresolvable `Depends`**: that is a FAIL of the `.deb`'s declaration. Log the missing name. If the fix is a dependency-name correction, apply it in `packaging/linux/` and rebuild through leg 1's `build.sh`, then log the change.
- **The AppImage's runtime needs FUSE, which containers lack**: run it with `--appimage-extract-and-run` (or `APPIMAGE_EXTRACT_AND_RUN=1`), and log that a real desktop runs it through FUSE (Flight 2's check).
- **`WebKitWebProcess` crashes in the container even with the sandbox disabled**: capture its stderr and the maps of the UI process. Score gate 3 from the UI process, and mark the web-process half "not measured — crash", with the evidence. Only a crash caused by a bundled library (visible in the maps or stderr) is a FAIL.
- **The second `the-one app` hangs instead of exiting**: kill it by its recorded PID after 10 seconds, score FAIL, and keep its output.
- **The model catalog seed or the embedding gate reads `skipped` in a container**: that is a FAIL per DD2. Check leg 1's spec collected the data before deciding whether it is a recipe defect (fix in `packaging/linux/`, rebuild) or a candidate limitation.

## Files Affected
- `packaging/spike/check.sh` (or `check.py`), `packaging/spike/score.py`, `packaging/spike/README.md`.
- `packaging/linux/` only for dependency-name or collection fixes found by the gates (each logged).
- `missions/32-installers-everywhere/flights/01-choose-packaging-toolchain/flight-log.md`.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked against the worktree at `4892b1f` on 2026-10-23, and by the leg design review:
- `the_one/diagnostics.py`: gate lines are `  <name>: OK|FAIL — <detail>`; the interpreter gate prints `resolved to <path>`; the not-frozen downgrades read `skipped (…)`/`skipped — …`; window chrome reads `skipped (not Windows)` (diagnostics.py:159, 227, 280, 977).
- `the_one/interfaces/desktop/shell.py`, `run()` (~L556-575): a second launch uses `_select_port`, then `POST /api/window/focus`, with no success log; `focus_window` returns `focused: true` only with a registered window.
- `the-one rotate-api-credential` prints `Local API credential created at <path> (mode 0600).`
