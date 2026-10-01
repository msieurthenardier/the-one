# Leg: core-controls

**Status**: completed
**Flight**: [Control Library Foundation](../flight.md)

## Objective

Complete the core control set on the settled mechanism, which is factories (DD1,
confirmed in Leg 2):
- **New controls:** `textarea`, `select`, `checkbox`, `toggle`, `badge` and
  `emptyState`.
- **Hardened:** `field` and `listPane`.

Every control is keyboard-operable with visible focus, wired for accessible names and
descriptions, and proven by contract tests in Chromium and WebKit and by the WebKitGTK
probe. The menu is a separate leg (`menu-control`).

## Context

- **Flight decisions:** DD1 (factories, cleanup rule), DD2 (testid rule), DD3 (resolver
  per control), DD4 (no sinks), DD5 (layout, export idiom, `ui-` classes, reuse of
  existing vocabulary), DD14 (list pane), and DD15 rows A8, A9, A10, A24 (selected-row
  meta contrast) and A31.
- **Read first:** `the_one/agents.md` "Control library (`App.ui`)" (Leg 2), and the Leg
  2 and Leg 3 flight-log entries.
- **Start only after Leg 3 (`deep-violet-tokens`) has landed.** Leg 3 owns the
  `.checkbox-primary` block, the `--control-*` tokens and the a11y test file, which this
  leg also edits. Re-read those files immediately before editing them.
- **Already shipped by Leg 2** (`ui/list-pane.js`), so not repeated here:
  - the `density` option (`.ui-list-pane-compact`);
  - leading `icon`;
  - `badges` rendered as muted spans (`.ui-list-pane-badge`);
  - the empty element (`class="empty-state ui-list-pane-empty" role="status"`);
  - contract tests including density (`test_ui_library_contract.py` around line 598).
- **Vocabulary to reuse** (DD5):
  - `.field-input`; `.field-textarea` (`components.css:183`); `.field-select`
    (`components.css:208`; markup uses `class="field-input field-select"`)
  - `.checkbox-primary`
  - `.badge` + `.badge--<kind>`, where the 14 kinds are `anthropic`, `anthropic-plan`,
    `approved`, `connectors`, `dismissed`, `execution`, `filesystem`, `mock`, `ollama`,
    `openai`, `openai-compatible`, `openrouter`, `unknown` and `web`. Their inks are
    already gated by `test_badge_ink_passes_body_aa`.
  - `.empty-state` (`components.css:632`); `.empty-canvas`, `.empty-canvas-inner` and
    `.empty-canvas-cta` (`:643-666`)
  - New library-only classes are `ui-`-prefixed.
- **Toggle colours** come from Leg 3's tokens:
  - off: track `--control-border`, thumb `--control-thumb`
  - on: track `--accent-fill`, thumb `--control-thumb`
  - focus: the standard `--accent` ring

  The legacy toggles (`.tool-enable-switch`, `.tool-switch`) are **not** migrated
  (DD13).
- **Contrast premise (design review, computed).** Ratios on the selected-row wash
  (`--accent-translucent` over `bg` and `surface`):

  | Theme | Base | `--fg-muted` | `--fg-secondary` |
  |---|---|---|---|
  | Dark | `bg` | 4.61 | 6.57 |
  | Dark | `surface` | **4.27** | 6.09 |
  | Light | `bg` | **4.43** | 6.79 |
  | Light | `surface` | **4.25** | 6.51 |

  `--fg-muted` fails in three of four cases, so selected rows use `--fg-secondary` for
  meta, badges and counts.
- **Scope fence.** No area module is changed to use these controls. The reference page
  (`living-reference-and-inventory`) is the first consumer.

## Inputs

- `the_one/interfaces/web/static/js/ui/*.js` and `css/components.css` as left by Legs
  2–3.
- `tests/browser/_ui_engines.py`: `engine_page` and `load_harness(page, theme)`. The
  harness reads `index.html`, so new `ui/` files are picked up once their tags exist.
