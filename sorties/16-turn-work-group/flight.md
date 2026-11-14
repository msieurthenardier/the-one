# Sortie: One work line per chat turn

**Status**: landed

## Charter

### Outcome
In a web chat, a turn shows one collapsible work line and one final reply, instead of a bubble and a tool group for every pass the agent makes.

### Why Now
Multi-tool turns bury the answer: every pass adds a narration bubble, a "Tool activity" group and sometimes a "Thinking" disclosure, and only the last bubble is the reply.

### Success Criteria
- [ ] A turn with tool calls shows exactly one work line and one reply bubble, live and after a reload.
- [ ] Expanding the work line shows every pass's narration, thinking and tool calls, in order.
- [ ] A stopped, errored or step-limited turn loses no text the model wrote.
- [ ] Copy reply copies only the final reply.

### Constraints
- Browser-only: no server, stored-history or prompt change.
- Built as an `App.ui` control (catalogue row, contract tests in both engines, no owned class outside `js/ui/`).

---

## Pre-Flight

### Objective
Replace the transcript's per-pass rendering (a narration bubble, a "Tool activity" trace and a "Thinking" disclosure for each pass) with one work group per turn:
- a new library control, `App.ui.turnWork`, draws the group;
- a new chat module, `areas/chat/turn-work.js`, decides what goes into it, live and on replay;
- the reply is one normal bubble that appears when the turn ends;
- the code that only served the old shape is deleted.

### Terms
- **Turn**: everything from one user message (or routine run) to the next.
- **Pass**: one model response inside a turn. A pass can carry text, thinking and tool calls.
- **Narration**: a pass's text that is not the reply.
- **Pending text**: text the current pass has produced so far, before the browser knows whether it is narration or the reply.

