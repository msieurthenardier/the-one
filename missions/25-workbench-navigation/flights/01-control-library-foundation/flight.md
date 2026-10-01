# Flight: Control Library Foundation

**Status**: planning
**Mission**: [Workbench Navigation and Control Library](../../mission.md)

## Contributing to Criteria

- [ ] **SC6 — One reusable control library** (foundation):
  - the mechanism is settled;
  - the core controls the shell needs exist as one library: button, field, select,
    toggle, checkbox, list pane, menu, badge, empty state;
  - the UI guard tests see library test ids with no manual exceptions;
  - a runtime resolver checks label and description wiring;
  - there are no new HTML-string sinks;
  - the design-language page is the library's living reference in both themes;
  - a control inventory classifies every control in the app.

  Modal, drawer and palette are *ruled* here (DD8) and *built* where they are consumed
  (Flights 2 and 4).
- [ ] **SC7 — Deep-violet design language**: tokens, the four button treatments and every
  solid accent fill, applied app-wide; control boundaries brought to non-text AA; mirror
  and contrast gates; in-repo reference and published design system updated.
- [ ] **SC8 — Matches the approved samples** (prerequisite only): the board source, its
  provenance and the derived reference spec are committed with the mission
  (`reference/`).
- [ ] **SC10 — Operable and regression-safe** (per-leg gate): every library control is
  keyboard-operable with visible focus; library controls are exercised in a WebKit engine
  as well as Chromium; unit, browser and guard suites stay green.

---

## Pre-Flight

### Objective

Lay the foundation every later flight builds on:
- **Test apparatus.** The guard tests, a WebKit engine and a runtime accessibility
  resolver are made ready for a control library.
- **Mechanism.** A spike settles how controls are built without a framework, and how
  modals stack.
- **Deep violet.** The approved treatment lands app-wide through tokens and CSS, with
  contrast gates in both themes.
- **Core controls.** The controls the workbench shell needs are built, documented and
  exercised in Chromium and WebKit.
- **Living reference.** The dev-mode Design language page is rebuilt as the library's
  reference, and a control inventory records which controls in the app are
  library-defined and which are not yet.

No surface's navigation or editor internals change in this flight.

### Open Questions

- [x] Control-library mechanism → DD1. Leaning: factories. Settled by the
  `control-mechanism-spike` leg against the five exit criteria plus a cleanup criterion.
- [x] Modal, drawer and palette mechanics → DD8. The rule is set and verified in the
  spike; the controls are built where consumed.
- [x] How library test ids stay visible to the registry guard, including composite
  sub-elements → DD2
- [x] Where library code and CSS live, given the guards' scan scopes → DD5
- [x] Deep-violet token shape, which fills move, and the size modifiers → DD6
- [x] Control boundaries below 3:1 (unchecked checkbox, off toggle) → DD7. Fixed in this
  flight.
- [x] Contrast pairs that fail non-text AA → DD7. Dark fill on `--surface-elevated` is
  2.95:1 and band-pinned.
- [x] WebKit apparatus and its skip/require policy → DD9
- [x] List-pane ARIA pattern → DD14: a navigation list with `aria-current`. The selection
  listbox is a separate Flight 4 control.
- [x] Fold squawks 0105 and 0106? → DD12. Yes.

### Design Decisions

**DD1 — Mechanism: ES5 factory functions returning native elements, under `App.ui`.**

What gets built:
- Every Flight 1 control is a factory.
- Simple controls return the native element (`<button>`, `<input>`, `<select>`), or a
  wrapper whose native control is reachable.
- Stateful composites (list pane, menu) return a small controller object
  `{el, …methods, destroy}`.
- Custom elements are **not** adopted unless the spike shows factories failing a criterion
  that a light-DOM custom element passes.

Why factories:
- Playwright `fill`/`select_option`/`check` and strict locators act on native controls.
- `HTMLLabelElement.control` and `aria-describedby` resolve natively.
- Custom elements need a `class`, which is a convention change for this ES5 codebase.
  They also carry upgrade and `connectedCallback` ordering hazards.
- Factories match existing idiom: the per-editor `_el`/`_btn`/`_fieldGroup` copies,
  `App.layout.renderSectionNav`, and `App.confirmDialog`.

**Cleanup rule** (factories have no `disconnectedCallback`; the orchestrators wipe
containers with `innerHTML` and will never call `destroy()`):
- A composite installs **no persistent document-level listener**. Its keyboard handling
  lives on its own root.
- A transient popup (an open menu) attaches its document-level listeners when it opens
  and removes them when it closes.
- Every document-level handler first checks `root.isConnected`, and detaches itself if the
  root is gone.
- So `destroy()` is an optimisation, never a correctness requirement.
- Global shortcuts (e.g. `/` to focus a list filter, Ctrl K) belong to the shell
  (Flights 2–4), never to a library control.

Spike scope (`control-mechanism-spike`):
- Build `button` and `field` as factories.
- Build the list pane **both ways**: as a factory with a controller, and as a light-DOM
  custom element `<ui-list-pane>`.
- The custom element is a throwaway. Inject it in tests with `page.add_script_tag`, never
  through `index.html`. Delete it before the leg lands; the evidence goes to the flight
  log.

