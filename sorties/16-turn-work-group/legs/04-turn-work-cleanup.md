# Leg: turn-work-cleanup

**Status**: completed
**Flight**: [One work line per chat turn](../flight.md)

## Objective
Delete the code the new turn shape left without a caller, and retire its testids, catalogue rows and lane pins. (The capture tool, the behavior specs and the docs are leg 5, `turn-work-docs`.)

## Context
- Flight DD10 (what is deleted and how), DD11 (the specs), and the operator's decision "Delete it" (flight log, Decisions).
- Legs 1 to 3 built the new shape and its tests. After leg 2 nothing calls `stream-commit.js`, `visual-stream.js`, `App.ui.trace`, `App.ui.chart.placeholder` or `App.ui.message`'s streaming API. This leg proves that with recorded greps and then deletes them.
- Every deletion follows `removing-dead-code` in `the_one/agents.md` (line 183): grep immediately before deleting, record the command and the result per item, run the UI guards after.
- Nothing is committed in this leg. Leg 5 follows it, then the flight review.
- In this leg, touch docs only where a guard forces it: `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, and the lane bullets in `CLAUDE.md` that name a deleted test file. Leave the prose in `CLAUDE.md`, `the_one/agents.md`, `README.md` and `SECURITY-MODEL.md` to leg 5.

## Inputs
- Legs 1 to 3 landed, uncommitted. All chat lanes and the unit tier green at the end of leg 3 (check its flight-log entry; if it lists anything under "Open for the Flight Director", read it before starting).

## Outputs
- Deleted product files and tests (below), with the greps recorded in the flight log.
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `tests/test_nav_helper.py`, `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` updated.
- `scripts/ui_capture.py` surfaces updated.
- Behavior specs re-authored.
- `CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md` and the format docs updated.

## The work

### 1. Deletions
The grep for every item is `grep -rn --exclude-dir={.claude,.git,.venv,missions,maintenance,squawks,sorties} '<name>' .`, run immediately before the deletion. Record the command and its hits in the flight log. The only hits may be the definition itself, its own tests, and docs this leg rewrites. **If a product file other than the definition calls it, stop: do not delete that item, record the caller, and carry on with the rest.**

| Item | Where | Goes with it |
|---|---|---|
| `App.chat.streamCommit` | `js/areas/chat/stream-commit.js` | its `<script>` tag in `index.html` |
| `App.chat.visualStream` | `js/areas/chat/visual-stream.js` | its `<script>` tag; `tests/browser/test_flow_chat_visual_stream.py` |
| `App.ui.trace` (with `.find`, `.thinking`) | `js/ui/trace.js` | its `<script>` tag; the `.ui-trace*` rules in `components.css` (including `.ui-trace-body .ui-message--tool` at 2853-2854 and the block at 3057 onward); `tests/browser/test_ui_trace_contract.py` |
| `App.ui.chart.placeholder` | `js/ui/chart-placeholder.js` | its `<script>` tag; in `components.css`: the `.ui-chart-placeholder` half of the shared selectors at 2929-2930 and 2950 (the `.ui-chart` halves stay), the whole `.ui-chart-ph-*` block (about 3022-3050), `@keyframes ui-chart-glimmer` and its reduced-motion rule; the header-comment lines in `chart.js:15-17`; `tests/browser/test_ui_chart_placeholder_contract.py`, **after** its dots cases are moved (below) |
| `App.ui.message`'s streaming API | `js/ui/message.js`: the `streaming` option, `appendText`, `commit`, `finalize`, `tail`, `setTailHold` and the state they use | the streaming and tail-hold cases in `tests/browser/test_ui_message_contract.py`; the handle's documented shape in the header comment |

Rules for the table:
- **Names built as strings are not found by grep.** Before deleting a CSS class, read its producer. `App.ui.thinking.dots` stays (the new control and "Loading model" use it), and so does everything else in `thinking.js`.
- **Retiring a test-only production method** (`removing-dead-code`, last bullet): `App.ui.message`'s streaming methods are now called only by tests. For each of their contract tests write "property removed with the method: the chat no longer streams into a bubble (flight DD3)" in the flight log; no replacement test is needed, because the behaviour is gone, not moved. **Move the dots tests first.** `App.ui.thinking.dots` is pinned directly only in `tests/browser/test_ui_chart_placeholder_contract.py` (its structure, reduced motion, and one interval per standalone instance, around lines 162-198); `test_ui_thinking_contract.py` has no `dots` case. Before deleting the placeholder contract file, move those cases into `test_ui_thinking_contract.py` (they call `App.ui.thinking.dots()` directly, with no placeholder), run them, and falsify one (break the reduced-motion branch, see it fail, restore). This is the first step of the leg.
- `App.ui.message` keeps working for every non-streaming caller: after the removal, the handle is what `transcript.addMsg`, `buildToolMsg` and the other callers use today. Grep every `App.ui.message(` call site and every use of its handle before trimming it.
- The unclosed-fence handling stays: `closed: false` on `App.ui.chart.block` and `App.ui.widget`, and `App.ui.visualNotice`.
- `transcript.js`: remove anything left with no caller after leg 2 (re-run the grep per exported name), and reword the stale comment near line 87 ("streaming commits render only new prefixes and finalize renders only the tail"): the invariant now is that every text is rendered once, by the turn-work module.
- The `.ui-trace*` rules run from about 3057 to 3105 (ending at `.ui-trace-thinking-body`); the `.ui-turn-work*` rules start right after and stay. Reword the comment near 2814 that mentions `.ui-trace-body .ui-message--tool`. Before deleting 2853-2854, confirm leg 1 gave the new body its own tool-row rule (it should have; if not, add it under the control's body class).
- Add `--exclude-dir=node_modules` to the dead-code grep. A hit under `evals/runs/` is a gitignored run log and does not count.
- `scripts/run-tests.sh:259-260`: remove `'test_ui_trace*'` from `contracts_chat_pat` and fix the comment that names the chart-placeholder contracts. The `test_ui_chart*` glob stays (it still matches the chart contract). In `tests/test_run_tests_lanes.py:119-123` remove `"trace"` and `"chart_placeholder"` from the pinned names; `"turn_work"` is already there from leg 1.
- Before deleting anything, re-check that leg 3 left no test naming a placeholder id: `grep -rnE 'chat-chart-placeholder|chat-widget-placeholder' tests/browser` must print nothing. If it does, stop and report.
- After the deletions: `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`, `tests/test_ui_control_inventory.py`, `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, `tests/test_index_asset_cache_busting.py`, and `ruff check`.

### 2. Catalogue, registry, lanes
- `docs/ui-control-inventory.md`: move the Trace row and the chart placeholder's row (or sub-entry) to "Retired controls", in that section's existing form; update the Message row (no streaming API, no `setTailHold` in its Debt cell) and the Thinking row (who uses `dots` now). Update the turn-work row's "mounted by" cell to name `areas/chat/turn-work.js`.
- `docs/ui-testid-registry.md` and `RETIRED_SELECTORS` in `tests/test_nav_helper.py`: retire `chat-chart-placeholder`, `chat-chart-placeholder-source`, `chat-widget-placeholder`, `chat-widget-placeholder-source` (their literals leave with `stream-commit.js`). The registry is checked in both directions (`tests/test_ui_guards.py`), so the registry and the JS change together. No test may name them afterwards.
- `scripts/run-tests.sh` and `tests/test_run_tests_lanes.py`: remove `test_ui_trace*` and the chart-placeholder file from the pinned `contracts-chat` set (keep `test_ui_chart*` for the chart contract itself; check the glob does not still expect the deleted file), and any pin of `test_flow_chat_visual_stream.py`. Update the `contracts-chat` and `chats` lane bullets in `CLAUDE.md`.

> **Sections 3, 4 and 5 below are leg 5's work** (`turn-work-docs`), split off at this leg's design review because the whole was too large for one pass. They stay here as that leg's specification; this leg (4) does sections 1 and 2 only.

### 3. Capture surfaces (`scripts/ui_capture.py`) — leg 5
- List the chat surfaces (`--list`) and read the ones that script live states. Any surface that scripted a streaming bubble, a "Tool activity" trace, a thinking disclosure or a visual placeholder is rewritten to the new shape or removed, with a line in the flight log.
- Add three surfaces: a turn working (the line with a count, a tool name and a preview), a finished turn with the group open (narration, thinking, tool rows), and a stopped turn.
- Run the tool once to prove the changed and new surfaces render: `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out <a directory outside the repo>` limited to those surfaces if the tool can filter (see its `--help`). The PNGs are local evidence and are never committed; record the output path and the surface names.

### 4. Behavior specs (`tests/behavior/*.md`) — leg 5
Re-author the steps that describe the old shape. A spec's Expected Results must be observable in the new UI; keep each spec's intent.
- `agent-step-limit-notice`, `chat-loop-hang-and-cancel`, `extended-thinking-tool-turn`, `stub-connector-round-trip`: they name "Tool activity", `trace-shell` or `thinking-indicator`.
- `chat-roundtrip` (step 4) and `anthropic-plan-token-chat` (step 6): they expect the reply text to grow while it streams. The new observable: the work line shows "Working" with a moving preview, and the reply appears whole when the turn ends.
- `anthropic-plan-chat-parity` (step 3) and `agent-governance-and-search` (lines 47, 63): read them; re-author only if the wording no longer holds.
- Then grep `tests/behavior/*.md` (not the `runs/` folders, which are history) for `Tool activity`, `trace`, `thinking-indicator`, `Thinking…`, `streaming`, `streamed`, `placeholder` and handle any other spec the list missed.
- Do not run the behavior tests. List each re-authored spec and step in the flight log.

### 5. Docs — leg 5
- `CLAUDE.md`: the "Chats pane" paragraph (the transcript: `App.ui.trace`, the thinking disclosure, "Charts in chat" and its streaming placeholder, "Widgets in chat" and its "Rendering widget" placeholder), the "Control library" paragraph if it names the retired controls, the lane bullets (`contracts-chat`, `chats`, `chats-transcript`, `chats-widgets`), and the `chats-widgets` note "mock streams in them must be slower than the 16 ms pacing tick" (the pacing is gone; keep the sentence only if leg 3 kept a test that needs it). Describe the new shape in the same compact style: one group per turn (`App.ui.turnWork`, `areas/chat/turn-work.js`), the six states and their words, the preview, the reply rule, the two accepted reload differences, and that there is no setting.
- `the_one/agents.md`: the "Chat module map" (add `turn-work.js`, remove the two deleted modules), "Chat transcript on the library" (line 1669 onward: streaming, `clearLog`, "B2, the thinking disclosure's place", Traces, Notices), "Charts in chat" and "Widgets in chat" where they describe the tail hold, the commit boundaries and the placeholder lifecycle, the "Control library" section's chat controls, and "Adding a factory" (drop the stale "bump the `/static` ref count" step: no count is pinned since squawk 0233). Add a short "Turn work group (sortie 16)" section that is the deep reference: the module's interface, `ensureOpen` and the trailing-turn re-render, the "latest narration waits" rule and why (a mounted widget frame never moves; `drawWidget` runs once per source), the frame-to-state table, and what replay does.
- `SECURITY-MODEL.md` "Live visuals": where it describes the streaming hold or "a Stop mid-block leaves the cut-off notice and the source never runs", restate it for the new shape (a stopped turn's text is folded into the group; an unclosed widget block there still never runs; pending text is only ever shown as plain text in the preview).
- `docs/chart-format.md` and `docs/widget-format.md`: grep for "placeholder" and "stream"; fix any sentence about the chat's streaming placeholder. The format rules themselves do not change.
- `docs/ui-testid-registry.md`: as in section 2.

### 6. Rider: a new agent starts at 50 steps (operator request, 2026-11-13) — this leg
Unrelated to the cleanup; the operator asked for it to ride in this sortie. It is browser-only.
- In `the_one/interfaces/web/static/js/areas/studio/general-tab.js`, `defaults(providers)` (line 51) returns `max_iterations: 20`. Change it to `50`. This is the value the "New agent" form (`#agents/~new`) starts with and sends on create.
- **Do not change anything else**: not the fallbacks `cfg.max_iterations || 20` at lines 196 and 366 (they cover a stored agent with no value, which the server reads as 20), not the field's 1 to 100 range, and no Python (`the_one/agent/config.py`, `core.py`, `db/schema.py`, `repositories.py` keep 20). Existing agents, the built-in default agent, API- and CLI-created agents and the evals are unaffected. The operator chose this scope over changing the server default.
- Test: in `tests/browser/test_flow_agent_general_tab.py` (lane `agents`), add or extend a test that opens the new-agent form and asserts the max-iterations field (`studio-max-iterations`) reads 50, and that creating the agent without touching the field stores `max_iterations` 50 (read it back through the API or the reopened form). Falsify it (set the default back to 20, see it fail, restore).
- Grep for pins of the old form default before changing it: `grep -rn "max_iterations" tests/browser tests/test_*static*.py scripts/ui_capture.py` and read each hit that concerns a **new** agent's form value. Update any that pinned 20 for the new-agent form.
- Docs: `grep -n -i "max iterations\|max_iterations\|20 steps" README.md CLAUDE.md the_one/agents.md docs/*.md`; if a doc states the new-agent form's default, update it. (Leg 5 owns the rest of the docs.)
- Gate: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_flow_agent_general_tab.py -m browser -x --timeout 30`, then the `agents` lane once.

## Acceptance Criteria
- [ ] Rider: the new-agent form starts at 50 steps and a created agent stores 50; the fallbacks, the range and all Python are unchanged; its test passes and was falsified; the `agents` lane passes.
- [ ] The five items in the deletion table are gone from the product (or an item is kept with its live caller recorded), and for each the flight log records the grep command and its result taken immediately before the deletion.
- [ ] `index.html` loads no deleted file; the app starts and a chat turn renders (proved by the chat lanes passing).
- [ ] `App.ui.message` still serves every remaining caller; its contract file passes with the streaming cases removed and each removed case listed as "property removed with the method".
- [ ] `App.ui.thinking.dots` is still covered by a contract test (running, stopped, reduced motion).
- [ ] The Trace and chart-placeholder catalogue rows are under "Retired controls"; the four placeholder testids are retired in the registry and in `RETIRED_SELECTORS`; no file under `tests/browser/` names a retired id.
- [ ] `scripts/run-tests.sh` and `tests/test_run_tests_lanes.py` list no deleted file, and the lanes test passes.
- [ ] The dots cases live in `test_ui_thinking_contract.py`, pass in both engines, and one was falsified.
- [ ] Gates: the unit-tier guards listed in section 1 pass; `THE_ONE_TEST_NETNS=1 make test-unit` passes; `contracts-chat` and `contracts-controls` pass with `THE_ONE_REQUIRE_WEBKIT=1`; `chats`, `chats-transcript`, `chats-widgets` and `shared` pass; `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/` are clean.
- [ ] No Python under `the_one/` changed.

## Verification Steps
- The dead-code grep per item, as above, recorded.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_ui_control_inventory.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_index_asset_cache_busting.py tests/test_nav_helper.py tests/test_run_tests_lanes.py -x --timeout 30`.
- Lanes, one at a time, in the background: `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane> --timeout 30 -q` for `contracts-chat`, `contracts-controls`, `chats-transcript`, `chats-widgets`, `chats`, `shared`.
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- The docs grep in the acceptance criteria.
- `git status --short` and `git diff --stat`: no `.py` under `the_one/`.

## Implementation Guidance
1. Read `removing-dead-code` (`the_one/agents.md:183`), the flight's DD10 and DD11, and the flight-log entries for legs 2 and 3.
2. Move the dots tests into `test_ui_thinking_contract.py`.
3. Delete in this order, running the guards after each: the two chat modules; `App.ui.trace`; `App.ui.chart.placeholder`; `App.ui.message`'s streaming API. Each with its tests, CSS, `<script>` tag, catalogue row and testids in the same step (the inventory guard needs a live row's factory and contract file to exist together).
4. Lanes and pins.
5. The rider (section 6): a separate, small change; do it after the cleanup is green so a failure is easy to place.
6. Run the gates; write the flight-log entry. Sections 3 to 5 of "The work" are not this leg's.

## Edge Cases
- **A grep hit in `evals/` or `packaging/`**: treat as a live caller until read; the packaging specs may list static files.
- **`tests/test_index_asset_cache_busting.py`** and any test that lists the `/static` scripts: removing four `<script>` tags may need its expectation updated; follow what it actually checks.
- **CSS shared with a kept rule**: a selector list that mixes `.ui-trace-*` with a kept class loses only the trace part.
- **A `.ui-message` streaming CSS rule** (a caret, a tail style): remove only if its class is no longer emitted; `tests/test_ui_emitted_classes.py` is exact in both directions.
- **The disk harness** (`tests/browser/_ui_engines.py`) loads the `ui/` scripts `index.html` lists; a deleted tag needs no other change, but check for a hard-coded file list.
- **A spec's run logs** under `tests/behavior/*/runs/` are history and are not edited.

## Files Affected
- Deleted: `js/areas/chat/stream-commit.js`, `js/areas/chat/visual-stream.js`, `js/ui/trace.js`, `js/ui/chart-placeholder.js`, `tests/browser/test_flow_chat_visual_stream.py`, `tests/browser/test_ui_trace_contract.py`, `tests/browser/test_ui_chart_placeholder_contract.py`.
- `the_one/interfaces/web/static/js/ui/message.js`, `js/ui/chart.js` (a comment), `js/areas/chat/transcript.js`, `index.html`, `css/components.css`.
- `tests/browser/test_ui_message_contract.py`, possibly `tests/browser/test_ui_thinking_contract.py`.
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `docs/chart-format.md`, `docs/widget-format.md`, `tests/test_nav_helper.py`, `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py`, `scripts/ui_capture.py`.
- `tests/behavior/*.md` (the listed specs).
- `CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md`.
- `sorties/16-turn-work-group/flight-log.md`.

## Citation Audit
Checked on 2026-11-13 against the working tree with legs 1 and 2 landed (uncommitted) and leg 3 in progress. Leg 3 edits test files only; the product-file rows below hold unless leg 3's log records a chat-module fix, in which case the Developer re-runs the greps (it does so anyway, per item).

- `grep -rnE 'streamCommit|visualStream' the_one/interfaces/web/static/js` - hits only inside `stream-commit.js` and `visual-stream.js` - verified
- `grep -rnE 'App\.ui\.trace\b|ui\.trace\(|trace\.find|trace\.thinking' the_one/interfaces/web/static/js` - no hit outside `ui/trace.js` - verified
- `App.ui.chart.placeholder` - called only at `stream-commit.js:47, 50`; mentioned in a comment at `chart.js:15` - verified
- `setTailHold`, `appendText(`, `.commit(`, `.tail(`, `streaming:` - used only inside `stream-commit.js` and defined in `ui/message.js:24-180` - verified
- `the_one/interfaces/web/static/index.html:67` (`ui/trace.js`), `76` (`ui/chart-placeholder.js`), `98-99` (`visual-stream.js`, `stream-commit.js`) - verified
- Files that still name the deleted code: `CLAUDE.md`, `the_one/agents.md`, `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `scripts/run-tests.sh`, `tests/browser/test_flow_chat_charts.py`, `test_flow_chat_widgets.py`, `test_flow_chat_visual_stream.py`, `test_ui_chart_placeholder_contract.py`, `test_ui_message_contract.py`, `test_ui_trace_contract.py` - verified (grep of 2026-11-13; the two flow files are rewritten by leg 3)
- `the_one/agents.md:183` `removing-dead-code`; `:1648` "Chat module map"; `:1669` "Chat transcript on the library"; `:2354` "Adding a factory" - verified
- `tests/test_run_tests_lanes.py` pins the `contracts-chat` set including `trace` and `chart_placeholder` - verified
- `scripts/ui_capture.py:2398` - leg 2 changed this ready selector to the group - per leg 2's report; the Developer re-reads it
- `SECURITY-MODEL.md` "Live visuals" - names no deleted module (grep), but its wording about a Stop mid-block is to be read - unverified; the Developer reads the section

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
