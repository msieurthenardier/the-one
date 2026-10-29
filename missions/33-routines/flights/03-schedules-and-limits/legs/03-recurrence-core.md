# Leg: recurrence-core

**Status**: completed
**Flight**: [Schedules and Limits](../flight.md)

## Objective

Write the calendar recurrence as new, pure code beside the existing
five-kind calculator: the DD1 shape and its validation, the DD5 input
normalizer (canonical, relative and legacy shapes), the DD2 occurrence
calculator, and the DD7 sentences and warnings, proven by frozen-clock
tables. Nothing in the running app calls the new code yet; leg 4 switches
the callers, rewrites the data and deletes the legacy code.

## Context

- **Why beside, not in place:** `the_one/routines/schedule.py` (`validate`,
  `next_run`, `grace`, `occurrences_between`) and `describe.py`
  (`describe_schedule`) are live: the scheduler, service, tools and views
  call them, and stored data stays in the legacy shape until v48 (leg 4).
  Rewriting them now would break the unit tier.
- **Runs beside leg 2** in the shared tree. Leg 2 edits `limits.py`,
  `repository.py`, `service.py`, `proposals.py`, `scheduler.py`,
  `runner.py`, `tools.py`, `models.py`, `retention.py`, `schema.py` and some
  tests. **This leg edits none of those.** It creates new files only, and
  may import from `schedule.py` (`resolve_wall_time`, `parse_utc`,
  `_parse_hhmm`) and from `limits.py` (`RoutineScheduleError`,
  `ROUTINE_PROMPT_MAX_CHARS` is not needed) and `time_zones` without editing
  them. Its new range constants live in the new module, not `limits.py`.
- **Read the flight spec's DD1, DD2, DD5 and DD7 in full** — they are the
  contract. The essentials:
  - **The shape** (DD1): `start {date, time}`; `repeat` null or
    `{every, unit, days?, month_by?}` with units `minute|hour|day|week|month|year`;
    `ends` `{kind: never}` | `{kind: on, date}` | `{kind: after, count}`. The
    stored dict is fully normalized (sorted unique `days`; `days` only for
    `week`; `month_by` only for `month`, defaulting to `{"by": "day"}` when
    absent on input; `repeat: null` stores `ends` never; no extra keys).
  - **Ranges:** minute 1-1439, hour 1-168, day 1-365, week 1-52, month
    1-12, year 1-10; `days` non-empty 0-6 (0 Monday); `ends.count` 1-1000;
    `ends.date` on or after `start.date`; the start at most a year ahead of
    now; `repeat: null` with a non-never `ends` refused ("A routine that
    does not repeat has no end to set.").
  - **Two kinds of start:** instant-anchored (one-offs, minute and hour
    units) carry an exact `anchor` instant (UTC) and `start` is its
    wall-clock rendering in the zone; wall-clock (day, week, month, year)
    use `start` directly and have no anchor.
  - **Occurrences** (DD2): the start is the first occurrence when it
    matches the rule; when it does not, the series begins at the first
    matching occurrence at or after the start instant. Weeks counted
    Sunday-first from the week holding `start.date`. Month by day skips
    months without that day; month by weekday `nth` 1-4 or -1 (last); year
    on month/day, February 29 only in leap years. Ends on a date: inclusive
    in the zone. Ends after N: the Nth occurrence counted from the start,
    deterministic (no counter). Daylight saving for wall units through
    `resolve_wall_time` (gap → end of gap; repeat → first occurrence);
    minute/hour units are elapsed time from the anchor. The search is
    explicitly bounded (February 29 can be eight years away); past the
    bound or past `ends`, there is no next occurrence.
  - **Normalizer** (DD5): canonical input with `repeat`/`ends` optional; a
    relative start `{"in": {amount, unit}}` (minutes|hours|days) is now plus
    the amount **rounded up to the next whole minute**; legacy
    `{"kind":"once","at"}` (rounded up to the minute), `{"kind":"once","on":{date,time}}`,
    `{"kind":"once","in"}`, `daily`, `weekdays` (every 1 week on 0-4),
    `weekly`, `{"kind":"interval","hours":N}` (anchor = now + N hours
    exactly). For daily/weekdays/weekly, `start.date` is the local date of
    the rule's next occurrence after now and `start.time` is the legacy
    `time` field — never the resolved instant's wall time (a spring-forward
    gap would otherwise store the post-gap time). An agent-only minimum lead
    (`min_ahead`, today's `MSG_ONCE_TOO_SOON` rule) applies to the first
    occurrence of a one-off, checked after rounding.
  - **"No runs left":** a helper says whether the schedule has an
    occurrence after a given instant; leg 4's service refuses a save
    without one ("This schedule has no runs left.").
  - **Sentences** (DD7, one wording, sentence case): "Every day at 9:00 AM",
    "Every weekday at 9:00 AM" (every 1 week on exactly Mon-Fri), "Every
    week on Tue, Thu at 9:00 AM", "Every 2 weeks on Mon at 9:00 AM", "Every
    month on day 15 at 9:00 AM", "Every month on the third Tuesday at 9:00
    AM", "Every month on the last Friday at …", "Every 3 months on …",
    "Every year on October 29 at 9:00 AM", "Every 90 minutes from Oct 29 at
    3:00 PM", "Every 2 hours from …", "Once, on Thu, Oct 29, 2026 at 3:00
    PM"; suffixes ", until Jan 28, 2027" and ", 13 times". Clock and date
    text through `the_one.time_zones` formatters (12-hour, M25 DD14), as
    `describe.py` does. These go into agent tool results (leg 4/5), so they
    never include a chat title or channel name.
  - **Warnings:** month by day above 28: "Some months have fewer than {d}
    days. Those months are skipped."; year on February 29: "February 29
    only comes in leap years. Other years are skipped."
- **Zone helpers for DD12** (used by leg 4): render an anchor's `start` in a
  zone; nothing else of DD12 is in this leg.
- **The legacy `grace()` rule** carries over: 24 h for a one-off and for a
  series' last occurrence (no next occurrence), otherwise min(half the gap
  to the next occurrence, 2 h).

