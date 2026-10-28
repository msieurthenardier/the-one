# Leg: transcript

**Status**: completed
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Move the message log onto the library:
- **The controls:** message bubbles and attributions (`App.ui.message`), the thinking and model-loading indicator (`App.ui.thinking`), tool traces and the thinking disclosure (`App.ui.trace`), the telemetry readout (`App.ui.telemetry`), and notice lines (`App.ui.notice`).
- **The approved looks:**
  - A4: an agent error as a danger notice with "Technical details";
  - A8: "Thinking…";
  - A15: timestamps at AA contrast;
  - A18: the telemetry's 2px focus offset;
  - B2: the thinking disclosure above its reply;
  - B3: the trace chevron and "· {n}";
  - B5: the "Operator only" chip;
  - B9: a "Stopped." line.
- **F1:** a "Copy reply" button on every finished agent reply.
- **Defects:** the model-loading interval leak (DD11 4) and the stale context-window maximum (DD11 5, with 0.3's 404).

Delete the four area renderers and their `chat.css` rules, and retarget the tests.

## Context
- **Flight decisions:** DD4 (the boundary, the class handover, the streaming source kept), DD7 (A4, A8, A15, A18, B2, B3, B5, B9; ledger rows 4, 8, 15, 18, 20-22, 24 and 30), DD8 (F1, B9), DD11 (4, 5, and 0.3's 404), DD13 and DD15 (re-author four specs).
- **After leg 04:** `App.ui.message`, `App.ui.message.attribution`, `App.ui.message.relabel`, `App.ui.thinking`, `App.ui.trace` (with `.find` and `.thinking`), `App.ui.telemetry` and `App.ui.notice` exist, with old-look defaults and options for the approved looks:
  - the trace takes `chevron: 'icon'` and `countStyle: 'dot'`;
  - the message takes `visibilityStyle: 'chip'`;
  - the thinking label comes from the caller;
  - the attribution takes `copyText` and `liveEl`.

  The streaming handle's contract: `streaming: true`, `appendText`, `tail()` returning a string, `commit(fragment, consumed)` (an empty fragment does nothing), and `finalize(fragment|null)`, which is idempotent.
- **`js/areas/chat/transcript.js`** (385 lines, leg 02):
  - `addMsg` (`:31-50`) calls `App.chat.renderMessage` and `App.chat.renderAttribution`;
  - `renderHistory` (`:59-155`) builds bubbles, traces (`App.chat.appendToTrace`), delivered results and the thinking disclosure, from the stored events;
  - the streaming core: `findSafeRenderBoundary` (`:158`), `commitSafeBoundary` (`:178-189`), `pacingTick` (`:192`), `startPacing`/`stopPacing`/`drainPacing` (`:204-224`), `finalizeStreamingBubble` (`:226-238`);
  - `showThinking`/`hideThinking` (`:240-250`, `App.chat.createThinking`/`removeThinking`);
  - `getOrCreateTrace` (`:266-290`, re-seeding from `.trace-shell[data-parent-msg-id]` with `cssEscape`);
  - `renderThinking` (`:292`), `buildToolMsg` (`:301`), `isDeliveredToolResult` / `appendDeliveredToolMsg` (`:317-333`);
  - `onAssistantChunk` (`:339-360`), which builds the empty streaming bubble with `renderMarkdown: false` plus an explicit empty text node, and its attribution with `new Date().toISOString()`.
- **`turn-frames.js`:**
  - `handleSystem` (`:22-60`) builds a hand-made "Loading model" `.msg.system.model-loading.system-model-loading` with an ungated 120 ms dot interval on `loadEl._dotTimer` (`:46`), and settles it on "Model loaded." by querying `.system-model-loading`;
  - the tool-call and tool-result branches append to traces (`:123-154`);
  - `usage` calls `App.chat.updateTelemetry(content, data)` (`:162`);
  - `cancelled` and `done` finalize.
- **`socket.js`'s `session_joined`** calls `App.chat.resetTelemetry` and `updateTelemetry` to restore the readout (`:203-217`), then fires `fetch('/api/agents/{name}/context-window')` and calls `App.chat.setTelemetryMax` (`:265-277`) with no session or generation check. That is DD11 5, plus a console 404 for a deleted agent (0.3). `session-flow.js:110` resets the telemetry.
- **The agent error:** `app.py` sends `{"type": "system", "content": "Agent error: {exc}"}`, which the client renders as a system bubble. A4 renders a frame whose content starts "Agent error: " as an `App.ui.notice({tone: 'danger'})` with a fixed headline, "The agent couldn't finish this reply.", and the raw text under a collapsed `App.ui.disclosure` "Technical details" (the DD19 pattern). Leg 06's provider wording (0.2) improves that raw text.
- **The zone relabel:** `chat.js` sweeps `.msg-attribution-ts[data-ts]` on `App.time.onChange`. It becomes `App.ui.message.relabel(messagesEl, fn)`, where `fn` uses `App.time.formatClock` and returns null for an invalid date.
- **F1's source:** `commitSafeBoundary` throws committed text away. The transcript keeps the full received text per streaming reply (a string accumulated in `onAssistantChunk`) and hands it to the attribution's `setCopy` at `finalizeStreamingBubble`. On replay, `renderHistory` passes the stored assistant content as `copyText`. One shared, visually hidden `role=status` node is placed outside `.messages[role=log]` (for example in the chat chrome), and every attribution gets it as `liveEl`.
- **B2:** the `thinking` frame arrives after the answer (the turn-frames order). The transcript inserts the disclosure **before** the bubble of the reply it belongs to, anchored on that reply's node (the latest assistant bubble of the turn, or the one whose message id matches when the frame carries one), live and on replay.
- **B9:**
  - after a `cancelled` frame, the transcript finalizes and appends `App.ui.notice({tone: 'muted', body: 'Stopped.'})`;
  - when the hold queue discarded a held message on Stop (`hold-queue.js` `cancelPendingQueued` / the Stop path in `chat.js`), it also appends "Queued message discarded.";
  - neither is stored, so a re-join shows neither.
- **Tests reaching the old classes:** about 32 `.msg`, 9 `.trace-shell`, 2 `.trace-count`, 2 `.thinking-disclosure`, 7 `.telemetry-overlay`, 11 `.t-ctx`, 9 `.context-bar`, 8 `.t-in`, 12 `.msg-operator-only` and 9 `.msg-from-peer-label` locators in `tests/browser`. `test_flow_context_overlay_thresholds.py` calls `window.App.chat.updateTelemetry` and `setTelemetryMax` (`:86`, `:92`). `[data-testid=message]` locators stay valid because the testid is passed through.
- **Contrast pins to move:** `_TELEMETRY_RESTING_OPACITY` (`tests/test_design_tokens_a11y.py:748-752`), and any `.msg-attribution-ts` audit. A15 drops the attribution timestamp's extra opacity, so audit the new pair.
- **Behavior specs to re-author:**
  - `chat-loop-hang-and-cancel.md` (B9's "Stopped." line, the thinking indicator);
  - `extended-thinking-tool-turn.md` (B2's order, B3's summary, the `.telemetry-overlay` class);
  - `stub-connector-round-trip.md` step 7 (`.msg-operator-only`, `.msg-attribution.from-agent`);
  - `agent-governance-and-search.md` step 8 (`.telemetry-overlay`, `.context-bar.warn`, `.t-ctx-pct.warn`).

## Inputs
- Leg 05b landed. The composer, sign-in and Chats list are on the library.

## Outputs
- **Bubbles:** `addMsg`, `buildToolMsg` and `appendDeliveredToolMsg` build `App.ui.message` (and `App.ui.message.attribution`) with today's testids:
  - roles, `source: 'api'`, `tone: 'error'`, `peerName`;
  - `visibility: 'operator'` with `visibilityStyle: 'chip'` and `visibilityLabel: 'Operator only'` (B5);
  - assistant bodies as `App.markdown.render(text)` Nodes.
- **Streaming:**
  - `onAssistantChunk` builds `App.ui.message({role: 'assistant', streaming: true, visibility})` and its attribution, and keeps the full source;
  - `pacingTick`, `commitSafeBoundary` and `drainPacing` use `appendText` / `tail()` / `commit(App.markdown.render(prefix), prefix.length)`;
  - `finalizeStreamingBubble` calls `finalize(App.markdown.render(tail))` and the attribution's `setCopy(fullSource)` (F1), with no Copy for an empty reply.
- **Replay:** `renderHistory` builds the same controls: assistant attributions with `copyText` from the stored content, traces through `App.ui.trace` / `App.ui.trace.find`, and the thinking disclosure through `App.ui.trace.thinking` placed before its reply (B2).
- **Thinking:**
  - `showThinking` and `hideThinking` use `App.ui.thinking({label: 'Thinking…', tone: 'assistant'})` and its `destroy` (A8);
  - `handleSystem`'s model-loading row uses `App.ui.thinking({label: 'Loading model…', tone: 'system'})`, kept as a handle in transcript state, and settles through `handle.settle('Model loaded.')`, not a class query;
  - the dots follow reduced motion, and the interval stops on any log wipe (DD11 4).
- **Traces:** `getOrCreateTrace` uses `App.ui.trace({id, label: 'Tool activity', chevron: 'icon', countStyle: 'dot'})` (B3) and `App.ui.trace.find(messagesEl, id)` after a re-join. `cssEscape` goes if nothing else needs it. `sign-in.js`'s trace lookup (it places the sign-in group after a trace shell) moves to `App.ui.trace.find`.
- **Telemetry:**
  - `chat.js` builds `App.ui.telemetry({thresholds: function () { return ctxThresholds-from-App.config; }})` in the composer's telemetry slot;
  - every `App.chat.updateTelemetry`, `resetTelemetry` and `setTelemetryMax` call becomes a handle call, with the perf marks kept in the area;
  - the A18 focus offset is 2px;
  - **DD11 5:** the context-window fetch is keyed on the session with `App.ui.util.latest()` (or a check that the bound session is unchanged), so a late response for another session is dropped;
  - **0.3's 404:** the fetch is skipped when the agent has no record in `App.store.peek('agents')`, and a non-OK response is handled without a console error;
  - a test seam `self._telemetry()` (or `App.chat.telemetry`) exposes the handle for `test_flow_context_overlay_thresholds.py`.
- **Notices:**
  - A4's agent error becomes a danger notice with its headline and "Technical details";
  - B9's "Stopped." and "Queued message discarded." are muted notices;
  - other system messages (for example "Context cleared.") stay system bubbles.
- **The zone relabel** uses `App.ui.message.relabel`.
- **The deletions:** `message-bubble.js`, `thinking-indicator.js`, `trace-shell.js` and `telemetry-overlay.js` and their script tags; the `App.chat.*` renderer exports; and the `chat.css` rules for `.msg*` (bubbles, attribution, system, operator-only, peer, the markdown descendants), `.trace*`, `.thinking*`, `.model-loading*` and `.telemetry*` / `.context-bar*`. The `chat.css` rules still in use (the pane layout, `.messages`, the header, the welcome, the drawer) stay. `.msg-pending-approval*` stays for leg 09a. Leg 04's parity test is deleted.
- **The locators** are retargeted to testids or the controls' `ui-*` classes, never relaxed; the contrast pins move to the new rules; the four behavior specs are re-authored.
- **The allowance:** any remaining chat-area row is gone. After this leg `OWNERSHIP_ALLOWANCE` holds no `js/areas/chat*` or `css/chat.css` row, and `TOTAL_USES` is lowered.
- **Catalogue:** the Message bubble, Thinking indicator, Trace, Telemetry readout and Notice rows name their consumer (the chat transcript).
- **Docs:** CLAUDE.md ("Chats pane", "Chat composer" telemetry row) and `the_one/agents.md` (the chat module map's transcript entry, the telemetry contract, the zone relabel).
- **Ledger rows 4, 8, 15, 18, 20-22, 24 and 30** confirmed, plus any new difference (for example the agent error headline's exact text).

## Acceptance Criteria
- [ ] **The four area renderers are deleted.** `git grep -n "App.chat.renderMessage\|App.chat.renderAttribution\|App.chat.createThinking\|App.chat.removeThinking\|App.chat.renderTrace\|App.chat.appendToTrace\|App.chat.renderThinking\|App.chat.renderTelemetry\|App.chat.updateTelemetry\|App.chat.resetTelemetry\|App.chat.setTelemetryMax\|App.chat.fmtTokens" -- the_one/ tests/` finds nothing.
- [ ] `git grep -nE "\.(msg|trace-shell|trace-count|thinking-disclosure|telemetry-overlay|t-ctx|context-bar|msg-attribution)\b" -- the_one/interfaces/web/static/ tests/browser/` finds no live use (comments excepted). `.msg-pending-approval*` remains until leg 09a.
- [ ] **New tests, failing first where marked:**
  - **DD11 4** — **failing today:** after "Loading model…" and a picker switch (a log wipe), no interval is left running (count with a wrapped `setInterval`). Under reduced motion the dots are static;
  - **DD11 5** — **failing today:** delay A's context-window response and 404 B's; open A, then B; release A; B's readout shows B's value (or 0);
  - **0.3:** opening a deleted agent's chat logs no console error and makes no context-window request;
  - **F1:** after a streamed reply with a code fence and a table, the attribution's "Copy reply" copies exactly the stored message content; there is no Copy while streaming; a replayed reply has one Copy; an empty reply has none;
  - **B2:** the thinking disclosure precedes its reply bubble, live and after a re-join;
  - **B9:** Stop during streaming shows "Stopped."; with a held message, "Queued message discarded." too; a re-join shows neither;
  - **A4:** a scripted provider error shows the danger notice with the headline, and the raw text inside a collapsed "Technical details";
  - **A8, A15, A18 and B3/B5:** each has a computed-style or text assertion.
- [ ] **Existing behaviour holds:** every `chats` and `chats-transcript` test, `test_markdown.py`, `test_flow_markdown_chat.py`, `test_oauth_modal_flow.py` and the streaming boundary test pass, with locators retargeted only.
- [ ] **The allowance** has no chat-area row, and `tests/test_ui_ownership.py` passes. `tests/test_area_module_size.py` passes: `chat.js` and every chat module are 800 lines or fewer.
- [ ] **Static guards:** `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass, with the moved pins and the new timestamp pair at AA.
- [ ] **A capture comparison** of every chat surface in the before set (PIL) shows only this leg's ledger rows and those of the earlier legs.
- [ ] **The four behavior specs** are re-authored to the new classes and text.
- [ ] **The full gate:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` passes (the batch B3 end), and `ruff` is clean.

## Verification Steps
1. The unit guards, `-q -x --timeout 120`.
2. `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats-transcript -x --tb=short`, then `chats`, then `tests/browser/test_markdown.py` and `test_oauth_modal_flow.py` with `-m browser`.
3. `git grep` as in the criteria.
4. **Captures:** every `needs_chat` surface, compared with the before set.
5. The full gate, once, at the end.

## Implementation Guidance
1. **The failing-first tests** (DD11 4, DD11 5, 0.3, F1, B2, B9, A4).
2. **The bubbles and attributions** (`addMsg`, tools, delivered), with the shared live node and the zone relabel.
3. **Streaming and finalize,** with the full source and F1; `--lane chats-transcript` after this step.
4. **Replay** (`renderHistory`), with traces and B2's anchoring.
5. **Thinking and model loading** (A8, DD11 4).
6. **Telemetry** (the handle, DD11 5, 0.3, A18, the seam).
7. **Notices** (A4, B9).
8. **The deletions,** the locator retargets, the contrast pins and the four specs.
9. **The allowance, catalogue, docs, captures,** then the full gate.

## Edge Cases
- **A `session_updated` re-join mid-stream** replays history and wipes the log. Every handle in the old log is dropped: `thinking` destroyed, model loading destroyed, the streaming handle finalized or discarded, the trace map reset. No timer survives.
- **The streaming bubble with operator visibility** keeps its marker chip before the tail (the leg 04 contract).
- **Delivered tool results** (`isDeliveredToolResult`) keep their attribution without a Copy. F1 is agent replies only.
- **A tool result whose trace is not in the log yet** (a reconnect): `App.ui.trace.find` returns null, and a new trace is created, as today.
- **The sign-in group's placement after a trace** (`sign-in.js`): use `App.ui.trace.find`, and keep `test_sign_in_group_sits_after_the_trace_shell_not_inside_it` passing (retargeted).
- **An agent error during streaming:** finalize the bubble, then the notice.
- **`relabel` with an invalid `data-ts`:** skip it, as today.

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat/{transcript,turn-frames,socket,session-flow,sign-in,hold-queue}.js`, `js/areas/chat.js`.
- `js/areas/chat/{message-bubble,thinking-indicator,trace-shell,telemetry-overlay}.js` (deleted), `index.html`, `css/chat.css`.
- The chat browser tests (retargets and new tests), `tests/test_design_tokens_a11y.py`, the parity test (deleted).
- Four behavior specs, `tests/_ui_ownership_allowance.py`, `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md` (if a testid's owner changes), CLAUDE.md, `the_one/agents.md`, the flight log.

## Citation Audit
- `transcript.js:31-50`, `:59-155`, `:158-238`, `:240-250`, `:266-290`, `:292`, `:301`, `:317-333`, `:339-360`. FD grep after B2 (2026-10-27).
- `turn-frames.js:22-60` (`:46` the interval), `:123-154`, `:162`. FD grep.
- `socket.js:203-217`, `:265-277`. FD read.
- `tests/browser/test_flow_context_overlay_thresholds.py:86`, `:92` and `tests/test_design_tokens_a11y.py:748-752`, from the code survey. Re-verify.
- **Legs 04, 05a and 05b have not all landed at design time.** The control contracts are taken from the leg 04 spec (the rewritten Outputs and amendments). Re-check them against the landed controls before starting.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review Amendments (cycle 1, 2026-10-27; these take precedence)
- **Order:** delete the parity test (`test_flow_chat_controls_parity.py`) in **step 1** (FD answer). The controls' contract tests cover them, and the approved looks (A8, A15, A18, B3, B5) change computed styles while the old renderers still exist.
- **B2, a per-iteration anchor** (FD answer). The live `thinking` frame carries no message id (`app.py` ~2377-2392); replay events carry `parent_message_id: "replay-msg-{i}"`, which matches no bubble. A thinking-plus-tool-call iteration has no reply bubble.
  - **Live:** the anchor is the current streaming bubble, or the last assistant bubble added since the last iteration boundary. It is cleared at `tool_call`, `tool_result`, `user`, `done` and `cancelled`.
  - **Replay:** the anchor is only the bubble built from the immediately preceding `assistant` event.
  - **No anchor:** the disclosure is appended in stream order, as today. `test_flow_chat_thinking_disclosure.py`'s no-preceding-bubble case keeps passing.
  - **New tests:** a multi-iteration turn puts each disclosure above its own iteration's reply, live and on replay.
  - `extended-thinking-tool-turn` step 4 ("interleaved … not necessarily above the answer") is re-authored.
- **B9's discarded notice is for Stop only** (FD answer; the chip's × is the operator's own cancel).
  - The Stop click handler (`chat.js` ~458-470) records `state.discardedOnStop[id] = true` when a held message existed, before it clears it.
  - The `cancelled` handler appends "Stopped." and then, if that flag is set, or a held message is still present (a Stop from another tab), "Queued message discarded.". It consumes the flag.
  - Both orders are tested. A `refreshAfterTurn` re-join right after `cancelled` wipes both notices at once (expected, since they are not stored).
- **A4's error source** (FD answer): a provider pointing at a closed loopback port, with no new mock option.
  - Detection keeps the `"Agent error: "` content prefix, which leg 06 keeps unchanged (it changes only the provider wording after the prefix; noted in leg 06).
  - "Technical details" is `App.ui.disclosure({variant: 'plain', …})` inside the notice body, with the disclosure's own styling.
- **F1:**
  - a finished reply's Copy copies its stored content (on replay) or the full received text (live), identical for a completed turn;
  - **a Stopped reply copies the received text** (FD answer); after a re-join it copies the stored text, which includes the `_[interrupted]_` marker;
  - the live non-streaming `assistant` frame (the direct path through `addMsg`) also gets `copyText`;
  - the source string resets per bubble (per iteration), not per turn;
  - the button added at finalize sits inside the `role=log`, so its arrival may be announced. That is accepted;
  - the clipboard tests grant permission in both engines, or use `copyButton`'s fallback approach (`test_ui_copy_contract.py`).
- **0.3 and DD11 5** (FD answer):
  - the context-window fetch is skipped when the join payload's `status` is not `'ok'` (the deleted-agent signal), **or** when `App.store.peek('agents')` is loaded and ok and the agent is absent. A cold deep link with an unloaded store still fetches (the F7 eager resolve is kept);
  - skipping the request is the only way to avoid the browser's own 404 console line;
  - the response is applied only if `chatState.boundId()` and the agent name are unchanged when it arrives.
- **One log wipe for DD11 4:**
  - `transcript.clearLog()` destroys the thinking handle, the model-loading handle and the stream handle, resets the trace map and empties the log;
  - the three wipe sites call it: `session-flow.js:108` (`renderPending`), `:166` (`clearConversation`) and `transcript.js:64` (`renderHistory`);
  - `hideThinking` calls `destroy()` **and** removes the node (`destroy` does not remove it);
  - the model-loading handle is also settled or destroyed on an `Agent error:` system frame, on `done` and on `cancelled`, so it never spins after a turn ends.
- **A8's labels:**
  - the thinking label is **"Thinking"**, with the control's dots as the ellipsis, so it reads "Thinking…" with static dots under reduced motion. That avoids a doubled ellipsis;
  - the model-loading label stays **"Loading model"**, matching the contract test, with no new difference.
- **A15, A18 and the contrast pins** are edits to `css/components.css`, added to Files Affected:
  - A15: `.ui-message-attribution-ts { opacity: 0.75 }` is removed, and a **new** `fg_faint` over `bg` pair at full opacity is added to `test_design_tokens_a11y.py` (no attribution-timestamp audit exists today);
  - A18: `.ui-telemetry:focus-visible` uses a 2px `outline-offset`;
  - `_TELEMETRY_RESTING_OPACITY` is a constant; only its comment and the ghost-value test's description are retargeted.
- **The telemetry testid:** the readout gets `testid: 'chat-telemetry'` (it had none), registered in `docs/ui-testid-registry.md`, and the tests retarget to it.
- **The locator scope is larger than stated.** About 55 locators use `[data-testid="message"].assistant|user|tool|system|api|error` across about 20 files:
  - the chat lanes' files and `_chats.py`;
  - `test_nav_guard.py` (`routing` lane) and `test_oauth_modal_flow.py` (`shared` lane);
  - `test_visual_snapshots.py` (pixel only, retargeted for consistency).

  A helper in `_chats.py` (for example `messages(page, role)`) carries the role-to-class mapping, and every file retargets through it. Text assertions on `[operator-only]` (`test_flow_chat_visibility_distinction.py:119`, `:190-195`) change to "Operator only" (B5), and the A8 label text changes. **The `routing` and `shared` lanes are added to the verification steps.**
- **`scripts/ui_capture.py`** retargets `.telemetry-overlay` (`:2009`) and `.messages .msg.assistant` / `.msg.system` (`:2052`, `:2087`). It is added to Files Affected; the capture comparison depends on it.
- **The AC grep is anchored** to selector and quote contexts, so `api.js`'s `d.msg` and comments do not match. For example `git grep -nE "['\"\` ](\.)?(msg|trace-shell|trace-count|thinking-disclosure|telemetry-overlay|t-ctx|context-bar|msg-attribution)\b" -- the_one/interfaces/web/static/js tests/browser`, plus a CSS check that `chat.css` has no `.msg`, `.trace-`, `.thinking-` or `.telemetry` selector except `.msg-pending-approval*` (leg 09a).
- **CSS deletions, said explicitly:**
  - `chat.css:485-487` `.model-loading` is chat-scoped and goes; `studio.css`'s `.model-loading` is a different element and stays;
  - the dead `.trace-shell .trace-body .login-required-*` rules (~`:394-452`) go;
  - `.messages .login-required-*` (`:533-540`) stays.
- **`cssEscape` stays** while `sign-in.js` uses `transcript.cssEscape` for its selectors (`:30`, `:155`, `:180`), unless leg 05b's group references removed those uses. Check after 05b.
- **The allowance:** 05c retires no row of its own. By its start, 05a and 05b have removed the chat rows and `MOVES` is empty. The criterion is a check, not an action.
- **Catalogue text:** the Message bubble and Thinking rows say leg **05c** mounts them, not 05b.
- **Behavior specs, the full list:**
  - `stub-connector-round-trip` steps **5-7** (`msg user msg-from-peer`, `msg assistant`, `[operator-only]`);
  - `agent-governance-and-search` preconditions (line 48) and step 8;
  - `extended-thinking-tool-turn` steps 4 and 5;
  - `chat-loop-hang-and-cancel` step 2 ("thinking") and step 4 ("Stopped.").
- **Capture expectations:** each surface's expected ledger rows are listed in the flight log (A4, A8, A15, B2, B3, B5, B9, F1, row 39), so an unexpected difference stands out.
- **Extra tests:** a `session_joined` restore (`update` with `max_context_tokens: 0`, then `setMax`) never zeroes a restored count. `drainPacing` appends `pendingChars` through `appendText` before `finalize`.

## Design Review
- **Developer design review, cycle 1 (Sonnet, 2026-10-27, read-only, against the landed leg 04): approve with changes.** Applied as the amendments above. FD answers:
  - B2 uses a per-iteration anchor, with stream order when there is none;
  - B9's discarded notice is for Stop only;
  - A4's error comes from a closed-port provider and keeps the prefix;
  - F1's Stopped reply copies the received text;
  - 0.3 checks `status` plus a loaded store;
  - the parity test is deleted at step 1;
  - the labels are "Thinking" and "Loading model".
- **No second cycle.** The amendments correct mechanics inside the leg's approved scope (anchoring, triggers, wipe points, test scope), with no new surface.
