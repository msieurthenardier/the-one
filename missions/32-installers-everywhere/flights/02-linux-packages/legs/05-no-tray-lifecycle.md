# Leg: no-tray-lifecycle

**Status**: completed
**Flight**: [Linux packages](../flight.md)

## Objective
Finish the desktop lifecycle the mission asks for on a Linux desktop with no tray:
- closing hides the window, and a one-time desktop notice explains how to get it back and how to quit;
- launching again shows it, raised;
- `the-one quit` (and the "Quit GleepGlorp AI" launcher action that leg 7 renders) quits it;
- a newer launch replaces an older running instance (DD13).

The quit route also covers the boot, browser-fallback and `serve` states.

## Context
- **Flight DDs:**
  - DD4: the three close states, hide and notice, the quit path end to end, the route states, `pid`, the focus route with the activation token;
  - DD13: the version takeover, the pid wait, the old-server fallback, the version order;
  - DD12: never block the close path; lazy imports moved to boot.
- **State after legs 2-3** (landed or code-complete, uncommitted, in this worktree):
  - `shell.py`:
    - `_tray_mode` (`indicator`/`xembed`/`none`/`failed`/None);
    - `_session`;
    - `_is_gtk_backend`, `_on_wayland`;
    - `_show_window(window, *, restore=False)`;
    - `_gtk_read`, `window_visible`, `_window_mapped`;
    - `window_state()`, whose `mode` is `"window"` or None; `quit_desktop()`; `focus_window`.
  - `_on_closing` is registered in every tray mode. With `self._icon is None` it currently **allows** the destroy (the interim; leg 3).
  - `_close_to_tray` still has the old `_icon is None` → `destroy()` branch.
  - `app.py`:
    - `GET /api/window/state` and `POST /api/window/quit` (`{"quit", "pid"}`);
    - `window_focus` is a plain `def`.
  - `desktop_host.send_notification(summary, body)` (leg 2) never blocks; it runs a daemon thread.
- **`_select_port`** decides "ours" by credential (a 200 from `/api/info` with our credential), whatever the version. The `is_ours` branch posts `/api/window/focus` and returns.
- **`api_credential.lookup_credential()`** is the read-only lookup (returns None with no file). `get_credential()` creates on first use, so `quit` must not use it.
- **Not this leg:** the `.desktop` templates and their "Quit GleepGlorp AI" action (leg 7, which calls `the-one quit`); the VM relaunch check (leg 6).

## Phases (one leg, two Developer sessions)
Design review cycle 1 sized this leg at more than one session. It runs as two sequential phases, each a separate Developer spawn. The leg stays `in-flight` between them.

- **Phase A:**
  - the close states, `_no_tray_hide`, the markers, the module-scope imports;
  - the lock and flags, `quit_desktop`, `mode`, the quit route;
  - `the-one quit`;
  - the CLAUDE.md, `SECURITY-MODEL.md` and stale-comment fixes;
  - the smoke close, relaunch and quit checks;
  - ACs 1, 2, 3, 6, 7, and the phase-A part of 8.
- **Phase B:**
  - the focus token;
  - the `is_ours` takeover, the comparator, the pid wait;
  - the takeover smoke runs;
  - ACs 4, 5, the phase-B part of 8, and 9.

## Inputs
- `the_one/interfaces/desktop/shell.py`, `notice.py`, `host.py`
- `the_one/interfaces/web/app.py` (window routes)
- `the_one/main.py::cli_entry`
- `the_one/api_credential.py::lookup_credential`
- Tests: `tests/test_desktop_shell.py`, `tests/test_desktop_tray.py`, `tests/test_window_routes.py`, `tests/test_window_focus.py`, `tests/test_desktop_host.py`, `tests/conftest.py::stub_desktop_host`
- leg 3's smoke harness (`packaging/spike/gtk-smoke.sh`), if it has landed by then