## Inputs

- Flight spec DD1, DD2, DD5, DD7 (sentences and warnings), DD12 (the
  render helper only).
- `the_one/routines/schedule.py`, `describe.py`, `limits.py`,
  `the_one/time_zones.py`; `tests/test_routines_schedule.py` (the
  existing frozen-clock style and DST cases to mirror); `tests/conftest.py`
  `frozen_clock`.

## Outputs

- `the_one/routines/recurrence.py` (suggested name): constants, shape
  validation, the normalizer (returns the canonical schedule and the anchor
  or None), `next_occurrence(schedule, anchor, after, zone)`,
  `occurrences_between(...)`, `last_occurrence(...)` (None for never),
  `has_future(...)`, `grace(...)`, the zone render helper.
- `the_one/routines/recurrence_text.py` (suggested): `describe(schedule,
  anchor, zone)` and `warnings(schedule)`.
- `tests/test_routines_recurrence.py` and
  `tests/test_routines_recurrence_text.py`.
- No `the_one/agents.md` change in this leg (other legs edit it
  concurrently); leg 4 documents the modules when it wires them.
- Flight log entry.

## Acceptance Criteria

- [ ] AC1. Validation accepts every in-range canonical shape and refuses,
      with one plain sentence each, every out-of-range or malformed field in
      the DD1 table (including `repeat` null with an `ends`, `days` on a
      non-week unit, `ends.date` before `start.date`, a start more than a
      year ahead). Accepted shapes come back fully normalized (two inputs
      that mean the same thing produce equal dicts).
- [ ] AC2. The normalizer maps every legacy shape and the relative start
      as in Context; for each legacy kind, the first occurrence of the
      normalized schedule equals `schedule.next_run(legacy, after=now, …)`
      today, under a frozen clock, including a 02:30 daily in
      America/Los_Angeles across the spring-forward day (start.time stays
      "02:30") and an interval created at a sub-minute `now`.
