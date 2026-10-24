# Flight: Choose the packaging toolchain

**Status**: in-flight
**Mission**: [GleepGlorp AI installs like an app on Windows, macOS and Linux](../../mission.md)

## Contributing to Criteria
This flight ships no package. It decides the recipe every later flight builds on, and it retires the mission's highest-impact unknowns before they are paid for on hosted runners.
- [ ] **The frozen runtime works in every build** (evidence only). `the-one doctor` is run inside a Linux bundle from each candidate and inside a macOS bundle on a hosted Mac runner, and its results decide the recipe.
- [ ] **One packaging source of truth, built within the CI budget** (decision only). The flight records which recipe can feed every platform from one metadata source, and what each costs in hosted minutes.
- [ ] **Windows does not regress** and **Upgrades keep the user's data** (evidence only). If Briefcase survives the Linux leg, its Windows installer is tried over the operator's current install, and the result prices the Windows side of the decision.
- [ ] **Linux install, no setup** (evidence only). Each candidate's Linux build is shown to use the desktop's own WebKitGTK, or shown unable to.

---

## Pre-Flight

### Objective
Choose, from evidence, the packaging toolchain the rest of Mission 32 uses: Briefcase on every platform, PyInstaller extended with per-platform wrappers, or a named hybrid. Each candidate is built on Linux (the cheapest platform to validate) and measured against the same hard gates: `doctor` inside the bundle, the desktop window on the host's WebKitGTK, a real Python child spawn, and an unchanged data directory. Then the soft criteria: tray, single-instance focus, upgrade over an older build, size, build time and recipe upkeep. One hosted macOS run builds a `doctor`-only bundle per surviving candidate. If Briefcase is still standing, one hosted Windows run builds its installer, and the operator tries it over the current install. A guided session closes the flight. In it, the operator tries the Linux builds in WSLg, reads the evidence table, and makes the go/no-go call. The winner's prototype recipe stays under `packaging/` as Flight 2's starting point; the loser is recorded and removed.

### Open Questions
- [x] Which candidates? → DD1
- [x] What decides the winner? → DD2
- [x] Where does spike code live, and may it change the app? → DD3, DD4
- [x] How are Linux builds checked, given the operator's host is Ubuntu 24.04 (not a mission target) under WSL2? → DD5
- [x] How many macOS runs, and what do they prove? → DD6 (operator: at most 2 macOS jobs this flight)
- [x] Where does the Windows upgrade test run? → DD7 (operator: a GitHub-built installer the operator downloads and runs)
- [x] What happens to the spike code after the decision? → DD8 (operator: keep the winner)
- [x] Is there a closing HAT? → yes, the guided decision session (`decision-hat`)
- [x] Do macOS arm64 wheels exist for the locked dependencies? → checked offline at planning (Citation Audit): yes, except pure-Python `proxy-tools` (sdist, builds anywhere) and Linux- or Windows-only packages. The macOS run no longer needs to discover wheel gaps.

### Design Decisions

**DD1 — Two candidates, hybrids allowed**:
- **(A) PyInstaller everywhere.** Extend today's freeze to the other platforms:
  - Linux: a one-dir bundle, wrapped as an AppImage (`appimagetool`, extract-and-run, no FUSE needed to build) and a `.deb` (`dpkg-deb`, with WebKitGTK and its introspection typelib declared as dependencies).
  - macOS: PyInstaller's `BUNDLE` `.app`, wrapped in a `.dmg` (`hdiutil`).
  - Windows: unchanged (`the-one.spec` + Inno Setup).
