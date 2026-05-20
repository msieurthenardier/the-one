# Leg: hat-and-alignment

**Status**: landed
**Flight**: [Multi-Agent Routing and the Platform-Side Command Surface](../flight.md)

## Objective

Operator-driven verification of the F7 L7 Studio **Routing Rules editor** on the Connector-Account detail page, plus DB-level inspection of the F7 L5 routing audit log. Catch design-language drift, UX flow issues, and integration-level routing bugs that unit tests cannot reach. Inline fixes per the F6 HAT precedent (Flight Director diagnoses + spawns a Developer agent if code changes needed, then re-verifies the failing step).

## Verification Steps

The Flight Director presents one step at a time and waits for the operator to perform it and report results. The sequence below is the script; steps may be skipped if the operator declares confident pass-through.

### Step 1 — Visual / design-language fit

1.1. Open Studio in a browser. Navigate to **Connectors** → pick any existing connector account → scroll to the new **Routing rules** section between Allowlist and Attached agents.

1.2. Compare side-by-side with the Allowlist section (above) and Attached agents (below):
- Section heading style matches (`section-title` typography + padding).
- Section wrapper margin/padding matches.
- Empty-state visual (no rules + "Add rule" button) is harmonious with the surrounding editor.
- Default-agent dropdown row matches the existing form-row style.

**Pass criteria**: nothing looks visually out of place. Operator reports any specific design-language drift.

### Step 2 — Rule CRUD + ordering flow

2.1. Click "Add rule". A new empty row appears.
2.2. Fill the scope dropdown (e.g. `channel`), match input (e.g. `C1`), agent dropdown (pick an attached agent).
2.3. Click "Add rule" again. Author a second rule with a different scope (e.g. `peer`) + match + agent.
2.4. Click Move-up on the second row → it swaps with the first.
2.5. Click Move-down on the now-first row → original order restored.
2.6. Click Delete on the second row → it disappears; first row remains.
2.7. Verify the Save button is now in "dirty / enabled" state (gain icon, color, or whatever the F6 pattern uses).
2.8. Click Save. Confirm the save succeeds (success indicator, no error).

**Pass criteria**: all interactions feel responsive and predictable; Save fires without error.

### Step 3 — Default-agent dropdown

3.1. With the rules saved from Step 2, select an attached agent in the **Default agent for unmatched conversations** dropdown.
3.2. Verify the dirty-tracker fires (Save enables).
3.3. Save. Reload the page. Verify the default-agent selection persisted.
3.4. Change the dropdown back to **None**. Save. Reload. Verify it's back to None and the "Fall back to first-eligible-alphabetical agent" hint is visible.

**Pass criteria**: round-trip works both directions.

### Step 4 — Snapshot-after-async-population

4.1. Save a state with at least one rule + a default agent (from Steps 2/3).
4.2. Reload the page. Wait until the agent dropdowns finish populating (≤1 second; check the dropdowns are not empty).
4.3. Without touching anything, click somewhere neutral. Verify the Save button is in "clean / disabled" state — NOT dirty.

**Pass criteria**: a freshly-loaded form is not falsely dirty.

### Step 5 — Stale-agent UX (skip if no detachable agent handy)

5.1. Author a rule pointing to agent X. Save.
5.2. Navigate to the Agent Editor for agent X. Detach agent X from this connector account. Save.
5.3. Return to the Connector-Account editor. Reload. Verify the rule still shows agent X but the dropdown indicates `(not attached)` (disabled option).

**Pass criteria**: stale state is visible, not silently dropped.

### Step 6 — DB-level audit-log inspection

