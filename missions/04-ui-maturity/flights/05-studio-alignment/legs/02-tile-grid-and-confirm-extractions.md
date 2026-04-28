# Leg: 02-tile-grid-and-confirm-extractions

**Status**: completed
**Flight**: [Studio Alignment](../flight.md)

## Objective

Replace the flat `.agent-list` (rendered as `.list-item.agent-item` rows after leg 01) with a CSS-grid tile layout where each tile is a `<button class="agent-tile">` carrying name + 2-line-clamped description + monospaced provider/model caption. Extract a single canonical `App.confirmDelete(itemEl, onConfirm, opts)` helper into `static/js/confirm.js`, migrate both chat's session-delete and studio's tile-delete to consume it, and lift chat's `.session-item.confirm-delete` rules from `chat.css` to `components.css` as the canonical `.list-item.confirm-delete` rule. Fix the studio agent-item keydown-bubble bug at the tile's keydown listener (NOT in the helper).

## Context

- Leg 01 landed the section-nav skeleton; the `.agent-list` rendering and the `+ New Agent` button now live inside the Agents section (`.studio-agents-header` + `.agent-list` at `studio.js:117-138` and the agent-list rendering at `studio.js:231-279`). The `+ New Agent` button is already at the top of the Agents content pane.
- Leg 02 mirrors F4 leg 02's design-system contribution discipline: every new visual primitive lands in `components.css`, never in `studio.css`. Per-area `studio.css` keeps only genuine studio-specific overrides (e.g., tile-grid layout dimensions).
- The flight spec's resolved Open Question "Tile design on the agents grid" specifies: tile shows name (large, bold), description (caption, 2-line clamp), and a footer caption with provider name + model in monospace. Hover/focus reveals delete X-button (top-right). Click → editor (`selectAgent`). Keyboard: tile is `<button>`, Enter/Space activates; X-button is its own focus stop with the keydown-bubble fix applied.
- The flight spec's resolved Open Question "`App.confirmDelete` and `App.confirmDialog` — one helper or two?" specifies the helper signature: `App.confirmDelete(itemEl, onConfirm, opts)` where `opts` is `{titleSelector?: string, confirmLabel?: string, revertMs?: number}`. Default `titleSelector` is `[data-confirm-title]` (a NEW attribute hook on the title element); chat and studio both add it during migration. Default `confirmLabel` is `'Confirm delete?'`. Default `revertMs` is `3000`. The `onConfirm` callback signature is `(itemEl, revertFn) => void`; the helper passes `revertFn` so callers can roll the UI back on transport failure (studio's DELETE fetch can fail; chat's WS delete is fire-and-forget so `revertFn` is unused there).
- The flight spec's resolved Open Question "Studio agent-item keydown-bubble bug" specifies: fix at the **tile's** keydown listener with `if (e.target !== el) return;` guard. The `App.confirmDelete` helper does NOT add its own keydown guard — the bubble check belongs to the parent activatable element.

## Inputs

What exists before this leg runs (post-leg-01 state):

- `the_one/interfaces/web/static/js/areas/studio.js` (1030 LOC):
  - `renderAgentList()` at `studio.js:231-279` — currently renders `<div class="list-item agent-item" role="option" tabindex="0" data-testid="agent-item" data-name="{name}" aria-selected="...">` rows with `.agent-item-name` span and `.list-item-delete.agent-item-delete` button.
  - `deleteAgentInline(name, el)` at `studio.js:281-311` — current two-step inline delete (first click adds `.confirm-delete`, swaps text; second click within 3s fires DELETE fetch; timer reverts).
  - Agent-item `keydown` listener at `studio.js:270-275` — Enter/Space → `selectAgent(agent)`. **No `e.target !== el` guard today** (the bug).
  - `+ New Agent` button at `studio.js:117-119` already lives in `.studio-agents-header` (leg 01 relocation).
- `the_one/interfaces/web/static/js/areas/chat.js` (605 LOC):
  - Inline two-step session delete at `chat.js:427-445` — `onDelete(id, btn)` callback closure: first click adds `.confirm-delete` to `.session-item`, swaps `.session-item-title` text to "Confirm delete?", starts 3s revert timer; second click sends WS `delete_session` action. Title element class is `.session-item-title`.
- `the_one/interfaces/web/static/css/chat.css:89-92` — three `.area-chat .session-item.confirm-delete*` rules (~5 LOC including the comment) — danger-color border, title color, and delete-button reveal.
- `the_one/interfaces/web/static/css/components.css:98-128` — F4 canonical `.list-item`, `.list-item.active`, `.list-item-delete` (already present; ready for composition).
- `the_one/interfaces/web/static/css/studio.css` (73 LOC) — current `.area-studio .agent-item.confirm-delete`, `.agent-item-name`, `.agent-item-delete svg` rules at lines 14-17 will be replaced/superseded by tile rules.
- `the_one/interfaces/web/static/index.html:26-39` — script load order; `confirm.js` must insert BEFORE both `chat.js` and `studio.js`.
- `the_one/interfaces/web/static/js/icons.js` — `'plus'`, `'square-pen'`, `'x'` already registered.
- `tests/browser/test_flow_agent_crud.py` — uses `[data-testid="agent-item"]` (lines 52, 80), `[data-testid="delete-agent-btn"]` (lines 58, 73). Existing two-click delete test at lines 72-78 expects: first click changes delete button text to "Confirm Delete?", second click fires DELETE.
- `tests/browser/test_flow_hash_routing.py:119` — asserts `.agent-item[data-name="{name}"][aria-selected="true"]` is visible.

