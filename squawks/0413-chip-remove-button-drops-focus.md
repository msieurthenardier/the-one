# Squawk 0413: Removing a chip with its button drops keyboard focus to the page

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-25

## Report

In the shared chip-list control, clicking a chip's remove button (or pressing Enter or Space on it) deletes the chip, and with it the focused button. Nothing moves focus, so it falls to `<body>` (WCAG 2.4.3). A keyboard user then has to Tab in from the top of the page. The control is used on many pages. Found by the 2026-11-24 routine maintenance (Accessibility Reviewer); the Architect rated it Action Required.

## Evidence
- `static/js/ui/chip-list.js` `onClick` (about line 411): `chip.remove(); fire(); return;` with no focus move.
- The same handler's chip-body branch already moves focus: `root.insertBefore(input, clicked); input.focus();`.
- The Backspace-on-empty-input path keeps focus in the input.

## Corrective Action
In `static/js/ui/chip-list.js` `onClick`, the remove-button branch now picks a focus target before removing the chip: the next editable chip's remove button, else the previous one's (locked chips have no button and are skipped), else the input. It then removes the chip, focuses the target and fires `onChange`. Focus moves only when focus was on the chip, or had already fallen to `<body>` (WebKit does not focus a button on click). It is synchronous because the control patches in place, so `App.focusAfter` was not needed. Backspace is unchanged. The header comment and `docs/ui-control-inventory.md` describe the behaviour. No public API change.

## Verification
Added `test_remove_button_keyboard_moves_focus_to_next_previous_then_input` and `test_remove_button_focus_skips_locked_chips` to `tests/browser/test_ui_chip_list_contract.py`. They focus a remove button and press Enter. They assert focus lands on the next chip's button, then the previous one's, then the input, never `<body>`, and that a locked neighbour is skipped.

Falsified: with the focus line commented out, the test failed (`'BODY' == 'Remove c'`). With the fix restored, the `contracts-controls` lane passes (1308 passed, 4 skipped). `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass (396 passed). `ruff check` and `ruff format --check` are clean on the test file.

Original verification criterion:
A browser contract test focuses a chip's remove button, presses Enter, and finds focus on the next chip's remove button, or on the input when none is left, not on `<body>`. The project convention is "Focus after an in-place action" in `the_one/agents.md`.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0411-0419; Accessibility Reviewer (Sonnet)
**Verdict**: confirmed (`contracts-controls -k chip`: 96 passed). No status announcement is made on removal; that is logged as squawk 0420.
**Commit**: `squawk: turnaround 2026-11-25` on squawk/turnaround-2026-11-25