- [ ] AC3. A table of frozen-clock cases passes for: every unit with
      `every` 1 and N; weeks on several days with every 2 weeks across a
      year boundary (Sunday-first week numbering); month by day 31 skipping
      short months; month by weekday 1-4 and last; year on February 29
      skipping to the next leap year (including 2096 → 2104); the inclusive
      and the non-matching start; ends on a date (inclusive, zone-local);
      ends after N, including the Nth occurrence before "now" (no future
      occurrence) and a start in the past; the search bound returning None.
- [ ] AC4. Daylight saving: for day, week, month and year units, a time in
      the spring-forward gap runs once at the end of the gap and a repeated
      fall-back time runs once on its first occurrence; minute and hour
      units keep exact elapsed spacing across both changes; a one-off
      anchored in the second pass of the repeated hour keeps its exact
      instant.
- [ ] AC5. `grace` matches the legacy rule (24 h one-off and last
      occurrence; else min(half gap, 2 h)); `occurrences_between` counts in
      `(start, end]` with a cap, like the legacy function.
- [ ] AC6. The minimum lead time refuses an agent one-off less than a
      minute away after rounding, with today's sentence; "in 1 minute"
      passes.
- [ ] AC7. Sentences: a table covers every pattern in Context (each unit,
      weekday detection, nth and last, the minute/hour "from" form, both
      suffixes, the one-off form), and the two warnings appear exactly when
      due.
- [ ] AC8. No existing file other than the flight log and this leg file is
      modified by this leg (only new files plus those two); `THE_ONE_TEST_NETNS=1 make test-unit` passes;
      ruff clean.

## Verification Steps

- AC1-AC7: the two new test files (`PYTHON=.venv/bin/python bash
  scripts/run-tests.sh tests/test_routines_recurrence.py
  tests/test_routines_recurrence_text.py -x --timeout 30`).
- AC8: `git status --short` restricted to this leg's paths, the unit suite
  and ruff.

## Implementation Guidance

1. Shape and validation, with the ranges as module constants.
2. The calculator: instant-anchored units by arithmetic from the anchor;
   wall units by walking periods aligned to the start's period (day, the
   Sunday-first week, calendar month, year) with `every` N, resolving each
   candidate through `resolve_wall_time`. Compute "after N" by finding the
   Nth occurrence from the start once (N ≤ 1000) and capping `next` at it;
   compute "ends on" as an inclusive local-date bound. Bound every walk.
3. The normalizer on top, then `grace`, `occurrences_between`,
   `last_occurrence`, `has_future`, the render helper.
4. Sentences and warnings.
5. Tests as tables, `frozen_clock` for "now"; build expected instants with
   `zoneinfo` explicitly in each case so the tables read as specifications.

## Edge Cases

- `every` N weeks with a start mid-week whose chosen days include days
  before the start's weekday in the first week: those are before the
  start instant and never count.
- Month by weekday "last" when a month has four vs five of that weekday.
- A wall-clock start whose own time is in the spring-forward gap: the
  first occurrence is at the end of the gap; the stored `start.time` stays
  as typed.
- Ends on a date earlier than the first matching occurrence: no
  occurrences (the "no runs left" case).
- Large `every` values with year units hitting the bound before a leap day.

## Files Affected

- New: `the_one/routines/recurrence.py`, `the_one/routines/recurrence_text.py`,
  `tests/test_routines_recurrence.py`, `tests/test_routines_recurrence_text.py`.
- Edited: the flight log and this leg's status only.

## Citation Audit

Checked at `49a5051a`:
- `schedule.py::resolve_wall_time`, `parse_utc`, `_parse_hhmm`, `next_run`
  (interval `k >= 1`), `grace`, `occurrences_between` — verified.
- `service.py::validate_schedule` — `once` `on`/`in` handling, `min_ahead`
  — verified; `describe.py::describe_schedule` wording ("every day at …")
  — verified.
- `time_zones._clock`, `_WEEKDAYS`, `_MONTHS`; `tests/conftest.py::frozen_clock`
  — verified.