## Outputs

- `the_one/interfaces/web/static/js/confirm.js` — NEW. Defines `App.confirmDelete(itemEl, onConfirm, opts)` (~50-80 LOC).
- `the_one/interfaces/web/static/js/areas/studio.js`:
  - `renderAgentList()` rewritten to render `<button class="agent-tile" data-testid="agent-item" data-name="{name}" aria-selected="..." aria-label="{name}">` tiles inside an `.agent-tile-grid` container. Each tile contains a name span (`data-confirm-title`), a 2-line-clamped description span, a monospaced provider/model caption, and a `.list-item-delete.agent-tile-delete` X-button.
  - `deleteAgentInline(name, el)` migrated to use `App.confirmDelete(el, onConfirm, {titleSelector: '[data-confirm-title]', confirmLabel: 'Confirm delete?', revertMs: 3000})`. The callback issues the DELETE fetch and calls `revertFn()` on `.catch`. Net delta: ~-15 LOC in studio.js.
  - Agent-tile keydown listener gets the `if (e.target !== el) return;` guard — pressing Enter on the X-button does NOT fall through to `selectAgent`.
- `the_one/interfaces/web/static/js/areas/chat.js`:
  - Inline two-step delete at `chat.js:427-445` migrated to call `App.confirmDelete(item, onConfirm, {titleSelector: '[data-confirm-title]', confirmLabel: 'Confirm delete?', revertMs: 3000})`. The callback sends the WS `delete_session` message; `revertFn` is ignored (WS delete is fire-and-forget). Net delta: ~-15 LOC in chat.js.
- The session-list rendering helper (`App.chat.renderSessionList`, in `static/js/areas/chat/`) gets `data-confirm-title` added to its `.session-item-title` element.
- The agent-tile name span gets `data-confirm-title`.
- `the_one/interfaces/web/static/css/components.css` GROWS:
  - `.agent-tile` + `.agent-tile-delete` — canonical tile primitives (~30-50 LOC). `.agent-tile-delete` composes with `.list-item-delete` reveal pattern.
  - `.list-item.confirm-delete` — generic two-step confirm rules lifted from chat.css's `.session-item.confirm-delete` (3 rules, ~5 LOC).
- `the_one/interfaces/web/static/css/chat.css` SHRINKS by ~5 LOC (the 3 `.session-item.confirm-delete*` rules removed; the generic `.list-item.confirm-delete` in components.css now applies via composition since `.session-item` already extends `.list-item`).
- `the_one/interfaces/web/static/css/studio.css` SHRINKS:
  - Remove `.agent-item.confirm-delete`, `.agent-item-name`, `.agent-item-delete svg` rules (lines 14-17).
  - Add `.agent-tile-grid` (CSS grid `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))`) — studio-specific layout only.
  - Net delta: small (~0 to -5 LOC; the tile-grid layout replaces the now-removed list-item rules).
- `the_one/interfaces/web/static/index.html` gains `<script src="/static/js/confirm.js"></script>` between `markdown.js` (line 28) and the chat sub-modules.
- `the_one/agents.md` — add a "Confirm-delete (in-place two-step)" entry to §Design system → "Affordance vocabulary" documenting `App.confirmDelete` API + the `data-confirm-title` hook + the canonical `.list-item.confirm-delete` rule + the keydown-bubble fix as the parent's responsibility (NOT the helper's).
- New tests: `tests/browser/test_flow_studio_navigation.py` extended (or NEW `test_flow_agent_tile.py`) — covers tile-grid layout (`.agent-tile-grid` present, tiles have testid + data-name + aria-selected), tile click → editor, tile delete two-step (first-click confirm prompt, second-click delete, revert after timeout, keydown-bubble fix verified by pressing Enter on the X-button without entering the editor).
- Existing chat session-delete behavior preserved — no chat browser test regressions.

## Acceptance Criteria

