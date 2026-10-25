# Flight: Linux packages

**Status**: completed
**Mission**: [GleepGlorp AI installs like an app on Windows, macOS and Linux](../../mission.md)

## Contributing to Criteria
- [ ] **Linux install, no setup.**
  - Both packages install on a stock Ubuntu 26.04 and a stock Debian 13 GNOME desktop, with no terminal and no manual system-package step.
  - Each appears in the application menu with the brand icon, and opens in its own window.
  - Where WebKitGTK is missing, the app says so plainly and opens in the browser.
  - *(Behavior-test-backed: `linux-package-install`, run in fresh VMs.)*
- [ ] **The frozen runtime works in every build** (Linux half). Strict `doctor` passes inside both Linux packages on both distros, built in the release build environment, and shows the sandbox fallback instead of hiding it.
- [ ] **The window behaves like a native app on each platform** (Linux half).
  - With a tray: closing hides to the tray, and Quit exits.
  - With no tray:
    - closing keeps the app running hidden;
    - launching it again brings it back;
    - the launcher's "Quit GleepGlorp AI" action exits.
  - A second launch focuses the running window, and a newer version replaces an older running one.
  - Size is remembered; position is remembered on X11 only (DD7).
- [ ] **Upgrades keep the user's data** (Linux half).
  - Installing N+1 over N keeps chats, agents, providers, secrets and the local-API credential, including while N is still running.
  - Uninstalling removes the app and leaves the data.
  - The guide says where the data lives and how to remove it.
