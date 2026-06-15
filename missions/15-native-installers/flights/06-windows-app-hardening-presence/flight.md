# Flight: Windows Native App Hardening — Desktop Presence & Lifecycle

**Status**: in-flight
**Mission**: [Native Desktop Installers](../../mission.md)

## Contributing to Criteria

- [ ] *(Re-scope addition, 2026-06-15)* The installed Windows app behaves like a
      polished, always-on desktop app — system-tray presence with background-run
      (close-to-tray, quit from the tray menu), persisted window state, and
      single-instance focus (a relaunch raises the running window). *(HAT + Witnessed
      GUI behavior-test backed)*
- [ ] Launching the installed app opens the agent UI in a **native application
      window** — extended here so a *second* launch focuses the running window rather
      than opening a duplicate.
- [ ] The installed app **preserves user state across app restarts** — extended here
      to window geometry (and re-confirming the F5 web-storage/theme persistence under
      the new shell).

> Splash screen, custom window chrome, and icon/branding polish are the sibling
> **Flight 7** (visual polish). This flight is the presence/lifecycle half.

---

## Pre-Flight

### Objective

Make the installed Windows app behave like a real, always-on desktop application by
introducing a **single composable desktop-shell module** (`the_one/interfaces/
desktop/`) that the `the-one app` entry point delegates to. The module composes the
F4 native window (pywebview) with: a **system-tray icon + background-run** model
(closing the window hides it to the tray and the app keeps serving; Quit lives in the
tray menu; a first-run notice explains the background behavior), **single-instance
focus** (a second launch raises the already-running window via a new
`/api/window/focus` endpoint and exits, instead of opening a duplicate), and
**window-state persistence** (size/position restored across restarts, clamped to
visible monitor bounds). The module is written cross-platform-clean (pywebview +
pystray, both cross-platform; OS quirks isolated as small functions) so the follow-up
macOS/Linux mission ports it rather than reworking it.

### Open Questions

- [x] Per-OS backend split vs. single module? → **Single composable module** (DD1).
- [x] Tray library? → **pystray** on a detached thread, pywebview on the main thread (DD2).
- [x] Close-button semantics? → **Close-to-tray** (background-run); Quit from the
      tray menu; first-run notification (DD3).
- [x] Single-instance focus mechanism? → **`/api/window/focus`** routed through the
      in-process server, Origin-allowlist-cleared (DD4).
- [x] Window-state storage? → **JSON under `settings.data_dir`**, clamped to visible
      bounds on restore (DD5).
- [x] Verification of the native GUI surface? → pytest for the logic seams +
      **operator HAT** + a **Witnessed GUI behavior test** (DD6).
- [x] Will `/api/window/focus` clear the Origin allowlist? → **Yes, verified**
      (`middleware.py:80-84,128-147`): a header-less loopback POST passes as-is; the
      focus client omits `Origin`. No exemption needed; Leg 3 confirms (DD4).
- [x] Does pywebview 5 expose live move/resize events? → `resized` yes, `moved`
      unreliable across 5.x → **close-only geometry capture is the baseline**, live
      hooks a stretch goal (DD5).
- [ ] Does pystray's window-message pump coexist with pywebview's EdgeChromium
      (WinForms) loop on the same process without a foreground-thread conflict? →
      **Resolve in Leg 2's spike** before building the full tray feature (named risk).

### Design Decisions

**DD1 — Single composable desktop module (not a per-OS backend split).**
- Choice: introduce `the_one/interfaces/desktop/` as one cross-platform package
  (`shell.py` composition + small `tray.py`, `window_state.py`, `focus.py` helpers).
  `interfaces/app.py`'s `run()` becomes a thin delegate to `desktop.run_desktop()`;
  the F4 window/port/availability/shutdown logic migrates in (or is imported by) the
  module. No `Protocol` + `WindowsDesktopShell` class + `sys.platform` factory.