- `tests/browser/_a11y_resolvers.py`.
- `tests/test_ui_library_source.py`: the ES5, idiom and no-app-globals guard over
  `js/ui/`. Confirm it globs the directory rather than listing files.
- `tests/test_design_tokens_a11y.py`: `_alpha_composite`, `_ACCENT_TRANSLUCENT_ALPHA`,
  the usage-pin pattern, and `test_badge_ink_passes_body_aa`.
- `areas/admin/design-language/fields-section.js::checkboxLabel` (around line 154):
  today's checkbox-with-label markup. Reference only.
- `the_one/interfaces/web/static/index.html` and `tests/test_index_asset_cache_busting.py`
  (59 after Leg 2).

## Outputs

**Factories**

| Factory | File |
|---|---|
| `App.ui.textarea`, `App.ui.select` | `ui/field.js` |
| `App.ui.checkbox`, `App.ui.toggle` | new `ui/choice.js` |
| `App.ui.badge`, `App.ui.emptyState` | new `ui/feedback.js` |

**Load order:** a `<script>` tag for each new file goes after `list-pane.js` and before
`markdown.js`, added in the same step as the file. The cache-busting count goes
**59 → 61**. These factories are used at call time, not load time, so their position
after `list-pane.js` is safe.

**CSS** in `components.css` `@layer components`:
- `.checkbox-primary:indeterminate` (a dash, using the same gated pair as the tick) and
  `.checkbox-primary:disabled`;
- `.ui-checkbox*` and `.ui-toggle*`;
- the empty-state title class (`.ui-empty-title`);
- the selected-row meta, badge and count colour.

**Hardened factories:**
- `field`: verified around `textarea` and `select`. It throws for the checkbox and
  toggle factories' controls.
- `listPane`: changes only these things:
  - its empty element is built by `App.ui.emptyState`;
  - its `badges` render through `App.ui.badge` when a `kind` is given;
  - it gains a `count` option per row;
  - selected-row meta, badges and counts use `--fg-secondary`.

**Tests:**
- Engine-parametrized contract tests for every new and hardened factory. Each is in a
  `tests/browser/test_ui_*.py` file in the `shared` lane, extending
  `test_ui_library_contract.py` or in family files such as
  `test_ui_choice_contract.py`.
- `tests/test_design_tokens_a11y.py`: the selected-row meta composite gate with its
  usage pin, an indeterminate-dash usage pin, and the empty-state text pair (if not
  already covered).
- A unit test pinning `App.ui.badge`'s kind list against the `.badge--*` selectors in
  `static/css/*.css`.
- `tests/browser/_probe_mount_ui.js`: mounts every factory from this leg.

**Docs:** `the_one/agents.md` "Control library" documents every factory added or
changed here.

**Flight log:** the leg entry, including the probe JSON summary per theme.

## Acceptance Criteria

Each factory occupies one `App.ui.<name> = function (opts) {` line, is ES5, and has no
sink tokens and no app globals. `testid` is forwarded to the **native** control unless
stated otherwise.

- [x] **AC1 — `App.ui.textarea(opts)`** returns `<textarea class="field-input field-textarea">`.
  - Options: `id` (default `uid('ta')`), `name`, `value`, `placeholder`, `rows`
    (default 4), `disabled`, `required`, `onInput`, `testid`.
  - Playwright `fill` works in both engines.
- [x] **AC2 — `App.ui.select(opts)`** returns `<select class="field-input field-select">`.
  - Options: `id`, `name`, `options` (`{value, label, disabled}`, or groups
    `{label, options}` → `<optgroup>`), `value`, `disabled`, `required`, `onChange`,
    `testid`. Labels are set via `textContent`.
  - It throws on an empty `options`, and on a `value` that is not among them.
  - `select_option` works in both engines.
