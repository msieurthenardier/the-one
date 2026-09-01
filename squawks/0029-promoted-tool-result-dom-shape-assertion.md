# Squawk 0029: Pin the promoted tool-result bubble's structural contract with a DOM-shape assertion

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-01
**Completed**: —

## Report

Flight 2's fix pass promotes peer-visible tool results (e.g. `[platform-send-ok]`) to top-level
bubbles in Chat: direct child of `.messages`, NOT nested in any `[data-testid="trace-shell"]`
accordion, followed by a `.msg-attribution.from-agent` row. That structural contract is currently
pinned only by one browser test plus the behavior test's structural dump — thin, given Flight 3 will
touch `chat.js` again for Discord rendering. Add a cheap DOM-shape browser assertion (the run-2
checkpoint-7 `evaluate_script` checks are the template: `isDirectChildOfMessages`,
`closest('[data-testid="trace-shell"]') === null`, sibling attribution row) so a regression doesn't
require a full behavior-test run to catch.

## Evidence

- `tests/behavior/stub-connector-round-trip/runs/2026-08-31-22-43-08.md` checkpoint 7 (the structural checks)
- Flight 2 debrief, Testing Assessment ("reasonable but thin")
- `the_one/interfaces/web/static/js/areas/chat.js` promotion logic (fix pass 2)

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
