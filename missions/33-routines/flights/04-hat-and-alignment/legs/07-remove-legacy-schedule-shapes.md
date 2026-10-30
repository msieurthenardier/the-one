# Leg: remove-legacy-schedule-shapes

**Status**: completed
**Flight**: [HAT and Alignment](../flight.md)

## Objective

Remove the legacy schedule input shapes that Flight 3 kept as aliases (F3
DD5): `{"kind": "once"|"daily"|"weekdays"|"weekly"|"interval", ...}` and the
legacy one-off `at` / `in` keys. After this leg the routine REST routes, the
preview route and the agent tools accept only the canonical shape `{start,
repeat, ends}` (with `start` as `{date, time}`, the relative `{"in": {amount,
unit}}`, or, on operator routes, `{"now": true}`), and every fixture, script
and eval that used the old shapes is moved to the canonical one. Nothing
dormant is left (the operator's standing instruction).

## Context

- **Operator decision at the HAT** (Part J, C6): "we should probably remove
  that now." Flight 3's debrief (Recommendation 3) planned it for later and
  suggested isolating the parsing; the operator chose to delete now.
- **Today:** `the_one/routines/recurrence.py::normalize` (~:283) routes a
  body with `kind` to `_normalize_legacy` (~:338) and
  `_normalize_legacy_calendar` (~:377); the docstring (~:293) documents the
  aliases. The **v48 migration's frozen converter** in `the_one/db/schema.py`
  (`_v48_convert` and helpers) is separate and **stays**: it converts stored
  rows, and migrations are frozen history.
- **Consumers of the old shapes** (grep at planning): unit tests
  (`tests/test_routines_recurrence.py`, `test_routines_recurrence_text.py`,
  `test_routines_api.py`, `test_routines_service.py`,
  `test_routines_scheduler.py`, `test_routines_self_config_api.py`,
  `test_routine_tools.py`, `test_routine_tools_taint.py`,
  `test_api_name_rule.py`, `test_evals_routines.py`, `test_db_migration.py`
  (the v48 tests feed old shapes to the frozen converter: those stay),
  helpers `tests/_routine_app.py`, `tests/_routine_tools_env.py`), browser
  tests (`test_flow_agent_routines.py`, `_form.py`, `_self_config.py`,
  `test_flow_chat_routine_marker.py`, `test_flow_chat_drawer.py`),
  `scripts/ui_capture.py`, and `evals/harness.py` (`_legacy_kind`, ~:442,
  which classifies a stored schedule for checks: keep it only if it is an
  output classification the checks need, renamed so it does not read as
  input support; else remove).
- Builds after legs 05 and 06 (shared browser test files).

### Design decisions (amended at design review)

**L7-DD1. Input.** `normalize` accepts only the canonical shape. A body with
a **top-level `kind`** is refused with one sentence that names the canonical
shape, so a model can correct itself: "A schedule is {start, repeat, ends};
the older kind-based shape is no longer accepted." (on `loc ["schedule"]`:
422 on the REST routes through `RoutineScheduleError` →
`RoutineFieldError("schedule", …)`, `service.py` ~:95; the tool error through
`tools.py` ~:185). A stray top-level `at`, `in` or `on` with no `kind` keeps
`_check_keys`' existing generic refusal ("A schedule does not take 'at'."),
pinned by a test (FD call). Nested `ends.kind` and the canonical relative
start `{"start": {"in": …}}` are untouched.
- **Delete in `recurrence.py`:** `_normalize_legacy` (~:338-366),
  `_LEGACY_KEYS` (~:369-374), `_normalize_legacy_calendar` (~:377-435), the
  `if "kind" in raw` branch (~:302-303, replaced by the refusal), and the
  legacy lines of `normalize`'s docstring (and the module docstring if it
  mentions the aliases). **Keep** (the canonical path uses them): `_relative`,
  `_REL_UNITS`, `_wall_instant`, `ceil_minute`, `_int`, `_check_keys`,
  `_hhmm`, `MSG_NO_RUNS_LEFT`. `service.validate_schedule`'s docstring ("or
  any legacy shape", ~:91) is reworded. `schema.py`'s `_v48_*` helpers import
  nothing from `recurrence` and stay untouched.

