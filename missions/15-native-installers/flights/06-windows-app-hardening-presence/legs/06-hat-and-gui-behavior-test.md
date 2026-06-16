# Leg: hat-and-gui-behavior-test

**Status**: completed
**Flight**: [Windows Native App Hardening — Desktop Presence & Lifecycle](../flight.md)

## Objective

Verify the F6 desktop behaviors (tray, background-run, close-to-tray, single-instance
focus, window-state, theme persistence) on a **real Windows install** via an
operator-driven Witnessed HAT against the `windows-desktop-presence` behavior test —
the only apparatus that can drive + observe the native surface (DD6).

## Context

- Interactive / HAT leg (no autonomous Developer/Reviewer agents): the Flight Director
  guided the operator step-by-step through `tests/behavior/windows-desktop-presence.md`;
  the operator acted, the Flight Director judged.
- The frozen artifact was built by the Concourse `windows-installer` pipeline (the
  pipeline's git resource temporarily repointed to `flight/06`), published to minio, and
  installed by the operator. Builds #13–#16 (each rebuild after a mid-HAT fix).

## Acceptance Criteria

- [x] Run the `windows-desktop-presence` Witnessed behavior test on a real Windows
      install and confirm **pass** — run log:
      [runs/2026-06-15-18-00-00.md](../../../../../tests/behavior/windows-desktop-presence/runs/2026-06-15-18-00-00.md)
      (10/10 checkpoints + the over-the-top-upgrade variant).
- [x] Any launch-/behavior-blocking defect found is fixed and re-verified on a fresh
      frozen build before the leg lands (four fixes: stdio crash `25e200a`,
      window-state restore + on-show resize `76dd170`, installer over-the-top `41c51fe`;
      plus the operator-side stale-container removal).

## Verification

The behavior-test run log records each checkpoint's result and the five bugs the HAT
surfaced (see the run log's "Bugs found & fixed" table). All desktop behaviors pass on
the installed Windows app.

## Outcome

PASS. One non-blocking edge case deferred to a follow-up: single-instance launch while a
headless the-one `serve` (no window) holds 8484 currently silent-exits (operator chose
to land F6 and track it — see the mission Known Issues).

---

## Post-Completion Checklist

- [x] Behavior test passed (operator-driven HAT)
- [x] Run log committed (`tests/behavior/windows-desktop-presence/runs/2026-06-15-18-00-00.md`)
- [x] Mid-HAT fixes committed (`25e200a`, `76dd170`, `41c51fe`)
- [x] Flight log updated; leg + flight status set
