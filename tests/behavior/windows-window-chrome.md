# Behavior Test: Windows Window Chrome

**Slug**: `windows-window-chrome`
**Status**: draft
**Created**: 2026-10-06 (Mission 25 Flight 5 planning; finalized in leg 4 against legs 1–3)
**Last Run**: never

## Intent

This test checks that the desktop window's native title bar takes the workbench's colours
in both themes and follows every theme change. It also checks:
- the first frame is already in the right colours;
- the window opens at about the board's size;
- the native frame still maximizes, minimizes, drags and hides to the tray;
- a real Ctrl K reaches the page in WebView2.

None of this has a CI apparatus: the Windows CI worker runs in session 0 with no
desktop. Unit tests prove the calls and their order, but only a real window on a real
Windows desktop shows the pixels.

The crew drives a **test copy** of the branch under test on the operator's desktop
(Flight 5 DD10). It reads the frame's pixels from the screen and the page through
WebView2's debugging port. A Validator judges each step from the captures.

## Preconditions

- **Consent.** The operator agreed to a test copy on their desktop (2026-10-06). The
  Orchestrator tells the operator in one line when a session starts and ends. The
  operator's Windows session must be **unlocked**, because a locked session captures
  black. The helper reports that, and the run waits rather than judging it.
- **Host.** Windows 11 build 22000 or later, reached from WSL through `powershell.exe`
  (which runs in the operator's interactive session). WSL networking is mirrored, so the
  WebView2 debugging port on Windows `127.0.0.1` is reachable from WSL.
- **The session record.** At the start, the helper records:
  - the build;
  - the WebView2 runtime version;
  - the DPI;
  - the OS app and system themes;
  - accent colour on title bars and transparency;
  - any `WEBVIEW2_*` variables already set user- or machine-wide;
  - the networking mode.

  The expected colours in step 1 assume the OS app theme is Light
  (`AppsUseLightTheme=1`). If it is Dark, step 1's expectations swap to the Dark row.
- **The test copy** is built with `scripts/windows_test_copy.py setup` (and `freeze` for the
  close gate) from the working tree under test, into the scratch root
  `%LOCALAPPDATA%\Temp\the-one-f5\`. The run log records which build was used: frozen
  one-dir or from source.
- **SAFETY — never the installed app:**
  - The operator's installed `the-one-app.exe` runs on **8484** in session 1, with its
    data in the operator's default data dir. The helper resolves that dir through
    platformdirs and never guesses it.
  - Use a port of **8490 or higher** (never 8484 or 8485), free on both the Windows and
    WSL sides (mirrored networking shares one port space). Use a **fresh scratch data dir**
    under the scratch root, never at, inside or containing the operator's data dir. The
    helper refuses all of these.
  - A frozen launch is refused if the operator's data dir holds a `.env`: a frozen build
    reads it whatever `THE_ONE_DATA_DIR` says.
  - Set `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` only in the launching process, never with
    `setx`.
  - **Snapshot.** Step 1 takes it and step 11 compares it: the installed app's PID and
    start time, and the existence, mtime and hash of `api-credential`, `.env`,
    `window-chrome.json` and `window-state.json` in the operator's data dir.
- **Input safety.** Every injected key, click or drag goes through the helper:
  - **Window identity.** It finds windows only through the recorded process tree (the
    launched PID and its descendants), never by title.
  - **Keys** are refused unless `GetForegroundWindow()` belongs to the tree.
  - **Pointer input** is refused unless `WindowFromPoint` at the target belongs to the
    tree or to the helper's own window.
  - **Operator activity.** It waits while the operator has used the keyboard or mouse in
    the last 5 seconds (`GetLastInputInfo`, ignoring the helper's own injections). It
    checks once before each compound gesture.
  - **Refusals.** A refused or timed-out injection is reported as an apparatus problem,
    never judged as a product failure.
  - **Sampling.** Before a pixel sample, the helper checks that the sample points are not
    covered.
- **Launch-time captures.** If leg 1 found that a WSL-launched window can open behind
  other windows, the first-paint clauses in steps 1 and 7 come from `PrintWindow`, if it
  renders the tinted frame. Otherwise those clauses are INCONCLUSIVE, not FAIL, and are
  left to the operator at Flight 6.
- **Processes.** Stop only the PIDs the helper recorded at launch, with their process
  tree, never by name pattern.
- **Credential.** For `GET /api/window/chrome` and `/api/info`, read
  `<scratch data dir>\api-credential` verbatim and send it as a bearer token. This follows
  CLAUDE.md's "Behavior-test credential convention". The window authenticates itself
  through the in-process handoff, so the page needs nothing. `/api/live` needs no
  credential.
- **Colour sampling.** A caption colour is read from a 9×9 patch in the caption's empty
  middle: right of the title text, left of the caption buttons, vertically centred. It
  passes when every channel is within ±3 of the target. Title text is judged from the
  zoomed capture: present, legible, and dark or light as stated.
- **The expected colours** (Flight 5 DD2 and DD5):

  | Theme | Caption | Title text, active | Title text, inactive | Page `--bg` |
  |---|---|---|---|---|
  | Light | `#fafafa` | `#18181b` | `#6e6e77` | `#ffffff` |
  | Dark | `#17181c` | `#ededf0` | `#85878f` | `#101114` |

- **Host theme.** The run never changes the OS theme. Auto is exercised with WebView2's
  emulated `prefers-color-scheme`, in the same CDP session as steps 4–6.

## Observables Required

- **desktop:** the window's on-screen pixels (`CopyFromScreen` of the window rect, after
  the foreground and occlusion checks) and the window rect (`GetWindowRect`), both through
  `scripts/windows_test_copy.py capture|pixel|rect`. Also a rapid screen-capture series
  (every 100ms or faster) during launches.
