# Leg: turn-work-tests

**Status**: completed
**Flight**: [One work line per chat turn](../flight.md)

## Objective
Finish the test work for the new turn shape: rewrite the 23 flow tests leg 2 left failing, add the remaining flow tests, and leave every chat lane and the unit tier green.

## Context
- Leg 2 landed the new shape: one `turn-work` group per turn, the reply as one bubble at `done`. Read its flight-log entry ("### Leg 2: turn-work-in-chat") for the module's interface names, the new `_chats.py` helpers and the exact failing list.
- Flight DD3 (the preview, the reply lands whole), DD4 (the reply rule, every text rendered once), DD5 (turns with no final answer, Stop changes state only on frames), DD6 and DD7 are what these tests pin.
- The 23 failing tests all assert on something that no longer exists before `done`: a streaming assistant bubble, a chart or widget placeholder, or a Copy button on a reply that has not landed.
- Leg 4 (`turn-work-cleanup`) deletes the dead code. This leg does not delete product files and does not edit `js/ui/`.
- Nothing is committed in this leg.

## Inputs
- Legs 1 and 2 landed, uncommitted, in the tree.
- `tests/browser/test_flow_chat_turn_work.py` with 13 tests (flow items 1 to 5, 8, 10 to 13, 16) and the `_chats.py` turn helpers.
- Leg 2's runs: `chats` 184 passed; `shared` 364 passed; `chats-transcript` 116 passed, 20 failed; `chats-widgets` 22 passed, 3 failed; `contracts-chat` 400 passed. The unit tier had one failure, a source-shape pin in `tests/test_store_static.py` that leg 2 then fixed; the full unit tier has not been re-run since.

## Outputs
- The 23 tests rewritten or removed, each accounted for in the flight log.
- New flow tests for items 6, 7, 9, 14, 15 and 17 to 21.
- Green lanes: `chats`, `chats-transcript`, `chats-widgets`, `shared`; a green unit tier.

## The work

### 1. Rewrite the 23 failing tests
For each test: if its property still exists in the new shape, rewrite it (keep the test, change how it observes; rename it when the name describes the old shape). If its property is gone, remove it and record "property removed" with one line of reason.

- **`test_flow_chat_queued_render.py` (9 tests)**: all go through the helper `_running_turn`, which waits for a streamed assistant bubble. Rewrite the helper to wait for the turn's group in `working` (and, where a test needs text to have arrived, for the preview). The nine properties (the queue chips, cancel, focus, order, the cap, announcements) all still exist. Expect all nine to stay.
- **`test_flow_chat_transcript_library.py` (8 tests)**:
  - `test_copy_reply_copies_the_stored_content_live_and_on_replay`, `test_an_empty_reply_has_no_copy_and_delivered_results_have_none`: Copy exists once the reply lands; assert after `done`.
  - `test_a_stopped_streaming_reply_keeps_every_received_character`: the property is now "a stopped turn keeps every received character **inside the group**" (flight DD5); rewrite and rename.
  - The four Stop tests and `test_an_agent_error_discards_the_whole_queue_and_sends_nothing`: the notices and the queue rules are unchanged; only the wait for a streaming bubble changes.
- **`test_flow_chat_charts.py` (3 tests)** and **`test_flow_chat_widgets.py` (3 tests)**:
  - The two "shows the placeholder then the chart/card before the stream ends" tests and `test_a_chart_and_a_widget_stream_in_one_reply`: the placeholder property is gone (flight DD3, DD10). Replace each with the new property: while the block streams, the preview reads "Drawing a chart" / "Building a widget" and no chart, card or raw source is in the log; at `done` the chart or card is in the reply. Rename accordingly.
  - `test_chart_and_placeholder_fill_the_reply_width`: keep the chart half (a chart in a landed reply fills the reply width); the placeholder half is removed.
  - The two "stop in the middle of a block" tests: the property is now "a stopped turn's text is folded into the group; an unclosed chart block there shows the cut-off notice, and an unclosed widget block never runs" (flight DD5 with the kept `closed: false` handling). Rewrite and rename.

