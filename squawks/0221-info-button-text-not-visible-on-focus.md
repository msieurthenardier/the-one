# Squawk 0221: Info-button descriptions are only a hover tooltip

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-15
**Completed**: 2026-10-21

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
Mission 31 Flight 2 leg 05. `App.ui.infoButton` is now a press-only toggletip (the operator chose press-only on 2026-10-21, so the hover `title` tooltip is removed; note for the release notes).
- The button has `aria-expanded` and `aria-controls`; pressing it (click, Enter, Space) toggles a `div.ui-info-bubble` inside `span.ui-info` showing the description, with a polite live region filled after the bubble shows so it is announced once.
- Escape, an outside press, focus leaving or a re-press closes it; focus stays on the button; one bubble is open at a time; the capture-phase document listeners exist only while open (a static guard now pairs every `document.addEventListener` in `js/ui` with a `removeEventListener`).
- The hidden description span and `aria-describedby` are unchanged. The string-path icons keep `title` until Flights 3 and 4.

## Verification
A contract case (both engines) shows that focusing or activating the info button reveals the description visibly, that Escape dismisses it, and that the description is announced once.

## Sign-Off
**Reviewer**: pending (flight review)
**Verdict**: pending
**Commit**: pending (flight commit)