**L7-DD2. Fixtures.** Every test, helper and script input moves to the
canonical shape through one shared helper in the test helpers (and a copy in
`scripts/ui_capture.py`): e.g. `daily(time)`, `weekly(days, time)`,
`every_hours(n)`, `once_in(amount, unit)`. Mappings: interval N hours →
`{"start": {"in": {"amount": N, "unit": "hours"}}, "repeat": {"every": N,
"unit": "hour"}}`; a `once` with `in` → a relative start; a `once` with `at`
→ a `{date, time}` start or a relative start. Canonical starts need a date: a
repeating start in the past is accepted (`_build` limits only the first
instant), so a fixed date works under a frozen clock; tests that pin
`next_run_at` or `start.date` (`test_routines_recurrence.py` ~:288-330) get
recomputed expectations. Tests that exist only to prove the aliases
(`test_routines_recurrence.py` ~:324-405, ~:655, e.g.
`test_legacy_weekdays_and_weekly_shapes`) are deleted; refusal tests are
added per path (create, update, preview, `schedule_routine`,
`change_routine`) plus a parametrized `normalize` test over every legacy
`kind` value. Also in scope: `tests/_routine_tools_env.py` (~:51, `IN_2H`),
`tests/test_routines_scheduler.py` (~:460).
- **`evals/harness.py::_legacy_kind` stays**: it is an **output**
  classification (a stored schedule → once/daily/weekdays/weekly/interval for
  `RoutineView.kind`, compared by the `routine_scheduled` check,
  `checks.py` ~:60, ~:381). Rename it (e.g. `_schedule_class`) and reword its
  docstring as "classify a stored schedule for the checks"; the TOML params
  and `RoutineView.kind` keep their names. No scenario change, no eval run.
- `tests/behavior/routine-connector-delivery.md` is deleted by the FD (leg
  02's plan), not edited here.

**L7-DD3. Docs.** `the_one/agents.md` "Routines (M33)" (incl. ~:2882,
"Server `on` input (legacy alias…)") and `evals/README.md` (~:76) lose the
alias text; CLAUDE.md appears to need no change (check); the v48 migration
note stays.

## Acceptance Criteria

- [ ] AC1. A legacy-shaped schedule is refused on create, update, preview and
      through the agent tools with the one sentence of L7-DD1; a test pins
      each path.
- [ ] AC2. `grep -rnE "_normalize_legacy|_LEGACY_KEYS|legacy shape|legacy alias|[\"']kind[\"']: *[\"'](once|daily|weekdays|weekly|interval)[\"']|kind=[\"'](once|daily|weekdays|weekly|interval)[\"']" the_one/ tests/ scripts/ evals/*.py evals/routines evals/README.md CLAUDE.md --exclude-dir=runs`
      has hits only in `the_one/db/schema.py`'s v48 block,
      `tests/test_db_migration.py`'s v48 tests (`TestSchemaV48`, `_DAILY_OLD`),
      the refusal tests, and the eval checks' output `kind` values
      (`routines-follow-up.toml` `kind = "once"`, `test_evals_routines.py`):
      each surviving hit named in the flight log.
- [ ] AC3. After leg 06's Developer has finished: `THE_ONE_TEST_NETNS=1 make
      test-unit` (15 skipped); the lanes `agent-routines`, `chats` and
      `chats-transcript` pass; `scripts/ui_capture.py --list` runs.
- [ ] AC4. The tool schemas and text are unchanged (no eval run), unless the
      Developer finds alias text in a tool description, in which case the FD
      runs the eval comparison.

## Files Affected

`the_one/routines/recurrence.py`; the tests, helpers, script and eval files
listed in Context; CLAUDE.md, `the_one/agents.md`, `evals/README.md`.

## Citation Audit

`recurrence.normalize` ~:283 (docstring ~:293, the `kind` branch ~:302),
`_normalize_legacy` ~:338, `_normalize_legacy_calendar` ~:377;
`evals/harness.py::_legacy_kind` ~:442 (use ~:335). Verified at planning.
