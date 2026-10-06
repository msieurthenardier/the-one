# Leg: composer-and-telemetry

**Status**: completed
**Flight**: [Chats and Jump-to](../flight.md)

## Objective

Restyle the chat composer to §5.5 and move the telemetry readout into a row above it
(§5.3, DD6). Specifically:
- a two-row textarea;
- a box focus ring through `:focus-within` (A25);
- a ghost paperclip attach control;
- the agent's model id;
- Stop and Send;
- the IME-safe Enter.

It also closes **squawk 0110**: the hidden file input gets an accessible name.

## Context

- **Flight DD6** is authoritative for the composer and telemetry, and DD15 covers A25.
- **Where the markup stands.** Leg 4b extracted the composer into a DOM builder,
  `areas/chat/composer.js`, and carried it over **unchanged**. That is a single-line `input.field-input`
  (`chat-input`), a hidden file input, `chat-attach-btn` (`btn-outlined-primary`, a plus
  icon, `aria-label` "Attach image"), `chat-stop-btn` and `chat-send-btn`, all in
  `.input-area`. This leg restyles it.
- **Testids are kept**, so the about 12 test files that use them keep working: `chat-input`,
  `chat-send-btn`, `chat-stop-btn`, `chat-attach-btn`, `chat-image-input`,
  `chat-attachments`, `chat-attachments-status` and `pending-queued*`.
- **The input becomes a textarea.** Tests that `fill` then press Enter keep working, as
  long as Enter sends. Tests that read `.value` are unaffected.
- **Telemetry today** is `.telemetry-overlay`, absolute, at `right:20px; bottom:76px`,
  resting at opacity 0.7 (pinned by `_TELEMETRY_RESTING_OPACITY`,
  `tests/test_design_tokens_a11y.py` around 771), and expanding on hover or focus.

## Inputs

- After leg 4b: the composer's DOM-built markup in `areas/chat/composer.js`; `send()`,
  `performSend` and the input `keydown` (around 1556 at drafting time); the attach and
  file-input handlers; the staged-images chicklets; the pending-queued region; and
  `App.chat.renderTelemetry()` (`areas/chat/telemetry-overlay.js`).
- `css/chat.css`: `.input-area`, `.telemetry-overlay` and related rules, and
  `.pending-queued-region`.
- Leg 3b: the session state (`activeId()`, the agent in `pending` and `joined`).
- `squawks/0110-chat-image-input-no-accessible-name.md`.

## Hand-off from leg 4b (re-verified by the Flight Director after 4b landed)

- **Where things are.**
  - The composer is `static/js/areas/chat/composer.js` (108 lines), a pure DOM builder.
  - `chat.js` appends telemetry with `chromeEl.appendChild(App.chat.renderTelemetry())`
    (around 333).
  - The input `keydown` is at around 1903.
- **Telemetry shows in `pending` today**, and
  `test_flow_new_chat.py::test_telemetry_overlay_collapses_by_default` (around 359) pins
  that. AC7 hides it in pending, so that test is **re-pinned** to a joined chat, and the
  flight log records the change.
- **Squawk 0110.** The assertion at the end of
  `test_flow_chat_pane.py::test_one_h1_landmarks_and_named_controls_in_every_state`
  (around 441) currently allows `chat-image-input` as the one unnamed control. After AC6
  it is flipped to expect `[]`.

## Acceptance Criteria

- [ ] **AC1. The box** (§5.5). A wrapper (`padding: 12px 24px 20px`) holds a box with:
  - `max-width: 760px`, centred;
  - a flex column with `gap: 8px`;
  - `background: var(--surface)`, `border: 1px solid var(--border)`,
    `border-radius: var(--radius-md)`;
  - `padding: 10px 12px`.

  The staged-images chicklets and the pending-queued chip stay **above** the box, inside
  the wrapper, and keep their testids and behaviour.
- [ ] **AC2. The textarea.**
  - `<textarea rows="2">` with testid `chat-input`, `resize: none`, `border: 0`,
    `background: transparent`, `font-size: var(--font-size-body-lg)`, and
    `outline: none` **only** because the box carries the ring.
  - A visually hidden `<label>` "Message" is associated through `for`/`id`, and
    `aria-label` is removed (a real label).
  - The placeholder is "Message {agent}…" for the current or pending agent, and
    "Message…" with no agent. It updates on pick and join.
  - `enterkeyhint="send"`.
- [ ] **AC3. Keys.**
  - **Enter** (no Shift, not composing) calls `preventDefault` and sends.
  - **Shift+Enter** inserts a newline.
  - Enter while `e.isComposing || e.keyCode === 229` does nothing; the IME commits.
  - `aria-keyshortcuts="Enter"` stays on Send.
  - A test: Shift+Enter makes a two-line value; Enter sends both lines as one message.
