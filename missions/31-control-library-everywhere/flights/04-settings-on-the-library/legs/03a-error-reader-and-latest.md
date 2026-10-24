# Leg: error-reader-and-latest

**Status**: landed
**Flight**: [Settings on the library](../flight.md)

## Objective
Give the app one error reader and one "latest request wins" helper:
- `App.api.fetchJson` errors also carry `status` and the raw `detail`;
- a new `App.api.fieldErrors` maps a 422 to fields, with one message humaniser;
- a new `App.ui.util.latest()` helper.

Then move the knowledge editor's four `_errorMessageFromResponse` callers onto `fetchJson` and delete that function, and write the error-placement rule down.

## Context
- **Flight decisions:** DD3, DD11 and DD12. DD12 does not apply: no owned class is added.
- **Flight 3 debrief recommendation 4:** three error readers in one editor (`fetchJson`; raw `fetch` plus `_errorMessageFromResponse`; raw `fetch` plus "HTTP N"), five copies of "latest request wins", and error placement split between field and header.
- **Additive by design.** `fetchJson`'s thrown message must not change: `test_flow_studio_mcp_editor.py:1626` and `test_studio_mcps_tab.py:559` pin "Server error 500 …", and 33 call sites read `err.message`. Only properties are added.
- **The `loc` rule (DD3, corrected at Architect cycle 2):** drop a leading `"body"` segment, then take the first segment that names a field in `names`. The real shapes:
  - `PUT /api/tools/configs/{name}`: `loc` such as `["path_denylist", 0]` → `path_denylist`;
  - `PUT /api/knowledge-settings`: the handler calls `ChunkingSettings.model_validate` by hand, so `loc` is `["size_chars"]`;
  - the knowledge overlap check is a model validator, so `loc` is `[]` (unmatched, editor level);
  - a string `detail` (a shape error, or a plain `HTTPException`) is unmatched.

  Verify each shape against `the_one/interfaces/web/api.py` and record them in the leg's tests.
- **The humaniser** (A11, ledger row 11) maps Pydantic v2 `msg` text to plain sentences. At least these:

  | Pydantic `msg` | Plain sentence |
  |---|---|
  | "Input should be greater than or equal to N" | "Must be N or more" |
  | "Input should be greater than N" | "Must be more than N" |
  | "Input should be less than or equal to N" | "Must be at most N" |
  | "Input should be less than N" | "Must be less than N" |
  | "Input should be a valid integer…" | "Must be a whole number" |
  | "Input should be a valid number…" | "Must be a number" |
  | "String should have at least N characters" | as is |
  | "Value error, …" | the text after "Value error, " |

  Anything unknown passes through unchanged. Both copies of `humanizeValidationMsg` (`tools-editor.js:669-677`, `tools-form-helpers.js` about `:559-567`) stay until leg 07a moves the tools editor onto the reader. This leg only provides it.
- **The editor-level text when fields matched:** built from the unmatched rest only, never from `err.message`. When nothing matched, `err.message`.
- **`latest()`** sits beside `mountSlot` in `js/ui/core.js` and returns `{next() -> token, isCurrent(token), invalidate()}`:
  - `next()` makes every earlier token stale;
  - `invalidate()` makes every token stale (for a teardown).

  It is a helper, not a control: a note in the catalogue's helpers list (like `mountSlot`, `docs/ui-control-inventory.md:123`) and contract tests in `tests/browser/test_ui_library_contract.py`, in both engines.
- **The knowledge callers.** After leg 02b, the four callers are in `knowledge-folders.js`/`knowledge-rows.js` (remove file, delete folder, add folder) and `knowledge-inspect.js:146` (chunks or source). Behaviour notes (DD3, Architect M3):
  - **remove file:** a 404 still counts as success (already gone). Use `err.status === 404`.
  - **The fallback texts change:** "HTTP N", "Remove failed" and "Folder registration failed" become `fetchJson`'s "Server error N …" when the body has no `detail`. That is a ledger row (43). Update or add tests that pin the new text.
  - **The Add-folder error stays on the folder-path field** (`knowledge-folders.js` about `:871`, a field-placed request error). That already follows the rule: a 422 naming the path is a validation error on its field. Keep it.

## Inputs
- Legs 02a and 02b landed (the knowledge callers live where 02b put them).
- `js/api.js` (52 lines); `knowledge-shared.js:26` `_errorMessageFromResponse` and its export at `:121`.

