# Leg: tinted-title-bar

**Status**: completed
**Flight**: [Window Chrome](../flight.md)

## Objective

The desktop window's native Windows title bar takes the workbench's colours and follows
every theme change. Its first frame and the splash are already in the right colours, and
an inactive window's title text dims. This leg delivers flight DD2–DD5 and DD7: a new
`chrome` module, the page-to-shell route pair, the `theme.js` signal and the shell's
first-paint order, verified on the Windows test copy.

## Context

- **The flight's DD2, DD3, DD4, DD5 and DD7 are this leg's contract.** Read them in full,
  including DD3's numbered "shell side" list (the lock contract, UI-thread applies,
  registration before show) and its page-side gate and ordering rules. DD13's
  footgun-note correction is also in this leg.
- **Leg 1b's findings settle the open premises** (the flight log's Leg 1b entry and
  Flight Director Notes):
  - **P1:** the colours apply exactly through `DwmSetWindowAttribute` on the UI thread
    via `window.native.Invoke`, with HRESULT 0. The splash border applies in
    `before_show`.
  - **P2:** DWM chooses the caption-button glyph colour from the caption colour itself,
    so attribute 20 is kept for correctness only.
  - **P3:** a change repaints within about 8ms, so no frame redraw is needed.
  - **P4:** `hidden=True`, then tint, then `show()` gives no default-caption frame.
    `events.shown` fires at the hidden-creation flash, so `show()` does not block.
  - **P5:** `window.chrome.webview` exists at document start in both windows.
    `window.pywebview` is absent until `pywebviewready`, about 20ms after `load`.
  - **P7:** a custom text colour is **not** dimmed when the window is inactive, so DD5's
    activation tracking is required.
  - **P8:** the HWND is stable across hidden and shown, and `Handle` reads fine off the UI
    thread. DD3 still applies on the UI thread, which serialises applies with the
    activation handlers.
- **pywebview 5.4 facts:**
  - **Event threading.** `Event.set` runs a locked event's handlers synchronously and an
    unlocked event's on a new thread. A handler with a `window` parameter receives the
    window. `before_show` is locked, so it runs on the UI thread.
  - **The splash's `before_show`** fires inside `create()` on the UI thread for windows
    created before `start()`. That is the splash's case, never the main window's.
  - **Activation.** `BrowserForm` already subscribes `self.Activated` internally, and
    extra subscriptions through pythonnet (`form.Activated += handler`) are allowed.
- **No pywebview upgrade** (DD1, DD7). The tint is Windows-only. Persistence, the launch
  theme, the themed splash, `background_color` and the hidden-then-show order are
  cross-platform.
  - On GTK, `hidden` is honoured (`gtk.py`: not shown at creation). `Window.show()` is
    `@_shown_call`: it waits up to 20s on `events.shown`, then raises
    `WebViewException`. This is unverified on GTK, so `show()` is guarded (see Outputs).
  - Nothing reads `native` off Windows.
- **The delegate idiom.** Leg 1b's spike (`spike_dwm.py`) used pywebview's own
  `form.Invoke(Func[Type](fn))` (`from System import Func, Type`), as pywebview 5.4's
  `winforms.py` does throughout. This leg uses the same delegate, through
  `BeginInvoke` with a bounded wait (see Outputs).
- **The operator's OS app theme is Light** (`AppsUseLightTheme=1`; leg 1a's
  `doctor-host`). Test-copy check 1 still reads it first and sets its expectations from
  it.
- **The Windows test copy** (`scripts/windows_test_copy.py`, legs 1a and 1b) is the
  verification apparatus. The rules in `the_one/agents.md` "Windows test copy" apply,
  including the snapshot and focus brackets, hands-off, and identity-checked stops. The
  Flight Director notifies the operator before this leg's Windows session.

## Inputs

- Legs 1a and 1b's uncommitted work (the helper, its tests and docs).
- `the_one/interfaces/desktop/shell.py`:
  - `_desktop_window` (line 24);
  - `_SPLASH_TEXT_ONLY` and `_splash_html()` (lines 43–200: `#0f1117`, `#e8eaf0`,
    `#6b7280`, `#1e2130`);
  - `focus_window()` (line 313);
  - `DesktopSession.run()`: the state reset (lines 509–510), `_create_kwargs` (line 583),
    the splash `create_window` (line 615), `_boot` (line 641; `create_window` at line
    691, the `loaded` wiring at lines 696–702, `_desktop_window = main_win` at line 721).
