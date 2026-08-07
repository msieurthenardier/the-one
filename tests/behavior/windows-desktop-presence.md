# Behavior Test: Windows Desktop Presence & Lifecycle

**Slug**: `windows-desktop-presence`
**Status**: active
**Created**: 2026-06-15
**Last Run**: 2026-06-15-18-00-00 (pass — operator-driven HAT, F6 Leg 6)

## Intent

Verify that the installed **Windows** app behaves like a real always-on desktop
application — the Flight 6 hardening surface that has **no CI apparatus**. The native
tray icon, hide-to-tray-on-close, window raise/focus, and geometry restore can only be
*driven* (click the tray, close the window, relaunch) and *observed* (is the icon in
the tray? did the window come forward? did size/position return?) by a **human on a
real Windows host** — chrome-devtools/Playwright cannot see the native tray or window
chrome, and CI has no rendered-window apparatus (F4/F5 DD6). The deterministic seams
underneath (the `/api/window/focus` handler, the `is_ours → focus-and-exit` branch,
window-state serialization + bounds-clamp) are covered hermetically by pytest; this
test covers the **end-to-end native behavior on real hardware**, which is where a
pywebview/pystray regression would actually bite.

It also folds in the **owed F4/F5 theme-persists-across-restart check** (the F5 fix for
`private_mode=True` dropping `localStorage`): only a frozen, installed, relaunched
binary exposes ephemeral-profile behavior, so the theme step belongs here.

This is a **functional/UX** test (presence, lifecycle, persistence), NOT a containment
or security test.

## Preconditions

- The **installed Windows app** (the F5 Inno installer, at the Flight-6 build with the
  desktop-shell module) is installed on a **real Windows host** (Windows 10 1809+) and
  launchable from the Start menu / `the-one app`. The operator confirms how the
  Executor drives the app and reads the screen (operator-relayed observation or
  screenshots).
- A way to read the **Windows process table** is available — `tasklist` (e.g.
  `tasklist /FI "IMAGENAME eq the-one-app.exe"`) or Task Manager — to confirm the
  background process lives after close and is gone after Quit.
- A way to issue an **HTTP GET to `http://127.0.0.1:8484/api/info`** from the host
  (browser, `curl`, or the bundled `httpx`) to confirm the server is/ isn't serving.
- The per-user data dir is known (platformdirs `user_data_dir("the-one")`) so the
  operator can read/edit `window-state.json` for the geometry + clamp rows.
- **Credential**: this build is gated (Mission 20 Flight 1). The `api-credential` file
  lives alongside `window-state.json` in that same per-user data dir — read it and attach
  `Authorization: Bearer <credential>` to the `/api/info` GETs in steps 2, 5, and 8, per
  CLAUDE.md's "Behavior-test credential convention". The app's **own window** (its
  embedded webview) authenticates itself internally via the desktop launcher's in-process
  handoff — that path needs nothing from the Executor/operator. **Safety note**: this spec
  intentionally targets the installed app's default port 8484, unlike a Linux dev-instance
  spec — it is testing the packaged installer's real default behavior on a **dedicated
  Windows test host**, not the operator's own daily-driver machine; never run it against an
  operator's personal Windows install.
- Fresh-state option for the first-run-notice row: if a prior run already set the
  "close notice shown" flag, the operator can clear it (delete the flag file / key)
  to re-observe the one-time notice — otherwise that sub-assertion is skipped.

## Observables Required

- gui (tray icon presence, window visible/hidden, window raised/focused, the one-time
  close notice — measured by operator visual observation / screenshot)
- http (`/api/info` 200 vs. connection-refused — measured via curl/httpx)
- process (the-one background process present/absent — measured via `tasklist`)
- filesystem (`window-state.json` contents — measured via Read/`type`)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Launch the installed app from the Start menu (or `the-one app`). Wait for the window. | The native window opens showing the agent UI. A **system-tray icon** appears in the notification area. |
| 2 | GET `http://127.0.0.1:8484/api/info`. | HTTP 200 with a JSON body whose `version` matches the installed build — the in-process server is serving. |
| 3 | In the UI, change the **theme** to a non-default value (e.g. toggle dark/light). Note the chosen value. | The theme visibly changes. (Setup for the persistence check in step 9.) |
| 4 | *(If the one-time close-notice flag was cleared in preconditions)* Click the window's **close (X)** button. | The window **disappears** but the app does **not** exit: the **tray icon remains**, and a one-time notification appears explaining the app is still running in the tray and to Quit from the tray menu. `[mixed-frame]` (the notice is transient; operator confirms it appeared). |
| 5 | GET `/api/info` again, and run `tasklist /FI "IMAGENAME eq the-one-app.exe"`. | `/api/info` still returns **200**, and the the-one process is **still listed** — close-to-tray kept the app serving in the background. |
| 6 | Left-click the tray icon (or tray menu → **Show**). | The window **reappears** with the agent UI (same session, server never restarted). |
| 7 | With the app running, launch a **second** instance (Start menu / `the-one app` again). Wait ~3 s for the second process to exit, then run `tasklist` for `the-one-app.exe`. | **No duplicate window** opens; the already-running window is **raised/focused** to the foreground. After the settle, `tasklist` shows **one** long-lived `the-one-app.exe` GUI instance — the second process focused the first and exited (single-instance focus via `/api/window/focus`). `[mixed-frame]` (a transient 2nd PID may appear before it exits; the post-settle re-check is the assertion). |
| 8 | **Move and resize** the window to a clearly distinct position + size (e.g. drag to a corner, shrink it). Then **Quit** from the tray menu. Run `tasklist`; GET `/api/info`. | The window closes, the **tray icon disappears**, the the-one process is **gone** from `tasklist`, and `/api/info` now **refuses the connection** — Quit is the real exit with a clean shutdown. |
| 9 | **Relaunch** the app. Observe the window geometry and the theme. Then read `window-state.json` in the data dir. | The window **reopens at the size + position from step 8** (geometry restored), and the **theme from step 3 persists** (web storage survived the restart — the F5 `private_mode=False` fix). `window-state.json` contains the saved width/height/x/y. |
| 10 | *(Off-screen clamp)* Quit. Edit `window-state.json` to an **off-screen** position (e.g. x/y far beyond the virtual desktop bounds). Relaunch. | The window appears **fully on-screen** (the saved rect was clamped to visible monitor bounds) — not lost off the edge of the desktop. |
| 11 | Clean up: restore a sane `window-state.json` (or delete it to reset to defaults) if the operator wants a clean slate. | (setup row, no judgment) |

## Out of Scope

- **Splash screen, custom window chrome, icon/branding polish** — Flight 7 (visual
  polish); a sibling spec covers those if behavior-test-backed.
- **The deterministic logic seams** — `/api/window/focus` handler, the
  `is_ours → focus-and-exit` branch, window-state serialize/clamp/corrupt-file
  handling — covered hermetically by pytest (`windows-2022` CI + host-native).
- **Containment / sandboxing** — Windows ships passthrough (mission DD9); this test is
  functional/UX only.
- **macOS / Linux desktop presence** — the follow-up mission, when the desktop-shell
  module is ported.

## Variants (optional)

- **Reinstall-survival**: after step 9, uninstall + reinstall the app (same version),
  relaunch, and confirm the theme + window geometry still restore (data dir is outside
  the install dir — F5 reinstall-survival, re-confirmed under the new shell).
