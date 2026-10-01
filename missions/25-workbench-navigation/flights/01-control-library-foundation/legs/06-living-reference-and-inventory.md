# Leg: living-reference-and-inventory

**Status**: completed
**Flight**: [Control Library Foundation](../flight.md)

## Objective

- Rebuild the dev-mode Design language page as the control library's living reference.
  Every `App.ui` factory is demonstrated through the library itself, side by side in
  dark and light.
- Write the app-wide control inventory.
- Add the guards that keep both complete.
- Finish the control-library documentation.
- Run the flight-close verification.

## Context

- **Flight decisions:** DD10 (living reference: nested theme wrappers, `data-ui-demo`
  roots, generated ids, the fate of each existing section), DD11 (inventory and its
  guards), DD13 (scope fence) and DD5 (the export idiom the guards parse). DD3 also
  applies: the resolver runs over every `[data-ui-demo]` root.
- **Library state after Legs 2–4:** `the_one/agents.md` "Control library (`App.ui`)" is
  the API reference, and the factories live in `static/js/ui/*.js`. Read the Leg 4
  and Leg 5 (`menu-control`) flight-log entries for the final factory list.
- **Page structure today:**
  - `areas/admin/design-language-page.js` builds the page with an HTML-string header
    and a `SECTIONS` list.
  - Each section is a module `App.admin.designLanguage.<slug>Section.render(host)` in
    `areas/admin/design-language/<slug>-section.js`.
  - Each module is loaded by its own `<script>` tag (`index.html` lines 71-80).
  - The page is dev-mode-only (`areas/admin.js:88-91`).
  - No test references a design-language `data-section` today, so slugs may change
    freely.
- **The fate of each existing section (DD10):**

  | Section | Fate |
  |---|---|
  | `tokens`, `typography`, `status`, `tabs`, `markdown` | stay (`tokens` already shows the Leg 3 tokens) |
  | `buttons`, `fields` | **replaced** by library sections |
  | `surfaces` | its local `toggleSwitch` demo is removed (the library toggle supersedes it); tiles, list rows, section nav and picker miniatures stay until Flights 2–3 retire them |
  | `modal` | keeps its live `App.confirmDialog` demo until Flight 2's migration |

- **Inventory scope (DD11).** It covers every control kind in the app, not only library
  ones. The flight survey in the flight log's planning notes is a starting point, not a
  substitute for reading the code. The M17 lesson applies: grep counts run high, so
  classify each control by reading its render site.
- **Deferred items** to record in the inventory as known debt:
  - the `.area-studio .tool-toggle { display:none }` keyboard debt (`studio.css:64`);
  - the two legacy toggles;
  - the per-editor `_el`/`_btn`/`_fieldGroup` copies;
  - `App.confirmDialog` (moves to DD8 in Flight 2);
  - `buildItemMenu` (superseded by `App.ui.menu`; migrates with the KB editor
    internals next mission);
  - squawk 0094 (KB attach toggle not reachable by role).

## Inputs

- `the_one/interfaces/web/static/js/areas/admin/design-language-page.js` and
  `design-language/*.js`.
- `the_one/interfaces/web/static/index.html` (design-language script tags at lines
  71-80) and `tests/test_index_asset_cache_busting.py`.
- `the_one/interfaces/web/static/js/ui/*.js`, the factories (one
  `App.ui.<name> = function` line each, per DD5).
- `tests/browser/_a11y_resolvers.py`, `scripts/webkitgtk_probe.py` and
  `tests/browser/_ui_engines.py`.
- `tests/test_ui_guards.py`: `DYNAMIC_SINK_BASELINE`. Removing the page's sink sites is
  allowed; removals never fail.
- `docs/ui-testid-registry.md`.
- The flight survey of control helpers. Sources: the flight-log planning notes, and the
  "How controls are built today" survey summarised in the flight Context and DD11.

## Outputs

- **`design-language-page.js`:** rebuilt with `App.ui.util.el`, with no HTML-string
  sink. The page header uses the existing `.page-header`/`.page-title` vocabulary. The
  `SECTIONS` list is updated.
- **New library sections** under `areas/admin/design-language/`, one per family, each
  built only with `App.ui` factories and `util.el`:

  | File | Demonstrates |
  |---|---|
  | `ui-buttons-section.js` | `button`: every variant × size, icon, icon-only, disabled |
  | `ui-fields-section.js` | `textInput`, `textarea`, `select`, `field` with hint and with error, disabled |
  | `ui-choices-section.js` | `checkbox` (unchecked, checked, indeterminate, disabled) and `toggle` (off, on, disabled) |
  | `ui-feedback-section.js` | `badge` (every kind) and `emptyState` (with and without action) |
  | `ui-lists-section.js` | `listPane`: groups, selection, filter, badges, density regular and compact, empty |
  | `ui-menus-section.js` | `menu`: trigger variants, danger and disabled items |

  - Each demo root is `[data-ui-demo="<factoryName>"]` containing a
    `[data-theme="dark"]` and a `[data-theme="light"]` pane. Each pane sets its own
    `color: var(--fg); background: var(--bg)`. Demos use generated ids and pass no
    `testid`, except where a guard test needs a handle, which would then be registered.