### 2. Review the streaming tests that still pass
`test_flow_streaming.py` and `test_flow_markdown_chat.py` passed after leg 2, and three more files use `stream_chunks`: `test_flow_chat_widgets_canvas.py`, `test_flow_chat_session_state.py`, `test_flow_usage_restore.py`. Read each test in these five files. A test whose name or docstring claims a live-streaming property that no longer exists (text growing in a bubble, the pacing, the safe markdown commit mid-stream) but which now passes only because it checks the final content is misleading:
- if the final-content check is worth keeping, rename the test and fix its docstring to say what it checks now;
- if another test already covers that final content, remove it and record "property removed".
Do not change tests that are still accurate.

### 3. New flow tests
Add to `tests/browser/test_flow_chat_turn_work.py`; if it would pass about 700 lines, put the new ones in `tests/browser/test_flow_chat_turn_work_states.py` and add that file to `chats_transcript_pat` in `scripts/run-tests.sh` and to the pin in `tests/test_run_tests_lanes.py`. Widget cases (the widget half of 19, and 20) go in `tests/browser/test_flow_chat_widgets.py`, which is already in the `chats-widgets` lane. Script live frames with `_chats.emit_frame`; seed replay with `seed_session(messages=...)`. Each test asserts the whole turn's shape, including what must be absent.

- **6. Stop racing `done`**: after a Stop click (the dots stop, the state is still `working`), a `done` still lands the reply and the line reads "Work"; separately, a `cancelled` that arrives with no open group adds only the notices and no group.
- **7. Errors**: an "Agent error" `system` frame followed by `done`; "An error occurred while processing your message."; "Failed to resume after authentication.". Each: the `error` line on a group with items, no reply bubble, no running dots, and the trailing `done` promotes nothing.
- **9. Step limit**: `step_limit` then `done`: the "Paused at the step limit" line, the notice with Continue, no reply; clicking Continue sends `continue` and the next turn has its own group.
- **14. A second window**: a `user` frame then a turn's frames, with no local send: one group, one reply.
- **15. A held message**: with a message held, `done` lands the reply and then the queued message's bubble, in that order in the log.
- **17. A connector chat**: the group carries the "Operator only" chip; tool rows inside it carry none; a delivered tool result is a top-level bubble outside the group.
- **18. Copy reply**: the copied text is the reply's source and contains none of the narration.
- **19. Visuals in a reply**: a chart and a widget in a reply are drawn when the reply lands; a reply that ends inside an open widget fence shows the cut-off notice and no frame runs.
- **20. A widget in narration**: (a) while the group is closed the widget is not mounted; opening the group mounts it once; (b) its key is the same live and after a reload; (c) when the latest narration becomes the reply at `done` (a turn that ends on a tool call), its widget is drawn exactly once.
- **21. The preview never shows visual source**: while a chart or widget block is streaming, the preview shows the phrase, and no text of the block.

### 4. If a new test finds a product defect
- A defect inside the chat modules (`areas/chat/*.js`, `areas/chat.js`) that contradicts the flight's design decisions: fix it here, keep the fix minimal, and record it in the flight log with the test that found it.
- A defect that needs a change under `js/ui/` (for example, item 20: a widget inside a closed `<details>` mounts anyway, or a card adopted at width 0 loses its height, `widget.js:191-199`), or any design question: do not edit `js/ui/`. Mark the test `xfail(strict=True)` with the reason, record it in the flight log under "Open for the Flight Director", and finish the rest. This is the one case where `xfail` is authorized in this leg.

## Acceptance Criteria
- [ ] Each of the 23 tests leg 2 listed is rewritten and passing, or removed; the flight log lists all 23 with "rewritten", "renamed to ..." or "removed: property removed (reason)".
- [ ] The five streaming test files are reviewed; every test whose name or docstring claimed a removed live-streaming property is renamed or removed, and listed.
- [ ] Flow tests for items 6, 7, 9, 14, 15, 17, 18, 19, 20 and 21 exist and pass, or are `xfail(strict=True)` with a recorded `js/ui` defect.
- [ ] Falsified (yes or no reported for each): item 6 (make the Stop click set `stopped`), item 15 (send the held message before the promote), item 20c (render the latest narration before promoting it).
- [ ] No test names a retired testid; `tests/test_nav_helper.py` passes.
- [ ] `chats`, `chats-transcript`, `chats-widgets` and `shared` pass in full with `THE_ONE_TEST_NETNS=1`; `contracts-chat` passes with `THE_ONE_REQUIRE_WEBKIT=1`.
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes (12 or 15 skips, see CLAUDE.md "Expected unit skip count"); `ruff check` and `ruff format --check` on `tests/ scripts/` are clean.
- [ ] Any product file changed is under `areas/chat` and listed with its reason; nothing under `js/ui/` and no Python under `the_one/` changed in this leg.

