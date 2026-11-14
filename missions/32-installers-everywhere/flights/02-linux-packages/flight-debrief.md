# Flight Debrief: Linux packages

**Date**: 2026-10-24
**Flight**: [Linux packages](flight.md)
**Status**: completed
**Duration**: 2026-10-24 (planned, flown and landed the same day)
**Legs Completed**: 13 of 13 (planned as 12; leg 11 was inserted after the leg 6 divert, and legs 4 and 5 ran as phases)
**Plugin version**: mission-control 1.2.2

## Outcome Assessment

### Objectives Achieved
GleepGlorp AI now installs on Ubuntu 26.04 and Debian 13 as an AppImage and as a `.deb`. Both are built from one pinned container and one metadata source, and both run as a desktop app with or without a tray.

- **The AppImage** carries a host-first fallback (DD1) for `libgirepository-2.0` and the Ayatana AppIndicator stack. It still uses the desktop's own WebKitGTK. Its ABI compatibility was proven against GLib 2.84 (Debian 13) and 2.88 (Ubuntu 26.04, with the fallback forced).
- **The desktop lifecycle works on GNOME** (DD3, DD4, DD12, DD13):
  - the tray is decided before pystray is imported;
  - the two GTK traps (the close deadlock, and `show()` re-hiding) are fixed;
  - with no tray, closing hides the window and a one-time notice explains it;
  - "Quit GleepGlorp AI" (a launcher action) and `the-one quit` exist;
  - Wayland focus works through the activation token;
  - a newer launch replaces an older running instance.
- **`doctor`** reports the sandbox and the tray (DD11).
- **Packaging infrastructure:**
  - The AppImage integrates itself into the menu (DD5).
  - The build emits AppStream metainfo and runs a post-freeze audit.
  - `packaging/product.toml` plus `render.py` are the metadata source (DD6).
  - The spike was folded into permanent code (DD8).
- **A dispatch-only hosted workflow** (DD10) was green on its first dispatch, and its output matches the local build file for file.
- **A fresh-VM apparatus** (DD9): QEMU/KVM in Docker, with Ubuntu 26.04.1 from the desktop ISO's autoinstall and Debian 13 GNOME. The `linux-package-install` behavior test passed 44/44 across all four variants.
- **`docs/linux-install.md`**, plus Linux sections in README, `CLAUDE.md` and `the_one/agents.md`. The project gained an MIT `LICENSE`.

**One divert (leg 6):** Ubuntu 26.04's App Center cannot upgrade or remove a local `.deb`, even with AppStream metainfo. The operator resolved it: on Ubuntu, the guide gives the `apt` commands, and the AppImage is recommended first. Installing stays click-only on both distros. In the debrief interview the operator confirmed this stays a known limit (no apt repository in this mission).

**The HAT (leg 13)** walked both desktops on the operator's screen, and every step passed:
- the tray notice was shortened inline;
- the first-launch blank became squawk 0253;
- the tile-label truncation, the GNOME badge and Debian's close-only title bar were accepted.

### Mission Criteria Advanced
- **Linux install, no setup: met for Ubuntu 26.04 and Debian 13 (x86-64).** Both packages install with no terminal and open their own window. On stock Debian (no tray) and stock Ubuntu (tray) the window, close, show and quit all work. The AppImage runs with FUSE 3 alone (no `libfuse2`).
- **The frozen runtime works in every build: met on Linux.** Strict `doctor` passes in both packages, on stock desktops and on bare images. The bare images give the honest "no display" answers.
- **Upgrades keep the user's data: met on Linux.**
  - The takeover (DD13) waits for the old pid, never just for the port.
  - Data survived every upgrade in the VMs: the providers and the chats.
  - The Ubuntu `.deb` upgrade is a documented `apt` line, not a click.
