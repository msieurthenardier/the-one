# Behavior Test: Windows Native Frame & Splash

**Slug**: `windows-native-frame-splash`
**Status**: active
**Created**: 2026-06-15
**Revised**: 2026-06-16 (PIVOT DD2-alt — native OS frame replaces frameless custom chrome)
**Revised**: 2026-10-06 (Mission 25 Flight 5 leg 4 — retargeted at the operator's own installed build for Flight 6; step 9 rewritten for the credential gate; steps 11-19 added for Mission 25 SC9: the tinted title bar, first-launch size, Ctrl K and the splash)
**Last Run**: 2026-06-17-00-47-21 (pass — [run log](windows-native-frame-splash/runs/2026-06-17-00-47-21.md)); steps 11-19 not yet run

## Intent

Verify the **visual polish** on the installed Windows app — a **native OS-framed window**
with the brand title ("GleepGlorp AI") and icon, a launch splash, working native
min/max/close via the OS title bar, native drag and edge-resize, close-to-tray preserved
on the native X, and a brand taskbar icon — none of which has a CI apparatus (DD6). Only a
human on a real Windows host can both *drive* (use the native title bar controls, drag the
window, drag edges to resize, watch the launch) and *observe* (the native window actually
minimizes / maximizes / hides-to-tray / moves / resizes; the splash appears then dismisses;
the taskbar shows the brand icon; it looks finished). The deterministic seams (splash
create/dismiss wiring, close-to-tray routing, window-state restore) are covered by
host-native pytest; this test covers the end-to-end native + visual result.

Since Mission 25 Flight 5 it also covers what only the operator can judge on their own
machine and their own eyes: the title bar's tint in both themes, its follow of a **real**
OS theme flip, snap layouts, a real upgrade, a fresh profile's first window, and the
splash in daily use (Mission 25 SC9). The crew spec `windows-window-chrome` proves the
rest on a test copy.

## Preconditions

- **The target is the operator's own installed build, driven by the operator** (Mission 25
  Flight 6). The installed app is therefore the thing under test, so its default port
  **8484** and its own data directory (`%LOCALAPPDATA%\the-one`) are expected here, and
  only here, because the operator drives it by hand. The installed build is the one
  produced by Concourse `windows-installer` for the flight under test. The crew's
  dedicated-copy and no-8484 rules (`windows-window-chrome`) do not apply to this spec, and
  an agent never runs this spec on the operator's behalf.
- A way to read the **Windows taskbar / process** (visual + `tasklist`) and the data-dir
  crash log (`%LOCALAPPDATA%\the-one\logs\the-one-app.log`) for any failure.
- Operator-relayed observation (or screenshots) — this is an operator-driven Witnessed run.
- **Credential**: this build is gated (Mission 20 Flight 1). The `api-credential` file
  lives in the per-user data dir (platformdirs `user_data_dir("the-one")`, next to the
  crash log's parent) — read it and attach `Authorization: Bearer <credential>` to the
  `/api/info` GETs in steps 7 and 8, per CLAUDE.md's "Behavior-test credential
  convention". The app's own window (steps 1-6, 10-19) authenticates itself internally
  via the desktop launcher's in-process handoff — nothing needed from the operator there.
- **Upgrade state (steps 16-17).** Step 16 needs the **first launch after the upgrade**
  with the operator's existing `window-state.json` in place (do not delete it before
  launching the new build). Step 17 needs a fresh profile: the operator chooses to rename
  `window-state.json` (and, if they want to see the theme default too, `window-chrome.json`)
  to a `.bak` name, then launches, then renames them back.
- **First-launch note (flight DD4, not a defect).** On the first launch after the upgrade
  the frame may show light, or the page area may flash white, once, when the OS app theme
  and the app's saved theme preference differ. The tint is applied from the theme stored by
  the new build, which is empty until the new build has run once. Judge step 12 and the
  Dark rows of steps 11 and 13 from the second launch on.
- **Time and display.** The OS app theme is set where the operator can flip it (Settings,
  Personalization, Colors, "Choose your mode"). Step 13 (real flip) changes the whole
  desktop for a moment; the operator picks a quiet time and flips back.

## Observables Required

- gui (native-framed window + OS title bar with brand name and icon; window min/max/
  restore/hide via native controls; native titlebar drag-move; edge-resize; splash
  appear/dismiss; taskbar icon; title-bar tint and active/inactive text; snap-layout
  flyout and snapped positions; first-launch window size and position — operator visual /
  screenshot)
- process (the-one-app.exe present/absent — `tasklist`)
- http (`/api/info` 200 vs refused — curl, to confirm hide-vs-quit)
- filesystem (crash log if a step fails — Read; `window-state.json` and
  `window-chrome.json` for steps 16 and 17)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Launch the app from the Start menu. Watch the launch closely. | A **splash** (brand logo + loading bar) appears while the app boots, then **dismisses** when the main UI loads. The main window opens with a **native OS title bar** showing "GleepGlorp AI" and the brand icon — no custom titlebar overlay. |
