# Squawk 0108: `App.ui.emptyState` docstring still says listPane passes `role: 'status'`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-01
**Completed**: 2026-10-07

## Report

The option comment for `App.ui.emptyState` in `ui/feedback.js` still says listPane passes
`'status'` as the role. That stopped being true in the Flight 1 review fix round. The
list pane's empty element no longer carries `role="status"`; announcements now come from
a persistent `.ui-list-pane-status` live region. The comment misleads anyone reading the
factory's API. Found by the Mission 25 Flight 1 debrief (Architect).

## Evidence

- `the_one/interfaces/web/static/js/ui/feedback.js:51` contains "role (set on the root
  when given; listPane passes 'status')".
- `the_one/interfaces/web/static/js/ui/list-pane.js` builds the empty state without a
  `role`, and a separate `.ui-list-pane-status` region does the announcing.

## Corrective Action

Reworded the `emptyState` option comment in `ui/feedback.js` (listPane passes no role; its own live region announces) and fixed the same stale claim in `the_one/agents.md` (the listPane changes bullet, which showed `role: 'status'`). Confirmed against `list-pane.js`: `emptyState({title})` is built with no role and a separate `.ui-list-pane-status` `role=status` region announces. `docs/ui-control-inventory.md` had no such claim.

## Verification

Read back the comment and agents.md line. Static guards (`tests/test_ui_guards.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`), `make test-unit`, and ruff were run; see the developer report for results.

## Sign-Off

**Reviewer**: independent batch Reviewer (Haiku tier: no credential, gate, sandbox or self-configuration-identity surface in the diff); `make test-unit` 5496 passed, 10 skipped; static guards 265 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-07` on branch `squawk/turnaround-2026-10-07`