### Open Questions
- [x] How does text show while it streams? → A muted preview under the work line; the reply appears whole at the turn's end (DD3, the operator's option C).
- [x] What shows when a turn has no final answer? → Everything folds into the group and the header says why (DD5, the operator's option 2).
- [x] Which text is the reply when a turn ends on a tool call? → The last non-empty text of the turn (DD4, operator).
- [x] A reload cannot tell why a turn ended. → Accepted; no server change (DD8, operator).
- [x] What happens to the live markdown, chart and widget streaming code? → Deleted (DD10, operator).
- [x] Always on, or a setting? → Always on; no setting (operator did not ask for one, and a toggle doubles the test surface).
- [x] Connector chats? → The web transcript only; nothing a platform receives changes (DD7).
- [x] HAT leg? → Yes (operator).

### Design Decisions

**DD1: A new control, `App.ui.turnWork`, not an extension of `App.ui.trace`**
- `js/ui/turn-work.js`. A native `<details>`: the summary is the work line, the body holds the turn's items in order. Collapsed by default, in every state. The operator can open it at any time, including while the turn runs; nothing opens or closes it automatically.
- It owns its states and their words (DD2), the dots while working (`App.ui.thinking.dots()`), the count text, the current-tool name, the preview line (DD3) and an optional "Operator only" chip (DD7).
- Items are appended by the caller as nodes of three kinds: narration (a rendered markdown fragment), thinking (plain text with a "Thinking" label) and tool rows (the existing `App.ui.message` `role: 'tool'` nodes).
- The exact option and method names are a leg-design choice. The contract the chat module needs: create; set state; set the tool-call count and whether the turn has thinking; set or clear the current-tool name; set or clear the preview text; append an item; replace an item's content in place and remove an item (DD4); read whether it is empty; destroy.
- **Accessibility.** The log is `role=log` with `aria-relevant="additions"` (`chat-pane.js:214-216`), so new text nodes are announced. The summary keeps a stable accessible name per state ("Working", "Work, 3 tool calls"); the changing visuals (the rising count, the tool name, the preview) are `aria-hidden` or update an existing text node's data, so they are not announced on every change.
- Rationale: `App.ui.trace` is keyed by a parent message id (one per pass), has no state, and its accessible name is fixed to "{label}, N items". The new control replaces it and its thinking sub-entry outright, so both retire (DD10). `App.ui.thinking` stays: the "Loading model" line and the dots use it.
- Follows "Adding a factory" in `the_one/agents.md`: the `<script>` tag in `index.html`, CSS in `components.css`, a catalogue row, contract tests in Chromium and WebKit. (The checklist's "bump the asset count" step is stale: `tests/test_index_asset_cache_busting.py` no longer pins a count, squawk 0233.)
- The contract file is `tests/browser/test_ui_turn_work_contract.py`; `test_ui_turn_work*` is added to `contracts_chat_pat` in `scripts/run-tests.sh` and to the exact set in `tests/test_run_tests_lanes.py::test_contracts_chat_lane_is_the_chat_control_files`, or it lands in `contracts-controls`.

**DD2: States and wording (operator-approved as mocked)**

| State | When | Work line |
|---|---|---|
| working | the turn is running | dots, "Working", then "· N tool calls" once N ≥ 1, then the running tool's name in mono |
| done | the turn ended normally | chevron, "Work · N tool calls" |
| stopped | a `cancelled` frame | chevron, "Stopped · N tool calls" |
| error | a `system` frame that ends a turn whose group has items (see DD5): an "Agent error", "An error occurred while processing your message." (`app.py:1318`), "Failed to resume after authentication." (`app.py:3058`) | chevron, "Ended with an error · N tool calls" |
| step limit | a `step_limit` frame | chevron, "Paused at the step limit · N tool calls" |
| sign-in | an `auth_required` frame | chevron, "Waiting for sign-in · N tool calls" |

- "1 tool call" is singular. The count is tool calls, not results.
- With zero tool calls: a group that holds only thinking reads "Work · thinking"; other states drop the count ("Stopped").
- A finished turn whose group would be empty (a plain reply: no tool call, no thinking) has no work line at all. The running line is removed when the reply lands.
- The existing notices stay where they are, after the group: "Stopped.", the agent-error notice with "Technical details", the step-limit notice with Continue, the sign-in block.

**DD3: Streaming is a quiet preview; the reply lands whole**
- While a pass's text arrives (`assistant_chunk`, or a whole `assistant` frame), the chat module keeps it as pending text and shows its latest part in the control's preview: muted, at most two lines, under the work line.
- The preview shows the **latest** text (the tail), so it keeps moving on a long reply. (The mockup clipped from the start; this is the one deliberate difference, and a HAT item.)
- Raw chart or widget source never shows in the preview: while the pending text is inside an unclosed ```` ```chart ```` or ```` ```widget ```` fence, the preview reads "Drawing a chart" or "Building a widget".
- The preview is `aria-hidden`. Screen readers hear the reply once, when its bubble is added to the log.
- The preview is plain text set with `textContent`. No markdown, chart or widget is drawn from pending text.

**DD4: What becomes the reply**
- At a `done` that arrives while the group is "working" (and only then), the reply is the turn's **last non-empty text**:
  - if there is pending text, it becomes the reply bubble;
  - if the turn ended on a tool call with no text after it, the latest narration becomes the reply bubble;
  - if the turn wrote no text at all, there is no reply bubble.
- The reply bubble is built through the existing `addMsg('assistant', …)` path: markdown, charts and widgets render at that moment, with the agent's attribution, Copy reply (the reply's full text) and the visibility its chunks carried.
- The reply is added **before** a held message is sent (`turn-frames.js:193-196`), so it lands above the queued message's user bubble.
- Every other text of the turn is narration inside the group. Narration renders through the same markdown renderer as a reply (charts and widgets included), so expanding the group loses nothing. Narration has no attribution row and no Copy.
- **Every text is rendered exactly once: the latest narration waits.** The chat module keeps each narration's source text. The most recent narration item is shown in the group as plain text (`textContent`) and is rendered as markdown, in place, only when it can no longer become the reply:
  - when a later non-empty text arrives (as narration or as the reply);
  - when the turn ends in "stopped", "error" or "step limit";
  - when the turn is closed by the next user event (for example, an abandoned sign-in).
  If instead it becomes the reply, the plain item is removed from the group and its source goes through `addMsg`.
- Why: a mounted widget frame must never move (`widget-frame.js:24-28`; a re-parent reloads it and a second `load` counts as an escape, `591-611`), and `drawWidget` must run once per source so a live turn and its reload give a widget the same key (`transcript.js:95-97`). Rendering once, in turn order (narrations, then the reply), keeps both.
- Known limits, to show the operator at the HAT: the newest narration reads as raw markdown source until the next text arrives; and a turn that ends "answer, tool call, short sign-off" shows the sign-off as the reply, with the answer in the group (accepted).

**DD5: Turns with no final answer fold completely**
- On `cancelled`, a turn-ending `system` frame (DD2), `step_limit` or `auth_required`: any pending text is folded into the group as narration, the state changes (DD2), and no reply bubble is built.
- A `done` promotes only from "working". `step_limit` is followed at once by `done`, and so is an agent error (the except branch at `app.py:2903-2913` falls through to the `done` at 2968): neither `done` promotes anything, and the state stays as set.
- **Every `system` frame except the two model-loading ones ends the turn**, as `handleSystem` already does (`turn-frames.js:40-64`). That includes a validation error (`app.py:1186-1229`, sent at 3797) and `/reset`'s "Context cleared." (3820-3823), which arrive after the send opened a group and are not followed by `done`. An empty group is removed (as on a failed start); a group with items goes to "error". No frame can leave the dots running.
- **Stop changes the state only on frames.** The click only stops the dots (visual, as hiding the "Thinking" line is today, `chat.js:499`). The server sends nothing when the turn's tasks have already finished (`app.py:3769-3783`), so:
  - a `done` that arrives after a Stop click promotes the reply as normal;
  - a `cancelled` folds and sets "stopped";
  - a `cancelled` that arrives with no open group adds only the notices;
  - a Stop during a sign-in pause leaves the group "Waiting for sign-in" (no frame follows).
- **"Non-empty" text** means it has at least one non-whitespace character, live and on replay.
- A sign-in pause sends no `done`. When the sign-in resolves and the turn resumes, the same group goes back to "working" and continues; a "Loading model" line on resume (`app.py:2992`) never removes it (DD6). If the sign-in fails or is abandoned, the group stays "Waiting for sign-in" until "Failed to resume after authentication." sets "error" or the next user event closes the turn.
- The sign-in block is placed directly after the turn's work group, never inside it (it must not hide in a collapsed panel: sortie 04's HAT decision, kept).

