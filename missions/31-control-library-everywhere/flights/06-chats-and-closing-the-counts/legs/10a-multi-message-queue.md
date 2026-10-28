# Leg: multi-message-queue

**Status**: ready
**Flight**: [Chats, and closing every count to zero](../flight.md)
**Origin**: HAT step 3 (operator, 2026-10-28). Operator choice: "Queue several". A behaviour change, so it goes through the fix-vs-feature gate.

## Objective
While a turn runs, every Send is held: any number of messages, kept in order, each shown as its own removable "Queued" chip above the composer. When a turn finishes (`done`), the first held message is sent through the normal path. Each later turn's end sends the next. A second Send no longer does nothing.

## Context
- **Today** (one slot, since Mission 9 F09-04):
  - `state.pendingQueuedMessages[sid]` holds one string (`areas/chat.js` ~43).
  - `send.js` ~112-131 ignores a second hold (`if (state.pendingQueuedMessages[active]) return;`).
  - `hold-queue.js` shows one `App.ui.chip` in `ctx.composer.slots.queued` (the `pending-queued-region` live region).
  - `send.js` ~70 (the `done` path) sends the held message.
  - `turn-frames.js` ~186 and ~217-231 handles `done` and Stop. After Stop, the notice is "Queued message discarded." (`transcript.js` ~467-478, testid `chat-discarded`).
  - `socket.js` ~93 clears every held message on a socket reset, and ~254-260 re-shows the chip on re-join.
  - `session-flow.js` ~89, 130, 145 and 315-326 discards on a conversation switch or start (`'The queued message was discarded.'`).
- **Ledger rows** this touches: 7, 24, 40 and 42.
- **Tests:**
  - `tests/browser/test_flow_chat_queued_render.py`;
  - the composer and queue tests in `test_flow_chat_composer.py`;
  - `test_flow_chat_start_flow.py` / `_start_reconnect.py` (held while starting);
  - `tests/browser/_chats.py` helpers.
  Some of these pin the one-slot rule. Invert or rename those deliberately (rename over delete-and-readd).

## Design (to confirm at design review)
- **Storage.** `pendingQueuedMessages[sid]` becomes an array of strings, in order. Every reader and writer changes together. Grep `pendingQueuedMessages` across `areas/`.
- **Holding.** A Send while busy appends to the array (trimmed, non-empty; images still cleared as today, since attach-while-busy stays out of scope). It clears the input and adds a chip.
- **Chips.** One `App.ui.chip` per held message, in order, in the existing region.
  - Each has the "Queued" lead and its own remove control. Name it so the operator can tell them apart, for example "Cancel queued message 2 of 3"; settle the exact naming at review.
  - Removing a chip drops that entry only. Focus moves to the next chip, else the previous one, else the message box.
  - The region stays a persistent `aria-live` region.
- **Draining.** On `done`, shift the first entry and send it through the normal path. The remaining chips stay. The next `done` sends the next entry. An agent error (`turn-frames.js` ~56) keeps today's behaviour for whatever is held; decide at review whether the whole queue drops.
- **Stop.** The operator's Stop discards every held message. Use one muted notice: "Queued message discarded." for one, "{n} queued messages discarded." for several.
- **Conversation switch, start or socket reset.** Discard all held, as today. The `session-flow.js` system line pluralises the same way.
- **Re-join.** Re-render every held chip in order.
- **Cap.** None requested. Raise it at review if an unbounded queue is a risk (it is client memory only).

## Acceptance Criteria
- [ ] With a turn running, three Sends produce three chips, in order, with the input cleared each time. Nothing goes to the server until `done`.
- [ ] At each `done`, exactly one held message is sent, the first, and its chip goes. The rest stay in order until their turn.
- [ ] Removing the middle chip drops only that message, and focus lands per the rule above.
- [ ] Stop with several held discards all of them and shows "{n} queued messages discarded."; with one held it still shows "Queued message discarded.". Switching conversation discards all of them.
- [ ] Each chip's remove control has a distinct accessible name. The region stays live and the chip count is announced sensibly.
- [ ] Tests that pinned the one-slot rule are inverted or renamed, and new tests cover order, drain, middle-remove and Stop. The chats lanes pass. CLAUDE.md "Chat composer" and `the_one/agents.md` describe the queue. Add ledger row 48.

## Verification
`THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats-transcript -x` and `--lane chats -x`; the static guards; then the HAT re-walks step 3.

## Design Review Amendments (cycle 1, Developer/Sonnet, 2026-10-28: approve with changes; these take precedence)
- **Every reader and writer of the slot converts together.** All checks become array-aware: `q && q.length`, and the key is deleted when the array empties (an empty array is truthy in JS). The sites:
  - `send.js`: ~70 `sendHeld`, ~107 the `/reset` discard (resets discard the whole queue), ~121-122 the hold.
  - `hold-queue.js`: all of it.
  - `areas/chat.js` ~474-475: the Stop click.
  - `turn-frames.js`: ~56 the agent error, ~186 `done`, ~221 `cancelled`.
  - `socket.js`: ~93 the reset, ~254-263 the re-join.
  - `session-flow.js`: ~89, 130, 145 and 315-326. The returned `held` becomes an array, and the "discarded" line is pluralised from its count.
- **Agent error.** An agent error drops the whole queue with the muted notice: "Queued message discarded." for one, "{n} queued messages discarded." for several. Nothing is auto-sent after a failed turn. This is an acceptance criterion with a test.
- **Drain, re-join and reconnect.**
  - `sendHeld` sends the first held message and re-renders the remaining chips. It does not clear them all.
  - On a re-join that finds the chat idle, the first message is sent and the rest stay chipped.
  - A drain attempt while the socket is closed or `state.rebinding` keeps every held message. Add a reconnect test.
- **Stop count.** The Stop click stores the count, `state.discardedOnStop[sid] = n`, because the queue is gone by the time `cancelled` arrives. A Stop from another tab uses the then-current length.
- **Chip names.**
  - With one held message, keep "Cancel queued message", so existing tests and labels stay stable.
  - With n > 1, each reads "Cancel queued message {i} of {n}". The names are recomputed on every change.
  - Each chip keeps the testids `pending-queued` and `pending-queued-cancel`, plus `data-index`.
- **Live region.** One persistent polite `aria-live` region holds a visually hidden status line, "{n} messages queued" (or "1 message queued"), updated on every change. This replaces "announced sensibly".
- **Cap of 10.** At the cap, Send does nothing and the text stays in the composer. A short muted note, "Queue is full (10)", shows under the composer.
- **Focus on remove.** Focus goes to the next chip, else the previous one, else the message box. Tests cover a middle remove and a last remove.
- **Unchanged and out of scope.**
  - A message held while the agent is paused for sign-in still drains at `done`.
  - Staged images are still cleared on hold (attach while busy stays out of scope; existing behaviour).
  - "A held message is trimmed, and an empty one is not held" keeps its test.
- **Tests to invert or extend:**
  - browser: `test_flow_chat_transcript_library`, `_composer`, `_composer_library`, `_queued_render`, `_start_flow` (add two Sends during `starting`), `_start_reconnect`, `_live_updates`;
  - `tests/behavior/chat-loop-hang-and-cancel.md`: re-author it if it states the one-slot rule or the old notice text;
  - `App.ui.composer`'s contracts, if one pins a single chip.
- **Lanes:** `chats-transcript`, `chats`, `contracts-chat`, and whichever lane holds `test_flow_chat_live_updates.py` (check with `--list`).
- **Status:** ready. No second review cycle for 10a.