- **input:** real OS keyboard and mouse input through `SendInput`
  (`windows_test_copy.py keys|click|drag`), with the input-safety checks above.
- **browser:** the page in the test copy's WebView2, through CDP on its debugging port
  (DOM, accessibility tree, screenshot, `window.innerWidth` and `innerHeight`, emulated
  media).
- **http:** `GET /api/window/chrome` (requested and applied theme, each DWM call's
  HRESULT), `/api/live` and `/api/info` (curl from WSL).
- **filesystem:** `window-chrome.json` and `window-state.json` in the scratch data dir,
  and the operator data-dir snapshot.
- **shell:** process list and PIDs (`powershell.exe`).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Take the snapshot. Create a fresh scratch data dir (no `window-state.json`, no `window-chrome.json`). Start a rapid capture series, then launch the test copy on its port with the debugging port set. Wait for `/api/live` and for the main window, then stop the series. `GET /api/info` with the scratch credential. Bring the window to the front, capture it, read its rect and, over CDP, `innerWidth`/`innerHeight` and `data-theme`. | The splash showed with a light background and dark text from its first captured frame, then went away. `/api/info` answers 200 on the requested port. The main window's outer rect is 1440×900, centred in the work area (within 2px). The viewport is at least 1280 wide. `data-theme` is `light` (Auto, OS light). The caption reads `#fafafa`, and the title "GleepGlorp AI" is dark. The caption buttons are dark glyphs on the light caption. The page is the app, not an error. |
| 2 | `GET /api/window/chrome`. Read `window-chrome.json`. | The requested and applied theme are `light`. Caption colours are supported. Every attribute's last HRESULT is `0`. `window-chrome.json` holds `light`. |
| 3 | Click into the page body (`click`, real input). Send a real **Ctrl+K** (`keys ^k`). Read the palette over CDP, then send **Esc**. | After Ctrl+K, one `[data-testid="jump-to"]` dialog is open with focus in `jump-to-input`. After Esc it is closed. No browser UI appeared (no find bar, no address or search box). |
| 4 | Over CDP, open Settings › Appearance and click **Dark**. Within 1 second, capture the window. `GET /api/window/chrome`. | `data-theme` is `dark`. The caption reads `#17181c` and the title text is light. The caption buttons are light glyphs that are legible on the dark caption. The window's 1px border is dark, not a light outline. The GET reports `dark` with HRESULTs `0`, and `window-chrome.json` holds `dark`. |
| 5 | Bring the helper's own small window to the front, and capture the test copy. While it is still inactive, click **Light** over CDP and capture again, then click **Dark** over CDP and capture. Then bring the test copy back to the front and capture it. | Inactive: the caption stays `#17181c`, and the title text is dimmer than when active (it reads close to `#85878f`). The theme change while inactive gives caption `#fafafa` with inactive light text (close to `#6e6e77`), then back to `#17181c` with close to `#85878f`. It never shows the active text colour while inactive. Active again: the title text is back to `#ededf0`. |
| 6 | Click **Light**. Capture. Then click **Auto**, and over CDP emulate `prefers-color-scheme: dark`. Capture. Then emulate `prefers-color-scheme: light` and capture again. Clear the emulation. | Light: caption `#fafafa`. Auto with emulated dark: `data-theme` is `dark` and the caption is `#17181c`. Auto with emulated light: `data-theme` is `light` and the caption is `#fafafa`. Each change shows within 1 second. |
| 7 | Click **Dark**, then wait 10 seconds so the page's storage is on disk. Click the caption's × (real input), so the window hides to the tray and saves its geometry. Stop the test copy by its recorded PIDs, app first, and wait until the tree has exited and its ports are free. Start a rapid capture series, relaunch with the same data dir, and stop the series once the main window has painted. | No capture shows the splash or the main window with a light caption, a white page area or a white splash. The first capture that shows the splash or the main window is already dark, and the main window's caption is `#17181c`. The window reopened at the size and position saved when it was hidden. |
| 8 | Stop the test copy. Write `{"width": 400, "height": 250, "x": 100, "y": 100}` to the scratch `window-state.json`. Relaunch, and read the rect. Then drag the bottom-right corner inward by 300, 200 (real input) and read the rect again. | At launch the outer size is 640×360 (±2), because the floor lifted the saved size. After the drag, the outer size is still 640×360 (±2): the window stopped at its floor. |
| 9 | Drag the window back to about 1200×800. Double-click the caption's empty middle (real input). Capture. Double-click again. Click the caption's minimize button, then restore the window with `ShowWindow(SW_RESTORE)` on its handle. Drag the caption 200px right and 100px down (real input) and read the rect. | The first double-click maximizes the window to the work area, and the caption keeps the theme colour. The second restores it. Minimize hides the window to the taskbar, and restoring brings it back with the same caption colour. The drag moves the window by 200, 100 (within 4px), and the page stayed interactive. |
| 10 | Click the caption's × (real input). Read the process list, the window's visibility and `/api/live`. | The window is hidden, not closed. The test copy's process is still running and `/api/live` returns 200. This is close-to-tray, unchanged. |
| 11 | Stop the test copy by its recorded PIDs, and wait until the tree has exited and its ports are free. Take the snapshot again and compare it with step 1's. | The test copy's processes are gone. The installed app has the same PID and start time. Every snapshotted file in the operator's data dir has the same existence, mtime and hash. Two changes are reported, not failed: `window-state.json` if the operator closed the installed app or sent it to the tray during the run, and a new PID if they restarted it. |

## Out of Scope

- **A real OS theme flip.** It changes the operator's whole desktop. The run emulates it
  in the page (step 6), and the operator checks the real flip at Flight 6.
- **Checked by the operator in the packaged build at Flight 6**
  (`windows-native-frame-splash`):
  - snap layouts (halves and thirds) and Win+arrow snapping;
  - the tray menu's Quit;
  - a fresh install, and an upgrade with an existing `window-state.json`;
  - the look in daily use.
- **Windows 10** (dark-mode-only path), scaling above 100% and multiple monitors. No such
  host is available.
- **The DWM call logic, colour maths, the requested-theme race and first-paint ordering as
  units.** These are covered by host-native pytest.
- **Linux and macOS.** There is no tint there.

## Variants (optional)

None. Both themes are exercised inside the steps.
