# Squawk 0421: A proposal-card rebuild can still drop focus when the new body has a button

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: —

## Report

Squawk 0411 rescues focus only when a rebuilt card body has nothing focusable. If the focused control is replaced but the new body still has a button, focus still falls to `<body>`. An example is a pushed change from one pending state to another. The "focusable" check also uses a bare `[tabindex]` selector, so a body holding only a `tabindex="-1"` element counts as focusable, and the rescue is skipped. Both are edge cases, and no current card hits the second one. Found by the reviewers of the 2026-11-25 squawk turnaround.

## Evidence
- `static/js/areas/chat/proposal-cards.js` `build(e)`: the 0411 rescue runs only if `!newBody.querySelector('button, a[href], input, select, textarea, [tabindex]')`.

## Corrective Action
*(written at completion)*

## Verification
After a pushed rebuild of a card that held focus, focus lands on the matching control in the new body when one exists, or on the composer otherwise. The selector excludes `[tabindex="-1"]`. A test covers a pushed pending-to-pending rebuild.