- Rationale: F4's debrief established that **pywebview *is* the cross-platform
  window abstraction** and a per-OS launcher split "adds structure without clarity."
  pystray is *also* cross-platform. A per-OS-class seam would therefore abstract over
  libraries that already abstract over the OS — the over-split F4 warned against. The
  operator chose this explicitly (2026-06-15). "Abstract now, port later" is honored
  by keeping the module cross-platform-clean (OS quirks isolated as named functions
  with a clear seam), not by a class hierarchy.
- Trade-off: the follow-up mission ports by *touching this module* (adding small
  OS-quirk branches) rather than by *implementing a new backend class*. Accepted —
  the quirks (macOS NSStatusItem main-thread requirement, Linux AppIndicator
  availability) are genuinely small and localized.

**DD2 — Tray = pystray on a detached thread; pywebview owns the main thread.**
- Choice: add `pystray` (+ `Pillow`, which builds the tray icon from an existing
  brand PNG) to the `[gui]` extra. pywebview keeps the main thread (`webview.start()`
  blocks there, as today); the pystray `Icon` runs via `run_detached()` / a daemon
  thread.
- Rationale: pywebview requires the main thread for its GUI loop (hard requirement on
  macOS, conventional on Windows). pystray supports detached operation. Both can't own
  the main thread, so the tray yields.
- Trade-off: cross-thread calls from tray-menu callbacks into the pywebview window
  (show/hide/destroy) must be marshalled safely (pywebview's window methods are
  thread-safe wrappers; verified in Leg 2). Named as the lead risk → Leg 2 spike.

**DD3 — Close-to-tray with background-run; Quit from the tray menu; first-run notice.**
- Choice: intercept the window-close event so the X **hides the window** (app keeps
  serving) instead of destroying it. The first time this happens, show a one-time
  notification ("GleepGlorp AI is still running in the system tray — Quit from the
  tray menu to exit"); persist a "notice shown" flag so it appears once. Quit (tray
  menu) is the real exit: it tears down the tray, closes the window, and drives the
  F4 graceful server drain.
- Rationale: matches the operator's selection and standard always-on desktop-app UX
  (Slack/Discord). The first-run notice mitigates the "I closed it but it's still
  running" confusion.
- Trade-off: a background process persists after window close — intended, but it must
  be genuinely killable (Quit is the only documented exit; Task Manager remains the
  escape hatch). The notice + tray menu make the state discoverable.

**DD4 — Single-instance focus via `/api/window/focus`; header-less loopback POST.**
- Choice: add `POST /api/window/focus` to the in-process web app; its handler raises
  and restores the pywebview window via pywebview's **thread-safe** `show()`/`restore()`
  wrappers (the window object is reachable as a module-level reference since the server
  runs in-process — **verified**: `app.run()` starts uvicorn in a thread in the *same*
  process as `webview.start()`, `app.py:112-142`). In `run_desktop()`, when
  `_select_port` returns `is_ours=True`, the second process POSTs focus to the running
  instance and **exits** instead of opening a second window (closing F4's
  duplicate-window gap). The focus client (httpx/socket) sends **no `Origin` header**.
- Rationale: reuses infrastructure that already exists — the localhost server and
  `_select_port`'s `is_ours` detection — instead of an OS-level IPC/named-mutex layer.
  **Origin-allowlist reality (verified, `middleware.py:80-84,128-147`):** the
  middleware rejects a gated POST only when an `Origin` header is present AND not
  allow-listed; a header-less request passes, and loopback origins
  (`127.0.0.1:*`/`localhost:*`/`[::1]:*`) are already wildcard-allowed by
  `build_default_allowlist`. So a header-less loopback POST passes **as-is — no
  exemption, no allowlist change**. Leg 3 *confirms* (asserts the focus client sends no
  `Origin` and the POST is accepted); it does not investigate.
- Trade-off: focus depends on the server being up; if the first instance is mid-startup
  (server not yet answering), the second falls back to F4's existing port logic
  (`is_ours` only returns true once `/api/info` confirms our version). Acceptable —
  the startup-retry window is already handled by `_select_port`. Note: both this
  handler and the tray callbacks (DD2) call into pywebview's GUI thread from another
  thread — standardize on pywebview's thread-safe window wrappers for both; the Leg-2
  spike establishes the one marshalling story that Leg 3 reuses.