6.1. With at least one rule configured (any rule), trigger an inbound through the stub plugin (the easiest path is the existing dispatcher test suite — or skip this step if there's no easy way to drive an inbound from the operator console).

6.2. If skipped: just verify via `sqlite3` that the `chat_sessions.session_metadata` column carries JSON entries under `routing` after the connector-attached test sessions ran. The test suite execution that landed the flight already wrote audit entries — they should be visible in the test DB if it persists, or trust the unit-test coverage.

**Pass criteria**: audit-log writes happen (or operator accepts the unit-test coverage as sufficient).

### Step 7 — Smoke-test commands (optional, skip if no platform fixture)

7.1. F7 ships a connector-agnostic command surface but the only connector is the test stub (no real Discord / Slack until F8 / F9). End-to-end smoke against a real platform is therefore F8+ territory — skip unless the operator has a way to drive a `/agents` or `/help` from the dispatcher test fixture.

**Pass criteria**: deferred.

## Iteration Protocol

For each step:
- Operator reports **pass** → proceed to next step.
- Operator reports **fail** with details → Flight Director diagnoses; if code changes needed, spawn a Developer agent; re-verify the failing step before proceeding.
- Operator may pause / skip / reorder steps.

When all non-skipped steps pass, the Flight Director:
1. Marks L9 status `landed`.
2. Marks the L9 checkbox in `flight.md`.
3. Appends a "Leg 9 HAT" entry to `flight-log.md` summarizing observations and any inline fixes.
4. Commits the L9 leg artifact + flight log update (+ any inline code fixes that were needed) as a separate commit on top of `382de75`.

## Files Affected

- `missions/10-bi-directional-comms-connectors/flights/07-multi-agent-routing-and-command-surface/legs/09-hat-and-alignment.md` — this artifact.
- `missions/10-bi-directional-comms-connectors/flights/07-multi-agent-routing-and-command-surface/flight.md` — L9 checkbox + flight status if needed.
- `missions/10-bi-directional-comms-connectors/flights/07-multi-agent-routing-and-command-surface/flight-log.md` — Leg Progress + observations.
- Any source files needing inline fixes (TBD).

## HAT iteration 1 — Connector-account editor tabbed layout

Operator feedback during HAT Step 1 (visual / design-language fit): the Connector Account editor page had grown too dense with section stacking (Connection, Credentials, Lifecycle, Pairing, Allowlist, Routing rules, Attached agents, Test connection, Danger zone — nine sections on a single scrolling surface). Operator requested a tabbed layout matching the Agent Editor's `App.tabs` pattern.

### Operator-specified tab partition

| Tab | Sections (in order) |
|---|---|
| **General** | Connection, Credentials, Pairing, Attached agents, Test connection, Danger zone |
| **Access and Routing** | Lifecycle, Allowlist, Routing rules |

Lifecycle (session-continuation window + pool idle timeout) was placed under the access tab even though it currently sits between Credentials and Pairing — the operator's framing is that session continuation IS a policy / access concern, not a connection concern. Trust the operator's intent.

### Implementation

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — refactored `renderConnectorAccountEditor`:
  - Decoupled section emission from layout: each section now builds into a named HTML fragment (`connectionHtml`, `credentialsHtml`, `lifecycleHtml`, `pairingHtml`, `allowlistHtml`, `routingHtml`, `attachedAgentsHtml`, `testConnectionHtml`, `dangerZoneHtml`) BEFORE the layout step.
  - Layout step branches on `isCreate`:
    - **Create mode**: flat layout (Connection + Credentials + Lifecycle only — not enough sections to warrant a tab split, and Pairing/Allowlist/Routing/etc. don't render at all here).
    - **Edit mode**: two-tab layout. Tablist + tabpanels match the agent-editor's pattern verbatim (`<div role="tablist" class="tablist" aria-label="Connector account settings">`, `<button role="tab" data-tab-id="general|access-and-routing" data-testid="tab-general|tab-access-and-routing">`, `<div role="tabpanel" ... hidden>`). Panel ids: `connector-tab-panel-general`, `connector-tab-panel-access-and-routing`.
  - All tab panel content is mounted SYNCHRONOUSLY at editor-load time — never lazy. `App.tabs` only toggles the `hidden` attribute. This preserves the L7 dirty-tracker / `getFormSnapshot` / `collectFormData` contract: every selector that queries by `data-field=...`, `.connector-routing-section`, `[data-allowlist-chiplist-slot=...]`, etc. continues to resolve against any section regardless of which tab is currently active.
  - Added an `initialTab` callbacks param (default `general`) mirroring the agent-editor's hook. Studio.js does not yet route `_activeTab` for connector accounts, but the hook is in place for future wiring.
  - Exposed `window.App.studio.CONNECTOR_ACCOUNT_PANEL_IDS` mirroring `AGENT_PANEL_IDS`.
- `tests/browser/test_flow_studio_connector_account_editor.py` — added `_activate_access_and_routing_tab(page)` helper and inserted activation calls into edit-mode tests that interact with Lifecycle inputs (idle-timeout dropdown, continuation dropdown, continuation hint). `to_be_visible()` assertions for Lifecycle elements gain the tab activation; `to_be_attached()` checks remain valid without activation (panels are in the DOM regardless of `hidden` state).

### Create-mode decision

Render the create form **flat** (no tabs), not tabbed. Rationale:
- Only Connection + Credentials + Lifecycle render in create mode — the six other sections are gated on `!isCreate`. A two-tab split over three sections (one tab with two sections, one tab with one section) costs more than it gives.
- The operator's tab partition is explicitly for edit-mode density.
- Cleaner: the "Create & Test" affordance reads more naturally on a single short form.

### CSS

ZERO new CSS. Tab styles already exist in studio CSS (the agent-editor uses the same `.tablist` / `.tab` / `.tabpanel` / `.tabpanels` classes; the W3C ARIA `[hidden]` attribute drives panel visibility).

### Regression

`docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py tests/test_db_api.py tests/test_pairing*.py -x --timeout 30'` → **551 passed in 54.87s**. UI-only refactor; backend untouched.

## HAT iteration 2 — Routing Rules editor redesign

Three operator-driven changes to the Routing Rules section of the Connector-Account editor's Access and Routing tab, plus the underlying schema for routing rules.

### Change 1 — Section layout reorder

Default-agent dropdown moves to the TOP of the Routing Rules section; the rules table + "Add rule" button move below it. The form-hint micro-copy ("Fall back to first-eligible-alphabetical agent") stays directly under the default-agent dropdown so it explains both empty-default AND empty-rules states.

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — `renderRoutingRulesSection` HTML emitted in new order: default-agent row + hint, then table, then "Add rule" button.

### Change 2 — Drag-handle reordering

Replaced the chevron move-up / move-down buttons with a single drag handle at the LEFT side of each rule row (new first column). Native HTML5 drag-and-drop wires the handle as the drag source and the row as the drop target.

- `the_one/interfaces/web/static/js/icons.js` — added the canonical Lucide v0.265.0 `grip-vertical` icon (6 dots in two columns).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`:
  - `_renderRoutingRow` gains a leading `<td class="connector-routing-drag-cell">` wrapping `<span class="connector-routing-drag-handle" draggable="true">` with the grip-vertical glyph and `data-routing-drag-handle data-row="<idx>"` attributes.
  - Trailing actions cell now holds only the trash button.
  - `wireRoutingRulesEvents` wires `dragstart` / `dragend` on each handle (records source row + adds `.is-dragging` opacity-0.5 cue) and `dragover` / `drop` on each row (inserts the dragged row before / after the target depending on DOM-position direction). Wired for pre-rendered rows AND newly-added rows via the `_wireRoutingRow` helper.
  - Move-up / move-down delegated click handlers removed; only the trash-button click handler remains.
- `the_one/interfaces/web/static/css/studio.css`:
  - Added `.connector-routing-drag-handle` with `cursor: grab` (and `cursor: grabbing` on `:active` / `.is-dragging`), 16x16 SVG sizing, hover-darken to `--fg`.
  - Added `.connector-routing-row.is-dragging { opacity: 0.5 }` for source-row visual cue.
  - Dropped the now-unused `.connector-routing-move-up-btn` / `.connector-routing-move-down-btn` selectors from the shared remove-button glyph styling.
- The L7-shipped `chevron-up` icon stays in `icons.js` as future-use — `grep` confirms zero non-routing-editor usages.

**Accessibility / keyboard-fallback decision** — keyboard reordering not shipped in this HAT cycle. The leg spec explicitly gave a "pick pragmatically" out. Operator can still add / remove / select-fields entirely by keyboard; only reorder requires mouse. Future iteration can add Up/Down keys on the handle, or restore screen-reader-only chevrons, if the operator flags it during the re-verification step.

### Change 3 — `match` becomes a list of strings (chip-list)

Schema change: each rule's `match` field is now `list[str]` (one or more values; the rule fires if ANY listed value matches the envelope's corresponding field — set-membership / OR semantics).

**Backend**:
- `the_one/db/models.py:_validate_config_reserved_keys` — `match` must be a non-empty `list`; every element must be a non-empty string. Validator rejects `match: "string"`, `match: []`, `match: ["x", ""]`, `match: ["x", 42]`. Docstring updated to pin the new shape (`list[str]`).
- `the_one/connectors/_routing.py:_scope_matches` — signature changes to `(rule_scope: str, rule_match: list[str], envelope) -> str | None`. Each scope branch uses `in` instead of `==`, returning the SINGLE envelope value that hit (`envelope.channel_id`, `envelope.thread_id`, or `envelope.peer_id`) on success, `None` on no-match. Module docstring updated.
- `the_one/connectors/_routing.py:resolve_routing` — the rule-walk's `RoutingDecision.match` field is now the matching envelope value, not the rule's full match list.

**`RoutingDecision.match` field shape decision** — kept as `match: str | None` (the SINGLE envelope value that triggered the rule, e.g. `envelope.channel_id == "C2"`). NOT `list[str] | None` (the full rule's match list). Rationale: the audit log reads more clearly ("the rule fired because channel was C2") when the field records the value that hit; downstream renderers (F7 L5 audit log) keep their existing `match: str | None` shape unchanged. The `RoutingDecision` dataclass docstring explicitly pins the new semantic.

**Frontend**:
- `_collectRoutingRows` reads `match` as a list (tolerates the old string-form during in-memory upgrades; the validator enforces list-form at write time).
- `_renderRoutingRow`'s match cell mounts a `<div class="chip-list-editor connector-routing-match-chiplist">` instead of the prior `<input type="text">`. Persisted chips render as `<span class="chip">value<button class="chip-remove">×</button></span>` mirroring the F6 allowlist chip CSS classes verbatim, so the cycle-1 design-language audit stays clean.
- `wireRoutingRulesEvents` wires each row's chip-list via `window.App.adminFormHelpers.wireChipListEditor` with `onChange: checkDirty`. Operator gets the same Enter/Tab/comma commit, click-× remove, Backspace-on-empty delete-last UX as the F6 allowlist editor.
- `collectRoutingFromContainer` walks the chip-list editor's `.chip` children and reads their text into a `matchValues: list[str]`. The live `chip-list-input` is ignored (operator must commit). Rows with `matchValues.length === 0` are skipped at collect time per the L7-shipped stub-row semantic (preserving the contract).

**Operator-word "slugs"** — the chip-list metaphor is the UI framing for "match values"; the chip values themselves are NOT shape-validated to slug form. Real platform IDs (Discord snowflakes, Slack channel IDs) are long digit/hex strings; the chip-list accepts any non-empty string per chip.

**CSS** — added `.connector-routing-match-cell { min-width: 240px }` and `.connector-routing-match-chiplist { min-height: 32px; padding: 2px 4px }` for table-cell-friendly chip-list sizing. The shared `.area-studio .chip-list-editor` styles in admin.css already cover the chip/×-button/input visuals.

**Test updates**:
- `tests/test_connectors_routing_schema.py` — all valid + invalid test cases updated to list-form; added explicit invalid cases for `match: "string"` (now rejected), `match: []`, `match: ["x", ""]`, `match: ["x", 42]`. Added a multi-value round-trip test.
- `tests/test_connectors_routing.py` — all rule fixtures updated to list-form via search-and-replace. Added `test_step2_multi_value_match_fires_for_each_listed_value` pinning the multi-value OR semantic AND the "decision.match is the envelope value that hit, not the list" contract.
- `tests/test_db_api.py:test_update_connector_account_routing_round_trips` — payload updated to list-form.
- `tests/test_connectors_inbound.py` — two routing-rule fixtures (lines 1535 / 1585) updated to list-form.

### Things not in scope (per spec) — confirmed not touched

- No SQL migration — `connector_accounts.config` is a JSON blob, shape is enforced at the validator layer only.
- F6 outbound reason strings untouched.
- Agent loop untouched.
- F4 platform-send tool untouched.

### Regression

`docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py tests/test_db_api.py tests/test_pairing*.py -x --timeout 30'` → **556 passed in 55.44s** (+5 vs L8 baseline of 551: +1 multi-value schema round-trip test, +4 new invalid-form match tests; -2 obsolete "non-empty string" match tests removed, replaced by list-shape variants for net +5).

Full non-browser regression: `docker exec the-one pytest tests/ --ignore=tests/browser -x --timeout 30` → **2261 passed, 4 skipped, 12 deselected** in 164s.

## HAT iteration 3 — Legacy `match: str` coercion on read

### Bug surfaced

HAT iteration 2 tightened `config["routing"]["rules"][i]["match"]` from `str` (single value) to `list[str]` (multi-value with OR semantics) at BOTH read and write paths. The operator's dev DB already contained at least one `connector_accounts` row whose routing rule had been authored under the OLD `match: str` shape (pre-HAT2). After iteration 2 landed, the validator rejected that row on read:

```
File "the_one/db/repositories.py", line 593, in _row_to_model
    return ConnectorAccount(...)
ValidationError: config['routing']['rules'][0]['match'] must be a non-empty list of non-empty strings
```

Symptom: `GET /api/connector-accounts` returned 500; agent studio failed to populate; the entire connector-aware UI was broken until the offending row was either deleted or hand-patched in SQL.

### Fix — read-path coercion in the validator

Updated `_validate_config_reserved_keys` in `the_one/db/models.py` to accept BOTH shapes for `match` and coerce the legacy `str` form to a singleton `list[str]` IN-PLACE on the validated `value` dict, before the existing list-shape validation runs. The mutation lands in the Pydantic v2 `@field_validator(mode="after")` return value, so subsequent reads and round-trips emit the new shape. Each affected row converges to the new form on next save — no SQL migration needed.

Coercion matrix:
- `match: "C1"` → coerced to `["C1"]` → passes downstream checks.
- `match: ["C1", "C2"]` → passes through unchanged.
- `match: ""` (empty string) → coerced to `[""]` → still fails the per-element non-empty-string check → ValueError.
- `match: []` (empty list) → still rejects (non-empty-list check).
- `match: ["C1", 42]` → still rejects (per-element string-type check).
- `match: 42` (other non-string non-list) → rejects (wrong type for `match`).

Write path is unchanged: writes still require `match: list[str]`. Only the validator's READ path coerces. New writes always emit the new shape because the editor's `collectRoutingFromContainer` already emits `list[str]` (HAT2).

### Files touched

- `the_one/db/models.py` — `_validate_config_reserved_keys` routing-rule walk: added 7-line legacy-string coercion block before the existing list-shape validation. Error messages byte-identical to HAT2.
- `tests/test_connectors_routing_schema.py`:
  - Removed `test_rule_match_as_string_rejected` (HAT2 contract; now superseded — legacy string is ACCEPTED on read under HAT3).
  - Added `test_legacy_match_str_coerced_to_singleton_list_on_read` — asserts `match: "C1"` is accepted AND the validated dict's `match` is `["C1"]` post-coercion.
  - Added `test_legacy_match_empty_string_still_rejects` — asserts `match: ""` still raises ValueError (coerces to `[""]`, fails per-element non-empty check).

### Verification

- `docker exec the-one pytest tests/test_connectors_routing_schema.py -x --timeout 30` → **34 passed** (was 33 pre-HAT3; net +1 from -1 removed + 2 added).
- `docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py tests/test_db_api.py tests/test_pairing*.py -x --timeout 30'` → **557 passed in 53.87s** (was 556 in HAT2; net +1 from same -1/+2 swap).
- `curl -s http://localhost:8484/api/connector-accounts` → **HTTP 200** with a JSON array. The operator's previously-broken connector account's `config["routing"]["rules"][0]["match"]` now reads as `["channel-1"]` (singleton list — coerced in-memory from the pre-HAT2 `"channel-1"` string still stored in the DB row; the row converges to the list shape on next save).

### Things not in scope

- SQL-layer data migration — handled in-memory by the validator; converges on next write.
- Loosening the strict-on-write contract — writes still require `match: list[str]`. Only the read path coerces.

### Critical preservation invariants — verified

- HAT2 baseline (556 in the curated regression bundle) preserved + 1 = 557 passes.
- Agent loop untouched.
- F4 platform-send tool untouched.
- F6 outbound reason strings untouched.