- [ ] **AC4. The focus ring** (A25). `.composer-box:focus-within` shows the app's pinned
  focus form (`outline: 2px solid var(--accent); outline-offset: 2px`). The ring is
  visible when the textarea **or** a toolbar button has focus. A test reads the computed
  outline on the box with the textarea focused.
- [ ] **AC5. The toolbar** is a flex row, centred, with `gap: 8px`:
  - **Attach.** `btn-ghost btn-sm`, icon only, the `paperclip` icon (added to
    `js/icons.js` with Lucide geometry, unless leg 4 or 6 already added it),
    `aria-label="Attach images"`, testid `chat-attach-btn`.
  - **The model id.** A `<span>` (testid `chat-model`) at 11px, `--fg-muted`, in
    `--font-family-mono`. It holds the agent's `llm_model` from `App.store` `agents` and
    is empty when unknown.
  - **Stop.** `btn-muted-destructive`, testid `chat-stop-btn`, behaviour unchanged.
  - **Send.** `btn-filled-primary`, `margin-left: auto`, the `send` icon plus the label
    "Send", testid `chat-send-btn`.
  - The model id meets 4.5:1 on `--surface` in both themes. Gate it if the pair is not
    already gated.
- [ ] **AC6. Squawk 0110.** The hidden file input carries `aria-label="Attach images"`.
  - A resolver-backed test (`tests/browser/_a11y_resolve.js`, as the squawk asks) finds no
    unnamed control on `#chats`, with a chat open, in either theme.
  - The squawk file gets its Corrective Action, Verification and status (`completed`,
    sign-off at the flight review).
  - Any allow-list that excused `chat-image-input` (in leg 4b's AC12, or an a11y probe
    test) is removed.
- [ ] **AC7. The telemetry row** (§5.3).
  - The readout moves out of the absolute overlay into a flex row directly above the
    composer box: `justify-content: flex-end; padding: 0 24px`, inside the wrapper.
  - It shows only in `joined`, not in `pending` or the new-chat state (§5.4).
  - Its content and the hover and focus expansion are unchanged: the `ctx` bar, `in` and
    `out`.
  - It keeps its resting opacity (0.7), so the `_TELEMETRY_RESTING_OPACITY` pin and
    `test_telemetry_ghost_value_holds_annotation_floor` stay valid. If the opacity
    changes, the pin is updated in the same edit, never deleted.
  - `test_flow_context_overlay_thresholds.py` and `test_flow_usage_restore.py` stay green,
    or are updated only for the position change, with the reason in the flight log.
- [ ] **AC8. No regression** in send, attach, stop, the hold queue or streaming. The chats
  lane is fully green.
- [ ] **AC9. Gates.**
  - `make lint` and format;
  - the static guards: `test_ui_guards` (no new sink), `test_token_definitions` and
    `test_design_tokens_a11y`;
  - `make test-unit`;
  - the lanes `chats`, `shared` (`TEST_TIMEOUT=3600`) and `contracts`
    (`THE_ONE_REQUIRE_WEBKIT=1`; only if a `ui/` file changed). Each runs through
    `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1`.
  - The numbers go in the flight log.
- [ ] **AC10. Docs.**
  - `docs/ui-control-inventory.md`: the "Chat composer" row stays "not yet defined" (the
    next mission's chat surface), with its note updated: it now meets §5.5's look, but it
    is not a library control.
  - The telemetry row note.
  - `the_one/agents.md`: the chat composer conventions (Enter and Shift+Enter, IME, the
    `focus-within` ring).

## Verification Steps

- The lanes in AC9.
- **A manual pass** at 1440 and 1024, in Light and Dark, on a dev instance (port 8486 or
  higher, scratch data dir): the composer matches §5.5, and the ring is visible.
- **Falsify AC4 once:** remove the `:focus-within` rule, and watch the test fail.

## Edge Cases

- **Paste of multi-line text:** it stays multi-line, and Enter sends.
- **A disabled input** (health banner, setup incomplete, `rebinding`): the textarea is
  disabled and the box shows no ring. The placeholder reflects the reason only where it
  does today.
- **Very long input:** the textarea grows to at most about 8 lines, then scrolls. A
  `max-height` stops it pushing the message log out.

## Files Affected

- `static/js/areas/chat.js` or `areas/chat/chat-pane.js` (the composer markup and keys),
  `areas/chat/telemetry-overlay.js` (placement), and `static/js/icons.js`.
- `static/css/chat.css`.
- Tests:
  - the chats-lane files touching the composer, only where the markup changed;
  - a new `test_flow_chat_composer.py`;
  - `tests/test_design_tokens_a11y.py`.
- `squawks/0110-chat-image-input-no-accessible-name.md`, `docs/ui-control-inventory.md`
  and `the_one/agents.md`.
