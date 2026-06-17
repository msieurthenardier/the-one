# Leg: hat-and-gui-behavior-test

**Status**: completed
**Flight**: [Windows Native App Hardening — Visual Polish](../flight.md)

## Objective

Operator HAT on the real installed Windows app + the `windows-native-frame-splash` Witnessed
behavior test — verify the F7 visual polish (native OS frame + title, splash, brand taskbar
icon) and confirm no F6 regression, on apparatus that has no CI proxy (DD6).

## Context

- **Interactive leg** (skill: HAT legs are operator-driven, not autonomous). The Flight
  Director guides the operator through the spec steps one at a time, fixes failures inline
  (new commit, no amend; re-verify the step), and lands only when all steps pass (or the
  operator accepts a failure as a known issue, recorded here + in the flight log).
- The step table is canonical in the behavior spec: `tests/behavior/windows-native-frame-splash.md`
  (10 steps + an optional multi-DPI variant).
- Verifies the F7 items: native frame (OS title bar, drag/min/max/close/resize), close→tray
  via native X, splash appear/dismiss/no-orphan, crisp brand taskbar/title-bar icon,
  browser-mode unchanged — plus F6 geometry/theme regression. Frameless/js_api/drag-region
  items are moot (DD3 divert → DD2-alt).

## Apparatus / Preconditions

- The **F7 installer** built by Concourse `windows-installer` build #18 (branch `flight/07`,
  succeeded) — published to MinIO. Installed on the operator's Windows box; port 8484 free.
- Operator visual observation / screenshots (Witnessed, operator-relayed).
- Crash log on failure: `%LOCALAPPDATA%\the-one\logs\the-one-app.log`.

## Acceptance Criteria (= the behavior-test steps; pass each)

- [ ] Step 1 — splash appears then dismisses; main window opens with native OS title bar ("GleepGlorp AI")
- [ ] Step 2 — taskbar shows the GleepGlorp brand icon (not generic)
- [ ] Step 3 — native minimize works; taskbar restore works
- [ ] Step 4 — native maximize/restore works
- [ ] Step 5 — native titlebar drag moves the window; nav buttons still fire (no interference)
- [ ] Step 6 — native edge/corner resize works
- [ ] Step 7 — native close (X) hides to tray (process alive, `/api/info` 200) — F6 close-to-tray preserved
- [ ] Step 8 — tray restore + Quit exits cleanly (`/api/info` refused) — F6 teardown intact
- [ ] Step 9 — plain browser shows no custom window controls (no win-controls rendered; native frame only)
- [ ] Step 10 — F6 regression: geometry restored on relaunch; theme persists

## Verification

Operator-driven Witnessed run. The Flight Director records a run log at
`tests/behavior/windows-native-frame-splash/runs/{ts}.md` with per-step verdicts + the operator's
observations, and links it from the flight log. A failing step blocks landing unless the
operator accepts it as a known issue (recorded with disposition).

Spec path: `tests/behavior/windows-native-frame-splash.md`.

---

## Post-Completion Checklist

**This is the final leg. On all-steps-pass:** record the run log; set this leg `completed`;
then the flight-completion sequence (Phase 2d/3): Leg 6 docs, statuses→`completed`,
flight→`landed`, mission check-off, revert the Concourse pipeline `repo` branch to `main`,
flight-completion commit + draft PR marked ready.

- [ ] All 10 behavior-test steps pass (or known-issue dispositions recorded)
- [ ] Run log written under `tests/behavior/windows-native-frame-splash/runs/`
- [ ] Flight log updated with the HAT outcome + run-log path
- [ ] Leg 8 (`themed-native-frame`) verified as its prerequisite; spec is `windows-native-frame-splash`
