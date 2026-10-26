# Flight: macOS app

**Status**: completed
**Mission**: [GleepGlorp AI installs like an app on Windows, macOS and Linux](../../mission.md)

## Contributing to Criteria
- [ ] **macOS install, without an Apple developer account.**
  - An ad-hoc signed `GleepGlorp AI.app` ships in a `.dmg` whose window offers drag-to-Applications.
  - The install guide gives the Gatekeeper approval steps for the macOS versions it names.
  - The app opens in its own window with the brand icon in the Dock.
  - *(Behavior-test-backed: `macos-app-install`, drafted here and run by a contributor on a real Mac at mission close, Flight 4.)*
- [ ] **The frozen runtime works in every build** (macOS half).
  - Strict `doctor` passes inside the built `.app` on the hosted runner, and a server starts there. A failed seam fails the build.
  - On a Mac with no real Python, nothing ever runs the Command Line Tools stub, and `doctor` says what to install.
  - A Finder-launched app finds `node`/`uv`/`python` where a terminal would.
- [ ] **The window behaves like a native app on each platform** (macOS half).
  - Closing the window keeps the app running in the Dock, and clicking the Dock icon brings it back.
  - Quit (the app menu, Cmd-Q or the Dock's Quit) exits cleanly, after the server's shutdown drain.
  - A second launch brings the running window forward instead of opening a second app. A newer second process replaces an older running one (Flight 2's DD13, shared code).
  - The window's size and position are remembered.
  - *(Unit-tested in code; driven through the real `.app` on the hosted runner where the runner allows it (DD9); confirmed by the contributor check.)*
- [ ] **Upgrades keep the user's data** (macOS half).
  - Replacing N with N+1 in Applications keeps chats, agents, providers, secrets and the local-API credential.
  - Removing the app (dragging it to the Trash) leaves the data.
  - The guide says where the data lives (`~/Library/Application Support/the-one/`) and how to remove it.
- [ ] **One packaging source of truth, built within the CI budget** (macOS's use of it).
  - The macOS recipe reads `packaging/product.toml` through `packaging/render.py`, with one app id shared with Linux (DD8).
  - It builds on a hosted runner only on a manual run, within the operator's cap of 4 macOS dispatches for this flight. The tag trigger is Flight 4's.
- [ ] **Install guides for every platform** (macOS): `docs/macos-install.md` and README "Install".
- [ ] **Existing gates pass.** Unit, browser and lint. Packaging code stays out of `the_one/` imports.

---

## Pre-Flight

### Objective
Turn Flight 1's macOS prototype into a shippable, ad-hoc signed `GleepGlorp AI.app` in a drag-to-Applications `.dmg`. The app behaves like a Mac app:
- closing the window keeps it in the Dock;
- the Dock icon brings it back;
- Quit drains the server before the process exits;
- a second launch focuses the running window.

Start by splitting `the_one/interfaces/desktop/shell.py`, as the Flight 2 debrief recommends, so the macOS states land in a structure that can carry them. Then probe the hosted runner's assumptions before relying on them: can it close, reopen, quit and photograph the app? Next build the macOS mode as a pure decision core plus a thin PyObjC layer, and make the frozen runtime safe on a stock Mac (the Command Line Tools stub, the GUI app's minimal `PATH`).

Every behaviour the runner can reach is proven on the hosted runner; everything else goes into a contributor checklist. The flight ends with the macOS install guide and an operator review of the runner's screenshots.

### Open Questions
- [x] Menu-bar icon, or Dock only? → DD2 (operator: Dock only)
- [x] Where does the `shell.py` split happen? → DD1 (operator: leg 1 of this flight)
- [x] Hosted macOS budget → DD10 (operator: up to 4 dispatches)
- [x] The app id → DD8 (operator: unify on `ai.gleepglorp.GleepGlorpAI`)
- [x] How Cmd-Q reaches the graceful drain → DD3
- [x] How the PyObjC layer attaches to pywebview → DD4
- [x] Second launch, and upgrade while running → DD5
- [x] The Command Line Tools stub → DD6
- [x] The PATH of a Finder-launched app → DD7
- [x] What the runner can act on and observe → DD9 (prepared in leg 2, verified by leg 3's premise probe)
- [x] The blank first paint (Flight 1 run 2, and squawk 0253 on Linux) → DD11
- [x] The CLI on macOS → DD12
- [x] Notifications on macOS → DD2 (none)
- [x] Verification and the contributor check → DD13, DD14

### Design Decisions

**DD1 — Split `shell.py` first, with no behaviour change (leg 1)**:
- **Why:** `shell.py` is 1478 lines. `DesktopSession.run()` is about 450 lines. Eight module-level mutable flags coordinate it (`_desktop_window`, `_session`, `_booting`, `_quit_requested`, `_really_quit`, `_browser_server`, `_tray_mode`, `_tracked_visible`) under `_window_lock`, which is taken at 7 sites. Both Flight 2 debrief reviewers ranked splitting it first, before macOS adds Dock, reopen and terminate states.
- **The modules**, all under `the_one/interfaces/desktop/`:
  - `takeover.py`: `_parse_version`, `_is_older`, `_auth_headers`, `_running_version`, `_request_quit`, `_pid_alive`, `_wait_for_exit`, `_activation_token`, `_post_focus`, `_takeover`, `_select_port`, `_now`, `_sleep` and the `_TAKEOVER_*` constants.
  - `window_control.py`: the window read and write paths the routes call, `window_visible`, `_window_mapped`, `_mode`, `window_state`, `quit_desktop`, `focus_window`, `set_window_theme`, the GTK helpers (`_is_gtk_backend`, `_on_wayland`, `_gtk_read`, `_gtk_activate`, `_show_window`, `_mark_visible`) and `_no_tray_hide`.
  - `shell.py` keeps `_NoTrayError`, `_NO_WEBVIEW_BODIES`/`_no_webview_body` and the notice constants beside `DesktopSession`, their only user.
  - `session_state.py`: one `SessionState` object holding the eight flags, the lock, and the session's own `server`/`thread` (today locals of `run()`, which DD3's terminate worker needs). It also holds the "never call quit under the lock" rule as methods. Examples: `publish_window()`, `begin_quit()` returning what to do after the lock is released, `mark_booting()`/`clear_booting()`. A module-level singleton replaces the globals. It is **reset in place, never rebound**, so every module that imported it sees the same object; tests reset it through a fixture.
  - `shell.py` keeps `DesktopSession`, the splash, `_webview_available`, `_wait_until_serving`, `_graceful_shutdown` and `run_desktop`.
- **Stable import surface:**
  - `the_one/interfaces/app.py`'s re-exports keep working (`_select_port` is imported by the CI packaged smoke), now pointing at the new homes.
  - The route imports in `the_one/interfaces/web/app.py` and `main._quit_command`'s `_wait_for_exit` move to the new modules.
  - `shell.py` keeps no compatibility aliases beyond what `interfaces/app.py` already promises.
- **Moved helpers are called through their module.** `shell.py` calls `window_control.X(...)` and `takeover.X(...)`, never `from … import X`, so one patch reaches every caller.
- **Tests move with the code.** Every patch of a moved name is re-pointed to its new module, because a patch on a re-export, or a direct assignment such as `shell_mod._desktop_window = None` (`tests/test_window_focus.py`), silently does not apply.

  A unit guard (an AST scan of `tests/`) fails on any of these forms:
  - `unittest.mock.patch("…shell.<name>")`;
  - `patch.object(<shell alias>, "<name>")`;
  - a `monkeypatch.setattr` with a dotted string, or with a module object (any alias of `the_one.interfaces.desktop.shell`, resolved through the test file's imports and fixtures, such as `shell_state` or `shell_mod`);
  - an `Assign` target on such an alias;

  in each case when the name is not *defined* in `shell.py`. State flags are reached through `SessionState` only.
- **Proof of no change:**
  - `make test-unit`: every pre-existing test passes (moved, not deleted), with new tests only for `SessionState` and the guard;
  - the `settings` browser lane (the window-chrome route);
  - Flight 2's real-GTK smoke test (`packaging/linux/checks/gtk-smoke.sh`) on both baselines, with every row PASS as at Flight 2 leg 3;
  - a `.deb` and AppImage `doctor` run in the build container.
- **Windows:** unit tests cover the win32 branches with fakes. Concourse's Windows lanes run on merge, and Flight 4 re-proves Windows end to end.
- **Trade-off:** a large mechanical diff in the flight's first leg. It is low-risk by construction, and it is the leg most worth reviewing carefully.

**DD2 — On macOS there is no tray: "dock" mode, native behaviour (operator: Dock only)**:
- On darwin `DesktopSession.run` never imports or builds pystray. pystray's `_darwin.Icon.__init__` creates an `NSStatusItem` on whatever thread builds it, which is `_boot`'s worker thread here, not AppKit's main thread.
- `_tray_mode = "dock"` (a new value):
  - `GET /api/window/state` reports `"tray": "dock"`;
  - `doctor`'s advisory line reads `tray: dock (macOS keeps the app in the Dock)`.
- **Close** (the red button, Cmd-W; pywebview's menu has no File menu) hides the window (`orderOut`) and the app stays in the Dock. That is native Mac behaviour, so there is **no notice** on macOS. The notice-length rule (squawk 0254) stays Linux-only.
- **The three close states:**
  - dock mode hides;
  - `_really_quit` allows the destroy;
  - a failed hide allows the destroy (a deterministic exit, as on Linux).
- **App Nap:** with its window hidden, the app must keep serving connectors, indexing and MCP at full speed. The Info.plist sets `LSAppNapIsDisabled` (DD8), and the dock layer also holds an `NSProcessInfo` activity (`beginActivityWithOptions_reason_`, user-initiated, allowing idle system sleep) for the server's lifetime.
- **`doctor`'s `desktop shell` gate on darwin** checks for the Cocoa backend with `importlib.util.find_spec("webview.platforms.cocoa")` and the `objc`/`AppKit` specs. It no longer checks pystray. It never imports `webview.platforms.cocoa`, because that import calls `NSApplication.sharedApplication()` and `setActivationPolicy_(0)` (`cocoa.py` module level), which would flash a Dock icon from the CLI.
- Windows and Linux are unchanged.

**DD3 — Every quit on macOS reaches the server drain: one terminate path, one stop path**:
- **The problem (pywebview 5.4):**
  - `BrowserView.AppDelegate.applicationShouldTerminate_` asks each window's `should_close`, which fires our `closing` handler. In dock mode that handler hides and answers "no", so the app menu's Quit, the Dock's Quit and the quit Apple event would do nothing.
  - If it answered "yes", AppKit's `terminate:` calls `exit()` after `applicationWillTerminate:`. `DesktopSession.run`'s `finally` (`_graceful_shutdown`: the lifespan drain, `close_vector_store()`, `close_connection()`) would never run, which is the M24 DD-3a hazard.
  - **Cmd-Q typed into the web view takes a second path:** `WebKitHost.keyDown_` maps Cmd-Q straight to `BrowserView.app.stop_` (`cocoa.py`, the `char == 'q'` branch), bypassing `applicationShouldTerminate_`.
  - `destroy()` reaches `windowWillClose_` → `app.stop_` through `AppHelper.callAfter`, outside event processing, and posts no event. So `NSApp.run` may not return until the next event arrives (pystray's `_darwin._stop` posts a dummy event for exactly this reason).
- **Path T (terminate):** the app menu's Quit, the Dock's Quit, the quit Apple event, logout and shutdown. Also, on darwin, **every quit the app starts itself**: `quit_desktop` (`POST /api/window/quit`, `the-one quit`, the takeover), **whether the window is published or the app is still booting**, calls `NSApp.terminate_(None)` on the main thread instead of `destroy()` or recording a pending flag. That makes one drain path and removes the missing-event hazard.
- **`_boot` never terminates on darwin.** `_abort_if_quit` and `_boot`'s exception path only stop the boot: they set `SessionState.boot_stopped`, a `threading.Event` that `_boot` sets on every exit, normal or not. They call no `terminate_` and no `destroy`. When `_boot` raises on darwin and no terminate is pending, it calls `terminate_` once, so the error exit also drains through path T.
- **Path T never closes a pywebview window.** Windows close only when AppKit terminates. A `windowWillClose_` while a terminate is pending would reach `app.stop_` and `app.abortModal()` (`cocoa.py`), returning `NSApp.run` mid-drain.

  Our `applicationShouldTerminate_` returns `NSTerminateLater` and, **only if no terminate is already pending**, starts one worker thread. A repeat call while one is pending also answers `NSTerminateLater` and starts nothing. The worker:
  1. calls `SessionState.begin_quit()`, which sets `_really_quit` and `_quit_requested` under the lock and returns the window to save, if any. The geometry is read outside the lock (DD1's rule): Cocoa's `get_size` may fall back to `callAfter` plus a semaphore;
  2. while booting, waits on `boot_stopped`, bounded at 10 s;
  3. runs `_graceful_shutdown(server, thread)` on the session's own server and thread, from `SessionState`, joining for 60 s;
  4. flushes and closes the logging handlers;
  5. calls `NSApp.replyToApplicationShouldTerminate_(True)` on the main thread (`AppHelper.callAfter`).

  AppKit then terminates the process. Logout and shutdown use the same path, so the app never cancels a logout. `run()`'s `finally` never runs on this path, and nothing relies on it.
  - **Bounded:** the worker's whole budget is 10 s (boot) plus 60 s (join), plus logging, within the takeover's 75 s pid wait (`_TAKEOVER_WAIT_BOUND`). After it, the worker replies `True` anyway and logs it.
  - **A second launch that only focuses** (the `is_ours` branch) returns before any server or `webview.start` exists, so no delegate is installed there.
  - **Exit safety:** AppKit's `exit()` runs C and C++ static destructors with daemon threads alive (usearch, tokenizers). `lifecycle.sh` checks `~/Library/Logs/DiagnosticReports` for a crash report after each quit.
  - **Acceptable variation, recorded if used:** `os._exit(0)` after a successful drain and log flush, in place of the reply.
- **Path S (stop):** Cmd-Q reaching `WebKitHost.keyDown_`, from the main window or the splash. pywebview's own `app.stop_` runs inside event processing, so `NSApp.run` returns, then `webview.start` returns. `run()` then, on darwin:
  1. calls `begin_quit()` first, so a still-running `_boot` sees `_really_quit`, stops without publishing, and sets `boot_stopped`;
  2. hides the window directly (`orderOut_`), so the user never sees a frozen window during the drain;
  3. saves the geometry if `self._window` is set and was shown;
  4. lets the `finally` drain, as on every other platform.

  After the loop has stopped, a darwin `quit_desktop` or boot abort does nothing more: the drain is already under way.
- **Which path a real keystroke takes** is premise-probed (P3, DD9). AppKit tries menu key equivalents before `keyDown_`, and pywebview's app menu binds `q` to `terminate:` (`cocoa.py` `_add_app_menu`), so a real Cmd-Q most likely takes path T. Path S is then defensive, but kept, because the binding is pywebview's. The canary pins both facts. Both paths drain and save geometry.
- **The window routes' answers are unchanged.** `quit_desktop` returns `quit: true` with the pid before termination starts, and `the-one quit --wait` and the takeover wait on the pid, as on Linux.

**DD4 — The PyObjC layer is thin; the decisions are pure and unit-tested on Linux**:
- **`the_one/interfaces/desktop/macos_dock.py`:**
  - a pure decision core: `on_close(state) → "hide" | "allow"`, `on_reopen(state) → "show" | "defer" | "ignore"` (`defer` while booting: shown when the window is published), `on_terminate(state) → "drain-then-reply" | "reply-now"`;
  - DD3's worker;
  - `activate(window)`, which shows, deminiaturizes and activates the app (`NSApp.activateIgnoringOtherApps_`), always through `AppHelper.callAfter`, because pywebview's Cocoa `restore()` calls `deminiaturize_` on the caller's thread. `window_control.focus_window`'s non-GTK path calls it on darwin (the route runs on a threadpool thread);
  - `install(session)`, called **once, on the main thread**, by `DesktopSession.run` before `webview.start`. It runs only on darwin and imports `objc`/`AppKit`/`webview.platforms.cocoa` lazily.
- **What `install` adds:** a runtime subclass of `BrowserView.AppDelegate`, with a unique Objective-C class name (`TheOneAppDelegate`), replaces the class attribute. pywebview instantiates `BrowserView.AppDelegate.alloc().init()` in `BrowserView.__init__` for every window it creates, the splash included, so each delegate it sets is ours. The subclass adds:
  - `applicationShouldHandleReopen_hasVisibleWindows_`: applies `on_reopen`, then returns NO (it acted);
  - `applicationShouldTerminate_` (DD3), declared so PyObjC types the return as `NSUInteger` (`NSTerminateLater` is 2, not a BOOL).

  If the subclass route fails on the runner, the leg may use `objc.classAddMethods` instead and records which.
- **The leg 3 probe proves these premises before leg 4 builds on them (DD9):** the subclass takes effect; `NSTerminateLater` plus a deferred reply terminates; the reopen handler fires on `open -a`; the return type survives.
- **No AppKit code runs in tests.** The decision core, the worker and `activate`'s dispatch are tested with fakes on Linux. A **canary unit test** reads pywebview 5.4's `webview/platforms/cocoa.py` source (present in every install, any OS) with `ast` and asserts the facts DD3 and DD4 rely on:
  - `BrowserView.AppDelegate` defines `applicationShouldTerminate_` and not `applicationShouldHandleReopen_hasVisibleWindows_`;
  - `WindowDelegate.windowShouldClose_` calls `should_close`, which fires `events.closing`;
  - `windowWillClose_` calls `app.stop_` and `app.abortModal()`, and posts no event;
  - `WebKitHost.keyDown_`'s `'q'` branch calls `app.stop_`;
  - `_add_app_menu` binds the Quit item to `terminate:` with key `q`;
  - `BrowserView.__init__` calls `BrowserView.AppDelegate.alloc()`;
  - `restore()` calls `deminiaturize_` directly.

  A pywebview bump that changes any of them fails the canary, not a contributor's Mac.
- **Visibility read:** `window_visible()` on Cocoa reads the native `NSWindow.isVisible()` through `window.native`, trying a direct read first as pywebview's own `get_size`/`get_position` do. It replaces the intent-tracked `_tracked_visible` on darwin, so the state route reports the truth (the observable for DD9).

**DD5 — Second launch and upgrade on macOS**:
- **A Finder, Dock or `open -a` launch of a running app** is a LaunchServices *reopen* of the running process, not a second process. DD4's reopen handler shows the window.
- **A second process** (`open -n`, a terminal `Contents/MacOS/the-one app`) takes the existing `takeover._select_port` path:
  - the same version focuses the window through `POST /api/window/focus`;
  - an older running version is replaced, per Flight 2 DD13 (shared code). The pid wait uses POSIX `os.kill(pid, 0)`, which is safe on darwin.
- **Upgrade while running (a premise, probed in leg 3, P5):** Finder may refuse to replace a running app outright. If it does replace it, a Finder launch most likely reopens the still-running N (LaunchServices matches the running bundle). The probe emulates Finder: remove the old bundle, then copy the new one, so its files are new inodes. It never overwrites in place, which could get the running ad-hoc-signed process killed for a code-signature mismatch. Either way:
  - the guide says to quit GleepGlorp AI (Cmd-Q) before replacing it;
  - the contributor checklist records what Finder itself does if you don't (behavior-test step 9);
  - data safety does not depend on it, since N and N+1 share the data dir and only one server owns the port.

**DD6 — Never run the Command Line Tools stub; walk `PATH` for the first real interpreter**:
- **The stub:** on a Mac without the Command Line Tools, `/usr/bin/python3` is a stub that opens an install dialog when run.
- **The fix in `the_one/platform/interpreter.py::_resolve_frozen_python`:**
  - on darwin, `/usr/bin/python3` and `/usr/bin/python` count as interpreters only if `xcode-select -p` exits 0 and the directory it prints exists. It runs with a 5 s bound, is cached per process, and never prompts;
  - the resolver **walks every `PATH` entry**, calling `shutil.which(cand, path=entry)` per entry, which keeps `PATHEXT` on Windows, rather than taking the first hit across the whole `PATH`. A stub (or, on Windows, a Store alias) early on `PATH` then no longer hides a real interpreter later on it.
- **`doctor`'s runtime list (`diagnostics.detect_runtimes`)** applies the same stub filter, so it no longer reports the stub as a found `python3`.
- **On Windows** this changes behaviour only in the shadowing case (strictly better); the existing Store-alias tests are kept.
- **`doctor`'s interpreter gate:** on a Mac with no real Python it fails with "Install Python 3 (python.org or Homebrew), or set THE_ONE_PYTHON", which is the frozen seam's existing actionable path.
- **Tests:** unit-tested with fake `PATH` trees and a fake `xcode-select`. Not reproducible on the runner (it has Xcode); the contributor checklist covers a stock Mac if one is available.

**DD7 — A Finder-launched app gets the user's login-shell `PATH` (frozen, darwin only)**:
- **The problem:** a Finder or Dock launch inherits launchd's `PATH` (`/usr/bin:/bin:/usr/sbin:/sbin`). The static augment list (`env.py::_common_runtime_dirs`) misses nvm, fnm, asdf, Volta and pyenv, which live in per-version or shim directories that only the user's shell configuration knows.
- **The design:** when frozen on darwin, `env.py` asks the user's login shell for its `PATH`, **once per process, synchronously, before the server starts or anything is spawned**. It runs for `serve` and `doctor` at the start of the command (`main.cli_entry`), and for `app` in `DesktopSession.run` just after the `is_ours` return. A second launch that only focuses the running window then pays nothing. It never runs inside an async handler or a lifespan task. **An unprimed process** (`chat`, `version`, tests) uses the static fallback and never computes the `PATH` lazily.
  - **The shell:** `$SHELL`, else `pwd.getpwuid(os.getuid()).pw_shell`, else `/bin/zsh`.
  - **The command:** `-l -i -c` running `/usr/bin/printenv PATH` between two markers (works under fish too).
  - **Isolation:** stdin `/dev/null`, stderr `/dev/null`, stdout to a temporary file rather than a pipe (an rc file's `ssh-agent` or `gpg-agent` child can hold a pipe open). It starts in a new session and is bounded at 5 s; on timeout the whole process group is killed (`os.killpg`).
  - **The result** is cached in the process.
- **Order on darwin:** the login shell's entries come **first**, then the inherited `PATH`, then the static list, de-duplicated. The user's tools then win over `/usr/bin` as they do in a terminal: Homebrew or pyenv `python3` beats the system's. The `THE_ONE_EXTRA_PATH` override and an operator-supplied MCP `PATH` keep their precedence, and the bundle-dir strip still wins (the M15 F5 rule).
- **Failure modes:** a timeout, a non-zero exit or missing markers fall back to the inherited `PATH` plus the static list and log one line.
- **Static additions** (for the fallback): `~/.volta/bin` and `~/.local/share/fnm/aliases/default/bin`.
- **Scope:** Linux and Windows are unchanged. One implementation stays in `env.py` (mission constraint).
- **Trade-off:** it runs the user's shell startup files once at launch, adding up to 5 s in the worst case; typical shells take well under a second. That is the user's own configuration, bounded and cached, and it is the established fix for GUI apps on macOS. `doctor` prints the `PATH` source (`login shell` or `static fallback`) on darwin.
- **The probe pins its environment (DD9, P8):** it records the `PATH` and `SHELL` an `open`-launched app actually inherits on the runner (`ps eww <pid>`). The login-shell check is run with `SHELL` set explicitly, so a result is never an accident of the runner's environment.

**DD8 — One app id, and the macOS recipe reads `product.toml` (operator: unify)**:
- **`packaging/product.toml`** gains:
  - a top-level `app_id = "ai.gleepglorp.GleepGlorpAI"`;
  - a `[macos]` section: `bundle_name = "GleepGlorp AI"`, `bundle_executable = "the-one"`, `dmg_file_stem = "GleepGlorp_AI"`, `min_os = "14.0"` *(was "11.0"; operator, 2026-10-25, after leg 3 found the bundled numpy's arm64 extensions require macOS 14)*, `bundle_category = "public.app-category.productivity"`.
- **`render.load()` rejects a key that appears twice:** in two sections, or in a section and at the top level. It flattens every section into one namespace, so a `[macos] executable` would silently overwrite `[linux] executable`. The macOS keys carry distinct names, and a unit test pins the rejection.
- **`[linux] metainfo_id` is removed.** Linux's templates read `app_id`, so there is one source of truth.
- **Linux reads `app_id` for its AppStream id.** The value is unchanged, so no Linux output changes; a unit test compares a rendered metainfo file before and after.
- **`render.py`** exposes the macOS values plus two version forms. Apple wants one to three period-separated integers:
  - `CFBundleShortVersionString` is the PEP 440 release triplet (`0.11.9`);
  - `CFBundleVersion` keeps three integers and encodes the pre-release in the third: `major.minor.(patch × 10000 + n)`, where `n` is the dev number and 9999 is a final release. So `0.11.9.dev1` → `0.11.90001` < `0.11.9` → `0.11.99999` < `0.11.10.dev1` → `0.11.100001`.

  A unit test pins the mapping against PEP 440 order, and `render.py` refuses a version it cannot encode (a dev number of 9999 or more, `a`/`b`/`rc`, `.postN`).
- **`packaging/macos/the-one.spec`** takes `bundle_identifier`, names and `info_plist` from `render.py --json`, adding:
  - `LSApplicationCategoryType`;
  - `NSHumanReadableCopyright` (MIT);
  - `LSMinimumSystemVersion`;
  - `NSHighResolutionCapable`;
  - `LSAppNapIsDisabled` (DD2);
  - `NSAppTransportSecurity` with `NSAllowsLocalNetworking`. pywebview adds its ATS exception only to the in-memory Info.plist dictionary at import (`cocoa.py` module level). WebKit's out-of-process networking may read the file on disk, so the on-disk file must carry it (DD11).
- **`packaging/macos/the-one.spec` drops pystray** from its collection, since darwin never imports it.
- **`packaging/macos/build.sh`** takes the Linux recipe's CLI shape (`--version`, `--from-head`, `build.env`, `SOURCE_DATE_EPOCH`) and keeps calling the shared `stage.py`.
- **No shared shell library this flight.** The Linux build is proven. Consolidating the hosted workflows and shell steps is Flight 4's (debrief recommendation 5); this flight shares the Python layer (`stage.py`, `render.py`, `product.toml`).
- **The `.dmg`** is built with `hdiutil create` from a staging folder holding the `.app` plus an `Applications` symlink (UDZO, volume name "GleepGlorp AI"). No background image or Finder layout: those can't be authored or checked headlessly.
- **Signing:** ad-hoc (`codesign --force --deep -s -`), checked with `codesign --verify --deep --strict`. No hardened runtime and no entitlements; the inert notarization hook stays a comment.
- **`packaging/macos/audit.py`** (new; a Linux `audit.py` analogue, unit-tested on canned tool output) reads `otool -L`/`otool -l` for every Mach-O in the bundle. It fails on:
  - a load path outside `/System`, `/usr/lib`, `@rpath`, `@loader_path` or `@executable_path` (no Homebrew or runner-toolcache leaks);
  - a non-arm64 slice;
  - an `LC_BUILD_VERSION` minimum above `min_os`.

  `min_os = 11.0` has been checked only against wheel tags. Leg 3's dispatch runs the same `otool` read on a Flight-1-style build, report-only, to settle `min_os` before leg 6 hard-codes it.

**DD9 — The apparatus: the hosted `macos-15` runner, premise-probed before it is relied on (legs 2-3)**:
- **What we know:** Flight 1 run 2 showed the runner has a logged-in GUI session. A bare `open` made a real native window, and `screencapture` captured it.
- **To act:**
  - `open` and `open -a` (launch and reopen);
  - `open -n` (a second process);
  - `osascript -e 'tell application id "<app_id>" to quit'` (the quit Apple event, i.e. the Cmd-Q path);
  - System Events `keystroke "w" using command down` (needs Accessibility);
  - `the-one quit`, `POST /api/window/focus`;
  - `ditto` (replace the `.app`), `xattr` (quarantine).
- **To observe:**
  - `GET /api/window/state` (`visible` from `NSWindow.isVisible()` after DD4, plus `mode`, `tray`, `pid`, `version`);
  - `GET /api/live`, `GET /api/info`;
  - `screencapture` series;
  - the app log in the data dir, `log show`;
  - `window-state.json`;
  - the process table by recorded pid only.
- **The premises** are prepared in leg 2 and probed in leg 3's single dispatch, with two bundles built in the same job:
  - **The product `.app`**, built from the current tree. Its observations describe today's build: it still starts pystray on darwin, which may explain Flight 1's `focused:false`, since `_boot` builds pystray before publishing the window. The app log is captured. These observations are not the target behaviour.
  - **A minimal probe `.app`**, frozen with PyInstaller from a probe script in the same venv (pywebview 5.4, pyobjc). It answers what the runner and AppKit can do, with no product change. It installs DD4's delegate subclass, returns `NSTerminateLater` and replies from a worker after 3 s, logs reopen calls, destroys its last window from a worker, and times how long `webview.start` takes to return.
- **What leg 3 settles:**
  - **P1:** a window and a timed first paint (DD11).
  - **P2:** the quit Apple event is delivered (Automation consent may block it headless), and the probe app's `NSTerminateLater` and deferred reply terminate the process.
  - **P3:** System Events keystrokes work (Accessibility). A real Cmd-Q keystroke with the web view focused shows which path it takes (DD3: T or S).
  - **P4:** `open -a` on a running app starts no second process, and the probe app's reopen handler fires. After `open -n` (a second process that asks the first to focus), check whether the app is really frontmost (`lsappinfo front`, plus a screenshot). `activateIgnoringOtherApps_` is deprecated on macOS 14+, where cooperative activation can ignore a raise asked for by a background process.
  - **P5:** replace while running, emulating Finder (DD5).
  - **P6:** Gatekeeper and translocation: an `spctl` assessment of a quarantined app, and `doctor` from a translocated path.
  - **P7:** `xcode-select -p` on the runner.
  - **P8:** the `PATH` and `SHELL` an `open`-launched app inherits (`ps eww`), and whether `open --env` passes variables to the launched app.
  - **P9 (informational):** destroying the last window from a worker returns from `webview.start` promptly, or hangs without an event. DD3 no longer destroys windows on darwin, so this only documents the hazard.
  - **The bundle's `LC_BUILD_VERSION` minimums** (DD8), report-only.
- **Every probe action is bounded.** A TCC consent prompt blocks rather than fails, so every `osascript`, System Events call, `screencapture` and `open` goes through the `perl alarm` bound (`tl`, as in `build.sh`).
- **Terminate needs no seam.** On darwin, `the-one quit` and `POST /api/window/quit` already call `NSApp.terminate_` (DD3), so they drive the same delegate path as the Dock's Quit. The quit Apple event (P2) adds the external sender.
- **Fallback if P3 fails** (Accessibility; decided now, an acceptable variation): a dual-gated test seam (`THE_ONE_DEV_MODE=true` plus its own flag, `THE_ONE_DESKTOP_TEST_ENDPOINT=1`, as the project's other `/api/_test/*` seams):
  - `POST /api/_test/desktop/close` calls `performClose_` on the main thread (the red button's path);
  - `POST /api/_test/desktop/geometry` with `{width, height, x, y}` sets the window frame on the main thread, for the geometry round-trip.

  They drive the real paths from inside the app and are never set outside the hosted check. The seam is product code (`the_one/interfaces/web/`, a row in CLAUDE.md's seam table), so it belongs to leg 4 and is written only if leg 3 shows that P3 fails.

  The flags are read from `os.environ`, and an `open` launch does not pass the job's environment. So the hosted check either uses `open --env` (if P8 shows it works) or starts the bundle's executable directly.
- **Read path for each assertion:** state from `/api/window/state`; the drain from the app log's lifespan-shutdown lines plus a clean `/api/live` refusal; data from authenticated `GET /api/agents`, `/api/providers`, `/api/chat/sessions` (credential from `~/Library/Application Support/the-one/api-credential`, only the `loc_<id>` prefix printed).

**DD10 — Hosted runs: a `.github/`-only stub PR, then at most 4 dispatches (operator)**:
- **The workflow:** a new `.github/workflows/macos-packages.yml`, `workflow_dispatch` plus `workflow_call` like `linux-packages.yml`, replaces `packaging-probe-macos.yml` (deleted in this flight's PR).
  - It needs a stub on `main` first. The stub is a `.github/`-only PR, as #310 was, and the outward steps stay with the Flight Director with the operator's go.
- **Cost guards** (Flight 1's): job and step timeouts, `concurrency` with no cancel-in-progress, `contents: read`, no secrets.
- **Uploads:**
  - the logs directory (7 days);
  - the `.dmg` as an artifact (7 days), so the contributor check (Flight 4) and the HAT have something to download. This is the release vehicle while Mission 31 forbids a release.
- **Budget, 4 dispatches** *(raised to 5 by the operator, 2026-10-25, for a re-probe after leg 3's delegate premise came back unanswered; see the flight log)*:
  - 1: the premise probe (leg 3);
  - 2-3: the built recipe and the lifecycle check, with one retry (leg 7). N and N+1 are two freezes in the same job, about 40 s each at Flight 1's measure;
  - 1 spare. A fifth needs the operator.
- **External session:** `gh auth status` and the `macos-15` label are re-verified at each leg that pushes or dispatches (legs 2, 3 and 7).
- **Rehearsal:** every script a dispatch runs is first executed on Linux under shims for the macOS-only commands (`codesign`, `hdiutil`, `otool`, `osascript`, `screencapture`, `open`), plus `shellcheck` and macOS bash 3.2 syntax (no `mapfile`, no `[[ … =~` captures), as leg 9 of Flight 2 did. That is an acceptance criterion of each leg that prepares a dispatch.

**DD11 — The blank first paint: measure first, fix only if the cause is in our shell**:
- **The evidence:**
  - Flight 1 run 2's capture showed a native window with blank dark content and `focused:false`;
  - squawk 0253 saw about 20 s of blank on Ubuntu's AppImage.
- **Flight 1's `focused:false` is not paint evidence.** It more likely means `_boot` had not published the window yet (on darwin it builds pystray on a worker thread first).
- **Leg 3's probe (P1):**
  - takes a screencapture series at +1, +3, +5, +10, +20 and +30 s after `open`;
  - records the app log's timings (server serving, window shown, the main window's `loaded` event, splash dismissed);
  - then repeats with the app already warm (a second launch after quit).
- **Candidate causes to classify:**
  - the window shown before the first page answers;
  - App Transport Security blocking the `http://127.0.0.1` load, because the exception is only in memory (DD8 adds it on disk);
  - the first WKWebView process start;
  - software rendering on the runner.
- **If the cause is in shared shell code** (for example the window shown before the server answers its first page, or the splash dismissed early), leg 4 fixes it in the shell. The fix covers Linux too: leg 4 also runs the Ubuntu AppImage first launch in Flight 2's VM apparatus, and squawk 0253 closes on that evidence.
- **If ATS is the cause,** DD8's on-disk key is the fix (macOS only).
- **If the cause is environmental** (the runner's first WKWebView process start, software rendering), the guide and the squawk record it and nothing is changed.
- Either way, the measured timings go in the flight log.

**DD12 — The CLI on macOS**:
- The guide documents `"/Applications/GleepGlorp AI.app/Contents/MacOS/the-one" doctor` (and `quit`, `version`) and suggests an `alias the-one=…` line.
- A drag-install has no script to place a symlink, and none is added.
- Bare `the-one` with no arguments opens the window (`frozen_entry_mac.py::launch_args`, unchanged).

**DD13 — Verification layers**:
- **Unit:**
  - the `SessionState` methods;
  - the dock decision core and the terminate worker;
  - the pywebview canary;
  - the interpreter `PATH` walk and the Command Line Tools stub;
  - the login-shell `PATH` with a fake shell;
  - `render.py`'s version mapping;
  - `audit.py` on canned `otool` output;
  - the `split` guard.
- **Hosted** (the `.app` actually built): `packaging/macos/checks.sh` keeps strict `doctor`, the interpreter, `serve` and the signature, and adds the audit and the `.dmg` layout (mount it, check the `Applications` link). A new `packaging/macos/lifecycle.sh` drives, through DD9's act and observe surfaces:
  - launch → `visible: true`, the first-paint series;
  - close → `visible: false` with the pid alive;
  - reopen → `visible: true`, with no new pid;
  - `open -n` → the app is frontmost (`lsappinfo front`), with no second server;
  - `the-one quit` → exits;
  - relaunch;
  - an N → N+1 replacement with data seeded through the API before and read back after;
  - Cmd-Q (the Apple event, or DD9's seam), and a real keystroke if P3 allows → the lifespan drain is logged, the process exits, and no new crash report appears in `~/Library/Logs/DiagnosticReports`;
  - `the-one quit` → the same drain (path T on darwin);
  - the geometry round-trip (`window-state.json` size and position after a move and resize through System Events if P3 allows, else the seam's `geometry` route, then a relaunch).
- **Contributor (Flight 4):** the behavior test `macos-app-install` (DD14).

**DD14 — The contributor check is a behavior test with a human Executor, drafted now and run at mission close**:
- `tests/behavior/macos-app-install.md` is drafted in this flight (status `draft`) so its observables shape the hosted checks.
- **Apparatus:** a contributor's Apple Silicon Mac. The contributor performs the actions and returns screenshots plus the outputs of a short command list (the CLI `doctor`, `/api/window/state` via `curl` with the credential). The Flight Director and a Validator judge from that evidence.
- **The written checklist** the contributor follows is `docs/macos-contributor-check.md`, generated from the spec's step table.
- **Steps:** the spec's step table is the one list. It needs three builds (N, N+1, N+2), so that "replace while running" can be told apart from "quit first", and it quits once with Cmd-Q and once from the Dock's menu (paths S/T).
- **The `.dmg` artifacts expire after 7 days (DD10).** Flight 4 dispatches fresh builds for the contributor run.

### Citation Audit
Verified against the working tree at `e21d219`:

| Citation | Status |
|---|---|
| `the_one/interfaces/desktop/shell.py` — 1478 lines; module flags `_desktop_window`, `_session`, `_window_lock`, `_browser_server`, `_tray_mode`, `_really_quit`, `_booting`, `_quit_requested`, `_tracked_visible` | verified |
| `shell.py::DesktopSession._on_closing` — hides when `self._icon` or `_tray_mode == "none"`, else allows; `_really_quit` allows | verified |
| `shell.py::DesktopSession._on_quit` — sets `_really_quit`, stops the icon if any, destroys the window; the drain is `run()`'s `finally: _graceful_shutdown(server, thread)` | verified |
| `shell.py::DesktopSession.run` step 5 — on non-Linux it calls `tray.build_tray(...)` and `run_detached()` with no tray decision (today's darwin path) | verified |
| `shell.py::window_visible` — non-GTK returns `_tracked_visible` | verified |
| `shell.py::focus_window` — non-GTK path `_show_window(window, restore=True)` | verified |
| `the_one/interfaces/app.py` — re-exports `_select_port`, `_webview_available`, `_wait_until_serving`, `_graceful_shutdown`, `run`; comment names the CI packaged smoke's `from the_one.interfaces.app import _select_port` | verified |
| `the_one/interfaces/web/app.py` — routes import `focus_window`, `window_state`, `quit_desktop`, `set_window_theme` from `shell` lazily; `the_one/main.py` imports `_wait_for_exit` from `shell` | verified |
| pywebview 5.4 `webview/platforms/cocoa.py::BrowserView.AppDelegate` — defines `applicationShouldTerminate_` (all windows' `should_close`) and `applicationSupportsSecureRestorableState_`; no reopen handler | verified |
| `cocoa.py::BrowserView.WindowDelegate.windowShouldClose_` → `BrowserView.should_close` → `window.events.closing.set()`; `windowWillClose_` calls `app.stop_` when no instances remain | verified |
| `cocoa.py::BrowserView.__init__` — `BrowserView.AppDelegate.alloc().init().retain()` then `app.setDelegate_` | verified |
| `cocoa.py::get_size`/`get_position` — try a direct read first, `AppHelper.callAfter` + semaphore only on exception | verified |
| `cocoa.py` — `app.setActivationPolicy_(0)` (a regular Dock app) | verified |
| pystray 0.19.5 `_darwin.Icon.__init__` — creates `NSStatusBar.systemStatusBar().statusItemWithLength_` in the constructor (the caller's thread) | verified |
| `the_one/platform/interpreter.py::_resolve_frozen_python` — `shutil.which(cand, path=search_path)` takes the first hit per name; Store aliases skipped by name, darwin stub not handled | verified |
| `the_one/platform/env.py::_common_runtime_dirs` — POSIX list `/usr/local/bin`, `/opt/homebrew/bin`, `~/.local/bin`, `~/.cargo/bin`, `~/.npm-global/bin` | verified |
| `packaging/macos/the-one.spec` — `bundle_identifier="ai.gleepglorp.the-one"`, hard-coded `info_plist` | verified |
| `packaging/macos/build.sh` — `hdiutil create -srcfolder "$APP"` (no `Applications` link); positional `<version>` | verified |
| `packaging/product.toml` — `[linux] metainfo_id = "ai.gleepglorp.GleepGlorpAI"`; no `app_id`, no `[macos]` | verified |
| `.github/workflows/packaging-probe-macos.yml` — dispatch-only, `macos-15`, `candidates` input, logs-only upload | verified |
| `cocoa.py::BrowserView.WebKitHost.keyDown_` — the `char == 'q'` branch calls `BrowserView.app.stop_(self)` (bypasses `terminate:`) | verified (design review cycle 1) |
| `cocoa.py::BrowserView.destroy` → `AppHelper.callAfter(self.window.close)`; `windowWillClose_` calls `app.stop_` and posts no event (pystray's `_darwin._stop` does post one) | verified (cycle 1) |
| `cocoa.py::BrowserView.restore` → `self.window.deminiaturize_(self)` on the caller's thread; module `restore(uid)` calls it directly | verified (cycle 1) |
| `cocoa.py` module level — sets `NSAppTransportSecurity` and `NSRequiresAquaSystemAppearance` on the in-memory `infoDictionary()` only; `sharedApplication()` and `setActivationPolicy_(0)` at class definition | verified (cycle 1) |
| `packaging/render.py::load` — flattens every TOML section into one dict with `values.update`, so a key repeated across sections is silently overwritten | verified (cycle 1) |
| `shell.py::_graceful_shutdown` — `should_exit = True` then `thread.join(timeout)`; a second call joins again (not a no-op after a timed-out join) | verified (cycle 1) |
| `shell.py` — `with _window_lock` appears 7 times | verified (cycle 1) |

### Prerequisites
- [x] Flight 2 merged to `main` (`e21d219`); the branch `flight/03-macos-app` is cut from it.
- [x] pywebview 5.4 and pystray 0.19.5 are the locked versions; the Cocoa source is readable in the venv.
- [x] GitHub Actions `macos-15` is available to the repo (Flight 1 ran 2 jobs).
- [ ] Re-verify at legs 2, 3 and 7, before any push, PR or dispatch: `gh auth status`, and that the `macos-15` runner label still resolves. This is an external session, so it's checked per leg.
- [x] The Linux real-GTK smoke apparatus (`packaging/linux/checks/gtk-smoke.sh`, the `m32/*` baseline images) exists for leg 1's no-change proof; the images are re-checked at leg 1.
- [x] Mission 31 is active: no release, and edits to `CLAUDE.md`, `the_one/agents.md` and `README.md` stay additive in their own sections.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [ ] Prerequisites verified (the leg-3 re-verify is per leg)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Leg 1:** split `shell.py` (DD1) and prove no change on Linux.
2. **Legs 2-3:** prepare and run the premise probe on the hosted runner (DD9, DD10, DD11). This is the flight's divert point for the apparatus.
3. **Leg 4:** the dock mode and both quit paths (DD2-DD5), plus any shell first-paint fix leg 3 calls for (DD11).
4. **Leg 5** (beside leg 4): the runtime seam on macOS (DD6, DD7). Leg 5 owns every `the_one/diagnostics.py` and `tests/test_doctor.py` change, including DD2's `tray: dock` line and the darwin `desktop shell` gate, so the two legs' files are disjoint.
5. **Leg 6:** the recipe (DD8): metadata, Info.plist, the `.dmg`, the audit, the full workflow and `lifecycle.sh`, rehearsed by execution on Linux.
6. **Leg 7:** the hosted run and fixes within the budget. Then the guide and the contributor checklist written from the run's evidence, and the behavior test finalized.
7. **Leg 8:** the operator reviews the screenshot series, the `.dmg` and the guide.

### Checkpoints
- [ ] The split lands with every pre-existing test passing (plus the new `SessionState` and guard tests), the browser lanes green and the GTK smoke all PASS.
- [ ] The premise probe answers P1-P9, and the apparatus is settled (Accessibility, or the fallback seam).
- [ ] The dock mode and the seam changes pass the unit tier, with the canary green.
- [ ] A hosted run builds the `.app` and `.dmg` from `product.toml`, passes strict `doctor`, the audit and the lifecycle check, and uploads the `.dmg`.
- [ ] `docs/macos-install.md`, the contributor checklist and `tests/behavior/macos-app-install.md` (draft) exist.
- [ ] The operator has reviewed the evidence.

### Adaptation Criteria

**Divert if**:
- **pywebview's Cocoa delegate cannot be extended** by either the subclass route or `objc.classAddMethods` (DD4). Then the choice between a vendored patch and a pywebview upgrade goes to the operator.
- **`NSTerminateLater` does not drain** (the process hangs, or AppKit exits before the reply) and no in-process alternative keeps the drain (DD3).
- **The runner has no GUI session** for a dispatched job (P1 fails). Then the window-level checks move to the contributor check, and the operator decides whether that is enough.
- **A replace-while-running sequence loses or corrupts data** (P5).
- **The 4-dispatch budget is spent** without a green lifecycle run.

**Acceptable variations**:
- **P3 fails (Accessibility):** drive close and geometry through the dual-gated test seam (DD9). **P2 fails (Automation):** terminate is still driven by `the-one quit` (DD3), and the quit Apple event goes to the contributor check.
- **The first paint is environmental:** document it and keep squawk 0253 open (DD11).
- **`objc.classAddMethods`** in place of the subclass (DD4), recorded.
- **`os._exit(0)`** after a successful drain in place of AppKit's reply, if the reply's `exit()` leaves crash reports (DD3), recorded.
- **The `.dmg`** without a Finder layout or background.
- **The geometry round-trip** asserted on size only, if the runner cannot move windows; position goes to the contributor check.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `shell-split` — split `shell.py` into takeover, window-control and session-state modules, with tests re-pointed and a guard; no behaviour change, proven by the unit tier, the browser lanes and the Linux GTK smoke (DD1)
- [x] `macos-probe-prepare` — the `macos-packages.yml` stub PR, the probe job for P1-P9 (the product `.app` plus a minimal probe `.app`), the first-paint series and the report-only `otool` read, rehearsed by execution on Linux (DD9-DD11)
- [x] `macos-probe-run` — one dispatch, the evidence read, the apparatus settled (Accessibility, or the test seam), the first-paint cause classified
- [x] `macos-probe-rerun` *(added 2026-10-25)* — the probe's delegate signatures fixed and re-run (dispatch 2): the subclass route, `NSTerminateLater` with a delivered `callAfter` reply, Cmd-Q on path T, reopen
- [x] `macos-dock-mode` — the dock mode, reopen, both quit paths (terminate with `NSTerminateLater`; stop with `begin_quit` and the geometry save), `boot_stopped`, `activate` on the main thread, App Nap, the native visibility read, the pywebview canary, the desktop test seam if leg 3 needs it, and any shell first-paint fix with its Linux VM check (DD2-DD5, DD9, DD11)
- [x] `macos-runtime-seam` — the interpreter `PATH` walk and the Command Line Tools stub, the login-shell `PATH`, the static additions, and every `doctor` change (the `PATH` source, the runtime list, `tray: dock`, the darwin `desktop shell` gate) (DD2, DD6, DD7)
- [x] `macos-recipe` — `app_id` and `[macos]` in `product.toml`, the Info.plist from `render.py`, the version mapping, `build.sh` CLI, the drag-install `.dmg`, `audit.py`, the full workflow with `lifecycle.sh`; rehearsed by execution (DD8-DD10, DD13)
- [x] `macos-hosted-checks` — dispatches within the budget, fixes, then `docs/macos-install.md`, README, the `CLAUDE.md`/`agents.md` sections, the contributor checklist and `tests/behavior/macos-app-install.md` (draft) from the evidence (DD12-DD14)
- [x] `macos-hat` *(optional)* — the operator reviews the screenshot series, the `.dmg` and the guide; decisions are logged

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated

### Verification
- `make test-unit`, `make test-browser` (`THE_ONE_TEST_NETNS=1`) and ruff, all passing.
- Leg 1's GTK smoke test on both Linux baselines.
- A hosted `macos-packages.yml` run: strict `doctor`, the audit, the signature, the `.dmg` layout and `lifecycle.sh`, all PASS, with its run id in the flight log.
- `tests/behavior/macos-app-install.md` drafted, for the contributor run at mission close (Flight 4).
