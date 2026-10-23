# Leg: disclosure

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Add `App.ui.disclosure`, a native `<details>`/`<summary>` control with a bordered and a plain variant, summary actions and the armed-confirm look on a summary. Contract-test it in both engines and move its first consumer, the self-configuration history, onto it with no visible change.

## Context
- **Flight DD4** ("`App.ui.disclosure(opts)`") is the spec. **DD11:** the style-hook rule, the cascade-layer rule, the ledger and in-progress log lines. **DD10:** Flight 2 DD11's size and role-structure assertions.
- **The two looks to reproduce exactly:**
  - **bordered:** today's folder-panel look, borrowed from the MCP editor's tool tiles. `css/studio.css` (inside `@layer areas`):
    - `.area-studio .mcp-tool-item` (about `:155-164`): surface, hairline border, `--radius-sm`, hover accent border;
    - `.mcp-tool-summary` (about `:166-175`): flex, gap 10px, padding 8px 12px, `--font-size-body-sm`, no marker;
    - `.mcp-tool-summary-text` (ellipsis);
    - `.mcp-tool-chevron` (`--fg-tertiary`, rotates 90° when open, accent on summary hover);
    - `.mcp-tool-body` (padding 8px 12px 10px, dashed top border).
  - **plain:** `components.css` `.advanced-collapsible` (about `:1596-1611`): top border, padding-top 12px, summary `--fg-secondary` at `--font-size-body-sm`, `:focus-visible` outline, `[open]` summary `--fg`. Its only live consumer is `self-config-history.js:81`.
- **The armed state on a summary.** Today it is `studio.css` about `:984-996`:
  - `.mcp-tool-item:has(> .kb-folder-summary.confirm-delete)` takes a danger border;
  - `[data-confirm-title]` and the delete button take the danger colour.

  `App.ui.confirm` (alias `App.confirmDelete`) adds `.confirm-delete` to the element it is given. Here that is the summary, and the label swap targets `[data-confirm-title]` inside it.
- **The svg pointer-events rule.** `studio.css` about `:969` sets `.kb-folder-delete-btn svg { pointer-events: none; }`. Blink tests the click's target node, so an `<svg>` inside a summary button would toggle the details. This is load-bearing and moves into the control for any action placed in the summary.
- **The `toolRow` precedent** (`js/ui/tile.js`, `details.ui-tool-row`; catalogue row about `:105`): a control inside a `summary`, with native HTML keeping clicks on it from toggling. It is the pattern for `actions`.
- **This leg does not touch the knowledge section.** The folder panels move in leg 06a. The `.mcp-tool-*` rules stay for the MCP editor (Flight 5) and the knowledge panels (until 06a), as recorded intentional duplicates, like the tool-row rules in Flight 2.

