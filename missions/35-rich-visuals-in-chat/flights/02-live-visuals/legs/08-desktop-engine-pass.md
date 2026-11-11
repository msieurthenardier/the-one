# Leg: desktop-engine-pass

**Status**: in-flight
**Flight**: [Live Visuals](../flight.md)

## Objective
Close the desktop-shell items the widget boundary depends on, and prove charts and widgets in the three real desktop engines:
1. the shell removes pywebview's native message handlers (`jsBridge` on GTK and Cocoa, plus `browserDelegate` on Cocoa) so no widget frame can reach them, and reports that it did;
2. a clean quit leaves no hang-guard crash record that the next launch would read as a hung widget;
3. charts and widgets render and behave in WebKitGTK, WebView2 and WKWebView, with the bridge confirmed unreachable on all three.

## Context
- **Flight DDs:** DD13 (the bridge, operator decision at the leg 1 gate: switch it off on GTK and Cocoa; Windows keeps a regression probe), DD9 (the crash record and its next-launch check, with a bounded shell fallback), DD17 (engine checks owned by legs; this leg is the "desktop engine pass"), and the desktop test-patch rule (`the_one/agents.md` "Desktop test-patch rule and the pywebview/PyObjC upgrade checklist").
- **Operator decisions (2026-11-11, flight log "Leg 8 design"):** the macOS check extends the existing `probe` mode of `.github/workflows/macos-packages.yml` (no change to `main` or `release.yml`); Cocoa's `browserDelegate` is removed too; squawk 0343 is fixed before the Windows session.
- **Leg 1 measured** (flight log "Leg 1"): from a sandboxed frame, a replica `jsBridge` registration on WebKitGTK was reachable (`postMessage` reached the Python callback); on WebView2 157 `chrome.webview` exists in the frame but a move from it did nothing. WebKitGTK and WKWebView freeze the page during a widget busy loop; WebView2 does not.
- **What travels over the bridge** (research, pywebview 5.4): `_jsApiCallback` for `js_api`/`expose` calls, `pywebviewMoveWindow` (easy-drag), `pywebviewEventHandler` (DOM events, file drop), `pywebviewAsyncCallback` (`evaluate_js` with a callback), and `_pywebviewAlert` (GTK `window.alert`). The-one uses none of them: no `js_api`, `expose`, `evaluate_js`, `run_js`, `window.dom` or `alert` in `the_one/`. `inject_pywebview` and the `loaded`/`closing` events are native, so `window.pywebview` and `pywebviewready` (read by `theme.js:73`, `:122`) keep working.
- **The crash record** (leg 5): `widget-lifecycle.js` writes `localStorage["widget-running:{pageId}"]` while a widget is loaded and removes it on `pagehide` (`onPageHide`, `:354-356`) and on `release()` (`:409-421`). `scanRecords()` (`:196-214`) runs at library load and turns a foreign record older than 10 s (90 s if written hidden) into "This widget stopped responding last time." on that widget.
- **Storage persists across launches:** `webview.start(_boot, private_mode=False, storage_path=...)` (`shell.py:1080`) leaves localStorage enabled. `storage_path` is **not** where it lives: on GTK it only names the cookie file (`gtk.py:130-141`); localStorage goes to `WebContext.get_default()`'s data directory (normally `$XDG_DATA_HOME/<program name>/localstorage/`, program name unverified); Cocoa uses `WKWebsiteDataStore.defaultDataStore()`; WebView2 uses the user data folder. WebKit flushes localStorage lazily. Whether `pagehide` fires on pywebview's `destroy()` (GTK, WebView2) or `NSApp.terminate_` (Cocoa), and whether the removal reaches disk before exit, is unmeasured.
- **Threads:** pywebview runs each `events.loaded` handler on its own new thread (`event.py:37-60`), after `inject_pywebview`'s `run_js` calls (`util.py:211-221`). `_on_quit` runs on the tray thread or a request thread (`window_control.py:186`), never the GTK main thread.
- **Quit paths:** tray Quit, `the-one quit` and `POST /api/window/quit` reach `DesktopSession._on_quit` (`shell.py:533-570`, `state.desktop_window.destroy()` at `:562`); on macOS they and the Dock/app-menu/Cmd-Q quits reach `NSApp.terminate_` → `macos_dock.handle_terminate` → `TerminateWorker.run` (`macos_dock.py:124-180`, `:306-338`). The window × only hides. Logout and a kill run no shell code (accepted residual, as for a closed browser).
- **Blocking calls:** GTK and Cocoa `evaluate_js` and `run_js` wait on an unbounded semaphore (`gtk.py:576-579`, `cocoa.py:812-834`); against a page frozen by a widget they never return. Any shell call into the page must run on a daemon thread joined with a timeout.

