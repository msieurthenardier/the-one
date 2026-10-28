# Leg: step-limit-continue

**Status**: completed
**Flight**: [Chats, and closing every count to zero](../flight.md)
**Origin**: HAT step 5 (operator, 2026-10-28): "in our message we have a 'continue' button that just sends 'continue' to the agent to keep going." New behaviour, so it goes through the fix-vs-feature gate. The FD's proposed defaults are stated in the HAT turn.

## Objective
The web chat's step-limit notice gains a **Continue** button. Clicking it sends the text `continue` to the agent as an ordinary user message through the normal send path. The agent then resumes with its stored tool history and a fresh step budget.

## Context
- **The notice** (leg 06): a broadcast-only `step_limit` frame renders a muted `App.ui.notice`. Its testid is `chat-step-limit`, its link `chat-step-limit-link` ("Max iterations", to `#agents/{name}`). It comes from `turn-frames.js` / `transcript.js`; find where it is built. It is never stored, so a reload or re-join shows no notice and therefore no button.
- **The send path.** Use `ctx.send.send(raw)` or the equivalent, not a hand-built frame. When idle it sends; when a turn is running it holds the message in the multi-message queue (leg 10a). A blocked composer (a deleted agent or a health banner) cannot send; the button follows the same rule.
- **`App.ui.notice`.** Check whether it accepts an action slot. If not, the area appends a library button (`App.ui.button`, small, secondary) inside the notice body. That is not a new owned class. If a notice option is needed, it is a library change with catalogue and contract tests.

## Design (to confirm at design review)
- **The button.** "Continue" (`chat-step-limit-continue`), placed after the notice text and the settings link.
- **Click.** The button is disabled at once, so a double click sends once, and `send('continue')` runs. The button is then removed. The notice text stays.
- **Only the latest notice is live.** A new turn starting, from a Continue click, a typed message or a queue drain, removes any live Continue button. An older notice in the log never shows one, which follows from removal, and a reload has no notice at all.
- **Blocked or busy.**
  - Blocked: the button is disabled while `computeBlocked()` is true and re-enables when it clears, following `applyComposerState`.
  - Busy: a click still works and queues the message, like typing it would.
- **Focus.** After a click, focus moves to the message box, as after a send.
- **Connectors and the CLI** are unchanged: there is no button on a platform.

## Acceptance Criteria
- [ ] At a step limit in the web chat, the notice shows "Continue" beside "Max iterations". Clicking it sends exactly one user message, `continue`, which appears as the operator's bubble and is stored. The agent's next turn runs, and the button is gone.
- [ ] A new turn removes the live button. A reload or re-join shows no notice and no button. A double click sends one message. A blocked composer disables the button.
- [ ] The button is a real `button` named "Continue" and keyboard operable, with focus after a click in the message box. Contrast holds in both themes.
- [ ] Browser tests, using the step-limit mock seed as in `test_step_limit_web.py` or the browser equivalent, cover the click, a single send, removal on a new turn, the blocked state and focus. The chats lanes pass. CLAUDE.md and `the_one/agents.md` (the step-limit notes) are updated. Ledger row 51 is added. The `agent-step-limit-notice` behavior spec gains a step for the button (a deliberate re-author, noted).

## Verification
`--lane chats-transcript -x`, `--lane chats -x`, and the contracts lanes if `App.ui.notice` changes. Then the HAT re-walks step 5.

## Design Review Amendments (cycle 1, Developer/Sonnet, 2026-10-28: approve with changes; these take precedence)
- **Send entry.** `send.js` gains `sendText(text)`.
  - It shares `send()`'s guard block (idle, joining, blocked, closed or rebinding socket, a full queue) and goes through the hold path when busy.
  - It never touches the composer text or the staged images (10c's drafts stay intact).
  - It returns `true` only when the text was sent or held.
- **Click.** The button is disabled at once, then `sendText('continue')` runs.
  - On `true`: the button is removed and focus moves to the message box.
  - On `false`: the button is re-enabled. At the queue cap it stays, beside the queue-full note.
- **Live-button handle.** It lives entirely in `transcript.js` (`liveContinue`). It is dropped when:
  - `addMsg('user', …)` runs: a typed message, a queue drain, Continue itself, or a `user` frame from another tab or a peer;
  - `clearLog()` runs (re-join, replay, 10c's switches);
  - a new step-limit notice replaces it.
  A repeated step limit after Continue carries a fresh live button and the old one is gone; add a test.
- **No button when it can't be used.** No button is rendered when the active session's hold queue is non-empty at notice time: the queue drains immediately. None is rendered when the composer is already blocked at notice time.
- **Blocked sync.** `applyComposerState` in `areas/chat.js` gets one line, `ctx.transcript.setContinueEnabled(!computeBlocked())`, which merges around 10c's changes. A click while blocked is also a no-op, through `sendText`'s return value.
- **Markup.** The button is an `App.ui.button({variant:'secondary', size:'sm', text:'Continue', testid:'chat-step-limit-continue'})`. It sits inside an area-owned wrapper span, `.chat-step-limit-actions`, with one small `chat.css` rule. No `ui-notice*` or `btn-*` selectors appear in area CSS, so no library or catalogue change is needed.
- **Copy.** The notice text is unchanged.
- **Tests.**
  - Existing: the notice tests asserting exact `to_have_text(_STEP_TEXT)` switch to asserting the text node, or `to_contain_text`, deliberately.
  - New, in `test_flow_chat_transcript_library.py`, chats-transcript lane:
    - a click stores exactly one `continue` user message, and the button goes;
    - a double click sends once;
    - a typed draft and a staged image survive the click;
    - a typed message removes the button;
    - a blocked (deleted-agent) chat renders no button;
    - focus lands in `chat-input`;
    - a repeated step limit shows a fresh button;
    - no button appears when the queue is non-empty.
  - Registry: add `chat-step-limit-continue` to `docs/ui-testid-registry.md`.
- **Behavior spec.** Re-author `agent-step-limit-notice` step 1's text assertion and add a Continue step, with the reason noted. The FD re-runs the spec after the HAT changes.
- **Sequencing.** 10d is implemented after 10c lands. Its footprint is `transcript.js`, `send.js`, one `chat.js` line, `chat.css` and tests.
- **Status:** ready.