- [x] **AC3 — `App.ui.checkbox(opts)`** returns a controller `{el, control,
  setChecked(bool), setIndeterminate(bool)}`.
  - **Structure.** `el` is `<div class="ui-checkbox">`. It contains a
    `<label class="ui-checkbox-label">` wrapping
    `<input type="checkbox" class="checkbox-primary">` and a text `<span>`, so the label
    text is the click target and the accessible name.
  - **Hint.** An optional `.field-hint` is a **sibling** after the label (never inside
    it), with an id wired via the input's `aria-describedby`. The name therefore stays
    clean.
  - **Options:** `id`, `label`, `checked`, `indeterminate` (set via the property),
    `disabled`, `hint`, `onChange(checked)`, `testid` (on the input).
  - **State.** `setChecked` clears indeterminate.
  - **CSS:**
    - `.checkbox-primary:indeterminate` shows a dash drawn with the same gated
      fill and ink pair as `:checked` (`--accent-fill`, `--fg-on-accent-fill`);
    - `.checkbox-primary:disabled` uses opacity .4 and `cursor: not-allowed`;
    - `.ui-checkbox-label` is `inline-flex`, with `align-items: center`, a gap and a
      pointer cursor;
    - `.ui-checkbox-label:hover .checkbox-primary` gives the hover border.
  - **Playwright.** `check`/`uncheck`, `get_by_role('checkbox', name=label)` (exact
    name, no hint text) and `is_disabled` all work in both engines.
- [x] **AC4 — `App.ui.toggle(opts)`** returns a controller `{el, control,
  setChecked(bool)}`. It is on/off only, with no indeterminate state.
  - **Structure.** `el` is `<div class="ui-toggle">`. It contains a
    `<label class="ui-toggle-label">` wrapping three parts:
    - `<input type="checkbox" role="switch" class="ui-toggle-input">`, visually hidden
      with the clip/1px technique (**not** `display:none`, **not** `opacity:0` alone),
      so it stays focusable and role-reachable;
    - a decorative `<span class="ui-toggle-track" aria-hidden="true">` (its thumb is
      `::after`);
    - a text `<span>`, visually hidden when `labelHidden: true` but still the accessible
      name.

    An optional `.field-hint` is a sibling, wired via `aria-describedby`.
  - **Colours** use the Leg 3 tokens:
    - off: `--control-border` track, `--control-thumb` thumb
    - on: `--accent-fill` track, `--control-thumb` thumb
  - **Motion.** The thumb transition uses the motion tokens, which collapse under
    `prefers-reduced-motion`.
  - **Focus.** `.ui-toggle-input:focus-visible + .ui-toggle-track` draws the standard
    `--accent` ring.
  - **Disabled.** Opacity .4 and `cursor: not-allowed`; Space does nothing.
  - **Playwright.** `get_by_role('switch', name=label)` resolves in both engines;
    Space and click toggle it.
  - **Usage pin.** The `.ui-toggle*` rules consume exactly the gated pairs.
- [x] **AC5 — `App.ui.badge(opts)`** returns `<span class="badge badge--<kind>">`, with
  `text` set via `textContent`.
  - Options: `text`, `kind`, `title`, `testid` (on the span).
  - It throws on an unknown `kind` or a missing `text`.
  - The kind list is exposed as `App.ui.badge.KINDS`, a property assignment, not a
    factory line.
  - A unit test asserts `KINDS` equals the set of `.badge--<kind>` selectors in
    `static/css/*.css`.
- [x] **AC6 — `App.ui.emptyState(opts)`.**
  - **Options:** `title`, `body`, `action` (element), `icon` (name), `headingLevel`
    (default 3), `size: 'inline'|'pane'` (default `inline`), `role` (default none;
    `listPane` passes `'status'`), `testid` (on the root).
  - **Inline structure.** `<div class="empty-state">`, containing:
    - an optional icon (`util.icon`, `aria-hidden`);
    - `<h{n} class="ui-empty-title">` (new CSS: body size, medium weight, `--fg`, no
      margin);
    - an optional `<p>` body;
    - an optional action.
  - **Pane structure.** `<div class="empty-canvas"><div class="empty-canvas-inner">…`,
    with the same children. The action carries the `.empty-canvas-cta` class.
  - **Contrast.** The body text colour and its background are a gated pair. Confirm the
    existing body ladder covers it, or add a gate.
