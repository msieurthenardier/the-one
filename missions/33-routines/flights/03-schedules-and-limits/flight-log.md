# Flight Log: Schedules and Limits

**Flight**: [Schedules and Limits](flight.md)

## Summary

*(Written at landing.)*

---

## Planning

### Origin (2026-10-29)

Flight 3 began as the mission's closing HAT. In planning, the operator
reviewed the Flight 1 and 2 judgement calls on five topics, one at a time:

1. **Caps.** The 50-row total and the agent's 10 active conflicted (the 50
   counted disabled and finished routines, so finished one-offs filled it).
   Decisions:
   - one active cap of 50 for everyone, raise-only;
   - intervals down to 1 minute;
   - no runs-a-day cap;
   - resolved proposals follow retention, not a count of 500;
   - 5 writes a turn kept ("if bulk becomes a thing we can address it
     later");
   - finished one-offs age out with retention.
2. **Purging the proposal record.** Settled by the caps decision on
   proposals.
3. **The `default` agent.** Keeps refusing routines. It is reserved for a
   future built-in assistant that is never configured by hand, and the UI
   cannot start a chat without an agent.
4. **The date and time form.** The operator chose a standard, robust
   recurrence form modelled on Google Calendar's "Custom recurrence" (a
   screenshot was shared). Decisions:
   - a day missing in a month is skipped, with a UI warning;
   - "after N occurrences" counts missed and skipped occurrences;
   - units: minutes (1-1439), hours (kept, since the data model already has
     them, so existing routines convert one-to-one), days, weeks, months,
     years.
5. **Maintenance.** All six items are in this flight.

The operator agreed to split the work: this flight, "Schedules and limits",
then Flight 4, "HAT and alignment".

## Leg Progress

*(Entries added as legs land.)*

## Decisions

*(In-flight decisions recorded here.)*

## Flight Director Notes

- Planning ran from `main` at `ebb83d8c` on branch
  `flight/03-schedules-and-limits`.
- The operator approved every *(FD)* call in the spec ("looks good to me")
  while the Architect's cycle 1 review was running.

### Design review, cycle 1 (Opus Architect): approve with changes

The four high-severity findings, and how each was fixed:
- **H1, the route move was not "pure".** Two test files build a bare app
  from `api.router` and patch `api.*`.
  - Fix: the routes are included into `api.router`, and the handlers look
    up the `api` helpers lazily.
  - `_RoutineTurnHost` stays in `app.py`, because moving it would create an
    import cycle for about 30 lines.
- **H2, the "after N" counter disagreed with the form's last date.**
  - The operator chose to count from the start, deterministically. The
    `occurrences` column is dropped.
- **H3, the spec never said whether the start is an occurrence.**
  - The start is inclusive when it matches the rule. When it does not, it
    only begins the series *(FD)*.
  - The v47 start is the routine's `next_run_at`, so the next run is
    unchanged.
- **H4, the `agent-routines` lane would be red between legs.**
  - Sentences are now rendered on the server (`schedule_text`, plus a
    preview route).
  - The old form keeps sending the legacy shapes, which DD5 accepts.
  - The integration leg carries a minimal JS adapter.

The medium findings, and how each was fixed:
- **M1, the zone-change path.** New DD12. The query selects by the new
  shape.
- **M2, one-offs across a zone change.** The operator chose to keep the
  instant, which reverses the cycle 0 *(FD)* wall-clock rule for one-offs.
- **M3, minute/hour units.** The anchor stays fixed and `start` is
  rewritten. Re-enabling continues the grid *(FD)*.
- **M4, routines that are off had no bound.** The operator chose
  `ROUTINES_OPEN_MAX = 200` on routines that are not Done.
- **M5, v47.**
  - It uses a frozen converter.
  - The pending `base` takes the routine's migrated schedule verbatim when
    it matches.
  - Resolved proposals are rewritten too.
  - The unreadable path gets named values and a duplicate guard.
  - The column-list pins are updated.
- **M6, sentences.** They come from the server (`POST …/routines/preview`),
  so no calculator is written in JS.