## Outputs
- `js/api.js`:
  - `fetchJson` attaches `err.status` (number), `err.detail` (the raw parsed `detail`: string, array or undefined, kept in its own variable before the message is flattened) and `err.body` (the raw text), with the message unchanged;
  - `App.api.fieldErrors(err, names)` returns `{fields: {name: message}, rest: [message…], text: string}`;
  - `App.api.humanizeMessage(msg)`;
  - header comments updated.
- `js/ui/core.js`: `App.ui.util.latest()`.
- The knowledge callers on `fetchJson`; `_errorMessageFromResponse` removed from `knowledge-shared.js` and its export.
- Tests:
  - `tests/browser/test_ui_library_contract.py` (`latest`, both engines);
  - a new `tests/browser/test_ui_api_errors.py` for `fetchJson`/`fieldErrors`/`humanizeMessage`, run in a page with routed responses, both engines, in the `contracts-controls` lane (add its glob if that lane is an explicit list; check `scripts/run-tests.sh`);
  - knowledge tests updated for the fallback texts.
- Docs:
  - `the_one/agents.md`: a "Errors and late responses" section with the DD3 placement rule, the reader, `fieldErrors`, the humaniser and `latest()`;
  - `docs/ui-control-inventory.md`: a helper note for `latest()`;
  - CLAUDE.md's "Control library" paragraph: one sentence.
- Ledger row 43 (the knowledge fallback texts).

## Acceptance Criteria
1. **`fetchJson`'s message is byte-identical to today** for every case: a string `detail`, an array `detail`, a non-JSON body, an empty body. A test per case asserts message, `status` and `detail`.
2. **`fieldErrors`** maps each real shape in Context to the right field or to `rest`. A test per shape uses response bodies copied from the real API. One check proves the tools shape against the real server: a `TestClient` call in a unit test, or a captured body recorded in the test with its provenance.
3. **`humanizeMessage`** maps each listed pattern, and passes unknown text through unchanged. Tested.
4. **`latest()`:** `next()` invalidates earlier tokens; `invalidate()` invalidates all; tokens from two helpers are independent. Contract-tested in Chromium and WebKit, and in the catalogue's helpers list.
5. `git grep -n "_errorMessageFromResponse\|errorMessageFromResponse" the_one/` returns nothing.
6. **The knowledge editor's behaviour holds,** apart from the ledger row:
   - a 404 on remove file removes the row (its existing test passes);
   - each failure path still shows its error in the same place;
   - the `knowledge` lane passes.
7. **The placement rule is written down** in `agents.md`, with the editor-level text built from the unmatched rest when fields matched.
8. The unit tier, the static guards, and the `knowledge`, `contracts-controls` and `mcp` lanes pass. The `mcp` lane covers the two "Server error 500" pins.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_ui_control_inventory.py tests/test_store_static.py -q -x --timeout 120`.
- Lanes `contracts-controls`, `knowledge` and `mcp` with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`.
- `git grep` for criterion 5.
- `make test-unit` once.

## Implementation Guidance
1. Read `js/api.js`, `ui/core.js` (`mountSlot`), the four knowledge callers, and the two pinned tests.
2. Extend `fetchJson` additively, then add `fieldErrors` and `humanizeMessage`, test-first against the real shapes.
3. Add `latest()` and its contract tests.
4. Move the knowledge callers, one at a time, each with its test passing.
5. Write the docs.

## Edge Cases
- **`fetchJson` on a 204 or an empty 2xx body:** today it calls `r.json()`. Don't change success-path behaviour.
- **A `detail` array item without `loc` or `msg`** is skipped safely.
- **`names` matching:** exact segment equality, never a substring. Today's `applyModelLevelHighlights` substring match is what DD3 retires.

## Files Affected
- `static/js/api.js`, `static/js/ui/core.js`, `static/js/areas/studio/knowledge-shared.js`, `knowledge-folders.js`, `knowledge-rows.js`, `knowledge-inspect.js`.
- `tests/browser/test_ui_library_contract.py`, `tests/browser/test_ui_api_errors.py` (new), knowledge browser tests, `scripts/run-tests.sh` (lane glob, if needed).
- `the_one/agents.md`, `docs/ui-control-inventory.md`, CLAUDE.md, the flight log.

