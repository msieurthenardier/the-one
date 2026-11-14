# Leg: turn-work-in-chat

**Status**: completed
**Flight**: [One work line per chat turn](../flight.md)

## Objective
Render every web chat turn as one work group and one reply, live and on replay, through a new chat module `areas/chat/turn-work.js` built on `App.ui.turnWork`, with the core flow tests and the retired-id sweep. (The remaining flow tests and the streaming-bubble test rewrites are leg 3, `turn-work-tests`.)

## Context
- Flight DD2 to DD9, DD11 and DD12 are this leg's rules. Read them in the flight artifact first; this leg does not restate their reasons.
- Leg 1 added the control `App.ui.turnWork` (states, count, activity, preview, items with `setContent` and `remove`, `stopDots`, the "Operator only" chip). Its artifact (`01-turn-work-control.md`, "The control") is the API this leg calls. If leg 1's flight-log entry records a different name for anything, the log wins.
- Leg 3 (`turn-work-tests`) finishes the test work. Leg 4 (`turn-work-cleanup`) deletes the code this leg leaves without a caller (`stream-commit.js`, `visual-stream.js`, `App.ui.trace`, streaming-only library pieces). **Do not delete those files in this leg**, and do not edit files under `js/ui/`. Where this artifact says "leg 3" for a deletion, a capture surface, a behavior spec or a doc, read "the cleanup leg".
- Nothing is committed in this leg.

## Terms
- **Turn**, **pass**, **narration**, **pending text**: as in the flight artifact's "Terms".
- **Open group**: the current turn's `App.ui.turnWork` handle, while the turn has not been closed.
- **Latest narration**: the most recent narration item of the open group. It is shown as plain text until it can no longer become the reply (flight DD4).

## Inputs
- Leg 1 landed: `App.ui.turnWork` exists and its contract tests pass.
- The chat modules as they are on the branch: `transcript.js` (667 lines), `turn-frames.js`, `socket.js`, `session-flow.js`, `send.js`, `sign-in.js`, `chat.js`.

## Outputs
- `the_one/interfaces/web/static/js/areas/chat/turn-work.js` (new): `App.chat.turnWork.create(ctx)`.
- `transcript.js`, `turn-frames.js`, `socket.js`, `session-flow.js`, `send.js`, `sign-in.js`, `chat.js`, `index.html` changed to use it.
- `tests/browser/_chats.py` helpers for a turn's group.
- New and rewritten flow tests; lane lists updated.
- `docs/ui-testid-registry.md` and `tests/test_nav_helper.py` updated for the ids this leg adds and retires.

## Design

### The module
`App.chat.turnWork.create(ctx)`, the house pattern (`'use strict'` IIFE, ES5, one shared `ctx`, call-time access to other modules). Created in `chat.js` after `ctx.transcript` and before `ctx.send`; its `<script>` tag goes after `transcript.js` in `index.html`. Add `self._turnWork` beside the other test seams in `chat.js`.

It owns: the open group's handle, the pending text and its visibility, the tool-call count, the latest-narration item and every narration's source text, the history array kept for a re-render, and whether replay closed the trailing turn.

Suggested interface (names may change; record the final ones in the flight log):

