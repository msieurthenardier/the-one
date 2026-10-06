# Flight: Window Chrome

**Status**: in-flight
**Mission**: [Workbench Navigation and Control Library](../../mission.md)

## Contributing to Criteria

- [ ] **SC9 — The window belongs to the product.** In the packaged Windows desktop app:
  - the frame matches the workbench in both themes and follows theme changes;
  - dragging, snapping, minimize, maximize, close and close-to-tray keep working;
  - the app opens at a size the workbench fits.

  *Flight 5's part:* it ships the code and verifies it with a crew agent on a test copy on
  the operator's desktop (the new `windows-window-chrome` spec). SC9's own wording is
  "verified by the operator in the packaged app", so the criterion stays open until the
  operator walks the packaged build at Flight 6 (DD11).
- [ ] **SC10 — Operable and regression-safe** (this flight's surfaces). The theme change
  that drives the frame adds no new control. The unit and browser suites, the UI guards
  and the existing desktop tests pass.
- **Known Issue: Ctrl K in WebView2** (carried from Flight 4 DD9). It is verified with real
  OS key input in the test copy (DD9). The operator re-confirms it in the installed build
  at Flight 6.

---

## Pre-Flight

### Objective

The desktop window should look like part of the workbench. Today it has the stock Windows
title bar, white or default grey in both themes, and it opens at 800×600, which is below
the workbench's 1024px supported minimum. After this flight:
- the native Windows title bar takes the workbench's colours and follows every theme
  change, including Auto when the OS theme flips;
- the first frame is already in the right colours;
- the app opens at about the board's 1440×900, fitted to the screen.

Everything the native frame gives for free stays: drag, Aero Snap and snap layouts
(including thirds), minimize, maximize, close and close-to-tray.

### Open Questions

None block planning. The spike in leg 1 settles every item that rests on an unverified
Windows behaviour, and each one has a decided fallback (see Adaptation Criteria).

- [x] **Custom title strip or tinted native bar?** Tinted native bar. The operator chose
  "Tinted Windows bar" on 2026-10-06 (DD1).
- [x] **How does the crew see a real Windows window?** Through a test copy on the
  operator's desktop. The operator chose "Test copy on my desktop" on 2026-10-06 (DD10).
- [x] **Which colours?** The rail and list column's `--surface` for the caption (DD2).
  This is a preview question (DD12), not a blocker.
- [x] **Enforce the 1024 minimum width?** No. It would block Windows' snap thirds and, on
  smaller screens, halves, and SC9 requires snapping to keep working. The floor is a
  small sanity minimum (DD6). This is also a preview question (DD12).

### Design Decisions

**DD1: A tinted native title bar, not a custom strip.**
- **Choice.** Keep `frameless=False` and tint the native caption through
  `DwmSetWindowAttribute` on the window's HWND. No custom HTML title strip, no
  `IsNonClientRegionSupportEnabled`, and no pywebview upgrade (5.4 stays pinned,
  `pyproject.toml` `gui` extra `>=5,<6`).
- **Rationale.**
  - The mission asked for a spike of WebView2's non-client regions. Research answered it
    without one. The setting is in pywebview 5.4's bundled SDK (1.0.2957.106), and
    windowed hosting would get drag by default. But a frameless form loses native edge
    resize. Snap layouts need either the WebView2 window-controls overlay
    (prerelease-only) or host `WM_NCHITTEST`, and neither is available. SC9 requires both
    to keep working.
  - Mission 15 already reverted frameless chrome (inert drag, dead `js_api` buttons, lost
    resize). The operator's 2026-06-17 decision made native-frame-first the standard.
  - The operator chose the tinted bar on 2026-10-06.
- **Reachability.** `window.native` is the WinForms `BrowserForm`, and `.Handle` is the
  HWND. pywebview itself calls `DwmSetWindowAttribute` on it (5.4 `platforms/winforms.py`,
  border colour during fullscreen). The operator's Windows is build 26200, at or above
  the 22000 floor for the colour attributes.

**DD2: The colours come from the workbench tokens, pinned by a test.**
- **Caption** (`DWMWA_CAPTION_COLOR`, 35) = `--surface`, the rail and list column's
  colour: light `#fafafa`, dark `#17181c`.
- **Title text** (`DWMWA_TEXT_COLOR`, 36) = `--fg` while active (light `#18181b`, dark
  `#ededf0`). For the inactive window, see DD5.
- **Border** (`DWMWA_BORDER_COLOR`, 34) = `--border` (light `#e4e4e7`, dark `#26272c`) in
  both states.
- **Dark mode** (`DWMWA_USE_IMMERSIVE_DARK_MODE`, 20) = 1 for dark and 0 for light, so
  the caption buttons' glyphs contrast with the caption.
- **Encoding.** DWM takes a COLORREF `0x00BBGGRR`, so `#17181c` becomes `0x001C1817`.
- **One source.** The Python palette repeats hex values from `tokens.css`. A unit test
  asserts that **every** hex value the Python palette holds equals its token, for both
  themes. That covers the caption, text, inactive text, border and background (`--bg`,
  DD4), plus the splash's secondary text (`--fg-secondary`) and bar (`--border`). It parses `tokens.css` through the existing
  `tests/_ui_guard_helpers.py::parse_tokens_css_theme_blocks`, so a token change cannot
  silently leave the frame behind.
- **Platform gating.**
  - The build number comes from `sys.getwindowsversion().platform_version[2]`, the running
    OS. `.build` reports the version the exe's manifest declares, which differs between
    `python.exe` and the PyInstaller bootloader.
  - That is kernel32's file build. On this 25H2 enablement-package host it likely reads
    26100, while the registry says 26200. Gating at 22000 is unaffected. Nothing compares
    it with the registry build.
  - Build 22000 or later: all four attributes.
  - An older Windows build: attribute 20 only, best effort and untested (no such host).
  - Not Windows: no DWM call.
  - Every call's HRESULT is logged and kept for `GET /api/window/chrome` (DD3).

**DD3: The page tells the shell its theme over HTTP, and no post is ever lost.**
- **Why a channel.** The server does not know the theme. It lives in the page's
  `localStorage` and `prefers-color-scheme` (`theme.js` `apply()`, the one choke point).
  `js_api` failed in Mission 15 and was never diagnosed, so it is not used.
- **The route.** `POST /api/window/chrome` with body `{"theme": "light" | "dark"}`.
  - It mirrors `POST /api/window/focus` (`the_one/interfaces/web/app.py` `window_focus`)
    by lazy-importing a shell hook, so the web app stays importable without the GUI stack.
  - Unlike `window_focus`, it is a plain `def` route, so FastAPI runs it in its
    threadpool. A DWM or `Invoke` call then cannot block the event loop that serves the
    chat WebSockets.
  - It sits behind the existing credential gate, like every other route.
  - The body is validated as a `Literal`, so any other value gets a 422.
  - It returns `{"theme": str, "desktop": bool, "tinted": bool}`:
    - `desktop` is true when a desktop session is running in this process;
    - `tinted` is true when the DWM attributes were applied to a registered window.
- **The read-back.** `GET /api/window/chrome` (also plain `def`) returns:
  - the requested and the last applied theme;
  - whether caption colours are supported;
  - the Windows build;
  - each attribute's last HRESULT.

  This is the behavior test's read path for "the call ran and succeeded". The pixels are
  the other half (DD10).
- **The shell side** (`the_one/interfaces/desktop/chrome.py` state, hook in `shell.py`).
  1. `DesktopSession.run` **enables** the chrome state with its data dir before the server
     starts. In serve mode it is never enabled.
  2. `set_window_theme(theme)`, beside `focus_window()`:
     - always records the theme as **requested**;
     - when enabled, writes it to `{data_dir}/window-chrome.json`, on every platform;
     - when a window is registered on Windows, applies DD2's attributes.

     It never raises into the HTTP handler; failures are logged, as `focus_window()`
     does.
  3. The main window is **registered** with the chrome state right after `create_window`
     returns, before `show()` (DD4). Registration applies the requested theme if one has
     arrived, else the launch theme. A post that beats registration is therefore applied,
     not lost.

     `_desktop_window` (focus, tray) keeps its current assignment point. The chrome
     registration is separate and earlier.
  4. **Every DWM apply runs on the WinForms UI thread.**
     - Requests and registration reach it through `window.native.Invoke`; DD5's
       activation handlers are already on it.
     - The UI thread is therefore the only applier, which serialises applies with the
       activation handlers by construction.
     - Each apply uses the tracked activation state (DD5), never an assumed "active".
  5. **The lock guards state only:** enabled, requested, registered, active and last
     applied. It is never held across `show()`, `Invoke` or any Win32 call that can wait
     on the UI thread. Holding it there could deadlock the GUI thread, because an
     `Activated` event fired by `show()` would wait on it.
  6. **The HWND is read at apply time.**
     - On the UI thread, after checking `IsHandleCreated and not IsDisposed` (reading
       `.Handle` otherwise creates one), then `IsWindow`.
     - It is not cached forever, because WinForms may recreate the handle during the
       hidden path.
  7. **Each launch starts clean.** `DesktopSession.run` resets the chrome state, as it
     resets `_desktop_window`.
  8. **The file is written safely.** `window-chrome.json` is written atomically (a temp
     file, then replace), and a missing or corrupt file loads as "no file". A crew
     session's hard kill can land mid-write.
- **The page side** (`theme.js`):
  - **Gate.** It posts only inside a desktop webview. That is `window.chrome &&
    window.chrome.webview` (WebView2: present from document start, because pywebview sets
    `IsWebMessageEnabled`) or `window.pywebview` (any pywebview backend, after injection).
    A plain browser tab, including one pointed at the desktop app's own server, never
    recolours the desktop window.
  - **When.** On every `apply()` whose resolved theme differs from the last theme
    successfully sent: the initial load, `App.theme.set`, OS flips in Auto and the
    cross-tab `storage` path.
    - A `pywebviewready` listener, registered in `<head>` before pywebview injects, does
      the same check, so it posts on backends with no `chrome.webview`.
    - On WebView2 it finds the theme already sent and does nothing.
  - **Order.** One post is in flight at a time, and later changes coalesce to the latest
    theme. A theme counts as sent only on a 2xx. A failed post is retried once on the
    next `apply()` or after 2 seconds, then left. The frame keeps its last colour, and the
    page never shows an error for it.
- **Persistence lives in a separate file.** `window-state.json` is rewritten whole by
  `save_state()` on the GUI thread (close and quit). A theme key in the same file, written
  from a request thread, could be lost to that race. `window-chrome.json` has one writer
  under the lock.

**DD4: The first frame is already in the right colours.**
- **The launch theme** is the one in `window-chrome.json`.
  - On a first launch there is no file. On Windows the shell reads the OS app theme
    (`HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\
    AppsUseLightTheme`).
  - Elsewhere, or if the value cannot be read, it uses dark, which is `theme.js`'s own
    fallback.
  - A fresh install's page preference is Auto, which follows the OS, so on Windows the
    guess matches the page.
- **The main window:**
  - It is created with `background_color` = that theme's `--bg` (`#ffffff` or `#101114`).
    Today the default `#FFFFFF` flashes white before a dark page paints.
  - It is created with `hidden=True`, registered with the chrome state, tinted, then
    shown with `show()`.
  - The reason: pywebview 5.4 shows the main window inside `create_window` (it is created
    after `start()`), so a `before_show` handler cannot run first. The hidden path is
    pywebview's own (opacity 0, Show, Hide, opacity 1).
  - `Window.show()` waits on `events.shown` and raises after 20 seconds. Leg 1 confirms
    that `shown` fires on the hidden path.
  - The hidden path's Show then Hide may hand activation to another window. Leg 1 checks
    that after `show()` the main window is active (premise 4). If it is not, the shell
    activates it on the UI thread.
  - `show()` and `Invoke` are never called under DD3's lock.
- **The splash** is frameless, so it has no caption.
  - Its `background_color` and its HTML (`_splash_html(theme="dark")`, keeping the default
    for existing callers) follow the launch theme: background `--bg`, text `--fg`, and the
    status line and loading bar from the same theme's secondary text and border tokens.
    This replaces the hard-coded `#0f1117`, `#6b7280` and `#1e2130`.
  - On Windows the splash also gets DD2's border colour. It is applied in
    `splash.events.before_show`, which runs on the UI thread before the first `Show`;
    that works because the splash is created before `start()`.
- **A wrong guess** (the page resolves a different theme from the persisted one, for
  example after the OS flipped while the app was closed) is corrected by the page's first
  post. That post now always lands (DD3).
- **Known one-off.** The first launch after an upgrade has no `window-chrome.json`. An
  operator with a Dark preference on a light OS sees a light frame and a white page area
  once, until the page posts. The revised operator spec says so (leg 4), so Flight 6 does
  not log it as a defect.

**DD5: An inactive window still looks inactive.**
- **The problem.** Windows dims an inactive window's title text by default. A custom
  `DWMWA_TEXT_COLOR` may hold for both states, and then the operator cannot tell which
  window is active.
- **The target.** When the window loses focus, the title text changes to `--fg-muted`
  (light `#6e6e77`, dark `#85878f`). The caption and border stay the same.
- **The mechanism is committed: activation tracking.** It does not depend on what DWM
  happens to do on this host.
  - The shell subscribes to the form's `Activated` and `Deactivate` events through
    pythonnet.
  - Each handler records the active state (under DD3's lock, state only) and re-applies
    attribute 36 on the UI thread.
  - Every apply, including a theme change while the window is in the background, uses
    the tracked state. A post that arrives while the window is inactive therefore sets
    the new theme's `--fg-muted`, not the active colour.
  - The handlers catch every exception, so none reaches the WinForms message loop.
- **Leg 1's premise 7** records what DWM does by itself, as information only.

**DD6: The window opens at about the board's size, and snapping keeps working.**
- **Units.** All sizes here are logical pixels at 96 DPI. pywebview passes width, height
  and `min_size` to a form with `AutoScaleMode.Dpi`. `webview.screens` is read before
  `start()` calls `SetProcessDPIAware`, so at 100% scaling (the operator's) logical and
  physical are the same. Scaling above 100% is untested and recorded for Flight 6.
- **First launch** (no `window-state.json`):
  - an **outer** size of 1440×900, close to the board's 1440×900 viewport (reference spec,
    "Viewport the board assumes"); the viewport is then at least 1280 wide, so the agent
    drawer pushes and is open by default, matching the design;
  - fitted to a work area:
    - on Windows (`sys.platform == "win32"`, not merely "`frame` is set"), the first
      screen's `frame`, a .NET `Rectangle` holding `Screen.WorkingArea`. Its values are
      checked to be numbers, because test mocks create `.frame` on access;
    - elsewhere, the first screen's bounds less 64px. On GTK, `frame` is the monitor
      geometry, not a work area;
  - **no `x` or `y`**, so pywebview uses `CenterScreen`.
    - This also avoids pywebview's scale-factor multiplication of explicit coordinates.
    - `CenterScreen` centres on the screen under the mouse, which matters only with
      several monitors; that is noted for Flight 6.
- **Minimum size: a sanity floor of 640×360**, not the 1024 supported minimum.
  - It is below every Windows 11 snap-layout cell on a 1366×768 or larger screen (thirds
    of a 1920 work area are 640 wide, and quarters of 1366×728 are 683×364).
  - Enforcing 1024 would block thirds on the operator's 2560 screen (853px) and halves
    below about 2080px. SC9 requires snapping to keep working.
  - The 1024 width stays the design's supported minimum, not an enforced one. Whether to
    enforce it is a preview question (DD12).
- **Restored geometry** keeps the operator's own size and position (the operator's
  current file holds a right-half snap at 1294×1399). WinForms' `MinimumSize` lifts
  anything below the floor. `clamp_to_bounds` still runs. The existing restore tests
  (1024×768) stay as they are.
- **Platform scope.** These rules apply on every platform. Linux is covered by unit tests
  only.

**DD7: Platform scope.**
- **The DWM tint** is Windows-only.
- **Everything else is cross-platform:** persistence (DD3), the launch theme, the themed
  splash and `background_color` (DD4), and the size rules (DD6). On Linux the launch theme
  is dark until the first post persists a theme, a one-off on first launch.
- **The hidden-then-show path is a Windows mechanism.**
  - On GTK in 5.4, `hidden=True` is ignored for windows created after `start()`, and
    `create_window` returns before the native window exists (`idle_add`). There the path
    is a harmless no-op.
  - Registration never reads `native` off Windows.
- **No pywebview 6.x.** Its `update_title_bar_theme()` follows the OS theme on
  `UserPreferenceChanged` and would overwrite an app-chosen theme.

**DD8: A `window chrome` gate in `the-one doctor`.**
- **What it reports.** A concrete value, per the probe contract in `the_one/agents.md`
  ("Probe contract", `report-what-you-got`):
  - the running build (DD2's source);
  - the HRESULT of a `DwmSetWindowAttribute` call with a NULL HWND, which proves the
    function loads and answers. An invalid handle returns an error code, which is
    expected.
- **The results:**
  - On build 22000 or later: `window chrome: OK — caption colours supported (build N,
    probe 0x…)`, in the doctor's real `name: OK — detail` line format.
  - On an older build: `… OK — dark mode only …`.
  - Off Windows: `skipped (not Windows)`.
  - It fails only when dwmapi cannot be loaded on Windows, which would be a packaging
    defect.
  - The detail is ASCII only, because the frozen CI lane's piped stdout is cp1252.
- **Scope and wiring.**
  - It runs on every Windows run, frozen or not.
  - `"window chrome: OK"` joins the needle lists in
    `ci/tasks/windows-installer-build.yml` and
    `.github/workflows/windows-installer.yml`. The latter's `windows-2022` runner is
    build 20348, which takes the dark-mode-only branch and still matches the needle.
  - Leg 3 runs CI's `foreach`/`Contains` check verbatim against the local frozen doctor's
    output.
  - The gate goes **last** in the gate list, after `file watcher`.
  - It stays unexercised in CI while Concourse is unreachable. The test copy's frozen
    build runs `doctor` locally (leg 3).
- **Existing tests.** `tests/test_doctor.py::test_gates_list_has_nine_names_ending_with_
  file_watcher` is renamed and inverted to ten, and CLAUDE.md's "ninth gate" wording
  follows.

**DD9: Ctrl K in WebView2 is verified with real OS input.**
- **The premise.** Ctrl K reaches the page. Microsoft lists Ctrl+K among the WebView2
  shortcuts that are always off. pywebview sets `AreBrowserAcceleratorKeysEnabled =
  False`, and disabled accelerators still propagate to web content. That is strongly
  supported but not yet observed.
- **The check.** In the test copy, a real key via `SendInput` (not a synthetic DOM event),
  with the test copy's window verified in front (DD10), opens the palette. The read path
  is CDP: `[data-testid="jump-to"]` open, with focus in `jump-to-input`.
- **Timing.** Leg 1 checks it on `main`'s code, where the palette already exists. The
  close gate re-checks it on the flight's build.
- **If it fails,** the flight adds a host-side `AcceleratorKeyPressed` pass-through as a
  new leg (Adaptation Criteria). Nothing is added otherwise.
- **The Known Issue** closes as crew-verified, with the operator's confirmation in the
  installed build at Flight 6.

**DD10: The apparatus is a test copy on the operator's desktop.**
- **Where it runs.** `powershell.exe` from WSL runs in the operator's interactive
  session 1 (verified at planning). A crew agent:
  - builds and launches a copy of the branch under test from a scratch root
    (`%LOCALAPPDATA%\Temp\the-one-f5\`);
  - drives it;
  - captures it;
  - stops it.
- **The helper.** `scripts/windows_test_copy.py` (leg 1) wraps the steps. Its precedent is
  `scripts/webkitgtk_probe.py`, including that file's refusals. Its subcommands:
  - **`setup`:**
    - copies the **working tree** (tracked plus untracked-not-ignored files, since leg work
      is uncommitted until the flight-end commit) into the scratch root;
    - creates a venv there from `C:\Python311` (never installing into `C:\Python311`
      itself);
    - installs **the CI build's own closure, verbatim**: `uv export --no-dev
      --no-emit-project --extra gui --extra all-llms --format requirements-txt`, then
      `pip install -r … --no-deps`, then `pip install -e . --no-deps`
      (`ci/tasks/windows-installer-build.yml` steps 1–2);
    - is re-runnable: Storage Sense can purge `%LOCALAPPDATA%\Temp` during a multi-day
      flight, so `launch` checks that the venv or dist exists and says to re-run `setup`;
  - **`freeze`:** a PyInstaller one-dir build from `packaging/windows/the-one.spec` (step
    3 of the same task, without Inno);
  - **`launch`:**
    - from source (`pythonw.exe -m the_one app`) or frozen (`the-one-app.exe`);
    - working directory set to the scratch root;
    - no `-WindowStyle Hidden`, because the startup show flag would hide the splash;
  - **`capture`, `pixel`, `rect`, `keys`, `click`, `drag`, `front`, `own-window` and
    `stop`.**
- **Act paths:**
  - **Launch:** `Start-Process` with `THE_ONE_PORT`, `THE_ONE_DATA_DIR` and
    `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=<p>`, set only in the
    launching PowerShell process.
    - The variable is the only channel. With `storage_path` set, pywebview 5.4 builds the
      environment with `CreateAsync(userDataFolder=…)` and no options, so its own
      `AdditionalBrowserArguments` (and `settings['REMOTE_DEBUGGING_PORT']`) are never
      applied.
  - **OS-level input:** keys and mouse through `SendInput`, for Ctrl K, caption
    double-click, caption drag, minimize and ×.
  - **Page actions:** through CDP on the WebView2 debugging port. WSL networking is
    mirrored, so `127.0.0.1` reaches it. This covers clicking Settings › Appearance and
    emulating `prefers-color-scheme` for the Auto check, in one CDP session per run.
- **Observe paths:**
  - **The frame's pixels:** `CopyFromScreen` of the window rect, after the occlusion
    check below. That is what is actually on screen. An inactive-state capture (spec
    step 5) needs no foreground check. `PrintWindow` may render a classic frame, which leg
    1 checks (premise 11).
  - **The window rect:** `GetWindowRect`.
  - **The page:** CDP (DOM, accessibility tree, screenshot, `innerWidth`).
  - **The DWM call:** `GET /api/window/chrome`.
  - **Serving:** `/api/info` with the scratch credential, which proves the copy serves on
    the requested port and `_select_port` did not fall back.
  - **Files:** `window-chrome.json` and `window-state.json` in the scratch data dir.
- **Input safety on a live desktop.** `SendInput` goes to whatever window is in front or
  under the cursor, and the test copy has the installed app's title (and, frozen, its exe
  name and icon). So:
  - **Window identity.** Windows are found only through the recorded process tree, never
    by title or exe name.
    - The tree is the launched PID plus all its descendants. From source, the venv's
      `pythonw.exe` is a launcher that starts the real `C:\Python311\pythonw.exe` as a
      child. The frozen one-dir build is a single process.
  - **Keys.** Before every injected key, the helper refuses unless `GetForegroundWindow()`
    belongs to the recorded tree.
  - **Pointer input.** Before every click, double-click or drag, the helper refuses unless
    `WindowFromPoint(target)` belongs to the recorded tree or to the helper's own window.
    There is no foreground check for pointer input, because a click is how a window is
    brought to the front.
  - **Occlusion check.** Before sampling, the helper checks that the sample points are not
    covered (`WindowFromPoint` at each point).
  - **Bringing the window to the front, and launching visibly.** A window launched through
    WSL interop may open behind the operator's active window, and `SetForegroundWindow`
    from a background process fails silently.
    - The technique for both input and launch-time visibility is leg 1's premise 13,
      decided and recorded. One candidate: launch while a helper-owned window is in
      front, since a process started by the foreground process may take the foreground.
    - No candidate may send input to a window the test copy or helper does not own. That
      excludes the common Alt-keypress trick before `SetForegroundWindow`.
    - If nothing works for input, the helper stops and asks rather than injecting.
    - If launch-time frames cannot be seen, steps that judge first paint fall back as the
      spec states.
  - **Hands off.** The helper records the tick of its own last injection. Only input newer
    than that counts as the operator's.
    - If `GetLastInputInfo` shows operator input in the last 5 seconds, the helper waits,
      up to a limit, then stops and reports.
    - It checks once before a compound gesture (a drag, a double-click, Ctrl+K then Esc),
      never between its events.
    - Each session starts and ends with a one-line notice to the operator in the Flight
      Director's chat.
  - **The inactive state.** It uses a small window the helper itself owns.
- **Other safety rules** (in the helper and in every crew prompt):
  - **Ports and data dirs.** The helper refuses ports 8484 and 8485. The operator's
    installed `the-one-app.exe` runs on 8484 in session 1. It also refuses any data dir
    at, inside or containing the operator's Windows data dir. It resolves that dir at run
    time through platformdirs in the Windows venv and cross-checks it against
    `%LOCALAPPDATA%\the-one`; it never guesses.
  - **Shared ports.** With mirrored networking, WSL and Windows share one localhost port
    space. The helper checks that the app port and the debugging port are free on both
    sides before launching.
  - **`.env`.** A frozen build reads `.env` from the operator's default data dir whatever
    `THE_ONE_DATA_DIR` says (`the_one/config.py`). The helper re-checks for one at every
    frozen `launch` and refuses if it is present.
  - **WebView2 variables.** It never sets `WEBVIEW2_*` user- or machine-wide (`setx`),
    which would reach the installed app's next launch.
  - **Stopping.**
    - It records PIDs at launch in the scratch root and stops only those, with their
      process tree, never by name pattern.
    - It kills the app's interpreter first (not the venv launcher) and lets
      `msedgewebview2` exit on its own.
    - `stop` returns only when the whole recorded tree has exited and the app and
      debugging ports are free, within a bounded wait. A lingering `msedgewebview2`
      holds the user-data-folder lock and the CDP port, and would make the next launch
      fail.
    - A watchdog stops the recorded PIDs if a session overruns.
    - A hard kill leaves a ghost tray icon until it is hovered; this is noted, not fixed.
  - **A snapshot of the operator's data.** Before and after each session, the helper
    records:
    - the installed app's PID and start time;
    - the existence, mtime and hash of `api-credential`, `.env`, `window-chrome.json` and
      `window-state.json` in the operator's data dir.

    Any change fails the session, with two exceptions, which are reported, not judged:
    - `window-state.json` changing because the operator closed the installed app or sent
      it to the tray (both save geometry);
    - a new PID because the operator restarted the installed app.
  - **Each session also records:**
    - the WebView2 runtime version, the DPI and the networking mode;
    - the OS app and system themes (`AppsUseLightTheme`, `SystemUsesLightTheme`);
    - accent colour on title bars (`DWM\ColorPrevalence`) and `EnableTransparency`;
    - any `WEBVIEW2_*` variables already set user- or machine-wide.

    These can change what the border, the glyphs and the inactive caption look like. A
    locked session (captures come back black) is reported, not judged.
- **Consent and intrusion.** The operator chose this on 2026-10-06. Sessions are short,
  and windows and the second tray icon go away at the end.
- **No Concourse path.** Concourse was unreachable at planning (`fly` against
  `localhost:8080` timed out), and its Windows worker runs as LocalSystem in session 0,
  where no window can be shown. The local freeze replaces `fly execute`.

**DD11: Who verifies what.**

| Check | Verified by |
|---|---|
| Palette, COLORREF, build source, gating, persistence, the requested-theme race, OS-theme fallback, first-paint order, size maths, route shape | Unit tests with a mocked `webview` and ctypes (existing pattern in `tests/test_window_state.py` and `tests/test_desktop_shell.py`) |
| The page posts on each resolved change only inside a desktop webview, one at a time, coalesced | A browser test (`settings` lane) with two stubs: `chrome.webview` at document start, and `window.pywebview` injected late plus a dispatched `pywebviewready` (the real order). A plain page posts nothing. |
| The frame's colours in both themes, live switching, Auto with an emulated OS flip, inactive dimming, first paint, first-launch size, native maximize, minimize, drag and ×-to-tray, Ctrl K | The crew spec `windows-window-chrome` on the test copy (the frozen build at the close gate) |
| The look in real use, a **real** OS theme flip, snap layouts (halves, thirds), Win+arrows, a fresh install and an upgrade with an existing `window-state.json`, splash continuity, scaling above 100% | The operator, at Flight 6, in the packaged build (`windows-native-frame-splash`, revised in leg 4) |

A real OS theme flip changes the operator's whole desktop, so the crew emulates it in the
page instead and leaves the real flip to the operator.

**DD12: A non-blocking operator preview.**
- **When.** After leg 3, with captures of the test copy in both themes: active and
  inactive, the splash, and the first-launch size.
- **The questions,** in what-you-see terms:
  - "the title bar is the sidebar's colour; should it match the main pane (white or
    near-black)?";
  - "the inactive title text is grey; is that enough to tell the windows apart?";
  - "the app opens at 1440×900 in the middle of the screen; is that right?";
  - "the window can be made as narrow as Windows' snap thirds; should it refuse to go
    narrower than 1024 instead, which would stop thirds snapping?"
- **Not a blocker.** The close gate does not wait for answers. Answers before the PR
  merges become a leg, as at Flight 4 leg 9. Later ones go to Flight 6.

**DD13: Carried items.**
- **Shortcuts.** This flight adds no keyboard shortcut. Any future desktop shortcut goes
  through `App.shortcuts`, and none is needed here.
- **The drawer.** The native caption is outside the page, so the static `#chat-drawer`
  slot and `--drawer-w` are untouched. DD6's default size puts first launch in the
  drawer's push mode.
- **The `agents.md` footgun note** (`the_one/agents.md`, "pywebview frameless
  custom-chrome footgun") is corrected for 5.4 in leg 2:
  - `.pywebview-drag-region` listeners attach on every platform, but only to elements
    present when pywebview injects its script, and the move is a JS `window.move()`, not a
    native move loop;
  - `easy_drag` never fires in 5.4, because of a `'True'`/`'true'` string mismatch;
  - `app-region` works in WebView2 only when `IsNonClientRegionSupportEnabled` is on,
    which pywebview leaves off.

  The conclusion, native frame first, stands.

### Citation Audit

Checked against `b044cab` on 2026-10-06, then spot-checked by both design-review cycles
(all matching after cycle 2's two drift fixes):
- **`the_one/interfaces/desktop/shell.py`:**
  - `_desktop_window = None` (line 24), assigned near the end of `_boot` (around line 721,
    after the tray wiring);
  - `_splash_html` (line 109, no parameters today; called with none by
    `tests/test_desktop_shell.py`) and `background: #0f1117` (lines 51 and 143);
  - `focus_window` (line 313);
  - in `DesktopSession.run`:
    - `_create_kwargs = {"frameless": False, "resizable": True}` and the `clamp_to_bounds`
      restore (lines 583–608);
    - the splash `create_window` (lines 615–621);
    - `_boot` with `create_window("GleepGlorp AI", url, **_create_kwargs)` (line 691);
    - `webview.start(_boot, private_mode=False, storage_path=...)` (lines 743–747).
- **`the_one/interfaces/desktop/window_state.py`:** `_state_path`, `load_state`,
  `save_state` (rewrites the whole file), `clamp_to_bounds`.
- **`the_one/interfaces/web/app.py`:** `@app.post("/api/window/focus")` `async def
  window_focus` (line 2619).
- **`the_one/interfaces/web/static/js/theme.js`:** `apply(theme)`, `reapply()`, the media
  listeners, the `storage` listener, `App.theme.set`.
- **`the_one/interfaces/web/static/css/tokens.css`:** dark `--bg`, `--surface`,
  `--border`, `--fg` and `--fg-muted` (lines 73–95); light (lines 220–238).
- **`tests/_ui_guard_helpers.py`:** `parse_tokens_css_theme_blocks` (line 600).
- **`the_one/diagnostics.py`:** `run_doctor` (line 848); the `desktop shell` probe
  (lines 128–166).
- **`tests/test_doctor.py`:** `test_gates_list_has_nine_names_ending_with_file_watcher`
  (line 867).
- **`ci/tasks/windows-installer-build.yml`:** the doctor needle list (line 113); the
  closure commands (lines 65–90).
- **`.github/workflows/windows-installer.yml`:** the GitHub fallback's doctor smoke
  (`windows-2022`, `v*` tags only).
- **`tests/test_window_state.py`:** `test_run_desktop_no_state_uses_defaults` (line 432)
  pins "no width or height when state is absent", and leg 3 inverts it.
- **`the_one/agents.md`:** the footgun note (lines 66–74); the doctor "Probe contract".
- **`tests/behavior/windows-native-frame-splash.md`:** the stale step 9 (its Preconditions
  "Known gap").
- **`missions/25-workbench-navigation/reference/reference-spec.md`:** "Viewport the board
  assumes | 1440 × 900" (a viewport; DD6 uses it as an outer size, on purpose).
- **pywebview 5.4** (from the locked wheel):
  - `winforms.py`: `BrowserForm` sets `native` (lines 162–167); size, `MinimumSize` and
    `AutoScaleMode.Dpi` (lines 170–174); explicit `x`/`y` multiplied by the scale factor,
    else `CenterScreen` (lines 177–198); the hidden path (lines 658–662);
    `SetProcessDPIAware` (line 678); `get_screens` with `frame=WorkingArea` (line 940);
  - `edgechromium.py`:
    - `IsWebMessageEnabled=True`;
    - injection on every `NavigationCompleted`;
    - with `storage_path` set, `CreateAsync(userDataFolder=…)` and no environment options,
      so `AdditionalBrowserArguments` never applies (DD10);
  - `gtk.py`: `hidden` ignored for windows created after `start()`, and `create_window`
    through `idle_add` (DD7);
  - `__init__.py`: the `create_window` defaults 800×600, `min_size=(200, 100)`,
    `background_color='#FFFFFF'`.

### Prerequisites

- [x] Flight 4 merged (PR #220). The branch `flight/05-window-chrome` is at `main`
  `b044cab`.
- [x] **Windows host:**
  - build 26200 (25H2);
  - one 2560×1440 screen (work area 2560×1392), 96 DPI (100%);
  - the toolchain is `C:\Python311` (3.11.9, pip and uv) and Git for Windows;
  - WSL interop launches into session 1, and WSL networking is mirrored.
- [x] The operator consented to a test copy on their desktop (2026-10-06).
- [x] The installed app is PID 208344 in session 1 on 8484. Its data dir
  `C:\Users\cprch\AppData\Local\the-one` holds no `.env`. **Never touched.** This is
  re-checked at every session, not trusted from planning (DD10).
- [ ] The operator's session is unlocked, and the operator is not typing, during each crew
  session. Checked at the start of each session (DD10).
- [ ] The local freeze works and its time is known (leg 1). Concourse was unreachable at
  planning.
- [x] The 8485 Flight 4 preview instance is still up. Leg checks on Linux use 8486 and
  up, and Windows test copies use 8490 and up, with both sides checked for a free port.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [ ] Prerequisites verified, or explicitly deferred with a re-check point (session lock
  and the operator's data dir: at each session; local freeze: leg 1)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

- **A new module, `the_one/interfaces/desktop/chrome.py`.** It has no GUI import at
  module top level, so it is importable headless, as `window_state.py` is. It holds:
  - the palette (DD2) and `colorref()`;
  - `windows_build()`;
  - `apply_title_bar(hwnd, theme, active=True) -> dict`, returning an HRESULT per
    attribute;
  - `os_theme()` (winreg, with the dark fallback);
  - `load_theme()` and `save_theme()` for `window-chrome.json`;
  - the module state: enabled, requested, registered window, last applied, the lock.
- **`shell.py`:**
  - `set_window_theme()` beside `focus_window()`;
  - in `DesktopSession.run`:
    - enable the chrome state;
    - read the launch theme before the splash;
    - the themed splash (`background_color` and HTML);
    - `background_color` and `hidden=True` on the main window;
    - register, tint, `show()`;
    - activation wiring if DD5 needs it.
- **`app.py`:** `POST` and `GET /api/window/chrome`, both plain `def`.
- **`theme.js`:** the gate, the single in-flight post with coalescing, and the
  `pywebviewready` listener (DD3).
- **`shell.py` (size):** the first-launch size from the work area and `min_size` (DD6).
- **`diagnostics.py`:** the `window chrome` probe (DD8), plus the CI needle.

### Checkpoints

- [ ] Leg 1 findings recorded (the spike's thirteen premises). The Flight Director amends
  legs 2 and 3 before designing them.
- [ ] Leg 2: the frame follows the theme in the from-source test copy, in both themes,
  live, with no lost first post.
- [ ] Leg 3: first launch at 1440×900 centred and the doctor gate, in the test copy.
- [ ] The flight-end review confirmed, with one commit.
- [ ] The DD12 preview published (non-blocking).
- [ ] **The close gate:**
  - `windows-window-chrome` passes on the frozen test copy;
  - the unit suite passes;
  - the `settings` and `shared` browser lanes pass;
  - the UI guards pass.

### Adaptation Criteria

**Divert if:**
- **The colours have no effect.** If the DWM colour attributes do nothing visible on a
  pywebview 5.4 window on this host, stop, record the finding and ask the operator: dark
  mode only (attribute 20), or a custom strip with its losses (DD1).
- **The hidden path breaks things.** If `hidden=True` followed by `show()` breaks the
  splash dismissal, close-to-tray, the geometry save or `events.shown`, fall back to
  creating the window shown and tinting it immediately. Accept a brief default caption,
  and record it.
- **The window cannot be brought to the front safely.** If no technique for premise 13
  works, crew input steps cannot run unattended. Stop and ask the operator: either they
  click the test copy into focus when asked during a session, or input steps move to
  Flight 6.
- **Launch frames are hidden.** If WSL-launched windows cannot open unoccluded, the
  first-paint clauses of spec steps 1 and 7 are judged from `PrintWindow` captures when
  premise 11 shows that it renders the tinted frame. Otherwise they are marked
  inconclusive, not failed, and move to the operator at Flight 6.

**Acceptable variations:**
- **The page gate.** If `chrome.webview` is absent at document start in pywebview 5.4,
  rely on `window.pywebview` and `pywebviewready` alone, with registration-time
  application (DD3) covering the late first post.
- **Repainting.** A caption change may not repaint on a shown window. If so, add a frame
  redraw (`SetWindowPos` with `SWP_FRAMECHANGED`, or `RedrawWindow` with `RDW_FRAME`).
  This runs in the threadpool route, never on the event loop.
- **No local freeze.** If it is impractical (over about 20 minutes, or failing), the close
  gate runs on the from-source copy. The frozen-specific checks then rest on the CI
  `build-windows-installer` job's frozen doctor (the new needle) once Concourse is back,
  and on the operator's packaged build at Flight 6. The flight log records it.
- **Ctrl K.** If it does not reach the page in WebView2, add a leg for an
  `AcceleratorKeyPressed` pass-through (DD9).

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

> **In-flight change (2026-10-06):** `windows-apparatus` was split at its design review
> into **1a `windows-apparatus-core`** (no input; premises 5, 6, 8, 10 and 12) and
> **1b `windows-apparatus-input`** (input and captures; premises 1–4, 7, 9, 11 and 13).
> The flight log records the change. The original entry is kept below as its scope.

- [ ] `windows-apparatus` (spike plus apparatus), now 1a and 1b:
  - `scripts/windows_test_copy.py` with DD10's refusals and input-safety checks, and unit
    tests for the pure parts (ports, data-dir containment, PID ownership, the snapshot
    diff);
  - a from-source test copy and a frozen one-dir build, timed;
  - throwaway spike scripts (scratchpad, not product code) answering thirteen premises:
    1. the caption, text and border are visible in pixels, and so is the splash border;
    2. attribute 20's glyph legibility under the OS light theme;
    3. live repaint;
    4. hidden, then tint, then show: no flash, `events.shown` fires, and the main window
       is active afterwards;
    5. `window.chrome.webview` at document start, and `window.pywebview` and
       `pywebviewready` on the main window;
    6. the outer-to-viewport insets;
    7. the inactive caption without tracking (information only; DD5 is committed);
    8. a cross-thread `Handle` read, and whether the handle changes on the hidden path;
    9. Ctrl K through `SendInput` on `main`'s palette;
    10. CDP through `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` (the only channel; see
        DD10);
    11. what a capture needs, the locked-session result, and whether `PrintWindow`
        renders the DWM-tinted frame;
    12. the freeze time;
    13. bringing a WSL-launched window to the front reliably, for input and for
        launch-time visibility, within DD10's limits.
  - **Order within the leg.** First land and unit-test the parts that never inject input:
    the refusals, the snapshot, the process tree and `stop` with its wait. Then attempt
    injection.
  - **Unit tests** include a sibling-prefix case (`…\the-one-f5` against `…\the-one`),
    so containment compares path components, not string prefixes.
  - the recipe documented in `the_one/agents.md` "UI test apparatus".
  - **Risk:** high (a new apparatus that injects input on the operator's desktop). Design
    review.
- [ ] `tinted-title-bar`:
  - `chrome.py`;
  - `set_window_theme`, enable and register, and the first-paint order (DD3, DD4);
  - the themed splash;
  - DD5 per leg 1;
  - the route pair (DD3);
  - `theme.js` gate and posting;
  - unit tests, plus route and browser tests. The unit tests include:
    - post-before-registration;
    - a theme change while inactive, which gives the new theme's `--fg-muted`;
    - the lock never held across `Invoke`;
    - the atomic write and the corrupt-file load;
  - docs: an `agents.md` "Window chrome" contract, the footgun correction (DD13) and
    CLAUDE.md's desktop launcher paragraph;
  - test-copy verification in both themes.
  - **Risk:** high (a new route, and a change to the window lifecycle). Design review.
- [ ] `window-size-and-doctor`:
  - DD6's first-launch size and floor;
  - `test_run_desktop_no_state_uses_defaults` renamed and inverted to the new default;
  - the DD8 doctor gate, its test rename and the CI needle;
  - docs (CLAUDE.md's gate count, the doctor docs);
  - test-copy verification, including the frozen `doctor`.
  - **Risk:** low (additive, within `_create_kwargs` and the probe list).
- [ ] `specs-and-close`:
  - `windows-window-chrome` finalized against legs 1–3;
  - `windows-native-frame-splash` revised:
    - the stale step 9;
    - an operator-on-own-install precondition;
    - the SC9 steps for Flight 6 (including halves and thirds snapping, and the
      first-launch-after-upgrade one-off from DD4);
  - the doc sweep;
  - the gates;
  - the DD12 preview, then the Flight Director's close-gate behavior run on the frozen
    test copy.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing: the unit suite, the `settings` and `shared` browser lanes, and the UI
  guards (`theme.js` loads on every page, so `shared` runs in full)
- [ ] Documentation updated:
  - `the_one/agents.md`: Window chrome, the corrected footgun note, the Windows test copy,
    the doctor gate;
  - `CLAUDE.md`: the desktop launcher paragraph, the doctor gate count, the route
- [ ] The Known Issue "Ctrl K in WebView2" updated in `mission.md`
- [ ] The mission's "Window chrome mechanism" question closed
- [ ] SC9 left open for Flight 6, with Flight 5's part noted

### Verification

- **Unit:**
  - `tests/test_window_chrome.py` (new):
    - the palette against `tokens.css`;
    - COLORREF;
    - the build source and gating;
    - HRESULT capture;
    - persistence (enabled only);
    - the requested-theme race (post, then register, then applied);
    - the OS-theme fallback;
  - the route tests (new): 422, serve mode, a fake registered window, GET;
  - `tests/test_desktop_shell.py` and `tests/test_window_state.py`: first paint, the
    splash theme, size, floor;
  - `tests/test_doctor.py`: the tenth gate;
  - the existing `tests/test_window_focus.py` and `tests/test_desktop_tray.py` stay green.
- **Browser:** `tests/browser/test_flow_settings_window_chrome_signal.py` (new, `settings`
  lane), per DD11's two stubs and the plain-page case.
- **Behavior:**
  - `windows-window-chrome` (crew, Witnessed, on the frozen test copy) at the close gate;
  - `windows-native-frame-splash` (operator) at Flight 6.
- **Safety:** every crew session's before-and-after snapshot of the operator's data dir
  and installed app (DD10) matches, and the run logs record it.
