# Leg: 01-listbox-keyboard-and-structure

**Status**: ready
**Flight**: [Accessibility Carry-forward](../flight.md)

## Objective

Fix listbox keyboard semantics on the chat welcome agent picker (the one real `role="listbox"` site in the codebase), resolve the session-list structural ARIA violation by dropping the listbox semantic entirely (the per-item delete button cannot be a descendant of `role="option"`), and verify that the admin tools-grid is keyboard-accessible as-is (it's a button-grid post-M08 F5, NOT a listbox — no role change required).

## Context

The 2026-05-15 maintenance report's Accessibility A.1 and A.4 findings clustered as "listbox options lack arrow-key navigation across 3 sites" plus "listbox option contains a button." During Phase 4b mission validation, the Architect spot-check found that **the tools-grid claim was wrong**: `admin/tools-grid.js` uses `role="list"` + `role="listitem"` (NOT `role="listbox"` + `role="option"`) — already migrated to a button-grid in M08 F5 leg 02, per the explicit test docstring at `tests/browser/test_flow_keyboard.py:107-110`. Adding `role="listbox"` semantics to a `list`/`listitem` structure would be semantically inappropriate.

Net result: only **one** site actually needs roving-tabindex treatment (chat welcome agent picker at `chat/welcome.js`). The session-list at `chat/history-buckets.js` is being de-listbox'd (not roving-tabindex-fixed). The tools-grid just needs verification that the existing button-grid is keyboard-accessible.

`areas/layout/section-nav.js:71-91` implements the correct roving-tabindex pattern. With only one consumer, helper extraction is moot — copy-with-attribution into `welcome.js`.

**Affected tests**: `tests/browser/test_flow_keyboard.py:50, 63` asserts `session_list.role == "listbox"`. The leg MUST update these assertions to match the new shape (and verify there are no other listbox-role assertions in the same file).

The session-list restructure: replace `role="listbox"` container + `role="option"` items containing interactive `<button class="list-item-delete">` with `<nav>` + `<ul>` of `<button>` items where the delete button is a sibling. The UX (click to load a session; click a sibling button to delete) doesn't match the single-select listbox shape; `<nav>` + buttons gets Tab/Shift+Tab for free and matches the surrounding shell-navigation pattern.

## Inputs

- `the_one/interfaces/web/static/js/areas/layout/section-nav.js` — existing roving-tabindex implementation to lift (lines around 71-91; note: actual path is `areas/layout/`, not `layout/`)
- `the_one/interfaces/web/static/js/areas/chat/welcome.js` — chat welcome agent picker; `role="listbox"` + `role="option"`; first option has `tabindex="0"`, others `tabindex="-1"` (partial roving in place); `aria-selected="false"` on all; missing container-level keydown handler for Arrow/Home/End
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` — session list; `role="listbox"` + `role="option"` items each containing `<button class="list-item-delete">`; every item has `tabindex="0"` (no roving)
- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` — verify-only: container is `role="list"`, items are `role="listitem"`, each wraps an inner `<button>` for the click affordance (button-grid pattern from M08 F5); leg does NOT add listbox semantics
- `tests/browser/test_flow_keyboard.py:50, 63` — asserts session-list `role == "listbox"`; will break under this leg's restructure; must be updated in the same commit
- Manual keyboard testing capability (browser + reach the affected UI surfaces)

## Outputs

- `chat/welcome.js` agent picker: container keydown handler added; ArrowUp/Down/Home/End; `aria-selected` toggling; pattern copied with attribution comment naming `areas/layout/section-nav.js` as the source (no helper extraction — single consumer)
- `chat/history-buckets.js`: dropped `role="listbox"` / `role="option"`; replaced with `<nav>` + `<ul>` of `<button>` items; per-item delete button is a sibling rather than a child
- `tests/browser/test_flow_keyboard.py`: assertions around lines 50, 63 updated to match new session-list shape (re-read the file end-to-end before edit for any related assertions)
- `admin/tools-grid.js`: no code change — verification only that the existing button-grid is keyboard-accessible
- Manual keyboard testing performed and documented in `flight-log.md`

## Acceptance Criteria

- [ ] In chat welcome agent picker: Tab into listbox → first option focused → ArrowDown → focus moves to next option → `aria-selected="true"` shifts → Enter activates
- [ ] In session list: Tab through items linearly → each session button focusable → delete button focusable as sibling — NO `role="option"` containing `<button>` in the DOM
- [ ] In admin tools-grid: Tab into grid → first tile focused → Enter activates; verify the existing button-grid is keyboard-accessible without any role change (this is a verification criterion, not an edit criterion)
- [ ] WCAG 2.1.1 (Keyboard) satisfied across all three surfaces
- [ ] WCAG 4.1.2 (Name, Role, Value) satisfied — no nested interactive elements inside `role="option"`
- [ ] `tests/browser/test_flow_keyboard.py` updated to match new session-list shape; broad pytest collection still 0 errors
- [ ] Browser tests for chat and admin surfaces still pass (or are updated to match new markup)
- [ ] Ruff baselines preserved (0/0)

## Verification Steps

- `cd /home/cprch/projects/the-one && grep -rn 'role="listbox"\|role="option"' the_one/interfaces/web/static/js/` — confirm session-list no longer matches; only chat welcome matches (with the new roving-tabindex implementation). Tools-grid should not appear (it uses `role="list"`/`role="listitem"`).
- `cd /home/cprch/projects/the-one && grep -rn 'list-item-delete' the_one/interfaces/web/static/js/` — confirm delete button is a sibling, not a child of an `option`
- Manual: navigate to Chat → Welcome canvas → keyboard test as described in acceptance
- Manual: navigate to Chat → focus session sidebar → keyboard test (Tab/Shift+Tab through items)
- Manual: navigate to Admin → Tools → keyboard test (Tab cycles through button-grid tiles; Enter activates)
- `cd /home/cprch/projects/the-one && pytest tests/browser/test_flow_keyboard.py -q` — exits 0 with updated assertions
- `cd /home/cprch/projects/the-one && pytest --tb=no -q` → exit 0
- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/` → both exit 0

## Implementation Guidance

1. **Inspect the reference pattern**
   - Read `the_one/interfaces/web/static/js/areas/layout/section-nav.js` (roving-tabindex + arrow-key implementation around lines 71-91; line numbers are approximate)
   - Note the structure: an event handler on the container that intercepts ArrowUp/Down/Home/End, moves focus, and updates `tabindex`/`aria-selected`/`aria-current` as needed
   - Note any DOM contract requirements (e.g., specific class names, data-attributes)

2. **Apply to `welcome.js` agent picker (the one consumer)**
   - Read `the_one/interfaces/web/static/js/areas/chat/welcome.js` to find the listbox + options block (around lines 51-59; line numbers approximate)
   - Container gets a keydown listener (the options already exist with `role="option"`, `tabindex="0"` on first item, others `tabindex="-1"`, `aria-selected="false"` on all)
   - On ArrowDown/ArrowUp: move focus + update `tabindex` (only the focused option has `tabindex="0"`, others `"-1"`) + update `aria-selected="true"` on new active, `"false"` on prior
   - Home / End: move to first / last
   - Enter / Space: activate (existing handler likely already does this)
   - Add a header comment naming `areas/layout/section-nav.js` as the source pattern (no helper extraction — single consumer)

3. **Verify `tools-grid.js` is keyboard-accessible (no edit)**
   - Read `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` around the tile-rendering block (the `role="list"` + `role="listitem"` + inner `<button>` structure)
   - Verify in the running app: Tab cycles through tiles via the inner `<button>` affordance; Enter activates; no keyboard trap
   - This is a verification leg item, not an edit; document outcome in `flight-log.md`

4. **Restructure `history-buckets.js`**
   - Edit `chat/history-buckets.js:35-68`
   - Remove `role="listbox"` from the container
   - Remove `role="option"` from each session item; replace with the parent `<button>` being the clickable affordance
   - The delete `<button>` (line ~60s) becomes a sibling inside the same `<li>` but NOT inside the clickable session `<button>`. The DOM shape becomes:
     ```html
     <nav aria-label="Recent sessions">
       <ul>
         <li>
           <button class="session-item" data-session-id="...">Session title</button>
           <button class="list-item-delete" aria-label="Delete session">×</button>
         </li>
         ...
       </ul>
     </nav>
     ```
   - Update any CSS selectors that depended on the listbox shape (e.g., `[role="option"]` → `.session-item`)
   - Verify keyboard navigation: Tab cycles through session-button → delete-button → next session-button → next delete-button. This is the standard linear behavior; acceptable for a chat history.

6. **Update affected browser test assertions**
   - Read `tests/browser/test_flow_keyboard.py` end-to-end (the file is small enough — start at line 1) to find ALL listbox-role assertions on the session-list. Known sites: lines 50, 63.
   - Update each to match the new shape (`role="navigation"` on the container, or query by `<nav aria-label="Recent sessions">`); update test docstrings where they describe the listbox shape
   - Run `pytest tests/browser/test_flow_keyboard.py -q` — exit 0
   - If other browser tests assert the listbox shape (search: `grep -n 'role.*listbox\|getByRole.*listbox' tests/browser/`): update those too
   - Run broad pytest: `pytest --tb=no -q` — exit 0

7. **Manual keyboard test**
   - Document the test outcome in `flight-log.md` Session Notes (which surfaces were tested, what was observed, any anomalies)

8. **Commit**
   - `git add the_one/interfaces/web/static/js/areas/chat/welcome.js the_one/interfaces/web/static/js/areas/chat/history-buckets.js tests/browser/test_flow_keyboard.py` (NOT tools-grid.js — no edit; NOT a new helper file — no extraction)
   - Plus any CSS selector adjustments and other affected browser tests
   - Commit message: `a11y: roving-tabindex on chat welcome picker; session-list dropped listbox semantic; tools-grid verified keyboard-accessible`

## Edge Cases

- **Existing pixel-snapshot baselines drift** from the markup change in session-list: regenerate locally (gitignored per project convention); note in flight log.
- **A11y assertions in browser tests** (e.g., `expect(page.getByRole('listbox'))`): update to `expect(page.getByRole('navigation'))` for session-list specifically.
- **Tab order surprise**: dropping listbox semantic on session-list means every session button is tab-stop. For long history (>30 sessions), this is a tab-key marathon. Acceptable in the immediate term; if it becomes user-painful, M10 can add a "skip past sessions" link.
- **Click target shrinks**: if the existing UI relied on the entire `<li>` being clickable (large hit target), the change to `<button class="session-item">` may shrink the click target. Verify visually and either accept or apply CSS to keep the click area large (`button { display: block; width: 100%; }`).

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat/welcome.js` — keydown handler + roving-tabindex on agent picker
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` — structural restructure to nav+buttons (drop listbox semantic)
- `tests/browser/test_flow_keyboard.py` — assertion updates for new session-list shape (lines 50, 63 minimum; re-read file for any related sites)
- `the_one/interfaces/web/static/css/` (chat-area stylesheet) — adjusted selectors for session-list shape change (e.g., `[role="option"]` → `.session-item`)
- Possibly other `tests/browser/*.py` files if they assert `role="listbox"` on session-list (grep first)
- `flight-log.md` — Leg Progress + Session Notes for manual test
- **NOT modified**: `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` (verification-only — no role change)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Manual keyboard test documented in flight log
- [ ] Browser tests for these surfaces pass (or are updated)
- [ ] Broad pytest exits 0
- [ ] Ruff baseline preserved
- [ ] Update `flight-log.md` with leg progress entry
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in `flight.md`
- [ ] Commit all changes together
