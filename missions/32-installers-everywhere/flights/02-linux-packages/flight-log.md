# Flight Log: Linux packages

**Flight**: [Linux packages](flight.md)

## Summary
**Landed 2026-10-24.** Thirteen legs completed (twelve planned; leg 11 was added after leg 6).

**Delivered:** both Linux packages, built from one pinned container and one metadata source.
- The AppImage carries a host-first fallback for `libgirepository-2.0` and the Ayatana stack; its compatibility was proven against GLib 2.84 and 2.88.
- The desktop works on GNOME with or without a tray:
  - closing and showing the window work under GTK;
  - no-tray hide, with a notice;
  - "Quit GleepGlorp AI" and `the-one quit`;
  - Wayland focus;
  - a newer launch replaces an older running one.
- `doctor` reports the sandbox and tray.
- Self-integration into the menu, AppStream metainfo, and a post-freeze audit.
- A dispatch-only hosted workflow, green on its first run and matching the local build.
- A fresh-VM apparatus. The `linux-package-install` behavior test passed 44/44 on Ubuntu 26.04 and Debian 13 for both packages.
- The Linux install guide.

**Gates:** `make test-unit` 7059 passed, 12 skipped; all 12 browser lanes passed (`--parallel 3`, 1450 s; `knowledge` 326 s against a 300 s budget, flagged); ruff clean.

