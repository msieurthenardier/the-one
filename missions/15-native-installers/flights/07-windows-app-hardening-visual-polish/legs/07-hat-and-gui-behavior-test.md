# Leg: hat-and-gui-behavior-test

**Status**: in-flight
**Flight**: [Windows Native App Hardening — Visual Polish](../flight.md)

## Objective

Operator HAT on the real installed Windows app + the `windows-desktop-chrome` Witnessed
behavior test — verify the F7 visual polish (frameless titlebar, window controls, splash,
brand taskbar icon) and confirm no F6 regression, on apparatus that has no CI proxy (DD6).

## Context

- **Interactive leg** (skill: HAT legs are operator-driven, not autonomous). The Flight
  Director guides the operator through the spec steps one at a time, fixes failures inline
  (new commit, no amend; re-verify the step), and lands only when all steps pass (or the
  operator accepts a failure as a known issue, recorded here + in the flight log).
- The step table is canonical in the behavior spec: `tests/behavior/windows-desktop-chrome.md`
  (10 steps + an optional multi-DPI variant).
- Verifies the HAT-deferred items from Legs 2/4/5: frameless edge-resize (DD3), native
  drag-move, min/max/close→tray, splash appear/dismiss/no-orphan, crisp brand taskbar icon,
  and the browser-mode "no fake controls" gate — plus F6 geometry/theme regression.

## Apparatus / Preconditions

- The **F7 installer** built by Concourse `windows-installer` build #18 (branch `flight/07`,
  succeeded) — published to MinIO. Installed on the operator's Windows box; port 8484 free.
- Operator visual observation / screenshots (Witnessed, operator-relayed).
- Crash log on failure: `%LOCALAPPDATA%\the-one\logs\the-one-app.log`.

## Acceptance Criteria (= the behavior-test steps; pass each)

- [ ] Step 1 — splash appears then dismisses; main window opens frameless with the themed titlebar
- [ ] Step 2 — taskbar shows the GleepGlorp brand icon (not generic)
- [ ] Step 3 — custom minimize works; taskbar restore works
- [ ] Step 4 — custom maximize/restore works
- [ ] Step 5 — titlebar drag moves the window; nav buttons AND window controls still fire (no click-swallow)
- [ ] Step 6 — edge/corner resize works (or the DD3-agreed fallback is confirmed → decides Leg 3)
- [ ] Step 7 — custom close hides to tray (process alive, `/api/info` 200) — F6 close-to-tray preserved
- [ ] Step 8 — tray restore + Quit exits cleanly (`/api/info` refused) — F6 teardown intact
- [ ] Step 9 — plain browser shows NO custom window controls (pywebview-gated render)
- [ ] Step 10 — F6 regression: geometry restored on relaunch; theme persists

## Verification

Operator-driven Witnessed run. The Flight Director records a run log at
`tests/behavior/windows-desktop-chrome/runs/{ts}.md` with per-step verdicts + the operator's
observations, and links it from the flight log. A failing step blocks landing unless the
operator accepts it as a known issue (recorded with disposition).

---

## Post-Completion Checklist

**This is the final leg. On all-steps-pass:** record the run log; set this leg `completed`;
then the flight-completion sequence (Phase 2d/3): Leg 6 docs, statuses→`completed`,
flight→`landed`, mission check-off, revert the Concourse pipeline `repo` branch to `main`,
flight-completion commit + draft PR marked ready.

- [ ] All 10 behavior-test steps pass (or known-issue dispositions recorded)
- [ ] Run log written under `tests/behavior/windows-desktop-chrome/runs/`
- [ ] Flight log updated with the HAT outcome + run-log path
