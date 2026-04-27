# Leg: 03-keyboard-operability

**Status**: completed
**Flight**: [App Shell Restructure](../flight.md)

## Objective

Make every interactive `<div>`/`<span>` in the application keyboard-operable. Convert: chat session-item (div→listbox-option pattern), chat session-delete (span→button), studio agent-item (div→listbox-option pattern), studio agent-item-delete (span→button), studio chip-remove (3 sites — span→button), and admin admin-category-item (div→button). Add `:focus-within` reveal for the hover-only delete affordances so keyboard users can reveal the delete via Tab focus. Add `:focus-visible` accent-ring rules matching the existing `.delete-btn:focus-visible` pattern (`studio.css:93`). Closes the F2-flagged WCAG 2.1.1 (Keyboard) blocking debt for the elements the leg-02 top-bar restructure didn't already replace.

## Context

This leg lands the keyboard-operability rebuild flagged by F2's a11y review and absorbed into F3 per the user's Option-B scoping decision. Leg 01 placed `// TODO(a11y-keyboard)` markers at the eight debt sites; this leg removes the markers as the conversions are made.

Key carry-forward decisions:

- **Nested-button avoidance**: a `<button>` cannot contain a `<button>` (invalid HTML). Sites with a parent click-target AND an inline delete affordance (chat session-item + .delete; studio agent-item + .agent-item-delete) must NOT use parent=`<button>` with child=`<button>`. Two acceptable patterns:
  1. **Listbox/option pattern**: parent stays as `<div>` but receives `role="option"` (with parent list `role="listbox"`), `tabindex="0"`, and explicit Enter/Space activation handlers. The `.delete` becomes a `<button>` child — perfectly valid since the parent is no longer a `<button>`. This preserves the existing DOM structure and CSS rules with minimal change.
  2. **Sibling-restructure pattern**: parent becomes `<button class="session-item">` and `.delete` is moved OUTSIDE as a sibling, wrapped in a new `<div class="session-item-row">` flex container. Cleaner semantically but requires CSS rule renames.

  **This leg uses pattern 1 (listbox/option)** for chat session-item and studio agent-item, and **pattern: just-`<button>`** for the simpler cases (admin-category-item has no delete child; chip-remove sits inside a `<span class="chip">` non-interactive parent; the inline delete affordances themselves all become plain `<button>`s).

  Rationale for pattern 1 over pattern 2: the existing `.session-item:hover .delete` reveal (chat.css:19), the `.agent-item:hover .agent-item-delete` reveal (studio.css:17), and the `.session-item.active` highlighting (chat.css:14) all assume the delete is a descendant of the parent. Pattern 1 preserves this DOM relationship; pattern 2 would require renaming CSS selectors and re-coordinating the active-state highlight logic. Pattern 1's cost is two explicit Enter/Space handlers (one per area). Worth it.

- **`:focus-within` reveal**: when the user Tabs into the `.delete` button, focus is on the button; the parent `.session-item` matches `:focus-within`; CSS reveals the delete via `display: block`. The hover-only `.session-item:hover .delete { display: block; }` rule (chat.css:19) is extended to `.session-item:hover .delete, .session-item:focus-within .delete { display: block; }`. Same pattern for `.agent-item:hover .agent-item-delete`. The chip-remove is always-visible (no `display: none` rule); no `:focus-within` reveal needed there.

- **Focus-visible accent-ring**: the existing pattern at `studio.css:93` is `outline: 2px solid var(--accent); outline-offset: 2px; box-shadow: 0 0 0 3px var(--accent-glow);`. The existing `.area-admin .admin-category-item:focus-visible` rule at `admin.css:84` uses `outline-offset: -2px; box-shadow: inset 0 0 0 3px var(--accent-glow);` — the inset variant for elements with backgrounds. Per element type:
  - **Buttons that are list rows with backgrounds** (session-item, agent-item, admin-category-item): use the inset variant.
  - **Buttons that are inline action affordances** (.delete, .agent-item-delete, chip-remove): use the standard outline+offset variant matching .delete-btn:focus-visible.

- **Chip-remove click-handler dispatch update**: at `studio.js:441`, the existing handler uses `e.target.classList.contains('chip-remove')` — but when chip-remove is a `<button>` containing an `<svg>`, clicking on the SVG produces `e.target = <svg>` and the classList check fails. **Fix**: use `e.target.closest('.chip-remove')` to find the button reliably regardless of which descendant was clicked.

