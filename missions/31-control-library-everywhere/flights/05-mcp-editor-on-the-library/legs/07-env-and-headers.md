# Leg: env-and-headers

**Status**: completed
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Move the MCP editor's environment variables and headers onto `App.ui.keyValueTable`'s secret and toggle columns (leg 04), as a DOM-built module with handles. Keep the server's secrets contract exactly (DD5). Fix defect 4 (re-mask after Save) and show B5 and defect 15 in the editor. Then delete the last legacy switch and the `.mcp-kv-*` rules.

## Context
- **Flight decisions:**
  - DD5 (the contract; the client rules for the Save and Test bodies; B5; the key-rename rule; re-mask after Save by key; the Security Reviewer);
  - DD7 (A11-A13; ledger rows 11-13, 26, 35);
  - DD9 (defects 4, 11, 15);
  - DD10, DD11 (the legacy switch and the `.mcp-kv-*` rules go here);
  - DD12 (the behavior spec `mcp-sensitive-headers-round-trip`, drafted here and run in leg 12).
- **The server contract** (`the_one/interfaces/web/api.py::update_mcp_source`, about `:3143-3245`):
  - for a key in `secrets`, a masked value (`__MASKED__` or the GET mask shape, `_looks_masked`) keeps the stored secret when the key exists and is dropped otherwise; any other value overwrites;
  - **a key omitted from `secrets` is deleted;**
  - the OAuth-managed keys are pinned;
  - `config` is replaced, apart from `_cache`.
  - `POST .../test/connect`'s override path recognises only the literal `__MASKED__` (about `:3804`).
  - GET returns masks shaped `***...tail`.
- **Today** (`mcp-env-headers.js`, after leg 06):
  - `collectExistingKvRows(source, type)` builds `{key, value, sensitive, _originalMasked}` rows: plaintext first, then secrets, plaintext winning on a duplicate key;
  - `renderKvTable` and `renderKvRow` produce strings (the masked tail sits in `value=` and `data-original-masked=` attributes);
  - `handleSensitiveToggle` and `partitionKvRows` (the `__MASKED__` rule: sensitive, an original mask, and a value equal to it), with `wire` for the events and Add row, and `nextRowIdx`;
  - `setType(type)` (from leg 06) swaps the title and hides the section for A17.
  - The controller still reads the kv rows by class in `getFormSnapshot` (about `:303-317`), `collectFormData` (through `partitionKvRows`) and `revertEditorToSource` (the `tbody.innerHTML` rebuild, about `:657-665`), and excludes `.kv-key-input`/`.kv-value-input` from `attachStaticListeners`.
