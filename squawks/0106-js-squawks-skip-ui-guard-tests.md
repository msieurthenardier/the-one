# Squawk 0106: Verification of JS changes can skip the `test_ui_guards.py` unit guards

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-30
**Completed**: —

## Report

Squawk 0102 changed `static/js` and verified only through the studio browser
lane. That lane does not run `tests/test_ui_guards.py`, a unit-tier test that
statically scans the JS sources. So a guard violation (a new dynamic innerHTML
sink) reached `main` and turned `make test-unit` red until squawk 0104. Nothing
in the leg-execution crew prompts points a Developer or Reviewer at the static
guards when a change touches only frontend files.

## Evidence

- `.flightops/agent-crews/leg-execution.md` — the "Developer: Implement" prompt names `scripts/run-tests.sh <files>` and "`make test-unit` for the whole unit suite" but does not say which unit tests cover `static/js`.
- Squawk 0104's Report records the escape.

## Corrective Action

*(written at completion)*

Add one line to the leg-execution crew prompts (Developer: Implement and
Reviewer: Review): a change under `the_one/interfaces/web/static/` must also
run `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and
`tests/test_design_tokens_a11y.py` (the static JS/CSS guards), not only a
browser lane. Check whether `/mission-control:init-project` regenerates this
file, and if so make sure the edit survives or record it as a project override.

## Verification

*(written at completion)*

## Sign-Off

*(written at completion)*
