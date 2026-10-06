# Squawk 0110: Chat composer's hidden image file input has no accessible name

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-01
**Completed**: 2026-10-05 (M25 Flight 4 leg 5, `composer-and-telemetry`)

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

Fixed in M25 Flight 4 leg 5 (`composer-and-telemetry`, flight DD6), in the composer
restyle:

- **The hidden file input is named.** `static/js/areas/chat/composer.js` builds it with
  `aria-label="Attach images"` (`type=file`, `accept=image/*`, `multiple`, `hidden`, testid
  `chat-image-input`, all unchanged). The name matches the visible button's, which the
  same leg renamed from "Attach image" to "Attach images" (the input takes several images,
  and the attachment is image-only, so the board's "Attach a file" would be untrue).
- **Named, not hidden from the tree.** `aria-hidden` was not used: the resolver selects
  every `input:not([type=hidden])` and skips neither `hidden` nor `aria-hidden`
  (`tests/browser/_a11y_resolve.js:18-20`), so only a name satisfies it, and a named input
  is also the honest state for assistive tech that reaches it.
- **The allow-list is gone.** Leg 4b's `test_flow_chat_pane.py` filtered
  `chat-image-input` out of the resolver's failures (`_unnamed`) and asserted it was the
  one failure left; both are removed, and the test now expects `[]` in every state.
- **The composer joined a resolver-backed test**, as the report asked (below).

## Verification

- **Browser:** `tests/browser/test_flow_chat_composer.py::test_no_unnamed_control_on_chats_with_a_chat_open_in_either_theme`
  runs the shared resolver (`_a11y_resolve.js` through `collect_label_failures`) over
  `body` on `#chats` with a chat open (joined, after a reply), in Light and in Dark, and
  expects no failure; it also pins `chat-image-input`'s `aria-label="Attach images"`.
- **Browser:** `tests/browser/test_flow_chat_pane.py::test_one_h1_landmarks_and_named_controls_in_every_state`
  expects `[]` from the resolver over the chat panel in the guidance, empty, pending and
  joined states, with no allow-list.
- **Browser:** `tests/browser/test_flow_chat_composer.py::test_composer_box_textarea_and_toolbar_match_the_board`
  pins the file input's shape (`type`, `hidden`, `accept`, `multiple`) and its name.
- **Lanes:** the `chats` and `shared` browser lanes are green (numbers in the flight
  log's leg 5 entry).
- **Leg 8 re-check** (the flight's closing gates): `chats` 162 passed (both resolver
  tests above included), `shared` 461 passed, `contracts` 644 passed and 3 skipped;
  `composer.js` still builds the input with `aria-label` "Attach images".

## Sign-Off

*(pending: the M25 Flight 4 flight-end review signs it off)*