**DD6: One group per turn; when it starts and ends**
- A group starts wherever the "Thinking" line starts today: the operator's send (`send.js:63`, `session-flow.js:345`), a routine run's user frame, a join that reports `is_processing` (`socket.js:252`), and "Model loaded.".
- It is also created lazily: a chunk, `assistant`, `thinking` or tool frame that arrives with no open group opens one. A second window that receives another tab's turn has no send of its own (`turn-frames.js:75-81` starts the line only for a routine frame), and this gives it the same shape.
- **A turn never has two groups.** Every start site reuses the turn's open group if there is one: the join with `is_processing` (after a start's join the group opened at `session-flow.js:345` is still there, and after DD8 the trailing turn may already be open), "Model loaded.", and the lazy path.
- The "Loading model" line keeps its own `App.ui.thinking` handle. While it shows, an **empty** running work line is hidden; a group that already has items is never removed or hidden.
- The other places that hide the "Thinking" line today map as follows: a failed start (`session-flow.js:357`) removes the empty group; a socket disconnect (`socket.js:89`) leaves the group as it is; the `session_joined` handler (`socket.js:215`) is followed by the replay, which rebuilds the log.
- The "Resuming…" line the sign-in module adds (`sign-in.js:261-266`) sits after the group; leg 2's design decides whether it stays once the resumed items arrive above it.
- A group ends at `done`, `cancelled`, a turn-ending `system` frame or the next user event. A new user event always starts a new turn.
- Tool results go into the group under their call, as today, except a delivered (peer-visible) tool result in a connector chat, which stays a top-level bubble after the group (unchanged rule, `isDeliveredToolResult`).
- Thinking is appended when its frame arrives. Live, that is after its pass's text and before its tool calls (`app.py:2706-2770`), so inside the group it sits above that pass's narration, which is folded in at the tool call. Replay stores the text first (`codec.py:421-435`), so DD8 places a message's thinking above that message's text to match.
- A widget in narration inside a collapsed group never intersects the viewport, so the lifecycle manager leaves it unmounted until the group is opened. That is the wanted behaviour and is pinned by a test. Two side effects are checked in leg 2: a card adopted at width 0 (`widget.js:191-199`) must not lose its remembered height, and a chart's first layout on expand (`transcript.js:55-57`) must not jump a pinned log.

**DD7: Connector chats and visibility**
- Nothing sent to Discord or Telegram changes: this is a rendering change in the web transcript.
- In a connector chat the group carries an "Operator only" chip when any item in it is operator-only. Items inside the group do not repeat the chip.
- The reply bubble keeps today's per-bubble visibility chip.

