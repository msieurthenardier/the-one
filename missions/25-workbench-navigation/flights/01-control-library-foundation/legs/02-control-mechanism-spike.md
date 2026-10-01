# Leg: control-mechanism-spike

**Status**: completed
**Flight**: [Control Library Foundation](../flight.md)

## Objective

Settle how the control library is built:
- Create the `App.ui` core and the first factories (`button`, `textInput` and `field`).
- Build the list pane both ways: a factory with a controller, which is committed, and a
  throwaway light-DOM custom element.
- Judge both mechanisms against the six exit criteria in Chromium and WebKit, and record
  the decision with evidence.
- Verify the DD8 native-`<dialog>` stacking rule in a reusable test module.

## Context

- Flight decisions implemented: **DD1** (mechanism, cleanup rule, spike scope, six
  criteria), **DD2** (library `testid` rule, now enforced by the Leg 1 guards), **DD3**
  (resolver), **DD4** (no sinks; icons parsed), **DD5** (layout, export idiom, naming),
  **DD8** (dialog rule; the spike's checks), **DD14** (list-pane ARIA and keyboard), and
  DD15 rows A9, A10, A11 and A31 for the list pane. Read them in `flight.md`.
- **Leg 1 (`ui-test-apparatus`) outputs this leg consumes.** Read Leg 1's flight-log
  entry for the actual names and the WebKit route outcome before starting.
  - `engine_browser`/`engine_page` fixtures and the disk harness in
    `tests/browser/_ui_engines.py`. The harness loads `static/js/ui/*.js` in
    `index.html` order automatically once the `<script>` tags exist.
  - `tests/browser/_a11y_resolvers.py`: `collect_label_failures` and
    `assert_controls_labelled_and_described`.
  - `scripts/webkitgtk_probe.py`.
  - The testid-value and ui-dir zero-token guards in `tests/test_ui_guards.py`.
- This leg creates `the_one/interfaces/web/static/js/ui/`. From now on the Leg 1 guards
  are live, not vacuous.
- What is **committed** from the spike: `core.js`, `button.js`, `field.js`
  (`textInput` and `field`) and `list-pane.js` (the factory variant). The next leg
  (`core-controls`) completes and hardens these; this leg must still make each committed
  factory correct, keyboard-operable and tested.
- What is **thrown away**: the `<ui-list-pane>` custom element. It lives only in a test
  fixture file injected with `page.add_script_tag` (e.g.
  `tests/browser/_spike_ui_list_pane_ce.js`). It is **deleted before landing**; its
  evidence goes to the flight log.
- No visual styling work beyond what the factories need to be usable. The deep-violet
  treatment and `.btn-icon` CSS arrive in Leg 3; the button factory already emits the
  `.btn-icon` class.
- Interim invariant (DD8): no production surface opens a native modal in this flight. The
  dialog checks run against a **test-only** harness.

## Inputs

- `the_one/interfaces/web/static/index.html`: script order; `icons.js` comes before
  `markdown.js`.
- `the_one/interfaces/web/static/js/icons.js`: `App.icon(name)` returns an SVG string;
  `App.icons` is the map.
- `the_one/interfaces/web/static/js/areas/studio/knowledge-section.js::_appendIcon` (around
  line 163), the DOMParser SVG pattern to promote.
- `the_one/interfaces/web/static/js/areas/layout/section-nav.js`, the roving-tabindex
  precedent (Up/Down/Home/End).
- `the_one/interfaces/web/static/js/dialog.js`: today's overlay. It is **not modified**
  here.
- `the_one/interfaces/web/static/css/components.css`: the `.btn-*`, `.field-*`,
  `.is-invalid` and `.empty-state` vocabulary.
- `tests/test_index_asset_cache_busting.py:59` asserts exactly 55 `/static` refs.
- `the_one/agents.md`: the "Modals" bullet at around line 1666 ("NOT a native `<dialog>`
  migration") and the Design language v3 section.
- `missions/25-workbench-navigation/reference/reference-spec.md` §3, the list column:
  row anatomy and the selected treatment.

## Outputs

- **Library code**, under `the_one/interfaces/web/static/js/ui/`:

  | File | Contents |
  |---|---|
  | `core.js` | `App.ui` namespace; `App.ui.util.el`, `uid`, `icon`, `rovingFocus` |
  | `button.js` | `App.ui.button` |
  | `field.js` | `App.ui.textInput`, `App.ui.field` |
  | `list-pane.js` | `App.ui.listPane` |

- **CSS** for the list pane, in `@layer components`, in a flat file (`components.css`, or
  a flat sibling with its own `<link>`): `.ui-list-pane*` classes. They use existing
  tokens only (`--accent-translucent` wash, inset `--accent` ring, `--surface-elevated`
  hover).
- **Load order and count.** `index.html` gains `<script>` tags for the four files, after
  `icons.js` and before `markdown.js`. Add a `<link>` if a new CSS file is created.
  `tests/test_index_asset_cache_busting.py` updates its count (55 → 59, or 60 with a new
  CSS link).
- **Tests:**
  - `tests/browser/test_ui_library_contract.py`: engine-parametrized contract tests for
    the committed factories. The name falls to the `shared` lane.
  - `tests/browser/test_ui_mechanism_spike.py`: engine-parametrized comparison of
    factory vs custom-element list pane against the six criteria. It is kept only if it
    still tests committed code after the custom element is deleted; otherwise its
    factory-side assertions move into the contract file and it is deleted.
  - `tests/browser/_dialog_rule.js`: a test-only DD8 harness, a minimal wrapper
    implementing the rule.
  - `tests/browser/_dialog_rule_checks.py`: reusable check functions taking a page and a
    small adapter (open, close, open-confirm), so Flight 2 can point them at the real
    wrapper.
  - `tests/browser/test_ui_dialog_rule.py`: runs the checks against the harness in both
    engines.
- **Docs.** `the_one/agents.md`:
  - the "Modals" bullet is rewritten to DD8 (native `<dialog>` for new modals; legacy
    overlay migrates in Flight 2; the interim invariant);
  - a new **"Control library (`App.ui`)"** section is started: mechanism (with the
    decision and its evidence summary), export idiom, `util` vs factories, the cleanup
    rule, the testid rule, and how to add a control.

  `CLAUDE.md` gets nothing yet; the pointer lands in the reference leg.
- **Flight log.** A leg entry plus a **Decisions** entry, "Control-library mechanism".
  The decision entry holds the evidence table: criterion × mechanism × engine, with
  pass/fail and one-line evidence each. It also holds the WebKitGTK probe output and the
  DD8 results.

## Acceptance Criteria

**Core and factories**

- [x] **AC1 — Core.** `ui/core.js` defines `window.App.ui` and `App.ui.util` with:
  - `el(tag, attrs, children)`, a DOM builder with no HTML strings;
  - `uid(prefix)`, a monotonic, page-unique id;
  - `icon(name)`, which returns an `SVGElement` parsed with `DOMParser`
    (`image/svg+xml`) and imported into `document`, throws on an unknown name, and is
    `aria-hidden="true"` and `focusable="false"`;
  - `rovingFocus(container, itemSelector, opts)`, keyboard handling bound on the
    container only:
    - it queries items **at event time**, because rows re-render;
    - it handles only ArrowUp, ArrowDown, Home and End (plus Left and Right when
      `opts.horizontal`);
    - it **clamps** at the ends by default; `opts.wrap: true` exists for menus later;
    - it never intercepts Enter or Space, so `<a href>` rows keep native navigation and
      ctrl-click.

  Code rules:
  - **Syntax.** The file is ES5 (no `class`, `let`/`const` or arrow functions), uses
    `'use strict'` and the IIFE idiom, and guards the namespace with
    `window.App = window.App || {}`.
  - **No app globals.** The disk harness loads only `icons.js` before `ui/`, so `ui/`
    files must not touch `app.js` globals (`App.router`, `App.config`, …).
  - **No sink words.** It has no inner-HTML sink tokens, not even in comments. The DD4
    guard scans comments.
  - **`uid`** itself emits `ui-<prefix>-<n>`, e.g. `uid('in')` gives `ui-in-1`.
  - **`icon`** checks `App.icons[name]` exists and throws if not (`App.icon` only warns
    and returns `''`). After parsing, it throws if `documentElement.nodeName !== 'svg'`,
    which covers a `parsererror` document. It then uses `document.importNode`.
  - **Export idiom (DD5).** The only non-function assignments to `App.ui` are the
    namespace line `App.ui = App.ui || {}` and the `App.ui.util = App.ui.util || {}`
    line. Every factory is exactly one line of the form `App.ui.<name> = function (opts) {`.
  - **`testid` in `ui/`.** The live testid-value guard requires any `testid:` object key
    in `ui/*.js` to forward (`opts.testid`, `item.testid`). Prefer setting it with
    `setAttribute('data-testid', opts.testid)` or `dataset`. No comment may contain
    `testid:` at all.
- [x] **AC2 — `App.ui.button(opts)`** returns an `HTMLButtonElement`.
  - **Defaults**: `type="button"`; `variant` (`primary|secondary|ghost|danger`) maps to
    the four existing classes; default `secondary`.
  - **Options**:
    - `size` (`sm|lg|xl`) adds `.btn-sm`/`-lg`/`-xl`;
    - `icon` prepends `util.icon`;
    - `iconOnly: true` adds `.btn-icon` and **throws** unless `ariaLabel` is given;
    - `disabled`, `onClick`, `className`;
    - `testid` sets `data-testid` on the button itself.
  - The label is set with `textContent`, never HTML.
- [x] **AC3 — `App.ui.textInput(opts)` and `App.ui.field(opts)`.**
  - `textInput` returns an `<input class="field-input">` with:
    - `id` (default `uid('in')`) and `name`;
    - `type` (`text|password|search|email|url|number`), `value`, `placeholder`;
    - `disabled`, `required`, `autocomplete`, `onInput`;
    - `testid` on the input.
  - `field({label, labelHidden, control, hint, error, testid})` returns a **controller**
    `{el, control, setError(msg|null), setHint(msg|null)}`. The same controller shape is
    used for every composite.
    - `el` is the `.field-group` wrapper. `testid` goes on the wrapper.
    - `control` must be an element. If it has no `id`, `field` assigns one with `uid`.
    - The `<label for>` is a **direct child** of `.field-group`, since the CSS uses
      `.field-group > label`. `labelHidden: true` adds `.visually-hidden` to the label;
      the label stays in the DOM.
    - A `.field-hint` and/or `.field-error` element, each with an id, is joined into the
      control's `aria-describedby`, hint first, then error. The error element has
      `role="alert"`.
    - When `error` is set, the control gets `aria-invalid="true"` and `.is-invalid`.
  - `setError(null)` **removes** the error element and strips `.is-invalid`,
    `aria-invalid` and the error id from `aria-describedby`; it does not blank the text.
    `setHint(null)` does the same for the hint.
- [x] **AC4 — `App.ui.listPane(opts)`, factory variant, per DD14.**
  - **Structure**: a `<section>` labelled by its `<h2>` title, optional `actions`
    (elements), an optional `filter`, and a `<ul>` of rows.
    - The filter is built with `textInput` and `field`, using `labelHidden: true` (a
      real label, visually hidden).
  - **Items**: `{id, label, meta, href | onSelect, badges[], icon, testid}`. Optional
    `groups` (`{label, items}`) render as one `<ul>` per group, each preceded by a
    caption element whose id the `<ul>` uses for `aria-labelledby`. No caption `<li>`s
    inside a list.
  - **Edge rules**:
    - an item with neither `href` nor `onSelect` **throws** `Error('listPane item <id>:
      href or onSelect required')`;
    - duplicate item ids **throw**;
    - `setSelected(unknownId)` clears the selection, and the first row becomes the tab
      stop.
    - Each rule gets a contract test.
  - **Rows**: `<a href>` when `href` is given, else `<button type="button">`. The
    selected row has `aria-current="page"` and the DD14 selected marker (wash plus inset
    ring). No colour-only information (A31).
  - **Keyboard**: Tab enters at the selected row, else the first row. Up/Down/Home/End
    move by roving tabindex. Enter or click activates (`onSelect(item)`, or follows
    `href`).
  - **Filter**: input narrows rows through `opts.filter.predicate(item, query)`,
    defaulting to a case-insensitive substring match on `label` and `meta`. When nothing
    matches, an empty-state element shows (`opts.emptyText`; a plain `.empty-state` div
    is acceptable until `core-controls` adds `App.ui.emptyState`).
    - If the selected row is filtered out, Tab enters at the first visible row.
    - The selection model keeps the selected id, so clearing the filter restores
      `aria-current` and the tab stop to the selected row. Tested.
  - **Controller**: `{el, setItems(items|groups), setSelected(id), focusSelected(),
    destroy()}`.
  - It installs **no** document-level listener at any time (DD1).
  - Each row's `testid` comes from the item object (DD2 per-item form).

**The comparison (the six criteria)**

- [x] **AC5 — The custom element.** A throwaway `<ui-list-pane>` light-DOM custom element
  with the same feature set as AC4 is written in a test-only JS file and injected with
  `page.add_script_tag`.
  - It may use `class` (it is a throwaway) and `connectedCallback`/`disconnectedCallback`.
  - It registers any document-level listener it would naturally need (e.g. none, or a
    filter shortcut) in `connectedCallback`, and removes it in `disconnectedCallback`.
- [x] **AC6 — Every criterion evaluated for both mechanisms; results in the flight-log
  Decisions entry.**
  1. **Test ids.** Representative call-site snippets for each mechanism (factory:
     `testid:` options including per-item rows; custom element: whatever its natural
     test id form is, attributes or properties) are written to `tmp_path`. Running
     `extract_testids` on them shows which ids the registry guard sees, and whether any
     would need a manual exception. The snippets live in a unit test, so the evidence is
     reproducible.
  2. **Locators**, in both engines via `engine_page`:
     - `get_by_role('link'|'button', name=…)` strict locators resolve single rows;
     - `fill` on the filter narrows rows;
     - `click` and keyboard Enter activate;
     - for the factories, `fill`, `check` (n/a until Leg 4) and `is_disabled` work on
       `button` and `textInput`.
  3. **Resolver.** `assert_controls_labelled_and_described` passes over each mounted
     variant.
  4. **No sinks.** The ui-dir zero-token guard passes on `ui/*.js`.
     `find_markdown_html_sink_tokens` is also run on the custom-element file, and the
     result recorded.
  5. **WebKitGTK.** `scripts/webkitgtk_probe.py` is run against a dev instance (8485,
     scratch data dir, dev mode). After this leg's `index.html` change, restart that
     instance (`make restart` with the same env), since `index.html` is cached per
     process.

     **Extend the probe with `--setup-script PATH`:**
     - `action="append"`, so several scripts run in order;
     - paths are validated as existing files before the WebView is built;
     - a small argparse/validation test goes in `tests/test_webkitgtk_probe_safety.py`.

     **Timing.** Setup scripts run **after** load and the hash route, and **before** the
     root-selector poll. Each is evaluated as a synchronous expression whose completion
     value is JSON-serialisable: wrap it so it ends in `true`, never a DOM node, because
     `to_json` on a node aborts the run.

     **`tests/browser/_probe_mount_ui.js`:**
     - creates `<div id="ui-probe-root">` appended to `body`, outside the app shell, so
       the router does not re-render it;
     - mounts a factory list pane (with filter and groups), a button and a field into it;
     - is run with `--root-selector '#ui-probe-root'`, so legacy shell markup does not
       pollute the result;
     - is also evaluated by a Playwright contract test, so it cannot rot unexercised.

     **The custom element** is probed with two setup scripts in order, its definition
     file then a mount wrapper, **before** the CE file is deleted.

     The probe output (engine version, pinned env, ok) for both mechanisms goes in the
     flight log.
  6. **Cleanup.** In both engines, after `load_harness` and before mounting, wrap
     `EventTarget.prototype.addEventListener` and `removeEventListener` with
     `page.evaluate`, recording registrations on `document`, `window` and `body`:
     - key each by (type, listener, capture);
     - honour `once` and `signal`.

     Then:
     - mount each variant, interact (focus, filter), and wipe the host with
       `host.textContent = ''` **without** calling `destroy()`;
     - assert zero outstanding document-level listeners attributable to the control;
     - dispatch keydown and click on `document`, and assert no handler touched detached
       nodes (via an injected counter).

     **Negative control (required).** A deliberately leaky mock control that registers a
     document listener and never removes it. The instrumentation must report it.

     Record the results for both mechanisms. If both pass, the Decisions entry states
     this criterion is **non-differentiating** (the CE passes via
     `disconnectedCallback`; the factory by installing none) rather than a factory win.
- [x] **AC7 — Decision.** The flight-log Decisions entry "Control-library mechanism"
  states the chosen mechanism and why, citing the evidence table. If factories pass
  all six criteria, the decision is **factories (DD1 confirmed)** and the custom-element
  file and any CE-only test code are **deleted**.
  - If factories fail a criterion that the custom element passes, **stop**. Mark the leg
    `aborted`, keep the evidence, and signal `[BLOCKED:mechanism-divert]` (a flight
    divert criterion). Do not adopt `class` on your own.

**Dialog rule (DD8)**

- [x] **AC8 — Harness.** `tests/browser/_dialog_rule.js` implements the DD8 wrapper
  minimally. It also injects the test's own backdrop rule, in the `var(--token)` form
  (e.g. `dialog::backdrop { background: var(--x-scrim) }` with `--x-scrim` defined on
  `:root`), because DD8's concern is custom-property inheritance into `::backdrop`:
  - `open(dialogEl, {opener, transient})`, with explicit opener and explicit focus on
    open;
  - close-topmost;
  - Escape on `keydown` with `preventDefault()` and `stopPropagation()`;
  - `cancel` prevented and routed through the same path;
  - a `close` listener keeping the stack in sync;
  - backdrop click closes transient dialogs only;
  - focus restored to the recorded opener.

  `_dialog_rule_checks.py` exposes check functions parametrized by an **adapter**:
  - `{name, open(opener_testid, transient), close_topmost(), open_confirm_programmatic(),
    backdrop_css}`;
  - each check reports the layer count it observed, so Flight 2 failures read clearly.

  Flight 2 points the same checks at the real wrapper and its real CSS.
- [x] **AC9 — Checks pass in Chromium and in WebKit**, locally (Leg 1 established WebKit
  route 1):
  - **(a) Stacked dialogs, user-activated.** Both dialogs are opened by **real clicks**,
    each with user activation. A real `page.keyboard.press('Escape')` peels exactly one
    layer, and a second press peels the next.
  - **(b) Programmatic confirm over a modal.** The modal is opened by a click; the
    confirm is then opened by `page.evaluate`, with no user activation between. This is
    the CloseWatcher-grouping case. Each Escape peels exactly one layer.
  - **(c) Focus restore.** Focus returns to the opener after a **mouse** open + Escape,
    and after a **keyboard** open + Escape. Assert
    `document.activeElement === document.querySelector('[data-testid=<opener>]')` via
    `evaluate`.
  - **(d) Backdrop clicks.** A backdrop click closes a transient dialog but not a confirm.
  - **(e) Inertness.** While a modal is open, a button outside it cannot be activated.
    - Click with `page.mouse.click(x, y)` at the outside button's centre, and assert its
      injected click counter did not change.
    - Tab N times, and assert `document.activeElement` stays inside the dialog.
    - **Positive control first**: show Tab does reach the dialog's own buttons in this
      engine. If an engine's Tab does not reach buttons at all, record that and use
      `focus()` plus `elementFromPoint` evidence instead. Never pass vacuously.
  - **(f) Backdrop colour.** Read `getComputedStyle(dlg, '::backdrop').backgroundColor`
    and compare it with the resolved token value. If an engine returns an empty or
    unsupported result, the check reports **"unverifiable"** (pytest `xfail(strict=False)`
    with the engine named is acceptable), never a pass.
    - Also run the same check in WebKitGTK 2.52.6 through the probe, with a setup script
      that opens a harness dialog. Record it.
    - If the probe cannot open a modal (no user activation is needed for `showModal`, so
      it should), record the gap in the flight log.
  - **(g) Body scroll.** In Chromium only, in its own module (it uses the app fixtures,
    not `engine_page`): one spawned `app_clean` app. At each of 1024×768 and 1440×900,
    `page.set_viewport_size` → `goto` → wait for the shell's main region to render → read
    `document.scrollingElement.scrollHeight <= clientHeight`. Measure the default route
    with an empty DB (the getting-started state), and record it.
    - If the shell does scroll `body`, record it as an anomaly; it re-opens DD8's
      scroll-lock note for Flight 2.

**Docs and gates**

- [x] **AC10 — Docs.**
  - `agents.md`: the Modals bullet is rewritten to DD8, and the new "Control library
    (`App.ui`)" section covers the mechanism decision, export idiom, `util` vs factories,
    the cleanup rule, the testid rule, the no-sink and icon rule, and how to add a
    factory (file, `<script>` tag, count bump, demo and inventory, which the reference
    leg makes mandatory).
  - The registry (`docs/ui-testid-registry.md`) changes only if a `static/js` file
    calls a factory with a `testid`. None should in this leg.
- [x] **AC11 — Gates pass:**
  - `make lint`;
  - `make test-unit`, which includes the cache-busting count, the Leg 1 guards (now
    live), `test_js_string_css_var_refs_are_defined` and the token-definition test;
  - `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_library_contract.py tests/browser/test_ui_dialog_rule.py -x -rA`;
  - `--lane shared`;
  - **one other full lane** (`--lane system`), proving the new scripts load without
    breaking an area. Every lane loads `index.html`.

## Verification Steps

- AC1–AC4: read `ui/*.js`; run the contract tests with `-rA` and see both engines'
  params.
- AC5–AC7: the flight-log Decisions entry with the evidence table. Grep for leftover CE
  code:
  `git status --porcelain tests/browser | grep -i spike` shows no leftover
  custom-element file.
- AC8–AC9: run `test_ui_dialog_rule.py` with `-rA`; read `_dialog_rule_checks.py` and
  check the adapter seam.
- AC10: read the doc diffs.
- AC11: run the listed commands; record counts and durations.

## Implementation Guidance

Add each file's `<script>` tag to `index.html`, and bump the cache-busting count, **in
the same step as you create the file**. The disk harness only loads `ui/` scripts that
`index.html` lists, so a file without its tag is invisible to every contract test.

1. **`core.js` first.**
   - `el(tag, attrs, children)` maps attributes as follows:
     - `className` → `className`;
     - `text` → `textContent`;
     - `dataset` → keys;
     - `on*` → `addEventListener`;
     - everything else → `setAttribute`.
   - Use `children` items for nested content: a string becomes a text node, a node is
     appended.
   - `icon` parses `App.icons[name]`. Check `icons.js` for how strings are stored.
2. **Factories**, `button` then `textInput` and `field`. Keep each factory's options
   documented in a JSDoc-style comment, with no quoted test ids in comments (DD2).
3. **List pane.**
   - Bind the roving keyboard on the `<ul>`.
   - Re-render rows with `textContent = ''` plus appends, never inner-HTML.
   - Keep the selected row's tabindex at `0` and the others at `-1`.
4. **The custom element** for comparison. Keep it in a test-support file, inject it per
   test, and delete it at the end.
5. **Compare and decide**, before any docs and before deleting anything:
   - run the six-criteria comparison in both engines, including the probe runs for both
     mechanisms;
   - write the Decisions entry with the evidence table (engine version per row);
   - evaluate AC7's stop condition. If it triggers, stop here with
     `[BLOCKED:mechanism-divert]`;
   - otherwise delete the CE file and any CE-only test code. Unit-test snippets in
     `tests/test_ui_mechanism_testids.py` may stay as snippets only.
6. **Dialog harness and checks.**
   - Write the checks against an adapter interface first, so Flight 2 reuses them.
   - Use real keyboard presses (`page.keyboard.press`) and real mouse clicks (`.click()`)
     for the opener-focus checks. In WebKit a mouse click does not focus a button, which
     is exactly what (c) tests.
7. **Docs**, then the **gates** (AC10, AC11). Contract tests assert classes for
   `.btn-icon`, not geometry; its CSS arrives in Leg 3.

## Edge Cases

- **`App.icon` vs `App.ui.util.icon`.** The existing `App.icon` returns a string and has
  46 call sites. Do not change it. `util.icon` is new and returns a node.
- **`uid` collisions** with existing static ids: prefix generated ids, e.g. `ui-in-1`.
- **A `listPane` item with neither `href` nor `onSelect`** renders a `<button>`, which is
  inert but focusable. Prefer to throw a clear error in development. Pick one and test
  it.
- **Filter + selection.** The selected row filtered out leaves no tabbable row. Tab
  then enters at the first visible row. Test this.
- **WebKit runs locally.** Leg 1 established route 1: WebKit 26.0 via
  `scripts/setup-webkit-userland.sh` and the `webkit-wrapper.sh` executable path. Every
  `[webkit]` param must therefore **run** in this leg; none may skip. If WebKit stops
  launching (e.g. the userland cache is missing), re-run the setup script rather than
  accepting skips. Record the engine versions in the flight log.

## Files Affected

- `the_one/interfaces/web/static/js/ui/core.js`, `button.js`, `field.js`, `list-pane.js`:
  new.
- `the_one/interfaces/web/static/css/components.css`, or a new flat CSS file: list-pane
  styles.
- `the_one/interfaces/web/static/index.html`: script and possibly link tags.
- `tests/test_index_asset_cache_busting.py`: the count.
- `tests/browser/test_ui_library_contract.py`, `test_ui_mechanism_spike.py` (kept or
  folded), `_dialog_rule.js`, `_dialog_rule_checks.py`, `test_ui_dialog_rule.py`, and
  `_probe_mount_ui.js`: new.
- `tests/test_ui_mechanism_testids.py` (or a section in `test_ui_guards.py`): the
  criterion-1 extractor evidence.
- `scripts/webkitgtk_probe.py`: `--setup-script`, if not already present.
- `the_one/agents.md`
- `missions/25-workbench-navigation/flights/01-control-library-foundation/flight-log.md`

## Citation Audit

Checked at leg design against the flight branch:
- `index.html`: `icons.js` precedes `markdown.js` in the body script list ✔
- `test_index_asset_cache_busting.py:59` count 55 ✔
- `knowledge-section.js` `_appendIcon` around line 163 ✔ (survey)
- `agents.md:1666` Modals bullet ✔
- Leg 1 output names are as specified in Leg 1's ACs. **Re-check them against Leg 1's
  flight-log entry before implementing.**

Design review (Developer, 2026-09-30) — "approve with changes". Applied:
- the script tags move with each file's creation, and an explicit compare-and-decide
  step was added;
- AC9 (a) and (b) are made distinct; (e) gets positive controls and real coordinate
  clicks; (f) defines its CSS under test and an "unverifiable" outcome; (g) is
  specified;
- the probe `--setup-script` contract;
- the cleanup criterion's negative control and its non-differentiating note;
- `rovingFocus` is event-time, Arrow/Home/End only, clamped by default, and never
  touches Enter;
- the export idiom and the testid and comment rules inside `ui/`;
- `uid` emits `ui-<prefix>-<n>`; `icon` validates its input and output;
- list-pane group markup, the hidden filter label, and the edge rules
  (throw/throw/clear);
- `field` returns a controller and `setError(null)` removes its wiring.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.