## Inputs
- Legs 1-7 committed (`48ab1bb7`). The working tree holds another session's uncommitted `the_one/db/_notes.py`, `tests/test_prompt_layers.py`, `tests/behavior/agent-notes-round-trip.md` and `env.sh`: never stage, stash or revert them.
- WSLg on this host (`DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`), `gi` importable from `.venv`, `scripts/webkitgtk_probe.py` (plain WebKit2, `--setup-script`, `--register-message-handler`), `scripts/widget_sink.py`, `tests/fixtures/widgets/escape.html`.
- Part B: squawk 0343 completed (so `scripts/windows_test_copy.py setup` works on Python 3.12); the operator at the Windows desktop.
- Part C: the branch pushed; the operator's go for each dispatch; no release running.

## Outputs
- Shell code that removes the handlers, a `boot_policy` flag, a window-state field, canary pins and a guard test.
- If Part A's measurement shows a quit path leaves the record: the bounded shell clear (AC4).
- `packaging/macos/probe/visuals.sh` and a `probe`-mode step that runs it.
- Measurements and verdicts in the flight log for Linux (Part A), Windows (Part B) and macOS (Part C).
- Docs: `SECURITY-MODEL.md` "Live visuals", `the_one/agents.md` (desktop shell and the test-patch rule), `docs/widget-format.md` if the crash-record behaviour it states changes.

## Acceptance Criteria

### Part A (autonomous)

- [ ] **AC1 — The handlers are removed.**
  - A new function in a module that defines it (not `shell.py`; the split guard `tests/test_desktop_split_guard.py` forbids patching shell names), for example `the_one/interfaces/desktop/native_bridge.py::remove_native_handlers(window) -> str`, removes:
    - GTK: `jsBridge` from the main window's `UserContentManager` (`BrowserView.instances[window.uid].manager.unregister_script_message_handler("jsBridge")`), on the GTK main thread (`glib.idle_add`, as `window_control._gtk_read` does);
    - Cocoa: `jsBridge` and `browserDelegate` from the WKWebView's `userContentController` (`removeScriptMessageHandlerForName_`), on the main thread (as `macos_dock._call_after` does);
    - Windows and other backends: nothing.
  - It returns one of `"removed"`, `"not-applicable"` (Windows/other) or `"failed"`; a failure is logged at `error` with the reason and never raises into the shell.
  - **`"removed"` means the removal ran:** the UI-thread job sets an event when it has run, and the caller waits on it for at most 2 s; a timeout or an exception in the job is `"failed"`. The result is stored in `session_state.state` before the function returns.
  - It runs once per main window, from its **own, separate** `main_win.events.loaded += …` handler (`shell.py:927` registers the splash handler, which waits up to 25 s on `_main_shown`; do not add the removal to that lambda), on every platform where the new `BootPolicy` flag (AC2) is true. The handler's thread is not the UI thread, so the GTK and Cocoa hops are required. pywebview registers the handlers only in the constructor, so one removal holds across reloads; a second call is a no-op that keeps `"removed"`. The `script-message-received` signal may stay connected (harmless once the handler is gone).
  - Cocoa: `-[WKWebView configuration]` returns a copy whose `userContentController` is shared with the live view; this is relied on and verified on the hosted runner (Part C).
  - Only the main window: the splash has no remote content.
