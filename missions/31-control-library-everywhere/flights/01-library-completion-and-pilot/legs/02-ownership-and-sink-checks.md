# Leg: ownership-and-sink-checks

**Status**: completed
**Flight**: [Library completion and a stateful pilot](../flight.md)

## Objective
Install the mission's code-level regression apparatus before any control changes:
- the `App.ui.icon` control;
- an Owned classes column in the control catalogue;
- the reuse check, with a measured exact-count allowance and retired-API rows;
- an exact per-file count of every HTML-string sink.

The capture tool and the "before" captures are leg 03, split out at design review.

## Context
- **Flight decisions:**
  - DD3: owned classes are declared in the catalogue.
  - DD4: the reuse check and its tokenizer.
  - DD5: the sink count.
  - DD6: the icon control and the retired-API rows.
- **Leg 01 has landed.** The Design language page is gone, and the inventory doc has a Tokens and type section with its row parser scoped to the control tables (5 cells). Read the flight log's leg 01 entry for exactly how it scoped the parser.
- **Existing guard helpers:**
  - `tests/_ui_guard_helpers.py`: `iter_js_files`, `relpath`, `classify_sinks` (`:361`, returns `(dynamic, static)` per-file snippet lists) and the testid-extraction regexes (near `:53-80`).
  - `extract_js_string_contents` (`:489`) is **not reusable** for the reuse check (design review). It returns one joined blob with no positions or context, and has no regex-literal handling. Write a new tokenizer that reuses only its comment and quote state-machine pattern.
- `tests/test_ui_guards.py:97` `DYNAMIC_SINK_BASELINE`: the text freeze stays as it is.

## Inputs
- Leg 01 landed (uncommitted on the branch).
- `static/js/ui/core.js:72` `App.ui.util.icon(name)`: returns an `aria-hidden` svg node and throws on an unknown name.

## Outputs
- `static/js/ui/core.js`: `App.ui.icon`. It goes in `core.js`, not a new file, so `index.html` and the script-count pin are unchanged.
- `static/css/components.css`: the `App.ui.icon` banner.
- `docs/ui-control-inventory.md`: the Owned classes column, the `App.ui.icon` row, and the "Owned by controls built later" table.
- `tests/test_ui_control_inventory.py`: 6 cells; parser scoped to tables whose header starts `| Control |`.
- `tests/test_ui_ownership.py` (new), `tests/_ui_ownership_allowance.py` (new).
- `tests/test_ui_guards.py`: `HTML_SINK_ALLOWANCE` and its test.
- `tests/browser/test_ui_icon_contract.py` (new).

## Acceptance Criteria
- [ ] **`App.ui.icon(name, opts)`**, defined in `static/js/ui/core.js`:
  - returns an SVG element node with `aria-hidden="true"` and throws on an unknown name;
  - `opts.size` is `'sm'` (14px) or omitted (16px), set through owned classes `ui-icon` and `ui-icon--sm` in a `/* === App.ui.icon === */` banner in `components.css`, not inline styles;
  - `opts.className` is appended;
  - `App.ui.util.icon` delegates to it, so existing library callers are unchanged.

  It has a catalogue row and `tests/browser/test_ui_icon_contract.py` in both engines, covering node type, `aria-hidden`, size classes, the unknown-name throw, and that it is not focusable.
- [ ] **The Owned classes column.** Every row of every control table (tables whose header line starts `| Control |`) has 6 cells: Control, Built today, Status, Owner / migration, **Owned classes**, Debt.
  - `cells[2]` stays Status.
  - Owned classes is a comma-separated backticked list for `library:` rows, and `—` for `not yet defined` rows.
  - `tests/test_ui_control_inventory.py` checks 6 cells, only in `| Control |` tables, and that every `library:` row lists at least one owned class.
  - The owned classes are each factory's own classes, read from its source (do not guess), plus the adopted shared names in flight DD3, each assigned to the row of the factory that emits it:
    - buttons: `btn-filled-primary`, `btn-outlined-primary`, `btn-ghost`, `btn-muted-destructive`, `btn-sm`, `btn-icon`;
    - fields: `field-input`, `field-textarea`, `field-select`, `field-group`, `field-group-label`, `field-hint`, `field-error`;
    - feedback: `badge`, `empty-state`;
    - choices: `checkbox-primary`.
- [ ] **The "Owned by controls built later" table** has the header `| Class | Owning control (planned) | Flight |`. It must not start with `| Control |`, and the inventory test reads it as a separate table. It lists:
  - `field-info-icon`;
  - the editor shell classes `editor-header`, `editor-header-text`, `editor-breadcrumb`, `editor-breadcrumb-link`, `editor-title`, `editor-subtitle`, `form-actions`, `editor-unsaved`, `editor-error`;
  - `editor-section`, `section-title`, `section-description`;
  - `danger-zone`, `danger-zone-title`, `delete-btn`, `action-blocked-message`;
  - `indicator-led`, `app-flash`, `confirm-delete`, `confirm-lapsed`, `chip`.