- **(B) Briefcase everywhere.**
  - Linux: its system-package `.deb`, built against each distro's system Python, so the host's GTK and WebKitGTK libraries are used as-is. PyGObject and pycairo come from the pinned closure (DD3) and are compiled inside Briefcase's Docker build against the distro's dev packages. That build needs those build-time packages (the `libgirepository-2.0-dev`/`libcairo2-dev` equivalents), and its `.deb` declares the matching runtime ones. A system package is tied to one distro's Python, so B builds with `briefcase build/package linux system --target ubuntu:26.04` and `--target debian:13` (Docker builds): two `.deb` files where A has one. That count is part of B's upkeep and hosted-minutes score. Its AppImage format is also built (linuxdeploy on an old base that bundles GTK). It is expected to fail gate 3, since PyGObject 3.56 needs `girepository-2.0`, which old AppImage bases lack; that failure is evidence, not a defect. A format that fails a hard gate stops there: the failing gate's evidence is recorded, and it goes through no window, upgrade or later steps.
  - macOS: its `.app`/`.dmg`.
  - Windows: its MSI.
- **Elimination is per platform and per format.** For example, B's `.deb` can pass gate 3 while its AppImage fails.
- **A hybrid is a named per-platform mix** (for example, Briefcase's `.deb` with PyInstaller elsewhere). It is a legitimate outcome if it scores better than either pure option once upkeep is counted.
- No third tool (Nuitka, cx_Freeze, PyApp) is evaluated unless both candidates fail a hard gate on Linux (see Adaptation Criteria).
- Rationale: these are the two the backlog seed and the Architect review named. A is already proven on Windows (12 `doctor` gates, close-to-tray, Restart Manager). B is the one-config tool the mission seed asked to evaluate.
- Trade-off: a third tool might score better and goes unexamined unless both fail.

**DD2 — The rubric: hard gates first, then a weighted comparison**:
- **Hard gates** (any FAIL eliminates a candidate on that platform):
  1. **`doctor` passes strictly.** `the-one doctor` exits 0 from inside the installed bundle, and no gate's detail contains `skipped` in any form (`skipped (…)` or `skipped — …`). The one allowed skip is `window chrome: OK — skipped (not Windows)`. The advisory `runtimes:` lines are outside this check: `node` and `uv` are absent by baseline design and print `not found —`. `doctor` is run twice: once with the pinned `PYSTRAY_BACKEND`, and once with no `PYSTRAY_BACKEND` set, as a user would run it. Both results are recorded, because the desktop-shell probe only imports `pystray`, and the pin can hide a missing Ayatana typelib. This is stricter than `doctor`'s own exit code on purpose. Under Briefcase `is_frozen()` is false, so these gates otherwise downgrade to "skipped" and would let a bundle missing usearch or the catalog seed pass:
     - desktop shell;
     - LLM providers;
     - model catalog;
     - vector store;
     - the file watcher's native round-trip half.
  2. **A real Python, measured independently.** Take the interpreter path `doctor`'s interpreter gate reports, and run it with `-c 'import sys; print(sys.executable, sys.prefix)'`. The prefix must be a system Python, not the app bundle or Briefcase's stub. On the macOS runner, that system Python is the `setup-python` toolcache interpreter. `doctor`'s own interpreter gate always passes when not frozen, so it is not this measurement.
  3. **One copy of the GTK stack, the host's.** `the-one app` opens the window, and `/proc/<pid>/maps` of the UI process shows exactly one copy each of `libglib-2.0`, `libgobject-2.0`, `libgtk-3`, `libgirepository-2.0` and `libwebkit2gtk-4.1`, all from `/usr/lib`. `WebKitWebProcess` (a C binary, which never maps `libgirepository`) shows at most one copy of each, every one from `/usr/lib`. The web-process check stays, because an AppImage's `LD_LIBRARY_PATH` leaking into WebKit's helper processes is the real hazard there. A bundle file listing is supporting evidence only. The hazard is two GLib copies in one process: the bundled one plus the host's, pulled in by host WebKit.
  4. **The data directory is unchanged.** Measured only in a container, with no `THE_ONE_DATA_DIR` override: start `serve`, then list `~/.local/share/the-one` (the `platformdirs.user_data_dir("the-one")` path). `rotate-api-credential` (which prints the credential path) is run only before any data is seeded. This check never runs on the dev host, where an unset override would hit the operator's real data dir.
- **Soft criteria**, scored in the evidence table, each with its measurement:
  - tray: the pinned tray backend and its typelib are present and load inside the bundle. Whether a tray icon actually appears is not scored, because WSLg and bare containers have no StatusNotifier or XEmbed tray host for either candidate; visible-tray checks are Flight 2's fresh-VM work;
  - single-instance focus on a second launch;
  - upgrade over an older build keeps the data dir and the local-API credential;
  - bundle size, and cold build time;
  - recipe upkeep: files and lines a contributor maintains, how many places the version and name live, the number of per-distro artifacts, and the Windows CLI arrangement (a GUI-subsystem launcher has no console, so `doctor` output needs a console app beside it, as the two-exe split does today);
  - the macOS run result (DD6);
  - the Windows cost (DD7);
  - hosted minutes per release.
- The operator decides at the closing leg (`decision-hat`). The table informs that decision and does not compute it.
- Rationale: hard gates are the mission's non-negotiables; everything else is a trade the operator owns.
- Trade-off: the soft criteria are not weighted in advance, so the call is a judgement, by design.

**DD3 — Spike code lives under `packaging/`, outside the root `pyproject.toml`**:
- Candidate A's Linux and macOS recipes go in `packaging/linux/` and `packaging/macos/`, beside `packaging/windows/`.
- Candidate B's config goes in its own `packaging/briefcase/pyproject.toml` (Briefcase reads `[tool.briefcase]` from the `pyproject.toml` in the directory it runs from). It does not go in the root `pyproject.toml`, which Mission 31 also edits.
- **One shared staging step, used by both candidates.** A script under `packaging/` copies `the_one/` into a gitignored staging directory, rewrites `__version__` there to the build's version (DD5's upgrade check), applies the candidate's patch diffs (DD4), and both candidates build from that copy. Briefcase resolves `sources` against the directory holding its `pyproject.toml`, so the staging copy also answers "sources outside the project directory". A local-path requirement (`requires = ["../..[gui,all-llms]"]`) is the fallback, if staging fights Briefcase. Only if neither works does the root `pyproject.toml` take an additive `[tool.briefcase]` section, with the conflict risk logged.
- **Both candidates install the same pinned dependency closure.** That is the hash-pinned `uv export --no-dev --extra gui --extra all-llms` that the Windows CI and the release `pip-audit` use, never a re-resolve of version ranges.
- Build-only tools (`pyinstaller`, `briefcase`, `appimagetool`) stay out of the app's runtime dependencies and out of `uv.lock`, installed per build the way `windows-installer-build.yml` installs PyInstaller today.
- Rationale: the mission's "packaging stays outside the app" constraint, and no merge friction with Mission 31.
- Trade-off: a spike-only staging step may be thrown away along with the losing candidate.

