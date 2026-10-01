# Squawk 0110: Chat composer's hidden image file input has no accessible name

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-01
**Completed**: —

## Report

The chat composer's file input (`chat-image-input`, used by the attach-image
affordance) has no accessible name: no `<label>`, `aria-label` or `aria-labelledby`.
The shared runtime resolver (`tests/browser/_a11y_resolve.js`) flags it whenever the
whole page is scanned. The Mission 25 Flight 2 `router-core` WebKitGTK probe hit it with
`--root-selector body` at `#agents` and `#settings/general`, where the chat panel is
present but hidden.

Assistive tech that reaches the input gets an unnamed control. The visible attach
button is the operator's real affordance, so impact is low, but the input should be
named or removed from the accessibility tree.

## Evidence

- The probe JSON in `missions/25-workbench-navigation/flights/02-shell-and-router/flight-log.md`
  (leg 3 entry) reports exactly one failure, `chat-image-input`.
- `grep -rn "chat-image-input" the_one/interfaces/web/static/js` shows the input is
  created without a name.

## Corrective Action

*(written at completion)*

Give the input `aria-label="Attach image"`, matching the visible button's name. If it is
purely an implementation detail behind a labelled button, consider `hidden` or
`tabindex="-1"` plus `aria-hidden`. Then add the chat composer to a resolver-backed
test.

## Verification

*(written at completion)*

## Sign-Off

*(written at completion)*