| 2 | Inspect the **taskbar** icon for the running app. | The taskbar shows the **GleepGlorp brand icon**, not the generic PyInstaller/Python icon. |
| 3 | Click the **native minimize** button (OS title bar). | The window **minimizes** to the taskbar. Click the taskbar entry → it restores. |
| 4 | Click the **native maximize/restore** button (OS title bar). | The window **maximizes** to fill the work area; clicking again **restores** to the prior size. |
| 5 | **Drag the native title bar** to move the window. | The window **moves** with the drag. The rail's destination links (`#app-rail`) and the app itself remain fully interactive (native frame, no drag-region interfering). |
| 6 | **Drag a window edge/corner** to resize. | The window **resizes** freely — native OS edge-resize works as expected (native frame provides this without custom grips). |
| 7 | Click the **native close** button (OS title bar X). Then `tasklist` + GET `/api/info`. | The window **hides to the tray** (F6 close-to-tray preserved — the native X fires `events.closing` → `_on_closing` → hide): tray icon remains, process still listed, `/api/info` still 200. (Not a quit.) |
| 8 | Restore from the tray; then **Quit** from the tray menu. | Window restores; Quit exits cleanly (tray gone, `/api/info` refused) — F6 teardown unchanged under the native frame. |
| 9 | Launch the app again. Open `http://localhost:8484/` in a **plain browser** (a normal browser window, no handoff), with the app running. | The browser is **refused** with a not-authenticated response (the credential gate; no session cookie, no handoff). It shows **no app page and no window controls** of any kind: the OS/browser frame is all there is. (The custom-control check is moot since Mission 15's revert to the native frame.) |
| 10 | *(regression)* Re-confirm F6 behaviors under the native frame: move/resize → Quit → relaunch restores geometry; theme persists. | Geometry restored, theme persists — the revert to native frame didn't regress F6. |
| 11 | *(SC9 title bar, both themes)* In Settings › Appearance choose **Light**, then **Dark**. For each, look at the title bar. | The title bar is the workbench's own colour: **Light** a very light grey-white (`#fafafa`) with dark title text and dark min/max/close glyphs; **Dark** a near-black (`#17181c`) with light title text and light glyphs. The bar reads as part of the app, not a separate system-coloured strip. The glyphs are legible in both. |
| 12 | *(SC9 follows a Settings change)* With the window in front, flip Light → Dark → Light → Dark in Settings › Appearance a few times. | The title bar changes **at once** with the page each time (no lag, no wrong colour left behind, no flicker to the old colour). |
| 13 | *(SC9 Auto follows a real OS flip)* Set the preference to **Auto**. Then flip the OS app theme (Settings › Personalization › Colors › "Choose your mode": Light ↔ Dark) while the app is open. Flip back when done. | The page **and** the title bar follow the OS flip, both ways. The title bar's text and glyph colours follow too. |
| 14 | *(SC9 inactive title)* With the app open, click another window so the app is behind it. Look at the app's title bar, then click the app again. Do it once in Light and once in Dark. | The **inactive** title text is **dimmer** than the active title text in both themes; the caption colour itself stays the theme colour. Active again: the text is back to full strength. |
| 15 | *(SC9 snap layouts)* Hover the **maximize** button for about a second. Choose a half from the flyout, then a third layout position. Then use **Win+Left**, **Win+Right**, **Win+Up** and **Win+Down**. Restore the window afterwards. | The snap-layout **flyout appears** on the maximize button and snapping to **halves** and to **thirds** works, as do the Win+arrow keys. The title bar keeps its colour and the page stays interactive after each snap. |
| 16 | *(SC9 upgrade keeps the size)* On the **first launch after the upgrade**, with the existing `window-state.json` in place, look at the window's size and position. | The window opens at the **size and position the operator had before** (the saved geometry is restored; not 1440x900, not re-centred). |
| 17 | *(SC9 fresh profile)* Quit. Rename `window-state.json` to a `.bak` name (and, optionally, `window-chrome.json`). Launch. Quit, then rename the files back. | A fresh profile opens at about **1440×900, centred** on the screen (smaller only if the work area is smaller), at least 1280 wide where the screen allows. |
| 18 | *(SC9 Ctrl K)* Click in an empty part of the page, then press **Ctrl+K**, then **Esc**. | Ctrl+K opens the **Jump to** palette with the cursor in its search field; **Esc** closes it. No browser find bar or address box appears. |
| 19 | *(SC9 splash)* Quit and launch again, once with Light selected and once with Dark selected, watching the first second. | The **splash matches the theme** (a light splash in Light, a dark one in Dark; no white flash in Dark), and the **main window replaces it with no gap** where nothing is on screen. (On a fast machine the splash may be only a themed rectangle for a moment before the window appears; that is expected.) |

## Out of Scope

- Tray / background-run / single-instance / window-state **logic** — covered by F6's
  `windows-desktop-presence` + host-native pytest; this test only re-confirms they still
  work under the native frame (steps 8, 10).
- The splash-wiring / close-to-tray **unit contracts** — host-native pytest.
- The title bar's colour values, the activation tracking, the first-launch size and the
  Ctrl K delivery on a **test copy** — covered by the crew spec `windows-window-chrome`
  (steps 11-19 here are the operator's own-eyes, own-machine confirmation of the same).
- macOS / Linux — the follow-up port mission.

## Variants (optional)

- **Per-monitor DPI**: if the operator has a multi-monitor / mixed-DPI setup, repeat
  steps 5–6 with the window dragged to a different-scaling monitor (splash sizing is a
  known DPI risk area on Windows).
- **Scaling above 100%** (125%, 150%): repeat steps 11, 14 and 17. Check that the title
  bar tint is unchanged, that the first-launch window is still about 1440×900 of **logical**
  size on screen, and that the window is not cut off by the screen's edge.
- **Several monitors**: repeat step 17 with the mouse on a second monitor when launching.
  `CenterScreen` uses the monitor under the mouse, so the window should open centred on
  **that** monitor.
