# Leg: 04-hash-routing-state

**Status**: completed
**Flight**: [App Shell Restructure](../flight.md)

## Objective

Extend hash routing from area-only (`#chat`, `#studio`, `#admin`) to area-plus-sub (`#chat/sessions/<id>`, `#studio/agents/<name>`, `#admin/providers`). Add an optional per-area `serializeState()` / `hydrateState(sub)` contract on the area descriptor passed to `App.registerArea`. Modify `switchTo` so same-area sub-state changes call only `hydrateState(sub)` (not full re-init/activate). Use `history.replaceState` for area-internal sub-navigation (no back-button pollution); cross-area navigation continues via `location.hash =` assignment which DOES push history. Implement for chat, studio, and admin. Add browser tests asserting refresh persistence per area.

## Context

This leg lands the "refresh preserves location" outcome flagged in the mission outcome. The flight spec design decisions are already finalized — this leg implements them faithfully.

Key carry-forward decisions from the flight spec:

- **Hash format**: `#area/sub` where area is required and sub is optional. Area defaults to `chat` if absent or unknown. Sub format is per-area:
  - chat: `sessions/<id>` (the session UUID, e.g., `#chat/sessions/abc-123`)
  - studio: `agents/<name>` (the agent name, e.g., `#studio/agents/coder`)
  - admin: bare category id (e.g., `#admin/providers`, `#admin/system`, `#admin/general`)

  The convention: `serializeState()` returns the sub WITHOUT the area prefix. The framework owns the `area/` segment.

- **Lifecycle ordering**:
  - **Cold entry** (first activation of an area or area-change): `init` → `activate` → `hydrateState(sub)`.
  - **Same-area sub-change**: ONLY `hydrateState(sub)` is called. `init` and `activate` do NOT re-fire.
  - **Async-dependency rule**: `hydrateState` runs synchronously after `activate` returns, but `activate` may have kicked off async work (HTTP fetches, WebSocket connect). If `hydrateState` needs data that's still loading, it MUST stash a "pending hydrate target" rather than acting immediately. The async completion handler checks the pending target and resolves it. Per area:
    - **Chat**: `joinSession` requires the WebSocket to be open. `hydrateState('sessions/<id>')` stashes `pendingJoinId`; the `session_list` WS message handler (which is the first message after WS open) checks `pendingJoinId` and joins it instead of auto-joining `sessions[0]`.
    - **Studio**: `selectAgent` requires the `agents` array to be populated. `hydrateState('agents/<name>')` stashes `pendingSelectName`; the `loadAll().then(...)` continuation checks `pendingSelectName` and selects.
    - **Admin**: `currentCategory` updates are synchronous (no fetch needed for the category-id swap itself; the per-category render kicks off its own fetch). Acceptable double-fetch on cold entry to a non-`general` sub: `init` sets `currentCategory='general'`, `activate` fetches general data, `hydrateState` switches to (e.g.) `providers` and fetches providers data. The general fetch's completion checks for the (now-removed) `.admin-form` element and bails — no visual flicker. Documented as benign.

- **`switchTo` modification**: the current early-return at line 109 (`if (areaId === currentId) return;`) becomes:
  - if `areaId === currentId` AND `sub === currentSub` → return (no-op, already there).
  - if `areaId === currentId` AND `sub !== currentSub` → call `hydrateState(sub)` only and return.
  - else → full activation flow (init+activate), then `hydrateState(sub)`.

- **History semantics**:
  - Cross-area navigation (picker click; programmatic `location.hash = 'admin'`): uses `location.hash =` assignment which DOES push history.
  - Area-internal sub-navigation (clicking a chat session, switching admin sub-page): uses `history.replaceState(null, '', newHash)` which does NOT push history. Net effect: back button exits the area; it does not walk through sub-views.
  - **Important**: `history.replaceState` does NOT fire `hashchange`, so calling `replaceState` from inside an option-click handler is safe (no recursion).

- **Area descriptor extensions** (optional fields, defaults preserve current behavior):
  ```javascript
  App.registerArea({
    id, label, icon, order,
    sidebarLabel,
    init, activate, deactivate,
    serializeState,  // optional: () => string | null  — null/undefined means "no sub"
    hydrateState,    // optional: (sub: string | null) => void
  });
  ```
  Areas without `serializeState`/`hydrateState` behave exactly as today.

