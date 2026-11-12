# Leg: visual-seams

**Status**: completed
**Flight**: [Live Visuals](../flight.md)

## Objective
Pay down Flight 1's debt before widget code lands:
- split `ui/chart.js` by concern, and measure axis text width instead of estimating it;
- move the transcript's streaming commit and pacing into their own module;
- make the streaming scanner tag-driven;
- give the placeholder label options;
- lift the chart error notice into a shared `App.ui.visualNotice`.

Apart from the measured text width, nothing a user can see changes.

## Context
- **Flight DD14** (operator choice: all three carry-over items) and **DD12** (streaming reuses Flight 1's single path).
- **Flight 1 debrief recommendation 2:**
  - split `chart.js` before building on it;
  - measure text width (6.4 px per code point mis-sizes CJK, emoji and bold);
  - keep `transcript.js` under 800 lines by extracting commit and pacing first.
- This leg is the regression net: the existing chart contract and flow tests must pass **unchanged**, except any that pin estimated text widths (none found at design: `grep textWidth\|6\.4 tests/browser/test_ui_chart*.py` is empty).
- **Leg 1** (landed, uncommitted) added `ui/widget-frame.js` and `test_ui_widget*` to `contracts_chat_pat`. This leg does not touch widget code.
- **Squawk 0342's third note** (the estimate's limits) becomes moot for the browser. This leg updates `docs/chart-format.md` to say the browser measures, and that Flight 3's server renderer must use font metrics. The squawk's other two notes stay open; this leg does not close 0342.

## Inputs
- `the_one/interfaces/web/static/js/ui/chart.js` (1,475 lines). Section map at `3dc20800`:
  - constants and class map `:24-70`;
  - number formatting `:78-154`;
  - parse and validation `:155-492` (`parse` `:481`);
  - SVG and text helpers `:494-527` (`textWidth` `:512` = `cpLen(String(text)) * 6.4`; `truncate` `:514`);
  - scales `:528-603`;
  - kinds, stacks and `summarise` `:604-683`;
  - axis drawing `:684-728`;
  - `layoutCartesian` `:729-907` (`maxChars` `:789` divides by 6.4);
  - `layoutScatter` `:911-971`, `layoutPie` `:972-1015`, `layoutSpark` `:1016-1050`;
  - `buildTable` `:1051-1096`, `annotationLines` `:1097-1107`;
  - the `App.ui.chart` control `:1108-1425`;
  - `errorBlock` `:1435-1454`, `block` `:1456-1474`.
- `ui/chart-placeholder.js` (120 lines): labels fixed as `'Rendering chart'` / `'Rendering ' + type + ' chart'` (`:72`, `:100`), source label `'Chart source'` (`:82`), classes `ui-chart-ph-*`.
- `areas/chat/chart-stream.js` (149 lines): `App.chat.chartStream = {scanTail, create, typeOf}`. `chart` is hard-coded at `:28` (`KIND_CHART`), `:53` (`lang === 'chart'`), `:60`, `:65`, `:91` and `typeOf` `:137-142`. `plan()` returns `{boundary, open}`, with `open` a bare offset.
- `areas/chat/transcript.js` (710 lines):
  - `drawChart` and `mdOpts` `:64-67`;
  - `clearLog` `:144-153`, which calls `resetStream`;
  - `chartHold`/`dropChartHold` `:266-275`;
  - `commitSafeBoundary` `:280-320`;
  - `pacingTick` `:322-334`;
  - the pacing timer `:336-339`;
  - `finalizeStreamingBubble` `:355-373`;
  - `onAssistantChunk` `:640-673`.
- Consumers of `App.chat.chartStream`: `transcript.js:261`, `:318`, `index.html:91`, `the_one/agents.md:1647`. No tests reference it by name.
- `index.html:70-71` loads `ui/chart.js` and then `ui/chart-placeholder.js`.

## Outputs
- **`ui/chart.js` split** into files under `js/ui/`:
  - `chart-parse.js`: parse, validation, the number formatters and `cpLen`;
  - `chart-scale.js`: scales, axes, ticks, and the text helpers including the new measurement;
  - `chart-layout.js`: the per-type layouts, the table and the annotations;
  - `chart.js`: the `App.ui.chart` factory, tooltip, keyboard, live node, Show data, `block`.
  
  The public API is unchanged: `App.ui.chart(opts)`, `.parse`, `.block`, `.placeholder`, `.formatTick`/`.formatFull` (whatever exists today). Each file stays well under 800 lines.
