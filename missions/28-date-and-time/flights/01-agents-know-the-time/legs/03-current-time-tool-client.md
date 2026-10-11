# Leg: current-time-tool-client

**Status**: completed
**Flight**: [Agents Know the Time](../flight.md)

## Objective

Make the UI tell the truth about `current_time`. It gets:

- a styled "Time" category on Settings › Built-in tools and on the agent
  Tools tab;
- a Tools tab checkbox that turns it off for one agent even when that agent's
  tool list is trimmed;
- an agent drawer count that matches the server;
- a "Date" layer on Settings › Prompts showing both wordings.

Browser tests cover each of these, and the docs are finished.

## Context

- Read [flight.md](../flight.md):
  - **DD6:** the three client sites;
  - **DD7:** badge tokens, classes and the a11y gate;
  - **DD3/DD4:** the `/api/info` placeholders, rendered on the Prompts page.
- **Built on legs 1 and 2a** (uncommitted on the branch; see the flight log for
  the as-built names):
  - `/api/info` returns `date_prompt_example` and
    `date_prompt_example_without_tool`;
  - `App.toolCategories` has the Time row and the frozen `whitelistExempt`
    field;
  - `AgentConfig.is_tool_enabled` exempts `current_time` from `enabled_tools`.
- **The server is the truth.** Each client site must reproduce
  `is_tool_enabled` exactly for exempt names: the whitelist is ignored and
  `disabled_tools` applies.
- The static guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`,
  `tests/test_design_tokens_a11y.py`) must run, not only browser lanes (squawk
  0106).
- `ui/feedback.js` is an `App.ui` library file, so the `contracts` lane runs
  under `THE_ONE_REQUIRE_WEBKIT=1`.

## Inputs

- Legs 1 and 2a landed. `make test-unit` is green apart from browser tests not
  yet updated (the unit tier does not run browser tests).

## Outputs

- `static/css/tokens.css`: `--badge-time` and `--badge-ink-time` in both theme
  blocks, theme-stable.
- `static/css/components.css`: `.badge--time`.
- `static/css/admin.css`: `.admin-tool-badge--time`.
- `static/js/ui/feedback.js`: `'time'` added to `BADGE_KINDS` in sorted order.
- `tests/browser/design_tokens.py`: both palettes.
- `tests/test_design_tokens_a11y.py`: the `time` entry in `_TOKEN_BADGE_KINDS`
  (~1184) and `_BADGE_INK_PAIRS` (~1332).
- `tests/test_ui_badge_kinds.py`: the count goes from 14 to 15, and any listed
  kinds are updated.
- `static/js/areas/chat/agent-drawer.js::isToolEnabled`: exempt names are
  treated as ungated.
- `static/js/areas/studio/tools-tab.js`: the `enabledSet` rule, plus a note
  on the Time tile that the tool is always loaded.
- `static/js/areas/studio.js`: the save branches.
- `static/js/areas/admin/system-page.js`:
  - the Prompts page Date layer;
  - the intro and the Notes help copy.
- `docs/ui-testid-registry.md`: three testids (`date-prompt-content`,
  `date-prompt-content-without-tool` and `time-tool-note`).
- **Browser tests:**
  - `tests/browser/test_flow_admin_settings_nav.py`;
  - `tests/browser/test_flow_admin_tools_grid.py`;
  - `tests/browser/test_flow_studio_tools_overrides.py`;
  - `tests/browser/test_flow_chat_drawer.py` (four sites, see AC3);
  - `tests/browser/test_flow_studio_knowledge_attach.py`, run and checked;
  - a new `tests/browser/test_flow_studio_time_tool.py` (the agents lane,
    through the `test_flow_studio_*` glob).
- **Docs:**
  - CLAUDE.md: one short paragraph, "current_time and the date layer (M28)",
    in Architecture beside leg 1's paragraph;
  - `the_one/agents.md`: the leg 2a section gains the client-mirror sentences;
  - `docs/ui-control-inventory.md`, only if the badge kinds are listed there.
- The flight log: the leg entry.

## Acceptance Criteria

**Badge**

- [ ] **AC1.** `--badge-time` is defined in both theme blocks of `tokens.css`
      with the same value (theme-stable, like `--badge-connectors`). Its comment
      follows the existing style.
  - The value must differ clearly from `--badge-filesystem`, `--badge-connectors`
    and `--badge-ollama`. Use deep forest green `#2e6b3f` with white ink
    (about 6.5:1). This leg's value supersedes DD7's "slate teal" wording.
  - The mirror keys are `badge_time` and `badge_ink_time`, inserted beside the
    connectors keys (~116/130 and ~200/213). Do the mirror **before** running
    the a11y gate, which reads the inks from the mirror.
  - `_TOKEN_BADGE_KINDS` is a sorted tuple; insert `"time"` between
    `"openrouter"` and `"unknown"`.
  - `--badge-ink-time` is a single value that clears 4.5:1 on the fill (the
    a11y gate proves it).
  - The values are mirrored in both palettes of `tests/browser/design_tokens.py`,
    which `tests/test_ui_guards.py::test_design_token_mirror_in_sync` checks.
