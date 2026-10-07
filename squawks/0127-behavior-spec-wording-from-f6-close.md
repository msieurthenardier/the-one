# Squawk 0127: Behavior-spec wording drift from the Mission 25 Flight 6 close

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

## Report

Mission 25 Flight 6's mission-close re-runs (run `2026-10-07-11-51-23`) all passed. Their Validators listed Expected-Result wording that predates the flight's intended changes. No product change is needed; the specs should say what the build does now, so a later run doesn't stop to re-interpret them. Same shape as squawk 0122.

## Evidence

Each run log's "Validator closing" under `tests/behavior/{slug}/runs/2026-10-07-11-51-23.md`:

- **`system-provider-config`:**
  - Step 2: the empty state has no intro line, and it has its own Add provider button.
  - Step 5: name the "Provider created" toast, the new tile, the intro line and Available models with its help line.
  - Steps 2 and 6: "Used by" is visually hidden; the tile reads "0 agents".
  - Step 7: "the text clears" means the Unsaved changes caption. Name the "Provider saved" toast and the focus on the editor title.
  - Step 8: both a toast and an inline result line appear.
  - Steps 9–10: allow a re-arm before the confirm, and let the armed look settle for about 0.6 s before capturing it.
  - Step 10: the "Provider deleted" toast.
  - The header's Updated line.
- **`shell-navigation-smoke`:**
  - Step 9: record the raw hash at navigation commit (the legacy form is expected there), then assert `#settings/providers` after boot and after the reload.
  - Step 4: the description "begins with" the quoted sentence; "Filter agents" is an accessible name, not a visible label.
  - Step 7: restoring Auto removes the `theme-preference` key.
- **`studio-agent-crud`:**
  - Steps 3–4: with one provider and one model, Provider and Model are pre-selected.
  - Step 8: about 400 ms of settle before judging the armed look.
  - Step 9: name `new-agent-btn`.
  - A neutral "Saved" toast after Save is expected.
- **`list-and-detail`:**
  - Step 18: exempt the Design language page's own `role=alert` demos from "No error banners".
  - Say where focus goes after a dirty-guard Continue (`MAIN#main-content`).

## Corrective Action
*(written at completion)*

## Verification
Each spec re-read against its `2026-10-07-11-51-23` run log, each with an Updated line. No Expected Result may change meaning, only its wording.

## Sign-Off
*(written at completion)*