**DD4 — This flight commits no change under `the_one/`**:
- If a candidate needs an app-side change to pass a hard gate, that is evidence about its cost. The change is kept as a diff file under `packaging/<candidate>/patches/`, recorded in the flight log with its reason, and applied by the DD3 staging step to the staging copy only, never to `the_one/`. That way the hosted macOS and Windows jobs, which build from the committed flight branch, run with the same patch the Linux legs proved. Examples: Briefcase not setting `sys.frozen`, so `is_frozen()` is false and `resolve_python` returns `sys.executable`; a bundle-dir rule for a new layout.
- The candidate is scored "passes with patch X" on every platform. Flight 2 implements the winner's patches properly in `the_one/`, with tests, and deletes the diff files.
- Build scaffolding (the staged `__version__` rewrite and the patch diffs, DD3) is not an app change. It happens only in the gitignored staging copy, never in `the_one/`.
- Rationale: the mission's single-seam constraint. Seam changes deserve their own design and tests, not spike code.
- Trade-off: the diffs are re-done in Flight 2, a small duplication.

**DD5 — Linux apparatus: build on the dev host, install in fresh containers, look in WSLg**:
- **Build:** on the dev host (Ubuntu 24.04, WSL2), in a scratch build directory outside the repo tree.
- **Install, upgrade, uninstall and `doctor`:** in disposable `ubuntu:26.04` and `debian:13` Docker containers (both pullable, verified at planning). Both candidates get the same **stock-desktop baseline**: the container first installs `python3` and the distro's desktop GTK basics, as a stock GNOME desktop has them; `node` and `uv` stay absent. Bare images ship without `python3`, which would fail A's gate 2 for an environmental reason. The baseline's exact package list is written in the first leg and applied unchanged to every candidate.
  - The `.deb` installs through `apt install ./file.deb`, which resolves its declared dependencies (so a missing declaration fails).
  - The AppImage runs with `--appimage-extract-and-run` (containers have no FUSE).
  - `doctor` runs headless, and its stdout, `PASS`/`FAIL` lines and exit code are the read path.
