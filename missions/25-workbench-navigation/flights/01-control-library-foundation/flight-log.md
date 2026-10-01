# Flight Log: Control Library Foundation

**Flight**: [Control Library Foundation](flight.md)

## Summary

Flight planned 2026-09-30 under autonomous execution. The operator approved Mission 25 and
asked for it to run autonomously; the human touchpoints are the post-Flight-3 checkpoint
and the alignment flight.

---

## Reconnaissance Report

Source items folded into this flight (DD12), checked against `b9630bc`:

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Squawk 0105 — stale `DYNAMIC_SINK_BASELINE` header count | confirmed-live | `tests/test_ui_guards.py:90` still reads "92 sites across 27 files" | Fold into Leg 1 |
| Squawk 0106 — JS changes can skip the static UI guards | confirmed-live | `.flightops/agent-crews/leg-execution.md` names no static-guard tests for `static/` changes | Flight Director edits the crew prompts at flight start; close in the flight commit |
| Squawk 0101 — KB create lands on grid | confirmed-live (out of this flight) | Mission assigns it to Flight 3 | Not folded |
| Squawk 0082 (deferred) — `App.router.replaceSub` leaves `currentSub` stale | confirmed-live (out of this flight) | `static/js/app.js` | Carry to Flight 2 (router contract) |

---

## Leg Progress

*(entries appended as legs land)*

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes

- 2026-09-30: Planning probes. `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`. System
  `python3` has `gi` with WebKit2 4.1 (WebKitGTK 2.52.6); the repo venv has neither `gi`
  nor `pywebview`. Playwright 1.58.0 is installed; `~/.cache/ms-playwright` holds chromium
  and firefox builds but no webkit.
- 2026-09-30: Design review. Architect cycle 1 returned "approve with changes" with 17
  issues: the DD2 regex collision, composite test ids, the WebKit route, the
  skip/require policy, control boundaries, DD6 site lists, listener cleanup, DD8 engine
  gaps, probe environment pinning and smaller items. The spec was revised, Leg 1 was
  split into `ui-test-apparatus` and `control-mechanism-spike`, and DD14 was added
  (list-pane ARIA). Architect cycle 2 also returned "approve with changes" with 10
  refinements, all applied without a third cycle (the methodology caps review at two):
  - Escape `preventDefault` and popup containment
  - `--fg-on-accent-fill` moving with each fill, plus CSS usage pins
  - all three toggle kinds named, with a dedicated `--control-border`
  - route-2 post-merge gating of Flight 2's first native modal
  - the §15 disposition (DD15)
  - testid value enforcement
  - DD4 comment convention
  - userland WebKit gotchas
  - the menu-in-dialog check moved to `core-controls`

  Flight set to `ready`.
