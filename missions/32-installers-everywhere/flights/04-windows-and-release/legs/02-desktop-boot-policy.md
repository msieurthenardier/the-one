# Leg: desktop-boot-policy

**Status**: landed
**Flight**: [Windows on shared metadata, and one release](../flight.md)

## Objective
Move every per-platform decision in the desktop shell's boot sequence and window control into one `BootPolicy`. The aim is that `shell.py` and `window_control.py` read no `sys.platform` and do not branch on a policy's identity. This is phase 2a: the move, plus the Windows tray-hide `visible` fix.

Then fix squawk 0261 (the blank macOS splash) as a separate phase, 2b. Both are proven by unit tests, the Linux GTK smoke and one standalone macOS `lifecycle` run.

## Context
- **Flight DD1 is the full contract:** the decisions the policy owns, lazy selection through `state`, the guard, behaviour equivalence, phases 2a and 2b, and the attribution of macOS run rows to phases.
- **Flight DD9:** squawk 0261's fix rides here, in 2b.
- **A product defect found in leg 1's design review, fixed in 2a:**
  - On Windows (any non-GTK, non-darwin backend), `window_control.window_visible()` returns `state.tracked_visible`.
  - `shell.py::DesktopSession._close_to_tray` calls `state.desktop_window.hide()` but never clears that flag. Only `window_control._no_tray_hide` sets it False.
  - So `GET /api/window/state` says `visible: true` after close-to-tray. Leg 3b's lifecycle "state hidden" row depends on the fix.
  - It is a route-only fix for the non-GTK, non-darwin backend, and the one named exception to 2a's "no behaviour change". macOS reads `macos_dock.native_visible`, so its attribution is unaffected.
- **Flight 3's split guard,** `tests/test_desktop_split_guard.py`: patch a name in the module that defines it, and state lives on `session_state.state`.
- **Test fixtures:**
  - The autouse `_reset_desktop_session_state` fixture in `tests/conftest.py` resets `state` before and after every test.
  - Platform-patching tests: `tests/test_desktop_shell.py` (about lines 298-349, 1032, 1371, 1395), `tests/test_macos_dock_shell.py:67`, `tests/test_macos_dock.py:231` (a `darwin` fixture, then `quit_desktop()` after `state.reset()`), and `tests/test_macos_runtime_seam.py`.
  - The Architect counted 45 `sys.platform` monkeypatches across 6 files.
- **Leg 1's probe** (run `40242850115`) is unrelated to this leg's code. Its W1/W5 results only confirm the Windows rows leg 3b will rely on.

## Inputs
- Leg 1 is committed at `8676392`.
- `the_one/interfaces/desktop/shell.py` reads `sys.platform` 17 times:
  - darwin: 557, 729, 783, 848, 906, 947, 960, 990, 997;
  - win32: 705, 879;
  - linux: 908, 928, 933, 1027;
  - the `first_launch_size(..., sys.platform)` call: 674;
  - `_webview_available`: 286.
- `window_control.py` reads it 4 times: 100, 165, 170, 228.

