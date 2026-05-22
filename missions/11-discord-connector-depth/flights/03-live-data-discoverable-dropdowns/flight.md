# Flight: Live-Data Discoverable Dropdowns

**Status**: landed
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [x] The allowlist editor for a Discord connector account (account-scope and per-agent overlay) replaces M10's free-form chip-list with searchable dropdowns sourced from the live bot's view of the Discord users, channels, servers, and roles it can actually reach; the operator types to filter and selects from real entries rather than pasting in IDs from external Discord-developer-mode lookups; entries that the bot can no longer see (user left server, channel deleted, bot kicked) are flagged in the editor with a stale-entry indicator.
- [x] The routing-rules editor for multi-agent Discord accounts uses the same searchable-dropdown data source as the allowlist editor — channel selection and per-(channel, user) overrides surface real Discord channels and usernames, not free-form text; the M10 debrief's "operator typed `#channel-name`, got 'No agents available'" failure mode is structurally prevented.

---

## Pre-Flight

### Objective

F3 closes M11's "no more channel-ID-paste UX" promise at the allowlist + routing surfaces. The substrate-level `enumerate_discoverable_entities(account)` hook lands on `ConnectorPlugin` Protocol as the per-axis-tri-state-like generic abstraction (Discord supplies the data; future Slack / Matrix inherit additively). Discord's plugin implements the hook by reading the live `discord.Client` view at probe-time + caching with a periodic refresh (default 5min while bot online) + manual refresh button + stale-entry indicator. The substrate exposes the cached snapshot via a new read-only `GET /api/connector-accounts/{id}/discoverable-entities` endpoint. Studio's allowlist + routing-rules editors swap their chip-lists and free-form text inputs for a searchable combobox component (typeahead filter + grouped sections + virtualization >100 entries + paged fetch >1000). The dropdown component registers via a NEW optional registry-entry hook (`renderDiscoverableDropdown` — the 5th optional hook; F2 debrief flagged n=5 as the evaluation point and the operator opted to keep the flat-array shape since the new hook has the same function-if-present signature as the existing four). F3 also folds in three F2-debrief items: L1 codifies `primitive-rename-test-classification` + `flight-spec-dom-order-audit` in `agents.md` (per operator decision; mission-control skill codification deferred); L2 triages the 3-flight-deep `test_connector_test_connection_button` chronic debt (test-vs-code disagreement at `connector-account-editor.js:1625-1631`'s success-with-no-details branch — operator chose "update test to match code" direction); and the `connector-form-registry.js` top-comment consolidation (1-line doc lift) is bundled into L5 when the registry is touched.

### Open Questions

*Planning-time open questions resolved at the Phase 4 crew interview (2026-05-22). Resolutions promoted to Design Decisions below.*

### Design Decisions