- [x] Studio's Agents section content shows a CSS-grid container (`.agent-tile-grid`) with tiles laid out via `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))` (or equivalent in `studio.css`). The grid replaces the previous flex `.agent-list` layout.
- [x] Each tile root carries: `data-testid="agent-item"`, `data-name="{agent.name}"`, `aria-selected="true|false"`. **DOM structure**: the tile root is a wrap `<div class="agent-tile-wrap">` containing two siblings — `<button class="agent-tile" type="button">` (the activatable tile) and `<button class="list-item-delete agent-tile-delete" type="button">` (the X-button). The wrap is needed because nesting a `<button>` inside another `<button>` is invalid HTML. **Attribute placement**: `data-testid="agent-item"`, `data-name`, `aria-selected` live on the inner `.agent-tile` button (so `test_flow_hash_routing.py:124` continues to match `.agent-item[data-name="..."][aria-selected="true"]`).
- [x] Every `.agent-tile` button is a natural tab stop (default `<button>` behavior). No custom `tabindex` management on tiles. The X-button is a separate tab stop after its parent tile (rendered as a sibling, so it's the next focusable element after the tile button in DOM order — Tab from a tile lands on its X-button next).
- [x] Tile content (inside the `.agent-tile` button): (a) agent name in a large bold span (`data-confirm-title` attribute on this span — the `App.confirmDelete` title hook), (b) description span with `-webkit-line-clamp: 2` (2-line clamp + ellipsis), (c) footer caption span styled in monospace showing `<provider-config-display-name> · <model>` (use the existing studio data the editor already loads; if a tile has no provider configured, render an empty footer or "no provider" caption — pick during impl).
- [x] Hover OR focus-within on `.agent-tile-wrap` reveals the X-button. The X-button uses `<button class="list-item-delete agent-tile-delete" type="button" aria-label="Delete agent {name}">`. **Testid clash avoidance**: the existing `data-testid="delete-agent-btn"` is on the editor's "Delete Agent" button at `studio.js:380` (used by `test_flow_agent_crud.py:58, 73` to click the editor button when an agent is selected). The new tile X-button MUST use a different testid: `data-testid="agent-tile-delete-btn"`. The editor button keeps its existing `delete-agent-btn` testid unchanged.
- [x] Tile click (the `.agent-tile` button) calls `selectAgent(agent)`. Pressing Enter or Space on a focused tile activates `selectAgent(agent)` — UNLESS the keydown originated from a child element bubbling up. Since the X-button is now a sibling (not a child), the bubble guard `if (e.target !== el) return;` is still applied as defensive depth (in case the tile's content children gain focusable descendants in the future).
- [x] **Keydown-bubble fix**: Pressing Enter on a focused X-button triggers the delete flow (first click of the two-step confirm). It does NOT also call `selectAgent`. With the wrap-with-siblings pattern, this is naturally guaranteed (the X-button is not a descendant of the tile button, so its key events do not bubble to the tile's keydown listener). The leg also retains the `if (e.target !== el) return;` guard inside the tile's keydown listener as defensive depth for future content children. Verified via a new browser test.
- [x] **Tile attribute preservation**: `data-testid="agent-item"`, `data-name="{name}"`, `aria-selected="true|false"` all carry forward on the inner `.agent-tile` button. `tests/browser/test_flow_hash_routing.py:124` (`.agent-item[data-name="{name}"][aria-selected="true"]`) passes without modification. `tests/browser/test_flow_agent_crud.py` selectors at lines 25 (`agent-empty`), 30 (`new-agent-btn`), 52 + 80 (`agent-item`), 58 + 73 (`delete-agent-btn` — editor button, NOT tile X) all pass without modification.
- [x] **Editor's "Delete Agent" button is OUT OF SCOPE for leg 02**. The editor's two-step delete flow at `studio.js:590-611` (with its capital-D "Confirm Delete?" label, on the editor button at `studio.js:380` carrying `data-testid="delete-agent-btn"`) is NOT migrated to `App.confirmDelete` in this leg. It keeps its existing inline implementation. Migration to the canonical helper is captured as a Known Issue / future debrief item — the divergence (capital-D vs lowercase-d) is a design-system smell to unify in a follow-up flight.
- [x] **`+ New Agent` button** stays at `studio.js:117-119` inside `.studio-agents-header` with `data-testid="new-agent-btn"`. Its visual treatment aligns with chat's `.new-chat-header` button — same `.btn-outlined-cyan` class, same icon system. No relocation in this leg (already done in leg 01).
- [x] **NEW `App.confirmDelete(itemEl, onConfirm, opts)` helper** in `static/js/confirm.js` (~50-80 LOC). Signature:
  - Args: `itemEl` (the parent activatable element bearing the title-text and `confirm-delete` class state), `onConfirm: (itemEl, revertFn) => void` (called on second click), `opts: {titleSelector?: string, confirmLabel?: string, revertMs?: number}` (optional).
  - Defaults: `titleSelector = '[data-confirm-title]'`, `confirmLabel = 'Confirm delete?'`, `revertMs = 3000`.
  - Behavior: First call (when `itemEl` does NOT have `confirm-delete` class) — adds the class, replaces the title element's text with `confirmLabel`, starts a `revertMs` timer that on expiry restores the original text and removes the class. Second call (when `itemEl` HAS `confirm-delete` class within the timer window) — clears the timer, calls `onConfirm(itemEl, revertFn)`. The `revertFn` (when invoked by the caller) restores the original title text and removes the `confirm-delete` class — for transport failures.
  - The helper does NOT add a keydown bubble guard — the bubble check belongs to the parent activatable element (per the resolved Open Question).
  - Idempotent on rapid double-invocation (e.g., quick double-click): the second call enters the second-click branch correctly.
  - The helper DOES NOT manage focus state — focus remains where the browser places it.
- [x] **Chat session-delete migrated**: chat.js's `onDelete` callback at `chat.js:427-445` is rewritten to call `App.confirmDelete(item, function(item, revertFn) { ws.send(...delete_session...); }, {})` (using defaults). The session-item template (in `App.chat.renderSessionList` or wherever the session item DOM is built) adds `data-confirm-title` to `.session-item-title`. Net chat.js delta: ~-15 LOC.
- [x] **Studio agent-tile delete migrated**: studio's `deleteAgentInline(name, el)` is rewritten to call `App.confirmDelete(el, function(el, revertFn) { fetch(...DELETE...).catch(() => revertFn()); }, {})`. The tile template adds `data-confirm-title` to the agent-name span. The DELETE fetch's `.catch` calls `revertFn()` so the UI rolls back on transport failure. Net studio.js delta: ~-15 LOC.
- [x] **CSS migration**: chat.css's three `.area-chat .session-item.confirm-delete*` rules at lines 89-92 (plus the comment at line 89) are REMOVED. components.css gains generic confirm-delete rules (~5-8 LOC) using a multi-selector list (`.list-item.confirm-delete, .agent-tile.confirm-delete`) so the same rules cover both chat session items (which extend `.list-item`) and studio tiles (which use `.agent-tile` standalone). studio.css's `.agent-item.confirm-delete` rule at line 14-15 is REMOVED. **Tile classing**: `.agent-tile` does NOT compose with `.list-item` — the tile is structurally a grid cell, not a list row, with different padding/border/layout primitives. Multi-selector is the chosen approach (avoids inheritance conflicts).
- [x] **Components.css adds `.agent-tile` + `.agent-tile-delete` primitives** (~30-50 LOC) under `@layer components`: tile padding, border, background, hover/focus states using F4 tokens; tile name typography (large, bold); description 2-line clamp; footer caption (monospace, smaller); `.agent-tile-delete` positioned top-right, hidden by default, revealed via `:hover` or `:focus-within` (composes with F4 `.list-item-delete` if used; otherwise standalone).
- [x] **studio.css gains `.agent-tile-grid` only** (CSS grid layout); removes `.agent-item*` legacy rules. Target: shrinkage of ~3-5 LOC or net-neutral.
- [x] **`data-confirm-title` attribute hook** added in two sites: chat session-item title element (via the `App.chat.renderSessionList` helper or the inline session-item template), and the studio agent-tile name span. No other consumers in this leg.
- [x] **index.html** gains exactly one new `<script>` line: `<script src="/static/js/confirm.js"></script>`, inserted between line 28 (`markdown.js`) and the chat sub-modules block.
- [x] **All existing tests pass**: `pytest --timeout=60 tests/` returns exactly 407, `pytest --timeout=120 -m browser tests/browser/` returns ≥ 137 + new tests added by this leg (3-5 new tests targeting tile grid + tile delete + keydown-bubble fix).
- [x] **New browser tests** (in `test_flow_studio_navigation.py` extension OR new `test_flow_agent_tile.py`):
  - Tile grid renders (`.agent-tile-grid` selector visible, multiple tiles render as `<button class="agent-tile">`).
  - Tile click navigates to editor (selects the agent).
  - Tile delete two-step: first click on X-button shows confirm prompt; second click within 3s fires DELETE; tile is removed.
  - Tile delete revert: first click on X-button → wait ~3.5s → confirm prompt cleared (tile back to normal).
  - Keydown-bubble fix: focus the X-button via Tab, press Enter, observe the delete prompt fires WITHOUT the editor opening (no `selectAgent` side-effect).
- [x] **Existing chat session-delete behavior preserved** — manual or test-based check that two-click session delete still works in chat.
- [x] **Single canonical confirm-delete pattern** — `grep -rn 'confirm-delete' the_one/interfaces/web/static/` shows uses ONLY in `confirm.js`, `studio.js` (test selectors), and `chat.js` (test selectors). No CSS rules outside `components.css`. No second inline implementation.
- [x] Flight log updated with `### 02-tile-grid-and-confirm-extractions` progress entry.
- [x] This leg's status set to `landed`.

## Verification Steps

- `pytest --timeout=60 tests/` — passes baseline (exactly 407).
- `pytest --timeout=120 -m browser tests/browser/` — passes ≥ 140 (137 baseline + 3-5 new for this leg).
- `pytest --timeout=120 -m browser tests/browser/test_flow_agent_crud.py` — passes unmodified (existing testids + delete two-step behavior preserved).
- `pytest --timeout=120 -m browser tests/browser/test_flow_chat*.py` — passes unmodified (chat session-delete migration is behavior-preserving).
- `pytest --timeout=120 -m browser tests/browser/test_flow_hash_routing.py` — passes unmodified (`aria-selected` + `data-name` carry forward).
- `grep -n 'confirm-delete' the_one/interfaces/web/static/css/chat.css` — returns zero matches (rules lifted to components.css).
- `grep -n 'confirm-delete' the_one/interfaces/web/static/css/studio.css` — returns zero matches (rules lifted to components.css).
- `grep -n 'App.confirmDelete' the_one/interfaces/web/static/js/` — returns one definition (in confirm.js) and two consumers (chat.js, studio.js).
- `grep -n 'App.router.replaceSub' the_one/interfaces/web/static/js/areas/studio.js` — still returns exactly one site (the `_writeUrl` helper from leg 01 — unchanged).
- Manual browser check: open studio, observe tile grid; hover a tile to see X-button; click X to see "Confirm delete?"; second click deletes; refresh; first click + 3s wait → tile reverts; Tab to X-button + Enter → delete prompt fires without entering the editor.
- `wc -l the_one/interfaces/web/static/css/components.css` — grows by ~35-55 LOC (`.agent-tile`, `.agent-tile-delete`, generic `.list-item.confirm-delete`).
- `wc -l the_one/interfaces/web/static/css/studio.css` — neutral or small shrinkage (the legacy agent-item rules removed; tile-grid layout added).
- `wc -l the_one/interfaces/web/static/css/chat.css` — shrinks by ~5 LOC (`.session-item.confirm-delete*` removed).

## Implementation Guidance

1. **Create `the_one/interfaces/web/static/js/confirm.js`** with the `App.confirmDelete` helper.
   - Module pattern: `(function (window) { ... window.App = window.App || {}; window.App.confirmDelete = function (itemEl, onConfirm, opts) { ... }; })(window);`
   - **Implementation outline** — note that `originalText` is captured ONLY in the first-click branch and stored on `itemEl._confirmOriginalTitle`:
     ```
     opts = opts || {};
     var titleSelector = opts.titleSelector || '[data-confirm-title]';
     var confirmLabel = opts.confirmLabel || 'Confirm delete?';
     var revertMs = opts.revertMs || 3000;
     var titleEl = itemEl.querySelector(titleSelector);

     function revert() {
       if (itemEl._confirmRevertTimer) {
         clearTimeout(itemEl._confirmRevertTimer);
         itemEl._confirmRevertTimer = null;
       }
       itemEl.classList.remove('confirm-delete');
       if (titleEl && itemEl._confirmOriginalTitle != null) {
         titleEl.textContent = itemEl._confirmOriginalTitle;
       }
       itemEl._confirmOriginalTitle = null;
     }

     if (itemEl.classList.contains('confirm-delete')) {
       // Second click within the revert window — commit.
       if (itemEl._confirmRevertTimer) {
         clearTimeout(itemEl._confirmRevertTimer);
         itemEl._confirmRevertTimer = null;
       }
       // Pass revert as the rollback callback for transport-failure paths.
       onConfirm(itemEl, revert);
       return;
     }

     // First click — arm. Capture original title NOW (before the swap).
     itemEl._confirmOriginalTitle = titleEl ? titleEl.textContent : '';
     itemEl.classList.add('confirm-delete');
     if (titleEl) titleEl.textContent = confirmLabel;
     itemEl._confirmRevertTimer = setTimeout(revert, revertMs);
     ```
   - **Why capture in the first-click branch**: on the second click, the title already displays `confirmLabel` — capturing then would record the placeholder, not the original name, and revert would overwrite the user's data with `'Confirm delete?'`.
   - **Multiple items concurrently armed**: if the user clicks delete on tile A (arms a timer), then on tile B before A reverts, both tiles are simultaneously in `.confirm-delete` state. Each tile has its own `_confirmRevertTimer` and `_confirmOriginalTitle`, so they revert independently. Acceptable.
   - **Helper does NOT add a keydown bubble guard** — that responsibility lives on the parent activatable element, per the resolved Open Question.

2. **Add `confirm.js` to index.html**. Verify exact line numbers post-leg-01 — leg 01 added three new `<script>` tags for studio sub-modules. Insertion point: after `markdown.js`, before the chat sub-modules block. Single line: `<script src="/static/js/confirm.js"></script>`.

3. **Add `data-confirm-title` to chat session items**:
   - Edit `the_one/interfaces/web/static/js/areas/chat/history-buckets.js:47` (the line where `.session-item-title` is created). Add `data-confirm-title` attribute to the title element.
   - Confirmed: `chat/history-buckets.js:37` shows `<div class="list-item session-item">` — the session item composes both classes, so the generic `.list-item.confirm-delete` rule will apply automatically once the area-specific chat.css rules are removed.

4. **Migrate chat.js's inline two-step delete** (current lines 427-445):
   - Replace the current `onDelete(id, btn)` callback body with:
     ```
     onDelete: function (id, btn) {
       var item = btn.closest('.session-item');
       App.confirmDelete(item, function (item, revertFn) {
         ws.send(JSON.stringify({ action: 'delete_session', session_id: id }));
         // WS delete is fire-and-forget; revertFn unused
       }, {});
     }
     ```
   - Net delta: ~-15 LOC.
   - Verify chat session-delete tests still pass.

5. **Add `data-confirm-title` to the studio agent-tile name span** (in the new tile template, see step 6).

6. **Rewrite `renderAgentList()`** in studio.js:231-279:
   - Container: `<div class="agent-tile-grid" aria-label="Agents">`. Drop the legacy `role="listbox"` — the new structure is a grid of buttons, not a listbox.
   - **DOM structure per agent** (wrap-with-siblings, NOT nested-button):
     ```html
     <div class="agent-tile-wrap">
       <button class="agent-tile" type="button"
               data-testid="agent-item"
               data-name="{name}"
               aria-selected="true|false"
               aria-label="{name}">
         <span class="agent-tile-name" data-confirm-title>{name}</span>
         <span class="agent-tile-description">{description || ''}</span>
         <span class="agent-tile-meta">{provider} · {model}</span>
       </button>
       <button class="list-item-delete agent-tile-delete" type="button"
               data-testid="agent-tile-delete-btn"
               aria-label="Delete agent {name}">
         <svg>{X icon}</svg>
       </button>
     </div>
     ```
   - **Testid choice**: the X-button uses `data-testid="agent-tile-delete-btn"` (NEW). Do NOT use `data-testid="delete-agent-btn"` — that one is on the editor's "Delete Agent" button (`studio.js:380`) and reusing it here would create a Playwright locator clash.
   - X-button click handler: `e.stopPropagation(); deleteAgentInline(agent.name, tileEl);` — `tileEl` is the inner `.agent-tile` button (the element that bears the `data-confirm-title` span and the `confirm-delete` class state). Note: with the X-button as a sibling (not a descendant of the tile button), `stopPropagation` is no longer strictly necessary for click-bubbling-into-tile, but keep it for defensive depth.
   - Tile click handler: `tileEl.onclick = function() { selectAgent(agent); };`.
   - Tile keydown listener: `tileEl.addEventListener('keydown', function(e) { if (e.target !== tileEl) return; if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectAgent(agent); } });`. **The `e.target !== tileEl` guard is defensive depth** for any future descendants of the tile button — with the wrap pattern, the X-button is a SIBLING, so its key events do not bubble through the tile button at all (different DOM parent).
   - Verify: focusing the X-button via Tab and pressing Enter triggers ONLY the delete flow, not `selectAgent`.

7. **Migrate `deleteAgentInline(name, el)`** at studio.js:281-311:
   - Read the current implementation to identify the existing post-DELETE reload helper. The current code at studio.js:283-299 calls `loadAll()` after a successful DELETE (also resets `selectedAgent` and selects-first-or-renders-empty). Preserve that post-delete cleanup.
   - Replace the body with:
     ```
     function deleteAgentInline(name, el) {
       App.confirmDelete(el, function (el, revertFn) {
         fetch('/api/agents/' + encodeURIComponent(name), { method: 'DELETE' })
           .then(function (r) {
             if (!r.ok) throw new Error('delete failed: ' + r.status);
             // Reset selection + reload list (mirrors current flow at studio.js:283-299).
             if (self._selectedAgent && self._selectedAgent.name === name) {
               self._selectedAgent = null;
               self._writeUrl();  // URL falls back to '#studio/agents'
             }
             loadAll();  // existing reload helper; re-fetches agents and re-renders the grid
           })
           .catch(function (err) {
             console.error(err);
             revertFn();
             // Optionally surface a flash error
           });
       }, {});
     }
     ```
   - The helper signature passes `el` = the tile button. The `data-confirm-title` selector finds the tile's name span.
   - Net delta: ~-15 LOC.
   - **`test_flow_agent_crud.py` lines 72-78 are the EDITOR's delete two-step flow** (clicks `[data-testid="delete-agent-btn"]` which is the editor button at `studio.js:380`, NOT the tile X). The editor flow is OUT OF SCOPE for leg 02 — it keeps its existing inline implementation. The tile X-button uses the NEW `App.confirmDelete` helper with the lowercase `'Confirm delete?'` label, but no existing test exercises that path; new tile-delete tests added in step 13 cover it.

8. **Add `.agent-tile` + `.agent-tile-delete` rules to components.css** (`@layer components` block):
   - Tile: padding, border (using F4 token `--border` or similar), border-radius, background (`--surface`), `cursor: pointer`, transitions on hover/focus.
   - `:hover` and `:focus-visible`: brighter border, subtle shadow, accent ring.
   - `[aria-selected="true"]`: stronger accent treatment.
   - `.agent-tile-delete`: positioned `top: 8px; right: 8px;` (or token-based), hidden by default (`opacity: 0; pointer-events: none;`), revealed via `.agent-tile:hover .agent-tile-delete`, `.agent-tile:focus-within .agent-tile-delete`, `.agent-tile-delete:focus-visible`.
   - Tile content typography: `.agent-tile-name` (large, bold), `.agent-tile-description` (caption with 2-line `-webkit-line-clamp: 2; display: -webkit-box; -webkit-box-orient: vertical; overflow: hidden;`), `.agent-tile-meta` (monospace, smaller, muted color).
   - Total: ~30-50 LOC.

9. **Lift `.session-item.confirm-delete` rules from chat.css to components.css** as `.list-item.confirm-delete`:
   - Old chat.css rules (lines 89-92):
     ```css
     /* Two-step delete confirm state on session items (mirrors studio.css). */
     .area-chat .session-item.confirm-delete { border: 1px solid var(--status-danger); }
     .area-chat .session-item.confirm-delete .session-item-title { color: var(--status-danger); }
     .area-chat .session-item.confirm-delete .list-item-delete { color: var(--status-danger); opacity: 1; display: block; }
     ```
   - **Composition reality check**: chat session items already render as `<div class="list-item session-item">` (verified at `chat/history-buckets.js:37`). So once the chat-area-specific rules are removed and a generic `.list-item.confirm-delete` rule lands, chat session items inherit the danger styling automatically. Studio tiles do NOT extend `.list-item` (they use `.agent-tile` standalone, since the tile is structurally a grid cell, not a list row). The components.css rule must therefore use a multi-selector list:
   - Generic version in components.css:
     ```css
     /* Two-step confirm-delete state (canonical; lifted from chat.css per F5 leg 02). */
     .list-item.confirm-delete,
     .agent-tile.confirm-delete { border: 1px solid var(--status-danger); }
     .list-item.confirm-delete [data-confirm-title],
     .agent-tile.confirm-delete [data-confirm-title] { color: var(--status-danger); }
     .list-item.confirm-delete .list-item-delete,
     .agent-tile.confirm-delete + .agent-tile-delete { color: var(--status-danger); opacity: 1; display: block; }
     ```
   - Note: with the wrap-with-siblings pattern, the X-button is NOT a descendant of `.agent-tile`, so the descendant combinator (`.agent-tile.confirm-delete .list-item-delete`) would not match the tile's X. Use the `+` adjacent-sibling combinator: `.agent-tile.confirm-delete + .agent-tile-delete` matches the X-button button that immediately follows a confirm-armed tile button (the wrap-with-siblings DOM places them as adjacent siblings). For chat session items, the existing `.list-item.confirm-delete .list-item-delete` descendant rule still matches because chat's X-button IS a descendant of `.list-item`. One rule list, two selectors, both correct.
   - The `[data-confirm-title]` selector matches whatever element bears the new attribute hook (chat session items add it to `.session-item-title`; studio tiles add it to `.agent-tile-name`).
   - Remove chat.css lines 89-92 entirely (including the comment).
   - Remove `studio.css:14-15` `.area-studio .agent-item.confirm-delete` rule.

10. **Update studio.css**:
    - Remove `.area-studio .agent-item.confirm-delete` (lines 14-15).
    - Remove `.area-studio .agent-item-name` (line 16).
    - Remove `.area-studio .agent-item-delete svg` (line 17).
    - Add `.area-studio .agent-tile-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: <token>; }` — this is the studio-specific layout.
    - Optional: studio-specific tile sizing tweaks (e.g., min-height) — only if the canonical tile in components.css doesn't suit the agents grid. Comment any override with `/* studio override: <reason> */`.
    - Remove the `.area-studio .agent-list { ... }` rule if the `.agent-list` selector is no longer used. Verify: studio.js still references `.agent-list` anywhere? If not, remove. (After the rewrite, only `.agent-tile-grid` is the container.)

11. **Run `pytest --timeout=60 tests/`** — should still be exactly 407.
12. **Run `pytest --timeout=120 -m browser tests/browser/`** — should be ≥ 140. New tests added in step 13 ride along.
13. **Add browser tests**:
    - Either extend `tests/browser/test_flow_studio_navigation.py` with tile-grid + delete tests, OR create `tests/browser/test_flow_agent_tile.py`. Pick whichever results in fewer ~80-120 LOC. Recommended: extend `test_flow_studio_navigation.py` for cohesion (the navigation file already covers the Agents section).
    - Cover: tile grid rendering, tile click, two-step delete (first click → prompt, second click → DELETE, tile gone), revert after timeout, keydown-bubble fix.
14. **Update `the_one/agents.md`**:
    - Add a "Confirm-delete (in-place two-step)" entry to §Design system → "Affordance vocabulary" with the `App.confirmDelete` API + the `data-confirm-title` hook + the canonical `.list-item.confirm-delete` rule + the keydown-bubble note (parent's responsibility).
    - Add an "Agent tile" entry documenting `.agent-tile` / `.agent-tile-delete` / `.agent-tile-grid` + the tile composition contract.
15. **Update flight log** — add `### 02-tile-grid-and-confirm-extractions` progress entry.
16. **Set leg status to `landed`**. Do NOT commit. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Concurrent timers across multiple confirm-delete sites**: if user arms confirm on tile A, then tile B, both timers run independently. `App.confirmDelete` stores its timer on `itemEl._confirmRevertTimer` so each item has its own.
- **Original-title preservation across revert/re-arm**: if user arms confirm, lets it revert, then arms again, the second arm captures the original text correctly because revert restored it before the second call. Verify in implementation that `originalText` is captured fresh on each first-click branch (not closured at outer scope).
- **`<button>` inside `<button>` (resolved)**: nesting a `<button>` inside another `<button>` is invalid HTML. The leg uses the **wrap-with-siblings pattern**: `<div class="agent-tile-wrap"><button class="agent-tile">...</button><button class="agent-tile-delete">X</button></div>`. The wrap div owns the `:hover` / `:focus-within` state for revealing the X-button; the tile button and X-button are independent focus stops. Reflected in AC + Implementation step 6 + CSS step 9. Documented in agents.md.
- **Migration of `data-name` ATTRIBUTE**: `data-name="{name}"` and `aria-selected="true|false"` live on the inner `.agent-tile` button (the element bearing `data-testid="agent-item"`). The wrap div bears no test-relevant attributes — it's a pure layout primitive. Test `test_flow_hash_routing.py:124` queries `.agent-item[data-name="..."][aria-selected="true"]`; that selector matches the tile button (since `agent-item` is the testid). Confirm in step 6.
- **Composition vs. multi-class**: the leg description suggests `<button class="list-item agent-tile">` as composition, but the tile is structurally different from a list-item (grid cell vs. row, different padding, different content layout). The cleaner pattern is: `<button class="agent-tile">` standalone, with the generic `.list-item.confirm-delete, .agent-tile.confirm-delete` selector list in components.css (covered in step 9). Document the choice.
- **Grid layout vs. CSS-grid `auto-fill` minmax**: `repeat(auto-fill, minmax(280px, 1fr))` ensures tiles wrap to fill available space. Verify in browser at narrow viewport (~640px width); at very narrow widths, tiles stack vertically.
- **Empty state**: when there are zero agents AND active section is Agents, render `agent-empty` (existing testid) instead of the empty grid container. Verify the existing empty state still appears.
- **Existing studio tests' delete two-step assertion** at `test_flow_agent_crud.py:72-78` exercises the EDITOR'S "Delete Agent" button (`studio.js:380`, two-step flow at `studio.js:590-611`, capital-D label "Confirm Delete?"). The leg does NOT migrate that flow — the editor button keeps its existing inline implementation. The new `App.confirmDelete` (lowercase-d "Confirm delete?") only handles tile X-button + chat session-item flows. The casing divergence is a known design-system smell to unify in a follow-up flight.
- **`delete-agent-btn` testid clash avoidance**: `data-testid="delete-agent-btn"` stays on the editor's "Delete Agent" button only. The new tile X-button uses `data-testid="agent-tile-delete-btn"`. Playwright locators in existing tests (lines 58, 73) match a single element only — no ambiguity introduced.

## Files Affected

- `the_one/interfaces/web/static/js/confirm.js` — NEW (~50-80 LOC).
- `the_one/interfaces/web/static/js/areas/studio.js` — `renderAgentList()` rewrite (+~30 LOC, -~25 LOC for rendering); `deleteAgentInline` migration (~-15 LOC); keydown-bubble guard (+1 line). Net: ~-10 LOC; new total ~1020.
- `the_one/interfaces/web/static/js/areas/chat.js` — onDelete migration (~-15 LOC); new total ~590.
- `the_one/interfaces/web/static/js/areas/chat/<session-list-helper>.js` — add `data-confirm-title` to title element (+1 attribute; possibly +1 line).
- `the_one/interfaces/web/static/css/components.css` — `+~35-55 LOC` (`.agent-tile`, `.agent-tile-delete`, generic `.list-item.confirm-delete`).
- `the_one/interfaces/web/static/css/chat.css` — `-~5 LOC` (`.session-item.confirm-delete*` rules removed).
- `the_one/interfaces/web/static/css/studio.css` — `-~3 LOC` (legacy `.agent-item*` rules removed); `+~3 LOC` (`.agent-tile-grid` layout). Net neutral or small shrinkage.
- `the_one/interfaces/web/static/index.html` — `+1 line` (`<script src="/static/js/confirm.js"></script>`).
- `tests/browser/test_flow_studio_navigation.py` (or new `test_flow_agent_tile.py`) — `+~80-120 LOC, +3-5 tests`.
- `the_one/agents.md` — `+~15 LOC` under §Design system → "Affordance vocabulary".
- `missions/04-ui-maturity/flights/05-studio-alignment/flight-log.md` — leg progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`. Flight Director defers commit to flight-end review.**

- [x] All acceptance criteria verified
- [x] All existing tests passing (`pytest --timeout=60 tests/` = 407, `pytest --timeout=120 -m browser tests/browser/` ≥ 140)
- [x] New tests passing
- [x] Existing chat session-delete tests pass unmodified (regression check for the `App.confirmDelete` extraction)
- [x] `agents.md` updated with confirm-delete + agent-tile documentation
- [x] Flight log updated with `### 02-tile-grid-and-confirm-extractions` progress entry
- [x] This leg's status set to `landed`
- [x] Do NOT check off this leg in flight.md yet (Flight Director handles at flight commit)
- [x] Do NOT commit (Flight Director commits all autonomous legs at flight-end review)
- [x] Signal `[HANDOFF:review-needed]`