## Outputs
- `the_one/interfaces/desktop/boot_policy.py` (new): `BootPolicy`, three instances (Windows, Linux, macOS), and `current()`.
- `the_one/interfaces/desktop/session_state.py`: a `policy` field, filled lazily on first read and cleared by `reset()`. A property or an accessor, whichever matches the file's style.
- `shell.py` and `window_control.py` call the policy for every decision that used to read `sys.platform`.
- `_close_to_tray` clears `tracked_visible` on a successful hide (2a's exception).
- Tests:
  - the guard test;
  - a decision-table test;
  - a `tracked_visible` test;
  - updated patch targets where needed;
  - 2b's tests.
- `squawks/0261-macos-splash-card-blank.md`: the corrective action, verification and status. It is marked `completed` at the flight commit, after review.
- The flight log: the leg entry, including the macOS run's row-to-phase table.

## Acceptance Criteria

### Phase 2a: the move
- [x] **AC1:** `boot_policy.py` defines `BootPolicy` and four instances.
  - **Windows** for `win32`, **macOS** for `darwin`, **Linux** for any `linux*`.
  - **Other** for anything else. It reproduces today's fallthrough exactly:
    - the gi probe in `_webview_available`;
    - `build_tray` with no detection and no `tray_mode` write;
    - a re-raise on a show failure;
    - no browser-fallback notification.
  - The Linux policy differs from today's fallthrough, so it must not stand in for it.
  - **The policy is pure data:** flags, plus hooks over primitives. `boot_policy.py` imports only the stdlib. It holds no references to `macos_dock`, `desktop_host`, `tray`, `chrome` or pywebview functions. Every such call stays in `shell` or `window_control`, reached through the module attribute, so the existing monkeypatches keep working. Importing the policy from `session_state` therefore creates no import cycle.
  - **The tray decision** is a plan the policy returns, such as `(detect, records_tray_mode, skip)`. The detection calls (`desktop_host.choose_pystray_backend`, `detect_tray`) and `_NoTrayError` stay in `shell`.
  - **`name`** is for logs and tests only.
- [x] **AC2:** every decision listed in flight DD1 is a hook or flag on `BootPolicy`, and each of the 21 reads maps to one. The flight log carries a table: read site (old line) → hook → per-policy value. A read that cannot become a hook without a behaviour change stops the leg (`[BLOCKED:…]`), which is the flight's divert criterion.
- [x] **AC3:** `git grep -n "sys.platform" the_one/interfaces/desktop/shell.py the_one/interfaces/desktop/window_control.py` prints nothing.
- [x] **AC4:** a new `ast` guard test (in `tests/test_desktop_split_guard.py` or beside it) fails, in those two files, on:
  - any platform read: `sys.platform` (including `from sys import platform`, `import sys as x`, `getattr(sys, "platform")`), `os.name`, or the `platform` module;
  - any identity check on a policy: `policy.name`, `isinstance`, `type(policy)`, `policy is/== <instance>`.
  - AC3's `git grep` also matches comments, so write no comment containing that literal.

  A deliberately inserted read in a scratch copy is shown to fail it (record the falsification in the flight log, then revert).
- [x] **AC5:** `state.policy` is lazy. Its first read takes `boot_policy.current()`, and `state.reset()` clears it.
  - `run()` binds `policy = state.policy` once, right after its `state.reset()`, and `_boot`'s closures use that binding. So there is no first-read race on the `_boot` thread and no mid-run flip.
  - `window_control`'s functions, called with no `run()` (HTTP routes in `serve` mode, tests), read through `state` and see the platform patched before their first read. A test pins this.
  - `tests/test_desktop_session_state.py`'s defaults test gains a "`policy` is unset" assertion.
- [x] **AC6:** a decision-table test asserts each hook's value or behaviour for each of the three policies. These are the old branches' semantics, written as data.
- [x] **AC7:** behaviour equivalence. Every existing desktop test passes. Where a test must change, it changes only its patch target (under the split guard's rule), never its assertion. The flight log lists every changed test, with the reason for each.
- [x] **AC8:** the tray-hide fix. After a successful `hide()`, `_close_to_tray` calls a new `window_control._mark_hidden()`. The call is unconditional; it is harmless on GTK and darwin, which read the native state.
  - `_no_tray_hide`'s direct `state.tracked_visible = False` goes through `_mark_hidden` too, so the flag has one writer module.
  - `_mark_hidden` is added to `window_control`'s name list in `tests/test_desktop_split_guard.py`.
  - Unit tests run at the backend level (`_is_gtk_backend` false): hide then state is False; hide, then show through the tray Show callback, the boot show or `focus_window`, then state is True. Every show path already calls `_mark_visible`.
- **Out of scope, stated so AC3 is not misread:** `chrome.py::_native_enabled` (win32) and `takeover.py::_pid_alive` (win32) keep their own `sys.platform` reads. They are Windows-API gates that tests patch directly, so the policy does not cover them.

### Phase 2b: squawk 0261
- [x] **AC9:** 2b is one policy flag, `splash_hidden_until_loaded`, set True on macOS only. With it set, the splash is created `hidden=True` and shown after its own `loaded`, with a short bound (at most 3 s; record the value and why).
  - The pywebview 5.4 facts the design rests on (cite them):
    - Cocoa's `first_show` (`webview/platforms/cocoa.py`, about 643-652) sets `shown` even for a hidden window, so `splash.events.shown.wait(15)` does not block;
    - `first_show` starts the loop with only the hidden splash;
    - `Window.show()` is `_shown_call`-wrapped (`webview/window.py`, about 334-346), so a show from the `loaded` handler thread is safe;
    - the splash is created before `start()`, so subscribing to `loaded` right after `create_window` cannot race. The `is_set()` check is only a backstop.
  - Hazards to handle:
    - the show must be guarded by `_splash_closed` and `_splash_blocked`, with a try/except, because it can arrive after `_destroy_splash`, a terminate or a stopped loop (a `BrowserView.instances` `KeyError`);
    - the bound runs on a daemon timer that is cancelled on quit;
    - an ordered-out WKWebView may not have painted at `loaded`, so consider a short settle or an `evaluate_js` round trip, and record the choice;
    - `MAIN_LOADED_BOUND` may show the main window before the splash bound, so the splash is destroyed while still hidden. Test that.
  - Check that `tests/test_macos_dock_shell.py`'s splash mocks still pass. A new `hidden` kwarg on the darwin path only is a 2b change, and is recorded.
  - If the only correct fix needs a change to the shared boot sequence beyond the darwin splash path, stop 2b, record it, and escalate the squawk. 2a then ships alone.
  - Linux and Windows splash behaviour is unchanged (the decision-table test pins it).
- [x] **AC10:** 2b's unit tests cover:
  - the splash staying hidden until `loaded` on darwin;
  - the bound firing when `loaded` never comes;
  - no change on the other two policies.

### Both
- [x] **AC11:** `make test-unit` passes (12 skips expected; read `-rs` if different). Ruff check and format are clean. The pywebview canary (`tests/test_pywebview_cocoa_canary.py`) passes.
- [x] **AC12:** after 2b, a fresh `.deb` passes the GTK smoke with `OVERALL PASS`:
  - build: `M32_BUILD=$HOME/the-one-m32-build/f4 packaging/linux/build.sh --version 0.11.9.dev40`;
  - smoke: `packaging/linux/checks/gtk-smoke.sh ubuntu-26.04 --deb <the .deb> --evidence $HOME/the-one-m32-evidence/f4/leg2`;
  - check first that no other `m32-gtk-smoke-*` container is running (`docker ps`);
  - leave no containers and no root-owned files.
- [x] **AC13 (the Flight Director, outward):** one standalone `macos-packages.yml` `-f mode=lifecycle` dispatch from the pushed branch, carrying both 2a and 2b (two commits).
  - Every `A/SUMMARY.txt` and `lifecycle/SUMMARY.txt` row passes.
  - **L1's +1 s screenshot:**
    - it proves 2b only if it shows the splash's logo and text;
    - a painted main window, or a blank card that matches Flight 3's known-blank result for a data-URL window on the runner (Flight 3 DD11), reads **inconclusive**, not PASS.
    - If inconclusive, 2b ships, and squawk 0261 stays `in-progress` until the contributors' check on real Macs confirms it (DD10).
  - **Attribution:** a red non-splash row could come from either phase, because 2b changes the splash lifecycle. The spare run is then spent with `splash_hidden_until_loaded` set False (one flag), to bisect. A fifth macOS run needs the operator.
  - The run id, minutes and the row table go in the flight log. This is macOS run 1 of the flight's 4.

## Verification Steps
- AC1-AC8: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_desktop_split_guard.py tests/test_boot_policy.py tests/test_desktop_shell.py tests/test_desktop_session_state.py tests/test_desktop_tray.py tests/test_desktop_takeover.py tests/test_window_state.py tests/test_macos_dock.py tests/test_macos_dock_shell.py -x --timeout 30`, plus the AC3 `git grep`. (`tests/test_macos_runtime_seam.py` patches the `platform/` seam, not the shell, so it is unaffected.)
- AC9-AC10: the 2b tests; the citations in the flight log.
- AC11: `make test-unit`, ruff.
- AC12: the build and the smoke commands, with `OVERALL PASS` quoted in the flight log.
- AC13: `gh run download <id>`; the summaries; the L1 PNG.

## Implementation Guidance
1. **Map first, then move.**
   - Read `DesktopSession.run`/`_boot` and `window_control` end to end, and write the AC2 table before changing code.
   - Many bodies are closures over `_boot` locals (`main_win`, `splash`, `_main_shown`, `_boot_errored`, `_abort_if_quit`, `self`). Prefer flags and small hooks that take what they need as parameters, over moving whole closures into the policy.
   - The policy decides; the shell still does the work. For example, `policy.wait_for_page_before_show` is a flag the shell reads, and the waiting code stays in the shell.
2. **Keep the native calls where they are.** The `macos_dock.*`, `desktop_host.*`, `tray.*` and `chrome.*` calls stay in the shell or `window_control`, behind policy flags (AC1). In the AC2 table, split the tray block (old lines 906, 908, 928, 933) into named decisions. Keep old 783 (`_abort_if_quit` on darwin) and old 947 (darwin `quit_now`) as two flags, unless the table shows they can never diverge.
3. **`_webview_available` and `first_launch_size`:** route their platform input through the policy (`webview_assumed_present`, `first_launch_platform` or similar). Keep `first_launch_size`'s own signature unchanged if other callers exist (grep first).
4. **2a and 2b are separate spawns.** The first Developer does 2a (AC1-AC8, AC11's unit tier for 2a), writes a "2a green" flight-log checkpoint, marks the leg's 2a criteria, and hands back with `[HANDOFF:review-needed]`. The Flight Director reviews and commits 2a. A second Developer then does 2b (AC9-AC12) on top of it. Keep 2b's diff confined to the darwin splash path, its flag and its tests.
5. **The tray-hide fix** goes in `_close_to_tray`: set `state.tracked_visible = False` after a successful `hide()`, through a `window_control` helper mirroring `_mark_visible` (for example `_mark_hidden`), so the flag has one writer module.
6. **Do not push, dispatch or open PRs.** The Flight Director runs AC13 after the checkpoint review and commit.

## Edge Cases
- **A test patches `sys.platform` after the policy was read in the same test:** it must call `state.reset()` (the flight's DD1 rule). If an existing test does this, fix the test's order and record it under AC7. That is a patch-target change, not an assertion change.
- **`serve` mode (no desktop session):** `window_control` routes still need a policy. The lazy `state.policy` covers it, since `current()` needs nothing from `run()`.
- **The browser-fallback branch** (Linux, no WebKitGTK): its notification decision (old line 1027) is a policy hook too. The fallback still works with no pywebview import.
- **A splash `loaded` that fires before the subscription** (2b): use the same "already set" check the main window's handler uses (`events.loaded.is_set()`).

## Citation Audit
Checked at `8676392`:
- `shell.py`: all 17 read sites, by line, as listed above: verified.
- `shell.py::DesktopSession._close_to_tray` (about 386-413): calls `hide()`, no `tracked_visible` write: verified.
- `window_control.py`: `_mark_visible` (46), `window_visible` (97-108), `quit_desktop` (165, 170), `focus_window` (228), `_no_tray_hide` (257-273): verified.
- `session_state.py::SessionState._set_defaults` / `reset`: verified.
- `shell.py`: `_splash_html` (148), `splash = webview.create_window` (696), `_destroy_splash` (736), `splash.events.shown.wait(15)` (799): verified.
- `packaging/linux/checks/gtk-smoke.sh` usage line: verified.
