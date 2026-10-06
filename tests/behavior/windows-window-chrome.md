# Behavior Test: Windows Window Chrome

**Slug**: `windows-window-chrome`
**Status**: active
**Created**: 2026-10-06 (Mission 25 Flight 5 planning)
**Revised**: 2026-10-06 (Mission 25 Flight 5 leg 4: written against the real helper and the values legs 1-3 observed, and dry-run on the frozen test copy)
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

- **The helper and its safety rules.** Every Windows action goes through
  `scripts/windows_test_copy.py`, run from WSL as
  `.venv/bin/python scripts/windows_test_copy.py --run-id <id> <command>`; below it is
  written `helper <command>`. The safety rules (one gate tree found by PID, never by title;
  the foreground, pointer and hands-off gates; the key denylist; capture containment and the
  occlusion test; the own windows; focus save and restore; identity-checked stops) are the
  ones in `the_one/agents.md` "Windows test copy". They are not repeated here, and a refusal
  from the helper is an apparatus problem, never a product failure.
- **Consent and session.** The operator agreed to a test copy on their desktop
  (2026-10-06). The Orchestrator tells the operator in one line when a session starts and
  ends. The session must be **unlocked** (a locked session captures black; the helper exits
  6) and the operator idle (the helper waits on `hands-off`, exit 3 if it times out). If
  either fails, the run waits or reports BLOCKED; it does not judge.
