# Flight: Windows on shared metadata, and one release

**Status**: completed
**Mission**: [GleepGlorp AI installs like an app on Windows, macOS and Linux](../../mission.md)

## Contributing to Criteria
- [x] **One packaging source of truth, built within the CI budget** (the Windows half, and the whole of it).
  - The Windows installer and the frozen Windows app read their product name, publisher, URL, version, app GUID and file names from `packaging/product.toml` through `packaging/render.py`, and freeze from `packaging/stage.py`'s staged copy, like Linux and macOS (DD3).
  - A version bump is one edit in `the_one/__init__.py`, and `pyproject.toml` reads its version from there (DD6).
  - The Concourse per-push Windows build keeps working, proven before merge with `fly execute` (DD4).
  - macOS and Linux still build on hosted runners only on a tag or a manual run.
- [x] **A release ships all three.**
  - A `v*` tag runs `release.yml`. The release-closure `pip-audit` runs first, and the three platform jobs need it (DD7).
  - The release publishes four packages to one GitHub release: the Windows installer, the macOS `.dmg`, the AppImage and the `.deb`.
  - A manual dry run of the same workflow, which publishes nothing, is green before the tag (DD8).
  - The real release is `v0.12.0`, cut in this flight with the operator's go (the amended charters, DD11).
- [x] **Windows does not regress.**
  - On a hosted `windows-2022` runner, the installed app passes `doctor`, the windowed launcher, close-to-tray, single-instance focus, `the-one quit`, the title-bar state and the version check (DD5).
  - The operator upgrades their own install and confirms it (DD11).
- [x] **Upgrades keep the user's data** (Windows).
  - Installing over a running app quits it gracefully, with the server's shutdown drain, before files are replaced. Anything older or hung falls back to today's force path (DD2).
  - The upgrade from the released v0.11.8 installer is rehearsed on the runner (DD5).
  - Chats, agents, providers, secrets and the credential survive.
  - Uninstalling leaves the data, and the guide says where it lives.
- [x] **The window behaves like a native app on each platform** (no regressions from the boot-policy refactor, DD1).
  - Windows: proven on the hosted lifecycle run.
  - Linux: the GTK smoke.
  - macOS: a standalone `lifecycle` run at the end of leg 2, and again inside the dry run.
- [ ] **macOS install, without an Apple developer account** (the contributor half). *(Carried at landing, operator 2026-10-26: "Land now, carry it". No real-Mac report yet; squawk 0261 is deferred on it, and the report becomes the `macos-app-install` run log when it arrives.)*
  - Contributors with real Macs run `macos-app-install` from `docs/macos-contributor-check.md` against the release's `.dmg`.
  - Their report becomes the behavior test's run log (DD10).
- [x] **Install guides for every platform.**
  - `docs/windows-install.md` covers the graceful upgrade and the data location.
  - README "Install" points every platform at the release page.
- [x] **Existing gates pass.** Unit, browser (every lane) and lint. Packaging code stays out of `the_one/` imports.

---

## Pre-Flight

### Objective
- **Windows on the shared metadata:** bring the Windows app and installer onto the shared packaging metadata and the staged-version build.
- **Graceful upgrade:** an upgrade over a running app quits it gracefully instead of killing it.
- **Boot-policy refactor:** move the per-platform desktop boot rules out of `shell.py` into one policy object, before a third platform grows more branches.
- **One version source:** make the version come from one place.
- **One release workflow:** replace the Windows-only tag workflow with one `release.yml`. It audits, then builds the three platforms and publishes four packages.
- **Dry run:** prove that workflow with a manual dry run.
- **Release and field checks:** cut `v0.12.0`, the first three-platform release, and close the mission's field checks:
  - the operator upgrades their own Windows install;
  - contributors run the macOS check on real Macs.
- **Squawks:** three that would otherwise ship in that release are fixed on the way: 0260, 0261 and 0262.

### Open Questions
- [x] **Release while Mission 31 is active?** → Yes. The operator amended both charters: release during this flight, "but only after as verified as we can get it" (DD11).
- [x] **Release vehicle for the rehearsal?** → A manual dry run of `release.yml` that publishes nothing, then a regular minor release. Contributors download from the release page (DD8, DD10).
- [x] **Who confirms Windows?** → A hosted `windows-2022` lifecycle run (automated). Then the operator upgrades their daily install "just like the contributors will" and reports (DD5, DD11).
- [x] **The boot-policy refactor (Flight 3 debrief, Recommendation 1)?** → In this flight (operator) (DD1).
- [x] **Which squawks ride along?** → 0260, 0261 and 0262 (operator).
- [x] **Checking the Concourse Windows task before merge?** → `fly execute` on the Windows worker; the operator logs `fly` in (DD4).
- [x] **The gate for landing?** → The real `v0.12.0` release and its field checks (operator: "the real v release is the gate"). The operator confirms before the flight closes (DD11).
- [x] **How does the Windows freeze carry a dev or N+1 version?** → Through `stage.py`, as on Linux and macOS (DD3). This came from the Architect's review.
- [x] **A two-step field upgrade on Windows** (v0.11.8 → the dry run's `0.12.0.dev1` installer → `v0.12.0`), so the graceful path meets a real UAC prompt in this flight → proposed in DD11; the operator's answer is needed at plan approval. **Resolved (operator, leg 6):** one step instead ("yolo it"): v0.11.8 → `v0.12.0` directly, no backup. The real UAC prompt met the graceful path on 0.12.0 → `v0.12.1`.

### Design Decisions

**DD1 — Per-platform desktop boot rules move into one policy object (leg 2, operator: in flight)**:
- **Today:** `the_one/interfaces/desktop/shell.py` reads `sys.platform` 17 times:
  - 9 `== "darwin"` reads in `run`/`_boot` (lines 557, 729, 783, 848, 906, 947, 960, 990, 997);
  - 2 win32 reads: the splash border (705) and the show fallback `!= "win32"` (879);
  - 4 Linux `startswith("linux")` reads: the tray detection (908, 928, 933) and the browser-fallback notification (1027);
  - the platform argument to `first_launch_size(_resolve_screens(), sys.platform)` (674);
  - `_webview_available` (286).

  `window_control.py` reads it 4 times (100, 165, 170, 228).
- **Change:** a new `the_one/interfaces/desktop/boot_policy.py` defines a small `BootPolicy`, with one hook or flag per decision, and three instances (Windows, Linux, macOS). It owns:
  - the initial tray mode;
  - how the tray is chosen (macOS none; Linux detects a StatusNotifier or X11 tray; Windows pystray);
  - the splash's pre-show chrome (Windows' DWM border);
  - whether the splash may be destroyed in the current quit state;
  - whether a quit during boot stops without a destroy (macOS);
  - waiting for the main page before the first show (macOS, HAT P1);
  - the native show fallback (Windows);
  - the boot-error teardown (macOS asks to terminate);
  - the pre-loop setup (`macos_dock.install`);
  - the after-loop path S;
  - the first-launch-size platform;
  - the browser-fallback notification (Linux);
  - `webview_assumed_present`;
  - `window_control`'s four branches.