- **Removed:** `buttons-section.js` and `fields-section.js`, and their `<script>` tags.
  The `surfaces` toggle demo is removed. `<script>` tags are added for the new section
  files, and the cache-busting count is adjusted to match.
- **`docs/ui-control-inventory.md`** (new): one table per control family. Each row
  gives:
  - the control;
  - where it is built today (file and helper);
  - status: `library: App.ui.<factory>` or `not yet defined`;
  - the owning surface and the expected migration (flight or mission) for undefined
    controls;
  - known a11y or keyboard debt.

  A header explains the guard and how to update the doc.
- **Guards:**
  - **Unit:** `tests/test_ui_control_inventory.py` extracts every `App.ui.<name> =
    function` from `static/js/ui/*.js` (excluding `App.ui.util.*`) and asserts each
    `<name>` appears in the inventory as `App.ui.<name>`. It also asserts the reverse:
    every `App.ui.<name>` the inventory cites exists.
  - **Browser** (`tests/browser/test_ui_reference_page.py`, `shared` lane, Chromium on
    the spawned app with dev mode): on `#admin/design-language`, every factory has a
    `[data-ui-demo]` root with both theme panes. `assert_controls_labelled_and_described`
    passes over every `[data-ui-demo]` root. The dark pane's computed `background-color`
    equals the dark `--bg`; the light pane's equals the light `--bg`.
- **Docs:**
  - `the_one/agents.md`: the "Control library" section is finalised. It covers the
    living reference, the inventory and its guards, and makes "Adding a factory"
    mandatory: demo, inventory row and contract tests. The Design language section's
    pointer to the gallery is updated.
  - `CLAUDE.md`: a ≤6-line "Control library" pointer under Architecture or Conventions,
    the always-loaded orientation.
- **Flight log:** the leg entry, plus the **flight-close verification** results.

## Acceptance Criteria

- [x] **AC1 — Page rebuilt.**
  - `design-language-page.js` contains no inner-HTML sink. Its `DYNAMIC_SINK_BASELINE`
    entries are removed, and the baseline test still passes.
  - The page renders all sections in this order: tokens, typography, the six library
    sections, surfaces, status, tabs, modal, markdown.
  - It stays dev-mode-only.
- [x] **AC2 — Every factory demonstrated.** Every `App.ui.<name>` factory has exactly
  one `[data-ui-demo="<name>"]` root on the page, with a dark and a light pane. Each pane
  shows the variants and states listed in Outputs. Demos are built only through `App.ui`
  factories and `App.ui.util.el`. A source check in the unit tier asserts the new
  section files contain no `document.createElement('button'|'input'|'select'|'textarea')`
  and no `className = 'btn-`.
- [x] **AC3 — Superseded sections removed.**
  - `buttons-section.js` and `fields-section.js` are deleted, along with their
    `<script>` tags.
  - The `surfaces` local toggle demo and its helper are removed.
  - `modal`, `tokens`, `typography`, `status`, `tabs` and `markdown` are unchanged
    except as needed to fit the rebuilt page.
  - The cache-busting count is updated and the test passes.
- [x] **AC4 — Reference-page browser guard.** `tests/browser/test_ui_reference_page.py`
  passes in Chromium on the spawned app (`app_clean` with dev mode, `page`). It asserts:
  - (a) every factory name extracted from `ui/*.js` has a `[data-ui-demo]` root;
  - (b) each root has both theme panes, whose computed `background-color` matches the
    mirror's `bg` for its theme;
  - (c) the shared resolver passes over every `[data-ui-demo]` root;
  - (d) the menu demo opens and closes by keyboard on the page, as an in-app smoke for
    the most stateful control.
- [x] **AC5 — Inventory.** `docs/ui-control-inventory.md` exists and classifies every
  control kind in the app. At minimum it covers:
  - button variants and modifiers; text inputs; textareas; selects; checkboxes; both
    legacy toggles plus the library toggle;
  - chips and chip lists; tabs; section nav; list rows and tiles (entity tiles,
    category tiles); menus; modals and dialogs (`App.confirmDialog`); the two-step
    confirm (`App.confirmDelete`);
  - flashes (`App.showFlash`); badges; empty states (`.empty-state`, `.empty-canvas`);
    LEDs and status lines; the info-icon button; key-value tables (`renderKvTable`);
    the chat composer; message bubbles' controls; the theme switcher;
  - the provider model picker and the pull-model control; the telemetry overlay; the
    KB item menu.

  Every row is either `library: App.ui.<factory>` or `not yet defined` with an owning
  surface and expected migration. The known debt listed in Context is recorded.
- [x] **AC6 — Inventory guard.** `tests/test_ui_control_inventory.py` (unit tier)
  enforces both directions between the `ui/*.js` factory exports and the inventory's
  `App.ui.<name>` citations. A `tmp_path` probe shows it fails on a missing row and on a
  stale citation.