## Citation Audit
Checked at `512616b`:
- `js/api.js:20-45` `fetchJson` (message resolution, `throw new Error(detail || 'Request failed')`): verified (FD read).
- `knowledge-shared.js:26`, `:121`: verified (FD grep).
- Callers `knowledge-inspect.js:146`, `knowledge-folders.js:445` (`'HTTP ' + r.status`), `:521` (`'Remove failed'`), `:854` (`'Folder registration failed'`): verified (FD grep). These move in 02b; re-locate them.
- `docs/ui-control-inventory.md:123` `mountSlot` helper note: verified.
- `tests/browser/test_flow_studio_mcp_editor.py:1626`, `tests/browser/test_studio_mcps_tab.py:559`: verified (FD grep).

## Design Review Amendments (cycle 1, 2026-10-23)
These override anything above they contradict.
- **The test file is `tests/browser/test_ui_api_errors.py`**, so it lands in `contracts-controls` (`test_ui_*` minus the overlay list). The inventory guard checks only `App.ui.<factory>(` calls, so a `test_ui_` name is safe.
- **`tests/browser/test_ui_library_contract.py:70`** pins `Object.keys(App.ui.util).sort()`. Add `latest` in sorted order (`…"icon", "latest", "mountSlot"…`). Leg 03b adds `syncChildren` to the same line.
- **`err.detail` is the raw parsed `detail`.** Keep the parsed array in its own variable before flattening. The array case asserts `err.detail` is the array while `err.message` is still `"loc: msg | loc: msg"`. Also pin the empty-body non-2xx text as it is today.
- **`fieldErrors` output format.**
  - Each `rest` item is the humanised `msg` with **no** `loc` prefix.
  - `text` joins `rest` with a space between sentences. Each sentence ends with a period, and none is added if it already has one.
  - `fields` hold humanised messages.
  - Name matching compares `String(segment)` for exact equality, never a substring. Only the first segment that names a field counts. A test where `names` has `size` and the loc segment is `size_chars` proves there is no substring match.
  - A non-`fetchJson` error (a network `TypeError`) returns `{fields: {}, rest: [], text: err.message}`. It never throws.
  - Example: the real overlap body `{loc: [], msg: "Value error, overlap_chars (900) must not exceed 50% of size_chars (1000)"}` → `text` "overlap_chars (900) must not exceed 50% of size_chars (1000)."
- **Humaniser regexes** are anchored prefixes, and handle a negative or float N ("-1", "0.5").
- **Remove file, the 404 path.** The success body becomes one named function, called from `.then` and from a `.catch` that checks `err.status === 404`. Both check `isCurrent()` first. `DELETE …/items/{id}` returns a JSON body (`api.py` about `:2127`).
- **The fallback texts** (ledger row 43) also mean a non-JSON error body (an HTML 500 page) now shows up to 500 characters of it, in the header or the folder field. Record that in row 43. **No existing test pins** "HTTP N", "Remove failed" or "Folder registration failed", so **add a test per caller** with routed 500s and empty bodies: remove file (non-404), delete folder, add folder (on the field), and chunks or source load.
- **The orphan aliases go too:** `var _errorMessageFromResponse = K.errorMessageFromResponse;` in `knowledge-folders.js`/`knowledge-rows.js` (after 02b) and `knowledge-inspect.js:30`, and `agents.md` (about `:2150`) where it lists the helper.
- **`knowledge-search.js` (about `:126`)** is raw `fetch` plus `'Search failed: HTTP ' + r.status`. Move it to `fetchJson` in this leg too (same file family; the same fallback-text ledger row).
- **`latest()` tokens are opaque** (stated in the catalogue note); tests never depend on their type.
- **Lanes to run:** `contracts-controls`, `knowledge`, `mcp`. `shared` is not needed now that the file is named `test_ui_*`.

## Design Review Amendments (cycle 2, 2026-10-23)
- **Every `fetchJson` error case** asserts `err.body` (the raw text), as well as `message`, `status` and `detail`.
- **"Value error, " is stripped before** the `text` period rule applies.
- **`knowledge-search.js`** keeps its own `generation` counter in this leg. It moves only to `fetchJson`, not to `latest()` (recorded choice: legs 07b, 09 and 10 pilot `latest()`).
- **Ledger row 43** names every changed fallback text: "HTTP N", "Remove failed", "Folder registration failed" and "Search failed: HTTP N".
- **The remove-file `.catch` rethrows** when `err.status !== 404`, so a non-404 failure still reaches the error path.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
