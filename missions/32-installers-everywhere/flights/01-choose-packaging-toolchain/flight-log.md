# Flight Log: Choose the packaging toolchain

**Flight**: [Choose the packaging toolchain](flight.md)

## Summary
Planned 2026-10-23 in the worktree `/home/cprch/projects/the-one-worktrees/m32-installers`, from `origin/main` at `8a52a39` plus the mission commit `b060d84`. Mission 31 is active in the main checkout at the same time; this flight never touches it.

---

## Planning Notes

- **Operator decisions, 2026-10-23:**
  - macOS budget: at most 2 macOS jobs this flight;
  - the winner's spike recipe is kept as Flight 2's starting point, and the loser is removed;
  - the Windows comparison is tested for real if Briefcase survives Linux;
  - the Windows installer is built on GitHub, and the operator downloads it and runs it over their own install (Windows 11 Home: no Windows Sandbox or Hyper-V);
  - a guided decision session (HAT) closes the flight.
- **Planning checks:**
  - the target-distro containers resolve;
  - WSLg and the host WebKitGTK 4.1 are present;
  - an offline `uv.lock` audit found no macOS arm64 wheel gaps that matter (see the flight's Citation Audit).
- **Carried from the Mission 15 Flight 5 debrief:**
  - the packaged smoke proves spawn behaviour, never the rendered window, so the window is looked at directly (the Linux legs and `decision-hat`);
  - first-time freeze recipes carry 2 to 4 CI-only issues, which is why the macOS run is rehearsed on Linux first and capped;
  - Actions artifact storage hit its quota in Mission 15, so there is a draft-release fallback;
  - every `webview.start()` call needs its `private_mode`/`storage_path` decision, which matters for the upgrade check;
  - `_common_runtime_dirs()` lacks NVM/fnm node paths on macOS (a paper item for Flight 3).
- **Design review, cycle 1 (Architect): approve with changes.** Folded in:
  - workflows must exist on `main` to be dispatched. The operator chose a small `.github/`-only PR to `main` (DD6);
  - the pystray backend is pinned, and tray visibility is not scored in WSLg or containers (DD2, DD5);
  - gate 3 now asserts a single host GTK/WebKit stack through `/proc/<pid>/maps`, and A owes an exclude list;
  - Briefcase builds a `.deb` per distro through Docker targets (DD1);
  - gates 1 and 2 are strict and measured independently, because the not-frozen path downgrades or short-circuits them under Briefcase;
  - one stock-desktop container baseline for both candidates;
  - a staged `__version__` rewrite for the N to N+1 upgrade;
  - gate 4 is measured only in containers;
  - elimination and hybrids are per platform and format;
  - per-leg re-verification of external sessions;
  - `macos-15` is pinned;
  - leg 1 is split into one leg per candidate (five legs);
  - three citation corrections.
- **Design review, cycle 2 (Architect): approve with changes.** Folded in:
  - DD4 patches are kept as staging-time diff files, so the hosted jobs run with them;
  - gate 1 rejects any `skipped` detail (the not-frozen downgrades read `skipped (…)`), and is run with and without `PYSTRAY_BACKEND`;
  - gate 3's web-process check is "at most one copy, all host";
  - B's PyGObject comes from the pinned closure, compiled in its Docker build;
  - A is frozen with Python 3.11, and B's distro Pythons are recorded;
  - a format that fails a hard gate stops there;
  - small wording fixes.

  This was the last design review cycle.
- **Finding for Flight 2 (operator: no separate squawk):** with the Ayatana AppIndicator typelib missing, `import pystray` raises `ValueError`, which `pystray.backend()` does not catch (it falls through only on `ImportError`). So the tray never starts on a stock Debian GNOME source install, and in a frozen build the desktop-shell `doctor` gate fails.

---

## Leg Progress

_(none yet)_

---

## Decision

_(recorded at `decision-hat`)_
