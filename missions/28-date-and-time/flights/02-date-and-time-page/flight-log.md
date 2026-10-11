# Flight Log: The Date and Time Page

**Flight**: [The Date and Time Page](flight.md)

## Summary

Planned 2026-10-10, while Flight 1's last legs ran. The operator pre-authorized
autonomous execution through to one mission PR, with no per-flight HAT.

---

## Leg Progress

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes

### 2026-10-10: Flight design

- Two Architect cycles (Opus). Both returned **approve with changes**, and
  every finding was applied.
- **Cycle 1:**
  - (high) Browsers report legacy aliases (`Asia/Calcutta`, `UTC`), so DD6
    adds `links`, `effective.canonical` and canonical comparisons.
  - The radio card structure, defined so the zone rows never join the radio's
    accessible name.
  - Patch-in-place, generations, and `setActive`.
  - The boot fetch bounded at 2 seconds, with an `r.ok` check.
  - An unnamed zone uses the server offset.
  - The pinned time-label tests and Settings lists.
  - `renderPage` exported.
  - `TZ` pinning and `set_fixed_time`.
  - Leg 2 split into a radio-group leg and a page leg.
- **Cycle 2:**
  - (high) tzdata 2026 merges cities into aliases (Oslo → Berlin, and others).
    **FD decision:** search also finds alias names and shows them as their own
    items ("same clock as …"). A pick, or "Use {browser}", stores the name the
    operator chose. Comparisons stay canonical, and the "Selected" line shows
    the stored name.
  - DD6's server part moved into leg 1.
  - `zoneFromSettings`, used on save and at boot.
  - The generation counter is module-level, and a failed PUT re-GETs.
  - An exact CSS selector for the suppressed active row.
  - Testid placement and leg naming.
  - The settings lane re-budget allowed.
- Status: ready. It executes after Flight 1 lands and commits, on a branch from
  `flight/01-agents-know-the-time`.
