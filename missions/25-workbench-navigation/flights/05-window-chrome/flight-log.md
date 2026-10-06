# Flight Log: Window Chrome

**Flight**: [Window Chrome](flight.md)

## Summary

**Status**: completed (2026-10-06). Five legs (leg 1 split into 1a and 1b at its design review), committed as `e91de9a` and opened as PR #221. The flight-end review was confirmed after two non-blocking fixes. The close gate `windows-window-chrome` passed 11 of 11 on the frozen build.

---

## Reconnaissance Report

**Sources:**
- the Flight 5 research digest (read-only reconnaissance of `b044cab`, the pywebview 5.4
  and 6.2.1 wheels, Microsoft Learn and the WebView2 specs, and the Windows host; kept in
  the Flight Director's scratchpad);
- the Flight 4 debrief's Flight 5 action item;
- the mission's Known Issues and the open design question for Flight 5.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Mission open question: "Window chrome mechanism" (spike non-client regions) | confirmed-live; answered by research and operator decision | pywebview 5.4 SDK 1.0.2957.106 has `IsNonClientRegionSupportEnabled`, but snap layouts need the prerelease-only window-controls overlay, and a frameless form loses resize | DD1: tinted native bar (operator, 2026-10-06). Close the mission question at landing. |
| Known Issue: Ctrl K in WebView2 (Flight 4 DD9) | confirmed-live | No packaged-build observation exists | DD9: crew-verified with a real `SendInput` key in leg 1 and at the close gate. The operator confirms at Flight 6. |
| F4 debrief: route any desktop shortcut through `App.shortcuts` | already-satisfied for this flight | The flight adds no shortcut | Recorded in DD13. |
| F4 debrief: respect the static drawer slot and `--drawer-w` | already-satisfied by design | The native caption is outside the page | DD13. The first-launch size puts the drawer in push mode. |
| The `agents.md` footgun note is imprecise for pywebview 5.4 | confirmed-live | `the_one/agents.md` lines 66–74, against 5.4 `util.py` and `customize.js` | Corrected in leg 2 (DD13). |
| First launch opens at 800×600 | confirmed-live | `shell.py` passes no size without `window-state.json`; the 5.4 defaults | Leg 3 (DD6). |
| A white flash before a dark page paints | confirmed-live | 5.4 `background_color='#FFFFFF'` default | Leg 2 (DD4). |
| The splash's hard-coded `#0f1117` | confirmed-live | `shell.py` lines 51 and 143 | Leg 2 (DD4). |
| `windows-native-frame-splash` step 9 is stale under the credential gate | confirmed-live | The spec's own Preconditions "Known gap" | Leg 4. |
| Restore drift at more than 100% scaling (pywebview multiplies `x`/`y` by the scale factor) | needs-human-recheck | Inferred from 5.4 `winforms.py`; the operator's screen is 100% | Out of scope. Not observable on this host; noted for the Flight 6 operator walk. |

---

## Leg Progress

### Leg 1a: windows-apparatus-core

Built `scripts/windows_test_copy.py` (WSL CLI plus a Windows half piped to `C:\Python311\python.exe -`) and `tests/test_windows_test_copy.py` (69 pure tests). No input sent, no DWM colours painted, nothing under `packaging/` or `the_one/` (except `agents.md`) touched. Docs: `the_one/agents.md` "Windows test copy (M25 F5 L1a)" and one `CLAUDE.md` sentence.

**Windows sessions** (every one bracketed by `snapshot --out` / `--compare`; installed app stayed pid 208344 on 8484 throughout):

| Session | Contents | Compare |
|---|---|---|
| 1 | `doctor-host`; first `setup`; `snapshot --out` before | clean (`ok`, no allowed changes) |
| 2 | second `setup`; 7 refusals (8484, 8485, 8489, operator dir, `..` into operator dir, 2 bad roots, all exit 2, nothing started); source `launch` on 8490/9390 + `/api/live` 200 + `/api/info` 200; `tree`/`windows`/`rect`; `stop`; watchdog launch (`--max-minutes 1`); the premise-5/8 spike (`launch --script`, ports 8491/9391); `stop` | clean |
| 3 | `freeze`; `doctor --frozen`; frozen `launch` on 8492/9392; `rect`; `stop` | clean |

**Times:** first `setup` 325s (copy of 2168 files 130.5s, venv 17.7s, pip uv 8.9s, uv export 5.2s, closure 146.8s, editable 8.4s); second `setup` 7.5s (copied 1 file, venv up to date). `freeze` 113.7s (pip pyinstaller 21.8s, PyInstaller 91.0s), no extra steps needed beyond CI's. Frozen `doctor`: exit 0, `RESULT: PASS`, **9 gates**, all four CI needles present. `stop` returned in about 5s with both ports free; `audit.log` lists every kill (identity-checked, one handle). Watchdog: after 1 minute it stopped its tree itself (actor `watchdog` in `audit.log`, `tree` empty, ports free). A listener on 8888 (pid 6808) is the operator's, not ours.

**Premise table**

| Premise | Method | Observed | Verdict | Consequence for legs 2-3 |
|---|---|---|---|---|
| 5: `window.chrome.webview` at document start; `window.pywebview` / `pywebviewready` on the main window of a two-window spike | `launch --script` spike (splash + main, local HTTP page on 8491, inline head script recording state); read over CDP with the repo Playwright | `chrome.webview` present at document start in BOTH windows (`postMessage` is a function). `window.pywebview` absent at `DOMContentLoaded` and `load`; `pywebviewready` fires afterwards (main 38ms vs load 18.7ms) with `pywebview` set. | Confirmed as planned | The page's desktop post must not assume `window.pywebview` at start: use `chrome.webview` presence for the desktop test and wait for `pywebviewready` (or poll) before using `pywebview`; the browser-test stubs (chrome.webview at start, pywebview injected late plus a dispatched event) match the real order. |
| 6: outer vs client rect vs `innerWidth`/`innerHeight` at 100% | `rect` on the real from-source copy plus CDP `innerWidth` | Outer 800x600 (880,396 to 1680,996); client 784x561; `innerWidth`x`innerHeight` 784x561, `dpr` 1; DWM extended frame bounds 786x593 (caption 31px, 8px side/bottom frame). The 1000x700 spike: client 984x661. | Confirmed: inner size equals the client rect exactly | Size maths: page size = window size minus 16 px wide and 39 px high at 96 DPI; first-launch size and clamp tests can compute from the client rect. |
| 8: `Handle` off the UI thread; HWND across `hidden=True` then `show()` | spike: read `main.native.Handle` from the boot thread, then `show()`, `hide()`, `show()`, comparing with `EnumWindows` | `InvokeRequired` True yet the read raised nothing; HWND 2885032 existed while hidden and was identical after `show()`, `hide()` and `show()`; also matches the `windows` listing. Handles only, no colours. | Confirmed | A DWM colour call can run from the boot thread against a cached HWND, created hidden, with no re-fetch after `show()`; the first-paint order can set colours before show. |
| 10: CDP via `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` on the real copy | `launch --cdp-port 9390` (source) and 9392 (frozen); `connect_over_cdp` from WSL | `/json/version` and Playwright answered over mirrored localhost (Edg/154.0.4258.53); one page `http://127.0.0.1:8490/#chats`; the variable is the only channel (pywebview 5.4 + `storage_path` ignores its own). Without `--cdp-port` the variable is not set. | Confirmed | Legs 2-3's page actions and `prefers-color-scheme` emulation can use one CDP session per run on 9390+. |
| 12: freeze time | `freeze` | 113.7s total (PyInstaller 91s) | Well inside the 20-minute bar | The "No local freeze" variation does not apply; the frozen build is available at `R\src\dist\the-one\`. |

**Deviations / notes.** (a) The `windows`/`rect` listing includes `frame_bounds` (DWM extended frame bounds), an addition for premise 6. (b) Hands-off and the `.env` refusal run inside the Windows half after validation, so a refused launch never waits. (c) The scratch root `C:\Users\cprch\AppData\Local\Temp\the-one-f5\` is left in place (src, venv, dist, logs, audit.log, spike, data dirs). `LongPathsEnabled` is 0 and nothing needed it. `doctor-host`: build 26200 UBR 9457 (25H2), WebView2 154.0.4258.53, 96 DPI, both themes light, transparency on, `ColorPrevalence` 0, no `WEBVIEW2_*`/`THE_ONE_*` variables at user or machine level, mirrored networking, session 1 unlocked, excluded ranges 5357 and 50000-50059. Nothing of ours remains running on either side.


### Leg 1b: windows-apparatus-input

Extended `scripts/windows_test_copy.py` with the input and capture half and `tests/test_windows_test_copy.py` with 74 more pure tests (143 in all). No product code changed (`the_one/` apart from `agents.md`, nothing under `packaging/`); the DWM colour work was throwaway spike scripts (`spike_dwm.py` in the scratchpad's `f5-spike/`, started only through `launch --script`). Docs: `the_one/agents.md` "Windows test copy, input and capture (M25 F5 L1b)" and the `CLAUDE.md` sentence.

**What was built.** Commands `own-window show|close|do`, `front`, `front-trial`, `capture` (single, `--series`, `--print-window`, `--allow-own-cover`), `pixel`, `keys`, `release-all`, `click`, `drag` (`--caption` and default), `show-window`, `focus-save`/`focus-restore`, and the read-only `foreground`, `screen`, `hands-off`, `input-log`; a global `--run-id`. The gate rules are the leg's: one gate tree through `select_gate_pids` (own windows reserved ids, never a tree); hands-off before every gesture and focus change, then the foreground or pointer gate, then the send, with `record_injection` after every batch and the mid-gesture interference abort; the key grammar with its denylist; `WindowFromPoint` before any cursor motion, a re-check after `SetCursorPos`, button released in a `finally`, `cursor_restore_decision`; captures contained in DWM frame bounds with an exact z-order occlusion test before and after every grab (`covered_by_own`, `covered_by_tree`); the own windows with `WS_EX_NOACTIVATE`, `SW_SHOWNOACTIVATE`, an identity check and the allowlisted nonce/expiry command channel; identity-checked `focus-save`/`focus-restore`.

**Windows session** (one session, 17:36-17:48 UTC, run id `l1b-s1`, bracketed by `snapshot --out`/`--compare` and `focus-save`/`focus-restore`):

| Step | Result |
|---|---|
| `snapshot --out`, `hands-off`, `screen`, `foreground`, `focus-save`, `setup` | Installed app pid 208344 on 8484; work area 2560x1392, taskbar at the bottom; foreground was Windows Terminal (saved); `setup` copied 7 files in 15s |
| from-source copy on 8490/9390 (data dir `data-l1b-1`) | `/api/live` and `/api/info` 200; every command in the leg's list ran on it |
| spike trees on 8491/9391 and 8492/9392 (data dirs `data-l1b-spike1`, `-spike2`) | premises 1, 2, 3, 4, 7, 11 |
| `stop` of each tree, `focus-restore`, `own-window close`, sweeper `stop`, `snapshot --compare` | **clean**: `ok`, no allowed changes, installed app still pid 208344; `tree` empty; no process under the scratch root and nothing listening on 8490-8492 or 9390-9392 |

`focus-restore`: **3 of 3 restored** (after the premise-13 trials, after real-foreground trial 1, and the final one after real trial 2); the operator's Windows Terminal came back each time and no trial failed to restore. After `stop`, the foreground went to an own window or to Windows Terminal, so "the foreground is nothing" was NOT reached on this host. A minimise of the test window returned the foreground to Windows Terminal by itself.

**`input.log` summary** (193 rows, one run id): **sent 40, aborted 1, refused 18** (plus `ok` rows for captures, pixels and `focus-save`). Every `sent` row's target was the gate tree (18) or an own window (15), except `focus-restore` (3, target `operator`: the one explicitly specified restore of the operator's saved foreground, `SetForegroundWindow` only, no input) and `release-all`/`recover` (4, target `none`: three found nothing held; the one `recover` row is the defect below). The abort is the deliberate mid-drag test (a second helper process moved the cursor; the drag aborted `the cursor left the planned point` with the button released). `audit.log` lists every kill (identity-checked, one handle; all in our own trees; `own-window close` needed none).

**Premise table**

| Premise | Method | Observed | Verdict | Consequence for legs 2-3 |
|---|---|---|---|---|
| 1: colours on the UI thread, caption's empty middle within +-3, both themes; splash border in `before_show` sampled on its edge | Spike `spike_dwm.py`: `DwmSetWindowAttribute` 35/36/20 through `window.native.Invoke`; `pixel` at the caption middle (frame left + 493, top + 15), then the splash edges | All HRESULTs 0. Caption sample EXACTLY the target in both: light (240,240,245) and dark (30,30,40), delta 0. The splash border (34, applied in `before_show`, which pywebview runs synchronously on the UI thread) is a 1px (255,0,128) line on all four edges of the frameless splash, interior untouched | Confirmed | Apply from the UI thread through `Invoke` (or directly inside `before_show`); `before_show` is the place for the splash border and the first tint |
| 2: minimise glyph contrast, four cases | Same spike, OS theme Light; `pixel --size 15` at frame right - 115, caption centre (confirmed on a strip capture); extreme pixel vs caption sample | Dark caption: lightest pixel (255,255,255), contrast **16.52** with attribute 20 on AND off. Light caption: darkest (0,0,0), contrast **18.49** with attribute 20 off AND on | Confirmed, better than needed: DWM chooses the glyph colour itself from the caption colour; attribute 20 does not change it here | No legibility fix needed for the min/max/close glyphs on this host; attribute 20 is optional (set it from the resolved theme anyway for other hosts) |
| 3: apply to first new-caption frame | Spike apply at T during a 20ms `--series` over the caption; both sides on `perf_counter` | Apply call 0.38ms; the first frame sampling the new caption was **8.0ms** after the apply call began (the frames before it, -12ms and earlier, the old caption); no redraw call was needed | Confirmed | No `SWP_FRAMECHANGED`/`RedrawWindow` after an apply; the caption repaints within one frame |
| 4: `hidden=True`, tint, `show()` | Spike hidden mode (tint in `before_show`), a 16-20ms series over a caption `--rect` started before `show()`, three runs | 135 `no-window` frames before `show()`, then 5, 55 and 61 visible frames (first at 20.6, 16.2 and 9.3ms after the `show()` call, which itself took 10-15ms): **no default-caption frame in 121 visible frames** (all (20,40,160) within 0). In front 300ms after `show()` in all runs. `events.shown` fired ONCE, at creation: pywebview shows the form at opacity 0 and hides it again, so it does NOT mean the user-visible show | Confirmed | Tint before show is flash-free; use the app's own `loaded`/`show()` for "visible", never `events.shown`, when `hidden=True` |
| 7: custom text colour, active vs inactive | Spike: text colour 240,240,240 on a dark caption; `pixel --size 31` over the title text; own A clicked in front for the inactive state | Lightest pixel (240,240,240) in BOTH states; patch means 51.28/51.34/60.13 (active) vs 51.31/51.37/60.16 (inactive); caption unchanged | Information: a custom text colour is not greyed when inactive here | DD5's activation tracking is still the committed design; this host would not show the difference |
| 9: real Ctrl+K into the from-source copy | `front`, then `click` at a CDP-derived body point (client origin 888,427 + (700,500)), `keys ^k`, CDP read, `keys {ESC}`, CDP read | `[data-testid="jump-to"]` open with focus in `jump-to-input` after Ctrl+K; gone after Esc, focus back on `MAIN`; cursor restored to its `before` | Confirmed | Spec step 8's Ctrl+K and Esc can run through `keys` after `front` and a body click |
| 11: what `CopyFromScreen` needs | Own B (the orange window) over the test copy; `capture`/`pixel` with and without `--allow-own-cover`; `--print-window` vs a normal capture of the tinted caption | Normal capture and pixel: refused `covered_by_own` (the passing outcome). `--allow-own-cover`: the covered point samples (240,184,112) = own B's colour, where the test copy there is white, so a naive capture would have mis-attributed it. `PrintWindow` with `PW_RENDERFULLCONTENT` renders the DWM-tinted caption pixel-for-pixel like the screen capture ((30,30,40) at the caption middle in both; the print image is the 1000x700 outer rect, the screen one the 986x693 frame bounds) | Confirmed | A capture needs the window unoccluded; `PrintWindow` is a sound fallback for steps 1 and 7 when something covers it |
| 13: foreground technique | See the trial matrix | Candidate 1 decided (5/5 from both starts) | **Decided: `own`** | `front` and `focus-restore` use it |

**Premise 13 trial matrix** (candidates in order, stopping at the first decided):

| Candidate | Start: own B in front | Start: own A in front | Result |
|---|---|---|---|
| 1. `SetForegroundWindow` from own window A's process, after a gated click on A | 5/5 (the technique's own first step is the click on A) | 5/5 | **decided** |
| 2. `SwitchToThisWindow` | not run (stop at the first decided) | not run | n/a |
| 3. topmost then not topmost | not run | not run | n/a |
| 4. minimise then restore | not run | not run | n/a |

Real-foreground trials for the decided candidate: **2 of 2** (operator's Windows Terminal in front, `front` brought the test copy forward; each followed by `focus-restore`, which restored it for trial 1, while trial 2 was left in front and restored by the final `focus-restore`). The informational `AllowSetForegroundWindow` spike was not run: the own window's allowlist (and the unchanged product code) rule it out as a production technique, and candidate 1 decided. **Launch-time visibility:** a plain `launch` opened in front in 4 of 4 trials (operator's foreground twice, own A, own B in front), so `launch --via-own` was not added. `front` also brings a MINIMISED window forward (`SW_RESTORE` first, then the technique): verified. "Foreground is nothing" was not reached.

**Deviations from the leg and why.**
- **Containment area widened to every visible window of the gate tree** (the main window first, then the splash or a dialog), not only the main window: premise 1's splash-edge sample needs it, and those windows are the test copy's own pixels. Also added: a target layered below full alpha (the hidden-creation flash) is refused as `translucent-target`, because it shows what is behind it.
- **`click` runs with no live tree** (only an own window can then pass the gate): needed to put own B in front before a launch-time trial.
- **A defect found and fixed in my own recovery rule.** `_recover` released the held button of a gesture that was still running in ANOTHER helper process (seen in the mid-drag abort test: a `recover` row with `button:0x1`). A `begin` row now records the helper's identity and recovery only runs when that process is gone; a unit test covers the row shape.
- Extra commands beyond the leg's table (`front-trial` for premise 13, `foreground`, `screen`, `hands-off`, `input-log`, `own-window show --no-overlap`, `own-window do --technique`), all read-only or inside the same gates.
- Premise 13 candidates 2-4 and the informational `AllowSetForegroundWindow` spike were not run, per the "stop at the first decided" rule.
- The own window's `WM_LBUTTONDOWN` calls `SetForegroundWindow` on itself (a click on a `WS_EX_NOACTIVATE` window does not activate it by itself; the call from the process that just received the click did: 27 of 27 clicks on the two own windows left the clicked window in front, and all 19 allowlisted commands ran).
- Not exercised on the host: the "operator moved the cursor, leave it alone" branch of the cursor restore and the operator-interference abort (unit-tested; the abort path itself was exercised with a second helper process moving the cursor), and `release-all` against a really stuck key (it found nothing held on every call).

### Leg 2: tinted-title-bar

Built `the_one/interfaces/desktop/chrome.py` (palette, `colorref`, `windows_build`, `attribute_plan`, `apply_title_bar`, `os_theme`, `load_theme`/`save_theme`, the lock-guarded state, UI-thread applies through `BeginInvoke` with a 2s bounded wait, activation tracking, `deregister`, `apply_splash_border`, `native_show`, `snapshot`), `shell.set_window_theme`, the first-paint order in `DesktopSession.run`/`_boot` (hidden main window with `background_color`, `register` before `show()`, the `_main_shown` splash gate, guarded `show()` with the Windows-only native fallback, the themed splash and its `before_show` border), `POST`/`GET /api/window/chrome`, and `theme.js` `notifyShell`. Docs: `the_one/agents.md` "Window chrome (M25 F5)" plus the corrected 5.4 footgun note (DD13), and a `CLAUDE.md` paragraph.

**Tests.** `tests/test_window_chrome.py` (47: palette pin for both themes, colorref, attribute plans, persistence incl. atomic write, state, activation, lock-free invoke, racing requests, the `BeginInvoke` path, pending, deregister), `tests/test_api_window_chrome.py` (12), 16 new shell tests in `tests/test_desktop_shell.py`, `tests/browser/test_flow_settings_window_chrome_signal.py` (5, `settings` lane), an autouse `chrome.reset()` fixture in `tests/conftest.py`. One existing test updated in place: `tests/test_desktop_tray.py::test_show_callback_calls_window_show_not_restore` now resets the mock after `_boot` (`_boot` itself calls `show()` once now). Results: `make test-unit` 5397 passed, 10 skipped (11m52s); static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`) 258 passed; new browser file 5 passed; `settings` lane 183 passed (5m58s), `shared` lane 465 passed (12m00s), both with `THE_ONE_TEST_NETNS=1`; `ruff check` and `ruff format --check` clean.

