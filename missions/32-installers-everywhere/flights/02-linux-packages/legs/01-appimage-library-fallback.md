# Leg: appimage-library-fallback

**Status**: completed
**Flight**: [Linux packages](../flight.md)

## Objective
Build both Linux packages inside one pinned build container (DD2), and give the AppImage a host-first fallback for `libgirepository-2.0` and the Ayatana AppIndicator stack (DD1). Prove that the fallback actually works against both target hosts' newer GLib: strict `doctor` passes unpinned, and amended gate 3 passes, for the AppImage on the stock Ubuntu 26.04 and Debian 13 containers, with the `.deb` still passing everything. This leg is the flight's divert point.

## Context
- **Flight DDs:** DD1 (the fallback: where it lives, host first by soname, best effort, never `LD_LIBRARY_PATH`, amended gate 3, the ABI premise), DD2 (the pinned `ubuntu:24.04` container, the same locally and hosted). DD11 (the `doctor` desktop-shell split) is leg 2, not here.
- **Flight 1 ground truth** (the Flight 1 flight log's `linux-pyinstaller-build` and `linux-pyinstaller-gates` entries, and the Evidence Table):
  - The AppImage fails unpinned gate 1 on the Ubuntu 26.04 baseline: `desktop shell: unexpected error: Namespace AyatanaAppIndicator3 not available`.
  - On the Debian 13 baseline it fails gate 1 pinned, gate 3 and single-instance: `libgirepository-2.0.so.0` is missing, so `gi` cannot load and no window opens.
  - The `.deb` passes everything on both distros.
  - The dev host (Ubuntu 24.04, GLib 2.80) gives no gi hook output, so the exclude list is valid for a GLib 2.80 build host. The pinned container is meant to match that host for the freeze. To keep it that way, the Ayatana fallback packages are **extracted** into a staging directory (`apt-get download` + `dpkg -x`), never installed system-wide, so PyInstaller's gi hooks and pystray see the same environment as Flight 1's host. `libgirepository-2.0-0` itself is installed system-wide, as it was on the dev host (PyGObject compiles against `libgirepository-2.0-dev`). AC2b checks the result.
  - `collect_submodules("gi.overrides")` is required, or no window opens.
  - The window check forwards WSLg's X socket into the container.
- **What each baseline has**, measured by `ldconfig -p` and typelib listings in design review cycle 1:

  | Image | Has | Lacks |
  |---|---|---|
  | Ubuntu 26.04 baseline (GLib 2.88) | every fallback `.so` (`libgirepository-2.0`, the Ayatana libraries, dbusmenu, ido) | only `AyatanaAppIndicator3-0.1.typelib`. Flight 1's `Namespace AyatanaAppIndicator3 not available` is a missing typelib, not a missing library. |
  | Debian 13 baseline (GLib 2.84) | `libdbusmenu-glib`, `libdbusmenu-gtk3`, `libffi8`, GTK | `libgirepository-2.0`, `libayatana-appindicator3`, `libayatana-indicator3`, `libayatana-ido3`, the typelib. This is the partially satisfied chain, and the main case. |
  | Both bare images | `libffi8` | everything else (no GTK) |

- **The fallback closure** (ubuntu:24.04, measured): exactly six sonames:
  - `libgirepository-2.0.so.0`;
  - `libayatana-appindicator3.so.1`, `libayatana-indicator3.so.7`, `libayatana-ido3-0.4.so.0`;
  - `libdbusmenu-gtk3.so.4`, `libdbusmenu-glib.so.4`.

  Every other `NEEDED` is glibc, `libffi.so.8` (present on all targets) or an `excludes.txt` family. `ldd -r` of the 24.04 `libgirepository-2.0` against Debian's 2.84 and Ubuntu's 2.88 GLib shows no undefined symbols. Bind-time ABI is fine; using it is still the real test (AC4).
- **PyInstaller 6.22.3 facts:**
  - The Linux bootloader sets `LD_LIBRARY_PATH` (bundle first) for the frozen process itself.
  - Its ctypes hook wraps only `CDLL`/`PyDLL` on Linux, falling back to `_MEIPASS/<basename>` when that file exists there.
  - `find_library` is stock on Linux.
  - Load errors are `PyInstallerImportError`, an `OSError` subclass.

  So `ctypes.CDLL(soname)` searches `_internal` and then the system, which is correct as long as `_internal` never holds these libraries (AC2).
- **The AppImage runtime** mounts at `/tmp/.mount_XXXXXX`, extracts to `…/appimage_extracted_…` under extract-and-run, and exports `APPDIR`, `APPIMAGE` and `ARGV0`.
- **What this leg does not do:**
  - the metadata source and templates (leg 7);
  - folding `packaging/spike/` (leg 8), so this leg still uses `packaging/spike/{stage.py,check.sh,inner.sh,score.py}` in place and edits them where needed;
  - the bundle audit (leg 8);
  - the hosted workflow (leg 9).

  The build still takes the version as an argument.
- **Git worktree caveat:** this checkout is a git worktree whose `.git` file points into `/home/cprch/projects/the-one/.git/worktrees/…`, which is Mission 31's checkout. Never mount or touch that path. So `stage.py` (which runs `git rev-parse`) and `uv export` run on the host, outside the container. The container receives the staged copy, the closure file and `packaging/` only. This deliberately replaces DD2's `safe.directory` note: record it in the flight log as a deviation. On the GitHub runner, staging runs on the runner the same way (leg 9).

## Inputs
- `packaging/linux/{the-one.spec,rthook_host_gtk.py,excludes.txt,build.sh,AppRun,control.in,gleepglorp-ai.desktop.in}` (Flight 1's prototype)
- `packaging/spike/` harness
- Flight 1's container images `m32/{ubuntu-26.04,debian-13}:{baseline,bare}` (present)
- Pinned tool versions and sha256s in `packaging/linux/README.md`. That table is the source of truth the Dockerfile verifies downloads against; the `$HOME/the-one-m32-build/tools/` copies are not used by the container build.
- Host `uv` (0.10.0, only for the host-side `uv export`) and host `python3` (for `stage.py`)
- Docker

## Outputs
- `packaging/linux/build.Dockerfile`, the build image:
  - `FROM ubuntu@sha256:<digest>`;
  - the compile headers;
  - the DD1 fallback packages;
  - a pinned `uv`, and through it CPython 3.11.14;
  - the pinned PyInstaller and contrib hooks;
  - the pinned `appimagetool` and type2 runtime, downloaded and sha256-verified in the Dockerfile, so the hosted runner needs no pre-seeded tools dir.
- `packaging/linux/build.sh`, reworked:
  - on the host: stage (`stage.py`), and `uv export` the hash-pinned closure;
  - then `docker run` the build image as the invoking uid (`-u "$(id -u):$(id -g)"`), with all of `packaging/` (read-only), the stage dir and the output dir mounted;
  - the freeze, the fallback copy, and the AppImage and `.deb` wrapping all run inside;
  - the closure is installed into a venv inside the container; caching it in an image layer keyed on the closure file is allowed.
- A small inner script if needed (for example `packaging/linux/build-inner.sh`).
- The fallback set in the AppDir:
  - `usr/lib/gleepglorp-ai-fallback/lib/` for the `.so` files, with their sonames;
  - `usr/lib/gleepglorp-ai-fallback/girepository-1.0/` for `AyatanaAppIndicator3-0.1.typelib`.

  Never inside the PyInstaller bundle (`usr/lib/gleepglorp-ai/` and its `_internal`). The `.deb` gets no fallback directory.
- `packaging/linux/rthook_host_gtk.py`: the host-first soname preload (below).
- `packaging/spike/score.py` and `inner.sh`: amended gate 3 for the AppImage; a "host has the library" variant; the ABI exercise.
- `packaging/linux/README.md`: the container build, the fallback, and the digest.
- Packages for N=`0.11.8` and N+1=`0.11.9.dev1` under `$HOME/the-one-m32-build/f2/packages/`. This is a new `M32_BUILD` root, so Flight 1's packages in `$HOME/the-one-m32-build/packages/` stay untouched for leg 4's probes.
- Evidence under `$HOME/the-one-m32-evidence/f2/leg1/`.
- A flight-log entry, with the Evidence Table rows for this leg.

## Acceptance Criteria
- [ ] **AC1 — pinned container build.** `packaging/linux/build.sh 0.11.8` and `… 0.11.9.dev1` each produce an AppImage and a `.deb` from the build image.
  - The image's `FROM` names `ubuntu@sha256:` with the digest re-read at leg start and recorded in the flight log. Planning value: `68ee2200…aff33ac`; if the tag has moved, record both and use the new one.
  - The build log shows `Python: 3.11.14` and PyInstaller `6.22.3`.
  - No step of the freeze or wrap runs outside the container.
  - Nothing is written inside the repo: `git status --porcelain` shows only intended source edits.
- [ ] **AC2 — fallback placement.**
  - `find` over the extracted AppImage lists exactly the six sonames from Context, as real files (no compat symlinks such as `libappindicator3.so.1`), plus `AyatanaAppIndicator3-0.1.typelib`, only under `usr/lib/gleepglorp-ai-fallback/`.
  - None of `libgirepository-*`, `libayatana-*`, `libdbusmenu-*` or `*.typelib` is anywhere under `usr/lib/gleepglorp-ai/`.
  - The build's `NEEDED` walk fails the build if any of the six needs a library outside glibc's own sonames (`libc.so.6`, `libm.so.6`, `libdl.so.2`, `libpthread.so.0`, `librt.so.1`, `ld-linux-x86-64.so.2`), `libffi.so.8`, `excludes.txt`'s families and the six themselves.
  - `readelf -d` `NEEDED` lists for the six are saved as evidence.
  - `dpkg-deb -c` of the `.deb` shows no fallback directory.
- [ ] **AC2b — the container bundle matches what Flight 1 measured.**
  - Diff the container-built bundle's file list against Flight 1's `$HOME/the-one-m32-build/linux-0.11.8/dist/the-one/` list (read only). Each difference is explained in the flight log, or there are none.
  - The bundle still contains the `gi.overrides` modules (`GLib`, `Gtk`, `Gio`, …) in the PYZ TOC.
  - No `excludes.txt` pattern matches a bundle file.
  - The build log records the installed versions of `libglib2.0-0t64`, `libgirepository-2.0-0`, `libayatana-appindicator3-1`, `gir1.2-ayatanaappindicator3-0.1` and the dbusmenu and ido packages. They float with 24.04 updates, so each build records what it bundled.
- [ ] **AC3 — never on the loader path.**
  - With `M32_DEBUG_ENV=1`, the frozen AppImage's hook prints `LD_LIBRARY_PATH` and `GI_TYPELIB_PATH`. `LD_LIBRARY_PATH` contains no fallback and no bundle path.
  - `GI_TYPELIB_PATH` lists the host directories first, and the fallback typelib directory last, only when the AppImage has one.
  - In `/proc/<pid>/environ` of a `WebKitWebProcess`, none of the loader-affecting variables (`LD_LIBRARY_PATH`, `LD_PRELOAD`, `GI_TYPELIB_PATH`, `GIO_MODULE_DIR`, `GTK_PATH`, `XDG_DATA_DIRS`) holds a path under the AppImage mount or the bundle. `APPDIR`, `ARGV0` and `_PYI_APPLICATION_HOME_DIR` are expected there and are inert.
- [ ] **AC4 — the ABI exercise (the divert test).** An env-gated probe runs inside the frozen process: a block at the end of `rthook_host_gtk.py`, active only when `M32_ABI_PROBE=1`, that prints its results and calls `os._exit`. It stays out of `the_one/`, and the README says it ships, inert, in both packages. Run it with `LD_BIND_NOW=1` so lazy-binding errors surface. It:
  - imports `gi`;
  - `require_version`s Gtk 3.0, WebKit2 4.1 and AyatanaAppIndicator3 0.1;
  - creates a `Gtk.Window`, a `WebKit2.WebView` inside it, and an `AyatanaAppIndicator3.Indicator.new(...)`;
  - runs the main loop briefly, then exits.

  It runs in three configurations, all with the WSLg display:
  1. **Debian 13 baseline:** the real fallback, so GLib 2.84 with the fallback `libgirepository` and fallback Ayatana libraries on top of the host's dbusmenu.
  2. **Ubuntu 26.04 baseline:** the host libraries plus the fallback typelib.
  3. **Ubuntu 26.04 baseline with `M32_FORCE_FALLBACK=1`:** a debug knob, honoured only together with `M32_DEBUG_ENV=1`, that preloads all six fallback copies by absolute path even though the host has them. This is the GLib 2.88 evidence DD1 needs.

  Each run passes with no crash, no `undefined symbol`, and no GLib or GObject critical or warning (stderr captured and grepped). For run 3, the maps confirm the fallback copies were the ones loaded. Output is saved as evidence.

  **If this fails, stop: emit `[BLOCKED:divert-appimage-abi]` with the evidence. The flight diverts to the operator. Do not work around it.**
- [ ] **AC5 — strict gates, AppImage.** `check.sh` (amended) for the AppImage on `ubuntu-26.04-baseline` and `debian-13-baseline`:
  - G1 pinned PASS and **G1 unpinned PASS**;
  - G2 PASS;
  - **amended G3 PASS, scored per soname:**
    - one copy of each listed library in the UI process;
    - each of the six fallback sonames comes from `/usr/lib` when the host resolves it, and from the AppImage mount (`/tmp/.mount_*` or the extract-and-run dir) only when it does not. On Debian 13 that means dbusmenu from `/usr/lib`, and girepository, indicator, ido and appindicator from the mount;
    - every other listed library from `/usr/lib`;
    - each `WebKitWebProcess` maps nothing from the AppImage mount.

    `score.py`'s `LIBS` gains the five Ayatana and dbusmenu sonames. Whether the host has each one comes from `ldconfig -p` per soname, recorded by `inner.sh`, not from `dpkg -s`. The hook's `M32_DEBUG_ENV` host/fallback report is cross-checked against the maps;
  - G4, upgrade and single-instance PASS.

  The `score.py` output lines are recorded in the flight log.
- [ ] **AC6 — host first, and the mixed case.**
  - **Ubuntu 26.04 baseline plus `apt-get install gir1.2-ayatanaappindicator3-0.1`** (host libraries and typelib): the UI process maps nothing from the fallback directory, `GI_TYPELIB_PATH` does not include the fallback typelib directory, and gate 3 passes.
  - **Debian 13 baseline plus `apt-get install libayatana-appindicator3-1 gir1.2-ayatanaappindicator3-0.1`** (Ayatana from the host, girepository missing; precheck: `ldconfig -p | grep girepository-2.0` is still empty after that install, or record that this variant is not reachable on Debian 13 and drop it): the maps show `libgirepository-2.0` from the mount and every Ayatana library from `/usr/lib`, and gate 3 passes.
- [ ] **AC7 — the `.deb` still passes.** `check.sh` for the `.deb` on all four images (`ubuntu-26.04` and `debian-13`, `baseline` and `bare`): the same PASS lines as Flight 1 (G1 both, G2, G3 where a window runs, G4, upgrade, single-instance).
- [ ] **AC8 — bare hosts don't crash.** On `ubuntu-26.04-bare` and `debian-13-bare` (no GTK): the AppImage's `version` prints `GleepGlorp AI v0.11.8`, and `doctor` runs to its `RESULT:` line, with no traceback from the runtime hook (the preload is best effort, catching `OSError`).
  - The desktop-shell gate is **expected to FAIL here** until leg 2 (DD11). Record its line as evidence; do not fix it in this leg.
- [ ] **AC9 — hygiene.**
  - `ruff check packaging/` and `ruff format --check packaging/` pass.
  - `shellcheck` (from `$HOME/the-one-m32-build/tools/shellcheck-0.10.0/`) passes on every changed shell script.
  - This leg's changes are confined to `packaging/linux/`, `packaging/spike/` and this flight's log. Leg 2 is editing `the_one/` and `tests/` concurrently in the same worktree, so check with `git status --porcelain -- packaging/ missions/`, not a whole-tree diff.
  - No instance used port 8484 or 8485.
  - The operator's data dir `/home/cprch/.local/share/the-one` has the same newest mtime before and after.
  - Only `m32-*` containers were created, and none is left running.

## Verification Steps
- AC1: the build log heads; `docker image inspect` of the build image; `grep '^FROM' packaging/linux/build.Dockerfile`.
- AC2: `<AppImage> --appimage-extract` into a scratch dir, then `find`; `dpkg-deb -c`.
- AC3: `M32_DEBUG_ENV=1` output; `cat /proc/<webpid>/environ | tr '\0' '\n'` inside the gate container.
- AC4: the ABI probe's output files under the evidence dir.
- AC5-AC7: `score.py` lines (`score.json` per run).
- AC8: the bare-run `doctor` output.
- AC9: the commands named.

## Implementation Guidance

1. **Re-read the digest:** `docker pull ubuntu:24.04` and `docker inspect --format '{{index .RepoDigests 0}}'`. Record it.
2. **The build image** (`packaging/linux/build.Dockerfile`):
   - apt installs: `gcc pkg-config libgirepository-2.0-dev libcairo2-dev gobject-introspection dpkg-dev file curl ca-certificates`, plus the fallback packages `libgirepository-2.0-0 gir1.2-ayatanaappindicator3-0.1 libayatana-appindicator3-1`;
   - `uv` copied from `ghcr.io/astral-sh/uv:0.9.30`, the version CI pins (`ci/tasks/*.yml`);
   - `uv python install 3.11.14`;
   - `appimagetool` and the type2 runtime fetched by URL and checked against the sha256 in `packaging/linux/README.md`;
   - no network needed at `docker run` time.

   The closure is installed in an image layer, not at run time. The closure holds sdists (PyGObject, pycairo) that need network and headers. Concretely:
   - the hash-pinned closure file is passed as build context, and the venv is created in a layer keyed on that file, with PyInstaller and the contrib hooks in the same or the next layer;
   - `UV_PYTHON_INSTALL_DIR=/opt/uv-python`, and the venv under `/opt/`, both world-readable, because the build runs as a non-root `-u uid:gid` and the default `/root/.local/share/uv` is unreadable to it;
   - `uv` is copied from `ghcr.io/astral-sh/uv:0.9.30` **pinned by digest** (`sha256:538e0b39…`, re-read and recorded), as the base image is.
   - At `docker run`, set `HOME`, `UV_CACHE_DIR` and `PYINSTALLER_CONFIG_DIR` to writable paths under the output dir.
3. **`build.sh`:**
   - `M32_BUILD` defaults to `$HOME/the-one-m32-build/f2` for this flight;
   - stage on the host;
   - `uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt` on the host;
   - `docker build` (or reuse) the image;
   - `docker run --rm --name m32-build-<ver> -u uid:gid` with read-only mounts of **all of `packaging/`** (the spec loads `../windows/frozen_entry.py`) and the stage dir, a read-write output dir, and `HOME` set to a writable dir inside the output dir;
   - no `--privileged`, no `--network host`.

   Keep `set -euo pipefail`. The AppDir and `.deb` layouts stay as in Flight 1, plus the fallback dir in the AppDir only.
4. **The fallback copy (inside the container):**
   - `libgirepository-2.0.so.0` is copied from the installed system library (`cp -L`).
   - The Ayatana stack is extracted: `apt-get download libayatana-appindicator3-1 libayatana-indicator3-7 libayatana-ido3-0.4-0 libdbusmenu-gtk3-4 libdbusmenu-glib4 gir1.2-ayatanaappindicator3-0.1`, at the versions apt picks (adjust the package names to what 24.04 calls them, and record them), then `dpkg -x` into a staging dir, then copy the six sonames (real files, not compat symlinks) and the typelib from there.
   - Do the `NEEDED` walk (AC2) with `readelf -d` on those files. `ldconfig` cannot see the extracted ones.
   - Print the list and the package versions to the build log.
5. **`rthook_host_gtk.py`:**
   1. Locate the fallback dir as `<dirname(sys._MEIPASS)>/../gleepglorp-ai-fallback` (resolve and check it exists), so both the mounted and the extract-and-run layouts work.
   2. If it does not exist (the `.deb`), do nothing new.
   3. Walk the sonames in dependency order: `libgirepository-2.0.so.0` on its own, then the Ayatana chain `libdbusmenu-glib.so.4`, `libdbusmenu-gtk3.so.4`, `libayatana-ido3-0.4.so.0`, `libayatana-indicator3.so.7`, `libayatana-appindicator3.so.1`. For each, try `ctypes.CDLL(soname, mode=ctypes.RTLD_GLOBAL)` (the bare name reaches the system loader, since `_internal` holds none of these).
   4. On `OSError`, try `ctypes.CDLL(<fallback>/<soname>, mode=ctypes.RTLD_GLOBAL)`. If that also fails, stop the chain there: on a bare host `libdbusmenu-gtk3` cannot load without GTK, so do not half-load the rest. Never raise; under `M32_DEBUG_ENV=1` print which source each soname came from, or why it was skipped. With `M32_FORCE_FALLBACK=1` (honoured only with `M32_DEBUG_ENV=1`), load the fallback path first, for AC4's run 3.
   5. **The typelib is decoupled from the library preload.** Append `<fallback>/girepository-1.0` to `GI_TYPELIB_PATH`, after the host directories, whenever neither `AyatanaAppIndicator3-0.1.typelib` nor `AppIndicator3-0.1.typelib` exists in a host typelib directory. That is a file-existence check, whether or not any fallback `.so` was loaded. The typelib's `shared-library` entry then binds to the host's or the preloaded library by soname. This is exactly Ubuntu 26.04's case.
   6. Never touch `LD_LIBRARY_PATH` beyond what the hook already does.
   7. Extend the `M32_DEBUG_ENV=1` print with which sonames came from host and which from the fallback.
6. **The amended gate 3** (`score.py` and `inner.sh`):
   - `inner.sh` records whether the host has `libgirepository-2.0-0` and the Ayatana package (`env.txt` already lists them);
   - `score.py` accepts the fallback path for exactly those libraries when the host lacks them, and requires `/usr/lib` otherwise;
   - it adds a check that every `web-*.maps` has no path under the AppImage mount;
   - it adds the AC6 variant (an `--extra-apt` option, or an image tag built with the package added).

   Keep the scoring strict: a fallback path when the host *has* the library is a FAIL.
7. **The harness additions,** all in `packaging/spike/`:
   - `check.sh --env K=V` (repeatable), forwarded into `inner.sh`'s run environment (`WENV`; `inner.sh` uses `env -i`), for `M32_DEBUG_ENV`, `M32_FORCE_FALLBACK`, `M32_ABI_PROBE` and `LD_BIND_NOW`.
   - `check.sh --variant NAME --extra-apt "pkgs"`: changes only the evidence subdir (`…/<distro>-<image>-<variant>`, so the AC5 evidence is never overwritten) and runs `apt-get install -y <pkgs>` inside `inner.sh` before the run. `IMAGE` stays `baseline`, so the window, G3 and single-instance checks still run.
   - **Probe mode** in `inner.sh` (`M32_ABI_PROBE=1`): install the package, then run the probe as `tester` with `WENV` (`DISPLAY`, the WebKit sandbox variables) under `dbus-run-session`, capturing stdout, stderr and the probe's printed `/proc/self/maps` lines for the six sonames, and skip the rest of the flow.
   - **The `ldconfig -p` per-soname host record** in `inner.sh`, before the package install, into `host-libs.txt`. `score.py` reads it.
   - **The `/proc/<webpid>/environ` capture** in `inner.sh`, read as the process's own user (as the maps are), for AC3.
8. **The ABI probe (AC4):**
   - The `M32_ABI_PROBE=1` block runs at the very end of `rthook_host_gtk.py`, after the preload and the `GI_TYPELIB_PATH` change; the stock `pyi_rth_gi` hook has already run, or the assignment wins either way. It prints the maps lines for the six sonames, then `os._exit`.
   - The fail grep is exactly: `GLib-CRITICAL`, `GLib-GObject-(CRITICAL|WARNING)`, `GLib-GIO-(CRITICAL|WARNING)`, `symbol lookup error`, `undefined symbol`.
   - A **control run** of the same probe uses the `.deb` on the same image (pure host libraries, same hook). Any line that also appears in the control is excluded from the fail grep, and the exclusions are recorded.
9. **Run** AC5-AC8, update the README, and write the flight-log entry: a new `### appimage-library-fallback` under Leg Progress, the score lines, the fallback list, the digest, the deviation (staging on the host, because of the worktree), and the evidence paths.

## Edge Cases
- **Extract-and-run** (containers have no FUSE): the AppImage runs from `/tmp/appimage_extracted_*` instead of `/tmp/.mount_*`. The fallback lookup must be relative to `sys._MEIPASS`, and gate 3's "AppImage mount" must cover both prefixes.
- **The host has the legacy `AppIndicator3` typelib but no Ayatana one:** pystray tries `AppIndicator3` first and uses it, so the fallback typelib is not added (step 5 checks both). Neither baseline is in this state.
- **`find_library` on a host without `ldconfig` in `PATH` for the test user:** fall back to `CDLL(soname)` in a `try`.
- **A partially satisfied chain** (Debian 13's normal case: the host has dbusmenu but not the indicator): the bare-name `CDLL` succeeds for dbusmenu (host), and the fallback loads the rest. The loader reuses the host's dbusmenu for the indicator's `NEEDED` by soname.
- **The image build needs network:** fine on the dev host and on the runner. `docker run` for the build needs none.
- **uid inside the container:** `-u uid:gid` with no matching passwd entry. Set `HOME`, and make the uv cache and Python paths writable.

## Files Affected
- `packaging/linux/build.Dockerfile` (new)
- `packaging/linux/build.sh`
- `packaging/linux/build-inner.sh` (new, if used)
- `packaging/linux/rthook_host_gtk.py`
- `packaging/linux/README.md`
- `packaging/spike/{inner.sh,score.py,check.sh}`: amended per-soname gate 3, `--env`, `--variant`/`--extra-apt`, probe mode, the host-libs record, the environ capture
- `missions/32-installers-everywhere/flights/02-linux-packages/flight-log.md`

## Citation Audit
Checked at `980415e`:
- `packaging/linux/build.sh`: version from `$1`; `M32_BUILD` default; `stage.py` from `packaging/spike/`; AppDir `usr/lib/gleepglorp-ai`; `.deb` at `/opt/gleepglorp-ai`. Verified.
- `packaging/linux/rthook_host_gtk.py`: sets `GI_TYPELIB_PATH` to three host dirs; restores `LD_LIBRARY_PATH` from `LD_LIBRARY_PATH_ORIG`; `M32_DEBUG_ENV`. Verified.
- `packaging/linux/excludes.txt`: includes `libgirepository-*.so*` (and, per the cycle-1 design review, `libayatana-*`/`libdbusmenu-*`). Re-check at leg start.
- `packaging/spike/check.sh`: hard-codes `-v /mnt/wslg/.X11-unix:/tmp/.X11-unix` for `baseline`. Verified.
- `packaging/spike/score.py::score_maps`: `host = [h for h in hits if h.startswith("/usr/lib/")]`. Verified.
- `.git` of this worktree: `gitdir: /home/cprch/projects/the-one/.git/worktrees/m32-installers`. Verified (the reason staging stays on the host).

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