- **One packaging source of truth, built within the CI budget: partly met.**
  - `product.toml` is the source for both Linux formats.
  - The hosted cost is about 18 billed job-minutes per build: 1 of the 6 dispatches allowed, against 36 minutes estimated.
  - The version still lives in `pyproject.toml` and `the_one.__version__`, kept equal by a test. Flight 4 makes it dynamic.
- **Windows does not regress: held.** The shared `shell.py` changes are unit-tested on every platform. The DD13 takeover's win32 path (`_pid_alive` through `OpenProcess`) is unit-tested only. Flight 4 proves it through the Inno upgrade.

## What Went Well
- **Two Architect design-review cycles at planning found the flight's worst bugs before any code existed.**
  - The GTK close deadlock: `closing` is a locked event on the main thread, and the geometry getters block.
  - `show()` re-hiding a window created hidden. This was the cause of Flight 1's invisible first window.
  - `_select_port` deciding "ours" by credential rather than by version.
  - The port-free wait reopening the M24 DD-3a race.

  The leg 3 smoke test on real GTK then confirmed both traps on Flight 1's control build.
- **Per-leg design reviews kept catching wrong premises cheaply:**
  - pystray's package `__init__` runs `backend()` on import;
  - `os.kill(pid, 0)` terminates a process on Windows;
  - takeover tests would have reached port 8484 (now blocked by a conftest guard);
  - Ubuntu 26.04 lacks only the Ayatana typelib, not the libraries;
  - autoinstall's real schema, read from the ISO;
  - `appstreamcli` needing a homepage and a release date;
  - the `Exec` quoting layers.
- **The VM apparatus paid for itself.** It found a divert criterion (App Center) before any release, it produced the 44/44 behavior test, and it let the operator watch real desktops through WSLg ("holy cow, I didn't know you could do that"). The operator wants a visual walk like this at the end of each platform flight.
- **Rehearsal by execution worked.** Leg 9 ran the hosted workflow's scripts locally under a runner-like environment. That caught three bugs (the `.deb` file name, the summary job's subshell counter, and PEP 668 blocking `pip install`), and the first hosted dispatch was green. This was Flight 1's top recommendation, applied, and it turned three lost hosted jobs into none.
- **The behavior test ran in live mode with grouped checkpoints.** 44 checkpoints across four variants completed in one run, and the Validator's findings fed the HAT directly.
- **Parallel legs on disjoint files** (legs 1 and 2; legs 5A, 7 and 4C; legs 8 and 5B) kept a 13-leg flight to one day. The prompts named each leg's file set, and a failure in another leg's files was noted rather than chased.
- **The standing autonomy mode held.** About 15 Flight Director calls were logged for alignment and none was reversed. The operator judged the five check-ins "about right".
- **The unit tier's time stayed flat** despite +317 tests (see Technical), because the new tests are pure Python with fakes.

## What Could Be Improved

### Process
- **The divert premise was checked late.** The flight listed "a software centre cannot upgrade or remove a local `.deb`, even with metainfo" as an Adaptation Criterion. Leg 4's premise probe (P1) tested only installation, and upgrade and removal (P2, P3) surfaced at the end of leg 4. Testing them with this flight's own packages was folded into leg 6. Any criterion that rests on an OS component's behaviour should be probed in the first VM leg, with a throwaway package if needed.
- **Notification length was a planning miss, found twice.** DD4 specified one long notice string. GNOME's banner truncated the no-tray notice (found in leg 6, fixed in leg 11), and then the tray notice (found in the behavior test, fixed in the HAT). The DD14 no-WebKit notice (`shell.py::_NO_WEBVIEW_BODIES["webkit"]`, about 120 characters) has the same shape and has not been shortened. A "title plus a body of at most 60 characters" rule now exists only as a test on two strings.
- **Leg sizing:**
  - Two legs ran as phases (leg 4: A, B, C; leg 5: A, B). That was the right tool and kept the numbering stable.
  - One leg was inserted (11), and one grew in place: leg 6 absorbed the P2-P5 re-runs.
  - Leg 6 was written too narrowly for the question it ended up answering.
