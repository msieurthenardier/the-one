# Squawk 0413: Removing a chip with its button drops keyboard focus to the page

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: —

## Report

In the shared chip-list control, clicking a chip's remove button (or pressing Enter or Space on it) deletes the chip, and with it the focused button. Nothing moves focus, so it falls to `<body>` (WCAG 2.4.3). A keyboard user then has to Tab in from the top of the page. The control is used on many pages. Found by the 2026-11-24 routine maintenance (Accessibility Reviewer); the Architect rated it Action Required.

## Evidence
- `static/js/ui/chip-list.js` `onClick` (about line 411): `chip.remove(); fire(); return;` with no focus move.
- The same handler's chip-body branch already moves focus: `root.insertBefore(input, clicked); input.focus();`.
- The Backspace-on-empty-input path keeps focus in the input.

## Corrective Action
*(written at completion)*

## Verification
A browser contract test focuses a chip's remove button, presses Enter, and finds focus on the next chip's remove button, or on the input when none is left, not on `<body>`. The project convention is "Focus after an in-place action" in `the_one/agents.md`.
