# Squawk 0221: Info-button descriptions are only a hover tooltip

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-15
**Completed**: —

## Report
`App.ui.infoButton` (formerly the hand-built `.field-info-icon`) carries its description only in `title` (a hover tooltip) and in a visually hidden span that the control references through `aria-describedby`.
- Sighted keyboard and touch users cannot see the text on focus or on press (the intent of WCAG 1.4.13 and 3.3.2).
- The inventory row already records this debt: "no keyboard-visible popover".

Adding a focus or press popover is new behaviour, not a codification, so Mission 31 Flight 1 shortened the button's accessible name and left the popover as this squawk.

## Evidence
- `the_one/interfaces/web/static/js/ui/field.js` `App.ui.infoButton`.
- `docs/ui-control-inventory.md` Buttons table, the info-icon row ("Tooltip carried by `title` plus `aria-describedby`; no keyboard-visible popover").
- Mission 31 Flight 1 Accessibility Reviewer, non-blocking item 7.

## Corrective Action
*(written at completion)*

## Verification
A contract case (both engines) shows that focusing or activating the info button reveals the description visibly, that Escape dismisses it, and that the description is announced once.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
