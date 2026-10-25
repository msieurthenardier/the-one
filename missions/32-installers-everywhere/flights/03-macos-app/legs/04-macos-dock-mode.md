# Leg: macos-dock-mode

**Status**: completed
**Flight**: [macOS app](../flight.md)

## Objective
Give the macOS app native Dock behaviour:
- closing the window hides it while the app stays in the Dock;
- the Dock icon (or `open -a`) brings it back;
- every quit drains the server before the process exits: the app menu's Quit, the Dock's Quit, the quit Apple event, logout, `the-one quit`, `POST /api/window/quit`, the takeover, and a Cmd-Q typed into the web view;
- a second launch focuses the window on the main thread;
- the state route reports the real native visibility.

Linux and Windows are unchanged.

## Context
- **Flight DDs:** DD2 (dock mode, App Nap), DD3 (paths T and S, `boot_stopped`, the bounds), DD4 (the thin PyObjC layer, the decision core, `activate`, the canary, the native visibility read), DD5 (the second launch). DD9's test seam is **not** needed (leg 3: Accessibility works). DD11: no first-paint change (leg 3: environmental).
- **Leg 1** made the structure this leg extends:
  - `the_one/interfaces/desktop/session_state.py::SessionState` already has `server`, `thread` and `boot_stopped` slots, which this leg starts using. Per the leg 1 review, `run()` must clear `state.server`/`state.thread` when it ends.
  - `window_control.py` holds `window_visible`, `focus_window` and `quit_desktop` (`request_quit` tags).
  - `takeover.py` holds the second-launch path.
- **Leg 5** provides `the_one.platform.env.prime_login_shell_path()` (never raises; a no-op off frozen darwin). **This leg adds its one call** in `DesktopSession.run`, just after the `is_ours` return and before the server starts (DD7).
- **Leg 3 and leg 3b (the probe), the ground truth for the AppKit premises:**
  - Accessibility keystrokes and the quit Apple event reach the app.
  - Cmd-Q most likely takes path T (leg 3b observes this directly).
  - **The delegate signatures:** `applicationShouldTerminate:`'s installed prototype is `I@:@`, not `Q@:@`. The overrides take their signature from the runtime (no explicit `typedSelector`). The route that works, subclass or `classAddMethods`, and the logged signatures **come from leg 3b's flight-log section, which this leg must read first**.
  - Today's build: pystray raises "NSWindow should only be instantiated on the main thread!", `tray: null`, a close exits, and an Apple-event quit gives no drain.
- **pywebview 5.4's Cocoa facts** (the flight's Citation Audit) are pinned by this leg's canary test.

## Preconditions (a gate before Phase B; Phase A needs none of them)
- **Leg 3b's `### macos-probe-rerun` section exists.** This leg's flight-log entry quotes, before any code:
  - the route that installed (`subclass` or `classAddMethods`);
  - the logged signatures;
  - the probe's `terminate`/`reply`/`willTerminate` counts;
  - whether a reply sent through `AppHelper.callAfter` was **delivered** while AppKit waited on `NSTerminateLater` (it runs its loop in a modal mode).
- **If neither route installed:** stop with `[BLOCKED:delegate-unextendable]` (a divert).
- **If the `callAfter` reply was not delivered:** the reply uses `performSelectorOnMainThread_withObject_waitUntilDone_modes_` with `NSRunLoopCommonModes` (the named fallback), recorded.
- **If 3b chose `classAddMethods`:** `install` adds the methods to `BrowserView.AppDelegate` itself instead of replacing the class attribute.

## Decision tables (the pure core; `view` fields as named under Outputs)
- **`on_close`:**
  - `really_quit` → `allow`;
  - else a published window → `hide`;
  - else (a window not yet published, or booting) → `hide` if a native window exists, else `allow`;
  - a failed hide → `allow` (the caller handles it).
- **`on_reopen`:**
  - `really_quit` or `terminate_pending` → `ignore`;
  - `booting` with no published window → `defer`;
  - else → `show` (which also deminiaturizes; a miniaturized window reports no visible windows).
- **`on_terminate`:**
  - `terminate_pending` → `already-pending` (answer `NSTerminateLater`, start nothing);
  - no local server (window client) → `reply-now`, which returns **`NSTerminateNow` (1)**;
  - else → `drain-then-reply`, which returns `NSTerminateLater` (2) and starts the worker.

