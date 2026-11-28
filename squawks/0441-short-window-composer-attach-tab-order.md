# Squawk 0441: short-window composer shows attach before the input but tabs to it after

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-27
**Completed**: —

## Report
In a window under 480px tall, the composer lays out attach, input, model label and Send on one row (sortie 21, HAT fix batch 2). The attach button is moved before the input visually with CSS `order: -1`, but the DOM and tab order are label, input, attach, model, Send, so keyboard focus reaches the input first and then the attach button, the reverse of what the operator sees (WCAG 1.3.2 Meaningful Sequence / 2.4.3 Focus Order, minor). Found by the sortie 21 accessibility review of the HAT changes. The `order: -1` rule predates sortie 21; the one-row layout made the mismatch visible.

## Evidence
- `the_one/interfaces/web/static/css/components.css` (short-height composer block, ~:3347): `.ui-composer-attach { order: -1 }`.
- `the_one/interfaces/web/static/js/ui/composer.js` (~:72): the visually hidden "Message" label and the input are built before the attach button.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