- [ ] **AC2.** `.badge--time` sits in `components.css` beside the other badge
      kinds, and `.area-admin .admin-tool-badge--time` in `admin.css` beside
      `--connectors`. `BADGE_KINDS` gains `'time'`, and
      `tests/test_ui_badge_kinds.py`'s count goes from 14 to 15. `test_design_tokens_a11y.py`'s
      two lists gain `time`, and `test_badge_kind_rules_consume_the_gated_pair`
      passes. The Design language page and `docs/ui-control-inventory.md`
      list no badge kinds, so neither changes (design review).

**Client exemption (DD6)**

- [ ] **AC3. The drawer.** `agent-drawer.js::isToolEnabled(agent, name)`
      returns true for a name in `App.toolCategories.whitelistExempt` whatever
      `agent.enabled_tools` says, and false when it is in `disabled_tools`. It
      reads the list from `App.toolCategories`, not a new literal.
      `test_flow_chat_drawer.py` changes:
  - The JS/Python parity case (~420) gains `current_time` among the names, plus
    configurations with `enabled_tools: ["read_file"]` and with
    `disabled_tools: ["current_time"]`, and asserts parity with
    `AgentConfig.is_tool_enabled`.
  - The "tools" group `li` count goes from 4 to 5 (~340), and its items list
    (~353-358) gains `"Time 1 of 1"` last.
  - `test_one_tools_fetch_per_open` (~409): the count goes from 4 to 5.
  - The `Bare` agent (whitelist `["read_file","glob"]`, read_file globally
    off, ~371-378): the `li` count goes from 1 to 2, and its items are
    `["Filesystem 1 of 9", "Time 1 of 1"]`.
  - New: with `current_time` globally disabled (`seed_tool_config` with
    `enabled=False`), the drawer has no Time line.
- [ ] **AC4. The Tools tab render.** For an exempt name, `tools-tab.js`'s
      `enabledSet` is `disabled_tools.indexOf(name) < 0`, whatever the
      whitelist. On an agent saved with `enabled_tools: ["read_file"]`, the
      Time tile shows `current_time` checked, and its count badge reads
      `1 / 1 enabled` (the tab's `{n} / {m} enabled` form, also rewritten by
      `_refreshCategoryCounts`). The `current_time` **tool row** carries a
      short line, `data-testid="time-tool-note"`, which is registered in
      `docs/ui-testid-registry.md`:
      "Always available to the agent from the start of every conversation,
      even if you limit its other tools. Untick to remove it from this agent."
      The wording is provisional, and it is rendered with
      `textContent`/`createElement` (no `innerHTML`).
- [ ] **AC5. The save** (`studio.js` ~3404-3437):
  - **The branch choice** (`allOn`, and enabled versus disabled count) counts
    only non-exempt toggles.
  - **An unchecked exempt toggle** is added to `disabled_tools` in **every**
    branch.
  - **No exempt name** is ever added to `enabled_tools`.
  - **A checked exempt toggle** adds nothing.
  - **The ungated-name union** (`_storedUngatedDisabledNames()`) is unchanged.

  Browser test (`test_flow_studio_time_tool.py`):
  1. Seed an agent with `enabled_tools: ["read_file"]`.
  2. Open its Tools tab: `current_time` is checked.
  3. Untick it and save. `GET /api/agents/{name}` shows `current_time` in
     `disabled_tools` and not in `enabled_tools`, with `enabled_tools` still
     `["read_file"]`.
  4. Reload: it is unchecked.
  5. Tick it again and save: it is gone from `disabled_tools`.

  A second case, an agent with all tools on (blocklist branch): unticking only
  `current_time` and saving gives exactly `enabled_tools: null` and
  `disabled_tools: ["current_time"]`.

  More cases in the same file:
  - **Dirty state.**
    - Merely opening an agent saved with `enabled_tools: ["read_file"]` leaves
      the `editor-unsaved` caption empty and Save disabled.
    - After any save above, the caption is empty and Save disabled.
  - **The category master.** The Time master checkbox (`data-category-master="Time"`,
    whose aria-label is "Enable all Time tools", the existing a11y rule)
    unticks `current_time`, and the save puts it in `disabled_tools`.
  - **Create mode.** A new agent shows Time checked, and the saved body has
    `enabled_tools: null` and `disabled_tools: []`.
  - **Globally disabled** (`seed_tool_config("current_time", enabled=False)`,
    or the existing seeder): the Tools-tab checkbox is disabled and marked as
    operator-disabled, as for any other tool.