- **`data-testid` preservation**: `agent-item` has `data-testid="agent-item"`; preserve. Other tests grep for class names (`session-item`, `agent-item-delete`, etc.) — preserve.

- **`role="listbox"` on parent containers**: `<div class="session-list">` becomes `<div class="session-list" role="listbox" aria-label="Chat sessions">`; same for `<div class="agent-list">` (becomes `<div class="agent-list" role="listbox" aria-label="Agents">`); `<div class="admin-category-list">` (becomes `<div class="admin-category-list" role="listbox" aria-label="Admin categories">`). Each child gets `role="option"` and a single child has `aria-selected="true"` (the active one). Combined with `tabindex` roving (active option = `tabindex="0"`, others = `tabindex="-1"`), this gives the canonical listbox keyboard model: arrow keys move between options, Tab leaves the listbox.

  - **However**: the user-visible navigation in this app is "click to switch session/agent/category." A full roving-tabindex listbox is overkill for ~5-20 items. Simplification: each option uses `tabindex="0"` (all in tab order), no arrow-key navigation. Tab cycles through visible options; Enter/Space activates. This is simpler than roving-tabindex and still WCAG-compliant. Document the choice.

- **Visual snapshots stay drifted** — leg 06 still owns regeneration. The DOM structure changes (div→button or div role=option) will marginally shift snapshots; do NOT regenerate in leg 03. Leg 06 inventory will absorb any new drift.

## Inputs

- Branch `flight/03-app-shell-restructure`; legs 01-02 landed (uncommitted per F3 batching).
- Working tree state: legs 01-02 modifications present (theme.js renderToggle, admin.js theme-lift, tokens.css token migration, base.css topbar, components.css picker rules, app.js renderTopBar + hashchange guard + aside aria-label, area-registration sidebarLabels, test_flow_picker.py, agents.md affordance + app-shell sections, regenerated dark snapshots from leg 01).
- The eight `// TODO(a11y-keyboard)` markers from leg 01 are still in place; this leg removes them as it completes the conversions (the new-chat marker at chat.js:23 stays — that's leg 05's work).