Judge each mechanism against the mission's five exit criteria, plus a sixth:
1. Library-authored test ids are seen by the registry guard with no manual exceptions.
2. `fill`, `select`, `check`, `disabled` and strict locators work in Chromium and WebKit.
3. A runtime label/description resolver passes over library surfaces.
4. No new HTML-string sinks.
5. A pass in the real WebKitGTK engine (DD9).
6. **Cleanup**: after the host container is wiped with `textContent = ''` without calling
   `destroy()`, no listener keeps acting on detached nodes. Probe this by dispatching the
   events that listener would handle.

Trade-off: no declarative markup authoring.

**DD2 — Library test ids are registry-visible through an extractor extension, never
through manual exceptions.**

The option:
- Factories take a `testid` option, e.g. `App.ui.button({…, testid: 'agents-new-btn'})`.

Two new patterns in `tests/_ui_guard_helpers.py`:
- **Literal:** `\btestid:\s*'([^"'\n]+)'(?!\s*\+)`. The negative lookahead stops a
  parametric site also matching as a literal; without it, every library prefix would need
  a Literal and a Parametric row, which trips the duplicate-row check. The `\b` excludes
  keys like `rowtestid:`.
- **Parametric:** `\btestid:\s*'([^"'\n]+)'\s*\+`.

Both join the definition set that `test_testids_in_source_are_registered` and
`test_registered_testids_exist_in_source` diff.

**Composite rule.** Every test id the library places on any element is supplied by the
caller as a property named exactly `testid`:
- on the control's own options;
- on a nested option object, e.g. `filter: {testid: 'agents-filter'}`;
- on a per-item object, e.g. `{label: a.name, href: …, testid: 'agents-row-' + a.id}`.

The value is a single-quoted literal or a `'prefix-' + …` concatenation. The library
**never derives an id internally**: no `rowTestidPrefix`, no suffixing, no ids returned
from callbacks.

Where test ids live:
- Registration: ids passed to library factories are **Literal** or **Parametric** rows.
- Naming: new ids follow `{area}-{element}`.
- Placement: a test id goes on the **native** control itself.
- The `testid` key is reserved for this purpose in JS. It has no current uses: grepping
  for `testid:` over `static/js` at `b9630bc` finds nothing.

Comments in `static/js/ui/*.js`:
- The extractor scans comments like live code, so JSDoc examples there must never contain
  a quoted test id.
- Write examples as `testid: <id>`, without quotes.

Guard fixes and probes (land in `ui-test-apparatus`):
- `relpath()` (`tests/_ui_guard_helpers.py:73`) is hardwired to `JS_DIR`, so
  `extract_testids(tmp_path)` raises `ValueError`. It must take the directory being
  scanned. `classify_sinks` has the same flaw.
- Probe tests in `tmp_path` cover:
  - a literal yields a literal;
  - a parametric site yields a parametric and **no** literal;
  - the per-item form;
  - `rowtestid:` yields nothing.

Real call-site registration starts when a `static/js` file first calls a factory with a
`testid`. Until then, the probes are the evidence.

**DD3 — Label and description wiring is generated, then checked at runtime.**

What `App.ui.field` generates:
- The `<label>`, with `htmlFor` pointing at the control's id. The id is caller-supplied,
  or generated by `App.ui.util.uid(prefix)`, a monotonic counter.
- Hint and error elements, each with an id, joined into the control's `aria-describedby`.
- For the error state: `aria-invalid="true"`, `.is-invalid`, and a `.field-error` element
  with an id. This keeps the existing vocabulary.

The static `for=` guard only scans HTML strings, so the library is checked at **runtime**.
- The resolver JS lives in exactly one place, `tests/browser/_a11y_resolve.js`. It is
  promoted from `test_flow_chiplist_label_resolver.py::_RESOLVE_JS` and shared by the
  Playwright helper and the WebKitGTK probe (`single-source-of-truth-for-paired-helpers`).
- The Playwright helper is `tests/browser/_a11y_resolvers.py::assert_controls_labelled_and_described(page, root_selector)`.

Rules, for every control under a root:
- **Which controls.** `input`, `select`, `textarea`, `button`, `a[href]`,
  `[role=button]`, `[role=switch]`, `[role=menuitem]`, `[role=option]`.
- **Accessible name.** Each must have a non-empty accessible name. Accepted sources:
  `labels`, `aria-label`, a resolvable `aria-labelledby`, or non-empty text content for
  content-named roles (buttons, links, menuitems, options).
- **Id references.** Every id in `aria-describedby` and `aria-labelledby` must resolve to
  an element.
- **`aria-controls`.** It must resolve unless the referencing element has
  `aria-expanded="false"`, since a popup may render only when opened.

Where it applies:
- In this flight, every control's contract test applies the helper per control.
- It is also applied to each `[data-ui-demo]` root on the reference page, not to the
  page's legacy sections.
- Flights 2–4 apply it to the surfaces they build.

**DD4 — No HTML-string sinks in the library; icons are parsed, not injected.**
- `App.ui.util.icon(name)` returns an `SVGElement`, parsed from the `App.icons` string
  with `DOMParser` (`image/svg+xml`) and imported. This promotes the pattern of
  `knowledge-section.js::_appendIcon`.
- Library files contain no `innerHTML`, `outerHTML` or `insertAdjacentHTML`, not even
  static clears; use `textContent = ''`.
- The existing sink guard already fails any new file with a dynamic sink. It exempts
  static clears by design, so a new unit guard runs `find_markdown_html_sink_tokens(path)`
  over every `static/js/ui/*.js` and asserts zero tokens.

**DD5 — Layout, export idiom and naming.**