- `the_one/interfaces/web/app.py`: `window_focus` (line 2619), the pattern for the new
  routes.
- `the_one/interfaces/web/static/js/theme.js`: `apply()` (line 51), the one choke point.
- `the_one/interfaces/web/static/css/tokens.css` and
  `tests/_ui_guard_helpers.py::parse_tokens_css_theme_blocks` (line 600).
- **Tests:**
  - `tests/test_desktop_shell.py`: the `webview_mock` fixture (line 58),
    `_make_splash_mock` (line 353), `_EventCapture` (line 463), the `_boot` tests
    (lines 489–686), the `_splash_html` tests (lines 928–990);
  - `tests/test_window_focus.py`: the route test pattern.

## Outputs

- **`the_one/interfaces/desktop/chrome.py` (new).** It has no GUI imports at module top
  level, and every `ctypes`, `winreg` and pythonnet use is lazy and Windows-gated. It
  holds:
  - `PALETTE`: per theme, `caption` (`--surface`), `text` (`--fg`), `text_inactive`
    (`--fg-muted`), `border` (`--border`), `bg` (`--bg`), `fg_secondary`
    (`--fg-secondary`);
  - `colorref(hex) -> int`, giving `0x00BBGGRR`;
  - `windows_build() -> int | None`, from `sys.getwindowsversion().platform_version[2]`,
    None off Windows;
  - `attribute_plan(theme, active, build) -> list[tuple[str, int, int]]` (name, attribute
    id, value), a pure function:
    - build 22000 or later: `dark_mode` (20), `border` (34), `caption` (35) and `text`
      (36, `text_inactive` when inactive);
    - an older build: `dark_mode` only;
    - None: an empty list;
  - `apply_title_bar(hwnd, theme, active, build) -> dict[str, int]`, giving each
    attribute's HRESULT, through `ctypes.windll.dwmapi.DwmSetWindowAttribute` (4-byte
    values);
  - `os_theme() -> "light" | "dark"`, from `HKCU\…\Personalize\AppsUseLightTheme`
    (1 → light, 0 → dark), and dark when unreadable or off Windows;
  - `load_theme(data_dir)` and `save_theme(data_dir, theme)` for `window-chrome.json`
    (`{"theme": "light"|"dark"}`). The write is atomic (a temp file in the same dir,
    then `os.replace`). A missing, corrupt or invalid file loads as None;
  - **the state**, behind one module lock that guards state only, per DD3 item 5. Its
    fields are `enabled`, `data_dir`, `requested`, `window`, `active` (default True),
    `last_applied` (theme, active, results, time) and `build`. Its functions:
    - `reset()`;
    - `enable(data_dir)`;
    - `request(theme) -> dict`;
    - `register(window, launch_theme)`;
    - `snapshot() -> dict`;
  - **the UI-thread apply.** The apply runs on the UI thread, called directly from the
    activation handlers (already on it). From any other thread (requests, registration)
    it goes through `form.BeginInvoke(Func[Type](fn))` plus a bounded wait of 2s on the
    result's `AsyncWaitHandle`.
    - It is skipped, and logged, when `chrome`'s own `closing` flag is set (by
      `deregister()`, cleared by `reset()`; `chrome` never imports `shell`), when the form
      `IsDisposed`, or when the state's window has been deregistered.
    - **The UI-thread function catches everything.** It has a top-level `try/except
      Exception` that logs and records the failure in `last_applied`. An exception in a
      `BeginInvoke`d delegate would otherwise reach `Application.ThreadException`.
    - The wait is a module constant, `_UI_WAIT_MS = 2000`, so tests can shorten it. A
      timeout is logged once, with the theme, so a `pending` on the test copy can be
      diagnosed. When
      the wait returns True, `EndInvoke` runs in a `finally`, which releases the async
      result.
    - An exception from `BeginInvoke` (a disposed form, or a message loop that has gone)
      is caught and logged, never raised.
    - A wait timeout returns with `tinted` reported as `pending`, and the apply still
      lands when the UI thread runs it.
    - A request thread therefore never blocks for long, even across Quit.
    - Inside it, the theme and active state are read **at apply time** (briefly under
      the lock), so the UI thread always applies the latest requested state, even when
      two requests race.
    - It reads the HWND only after `IsHandleCreated and not IsDisposed`, then checks
      `IsWindow`.
    - It records `last_applied`.
    - It never holds the lock across `Invoke` or a Win32 call.
  - **activation wiring** (Windows): `register` subscribes the form's `Activated` and
    `Deactivate`. Each handler sets `active` under the lock, then applies on the UI
    thread (it is already on it). Every handler catches everything, so nothing reaches
    the WinForms message loop.
  - `apply_splash_border(window, theme)`: the border colour only, for the splash's
    `before_show`.
  - `deregister()` is idempotent. It sets `closing` and clears the window, so a later
    request applies nothing. It is called before every destroy path:
    - `_on_quit`;
    - `_on_closing`'s allow-destroy returns (the `if _really_quit: return True` line and
      the `not hidden` return);
    - `_close_to_tray`'s no-tray fallback.
  - `native_show(window)`: the Windows-only native show fallback, `form.Show();
    form.Activate()` through the same bounded `BeginInvoke`. It is the named seam that
    tests replace.
  - **The snapshot.** `snapshot()` reports `pending: bool`, true while an apply is
    requested but not yet recorded (a request sequence number against an applied
    sequence number). `last_applied` carries `queued_at` and `applied_at`.