**Settings › Built-in tools**

- [ ] **AC6.** The Built-in tools page shows a fifth tab, "Time", holding the
      `current_time` tile with the Time badge, and the tile opens the tool
      editor.
  - `test_flow_admin_tools_grid.py` changes:
    - line ~53: the tab count goes from 4 to 5, plus an `nth(4)` "Time"
      assertion;
    - the docstrings at ~12 and ~89;
    - `expected` gains `"time": 1`.
  - `test_flow_studio_tools_overrides.py` (~93-112) expects five category tiles
    and 23 tools.
  - The Settings tile's global toggle
    (`[data-testid="tool-toggle"][data-name="current_time"]`, or the selector
    `_lists.tool_toggle` uses) disables the tool, which
    `GET /api/tools/configs` shows with `current_time` `enabled: false`. A
    toggle back re-enables it.
  - No grid, editor or Tools-tab code beyond the CSS class is needed for the
    new category. `tools-tab.js` iterates the categories, and `tools-grid.js`
    and `tools-editor.js` read `App.toolCategories`.
  - Also run `tests/browser/test_flow_studio_knowledge_attach.py::test_disabled_tools_union_survives_three_branches`
    (~335-380) deliberately. Its `_set_tool_checkboxes` now also flips the
    exempt box, and the test must still pass.

**The Prompts page**

- [ ] **AC7.** `renderPromptsPage` gains a fourth layer after Notes, titled
      "Date", with the help text "Added last to every agent's prompt, with the
      date in your time zone. The first wording is used when the agent has the
      current_time tool; the second when it doesn't."
  - It shows two `<pre>` blocks: `date-prompt-content` (filled from
    `date_prompt_example`) and `date-prompt-content-without-tool` (from
    `date_prompt_example_without_tool`). Each is preceded by a small caption,
    "With the time tool" and "Without it", rendered with `text()`/`el()` and
    not as a `.section-title`, so the title list stays four.
  - The page intro becomes "…the base prompt, the agent's own system prompt
    (set on its General tab), then rules, notes and the date…".
  - The Notes help becomes "Added after the rules when the agent keeps
    notes."
  - `fetchPrompts` fills and falls back for both new blocks, as it does for the
    others.
  - The two testids are registered in `docs/ui-testid-registry.md` beside
    `notes-prompt-content`.
  - `test_flow_admin_settings_nav.py` (~283-295) expects 5 `<pre>` blocks in
    that order, and the title list `["base prompt", "rules", "notes", "date"]`.
    The testid order is `base-prompt-content`, `rules-prompt-content`,
    `notes-prompt-content`, `date-prompt-content`,
    `date-prompt-content-without-tool`. It asserts that `pres.nth(3)`
    (with-tool) contains `{today's date}` and `current_time`, and that
    `pres.nth(4)` (without) contains `{today's date}` but not `current_time`.
  - `fetchPrompts` takes five targets, and its catch path fills all five.

**Gates and docs**

- [ ] **AC8.** The static guards pass: `tests/test_ui_guards.py`,
      `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`,
      `tests/test_ui_badge_kinds.py`, `tests/test_tool_categories.py` and
      `tests/test_nav_helper.py`.
- [ ] **AC9.** `make gate` is green: the unit tier, then every browser lane, 3
      at a time, with `THE_ONE_REQUIRE_WEBKIT=1` and `TEST_TIMEOUT=3600`. The
      lane summary and `PARALLEL_RESULT` line are recorded in the flight log,
      together with any OVER BUDGET warning.
  - A lane flake is re-run in isolation, per the project rule, before it is
    called a regression. The re-run is recorded.
- [ ] **AC10.** The docs:
  - CLAUDE.md gains one short paragraph on `current_time`, its exemption and
    the date layer (pointing at `agents.md`);
  - `agents.md`'s leg 2a section names the three client mirrors and
    `App.toolCategories.whitelistExempt` as their single source;
  - `docs/ui-control-inventory.md` is updated only if it lists badge kinds.

## Verification Steps