**DD8: Replay (a reload, a re-join, opening an old chat)**
- `renderHistory` groups the stored events by turn (a `user` event starts a turn) and applies DD4 to each: the last non-empty `assistant` event is the reply, earlier ones are narration, `thinking`, `tool_call` and `tool_result` events go into the group in stored order.
- Within one stored assistant message, replay places its `thinking` above its text (DD6), so a reload keeps the live order.
- The trailing turn of a session that reports `is_processing` is rendered as running: all its text is narration (the latest left unrendered, DD4), the state is "working", and the live frames continue it. `renderHistory` therefore takes the join's `is_processing`; today the flag is read only after the render (`socket.js:222` against `250`).
- **A trailing turn that replay closed but is still alive.** Two cases reach the browser after replay has closed the trailing turn and built its reply:
  - a paused session: after `session_joined` the server replays a cached `auth_required` (`app.py:3522-3525`);
  - a join during a resume: the resume takes no session lock (`app.py:2974-3051`; `is_session_processing` reads `session_locks`, `sessions/_locks.py:26-35`), so the join reports `is_processing` false and the resumed turn's frames arrive live.
  In both, the first live turn frame that is not a `user` frame and reaches a trailing turn closed by replay makes the chat module render the history again from the array it kept, with the trailing turn open: "sign-in" for an `auth_required`, "working" otherwise, and no reply bubble. The frame is then handled as usual. A second full render resets the widget counters with the log (`clearLog`), so keys stay equal. Without this the turn would get a second group and a second reply.
- The kept array is dropped at the first live `user` frame or local send (a held message can be sent on the re-join before the snapshot arrives, `socket.js:254-258`; a re-render after that would wipe its bubble).
- A second accepted live-versus-reload difference: a sign-in that was abandoned renders its last text as narration live, and as a reply bubble after a reload (the last-text rule). Tests do not assert equality for unfinished turns.
- The server stores no reason for a turn's end. After a reload, a stopped, errored or step-limited turn therefore renders as a finished one: its last text is a reply bubble and the line reads "Work". Accepted by the operator; the "Stopped." and step-limit notices already vanish on reload today. No text is lost.
- Events before the first `user` event (legacy sessions) form one leading turn.

**DD9: The turn logic lives in a new chat module**
- `areas/chat/turn-work.js` (`App.chat.turnWork.create(ctx)`, the house pattern) owns: the current group's handle, the pending text, the tool-call count, fold and promote, the replay grouping, and the wipe on `clearLog`.
- `transcript.js` (667 lines, flagged for a split by the Mission 35 Flight 2 debrief) shrinks: it loses the streaming wiring, the "Thinking" line, the trace bucket, `renderThinking` and the iteration anchor. It keeps `addMsg`, the user event, the scroll pin, the notices, the widget and chart draw functions and `clearLog`.
- `turn-frames.js` keeps the frame chain and calls the new module. `socket.js`, `send.js`, `session-flow.js`, `sign-in.js` and `chat.js` call the new module where they call `showThinking`, `hideThinking`, `finalizeStreamingBubble` and `traceShellFor` today.

**DD10: Code with no caller is deleted in the same flight, in its own leg (operator: "Delete it")**
Each deletion follows `removing-dead-code` in `the_one/agents.md`: the grep is run and recorded per item immediately before deleting, and the UI guards run after. Library code with no caller passes every guard, so the tree is green between leg 2 and leg 3.
- **Leg 2** removes from `transcript.js` the functions the new module replaces (the "Thinking" line, the trace bucket, `renderThinking`, the streaming wiring), and rewrites or removes every flow test that pins the old shape (`test_flow_chat_visual_stream.py`, `test_flow_streaming.py`, `test_flow_chat_thinking_disclosure.py`, the placeholder cases in `test_flow_chat_charts.py` and `test_flow_chat_widgets.py`). Removing a lane-pinned file updates `scripts/run-tests.sh` and `tests/test_run_tests_lanes.py` (lines 170-175 pin `test_flow_streaming.py`) together. New `test_flow_chat_*` files are added to `chats_transcript_pat` (`scripts/run-tests.sh:193-199`), or the glob puts them in `chats`.
- **The testid registry changes in the same leg as the testid.** `tests/test_ui_guards.py:255, 288` checks both directions: every testid in the JS is registered, and every registered testid is in the JS. So leg 2 registers the new ids and retires `thinking-indicator`, `trace-shell` and `thinking-disclosure` (their literals leave `transcript.js` in leg 2); leg 3 retires the placeholder ids when `stream-commit.js` goes.
- **Leg 3** deletes:
  - `areas/chat/stream-commit.js` and `areas/chat/visual-stream.js` and their `<script>` tags;
  - `App.ui.trace` with `trace.find` and `trace.thinking`: its file, CSS and contract test; its catalogue row moves to "Retired controls"; `trace` leaves the pinned `contracts-chat` set;
  - streaming-only library pieces, **if the recorded grep shows no caller**: `App.ui.message`'s streaming API (`streaming`, `appendText`, `commit`, `finalize`, `tail`, `setTailHold`) and `App.ui.chart.placeholder` (`chart-placeholder.js`; the "Rendering widget" placeholder is this control with another label, built in `stream-commit.js:47-55`, not a widget-card state), with its contract file and its place in the pinned `contracts-chat` set;
  - transcript functions left without a caller (`resetStream` and `resetTraceShells` already have none outside the module).
