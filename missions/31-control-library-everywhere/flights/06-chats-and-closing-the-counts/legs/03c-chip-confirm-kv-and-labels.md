# Leg: chip-confirm-kv-and-labels

**Status**: ready
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Finish the library options that the chat migration needs, close two library squawks and apply D7:
- **`App.ui.chip`** gains a leading node (`lead`) and a library icon-only remove button (`onRemove` / `removeLabel`). These are the staged-image chip (A6) and the queued-message chip (A7), consumed in leg 05a.
- **`App.ui.confirm`** gains `onArmChange(armed)`. That retires the Chats list's per-row MutationObserver; the consumer change is in leg 05b.
- **`keyValueTable`:**
  - the remove button's accessible name follows an unsaved key rename (squawk 0269);
  - a re-baselining `setRow` clears the rename hint (squawk 0270).
- **D7: sentence case** for the agent and provider editors' labels, and the behavior specs that quote them.

## Context
- **Flight decisions:** DD6 (the option table), DD7 (D7; ledger rows 26 and 36), DD13 and DD15 (spec re-authoring).
- **`App.ui.chip`** (`js/ui/feedback.js:206-227`) takes `label` (required), `tone` (neutral, danger or warning), `size` ('sm'), `title`, `dataset` and `testid`, and returns a `span.chip` whose text is the label. It has no lead and no remove.
- **The two chat chips today:**
  - **The staged-image chip** (`chat.js` `buildAttachmentChip`, about `:237-270`, moving to `chat/attachments.js` in leg 02): a `span.chat-attachment.chip` with a thumbnail `img`, inline styles, and a `.chip-remove` "✕" button in danger colour (`.chip-remove`, `components.css:570-579`). The `.chip-remove` contrast gate is in `tests/test_design_tokens_a11y.py:402-431`.
  - **The queued-message chip** (`chat.js` about `:83-114`, moving to `chat/hold-queue.js` in leg 02): a "Queued:" label, the text, and a 22px "×" button with its own hover colours (`chat.css:651-657`).
- **The library's icon-only remove pattern** is the ghost small `App.ui.button` with the `x` icon, used by `App.ui.chipList` and `keyValueTable`'s remove. A6 and A7 match it.
- **`App.ui.confirm(itemEl, onConfirm, opts)`** (`js/ui/confirm.js:125-186`):
  - it arms by adding `.confirm-delete` and swapping a title node's text to `confirmLabel`;
  - it lapses on a timer (`lapse`, which adds `.confirm-lapsed`, reverts and announces);
  - it commits on a second click, calling `onConfirm(itemEl, revert)`.

  The Chats list (`chat.js:310-335`, construction, staying in `chat.js` after leg 02) watches `.confirm-delete` with one MutationObserver per row, so it can swap the delete action's `aria-label` between idle and armed. That observer is never disconnected. An `onArmChange(armed)` callback, fired on arm, revert, lapse and commit, lets the caller swap the label without watching classes. The consumer change and DD11 6 (offline delete) are leg 05b's.
- **`keyValueTable`** (`js/ui/key-value-table.js`):
  - **Squawk 0269:** `removeName(row, n)` runs only from `renumber()` (`:437-443`). `onInput` for the key column calls `checkRename` and `fire('input')` but never refreshes `row.remove`'s `aria-label` (`:181-192`). So after typing a new key, the button still reads "Remove {old key}".
  - **Squawk 0270:** `checkRename` sets the hint "Type the value again for the new name." (`:168`). After a Save with an empty value under a renamed sensitive key, `remaskAfterSave` (`studio/mcp-env-headers.js:236-262`) calls `table.setRow(idx, {value: mask, _originalMasked: mask})`. When nothing differs, `setRow` hits `continue` (`:529`) and never clears the hint, and the Show button lingers.

  Re-verify the line numbers; Flight 5 left these files stable.