- [ ] **AC2 — Platform decision and observable.**
  - `BootPolicy` gains `removes_native_bridge: bool` (`LINUX` and `MACOS` true, `WINDOWS` and `OTHER` false), with its row in `tests/test_boot_policy.py`'s decision table (`test_the_table_covers_every_field` must stay green).
  - `window_control.window_state()` (`:140-153`) and therefore `GET /api/window/state` gain `"native_bridge": "removed" | "not-applicable" | "failed" | "pending"` (`"pending"` before the main window's first `loaded`). No exact-shape pins of that response exist (design review: `tests/test_window_routes.py:50` asserts single keys; `packaging/macos/lib.sh`, `lifecycle.sh`, the Linux `gtk-smoke-inner.sh` and the Windows `lib.ps1` read single fields). Add a unit test for the field with a fake state.
- [ ] **AC3 — Pins and guards.**
  - `tests/test_pywebview_cocoa_canary.py` gains AST pins that `BrowserView.__init__` registers `addScriptMessageHandler_name_(…, 'jsBridge')` and `(…, 'browserDelegate')` and keeps `self.webview`; a new `tests/test_pywebview_gtk_canary.py` pins `register_script_message_handler('jsBridge')` and `self.manager` in the GTK `BrowserView.__init__`, parsed with `ast` (never imported), like the Cocoa canary.
  - A guard test fails on any use in `the_one/` of what the removal breaks. Python through `ast` (comments ignored; `shell.py:51` mentions `evaluate_js` in a comment): a `js_api=` keyword, an `.expose(` call, an `evaluate_js(` call with a second positional argument or a `callback=` keyword. The static JS (`*.js` and inline scripts in `index.html`, comments stripped, vendored files excluded): `window.pywebview.api`, `window.dom`, and a bare `alert(`/`print(` call matched with `(?<![\w.$])alert\(` style boundaries. It scans no `.md`. It passes on the current tree (design review: no hits). Its failure message says why (the bridge is removed for widgets, DD13).
  - Unit tests for `remove_native_handlers` with fakes: each backend's call, the thread hop, idempotence, the failure path (`"failed"`, logged, no raise), and that the shell calls it from `loaded` only when the flag is true.
- [ ] **AC4 — Clean quits leave no crash record (Linux measured here).**
  - Measure on the real `the-one app` under WSLg, for tray Quit, `the-one quit` and `POST /api/window/quit`: with a chat open whose widget is running, quit, relaunch, reopen the same chat. **Pass:** no "This widget stopped responding last time." on that widget, and no `widget-running:` key in WebKitGTK's localStorage on disk, read **after the process has fully exited** (WebKit flushes lazily). Locate the store empirically, e.g. `find ~/.local/share ~/.cache -newer <marker> -path '*localstorage*'` after a run that wrote a record, and record its path; do not assume `storage_path`. Record the outcome per path, at least twice each.
  - **If any path fails:** implement the bounded clear: before `state.desktop_window.destroy()` in `_on_quit` (and, for macOS, in `TerminateWorker.run` before the drain), run a script that removes every `widget-running:` key through `window.run_js(script)` (it returns nothing and never uses the bridge) on a daemon thread joined with a 1 s timeout; a timeout or error is logged and the quit continues. If `_on_quit` is ever entered on the GTK main thread, skip the clear (the semaphore inside `run_js` would deadlock the loop) and log it. A thread left blocked on a frozen page is a leaked daemon thread, harmless at exit; the unit test says so. Behind a `BootPolicy` flag if it is not needed on every platform. Unit tests with a fake window that blocks forever prove the quit still completes within the bound. Re-measure.
  - Never call `evaluate_js` with a callback (it needs the bridge).
- [ ] **AC5 — The bridge is unreachable in the real Linux shell.**
  - **Engine proof (positive and negative arms):** a small harness (scratch or `scripts/`, Developer's choice; not shipped) creates a pywebview GTK window with a `js_api` object whose method records each call, loading a page with a sandboxed `srcdoc` frame that calls `window.webkit.messageHandlers.jsBridge.postMessage` with a `js_api` call. Arm 1 (no removal): the call is recorded. Arm 2 (`remove_native_handlers` called from `loaded`): it is not recorded, and in a frame created after the removal `typeof window.webkit?.messageHandlers?.jsBridge` is `"undefined"`. Arm 3: a frame inserted **before** the removal (and that touched `jsBridge`) posts after it; **pass** is that the call is not recorded (WebKit may keep a stale handler object there, so `typeof` is recorded but not required).
  - **Product shell:** the real `the-one app` (scratch port ≥ 8490, scratch data dir under `$HOME`, scratch cwd, dev mode) with a seeded chat whose widget, on load, tries `pywebviewMoveWindow` through `jsBridge` and shows its result in large text. `GET /api/window/state` reads `native_bridge: "removed"` and the window position is unchanged (run the app with `GDK_BACKEND=x11` so a move would be observable under WSLg; record if that is not possible).
- [ ] **AC6 — Charts and widgets in WebKitGTK, both themes.** Through `scripts/webkitgtk_probe.py` against a scratch dev instance with a seeded chat holding a chart and a widget (and the escape battery from `tests/fixtures/widgets/escape.html` with `scripts/widget_sink.py`): DOM assertions that the chart draws, the widget card runs (an in-frame counter advances) and follows a theme switch, the escape grid shows no escape, and the sink count is 0, in the light and the dark theme. A screenshot of the real `the-one app` showing the same chat in each theme is recorded as evidence.
- [ ] **AC7 — The macOS probe (built here, run in Part C).**
  - `packaging/macos/probe/visuals.sh "$APP" "$APP_ID" "$OUT"`, run by a new step in `macos-packages.yml` under `inputs.mode == 'probe'` (observation-only, `continue-on-error`, its own `perl alarm` bound, writing `"$OUT"/SUMMARY.txt` and screenshots into the uploaded logs). It must not change the workflow's `on:` block, `release.yml`, or any `full`/`lifecycle` step.
  - It launches the installed product app with dev mode, a scratch port (≥ 8490) and a scratch data dir and cwd, the way `lifecycle.sh:204`, `:213` already do (`open --env THE_ONE_PORT=… --env THE_ONE_DATA_DIR=…`, plus `THE_ONE_DEV_MODE=true`; a binary-path launch must pass `app` explicitly, since `frozen_entry_mac.py` adds it only with no arguments), creates the credential, seeds a mock provider, an agent and a session holding a chart, a widget and the bridge-check widget (AC5's, which also prints its own result in large text so the screenshot carries it). Chats joins the most recently updated session on load (`session-state.js:284`), so the seeded session is created last or given the newest `updated_at`. It records:
    - `GET /api/window/state` `native_bridge` (expect `"removed"`) and the window position before and after the bridge-check widget ran (`lib.sh` `window_state`);
    - whether a print dialog or any new window appeared (System Events window list);
    - `screencapture` of the chat in the light and the dark theme;
    - the next-launch check after the quit Apple event (`osascript -e 'tell application id "$APP_ID" to quit'`, `lifecycle.sh:526`, the same event the Dock menu's Quit sends) and after `the-one quit --wait` (`:542`): relaunch, let the seeded chat open, screenshot; **pass** is no "stopped responding last time".
  - Each observation is a `PASS`/`FAIL`/`INFO` line in `SUMMARY.txt`, in `lifecycle.sh`'s `emit` style.
  - A dry check of the script's argument handling and its non-macOS refusal runs locally; `bash -n` and `shellcheck` (if installed) are clean.
- [ ] **AC8 — Docs.** `SECURITY-MODEL.md` "Live visuals": the bridge residual is replaced by the removal (both Cocoa handlers), its observable, and what it costs in the desktop app (`js_api`/`expose` calls, `evaluate_js` callbacks, `window.dom` events and easy-drag through the page no longer work; `window.alert` on GTK and `window.print()` on macOS throw in the main document; the app uses none of them, operator decision 2026-11-11); the crash-record residual states the quit-path result. `the_one/agents.md`: the desktop shell section and the test-patch rule's checklist name the new canary pins and the `removes_native_bridge` flag. CLAUDE.md only if an operator-facing fact changes (the `/api/window/state` field).
- [ ] **AC9 — Gates.** `ruff check`/`ruff format --check`; `THE_ONE_TEST_NETNS=1 make test-unit` (the known failures `tests/test_mcp_library_test_missing_values.py::test_cached_no_auth_posture_still_takes_the_branch_and_keeps_its_posture` and the order-dependent `test_evals_fingerprint` case are recorded, not fixed); the browser lanes whose files the leg touches (none expected; if `widget-lifecycle.js` changes, `contracts-widget-lifecycle` and `chats-widgets` with `THE_ONE_REQUIRE_WEBKIT=1`).

### Part B (operator at the Windows desktop; after squawk 0343)

- [ ] **AC10 — WebView2.** With `scripts/windows_test_copy.py` (`setup`, `launch --cdp-port`, Playwright `connect_over_cdp`), on a scratch port and data dir:
  - the seeded chart and widget chat passes AC6's DOM assertions in both themes, with the runtime version recorded;
  - the bridge regression probe: a frame call through `chrome.webview.postMessage` with a move does nothing (window rect unchanged), while the same call from the page moves it (positive control); `native_bridge` reads `"not-applicable"`;
  - AC4's next-launch check for tray Quit, `the-one quit` and `POST /api/window/quit`. If a path fails, the AC4 bounded clear covers Windows too (flag value updated, re-measured).

### Part C (outward; each dispatch confirmed with the operator)

- [ ] **AC11 — macOS.** The branch is pushed and `git rev-parse HEAD origin/<branch>` match. Then, each as its own command with its run id and head SHA recorded right after:
  - `gh workflow run macos-packages.yml --ref <branch> -f mode=lifecycle` reads **13 PASS** (the test-patch rule);
  - `gh workflow run macos-packages.yml --ref <branch> -f mode=probe`: `visuals.sh`'s summary shows `native_bridge` `"removed"`, no window move, no print dialog, both theme screenshots showing a drawn chart and a running widget, and the Dock Quit next-launch check passing. A `FAIL` is diagnosed and fixed in a new commit, then re-dispatched.

## Verification Steps
- AC1-AC3: the new unit tests and canaries; `pytest tests/test_boot_policy.py tests/test_desktop_*.py tests/test_pywebview_*_canary.py tests/test_window_*.py -x`.
- AC4-AC6: the Developer's measurement log in the flight log (commands, PIDs, paths, the on-disk key listing, screenshots' paths outside the repo).
- AC7: `bash -n packaging/macos/probe/visuals.sh`; the workflow diff limited to the new step; `pytest tests/test_release_workflow.py tests/test_packaging_macos_*.py -x`.
- AC10: the Part B log; AC11: the two run ids, their summaries and the downloaded artifacts.

## Implementation Guidance
1. **The function and its seam.** Put `remove_native_handlers` in its own module under `the_one/interfaces/desktop/`; reach the native objects through `webview.platforms.gtk.BrowserView.instances[window.uid]` (`.manager`) and, on Cocoa, `BrowserView.instances[window.uid].webview.configuration().userContentController()`. Import the backend modules lazily inside the function (the base install is GTK-free; the module must import on every OS). Store the result where `window_state()` can read it (`session_state.state`, reset by the autouse fixture).
2. **Wire it** as a separate `main_win.events.loaded +=` handler next to `shell.py:927`, behind `state.policy.removes_native_bridge`. Each handler gets its own thread, so it neither waits on nor delays the splash handler's `_main_shown.wait(25)`.
3. **Pins and guard** (AC3), then the unit tests. Follow the test-patch rule: patch names in the module that defines them.
4. **Linux measurements** (AC4-AC6): start every instance on a scratch port ≥ 8490 and a scratch data dir under `$HOME`, from a scratch cwd; never 8484/8485 or the default data dir; record PIDs and stop only those. Seed sessions through `POST /api/chat/sessions` with `messages` (as `tests/browser/test_flow_chat_widgets.py:84-105` and `seeders.seed_session` do), so no send is needed. If AC4 fails on a path, implement the bounded clear and re-measure.
5. **The macOS probe script** (AC7): reuse `packaging/macos/lib.sh` (`window_state`, `shot`, `http`, `http_post`, `cred`, `wait_exit`, `tl`) and `lifecycle.sh`'s `emit` style and Dock Quit step. Getting the window onto the seeded chat is the hard part: check whether Chats auto-joins the most recent session on load; otherwise find an existing route (no new product route only for the probe without asking the Flight Director).
6. **Docs** (AC8). Stop after Part A: leave the leg `in-flight` (it is not done until Parts B and C pass), record Part A in the flight log, and report `[BLOCKED:part-b]` for the Flight Director. Any fix commit in Part B or C re-runs AC9's gates.

## Edge Cases
- **A frame inserted before the removal** may hold a reference to the handler object: AC5 measures it; if it can still post, report it (a reload-after-removal or an earlier removal point becomes a design question for the Flight Director).
- **The removal fails** (pywebview internals changed): `"failed"` in `/api/window/state`, an `error` log, and the canary fails in CI first.
- **GTK `loaded` fires on every main-frame load:** the call is idempotent.
- **A page frozen by a widget at quit:** the AC4 clear times out after 1 s and the quit continues; the next launch then shows "stopped responding last time" for that widget, which is correct.
- **WSLg/Wayland cannot move windows:** use `GDK_BACKEND=x11`; if the move observable is still unavailable, the harness arms (AC5) are the proof and the gap is recorded.
- **The hosted runner's dev mode:** the packaged app must accept `THE_ONE_DEV_MODE=true` from its environment; the probe must not leave state behind for later workflow steps (it runs in `probe` mode only).

## Files Affected
- `the_one/interfaces/desktop/native_bridge.py` (new), `shell.py` (`loaded` wiring), `boot_policy.py` (flag), `window_control.py` (`native_bridge` field), `session_state.py` (result slot); possibly `shell.py::_on_quit` and `macos_dock.py::TerminateWorker` (AC4 clear).
- `tests/test_pywebview_cocoa_canary.py`, `tests/test_pywebview_gtk_canary.py` (new), `tests/test_boot_policy.py`, `tests/test_desktop_*.py`/`tests/test_window_*.py` (new tests and shape pins), a new guard test.
- `packaging/macos/probe/visuals.sh` (new), `.github/workflows/macos-packages.yml` (one `probe`-mode step).
- `SECURITY-MODEL.md`, `the_one/agents.md`, possibly `CLAUDE.md` and `docs/widget-format.md`.

## Citation Audit
- `.venv/.../webview/platforms/gtk.py:143-147` - `UserContentManager` created, `register_script_message_handler('jsBridge')` in `BrowserView.__init__`, kept as `self.manager` - verified (research)
- `.venv/.../webview/platforms/cocoa.py:543`, `:575` - `browserDelegate` and `jsBridge` handlers added in `BrowserView.__init__` - verified (research)
- `.venv/.../webview/platforms/gtk.py:62`, `cocoa.py:466` - `BrowserView.instances` keyed by `window.uid` - verified (design review); `gtk.py:26` tries WebKit2 4.1 then 4.0, both with `unregister_script_message_handler(name)` - verified (design review)
- `.venv/.../webview/event.py:37-60` - each handler runs on a new thread; `util.py:211-221` `loaded` set after injection - verified (design review)
- `the_one/interfaces/web/static/js/areas/chat/session-state.js:284` - joins the most recent session on load - verified (design review)
- `packaging/macos/lifecycle.sh:204`, `:213`, `:526`, `:542` - `open --env` launch, binary launch, quit Apple event, `the-one quit --wait` - verified (design review)
- `the_one/interfaces/desktop/shell.py:1080` - `webview.start(_boot, private_mode=False, storage_path=...)` - verified (research)
- `the_one/interfaces/desktop/shell.py:921`, `:927` - `main_win.events.closing += self._on_closing`; `main_win.events.loaded += lambda: (_main_shown.wait(25), _destroy_splash())` - verified (Flight Director)
- `the_one/interfaces/desktop/shell.py:533-570` - `_on_quit`: `begin_quit`, `chrome.deregister`, `icon.stop`, `state.desktop_window.destroy()` at `:562` - verified (Flight Director)
- `the_one/interfaces/desktop/macos_dock.py:124-180` - `TerminateWorker` with injected `drain`, `run()` order boot wait → drain → reply - verified (Flight Director)
- `the_one/interfaces/desktop/boot_policy.py:38-78` - frozen `BootPolicy` fields; `tests/test_boot_policy.py:59`, `:67` decision table and full-field coverage - verified (Flight Director)
- `the_one/interfaces/desktop/window_control.py:73-92`, `:140-153` - `_gtk_read` via `glib.idle_add`; `window_state()` dict with `mapped`, `tray` - verified (Flight Director)
- `the_one/interfaces/web/static/js/ui/widget-lifecycle.js:31`, `:196-214`, `:354-356`, `:406`, `:409-421` - record prefix, `scanRecords`, `onPageHide`, listener, `release` - verified (Flight Director)
- `tests/test_pywebview_cocoa_canary.py` - AST-only Cocoa pins, none on the bridge - verified (Flight Director)
- `.github/workflows/macos-packages.yml` probe steps (~`:290-335`) and Summary step - verified (Flight Director); `tests/test_release_workflow.py:52-59` pins `release.yml` inputs only - verified
- `tests/browser/test_flow_chat_widgets.py:84-105` - seeded-history helper - verified (research)
- `scripts/windows_test_copy.py:59-60` - `PYTHON_WIN = "/mnt/c/Python311/python.exe"` (squawk 0343) - verified (research)
