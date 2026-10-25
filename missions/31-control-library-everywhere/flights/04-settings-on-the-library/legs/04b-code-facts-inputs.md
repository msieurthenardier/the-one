# Leg: code-facts-inputs

**Status**: completed
**Flight**: [Settings on the library](../flight.md)

## Objective
Build, in the library only:
- `App.ui.codeBlock`;
- `App.ui.facts`;
- the `section` `info` option;
- the `textInput` options `min`, `max`, `step`, `inputMode` and `width: 'short'` (B3).

Each is contract-tested in Chromium and WebKit, with a catalogue row. **No consumer moves.**

Split from the original leg 04a at its design review (2026-10-23).

## Context
- **Flight decisions:** DD4, DD12 (`codeBlock`'s marker is `ui-code-block`, and the legacy `code-block` hands over in leg 08b; `facts` is new classes only), DD11, DD7 (row 27).
- `.code-block` today has `overflow-x: auto` only. `maxHeight` needs `overflow-y: auto` too.
- `App.ui.infoButton` (`js/ui/field.js` about `:133`) takes `description` and `label`. The section `info` option maps `{text, label}` onto it.
- The Test section's title row today is `.area-admin .section-title-row` (`admin.css` about `:481-505`): a title, then the info button, then the eyebrow rule after the icon. Reproduce it under library classes for `.editor-section`.

## Outputs
1. **`App.ui.codeBlock({text, trim, maxHeight, label, className, testid})`** → `{el, set(text)}`.
   - It renders a read-only `pre.code-block.ui-code-block`, plus `className`.
   - `trim` (**default false**) strips leading and trailing **blank lines** only, never indentation (A1). Callers opt in, so existing text stays byte-identical (leg 04f's review).
   - `maxHeight` is `'tall'` (24rem) or `'short'` (18rem), with `overflow-y: auto`.
   - **When the content overflows**, it gets `tabindex=0`, `role=region` and `aria-label` from `label`, so a keyboard user can scroll it (WCAG 2.1.1). Overflow is measured on attach and on every `set(text)`; there is no ResizeObserver. A text-only node with no `label` gets no region role, and the catalogue states that a scrollable block needs a `label`.
2. **`App.ui.facts({rows: [{label, value, mono, testid}], testid})`** → `{el, set(rows)}`.
   - A `dl.ui-facts` of `div.ui-facts-row > dt + dd` wrappers (HTML5-valid, and they carry the per-row testids). A `mono` value is monospace.
3. **`App.ui.section({info: {text, label}})`**: the title, an `infoButton` (description `text`, label `label`), then the eyebrow rule, in a library title row (for example `.ui-section-title-row`). A computed check proves the rule still draws after the button.
4. **`App.ui.textInput` options:**
   - `min`, `max` and `step` (attributes);
   - `inputMode`;
   - `width: 'short'`: about 10ch, with `flex: none` or `max-width`, so it applies even inside the full-width `.field-input` (`width: 100%`) rule. Ledger row 27.
5. Catalogue rows and contract tests (literal `App.ui.codeBlock(` and `App.ui.facts(` calls) in `contracts-controls`.

## Acceptance Criteria
1. Each output is contract-tested in both engines:
   - `codeBlock`: trim (blank lines only), both heights, the overflow region (role, name and `tabindex` present only when it overflows; re-evaluated on `set`), `className`;
   - `facts`: the DOM shape, `dt`/`dd` pairing, mono, per-row testids;
   - section `info`: the info button reachable by Tab and named, the rule drawn after it;
   - `textInput`: the attributes, and the computed width with `width: 'short'` inside a `field`.
2. **`codeBlock` matches today's look:** computed font, padding, background and border are the same as a legacy `pre.code-block` fixture.
3. `OWNERSHIP_ALLOWANCE` is unchanged; no consumer file changes; `ui-code-block` and `ui-facts` appear nowhere outside the library (grep).
4. The unit tier, the static guards, both contracts lanes and `agent-tabs` pass. `agent-tabs` covers the self-configuration code blocks, which still use the legacy markup.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_token_definitions.py tests/test_ui_ownership.py tests/test_ui_control_inventory.py -q -x --timeout 120`.
- Lanes `contracts` and `agent-tabs`, with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`.
- `make test-unit` once.

## Files Affected
- `static/js/ui/field.js`, `static/js/ui/editor.js`, a new library file for `codeBlock` and `facts` if preferred (`page.js` from 04a); `static/css/components.css`.
- The new and extended `tests/browser/test_ui_*_contract.py` files.
- `docs/ui-control-inventory.md`, `the_one/agents.md`, the flight log.

## Citation Audit
- `field.js:18` `textInput`: verified (FD grep).
- `field.js` about `:133` `infoButton`; `.code-block` with `overflow-x: auto`; the `.field-input` width: from the 04a design review.

## Amendment from leg 09's design review (2026-10-23)
- **`facts` rows accept a node or an array of nodes as `value`** (as well as text), and a per-row `testid` and `valueTestid`. Date and time's "A new chat starts with" row is two nodes. Contract-tested.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