JS:
- Code lives in `the_one/interfaces/web/static/js/ui/`.
- It is loaded by classic `<script>` tags in `index.html`, after `icons.js` and before
  `api.js` and the area modules.
- Each new tag bumps the count in `tests/test_index_asset_cache_busting.py`, which is 55
  at `b9630bc`.
- An `index.html` edit needs `make restart` on a dev instance, because the page is
  `lru_cache`d.
- Files use `'use strict'` and the IIFE namespace idiom
  (`window.App = window.App || {}; App.ui = App.ui || {}`).

Recommended split (legs may merge files, but never split a control across files):

| File | Contents |
|---|---|
| `core.js` | namespace and `App.ui.util` |
| `button.js` | button |
| `field.js` | field, text input, textarea, select |
| `choice.js` | checkbox, toggle |
| `feedback.js` | badge, empty state |
| `list-pane.js` | list pane |
| `menu.js` | menu |

Export idiom:
- **Factories** each get exactly one line of the form `App.ui.<factoryName> = function (opts) {…}`.
  This is the idiom the inventory and demo guards parse.
- **Utilities** live under `App.ui.util.*`: `el`, `uid`, `icon`, `rovingFocus`. They are
  not controls, and the guards exclude them.

CSS:
- Library rules go in `@layer components`, in **flat** files directly under `static/css/`:
  `components.css`, or a new flat sibling with its own `<link>` and a count bump.
  `test_token_definitions.py` globs `css/*.css` non-recursively, so a subdirectory would
  escape the undefined-token check.
- Existing class vocabulary is reused wherever it exists: `.btn-*`, `.field-*`,
  `.is-invalid`, `.checkbox-primary`, `.badge`, `.badge--*`, `.empty-state`. Existing
  surfaces and test selectors then keep working and pick up DD6 automatically.
- Controls with no global vocabulary get `ui-`-prefixed classes (`.ui-toggle`,
  `.ui-list-pane`, `.ui-menu`). Library-owned CSS stays greppable.
- No `backdrop-filter`: the retired-vocabulary guard forbids it.

API:
- Factories are lower-camel nouns (`App.ui.button`, `App.ui.textInput`,
  `App.ui.listPane`) and take one options object.
- Button variants are semantic. They map to the existing classes, and the mapping is
  documented:

  | Variant | Class |
  |---|---|
  | `primary` | `.btn-filled-primary` |
  | `secondary` | `.btn-outlined-primary` |
  | `ghost` | `.btn-ghost` |
  | `danger` | `.btn-muted-destructive` |

- Classes are not renamed: `.btn-outlined-primary` alone has 61 references in 18 files.

**DD6 — Deep-violet tokens and treatment.**

Three new hex tokens go in **both** theme blocks of `tokens.css`, mirrored in
`tests/browser/design_tokens.py`:

| Token | Dark | Light |
|---|---|---|
| `--accent-fill` | `#7c3aed` | `#6d28d9` |
| `--accent-fill-hover` | `#6d28d9` | `#5b21b6` |
| `--fg-on-accent-fill` | `#ffffff` | `#ffffff` |

`--accent` keeps its job: focus rings, links, selection borders, translucent washes, the
`.context-bar` meter (`chat.css:119`, a data meter, not a control) and the indeterminate
`.tool-switch` thumb (`studio.css:72-75`, pinned by
`test_tool_switch_indeterminate_thumb_holds_ui_contrast`). `--fg-on-accent` stays for
anything still on `--accent`.

**Solid control fills move to `--accent-fill`.** The leg greps every
`background(-color)?:\s*var\(--accent\)`, classifies each hit, and records the list in the
flight log. Known sites at `b9630bc`:

| Site | Location |
|---|---|
| `.btn-filled-primary` | `components.css:434-454` |
| `.checkbox-primary:checked` and its tick | `components.css:346-357` |
| `.skip-link` | `components.css:15-27` |
| `.admin-theme-option.active` | `admin.css:81` |
| admin toggle on-track | `admin.css:296-299` |
| `.tool-switch` on-track | `studio.css:67-68` |
| `.msg-pending-approval-approve` | `chat.css:523` |
| `.chip-attached` | `studio.css:397` |

The admin toggle thumb rule (`admin.css` ~284-295) applies in both states, so it is split
per state. Checked checkboxes and on toggles never use `--accent-fill-hover`, because the
dark hover fill is below 3:1 against surfaces.

**Button treatment** follows the approved board (`reference/boards/Buttons.dc.html`,
`.deep` rules; `reference/reference-spec.md` §11). All four variants share:

| Property | Value |
|---|---|
| Height | 32px |
| Padding | `0 12px` (the board's `.b` base; `.deep .p` does not restore the old 16px) |
| Radius | `--radius-sm` (6px) |
| Label | `--font-size-body` (13px) at `--font-weight-medium` (500) |
| Icon | 16px |
| Icon-only | 32×32 |
| Focus ring | unchanged: `2px solid var(--accent)`, offset 2px |
| Disabled | unchanged: opacity .4 (the board defines none) |

Per variant:

| Variant | Class | Default | Hover |
|---|---|---|---|
| primary | `.btn-filled-primary` | `--accent-fill` fill, `--fg-on-accent-fill` label | `--accent-fill-hover`, replacing `opacity .9` |
| secondary ("raised") | `.btn-outlined-primary` | `--surface-elevated` fill, `--border` hairline, `--fg` label | border `--border-strong` |
| ghost | `.btn-ghost` | transparent, `--fg-secondary` | `--surface-elevated` fill, `--fg` |
| danger | `.btn-muted-destructive` | transparent, `--status-danger-muted` hairline, `--status-danger` label | `--status-danger-bg-soft` fill |

**Size modifiers survive.** `.btn-sm` (24px), `.btn-lg` (36px) and `.btn-xl` (40px) are
used 11 times in JS and documented in `agents.md`. They keep their heights and label
sizes; they pick up the new colours and the medium weight. The 13px-label rule applies to
unmodified buttons.

**Overrides to reconcile** so an unmodified primary or secondary button renders with the
13px medium label:

| Override | Location |
|---|---|
| `.save-btn` | `components.css:984-986` |
| `.delete-btn` | `components.css:1010` (pins body-sm and padding) |
| area override | `studio.css:62` |
| `.mcp-refresh-tools-btn` | `studio.css:407` |

(`chat.css:421` is only `[hidden]{display:none}` and needs no change.)

Trade-off: secondary buttons lose their "outlined" look app-wide, including on editor
internals this mission does not otherwise touch. The operator chose the treatment
app-wide (mission decision 4).

**DD7 — Contrast gates** (`tests/test_design_tokens_a11y.py`, both themes; the
completeness net requires every new `--accent*`/`--fg*` hex token to be gated or exempt).

| Pair | Threshold | Dark | Light | Status |
|---|---|---|---|---|
| `fg_on_accent_fill` on `accent_fill` | 4.5 | 5.70 | 7.10 | new gate |
| `fg_on_accent_fill` on `accent_fill_hover` | 4.5 | 7.10 | 8.98 | new gate |
| `accent_fill` vs `bg`, `surface` (checked checkbox and on toggle identify state) | 3.0 | 3.31 / 3.11 | ≥6.4 | new gate |
| `accent_fill` vs `surface_elevated` | 3.0 | **2.95** | 6.46 | dark band-pinned; light gated |
| `status_danger` on `surface_elevated` (danger label on a transparent button) | 4.5 | 6.08 | 5.89 | new, danger-only gate |
| `status_danger` on `bg`/`surface` | 4.5 | — | — | already gated by `test_status_text_passes_body_aa` |
| `status_danger` on soft fill over all surfaces | 4.5 | — | — | already gated by `test_danger_text_on_soft_fill_passes_body_aa` |

The band-pinned exception:
- **Dark only:** `accent_fill` vs `surface_elevated`, asserting `2.9 ≤ r < 3.0`.
- It follows the shape of `test_fg_faint_band_exception`: a `# DELIBERATE EXCEPTION`
  comment plus rationale.
- The rationale: the checked or on state is carried by the white tick or thumb (5.70:1
  against the fill), so the fill-to-surface edge is not the only cue.

**Control boundaries reach 3:1 in this flight** (SC7 non-text; the library adopts these
controls, so they are changed pairs). Today the unchecked `.checkbox-primary` border and
the off-toggle track are `--border-strong`, which measures:
- Dark: 2.18 / 2.05 / 1.95 against bg / surface / surface-elevated.
- Light: 2.56 / 2.46 / 2.33.
- The light thumb on the off track is 2.56.

The fix:
- Give the unchecked checkbox border and the off-toggle track a colour that clears 3.0
  against `bg`, `surface` and `surface_elevated` in both themes.
- Give the toggle thumb a colour that clears 3.0 against its track in **both** states.
- The leg picks the token, reusing `--fg-faint` (already gated ≥3.0) or adding a
  dedicated `--control-border` hex pair. It gates every pair, mirroring as needed.

Housekeeping:
- Update the comment on the existing `fg_on_accent`/`accent` gate, since
  `.btn-filled-primary` is no longer its consumer.
- Any further failing pair the leg finds is fixed by token choice or raised as a
  flight-log anomaly before landing. It is never silently exempted.

**DD8 — Modal, drawer and palette stacking rule.** Set here, verified by the spike, and
built where consumed.

**Modals** use native `<dialog>` with `showModal()`. This covers confirm dialogs, the
leave-guard confirm, the agent picker and the jump-to palette. Native stacking and
inertness: the top layer stacks dialogs in open order and makes the rest of the page
inert.

What the library wrapper owns:
- **Opener.** Take the opener as an **explicit option** (or the triggering event's
  `currentTarget`), never `document.activeElement`. A mouse click does not focus a button
  in WebKit, so `activeElement` would be `body`.
- **Focus on open.** Focus moves explicitly to the `autofocus` element, else the first
  focusable element.
- **Focus on close.** Focus returns explicitly to the recorded opener.
- **Escape.** Handle it on `keydown` within the dialog: stop propagation and close the
  **topmost** layer only. Treat `cancel` as a fallback that is prevented and routed
  through the same close path. Chromium's CloseWatcher can group dialogs opened without
  intervening user activation and make `cancel` uncancelable.
- **Backdrop.** Use `::backdrop` with a token colour and no `backdrop-filter`.
  Custom-property inheritance into `::backdrop` shipped later than `<dialog>` itself
  (around Chrome 122 / Safari 17.4). Either use a literal-safe declaration or verify it
  on WebKitGTK 2.52.6 and WebView2.
- **Backdrop clicks.** They close transient choosers (picker, palette), never confirms.
- **Scroll.** The shell does not scroll `body`, so no scroll lock is needed. The spike
  verifies this at 1024px and 1440px.

**Chaining.**
- A transient chooser closes itself **before** acting on the chosen item. In
  palette → choose → navigate → leave guard → confirm, the confirm is the only modal open
  when it appears.
- If that confirm is dismissed, focus returns to the chooser's original opener.
- A confirm may stack above a non-transient modal.

**The spike tests**, in Chromium and WebKit:
- Escape pressed twice over two stacked dialogs peels exactly one layer each time.
- A confirm opened programmatically over a modal, without intervening user activation.
- Escape on an open `App.ui.menu` inside a dialog closes only the menu.
- Focus restore after mouse and keyboard opening.

**Interim invariant**: no production surface opens a native modal until `App.confirmDialog`
moves onto DD8. The legacy overlay is a div singleton (`dialog.js`, `z-index: 200`, 12 call
sites). Opened over a native modal, it would render under the top layer, inert, while its
document-capture keydown still mapped Enter to `onConfirm`. `App.confirmDialog` moves onto
DD8 in **Flight 2**, where the unified leave guard consumes it, before or with Flight 2's
first native modal. Its test ids are preserved: `confirm-dialog-overlay`,
`modal-cancel-btn`, `modal-confirm-btn`.

**Drawer** (Flight 4): a non-modal `<aside>` landmark. Escape closes it while focus is
inside, and focus returns to its toggle. Push vs. overlay by width is decided in Flight 4.

The spike leg updates `the_one/agents.md`'s "Modals" bullet (`agents.md:1666`, "NOT a
native `<dialog>` migration"), which this decision supersedes.

**DD9 — WebKit apparatus.**

Policy for the engine-parametrized library contract tests (Chromium and WebKit):
- **Fixture.** The engine fixture is **not** named `browser_name`: pytest-playwright's
  `pytest_generate_tests` auto-parametrizes that name.
- **Report.** Each WebKit run asserts the launched engine is WebKit and records the engine
  version (`report-what-you-got`).
- **Skip or fail.** Locally, the WebKit param **skips with a reason** when WebKit cannot
  launch. When `THE_ONE_REQUIRE_WEBKIT=1`, it **fails** instead.
  `ci/tasks/browser.yml` sets that variable and installs
  `playwright install --with-deps chromium webkit`. Pin the image to
  `python:3.11-bookworm`, or verify the floating tag's Debian base.
- **Installs.** `Makefile` `_ensure-playwright` (`Makefile:89-90`) also installs webkit;
  downloading the browser needs no sudo. The break-glass `.github/workflows/test.yml:73`
  install line also gains `webkit`.
- **Scope.** Only the library contract tests run under WebKit. The rest of the browser
  suite stays Chromium-only.

Local WebKit route (`ui-test-apparatus` establishes one, in order):
1. **Playwright WebKit** (`playwright install webkit`, no sudo). The host is missing
   system libraries Playwright's WebKit build needs, and `install-deps` needs a password:
   - `libwoff1`, `libavif16`, `libevent-2.1-7t64`, `libflite1`, `libgtk-4-1`
   - gstreamer bad and libav plugins

   The leg tries a **userland** fix: `apt-get download` plus `dpkg -x` into a cache
   directory outside the repo (e.g. `~/.cache/the-one-webkit-deps`), exposed to the WebKit
   launch only through `LD_LIBRARY_PATH`. If headless WebKit launches, this is the local
   route. The setup is recorded in a committed script, `scripts/setup-webkit-userland.sh`,
   which needs no sudo and is idempotent.
2. Otherwise the **WebKitGTK probe** (below) is the local WebKit evidence for criteria 3
   and 5 and the DD8 checks it can make. The Playwright-WebKit half of criterion 2 then
   becomes **post-merge CI evidence**. The Flight Director records that decision in the
   flight log and flags it at the post-Flight-3 operator checkpoint.

   At planning, the local Concourse (`127.0.0.1:8080`) is unreachable and WSL Docker
   integration is off. Re-check both whenever the post-merge route is relied on: an
   external-session prerequisite.

**WebKitGTK probe** (`scripts/webkitgtk_probe.py`): a committed dev tool that runs the
real desktop engine.
- **Runtime.** It runs with **system** `python3`, which has `gi` and WebKit2 4.1
  (2.52.6). The repo venv has neither, and system python cannot import `the_one`.
- **Arguments.** It takes explicit `--url` and `--data-dir`. It refuses port 8484 and the
  platformdirs default data dir.
- **Auth.** It reads `<data-dir>/api-credential`, mints a handoff through
  `POST /api/session/handoff`, and loads the handoff URL.
- **Environment pinned and recorded in its output:**
  - `GDK_BACKEND`, chosen explicitly, not inherited from `WAYLAND_DISPLAY`;
  - `WEBKIT_DISABLE_DMABUF_RENDERER=1` (WSLg DMA-BUF failures) and the
    hardware-acceleration policy;
  - an **ephemeral** website data manager, so no stale `?v=` cache between runs
    (squawk 0085);
  - an explicit theme, set via `theme-preference` before load and verified from
    `data-theme`.
- **Output.** It evaluates the shared resolver JS (DD3) plus a control self-check,
  prints JSON with the engine version, and exits non-zero on failure.
- **Lint.** `gi` imports go inside `main()` (ruff E402). No `pip install -e ".[gui]"`
  line appears in `scripts/` or the `Makefile` (`test_packaging_locked_closure` scans
  them).
- **Optional real launch.** A real `the-one app` launch, via a **scratch** venv with
  `[gui]`, never `.venv`, is optional extra evidence.
- **Feasibility.** The planning probe only proved `gi.require_version` on the WSLg
  display. Creating a WebView and evaluating JS on WSLg is **unproven** until this leg
  proves it.

**DD10 — The design-language page becomes the library's living reference.**

How demos render:
- The dev-mode Design language page demonstrates every `App.ui` factory **through the
  library**.
- Each demo is side by side in dark and light, using nested `[data-theme]` wrappers.
  Theme tokens are `[data-theme]`-scoped (`tokens.css:54/188`). Each wrapper sets its own
  `color: var(--fg); background: var(--bg)`, since inherited colour is resolved at `body`.
- Demos show variants and states: disabled, invalid, checked, indeterminate where
  supported, selected, open, and empty.
- Each demo root carries `data-ui-demo="<factoryName>"`.
- Demos render twice, once per theme, so they take generated ids (`uid`), pass **no**
  `testid` unless a test needs one, and are located by wrapper scope (theme wrapper +
  `data-ui-demo`).

Existing sections:

| Section | Fate |
|---|---|
| typography, tabs, markdown, status | stay |
| tokens | stays, and gains the DD6/DD7 tokens |
| buttons, fields | superseded by library demos |
| surfaces | its local `toggleSwitch` demo is superseded by the library toggle; tiles, list rows, section nav and picker miniatures stay until Flights 2–3 retire them |
| modal | keeps its live `App.confirmDialog` demo (one of the 12 call sites) until Flight 2's migration |

The page stays dev-mode-only (Settings › Developer, per the mission).

**DD11 — Control inventory** (`docs/ui-control-inventory.md`): one table classifying every
control kind in the app.

Kinds covered: button variants, text inputs, textareas, selects, checkboxes, toggles (both
of today's variants), chips and chip lists, tabs, section nav, list rows and tiles, menus,
modals and dialogs, the two-step confirm, flashes, badges, empty states, LEDs and status
lines, the info-icon button, key-value tables, and so on.

Each row gives:
- where the control is built today;
- its status: `library: App.ui.<factory>` or `not yet defined`;
- for undefined controls, the owning surface and the flight or mission expected to
  migrate it;
- known keyboard or a11y debt (e.g. `.area-studio .tool-toggle { display: none }`,
  `studio.css:64`).

Guards:
- A unit guard asserts that every `App.ui.<name> = function` export in
  `static/js/ui/*.js` appears in the inventory. `App.ui.util.*` is excluded.
- A browser guard asserts that every factory has a `data-ui-demo` root on the reference
  page.

**DD12 — Squawks 0105 and 0106 fold into this flight.**
- **0105** is folded into `ui-test-apparatus`. Reword the stale `DYNAMIC_SINK_BASELINE`
  header count (`test_ui_guards.py:90`) so no live count is restated.
- **0106** is already applied by the Flight Director at flight start (2026-09-30), so this
  flight's own crews receive it. The Developer and Reviewer prompts in
  `.flightops/agent-crews/leg-execution.md` now say a change under `static/` also runs
  `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and
  `tests/test_design_tokens_a11y.py`. The crew file is project-owned and not synced by
  init-project.

Both squawks close in the flight commit.

**DD13 — Scope fence.**
- Flight 1 migrates **no** existing editor or orchestrator to the library. Only the
  design-language page moves.
- Deep violet and the control-boundary fix reach existing surfaces through CSS alone.
- The per-editor `_el`/`_btn`/`_fieldGroup` copies stay until their surfaces are rebuilt:
  Flights 2–3 for chrome, the next mission for internals.
- Visual snapshot baselines (`-m pixel`, gitignored, local-only) will differ after the
  deep-violet leg. Regenerate them locally if wanted; they are never a gate. No browser
  test asserts computed colour, opacity or weight on the button or toggle classes (checked
  at design review).

**DD14 — The list pane is a navigation list. The selection listbox is a separate control.**

Structure:
- `App.ui.listPane` renders a `<section>` labelled by its header.
- The header has a title (`h2`), optional actions, and an optional filter field (a library
  `textInput`).
- Below it is an optional count/summary line and a `<ul>` of rows.
- Rows can be grouped under captions; Library groups and Settings groups use this.

Rows:
- Each row is an `<a href>`, or a `<button>` when there is no URL.
- The open item has `aria-current="page"`.
- Row anatomy: primary text, an optional meta line, optional trailing badges or counts.
- The selected-row treatment and every text-on-row colour pair are gated. On the board,
  muted caption text on a selected row measures 4.43:1 in light (reference spec §15), so
  the meta line on a selected row uses a colour that passes 4.5:1 on the composited
  selection wash.

Keyboard:
- Tab enters the list at the current row, or the first row.
- Up/Down/Home/End move by roving tabindex (`App.ui.util.rovingFocus`, following
  `section-nav.js`).
- Enter or click activates the row.
- Typing in the filter narrows rows client-side through a caller-supplied predicate and
  shows the library empty state on no match.

What the library does **not** do: it is router-agnostic (rows carry `href` and/or
`onSelect`), and it owns no global shortcut (DD1).

The searchable **selection** list behind the agent picker and the jump-to palette is a
combobox plus a listbox (`aria-activedescendant`, `aria-selected`). It is a different
control, built in Flight 4 where consumed.

### Citation Audit

Verified against the working tree at `b9630bc` by the Flight Director, then re-checked by
the Architect at design review:

| Citation | Status |
|---|---|
| `tests/_ui_guard_helpers.py:50-66` — testid extractor recognises only HTML-string `data-testid="…"` and single-quoted `setAttribute('data-testid', …)` forms (literal + parametric, each terminator-anchored) | verified |
| `tests/_ui_guard_helpers.py:69-70::iter_js_files` — `JS_DIR.rglob("*.js")`, so `static/js/ui/*.js` is scanned automatically | verified |
| `tests/_ui_guard_helpers.py:73::relpath` — hardwired to `JS_DIR`; `extract_testids(tmp_path)` raises `ValueError` | verified (Architect reproduced) |
| `tests/test_index_asset_cache_busting.py:59` — asserts exactly 55 versioned `/static` refs | verified |
| `tests/test_token_definitions.py:65` — `CSS_DIR.glob("*.css")` non-recursive; definitions only from `tokens.css`/`fonts.css` | verified |
| `tests/test_design_tokens_a11y.py:695::_FG_ROLE_PREFIXES` — `--fg`, `--accent`, `--status`, `--code-block` subject to the completeness net | verified |
| `tests/test_design_tokens_a11y.py:632-641::test_fg_faint_band_exception` — band-pinned exception shape | verified |
| `tests/test_design_tokens_a11y.py::test_status_text_passes_body_aa`, `::test_danger_text_on_soft_fill_passes_body_aa` — existing danger gates | verified (Architect) |
| `the_one/interfaces/web/static/css/components.css:434-454::.btn-filled-primary` — `background var(--accent)`, `color var(--fg-on-accent)`, semibold, hover `opacity .9` | verified |
| `the_one/interfaces/web/static/css/components.css:524-526` — `.btn-sm` 24px/10px, `.btn-lg` 36px, `.btn-xl` 40px | verified |
| `the_one/interfaces/web/static/css/tokens.css:54,188` — theme blocks are `[data-theme="dark"]` / `[data-theme="light"]` selectors (nestable on a wrapper) | verified |
| `the_one/interfaces/web/static/css/tokens.css:71,201` — `--border-strong` dark `#4a4b55`, light `#a1a1aa` | verified |
| `the_one/interfaces/web/static/css/fonts.css:41,47` — `--font-size-body: 13px`, `--font-weight-medium: 500` | verified |
| `the_one/interfaces/web/static/css/tokens.css:43` — `--radius-sm: 6px` | verified |
| `tests/browser/conftest.py:331` — browser fixture launches Chromium only | verified |
| `ci/tasks/browser.yml:30` — `playwright install --with-deps chromium` | verified |
| `the_one/interfaces/web/static/js/areas/admin/design-language-page.js:20-30::SECTIONS` — section registry | verified |
| `the_one/interfaces/web/static/js/areas/admin.js:88-91` — Design language category is dev-mode-only | verified |
| `the_one/agents.md:1666` — "Modals … NOT a native `<dialog>` migration" bullet (superseded by DD8) | verified |
| `tests/test_ui_guards.py:90` — stale "92 sites across 27 files" baseline comment (squawk 0105) | verified |

### Prerequisites

- [x] Mission approved and set `active` (2026-09-30)
- [x] Board source copied under `missions/25-workbench-navigation/reference/boards/` (canvas
  version 1790814146-6469). The canvas runtime `./support.js` is deliberately not copied.
- [x] Reference spec and provenance README derived from the approved boards
  (`reference/reference-spec.md`, `reference/README.md`, 2026-09-30). The list pane and
  menu measurements in `core-controls` draw on spec §3, §7 and §11.
- [x] Planning artifacts and the init-project methodology sync committed on the flight
  branch before the first leg. This is a separate chore commit, so the flight commit
  carries only flight work.
- [x] Squawk 0106 crew-prompt edit applied (2026-09-30)
- [x] WSLg display and system WebKitGTK 2.52.6 present (probed 2026-09-30). A WebView has
  **not** yet been created on it. **Re-verify at every leg that runs the probe.**
- [ ] A local WebKit route established, or the post-merge CI route recorded (DD9). Done in
  `ui-test-apparatus`.
- [x] Port 8485 free for a dev instance with a scratch data directory. Never 8484 or the
  default data directory. **Re-verify per leg.**

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified, except the WebKit route, which is the first leg's deliverable
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

1. **`ui-test-apparatus`** — makes the test infrastructure library-ready before any
   library code exists:
   - the extractor fix and DD2 patterns with probes;
   - the DD3 resolver JS and Playwright helper;
   - the DD4 zero-token guard (vacuous until `ui/` exists, then live);
   - the engine fixture with its skip/require policy;
   - the Makefile, CI and break-glass installs;
   - the local WebKit route and the WebKitGTK probe;
   - squawk 0105.
2. **`control-mechanism-spike`** — builds:
   - the `App.ui` core (`util`);
   - `button` and `field`;
   - the list pane both ways;
   - the DD8 `<dialog>` verification.

   It judges both mechanisms against the six criteria and records the decision with
   evidence. It also updates the `agents.md` Modals bullet. The Flight Director confirms
   the decision before `core-controls` is designed.
3. **`deep-violet-tokens`** — tokens, CSS, mirror and gates, plus the control-boundary
   fix. It is independent of the spike's outcome.
4. **`core-controls`** — completes the core set on the settled mechanism: select,
   textarea, checkbox, toggle, menu, badge and empty state, plus hardening `button`,
   `field` and `listPane`. Each control gets keyboard behaviour, visible focus, the DD3
   helper, and contract tests in both engines.
5. **`living-reference-and-inventory`** — covers:
   - the reference page;
   - the inventory with its guards;
   - control-library docs in `agents.md` and a CLAUDE.md pointer;
   - the flight-close verification.

### Checkpoints

- [ ] Guard extensions and probes green; resolver helper and engine policy in place; local
  WebKit route established or post-merge route recorded (`ui-test-apparatus`)
- [ ] Mechanism decided with evidence against all six criteria; `<dialog>` chaining,
  Escape and focus restore verified in Chromium and WebKit (`control-mechanism-spike`)
- [ ] Deep violet app-wide; control boundaries at 3:1; mirror in sync; gates and band
  exception green (`deep-violet-tokens`)
- [ ] Core controls complete with contract tests in both engines (`core-controls`)
- [ ] Living reference and control inventory with their guards (`living-reference-and-inventory`)
- [ ] Flight close:
  - full unit tier and `make lint`;
  - all four browser lanes;
  - WebKit contract tests;
  - WebKitGTK probe of the reference page;
  - shell-navigation-smoke.

### Adaptation Criteria

**Divert if**:
- Factories fail a spike criterion that the custom-element variant passes. The mechanism
  changes; `core-controls` and the reference leg are re-planned; adopting `class` is
  recorded as an explicit convention change in `the_one/agents.md`.
- Native `<dialog>` misbehaves in WebKitGTK 2.52 or Playwright WebKit (stacking, Escape,
  inertness, focus restore). DD8 is re-ruled, with an overlay plus manual `inert` as the
  fallback, before Flight 2 consumes it.
- A DD6 or DD7 pair fails a gate and no token choice within the operator's approved hexes
  fixes it. This needs an operator decision; record it and hold the leg.
- The WebKitGTK probe cannot create a WebView on WSLg. Record it; the WebKit evidence then
  rests on Playwright WebKit, locally or post-merge.

**Acceptable variations**:
- The file split under `static/js/ui/` differs from DD5's recommendation, with no control
  split across files.
- Playwright WebKit is unavailable on the dev host while CI installs it. The WebKitGTK
  probe is the local evidence and the post-merge route is recorded (DD9).
- Leg 3's grep finds solid-accent-fill sites beyond the known list.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created
> one at a time as the flight progresses.

- [ ] `ui-test-apparatus` - Extractor `relpath` fix and DD2 patterns with probes; shared
  DD3 resolver JS and Playwright helper; DD4 zero-token guard; engine-parametrized fixture
  with skip/require policy; Makefile, CI and break-glass WebKit installs; local WebKit route
  (userland deps) and `scripts/webkitgtk_probe.py`; squawk 0105.
- [ ] `control-mechanism-spike` - `App.ui.util` core; `button` and `field`; list pane both
  ways; judged against six criteria; `<dialog>` stacking, Escape and focus-restore
  verification in both engines; decision record; `agents.md` Modals bullet.
- [ ] `deep-violet-tokens` - `--accent-fill*` tokens in both themes; four button treatments
  app-wide; solid control fills migrated; control boundaries at 3:1; mirror, gates and
  dark band exception; design-language doc updates in `agents.md`.
- [ ] `core-controls` - Complete the core set on the settled mechanism (select, textarea,
  checkbox, toggle, menu, badge, empty state; harden button, field, list pane). Keyboard
  behaviour, visible focus, the DD3 helper, and contract tests in Chromium and WebKit.
- [ ] `living-reference-and-inventory` - Design-language page rebuilt from the library in
  both themes; `docs/ui-control-inventory.md`; demo and inventory guards; control-library
  docs in `the_one/agents.md` and a CLAUDE.md pointer; flight-close verification.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged to `main` (per-flight branch, mission decision 8)
- [ ] Tests passing:
  - `make lint`;
  - `make test-unit`;
  - all four browser lanes;
  - WebKit contract tests (locally or post-merge, per DD9).
- [ ] Documentation updated:
  - `the_one/agents.md`;
  - `CLAUDE.md`;
  - `docs/ui-testid-registry.md`;
  - `docs/ui-control-inventory.md`.
- [ ] Published design system updated by the Flight Director
  (https://claude.ai/artifact/51jpj1RcXp18MehEQAteWs): tokens, plus the Button, Checkbox
  and Toggle components, for deep violet and the boundary fix.
- [ ] Squawks 0105 and 0106 closed in the flight commit

### Verification

- **Unit tier**: `make test-unit` and `make lint`. Covers:
  - the extended guards in `tests/test_ui_guards.py`;
  - `tests/test_token_definitions.py`;
  - `tests/test_design_tokens_a11y.py`;
  - the zero-token and inventory guards;
  - the cache-busting count.
- **Browser**: all four lanes via `scripts/run-tests.sh --lane …`. Deep violet is app-wide
  CSS, so every lane is in the diff. Plus the engine-parametrized library contract tests
  in both engines, per DD9.
- **WebKitGTK**: `scripts/webkitgtk_probe.py` against the rebuilt reference page on a dev
  instance (`THE_ONE_DEV_MODE=true`, port 8485, scratch data dir), with the engine
  version, the pinned environment and the results in the flight log.
- **Flight review**: a Reviewer plus an Accessibility Reviewer (UI changes), over the
  whole flight diff.
- **Flight close**: `/mission-control:behavior-test shell-navigation-smoke` against the dev
  instance on 8485. This is the standing data-independent regression gate (M17-F1), and
  it confirms the app-wide CSS change broke no area.
- No new behavior specs: the core-flow specs arrive with Flights 2 and 4.