- **`the_one/interfaces/desktop/shell.py`:**
  - `set_window_theme(theme) -> dict`, beside `focus_window()`. It returns `{"theme",
    "desktop", "tinted"}` and never raises; it logs instead.
  - **In `run()`:**
    - `chrome.reset()` beside the existing state reset;
    - in the webview branch, before the splash:
      - `chrome.enable(settings.data_dir)`;
      - `launch_theme = chrome.load_theme(settings.data_dir) or chrome.os_theme()`;
    - the splash created with `html=_splash_html(launch_theme)` and `background_color =
      PALETTE[launch_theme]["bg"]`. On Windows only, right after its `create_window` and
      before `start()`, add `splash.events.before_show += _splash_border` to it.
      - `create_window` has no `before_show` keyword.
      - The handler's parameter must be named exactly `window`, because pywebview passes
        the window only to a handler with a `window` parameter. Otherwise it closes over
        `splash`.
      - It runs on the UI thread inside `create()`. `window.native` is set by then
        (`BrowserForm.__init__`, line 167).
    - `_create_kwargs` gains `background_color = PALETTE[launch_theme]["bg"]` and
      `hidden=True`.
  - **In `_boot`, after `create_window`:**
    1. register the `loaded` handler. It now waits on a new `_main_shown` event,
       `lambda: (_main_shown.wait(25), _destroy_splash())` (the handler runs on its own
       thread), so the splash stays until the main window is visible. A hidden window can
       finish loading before `show()`, which would otherwise leave a gap with nothing on
       screen.
       - **The backstop runs on `_boot`'s own thread,** so it must not wait: it moves to
         just after step 3, as `if main_win.events.loaded.is_set(): _destroy_splash()`.
         Waiting there before `show()` would block `_boot` on itself.
       - The error path still calls `_destroy_splash()` directly;
    2. `chrome.register(main_win, launch_theme)`, which applies the theme;
    3. `main_win.show()`, guarded:
       - on a `WebViewException` (the 20s `shown` wait) or any other exception: on
         Windows, log it and fall back to `chrome.native_show(main_win)`; off Windows,
         log it and re-raise, with no native fallback;
       - if the fallback also fails, raise, so `_boot`'s existing error path destroys
         both windows;
       - then set `_main_shown`;
    4. the tray wiring, and `_desktop_window = main_win` at its current point.

    The error path still destroys both windows.
  - `_splash_html(theme="dark")`: background `--bg`, text `--fg`, status
    `--fg-secondary`, bar track `--border`, all from `PALETTE`. The default keeps
    today's no-argument callers working. The brand gradients (logo, bar fill) stay.
    `_SPLASH_TEXT_ONLY` is themed the same way, for example as a builder taking the
    theme.
- **`the_one/interfaces/web/app.py`:** `POST /api/window/chrome`, a plain `def` with a
  body model `theme: Literal["light", "dark"]`, which lazy-imports
  `shell.set_window_theme`. Also `GET /api/window/chrome`, a plain `def` returning
  `chrome.snapshot()`. Both sit behind the existing credential gate.
