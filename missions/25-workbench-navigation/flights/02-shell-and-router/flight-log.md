# Flight Log: Shell and Router

**Flight**: [Shell and Router](flight.md)

## Summary

Planned 2026-10-01 under autonomous execution. The branch `flight/02-shell-and-router`
is **stacked on** `flight/01-control-library-foundation`: the Flight 1 PR (#217) is
waiting on the operator's merge.

---

## Reconnaissance Report

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Squawk 0082 (deferred): `App.router.replaceSub` leaves `currentSub` stale | confirmed-live | `static/js/app.js:309-314`. The router research also found a second effect: the cross-area abort rollback uses the stale `currentSub` (app.js:171) | Fixed by construction in `router-and-redirects` (DD4); close in the flight commit |
| F1 debrief: 4 recurring lane flakes | needs-human-recheck | The F1 debrief's sequential run did not reproduce them | Investigate and fix in `test-navigation-helper` before the migration (DD9) |
| F1 debrief: `.visually-hidden` only in area CSS | confirmed-live | Defined in `admin.css` and `chat.css` only | Lift in `rail-and-shell` (DD7) |
| F1 open item: CI WebKit install never run | needs-human-recheck | Concourse at 127.0.0.1:8080 is unreachable | Re-check before the PR; otherwise an operator item |

---

## Leg Progress

*(entries appended as legs land)*

---

## Flight Director Notes

- 2026-10-01: Flight design review.
  - **Architect cycle 1** returned "approve with changes" with 21 issues (5 high). The
    spec was rewritten:
    - `go`/`sync` URL primitives;
    - the alias-layer studio.js changes;
    - teardown discard with per-area sources;
    - confirm-dialog test dispositions and native Enter semantics;
    - store copies, load state and invalidation map;
    - guard traversal mechanics and link-interception rules;
    - leg 3 split into `confirm-dialog-native` + `unified-leave-guard` (7 legs).
  - **Architect cycle 2** returned "approve with changes": 2 high and about 10
    medium/low items, all text additions with no redesign:
    - section-root routes render exactly the root (the Back item→list close);
    - `prevSection` captured before assignment in hydrate, plus a `doSelect` stale-then
      guard;
    - traversal details (revert popstate no-op, hashchange dedupe, live delta, boot seq);
    - `sync` dropped while a decision is pending;
    - the per-site `replaceSub` table;
    - `isDirty = dirty && editorOpen()`;
    - an interim leg-3 guard;
    - the scoped `~new` redirect;
    - a bubble-phase interceptor;
    - the rail current-href rule;
    - DD6 role and styling notes;
    - Chats history.
  - These were applied without a third cycle: the methodology caps flight review at two,
    and per-leg design reviews (high-risk legs) will re-verify against the code.
  - Flight set `ready`.

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