| Call | From | Does |
|---|---|---|
| `begin()` | the send (`send.js:63`), the start (`session-flow.js:345`), a routine `user` frame, the join with `is_processing`, "Model loaded." | `ensureOpen('working')` (below), then: an empty group that was hidden for "Loading model" is shown again and moved to the end of the log (an empty group holds no widget, so moving it is safe). |
| `onText(data, whole)` | `assistant_chunk` (`whole` false), `assistant` (`whole` true) | `ensureOpen('working')`. Appends to the pending text (a whole frame first folds any pending text, then sets it). Keeps the first chunk's `visibility`. Updates the preview (see "The preview"). |
| `onThinking(data)` | `thinking` | `ensureOpen('working')`. Adds a thinking item. |
| `onToolCall(data)` | `tool_call` | `ensureOpen('working')`. Folds the pending text as narration. Adds the tool row, raises the count, sets the activity to the tool's name. |
| `onToolResult(data)` | `tool_result` | A delivered result (`transcript.isDeliveredToolResult`) stays a top-level bubble after the group, as today. Any other result is added as a tool row. Clears the activity. |
| `onDone()` | `done`, **before** the held-message send | If the group is `working`: promote the reply (flight DD4), set `done`, remove the group if it is empty. In any other state: nothing. Closes the turn. |
| `onCancelled()` | `cancelled` | Fold, set `stopped`, render the latest narration, close the turn. With no open group: nothing (the caller still adds the notices). |
| `onSystemEnd()` | `handleSystem`'s final branch (any `system` frame that is not one of the two model-loading ones) | Fold. An empty group is removed; a group with items is set to `error` and its latest narration rendered. Closes the turn. With no open group: nothing. |
| `onStepLimit()` | `step_limit` | Fold, set `step-limit`, render the latest narration. The `done` that follows does nothing. |
| `onAuthRequired()` | `sign-in.js::onAuthRequired` | `ensureOpen('sign-in')`. Fold, set `sign-in`. The latest narration stays plain (the turn may resume). Returns the group's element for the sign-in block's placement. |
| `onAuthResolved()` | `sign-in.js::onAuthResolved` | Sets the same group back to `working`. |
| `onUserEvent()` | **live only**, before the user bubble is added: the `user` frame in `turn-frames.js`, the local send (`send.js` `performSend`, which also carries the held-message send) and the start (`session-flow.js:340`) | Closes any open turn: render its latest narration in place; a group still `working` gets `stopDots()` and is no longer the open group. Drops the kept history and the "replay closed the trailing turn" mark. Replay never calls it (see "Replay"). |
| `stopClicked()` | `chat.js::stopTurn` | `stopDots()` on the open group. No state change. |
| `dropEmpty()` | a failed start (`session-flow.js:357`) | Removes the open group if it is empty. |
| `hideForLoading()` | `transcript.showModelLoading` | Hides the open group if it is empty; a group with items is untouched. |
| `groupEl()` | `sign-in.js` | The open group's root, or the most recent group's root, or null. |
| `replay(history, agentLabel, opts)` | `transcript.renderHistory` | Renders the stored events, grouped by turn (see "Replay"). |
| `reset()` | `transcript.clearLog` | Destroys every group handle and clears all state except the kept history. |

**`ensureOpen(state)`: the one way a group is opened.** Every path that needs the open group goes through one internal function, so no path can open a second group for a turn:
1. If there is an open group, return it.
2. Otherwise, if replay closed the trailing turn (the mark is set), render the history again with that turn open in `state` (see "A trailing turn that is still alive"), clear the mark, and return the group the re-render opened.
3. Otherwise create a group in `state` at the end of the log.
`onToolResult` uses it too, but only for a result that goes into the group; a delivered result stays top-level and opens nothing. `begin()` after a local send or a `user` frame always reaches step 3, because `onUserEvent` cleared the mark first.

"Fold" means: if the pending text is non-empty (has a non-whitespace character), render the previous latest narration in place (it is now superseded), add the pending text as a new plain narration item, make it the latest, and clear the pending text and the preview. Whitespace-only pending text is discarded.

"Render in place" means `item.setContent(transcript.renderMarkdown(source))`, once per item. `renderMarkdown(text)` is a new one-line seam in `transcript.js` (`App.markdown.render(text, mdOpts())`), so the chart and widget draw functions and the widget key counter stay in the transcript.

"Promote the reply" (flight DD4), at a `done` in `working`:
1. Pending text non-empty: render the latest narration in place, then `transcript.addMsg('assistant', pending, agentName, {visibility})`.
2. Otherwise, a latest narration exists: remove its item from the group and `addMsg` its source text.
3. Otherwise: no reply bubble.
The agent name is `state.currentAgentName || 'agent'`, as today.

**Order of rendering.** Within a turn every narration is rendered before the reply, and each text exactly once. This is what keeps a widget's key (`transcript.js:95-114`) equal between a live turn and its reload. Do not render a text twice, and do not move a rendered node.

**Thinking order.** Live, a pass's thinking arrives after its text and before its tool calls, so `onThinking` adds the thinking item while that pass's text is still pending; the fold at the tool call then puts the narration after it. For the final pass the thinking item is in the group and the text becomes the reply.