- [ ] **One packaging source of truth, built within the CI budget** (the source, and Linux's use of it).
  - Name, package name, identifiers and icon are defined once; Linux reads them.
  - Linux builds on a hosted runner only on a manual run. The tag trigger is Flight 4's.
  - The version's last duplicate (`pyproject.toml`) is pinned by a test now and removed after Mission 31 merges (DD6).
- [ ] **Install guides for every platform** (Linux): `docs/linux-install.md` and README "Install" for packaged Linux. The manual WebKitGTK `apt` step stays, for source installs only.
- [ ] **Existing gates pass.** Unit, browser and lint. Packaging code stays out of `the_one/` imports.

---

## Pre-Flight

### Objective
Turn Flight 1's Linux prototype into the two shipped Linux packages:
- **The AppImage** stops depending on two libraries that stock desktops lack. It carries the AppIndicator and girepository libraries as a host-first fallback, and still uses the desktop's own WebKitGTK.
- **The app on a Linux desktop** behaves as the mission asks:
  - its close and show paths work under GTK (two latent pywebview traps are fixed);
  - a missing tray library degrades instead of failing;
  - a desktop with no tray keeps the app running hidden, and the launcher can quit it;
  - a newer launch replaces an older running instance;
  - a missing WebKitGTK is announced, not silent;
  - `doctor` says how tools are sandboxed and what tray it found.
- **The build:**
  - reads one product-metadata source;
  - runs in one pinned build container, the same locally and on GitHub;
  - is proven on a dispatch-only hosted run;
  - is verified on fresh Ubuntu 26.04 and Debian 13 GNOME desktops in disposable VMs.
- **It ends** with the Linux install guide and a short guided walk where the operator looks at both desktops.

### Open Questions
- [x] One flight or two? → one, risk first (operator, 2026-10-24); leg 1 is the divert point.
- [x] The AppImage's missing libraries → DD1 (operator: "bundle the two libs").
- [x] Where does the build run? → DD2
- [x] Tray backend and "is there a tray" → DD3
- [x] Quit with no tray → DD4 (operator: launcher action, a one-time notice; named "Quit GleepGlorp AI")
- [x] Menu entry for an AppImage → DD5 (operator: it adds itself on launch)
- [x] One metadata source → DD6
- [x] Window position on Wayland → DD7
- [x] `packaging/spike/` → DD8
- [x] Verification apparatus → DD9 (operator: fresh VMs in a container; Ubuntu guest from the desktop ISO's autoinstall)
- [x] Outward steps and the walk → DD10 (operator: a `.github/`-only PR; a closing walk)
- [x] What `doctor` shows → DD11
- [x] Close and show under GTK (design review cycle 1 findings 1 and 2; cycle 2 corrected the geometry fix) → DD12
- [x] Upgrade while the old version runs → DD13 (operator: the newer one replaces the older)
- [x] WebKitGTK missing → DD14 (operator: a notification plus `doctor`)
- [x] AppImage and `.deb` side by side → DD5, DD13

### Design Decisions

**DD1 — The AppImage carries a host-first fallback for two library sets**:
- **The sets**, taken from the pinned build container (DD2):
  - `libgirepository-2.0.so.0`;
  - the Ayatana AppIndicator stack (`libayatana-appindicator3.so.1` and its private dependencies, measured in leg 1: expected `libayatana-indicator3`, `libayatana-ido3-0.4`, `libdbusmenu-glib`, `libdbusmenu-gtk3`), plus `AyatanaAppIndicator3-0.1.typelib`.

  GLib, GTK and WebKitGTK still come from the host; the bundle never carries them (Flight 1's excludes).
- **Where it lives:** an AppDir directory outside PyInstaller's `_internal` (for example `usr/lib/gleepglorp-ai-fallback/`), located relative to `sys._MEIPASS`, so `--appimage-extract-and-run` works too. `_internal` must never hold these libraries. `excludes.txt` already drops their families, and the bundle audit (DD2) enforces it. PyInstaller's ctypes shim, and possibly the bootloader's own `LD_LIBRARY_PATH`, look in `_internal` first.
- **Host first, by soname.** A runtime hook checks, before any `gi` import, whether the host loader can resolve each soname. Only when it cannot does the hook load the AppImage copy, by absolute path with `RTLD_GLOBAL`, in dependency order. It appends the fallback typelib directory after the host directories in `GI_TYPELIB_PATH`.
  - This works because glibc matches a later by-name load (from `gi/_gi*.so`'s `NEEDED libgirepository-2.0.so.0`, which has no RPATH, and from the typelib's `shared-library` entry) against the `DT_SONAME` of objects already loaded.
  - The stock `pyi_rth_gi`/`glib`/`gio`/`gtk` hooks only set environment variables, so nothing imports `gi` before ours.
- **Best effort.** Every preload catches `OSError`. A host with no GTK cannot load the Ayatana stack, and that must not break `version`, `doctor` or `quit`.
  - Cost, accepted: on a host lacking Ayatana, the preload maps GTK on every CLI call.
- **Never `LD_LIBRARY_PATH`.** The fallback directory is never on the loader path, so it cannot reach WebKit's helper processes (Flight 1's gate 3 hazard). The `.deb` ships no fallback directory, so the hook is a no-op there, and the `.deb` declares both as dependencies.
- **Gate 3, amended for the AppImage:**
  - exactly one copy of each library in the UI process;
  - `libgirepository-2.0` and the Ayatana libraries come from `/usr/lib` when the host has them, and from the AppImage mount only when it does not;
  - `WebKitWebProcess` maps nothing from the AppImage mount.
- **The ABI premise is unverified, and is leg 1's first job.** girepository is built from GLib's own source tree, so private GLib ABI is the real risk. Leg 1 tests the fallback `libgirepository-2.0` (GLib 2.80) against Debian 13 (2.84) and Ubuntu 26.04 (2.88) by using it, not only by `dlopen`:
  - load the Gtk 3.0 and WebKit2 4.1 typelibs;
  - open the window;
  - create an indicator.

  If that fails, the flight diverts (Adaptation Criteria).
- **A host with no GTK at all** (a bare image): the AppImage cannot open a window. Expected behaviour there is DD14's browser fallback, and `doctor` passes (DD11).
- Rationale: the operator's decision. It keeps "no manual step" without a second GLib.
- Trade-off: the AppImage owns a small library set and its updates.

**DD2 — One pinned build container for every Linux build, local and hosted**:
- **The container:** `ubuntu:24.04`, pinned by digest (`sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac` at planning; leg 1 re-reads and records it).
- **What it installs:**
  - the compile headers (`libgirepository-2.0-dev`, `libcairo2-dev`, `gobject-introspection`, `gcc`);
  - the DD1 fallback packages;
  - a uv-managed CPython 3.11 with the hash-pinned closure (`uv export --no-dev --extra gui --extra all-llms`);
  - the pinned tools (`packaging/linux/README.md`).
- **How it runs:** the same `build.sh` drives it on the dev host and on the runner, running as the invoking uid, with `git config --global safe.directory` set for the bind-mounted repo (`stage.py` runs `git rev-parse`).
- **Why it matches:** the gi hooks see GLib 2.80, as Flight 1 measured, so the exclude list stays valid. glibc 2.39 is the floor, below both targets.
- **A post-freeze bundle audit,** scoped to the PyInstaller bundle directory, fails the build when:
  - any file there matches `excludes.txt`;
  - any typelib is there;
  - any library there needs a glibc symbol newer than 2.39.
- Rationale: debrief recommendation 3, and key learning 5.
- Trade-off: a slower build, and the digest needs a deliberate bump.

**DD3 — The app chooses the tray backend, and decides whether there is a tray at all**:
- **Backend, before `import pystray`.** On Linux, with `PYSTRAY_BACKEND` unset, the app probes through `gi.require_version` inside a `ValueError` guard:
  - `appindicator` when the Ayatana or legacy AppIndicator typelib is present;
  - else `gtk`, only when GDK is on X11;
  - else `xorg`.

  It sets `PYSTRAY_BACKEND` for that import, and an explicit value is respected. This fixes Flight 1's fall-through: `pystray.backend()` catches only `ImportError`, and a missing typelib raises `ValueError`. `doctor`'s desktop-shell probe imports through the same selection. Both packages get `appindicator` in practice (DD1); `gtk` and `xorg` matter for source installs.
- **A tray exists when:**
  - **appindicator:** the session bus has an owner for `org.kde.StatusNotifierWatcher` and its `IsStatusNotifierHostRegistered` is true.
  - **gtk and xorg:** only on an X11 session (no `WAYLAND_DISPLAY`), and when `_NET_SYSTEM_TRAY_S0` has an owner. The query uses `python-xlib` 0.33, already in the closure as pystray's dependency.

  The calls are synchronous GDBus and Xlib calls from `_boot`'s thread, with no main loop needed, and a short timeout.
- **Logged:** an X11 desktop that has only an XEmbed tray and no StatusNotifier host is judged "no tray" under appindicator, although libayatana would fall back to XEmbed. Accepted: it is not a target desktop.
- **Order: the tray decision comes first.** The tray-host check runs before any pystray import. In no-tray mode pystray is never imported: its `_xorg` backend connects to the X display at import time (`display = Xlib.display.Display()` at module level), which on GNOME starts Xwayland on demand, and with no `DISPLAY` raises. `doctor`'s `tray: none` needs no backend import either.
- **No tray means no-tray mode** (DD4). The tray is not started. pystray's appindicator backend on stock Debian starts, raises nothing and is never seen, so starting it there would only hide the problem.
- **A tray start that raises** keeps today's exit-on-close fallback.
- **Out of scope:** Windows is unchanged; macOS is Flight 3's.
- Trade-off: a tray host added after launch is noticed at the next launch.

**DD4 — No-tray mode: closing hides, launching again shows, "Quit GleepGlorp AI" exits**:
- **Three states replace today's two:**
  - **tray:** close hides to the tray, as today;
  - **no tray (DD3):** close hides, with no tray;
  - **tray failed** (a start that raised): close exits, as today's F4 fallback.

  `_close_to_tray`'s `self._icon is None` → `destroy()` branch becomes the "tray failed" state only. `_on_quit` guards `icon is None` instead of relying on the broad `except` around `icon.stop()`.
- **Hide on close.** In no-tray mode, closing hides the window instead of destroying it. Today, close-to-tray is wired only after a successful tray start (`DesktopSession.run` step 5).
- **Show on relaunch.** A relaunch focuses the running window through `POST /api/window/focus`, which must actually map it on GTK (DD12). The second launch forwards its `XDG_ACTIVATION_TOKEN` (or `DESKTOP_STARTUP_ID`) in the focus request, and the shell applies it before presenting, so Wayland's focus-stealing prevention raises the window instead of showing "ready". This is verified in the VMs. `POST /api/window/focus` becomes a plain `def` like the new routes, since it calls `_shown_call` wrappers that can wait up to 20 s. The startup id and `present()` are applied in one GTK idle callback.
- **The notice on the first hide.** One time, through `org.freedesktop.Notifications`: "GleepGlorp AI is still running. Open it again to bring it back, or right-click its icon and choose Quit GleepGlorp AI." It uses its own marker, separate from the tray notice's `.close_to_tray_notice_shown`. It is sent **asynchronously**, never as a blocking D-Bus call. `_on_closing` runs on the GTK main thread, and a synchronous call could stall the close for the D-Bus timeout, against DD12. With no notification service, the hide still happens, and the guide explains.
- **Quit, end to end:**
  1. A new CLI subcommand, `the-one quit`, reads the credential file without creating one (`get_credential()` creates on first use; quit must not). No file means nothing to quit.
  2. It calls the configured port.
  3. That call is a new credential-gated `POST /api/window/quit`, a plain `def` so it runs in the threadpool; pywebview's `destroy`, `show` and geometry calls can block.
  4. The route runs the tray Quit's sequence, `_on_quit`: really-quit flag, stop the tray if any, destroy the window. The server drains through the existing `_graceful_shutdown`.
- **The route covers every state the app can be in:**
  - window registered: `{"quit": true}`;
  - still booting, no window yet: a pending-quit flag. `_boot` checks it before showing, and again at step 6. At step 6, publishing the window and checking the flag happen under one lock, so a quit that lands between the show and the publish is not lost;
  - the browser-fallback branch (no window, `thread.join()` waiting): `server.should_exit = True`;
  - `serve` mode: `{"quit": false}`, nothing stopped.

  Every response carries the process `pid` (DD13 waits on it). `the-one quit` reaches only the configured port: an instance that moved to another port because the configured one was taken (`_select_port` case c) cannot be quit this way, and the guide says so.
- **Both packages' `.desktop` files** gain a desktop action named "Quit GleepGlorp AI" running that command, distinct from GNOME's own "Quit", which only closes windows. The tray's Quit is unchanged.
- **The read path:** a new read-only `GET /api/window/state` (plain `def`) returns `{"desktop": bool, "mode": "window" | "booting" | "browser" | "serve", "visible": bool, "tray": "indicator" | "xembed" | "none" | "failed" | null, "version": str, "pid": int}`. `mode: "browser"` is the observable for DD14's fallback. `visible` comes from the real GTK state (`Gtk.Window.get_visible()`, read on the GTK thread through a bounded idle), not from what the shell intended (DD12). This is what tests and the behavior test observe.
- **Security:** the routes sit behind the credential gate and the Origin allowlist, like `/api/window/focus`. A credential holder can already stop the app, so nothing new is granted. `SECURITY-MODEL.md` gets a line.
- Trade-off: on a no-tray desktop, quitting is a right-click a user must learn, which is why the notice exists.

**DD5 — The AppImage adds itself to the menu, done by `AppRun`; the AppImage and the `.deb` are separate entries**:
- **The locus is `AppRun`** (POSIX sh, under `packaging/`). It keeps AppImage-specific behaviour out of `the_one/`, per "packaging stays outside the app", and the packaging unit tier tests it with a fake `APPIMAGE`/`APPDIR` and `HOME`.
- **On every launch with no argument or `app`,** best effort and never blocking the launch, `AppRun` writes:
  - `~/.local/share/applications/gleepglorp-ai-appimage.desktop`, copied from the AppImage's embedded entry (rendered by DD6), with `Exec`, `TryExec` and the "Quit GleepGlorp AI" action's `Exec` rewritten to `$APPIMAGE`;
  - the icon, at `~/.local/share/icons/hicolor/512x512/apps/gleepglorp-ai-appimage.png`, referenced by absolute path, so no icon-cache question arises.

  It rewrites only on change, so the most recently launched AppImage owns the entry.
- **Separate entries.** A distinct id (`gleepglorp-ai-appimage`, named "GleepGlorp AI (AppImage)") against the `.deb`'s `gleepglorp-ai`, so both appear when both are installed. A shared id would let the user-level entry shadow the system one, and then hide the app once the AppImage is deleted.
  - Both share `StartupWMClass=the-one`. Which entry GNOME attributes a window to when both are installed is observed in the VMs and noted in the guide.
- **Side by side.** Both use the same data dir, port and credential, so they are one running app (DD13 for different versions). The guide documents this.
- **Uninstall:**
  - delete the AppImage;
  - `TryExec` hides the stale entry the next time GNOME reloads the menu, which is the next login (GNOME Shell reloads only on application-directory changes);
  - the guide names the two files to delete for an immediate clean-up.
- Trade-off: the AppImage writes two user-level files outside the data dir, documented.

**DD6 — One product-metadata source; the version's last duplicate is pinned, then removed after Mission 31**:
- **Product metadata** goes in `packaging/product.toml`:
  - display name, Linux package name, desktop ids and names, executable, WM class, summary, maintainer, icon source;
  - the data-dir slug `the-one`, pinned read-only by a unit test against `the_one/config.py::_default_data_dir`, so the data dir cannot move.
- **A stdlib-only renderer** fills the Linux templates (`control.in`, both `.desktop` templates with the Quit action, `AppRun`'s names) from `product.toml` plus the version. It exposes the same values for Flight 3 (`Info.plist`) and Flight 4 (`iscc /D…`); those flights wire them.
- **The version** for every build is `the_one/__init__.py::__version__`, which the Windows builds already read. `build.sh` takes no hand-typed version; the N/N+1 test builds override it through the staging rewrite only.
- **`pyproject.toml`'s `version` stays for now,** pinned equal to `__version__` by a unit test. Making it `dynamic` changes `uv.lock`, which Mission 31 also edits, and has to be checked against every CI task's `uv sync --locked` with the pinned uv versions (0.9.30, and 0.10.0 on the macOS probe). That conversion is handed to Flight 4, after Mission 31 merges (recorded in the mission's flight list).
- Rationale: the criterion asks for "one edit". Until then, a missed edit fails the unit gate instead of shipping.
- Trade-off: two edits for a version bump until Flight 4.

**DD7 — Window geometry under Wayland: size is remembered, position belongs to the compositor**:
- Ubuntu 26.04 (Wayland only) and Debian 13 (Wayland by default) give a client no global position. The app runs GTK natively on Wayland, with no forced `GDK_BACKEND=x11`.
- On a Wayland session, `_save_current_geometry` passes `x`/`y` as `None`. `save_state` accepts that, and GTK reports `(0, 0)` there, which would otherwise restore a later X11 session at the corner. Position is still remembered on X11.
- Trade-off: the criterion's "position" holds on X11 only on Linux. The guide states this, and the HAT shows it.

**DD8 — `packaging/spike/` is folded in or removed**:
- **`stage.py`** becomes `packaging/stage.py`, the shared staging step.
- **`check.sh`, `inner.sh`, `score.py`, `xwd2png.py` and `images/`** become `packaging/linux/checks/`, the container gate suite. The WSLg display path becomes optional: the window phase runs under the forwarded display locally and under `xvfb` on the runner.
- **`macos-checks.sh`** moves to `packaging/macos/`, with the path edit in `packaging-probe-macos.yml`; its `on:` block is unchanged.
- **`packaging/spike/`** is deleted.
- **A small unit tier** (`tests/test_packaging_*.py`) loads these scripts by path, as `tests/test_windows_test_copy.py` does. It covers:
  - staging;
  - the renderer and the slug pin;
  - the version pin;
  - the exclude and audit rules;
  - the scoring;
  - `AppRun`'s self-integration (DD5).

**DD9 — Fresh-VM verification: QEMU/KVM inside a Docker container, on stock GNOME desktops**:
- **Probe at planning (passed):** `--device /dev/kvm` in a container (no `--privileged`) answers `KVM_GET_API_VERSION` 12 and creates a VM; nested virtualisation is on. QEMU lives in an `m32-*` image, and nothing is installed on the operator's PC.
- **The guests, provisioned once, snapshotted, and reused through fresh overlays:**
  - **Ubuntu 26.04:** an unattended install from the official desktop ISO (autoinstall), so the seeded snaps, App Center included, are present as on a real install (operator, 2026-10-24).
  - **Debian 13:** the `debian-13-generic` image (not `genericcloud`, whose cloud kernel likely lacks DRM and input drivers) plus `task-gnome-desktop`, the same task the Debian installer uses for a GNOME desktop.
  - **Both:**
    - a test user with a password, GDM autologin, initial setup disabled, and sshd;
    - `virtio-vga`/`virtio-gpu`, and `usb-tablet` for absolute pointer input;
    - nothing the packages need installed in advance.
- **Act:**
  - the desktop's own install path, by keyboard and mouse through QMP (`input-send-event`, `send-key`):
    - the `.deb`: double-click in Files, the App Center or GNOME Software, and the polkit password typed in;
    - the AppImage: Files Properties "executable", then double-click;
  - SSH, for shell steps only;
  - never `apt`, `dpkg` or `pkcon` for an install under test.
- **Observe:**
  - QMP `screendump` PNGs;
  - SSH output;
  - inside the guest, the app's API: `/api/live`, `GET /api/window/state`, `/api/agents`, with the guest's credential.
  - SSH commands that need the session use its environment (`XDG_RUNTIME_DIR=/run/user/<uid>`, `WAYLAND_DISPLAY`, `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus`).
- **Resources:** one guest at a time (4-6 GB RAM on a 15 GB host), and never alongside a Mission 31 test gate.
- **Safety:** guests are disposable, and use only guest-local ports and data dirs. Nothing runs on the host's 8484 or 8485, and the host data dir is never touched. Containers are named `m32-vm-*` and stopped by name. Only `/dev/kvm` is passed through.
- **Premises probed in the apparatus leg** (leg 4), with Flight 1's existing packages plus a version-bumped copy, before the hosted work. The relaunch row is probed in leg 6 with a local build of the lifecycle legs. Each premise has an owner and a fallback:

  | premise | fallback |
  |---|---|
  | double-clicking a `.deb` installs it without a terminal on both distros | divert to the operator: a criterion question |
  | Files launches an executable AppImage, and `fusermount3` is present | documented in the guide; the operator is told |
  | WebKitGTK renders on a VM with no GPU (DMA-BUF blank-window risk) | apparatus-only render flags, logged; never shipped |
  | QMP input reaches a Wayland GNOME session | SSH plus `gio launch` for launching, logged |
| App Center and GNOME Software upgrade an installed package from a newer local `.deb`, and list it under Installed so it can be removed (software centres often list only packages with AppStream data) | ship a `/usr/share/metainfo/*.metainfo.xml` rendered from `product.toml` (the recipe leg); else divert to the operator |
| relaunch recovery and focus on a real session: a hidden window comes back and is raised, not a "ready" notice | probed in leg 6 with a local build after the lifecycle legs; else divert |
  | the host `bwrap` and WebKit's own sandbox under each distro's AppArmor/userns policy | observed and recorded; the `doctor` sandbox line (DD11) is read |

- Rationale: the criterion is behavior-test-backed on fresh VMs. A tray host, a notification service and a real GNOME session exist only there.
- Trade-off: building the guests is real effort (an ISO autoinstall about 6 GB, Debian about 3 GB), done once and snapshotted.

**DD10 — Outward steps, the hosted matrix, and the closing walk**:
- **One `.github/`-only PR to `main`** (operator-approved, 2026-10-24) adds `.github/workflows/linux-packages.yml`:
  - `on: workflow_dispatch` and `workflow_call` (ready for Flight 4's release);
  - no push, PR or tag trigger;
  - runs use `gh workflow run linux-packages.yml --ref flight/02-linux-packages`.
- **The hosted job:**
  - builds both packages in the DD2 container;
  - runs the gate suite on Ubuntu 26.04 and Debian 13 **bare** images, for both formats:
    - strict `doctor`, pinned and unpinned, under `xvfb`;
    - gate 2 and gate 4;
    - gate 3 on the `.deb` runs, whose dependencies bring in WebKitGTK;
    - the AppImage on bare images proves DD14's browser fallback, and `doctor` passing (DD11);
  - uploads the packages (short retention) and the gate logs;
  - fails on any FAIL or a missing summary.
- **What stays local:** the stock-desktop baselines (3.8 GB and 5.85 GB) do not fit a standard runner's free disk. The AppImage's gate 3 on stock desktops is measured locally (leg 1) and in the VMs.
- **Budget:** about 20-30 minutes per hosted run (image builds plus 4 checks), at 1×. At most 6 dispatches in the flight.
- **Before the first dispatch,** every script the job calls is rehearsed by running it (debrief recommendation 1):
  - the build in the same container locally;
  - the check suite against that build, with `xvfb` as on the runner;
  - `actionlint` and `shellcheck` with `set -u`, both from `$M32_BUILD/tools/`.
- **The closing walk (`linux-hat`):** the operator looks at both VM desktops through WSLg, one step at a time.

**DD11 — `doctor` reports the sandbox and the tray; a host with no desktop GTK is a supported degrade**:
- **Two advisory lines,** never gates, beside the `runtimes:` lines:
  - `sandbox:` — `bubblewrap`, or `passthrough — <reason>` with the factory's own reason (through a new small `describe_selection()` on the factory, which computes the same `(backend, reason)` as `get_sandbox_backend()`; log-once and caching unchanged);
  - `tray:` — DD3's decision.
- **The desktop-shell gate, when frozen, decides first whether the host has a desktop GTK, independently of the bundle.** The check is a host-loader soname probe for `libgtk-3.so.0`, plus the WebKit2 4.1 typelib in the host typelib directories. It is the same predicate `_webview_available()` and DD14 use, so `doctor` and the app always agree.
  - **The host has GTK:** any failure importing `gi`, Gtk, the tray module, or pystray's chosen backend is a FAIL. This catches a broken DD1 fallback on a GNOME host, which would otherwise look like "no GTK".
  - **The host has GTK but there is no display session** (no `DISPLAY`/`WAYLAND_DISPLAY`, for example over SSH): the probe checks the bundle's modules without importing a backend, which would open a display. It reports `desktop shell: OK — no display session; tray not probed`. So `doctor` passes headless and with no `xvfb`.
  - **The host lacks GTK:** `desktop shell: OK — no desktop GTK on this host; the app opens in the browser`, as long as `PIL`, `pystray._base` and the tray module import.
  - **The word "skipped" is never used:** Flight 1's strict scoring treats it as FAIL, and these are supported states.
- **Unchanged:** the exit code, the twelve gate names, and the lines the Windows CI lanes grep.

**DD12 — The GTK close and show paths are fixed in the shell (design review findings 1 and 2)**:
- **The close path must never block.** pywebview 5.4's `closing` is a locked event (`webview/window.py`: `Event(self, True)`), run synchronously on the GTK main thread from `delete-event` (`platforms/gtk.py::BrowserView.close_window`).
  - `_on_closing` saves geometry first, and the geometry getters do `glib.idle_add` plus a blocking `Semaphore.acquire()` (`platforms/gtk.py::get_size`/`get_position`). On the main thread, that deadlocks every close, the tray's Quit and the new quit route.
  - **Fix (cycle 2):** `_on_closing` always runs on the GTK main thread. It is a locked event fired from `delete-event`, and `destroy()`/`destroy_window` reach `close_window` through `glib.idle_add`. So on GTK it reads `window.native.get_size()` and `get_position()` (`Gtk.Window`) directly: synchronous, no deadlock, and the same measure as today's restore.
    - Not used: caching from `events.resized`/`moved`. Those report the allocation including client-side decorations and shadow on Wayland, and the client-area origin on X11, so the window would grow or drift at every relaunch.
    - `_on_quit`'s extra pre-destroy save is skipped on GTK; `closing` saves anyway.
    - The Windows path is unchanged.
  - **Lazy imports on the close and quit path** (`window_state`, `notice`, the notification helper) are moved to boot. A `.deb` upgrade replaces the bundle on disk under a running N, and N's later lazy import could load N+1 code or fail.
- **Show must map the window.** pywebview's GTK `BrowserView.show()` does `show_all()` and then, when `gtk.main_level() == 0`, which is the case under `Gtk.Application.run()`, `hide()`s again if `Window.hidden`. `hidden` is set once at creation and never cleared, and the shell creates the main window hidden.
  - So the first launch's `show()`, the tray's "Show" and a plain `show()` leave the window unmapped on Linux. Only `restore()`, through `present()`, maps it: Flight 1's "hidden until focused" finding.
  - **Fix:** on GTK the shell clears `window.hidden` before showing, and shows through a path that maps it (`restore()`/`present()`). This applies to the first show, the tray's Show, `focus_window` and the DD4 relaunch.
- **A real-GTK smoke test is required**, because fakes cannot catch either trap. A packaged or source run in Flight 1's container image under `xvfb` with a window manager-free display:
  1. launch;
  2. assert `GET /api/window/state` reads `visible: true` from GTK;
  3. `POST /api/window/quit`;
  4. assert the process exits within 15 s;
  5. also: a no-tray close leaves `visible: false` with the process alive, and a relaunch shows it again;
  6. also: `window-state.json` holds the same size after close and relaunch.

  The close is sent as a real `WM_DELETE_WINDOW` client message through python-xlib, so the real `delete-event` → `closing` path runs, not `window.destroy()`. It runs on a staged source build of leg 1's container, in Flight 1's container image, in leg 3 (`gtk-window-fixes`). A WM-free display has no client-side decorations and no focus-stealing prevention, so the VM probe after the lifecycle legs (leg 6) covers those.

**DD13 — A newer launch replaces an older running instance (operator, 2026-10-24)**:
- `_select_port` decides "ours" by credential, not version (Mission 20 DD11; `shell.py::_select_port`). So after an upgrade, a launch reaches the old process, possibly running hidden for days from a bundle `dpkg` has replaced on disk.
- **In the `is_ours` branch, the launch compares versions.** It takes the running instance's version from `/api/info`, which `_select_port` already fetches and every older build serves. The comparison is PEP 440 (`packaging.version`, whichever way the leg confirms is declared; an unparseable version means "not older"). It must order the N/N+1 test builds (`0.11.8` < `0.11.9.dev1`, and `0.11.9.dev1` < `0.11.9`) the same way dpkg orders `0.11.8` < `0.11.9~dev1` < `0.11.9`, and a unit test pins that agreement.
  - **Running version older:** `POST /api/window/quit`, then wait for the returned `pid` to exit, not for the port to free. uvicorn closes its listener before the lifespan drain (indexing, `close_vector_store()`, `close_connection()`), and a port-free wait would open the data dir during that flush, the M24 F7 DD-3a race. The bound covers `_graceful_shutdown`'s 60 s join plus margin. Then start normally.
  - **The old server lacks the quit route** (any build older than this flight; a non-2xx answer): focus it at once, with no wait, and log that a restart finishes the upgrade.
  - **Same or newer:** focus it, as today. An older package launched beside a newer running one does not take over.
  - **The old instance does not exit within the bound:** focus it and log. Never two servers on one data dir.
- **All platforms.** `shell.py` is shared. On Windows, Inno's close-applications step normally closes the old instance before an upgrade, so the takeover rarely runs there. Flight 4 confirms it with its Windows checks.
- **Fixed alongside:** the stale comment in `_select_port`'s fall-through ("a different the-one VERSION lands here too") and CLAUDE.md's "ours-by-version (attach a window only)" line. The latter is a one-line correction in a file shared with Mission 31.

**DD14 — WebKitGTK missing: the app says so and opens in the browser (operator, 2026-10-24)**:
- When `_webview_available()` is false on Linux, the browser-fallback branch first sends a desktop notification through `org.freedesktop.Notifications`: "GleepGlorp AI opened in your browser because WebKitGTK isn't installed. Install gir1.2-webkit2-4.1 for its own window." Then it opens the browser, as today.
- With no notification service, it logs only. `doctor` carries the same fact (DD11).
- When `gi` itself cannot be imported (a source install without PyGObject), the notice goes through `gdbus call` or `notify-send` if either is on `PATH`, else the log only. The call is bounded and never blocks the launch.
- No web UI change: that area belongs to Mission 31.

### Citation Audit
Verified against the worktree at `6f92fd5` (`main` after #308). Rows marked "corrected" were fixed after design review cycle 1.

| Citation | Status |
|---|---|
| `pystray/__init__.py::backend` — catches only `ImportError`; Linux order `appindicator, gtk, xorg`; `PYSTRAY_BACKEND` picks one (pystray 0.19.5) | verified |
| `pystray/_appindicator.py:22-28` — `require_version('AppIndicator3')`, then on `ValueError` `AyatanaAppIndicator3`, whose own `ValueError` escapes | verified |
| `tray.py::build_tray` — lazy `import pystray` | verified |
| `shell.py::DesktopSession.run` step 5 — `events.closing += _on_closing` only after a successful tray start; an exception means exit on close | verified |
| `shell.py::DesktopSession._on_closing` — calls `_save_current_geometry` before the `_really_quit` check | verified (cycle 1) |
| `shell.py::_save_current_geometry` — reads `window.width/height/x/y` | verified (cycle 1) |
| `webview/window.py` — `events.closing = Event(self, True)` (locked); `event.py::Event.set` runs locked handlers synchronously | verified (cycle 1) |
| `webview/platforms/gtk.py::BrowserView.close_window` — connected to `delete-event`, runs `events.closing.set()` | verified (cycle 1) |
| `webview/platforms/gtk.py::get_size`/`get_position` — `glib.idle_add` plus `Semaphore.acquire()` | verified (cycle 1) |
| `webview/platforms/gtk.py::BrowserView.show` — `show_all()`, then `hide()` when `main_level()==0` and `hidden` | verified (cycle 1) |
| `webview/platforms/gtk.py` — `resized`/`moved` report the allocation and the configure origin, not `get_size()`/`get_position()`'s measure (why DD12 does not cache them) | verified (cycle 2) |
| `webview/platforms/gtk.py::BrowserView.destroy` emits `delete-event`; `destroy_window` → `glib.idle_add(close_window)`: `closing` always runs on the GTK main thread | verified (cycle 2) |
| `app.py` `/api/info` returns `version` | verified (cycle 2) |
| `pystray/_xorg.py:36` — `Xlib.display.Display()` at import time | verified (cycle 2) |
| `packaging` 26.1 in the runtime closure (transitive; the leg confirms how it is declared before DD13 relies on it) | verified (cycle 2) |
| `shell.py::_on_quit` — really-quit flag, `chrome.deregister()`, `icon.stop()`, save geometry, `destroy()` | verified |
| `shell.py::DesktopSession.run` `is_ours` branch — credential-bearing `POST /api/window/focus`, then return | verified |
| `shell.py::focus_window` — `show()` + `restore()`; on GTK only `restore()` maps a hidden window | corrected (cycle 1) |
| `shell.py::_select_port` — "ours" means `/api/info` answers 200 to our credential, whatever the version; the fall-through comment about versions is stale | corrected (cycle 1) |
| `app.py::window_focus` — `async def` `POST /api/window/focus`; `window_chrome_post` is a plain `def` (threadpool), the pattern the new routes follow | verified |
| `main.py::cli_entry` — `if/elif` on `args[0]` | verified |
| `diagnostics.py::_probe_desktop_shell` — imports `PIL`, `pystray`, then the tray module; a frozen failure is a hard gate | verified |
| `diagnostics.py::run_doctor` — twelve gates plus advisory runtime lines | verified |
| `sandbox/factory.py::get_sandbox_backend` — selection order and reasons; log-once guard | verified |
| `window_state.py::save_state` — `x`/`y` optional | verified |
| `config.py::_default_data_dir` — `platformdirs.user_data_dir("the-one", appauthor=False)` | verified |
| version in `the_one/__init__.py:3` and `pyproject.toml:3`; setuptools backend; nothing in `tests/`, `scripts/`, `ci/` or `.github/` reads pyproject's version | verified |
| `windows-installer.yml`, `ci/tasks/windows-installer-build.yml` — read `the_one.__version__` | verified |
| `packaging/linux/rthook_host_gtk.py` and `build.sh` — as described in DD1 and DD2 | verified |
| `python-xlib` 0.33 in the closure (pystray dependency) | verified (cycle 1) |
| KVM in a container: API 12, VM created; nested `Y` | verified (planning probe) |
| Ubuntu 26.04 and Debian 13 image URLs answer 200 | verified (planning); the `generic` image and the desktop ISO are re-checked in the apparatus leg |

### Prerequisites
- [x] The toolchain decision and the AppImage approach (Flight 1; operator 2026-10-24)
- [x] Squawk 0251 merged (#308): the 3.11 freeze is clean
- [x] Squawk 0250 merged (#307): `pip-audit` is green on `main`
- [x] KVM usable from a container; images reachable; Docker present; Flight 1's `m32/*` images still present
- [ ] `gh auth status` and Actions minutes: re-verified at the hosted-build-prepare leg and before each dispatch
- [ ] The `ubuntu:24.04` digest: re-read at leg 1
- [ ] Ubuntu 26.04 desktop ISO and `debian-13-generic` URLs and checksums: re-checked at the apparatus leg

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified (three are re-verified at leg start, as listed)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Risk first:** leg 1 proves the AppImage fallback (DD1) in the pinned build container (DD2), on Flight 1's container baselines. It is the divert point.
2. **The app, then, in two legs:**
   - first the host-facing choices (the tray backend and detection, the no-WebKit notice, the `doctor` lines);
   - then the lifecycle (the GTK close and show fixes, no-tray hiding, quit and state routes, the version takeover), with a real-GTK smoke test.
3. **The VM apparatus is built alongside those app legs,** on disjoint files under `packaging/linux/vm/`, by its own Developer. Its premise probes run with Flight 1's existing packages: installing, upgrading and removing without a terminal. Once the lifecycle legs land, a short VM probe with a local container build checks relaunch recovery and focus on a real session (leg 6). Both divert risks are answered before any hosted spend.
4. **The recipe becomes product:** metadata, renderer, `AppRun` integration, audit, the spike fold and the unit tier.
5. **The hosted workflow** is prepared and rehearsed, then committed, pushed, and merged to `main` as a `.github/`-only PR.
6. **The hosted run** follows.
7. **The fresh-VM checks** and the behavior test run, and the guide is written from what they show.
8. **The operator's walk** closes the flight.

Legs 1-9 are reviewed, committed and pushed before the first dispatch (Flight 1's hosted-run pattern). Review checkpoints fall after leg 3 and after leg 5; both lifecycle legs have a Sonnet Reviewer (new credential-gated routes).

### Checkpoints
- [ ] The AppImage passes strict `doctor` unpinned, and amended gate 3, on stock Ubuntu 26.04 and Debian 13 containers; the ABI exercise passes (leg 1).
- [ ] Tray choice and detection, the no-WebKit notice and the `doctor` lines, unit-tested (leg 2).
- [ ] The GTK close and show fixes, the state route and a minimal quit route, real-GTK smoke-tested (leg 3).
- [ ] Both guests provisioned and snapshotted; the install, upgrade and remove premises answered (leg 4).
- [ ] No-tray hide and notice, the full quit path, focus with the activation token, and version takeover, unit-tested (leg 5).
- [ ] VM probe with a local build: relaunch recovery and focus on real GNOME (leg 6).
- [ ] One metadata source; packages, templates, metainfo and `AppRun` integration rendered from it (leg 7).
- [ ] The spike folded, the bundle audit enforced, the packaging unit tier green (leg 8).
- [ ] Workflow rehearsed; PR to `main` merged (leg 9).
- [ ] Hosted build green; listing matches the local container build (leg 10).
- [ ] `linux-package-install` passes on all four variants; Linux guide written (leg 11).
- [ ] Operator walk complete (leg 12).

### Adaptation Criteria

**Divert if**:
- The fallback `libgirepository-2.0` or the Ayatana stack does not work against a target host's GLib (leg 1). The options go back to the operator:
  - a newer pinned build container, checking the glibc floor against Debian 13's 2.41;
  - the AppImage with a stated prerequisite;
  - no AppImage.
- A stock desktop cannot install a local `.deb` without a terminal (leg 4). That is a criterion question for the operator.
- A relaunch cannot bring a hidden window back on a real GNOME session, even with the activation token (leg 6).
- The hosted build differs materially from the local container build (leg 10).
- A software centre cannot upgrade or remove a local `.deb`, even with AppStream metainfo (legs 4 and 11).

**Acceptable variations**:
- The Ayatana dependency set differs from DD1's expected list, as measured in the build container (logged).
- Apparatus-only render flags in the VMs (logged; never in a package).
- An extra hosted dispatch, within the 6-run cap.
- Leg 4 starts in parallel with leg 2 on disjoint files (concurrent crew, as in Flight 1 legs 5 and 6).

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `appimage-library-fallback` - Pinned build container. Host-first soname fallback for `libgirepository-2.0` and the Ayatana stack, outside `_internal`, with no `LD_LIBRARY_PATH`. The ABI exercise; strict unpinned `doctor` and amended gate 3 on Flight 1's stock and bare containers. The divert point.
- [x] `tray-selection-and-doctor` - The tray decision before any pystray import, backend choice and tray-host detection (DD3); the no-WebKit notice (DD14); the `doctor` sandbox and tray lines, and the host-GTK-first desktop-shell rule (DD11). Unit-tested.
- [x] `gtk-window-fixes` - DD12: the close path on the GTK thread, and show that maps; DD7 geometry on Wayland; `GET /api/window/state` from GTK; a minimal `POST /api/window/quit` (window registered or not); the real-GTK smoke harness (`WM_DELETE_WINDOW` close, quit exits, size round-trip) on a staged build from leg 1's container. Sonnet Reviewer.
- [x] `vm-apparatus` - QEMU-in-container guests: the Ubuntu 26.04 desktop ISO autoinstall, and Debian 13 generic plus GNOME. Snapshots, overlays, QMP and SSH helpers. The install, upgrade and remove premise probes with Flight 1's packages. Can start beside leg 2 (disjoint files).
- [x] `no-tray-lifecycle` - DD4 in full: the three close states, hide and async notice, `the-one quit`, the quit route's boot, browser and serve states with `pid`, the focus route as a plain `def` with activation-token forwarding, and DD13's version takeover (pid wait, old-server fallback, the version-order test). `SECURITY-MODEL.md` and the CLAUDE.md correction. Sonnet Reviewer.
- [x] `vm-relaunch-probe` - A short VM run of a local container build of legs 1-5 on both guests: no-tray hide and relaunch, focus with the activation token, the tray on Ubuntu, quit. Answers the relaunch divert risk before any hosted spend.
- [x] `linux-recipe` - `packaging/product.toml` and the renderer, the version pin test, the `.desktop` templates with "Quit GleepGlorp AI", AppStream metainfo, and `AppRun` self-integration (DD5).
- [x] `packaging-checks-and-audit` - The spike fold into `packaging/stage.py` and `packaging/linux/checks/`, `macos-checks.sh` moved, the post-freeze bundle audit, and the packaging unit tier (DD8).
- [x] `hosted-build-prepare` - `linux-packages.yml` and the bare-image hosted matrix (DD10), rehearsal by execution, review, commit and push, then the `.github/`-only PR to `main`.
- [x] `hosted-build-run` - Dispatch on the flight branch, the gate summary, and a listing comparison with the leg 9 rehearsal build.
- [x] `notice-and-metainfo-polish` - Shorter no-tray notice text that fits GNOME's banner; AppStream icon and developer/publisher fields; more icon sizes (operator, 2026-10-24, after leg 6).
- [x] `fresh-vm-checks` - `linux-package-install` on all four variants. `docs/linux-install.md`, README "Install", and the packaging sections in `CLAUDE.md` and `the_one/agents.md`.
- [x] `linux-hat` - The operator's guided walk on both VM desktops.
---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing (unit, browser lanes, lint)
- [x] Documentation updated (Linux guide, README, CLAUDE.md, agents.md, SECURITY-MODEL.md)
- [x] `packaging/spike/` gone; the `dynamic` version hand-off recorded for Flight 4

### Verification
- **The hosted run:** `linux-packages.yml`, dispatched on the flight branch, is green, and its summary shows PASS for both formats on both distros' bare images.
- **The behavior test:** `/mission-control:behavior-test linux-package-install` passes on all four variants in fresh VMs, with the run log committed.
- **The real-GTK smoke test** passes: the window maps; quit exits within 15 s; a no-tray close hides and a relaunch shows.
- **The gates:** `make test-unit`, `make test-browser` (under `THE_ONE_TEST_NETNS=1`) and `ruff` pass, and nothing under `the_one/` imports `packaging/`.
- **The operator's walk** is complete, with remarks logged in the flight log.