- The unclosed-fence handling (`closed: false` on `App.ui.chart.block` and `App.ui.widget`) stays: a reply can still end inside an open fence.
- Retired testids go to the "Retired testids" table in `docs/ui-testid-registry.md` and to `RETIRED_SELECTORS` in `tests/test_nav_helper.py`: in leg 2 `trace-shell`, `thinking-disclosure`, `thinking-indicator`; in leg 3 `chat-chart-placeholder`, `chat-chart-placeholder-source`, `chat-widget-placeholder`, `chat-widget-placeholder-source`. Once retired, no test may name them, so "the old shape is absent" is asserted through the new helpers (for example, a turn has exactly one group and one assistant bubble), never by a retired id.
- If a deletion turns out to have a live caller, it stays and the flight log says why.

**DD11: The contract the tests and behavior specs read**
- New testids (final names fixed at leg design and recorded in `docs/ui-testid-registry.md`): the group `turn-work`, its preview `turn-work-preview`, and `data-state` on the group with the six state names.
- Kept as they are: `message`, `message-copy`, `chat-stopped`, `chat-agent-error`, `chat-agent-error-details`, `chat-step-limit`, `chat-step-limit-continue`, `chat-discarded`, `model-loading`, `chat-chart`, `chat-widget`.
- `tests/browser/_chats.py` gains the helpers the flow tests use to reach a turn's group, its items and its state, so tests name the group through the helper and never the control's classes.
- Behavior specs that describe the old shape are re-authored in leg 3: `agent-step-limit-notice`, `chat-loop-hang-and-cancel`, `extended-thinking-tool-turn`, `stub-connector-round-trip`, `chat-roundtrip` (its step 4 expects the reply to fill in progressively) and `anthropic-plan-token-chat` (its step 6 expects "strictly growing reply text"). `anthropic-plan-chat-parity` step 3 and `agent-governance-and-search` (lines 47, 63: "streamed assistant text", "the activity trace") are checked and re-authored where the old wording no longer holds. A HAT change to this contract is a spec re-author, not an inline fix.

**DD12: How the tests drive a turn**
- The mock provider cannot script a multi-pass turn: it returns the same `response` on every call (`the_one/llm/mock.py:98-111`), so a `tool_calls` response repeats until the step limit. Changing it would be a server change, outside the charter.
- Live shapes are driven by scripted socket frames through `page.route_web_socket` (the pattern in `tests/browser/test_flow_chat_build_failed.py:39`; `scripts/ui_capture.py`'s `SocketScript`, line 1871, is the capture tool's equivalent).
- Replay shapes are seeded with `seed_session(messages=...)` (`tests/browser/seeders.py:418`).
- One end-to-end test runs a real mock-provider turn with a tool call to the step limit, to prove the real frame order reaches the group.

### Mockups (operator-approved, 2026-11-13)
Canvas: https://claude.ai/artifact/RKMWAKcZpdd9QdpwvzbG2a (private to the operator), built on the GleepGlorp AI design system.

1. **Today, and the proposed group** (running, finished and collapsed, finished and expanded). Approved: "looks great".
2. **Streaming**, three animated options. **C chosen**: a quiet preview, then the reply. The caption strip and Replay button on these boards are mockup scaffolding, not design.
3. **No final answer**, two options. **Option 2 chosen**: everything folds, the header says why.
4. **Edge cases** (plain reply, thinking only, sign-in pause, connector chat) and a **light theme** board. Approved with the rest.
5. **Wording** approved: "I like your wording".