- **`the_one/interfaces/web/static/js/theme.js`:** `notifyShell(theme)`, called at the
  end of `apply()`, plus a `pywebviewready` listener registered at load. Per DD3's page
  side:
  - **Gate:** `isDesktopWebview()` is `(window.chrome && window.chrome.webview) ||
    window.pywebview`.
  - **Dedup:** skip when the theme equals the last one sent successfully.
  - **Ordering:** one POST in flight; later changes coalesce to the latest; a theme
    counts as sent on any 2xx, including a `tinted: "pending"` response, because the shell
    already holds it as requested.
  - **Retry:** a failed post is retried once, after 2s or on the next `apply()`, then
    left.
  - **Errors:** none are shown to the user.
  - **Style:** ES5, as the file already is (no arrow functions).
- **Tests:**
  - `tests/test_window_chrome.py` (new), for the units;
  - `tests/test_api_window_chrome.py` (new), for the routes;
  - `tests/test_desktop_shell.py`, extended for the first-paint order, the splash theme
    and `set_window_theme`;
  - `tests/browser/test_flow_settings_window_chrome_signal.py` (new, `settings` lane).
- **Docs:**
  - **`the_one/agents.md`, "Desktop launcher":**
    - a "Window chrome (M25 F5)" contract block: the palette and its pin, the route
      pair, the state and lock contract, UI-thread applies (`BeginInvoke` with a bounded
      wait), first paint and the guarded `show()`, activation, persistence and platform
      scope. It notes:
      - Windows does not dim a custom title-text colour on an inactive window
        (premise 7), so the activation tracking is necessary;
      - a `pending` registration still tints before the window appears, because `show()`
        goes through the same UI message queue as the posted apply;
      - the reason for calling `EndInvoke`;
    - the "pywebview frameless custom-chrome footgun" note corrected for 5.4 (DD13).
  - **`CLAUDE.md`, "Desktop launcher (`the-one app`)":** a short M25 F5 paragraph (the
    tint, the route pair, `window-chrome.json`, first paint).
- **The flight log:** a "Leg 2: tinted-title-bar" entry with the test-copy verification
  results.

## Acceptance Criteria

- [ ] **Palette pin.** A unit test parses `tokens.css` with
  `parse_tokens_css_theme_blocks` and asserts that every hex in `PALETTE` equals its
  token for both themes: `--surface`, `--fg`, `--fg-muted`, `--border`, `--bg` and
  `--fg-secondary`.
- [ ] **`chrome.py` units** (`tests/test_window_chrome.py`, no Windows calls):
  - `colorref` (`#17181c` gives `0x001C1817`);
  - `attribute_plan` for build 26100 active and inactive, light and dark; for build
    19045; and for None;
  - `windows_build` off Windows gives None;
  - `os_theme` with winreg absent gives dark, and with a fake winreg giving 1 or 0;
  - `load_theme` and `save_theme`: a round trip, a missing file, a corrupt file, an
    invalid theme value, and an atomic write (no partial file left);
  - **state:**
    - `request` before `enable` (recorded, not persisted, `desktop: false`);
    - after `enable` (persisted);
    - before `register` (requested, then applied at registration, the post-before-
      registration race);
    - after `register` (applied with the current active state);
  - **activation:** a theme change while inactive applies `text_inactive` of the new
    theme;
  - **the lock:** never held during the injected UI-thread invoke (a fake `Invoke` that
    asserts the lock is free);
  - **racing requests:** two requests resolved in either order leave the latest
    requested theme applied;
  - **`reset`**, and **`deregister`** (a request after it applies nothing);
  - **the `BeginInvoke` path:**
    - a fake that raises gives a logged skip with no exception;
    - a fake that never completes gives `pending` within the bound, with `_UI_WAIT_MS`
      monkeypatched to about 50;
    - `deregister()` (the `closing` flag) or a disposed form gives no invoke at all;
    - a Win32 call that raises inside the UI-thread function is logged and recorded in
      `last_applied`, never raised;
  - **`snapshot`'s `pending`:** true after a timed-out request, false once the apply is
    recorded;
  - **`attribute_plan`** never lists attribute 36 twice, and uses `text_inactive` only
    for `active=False`;
  - **`snapshot`'s shape.**

  The Windows-only calls are injected or monkeypatched, as the existing desktop tests
  mock `webview`.