- [ ] **The reuse check: `tests/test_ui_ownership.py`**
  - Reads the owned and planned classes from the catalogue. Planned classes are checked from now on, so their existing uses are counted in the allowance.
  - Scans every `static/js/**/*.js` outside `static/js/ui/`, and `static/css/{chat,studio,admin,base}.css`.
  - **New tokenizer:** a state machine over JS source that yields each string literal with its start offset and the preceding source context.
    - It handles `//` and `/* */` comments, `'…'` and `"…"` strings with escapes, and regex literals: a `/` in an operand position starts a regex.
    - Backticks are banned by the existing tripwire; treat one as a string anyway.
    - A unit test asserts that the scan of every real JS file ends in the code state (not inside a string, comment or regex). This is the guard against desynchronisation.
  - **Excluded literals:** testid values, which are a value after `testid:` or `<word>Testid:`, a value after a `'data-testid'` key, or the second argument of `setAttribute('data-testid', …)`.
  - **Token match:** `(?<![\w-])name(?![\w-])` within a literal's content.
  - **CSS:** comments are stripped; only selector text (before each `{`) is searched.
  - **Retired-API calls** are counted per file under pseudo-keys: `api:App.icon(`, `api:App.iconNode(`, `api:App.showFlash(`, `api:App.confirmDelete(`, `api:App.consentLink.`. Calls in comments do not count, and the `window.` prefix is optional.
  - **The comparison** is against `OWNERSHIP_ALLOWANCE` (`{(relpath, key): count}`, in `tests/_ui_ownership_allowance.py`). It fails on any difference: a new row, a higher or lower count, a row now at zero. It prints the complete corrected dict, sorted by `(relpath, key)` and ready to paste.
  - The module docstring explains the ratchet: lower the allowance in the same change that removes uses, and never raise it without a flight-log reason.
- [ ] **Tokenizer unit tests** (fixture strings, no file IO) cover each of these:
  - a class inside a `//` comment and inside a `/* */` comment is ignored;
  - an apostrophe in a comment does not break string pairing;
  - a regex literal containing a quote (`/['"]/`) does not open a string;
  - a testid equal to a class name is ignored, in all three testid forms;
  - `field-input-wide` does not match `field-input`;
  - `'btn-ghost btn-sm'` counts both;
  - a CSS declaration value is ignored, and a selector `.area-studio .field-input` counts.
- [ ] **The allowance is generated by running the check, not predicted.** Its largest rows are read to confirm they are real emissions or queries; a noisy row means a tokenizer bug to fix, not an allowance. The flight log records the row count, the total uses, the five largest rows, and the retired-API totals.
- [ ] **The sink count: `HTML_SINK_ALLOWANCE`**
  - Added to `tests/test_ui_guards.py`: an exact per-file count of every sink `classify_sinks` finds, dynamic plus static, including clears and single literals.
  - A test fails on any difference, both directions, printing a paste-ready corrected dict.
  - It is generated, not predicted, and the flight log records the total and the per-file counts of the provider files.
  - `DYNAMIC_SINK_BASELINE` and its test stay.
- [ ] **Gates:**
  - `make test-unit`, with the documented skip count;
  - ruff check and format;
  - the static guards (`test_ui_guards.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`);
  - the `contracts` lane with `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1`.
- [ ] **Docs:**
  - `the_one/agents.md` "Control library (`App.ui`)" describes `App.ui.icon`, the Owned classes column, the reuse check, its tokenizer exclusions and ratchet rule, and the sink count;
  - `CLAUDE.md`'s Control library paragraph names the reuse check in one sentence.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_ownership.py tests/test_ui_guards.py tests/test_ui_control_inventory.py -x -q`.
- `make test-unit`.
- `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts -x`.
- Edit one line to add `'field-input'` to some area file and confirm the check fails with a paste-ready dict; then revert. Do the same for a sink.

## Implementation Guidance
1. **`App.ui.icon` in `core.js`:** factory, CSS banner, catalogue row, contract test. The disk harness and `index.html` both load `icons.js` before `core.js` uses it at call time; confirm the order in `index.html`.
2. **The catalogue column and the "built later" table**, then the inventory test.
3. **The tokenizer as plain functions** with fixture unit tests, then the file-state assertion, then the file scan and the generated allowance.
4. **The sink count**, built on `classify_sinks`.
5. **Docs.**

## Edge Cases
- `btn-*` modifier strings, querySelector hooks (`'.field-input'`) and `className +` concatenation are real uses under DD4 (queries count), so they are allowance rows, not tokenizer exceptions.
- `'badge--' + type` never forms the whole token `badge--x`. `badge` itself still matches inside `'badge badge--'`, which is intended.
- A regex literal's operand-position rule: a `/` after `(`, `,`, `=`, `:`, `[`, `!`, `&`, `|`, `?`, `{`, `}`, `;`, `return` or the start of a line starts a regex; elsewhere it is division. The file-state assertion catches a mistake.

## Files Affected
- `the_one/interfaces/web/static/js/ui/core.js`, `the_one/interfaces/web/static/css/components.css`.
- `docs/ui-control-inventory.md`, `tests/test_ui_control_inventory.py`.
- `tests/test_ui_ownership.py` (new), `tests/_ui_ownership_allowance.py` (new), `tests/test_ui_guards.py`.
- `tests/browser/test_ui_icon_contract.py` (new; contracts lane).
- `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit
Checked 2026-10-15 at `59992fd`:
- `ui/core.js:72` (`util.icon`);
- `_ui_guard_helpers.py:361` (`classify_sinks`), `:489` (`extract_js_string_contents`, a joined blob);
- `test_ui_guards.py:97` (`DYNAMIC_SINK_BASELINE`);
- `test_ui_control_inventory.py` `test_inventory_rows_are_classified` (`len(cells) == 5`).

Design review (Developer, 2026-10-15): approve with changes. The capture tool was split to leg 03; the tokenizer rules, the table-header scoping and `icon` in `core.js` came from that review.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