- **AC1, AC2, AC8:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_badge_kinds.py tests/test_tool_categories.py tests/test_nav_helper.py -x --timeout 60`.
- **AC3:** `PYTHON=.venv/bin/python TEST_TIMEOUT=900 bash scripts/run-tests.sh --lane chats -x -k drawer`. Use `-k` or the file path through the lane's pass-through.
- **AC4-AC6:**
  - `TEST_TIMEOUT=900 bash scripts/run-tests.sh tests/browser/test_flow_studio_time_tool.py tests/browser/test_flow_studio_tools_overrides.py -x`;
  - `… tests/browser/test_flow_admin_tools_grid.py -x`.

  Browser files may be passed directly to `run-tests.sh`; check its usage
  (`--help`). Always use `run-tests.sh`, never bare pytest.
- **AC7:** `… tests/browser/test_flow_admin_settings_nav.py -x`.
- **AC9:** `THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 make gate`.
  Run it in the background and wait. It takes about 18 minutes and is longer
  than a foreground Bash call.

## Implementation Guidance

1. **Tokens, CSS, BADGE_KINDS and the mirror first.** Then run the static
   guards.
2. **The drawer:**
   `var EXEMPT = (App.toolCategories && App.toolCategories.whitelistExempt) || [];`.
   Treat `EXEMPT.indexOf(name) !== -1` as ungated. The script load order
   already puts `tool-categories.js` before the area scripts; confirm it in
   `index.html`.
3. **The Tools tab:** set the `enabledSet` rule. The tile note goes on the Time
   category tile, or on the tool row; keep it to the existing DOM-builder
   idiom.
4. **The studio save:**
   - partition `toggles` into exempt and non-exempt;
   - run the existing branch logic on the non-exempt set;
   - then append unchecked exempt names to `disabled_tools`.

   The `disabled_tools` order is exact:
   1. the non-exempt disabled names (blocklist branch only);
   2. the unchecked exempt names;
   3. `_storedUngatedDisabledNames()`.

   `enabled_tools` (whitelist branch) holds non-exempt checked names only.
   `allOff` is unused; ignore it.
5. **The Prompts page:** add the layer through the existing `promptLayer` and
   `promptPre` helpers, then extend `fetchPrompts`.
6. **Browser tests** use `_nav`, `_lists` and `seeders`: no raw route hashes
   and no retired selectors. They seed through the existing seeders and API
   with the credential helpers. The new file is
   `tests/browser/test_flow_studio_time_tool.py`.
7. **Docs** next, then the full gate last.

## Edge Cases

- **Older agents with `current_time` already inside `enabled_tools`** (none
  exist, but a hand-edited row could). The render ignores the whitelist for
  exempt names. On the next save, the save drops it from `enabled_tools`.
  This is harmless.
- **The tool globally disabled** (`tool_configs` `enabled: false`): the Tools
  tab already greys out or marks operator-disabled tools through
  `disabledTools`. Keep that behaviour for `current_time`; it is not special.
- **The drawer with the tool globally off:** `builtinGroups` already drops
  globally disabled tools, so the Time group disappears.
- **The Prompts page `/api/info` failure path:** all five blocks show "(failed
  to load)".

## Files Affected

- **CSS:** `static/css/tokens.css`, `components.css`, `admin.css`.
- **JS:** `static/js/ui/feedback.js`, `areas/chat/agent-drawer.js`,
  `areas/studio/tools-tab.js`, `areas/studio.js`,
  `areas/admin/system-page.js`, and possibly
  `areas/admin/design-language/status-section.js`.
- **Docs:** `docs/ui-testid-registry.md`, possibly
  `docs/ui-control-inventory.md`, `CLAUDE.md`, `the_one/agents.md`.
- **Tests:**
  - `tests/browser/design_tokens.py`, `tests/test_design_tokens_a11y.py`,
    `tests/test_ui_badge_kinds.py`;
  - `tests/browser/test_flow_admin_settings_nav.py`,
    `test_flow_admin_tools_grid.py`, `test_flow_studio_tools_overrides.py`,
    `test_flow_chat_drawer.py`;
  - new `tests/browser/test_flow_studio_time_tool.py`.
- The flight log.

## Citation Audit

Checked at `afa7855` plus legs 1 and 2a:

- `ui/feedback.js::BADGE_KINDS`: 8-23, 14 kinds.
- `tokens.css` connectors badge: 175/193 and 324/340.
- `admin.css:317`, `.admin-tool-badge--connectors`.
- `design_tokens.py`: 116/130 and 200/213.
- `test_design_tokens_a11y.py`: 1187 (`_TOKEN_BADGE_KINDS` entry) and
  1344-1345 (the ink pair).
- `test_flow_admin_settings_nav.py`: 283-295, the three `<pre>` blocks and
  titles.
- `docs/ui-testid-registry.md`: 65-66.
- `system-page.js::renderPromptsPage`: 67, and `fetchPrompts`.
- `agent-drawer.js`: 95 and 129-138.
- `tools-tab.js`: 56-64.
- `studio.js`: 3404-3437.

All present.

---

## Post-Completion

Completion steps are Flight Control protocol, driven by the execution
workflow. They are not repeated here.
