# Flight Log: One work line per chat turn

**Flight**: [One work line per chat turn](flight.md)

## Summary
Ready. The charter and the flight spec were agreed with the operator on 2026-11-13, after two Architect design reviews.

---

## Leg Progress

### Flight Director Notes (execution)
- **2026-11-13, start.** Status `in-flight`; branch `sortie/16-turn-work-group` from `main` at `7d6ab953`. Crew file `leg-execution.md` loaded and valid. Four legs: three autonomous, then the HAT. Legs 1 to 3 run as one batch: one code review, one accessibility review (this is a UI flight) and one commit before the HAT.
- **Leg 1 risk tier: low.** A new, additive library control on an established pattern (`trace.js`), used by nothing yet; no shared interface, state machine or cache changes. No per-leg design review; the flight-end Reviewer and Accessibility Reviewer cover it. Developer on Sonnet (crew file).
- **Leg 2 risk tier: high.** It changes the turn's lifecycle and state handling, removes functions other chat modules call, and changes the join and replay paths. Leg 2 was drafted while leg 1 was being implemented, because leg 1's control API is fixed by its artifact; a Developer design review (Sonnet, read-only) runs in parallel with leg 1's implementation. The leg stays `planning` until that review is incorporated and leg 1 has landed.
- **Leg 2 design review, cycle 1** (Developer, Sonnet): **approve with changes**; 14 citations spot-checked, all hold. Incorporated:
  - **[high] "Model loaded." on a resume join opened a second group**, below the reply replay had built. Every open now goes through one `ensureOpen`, which re-renders the trailing turn when replay closed it.
  - **[medium] An empty "Working" line could outlive a start whose turn never ran**: the join now drops an empty group when it reports no turn in flight and rendered no history.
  - **[medium] `onUserEvent` and replay**: replay never calls it; the local send and the start call it explicitly before the user bubble.
  - **[medium] The re-render wipes transient lines** (a "Model loaded." line, a sign-in block): stated and accepted, as on any re-join; the sign-in block is rebuilt by the frame that follows.
  - **[medium] Too large for one pass.** Split: leg 2 keeps the module, live, replay, the core flow tests and the retired-id sweep the registry guard forces; a new leg 3, `turn-work-tests`, takes the remaining flow tests and the streaming-bubble rewrites. The flight is now four autonomous legs plus the HAT. This is a work split, not new scope; the operator is told.
  - **[low]** `stopDots` on a group a new turn orphans; the socket-close behaviour change goes on the HAT list; the existing `emit_frame` helper is named so no second one is built.
  - Answer to the reviewer's question: a start's `session_joined` reports `is_processing` true (`app.py:3716`).
- **Leg 2 design review, cycle 2** (Developer, Sonnet, a fresh agent): **approve with changes**, no design defect; every `ensureOpen` sequence walked gives one group and no recursion, and the unit tier should pass at the end of the leg. Text fixes applied: the leftover-caller grep needed word boundaries (an unrelated `showThinkingEnabled` exists in Studio); stale "leg 3" wording; "Model loaded." keeps its in-flight gate, so it is not a re-render trigger; a delivered tool result opens no group. Leg 2 marked `ready`; it starts when leg 1 lands.