## Outputs
- **`the_one/interfaces/desktop/macos_dock.py`** (new; darwin-only imports, all lazy, inside functions):
  - **A pure decision core**, importable on any OS:
    - `on_close(view) → "hide" | "allow"`;
    - `on_reopen(view) → "show" | "defer" | "ignore"`;
    - `on_terminate(view) → "drain-then-reply" | "reply-now" | "already-pending"`.

    `view` is a small immutable snapshot taken from `SessionState`: `really_quit`, `booting`, `desktop_window is not None`, `terminate_pending`, `server is not None`.
  - **`TerminateWorker(reply, drain, boot_wait, log_flush, clock, sleep)`**, which runs DD3's steps with injectable seams, so it can be unit-tested with fakes:
    1. **Geometry is read in the delegate callback, on the main thread, before it returns `NSTerminateLater`.** That makes it a direct `frame()` read; the worker never reads geometry. With an unpublished window, the save is skipped;
    2. the worker waits on `boot_stopped`, bounded at **5 s** (not 10);
    3. `drain()` (`_graceful_shutdown`, its 60 s join);
    4. logs "terminate: reply sending", then `log_flush()` (flush, never close the handlers);
    5. `reply()`.

    Total: at most 5 s + 60 s + the flush, well inside `_TAKEOVER_WAIT_BOUND = 75`. The worker never holds `state.lock` while it waits.
  - **Named AppKit seams** (module functions the tests replace): `_call_after(fn, *args)`, `_nsapp()`, `_native_window(window)`, `terminate_app()` (main-thread `NSApp.terminate_(None)` via `_call_after`), `reply_to_terminate(ok)`.
  - **`activate(window)`**: `AppHelper.callAfter` of show, deminiaturize and `NSApp.activateIgnoringOtherApps_(True)`.
  - **`native_visible(window) -> bool | None`**: `window.native.isVisible()` read directly, with a fallback through `AppHelper.callAfter` plus a bounded wait. `None` on failure.
  - **`install(session) -> str`**: runs once, on the main thread, before `webview.start`. It installs the delegate overrides by leg 3b's working route and returns the route name for the log. It also begins the App Nap activity (`NSProcessInfo.processInfo().beginActivityWithOptions_reason_` with `NSActivityUserInitiatedAllowingIdleSystemSleep`). The returned token is kept in a **module-level** variable (a local would be released, ending the activity), and a test asserts that `install` stores it.
- **`session_state.py`:**
  - `begin_quit()`: sets `really_quit` and `quit_requested` under the lock; returns the window to save, or None.
  - `terminate_pending` (a bool), plus `mark_terminate_pending() -> bool`, which returns False if already pending;
  - `loop_stopped` (a bool), set by path S when `webview.start` returns;
  - `reset()` clears both (pinned by a test).
  - `run()` clears `server`/`thread` on exit (the leg 1 review note).
  - `boot_stopped` is set by `_boot` on every exit.