- [x] **AC7 — `field` around every control.**
  - `field({control: textarea | select, label, hint, error})` wires `label[for]`, the
    hint and error ids, `aria-describedby` (hint, then error) and `aria-invalid`.
    Proven by the resolver and by explicit assertions in both engines.
  - The checkbox and toggle factories mark their input with `data-ui-own-label="true"`.
    `field` **throws** `Error('field: checkbox/toggle carry their own label')` when
    given such a control. A bare `<input type=checkbox>` without the marker is
    accepted.
  - Tests cover the throw and both accepted cases.
- [x] **AC8 — `listPane` hardening.** Only these changes:
  - **Empty element.** It is built with `App.ui.emptyState({…, role: 'status'})`,
    keeping the `ui-list-pane-empty` class and its `hidden` toggling. Existing contract
    tests still pass.
  - **Badges.** An item's `badges` entries with a `kind` render via `App.ui.badge`.
    Entries without a `kind` keep today's neutral span.
  - **Counts.** A row `count` renders as trailing text, with no colour-only meaning
    (A31).
  - **Selected-row colour.** On a selected row (`[aria-current="page"]`), meta, neutral
    badges and counts use `--fg-secondary`.
  - **Gates.**
    - A new composite gate: `fg_secondary` on `_alpha_composite(accent, alpha, base)`,
      for base ∈ {`bg`, `surface`}, both themes, ≥ 4.5.
    - A usage pin asserting the selected-row rule (selector anchored on
      `[aria-current="page"]`) sets `--fg-secondary` for those elements.
  - **Regular density.** A computed-style assertion for `regular` density is added:
    padding `8px 10px` and a 2px gap. Compact is already tested.

**Behaviour proofs** (both engines; every `[webkit]` param runs, none skipped)

- [x] **AC9 — Contract tests per factory** cover:
  - construction;
  - the testid on the right element;
  - Playwright native actions (`fill`, `select_option`, `check`, `click`, `press`);
  - disabled state (`is_disabled`; no `onChange` fires);
  - hint and error wiring through `field`;
  - `assert_controls_labelled_and_described` passing over a mount of every factory from
    this leg together.
- [x] **AC10 — Keyboard and visible focus.**
  - Each interactive factory here (`textarea`, `select`, `checkbox`, `toggle`) is
    reached by a **real Tab**, with a positive control that Tab moves focus in that
    engine. It is then asserted `el.matches(':focus-visible')`.
  - The computed indicator must be non-empty. Read `outline-style` (≠ `none`) and
    `outline-width` (≥ 2px). For the toggle, read the track's `box-shadow` or
    `outline`, since the input is visually hidden.
  - Focus-visible is never asserted after a pointer interaction.
- [x] **AC11 — WebKitGTK.** `_probe_mount_ui.js` mounts one of every factory from Legs
  2 and 4, including a checkbox in all three states, a toggle in both states, a badge
  of each of two kinds, and both empty-state sizes.
  - The probe runs against a dev instance (8485, scratch data dir, dev mode;
    `make restart` after `index.html` changes) with `--root-selector '#ui-probe-root'`,
    in **dark and light**.
  - Both runs are `ok: true`.
  - The flight log records control count and engine version.

**Docs and gates**

- [x] **AC12 — Docs.** `agents.md` "Control library" documents each factory added or
  changed here: options, return shape, keyboard behaviour, testid placement and the
  classes used. The "Adding a factory" bullet stays accurate.
- [x] **AC13 — Gates pass:**
  - `make lint`;
  - `make test-unit` (static guards, token, a11y, the cache-busting count and the badge
    kind pin);
  - every `tests/browser/test_ui_*.py` file plus `test_deep_violet_computed_styles.py`,
    with `-m browser -rA` and no skips;
  - `--lane shared`.

  The flight log records counts.