- **M7, leg sizes.** The core is split from the integration, and the
  controls are split from the form, giving 7 legs.
- **M8, DD11.** The collapse now matches on a stable `reason_code` and runs
  in one transaction.
- **M9, minute precision.** Relative starts round up to the minute.
- **M10, retention.** The sweep supersedes pending proposals, and the test
  seam returns the new keys.

The low findings: two citations were corrected, the criterion wording was
softened, and the month-day warning is a field hint linked by
`aria-describedby` rather than `App.ui.notice`.

Suggestions adopted:
- `repeat` and `ends` are optional on input;
- the evals harness maps the new shape back to `kind`, so no re-baseline is
  needed;
- the calculator's search is bounded;
- Escape inside the modal closes only the calendar;
- the controller split adds a script tag, which needs a restart;
- the Purge now confirm wording is updated;
- the migration test pins the fallback zone.

### Design review, cycle 2 (Opus Architect): approve with changes

The cycle 1 fixes held: the `include_router` placement, the pending-base
rule and the DD11 mapping were confirmed against the code. The new findings
were fixed in the spec without a third cycle (the skill allows at most two;
the per-leg design reviews of the high-risk legs re-check them):
- **[high] Spring-forward corruption.** v48 and the DD5 aliases took
  `start.time` from `next_run_at`'s wall time. A 02:30 daily on a
  spring-forward day would have moved to 03:00 for good. Fix:
  `start.time` comes from the legacy `time` field; `start.date` comes from
  `next_run_at`'s date.
- **The leg 2 core collided with live callers.** It is now new code beside
  the old, and leg 4 switches the callers and deletes the old code. The
  caps, retention and skip-collapse work became its own earlier leg with
  v47 (columns only); the schedule rewrite is v48. That makes 8 legs.
- **`_poke_scheduler`** stays in `api.py`, because `put_time_settings` and
  one test call it.
- **DD12, zone changes.**
  - The rewrite now covers routines that are off.
  - It does a compare-and-set on `schedule` and `anchor_at`.
  - It rebases pending proposal bases, so a zone change never makes a
    proposal stale.
- **Instants.** `anchor_at` is now the exact instant for one-offs and
  minute/hour units, and `start` is only how it displays. This closes three
  problems at once: sub-minute precision, the repeated fall-back hour, and
  one-offs across a zone change.
- **A save with no future occurrence** is refused: 422, or 409 at approval
  *(FD)*.
- **One sentence wording,** "Every day at 9:00 AM" *(FD)*. The leg 4 JS
  adapter is specified, including the stale 409 body and the list of
  browser tests it edits.
- **Legacy proposal payloads** fix their start when they are made *(FD)*.
- **Low findings:**
  - an off interval's `anchor_at` is set;
  - `upgrade_failed` sets `started_at`;
  - v48's lazy import of `time_zones`;
  - the proposal-time caps check is named;
  - the 24 h grace for a series' last occurrence is stated;
  - `last_occurrence` is named;
  - the scope of the alias proof is stated;
  - `repeat` null with an `ends` is refused;
  - `routines-no-spam` is added to the eval gate;
  - the plan-token checklist item is fixed;
  - the date picker's `min` is defined for an edit.

### Execution start

- The operator approved the cycle 2 *(FD)* calls by asking to fly the
  flight (`/mission-control:agentic-workflow flight 03 mission 33`). The
  status moved from `planning` to `ready` to `in-flight`.
- **Crew file:** `.flightops/agent-crews/leg-execution.md` (plugin 1.2.3).
  The Developer is Sonnet. The Reviewer is Sonnet when the diff touches a
  security-sensitive surface (caps and retention on agent-written routines
  count), otherwise Haiku. The Accessibility Reviewer is Sonnet for the UI
  batches.
- **Batches,** following the operator's standing preference, each closed by
  a review and a checkpoint commit made by the FD:
  - A: legs 1-2;
  - B: legs 3-4;
  - C: legs 5-7;
  - then leg 8 (behavior re-runs and the gate).
- **Leg 6** (the controls) may run beside Batch B, on disjoint files.