## Verification Steps
- One file: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/<file> -m browser -x --timeout 30`.
- Lanes, one at a time, each in the background: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane> --timeout 30 -q` for `chats-transcript`, `chats-widgets`, `chats`, `shared`; `contracts-chat` with `THE_ONE_REQUIRE_WEBKIT=1`.
- `THE_ONE_TEST_NETNS=1 make test-unit` at the end.
- Record each lane's pass count and wall time. The host may be busy, so these are not budget readings; say so.

## Implementation Guidance
1. Read leg 2's flight-log entry, `tests/browser/_chats.py` (the turn helpers), `tests/browser/test_flow_chat_turn_work.py` (the pattern for scripted frames and seeded replay), and `the_one/interfaces/web/static/js/areas/chat/turn-work.js`.
2. Fix `_running_turn` first; it unblocks nine tests.
3. Rewrite the remaining failing tests file by file, running each file as you go.
4. Review the five streaming files.
5. Add the new flow tests, then falsify the three named ones.
6. Run the lanes and the unit tier; triage any failure in isolation before calling it a regression.

## Edge Cases
- **Mock-provider turns** (`stream_chunks`, `delay_ms`): a real turn's text is only in the preview until `done`; a test that needs "the turn is running" waits for the group's `working` state, not for text.
- **Mock streams in the widget flow tests must be slower than the 16 ms pacing tick** (CLAUDE.md, `chats-widgets`); that rule concerned the old pacing. If a test only needs the reply after `done`, the delay can go; do not keep a delay whose reason is gone.
- **`emit_frame` needs a joined chat** for session-scoped frames to pass the frame gate.
- **Copy** needs clipboard permission in the test context; follow what the existing Copy test does.
- **Lane membership**: a new `test_flow_chat_*` file lands in `chats` unless it is added to `chats_transcript_pat`.

## Files Affected
- `tests/browser/test_flow_chat_queued_render.py`, `test_flow_chat_transcript_library.py`, `test_flow_chat_charts.py`, `test_flow_chat_widgets.py` - rewrites.
- `tests/browser/test_flow_streaming.py`, `test_flow_markdown_chat.py`, `test_flow_chat_widgets_canvas.py`, `test_flow_chat_session_state.py`, `test_flow_usage_restore.py` - reviewed; renamed or trimmed where misleading.
- `tests/browser/test_flow_chat_turn_work.py` (and possibly `test_flow_chat_turn_work_states.py`), `tests/browser/_chats.py` - new tests and helpers.
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` - only if a file is added or removed.
- `the_one/interfaces/web/static/js/areas/chat/*.js` - only for a defect a new test finds (section 4).
- `sorties/16-turn-work-group/flight-log.md` - the leg's entry.

## Citation Audit
Checked on 2026-11-13 against the working tree with legs 1 and 2 landed (uncommitted).

- `sorties/16-turn-work-group/flight-log.md` "### Leg 2: turn-work-in-chat" - the 23 failing test ids (20 in `chats-transcript`, 3 in `chats-widgets`), the helper names, the interface names - verified against the Developer's landing report
- `tests/browser/_chats.py::emit_frame` - pushes a frame through the real `ws.onmessage` path - verified at leg 2's design
- `tests/browser/seeders.py::seed_session` - takes `messages=` - verified (Architect)
- `tests/browser/test_flow_chat_queued_render.py::_running_turn` - waits for a streamed assistant bubble (per leg 2's report) - unverified by the Flight Director; the Developer reads it first
- `the_one/interfaces/web/static/js/ui/widget.js:191-199` - a card adopted at width 0 (Architect's note) - unverified here; only relevant if item 20 fails
- `scripts/run-tests.sh` `chats_transcript_pat`, `tests/test_run_tests_lanes.py` - explicit lists, edited by legs 1 and 2 - re-read by the Developer before editing

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
