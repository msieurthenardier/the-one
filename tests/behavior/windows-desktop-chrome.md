# Behavior Test: Windows Desktop Chrome & Splash

**Slug**: `windows-desktop-chrome`
**Status**: draft
**Created**: 2026-06-15
**Last Run**: never

## Intent

Verify the F7 **visual polish** on the installed Windows app — frameless window with a
themed custom titlebar, working window controls, a launch splash, and a brand taskbar
icon — none of which has a CI apparatus (DD6). Only a human on a real Windows host can
both *drive* (click the custom min/max/close, drag the titlebar, drag window edges to
resize, watch the launch) and *observe* (the native window actually minimizes /
maximizes / hides-to-tray / moves / resizes; the splash appears then dismisses; the
taskbar shows the brand icon; the chrome "looks finished"). chrome-devtools/Playwright
can drive the HTML titlebar DOM but cannot observe the **native** window-manager effects
or the taskbar icon. The deterministic seams (the `js_api` methods calling the right
window methods, the `window.pywebview`-gated titlebar render, the splash create/dismiss
wiring) are covered by host-native pytest; this test covers the end-to-end native +
visual result.

## Preconditions

- The installed Windows app at the **F7 build** (Concourse `windows-installer`, branch
  `flight/07`) is installed and launchable; 8484 free so it starts its own window.
- A way to read the **Windows taskbar / process** (visual + `tasklist`) and the data-dir
  crash log (`%LOCALAPPDATA%\the-one\logs\the-one-app.log`) for any failure.
- Operator-relayed observation (or screenshots) — this is an operator-driven Witnessed run.

## Observables Required

- gui (frameless window + themed titlebar render; window min/max/restore/hide; titlebar
  drag-move; edge-resize; splash appear/dismiss; taskbar icon — operator visual / screenshot)
- process (the-one-app.exe present/absent — `tasklist`)
- http (`/api/info` 200 vs refused — curl, to confirm hide-vs-quit)
- filesystem (crash log if a step fails — Read)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Launch the app from the Start menu. Watch the launch closely. | A **splash** (brand logo) appears while the app boots, then **dismisses** when the main UI loads. The main window opens **frameless** — no OS title bar — with a **themed custom titlebar** at the top (app name + window controls). |
| 2 | Inspect the **taskbar** icon for the running app. | The taskbar shows the **GleepGlorp brand icon**, not the generic PyInstaller/Python icon. |
| 3 | Click the custom **minimize** button in the titlebar. | The window **minimizes** to the taskbar. Click the taskbar entry → it restores. |
| 4 | Click the custom **maximize/restore** button. | The window **maximizes** to fill the work area; clicking again **restores** to the prior size. |
| 5 | **Drag the titlebar** (not a button) to move the window. Then click an existing **topbar nav button** and a **window-control button**. | The window **moves** with the drag. `[a11y]` the drag region must NOT swallow clicks — both the existing `#app-topbar` nav buttons AND the window controls still fire (they carry `no-drag`). |
| 6 | **Drag a window edge/corner** to resize. | The window **resizes** (or, if resize was scoped out per the DD3 spike, document the agreed behavior — maximize/restore only — and confirm it matches that decision). |
| 7 | Click the custom **close** button. Then `tasklist` + GET `/api/info`. | The window **hides to the tray** (F6 close-to-tray preserved — the custom close routes to the same path): tray icon remains, process still listed, `/api/info` still 200. (Not a quit.) |
| 8 | Restore from the tray; then **Quit** from the tray menu. | Window restores; Quit exits cleanly (tray gone, `/api/info` refused) — F6 teardown unchanged under the new chrome. |
| 9 | Open `http://localhost:8484/` in a **plain browser** (with the app running, or a fresh `serve`). | The browser page does **NOT** show the custom window-control buttons (they render only inside the native window via `window.pywebview` detection) — the OS/browser frame applies there. |
| 10 | *(regression)* Re-confirm a couple of F6 behaviors under the new chrome: move/resize → Quit → relaunch restores geometry; theme persists. | Geometry restored, theme persists — the chrome refactor didn't regress F6. |

## Out of Scope

- Tray / background-run / single-instance / window-state **logic** — covered by F6's
  `windows-desktop-presence` + host-native pytest; this test only re-confirms they still
  work under the new chrome (step 8, 10).
- The `js_api` / titlebar-render / splash-wiring **unit contracts** — host-native pytest.
- macOS / Linux chrome — the follow-up port mission.

## Variants (optional)

- **Per-monitor DPI**: if the operator has a multi-monitor / mixed-DPI setup, repeat
  steps 3–6 with the window dragged to a different-scaling monitor (chrome/splash sizing
  is a known DPI risk area on Windows).
