# Leg: header-and-banner

**Status**: completed
**Flight**: [Settings on the library](../flight.md)

## Objective
Build, in the library only:
- `App.ui.pageHeader` (with an actions slot);
- the `editorShell` page variant, which composes it;
- `editorShell` and `section` `inset: 'none'`;
- `App.ui.banner`, with a persistent live mode.

Each is contract-tested in Chromium and WebKit, with a catalogue row. **No consumer moves.**

Split from the original leg 04a at its design review (2026-10-23), with `codeBlock`, `facts` and the input options (04b) and B14 plus the emitted-class guard (04c).

## Context
- **Flight decisions:** DD4, DD12 (marker classes `ui-page-header` and `ui-banner`; the legacy `page-header`, `page-title`, `banner` and `banner-*` names stay emitted, and their ownership hands over in leg 10), DD11.
- **The shell's header today** (`js/ui/editor.js`): `div.editor-header > div.editor-header-text + div.form-actions`.
  - The text column holds the breadcrumb, `hN.editor-title[tabindex=-1]` and the subtitle.
  - The actions hold `span.editor-unsaved[role=status]` first, then Cancel, Save and Test, then `span.editor-error` last.
  - About 208 test lines select `.editor-title`, and about 37 select `.page-title`. `App.focusAfter` targets `.editor-title`.
- **The decision** (design review option b): `pageHeader` takes an `actions` node slot. The page variant builds a `pageHeader` and passes its existing actions cluster into that slot. The `h1` carries **both** `editor-title` and `page-title`, with `tabindex=-1`, so focus-after and both sets of selectors keep working.
- **`dangerZone`'s notice** today is `div.action-blocked-message.banner.banner-error[role=alert]`, kept in the DOM and collapsed by `.action-blocked-message:empty`. `provider-editor.js:379` queries `.action-blocked-message`.
  - The banner's persistent live mode must collapse to zero height while empty. Use a `data-empty` hook set by the factory, not `:has`, and not relying on `:empty` alone if the banner has inner structure.
  - The banner never emits `action-blocked-message`. Leg 04f passes it through a `className` option.

## Outputs
1. **`App.ui.pageHeader({title, headingId, intro, actions, testid, titleClassName})`** → `{el, titleEl, setTitle, setIntro, actionsEl}`.
   - It renders `div.page-header.ui-page-header > (div.ui-page-header-text > h1.page-title[id] + p intro?) + div.ui-page-header-actions?` (`actions` is a node).
   - The `.ui-page-header` rules go in `components.css` **after** `.page-header` (about `:1223`), so the control's geometry wins without new specificity. Test it computed both bare and under `area-admin`. The Settings geometry is today's `.area-admin .page-header`, 16px 32px (re-read `admin.css:24-33`).
2. **`editorShell({variant: 'page', …})`**: the header is a `pageHeader` whose `h1` also has `editor-title` and `tabindex=-1`, with the shell's existing actions cluster in its `actions` slot. `setDirty`, `setBusy`, `setError`, `focusTitle` and `setTitle` behave exactly as in the default variant.
   - A `breadcrumb` with `variant: 'page'` throws, and so does `titleLevel: 2`.
   - **The default variant is unchanged.** A regression test pins its header DOM: `div.editor-header > div.editor-header-text + div.form-actions`, the caption `span[role=status]` first and the error span last.
3. **`inset: 'none'`** on `editorShell` and `section` removes their horizontal padding (what `.settings-item .editor-header`/`.editor-section` do today, `admin.css` about `:132-133`) through a modifier class owned by each row.
4. **`App.ui.banner({tone, text, children, role, live, className, actions, hidden, testid})`** → `{el, set(text), setChildren(nodes), show(), hide()}`.
   - `tone` is `info`, `warning` or `error`.
   - `role` is `note` (default), `status` or `alert`.
   - `live` is `'alert'|'status'`; it implies the matching `role`, and contradicting values throw.
   - Unknown `tone`, `role` or `live` values throw.
   - **Persistent live mode** keeps the node rendered with its role while empty, collapsed (`data-empty` on the node gives zero height and no padding). `set('')` after text collapses it again.
   - It renders `div.banner.banner-{tone}.ui-banner` plus `className`. The `ui-banner` CSS adds only the new behaviour (the empty collapse); the look stays the legacy `.banner` rules until leg 10's handover.
5. Catalogue rows for `pageHeader` and `banner`, plus the `editorShell` and `section` row updates. Contract tests in `contracts-controls` (`test_ui_page_header_contract.py`, `test_ui_banner_contract.py`, additions to the editor contract file), with literal `App.ui.pageHeader(` and `App.ui.banner(` calls (the inventory guard).

## Acceptance Criteria
1. Each output exists as specified, contract-tested in both engines: DOM shape, roles and names, every option and setter, the throws.
2. **Computed checks:**
   - `pageHeader` geometry, bare and under `area-admin`;
   - `inset: 'none'` under `area-admin`;
   - an empty live banner has height 0;
   - a non-empty banner looks as today's `.banner.banner-{tone}` does (same computed padding, border and colours as a legacy-markup fixture).
3. **The page variant:**
   - its `h1` matches `.editor-title`, `.page-title` and `[tabindex="-1"]`;
   - `focusTitle()` focuses it;
   - the actions and caption sit in the header row (bounding-box check).

   The default variant's DOM pin passes.
4. `OWNERSHIP_ALLOWANCE` is byte-identical. `test_ui_control_inventory.py` passes. A grep shows that `ui-page-header` and `ui-banner` appear nowhere outside `js/ui/`, the library CSS and the tests.
5. No consumer file changes (`git diff --stat`).
6. The unit tier, the static guards and both contracts lanes pass, and so do the lanes with editors that use `editorShell` (`providers`, `agents`, `library`, `knowledge`, `settings`, `agent-tabs`), at most 3 at a time.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_ownership.py tests/test_ui_control_inventory.py -q -x --timeout 120`.
- The lanes under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`.
- `make test-unit` once.

## Files Affected
- `static/js/ui/editor.js`, plus a new `static/js/ui/page.js` if preferred for `pageHeader` and `banner` (its `index.html` tag goes in the `js/ui/` group; the cache-busting order check applies). `static/css/components.css`.
- `tests/browser/test_ui_page_header_contract.py`, `test_ui_banner_contract.py`, the editor contract file.
- `docs/ui-control-inventory.md`, `the_one/agents.md`, the flight log.

## Citation Audit
- `editor.js:42-60` shell options and the header build: verified (FD read). The header structure and selector counts come from the 04a design review.
- `editor.js:283` `dangerZone` notice; `provider-editor.js:379` `.action-blocked-message` query: from the design review.
- `components.css` about `:1223` `.page-header`: from the design review.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
