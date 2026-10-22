# Leg: rules-and-notes-tab

**Status**: ready
**Flight**: [Agents on the library](../flight.md)

## Objective
Move the Rules and notes tab's remaining hand-built pieces onto the library:
- status and alert lines;
- empty states;
- the `.ui-toggle` class query.

The tab keeps its save-immediately behaviour and stays outside the General form's Save and leave guard. `rules-notes-tab.js` ends with zero sinks and zero allowance rows.

## Context
- **Flight decisions:** DD6 (mount once, patch), DD7 (Rules and notes), DD10.
- **Leg 05** already removed this tab's local arm announcement in favour of the shared confirm live region.
- **Today** (planning survey, at `dbcd458`):
  - `rules-notes-tab.js` (883 lines) is mostly on the library: `App.ui.textarea`, `button`, `toggle` and `badge` (about `:154-433`, `:566`, `:594`).
  - Still outside the library:
    - `role=status`/`alert` lines (about `:234-245`, `:619-627`);
    - the empty states `rules-empty`, `notes-empty` and the create-mode `empty-state` (about `:446`, `:797`, `:870-874`);
    - a `.ui-toggle` class query (about `:341`);
    - "Clear all" through `App.confirmDialog` (about `:844`), which **stays**: it is the library modal adapter (DD7).
  - The tab saves immediately (header `:10-14`).
  - Tests: `test_flow_agent_rules.py` (13), `test_flow_agent_notes.py` (13). Leg 05 retargeted the old "Press Delete again" assertions to `ui-confirm-live`.
  - The chat drawer's read-only Rules and Notes groups (`areas/chat/agent-drawer.js`) are **out of scope**: they belong to Flight 5. They read the same data and must keep working.

## Acceptance Criteria
- [ ] **Leave the interim rebuild list, with no `setAgent`** (design review, 2026-10-21). The tab reads nothing from the agent record that a same-identity General Save can change: it keys only on the agent's name, and a rename is a new identity, which remounts. So the tab declares **no** `setAgent`. Leg 06a's patch loop skips a tab without one, and this leg removes the tab from the interim rebuild list (and from Cancel's rebuild). A test pins it: type text into the Add-rule textarea (unsaved), edit the General description and Save, then assert the Add-rule text is still there and that no extra `GET /api/agents/{name}/rules` or `.../notes` request was made during the Save.
- [ ] **Status and alert lines** use `App.ui.status`, keeping today's text, `role`, testids (`rules-status`, `notes-status` and so on) and visibility behaviour. The over-limit and error messages still show. **For the `role=alert` lines:** if `App.ui.status` cannot set `role="alert"`, add a `role` option (`'status'` default, `'alert'`) to the factory, with a contract case in both engines, a demo note and the catalogue row updated. Do not fall back to a hand-built `<p role=alert>`.
- [ ] **Empty states** use `App.ui.emptyState` (with `titleTag: 'p'` where a heading would be wrong), keeping today's text and testids. The `.rules-empty`/`.notes-empty` CSS is removed if no consumer remains.
- [ ] **The `.ui-toggle` query** is replaced by the handle that `App.ui.toggle` returns.
- [ ] **Mount once:** the tab mounts once per agent. Rule and note changes re-render only their own list (the rules list or the notes list), never the tab's frame, the switch or the Add form; a full re-render happens only on a new agent. Note pending and flagged states (from M27) are unchanged.
- [ ] **The other hand-built pieces** on the leg's allowance rows also move, each to its library owner:
  - delete through `App.confirmDelete` → `App.ui.confirm` on a library button (the `delete-btn` class row goes with it; keep today's labels, `aria-label` and the shared `ui-confirm-live` announcement);
  - `editor-section`/`section-title` markup → `App.ui.section({titleTag: 'h3'})`;
  - `empty-state` → `App.ui.emptyState` (above);
  - `ui-toggle` → the toggle handle (above).
- [ ] **Zero:** `rules-notes-tab.js` has no sinks and no allowance rows (lowered from the printed dicts).
- [ ] **Tests:** `test_flow_agent_rules.py`, `test_flow_agent_notes.py`, the chat drawer's tests (`test_flow_chat_drawer.py`, `chats` lane) and the new no-rebuild test pass. The selectors that change are listed from a grep.
- [ ] **Captures:** `agent-rules-and-notes` to `…/m31-f2-after-09/`, with no visible difference expected. Any difference is listed and justified, or fixed.
- [ ] **Gates:** `make test-unit`; the static guards and ownership checks; the `agents` and `chats` lanes under netns.

## Verification Steps
- `grep -n "innerHTML\|outerHTML\|insertAdjacentHTML\|ui-toggle'\|\.ui-toggle" the_one/interfaces/web/static/js/areas/studio/rules-notes-tab.js` returns nothing.
- The lanes above.

## Implementation Guidance
1. Read the tab, then list every hand-built piece and every class query.
2. Replace them one at a time, and run `test_flow_agent_rules.py` and `test_flow_agent_notes.py` after each.
3. Captures, allowances, docs.

## Edge Cases
- **Note text is attacker-influenced** (M27): it is rendered with `textContent` only. Keep that property; it must not regress.
- **Create mode:** the tab shows its create-mode empty state, as today.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/rules-notes-tab.js`, possibly `css/studio.css`.
- `tests/browser/test_flow_agent_rules.py`, `test_flow_agent_notes.py` (selectors only, if needed).
- `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py`, `the_one/agents.md`.

## Citation Audit
Carried from the planning survey (`dbcd458`). Re-verified by symbol at the leg design review (2026-10-21, one cycle: approve with changes). The review's addenda are applied above: no `setAgent`, the allowance-row pieces, the `role=alert` decision, list-local re-renders and the drawer test file.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