Decided after the mockups, with no board (operator, same day): the "last text written" reply rule (DD4), the reload behaviour (DD8), deleting the streaming code (DD10), the HAT leg. One difference from the boards, for the HAT: the preview follows the tail of the text (DD3).

### Citation Audit
Verified in the working tree at `7d6ab953`.

| Citation | Status |
|---|---|
| `the_one/interfaces/web/static/js/areas/chat/turn-frames.js::handle` — a `tool_call` frame finalizes the streaming bubble, so each pass's text is its own bubble (lines 103-111); `step_limit` is handled before `done` (165-173); `cancelled` adds the "Stopped." notice (215-228) | verified |
| `the_one/interfaces/web/static/js/areas/chat/transcript.js::getOrCreateTrace` — one trace per `parent_message_id`, created on the first tool event (392-413) | verified |
| `transcript.js::renderThinking` — a separate disclosure, placed above `iterationAnchor` (420-434) | verified |
| `transcript.js::renderHistoryEvents` — replays `user`, `assistant`, `thinking`, `tool_call`, `tool_result`, `system` in stored order (242-292) | verified |
| `transcript.js::isDeliveredToolResult` — connector session, not an error, not operator-only (464-466) | verified |
| `transcript.js` — the only caller of `App.chat.streamCommit.create` (311); `stream-commit.js` is the only caller of `visualStream` | verified (sweep, 2026-11-13) |
| `the_one/db/codec.py::messages_to_ui_events` — per assistant message: `assistant` (if content), then `thinking`, then `tool_call` events; a tool message gives `tool_result` (420-463). No end-reason field | verified |
| `the_one/interfaces/web/app.py` — live order for a pass: text (chunks, or `assistant` when no chunk fired), then `thinking`, then `tool_call` events (2706-2794) | verified |
| `app.py::_build_session_joined_ok` — the payload carries `is_processing` (2141-2163); `socket.js` shows the thinking line on it (250-252) | verified |
| `app.py` — a paused turn (sign-in) sends no `done` (2933-2936); `step_limit` is sent immediately before `done` (2964-2968); `cancelled` comes from `_notify_cancelled_once` (1020-1030) | verified |
| `the_one/interfaces/web/static/js/areas/chat/sign-in.js` — the login group is inserted as the next sibling of the turn's trace shell, found through `App.ui.trace.find` or `transcript.traceShellFor` (242-251) | verified |
| Callers outside `transcript.js` and `turn-frames.js`: `showThinking` in `socket.js:252`, `session-flow.js:345`, `send.js:63`; `hideThinking` in `socket.js:89, 215`, `session-flow.js:357`, `sign-in.js:275`, `chat.js:499`; `finalizeStreamingBubble` in `sign-in.js:276` | verified |
| `the_one/interfaces/web/static/js/ui/thinking.js::dots` — `App.ui.thinking.dots() -> {el, destroy()}` | verified (sweep) |
| `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py` — a factory needs a catalogue row and a `tests/browser/test_ui_*.py` that calls it; owned classes may not appear outside `js/ui/` | verified (sweep) |
| `scripts/run-tests.sh` — `contracts_chat_pat` and `chats_transcript_pat` are explicit lists; `tests/test_run_tests_lanes.py` pins them | verified |
| `tests/browser/test_flow_chat_build_failed.py:39` — live frames are scripted with `page.route_web_socket`; `tests/browser/seeders.py:418` `seed_session(messages=...)` seeds history | verified (Architect, 2026-11-13) |
| `the_one/llm/mock.py:98-111` — the mock returns the same `response` on every call, so it cannot script a multi-pass turn | verified (Architect) |
| `app.py:2903-2913` then `2968` — an agent error is followed by `done`; `app.py:1318`, `3058` — two other `system` frames end a turn with no `done`; `turn-frames.js:40-63` clears in-flight for any such frame | verified (Architect) |
| `app.py:3522-3525` — a join replays a cached `auth_required` after `session_joined` | verified (Architect) |
| `the_one/interfaces/web/static/js/ui/widget-frame.js:24-28, 591-611` — a mounted frame is never moved; a second `load` is an escape signal | verified (Architect) |
| `the_one/interfaces/web/static/js/areas/chat/chat-pane.js:214-216` — the log is `role=log`, `aria-relevant="additions"` | verified (Architect) |
| `tests/test_run_tests_lanes.py:106-130, 170-175` — the exact `contracts-chat` set and `test_flow_streaming.py`'s lane are pinned | verified (Architect) |