- **`shell.py` (`DesktopSession`):**
  - **darwin:**
    - no tray: `state.tray_mode = "dock"`, set **at the top of `run()`**, before `webview.start` (not at step 5, so there is no `tray_mode=None` gap in which `_on_closing` would allow a destroy); pystray is never imported (a test asserts no `pystray` import on darwin);
    - `_destroy_splash` is a no-op while `terminate_pending`, `really_quit`, `boot_stopped` or `loop_stopped` is set, and in `_boot`'s error path. While only the splash exists, its `windowWillClose_` empties `BrowserView.instances` and calls `app.stop_` and `abortModal`, which would stop the loop mid-drain (tested);
    - `_on_closing` in dock mode applies `on_close` (hide through `window.hide()`, no notice), with `_really_quit` still allowing the destroy;
    - `macos_dock.install(self)` before `webview.start`;
    - **path S** after `webview.start` returns:
      1. `state.loop_stopped = True`;
      2. `begin_quit()`;
      3. a direct `orderOut_`;
      4. the geometry save (if a window was shown);
      5. the existing `finally` drain;
      6. then a bounded wait on `boot_stopped` (5 s);
      7. log, flush, and **`os._exit(0)`**: pywebview starts `_boot` on a non-daemon thread, which can be stuck in `create_window` after the loop stopped (the probe's P9 showed the process lingering).

      A Cmd-W on the splash alone also ends here: path S, with no window published. Tested as an ordered sequence of fakes;
    - `_boot`'s `_abort_if_quit` and its exception path follow DD3: they set `boot_stopped` and never call `terminate_`/`destroy`, except that an unhandled boot error with no terminate pending calls `terminate_` once.
  - **All platforms:** `prime_login_shell_path()` is called after the `is_ours` return and after `state.begin_boot()`, so a quit that arrives during its up-to-5 s probe finds the boot guard. Note the possible 5 s before the splash in the docs.
- **`window_control.py`:**
  - darwin `quit_desktop`: if `state.loop_stopped`, it does nothing more and returns `"window"` (the drain is under way). Otherwise every non-`None` tag, including `"booting"`, calls `macos_dock.terminate_app()` instead of `_on_quit` or a pending flag. `"browser"` is unchanged (effectively unreachable on darwin, since `_webview_available` is always True there).
  - darwin `focus_window`: `macos_dock.activate`.
  - darwin `window_visible`: `macos_dock.native_visible`.
  - `window_state()` already reports `state.tray_mode`, so `tray: "dock"` follows from `shell.py`'s assignment. Update `_on_closing`'s docstring and `tray.py`'s darwin references to match.
  - `chrome.register`/`deregister` on darwin: no change (off Windows, `register` only stores the window and `deregister` only sets flags), asserted by a test.
- **Tests** (Linux, fakes only, no AppKit):
  - the decision core's truth tables;
  - `TerminateWorker`: the drain then the reply; the bound (10 s boot wait plus a 60 s join, with a fake clock); the reply after a timeout; window-client (no server) replies at once; a repeated terminate starts no second worker; logging is flushed before the reply;
  - `_on_closing` in dock mode;
  - path S ordering;
  - the darwin `quit_desktop` mapping for each tag;
  - the darwin `focus_window` → `activate`;
  - the boot abort under darwin;
  - `state.server`/`thread` cleared after `run()`;
  - `prime_login_shell_path` called once after `is_ours` and not on the `is_ours` branch;
  - **the canary** (`tests/test_pywebview_cocoa_canary.py`): locates `webview/platforms/cocoa.py` through `importlib.util.find_spec("webview")` plus the path (never importing the Cocoa module), reads it with `ast`, and asserts every fact listed in flight DD4, plus `_add_app_menu`'s `q` → `terminate:` and `windowWillClose_`'s `abortModal`.
  - **How the shell tests run:** `state` plus a `DesktopSession` with a fake window and a patched `webview.start`, as `tests/test_desktop_shell.py` already does. `sys.platform` is patched to `darwin`, and the `macos_dock` seams are replaced.
- **Docs:**
  - `the_one/agents.md` Desktop launcher: a "macOS dock mode (M32 F3)" paragraph covering the paths, the delegate route, App Nap and the canary;
  - `CLAUDE.md` Desktop launcher: one additive sentence;
  - `SECURITY-MODEL.md`: only if a route's behaviour changes. It shouldn't: the routes' answers are unchanged.

## Acceptance Criteria
- [x] **AC1:** every Output is implemented and unit-tested as listed, on Linux, with `sys.platform` patched where needed and AppKit faked through injected seams (no `objc` import in tests).
- [x] **AC2:** Linux and Windows unchanged. Every existing desktop test passes unmodified, except tests that pinned darwin's old tray path, each renamed and inverted (state which). The split guard passes.
- [x] **AC3:** `make test-unit` passes with 12 skips; ruff is clean. The `settings` browser lane passes (`THE_ONE_TEST_NETNS=1`).
- [x] **AC4:** the Linux real-GTK smoke test still passes on one baseline (`packaging/linux/checks/gtk-smoke.sh ubuntu-26.04 --deb <new build>`). A build from this tree proves the shared `shell.py` paths didn't regress.
- [x] **AC5:** the hosted proof is leg 7's `lifecycle.sh`. This leg records, in its flight-log section, a table of the exact observable each lifecycle step will read: the log line text (the route installed, terminate received, the drain started and done, reply sending, path S exiting) and the state-route field.
- [x] **AC6:** hygiene as in leg 1's AC7.

## Verification Steps
- The test names per Output; the `make test-unit` and lane summaries; the smoke `OVERALL` line; `git status`.

## Phases
Two Developer spawns:
- **Phase A:** the pure core and its tables, `TerminateWorker` and the seams, `session_state`, `window_control`, their tests, and the canary.
- **Phase B:** the `shell.py` wiring (darwin dock mode, path S, `_destroy_splash` suppression, the prime call), `macos_dock.install` (the route from 3b, the App Nap token), the shell tests, the docs, the AC3 gates and the AC4 smoke.

## Implementation Guidance
1. Satisfy the Preconditions gate first (quote 3b in the flight log).
2. Decision core and worker first (pure), then `session_state`, then `window_control`, then `shell.py`, then the darwin glue in `macos_dock.install`, then the canary and the docs.
3. Keep every AppKit import inside a darwin-only function, so nothing on Linux or Windows imports `objc`.

## Edge Cases
- **A terminate arrives while booting:** the worker waits on `boot_stopped` (bounded), and `_boot`'s next `_abort_if_quit` sees `really_quit`, stops without publishing, and sets the event.
- **A reopen while booting:** `defer`. The window shows when published, as normal boot does.
- **A second terminate while one is pending:** answer `NSTerminateLater` again and start nothing.
- **Logout:** the same path T; the reply always comes, within the bound.
- **Cmd-Q while only the splash exists:** path S. `begin_quit()` makes `_boot` stop.

## Files Affected
- `the_one/interfaces/desktop/{macos_dock.py (new),session_state.py,shell.py,window_control.py}`
- tests: new `tests/test_macos_dock.py`, `tests/test_pywebview_cocoa_canary.py`; existing desktop tests only if they pinned darwin's tray path
- `the_one/agents.md`, `CLAUDE.md` (additive)

### Citation Audit
Checked at `ddedd5c` plus leg 5's working tree:
- `session_state.py::SessionState` (its slots and methods);
- `window_control.py::quit_desktop`/`focus_window`/`window_visible`;
- `shell.py::DesktopSession.run`: the `is_ours` returns at about lines 497-503, step 5's tray wiring at about 780-820, `webview.start` at about 857, and the `finally` drain at about 899-902.

The signature and route facts are **pending leg 3b**. This leg goes `ready` only after 3b's section exists.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
