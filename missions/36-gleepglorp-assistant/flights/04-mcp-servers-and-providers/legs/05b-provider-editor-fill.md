# Leg: 05b-provider-editor-fill

**Status**: completed
**Flight**: [MCP servers and model providers](../flight.md)

## Objective

GleepGlorp can fill the model provider editor, new and existing, as unsaved edits, including a
type change. A fill never carries a key:
- a fill that moves a provider to a **different key-taking type** clears the editor's key field,
  so the old key is never sent to the new service;
- a fill of a key-taking type leaves the key for the operator.

An open provider editor follows an approved provider proposal without a reload, and never
overwrites unsaved edits. Provider proposal cards show their options and warnings.

## Context

- **Flight DD10, the operator decision of 2026-11-21** (type changes allowed, with a warning),
  **and Leg 5a's decision 2** (the type-change table) are the authority. The patterns are
  **Leg 4b's**, as landed, with its twelve binding resolutions: the `kept` contract, `setType`,
  `fill_view` stale, the applier reading `view.values`, and the rest.
- **Depends on Leg 5a** (the `provider` kind with `fillable = ()`, `PROVIDER_TYPE_DEFAULTS`,
  warnings, and `card_extras`) and **Leg 4b** (`normalize(mode=)`, the generalized `fill/tool.py`
  and `fill_view`, the card row and footer rendering, `mcp-kinds.js` as the registration
  pattern).
- **The provider editor today** (survey, 2026-11-21):
  - **Structure.**
    - `renderProviderEditor` (`provider-editor.js`) keeps a per-mount handle `h` in a module
      `slot` that is not exported.
    - Fields carry `data-field`, and dirty tracking compares a `getFormSnapshot(h)` JSON. The
      setters exist only for the key (`h.secret.setValue`).
    - The type select's change handler toggles rows, **resets `base_url` to the type default**,
      relabels the key row, and calls `checkDirty`.
  - **The save body.**
    - It clones the mounted `provider.config` and overlays the shown fields.
    - The key goes as `__MASKED__` when unchanged, or `null` when empty.
  - **Out of scope for fills.**
    - The Anthropic sign-in section sits outside the dirty machinery. In create mode it
      auto-saves before sign-in. A fill never touches it.
    - The models panel dispatches on the **saved** type at mount, and has no fillable fields.
  - **Create, then edit.** After Create Save, `providers-section.js` `onSaveSuccess` re-renders
    the form into edit mode.
  - **No refresh path.** An open editor never refreshes when its provider changes. The
    `'providers'` store subscriptions refresh only the list.

## Inputs

- Legs 4a, 4b and 5a landed, uncommitted.
- `areas/studio/provider-editor.js`, `providers-section.js`, `provider-models.js`,
  `studio-subscriptions.js`; `mcp-editor-fill.js`, `mcp-editor-follow.js` and `mcp-kinds.js`
  (the 4b patterns); `gleepglorp-kinds.js`; `proposal-cards.js`; `approvals.js`.
- **Tests:** `tests/browser/seeders.py` (`seed_gleepglorp_fill` with `target_id`), the
  `conftest.py` provider fixtures (`app_with_provider`, the openrouter and ollama seeders),
  `test_flow_provider_editor.py` (`_seed_anthropic_provider`), and the 4b fill test helpers.

## Outputs

**Server**
- **`kinds/provider.py` `fillable = ("create", "change")`.** Its `normalize(mode="fill")` allows
  what Leg 5a's decision 2 allows for fills:
  - a key-taking to different key-taking change;
  - a create or change into `anthropic-plan-token`.

  A fill still never carries `api_key` or `secrets` (they are `operator_only`). `mock` is still
  refused.
- **The fill's view carries `clears_key: true`** when the fill is a key-taking to different
  key-taking type change, so the client knows to clear the key field. It is computed on the
  server, from the stored type and the fill's type.
- **`fill_view`** for `provider` change fills takes the title and `target_gone` from
  `card_extras`, and `stale` from the provider service's public stale alias, labelled, as Leg
  4b did for MCP.
- **`fill/tool.py`'s description** names `provider`, within 90 tokens and the character pin.
  Draft and measure it first, and stop if it cannot fit.

**Client**
- **Editor handles.** The provider controller exposes `ready()`, `values()`, `baseline()`,
  `setType(type)`, `setField(key, value)`, `clearKey()`, `placeNote(key, el)`, `rebase(provider)`
  and `checkDirty()`.
  - **`setType`** sets the select's value and runs **the same code as the change handler** (row
    visibility, the `base_url` default reset and the key relabel), with no `change` event
    dispatch side effects beyond what the handler does. A type the operator already changed is
    kept (the kept rule).
  - **`setField`** covers `name`, `base_url` (only when the type shows it), `num_ctx`,
    `thinking_enabled` and `reasoning_effort`.
  - **`clearKey()`** empties the key input (`h.secret.setValue('')`), so Save sends `null`.
  - Each handle is silent; the caller calls `checkDirty()` once.