- **The window:** inside the target-distro containers, with WSLg's display sockets forwarded (`/tmp/.X11-unix`, and `/mnt/wslg` for Wayland), so the window runs on the real targets' own WebKitGTK. Each instance gets a scratch `THE_ONE_DATA_DIR` and a non-default port.
  - The read path is a screenshot (the operator's eyes at `decision-hat`) plus gate 3's `/proc/<pid>/maps` check.
  - Fallback: if forwarding fails, the window is checked on the dev host (Ubuntu 24.04, not a mission target). B then needs a third, 24.04-targeted build, and the evidence is marked directional.
- **Pinned interpreters.** A freezes with Python 3.11 (a uv-managed interpreter on the dev host, not the host's 3.12), which matches the Windows build and the macOS probe. B's `.deb` runs on each distro's own system Python, recorded per distro at leg start before any gate result is trusted (`uv.lock` has cp313/cp314 x86-64 wheels for every native dependency).
- **Pinned backends.** Every run sets and records these, rather than taking whatever the host or container selects:
  - `PYWEBVIEW_GUI=gtk`;
  - `GDK_BACKEND=x11`, because under Wayland GTK cannot report window position, which would skew the window-state criterion;
  - `PYSTRAY_BACKEND`, plus whether the Ayatana AppIndicator typelib is installed.

  Today, a missing Ayatana typelib makes `import pystray` raise `ValueError`, and `backend()` falls through only on `ImportError`. So the tray (and, when frozen, the desktop-shell `doctor` gate) fails rather than falling back. The first leg pins one tray configuration for both candidates. A declares that typelib as a dependency of its `.deb`, and B's `.deb` declares the same. The fall-through gap is recorded as a finding for Flight 2 (operator, 2026-10-23: no separate squawk).
- **Upgrade:**
  1. Build version N and N+1 of each candidate from the staging step (DD3), which sets both `__version__` and the package version.
  2. Install N, assert `the-one version` prints N, and write data through the app's API.
  3. Stop N: `_select_port` treats a running different version as foreign and would start a second instance.
  4. Install N+1, assert `the-one version` prints N+1, and show the data and the credential intact.
- **Safety:** never port 8484 or 8485, never the operator's default data dir (`settings.data_dir`, read rather than guessed), and every instance started from a scratch working directory and stopped by PID (CLAUDE.md behavior-test safety rule).
- Rationale: the dev host has all the pieces for free, and containers give fresh target distros without a VM.
- Trade-off: no fresh-desktop window check on the target distros until Flight 2.

**DD6 — The macOS probe: one dispatched job building every surviving candidate, at most two jobs in the flight**:
- **Getting a workflow onto `main`.** GitHub offers a manual run only for a workflow file that exists on the default branch. So the first step of `macos-probe` is a small PR to `main` that touches only `.github/workflows/`. It holds the `workflow_dispatch`-only probe workflows: macOS, plus Windows for DD7, so one PR serves both. It touches no file Mission 31 touches, and cuts no release (operator, 2026-10-23). Runs then use `gh workflow run <file> --ref <flight branch>`, which runs the flight branch's copy of the workflow. The PR's stub only needs to define `on: workflow_dispatch` and the job's shape; the real steps can live on the flight branch.
- A `workflow_dispatch`-only workflow (no push, PR or tag trigger) runs one job pinned to `macos-15` (Apple Silicon), not `macos-latest`. That job:
  - builds each surviving candidate's `.app` in sequence;
  - ad-hoc signs it (`codesign --force --deep -s -`);
  - runs the app's `doctor` from inside the bundle (`Contents/MacOS/...`);
  - starts `serve` on a scratch port with a scratch data dir and probes `GET /api/live`;
  - prints a bundle listing and the size.
- The read path is the job log; the doctor output is also uploaded as a small artifact.
- Budget: at most 2 macOS jobs in this flight (operator, 2026-10-23), so one run plus one retry. Before the first dispatch, the workflow is linted (`actionlint` or a YAML parse) and the recipe is exercised on Linux as far as it can be.
- The Python on the runner is pinned explicitly (`actions/setup-python` 3.11). Every run first re-verifies `gh auth status`, remaining Actions minutes and artifact storage.
- The window is not tested on the runner (the Architect: no reliable GUI session). The Xcode-stub `python3` hazard cannot be observed on a runner, which has a real Python. Both are recorded as paper items for Flight 3.
- Rationale: one job warms one runner for both candidates, and the wheel question is already answered offline.
- Trade-off: a failure that needs two fixes exhausts the budget, and the leg then reports the macOS result as partial rather than spending more.

**DD7 — The Windows probe runs only if Briefcase survives the Linux legs, and the operator runs the installer**:
- A `workflow_dispatch`-only `windows-2022` job builds Briefcase's MSI and runs its `doctor` from the installed location on the runner. It publishes the MSI where the operator can download it: an Actions artifact, or a draft GitHub release asset if artifact storage is short. Mission 15 hit the artifact quota. A draft release is allowed under the mission's "draft or pre-release that the operator controls" rule.
- The operator then:
  1. backs up the data dir with a command the leg provides;
  2. runs the MSI over the current Inno Setup install on their own PC;
  3. reports what happened, against a checklist the leg provides: side by side or replaced, the Start-menu entries, Add/Remove Programs entries, data intact, `doctor`, close-to-tray, and the Windows 11 title-bar tint.
- **Rollback, written into the leg:** uninstall the MSI, reinstall the current release's Inno installer from the releases page, restore the data backup if needed.
- **The paper half (always done):** price `pywinpty`, WebView2, the tray, Restart Manager (`CloseApplications=force`), and the Inno AppId upgrade path for each candidate.
- The workflow file for this job lands on `main` in the same small PR as DD6's.
- If Briefcase is eliminated on every format in `linux-briefcase`, the hosted job is skipped with a log note. The paper half still records why Windows stays on Inno.
- Rationale: operator's choice (2026-10-23). Windows 11 Home has no Windows Sandbox or Hyper-V, so there is no disposable local Windows. The operator is the only Windows user and accepts the risk.
- Trade-off: a real install is touched, mitigated by the backup and the rollback.

**DD8 — The decision and the winner's recipe are recorded where Flight 2 starts**:
- **The decision** goes in the flight log ("Decision" section: the choice, the evidence table, the patches the winner needs per DD4, and the open risks handed to Flights 2 to 4).
- **Mission and backlog updates:**
  - the mission's "Which toolchain?" open question is struck through with a link to the decision;
  - the BACKLOG seed gets a pointer to the decision.
- **The winner's recipe** stays under `packaging/`, labelled a prototype in its README: not wired into CI, and no packages published. The macOS probe workflow is kept if A wins (Flight 3 grows it) and rewritten if B wins.
- **The loser's files** are removed in the same leg. In a hybrid, each platform keeps the winning candidate's files for that platform, and the rest are removed. The probe workflow keeps whichever candidate won macOS.
- Rationale: the operator's choice to keep the winner, and one place for Flight 2 to read.

### Citation Audit
Verified against the worktree at `b060d84` (`origin/main` `8a52a39` plus the mission commit):

| Citation | Status |
|---|---|
| `the_one/platform/env.py::is_frozen` — true only when `sys.frozen` is set or `sys._MEIPASS` exists (env.py:155-162); a freezer that sets neither reads as not frozen (DD4) | verified |
| `the_one/platform/interpreter.py::resolve_python` — when not frozen returns `Path(sys.executable).resolve()`; when frozen delegates to `_resolve_frozen_python`, which resolves `THE_ONE_PYTHON` or `python3`/`python` on the cleaned PATH and raises `FrozenInterpreterError` if none (interpreter.py:56-89, 105-147) (DD2 gate 2, DD4) | verified |
| `the_one/platform/interpreter.py::_is_store_alias` — skips the Windows Store stub `python.exe`; there is no macOS equivalent for the Xcode `/usr/bin/python3` stub (DD6 paper item) | verified |
| `the_one/platform/env.py::_common_runtime_dirs` — POSIX list is `/usr/local/bin`, `/opt/homebrew/bin`, `~/.local/bin`, `~/.cargo/bin`, `~/.npm-global/bin`; no NVM/fnm paths (env.py:181-209; M15 F5 debrief Rec 3) | verified |
| `the_one/interfaces/desktop/shell.py::_webview_available` — on Linux probes `gi.require_version("WebKit2", "4.1"/"4.0"/"6.0")` without importing Gtk; on win32/darwin returns True (shell.py:312-332) (DD2 gate 3, DD5) | verified |
| `the_one/interfaces/desktop/shell.py::DesktopSession._close_to_tray` — when the tray fails to start, `_on_closing` is never registered, so × destroys the window directly and the app exits; the failure logs "System tray unavailable — close button will exit the app" (shell.py:811-822; `_close_to_tray`'s no-icon branch, shell.py:411-431, is defensive) (soft criterion; the mission's hide-without-tray change is Flight 2's) | verified |
| `the_one/config.py::_default_data_dir` — `platformdirs.user_data_dir("the-one", appauthor=False)` (config.py:23) (DD2 gate 4) | verified |
| `the_one/diagnostics.py::run_doctor` — returns 0 only when every gate passes; desktop-shell, provider, model-catalog and vector-store gates, and the file watcher's native round-trip half, are hard only when frozen and otherwise read "skipped" (diagnostics.py:998+) (DD2 gate 1; under Briefcase, with `is_frozen()` false, these downgrade, which the leg must account for) | verified |
| `packaging/windows/the-one.iss` — fixed `AppId={{CAEEFB46-…}}`, `PrivilegesRequired=admin`, `CloseApplications=force`, `RestartApplications=no`; the AppId is not a `/D` define (the-one.iss:35, 61, 69-70) (DD7) | verified |
| `uv.lock` — every package has a `py3-none-any` or macOS arm64/universal2 wheel except `proxy-tools` (pure-Python sdist), `pycairo`/`pygobject`/`pygobject-stubs` (Linux-only marker) and `pywin32`/`pywinpty` (Windows-only); `pyobjc-core` and `pyobjc-framework-{cocoa,quartz,security,webkit}` are locked (DD6) | verified |
| Dev host: Ubuntu 24.04.2 under WSL2 with WSLg (`DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`); `gi.require_version("WebKit2","4.1")` succeeds; `/usr/lib/x86_64-linux-gnu/libwebkit2gtk-4.1.so.0.21.10`; `dpkg-deb` and `docker` present; `ubuntu:26.04` and `debian:13` manifests resolve (DD5) | verified |
| `pystray.backend()` (pystray 0.19.5) — honours `PYSTRAY_BACKEND`; on Linux, an `appindicator` backend raising `ValueError` (missing Ayatana typelib) is not caught by the `ImportError` fall-through, so `import pystray` raises on this host (DD5) | verified |
| `the_one/__init__.py::__version__` — hard-coded `"0.11.8"`; the Windows `.spec` imports it from the tree (DD3 staging, DD5 upgrade) | verified |
| GitHub `workflow_dispatch` — a workflow can be run by hand only when its file exists on the default branch; `gh workflow run --ref` then runs that ref's copy (DD6; external knowledge, the Architect's and the Flight Director's) | verified (external) |
| Operator PC: Windows 11 Home, no `WindowsSandbox.exe` (DD7) | verified |
| GitHub repo is private (macOS runners billed at 10×, Windows at 2×) (DD6, DD7) | verified |

### Prerequisites
- [x] Work happens on a branch off `mission/32-installers` in the worktree `/home/cprch/projects/the-one-worktrees/m32-installers`, never in the Mission 31 checkout.
- [x] Fresh target-distro containers (`ubuntu:26.04`, `debian:13`) resolve (planning check).
- [x] WSLg display and the host WebKitGTK 4.1 are present (planning check).
- [x] Operator-confirmed hosted budget: at most 2 macOS jobs and 1 Windows job in this flight.
- [ ] **Re-verified at the start of every leg, not trusted from planning:** `gh auth status`, remaining Actions minutes and artifact storage (`macos-probe`, `windows-cost`; the fallback is a draft release asset, DD7), the Docker daemon and the WSLg display (both Linux legs and `decision-hat`). Remaining minutes: if the billing API does not answer (GitHub's newer billing platform retires the old endpoint), the operator's word is the check.
- [ ] The probe-workflow PR (DD6) is merged to `main` before the first dispatch.
- [ ] `appimagetool` and `briefcase` are installable on the dev host without root (pinned versions recorded in the Linux legs).

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [ ] Prerequisites verified (the three open ones are checked at leg start, by design)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
> **Leg split (in flight, 2026-10-23; see the flight log's Flight Director Notes).** The five steps below were planned as five legs. Execution split step 1 into `linux-pyinstaller-build` and `linux-pyinstaller-gates`, and step 3 into `macos-probe-prepare` and `macos-probe-run`. The step text is kept as written; the Legs list below is the live plan.

1. **Leg 1, `linux-pyinstaller`:**
   - Write the shared staging step (DD3) and the stock-desktop container baseline (DD5).
   - Then candidate A: the Linux spec, the AppImage and `.deb` wrappers, and an exclude list for the host GTK/WebKit stack. First take a bundle listing with no excludes, to confirm what PyInstaller's gi hooks pull in.
   - Build at N and N+1, run the DD2 hard gates and soft criteria per DD5, and fill A's rows in the evidence table.
2. **Leg 2, `linux-briefcase`:**
   - Candidate B under `packaging/briefcase/`, built from the same staging step and baseline.
   - Per-distro `.deb` builds, plus its AppImage.
   - The same gates and the same table. Record any app-side patch (DD4).
   - A format that fails a hard gate it cannot pass even with a patch is eliminated, which ends its later legs.
3. **Leg 3, `macos-probe`:**
   - The small `.github/`-only PR to `main` (DD6).
   - Then the dispatch-only probe for every surviving candidate, run once (a second time only for a contained fix).
   - Record `doctor`, `serve`, the bundle size and listing, and the paper items: the Xcode stub, launchd's `PATH`, and the window lifecycle the shell lacks on darwin.
4. **Leg 4, `windows-cost`:**
   - If B survived: run the Windows job, hand the operator the MSI with the backup, checklist and rollback, and record the result.
   - Always: the paper pricing for each candidate.
5. **Leg 5, `decision-hat`:**
   - Walk the operator through each Linux build (window and second launch, with WSLg forwarded into the target containers), then the evidence table.
   - The operator decides; apply DD8.

### Checkpoints
- [ ] Both candidates (or the survivors) build on Linux, and the evidence table is filled against every hard gate.
- [ ] The probe-workflow PR is merged to `main` (`.github/` only).
- [ ] The macOS probe has run, and its `doctor` result is recorded per surviving candidate.
- [ ] The Windows cost is recorded (hosted plus operator test if B survived; paper always).
- [ ] The operator's go/no-go is recorded, and the winner's prototype recipe is the only one left under `packaging/`.

### Adaptation Criteria

**Divert if**:
- Both candidates fail a hard gate on Linux even with patches. Re-plan: evaluate a third tool, or relax a gate with the operator (for example, bundling WebKitGTK in the AppImage).
- The macOS probe fails the seam (DD2 hard gates 1 or 2) for every candidate within the two-job budget. The operator decides whether to spend more minutes or to carry the risk into Flight 3 with the decision made on Linux and Windows evidence.
- The operator's Windows test damages the current install beyond the written rollback.

**Acceptable variations**:
- A candidate is eliminated early, and its later legs shrink to a log note.
- The decision is a hybrid not spelled out in DD1.
- The macOS probe uses one job, not two.
- The AppImage is evaluated for one candidate only, if the other's AppImage format is unsupported or deprecated; that is itself evidence.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `linux-pyinstaller-build` — The candidate-neutral harness (staging, container images), then candidate A frozen with the host GTK/WebKit stack excluded. Output: an AppImage and a `.deb` at two versions. *(Split from `linux-pyinstaller` after its leg design review.)*
- [x] `linux-pyinstaller-gates` — The gate runner and scorer, and A's four packages measured against every DD2 hard gate and soft criterion. Output: the Evidence Table with A's rows.
- [x] `linux-briefcase` — Candidate B on Linux (a `.deb` per distro, plus its AppImage) from the same staging step and harness. Output: B's rows (unpatched and patched) and patch diffs (DD4).
- [ ] `macos-probe-prepare` — A's and B's macOS recipes, the dispatch-only macOS workflow and a Windows stub workflow, all rehearsed on Linux. No push, PR or dispatch. *(Split from `macos-probe`.)*
- [ ] `macos-probe-run` — After the Flight Director's operator-approved PR to `main` and dispatch: read the run (≤ 2 macOS jobs), score it, and record the macOS rows.
- [ ] `windows-cost` — The paper pricing for each candidate. Since Briefcase survived Linux, also the hosted MSI build and the operator's install over the current Inno install, with backup and rollback.
- [ ] `decision-hat` — The guided session: the operator tries the Linux builds and reads the evidence, then decides. Record the decision and keep the winner's recipe (DD8).

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged (the prototype recipe under `packaging/`, the dispatch-only workflows; nothing under `the_one/`)
- [ ] Tests passing (unit and lint; no browser lane is affected because no app code changes, so the browser gate is not run, and the log says so)
- [ ] Documentation updated (the winner's `packaging/` README marked prototype; the mission and BACKLOG pointers)

### Verification
- The flight log's evidence table has one row per candidate per hard gate and soft criterion, each with its measurement (command and output excerpt, screenshot reference, or job URL).
- The macOS probe's job URL and `doctor` output are linked for each surviving candidate.
- The operator's decision and its reasons are recorded in the operator's words, and the mission's toolchain question points at it.
- `git diff --stat` for the flight shows no change under `the_one/`, and no new push, PR or tag trigger in `.github/workflows/`. The only change that reaches `main` before the flight merges is the `.github/`-only probe-workflow PR.