### Prerequisites
- [x] No open flight touches the chat transcript (sorties 12 and 13 are evals and Ollama wire work).
- [x] `main` is clean apart from an untracked `env.sh`.
- [ ] WebKit host libraries present for the contract lanes (`bash scripts/setup-webkit-userland.sh`); re-checked at the start of leg 1.
- [ ] HAT: a dev instance on a non-default port with a scratch data directory, started from a scratch working directory (CLAUDE.md "Behavior-test credential convention"), never on 8484 or 8485. It needs `THE_ONE_STUB_TEST_ENDPOINT=1` (step 9), a real provider whose model emits thinking (step 8) and an MCP server that asks for an OAuth sign-in (step 7). These depend on outside sessions (a plan token or sign-in, a running MCP server), so each is re-verified at the start of the HAT leg, not taken from planning.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Operator-approved mockup recorded
- [x] Citation Audit complete
- [ ] Prerequisites verified (WebKit at leg 1; the HAT instance at the HAT leg)
- [x] Validation approach defined
- [x] Legs defined
- [x] Architect design review (two cycles, both "approve with changes", both incorporated; see the flight log)

---

## In-Flight

### Technical Approach
1. **The control** (leg 1). `App.ui.turnWork` with its CSS, catalogue row and contract tests, built and tested alone on the disk harness. Nothing in the app uses it yet, so the app is unchanged after leg 1.
2. **The chat change** (leg 2), in this order:
   - add `areas/chat/turn-work.js` and move the live frames onto it;
   - move replay and the sign-in block's placement onto it;
   - add the `_chats.py` helpers and rewrite or remove every flow test that pins the old shape (DD10, DD12).
   After leg 2 the app has the new shape and the old code is still on disk with no caller.
3. **The cleanup** (leg 3):
   - delete what has no caller (DD10), with the recorded greps, and retire the testids;
   - update the capture surfaces in `scripts/ui_capture.py`: the `chat-live-thinking` surface waits on `thinking-indicator` today (line 2398); add surfaces for working, finished-and-expanded and stopped;
   - re-author the behavior specs (DD11);
   - update the docs: `CLAUDE.md`, `the_one/agents.md` (including the stale asset-count step in "Adding a factory"), `docs/ui-control-inventory.md`, and `SECURITY-MODEL.md` "Live visuals" where it describes the streaming hold. (`docs/ui-testid-registry.md` changes in whichever leg adds or removes the id, DD10.)
4. **HAT** (leg 4). The operator walks the states on a dev instance with a real model.

### Verification approach
- **Contract tests** (both engines): the control's states, wording, count, preview, items, the move-out of the last narration, the accessible name, reduced motion, and that it is a native `<details>`.
- **Flow tests** (`chats-transcript`), each asserting the whole turn's shape, including what must be absent (no second bubble, no old trace):
  - a multi-pass turn live: one group, one reply, the items in order;
  - the same turn after a reload: the same shape;
  - a turn that ends on a tool call: the last narration is the reply;
  - a plain reply: no work line;
  - thinking only;
  - stopped, error, step limit (with Continue), sign-in pause and resume;
  - an agent error followed by `done`, and each of the two `system` frames that end a turn without `done`: no reply bubble, the "error" line, no spinning dots;
  - a validation error and `/reset`: the empty group is removed, nothing spins;
  - Stop racing `done`: a `done` after the click still lands the reply; a `cancelled` with no open group adds only the notices;
  - a join during a resume (no `is_processing`, then live frames): one group, one reply;
  - a join while a turn is running; a join on a paused turn (the cached `auth_required`): no reply bubble, then exactly one after the resume;
  - a second window that receives only the frames of another tab's turn: the same shape;
  - a held message: the reply lands above the queued message's bubble;
  - "Loading model" on a fresh turn and on a resume: one group, never a second;
  - a connector chat: the chip, and a delivered result outside the group;
  - Copy reply copies the reply only;
  - a chart and a widget in a reply draw when the reply lands, and an unclosed widget fence never runs;
  - a widget in narration: the same key live and after a reload, not mounted while the group is collapsed, mounted once when it is opened, and never drawn twice when the latest narration becomes the reply.
- **No new behavior spec.** The existing specs that describe the old shape are re-authored (DD11). Real-model behaviour is the HAT's job.
- **Gates**: `make test-unit`, then the lanes that own or assert on the changed files: `contracts-chat`, `contracts-controls`, `chats`, `chats-transcript`, `chats-widgets`, `shared` (`test_oauth_modal_flow.py` reads `trace-shell`), `agents` (`test_flow_agents_focus_after.py` reads `model-loading`). The full `make gate` runs once at the close, on a quiet host, and `chats`, `chats-transcript` and `contracts-chat` are re-budgeted from that run if they moved more than 15%.