- **Flight-log hygiene:**
  - Leg 3's section landed under "Session Notes" and had to be moved.
  - The template's Decisions, Deviations and Anomalies sections stayed empty, because everything went into the Flight Director Notes.
  - The `linux-hat` section recorded the code fix but not the operator's dispositions; they were added with this debrief.
- **Leftovers outside the repo:**
  - A Reviewer left `~/m32rev`, which was root-owned. The Flight Director removed it through a container.
  - Two `dbus-daemon` processes (2132108, 2132116) from leg 2's first no-bus `doctor` smoke **are still running** (8 hours at debrief time). The permission classifier refused the kill, so they are with the operator.

### Technical
- **`the_one/interfaces/desktop/shell.py` is the main debt.**
  - It grew from 893 to 1478 lines (+702/−117).
  - `DesktopSession.run()` is a roughly 450-line method with numbered steps.
  - It is coordinated by module-level mutable state: `_really_quit`, `_booting`, `_quit_requested`, `_browser_server`, `_session`, `_tray_mode`, `_tracked_visible`, `_desktop_window`.
  - `_window_lock` is taken at 8 sites, and the "never call `_on_quit` under the lock" rule is enforced only by comments and review.

  Both crew members recommend a split before Flight 3 adds the Dock reopen and Cmd-Q states:
  - a takeover module: `_parse_version`, `_is_older`, `_running_version`, `_request_quit`, `_pid_alive`, `_wait_for_exit`, `_takeover`, `_select_port`;
  - a window-control module: `window_state`, `quit_desktop`, `focus_window`, `_gtk_read`, `_gtk_activate`;
  - a boot-state object in place of the globals.
- **`packaging/linux/rthook_host_gtk.py` is fragile in two ways:**
  - It undoes PyInstaller's stock `pyi_rth_gi/gio/glib/gtk` hooks. The spec drops them, and the hook removes variables that point into the bundle. A PyInstaller upgrade that renames or extends those hooks would silently re-leak bundle paths into WebKit's helpers. Leg 1 found exactly this leak latent in Flight 1.
  - `_HOST_TYPELIB_DIRS` is x86-64 only. That is fine for this mission's scope, but arm64 would silently get no host typelibs.
- **Untested paths:**
  - `diagnostics.py::bundle_has_modules` has a PYZ branch (`pkgutil.iter_modules` over PyInstaller's virtual paths). It is exercised only by real frozen builds. It fails safe (it reports "missing"), but a wrong "missing" would wrongly report no tray.
  - `build-inner.sh`, `vm/lib.sh`, `vm/vm.sh` and `checks/gates-inner.sh` are validated only by running them.
  - `AppRun.in` does have real coverage: `tests/test_packaging_apprun.py` renders and runs it.
- **Linux and macOS packaging have drifted.** `packaging/linux/build.sh` and `packaging/macos/build.sh` share argument parsing, `build.env`, render and stage steps, but differ on 169 of the first 200 lines. The hosted workflows (Linux 281 lines, Windows 248, the macOS probe) are three separate files. Flights 3 and 4 should extract shared steps, not copy them a third time. A small stale comment too: `packaging/linux/the-one.spec`'s header still says "SPIKE PROTOTYPE, not wired into CI", though it is now the product recipe used by the hosted workflow. Fix it in the next packaging leg that touches the file.
- **Notification copy is spread across shell constants:**
  - `_NO_TRAY_NOTICE_SUMMARY`;
  - `_TRAY_NOTICE_TITLE`/`_TRAY_NOTICE_BODY`;
  - `_NO_WEBVIEW_BODIES`.

  The DD4 text in `flight.md` is now stale by design (left as written).
- **Test metrics (debrief run, worktree `.venv` CPython 3.12):**
  - **Unit tier:**
    - 7100 passed, 0 failed, 15 skipped, 2512 deselected.
    - 338.6 s in pytest, 6m05s wall. No flakes.
    - The 15 skips are the expected 12 plus 3 `test_mcp_sandbox_integration.py` skips. Those 3 appear because the explicit `-m` dropped `not requires_bwrap`, exactly as CLAUDE.md predicts.
    - Against Flight 1's debrief (6783 passed, 341 s, 6m03s): **+317 tests, time flat.**
    - The flight added about 202 `def test_` lines, and parametrization accounts for the rest. They are in `test_desktop_shell.py` (+556 lines), `test_desktop_tray.py`, `test_desktop_host.py`, `test_desktop_takeover.py`, `test_cli_quit.py`, `test_window_routes.py` and `test_packaging_*`.
    - The slowest tests are all pre-existing, led by `test_mcp_pool.py::test_drain_timeout_handles_stuck_worker` at 10.0 s.
  - **Browser lanes (`--parallel 3`, netns):**
    - `PARALLEL_RESULT rc=0 total=1411s lanes=12`, 39 s faster than the landing run (1450 s).
    - `knowledge` came in at 284 s against its 300 s budget. It was over at landing (326 s), so that was load noise.
    - This run, `routing` (607/600) and `chats` (469/450) went slightly over. This flight touched neither area.
    - At the schedule head, the over-budget flag moves between lanes from run to run. That is noise around the budgets, not drift from this flight. Re-measure the budgets at the mission's end (squawk 0217's rule), not per flight.
    - Mission 31 F3 (1304 s, 13 lanes in its tree) is not directly comparable.