- **Host.** Windows 11 build 22000 or later, reached from WSL through `powershell.exe`
  (the operator's interactive session). WSL networking is mirrored, so the WebView2
  debugging port on Windows `127.0.0.1` is reachable from WSL. `helper doctor-host` records
  the build, the WebView2 version, the DPI, the OS app and system themes, accent colour on
  title bars, transparency, any `WEBVIEW2_*` variables set user- or machine-wide, and the
  networking mode. **The expected colours in step 1 assume the OS app theme is Light**
  (`AppsUseLightTheme` 1, as `doctor-host` reports). If it is Dark, step 1's expectations
  swap to the Dark column (the splash and caption start dark).
- **The test copy.** `helper setup` (and `helper freeze` for the close gate, then every
  `launch` below carries `--frozen`) builds it from the working tree under test into the
  scratch root `%LOCALAPPDATA%\Temp\the-one-f5\` (written `R`). The run log records which
  build was used, frozen or from source.
- **SAFETY, never the installed app.** The operator's installed `the-one-app.exe` runs on
  **8484** in session 1 with its data in the operator's default data dir. Use app port
  **8490** and debugging port **9390** (8490 or higher and 9390 or higher, never 8484 or
  8485), and a **fresh data dir** under `R` named for the run, for example `data-<run>-1`
  (the helper refuses anything at, inside or containing the operator's dir, and a frozen
  launch is refused while the operator's data dir holds a `.env`). The debugging port is set
  only in the launched process (`launch --cdp-port`), never with `setx`.
- **Credential.** For `GET /api/window/chrome` and `/api/info`, read
  `R\<scratch data dir>\api-credential` verbatim and send it as a bearer token, per
  CLAUDE.md's "Behavior-test credential convention". The window authenticates itself, so
  the page needs nothing. `/api/live` needs no credential.
- **CDP.** Page reads and clicks use Playwright `chromium.connect_over_cdp("http://127.0.0.1:9390")`
  from the repo venv, on the page whose URL is on port 8490. One held CDP session is needed
  wherever a step says "emulate" (a detached session drops the emulation).
- **Colour sampling.** A caption is sampled with `helper pixel --x X --y Y` (9x9 patch) at the
  caption's empty middle: the window's DWM frame bounds (`helper rect`, `frame_bounds`)
  left plus half the frame width, top plus 15. It passes when every channel is within +-3 of
  the target. Title text is judged from `helper pixel --size 31` over the text (frame left +
  about 75 to 105, same row): the darkest pixel for Light, the lightest for Dark.
  Caption-button glyphs are judged from the extreme pixel of a 15 px patch at frame right
  minus 115 (minimize).
- **The expected colours** (Flight 5 DD2 and DD5):

  | Theme | Caption | Title text, active | Title text, inactive | Page `--bg` | Window border |
  |---|---|---|---|---|---|
  | Light | `#fafafa` (250,250,250) | `#18181b` | `#6e6e77` | `#ffffff` | light |
  | Dark | `#17181c` (23,24,28) | `#ededf0` | `#85878f` | `#101114` (16,17,20) | `#26272c` (38,39,44) |

- **Host theme.** The run never changes the OS theme. Auto is exercised with WebView2's
  emulated `prefers-color-scheme` (CDP `Emulation.setEmulatedMedia`).
- **Page storage is flushed lazily.** WebView2 writes `localStorage` about 5 seconds after a
  change, and later after a burst of changes (a rapid sequence of theme flips defers the last
  write by more than 20 seconds). Step 7 therefore flushes by observation, not by sleeping.

## Observables Required

- **desktop:** the window's on-screen pixels and rect through `helper capture`, `helper
  pixel` and `helper rect|windows`, including a rapid series (`capture --series`, 40ms) during
  launches.
- **input:** real OS keyboard and mouse input through `helper keys|click|drag|front|show-window`
  and `helper resize` (SetWindowPos, the one non-input command that changes the window).
- **browser:** the page in the test copy's WebView2, through CDP (DOM, `innerWidth` and
  `innerHeight`, `data-theme`, `localStorage`, emulated media).
- **http:** `GET /api/window/chrome` (`requested`, `last_applied`, `pending`, the HRESULTs),
  `/api/live` and `/api/info` (curl from WSL).
- **filesystem:** `window-chrome.json` and `window-state.json` in the scratch data dir, the
  newest `webview\EBWebView\Default\Local Storage\leveldb\*.log` mtime, and the snapshot of
  the operator's data dir.
- **shell:** the process list through `helper tree` and `helper windows`.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | `helper snapshot --out <file>`, `helper focus-save`, `helper screen`, then `helper own-window show --id a --seconds 600` (the inactive window of step 5). Create no `window-state.json` or `window-chrome.json` (a fresh data dir). Run `helper launch --frozen --port 8490 --cdp-port 9390 --data-dir data-<run>-1 --tree-id main` in the background. As soon as `R\pids\main.json` exists (the helper refuses an unrecorded tree), start two concurrent series: `helper capture --window --splash --series 200 --interval-ms 40 --tree-id main --out splash` and `helper capture --rect X,Y,20,10 --series 200 --interval-ms 40 --tree-id main --out caption`, with the rect a 20x10 strip at the horizontal centre of the expected window, 10 px below its top (this host: 1270,256; the window is 1440x900 centred in the work area `screen` reports). When `launch` returns (`live` and `info` 200), `helper front --tree-id main`, `helper capture --window --out first-launch`, `helper rect`, and over CDP read `innerWidth`, `innerHeight` and `data-theme`. | The splash frames (the `--splash` series) are light: every channel above 220 in every frame (the first frame can be the 1px border at about 228), never dark. The caption series' first frame that sees the main window already reads `#fafafa` (+-3), and no later frame differs. The main window's outer rect is 1440x900, centred in the work area (+-2). `innerWidth` is at least 1280 (1424 here). `data-theme` is `light` (Auto, OS light). The capture shows the caption `#fafafa`, the title "GleepGlorp AI" dark, dark caption-button glyphs, and the app (rail, "Chats", "Hello."), not an error page. |
| 2 | `GET /api/window/chrome` (bearer token from the scratch `api-credential`). Read `window-chrome.json` in the data dir. | `pending` is `false`. `last_applied.theme` is `light` and `last_applied.results` has every HRESULT `0` (`dark_mode`, `border`, `caption`, `text`) and `last_applied.error` is null; the top-level `supported` is true. `launch_theme` is `light`. `window-chrome.json` holds `{"theme": "light"}`. The pass is judged on `last_applied` with `pending: false`, never on `requested` alone. |
| 3 | `helper front --tree-id main`. `helper rect` for the client origin, then `helper click <client left + 700> <client top + 500>` (an empty page area; here 1268,777). `helper keys '^k'`. Over CDP read whether `[data-testid="jump-to"]` exists and the active element. `helper keys '{ESC}'`, then read again. | After Ctrl+K, one `[data-testid="jump-to"]` dialog is open and focus is in `jump-to-input`. After Esc it is gone and focus is back on `MAIN`. |
| 4 | Over CDP, open Settings > Appearance (`location.hash = '#settings/appearance'`) and click `.admin-theme-option[data-theme-pref="dark"]`. At once `helper pixel` the caption, the title text and the caption-button glyph, and `helper capture --window --out dark-active`; sample one border pixel at frame left (`--size 1`, y mid-height). `GET /api/window/chrome`. Read `window-chrome.json`. | `data-theme` is `dark`. The caption reads `#17181c` (+-3). The title text's lightest pixel reads close to `#ededf0`. The glyph patch's lightest pixel is white-ish (the glyph is light on the dark caption, contrast at least 7:1). The window border pixel is dark (38,39,44, +-6), not a light outline. The GET reports `last_applied.theme` `dark`, `active` true, `pending` false, HRESULTs `0`, and `window-chrome.json` holds `dark`. |
| 5 | `helper click` own window A's centre (its rect from `own-window show`; here 108,1330) so the helper's own window is in front and the test copy is inactive. `helper foreground` (class `TheOneF5Owna`). Sample (`helper pixel`) and `GET /api/window/chrome`. Then over CDP click **Light**, sample, capture (`--out light-inactive`) and GET again; click **Dark**, sample and GET again. Then `helper front --tree-id main` and sample and GET. | Inactive, dark: the caption stays `#17181c` and the title text's lightest pixel is dimmer, close to `#85878f`; the GET has `active` false. Light while inactive: caption `#fafafa` with the title text's darkest pixel close to `#6e6e77`, and `last_applied` `light`, `active` false. Dark again while inactive: `#17181c` with close to `#85878f`. It never shows the active text colour (`#ededf0` or `#18181b`) while inactive. After `front`: the title text is back to `#ededf0` and the GET has `active` true. |
| 6 | In one held CDP session: click **Light**, sample; click **Auto**, sample (OS light); `Emulation.setEmulatedMedia` `prefers-color-scheme` `dark`, wait 1 s, read `data-theme` and sample; emulate `light`, read and sample; clear the emulation (`{"media": "", "features": []}`); then click **Dark**. | Light: `data-theme` `light`, caption `#fafafa`. Auto with the OS light: `light`, `#fafafa`. Auto with emulated dark: `data-theme` `dark` and the caption `#17181c`. Auto with emulated light: `light` and `#fafafa`. Cleared: `light`. Dark: `dark` and `#17181c`. Each change is on screen by the sample taken one second later. |
| 7 | Over CDP click **Dark**. Poll the mtime of the newest `R\<data dir>\webview\EBWebView\Default\Local Storage\leveldb\*.log` until it is newer than the click (about 5 s; wait up to 120 s, and if it never moves report INCONCLUSIVE, not FAIL). `helper front`, then `helper click` the caption's x button (frame right minus 30, top plus 15; here 1963,261) so the window hides to the tray and saves its geometry. Check `helper windows` (the main window not visible), `/api/live` 200, `window-state.json` and `window-chrome.json`. `helper stop --tree-id main` and wait until `helper tree` is empty and the ports are free. Start the launch in the background again (`--tree-id main2`, same data dir) and, as soon as `R\pids\main2.json` exists, the same two series (`--out splash2`, `--out caption2`). When the launch returns, read `data-theme` and `localStorage` `theme-preference` over CDP. | The x hid the window (not visible), `/api/live` stayed 200, `window-state.json` holds the 1440x900 size and position, `window-chrome.json` holds `dark`. In the relaunch no splash frame is light (every channel below 60) and no caption-strip frame is light or white: the first frame that sees the main window already reads `#17181c`, and every later one does. The page comes up dark (`data-theme` `dark`, `theme-preference` `dark`) and the window reopened at the saved size and position (+-2). |
| 8 | `helper stop --tree-id main2` and wait for the tree to be gone. Write `{"width": 400, "height": 250, "x": 100, "y": 100}` to the data dir's `window-state.json`. `helper launch --frozen ... --tree-id floor`, then `helper rect`. Then `helper resize --width 400 --height 250 --tree-id floor` and read the result, then `helper resize --width 1000 --height 700 --tree-id floor` and read it. (The `resize` command is used because a drag cannot start on the invisible resize border.) | At launch the outer size is 640x360 (+-2) at (100,100), because the floor lifted the saved size. `resize` to 400x250 leaves the outer size at 640x360 (+-2): the window stopped at its floor. `resize` to 1000x700 gives 1000x700 (+-2), and the page's `innerWidth` follows (984 here). `helper resize --width 50 --height 700` is refused (exit 2). |
| 9 | `helper resize --width 1200 --height 800 --tree-id floor`; `helper front`; `helper rect` for the frame bounds. `helper click <middle> <top+15> --double` on the caption's empty middle, `helper rect` and `helper pixel` on the caption (now at the top of the work area), `helper capture --window --out maximized`; `helper click --double` again and `helper rect`. `helper click <frame right - 115> <top + 15>` (the minimize button), `helper windows`, then `helper show-window --restore --tree-id floor` and sample the caption. `helper drag <middle> <top+15> <middle+200> <top+115> --caption --tree-id floor`, `helper rect`. Click into the page body, send `helper keys '^k'` and `'{ESC}'` over CDP reads. | The first double-click maximizes the window to the work area (frame bounds equal the work area, `0,0,2560,1392` here) and the caption keeps `#17181c`. The second restores the 1200x800 frame. Minimize hides the window to the taskbar (outer rect at about -32000), and `show-window --restore` brings back the same frame with the same caption colour. The caption drag moves the frame by 200 right and 100 down (+-4), and the page is still interactive (Ctrl K opens Jump to, Esc closes it). |
| 10 | `helper click` the caption's x button. `helper windows`, `helper tree` and `curl /api/live`. | The window is hidden, not closed. The test copy's processes are still running and `/api/live` returns 200. This is close-to-tray, unchanged. |
| 11 | `helper stop` (all trees; it also closes the own windows) and wait until `helper tree` is empty and nothing listens on 8490 or 9390. `helper focus-restore`. `helper own-window close --id a` if it is still running. `helper snapshot --compare <step 1's file>`. | The test copy's processes are gone. The installed app has the same PID and start time. Every snapshotted file in the operator's data dir has the same existence, mtime and hash (`ok`, exit 0). Two changes are reported, not failed: `window-state.json` if the operator closed the installed app or sent it to the tray during the run, and a new PID if they restarted it. `focus-restore` reports `restored` or `already-foreground`. |

## Out of Scope

- **A real OS theme flip.** It changes the operator's whole desktop. The run emulates it
  in the page (step 6), and the operator checks the real flip at Flight 6.
- **Checked by the operator in the packaged build at Flight 6**
  (`windows-native-frame-splash`):
  - snap layouts (halves and thirds) and Win+arrow snapping;
  - the tray menu's Quit;
  - a fresh install, and an upgrade with an existing `window-state.json`;
  - the look in daily use.
- **The splash's logo.** On a warm boot the splash lives 0.3 to 1 second and its WebView2
  has not painted its logo before the main window covers it, so the run judges the splash's
  colour only. The operator judges the splash in daily use.
- **A live drag to the size floor.** The invisible resize border cannot be a drag start
  (leg 3); step 8 proves the floor at launch and through `resize`.
- **Windows 10** (dark-mode-only path), scaling above 100% and multiple monitors. No such
  host is available.
- **The DWM call logic, colour maths, the requested-theme race and first-paint ordering as
  units.** These are covered by host-native pytest.
- **Linux and macOS.** There is no tint there.

## Variants (optional)

None. Both themes are exercised inside the steps.