**Windows session** (run id `l2-s1`, bracketed by `snapshot --out`/`--compare` (clean, installed app still pid 208344) and `focus-save`/`focus-restore`; OS app theme Light; trees `l2a`-`l2d`, ports 8490/9390, data dirs `data-l2-1`..`-3`):

| Check | Sampled values |
|---|---|
| 1. First launch (fresh `data-l2-3`, `capture --series` 200 frames at 40ms over rect 1200,600,100,100, started when the tree record appeared) | no-window frames until 2.84s, then the splash mean (255,255,255) = `#ffffff` for 11 frames, then the main window (251.8,251.8,251.8) with NO frame between showing neither window (the one `no-window` frame, i=72, precedes the splash). Caption at (1380,411): (250,250,250) = `#fafafa`. `GET`: `last_applied.theme` `light`, HRESULTs `{dark_mode:0, border:0, caption:0, text:0}`, `pending` false, `build` 26100. `window-chrome.json` = `{"theme": "light"}` |
| 2. Dark through CDP (Settings > Appearance > Dark) | caption (23,24,28) = `#17181c` 0.70s after the click (click to `pixel` return); `GET` `last_applied.theme` `dark`, `pending` false; file `dark` |
| 3. Inactive/active (own window A, `front`, gated click on A) | dark: inactive title text lightest (133,135,143) = `#85878f`; after `front`, active lightest (237,237,240) = `#ededf0`. Light changed while A was in front (inactive): darkest (110,110,119) = `#6e6e77`, `last_applied.active` false |
| 4. Auto (`Emulation.setEmulatedMedia`, one held CDP session) | emulated dark: `data-theme` dark, caption (23,24,28); emulated light: caption (250,250,250); emulation cleared |
| 5. Relaunch with `dark` persisted (x clicked at 1650,411: window hidden to the tray, server alive, `window-state.json` saved; `stop`; relaunch, series started on the tree record) | first visible frame (16,17,20) = `#101114`; no light or white frame in 117 visible frames (one 40ms frame (18,18,18) at 3.49s, dark); no `no-window` frame after the first visible one; caption (23,24,28); `GET` `launch_theme` `dark`, `last_applied.theme` `dark`, `active` true |
| 6. Browser gate (WSL Playwright, handoff minted over HTTP) | tab went `light` > `dark` > `light` > `dark`: zero requests to `/api/window/chrome`; desktop caption stayed (250,250,250); file unchanged |

