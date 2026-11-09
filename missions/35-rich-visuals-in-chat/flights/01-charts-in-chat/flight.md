# Flight: Charts in Chat

**Status**: completed
**Mission**: [Rich Visuals in Chat](../../mission.md)

## Contributing to Criteria
- [x] **Charts appear in the app** (all of it: the six types, theme, theme change without reload, the text alternative)
- [x] **A visual appears when it is ready** (for charts: the streaming placeholder, the error notice, Copy reply unchanged; Flight 2 extends it to live visuals)
- [x] **Operators choose per agent** (all of it)
- [x] **The prompt cost is measured and accepted** (for the chart format; Flight 2 measures the live-visual addition). Accepted by the operator, with m35 baselines recorded; the HAT's two later prompt additions (+96 tokens in all over m35) were sentinel-checked only, and their full re-baseline is deferred.
- [x] **Visuals work in the desktop app** (for charts: WebKit contract lanes plus a WebKitGTK probe, both themes; WebView2 and WKWebView are checked in Flight 2's engine leg with live visuals)

---

## Pre-Flight

### Objective
An agent reply can carry a ```` ```chart ```` block that the chat draws as a chart in place: bar, line, area, scatter, pie or sparkline, with stacking, two y-axes, log scales, reference lines and a value tooltip, in the current theme, with a "Show data" table under it. While the block streams, a glimmering placeholder in the chart's shape holds the space, with "Rendering chart" and the thinking dots, and the source one click away. A block that cannot be drawn shows a plain error with the source under "Technical details". Each agent gets a "Rich visuals" switch on its General tab, on by default for new and existing agents. When on, a short platform-prompt section teaches the agent the format. The chart format is written down once, language-neutral, with a shared set of sample specs. A server-side validator, which Flight 3 reuses for connector images, is tested against them, and so is the browser control. An eval scenario set shows the default models can write valid charts, and the prompt's size growth gets the operator's decision.

### Open Questions
- [x] Block tag → DD1 (`chart`)
- [x] Exact chart format and its limits → DD2, DD3
- [x] One format, two renderers: how the browser and the server cannot drift → DD3, DD4
- [x] Do user or routine messages render charts? → no: only assistant replies render markdown (`transcript.js:74`); recorded in DD6
- [x] Text alternative → DD5 ("Show data" disclosure, operator choice)
- [x] Scope beyond the six types → DD2 (richer: stacking, dual axes, log scale, reference lines, tooltip; operator choice)
- [x] Streaming treatment → DD8 (option B, glimmering placeholder shaped by type; operator choice)
- [x] Error display → DD9
- [x] Switch placement, storage and default → DD11
- [x] How the prompt learns about charts, and only when on → DD12
- [x] How evals prove models write valid charts → DD13 (new check plus its own scenario set; operator choice)
- [x] Theme following → DD7 (CSS custom properties, no JavaScript)
- [x] Fence detector mismatch: all fences or visual only → DD10 (all fences)
- [x] HAT leg → yes (operator, 2026-11-08), with the usage walk (M31 F6 debrief recommendation 1)

### Design Decisions

**DD1 — The block tag is `chart`**
- A chart is a fenced block whose info string's first token is exactly `chart` (lowercase), parsed as today (`markdown.js:169-176`).
- Any other language, including `json`, stays a code block, so a model showing JSON source is unaffected.
- Flight 2 adds its own tag for live visuals; this flight reserves nothing else.

**DD2 — The chart format, version 1** (scope: operator chose "richer", 2026-11-08)
- One JSON object. By convention `type` is the first key; every example and the prompt write it first (DD8 reads it early).
- Keys:
  - `type` (required): `bar`, `line`, `area`, `scatter`, `pie`, `sparkline`.
  - `title` (optional, ≤ 120 characters).
  - `x` (object): `label`, `values` (strings or numbers; the categories or the x positions; required except for `scatter`), `scale` (`linear` default, or `log`).
  - `y` (object, optional): `label`, `unit` (≤ 12 characters, shown on ticks and in the tooltip and table), `scale`, `min`, `max`.
  - `y2` (object, optional): a right-hand axis with the same keys as `y`; only for `bar`, `line` and `area`.
  - `series` (required, 1-8 entries): `name`, `values` (numbers or `null` for a gap, one per `x` value; for `scatter`, `[x, y]` pairs), optional `axis` (`left` default, or `right`, which needs `y2`), and optional `type` (`bar` or `line`) to mix bars and a line in one `bar` or `line` chart.
  - `stacked` (optional boolean; `bar` and `area`).
  - `annotations` (optional, ≤ 5): reference lines, `{"axis": "y" | "y2" | "x", "value": number | category, "label": string}`.
- A `pie` uses `x.values` as slice labels and exactly one series of non-negative values with a positive total, at most 12 slices. A `sparkline` is one series and an optional `title`, drawn without axes, legend or "Show data".
- Unknown keys are ignored. That is forward-compatible and kind to small models that add a `colors` key. Every known key is checked strictly.
- Limits: 8 series, 2,000 values in all (a `null` gap counts as a value), 200 categories, labels ≤ 60 characters, a log scale needs every value on it > 0.
- **Numbers are numbers.** `true`/`false` are not numbers. `NaN`, `Infinity` and `-Infinity` are refused at parse time. String lengths are counted in Unicode code points.
- **Number display is locale-neutral and defined in the document**, never the system locale (WebKitGTK follows it): ticks use a compact form (`1.2k`, `3.4M`, at most 3 significant digits); the tooltip and table show the full value with `,` grouping and `.` decimals. A `unit` of `$`, `€`, `£` or `¥` is a prefix; any other unit is a suffix after a thin space.
- Trade-off: the richer options cost validator code, renderer code and Flight 3's server renderer. All are optional, so the minimal spec in the prompt stays small.

**DD3 — The format is documented once, with a shared corpus, and the server validates too**
- `docs/chart-format.md` is the language-neutral spec: keys, rules, limits and the exact error sentences.
- A corpus under `tests/fixtures/charts/` holds `valid/*.json` and `invalid/*.json`, plus `invalid/expected.json`, which maps each invalid file to its one error sentence.
- A pure-Python validator, `the_one/visuals/chart_spec.py` (a new package with no Pillow and no web imports), exposes `parse_chart(source: str) -> ChartSpec | ChartError`. It is used by the eval check in this flight (DD13) and by the connector renderer in Flight 3.
- The browser validator (`App.ui.chart.parse`, DD4) is a separate implementation of the same document.
- **Both are tested against the corpus with identical sentences**: a unit test for Python, and a contract test that loads the corpus files into the page for JavaScript.
- **Known drift traps get corpus cases**: Python's `json.loads` accepting `NaN`/`Infinity` (refuse through `parse_constant`); `bool` being an `int` in Python (exclude it explicitly); code points against UTF-16 units (an emoji in a label at the limit); `null` in the value count; the number-format examples (DD2) for both formatters.
- A new rule lands in the doc, the corpus and both validators in the same leg.
- Rationale: two implementations are unavoidable (the server cannot run the browser's JavaScript, and the browser needs no server round trip). The corpus is what keeps them from drifting.

**DD4 — `App.ui.chart`: one library control, three entry points**
- `App.ui.chart.parse(source) -> {ok: true, spec} | {ok: false, message}`: the browser validator.
- `App.ui.chart({spec, testid}) -> {el, destroy()}`: the drawn chart.
  - Structure: `figure` > `figcaption` (title, legend) > the SVG (`role="img"`, `aria-label` carrying a one-sentence summary such as "Line chart, Monthly revenue vs target, Jan to Dec, 2 series") > the "Show data" `App.ui.disclosure` holding a `<table>`.
  - The SVG is built with `createElementNS` (precedent: `ui/date-time.js:92`), with no HTML-string sink. Every SVG class is assigned through a `cls` variable the emitted-class guard can see (`tests/test_ui_emitted_classes.py:17-22`), or the catalogue row owns the `ui-chart-series-` prefix.
  - **Layout happens after attach, in real pixels.** The chart builds its structure at once (it is created inside a DocumentFragment during a commit, so its width is unknown). On its first `ResizeObserver` callback, and on later width changes coalesced to one animation frame, it lays out the SVG geometry at the container's width. The plot height is fixed (about 240 px; a sparkline is a 32 px row). Text is laid out at its true size and never scaled, so it stays legible in the drawer's overlay mode. The observer is disconnected by `destroy()` and when the chart is detached.
  - Contract tests assert structure, classes, names and the table's contents, never pixel positions (text measurement differs by engine and font).
- `App.ui.chart.block(source, opts) -> Node`: what the markdown hook calls (DD6). It parses, then returns either the chart or the error notice of DD9.
- `App.ui.chart.placeholder({type, testid}) -> {el, setType(t), setSource(text), destroy()}`: the streaming placeholder of DD8.
- **Tooltip.** It shows on pointer hover and on keyboard focus. The keyboard target is a wrapper around the plot with `role="group"`, its own name ("{title}, chart values") and a description ("Use the arrow keys to read values"); the SVG inside keeps `role="img"`. It is one tab stop, and the arrow keys move between x positions (Home and End jump to the ends; Escape hides it). The tooltip is visual; the accessible path to the numbers is the "Show data" table (DD5).
- **Library rules.**
  - Each piece gets a catalogue row in `docs/ui-control-inventory.md` with its owned classes.
  - Contract tests run in Chromium and WebKit: `tests/browser/test_ui_chart_contract.py`, plus `test_ui_chart_placeholder_contract.py` if the leg splits it.
  - The controls load in `index.html` among the `js/ui/` scripts, so `load_harness` sees them (`tests/browser/_ui_engines.py:192`).
  - The test files join the explicit `contracts-chat` list (`scripts/run-tests.sh`, `contracts_chat_pat`). That lane has a 90 s budget (61 s measured) that two engines × two themes of charts will exceed, so leg 1 measures the new lane time and re-budgets it in `scripts/run-tests.sh` (or gives the chart contracts their own lane) before leg 1 closes.

**DD5 — Text alternative: a "Show data" disclosure plus a spoken summary** (operator choice, 2026-11-08)
- Under every chart except a sparkline, a closed "Show data" disclosure opens a real `<table>`: a header row, one row per category or point and one column per series, with units in the cells. Annotations are listed under it ("Reference line: Target, $150k").
- The table scrolls in a bounded box (as on the approved light-theme board), never widening the reply.
- The assistant bubble's markdown table rules (`css/components.css:2908`) would restyle it, and the contract harness does not load the bubble, so the chart's table is scoped by its own owned class. A flow test checks it inside a real reply.
- The SVG's `aria-label` is the one-sentence summary; a sparkline's label also carries its first and last values.

**DD6 — The markdown hook is a per-call option, used only for assistant replies**
- `App.markdown.render(text, {copyLiveEl, codeBlockRenderers})`. `renderCodeBlock` (`markdown.js:923-960`) consults `renderOptions.codeBlockRenderers[lang]` the same way it reads `copyLiveEl`. On a match it appends the returned node instead of `div.markdown-code-wrap`; a renderer that returns nothing falls back to the code block.
- **The render is made safe around renderers.**
  - `render` restores the previous `renderOptions` in its `finally` instead of setting it to `null` (`markdown.js:971-976`). A nested `render` (none today) then cannot strip `copyLiveEl` or the renderers from the outer render's later blocks.
  - The renderer call is wrapped in try/catch and falls back to the plain code block. A throw inside `pacingTick`'s commit or inside finalize would otherwise lose the whole reply.
  - The parser records whether a fence was closed (`meta.closed` on the CODE_BLOCK node; `markdown.js:181-187`) and passes it to the renderer (DD9's cut-off case), and DD10 uses it to confirm boundaries. `meta.closed` is false whenever the block's input ran out before a closing line, including a nested fence ended by the end of its list item. That is deliberately conservative; do not "fix" it.
- markdown.js creates no SVG and stays free of HTML sinks; the chart code lives in `js/ui/` (`tests/_ui_guard_helpers.py:433`, `:455` keep guarding it).
- The transcript's `mdOpts()` (`transcript.js:53`) adds `codeBlockRenderers: {chart: App.ui.chart.block}`. It is the only caller of `render` (`:74`, `:269`, `:311`), and only for `role === 'assistant'` (`:74`). User messages, routine-run messages, tool output and the thinking disclosure stay plain text.
- Copy reply keeps copying the raw stored markdown (`transcript.js:96`, `:312`), so a chart is copied as its source.

**DD7 — Chart colours are tokens, and the theme follows by CSS alone**
- New tokens in both theme blocks of `css/tokens.css`:
  - `--chart-1` … `--chart-8` (categorical);
  - `--chart-grid` and `--chart-axis` (or the existing `--border`/`--fg-faint`, if the leg finds them equal);
  - `--chart-ref` for reference lines (the warning amber on the approved boards).
- Approved dark values start from the boards: violet `#a78bfa`, cyan `#22d3ee`, amber `#fbbf24`, pink `#f472b6`, green `#4ade80`, then orange, blue and slate. Light starts from the boards' `#6d28d9`, `#0e7490`, `#b45309`, … The leg tunes the rest to pass.
- Each series token passes **3:1 (WCAG 1.4.11, non-text)** against the backgrounds a chart actually sits on, gated by a new parametrized pair test. In a reply that is the assistant bubble, whose background is `--surface-translucent` (`css/components.css:2844`) composited over `--bg`, in both themes. The pair test computes that composite; the chart card's own fill, `--surface` (boards 1-3), is tested too. The test is in `tests/test_design_tokens_a11y.py` (pattern at `:189-202`). The hex values are mirrored by hand in `tests/browser/design_tokens.py` (the sync check is mirror-driven, `test_ui_guards.py:355`).
- The SVG paints through classes (`ui-chart-series-N`) whose CSS uses `var(--chart-N)`. A theme switch, including an OS change in auto mode that fires no event (`theme.js:139-143`), repaints every chart with no JavaScript and no re-render.
- Series are never told apart by colour alone: the legend, the tooltip and the table carry names, and line series beyond the fourth also get a dash pattern.

**DD8 — Streaming: a glimmering placeholder shaped by the chart type** (option B, operator choice 2026-11-08; board 4 approved)
- **What the reader sees.**
  - While a **top-level** ```` ```chart ```` block is open in the streaming tail, the raw JSON is hidden. A top-level block's opening line starts at column 0, outside any list or quote. A chart nested in a list item streams as raw text and is drawn when it is committed (decided at design review, recorded in the flight log; the HAT confirms). In its place is a placeholder card at the reply's width: "Rendering chart" plus the thinking spinner dots, a glimmering title bar and a glimmering plot area.
  - Its shape is generic until the block's **first key** has streamed in as `"type": "<t>"` (anchored at the start of the object, `^\s*\{\s*"type"\s*:\s*"(bar|line|area|scatter|pie|sparkline)"`, so a series-level `"type"` never sets it; a block that does not put `type` first stays generic), then follows the type: bars for `bar`, a line for `line`, `area` and `scatter`, a disc for `pie`, a short row for `sparkline`. The label names it ("Rendering line chart").
  - A "Show source" disclosure under it shows the raw block as it streams.
  - **When the closing fence arrives, the chart replaces the placeholder at once.** The end of a top-level closing-fence line is a safe commit boundary (DD10), so there is no gap where raw JSON flashes or the text after the fence stays hidden while the stream waits for a blank line. The parser restarts cleanly after a close (`markdown.js:182-188`), so this boundary agrees with the parser. The chart or the error notice takes the placeholder's place, and finalize does the same for a reply that ends with the block.
- **Reduced motion.** No glimmer (a static fill) and the spinner's existing static " …" (`ui/thinking.js:52-55`).
- **The dots.** They are factored out of `App.ui.thinking` into a reusable piece, `App.ui.thinking.dots() -> {el, destroy}`, a sub-entry like `App.ui.trace.thinking`. It keeps every behaviour `tests/browser/test_ui_thinking_contract.py` pins: `span.ui-thinking-dots[aria-hidden]`, one interval per instance, stop on settle, on destroy or when detached, and the reduced-motion text. The dots CSS selector stops being scoped to `.ui-thinking`.
- **The seam.**
  - The streaming tail is one bare text node (`ui/message.js:116-142`), and transcript.js may not emit library classes (`test_ui_ownership`). So the message handle gains a library method that **hides the tail from a given offset and shows a node in its place**. A working name is `setTailHold(offset, node | null)`.
  - **Invariants the leg pins with contract tests:**
    - A text node cannot be partly hidden, so the handle keeps the logical tail string itself and renders the visible part (before `offset`) and the held part (the node) separately.
    - `tail()` always returns the full logical text; `appendText` always appends to it, whether or not a hold is set.
    - The order is fixed: transcript.js commits the prefix up to the fence first, then calls `setTailHold(0, placeholder)`.
    - `commit(fragment, consumed)` with `consumed > offset` clears the hold (and destroys nothing it does not own: the caller destroys the placeholder). With `consumed ≤ offset`, the hold stays and the offset shifts down by `consumed`.
    - `commit` still returns early on an empty fragment without consuming (`message.js:128-131`). That is why the offset is a parameter, never assumed to be 0: a prefix that renders to nothing leaves the fence above 0.
    - `finalize` clears the hold before appending its fragment.
  - **Detection uses the one fence state machine.** transcript.js finds the open chart fence with the same scanner as `findSafeRenderBoundary` (DD10), so a ```` ```chart ```` line inside an already-open ```` ``` ```` block is content, not a fence.
  - Text before a top-level chart fence is committed at once: a column-0 ```` ``` ```` line ends a paragraph (`markdown.js:254`), so the prefix is safe to render. transcript.js then passes the placeholder to the handle and feeds `setSource` on each pacing tick.
  - The placeholder is created at most once per open block. transcript.js destroys it when the block is committed or finalized, and on `clearLog` and a session switch.
- **A chart cut off before its closing fence** (Stop, an error, the step limit) is told apart from a broken one. The parser's `meta.closed` (DD6) is false, so `App.ui.chart.block` shows a **muted** notice, "This chart was cut off before it finished.", with the source under Technical details, instead of the danger "Couldn't draw this chart." The streaming placeholder never outlives the bubble's finalize.

**DD9 — A chart that cannot be drawn: one plain sentence, the source under "Technical details"**
- `App.ui.chart.block` returns, on a parse or validation failure of a closed block, an `App.ui.notice({tone: 'danger'})`. Its body holds the headline "Couldn't draw this chart." and the validator's one sentence, plus an `App.ui.disclosure({variant: 'plain', summary: 'Technical details'})` whose body is the block's source in an `App.ui.codeBlock` (`ui/page.js:166`), never through markdown. This is the composition `transcript.js:470-483` uses for agent errors (`ui/notice.js:8-38` has no details option).
- The rest of the reply renders normally.
- Error sentences come from the shared document (DD3), for example: `Series "2024" has 11 values, but the x axis has 12.`

**DD10 — The streaming fence detector over-detects, never under-detects, and commits at a top-level close**
- Today `findSafeRenderBoundary` (`transcript.js:244-258`) toggles `inFence` on any line that starts with "```" after optional indentation (`:251`), for opening and closing alike.
- The parser opens a top-level fence only at column 0 (`markdown.js:169`) and closes it only on `/^```\s*$/` (`:176`). But it also parses list items and blockquotes recursively, so an indented fence inside a list item **is** a code block there. The Architect verified `"- Step:\n  ```python\n  x = 1\n\n  y = 2\n  ```"` parses as a `codeBlock` in a `listItem`. A column-0-only detector would treat the blank line inside that block as safe and commit half a fence.
- **The rule: the detector may hold a commit longer than the parser needs, never shorter.** No indentation rule alone achieves that.
  - Design review cycle 2 ran three cases through the real parser where any "closer indented no more than its opener" rule commits inside a fence. One is a code block in a list step closed at column 0 and followed by more text: that column-0 line ends the list item and *opens* a new top-level fence. Small models write it often. Today's toggle has the same gap.
- **So every boundary is parser-confirmed.**
  1. The cheap line scanner proposes candidates, as today: a blank line, and the new kinds below. Its opener stays permissive (`^\s*```` after optional indentation).
  2. A candidate is accepted only when `App.markdown.parse(prefix)` holds **no** CODE_BLOCK with `meta.closed === false` at any depth. DD6 adds that flag, so a fence the parser still considers open always blocks the commit.
  3. The parse runs only when a new candidate appears (at most once per pacing tick, on the prefix since the last commit), never on every chunk. Replies are small, and the parser is linear.
- **Three kinds of candidate boundary:**
  1. a blank line outside a fence (today's);
  2. **new:** the end of a top-level closing-fence line, so a chart replaces its placeholder the moment it closes (DD8);
  3. **new:** the start of a top-level ```` ```chart ```` opener line, so the text before it is committed at once and the placeholder can take over (DD8). A column-0 ```` ``` ```` line ends a paragraph (`markdown.js:254`).
- Chart detection waits for the opener line's newline, since ```` ```chart ```` and ```` ```charts ```` look the same until it arrives.
- These rules apply to every fence, not only charts. The flow tests pin:
  - a code block nested in a numbered step with a blank line inside;
  - the cycle-2 case: a list-step block closed at column 0, followed by text and another ```` ``` ````;
  - an indented ```` ``` ```` inside a top-level block;
  - an info string containing backticks;
  - an unclosed block;
  - a top-level close followed straight away by text.

**DD11 — The "Rich visuals" switch: an agent field, on by default, saved with the General form** (board 6 approved)
- `AgentConfig.rich_visuals: bool = True`.
- **Schema v52**: a guarded `ALTER TABLE agents ADD COLUMN rich_visuals INTEGER NOT NULL DEFAULT 1` in the v51 pattern (`db/schema.py:3284-3318`), `CURRENT_VERSION = 52` (`schema.py:18`). The default backfills existing agents to on. The migration tests' `51` pins move (`tests/test_db_migration.py`, eleven sites, `:5019` to `:6564`; the leg greps for every one). The test template builds through `ensure_schema`, so it needs no edit.
- The repository's `save` names the column (`repositories.py:281`, `:300`, `:319`) and `_row_to_config` reads it (`:542`).
- **The API.** `update_agent` keeps the stored value when a PUT omits the field, mirroring `notes_enabled` (`api.py:1545-1546`). Without that, an omitted field would silently turn the switch back on. Create takes the model default. Responses carry it through `model_dump()`.
- `self_configuration/projection.py:64-73` does not list it: it stays operator-only, invisible to `get_my_configuration`.
- **The UI.**
  - `App.ui.toggle({label: 'Rich visuals', hint, dataset: {field: 'rich_visuals'}})` goes in the General tab's Behavior section (`general-tab.js:196-202`), patched in `setAgent` (`:334-359`).
  - `collectFormData` (`agent-form-data.js:86-110`) gains a checkbox branch that reads `.checked`, so a change marks the form dirty and Save sends a boolean.
  - A missing field reads as on everywhere in the browser (`defaults()`, `setAgent`, the drawer: `rich_visuals !== false`), so an older cached row never shows the switch off.
  - Hint text in this flight: "Tell this agent it can answer with charts. When it's off, the agent isn't told, but any chart in its replies is still shown." Flight 2 widens it to live visuals when they ship.
- **When a change takes effect**: like any other saved agent setting, at the agent's next prompt build. Leg 3 reads the factory and session code and records the exact moment (the next turn, or the next chat) in the flight log. Leg 4, where the flag first reaches the prompt, writes the test that pins it.
- **The drawer.** A "Rich visuals: On/Off" group joins "What it can use" (`agent-drawer.js:526-591`, the Self-configuration pattern), read from the `agents` store row with no fetch.
- Turning it off removes only the prompt section (DD12). Rendering never reads it (mission operator decision).

**DD12 — A platform-prompt section for agents with Rich visuals on**
- `Capabilities` gains `visuals: bool = True` (`platform_prompt.py:30-45`). A new `Section("visuals", "Rich visuals", "agents with Rich visuals on", lambda c: c.visuals, ...)` sits after `formatting` (`:181`).
- `tool_free_capabilities` (`:273-281`) keeps it, since writing a chart needs no tool.
- Settings › Prompts lists it with its "Applies when" line automatically (`platform_sections_for_ui`, `:220-250`).
- **Draft text**, final wording and size set in leg 4 by measurement:
  > To show data as a chart, write a fenced code block with the language `chart` holding one JSON object, `type` first: `{"type": "bar", "title": "…", "x": {"values": […]}, "series": [{"name": "…", "values": […]}]}`. Types: bar, line, area, scatter, pie, sparkline. Optional: axis `label`, `unit`, `"scale": "log"`, `"stacked": true`, a right axis `y2` with a series `"axis": "right"`, and `"annotations": [{"axis": "y", "value": 150, "label": "Target"}]`. Use a chart when it makes numbers clearer.
- **Threading the flag: one keyword, one source of truth** (the `tools_preloaded` precedent).
  - The prompt that is actually rendered is built by `build_system_prompts` / `build_system_prompt` in `agent/prompt_layers.py`, which constructs its own `Capabilities` from keyword arguments (`:149`). The factory's `caps` from `capabilities_from_registry` (`factory.py:688`) are not what gets rendered, so setting the flag there alone would do nothing.
  - So `build_system_prompts` and `build_system_prompt` gain `visuals: bool = True`, passed into that `Capabilities(...)`.
  - `AgentFactory.create` passes `visuals=config.rich_visuals` and sets `agent.rich_visuals` on the built `Agent`.
  - `self_configuration/pending.py:132` passes `visuals=getattr(agent, "rich_visuals", True)` on both its main path and its fallback path, so a pending self-revision preview matches the agent's real prompt. The fallback renders `caps` from `capabilities_from_registry` (`pending.py:132-137`, `:165-167`), which has no `visuals` parameter today (`platform_prompt.py:289-311`). So `capabilities_from_registry` gains `visuals: bool = True` too, and the factory and both `pending.py` paths pass it.
  - No database read in `prompt_layers.py`. The `default` agent and test agents with no stored row take the keyword's default, and a mid-session toggle reaches a running agent only when it is rebuilt, never through a side read.
- **Pins that move:**
  - `tests/_platform_prompt_pins.py` and the byte-for-byte tests (`tests/test_platform_prompt.py:22-27`);
  - the "toggling changes nothing" list (`:36-41`), which must not include `visuals`;
  - the UI row ids (`:123-134`);
  - `evals/tokens.py:164-178`'s capability combinations. Strict mode would not raise on its own here, because `visuals` defaults to True; the `visuals=False` combinations are added anyway, so the measurement covers an agent with the switch off.
- **Gate lanes (squawk 0334).** A new Prompts section moves count and label pins in the `settings` lane (`tests/browser/test_flow_admin_settings_nav.py:244-275`) and the unit pins in `tests/test_platform_prompt.py:123-134`. Leg 4 greps `tests/` for the section count and labels and runs every matching lane, not only its own.

**DD13 — Evals: a new `reply_has_valid_chart` check and its own scenario set** (operator choice, 2026-11-08)
- **The check.** `reply_has_valid_chart(turn=, types=[...]?)` passes when the reply holds a ```` ```chart ```` block that `the_one.visuals.chart_spec.parse_chart` accepts, optionally of one of the given types. This changes `evals/checks.py`, so the frozen scoring digests (`tests/test_evals_freeze.py::SCORING_DIGESTS`) are updated in the same commit (operator-approved).
- **The scenario set.** It lives in its own directory, `evals/visuals/scenarios/`, run with `--scenarios-dir evals/visuals/scenarios`, mirroring `evals/routines/scenarios` (README `:147-150`). The `s11` platform fingerprint (`fingerprint.py:48`) therefore does not move for it. Three scenarios, each with the usual phrasings × facts variants:
  - `chart-when-asked`: data given, a chart asked for, so `reply_has_valid_chart`;
  - `chart-fits-data`: a time series, so `line` or `area`, and shares, so `pie` or `bar`;
  - `no-chart-unasked`: a prose question with no numbers, so `reply_not_matches` a chart fence.
- **The procedure** (sortie 11's DD14 standard, debrief recommendation 3):
  1. **A mid-flight review and commit checkpoint** before any quota-heavy run. The agentic workflow normally reviews and commits once at the end of the flight. Here, legs 1-3 and leg 4's product code are reviewed and committed on the flight branch first, so the eval runs measure committed code; this is the flight's one planned exception to the single end-of-flight review.
  2. Run an n=5 sentinel on the most exposed cells.
  3. Run the n=20 sets.
  4. `measure-prompt`.
  5. `compare --baseline evals/baselines/s11-platform.json` on the platform set, **and** `compare --baseline evals/baselines/s11-routines.json` on the routines set (`--scenarios-dir evals/routines/scenarios`), because routine agents get the section too. Pass-rate gates must hold. The size gates will fail by construction (`bare` 168 and `all-on` 354 prompt-text tokens grow, because eval agents take the `rich_visuals=True` default, `evals/harness.py:388`).
  6. **Operator decision at the end of leg 4**: accept the growth and record same-prompt re-baselines (`evals/baselines/m35-platform.json`, `m35-routines.json`), or cut the text and re-measure.
  7. Record `evals/baselines/m35-visuals.json` for the new set on the default models (haiku, qwen3-4b, lfm3).
- **Sortie 12 and 13 interplay.** Sortie 12 (claimed actions, status planning) also changes platform prompt text against `s11`. Whichever lands second compares against the other's new baseline. Leg 4 re-checks sortie 12's status first and records which baseline it compares against.

**DD14 — Browser tests drive charts through the mock provider**
- The mock provider's `response.content` and `stream_chunks` (CLAUDE.md "Dev mode and the mock provider") give deterministic chart replies, including a chunk split mid-block and mid-`"type"`. The streaming placeholder, the type switch, the commit swap, the error path and history re-render are all tested with no live model.
- New flow tests: `tests/browser/test_flow_chat_charts.py`, added to the explicit `chats-transcript` list (`chats_transcript_pat`). Switch tests: `tests/browser/test_flow_agent_rich_visuals.py`, which lands in `agents` by default; it must not match the `agent-tabs` globs.
- **Gate lanes per leg (squawk 0334)**, beyond each leg's own:
  - leg 1: `contracts-chat` and `contracts-controls` (the thinking dots), both engines;
  - leg 2: `chats-transcript` and `chats` (the transcript and the shared message handle);
  - leg 3: `agents` (the PUT shape and the General form) and `chats` (the drawer group), plus a grep for the drawer group count;
  - leg 4: `settings` (Prompts pins) plus the unit tier's platform-prompt pins.

**DD15 — The HAT leg includes the usage walk** (M31 F6 debrief recommendation 1)
- The HAT is a guided walk in a scratch dev instance with a real model and the mock provider:
  - ask for charts of each type;
  - two charts in one reply;
  - a chart streaming while another chat is open, and while the reply is in a background chat;
  - reopen a long chat;
  - switch theme while a chart is on screen, including the OS theme in auto mode;
  - Copy reply;
  - a broken chart;
  - turn Rich visuals off, start a new chat and check the prompt in Settings › Prompts and the drawer;
  - narrow the window to the drawer's overlay mode.
- It ends with the question the debrief asked for: "what would you want from charts day to day that this does not support?" The answers are recorded as approved follow-ups, not built in the HAT, unless they are fixes.
- Contract the HAT may not change without a spec re-author: the chart format (DD2), which Flight 3's renderer and the corpus depend on, and these testids:
  - `chat-chart`, the chart figure in a reply;
  - `chat-chart-data`, its "Show data" disclosure;
  - `chat-chart-plot`, the keyboard target;
  - `chat-chart-tooltip`;
  - `chat-chart-placeholder`, the streaming placeholder;
  - `chat-chart-placeholder-source`, its "Show source" (derived as `<testid>-source`, leg 1);
  - `chat-chart-error`, the danger and cut-off notices;
  - `agent-rich-visuals-toggle`;
  - the drawer's `chat-drawer-group[data-group="rich-visuals"]`.

### Mockups (operator-approved, 2026-11-08)
Canvas: https://claude.ai/artifact/5qfTVCkB5peb1ekzi8gCTS (private to the operator)
1. A chart in a reply, dark: a line chart with two series, a reference line, the tooltip and "Show data" closed. Approved.
2. Light theme with "Show data" open, the table in a bounded scrolling box. Approved.
3. The chart types: a sparkline as a compact row (corrected: a fenced block cannot sit mid-sentence), stacked bars, grouped bars, a stacked area, a scatter on a log x axis with a reference line, a pie, and dual y-axes. Approved.
4. Streaming: option B chosen. The operator asked for a glimmer and a type-aware shape; the board was revised to generic, bar, line and pie placeholders and approved ("excellent").
5. The error notice with Technical details. Approved.
6. The Rich visuals switch in Behavior, and the drawer line. Approved.

### Citation Audit

Verified against the working tree at `293a81d2` by the planning crew (three read-only research passes and the Flight Director). The Architect spot-checks a sample.

| Citation | Status |
|---|---|
| `static/js/markdown.js:169-176` — fence opens only at column 0, `^```(.*)$`; lang is the first info token matching `^[A-Za-z0-9_+#.-]{1,32}$`; closes on `^```\s*$` | verified |
| `static/js/markdown.js:181` — an unclosed fence runs to end of input | verified |
| `static/js/markdown.js:254` — a column-0 ```` ``` ```` line ends a paragraph | verified |
| `static/js/markdown.js:923-960` / `:965-978` — `renderCodeBlock` builds the code well; `render(text, options)` keeps `renderOptions` around a synchronous render; only option today is `copyLiveEl` | verified |
| `static/js/areas/chat/transcript.js:53`, `:74`, `:269`, `:311` — `mdOpts()`; the only `render` callers; markdown only for `role === 'assistant'` | verified |
| `static/js/areas/chat/transcript.js:244-258` / `:263-270` / `:301-313` — fence toggle on any line starting with ```` ``` ```` (indented too, `:251`); commit after a blank line outside a fence; finalize renders the tail | verified |
| `static/js/ui/message.js:116-142` — the tail is one bare text node; `commit` inserts before it; `finalize` removes it | verified |
| `static/js/ui/thinking.js` (`:6`, `:37-77`) — braille frames, 120 ms interval, reduced-motion static text, `{el, settle, destroy}`; contract pins in `tests/browser/test_ui_thinking_contract.py` | verified |
| `static/js/ui/notice.js:8-38` — options `tone`/`body`/`testid` only; details built by caller as at `transcript.js:470-483` | verified |
| `static/js/areas/studio/general-tab.js:196-202`, `:334-359`; `agent-form-data.js:86-110` — Behavior section; in-place `setAgent`; `collectFormData` reads `f.value` | verified |
| `static/js/ui/choice.js:117` — `App.ui.toggle` options incl. `dataset`, `hint`, `onChange` | verified |
| `static/js/areas/chat/agent-drawer.js:526-591` — "What it can use" groups incl. Self-configuration On/Off | verified |
| `the_one/agent/config.py:153-168` — operator booleans on `AgentConfig`; `extra: "ignore"` | verified |
| `the_one/db/schema.py:18`, `:3284-3318` — `CURRENT_VERSION = 51`; guarded ALTER pattern | verified |
| `the_one/db/repositories.py:281`, `:300`, `:319`, `:542` — explicit column lists in `save`; read in `_row_to_config` | verified |
| `the_one/interfaces/web/api.py:1545-1546` — `update_agent` preserves omitted `notes_enabled` | verified |
| `the_one/self_configuration/projection.py:64-73` — explicit field list | verified |
| `the_one/agent/platform_prompt.py:30-45`, `:142-181`, `:220-250`, `:273-281` — `Capabilities`; `SECTIONS`; UI listing; `tool_free_capabilities` keeps notes/rules | verified |
| `the_one/agent/factory.py:688`, `the_one/agent/prompt_layers.py:149`, `the_one/self_configuration/pending.py:132` — the three capability build sites | verified |
| `evals/tokens.py:164-178` — strict capability enumeration | verified |
| `evals/fingerprint.py:48`; `evals/README.md:147-150`, `:172-190` — fingerprint covers `evals/scenarios/*.toml`; separate-dir precedent; check vocabulary has no JSON check | verified |
| `evals/harness.py:388` — eval agents built with `AgentConfig(...)` defaults | verified |
| `css/tokens.css:63`, `:215`; `tests/test_design_tokens_a11y.py:189-202`; `tests/browser/design_tokens.py:59`, `:139` — theme blocks; pair-test pattern; hand mirror | verified |
| `static/js/theme.js:139-143` — OS change in auto mode fires no event | verified |
| `tests/browser/_ui_engines.py:192` — `load_harness` loads `js/ui/*.js` listed in index.html; not markdown.js | verified |
| `scripts/run-tests.sh` `contracts_chat_pat`, `chats_transcript_pat` — explicit lane lists | verified |
| `static/js/markdown.js` list-item recursion — an indented fence inside a list item parses as a `codeBlock` (Architect, run under node) | verified |
| `static/js/markdown.js:182-188` — the parser restarts at the next line after a closing fence | verified (Architect) |
| `static/js/markdown.js:971-976` — `render`'s `finally` sets `renderOptions = null` instead of restoring | verified (Architect) |
| `static/js/ui/message.js:128-131` — `commit` returns early on an empty fragment without consuming | verified (Architect) |
| `css/components.css:2844`, `:2908` — the assistant bubble's `--surface-translucent` background; bubble table rules | verified (Architect) |
| `static/js/ui/page.js:166` — `App.ui.codeBlock` | verified (Architect) |
| `tests/test_ui_emitted_classes.py:17-22` — the emitted-class guard's detection of class assignments | verified (Architect) |
| `tests/browser/test_flow_admin_settings_nav.py:244-275` — Prompts section count and label pins | verified (Architect) |

### Prerequisites
- [x] WebKit userland provisioned (`bash scripts/setup-webkit-userland.sh`); contract lanes run with `THE_ONE_REQUIRE_WEBKIT=1`
- [x] Browser runs use `THE_ONE_TEST_NETNS=1` on this WSL host
- [x] Leg 4, re-verified at the start of the leg (external sessions): the plan token at `~/.config/the-one-evals/plan-token` works, Ollama serves `qwen3-4b` and `lfm3`, and `pip install -e ".[evals]"` is in the venv
- [x] Leg 4: sortie 12's status re-checked to pick the comparison baseline (DD13)
- [x] HAT: a scratch dev instance on a port ≥ 8490 with a scratch data dir under `$HOME` (never 8484, never the default data dir), and a real provider for the "ask for a chart" steps (the plan token or Ollama), re-verified at the start of the HAT leg

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Leg 1** builds the format and the library pieces, independent of chat:
   - the spec document and the corpus;
   - the Python validator;
   - `App.ui.chart` (parse, chart, block, placeholder) and the factored dots;
   - the palette tokens with their contrast gate;
   - catalogue rows and engine contract tests.
2. **Leg 2** wires them into chat: the markdown option, the streaming hold seam on the message handle, the transcript's detection and swap, the fence-detector rules, the cut-off case, history re-render and mock-driven flow tests.
3. **Leg 3** adds the per-agent switch end to end: schema, API, General tab and drawer. It is autonomous.
4. **Leg 4** adds the prompt section and its threading, passes the mid-flight review and commit checkpoint, runs the eval procedure, and stops for the operator's size decision. It is split from leg 3 because it alone is operator-gated and spends quota.
5. **Leg 5** is the HAT.

### Checkpoints
- [x] The corpus passes in both validators with identical sentences
- [x] Every chart type renders in Chromium and WebKit, in both themes, with the table and the tooltip
- [x] A mock-streamed chart shows the placeholder, takes its type's shape, and swaps to the chart (or the error) with no flicker of raw JSON
- [x] The switch round-trips through save, reload and an omitted-field PUT, and the drawer shows it
- [x] The prompt section appears only when on; the platform pins are updated; the eval compare is run; the operator has decided on size
- [x] The full gate is green (`make gate`, `THE_ONE_TEST_NETNS=1`)

### Adaptation Criteria

**Divert if**:
- The hold seam on `App.ui.message` cannot be added without breaking the existing message contract tests or the commit/finalize invariants. Re-plan the streaming display with the operator before building around it.
- The default models fail `chart-when-asked` badly (below about 0.5 on haiku), which means the format is too hard. Return to DD2 and the prompt text with the operator rather than tune silently.
- The chart palette cannot reach 3:1 on all three surfaces in light mode with eight distinct series. Bring a smaller palette (six) to the operator.

**Acceptable variations**:
- Splitting the placeholder into its own control file and catalogue row
- The exact error sentences, as long as the doc, the corpus and both validators agree
- Reusing existing tokens for grid and axis instead of new ones
- The prompt's final wording, inside the measured size the operator accepts

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `chart-format-and-control` - The format document and shared corpus, `the_one/visuals/chart_spec.py`, `App.ui.chart` (parse, chart with tooltip and Show data, block with the error notice, placeholder with glimmer), `App.ui.thinking.dots`, chart palette tokens with the contrast gate, catalogue rows, and Chromium + WebKit contract tests
- [ ] `charts-in-chat` - The markdown `codeBlockRenderers` option (re-entrant, try/catch, `meta.closed`), the message handle's tail hold and its invariants, the transcript's top-level open-fence detection and swap, the fence-detector rules and the top-level close boundary, the cut-off notice, history re-render, mock-driven flow tests in `chats-transcript`, and the `agents.md` section
- [ ] `rich-visuals-switch` - Schema v52 `rich_visuals`, the API preserve, the General tab switch (missing reads as on), the drawer line, and recording when a change takes effect (leg 4 pins it)
- [ ] `visuals-prompt-and-evals` - `Capabilities.visuals` and its section, the `visuals` keyword through `build_system_prompts` / `capabilities_from_registry` / the factory / `pending.py`, the pins (including when a switch change takes effect), the `reply_has_valid_chart` check and `evals/visuals/`, the mid-flight review and commit, the eval procedure (`s11-platform`, `s11-routines`, the new set), and the operator's size decision
- [ ] `hat` - Guided HAT with the usage walk (DD15)

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing (`make gate` under `THE_ONE_TEST_NETNS=1`; contract lanes with `THE_ONE_REQUIRE_WEBKIT=1`)
- [x] Documentation updated (`docs/chart-format.md`, `docs/ui-control-inventory.md`, `the_one/agents.md`, CLAUDE.md where operator-facing, `evals/README.md` for the check and set)

### Verification
- Unit tier: the Python validator against the corpus; the schema v52 migration; the API preserve; the prompt section's presence and absence and its pins; the eval check offline against hand-built replies.
- Contract lanes (Chromium + WebKit): every type, both themes, the tooltip by pointer and keyboard, the table, the placeholder shapes and reduced motion, the error block, the JS validator against the corpus.
- Flow tests (`chats-transcript`, `agents`): mock-streamed charts, history, Copy reply, the switch and the drawer.
- WebKitGTK probe (`scripts/webkitgtk_probe.py`, a dev instance ≥ 8486) of a chart reply in the real desktop engine.
- Evals: the `s11` compare and the `m35-visuals` set, with the operator's size decision recorded in the flight log.
- The HAT leg's walk.