**Connector chats** (flight DD7): the group gets `setOperatorOnly(true)` as soon as an item with `visibility === 'operator'` is added. Tool rows inside the group are built without their own chip: call `transcript.buildToolMsg` with no `visibility` for a row that goes into the group.

**What the control gives and what the module tracks.** Hide a group with `handle.el.hidden` (the global `[hidden]` reset applies); move an empty group with `appendChild`; remove one with `el.remove()` plus `destroy()`. The module tracks each item's kind and source text itself. The module never names a class the control owns (`tests/test_ui_ownership.py`); it reaches the group through the handle.

### The preview (flight DD3)
On every text update call `setPreview(pendingText)`; the control keeps the tail. While the pending text is inside an unclosed fenced block whose info string is `chart` or `widget`, pass "Drawing a chart" or "Building a widget" instead. A small local function decides this by counting fence lines (lines that start with three backticks) in the pending text: an odd count means a fence is open, and the last opening fence's info string names it. Do not use `visual-stream.js` for it.

### What leaves `transcript.js`
Removed in this leg, because the new module replaces them: the streaming wiring (`stream`, `streamAttr`, `streamSource`, `currentStreamingVisibility`, `onAssistantChunk`, `finalizeStreamingBubble`, `resetStream`, `clearStreamingVisibility`), the "Thinking" line (`showThinking`, `hideThinking`, `thinkingHandle`), the trace bucket (`traceShells`, `getOrCreateTrace`, `traceShellFor`, `resetTraceShells`), `renderThinking`, and the iteration anchor (`iterationAnchor`, `clearIterationAnchor`). `clearLog` calls `ctx.turnWork.reset()` in their place.

Kept: `addMsg`, `addUserEvent`, the scroll pin, `renderHistory` (see below), the model-loading line, `buildToolMsg`, `isDeliveredToolResult`, `appendDeliveredToolMsg`, the notices, `drawChart`, `drawWidget`, `clearLog`.

Before removing each name, grep for its callers (`grep -rn '<name>' the_one/interfaces/web/static/js tests scripts`) and move every one. The known outside callers are in the Citation Audit. The `<script>` tags for `visual-stream.js` and `stream-commit.js` stay until the cleanup leg.

The new module has no HTML-string sinks (`tests/test_ui_guards.py` treats `areas/chat*` as sink-free): DOM APIs and `textContent` only.

### Live frames (`turn-frames.js` and the other callers)
Replace each old call with the new one. In `handle(data)`:
- `user`: `onUserEvent()`, then `addUserEvent`; a routine frame then calls `begin()` where it calls `showThinking()` today.
- `assistant_chunk` / `assistant`: `onText`. No bubble is added here any more.
- `thinking`, `tool_call`, `tool_result`: the calls above. The note and routine drawer refreshes on `tool_result` stay.
- `step_limit`: `onStepLimit()`, then the notice as today.
- `done`: `dropModelLoading()`, then `onDone()`, **then** the held-message logic (the reply must be in the log before `sendHeld` adds the queued bubble).
- `cancelled`: `onCancelled()`, then the notices as today.
- `handleSystem`: "Loading model..." calls `showModelLoading()` (which calls `hideForLoading()`); "Model loaded." settles the line and calls `begin()` where it calls `showThinking()` today; every other content calls `onSystemEnd()` before the error notice or system line is added.