`last_applied.active` read false whenever the test window was not in front (the launch never takes the foreground), so the activation tracking ran for real on every check, not only in check 3.

**Focus.** `focus-save` saved the operator's foreground (`msrdc.exe` RAIL_WINDOW pid 17840); `focus-restore` reported `gone` at the end (that window no longer existed; the foreground was another process), so nothing was force-changed. The input log (cumulative, all runs): sent 46 (own 18, tree 21, operator 3, none 4), aborted 1, refused 21. Nothing of ours remains: `tree` empty, no listener on 8490-8491/9390-9391, no `pythonw`, own window closed; the Linux side started no process beyond the test runs.

**Deviations from the leg.** (1) The launch `capture --series` could not start before `launch` returns (the helper refuses an unrecorded tree and the tree record is written seconds after `launch` starts): the series was started by polling for the record file `R\pids\<tree>.json` while `launch` ran in the background, which still caught the splash's first frame. (2) The splash's visible life was short (11 frames, 0.44s) because the server was already up when it appeared. (3) `tinted` is true only when every attribute's HRESULT is 0 and the apply recorded no error. (4) `snapshot()` also reports `enabled`, `registered`, `launch_theme`, `persisted`, `active`, `build` and `supported`. (5) The page's retry: the leg's "after 2s or on the next `apply()`" can be satisfied by either; in the browser test the next `apply()` at boot fires it, and the 2s timer then finds the retry budget spent. No other difference from the leg.


### Leg 3: window-size-and-doctor

