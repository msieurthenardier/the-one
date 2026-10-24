# Leg: knowledge-indexing

**Status**: ready
**Flight**: [Settings on the library](../flight.md)

## Objective
Rebuild Settings › Knowledge indexing on the library:
- the `editorShell` page variant: Cancel and Save top right, the unsaved caption, busy and dirty from the shell (A19);
- sections with one rule each (A18);
- `field`s with linked hints (DD8-14) and errors that replace hints (A21);
- the library switch for watching (A20);
- humanised values and plain wording (A22-A24);
- an intro line (B15).

It also fixes the double submit and lost edits (DD8-15), the "Saved." timer race (DD8-16), focus after Save (DD8-17) and unnamed 422s (DD8-18). It is the last Settings page to move, so `banner` and `pageHeader` take ownership of their legacy classes (DD12), and the `.area-admin` legacy switch and field-error rules go.

## Context
- **Flight decisions:** DD6 (Knowledge indexing), DD8 14-18, DD5, DD3, DD12, DD7 (rows 18-24, 27, 38, 40).
- **Today** (`knowledge-settings-page.js`, 314 lines):
  - **the page is one HTML string** (`:31-97`, 1 sink);
  - **structure:** four `admin-system-section` blocks; the load-error banner; three number fields as `field-group` + `field-hint` + `field-error[hidden]` (the hints are not linked, DD8-14);
  - **watching:** the legacy switch in `field-row.admin-pf-row` (two labels, no switch role; `field-row`/`admin-pf-row` have no CSS);
  - **status and Save:** the `admin-system-flash`; Save mid-page with no Cancel; the read-only `admin-kv-*` rows;
  - **wiring:** `wireKnowledgeSettings` (`:102-311`):
    - `querySelector` lookups;
    - a hand-rolled `setFieldError`;
    - a dirty baseline mirrored to `admin.js`'s `dirty` (`App.nav` source, `_refresh` skips while dirty);
    - raw `fetch` for GET and PUT;
    - input during a PUT re-enables Save (`:210`), and the response then overwrites newer typing (`:289`) (DD8-15);
    - a 3 s "Saved." clear that wipes a later error (`:291`) (DD8-16);
    - a server 422 joined into the flash without the field name (DD8-18).
