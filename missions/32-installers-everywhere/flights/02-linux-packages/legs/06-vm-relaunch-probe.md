# Leg: vm-relaunch-probe

**Status**: completed
**Flight**: [Linux packages](../flight.md)

## Objective
Before any hosted spend, run this flight's own packages (legs 1-5, 7 and 8) on the real Ubuntu 26.04 and Debian 13 GNOME guests. Answer the two divert risks that only a real session can answer:
1. A hidden window comes back and is raised on relaunch, with focus.
2. The software centres can upgrade and remove the `.deb` now that it ships AppStream metainfo.

Also confirm the behaviours leg 4 saw broken with Flight 1's packages: the first-launch window, the Debian AppImage's own window, and the tray "Show" item.

## Context
- **Flight DDs:** DD3 (tray detection), DD4 (no-tray hide, the notice, "Quit GleepGlorp AI", the activation token), DD5 (AppImage self-integration), DD9 (the apparatus, the premise table), DD12 (the show fix), DD13 (the takeover).
- **The apparatus (leg 4):** `packaging/linux/vm/` (`vm.sh up|down|ssh|session-env|copy-in|base-hash|status|prep`, `qmp.py`), the bases at `$HOME/the-one-m32-vm/`, the test user `tester`/`m32testpw`. The driving tips are in the flight log's `### vm-apparatus` section. Read them first: the welcome dialog, the overview to raise a window, scrolling with `qmp.py raw`, and checking that a double-click actually did something.
- **Leg 4's findings this leg re-checks** (with Flight 1's 0.11.8, which lacked this flight's fixes):

  | finding with Flight 1's package | expected now |
  |---|---|
  | first launch: no window, on both guests | the window shows (leg 3) |
  | tray "Show" did nothing (Ubuntu) | it shows the window (leg 3's `_show_window`) |
  | Debian AppImage opened in Firefox | own window (leg 1's fallback) |
  | Ubuntu App Center: no upgrade, no remove, not listed | unknown: the metainfo (leg 7) is the test |
  | Debian GNOME Software: upgrade and remove work, not listed | listed now? |

- **Tray hosts:** the Ubuntu guest has the AppIndicator extension enabled, so the tray mode should be `indicator`. The Debian guest has none, so the mode should be `none`.
- **GTK:** 3.24.52 (Ubuntu), 3.24.49 (Debian), from leg 4. Whether the `xdg_activation` token raises the window is checked here only through a real app-grid launch (`gio launch` gives no token).
- **Packages:** build a fresh pair from the working tree after legs 5 and 8 land: N=`0.11.9.dev10`, N+1=`0.11.9.dev11`, with `packaging/linux/build.sh --version …` and `M32_BUILD=$HOME/the-one-m32-build/f2`. Record their sha256s.

## Inputs
- Legs 1-5, 7 and 8 landed (uncommitted, in this worktree).
- The guests' base images and their hashes (leg 4).
- The packages above.

## Outputs
- Evidence under `$HOME/the-one-m32-evidence/f2/leg6/{ubuntu,debian}/`: screendumps of every step, SSH reads, the app API reads (`GET /api/window/state` with the guest's credential), and `doctor` output.
- The flight-log section `### vm-relaunch-probe`, with the answer table below.
- **No code changes,** unless a defect is found. A found defect is reported with evidence and `[BLOCKED:defect-<slug>]`, and the Flight Director decides whether to fix it inside this leg's scope (a new fix leg) or log a squawk. The Developer does not fix product code in this leg.

## Acceptance Criteria
Each row answered with evidence, on both guests unless marked. A fresh overlay per distro, plus a second fresh overlay for the AppImage rows.

- [ ] **R1 — install and first launch (`.deb`).**
  - Install N through the software centre by GUI (as leg 4's P1).
  - Launch it from the app grid.
  - The window shows on the **first** launch, with the Chats page ("Hello."). `GET /api/window/state` reads `visible: true, mapped: true`, and `tray` is `indicator` (Ubuntu) or `none` (Debian).
- [ ] **R2 — the menu entry.** The app grid shows "GleepGlorp AI" with the brand icon. A right-click shows "Quit GleepGlorp AI".
- [ ] **R3 — close, by the title-bar close button through QMP.**
  - **Ubuntu (tray):** the window hides, a tray icon is in the top bar, and the tray menu's Show brings the window back.
  - **Debian (no tray):**
    - the window hides and the process stays up (`visible: false`, `/api/live` 200);
    - a desktop notification appears with the no-tray text (screendump within 2 s of closing);
    - a second close shows no notification.
- [ ] **R4 — relaunch from the app grid while hidden.** The same process answers, and the window is shown **and raised** (focused, in front; not a "GleepGlorp AI is ready" notice). Record whether `XDG_ACTIVATION_TOKEN` reached the second launch (from the app's log line, if leg 5 logs a token prefix; otherwise `/proc/<pid>/environ` of the short-lived launcher, if catchable). **This is a divert criterion:** if the window cannot be brought back on either guest, emit `[BLOCKED:divert-relaunch]` with evidence.
- [ ] **R5 — quit.** Debian: right-click → "Quit GleepGlorp AI". Ubuntu: the tray's Quit; and, once relaunched, the right-click action too. Each time the process exits within 15 s, and `/api/live` stops answering.
- [ ] **R6 — upgrade while running (the takeover).**
  - Launch N, close it (hidden on Debian; in the tray on Ubuntu), install N+1 through the software centre, launch N+1 from the app grid.
  - N exits, N+1's window shows, and the version reads N+1.
  - Data seeded before the upgrade survives: an agent, a provider with a dummy key, and a chat (created through the API).
  - Record what the software centre offered: Update or Install, or nothing, as on Ubuntu with Flight 1's package.
  - **If Ubuntu's App Center still cannot install N+1 over N even with metainfo, record it and emit `[BLOCKED:divert-appcenter-upgrade]`.** The operator decides between documenting a terminal command and something else. Do the takeover itself by the closest allowed path (Debian's GUI, or Ubuntu with the operator's decision pending), so the takeover evidence still exists.
- [ ] **R7 — remove.** Remove the package through the software centre, and record whether it is now listed (Installed tab or search) because of the metainfo. The data dir survives. On Ubuntu, if App Center cannot remove it, that is part of R6's divert question.
- [ ] **R8 — AppImage** (a fresh overlay per guest):
  - make it executable in Files, then double-click it;
  - **its own window** shows on Debian (not Firefox) and on Ubuntu;
  - the app grid then shows "GleepGlorp AI (AppImage)" with the icon, either at once or after the next login (record which);
  - its right-click "Quit GleepGlorp AI" works;
  - deleting the AppImage file, then logging out and in, removes the entry (`TryExec`).
- [ ] **R9 — `doctor` in the session environment,** for both packages:
  - exit 0;
  - no "skipped" except window chrome;
  - the `sandbox:` line (record it, given leg 4's `bwrap` facts);
  - the `tray:` line matching R1.
- [ ] **R10 — hygiene:**
  - the base hashes are unchanged (`base-hash --check` on both);
  - only `m32-vm-*`/`m32-build-*` containers were used, and none is left running;
  - no root-owned files;
  - nothing on host 8484/8485;
  - the operator data dir is untouched.

## Verification Steps
- The evidence folders, and the answer table in the flight log.

## Implementation Guidance
1. Confirm in the flight log that legs 5 and 8 have landed, then build N and N+1.
2. Ubuntu first: R1-R7 in one overlay; then a new overlay for R8; R9 throughout. Then Debian the same way.
3. Prefer keyboard paths for the GNOME shell. Use QMP clicks for the title-bar close button and dialogs.
4. Keep every screendump. Name them `<row>-<step>.png`.

## Edge Cases
- **The first App Center launch may refresh snaps:** wait for `snap changes` to settle, as leg 4 did.
- **GNOME may show "<app> is ready" instead of raising** (focus-stealing prevention). That is exactly R4's question. Record it precisely, with screendumps before and after.
- **The tray icon on Ubuntu** may take a few seconds to appear. Poll the screen.
- **A notification may be swallowed by Do Not Disturb or the lock screen:** neither is on in these bases. If none appears, check `gdbus`/`journalctl --user` for the `Notify` call before calling it missing.

## Files Affected
- `missions/32-installers-everywhere/flights/02-linux-packages/flight-log.md` (own section only)

## Citation Audit
Checked against the flight log after legs 1-5, 7 and 8 (uncommitted):
- leg 4's apparatus verbs and driving tips (`### vm-apparatus`);
- leg 4's P-table and GTK versions;
- leg 7's AppImage integration paths;
- leg 5 phase A's close states and `the-one quit`.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