- **D7.** The title-case strings, from a grep at design:
  - `general-tab.js:150` `'LLM Configuration'`;
  - `:172-173` `'System Prompt'` (title and label);
  - `:197` `'Chat History Retention (days)'`;
  - `:198` `'Max Iterations'`;
  - `provider-editor.js:177` `'Context Window'`, `:199` `'Reasoning Effort'`, `:225` `'Anthropic Account'`;
  - the server's provider-type label `the_one/interfaces/web/api.py:5465` `{"value": "openai-compatible", "label": "OpenAI-Compatible"}`.

  "Base URL" stays (URL is an acronym). The Developer greps once more for title-case labels, titles, placeholders and option text in both editors and their tab modules, and records the final list in the flight log.
  - **`provider-editor.js` has zero line headroom** (896/896). These edits are in place on the same lines. Add no net lines.
  - **Tests that read these strings** (grep at design): `tests/browser/test_flow_provider_editor.py`, `test_flow_agent_tabs.py`, `test_flow_studio_retention_error_message.py`, `test_ui_info_contract.py` and `test_ui_secret_input_contract.py` (check each: some may be fixtures with their own copy), plus any unit test on `/api/providers/types`.
  - **Behavior specs that quote them:** `studio-agent-crud.md`, `agent-retention-setting-roundtrip.md` (its intro and step 1, "Max Iterations") and `save-preserves-config.md` (steps 5-6, "Reasoning Effort"). Run logs under `runs/` are history and stay as written.
- **The section titles** may render uppercase through the eyebrow style (DD13 of M25 F6). The source string still changes to sentence case, which is what a screen reader reads and what the D7 decision names.

## Inputs
- Legs 03a and 03b landed.

## Outputs
- **`App.ui.chip({…, lead, onRemove, removeLabel, removeTestid})`:**
  - `lead` is a Node placed before the label (the thumbnail);
  - `onRemove` adds a trailing library icon-only remove button (ghost, small, `x` icon) named `removeLabel` (required with `onRemove`; for example "Remove image 1" or "Cancel queued message"), which calls `onRemove()` on click;
  - the chip stays a non-interactive `span`, and the button is its only control;
  - new owned classes (for example `chip-lead`, `chip-remove-btn`) go in the catalogue.

  The old `.chip-remove` rule stays until leg 05a moves its last user, then that leg deletes it and moves its contrast gate.
- **`App.ui.confirm` `onArmChange(armed)`:** called with `true` on arm and `false` on revert, lapse and commit, after the class change. It is documented in the catalogue's Confirm row. No caller changes in this leg.
- **`keyValueTable`:**
  - `onInput` on the key column refreshes `row.remove`'s name from `removeName(row, idx + 1)` (squawk 0269);
  - `setRow` clears the one-off rename hint (`ctl.setHint(null)`, and the Show button state with it) whenever the patch re-baselines the row (squawk 0270).

  Both squawks are closed in this leg's flight-log entry with their corrective action and verification (sign-off at the flight-end review).
- **D7:** the strings above in sentence case ("LLM configuration", "System prompt", "Chat history retention (days)", "Max iterations", "Context window", "Reasoning effort", "Anthropic account", "OpenAI-compatible"), plus any the final grep adds. Tests and the three behavior specs are re-authored to match.
- **Catalogue:** the Chip, Confirm and Key-value table rows.
- **Ledger rows 26 and 36** confirmed in the flight log, with the final D7 list.

## Acceptance Criteria
- [ ] **Chip (contract test, both engines):**
  - a chip with `lead` places the node before the label;
  - with `onRemove`, it has one button named `removeLabel` that calls `onRemove` on click and on Enter or Space, and is reachable by Tab;
  - without `onRemove` the chip is unchanged (same DOM as today);
  - `onRemove` without `removeLabel` throws.