## Verification Steps

- AC1–AC8: read `ui/*.js` and the CSS. Run
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_*.py -x -rA`.
  Every test shows passing `[chromium]` and `[webkit]` params.
- AC8 (contrast), plus the AC3/AC4 pins:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_design_tokens_a11y.py -x`.
- AC11: the probe JSON in the flight log, for both themes.
- AC12: read the docs.
- AC13: run the listed commands.

## Implementation Guidance

1. **`textarea` and `select`** (in `field.js`, no new tag), then `feedback.js` (`badge`,
   `emptyState`, plus its tag and the count bump to 60). Add the badge kind pin test.
2. **`choice.js`** (`checkbox` and `toggle`, plus its tag and the count bump to 61),
   then the CSS. Re-read `components.css` first, since Leg 3 just changed the checkbox
   block. Append the new blocks; edit `.checkbox-primary` only to add
   `:indeterminate` and `:disabled`.
3. **`field` hardening** (AC7).
4. **`listPane` hardening** (AC8), then its gate and pin. Re-read
   `test_design_tokens_a11y.py` first.
5. **Contract tests** (AC9, AC10).
6. **Probe mount and runs** (AC11), **docs** (AC12), **gates** (AC13).

## Edge Cases

- **`checkbox` with `indeterminate: true` and `checked: true`.** Indeterminate wins
  visually until `setChecked` is called. Test it.
- **`toggle` clicked on the track.** The click hits the label, so the toggle flips.
- **`toggle` clicked on the hint.** The hint is outside the label, so nothing happens.
- **`emptyState` with `action` and `size: 'pane'`.** The action gets `.empty-canvas-cta`
  added, and its own classes are preserved.
- **`select` options containing `&`, `<` or `>`.** They render literally (`textContent`).
  Test one.
- **WebKit Tab** may land differently from Chromium (Leg 2 finding). Always pair a Tab
  assertion with a positive control.

## Files Affected

- `the_one/interfaces/web/static/js/ui/field.js`, `list-pane.js`: extended or hardened.
- `the_one/interfaces/web/static/js/ui/choice.js`, `feedback.js`: new.
- `the_one/interfaces/web/static/css/components.css`
- `the_one/interfaces/web/static/index.html`, `tests/test_index_asset_cache_busting.py`
- `tests/browser/test_ui_*.py`, `tests/browser/_probe_mount_ui.js`
- `tests/test_design_tokens_a11y.py`; a badge kind pin, either in a new
  `tests/test_ui_badge_kinds.py` or in `test_ui_library_source.py`
- `the_one/agents.md`
- `missions/25-workbench-navigation/flights/01-control-library-foundation/flight-log.md`

## Citation Audit

Checked at leg design (2026-09-30) against the tree after Leg 2 landed:
- `ui/core.js:96` `rovingFocus` (supports `wrap`, Home/End, event-time items) ✔
- `ui/field.js:17,45` ✔
- `ui/list-pane.js:64` (density, icon and badges already present) ✔
- `components.css:183/208/632/643-666` ✔
- `.checkbox-primary` has no `:indeterminate` or `:disabled` rule (grep) ✔
- Badge modifiers: 14 kinds ✔

Design review (Developer, 2026-09-30) — "approve with changes". Applied:
- The leg is split: the menu moves to `menu-control`.
- The AC8 contrast premise is corrected (`--fg-secondary` on selected rows, both
  themes, badges and counts too), and AC8 is reduced to what is genuinely new.
- Checkbox and toggle hints are siblings, not inside the label.
- Indeterminate and disabled checkbox CSS is added.
- `field`'s throw is keyed on a factory marker.
- `emptyState` gains `role`, a size structure and a title class.
- The badge kind pin is added.
- Focus-visible is never asserted after a pointer interaction.
- The count target is stated.
- The leg starts only after Leg 3 lands.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.