## Inputs
- **Requires leg 01 to have landed:** the lane split and squawk 0233, so a new `<script>` needs only a valid order.
- `js/ui/*.js` factories, `ui/core.js` (`App.ui.util.el`, `mountSlot`), `ui/confirm.js`, `ui/button.js` (icon-only buttons), `ui/tile.js` (`toolRow`'s `details` handling).
- `css/components.css`, which is `@layer components`. Library sections are banner-commented per owner.
- `docs/ui-control-inventory.md` (a catalogue row per factory), `tests/test_ui_control_inventory.py` (it requires the row plus a `tests/browser/test_ui_*.py` calling `App.ui.disclosure(`), and `tests/test_ui_ownership.py` with `tests/_ui_ownership_allowance.py` (owned classes declared in the row).
- `tests/browser/_ui_engines.py` (`engine_page`, `load_harness`). The harness root has no area ancestor.
- `js/areas/studio/self-config-history.js:77-105`: `details.advanced-collapsible.self-configuration-history-details` (testid `revision-history-details`), `summary` (testid `revision-history-summary`, text "History", later "History (N)"), and the body list `revision-history`.
- `tests/`: 5 references to `advanced-collapsible`/`revision-history-summary`/`revision-history-details`. Grep them; all testids are kept.

## Outputs
- **`App.ui.disclosure(opts)`** in a new `js/ui/disclosure.js`, loaded in `index.html` right after `ui/button.js` (and `ui/confirm.js`) and before any consumer.
  - **Options:**
    - `variant: 'bordered' | 'plain'`, required, with no default, so a caller always states the look;
    - `summary` (string or node);
    - `meta` (an array of non-interactive nodes, such as chips, placed after the text; they are part of the summary's name);
    - `actions` (an array of interactive nodes placed after `meta`, before the chevron; they are not part of the summary's name);
    - `open` (bool);
    - `onToggle(open)`;
    - `onFirstOpen(body)` (called once, the first time it opens, including when `open: true` is set at creation);
    - `chevron` (bool, default `true` for bordered, `false` for plain);
    - `testid`, `summaryTestid`, `summaryTextTestid` (on the summary-text span, so consumers such as the knowledge folder panels can read the text by testid; added at FD planning of leg 06a), `dataset`, `className`.
  - **Returns** `{el, summary, summaryText, body, actions, setOpen(bool), isOpen(), setSummary(textOrNode), destroy}`.
    - **Naming.** The summary gets `aria-labelledby` set to the `summaryText` id plus each `meta` node's id (ids generated with `App.ui.util.uid`). So its accessible name is the text and the meta, and each action keeps its own name, outside the summary's.
    - **The confirm title.** `summaryText` always carries `data-confirm-title`, so `App.ui.confirm` armed **on `ctl.summary`** swaps that text ("Confirm delete?") and restores it on lapse or commit.
    - **`setSummary`** replaces only the summary-text content, never `meta`, actions or the chevron. While the summary is armed (`.confirm-delete` present) it is a no-op and returns `false`, so a caller can never clobber the confirm text. The 0088 rule is that callers do not rename an armed summary.
    - **Opening.** An internal `opened` flag drives `onFirstOpen`. With `open: true`, `onFirstOpen(body)` runs synchronously at creation, and `onToggle` does **not** fire for that initial state: the constructor ignores the first queued `toggle` event when the state is unchanged. `onToggle` uses the `toggle` event, never `click`.
    - **`destroy`** removes the toggle listener, drops `onToggle`/`onFirstOpen`, and makes later `setOpen`/`setSummary` calls no-ops.
  - **The plain variant** takes no `meta`, `actions` or `chevron: true`; any of these throws. It keeps the native disclosure marker. It carries **no** `margin-top`: the caller or area owns spacing, so the history's existing area rule `.area-studio .self-configuration-history-details { margin-top: 12px }` stays. Unknown `variant` throws `App.ui.disclosure: unknown variant "…"`, mirroring `button`.
  - **The node is long-lived.** Nothing in the control rebuilds `el` or `summary`. A caller rebuilds only inside `body`.
- **Owned classes, a new family:** `ui-disclosure`, `ui-disclosure--bordered`, `ui-disclosure--plain`, `ui-disclosure-summary`, `ui-disclosure-text`, `ui-disclosure-actions`, `ui-disclosure-chevron`, `ui-disclosure-body`. Each variant's declarations are copied exactly from the source rules above, including hover, `[open]`, `:focus-visible`, `::-webkit-details-marker` and the `pointer-events: none` rule for `.ui-disclosure-actions svg`.
- **The armed look on a summary** (owned by the disclosure, keyed on the confirm control's class):
  - `.ui-disclosure--bordered:has(> .ui-disclosure-summary.confirm-delete)` takes the danger border;
  - `.ui-disclosure-summary.confirm-delete [data-confirm-title]` takes the danger colour;
  - each action button and its icon (`.ui-disclosure-summary.confirm-delete .ui-disclosure-actions > *` and their `svg`) take the danger colour. A library button sets its own colour, so inheritance from the actions wrapper is not enough.

  **No ownership-check change is needed.** `tests/test_ui_ownership.py` scans only `static/js/**` outside `js/ui/` and `css/{chat,studio,admin,base}.css`, not `components.css`. The `studio.css` `confirm-delete: 3` allowance stays until leg 06a removes the knowledge rules.
- **The self-configuration history** uses `App.ui.disclosure({variant: 'plain', summary: 'History', testid: 'revision-history-details', summaryTestid: 'revision-history-summary', className: 'self-configuration-history-details'})`.
  - The history list is appended to `body`, and `ctl.el` is appended where the `<details>` is today (`historySection.appendChild`).
  - The "History (N)" write (`self-config-history.js` about `:203`) goes through `setSummary`.
  - The `.advanced-collapsible` and `.advanced-caption` rules are then dead (`.advanced-caption` has no user) and are removed from `components.css`.
  - **The stale references updated in the same change:**
    - `self-configuration-tab.js:71`;
    - `self-config-history.js:78`;
    - the comment at `css/studio.css:621`;
    - the testid registry row at `docs/ui-testid-registry.md` about `:314`;
    - the docstring at `tests/browser/test_flow_agent_tabs.py:15`.
- **The catalogue row** for "Disclosure" (options, states, returns, owned classes, and the note on actions in a summary). The tokens section is unchanged.
- **The contract tests:** `tests/browser/test_ui_disclosure_contract.py`, engine-parametrized, in the `contracts-controls` lane.

## Acceptance Criteria
- [ ] `App.ui.disclosure` exists with the options and returns above. `variant` is required: it throws on a missing or unknown value.
- [ ] **Contract tests pass in Chromium and WebKit** (`THE_ONE_REQUIRE_WEBKIT=1`). They prove:
  - Enter and Space on the summary toggle it;
  - a click on the summary toggles it;
  - **an action button in `actions`, including one whose content is an `<svg>` icon, does not toggle the disclosure** on click, Enter or Space, and its own handler fires;
  - `onToggle` fires with the new state;
  - `onFirstOpen` runs exactly once (open → close → open);
  - `setOpen` works without firing `onFirstOpen` twice;
  - `setSummary` keeps the actions and the chevron nodes (the same node identity);
  - rebuilding `body`'s children leaves `el.open` unchanged;
  - after `destroy`, toggling fires no callback.
- [ ] **Role structure:**
  - the summary is the first child of `details`;
  - its accessible name is exactly the text plus the `meta` (through `aria-labelledby`), with no action names;
  - each action keeps its own accessible name;
  - the body is not inside the summary.
- [ ] **Confirm on the summary:** `App.ui.confirm` armed on `ctl.summary` swaps the summary text to the confirm label. On lapse, and after commit, the original text is back. `setSummary` while armed returns `false` and changes nothing.
- [ ] **The svg click:** a test clicks the action's `<svg>` node itself (a locator on the svg, or a dispatched event with the svg as target), and the disclosure does not toggle. Falsify it once by removing the `pointer-events: none` rule, see it fail, and restore it.
- [ ] **No fixed sleeps:** the tests wait on the `toggle` event or on `el.open` (`page.wait_for_function`), never a fixed timeout. The `destroy` test waits for the event to settle before it asserts that no callback fired.
- [ ] **Computed-style parity** under an `area-studio` ancestor (DD11):
  - **bordered:** the border, radius, summary padding, gap and font size match a legacy `<details class="mcp-tool-item">` fixture rendered beside it in the same host. The harness loads every stylesheet `index.html` lists, so the real `studio.css` applies. Follow the `test_ui_chip_list_contract.py` legacy-fixture precedent;
  - **plain:** matches a fixture copy of the old `.advanced-collapsible` CSS kept in the test (the source rule is deleted in this leg, as chip-list did with `LEGACY_LOCKED_CHIP_CSS`). Compare everything except `margin-top`;
  - the open chevron's transform is 90°;
  - **the armed look:** after `App.ui.confirm` arms an action on the summary, the bordered border colour, the confirm-title colour and the action icon's computed colour are all the danger token. Check in both themes.
- [ ] **The self-configuration history** renders through the disclosure with its testids, text and look unchanged: the computed styles of the summary and the top border match before/after in both themes, and the 12px area margin stays.
  - The node-identity and open-across-save test (`test_studio_self_configuration_dirty.py` about `:288-311`) passes unchanged.
  - The `agent-tabs` lane passes with no test-behaviour change; selectors on retired classes, if any, move to testids.
- [ ] `.advanced-collapsible` and `.advanced-caption` are gone. `git grep -nE 'advanced-(collapsible|caption)' -- ':!missions'` is empty.
- [ ] The catalogue row, the inventory guard, the ownership check, `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass. The sink and ownership allowances do not grow.
- [ ] `contracts-controls`, `contracts-overlay` (no regressions) and `agent-tabs` pass under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`, and `make test-unit` passes.
- [ ] The ledger has a row for this leg: "none visible" if the parity checks hold, or each difference with its reason.

## Verification Steps
- `PYTHON=.venv/bin/python THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 bash scripts/run-tests.sh -m browser tests/browser/test_ui_disclosure_contract.py -x --timeout 60`
- `--lane agent-tabs`, `--lane contracts-controls` and `--lane contracts-overlay` with the same env.
- `make test-unit`
- `git grep -nE 'advanced-(collapsible|caption)' -- ':!missions'` prints nothing.

## Implementation Guidance
1. **Log a start line.** Read `tile.js`'s `toolRow` `details` branch and `button.js`'s icon-only button for the idioms: `util.el`, testid placement, `destroy`.
2. **Write `disclosure.js`** and its CSS section in `components.css`, banner-commented as owned by `App.ui.disclosure`, with declarations copied exactly from the sources.
3. **Write the contract tests first** for the behaviour, then the parity checks, mounting under an `area-studio` wrapper with `studio.css` loaded, as `test_ui_chip_list_contract.py` (about `:290-292`) does.
4. **Move the self-configuration history** onto it. Remove the dead `.advanced-collapsible` rules.
5. **Write the catalogue row.** Run the guards, the lanes and `make test-unit`.
6. **Flight log:** the leg entry, the ledger row, in-progress lines.

## Edge Cases
- **`onFirstOpen` with `open: true`:** the body fills at creation, synchronously, before the caller appends `el`. State this in the catalogue.
- **Toggle events are asynchronous** (`toggle` fires after the attribute change). `onToggle` uses the `toggle` event, never `click`, so programmatic `setOpen` reports the same way.
- **An action that is a form control** (checkbox, button) is skipped by the summary's default handler, but its `svg`/`span` children are not. The `pointer-events: none` rule covers `svg`. For text spans inside an action button, the target is the button. Test an icon-only `App.ui.button` inside `actions`.
- **WebKit's details marker** uses `::-webkit-details-marker`; `list-style: none` covers Chromium. Keep both.
- **The armed `:has()` rule.** WebKit supports `:has()`; confirm in the contract test.

## Files Affected
- New: `js/ui/disclosure.js`, `tests/browser/test_ui_disclosure_contract.py`
- `css/components.css` (the new section; `.advanced-collapsible` removed)
- `index.html` (the script tag)
- `js/areas/studio/self-config-history.js` (the consumer), and `self-configuration-tab.js` (its comment at about `:71`)
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `css/studio.css` (a comment only), `tests/browser/test_flow_agent_tabs.py` (a docstring only)
- The flight log

## Citation Audit
Checked at `332496d` on 2026-10-22 (FD read). The design review (Sonnet Developer, cycle 1: approve with changes) confirmed the citations and added these:
- summary naming through `aria-labelledby` with `meta` against `actions`;
- the `data-confirm-title` and armed `setSummary` rule;
- the armed icon colour;
- the initial-open and `onToggle` semantics;
- the plain variant's limits and margin;
- the stale references;
- no ownership-check change;
- the legacy CSS fixture for plain;
- the svg falsification.

The FD read covered:
- `studio.css:136-205,969,984-996`;
- `components.css:1596-1611`;
- `self-config-history.js:77-105`;
- `knowledge-section.js:945-1035` (the source of the bordered look and the armed pattern; not changed here);
- the catalogue toolRow row (about `:105`).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
