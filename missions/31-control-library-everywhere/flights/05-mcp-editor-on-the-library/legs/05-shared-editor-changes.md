# Leg: shared-editor-changes

**Status**: completed
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Make three library changes that reach every editor, before the MCP editor moves onto the shell:
- the `editorShell` error moves out of the button cluster onto its own full-width row (A1);
- an `editorShell` `setTestState({disabled, label})` (DD4: a Test held for a consent poll survives a dirty change);
- sentence-case danger-zone buttons in the provider, connector and knowledge editors (B7).

## Context
- **Flight decisions:** DD7 (A1 and B7, with the pins listed there; ledger rows 1, 28 and 36), DD4 (`setTestState`), DD10 (derived-relationship and degenerate-input criteria; retarget pins, never relax them; no consumer CSS on library internals).
- **The shell today** (`js/ui/editor.js` `App.ui.editorShell`, about `:68-215`):
  - **The default variant:** `div.editor-header` is a flex row of `div.editor-header-text` (breadcrumb, title, subtitle) and `div.form-actions` (unsaved caption, extra, Cancel, Save, Test, then `span.editor-error` last).
  - **The page variant** puts the same cluster into `App.ui.pageHeader`'s actions slot.
  - `.form-actions` is `flex-shrink: 0` (`css/components.css:1286-1291`), so a long error squeezes the title column to nothing (survey A1, `ref-provider-long-error` capture).
  - The error's colour and size rule is `.form-actions .editor-error` (`components.css:1292-1295`).
  - `apply()` sets `testButton.disabled = busy`, so `setDirty` re-enables a Test the caller disabled.
- **Who uses the shell:** `tools-editor.js:153`, `agent-editor.js:167`, `knowledge-settings-page.js:82` (the page variant), `knowledge-create.js:41`, `provider-editor.js:100`, `knowledge-detail.js:67`, `connector-editor.js:312`. The MCP editor joins in leg 10. Until then its hand-built header keeps `.form-actions .editor-error`, so that selector stays styled until leg 10 deletes it (DD7).
- **Pins on the error's place** (DD7, Architect M5):
  - `tests/browser/test_ui_editor_contract.py:74-80` and `:271-274`;
  - `tests/browser/test_ui_page_header_contract.py:150` and `:221`;
  - `tests/browser/test_flow_provider_editor.py:134` and `:145` (`.form-actions .editor-error`);
  - `tests/test_design_tokens_a11y.py:471-477` (the contrast rule body for `.form-actions .editor-error`);
  - the knowledge tests' `_HEADER .editor-error` locators, which keep resolving if the row stays inside `shell.el`.
- **B7 labels:**
  - `provider-editor.js:248` "Delete Provider";
  - `connector-editor.js:598` "Delete Connector";
  - `knowledge-detail.js:296` "Delete Knowledge Base";
  - the MCP editor's "Delete MCP Server" (leg 10, through `dangerZone`);
  - the armed label is already the library's "Confirm delete?" in these editors.
- **Not in B7 as approved:** the agent editor's "Delete Agent" (`general-tab.js:220`). The FD has asked the operator whether it joins. **Change it only if the flight log records the operator's yes**; otherwise leave it.
- **The danger zone's title** defaults to "Danger Zone" (`editor.js` `dangerZone`). CSS shows it in capitals, so a sentence-case default ("Danger zone") changes only what a screen reader reads. It goes with B7 as a source-text fix, recorded in the ledger as no visible change.
- **Tests and specs that read the labels:**
  - `tests/browser/test_studio_connector_editor.py`, `test_flow_studio_knowledge_inventory.py`, `test_flow_provider_editor.py`, `test_ui_confirm_contract.py`, `test_ui_editor_contract.py`, `test_ui_secret_input_contract.py` (check which hits are the labels);
  - if the agent label changes, also `test_flow_agent_crud.py`, `test_flow_agent_general_tab.py` and `test_flow_studio_purge_now_button.py`;
  - the behavior specs `tests/behavior/system-provider-config.md` (`:75`, `:79`, `:80`; and, if the agent label changes, `studio-agent-crud.md` and `agent-purge-now-clears-history.md`). Amend the spec texts, never the old run logs.

