# Squawk 0194: testid registry rows for the provider Test button are stale

**Status**: deferred
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —

## Report
`docs/ui-testid-registry.md` lists `test-connection-btn` under area "admin", but the provider editor has lived in studio (Library) since sortie 02; and it lists `test-provider-btn` as a testid, though that is only a CSS class on the same button. A behavior-test Executor following the registry used the wrong testid in sortie 03's live run.

## Evidence
- `docs/ui-testid-registry.md` ~l.372 (`test-connection-btn` | admin) and ~l.373 (`test-provider-btn` | studio).
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js` ~l.88 — `class="btn-outlined-primary test-provider-btn" data-testid="test-connection-btn"`.
- Run log `tests/behavior/anthropic-plan-token-chat/runs/2026-10-12-17-04-32.md` (Executor closing).

## Deferral
Deferred mid-flight (sortie 03). Revisit trigger: the next squawk batch after the sortie 03 debrief (batch with 0193). Check `tests/test_ui_guards.py`'s registry sync before removing the `test-provider-btn` row.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