- **Measured text width:** an offscreen SVG `<text>` measured with `getComputedTextLength()`, cached per (string, font-size, font-weight). The estimate stays as the fallback when measurement is impossible (detached, `0`, or throws). `maxChars`/`truncate` use real widths.
- **`areas/chat/stream-commit.js`** (`App.chat.streamCommit`) takes the streaming state and logic out of `transcript.js` with no behaviour change: pacing timer, `pendingChars`, `commitSafeBoundary`, the hold, the finalize drain. The `transcript.js` line count goes down by roughly that amount.
- **`areas/chat/visual-stream.js`** (`App.chat.visualStream`) replaces `chart-stream.js`.
  - `create({tags: [...]})` is tag-driven.
  - `plan()` returns `open` as `{offset, lang}` (or `null`).
  - The opener candidate kind is renamed for any tag.
  - `typeOf` stays chart-only.
  - The transcript passes `tags: ['chart']` in this leg; leg 4 adds `widget`.
  - `chart-stream.js` is deleted, and `index.html`, `agents.md` and every consumer are updated.
- **`App.ui.chart.placeholder` options:** `label` (default as today), `sourceLabel` (default `'Chart source'`) and `shape: 'generic'` (a type-free glimmer block in a card shape, which leg 4 uses for widgets). With no new options, the chart output is byte-identical (DOM structure, classes, text).
- **`App.ui.visualNotice({tone, headline, reason, source, testid})`**, a new library factory in `js/ui/visual-notice.js`. It is the composition `errorBlock` builds today: an `App.ui.notice` with the headline, the reason, and a "Technical details" `App.ui.disclosure` holding an `App.ui.codeBlock` of the source. It gets a catalogue row, owned classes and `tests/browser/test_ui_visual_notice_contract.py` (Chromium + WebKit). `App.ui.chart.block` uses it, and chart error and cut-off output is identical, pinned by the existing chart contract tests.
- **Lanes:** `contracts_chat_pat` gains `test_ui_visual_notice*`; `tests/test_run_tests_lanes.py:97`'s name tuple gains `visual_notice`.
- **Docs:**
  - `docs/chart-format.md` (text width is measured in the browser; the server must use font metrics);
  - `docs/ui-control-inventory.md` (the chart row lists its files; a new `visualNotice` row);
  - `the_one/agents.md` "Charts in chat" (`visual-stream.js`, `stream-commit.js`);
  - CLAUDE.md's "Charts in chat" sentence naming `chart-stream.js`.

