# Leg: studio-routing-rules-editor

**Status**: landed
**Flight**: [Multi-Agent Routing and the Platform-Side Command Surface](../flight.md)

## Objective

Add a "Routing Rules" editor to the Studio Connector-Account detail page at `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`. The editor renders between the F6 Allowlist section (line 299) and the F6 Attached Agents read-only summary (line 309). Operator can: author an ordered list of rules `{scope, match, agent}` with Move-up/Move-down ordering controls; select a per-account default agent; save round-trips through the existing `PUT /api/connector-accounts/{id}` endpoint (no new endpoint — `config["routing"]` rides the existing payload, validated by L2's `_validate_config_reserved_keys`). Apply the F6-debrief cycle-1 design-language uptake audit gate. No API endpoint changes, no schema migration, no backend logic changes (L2's validator + L4's engine already consume the persisted shape).

## Context

This is the seventh F7 leg and the only Studio surface. Per Design Decisions in `flight.md`:

- **"Studio surfaces — connector account Routing Rules editor only, no Agent Editor work"** — routing rules are account-scoped; the Agent Editor Connectors tab (F6) gets NO new UI. The new section lives ONLY on the Connectors detail page.
- **"Specificity-then-order precedence"** — the operator authors rules in declared order; the dispatcher walks top-to-bottom and the first match wins. Studio surfaces Move-up / Move-down explicitly so order is visible and editable. No specificity-rank baked into the UI.
- **"Account-config persistence with ordered rule list"** — routing rides on `connector_accounts.config["routing"]`; L2's Pydantic validator already enforces shape; L7 emits the validated shape from the form on save.
- **F6 debrief rec #1 (design-language uptake audit gate)** — at cycle-1 design review of this leg's UI implementation, grep for new custom selectors and challenge each; mandate existing primitives (`.chip-list`, `.editor-section`, `.btn-outlined-primary`, etc.) where possible. This is the discipline F6 codified to prevent design-language drift between bespoke editors.

Key learnings from prior legs:

- L1: parser + Protocol surface — no Studio impact.
- L2: routing-key validator in `db/models.py:_validate_config_reserved_keys`. `_VALID_ROUTING_SCOPES = frozenset({"channel", "thread", "dm", "peer"})` is module-level and importable for the API to surface (currently unused by API; L7 hardcodes the scope list client-side, matching F6's hardcoded-axis pattern in the allowlist editor).
- L3: `SQLiteAgentStore.list_by_connector_account(account_id)` and the API endpoint `GET /api/connector-accounts/{id}/attached-agents` (used by the F6 Attached Agents section). The L7 routing-rule editor's "agent" dropdown reuses this endpoint's response (already fetched on mount; L7 piggy-backs).
- L4: routing engine consumes the persisted shape — no Studio coupling.
- L5: dispatcher composes L4 — no Studio coupling.
- L6: command handlers consume the persisted shape — no Studio coupling.
- F6 L4 / F6 L7 HAT: the connector-account-editor.js renders Pairing (line 289), Allowlist (line 299), Attached Agents (line 309), Test Connection (line 313). L7 inserts the Routing Rules section between Allowlist and Attached Agents.
- F6 L7 HAT surfaced 18+ design-language defects on three Studio surfaces — the cycle-1 audit gate is the precedent L7 inherits to keep the count low.

## Inputs

What exists before this leg runs:

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` (1661 lines) — the F6-shape editor with Pairing / Allowlist / Attached Agents / Test Connection sections; `renderAllowlistSection`, `renderAttachedAgentsSection` are the precedent renderers L7 mirrors.
- `the_one/interfaces/web/api.py:update_connector_account` at line 2171 — PUT endpoint that merges incoming JSON onto the existing account and validates via `ConnectorAccount.model_validate`. The validator already covers `config["routing"]` (L2).
- `the_one/interfaces/web/api.py:list_attached_agents_for_connector_account` at line 2331 — GET endpoint returning `[{name, peers, channels, peers_count, channels_count}, ...]`. The F6 Attached Agents section consumes this; L7 reuses the same response for the agent-dropdown options in routing rules.
- `the_one/db/models.py:_VALID_ROUTING_SCOPES` (L2 module-level constant). Client-side L7 hardcodes the same list — matches F6's hardcoded-axis pattern (the allowlist editor hardcodes `["peers", "channels"]` client-side).
- F1–F7 (post-L6) test suite green: 480 backend tests pass.

## Outputs

What exists after this leg completes:

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` extended with:
  - `renderRoutingRulesSection(account)` renderer.
  - `wireRoutingRulesEvents(container, account, checkDirty)` event-binding.
  - `collectRoutingFromContainer(container)` form-state collector.
  - Routing section inserted into the render pipeline at the position between Allowlist and Attached Agents.
  - Save flow's `collectFormData` extended to merge `config["routing"]` into the PUT payload.
  - The `RESERVED_CONFIG_KEYS` map at line 430 extended with `routing: true`.
- Studio CSS (the relevant `.css` file the existing editor pulls in) extended with the minimal new styles only when existing primitives can't be reused (cycle-1 audit gate enforces this).
- No new backend code; no new API endpoint; no schema migration; no new tests in `tests/test_db_api.py` because the existing PUT endpoint's HTTP test coverage already exercises round-trip on the `config` dict.
- New Playwright / DOM-shape tests under `tests/` (if the project has a JS/UI test surface; otherwise: documented as HAT-validated, deferred to L9).

## Acceptance Criteria

- [ ] `renderRoutingRulesSection(account)` ships in `connector-account-editor.js`:
  - Section wrapper: `<div class="editor-section connector-routing-section">` — mirrors the F6 `.editor-section connector-allowlist-section` shape exactly.
  - Section title: `<div class="section-title">Routing rules</div>`.
  - Rules list rendered as `<table class="connector-routing-table">` paralleling the existing `connector-account-config-table` / `connector-account-secrets-table` at `connector-account-editor.js:463-491` and `:494-523` — the closest editable-table-row precedent in the file. Each `<tr class="connector-routing-row" data-routing-rule-idx="{N}">` carries: scope `<select class="field-input field-select admin-pf-input admin-pf-select">` (hardcoded `channel/thread/dm/peer`), match `<input class="field-input" type="text">`, agent `<select class="field-input field-select admin-pf-input admin-pf-select">` (populated from the GET attached-agents response, same wire-up as F6 Attached Agents), and a trailing actions cell with bare `<button class="connector-routing-move-up-btn">`, `<button class="connector-routing-move-down-btn">`, and `<button class="connector-routing-remove-row-btn">` buttons — NO `.btn-icon` class (no such primitive exists; the F6 kv-tables use bare buttons with the row-specific class).
  - Move buttons use `window.App.icon('chevron-up')` and `window.App.icon('chevron-down')`. `chevron-down` already exists in `the_one/interfaces/web/static/js/icons.js`; `chevron-up` does NOT and MUST be added as a sub-task of L7 (pull the SVG from Lucide v0.265.0 to match the existing entries' source set). Delete button uses the existing `trash` icon (or whichever icon the F6 kv-table delete buttons use — grep to confirm).
  - "Add rule" button below the table: `<button class="btn-outlined-primary kv-add-row-btn connector-routing-add-row-btn">+ Add rule</button>`. Mirrors `connector-config-add-row-btn` and `connector-secrets-add-row-btn` at lines 478 and 506 — literal `+` glyph, NOT `App.icon('plus')`.
  - Per-account default agent dropdown below the rules table, in a `<div class="field-row admin-pf-row">` with a `<label>` + the default-agent `<select>` (same class set as the rule-row dropdowns). Empty option `<option value="">None</option>` plus a `<small class="form-hint">` clarifying "Fall back to first-eligible-alphabetical agent." (Wording matches L4's actual algorithm — verify against `connectors/_routing.py` before HAT.)
  - When `account.config.routing` is absent OR `{"rules": [], "default": null}`, the section renders the empty state with the "Add rule" button visible and the default-agent dropdown set to "None."
- [ ] `wireRoutingRulesEvents(container, account, checkDirty)` ships:
  - Bind click handlers for Add rule / Move-up / Move-down / Delete.
  - Bind change handlers for scope / match / agent / default dropdowns to call `checkDirty()` (mirroring the allowlist editor's pattern).
  - Initial snapshot captured AFTER the agent-dropdown population (the snapshot must reflect the populated form, not the empty-on-mount form).
- [ ] `collectRoutingFromContainer(container)` ships:
  - Returns `{rules: [...], default: str | null}` matching the L2-validated shape.
  - Skips rules with empty `match` or empty `agent` (operator authored a stub and didn't finish; treated as "not saved").
  - Default dropdown's "None" option returns `null`.
- [ ] Render pipeline updated: routing section rendered between Allowlist (line 299) and Attached Agents (line 309). The renderer is gated by `!isCreate` mirroring the other sections (routing rules are edit-only — fresh accounts have no agents attached yet).
- [ ] `RESERVED_CONFIG_KEYS` at line 430 extended with `routing: true`. (Prevents the kv-row editor from displaying routing as a "custom" config key.)
- [ ] `collectFormData` (line ~1006) extended to merge `config["routing"]` from `collectRoutingFromContainer` into the PUT body, alongside the existing pairing/allowlist merge. The merge ONLY emits the `routing` key when `routes.length > 0 OR default !== null` — empty-default + empty-rules emits NO `routing` key (matches allowlist's pattern: "absent = unrestricted").
- [ ] Wire setup at line ~796 calls `wireRoutingRulesEvents` alongside the existing `wireAllowlistEvents`. Order: pairing → allowlist → ROUTING (new) → attached-agents.
- [ ] Save round-trip works: operator authors rules, saves, reloads the editor, sees the same rules in the same order. Verified at HAT (L9) and via a single regression test in `tests/test_db_api.py` (or wherever the existing PUT-round-trip tests live) — `test_update_connector_account_routing_round_trips` posts a routing config, GETs, asserts the payload matches.
- [ ] **Cycle-1 design-language uptake audit gate** (F6 debrief rec #1):
  - At leg-design-review time, grep for newly-introduced custom CSS selectors in the leg's diff (or in the planned implementation per Implementation Guidance). For each new selector, ask: can an existing primitive (`.chip-list`, `.editor-section`, `.btn-outlined-primary`, `.btn-icon`, `.indicator-led`, etc.) serve the same purpose? If yes, mandate the primitive.
  - The audit's findings are recorded in the L7 design-review log entry. Cycle-1 means the audit fires BEFORE implementation lands — F6's HAT 18-defect surprise should not recur.
- [ ] No new backend code:
  - `the_one/interfaces/web/api.py` unchanged.
  - `the_one/db/models.py`, `the_one/db/repositories.py`, `the_one/db/schema.py` unchanged.
  - `the_one/connectors/_routing.py`, `_acl.py`, `_inbound.py`, `_commands.py` unchanged.
- [ ] Round-trip regression test in `tests/test_db_api.py` (or peer file):
  - `test_update_connector_account_routing_round_trips` — `PUT /api/connector-accounts/{id}` with `config={"routing": {"rules": [{"scope":"channel","match":"C1","agent":"alpha"}], "default": "bravo"}}`; assert 200; GET the account; assert `config["routing"]` matches the input verbatim.
- [ ] F1–F7 (post-L6) regression suite passes byte-identically. No backend code paths touched.

## Verification Steps

How to confirm each criterion is met:

**Rendering** (manual / HAT):

- Open the editor on an existing connector account. Confirm the Routing Rules section renders between Allowlist and Attached Agents.
- "Add rule" → new empty row appears.
- Author a rule: select scope `channel`, type match `C1`, select agent from dropdown.
- Add a second rule; click Move-up on the second row → second becomes first. Click Move-down → original order restored.
- Delete a rule → row removed.
- Set default to an attached agent; save; reload → state preserved.

**Save round-trip** (automated):

- `test_update_connector_account_routing_round_trips` in `tests/test_db_api.py` — PUT + GET parity.

**Design-language audit** (cycle-1, at design-review time):

- The Developer agent's design review counts new custom CSS selectors. The Acceptance Criteria gate fires if any new selector exists that an existing primitive could serve.

**Regression**:

- `docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py tests/test_db_api.py -x --timeout 30'` — full suite green. Backend untouched.

## Implementation Guidance

### 1. Renderer

Add `renderRoutingRulesSection(account)` after `renderAllowlistSection` (around line 1303-1305). Mirror the existing renderer's structure: `editor-section` wrapper, section-title, content div, hidden data-state attributes for dirty-tracking.

The agent dropdown is async-populated. Initial render emits an empty `<select>`; the mount sequence calls `fetchAttachedAgents(container, account.id)` at `connector-account-editor.js:812`; the function body lives at `:1384-1412`. L7 piggy-backs: in the fetch's `.then` callback, iterate the response and inject `<option value="{name}">{name}</option>` into BOTH (i) every rule's agent dropdown AND (ii) the default-agent dropdown.

The scope dropdown is static client-side: hardcode `["channel", "thread", "dm", "peer"]` — matches F6's hardcoded-axis pattern in the allowlist editor.

Rule rows use a list-with-controls pattern. Existing precedent: F6 chip-list rows have a delete button. Routing rules add Move-up and Move-down controls — these need NEW icon buttons (or existing icons like `arrow-up` / `arrow-down` from the project's icon library; check `window.App.icon` for available glyphs).

### 2. Wire events

Add `wireRoutingRulesEvents(container, account, checkDirty)` after `wireAllowlistEvents`. The handler binds:
- "Add rule" click → append a fresh row, focus the scope dropdown.
- Move-up click → swap with previous sibling; call `checkDirty()`.
- Move-down click → swap with next sibling; call `checkDirty()`.
- Delete click → remove the row; call `checkDirty()`.
- Any select / input change → call `checkDirty()`.

Snapshot timing: the routing section's agent-dropdown options are populated ASYNCHRONOUSLY (in `fetchAttachedAgents`'s `.then` at `:1384-1412`). The dirty-tracking baseline snapshot MUST reflect the populated form — otherwise the operator's first edit will appear "dirty" against an empty-options baseline that no longer exists. Two acceptable approaches: (a) trigger a fresh `recaptureSnapshot()` call inside the `fetchAttachedAgents` `.then` AFTER the routing-section dropdowns are populated; (b) defer the initial snapshot in `wireEditorEvents` until the agent-fetch promise resolves. Pick (a) — it's localized to the routing-section concern and doesn't change F6's snapshot-timing for the rest of the editor.

### 3. Collect form state

Add `collectRoutingFromContainer(container)` after `collectAllowlistFromContainer` (around line 1529-1550):

```javascript
function collectRoutingFromContainer(container) {
  var section = container.querySelector('.connector-routing-section');
  if (!section) return null;

  var rules = [];
  var ruleRows = section.querySelectorAll('[data-routing-rule]');
  for (var i = 0; i < ruleRows.length; i++) {
    var row = ruleRows[i];
    var scope = (row.querySelector('[data-routing-scope]') || {}).value;
    var match = (row.querySelector('[data-routing-match]') || {}).value || '';
    var agent = (row.querySelector('[data-routing-agent]') || {}).value || '';
    match = match.trim();
    if (!scope || !match || !agent) continue;
    rules.push({scope: scope, match: match, agent: agent});
  }

  var defaultSelect = section.querySelector('[data-routing-default]');
  var defaultAgent = defaultSelect ? defaultSelect.value : '';
  if (defaultAgent === '') defaultAgent = null;

  return {rules: rules, default: defaultAgent};
}
```

### 4. Save-pipeline merge

In `collectFormData` (around line 1026-1031, where allowlist is merged), add after the allowlist block:

```javascript
var routingState = collectRoutingFromContainer(container);
if (routingState && (routingState.rules.length > 0 || routingState.default !== null)) {
  config.routing = routingState;
}
```

The conditional "rules.length > 0 OR default !== null" matches the F6 allowlist pattern: empty-by-everything means "absent" — saving OMITS the `routing` key entirely so the default-permit semantic applies.

### 5. Reserved-keys map

At line 430:

```javascript
var RESERVED_CONFIG_KEYS = { pairing: true, allowlist: true, routing: true };
```

Prevents the generic kv-row editor from showing `routing` as a custom key the operator should hand-edit.

### 6. Render pipeline insertion

Around line 309 (after `renderAttachedAgentsSection`-equivalent existing call):

```javascript
if (!isCreate) {
  html += renderAllowlistSection(account);
}

// NEW for F7 L7:
if (!isCreate) {
  html += renderRoutingRulesSection(account);
}

if (!isCreate) {
  html += renderAttachedAgentsSection();
}
```

### 7. Round-trip test

Add to `tests/test_db_api.py` (or `tests/test_api_connector_accounts.py` — depending on where existing connector-account API tests live; grep for `update_connector_account` in tests to find the right file):

```python
async def test_update_connector_account_routing_round_trips(...):
    # ... seed an account ...
    response = await client.put(f"/api/connector-accounts/{account_id}", json={
        "config": {"routing": {"rules": [{"scope": "channel", "match": "C1", "agent": "alpha"}], "default": "bravo"}},
    })
    assert response.status_code == 200

    get_resp = await client.get(f"/api/connector-accounts/{account_id}")
    assert get_resp.json()["config"]["routing"] == {
        "rules": [{"scope": "channel", "match": "C1", "agent": "alpha"}],
        "default": "bravo",
    }
```

### 8. Order of file edits

1. `the_one/interfaces/web/static/js/icons.js` — add `chevron-up` SVG (pulled from Lucide v0.265.0; mirror the existing `chevron-down` entry's structure). Required before the editor changes so `window.App.icon('chevron-up')` resolves.
2. `connector-account-editor.js`:
   - Add `renderRoutingRulesSection` adjacent to `renderAllowlistSection` (~line 1303-1305).
   - Add `wireRoutingRulesEvents` adjacent to `wireAllowlistEvents` (~line 796-810).
   - Add `collectRoutingFromContainer` adjacent to `collectAllowlistFromContainer` (~line 1529-1565).
   - Insert routing section into render pipeline between Allowlist (`:299`) and Attached Agents (`:309`) — gated by `!isCreate`.
   - Extend `RESERVED_CONFIG_KEYS` at `:430` with `routing: true`.
   - Extend `collectFormData` (~`:1026-1031`) to merge `config["routing"]` per the conditional-emit rule.
   - Extend `fetchAttachedAgents` `.then` callback (`:1384-1412`) to populate the agent dropdowns in the routing section.
3. CSS — only if existing primitives can't be reused. Cycle-1 audit verdict: zero new bespoke selectors required; `.connector-routing-table` may need minimal column-width tuning. Use CSS Grid / table-cell sizing already present in `connector-account-config-table` if possible.
4. `tests/test_db_api.py` — add `test_update_connector_account_routing_round_trips`.
5. Run full regression: `docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py tests/test_db_api.py -x --timeout 30'`.
6. HAT (L9) for visual + flow validation.

### 9. Cycle-1 design-language audit findings (recorded per F6 debrief rec #1)

Audit was run at design-review time. Verdict: ZERO new bespoke selectors land beyond the F6 naming convention (`.connector-routing-section`, `.connector-routing-table`, `.connector-routing-row`, and three per-row button classes that mirror the existing `*-remove-row-btn` pattern).

| Proposed pattern | Mandated primitive |
|---|---|
| Section wrapper | `.editor-section connector-routing-section` (mirrors `.editor-section connector-allowlist-section`) |
| Section heading | `<div class="section-title">Routing rules</div>` |
| Rules list | `<table class="connector-routing-table">` paralleling `connector-account-config-table` (`connector-account-editor.js:463-491`) and `connector-account-secrets-table` (`:494-523`) |
| Per-row `<tr>` | `connector-routing-row` with `data-routing-rule-idx="{N}"` (mirrors `data-row-idx` at `:485, 514`) |
| Scope / agent / default dropdowns | `<select class="field-input field-select admin-pf-input admin-pf-select">` (canonical 4-class set used at `:107, 396`) |
| Match input | `<input class="field-input" type="text">` (matches per-row config/secrets inputs at `:486-487`) |
| "Add rule" button | `<button class="btn-outlined-primary kv-add-row-btn connector-routing-add-row-btn">+ Add rule</button>` (literal `+` glyph; matches `connector-config-add-row-btn` at `:478`) |
| Per-row Delete button | `<button class="connector-routing-remove-row-btn">{icon('trash')}</button>` (bare button; matches `config-remove-row-btn` / `secret-remove-row-btn` at `:488, 520`). **NO `.btn-icon` class — no such primitive exists.** |
| Per-row Move-up / Move-down buttons | Same shape — bare buttons with classes `connector-routing-move-up-btn` / `connector-routing-move-down-btn` and `window.App.icon('chevron-up')` / `('chevron-down')` icons. **`chevron-up` must be ADDED to `icons.js` first** (step 1 of the file-edit order). |
| Default-agent row | `<div class="field-row admin-pf-row">` with `<label>` + `<select>` (matches form-field row pattern at `:381-399`) |
| "None" option fallback hint | `<small class="form-hint">` (matches `:1249, 1257`) |

### 10. Things NOT in scope

- Rule preview / simulator ("paste a sample channel_id, see which rule matches") — deferred to F10 hardening per flight Adaptation Criteria.
- Per-platform slash-command registration UI — F8 / F9 territory.
- Per-agent routing UI (Agent Editor) — deliberately excluded per flight Design Decision.
- Backend changes to `api.py`, `models.py`, repositories — none needed; L2 already validates the persisted shape.

## Edge Cases

- **Empty rules + non-null default**: legal; `collectRoutingFromContainer` returns `{rules: [], default: "alpha"}`; save emits `config["routing"]` with the default agent. The routing engine (L4) skips rule-walk, hits the default at step 3.
- **Stub rule (operator added a row but didn't fill in match or agent)**: `collectRoutingFromContainer` skips the row. Saving emits a shorter rules list. This is the right UX — don't hide stub rows from the operator's view, but don't persist them either.
- **Default agent points to an agent no longer attached**: the routing engine (L4) treats this as "default ineligible — fall through to first-eligible." Studio editor doesn't validate at save time (the dropdown's options reflect the CURRENT attached-agents response — operator can't pick a non-attached agent from the dropdown — but if an agent is detached AFTER the rule was saved, the persisted state is stale; the routing engine handles this gracefully).
- **Routing scope `dm` rule with `match` = peer_id**: the routing engine (L4) interprets this against `envelope.peer_id` AND requires `envelope.thread_id is None`. Studio doesn't enforce platform-specific match-shape validation (e.g. Discord snowflake format) — the operator authors strings; the engine compares strings.
- **Operator authors a thread-scope rule but the F3 session-key normalization collapses threads into the parent channel**: per L4's edge cases, the rule would never fire. Studio editor doesn't warn about this. F8 / F9 plugins may add per-plugin warnings in a future leg.

## Files Affected

- `the_one/interfaces/web/static/js/icons.js` — add `chevron-up` SVG (precondition for the editor's move buttons).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — add `renderRoutingRulesSection`, `wireRoutingRulesEvents`, `collectRoutingFromContainer`; extend render pipeline, wire setup, `collectFormData`, `RESERVED_CONFIG_KEYS`, `fetchAttachedAgents` `.then`.
- CSS — minimal additions per cycle-1 audit (likely zero or column-width tuning only).
- `tests/test_db_api.py` — one new round-trip regression test.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)

## Citation Audit

Citations verified against current code at leg design time:

| Citation | Status | Notes |
|----------|--------|-------|
| `connector-account-editor.js:299` (Allowlist render call) | OK | F6 L4 site verified |
| `connector-account-editor.js:309` (Attached Agents render call) | OK | F6 L4 site verified |
| `connector-account-editor.js:430` (RESERVED_CONFIG_KEYS map) | OK | F6 L4 site verified |
| `connector-account-editor.js:567` (allowlist collection in `collectFormData`) | OK | F6 L4 site verified |
| `connector-account-editor.js:796-802` (wire setup) | OK | F6 L4 site verified |
| `connector-account-editor.js:1006-1031` (collectFormData merge block) | OK | F6 L4 site verified |
| `connector-account-editor.js:1231` (renderAllowlistSection) | OK | F6 L4 renderer |
| `connector-account-editor.js:1307` (renderAttachedAgentsSection) | OK | F6 L4 renderer |
| `connector-account-editor.js:1529` (collectAllowlistFromContainer) | OK | F6 L4 collector |
| `the_one/interfaces/web/api.py:update_connector_account` (PUT endpoint at line 2171) | OK | Existing endpoint round-trips `config` dict; L2 validator covers `routing` |
| `the_one/interfaces/web/api.py:list_attached_agents_for_connector_account` (GET attached-agents at line 2331) | OK | L3 endpoint; reused for agent-dropdown options |
| `the_one/db/models.py:_VALID_ROUTING_SCOPES` | OK | L2 module-level constant; L7 hardcodes client-side to match F6 pattern |

12 in-leg-artifact code-location citations verified.