### Checkpoints
- [x] Leg 1: the control passes its contract tests in both engines; the UI guards pass.
- [x] Leg 2: live and replay render the new shape; the listed lanes pass. (With leg 3, `turn-work-tests`, after the split.)
- [x] Legs 4 and 5 (the cleanup and the docs, after the splits): the deletion greps are recorded; the UI guards and the listed lanes pass; specs and docs updated.
- [x] Full gate: unit tier and 19 of 20 lanes green on 2026-11-14; the `agents` lane failed once on a known test race (squawk 0359) and passed 186 of 186 when re-run alone. The host was not quiet (start load 1.70), so no lane budget was re-read from this run.
- [x] HAT walked and signed off (2026-11-14). Two fixes came out of it: the chevron shows in every state, and the working indicator is three CSS-drawn dots (DD1's `App.ui.thinking.dots()` was replaced, because a font glyph could not be aligned across browsers). Not walked: the sign-in pause, thinking in the group, the desktop webview.

### Adaptation Criteria

**Divert if**:
- The change cannot stay browser-only (for example, replay cannot group turns without a server change).
- A second cluster of decisions appears (for example, the operator wants the end reason stored, or a per-agent setting): that is a new sortie or a mission, not a wider leg.
- Deleting the streaming code breaks something outside chat.

**Acceptable variations**:
- The control's option and method names, and the final testids.
- Keeping a small part of `visual-stream.js` if the preview's open-fence check uses it (then it is not dead and stays, with the reason logged).
- HAT wording and spacing changes that stay inside DD2's states.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [x] `turn-work-control` - `App.ui.turnWork`: the control, its CSS, catalogue row and contract tests.
- [x] `turn-work-in-chat` - the chat module, live and replay on the new shape, the sign-in placement, the test helpers, the core flow tests and the retired-id sweep.
- [x] `turn-work-tests` - the remaining flow tests and the rewrite of the tests that assert on a streaming bubble. Split from `turn-work-in-chat` at its design review (2026-11-13): the whole was too much for one Developer pass. The lanes are expected red between these two legs, with the failing tests listed in the flight log; nothing is committed until the flight review.
- [x] `turn-work-cleanup` - the deletions with their recorded greps, the retired testids, catalogue rows and lane pins. Split from leg 2 at the Architect's request: deleting library code is the hard-to-reverse step and gets its own checkpoint.
- [x] `turn-work-docs` - the capture surfaces, the behavior specs and the docs. Split from `turn-work-cleanup` at its design review (2026-11-13), again for size.
- [x] `hat-and-alignment` *(optional, operator chose yes)* - a guided walk on a dev instance:
  1. [idle] → [working]: send a multi-tool prompt. One "Working" line, the count rising, the tool name, the moving preview; no bubble yet; no error line.
  2. [working] → [done]: the reply lands whole; the line reads "Work · N tool calls"; exactly one reply bubble; Copy copies the reply only.
  3. [done] → [expanded]: narration, thinking and tool rows in order; collapse again. Also open the group while a turn runs: the newest narration shows as plain source until the next text arrives (DD4). Is that acceptable?
  4. [done] → [reloaded]: the same shape; no duplicate group.
  5. [working] → [stopped]: Stop mid-pass. "Stopped · N", the partial text inside the group, "Stopped." below, no reply bubble.
  6. [working] → [step limit] → Continue: the paused line, then a new turn with its own group.
  7. [working] → [sign-in] → [working]: the sign-in block sits after the group; after signing in the same group continues.
  8. A plain reply (no work line), a thinking-only turn, a chart and a widget in a reply.
  9. A connector chat (stub connector) and a second window on the same chat: both show the same shape.
  10. Both themes; the desktop webview if the operator wants it.

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated

### Verification
- In a web chat, a multi-tool turn shows one work line and one reply, live and after a reload (criteria 1 and 2: the flow tests and HAT steps 1-4).
- A stopped, errored or step-limited turn keeps all its text inside the group (criterion 3: the flow tests and HAT steps 5-6).
- Copy reply yields the reply's text only (criterion 4: the flow test and HAT step 2).
- `grep` shows no caller of the deleted modules, and the UI guards pass.