### Documentation
- **Most of what this flight introduced is documented:**
  - `the_one/agents.md` covers the tray decision, the host helpers, `bundle_has_modules`, the window routes, `the-one quit` and `_window_lock`.
  - `packaging/linux/README.md` covers the `THE_ONE_PKG_*` debug switches.
  - `packaging/linux/vm/README.md` covers the apparatus.
- **Gaps:**
  - nothing records the notification-length rule;
  - the PyInstaller stock-hook dependency is explained only in the hook's own comments and the flight log.
- **The behavior-test spec should take the Validator's five suggestions** (**squawk 0256**):
  - a window-geometry observable;
  - timed notification captures;
  - the apparatus facts (passwordless sudo, no GDM autologin after a logout);
  - the AppImage runtime-parent rule;
  - "hidden from the menu" wording.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Staging and `uv export` on the host, not in the build container (DD2) | This worktree's `.git` points into Mission 31's checkout, which must never be mounted | Yes, while missions run concurrently in worktrees; the hosted runner stages the same way |
| Legs 4 and 5 ran as phases (A/B/C, A/B) rather than new legs | They were too big for one session, and splitting kept the numbering stable for legs already in flight | Yes |
| Leg 11 (`notice-and-metainfo-polish`) inserted; the following legs renumbered | Cosmetic findings from leg 6, chosen by the operator as a small fix leg | Yes: insert a polish leg rather than stretch a verification leg |
| Leg 6 grew to re-run P2-P5 with this flight's packages | Leg 4's P2/P3 failures needed retesting with metainfo before declaring the divert | No: probe OS-component premises fully in the first VM leg |
| Ubuntu guest from `ubuntu-desktop-minimal`, not `ubuntu-desktop` | It is the installer's real default (`install-sources.yaml`), and it carries App Center | Yes: take "stock" from the installer's own default |
| Divert accepted: on Ubuntu, `.deb` upgrade and removal are documented with `apt`, and the AppImage is recommended first | App Center cannot manage a local `.deb`, even with metainfo | Known limit, kept (operator, debrief) |
| Notice text split into a title and a body of at most 60 characters (no-tray in leg 11, tray at the HAT) | GNOME's banner truncates long single strings | Yes: a rule for every desktop notification |
| AppStream category derived in `render.py::appstream_category` | `appstreamcli validate` requires categories once an icon is declared | Yes |
| Debug variables renamed `M32_*` → `THE_ONE_PKG_*` | They became product code | Yes |
| Three review/commit checkpoints instead of one at flight end | Hosted and VM legs build from the committed (and pushed) tree | Yes, for flights with hosted or VM legs (the same as Flight 1) |