Marker sites carried forward (line numbers may have shifted by ±2 from leg-01-baseline due to the comment lines and from leg-02's adjacent edits; the implementation searches by class name, not line number):

- `chat.js` — `<div class="session-item">` (~line 131); `<span class="delete">` inside (~line 151).
- `studio.js` — `<div class="agent-item">` (~line 91); `<span class="agent-item-delete">` inside (~line 102); `<span class="chip-remove">` × 3 sites (~lines 290/300, 522).
- `admin.js` — `<div class="admin-category-item">` (~line 93).

## Outputs

State that must exist after this leg completes:

### `chat.js`
- `<div class="session-list">` → `<div class="session-list" role="listbox" aria-label="Chat sessions">`. Set this at sidebar-build time (chat.js:26).
- Each session row: `<div class="session-item" role="option" tabindex="0" aria-selected="…">` (NOT a `<button>`). Receives explicit Enter/Space handler that calls `joinSession(s.id)`. The `aria-selected` value is `"true"` for the current session, `"false"` otherwise.
- The `.session-item-text` and `.session-item-title` / `.session-item-agent` children unchanged.
- The inline delete: `<span class="delete">` → `<button class="delete" type="button" aria-label="Delete session">`. The `App.icon('x')` SVG stays as the button's content. The click handler stays the same.
- `// TODO(a11y-keyboard)` markers at chat.js:130 and chat.js:150 REMOVED.
- `highlightActiveSession` (chat.js:89) updated to also flip `aria-selected` on each item: `items[i].setAttribute('aria-selected', items[i].dataset.id === currentSessionId ? 'true' : 'false');`.

### `studio.js`
- `<div class="agent-list">` → `<div class="agent-list" role="listbox" aria-label="Agents">`. Located at the studio-area sidebar build site (search for `'<div class="agent-list">'` or equivalent — verify against current source).
- Each agent row: `<div class="agent-item" role="option" tabindex="0" aria-selected="…" data-name="…" data-testid="agent-item">`. Receives explicit Enter/Space handler that calls `selectAgent(agent)`. `aria-selected` = `"true"` if this is the currently selected agent.
- The inline delete: `<span class="agent-item-delete">` → `<button class="agent-item-delete" type="button" aria-label="Delete agent">`. Click handler unchanged.
- The three chip-remove sites (~lines 290, 300, 522): `<span class="chip-remove">…</span>` → `<button class="chip-remove" type="button" aria-label="Remove">…</button>`. The dispatching click handler at `studio.js:441` updated: `if (e.target.closest('.chip-remove'))` instead of `if (e.target.classList.contains('chip-remove'))`. The next line `e.target.parentElement.remove()` becomes `e.target.closest('.chip-remove').parentElement.remove()` so the chip's parent is reliably found regardless of which descendant fired the click.
- All four `// TODO(a11y-keyboard)` markers in studio.js REMOVED (the chip-remove pair-marker at line 287 covers both :290 and :300, plus the wireEditorEvents marker at line 521).
- Whichever function selects an agent (`selectAgent`) updates aria-selected on all items after activating one (analogous to `highlightActiveSession`).

### `admin.js`
- `<div class="admin-category-list">` (or whatever class wraps admin-category items — verify by reading admin.js around the renderCategoryList function): wrap with `role="listbox" aria-label="Admin categories"`.
- Each admin-category-item: `<div class="admin-category-item" role="option" tabindex="0" aria-selected="…">` with explicit Enter/Space handler calling the existing `el.onclick` body (which sets currentCategory, etc.).
- The `// TODO(a11y-keyboard)` marker at admin.js:93 REMOVED.

### `chat.css`
- `.area-chat .session-item:hover .delete` rule extended to `.area-chat .session-item:hover .delete, .area-chat .session-item:focus-within .delete { display: block; }` — adds keyboard reveal.
- New rule: `.area-chat .session-item:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; box-shadow: inset 0 0 0 3px var(--accent-glow); }` — inset variant (matches `.admin-category-item:focus-visible`).
- New rule: `.area-chat .session-item .delete:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; box-shadow: 0 0 0 3px var(--accent-glow); }` — standard variant.
- `.area-chat .session-item .delete` should also include `background: transparent; border: none; padding: 2px 4px;` (button reset) IF the existing rule doesn't already neutralize button defaults. The current rule at `chat.css:18` uses `padding: 2px 4px` — preserve. Add `background: transparent; border: none; cursor: pointer;` (cursor remains pointer for visual consistency). The existing color/transition rules stay.
- `.area-chat .session-item` itself doesn't need button-reset rules because it's a `<div role="option">`, not a `<button>`.

### `studio.css`
- `.area-studio .agent-item:hover .agent-item-delete` rule extended to also include `.area-studio .agent-item:focus-within .agent-item-delete { display: block; }` — keyboard reveal.
- New rule: `.area-studio .agent-item:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; box-shadow: inset 0 0 0 3px var(--accent-glow); }` — inset variant.
- `.area-studio .agent-item-delete` button-reset additions: `background: transparent; border: none; cursor: pointer;` (existing `cursor: pointer` already present at studio.css:16).
- `.area-studio .agent-item-delete:focus-visible` rule: standard outline+offset variant.
- `.area-studio .chip-remove` button-reset additions: `background: transparent; border: none; padding: 0;` plus `:focus-visible` outline+offset variant. Existing color/cursor/transition rules stay.

### `admin.css`
- `.area-admin .admin-category-item:focus-visible` rule already exists at admin.css:84 — confirm it's correctly scoped (it should now fire on Tab focus since the element is focusable).
- No new CSS rules needed if admin-category-item has no inline child action — verify by reading admin.css for `.admin-category-item *` rules.

### Tests
- New file `tests/browser/test_flow_keyboard.py` with 4-6 tests:
  - `test_session_item_keyboard_select`: seed 2 sessions, focus first session-item, press Enter, assert that session is the active one (DOM check via `aria-selected="true"`).
  - `test_session_delete_keyboard_reveal`: seed 1 session, Tab focus into the session-item, then Tab again to the .delete button, assert the .delete is visible (`is_visible()`), press Enter, assert session was deleted (list now empty).
  - `test_agent_item_keyboard_select`: seed 2 agents, Tab to first agent-item, press Space, assert it's selected.
  - `test_chip_remove_keyboard`: open studio, select an agent with at least one MCP source chip, focus the chip-remove button, press Enter, assert the chip is removed from DOM.
  - `test_admin_category_keyboard_select`: open admin, Tab through to a category, press Enter, assert that category is now active.
- Existing flow tests must continue to pass.
- Visual snapshots: continue to drift; leg 06 owns. Document any NEW drift in flight log.

### Documentation
- `the_one/agents.md` — add a `### Keyboard operability` subsection (or extend the `### App shell` section landed in leg 02) documenting the listbox/option pattern for list rows + the per-item button pattern for inline action affordances + the `:focus-within` reveal convention.
- The 8 `// TODO(a11y-keyboard)` markers reduced to 1 (only the new-chat-flow marker at chat.js:23 stays for leg 05).

## Acceptance Criteria

- [x] `chat.js` — session-list has `role="listbox" aria-label="Chat sessions"`; each session-item has `role="option" tabindex="0" aria-selected` (true for active, false for others). Explicit Enter/Space handler calls `joinSession`. The session-delete is now a `<button class="delete" type="button" aria-label="Delete session">`. `highlightActiveSession` updates `aria-selected` on each row.
- [x] `studio.js` — agent-list has `role="listbox" aria-label="Agents"`; each agent-item has `role="option" tabindex="0" aria-selected` (true for selected, false for others) and preserves `data-testid="agent-item"` and `data-name`. Explicit Enter/Space handler calls `selectAgent`. The agent-item-delete is `<button>`. The 3 chip-remove sites are `<button>` (with `aria-label="Remove"`). Click handler at studio.js:441 uses `closest('.chip-remove')` for SVG-resilient dispatch.
- [x] `admin.js` — admin-category-list (or wrapping element) has `role="listbox" aria-label="Admin categories"`; each admin-category-item is `<div role="option" tabindex="0" aria-selected>` with explicit Enter/Space handler. Active item has `aria-selected="true"`.
- [x] `chat.css`, `studio.css` — `:focus-within` rules added on parent rows (extends the `:hover .delete` reveal pattern). `:focus-visible` accent-ring rules added per element type (inset for list-row buttons; standard for inline action buttons).
- [x] All 8 a11y-keyboard markers from leg 01 REMOVED. The 1 new-chat marker at chat.js:24 STAYS.
- [x] `pytest tests/` reports 393 passing.
- [x] `pytest -m browser tests/browser/ --ignore=tests/browser/test_visual_snapshots.py --tb=short --timeout=120` reports all flow tests passing — 12 prior + 5 new keyboard tests = 17.
- [x] `pytest -m browser tests/browser/test_visual_snapshots.py` continues to report failures — no NEW drift relative to leg 02's failing inventory (same 7 baselines). Recorded in flight log.
- [x] `the_one/agents.md` has a Keyboard operability section (or extension of App shell) documenting the listbox/option + button conventions used.
- [x] Manual keyboard walkthrough: Tab from skip-link, through topbar items, into sidebar listbox, between options (each individual Tab moves to the next option since per-row `tabindex="0"`); Enter on an option activates it; Tab into the `.delete` button reveals it via `:focus-within`; Enter on `.delete` deletes the row.

## Verification Steps

- `grep -rn "TODO(a11y-keyboard)" the_one/interfaces/web/static/js/areas/` → returns 1 hit (the new-chat marker at chat.js:23).
- `grep -n 'role="option"\|role="listbox"' the_one/interfaces/web/static/js/areas/` → returns 6+ hits (3 listbox attrs at sidebar-build sites + 3 option attrs in render functions).
- `grep -n "session-item-text\|session-item-title\|session-item-agent" the_one/interfaces/web/static/js/areas/chat.js` → unchanged (these inner elements survive the conversion).
- `grep -n 'data-testid="agent-item"' the_one/interfaces/web/static/js/areas/studio.js` → returns 1 hit (preserved on the new `<div role="option">`).
- `grep -n "closest.*chip-remove" the_one/interfaces/web/static/js/areas/studio.js` → returns 1+ hit (the SVG-resilient dispatch).
- `pytest tests/ --tb=short --timeout=60` → 393 passing.
- `pytest -m browser tests/browser/ --ignore=tests/browser/test_visual_snapshots.py --tb=short --timeout=120` → all flow tests passing (12 + 5 = 17, or whatever the actual prior count was per leg 02 — confirm via enumeration).
- Manual browser open: Tab through chat sessions list, verify focus ring appears on each session and on each `:focus-within`-revealed `.delete`. Press Enter on a session — it activates. Press Enter on the `.delete` — session deleted.
- Manual screen-reader spot-check (NVDA / VoiceOver): "listbox, Chat sessions, 3 items"; "option, <session title>, selected"; etc.

## Implementation Guidance

1. **Convert chat.js session-item**

   In `chat.js` at the sidebar-build (line ~26):
   ```javascript
   '<div class="session-list" role="listbox" aria-label="Chat sessions"></div>';
   ```

   In `renderSessionList` (line ~127), replace the session-item construction:
   ```javascript
   // Was:
   var el = document.createElement('div');
   el.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');
   el.dataset.id = s.id;
   ...
   el.onclick = function () { joinSession(s.id); };

   // Becomes:
   var el = document.createElement('div');
   el.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');
   el.setAttribute('role', 'option');
   el.setAttribute('tabindex', '0');
   el.setAttribute('aria-selected', s.id === currentSessionId ? 'true' : 'false');
   el.dataset.id = s.id;
   ...
   el.onclick = function () { joinSession(s.id); };
   el.addEventListener('keydown', function (e) {
     if (e.key === 'Enter' || e.key === ' ') {
       e.preventDefault();
       joinSession(s.id);
     }
   });
   ```

   Replace the .delete construction:
   ```javascript
   // Was:
   var delBtn = document.createElement('span');
   delBtn.className = 'delete';
   delBtn.innerHTML = App.icon('x');
   delBtn.onclick = function (e) { ... };

   // Becomes:
   var delBtn = document.createElement('button');
   delBtn.type = 'button';
   delBtn.className = 'delete';
   delBtn.setAttribute('aria-label', 'Delete session');
   delBtn.innerHTML = App.icon('x');
   delBtn.onclick = function (e) { ... };  // body unchanged
   ```

   Update `highlightActiveSession`:
   ```javascript
   function highlightActiveSession() {
     var items = sessionListEl.querySelectorAll('.session-item');
     for (var i = 0; i < items.length; i++) {
       var isActive = items[i].dataset.id === currentSessionId;
       items[i].classList.toggle('active', isActive);
       items[i].setAttribute('aria-selected', isActive ? 'true' : 'false');
     }
   }
   ```

   REMOVE the two `// TODO(a11y-keyboard)` markers (chat.js:130, chat.js:150).

2. **Convert studio.js agent-item, agent-item-delete, chip-remove**

   At the studio sidebar-build (search for `'<div class="agent-list">'` or similar):
   ```javascript
   '<div class="agent-list" role="listbox" aria-label="Agents"></div>'
   ```

   In the agent-item render (line ~89):
   ```javascript
   var el = document.createElement('div');
   el.className = 'agent-item' + (selectedAgent && selectedAgent.name === agent.name && !createMode ? ' active' : '');
   el.setAttribute('role', 'option');
   el.setAttribute('tabindex', '0');
   el.setAttribute('aria-selected', selectedAgent && selectedAgent.name === agent.name && !createMode ? 'true' : 'false');
   el.dataset.name = agent.name;
   el.setAttribute('data-testid', 'agent-item');
   ...
   el.onclick = function () { selectAgent(agent); };
   el.addEventListener('keydown', function (e) {
     if (e.key === 'Enter' || e.key === ' ') {
       e.preventDefault();
       selectAgent(agent);
     }
   });
   ```

   Replace the agent-item-delete:
   ```javascript
   var delBtn = document.createElement('button');
   delBtn.type = 'button';
   delBtn.className = 'agent-item-delete';
   delBtn.setAttribute('aria-label', 'Delete agent');
   delBtn.innerHTML = App.icon('x');
   delBtn.onclick = function (e) { ... };  // body unchanged
   ```

   `selectAgent` calls `renderAgentList()` unconditionally — meaning the agent-item DOM is fully rebuilt on each selection. Set `aria-selected` AT RENDER TIME inside the `renderAgentList` loop (alongside the existing `' active'` class concatenation), NOT in a separate post-render walk. The render-time approach is what the code block above already does (`el.setAttribute('aria-selected', ...)`); confirm there is no separate post-render walk added that would duplicate the logic.

   For the three chip-remove sites in template literals (lines ~290, ~300, ~522), replace:
   ```javascript
   '<span class="chip-remove">' + App.icon('x') + '</span>'
   ```
   with:
   ```javascript
   '<button class="chip-remove" type="button" aria-label="Remove">' + App.icon('x') + '</button>'
   ```
   (apply at all three sites).

   Update the dispatch handler at studio.js:441:
   ```javascript
   editorEl.addEventListener('click', function (e) {
     var removeBtn = e.target.closest('.chip-remove');
     if (removeBtn) {
       removeBtn.parentElement.remove();
       checkDirty();
     }
   });
   ```

   REMOVE the four `// TODO(a11y-keyboard)` markers in studio.js.

3. **Convert admin.js admin-category-item**

   `categoryListEl` IS the listbox container — it's the `<div class="admin-category-list">` element built by the sidebar's `innerHTML` and grabbed via `sidebar.querySelector('.admin-category-list')`. Set the role directly on it at init time (NOT inside the per-render loop):
   ```javascript
   categoryListEl.setAttribute('role', 'listbox');
   categoryListEl.setAttribute('aria-label', 'Admin categories');
   ```

   In `renderCategoryList` (line ~89), replace the admin-category-item:
   ```javascript
   var el = document.createElement('div');
   el.className = 'admin-category-item' + (currentCategory === cat.id ? ' active' : '');
   el.setAttribute('role', 'option');
   el.setAttribute('tabindex', '0');
   el.setAttribute('aria-selected', currentCategory === cat.id ? 'true' : 'false');
   ...
   el.onclick = function () { ... };  // existing body
   el.addEventListener('keydown', function (e) {
     if (e.key === 'Enter' || e.key === ' ') {
       e.preventDefault();
       el.onclick();  // reuse the same body
     }
   });
   ```

   REMOVE the `// TODO(a11y-keyboard)` marker at admin.js:93.

4. **Update CSS — chat.css**

   At chat.css:19 (the existing `:hover .delete` rule), extend:
   ```css
   .area-chat .session-item:hover .delete,
   .area-chat .session-item:focus-within .delete { display: block; }
   ```

   Add new rules (place after the existing `.session-item` rules):
   ```css
   .area-chat .session-item:focus-visible {
     outline: 2px solid var(--accent);
     outline-offset: -2px;
     box-shadow: inset 0 0 0 3px var(--accent-glow);
   }
   .area-chat .session-item .delete {
     background: transparent;
     border: none;
   }
   .area-chat .session-item .delete:focus-visible {
     outline: 2px solid var(--accent);
     outline-offset: 2px;
     box-shadow: 0 0 0 3px var(--accent-glow);
   }
   ```

5. **Update CSS — studio.css**

   At studio.css:17 (the existing `:hover .agent-item-delete` rule), extend:
   ```css
   .area-studio .agent-item:hover .agent-item-delete,
   .area-studio .agent-item:focus-within .agent-item-delete { display: block; }
   ```

   Add new rules:
   ```css
   .area-studio .agent-item:focus-visible {
     outline: 2px solid var(--accent);
     outline-offset: -2px;
     box-shadow: inset 0 0 0 3px var(--accent-glow);
   }
   .area-studio .agent-item-delete {
     background: transparent;
     border: none;
   }
   .area-studio .agent-item-delete:focus-visible {
     outline: 2px solid var(--accent);
     outline-offset: 2px;
     box-shadow: 0 0 0 3px var(--accent-glow);
   }
   .area-studio .chip-remove {
     background: transparent;
     border: none;
     padding: 0;
   }
   .area-studio .chip-remove:focus-visible {
     outline: 2px solid var(--accent);
     outline-offset: 2px;
     box-shadow: 0 0 0 3px var(--accent-glow);
   }
   ```

6. **Update CSS — admin.css**

   The existing `.area-admin .admin-category-item:focus-visible` rule (admin.css:84) is already correct. No change needed here unless the audit reveals a missing button-reset (admin-category-item is now a `<div role="option">`, NOT a `<button>` — no button reset needed).

7. **Add keyboard tests**

   Create `tests/browser/test_flow_keyboard.py`:
   ```python
   """Keyboard-operability tests (F3 leg 03)."""
   from __future__ import annotations
   import pytest
   from playwright.sync_api import Page, expect


   @pytest.mark.browser
   def test_session_item_keyboard_select(app_with_provider: str, page: Page) -> None:
       page.goto(app_with_provider)
       page.evaluate(...)  # seed two sessions via WebSocket — pattern from existing test_flow_chat
       items = page.locator(".session-item")
       expect(items).to_have_count(2)
       items.nth(0).focus()
       page.keyboard.press("Enter")
       expect(items.nth(0)).to_have_attribute("aria-selected", "true")
       expect(items.nth(1)).to_have_attribute("aria-selected", "false")


   @pytest.mark.browser
   def test_session_delete_keyboard_reveal(app_with_provider: str, page: Page) -> None:
       page.goto(app_with_provider)
       # seed one session...
       session = page.locator(".session-item").first
       session.focus()
       page.keyboard.press("Tab")
       deleteBtn = page.locator(".session-item .delete").first
       expect(deleteBtn).to_be_visible()


   @pytest.mark.browser
   def test_agent_item_keyboard_select(app_with_agent: str, page: Page) -> None:
       page.goto(app_with_agent + "#studio")
       items = page.locator(".agent-item")
       items.first.focus()
       page.keyboard.press("Enter")
       expect(items.first).to_have_attribute("aria-selected", "true")


   @pytest.mark.browser
   def test_chip_remove_keyboard(app_with_agent: str, page: Page) -> None:
       page.goto(app_with_agent + "#studio")
       page.locator(".agent-item").first.click()
       # add an MCP chip first via the chip-add flow OR seed a config with chips
       # then:
       chip_remove = page.locator(".chip-remove").first
       chip_remove.focus()
       page.keyboard.press("Enter")
       # assert chip count decreased
   

   @pytest.mark.browser
   def test_admin_category_keyboard_select(app_clean: str, page: Page) -> None:
       page.goto(app_clean + "#admin")
       items = page.locator(".admin-category-item")
       items.first.focus()
       page.keyboard.press("Enter")
       expect(items.first).to_have_attribute("aria-selected", "true")
   ```

   Seeding adjustments — DO NOT use `xfail`; land working tests:
   - **Two sessions**: the WebSocket auto-creates one session on page load. To get a second, drive the new-chat flow via `page.click('.new-chat')` after WS open (pattern: `test_flow_chat.py`). Alternatively, **trim the test** to a single seeded session — keyboard mechanics (focus, press Enter, assert `aria-selected="true"` on the only option) is still the load-bearing assertion, and adding "select among many" coverage can wait.
   - **Agent with one chip**: `seed_mock_agent` (`tests/browser/seeders.py:58`) does NOT accept `mcp_source_ids`. Two options:
     (a) Extend `seed_mock_agent` to optionally accept `mcp_source_ids` (one-line payload addition) — do this if the chip-remove test is included, OR
     (b) Trim the chip-remove keyboard test to drive chip-add via the UI (click `.chip-add[data-type="mcp"]`, click an option in the dropdown), then test chip-remove keyboard. This is more of an integration test but also more realistic.
   - **Recommended**: pick (b) for the chip-remove test (UI-driven creation matches user behavior), and trim the session test to single-session mechanics. Drop the "two sessions" requirement entirely. If the chip test proves brittle (e.g., dropdown timing), drop it and rely on the `closest('.chip-remove')` dispatch correctness from manual verification only.

8. **Update `the_one/agents.md`**

   Add a `### Keyboard operability` subsection (or extend the App shell section landed in leg 02). Document:
   - Listbox/option pattern: list rows are `<div role="option" tabindex="0">`; the parent list is `<div role="listbox" aria-label="…">`.
   - Per-row Enter/Space handler: each row attaches its own keydown listener; both keys activate (no roving tabindex).
   - Inline action buttons: real `<button type="button" aria-label="…">` with `:focus-visible` outline+offset accent-ring.
   - `:focus-within` reveal: keyboard-focusing the inline action button reveals it via the parent's `:focus-within` selector. Used wherever the action is hidden until hover.
   - Anti-pattern: do NOT nest `<button>` inside `<button>`; use `role="option"` for the parent if it needs keyboard activation alongside child buttons.

9. **Run tests and verify**

   ```
   pytest tests/ --tb=short --timeout=60
   pytest -m browser tests/browser/ --ignore=tests/browser/test_visual_snapshots.py --tb=short --timeout=120
   pytest -m browser tests/browser/test_visual_snapshots.py --tb=short --timeout=120
   ```

   First: 393 passing. Second: 12 prior + 5 new = 17 passing (or note xfail count if any keyboard tests are marked xfail). Third: snapshot tests still failing — record NEW drift in flight log.

## Edge Cases

- **`role="option"` requires `role="listbox"` parent** for proper screen-reader semantics. If the listbox role is missing on the parent, the `option` role is invalid. Verify the listbox role is set on the parent BEFORE option items are appended.
- **`tabindex="0"` on every option** (the simplification) means a list of 20 sessions adds 20 Tab stops. For the current usage (~5-20 sessions/agents), this is acceptable. If lists ever grow large, switching to roving tabindex (only the active option = `tabindex="0"`, others = `-1`, with arrow-key navigation between) is the WCAG-recommended escalation. Document the simplification choice and the threshold for revisiting (~50 items?).
- **Enter vs Space activation differences**: native `<button>` activates on both Enter (on keydown) and Space (on keyup). Custom Enter/Space handlers on `<div role="option">` activate on keydown for both. Subtle behavioral difference; acceptable. The handler uses `e.preventDefault()` to prevent Space from scrolling the page when on the option.
- **`role="option"` does not support nested interactive content per ARIA**: technically, an `option` SHOULD NOT contain another interactive element (like a `<button>`). However, the listbox-with-actions pattern is widely used in the wild and is accepted by major screen readers (NVDA, VoiceOver) — they announce the option, then announce the inner button as a separate focusable. If strictness is required (e.g., for an audit), the alternative is the sibling-restructure pattern (see Context section). Document this as a deliberate accepted deviation.
- **`:focus-within` reveal + click-outside**: when the user clicks elsewhere, focus leaves the option, `:focus-within` no longer matches, and `.delete` returns to `display: none`. This is the desired behavior. Verify no race on click-handler ordering.
- **`aria-selected` on options never set true initially**: on first render with no active session, `aria-selected="false"` for all options. WCAG-correct (no false claim of selection). When the user activates one, the handler sets `aria-selected="true"`.
- **Chip-remove `<button>` inside `<span class="chip">`**: `<button>` inside `<span>` is valid HTML5 (span is non-interactive). The chip's outer span is purely visual; no interactive role is implied.

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat.js` — Convert session-item to role=option div; convert .delete to button. Update `highlightActiveSession`. Remove 2 markers.
- `the_one/interfaces/web/static/js/areas/studio.js` — Convert agent-item to role=option div; convert agent-item-delete to button; convert 3 chip-remove sites to button; update click dispatch with `closest`. Remove 4 markers.
- `the_one/interfaces/web/static/js/areas/admin.js` — Set listbox role on category container; convert admin-category-item to role=option div with keydown handler. Remove 1 marker.
- `the_one/interfaces/web/static/css/chat.css` — Add `:focus-within` reveal extension, `:focus-visible` rules for session-item and .delete, button reset for .delete.
- `the_one/interfaces/web/static/css/studio.css` — Add `:focus-within` reveal extension, `:focus-visible` rules for agent-item, agent-item-delete, chip-remove, button resets.
- `the_one/interfaces/web/static/css/admin.css` — No change (existing `:focus-visible` rule sufficient).
- `tests/browser/test_flow_keyboard.py` — NEW file: 5 tests covering keyboard operability.
- `the_one/agents.md` — Add Keyboard operability subsection (or extend App shell).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[LEG:03:landed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing per the verification plan (393 unit; 17 flow; visual snapshots still failing — no NEW drift)
- [x] Flight log updated with: leg 03 outcomes, manual keyboard walkthrough result, any tests marked xfail with reason
- [x] Leg status updated to `landed`
- [x] Per F3 batching: do NOT commit. Report `[LEG:03:landed]`.