**Operator decisions:** MIT license; homepage; on Ubuntu, `.deb` upgrade and removal are documented with `apt`, and the AppImage is recommended first; the cosmetic polish; the HAT dispositions. Squawk 0253 is open (the Ubuntu AppImage's slow first paint).

---

## Planning Notes

### Flight Director Notes
- **Branch:** `flight/02-linux-packages`, off `origin/main` at `6f92fd5` (after #305-#308), in the Mission 32 worktree `/home/cprch/projects/the-one-worktrees/m32-installers`. Mission 31's checkout (`/home/cprch/projects/the-one`) is untouched.
- **Inputs carried in:**
  - **Flight 1 debrief recommendations:**
    - rec 1, rehearse hosted scripts by running them → DD10;
    - rec 2, the 3.11 failures → done, squawk 0251;
    - rec 3, measure the release runner's bundle → DD2 and leg 4;
    - rec 4, consider a split → the operator chose one flight, risk first.
  - **Flight 1 action items:**
    - the AppImage bundling → DD1;
    - the pystray fall-through → DD3;
    - hide-without-tray → DD4;
    - the metadata source → DD6;
    - fresh-VM checks → DD9;
    - a hosted build check → DD10;
    - the spike's fate and the packaging unit tier → DD8.
  - **The operator's decision:** "bundle the two libs".
- **Operator answers (2026-10-24):**
  - one flight, risk first;
  - quit with no tray through a launcher Quit action plus a one-time notice;
  - an AppImage self-integrates on first run;
  - QEMU-in-container VMs, the `.github/`-only PR, and a closing guided walk all approved.
- **Probes at planning:**
  - KVM works inside a container (`--device /dev/kvm`, API 12, VM created; nested `Y`);
  - the Ubuntu 26.04 and Debian 13 cloud images answer 200;
  - `ubuntu:24.04` digest `sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac`;
  - Flight 1's `m32/{ubuntu-26.04,debian-13}:{bare,baseline}` images are still present.
- **Design review cycle 1 (Architect, Opus): approve with changes.** Three high findings, each re-checked by the Flight Director against the code:
  1. Every Linux close deadlocks: the locked `closing` event, plus the blocking GTK geometry getters → DD12.
  2. On GTK, pywebview's `show()` re-hides a window created hidden; only `restore()` maps it. This is the cause of Flight 1's finding 5 → DD12.
  3. A wrong citation: `_select_port` decides "ours" by credential, not version, so an upgraded launch reaches the old running process → DD13.

  The medium and low findings were folded in:
  - the Ubuntu guest from the desktop ISO, and Debian `generic`;
  - polkit and the GUI-only install act, and `usb-tablet`;
  - TryExec semantics;
  - the action name;
  - the WebKitGTK-missing criterion → DD14;
  - the behavior test's session environment;
  - the hosted matrix reduced to bare images;
  - legs 2, 3 and 5 split (6 legs became 9), and the apparatus moved earlier;
  - the dynamic version deferred to Flight 4 (the mission flight list was updated);
  - the quit route's details;
  - DD1's location and best-effort handling;
  - DD3's host check and XEmbed note;
  - Wayland passes `None` for position;
  - `AppRun` as the integration locus;
  - `git safe.directory`;
  - the tool paths;
  - a separate notice marker;
  - the activation token.
- **Operator answers after cycle 1 (2026-10-24):**
  - a newer launch replaces an older running instance;
  - the Ubuntu guest comes from the desktop ISO's autoinstall;
  - a missing WebKitGTK gets a notification plus a `doctor` line;
  - the launcher action is named "Quit GleepGlorp AI".
- **Design review cycle 2 (Architect, Opus): approve with changes.** No stale cycle-1 text was found in the spec. Two new high findings, both re-checked by the Flight Director:
  1. Caching geometry from pywebview's `resized`/`moved` events records the wrong measure, because they include the client-side decorations on Wayland. `_on_closing` always runs on the GTK main thread (`destroy` → `idle_add(close_window)`), so DD12 reads `Gtk.Window` geometry directly.
  2. DD13 must wait for the old process's `pid` to exit, not for the port to free. uvicorn closes the listener before the lifespan drain, so a port-free wait reopens the M24 DD-3a race. The version comes from `/api/info`, and an old server with no quit route is focused at once.

  The medium and low findings were folded in:
  - the tray decision before any pystray import (`_xorg` connects at import);
  - DD11's host-GTK-first rule, and the no-display case;
  - the boot-race lock;
  - the asynchronous notice;
  - the no-`gi` notice path;
  - the state route's `mode`/`pid`;
  - the focus route as a plain `def`;
  - the three close states;
  - lazy imports moved to boot;
  - a VM relaunch probe before any hosted spend (the new leg 6);
  - GUI upgrade/remove and AppStream metainfo as premises;
  - upgrade coverage of providers and chats in the behavior test;
  - `WM_DELETE_WINDOW` in the smoke test;
  - the size round-trip;
  - legs 3 and 5 split (9 legs became 12).
- **The Flight Director's answers to the cycle-2 questions** (no third cycle: the max-2 rule, and the remaining items are concrete fixes, not disagreements):
  - DD13 applies on every platform (`shell.py` is shared), and Flight 4 confirms it on Windows beside Inno's close-applications step.
  - The test versions are N=`0.11.8` and N+1=`0.11.9.dev1` (dpkg `0.11.9~dev1`), with a unit test pinning PEP 440 against dpkg order.
  - The frozen `doctor` passes with no display at all (DD11).
- **Calls the Flight Director made without asking (standing autonomy mode, logged for alignment):**
  - the build container pin (DD2);
  - host-first soname preloading rather than `LD_LIBRARY_PATH` (DD1);
  - the tray-detection rules (DD3);
  - `GET /api/window/state` as the read path (DD4);
  - separate desktop ids for the AppImage and the `.deb`, and `AppRun` as the integration locus (DD5);
  - `packaging/product.toml`; the `pyproject` version pinned by a test, with the dynamic version deferred to Flight 4 (DD6);
  - Wayland size-only geometry (DD7);
  - the spike fold (DD8);
  - a 6-dispatch cap (DD10).

### Execution — Flight Director Notes
- **2026-10-24, `agentic-workflow` started.**
  - Phase file `.flightops/agent-crews/leg-execution.md` loaded (Developer: Sonnet; Reviewer: Haiku, or Sonnet for security-sensitive diffs).
  - Flight status `ready` → `in-flight`.
  - The operator's standing autonomy mode applies.
- **Leg 1 (`appimage-library-fallback`) risk tier: HIGH.** It is the flight's divert point. It introduces a new loader mechanism (soname preloading in a runtime hook) and a new build environment, and it amends a hard gate's scoring. A Developer design review runs before implementation.
- **Leg 1 design note:** staging and `uv export` run on the host, not in the container. This worktree's `.git` points into Mission 31's checkout, which must never be mounted, so DD2's `safe.directory` approach is replaced. Logged as a planned deviation.
- **Leg 2 (`tray-selection-and-doctor`) risk tier: HIGH.** It changes `doctor`'s desktop-shell gate semantics, which the Windows CI lanes grep, and it changes the tray lifecycle wiring.
  - **Design review cycle 1 (Sonnet): approve with changes.** Findings:
    - pystray's package `__init__` runs `backend()` on any import, so the no-GTK and no-display `doctor` branches must never import pystray;
    - existing Linux `_boot`, browser-fallback and `doctor` tests would hit the real probes → AC0 stub fixture;
    - the `PYSTRAY_BACKEND` leak → a `backend=` keyword;
    - the backend order made explicit;
    - WebKit2 4.0 is kept, and multiarch directories are globbed;
    - no D-Bus autolaunch;
    - synchronous notifications in a daemon thread;
    - the non-frozen path unchanged;
    - `_tray_mode` semantics;
    - cp1252-safe lines.
  - **Cycle 2 (Sonnet): approve with changes.** Findings:
    - stale `bus_get_sync` text in the guidance;
    - `backend=` passed only when not None, so the existing fakes stay valid;
    - `appindicator` also requires Gtk 3.0;
    - the `tray:` line is consistent with the desktop-shell branch;
    - the `bundle_has_modules` dotted algorithm;
    - per-cause notification wording.

    All folded in. Status `ready` (the 2-cycle maximum was reached; the remaining items were concrete fixes).
- **Leg 1 design review cycle 1 (Sonnet): approve with changes.** Findings:
  - the Ubuntu 26.04 baseline has every Ayatana `.so` but lacks only the typelib, so the typelib fallback is decoupled from the library preload;
  - the ABI test never exercised the fallback against GLib 2.88 → a `M32_FORCE_FALLBACK` debug knob for a 26.04 run;
  - per-soname gate 3 scoring (Debian 13 is a partial chain);
  - the WebKit environ check restricted to loader variables;
  - the closure is installed in an image layer, with a world-readable uv Python;
  - an AC comparing the container bundle with Flight 1's bundle, and recording package versions;
  - the exact six-soname closure;
  - uv pinned by digest.

  All folded in. A cycle-2 review runs in parallel with leg 2's implementation (disjoint files).
- **The reviewer left a root-owned scratch dir, `/home/cprch/m32rev`** (six copied libraries and a typelib from its closure check). The Flight Director listed it and removed it through a throwaway `m32-cleanup-rev` container.
- **Concurrency:** legs 1 and 2 are implemented by separate Developers in the same worktree, on disjoint files (`packaging/` against `the_one/` and `tests/`). Each adds only its own Leg Progress section to this log.
- **Leg 1 design review cycle 2 (Sonnet): approve with changes.** Findings:
  - the build container must mount all of `packaging/` (the spec loads `../windows/frozen_entry.py`);
  - the harness additions are now listed explicitly (`--env`, `--variant`/`--extra-apt`, probe mode, the host-libs record, the environ capture);
  - the Ayatana packages are extracted rather than installed, so the gi hooks see Flight 1's environment;
  - a named critical-warning grep with a `.deb` control run;
  - the glibc soname list;
  - a precheck for the Debian mixed variant;
  - the diff check scoped to leg 1's own paths.

  All folded in. Status `ready` (2-cycle maximum).
- **Flight Director decision, logged for alignment:** the runtime hook's debug variables (`M32_DEBUG_ENV`, `M32_FORCE_FALLBACK`, `M32_ABI_PROBE`) ship inert in both packages. They do nothing unless set, `M32_FORCE_FALLBACK` acts only together with `M32_DEBUG_ENV`, and the README documents them. Leg 7 (`linux-recipe`) may rename them out of the `M32_` namespace once the recipe is product.
- **Leg 4 (`vm-apparatus`) risk tier: HIGH, for feasibility.** It is new apparatus with premises that can divert the flight.
  - **Design review cycle 1 (Sonnet): approve with changes.** Findings:
    - the Ubuntu seed must be NoCloud `user-data`/`meta-data` under `autoinstall:`, after reading the installer's own schema;
    - `-no-reboot` plus a disk-only second boot;
    - UEFI decided, with a per-base `OVMF_VARS`;
    - the container runs as the invoking uid with `--group-add kvm`, so no root-owned files are left;
    - the Debian image is resized before first boot;
    - "stock" absences are recorded, not asserted;
    - the screen-stability tolerance;
    - QMP and resolution details;
    - `qemu-system-gui` for the visible display;
    - AC6 scoped for concurrent legs;
    - the premise order, and a fresh overlay for P4;
    - libfuse2 recorded;
    - one P1 retry after snap/PackageKit settle.

    All folded in.
  - **The leg runs as three sequential Developer phases** (A: runner, helpers and Debian; B: Ubuntu autoinstall; C: the premises) rather than three numbered legs. That keeps the flight's leg numbering stable for the two legs already in flight.
  - **No second review cycle.** Every change adopts the reviewer's own recommendation, and the risky part (the autoinstall) has its own time box and BLOCKED signal. Status `ready`.
- **Leg 4 phase A starts beside legs 1 and 2.** The first part is downloads, an image build and scripts. The leg's `free -g` ≥ 8 GB guard before each VM `up` keeps the guest from starving the concurrent gate containers.
- **Leg 2 landed** (Developer report):
  - 6852 passed, 12 skipped; ruff clean.
  - Deviations: the helper module is imported as `desktop_host`, since `host` collides with `settings.host` locals; `detect_tray` returns `(mode, reason)`.
  - **Open item:** two `dbus-daemon` processes (2132108 session bus, 2132116 at-spi) started at 10:14:27 by the Developer's first no-bus `doctor` smoke on the dev host, pointed at a scratch `XDG_RUNTIME_DIR`. They are most likely GTK's accessibility bus from the unchanged non-frozen pystray/Gtk import, not the new probe. Not reproduced in five later runs.
    - The Developer's kill was refused by the permission classifier.
    - The Flight Director did not kill them either: it is a refused action, so it is surfaced to the operator (`kill 2132108 2132116`), and they are harmless.
- **Leg 3 (`gtk-window-fixes`) risk tier: HIGH.** It changes the window lifecycle, adds credential-gated routes, and has a security-sensitive surface (the Reviewer will be Sonnet). Its design review is running. Implementation waits for leg 1 to land, because its smoke test builds a `.deb` with leg 1's `build.sh`.
- **Leg 3 design review cycle 1 (Sonnet): approve with changes.** It confirmed both traps against pywebview 5.4. Folded in:
  - The Flight 1 control can't use the new routes; it proves trap 2 by `xwininfo IsUnMapped`, and trap 1 only if it had a tray.
  - Wayland is decided from the `GdkDisplay` type, not from `WAYLAND_DISPLAY`.
  - GTK detection via `sys.modules["webview"].renderer`.
  - The smoke geometry check compares X sizes across relaunches (CSD margin), with a fixed Xvfb screen.
  - `get_visible` through pywebview's `glib`, plus `mapped`.
  - `_on_quit(None)` still destroys.
  - The harness scaffolding, the `python3-xlib` client message, and the exact window title (the splash differs).
  - The Windows show-test stubs.
  - The `settings` browser lane for the `/api/window/chrome` mock.

  No second cycle: all changes adopt the reviewer's own recommendations. Status `ready`.
- **Leg 3 starts now, code half first.** The code half (shell, routes, unit tests) runs beside legs 1 and 4. The smoke half waits until leg 1's leg file reads `landed`, because it builds with leg 1's `build.sh`.
- **Leg 3 code half complete** (Developer, `[HANDOFF:review-needed]`):
  - 6871 passed, 12 skipped; ruff clean; the `settings` browser lane 109 passed;
  - the smoke half is pending leg 1.
- **Leg 4 phase A complete:**
  - the Debian 13 guest provisioned in about 7 minutes; act and observe work on Wayland;
  - recorded: no `libgirepository-2.0-0` (only 1.0 with `python3-gi` 3.50), no Ayatana, no `libfuse2` (`fusermount3` present), `bwrap` userns works;
  - the Ubuntu ISO was downloaded and verified.

  Phase B (the Ubuntu autoinstall) is running.
- **Leg 5 (`no-tray-lifecycle`) risk tier: HIGH** (lifecycle, new routes, a Windows-shared path).
  - **Design review cycle 1 (Sonnet): approve with changes.** Findings folded in:
    - `os.kill(pid, 0)` terminates the process on Windows → `_pid_alive` with `OpenProcess`/`WaitForSingleObject` on win32;
    - the takeover's version probe would make the existing `is_ours` tests hit port 8484 → separate stubbable `_running_version`/`_request_quit`, with `_select_port`'s shape unchanged, plus a conftest guard against 8484/8485;
    - where `_booting` is set and cleared, the quit checks after the splash and server waits, the browser-branch race, `_on_quit` never under the lock, and `mode: quitting`;
    - quit-answer validation (`quit: false`/404/401);
    - the token applied in one idle that replaces the plain present, the token length cap, and GTK versions recorded;
    - no `packaging` dependency → a documented comparator, with `dev9 < dev10`;
    - `the-one quit`: the missing-file warning, the malformed file, 401;
    - `serve` detection, and module-scope imports with an AST check;
    - `_on_closing` registered before the tray decision.
  - **The leg is split into phases A (close states, quit, `mode`, CLI) and B (focus token, takeover)**, like leg 4. No second review cycle: the changes adopt the reviewer's recommendations. Status `ready`.
- **Sequencing call:** leg 5 waits for leg 3 to land. Leg 3's pending smoke half builds a `.deb` from this worktree, and leg 5 rewrites the same `shell.py`, so a build taken mid-edit could carry half-done code.
- **Leg 1 landed** (Developer report). **The divert test passed:**
  - the fallback `libgirepository-2.0` and Ayatana stack work against Debian 13's GLib 2.84;
  - with `M32_FORCE_FALLBACK=1`, against Ubuntu 26.04's 2.88;
  - no `undefined symbol` and no criticals.

  Gates: the AppImage passes every gate unpinned on both baselines. The `.deb` is unchanged (all PASS, including the bare images). The bundle's file list equals Flight 1's (1025 files).

  **Two latent Flight 1 defects were fixed:**
  - PyInstaller's stock gi/gio/glib/gtk runtime hooks re-pointed `GI_TYPELIB_PATH`/`GIO_MODULE_DIR`/`XDG_DATA_DIRS`/`GTK_PATH` into the bundle after our hook ran (the spec now drops them);
  - the fallback typelib path would have leaked into WebKit's helpers (the hook drops the variable after gi reads it).

  Notes:
  - one AC5 run was repeated after a 120 s `/api/live` timeout under host load of about 10;
  - the packages were staged from HEAD (`M32_FROM_HEAD=1`) to keep leg 2's in-progress edits out;
  - the bare-image AppImage `doctor` desktop-shell FAIL remains until leg 2's split reaches a rebuilt package.
- **Leg 3 resumed** for its smoke half (it builds from the working tree, version `0.11.9.dev3`).
- **Leg 7 (`linux-recipe`) risk tier: HIGH.** It is the metadata interface consumed by Flights 3 and 4, changes every build output, and adds runtime shell code (`AppRun`) that writes into the user's home. Its design review is running. It runs after leg 3 lands, beside leg 5, on disjoint files.
- **Leg 3 landed** (Developer report):
  - smoke OVERALL PASS on both baselines: the window maps (`visible:true, mapped:true`, `IsViewable`); a real `WM_DELETE_WINDOW` close exits within 15 s; size is stable across relaunches (1440x900); the quit route exits within 15 s; the tray decision is `none`;
  - the Flight 1 control shows trap 2 (`IsUnMapped`). Trap 1 was not reproducible on the control, which registered no closing handler without a tray;
  - 6871 passed, 12 skipped; the `settings` lane 109 passed.

  Note: its log section landed under `## Session Notes`; it is tidied at the review checkpoint.
- **Leg 4 phase B complete:**
  - the Ubuntu 26.04.1 autoinstall worked first time, plus three reruns for first-login wizards (the real stamp is `~/.config/gnome-initial-setup/upgrade-26.04-done`);
  - **deviation accepted by the Flight Director:** the installer's real default source is `ubuntu-desktop-minimal` (`/casper/install-sources.yaml` `default: true`), not `ubuntu-desktop`. It is used as the stock default, and it carries App Center;
  - recorded on the Ubuntu base:
    - the AppIndicator extension is **enabled** (a tray host exists);
    - `libgirepository-2.0-0` and `libayatana-appindicator3-1` are present;
    - the Ayatana typelib and `libfuse2t64` are absent;
  - base sha256 `5aad3618…2e66`.
- **Operator answers (2026-10-24):** project license **MIT** (a `LICENSE` file and the `pyproject` `license` field are added in leg 7); homepage `https://github.com/msieurthenardier/the-one`.
- **Leg 7 design review cycle 1 (Sonnet): approve with changes.** Folded in:
  - the homepage is required (otherwise `appstreamcli` exits 3);
  - a release date, from `SOURCE_DATE_EPOCH`, set to the last commit's time;
  - three runtime placeholders with distinct escapes, the `Exec` two-layer quoting and `%%` (verified with `desktop-file-validate`);
  - `awk` with `ENVIRON` instead of `sed`;
  - `AppRun` rendered from `AppRun.in`;
  - `build.sh` argument rules and order, and the `build.env` regex;
  - the `cmp` fallback, `umask`, the `mtime` test;
  - an early `appimagetool` check;
  - AC6 may defer to leg 8 if the budget is short.

  Status `ready`; no second cycle (the changes adopt the review's own findings and the operator's answers).
- **Now running in parallel:**
  - leg 5 phase A (`the_one/`, `tests/`, docs);
  - leg 7 (`packaging/` minus `vm/`/`spike/`, `LICENSE`, the `pyproject` license line, `tests/test_packaging_*`);
  - leg 4 phase C (`packaging/linux/vm/`, VMs).

  The files are disjoint. Each Developer's unit gate may see another leg's in-progress test files: a failure confined to another leg's files is noted, not chased.
- **Leg 7 landed** (Developer report):
  - AppStream id `ai.gleepglorp.GleepGlorpAI`; MIT; homepage set;
  - the `.desktop` and metainfo validators pass;
  - `appimagetool` wants the metainfo named after the desktop id and validates over the network, so the file follows AppStream's id-based name and the build validates it itself (appimagetool only warns);
  - the `.deb` template was renamed `deb.desktop.in`;
  - AC6 ran: AppImage on Debian 13 baseline and `.deb` on Ubuntu 26.04 baseline, all PASS;
  - 6951 passed, 12 skipped.
- **Leg 8 (`packaging-checks-and-audit`) risk tier: LOW. No design review.**
  - It is mechanical `git mv`s within `packaging/`, an additive audit script with its own unit tests, and a rename of three debug variables.
  - No `the_one/` change and no shared interface: the macOS workflow calls only `packaging/macos/build.sh`, whose two path references are updated and statically checked.
  - The flight-end Reviewer covers the code.
  - Status `ready`. It starts after leg 5 phase A hands off, because phase A may be running the smoke harness that this leg moves.
- **Leg 4 landed** (phase C, Developer report). No divert: P1 (install a local `.deb` without a terminal) passes on both guests.
  - **Findings:**
    - **Ubuntu 26.04's App Center cannot upgrade (P2) or remove (P3) a local `.deb`.** It shows only a disabled "Installed" button, and the package is not listed anywhere.
    - **Debian's GNOME Software can upgrade and remove it** (from the package's own page), but does not list it.
    - **The first launch shows no window on both guests,** and a relaunch shows it. That is Flight 1's trap 2, fixed by leg 3; it was observed with Flight 1's 0.11.8 package.
    - **The Flight 1 AppImage opens in Firefox on Debian.** Expected: that build has no `libgirepository-2.0` fallback (leg 1), so the browser fallback ran.
    - **FUSE works on both** (`fusermount3`, `/dev/fuse`; there is no `libfuse.so.2`, and none is needed).
    - Ubuntu has `apparmor_restrict_unprivileged_userns=1` and `bwrap` works on both. WebKit's processes are not `bwrap`-wrapped on either.
    - GTK is 3.24.52 (Ubuntu) and 3.24.49 (Debian).
  - **The Flight Director's call:** leg 6 (`vm-relaunch-probe`) grows to re-run P2, P3, P4 and P5 with this flight's packages: leg 7's metainfo, leg 1's fallback, leg 3's show fix. If Ubuntu's App Center still cannot upgrade or remove with metainfo, that is the flight's divert criterion ("A software centre cannot upgrade or remove a local `.deb`, even with AppStream metainfo"), and it goes to the operator. The operator was given a heads-up.
- **Leg 5 phase A complete** (Developer report):
  - 6951 passed, 12 skipped; the `settings` lane 109 passed;
  - real-GTK smoke OVERALL PASS on both baselines (none-mode close hides, relaunch shows, `the-one quit` exits in 1-2 s, a second quit reports "not running");
  - the port guard is in `tests/conftest.py`.

  Design calls the Flight Director accepts:
  - a quit at step 6 also releases the splash;
  - the boot abort sets `_really_quit`;
  - the `is_ours` return clears `_session` (it fixed a full-suite-only failure);
  - `the-one quit --wait` moves to phase B (it needs `_pid_alive`).
- **Leg 8 and leg 5 phase B are running in parallel.** Phase B does its code first and runs smoke only after leg 8 lands, because leg 8 moves the smoke harness.
- **Leg 6 (`vm-relaunch-probe`) risk tier: LOW.** It is verification only, makes no code change, and a found defect becomes `[BLOCKED:defect-…]` for a Flight Director decision. No design review. Status `ready`.
- **Review and commit plan:** when leg 5 phase B and leg 8 land, one Reviewer (Sonnet: the diff adds credential-gated routes and touches the sandbox factory) covers all uncommitted work (legs 1-5, 7, 8, and leg 4's apparatus). Then fix, commit, and leg 6 builds from the committed tree.
- **Leg 8 landed** (Developer report):
  - `packaging/spike/` is gone (`git mv` for tracked files, `mv` for the untracked smoke scripts);
  - `gates.sh --display wslg|xvfb`;
  - the audit passes on a real build (`max GLIBC_2.34`) and fails a deliberately broken scratch build (12 problems);
  - `THE_ONE_PKG_*` debug names;
  - `launch_args()` extracted in `packaging/macos/frozen_entry_mac.py`, behaviour identical (the one Flight 3 file touched beyond paths);
  - 7035 passed, 12 skipped; ruff clean on the whole tree.
- **Leg 9 (`hosted-build-prepare`) risk tier: LOW. No design review.**
  - It adds a CI file and a small harness mode.
  - The hosted-cost risk is handled by the leg's own rehearsal-by-execution ACs, and Linux minutes are 1×.
  - The outward steps (push, the stub PR, merge, dispatch) stay with the Flight Director.
  - Status `ready`; it runs after the review and commit checkpoint.
- **Review checkpoint (legs 1-5, 7, 8 and leg 4's apparatus):**
  - Reviewer (Sonnet, the security-sensitive tier): `[HANDOFF:confirmed]`, no blocking issues; security checks held across route gating, token validation, credential handling, process signalling, AppRun escaping, library paths, and the import boundary.
  - Six non-blocking items were fixed by a Developer:
    1. log placement;
    2. pid validation;
    3. repeat quit;
    4. win32 ctypes types;
    5. printable-ASCII token;
    6. the `SECURITY-MODEL.md` posture sentence.

    7051 passed, 12 skipped; ruff clean. No re-review: the reviewer had already confirmed, and the fixes were its own non-blocking items.
  - Leg statuses → `completed`, and the legs are checked off in `flight.md`. Committed as the flight's first implementation checkpoint, so leg 6 builds from a committed tree.
- **Leg 6 landed** (Developer report). **No relaunch divert:** the window shows on the first launch, and on relaunch it comes back in front and active, on both guests (`XDG_ACTIVATION_TOKEN` was present in the launcher's environment). Every other row passed:
  - Ubuntu's tray and its Show item;
  - Debian's no-tray hide and the one-time notice;
  - "Quit GleepGlorp AI" (exits in 2 s);
  - the GUI takeover on Debian;
  - the AppImage's own window and its menu entry on both, with the entry removed after the file is deleted and the session logged out and in;
  - `doctor` (`sandbox: bubblewrap`; tray `indicator`/`none`).

  **`[BLOCKED:divert-appcenter-upgrade]`: Ubuntu 26.04's App Center cannot upgrade or remove the local `.deb`, even with metainfo** ("Something went wrong" on N+1; a disabled "Installed" button; not listed). On Ubuntu the takeover and removal were done with `apt` over SSH; data survived. Smaller findings: the no-tray notice is truncated in GNOME's banner, and App Center shows a generic icon and "Unknown publisher".
- **Operator decisions (2026-10-24), resolving the divert:**
  - **Ubuntu `.deb` upgrade and removal: document it, AppImage first.** Installing stays click-only on both distros. The Linux guide gives the one-line `sudo apt install ./…deb` (upgrade) and `sudo apt remove gleepglorp-ai` (removal) for Ubuntu, and recommends the AppImage to Ubuntu users who want no terminal at all. **The flight continues.** The mission's Linux criterion concerns installation, which is met. Its upgrade criterion concerns keeping data, which is met; the upgrade path on Ubuntu is documented.
  - **Cosmetics: a small fix leg** (shorter notice text; icon and developer/publisher fields in the metainfo). It is inserted as leg 11 (`notice-and-metainfo-polish`), and the following legs renumber: `fresh-vm-checks` is now leg 12, `linux-hat` leg 13.
- **Hosted run 1 (`40127933969`) green on the first dispatch** (1 of 6 used):
  - build 2m13s, audit PASS;
  - all four cells PASS, with the deb cells' G3 and single-instance PASS;
  - 471 s wall, about 18 billed job-minutes, against the 36 estimated;
  - runner: Ubuntu 24.04.5, 13 GB free, 7 GB RAM.

  Leg 10's comparison and baseline gates are running.
- **Flight landed (2026-10-24).**
  - All 13 legs completed. The full browser gate passed (`PARALLEL_RESULT rc=0 total=1450s lanes=12`; `knowledge` was over its budget, 326 s against 300 s, a warning that this flight touched no knowledge code).
  - Status `landed`, and Flight 2 is checked off in the mission.
  - The flight PR is opened ready for review. The debrief (`/mission-control:flight-debrief`) is next.

---

## Leg Progress

### appimage-library-fallback

**Status**: landed (leg 1). The divert test (AC4) passed. Evidence: `$HOME/the-one-m32-evidence/f2/leg1/` (`linux/<fmt>/<distro>-<image>[-variant]/`, `score-*.txt`, `build-*.log`, `needed-readelf.txt`, `ac2-find.txt`, `bundle-diff.txt`, `SHA256SUMS`). Packages: `$HOME/the-one-m32-build/f2/packages/` (Flight 1's `…/packages/` untouched). Changed: `packaging/linux/{build.Dockerfile,build.sh,build-inner.sh,rthook_host_gtk.py,the-one.spec,README.md}`, `packaging/spike/{stage.py,check.sh,inner.sh,score.py,README.md}`.

- **Pins.** Base `ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac` (re-read; the tag had not moved). `uv` 0.9.30 by digest `sha256:538e0b39736e7feae937a65983e49d2ab75e1559d35041f9878b7b7e51de91e4`. Build log head: `Python: 3.11.14`, `PyInstaller: 6.22.3`. Bundled versions recorded per build: `libglib2.0-0t64`/`libgirepository-2.0-0` 2.80.0-6ubuntu3.10, `libayatana-appindicator3-1`/`gir1.2-ayatanaappindicator3-0.1` 0.5.93-1build3, `libayatana-indicator3-7` 0.9.4-1build1, `libayatana-ido3-0.4-0` 0.10.1-1build2, `libdbusmenu-glib4`/`libdbusmenu-gtk3-4` 18.10.20180917~bzr492+repack1-3.1ubuntu5.
- **Packages (sha256, final build).** AppImage 0.11.8 a8faed19…4beead45, AppImage 0.11.9.dev1 5a809090…1e2ad4e0, `.deb` 0.11.8 b7f7b82a…791b5c78, `.deb` 0.11.9~dev1 550c0d08…109bd6a3 (full values in `SHA256SUMS`). Staged from `git archive HEAD` (`M32_FROM_HEAD=1`, 980415e), so leg 2's concurrent `the_one/` edits are not in these packages.
- **Fallback set** (AppDir `usr/lib/gleepglorp-ai-fallback/lib/`, real files by soname): `libgirepository-2.0.so.0`, `libdbusmenu-glib.so.4`, `libdbusmenu-gtk3.so.4`, `libayatana-ido3-0.4.so.0`, `libayatana-indicator3.so.7`, `libayatana-appindicator3.so.1`; plus `girepository-1.0/AyatanaAppIndicator3-0.1.typelib`. `find` over the extracted AppImage lists exactly these seven and no compat symlink; zero `libgirepository*`/`libayatana*`/`libdbusmenu*`/`*.typelib` under `usr/lib/gleepglorp-ai/`; `dpkg-deb -c` of the `.deb` shows no fallback directory. The NEEDED walk (in `build-inner.sh`, `readelf -d`) passed; the lists are in `needed-readelf.txt`.
- **AC2b.** The container bundle's file list is identical to Flight 1's (`bundle-diff.txt` empty, 1025 files); the PYZ TOC has the 22 `gi.overrides*` entries (`GLib`, `Gtk`, `Gio`, ...); no `excludes.txt` pattern matches a bundle file. The closure differs from Flight 1's by one pin, `filelock` 3.29.0 to 4.2.1 (the lock moved since), which does not change the file list.
- **AC4 (the divert test) PASS** (`score-probe.txt`, `linux/appimage/*-probe*`; `LD_BIND_NOW=1`, WSLg display, Gtk window plus `WebKit2.WebView` plus `AyatanaAppIndicator3.Indicator`, main loop 4 s, stderr grepped):
  - Debian 13 baseline (GLib 2.84): `PASS`; the maps show `libgirepository-2.0`, `libayatana-indicator3`, `libayatana-ido3`, `libayatana-appindicator3` from the AppImage and the two dbusmenu libraries from `/usr/lib`.
  - Ubuntu 26.04 baseline (GLib 2.88): `PASS`, all six from `/usr/lib` (typelib from the fallback dir).
  - Ubuntu 26.04 with `M32_FORCE_FALLBACK=1` (the GLib 2.88 evidence): `PASS`, all six 24.04 copies loaded from the AppImage by the maps, no crash, no `undefined symbol`, no GLib/GObject critical or warning.
  - `.deb` control runs on both images: `PASS`, no excluded lines (control stderr had no matching line).
  - The first force-run logged one `GLib-GIO-WARNING ... Error releasing name ...WebProcess: The connection is closed`, from WebKit's helper process after the probe called `os._exit` while the session bus was torn down (kept as `ubuntu-26.04-baseline-probe-force-first-run-teardown-warning`). It is the probe's teardown, not the ABI; the probe now destroys the window and runs the loop 1.5 s more before exiting, and the clean re-run is the evidence above.
- **AC5, `score.py` lines** (`score-ac5.txt`):
  - `appimage/ubuntu-26.04-baseline: G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=PASS single=PASS`
  - `appimage/debian-13-baseline: G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=PASS single=PASS`
  - Unpinned `doctor` passes on both (desktop shell OK). The Ubuntu run was repeated once: its first run (`score-ac5-run1.txt`, dir `…-flaky-load-run1`) had the server not go live in 120 s while host load average was about 10 (leg 2's tests and a VM container), a load flake with no window; the repeat passed.
  - G3 is per soname: Debian 13 gets girepository, indicator, ido and appindicator from the mount, dbusmenu from `/usr/lib`; Ubuntu 26.04 gets all from `/usr/lib`; WebKitWebProcess maps nothing from the mount; the hook's `M32_DEBUG_ENV` report agrees with the maps and with `ldconfig -p` (`hook_cross_check` is empty).
- **AC3.** `LD_LIBRARY_PATH` is `None` in the hook's report; in `/proc/<pid>/environ` of every WebKitWebProcess none of `LD_LIBRARY_PATH`, `LD_PRELOAD`, `GI_TYPELIB_PATH`, `GIO_MODULE_DIR`, `GTK_PATH`, `XDG_DATA_DIRS` is set (only `APPDIR`/`ARGV0`). The UI process's own `/proc/<pid>/environ` is the bootloader's initial block and still names the bundle; the hook edits the live environment, so `score.py` reads the web processes only, as the AC says.
- **Two defects found and fixed here (both would have failed AC3 and the first one was latent in Flight 1):**
  1. PyInstaller's stock `pyi_rth_gi/gio/glib/gtk` runtime hooks run AFTER `rthook_host_gtk.py`, so they re-pointed `GI_TYPELIB_PATH`, `GIO_MODULE_DIR`, `XDG_DATA_DIRS`, `GTK_PATH` into the bundle and WebKit's helpers inherited them. Flight 1's hook deletions were ineffective. `the-one.spec` now drops those four scripts (they only set environment variables). This applies to both packages.
  2. A fallback typelib directory in `GI_TYPELIB_PATH` would leak the AppImage mount into the helpers. The hook now forces gi to read the search path (`gi.require_version("GLib", "2.0")`) and then drops the variable, only when the fallback typelib dir was added.
- **AC6** (`score-ac6.txt`, `…-host-typelib`, `…-host-ayatana`):
  - `appimage/ubuntu-26.04-baseline` + `gir1.2-ayatanaappindicator3-0.1`: `G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=PASS single=PASS`; nothing mapped from the fallback dir; `GI_TYPELIB_PATH` is the three host dirs only.
  - `appimage/debian-13-baseline` + `libayatana-appindicator3-1 gir1.2-ayatanaappindicator3-0.1`: same PASS line; `ldconfig -p` still has no `libgirepository-2.0` after the install (precheck holds), the maps show `libgirepository-2.0` from the mount and the Ayatana and dbusmenu libraries from `/usr/lib`; no fallback typelib dir.
- **AC7, `.deb`** (`score-ac7.txt`): `deb/ubuntu-26.04-baseline` and `deb/debian-13-baseline`: `G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=PASS single=PASS`; both `bare`: `G1p=PASS G1u=PASS G2=PASS G3=N/A G4=PASS upgrade=PASS single=N/A`. For the `.deb` (no preload) the tray libraries count 0 or 1 in the UI process and must be from `/usr/lib` (the gate pins pystray's `gtk` backend, so they are not loaded).
- **AC8, bare hosts** (`score-ac8.txt`): the AppImage's `version` prints `GleepGlorp AI v0.11.8` (rc=0) and `doctor` reaches `RESULT: FAIL` with no traceback on both bare images. Expected until leg 2's DD11 split reaches a rebuilt package: `desktop shell: FAIL — unexpected error: Namespace Gtk not available` (both pinned and unpinned; `G1p=FAIL G1u=FAIL`, the other gates PASS). These packages were built before leg 2 landed.
- **Deviation (DD2).** Staging (`stage.py`, which runs `git rev-parse`) and `uv export` run on the host, not in the container: this checkout is a git worktree whose `.git` file points into Mission 31's checkout, which must not be mounted. The container gets the staged copy, `packaging/` (read-only) and the output dir. This replaces DD2's `safe.directory` note; on the GitHub runner staging runs on the runner the same way (leg 9). `stage.py` gained `M32_SOURCE` (stage a `git archive HEAD` export instead of the working tree).
- **Harness notes.** `inner.sh`/`check.sh` were edited during one background run and corrupted that container's script read (bash reads scripts incrementally); that run was repeated. The Flight 1 scripts carried shellcheck warnings of the style kind, so `inner.sh` and `check.sh` carry file-level `disable=` lists (SC2164, SC2002, SC2086, SC2009, SC2034, SC2206, SC2015); everything else is clean.
- **AC9.** `ruff check packaging/` and `ruff format --check packaging/` pass; shellcheck 0.10.0 passes on `build.sh`, `build-inner.sh`, `inner.sh`, `check.sh`. The leg's changes are confined to `packaging/linux/`, `packaging/spike/` and this log. No port 8484/8485 used by this leg (the harness used 8490-8492 inside containers). The operator data dir's newest mtime is unchanged (1791383047.967 before and after). Only `m32-*` containers were created; `m32-gate-*`, `m32-build-*` and `m32-inspect` are removed (`m32-vm-provision-ubuntu` is leg 4's).
- **Evidence Table rows (for the flight's table):** `f2/leg1/score-ac5.txt` (G1-G4 AppImage), `score-probe.txt` (ABI probe, 5 runs), `score-ac6.txt` (mixed host), `score-ac7.txt` (`.deb`), `score-ac8.txt` (bare), `needed-readelf.txt`, `ac2-find.txt`, `bundle-diff.txt`, `SHA256SUMS`, `build-*.log`.

### tray-selection-and-doctor

**Status**: landed (leg 2). Files: `the_one/interfaces/desktop/host.py` (new; notifications merged in, no `notify.py`), `tray.py`, `shell.py`, `the_one/diagnostics.py`, `the_one/platform/sandbox/factory.py`, tests, `the_one/agents.md`, one CLAUDE.md sentence.

- **Interim state, until leg 5:** a "no tray" decision (`none`/`unavailable`) only skips building and starting the tray; no closing handler is registered, so closing the window still exits (the F4 path). `shell._tray_mode` records `indicator`/`xembed`/`none`/`failed`, `None` on Windows and macOS.
- **Naming:** `shell.py` imports the helper module as `desktop_host`, because `host` is already a local (`settings.host`) in `run()` and `_boot`. It is always called as `desktop_host.fn(...)` at call time. `detect_tray` returns `(mode, reason)`.
- **Factory:** `get_sandbox_backend()` and the new `describe_selection()` share one `_select()`; log texts and levels are unchanged.
- **AC0 fixture:** `stub_desktop_host` in `tests/conftest.py`, applied by `pytestmark` in `test_desktop_tray.py`, `test_desktop_shell.py`, `test_doctor.py`, `test_window_state.py`.
- **AC8 (dev host, Ubuntu 24.04 WSLg, scratch data dir, port 8496, exit 0):** `desktop shell: OK — skipped — unexpected error: Namespace AyatanaAppIndicator3 not available` (the non-frozen path, unchanged: pystray's import raises `ValueError` here), `sandbox: bubblewrap`, `tray: none — no tray backend for this session` (WAYLAND_DISPLAY and DISPLAY both set, no Ayatana, so no backend), `RESULT: PASS`. With `DISPLAY=:0` and no Wayland: `tray: none — no X11 system tray on this display`. With `DBUS_SESSION_BUS_ADDRESS` unset and an empty `XDG_RUNTIME_DIR`: the doctor line was still `tray: none — no tray backend` because the backend is None on this host, so the bus check is never reached; with `PYSTRAY_BACKEND=appindicator` added it prints `tray: unavailable — no session bus`, exit 0, and `dbus-daemon` PIDs unchanged. Note: the very first no-bus run was followed by two new `dbus-daemon` processes (an autolaunched session bus and an at-spi bus on the scratch `XDG_RUNTIME_DIR`); five later doctor runs and the host helpers run alone started none, so the cause is not reproduced and not in the new code path (the helper never autolaunches). The kill was refused by the permission classifier, so those two PIDs (2132108, 2132116) are left for the operator.
- **Gates:** `make test-unit`: 6852 passed, 12 skipped (the expected count). `ruff check` and `ruff format --check` clean on `the_one/ tests/ scripts/ evals/`.
- **Not covered by unit tests:** the PYZ case of `bundle_has_modules` (verified on the dev host's real `pystray` package only); the webview-path "no notification" assertion is structural (the call sits in the browser-fallback branch).

---

### gtk-window-fixes

- Code half complete. Leg 1 landed; smoke half done.
- shell.py: `_is_gtk_backend`, `_on_wayland`, `_show_window`, GTK-safe `_save_current_geometry` (native get_size/get_position, size only on Wayland), `_on_closing` registered in every tray mode (no tray allows destroy), `_on_quit(None)` safe, `window_visible`/`window_state`/`quit_desktop`, `_session`. app.py: `GET /api/window/state`, `POST /api/window/quit`, `window_focus` now a plain `def`. SECURITY-MODEL.md line added.
- Tests: new tests/test_window_routes.py; GTK/closing/show/quit tests in tests/test_desktop_tray.py (two leg-2 tests updated: a closing handler is now always registered). Touched files 133 passed; `make test-unit` 6871 passed, 12 skipped; ruff clean; settings browser lane (THE_ONE_TEST_NETNS=1) 109 passed.
- Smoke: built `gleepglorp-ai_0.11.9~dev3_amd64.deb` (working-tree staging) with M32_BUILD=$HOME/the-one-m32-build/f2. Harness `packaging/spike/gtk-smoke.sh` + `gtk-smoke-inner.sh` (private Xvfb :99, no WM, python3-xlib WM_DELETE_WINDOW; shellcheck clean). ubuntu-26.04 and debian-13 baselines: OVERALL PASS (window maps: state visible:true + IsViewable; WM_DELETE close exits <15 s with window-state.json 1440x900; S1 == S2 == 1440x900, equal saved sizes; POST /api/window/quit returned quit:true with the app's pid and exited <15 s). Tray mode `none` on both ("no StatusNotifier watcher").
- Flight 1 control (0.11.8) on both: toplevel `IsUnMapped` after boot with no focus request (trap 2 seen); state route 404 (n/a). Trap 1: not reproduced as a deadlock signal; WM_DELETE_WINDOW on the unmapped control window did not exit it within 15 s (old code registers `closing` only with a tray, and there is none under Xvfb, so the delete is ignored/unmapped; reason recorded, not claimed as the deadlock).
- Note: the tray decision line is logged after the window is shown, so the harness reads it after step 2.
- Evidence: $HOME/the-one-m32-evidence/f2/leg3/{ubuntu-26.04,debian-13}[-control]/. No m32-gtk-smoke container left; ports 8490 only (in containers).

### vm-apparatus

**Status**: landed (leg 4, all three phases done). Files: `packaging/linux/vm/` only (`Dockerfile`, `lib.sh`, `vm.sh`, `qmp.py`, `provision-debian.sh`, `debian-user-data.in`, `README.md`). Evidence: `$HOME/the-one-m32-evidence/f2/leg4/`.

**Phase A checkpoint (runner, helpers, Debian) — complete.**

- **Runner image:** `m32/qemu` from `debian@sha256:4c25275446ca371766b8b093c696782eabce06263fccacb8d5d813b3dc44b308`; QEMU 10.0.13, OVMF 4M. Builds in about 25 s. Docker is Docker Desktop (WSL), and the QMP unix socket and the KVM passthrough both work through bind mounts as the invoking uid.
- **Images:** Debian pinned to `20261021-2638` (`debian-13-generic-amd64-20261021-2638.qcow2`, 438,566,912 B, sha512 `70ef6adc...ead5f0` verified against that directory's `SHA512SUMS`). Ubuntu **26.04.1** ISO downloaded and sha256-verified (`601e30fb...da1f`, 6,482,409,472 B) at `$M32_VM/dl/`; not installed (phase B).
- **Debian base** `debian-13-base.qcow2` (30 GB virtual, 5.95 GB on disk; read-only): sha256 `3735df2cb0fc230b009af573d0de5e61d7b969d0fdba6fa63503a332c2e5e9b5`; `debian-13-base.vars.fd` sha256 `7fb553a90ccdfb70f0d7a30b6d39c8d9c701ea0d827eeb79f1b1ca33b7177258`. `base-hash debian --check` is OK after three runs. Provisioning took one iteration, about 7 min (1275 packages for `task-gnome-desktop`); it is unattended and the first attempt was clean (the only slip was a missing `chmod +x` on `vm.sh`, which broke the final hash step, redone by hand).
- **Debian base contents (recorded, not asserted):** Debian 13 trixie, kernel 6.12.113, GNOME Shell 48.7, GDM autologin as `tester`, Wayland session (`loginctl show-session` Type=wayland, State=active). `gnome-software` 48.3-2, `libgs_plugin_packagekit.so`, `packagekit` 1.3.1 (active) installed (AC3 asserted items hold). `libgirepository-2.0-0` **absent** (only `libgirepository-1.0-1` 1.84.0-1, plus `gir1.2-girepository-2.0`, `python3-gi` 3.50.0, GTK 3 and 4 typelibs, `gir1.2-webkit2-4.1`, `libwebkit2gtk-4.1-0` 2.54.0, `libwebkitgtk-6.0-4`). Ayatana/appindicator (`gir1.2-ayatanaappindicator3-0.1`, `libayatana-appindicator3-1`, `gir1.2-appindicator3-0.1`) **absent**. `libfuse2t64`/`libfuse2` **absent**; `fuse3` 3.17.2 and `fusermount3` present (so an AppImage will not find `libfuse.so.2`). `bubblewrap` 0.12.0 present: `bwrap --unshare-user --ro-bind / / true` exits 0; `kernel.unprivileged_userns_clone=1`; `kernel.apparmor_restrict_unprivileged_userns` does not exist (no AppArmor userns restriction on Debian). No terminal-free question here is answered yet; that is phase C.
- **Stock behaviour to know:** the first login shows the GNOME welcome dialog ("Skip"/"Take Tour", gnome-tour) and starts in the Activities overview: `key esc` closes the dialog, a second `key esc` leaves the overview. A "Software: Updates Ready to Install" notification appears too. Setting `welcome-dialog-last-shown-version` through SSH after boot is too late (the dialog is already up), so `vm.sh prep` only waits for SSH and the session bus.
- **Helper verbs proven on Debian (evidence files in the evidence dir):** `up` (and `--visible`: QEMU's GTK window started without error under WSLg, only a Fontconfig cache warning, since fixed with `HOME=/tmp`; the guest booted and answered SSH; I could not see the Windows-side window, so "visible" is started-clean, not observed), `status`, `down` (QMP quit, `docker stop` by name, overlay deleted), `base-hash`/`--check`, `ssh`, `session-env` (`XDG_RUNTIME_DIR=/run/user/1000`, `WAYLAND_DISPLAY=wayland-0`, `DBUS_SESSION_BUS_ADDRESS`), `copy-in`, `prep`. `qmp.py`: `screendump` (png), `key` (`esc`, `super`), `type` (lowercase and the rest of the table), `move`, `click left`/`right`/`double`, `wait-for-screen` (returns "stable (diff 0.00000)"), `raw`. AC4 on Debian: Super then `files` shows Files in the search (debian-ac4/t2.png); an absolute click on "Show Apps" (919,738) opened the app grid, and a click at (577,300) launched GNOME Clocks (`gnome-clocks` seen over SSH, screendump `debian-ac4-clocks.png`): the pointer lands where aimed with `usb-tablet`. Not yet exercised: uppercase and symbol typing on a real input (the key table is written, untested).
- **Lint:** `shellcheck` 0.10.0 clean on all scripts; `ruff check` and `ruff format --check` clean on `qmp.py`.
- **Resources:** a running Debian guest (idle desktop): container 2.56 GiB RAM, about 33% of a CPU; guest sees 5.9 GB and 4 vCPU. Host before each `up`: `free -g` available 10-11 GB, so no wait was needed (waits recorded: none). `du -sh $HOME/the-one-m32-vm` is 11 GB at this point (Debian base 5.9 GB, Debian image 0.44 GB, Ubuntu ISO 6.5 GB less sparse savings). No `m32-vm-*` container is left running. No root-owned files in `$M32_VM`. Operator data dir: newest mtime `1791383047` (2026-10-07) at start and end, unchanged. Ports 8484/8485 untouched.
- **For phase B and C:** `vm.sh` already maps `ubuntu` to `ubuntu-26.04-base` and port 2292; `provision-ubuntu.sh` does not exist yet. Boot is fast: the Debian guest has SSH about 20-30 s after `up` and its desktop in under 60 s. A click or key needs no sleep, but `sleep 2` before a screendump avoids catching mid-animation. The Debian guest uses NetworkManager and gets 10.0.2.15 through QEMU user networking; apt works in the guest. The `.deb` flow in P1 needs the package copied in with `vm.sh copy-in debian <file> ~/Downloads/`. `wait-for-screen` ignores the top 40 px and takes about 1 s per probe.

**Phase B checkpoint (Ubuntu 26.04.1 base) — complete.** Files: `provision-ubuntu.sh`, `ubuntu-user-data.in` (new), README updated. Evidence: `$HOME/the-one-m32-evidence/f2/leg4/{ubuntu-prov,ubuntu-ac,ubuntu-ac2,ubuntu-ac3,ubuntu-final}/`.

- **Schema first:** read from the ISO (`minimal.standard.live.squashfs` → installer snap `ubuntu-desktop-bootstrap` 665 → `bin/subiquity/autoinstall-schema.json`). It is the subiquity schema (`identity` needs a crypted password, `ssh.install-server`, `source.id`, `storage.layout`, `shutdown`, `late-commands`, `refresh-installer`). `/casper/install-sources.yaml` offers `ubuntu-desktop-minimal` (**`default: true`**) and `ubuntu-desktop`. I used the installer's real default, **`ubuntu-desktop-minimal`** (the leg text said to expect `ubuntu-desktop`; the "default" selection is the minimal one, and it carries App Center). `UBUNTU_SOURCE_ID` overrides it. Deviation, recorded.
- **Autoinstall worked on the first try** (CIDATA ISO as a read-only virtio disk, direct `-kernel`/`-initrd`, `-append "autoinstall quiet ---"`, ISO as `-cdrom`, `-no-reboot`; the installer ran headless, UI showed "Copying files…", then powered off). Install run 826-1039 s (about 15-17 min). Four provisioning iterations in total, three of them only fixing the first-run wizards (the autoinstall itself needed no change): (1) the Ubuntu "existing-user" welcome appeared because the installer creates `/home/tester` (from the old skel) *before* late-commands, so the `/etc/skel` stamp never reached it → late-command now writes the stamp straight into the home; (2) the "Welcome to Ubuntu 26.04.1 LTS" upgrade wizard (`gnome-initial-setup --upgrade-user`) appeared → I first guessed `~/.config/upgrade-26.04-done`; (3) the real stamp, read from `/usr/lib/systemd/user/gnome-initial-setup-upgrade-login.service`, is `~/.config/gnome-initial-setup/upgrade-26.04-done`; (4) final base boots straight to the desktop, no wizard. Earlier bases' hashes are in `ubuntu-prov/iter*-base.sha256` (discarded). Disk-only first boot (poweroff over SSH after `snap wait system seed.loaded`) is in the script.
- **Final base:** `ubuntu-26.04-base.qcow2` (40 GB virtual, 9.4 GB on disk, read-only) sha256 `5aad3618711915178cb749df4c118ee36e4feb3fb6f200868f3b9fd271d82e66`; `ubuntu-26.04-base.vars.fd` sha256 `8f87ed7cfed8126f1d5d754becd85dbbfdd2c5a5653aa5e697072a62ce6d5309`. `base-hash ubuntu --check` OK after the runs. `du -sh $HOME/the-one-m32-vm` 22 GB.
- **AC2 results (final base):** autologin to a GNOME session (`ubuntu-final/boot.png`: the desktop with the dock, no wizard); Ubuntu 26.04.1 LTS, kernel 7.0.0-38-generic, GNOME Shell 50.1, `loginctl` Type=wayland State=active. `snap list`: bare, core24, desktop-security-center, firefox 154.0-1, firmware-updater, gnome-46-2404, gtk-common-themes, hwctl, mesa-2404, prompting-client, **snap-store** (0+git.8334e2e4, rev 1390, channel 2/stable; this is App Center, the dock shows it), snapd 2.76.2, snapd-desktop-integration. **Recorded presences:** `gir1.2-ayatanaappindicator3-0.1` **absent**; `libgirepository-2.0-0` **present** (2.88.0-1ubuntu0.1; `python3-gi` 3.56.2, `gir1.2-gtk-3.0/4.0`, `gir1.2-webkit2-4.1` 2.52.6, `libwebkit2gtk-4.1-0`, `libwebkitgtk-6.0-4` present); `libfuse2t64` **absent** (only `fuse3` 3.18.2; no `libfuse.so.2`); `libayatana-appindicator3-1` 0.5.94 present (C library, no GI typelib). `bubblewrap` 0.11.1, `kernel.apparmor_restrict_unprivileged_userns = 1`. **Tray host: the AppIndicator GNOME extension IS enabled** — `gnome-extensions list --enabled` in the session env: `ding@rastersoft.com`, `snapd-prompting@canonical.com`, `snapd-search-provider@canonical.com`, `tiling-assistant@ubuntu.com`, **`ubuntu-appindicators@ubuntu.com`**, `ubuntu-dock@ubuntu.com`, `web-search-provider@ubuntu.com`. So the Ubuntu guest has a tray host, but the typelib `gir1.2-ayatanaappindicator3-0.1` is absent, so a Python app using it would take its fallback path. The only addition beyond the default selection is `openssh-server` (through `ssh: install-server: true`; `openssh-server` 1:10.2p1-2ubuntu3.8), plus a passwordless sudoers drop-in (apparatus). Lock-enabled false, idle-delay 0 via the system dconf default.
- **AC4 on Ubuntu:** `loginctl` Type=wayland; Super then `files` shows Files (`ac4-search.png`), Enter opens it (`ac4-files.png`); an absolute click on the dock's Show Apps (33,767) opens the app grid (`ac4-grid.png`) and a click at (303,348) launches GNOME Clocks (`gnome-clocks` seen over SSH, `ac4-clocks.png`). The pointer lands where aimed.
- **AC6 so far:** only `m32-vm-*` containers, as the invoking uid, only `/dev/kvm`, ports on 127.0.0.1; none left running (`docker ps -a --filter name=m32-vm` empty); no non-owned files in `$M32_VM`; `free -g` available was 11-12 GB before every `up`, no waits; Ubuntu guest container RAM about 2.9 GiB idle (`ubuntu-final/stats.txt`; provisioning ran with 6 GB guest RAM); operator data dir newest file mtime `1791383047` unchanged; nothing listening on 8484/8485 (`ss`); `shellcheck -x` clean on all scripts from inside `packaging/linux/vm/`; `git status` shows only `packaging/linux/vm/` (untracked).
- **For phase C:** (1) First login shows no wizard on Ubuntu, but the first Activities/Esc state may differ from Debian; take a screendump before assuming. (2) Ubuntu's Files `Downloads` exists; `copy-in ubuntu <file> ~/Downloads/` works over the same SSH key. (3) Software centre here is `snap-store` (App Center); expect the `snap changes` settle wait before P1. (4) The default selection is minimal, so no Thunderbird, LibreOffice or similar; Firefox is a snap. (5) Provisioning from scratch takes about 20 min; remove the three base files (`.qcow2`, `.vars.fd`, `.sha256`) deliberately to redo. (6) `snapd` 2.76.2 is the seeded one; no refresh was observed during the runs, so `snap refresh` may fire later.

**Phase C checkpoint (the premises, AC5, and AC6 final) — complete; leg landed.** Evidence: `$HOME/the-one-m32-evidence/f2/leg4/p-ubuntu/` and `p-debian/` (numbered screendumps at every dialog, `p*-*.txt` SSH reads). Packages were Flight 1's, copied in with `copy-in`; every install under test was Files double-click, the software centre's Install, and the polkit password typed by QMP (no apt, dpkg or pkcon for an install under test; SSH for observation only). `snap changes` had settled (all Done) before P1; no retry was needed anywhere, so no divert.

**GTK versions (leg 5/6 activation-token work):** Ubuntu 26.04.1 `libgtk-3-0t64` 3.24.52-0ubuntu1; Debian 13 `libgtk-3-0t64` 3.24.49-3. WebKit2GTK 4.1: 2.52.6 (Ubuntu), 2.54.0 (Debian). Both guests: Wayland, mutter software-rendered (no GPU).

**AC5 answer table**

| # | Ubuntu 26.04.1 (App Center, snap-store 1390) | Debian 13 (GNOME Software 48.3) |
|---|---|---|
| P1 | **Yes, no terminal.** Double-click `.deb` opens App Center on a detail page for `gleepglorp-ai`, "Unknown publisher", orange "Potentially unsafe ... third party" banner; Install, then a second confirm dialog ("provided by a third party and may threaten your system... Are you sure?"), then polkit "Authentication is required to install untrusted software" (typed `m32testpw`). `dpkg -s` -> `install ok installed`, 0.11.8 (`p1-dpkg.txt`). Dependencies came from the mirrors (no mirror failure). | **Yes, no terminal.** Double-click opens GNOME Software, page titled `gleepglorp-ai` with a generic icon and "Local file"; Install, then polkit "Authentication is required to install untrusted software". `dpkg -s` -> installed, 0.11.8. The UI sat at "Preparing..." a while after dpkg had finished (PackageKit was also downloading unrelated updates), then flipped to the real name "GleepGlorp AI" with the robot icon (from the `.desktop` file), Open and a trash button. |
| P5 | **Yes, renders.** Launch from the app grid (Super, type `gleep`, Enter; the icon shows) starts `the-one app` and WebKit processes, but **the window does not appear on first launch** (no dock entry, `/api/live` ok). A tray icon appears (the Ubuntu AppIndicator extension is the host); the tray menu "Show" did not raise it either. A **second launch** from the grid (`POST /api/window/focus` in the journal) shows the window: "Hello." Chats start page, mascot drawn, 1280x800 (`p-ubuntu/13-p5-relaunch.png`). Same trap-2 behaviour Flight 1's control saw (hidden toplevel at start); it is the 0.11.8 code, which this flight's no-tray hide/quit changes address. | **Yes, renders**, same sequence: first launch from the grid: process and WebKit up, no window, no tray (no host; journal shows only `libayatana-appindicator is deprecated`); second launch focuses and shows the "Hello." Chats page (`p-debian/11-p5-relaunch.png`). Only a Close button in the title bar (GNOME default, no min/max). |
| P2 | **No, not as an upgrade.** Double-click `0.11.9~dev1.deb`: the already-running App Center instance receives it (its window stays behind: Wayland does not raise; raise through the overview); the page shows version "0.11.9~dev1" but the button is a disabled grey **"Installed"**, and a freshly started App Center (closed, then reopened from the `.deb`) shows the same. `dpkg -s` stays 0.11.8 (`p2-dpkg.txt`). App Center compares by package name and offers no Update or Install for a newer local `.deb`. A user needs a terminal (`apt install ./x.deb`) or must remove first (see P3, which also fails). | **Yes.** Double-click `0.11.9~dev1.deb`: the page offers **"Install"** (not "Update"; the same window sits behind, raise via overview), polkit again, then `dpkg -s` -> 0.11.9~dev1. The running 0.11.8 process kept running after the upgrade (no restart prompt). |
| P3 | **Not listed, cannot be removed.** Manage > Installed apps search "gleep" / "gleepglorp", Explore search with the Snap and the Debian packages filters: nothing (control "cloc" finds Clocks, so the filter works). Cause: `appstreamcli search gleepglorp` finds no component and `/usr/share/metainfo` holds no entry for it. The `.deb`'s own App Center page only shows a disabled "Installed". No GUI route to Remove: **recorded as no**, which sets up leg 7's metainfo work (and leg 11 retries it). | **Listed only through the `.deb`, not in Installed or search.** Installed tab (scrolled alphabetically past "Fonts" to "Image Viewer") and search "gleepglorp" show nothing ("No App Found"); no AppStream component. But reopening the installed `.deb` shows Open plus a **trash** button; "Uninstall GleepGlorp AI?" (note: "App data and settings will be kept on disk") then polkit "Authentication is required to remove software": `dpkg -s` -> not installed (`p3-dpkg.txt`). The running app process survived the removal. |
| P4 | **Yes (fresh overlay, no `.deb`).** Files > Properties > "Executable as Program" (I set mode `a-x` over SSH first so the toggle was real) then double-click: launches `/tmp/.mount_Gleep*/usr/lib/gleepglorp-ai/the-one app` as `fuse.GleepGlorp_AI-0.11.8-x86_64.AppImage` (ro mount), WebKit processes up, `/api/live` -> ok, "Hello." window after a second launch (same hidden-first-window behaviour; no tray icon). **No `libfuse.so.2`** (`ldconfig -p` empty), `fusermount3` and `fusermount` present, `/dev/fuse` crw-rw-rw-: the AppImage's runtime works with FUSE 3 (Files showed no error). Stderr goes to the user journal (Files starts it under systemd), `p4-observe.txt`. | **Yes, but not in a window.** Same steps; mounted at `/tmp/.mount_Gleep*`, server up (`/api/live` ok, process 2112) and the app **opened the Chats page in Firefox** (`http://127.0.0.1:8484/#chats`, a handoff URL) instead of its own WebKit window, with no log line giving the reason (the `.deb` build on this guest does open a window). No `libfuse.so.2` (`/sbin/ldconfig -p`), `fusermount3` present, so FUSE worked. Leg 5/6 should find why the AppImage takes the browser path on Debian (most likely the GI/WebKit import in the frozen AppImage env). |
| P6 | `kernel.apparmor_restrict_unprivileged_userns = 1`, `kernel.unprivileged_userns_clone = 1`, `user.max_user_namespaces = 21407`; `bwrap --unshare-user --ro-bind / / true` exits **0** (`/etc/apparmor.d/bwrap-userns-restrict` exists, bubblewrap 0.11.1); `ps` shows `WebKitNetworkProcess` and two `WebKitWebProcess`, **none `bwrap`-wrapped**, in both the `.deb` and AppImage runs. | no `apparmor_restrict_unprivileged_userns` sysctl, `kernel.unprivileged_userns_clone = 1`, `user.max_user_namespaces = 23300`; `bwrap` exits **0** (bubblewrap 0.12.0); WebKit processes likewise not `bwrap`-wrapped. |

**For legs 5, 6, 7 and 11:** (1) **First-launch window is hidden on both guests** with the 0.11.8 code; relaunch (focus route) shows it, and the Ubuntu tray's "Show" did not. (2) **A stock Ubuntu cannot upgrade or remove a local `.deb` through App Center** (P2/P3) and shows a double warning on install; the guide must give the `apt install ./x.deb` line for upgrades and removal there, or leg 7's metainfo/AppStream work must be tested to change App Center's behaviour (it matches by name, so it may not). Debian's GNOME Software upgrades and removes fine but never lists the package under Installed or search until metainfo exists. (3) The AppImage works without `libfuse2t64` on both guests and needs the exec bit set through Properties (a copy over SSH preserved it, so tests must chmod first). (4) Driving tips: a window opened by a second request does not raise on Wayland, so use the overview (Super, click the thumbnail); `qmp.py raw input-send-event` with `btn` `wheel-down` scrolls; the first double-click after a window change sometimes only selects, so look before assuming; Debian shows the GNOME welcome dialog on every fresh overlay (esc twice). (5) Tray: Ubuntu has the host (`ubuntu-appindicators` enabled) and the app drew an icon with a menu "Show"/"Quit"; Debian has none.

**AC6 final:** only `m32-vm-*` containers from `m32/qemu`, run as the invoking uid; `docker ps -a --filter name=m32-` is empty at the end (`ac6-final.txt`); `find $HOME/the-one-m32-vm -not -user $(id -u)` empty; ports 127.0.0.1 only (2291/2292); nothing on 8484/8485 on the host (`ss`; the apps ran on 8484 inside the guests); `base-hash --check` OK for all four files (both bases and both vars files) at the end; operator data dir newest mtime `1791383047` unchanged (start and end); `free -g` available 10-11 GB before each `up`, no waits; peak guest container RAM: Ubuntu 4.93 GiB with the `.deb` app running (3.84 GiB with the AppImage app), Debian 4.18 GiB (3.55 GiB AppImage run) (`stats.txt` in both evidence folders); `du -sh $HOME/the-one-m32-vm` 22 GB; `git status --porcelain -- packaging/linux/vm` shows only the untracked leg files, and no vm file was changed in this phase. Leg status set to `landed`.

### no-tray-lifecycle

**Phase A checkpoint — complete (leg stays in-flight; phase B = focus token, takeover, comparator, pid wait).**

- **Shell.** `_on_closing` is registered right after `create_window` (before the tray decision; `_tray_mode` None means allow). Close states: really-quit allow; tray icon present hide-to-tray; `_tray_mode == "none"` hide through module-level `_no_tray_hide(window)` (hide, tracked visibility False, one-time `send_notification`, never blocks); `failed`/None allow. `_close_to_tray`'s dead `_icon is None` destroy branch is gone. `notice.py` gained `no_tray_notice_shown()` / `mark_no_tray_notice_shown()` (marker `.no_tray_notice_shown`, separate from the tray's). `window_state` (store), `notice`, `tray`, `host` and `__version__` are module-scope imports; an AST test pins no `import` inside `_on_closing`, `_no_tray_hide`, `_close_to_tray`, `_save_current_geometry`, `quit_desktop`, `window_state`, and a subprocess test pins that importing the shell loads neither pystray nor webview.
- **Quit and boot race.** `_window_lock`, `_booting` (set after the `is_ours` return, before the server thread; cleared at step 6 under the lock, in the `_boot` except path, before the missing-pywebview `SystemExit`, on browser-branch entry, and in `run()`'s `finally`), `_quit_requested`, `_browser_server`. `quit_desktop()` now returns the state (`"window"|"booting"|"browser"|None`); `_on_quit` is never called under the lock. `_boot` honours a recorded quit after the splash wait, after `_wait_until_serving`, before the show, and at step 6 (publish + clear `_booting` + read the flag in one critical section, quit right after release). Beyond the leg text: the step-6 quit also sets `_main_shown` and destroys the splash, because a main window destroyed before its `loaded` fires would otherwise leave the splash and `webview.start` alive. The abort path sets `_really_quit` so the destroy is not cancelled by `_on_closing`. Browser branch: a quit during its server wait sets `server.should_exit`; a failed wait or a set flag then returns without opening the browser. `mode` is `serve` (`_session is None`) / `quitting` / `window` / `booting` / `browser` / None; the route's `except` fallback reports `serve`. The `is_ours` return now clears `_session` (it leaked into later tests and `window_state`).
- **App.** `POST /api/window/quit` returns `{quit, pid, state}`.
- **CLI.** `the-one quit` (`main._quit_command`): missing credential file prints "GleepGlorp AI is not running." and creates nothing; read-only `lookup_credential`; connection error "not running"; `quit:true` "is quitting."; `quit:false` server-only line; 401/403 distinct port line (exit 1); 404/405 "too old" line (exit 1); other status or bad body exit 1. `--wait` (pid wait) is NOT implemented: it needs phase B's `_pid_alive`, so it is deferred to phase B. Usage text lists `quit`.
- **Docs.** CLAUDE.md phrase corrected ("ours by credential (attach a window, or replace an older running version)") and a `the-one quit` Commands entry; `SECURITY-MODEL.md` quit-route paragraph extended (activation-token sentence belongs to phase B); the stale `_select_port` fall-through comment rewritten.
- **Tests.** `tests/test_desktop_shell.py` (close states, markers, AST/import checks, closing-before-tray order, `quit_desktop` per state, `mode`, boot race at all four checkpoints, `_booting` lifecycle, browser branch), `tests/test_cli_quit.py` (11, local stub server), `tests/test_operator_port_guard.py` + a `tests/conftest.py` autouse guard (any `httpx.Client`/`AsyncClient` request to port 8484/8485 raises `AssertionError`); routes/tray tests updated for the new return values.
- **AC8 (phase A part), real GTK, both baselines, none mode** (scratch `.deb` 0.11.9~dev5 built from this tree; extended `packaging/spike/gtk-smoke-inner.sh`): close hides (`visible:false`, toplevel `IsUnMapped`, process group alive, `.no_tray_notice_shown` written, geometry saved); a second `the-one app` shows it (`visible:true`, `IsViewable`) and exits by itself; `the-one quit` exits the app in 1-2 s (rc 0), a second `quit` prints "not running"; relaunch size stable; the quit route reply `{"quit":true,"pid":...,"state":"window"}`. Both `OVERALL PASS` (ubuntu-26.04 and debian-13). Evidence `$HOME/the-one-m32-evidence/f2/leg5/{ubuntu-26.04,debian-13}/` (chowned back to the invoking uid with a `m32-gtk-smoke-chown` container). The notice itself is observable only in the Ubuntu container log (xdg-desktop-portal fallback line); the real banner is a leg 6 VM check.
- **Gates so far.** `ruff check` clean on everything but leg 7's `tests/test_packaging_metadata.py:24` (E501, not mine); `ruff format --check` clean; shellcheck 0.11.0 (scratch venv, wheel from `/tmp/claude-1000/sc`) clean on `gtk-smoke.sh` and `gtk-smoke-inner.sh`; browser `settings` lane 109 passed (`THE_ONE_TEST_NETNS=1`).
- **For leg 7 / phase B.** `AppRun` and the frozen entry must pass `quit` through (a no-argument run means `app`). Phase B owns `_pid_alive`, so `the-one quit --wait` can share it.

**Phase B checkpoint — complete.**

- **Focus token.** `POST /api/window/focus` takes an optional `WindowFocusBody {activation_token}` (`max_length=256`, pattern `^\S*$`; no body and `{}` still work). `focus_window(activation_token=None)`: on GTK with a token, `_gtk_activate` clears `hidden` and queues ONE `glib.idle_add` doing `set_startup_id`, `deiconify`, `present` (no plain present precedes it); only a 6-character prefix is logged. No token: the old `_show_window(restore=True)`.
- **Takeover (DD13).** Seams in `shell.py`: `_running_version`, `_request_quit`, `_pid_alive` (POSIX `os.kill(pid, 0)`; win32 `OpenProcess(SYNCHRONIZE)` + `WaitForSingleObject`, never `os.kill`), `_now`, `_sleep`, `_post_focus` (forwards `XDG_ACTIVATION_TOKEN`/`DESKTOP_STARTUP_ID`), `_wait_for_exit` (0.5 s poll, 75 s bound, one "Updating GleepGlorp AI..." notice after 3 s), `_takeover` (older+accepted waits then re-runs `_select_port`; `quit:false` neither waits nor focuses; 404/405 focuses + "restart GleepGlorp AI" log; 401/403 distinct log; other/never-exits focus). `_select_port`'s `(port, bool)` shape unchanged. Comparator `_parse_version`/`_is_older` (`X.Y.Z[.devN]`, numeric dev, unparseable = not older). dpkg order run once on the dev host: `0.11.8 < 0.11.9~dev1 < 0.11.9`, `dev3 < dev4`, `dev9 < dev10` -- all match.
- **CLI.** `the-one quit [--wait|--no-wait]` (default on when stdout is a tty); `--wait` shares `shell._wait_for_exit`, exit 1 with "did not exit within 75 seconds" at the bound. CLAUDE.md Commands comment updated; `SECURITY-MODEL.md` gained the activation-token and takeover sentence.
- **Tests.** New `tests/test_desktop_takeover.py` (comparator table, every takeover branch through the seams with a fake clock, `_pid_alive` win32/posix, token env, run() restart after takeover), focus-route/token/GTK-one-idle tests in `tests/test_window_focus.py`, `--wait` tests in `tests/test_cli_quit.py`; the three `is_ours` tests (two in `test_desktop_shell.py`) now stub `_running_version`. `make test-unit` 7035 passed, 12 skipped; ruff check/format clean; shellcheck clean on both smoke scripts; `settings` lane 109 passed (netns).
- **GTK versions (leg 4 baselines).** Ubuntu 26.04 `libgtk-3-0t64` 3.24.52; Debian 13 `libgtk-3-0` 3.24.49. The Wayland activation path itself remains a leg 6 VM check (a real app-grid click; a container run has no token).
- **AC8 phase B, real GTK, both baselines** (harness extended: `gtk-smoke.sh --takeover-from OLD.deb`, install OLD, start it, upgrade the package in place under it, launch the new one). This-tree N 0.11.9.dev7 -> N+1 0.11.9.dev8: the new launch POSTs the quit route (old log: `POST /api/window/quit 200`, orderly shutdown), old gone in 1 s, new serves v0.11.9.dev8 with `visible:true`, `the-one quit --wait` ends it; PASS on ubuntu-26.04 and debian-13. Flight 1's N 0.11.8 -> dev8: no quit route, so the new launch focuses it and exits in 1 s, N keeps running as v0.11.8, log "restart GleepGlorp AI to finish the upgrade"; PASS on both. The phase A smoke re-run on dev8 PASS on both (relaunch with no token still shows). Evidence `$HOME/the-one-m32-evidence/f2/leg5/{takeover-thistree,takeover-flight1,regress-b}/` (chowned back). Builds: `$HOME/the-one-m32-build/f2/packages/*0.11.9~dev{7,8}*`.
- **Notes.** A takeover started while a third launch races is not serialised (documented). `AppRun`/frozen entry must still pass `quit` (and `--wait`) through (leg 7).

### vm-relaunch-probe

**Status**: landed (leg 6). Verification only, no product code changed. Evidence: `$HOME/the-one-m32-evidence/f2/leg6/{ubuntu,debian}/` (numbered screendumps `<row>-<step>.png`, SSH and API reads, `doctor` output), `r10-hygiene.txt`, `SHA256SUMS`, build logs. Result: **one divert, `[BLOCKED:divert-appcenter-upgrade]`** (R6/R7 on Ubuntu); every other row passes on both guests; no product defect found.

- **Packages (built from the committed tree, `build.sh --version`, `M32_BUILD=$HOME/the-one-m32-build/f2`).** N `0.11.9.dev10`: AppImage `5256e2fc…a74ca`, `.deb` `0.11.9~dev10` `a69cec5e…a792a69` (full values in `SHA256SUMS`). N+1 `0.11.9.dev11`: AppImage `b77251d6…1d1c`, `.deb` `0.11.9~dev11` `d1732f00…3f90d9`. Staged from the working tree; at build time `packaging/linux/checks/*`, `tests/test_packaging_score.py` and an untracked `.github/workflows/linux-packages.yml` were modified by another leg in the same worktree (none of it is product code or enters the packages).
- **Apparatus notes (for later legs).** (1) `ssh`-launched helpers need the session's `XDG_DATA_DIRS` (a Files started without it says "no app for Debian package"): the probe read it from `gnome-shell`'s environ. (2) The guest has no `curl`; API reads used `python3` with the `loc_` credential (only the `loc_` prefix was ever printed). (3) A logout lands on the GDM user list (autologin does not repeat), so the relogin is click user + `m32testpw`. (4) The Debian welcome dialog can appear late on a fresh overlay; press Esc twice again before the first click. (5) Debian's overview search showed "Searching..." forever after a relogin, so the app grid page and `Gio.AppInfo.get_all()` were used instead. (6) The `.deb` is opened by double-click in Files (the default handler needs the session env), never `gio open` from SSH. Launches that matter were all real grid launches (Super, type, Enter), so they carried GNOME's `XDG_ACTIVATION_TOKEN`.

**Answer table**

| row | Ubuntu 26.04.1 (App Center, tray `indicator`) | Debian 13 (GNOME Software 48.3, tray `none`) |
|---|---|---|
| R1 install + first launch | App Center: Install, third-party confirm, polkit; `dpkg` 0.11.9~dev10. **First grid launch shows the window** ("Hello."), `visible:true mapped:true tray:indicator` (`r1-window-state.txt`). The page now shows the metainfo summary text, but still the generic icon and "Unknown publisher" | GNOME Software: Install, polkit (no "Preparing" stall this time); name and robot icon from the first page. **First grid launch shows the window**, `visible:true mapped:true tray:none` |
| R2 menu entry | Overview result and dock show the robot icon and "GleepGlorp AI"; dock right-click has "Quit GleepGlorp AI" (`r2-dock-rightclick.png`) | Overview result has the icon and name; right-click has "Quit GleepGlorp AI" (`r2-02-rightclick.png`) |
| R3 close | Title-bar close via QMP: `visible:false`, process and `/api/live` up, tray icon in the top bar; the tray menu (Show, Quit) **Show restores the window in front** (`r3-after-show.png`) | Close: `visible:false`, `/api/live` 200; the no-tray notification is on screen in the first dump after the click ("GleepGlorp AI is still running. Open it again to bring it back, or right-click…", `r3-notice-0.png`); the marker `.no_tray_notice_shown` is written; a **second close shows no notification** (`r3-second-close-0/1.png`) |
| R4 relaunch while hidden (divert criterion) | **Pass.** A grid launch while hidden: same pid answers, window shown and in front of App Center, title bar active, no "is ready" notice (`r4-01`, `r4-03`). The launcher's `/proc/<pid>/environ` held `XDG_ACTIVATION_TOKEN=gnome-…` and `DESKTOP_STARTUP_ID=gnome-…` (`r4-token-watch.txt`). The app's `focus_window: activation token` line is INFO and does not reach the journal (uvicorn logs only), so whether the GTK token path or the plain path raised it is not separately proven; the observable result is the same | **Pass.** Same: same pid, window shown, in front, active title bar (`r4-01-after-relaunch.png`), token in the launcher's environ (`r4-token-watch.txt`) |
| R5 quit | Tray Quit: process gone and `/api/live` refused at the first poll (1 s). After a grid relaunch (data intact), dock right-click "Quit GleepGlorp AI": gone within 2 s | Right-click "Quit GleepGlorp AI" from the overview result: gone within 2 s, `/api/live` refused (`r5-quit.txt`) |
| R6 upgrade while running | **App Center cannot install N+1 over N even with metainfo.** Double-clicking dev11 into a running App Center ends in "Something went wrong" (Retry does not help); a fresh App Center shows version 0.11.9~dev11 with a disabled grey "Installed", as with Flight 1 (`r6-03/04/06`). **`[BLOCKED:divert-appcenter-upgrade]`.** Takeover done by the closest path: `apt-get install ./dev11.deb` over SSH (not a GUI install) with N hidden in the tray, then a real grid launch: the new process answered `mode:booting` then `window` v0.11.9.dev11 within 6 s, the old pid gone, window shown; agent, provider (key set) and chat all survived (`r6-takeover-poll.txt`, `r6-after-takeover-check.txt`) | **GUI works.** N hidden (no tray), double-click dev11: GNOME Software offers **"Install"** (not "Update"), polkit, `dpkg` 0.11.9~dev11; the old process kept running (no restart prompt, as in leg 4); a real grid launch then took over: new pid, `version 0.11.9.dev11`, window shown within 3 s, old gone, and the agent, provider and chat survived (`r6-takeover-poll.txt`, `r6-after-takeover-check.txt`) |
| R7 remove | **Not listed.** `appstreamcli search gleepglorp` now finds `ai.gleepglorp.GleepGlorpAI`, but App Center's Installed apps search (gleep), Explore search with Snap and with Debian filters, all empty; the `.deb` page only shows a disabled "Installed", so no GUI route to Remove. Removal through `apt-get remove` (terminal): data dir (`api-credential`, db) survives (`r7-remove-ubuntu.txt`) | **Not listed** in Installed (scrolled F to I: no entry), in search (also with a freshly started Software), nor via the overview's App Details ("no details for that application"), even though `appstreamcli` finds the component. Removal from the `.deb` page (trash, "App data and settings will be kept", polkit) works; data dir survives; a running process outlived the removal (`r7-remove-debian.txt`) |
| R8 AppImage (fresh overlay) | Exec bit through Properties then double-click: **own window** at once (`visible:true`, tray indicator, `/tmp/.mount_Gleep…/the-one app`); the grid entry "GleepGlorp AI (AppImage)" with the icon **appears at once** (written at first run: `~/.local/share/applications/gleepglorp-ai-appimage.desktop`, `…/icons/hicolor/512x512/apps/gleepglorp-ai-appimage.png`); dock right-click "Quit GleepGlorp AI" exits it in 2 s; after deleting the file and a logout and login the entry is gone from the overview (`TryExec`); the stale `.desktop` file stays on disk | Same steps: **own window, no Firefox** (leg 4's finding is fixed), `tray:none`; entry "GleepGlorp AI (A…" with the icon at once; its right-click Quit exits in 2 s; after deleting the file and a relogin the entry is gone from the app grid and from `Gio.AppInfo.get_all()` |
| R9 `doctor` | `.deb` and AppImage: exit 0, `RESULT: PASS`, only "skipped" is window chrome, `sandbox: bubblewrap`, `tray: indicator — StatusNotifier host registered` | `.deb` and AppImage: exit 0, PASS, only "skipped" is window chrome, `sandbox: bubblewrap`, `tray: none — no StatusNotifier watcher on the session bus` |
| R10 hygiene | see below | see below |

- **R10.** `base-hash --check` OK for both bases and both `vars.fd` at the end. Only `m32-vm-ubuntu`/`m32-vm-debian` (and `m32-build-*` for the two builds) were used, as the invoking uid; `docker ps -a --filter name=m32` is empty. No root-owned files in `$M32_VM`, `$M32_BUILD/f2` or `…/evidence/f2/leg6` (older root-owned files exist in `…/evidence/f2/leg3/` and `…/evidence/A/` from earlier container runs, not this leg). Nothing listening on host 8484/8485 or 2290-2299 at the end; the operator data dir's newest mtime is unchanged (1791383047). `free -g` available was 11-12 GB before every `up`. Nothing installed on the host.
- **Findings for the Flight Director.** (1) **Ubuntu App Center upgrade/remove stays unusable** with metainfo present: the operator decision is between documenting `sudo apt install ./gleepglorp-ai_X.deb` (and `sudo apt remove gleepglorp-ai`) for Ubuntu, and anything else; the in-app takeover itself works once the new package is on disk. (2) Neither software centre lists the package under Installed or in search despite a valid metainfo found by `appstreamcli`; Debian's `.deb` page (Install/Remove) and its upgrade work. (3) The GNOME `XDG_ACTIVATION_TOKEN` reaches the second launch; raising works on both guests. (4) The no-tray notice text is longer than the banner shows (it is cut with "…" on screen). (5) Ubuntu's App Center page now shows the metainfo summary but not the icon or a publisher.

### linux-recipe

**Status**: landed (leg 7). Evidence: `$HOME/the-one-m32-evidence/f2/leg7/` (`check-appimage.log`, `check-deb.log`, `linux/...`, `SHA256SUMS`). Packages (0.11.8 and 0.11.9.dev1/`~dev1`) in `$HOME/the-one-m32-build/f2/packages/`, staged from the working tree.

- **Metadata:** `packaging/product.toml`, `packaging/render.py` (`load(repo, overrides)`, `render`, `--json`, `--set`), `LICENSE` (MIT), one `license = "MIT"` line in `pyproject.toml` (`uv lock --check` passes). AppStream id `ai.gleepglorp.GleepGlorpAI`, license MIT, homepage per operator. Reserved (runtime) placeholders left by the renderer: `APPIMAGE_EXEC`, `APPIMAGE_PATH`, `ICON_PATH`, `INSTALLED_SIZE`.
- **Templates (packaging/linux):** `AppRun.in` (replaces `AppRun`), `deb.desktop.in` (renamed from `gleepglorp-ai.desktop.in` so `build*.sh` hold no product name; the leg listed the old name), `appimage.desktop.in`, `control.in`, `metainfo.xml.in`, `build.env.in`. `build.sh [--version X] [--no-excludes]`, positional form kept with the warning, both together is an error; renders into `$STAGE/rendered/`; `build-inner.sh` takes no version argument any more (reads `build.env`). Only `packaging/` plus `LICENSE`, `pyproject.toml` (one line), `tests/test_packaging_{metadata,apprun}.py` changed; `stage.py` untouched.
- **Metainfo finding (for leg 8, leg 11):** `appimagetool` 1.9.1 only looks for `usr/share/metainfo/<desktop-id>.appdata.xml` and then validates it WITH the network (url-not-reachable warning) and demands the file name match nothing AppStream accepts (`metainfo-filename-cid-mismatch`, `desktop-file-not-found`), failing the build. So the file ships as `<metainfo_id>.metainfo.xml` in the AppDir and the `.deb` (found by software centres), appimagetool says "metadata missing" (a warning), and the build validates it itself with `appstreamcli validate --no-net` (exit 0, "pedantic: 1" only). `--no-appstream` was not needed.
- **Validation:** `desktop-file-validate` OK on the `.deb` entry, the AppDir root entry and the integration template filled with sample values; both entries have `StartupNotify=true` and the `quit` action "Quit GleepGlorp AI" (`the-one quit`, `AppRun quit`). The `.deb` contains `usr/share/metainfo/ai.gleepglorp.GleepGlorpAI.metainfo.xml`. `control` has no spike wording; it gained `Homepage`.
- **AC5 negative:** with `pyproject.toml` version set to 0.11.7 `test_pyproject_version_matches_dunder_version` failed; reverted.
- **AC6 ran:** `appimage/debian-13-baseline: G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=PASS single=PASS`; `deb/ubuntu-26.04-baseline`: same PASS line (N=0.11.8, N+1=0.11.9.dev1). Note the window runs now exercise AppRun self-integration inside the container (writes under the test user's XDG data dir).
- **Gates:** `make test-unit` 6951 passed, 12 skipped; ruff check/format clean over `the_one/ tests/ scripts/ evals/ packaging/`; shellcheck clean on `build.sh`, `build-inner.sh` and the rendered `AppRun` (`-s sh`). Packaging tests: 38 pass. Containers: only `m32-vm-ubuntu` (leg 4) is running.
- **For leg 8:** `M32_DEBUG_ENV`/`M32_FORCE_FALLBACK`/`M32_ABI_PROBE` not renamed. `AppRun` requires `APPDIR`/`APPIMAGE` (set by the AppImage runtime) for integration. A host with `desktop-file-validate`/`appstreamcli` can render and validate the templates with `render.py` alone. For leg 11: the integration entry is `$XDG_DATA_HOME/applications/gleepglorp-ai-appimage.desktop`; uninstall = AppImage file plus that and the icon `icons/hicolor/512x512/apps/gleepglorp-ai-appimage.png`.

### packaging-checks-and-audit

**Status**: landed (leg 8, uncommitted). Evidence: `$HOME/the-one-m32-evidence/f2/leg8/` (`build.log`, `ac3-break.log`, `gates-*.txt`, `ac4-debug.txt`, `linux/...`, `smoke/`). Build: `0.11.9.dev6` in `$HOME/the-one-m32-build/f2/packages/` (scratch).

- **Moves** (`git mv` for tracked, plain `mv` for untracked): tracked and `git mv`'d: `spike/stage.py` to `packaging/stage.py`; `check.sh`/`inner.sh` to `linux/checks/gates.sh`/`gates-inner.sh`; `score.py`, `xwd2png.py`, `images/`, `README.md` to `linux/checks/`; `macos-checks.sh` to `packaging/macos/checks.sh`. Untracked, plain `mv`: `gtk-smoke.sh`, `gtk-smoke-inner.sh` to `linux/checks/` (leg 5 phase A's none-mode checks kept). `packaging/spike/` is gone. `git log --follow` shows nothing yet: the renames are staged and uncommitted, history follows after the commit. `linux/checks/check.sh` is a one-line forwarding shim (leg 9 deletes it).
- **`stage.py`**: `--target` (with `--candidate` kept as an alias), `REPO` is `parents[1]`, no "spike" wording. Callers updated (`linux/build.sh`, `macos/build.sh`, both spec docstrings).
- **Display** (`gates.sh --display wslg|xvfb`, default wslg when `/mnt/wslg/.X11-unix/X0` exists): xvfb starts `Xvfb :99 -screen 0 1920x1080x24` as the test user inside the container; `gates-inner.sh` uses `$XDISP` (`:0` or `:99`) for the window phase and the probe. `macos/checks.sh` now imports `score` from `../linux/checks`.
- **Audit** (`packaging/linux/audit.py`, stdlib, run by `build-inner.sh` after the freeze, skipped for `--no-excludes`): excludes.txt basename match, any `*.typelib`, any ELF needing GLIBC above 2.39 (`readelf -V`), bundle dir only. Real build line: `audit: 1025 files, max GLIBC_2.34 (limit 2.39), 0 problem(s): PASS`.
- **AC3**: in a scratch copy (own `git init`, deleted after) the spec's two `if not _NO_EXCLUDES:` blocks were turned into `if False:`; `build.sh --version 0.11.9.dev7` exited 1 with `AUDIT FAIL: excluded library present: _internal/libglib-2.0.so.0 (matches libglib-2.0.so*)` and 11 more lines, `audit: 1037 files, ... 12 problem(s): FAIL` (`ac3-break.log`). Reverted by deleting the copy; the real tree was untouched.
- **Rename**: `THE_ONE_PKG_DEBUG`, `THE_ONE_PKG_FORCE_FALLBACK`, `THE_ONE_PKG_ABI_PROBE` in the hook, gates, scorer and READMEs; zero `M32_DEBUG_ENV|M32_FORCE_FALLBACK|M32_ABI_PROBE` left in `packaging/` and `tests/`. Build-time `M32_*` variables unchanged (documented in `checks/README.md`). AC4: the extracted dev6 AppImage with `THE_ONE_PKG_DEBUG=1 AppRun version` prints the two `[rthook_host_gtk]` lines (`ac4-debug.txt`).
- **AC2** (leg 7 pair re-run through the new paths, one container at a time): `deb/ubuntu-26.04-baseline` and `appimage/debian-13-baseline` both `G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=PASS single=PASS`; `deb/debian-13-bare --display xvfb`: `G3=N/A ... single=N/A`, rest PASS. Extra: `deb/ubuntu-26.04-baseline --display xvfb` (through the `check.sh` shim) all PASS with the window mapped on the private Xvfb, which is the hosted-runner path. `gtk-smoke.sh ubuntu-26.04 --deb ...0.11.9~dev6...`: `OVERALL PASS` (all step1-step5 lines, including the none-mode hide, relaunch, `the-one quit`, and the quit route). Root-owned evidence files from the containers were chowned back with an `m32-gtk-smoke-chown` container.
- **Tests** (new): `tests/test_packaging_{stage,audit,score,macos_entry}.py` (loaded by path). The macOS `-psn_*` handling was trivial, so it is extracted as `launch_args()` in `packaging/macos/frozen_entry_mac.py` (behaviour identical) and tested. The `test_packaging_metadata.py:24` E501 no longer fires (ruff clean on the whole tree). `tests/test_packaging_*.py` 82 pass.
- **AC6**: `bash -n` and shellcheck 0.10.0 clean on `packaging/macos/{build.sh,checks.sh}`; every non-variable path in `macos/build.sh` exists; actionlint 1.7.7 clean on `packaging-probe-macos.yml` (unchanged). No new shellcheck disables.
- **AC7**: ruff check and format clean on `the_one/ tests/ scripts/ evals/ packaging/`; shellcheck clean on all `linux/checks/*.sh`, `build.sh`, `build-inner.sh`; no `m32-` container left; no 8484/8485; operator data dir untouched.

### hosted-build-prepare

**Status**: landed (leg 9, uncommitted). Evidence: `$HOME/the-one-m32-evidence/f2/leg9/` (`rehearsal-*.log`, `rehearse.py`, `docker-run-args.txt`, `.github-stub/linux-packages.yml`, per-cell `evidence-*`). Scratch version `0.11.9.dev12`, `RUNNER_TEMP=$HOME/the-one-m32-build/f2/runner-rehearsal*`.

- **Workflow** `.github/workflows/linux-packages.yml`: `workflow_dispatch` + `workflow_call` (input `version`), `contents: read`, concurrency `linux-packages` (no cancel), no `secrets.`. Jobs `build` (45 min), `checks` (30 min; 2 distros x 2 formats, `fail-fast: false`, `max-parallel: 4`; bare image built with one bounded retry; `gates.sh A <fmt> <distro> bare --n V --display xvfb`; last step fails on a missing `score.json`, any `=FAIL`, or G1p/G1u/G2/G4 not PASS), `summary` (`if: always()`, fails unless 4 score lines and build/checks succeeded). Every job and step has a timeout; packages retained 3 days, logs and evidence 7. Version output flows from `build` to `checks`.
- **gates.sh single-version mode:** `--n1` optional; `SINGLE_VERSION=1` makes `gates-inner.sh` skip the N+1 install/serve/readback, `score.py` reports `upgrade=N/A`. Three new tests in `tests/test_packaging_score.py` (22 pass at first landing; 25 after the review fix below). `check.sh` deleted (`git grep` outside missions: nothing), README updated.
- **Rehearsal by execution:** `rehearse.py` extracts each step's exact `run:` text from the workflow and runs it with `bash -euo pipefail` in a fresh env with `RUNNER_TEMP`, `GITHUB_ENV`, `GITHUB_OUTPUT`, `GITHUB_STEP_SUMMARY` on scratch files (checkout/setup-python/uv-install/upload/download steps are `uses:` or host-provided and skipped; host `uv` is 0.10.0). Build job: both packages, `audit: 1025 files, max GLIBC_2.34 (limit 2.39), 0 problem(s): PASS`, SUMMARY.txt rendered (52 s locally, layers cached; a runner has no cache, so the build image compiles PyGObject and pycairo, budget 10-12 min). Cells: `deb/debian-13-bare` and `appimage/ubuntu-26.04-bare` `G1p=PASS G1u=PASS G2=PASS G3=N/A G4=PASS upgrade=N/A single=N/A`. With a `docker` shim logging the `run` args: `DISPLAY_MODE=xvfb`, no `/mnt/wslg` mount, no `--privileged`/`--network`. Fail step: passes the PASS line; fails (exit 1) on a doctored `G2=FAIL` and on a missing `score.json`. Summary job: 4 lines render, exit 0; with one cell missing and checks=failure it prints "expected 4 score lines, found 3" and exits 1.
- **Defects the rehearsal found (the point of the leg):** (1) `gates.sh` built the `.deb` file name for N as `gleepglorp-ai_0.11.9.dev12_amd64.deb` (only N+1 mapped `.dev` to `~dev`), so a single-version `.deb` cell could not find its package: all gates FAIL, caught by the fail step (`rehearsal-checks-deb-debian-13-FIRST-FAILED.log`); fixed, pinned by a test. (2) actionlint's shellcheck found `n` incremented inside a `{ ...; } | tee` subshell in the summary job, which would have made the "4 score lines" check always fail; the lines are now collected before the piped write. (3) `uv` on the runner: `pip install` on ubuntu-24.04 is PEP 668 externally managed, so the job uses `actions/setup-python@v6` (3.11) as the macOS probe does.
- **Stub for main:** `$HOME/the-one-m32-evidence/f2/leg9/.github-stub/linux-packages.yml` (same name, byte-identical `on:` block per `diff`, `permissions: contents: read`, one echo job; actionlint clean). The Flight Director opens the `.github/`-only PR with it. Nothing pushed, no workflow dispatched.
- **Runner facts and budget (not measured on a runner; no dispatch):** runner is `ubuntu-24.04` (Docker preinstalled; the build step's `df -h` and `docker version` are in the runner-evidence log of the first dispatch to confirm the ~14 GB free). Repo is private; Linux minutes bill 1x; `gh` does not expose the plan, so the included-minutes figure is for the Flight Director to read from the billing page. Estimated billed minutes per run: build ~12 + four cells x ~6 (image 1-2, gates 2-4) = about 36 (wall about 20, cells parallel). Cap: 6 dispatches, about 220 minutes. Artifact storage: 5 existing artifacts, 126 MB total; cache usage 0; one run adds about 290 MB of packages (3 days) plus small logs/evidence (7 days), so room is not a concern.
- **Review fixes (G3 on the .deb cells, shell, residual risk):**
  - `gates.sh` now sets `WINDOW=1` for `--format deb` on a `bare` image under `--display xvfb` (DD10: the .deb's Depends pull in WebKitGTK); `appimage`+`bare` and `bare`+`wslg` keep `WINDOW=0`. It passes `--window` to `score.py`, which scores G3 and single-instance for any windowed run (baseline or `--window`). The workflow's fail step now also requires `G3=PASS` and `single=PASS` on the deb cells (`G3=N/A` stays accepted for the AppImage cells). Three new tests (25 pass in `tests/test_packaging_score.py`).
  - Re-rehearsal, `deb/debian-13-bare`, `--display xvfb`, package `gleepglorp-ai_0.11.9~dev12_amd64.deb` read only (4 min 8 s): `G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=N/A single=PASS`. Evidence `$HOME/the-one-m32-evidence/f2/leg9/rehearsal2/`.
  - Workflow: `defaults: run: shell: bash` (GitHub's explicit `bash --noprofile --norc -eo pipefail {0}`) so the `| tee` steps fail on a failing left side; `on:` block unchanged (diff against the stub still empty); actionlint clean; shellcheck clean.
- **Residual risk (leg 9):** only 2 of the 4 matrix cells were rehearsed locally (`deb/debian-13` and `appimage/ubuntu-26.04`); `deb/ubuntu-26.04` and `appimage/debian-13` never ran. The runner's disk and Docker facts (~14 GB free, Docker version) are unmeasured until the first dispatch's Runner evidence step.
- **Gates:** `make test-unit` 7055 passed, 12 skipped; ruff check and format clean over `the_one/ tests/ scripts/ evals/ packaging/`; actionlint 1.7.7 clean (workflow and stub); shellcheck 0.10.0 clean on `packaging/linux/checks/*.sh`, `build.sh`. Root-owned container output chowned back with `m32-leg9-chown`; only `m32-vm-ubuntu` (leg 6) is running; 8484/8485 and the operator data dir untouched.

### hosted-build-run

**Status**: landed (leg 10, uncommitted). Evidence: `$HOME/the-one-m32-evidence/f2/leg10/hosted/` (gates), `$HOME/the-one-m32-build/f2/leg10/{hosted,local,x}` (artifacts, local build, extractions and file lists).

- **AC1/AC2 (Flight Director, as given):** run `40127933969` green on `2fdfaa3`; four score lines PASS, deb cells G3 and single PASS; 471 s wall. Runner Ubuntu 24.04.5, Docker 28.0.4, 13 GB free disk (of 72 GB), 2 CPUs, 7 GB RAM, uv 0.10.0.
- **AC3 (hosted vs local, same commit 2fdfaa3, version 0.11.8, same build image `m32/linux-build:f2` sha256 `d1c7b822...`):** `git status --porcelain -- the_one packaging` empty. Local build in a separate root (`M32_BUILD=.../leg10/local`), 8 min.
  - File lists: hosted and local `.deb` (1231 entries) and AppImage (1243 entries) are identical, no added or missing path.
  - Content: sha256 of every file (1028 regular files in the deb tree) is identical except one per package: `base_library.zip` (`/opt/gleepglorp-ai/_internal/` and `/usr/lib/gleepglorp-ai/_internal/`). Same size (1444808), same 155 members and member sizes; the difference is zip entry timestamps/compile mtimes from the build time (15:03 vs 15:11).
  - Package files differ in sha256 and size by a few hundred bytes (deb 141378894 vs 141379242; AppImage 144308728 vs 144304632), consequence of the above plus archive timestamps and ownership (hosted 1001, local `ubuntu`). Control files identical (`dpkg-deb -I` differs only in the size line).
  - Audit line identical: `audit: 1025 files, max GLIBC_2.34 (limit 2.39), 0 problem(s): PASS`.
  - Build logs diff (minus hosted-only stage/render lines and the output path) is empty: same Python 3.11.14, PyInstaller 6.22.3, same fallback library versions (libgirepository-2.0-0 and libglib2.0-0t64 2.80.0-6ubuntu3.10, ayatana-appindicator 0.5.93-1build3, ayatana-ido 0.10.1-1build2, ayatana-indicator 0.9.4-1build1, dbusmenu 18.10.20180917~bzr492+repack1-3.1ubuntu5), same NEEDED walks, same sha256 for all six fallback `.so` files and the typelib. Not bit-reproducible only by zip timestamps; library set unchanged. No divert criterion.
- **AC4 (baseline images, `--display wslg`, single-version, `--pkgdir` the hosted download, one container at a time, 41 s for the first):**
  - `deb/ubuntu-26.04-baseline`: `G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=N/A single=PASS`
  - `appimage/debian-13-baseline`: `G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=N/A single=PASS`
- Housekeeping: root-owned container output chowned back (`m32-leg10-chown`); no `m32-` container left; leg 6's VMs untouched; 8484/8485 and operator data dir untouched; no commit, push or dispatch.

### fresh-vm-checks (part A)

**Status**: part A (documentation) written, uncommitted; part B (behavior test on the four variants) is the Flight Director's.

- **New:** `docs/linux-install.md` (modelled on `docs/windows-install.md`: which download, install, first launch and the three close states, quitting, WebKitGTK missing, window size/position (X11 only), upgrade, remove, data, both installed, `doctor` with the `sandbox:`/`tray:` lines, troubleshooting). The no-tray notice is described, not quoted (leg 11 owns the wording). The `apt` lines, the AppImage clean-up paths and `the-one quit [--wait]` are the ones the behavior test exercises (AC4's cross-check against the run log is still to do after part B).
- **Edited, additively:** `README.md` (Linux paragraph in "Install"; source-install steps kept, marked source-only), `CLAUDE.md` (a "Linux packaging (M32 F2)" paragraph after "Windows packaging (M15 F5)", which also carries the window routes and `the-one quit` sentence, since the Desktop launcher paragraph did not name them), `the_one/agents.md` (a "Linux packaging (M32 F2)" section before "Time zones (M28)").
- **Checks:** `ruff check the_one/ tests/ scripts/ evals/ packaging/` clean. `make test-unit`: 7058 passed, 12 skipped. No source, template or packaging file touched.


### fresh-vm-checks (part B: behavior test)
**Status**: completed. 2026-10-24, the Flight Director running `/mission-control:behavior-test linux-package-install`.

- **Run log:** `tests/behavior/linux-package-install/runs/2026-10-24-20-34-28.md`. **44 of 44 checkpoints PASS** across ubuntu-deb, ubuntu-appimage, debian-deb and debian-appimage, in live mode with grouped checkpoints. Packages `0.11.9.dev20`/`dev21` were built from `3186f4a`. The base hashes were unchanged, and no `m32-*` container was left.
- **AC3 (leg 11's App Center outcome):** Ubuntu's App Center still shows a generic icon and "Unknown publisher" for a local `.deb`. This is an App Center limit, recorded and not chased. Debian's GNOME Software shows the brand icon after install.
- **AC4, guide cross-check:** the run used exactly the guide's commands and paths:
  - `sudo apt install ./…deb` and `sudo apt remove gleepglorp-ai` (`docs/linux-install.md:108,130`);
  - the AppImage clean-up files `gleepglorp-ai-appimage.desktop` and `…/512x512/apps/gleepglorp-ai-appimage.png` (`:119-120`), which remained after deletion and were hidden by `TryExec`, as documented.

  `the-one quit` is not in the behavior test; leg 5's smoke test covers it.
- **Findings for alignment and follow-up (not failures):**
  1. **Ubuntu's tray-mode notice is truncated** in GNOME's banner ("…Quit from the tray m…"). Leg 11 shortened only the no-tray notice; the tray notice wants the same treatment.
  2. AppImage tile labels are truncated by GNOME's grid ("GleepGlor…" on Ubuntu, "GleepGlorp AI (A…" on Debian).
  3. On the first launch of the Ubuntu AppImage, the window body was empty for about 20 s (first mount); Debian rendered by +5 s.
  4. A green "1" badge appeared on the Ubuntu `.deb` tile while the old instance was hidden.
  5. Debian's window has a close-only title bar.
  6. Spec improvements the Validator suggested: a window-geometry observable, timed notification captures, the apparatus facts (passwordless sudo, no GDM autologin after logout), the AppImage runtime-parent rule, and "hidden from the menu" wording.

### Flight review fixes

- Pid answers (takeover and `the-one quit --wait`) must be a positive int (bool and non-positive rejected as an invalid answer).
- A repeat `POST /api/window/quit` while a quit is under way reports `window` without destroying again.
- `_pid_alive` declares ctypes argtypes/restype for OpenProcess, WaitForSingleObject and CloseHandle.
- `activation_token` is printable ASCII without whitespace (max 256).
- SECURITY-MODEL.md states the window routes share the existing posture (admitted localhost origin with a session cookie).
- Flight log: gtk-window-fixes moved under Leg Progress; leg sections ordered by leg number.

### notice-and-metainfo-polish

Leg 11, landed (not committed).

- **Notice (AC1):** `shell.py` now sends summary `_NO_TRAY_NOTICE_SUMMARY` = "GleepGlorp AI is still running" and body "Open it again to show it, or right-click its icon to quit." (57 characters). This supersedes the single-string wording in flight DD4 (DD4 text left as written). `test_none_mode_close_hides_and_notices_once` pins both strings and the 60-character bound.
- **Icons and metainfo (AC2):** `metainfo.xml.in` gains `<icon type="stock">@DESKTOP_ID@</icon>`. `build-inner.sh` resizes 64/128/256 px from the 512 px source with Pillow (new `== icons` step, `install_icons` helper) into both the AppDir and the deb root. Deviation found while building: once an icon is declared, `appstreamcli validate` fails with `app-categories-missing`, so the template also gains `<categories><category>@APPSTREAM_CATEGORY@</category></categories>`, derived in `render.py` `load()` from the single `product.toml` `categories` value (exactly one entry required, else it fails loudly). After that, validate exits 0 (one pre-existing pedantic note).
- **Verification (AC3):** scratch build 0.11.9.dev14: `dpkg-deb -c` and the extracted AppImage both list 64, 128, 256 and 512 px icons; audit PASS (1025 files, max GLIBC_2.34); desktop-file-validate OK; `make test-unit` 7058 passed, 12 skipped; ruff check and format clean; shellcheck clean on `build-inner.sh`. No m32-* containers left.
- **AC4:** App Center icon and publisher are checked in leg 12's VM run, not here.

### linux-hat

- **Tray notice (inline HAT fix, leg 13):** the close-to-tray notice was truncated in GNOME's banner. `shell.py` now sends title `_TRAY_NOTICE_TITLE` = "GleepGlorp AI is still running" and body `_TRAY_NOTICE_BODY` = "It's in the tray. Click its icon to show it or quit." (52 characters), replacing the single long string. Same code path as the Windows balloon (accepted). Pinned in `tests/test_desktop_tray.py`; once-only marker unchanged.
- `docs/windows-install.md` (first-close notice quote) updated to the new title and body; historical mission and flight docs left as written.

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