- **`areas/studio/provider-editor-fill.js`** (new), mirroring `mcp-editor-fill.js`:
  - the allowlist `name`, `type`, `base_url`, `num_ctx`, `thinking_enabled`, `reasoning_effort`;
  - writes in this order: type, then fields, then `clearKey()` when `view.clears_key`, then
    `checkDirty`;
  - the kept rule;
  - a note under each filled control;
  - a note under the key field when the key was cleared or must be entered: "Enter the key for
    this type." (the per-field note slot);
  - the settle wait, which never waits for the models panel, and the dev-mode timeout seam.
- **`areas/studio/provider-editor-follow.js`** (new), on `CONFIG_CHANGED` with
  `kind === 'provider'` and the open edit editor's `target_id`:
  - fetch the provider and update the section's `editing` object;
  - rebase per field: a clean field takes the new value, a dirty field is kept with its baseline
    moved;
  - update the title on a rename;
  - draw the follow note and call `checkDirty`;
  - defer while a Save is in flight.

  A **type change by approval** re-renders the editor as a fresh mount if the editor is clean.
  If it is dirty, the follow note says "This provider's type changed; Cancel to see it", and no
  rebase runs: a type switch rebuilds the rows, and merging dirty fields across types is out of
  scope.
- **`areas/studio/provider-kinds.js`** (new), registered after `mcp-kinds.js`:
  - `labels`: "model provider", "The model provider editor could not open.", "That model
    provider no longer exists.";
  - `openLink`: `{destination: 'library', section: 'providers', id}`, text "Open model
    provider", testid `proposal-open-item`;
  - `store: 'providers'`;
  - `recordKey`: by `target_id`, or `null`;
  - `fill`: the spec, with `exists` from the `providers` store.
- **Cards.** Provider options show as rows (Context size, Thinking, Reasoning effort). Warnings
  go in the footer, which works already via 4b.

## Acceptance Criteria