- **Selection:**
  - `state.policy` is set lazily: the first read takes `boot_policy.current()`, which reads `sys.platform` at that moment, and `state.reset()` clears it.
  - `window_control` reads the policy through `state` too. So its functions called from HTTP routes in `serve` mode, or from tests with no `run()` (such as `tests/test_macos_dock.py`'s `darwin` fixture, which patches `sys.platform` and then calls `quit_desktop()` after `state.reset()`), still see the patched platform.
- **The rule, guarded:** after this leg, `shell.py` and `window_control.py` contain no `sys.platform` read, and they do not branch on a policy's identity (`policy.name == …`, `isinstance(policy, MacPolicy)`). An `ast` guard test beside `tests/test_desktop_split_guard.py` pins both.
- **No behaviour change:** proven by behaviour equivalence, not byte identity, because the moved bodies are closures over `_boot` locals and become hooks with parameters.
  - The existing desktop tests pass. That includes their `sys.platform` monkeypatches; they may change only where they must patch the defining module, under the split guard's rule.
  - A per-policy decision-table test is added.
  - Proof on each platform:
    - Linux: the GTK smoke;
    - Windows: leg 3's hosted lifecycle;
    - macOS: a standalone `macos-packages.yml` `lifecycle` dispatch at the end of leg 2 (DD8's budget), then again in the dry run.
- **Squawk 0261 is a behaviour change, so it is a separate phase (2b) and commit after the refactor (2a)**, so that a red macOS row can be pinned on one or the other.
  - The fix: on macOS the splash is shown only after its own `loaded`, bounded (a policy flag).
  - The leg settles how a splash created hidden interacts with `_boot`'s `splash.events.shown.wait(15)`, and with Cocoa starting with only a hidden window. Its design is reviewed (high-risk tier).
  - Proof: the leg-2 macOS run's L1 +1 s screenshot.
  - **Attribution with one run:** the L1 splash-screenshot row belongs to 2b; every other row belongs to 2a. If any non-splash row is red, 2a is at fault. If only the splash row is red, 2b is at fault, and 2b can be reverted so 2a ships alone.
  - **Test rule:** a test that changes `sys.platform` after a policy has been read must call `state.reset()`. The autouse `_reset_desktop_session_state` fixture in `tests/conftest.py` covers the start and end of every test, which is why lazy selection is safe.
  - If the fix needs a change to the shared boot sequence beyond the darwin splash path, it escalates (the squawk's rule), and 2a ships alone.
- **Rationale:** Flight 3's debrief rated this Important before Windows adds anything. The boot sequence already interleaves three platforms.
- **Trade-off:** a refactor of macOS code that only hosted runs can prove, bounded by the decision-table test and an early macOS run.

**DD2 — An upgrade over a running app quits it gracefully, then always force-checks (probe first, legs 1 and 3)**:
- **Today:** `packaging/windows/the-one.iss` sets `CloseApplications=force` and `RestartApplications=no`, and its `PrepareToInstall` calls `KillRunning`, which runs `taskkill /F /IM the-one-app.exe` and `/IM the-one.exe`. The server never drains.
- **Design (settled on paper; the probe confirms it, not ranks it):**
  1. `PrepareToInstall` runs `ExecAsOriginalUser('{app}\the-one.exe', 'quit --wait', …)` with a bounded wait, if `{app}\the-one.exe` exists.
     - The installed CLI resolves the user's own data dir and credential itself. That is why this candidate beats a WinHTTP call from Pascal, which would need the original user's `%LOCALAPPDATA%` from an elevated process.
     - No version gate: v0.11.8's `cli_entry` has no `quit` branch, prints its usage and exits 0, which is harmless.
     - Exit codes are not trusted: 0 also means "not running" or "serve-only".
  2. Then it checks the process is gone.
  3. Then it always runs `KillRunning`, which is a no-op when nothing is left.
  4. The installer never waits unbounded and never fails an install because the quit failed. It starts the CLI with `ewNoWait`, then polls for the process to exit, with its own 90 s bound. The CLI's own bound (a 5 s POST plus a 75 s `_wait_for_exit`) sits inside that.
  5. **Uninstall gets the same sequence:** `CurUninstallStepChanged(usUninstall)` runs quit, then the process-gone check, then `KillRunning`. Today's `.iss` has no uninstall-time code, so a close-to-tray app could hold files in `{app}`.
- **What the probe (leg 1) can and cannot answer:**
  - W3 records the order of `PrepareToInstall` and the Restart Manager check in the `/LOG`. It uses a probe `.iss` variant without `KillRunning`, because with today's `.iss` the RM never sees the app.
  - W4 proves the quit runs from the installer context and the drain line appears.
  - **The runner cannot prove elevation:** on `windows-2022`, UAC is off and the job is already an elevated `runneradmin`, so `ExecAsOriginalUser` runs with the same token. W4's elevation half is **field-only**. The graceful path under a real UAC prompt stays unproven until the operator's field upgrade (DD11), and the flight log says so.
- **macOS has no installer hook** (a drag replace). The guide keeps "quit first" (Flight 3 DD5).
- **Rationale:** Flight 3 debrief, Recommendation 4. `the-one quit --wait` (`the_one/main.py`) already performs the graceful quit.
- **Trade-off:** an upgrade from v0.11.8 still takes the force path, because v0.11.8 has no quit route.

**DD3 — Windows reads `product.toml` and freezes from the staged copy (leg 3a)**:
- **The `[windows]` section in `packaging/product.toml`:**
  - `app_guid`: the frozen `CAEEFB46-2698-4048-AD9F-0120D0B7174A`, pinned to that value by a test. It must never change, or it orphans installs. It is not `app_id`.
  - *(Leg 1 finding, probe run `40246340174`):* the shipped line `AppId={{CAEEFB46-…-0120D0B7174A}}` gives the effective AppId `{CAEEFB46-…}}`, and the uninstall key `{CAEEFB46-…}}_is1`, with two closing braces. The rendered `.iss` must reproduce that line byte for byte. That is the identity every release has used.
  - `install_dir_name`: `GleepGlorp AI`.
  - `setup_file_stem`: `the-one-setup`. It is kept, so Concourse's MinIO glob `the-one-setup-*.exe` still matches.
  - `cli_executable` and `gui_executable`: `the-one`, `the-one-app`.
  - `publisher`.
  - `render.load` merges every section into one key namespace and rejects duplicates, so `[windows]` keys never reuse a name such as `executable`.
- **Rendering:**
  - `render.py` gains `--out FILE`, which writes UTF-8 with LF line endings. The Windows recipe uses it on every Windows host, because Windows PowerShell 5.1's `>` writes UTF-16LE. The Linux and macOS build scripts keep stdout, so no macOS build code changes here.
  - `packaging/windows/product.iss.in` (`#define` lines) renders to a gitignored `packaging/windows/product.iss`, which `the-one.iss` `#include`s. It replaces the hard-coded `AppName`, `DefaultDirName`, group, shortcut names, `OutputBaseFilename` and the `0.2.0` fallback.
  - The version comes from `render.load` (the strict grammar).
- **The freeze is staged.** Today `packaging/windows/the-one.spec` freezes from the repo (`pathex=[_REPO_ROOT]`, `from the_one import __version__`) after `pip install -e .`. So a `--version` or N+1 would change the installer but not the frozen app.
  - Windows now freezes from `packaging/stage.py --target windows --version V`, and the spec requires `M32_STAGE`, as the Linux and macOS specs do.
  - **`stage.py` must work without git.** Today `main()` always calls `repo_toplevel()` (`git rev-parse --show-toplevel`) and dies if that fails. Its `git apply` branch never runs on Windows, because there is no `packaging/windows/patches/`. Under `fly execute`, `.git` is not uploaded (and the worktree's `.git` is a gitlink to a Linux path), and git on the Windows worker's PATH is unproven.
    - Leg 3a adds a fallback that needs no git: when `rev-parse` fails, the outside-the-repo check compares against `REPO.resolve()`, and git is required only when patches exist. A unit test covers it.
  - **The stage directory:** each build passes `--out` inside its own working directory, as a sibling of `repo` (still outside the repo). The Concourse Windows worker runs tasks uncontainerised, so a shared `~/the-one-m32-build/stage-windows-<ver>` would let a `fly execute` and a per-push build of the same version clobber each other.
  - The editable install leaves the freeze path, on both GitHub and Concourse. The leg checks that setuptools' editable finder cannot shadow the staged `pathex`.
  - The spec imports `render` directly (stdlib only) for its two exe names. It takes the version from the staged copy, and is not rendered itself.
  - **`/DAppVersion` is dropped.** The rendered `product.iss` is the only source of `AppVersion`. `render.py --set version=V` and `stage.py --version V` must name the same `V`, and a test pins that agreement.
  - **The probe mode** (leg 1) builds with today's unstaged recipe. It stays frozen as a historical mode once 3b lands.
  - **The Windows `PATH`-walk tests** (the Flight 3 debrief's action item) are Linux-run unit tests that simulate win32, as `test_windows_alias_shadowing_walks_to_the_real_python` does. They cover `PATH` order, the `WindowsApps` alias, `py.exe`, and a missing interpreter. They add no skips.
- **Tests:**
  - `test_every_template_renders` picks up the new template.
  - Linux and macOS render output stays byte-identical (Flight 3 DD8's rule).
  - A test pins the GUID, and another pins the rendered effective `AppId={{…}` line, whose brace escaping is easy to break.
- **Not done here:** merging the Linux/macOS shell helpers into one library (Flight 3 DD8's deferral). The release workflow composes the three platform workflows (DD7), which is the consolidation the mission needs. A bash/PowerShell helper merge would re-prove macOS for no user-visible gain. It is a debrief carry-forward.

**DD4 — The Concourse Windows task stages and renders too, proven with `fly execute` before merge (leg 3a, operator)**:
- **Change:** `ci/tasks/windows-installer-build.yml` runs `stage.py` and `render.py --out` (with the build venv's Python) before the freeze and `iscc`. It keeps its `doctor` needles and the MinIO publish (the pipeline's second task).
- **Proof:** a Developer runs `fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=<worktree>`. It uploads the worktree minus gitignored files.
  - The operator must log in first (`fly -t the-one login`). At the leg, `fly -t the-one status` and the worker's state are re-checked.
- **Safety:**
  - The worker is the operator's PC. `fly execute` only stages, freezes, runs `doctor` and builds the installer, as the per-push build already does. It never installs, launches the app or publishes, and its output is discarded.
  - One execution at a time, never beside a local test gate.
  - The task's Inno comes from an unpinned `choco install innosetup`. The run records the ISCC version (DD5's environment rule) and whether git is on the worker's PATH.

**DD5 — The Windows apparatus: `windows-packages.yml` on a hosted `windows-2022` runner, premise-probed first (legs 1 and 3b)**:
- **A new reusable workflow,** `.github/workflows/windows-packages.yml`, mirrors `macos-packages.yml`:
  - `workflow_dispatch` and `workflow_call`;
  - inputs `version` and `mode` (`full`, `lifecycle`, `probe`);
  - publishes nothing; reads no secret;
  - a job timeout and per-step timeouts;
  - a concurrency group that never cancels a running build.
- **Artifact names are unique in a composed run:** `windows-installer` and `windows-packages-logs`, never matching `evidence-*` (the pattern `linux-packages.yml`'s summary downloads). Only N's installer is uploaded, never N+1's. `windows-installer` keeps 14 days, like the `.dmg`, so the dry run's `0.12.0.dev1` installer still exists for DD11's field upgrade. The flight log records the gap between legs 5 and 6.
- **`full`:** stages, freezes and runs strict `doctor` with today's by-name needles. It runs the frozen `serve` `/api/info` version check (now the staged version) and the single-instance probe (both moved from `windows-installer.yml`). It builds the installer and uploads it.
- **`lifecycle`:** `full`, then builds N+1 (`render.py --next-version`) and runs `packaging/windows/lifecycle.ps1`, writing PASS/FAIL rows to `lifecycle/SUMMARY.txt`:
  - **Old-to-new:** download and silently install the released `the-one-setup-0.11.8.exe` (as Flight 1's run `40060408672` did), start it, create a data marker, then silently install N over it. Checks:
    - the force path is logged;
    - the `{app}` dir is the same;
    - one Add/Remove entry and no duplicate Start-menu links;
    - the marker survives;
    - N answers `/api/info` with N's version.
  - **N:** the Start-menu shortcut; `doctor` from `{app}`; launch `the-one-app.exe` and `/api/window/state` shows it visible; `GET /api/window/chrome`'s DWM results (the runner's Server 2022 build 20348 reports "dark mode only").
  - **Close:** `WM_CLOSE` leaves the process alive and the state hidden (close-to-tray).
  - **Second launch:** one process, the window shown and focused.
  - **Geometry** is restored on relaunch.
  - **N → N+1 while N runs:** the DD2 path is logged, N exits with its drain line, N+1 answers `/api/info` with N+1's version, and the marker survives.
  - **`the-one.exe quit --wait`** quits N+1.
  - **Uninstall while running:** a silent uninstall with the app started. `{app}` is gone, no process is left, and the data dir remains.
- **The FAIL rule:** the job reads red on any `^FAIL` row, a missing summary or a failed step (Flight 3's anchored rule).
- **Environment rule:** every summary's header records the runner image version, the ISCC version, Windows' build and the UAC state. The release and Concourse checks assert the same Inno major.minor the probe ran.
  - **What the runner cannot represent** (field-only, DD11): the Windows 11 title-bar tint, a real UAC prompt, and Windows 11 Explorer's notification area.
- **Ports:** the runner's data dir is its own, so port 8484 is safe on the ephemeral runner (`windows-installer.yml` uses it today). The 8484 rule protects the operator's PC.
- **Leg 1's probe (`mode=probe`):** each premise has a positive control and a fail-loud row (Flight 3 debrief, Recommendation 2), and a row that did not run prints `FAIL not-run`:
  - **W1:** the runner session shows a WebView2 window that `/api/window/state` reports visible. Positive control: a screenshot.
  - **W2:** the notification area exists, the tray starts, and `doctor`'s `tray:` line says so.
  - **W3:** a silent upgrade over a running app with the RM alone (the variant `.iss` without `KillRunning`), with the `/LOG` ordering recorded.
  - **W4:** `quit --wait` through `ExecAsOriginalUser` from the installer context, and the app's drain line. Positive control: the same quit from the runner's shell first. Elevation is field-only, as DD2 says.
  - **W5:** `WM_CLOSE` to the main window takes the hide path, not exit.
  - **W6:** the v0.11.8 release installer downloads and installs silently, the apparatus for the old-to-new row.
- **Observation surfaces:** `/api/window/state` (`the_one/interfaces/web/app.py`), `/api/window/chrome`, `/api/info`, the Inno `/LOG`, the windowed app's log file (from `ensure_stdio_streams`), `tasklist`, the uninstall registry key and screenshots. All are uploaded.
- **Budget:** Windows bills 2x. At most 8 Windows dispatches outside the dry run and the release, about 15-20 min each: probe 2, lifecycle 4, plus 2 spare.

**DD6 — One version source, the strict grammar end to end (leg 4a)**:
- **`pyproject.toml`:**
  - `version = "0.11.8"` becomes `dynamic = ["version"]` with `[tool.setuptools.dynamic] version = {attr = "the_one.__version__"}`.
  - `uv.lock` is regenerated with the pinned uv (`0.10.0`, as in `linux-packages.yml`), so the lock's `revision` does not move. The leg records what uv writes for a dynamic editable project.
  - `tests/test_packaging_metadata.py::test_pyproject_version_matches_dunder_version` is renamed and inverted to pin the dynamic declaration (renamed, not deleted).
  - Both files are shared with Mission 31: the edits are additive, and the branch rebases on `main`.
- **The lanes that check the lock:**
  - they are `uv sync --locked` in `ci/tasks/{lint,test,bwrap,browser,windows-tests}.yml`, `uv export` in `pr-lint.yml` and the Concourse Windows task, and the closure stamp in `scripts/windows_test_copy.py`;
  - these lanes do not all run the uv that regenerates the lock:
    - uv 0.9.30 in the `ci/tasks/{lint,test,bwrap,browser}.yml` image (`0.9.30-python3.11-bookworm`) and in `windows-tests.yml` (`pip install uv==0.9.30`);
    - an unpinned uv in `pr-lint.yml` and `windows-installer-build.yml`.
  - The leg proves `uv sync --locked` and the export against the regenerated lock with each lane's own uv version, and records which version wrote the lock.
  - `release.yml`'s audit export adds `--frozen`. `pr-lint.yml` deliberately keeps checking the lock (no `--frozen`).
- **The release gate:**
  - a `release.yml` `version` job, plus a unit test through `render.load`, requires the tag to be exactly `v` + `__version__`, with a final `X.Y.Z` (no `.devN` on a tag);
  - the tagged commit must be an ancestor of `origin/main`;
  - a dry run accepts `X.Y.Z.devN` through its `version` input;
  - `CFBundleVersion` for a final release is `patch*10000+9999` (Flight 3, unchanged).
- **The bump:** `__version__` becomes `0.12.0` in the flight's last code commit (leg 6, before the tag).

**DD7 — `release.yml` composes the three platform workflows (leg 4a)**:
- **Triggers:** `push: tags: ["v*"]` and `workflow_dispatch`.
- **Concurrency:** its own group, `release`, with `cancel-in-progress: false`.
- **Jobs:**
  - `audit`: the release-closure `pip-audit`, with `pr-lint.yml`'s extras and flags, plus `--frozen` on the export.
  - `version`: DD6's gate. It outputs the version, and checks out with `fetch-depth: 0` so the ancestor-of-`main` check can run.
  - `windows`, `linux`, `macos`: `uses:` the three reusable workflows, all `needs: [audit, version]`, so a finding stops the release before any build time. On a tag, `mode=full`. On a dispatch, the modes and which platforms run come from inputs.
    - On a `push`, `inputs.*` is empty, so every expression needs a fallback, for example:
      - `if: github.event_name == 'push' || contains(format(',{0},', inputs.platforms), ',windows,')`;
      - `mode: ${{ inputs.windows_mode || 'full' }}`.
    - The tag path first runs at the real release, so a unit test parses `release.yml` and pins these expressions.
  - `publish` (tag only; `ubuntu-latest`; `contents: write`):
    - needs all three platform jobs;
    - downloads `windows-installer`, `linux-packages` and `macos-dmg`;
    - selects the four packages by their exact file names for the version (never a glob, never an N+1);
    - writes `SHA256SUMS`;
    - creates the release as a **draft**, uploads all five files, then publishes it. A re-run finds the existing draft and uploads with `--clobber` before publishing, rather than failing on create;
    - keeps the notes logic (`scripts/release_notes.py`, `docs/releases/$TAG.md`), replacing the Windows-specific `"$TAG — Windows installer"` generic title with `"$TAG"`;
    - its `if:` is `github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')`, so a dispatch never publishes.
- **Dispatch inputs:**
  - `version` (string, empty = `__version__`);
  - `platforms` (string, default `windows,linux,macos`, so a failed platform can be re-run alone);
  - `macos_mode` (`full`|`lifecycle`, default `full`);
  - `windows_mode` (`full`|`lifecycle`, default `full`).
- **Permissions:** `contents: read` at the top. The callees declare `contents: read`, and only `publish` raises to `write`.
- **Retired:**
  - `windows-installer.yml` is deleted in the same change. Its smoke moves to `windows-packages.yml` (DD5), its publish to `release.yml`.
  - Flight 1's leftover stub `.github/workflows/packaging-probe-windows.yml` is deleted too.
- **`.dmg` retention:** `macos-packages.yml`'s `on:` block is unchanged. Its `.dmg` artifact's retention rises from 7 to 14 days (DD10).
- **Standalone runs:** none during a release. The fixed groups `linux-packages`/`macos-packages` hold one pending slot, and a standalone dispatch could displace the release's pending job.
- **Stubs:** GitHub dispatches only workflows on the default branch. So there are two `.github/`-only stub PRs (Flights 2-3 pattern), each needing the operator's go:
  - `windows-packages.yml`'s `on:` block, at leg 1;
  - `release.yml` (dispatch-only, the inputs above, no tag trigger, no publish job), at the end of leg 4a, once its inputs are designed. Its inputs then freeze.
  - The tag trigger arrives with the flight's merge.

**DD8 — The dry run is the release's rehearsal (leg 5)**:
- **The command:** `gh workflow run release.yml --ref flight/04-windows-and-release -f version=0.12.0.dev1 -f macos_mode=lifecycle -f windows_mode=lifecycle`.
- **What it proves:**
  - the audit and version gates;
  - the three platform jobs and their four packages;
  - the Windows `lifecycle`;
  - the macOS `lifecycle` (the refactor and 0261 again, after legs 3-4);
  - the composed run's artifact names;
  - concurrency inside the called workflows.
  - `publish` reads as skipped. Its remaining risk (the `gh release` steps) is first exercised at the tag. The draft-then-publish order keeps a partial upload unseen.
- **Fixing:** a red row is classified as a product defect, a harness defect or a runner limit, fixed, and the failed platform re-run alone through `platforms`.
- **The macOS budget for the whole flight is 4 runs:** leg 2's standalone lifecycle, the dry run, the release tag, and one spare that stays spare (Flight 3 debrief). A patch release is another run each. A fifth run needs the operator.

**DD9 — The three squawks**:
- **0260 (the model catalog never refreshes)** (leg 4b):
  - The seed drops the retired `claude-3-5-haiku-20241022`, and any other pair the live fetch lacks. The live fetch is re-run at the leg, because it drifts.
  - The test is self-contained: a projected-catalog fixture of a few lines, and the guard accepting it. No upstream dump is committed; snapshot-style golden files are not committed (operator rule).
  - The guard's design is unchanged.
  - The recurrence risk is recorded in the mission's Known Issues at the leg: the next model models.dev drops stops refreshes in shipped builds again. A guard-tolerance redesign needs design work, so it is not a squawk.
- **0261 (the blank splash)** (leg 2b): with DD1.
- **0262 (the docs)** (leg 4b), additive in `the_one/agents.md` and `CLAUDE.md`:
  - the test-patch rule;
  - the pywebview/PyObjC upgrade checklist (the canary plus a `lifecycle` dispatch);
  - "macOS CI is hosted-only".
- **Records:** each squawk gets its corrective action, verification and sign-off from the leg's review, and is marked `completed` in the flight's commit.

**DD10 — The contributor check runs against the release (leg 6)**:
- **Updates in leg 4b** to `tests/behavior/macos-app-install.md` (draft) and `docs/macos-contributor-check.md`:
  - install from the GitHub release page;
  - the Flight 3 debrief's additions: a real zsh with nvm on `PATH`, logout while running, and a quit during boot;
  - a sentence on downloading an Actions artifact: a zipped `.dmg`, and sign-in required.
- **Versions:**
  - N is the dry run's `0.12.0.dev1` `.dmg` (14-day artifact).
  - N+1 is the `v0.12.0` release `.dmg`.
  - Step 9's N+2 (installed over a running N+1) is deferred to the first patch release. The run log records the deferral, and step 9 is marked as waiting on it.
- **The run log:** contributors are human Executors who return the filled checklist and screenshots. The Flight Director writes the run log from those, with the Validator's judgments made on the returned evidence (Flight 3's "evidence HAT").
- **A FAIL** is a patch-release candidate. If the operator accepts it as a known issue, it is not a landing blocker.

**DD11 — The release and the field checks are the gate (leg 6, interactive)**:
1. **Merge:** the operator reviews and merges the flight PR to `main`. It carries `__version__ = "0.12.0"` and `docs/releases/v0.12.0.md`, whose text the operator approves.
2. **Tag:** the operator gives the go. The Flight Director re-checks `gh auth status`, then pushes `v0.12.0`.
3. **Publish:** `release.yml` publishes.
4. **Windows field upgrade, proposed in two steps** so the graceful path meets a real UAC prompt in this flight:
   - the operator backs up `%LOCALAPPDATA%\the-one`;
   - upgrades from v0.11.8 to the dry run's `0.12.0.dev1` installer (the force path);
   - starts it;
   - upgrades to `v0.12.0` (the graceful path);
   - then checks the tray, the Windows 11 tint, single instance, and that their data survived.
   - If the operator prefers one step (v0.11.8 → v0.12.0), the graceful path under UAC is recorded as unproven until the first patch release.
5. **macOS:** contributors run their check (DD10).
6. **Linux:** the release's `.deb` and AppImage have already passed the container gates in the run.
7. **Issues** become patch releases (`v0.12.1` and on). Each is a fixing commit on a branch, a PR, a merge and a tag, with the operator's go.

- **Landing:** the flight lands only when the operator confirms. Leg 6's artifacts go in a follow-up PR, as Flight 3's debrief did.
- **Outward steps that need the operator's go:**
  - pushing the branch;
  - the two stub PRs and their merges;
  - each dispatch, counted against DD5 and DD8;
  - the merge to `main`;
  - each tag.
- **External sessions are re-checked at every leg that uses them:**
  - `gh auth status`;
  - `fly -t the-one status`, and the Concourse worker's state;
  - the host load before any gate or `fly execute`: `uptime`, plus other sessions' test processes (Mission 31 shares the host; at most 3 browser lanes host-wide; the unit tier never beside lanes).

**DD12 — Verification layers**:

| Layer | Proves | Where |
|---|---|---|
| Unit | the policy hooks and decision table, the guard, the render, GUID and spec pins, `--out`, the version gate, the 0260 fixture, the Windows PATH walk | `make test-unit` (12 skips expected) |
| Linux GTK smoke | the refactored boot on GTK | `packaging/linux/checks/gtk-smoke.sh` |
| Hosted Windows | DD2 (without elevation), DD5's lifecycle rows including old-to-new | `windows-packages.yml` |
| Concourse | the staged, rendered per-push task builds | `fly execute` (DD4) |
| Hosted macOS | the refactored Dock mode, 0261 | leg 2's `lifecycle`; the dry run |
| Lock lanes | the dynamic version under `uv sync --locked` and `uv export --frozen` | DD6's list |
| Release | `publish` | the `v0.12.0` tag |
| Field | Windows upgrade under a real UAC prompt, the Windows 11 tint; macOS on real Macs | the operator; contributors (DD10, DD11) |
| Gates | unit, browser (13 lanes, `--parallel 3`, netns, WebKit required), lint | the flight-end gate (leg 5) |

### Citation Audit

Verified against the worktree at `f98f2c7` (`origin/main` after #314). Corrected after the Architect's two reviews (the `shell.py` count; `stage.py`'s git dependency):

| Citation | Status |
|---|---|
| `the_one/interfaces/desktop/shell.py` — 17 `sys.platform` reads: darwin 557, 729, 783, 848, 906, 947, 960, 990, 997; win32 705, 879; linux 908, 928, 933, 1027; `first_launch_size(..., sys.platform)` 674; `_webview_available` 286 | verified (Architect re-count) |
| `the_one/interfaces/desktop/window_control.py` — `sys.platform == "darwin"` at 100, 165, 170, 228 | verified |
| `tests/test_macos_dock.py` — a `darwin` fixture patching `sys.platform`, then `quit_desktop()` after `state.reset()` | verified (Architect) |
| `packaging/windows/the-one.iss` — `AppId={{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}`, `#define AppVersion "0.2.0"`, `CloseApplications=force`, `PrepareToInstall` → `KillRunning` (`taskkill /F`) | verified |
| `packaging/windows/the-one.spec` — `_REPO_ROOT` from `SPECPATH`, `from the_one import __version__`, `pathex=[_REPO_ROOT]` (not staged) | verified |
| `packaging/stage.py` — `--target`, `--version`; `main()` always calls `repo_toplevel()` (`git rev-parse`) and dies without git; `use_git` matters only when patches exist; `--out` defaults to `$M32_BUILD` or `~/the-one-m32-build` and `rmtree`s its stage dir | verified (corrected, cycle 2) |
| `packaging/product.toml` — no `[windows]`; `app_id = "ai.gleepglorp.GleepGlorpAI"`; `[linux] executable` exists (namespace clash to avoid) | verified |
| `packaging/render.py::RELEASE_RE`, `_release_parts`, `load` (one key namespace, duplicates rejected, `version` override) | verified |
| `pyproject.toml` — `version = "0.11.8"`, `setuptools.build_meta`; `uv.lock` `the-one` `0.11.8` editable | verified |
| `tests/test_packaging_metadata.py::test_pyproject_version_matches_dunder_version` | verified |
| `.github/workflows/windows-installer.yml` — tag-only, `pip-audit` → build, doctor needles, `/api/info` version, `_select_port`, notes via `scripts/release_notes.py`, `cancel-in-progress: true` | verified |
| `.github/workflows/linux-packages.yml` / `macos-packages.yml` — `workflow_call`; artifacts `linux-packages` (3 d), `macos-dmg` (7 d); fixed concurrency groups | verified |
| `.github/workflows/packaging-probe-windows.yml` — Flight 1's stub, still on `main` | verified |
| `.github/workflows/pr-lint.yml` — `uv export --no-dev --no-emit-project --extra gui --extra all-llms`; `pip-audit --disable-pip -r` | verified |
| `ci/tasks/windows-installer-build.yml` — Windows PowerShell, choco Python 3.11 + unpinned Inno, `pip install -e .`, freeze, needles, `iscc /DAppVersion=$ver` | verified |
| `ci/windows-installer.pipeline.yml` — tracks `main`; MinIO glob `the-one-setup-*.exe` | verified |
| `the_one/main.py` quit — read-only credential; 404/405 → "too old"; `--wait` → `_wait_for_exit` (75 s); exit 0 also for not-running and serve-only | verified |
| v0.11.8 `cli_entry` — no `quit` branch (prints usage, exit 0) | verified (Architect, at the tag) |
| `the_one/config.py::_default_data_dir` — `platformdirs.user_data_dir("the-one", appauthor=False)` | verified |
| `the_one/interfaces/web/app.py` — `@app.get("/api/window/state")` | verified |
| `the_one/llm/model_catalog.py` — the seed-coverage guard loop, "fetch missing seed pair" | verified |
| `tests/test_macos_runtime_seam.py::test_windows_alias_shadowing_walks_to_the_real_python` — the only Windows walk test | verified |
| `tests/behavior/macos-app-install.md` — draft, never run, 12 steps; step 9 needs N+2 | verified |
| Inno `ExecAsOriginalUser`, `/VERYSILENT /SUPPRESSMSGBOXES /LOG=`, RM ordering versus `PrepareToInstall` | documented Inno 6 behaviour; in this installer → leg 1 (W3, W4) |
| The hosted `windows-2022` runner shows a WebView2 window and has a notification area | unverified → leg 1 (W1, W2) |

### Prerequisites
- [x] `origin/main` at `f98f2c7`; the branch `flight/04-windows-and-release` is cut from it in the worktree.
- [x] `gh` is authenticated (re-checked at each leg that uses it). The repo is private, with three collaborators.
- [ ] The operator logs in to Concourse (`fly -t the-one login`) before leg 3a. It is re-checked at the leg.
- [ ] The operator's go for the stub PRs, their merges and the dispatch budgets (DD5, DD8), asked for at leg 1.
- [x] Mission 31 is active in `~/projects/the-one` and is never touched. The host test policy holds.
- [x] Both charters are amended for the in-flight release (2026-10-25).

### Pre-Flight Checklist
- [x] All open questions resolved (the two-step field upgrade is put to the operator at approval)
- [x] Design decisions documented
- [x] Citation Audit complete (corrected after review)
- [ ] Prerequisites verified (fly login and the outward-step go come at their legs)
- [x] Validation approach defined (DD12)
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Windows premises first:** probe them on the hosted runner, with fail-loud rows, before anything depends on them.
2. **The boot-policy refactor:** done while nothing else moves in the desktop shell, with 0261 as a separate phase. Proved early on macOS by one standalone run.
3. **The Windows recipe:** staged metadata (no hosted runs; `fly execute`), then the graceful upgrade and the lifecycle driver on the runner. Its run also proves the refactor on Windows.
4. **The version and `release.yml`:** then the release stub. Then the two squawks that are not desktop code, and the docs.
5. **The dry run:** proves the composed release at once.
6. **The release and the field checks.**

Hosted runs build from the pushed branch, so the flight is reviewed and committed at each dispatch checkpoint, as Flights 1-3 did, not only at the end.

### Checkpoints
- [ ] Leg 1: the `windows-packages.yml` stub is merged, and the probe answers W1-W6 with no `not-run` row.
- [ ] Leg 2: `shell.py`/`window_control.py` have no `sys.platform` read and no policy-identity branch; the unit tier and the GTK smoke are green; the standalone macOS `lifecycle` passes, and its L1 screenshot shows the painted splash.
- [ ] Leg 3: `fly execute` builds the staged installer on Concourse. A Windows `lifecycle` run is all PASS, including old-to-new and the graceful upgrade over a running app.
- [ ] Leg 4: `release.yml` and the version gate are in place, the release stub is merged, the squawks are fixed, and the docs are written.
- [ ] Leg 5: the dry run is green and all four packages exist; the flight-end gates pass.
- [ ] Flight PR merged; `v0.12.0` published with four packages plus `SHA256SUMS`.
- [ ] The operator's Windows upgrade and the contributors' macOS check are reported, and the operator confirms.

### Adaptation Criteria

**Divert if**:
- **W1 is red** (the hosted runner cannot show a window): the lifecycle shrinks to install, `doctor`, `serve`, old-to-new, upgrade and uninstall, and the window rows move to the operator's field check. Re-plan leg 3b.
- **W4 is red even without elevation:** keep the force path, document "quit first" for Windows as for macOS, and tell the operator before leg 3b.
- **The refactor needs a real behaviour change** to stay correct: a leg design review, then the operator's call.
- **The macOS budget reaches 4** before a green dry run: the operator decides.
- **Mission 31 merges** a change to `pyproject.toml`, `uv.lock` or the desktop shell mid-flight: merge `main` at a checkpoint, never under running Developers.

**Acceptable variations**:
- Key names in `[windows]`, hook names in `BootPolicy`, row names in the lifecycle.
- `VersionInfoVersion` on the setup exe, if a numeric mapping is cheap.
- 0261 taking a different measured route than "wait for loaded", as long as its screenshot proof holds.
- One patch release before the operator confirms.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `windows-probe` - `windows-packages.yml` (probe mode) and its stub PR; W1-W6 on a hosted `windows-2022` runner, each with a positive control and a fail-loud row (DD2, DD5).
- [ ] `desktop-boot-policy` - 2a: `boot_policy.py` replaces all 21 `sys.platform` reads in `shell.py`/`window_control.py`, with an `ast` guard and a decision-table test. 2b: squawk 0261's splash flag. Then one standalone macOS `lifecycle` run (DD1, DD9).
- [ ] `windows-recipe` - 3a: `[windows]` in `product.toml`, `render.py --out`, the rendered `.iss` include, the staged spec, the Concourse task with `fly execute`, the Windows PATH-walk tests. 3b: the graceful upgrade, `windows-packages.yml` `full`/`lifecycle`, `lifecycle.ps1` (old-to-new included), `docs/windows-install.md` (DD2-DD5).
- [ ] `release-workflow` - 4a: the dynamic version and its lanes, the version gate, `release.yml` (retiring `windows-installer.yml` and `packaging-probe-windows.yml`), `.dmg` retention, and the release stub PR. 4b: squawks 0260 and 0262; README, `CLAUDE.md`, `agents.md`, `ci/README.md`; the contributor-check updates; a draft `docs/releases/v0.12.0.md` (DD6, DD7, DD9, DD10).
- [ ] `release-dry-run` - dispatch the dry run, read every row, fix and re-run the failed platform within budget; the flight-end gates and review (DD8, DD12).
- [ ] `release-and-field-check` *(interactive)* - bump (the PR's last commit), merge, tag `v0.12.0`, the field checks (the operator's Windows upgrade, the contributors' macOS run), and patch releases as needed; the operator confirms (DD10, DD11).

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated
- [ ] `v0.12.0` (or its last patch) published with all four packages
- [ ] Squawks 0260, 0261 and 0262 completed

### Verification
- The dry run (leg 5) is green: audit, version, three platform jobs, and the Windows and macOS `lifecycle` summaries all PASS.
- The `v0.12.0` release page lists the `.exe`, the `.dmg`, the AppImage, the `.deb` and `SHA256SUMS`, published by one `release.yml` run whose `audit` job ran first.
- `git grep -n "sys.platform" the_one/interfaces/desktop/shell.py the_one/interfaces/desktop/window_control.py` prints nothing.
- Changing `__version__` alone changes the version of all four packages and of the frozen Windows app (unit tests through `render.load`, `stage.py` and the `.iss` render; the spec reads the staged copy).
- The operator reports a successful in-place upgrade of their Windows install, with their data intact.
- `tests/behavior/macos-app-install.md` has a run log from a contributor's real Mac.
