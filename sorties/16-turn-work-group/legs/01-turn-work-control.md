# Leg: turn-work-control

**Status**: completed
**Flight**: [One work line per chat turn](../flight.md)

## Objective
Add the library control `App.ui.turnWork` (the per-turn work group), with its CSS, catalogue row and contract tests in both engines. Nothing in the app uses it after this leg.

## Context
- Flight DD1 (the control), DD2 (states and wording), DD3 (the preview), DD4 (an item's content is replaced in place, and an item can be removed), DD7 (the "Operator only" chip).
- The operator approved the look on the mockup canvas (flight.md "Mockups"). The canvas drew three pulsing dots; the control uses the app's existing spinner, `App.ui.thinking.dots()`, which is the product's "working" motion. That is a HAT item, not a leg decision.
- This is leg 1 of 3 autonomous legs. Leg 2 mounts the control in chat; leg 3 retires `App.ui.trace`. Do not change `trace.js`, `transcript.js` or any chat module in this leg.
- Nothing is committed in this leg (the flight commits once, after review).

## Inputs
- Branch `sortie/16-turn-work-group`, clean apart from the sortie's planning files and an untracked `env.sh` (not ours; leave it).
- `the_one/interfaces/web/static/js/ui/trace.js` and `thinking.js` as the nearest exemplars.
- WebKit host libraries for the contract lanes. Check first: if the WebKit launch fails, run `bash scripts/setup-webkit-userland.sh` and re-check.

## Outputs
- `the_one/interfaces/web/static/js/ui/turn-work.js` (new).
- CSS for `.ui-turn-work*` in `the_one/interfaces/web/static/css/components.css`.
- A `<script>` tag in `the_one/interfaces/web/static/index.html`.
- `tests/browser/test_ui_turn_work_contract.py` (new), in the `contracts-chat` lane.
- A row in `docs/ui-control-inventory.md`.
- `scripts/run-tests.sh` and `tests/test_run_tests_lanes.py` updated for the new contract file.

## The control

`App.ui.turnWork(opts) -> handle`. ES5, native elements, DOM APIs only (no HTML-string sinks), following `trace.js`.

**Options**: `testid` (on the root), `previewTestid` (on the preview node), `state` (default `'working'`).

**DOM** (class names are the suggested ones; keep the `ui-turn-work` prefix):
```
div.ui-turn-work [data-state] [data-testid]
  details.ui-turn-work-details                 (closed by default, in every state)
    summary.ui-turn-work-toggle [aria-label]
      span.ui-turn-work-lead [aria-hidden]     dots while working, a chevron icon otherwise
      span.ui-turn-work-label                  the state's word
      span.ui-turn-work-count [aria-hidden]    "· 2 tool calls"
      span.ui-turn-work-now [aria-hidden]      the running tool's name, mono
      span.ui-turn-work-chip                   "Operator only" (an App.ui.chip, size sm), when set
    div.ui-turn-work-body                      the items, in the order added
  div.ui-turn-work-preview [aria-hidden=true]  hidden when empty
```

**States** (`setState(name)`; an unknown name throws, like `trace.js` does for an unknown chevron):

| name | label |
|---|---|
| `working` | Working |
| `done` | Work |
| `stopped` | Stopped |
| `error` | Ended with an error |
| `step-limit` | Paused at the step limit |
| `sign-in` | Waiting for sign-in |

- `data-state` on the root always equals the current name.
- Leaving `working`: the dots stop and are replaced by the chevron; the preview and the tool name are cleared and hidden.
- Returning to `working` (a resumed sign-in): fresh dots replace the chevron.

**Handle**:
- `el`: the root.
- `setState(name)`.
- `setToolCalls(n)`: the tool-call count. The count text is "· 1 tool call" or "· N tool calls" when n ≥ 1. When n is 0: "· thinking" if the state is `done` and the body holds at least one thinking item; otherwise empty.
- `setActivity(text | null)`: the running tool's name. Shown only while `working`.
- `setPreview(text | null)`: the pending text. Shown only while `working`, set with `textContent`. The control shows the **end** of the text, in at most two lines: keep the last 400 characters, collapse runs of whitespace to one space, and lay the node out so that overflow is cut at the top, not the bottom. `null` or an empty string hides it.
- `setOperatorOnly(bool)`: shows or removes the chip.
- `stopDots()`: while `working`, replaces the spinner with a static ellipsis and stops its timer (the Stop click, flight DD5). It does not change the state. A later `setState('working')` starts fresh dots.
- `add(kind, content) -> item`: appends an item to the body. `kind` is `'narration'`, `'thinking'` or `'tool'` (an unknown kind throws).
  - `'tool'`: `content` is a node (the caller's `App.ui.message` tool row).
  - `'thinking'`: `content` is a string. The control builds a "Thinking" label and the text, both with `textContent`.
  - `'narration'`: `content` is a string (shown as plain text, whitespace preserved) or a node (a rendered fragment).
  - The item is `{el, kind, setContent(content), remove()}`. `setContent` replaces the item's content in place (the same item node, the same position); `remove()` takes the item out of the body. Both are safe to repeat.
- `isEmpty()`: true when the body has no items.
- `destroy()`: stops the dots timer. It never removes the node and is safe to repeat.

**Accessible name.** The summary's `aria-label` is the state's label, then ", N tool call(s)" or ", thinking" when the count text shows one, then ", operator only" when the chip shows. Examples: "Working", "Work, 3 tool calls", "Stopped, 1 tool call, operator only". The count and tool-name spans are `aria-hidden`. Rationale: the chat log is `role=log` with `aria-relevant="additions"` (`chat-pane.js:212-217`), so the changing visuals must not be new text nodes that get announced; update `aria-label` and existing nodes' text only.

**Look** (from the mockup; tokens only, no ad-hoc colours):
- The summary line: `--font-size-body-sm`, weight 500, `--fg-secondary`; the count in `--fg-tertiary`, weight 400; the tool name in the mono family, `--fg-tertiary`. An 8px gap between parts, a line at least 28px tall, no default disclosure marker, the pointer cursor.
- The chevron is `util.icon('chevron-right')` at 14px and rotates 90 degrees when the details are open, as `.ui-trace-chevron` does.
- The body: indented under the line, a 1px `--border` rule on its left, items in a column with an 8px gap.
- A narration item: `--font-size-body`, `--fg-secondary`. A plain (string) narration keeps its line breaks.
- A thinking item: `--font-size-body-sm`, italic, `--fg-muted`; its "Thinking" label upright, weight 500, `--fg-tertiary`.
- Tool rows inside the body take the full width and a 2px accent left border, as `.ui-trace-body .ui-message--tool` does today (`components.css:2853-2854`); add the equivalent rule for the new body, including the error variant.
- The preview: `--font-size-body`, `--fg-muted`, at most two lines, aligned with the label text.
- The root stretches to the reply's reading width: `align-self: stretch; max-width: min(100%, 46rem)`.
- Focus: `outline: 2px solid var(--accent); outline-offset: 2px` on `summary:focus-visible`.
- Every text colour used clears 4.5:1 on `--bg` in both themes (these tokens already do; `tests/test_design_tokens_a11y.py` must still pass).

## Acceptance Criteria
- [ ] `App.ui.turnWork(opts)` exists in `js/ui/turn-work.js`, written as `App.ui.turnWork = function (opts) {` on one line, and is loaded by `index.html` after `ui/thinking.js` and before `markdown.js`.
- [ ] The root is a `div` holding a native `<details>` that is closed by default in every state; Enter and Space on the summary toggle it; nothing in the control opens or closes it.
- [ ] `setState` sets `data-state` and the label for each of the six states, and throws on an unknown name.
- [ ] While `working` the lead holds the running dots; in every other state it holds the chevron and no timer is running. `stopDots()` stops the timer without changing `data-state`. `destroy()` stops the timer.
- [ ] `setToolCalls` gives "· 1 tool call", "· N tool calls", "· thinking" (state `done`, zero calls, a thinking item present) or nothing, exactly as specified.
- [ ] `setActivity` and `setPreview` show only while `working` and are cleared by leaving it.
- [ ] `setPreview` with a long text shows its end, not its start, in at most two lines; it never renders markup (a `<b>` in the text shows as characters).
- [ ] `add` appends items in order for the three kinds and throws on an unknown kind; a thinking item's text and a string narration are set with `textContent`.
- [ ] An item's `setContent` replaces its content in the same position; `remove()` takes it out; `isEmpty()` follows.
- [ ] The summary's `aria-label` matches the rule above for every combination tested; the count and tool-name spans and the preview are `aria-hidden`.
- [ ] `setOperatorOnly(true)` shows one "Operator only" chip and adds ", operator only" to the name; `false` removes both.
- [ ] Under `prefers-reduced-motion: reduce` no interval runs (the dots are static).
- [ ] The contract tests pass in Chromium and WebKit, and the file is in the `contracts-chat` lane (`--lane contracts-chat --list` shows it; `tests/test_run_tests_lanes.py` passes with `turn_work` in the pinned set).
- [ ] `docs/ui-control-inventory.md` has a row for the control with status `library: App.ui.turnWork` and every class the factory emits listed as owned.
- [ ] The unit-tier guards pass: `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`, `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, `tests/test_run_tests_lanes.py`, `tests/test_index_asset_cache_busting.py`.
- [ ] No file under `areas/` and no existing `js/ui/` file changes behaviour (the app renders exactly as before).

## Verification Steps
- Contract file while iterating: `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_ui_turn_work_contract.py -m browser -x --timeout 30`.
- The lane: `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-chat -x --timeout 30`.
- Lane membership: `bash scripts/run-tests.sh --lane contracts-chat --list | grep turn_work`, and the same with `--lane contracts-controls` prints nothing.
- Guards: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_control_inventory.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_run_tests_lanes.py tests/test_index_asset_cache_busting.py -x --timeout 30`.
- At the end of the leg: `THE_ONE_TEST_NETNS=1 make test-unit`, and `ruff check` plus `ruff format --check` on `tests/ scripts/`.
- "The app renders as before": `git diff --stat` shows no file under `the_one/interfaces/web/static/js/areas/` and no `js/ui/` file other than the new one.

## Implementation Guidance

1. **Read the exemplars first**: `js/ui/trace.js` (the `<details>` shape, `util.el`, `util.icon`, throwing on a bad option, the header comment style), `js/ui/thinking.js` (`makeDots`, its stop rules), `js/ui/message.js:96-97` (how the "Operator only" chip is built with `App.ui.chip`), `tests/browser/test_ui_trace_contract.py` (the `engine_page` + `load_harness` pattern), and "Adding a factory" in `the_one/agents.md`. Its "bump the `/static` ref count" step is stale (squawk 0233: no exact count is pinned); run `tests/test_index_asset_cache_busting.py` and follow what it actually checks.
2. **Write the factory** with a header comment that documents the options, the handle and the accessible-name rule, as `trace.js` does.
3. **Add the `<script>` tag** in `index.html` directly after `ui/trace.js` (line 67), so it loads after `thinking.js` and before `markdown.js`.
4. **Add the CSS** in `components.css` inside `@layer components`, next to the `.ui-trace` block (around line 3057), using existing tokens.
5. **Write the contract tests** (`tests/browser/test_ui_turn_work_contract.py`), engine-parametrized. Cover every acceptance criterion; for the timer criteria, count live intervals the way the thinking contract does (read `tests/browser/test_ui_thinking_contract.py` for its method). For "shows the end of the text", set a preview whose start and end are distinct words and assert the end is inside the node's visible box and the start is not.
6. **Register the lane**: add `'test_ui_turn_work*'` to `contracts_chat_pat` (`scripts/run-tests.sh:260`) and `"turn_work"` to the set in `tests/test_run_tests_lanes.py::test_contracts_chat_lane_is_the_chat_control_files`. Check `scripts/run-tests.sh --help` and CLAUDE.md's lane list wording; update CLAUDE.md's `contracts-chat` bullet to name the new glob.
7. **Add the catalogue row** in `docs/ui-control-inventory.md` after the Trace row, in the same six-cell shape, listing every owned class. `tests/test_ui_emitted_classes.py` is exact in both directions: every class the factory emits must be owned, and every owned class must be emitted.
8. **Falsify** the tests that guard behaviour which could silently regress: the tail preview, the timer stop on leaving `working`, and the accessible name. Break the behaviour by editing, see the test fail, restore by editing. Report yes or no per test.

## Edge Cases
- **`setPreview` before any state change, then `setState('done')`**: the preview node is hidden and its text cleared.
- **`setActivity` or `setPreview` called while not `working`**: stored nothing, shows nothing.
- **`setToolCalls` with a non-number or a negative**: treat as 0.
- **`remove()` on the only thinking item in a `done` group with zero calls**: the "· thinking" text and the name update.
- **`destroy()` then further calls**: no throw, no timer restarted.
- **A node built and never attached**: `makeDots` keeps ticking until attached (its documented rule); the contract test attaches before counting timers.
- **WebKit `<details>`**: `summary::-webkit-details-marker` must be hidden, as the trace CSS does.

## Files Affected
- `the_one/interfaces/web/static/js/ui/turn-work.js` - new.
- `the_one/interfaces/web/static/css/components.css` - the `.ui-turn-work*` rules.
- `the_one/interfaces/web/static/index.html` - one `<script>` tag.
- `tests/browser/test_ui_turn_work_contract.py` - new.
- `scripts/run-tests.sh` - `contracts_chat_pat`.
- `tests/test_run_tests_lanes.py` - the pinned `contracts-chat` set.
- `docs/ui-control-inventory.md` - the new row.
- `CLAUDE.md` - the `contracts-chat` lane bullet.
- `sorties/16-turn-work-group/flight-log.md` - the leg's entry.

## Citation Audit
Checked against the working tree at `7d6ab953` on 2026-11-13.

- `the_one/interfaces/web/static/js/ui/trace.js::App.ui.trace` - a `div` root holding a native `<details>`, built with `util.el`, the chevron from `util.icon('chevron-right')`, throws on an unknown `chevron` - verified
- `the_one/interfaces/web/static/js/ui/thinking.js::makeDots` - `App.ui.thinking.dots() -> {el, destroy()}`; a 120 ms interval; one static " …" and no interval under reduced motion - verified
- `the_one/interfaces/web/static/js/ui/message.js:96-97` - the "Operator only" chip is `App.ui.chip({label, size: 'sm'})` inside a span - verified
- `the_one/interfaces/web/static/index.html:65-69, 80` - `ui/notice.js`, `ui/thinking.js`, `ui/trace.js`, `ui/message.js` load before `markdown.js` - verified
- `the_one/interfaces/web/static/css/components.css:2853-2854, 3057-3090` - the trace body's tool-row rule and the `.ui-trace` block - verified
- `scripts/run-tests.sh:260` - `contracts_chat_pat` is an explicit glob list - verified
- `tests/test_run_tests_lanes.py:107-131` - `test_contracts_chat_lane_is_the_chat_control_files` pins the exact set of nine names - verified
- `tests/browser/test_ui_trace_contract.py:1-40` - contract tests use `engine_page` and `load_harness` from `browser._ui_engines` - verified
- `the_one/agents.md:2354` "Adding a factory" - the four-step checklist; its asset-count step is stale (Architect, squawk 0233) - verified as stale, hence step 1's note

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
