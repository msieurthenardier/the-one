# Behavior Test: Windows Native Frame & Splash

**Slug**: `windows-native-frame-splash`
**Status**: active
**Created**: 2026-06-15
**Revised**: 2026-06-16 (PIVOT DD2-alt — native OS frame replaces frameless custom chrome)
**Last Run**: 2026-06-17-00-47-21 (pass — [run log](windows-native-frame-splash/runs/2026-06-17-00-47-21.md))

## Intent

Verify the F7 **visual polish** on the installed Windows app — a **native OS-framed window**
with the brand title ("GleepGlorp AI") and icon, a launch splash, working native
min/max/close via the OS title bar, native drag and edge-resize, close-to-tray preserved
on the native X, and a brand taskbar icon — none of which has a CI apparatus (DD6). Only a
human on a real Windows host can both *drive* (use the native title bar controls, drag the
window, drag edges to resize, watch the launch) and *observe* (the native window actually
minimizes / maximizes / hides-to-tray / moves / resizes; the splash appears then dismisses;
the taskbar shows the brand icon; it looks finished). The deterministic seams (splash
create/dismiss wiring, close-to-tray routing, window-state restore) are covered by
host-native pytest; this test covers the end-to-end native + visual result.

## Preconditions

- The installed Windows app at the **F7 build** (Concourse `windows-installer`, branch
  `flight/07`) is installed and launchable; 8484 free so it starts its own window.
- A way to read the **Windows taskbar / process** (visual + `tasklist`) and the data-dir
  crash log (`%LOCALAPPDATA%\the-one\logs\the-one-app.log`) for any failure.
- Operator-relayed observation (or screenshots) — this is an operator-driven Witnessed run.

## Observables Required

- gui (native-framed window + OS title bar with brand name and icon; window min/max/
  restore/hide via native controls; native titlebar drag-move; edge-resize; splash
  appear/dismiss; taskbar icon — operator visual / screenshot)
- process (the-one-app.exe present/absent — `tasklist`)
- http (`/api/info` 200 vs refused — curl, to confirm hide-vs-quit)
- filesystem (crash log if a step fails — Read)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Launch the app from the Start menu. Watch the launch closely. | A **splash** (brand logo + loading bar) appears while the app boots, then **dismisses** when the main UI loads. The main window opens with a **native OS title bar** showing "GleepGlorp AI" and the brand icon — no custom titlebar overlay. |
| 2 | Inspect the **taskbar** icon for the running app. | The taskbar shows the **GleepGlorp brand icon**, not the generic PyInstaller/Python icon. |
| 3 | Click the **native minimize** button (OS title bar). | The window **minimizes** to the taskbar. Click the taskbar entry → it restores. |
| 4 | Click the **native maximize/restore** button (OS title bar). | The window **maximizes** to fill the work area; clicking again **restores** to the prior size. |
| 5 | **Drag the native title bar** to move the window. | The window **moves** with the drag. The `#app-topbar` nav buttons and the app itself remain fully interactive (native frame, no drag-region interfering). |
| 6 | **Drag a window edge/corner** to resize. | The window **resizes** freely — native OS edge-resize works as expected (native frame provides this without custom grips). |
| 7 | Click the **native close** button (OS title bar X). Then `tasklist` + GET `/api/info`. | The window **hides to the tray** (F6 close-to-tray preserved — the native X fires `events.closing` → `_on_closing` → hide): tray icon remains, process still listed, `/api/info` still 200. (Not a quit.) |
| 8 | Restore from the tray; then **Quit** from the tray menu. | Window restores; Quit exits cleanly (tray gone, `/api/info` refused) — F6 teardown unchanged under the native frame. |
| 9 | Open `http://localhost:8484/` in a **plain browser** (with the app running, or a fresh `serve`). | The browser page renders normally with the banner image and nav buttons — no custom window-control buttons (they were Leg-2 only; the native frame needs none). The OS/browser frame applies there. |
| 10 | *(regression)* Re-confirm F6 behaviors under the native frame: move/resize → Quit → relaunch restores geometry; theme persists. | Geometry restored, theme persists — the revert to native frame didn't regress F6. |

## Out of Scope

- Tray / background-run / single-instance / window-state **logic** — covered by F6's
  `windows-desktop-presence` + host-native pytest; this test only re-confirms they still
  work under the native frame (steps 8, 10).
- The splash-wiring / close-to-tray **unit contracts** — host-native pytest.
- macOS / Linux — the follow-up port mission.

## Variants (optional)

- **Per-monitor DPI**: if the operator has a multi-monitor / mixed-DPI setup, repeat
  steps 5–6 with the window dragged to a different-scaling monitor (splash sizing is a
  known DPI risk area on Windows).