**DD5 — Window-state persisted to JSON under `data_dir`, clamped to visible bounds.**
- Choice: persist window size + position (and maximized flag) to
  `settings.data_dir / "window-state.json"`, read on launch and **captured on window
  close as the planned path**. On restore, clamp the rectangle to the current
  virtual-screen bounds so a window saved on a now-absent monitor doesn't open
  off-screen. Live save-on-move/resize is a **stretch goal**, not the baseline.
- Rationale: `data_dir` (platformdirs) is the established per-user store (survives
  restart and reinstall, migrates with the rest of the user's data, same pattern as
  the F5 webview profile). JSON keeps it inspectable and dependency-free.
- Trade-off: pywebview 5 exposes `closing`/`closed` and `resized` reliably, but a
  dedicated `moved` event is **not** dependable across 5.x backends (EdgeChromium/
  WinForms). So **close-only capture is the baseline** (covers the common "remember my
  last window" case); upgrade to live capture opportunistically only if a usable hook
  exists on the frozen build. Corrupt/missing file → ignore and use defaults (no crash).

**DD6 — Validation: pytest for the logic seams + operator HAT + Witnessed GUI behavior test.**
- Choice: the native GUI surface (tray, close-to-tray, window raise, geometry
  restore) has **no CI apparatus** — only a human on Windows can both *drive* it
  (click the tray, close the window, relaunch) and *observe* it (is the icon in the
  tray? did the window raise? did geometry restore?); chrome-devtools/Playwright
  cannot see native tray or chrome. So: (a) **pytest** covers the deterministic seams
  — the `/api/window/focus` handler (window mocked), the `is_ours → focus-and-exit`
  branch, window-state serialization + bounds-clamp + corrupt-file handling, and
  module wiring/delegation; (b) an **operator HAT** drives the real Windows app; (c) a
  **Witnessed GUI behavior-test** spec (`tests/behavior/windows-desktop-presence.md`)
  is authored now and run in the HAT leg — it folds in the owed F4/F5
  theme-persists-across-restart check.
- Rationale: mirrors F4/F5 — light, honest verification of an un-CI-able render/native
  surface, with the logic underneath fully unit-tested. The apparatus audit (act +
  observe) confirms the human-on-Windows apparatus is the only one that satisfies both
  axes for the tray/window behaviors.
- Trade-off: the GUI behaviors are not regression-gated in CI; they rely on the
  operator HAT per release until the next mission's MCP/GUI apparatus exists. Bounded —
  the project-owned logic is unit-tested; only the pywebview/pystray-owned render/native
  glue is HAT-only.

**DD7 — `pystray` + `Pillow` enter the `[gui]` extra and the freeze recipe.**
- Choice: add `pystray>=0.19` and `Pillow>=10` to the `[gui]` optional-dependency
  group (**today `[gui]` has only pywebview, and `Pillow` is only in the `dev` extra —
  both are genuinely new `[gui]` inputs**). Update `packaging/windows/the-one.spec`
  with an **explicit collection contract** (the per-package `collect_*` pattern will
  NOT auto-cover new packages): `collect_submodules("pystray")` **plus a
  `pystray._win32` hidden import** (pystray selects its Windows backend dynamically),
  `collect_submodules("PIL")` (or the maintained PyInstaller PIL hook) **plus the
  `_imaging` C-extension binary**, and the **tray icon PNG added to `datas`** (bundling
  the asset is a separate failure mode from importing the libs). Verify the frozen
  artifact still launches (Leg 5 packaged-smoke).
- Rationale: consistent with F4's DD1 (`[gui]` extra, not base deps) — these are GUI
  components with native surface. New freeze inputs can break the bundle (pystray
  backend selection, Pillow plugins), so the `.spec` impact is verified on the
  `windows-2022` runner before the operator HAT.
- Trade-off: a heavier `[gui]` install + freeze; negligible vs. pywebview/the LLM
  extras already present.

### Prerequisites

- [ ] F4 native window (`the-one app`) landed — **met** (F4 completed 2026-06-14).
- [ ] F5 freeze runtime seam + Windows installer landed — **met** (F5 completed,
      v0.2.1); the `windows-2022` packaged-smoke harness exists and is green.
- [x] `OriginAllowlistMiddleware` behavior for a loopback/non-browser POST — **known**
      (`middleware.py:80-84,128-147`): a header-less request passes; loopback origins
      are wildcard-allowed. A header-less loopback focus POST needs no exemption. Leg 3
      confirms the client sends no `Origin` and the POST is accepted.
- [ ] pystray ⇄ pywebview main-thread coexistence on Windows — **verify at Leg 2
      spike** before building the full tray feature.
- [ ] Operator HAT apparatus: a native Windows host able to install/run the frozen
      app and observe the tray/window — **the operator has one** (the F4/F5 HAT box).

### Pre-Flight Checklist

- [x] All open questions resolved (the remaining one is an execution-time Leg-2
      spike — pystray⇄pywebview coexistence — scoped + named, not a planning blocker)
- [x] Design decisions documented
- [x] Prerequisites verified (Phase-5b Architect review, 2026-06-15)
- [x] Validation approach defined (pytest + HAT + behavior test)
- [x] Legs defined

---

## In-Flight

### Technical Approach

`the_one/interfaces/desktop/` is introduced as a cross-platform package. `app.run()`
(the `the-one app` entry) becomes a thin delegate to `desktop.run_desktop()`. The
F4 launcher logic (`_select_port`, `_webview_available`, `_wait_until_serving`,
`_graceful_shutdown`, the in-process uvicorn server) migrates into / is reused by the
module so there is one home for the windowed-launch lifecycle.

Composition order inside `run_desktop()`:
1. Port-select (`_select_port`). If `is_ours` → POST `/api/window/focus` to the
   running instance and **exit** (single-instance focus, DD4).
2. Otherwise start the in-process uvicorn server (as F4), wait for readiness.
3. Build the pywebview window (geometry from `window-state.json`, clamped — DD5).
4. Start the pystray tray icon on a detached thread (icon from a brand PNG via
   Pillow; menu: Show, Quit — DD2).
5. Wire the close event to hide-to-tray + first-run notice (DD3); wire geometry-save
   hooks; wire Quit to tray-teardown + window-close + server drain.
6. `webview.start()` on the main thread (blocks until real Quit).

The new `/api/window/focus` endpoint lives beside `/api/info` in
`interfaces/web/app.py`; it raises/restores the module-level window reference and must
clear the Origin allowlist (DD4).

### Checkpoints

- [ ] `desktop/` package exists; `the-one app` delegates to it; `serve`/`chat`/
      `version` byte-identical; window still opens as in F4 (scaffold, no regression).
- [ ] Tray icon appears; Show/Quit work; closing the window hides to tray and the app
      keeps serving (`/api/info` still 200 after close); Quit drains and exits.
- [ ] A second `the-one app` while one runs raises the first window and exits (no
      duplicate); `/api/window/focus` clears the Origin allowlist.
- [ ] Window size/position restore across a restart; an off-screen saved rect clamps
      to visible bounds; corrupt/missing state file → defaults, no crash.
- [ ] The frozen Windows artifact (with pystray/Pillow) builds and launches green on
      the `windows-2022` runner (packaged-smoke).
- [ ] Operator HAT + the `windows-desktop-presence` Witnessed behavior test pass on
      the real Windows app.

### Adaptation Criteria

**Divert if**:
- The Leg-2 spike shows pystray and pywebview cannot coexist on one process/thread on
  Windows without a foreground-thread conflict → re-plan the tray approach (native
  `Shell_NotifyIcon` on pywebview's own loop, or a separate tray helper process)
  before building the full feature. Log the spike result regardless.
- (Backstop only — not expected to fire; the middleware already passes a header-less
  loopback POST.) If the focus POST somehow cannot be accepted without weakening the
  allowlist, switch the focus mechanism to a localhost-only token or an OS
  named-mutex/IPC rather than relaxing the middleware.

**Acceptable variations**:
- Geometry-save on close-only (vs. live resize/move hooks) if pywebview lacks the
  move/resize events.
- Tray icon sourced from any existing brand asset (`icon-192.png` /
  `gleepglorp_icon.png` / the `.ico`) — whichever renders cleanest at tray size.
- First-run notice via the tray balloon vs. a pywebview-native notification —
  whichever is reliable on the frozen build.

### Legs

> **Note:** Tentative; planned one at a time as the flight progresses.

- [x] `desktop-shell-scaffold` — create `the_one/interfaces/desktop/`; migrate the F4
      launcher composition into `run_desktop()`; `app.run()` delegates; add
      `pystray`/`Pillow` to the `[gui]` extra. No behavior change. Tests: delegation,
      module wiring, `serve`/`chat`/`version` unchanged.
- [x] `system-tray-and-background` *(lead risk — opens with the pystray⇄pywebview
      coexistence spike)* — tray icon on a detached thread; menu Show/Quit;
      close-to-tray (hide, keep serving) + one-time first-run notice; Quit →
      tray-teardown + window-close + server drain. Tests: close-intercept logic,
      first-run-flag persistence, Quit teardown ordering (window mocked).
- [x] `single-instance-focus` — `POST /api/window/focus` (raise/restore window,
      Origin-allowlist-cleared); `run_desktop()` `is_ours → focus-and-exit` branch.
      Tests: endpoint handler (window mocked), the focus-and-exit branch, Origin
      acceptance for a loopback POST.
- [x] `window-state-persistence` — load `window-state.json` under `data_dir` and apply
      geometry on window create with a visible-bounds clamp; **capture geometry on
      window close (baseline)**; add live move/resize capture only if a usable
      pywebview-5 hook exists on the frozen build (stretch). Tests: serialize/
      deserialize, clamp, corrupt/missing-file handling.
- [x] `freeze-integration` — update `packaging/windows/the-one.spec` per the DD7
      contract: `collect_submodules("pystray")` + a `pystray._win32` hidden import,
      `collect_submodules("PIL")` (or the PIL hook) + the `_imaging` binary, and the
      tray PNG in `datas`. Extend the `windows-2022` packaged-smoke so the frozen app
      launches under the new shell (tray import doesn't break the freeze; window still
      serves). **Update user-facing docs** (CLAUDE.md / README / agents.md: close-to-
      tray + Quit-to-exit, `/api/window/focus`, `window-state.json`) and reconcile the
      stale Leg-number reference in `the-one.spec`'s docstring. The frozen-artifact
      gate before the HAT.
- [ ] `hat-and-gui-behavior-test` *(optional, interactive)* — author is done in
      planning; run the `windows-desktop-presence` Witnessed behavior test +
      operator HAT on the real Windows app (tray, close-to-tray-keeps-serving,
      relaunch-focuses, geometry-restore, theme-persists). Fix inline; land with the
      run-log path recorded.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged (feature branch `flight/06-windows-app-hardening-presence`)
- [ ] Tests passing (host-native pytest + `windows-2022` packaged-smoke)
- [ ] Documentation updated (CLAUDE.md / README / agents.md: the tray/background-run
      behavior, the Quit-to-exit model, `/api/window/focus`, window-state file)

### Verification

- **CI / host-native**: the new pytest seams pass; `serve`/`chat`/`version`
  byte-identical; the `windows-2022` packaged-smoke builds + launches the frozen app
  with pystray/Pillow bundled.
- **Operator HAT + Witnessed behavior test** (`/behavior-test windows-desktop-presence`):
  on the real Windows app — tray icon present; closing the window hides to tray and
  `/api/info` still answers; relaunch focuses the running window (no duplicate); window
  geometry restores across a restart; theme persists across a restart; Quit exits
  cleanly. Run-log path recorded in the flight log.
