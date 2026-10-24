# Flight Log: Choose the packaging toolchain

**Flight**: [Choose the packaging toolchain](flight.md)

## Summary
Planned 2026-10-23 in the worktree `/home/cprch/projects/the-one-worktrees/m32-installers`, from `origin/main` at `8a52a39` plus the mission commit `b060d84`. Mission 31 is active in the main checkout at the same time; this flight never touches it.

---

## Planning Notes

- **Operator decisions, 2026-10-23:**
  - macOS budget: at most 2 macOS jobs this flight;
  - the winner's spike recipe is kept as Flight 2's starting point, and the loser is removed;
  - the Windows comparison is tested for real if Briefcase survives Linux;
  - the Windows installer is built on GitHub, and the operator downloads it and runs it over their own install (Windows 11 Home: no Windows Sandbox or Hyper-V);
  - a guided decision session (HAT) closes the flight.
- **Planning checks:**
  - the target-distro containers resolve;
  - WSLg and the host WebKitGTK 4.1 are present;
  - an offline `uv.lock` audit found no macOS arm64 wheel gaps that matter (see the flight's Citation Audit).
- **Carried from the Mission 15 Flight 5 debrief:**
  - the packaged smoke proves spawn behaviour, never the rendered window, so the window is looked at directly (the Linux legs and `decision-hat`);
  - first-time freeze recipes carry 2 to 4 CI-only issues, which is why the macOS run is rehearsed on Linux first and capped;
  - Actions artifact storage hit its quota in Mission 15, so there is a draft-release fallback;
  - every `webview.start()` call needs its `private_mode`/`storage_path` decision, which matters for the upgrade check;
  - `_common_runtime_dirs()` lacks NVM/fnm node paths on macOS (a paper item for Flight 3).
- **Design review, cycle 1 (Architect): approve with changes.** Folded in:
  - workflows must exist on `main` to be dispatched. The operator chose a small `.github/`-only PR to `main` (DD6);
  - the pystray backend is pinned, and tray visibility is not scored in WSLg or containers (DD2, DD5);
  - gate 3 now asserts a single host GTK/WebKit stack through `/proc/<pid>/maps`, and A owes an exclude list;
  - Briefcase builds a `.deb` per distro through Docker targets (DD1);
  - gates 1 and 2 are strict and measured independently, because the not-frozen path downgrades or short-circuits them under Briefcase;
  - one stock-desktop container baseline for both candidates;
  - a staged `__version__` rewrite for the N to N+1 upgrade;
  - gate 4 is measured only in containers;
  - elimination and hybrids are per platform and format;
  - per-leg re-verification of external sessions;
  - `macos-15` is pinned;
  - leg 1 is split into one leg per candidate (five legs);
  - three citation corrections.
- **Design review, cycle 2 (Architect): approve with changes.** Folded in:
  - DD4 patches are kept as staging-time diff files, so the hosted jobs run with them;
  - gate 1 rejects any `skipped` detail (the not-frozen downgrades read `skipped (…)`), and is run with and without `PYSTRAY_BACKEND`;
  - gate 3's web-process check is "at most one copy, all host";
  - B's PyGObject comes from the pinned closure, compiled in its Docker build;
  - A is frozen with Python 3.11, and B's distro Pythons are recorded;
  - a format that fails a hard gate stops there;
  - small wording fixes.

  This was the last design review cycle.
- **Finding for Flight 2 (operator: no separate squawk):** with the Ayatana AppIndicator typelib missing, `import pystray` raises `ValueError`, which `pystray.backend()` does not catch (it falls through only on `ImportError`). So the tray never starts on a stock Debian GNOME source install, and in a frozen build the desktop-shell `doctor` gate fails.

### Flight Director Notes

- **2026-10-23, execution start.** Loaded `.flightops/agent-crews/leg-execution.md`; Developer is Sonnet, and the Reviewer is Haiku unless the diff touches a security-sensitive surface. The flight branch `flight/01-choose-packaging-toolchain` was cut from `mission/32-installers` at `4892b1f`, and the flight was set to in-flight.
- **Deviation from the deferred-commit default, made out loud:** `macos-probe` and `windows-cost` build on hosted runners from the pushed flight branch, so the Linux legs' code must be reviewed, committed and pushed before leg 3 dispatches anything. The plan:
  - Reviewer pass and commit after leg 2 (`linux-briefcase`);
  - push the flight branch;
  - then the `.github/`-only PR to `main` (DD6), as its own branch off `main`;
  - legs 3 and 4 committed after their own review;
  - leg 5 (HAT) committed at the end.
- **Leg 1 (`linux-pyinstaller`) risk tier: high.** It is additive and outside `the_one/`, but its apparatus rests on several unproven premises: WSLg forwarding through Docker Desktop, PyInstaller's gi-hook behaviour, and the stock-desktop baseline contents. A wrong premise would waste the leg, so it gets a Developer design review.
- **Leg 1 design review (Developer): approve with changes.** The leg was too big for one session, so it is split into `linux-pyinstaller-build` (legs/01) and `linux-pyinstaller-gates` (legs/02). The flight now has six legs; the Briefcase leg is 03. The commit point moves to after leg 03. Also folded in:
  - the tray is decided by measurement: the AppImage's unpinned result on the stock baseline is the truth, and the `.deb`'s `Depends` are proven on a `bare` image;
  - single-instance mechanics follow `shell.py` (`_select_port`, then `POST /api/window/focus`, with no success log);
  - the version is asserted as a `v<version>` substring;
  - the Linux spec must not put the repo root on `sys.path`;
  - the container window runs under `dbus-run-session`, with WebKit's own sandbox disabled in containers only (logged), and no `--privileged` or `--network host`;
  - the icon is `icon-512.png`, and the package is `gleepglorp-ai`, with `the-one` as the command;
  - the appimagetool runtime is pinned with checksums;
  - three exclude-list attempts at most;
  - only the credential's prefix is logged, never the secret.
- **No second design review for `linux-pyinstaller-build`** (Flight Director call). Every change is a fix the review itself specified, plus the split; nothing new was designed. It is set to `ready`. `linux-pyinstaller-gates` is drafted, and is tiered and reviewed when it comes up.
- **`linux-pyinstaller-build` landed** (`[LAND:leg]`). Four packages are in `~/the-one-m32-build/packages/`. The Flight Director checked: the worktree changes sit only under `packaging/` and `missions/`, and the leg status is `landed`.
- **Observation, not yet a squawk:** the Developer saw 21 unit failures under a uv-managed CPython 3.11.14 venv that pass on 3.12 (MCP and credential tests). It judged them environmental. CI's unit tier runs a 3.11 image, so this is worth checking. It is raised to the operator, not folded into this flight.
- **`linux-pyinstaller-gates` risk tier: low.** It measures and adds spike harness only, with no app code. Its criteria came out of the reviewed leg 1 design, so it skips a design review. It was updated from leg 1's findings: the pinned tray backend is `gtk` (a pin to `appindicator` fails on every stock baseline); gate 3 also counts `libstdc++` and `libgcc_s`; Debian's missing `libgirepository-2.0-0` is expected. Set to `ready`.
- **`linux-pyinstaller-gates` landed** (`[LAND:leg]`).
  - A's `.deb` passes every gate on both distros, and its declared dependencies are proven on `bare`.
  - A's AppImage fails the unpinned tray check on Ubuntu (no Ayatana typelib), and everything window-related on Debian (no `libgirepository-2.0` on its stock desktop).
  - The forwarded WSLg display worked, so no window result is directional.
  - A recipe defect was found and fixed in `packaging/linux/` (`gi.overrides` not collected: `doctor` passed but no window opened).
- **`linux-briefcase` risk tier: high.** Briefcase's behaviour for system packages (launcher, `sys.executable`, `requires` pinning, AppImage status) is unverified, and the leg may need an app-side patch, so it gets a Developer design review.
- **`linux-briefcase` design review (Developer, from reading Briefcase 0.4.6's source): approve with changes.** Folded in:
  - `allow_subprocesses = true` is required, otherwise `sys.executable` is `""`;
  - the `.desktop` `Exec` and main module are not configurable, so opening the window needs a startup-default DD4 patch;
  - `Depends` needs exact per-distro names (an `a | b` would become a shell pipe) plus an explicit `python3`;
  - a narrow `is_frozen()` patch must handle `_bundle_dir()`, and the `PATH` and `.env` checks are logged;
  - an AppImage build failure is a FAIL with its log;
  - per-target pip outcomes, cold and warm build times, and icon sizes.
- **`linux-briefcase` landed** (`[LAND:leg]`).
  - B's `.deb`s pass every gate with two staged patches: 01 (bare start opens the window) and 02 (Briefcase counts as frozen).
  - Unpatched, gate 2 fails everywhere: in 0.4.6, `sys.executable` is the launcher whatever `allow_subprocesses` says, which corrects the design review's premise.
  - B's AppImage fails to build.
- **Review checkpoint (the deviation recorded at execution start):** a Reviewer evaluates legs 01-03 now, before the commit and push that the hosted legs need. **Reviewer tier: Sonnet.** The diff carries DD4 patches to `the_one/platform/env.py`'s frozen/subprocess-environment seam (the spawn path behind sandboxing and the `PATH` stripping), which is a security-adjacent surface, even though the patches apply only to the staging copy.
- **Review checkpoint result: `[HANDOFF:confirmed]`** (Sonnet Reviewer; no blocking issues). Non-blocking notes:
  1. Patch 01 changes bare `the-one` for every install, source included. If B wins, Flight 2 gates it on the Briefcase marker or a launcher flag. This is recorded as a cost of B.
  2. The `flight.md` Technical Approach prose described five legs. It is now annotated with the split, and the Legs list is updated.
  3. The landed legs were unchecked; they are now ticked.
  4. `rthook_host_gtk.py` lists the amd64 typelib path first, which needs revisiting if an arm64 Linux target is ever added (out of mission scope).

  Legs 01-03 are set to `completed` and committed by the Flight Director (a mechanical commit of reviewed changes).
- **`macos-probe` split** into `macos-probe-prepare` (autonomous; no push, PR or dispatch) and `macos-probe-run`. Between them, the Flight Director commits and pushes, opens the `.github/`-only PR to `main` with the operator's go, merges it after `pr-lint`, and dispatches. That human checkpoint is why it is two legs. The flight now has seven legs.

  No second review (Flight Director call): the changes are the review's own specified fixes. Set to `ready`.



### linux-pyinstaller-build
**Status**: landed
**Started**: 2026-10-23
**Landed**: 2026-10-23

#### Changes Made
- `packaging/spike/` (candidate-neutral): `stage.py`, `images/{ubuntu-26.04,debian-13}.Dockerfile` (targets `baseline` and `bare`, each with a final observe layer), `README.md` (says spike tooling, not product).
- `packaging/linux/`: `the-one.spec`, `rthook_host_gtk.py`, `excludes.txt`, `build.sh`, `AppRun`, `gleepglorp-ai.desktop.in`, `control.in`, `README.md` (pinned tools and checksums). `patches/` is empty: no app-side patch was needed to freeze or start.
- Build outputs, all outside the repo: `$M32_BUILD=$HOME/the-one-m32-build` (bundles, `packages/`, `venv-pyi/`, `tools/`), evidence in `$M32_EVIDENCE=$HOME/the-one-m32-evidence`.
- Nothing changed under `the_one/`, `tests/`, `.github/`, `ci/`, `pyproject.toml` or `uv.lock`; CLAUDE.md and `the_one/agents.md` untouched (shared with Mission 31).
- Operator default data dir (read, not guessed; leg 2 uses it for its safety check): `/home/cprch/.local/share/the-one`.

#### AC1 - staging never touches the repo (met)
- `stage.py --version 0.11.9.dev1 --candidate linux` -> `$M32_BUILD/stage-linux-0.11.9.dev1/` with `the_one/` and `icon-512.png`; `grep __version__` there: `__version__ = "0.11.9.dev1"`.
- `--out $PWD/x` (inside the repo) -> `stage.py: error: output path ... resolves inside the repo`, exit 1. The version rewrite fails the same way unless exactly one `__version__` line matches. Patches in `packaging/<candidate>/patches/*.diff` apply in name order via `patch -p1`, failing on any reject (none exist).
- `git status --porcelain -- the_one/ pyproject.toml uv.lock`: empty.

#### AC2 - container images (met; default recommends worked, no substitution beyond the snapd hold)
`baseline` = `ubuntu-desktop-minimal` / `task-gnome-desktop` with default recommends; the only change is an apt pin that refuses `snapd` on Ubuntu (it needs a running service). Both built headless with rc=0; no `--no-install-recommends` substitution was needed. Observe layer (separate, harness-only): `procps dbus-x11 xvfb xauth x11-apps scrot curl ca-certificates` (bare adds `dbus-user-session`). Sizes: ubuntu baseline 3.8 GB, debian baseline 5.85 GB, bares 735/797 MB. Full output: `$M32_EVIDENCE/ac2-images.txt`.

| image | python3 | gir1.2-webkit2-4.1 | libwebkit2gtk-4.1-0 | gir1.2-gtk-3.0 | gir1.2-ayatanaappindicator3-0.1 | libgirepository-2.0-0 | bubblewrap | node/uv |
|---|---|---|---|---|---|---|---|---|
| ubuntu-26.04 baseline | 3.14.4 | 2.52.6 | 2.52.6 | 3.24.52 | **absent** | 2.88.0 | 0.11.1 | absent |
| ubuntu-26.04 bare | 3.14.4 | absent | absent | absent | absent | absent | 0.11.1 | absent |
| debian-13 baseline | 3.13.5 | 2.54.0 | 2.54.0 | 3.24.49 | **absent** | **absent** | 0.12.0 | absent |
| debian-13 bare | 3.13.5 | absent | absent | absent | absent | absent | absent | absent |

Findings: package names are non-t64 on both distros (`libwebkit2gtk-4.1-0`, `libgirepository-2.0-0`; the `t64` alternatives in `Depends` are harmless insurance). The Ayatana typelib is absent from BOTH stock desktops, so an unpinned tray fails on a stock desktop unless the package declares it. Debian 13's stock desktop does not even have `libgirepository-2.0-0` (its python3-gi uses the 1.0 library), so the `.deb` must declare it, and an AppImage cannot rely on it there.

#### AC3 - freeze (met)
- Build venv `$M32_BUILD/venv-pyi`: uv-managed CPython 3.11.14; closure from `uv export --no-dev --no-emit-project --extra gui --extra all-llms` (1755-line hash-pinned file) installed with `--no-deps` (PyGObject 3.56.3 and pycairo 1.29.0 compiled from source against host headers; no blocker), then `pyinstaller==6.22.3`, `pyinstaller-hooks-contrib==2026.8` (2026.9 was 3 days old).
- Build log head: `PyInstaller: 6.22.3, contrib hooks: 2026.8` / `Python: 3.11.14` / `Platform: Linux-...-glibc2.39`.
- Frozen `the-one version`: N -> `GleepGlorp AI v0.11.8`; N+1 -> `GleepGlorp AI v0.11.9.dev1`. Both AppImages print the same under `--appimage-extract-and-run`.
- Repo path in PYZ: `grep -c "m32-installers\|projects/the-one" work/the-one/PYZ-00.toc` = 0; 170 modules point at `$M32_BUILD/stage-linux-0.11.9.dev1/the_one/`. The spec never imports `the_one` from the repo and only puts the staged dir on `sys.path`/`pathex`.
- `grep -i -E 'pyinstaller|appimagetool|briefcase' uv.lock pyproject.toml`: no output.
- Cold freeze: about 71 s wall (excludes off or on); a full `build.sh` run (stage, freeze, both wrappers) about 70-73 s on this 20-core host.

#### AC4 - the gi premise (met)
Before (no excludes, `M32_NO_EXCLUDES=1`; bundle 296 MB):
```
_internal/libgirepository-2.0.so.0
_internal/libglib-2.0.so.0
_internal/libgobject-2.0.so.0
```
No `libwebkit2gtk*`, `libjavascriptcoregtk*`, `libgtk-3*` or `*.typelib` at all. Why: on this build host (Ubuntu 24.04, glib 2.80) PyInstaller 6.22.3's gi hooks cannot query any GI module, because `hook-gi` requires `GIRepository-3.0` and the host only ships `GIRepository-2.0.typelib` (`WARNING: Failed to query GI module GObject 2.0 ... Namespace GIRepository not available`, also for Gtk, Gdk, Gio, GLib, Soup, AyatanaAppIndicator3). So the hooks collected no typelibs and no GTK stack here; only the dependency scan of `gi/_gi*.so` pulled the three GLib libraries. On a build host with a newer glib the hooks would work and pull far more, so the build host is a recipe input (Flight 2 must pin it; the exclude list and the typelib drop in the spec keep either case clean). After (final build, N+1): the same `find` returns nothing, and none of `excludes.txt`'s patterns matches any file in the bundle. The spec excluded 12 files: `libblkid libgcc_s libgio-2.0 libgirepository-2.0 libglib-2.0 libgmodule-2.0 libgobject-2.0 libmount libmvec libpcre2-8 libselinux libstdc++`. Pillow's hashed wheel libraries (`libharfbuzz-<hash>.so`, `libfreetype-<hash>.so`, `libxcb-<hash>.so`, ...) are kept on purpose: `excludes.txt` anchors on the real soname, because Pillow links those by their hashed names. One exclude iteration was needed (the first draft's `libX*`/`libxcb-*` patterns would have matched Pillow's hashed copies). Bundle after excludes: 288 MB.
Hook proof (`M32_DEBUG_ENV=1 the-one version`): `GI_TYPELIB_PATH=/usr/lib/x86_64-linux-gnu/girepository-1.0:/usr/lib64/girepository-1.0:/usr/lib/girepository-1.0 LD_LIBRARY_PATH=None` (the stock `pyi_rth_gi`, `pyi_rth_gio`, `pyi_rth_glib` and `pyi_rth_gtk` hooks are all in the bundle and run first; ours runs after them and wins. It also undoes their bundle-pointing `GIO_MODULE_DIR`, `GTK_PATH`, `GTK_*_PREFIX`, `PANGO_*` and `XDG_DATA_DIRS` entries, which WebKit's helpers would inherit).
Smoke on the build host (24.04, host WebKit): `the-one doctor` from the final bundle: `desktop shell: FAIL — unexpected error: Namespace AyatanaAppIndicator3 not available` (the DD5 finding, the host lacks the Ayatana typelib), all other gates OK; with `PYSTRAY_BACKEND=gtk PYWEBVIEW_GUI=gtk`: `desktop shell: OK — pystray + PIL importable`, `RESULT: PASS`. So `gi` loads the host's typelibs and libraries from the frozen process. Leg 2 measures the rest.

#### AC5 - four packages (met)
```
GleepGlorp_AI-0.11.8-x86_64.AppImage        143710712  sha256 53cc43b2ded1afdaa2cf462f16266b2993426123238299364a39205f3b99212b
GleepGlorp_AI-0.11.9.dev1-x86_64.AppImage   143710712  sha256 c81270c4dbccb2238f31badb33eeb3950f10245cd89b72bde1b22dceeec8a22c
gleepglorp-ai_0.11.8_amd64.deb              141004908  sha256 242a236814d3e1603e9ec5df32f5eeca926cb082dcfdf915e023861490f2be6c
gleepglorp-ai_0.11.9~dev1_amd64.deb         141003404  sha256 d218ebc1dc6aac565000406e2117a6c9d827d81c4e31e098436f8e41cf15591c
```
- Tools (own dirs under `$M32_BUILD/tools/`): appimagetool 1.9.1 `ed4ce84f...eb0` (the release asset self-reports "continuous build 8c8c91f, 2025-12-04"), type2-runtime 20251108 `2fca8b44...c260d` (matches the release digest). Both are in `packaging/linux/README.md`. AppImages are built with `appimagetool --appimage-extract-and-run --runtime-file <pinned runtime>`.
- `AppRun` (`cat AppDir/AppRun`): `exec "$HERE/usr/lib/gleepglorp-ai/the-one" "$@"` with `app` as the no-argument default; `PATH` is not touched.
- `.deb`: `Package: gleepglorp-ai`, `Version: 0.11.8` / `0.11.9~dev1` (`dpkg --compare-versions 0.11.9~dev1 gt 0.11.8` true), `Architecture: amd64`, `Depends: python3, libwebkit2gtk-4.1-0 | libwebkit2gtk-4.1-0t64, gir1.2-webkit2-4.1, gir1.2-gtk-3.0, libgirepository-2.0-0 | libgirepository-2.0-0t64, gir1.2-ayatanaappindicator3-0.1, libstdc++6, libgcc-s1`. The last two are there because the bundle drops its own libstdc++ and libgcc_s. `dpkg-deb -c`: `./opt/gleepglorp-ai/the-one`, `./usr/bin/the-one -> /opt/gleepglorp-ai/the-one`, `./usr/share/applications/gleepglorp-ai.desktop`, `./usr/share/icons/hicolor/512x512/apps/gleepglorp-ai.png`. No maintainer scripts. Highest glibc symbol needed by the bundle: 2.34 (host 2.39; targets 2.41 and later).

#### AC6 - lint, unit gate, forbidden paths
- `.venv/bin/ruff check packaging/` -> All checks passed; `ruff format --check packaging/` -> 5 files already formatted.
- `make test-unit` (worktree `.venv`, CPython 3.12, locked closure + dev extra): `6783 passed, 12 skipped, 2556 deselected` (skip count 12, as CLAUDE.md expects). Log: `$M32_EVIDENCE/unit-gate2.log`.
- Triage note: a first run on a 3.11 `.venv` (unlocked resolve, then locked) failed 21 tests (`test_mcp_signin_detection`, `test_mcp_test_connection_negotiation`, `test_mcp_wire_shapes`, `test_openrouter_wire_level`, `test_credential_gate`: `CancelledError` in `MCPClient._cleanup_after_failed_connect`, and `openai` 401s). The unlocked resolve caused the OpenRouter ones (they pass with the locked closure); the MCP/credential ones fail only on CPython 3.11.14 and pass on 3.12 (164 passed on those five files). No `the_one/` file differs from the base, so it is environmental, not this leg. Worth a squawk if CI runs the unit tier on 3.11. The log is `$M32_EVIDENCE/unit-gate.log`.
- `git diff --stat mission/32-installers -- the_one tests .github ci pyproject.toml uv.lock`: empty.

#### Deviations and notes for leg 2 (`linux-pyinstaller-gates`)
- Fresh evidence pins: the run directory for scratch bundles is `$M32_BUILD/scratch-run/` (a `doctor` smoke only; its data dir was `$M32_BUILD/scratch-run/data`, never the operator's).
- Tray: no image has the Ayatana typelib. The `.deb` declares it; the AppImage cannot, so its unpinned `doctor` on the stock baseline is expected to FAIL the desktop-shell gate (the pystray `ValueError` fall-through finding). The pin `PYSTRAY_BACKEND=gtk` passes on the build host.
- The leg 2 gate-1 "skipped" check applies to the frozen bundle, where `is_frozen()` is true, so those gates are hard.
- `rthook_host_gtk.py` prints its result when `M32_DEBUG_ENV=1`; leg 2 can reuse that.
- `libffi.so.8` (and `libz.so.1`) are still bundled; they are leaf libraries. The bundle drops `libstdc++`/`libgcc_s`, so the Ubuntu and Debian hosts' own copies must load; the `.deb` declares them. Gate 3's `/proc/<pid>/maps` check should also look at `libstdc++`.
- WebKit helper processes and the window path are untested here by design (leg 2).
- The build host matters (see AC4): Ubuntu 24.04 with glib 2.80 yields no gi hook output; a host with a newer glib would change what is collected.

### linux-pyinstaller-gates
**Status**: landed
**Started**: 2026-10-23
**Landed**: 2026-10-23

#### Changes Made
- `packaging/spike/{check.sh,inner.sh,score.py,xwd2png.py}` and a README section; `packaging/linux/the-one.spec` (one collection fix, below) and a README note. Nothing outside `packaging/` and `missions/`; `ruff check packaging/` and `ruff format --check packaging/` pass.
- Packages rebuilt after the fix (`build.sh` for 0.11.8 and 0.11.9.dev1, about 70 s each). New sha256 (`$M32_BUILD/packages/SHA256SUMS`): AppImage 0.11.8 `c2105f4b...6539e4`, AppImage 0.11.9.dev1 `85b4cea5...8658`, .deb 0.11.8 `bae30f22...d530`, .deb 0.11.9~dev1 `ed520d48...0d31`. Versions still read `v0.11.8` and `v0.11.9.dev1`.

#### Findings and deviations (in order found)
1. **The forwarded WSLg display worked** (`xdpyinfo` from a Docker container, then real windows): no DD5 fallback was used for gate 3 or single-instance; results are not directional. Docker blocks WebKit's own sandbox, so window runs set the four `WEBKIT_*`/`LIBGL` variables in the table's environment line.
2. **Recipe defect, fixed in `packaging/linux/` (authorized dependency/collection fix):** the first window run failed: `TypeError: GLib.idle_add() takes exactly 3 arguments (1 given)`. Cause: PyInstaller's gi hooks cannot query GI on the 24.04 build host, so the PyGObject override modules were never collected (only `gi.overrides/__init__` was in the PYZ). `doctor` passed anyway, the server started, the window did not. Fix: `collect_submodules("gi.overrides")` in `hiddenimports`. This is exactly the failure class the packaged smoke (Mission 15) could not see: `doctor` does not exercise `GLib.idle_add`.
3. **`doctor` needs an X display** to pass the desktop-shell gate under the `gtk` backend (`Gtk could not be initialised` headless). All `doctor` runs use `xvfb-run`. A headless server install running `doctor` would see that failure.
4. **Harness faults found and fixed (not candidate defects):** no `apt-get update` in the images (the first `.deb` run reported `libwebkit2gtk-4.1-0` uninstallable); a backgrounded command-substitution hung the runner; `/proc/<pid>/maps` of another uid is unreadable even to container root (no `CAP_SYS_PTRACE`), so maps are read as `tester`; the UI process was first mis-identified as `xdg-desktop-portal-gtk`.
5. **Finding for Flight 2 (not packaging-specific, cause not confirmed on a source install):** `the-one app` creates the main window hidden and it stays unmapped (`xwininfo`: `IsUnMapped`) until a focus request arrives, on both WSLg's X and a private Xvfb (no window manager in either). The screenshot is therefore taken after `POST /api/window/focus`. The page itself loads in the webview before that (HTTP log). Worth a check on a real desktop session.
6. **Debian 13 AppImage is a real FAIL on a stock desktop:** `libgirepository-2.0.so.0` is absent, so `gi` cannot load, `_webview_available` is false, and the app serves with no window (gate 1 pinned FAIL, gate 3 FAIL, single-instance FAIL; gates 2, 4 and upgrade pass). The `.deb` passes because it declares `libgirepository-2.0-0`.
7. **Ubuntu 26.04 AppImage unpinned gate 1 FAIL** is the predicted missing Ayatana typelib (Context finding).

#### Acceptance
AC1-AC8: met, per the Evidence Table (`score.py` output in each `score.json`; summary lines below). AC9: below.
```
deb/ubuntu-26.04-baseline: G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=PASS single=PASS
deb/ubuntu-26.04-bare:     G1p=PASS G1u=PASS G2=PASS G3=N/A  G4=PASS upgrade=PASS single=N/A
deb/debian-13-baseline:    G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=PASS single=PASS
deb/debian-13-bare:        G1p=PASS G1u=PASS G2=PASS G3=N/A  G4=PASS upgrade=PASS single=N/A
appimage/ubuntu-26.04-baseline: G1p=PASS G1u=FAIL G2=PASS G3=PASS G4=PASS upgrade=PASS single=PASS
appimage/debian-13-baseline:    G1p=FAIL G1u=PASS G2=PASS G3=FAIL G4=PASS upgrade=PASS single=FAIL
```
#### AC9 safety
- No instance ran on 8484 or 8485; every instance used port 8490, 8491 or 8492, all inside containers (nothing app-side ran on the host). Every container used a scratch or container-home data dir (gate 4 uses the container's own `~/.local/share/the-one`, inside a container only). No container used `--privileged` or `--network host`; only containers named `m32-*` were created and stopped; two leftover `m32-gate-*`/`m32-shot-dbg` containers were removed by name.
- The operator's default data dir `/home/cprch/.local/share/the-one`: newest mtime `1791383047.9672937840` before and after (unchanged).
- `git diff --stat mission/32-installers`: changes only under `missions/` (and untracked `packaging/`); `the_one/`, `tests/`, `.github/`, `ci/`, `pyproject.toml`, `uv.lock`, `CLAUDE.md`, `the_one/agents.md` untouched. The unit gate was not run: nothing outside `packaging/` changed.

#### For leg 3 (`linux-briefcase`): reusing the runner
- `check.sh <candidate> <deb|appimage> <distro> <image> --n 0.11.8 --n1 0.11.9.dev1 [--pkgdir DIR]` and `score.py` are candidate-neutral; evidence goes to `$M32_EVIDENCE/<candidate>/<format>/<distro>-<image>/`. A candidate's packages must be named `gleepglorp-ai_<N>_amd64.deb` / `GleepGlorp_AI-<N>-x86_64.AppImage` (or edit the `DEB_*`/`APPIMG_*` names in `check.sh`) and must provide a `the-one` command on `PATH` that accepts `version`, `doctor`, `serve`, `app`, `rotate-api-credential`. One run takes 1.5-3 minutes (bare .deb: apt dominates).
- Under Briefcase `is_frozen()` is false, so `doctor` gates read `skipped`, which `score.py` scores FAIL by design. Run `doctor` pinned and unpinned exactly as here (it needs `xvfb-run`).
- Gate 3 identifies the UI process as a `the-one` process with `libgtk-3` mapped; under Briefcase the process name may differ (adjust the `grep 'the-one'` in `find_ui` in `inner.sh`).

### linux-briefcase
**Status**: landed
**Started**: 2026-10-23
**Landed**: 2026-10-23

#### Changes Made
- `packaging/briefcase/` (new, 6 files plus 2 patch diffs, 275 lines): `pyproject.toml.in` (57), `build.sh` (85), `run-gates.sh` (16), `probe.sh` (45), `README.md`, `patches/01-bare-start-opens-window.diff` (17), `patches/02-briefcase-counts-as-frozen.diff` (55).
- Candidate-neutral harness change: `packaging/spike/check.sh` gained optional `--pkg-n FILE --pkg-n1 FILE` (package-file names for N and N+1, for per-distro `.deb` names); with neither flag the old default names apply, so A's runs are unchanged. Re-run proof: `check.sh A-recheck deb ubuntu-26.04 baseline` -> `G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=PASS single=PASS` (same as leg 2). `packaging/spike/README.md` mentions the flags. `inner.sh` and `score.py` unchanged.
- Nothing changed under `the_one/`, `tests/`, `.github/`, `ci/`, `pyproject.toml`, `uv.lock`, `CLAUDE.md` or `the_one/agents.md`.
- Briefcase **0.4.6** (PyPI 2026-10-13, 10 days old: under the usual 14-day soak, taken because the design review read exactly this version) in its own tool venv `$M32_BUILD/venv-briefcase` (CPython 3.12). Template cloned from GitHub at build time (`briefcase-linux-system-template`, branch `v0.4.6`).
- Packages (not committed), `$M32_BUILD/packages-briefcase/` (`SHA256SUMS` beside them), final = patched:

```
the-one_0.11.8-1~ubuntu-resolute_amd64.deb         116241814  0b1f8556...72c0
the-one_0.11.8-1~debian-trixie_amd64.deb           111495928  36ab8cb2...9117
the-one_0.11.9.dev1-1~ubuntu-resolute_amd64.deb    116241698  a07705da...201b
the-one_0.11.9.dev1-1~debian-trixie_amd64.deb      111493584  e30136c0...94bc
```
  The unpatched N+1/N builds (hashes in `packages-briefcase-unpatched/SHA256SUMS`) were measured first and kept: `the-one_0.11.9.dev1-1~ubuntu-resolute` 116234210 bytes, `~debian-trixie` 111495956.
- Evidence roots under `$M32_EVIDENCE`: `B-unpatched/` and `B-patched/` (`deb/<distro>-<image>/` from `check.sh`, `probe/<distro>/` from `probe.sh`), `B/ac0-probe.txt`, `B/build-logs/` (Briefcase create/build/package logs, AppImage failure logs), `A-recheck/`.

#### AC0 - `allow_subprocesses = true` (the leg's premise is wrong for 0.4.6: it is in the config but has NO effect)
- `allow_subprocesses = true` is in `pyproject.toml.in` and Briefcase accepts it. In the installed app (probe module run through the launcher with `BRIEFCASE_MAIN_MODULE=m32probe`, `B/ac0-probe.txt`), on both distros:

```
sys.executable='/usr/bin/the-one' exists=True     (NOT /usr/bin/python3.<minor>)
sys.frozen='<absent>'  hasattr(_MEIPASS)=False
sys.prefix='/usr' base_prefix='/usr'  argv=['the-one', ...]
version 3.14.4 (ubuntu-26.04) / 3.13.5 (debian-13)
is_frozen=False bundle_dir=None resolve_python='/usr/bin/the-one'
```
- Why: the system template's `bootstrap/main.c` does `PyConfig_SetBytesString(&config, &config.executable, exe_path)` with `exe_path = realpath("/proc/self/exe")` unconditionally; `grep allow_subprocesses` finds nothing in the generated bundle. The design review's reading was wrong. Consequence: unpatched, `resolve_python()` returns the launcher, so `python_exec`, MCP stdio spawns and the shell tool would re-launch the app (G2 below). `PYTHONPATH` and `sitecustomize` are ignored (isolated config, `site_import=0`), so the probe uses `BRIEFCASE_MAIN_MODULE`, which is also the only way to change the main module.

#### AC1 - build from shared staging, pinned closure (met)
- `build.sh` runs `stage.py --candidate briefcase` (patches applied to the staged copy: `applied 01-... applied 02-...`), then builds from `$M32_BUILD/stage-briefcase-<ver>/`. `the-one version` in the installed `.deb` (`version-N.txt`, `version-N1.txt` in every evidence dir): `GleepGlorp AI v0.11.8` and `GleepGlorp AI v0.11.9.dev1`. Briefcase prints `briefcase 0.4.6` first in the build log.
- Closure: hashes kept. `requires = ["-r", "./closure.txt"]` plus `requirement_installer_args = ["--no-deps", "--require-hashes"]`: Briefcase copies a path-like requirement into the bundle (`/app/_requirements/closure.txt` inside the container), and pip verified every hash (log: `Collecting pyjwt==2.15.1 (from -r /app/_requirements/closure.txt (line 1104))`). A `requires` entry is one pip argument and cannot carry `--hash`, so the `-r` route is the way. `--no-deps` is needed: the first run died with `In --require-hashes mode, all requirements must have their versions pinned: hf-xet<2.0.0,>=1.5.2 (from huggingface-hub==1.30.0)` because the lock leaves out that optional dep; A installs with `uv pip install --no-deps`, so this is parity, not a weakening. No version deviation.
- `git status --porcelain -- the_one/ pyproject.toml uv.lock`: empty.

#### AC2 - a system `.deb` per target (met: four files)
- Names above. Package name `the-one`, `Version: 0.11.9.dev1` (and `0.11.8`); filename adds `-1~<vendor>-<codename>`. `dpkg --compare-versions 0.11.9.dev1 gt 0.11.8` true (A's `0.11.9~dev1` sorts BELOW `0.11.9`, B's `0.11.9.dev1` sorts ABOVE it: a naming point for Flight 2).
- `dpkg-deb -I` (N+1):
  - ubuntu-26.04: `Depends: libc6 (>=2.43), libpython3.14, python3, libwebkit2gtk-4.1-0, gir1.2-webkit2-4.1, gir1.2-gtk-3.0, libgirepository-2.0-0, gir1.2-ayatanaappindicator3-0.1, libcairo2`
  - debian-13: `Depends: libc6 (>=2.41), libpython3.13, python3, <same list>`
  - System Pythons: 3.14.4 (ubuntu-26.04, GCC 15.2.0), 3.13.5 (debian-13, GCC 14.2.0).
  - The libc6 floor is the build container's glibc, so each `.deb` is tied to its distro (A's one `.deb` needed glibc 2.34).
- Build times (wall, `times.txt`): cold (Briefcase's Docker image built and template cloned) **ubuntu:26.04 105 s, debian:13 223 s**; warm (image cached) **69-74 s per target** (both versions). Cold ubuntu was made by `docker rmi briefcase/ai.gleepglorp.the-one:ubuntu-resolute` and rebuilding (Briefcase's own image name; the debian image's first build was the other cold number). Briefcase images left in Docker: `briefcase/ai.gleepglorp.the-one:ubuntu-resolute` 1.73 GB and `...:debian-trixie` 1.98 GB.
- pip outcome per target (`B/build-logs/<target>-create.log`): everything installs from wheels (cp314 on 26.04, cp313 on 13, abi3 wheels for tokenizers/safetensors) EXCEPT four sdists built in the container: `pycairo 1.29.0`, `pygobject 3.56.3`, `pygobject-stubs 2.17.0`, `proxy-tools 0.1.0` (the last two are pure Python). pycairo and PyGObject compile against `libcairo2-dev` and `libgirepository-2.0-dev` from `system_requires`; no failure on either distro.

#### AC3 - the desktop entry opens the window (met, with patch 01)
- `.desktop` in the `.deb`: `Exec=/usr/bin/the-one %F`, `Icon=ai.gleepglorp.the-one`, file `ai.gleepglorp.the-one.desktop` (`probe/<distro>/desktop-exec.txt`). Fixed by the template: not configurable.
- Unpatched, a bare `/usr/bin/the-one` (what `Exec` runs with no files) starts the terminal chat: `bare-launch.log` shows the Rich banner, "No provider configured...", no server on 8490, no window (`B-unpatched/probe/*/bare-state.txt`: `live=` empty, `window id: none`).
- Patched (`01-bare-start-opens-window.diff`: `if not args:` runs `app`; `chat` is its own branch): bare `/usr/bin/the-one` serves (`live={"status":"ok"}`), `POST /api/window/focus` -> `{"focused":true}`, the window "GleepGlorp AI" is viewable on the forwarded X display, and two `WebKitWebProcess` children run from `/usr/lib/x86_64-linux-gnu/webkit2gtk-4.1/` (`B-patched/probe/ubuntu-26.04/{bare-state.txt,window.png}`; on debian-13 `xwd` of the window gives `BadMatch`, the known WSLg limitation from leg 2, so its picture is the one from `check.sh`'s `app` run in `B-patched/deb/debian-13-baseline/window.png`).
- Effect of the patch: bare `the-one` no longer opens the terminal chat (`the-one chat` still does). Options considered: (a) a custom template (a forked `.desktop`/launcher, so Flight 2 would own a template fork); (b) post-processing the `.desktop` after `briefcase create` to `Exec=/usr/bin/the-one app %F` (a build-script edit, no app patch, but then `the-one` on a shell still opens chat, and it edits generated output); (c) the DD4 patch, chosen as the Flight Director allowed. Config alone cannot do it: `Exec`, the module and the launcher args are fixed in 0.4.6 (the module only by the `BRIEFCASE_MAIN_MODULE` environment variable, which a `.desktop` cannot set).

#### AC4 - gates 1 and 2, unpatched then patched (met)
- **Unpatched** (`B-unpatched`, four runs): G1 pinned PASS, G1 unpinned PASS (every gate printed OK; `frozen: False`; the strict "no skipped" rule never trips because the non-frozen branches only print "skipped" when an import FAILS, and every import succeeded: `desktop shell`, `llm providers`, `model catalog`, `usearch`, `file watcher: native change notification round-trip OK`). So DD2's expectation that G1 fails by design under Briefcase did NOT happen on these builds; G1 passes unpatched. **G2 FAIL on all four**: `doctor` prints `python interpreter: OK — resolved to /usr/bin/the-one` (its own gate always passes when not frozen), and running it with `-c` prints the app's usage text (`gate2.txt`). The independent measurement is what catches it.
- **Patched** (`02-briefcase-counts-as-frozen.diff`, with 01): `is_frozen()` also returns true when `<exe dir>/../lib/<exe name>/app_packages` is a directory (Briefcase's installed layout: `/usr/lib/the-one/app_packages` beside `/usr/bin/the-one`; `lru_cache`d); `_bundle_dir()` returns `None` for it (the launcher dir is `/usr/bin`; the stock fallback would strip `/usr/bin` from the child `PATH`). No check is skipped: G1 now sees `frozen: True` and the frozen-only hard gates run (desktop shell, LLM providers, model catalog, usearch, file watcher round-trip all OK; the only `skipped` is `window chrome ... skipped (not Windows)`). G1 pinned/unpinned PASS on all four, **G2 PASS**: `resolved: /usr/bin/python3.14`, `/usr/bin/python3.14 /usr`, `Python 3.14.4` (ubuntu); `/usr/bin/python3.13 /usr`, `Python 3.13.5` (debian).
- Patched vs unpatched on the same package (`probe/<distro>/ac4-path.txt`): child `PATH` unpatched `/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`; patched the same entries in the same order, with `/opt/homebrew/bin`, `~/.local/bin`, `~/.cargo/bin`, `~/.npm-global/bin` appended (the intended frozen augmentation). `/usr/bin` is NOT stripped. `.env` location: unpatched `.env` (CWD-relative); patched `/home/t/.local/share/the-one/.env` (the frozen path, the data dir). `resolve_python()`: `/usr/bin/the-one` -> `/usr/bin/python3.14` / `python3.13`.
- Cost of the patch: 2 files and 55 lines in `the_one/`, not a one-liner; and `is_frozen()`'s other readers change with it (the `.env` anchoring, the shell resolution, the doctor's hard gates), which is intended, but Flight 2 must write it with tests.

#### AC5 - gates 3, 4, upgrade, single-instance on the final (patched) build (met)
```
B-patched deb/ubuntu-26.04-baseline: G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=PASS single=PASS
B-patched deb/ubuntu-26.04-bare:     G1p=PASS G1u=PASS G2=PASS G3=N/A  G4=PASS upgrade=PASS single=N/A
B-patched deb/debian-13-baseline:    G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=PASS single=PASS
B-patched deb/debian-13-bare:        G1p=PASS G1u=PASS G2=PASS G3=N/A  G4=PASS upgrade=PASS single=N/A
B-unpatched (same runs, before the patches): G1p/G1u/G3/G4/upgrade/single as above, G2=FAIL on all four
```
- G3: UI process maps exactly one `libglib-2.0`, `libgobject-2.0`, `libgtk-3`, `libgirepository-2.0`, `libwebkit2gtk-4.1`, `libstdc++`, `libgcc_s`, all under `/usr/lib`; 2 `WebKitWebProcess` checked per baseline run. No bundled GTK stack exists to leak: the `.deb` carries only Python packages. The UI process is `the-one app` (matches `inner.sh::find_ui` unchanged).
- G4: `Local API credential created at /home/tester/.local/share/the-one/api-credential (mode 0600).`, `serve` live, dir listing as A's. Upgrade: N -> N+1 versions read back, `m32-upgrade-agent` read back, credential prefix unchanged. Single-instance: second launch exits in 0.83 s (ubuntu baseline), 1 listener, `{"focused":true}`.
- `apt install ./the-one_...deb` pulled every dependency on the bare images (ubuntu 145 packages, 20 s; debian 307 packages, 38 s): the declared list is complete. Tray: `gir1.2-ayatanaappindicator3-0.1` is declared, desktop shell OK pinned and unpinned (Ayatana typelib present after install). No gi-overrides gap: B installs real packages, `gi.overrides` is the host's/pip's own, and the window opened.

#### AC6 - the AppImage (FAIL: does not build)
- The pinned Briefcase still offers the format (`briefcase package linux --help`: "Supported formats: appimage, flatpak, system"), with the warning "Use of AppImage is not recommended ... AppImages cannot use pre-compiled binary wheels, and has significant problems with most commonly used GUI toolkits (including GTK and PySide)".
- `briefcase create linux appimage --no-input` fails before any pip or Docker work, twice (`B/appimage/appimage-create.log`, `appimage-create-retry.log`): `Briefcase configuration error: Unable to create file 'briefcase.toml': 'collections.OrderedDict object' has no attribute 'host_arch'`. Cause: the AppImage template (`briefcase-linux-appimage-template`, branch `v0.4.6`, sha `b4e0e7d`, "Bump support packages", 2026-10-12) references `cookiecutter.host_arch` in `briefcase.toml`, which its `cookiecutter.json` does not define. No AppImage was produced, so no gates ran. Scored FAIL (build). Not pursued (best-effort format, template out of step with the CLI); even if it built, the manylinux base cannot hold PyGObject 3.56's `girepository-2.0`.

#### AC7 - Evidence Table rows and upkeep
See the table below.

#### AC8 - safety and forbidden paths (met)
- No instance ran on 8484 or 8485: gate and probe runs used 8490-8492 inside containers named `m32-gate-*` / `m32-probe-*` (none left: `docker ps -a | grep m32` empty); no `--privileged`, no `--network host`; Briefcase's own build containers and `briefcase/ai.gleepglorp.the-one:*` images were the only other Docker objects. All data dirs were container-local or scratch; nothing app-side ran on the host.
- `/home/cprch/.local/share/the-one` newest mtime `1791383047.9672937840` before and after (unchanged).
- `git diff --stat mission/32-installers`: only the flight log and `flight.md` under `missions/` (plus untracked `packaging/`, `legs/`); `git status --porcelain -- the_one/ pyproject.toml uv.lock` empty.
- `ruff check packaging/` and `ruff format --check packaging/` pass (7 files). The unit gate was not run: nothing outside `packaging/` and `missions/` changed (the patches live in `packaging/briefcase/patches/` and apply to the staging copy only).

#### Findings and deviations (in order found)
1. **`allow_subprocesses` does nothing on Linux system builds in 0.4.6**; `sys.executable` is always the launcher (AC0). The leg asserted otherwise; measured and recorded.
2. **DD2's "G1 fails by design" did not occur.** `score.py` flags only the word `skipped`, and the app prints it only when an import fails. Under Briefcase everything imports, so G1 passes unpatched; the real unpatched failure is G2. `doctor` itself reports `frozen: False` and approves `resolved to /usr/bin/the-one`.
3. Briefcase demands inputs the repo does not have: a license file (PEP 639 `license` + `license-files`; mixing with `license.file` is an error) and a changelog; `build.sh` writes placeholders into the staging root. A real build needs a real `LICENSE`.
4. Cold vs warm: 105/223 s vs about 70 s per target.
5. `build.sh` copied stale `dist/*.deb` from the previous target until `rm -rf dist` was added per target.
6. The AppImage template/CLI mismatch (AC6) is an upstream defect at this version; a later 0.4.x may fix it.

---

## Evidence Table

**Candidate A (PyInstaller), Linux.** Leg 2 (`linux-pyinstaller-gates`). Cells: PASS, FAIL, N/A or directional. Evidence root `E=$HOME/the-one-m32-evidence/A/<format>/<distro>-<image>/` (`score.json` in each; the table is `score.py`'s output).

| candidate / format / distro-image | G1 pinned (`PYSTRAY_BACKEND=gtk`) | G1 unpinned | G2 | G3 | G4 | upgrade | single-instance | tray | sandbox | size | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A / .deb / ubuntu-26.04-baseline | PASS (`doctor-pinned.txt`) | PASS (`doctor-unpinned.txt`) | PASS `/usr/bin/python3.14`, prefix `/usr` (`gate2.txt`) | PASS (`ui.maps`, `web-*.maps`, `window.png`) | PASS (`gate4-*.txt`) | PASS (`version-N*.txt`, `agents-N1.json`, `cred-prefix-N*.txt`) | PASS, exit in 0.52 s, 1 listener, `{"focused":true}` (`single-instance.txt`, `focus.txt`) | typelib present (declared dep); shell OK pinned and unpinned (`tray.txt`) | bwrap denied (see below) | .deb 141.1 MB | 1 apt step pulled 2 packages (baseline already has the rest) |
| A / .deb / ubuntu-26.04-bare | PASS | PASS | PASS `/usr/bin/python3.14` | N/A (no window) | PASS | PASS | N/A | typelib pulled by apt; shell OK both | bwrap denied | .deb 141.1 MB | `apt install ./x.deb` resolved every `Depends` (144 packages, 33 s): declaration complete |
| A / .deb / debian-13-baseline | PASS | PASS | PASS `/usr/bin/python3.13`, prefix `/usr` | PASS | PASS | PASS | PASS, 0.41 s, 1 listener | typelib pulled by the .deb (baseline lacks it); shell OK both | bwrap denied | .deb 141.1 MB | the .deb pulled `libgirepository-2.0-0` (6 packages), which Debian's stock desktop lacks |
| A / .deb / debian-13-bare | PASS | PASS | PASS `/usr/bin/python3.13` | N/A | PASS | PASS | N/A | shell OK both | bwrap denied | .deb 141.1 MB | 306 packages, 52 s, all `Depends` resolved |
| A / AppImage / ubuntu-26.04-baseline | PASS | **FAIL** (`desktop shell: unexpected error: Namespace AyatanaAppIndicator3 not available`) | PASS `/usr/bin/python3.14` | PASS | PASS | PASS | PASS, 0.62 s, 1 listener | typelib absent on the host; pinned `gtk` loads, unpinned raises | bwrap denied | AppImage 143.8 MB | FAIL on unpinned: "needs the host's AppIndicator typelib" (the pystray `ValueError` finding) |
| A / AppImage / debian-13-baseline | **FAIL** (`desktop shell: ... libgirepository-2.0.so.0: cannot open shared object file`) | PASS (pystray falls back, because `gi` is absent) | PASS `/usr/bin/python3.13` | **FAIL** (no window: `_webview_available` false, so server only) | PASS | PASS | **FAIL** (`{"focused":false}`, no window registered) | typelib absent; pinned `gtk` cannot load | bwrap denied | AppImage 143.8 MB | AppImage cannot declare `libgirepository-2.0-0`; Debian's stock desktop lacks it |

**Legend.** G1: `doctor` exit 0 and no `skipped` in a gate detail (window chrome's `skipped (not Windows)` excepted), by `score.py`. G2: the interpreter `doctor` resolved, run as `-c 'import sys; print(sys.executable, sys.prefix)'`, is a system Python outside `/opt/gleepglorp-ai`, `/opt/m32` and the AppImage mount. G3: `/proc/<pid>/maps` of the UI process has exactly one path each of libglib-2.0, libgobject-2.0, libgtk-3, libgirepository-2.0, libwebkit2gtk-4.1, libstdc++ and libgcc_s, all under `/usr/lib`; each `WebKitWebProcess` at most one each, all under `/usr/lib` (2 web processes measured per passing run). G4: no `THE_ONE_DATA_DIR`, `rotate-api-credential` printed `Local API credential created at /home/tester/.local/share/the-one/api-credential`, `serve` on 8491, `ls` shows `api-credential encryption.key the-one.db(-shm,-wal) vectors`. Upgrade: N=0.11.8 to N+1=0.11.9.dev1; versions read back, seeded agent `m32-upgrade-agent` read back, credential prefix unchanged. Single-instance: second `the-one app` exits 0 within 10 s, one listener on 8490, `POST /api/window/focus` answers `{"focused":true}`. Tray is not scored for visibility.

**Environment every run set.** Container run as non-root `tester` with a real `HOME`, `docker run --rm --name m32-gate-...`, no `--privileged`, no `--network host`. `PYWEBVIEW_GUI=gtk` always; `PYSTRAY_BACKEND=gtk` for the pinned runs only; `doctor` under `xvfb-run`. Window runs: `DISPLAY=:0` (WSLg's X socket forwarded at `/tmp/.X11-unix`), `GDK_BACKEND=x11`, `WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1`, `WEBKIT_DISABLE_COMPOSITING_MODE=1`, `WEBKIT_DISABLE_DMABUF_RENDERER=1`, `LIBGL_ALWAYS_SOFTWARE=1`, `THE_ONE_PORT=8490`, scratch `THE_ONE_DATA_DIR`, under `dbus-run-session`. AppImage: `APPIMAGE_EXTRACT_AND_RUN=1`. Images `m32/{ubuntu-26.04,debian-13}:{bare,baseline}`; system Pythons 3.14.4 (Ubuntu 26.04) and 3.13.5 (Debian 13).

**Screenshots** (the window itself, `xwd -id`, from the forwarded WSLg display, not directional): `A/deb/ubuntu-26.04-baseline/window.png`, `A/deb/debian-13-baseline/window.png`, `A/appimage/ubuntu-26.04-baseline/window.png` (each 1440x900, the Chats start page).

**Soft criteria for A, Linux.**
- Sizes: bundle 288 MB; AppImage 143.8 MB; .deb 141.1 MB. Cold build about 71 s (full `build.sh`, both wrappers, about 70-73 s, from leg 1).
- Upkeep: `packaging/linux/` is 529 lines in 9 files (spec 200, excludes 100, rthook 81, build.sh 68, README 51, the rest templates), plus the candidate-neutral `packaging/spike/` harness. Version lives in 3 places (the staged `__version__` rewrite, `build.sh`'s argument which sets the .deb and AppImage names, and the changelog-less `control.in` stamped by `build.sh`); the name lives in 5 files (`build.sh`, `control.in`, `.desktop.in`, `AppRun`, spec docstring). ONE .deb serves both distros (the same file passed on both). CLI: the .deb installs `/usr/bin/the-one`; the AppImage runs `the-one`-style arguments through `AppRun` (no argument starts `app`). Known recipe inputs: the build host (Ubuntu 24.04, glib 2.80 gives no gi hook output), `excludes.txt`, and the gi overrides collection (below).
- Sandbox: inside Docker `bwrap` is present but fails ("No permissions to create a new namespace"), and `doctor` has no sandbox gate, so it passes. Not representative of a desktop.
- Tray: neither stock baseline has `gir1.2-ayatanaappindicator3-0.1`. The .deb declares it (and its `bare` run proves apt pulls it). The AppImage cannot, so a stock desktop's unpinned run FAILS gate 1 on Ubuntu 26.04 and the pinned run is the only one that passes. On Debian the AppImage cannot even load `gi` (no `libgirepository-2.0`), so the pinned run fails and the unpinned one passes only because pystray falls back to its X backend.


**Candidate B (Briefcase 0.4.6), Linux.** Leg 3 (`linux-briefcase`). Same columns and legend as A. Evidence root `E=$HOME/the-one-m32-evidence/B-patched/deb/<distro>-<image>/` (patched) and `B-unpatched/` (unpatched); `probe/<distro>/` holds the AC0/AC3/AC4 probes. Patched = patches 01 (bare start opens the window) and 02 (`is_frozen()` for a Briefcase system app), applied to the staging copy only (DD4). Package names are `the-one_<ver>-1~ubuntu-resolute_amd64.deb` and `the-one_<ver>-1~debian-trixie_amd64.deb`.

| candidate / format / distro-image | G1 pinned | G1 unpinned | G2 | G3 | G4 | upgrade | single-instance | tray | sandbox | size | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B unpatched / .deb / ubuntu-26.04-baseline | PASS (`frozen: False`, no `skipped`) | PASS | **FAIL** `resolved: /usr/bin/the-one`; running it prints the app usage (`gate2.txt`) | PASS | PASS | PASS | PASS | typelib pulled by the .deb; shell OK both | bwrap denied | .deb 116.2 MB | `sys.executable` is the launcher; `resolve_python()` would re-launch the app |
| B unpatched / .deb / ubuntu-26.04-bare | PASS | PASS | **FAIL** | N/A | PASS | PASS | N/A | shell OK both | bwrap denied | 116.2 MB | apt resolved every `Depends` (145 packages) |
| B unpatched / .deb / debian-13-baseline | PASS | PASS | **FAIL** | PASS | PASS | PASS | PASS | shell OK both | bwrap denied | .deb 111.5 MB | |
| B unpatched / .deb / debian-13-bare | PASS | PASS | **FAIL** | N/A | PASS | PASS | N/A | shell OK both | bwrap denied | 111.5 MB | 307 packages |
| B patched / .deb / ubuntu-26.04-baseline | PASS (`frozen: True`) | PASS | PASS `/usr/bin/python3.14`, prefix `/usr` | PASS (one copy each, all `/usr/lib`; 2 web processes) | PASS | PASS | PASS, exit in 0.83 s, 1 listener | typelib present (declared dep); shell OK both | bwrap denied | .deb 116.2 MB | PASS with patches 01+02 |
| B patched / .deb / ubuntu-26.04-bare | PASS | PASS | PASS `/usr/bin/python3.14` | N/A | PASS | PASS | N/A | shell OK both | bwrap denied | 116.2 MB | 145 packages, 20 s |
| B patched / .deb / debian-13-baseline | PASS | PASS | PASS `/usr/bin/python3.13`, prefix `/usr` | PASS | PASS | PASS | PASS | shell OK both | bwrap denied | .deb 111.5 MB | |
| B patched / .deb / debian-13-bare | PASS | PASS | PASS `/usr/bin/python3.13` | N/A | PASS | PASS | N/A | shell OK both | bwrap denied | 111.5 MB | 307 packages, 38 s |
| B / AppImage / (any) | not run | not run | not run | not run | not run | not run | not run | not run | n/a | none | **FAIL (build)**: `briefcase create linux appimage` -> `'collections.OrderedDict object' has no attribute 'host_arch'` (template `v0.4.6` out of step with the CLI), twice; `B/appimage/*.log`. Briefcase also warns the format is "not recommended" for GTK apps |

**Screenshots for B** (same method as A, 1440x900 Chats start page): `B-patched/deb/ubuntu-26.04-baseline/window.png`, `B-patched/deb/debian-13-baseline/window.png`; the desktop-entry (bare, no arguments) launch: `B-patched/probe/ubuntu-26.04/window.png`.

**Soft criteria for B, Linux.**
- Sizes: `.deb` 116.2 MB (ubuntu-resolute), 111.5 MB (debian-trixie); A: 141.1 MB `.deb`, 143.8 MB AppImage. Build image `briefcase/ai.gleepglorp.the-one:*` 1.73-1.98 GB each on the build host. Cold build 105 s (ubuntu) / 223 s (debian) including the image and template, warm 69-74 s per target, so about 140-150 s warm for both distros against A's about 71 s for one package; A's exclude and spec tuning is B's `system_requires` list.
- Upkeep, `packaging/briefcase/`: 275 lines in 8 files (config template 57, build.sh 85, run-gates 16, probe 45, README, two patch diffs 72 lines). A's `packaging/linux/` is 529 lines in 9 files (spec 200, excludes 100, rthook 81, build.sh 68), with no app patch; B needs no spec, excludes or runtime hook (it ships no GTK stack and no frozen interpreter), but needs two DD4 patches (`the_one/main.py`, `the_one/platform/env.py`, 55 lines) that Flight 2 must turn into real, tested app changes.
- Version and name: the version lives in ONE place, the `build.sh` argument, which fills `[project]` and `[tool.briefcase]` in the generated `pyproject.toml` and the staged `__version__` (A: 3 places). The name lives in `pyproject.toml.in` (`app_name`, `formal_name`, `bundle`) and derives the package name (`the-one`), the `.desktop` file (`ai.gleepglorp.the-one.desktop`), the icon names and the install dir; no hand-kept `control`/`AppRun`/`.desktop` templates (A: 5 files). The package is `the-one`, not `gleepglorp-ai`, unless the app name changes.
- Per-distro artifacts: 2 `.deb` files (one per `--target`), each tied to its distro's Python and glibc; A's one `.deb` served both. Every added distro is a new target, a new `Depends` section if package names differ and one more Docker build. The `Depends` list cannot use `a | b` alternatives (it is pasted unquoted into a Dockerfile `apt-get` line), so t64-renamed or differently named packages need per-vendor/codename sections.
- Build image extra system requirements: `pkg-config`, `libcairo2-dev`, `libgirepository-2.0-dev`, `gobject-introspection` (compile pycairo and PyGObject 3.56 in the container); runtime: `python3`, `libwebkit2gtk-4.1-0`, `gir1.2-webkit2-4.1`, `gir1.2-gtk-3.0`, `libgirepository-2.0-0`, `gir1.2-ayatanaappindicator3-0.1`, `libcairo2`.
- CLI on `PATH`: yes, `/usr/bin/the-one` is the launcher, so `doctor`, `serve`, `version` and `rotate-api-credential` work from a shell (A's `.deb` also installs `/usr/bin/the-one`, A's AppImage does not).
- Launcher arrangement: the `.desktop` `Exec=/usr/bin/the-one %F` and the main module are fixed by the template, so opening the window needs patch 01 (bare `the-one` now opens the window, not the terminal chat) or a template fork. `sys.executable` is the launcher and `allow_subprocesses` has no effect on this template, so patch 02 is needed for `resolve_python()` (G2); without it the app would re-launch itself for every `python_exec`, shell-adjacent and MCP stdio spawn.
- Build inputs Briefcase insists on that the repo lacks: a license file and a changelog (placeholders written by `build.sh`).
- Hosted CI: a hosted Linux build of B needs Docker on the runner (GitHub's `ubuntu-latest` has it), a template clone from GitHub, about 2.5 minutes warm (about 5.5 minutes cold) for the two `.deb`s, and `uv export` plus `git`; each additional distro adds a Docker build. A needs a Python 3.11 venv, `appimagetool` and about 70 s.
- Sandbox: same as A (inside Docker `bwrap` is denied; not representative).
- Closure pinned with hashes (`-r closure.txt` + `--require-hashes`, `--no-deps`): no deviation.

---

## Decision

_(recorded at `decision-hat`)_