- [ ] **AC1. Server.**
  - **Fill mode allows:** a key-taking to different key-taking change, and a create into
    `anthropic-plan-token`.
  - **Propose mode refuses both** (Leg 5a's tests are unedited).
  - **Every mode refuses:** `api_key` and `secrets` (operator-only) and `mock`.
  - **`clears_key`:** set exactly on key-taking to different key-taking changes.
  - **`fill_view`:** title, `target_gone` and labelled `stale` for provider change fills.
  - **The description:** at most 90 tokens and within its character cap, naming `provider`.
  - **Pins:** `FILLABLE` and the enum are updated.
- [ ] **AC2. Editor seam.**
  - `setType('ollama')` on a create form shows Context size, hides the key, and sets the default
    URL, exactly as a manual change does.
  - `clearKey()` empties the key.
  - Nothing saves, opens sign-in, or fetches models (shown by the request counter).
- [ ] **AC3. Create fill.** An `anthropic` provider fill with name and thinking opens
  `#library/providers/~new`. It sets the type (base URL hidden at its default), the name and
  thinking, with notes and the key note "Enter the key for this type.". The unsaved caption
  shows. Nothing is stored. The receipt reads filled.
- [ ] **AC4. A change fill across key-taking types** (`anthropic` to `openai` on an existing
  provider with a stored key):
  - the type switches, and the key field is **empty**, with its note;
  - Save without typing a key stores `api_key` null, and the old key is not sent;
  - Cancel restores the stored type and the masked key.
- [ ] **AC5. A change fill that stays on its type** (`thinking_enabled` and `reasoning_effort`
  only) leaves the key masked. Save keeps the stored key.
- [ ] **AC6. Dirty-state navigation.**
  - **Same route, dirty:** a field the operator changed is kept, and the receipt names it with
    a 200 outcome.
  - **Other route, dirty:** the leave guard asks. Choosing Stay means not filled.
- [ ] **AC7. Follow-through.**
  - Approving a `provider` option change for the open provider updates the clean fields without
    a reload. A dirty field is kept. A later Save does not undo the change.
  - A type change by approval re-mounts a clean editor, and gives a dirty editor the "Cancel to
    see it" note.
  - An approval for another provider changes nothing.
  - At least one follow test runs a **real Approve**, through `seed_gleepglorp_proposal` and the
    approve route, not only `App.approvals.record`.
- [ ] **AC8. Card.** A provider proposal card shows the option rows and the footer warnings (for
  example the type-change warning with the agent count). "Open model provider" links to
  `#library/providers/{id}` after apply, for a create as well as a change.
- [ ] **AC9. Registration.** `App.gleepglorpKinds.names()` gives five kinds. The kinds browser
  test's names, shapes and order are updated.
- [ ] **AC10. Accessibility.** Notes are linked to their controls by `aria-describedby`. The key
  note is linked to the key input. No live region announces values. The static guards pass.
- [ ] **AC11. No regression.**
  - These lanes pass, one at a time: `gleepglorp`, `providers` and `library`.
  - The agent and MCP fill and follow tests pass unedited.
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes with 15 skips.
  - The new browser files are in the `gleepglorp` lane list, and
    `tests/test_run_tests_lanes.py` is updated.

## Verification Steps

- **Unit:** `.venv/bin/python -m pytest tests/test_gleepglorp_kind_provider.py tests/test_gleepglorp_fill_*.py tests/test_gleepglorp_kinds.py -x --timeout 60`.
- **Browser:** new `tests/browser/test_flow_gleepglorp_fill_provider.py` and
  `test_flow_gleepglorp_follow_provider.py`, in the `gleepglorp` lane.
- **Lanes,** one at a time in the background, then the unit tier.

## Implementation Guidance

1. **Server** (AC1). Draft and measure the description first.
2. **The editor seam** (AC2). Refactor the type-select change handler's body into a function
   that both the handler and `setType` call. Expose `h` through the controller, not through a
   global.
3. **`provider-editor-fill.js` and `provider-kinds.js`** (AC3-AC6, AC9).
4. **`provider-editor-follow.js`** (AC7).
5. **Card option rows** (AC8).
6. **Accessibility, docs** (`the_one/agents.md`; the guide `model-providers.md` if the fill
   wording changed), **lanes and the unit tier** (AC10, AC11).

## Edge Cases

- **A fill into `anthropic-plan`:** the key row hides. GleepGlorp's reply says to sign in after
  Save, and the fill never starts sign-in.
- **A fill on a create form whose type the operator already chose:** the type is kept, and the
  fields for that type are written where they apply.
- **A fill naming `base_url` for a hidden-URL type:** refused at `normalize` (Leg 5a), so it
  never arrives.
- **The provider used by GleepGlorp itself:** the fill is allowed. The receipt and the reply
  carry the warning.

## Files Affected

- **Server:** `the_one/gleepglorp/kinds/provider.py`, `fill/tool.py`, `fill/store.py`, and the
  provider service's public stale alias.
- **Client:** `provider-editor.js`, `providers-section.js`; new `provider-editor-fill.js`,
  `provider-editor-follow.js` and `provider-kinds.js`; `proposal-cards.js` (option rows, if
  needed); `static/index.html`.
- **Tests:** the new browser files, `test_flow_gleepglorp_kinds.py`, and the pins.
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py`, `the_one/agents.md`, the guide.

## Design Review

Cycle 1 (Developer, Sonnet): **approve with changes.** These FD resolutions **bind over any
earlier text in this leg:**
1. **`clears_key`.** It is computed on the server from the fill's `base["type"]` and
   `changes["type"]`, with `provider_service.takes_key`, not from a view-time row read. It is true
   when the type changes **and** either the new type has **no key row** (`ollama`,
   `anthropic-plan`) or both are key-taking and different. This closes the case where a fill to
   `ollama` silently kept the old key (5a decision 2: "into `ollama`, the key is cleared"). AC1
   and AC4 test both, and AC4 gains an `anthropic` → `ollama` variant (Save stores `api_key`
   null).
2. **The kept rule for the key and the URL.**
   - If the operator changed the type (kept), the fill does not change the type, and `clearKey`
     does not run.
   - If the operator typed into the key field (dirty), `clearKey` does not run. The key note
     reads "Check the key for this type." `kept` stays limited to the fill's own stored keys
     (Leg 4b resolution 1), so the key is never in `kept`.
   - The apply-type step keeps an operator-edited `base_url` when the new type shows the URL
     field. When the new type hides it, the default applies, as the editor does today.
3. **Cancel.** The type-select handler's body is extracted into `applyType(h, type)`, called by
   the handler, by `setType` **and by Cancel**. Cancel therefore restores row visibility, the
   key label, placeholder and help, and the expiry line. This also fixes an existing manual
   bug. Cancel also clears the fill record and notes. AC4 asserts row visibility and the key
   label after Cancel.
4. **The controller.** It lives in a new `provider-editor-controller.js`, because
   `provider-editor.js` is at 862 of the 895-line ceiling (`tests/test_area_module_size.py`).
   - `renderProviderEditor` returns the controller, which exposes:
     - the members in Outputs;
     - `id`, `isCreate`, `alive()`, `saving()` and `onIdle(fn)`;
     - `placeFollowNote(el)` and `destroy()`.
   - `providers-section.js` captures it on each mount and exposes it through
     `attach(() => current)`, as `mcp-glue.js` does. Any new section call goes through `ctx`
     (the module's divert rule), and the Developer lists the calls added.
   - A create → edit remount clears the fill record.
   - `tests/test_store_static.py`'s literal lines in `provider-editor.js` (the `'providers'`
     invalidations; `var method = isEdit ? 'PUT' : 'POST';` …
     `callbacks.onSaveSuccess(updated, !isEdit)`) stay byte-identical.
5. **`rebase(provider)`** refreshes:
   - the editor closure's `provider`, since `collectFormData` clones its `config`;
   - `originalMaskedApiKey` and the expiry row;
   - the per-field snapshot;
   - the delete widget's provider and `h.danger.dataset.name`;
   - the title and subtitle.

   On a rename it calls `App.router.sync(..., {name})`. AC7 adds: Save after a follow sends the
   approved values (checked in the stored row).
6. **Fill-time warnings, for MCP servers and providers both.** `fill_view` gains `warnings`
   through the kind's `warnings` (adapted to accept a `Fill`), for pending fills. The
   `fill_form` reply text appends them. This delivers the type-change, agent-count, "GleepGlorp
   uses this provider" and sign-in warnings at fill time, and closes DD9's "fill warnings in the
   tool result" for MCP, which Leg 4b did not wire. Tests cover both kinds.
7. **The description.** The `fill_form` character cap rises deliberately from 360 to **440**,
   with the token cap kept at 90. Update `FillFormTool.summary` and the docstring to match. This
   is provisional platform text: per the flight plan (DD12), the eval measurement and compare
   happen in Legs 6 and 7, the same deferral as Legs 4a, 4b and 5a.
8. **Pins** (each updated, none weakened):
   - `tests/test_gleepglorp_kind_provider.py:154` (5a's not-fillable assertion; "5a's tests are
     unedited" applies to its propose-mode refusal tests);
   - `tests/test_gleepglorp_kinds.py:82` (`FILLABLE`);
   - `tests/test_gleepglorp_fill_tool.py:79` (the enum) and the character pin;
   - `tests/browser/test_flow_gleepglorp_kinds.py` (names ~:108, shapes ~:114, a `providerKinds`
     slot in script order);
   - `tests/browser/seeders.py::seed_gleepglorp_fill`, generalized to use `kinds.target_key` for
     every kind that has `resolve_target`;
   - the guide `model-providers.md` (596 of 600 words; trim to make room) and
     `tests/test_gleepglorp_guide.py`.
9. **`fill_view` gets a provider branch** next to `mcp_server`'s. `stale` comes from
   `provider_service.stale_fields(current, changes, base)` (already public) via
   `provider._load(conn, None, id)`, labelled and in display form, matching `_mcp_stale`.
10. **The real Approve in AC7** uses a change `change_provider` accepts: an option change, or a
    keyless ↔ key-taking change (key-taking ↔ key-taking is refused on approve). The seeded
    `base` matches the row exactly. A deliberately mismatched seed checks the stale path.
11. **An option the chosen type does not show** (for example `thinking_enabled` on a kept
    `ollama` type) is skipped, and is in neither `written` nor `kept`. The receipt counts only
    written fields. `setField` maps the stored names (`num_ctx`) to `data-field` names
    (`config.num_ctx`). `written` and `kept` use stored names, and never `api_key`.
12. **Wording.**
    - The field labels are "Context window" and "Extended thinking"; tests use these.
    - For `anthropic-plan-token`, the key note reads "Enter the token from `claude
      setup-token`."
    - The follow note gets a distinct testid (`provider-approved-change-note`), registered in
      `docs/ui-testid-registry.md`.
    - A failed types fetch makes `ready()` false, and `whenSettled` resolves false.
13. **Type change by approval with a dirty editor:** the "Cancel to see it" note is enough. It
    does not name fields.

The FD made these calls without a second cycle. They decide the reviewer's questions and fix
the specifics; the leg's shape is unchanged. The Batch B review covers the result.

## Citation Audit

From the provider survey (2026-11-21), to be re-checked after Leg 5a lands:
- `provider-editor.js:59` `renderProviderEditor`; `:84` `checkDirty`; `:275` the type change
  handler (row visibility, the `base_url` reset, the key relabel); `:774` `getFormSnapshot`;
  `:789` the masked-key save; `:540-772` sign-in — verified (survey).
- `providers-section.js:53-70` `TYPE_DEFAULTS`; `:157` `onSaveSuccess` (create to edit) —
  verified (survey).
- `provider-models.js:96`, dispatching on the saved type at mount — verified (survey).
- `studio-subscriptions.js:46,55`: the `'providers'` subscriptions refresh the list only —
  verified (survey).
- Leg 4b's landed `mcp-editor-fill.js`, `mcp-editor-follow.js` and `mcp-kinds.js` — the patterns.