- **After:**
  - `App.ui.editorShell({variant: 'page', title: <the page label from App.settingsPages>, actions: {cancel, save}, errorRole: 'alert'})`, plus an intro line (B15);
  - the sections are `App.ui.section({title, layout: 'stack'})`: Chunking, Monitoring, Embedding, Vector store (sentence case);
  - the fields are `App.ui.field({label, hint, error})` with `App.ui.textInput({type: 'number', min, max, step, width: 'short'})`; testids kept through `testid`, `hintTestid` and `errorTestid`. The hint is linked by `aria-describedby`, and the error replaces the hint while shown (A21). The overlap is checked against its own limit even when the size is invalid;
  - the interval: the hint "10 seconds to 24 hours", with the value echoed humanised next to the field ("15 minutes") (A22);
  - watching is an `App.ui.toggle({label: 'Watch registered folders for changes'})` on one line (A20; ledger row 40);
  - the read-only rows are `App.ui.facts` with humanised values ("Local (bundled)", "USearch", "16-bit float"; the model id kept) and plain notes (A23, A24);
  - save through `fetchJson` with `fieldErrors` (`loc` `["size_chars"]`, etc.; the overlap's `[]` goes to editor level) (DD8-18);
  - `latest()` for load and save; busy through the shell (fields stay live);
  - the baseline from the response: typing during the request stays dirty and is not overwritten (DD8-15);
  - "Saved." through `App.ui.flash`, or a status with one timer cleared on each attempt (DD8-16);
  - focus after Save through `App.focusAfter` (DD8-17);
  - Cancel patches the fields back to the baseline.
- **The remount side-effect inventory (DD5)** applies: `_refresh` re-mounts the page when clean today. Keep that (it refetches settings), or patch in place, and record the choice. Errors, flash, focus, the dirty mirror and the read-only rows are each inventoried.
- **DD12 handovers here:**
  - `banner`'s row lists `banner` and `banner-*` as owned;
  - `pageHeader`'s row lists `page-header` and `page-title` as owned;
  - the `.area-admin .page-header`/`.admin-form` rules (`admin.css` about `:24-33`) are deleted (the control owns the geometry);
  - the `.area-admin` halves of the legacy `.tool-enable-switch` rules and their a11y pins are deleted (`test_design_tokens_a11y.py` about `:599`, `:631-641`, `:664-673`; `tests/browser/test_deep_violet_computed_styles.py:47-49` fixture). The `.area-studio` halves stay for Flight 5;
  - `.area-admin .field-error` (`admin.css` about `:448-459`) is deleted;
  - every remaining `admin-system-*` rule is deleted.
- **Tests:** `test_flow_admin_knowledge_settings.py` (11). The library field removes a cleared error node where today it is kept `[hidden]`: count-1 assertions move to `to_be_hidden`. `test_load_failure_renders_error_state_not_empty_form` keeps its meaning.

## Inputs
- Legs 03a, 03b, 04a-04c, 08a and 08b landed.

## Outputs
- `knowledge-settings-page.js` DOM-built on the library: zero sinks (its `HTML_SINK_ALLOWANCE` and `DYNAMIC_SINK_BASELINE` entries removed) and zero ownership rows (from 6 rows / 18 uses).
- `admin.css` as above.
- The DD12 handovers, with the catalogue and emitted-class guard updated.
- Tests:
  - DD8-14 to DD8-18, test-first:
    - the hints are in the inputs' accessible descriptions;
    - typing during a held PUT keeps Save enabled-state correct (busy), sends one PUT, and keeps the newer typing dirty;
    - a second save within 3 s keeps its error;
    - focus after Save;
    - a server 422 on `size_chars` shows on that field;
  - A18-A24 and B15;
  - the knowledge settings file retargeted.
- `agents.md` (the Knowledge indexing panel paragraph), CLAUDE.md's Studio-surfaces paragraph (if it describes the panel layout), the registry (new testids: Cancel, the intro, the echo), and ledger rows confirmed by captures.

## Acceptance Criteria
1. DD8-14 to DD8-18 tests fail before and pass after.
2. A18-A24 and B15 are each asserted:
   - one rule per section, computed;
   - Cancel and Save in the header;
   - the switch on one line;
   - the hint replaced by the error;
   - the humanised interval;
   - the humanised read-only values;
   - the plain notes;
   - the intro.
3. **The leave guard still works:** a dirty page asks on leave (`App.nav`), and `_refresh` while dirty doesn't wipe edits.
4. `knowledge-settings-page.js` has no sink and no ownership rows. `admin.css` has no `.area-admin .tool-enable-switch*`, `.area-admin .field-error`, `.area-admin .page-header` or `admin-system-*` rule.
5. **DD12:** `banner` and `pageHeader` own their legacy names. `OWNERSHIP_ALLOWANCE` has no row naming them, and the emitted-class guard passes with their exemptions removed.
6. The capture compare shows only ledger rows 18-24, 27, 38 and 40.
7. The unit tier, the static guards (`test_design_tokens_a11y.py` with the switch pins retargeted), the emitted-class guard, and the `settings`, `shared` (`test_deep_violet_computed_styles.py`) and `mcp` lanes pass. `mcp` covers the `.area-studio` switch rules that stay.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_ui_control_inventory.py tests/test_ui_emitted_classes.py tests/test_design_tokens_a11y.py -q -x --timeout 120`.
- Lanes `settings`, `shared` and `mcp` under netns; the capture compare; `make test-unit` once.

## Edge Cases
- **Invalid input while clean:** the Save stays disabled, as today, until the value is valid and dirty.
- **The watcher toggle** saves only through Save (not immediately), as today.

## Files Affected
- `static/js/areas/admin/knowledge-settings-page.js`, `static/js/areas/admin.js` (if the bridge's call changes), `static/css/admin.css`.
- `tests/browser/test_flow_admin_knowledge_settings.py`, `tests/browser/test_deep_violet_computed_styles.py`, `tests/test_design_tokens_a11y.py`, `tests/test_ui_guards.py`, `tests/_ui_ownership_allowance.py`.
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `the_one/agents.md`, CLAUDE.md, the flight log.

## Citation Audit
- `knowledge-settings-page.js:208-211`, `:287-291`: verified (FD read at planning).
- `:31-97`, `:102-311`, `:120-132` and the `admin.css` and a11y pin lines: from the surveys.

## Design Review Amendments (cycle 1, 2026-10-23)
These override the body where they conflict.
- **Inputs** add legs 04f, 06, 07a-07d, 08b and 09. Their users of `banner`, `page-header`, `field-error` and `tool-enable-switch` must be gone before this leg deletes the rules and hands over ownership.
  - **A pre-step** greps `page-header|page-title|banner( |-)|tool-enable-switch|field-error` across `static/js` outside `js/ui/`, and across the area CSS. It fails the leg (`[BLOCKED:…]`) if any hit remains outside the studio-scoped Flight 5 rules (`mcp-server-editor.js`, `.area-studio`).
- **Pins** for the switch deletion: `test_design_tokens_a11y.py` about `:599`, `:631-641` and `:664-673` (including `.area-admin .tool-enable-switch-track` and `::after` at `:666`/`:672`). `test_deep_violet_computed_styles.py:47` keeps its `<div class="area-admin">` wrapper, and only the switch markup is removed (check what else it asserts).
- **The leave guard and `_refresh`:**
  - `onDirtyChange` fires on every edge, including Cancel and a successful Save, so `admin.js`'s `dirty` returns to false and `App.nav` asks only when the page really is dirty (test: Cancel, then navigate, and no prompt appears);
  - `_discardEditor` for Knowledge also invalidates the page's `latest()`, so an in-flight GET or PUT cannot repaint a torn-down page;
  - **the clean `_refresh` still remounts** (it refetches and refreshes the baseline). The "Saved." status is dropped on that remount, deliberately, and a test pins it.
- **The baseline** is `{chunking, monitoring}` from the response. After a Save, the fields are re-diffed against it and never overwritten, so typing during the request stays dirty (DD8-15). The facts come from the response. Cancel patches the fields to the baseline, clears the errors, resets the interval echo, and revalidates.
- **Load failure:** the shell's `errorRole: 'alert'` carries the load error, with testid `knowledge-settings-load-error`. Save is never enabled (`baseline == null` never marks dirty), and `enabledWhenClean` is false.
- **422s:**
  - field errors have `loc` relative to the sub-model (`["size_chars"]`, `["reconcile_interval_seconds"]`);
  - the overlap model validator has `loc: []` and a "Value error, …" message (03a's humaniser strips the prefix), and it runs only when the field validators pass;
  - a plain-string `detail` goes to the editor level;
  - `test_server_422_renders_detail_text` (a plain-string detail) is retargeted from the flash to the shell error.
- **Testids:**
  - kept through `testid`, `hintTestid` and `errorTestid`: `knowledge-{size-chars,overlap-chars,reconcile-interval}-{input,error}`, `knowledge-overlap-hint` (it survives being replaced by the error while it shows), `knowledge-watch-enabled-toggle`, the section and read-only value testids, `knowledge-settings-load-error`;
  - **renamed:** `knowledge-settings-flash` becomes the "Saved." status's testid (same name, if possible), and `knowledge-settings-panel` goes on the shell root;
  - **new:** `knowledge-settings-cancel-btn`, `knowledge-settings-intro`, `knowledge-reconcile-interval-echo`.

  Check that `test_panel_renders_defaults_and_readonly_sections`' "0 `input, select` in the read-only sections" still holds.
- **The notes:** use the server's `notes` strings or the client's static text, not both. Pick the server's, if they carry A24's wording (rewrite them there if needed, since they are not model-facing).
- **The interval echo** is plain text, not a live region. Test it with "15 minutes", "1 hour", "1 day", and blank or invalid (no echo).
- **The "Saved." timer:** one handle, cleared on each attempt and on discard.
- **`components.css:1245`** is checked and deleted in leg 11, not here.

## Amendment from batch B4 (2026-10-24, FD call; a proactive presentation fix)
- **`App.ui.facts` aligns its values.** Today each label sizes to its own text, so values in one list don't share a left edge (seen on Encryption after 08b). This leg uses `facts` for the read-only rows, so fix it here: the `dl` is a two-column grid (`grid-template-columns: max-content 1fr`, rows `display: contents`, or an equivalent that keeps the `div.ui-facts-row` wrappers and their testids). This is a library change in a surface leg, re-tiered high under DD11. It gets a contract test in both engines (all values share one left edge, long labels wrap without overlap at 1024) and a catalogue note. Re-capture Encryption, Date and time's preview and this page. A ledger row records the alignment.

Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
