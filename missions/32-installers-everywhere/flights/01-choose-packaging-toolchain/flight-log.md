# Flight Log: Choose the packaging toolchain

**Flight**: [Choose the packaging toolchain](flight.md)

## Summary
Planned 2026-10-23 in the worktree `~/projects/the-one-worktrees/m32-installers`, from `origin/main` at `8a52a39` plus the mission commit `b060d84`. Mission 31 is active in the main checkout at the same time; this flight never touches it.

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
- **`macos-probe-prepare` risk tier: high** (it spends scarce hosted minutes, and its output reaches `main`). **Design review (Developer): approve with changes.** Folded in as numbered findings in the leg:
  - B's build would fail on sdist-only `proxy-tools` under Briefcase's macOS `--only-binary :all:`; fix with `--no-binary proxy-tools`;
  - a Linux rehearsal of macOS pip resolution at three `min_os_version` tags;
  - a layered cost guard (30-minute job, 15-minute steps, in-script time limits, concurrency, a choice input);
  - one entry script for A that defaults to `app` on a bare launch;
  - macOS-specific gate 2 scoring;
  - quoting the space in B's executable name;
  - `--no-input`;
  - patch 02's macOS clause narrowed, with `_bundle_dir()` returning `None`;
  - `sys.executable` probed first.
- **`macos-probe-prepare` landed, then review checkpoint: `[HANDOFF:confirmed]`** (Sonnet Reviewer; no blocking issues). Three non-blocking fixes were applied by a Developer:
  - the job cap raised from 30 to 40 minutes (the estimate sat at the cap, and 40 lets the 15-minute step caps fire first, so the log upload is always reached);
  - a final step that fails the job on a FAIL or missing candidate summary;
  - time limits on `log show` and `screencapture`.
- **2026-10-24, the PR and the dispatch.**
  - PR #305 (`.github/`-only: the two workflow files, cut from `origin/main` in a separate worktree, `~/projects/the-one-worktrees/m32-probe-pr`, branch `m32/probe-workflows`) passed `lint`. `pip-audit` failed on a pre-existing `filelock 3.29.0` CVE on `main`, unrelated to the PR.
  - With the operator's go, it was merged anyway: squash `df30153`.
  - The filelock finding is logged as squawk 0250. Id 0250 was taken because Mission 31's uncommitted tree holds 0249; the squawk notes it.
  - **macOS run 1 dispatched:** run `40058032297`, https://github.com/msieurthenardier/the-one/actions/runs/40058032297 (`--ref flight/01-choose-packaging-toolchain`, `candidates="A B"`). It is job 1 of 2.
- **`macos-probe-run` risk tier: low** (it reads logs, and nothing is outward-facing), so no design review. It is set to `ready`.
- **The operator is away overnight (2026-10-24)** and asked for autonomous progress until needed. A second macOS dispatch, if warranted, waits for the operator. The `decision-hat` leg and the operator's Windows install (`windows-cost`) need the operator. The hosted Windows MSI build is within the approved flight plan (DD7, one Windows job) and proceeds autonomously if the minutes allow.
- **The operator delegated decisions overnight** ("feel free to make decisions, we can align if needed tomorrow"). The Flight Director makes the calls, logs each one here, and raises them at the morning alignment. Limits kept regardless:
  - at most 2 macOS jobs and 1 Windows job;
  - nothing installed on the operator's PC;
  - no release;
  - no further change to `main`.
- **`windows-cost` designed; risk tier high** (it produces an installer the operator will run on their real machine, and spends hosted minutes), so it gets a Developer design review. Its autonomous part stops at `[HANDOFF:review-needed]` for review, commit, push and dispatch. The operator's real-machine install is a morning step, outside its acceptance.
- **`macos-probe-run` landed.**
  - Run 1: B passed every hard check on macOS. A died at its icon step (`$WORK` missing, a one-line recipe defect), so none of A's checks were reached.
  - Flight Director call, under the operator's overnight delegation: **dispatched run 2 (the last macOS job) with `candidates="A"` only**, since B's row is complete. Run `40058513153`, https://github.com/msieurthenardier/the-one/actions/runs/40058513153. Expected 80-120 billed minutes.
  - The fix (`mkdir -p "$WORK"`, plus a cosmetic NSLog filter in the summary lines) was checked by the Flight Director and committed at `2b5c543` without a separate Reviewer pass: a one-line correction, covered again by the flight-end review.
  - `macos-probe-run` stays `landed` until a follow-up pass records run 2.