- **The library** (leg 04):
  - `App.ui.keyValueTable` columns: `text`, `secret` (`maskedBy`, `storedKey`, `clearOnUnmask`), `toggle` (`ariaLabel`, `inputTestid`); `keyColumn`; `setRow(i, patch)` merges, never fires `onChange`, keeps focus;
  - `removeLabel(n, row)`; `label` (the table's `aria-label`, set at creation); `testid`, `addTestid`, `onChange(values, {type})`;
  - the secret input's stored mode, with the hint and every edit replacing the mask; the rename hint.
  - The table has no label setter. A type switch therefore rebuilds the table with the current `values()` (focus is on the Type select at that moment). No library change is needed.
- **The legacy switch's last user** is the Sensitive switch on each row. Its pins:
  - `tests/test_design_tokens_a11y.py:579-581, 633-643`;
  - `tests/browser/test_deep_violet_computed_styles.py:48-49`;
  - `tests/browser/test_ui_tile_contract.py:681` (legacy markup in a fixture);
  - `tests/browser/test_flow_studio_mcp_editor.py:729-748`.

  Its catalogue row is "Legacy toggle 1". Its rules are `css/studio.css` about `:1268-1340`. The `.mcp-kv-*` and `.kv-remove-row-btn` rules are about `:410-448`. Re-check the line numbers at the start.

## Inputs
- Legs 03-06 landed (leg 06 gives `envHeaders.setType` and `mount.onDestroy`). The batch B2 checkpoint is committed.

## Outputs
- **`mcp-env-headers.js`** becomes `App.studio.mcpEditor.envHeaders.create({source, type, onChange})`, which returns `{el, values(), isDirty(), revert(), setType(type), partition(plaintextDict, secretsDict), remaskAfterSave(submitted, response), destroy()}`:
  - **Row identity:** every row carries a stable `_rid`, a non-column key the module assigns when a row is created. It round-trips through `values()`, `setValues` and `setRow`, and survives removals and additions, so nothing is matched by index alone.
  - **It keeps its own baseline rows** (cycle 1 H1 and H2, made precise at cycle 2):
    - each baseline row is `{_rid, key, value, sensitive, _originalMasked}`, with `value = _originalMasked = mask` for a stored secret;
    - `isDirty()` compares **by `_rid`**, on `key`, `value` and `sensitive` only. It is dirty when a row's fields differ, or when the set of `_rid`s differs (a row added or removed). Order never matters;
    - **at mount**, the baseline is the rows built from `source`;
    - **after a Save**, once `remaskAfterSave` has run, the baseline is the **live** rows, except a row edited during the request, which keeps its submitted values in the baseline (so it stays dirty). Nothing is rebuilt from the response, so server reordering, trimmed keys and rows the server never saw (blank keys) cannot leave the form dirty;
    - `revert()` (Cancel) sets the table to the baseline rows: a just-saved secret stays (in stored mode), and a deleted or renamed key does not come back. The controller's closure `source` is still stale for the other fields until leg 10 (defect 3); this module does not depend on it;
    - **the controller's dirty state** is its own snapshot (which excludes the kv rows) **or** `envHeaders.isDirty()`, in every place it is computed: `checkDirty`, `recaptureSnapshot`, and the Save success path (today's `dirty = false; applyButtons(); reportDirty(false)` at about `:505-508` changes);
    - Cancel's order is `envHeaders.revert()`, then `recaptureSnapshot`, then the focus restore to the title.
  - **`el`** is an `App.ui.section({layout: 'stack', testid: 'mcp-env-headers-section'})` titled "Environment variables" (stdio) or "Headers" (HTTP) (A3), holding one `App.ui.keyValueTable`:
    - `label` the same as the title (A11), `testid: 'mcp-kv-table'`, `addTestid: 'kv-add-row-btn'`, `keyColumn: 'key'`;
    - the columns:
      - `{key: 'key', label: 'Key', placeholder: 'KEY', mono: true}`;
      - `{key: 'value', label: 'Value', type: 'secret', maskedBy: 'sensitive', storedKey: '_originalMasked', clearOnUnmask: true}`;
      - `{key: 'sensitive', type: 'toggle', label: <"Sensitive" plus an App.ui.infoButton>, ariaLabel: 'Sensitive'}`;
    - A13's info text: "Sensitive values are stored encrypted. Turning this off clears the stored value; type it again to keep it.";
    - `removeLabel(n, row)`: "Remove {KEY}", or "Remove row n" for an empty key.
  - **`setType`** swaps the title and rebuilds the table with the current rows (with their `_rid`s) under the new label. The old table node is replaced in place inside the section, never appended, and `onChange` stays wired. It hides the section for `''` (A17). After a type switch, `isDirty()` keeps comparing against the baseline; the controller's static snapshot already marks the type change dirty.
  - **`partition`** reads `values()`:
    - an empty trimmed key is skipped;
    - a sensitive row whose value equals its `_originalMasked` sends `__MASKED__`;
    - **a sensitive row with an empty value sends `''`, as today** (the cycle 1 "sends nothing" rule is withdrawn at cycle 2: silently dropping the key surprised more than an empty stored secret does). After a rename with no retype, the old key is omitted, so the server deletes it, and the new key is stored with an empty value;
    - any other sensitive row sends its value;
    - a plain row goes to the plaintext dict (an empty plain value is sent as `''`, as today);
    - for duplicate keys the last row wins, as today;
    - **`partition` also records what it sent per row:** `{_rid → {key, sentValue}}`, stashed by the controller at the Save click for `remaskAfterSave` and the post-Save baseline;
    - the mask shape is never sent;
    - Save and Test already share this path (`runTest` → `collectFormData` → `partition`), so there is no `forTest` option; test 8 pins the Test body;
    - managed OAuth keys are never present (they are stripped on GET).
  - **`remaskAfterSave(submitted, response)`** (defect 4; `submitted` is `partition`'s per-row record from the Save click):
    - for each submitted row, found **by `_rid`** in the live table (a row removed during the request is skipped), and only for the row that won in `partition` for a duplicate key:
      - if its key is in `response.secrets`, it is still sensitive, and its live key and value still equal what was sent (or it was sent as `__MASKED__` and its value still equals its `_originalMasked`), call `setRow(index of that _rid, {value: mask, _originalMasked: mask})`;
      - if it was sent as `__MASKED__` but its key is **not** in `response.secrets` (the server dropped it), call `setRow(…, {_originalMasked: ''})`, so it leaves stored mode;
    - a row edited during the request, an empty-key row, and a row never sent are left alone;
    - then take the post-Save baseline as described above.
  - **`setValues`** never fires `onChange`. Cancel uses it.
- **The controller:**
  - the env and headers string, the `nextRowIdx`/`wire` call, and the kv parts of `getFormSnapshot`, `collectFormData` and `revertEditorToSource` are replaced by the handle;
  - the `.kv-*` exclusions in `attachStaticListeners` go;
  - **Save's success path, in this order:** `envHeaders.remaskAfterSave`, then the controller's snapshot (which excludes the kv rows), then `reportDirty(controllerDirty || envHeaders.isDirty())`;
  - Cancel calls `envHeaders.revert()`;
  - **target:** the controller at 760 lines or fewer (as after leg 06), and lower if the kv sites free more;
  - the sinks go: `tmp.innerHTML = renderKvRow`, the two `eyeBtn.innerHTML`, `btn.innerHTML` (the eye), `tbody.innerHTML`;
  - the controller shrinks and stays at 800 lines or fewer.
- **Deleted:**
  - **the `.tool-enable-switch*` rules in `studio.css`**, after leg 06 moved the second user (`mcp-sandbox-fields.js`) onto `App.ui.toggle`. The pins:
    - `tests/test_design_tokens_a11y.py:579-583` and `_ON_TRACK` / `_FILL_SITES` at `:638-644` read those `studio.css` rules by selector. They are retargeted in their own step to `App.ui.toggle`'s rules in `components.css`, keeping every contrast pair;
    - the frozen copy in `tests/browser/_legacy_tool_css.py:365-440` is kept only if a remaining test reads it; otherwise its switch part is deleted, with the reason in the leg's flight-log entry;
    - the fixture at `test_ui_tile_contract.py:681` is frozen or retired, with a reason;
    - the comments and docs naming the switch are updated: `components.css:329` and `:2449` ("intentional duplicates until Flight 5"); `the_one/agents.md:1914`, `:2308`; the testid registry's rows for `approval-mode-toggle-btn` and `self-configuration-toggle-btn`; the comments in `test_flow_admin_tools_editor.py:8` and the `test_studio_self_configuration_*` files;
  - the "Legacy toggle 1" catalogue row;
  - the `.mcp-kv-*` and `.kv-remove-row-btn` rules;
  - the `.mcp-kv-th-sensitive .field-info-icon` rule at `studio.css:427`, which is inside the deleted `.mcp-kv-*` range, and its allowance row. The `.field-info-icon` rule in `components.css:275` stays;
  - the hand-built secret-input notes in the catalogue (rows 45 and 58: `mcp-env-headers.js` is no longer a hand-built copy).
- **Testids:**
  - kept: `mcp-kv-table` and `kv-add-row-btn`; added: `mcp-env-headers-section` (registry row);
  - retired: `mcp-kv-tbody`, `mcp-kv-thead` and `mcp-kv-sensitive-info`, in `docs/ui-testid-registry.md` (about `:272-275`) **and** in `RETIRED_SELECTORS` in `tests/test_nav_helper.py`, whose test pins the two together;
  - the thead assertions at `test_flow_studio_mcp_editor.py:644, :664` become `table.locator("thead")` hidden or visible.
- **Guards:** every sink and ownership use the module and the controller held for this surface is removed, with the totals lowered and the move entries retired or removed. No new use.
- **Tests** in `tests/browser/test_flow_studio_mcp_editor.py` (lane `mcp`), the security ones written first and run against today's tree:
  - **the payload round trips**, each asserting the stored row through the API (`GET /api/mcp-sources/{id}`). Sources with secrets are seeded by a direct `POST /api/mcp-sources` with `type: streamable-http`, `config.headers` and `secrets` (`seeders.seed_mcp_source` is stdio-only with empty secrets), or a new seeder parameter;
    1. create a source with a sensitive header **through the UI**, then reload and Save: the secret is in `secrets` (masked on GET) and not in `config.headers`;
    2. reload: the row shows stored mode (no eye, the hint);
    3. change only the name and Save: the secret is kept (`__MASKED__` sent);
    4. retype the value and Save: it is replaced, verified by the mask's tail changing, using two secrets with distinct last four characters;
    5. untick Sensitive on the stored row and Save: the key is gone from `secrets`, and `config.headers[key]` is `''` (the cleared value, sent as plaintext), never mask text;
    6. rename the key on a stored row: the value clears and the hint asks again. Save without retyping: `secrets` no longer holds the old key, and the new key is stored with an empty value. It holds no `__MASKED__` and never the old secret (defect 15; fails first on today's tree, where the secret is silently lost under the new key);
    7. **defect 4, failing first, in edit mode** (seed through the API with no secret, then add the row in the editor): Save a newly typed secret. After the Save the row is in stored mode, because `remaskAfterSave` set `_originalMasked`. Then untick Sensitive, which clears the value (`clearOnUnmask`), then Save. Today the secret moves into plaintext `config.headers`; after the fix the plaintext value is `''`;
    8. **the Test body** (a pin; it passes today): with `page.route` on `**/test/connect` returning a stub, the body for a dirty form with a stored secret carries `__MASKED__`, never `***`;
    9. **Cancel after a Save** (H1): Save a new secret, edit another row, Cancel. The saved secret's row is still shown in stored mode, and a key deleted before the Save does not return;
    10. **an edit during an in-flight Save** (H2): hold the PUT, edit a row, release. The edit is kept and the form stays dirty;
    11. **clean after Save** (cycle 2): after a Save in each of these cases, the form reads clean (Save disabled, no "Unsaved changes" caption):
        - a rename with no retype;
        - a new sensitive row left empty;
        - an untouched blank Add row;
        - a key typed with surrounding spaces;
        - plain and secret rows in an order the server returns differently;
    12. **a cleared stored value** (cycle 2): clear a stored secret's value (stored mode replaces the mask) and Save. The key is stored with an empty value, as today, and the row shows the empty value, not stored mode. The flight log records this unchanged behaviour;
  - **"no attribute holds a secret"** in the live editor: after load and after typing, no attribute in the editor subtree contains the mask tail or the typed value;
  - **A11-A13:**
    - the table's name matches the section title;
    - the Sensitive column header's accessible name is exactly "Sensitive". The info button's description must not join the header's text: place the button so its description is not in the header's name, and assert it;
    - each row's controls name their row (and the remove button names the key);
    - the eye has `aria-pressed`;
    - Sensitive is `role=switch`;
    - the info button is a press-only toggletip;
    - no sideways scroll at 1024 (A12, `scrollWidth <= clientWidth` on the section);
  - **the retargeted pins:** the roughly 29 `.mcp-kv-*` and `.kv-*` selector lines move to the table's testids, roles and names.
- **`tests/behavior/mcp-sensitive-headers-round-trip.md`** (new, DD12), drafted per `.flightops/ARTIFACTS.md`'s behavior-test format and the CLAUDE.md "Behavior-test credential convention":
  - a dedicated dev instance on port 8486 or higher, with a scratch data dir under `$HOME`;
  - a browser apparatus;
  - steps 1-6 above as Action / Expected Result rows, observed both in the UI and through the API.

  It is run in leg 12.
- **Captures:** the MCP surfaces with the table (`mcp-edit-stdio`, `mcp-edit-http`, `mcp-create-*`, at 1280 and 1024), compared with the leg 06 set. Differences map to ledger rows 11, 12, 13, 26 and 35 only.

## Acceptance Criteria
- [ ] **Payload tests 1-12 pass.** Tests 6, 7, 9 and 10 fail on the leg 06 tree first, and the flight log records each failure and its reason. Tests 8 and 12 are pins that pass today. Test 11 is new behaviour (the module baseline) and is recorded either way.
- [ ] **No attribute holds a secret** (tested), and the Test body never carries the mask shape (tested).
- [ ] **A11-A13, B5 and defect 15** behave as specified in the editor (tested).
- [ ] **The legacy switch is gone:** `git grep -n "tool-enable-switch" the_one/interfaces/web/static/` finds nothing, and its pins are retargeted, not deleted. The catalogue row is removed.
- [ ] **The `.mcp-kv-*` rules are gone,** and `git grep -n "mcp-kv-\|kv-remove-row-btn\|kv-key-input\|kv-value-input\|kv-sensitive" the_one/interfaces/web/static/` finds nothing.
- [ ] **Lanes and files pass:** `mcp`, `library`; both contracts lanes (`THE_ONE_REQUIRE_WEBKIT=1`); `test_studio_mcps_tab.py`; `test_deep_violet_computed_styles.py`; `test_ui_tile_contract.py`; the unit tier, including `test_design_tokens_a11y.py`.
- [ ] **The captures differ only on the listed ledger rows** (FD-checked).
- [ ] **Guards:** totals lowered, no stale move entry, every `mcp-*.js` file at 800 lines or fewer, the static guards and `make test-unit` pass.
- [ ] **The behavior spec is drafted** and validates against the format in `.flightops/ARTIFACTS.md`.

## Verification Steps
- The payload tests first on the leg 06 tree: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_flow_studio_mcp_editor.py -k "payload or secret or sensitive" -x --timeout 60`.
- The greps above. For each deleted class, grep `tests/` and run the owning lane (DD10).
- The lanes and files above, at most 3 at a time, then `make test-unit`.
- The capture compare against the leg 06 set.

## Implementation Guidance
1. **Tests 1-8 first,** with the attribute scan. Record which fail today and why.
2. **The module:** the section, the table, `partition`, `remaskAfterSave`, `setType`, `setValues`.
3. **The controller:** the host, the handle in the per-mount `handles`, snapshot, collect and revert through it, the Save success path, and removing the sinks and exclusions.
4. **The deletions,** with their pins, the catalogue and the registry.
5. **The behavior spec draft, the guards, the lanes, the captures and the ledger.**

## Edge Cases
- **A duplicate key** in plaintext and secrets: plaintext wins on load (today's rule). Two UI rows with the same key: last wins in `partition`, as today; keep that.
- **A type switch with rows entered:** the rows move with it (env becomes headers), as today, through the table rebuild.
- **A stored mask of `***`** (no tail): stored mode works. Leg 04 tested it.
- **Save while a row is being edited:** that row keeps its new value and stays dirty; `remaskAfterSave` skips it.
- **The server reorders rows** (plaintext first, then secrets), and the UI order stays as the operator left it until the next load.
- **The Security Reviewer** (DD5): the batch review for this leg uses the Sonnet tier with a secrets-focused brief.
- **A typed secret that looks like a mask** (`***` or `***...abcd`) matches the server's `_looks_masked`, so the PUT silently keeps or drops it. The Test override only knows the literal sentinel. This is a known limitation, outside this leg (it is the server's contract): record it in the flight log for the debrief, as a squawk candidate.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/mcp-env-headers.js`, `mcp-server-editor.js`; `css/studio.css`.
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`.
- `tests/browser/test_flow_studio_mcp_editor.py`, `test_deep_violet_computed_styles.py`, `test_ui_tile_contract.py`; `tests/test_design_tokens_a11y.py`; the guard tables.
- `tests/behavior/mcp-sensitive-headers-round-trip.md` (new); the flight log and ledger.

## Citation Audit
- `mcp-env-headers.js` (`collectExistingKvRows` `:20-48`, `partitionKvRows` `:176-200`, `wire` `:205`) and the controller's kv sites (about `:303-317`, `:328`, `:371`, `:657-665`): FD read on the leg 04 tree. Leg 06 edits the controller, so re-locate them at the start.
- The `keyValueTable` API: `js/ui/key-value-table.js` header comment, read after leg 04 landed. The `api.py` contract lines are from the flight's citation audit (`:3143-3245`, `:3804`).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (2026-10-25): approve with changes.** Applied in place:
  - the module keeps its own baseline, so Cancel after a Save shows the saved rows (H1);
  - kv dirtiness through `isDirty()`, so an edit typed during an in-flight Save stays dirty (H2);
  - `remaskAfterSave` eligibility and duplicate keys spelled out; the dead `forTest` dropped (M);
  - empty sensitive values send nothing, with test 5's and test 6's expected payloads stated (M);
  - every legacy-switch user, pin and doc hit listed, with the contrast-pin retarget as its own step (M);
  - `RETIRED_SELECTORS` and the registry (M);
  - test seeding and feasibility (L); the mask-shaped-input limitation recorded (L); the Sensitive header's accessible name (L).
  - **FD decisions:** Cancel restores the last saved rows; an empty secret is never sent; the form is not locked during a Save.

  Substantive, so a second cycle follows.
- **Developer design review, cycle 2 (2026-10-25): approve with changes.** Applied in place:
  - a stable `_rid` per row, and the post-Save baseline taken from the live rows (minus rows edited during the request) rather than from the response, so the form is clean after a Save (H);
  - the baseline's contents and comparison specified (H);
  - the empty-sensitive rule withdrawn, so today's `''` behaviour is kept, with tests 6 and 12 stating the payload (M);
  - `remaskAfterSave` by `_rid`, using `partition`'s per-row record, and clearing stored mode when the server dropped a key (M);
  - the `setType` rebuild and the dirty computation in `checkDirty`, `recaptureSnapshot` and the Save path (M);
  - the test 7 explanation and the Cancel order (L).

  This was the last of two cycles. Status `ready`.
