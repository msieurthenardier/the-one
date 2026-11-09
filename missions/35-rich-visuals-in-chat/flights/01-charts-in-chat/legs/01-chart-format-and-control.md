# Leg: chart-format-and-control

**Status**: completed
**Flight**: [Charts in Chat](../flight.md)

## Objective
Define the chart format once (a document plus a shared corpus) and build everything that draws or checks a chart outside chat:
- the server-side validator and number formatter;
- the browser control `App.ui.chart` (parse, chart, block, placeholder);
- a reusable thinking-dots piece;
- the chart palette tokens with their contrast gate;
- catalogue rows and Chromium + WebKit contract tests.

## Context
- Flight design decisions this leg implements: **DD1** (tag `chart`), **DD2** (format v1, richer scope, limits, locale-neutral numbers), **DD3** (one document, one corpus, two validators with identical sentences, drift traps), **DD4** (the control's entry points, pixel layout after attach, tooltip and keyboard target, structure-only contract tests, lane budget), **DD5** ("Show data"), **DD7** (palette tokens, contrast on the composited bubble, theme by CSS alone), **DD8** (the placeholder control and the dots factoring only; the chat wiring is leg 2), **DD9** (the error and cut-off notices built by `App.ui.chart.block`).
- Approved mockups: https://claude.ai/artifact/5qfTVCkB5peb1ekzi8gCTS. Boards 1-3 show the chart, the table, the types and the colours; board 4 shows the placeholder (option B, glimmer, shaped by type); board 5 shows the error.
- Nothing in chat changes in this leg. `markdown.js`, `transcript.js` and `message.js` are untouched; leg 2 calls `App.ui.chart.block` and `App.ui.chart.placeholder` from chat.
- Flight 3 will render the same format to PNG on the server from `the_one/visuals/`, so the Python side must be complete for every key in DD2, not only what the eval check needs.
- This is the first leg; there are no prior-leg outcomes.

## Inputs
- Branch `flight/01-charts-in-chat` at `293a81d2` plus the mission and flight artifacts.
- The existing library: `App.ui.util` (`js/ui/core.js`), `App.ui.disclosure` (`js/ui/disclosure.js:25`), `App.ui.notice` (`js/ui/notice.js`), `App.ui.codeBlock` (`js/ui/page.js:166`), `App.ui.thinking` (`js/ui/thinking.js:30`).

## Outputs
- `docs/chart-format.md`: the language-neutral spec.
- `tests/fixtures/charts/`: `valid/*.json`, `invalid/*.json`, `invalid/expected.json`, `number-format.json`.
- `the_one/visuals/__init__.py`, `the_one/visuals/chart_spec.py`.
- `tests/test_chart_spec.py`.
- `the_one/interfaces/web/static/js/ui/chart.js` and `js/ui/chart-placeholder.js`, loaded from `index.html` after `message.js` (`index.html:69`), in that order.
- Chart CSS in `css/components.css` (the library's stylesheet), and `--chart-*` tokens in `css/tokens.css` (both theme blocks).
- `App.ui.thinking.dots()`, with `js/ui/thinking.js` refactored to use it.
- Token mirror in `tests/browser/design_tokens.py`; contrast pairs in `tests/test_design_tokens_a11y.py`.
- Catalogue rows in `docs/ui-control-inventory.md`.
- Contract tests `tests/browser/test_ui_chart_contract.py` and `test_ui_chart_placeholder_contract.py`, in the `contracts-chat` lane.
- `scripts/run-tests.sh`: `contracts_chat_pat` extended, and the lane re-budgeted (or a new lane, with `tests/test_run_tests_lanes.py` updated).

## Acceptance Criteria

**Format and corpus**
- [ ] AC1. `docs/chart-format.md` specifies every key, rule and limit of DD2 and the locale-neutral number display. It lists each validation error sentence verbatim, with a minimal example of each type plus one using every optional key. `type` comes first in every example.
- [ ] AC2. `tests/fixtures/charts/valid/` holds at least one spec per type plus specs for `stacked` (bar and area), `y2` with `"axis": "right"`, mixed `series[].type`, `scale: "log"`, `annotations` on `y`, `y2` and `x`, `null` gaps, unknown keys (ignored), and a sparkline with only `type` and `series`.
- [ ] AC3. `tests/fixtures/charts/invalid/` holds one file per error sentence in the document. `invalid/expected.json` maps each file name to its exact sentence. It includes the DD3 drift traps:
  - `NaN`/`Infinity` literals;
  - `true` as a value;
  - an emoji label at exactly the code-point limit (valid, in `valid/`) and one code point over (invalid);
  - `null` counted toward the 2,000-value limit;
  - non-JSON text;
  - JSON that is not an object;
  - a missing `type` and an unknown `type`;
  - a series length mismatch;
  - a log scale with a 0 value;
  - `axis: "right"` without `y2`;
  - pie with two series;
  - pie with a negative value;
  - pie with a zero total;
  - more than 8 series and more than 12 slices;
  - a scatter pair that is not a pair;
  - two series with the same name;
  - duplicate `x.values`;
  - `y.min >= y.max`;
  - a `unit` over 12 code points and a `title` over 120;
  - an `annotations` category not in `x.values`;
  - a series `type` on a `pie`.

  Two of these may be valid by the document's choice: `x.values` given on a scatter (ignored) and a `0` slice among positive pie values (drawn as a zero-width slice and kept in the table). Whichever the document decides, the corpus holds a file for it in `valid/` or `invalid/`.
- [ ] AC3b. The document is the single source of the error sentences. `tests/test_chart_spec.py` asserts that every sentence in `invalid/expected.json` appears verbatim in `docs/chart-format.md`'s sentence list, and that every listed sentence has at least one corpus file.
- [ ] AC4. `tests/fixtures/charts/number-format.json` lists `[value, unit, tick_text, full_text]` rows covering compact suffixes (k, M, B), at most 3 significant digits, negatives, decimals, zero, each prefix unit (`$`, `€`, `£`, `¥`), a suffix unit (`%`, `ms`), and log-scale ticks at powers of ten (`1`, `10`, `100`, `1k`, `10k`) under the same compact rules.
- [ ] AC4b. `docs/chart-format.md` has a palette appendix with the final `--chart-*` hex values for both themes. Flight 3's server renderer reads the colours from there instead of re-deriving them.

**Python validator**
- [ ] AC5. `the_one.visuals.chart_spec.parse_chart(source: str)` returns a `ChartSpec` (a frozen, typed structure holding every DD2 key, normalised) or a `ChartError(message: str)`. It never raises on any input string, imports nothing from `the_one.interfaces`, `the_one.agent` or Pillow, and refuses `NaN`/`Infinity` (through `json.loads(..., parse_constant=...)`) and booleans as numbers.
- [ ] AC6. `the_one.visuals.chart_spec` exposes `format_tick(value, unit)` and `format_full(value, unit)` implementing the document's number display.
- [ ] AC7. `tests/test_chart_spec.py` asserts:
  - every `valid/` file parses;
  - every `invalid/` file yields exactly its `expected.json` sentence;
  - `number-format.json` matches both formatters;
  - a fuzz-style loop over truncated prefixes of every valid file never raises;
  - a roughly 100 KB input over the 2,000-value limit returns its error in well under a second.

**Browser control**
- [ ] AC8. `App.ui.chart.parse(source)` returns `{ok: true, spec}` or `{ok: false, message}`. It runs over the same corpus in a contract test, in both engines, with the identical sentence for every invalid file. `App.ui.chart.formatTick` / `formatFull` (or equivalent exposed helpers) match `number-format.json`.
- [ ] AC9. `App.ui.chart({spec, testid})` returns `{el, destroy()}` and draws each of the six types and every optional key in AC2. Structure:
  - `figure` > `figcaption` (title and legend; no legend for one unnamed series or a sparkline);
  - a keyboard wrapper with `role="group"`, an accessible name "{title}, chart values" (or "Chart values" with no title) and a description of the arrow keys;
  - inside it, an `svg` with `role="img"` and a one-sentence `aria-label` summary;
  - a "Show data" `App.ui.disclosure` holding a `<table>` with one row per category or point and one column per series, units in the cells, and annotations listed under it.

  A sparkline is a compact row with no axes, legend, keyboard wrapper or "Show data"; its `aria-label` names its first and last values.
- [ ] AC10. Layout happens after attach. The chart builds its structure at once, lays out SVG geometry on its first `ResizeObserver` callback and again on width changes (coalesced to one frame), and disconnects the observer on `destroy()` and when detached. A chart created detached and attached later draws correctly. Text is never scaled by a `viewBox`.
- [ ] AC11. Tooltip: hovering the plot shows `chat-chart-tooltip`-style content (the testid is caller-supplied, as `<testid>-tooltip`) with the x label and each series' full value. Focusing the keyboard wrapper shows it at the first x position; ArrowRight/ArrowLeft move, Home/End jump to the ends, Escape hides it, and blur hides it. The tooltip is `aria-hidden="true"`.
- [ ] AC12. Series paint through owned classes whose CSS uses `var(--chart-N)`. A change of `data-theme` on `<html>` repaints with no JavaScript (a contract test flips the attribute and reads the computed stroke or fill). Line series beyond the fourth get a dash pattern.
- [ ] AC13. `App.ui.chart.block(source, {closed, testid})` returns a Node:
  - the chart, for a valid spec;
  - for an invalid spec with `closed !== false`, an `App.ui.notice({tone: 'danger'})` with "Couldn't draw this chart." plus the validator's sentence, and an `App.ui.disclosure({variant: 'plain', summary: 'Technical details'})` holding an `App.ui.codeBlock` of the source;
  - for `closed === false`, the same shape with a muted notice "This chart was cut off before it finished.".

  It never throws.
- [ ] AC14. `App.ui.chart.placeholder({type, testid})` returns `{el, setType(t), setSource(text), destroy()}`. It shows:
  - "Rendering chart" (or "Rendering {type} chart" once known, as on board 4) with the dots;
  - a glimmering title bar and plot shaped by type: generic, bars, a line (for `line`, `area` and `scatter`), a disc (for `pie`) and a short row (for `sparkline`);
  - a "Show source" disclosure (testid `<testid>-source`) whose code well `setSource` updates in place.

  Under `prefers-reduced-motion: reduce` there is no glimmer animation and the dots show the static text. `destroy()` stops the dots and removes nothing the caller owns.
- [ ] AC15. `App.ui.thinking.dots()` returns `{el, destroy()}`; `App.ui.thinking` is rebuilt on it. Every assertion in `tests/browser/test_ui_thinking_contract.py` still passes unchanged, the dots CSS no longer depends on `.ui-thinking`, and each dots instance runs exactly one interval.

**Tokens, catalogue, lanes**
- [ ] AC16. `css/tokens.css` defines `--chart-1` … `--chart-8` and `--chart-ref` in both theme blocks, plus grid and axis tokens unless existing tokens are reused (record which).
  - `tests/browser/design_tokens.py` mirrors every new **hex** token in both `DARK` and `LIGHT`. The mirror guard is mirror-to-CSS (`test_ui_guards.py:355`), so every mirrored key must exist in both blocks. rgba wash tokens stay unmirrored (`design_tokens.py:25`).
  - `tests/test_design_tokens_a11y.py` asserts every series token and `--chart-ref` reach ≥ 3.0:1 in both themes against `--surface`, against `--bg`, and against `--surface-translucent` composited over `--bg`.
  - The composite uses the existing `_alpha_composite(fg_hex, alpha, base_hex)` helper (`test_design_tokens_a11y.py`, near `:102`). Its rgba is **parsed from `tokens.css`** (through the existing theme-block parser) rather than hardcoded, so the test cannot drift: dark `rgba(255, 255, 255, 0.03)` (`tokens.css:78`), light `rgba(24, 24, 27, 0.03)` (`:225`).
  - `--chart-*` tokens sit outside the fg-role completeness net (`test_design_tokens_a11y.py` near `:1418`). Confirm that, so no `_CONTRAST_EXEMPT` entry is needed, or add one with a reason.
- [ ] AC17. Catalogue rows in `docs/ui-control-inventory.md` ("Feedback and status" or a new "Charts" section).
  - **One factory, `App.ui.chart = function`**, gets one six-cell row. Its sub-entries `App.ui.chart.parse`, `.block` and `.placeholder` (and any exposed formatters) are described in that row's text, as `App.ui.trace.thinking` is at `ui-control-inventory.md:83`. The guard's `_FACTORY` regex (`tests/test_ui_control_inventory.py:20`) matches only `App.ui.X = function`, so no other top-level name (no `App.ui.chartBlock`) is created.
  - The row's owned-classes cell lists every class the chart, table, tooltip, placeholder and glimmer emit, in the backticked form the guard parses (`:96`), including the `ui-chart-series-` family.
  - `App.ui.thinking.dots` is sub-entry text in the existing Thinking row. `ui-thinking-dots` stays owned there, and the placeholder reuses it.
  - SVG classes are assigned through a `cls` variable (`var cls = ...; el.setAttribute('class', cls)`). Do not rely on the emitted-class guard's blind spot for direct `setAttribute('class', ...)` on SVG (`tests/test_ui_emitted_classes.py:11-20`).
  - If testids with suffixes (`<testid>-tooltip`, `<testid>-source`, `<testid>-data`) trip a testid guard or need entries in `docs/ui-testid-registry.md`, add them.
  - `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py` and `tests/test_ui_guards.py` pass.
- [ ] AC18. Contract tests run in Chromium and WebKit (`engine_page`) and assert structure, names, classes, table contents, keyboard behaviour, theme repaint, reduced motion, block outcomes and placeholder shapes, never pixel positions. They are claimed by the `contracts-chat` lane: add `'test_ui_chart*'` to `contracts_chat_pat` (`scripts/run-tests.sh:252`). Otherwise they fall into `contracts-controls` as the complement. Measure the lane's time with `THE_ONE_REQUIRE_WEBKIT=1` and raise `[contracts-chat]=90` (`:82`) to measured + 25%, rounded up to 30 s. Update the budget comment in the script and the lane table and prose in CLAUDE.md in the same change. Check `tests/test_run_tests_lanes.py` (around `:104`) for any hardcoded `contracts-chat` file list. Prefer re-budgeting to a new lane; a new lane touches `LANE_LIST`, `CANON_LANES`, the budget table, the `case` at about `:302`, the alias comment at `:23-27` and the lane tests.
- [ ] AC19. Gate: `THE_ONE_TEST_NETNS=1 make test-unit` passes (the expected skip count, or a stated reason). `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1` runs of `--lane contracts-chat` and `--lane contracts-controls` pass. The static guards `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass. `ruff check` and `ruff format --check` are clean.

## Verification Steps
- AC1-AC4: read `docs/chart-format.md` against DD2; list the corpus files; `expected.json` keys equal the `invalid/` file names (asserted in `tests/test_chart_spec.py`).
- AC5-AC7: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_chart_spec.py -x --timeout 30`; `grep -n "^from\|^import" the_one/visuals/chart_spec.py` shows no forbidden imports.
- AC8-AC14: `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_ui_chart_contract.py -m browser -x --timeout 60` (plus the placeholder file if split).
- AC15: the same command on `tests/browser/test_ui_thinking_contract.py`, with no edits to that file (`git diff --stat` shows it untouched).
- AC16: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_ui_guards.py -x --timeout 30`.
- AC17: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_control_inventory.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py -x --timeout 30`.
- AC18: `bash scripts/run-tests.sh --lane contracts-chat --list` shows the new files; `tests/test_run_tests_lanes.py` passes; the lane's wall time is in the flight log.
- AC19: the commands named in it.

## Implementation Guidance

1. **Write `docs/chart-format.md` first, then the corpus.** The document is the contract; the corpus is its executable form.
   - Error sentences:
     - one sentence each, plain words, naming the series or key when there is one;
     - the first error found wins;
     - checks run in document order: syntax, then object shape, then `type`, then per-key rules, then cross-key rules, then limits.
   - Examples: `Series "2024" has 11 values, but the x axis has 12.`, `A log scale needs every value above 0; series "Latency" has 0.`, `This chart has 9 series; the limit is 8.`, `The chart text isn't valid JSON.`
   - Unknown keys are ignored at every level.
   - Strings are counted in code points.

2. **Build `the_one/visuals/chart_spec.py`.**
   - Pure Python, standard library only. `json.loads(source, parse_constant=_refuse)`.
   - Check numbers with `isinstance(v, (int, float)) and not isinstance(v, bool)`, plus `math.isfinite`.
   - Return frozen dataclasses: `ChartSpec`, `Axis`, `Series`, `Annotation`, and `ChartError`.
   - Normalise defaults: `scale` `linear`, `axis` `left`, `stacked` `False`.
   - Keep `format_tick` / `format_full` in the same module.
   - Write `tests/test_chart_spec.py` to load the corpus by path relative to the test file.
   - Add `the_one/visuals/__init__.py`. Setuptools picks the package up (`pyproject.toml:185-186`, `include = ["the_one*"]`). The PyInstaller specs find it by import analysis once Flight 3 imports it; it has no data files.

3. **Factor the thinking dots.**
   - In `js/ui/thinking.js`, extract `App.ui.thinking.dots()`: `span.ui-thinking-dots[aria-hidden=true]`, the same frames, the 120 ms interval, the reduced-motion static `' …'`, and the stop rules (destroy, or connected-then-detached).
   - Rebuild `App.ui.thinking` on it, so `settle` destroys its dots.
   - **Traps the contract test pins** (read `tests/browser/test_ui_thinking_contract.py` in full first):
     - `dots()` keys its stop rule off **the dots node's own** `isConnected` (connected once, then detached), not the thinking root's. `thinking.js:57-66` uses `root.isConnected` today; the two are equivalent because the dots sit inside the root.
     - A dots instance that was built but never attached keeps ticking.
     - `dots()` reads the reduced-motion query once at creation and then creates **no** interval, with text `' …'`.
     - Its `destroy` is idempotent.
     - `thinking.settle` calls `dots.destroy()` **before** `root.textContent = ...`, so `__live.size == 0` and `children.length == 0` after settle.
     - Keep the `.ui-thinking-dots` class and the `' ' + FRAME` text format, because the test compares `textContent`.
   - Run `test_ui_thinking_contract.py` before and after; it must not be edited.
   - Move the dots' size rule off the `.ui-thinking` scope (`components.css:2921`) so the placeholder can use it; keep the italic and muted rules scoped as they are.

4. **Build `js/ui/chart.js`, and `js/ui/chart-placeholder.js` as a separate file** with its own contract file `tests/browser/test_ui_chart_placeholder_contract.py`. The split is decided, not optional.
   - Both load from `index.html` after `message.js` (`index.html:69`), `chart.js` first. `load_harness` derives its script list from `index.html` in order (`tests/browser/_ui_engines.py:187-203`), so the `<script>` tags suffice.
   - `chart-placeholder.js` attaches `App.ui.chart.placeholder` to the existing `App.ui.chart`. Only `chart.js` contains `App.ui.chart = function`.
   - ES5, no HTML-string sinks; `App.ui.util.el` for HTML and `document.createElementNS` for SVG.
   - **Axis zero rule.** Bars include 0 on whichever axis they are drawn against: the left, or `y2` for a bar series with `"axis": "right"`. A line-only axis is fitted to its data with padding.
   - `parse` mirrors the Python checks and sentences exactly.
   - **Layout.** A small internal layout per type (scales, ticks, bars, paths, arcs) from the measured width and a fixed height. Ticks use `formatTick`; the tooltip and table use `formatFull`. Log scales use powers of ten for ticks. With `y2`, the right axis gets its own ticks.
   - **Stacking.** Stacked bars and areas accumulate per category. `null` breaks a line or area and is an empty cell in the table.
   - Annotations draw as dashed `--chart-ref` lines with their label at the end.
   - **Keyboard and tooltip.** One wrapper with `tabindex="0"` and the role and name of AC9. `pointermove` over the plot picks the nearest x. Keys follow AC11. The tooltip is positioned inside the figure, never outside the bubble.
   - **Theme.** No colour literals in JavaScript: classes such as `ui-chart-series-1` and their CSS do the painting.
   - `block` composes `parse` + the chart or the notice (AC13), inside try/catch, falling back to the notice with the plain headline.
   - `placeholder`:
     - The shapes are built from DOM boxes styled by owned classes.
     - The glimmer is a CSS animation on an owned class, disabled under `prefers-reduced-motion: reduce`.
     - "Show source" is an `App.ui.disclosure({variant: 'plain'})` holding an `App.ui.codeBlock`; `setSource` calls the code block's `set`.
     - `setType` swaps the shape and the label in place, once per real change.

5. **Tokens and contrast.**
   - Start from the approved board values: dark `#a78bfa #22d3ee #fbbf24 #f472b6 #4ade80`, then an orange, a blue and a slate; light `#6d28d9 #0e7490 #b45309`, then pink, green, orange, blue and slate in shades dark enough to pass.
   - `--chart-ref` is the board's amber: `#fbbf24` dark, `#b45309` light.
   - Tune any value that fails 3:1 on any of the three backgrounds. Record the final palette in the flight log and in the document's palette appendix (AC4b).
   - Add the mirror entries and a parametrized pair test with a small alpha-composite helper.

6. **Catalogue and contracts.**
   - Add the catalogue rows.
   - Write the contract tests with `load_harness`/`engine_page` (pattern: `tests/browser/test_ui_notice_contract.py:18-34`).
   - Feed the corpus from Python into `page.evaluate` for the JS-parity test.
   - Add the files to `contracts_chat_pat`, measure the lane and re-budget it (AC18).

**Work order.** Follow steps 1-6 in order: (a) document, corpus and Python; (b) the dots refactor and tokens; (c) `chart.js`; (d) the placeholder, the catalogue and the lane. Get each part green before starting the next.

## Edge Cases
- **An empty series list, a series with all `null` values, or a single category:** the first two are validation errors with their own sentences, as the document says. A chart with one category draws one bar or point, with no division by zero in scales.
- **Every value equal** (a flat line): the y domain pads, so the scale has a non-zero span.
- **Negative values on bars:** bars grow down from 0, and the axis includes 0. A log scale with negatives is an error.
- **Very long category labels:** truncated with an ellipsis in the axis; full text in the tooltip and table.
- **200 categories:** ticks thin out to fit the width; every category stays in the table.
- **A chart attached to a zero-width container** (a hidden drawer): layout waits until the width is above 0.
- **`destroy()` called twice, or before layout:** a no-op the second time; no observer or interval is left behind.
- **The placeholder's `setType` with an unknown type or `null`:** generic shape.

## Files Affected
- `docs/chart-format.md` (new), `docs/ui-control-inventory.md`
- `tests/fixtures/charts/**` (new), `tests/test_chart_spec.py` (new)
- `the_one/visuals/__init__.py`, `the_one/visuals/chart_spec.py` (new)
- `the_one/interfaces/web/static/js/ui/chart.js`, `js/ui/chart-placeholder.js` (new), `js/ui/thinking.js`, `index.html`
- `the_one/interfaces/web/static/css/components.css`, `css/tokens.css`
- `tests/browser/design_tokens.py`, `tests/test_design_tokens_a11y.py`
- `tests/browser/test_ui_chart_contract.py`, `tests/browser/test_ui_chart_placeholder_contract.py` (new)
- `CLAUDE.md` (the lane budget table and prose), `docs/ui-testid-registry.md` (if the testid guard needs it)
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` (if the lane table or budgets change)
- The flight log

## Citation Audit
Verified at `293a81d2` by the Flight Director at leg design:
- `js/ui/thinking.js:30` — `App.ui.thinking = function (opts)` - verified
- `js/ui/disclosure.js:25-60` — `App.ui.disclosure(opts)`: variants `bordered` and `plain`; plain takes no meta, actions or chevron; `testid`, `summaryTestid` - verified
- `js/ui/page.js:166-197` — `App.ui.codeBlock({text, label, maxHeight, trim, testid, className}) -> {el, set, refresh}` - verified
- `index.html:62-70` — ui script order, `message.js` at `:69` and `composer.js` at `:70` - verified
- `css/components.css:2921-2923` — dots size rule scoped to `.ui-thinking` - verified
- `css/components.css:2844` — `.ui-message--assistant` background `var(--surface-translucent)`, `max-width: min(100%, 46rem)` - verified
- `css/tokens.css:78`, `:225` — `--surface-translucent` dark `rgba(255, 255, 255, 0.03)`, light `rgba(24, 24, 27, 0.03)` - verified
- `tests/test_design_tokens_a11y.py:85`, `:117` — `contrast_ratio(fg_hex, bg_hex)`, `_palette(theme)` - verified
- `pyproject.toml:185-186` — `include = ["the_one*"]` - verified
- `docs/ui-control-inventory.md:69-85` — "Feedback and status" rows incl. Thinking and Notice - verified
- `tests/test_ui_emitted_classes.py:17-22`, `tests/browser/test_ui_notice_contract.py:18-34`, `tests/browser/_ui_engines.py:192` - verified at flight design (Architect)