## Acceptance Criteria
- [ ] **AC1 — Split.**
  - `ui/chart.js` is split into `chart-parse.js`, `chart-scale.js`, `chart-layout.js` and `chart.js` (exact boundaries at the Developer's discretion, each file under 800 lines), loaded by `index.html` in dependency order.
  - The helper files define **no** new `App.ui.X = function` factory and are cited in no catalogue row as `App.ui.X`. They share internals through a private, non-`App.ui.` namespace (for example `window.App._chartParts`), or attach under the existing factory after `chart.js` loads.
  - Every class they emit is owned by the chart row.
  - `tests/test_ui_control_inventory.py`, `test_ui_ownership.py`, `test_ui_emitted_classes.py` and `test_ui_guards.py` pass.
- [ ] **AC2 — No chart regression.** `tests/browser/test_ui_chart_contract.py`, `test_ui_chart_placeholder_contract.py` and `tests/browser/test_flow_chat_charts.py` pass with **no edits**, apart from AC7's error-class selectors. If any other test must change, the leg records why in the flight log. `tests/test_chart_spec.py` is untouched and passing.
- [ ] **AC3 — Measured width.**
  - Axis label width comes from `getComputedTextLength()` on an offscreen SVG `<text>` with the axis label's font settings, cached.
  - The 6.4 px estimate remains only as the fallback.
  - **The probe lives inside the chart's own `<svg>`:** a `<text class="ui-chart-axis-label">` (or the class the measured text uses) is appended to the live chart SVG while measuring and removed afterwards, so the real inherited font applies (`.ui-chart-axis-label { font-size:11px; font-family:inherit }`, `components.css:2978`). It never measures on `document.body`.
  - **The cache** is keyed by (class, string) and cleared once on `document.fonts.ready` (and when it is created), so a layout run before the web fonts loaded cannot poison later ones.
  - **Fallback:** a probe length of 0 for a non-empty string counts as a failure and uses the estimate.
  - **New contract tests, both engines** (design review: y labels are `formatTick` numbers plus a unit, so W/i must go in `y.unit`):
    - (a) **The y margin.** Two otherwise identical charts with `y.unit` `WWWWWWWW` and `iiiiiiii` have left plot edges that differ by more than 25 px; under the estimate they would be equal. Assert also that the plot's left edge is within a few px of an independent in-page measurement (a probe `<text>` with the same class inside the same `.ui-chart`) plus the known padding. No hard-coded pixel widths, since the harness's web fonts 404 and the engines fall back to system fonts.
    - (b) **X truncation.** In a narrow chart, a category label of CJK characters (`売上高合計売上高合計`) is truncated at a different length than `cpLen × 6.4` would give.
    
    **Falsified:** with measurement forced off, (a) and (b) fail.
- [ ] **AC4 — `stream-commit.js`.**
  - The streaming commit and pacing logic lives in `areas/chat/stream-commit.js` (`App.chat.streamCommit`), wired by `transcript.js` through a small, explicit interface (the area's `ctx` style).
  - `transcript.js` is at most 650 lines (about 120 lines move); the flight log records the final count and why, if it is above 600.
  - **Ownership** (design review):
    - `transcript.js` keeps creating the streaming bubble (`streamMsg`, in `onAssistantChunk`), `iterationAnchor`, history, notices, copy and `clearLog`, and hands the bubble to the stream module with `begin(msg)`.
    - `stream-commit.js` owns `pendingChars`, the pacing timer, `commitSafeBoundary`, the hold, the finalize drain and the boundary planner.
    - The `ctx` seam provides `isPinned()`, `setPinned(b)`, `pinToBottom()` (the scroll-then-set idiom duplicated at `:82`, `:326` and `:359`), `scrollToBottomIfPinned()` and `mdOpts()`.
    - The transcript's public `scrollToBottomIfPinned` export (`:679`) stays.
  - Behaviour is unchanged: the `chats-transcript` and `chats` lanes pass with no test edits.
  - `test_ui_guards.py`'s chat-area sink rule (`test_chat_area_has_no_baselined_sink`) passes.
- [ ] **AC5 — `visual-stream.js`.**
  - `App.chat.visualStream.create({tags})` replaces `App.chat.chartStream.create()`.
  - `plan()`'s `open` is `{offset, lang}` or `null`.
  - The transcript passes `['chart']` and reads `open.offset`/`open.lang`.
  - `chart-stream.js` and every reference to `chartStream` are gone, including `index.html` and `agents.md` (`grep -rn chartStream the_one tests scripts docs CLAUDE.md` is empty).
  - A focused browser test, `tests/browser/test_flow_chat_visual_stream.py`, lands in the `chats` lane by default. It loads `markdown.js` and `visual-stream.js` with `add_script_tag`, because `load_harness` loads only `js/ui/*`. Its test of `create({tags:['chart','widget']})` shows a ```` ```widget ```` opener at column 0 reported as `{offset, lang:'widget'}`, and a ```` ```widgets ```` line not reported. This is the tag rule DD1, using the real `App.markdown.parse` confirmation. **Falsified**: with the tag check removed, the test fails.
- [ ] **AC6 — Placeholder options.**
  - `App.ui.chart.placeholder({label, sourceLabel, shape:'generic', testid})` works.
  - With none of the new options, the DOM is identical to today's (the existing placeholder contract tests unchanged).
  - New contract cases, both engines: a custom label and source label, and the generic shape with no type sniffing (`setType` is a no-op or ignored for `generic`).
- [ ] **AC7 — `App.ui.visualNotice`.**
  - The factory exists in `js/ui/visual-notice.js`, with a catalogue row and owned classes.
  - `tests/browser/test_ui_visual_notice_contract.py` (both engines) covers: the danger and muted tones; the headline and reason via `textContent`; Technical details closed by default, holding a code block whose text equals the source exactly; the testid; and that a source containing `<script>` renders as text.
  - **Classes:** `visualNotice` emits its own neutral classes (`ui-visual-notice`, `-head`, `-reason`, `-details`), owned by its row and written as `className`/`cls` literals that the emitted-class scanner sees. It takes a `sourceLabel` option, which the chart passes as `'Chart source'`.
  - `App.ui.chart.block` uses it. The chart error and cut-off output is unchanged **except for those class names**: testids, text, nesting and tones are identical.
  - **The one permitted test edit:** the selectors `.ui-chart-error-head` and `.ui-chart-error-reason` in `tests/browser/test_ui_chart_contract.py` (about `:536-561`) change to the new class names. The flight log records this as the single allowed edit to a pre-existing chart test.
  - The `.ui-chart-error*` CSS rules (`components.css` about `:3018`) move to the new classes, and the chart row's catalogue entry drops them.
  - `contracts_chat_pat` and `tests/test_run_tests_lanes.py` are updated.
- [ ] **AC8 — Docs.** `docs/chart-format.md`, `docs/ui-control-inventory.md`, `the_one/agents.md` "Charts in chat" and CLAUDE.md's chart sentence reflect the new files and measured width.

## Verification Steps
- **Static and unit:**
  - `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_control_inventory.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_run_tests_lanes.py tests/test_chart_spec.py -x --timeout 60`;
  - then `THE_ONE_TEST_NETNS=1 make test-unit` once at leg end.
- **Contracts:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-chat -x`, and `--lane contracts-controls` (shared `js/ui` load order).
- **Chat:** `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats-transcript -x` and `--lane chats -x` (the latter includes the new visual-stream test). Also run `--lane shared` if any shared test pins the `index.html` script list.
- **Lanes that pin shared lists (squawk 0334):** grep `tests/` for `chart-stream`, `chartStream`, `chart.js`, the contracts-chat file count and the catalogue row count, and run every matching lane.
- **Falsifications:** AC3 and AC5, each restored by editing.
- **`wc -l`** on `transcript.js`, `stream-commit.js` and every new chart file, recorded in the flight log.

## Implementation Guidance
1. **The split first, as a pure move.** Move code into files without changing it, run the chart contract and flow tests, then add the measurement. That makes any regression attributable.
   - Keep ES5 and the existing IIFE style.
   - **Share internals through a non-`App.ui.` namespace:** `App._chartParts = {…}`, which each helper file's IIFE merges into. Never write `App.ui._x = function`, which `_FACTORY` would count as a factory.
   - **Keep the emitted-class patterns verbatim:** the `SVG_CLASS` table (a `*CLASS` name), and `seriesClass`'s `var cls = 'ui-chart-series-' + …`. Keep the table in one file, shared through the namespace. Classes built outside the `cls`/`*Class`/`*CLASS` forms are invisible to `tests/test_ui_emitted_classes.py`, and its coverage would silently drop.
   - **Script order:** `index.html` loads the helpers in dependency order, before `chart.js`. `visual-notice.js` must come before `chart.js` uses it, or be referenced lazily at call time. The contract harness takes its order from `index.html` (`index_ui_script_paths`), so it needs no other edit.
   - **Docs:** update the chart catalogue row's "Text is measured by a character-width estimate" statement and its file list.
2. **Measurement** (per AC3).
   - Use a probe `<text>` with the measured class, inside the live chart SVG, removed after measuring. Read `getComputedTextLength()`.
   - Cache by (class, string); clear the cache on `document.fonts.ready`.
   - Layout already runs after attach, on `ResizeObserver` (Flight 1 DD4), so the text is laid out by then. Guard detached cases with the fallback.
   - Keep `truncate` code-point safe. Binary-search the prefix length with a capped number of iterations, and include the ellipsis in the measured string.
3. **`stream-commit.js`.**
   - Move the functions that own streaming state and expose `create(ctx)` returning `{onChunk, finalize, reset, …}`.
   - The transcript keeps message rendering, history, `mdOpts`, `clearLog`, notices and copy, and calls into the stream module.
   - Do not change the commit rules, the pacing constants, the hold seam or the scroll pinning (`pinnedFlag`, `onChartLayout`). Move them exactly.
   - Add `stream-commit.js` and `visual-stream.js` to `index.html` in the place `chart-stream.js` held, before `transcript.js`.
4. **`visual-stream.js`.** Generalise exactly the places the seam map lists (`:28`, `:53`, `:60`, `:65`, `:91`): the opener test becomes `tags.indexOf(lang) >= 0` for a top-level opener. `typeOf` keeps the chart regex. Update `the_one/agents.md:1647` and the CLAUDE.md chart sentence.
5. **The placeholder.** Add the options with today's defaults. For `shape:'generic'`, render one glimmer block in the card's shape (board 4: a short title bar and one tall block) with no type classes. Reduced motion behaves as today.
6. **`visualNotice`.** Copy `errorBlock`'s composition into the factory, parametrised (`tone`, `headline`, `reason`, `source`, `sourceLabel`, `testid`), with the neutral classes of AC7. Make `errorBlock` a thin call to it with the chart's existing strings and testids (`-error`, `-error-details`). Update the two pinned selectors in the chart contract test (AC7), and nothing else there.

## Edge Cases
- **A chart drawn while detached** (built in a fragment during commit): measurement must not run until attached. Layout already waits for the observer; assert that the fallback is used if layout is somehow forced while detached.
- **Fonts not yet loaded** at first layout. A later `ResizeObserver` tick re-lays out; acceptable. Do not add a font-loading wait.
- **`getComputedTextLength` returning 0** for an empty string. Width 0 is correct; do not fall back for empty labels.
- **`chartStream` named in behaviour-test specs or the flight logs of earlier missions.** Leave historical mission artifacts alone. Fix only live docs and code.
- **A placeholder `setType` called on a generic placeholder:** ignore it.

## Files Affected
- `the_one/interfaces/web/static/js/ui/chart.js` - split
- `the_one/interfaces/web/static/js/ui/chart-parse.js`, `chart-scale.js`, `chart-layout.js` - new
- `the_one/interfaces/web/static/js/ui/chart-placeholder.js` - options
- `the_one/interfaces/web/static/js/ui/visual-notice.js` - new
- `the_one/interfaces/web/static/js/areas/chat/transcript.js` - slimmed
- `the_one/interfaces/web/static/js/areas/chat/stream-commit.js` - new
- `the_one/interfaces/web/static/js/areas/chat/visual-stream.js` - new; `chart-stream.js` deleted
- `the_one/interfaces/web/static/index.html` - script list
- `the_one/interfaces/web/static/css/components.css` - only if the generic placeholder or the notice needs classes
- `tests/browser/test_ui_chart_contract.py` - the AC3 test added (existing tests unedited)
- `tests/browser/test_ui_chart_placeholder_contract.py` - AC6 cases added
- `tests/browser/test_ui_visual_notice_contract.py` - new
- a visual-stream test (contract or unit via node) - new
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` - lane list
- `docs/chart-format.md`, `docs/ui-control-inventory.md`, `the_one/agents.md`, `CLAUDE.md` - docs
- `missions/35-rich-visuals-in-chat/flights/02-live-visuals/flight-log.md` - leg entry

## Citation Audit
Verified against the working tree (leg 1 landed and uncommitted on `flight/02-live-visuals`), 2026-11-09:
- `ui/chart.js:512` `function textWidth(text) { return cpLen(String(text)) * 6.4; }`; `:789` `maxChars = Math.max(3, Math.floor((band * stride - 6) / 6.4))`; `:792` `truncate(xTick(...), Math.min(maxChars, 24))` - verified
- `ui/chart.js` section map (`:78-154`, `:155-492`, `:494-527`, `:528-603`, `:729-1050`, `:1108-1425`, `:1435-1474`) - verified by the planning seam pass; the Developer re-checks before moving
- `index.html:70-71` (`ui/chart.js`, `ui/chart-placeholder.js`), `:91` (`areas/chat/chart-stream.js`) - verified
- `areas/chat/chart-stream.js:144` `window.App.chat.chartStream = {` and the hard-coded `chart` sites - verified (planning seam pass)
- `areas/chat/transcript.js:259-261` (`App.chat.chartStream.create()`), `:318` (`typeOf`), 710 lines - verified
- `the_one/agents.md:1647` - names `chart-stream.js` / `App.chat.chartStream` - verified
- `tests/browser/test_ui_chart*.py` - no pin on `textWidth` or `6.4` (grep) - verified
- `tests/test_run_tests_lanes.py:97` - exact `contracts-chat` file-set pin (now including `widget_frame` from leg 1) - verified (leg 1 design review)