- **Hashchange listener**: currently bails on non-area hashes (leg 02's skip-link guard). Now it must parse `area/sub` and dispatch. **Updated guard**:
  ```javascript
  window.addEventListener('hashchange', function () {
    var parsed = parseHash(location.hash);
    if (!parsed.area || !areas[parsed.area]) return;  // skip-link / unknown area
    switchTo(parsed.area, parsed.sub);
  });
  ```

- **`getHashArea` becomes `parseHash`**: returns `{area, sub}` instead of just `area`. Initial DOMContentLoaded path uses the parsed result; if `area` is missing/unknown, falls back to `chat`.

- **Backward compatibility**: an old `#chat`/`#studio`/`#admin` hash (no sub) parses as `{area: <id>, sub: null}` — `hydrateState(null)` is called (or skipped if the area defines no `hydrateState`). Areas without sub-state (or before this leg's per-area implementation) ignore the call.

- **`serializeState` invocation cadence**: area code calls `App.router.replaceSub(serializeState())` (new helper) whenever its internal sub-state changes (e.g., user clicks a different chat session, switches admin category). The helper handles the hash update + `replaceState` mechanics so each area doesn't re-implement them.

## Inputs

- Branch `flight/03-app-shell-restructure`; legs 01-03 landed (uncommitted per F3 batching).
- `app.js` `switchTo` at lines 107-157 (current line numbers post-leg-02). The early-return at line 109 (`if (areaId === currentId) return;`) is the modification site.
- `app.js` hashchange listener at lines 164-168.
- `app.js` `getHashArea` at lines 159-162.
- Area code state:
  - chat: `currentSessionId` is the source of truth for sub-state (`chat.js`, in the IIFE init scope).
  - studio: `selectedAgent.name` (or `null` when no agent selected).
  - admin: `currentCategory` (`'general'` / `'providers'` / `'system'`).

## Outputs

State that must exist after this leg completes:

### `app.js`

- New helper `parseHash(hashString)` returning `{area: string|null, sub: string|null}`:
  ```javascript
  function parseHash(hashString) {
    var raw = (hashString || '').replace(/^#/, '');
    if (!raw) return { area: null, sub: null };
    var slash = raw.indexOf('/');
    if (slash === -1) return { area: raw, sub: null };
    return { area: raw.slice(0, slash), sub: raw.slice(slash + 1) };
  }
  ```

- `switchTo` signature changes from `switchTo(areaId)` to `switchTo(areaId, sub)`. Body:
  ```javascript
  function switchTo(areaId, sub) {
    if (!areas[areaId]) areaId = 'chat';
    sub = (sub === undefined ? null : sub);

    // Same-area sub-change: only hydrate
    if (areaId === currentId && sub === currentSub) return;
    if (areaId === currentId && sub !== currentSub) {
      currentSub = sub;
      var hydrate = areas[areaId].hydrateState;
      if (typeof hydrate === 'function') hydrate(sub);
      return;
    }

    // Cross-area navigation: deactivate current, activate target
    if (currentId && areas[currentId]) {
      areas[currentId].deactivate();
    }

    var sidebarPanels = document.querySelectorAll('#app-sidebar .sidebar-panel');
    var contentPanels = document.querySelectorAll('#main-content .content-panel');
    for (var i = 0; i < sidebarPanels.length; i++) sidebarPanels[i].classList.remove('active');
    for (var i = 0; i < contentPanels.length; i++) contentPanels[i].classList.remove('active');

    if (!initialized[areaId]) {
      var sidebarPanel = document.createElement('div');
      sidebarPanel.className = 'sidebar-panel area-' + areaId;
      document.getElementById('app-sidebar').appendChild(sidebarPanel);

      var contentPanel = document.createElement('div');
      contentPanel.className = 'content-panel area-' + areaId;
      document.getElementById('main-content').appendChild(contentPanel);

      areas[areaId].init(sidebarPanel, contentPanel);
      initialized[areaId] = true;
    }

    var targetSidebar = document.querySelector('#app-sidebar .area-' + areaId);
    var targetContent = document.querySelector('#main-content .area-' + areaId);
    if (targetSidebar) targetSidebar.classList.add('active');
    if (targetContent) targetContent.classList.add('active');

    var asideEl = document.getElementById('app-sidebar');
    var areaLabel = areas[areaId].sidebarLabel || (areas[areaId].label + ' sidebar');
    asideEl.setAttribute('aria-label', areaLabel);

    var pickerOpts = document.querySelectorAll('.app-picker-option');
    for (var i = 0; i < pickerOpts.length; i++) {
      pickerOpts[i].classList.toggle('active', pickerOpts[i].dataset.area === areaId);
    }

    currentId = areaId;
    currentSub = sub;
    areas[areaId].activate();

    var hydrate = areas[areaId].hydrateState;
    if (typeof hydrate === 'function') hydrate(sub);
  }
  ```
  New module-scope variable `var currentSub = null;` declared near `currentId`.

- `getHashArea` REMOVED. Callsites use `parseHash` directly.

- Hashchange listener updated:
  ```javascript
  window.addEventListener('hashchange', function () {
    var parsed = parseHash(location.hash);
    if (!parsed.area || !areas[parsed.area]) return;  // skip-link / unknown area
    switchTo(parsed.area, parsed.sub);
  });
  ```

- DOMContentLoaded handler updated:
  ```javascript
  document.addEventListener('DOMContentLoaded', function () {
    renderTopBar();
    var parsed = parseHash(location.hash);
    var area = (parsed.area && areas[parsed.area]) ? parsed.area : 'chat';
    switchTo(area, parsed.sub);
  });
  ```

- New `App.router` namespace exposed via the `Object.assign` block at line 213:
  ```javascript
  router: {
    parseHash: parseHash,
    /**
     * Update the URL sub-state without pushing history. Used by area code when
     * the user navigates within an area (selects a different session/agent/category).
     * The area is implicit (currentId) — only the sub portion is updated.
     * Calling this does NOT fire hashchange (replaceState is silent), so it does
     * not loop back through switchTo.
     */
    replaceSub: function (sub) {
      if (!currentId) return;
      var newHash = sub ? '#' + currentId + '/' + sub : '#' + currentId;
      if (location.hash === newHash) return;  // no-op
      history.replaceState(null, '', newHash);
    },
  },
  ```

### `chat.js` (area extensions)

- New closure-scope variable `var pendingJoinId = null;` declared near `currentSessionId`. Used to defer hydration until the WebSocket is open.
- Add `serializeState`/`hydrateState` to the `App.registerArea({...})` descriptor:
  ```javascript
  serializeState: function () {
    return currentSessionId ? 'sessions/' + currentSessionId : null;
  },
  hydrateState: function (sub) {
    if (!sub) return;  // no sub state to apply
    if (sub.indexOf('sessions/') === 0) {
      var id = sub.slice('sessions/'.length);
      if (!id || id === currentSessionId) return;
      // Defer: WS may not be open yet on cold entry. The session_list handler
      // (which fires when the server confirms the WS connection) consumes
      // pendingJoinId in preference to its auto-join behaviour.
      pendingJoinId = id;
      // Warm path: WS is open and currentSessionId differs — join immediately
      // and clear the pending stash.
      if (ws && ws.readyState === WebSocket.OPEN) {
        joinSession(id);
        pendingJoinId = null;
      }
    }
  },
  ```

- **`replaceSub` placement**: do NOT call `replaceSub` from inside `joinSession` (which sets `currentSessionId` optimistically before WS confirms). Instead, place the call in the `session_joined` WS message handler (around chat.js:323 — the line `currentSessionId = data.session_id;`). After that assignment:
  ```javascript
  currentSessionId = data.session_id;
  if (window.App && window.App.router) {
    App.router.replaceSub('sessions/' + currentSessionId);
  }
  ```
  This catches both explicit joins (`joinSession`) and auto-creates (`new_session`) — the `session_joined` handler is the single confirmed-state mutation site.

- **`session_list` handler hydration consumption**: locate the WS message handler for `session_list` (the response received after WS opens). Its current behavior is to render the session list and auto-join `sessions[0]` if `currentSessionId` is null. Update it to check `pendingJoinId` first:
  ```javascript
  if (data.type === 'session_list') {
    sessions = data.sessions;
    renderSessionList(sessions);
    if (pendingJoinId) {
      var target = pendingJoinId;
      pendingJoinId = null;
      // Verify the session exists in the list before joining; if not, fall
      // back to the auto-join (or stay empty if nothing is available).
      var found = false;
      for (var i = 0; i < sessions.length; i++) {
        if (sessions[i].id === target) { found = true; break; }
      }
      if (found) {
        joinSession(target);
        return;
      }
      // pendingJoinId did not match — fall through to auto-join.
    }
    // Existing auto-join logic (e.g., joinSession(sessions[0].id) when current is null) follows.
  }
  ```

- **New-chat handler**: when the user clicks the new-chat button, `currentSessionId` is set to null then a `new_session` WS action is sent. The `session_joined` response carries the new id, and the `replaceSub` call fires there. Additionally, set `App.router.replaceSub(null)` immediately when `currentSessionId = null` is set (to clear the URL sub during the brief gap before the server responds):
  ```javascript
  // In newChatBtn click handler, after currentSessionId = null:
  if (window.App && window.App.router) App.router.replaceSub(null);
  ```

- **Session-deletion**: similarly, after a session is deleted and `currentSessionId` is updated (either to a new active or cleared), the `session_joined` (for the new active) OR an explicit `replaceSub(null)` (for cleared) must fire. The existing delete handler should already update `currentSessionId`; ensure both paths emit a `replaceSub`.

### `studio.js` (area extensions)

- New closure-scope variable `var pendingSelectName = null;` declared near `selectedAgent`. Used to defer hydration until the agents list loads.
- Add `serializeState`/`hydrateState`:
  ```javascript
  serializeState: function () {
    return (selectedAgent && !createMode) ? 'agents/' + encodeURIComponent(selectedAgent.name) : null;
  },
  hydrateState: function (sub) {
    if (!sub) return;
    if (sub.indexOf('agents/') === 0) {
      var name = decodeURIComponent(sub.slice('agents/'.length));
      // Defer: agents array may not be loaded yet on cold entry.
      pendingSelectName = name;
      tryConsumePendingSelect();
    }
  },
  ```

- New helper `tryConsumePendingSelect()`:
  ```javascript
  function tryConsumePendingSelect() {
    if (!pendingSelectName) return;
    if (!agents || agents.length === 0) return;  // wait for loadAll
    var target = null;
    for (var i = 0; i < agents.length; i++) {
      if (agents[i].name === pendingSelectName) { target = agents[i]; break; }
    }
    pendingSelectName = null;
    if (target && (!selectedAgent || selectedAgent.name !== target.name)) {
      selectAgent(target);
    }
  }
  ```

- **Wire `tryConsumePendingSelect()` into the existing `loadAll().then(...)` callsite** in `activate` (around studio.js:824). The current chain is roughly:
  ```javascript
  loadAll().then(function () {
    if (agents.length > 0) selectAgent(agents[0]);
    else renderEmptyEditor();
  })
  ```
  `loadAll` itself already calls `renderAgentList()` internally — do NOT re-render. Modify the existing `.then` callback so pending hydration takes priority over the default-select-first behavior:
  ```javascript
  loadAll().then(function () {
    if (pendingSelectName) {
      tryConsumePendingSelect();
      // tryConsumePendingSelect calls selectAgent if it found a match;
      // if no match (or no agents), fall through to default behavior.
      if (selectedAgent) return;
    }
    if (agents.length > 0) selectAgent(agents[0]);
    else renderEmptyEditor();
  })
  ```

- **`replaceSub` placement**: at the bottom of `selectAgent(agent)`, after `selectedAgent = agent;`:
  ```javascript
  if (window.App && window.App.router) {
    App.router.replaceSub(selectedAgent && !createMode ? 'agents/' + encodeURIComponent(selectedAgent.name) : null);
  }
  ```
  Also call `App.router.replaceSub(null)` when `selectedAgent` is cleared (e.g., post-delete or when entering create mode).

### `admin.js` (area extensions)

- Add `serializeState`/`hydrateState`:
  ```javascript
  serializeState: function () {
    return currentCategory || null;  // 'general' / 'providers' / 'system'
  },
  hydrateState: function (sub) {
    if (!sub) return;
    var validIds = ['general', 'providers', 'system'];
    if (validIds.indexOf(sub) === -1) return;
    if (currentCategory !== sub) {
      currentCategory = sub;
      providerFormMode = null;
      editingProvider = null;
      renderCategoryList();
      renderContent();
    }
  },
  ```

- After every `currentCategory` change in admin.js (locate the `el.onclick` in `renderCategoryList` at lines 114-120 — after the `currentCategory = cat.id` assignment, add the `replaceSub` call before `renderCategoryList()` and `renderContent()` execute).
  ```javascript
  if (window.App && window.App.router) App.router.replaceSub(currentCategory);
  ```

### Tests

- New file `tests/browser/test_flow_hash_routing.py` with ~4 tests:
  - `test_hash_routing_admin_subpage_persists_on_refresh`: load app, click admin, click Providers category, assert URL becomes `#admin/providers`, refresh page, assert app loads with admin area + providers sub-page active (test by checking `.admin-category-item.active` text content or `aria-selected="true"`).
  - `test_hash_routing_chat_session_persists_on_refresh`: seed a session via WebSocket, click it, assert URL becomes `#chat/sessions/<id>`, refresh, assert that session is selected (`.session-item[aria-selected="true"]` matches the seeded id).
  - `test_hash_routing_studio_agent_persists_on_refresh`: seed an agent, click it, assert URL becomes `#studio/agents/<name>`, refresh, assert that agent is loaded in the editor.
  - `test_hash_routing_unknown_area_falls_back_to_chat`: load `#nonsense/foo`, assert app loads with chat area active and `location.hash` either stays `#nonsense/foo` or normalizes to `#chat` (current implementation falls back silently — assert the active area is chat, don't assert the hash itself unless we explicitly normalize on initial load).
  - `test_hash_routing_replacestate_no_history_growth`: load app, capture `page.evaluate("history.length")` baseline, click admin (cross-area, pushes history), click Providers (replaceState — should NOT grow), click System (replaceState — should NOT grow), capture `history.length` again. Assert post-clicks length equals baseline + 1 (only the cross-area transition pushed). This directly tests the replaceState-not-pushState invariant — the design property — without depending on Playwright's unreliable `go_back()` behavior in test environments.

  Bring browser flow test count from 17 to ~22 (5 prior in test_flow_chat/agent/provider; 2 in app_fixture; 1 smoke; 4 picker; 5 keyboard; 4 hash routing — 21 total, or 22 if seeders counted; verify by enumeration after implementation).

- Existing flow tests must continue to pass.
- Visual snapshots stay drifted; leg 06 still owns regeneration.

### Documentation

- `the_one/agents.md` — extend the App shell section (or add a `### Hash routing` subsection) documenting:
  - The `#area/sub` format and per-area sub conventions (chat: `sessions/<id>`; studio: `agents/<name>` URL-encoded; admin: bare category id).
  - The `serializeState`/`hydrateState` contract on the area descriptor.
  - The `App.router.replaceSub(sub)` helper for area-internal navigation.
  - The replaceState vs hash-assignment distinction (back-button semantics).
  - The lifecycle ordering: `init` → `activate` → `hydrateState` on cold entry; `hydrateState` only on same-area sub-change.

## Acceptance Criteria

- [x] `app.js` exports `App.router.parseHash` and `App.router.replaceSub`. `parseHash('#admin/providers')` returns `{area: 'admin', sub: 'providers'}`. `parseHash('#chat')` returns `{area: 'chat', sub: null}`. `parseHash('')` and `parseHash('#')` return `{area: null, sub: null}`.
- [x] `switchTo(areaId, sub)` accepts the new sub parameter; same-area sub-change calls only `hydrateState(sub)`; cross-area follows full init+activate+hydrate ordering.
- [x] `currentSub` module variable tracks the active sub.
- [x] Hashchange listener parses `area/sub`, bails on unknown areas, dispatches `switchTo(area, sub)`.
- [x] DOMContentLoaded handler reads `parseHash(location.hash)` and switches to the parsed area + sub.
- [x] chat.js, studio.js, admin.js each define `serializeState` / `hydrateState` matching the per-area sub format.
- [x] Each area calls `App.router.replaceSub(...)` after every internal sub-state change (session join in chat, agent select in studio, category click in admin).
- [x] `pytest tests/` reports 393 passing.
- [x] `pytest -m browser tests/browser/ --ignore=tests/browser/test_visual_snapshots.py --tb=short --timeout=120` reports prior + 4 new hash-routing tests passing (target: ~21-22 flow tests). Actual: 21 passing.
- [x] Visual snapshots continue to fail (leg 06 still owns). Same 7 failing as legs 02-03.
- [x] `the_one/agents.md` documents the hash routing contract.
- [x] Manual test: load `#admin/providers`, refresh, lands on Providers tab (asserted by browser test). Load `#chat/sessions/<id>` (with a real session), refresh, that session is selected (asserted by browser test). Click between admin sub-pages — history.length invariant test confirms no extra history entries pushed (replaceState).

## Verification Steps

- `grep -n "parseHash\|replaceSub\|hydrateState\|serializeState\|currentSub" the_one/interfaces/web/static/js/` recursive — confirms the new APIs are wired.
- `pytest tests/ --tb=short --timeout=60` → 393 passing.
- `pytest -m browser tests/browser/ --ignore=tests/browser/test_visual_snapshots.py --tb=short --timeout=120` → all flow tests passing including the 4 new hash-routing tests.
- Manual browser: open the app at `/`, click admin, click Providers — URL becomes `#admin/providers`. Refresh — Providers tab is active. Click System — URL becomes `#admin/system`, no extra back-stack entry. Press back — URL exits admin.

## Implementation Guidance

1. **Refactor `getHashArea` → `parseHash`** in app.js

   Remove the `getHashArea` function (lines 159-162). Add `parseHash` per the code block in Outputs > app.js. Update both callsites: hashchange listener and DOMContentLoaded handler.

2. **Modify `switchTo` to accept sub**

   Add `var currentSub = null;` near the existing `var currentId = null;` declaration (line 4). Update `switchTo` per the code block in Outputs > app.js. Key behaviors:
   - Early-return only when BOTH area and sub match.
   - Same-area sub-change calls only `hydrateState(sub)` (no init/activate/deactivate).
   - Cross-area follows full lifecycle, ending in `hydrateState(sub)`.

3. **Update hashchange listener and DOMContentLoaded** per Outputs.

4. **Add `App.router` to the namespace export** at the bottom of `app.js`'s IIFE:
   ```javascript
   Object.assign(window.App, {
     registerArea: registerArea,
     router: {
       parseHash: parseHash,
       replaceSub: function (sub) {
         if (!currentId) return;
         var newHash = sub ? '#' + currentId + '/' + sub : '#' + currentId;
         if (location.hash === newHash) return;
         history.replaceState(null, '', newHash);
       },
     },
     escapeHtml: escapeHtml,
     escapeAttr: escapeAttr,
     formatBytes: formatBytes,
     showFlash: showFlash,
   });
   ```

5. **Extend chat.js area descriptor**

   Add `serializeState` and `hydrateState` to the `App.registerArea({...})` call (top of `chat.js`). Locate `joinSession` and the session-delete WebSocket handler; after each `currentSessionId` mutation, call:
   ```javascript
   if (window.App && window.App.router) {
     App.router.replaceSub(currentSessionId ? 'sessions/' + currentSessionId : null);
   }
   ```

   The `joinSession(id)` function: after the WebSocket sends the join action AND the server responds with the session id (which sets `currentSessionId`), call `replaceSub`. Specific site: the "joined" message handler in the WebSocket onmessage path. If unsure of the exact site, place the call after every `currentSessionId =` assignment as the simplest defensible rule.

6. **Extend studio.js area descriptor**

   Add `serializeState`/`hydrateState`. Locate `selectAgent(agent)` (the function set as the option's click handler); after `selectedAgent = agent;` (or whatever the assignment is), append the `replaceSub` call:
   ```javascript
   if (window.App && window.App.router) {
     App.router.replaceSub(selectedAgent && !createMode ? 'agents/' + encodeURIComponent(selectedAgent.name) : null);
   }
   ```
   Also call `App.router.replaceSub(null)` when transitioning to create-mode or when no agent is selected (e.g., `selectedAgent = null` after delete).

7. **Extend admin.js area descriptor**

   Add `serializeState`/`hydrateState`. In `renderCategoryList`'s `el.onclick` handler (admin.js:114-120), insert the `replaceSub` call after `currentCategory = cat.id` and before `renderCategoryList()`:
   ```javascript
   el.onclick = function () {
     currentCategory = cat.id;
     providerFormMode = null;
     editingProvider = null;
     if (window.App && window.App.router) App.router.replaceSub(currentCategory);
     renderCategoryList();
     renderContent();
   };
   ```

8. **Add hash-routing tests**

   Create `tests/browser/test_flow_hash_routing.py` with 4 tests per the leg's Outputs > Tests section. Use `app_with_provider` / `app_with_agent` fixtures where seeded state is needed; for the admin sub-page test, `app_clean` is sufficient. For the back-button test, use `page.go_back()`.

9. **Update agents.md**

   Add the hash routing contract documentation per the leg's Outputs > Documentation section.

10. **Run tests and verify**

    ```
    pytest tests/ --tb=short --timeout=60
    pytest -m browser tests/browser/ --ignore=tests/browser/test_visual_snapshots.py --tb=short --timeout=120
    pytest -m browser tests/browser/test_visual_snapshots.py --tb=short --timeout=120
    ```

    First: 393 passing. Second: prior count (17 from leg 03) + 4 new hash-routing = ~21 passing. Third: snapshot tests still failing — record any new drift (likely none, since this leg has no DOM-shape changes).

## Edge Cases

- **`replaceState` does NOT fire `hashchange`**: this is the load-bearing property that prevents recursion. If a future change introduces `pushState` instead of `replaceState` (or `location.hash =` for sub-state), the hashchange listener would re-fire `switchTo` which would call `replaceSub` which would fire `hashchange`... Avoid that loop. Document the invariant clearly: AREA-INTERNAL = replaceState; CROSS-AREA = location.hash assignment.
- **Initial load with sub but no matching state**: e.g., user bookmarked `#chat/sessions/deadbeef-no-such-session`. `hydrateState('sessions/deadbeef-no-such-session')` calls `joinSession('deadbeef-no-such-session')`, which the WebSocket will reject (or auto-create with that id, depending on backend behavior). Acceptable: the user lands in chat with an error or empty state. Do NOT pre-validate the sub before calling hydrate; the hydrate function itself is responsible for graceful failure.
- **Async hydrate**: chat's `joinSession` is asynchronous (WebSocket round-trip). `hydrateState` returns immediately; the actual session-load happens later. This is fine — `switchTo` doesn't block on hydration. Document that `hydrateState` may complete asynchronously.
- **Hash with empty area** (`#/something`): `parseHash('#/sessions/abc')` returns `{area: '', sub: 'sessions/abc'}`. The `!parsed.area` check in the listener bails, so this is treated as no-op. Confirm.
- **Special characters in agent names**: agent names may contain spaces (`my agent`) which encode as `my%20agent` in the hash. Use `encodeURIComponent` in `serializeState` and `decodeURIComponent` in `hydrateState`. Test with at least one agent name containing special chars in the manual verification.
- **`currentSub` reset on cross-area navigation**: when the user clicks the picker to switch to admin, the chat's `currentSessionId` does NOT change (chat's deactivate doesn't clear it). But `currentSub` (the global) DOES update because `switchTo` sets `currentSub = sub` after the cross-area path. When the user later returns to chat, `currentSessionId` is still set in chat's closure — chat's `serializeState` will return `'sessions/<old-id>'`. Good: the chat session is preserved across area switches. Verify by manual walkthrough.
- **`replaceSub` when `currentId` is null** (before DOMContentLoaded fires): early-return guard `if (!currentId) return;` prevents wild updates. Safe.
- **Old `getHashArea` callers**: confirmed only two callsites (hashchange listener, DOMContentLoaded). Removing it is safe.

## Files Affected

- `the_one/interfaces/web/static/js/app.js` — Add `parseHash`; remove `getHashArea`; update `switchTo` to accept and propagate sub; add `currentSub` module variable; expose `App.router.{parseHash, replaceSub}`; update hashchange listener and DOMContentLoaded handler.
- `the_one/interfaces/web/static/js/areas/chat.js` — Add `serializeState`/`hydrateState` to area descriptor; add `App.router.replaceSub` calls after every `currentSessionId` mutation.
- `the_one/interfaces/web/static/js/areas/studio.js` — Add `serializeState`/`hydrateState`; add `replaceSub` calls after `selectedAgent` mutations.
- `the_one/interfaces/web/static/js/areas/admin.js` — Add `serializeState`/`hydrateState`; add `replaceSub` call in `renderCategoryList`'s onclick.
- `tests/browser/test_flow_hash_routing.py` — NEW file: 4 tests covering refresh persistence per area + back-button + unknown-area fallback.
- `the_one/agents.md` — Hash routing contract documentation.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[LEG:04:landed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing per the verification plan (393 unit; 21 flow; visual snapshots still failing at 7)
- [x] Flight log updated with: leg 04 outcomes, history.length invariant test result, deviations documented
- [x] Leg status updated to `landed`
- [x] Per F3 batching: do NOT commit. Report `[LEG:04:landed]`. **This is the final leg in batch A** — after this leg completes, batch A goes to Reviewer + Accessibility Reviewer + commit phase.