## Key Learnings
1. **A lifecycle change needs a test on the real toolkit.** Fakes could not see either GTK trap. The real-GTK smoke test (Xvfb, `xwininfo`, a real `WM_DELETE_WINDOW`) proved both the traps and the fixes. Flight 3 needs the macOS equivalent.
2. **Probe "the OS manages it" premises first, end to end.** Installation working says nothing about upgrade and removal in the same software centre.
3. **Read the third-party tool's own schema or source at the pinned version.** That held again for subiquity's autoinstall schema (read from the ISO), pywebview 5.4's GTK backend, pystray's `__init__` and `appstreamcli`. It is now the default way design reviews work in this mission.
4. **Rehearsing hosted scripts by execution works.** One dispatch was spent, against Flight 1's three lost jobs.
5. **A visual walk is worth it even after a green behavior test.** The behavior test judged the notice "shown". The operator saw it was cut off.
6. **Host-first soname preloading through `ctypes` with `RTLD_GLOBAL`** (never `LD_LIBRARY_PATH`) keeps a bundled fallback out of WebKit's helper processes. Flight 1's environment-variable deletions were silently undone by PyInstaller's stock hooks; checking `/proc/<pid>/environ` of the helpers is what showed it.

## Methodology Observations
Recorded against mission-control 1.2.2.

1. **`agentic-workflow`, Phase 2a (leg sizing): phases inside a leg.**
   - **What happened:** two legs (4 and 5) were too large for one Developer session. The skill's only tools are "split into new legs" or "abort and re-create". The Flight Director ran them as phases A/B/C under one leg, each a separate Developer spawn with a checkpoint in the flight log, to keep the numbering stable while other legs ran in parallel.
   - **Expected:** a named pattern for multi-session legs.
   - **Cost:** improvised wording in five spawn prompts; no rework.
   - This recurs: Flight 1 split two legs for the same reason.
2. **`agentic-workflow`, Phase 2b (parallel crew in one worktree).**
   - **What happened:** up to three Developers worked at once on disjoint file sets, named in each prompt. Each was told that a unit-gate failure in another leg's files is noted, not chased.
   - **Expected:** guidance on concurrent crew in one tree. The skill implies sequential legs.
   - **Cost:** none, but it rests entirely on the Flight Director's prompt wording.
   - This recurs from Flight 1's observation 6.
3. **`agentic-workflow`, Phase 2b (`[BLOCKED:divert-*]`).**
   - **What happened:** leg 6 emitted `[BLOCKED:divert-appcenter-upgrade]` for a flight-level Adaptation Criterion. The protocol has no divert signal or state distinct from a crew blocker.
   - **What was done instead:** the Flight Director surfaced it to the operator, logged the decision, inserted leg 11 and renumbered.
   - **Cost:** about 15 minutes of artifact edits; no rework.