Added to `window_state.py`: `DEFAULT_SIZE` 1440x900, `MIN_SIZE` 640x360, `SCREEN_MARGIN` 64 and the pure `work_area` / `first_launch_size` / `apply_floor`. `shell.py` now always passes `min_size`, passes `width`/`height` only (no `x`/`y`) on a first launch, and runs `apply_floor` before `clamp_to_bounds` on a restore; `webview.screens` is resolved by one helper, `_resolve_screens`, for both paths. Leg 2's `background_color`, `hidden=True` and the `_main_shown` gate are untouched. `diagnostics.py` gained `_probe_window_chrome` (a tenth gate, appended last; `ProbeResult` detail is ASCII), and both CI needle lists (`ci/tasks/windows-installer-build.yml`, `.github/workflows/windows-installer.yml`) gained `window chrome: OK`; both files parse as YAML. Docs: `the_one/agents.md` (ten gates, probe contract, first-launch size block) and `CLAUDE.md`.

**Tests.** `test_run_desktop_no_state_uses_defaults` was renamed `test_run_desktop_no_state_uses_first_launch_size` and inverted; new tests cover `work_area`, `first_launch_size`, `apply_floor`, a saved 400x250 lifted to 640x360 and a saved 1294x1399 kept; `tests/test_doctor.py` has the ten-name line-up test and a `TestWindowChromeProbe` class (off Windows, build 26100, build 20348, dwmapi missing, ASCII). No other test pinned `_create_kwargs` exactly. Linux `the-one doctor`: `window chrome: OK — skipped (not Windows)`, `RESULT: PASS`.

**Windows session** (run id `l3-s1`, bracketed by `snapshot --out`/`--compare` (clean, no changes, installed app still pid 208344) and `focus-save`/`focus-restore` (saved Windows Terminal pid 18816; restore reported `already-foreground`); build 26100, 96 DPI, work area 0,0,2560,1392; trees `l3a`-`l3c`, ports 8490-8492 / CDP 9390-9392, data dirs `data-l3-1`..`-4` under the scratch root; every tree stopped, `windows` lists none afterwards):

