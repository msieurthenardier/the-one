# Squawk 0125: Document the pywebview 6.x upgrade blocker for the window chrome

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-06
**Completed**: —

## Report

Mission 25 Flight 5's window chrome depends on pywebview 5.4. pywebview 6.x's WinForms
backend adds `update_title_bar_theme()`, which runs on creation and on
`SystemEvents.UserPreferenceChanged`, sets DWM attributes 20 and 38 from the **OS**
theme, and would overwrite the app-chosen title-bar theme whenever the OS theme changes.

The flight spec's DD7 records this, but `the_one/agents.md` does not. A future dependency
bump could lift the `>=5,<6` pin without anyone seeing the conflict.

Source: the Mission 25 Flight 5 debrief, recommendation 4.

## Evidence

- `pyproject.toml`: the `gui` extra, `pywebview>=5,<6`.
- `missions/25-workbench-navigation/flights/05-window-chrome/flight.md`: DD7.
- `the_one/agents.md`: no mention of `update_title_bar_theme` or 6.x.

## Corrective Action

*(written at completion)*

Add a short "upgrade blocker" note to `the_one/agents.md`'s Window chrome block, and a
comment beside the `pyproject.toml` pin, both naming `update_title_bar_theme()` and the
re-check an upgrade needs.

## Verification

`grep update_title_bar_theme the_one/agents.md pyproject.toml` finds both notes.

## Sign-Off

*(written at completion)*