## Inputs
- Batch B1 committed. Legs 03 and 04 may be in the same working tree; this leg touches `js/ui/editor.js`, `css/components.css`, the three editors' danger labels and their tests, with no overlap with leg 03's MCP files or leg 04's table files (`components.css` is shared with leg 04: edit different blocks only).

## Outputs
- **`js/ui/editor.js` `editorShell`:**
  - **The error row** (reworked at the leg's design review):
    - **Placement.** The error (`errorEl`, the same `span.editor-error`, now also carrying the shell-owned marker class `ui-editor-error-row`) leaves `.form-actions` and becomes the last child of the header element (`shell.el`): `div.editor-header` in the default variant, and the page header element in the page variant. The shell adds the shell-owned class `ui-editor-shell-header` to that element.
    - **CSS, scoped to that class:** `flex-wrap: wrap; row-gap: 0` (the column gap is kept). The row is `flex: 0 0 100%; display: block; overflow-wrap: anywhere`. `App.ui.pageHeader` itself and every Settings page header outside the shell are unchanged.
    - **An empty row takes no height and adds no gap.** `setError` sets `data-empty` (the banner `live` precedent; never `hidden` or `display: none`, so a role=alert region stays in the tree). The row's top spacing applies only to `:not([data-empty])`. No `:empty` selector, so stray whitespace cannot break it.
    - **No movement without an error.** Removing the empty span from the cluster would move Cancel, Save and Test 8 px right (the cluster's `gap: 8px` trailed the empty span). The shell compensates (`.ui-editor-shell-header .form-actions { margin-right: 8px }`, with a comment saying why), so the no-error layout is pixel-identical.
    - **Long text** wraps on the row and never narrows the title column or the cluster.
    - **Locators keep resolving.** Because the row stays inside `.editor-header` (default variant), `_HEADER .editor-error` (the knowledge tests), `.studio-editor .editor-error` (`test_flow_studio_knowledge_attach.py:708`) and the bare `.editor-error` locators (`test_flow_provider_focus_after.py`, `test_flow_provider_visible_fixes.py`, `test_flow_provider_plan_signin.py`, `test_flow_studio_tools_fields.py`, `test_flow_studio_retention_error_message.py`) keep resolving. A run of their lanes proves it.
    - **Callers are unchanged.** `errorEl` is the same element, so the caller-set `data-testid` in `knowledge-settings-page.js:94-102` still works.
  - **`setTestState({disabled, label})`:**
    - `apply()` becomes `testButton.disabled = busy || testHeld`, so a held Test stays disabled across `setDirty` and `setBusy` until `setTestState({disabled: false})`;
    - `label` replaces the visible label's text node only, so the play icon survives, as `setSaveLabel` does, and any `aria-label`; `null` restores the configured label;
    - on a shell with no `actions.test`, it is a no-op, not a throw;
    - the default is no hold and no relabel, so the tool editor's `actions.test` path is unchanged.
- **`css/components.css`:**
  - the rules above, under `.ui-editor-shell-header` and `.ui-editor-error-row`, both owned by the editor-shell catalogue row;
  - the colour and size in **one** shared declaration, `.form-actions .editor-error, .ui-editor-error-row { color: var(--status-danger); font-size: var(--font-size-body-sm); }`. The legacy selector is kept until leg 10 for the MCP header, with a comment saying so (DD7), and leg 10 drops it.
- **The labels:** "Delete provider", "Delete connector", "Delete knowledge base" (and "Delete agent" only on the operator's yes).
- **The danger title:**
  - the `dangerZone` default becomes "Danger zone";
  - `provider-editor.js:246` passes `title: 'Danger Zone'` explicitly and is edited to match;
  - the connector, knowledge and agent editors (`general-tab.js:217`) use the default, so the agent editor's title source text changes too. That is not visible (CSS shows capitals), and it is accepted as part of this source-text fix;
  - the MCP editor's hand-built "Danger Zone" stays until leg 10, deliberately.
- **`docs/ui-control-inventory.md`:** the editor-shell row (the error row, `setTestState`) and the danger-zone row (the default title).
- **Tests:**
  - **contract tests** (`test_ui_editor_contract.py`, `test_ui_page_header_contract.py`), both engines:
    - the error is a full-width row below the title and the cluster; a 400-character error wraps, the title keeps at least its no-error width, and the breadcrumb does not wrap word by word (compare bounding boxes with and without the error, at 1024 and 1280);
    - an empty error row adds no height;
    - `role=alert` is still on the element;
    - the page variant does the same;
    - `setTestState` survives `setDirty(true)`, `setDirty(false)` and `setBusy`, and restores the label;
  - **the pins listed in Context**, retargeted to the new place (never deleted):
    - `test_ui_editor_contract.py:74-80` (`actKids` drops `SPAN.editor-error`, and a new assertion puts it last in the header);
    - `test_ui_page_header_contract.py:150` and `:221`;
    - `test_flow_provider_editor.py:134` and `:145` (to `.editor-header .editor-error`).
    - Not pins: the hand-written legacy harness at `test_ui_editor_contract.py:265-276`, and `test_agents_chat_action.py:60` and `test_flow_agents_list.py:642` (which read the cluster's first children).
  - **the contrast pin** (`test_design_tokens_a11y.py:471-477`) reads the shared declaration, so the shell's real rule is pinned, and the legacy selector stays pinned until leg 10;
  - **the label tests** retargeted:
    - `test_flow_provider_editor.py:298`, `:323`, `:354` (and the comments at `:281`, `:296`), plus the title at `:241`;
    - `test_studio_connector_editor.py:338`;
    - `test_flow_studio_knowledge_inventory.py:232`, `:1504`, and the title at `:613`;
    - `test_ui_editor_contract.py:353` (the library default title);
    - check `test_flow_studio_purge_now_button.py`;
    - the synthetic harness labels in `test_ui_editor_contract.py`, `test_ui_confirm_contract.py` and `test_ui_secret_input_contract.py` may stay;
  - **a derived-relationship check** that each danger button's accessible name equals its visible label;
  - **a no-error geometry check** (contract test, both engines, at 1024 and 1280): the header's height and the title's and cluster's rects are identical to the shell without the change. A fixture copy of today's rules is acceptable, or a measured constant;
  - **an empty-row check:** the empty row adds no height, measured on the **header**, not the row, with and without `errorRole`.
- **Captures:** retake `ref-provider-long-error`, `ref-provider-danger-armed`, `ref-connector-danger-armed`, the `kb-danger-armed` surface and one Settings editor with an error (`settings-knowledge-invalid` or the tool editor's error surface). Compare with the before sets. Each difference must be A1's row or B7's label (ledger rows 1, 28 and 36) and nothing else.

## Acceptance Criteria
- [ ] **A1 on every shell editor:** a long error never narrows the title or the cluster, at 1024 and 1280, in both engines (contract tests), and the provider capture with the injected long error shows the title intact.
- [ ] **No layout change without an error:** in every capture above, nothing moves while the error is empty (`ImageChops` on the no-error surfaces, `provider-edit-*` and `connector-edit`, shows no difference).
- [ ] **`setTestState`** behaves as specified (contract tests).
- [ ] **B7:** the three labels are sentence case, and the agent label changes only with the operator's recorded yes. The danger title's source text is "Danger zone".
- [ ] **Tests and specs:**
  - every listed pin is retargeted, with no test deleted or loosened;
  - the lanes `providers`, `library`, `knowledge`, `settings`, `settings-tools` and both contracts lanes (`THE_ONE_REQUIRE_WEBKIT=1`) pass, plus `agents` and `agent-tabs` if the agent label changes;
  - the behavior spec texts are amended.
- [ ] **Guards:** the catalogue, ownership and emitted-class guards pass (any new class owned; no allowance row added); the static JS/CSS guards, `tests/test_design_tokens_a11y.py` and `make test-unit` pass.

## Verification Steps
- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_editor_contract.py tests/browser/test_ui_page_header_contract.py -x --timeout 60`.
- The lanes listed above, at most 3 at a time, never alongside the unit suite. These are six lanes, which is most of a parallel run. Running `--parallel 3` across all lanes instead is acceptable, and quicker to read.
- The captures listed in Outputs, compared with `m31-f5-before` (the reference surfaces) and Flight 4's `m31-f4-after` (the Settings and knowledge surfaces), or a fresh `main` set.
- `git grep -n "Delete Provider\|Delete Connector\|Delete Knowledge Base" the_one/ docs/ tests/behavior/*.md` finds nothing, and the product tests listed above no longer assert the old labels. The synthetic contract-harness labels may remain. `the_one/agents.md` mentions are updated.
- `.venv/bin/python -m pytest tests/test_ui_control_inventory.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -q -x --timeout 120`, then `make test-unit`.

## Implementation Guidance
1. **Contract tests first,** for the error row (the bounding-box comparison, no-error geometry, empty-row height) and `setTestState`.
2. **The shell change, its CSS and the catalogue rows together,** so the guards pass at each step; then retarget the pins.
3. **B7's labels and the danger default title;** then the label tests and the behavior specs.
4. **Lanes, captures, catalogue rows and the flight log** (the ledger rows' status).

## Edge Cases
- **An error set while the form is dirty:** the caption and the error must not overlap. The caption stays in the cluster.
- **The tool editor's Test button** (`tools-editor.js`) uses `actions.test`. Make sure its existing busy behaviour is unchanged by `setTestState`'s default.
- **The knowledge-settings page variant** has Cancel and Save in the page header: its error row goes under the whole page header.
- **RTL is not in scope** (the app is LTR only).
- **A 400-character unbroken error string** wraps (`overflow-wrap: anywhere`).
- **`errorRole` unset:** no `role=alert`, and the empty row still collapses.
- **A page-variant error with a caller-set `data-testid`** (`knowledge-settings-page.js`).
- **The shell header below 1024** may now wrap the cluster under the title instead of overflowing. Below the supported minimum, that is accepted.

## Files Affected
- `the_one/interfaces/web/static/js/ui/editor.js`, `css/components.css`.
- `js/areas/studio/provider-editor.js` (the label and the explicit title), `connector-editor.js`, `knowledge-detail.js` (and `general-tab.js` only on the operator's yes).
- `the_one/agents.md` (any label mentions).
- `docs/ui-control-inventory.md`.
- The tests named in Context; the behavior specs named in Context; the flight log.

## Citation Audit
- `editor.js` `editorShell` (the `apply()` Test line; `errorEl` appended last to the cluster), `dangerZone` (the default title). FD read at `ebf3ef6`.
- `components.css:1286-1295`. FD read.
- The shell's users and the labels: `git grep` at `ebf3ef6`. The pins: from DD7 (Architect cycle 1), with `test_flow_provider_editor.py:134, :145` and `test_design_tokens_a11y.py:471-477` re-checked by grep.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (2026-10-25): approve with changes**, applied in place:
  - an empty row adds no height (`row-gap: 0`, `data-empty`) (H1);
  - the 8 px cluster shift compensated, so the no-error layout stays pixel-identical (H2);
  - the page variant's wrap scoped to the shell's own class, with `pageHeader` unchanged (H3);
  - a no-error geometry check (M4); the missing locators and pins listed (M5);
  - one shared colour declaration for the contrast pin (M6);
  - the explicit provider title and the title tests (M7); the label tests' real lines and the scoped grep (M8);
  - `setTestState` details (L9); edge cases (L10).
  - The FD calls on the review's questions: the no-error captures must be pixel-identical; the page wrap is scoped; the agent label waits for the operator, and the default title's source text reaching the agent editor is accepted.
  - These are clarifications and decisions, not a change of design, so there is no second cycle. Status `ready`.
