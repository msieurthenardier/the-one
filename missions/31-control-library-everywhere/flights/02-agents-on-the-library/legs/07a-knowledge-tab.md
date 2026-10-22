# Leg: knowledge-tab

**Status**: completed
**Flight**: [Agents on the library](../flight.md)

## Objective
Rebuild the agent editor's Knowledge tab from library controls: one `App.ui.toggle` per knowledge base (switch first, label beside), mounted once per agent identity and patched with `setAgent`. This closes squawk 0094 (the attach toggle cannot be reached by role or by Tab). `knowledge-tab.js` ends with zero sinks and zero allowance rows.

## Context
- **Flight decisions:** DD4 (the switch), DD6, DD7, DD10.
- **The leg-07 design review** (2026-10-21) split the old leg 07 into this leg and 07b (MCPs).
- **Legs 01-05 and 06a/06b have landed.** Read the flight log, 06a's identity and `patch` policy (this tab is on 06a's interim rebuild list until this leg), and the actual `App.ui.toggle` API (leg 05 included).
- **Today** (re-locate by symbol): `knowledge-tab.js` builds each row as `label` > `input.tool-toggle[data-kb-toggle]` + `span.tool-switch` + name, plus a tool-name span or placeholder from `agent.kb_tool_names`. The load-error and empty states are hand-built. `data-kb-list-loaded` gates whether `kb_ids` is sent.
  - `agent-form-data.js` reads `[data-kb-toggle]` `.checked` and `data-kb-list-loaded` (about `:268`, `:277`; re-locate).
  - `agent-model-picker.js` (about `:211`) wires change listeners by the `.tool-toggle` selector. Since 06a, the listeners are wired per panel at mount; confirm the Knowledge panel's switches fire dirty.
  - `.area-studio .tool-toggle{display:none}` (`studio.css:69`) removes these inputs from the accessibility tree: squawk 0094's cause.

## Acceptance Criteria
- [ ] **Each knowledge base is an `App.ui.toggle`** with the label "{kb name}", `dataset: {kbToggle: id}` on the **input** (`App.ui.toggle`'s `dataset` already applies to the native control), today's testid, and the tool-name text (`kb_tool_names`, or today's placeholder) as the toggle's hint or a sibling node kept as a handle.
- [ ] **States:** the load-error state is an `App.ui.status`, and the empty state is an `App.ui.emptyState` (`titleTag: 'p'`). Today's text and testids are kept. The `data-kb-list-loaded` semantics are preserved on the same element `agent-form-data.js` reads.
- [ ] **Squawk 0094:** each attach switch is reachable by `get_by_role('switch', name=<kb name>)` and by Tab, with Space toggling it. A test proves both, and the squawk is completed.
- [ ] **Patch-only:** the tab exposes `{setAgent(agent), destroy}`. `setAgent` sets each switch's checked state from `agent.kb_ids` and updates each tool-name node from `agent.kb_tool_names`, and it does not rebuild. The tab is removed from 06a's interim rebuild list. A test: attach a knowledge base, Save, and assert the tool-name text updates with no reload, and that the switch node is the same element (not rebuilt).
- [ ] **Form data:** for the same UI state, `kb_ids` sent on Save is identical to today's. A round-trip test pins it.
- [ ] **Zero:** `knowledge-tab.js` has no sinks and no allowance rows. Delete `.agent-knowledge-row-toggle` and the other Knowledge-only CSS only after grepping each class; `.tool-toggle`/`.tool-switch` stay for leg 08.
- [ ] **Tests:** `test_flow_studio_knowledge_attach.py` keeps passing. Where a test intends a user action, it uses clicks or Space on the now-visible switches instead of `evaluate` flips. The grep of `data-kb-*`, `.tool-switch` and `.tool-toggle` across `tests/` is listed in the log.
- [ ] **Captures:** `agent-knowledge` to `…/m31-f2-after-07a/`. The only difference is DD4 item 1, the switch.
- [ ] **Gates:** `make test-unit`; the static guards and ownership checks; the `agents` lane under netns.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/{knowledge-tab,agent-form-data,agent-editor-controller}.js` (the interim list), `css/studio.css`.
- `tests/browser/test_flow_studio_knowledge_attach.py` (plus new cases); `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py`.
- `squawks/0094-*.md`, `the_one/agents.md`.

## Citation Audit
From the leg 07 design review (2026-10-21, post-split tree). Re-locate by symbol.

## Design Review Addenda, cycle 2 (2026-10-21)
- **Datasets on the input:** `{kbToggle: '', kbId: id}`, because `agent-form-data.js` reads `[data-kb-toggle][data-kb-id]:checked` and `dataset.kbId`. The round-trip test attaches a knowledge base and asserts the stored `kb_ids`.
- **Dirty tracking (binding).** `wireEditorEvents` only listens to `.field-input`, `.field-textarea`, `.field-select` and `.tool-toggle`, so the new library inputs would not mark the form dirty. Each control's own `onChange` (`toggle`, `toolRow`, `groupTile` `master.onChange`) calls the editor's dirty callback directly, passed in through the tab's ctx. A test checks that clicking a switch or checkbox enables Save and shows `.editor-unsaved`. It uses a real click, not an `evaluate` flip.
- **The list of knowledge bases refreshes only on remount** (a different agent or a reload). A knowledge base added in the Library while the same agent stays open appears after the next remount. This is recorded, not fixed.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