- [ ] **Confirm (contract test, both engines):** `onArmChange` is called `true` on arm, `false` on lapse, `false` on the commit click and `false` when the caller's `revert` runs. A control with no `onArmChange` behaves as today.
- [ ] **Squawk 0269:** a contract test types into a key cell and asserts the remove button's name follows the typed key. A row with an empty key keeps the numbered name. An MCP editor test (`mcp` lane) shows the same for a header row.
- [ ] **Squawk 0270:** an MCP editor test renames a sensitive key, saves with an empty value, and asserts no rename hint and no Show button afterwards. A contract test covers `setRow` clearing the hint.
- [ ] **D7:** `git grep -nE "'(System Prompt|Max Iterations|Context Window|Reasoning Effort|Chat History Retention|Anthropic Account|LLM Configuration)'"` and `grep -n "OpenAI-Compatible" the_one/interfaces/web/api.py` find nothing. The re-authored tests pass, and the three behavior specs read the new labels.
- [ ] `tests/test_area_module_size.py` passes (`provider-editor.js` at most 896).
- [ ] **Guards:** `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`, `tests/test_ui_control_inventory.py`, `tests/test_ui_library_source.py`, `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass.
- [ ] **Lanes:** `contracts-controls` and `contracts-overlay` (`THE_ONE_REQUIRE_WEBKIT=1`), plus `mcp`, `mcp-connection`, `providers`, `agents`, `agent-tabs` and `chats`. Run them at most three at a time.
- [ ] `make test-unit` passes after the browser runs, and covers the `/api/providers/types` label change. `ruff` is clean.

## Verification Steps
1. The unit guards, plus `tests/` grep for the old strings.
2. `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-controls -x --tb=short`, then the area lanes.
3. `wc -l the_one/interfaces/web/static/js/areas/studio/provider-editor.js` (at most 896).
4. `make test-unit`; `ruff check`; `ruff format --check`.

## Implementation Guidance
1. **The `keyValueTable` squawks first,** tests first (contract, then MCP editor).
2. **The chip options** and their contract test.
3. **The confirm callback** and its contract test.
4. **D7:** grep, edit in place, retarget the tests, re-author the three specs.
5. **Catalogue and ledger,** then the lanes and `make test-unit`.

## Edge Cases
- **A chip's remove button inside a `role=log` transcript** (the queued chip sits above the composer, not in the log, which is fine). Its name must be specific, never just "Remove".
- **`onArmChange` and the lapse announcement:** fire the callback after the announcement is queued, so a caller changing labels does not interrupt it.
- **`setRow` with a stored key unchanged** (a plain value edit) must not clear a hint the user still needs. Clear it only when the patch re-baselines the stored key or value.
- **The `/api/providers/types` label** is read by the Library's Add menu and the provider editor's type select. Check the A-Z sort and any test that matches the label.
- **The eyebrow style** keeps uppercase display for section titles. A test reading `innerText` may see uppercase. Assert on `textContent`.

## Files Affected
- `the_one/interfaces/web/static/js/ui/feedback.js` (chip), `js/ui/confirm.js`, `js/ui/key-value-table.js`, `css/components.css`.
- `js/areas/studio/general-tab.js`, `js/areas/studio/provider-editor.js`, `the_one/interfaces/web/api.py` (one label).
- `tests/browser/test_ui_feedback_contract.py` (or the chip's contract file), `test_ui_confirm_contract.py`, `test_ui_key_value_table_contract.py`, the MCP editor test files (`mcp` lane), the D7-affected tests and a unit test for the label.
- `tests/behavior/studio-agent-crud.md`, `agent-retention-setting-roundtrip.md`, `save-preserves-config.md`.
- `docs/ui-control-inventory.md`, `squawks/0269-…`, `squawks/0270-…`, the flight log.

## Citation Audit
- `js/ui/feedback.js:206-227` (`App.ui.chip`) and `js/ui/confirm.js:125-186` (`App.ui.confirm`: `revert`, `lapse`, arm, commit). FD read.
- `general-tab.js:150`, `:172-173`, `:197-198`; `provider-editor.js:177`, `:199`, `:225`; `api.py:5465`. FD grep.
- `key-value-table.js:168`, `:181-192`, `:437-443`, `:529` and `mcp-env-headers.js:236-262`, from the reconnaissance report (code survey §7). Re-verify.
- `chat.js:310-335` (the per-row observer), from the code survey. It stays in `chat.js` after leg 02; re-verify there.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