- **Leg 1 landed** (`[LAND:leg]`): contract tests 24 passed in both engines, `contracts-chat` 400 passed, unit tier 10143 passed and 15 skipped (the expected count under netns); three behaviours falsified. No test process left running. Leg 2's Developer spawned (Sonnet). The flight now has four autonomous legs (the leg 2 split), still one batch with one review and one commit before the HAT.
- **Leg 2 landed** (`[LAND:leg]`). Its new flow file passes (13), `chats` 184 and `shared` 364 pass, `contracts-chat` 400 passes; `chats-transcript` has 20 failures and `chats-widgets` 3, all on the list expected for leg 3 (a streaming bubble, a placeholder or a pre-`done` Copy). Four behaviours falsified. Three small departures from the leg's interface table, all accepted: `reset()` also drops the kept history, `ensureOpen('working')` also revives a `sign-in` or hidden group, `replay` takes the raw agent name. One thing to watch: the unit tier had one failure (a source-shape pin in `tests/test_store_static.py`), fixed after the run, so the full unit tier has not been green end to end since; leg 3 runs it.
- **Leg 3 risk tier: low.** Tests only, on the shape leg 2 built, with one bounded exception: a defect a new test finds inside the chat modules may be fixed there; anything needing `js/ui/` is recorded and `xfail`ed for the Flight Director. No per-leg design review. Developer on Sonnet.
- **Leg 4 risk tier: high.** It deletes library code and a shared control API (`App.ui.message`'s streaming methods) and is the hard-to-reverse step. Drafted while leg 3 runs; a Developer design review (Sonnet, read-only) runs in parallel. The Flight Director's own greps show no product caller of any of the five items after leg 2.
- **Leg 4 design review** (Developer, Sonnet): **approve with changes**. It ran the dead-code grep for all five items and found every deletion safe (hits are the definition, its own test, a doc, or a flow test leg 3 rewrites). Incorporated:
  - **[high] Too large for one pass.** Split in two: leg 4 keeps the deletions, catalogue, registry and lane pins; a new leg 5, `turn-work-docs`, takes the capture surfaces, the behavior specs and the docs. The flight is now five autonomous legs plus the HAT. Same scope, smaller passes.
  - **[medium] `App.ui.thinking.dots` would lose its only direct contract tests** with the chart-placeholder contract file. Moving them into the thinking contract file is now the leg's first step.
  - **[medium] CSS details**: the placeholder shares two selector lists with the kept chart rule; its own block, a keyframe and a reduced-motion rule go with it; the trace block's exact extent is given.
  - **[low]** `README.md` describes the old shape (two sentences) and was missing from the docs list; the exact spec lines and capture surfaces are listed in leg 5.
  - No second review cycle: the code scope of leg 4 changed only by adding the reviewer's own precise findings, and the split moved work out without changing it. Leg 4 `ready`.
- **Leg 5 risk tier: low** (a developer tool's surfaces, spec text and docs; no product behaviour). No design review of its own; its content was reviewed as part of leg 4's draft. `ready`.
- **Leg 3 landed** (`[LAND:leg]`). `chats-transcript` 147 passed (was 116 and 20 failed), `chats-widgets` 30 passed (was 22 and 3 failed), `chats` 184, `shared` 364, `contracts-chat` 400, unit tier 10143 passed and 15 skipped: the first fully green unit run since leg 2's pin fix. All 23 tests accounted for; two chart tests removed as "property removed" (per-tick parsing); 18 new tests; three falsified. No product file changed, no `xfail`, nothing open for the Flight Director. The widget-in-a-closed-group checks (item 20) pass without any `js/ui` change. Leg 4's Developer spawned (Sonnet), with the operator's rider (the new-agent form's 50 steps).
- **Leg 4 landed** (`[LAND:leg]`). All five items deleted; no grep found a product caller. `App.ui.message`'s handle is now `{el, destroy()}`. Dots tests moved and falsified; the rider done and falsified. Guards 557 passed; `contracts-chat` 322 (78 fewer: the deleted trace, placeholder and streaming cases), `contracts-controls` 1230 and 4 skipped, `chats-transcript` 147, `chats-widgets` 30, `chats` 176 (8 fewer: the deleted visual-stream file), `shared` 364, unit tier 10137 passed and 15 skipped. No Python changed.
  - **`agents` lane: 185 passed, 1 failed**: `test_flow_agents_focus_after.py::test_form_is_clean_and_shows_the_stored_model_while_loading`. It passed alone in 3 s. Recorded as a timing flake on a loaded host, not accepted as proven: the closing gate re-reads it on a quiet host, and a second failure there makes it a regression to triage (this leg changed the new-agent form's default in the same General tab).
  - **Left out of scope on purpose**: a stale "Tool activity" comment at `the_one/interfaces/web/app.py:2175`. It is Python, and the charter is browser-only; it goes to the debrief as a squawk candidate.
- Leg 5's Developer spawned (Sonnet).
- **Leg 5 landed** (`[LAND:leg]`). Capture surfaces: two removed, three added, one renamed; one capture run, 28 PNGs, 0 failures, in `/home/cprch/the-one-capture-sortie16` (not committed). Nine behavior specs re-authored (one beyond the list, `directory-lookup-send`). Docs updated, with a new "Turn work group (sortie 16)" section in `the_one/agents.md`. `docs/chart-format.md:13` was not a false positive after all and was reworded. Unit tier 10137 passed, 15 skipped. No product or test file changed.
- **Flight Director's own look at the captures** (`chat-turn-finished-open` dark, `chat-turn-working` light, 1280 wide): the finished turn reads "Work · 1 tool call" with thinking, narration, the tool call and its result in order, and one reply bubble with Copy below; the working turn reads "Working · 1 tool call read_file" with a two-line muted preview, Stop shown and Send disabled. Both match the approved mockup, with the app's spinner in place of the mockup's three dots.
- **All five autonomous legs landed. Flight review started** (Phase 2d): a Reviewer and, because this is a UI flight, an Accessibility Reviewer, in parallel, both read-only on the uncommitted tree against `7d6ab953`. **Reviewer tier: Sonnet (the security tier).** The diff changes when and how often model-written widget source is drawn (the widget key rule, the unclosed-fence rule, narration rendering) and edits `SECURITY-MODEL.md` "Live visuals", which is the sandboxing surface the crew file names.
- **Accessibility review: `[HANDOFF:confirmed]`**, no blocking issue. Contrast computed for every text colour of the control in both themes (5.5:1 or better); announcements in the `role=log` region reasoned through; a live screen reader and 200% zoom were not run. Non-blocking: focus loss and a collapsed group on the trailing-turn re-render (accepted in the design, DD8); the chevron's rotation ignores reduced motion (fixed in the fix pass); no forced-colors override (not taken: the outline survives forced colours).
- **Code review, pass 1: `[HANDOFF:confirmed]`**, no blocking issue: render-once and no-moved-node rules hold on every path walked; no double group, stuck group or double reply; the deletions leave no reference; the security claims match the code; the rider touches only the form default. It stated it had **not** checked whether rewritten tests were weakened or whether new tests can pass vacuously, both of which the brief asked for, and it called a mid-turn `user` frame "unreachable" without reading the server.
- **Code review, pass 2** (a fresh Reviewer, Sonnet, on those three points only): `[HANDOFF:confirmed]`.
  - Rewritten tests: no assertion about surviving behaviour was dropped, with two small losses, both fixed in the fix pass: the continuous "source text never visible" watch in the widget and chart tests had become a single sample, and one absence check in the queued-render stop test could pass on a missing group.
  - New tests: none can pass vacuously; the five falsified ones assert exact lists and order.
  - A `user` frame cannot reach an open chat before the running turn's `done` from any server source: the `user` broadcast and `done` are both inside the session's turn lock (`app.py:1280, 2531-2560, 2968`); a connector turn broadcasts no `user` frame; a routine run always uses a new session; no route injects a message.
  - **A defect that predates this flight, left alone**: a second window that is only watching another window's turn keeps its Send enabled (it is marked in flight only for a routine frame, `turn-frames.js:75-81`). If it sends mid-turn, the first turn's remaining frames merge into the new turn's group. The base had the same mix-up with bubbles. Out of scope; a squawk candidate for the debrief, and something to keep in mind at HAT step 9.
- **Fix pass spawned** (Developer, Sonnet): six small items from the two reviews (chevron motion, a registry wording, an overbroad comment, the vacuous assertion, the continuous watch, a stale "Copy reply" sentence). Code review cycles used: 1 of 3.
- **Fix pass 1 found a real defect.** The restored continuous watch caught the preview showing raw chart and widget source before `done` (a half-typed opening fence; a closed block still in the pending text), against DD3. The Developer rewrote `previewFor`. That was unreviewed product code, so the Flight Director sent it to a fresh Reviewer rather than straight to the gate.
- **Code review, cycle 2** (Reviewer, Sonnet, on the fix pass): **not confirmed.** Running `previewFor` under node showed three more leaks for inputs the markdown renderer does draw as a chart or widget: CRLF line endings; a block inside a blockquote or a list item; a fence-like line inside an open block's body, which ended the hiding early. The other five fixes are fine. The existing watches run one plain stream each and cover none of the three.
- **Fix pass 2 spawned** (Developer, Sonnet): `previewFor` must hide at least everything the renderer would hand to the chart or widget renderer, at every prefix of the text; over-hiding is acceptable, a leak is not. A differential test against the real renderer over a corpus, checked at every prefix, is required, with each of the three leaks falsified. Code review cycles used: 2 of 3; one more failed cycle escalates to the operator.
- **Fix pass 2 done** (`[HANDOFF:review-needed]`): the three leaks fixed; a differential test against the real renderer over 34 inputs at every prefix, falsified for each leak. One unit failure, `tests/test_run_tests_lanes.py::test_parallel_exit_codes` (a subprocess timeout under load; passed alone, and passed for the next reviewer on a quiet run). The full unit tier was not re-run; the gate settles it.
- **Code review, cycle 3** (a fresh Reviewer, Sonnet, told to break it): `[HANDOFF:confirmed]`, with one leak that meets this flight's own blocking definition. It loaded the real `markdown.js` and `turn-work.js` in node and fuzzed about 26,000 inputs the renderer draws, at every prefix: 0 leaks. Cost is linear. The one leak: `unwrapLine` looks at a 24-character window, so an ordered-list marker of 23 or more digits hides nothing, while the renderer accepts a number of any length. Contrived, but real. It also judged the differential test's oracle weak (only whole secret tokens count).
- **Flight Director's call on the cycle limit.** Three code review cycles are used. The Reviewer signalled confirmed, and the remaining leak has a one-line cause and an exact reproducer, so this is not an unresolved review loop to escalate; it is a known defect to fix and verify. A third fix pass (Developer, Sonnet) removes the window and any other fixed cap, strengthens the oracle (a token on every body line) and adds the long-marker entries. Instead of a fourth review cycle, the Flight Director verifies it directly: re-run the Reviewer's node fuzz harness and the exact reproducer against the fixed file, then the full gate. The operator is told all of this.
- **Fix pass 3 done** (`[HANDOFF:review-needed]`): the 24-character window is gone (markers are scanned in place, any length; it was the only fixed cap); the differential test's oracle now flags any body line of a drawn block and any partial secret token, with five new corpus entries (22 entries must reach the renderer); falsified.
- **Flight Director's verification of fix pass 3** (in place of a fourth review cycle), run in node against the real `markdown.js` and the fixed `turn-work.js`, from the scratch directory, with nothing in the repo touched:
  - a structured sweep written for this check: 20 container shapes (top level, quotes, bullets, ordered markers of 1 to 200 digits, task markers, mixed nesting, tabs, 40 spaces, 60 nested quotes) with correctly indented or quoted continuation lines, 4 info strings, 7 bodies (including fence-like body lines), LF, CRLF and lone CR, open and closed, with and without text before and after: **13,442 texts, all drawn by the renderer as a chart or widget, each checked at every prefix: 0 leaks** (a leak is the opener, or any body line of 5 or more characters, in the preview);
  - the Reviewer's exact reproducer (a 30-digit ordered marker): "Drawing a chart", no source;
  - the Reviewer's own fuzz harness, three seeds: about 26,000 drawn texts, 0 leaks;
  - no exception on null, empty, backtick-only, 100,000-nested-quote and 100,000-digit inputs; two 300,000-character inputs in 4 ms;
  - the oracle was checked against a preview that returns its input unchanged: it flags it.
  The weakness of the Reviewer's fuzz is worth recording: its list cases never indented the continuation lines, so the renderer never put a body inside those blocks, which is why it reported 0 leaks while a 26-digit marker sat in its own prefix list.
- **Closing gate started** (`make gate` with `THE_ONE_TEST_NETNS=1`, `THE_ONE_REQUIRE_WEBKIT=1`, `TEST_TIMEOUT=3600`). Start load 1.70 (an Ollama server and other sessions), above the quiet-host line of about 1.0: the result counts for pass or fail, **not** for lane budgets.
- **Closing gate result** (2026-11-14): unit tier **10137 passed, 15 skipped** (271 s; the expected skip count under netns; `test_parallel_exit_codes` passed). Browser `--parallel 3`: `PARALLEL_RESULT rc=1 total=2031s lanes=20 failed=agents`. **19 of 20 lanes green**, none over budget (not a budget reading: start load 1.70, 3.8 at the end).
  - The one failure is again `test_flow_agents_focus_after.py::test_form_is_clean_and_shows_the_stored_model_while_loading` (`AssertionError: ['mock-default']`). Triage, as the leg 4 note required: it is **not** a regression from this flight. The test waits on the model select's value, which is already the stored model while the list loads, then reads the options at once; on a busy host the list has not landed. It passed 3 of 3 alone after the gate, and the same failure is in the logs of sorties 08 and 09. This flight's only change in that tab is the new-agent form's default step count, which the test does not touch (it edits a stored agent). Logged as **squawk 0359** (deferred). The `agents` lane is being re-run alone for a clean record before the commit.
- **`agents` lane re-run alone: 186 passed** (437 s). With that, every lane has passed on the final tree. Leg statuses set to `completed`, the five autonomous legs checked off in the flight artifact, and a Developer spawned to make the flight's one commit (crew file: the Developer commits). The HAT follows the commit and the draft PR.
- **Squawks logged mid-flight** (deferred, not fixed here): **0359** (the test race above) and **0360** (the stale "Tool activity" comment in `app.py`).
- **Not a squawk: the second-window send.** It fails the squawk gate's third criterion (it changes in-flight state handling in the chat). It is a small sortie, or a leg of the next chat flight: a window that receives another window's `user` frame should hold its own sends until `done`. Recorded here for the debrief.
- **For the debrief**: the first code review confirmed `previewFor` by reading it ("`previewFor` hides open chart and widget sources"). The leaks were found only because a second reviewer was asked whether tests had been weakened, and a restored test then failed. A "must never appear" property needs a continuous or exhaustive test, not a sample, and a reviewer's "confirmed by reading" on such a property is weak evidence.

### Leg 1: turn-work-control
**Status**: landed (uncommitted; the flight commits once)
**Started**: 2026-11-13
**Completed**: 2026-11-13

#### Changes Made
- New `js/ui/turn-work.js` (`App.ui.turnWork`), loaded after `ui/trace.js` in `index.html`; `.ui-turn-work*` CSS in `components.css`.
- `tests/browser/test_ui_turn_work_contract.py` (12 tests, both engines); `contracts_chat_pat` in `scripts/run-tests.sh`, the pinned set in `tests/test_run_tests_lanes.py`, CLAUDE.md's `contracts-chat` bullet, and a catalogue row in `docs/ui-control-inventory.md`.
- Falsified (edit, see fail, restore): preview tail (text slice, and the CSS `justify-content: flex-end`) yes; dots timer stop on leaving `working` yes; accessible name (", operator only") yes. Other tests not falsified.

#### Notes
- The preview cut-at-top is a column flex box with `justify-content: flex-end` and `overflow: hidden`, `max-height: 3em` at line-height 1.5; the text is a direct text node.
- The chip inside the summary is `App.ui.chip` (class `chip`, not `ui-chip`); the chip wrapper is hidden when unset.
- No file under `areas/` and no existing `js/ui/` file changed. Contract file reformatted by `ruff format` after writing.

### Leg 2: turn-work-in-chat
**Status**: landed (uncommitted; the flight commits once)
**Started**: 2026-11-13
**Completed**: 2026-11-13

#### Changes Made
- New `areas/chat/turn-work.js` (`App.chat.turnWork.create(ctx)`), created in `chat.js` after `ctx.transcript`, `<script>` after `transcript.js`, `self._turnWork` test seam. **Final interface names:** `begin`, `onText(data, whole)`, `onThinking`, `onToolCall`, `onToolResult`, `onDone`, `onCancelled`, `onSystemEnd`, `onStepLimit`, `onAuthRequired` (returns the group's element), `onAuthResolved`, `onUserEvent`, `stopClicked`, `dropEmpty`, `hideForLoading`, `groupEl`, `replay(history, agentLabel, {trailing, agentName})`, `reset`. Internal `ensureOpen(state)` is the one way a group opens (reuse the open group; reopen a trailing turn replay closed by re-rendering the kept history; else create). Differences from the leg's table: `reset()` also drops the kept history (so a stale history cannot survive a chat switch; `ensureOpen` holds locals across its own re-render); `replay` receives the raw agent name in its opts so the re-render passes the same name; `ensureOpen('working')` also moves a `sign-in` group back to `working` and un-hides a group hidden for "Loading model".
- `transcript.js`: removed the streaming wiring, `showThinking`/`hideThinking`, the trace bucket, `renderThinking`, the iteration anchor, `pinToBottom` (only the stream used it); added `renderMarkdown(text)`; `renderHistory(history, agentName, opts)` delegates to `turnWork.replay`; `clearLog` calls `ctx.turnWork.reset()`; `showModelLoading` calls `hideForLoading`. Callers moved in `turn-frames.js`, `socket.js` (join passes `trailing: 'working'` when `is_processing`; `dropEmpty` when no history was rendered and not processing), `send.js`, `session-flow.js`, `sign-in.js` (block placed after `groupEl()`), `chat.js` (Stop click -> `stopClicked`). Leftover-caller grep over `areas/chat*`: empty (also for `streamCommit`, `iterationAnchor`, `pinToBottom`). `stream-commit.js`, `visual-stream.js`, `trace.js` still exist and are still loaded; nothing under `js/ui/` changed.
- Registry: `turn-work`, `turn-work-preview` registered; `trace-shell`, `thinking-disclosure`, `thinking-indicator` moved to the Retired table and to `RETIRED_SELECTORS`. `scripts/ui_capture.py` `chat-live-thinking` ready selector now `turn-work`.
- `_chats.py` helpers: `turn_groups`, `working_turns`, `turn_group`, `turn_state`, `turn_summary`, `turn_line`, `turn_name`, `turn_preview`, `turn_items`, `turn_texts`, `turn_item_list`, `turn_is_open`, `open_turn`, `replies`.
- New `tests/browser/test_flow_chat_turn_work.py` (13 tests: items 1, 2, 3, 4, 5, 8 (two cases), 10, 11, 12, 13, 16 (fresh and resume)); added to `chats_transcript_pat` and pinned in `tests/test_run_tests_lanes.py`.
- Retired-id sweep (nine files, all clean; `grep` over `tests/browser` finds none). Rewritten (renamed to the new property): `test_flow_chat_thinking_disclosure.py` (`test_thinking_item_in_collapsed_work_group_expands_and_survives_reopen`), `test_flow_chat_transcript_library.py` (`test_the_working_label_and_its_static_dots`, `test_thinking_work_group_precedes_its_reply_live_and_on_replay`, `test_each_iterations_thinking_sits_above_its_own_narration_live/_on_replay`, `test_operator_only_is_a_chip_and_the_work_group_names_its_tool_calls`), `test_flow_chat_visibility_distinction.py` (one group for the two passes of one turn; the tool bubble test opens the group), `test_oauth_modal_flow.py` (`test_sign_in_group_sits_after_the_work_group_not_inside_it`), `test_flow_new_chat.py`, `test_flow_chat_start_flow.py`, `test_flow_chat_live_updates.py` (`test_joining_mid_turn_ends_the_running_work_line_after_the_turn`), `test_flow_chat_routine_marker.py`, `test_flow_chat_queued_render.py` (docstring and idle check): the "Thinking" line assertions became `working_turns` / `turn_groups` checks.
- **Removed tests: none.** Property removed inside a kept test: the trace chevron rotation and the "Tool activity · N" dot count in the operator-only test (library-level properties, covered by the `turnWork` contract file); the "indicator reads Thinking…" wording (now "Working", the work line).
- Comment-only mentions reworded: `test_flow_chat_visibility_distinction.py` docstrings, `test_flow_chat_queued_render.py` docstring, `test_flow_chat_thinking_disclosure.py` module docstring.

#### Falsification (edit, see red, restore)
- One reply at `done` (promote's `addMsg` disabled): items 1, 3, 4 failed. **Yes.**
- Trailing-turn re-render (`ensureOpen` step 2 disabled): items 11, 12 and the resume case of 16 failed. **Yes.**
- A paused turn's single reply after the resume (`onAuthResolved` and the `ensureOpen` sign-in -> working move disabled): item 10 failed. **Yes.**
- "Loading model" on a resume gives one group (`hideForLoading` hid non-empty groups): the resume case of 16 failed. **Yes.**
- Other new tests were not falsified.

#### Test runs (host-native, `THE_ONE_TEST_NETNS=1`)
- Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_ownership`, `test_ui_emitted_classes`, `test_ui_control_inventory`, `test_nav_helper`, `test_run_tests_lanes`): 530 passed.
- `test_flow_chat_turn_work.py`: 13 passed (26 s).
- `chats`: 184 passed, 365 s wall. `chats-transcript`: 116 passed, 20 failed, 509 s. `chats-widgets`: 22 passed, 3 failed, 165 s. `shared`: 364 passed, 302 s. (No `-x`; load about 3 from other sessions, so not a budget reading.)
- `contracts-chat` (`THE_ONE_REQUIRE_WEBKIT=1`, `-x`): 400 passed, 110 s wall.
- Unit tier (`make test-unit`, 315 s): the first run had 1 failure, `tests/test_store_static.py::test_start_session_join_refreshes_the_list_that_primes_sessions` (a source-shape pin on the one-line `if (joinedEff.render === 'history') ...renderHistory(` in `socket.js`); I updated the pin to the new shape (`rendersHistory` flag) and re-ran that file, `test_ui_guards.py` and `test_nav_helper.py`: pass. Otherwise 10142 passed, 15 skipped. `ruff check` and `ruff format --check` on `tests/ scripts/`: clean. The full unit tier was not re-run after that one-line pin edit.

#### Left for leg 3 (all expected failures: each asserts on a streaming assistant bubble, a placeholder or a Copy button before `done`; the reply now lands whole at `done`)
- `chats-transcript` (20):
  - `test_flow_chat_charts.py`: `test_streamed_chart_shows_the_placeholder_then_the_chart_before_the_stream_ends`, `test_chart_and_placeholder_fill_the_reply_width`, `test_stop_in_the_middle_of_a_block_leaves_the_cut_off_notice` (placeholders and mid-stream chart; Stop mid-block now folds into the group).
  - `test_flow_chat_queued_render.py` (9): `test_queued_chip_is_pinned_outside_scroll_list`, `test_cancel_chip_discards_held_message_no_turn_runs`, `test_cancelling_the_chip_by_keyboard_focuses_the_composer`, `test_held_message_sent_as_user_bubble_on_done`, `test_stop_during_queued_state_cancels_running_turn`, `test_several_sends_are_held_in_order_then_drain_one_per_turn`, `test_removing_the_middle_then_the_last_chip_moves_focus_and_renames`, `test_the_queue_is_capped_at_ten_and_the_eleventh_stays_in_the_box`, `test_chips_are_not_announced_individually` (`_running_turn` waits for the first streamed chunk as an assistant bubble before holding messages).
  - `test_flow_chat_transcript_library.py` (8): `test_copy_reply_copies_the_stored_content_live_and_on_replay` (asserts the streaming bubble and no Copy until done), `test_an_empty_reply_has_no_copy_and_delivered_results_have_none` (a whole `assistant` frame no longer makes a bubble before `done`), `test_a_stopped_streaming_reply_keeps_every_received_character` (a Stop leaves no reply bubble), and the five `_slow_turn` tests: `test_stop_shows_stopped_and_a_discarded_held_message`, `test_stop_without_a_held_message_shows_only_stopped_and_consumes_the_flag`, `test_a_cancel_from_elsewhere_with_a_held_message_discards_it_too`, `test_stop_with_several_held_messages_reports_the_count`, `test_an_agent_error_discards_the_whole_queue_and_sends_nothing` (wait for the first streamed chunk as an assistant bubble).
- `chats-widgets` (3), `test_flow_chat_widgets.py`: `test_streamed_widget_shows_the_placeholder_then_the_card`, `test_a_chart_and_a_widget_stream_in_one_reply`, `test_stop_in_the_middle_of_a_widget_leaves_the_cut_off_notice_and_it_never_runs` (streaming placeholders and a Stop mid-block).
- `chats` and `shared`: none.

#### Notes
- Replay renders closed turns in order (narrations in turn order, then the reply bubble after the turn's last event) and swaps a `thinking` event above the assistant event it follows (adjacent swap, per turn).
- Not observed this leg (leg 3 / HAT): a widget inside a closed group (mount, remembered height) and a chart's first layout on expand jumping a pinned log; no `js/ui/` edit was needed or made.
- A classifier refused four of my test edits once with "Undermining Oversight" (an assertion swap from the thinking line to the work group); the same edits were applied on a retry and are the rewrites listed above.

### Leg 3: turn-work-tests
**Status**: landed (uncommitted; the flight commits once)
**Started**: 2026-11-13
**Completed**: 2026-11-14

#### Changes Made
- **No product file changed.** The three falsification edits (`turn-work.js`, `turn-frames.js`) were each restored by edit; `git diff` of `areas/chat*` against the pre-leg tree is unchanged. Nothing under `js/ui/` or `the_one/**/*.py` was touched. No `js/ui` defect was found (item 20: a widget in a closed group is not mounted and mounts once on open; no xfail was needed).
- `tests/browser/_chats.py`: new helper `turn_dots_stopped(group)`; `turn_summary` and `turn_is_open` now take the group's own first `summary` / `details` (a widget or notice inside the group brings its own, which broke strict mode).
- New `tests/browser/test_flow_chat_turn_work_states.py` (13 tests: items 6, 7 (three cases), 9, 14, 15, 17, 18, 19 chart half, 21), added to `chats_transcript_pat` in `scripts/run-tests.sh` and to the pin in `tests/test_run_tests_lanes.py`. The existing turn-work file was 466 lines, so the new tests went to a second file as the leg allowed.
- `tests/browser/test_flow_chat_widgets.py`: 5 new tests (19 widget half: lands mounted, ends inside an open fence; 20a, 20b, 20c), imports the scripting helpers from `test_flow_chat_turn_work.py`.

#### The 23 previously failing tests
`test_flow_chat_queued_render.py` (9), all **rewritten**: the helper `_running_turn` and the other waits now use a new `_wait_running(page, text)` (the work group is `working` and its preview holds the text) instead of the first streamed assistant bubble. The nine properties all still exist: `test_queued_chip_is_pinned_outside_scroll_list`, `test_cancel_chip_discards_held_message_no_turn_runs`, `test_cancelling_the_chip_by_keyboard_focuses_the_composer`, `test_held_message_sent_as_user_bubble_on_done`, `test_stop_during_queued_state_cancels_running_turn` (also: a stopped turn builds no reply and "gamma-FINAL" is nowhere in its group), `test_several_sends_are_held_in_order_then_drain_one_per_turn`, `test_removing_the_middle_then_the_last_chip_moves_focus_and_renames`, `test_the_queue_is_capped_at_ten_and_the_eleventh_stays_in_the_box`, `test_chips_are_not_announced_individually`.

`test_flow_chat_transcript_library.py` (8):
- `test_copy_reply_copies_the_stored_content_live_and_on_replay`: **rewritten** (preview while streaming, no reply and no Copy before done; Copy after).
- `test_an_empty_reply_has_no_copy_and_delivered_results_have_none`: **rewritten** (an empty-text turn has no Copy; a whole `assistant` frame has none before `done`, one at `done`).
- `test_a_stopped_streaming_reply_keeps_every_received_character`: **renamed to** `test_a_stopped_turn_keeps_every_received_character_inside_the_group` (3000 characters are in the group's narration, state `stopped`, no reply bubble).
- The four Stop tests and `test_an_agent_error_discards_the_whole_queue_and_sends_nothing`: **rewritten** (only `_slow_turn`'s wait changed, via a new `_wait_running`; the second Stop test waits for the second turn's own working group).

`test_flow_chat_charts.py` (3):
- `test_streamed_chart_shows_the_placeholder_then_the_chart_before_the_stream_ends`: **renamed to** `test_a_streaming_chart_shows_only_the_drawing_phrase_until_the_reply_lands` (preview reads "Drawing a chart", no source and no chart in the log; chart at `done`; no group on a plain reply). The placeholder property is **removed** (flight DD3/DD10).
- `test_chart_and_placeholder_fill_the_reply_width`: **renamed to** `test_a_chart_in_a_landed_reply_fills_the_reply_width`; the placeholder half is **removed: property removed** (no placeholder exists).
- `test_stop_in_the_middle_of_a_block_leaves_the_cut_off_notice`: **renamed to** `test_a_stopped_turn_folds_an_unclosed_chart_block_into_the_group_with_the_cut_off_notice` (notice inside the stopped group, no reply, no chart).

`test_flow_chat_widgets.py` (3):
- `test_streamed_widget_shows_the_placeholder_then_the_card`: **renamed to** `test_a_streaming_widget_shows_only_the_building_phrase_until_the_reply_lands`.
- `test_a_chart_and_a_widget_stream_in_one_reply`: **renamed to** `test_a_chart_and_a_widget_in_one_streamed_reply_are_drawn_when_it_lands`.
- `test_stop_in_the_middle_of_a_widget_leaves_the_cut_off_notice_and_it_never_runs`: **renamed to** `test_a_stopped_turn_folds_an_unclosed_widget_block_into_the_group_and_it_never_runs` (the opener and body now arrive in one chunk, since the preview no longer shows the source to wait on).

Also cleaned in the two visuals files, because they no longer observed anything: `PLACEHOLDER`, `WATCH_JS` and every `to_have_count(0)` on a placeholder id are gone (leg 4 retires the ids; no test names them now). In `test_flow_chat_charts.py`:
- `test_streamed_reply_matches_a_non_streamed_render` **renamed to** `test_a_landed_reply_matches_a_direct_render` (chunks of 40, delay 10 ms; the 5-char/100 ms pacing reason is gone).
- `test_parse_count_stays_bounded_after_a_nested_fence_the_parser_leaves_open` and `test_one_long_unclosed_top_level_fence_never_asks_the_parser`: **removed: property removed** (they pinned the per-tick parser calls of the streaming commit; no streaming parse exists, and the fence cases are covered by the parametrised landed-reply test).
- `test_a_reader_who_scrolled_up_is_never_pulled_down_by_a_chart`: **rewritten** (it had become vacuous: it scrolled up after the whole reply had landed). It now overflows the log with a first turn, scrolls to the top, lands a chart reply at `done` and asserts the scroll position held.

#### Streaming-file review (section 2)
- `test_flow_streaming.py`: `test_streaming_chunks_accumulate_in_single_bubble` **renamed to** `test_streamed_chunks_land_as_one_reply_bubble_at_done` (docstring and module docstring fixed; it also asserts no work group on a plain reply); `test_streaming_message_persists_to_history` kept (docstring phrase corrected).
- `test_flow_markdown_chat.py`: three tests named "streaming_assistant_..." **renamed to** `test_a_streamed_reply_renders_markdown_when_it_lands`, `test_a_streamed_code_block_renders_with_copy_button_when_the_reply_lands`, `test_a_streamed_markdown_table_renders_when_the_reply_lands`; the docstrings no longer mention `finalizeStreamingBubble` or a plain-text mid-stream bubble. `test_code_copy_confirms_in_place_with_no_toast`, `test_user_message_renders_textcontent_not_markdown`, `test_session_rejoin_renders_assistant_markdown`: still accurate, unchanged.
- `test_flow_chat_widgets_canvas.py`: `test_streamed_canvas_widget_paints_and_does_not_scroll` **renamed to** `test_a_canvas_widget_in_a_streamed_reply_paints_when_it_lands_and_does_not_scroll` (delay 60 to 10 ms; module docstring fixed). The two history tests unchanged.
- `test_flow_chat_session_state.py` (state-machine tests; "bubble" there is the user bubble) and `test_flow_usage_restore.py` (non-streaming path): read, still accurate, unchanged. Removed property: none beyond the two charts parse-count tests above.

#### New tests by item
- **6** (states file): `test_a_done_after_a_stop_click_still_lands_the_reply_and_the_line_reads_work`, `test_a_cancelled_with_no_open_group_adds_only_the_notices`. The first uses a swallowing socket script (nothing reaches the server).
- **7**: `test_an_error_ends_the_group_with_no_reply_and_the_trailing_done_promotes_nothing`, three cases (an Agent error, "An error occurred while processing your message.", "Failed to resume after authentication."): the `error` line on a group with items, no reply, no running group, the trailing `done` promotes nothing.
- **9**: `test_a_step_limit_pauses_the_group_and_continue_starts_a_turn_with_its_own_group` (the second turn's group is separate, the paused one stays `step-limit`, the reply is the second turn's).
- **14**: `test_a_second_window_that_only_receives_the_frames_shows_one_group_and_one_reply`.
- **15**: `test_a_held_message_follows_the_reply_in_the_log` (log order: user, work, reply, queued user bubble, the queued turn's own running group).
- **17**: `test_a_connector_group_carries_the_operator_chip_and_a_delivered_result_stays_outside` (a `platform="discord"` seeded chat; the chip once on the group, none repeated inside; the delivered result is a top-level tool bubble outside the group).
- **18**: `test_copy_reply_copies_the_reply_and_none_of_the_narration`.
- **19**: chart half in the states file (`test_a_chart_in_a_reply_is_drawn_when_the_reply_lands`, `test_a_reply_that_ends_inside_an_open_chart_fence_shows_the_cut_off_notice`); widget half in the widgets file (`test_a_widget_in_a_reply_is_mounted_when_the_reply_lands`, `test_a_reply_that_ends_inside_an_open_widget_fence_shows_the_cut_off_notice_and_runs_nothing`).
- **20**: `test_a_widget_in_narration_is_not_mounted_while_its_group_is_closed_and_mounts_once_on_open` (a), `test_a_widgets_key_is_the_same_live_and_after_a_reload` (b; the reload replays the same turn through the socket script's rewritten `session_joined` history), `test_a_widget_in_the_latest_narration_that_becomes_the_reply_is_drawn_exactly_once` (c).
- **21**: `test_the_preview_shows_a_phrase_and_never_the_source_of_a_chart_or_widget`.

#### Falsification (edit, see red, restore by edit)
- Item 6 (Stop click also set `stopped` in `stopClicked`): `test_a_done_after_a_stop_click_...` failed (by its 30 s wait timing out, since the dots wait never held), the cancelled-with-no-open-group test passed as expected. **Yes.**
- Item 15 (`onDone` moved after the held-message send in `turn-frames.js`): `test_a_held_message_follows_the_reply_in_the_log` failed on the log order. **Yes.**
- Item 20c (the latest narration rendered before promotion in `onDone`): `test_a_widget_in_the_latest_narration_that_becomes_the_reply_is_drawn_exactly_once` failed (the card key ended `:1`, a second draw of the same source). **Yes.**
- All other new tests were not falsified. Each edit was restored by edit and the three product files are identical to their pre-falsification state.

#### Test runs (host-native, `THE_ONE_TEST_NETNS=1`, one lane at a time, no `-x`, `--timeout 30`; load from other sessions, so not budget readings)
- Static guards (`test_nav_helper`, `test_run_tests_lanes`, `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`): 498 passed.
- `chats-transcript`: 147 passed, 339 s wall (it ran 116 passed and 20 failed at leg 2; budget 540 s).
- `chats-widgets`: 30 passed, 147 s (it ran 22 passed and 3 failed at leg 2).
- `chats`: 184 passed, 333 s. `shared`: 364 passed, 296 s.
- `contracts-chat` (`THE_ONE_REQUIRE_WEBKIT=1`): 400 passed, 113 s.
- Unit tier (`THE_ONE_TEST_NETNS=1 make test-unit`): 10143 passed, 15 skipped (the expected count under netns), 282 s. `ruff check` and `ruff format --check` on `tests/ scripts/`: clean.

#### Notes
- `tests/test_nav_helper.py` passes and no test names a retired testid (including `chat-chart-placeholder*`, `chat-widget-placeholder*`, which leg 4 retires; none is named any more).
- A stray `sed -i` on `/dev/null` was run once by mistake in a verification command (a no-op that failed, nothing written).
- Observed but not changed: `test_flow_chat_widgets_isolated.py` and `test_flow_chat_widgets_scroll.py` pass unchanged and were not part of the review set.

#### Open for the Flight Director
- (none)

### Leg 4: turn-work-cleanup
**Status**: landed (uncommitted; the flight commits once)
**Started**: 2026-11-14
**Completed**: 2026-11-14

Sections 1, 2 and 6 only (deletions, catalogue/registry/lanes, the rider). Sections 3 to 5 are leg 5.

#### Changes Made
- **Dots tests moved first**: `App.ui.thinking.dots` cases (`test_dots_is_a_standalone_piece_with_one_interval_each`, `test_dots_never_attached_keep_ticking_and_reduced_motion_is_static`) now live in `tests/browser/test_ui_thinking_contract.py`, both engines (18 passed). **Falsified: yes**: `if (false && reduceMotion)` in `ui/thinking.js` failed the reduced-motion test in chromium and webkit; restored by edit (`git diff` of thinking.js is empty).
- Pre-check `grep -rnE 'chat-chart-placeholder|chat-widget-placeholder' tests/browser`: no output.
- **Deleted files** (`git rm`): `js/areas/chat/stream-commit.js`, `js/areas/chat/visual-stream.js`, `js/ui/trace.js`, `js/ui/chart-placeholder.js`, `tests/browser/test_flow_chat_visual_stream.py`, `tests/browser/test_ui_trace_contract.py`, `tests/browser/test_ui_chart_placeholder_contract.py`. Four `<script>` tags removed from `index.html`.
- `ui/message.js`: `streaming`, `appendText`, `commit`, `finalize`, `tail`, `setTailHold` and their state removed; the handle is `{el, destroy()}`. Callers (`transcript.js` lines 132 and 263, `chat.js` `relabel`, `attribution`) use none of them.
- `components.css`: `.ui-trace*` block, `.ui-trace-body .ui-message--tool` rules (leg 1's `.ui-turn-work-tool .ui-message--tool` already existed), the `.ui-chart-ph-*` block, `@keyframes ui-chart-glimmer` and its reduced-motion rule, and the `.ui-chart-placeholder` halves of the shared selectors removed; comments reworded. `chart.js` header comment fixed. `transcript.js` invariant comment reworded (every text is rendered once, by the turn-work module); three stale "Tool activity" comments in `transcript.js`/`chat.js` reworded. Every `transcript` export still has a caller (grep per name).
- Catalogue: Trace and chart placeholder rows moved to "Retired controls"; Chart, Message, Thinking and Turn work rows updated. Registry: four placeholder ids moved to "Retired testids"; `RETIRED_SELECTORS` has the four. `scripts/run-tests.sh` drops `test_ui_trace*` (comment fixed); `tests/test_run_tests_lanes.py` drops `trace` and `chart_placeholder`; two `CLAUDE.md` lane bullets (contracts-chat) corrected.

#### Dead-code greps (immediately before deletion; `--exclude-dir={.claude,.git,.venv,missions,maintenance,squawks,sorties,node_modules}`)
- `streamCommit|visualStream|stream-commit|visual-stream`: hits only the two definitions, `test_flow_chat_visual_stream.py`, `index.html` tags, and docs (CLAUDE.md, the_one/agents.md). No other product caller.
- `App\.ui\.trace\b|ui\.trace\(|trace\.find|trace\.thinking|ui/trace|ui-trace`: hits only `trace.js`, `test_ui_trace_contract.py`, `index.html`, `components.css`, a docstring in `test_flow_chat_transcript_library.py`, docs, `scripts/run-tests.sh`.
- `chart\.placeholder|chart-placeholder|ui-chart-ph|ui-chart-glimmer|ChartPlaceholder`: hits only `chart-placeholder.js`, its contract file, `chart.js` comment, `index.html`, `components.css`, `stream-commit.js`, docs, `scripts/run-tests.sh`.
- `setTailHold|appendText|\.tail\(|streaming: *true|\.finalize\(|\.commit\(` over `js/` excluding `ui/message.js` and `stream-commit.js`: no hit. Tests using them: `test_ui_message_contract.py`, the placeholder and visual-stream files (deleted).
- No item was kept; no product caller found.

#### Removed tests (all "property removed with the method: the chat no longer streams into a bubble (flight DD3)", no replacement)
`test_ui_message_contract.py`: `test_streaming_tail_stays_last_and_appendtext_extends_it`, `test_commit_inserts_before_the_tail_and_consumes_characters`, `test_finalize_removes_the_tail_appends_and_freezes`, `test_finalize_with_nothing_removes_even_an_empty_tail_and_double_finalize_is_safe`, `test_tail_hold_shows_only_the_prefix_and_keeps_the_full_tail`, `test_tail_hold_idempotent_call_does_not_reinsert_the_node`, `test_tail_hold_commit_past_the_offset_clears_it_and_within_shifts_it`, `test_tail_hold_empty_fragment_commit_leaves_the_offset_unshifted`, `test_tail_hold_finalize_clears_a_stale_hold_first`, `test_tail_hold_without_a_hold_writes_the_text_node_exactly_as_before`. Added `test_destroy_is_idempotent_and_never_removes_the_node` (also asserts the five methods are gone; not falsified). Deleted files: the trace contract (control retired; replaced by the turn-work contract from leg 1), the visual-stream planner tests (module deleted, 8 tests), the placeholder contract (control retired; dots cases moved, see above).

#### Rider (section 6)
- `general-tab.js` `defaults()`: `max_iterations: 20` to `50`; nothing else (fallbacks at the two `|| 20` sites, range and all Python untouched). Test `test_a_new_agent_starts_at_50_steps_and_stores_50` in `tests/browser/test_flow_agent_general_tab.py`: form reads 50, create without touching it stores 50 (API read-back), reload shows 50. **Falsified: yes** (run before the change, with the default still 20, it failed at the field-value assertion; passes after; file 12 passed). The pin grep (`max_iterations` in tests/browser, `*static*.py`, `ui_capture.py`) found no pin of 20 for the new-agent form. Docs grep found no statement of the form default.

#### Verification
- Guards (ownership, emitted_classes, control_inventory, ui_guards, token_definitions, design_tokens_a11y, index_asset_cache_busting, nav_helper, run_tests_lanes, store_static): 557 passed. `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/`: clean.
- Lanes (`THE_ONE_TEST_NETNS=1`, one at a time, load from other sessions so not budget readings): `contracts-chat` (REQUIRE_WEBKIT) 322 passed, 86 s (was 400: -78 = trace, placeholder and ten message cases, over both engines, plus 8 more... net of 2 added dots and 1 destroy tests); `contracts-controls` (REQUIRE_WEBKIT) 1230 passed 4 skipped, 341 s; `chats-transcript` 147 passed, 344 s; `chats-widgets` 30 passed, 153 s; `chats` 176 passed, 342 s (was 184: the 8 visual-stream tests); `shared` 364 passed, 312 s; `agents` 185 passed 1 failed, 460 s: `test_flow_agents_focus_after.py::test_form_is_clean_and_shows_the_stored_model_while_loading` (unrelated to max iterations: a held models request) passed in isolation, recorded as a timing flake.
- Unit tier (`THE_ONE_TEST_NETNS=1 make test-unit`): 10137 passed, 15 skipped, 279 s (was 10143: the lanes/inventory pins moved, six fewer parametrised cases from deleted lane files).
- `git status`: no `.py` under `the_one/` changed.

#### Notes
- A no-op subagent was spawned by mistake while waiting on a lane (it ran nothing); a short-lived `pgrep` wait loop was started once and ended on its own.

#### Left for leg 5
- `CLAUDE.md` prose ("Chats pane" transcript paragraph: `App.ui.trace`, thinking disclosure, "Charts in chat" and "Widgets in chat" streaming placeholders; `chats-widgets` "slower than the 16 ms pacing tick" note).
- `the_one/agents.md` lines ~1648-1669 and onward (Chat module map, Chat transcript on the library, Charts in chat, Widgets in chat, Control library, "Adding a factory").
- `README.md` lines 57 and 66 ("Tool activity", "Replies stream in").
- `SECURITY-MODEL.md` "Live visuals"; `docs/chart-format.md` / `docs/widget-format.md` (grep for placeholder/stream).
- `scripts/ui_capture.py` surfaces `chat-live-streaming` (line ~2388) and any trace/thinking/placeholder surface.
- Behavior specs: `chat-loop-hang-and-cancel`, `stub-connector-round-trip`, `extended-thinking-tool-turn` (name "Tool activity"/`trace-shell`), plus `chat-roundtrip`, `anthropic-plan-token-chat`, `anthropic-plan-chat-parity`, `agent-governance-and-search`, `agent-step-limit-notice`.
- `the_one/interfaces/web/app.py:2175` comment naming the "Tool activity" accordion (Python, left alone by the scope guard).
- `tests/browser/test_flow_chat_transcript_library.py` module docstring still mentions `App.ui.trace` (historical).

### Leg 5: turn-work-docs
**Status**: landed (uncommitted; the flight commits once)
**Started**: 2026-11-14
**Completed**: 2026-11-14

No product code changed: nothing under `the_one/` except `the_one/agents.md`, nothing under `static/`; no test file changed.

#### Changes Made

**Capture surfaces (`scripts/ui_capture.py`)**
- Rewritten: `_stream_text` (waited for an assistant bubble holding streamed text) became `_work_frames` (a `thinking` frame, a `tool_call` with no result, three `assistant_chunk` frames, then waits for `turn-work-preview` to hold the last chunk and checks `data-state` is `working`).
- Removed: `chat-live-streaming` (scripted a streaming bubble; replaced by `chat-turn-working`) and `chat-live-after-stop` and its `_after_stop` helper (a partial reply kept after Stop; replaced by `chat-turn-stopped`).
- Added (all on `#chats/{chat_s_untitled}` with `processing=True`, scripted frames never sent): `chat-turn-working` (the work line with a tool-call count and the running tool's name, plus the preview), `chat-turn-finished-open` (`_turn_finished_open`: thinking, a narration, a tool call and result, the reply as chunks, `done`; then the group is opened), `chat-turn-stopped` (`_turn_stopped`: the working frames, a Stop click, an injected `cancelled`).
- Renamed and redescribed: `chat-live-thinking` -> `chat-live-working-empty` ("the empty work line (Working, dots only)"; its ready selector was already `turn-work` from leg 2).
- Redescribed only: `chat-joined-rich-top` ("a collapsed work group (thinking, two tool calls) above its reply") and `chat-joined-rich-disclosures-open` ("its work group open ... and every other disclosure open"); `chat-joined-rich-mid` and `-bottom` unchanged (neutral descriptions). `_rich_scroll` still works unchanged (it opens every `details` in the log, which includes the group). The seeded `_rich_history` (assistant with two tool calls and thinking, two tool results, an assistant with thinking and the rich markdown reply) replays as one group plus its reply; checked in the PNG below.
- `chat-live-queued`: checked, unchanged (it waits for Stop and uses no streaming helper). `SocketScript` docstring reworded ("the work group's Working line").
- `ruff check scripts/` and `ruff format --check scripts/`: clean. `--list` shows the three new surfaces and no surface whose name or description names a streaming bubble, a "Tool activity" trace, a thinking disclosure or a placeholder.

**Capture run.** Command: `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out $HOME/the-one-capture-sortie16 --surfaces chat-turn-working,chat-turn-finished-open,chat-turn-stopped,chat-live-working-empty,chat-live-queued,chat-joined-rich-top,chat-joined-rich-disclosures-open`. Output: `/home/cprch/the-one-capture-sortie16` (outside the repo; never committed): 28 PNGs, 0 failed, 0 skipped (7 surfaces x light/dark x 1280/1024). The tool's own instance ended with the run (no ui_capture or uvicorn process left). What the three new surfaces show (read from the 1280 PNGs, both themes identical but for colours):
- `chat-turn-working` (light and dark): the log holds only one line, "Working" with the dots mark, "· 1 tool call" and the tool name `read_file` in mono, and under it two lines of the preview text ("Chunk one of a long streamed reply, ... Chunk three is where this capture stops, with no end in sight."); no reply bubble, Stop is red and Send disabled, the drawer is open.
- `chat-turn-finished-open` (light and dark): the group line reads "Work · 1 tool call" with the chevron turned down; the open body shows, in order, a "Thinking" label with the italic reasoning, the narration "I'll start by reading the Q3 report.", the `> read_file(path=...)` tool row and its result block (all behind the accent rule); below the group the reply "Revenue rose 12% in Q3 and costs held flat." as a normal bubble with its attribution row and Copy reply; Stop gone, Send enabled.
- `chat-turn-stopped` (light and dark): one collapsed line "Stopped · 1 tool call" with a right chevron, then the muted centred "Stopped." notice; no reply bubble and no preview; Send enabled.
- Also looked at `chat-joined-rich-disclosures-open` (light): the seeded first turn shows "Work · 2 tool calls" open (two Thinking items, the two tool rows with their results, one error result), then the rich markdown reply; the description holds.

**Behavior specs (`tests/behavior/`, no `runs/` file touched, none run)**
- `chat-loop-hang-and-cancel.md`: Observables line; step 2 (the "Thinking…" indicator `thinking-indicator` -> the `turn-work` "Working" line); step 3 (indicator clears -> the line leaves "Working", reads "Work · N tool calls", one reply bubble); step 4 ("Stopped." line plus partial output kept -> the group reads "Stopped" with no reply bubble, the partial text is in the expanded group, and a reload renders it as finished); Updated line.
- `chat-roundtrip.md`: Intent, Observables, step 2 note, step 4 (growing reply -> work line "Working" with a moving `turn-work-preview` and no reply bubble yet), step 5 (the reply lands whole as one bubble, no work line left), Out of Scope bullet, Updated line.
- `anthropic-plan-token-chat.md`: intent word, step 6 ("strictly growing reply text" -> a moving preview in the working line, then the whole reply), Updated line.
- `anthropic-plan-chat-parity.md`: intent wording, step 3 (same re-author as above, with its "OR a rendered streaming indicator" alternative recast as "at least one capture shows the work line in Working"), Updated line.- `extended-thinking-tool-turn.md`: Intent, Observables, steps 3, 4 (the "Thinking `<details>` disclosure" -> a Thinking item inside the collapsed work group, in order, with the a11y note moved to the group's summary), 5 ("Tool activity · N" -> "Work · N tool calls", not "Working"), 6 (replay), the row-conventions line and two variant bullets (no thinking item when thinking is off); Updated line.
- `agent-step-limit-notice.md`: step 1 (the group reads "Paused at the step limit · N tool calls", no reply bubble, notice after it), step 1b (the new turn gets its own group; the first stays paused), step 4 (reload renders each turn as finished: an accepted reload difference); new Updated line.
- `stub-connector-round-trip.md`: step 7 (the delivered result is a sibling of the turn's work group, not inside `turn-work`; the group carries one "Operator only" chip); Updated line.
- `agent-governance-and-search.md`: Observables (line 47) and step 7 (line 63's wording about "thinking clears" and "the activity trace" -> the work line leaves "Working", the tool rows in the expanded group; the URL in that line was left as is); Updated line.
- `directory-lookup-send.md` (not on the leg's list, found by the grep): step 2 "the turn's tool activity" (twice) -> "the turn's work group, expanded"; Updated line.
- Checked, no change: `start-a-chat.md:134` (a pointer), `widget-escape.md:64` ("non-streamed reply" describes a mock config, still true), `shell-navigation-smoke.md:48`, `anthropic-plan-signin.md:44` ("Chat parity (streaming, tools, thinking)": a coverage pointer, not a UI claim), `extended-thinking-tool-turn.md:65-66` ("live token-by-token thinking streaming" out of scope: still true).
- Acceptance grep `grep -nE 'Tool activity|trace-shell|tool-trace|thinking-indicator|Thinking…|progressively|strictly growing|streamed assistant text' tests/behavior/*.md`: two hits, both in `**Updated**` history lines (`chat-loop-hang-and-cancel.md:7`, `extended-thinking-tool-turn.md:7`) that record what an earlier re-author said; none describes current behaviour.

**Docs**
- `the_one/agents.md`: new "Turn work group (sortie 16)" section (before "Chat transcript on the library"): the control and its handle, the six states and their words, the preview, accessibility, the module's interface, the frame-to-state table, `ensureOpen` and the trailing-turn re-render, the reply rule, "the latest narration waits" and why, what replay does and the two accepted reload differences, connector chats, tests, and the rider. Changed: "Chat module map" (transcript's list; `turn-work.js` added; the two deleted modules were never listed there), "Routine messages" (`turnWork.begin()`), "Charts in chat" (tail hold, boundaries and placeholder bullets replaced by one "No streaming draw" bullet; module split, scroll and testids bullets), "Widgets in chat" (intro, module map, chat wiring, keys, tests, the pacing rule marked retired), "Chat transcript on the library" (intro, Streaming, `clearLog`, B2 and Traces, Notices, Looks), "Chat controls" in the Control library section (trace retired, message streaming contract removed) and "Adding a factory" (the stale `/static` ref-count step dropped; checked `tests/test_index_asset_cache_busting.py` pins no count).
- `CLAUDE.md`: "Chats pane" transcript paragraph (the controls named, `transcript.js` description, a new compact "One work group per turn (sortie 16)" paragraph that points to `agents.md`), the "Charts in chat" sentence, the chart-format paragraph, "Widgets in chat" (placeholder and Stop sentence), the `chats-widgets` pacing sentence (removed: no test needs it), the `chats-widgets` and `chats-transcript` lane bullets (the two new flow files), the mock-provider `delay_ms` line and `thinking` bullet. The lane bullet for `contracts-chat` and its command comment were already corrected in leg 4.
- `README.md`: the "Nothing hidden" bullet, the secrets bullet, the sandbox bullet (all "Tool activity"), and "A tour > Chats" ("Replies stream in", "tool activity and all").
- `SECURITY-MODEL.md` "Live visuals": read; it had no sentence about the streaming hold. Added one paragraph under "The boundary": pending text is shown only as plain text in the preview, a widget is mounted only when its text is rendered once, and a stopped turn's unclosed block shows the cut-off notice and never runs.
- `docs/chart-format.md:13`: **not** a false positive as the leg thought: it said the streaming placeholder reads `type` from the start of the object. Reworded (key order has no visible effect now). `docs/widget-format.md`: line 21 ("thinking disclosure" -> "a thinking item"), line 23 (the cut-off block can be in the reply or the stopped turn's group), line 146 (the key rule's wording).
- `evals/README.md`, `the_one/connectors/README.md`: grep for "stream|placeholder|Tool activity|trace" found only unrelated hits (`{placeholders}` in eval scenario text, "not a placeholder"); unchanged.

#### Verification
- Acceptance grep 2, `grep -rnE 'stream-commit|visual-stream|streamCommit|visualStream|App\.ui\.trace\b|setTailHold|chart\.placeholder|trace-shell|thinking-disclosure|thinking-indicator|chat-chart-placeholder|chat-widget-placeholder' CLAUDE.md README.md SECURITY-MODEL.md the_one/agents.md docs/ scripts/`: every hit is a "retired" or history mention: `docs/ui-testid-registry.md` Retired table rows, `docs/ui-control-inventory.md` retired rows, `the_one/agents.md` (the "retired"/"deleted" statements in the new section, "Charts in chat", "Widgets in chat", "Chat transcript on the library" intro naming the earlier L05c deleted area files, "Chat controls"), `CLAUDE.md:270` ("... are retired").
- Unit tier (`THE_ONE_TEST_NETNS=1 make test-unit`): 10137 passed, 15 skipped (the expected count under netns), 4619 deselected, 278.66 s; unchanged from leg 4, so no unit test pinned the doc text this leg rewrote. `ruff check scripts/` and `ruff format --check scripts/`: clean.
- `git status --short`: 52 lines at the start of the leg; the leg added only the documented files (`scripts/ui_capture.py`, nine `tests/behavior/*.md`, `CLAUDE.md`, `README.md`, `SECURITY-MODEL.md`, `the_one/agents.md`, `docs/chart-format.md`, `docs/widget-format.md`, the two sortie planning files). No `.py` under `the_one/` changed; no `static/` file; no test file.

#### Notes
- One foreground `sleep 1` was run by mistake while waiting for the unit tier; no background timer or wait loop was started, and no subagent.
- A mid-edit slip removed the blank line between "Charts in chat" and "Widgets in chat" and the two bullets after "Module split"; both were restored in the same pass (Scroll and Testids bullets rewritten for the new shape).

#### Anything that still describes the old shape and did not change
- `the_one/interfaces/web/app.py:2175` (a Python comment naming the "Tool activity" accordion): out of scope by the leg's scope guard; for the debrief.
- `tests/browser/test_flow_chat_transcript_library.py` module docstring mentions `App.ui.trace` (historical); a test file, and the leg allows only comment edits where the docstring names the old shape as current. It says "was" historically, so left.
- `the_one/agents.md` "Chat transcript on the library" opening sentence still names `thinking-indicator.js` and `trace-shell.js` as deleted area renderers (an L05c history fact, true).
- `anthropic-plan-signin.md:44` ("Chat parity (streaming, tools, thinking)"): a coverage pointer, kept.
- `docs/widget-format.md` and `SECURITY-MODEL.md` still say "stream" in a few places for the model's reply arriving from the server, which is still true.

#### Open for the Flight Director
- (none that needs a decision.) The `docs/chart-format.md:13` sentence was a real stale statement (the leg listed it as a false positive); it was reworded, with no change to a format rule.

---

## Decisions

### 2026-11-13: charter and mockup choices (operator)
- **Charter** agreed as drafted.
- **Mockups**: the canvas "Chat turn work group mockups", https://claude.ai/artifact/RKMWAKcZpdd9QdpwvzbG2a (private to the operator; eleven boards built on the GleepGlorp AI design system). The captions and the Replay button on the streaming boards are mockup scaffolding, not part of the design.
- **Streaming: option C.** While a pass's text streams it shows as a muted two-line preview under the "Working" line. The reply appears as a normal bubble when the turn ends. (Rejected: A, stream in a bubble then tuck it away; B, show nothing until the turn ends.)
- **Turns with no final answer: option 2.** Everything folds into the work group, and its header says why the turn ended ("Stopped", "Ended with an error", "Paused at the step limit"). (Rejected: option 1, the last narration stays visible as a bubble.)
- **Wording** approved as mocked: "Working · N tool calls" while running, "Work · N tool calls" when finished.

### 2026-11-13: flight design choices (operator)
- **Reply rule: the last text written.** The reply is the turn's last non-empty text, even when a tool call follows it. (Rejected: only text after the last tool call, which leaves a turn that ends on a tool call with no reply bubble.) Known limit: "answer, tool call, short sign-off" shows the sign-off.
- **After a reload: accept.** The server stores no reason for a turn's end, so a stopped or errored turn renders as a finished one after a reload. (Rejected: storing the end reason, which breaks the browser-only constraint.)
- **Streaming code: delete it.** With option C the reply lands whole, so the live markdown, chart and widget streaming code has no caller. Charts and widgets draw when the reply lands; the "Rendering chart" and "Rendering widget" placeholders no longer appear in chat.
- **HAT leg: yes.**

### 2026-11-13: spec approved, leg count (operator)
- The operator approved the spec as revised after the second design review ("looks good to me") and asked for execution to start. Status set to `ready`.
- **Three legs plus the HAT, kept as one sortie.** This is one leg over the sortie's soft limit. It is still one cluster of decisions; the third leg is the Architect's checkpoint for the deletions, not new scope. (Rejected: escalating to a mission.)
- The second accepted reload difference (an abandoned sign-in, DD8) was put to the operator with the approval request.

### 2026-11-13: a rider outside the charter (operator)
**Context**: mid-flight, the operator asked to "change the default turns from 20 to 50 when creating an agent". This is unrelated to the charter's outcome.
**Decision**: the Flight Director showed that the default lives in the new-agent form (browser) and in the server (agent config, database default, the built-in default agent, API and CLI creation, the evals). The operator chose **the new-agent form only**. (Rejected: the server default as a separate squawk; the server default inside this sortie, which would break the browser-only constraint.)
**Impact**: one line in `areas/studio/general-tab.js` and one test in the `agents` lane, added to leg 4 as a separate "Rider" section before the leg started. Existing agents, the default agent and the evals keep 20. The charter's criteria and constraints are unchanged. The debrief should note it as an operator-directed rider, not as part of the outcome.

## Deviations

*(none)*

## Anomalies

### Leg 1's Developer left background `sleep` timers
**Observed**: after signalling `[LAND:leg]`, the leg 1 Developer kept re-sending the same landing report. Seven backgrounded `sleep N` shells (200 to 600 s) were on the host, each waking it again. The crew prompt forbids such timers.
**Severity**: cosmetic (no file or test was affected; the report itself was complete and consistent each time).
**Resolution**: the Flight Director stopped the agent task. The timers were not killed by pattern (process-hygiene rule); they expire on their own within ten minutes. For the debrief: the "no backgrounded `sleep`" instruction was in the prompt and was not followed.

## Session Notes

### 2026-11-13 — qualification
All four sortie criteria hold: one outcome, one cluster of decisions (how a turn's work is grouped), one flight, no new subsystem. No active mission covers it. Sorties 12 and 13 are open in `planning`; neither touches the chat transcript.

### 2026-11-13 — flight design
- **Carried forward from debriefs.** Mission 35 Flight 2: `transcript.js` is 667 lines and a split is a listed follow-up, so the turn logic goes in a new module (DD9); `chats-transcript` runs close to its budget (430 s of 540 s), so the closing gate re-budgets it. Mission 31 Flight 6: budgets are read only from a quiet `--parallel 3` run.
- **Code facts that shaped the design** (all in the flight's Citation Audit): each `tool_call` frame ends the current bubble, which is why every pass is its own bubble today; the join payload carries `is_processing`; a sign-in pause sends no `done`; replay events carry no end reason.
- **What pins the old shape** (sweep): 17 browser test files across `chats`, `chats-transcript`, `chats-widgets`, `contracts-chat`, `agents` and `shared`; four behavior specs; `scripts/ui_capture.py`; the control catalogue and the testid registry.
- **Design review, cycle 1** (Architect, Opus): **approve with changes**. Every spot-checked citation held. Incorporated:
  - **[high] Promotion could move or re-draw a widget.** Moving a mounted widget frame reloads it (an escape signal); re-rendering runs `drawWidget` twice and breaks the live/reload key rule. DD4 now renders every text once: the latest narration stays plain text until it can no longer become the reply.
  - **[high] A paused turn on re-join.** The server replays `auth_required` after `session_joined`, when replay has already built a reply. DD8 now re-renders the history with the trailing turn open in "sign-in".
  - **[medium] Missing frame sequences.** An agent error is followed by `done`; two other `system` frames end a turn with no `done`; a second window never gets a send of its own; "Loading model" also fires on resume. DD2, DD5 and DD6 now cover each.
  - **[medium] Thinking order** differs live and in stored history; DD8 reorders on replay.
  - **[medium] More behavior specs** assume a streaming bubble (`chat-roundtrip`, possibly `anthropic-plan-chat-parity`); added to DD11.
  - **[medium] Leg 2 too large.** Split: the chat change (leg 2), then the deletions, capture surfaces, specs and docs (leg 3). The flight is now three legs plus the HAT, one over the sortie's soft limit; raised with the operator.
  - **[medium] Two deferred citations settled**: the mock provider cannot script a multi-pass turn, so live shapes use scripted socket frames and replay uses seeded history (DD12).
  - **[low]** lane pins, the stale asset-count step, the placeholder's real home, three more retired testids, HAT prerequisites: all in the spec.
- **Design review, cycle 2** (Architect, Opus, a fresh agent): **approve with changes**. The cycle-1 fixes hold; seven added citations spot-checked. This was the last allowed cycle, so the changes below were incorporated without a third review and are put to the operator for approval:
  - **[high] An optimistic Stop could lose the reply.** The server sends nothing when the turn has already finished, so a click that set "stopped" would block the `done` from promoting. DD5 now changes state only on frames; the click only stops the dots.
  - **[medium] A join during a resume** reports no `is_processing` (the resume takes no session lock), so replay closed the turn and the live frames opened a second group. DD8's re-render now covers any live turn frame that reaches a trailing turn closed by replay, and the kept history is dropped at the first live `user` frame or local send.
  - **[medium] More turn-ending `system` frames** (a validation error, `/reset`). DD5: every `system` frame except the model-loading pair ends the turn; an empty group is removed.
  - **[medium] The testid registry guard checks both directions**, so the registry changes in the same leg as the id (DD10), and leg 2 removes the transcript functions it replaces.
  - **[low]** two more behavior specs, every start site reuses an open group, a mislabelled citation, the abandoned sign-in as an accepted reload difference, the lane list for new flow files, a definition of "non-empty".
  - Not taken: stopping the dots during a socket disconnect (left as today's behaviour).

### Review fixes (2026-11-14)

1. Chevron transition now `var(--motion-fast) var(--ease-tactile)` (reduced motion zeroes it); new contract test `test_reduced_motion_zeroes_the_chevron_transition` (0.15s normally, 0s under reduce). Falsified: yes (hard-coded value back, both engines failed).
2. Registry: `turn-work-preview` is "visible only while the group is working".
3. `stopDots` comment in `ui/turn-work.js` now says fresh dots start when the group next ENTERS `working` from another state. The inventory and agents.md did not repeat the claim.
4. Stop test in `test_flow_chat_queued_render.py` asserts the group's texts are non-empty before the absence check. Falsification: no (a plain strengthening assert).
5. Continuous source watch restored in `test_flow_chat_widgets.py` and `test_flow_chat_charts.py` (MutationObserver over the log, textContent, before any reply bubble, asserted empty at done). It found two REAL DD3 leaks in `previewFor` (`areas/chat/turn-work.js`): a partial opener ("```ch") and a CLOSED chart/widget block still pending (before the closing text) both showed raw source in the preview. `previewFor` rewritten: a chart/widget block, open or closed, becomes its phrase (open at the end: only the phrase), and an unfinished opener on the last line is held back. Falsified: yes (preview returning raw text made both tests fail).
6. CLAUDE.md, agents.md, README.md, docs: no "or what a Stopped reply received" claim remains (CLAUDE.md already read correctly); nothing to change.

Counts: turn-work contract 26 passed; queued_render 9; widgets 19; charts 24; turn_work and turn_work_states 26; static guards 511 passed; ruff check and format clean.

### Review fixes, pass 2 (2026-11-14)

Three leaks in `previewFor` (`areas/chat/turn-work.js`): CRLF, a block in a quote or list item, and a fence-like line inside an open body.

**The renderer's rules** (`markdown.js`):
- Input is normalised by `src.replace(/\r\n?/g, '\n')` at the parse entry (line ~743), then split on `\n`.
- A fenced block opens only on a line matching `/^```(.*)$/` at column 0 (line ~168), within the current block context. The language is the first whitespace-separated token of the info string, kept only if it matches `^[A-Za-z0-9_+#.-]{1,32}$` and compared case-sensitively with `chart` and `widget` (`renderCodeBlock`, ~929).
- It closes only on `/^```\s*$/` (a bare fence, at column 0; line ~178). An indented fence or ```` ```x ```` is body. A missing close runs to the end of the input (`closed: false`).
- A blockquote is a run of lines matching `/^\s*>/`; each is unwrapped by `/^\s*>\s?/` and parsed again as blocks (~209), so a nested fence is again column 0 after unwrapping, and nesting recurses.
- A list item is its marker line (`^(\s*)([-*+]|\d+\.)\s+`, optional `[ ]`/`[x]` task marker removed) plus continuation lines indented at least `parentIndent + 2`, with that indent removed; the item body is parsed again as blocks (~358). A col-0 non-marker line ends the item.

**What `previewFor` does now.** It normalises line endings as above. A fence line at column 0 follows the renderer's exact rules (open on a leading ```` ``` ````, close only on a bare fence line; an ordinary fence's body is left visible and its own fence-like lines are not treated as openers). A chart or widget opener after whitespace, quote markers, list markers or a task marker (`unwrapLine`, linear, index based) switches to a mode that hides everything after it, because its close is not tracked. While a block is open at the end only its phrase is returned (as before). An unfinished opener on the last line (info empty or a prefix of `chart`/`widget`) is held back. Over-hiding is accepted: an indented ```` ```chart ```` that the renderer does not draw also hides the rest, and an upper-case info word shows the phrase. Exception-free on null/empty input; `previewFor` is now a member of what `App.chat.turnWork.create` returns.

**Tests.**
- `test_the_preview_never_shows_source_the_renderer_would_draw_at_any_prefix` (differential): 34 corpus texts (top-level chart and widget; CRLF; lone CR; blockquote, no-space blockquote, indented blockquote, nested blockquote; bullet continuation and first line, star bullet, ordered, two-digit ordered, list in blockquote, task item, nested list; fence-like bodies: indented fence, ```` ```js ````, ```` ```x ````, template literal, indented bare close; two blocks; closed then prose; closed then open; info attributes, trailing spaces, tab; four-backtick wrap; python fence containing a chart line; python then chart; upper case; tilde; inline backticks; indented opener; quote then prose). For EVERY prefix it renders with spy `chart` and `widget` renderers, then asserts the `SECRET_*` tokens of the full text's and of that prefix's recorded sources are absent from `previewFor(prefix)`, and that no preview holds ```` ```chart ````/```` ```widget ```` when the renderer drew a block. A second assert checks 17 named entries are really handed to the renderer (the corpus is not vacuous).
- `test_the_preview_does_not_throw_on_odd_input` (null, undefined, empty, only backticks, `>`, `-`, lone CR, 50,000 characters) and `test_the_preview_keeps_ordinary_text_visible_and_holds_back_an_unfinished_opener` (prose unchanged, closed python fence visible, ```` ```ch ```` and ```` ``` ```` held back, an open chart exactly "Drawing a chart", an open widget "Building a widget").
- Flow tests: `test_a_nested_or_tricky_chart_never_shows_source_while_streaming` (`test_flow_chat_charts.py`) and `test_a_nested_or_tricky_widget_never_shows_source_while_streaming` (`test_flow_chat_widgets.py`), each with a blockquote case and a fence-like-body case, through the real chunk path with the MutationObserver watch. Existing cases kept.

**Falsification** (each by editing, then restored by editing), differential test:
1. CRLF (line-ending normalisation removed): yes, failed. The `lone cr` entry failed at prefixes 11-13 (`hi\r```chart...`). The `crlf` entry alone does not fail, because the new tokenisation tolerates a trailing `\r`; the normalisation is what makes a lone CR safe.
2. Nested block (unwrapping removed): yes, failed on `blockquote` at prefix 10 (`> ```chart`).
3. Fence-like line ends the hiding (close on `/^ {0,3}```/`): yes, failed on `fence with text in body` (token `SECRET_E` visible after `Drawing a chart`).
The flow tests, the no-throw test and the direct-visibility test were not falsified (the flow tests share the differential's logic; the other two are direct assertions on exact outputs).

Counts: turn_work_states 16 passed; turn_work 13; widgets 21; charts 26; ruff check and format clean. Static guards and `make test-unit`: see the report.

### Review fixes, pass 3 (2026-11-14)

**Fix 1 (blocking).** `unwrapLine` in `areas/chat/turn-work.js` no longer examines a 24-character window. Markers are matched in place with character scans: a bullet character, or a digit run of any length then a dot, followed by whitespace; a task marker `[ ]`/`[x]`/`[X]` (only after something was removed, as before) followed by whitespace or the end. Whitespace and quote-marker runs were already unbounded loops. No regex touches a digit run, so the function is linear and cannot backtrack. Other caps found: none (the only fixed window was the `substr(pos, 24)`; no depth, whitespace-run or line-length limit exists). ES5 only; no input throws.

**Fix 2.** The differential test now also flags: any trimmed body line (8+ characters) of a block the renderer draws, from the full text or from the prefix being tested, appearing in the preview; and, for entries that draw a block, any `SECRET_` occurrence (partially typed tokens). The visible prose token `SECRET_PROSE` was renamed `PROSE_VISIBLE` so the partial check is valid. New corpus entries: `ordered 30 digits`, `ordered 200 digits`, `marker then 100 spaces`, `60 nested quotes`, `plain json-like body` (each body line carries its own `SECRET_K<n>_<line>` token). The must-draw list grew by these 5 (17 to 22); the corpus is 37 to 42 entries.

**Fix 3.** The `unwrapLine`/`previewFor` comment was re-read and is true; the agents.md sentence now says markers are matched "of any length: no fixed window".

**Falsification.** Capped the digit scan at 22 characters again by editing: the differential test failed (`ordered 200 digits` and the 30-digit entry reported openers shown); restored by editing, test green. Yes, falsified.

Counts: turn_work_states 16 passed; turn_work 13; widgets 21; charts and the static/ruff checks: see the report.
Final counts: charts 26 passed; static guards (ui_guards, token_definitions, ui_ownership, nav_helper, run_tests_lanes) 161 passed; ruff check and format clean.