| Check | Values |
|---|---|
| 1. From source, fresh `data-l3-1` | outer rect (560,246)-(2000,1146) = **1440x900** at (560,246), exactly the centred expectation; client 1424x861; CDP `innerWidth` **1424**, `innerHeight` 861. The drawer cannot be shown: a fresh dir has no provider or agent, so no chat opens (`#chat-drawer` exists, `hidden`, `display: none`); push mode is not observed here, only implied by 1424 >= 1280 |
| 2. Saved 400x250 (`data-l3-2`) | launch outer (960,516)-(1600,876) = **640x360**, centred. Default-mode `drag` 1592,868 -> 1292,668 (delta -300,-200; the helper refuses a start outside the visible frame bounds) left the rect at 640x360, but the helper cannot start inside the invisible 7px sizing border, so it is not proven that the drag engaged a sizing handle; `Browser.setWindowBounds` over CDP is unsupported ("Browser window not found"). The floor at launch is proven; the live drag floor is unproven |
| 3. Saved 1294x1399 at (1273,0) (`data-l3-3`) | outer (1266,0)-(2560,1399) = **1294x1399**, frame bounds x=1273 (the saved x), y=0: restored at that size and position, not shrunk or centred (the 7px invisible bottom border puts the outer height 7 past the 1392 work area, the same shape the operator's saved geometry has); the file is unchanged after `stop` |
| 4. Frozen | `freeze` built both exes (78s); `doctor --frozen` exit 0, `RESULT: PASS`, ten gates; `window chrome: OK - caption colours supported (build 26100, probe 0x80070006)`; the five needles `usearch`, `fts5`, `embedding model`, `file watcher`, `window chrome` (each `: OK`) all present in the output (a `grep` rendering of CI's `foreach` list) |

**Deviations from the leg and why.** (1) The live drag-to-floor in check 2 is inconclusive for the reason in the table; the unit and launch values cover `apply_floor` and `min_size`. (2) No drawer push-mode observation (no agent in a fresh data dir; creating one needs a provider, outside the leg's scope).

### Leg 4: specs-and-close

Added `resize --width W --height H` and `capture --splash` to `scripts/windows_test_copy.py` (7 new pure tests, 155 in all), rewrote the crew spec `windows-window-chrome` (now `active`) against the real helper, revised the operator spec `windows-native-frame-splash` for Flight 6's SC9 walk, updated `mission.md`, swept the docs, took the preview captures and ran the gates. No product code changed.

**`resize`.** `SetWindowPos` on the gate tree's main window with `SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE` (the missing `SWP_NOZORDER` constant added), behind the same gate, hands-off and identity checks as `show-window`; the pure `validate_resize` refuses non-integers and anything outside 100..10000 (exit 2); the result reports the requested size, the resulting outer rect and size. **`capture --splash`** (not in the leg, a deviation): the dry run showed that a plain `--series` only ever sees the window titled exactly "GleepGlorp AI", so leg 2's "splash mean (255,255,255)" frames were the MAIN window's white page area before the app painted, never the splash. `--window --splash --series` follows the splash window (title with an em dash, `SPLASH_WINDOW_TITLE`); it is series-only.

**The two specs, step by step.**

`windows-window-chrome` (Status `active`, `Revised` line added; Preconditions point to `the_one/agents.md` "Windows test copy" for the safety rules and add CDP, colour-sampling and lazy-storage notes; the structure is unchanged):
1. Launch: snapshot, `focus-save`, own window A, `launch` in the background, series started when `R\pids\main.json` exists; a splash series and a caption-strip series; expects light splash frames, the strip `#fafafa` from its first main-window frame, 1440x900 centred, `innerWidth` of 1280 or more (1424), no drawer clause.
2. Read-back: judged on `last_applied` and `pending: false` (HRESULTs 0), never on `requested` alone.
3. Ctrl K: `front`, a CDP-derived body `click` (client origin plus 700,500), `keys ^k`, read, `keys {ESC}`, read.
4. Dark: samples of caption, title text, caption-button glyph and the left border pixel (38,39,44), GET and file.
5. Inactive: own window A clicked in front (`click` on its centre), `foreground` check, then Light and Dark while inactive, then `front`.
6. Auto: one held CDP session, `Emulation.setEmulatedMedia`.
7. Persistence: click Dark, poll the leveldb log mtime (replaces the 10-second sleep), then the caption x `click`, `stop`, relaunch with the splash and caption series.
8. Floor: write the 400x250 state, relaunch, `resize` 400x250 (stays 640x360) and 1000x700, and a refused `resize --width 50`.
9. Caption `click --double`, maximize check, `click --double` again, the minimize button `click`, `show-window --restore`, `drag --caption` and a Ctrl K check.
10. x to the tray (alive, `/api/live` 200). 11. `stop`, `focus-restore`, `own-window close`, snapshot compare.

`windows-native-frame-splash`: Preconditions retargeted at the operator's own installed build on 8484 and its own data dir (driven by the operator at Flight 6; the old "dedicated test host" wording and the "Known gap" note are gone); step 9 rewritten (a plain browser with no handoff is refused and shows no window controls); steps 11-19 added for SC9 (title bar both themes, follows Settings, real OS flip in Auto, inactive dimmer, snap layouts, upgrade keeps the size, fresh profile 1440x900 centred, Ctrl K, splash matches the theme with no gap); the DD4 first-launch note; Variants for scaling above 100% and several monitors (`CenterScreen`); a second `Revised` line.

**CI needle `foreach`, verbatim** (the loop copied unchanged from `ci/tasks/windows-installer-build.yml`, run in PowerShell on Windows against the frozen `the-one.exe doctor`'s output captured the same way as CI does, `$doctorLines | Out-String`, with `THE_ONE_DATA_DIR` pointed at a scratch dir):
`foreach ($needle in @("usearch: OK", "fts5: OK", "embedding model: OK", "file watcher: OK", "window chrome: OK")) { if (-not $doctorText.Contains($needle)) { throw "frozen doctor output missing '$needle'" } }`
Result: no throw; the doctor exited 0 with `RESULT: PASS`, ten gates, and `window chrome: OK - caption colours supported (build 26100, probe 0x80070006)`.

**Dry run of the crew spec on the frozen copy** (every step ran; sessions below; values observed):

| Step | Observed | Changed in the spec? |
|---|---|---|
| 1 | Splash frames light (first frame the 1px border, mean 228,228,231; then 255); caption strip `#fafafa` (250,250,250) from the first main-window frame; outer rect (560,246)-(2000,1146) = 1440x900 centred; `innerWidth` 1424 x `innerHeight` 861; `data-theme` light | The splash needs `--splash` (new); the caption strip replaces a page-area rect |
| 2 | `pending` false, `last_applied.theme` light, all four HRESULTs 0, `error` null, `window-chrome.json` `{"theme": "light"}`, `launch_theme` light | `supported` is a top-level field, not in `last_applied` |
| 3 | After `^k`: `jump-to` open, active `jump-to-input`; after `{ESC}`: closed, active `MAIN` (frozen build) | Dropped the "no find bar" capture clause (not run) |
| 4 | Caption (23,24,28); title lightest (237,237,240); glyph lightest (255,255,255); border pixel (38,39,44); GET dark, HRESULTs 0, file dark | none |
| 5 | Inactive dark: caption (23,24,28), title lightest (133,135,143), `active` false; inactive light: caption (250,250,250), darkest (110,110,119); inactive dark again (133,135,143); after `front`: (237,237,240), `active` true | none |
| 6 | Light (250), Auto/OS light (250), emulated dark (23,24,28) and `data-theme` dark, emulated light (250), cleared light, Dark (23,24,28) | "within 1 second" replaced by "by the sample taken one second later" (each helper sample takes about a second) |
| 7 | **Failed twice as first written**, then passed with the poll below. Persistence: a burst of theme flips (Light, Auto, Dark) deferred WebView2's `localStorage` write by more than 20 s, the `stop` kill dropped it, the relaunch read no preference, so the dark launch frames were followed by a white frame and a light page (the app then posted light and rewrote `window-chrome.json`). A single Dark click flushed the leveldb log in 5 s. Final: x hid the window, `/api/live` 200, `window-state.json` `{"width": 1440, "height": 900, "x": 560, "y": 246}`; relaunch: first splash frame (16,17,20), first caption-strip frame (23,24,28), no light frame; `data-theme` and `theme-preference` dark | The 10-second sleep became a poll of the leveldb log mtime (INCONCLUSIVE, not FAIL, if it never moves); the burst-deferral note added to Preconditions. This is a Chromium storage-flush effect of killing the process (a graceful Quit flushes), not a product defect |
| 8 | 400x250 state: launch outer (100,100)-(740,460) = 640x360; `resize` 400x250 stays 640x360; `resize` 1000x700 gives 1000x700 and `innerWidth` 984 x 661; `resize --width 50` refused, exit 2 | The live drag is replaced by `resize` (as planned) |
| 9 | `resize` 1200x800 (frame 107,100-1293,893); caption `click --double`: maximized frame (0,0)-(2560,1392), caption (23,24,28); second double-click restores (100,100,1300,900); minimize button `click`: outer at -32000; `show-window --restore`: same frame, caption (23,24,28); `drag --caption` +200,+100: outer (300,200)-(1500,1000); Ctrl K opened and Esc closed Jump to | "Drag the window back to 1200x800" became `resize`; the caption sample after maximize is at the top of the work area |
| 10 | x at frame right minus 30: main window not visible, tree alive, `/api/live` 200 | none |
| 11 | `stop` complete, tree empty, ports free, `focus-restore` `already-foreground`, snapshot compare `ok` | none |

**Windows sessions** (every one bracketed by `snapshot --out`/`--compare` and `focus-save`/`focus-restore`; the installed app stayed pid 208344 on 8484 throughout; scratch data dirs `data-l4-1` to `-3`, `data-l4-doc`; ports 8490 and 9390 only):

| Session (run id) | Contents | Snapshot compare | Focus |
|---|---|---|---|
| `l4-s1` | `doctor-host`, `setup` (5 files, 8.4s), `freeze` (73.8s), the CI `foreach` (outside the bracketed trees), the full dry run, the preview captures, the persistence repro | clean (`ok`, no allowed changes) | saved Windows Terminal (pid 18816); `already-foreground` |
| `l4-s2` | steps 1 and 7 run again exactly as the spec words them (caption strip `1270,256,20,10`, both series), to prove the final wording | clean | `already-foreground` |

`input.log` for `l4-s1`: 30 sent, 2 refused (my own `px.sh` pointing at a stale tree id: nothing sent), no abort. Nothing of ours remains: `tree` empty, own windows closed, nothing listening on 8490 or 9390, no process with the scratch root in its command line.

**Preview files** (scratchpad `f5preview/`, copies under `R\evidence\preview\`): `light-active.png`, `light-inactive.png`, `dark-active.png`, `dark-inactive.png`, `first-launch.png`, `splash-light.png`, `splash-dark.png`, `README.txt` with the sampled values. **Finding for the preview:** the splash captures are the themed background only (no logo): its own WebView2 had not painted in the 0.25 to 0.9 s the splash was visible, because the main window now shows as soon as it has loaded and covers the splash. Colours and the no-gap property are proven; the logo is not visible on a fast boot (recorded in the crew spec's Out of Scope and the operator spec's step 19).

**Docs and drift fixed.** `mission.md`: "Window chrome mechanism" checked off with the DD1 answer; "Ctrl K in WebView2" given the crew evidence (leg 1b premise 9, repeated on the frozen build), left open for the close gate and Flight 6; SC9 left unchecked with a "Flight 5's part" note. `CLAUDE.md`: the M15 F7 paragraph said the splash is dismissed on the main window's `loaded` event (now: once the main window is shown and has loaded); the apparatus sentence gained `resize` and `capture --splash --series`. `the_one/agents.md`: the "Launch splash" bullet (same fix, plus the blank-splash note), the "Native OS frame" bullet (it still quoted the two-key `_create_kwargs`), the L1b command list (`resize`), and a new "`resize` and `capture --splash`" bullet with the two dry-run findings. Checked and correct: the ten gates and the probe table, the first-launch size block, the Window chrome block, the footgun note. `SECURITY-MODEL.md` enumerates no window routes (every route sits behind the gate by its general rule), so nothing was added.

**Gates.** `ruff check the_one tests scripts` and `ruff format --check` clean. Helper tests 155 passed. `TEST_TIMEOUT=3000 make test-unit`: 5423 passed, 10 skipped, 1820 deselected (11m27s). Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`) with the helper tests: 413 passed. Browser lanes, each under `THE_ONE_TEST_NETNS=1`, run sequentially in the background: `chats` 163 passed (4m21s); `agents` 134 passed, 2 skipped (5m29s); `library` 145 passed, 1 skipped (8m00s); `settings` 183 passed (5m50s); `contracts` (with `THE_ONE_REQUIRE_WEBKIT=1`) 646 passed, 3 skipped (2m48s); `shared` (`TEST_TIMEOUT=3600`) 465 passed (11m50s). The lanes ran against the tree as of the `resize` and `--splash` edit, before the doc, spec and extra helper-test edits; those touch no code the lanes exercise (the 3 later helper tests passed on their own, and the helper-test file ran again afterwards).

**Deviations.** (1) `capture --splash` added (see above). (2) The preview splash frames show no logo (see above). (3) The unit-suite run began before the last three helper tests and the doc edits (those were run separately). (4) The leg's "saved 400x250 launches at 640x360" check ran on the frozen build rather than from source.

---

## Flight Director Notes

### Planning (2026-10-06)

- **The operator's answers.** "Tinted Windows bar (Recommended)" and "Test copy on my
  desktop (Recommended)".
- **Planning probes,** all read-only on the Windows side:
  - `powershell.exe` from WSL runs in session 1;
  - `C:\Python311` (3.11.9, pip, uv) and Git for Windows are present;
  - the installed `the-one-app.exe` is PID 208344 in session 1;
  - DPI is 96;
  - WSL networking is mirrored;
  - `%LOCALAPPDATA%\the-one` holds no `.env`, and its `window-state.json` is a right-half
    snap at 1294×1399.
- **Concourse** at `localhost:8080` timed out from `fly`, so the local freeze replaces
  `fly execute` (DD10).
- **Design review, cycle 1** (Architect, Opus): **approve with changes**. One high, nine
  medium and six low issues. All were incorporated:
  - **High: input safety on a live desktop** (DD10).
    - Windows are found by PID tree only.
    - A foreground check and a `WindowFromPoint` check run before every injection.
    - An occlusion check runs before sampling.
    - Bringing the window to the front is premise 13.
    - Injection is held off while the operator is typing (`GetLastInputInfo`).
    - The inactive state uses a window the helper owns.
  - **Medium:**
    - The first-post race (DD3): register before show, record a requested theme, mark a
      theme sent only on a 2xx, and serialise posts.
    - The DD3/DD7 contradiction: persistence is cross-platform, and only the tint is
      Windows-gated.
    - DPI units (DD6): no `x`/`y` on first launch, so pywebview uses `CenterScreen`; the
      work area is `screens[0].frame`.
    - The floor against snapping (DD6): a 640×360 floor instead of an enforced 1024, made
      a preview question.
    - Spec step 7's false failures: wait, then × to the tray, then kill.
    - The stale safety check: a snapshot of the operator's data dir replaces "file
      absent".
    - Per-session re-checks: the operator's `.env` and the host record.
    - The user-agent fallback replaced by `window.chrome.webview`.
    - The closure copied verbatim from CI.
  - **Low:**
    - The build from `platform_version`.
    - The doctor gate gets a concrete HRESULT and a CI needle.
    - The tests that will break are named.
    - "Outer" is stated.
    - Plain `def` routes.
    - The browser-test stub order.
  - **Suggestions taken:** the doctor gate moves to leg 3; the token pin covers `--bg`; the
    splash is themed in full; the HWND is checked with `IsWindow`; the `events.shown`
    premise; launch hygiene; the watchdog; `/api/info` in step 1; minimize in step 9.
  - **Structural changes,** so a second cycle follows: a new premise 13, a reshaped DD3
    and DD6, and a new leg 3 scope.
- **Design review, cycle 2** (Architect, Opus, the last allowed): **approve with
  changes**, nothing blocking. It confirmed every cycle-1 fix landed, and raised six
  mediums and fourteen lows on the revisions. All were applied:
  - **M1, a lock deadlock.** Every DWM apply now runs on the UI thread through `Invoke`.
    The lock guards state only and is never held across `show()` or `Invoke`.
  - **M2, inactive text.** Applies use the tracked activation state, with a unit test and
    a step-5 sub-step.
  - **M3, launch visibility.** Premise 13 now covers it, and steps 1 and 7 fall back to
    `PrintWindow`, else INCONCLUSIVE.
  - **M4, input rules.**
    - Pointer input is gated on `WindowFromPoint` only.
    - The hands-off check ignores the helper's own input and runs once per gesture.
    - No Alt-key trick.
    - Step 9 restores with `ShowWindow`.
  - **M5, stop.** `stop` waits for the whole tree and both ports. The process tree
    includes the venv launcher's child.
  - **M6, environment.** The session record gains the system theme, title-bar accent,
    transparency and any existing `WEBVIEW2_*` variables. **DD5 is committed to activation
    tracking**, the designer's answer to the review's question 2.
  - **Lows:**
    - the dedup rule;
    - `IsHandleCreated`;
    - the splash border in `before_show`;
    - the palette pin covers every hex;
    - the kernel32 build note;
    - Win32-gated work area;
    - `CenterScreen` with several monitors;
    - GTK's hidden no-op;
    - premise 10 answered from source;
    - the GitHub needle and the gate's position and line format;
    - two citation drifts;
    - the spec wording;
    - reset, the atomic write and handler exceptions;
    - the sibling-prefix test;
    - re-runnable `setup`.
  - **Answers to the review's questions:**
    1. The apply runs on the UI thread.
    2. DD5 is committed.
    3. Unoccluded launches that prove impossible make steps 1 and 7 INCONCLUSIVE and
       move them to Flight 6.
  - **Suggestion taken:** leg 1 lands its non-injecting parts first.
- **Status: ready.** The flight is planned after two review cycles.

### Execution (2026-10-06)

- **Setup.** The agentic workflow started. The phase file `leg-execution.md` loaded and
  validated. The flight moved to `in-flight`.
- **Leg 1 `windows-apparatus`: designed, risk tier HIGH.**
  - Why: it builds a new apparatus that injects real OS input on the operator's live
    desktop, beside their installed app.
  - It runs a design review (a Developer, Sonnet) before implementation.
  - It changes no product code (only `agents.md` and `CLAUDE.md` docs).
  - Spike prototypes stay in the Flight Director's scratchpad.
- **Leg 1 design review, cycle 1** (a Developer, Sonnet): **approve with changes**. Four
  highs, ten mediums and four lows. **The leg is split** at the boundary the flight
  already chose ("land the non-injecting parts first"):
  - **1a `windows-apparatus-core`:**
    - record, snapshot, set up, freeze, run `doctor`, launch, observe and stop;
    - no input;
    - premises 5, 6, 8, 10 and 12.
  - **1b `windows-apparatus-input`:** input, captures, `own-window` and `front`; premises
    1–4, 7, 9, 11 and 13. It is designed after 1a lands, on 1a's actual helper and
    findings.

  The fixes, folded into 1a (and carried into 1b's design):
  - **Process identity.** Records hold pid, creation time and path. Kills are checked
    against the record and logged to `audit.log`. Orphaned WebView2 processes are found
    by their recorded identity or their user data folder, never by name.
  - **Hands-off.** It applies to every command that can take the foreground. The
    persisted `last-injection` tick handles wraparound.
  - **The installed app** is identified as the owner of the 8484 listener whose path is
    outside the root.
  - **Root validation** with a sentinel.
  - **Path normalisation:** 8.3 names, junctions, `\\?\`, UNC, `..`, relative paths.
  - **The operator's data dir** is resolved before the venv exists (a pending
    cross-check).
  - **A `doctor` subcommand** under the refusals. No raw Windows calls outside the
    helper.
  - **The child environment** is scrubbed of inherited `THE_ONE_*` and `WEBVIEW2_*`.
  - **The snapshot** adds top-level entry names and the environment, plus a source grep
    for `setx` and the like.
  - **Copy quirks** (`--deduplicate`, an existence filter), `-EncodedCommand`, the
    launch log, the watchdog, and Windows-authoritative port checks with excluded
    ranges.
- **Answers to the leg review's questions:**
  1. The Flight Director posts the operator notices before and after each
     Windows-running spawn.
  2. Hands-off covers all focus-taking commands.
  3. The split is accepted.
  4. The snapshot compares top-level entry names.
  5. If premise 13 finds nothing, `launch` still runs (it injects nothing), but input
     waits for the operator.
- **A second design review follows,** for 1a only, because the changes are substantive.
- **Leg 1a design review, cycle 2** (a Developer, Sonnet; the last allowed): **approve
  with changes**. It confirmed every cycle-1 fix, and found nothing that touches the
  installed app (single-instance behaviour is port-based only). Two highs, eight
  mediums and six lows were applied:
  - **The highs:**
    - one-handle kills (check and terminate on the same `OpenProcess` handle; never
      `taskkill /T` or a name);
    - the child-creation-time rule against reused parent PIDs;
    - a manifest-based sync that spares `dist\`, `build\`, `*.egg-info` and
      `__pycache__`, with writes checked on the resolved target.
  - **The mediums:**
    - the Windows half runs as this file's source piped to `C:\Python311\python.exe -`,
      with JSON in and out;
    - one source for process data;
    - `launch --script` for spikes (with `storage_path` under the scratch data dir);
    - the widened environment grep, with its patterns in the test only;
    - a missing `last-injection` means no injection;
    - the watchdog mechanism, and `--tree-id`;
    - long steps run in the background, with caches under `R`;
    - `pyinstaller` installed and `uv` in the venv;
    - the precise `doctor` criterion.
  - **The lows:** the root refusal through `setup --root`; no CDP variable without
    `--cdp-port`; the main-window definition; the `doctor-host` mechanisms and
    `LongPathsEnabled`; snapshot-first ordering; CDP reads through the repo's
    Playwright.
  - **Answers to its questions:** `launch` refuses while a live recorded tree exists (run
    `stop` first); the CI-sized download is acceptable.
  - **Leg 1a: ready.**
- **Leg 1a landed** (a Developer, Sonnet, about 40 minutes).
  - **What it built:** 69 pure tests; `make test-unit` 5247 passed and 10 skipped (about
    12 minutes, run with `TEST_TIMEOUT=3000`); ruff clean.
  - **Three Windows sessions,** each snapshot comparison clean. The installed app stayed
    PID 208344, and the Flight Director re-checked its start time afterwards (2026-09-30
    17:44:53, unchanged). No test-copy process remained.
  - **Premises 5, 6, 8, 10 and 12** were all confirmed as planned. The freeze takes
    113.7s, so the "No local freeze" variation does not apply.
  - **The Flight Director's operator notices** went out at the start and end, in chat.
- **Leg 1b `windows-apparatus-input`: designed, risk tier HIGH.** It injects real input
  on the operator's desktop. It goes to a design review (a Developer, Sonnet).
- **Leg 1b design review, cycle 1:** **approve with changes**. Five highs, seven
  mediums and two lows. All were applied:
  - the own window as a separate record outside the tree gates, through a pure
    `select_gate_pids`;
  - capture containment on DWM frame bounds, with an exact Z-order occlusion test per
    frame and `covered_by_own`;
  - pre-show frames that record only `no-window`;
  - a key-grammar denylist (no Win key, Alt+Tab, Alt+F4, Ctrl+Alt and similar), plus
    `release-all`;
  - a sound `focus-save` / `focus-restore` (identity-checked, first save wins, never
    taking the foreground from a window the operator moved to);
  - `front` run by the own window's process through a command file;
  - premise-13 candidates limited to the helper's and test copy's own windows, with no
    system-state changes, and "decided" defined as five out of five from two starts;
  - hands-off on every focus change;
  - pointer re-checks after `SetCursorPos`, with no cursor restore if the operator moved
    it;
  - drag modes (caption, and content or resize) that never end over an operator window;
  - `record_injection` per batch, with interference detection;
  - stdlib GDI captures with QPC timing;
  - the own window at bottom-left and not topmost by default;
  - measurable premise wording.

  **Answers to its questions:**
  - the own window is not a tree;
  - no focus change without hands-off;
  - no drag over operator windows (snap checks stay with the operator at Flight 6);
  - `launch --via-own` as an opt-in only.

  Candidates are tried in order, stopping at the first decided one, which keeps focus
  changes on the operator's desktop few. A second cycle follows.
- **Leg 1b design review, cycle 2** (the last allowed): **approve with changes**. Two
  highs, ten mediums and three lows. All were applied:
  - **The highs:**
    - candidates `AttachThreadInput` and `ASFW_ANY` are removed (they touch foreign
      input state or system state);
    - the trials now start from a second helper-owned window B, with exactly 2
      real-foreground trials for the decided candidate, each restored, and any failed
      restore reported.
  - **The mediums:**
    - the tree-side `AllowSetForegroundWindow` is informational only (spike);
    - the topmost toggle is undone in a `finally`;
    - `focus-restore` runs after `stop` and before `own-window close`, and gains
      `already-foreground`;
    - the `own-window do` allowlist, nonce, expiry and in-process re-checks;
    - `SW_SHOWNOACTIVATE` and `WS_EX_NOACTIVATE`;
    - `WindowFromPoint` checked before any cursor motion, and a default-mode drag end
      that must be in the tree itself;
    - the occlusion test pinned (cloaked, transparent, zero-size and layered windows
      skipped; `covered_by_tree`);
    - `--allow-own-cover` for premise 11;
    - per-frame containment, with a caption-strip `--rect` for premise 4;
    - a one-tick interference tolerance, and hands-off → gate → send ordering;
    - stale `focus.json` replacement and `--discard`.
  - **The lows:** the cursor-restore criterion and `cursor_restore_decision`; `launch
    --via-own` keeps hands-off; `own-window close` and `stop` are hands-off-checked.
  - **A deliberate refinement of DD10:** the mid-gesture interference abort is stricter
    than DD10's "never between its events", and is recorded here as intended.
  - **Answers to its questions:**
    - window B stands in for most trials, with 2 real-foreground trials;
    - the tree-side candidate is spike-only;
    - `focus-restore` runs after `stop`, and the leg records whether "foreground is
      nothing" is reachable.
  - **Leg 1b: ready.**
- **Leg 1b landed** (a Developer, Sonnet, about 35 minutes).
  - **Gates:** 143 helper tests; `make test-unit` 5320 passed and 10 skipped; ruff clean.
  - **One Windows session** (run id `l1b-s1`): the snapshot comparison was clean, and
    `focus-restore` brought back the operator's Windows Terminal 3 times out of 3.
  - **`input.log`:** 40 sent, 1 aborted (deliberate), 18 refused. Every sent gesture
    targeted the gate tree or an own window. The Flight Director re-checked the installed
    app afterwards (PID 208344, started 2026-09-30 17:44:53, unchanged) and found no
    test-copy process left on either side.
  - **What the findings mean for legs 2–3:**
    - **P1:** the DWM colours apply exactly (delta 0, HRESULT 0), including the splash
      border in `before_show`.
    - **P2:** DWM chooses the caption-button glyph colour from the caption colour itself,
      with contrast 16.5 and 18.5 whatever attribute 20 is. Attribute 20 stays in DD2
      for correctness, but nothing depends on it.
    - **P3:** the change repaints within about 8ms, so no frame redraw is needed.
    - **P4:** hidden, tint, show gave no default-caption frame in 121 visible frames.
      `events.shown` fires at the hidden-creation flash, so `show()` does not block.
    - **P7:** a custom text colour is not dimmed when the window is inactive, so DD5's
      committed activation tracking is required, not optional.
    - **P9:** a real Ctrl+K reaches the page in WebView2 and opens the palette. This is
      the Known Issue's evidence, crew-verified on the from-source copy; the close gate
      re-checks the frozen build.
    - **P11:** `PrintWindow` renders the tinted caption pixel for pixel.
    - **P13:** the decided technique is `own` (a gated click on own window A, then
      `SetForegroundWindow` from A's process). A plain `launch` opened in front 4 times
      out of 4, so `--via-own` was not added.
- **Leg 2 `tinted-title-bar`: designed, risk tier HIGH.**
  - Why: a new credential-gated route pair, a window-lifecycle change (hidden, then
    register and tint, then show), and cross-thread state with a lock contract and
    UI-thread applies.
  - It goes to a design review (a Developer, Sonnet).
  - It is designed on 1b's findings: no redraw needed; activation tracking required; the
    splash border in `before_show`; `chrome.webview` at document start.
- **Leg 2 design review, cycle 1:** **approve with changes**. Three highs, five
  mediums and six lows. The Origin and credential path was confirmed clean: the request
  is same-origin with the session cookie. Applied:
  - **The highs:**
    - the delegate is `Func[Type]`, matching leg 1b's spike and pywebview itself;
    - `BeginInvoke` with a 2s bounded wait (`tinted` may be `"pending"`), skips while
      quitting or disposed, and `deregister()` on Quit;
    - the splash's `before_show` added after `create_window`, with a handler parameter
      named `window`.
  - **The mediums:**
    - a guarded `show()` with a native fallback; the GTK claim corrected (`hidden` is
      honoured there, and `show()` waits on `shown`);
    - an autouse chrome-state reset, and `data_dir` pinned in every run test;
    - check 1 expectations taken from the observed OS theme (Light), with check 5
      covering the non-OS launch theme;
    - splash capture by a series started before `launch`;
    - check 6's handoff steps spelled out.
  - **The lows:** pythonnet `(*_)` handlers; writing the file only on change; the
    `attribute_plan` test.
  - A second cycle follows: the invoke and quit path changed.
- **Leg 2 design review, cycle 2** (the last allowed): **approve with changes**, no
  blockers. Five mediums and seven lows. Applied:
  - **The splash gap.** A `_main_shown` gate keeps the splash until the main window is
    visible. The backstop moves after `show()` on `_boot`'s thread, because waiting
    there would block `_boot` on itself; the resent report caught this.
  - **The UI-thread function's catch-all,** so no exception reaches
    `Application.ThreadException`.
  - **`chrome`'s own `closing` flag** set by an idempotent `deregister()`. It is called
    on every destroy path (`_on_quit`, `_on_closing`'s allow-destroy returns, and
    `_close_to_tray`'s no-tray fallback). `chrome` never imports `shell`.
  - **The native `show()` fallback** is Windows-only (`Show` and `Activate`, through the
    `chrome.native_show` seam); off Windows a failed show re-raises.
  - **`snapshot()` gains `pending`.** The checks read `last_applied`.
  - **The lows:**
    - `_UI_WAIT_MS` is monkeypatchable;
    - `EndInvoke` runs in a `finally`;
    - the stale isolation text is fixed (the existing `_boot` tests already pin
      `data_dir`);
    - tests that patch `win32` stub the chrome seams and `os_theme`;
    - `reset()` clears every field;
    - `theme.js` treats `tinted: "pending"` as sent.
  - **The designer's decision:** the splash dismissal follows `show()`.
  - **Leg 2: ready.**
- **Leg 2 landed** (a Developer, Sonnet, about 38 minutes).
  - **Tests:** 47 chrome, 12 route, 16 shell and 5 browser tests; `settings` lane 183
    passed; `shared` 465 passed; `make test-unit` 5397 passed and 10 skipped; static
    guards and ruff clean.
  - **All six test-copy checks matched the targets exactly:**
    - light `#fafafa` and dark `#17181c`;
    - inactive `#85878f` and `#6e6e77`;
    - Auto followed the emulated theme;
    - the dark relaunch showed no light frame in 117;
    - the plain browser tab sent zero POSTs.
  - **Safety:** the snapshot comparison was clean. `focus-restore` reported `gone`: the
    saved foreground, an `msrdc.exe` WSLg window, had closed, so nothing was forced. The
    Flight Director re-checked the installed app (PID 208344, unchanged) and found no
    test-copy process left.
  - **Deviations,** all accepted:
    - the capture series started just after `launch` began, because the helper refuses
      an unrecorded tree; it still caught the splash's first frame;
    - `tinted` is true only when every HRESULT is 0;
    - `snapshot()` carries extra fields;
    - the retry browser test counts exactly 2 POSTs.
- **Leg 3 `window-size-and-doctor`: designed, risk tier LOW.**
  - Why: additive keys in `_create_kwargs`, pure sizing functions, one more doctor
    probe, and two CI needle lines, all in established patterns, with one test renamed
    and inverted on purpose (DD6).
  - No design review. The flight-end Reviewer covers it.
- **Leg 3 landed** (a Developer, Sonnet, about 13 minutes).
  - **Tests:** 207 related tests passed; `make test-unit` 5413 passed and 10 skipped;
    ruff clean; both CI files parse.
  - **Linux `the-one doctor`:** `window chrome: OK — skipped (not Windows)`, `RESULT:
    PASS`.
  - **Test copy:**
    - first launch 1440×900 at (560, 246), exactly centred, viewport 1424 wide;
    - a saved 400×250 launches at 640×360;
    - a saved 1294×1399 at (1273, 0) is kept;
    - the frozen doctor shows ten gates, PASS, with `window chrome: OK — caption colours
      supported (build 26100, probe 0x80070006)`.
  - **Safety:** the snapshot comparison was clean, and `focus-restore` reported
    `already-foreground`. The Flight Director re-checked the installed app (PID 208344,
    unchanged).
  - **Two checks were not shown, both apparatus limits:**
    - **The live drag to the floor.** The helper refuses a drag that starts outside the
      visible frame, which is where the invisible resize border sits. The floor at launch
      and the unit tests cover it, and leg 4 adds a `resize` command (`SetWindowPos` on
      the tree's own window) so spec step 8 can test the floor at runtime.
    - **Drawer push mode.** A fresh data dir has no agent, so no chat opens. A viewport
      of 1424 (at least 1280) is the evidence, and the browser suites cover the drawer's
      push mode at 1280 and above. Spec step 1 asserts the viewport only.
  - **One gap to close:** CI's `foreach` was checked by `grep`, not run verbatim. Leg 4
    runs it verbatim.
- **Leg 4 `specs-and-close`: designed, risk tier LOW.**
  - Why: the specs and docs, a small additive helper command, the mission updates and
    the gates.
  - No design review. The flight-end Reviewer covers it.
- **Leg 4 landed** (a Developer, Sonnet, about 54 minutes).
  - **The dry run** of `windows-window-chrome`: all eleven steps passed on the frozen
    copy after one spec fix.
    - **Step 7.** WebView2 defers its `localStorage` write by more than 20s after a burst
      of theme changes, and a hard kill drops it. The step now waits for the profile's
      log to flush, and is INCONCLUSIVE if it never does.
    - This is not a product defect: a graceful Quit flushes. It is carried to the
      debrief.
  - **CI's `foreach`,** run verbatim, passed with five needles.
  - **Gates:**
    - `make test-unit`: 5423 passed;
    - the browser lanes: `chats` 163, `agents` 134 (2 skipped), `library` 145 (1
      skipped), `settings` 183, `contracts` 646 (3 skipped), `shared` 465;
    - ruff clean.
  - **Deviations,** accepted:
    - **`capture --splash`** was added. The leg 2 "splash `#ffffff`" frames were really
      the main window's page area before it painted. The splash's colour is now judged
      on the splash itself.
    - **The splash logo** is not visible on a fast boot (0.25 to 0.9s), recorded for
      Flight 6.
  - **Safety:** both sessions' snapshot comparisons were clean, with focus
    `already-foreground`. The Flight Director re-checked the installed app (PID
    208344, unchanged) and found no test-copy process left.
  - **Preview captures** are in the scratchpad's `f5preview/` folder.
  - **Review fixes** (flight-end review): the helper's `NEEDLES` gained `window chrome: OK` (pinned against the CI `foreach` list by a test), and `chrome.request()` now writes the theme file outside `_lock`, serialised by a separate `_file_lock` that re-reads the latest requested theme before writing, so the file always ends on the latest request (tests assert `_lock` is free during `save_theme` and that interleaved requests persist the latest theme).
- **Flight-end review** follows (a Reviewer, Sonnet). Sonnet, not Haiku, because the
  diff adds a credential-gated route and a helper that kills processes and injects input
  on the operator's desktop.
- **Flight-end review:** `[HANDOFF:confirmed]`, no blocking issues. 624 targeted tests
  and ruff were re-run. The kill, input and port guards were spot-checked and found
  sound. Two non-blocking items were fixed by a Developer:
  - **`NEEDLES`** now has five needles, pinned against CI's `foreach` list.
  - **The theme-file write** moved out of `_lock`, into a separate `_file_lock`.
    - The first attempt opened a race in which an older theme could win on disk.
    - The Flight Director had it closed: the latest requested theme is re-read inside
      `_file_lock`, and an interleaving test was added.

  Re-review: `[HANDOFF:confirmed]`, with no deadlock risk (the lock order is always
  `_file_lock`, then `_lock`), 260 passed and ruff clean. Every leg is now
  `completed`.
- **The DD12 operator preview** is published (non-blocking): five what-you-see
  questions with the captures, at https://claude.ai/artifact/CV8mDb9Wc49yzuciaDSFyQ.
- **The operator's instruction (2026-10-06):** "go ahead and merge the pr when its ready
  and cut a minor release".
  - The mission's branching constraint said no release until the mission completes. The
    operator's explicit instruction overrides it for this release, and the Flight
    Director noted the override to them.
  - The plan: the commit and PR; the close-gate witnessed run on the frozen test copy;
    landing; the debrief; a squash merge; then release `v0.10.0` (a version-bump PR, an
    annotated tag, the GitHub installer workflow, and release notes).
- **Commit and PR.** The flight was committed as `e91de9a` (by the Flight Director
  directly, not a commit Developer: one `git add -A` of a reviewed tree, with the
  pre-commit hook passing). It was pushed and opened as draft PR #221.
- **The close gate: `windows-window-chrome` PASSED 11 of 11** (run
  `2026-10-06-20-06-24`, live Executor and Validator, both Sonnet, on the frozen build of
  `e91de9a`).
  - **What it confirmed:**
    - the first launch is light from its first frame, at 1440×900 centred;
    - the read-back shows HRESULTs 0;
    - a real Ctrl K reaches the page in WebView2 (the Known Issue's frozen re-check);
    - in Dark, the caption, title, glyph and border are exact;
    - inactive dimming is exact in both themes;
    - Auto follows emulated media;
    - a dark relaunch shows no light frame;
    - the 640×360 floor holds through `resize`;
    - maximize, minimize and restore, caption drag and close-to-tray work.
  - **Safety:** the snapshot comparison was `ok` and focus was `already-foreground`.
  - **Two Orchestrator rulings:** step 5 "close to" is ±8 per channel; own window A was
    re-shown as setup for step 9's `front`.
  - **Evidence gaps,** non-blocking: the step-3 and step-9 screenshots were not saved,
    and the DOM reads carried both verdicts.
  - **Squawk 0123** logs the spec wording fixes from both closings, including step 7's
    flush poll, which cannot move when Dark is already stored.
- **The flight is landed.** Flight 5 is checked off in `mission.md`, and the Ctrl K Known
  Issue now waits only on the operator at Flight 6. The debrief is next, then the merge
  and release.

---

## Decisions

*(runtime decisions not in the flight spec)*

---

## Deviations

---

## Anomalies

---

## Session Notes

### Debrief (2026-10-06)

- **The debrief was written** (`flight-debrief.md`), with a Developer and an Architect
  (both Sonnet) interviewed. The operator was not interviewed: this was an autonomous
  run, and the operator had asked to merge and release.
- **Metrics:** unit 5428 passed (+250 against Flight 4, wall time flat). The browser lanes
  were reused from leg 4, since no browser-facing code changed since.
- **Squawks logged:** 0124 (pin the helper's CI closure) and 0125 (the pywebview 6.x
  upgrade-blocker note).
- **The flight is marked `completed`.** Next: squash-merge PR #221, then release
  `v0.10.0`.