- [ ] **Test isolation.**
  - An autouse fixture resets the `chrome` state around every test that can touch it: in
    `tests/conftest.py`, or a local `conftest` for the desktop tests.
  - Every test that runs `DesktopSession.run()` or `chrome.request` keeps or adds a
    monkeypatch of `settings.data_dir` to `tmp_path`. The existing `_boot` tests already
    pin it (lines 380, 511, 595 and 643). The new reads to cover are `chrome.enable` and
    `load_theme`.
  - Any shell test that patches `sys.platform` to `win32` also stubs
    `chrome.register`, `chrome.apply_splash_border`, `chrome.native_show` and
    `chrome.os_theme`, so no real pythonnet or winreg code runs against `MagicMock`
    windows.
  - `reset()` clears every field (`enabled`, `data_dir`, `requested`, `window`,
    `closing`, `active`, `last_applied`, the sequence numbers). The autouse fixture is
    cheap and import-safe, because `chrome.py` has no GUI imports.
  - No test reads or writes the real default data dir.
- [ ] **Routes** (`tests/test_api_window_chrome.py`, through the existing credentialed
  client fixtures):
  - POST `light` and POST `dark` give 200 with `{"theme", "desktop", "tinted"}`;
  - POST `"blue"` or a missing field gives 422;
  - with no desktop session, `desktop` is false and `tinted` false;
  - with a fake registered window, `set_window_theme` is called and `tinted` is
    reported (`true`, `false`, or `"pending"` when the UI thread did not finish within
    the 2s bound, a refinement of DD3's boolean). The `"pending"` case fakes
    `set_window_theme` rather than sleeping;
  - GET returns the snapshot shape, including `pending`;
  - both are refused without a credential (401).
- [ ] **Shell** (`tests/test_desktop_shell.py`):
  - the main `create_window` gets `hidden=True` and `background_color` for the launch
    theme;
  - `chrome.register` runs after `create_window` and before `show()`, and `show()` is
    called;
  - the `loaded` handler is still registered right after `create_window`;
  - the splash gets the themed HTML and `background_color`. On Windows (with
    `sys.platform` patched), a handler is added to `mock_splash.events.before_show`.
    Check what `_make_splash_mock` provides, and extend it if needed;
  - a `show()` that raises falls back to the native show. When the fallback also raises,
    `_boot`'s error path destroys both windows;
  - `chrome.deregister()` is called before the destroy in `_on_quit`, in `_on_closing`'s
    allow-destroy returns and in `_close_to_tray`'s no-tray fallback;
  - the splash is not destroyed before `show()` returns, even when `loaded` is already
    set at subscription time (the backstop) or fires before `show()`;
  - off Windows, a raising `show()` takes the error path with no native fallback;
  - the launch theme comes from `window-chrome.json`, else `os_theme()`;
  - `set_window_theme` never raises.

  The existing shell, window-state, focus and tray tests stay green. Any test that pins
  the old `_create_kwargs` exactly is updated in place, with the rename noted.
- [ ] **Browser** (`tests/browser/test_flow_settings_window_chrome_signal.py`, `settings`
  lane). POSTs to `/api/window/chrome` are intercepted with `page.route`, which records
  the bodies and fulfils 200 (a 500 for the retry case). Cases:
  1. **`chrome.webview` stubbed at document start** (init script): exactly one POST on
     load with the resolved theme. One POST per theme change made through Settings ›
     Appearance. No POST when the resolved theme does not change (Light, then Auto with
     emulated light). Rapid changes coalesce: no more than in-flight plus one, and the
     last body is the final theme.
  2. **`window.pywebview` injected after load,** then a dispatched `pywebviewready`:
     exactly one POST.
  3. **No stubs:** zero POSTs across load and theme changes.
  4. **A 500 response:** retried exactly once.
- [ ] **Static guards and lanes:**
  - `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and
    `tests/test_design_tokens_a11y.py` pass;
  - the `settings` lane passes (`THE_ONE_TEST_NETNS=1`);
  - the `shared` lane passes (`TEST_TIMEOUT=3600`). It holds the theme-sync tests, and
    `theme.js` loads on every page.
- [ ] **Test-copy verification on Windows**, bracketed by `snapshot --out` / `--compare`
  and `focus-save` / `focus-restore`, and recorded in the flight log with sampled values:
  1. **First launch.** First read the OS app theme (`doctor-host`). Expect Light values
     when it is Light (as at planning) and Dark values when it is Dark. With a fresh
     scratch data dir (no `window-chrome.json`), a `capture --series` (rect mode over the
     launch area, at the minimum interval) starts **before** `launch` and runs through
     the splash's life:
     - the splash's background is `#ffffff` (Light);
     - the main caption samples `#fafafa` (±3) (Light);
     - `GET /api/window/chrome` shows `last_applied.theme` `light`, HRESULTs 0, and
       `pending` false, read from `last_applied`, never from `requested` alone;
     - the splash stays until the main window is visible: no series frame between them
       shows neither window;
     - `window-chrome.json` holds `light`.
  2. **Dark.** CDP is reached from WSL at `127.0.0.1:<cdp-port>` (mirrored networking;
     leg 1a premise 10). Through it, Settings › Appearance › Dark: within 1s the caption
     samples `#17181c`, the GET shows `last_applied.theme` `dark` with `pending` false,
     and the file holds `dark`.
  3. **Inactive and active.** With own window A in front, the title text's lightest
     pixel is close to `#85878f`; active again, close to `#ededf0`. A Light change while
     inactive gives an inactive light title (close to `#6e6e77`).
  4. **Auto.** CDP `Emulation.setEmulatedMedia` with `prefers-color-scheme: dark` makes
     the caption follow to `#17181c`, and `light` brings it back to `#fafafa`. Clear the
     emulation afterwards.
  5. **Relaunch (the seeded dark launch theme).** With `dark` persisted (the file is
     written at request time): × (to the tray), `stop`, then relaunch with a `capture
     --series` started before `launch`. No visible frame shows a light caption or a white
     page or splash, and the first visible frame is already dark. This covers the
     launch theme that is not the OS theme.
  6. **The browser gate.** Open the same server in a plain browser tab: the repo's
     Playwright from WSL, with the credential read from `R\data-l2-*\api-credential`
     through `/mnt/c` and a handoff minted over HTTP (`POST /api/session/handoff`). It
     changes theme without sending a POST, and the desktop caption does not change.
- [ ] **Docs:** the `agents.md` "Window chrome (M25 F5)" block, the corrected footgun
  note and the `CLAUDE.md` paragraph.
- [ ] **Gates:**
  - `ruff check` and `ruff format --check` pass on `the_one/`, `tests/` and `scripts/`;
  - `TEST_TIMEOUT=3000 make test-unit` passes;
  - every Windows session's snapshot comparison is clean, or shows only an allowed
    change.

## Verification Steps

- **Units and routes:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_window_chrome.py tests/test_api_window_chrome.py tests/test_desktop_shell.py
  tests/test_window_state.py tests/test_window_focus.py tests/test_desktop_tray.py -x
  --timeout 30`.
- **Static guards:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py
  -x --timeout 60`.
- **Browser:**
  - `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser
    tests/browser/test_flow_settings_window_chrome_signal.py -x`;
  - then `--lane settings`;
  - then `TEST_TIMEOUT=3600 … --lane shared`.
- **Unit suite:** `TEST_TIMEOUT=3000 make test-unit`, in the background.
- **Test copy:** the helper's `setup` (re-sync), then `launch --port 849x --cdp-port 939x
  --data-dir R\data-l2-*`, `pixel`, `capture`, the own windows, CDP from WSL, `stop`, and
  the snapshot and focus brackets.

## Implementation Guidance

1. **Read** the flight's DD2–DD5, DD7 and DD13, the Leg 1b findings, `shell.py`
   (`run()` and `_boot`) and the desktop tests' mocking patterns.
2. **`chrome.py` and its unit tests first.** Start with the pure parts (`PALETTE`,
   `colorref`, `attribute_plan`, persistence, the state), then the Windows-only calls
   behind lazy imports, injected for tests.
   - **The UI-thread invoke** in pythonnet, with the delegate leg 1b proved on Windows
     and pywebview 5.4 uses itself:
     ```python
     from System import Func, Type
     form = window.native
     if form.InvokeRequired:
         ar = form.BeginInvoke(Func[Type](fn))
         ar.AsyncWaitHandle.WaitOne(2000)  # bounded; False -> "pending"
     else:
         fn()
     ```
     Put it behind one function that tests replace.
   - **pythonnet event handlers** take `(sender, args)`. Write them as `def h(*_):` so a
     signature mismatch never raises into WinForms.
   - **The HWND:** `int(form.Handle.ToInt64())`, after `IsHandleCreated and not
     IsDisposed`; then `user32.IsWindow`.
3. **The shell changes** in the order above, with the shell tests updated. Keep the
   `loaded` registration ahead of `register` and `show`, so a fast load still dismisses
   the splash.
4. **The routes** and their tests.
5. **`theme.js`** and the browser test. Run the static guards.
6. **Docs.**
7. **Test-copy verification:**
   - The Flight Director has notified the operator.
   - `setup` re-syncs the working tree into the scratch root, so the copy runs this
     leg's code.
   - The six checks run from source, on ports 8490 and up and 9390 and up, with fresh
     `R\data-l2-*` dirs, bracketed as stated.
   - Use the helper's own windows for the inactive state, and CDP from WSL for page
     actions.
   - Record the sampled values in the flight log.
8. **Gates,** then mark the leg `landed` and signal `[LAND:leg]`.

## Edge Cases

- **A post arrives before registration.** It is recorded as `requested` and applied at
  registration (a unit test covers it).
- **A post arrives in serve mode** (no desktop session). It returns `desktop: false`,
  writes no file and applies nothing.
- **A post arrives after the window is destroyed** (Quit).
  - `deregister()` has already cleared the window, so nothing is invoked.
  - If the post races the destroy, `_really_quit`, `IsDisposed`, `IsHandleCreated` or
    `IsWindow` fails, or `BeginInvoke` raises. The apply is skipped and logged, with no
    exception, and the request thread is never blocked beyond the 2s bound.
- **Hide to tray, then show from the tray.** The HWND and its DWM attributes persist
  (P8). Nothing needs re-applying, but a re-apply on `Activated` is harmless.
- **`window-chrome.json` is unwritable.** Logged, and the apply still happens. The file
  is written only when the requested theme differs from the persisted one.
- **A non-Windows desktop (GTK).** `register` stores the window, applies nothing and
  never touches `native`. The page still posts (`window.pywebview`), so the launch theme
  persists for the next run.
- **An older Windows build.** Only attribute 20 is set. This is unit-tested only.
- **A second desktop window.** None exists: the single-instance rule focuses the
  existing window.
- **The operator is active or the session is locked** during the test-copy check. Follow
  the helper's rules (`release-all`, then `[BLOCKED:…]`).

## Files Affected

- `the_one/interfaces/desktop/chrome.py`: new.
- `the_one/interfaces/desktop/shell.py`: `set_window_theme`, first paint, the themed
  splash.
- `the_one/interfaces/web/app.py`: the `/api/window/chrome` POST and GET.
- `the_one/interfaces/web/static/js/theme.js`: `notifyShell`.
- `tests/test_window_chrome.py`, `tests/test_api_window_chrome.py`: new.
- `tests/test_desktop_shell.py`: extended.
- `tests/browser/test_flow_settings_window_chrome_signal.py`: new.
- `the_one/agents.md`, `CLAUDE.md`: docs.
- The flight log: the Leg 2 entry. This leg file: status.

## Citation Audit

Checked on 2026-10-06 against the working tree after leg 1b:
- **`shell.py`:**
  - `_desktop_window` (line 24);
  - `_SPLASH_TEXT_ONLY` (line 43) and `_splash_html` (line 109);
  - `focus_window` (line 313);
  - the `run()` reset (lines 509–510), `_create_kwargs` (line 583), the splash (line
    615), `_boot` (line 641);
  - `create_window` (line 691), `_desktop_window = main_win` (line 721), the storage
    dir (line 741).
- **`app.py`:** `window_focus` (decorator at line 2619, function at line 2620).
- **`theme.js`:** `apply` (line 51).
- **`_ui_guard_helpers.py`:** `parse_tokens_css_theme_blocks` (line 600).
- **`test_desktop_shell.py`:** `webview_mock` (line 58), `_make_splash_mock` (line 353),
  `_EventCapture` (line 463), the `_splash_html` tests (lines 928 and 962).
- **pywebview 5.4:**
  - `event.py` `Event.set`, which runs locked handlers synchronously and others on a
    thread;
  - `window.py` line 165, `before_show = Event(self, True)`;
  - `winforms.py` line 265, `self.Activated += self.on_activated`, and line 656,
    `before_show.set()` inside `create`.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