**Substrate plugin hook — optional via `optional-plugin-hook-via-getattr-sentinel` convention** *(resolved at crew interview)*:
- Document a NEW optional method `enumerate_discoverable_entities(client: ConnectorClient) -> DiscoverableEntities` in the `ConnectorPlugin` module docstring at `the_one/connectors/base.py`. **Per `optional-plugin-hook-via-getattr-sentinel` (F1 L1 codified), optional hooks are NOT Protocol widenings** — the Protocol class body stays at its current 4 required methods. Plugins opt in by exposing the method; consumers consult via `getattr(plugin, "enumerate_discoverable_entities", None)` with a fallback. The convention's exemplar citations (`display_channel`, `resolve`, `is_dm`) follow this same shape — the method lives on the plugin implementation + the module docstring, not on the `class ConnectorPlugin(Protocol):` body. Connectors that can't enumerate (or don't want to — e.g., the test-only `'stub'`) simply don't expose the method; the Studio surface falls back to the existing chip-list editor for those types.
- **Signature: `client: ConnectorClient`** (the wrapper, not the raw SDK type). Discord's plugin implementation reaches into `_DiscordConnectorClient._client` (private SDK access) the same way `_DiscordConnectorClient._user` does today — deliberate boundary breach with inline comment. Substrate-neutral; future Slack/Matrix/etc. plugins receive the wrapper they already manage. This avoids coupling the hook signature to any one platform's SDK type.
- `DiscoverableEntities` shape — single structured return per `agents.md`'s convention for hook return values:
  ```python
  @dataclass(frozen=True)
  class DiscoverableEntity:
      id: str          # platform-native ID (Discord snowflake; Slack id; etc.)
      label: str       # display label ("#general", "@username", "Server Name")
      group: str | None = None  # optional grouping ("guild:123456" → renders as section header)
      metadata: dict[str, Any] = field(default_factory=dict)  # platform-specific
  
  @dataclass(frozen=True)
  class DiscoverableEntities:
      peers: list[DiscoverableEntity]     # Discord users, Slack workspace members
      channels: list[DiscoverableEntity]
      groups: list[DiscoverableEntity]    # Discord guilds, Slack workspaces
      roles: list[DiscoverableEntity]
      fetched_at: str                     # ISO timestamp at which the live read happened
  ```
- Substrate vocabulary (per F1 L6 convention): the four axis names stay `peers`/`channels`/`groups`/`roles` at the storage and API layers (matching the existing `account.config.allowlist` shape). Discord's plugin returns peers labeled `@username`, channels labeled `#channel-name`, groups labeled by guild name, roles labeled by role name. Vocabulary substitution to "users / servers" happens in the Studio render layer per F1 L6.
- **Rationale**: optional-getattr hook matches the existing `display_channel` / `resolve` / `is_dm` precedents codified in `agents.md`. Single structured return matches F1 L6's per-axis-tri-state-override shape. Substrate stays neutral; Discord supplies the data.
- **Trade-off**: future connectors that can't enumerate (webhook-driven plain HTTP, no live view) simply don't implement the hook → Studio falls back to the chip-list per-type. Acceptable per M11 mission constraint.

**Cache + refresh strategy — periodic background + manual + stale-indicator** *(operator-confirmed)*:
- The connector pool's warm `_RegistryEntry` carries a NEW field `discoverable_entities_cache: DiscoverableEntities | None = None` plus `discoverable_entities_fetched_at_monotonic: float | None = None`.
- A new background sweep task runs alongside the existing reaper (`_reap_loop` at `_pool.py:_reap_loop`), refreshing each warm entry's discoverable-entities cache every 5 minutes (`_DISCOVERABLE_REFRESH_INTERVAL_SECONDS = 300`). **Refresh mechanism — direct pool access, NOT `account_acquire`**: the sweep iterates `_pool._entries` directly under `_lock`, captures each entry's `client` reference, releases the lock, and calls `plugin.enumerate_discoverable_entities(entry.client)` outside the lock. **CRITICAL: the sweep does NOT touch `entry.last_activity`** — refreshing the cache is a substrate operation, not an operator-initiated acquire, so it does not reset the idle clock. This avoids the immortality race that Architect cycle-1 caught: 5-min refresh interval is less than 30-min idle TTL, so routing refresh through `account_acquire` would reset the clock on every sweep and warm entries would never be evicted.
- On refresh success, replace the cache + update timestamp; on failure (network error, plugin raise), log WARNING and keep the previous snapshot.
- Studio's `GET /api/connector-accounts/{id}/discoverable-entities`:
  - If the account is currently pooled (warm entry exists): return the cached snapshot `{entities, fetched_at, stale_seconds}` from `discoverable_entities_cache`.
  - If NOT pooled (cold account): **return 404 with body `{"detail": "Run Test Connection first to populate the bot's discoverable view."}`**. Mirrors F1 L5's Invite section pre-probe hint. Avoids warming a pool entry for full 30-min TTL on a single dropdown open. The operator clicks Test Connection (which goes through the existing doctor probe path AND populates the pool entry via the lifespan-listener-warmup path); the dropdown then has a cached view to serve.
- A manual `POST /api/connector-accounts/{id}/discoverable-entities/refresh` endpoint forces immediate refresh. Studio's dropdown "Refresh" button POSTs to this. **Same direct-pool-access mechanism** — does not touch `last_activity`. Returns 404 with the same hint string if the account is cold.
- Stale-entry indicator: when an entity was in the cache previously but is absent from the latest refresh, the API marks it `stale: true` in the response. The cache retains stale entries for one additional refresh cycle; if the entity reappears in the next refresh, the stale flag clears (the cache snapshot is replaced wholesale on each refresh, so stale-flagged entities are removed from the next snapshot unless the platform reports them again). After two consecutive absences, the entry is dropped from the cache entirely.
- **Rationale**: mission OQ#4 default — operationally proven shape. The direct-pool-access mechanism eliminates the immortality race; the 404-pre-probe-hint behavior mirrors F1 L5 precedent.
- **Trade-off**: stale entries linger up to 5 minutes after the bot loses visibility. Acceptable for an editor surface. Cold-account dropdown open requires the operator to click Test Connection first — acceptable per F1 L5 convention.

**API endpoint — GET per-account (read-only cached) + POST refresh** *(operator-confirmed)*:
- `GET /api/connector-accounts/{id}/discoverable-entities` returns `{entities: DiscoverableEntities, fetched_at, stale_seconds}` on warm; 404 with pre-probe hint on cold (see Cache strategy above).
- `POST /api/connector-accounts/{id}/discoverable-entities/refresh` triggers immediate refresh + returns the new snapshot. 200 on success; 404 with pre-probe hint if cold; 503 if the plugin doesn't implement `enumerate_discoverable_entities` (the hook is optional; some types simply don't have entities to discover — the connector-form-registry's fallback to chip-list editor covers these types in the UI, so a 503 should not normally reach the operator).
- Both endpoints are mounted at the connector-accounts router (existing routes at `interfaces/web/api.py:2148+`). No new authentication shape.
- **Rationale**: REST is simple, cacheable, debuggable. WebSocket push (mission OQ#4 alternative b) is explicitly rejected as over-complex for F3 — F8's HAT script flight will reassess if real-traffic freshness friction surfaces.
- **Trade-off**: Studio polls (on dropdown open or manual refresh) rather than receiving push notifications. For an editor surface, polling is fine.

**Dropdown UI shape — combobox with grouped sections + typeahead + virtualization** *(operator-confirmed)*:
- New shared component `App.studio.discoverableDropdown(opts) → DOMElement` lives in `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js`. Opts: `{axis, accountId, currentValues, onChange, vocab}`.
- Component renders a typeahead `<input>` with a results panel (combobox pattern). Results grouped by `entity.group` field (Discord channels grouped by guild; users grouped by role if metadata indicates; etc.). Typeahead filters by `label` substring (case-insensitive). Virtualized list for >100 entries (render only the visible viewport). For sources with >1000 total entries the dropdown shows a "Filter to narrow results" hint until the operator types ≥2 chars.
- Selected values render as removable chips below the input (same chip-list visual posture as the existing F6 chip-list editor; preserves operator muscle memory).
- A "Refresh" button next to the input triggers the POST refresh endpoint + repopulates the dropdown.
- Stale entries (those marked `stale: true` from the API) render with a `data-stale="true"` attribute and a CSS class that adds a strikethrough + tooltip "Bot can no longer see this entity."
- Keyboard navigation: existing combobox conventions per WCAG (ArrowUp/Down navigate; Enter selects; Escape closes; Tab commits on focus exit).
- **Rationale**: mission OQ#5 default — combobox is the operator-meaningful shape for discovering large entity sets; typeahead + virtualization handle the Discord-server-with-250k-members worst case.
- **Trade-off**: **~500-800 LOC of new frontend code** (Architect cycle-1 revised the original ~300-400 estimate upward by comparison to `connector-form-discord.js` actual at 722 LOC). Accepted because the same component serves both allowlist + routing-rules surfaces (and future Slack/Matrix inherit additively). The L5 leg's Adaptation Criteria allows pause + split-by-shape (e.g., extracting a virtualization helper as a separate module) if implementation exceeds 700 LOC.

**Registry-entry optional hook — `renderDiscoverableDropdown` (n=5; flat array stays)** *(operator-confirmed)*:
- F2 debrief flagged n=5 as the evaluation point for restructuring `optionalFns` from a flat array to an object map. Operator opted to KEEP the flat array because the 5th hook has the same function-if-present signature as the existing four. Defer object-map restructure to n=6+ when concrete per-hook arity/signature validation is needed.
- New entry hook `renderDiscoverableDropdown(account, axis, currentValues, vocab) → DOMElement | null` on registered connector entries. Discord implements; stub doesn't. Substrate consumers (the rewritten `renderAllowlistSection` + `renderRoutingRulesSection`) consult the registry-entry; fallback to existing chip-list if no hook OR if the hook returns null.
- The Discord entry's `renderDiscoverableDropdown` delegates to the shared `App.studio.discoverableDropdown(...)` component — Discord doesn't reimplement; it just passes its axis/vocab/data-source through. Other future per-type entries get the same path.
- **Trade-off**: the substrate's `renderAllowlistSection` (currently directly building chip-list editors) must be refactored to consult the registry. This is L6 scope (the substrate refactor); the dropdown component itself is L5.

**Allowlist + routing-rules consumer surfaces** *(L6 scope)*:
- `renderAllowlistSection` (account-scope; per F6 + F8 L8 axes: peers/channels/guilds/roles): each axis row's chip-list editor swaps for a `discoverableDropdown` consult; fallback to chip-list when no registry hook exists (e.g., stub-type accounts).
- `renderRoutingRulesSection` (per F7): the rule-row match-value input swaps from free-form text to a `discoverableDropdown` consult — match-values only. Scope literals (`channel`/`thread`/`dm`/`peer`) stay as the existing `<select>` per F1 L6's vocabulary discipline.
- The per-agent overlay editor (per F6 L1c — `AgentConfig.connector_acls[account_id]`) ALSO consults the dropdown when the account is Discord. Same per-axis shape.

**Test-connection-button triage — "update ALL three `status:'ok'` tests to match code"** *(operator-confirmed at L2 after Architect cycle-1)*:
- **Architect cycle-1 finding**: the test file at `tests/browser/test_connector_test_connection_button.py` contains 7 tests total, of which **three** assert `details_wrap.to_be_visible()` on a `status='ok'` path: `test_default_stub_probe_renders_success_with_no_details:67`, `test_non_string_detail_renders_as_font_mono_json:154` (ok-status + non-empty `{count:42,...}` details), and `test_secret_shaped_detail_value_passes_through_unmasked:191` (ok-status + masked-token-in-details). The F2 debrief originally referred to "the recurring 3× failure cluster" — these are the three. All three currently fail with the same `details_wrap hidden when expected visible` signature.
- The production code at `connector-account-editor.js:renderTestConnectionBanner` (lines 1625-1631) hides `details_wrap` UNCONDITIONALLY when `status === 'ok'`, regardless of whether `details` is empty or non-empty:
  ```javascript
  if (status === 'ok') {
    detailsEl.innerHTML = '';
    detailsWrap.hidden = true;
  } else {
    detailsEl.innerHTML = renderDetailsBlock(details);
    detailsWrap.hidden = false;
  }
  ```
- The code's behavior is operator-friendly + matches the explicit M07-inspector-convention comment ("status + one-sentence message at-a-glance; full structured detail behind a panel that opens only when there's something to debug").
- L2 updates **all three** `status:'ok'` tests: each gets `expect(details_wrap).to_be_hidden()` instead of `to_be_visible()`. The non-empty-details rendering paths (the `renderDetailsBlock` shapes for font-mono JSON + masked-token passthrough) are NOT lost — they're covered by the failure/degraded-status tests in the same file (`test_configured_failure_response_renders_red_led_and_details` exercises non-empty details on the failed path; the rendering logic is the same).
- **Rationale**: closes the actual 3-flight-deep cluster (not just one test). The code's intent matches the M07 inspector-pattern precedent; the tests were written ahead of the operator-friendly shipping shape.
- **Trade-off**: if the operator later prefers an always-visible-details UX for the success path, that's a UI change (`renderTestConnectionBanner` body edit) that can rotate the three tests then. F3 L2 takes the smallest-diff direction.

**L1 codification — two new agents.md conventions** *(operator-confirmed at planning)*:
- `primitive-rename-test-classification`: when a leg spec touches a primitive's name, default-classify every test file containing the primitive's name as `code-update`; downgrade to `docstring-sweep` only after grep verifies the name appears solely in `"""..."""` blocks. F2 L2 cycle-1's three mischaracterized test files (`tests/test_connectors_inbound.py`, `tests/test_lifespan.py`, `tests/test_connectors_e2e_platform_send.py`) are the n=1 codification trigger.
- `flight-spec-dom-order-audit`: at flight-design time when claiming section placement adjacencies (e.g., "between Pairing and Test Connection"), the architect must re-walk the current DOM order before committing the wording. F2 L4 cycle-1's "between Pairing and Test Connection" wording vs the actual "between Pairing and Attached Agents" DOM order is the trigger.
- Both land under `### Project-wide` in `agents.md` per the established F1+F2 L1 codification pattern.

### Prerequisites

- [ ] F2 is `completed` (confirmed: PR #70 status; flight artifact status `completed`).
- [ ] F2's pool primitives (`agent_acquire` / `account_acquire`) are landed — F3 extends `_RegistryEntry` with the discoverable-entities cache fields; the pool refactor is the substrate this builds on.
- [ ] F1 L4's `connector-form-registry` exists with the `optionalFns` array — F3 adds the 5th hook.
- [ ] gleepglorp test bot available + reachable (F1 L7 + F2 L6 setup).
- [ ] `chrome-devtools` MCP available for L7 HAT.

### Pre-Flight Checklist

- [ ] All open questions resolved (substrate hook shape; cache strategy; API endpoint shape; UI shape; registry-entry-hook shape; allowlist+routing consumer scope; test-connection-button triage direction; L1 codification scope — all locked at Phase 4)
- [ ] Design decisions documented (above)
- [ ] Prerequisites verified
- [ ] Validation approach defined (per-leg ACs + L7 HAT)
- [ ] Legs defined (below; planned one-at-a-time per Flight Control convention but tentatively scoped here)

---

## In-Flight

### Technical Approach

**Substrate-first sequencing.** L1 codifies the two F2-debrief conventions doc-only so subsequent legs can invoke them by name. L2 closes the chronic test-connection-button debt (single-test triage; smallest leg in F3). L3 lands the Protocol widening + Discord plugin implementation of the `enumerate_discoverable_entities` hook (substrate, no UI dependency). L4 lands the pool cache + the two new API endpoints (substrate, depends on L3's hook). L5 lands the shared `discoverableDropdown` frontend component + extends the connector-form-registry's `optionalFns` array to n=5 (UI substrate). L6 wires the consumer surfaces (allowlist + routing-rules editors) to use the dropdown via the registry hook (UI integration). L7 is the required HAT walking the operator through the dropdown UX against gleepglorp.

**The shared dropdown component is the load-bearing piece.** Once L5 ships `App.studio.discoverableDropdown(...)`, L6 is mostly call-site substitution — the chip-list editor's existing scaffolding (chip rendering, removal events, dirty-tracker integration) carries over; only the input shape changes from free-form text to typeahead-dropdown.

**Cache refresh runs alongside the existing reaper.** The pool's `_reap_loop` task already exists for idle eviction; L4 adds a sibling `_discoverable_refresh_loop` (or extends the existing loop with a discoverable-entities pass). Both sweep on a single asyncio task per `_pool.py`'s lifecycle invariants — no new task lifecycle to manage.

**Per-agent overlay editor reuses the same dropdown component.** F6 L1c's per-agent ACL surface (`AgentConfig.connector_acls[account_id]`) already mounts per-axis chip-lists; L6 swaps them to dropdowns via the same registry consult path. Single point of integration; no duplication.

### Checkpoints

- [x] L1 — Two F2-debrief conventions (`primitive-rename-test-classification`, `flight-spec-dom-order-audit`) codified in `agents.md` Project-wide with definitions, applicability boundaries, exemplar citations, and back-references to F2 debrief.
- [x] L2 — All three `status:'ok'` tests updated to assert `details_wrap` hidden (`:67`, `:154`, `:191`); 4 sibling tests pass UNMODIFIED (`test_test_connection_button_visible_in_edit_mode:24`, `test_test_connection_button_absent_in_create_mode:34`, `test_configured_failure_response_renders_red_led_and_details:73`, `test_degraded_response_renders_warning_led:119`).
- [x] L3 — `ConnectorPlugin` Protocol surface gains `enumerate_discoverable_entities` documented as optional-via-`optional-plugin-hook-via-getattr-sentinel`; `DiscoverableEntities` + `DiscoverableEntity` dataclasses live in `the_one/connectors/base.py`; `DiscordPlugin.enumerate_discoverable_entities` implementation reads from the live `discord.Client` view; unit tests pin the hook contract for both Discord-implements + stub-doesn't paths.
- [x] L4 — `_pool._RegistryEntry` gains discoverable-entities cache fields; periodic background refresh sweep landed; `GET /api/connector-accounts/{id}/discoverable-entities` + `POST .../refresh` endpoints; stale-entry semantics implemented (1-cycle retention before drop); API tests pin the response shape.
- [x] L5 — `App.studio.discoverableDropdown(opts)` component file + connector-form-registry `optionalFns` extended to n=5 (`renderDiscoverableDropdown`); component unit tests via Playwright probe (`page.evaluate` against component instances).
- [x] L6a — `renderAllowlistSection` (4 axes) consumes the dropdown via the registry hook for Discord accounts; chip-list fallback preserved for stub/unregistered types; consolidated `connector-form-registry.js` top-comment optional-hook table (bundled doc lift; natural pair with allowlist since both touch the registry surface).
- [x] L6b — `renderRoutingRulesSection` (match-values only) + per-agent overlay editor (`AgentConfig.connector_acls` UI) consume the dropdown via the registry hook for Discord accounts; chip-list / free-form fallback preserved.
- [x] L7 — HAT walk: 8 of 10 verification steps PASSED live against gleepglorp (steps 1-7, 10); Step 8 (stale-entry indicator) deferred to operator-side Discord action (smoke-verified via API contract); Step 9 (per-agent overlay) partial — chip-mode dropdown architecture intact; checkbox-mode raw-id-label UX flagged as pre-existing gap for F8 HAT. Full HAT outcomes in flight-log.

### Adaptation Criteria

**Divert if**:
- L3's `ConnectorPlugin` Protocol widening requires structural change to existing consumers beyond `getattr`-sentinel pattern. Pause, escalate; revisit whether this hook belongs at the Protocol layer or stays per-plugin internal.
- L4's cache refresh sweep introduces a race against the existing reaper (e.g., refreshing a entry that's mid-eviction). Pause; co-locate the two passes into one sweep task to serialize.
- L5's dropdown component blows past ~500 LOC. Pause; reassess whether the per-axis dropdowns share enough shape that a class-based abstraction is needed, or split into per-axis simpler components.
- L6's allowlist/routing-rules refactor breaks the existing F6 chip-list tests in `tests/browser/test_flow_studio_connector_account_editor.py`. Pause; the chip-list-fallback path must keep working byte-identically for stub-type accounts.
- HAT (L7) surfaces a substrate-contract reversal (per `prompt-discipline-needs-mechanical-fallback`, L1-codified F1) — pauses the flight and triggers fresh design review.

**Acceptable variations**:
- L3 and L4 may merge if the substrate surface area is small enough that the hook + cache + API land in one leg ≤ ~400 LOC.
- L5's dropdown component may exceed 700 LOC — if so, pause and extract the virtualization helper as a separate sibling module before crossing 800 LOC.
- L6a and L6b may merge ONLY if the allowlist refactor turns out to be ≤ ~150 LOC AND the routing+overlay surfaces fit in ≤ ~150 LOC AND the merged leg stays clearly atomic. Default is to keep them split per Architect cycle-1 recommendation.
- The 5-min refresh interval may shorten to 2-3 min if HAT reveals freshness friction; document the change in flight-log.
- Virtualization threshold (>100 entries) may rotate to >50 or >200 based on HAT observations on the gleepglorp test guild's actual entity count.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.
>
> **Dependency ordering**: L1 lands before L3-L6 (they reference codified conventions by name). L2 is independent of L3+ — small triage leg. L3 lands before L4 (L4's cache stores L3's return type). L4 lands before L5 (L5's dropdown fetches via L4's API). L5 lands before L6a (L6a's allowlist refactor calls the L5 component via the registry). L6a lands before L6b — L6b's routing + per-agent overlay surfaces reuse the same dropdown integration L6a proved; sequential ship reduces blast-radius if any consumer-side issue surfaces. L7 lands last (HAT verifies the integrated stack).

- [x] `codify-f2-debrief-conventions` — Doc-only L1 mirroring F1 L1 + F2 L1. Add `primitive-rename-test-classification` and `flight-spec-dom-order-audit` to `the_one/agents.md` Project-wide subsection. Each gets a definition + applicability boundary + exemplar citation from F2 (L2 cycle-1's three mischaracterized files + L4 cycle-1's section-ordering wording divergence) + back-reference to F2 debrief recommendations. No source modifications.

- [x] `triage-test-connection-button-cluster` — Update `tests/browser/test_connector_test_connection_button.py:test_default_stub_probe_renders_success_with_no_details` to assert `expect(details_wrap).to_be_hidden()` on the success-with-no-details path. Drop the "no additional details" placeholder-text assertion (moot when the wrap is hidden). Verify the other 2 tests in the file still pass UNMODIFIED. Closes 3-flight-deep chronic debt; small surface.

- [x] `discoverable-entities-plugin-hook` — Add `DiscoverableEntity` + `DiscoverableEntities` frozen dataclasses to `the_one/connectors/base.py`. Document `enumerate_discoverable_entities(client: ConnectorClient) -> DiscoverableEntities` as an OPTIONAL hook per `optional-plugin-hook-via-getattr-sentinel` (codified F1 L1). Implement on `DiscordPlugin` reading the live `discord.Client` view (users from `client.users`, channels from `client.get_all_channels()`, guilds from `client.guilds`, roles from each guild's `.roles`). Unit tests in `tests/test_connectors_discord.py` pin: discord-implements path returns 4 populated axes; stub-doesn't path returns hookmissing-fallback (via `getattr(plugin, "enumerate_discoverable_entities", None) is None`).

- [x] `discoverable-entities-cache-and-api` — Extend `_pool._RegistryEntry` with `discoverable_entities_cache: DiscoverableEntities | None` + `discoverable_entities_fetched_at_monotonic: float | None`. Add a NEW periodic refresh sweep as a SIBLING task to the existing `_reap_loop` (own asyncio task; own interval `_DISCOVERABLE_REFRESH_INTERVAL_SECONDS = 300`). Sweep mechanism: iterate `_pool._entries` under `_lock`, capture each entry's `client` reference, release the lock, call `getattr(plugin, "enumerate_discoverable_entities", None)(client)` outside the lock; if the entry is still in the pool when the result returns, write the cache back under `_lock` (this avoids the use-after-evict edge — the sweep doesn't write to evicted entries). **Critical**: the sweep MUST NOT touch `entry.last_activity` (no `account_acquire` route). Add `GET /api/connector-accounts/{id}/discoverable-entities` + `POST .../refresh` endpoints to `interfaces/web/api.py`. Stale-entry retention: 1 refresh cycle (entries absent in latest snapshot but present in prior carry `stale: true`; absent in two consecutive snapshots → dropped). Per `atomic-leg-pattern` (L1-codified F1): cache field + sweep + endpoint + tests in one leg.

- [x] `discoverable-dropdown-component` — New file `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` exposing `App.studio.discoverableDropdown(opts) → DOMElement`. Combobox shape per mission OQ#5: typeahead `<input>` + virtualized results panel + grouped sections + chip-list selected-values strip below + Refresh button. Stale-entry rendering with `data-stale="true"` + CSS strikethrough. Extend `connector-form-registry.js:optionalFns` array to `['snapshot', 'wireEvents', 'renderInviteSection', 'renderDirectiveSection', 'renderDiscoverableDropdown']` (n=5; flat-array shape preserved per F2 debrief operator decision). Component browser tests pin: typeahead filters; virtualization renders only visible viewport; stale-entry indicator displays; Refresh button POSTs the right endpoint.

- [x] `discord-dropdown-allowlist` — Refactor `renderAllowlistSection` (4 axes: peers/channels/guilds/roles) to consult `connector-form-registry.get(account.type).renderDiscoverableDropdown(...)`. Discord-type accounts get the dropdown; stub-type accounts fall back to the existing chip-list shape (preserves the L1-codified `registry-dispatch-create-mode-AC` symmetry — both create-mode-after-type-pick AND edit-mode-with-key-set paths verified). **Bundle**: consolidated `connector-form-registry.js` top-comment optional-hook table (natural pair — both touches the registry surface). Existing F6 + F8 chip-list browser tests continue to pass UNMODIFIED for stub-type accounts (the fallback path is the regression contract).

- [x] `discord-dropdown-routing-and-overlay` — Refactor `renderRoutingRulesSection` (match-values only; scope literals stay per F1 L6 vocab discipline) + the per-agent overlay editor (`AgentConfig.connector_acls` UI from F6 L1c) to consult the same `renderDiscoverableDropdown` hook. Discord-type accounts get the dropdown; stub-type accounts fall back to existing chip-list / free-form text. Independent surfaces from L6a's allowlist; the L6 split per Architect cycle-1 keeps atomic-leg-pattern compliance honest. Existing F6 + F7 routing-rules browser tests pass UNMODIFIED for stub-type accounts.

- [x] `uat-and-alignment` *(required HAT, per F1 debrief — registry-mediated UI dispatch touched)* — Chrome-MCP-driven walk against gleepglorp completed 2026-05-22. Outcomes: steps 1-7 + 10 PASS; step 8 (stale-entry) deferred to operator; step 9 (per-agent overlay) partial — architecture intact, raw-id-label UX in checkbox-mode flagged for F8. See flight-log L7 entry for full results and HAT anomalies (incl. pool-warming friction with Test Connection).

---

## Post-Flight

### Completion Checklist

- [x] All required legs (L1-L6) completed
- [x] L7 HAT completed (8/10 steps PASS; 1 deferred to operator; 1 partial with pre-existing-UX-gap flagged for F8)
- [ ] Code merged on `main` (or stacked behind F2 PR #70 until that merges)
- [ ] Tests passing at or above F2's 2834 baseline + new test counts
- [ ] `agents.md` updated with two codified conventions
- [ ] `ConnectorPlugin` Protocol gains `enumerate_discoverable_entities` documentation
- [ ] `DiscoverableEntities` dataclasses shipped in `connectors/base.py`
- [ ] Pool cache + refresh sweep + API endpoints shipped
- [ ] `discoverable-dropdown.js` component shipped
- [ ] Allowlist + routing-rules + per-agent overlay editors swap chip-lists for dropdowns on Discord accounts
- [ ] `test_default_stub_probe_renders_success_with_no_details` updated to match code (chronic-debt cluster closed)
- [ ] `connector-form-registry.js` top comment carries the consolidated optional-hook table

### Verification

**Mechanical verification** (CI / scripted):
- `pytest tests/test_connectors_discord.py` — pins `DiscordPlugin.enumerate_discoverable_entities` shape
- `pytest tests/test_connectors_pool.py` — pins the new cache field + refresh sweep
- `pytest tests/test_api_connector_accounts.py` (or wherever the new endpoint tests land) — pins GET + POST response shapes + stale-entry semantics
- `pytest tests/browser/test_flow_studio_connector_discoverable_dropdown.py` (new) — pins the dropdown component contract
- `pytest tests/browser/test_flow_studio_connector_account_editor.py` — passes UNMODIFIED for the stub-type chip-list fallback path
- `pytest tests/browser/test_connector_test_connection_button.py` — L2 update lands; all 3 tests pass
- Full suite stays at or above F2 baseline (2834)

**Operational verification** (L7 HAT):
- Real-bot dropdown population works end-to-end
- Typeahead + virtualization work against the test guild's actual entity count
- Stale-entry indicator surfaces real removed entities
- Refresh button works

**Methodology verification**:
- L1's codified conventions are referenceable by name in subsequent flights' design decisions
- F1-debrief Architect-checklist methodology continues to apply: cycle-1 HIGH-severity catches at design time (not at HAT)
- Symbolic-anchor citations default discipline maintained