Elsewhere:
- `send.js` `performSend` (around lines 56-63) and the start in `session-flow.js` (around 340-345): `onUserEvent()` before the user bubble, `begin()` after it.
- `session-flow.js:357` (failed start): `dropEmpty()`.
- `socket.js:89` (socket closed): nothing (the group stays as it is, dots running, until the re-join's replay rebuilds the log). This is a known change from today, where the "Thinking" line is dropped at once; it is on the HAT list.
- `socket.js:215` (`session_joined`, before the replay): nothing; when the join renders history (`socket.js:221`), `clearLog` resets the module. When it does not (a start's join that keeps the optimistic bubble), the group opened at the start is still the open group.
- `socket.js:250-252`: `begin()` when `is_processing` (a start's join reports it true, `app.py:3716`). It reuses the open group (the start's, or the trailing turn replay left open). When `is_processing` is false and the join did **not** render history, call `dropEmpty()`, so an empty "Working" line from a start whose turn never ran cannot stay.
- `chat.js:499` (Stop click): `stopClicked()`.
- `sign-in.js:242-251`: the sign-in block is inserted as the next sibling of `ctx.turnWork.groupEl()` when that node is a child of the log; otherwise appended. It is never put inside the group.
- `sign-in.js:275-277` (`onAuthRequired`): `onAuthRequired()`. `onAuthResolved` calls `onAuthResolved()`.
- The "Resuming…" system line (`sign-in.js:261-266`): keep it as it is. The resumed items land in the group above it; the HAT judges whether it should go.

### Replay (flight DD8)
`transcript.renderHistory(history, agentName, opts)` keeps its wrapper (the `aria-busy` flag, `clearLog`, `historyAgent`) and calls `ctx.turnWork.replay(history, agentLabel, opts)`. `opts.trailing` is `'closed'` (default), `'working'` or `'sign-in'`.
- `socket.js` passes `'working'` when the join's `is_processing` is true. Read the flag before the render (today it is read after, at line 250).
- Group the events by turn: a `user` event starts a turn; events before the first `user` event form one leading turn.
- Replay adds user bubbles through `transcript.addUserEvent` and never calls `onUserEvent`; it manages its own turn boundaries.
- For each turn, in stored order: `user` → the user bubble; `assistant` → a narration, except the turn's reply (below); `thinking` → a thinking item, placed **above** the text of the same stored message (the codec stores a message's text first, then its thinking; live order is the reverse); `tool_call` / `tool_result` → tool rows, with the delivered-result rule; `system` → a system line after the group, except the two model-loading strings, which are skipped as today.
- A closed turn: its reply is its last non-empty `assistant` event. Every other text is rendered narration. The group's state is `done`; an empty group is not created at all.
- An open trailing turn (`'working'` or `'sign-in'`): no reply; all texts are narration, the last one left plain as the latest; the group is the open group, in that state.
- Because the reply is the last text but may not be the last event, render a closed turn in two passes: first decide which `assistant` event is the reply, then walk the events in order, rendering narrations as they come and the reply bubble after the turn's last event. Every narration is rendered before the reply, as live.
- Keep the `history` array and `agentName` after a `'closed'` replay whose trailing turn has at least one `assistant`, `thinking` or tool event, and mark "replay closed the trailing turn".
- **A trailing turn that is still alive.** This is step 2 of `ensureOpen`: a live `assistant_chunk`, `assistant`, `thinking`, `tool_call`, `tool_result` or `auth_required` arrives, there is no open group, and replay closed the trailing turn. `ensureOpen` calls `transcript.renderHistory` again with the kept array and `trailing: 'sign-in'` or `'working'`, then the frame is handled as usual.
  - "Model loaded." keeps its existing gate (`turn-frames.js:36-38`: it starts the line only when the session is in flight). On a resume join the session is not marked in flight (`socket.js:253-255`), so "Model loaded." opens nothing there and the first text or tool frame triggers the re-render. Flow item 16 asserts the outcome (one group), not which frame opened it. Item 12's frames are sent with `emit_frame` and no `user` frame before them.
  - No recursion: the second render uses an open trailing turn, so it sets no mark, and `ensureOpen` clears the mark before it returns.
  - The re-render is a full `clearLog`, so anything in the log that is not in the history goes: a "Model loaded." or "Resuming…" line, an earlier notice, a sign-in block. That is the same as any re-join. A sign-in block is rebuilt by `sign-in.js::onAuthRequired` right after, because the frame is handled after the re-render; check that its stored references (`group._consentBlock`, `loginFlows`) do not point at the detached node.
  - It also collapses a group the operator had opened. It can only happen on the first live frame after a join, so that is accepted.
  - The mark and the kept array are dropped by `onUserEvent` and by the next replay.

### Testids and the registry
- The group: `testid: 'turn-work'`, `previewTestid: 'turn-work-preview'`. Register both in `docs/ui-testid-registry.md`.
- Retire `trace-shell`, `thinking-disclosure` and `thinking-indicator`: move them to the registry's "Retired testids" table and add them to `RETIRED_SELECTORS` in `tests/test_nav_helper.py`. `tests/test_ui_guards.py` checks both directions (every testid in the JS is registered, every registered testid is in the JS), so the registry and the JS change together.
- After that, no file under `tests/browser/` may name the retired ids. Assert "the old shape is absent" through the new helpers (a turn has exactly one group and exactly one assistant bubble).
- `scripts/ui_capture.py:2398` waits on `thinking-indicator`; change that one ready selector to the group's testid so the capture tool keeps working. The new capture surfaces are the cleanup leg's.

### Tests
- **Helpers** in `tests/browser/_chats.py`: reach the turn groups (`turn_groups(page)`), one group's state (`data-state`), its work-line text, its items by kind, and open it. Tests name the group through these, never through the control's classes.
- **Live frames are scripted with the existing helper** `_chats.emit_frame(page, payload)` (`tests/browser/_chats.py:166-177`), which pushes a frame through the real `ws.onmessage` path; `test_flow_chat_transcript_library.py` shows it in use. Do not build a second helper. A join payload (`session_joined` with a chosen `history` and `is_processing`) can be emitted the same way.
- **Replay** shapes are seeded with `seed_session(messages=...)` (`tests/browser/seeders.py:417`).
- **This leg writes the tests marked [2]; leg 3 (`turn-work-tests`) writes the rest and rewrites the streaming-bubble tests.** This leg must still do the retired-id sweep below, because the registry guard forces it.
- **New flow tests** (`tests/browser/test_flow_chat_turn_work.py`), each asserting the whole turn's shape including what must be absent. In this leg: items 1 to 5, 8, 10, 11, 12, 13 and 16.
  1. A multi-pass turn live: one group, one reply, the items in order (thinking above its narration), the count, the tool name while a tool runs, the preview moving, then gone.
  2. The same turn after a reload: the same shape.
  3. A turn that ends on a tool call: the latest narration becomes the reply and is no longer in the group.
  4. A plain reply: no group. A thinking-only turn: "Work · thinking".
  5. Stopped: the partial text is in the group, "Stopped · N", no reply bubble, the "Stopped." notice.
  6. Stop racing `done`: a `done` after the click still lands the reply; a `cancelled` with no open group adds only the notices.
  7. An agent error followed by `done`; "An error occurred while processing your message."; "Failed to resume after authentication.": the `error` line, no reply, no running dots.
  8. A validation error and `/reset` right after a send: the empty group is removed.
  9. Step limit: the paused line, the notice with Continue; Continue starts a new turn with its own group.
  10. Sign-in pause: the block is the group's next sibling; resume continues the same group; exactly one reply at the end.
  11. A join on a paused turn (a `session_joined` whose history ends in a tool call, then `auth_required`): no reply bubble, the `sign-in` line; after the resume, one reply.
  12. A join during a resume (`is_processing` false, then live turn frames with no `user` frame): one group, one reply.
  13. A join while a turn runs (`is_processing` true): the trailing turn is `working`, and live frames continue it.
  14. A second window that receives a turn's frames with no send of its own: the same shape.
  15. A held message: the reply is above the queued message's bubble.
  16. "Loading model" on a fresh turn and on a resume: one group, never two.
  17. A connector chat: the "Operator only" chip on the group, a delivered result as a top-level bubble outside it.
  18. Copy reply copies the reply's text and none of the narration.
  19. A chart and a widget in a reply draw when the reply lands; a reply that ends inside an open widget fence shows the cut-off notice and no frame runs.
  20. A widget in narration: not mounted while the group is closed, mounted once when it is opened, the same key live and after a reload; when the latest narration becomes the reply its widget is drawn once.
  21. The preview never shows chart or widget source.
- **The retired-id sweep (this leg).** Once `trace-shell`, `thinking-disclosure` and `thinking-indicator` are retired, no file under `tests/browser/` may name them. `grep -rlnE 'trace-shell|thinking-disclosure|thinking-indicator' tests/browser` finds nine files: `test_flow_chat_thinking_disclosure.py`, `test_flow_chat_visibility_distinction.py`, `test_flow_new_chat.py`, `test_flow_chat_start_flow.py`, `test_flow_chat_transcript_library.py`, `test_flow_chat_queued_render.py`, `test_flow_chat_routine_marker.py`, `test_oauth_modal_flow.py`, `test_flow_chat_live_updates.py`. In each, rewrite the tests that name a retired id to the new shape through the `_chats.py` helpers.
  - A test whose property still exists is rewritten (rename over delete-and-re-add, so the history shows the intent change).
  - A test whose property is gone is removed, and the flight log lists it with the reason "property removed" (flight DD3, DD10).
  - A retired id that appears only in a comment is still reworded; the flight log notes those files.
- **Left for leg 3**: the tests that assert on a streaming assistant bubble before `done` but name no retired id (in `test_flow_streaming.py`, `test_flow_markdown_chat.py`, `test_flow_chat_charts.py`, `test_flow_chat_widgets.py`, `test_flow_chat_widgets_canvas.py`, `test_flow_chat_session_state.py`, `test_flow_usage_restore.py` and any other the lanes show), and flow items 6, 7, 9, 14, 15 and 17 to 21. **These tests are expected to fail at the end of this leg.** Record the failing test ids per lane in the flight log, so leg 3 starts from a known list and nothing else is hidden among them.
- `tests/browser/test_ui_trace_contract.py`, `test_ui_chart_placeholder_contract.py`, the streaming cases of `test_ui_message_contract.py` and `test_flow_chat_visual_stream.py` exercise library or module code directly, not the chat's shape: they are untouched until the cleanup leg.
- **Lanes.** Add each new `test_flow_chat_*` file to `chats_transcript_pat` (`scripts/run-tests.sh:193-199`). When a lane-pinned file is removed, update `scripts/run-tests.sh` and `tests/test_run_tests_lanes.py` together.
- **Falsify** the tests for: one reply at `done` (break the promote), the trailing-turn re-render (items 11 and 12), a paused turn's single reply after the resume (10), and "Loading model" on a resume giving one group (16). Report yes or no per test.

## Acceptance Criteria
- [ ] `App.chat.turnWork.create(ctx)` exists, is created in `chat.js` and loaded by `index.html`; `transcript.js` no longer contains the names listed under "What leaves `transcript.js`", and no caller of them remains anywhere under `static/js`.
- [ ] Live: a multi-pass turn shows exactly one `turn-work` group and, after `done`, exactly one assistant bubble; no assistant bubble exists before `done`.
- [ ] The reply is the turn's last non-empty text (pending text, else the latest narration, else none), built by `addMsg` with attribution and Copy; Copy yields the reply's text only.
- [ ] Every text of a turn is rendered as markdown at most once, and no rendered node is moved between parents.
- [ ] `cancelled`, a turn-ending `system` frame, `step_limit` and `auth_required` fold the pending text and set the state in flight DD2's table; none builds a reply; no path leaves a group in `working` with the turn over.
- [ ] A `done` promotes only from `working`; a `done` after a Stop click still promotes.
- [ ] A turn never has two groups: every start site reuses the open group, and a finished plain reply has none.
- [ ] Replay renders each stored turn by the same rules, with thinking above its message's text; a join with `is_processing` leaves the trailing turn `working`.
- [ ] A live turn frame that reaches a trailing turn closed by replay re-renders the history with that turn open, and the turn ends with one group and one reply.
- [ ] The sign-in block is the group's next sibling, never inside it.
- [ ] In a connector chat the group shows the "Operator only" chip and a delivered tool result stays a top-level bubble.
- [ ] The preview shows the pending text's tail, and "Drawing a chart" or "Building a widget" inside an open fence; it is gone when the turn leaves `working`.
- [ ] `turn-work` and `turn-work-preview` are registered; `trace-shell`, `thinking-disclosure` and `thinking-indicator` are retired in the registry and in `RETIRED_SELECTORS`; no file under `tests/browser/` names them.
- [ ] Flow-test items 1 to 5, 8, 10, 11, 12, 13 and 16 exist and pass; the nine swept files pass; every removed test is listed in the flight log with its reason.
- [ ] `make test-unit` passes. `contracts-chat` passes (`THE_ONE_REQUIRE_WEBKIT=1`). The lanes `chats`, `chats-transcript`, `chats-widgets` and `shared` are run without `-x`, and every failure in them is a streaming-bubble test left for leg 3, listed by test id in the flight log; any other failure is fixed in this leg.
- [ ] No file under `js/ui/` changed, and `stream-commit.js`, `visual-stream.js` and `trace.js` still exist.

## Verification Steps
- No leftover callers: `grep -rnE '\b(showThinking|hideThinking|finalizeStreamingBubble|clearStreamingVisibility|clearIterationAnchor|getOrCreateTrace|traceShellFor|resetTraceShells|renderThinking|onAssistantChunk|resetStream)\b' the_one/interfaces/web/static/js/areas/chat the_one/interfaces/web/static/js/areas/chat.js` prints nothing. (The word boundary matters: the Studio provider editor has an unrelated `showThinkingEnabled`.)
- No retired id in tests: `grep -rnE 'trace-shell|thinking-disclosure|thinking-indicator' tests/browser` prints nothing; `tests/test_nav_helper.py` passes.
- Static guards: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_ui_control_inventory.py tests/test_nav_helper.py tests/test_run_tests_lanes.py -x --timeout 30`.
- While iterating: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_flow_chat_turn_work.py -m browser -x --timeout 30`.
- Lanes, one at a time, each in the background: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane> --timeout 30 -q` for `chats`, `chats-transcript`, `chats-widgets`, `shared` (no `-x` here: the point is the full list of failures); `contracts-chat` with `THE_ONE_REQUIRE_WEBKIT=1` and `-x`.
- `THE_ONE_TEST_NETNS=1 make test-unit`; `ruff check` and `ruff format --check` on `tests/ scripts/`.
- `git status --short` shows no change under `the_one/interfaces/web/static/js/ui/` and no deleted JS file.

## Implementation Guidance

1. **Read**: the flight's DD2 to DD12; leg 1's "The control" and its flight-log entry; `transcript.js`, `turn-frames.js` whole; the call sites in the Citation Audit; the "Chat module map" paragraph in `the_one/agents.md`.
2. **Add the module** and its seams (`renderMarkdown` in the transcript, `_turnWork` in `chat.js`, the `<script>` tag).
3. **Move the live frames** onto it, one frame type at a time, then the other callers.
4. **Move replay** onto it, with `opts.trailing`, and the trailing-turn re-render.
5. **Remove the replaced functions** from `transcript.js` after the caller grep is clean.
6. **Registry and retired selectors**, then the one `ui_capture.py` selector.
7. **Helpers, then tests**: the new file first, then the rewrites. Run the two chat lanes early; they are the slow ones.
8. **Record in the flight log**: the final interface names, every removed test with its reason, the falsification results, the lane results with wall times, and anything left for leg 3 beyond its listed scope.

## Edge Cases
- **`assistant` (whole) frame after chunks in the same pass**: the server sends it only when no chunk fired (`app.py:2718-2723`); if both arrive, fold the chunked text first, then take the whole text as pending.
- **`tool_result` with no open group** (a result that arrives after a re-join): the trailing-turn re-render applies; if there is no kept history, open a group lazily.
- **`done` with no open group**: nothing to promote; the rest of the `done` handler runs as today.
- **Whitespace-only pending text at `done`**: not a reply; fall through to the latest narration.
- **`clearLog` mid-turn** (switching chats): `reset()` drops everything; the next join's replay rebuilds from history.
- **The same widget source in a narration and in the reply**: two draws, two keys, in turn order; equal live and on reload.
- **A turn whose only text was the latest narration and which ended in `error`**: the narration is rendered in place inside the group; there is no reply.
- **A routine run in an open chat**: the routine's `user` frame starts the turn and calls `begin()`.
- **A degraded join** (deleted agent or missing provider): history renders with `trailing: 'closed'`; nothing else changes.
- **The scroll pin**: every group mutation that changes height ends with `transcript.scrollToBottomIfPinned()`, as the trace appends do today.
- **A widget or chart inside a closed group** is leg 3's test (item 20). If you notice while working that a widget in a closed `<details>` mounts, or loses its remembered height (`widget.js:191-199`), or that a chart's first layout on expand jumps a pinned log (`transcript.js:55-57`), record it in the flight log; do not edit `js/ui/` in this leg.

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat/turn-work.js` - new.
- `the_one/interfaces/web/static/js/areas/chat/transcript.js` - loses the replaced functions; `renderHistory` takes `opts`; `renderMarkdown`; `clearLog` resets the module.
- `the_one/interfaces/web/static/js/areas/chat/turn-frames.js`, `socket.js`, `session-flow.js`, `send.js`, `sign-in.js`, `the_one/interfaces/web/static/js/areas/chat.js` - call sites.
- `the_one/interfaces/web/static/index.html` - one `<script>` tag.
- `the_one/interfaces/web/static/css/chat.css` - only if the group needs layout in the log that is not the control's own (no owned class may appear here).
- `tests/browser/_chats.py`, `tests/browser/test_flow_chat_turn_work.py` (new), the rewritten flow tests, `tests/browser/test_oauth_modal_flow.py`.
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` - lane lists.
- `docs/ui-testid-registry.md`, `tests/test_nav_helper.py` - new and retired ids.
- `scripts/ui_capture.py` - one ready selector.
- `sorties/16-turn-work-group/flight-log.md` - the leg's entry.

## Citation Audit
Checked against the working tree at `7d6ab953` on 2026-11-13. Leg 1 edits `index.html`, `components.css`, `scripts/run-tests.sh` and `tests/test_run_tests_lanes.py`; the rows that cite those files are re-checked after leg 1 lands, and the re-check is recorded here.

- `the_one/interfaces/web/static/js/areas/chat/turn-frames.js::handle` - the frame chain; `tool_call` at 103-124, `tool_result` 125-154, `step_limit` 165-173, `done` 174-214 (the held-message send at 193-196), `cancelled` 215-250; `handleSystem` 21-65 ends the turn for every content except the two model-loading strings - verified
- `transcript.js` - `addMsg` 129-172; `addUserEvent` 177-190; `clearLog` 194-212; `renderHistory` 231-240 and `renderHistoryEvents` 242-292; the stream wiring 299-332 and 599-630; `showThinking` / `hideThinking` 336-349; `showModelLoading` 354-360; `getOrCreateTrace` 392-413; `renderThinking` 420-434; `isDeliveredToolResult` 464-466; `drawWidget` and its key counter 90-114; `mdOpts` 115-117 - verified
- `socket.js:89` (close handler hides the thinking line), `215` (`session_joined` hides it before the render), `222` (`renderHistory` call), `250-252` (`is_processing` shows it), `254-258` (a held message sent on the re-join) - verified
- `session-flow.js:345` (start shows the thinking line), `357` (failed start hides it) - verified
- `send.js:63` (send shows the thinking line after the user bubble) - verified
- `chat.js:499` (Stop click hides the thinking line), `477-485` (module creation order), `529-531` (test seams) - verified
- `sign-in.js:242-251` (the sign-in block is the trace shell's next sibling), `261-266` ("Resuming…"), `275-277` (`onAuthRequired` hides the line and finalizes the bubble) - verified
- `the_one/interfaces/web/static/index.html:96-104` - the chat module `<script>` order, `transcript.js` at 99 - verified (re-check after leg 1)
- `the_one/db/codec.py:420-463` - stored order per assistant message: text, thinking, tool calls - verified
- `the_one/interfaces/web/app.py:2706-2794` (live order: text, thinking, tool calls), `2718-2723` (`assistant` sent only when no chunk fired), `2903-2913` and `2968` (error then `done`), `1318`, `3058`, `1186-1229`, `3797`, `3820-3823` (turn-ending `system` frames), `3522-3525` (the cached `auth_required` after a join), `3769-3783` (no `cancelled` when the tasks are done), `2974-3051` (the resume takes no session lock) - verified by the Architect reviews of 2026-11-13; re-read by the leg's design reviewer
- `tests/browser/_chats.py:166-177` `emit_frame(page, payload)` pushes a frame through `area._ws().onmessage`; `tests/browser/seeders.py:417` (`seed_session(messages=...)`) - verified
- `the_one/interfaces/web/app.py:3716` - a start's `session_joined` is built with `is_processing=True` - verified
- Design review (Developer, 2026-11-13): 14 entries spot-checked, all hold; `renderHistory` is called at `socket.js:221` (corrected above); `index.html` line numbers shift by one after leg 1.
- `tests/test_ui_guards.py:255, 288` - the testid registry is checked in both directions - verified (Architect)
- `scripts/run-tests.sh:193-199` (`chats_transcript_pat`), `tests/test_run_tests_lanes.py:170-175` - verified (Architect; re-check after leg 1)
- `scripts/ui_capture.py:2398` - a surface's ready selector is `thinking-indicator` - verified (Architect)

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