- [x] **AC7 — Docs.**
  - `the_one/agents.md` "Control library" is final. It covers the API reference, cleanup
    rule, testid rule, no-sink rule, living reference, inventory, the guard list, and
    the mandatory "Adding a factory" checklist.
  - `CLAUDE.md` has a ≤6-line pointer.
  - The testid registry is updated only if a `testid` was added.
- [x] **AC8 — Flight-close verification.** Run and record in the flight log (counts and
  durations):
  - (a) `make lint`;
  - (b) `make test-unit`;
  - (c) every `tests/browser/test_ui_*.py` and `test_deep_violet_computed_styles.py`
    with `-m browser -rA`, with every `[webkit]` param run;
  - (d) all four lanes, **one at a time**: `--lane chat`, `--lane studio`,
    `--lane system`, `--lane shared` (`TEST_TIMEOUT=1800`). Rerun a failure alone
    before calling it a regression;
  - (e) `scripts/webkitgtk_probe.py` against a dev instance (8485, scratch data dir, dev
    mode, `make restart` after `index.html` changes) at
    `#admin/design-language` with `--root-selector '[data-ui-demo]'`, in **dark and
    light**. Both must be `ok: true`. Stop the instance and remove the scratch directory
    afterwards.

  Any failure that is not a rerun-confirmed flake is fixed in this leg if it is in the
  flight's diff, or raised as an anomaly.

## Verification Steps

- AC1–AC3: read the page and section files;
  `git diff --stat the_one/interfaces/web/static/index.html`; run
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_index_asset_cache_busting.py tests/test_ui_control_inventory.py -x`.
- AC4: `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_reference_page.py -x -rA`.
- AC5–AC6: read the inventory; run its guard and probes.
- AC7: read the docs.
- AC8: the flight-log record.

## Implementation Guidance

1. **Page shell.** Rebuild `design-language-page.js` with `App.ui.util.el`. Note that
   `ui/core.js` loads before the admin modules, so `App.ui` is available. Keep each
   section's `<section class="design-language-section" data-section="<slug>">` shape.
2. **A demo helper.** Write a small shared one, for example in the first new section
   file or a `design-language/ui-demo.js` with its own script tag:
   `demo(host, factoryName, buildFn)`. It creates the `[data-ui-demo]` root and two
   themed panes, and calls `buildFn(pane, theme)` for each. Build each demo twice, so ids
   come from `uid` and no ids or testids are duplicated.
3. **Library sections.** One file per family. Keep captions small (the existing
   `caption()` pattern in `buttons-section.js` is fine to carry over before deleting
   that file).
4. **Remove superseded sections and tags.** Update the count.
5. **Inventory.** Read the render sites. Use the survey as a map, not as truth.
6. **Guards.** Write the unit guard and the reference-page guard.
7. **Docs.**
8. **Flight-close verification (AC8).** Lanes run one at a time. Allow roughly 15–25
   minutes for the full lane set.

## Edge Cases

- **The `listPane` demo with a filter.** Its filter input needs a hidden label (the
  library handles it). The resolver must pass.
- **The `menu` demo** must not leave a document listener installed when the operator
  navigates away while it is open (the cleanup rule). AC4(d) closes it.
- **The `badge` demo for every kind.** The kind list is taken from the library's own
  allowed list, so demo and library cannot drift. Expose it as `App.ui.badge.KINDS`, or
  a similar non-factory property. The guard's regex matches only
  `App.ui.<name> = function`, so a property assignment like `App.ui.badge.KINDS = [...]`
  is fine.
- **Dev mode off.** The page is not routable, and the browser guard must spawn the app
  with dev mode. The `app_clean` fixture already sets `THE_ONE_DEV_MODE=true`.

## Files Affected

- `the_one/interfaces/web/static/js/areas/admin/design-language-page.js`: rebuilt.
- `the_one/interfaces/web/static/js/areas/admin/design-language/ui-*-section.js` (new);
  `buttons-section.js` and `fields-section.js` (deleted); `surfaces-section.js` (toggle
  demo removed).
- `the_one/interfaces/web/static/js/ui/feedback.js`: `badge` kinds exposed, if needed.
- `the_one/interfaces/web/static/index.html`, `tests/test_index_asset_cache_busting.py`.
- `tests/test_ui_guards.py`: baseline entries removed.
- `docs/ui-control-inventory.md` (new), `tests/test_ui_control_inventory.py` (new),
  `tests/browser/test_ui_reference_page.py` (new).
- `the_one/agents.md`, `CLAUDE.md`
- `missions/25-workbench-navigation/flights/01-control-library-foundation/flight-log.md`

## Citation Audit

Checked at leg design (2026-09-30):
- `design-language-page.js:11-48`: HTML-string header plus the `SECTIONS` list ✔
- `index.html:71-80`: design-language script tags ✔
- `areas/admin.js:88-91`: dev-mode-only ✔
- No test references a design-language `data-section`: a grep of `tests/` finds only
  `agents`, `connectors`, `general`, `knowledge` and `mcp` sections ✔

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.