## Outputs
- **`shell.py`:**
  - **The three close states:**
    - `_on_closing`:
      - really-quit: allow;
      - tray running (`self._icon is not None`): today's close-to-tray hide;
      - `_tray_mode == "none"`: **hide** through `_no_tray_hide()`, then return False (cancel the destroy);
      - `_tray_mode == "failed"` (or None on a non-Linux path with no tray): allow the destroy, as today's F4 fallback.
    - **`_on_closing` is registered right after `create_window`,** before the tray decision, with `_tray_mode` still None, which means "allow". That way an X-button press during the D-Bus/Xlib tray probes cannot leave an unregistered window.
    - Remove `_close_to_tray`'s dead `_icon is None` → `destroy()` branch, or reduce it to a return. Nothing reaches it now.
  - **`_no_tray_hide()`:**
    - `_desktop_window.hide()`, caught (a failure allows the destroy instead);
    - mark the tracked visibility False;
    - then, once, the notice: `desktop_host.send_notification("GleepGlorp AI", "GleepGlorp AI is still running. Open it again to bring it back, or right-click its icon and choose Quit GleepGlorp AI.")`;
    - recorded through a **separate marker**: `notice.py` gains `no_tray_notice_shown()`/`mark_no_tray_notice_shown()` with marker `.no_tray_notice_shown`. The existing tray marker functions are unchanged.

    `send_notification` returns at once, so the GTK main thread never blocks (DD12).
  - **Imports moved to module scope.** `window_state`, `notice`, `tray` (its GUI imports stay lazy inside its functions), `host` and `the_one.__version__` are all GUI-free. They are imported at module scope in `shell.py` and referenced from the close and quit path: `_on_closing`, `_no_tray_hide`, `_save_current_geometry` (`save_state`), `quit_desktop`, `window_state()`. A `.deb` upgrade replaces the bundle on disk under a running N, and a later lazy import could load N+1 code (DD12). The "pystray never imported in none mode" rule still holds, because `tray`'s pystray import is inside `build_tray`.
  - **Pending quit and the boot race (DD4):**
    - A module-level `_window_lock` (a `threading.Lock`) and `_quit_requested` flag.
    - **`_booting = True` is set right after the `is_ours` return and `settings.port = sel_port`,** before the server thread starts. It is cleared on every exit path:
      - step 6 (under the lock, with the publish);
      - the `_boot` except path;
      - the `SystemExit` for a missing pywebview;
      - entry to the browser branch;
      - a `finally` in `run()`.
    - **`_on_quit` is never called while holding `_window_lock`** (it blocks on `icon.stop()` and `destroy`).
    - `quit_desktop()`:
      - under the lock: if a window is registered, run `_session._on_quit(_session._icon)` (after releasing the lock) and return `"window"`;
      - if a session is booting (a `_booting` flag set in `run()` before `webview.start` and cleared at step 6), set `_quit_requested` and return `"booting"`;
      - if the browser-fallback branch is active (a `_browser_server` reference to the uvicorn `server`, set in that branch), set `server.should_exit = True` and return `"browser"`;
      - else return `None`.
    - **`_boot` checks `_quit_requested`** (under the lock) after `splash.events.shown.wait(15)`, after `_wait_until_serving`, and before step 4b's show. If set:
      1. set `_main_shown` (to release the `loaded` handler thread);
      2. destroy the main window, if created, and the splash;
      3. return.

      On GTK, `create_window` inside the running loop already maps the window (`BrowserView.show()`'s `show_all()` when `main_level() != 0`), so a quit after creation flashes the window briefly. Accepted, and documented. `Window.destroy` (`_shown_call`, then `idle_add(close_window)`, with no closing handler yet) is safe there. `webview.start` should return once both windows are gone; the smoke run confirms it.
    - **At step 6,** publishing `_desktop_window`, clearing `_booting` and reading `_quit_requested` happen in one critical section. If the flag is set, run the quit right after releasing the lock.
    - **The browser branch:** on entry, take the lock and check `_quit_requested`. If set, return at once (the server drains in `finally`). Otherwise set `_browser_server` and clear `_booting`.
  - **`window_state()["mode"]`** becomes `"window"`, `"booting"`, `"browser"`, `"quitting"` (once `_really_quit` is set), or `"serve"`.
    - `"serve"` means `_session is None`. In `serve` mode the route imports the shell lazily, and its top-level imports are GUI-free; after `run()` returns, the `finally` has cleared `_session`.
    - Fix the `except` fallback dict in the state route, which returns `mode: None` today, to report `mode` from the same rule.
  - **The focus path (phase B):** `focus_window(activation_token=None)`.
    - **On GTK with a token:** clear `window.hidden`, then queue **one** idle (pywebview's `glib.idle_add`) that does `native.set_startup_id(token)`, `native.deiconify()`, `native.present()`. It replaces, never precedes, a plain `_show_window(restore=True)`; a plain present first could already be denied by focus-stealing prevention.
    - `Gtk.Window.set_startup_id()` is the GTK3 call. It parses a `_TIMEnnn` suffix for X11 and, on a realized window, passes the token to GDK; the dev host's libgdk-3 3.24.41 carries the `xdg_activation_v1` symbols.
    - Record each baseline's GTK version (`dpkg -s libgtk-3-0*`) in the flight log. Leg 6's VM check, through a real app-grid click, is the only proof of the Wayland path. `gio launch` and a terminal give no token, so headless checks cannot prove it.
    - Otherwise, today's `_show_window(..., restore=True)`. Mark the tracked visibility True.
  - **The `is_ours` branch (DD13, phase B).** `_select_port`'s `(port, bool)` return shape is unchanged: about 15 existing test call sites and the `the_one/interfaces/app.py` re-export pin it. The new behaviour lives in separate, individually stubbable functions: `_running_version(host, port) -> str | None`, `_request_quit(host, port) -> dict | None`, `_pid_alive(pid) -> bool`, `_now()`, `_sleep(s)`.
    1. `_running_version`: `GET /api/info` with our credential, returning `version` or None. None means "unknown", which is treated as "not older", so the focus path.
    2. **Compare** with a small documented comparator. `packaging` is not declared, and no dependency is added for this.
       - Parse `X.Y.Z[.devN]`; a `.devN` sorts before its release; dev numbers compare numerically (`dev9 < dev10`).
       - Anything unparseable means "not older".
    3. **Running is older:** call `_request_quit`.
       - **Accepted:** the answer is JSON with `quit is True` and an int `pid`. Wait until `_pid_alive(pid)` is False, polling about every 0.5 s, bounded by 75 s (`_graceful_shutdown`'s 60 s join plus margin).
         - `_pid_alive`: on POSIX, `os.path.exists(f"/proc/{pid}")`, or `os.kill(pid, 0)` catching `ProcessLookupError`. On Windows, `ctypes` `OpenProcess(SYNCHRONIZE)` + `WaitForSingleObject(h, 0)`. **Never `os.kill` on Windows,** where any signal but CTRL_C/CTRL_BREAK is `TerminateProcess`.
         - If the wait passes about 3 s, send one `send_notification("GleepGlorp AI", "Updating GleepGlorp AI…")`, which never blocks. No splash: webview is not initialised on this path.
         - After the pid exits, re-run `_select_port`, then start normally. Two near-simultaneous launches can still race; documented.
       - **`quit: false`** (a bare `serve` instance): log "a server-only instance holds the port", and do not wait or focus. Exit, as today's focus would have shown nothing.
       - **404/405** (an old server with no quit route): log "restart GleepGlorp AI to finish the upgrade", focus it at once, return.
       - **401/403** (something else holds the port, or a rotated credential): log that distinctly, and return.
       - **Other errors:** log, focus, return.
       - **Still alive at the bound:** log, focus, return. Never start a second server on the same data dir.
    4. **Same or newer:** today's focus POST. The POST forwards `XDG_ACTIVATION_TOKEN` (or `DESKTOP_STARTUP_ID`) from this process's environment as a JSON body `{"activation_token": "..."}`. The focus route accepts an optional body, and an empty body stays valid for older callers.
  - Fix the stale `_select_port` fall-through comment ("a different the-one VERSION lands here too"). `_select_port` decides by credential.
- **`app.py`:**
  - `POST /api/window/focus` accepts an optional JSON body `{"activation_token": str | null}` (a Pydantic model, all fields optional, a missing body allowed), still a plain `def`.
  - `POST /api/window/quit` returns `{"quit": bool, "pid": int, "state": "window"|"booting"|"browser"|null}`. `quit` is true for the first three states.
  - `GET /api/window/state` reports the new `mode` values.
- **`main.py`:** a new `quit` subcommand:
  - check `credential_path().exists()` first, so `lookup_credential()`'s missing-file warning never reaches stderr. Missing means print "GleepGlorp AI is not running." and exit 0. Then read it with `lookup_credential()`; a `CredentialFileError` gives a one-line error and exit 1;
  - `POST http://{settings.host}:{settings.port}/api/window/quit` with it;
  - print "GleepGlorp AI is quitting." on `quit: true`; "GleepGlorp AI is not running." on a connection error; "GleepGlorp AI is running as a server only (`the-one serve`); stop it with Ctrl+C." on `quit: false`; and a distinct line for 401/403 ("Another program, or a GleepGlorp AI with a different credential, is using port N.");
  - optionally wait up to 75 s for the returned pid to exit (`--wait`, the default when interactive, off otherwise; document it);
  - exit 0 on success or not running, 1 on an unexpected answer.

  Add `quit` to the usage text. The desktop launcher action (leg 7) runs `the-one quit` (the `.deb`) or `<AppImage> quit`.
- **`SECURITY-MODEL.md`:** extend leg 3's paragraph. The focus route accepts an activation token, which is opaque, used only to raise our window, and never logged in full.
- **CLAUDE.md:** the "ours-by-version (attach a window only)" phrase in the Desktop launcher paragraph is corrected to "ours by credential (attach a window, or replace an older running version)". A one-phrase edit in a shared file, additive in intent. The new `the-one quit` command is listed in the Commands block, one line.
- **Tests:**
  - Close states: tray hides; `none` hides, notices once, a second close shows no notice, and a hide failure allows the destroy; `failed` allows.
  - Separate markers.
  - The notice is called and never blocks (the stub returns at once).
  - `quit_desktop` per state, including the boot race: a quit between show and publish is honoured, simulated with the lock and flags.
  - `mode` values.
  - The focus token: GTK sets the startup id then presents, with no token means today's path, and the route accepts a body or no body.
  - The `is_ours` takeover: older → quit + pid wait + start; same or newer → focus; old server 404 → focus, no wait; pid never exits → focus at the bound (a stubbed clock and process check, no real 75 s).
  - The version comparator, incl. `0.11.8 < 0.11.9.dev1 < 0.11.9`, matching dpkg's `0.11.8 < 0.11.9~dev1 < 0.11.9` (a table test; dpkg's order hard-coded from `dpkg --compare-versions`, run once on the dev host and recorded).
  - `the-one quit`, every output branch, with an httpx mock or a local stub server; no real app.
- **The smoke harness, extended** (if leg 3's harness landed). A run in `none` mode on each baseline:
  - close → `visible: false`, the process alive;
  - relaunch → `visible: true`;
  - `the-one quit` → the process exits within 15 s.

  Plus one takeover run: install the leg 1 N `.deb` (built from the old tree) and start it, install a scratch N+1 built from this tree, launch N+1, and assert N exits and N+1 is serving. N predates this flight's quit route, so the expected path is "old server lacks the quit route → focus it": record it. Then a second takeover from an N built from **this** tree (`0.11.9.dev3`) to a higher scratch version (`0.11.9.dev4`) proves the full quit-and-replace path.

## Acceptance Criteria
- [ ] **AC1** — the three close states behave as specified (unit tests), and the notice text and once-only marker are separate from the tray's.
- [ ] **AC2** — module-scope imports. An AST assertion in a unit test shows `_on_closing`, `_no_tray_hide`, `_save_current_geometry`, `quit_desktop` and `window_state` contain no `import` statements. `_on_closing` is registered before the tray decision.
- [ ] **AC3** — `quit_desktop` and the quit route cover `window`, `booting` (at each check point: after the splash wait, after the server wait, before show, at step 6), `browser` (including a quit arriving during the browser branch's server wait) and `serve`. Unit tests prove the boot race is closed; none calls `_on_quit` under the lock. `GET /api/window/state` reports the matching `mode` (including `quitting`), also in the route's `except` fallback. A unit-wide guard (a conftest autouse that fails any `httpx` call to port 8484/8485, or an equivalent assertion) proves no unit test reaches the operator's port.
- [ ] **AC4** — the focus route accepts an optional activation token (Pydantic `max_length=256`, no whitespace; only a short prefix is ever logged). On GTK the shell applies it in **one** idle (`set_startup_id`, `deiconify`, `present`) and no other present is queued: unit test with a fake native window. Older callers with no body still work (`tests/test_window_focus.py` passes).
- [ ] **AC5** — the version takeover, unit-tested through the named seams (no real clock, no real 75 s):
  - older + accepted: wait, then start;
  - older + `quit: false`: no wait, no focus;
  - older + 404: immediate focus;
  - older + 401: distinct log;
  - older + never exits: focus at the bound;
  - same or newer: focus;
  - unknown version: focus.

  Also:
  - `_pid_alive` never calls `os.kill` when `sys.platform == "win32"` (a test asserts it);
  - the comparator table matches dpkg's order, verified on the dev host: `0.11.8 < 0.11.9.dev1 < 0.11.9` ↔ `0.11.8 < 0.11.9~dev1 < 0.11.9`; `0.11.9.dev3 < 0.11.9.dev4`; `0.11.9.dev9 < 0.11.9.dev10`.
  - The existing `tests/test_window_focus.py` `is_ours` tests are updated to stub `_running_version` (None), and still assert exactly one focus POST.
- [ ] **AC6** — `the-one quit`: every branch unit-tested; it never creates a credential file (a test with no file asserts none exists afterwards); it is listed in the usage text and CLAUDE.md Commands.
- [ ] **AC7** — the stale `_select_port` comment and CLAUDE.md phrase are corrected, and `SECURITY-MODEL.md` is extended.
- [ ] **AC8** — real-GTK checks, on both baselines (if leg 3's harness exists; otherwise recorded as deferred to leg 6, with the reason):
  - in `none` mode, close hides and the process stays alive;
  - a relaunch shows;
  - `the-one quit` exits within 15 s;
  - the takeover from a this-tree N to N+1 replaces it;
  - the takeover from Flight 1's N focuses it.
- [ ] **AC9** — gates:
  - `make test-unit` passes (12 skips);
  - `ruff` clean;
  - `shellcheck` on any changed scripts;
  - the browser `settings` lane passes with `THE_ONE_TEST_NETNS=1`;
  - no `m32-` container left running;
  - no 8484/8485;
  - the operator data dir untouched.

## Verification Steps
- AC1-AC7: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_desktop_shell.py tests/test_desktop_tray.py tests/test_window_routes.py tests/test_window_focus.py tests/test_desktop_host.py tests/test_cli_quit.py -x --timeout 30`, then `make test-unit`.
- AC8: the smoke harness output and evidence under `$HOME/the-one-m32-evidence/f2/leg5/`.
- AC9: the commands named.

## Implementation Guidance
1. Read the current `shell.py` end to end; legs 2 and 3 changed it substantially. Map every place `_desktop_window`, `_session`, `_tray_mode` and `_really_quit` are read or written.
2. The close states, `_no_tray_hide`, the markers, and moving imports to boot.
3. The lock, the flags (`_booting`, `_quit_requested`, `_browser_server`), `quit_desktop`, and the `mode` values. Reset every new module global at the top of `run()`, as the existing ones are.
4. The focus token: route body, shell, GTK idle.
5. The `is_ours` takeover and the comparator. Keep the network calls behind small functions that tests can stub.
6. `the-one quit` in `main.py`.
7. Docs (CLAUDE.md phrase plus the Commands line; `SECURITY-MODEL.md`).
8. Unit tests, then `make test-unit`, then the smoke checks.
9. The flight-log section `### no-tray-lifecycle`.

## Edge Cases
- **Hide fails on GTK** (the window already gone): allow the destroy, so the app exits rather than stranding.
- **Quit requested during the takeover's own wait:** the new process has no window yet. A `the-one quit` from a third launch reaches whichever server answers the port. Acceptable; document it.
- **Two quick relaunches while hidden:** both focus. Idempotent.
- **`the-one quit` against a running instance on another port** (`_select_port` case c): unreachable; the guide documents it (DD4).
- **`AppRun` and the frozen entry must pass `quit` through** (in `AppRun`, a no-argument run means `app`). This is a leg 7 reminder; record it in the flight log.
- **A same-version `serve`-only instance and `the-one app`:** unchanged (a focus POST that answers `focused: false`, then exit). Log it clearly; no new behaviour.
- **`serve` mode under the takeover:** `/api/window/quit` answers `quit: false` (`state: null`). The new launch then cannot replace a bare server: it logs and exits, and never starts a second server on the same data dir.
- **Windows:** the takeover applies (`shell.py` is shared, DD13). Inno normally closes the old instance first. The Windows unit tests must still pass, and the Windows-specific show path is unchanged.
- **Python 3.11:** CI runs 3.11. Nothing newer.

## Files Affected
- `the_one/interfaces/desktop/shell.py`, `the_one/interfaces/desktop/notice.py`
- `the_one/interfaces/web/app.py`
- `the_one/main.py`
- `SECURITY-MODEL.md`, `CLAUDE.md` (one phrase plus one Commands line)
- `tests/test_desktop_shell.py`, `tests/test_desktop_tray.py`, `tests/test_window_routes.py`, `tests/test_window_focus.py` (the `is_ours` tests stub `_running_version`), `tests/test_cli_quit.py` (new), `tests/conftest.py` (the 8484/8485 guard)
- `packaging/spike/gtk-smoke.sh` and its inner script (extended, if present)
- `missions/32-installers-everywhere/flights/02-linux-packages/flight-log.md` (own section)

## Citation Audit
Checked against the worktree after legs 2-3 (uncommitted):
- `shell.py` module globals `_really_quit`, `_desktop_window`, `_tray_mode`, `_session`; functions `_show_window`, `_gtk_read`, `window_visible`, `_window_mapped`, `window_state` (`mode`: window/None), `quit_desktop`, `focus_window`. Verified.
- `shell.py::run` `is_ours` branch: `httpx.post(.../api/window/focus, headers=Authorization)`, then return. Verified.
- `shell.py::_close_to_tray`: the `_icon is None` → `destroy()` branch is still present. Verified.
- `notice.py`: `_MARKER_NAME = ".close_to_tray_notice_shown"`, `notice_shown`, `mark_notice_shown`. Verified.
- `api_credential.py::lookup_credential` (read-only, line 330) and `get_credential` (creates). Verified.
- `main.py::cli_entry`: `if/elif` dispatch; usage text. Verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