- **`windows-cost` design review (Developer, from Briefcase 0.4.6 source): approve with changes.** Folded in as ten findings. Flight Director calls, under the overnight delegation:
  - **a per-user MSI** (`system_installer = false`, with `MSIINSTALLPERUSER=1 ALLUSERS=2`), so it cannot land in Inno's `Program Files` directory;
  - the MSI is built at `0.11.9.dev1`;
  - `stage.py` changes in this leg (`git apply` on `win32`);
  - the MSI and its hash are uploaded before the upgrade scenario;
  - the operator's guide is rewritten: quit before backup, PowerShell syntax, `msiexec /x <file>` rollback, the SHA-256 check, and an explicit-variable restore.

  No second review (these are the reviewer's own fixes). Set to `ready`.

  The Flight Director checked the triggers and caps, then committed. The operator approved (2026-10-23) the push, the `.github/`-only PR to `main`, its merge after `pr-lint`, and one macOS dispatch building both candidates, and confirmed the minutes budget. A second dispatch needs the operator's go.

  The billing API is unreadable without the `user` scope, so the operator confirms minutes before dispatch. No second review: these are the reviewer's own specified fixes. Set to `ready`.

  No second review (Flight Director call): the changes are the review's own specified fixes. Set to `ready`.



- **`windows-cost` autonomous half: `[HANDOFF:review-needed]`. Review checkpoint (Sonnet; the env seam patch): `[HANDOFF:confirmed]`, no blocking issues.** The Flight Director applied guide notes 3 and 4 itself (artifact text): re-define the restore variables in a new session, and warn that the MSI build may migrate the real database, so a rollback restores the backup.
  - Note 1 (a step cap firing reads green in the final step) is accepted: the Flight Director reads per-step conclusions.
  - Note 2 (patch 02's Windows marker could be stricter) is carried to Flight 2.
  - Commit, push, then dispatch the single Windows job (`candidates="B"`).
- **Windows run 1 (`40060053657`) built no MSI.** A recipe defect: PowerShell's case-insensitive `$log` overwrote `$LOG` in `build-windows.ps1`, after `briefcase create` had succeeded. Flight Director call, under the overnight delegation: **one retry Windows job**, beyond DD7's single job. Category (a), the fix is contained, and the job is cheap at the 2× rate (run 1 cost about 5 billed minutes). The fix (a renamed loop variable; `Invoke-Capped` creates a missing output dir) was checked by the Flight Director and committed without a separate Reviewer pass, as one-line corrections covered by the flight-end review.
- **Windows retry (`40060408672`) recorded** by a Developer follow-up pass (`[HANDOFF:review-needed]`).
  - B's per-user MSI builds, installs, passes strict `doctor`, serves and uninstalls cleanly, and coexists with the Inno install rather than replacing it.
  - Three checks (gate 4, and both seeded-data checks) were not measured, because of a harness defect: `Use-EnvVars` left variables set to empty strings. The fix is in `windows-lib.ps1`, unverified, since no further Windows run is planned (Flight Director call: the decision does not need it).
  - Hosted minutes used in the whole flight: macOS about 5 job-minutes (about 50 billed), Windows about 11 job-minutes (about 22 billed).
- **Flight Director's decision brief** is written in the Decision section (recommendation: A, PyInstaller everywhere with Inno kept). `macos-probe-run` and `windows-cost` are set to `completed`. The operator's MSI try moves into `decision-hat` as an optional step. `decision-hat` is `ready` and needs the operator.
### linux-pyinstaller-build
**Status**: landed
**Started**: 2026-10-23
**Landed**: 2026-10-23
- **`decision-hat` (2026-10-24):**
  - The operator decided: **PyInstaller everywhere, Inno kept; the AppImage bundles the AppIndicator and girepository libraries.** The overnight calls stand.
  - The MSI try and the Linux window walk were skipped.
  - DD8 was applied: B's files were removed by a Developer, and the Flight Director edited the mission, the BACKLOG and the Decision section.
- **Flight-end review (Haiku; no security-sensitive surface remains once B's env-seam patches are removed): `[HANDOFF:confirmed]`**, no blocking issues.
  - Low items fixed: the leg 07 status, and a skip note under `windows-cost`.
  - Accepted: the Windows stub's comment ("Leg windows-cost fills in…") is now stale, but must stay byte-identical to `main`'s copy. Flight 4 replaces or removes the stub. A cosmetic long comment line in the macOS workflow is left as is.
  - Unit tests: not re-run. Nothing under `the_one/` or `tests/` changed across the flight, and leg 01 recorded `make test-unit` at 6783 passed / 12 skipped. Browser gate: not run, since no app code changed.
- **Flight landed.** Seven legs complete; status `landed`. The debrief is next (`/mission-control:flight-debrief`).
- **Debrief (2026-10-24)**, in `flight-debrief.md`. Squawk 0251 (the CPython 3.11 unit failures) was logged on the operator's go. The operator confirmed that the flight is `completed`, and that "continue autonomously" is the standing Flight Director mode when they hand over.

#### Changes Made
- `packaging/spike/` (candidate-neutral): `stage.py`, `images/{ubuntu-26.04,debian-13}.Dockerfile` (targets `baseline` and `bare`, each with a final observe layer), `README.md` (says spike tooling, not product).
- `packaging/linux/`: `the-one.spec`, `rthook_host_gtk.py`, `excludes.txt`, `build.sh`, `AppRun`, `gleepglorp-ai.desktop.in`, `control.in`, `README.md` (pinned tools and checksums). `patches/` is empty: no app-side patch was needed to freeze or start.
- Build outputs, all outside the repo: `$M32_BUILD=$HOME/the-one-m32-build` (bundles, `packages/`, `venv-pyi/`, `tools/`), evidence in `$M32_EVIDENCE=$HOME/the-one-m32-evidence`.
- Nothing changed under `the_one/`, `tests/`, `.github/`, `ci/`, `pyproject.toml` or `uv.lock`; CLAUDE.md and `the_one/agents.md` untouched (shared with Mission 31).
- Operator default data dir (read, not guessed; leg 2 uses it for its safety check): `~/.local/share/the-one`.

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
- The operator's default data dir `~/.local/share/the-one`: newest mtime `1791383047.9672937840` before and after (unchanged).
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
- `~/.local/share/the-one` newest mtime `1791383047.9672937840` before and after (unchanged).
- `git diff --stat mission/32-installers`: only the flight log and `flight.md` under `missions/` (plus untracked `packaging/`, `legs/`); `git status --porcelain -- the_one/ pyproject.toml uv.lock` empty.
- `ruff check packaging/` and `ruff format --check packaging/` pass (7 files). The unit gate was not run: nothing outside `packaging/` and `missions/` changed (the patches live in `packaging/briefcase/patches/` and apply to the staging copy only).

#### Findings and deviations (in order found)
1. **`allow_subprocesses` does nothing on Linux system builds in 0.4.6**; `sys.executable` is always the launcher (AC0). The leg asserted otherwise; measured and recorded.
2. **DD2's "G1 fails by design" did not occur.** `score.py` flags only the word `skipped`, and the app prints it only when an import fails. Under Briefcase everything imports, so G1 passes unpatched; the real unpatched failure is G2. `doctor` itself reports `frozen: False` and approves `resolved to /usr/bin/the-one`.
3. Briefcase demands inputs the repo does not have: a license file (PEP 639 `license` + `license-files`; mixing with `license.file` is an error) and a changelog; `build.sh` writes placeholders into the staging root. A real build needs a real `LICENSE`.
4. Cold vs warm: 105/223 s vs about 70 s per target.
5. `build.sh` copied stale `dist/*.deb` from the previous target until `rm -rf dist` was added per target.
6. The AppImage template/CLI mismatch (AC6) is an upstream defect at this version; a later 0.4.x may fix it.

### macos-probe-prepare
**Status**: landed
**Started**: 2026-10-23
**Landed**: 2026-10-23

#### Changes Made
- `packaging/macos/` (new): `the-one.spec` (A's `BUNDLE`, `GleepGlorp AI.app`), `frozen_entry_mac.py`, `make-icns.py`, `build.sh`, `README.md`.
- `packaging/briefcase/`: `pyproject.toml.in` gained `[tool.briefcase.app.the-one.macOS]` (+ `.info`); patch 02 gained a macOS clause; `build-macos.sh`, `check-env-layouts.py` (faked-layout check) and `macos-resolution-rehearsal.py` (pip rehearsal) are new; README gained a macOS section.
- `packaging/spike/`: `macos-checks.sh` (shared per-`.app` checks), `m32probe.py` (stub probe module, a lint-clean copy of the one leg 3 used); `stage.py` applies the diffs with `git apply` on darwin only (macOS ships BSD `patch`, which may lack GNU's `--no-backup-if-mismatch`; the Linux path is unchanged; both patches were proven to give a byte-identical tree under `git apply` and `patch`).
- `.github/workflows/packaging-probe-macos.yml` (complete) and `packaging-probe-windows.yml` (stub). Nothing else outside `packaging/`, `.github/workflows/` (those two files) and `missions/` changed. No push, PR, dispatch or commit.
- Tools (checksums in `$M32_BUILD/tools/SHA256SUMS`): actionlint 1.7.7 linux_amd64 `023070a287cd8cccd71515fedc843f1985bf96c436b7effaecce67290e7e0757`, shellcheck 0.10.0 linux.x86_64 `6c881ab0698e4e6ea235245f22832860544f17ba386442fe7e9d629f8cbedf87`. Scratch for the rehearsal: `$HOME/the-one-m32-build/macos-rehearsal/`.

#### Decisions
1. **A's Finder launch: one entry script** (`frozen_entry_mac.py`): ignoring `-psn_*`, an empty argv becomes `app`; anything else is the CLI unchanged, so `Contents/MacOS/the-one doctor|serve|version` still work for the checks. `console=False` + `ensure_stdio_streams()`. Recipe upkeep, not an app patch. Side effect, noted in the README: bare `the-one` in a shell also opens the window.
2. **Python versions.** Both candidates run on the runner's `setup-python` 3.11 (A freezes on it; Briefcase's macOS support package follows the Python that runs Briefcase, so B's app is 3.11; the template pins support revision 10 for 3.11, checked in the v0.4.6 template's `briefcase.toml`). Linux B ran 3.13/3.14 (distro Python); this is a difference to log for Flight 2.
3. **B must be `universal_build = false`** (not in the leg text; found in Briefcase 0.4.6's `macOS/__init__.py::_install_app_requirements`). The default does a second install pass for x86_64 with bare `name==version` pins, which `--require-hashes` would refuse ("requirements without hashes"). The runner is arm64, so one slice.
4. **`requires` by absolute path on macOS.** On Linux Briefcase copies `-r ./closure.txt` into the container; on macOS `requires` goes straight to `pip` (cwd-relative), so `build-macos.sh` writes the absolute staged path.
5. **Patch 02, macOS clause** (leg finding 8): `_is_briefcase_macos_app()` is true when `sys.executable`'s parent is named `MacOS` AND `../Resources/app_packages` is a directory; `is_frozen()` gains one `or` line; `_bundle_dir()` returns `None` there (a Briefcase macOS stub's `Contents/MacOS` holds nothing to strip, as `/usr/bin` on Linux), which supersedes the leg Context's "return `Contents/MacOS`". The new patch is the old one plus added lines only; the only "changed" lines are the two hunk headers' counts:

```
$ diff 02-old.diff 02-new.diff | grep '^<'
< @@ -152,14 +153,32 @@
< @@ -175,6 +194,9 @@
```
   (no Linux hunk content line removed or altered; the added lines are the new function, one `or _is_briefcase_macos_app()` line in `is_frozen()` and a 3-line `if` in `_bundle_dir()`).
6. **Cost guard (finding 3), as built:** job `timeout-minutes: 30`; each candidate step 15; `concurrency: packaging-probe-macos` with `cancel-in-progress: false`; `candidates` is a `choice` (`"A B"`, `"A"`, `"B"`); inside the scripts `doctor` (240 s), `serve` (240 s alarm, 60 s start-up wait), `hdiutil` (300 s, one retry), `version` and the interpreter run (60 s) go through `perl -e 'alarm ...; exec @ARGV'`; `serve` runs in the background with an EXIT trap that stops it by recorded PID. Permissions `contents: read`; no `secrets.`; the only upload is the logs directory (`retention-days: 7`), never a `.app` or `.dmg`.
7. **macOS bash is 3.2:** `"${extra[@]}"` of an empty array is an unbound-variable error under `set -u` there, so `build-macos.sh` uses `${extra[@]+"${extra[@]}"}`; no `[[`, `mapfile` or case-folding expansions anywhere.
8. **B's `doctor`/stub output** might be swallowed by a GUI stub (unconfirmed); if `version` prints nothing, `macos-checks.sh` saves the unified-log tail (`unified-log.txt`) for leg 5.
9. **Best-effort extra (unscored):** `macos-checks.sh` also does one Finder-style `open -n --env ... "$APP"` (no arguments), polls `/api/live`, posts `/api/window/focus`, takes a `screencapture`, and stops the app by the PID that owns port 8490. It answers "does a double-click choose `app`" for both candidates at no extra job.

#### macOS pip resolution (AC4, B's install exactly as Briefcase 0.4.6 runs it)
Briefcase passes `--platform macosx_<min_os>_arm64 --only-binary :all:` then the extra args (`create.py`/`virtual_environment/base.py`). The rehearsal (`macos-resolution-rehearsal.py`, `pip download --dest ... --platform ... --python-version ... --implementation cp --only-binary :all: --no-binary proxy-tools --no-deps --require-hashes -r closure`) first evaluates every environment marker as macOS arm64 (pip on Linux would drop `pyobjc-*` and keep `pygobject`), leaving 90 pins (12 dropped by marker), and strips the evaluated markers. Evidence: `macos-rehearsal/result-py3.11.txt`, `result-py3.12.txt`.

```
macosx_11_0_arm64 py3.11: rc=0 files=90     macosx_11_0_arm64 py3.12: rc=0 files=90
macosx_12_0_arm64 py3.11: rc=0 files=90     macosx_12_0_arm64 py3.12: rc=0 files=90
macosx_14_0_arm64 py3.11: rc=0 files=90     macosx_14_0_arm64 py3.12: rc=0 files=90
macosx_10_9_arm64 py3.11: rc=1   ERROR: Could not find a version that satisfies the requirement cffi==2.0.0   (negative control)
```
- **Chosen `min_os_version = "11.0"`:** the lowest tag at which the closure resolves (arm64 itself starts at 11.0; `cffi` has no arm64 wheel below it). 3.11 is the runner's Python for B and for A; 3.12 is recorded because the staged venvs on this host use it.
- **A** installs natively on the runner (`pip install --require-hashes --no-deps`, not `--platform`), so the same 3.11 result covers it; the macOS runner's own tag (`macosx_15_0_arm64`) accepts every wheel found at `11_0`.
- **`proxy-tools` (finding 1):** sdist-only (`proxy_tools-0.1.0.tar.gz`). Without `--no-binary proxy-tools`: `ERROR: No matching distribution found for proxy-tools==0.1.0` (proved). With it: resolves, and its sdist hash is already in the hashed closure, so `--require-hashes` holds: **the fallback (a pure wheel via `--find-links`, dropping it from the hashed file) was not needed.** `pip wheel` of the sdist builds `proxy_tools-0.1.0-py3-none-any.whl`.
- **Full install rehearsal:** the actual Briefcase command (`pip --python <venv> install --no-user --upgrade --target T --platform macosx_11_0_arm64 --only-binary :all: --no-deps --require-hashes --no-binary proxy-tools -r closure`) ran to completion on Linux for both Pythons (`target311`: 193 entries, 255 MB installed, `numpy/_core/_multiarray_umath.cpython-311-darwin.so`, `objc`, five `pyobjc-*` dist-infos, `usearch`, `proxy_tools`).
- Caveat (not testable on Linux): wheels for the `x86_64` slice are not needed (`universal_build = false`); `uv`'s resolver is not involved (Briefcase's default env manager is `venv`/pip).

#### Rehearsal results (AC4)
- `actionlint` 1.7.7 with `-shellcheck` 0.10.0 on both workflows: clean. (It caught one real defect first: `runner` context is not allowed in a job-level `env`; the paths are now set in a first step through `GITHUB_ENV`.) YAML parse (PyYAML): both have only `workflow_dispatch`, `candidates` is `type: choice`.
- `bash -n` and `shellcheck -x` on `packaging/macos/build.sh`, `packaging/briefcase/build-macos.sh`, `packaging/spike/macos-checks.sh`: clean. `py_compile` on the spec, entry, `make-icns.py`, the two Linux-side checks, `stage.py`, `m32probe.py`: clean. `ruff check packaging/` and `ruff format --check packaging/`: pass.
- `stage.py --candidate briefcase`: both patches apply (`applied 01-...`, `applied 02-...`); staged with `--candidate macos`: no patches. Config: Briefcase's own `parse_config(..., platform="macOS", output_format="app")` on the generated `pyproject.toml` merges the macOS section (`universal_build False`, `min_os_version 11.0`, the three installer args, `info {NSHighResolutionCapable: True}`, `allow_subprocesses True`).
- Faked layouts (`check-env-layouts.py`, output in `macos-rehearsal/faked-layout.txt`):

```
ok   macos-app: frozen=True bundle=None            (strip_path unchanged=True; clean_path = given PATH + runtime dirs appended)
ok   linux-system: frozen=True bundle=None
ok   source-install: frozen=False bundle=None
ok   macos-shaped-not-MacOS: frozen=False bundle=None   (Other.app/Contents/Elsewhere/<stub> with Resources/app_packages)
ok   macos-no-app_packages: frozen=False bundle=None    (Bare.app/Contents/MacOS/<stub>, no Resources/app_packages)
RESULT PASS
```
- A's spec ran through PyInstaller 6.22.3 Analysis/COLLECT on Linux against a staged macOS copy (rc 0, version `0.11.8` printed from the staged tree; the `gi` tracebacks in that log are the Linux venv's hooks, absent on a Mac; `BUNDLE` is a no-op off macOS). The `.icns` writes with Pillow (1.2 MB, 16-512 px).
- `macos-checks.sh` dry run on Linux with shim `codesign`/`sw_vers`/`plutil`/`ditto`/`open`/`log` and a fake `.app` (a stand-in executable replaying a real `doctor` capture and serving `/api/live`): ran end to end for labels A and B, `exit=0`, all six hard checks PASS. The dry run found one real bug (gate 2 passed for a non-existent interpreter), fixed: gate 2 now requires the resolved interpreter to run.
- Per-candidate command listing (what the workflow executes; `$M32_VERSION` is `__version__` read from the checkout):

```
common   : checkout; mkdir logs; sw_vers/uname/xcodebuild/df; setup-python 3.11;
           pip install uv==0.10.0; uv export --frozen --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt > requirements-closure.txt
A  (15 min cap, continue-on-error): bash packaging/macos/build.sh $M32_VERSION
   = stage.py --candidate macos; python3 -m venv; pip install --require-hashes --no-deps -r closure; pip install pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.8;
     make-icns.py; pyinstaller --noconfirm --clean packaging/macos/the-one.spec; codesign --force --deep -s - "GleepGlorp AI.app";
     hdiutil create -volname "GleepGlorp AI" -srcfolder ... -format UDZO (x2 max, 300 s each); macos-checks.sh A
B  (15 min cap, continue-on-error): bash packaging/briefcase/build-macos.sh $M32_VERSION
   = python3 -m venv; pip install briefcase==0.4.6 pillow; stage.py --candidate briefcase; make-icns.py; fill pyproject.toml (absolute closure path);
     briefcase create macOS app --no-input -v; briefcase build macOS app --no-input -v; briefcase package macOS app --no-input -v --adhoc-sign --no-notarize; macos-checks.sh B
checks   : codesign -dv; codesign --verify --deep --strict -vv; layout/size/plutil; (B) stub probe on a copy; version; doctor (240 s) -> score_doctor;
           gate 2 (resolved interpreter run, no ".app/" or "Contents"); serve :8490 + /api/live (scratch THE_ONE_DATA_DIR); rotate-api-credential (default dir);
           best-effort `open -n` (no args) + focus + screencapture
final    : summary to GITHUB_STEP_SUMMARY; upload logs (7 days)
```

#### Dispatch command (for the Flight Director, after the `.github/`-only PR is merged to `main`)
`gh workflow run packaging-probe-macos.yml --ref flight/01-choose-packaging-toolchain -f candidates="A B"`
Estimated job: setup 2-3 min; A about 9-13 min (closure install, PyInstaller on 3 cores, dmg, checks); B about 10-14 min (venv, template/support download, install, signing of every Mach-O, dmg, checks): **roughly 22-30 min, so the 30-minute job cap is tight if both are slow** (a candidate step is cut at 15 min regardless, and the log upload still runs). Billed at 10x, a full run is up to ~300 billed minutes; confirm the budget first.

#### Paper items (DD6; for Flight 3)
1. **`/usr/bin/python3` on a fresh Mac is the Xcode command-line-tools stub** (prints an install prompt and exits). `the_one/platform/interpreter.py::_is_store_alias` (line 90) is purely Windows: it checks for a `Microsoft\WindowsApps` parent via `PureWindowsPath`, and `_resolve_frozen_python` (line 105) only calls it for the bare-name search (line 131). On macOS, `shutil.which("python3")` on the cleaned PATH can return `/usr/bin/python3`, which `resolve_python` accepts. The runner has a real Python, so this cannot be observed there.
2. **A Finder-launched `.app` gets launchd's minimal `PATH`** (`/usr/bin:/bin:/usr/sbin:/sbin`). `the_one/platform/env.py::_common_runtime_dirs` (line 181) appends `/usr/local/bin`, `/opt/homebrew/bin`, `~/.local/bin`, `~/.cargo/bin` and `~/.npm-global/bin` on POSIX, which covers Homebrew and uv, but not `nvm`, `fnm`, `volta`, `asdf` or `pyenv` shims (user-installed Node via those never lands on the PATH); `THE_ONE_EXTRA_PATH` is the only escape.
3. **`DesktopSession` has no darwin lifecycle** (`the_one/interfaces/desktop/shell.py:368`): its only lifecycle hooks are `_on_closing` (hide to tray, line 463) and the tray; there is no `applicationShouldHandleReopen` (Dock click after the window is hidden), no Cmd-Q / app-menu Quit handling, and no "close the window but keep running" convention check. A grep of `desktop/*.py` and `interfaces/app.py` finds no `darwin` branch except `_webview_available`.
4. **`_webview_available` returns `True` on darwin without probing** (`shell.py:320-321`: `if sys.platform in ("win32", "darwin"): return True`). A broken or missing WKWebView would only show at window creation.

#### AC status
- AC1 met (see Decisions 6; actionlint clean). AC2 met (`py_compile`, Analysis run on Linux; every macOS-only line in the spec carries a comment). AC3 met (config section, patch clause, additive diff, five-layout check). AC4 met (above). AC5 met (above). AC6 met (changes only under `packaging/`, `.github/workflows/`, `missions/`; ruff clean; no push/PR/dispatch/commit; `gh auth status` read only).

#### Residual risks for the run
- B's macOS stub behaviour (argv forwarding, `sys.executable` being the stub, whether stdout reaches the terminal, `BRIEFCASE_MAIN_MODULE` support in the stub) is from memory; the run prints it first.
- The 30-minute job cap versus two cold builds on a 3-core runner (above).
- `pyobjc`/`PyInstaller` hidden imports for pywebview's Cocoa backend are a best guess; a missing module would show in `doctor`'s desktop-shell gate or the `open` probe.
- First time `doctor` runs on macOS at all: the file-watcher (FSEvents), embedding and window-chrome gates are unproven there.
- Briefcase clones its template and downloads its support package/stub from GitHub at build time.

#### Review fixes (leg 04)
- Workflow job `timeout-minutes` raised 30 -> 40 (worst case about 36 min; the 15-minute step caps now always fire first and the upload is reached). Header comment updated. Recorded post-review amendment: leg 04 AC1 now reads "40 or less" (the leg was already landed; the Flight Director changed the wording after review).
- New final step "Fail on a failed or missing candidate" (`if: always()`, after the upload): fails the job when a selected candidate's SUMMARY is missing or contains FAIL.
- `macos-checks.sh`: `log show` and `screencapture` wrapped in `tl 60`.
- Lint: actionlint 1.7.7 (with shellcheck 0.10.0) clean on the workflow; shellcheck clean on `macos-checks.sh`; `ruff check packaging/` and `ruff format --check packaging/` pass.

### macos-probe-run
**Status**: landed
**Started**: 2026-10-23
**Landed**: 2026-10-24

#### Run (AC1)
- Run 40058032297, https://github.com/msieurthenardier/the-one/actions/runs/40058032297, `candidates="A B"`, on macos-15 (15.7.9, arm64, Xcode 16.4, 3 cores billed as 5 CPUs reported, setup-python 3.11.9). Conclusion `failure`; job 03:22:28 to 03:25:45 UTC, **3 min 17 s**. Every step succeeded except the last ("Fail on a failed or missing candidate": `candidate A: SUMMARY missing`). Job 1 of 2 used.
- Evidence: `$HOME/the-one-m32-evidence/macos/run-1/` (`job.log`, `run.json`, `packaging-probe-macos-logs/{A,B,A-step.log,B-step.log,runner.txt}`).

#### Candidate A: not reached (AC4 (a), a recipe defect)
Died at its 4th step, 20 s in, before PyInstaller ran. The closure install (`--require-hashes --no-deps`, incl. the five pyobjc-* wheels and `usearch`/`numkong`) and the pinned PyInstaller 6.22.3 + hooks-contrib 2026.8 installs both succeeded (`A/pip-closure.log`, `A/pip-tools.log`).
```
== A: icon
  File ".../packaging/macos/make-icns.py", line 30, in main
    src.save(out, format="ICNS", sizes=[(s, s) for s in SIZES])
FileNotFoundError: [Errno 2] No such file or directory: '/Users/runner/work/_temp/m32-build/macos-0.11.8/icon.icns'
build.sh: icns failed
```
Root cause: `build.sh` wrote `$WORK/icon.icns` before `$WORK` existed (`mkdir -p "$WORK"` came later, at the freeze step, and `$LOG`/`$STAGE` creation never made it). The Linux rehearsal missed it because the scratch `$WORK` already existed there. Reproduced on Linux against an absent directory (same `FileNotFoundError`), and the fix gives `wrote ... icon.icns (1224031 bytes)`. Every A check (G1, G2, serve, G4, sign, size, dmg) is **not reached**.

#### Candidate B: all checks reached, all hard checks PASS (AC2)
`SUMMARY.txt`: `== B done: 0 hard check(s) failed`. Briefcase create/build/package took about 2 min 20 s (03:23:06 to 03:25:25) including the template and support-package download; checks 13 s.

| check | result | excerpt |
|---|---|---|
| codesign verify (`--deep --strict`) | PASS | `rc=0`; `Signature=adhoc`, `Identifier=ai.gleepglorp.the-one`, `Format=app bundle with Mach-O thin (arm64)`, sealed resources 7996 files, `valid on disk`, `satisfies its Designated Requirement` |
| G1 doctor, strict | PASS | `{"pass": true, "rc": 0, "gates": 12, "bad": []}`; window chrome `OK — skipped (not Windows)` is the only skip; `usearch: OK ... simd=neon`; `embedding model: OK — 512-dim ...`; `file watcher: OK — native change notification round-trip OK`; `desktop shell: OK — pystray + PIL importable`; `mcp sdk: OK — mcp 2.3.0 ...`; `time zones: OK — 345 zones` |
| G2 interpreter outside bundle | PASS | resolved `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11` (prefix `/Library/Frameworks/Python.framework/Versions/3.11`), runs, 3.11.9, no `.app/` or `Contents` |
| serve `/api/live` | PASS | `{"status":"ok"}` |
| G4 data dir | PASS | `Local API credential created at /Users/runner/Library/Application Support/the-one/api-credential (mode 0600)`; `ls` shows only `api-credential` after `rotate-api-credential` |
| version | PASS | `GleepGlorp AI v0.11.8`, rc 0 |
| size | `.app` 353 MB (361,780 KB), `.dmg` 138.6 MB (ad-hoc signed by `briefcase package --adhoc-sign --no-notarize`) | `artifacts.txt` |
| build time | about 2 min 20 s for create+build+package, cold runner | job log |
| finder-style `open -n` (best effort, unscored) | `open rc=0`, `/api/live` answered `{"status":"ok"}` with a bare launch, so the stub reached `app`/`serve`; `POST /api/window/focus` returned an empty body (no window registered, or unreadable); `screencapture` is an empty black desktop with Finder and Dock only, so no window is visible | `open*.txt`, `open-screen.png` |
| window, Dock, single-instance | N/A (contributor, Flight 3) | DD6 |

#### Residual risks (AC3)
- **B stub `sys.executable`, `sys.frozen`, argv, stdout: confirmed as assumed.** `sys.executable` is the stub `.../Contents/MacOS/GleepGlorp AI` (exists), `sys.frozen` absent and no `_MEIPASS`, `argv=[stub, 'a', 'b']` (forwarded), and stdout reaches the terminal (`GleepGlorp AI v0.11.8`). Python is the embedded 3.11.9 `Python.framework` in `Contents/Frameworks`. Patch 02's macOS clause works: `is_frozen=True bundle_dir=None resolve_python='/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11'`. Every launch prints two `NSLog` lines first (`No Python NSLog handler found ... add 'std-nslog' to your app dependencies`), so stdout is not clean (cosmetic, a Flight 2 upkeep note: add `std-nslog` or accept).
- **`BRIEFCASE_MAIN_MODULE`: confirmed working** (`stub-probe.txt`, `m32probe` ran with the env var; rc 0).
- **A's pyobjc hidden imports: unobservable** (A never built).
- **FSEvents file watcher, embedding, window-chrome gates: confirmed OK on macOS** (B, above; the embedding gate peaked at 290.6 MiB RSS).
- **`codesign --verify --deep --strict` on A: unobservable.** B's strict verify passes.
- **Job cap: refuted as a worry for B** (a cold B build is 2.5 min, not 10-14). A's duration is still unknown.
- **Template/support download from GitHub: did not fail** (the build ran).

#### Classification (AC4)
- A: **(a)** recipe defect, contained fix written (below).
- B: no FAIL; nothing to fix. Its only gaps are the DD6 paper items.

#### Fixes (uncommitted)
1. `packaging/macos/build.sh`: `mkdir -p "$WORK"` before the icon step (the defect).
2. `packaging/spike/macos-checks.sh` (cosmetic, from reading B's SUMMARY): the `version:` and `gate 4:` summary lines skipped the `NSLog` noise lines, so the first printed line was noise instead of the version. Scoring is unchanged (gate 4 greps the whole file).
Lint: `shellcheck` 0.10.0 on both scripts, `bash -n`, `ruff check` and `ruff format --check packaging/`, `actionlint` 1.7.7 on the workflow (unchanged; trigger and inputs identical to main's copy): all clean. Linux rehearsal: icon step reproduced and fixed against a missing `$WORK`. Scan for latent defects after the icon step: re-read `build.sh` from the freeze to the checks, the spec (PyInstaller Analysis/COLLECT already rehearsed on Linux in leg 4) and `macos-checks.sh` (all of its code paths except the B-only stub probe ran for B in this run and produced scores, so the shared checks are now proven on a real Mac); no other defect found. What cannot be rehearsed off a Mac, and is the residual risk for run 2: pyobjc submodule collection at Analysis time, `codesign --force --deep` over PyInstaller output, `hdiutil` (retried, never fatal), and A's runtime behaviour. A freeze failure or a missing hidden import would be scored as evidence (G1's `desktop shell` gate names a missing module), not a script defect. If PyInstaller itself fails, A's SUMMARY is again not written, but `A-step.log` and `pyinstaller.log` are uploaded and the failure is evidence.

#### Second-run case (the last macOS job; operator go needed, and the budget check before dispatch)
- What failed and why the fix is contained: one missing `mkdir -p` in A's build script, no app change, no design call, no trigger/input change, so no new `.github` PR to `main`; `--ref` runs the flight branch's copy, so the flight branch must be committed and pushed first.
- What run 2 adds to the decision: A's whole macOS row (G1/G2/serve/G4, signature, size, freeze time), the one comparison the decision needs (PyInstaller `.app` vs Briefcase `.app` on size, signing, and `doctor`); without it macOS has one candidate scored, and the table could not support a toolchain pick. Run `A` only (B is complete and passing; a rerun of B would add nothing).
- Expected cost: A alone is estimated at 8-12 min wall (closure install about 20 s, PyInstaller on a big closure 3-6 min, ad-hoc sign, 2 hdiutil attempts at most, checks about 1-2 min); billed at the 10x macOS rate about 80-120 billed minutes. Single dispatch, budget total 2 jobs.
- Exact command: `gh workflow run packaging-probe-macos.yml --ref flight/01-choose-packaging-toolchain -f candidates="A"`

#### Run 2 (candidate A, follow-up pass)
- Run 40058513153, https://github.com/msieurthenardier/the-one/actions/runs/40058513153, `candidates="A"`, same runner image. Conclusion `success`; job 03:29:37 to 03:31:15 UTC, **1 min 38 s** (the API's start/complete stamps; about 1 m 42 s with queueing). Job 2 of 2 used; no macOS job remains. Evidence: `$HOME/the-one-m32-evidence/macos/run-2/` (`job.log`, `packaging-probe-macos-logs/{A,A-step.log,runner.txt}`).
- **The fast green is real, not a silent skip.** Step timeline from `job.log`: closure install and tool pins 03:29:47 to 03:30:10 (23 s, wheels only, no builds); icon step 0.2 s (`make-icns` now has its `$WORK`); `pyinstaller rc=0 in 39 s` (`pyinstaller.log` runs Analysis, EXE, COLLECT and BUNDLE, `Build complete!`, with `Signing the BUNDLE`); ad-hoc `codesign` `rc=0` (0.3 s); `hdiutil create` attempt 1 `rc=0` (9 s); checks 03:31:01 to 03:31:15. `layout.txt` lists the real bundle (`Contents/{Frameworks,Resources,MacOS/the-one,Info.plist,_CodeSignature}`). B's step was `skipped` by design. My earlier 8-12 min estimate assumed a slower freeze; PyInstaller on 3 cores with a warm wheel set took 39 s. Every check wrote its own artifact (`doctor.txt` with 12 gates, `gate2.txt`, `serve.log` with `GET /api/live 200`, `codesign-dv.txt`, `codesign-verify.txt`, `dmg.txt`), and `SUMMARY.txt` ends `== A done: 0 hard check(s) failed`. The one "Terminated: 15" line in `A-step.log` is `macos-checks.sh` stopping its own `serve` (the probe's `perl alarm` wrapper), not a failure.
- Caveat on the elapsed time: the job is fast because this is a thin-closure macOS build (`.app` 177 MB), not because anything was skipped.

| check | result | excerpt |
|---|---|---|
| codesign verify (`--deep --strict`) | PASS | `rc=0`; `Identifier=ai.gleepglorp.the-one`, `Signature=adhoc`, `Format=app bundle with Mach-O thin (arm64)`, `Sealed Resources version=2 rules=13 files=1196`, `TeamIdentifier=not set`; `valid on disk`, `satisfies its Designated Requirement`. The 45 KB verify log is `--prepared:`/`--validated:` lines per nested `.so` (data), no error lines |
| G1 doctor, strict | PASS | `doctor score: {"pass": true, "rc": 0, "gates": 12, "bad": []}`; `frozen: True`; `window chrome: OK — skipped (not Windows)` is the only skip; `usearch: OK — HNSW round-trip ... (numkong=yes, simd=neon)`; `embedding model: OK — 512-dim float16 ... peak RSS 255.0 MiB` (loaded from `.app/Contents/Frameworks/the_one/embeddings/data/potion-retrieval-32M`); `file watcher: OK — native change notification round-trip OK`; `desktop shell: OK — pystray + PIL importable`; `mcp sdk: OK — mcp 2.3.0 ...`; `time zones: OK — 345 zones` |
| G2 interpreter outside bundle | PASS | `python interpreter: OK — resolved to /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11`; run: prefix `/Library/Frameworks/Python.framework/Versions/3.11`, `Python 3.11.9`, no `.app`/`Contents` in either |
| serve `/api/live` | PASS | `{"status":"ok"}`; `serve.log`: `GET /api/live HTTP/1.1" 200 OK` |
| G4 data dir | PASS | `Local API credential created at /Users/runner/Library/Application Support/the-one/api-credential (mode 0600)`; `ls` shows only `api-credential` |
| version | PASS | `GleepGlorp AI v0.11.8`, rc 0 |
| size | `.app` 177 MB (181,468 KB), `.dmg` 125.2 MB (125,218,150 B, UDZO, `hdiutil verify` checksum VALID) | `A/dmg.txt`, `layout.txt` |
| build time | PyInstaller 39 s; closure install 23 s; whole build step about 1 min 14 s (03:29:47 to 03:31:01) incl. sign and `.dmg`; cold runner | `job.log` |
| finder-style `open -n` (best effort, unscored) | `open rc=0`, `/api/live` answered `{"status":"ok"}`, and `open-screen.png` shows a real native window titled "GleepGlorp AI" (traffic lights, menu bar "GleepGlorp AI / View", Dock icon with the app's mascot) whose web content is a blank dark (`#111216`-like) panel at capture time; `POST /api/window/focus` returned `{"focused":false}`. So the Cocoa window was created through A's frozen pywebview, but the page had not painted (or the capture raced the load) and focus was not reported; this headless runner session cannot say which |
| window, Dock, single-instance | N/A (contributor, Flight 3) | DD6 |

Windows-only ctypes libraries (`ole32`, `shell32`, `dwmapi`) and `httpx2.websockets` (needs `wsproto`, not in the closure) are PyInstaller warnings only; nothing failed at runtime.

#### Residual risks resolved by run 2 (AC3)
- **A's pyobjc hidden imports: confirmed sufficient for what was exercised.** `layout.txt` shows `objc`, `Foundation`, `CoreFoundation`, `WebKit` (`_WebKit.cpython-311-darwin.so`) and friends in `Contents/Frameworks`; the bare `open` produced a native window, which requires pywebview's Cocoa backend to import `AppKit`/`WebKit` in the frozen app; `doctor`'s `desktop shell` gate (pystray + PIL) passed. Not exercised: pystray's Darwin tray icon in a live session and pywebview JS bridge calls (the focus call returned `focused:false`). That is a Flight 3 contributor item, not a toolchain differentiator.
- **A's strict codesign verify: PASS** (`--verify --deep --strict` rc 0, valid on disk, satisfies its Designated Requirement; the spec's PyInstaller re-sign plus the explicit `codesign --force --deep -s -` is enough for ad hoc).
- **Job cap: refuted** (A's whole job is under 2 minutes; the 15-minute step cap and 30-minute job cap were never near).

#### macOS comparison (A vs B)
Both candidates pass every scored macOS hard check: strict G1 (12 gates, only window chrome skipped), G2 (both resolve `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11`), serve `/api/live`, the data dir under `~/Library/Application Support/the-one/`, and ad-hoc `codesign --verify --deep --strict` rc 0. Build time: A about 1 min 14 s for sign plus `.dmg` (PyInstaller 39 s), B about 2 min 20 s (create, build, package, incl. a template and support-package download from GitHub). Size: A `.app` 177 MB and `.dmg` 125.2 MB; B `.app` 353 MB and `.dmg` 138.6 MB (B embeds a full `Python.framework`, nearly twice A's `.app` for a `.dmg` only 11% larger). Signing: identical ad hoc, Developer ID and notarization untested for both (paper, DD6). Launch: A's bare `open` made a visible native window (blank content at capture, focus false); B's bare `open` started the server but showed no window, which fits B's stub reaching `app`/`serve` without registering a window. Upkeep macOS adds: A has `packaging/macos/` (379 lines in 5 files: spec 182, `build.sh` 75, entry shim 39 for the Finder `-psn_*` argv, icns 41, README 42) and is the only one whose `sys.frozen`/`_MEIPASS` logic needs nothing; B needs patch 02's macOS clause (a `MacOS`/`app_packages` heuristic), `universal_build = false`, `--no-binary proxy-tools`, a `min_os_version` pin and a template/support download, and its `doctor` only passes because the clause makes `is_frozen()` true. Neither bundles Python resolution: both rely on a host Python 3.11 (paper item 1: on a stock Mac `/usr/bin/python3` is the CLT stub).

#### Status
Run 2 recorded; macOS evidence is complete for the toolchain decision (both candidates have a fully scored row). Leg status stays `landed`.


### windows-cost

> **2026-10-24, `decision-hat`:** the operator's real-machine MSI try was not run. Briefcase was rejected at the decision, so the try would decide nothing. The morning guide below is kept for the record only.
**Status**: in-flight (autonomous half done; hosted run 2 recorded; no further Windows run; awaiting review, commit and the operator's real-machine try)
**Started**: 2026-10-24

#### Changes Made
- `.github/workflows/packaging-probe-windows.yml` filled in on the flight branch (header comment rewritten; the `on:` block is byte-identical to `main`'s).
- `packaging/briefcase/`: `pyproject.toml.in` gained `[tool.briefcase.app.the-one.windows]` (`system_installer = false`, `--no-binary proxy-tools`); patch 02 gained a Windows clause; `build-windows.ps1` (new); `check-env-layouts.py` gained five Windows layouts; `windows-resolution-rehearsal.py` (new, the Linux `win_amd64` pip rehearsal); README gained a Windows section.
- `packaging/spike/`: `windows-lib.ps1` (shared, time-limited process helpers), `windows-checks.ps1` (new; phases `fresh` and `upgrade`), `m32probe_win.py` (stub probe), `m32run.py` (a redirect wrapper, the fallback if the GUI stub prints nothing), `score_doctor_file.py` (scores a doctor file, UTF-8 with a cp1252 fallback); `stage.py` uses `git apply` on `win32` as well as `darwin` (Linux path unchanged; proved byte-identical to `patch` on this host).
- Nothing under `the_one/` or `tests/` changed (the patch is a diff file). No commit, push, PR or dispatch.
- Tools: `pwsh` 7.6.7 linux-x64 (the official tar.gz, no root) in `$HOME/the-one-m32-build/tools/pwsh-7.6.7/`, sha256 `6896f9e3a6b0a354bf470835a96da76d2f801cd50dcf047ad7c4563bf93bf431` (matches the release's `hashes.sha256`; recorded in `tools/SHA256SUMS`); `tools/parse-ps.ps1` is the parser harness. Rehearsal scratch: `$HOME/the-one-m32-build/win-rehearsal/`.

#### What Briefcase 0.4.6 does on Windows (read from its source and the v0.4.6 template, not assumed)
- Installs requirements with the host's own pip, `--target=<src\app_packages>`, `--only-binary :all:` (`require_binary_installs` is True) and no `--platform` (`virtual_environment/base.py::platform_tag` returns None off macOS/iOS). The support package is python.org's **embeddable** zip for the Python that runs Briefcase (3.11 -> 3.11.9, support revision 9 in the template's `briefcase.toml`); so the job pins `setup-python` 3.11, as A's CI does.
- The stub is a GUI-subsystem exe unless `console_app` (`windows/__init__.py::stub_binary_filename`: "GUI-Stub" or "Console-Stub"); the app exe is `GleepGlorp AI.exe` (`bundle_package_executable_path`: `formal_name.exe`, or `app_name.exe` for a console app). `build` runs rcedit for icon and version strings; the template's `cleanup_paths` removes `src/python*.exe`.
- `package` builds the MSI with WiX 5.0.2 (`integrations/wix.py`, downloaded from github.com by Briefcase). `--adhoc-sign` is Briefcase's explicit "do not sign"; with a `--identity` it would sign through signtool. The MSI is **unsigned**.
- **Scope, from the rendered `.wxs`** (`faked-render.wxs`, the real v0.4.6 template rendered with `install_scope=perUser`): `system_installer = false` renders `Scope="perUserOrMachine"` (the template maps any scope containing "User" to it) and, because the scope is fixed, skips the scope dialog; the install folder is `ProgramFiles64Folder\GleepGlorp AI\GleepGlorp AI`, which for ALLUSERS=2/MSIINSTALLPERUSER=1 is `%LOCALAPPDATA%\Programs\GleepGlorp AI\GleepGlorp AI`. `UpgradeCode` is `app.guid`, default `uuid5(NAMESPACE_DNS, "gleepglorp.ai")` (the reversed bundle id), unrelated to Inno's AppId. The template has `<MajorUpgrade AllowSameVersionUpgrades="yes" Schedule="afterInstallInitialize">`, `ARPNOREPAIR`/`ARPNOMODIFY`, one Start-menu shortcut in a "GleepGlorp AI" folder, no `CloseApplications`/`util:CloseApplication` (the `Util` extension is loaded but unused), and `post_install_script`/`pre_uninstall_script` as deferred `.bat` custom actions.
- The generated `.wxs`, the bundle's top level and any `._pth` are dumped into the logs by `build-windows.ps1`.

#### Rehearsal (AC1, AC2)
- **AC1.** `actionlint` 1.7.7 (`-shellcheck` 0.10.0): clean. `diff <(git show origin/main:...packaging-probe-windows.yml | sed -n '/^on:/,/^[a-z]/p') <(sed -n '/^on:/,/^[a-z]/p' <branch copy>)` after a fresh `git fetch origin main`: empty. YAML: only `workflow_dispatch`, `candidates` is `type: choice`, `permissions: {contents: read}`, no `secrets.`, `timeout-minutes: 40` on the job, 14 / 9 / 11 on the build / fresh / upgrade steps, a `concurrency` group that never cancels. Uploads: the MSI + its hash (own step, `if: always()`, `retention-days: 7`) and the logs (`retention-days: 7`). `GH_TOKEN` is set only on the upgrade step. The draft-release fallback is described in the header, not wired (it needs `contents: write`).
- **win_amd64 pip resolution** (`windows-resolution-rehearsal.py`; the closure's markers are evaluated as Windows AMD64 first, so `pywinpty`, `pywin32` and `pythonnet` stay in and `pygobject`/`pyobjc` drop out; 89 pins kept, 13 dropped), `pip download --platform win_amd64 --only-binary :all: --no-binary proxy-tools --no-deps --require-hashes`:

```
win_amd64 py3.11: rc=0 files=89     (B's Python: setup-python 3.11 -> embeddable 3.11.9)
win_amd64 py3.12: rc=0 files=89
  pywinpty-3.0.5-cp311-cp311-win_amd64.whl   pywin32-311-cp311-cp311-win_amd64.whl
  pythonnet-3.1.0-cp310.cp311.cp312.cp313.cp314-none-win32.win_amd64.whl   usearch-2.26.4-cp311-cp311-win_amd64.whl
  numpy-2.4.6-cp311-cp311-win_amd64.whl   proxy_tools-0.1.0.tar.gz
negative control (no --no-binary proxy-tools): rc=1  ERROR: No matching distribution found for proxy-tools==0.1.0
```
  `proxy-tools` is the one sdist, as on macOS; its hash is in the closure, so `--require-hashes` holds. Evidence: `win-rehearsal/result-py3.11.txt`, `result-py3.12.txt`, `result-negctl.txt`.
- **Patch 02, Windows clause** (additive; `diff 02-old.diff 02-new.diff | grep '^<'` shows only the two hunk-header lines):

```
< @@ -152,14 +153,49 @@
< @@ -175,6 +211,12 @@
```
  The new `_is_briefcase_windows_app()` (`functools.lru_cache`) is true when `sys.executable`'s suffix is `.exe` (case-insensitive) and `<exe dir>/app_packages` is a directory; it is **not** gated on `sys.platform`. `is_frozen()` gains one `or _is_briefcase_windows_app()` line and `_bundle_dir()` returns `None` for it (the stub's directory holds the app and its runtime, not the runtimes the agent spawns). The Linux and macOS clauses are unchanged. `git apply --check` passes on the original `env.py`; the staged tree compiles; `git apply` and `patch` give byte-identical trees.
- **`check-env-layouts.py`** (output in `win-rehearsal/faked-layout.txt`):

```
ok   macos-app / linux-system / source-install / macos-shaped-not-MacOS / macos-no-app_packages     (unchanged)
ok   windows-app: frozen=True bundle=None            (strip_path unchanged=True; clean_path = given PATH + runtime dirs appended)
ok   windows-app-upper-EXE: frozen=True bundle=None
ok   windows-no-app_packages: frozen=False           ok   windows-no-.exe: frozen=False (app_packages present, stub not .exe)
ok   windows-venv-python.exe: frozen=False           RESULT PASS
```
- **Briefcase's own config parse** of the generated `pyproject.toml` for `platform="windows"`: `system_installer False`, the three installer args, `allow_subprocesses True`, `icon icon`; for macOS the merged result is unchanged.
- **PowerShell:** `pwsh` 7.6.7 `Parser::ParseFile` on `windows-lib.ps1`, `windows-checks.ps1`, `build-windows.ps1`: no errors. `Invoke-Capped`, `Use-EnvVars` and the quoting helper were run for real under Linux `pwsh` (rc propagation, stderr capture, em dash, env restore, timeout rc 124, "will not start" rc -1). The Windows-only calls (`msiexec`, registry, COM shortcuts, `taskkill`) are **unrehearsed**.
- `ruff check` and `ruff format --check packaging/`: clean. `m32run.py` ran for real against the repo (`version`, an unknown command): file output and `rc=` correct.

#### Decisions (beyond the leg's ten findings)
1. **`candidates`**: "A" or "A B" logs "A is the existing Inno installer, not built here"; "B" and "A B" build B.
2. **The job refuses to run its checks outside GitHub Actions** (`windows-checks.ps1` exits 2 unless `GITHUB_ACTIONS=true`): it deletes `%LOCALAPPDATA%\the-one` and installs/removes programs, which must never happen on a person's PC.
3. **GUI stub fallback**: if `version` prints nothing the checks record "CLI COST", run `doctor` through `m32run.py` (a `BRIEFCASE_MAIN_MODULE` wrapper that points stdout at a file) on a copy of the install, and retry `serve` the same way, so one run still yields gate data.
4. **`pywin32` risk probed**: `mcp` 2.x's Windows helpers import `win32api`/`win32job` (`mcp/os/win32/utilities.py`), and the embeddable Python does not process `.pth` files, so `pywin32.pth`'s path setup may not run. `m32probe_win.py` imports them and `mcp.os.win32.utilities` and prints whether they came up None; the stdio MCP server path on Windows depends on it.
5. **Uploads**: the MSI (artifact `m32-probe-msi-<sha>`) goes up before any check; the logs artifact is `packaging-probe-windows-logs`.

#### Paper half (AC3)
**A (keep PyInstaller and Inno).**
- *Two-exe split.* `the-one.exe` (console CLI: `chat|serve|doctor|version`, CI smoke) and `the-one-app.exe` (`console=False`, what the shortcut runs) share one `_internal` payload (`packaging/windows/the-one.spec:348-352, 383-411`; `the-one.iss` [Icons]). It exists because a console-subsystem exe pops a blank console when double-clicked. Upkeep: two EXE() blocks in one COLLECT; the CLI is a real console program, so `doctor` output works from any terminal and from CI.
- *Restart Manager.* `CloseApplications=force` + `RestartApplications=no` (`the-one.iss:69-70`) plus a `[Code] KillRunning` backstop that `taskkill`s both exes in `PrepareToInstall`, because close-to-tray makes `WM_CLOSE` only hide the window so the graceful close leaves the process alive (comment at `the-one.iss:63-68`; the F6 HAT fix). Inherited from Inno at no marginal cost.
- *Stable AppId upgrade path.* `AppId={{CAEEFB46-...}}` (`the-one.iss:35`, "frozen, NEVER regenerate"), `DefaultDirName={autopf}\GleepGlorp AI` (`:39`), `PrivilegesRequired=admin` (`:61`): every release installs in place over the last; this is the path the operator's PC is on today. The data dir (`%LOCALAPPDATA%\the-one`, `the_one/config.py:23`) lives outside `{app}`, so an uninstall leaves it.
- *pywinpty helper exes.* Squawk 0162: pywinpty 3's `OpenConsole.exe` and `winpty-agent.exe` were missing from the frozen bundle until `collect_dynamic_libs("winpty", search_patterns=["*.dll","*.pyd","*.exe"])` (`the-one.spec:113-118`). A carries a collection rule per native dependency (`pythonnet`, `winpty`, `uvicorn`, ...) and finds gaps only by running the frozen app.
- *WebView2 and the title bar.* `_webview_available` returns True on win32 without probing (`the_one/interfaces/desktop/shell.py:315-321`, WebView2 assumed); the M25 F5 tint is `DwmSetWindowAttribute` through `ctypes` on the window handle (`the_one/interfaces/desktop/chrome.py:62-65, 110-120`), so it is independent of the packager. The packager-dependent part is `pywebview -> pythonnet/clr_loader`, which the spec collects (`packaging/windows/README.md:23, 41`).
- *Per-push Concourse build.* The `build-windows-installer` job (`ci/windows-installer.pipeline.yml:36-41`, `trigger: true`, `passed: [ci]`) runs `ci/tasks/windows-installer-build.yml` (choco Python 3.11 + Inno Setup on an uncontainerised worker, freeze, iscc, publish to MinIO); the GitHub `windows-installer.yml` does the `v*`-tag release (`iscc //DAppVersion=$VER`, line 196). It already exists and runs; keeping A costs no CI migration.
- *"One metadata source".* The version is already single-sourced: `the-one.iss:25-31` has `#ifndef AppVersion` so `iscc /DAppVersion=` wins. What is still repeated (name, publisher, AppId, icon, install dir, the `.spec`'s version resource) would need one small generator that reads one block (the root `pyproject.toml` or a `packaging/metadata.toml`) and emits `/D` defines or an `#include`d `.iss` fragment plus the spec's values: roughly one stdlib script and an `#ifndef` guard per define. A smaller cost than B's template fork (below).

**B (Briefcase MSI).**
- *What the hosted job showed.* Pending the run (AC6): install path, Start-menu and Add/Remove entries, `doctor`, gate 2, `serve`, gate 4, build time, MSI size, and the upgrade scenario.
- *AppId versus the MSI upgrade code.* Inno's `{CAEEFB46-...}` and the MSI's `UpgradeCode` (`uuid5` of the reversed bundle id) are unrelated, so Windows Installer cannot see an Inno install as an earlier version: there is **no in-place upgrade from Inno**. MSI to MSI is fine (`MajorUpgrade`, `AllowSameVersionUpgrades`). Migration options: (a) a `post_install_script` `.bat` (a deferred custom action) that finds Inno's `...\Uninstall\{CAEEFB46-...}_is1` key and runs its `UninstallString /VERYSILENT`: it works only for a per-machine (elevated) MSI, because Inno is per-machine; (b) a one-time documented step ("uninstall the old GleepGlorp AI, then install this"), data intact because the data dir sits outside both install dirs. The per-user MSI chosen for this probe does not replace Inno, it sits beside it; a per-machine MSI (`system_installer = true`) is the like-for-like scope.
- *Restart Manager.* The template references the MSI `FilesInUse`/`MsiRMFilesInUse` dialogs, so an interactive install asks to close locked apps; a silent `/qn` install with the app running schedules a reboot instead. It has no `CloseApplications` or `util:CloseApplication` (the `Util` extension is loaded by `_package_msi` but unused), and because close-to-tray hides rather than closes, even Restart Manager's graceful close would leave the app alive. Matching Inno's `force` needs a `pre_uninstall_script` (`taskkill`, Briefcase supports `.bat` only) or a forked template (`template`/`template_branch` config keys exist) carrying `util:CloseApplication Terminate="yes"`: a template fork is a new upkeep item A does not have.
- *Tray, WebView2 and the title bar under the stub.* The tray (`pystray`, in-process) and the DWM tint (`ctypes`, window handle) do not depend on the packager. WebView2 goes through `pythonnet`/`clr_loader` loading `Python.Runtime.dll` inside the embeddable Python: `doctor`'s desktop-shell gate only proves `pystray + PIL`, so the window itself is unproven off a real desktop (the probe's bare launch is best effort). rcedit sets the icon and version strings; the taskbar identity is the stub's path.
- *pywinpty's helper exes and `.pth` files.* pip extracts the wheel as-is into `app_packages\winpty` (`OpenConsole.exe`, `winpty-agent.exe`, `conpty.dll` side by side), so no collection rule exists to forget (A's squawk 0162 class of defect cannot occur); the probe spawns a PTY to prove it. The B-specific risk is the embeddable Python ignoring `.pth` files: `pywin32.pth` is how `win32api`/`win32job` find `win32\` and `pywin32_system32\`, and `mcp`'s Windows stdio helpers use them (decision 4).
- *The CLI story.* The default stub is GUI-subsystem, so a console cannot show its output (unconfirmed until the run). Briefcase has one exe per app and one MSI per app, so A's two-exe split inside one installer is not available; the options are `console_app = true` for the whole app (a console window on every launch, rejected), a second Briefcase app (a second MSI), or nothing (no CLI on Windows). The probe measures which of those applies.
- *Moving the Concourse Windows build to Briefcase.* Replace the choco Inno step with a Briefcase venv, the staged closure and `create|build|package windows app`; Python must stay 3.11 (the embeddable support revision); WiX 5.0.2, rcedit, the stub, the template and the support package all download from github.com/python.org at build time (an offline or flaky worker fails the build, and the worker's `~\.briefcase` caches persist across runs); the MSI is named `GleepGlorp AI-<ver>.msi` (`distribution_path`), so the MinIO publish glob and the smoke steps that call `dist\the-one\the-one.exe` change; signing is `--identity <thumbprint>` from a cert store, as inert as A's `SignTool` hook today.

#### The operator's morning guide (AC4; PowerShell throughout; the Flight Director walks it)
The MSI is unsigned and per-user: it installs to `%LOCALAPPDATA%\Programs\GleepGlorp AI\GleepGlorp AI` beside the Inno install in `C:\Program Files\GleepGlorp AI`, and needs no elevation. Both show as "GleepGlorp AI" in Add/Remove Programs.
1. **Quit** GleepGlorp AI from the tray (right-click the tray icon, Quit). Then `Get-Process the-one-app, the-one -ErrorAction SilentlyContinue` must print nothing.
2. **Back up the data dir.** Confirm the real path first: open Explorer on `%LOCALAPPDATA%\the-one` and check it holds `the-one.db` and `api-credential`. Then, with these exact variables:
   `$src = "$env:LOCALAPPDATA\the-one"; $bak = "$env:USERPROFILE\the-one-backup-m32"; robocopy $src $bak /E`
   (robocopy exit codes 0 to 7 mean success). Check that `$bak` holds `the-one.db`.
3. **Download the MSI** from the run's artifact `m32-probe-msi-<sha>` (GitHub Actions run page > Artifacts; it unzips to the `.msi` and a `.msi.sha256`). Check it: `(Get-FileHash -Algorithm SHA256 '<path to the .msi>').Hash` must equal the hash in the `.sha256` file (case-insensitive).
4. **Install, per-user:** `msiexec /i "<path to the .msi>" MSIINSTALLPERUSER=1 ALLUSERS=2`. If SmartScreen appears, choose "More info", then "Run anyway". No wizard option should ask for a scope; if one does, pick "Just me" (per-user).
5. **Checklist** (report each):
   - Start menu: one "GleepGlorp AI" entry or two? Which one starts which install (right-click > Open file location)?
   - Add/Remove Programs: how many "GleepGlorp AI" entries (one or two), with which versions (Inno 0.11.8, MSI 0.11.9)?
   - The new shortcut opens the app. Existing chats, agents and providers are all there (the MSI's `serve` reads the same `%LOCALAPPDATA%\the-one`).
   - `doctor`, from a console: `& "$env:LOCALAPPDATA\Programs\GleepGlorp AI\GleepGlorp AI\GleepGlorp AI.exe" doctor` (prints nothing or hangs = the GUI stub's CLI cost; the Inno one still works: `& "C:\Program Files\GleepGlorp AI\the-one.exe" doctor`).
   - Close-to-tray (the window's x hides it; the tray icon stays) and Quit from the tray really exits (`Get-Process 'GleepGlorp AI' -ErrorAction SilentlyContinue` is empty).
   - The Windows 11 title bar is tinted to the theme, and follows a light/dark switch.
   - A second launch focuses the existing window instead of opening another.
6. **Rollback.** Uninstall the MSI by file, which is unambiguous even though both installs are named "GleepGlorp AI": `msiexec /x "<path to the .msi>"`. If the Inno install was removed or broken, reinstall the latest `the-one-setup-*.exe` from the releases page. Restore data only if it changed, with the app quit, using the variables exactly as defined in step 2 (the direction cannot be swapped). In a new PowerShell window, first re-run step 2's variable line, `$src = "$env:LOCALAPPDATA\the-one"; $bak = "$env:USERPROFILE\the-one-backup-m32"`, then run `robocopy $bak $src /MIR`.

   **Why the backup matters (review note):** the test MSI is built from the flight branch, which carries `main`'s code. That may include database migrations newer than the installed v0.11.8 release. Its first launch can migrate the real database one way, and the older Inno build may then refuse it or misread it. **If you roll back to the Inno install after running the MSI build, restore the backup too.**

#### Dispatch (for the Flight Director, after commit and push of the flight branch)
`gh workflow run packaging-probe-windows.yml --ref flight/01-choose-packaging-toolchain -f candidates="B"`
Estimated job: setup (checkout, setup-python, uv export) 3-4 min; B build 8-12 min (venv + Briefcase install 1, template clone, embeddable Python + stub + WiX + rcedit downloads and 89 wheels into `app_packages` 4-6, rcedit, WiX `build` 1-2); fresh checks 4-6 (install, `doctor` with the embedding gate, `serve`, probe copy of a few hundred MB, bare launch up to 90 s, uninstall); upgrade 7-10 (138 MB Inno download, silent Inno install, `serve`, MSI install, `serve`, uninstall). **About 25-32 minutes, worst case the 40-minute job cap** (step caps 14 + 9 + 11 fire first; both uploads and the summary still run). Windows minutes bill at 2x on a private repo: about 50-65 billed minutes. One job; no second dispatch is planned.

#### AC status
- AC1 met. AC2 met except that nothing could be run on Windows itself (the parse, the library helpers and the layout/resolution/stage rehearsals ran on Linux; `msiexec`, registry, COM and `taskkill` are unrehearsed). AC3 and AC4 met (above). AC5 met (`git status` shows edits only; no `gh workflow run`, push, PR or commit; `gh release list/view` and `git fetch` only). AC6 pending the dispatch.

#### Residual risks for the run
- Briefcase's WiX/rcedit/stub/template/support-package downloads (github.com, python.org) and the 14-minute build cap on a cold runner; a build failure still uploads logs and skips the checks with an honest FAIL.
- The stub's behaviour is unconfirmed on Windows: `sys.executable` (patch 02's marker also holds if it is an `.exe` in the install dir), argv forwarding (confirmed on macOS), GUI-stub stdout (fallback built), `BRIEFCASE_MAIN_MODULE` (confirmed on macOS; the wrapper and probe depend on it).
- `pywin32` under the embeddable Python (decision 4) may fail `mcp`'s stdio helpers even if `doctor` passes; the probe shows it.
- `doctor` first run on Windows from an embeddable Python: the file-watcher (ReadDirectoryChangesW), window-chrome (DWM) and embedding gates are unproven there; the hosted runner may have no usable desktop for the bare launch and screenshot (unscored).
- `msiexec` against a per-user scope while the runner is an admin session, `gh release download` of a 138 MB asset, and `Get-Process ... .Path` across the whole process list are untested on the runner; each is time-limited and logged, none aborts later steps.
- Billing: Windows minutes are 2x on a private repo.

#### Hosted run 1 (40060053657, 2026-10-24 03:52:07 to 03:54:27, 2 min 20 s; `candidates="B"`, windows-2022, flight-branch HEAD 5e5efd8)
Evidence: `$HOME/the-one-m32-evidence/windows/run-1/` (`job.log`, `packaging-probe-windows-logs/`). Conclusion `failure`; **no MSI was built, none was uploaded, and the fresh-install and upgrade phases never ran.**

What ran: setup, `uv export`, tool venv (33 s), Briefcase 0.4.6 install, `stage.py` (patches 01 and 02 applied with `git apply`), and `briefcase create windows app` (**rc=0 in 55 s**: template clone, embeddable Python 3.11.9, GUI-Stub-3.11-amd64-b14, 89 wheels into `app_packages`, "Created build\the-one\windows\app"). Then:

```
briefcase create rc=0 in 55 s (55 s so far)
MethodInvocationException: windows-lib.ps1:32  Exception calling "WriteAllText" ... "Could not find a part of the path
  'C:\m32\logs\B\briefcase-create.log\briefcase-build.log'."
InvalidOperation: windows-lib.ps1:72  You cannot call a method on a null-valued expression.   ($p.WaitForExit)
briefcase build rc=124 in 0 s (55 s so far)
FAIL build-windows: briefcase build failed
```
Then "Upload the MSI" found `C:\m32\out` empty (`if-no-files-found: warn`), the fresh and upgrade steps got `missing.msi` and logged `FAIL msi present` and nothing else, and the final step failed on the `FAIL` lines. Scored (the leg's checks): install path, Start-menu entries, Add/Remove entries, `doctor`, gate 2, `serve`, gate 4, build time of the full build, MSI size, upgrade scenario (two-or-one entries, shortcuts, seeded agent): **all "not reached"**. Measured: the tool venv, create step and runner facts (2 logical CPUs, 8 GB, Windows Server 2022 10.0.20348, 82 GB free, pwsh 7.6.8, setup-python 3.11.9).

**Root cause: a recipe defect, PowerShell variable names are case-insensitive.** `build-windows.ps1` defines `$LOG` (the log directory, `C:\m32\logs\B`) and its create/build/package loop assigned `$log = Join-Path $LOG "briefcase-$step.log"`: that is the same variable. After the first iteration `$LOG` became `...\briefcase-create.log`, so the second iteration built `...\briefcase-create.log\briefcase-build.log`, a path under a file. `Start-Process` could not open the redirect (null `$p`), `Invoke-Capped` returned its "timed out" code 124 with 0 s, and `Die` fired. Nothing is wrong with Briefcase, the MSI toolchain or the runner. Leg rehearsal missed it because the Linux `pwsh` rehearsal exercised `Invoke-Capped` alone, never the loop.

Classification: **(a) a recipe/script defect with a contained fix.** No candidate limitation was observed in this run.

**Fixes (uncommitted, working tree):**
1. `packaging/briefcase/build-windows.ps1`: the loop variable is `$stepLog` (three uses). No other file defines a colliding name in one scope: a case-insensitive duplicate-variable scan of the three scripts finds only `$LOG/$log` (fixed), and `$Text/$text`, `$EXE/$exe`, `$APPDIR/$appDir` which live in different function scopes (checked: `$EXE`/`$APPDIR` are used only inside `Phase-Fresh`/`Phase-Upgrade`, `$exe`/`$appDir` only as parameters of other functions).
2. `packaging/spike/windows-lib.ps1`: `Invoke-Capped` creates the output file's parent directory if it is missing, so a future bad path fails loudly in the log instead of as a null `Process`.
No change to the workflow (its `on:` block and every step are untouched; `git diff` of the workflow is empty).

**Latent-defect scan of the hidden phases:** read `windows-checks.ps1` end to end for scope and case collisions, `$script:` use inside `Use-EnvVars` bodies, `[bool]` casts in `Hard`, null `Process` arguments to `Wait-Live`, and the `$EXE` assignment on every path; found no further defect. Parse (`Parser::ParseFile`) clean for all three scripts, `actionlint` clean, `check-env-layouts.py` `RESULT PASS`, and the create/build/package loop was rehearsed under Linux `pwsh` with a stand-in executable: three iterations write `briefcase-create.log`, `briefcase-build.log`, `briefcase-package.log` in `$LOG` and `$LOG` is not reassigned. Still unrehearsable on Linux: `briefcase build` (rcedit download), `briefcase package` (WiX 5.0.2 download, `--adhoc-sign`), `msiexec`, registry, COM shortcuts, `taskkill`, the GUI stub's behaviour and `pywin32` under the embeddable Python.

**Retry case (one run, `candidates="B"`):** what failed is a variable-name typo that cost 2 min 20 s (about 5 billed Windows minutes at 2x); it is contained and independently confirmed by the log. The retry adds the first-ever execution of `build`, `package`, the MSI, the fresh install, `doctor`, `serve`, the interpreter and data-dir gates and the Inno-to-MSI upgrade scenario, i.e. all of AC6. Expected cost: 25-32 minutes, worst case the 40-minute cap (50-64 billed minutes at 2x). Remaining risks are the ones listed under "Residual risks for the run" (downloads, 14-minute build cap, GUI-stub stdout, pywin32); each has a time limit and a logged fallback, so a failure after the build step is a candidate finding, not a retry reason. Dispatch: `gh workflow run packaging-probe-windows.yml --ref flight/01-choose-packaging-toolchain -f candidates="B"` (after the fix is committed and pushed).

**MSI for the operator:** none yet (nothing was built). Its artifact will be `m32-probe-msi-<sha>` on the retry run, with a `.msi.sha256` beside it; the operator's guide (step 3) stands.

#### Hosted run 2 (40060408672, 2026-10-24 03:57:26 to 04:06:02, about 8.5 min; `candidates="B"`, windows-2022, flight-branch HEAD 1dd1823)
Evidence: `$HOME/the-one-m32-evidence/windows/run-2/` (`job.log`, `B/`, `runner.txt`, `msi/`). Conclusion `failure` only because the final gate step saw FAIL lines (every other step succeeded). **The MSI built, installed, passed `doctor`, served, uninstalled cleanly, and installed over the Inno install.** Four things went wrong, all traced below to one script defect (the environment-variable restore) plus one lazily created credential, none to the candidate. Windows minutes about 17 billed at 2x.

**Build (`B/BUILD-SUMMARY.txt`, `briefcase-*.log`).** `briefcase create` rc=0 in 58 s, `build` rc=0 in 2 s (rcedit download, stub renamed, details set), `package` rc=0 in 73 s (WiX CLI downloaded and installed by Briefcase); **132 s for create+build+package, about 2 min 55 s for the whole build step** (venv 39 s extra). Output `GleepGlorp AI-0.11.9.dev1.msi`, **121,108,264 bytes (115.5 MiB)**, sha256 `181ede8e5587625442449eb1d2a44fbc683a4bf6ffa1485747278e3da663347a` (re-verified locally against the bundled `.sha256`: OK). Bundle source 261.9 MB (installed 261.9 MB). Embeddable Python 3.11.9, `python311._pth` (isolated, no site), `app_packages` carrying pywin32, pywinpty, pywebview, clr_loader, pystray.

**`.wxs` scope (`B/the-one.wxs`).** `Package Scope="perUserOrMachine"`, `WixUISupportPerUser=1`, `WixAppFolder=WixPerUserFolder` (per-user is the default), `StandardDirectory ProgramFiles64Folder` (which MSI maps to `%LOCALAPPDATA%\Programs` when per-user), `MajorUpgrade` (so the MSI upgrades itself, never the Inno install), Start-menu `ProgramMenuFolder\GleepGlorp AI`, `ARPNOMODIFY`/`ARPNOREPAIR`. The permissions component applies only when `ALLUSERS = 1`. A full WixUI dialog set is compiled in (an "Install Scope" dialog: Just me / All users). The hosted run used `msiexec /qn`-style flags, so the wizard itself was not exercised.

**Fresh install (`B/fresh/SUMMARY.txt`).**
- Install rc=0 in 31 s; **per-user confirmed**: `C:\Users\runneradmin\AppData\Local\Programs\GleepGlorp AI\GleepGlorp AI\GleepGlorp AI.exe` (note the doubled folder name). No `Program Files` directory created.
- Start menu: one link, user scope, `\GleepGlorp AI\GleepGlorp AI.lnk` -> that exe, no arguments. Add/Remove: one entry, "GleepGlorp AI 0.11.9", publisher "GleepGlorp AI", `MsiExec.exe /X{39E34BE4-60A3-4731-AE4B-12074C0F94C2}` (the registry listing says HKLM:\SOFTWARE\...\Uninstall, but the files are per-user; the harness's hive label is not authoritative).
- Stub is a GUI-subsystem exe (PE subsystem 2); no `python*.exe` in the install dir.
- **Stub stdout: `version` printed `GleepGlorp AI v0.11.9.dev1` directly (rc=0) and `doctor` output arrived directly (the `m32run.py` fallback was NOT needed); `serve` also came up directly.** So the GUI stub's CLI cost is smaller than feared on Windows when output is redirected to a file; interactive console behaviour (a GUI-subsystem exe launched from a console does not attach to it, so a person typing `doctor` in PowerShell sees nothing unless output is piped) was not observed and remains a CLI cost for B regardless.
- **Gate 1: `doctor` rc=0 in 7 s, strictly scored `{"pass": true, "rc": 0, "gates": 12, "bad": [], "encoding": "utf-8"}`**: all 12 gates OK, including usearch, embedding model (peak RSS 240 MiB), file watcher (native round-trip), window chrome (build 20348, dark mode only), time zones (345, tzdata 2026d), mcp sdk (mcp 2.3.0, handshake 2025-11-25 and 2026-07-28). `frozen: True` (patch 02 held; `sys.frozen` itself is absent, as expected).
- **Gate 2: PASS**, interpreter resolved to the setup-python `C:\hostedtoolcache\windows\Python\3.11.9\x64\python.exe`, outside the install dir (the same external-Python dependency as on macOS: a real machine needs a Python on PATH; paper item 1).
- **serve `/api/live`: PASS** `{"status":"ok"}` (scratch data dir, port 8490).
- **pywin32 under the embeddable Python: PASS.** Probe copy: `win32api`, `win32job`, `win32con`, `pywintypes` (`pywintypes311.dll`), `winpty`, `webview`, `pystray`, `clr_loader` import from `app_packages`; `mcp.os.win32.utilities` imports with `win32api`/`win32job` bound. `sys.executable` is the stub (an `.exe` in the install dir), argv forwarded (`a b`), stdin/stdout/stderr are real text wrappers, `BRIEFCASE_MAIN_MODULE` works.
- Uninstall rc=0 in 41 s: **clean**, install dir gone, 0 Add/Remove entries, 0 Start-menu links.
- **Gate 4: FAIL (not measured), see classification.** Bare launch (Start-menu path), unscored: no server (output: `...GleepGlorp AI.exe: No module named `), see classification.

**Upgrade over the released Inno installer (`B/upgrade/SUMMARY.txt`).** Inno v0.11.8 (`the-one-setup-0.11.8.exe`, 137,978,952 bytes) installed silently in 12 s to `C:\Program Files\GleepGlorp AI` (all-users Start-menu links `GleepGlorp AI.lnk` and `Uninstall GleepGlorp AI.lnk`, one Add/Remove entry "GleepGlorp AI 0.11.8"). Inno `serve` answered `/api/live`. MSI installed over it rc=0 in 29 s. **Result: side by side, never replaced.** Add/Remove shows **two** "GleepGlorp AI" entries (0.11.8 and 0.11.9); install dirs `C:\Program Files\GleepGlorp AI` (Inno, `the-one-app.exe`) and `...\AppData\Local\Programs\GleepGlorp AI\GleepGlorp AI` (MSI); the Start menu has **two** items named "GleepGlorp AI" in the "GleepGlorp AI" folder (one user-scope -> the MSI exe, one all-users -> `the-one-app.exe`; Windows lists both) plus the Inno "Uninstall GleepGlorp AI". Their data dir is the same default (`%LOCALAPPDATA%\the-one` by `platformdirs`), so the two would share data, which is why the morning guide has a backup. MSI uninstall rc=0 in 41 s: removed only its own entry, folder and shortcut; the Inno install, entry and shortcuts all remained (`inno still runs after the MSI uninstall: rc=1`: see classification). Data dir: not created in this run (the seeded-agent check never reached it).

**Classification of the FAIL lines (the job logged three hard FAILs: gate 4, `agent seeded under the Inno install`, `seeded agent reads back through the MSI install`; the bare launch and the `inno still runs` line are unscored).**
1. **Gate 4 (`rotate-api-credential` under the stub, rc=124 after 60 s, no output): (a) script defect, cause inferred, not proven.** The harness's `Use-EnvVars` restore leaves the variable set to an empty string instead of removing it. Proof from the same run: after the Inno-phase `serve` step, the Inno `the-one.exe version` fails with `Settings port: Input should be a valid integer, unable to parse string as an integer [input_value='']` (`B/upgrade/inno-version-after.txt`), i.e. `THE_ONE_PORT` was `''`. Gate 4 ran right after the fresh-phase `serve` step (`THE_ONE_PORT` restored to `''`) and with `THE_ONE_DATA_DIR` cleared the same way, so the app would hit the same pydantic error; a GUI-subsystem stub has no console, so the failure most likely sits behind an error dialog until the 60 s cap. (A hang instead of an error exit is the inferred part.) **Not measured because of script defect X (env restore).** Whether the app's default data dir resolves to `%LOCALAPPDATA%\the-one` under the stub is therefore unproven for B (the platformdirs path is the same code path as A and macOS B: low risk, but not a result).
2. **Bare launch, `No module named ` (blank): (a) same defect.** The stub-probe step ran just before it with `BRIEFCASE_MAIN_MODULE=m32probe_win`; the restore left `BRIEFCASE_MAIN_MODULE=''`, and an empty module name is exactly what the message shows. So the Start-menu shortcut's behaviour (patch 01's bare start opening the window) is **not measured**; do not read this as "the MSI shortcut cannot start".
3. **`agent seeded under the Inno install` and `seeded agent reads back through the MSI install`: (a) script defects, two stacked.** The same restore defect left `THE_ONE_DATA_DIR=''` after `-Clear`, so the app's data dir was not `%LOCALAPPDATA%\the-one` (that folder never appeared; the live server wrote to an empty-path location relative to the scratch cwd); and the credential is created lazily on the first authenticated call (`GET /api/agents` returned 401 against the MSI serve), while the harness read `api-credential` from the file before any call. Result: **whether the seeded agent reads back across the Inno -> MSI step is NOT measured.** What is established: both installs coexist and both servers answer `/api/live`.
4. The `inno still runs after the MSI uninstall: rc=1` line is the env defect too (the `port=''` error above), not an MSI side effect: the Inno files, entry and shortcuts were present after the MSI uninstall.

No candidate limitation (b) was observed in the hard checks. Open B-specific costs that stay: the doubled install folder name, the Python-on-PATH dependency (gate 2, as macOS), the GUI stub's console behaviour for interactive `doctor`, an unsigned MSI (SmartScreen), and two same-named Start-menu entries and two Add/Remove entries when Inno is also installed.

**Fix (uncommitted, for the record; no further Windows run is planned, so it is unverified on Windows):** `packaging/spike/windows-lib.ps1` `Use-EnvVars` now sets or removes variables through `Env:` (`Remove-Item`/`Set-Item`) instead of `[Environment]::SetEnvironmentVariable(..., $null)`. Not changed: the lazy-credential read in `windows-checks.ps1` (a one-line fix would run `rotate-api-credential` before seeding; left because no run will use it, and the leg's results do not claim it).

#### The operator's morning guide, finalised (supersedes the draft above where they differ)
- **Where:** the run page https://github.com/msieurthenardier/the-one/actions/runs/40060408672 > Artifacts > `m32-probe-msi-1dd18235dc6b2c0138ed085067ecef19ee5ac5fe` (120 MB zip; contains the `.msi` and the `.sha256`). Retention is the Actions default (90 days). A copy is at `$HOME/the-one-m32-evidence/windows/run-2/msi/` (WSL; reach it from Windows as `\\wsl$\<distro>\home\<user>\the-one-m32-evidence\windows\run-2\msi\`).
- **File:** `GleepGlorp AI-0.11.9.dev1.msi`, 121,108,264 bytes. **SHA-256 `181ede8e5587625442449eb1d2a44fbc683a4bf6ffa1485747278e3da663347a`** (compare with `(Get-FileHash -Algorithm SHA256 '<path>').Hash`).
- **What you will see:** double-clicking runs a WiX wizard (the compiled-in dialogs include an Install Scope page: choose "Just me"; "All users" asks for elevation and should not be used for this try). Silent per-user form, no wizard: `msiexec /i "<path>" MSIINSTALLPERUSER=1 ALLUSERS=2`. Install location `%LOCALAPPDATA%\Programs\GleepGlorp AI\GleepGlorp AI`; Start-menu folder "GleepGlorp AI" with a second item "GleepGlorp AI" beside your Inno one (same names; right-click > Open file location tells them apart); Add/Remove Programs gets a second "GleepGlorp AI" entry, version 0.11.9. **It does not replace or touch your Inno install** (the hosted run showed them side by side, and the MSI uninstall left Inno intact). Both use the same data folder `%LOCALAPPDATA%\the-one`, so keep the backup step and do not run both at once.
- **Is it safe to try?** On the hosted machine the MSI installed, `doctor` passed all 12 gates, `serve` answered, and a clean uninstall removed everything. What the hosted run did NOT show: a window opening (no desktop), the Start-menu shortcut starting the app (bare launch was killed by the harness defect), close-to-tray/single-instance, the title-bar tint, and the shared-data upgrade. The first launch may also migrate your real database to a schema newer than Inno v0.11.8 (the build is from the flight branch). **Recommendation: the try is worthwhile (it is the only way to see the window, tray and shortcut behaviours), but only with the step 2 backup taken and step 6's restore ready; if you only want the toolchain decision, the hosted evidence already covers the install/doctor/serve/uninstall/coexistence questions and skipping is reasonable.** Expect the first interactive `doctor` in a PowerShell window to print nothing (GUI stub); pipe it (`... doctor | Out-String`) or use the Inno exe.

#### Windows comparison (A vs B; for `decision-hat`)
**A (keep PyInstaller + Inno)** is the shipped path: a two-exe split gives a console CLI and a windowless app, the Python interpreter is bundled so there is no Python-on-PATH requirement for the app itself (the interpreter for agent `python_exec` is still the external one), Inno handles close-to-tray via `KillRunning` and Restart Manager settings, per-machine install in Program Files, one Add/Remove entry, one Start-menu entry, and an upgrade that replaces itself; the cost is owning a spec and an `.iss` (upkeep listed in the paper half) and not matching a macOS/Linux toolchain. **B (Briefcase MSI)**, measured on a hosted runner: builds in about 3 min, MSI 115.5 MiB, per-user install with a wizard, unsigned, a clean uninstall, `doctor` strictly 12/12, pywin32/pywinpty/webview/pystray importable under the embeddable Python, the CLI works from a redirected stdout; but it is a GUI-subsystem stub only (no console CLI exe; interactive `doctor` is silent), needs an external Python 3.11 on PATH like macOS B, installs beside rather than over the Inno install (two entries, two Start-menu items, shared data dir), and the bare-launch, data-dir (gate 4) and cross-installer data checks are unmeasured because of the harness defect above. On Windows, B shows no blocking limitation but also no win over A: it trades Inno's single console-plus-GUI install for a cross-platform toolchain and a stub with a smaller CLI. Paper half: A's Windows upkeep (two EXE blocks, Restart Manager workaround, signing) is already paid; B would add a per-user scope decision, an MSI upgrade-code and code-signing story, and a doubled folder name to fix.


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

**macOS (hosted macos-15, arm64), run 1 (40058032297, 2026-10-24, 3 min 17 s; B) and run 2 (40058513153, 1 min 38 s; A), DD6.** Evidence roots `$HOME/the-one-m32-evidence/macos/run-1/packaging-probe-macos-logs/B/` and `.../run-2/packaging-probe-macos-logs/A/`. Window, Dock and single-instance columns are N/A (contributor, Flight 3).

| candidate | G1 strict | G2 | serve/live | data dir | signature | size | build time | notes |
|---|---|---|---|---|---|---|---|---|
| A / .app + .dmg | PASS (12 gates, only window chrome skipped) | PASS `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11` | PASS | PASS `~/Library/Application Support/the-one/` | PASS ad hoc, `--deep --strict` rc 0 | .app 177 MB, .dmg 125.2 MB | PyInstaller 39 s; build step about 1 min 14 s cold (run 2; run 1 died at the icon step) | run 2 (40058513153, job 1 m 38 s) is a genuine green: real `.app`, every check ran; bare `open` made a native window (blank dark content, `focused:false`), pyobjc imports present; PyInstaller warnings only for Windows ctypes libs and `httpx2.websockets` |
| B / .app + .dmg (patched) | PASS (12 gates, only window chrome skipped) | PASS `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11` | PASS | PASS `~/Library/Application Support/the-one/` | PASS ad hoc, `--deep --strict` rc 0 | .app 353 MB, .dmg 138.6 MB | about 2 min 20 s cold (create+build+package) | stub `sys.executable` is the stub, argv forwarded, stdout reaches the terminal, `BRIEFCASE_MAIN_MODULE` works; each launch prints two `NSLog` lines; best-effort bare `open` started the server, no window visible in the screenshot |

macOS upkeep notes for B: patch 02's macOS clause held with no change; `universal_build = false` and `min_os_version = 11.0` as configured; the app embeds Python 3.11.9 (`Python.framework`), and the interpreter it resolves is the system/toolcache one (a real macOS install would need a Python installed: paper item 1 stands). A (run 2) adds `packaging/macos/` (379 lines, 5 files) and the Finder `-psn_*` argv shim; see the comparison in `### macos-probe-run`.


**Windows (hosted windows-2022), run 2 (40060408672, 2026-10-24, about 8.5 min; B), DD7.** Run 1 (40060053657) died in the recipe (variable-name collision) before any MSI existed. Evidence root `$HOME/the-one-m32-evidence/windows/run-2/B/`; details and FAIL classification in `### windows-cost` "Hosted run 2".

| candidate | install path | Start menu | Add/Remove | doctor | G2 | serve/live | G4 data dir | build time | MSI size | upgrade over Inno | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A / Inno installer | existing Inno path, not built here; proven by the Concourse per-push build (`build-windows-installer`) and `windows-installer.yml` | same | same | same | same | same | same | n/a | n/a (released `the-one-setup-*.exe`, 138 MB) | n/a (the baseline) | the "before" state for B's upgrade scenario |
| B / Briefcase MSI (per-user, `perUserOrMachine` scope, default Just me) | PASS `%LOCALAPPDATA%\Programs\GleepGlorp AI\GleepGlorp AI\GleepGlorp AI.exe` | one user-scope link `\GleepGlorp AI\GleepGlorp AI.lnk` | one entry "GleepGlorp AI 0.11.9" | PASS strict, 12 gates, rc 0, 7 s, `bad: []` | PASS (setup-python's `python.exe`, outside the install dir) | PASS `{"status":"ok"}` | NOT MEASURED (script defect: env restore left `THE_ONE_PORT=''`, gate hit an error/hang, rc 124) | create 58 s + build 2 s + package 73 s = 132 s (step about 2 min 55 s) | 121,108,264 bytes (115.5 MiB), sha256 `181ede8e...3347a` | side by side, not replaced: 2 Add/Remove entries, 2 Start-menu items, separate dirs; seeded-agent read-back NOT MEASURED (script defects: env restore, lazy credential) | stub is GUI-subsystem; `version` and `doctor` stdout arrived directly (no wrapper needed); pywin32/pywinpty/webview/pystray import OK under the embeddable Python; `sys.executable` is the stub; clean uninstall (0 entries, 0 links, dir gone); bare launch NOT MEASURED (`BRIEFCASE_MAIN_MODULE=''` leaked by the same defect); no window/tray observed (no desktop) |

---

## Decision

### The operator's decision (2026-10-24, `decision-hat`)

**Toolchain: candidate A, PyInstaller on every platform, with Inno Setup kept on Windows.** In the operator's words: "pyinstaller it is."

**AppImage approach for Flight 2: bundle the two small libraries** (the Ayatana AppIndicator typelib and its library, and `libgirepository-2.0`) inside the AppImage, still using the desktop's own WebKitGTK, and make a missing tray indicator degrade rather than fail. In the operator's words: "bundle the two libs". This keeps the mission's "no manual step" criterion for the AppImage.

**Also settled at the session:**
- The overnight calls stand (operator: "All stand"): PR #305 merged with the pre-existing `pip-audit` red; squawk 0250; macOS run 2 on A only; the extra Windows run.
- The real-machine MSI try is dropped: Briefcase is no longer a candidate, so it would decide nothing. `windows-cost`'s morning guide is kept for the record only.
- The Linux window walk-through was skipped by the operator, who decided from the brief and the evidence.

**Applied per DD8:**
- Candidate B's files are removed (`packaging/briefcase/`, B's macOS workflow step, and the Windows probe's B build, which reverts to `main`'s stub).
- A's recipes (`packaging/linux/`, `packaging/macos/`) are marked as the Flight 2 and Flight 3 starting points.
- The mission's "Which toolchain?" question is resolved, with a link here, and the BACKLOG seed points here.

**Handed on (patches none; open items):**
- **Flight 2 (Linux):**
  - bundle the two libraries in the AppImage;
  - fix the pystray `ValueError` fall-through (Planning Notes finding), so a missing indicator degrades;
  - the hide-without-tray behaviour the mission asks for;
  - the single metadata source (the version lives in 3 places today);
  - fresh-VM desktop checks, including WebKit's own sandbox and `bwrap` on a real desktop, and FUSE AppImage launch;
  - the hidden-until-focused window seen with no window manager;
  - keeping the exclude list in step with the build host's GLib.
- **Flight 3 (macOS):**
  - the darwin desktop-session mode (Dock reopen, Cmd-Q, close keeps running);
  - A's blank first paint on a bare launch;
  - the tray and the JS bridge;
  - the Xcode-stub `python3`, and NVM/fnm paths (paper items).
- **Flight 4 (Windows and release):** Inno stays, and reads the single metadata source; release wiring for all packages.

_Below is the Flight Director's brief, written before the session: a recommendation, kept as written._

### Flight Director's decision brief (recommendation)

**Recommendation: candidate A, PyInstaller on every platform, keeping Inno Setup on Windows.** Ship the `.deb` as the primary Linux package, and keep the AppImage, fixed in Flight 2 so it stops depending on two libraries stock desktops lack.

**What the evidence says, per platform:**

- **Linux.**
  - **A's `.deb` passes every hard gate and every soft check** on Ubuntu 26.04 and Debian 13: one copy of the host GTK/WebKit stack, a real Python for tools, the data dir unchanged, the N to N+1 upgrade, single-instance. `apt` resolves its declared dependencies on a bare image, and **one `.deb` serves both distros**.
  - **A's AppImage** passes on Ubuntu except the unpinned tray (no Ayatana typelib on a stock desktop). It fails on Debian 13, whose stock desktop lacks `libgirepository-2.0`, so it cannot load `gi` and opens no window.
  - **B's `.deb`s pass everything, but only with two app patches** (bare start opens the window; Briefcase counts as frozen), and only as **one `.deb` per distro**, each built in Docker against that distro's Python.
  - **B's AppImage does not build.**
- **macOS.**
  - Both candidates pass every hard check on the hosted runner (strict `doctor`, real Python, `serve`, data dir, ad-hoc signature).
  - A is half B's size (`.app` 177 MB against 353 MB; `.dmg` 125 against 139 MB) and builds in about half the time.
  - A's bare launch opened a native window, its first paint blank. B's started the server with no visible window.
  - Both are for the contributors to confirm in Flight 3.
- **Windows.**
  - B's per-user MSI builds, installs, passes strict `doctor`, serves and uninstalls cleanly.
  - But it **coexists with the Inno install rather than replacing it**: two Add/Remove entries, two same-named Start-menu items, two install dirs. Moving to it means a migration step for the one Windows user.
  - Its GUI-subsystem stub gives an interactive console `doctor` no output, so B needs a second console entry point (A already has the two-exe split).
  - A is the existing, proven path, with in-place upgrades by a fixed AppId, Restart Manager and the tinted title bar.
  - The data-dir and shared-data checks were not measured on Windows (a harness defect), and nothing suggests B would differ there.

**Why A:**
1. **No app patches.** B needs two changes to `the_one/` (start-up default and frozen detection) on all three platforms. Both are behaviour changes Flight 2 would have to design, test and gate. A needs none.
2. **One Linux package for both distros**, against one per distro, each tied to its distro's Python.
3. **Windows stays on the proven installer**, with no migration for the operator and the per-push Concourse build unchanged.
4. **One tool across all three platforms in practice**: PyInstaller everywhere, with thin per-platform wrappers. That is also the "one recipe" the mission asked for, once Flight 2 adds the single metadata source.
5. **Smaller and faster on macOS.**

**What A costs, carried to Flights 2-4:**
- **More packaging code to own:** the Linux spec, the exclude list and the runtime hook (about 530 lines), plus `packaging/macos/` (about 380 lines). The host-GTK exclude list must be kept in step with what PyInstaller's gi hooks collect, and that depends on the build host's GLib version.
- **The version lives in three places today.** Flight 2 builds the single metadata source the mission's criterion requires (name, version, identifier, icon), and the `.iss` reads it too.
- **The AppImage's two host dependencies.** Flight 2's options: bundle the small AppIndicator and girepository libraries (not the WebKit stack), and fix the pystray `ValueError` fall-through (the planning finding), so a missing tray degrades instead of failing. Or ship the AppImage with a stated host prerequisite. The mission's "no manual step" criterion favours the first.

**Not recommended:**
- **B everywhere:** the app patches, per-distro packages, a Windows migration, and a CLI gap.
- **A hybrid with B's `.deb` on Linux:** it buys a smaller `.deb` at the cost of the app patches and per-distro builds.

**What the operator decides at `decision-hat`:**
1. A, B or a hybrid.
2. The AppImage approach for Flight 2: bundle the two libraries, or state a prerequisite.
3. Whether to try the MSI on the real machine at all. It is optional for the decision; the hosted run already shows coexistence rather than replacement.