4. **`flight`, Phase 4 (apparatus premise audit).**
   - **What happened:** the act/observe audit was done well (DD4's `GET /api/window/state` read path). But a premise behind an Adaptation Criterion (software-centre upgrade and removal) was assigned to leg 4 and only half-probed there.
   - **Expected:** the flight skill prompts that every Adaptation Criterion's premise is probed in the earliest leg that can reach it.
   - **Cost:** leg 6 grew in place, and the divert came mid-flight rather than at leg 4.
5. **`behavior-test` (live mode, grouped checkpoints; positive).**
   - **What happened:** 44 checkpoints across four variants were grouped per variant and run in live mode in one session. That was far cheaper than re-spawning per checkpoint.
   - **What it missed:** the Validator judged the truncated notice "shown". It is visual-quality judgment a step's Expected Result did not ask for. The finding came from the Validator's free-text notes and from the HAT.
6. **`agentic-workflow`, crew hygiene outside the repo.**
   - **What happened:** a Reviewer left a root-owned directory in `$HOME`, and a Developer's smoke test left two `dbus-daemon` processes that the permission classifier would not let anyone kill.
   - **Expected:** the crew prompts carry a "leave no processes or files outside the repo; record PIDs you start and stop them" rule.
   - **Cost:** two Flight Director clean-up steps; one item still with the operator.
7. **Subagent hand-back repeats.**
   - **What happened:** the leg 11 fix agent kept re-sending its final report after completing, until stopped.
   - **Cost:** a TaskStop and some context.
   - This is a harness behaviour, not the plugin's; recorded for the sweep.
8. **`flight-debrief` (positive).** The test-metrics instruction produced a like-for-like comparison with Flight 1's numbers. The Developer correctly explained the 12-versus-15 skip delta, as an `-m` override rather than a regression.

## Recommendations
1. **Split `shell.py` before Flight 3 adds macOS states** (Critical for Flight 3).
   - Extract the takeover and the window control into their own modules.
   - Replace the module-level flags with one boot-state object.
   - Keep the lock rules where code enforces them, not just in comments.

   Make it a leg of Flight 3, or a sortie before it.
2. **Probe every Adaptation Criterion's premise in the first leg that can reach it** (Important). For Flight 3, these are:
   - Gatekeeper and the "unidentified developer" flow for an ad-hoc-signed `.app`;
   - a drag-install replacing a running app;
   - the Dock reopen;
   - the blank first paint.

   Probe each end to end in its first macOS leg, not in a later verification leg.
3. **Give every desktop notification a short title and a body of at most 60 characters, pinned by one test over all notice constants** (Important). The DD14 no-WebKit body is the remaining offender: **squawk 0254**.
4. **Guard the PyInstaller stock-hook dependency** (Important before any PyInstaller bump). Add an audit or test check that the dropped `pyi_rth_gi/gio/glib/gtk` hooks are still the set the spec drops, and that no bundle path leaks into a helper's environment. Also add a frozen-build `doctor` assertion for `bundle_has_modules`' PYZ case: **squawk 0255**.
5. **Flights 3 and 4 share packaging steps instead of copying them** (Important).
   - Reuse `stage.py`, `render.py`, `product.toml` and the audit's structure for macOS.
   - Flight 4 extracts a shared release workflow from the three hosted workflows.
   - Flight 4 runs DD13's takeover through the Inno upgrade on real Windows.

## Action Items
- [ ] Operator: stop the two leftover `dbus-daemon` processes from leg 2 (`! kill 2132108 2132116`).
- [ ] **Squawk 0254**: the no-WebKit notice is too long for GNOME's banner; pin every notice constant at 60 characters or fewer.
- [ ] **Squawk 0255**: an audit canary for PyInstaller's dropped stock gi hooks, plus a frozen assertion for the PYZ branch of `bundle_has_modules`.
- [ ] **Squawk 0256**: fold the Validator's five suggestions into `tests/behavior/linux-package-install.md`.
- [ ] Squawk 0253 (the 20 s blank first paint of the Ubuntu AppImage): probe it together with Flight 1's macOS blank first paint in Flight 3's first macOS leg. If the cause is shared, the fix belongs in the shell, not in packaging.
- [ ] Flight 3 planning: the `shell.py` split (rec 1); a macOS real-toolkit smoke test; the premise probes (rec 2); reuse of the metadata and staging (rec 5); DD13 and `the-one quit` on macOS.
- [ ] Flight 4 planning:
  - the dynamic version (delete the pin test, and have `render.py::read_version` read the single source);
  - the shared release workflow;
  - DD13 on Windows through Inno;
  - keep `doctor`'s output contract stable for the Windows CI lanes.
- [ ] Mission end: re-measure the browser-lane budgets (`routing`, `chats` and `knowledge` alternate over budget at the schedule head).
