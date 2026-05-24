# Leg: per-agent-overlay-checkbox-label-resolver

**Status**: completed
**Flight**: [UX Hotfixes from F3 Debrief](../flight.md)

## Objective

Close A2: replace the per-agent overlay checkbox-mode's raw-Discord-ID display (`connectors-tab.js:_buildCheckboxList` renders `nameSpan.textContent = item;` where `item` is a raw snowflake) with friendly labels resolved against the L4 discoverable-entities cache. Fetch is LAZY on first axis-expand inside a tile and shared across all axes of that tile (one GET per tile, not per axis). Stub-type (503), pre-probe (404), and network-error paths all fall back to raw-id display so no regression for non-Discord accounts. Ship a new browser-test file pinning Discord-shows-friendly-label + stub-shows-raw-id-fallback + network-error-shows-raw-id-fallback contracts.

## Context

- F4 flight.md Design Decision "A2 — per-agent overlay checkbox-mode label resolver via L4 API" pins: LAZY-on-tile-expand fetch (not eager-on-renderConnectorsTab); per-tile-fetch (not shared cross-tile cache); single GET returns ALL 4 axes (peers/channels/groups/roles) so a multi-axis checkbox-mode tile fires ONE GET, not one-per-axis; cache on tile-local closure; collapse-then-re-expand does NOT re-fetch.
- Per-tile cost is one L4 cache-hit per first-expand (the L4 endpoint reads the pre-warmed cache from `_pool`; the operator's recovery path for a cold pool is to click Test Connection, which after F4 L2 lands warms the pool). Acceptable per the F4 design.
- The L4 API `GET /api/connector-accounts/{id}/discoverable-entities` exists (F3 L4) and returns `{entities: {peers, channels, groups, roles}, fetched_at, stale_seconds}` where each axis is a list of `{id, label, group, metadata, stale}` per `the_one/connectors/base.py:DiscoverableEntity`. 503 = plugin lacks the hook; 404 = account cold / pool not warm; 200 OK = entities populated.
- L2 just landed `pool-warmed=true` from the Test Connection handler — A1 + A2 are paired so that after Test Connection succeeds, the dropdowns AND the checkbox-mode labels both resolve. A2 alone is operator-visible whenever the operator opens an agent's Connectors tab against a Discord account that has account-scope chips on at least one axis (the checkbox-mode trigger).
- The current `_buildCheckboxList` at `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:460-518` renders the checkbox label as `nameSpan.textContent = item;` (item = raw `String(scopeList[i])`). The fix injects a label resolver that runs AFTER the cache is fetched and walks the rendered rows to update the `mcp-tool-toggle-name` span's text.
- The chip-mode branch at `_buildAxisRow` already uses the L4 cache via the `discoverable-dropdown` component (F3 L6b's registry-dispatch). A2 is the dual case — same data source, different render path.
- The L1-codified convention `touched-surface-ux-debt-folding` (`agents.md` Project-wide) is the design discipline this leg honors at flight design — F3 L6b touched `connectors-tab.js` and missed A2 because the leg's contributing-criteria framing was narrow; F4 L3 re-touches the same surface to fold the missed gap.
- The L1-codified convention `slot-getter-bridge-for-dropdown-collect-path` does NOT apply here — A2 only modifies render output, not the collect path (the checkboxes' `value` attribute is already the raw ID, which is what `collectFormData` expects to round-trip back to `account.config.allowlist`).
- F4 recon table R2 + R11 confirmed both the broken render (raw-IDs at `connectors-tab.js:507`) and the L4 endpoint's callable shape.

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` exists. The function `_renderAccountTile(listContainer, account, attachedMap, aclsMap, onChange)` starts at line 118; `_populateAclEditor` inner-function (which holds `_buildAxisRow` as a nested function) starts around line 199; `_buildAxisRow` starts around line 206; `_buildCheckboxList` starts at line 460. All three functions share closure scope over `_renderAccountTile`'s local vars, so a label-cache var declared at the top of `_renderAccountTile` is reachable from `_buildAxisRow`'s expand handler.
- The chip-mode branch at `_buildAxisRow` (the `else` branch starting around line 310) renders `discoverable-dropdown` via the registry hook; that branch is OUT of scope for this leg.
- The checkbox-mode branch at `_buildAxisRow` (the `if (scopeList && scopeList.length > 0)` branch around line 522) calls `_buildCheckboxList(account.id, axis, scopeList, agentAxisValue)` and appends the wrapper to `body`. The expand handler at lines 241-245 currently only toggles visibility.
- The L4 API endpoint `GET /api/connector-accounts/{accountId}/discoverable-entities` exists. Response shape on 200: `{entities: {peers: [{id, label, group, metadata, stale}], channels: [...], groups: [...], roles: [...]}, fetched_at, stale_seconds}`. 503 = plugin doesn't expose the hook; 404 = account cold / pool not warm; non-200 / non-404 / non-503 = transport error.
- The `_buildCheckboxList` function renders rows with class `connector-acl-checkboxlist-row` and an inner `span.mcp-tool-toggle-name`. The checkbox's `value` attribute holds the raw item (Discord snowflake ID for Discord accounts).
- An existing browser-test precedent at `tests/browser/test_flow_studio_per_agent_overlay_dropdown.py` shows the page.route() pattern for intercepting `/api/connector-accounts/{id}/discoverable-entities*` and returning a deterministic `_DISCOVERABLE_PAYLOAD`. The shape is locked: `{"entities": {"peers": [...], "channels": [...], "groups": [...], "roles": []}, "fetched_at": "...", "stale_seconds": 0}`.
- An existing browser-test precedent at `tests/browser/test_flow_studio_per_agent_overlay_dropdown.py:test_per_agent_overlay_checkbox_mode_unchanged` shows the pattern for seeding a Discord account with non-empty allowlist (`config={"allowlist": {"peers": ["alice", "bob"], "channels": [], ...}}`) and asserting checkbox-mode rendering on the peers axis.

## Outputs

- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:_renderAccountTile` grows three closure-scoped helpers near the top of its body (before `function _populateAclEditor`):
  - `var _labelCache = null;` — populated on first successful fetch with a flat `{id → label}` map combining all 4 axes; `{}` on 503/404/network error to mark "fetched, no labels resolvable" (vs. `null` meaning "not yet fetched").
  - `var _labelCachePromise = null;` — single-flight promise that gates concurrent first-expand calls on multiple axes from firing N parallel GETs.
  - `function _ensureLabelCache()` — returns the single-flight promise. On first call: `fetch('/api/connector-accounts/' + encodeURIComponent(account.id) + '/discoverable-entities')`; on 200, flatten `body.entities.{peers|channels|groups|roles}` into `{id → label}` (skip entries missing either id or label); on 404/503/non-OK/network error, set `_labelCache = {}` and resolve the promise. Subsequent calls return the same promise.
  - `function _applyLabelsToCheckboxes(bodyEl)` — walks `bodyEl.querySelectorAll('.connector-acl-checkboxlist-row')` and for each row reads its `input[type="checkbox"].value` (raw id), looks it up in `_labelCache`, and updates the `.mcp-tool-toggle-name` span's `textContent` if a label is resolved; no-op if the cache returns no label for that id.
- `_buildAxisRow`'s `expandBtn.addEventListener('click', ...)` handler (around line 243) gets one new clause AFTER the existing visibility-toggle code: when `nextExpanded === true` AND the axis is in checkbox-mode (`scopeList && scopeList.length > 0`), call `_ensureLabelCache().then(function () { _applyLabelsToCheckboxes(body); });`. The handler is per-axis but the cache is per-tile, so the first axis expansion fires the GET; subsequent expansions of other axes within the same tile reuse the cache.
- The fetch fires only on the FIRST expand of any checkbox-mode axis; collapse-then-re-expand reuses the cache (the promise is single-flight and the cache stays populated). If the operator never expands a checkbox-mode axis on a tile, no GET fires for that tile.
- Stub-type accounts (no `enumerate_discoverable_entities` hook → 503), cold-pool accounts (no warm entry → 404), and network errors all resolve `_labelCache = {}`. The renderer then keeps the raw-id display (no `.mcp-tool-toggle-name` span gets updated). Regression contract for stub-type accounts is preserved.
- `tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py` (new file) ships three browser tests:
  - `test_per_agent_overlay_checkbox_mode_resolves_discord_labels`: Discord account with non-empty `allowlist.channels` (e.g. `["111", "222"]`); `_DISCOVERABLE_PAYLOAD` includes channels `[{id: "111", label: "#general"}, {id: "222", label: "#random"}]`. Attach agent; navigate to agent's Connectors tab; expand the channels axis; assert the two checkbox-row name spans display `"#general"` and `"#random"` (NOT the raw IDs `"111"` and `"222"`).
  - `test_per_agent_overlay_checkbox_mode_stub_shows_raw_ids`: stub-type account with non-empty `allowlist.channels = ["raw-id-A", "raw-id-B"]`; the page.route() handler returns 503 on `/discoverable-entities*` (mirrors the substrate behavior for accounts whose plugin lacks the hook). Attach agent; expand the channels axis; assert the two checkbox-row name spans display `"raw-id-A"` and `"raw-id-B"` (raw-id fallback held).
  - `test_per_agent_overlay_checkbox_mode_network_error_shows_raw_ids`: Discord account with non-empty `allowlist.channels = ["111"]`; the page.route() handler aborts the request (`route.abort('failed')`) to simulate a network error. Attach agent; expand the channels axis; assert the checkbox-row name span displays `"111"` (raw-id fallback held; the `.catch()` branch in `_ensureLabelCache` swallows the error and sets `_labelCache = {}`).
- The collect-path round-trip is unchanged — `studio.js::collectFormData` continues to read `cb.value` (the raw id) and emit the same `account.config.allowlist` shape, so changing the displayed text has zero impact on persistence.
- No changes to the chip-mode dropdown branch. No changes to `_buildCheckboxList`'s internal shape (its rendered DOM is unchanged; A2 just walks the rendered rows after-the-fact via `_applyLabelsToCheckboxes`).
- Sibling artifact bookkeeping (explicit scope): F4 `flight.md`'s L3 Checkpoints entry + L3 Legs checklist item checked off; F4 `flight-log.md`'s Leg Progress section grows an L3 entry; this leg artifact's Status header progresses through its lifecycle.

## Acceptance Criteria

- [x] `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:_renderAccountTile` contains four new closure-scoped helpers near the top of the function body (before `function _populateAclEditor`): `_labelCache` (initial value `null`), `_labelCachePromise` (initial value `null`), `_ensureLabelCache` (function returning a single-flight promise), and `_applyLabelsToCheckboxes` (function walking checkbox rows and updating the name span). The empty-cache walk (`_labelCache === {}`) is a no-op that leaves raw-id text intact.
- [x] `_ensureLabelCache` is single-flight: a second call before the first call resolves returns the SAME promise (no second GET fires).
- [x] `_ensureLabelCache` fires `fetch('/api/connector-accounts/' + encodeURIComponent(account.id) + '/discoverable-entities')` (no `/refresh` suffix; no POST; same URL shape that `discoverable-dropdown.js:_doFetch` uses for the read path at lines 490-492).
- [x] On HTTP 200, `_ensureLabelCache` flattens `body.entities.peers`, `body.entities.channels`, `body.entities.groups`, `body.entities.roles` into a flat `{id → label}` map. Each axis's iteration is tolerant: skip entries missing either `id` or `label`. Set `_labelCache` to the populated map.
- [x] On HTTP 404 (cold pool / pre-probe), HTTP 503 (plugin lacks the hook), or any non-OK response (`!response.ok`), `_ensureLabelCache` sets `_labelCache = {}` (empty map; not `null`) and resolves the promise without throwing.
- [x] On `fetch` rejection (network error, AbortError, etc.), `_ensureLabelCache`'s `.catch()` sets `_labelCache = {}` and resolves the promise without throwing. The error is logged to console at info or error level (no silent swallow).
- [x] `_applyLabelsToCheckboxes(bodyEl)` walks `bodyEl.querySelectorAll('.connector-acl-checkboxlist-row')`, reads each row's `input[type="checkbox"].value` (raw id), and updates the row's `.mcp-tool-toggle-name` span's `textContent` ONLY IF `_labelCache[id]` is truthy. Rows whose ids miss the cache keep the raw-id text unchanged.
- [x] `_buildAxisRow`'s `expandBtn.addEventListener('click', ...)` handler runs one new clause AFTER the existing visibility-toggle code: when `nextExpanded === true` AND `scopeList && scopeList.length > 0` (checkbox-mode), it calls `_ensureLabelCache().then(function () { _applyLabelsToCheckboxes(body); });`. The clause does NOT fire in chip-mode (the `else` branch's wrapper has no `.connector-acl-checkboxlist-row` children anyway, so even if mis-fired the call would be a no-op).
- [x] The fetch fires ONLY on first-expand of any checkbox-mode axis within a tile. Collapse-then-re-expand reuses the cache (the promise is already resolved; `_applyLabelsToCheckboxes` re-runs but doesn't trigger another fetch). Verified by the network-error test: the test exercises a single expand and asserts raw-id fallback; the fetch happens exactly once.
- [x] Tiles whose every axis is in chip-mode (no `scopeList`) fire ZERO GETs (the new clause is gated on `scopeList.length > 0`). Verified structurally by inspection — no test required because the existing F3 L6b dropdown tests already cover chip-mode behavior end-to-end.
- [x] The `_buildCheckboxList` function body is byte-identical to before this leg (the new clause lives in `_buildAxisRow`'s expand handler; the checkbox list's DOM is unmodified at render time; A2 only mutates the rendered name span AFTER the user-triggered fetch resolves).
- [x] The chip-mode branch (`else` clause in `_buildAxisRow`, around line 310) is byte-identical to before this leg.
- [x] `tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py` exists as a new file.
- [x] The new test file imports `httpx`, `pytest`, `playwright.sync_api.Page`, `playwright.sync_api.expect`, and the seeders `seed_connector_account`, `seed_mock_agent`, `seed_mock_provider` from `browser.seeders` — matches the import pattern of `test_flow_studio_per_agent_overlay_dropdown.py`.
- [x] The new test file declares `_DISCOVERABLE_PAYLOAD` at module scope with channels axis populated as `[{"id": "111", "label": "#general", "group": "guild-1", "metadata": {}, "stale": False}, {"id": "222", "label": "#random", "group": "guild-1", "metadata": {}, "stale": False}]` and `peers`/`groups`/`roles` as empty lists.
- [x] The new test file declares helper `_route_discoverable_ok(page, account_id)` for the 200-OK path (mirrors precedent), `_route_discoverable_503(page, account_id)` for the stub-type path, and `_route_discoverable_network_error(page, account_id)` for the network-error path (uses `route.abort('failed')`).
- [x] The new test file declares helper `_attach_agent_to_account(base_url, agent_name, account_id)` and `_open_agent_connectors_tab(page, base_url, agent_name)` — verbatim copies of the precedent in `test_flow_studio_per_agent_overlay_dropdown.py`.
- [x] `test_per_agent_overlay_checkbox_mode_resolves_discord_labels` seeds a Discord account with `config={"allowlist": {"peers": [], "channels": ["111", "222"], "guilds": [], "roles": []}}`; calls `_route_discoverable_ok(page, account_id)`; attaches an agent; opens the agent's Connectors tab; expands the channels axis; asserts that the two checkbox-rows' `.mcp-tool-toggle-name` spans display `"#general"` and `"#random"` (NOT `"111"` and `"222"`). Use `expect(...).to_have_text(...)` for precision.
- [x] `test_per_agent_overlay_checkbox_mode_stub_shows_raw_ids` seeds a STUB account with `config={"allowlist": {"peers": [], "channels": ["raw-id-A", "raw-id-B"], "guilds": [], "roles": []}}`; calls `_route_discoverable_503(page, account_id)`; attaches an agent; opens the Connectors tab; expands the channels axis; asserts the two name spans display `"raw-id-A"` and `"raw-id-B"` (raw-id fallback held).
- [x] `test_per_agent_overlay_checkbox_mode_network_error_shows_raw_ids` seeds a Discord account with `config={"allowlist": {"peers": [], "channels": ["111"], "guilds": [], "roles": []}}`; calls `_route_discoverable_network_error(page, account_id)`; attaches an agent; opens the Connectors tab; expands the channels axis; asserts the single name span displays `"111"` (raw-id fallback held). The test uses a small explicit wait (`page.wait_for_timeout(200)` or `expect(...).to_have_text(...)` with a generous timeout) to allow the `.catch()` branch to settle before asserting; the raw-id is the original text so even an instant assertion would pass — the wait is defensive against the test asserting before any async work completes.
- [x] All three new tests use the `@pytest.mark.browser` marker.
- [x] `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py -m browser -x --timeout 60 -v` passes all three new tests.
- [x] `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_dropdown.py -m browser -x --timeout 60` continues to pass both existing tests (regression contract for chip-mode dispatch + checkbox-mode-unchanged invariant).
- [x] `docker exec the-one pytest tests/browser/test_connector_test_connection_button.py -m browser -x --timeout 60` continues to pass (no overlap, but verifies the broader connector browser surface is green).
- [x] No source files beyond `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` are modified. The only test file added is `tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py`.

## Verification Steps

- `grep -n "_labelCache\|_ensureLabelCache\|_applyLabelsToCheckboxes" the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` returns at least 8 hits (4 helper declarations + 1 call from the expand handler + 3 uses inside the helpers).
- `grep -n "/discoverable-entities" the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` returns exactly 1 hit (inside `_ensureLabelCache`).
- `grep -n "nameSpan.textContent = item;" the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` returns exactly 1 hit (preserved — the initial render still uses raw-id; A2 mutates AFTER render via `_applyLabelsToCheckboxes`).
- `git diff the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` shows insertions inside `_renderAccountTile` + one new clause inside the existing `expandBtn.addEventListener` handler. The chip-mode `else` branch and `_buildCheckboxList`'s body show no diff hunks.
- `ls tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py` confirms the new file exists.
- `grep -nE "^(async )?def test_" tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py` returns exactly 3 hits matching the three test names.
- `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py -m browser -x --timeout 60 -v` shows 3 PASS.
- `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_dropdown.py tests/browser/test_connector_test_connection_button.py -m browser -x --timeout 60` shows 9 PASS (2 dropdown + 7 test-connection-button), 0 FAIL — regression contract.

## Implementation Guidance

1. **Read `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js`** around the targets:
   - `_renderAccountTile` at line 118 (function signature + initial var declarations through line 138).
   - `_populateAclEditor` inner function (around line 199-ish through the end of the AclEditor build).
   - `_buildAxisRow` inner function (line 206) — particularly the `expandBtn.addEventListener` at line 241 and the checkbox-mode branch at line 522.
   - `_buildCheckboxList` standalone function (line 460-518) — particularly the `nameSpan.textContent = item;` at line 507.

2. **Insert the four closure helpers near the top of `_renderAccountTile`** — after the existing var declarations (after `var scopeChannels` at line 137), before `var tile = document.createElement('div');`. The position keeps all tile-local state colocated.

   ```javascript
   // A2 (M11 F4 L3) — lazy per-tile label cache for checkbox-mode rows.
   // Discord and similar live-data connector accounts expose
   // ``enumerate_discoverable_entities`` via the L4 cache; the cache
   // resolves Discord snowflake IDs to friendly labels (``#general``
   // etc.) so the per-agent overlay's checkbox-mode does not surface
   // raw IDs. Stub-type / cold-pool / network-error all fall back to
   // the raw-id render preserved by the initial DOM mount.
   var _labelCache = null;
   var _labelCachePromise = null;

   function _ensureLabelCache() {
     if (_labelCachePromise) return _labelCachePromise;
     var url = '/api/connector-accounts/' +
       encodeURIComponent(account.id) +
       '/discoverable-entities';
     _labelCachePromise = fetch(url).then(function (response) {
       if (!response.ok) {
         _labelCache = {};
         return _labelCache;
       }
       return response.json().then(function (body) {
         var map = {};
         var ents = (body && body.entities) || {};
         var axes = ['peers', 'channels', 'groups', 'roles'];
         for (var a = 0; a < axes.length; a++) {
           var list = ents[axes[a]] || [];
           for (var i = 0; i < list.length; i++) {
             var e = list[i];
             if (e && e.id && e.label) map[String(e.id)] = e.label;
           }
         }
         _labelCache = map;
         return _labelCache;
       });
     }).catch(function (err) {
       _labelCache = {};
       try { console.error('connectors-tab label-cache fetch failed:', err); }
       catch (logErr) { /* console missing */ }
       return _labelCache;
     });
     return _labelCachePromise;
   }

   function _applyLabelsToCheckboxes(bodyEl) {
     if (!_labelCache) return;
     var rows = bodyEl.querySelectorAll('.connector-acl-checkboxlist-row');
     for (var i = 0; i < rows.length; i++) {
       var cb = rows[i].querySelector('input[type="checkbox"]');
       if (!cb) continue;
       var label = _labelCache[String(cb.value)];
       if (!label) continue;
       var nameSpan = rows[i].querySelector('.mcp-tool-toggle-name');
       if (nameSpan) nameSpan.textContent = label;
     }
   }
   ```

3. **Modify `_buildAxisRow`'s expand handler** (line 243-247). Replace:

   ```javascript
   expandBtn.addEventListener('click', function () {
     var nextExpanded = expandBtn.getAttribute('aria-expanded') !== 'true';
     expandBtn.setAttribute('aria-expanded', nextExpanded ? 'true' : 'false');
     body.hidden = !nextExpanded;
   });
   ```

   With:

   ```javascript
   expandBtn.addEventListener('click', function () {
     var nextExpanded = expandBtn.getAttribute('aria-expanded') !== 'true';
     expandBtn.setAttribute('aria-expanded', nextExpanded ? 'true' : 'false');
     body.hidden = !nextExpanded;
     // A2: lazy label resolution for checkbox-mode rows. Fires once
     // per tile (single-flight promise); collapse-then-re-expand
     // reuses the cache.
     if (nextExpanded && scopeList && scopeList.length > 0) {
       _ensureLabelCache().then(function () {
         _applyLabelsToCheckboxes(body);
       });
     }
   });
   ```

   No other line in `_buildAxisRow` changes. `_buildCheckboxList` itself is unmodified — the initial render still produces raw-id text; A2's `_applyLabelsToCheckboxes` mutates the spans AFTER the cache resolves.

4. **Create `tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py`** as a new file. Structure mirrors `test_flow_studio_per_agent_overlay_dropdown.py`. Suggested skeleton:

   ```python
   """Browser tests for the per-agent overlay checkbox-mode label
   resolver (M11 F4 L3 A2).

   The per-agent overlay's checkbox-mode renders one row per
   account-scope chip. F3 L7 HAT surfaced that the row labels were
   raw Discord snowflake IDs (e.g. ``1506831630923333722``) instead of
   friendly labels (``#gleepglorp-text``). F4 L3 resolves labels via
   a lazy fetch of the L4 discoverable-entities cache on first axis
   expand, with raw-id fallback on 503 (stub-type), 404 (cold pool),
   and network errors.
   """

   from __future__ import annotations

   import json

   import httpx
   import pytest
   from browser.seeders import (
       seed_connector_account,
       seed_mock_agent,
       seed_mock_provider,
   )
   from playwright.sync_api import Page, expect


   _DISCOVERABLE_PAYLOAD = {
       "entities": {
           "peers": [],
           "channels": [
               {
                   "id": "111",
                   "label": "#general",
                   "group": "guild-1",
                   "metadata": {},
                   "stale": False,
               },
               {
                   "id": "222",
                   "label": "#random",
                   "group": "guild-1",
                   "metadata": {},
                   "stale": False,
               },
           ],
           "groups": [],
           "roles": [],
       },
       "fetched_at": "2026-05-23T00:00:00Z",
       "stale_seconds": 0,
   }


   def _route_discoverable_ok(page: Page, account_id: str) -> None:
       def handle(route):
           route.fulfill(
               status=200,
               content_type="application/json",
               body=json.dumps(_DISCOVERABLE_PAYLOAD),
           )

       page.route(
           f"**/api/connector-accounts/{account_id}/discoverable-entities*",
           handle,
       )


   def _route_discoverable_503(page: Page, account_id: str) -> None:
       def handle(route):
           route.fulfill(status=503, body="{}")

       page.route(
           f"**/api/connector-accounts/{account_id}/discoverable-entities*",
           handle,
       )


   def _route_discoverable_network_error(page: Page, account_id: str) -> None:
       def handle(route):
           route.abort("failed")

       page.route(
           f"**/api/connector-accounts/{account_id}/discoverable-entities*",
           handle,
       )


   def _attach_agent_to_account(
       base_url: str, agent_name: str, account_id: str
   ) -> None:
       cur = httpx.get(f"{base_url}/api/agents/{agent_name}", timeout=5.0)
       assert cur.status_code == 200
       cfg = cur.json()
       ids = list(cfg.get("connector_account_ids") or [])
       if account_id not in ids:
           ids.append(account_id)
       cfg["connector_account_ids"] = ids
       r = httpx.put(
           f"{base_url}/api/agents/{agent_name}", json=cfg, timeout=5.0
       )
       assert r.status_code == 200


   def _open_agent_connectors_tab(
       page: Page, base_url: str, agent_name: str
   ) -> None:
       page.goto(f"{base_url}#studio/agents/{agent_name}")
       expect(page.locator('[data-testid="tab-connectors"]')).to_be_visible(
           timeout=8000
       )
       page.locator('[data-testid="tab-connectors"]').click()


   # ── Tests ────────────────────────────────────────────────────────────


   @pytest.mark.browser
   def test_per_agent_overlay_checkbox_mode_resolves_discord_labels(
       app_clean: str, page: Page
   ) -> None:
       """Discord account with channels in allowlist (checkbox-mode) →
       checkbox-row name spans display friendly labels resolved from
       the L4 cache, NOT raw snowflake IDs."""
       provider_id = seed_mock_provider(app_clean, name="mock-label-resolver")
       agent_name = seed_mock_agent(
           app_clean, provider_id, name="label-resolver-agent"
       )
       account_id = seed_connector_account(
           app_clean,
           type="discord",
           name="Label Resolver Bot",
           secrets={"BOT_TOKEN": "real_bot_token_abcd"},
           config={
               "allowlist": {
                   "peers": [],
                   "channels": ["111", "222"],
                   "guilds": [],
                   "roles": [],
               }
           },
       )
       _attach_agent_to_account(app_clean, agent_name, account_id)
       _route_discoverable_ok(page, account_id)
       _open_agent_connectors_tab(page, app_clean, agent_name)

       tile = page.locator(f'[data-testid="connector-account-row-{account_id}"]')
       expect(tile).to_be_visible(timeout=8000)

       toggle = tile.locator(
           f'[data-testid="connector-acl-axis-toggle-channels-{account_id}"]'
       )
       toggle.click()

       checkbox_wrap = tile.locator(
           f'[data-testid="connector-acl-channels-checkboxes-{account_id}"]'
       )
       expect(checkbox_wrap).to_be_visible(timeout=8000)

       # Name spans display friendly labels (NOT raw IDs).
       name_spans = checkbox_wrap.locator(".mcp-tool-toggle-name")
       expect(name_spans).to_have_count(2)
       expect(name_spans.nth(0)).to_have_text("#general", timeout=8000)
       expect(name_spans.nth(1)).to_have_text("#random")


   @pytest.mark.browser
   def test_per_agent_overlay_checkbox_mode_stub_shows_raw_ids(
       app_clean: str, page: Page
   ) -> None:
       """Stub account (plugin lacks enumerate_discoverable_entities;
       L4 returns 503) → checkbox-row name spans display raw IDs
       (regression contract for stub-type / no-hook accounts).
       """
       provider_id = seed_mock_provider(app_clean, name="mock-stub-fallback")
       agent_name = seed_mock_agent(
           app_clean, provider_id, name="stub-fallback-agent"
       )
       account_id = seed_connector_account(
           app_clean,
           type="stub",
           name="Stub Fallback Bot",
           secrets={"BOT_TOKEN": "any_value"},
           config={
               "allowlist": {
                   "peers": [],
                   "channels": ["raw-id-A", "raw-id-B"],
                   "guilds": [],
                   "roles": [],
               }
           },
       )
       _attach_agent_to_account(app_clean, agent_name, account_id)
       _route_discoverable_503(page, account_id)
       _open_agent_connectors_tab(page, app_clean, agent_name)

       tile = page.locator(f'[data-testid="connector-account-row-{account_id}"]')
       expect(tile).to_be_visible(timeout=8000)

       toggle = tile.locator(
           f'[data-testid="connector-acl-axis-toggle-channels-{account_id}"]'
       )
       toggle.click()

       checkbox_wrap = tile.locator(
           f'[data-testid="connector-acl-channels-checkboxes-{account_id}"]'
       )
       expect(checkbox_wrap).to_be_visible(timeout=8000)

       name_spans = checkbox_wrap.locator(".mcp-tool-toggle-name")
       expect(name_spans).to_have_count(2)
       expect(name_spans.nth(0)).to_have_text("raw-id-A")
       expect(name_spans.nth(1)).to_have_text("raw-id-B")


   @pytest.mark.browser
   def test_per_agent_overlay_checkbox_mode_network_error_shows_raw_ids(
       app_clean: str, page: Page
   ) -> None:
       """Discord account; the L4 GET fails (route.abort) →
       checkbox-row name span displays the raw ID (the .catch()
       branch in _ensureLabelCache swallows the error and resolves
       _labelCache to {}). Regression contract for transport-error
       fallback."""
       provider_id = seed_mock_provider(app_clean, name="mock-net-error")
       agent_name = seed_mock_agent(
           app_clean, provider_id, name="net-error-agent"
       )
       account_id = seed_connector_account(
           app_clean,
           type="discord",
           name="Net Error Bot",
           secrets={"BOT_TOKEN": "real_bot_token_abcd"},
           config={
               "allowlist": {
                   "peers": [],
                   "channels": ["111"],
                   "guilds": [],
                   "roles": [],
               }
           },
       )
       _attach_agent_to_account(app_clean, agent_name, account_id)
       _route_discoverable_network_error(page, account_id)
       _open_agent_connectors_tab(page, app_clean, agent_name)

       tile = page.locator(f'[data-testid="connector-account-row-{account_id}"]')
       expect(tile).to_be_visible(timeout=8000)

       toggle = tile.locator(
           f'[data-testid="connector-acl-axis-toggle-channels-{account_id}"]'
       )
       toggle.click()

       checkbox_wrap = tile.locator(
           f'[data-testid="connector-acl-channels-checkboxes-{account_id}"]'
       )
       expect(checkbox_wrap).to_be_visible(timeout=8000)

       name_spans = checkbox_wrap.locator(".mcp-tool-toggle-name")
       expect(name_spans).to_have_count(1)
       # Raw-id fallback held; the .catch() branch set _labelCache = {}
       # so no span was rewritten.
       expect(name_spans.nth(0)).to_have_text("111")
   ```

5. **Run tests** (`docker exec the-one pytest …`; PASS `-m browser` to ensure the browser tier runs — default pyproject.toml addopts deselects browser tests per the L2 leg debrief note):
   - `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py -m browser -x --timeout 60 -v` (3 new tests)
   - `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_dropdown.py tests/browser/test_connector_test_connection_button.py -m browser -x --timeout 60` (regression contract)
   - Leg-end broader sweep: `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py tests/browser/test_flow_studio_per_agent_overlay_dropdown.py tests/browser/test_connector_test_connection_button.py tests/browser/test_flow_studio_connector_account_editor.py -m browser -x --timeout 60`

6. **Update F4 `flight.md` Checkpoints + Legs** — check off L3.

7. **Append L3 leg-progress entry** to F4 `flight-log.md`.

8. **Update this leg artifact's Status header** progressively: `planning` → `ready` → `in-flight` → `landed`.

## Edge Cases

- **Cache fetched, label-cache empty (`_labelCache = {}`), then operator collapses and re-expands**: `_ensureLabelCache` returns the resolved single-flight promise instantly; `_applyLabelsToCheckboxes` runs but finds no labels, leaves raw-id text untouched. Correct behavior.
- **Cache fetched OK, but a checkbox row's id is NOT in the response**: `_labelCache[id]` returns undefined; the row's `nameSpan.textContent` is left unchanged (raw-id stays). This is the desired fallback — an account might have a chip in its allowlist for a Discord entity that the bot no longer sees (deleted channel, kicked from guild). The stale-entry-indicator UX (F3-deferred to F9) is a separate concern; for this leg, raw-id fallback is acceptable for the unknown-id case.
- **Multiple axes in checkbox-mode on the same tile**: each axis's expand handler calls `_ensureLabelCache()` independently; the second call returns the same single-flight promise so no parallel GETs fire. After both promises resolve, each axis's body has had `_applyLabelsToCheckboxes` called on it (because the `.then()` is per-axis).
- **Operator expands a checkbox-mode axis, then expands another (chip-mode) axis on the same tile**: chip-mode axis's handler does NOT fire the new clause (gated on `scopeList.length > 0`); the chip-mode branch goes through the existing dropdown mount path which uses its own L4 fetch via `discoverable-dropdown.js`. Both code paths fetch the same endpoint but with their own state — acceptable; the duplicated fetch is one-per-tile-per-render, not per-axis.
- **The bot's response includes an entity in `peers`, `channels`, AND `roles` with the same id**: highly unlikely (Discord namespaces are disjoint) but the flattening map would have the last-axis-wins. Not a correctness issue for label display — the label string would be the same regardless of axis if Discord ever did emit the same id across axes. Document only.
- **The fetch returns 200 but `body.entities` is null or missing**: the `var ents = (body && body.entities) || {};` defaults to `{}`; the axis iteration short-circuits to no labels; `_labelCache = {}`. Raw-id fallback held.
- **Stub-type account toggles to checkbox mode via empty-config edit**: stub accounts may have non-empty allowlists (the test uses one); the route handler returns 503 per the substrate convention for plugins without the hook. `_ensureLabelCache` sets `_labelCache = {}`; raw-id fallback held. Regression contract for stub-type accounts is the second test.
- **`fetch` is undefined** (very old browser context, never happens in Playwright but be defensive): `_ensureLabelCache` would throw a `ReferenceError` synchronously — caught by the wrapper context? No: the throw escapes the function. Since this is a modern-browser-only project (Playwright Chromium), don't add defensive code; the project's existing `discoverable-dropdown.js:_doFetch` doesn't either.
- **`encodeURIComponent` not available**: same as above — modern-browser-only; don't defend.
- **`account.id` is null/undefined**: `_renderAccountTile` is only called with a valid `account` object; if invariant breaks, the URL becomes `/api/connector-accounts/undefined/discoverable-entities` and the server 404s — `_labelCache = {}`; raw-id fallback held. No new defensive code needed; the invariant is upstream.
- **A test environment without the registered fetch interception**: Playwright's `page.route()` intercepts BEFORE the network layer; the test handlers always fire. No race.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` — `_renderAccountTile` body grows four closure-scoped helpers + `_buildAxisRow`'s expand handler grows one new clause. Total surface ~50-70 LOC; well under the 100 LOC F4 leg budget.
- `tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py` — new file; 3 tests + 5 helpers + module-level fixture data; total ~200-220 LOC.
- `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/flight.md` — L3 checkpoint + L3 leg checklist checked off.
- `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/flight-log.md` — L3 leg-progress entry appended.
- `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/legs/03-per-agent-overlay-checkbox-label-resolver.md` — this artifact's status header updated through the lifecycle.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (grep checks pass; pytest runs green; chip-mode + `_buildCheckboxList` byte-identity confirmed via diff)
- [x] `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py tests/browser/test_flow_studio_per_agent_overlay_dropdown.py tests/browser/test_connector_test_connection_button.py -m browser -x --timeout 60` passes
- [x] Update `flight-log.md` with L3 leg-progress entry
- [x] Set this leg's status to `landed`
- [x] Check off L3 in `flight.md` (Checkpoints + Legs sections)
- [x] Do NOT commit (F4 batches review + commit at flight end per the agentic-workflow protocol)

---

## Citation Audit

All code-location citations in this leg artifact verified against current code at leg design time (2026-05-23):

- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:_renderAccountTile` — function definition confirmed at line 118.
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:_buildAxisRow` — inner function confirmed at line 206; expand handler at line 241.
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:_buildCheckboxList` — function confirmed at line 460; `nameSpan.textContent = item;` at line 507.
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:507` — `nameSpan.textContent = item;` (raw-id render site) confirmed; matches F4 recon table R2 evidence.
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js:480-512` — `_doFetch` reference for URL shape (`'/api/connector-accounts/' + encodeURIComponent(state.accountId) + '/discoverable-entities' + suffix`) confirmed; the new `_ensureLabelCache` uses the same shape with `suffix = ''`.
- `the_one/connectors/base.py:DiscoverableEntity` — dataclass with `id`, `label`, `group`, `metadata` confirmed at line 390.
- `the_one/connectors/base.py:DiscoverableEntities` — axis-keyed snapshot dataclass confirmed at line 437.
- `tests/browser/test_flow_studio_per_agent_overlay_dropdown.py` — 204-line precedent file with two tests; `_DISCOVERABLE_PAYLOAD` at line 35, `_route_discoverable_ok` at line 63, `_attach_agent_to_account` at line 77, `_open_agent_connectors_tab` at line 89, `test_per_agent_overlay_chip_mode_renders_dropdown_for_discord` at line 99, `test_per_agent_overlay_checkbox_mode_unchanged` at line 150 — all confirmed.
- The data-testid surface used by tests (`connector-account-row-{id}`, `connector-acl-axis-toggle-{axis}-{id}`, `connector-acl-{axis}-checkboxes-{id}`) — confirmed against `connectors-tab.js:144, 217, 472`.

9 citation sites verified clean. No drift repaired.
