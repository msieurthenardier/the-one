# Leg: linux-hat

**Status**: in-flight
**Flight**: [Linux packages](../flight.md)

## Objective
The operator sees both Linux packages working on real desktops and aligns on the open findings. The Flight Director guides one step at a time on the fresh-VM guests, shown on the operator's screen through WSLg. This is a HAT leg (interactive; no autonomous Developer), per DD10.

## Context
- **Everything below is already proven by automation:**
  - legs 1-12;
  - the `linux-package-install` behavior test, 44/44 PASS (`tests/behavior/linux-package-install/runs/2026-10-24-20-34-28.md`);
  - the hosted run `40127933969`, green.

  The walk is for the operator's eyes and decisions, not re-verification.
- **Apparatus:**
  - `packaging/linux/vm/vm.sh up <distro> --visible` opens the guest in a QEMU window on the operator's desktop (WSLg).
  - The test user is `tester` / `m32testpw`.
  - Packages `0.11.9.dev20`/`dev21` are in `$HOME/the-one-m32-build/f2/packages/`, copied into the guest's `~/Downloads` by the Flight Director before each walk.
  - One guest at a time; fresh overlays.
- **Findings to align on** (flight log, `fresh-vm-checks (part B)`):
  1. Ubuntu's tray-mode notice is cut off in GNOME's banner.
  2. AppImage tile labels are truncated in the app grid.
  3. On the first launch of the Ubuntu AppImage, the window body was empty for about 20 s.
  4. A green "1" badge appeared on the Ubuntu `.deb` tile.
  5. Debian's window has a close-only title bar.
  6. App Center shows a generic icon and "Unknown publisher" for a local `.deb` (known limit).

## Steps (presented one at a time; each waits for the operator)
1. **Ubuntu, the `.deb`.** The Flight Director starts the visible Ubuntu guest with the packages in `~/Downloads`. The operator double-clicks the N `.deb` in Files, installs it through App Center (password `m32testpw`), and launches GleepGlorp AI from the app grid. The operator looks at: the window, the tray icon, and App Center's page.
2. **Ubuntu, close and tray.** Close the window. The operator watches the tray banner (finding 1), then uses the tray's Show and the tray's Quit.
3. **Debian, the AppImage.** The Flight Director starts the visible Debian guest. The operator makes the N AppImage executable (Files → Properties), double-clicks it, and checks that its own window opens and that "GleepGlorp AI (AppImage)" appears in the app grid.
4. **Debian, no tray.** Close the window. The operator reads the one-time notice, launches it again from the grid, then right-clicks the icon → "Quit GleepGlorp AI".
5. **The guide.** The operator skims `docs/linux-install.md`, especially the Ubuntu `apt` upgrade and removal lines and the AppImage-first advice.
6. **Decisions.** The operator decides, for each finding 1-5, whether to fix it now (a look-and-feel FIX rides the inline protocol; anything that adds behaviour goes through the fix-vs-feature gate), log it as a squawk, or accept it. The decisions are logged in their words.

## Acceptance Criteria
- [ ] The operator has walked steps 1-5, or chosen to skip some, and their remarks are logged.
- [ ] Each finding has a recorded disposition (fixed, squawk id, or accepted).
- [ ] Any inline fix is committed, with its unit tests passing, and re-shown to the operator if visual.
- [ ] No `m32-vm-*` container is left running, and the base hashes are verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
