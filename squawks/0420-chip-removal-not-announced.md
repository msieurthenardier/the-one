# Squawk 0420: Removing a chip is not announced

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: —

## Report

After squawk 0413, removing a chip moves focus sensibly, but nothing tells a screen-reader user that the chip was removed (WCAG 4.1.3). When the last chip goes, focus lands on the input with no cue at all. The chip list already has a permanent `role=status` live node, written through `say()`. Found by the Accessibility Reviewer of the 2026-11-25 squawk turnaround.

## Evidence
- `static/js/ui/chip-list.js` `onClick`, remove-button branch (about line 414): the chip is removed and focus moves, but `say()` is not called.
- The live node `ui-chip-list-live` already exists, with its `say()` helper.

## Corrective Action
*(written at completion)*

## Verification
A contract test removes a chip with its button and reads "Removed <label>", or the project's wording, in the chip list's status node.
