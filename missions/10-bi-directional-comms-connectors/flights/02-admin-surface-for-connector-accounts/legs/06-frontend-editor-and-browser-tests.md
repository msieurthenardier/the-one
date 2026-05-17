# Leg: frontend-editor-and-browser-tests

**Status**: completed
**Flight**: [Admin Surface for Connector Accounts](../flight.md)

## Objective

Land the full Studio connector-account editor (replacing leg 5's placeholder), with editor-header / Connection / Credentials / Lifecycle / Test Connection / Danger Zone sections, masked-secret round-trip, the "Create & Test" combined-action button on the create form, the labeled k/v details renderer, and M04/M06 design tokens throughout. Ship the three browser-flow test files paralleling the MCP equivalents (editor, test-connection button, create-and-test) plus targeted augmentations to the leg-5 navigation file.

## Context

### Why this leg

Leg 5 shipped the routing + grid + a 34-LoC placeholder editor file. This leg replaces that placeholder with the full operator-facing editor. After this leg lands:

- The full Connector Accounts CRUD + probe surface is operator-usable end-to-end.
- The mission criterion "An operator can register, edit, and remove connector accounts ... through an Admin surface that follows the existing design language" is satisfied for Flight 2's scope.
- The mission criterion "The Admin connector-account surface ... meets the M04/M06 design-language quality bar without alignment-flight rework" is verifiable: the design-language pass is part of this leg, with a screenshot-review human-judgment gate at the end (per the flight's Adaptation Criteria).

### Relevant design decisions

- **"Create form's primary action is 'Create & Test'"** — drives the create-mode form: primary button is a two-step sequential action (POST to `/api/connector-accounts`, then POST to `/api/connector-accounts/{new_id}/test/connect`, then transition to edit-mode with the probe banner rendered inline). Edit-mode Save + Test Connection buttons remain separate. Button label states: "Create & Test" → "Creating…" → "Testing…" during the flow.
- **"Doctor-probe response shape: `{status, message, details}` rendered as banner + labeled k/v block"** — drives the Test Connection banner: a status LED, the `message` as the LED-adjacent text, the `details` dict rendered as a labeled k/v block beneath with `data-testid="connector-test-details"`. Secret-shaped values (any value starting with `***`) pass through without double-masking; non-string values are JSON-stringified in `font-mono`; truncated long values use M04/M06's `text-muted` overflow ellipsis. **LED-class map (verified at design review against `static/css/components.css:861-895`)**: `ok → indicator-led--success`, `degraded → indicator-led--warning`, `failed → indicator-led--danger`, `error (route-wrapped) → indicator-led--danger`. **Note**: the project uses `--danger`, NOT `--error`, and `--warning` DOES exist — no fallback needed.
- **"Idle-TTL persist + wire through the pool"** — drives the Lifecycle section: a nullable `idle_timeout_seconds` number input with placeholder text "Use default (30 min)". Empty input → null payload → backend honors env-var / default. A design-comment in the section explains that Flight 3 will add a chat-session-lifecycle field next to this one (distinct labels to avoid operator confusion).
- **"Per-key `__MASKED__` semantics"** — drives the Credentials section's kv-editor: every secret value renders with `data-original-masked="true"` if it came from the GET response as masked; at save time, if the input's value equals its `data-original-masked`-stored original (i.e. the operator didn't edit it), submit `__MASKED__` for that key; else submit the new value.
- **"M04/M06 design-language quality bar without alignment-flight rework"** — the design-language pass is a first-class acceptance criterion. No new CSS classes unless a connector-specific need surfaces (and then namespaced `connector-account-*`). Reuse `page-header`, `entity-tile-grid`, `editor-section`, `field-input`, `kv-value-input`, etc.

### Key learnings from prior flights

- **`mcp-server-editor.js` is 1950 LoC** — the full MCP editor template. The connector editor is structurally simpler (no transport-specific config, no OAuth, no tools list, no sandbox section) and should land in ~800-1100 LoC.
- **MASKED_SENTINEL pattern at `mcp-server-editor.js:28`** — `var MASKED_SENTINEL = '__MASKED__';` declared at the top of the IIFE. The connector editor mirrors verbatim.
- **kv-editor pattern at `mcp-server-editor.js:819-821, 1607-1621`** — `data-original-masked` attribute round-trip is the canonical pattern. Use it for the secrets section.
- **F2 L3 backend `__MASKED__` resolution at `api.py:910-926`** — the backend honors the sentinel per-key. This leg's editor produces those sentinels for unchanged values; nothing further on the backend.
- **Leg 5 already ships `renderConnectorAccountsGrid` and the routing wiring** — this leg replaces only `connector-account-editor.js`. The studio.js section dispatch already calls `renderConnectorAccountEditor` with `(container, account, types, callbacks)`; the new editor consumes the same callback contract (`onBack`, `onCancel`, `onSaveSuccess`, `onDeleteSuccess`, `onDirtyChange`).

## Inputs

What exists before this leg runs:

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` (34 LoC placeholder from leg 5) — to be replaced wholesale.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` (1950 LoC) — the structural template.
- `the_one/interfaces/web/static/js/areas/studio.js` — already calls `renderConnectorAccountEditor` with the canonical callback contract.
- `tests/browser/test_flow_studio_connector_account_navigation.py` (7 tests from leg 5) — the navigation surface is already tested; this leg may augment with edit-mode navigation tests but does NOT duplicate.
- `tests/browser/test_flow_studio_mcp_editor.py` (1610 LoC, ~30 tests) — the editor browser-test template.
- `tests/browser/test_mcp_test_connection_button.py` (420 LoC) — the test-connection-button template.
- `tests/browser/seeders.py` — the seeders helpers; this leg adds `seed_connector_account(...)` if not present.
- REST endpoints from legs 3 + 4: GET/POST/PUT/DELETE `/api/connector-accounts`, GET `/api/connector-accounts/types`, POST `/api/connector-accounts/{account_id}/test/connect`.

## Outputs

What exists after this leg completes:

- **Replaced**: `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — the full editor. Estimated size 800-1100 LoC. Structure (parallel to MCP editor):
  - IIFE with `'use strict'`; `window.App.studio.renderConnectorAccountEditor = ...` at the end.
  - `MASKED_SENTINEL = '__MASKED__'` constant.
  - `renderConnectorAccountEditor(container, account, types, callbacks)` public entry.
  - **editor-header section**:
    - Title: `New Connector Account` (create) / account.name (edit).
    - Subtitle: type · idle_timeout_seconds-or-"default TTL" on edit mode; absent on create.
    - Action cluster: Back button (`data-testid="back-connector-account-btn"`), Cancel button (`data-testid="cancel-connector-account-btn"`, disabled until dirty), Save / "Create & Test" button (`data-testid="save-connector-account-btn"` or `data-testid="create-and-test-connector-account-btn"` per the create-mode spec).
    - Error display span.
  - **Connection section**:
    - Name input (`data-field="name"` `data-testid="connector-account-name-input"`).
    - Type select (`data-field="type"` `data-testid="connector-account-type-select"`). On create-mode: populated from `types` parameter (the leg-5 fetch); first option is a placeholder "Select a connector type" (disabled). On edit-mode: type is rendered as a read-only value (matches MCP's edit-time type immutability — changing type would invalidate config + secrets shape).
    - Config kv editor (`renderConfigKvEditor`) — generic key-value pairs, no per-type validation (deferred to Flights 8/9). Sensitive flag is always false here; config is plaintext per the F1 contract.
  - **Credentials section**:
    - Secrets kv editor (`renderSecretsKvEditor`) — generic kv with `data-original-masked` round-trip + `kv-value-secret` class for masked rendering. On edit-mode, populated from the masked GET response; values come in as `"***...tail4"` and the input renders the masked form via the `data-original-masked` attribute. On create-mode, the editor starts empty.
  - **Lifecycle section**:
    - `idle_timeout_seconds` input (number, `data-field="idle_timeout_seconds"` `data-testid="connector-account-idle-timeout-input"`, placeholder "Use default (30 min)"). Empty → null payload. Validator on save: range 1-604800.
    - Inline help text or design-comment-styled note explaining what the field does AND a forward-compat note: "Flight 3 will add a chat-session continuation window field here."
  - **Test Connection section** (edit-mode only; create-mode's "Create & Test" subsumes it):
    - Button `data-testid="connector-test-connection-btn"`.
    - Status banner `data-testid="connector-test-status"` — initially hidden; populated by POST to `/test/connect`. LED + message text + collapsible details k/v block.
    - Details block `data-testid="connector-test-details"` — labeled key/value rendering of `report.details`. Empty dict → "(no additional details)" placeholder. Secret-shaped values (any string starting with `***`) pass through without double-masking. Non-string values JSON-stringified in `font-mono`.
  - **Danger Zone section** (edit-mode only):
    - Delete button (`data-testid="delete-connector-account-btn"`) with confirm-dialog gate.
  - **Save/Update logic**:
    - On Save (edit-mode): POST `__MASKED__` for every unchanged secret value (per the `data-original-masked` round-trip), then PUT `/api/connector-accounts/{id}` with the full payload.
    - On "Create & Test" (create-mode): POST `/api/connector-accounts` with the form payload; on 201, immediately POST `/api/connector-accounts/{new_id}/test/connect` with no body; render the result inline; transition the UI to edit-mode (callbacks.onSaveSuccess(updated, true)). If create returns 422, surface the error; do NOT fire the probe. If create succeeds but probe fails, the account is persisted; the UI lands in edit-mode with the failure banner.
    - On Delete (edit-mode): confirm-dialog → DELETE `/api/connector-accounts/{id}` → callbacks.onDeleteSuccess().
    - On Cancel (create-mode): callbacks.onCancel() — clears form-mode, navigates back to grid.
    - On Back: callbacks.onBack(); if dirty, prompt-via-confirmDialog.
    - On any input change: dirty=true; enable Cancel + Save buttons; callbacks.onDirtyChange(true).
- **Updated**: `tests/browser/seeders.py` — add `seed_connector_account(client, name, type='stub', secrets=None, config=None, idle_timeout_seconds=None)` helper that wraps a POST to `/api/connector-accounts` and returns the created id. Idempotent on duplicate name (allow duplicates per the API — `name` has no uniqueness constraint). Mirror of any existing seeders.
- **New file**: `tests/browser/test_flow_studio_connector_account_editor.py` (~400 LoC, ~12 tests parallel to `test_flow_studio_mcp_editor.py`). Coverage:
  1. Create form renders all sections (header, Connection name+type, Credentials, Lifecycle, "Create & Test" button — no Test Connection / Danger Zone in create-mode).
  2. Edit form renders all sections including Test Connection + Danger Zone.
  3. Type select on create populates from `/api/connector-accounts/types`.
  4. Name + type + first secret + idle_timeout → "Create & Test" → both calls fire → list shows new tile → URL transitions to `#studio/connector-accounts/{new_id}`.
  5. Edit existing account → masked secret value renders as `***...tail4` → save without changing → backend preserves stored value (round-trip via GET assertion).
  6. Edit existing account → change name only → save → list reflects new name → secret still preserved.
  7. Edit existing account → change a secret → save → backend stores new value (verifiable via masked tail in re-GET).
  8. Edit existing account → idle_timeout_seconds input → set 60 → save → backend persists.
  9. Edit existing account → idle_timeout_seconds input → clear → save → backend persists null.
  10. Edit existing account → idle_timeout_seconds 0 → save → validation error surfaces (422 from backend; UI shows error inline).
  11. Edit existing account → Delete → confirm → tile gone from grid.
  12. Edit form's Back button when dirty → confirm dialog appears; cancel keeps editor; confirm leaves.
- **New file**: `tests/browser/test_connector_test_connection_button.py` (~250 LoC, ~6 tests parallel to `test_mcp_test_connection_button.py`). Coverage:
  1. Test Connection button visible in edit-mode only (not in create-mode).
  2. Click → POST `/test/connect` → status banner appears with LED + message.
  3. Stub plugin's default doctor response (`status="ok", message="stub probe ok", details={}`) renders as green LED + message + "(no additional details)" placeholder.
  4. Configured failure response (`status="failed"`, details with multiple keys) renders as red LED + message + labeled k/v block of details.
  5. `details` with a non-string value (e.g. `{"count": 42}`) renders as `font-mono` JSON-stringified.
  6. `details` with a secret-shaped value (e.g. `{"masked_token": "***...abc1"}`) passes through without double-masking.
- **New file**: `tests/browser/test_flow_studio_connector_account_create_and_test.py` (~200 LoC, ~3 tests parallel to the combined-action coverage from the flight spec):
  1. Create succeeds + probe succeeds → operator lands in edit-mode with green LED banner; the new account tile is visible in the grid (assertable via back-to-grid navigation).
  2. Create succeeds + probe fails (`StubPlugin.doctor_response = DoctorReport(status="failed", ...)`) → operator lands in edit-mode with red LED banner; account is persisted (verifiable by clicking through and seeing it in the grid).
  3. Create fails with 422 (deliberately invalid payload, e.g. missing required field) → operator stays on create form with error surfaced; the probe call is NOT fired (assertable via the test client's network log: `0 == count_of("/test/connect")`).
- **Updated**: `tests/browser/test_flow_studio_connector_account_navigation.py` — leg 5 shipped a `connector-account-editor-placeholder` selector. Update tests 4 and 7 (which currently assert the placeholder selector) to use the new editor's actual selectors (e.g. `connector-account-name-input`, `cancel-connector-account-btn`). Two tests touched; the leg-5 spec called this out implicitly when describing the placeholder as throwaway.
- **No new CSS classes** unless a genuinely connector-specific need surfaces. If one does, namespace `connector-account-*` and document why in the flight log.
- Flight log "Leg Progress" entry + final design-language screenshot-review note (the human-judgment gate per the flight's Adaptation Criteria).
- Flight artifact's leg-6 checkbox ticked. Flight status → `landed` if this is the last leg (it is).

## Acceptance Criteria

- [ ] `connector-account-editor.js` replaces the leg-5 placeholder with the full editor (~800-1100 LoC).
- [ ] All six sections render correctly in create-mode (without Test Connection or Danger Zone) and in edit-mode (with all sections).
- [ ] Type select on create populates from `/api/connector-accounts/types`; production-empty case renders a disabled "no connector types registered yet" option (consistent with the grid's empty-canvas copy).
- [ ] Masked-secret round-trip works: editing an account without touching its secrets submits `__MASKED__` for every untouched secret value; backend preserves stored values; re-GET returns the same masked tail.
- [ ] `idle_timeout_seconds` input round-trips correctly: empty → null; integer in range → that value; out-of-range → validation error surfaced.
- [ ] "Create & Test" combined-action button on create-mode fires POST `/api/connector-accounts`, then POST `/test/connect`, then transitions to edit-mode with the probe banner inline. Loading copy: "Creating…" then "Testing…".
- [ ] On create+probe failure, the account is persisted and the operator lands in edit-mode with the failure banner.
- [ ] On create-422, the probe is NOT fired (verifiable via test network log).
- [ ] Test Connection banner renders LED + message + labeled k/v details block with `data-testid="connector-test-details"`.
- [ ] All 4 DoctorReport status values (ok / degraded / failed / route-wrapped error) map to correct LED colors (green / amber / red / red).
- [ ] Secret-shaped values in `details` pass through without double-masking.
- [ ] Delete button in Danger Zone uses confirm-dialog gate; confirmed delete fires DELETE; tile disappears from grid.
- [ ] All 12 editor flow tests pass.
- [ ] All 6 test-connection button tests pass.
- [ ] All 3 create-and-test combined-action tests pass.
- [ ] Leg-5 navigation tests (4 and 7) updated to use the real editor selectors and pass.
- [ ] `seed_connector_account` helper exists in `tests/browser/seeders.py`.
- [ ] M04/M06 design tokens applied throughout (no new CSS classes unless a connector-specific need surfaces, in which case namespaced).
- [ ] `make test` clean (no unit regressions); `make test-browser` clean (delta: +21-23 tests on the leg-5 browser baseline).
- [ ] `make lint` clean.
- [ ] **Design-language screenshots captured + filed** (soft post-leg deliverable, NOT a hard auto-verifiable gate): the implementer captures screenshots of the create form, the edit form, and the Test Connection banner (success + failure), files them under `tests/browser/__snapshots__/connector-account-editor/` (gitignored), and notes the location in the flight log. The human reviewer makes the go/no-go call at flight-review time. The implementer's checklist passes when the screenshots are filed and the location is noted — not when the design is judged.

## Verification Steps

How to confirm each criterion:

- `ls -la the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — file size has grown substantially (from ~1KB to ~30-40KB).
- `grep -n "MASKED_SENTINEL\|data-original-masked\|connector-test-status\|connector-test-details" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — every expected anchor present.
- `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_*.py tests/browser/test_connector_test_connection_button.py` — all new tests green.
- `make test-browser` — full browser recipe clean (no regressions on the 323-test baseline).
- `make test` — full unit suite clean.
- `make lint` — clean.
- Screenshots taken + reviewed.

## Implementation Guidance

1. **Read the MCP editor in full first** — `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` is the canonical template. Read through it once to internalize the patterns (MASKED_SENTINEL hoisting, the kv-editor functions, the dirty-state machinery, the form-submit pipeline, the test-connection button handler, the delete confirm gate). Then write the connector editor as a structural mirror minus the MCP-specific bits.

2. **Replace `connector-account-editor.js` with the full editor**
   - Wholesale replacement of the placeholder. Keep the IIFE wrapper + `'use strict'` + `window.App.studio` namespace setup; replace the body.
   - Constants at top: `MASKED_SENTINEL = '__MASKED__';`. Any other small constants (max length, etc.) — mirror MCP's pattern.
   - Helper functions (file-local, NOT exported): kv-editor renderers, validation helpers, error-surfacing helpers. Mirror MCP's structure.
   - **Sections that MCP has but the connector editor SHOULD NOT include**:
     - Sandbox section (stdio-only; no connector equivalent).
     - Tools-list section (MCP-specific).
     - Refresh-connection / Reset-connection buttons (MCP-specific; the connector Test Connection button is simpler — just a probe).
     - OAuth state UI (no OAuth for connectors in Flight 2).
   - **Sections that the connector editor adds beyond MCP**:
     - Lifecycle section (idle_timeout_seconds input + forward-compat note).
     - Test Connection details rendering (the labeled k/v block with `data-testid="connector-test-details"`).
   - **"Create & Test" combined-action** lives in the save-button handler. On create-mode form submit:
     ```javascript
     // Pseudo-code
     async function handleCreateAndTest() {
       setSaveBtnLabel("Creating…");
       const createResp = await fetch("/api/connector-accounts", { method: "POST", body: JSON.stringify(payload) });
       if (!createResp.ok) { surfaceError(await createResp.json()); return; }
       const newAccount = await createResp.json();
       setSaveBtnLabel("Testing…");
       const probeResp = await fetch(`/api/connector-accounts/${newAccount.id}/test/connect`, { method: "POST" });
       const probeData = await probeResp.json();
       renderTestConnectionBanner(probeData); // inline render in the soon-to-be-edit-mode editor
       callbacks.onSaveSuccess(newAccount, true); // isCreate=true → studio.js transitions to edit-mode for newAccount.id
       // After studio.js re-renders the editor in edit-mode, the banner is preserved if we render it AFTER the re-render
       // — alternatively, store the probe result on a closure-local and inject during the next render.
     }
     ```
   - **Test Connection banner renderer** is a separate helper used by both the create-and-test flow AND the edit-mode Test Connection button. Both code paths converge on `renderTestConnectionBanner(report)`.
   - **Details k/v block renderer**:
     ```javascript
     function renderDetailsBlock(details) {
       if (!details || Object.keys(details).length === 0) {
         return '<div class="connector-test-details-empty" data-testid="connector-test-details">' +
                '<em>No additional details</em></div>';
       }
       var html = '<dl class="connector-test-details kv-display" data-testid="connector-test-details">';
       for (var key of Object.keys(details)) {
         var value = details[key];
         var renderedValue;
         if (typeof value === 'string') {
           if (value.indexOf('***') === 0) {
             renderedValue = '<span>' + escapeHtml(value) + '</span>';  // pass-through; no double-mask
           } else {
             renderedValue = '<span>' + escapeHtml(value) + '</span>';
           }
         } else {
           renderedValue = '<code class="font-mono">' + escapeHtml(JSON.stringify(value)) + '</code>';
         }
         html += '<dt>' + escapeHtml(key) + '</dt><dd>' + renderedValue + '</dd>';
       }
       html += '</dl>';
       return html;
     }
     ```
   - **LED color map** (verified live in `static/css/components.css:861-895`): `ok` → `indicator-led--success`; `degraded` → `indicator-led--warning`; `failed` → `indicator-led--danger`; `error` (route-wrapped) → `indicator-led--danger`. The project uses `--danger` (NOT `--error`); `--warning` DOES exist — no fallback / Flight-10 TODO needed.

3. **Update `tests/browser/seeders.py`**
   - **Verified at design review**: `tests/browser/seeders.py` contains three seeders (`seed_mock_provider`, `seed_mock_agent`, `seed_tool_config`). NO MCP seeder exists in this file — MCP source seeding is done inline in `tests/browser/test_mcp_test_connection_button.py` via a local `_seed_mcp_source` helper. The connector seeder can land EITHER in `seeders.py` (for cross-file reuse, the leg's preference) OR as an inline helper in each test file (mirroring the MCP precedent). Pick `seeders.py` for consistency with the existing pattern in the file.
   - Mirror **`seed_mock_provider`'s signature** (verified live): `def seed_connector_account(base_url: str, name: str = "Test Account", type: str = "stub", secrets: dict | None = None, config: dict | None = None, idle_timeout_seconds: int | None = None) -> str:`. Body uses `httpx.post(f"{base_url}/api/connector-accounts", json=payload)`; asserts `r.status_code == 201`; returns `r.json()["id"]`.
   - Document the helper's expected fixture setup: tests using this seeder must run against a server where the stub plugin is registered. The browser-test framework's server is spawned with the production `register_builtin_connectors()` (empty); to use the stub, the test must POST to a test-only registration endpoint OR run in a mode that pre-registers it. **Audit point**: verify how `tests/browser/test_mcp_test_connection_button.py` ensures the stub-equivalent is registered for browser-side tests. If no such test-mode toggle exists, this leg ALSO needs to add a way to register the stub plugin in the browser-test server — likely an env-var or a CLI flag the conftest sets. Investigate before writing tests.

4. **Create the three new browser test files**
   - `test_flow_studio_connector_account_editor.py` (~12 tests) — model after `test_flow_studio_mcp_editor.py`. Each test uses `app_clean + page` fixtures + the seeders.
   - `test_connector_test_connection_button.py` (~6 tests) — model after `test_mcp_test_connection_button.py`. Several tests need to override `StubPlugin.doctor_response` BEFORE the page navigates; the F2 L3 `_isolation` fixture pattern doesn't apply to browser tests, so use the browser-test framework's seeding mechanism (likely an HTTP-level helper that mutates the running server's state via `/api/...` if such an endpoint exists, OR via a test-only side channel like `pytest.fixture` that sets a module-scoped flag the running server reads). **Investigate the existing MCP test-connection button tests to see how they configure the doctor response side**; replicate the pattern.
   - `test_flow_studio_connector_account_create_and_test.py` (~3 tests) — model after the leg-3 backend test `test_db_api.py::TestConnectorAccountAPI` create+probe combined-flow but at the browser layer.

5. **Update the leg-5 navigation tests**
   - Tests 4 and 7 in `test_flow_studio_connector_account_navigation.py` reference `connector-account-editor-placeholder`. Update to use:
     - Test 4: assert the real editor mounts (e.g. `connector-account-name-input` is visible).
     - Test 7: assert the Cancel button works (`cancel-connector-account-btn` is now the real editor's button, not the placeholder's).

6. **Design-language audit**
   - Inspect every CSS class used by the new editor. Confirm each is M04/M06-canonical (no invented classes).
   - Capture screenshots of: create form (empty), create form (filled), create-and-test in flight (loading state), create+probe success, create+probe failure, edit form, edit form with masked secrets, Test Connection banner success, Test Connection banner failure, Danger Zone delete confirm.
   - Save under `tests/browser/__snapshots__/connector-account-editor/` (gitignored). These are LOCAL artifacts only.

7. **Run scoped tests, browser recipe, full suite**
   - `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_*.py tests/browser/test_connector_test_connection_button.py` — all new tests green.
   - `make test-browser` — full browser recipe green (expected delta: +21-23 tests on leg-5 baseline).
   - `make test` — full unit suite green (no regression on the 1805 baseline).
   - `make lint` — clean.

8. **Update artifacts and flight log**
   - Set this leg's status to `landed`.
   - Append a "Leg Progress" entry summarizing: full editor file, three new browser test files, leg-5 navigation test updates, seeders extension, design-language screenshot review.
   - **Set FLIGHT status to `landed`** (this is the last leg of the flight).
   - **Check off the flight in the mission's flights list** (`missions/10-bi-directional-comms-connectors/mission.md` Flights section).
   - Check off leg 6 in `flight.md`.
   - **Do NOT commit yet** — the post-flight review and commit handle this.

## Edge Cases

- **MCP editor is 1950 LoC; connector editor should be ~800-1100 LoC** — if your implementation crosses 1500, you're carrying MCP-specific patterns that don't apply. Step back and audit.
- **`StubPlugin.doctor_response` cannot be set from browser tests — use `page.route()` mocking instead.** Verified at design review: `tests/browser/conftest.py:112-178` confirms `app_clean` spawns a uvicorn SUBPROCESS, so setting `StubPlugin.doctor_response` from test-process Python won't reach the server. The canonical browser-side pattern (used at `tests/browser/test_mcp_test_connection_button.py:216-405` in ~5 tests) is **Playwright `page.route()`** to intercept `/api/connector-accounts/{id}/test/connect` and `route.fulfill(body=json.dumps(stub_payload), content_type="application/json")`. The default-stub-`ok` test (#3 of the connection-button file) is the only one that should hit the real stub plugin's `doctor` method; all configured-response tests (failure, degraded, secret-shaped details, non-string details) use `page.route()` to fulfill with a hand-crafted JSON payload.
- **`indicator-led--warning` DOES exist** — verified at design review (`static/css/components.css:861-895`); use it for `degraded`. The class names are `--success`, `--warning`, `--danger`, `--idle` (no `--error`). Drop any draft code that uses `--error`.
- **Network-log assertions** — test 3 in `test_flow_studio_connector_account_create_and_test.py` asserts the probe is NOT fired on create-422. Use Playwright's `page.on("request", ...)` to capture requests; assert the count of `/test/connect` requests is 0.
- **`onSaveSuccess(updated, true)` UNMOUNTS the previous editor** — verified at design review (`static/js/areas/studio.js:670-738` for the connector-accounts dispatch; mirror of MCP's :485-531). The fresh editor mounted in edit-mode loses any DOM/closure state from the create-form editor. The leg's "render banner BEFORE calling onSaveSuccess" pseudo-code drops the banner immediately. **The canonical mitigation pattern (mirrored from MCP's auto-run-after-create at `studio.js:530`)** is module-level state: declare `var _pendingProbeReport = null;` at the top of `connector-account-editor.js` IIFE; the create-and-test handler sets it BEFORE calling `callbacks.onSaveSuccess(...)`; the editor's render-edit-mode path checks it and, if non-null, renders the banner immediately + clears the var. This pattern is the cleanest — no callback contract change to studio.js, no DOM rescue. Implementation skeleton:
  ```javascript
  // Module-level, inside the IIFE:
  var _pendingProbeReport = null;
  
  // Inside the create-and-test handler, AFTER the probe POST completes:
  _pendingProbeReport = probeData;  // BEFORE onSaveSuccess
  callbacks.onSaveSuccess(newAccount, true);
  // studio.js unmounts this editor and mounts a fresh one in edit-mode.
  
  // Inside renderConnectorAccountEditor, BEFORE returning:
  if (!isCreate && _pendingProbeReport) {
    renderTestConnectionBanner(_pendingProbeReport);
    _pendingProbeReport = null;  // one-shot
  }
  ```
  This is the only viable path without touching the studio.js callback contract.
- **Lifecycle section forward-compat note** — the note explains a future field. Don't over-design — a short inline `<small class="text-muted">` is sufficient. Avoid placeholder UI for the unborn field.
- **Empty `details` dict** — surface "(no additional details)" rather than rendering an empty `<dl>`. The stub's default doctor returns `details={}`, so this is the common-case rendering.
- **`idle_timeout_seconds=0` validation** — the backend Pydantic validator rejects 0 (per F2 L2). The frontend SHOULD also validate before submit (set a `min=1` attribute on the number input) for instant feedback, but ALSO surface the backend's 422 error if it slips through.
- **Test isolation for the new browser tests** — verified at design review: `tests/browser/conftest.py:112-178` confirms `app_clean` spawns a fresh uvicorn subprocess per test → clean DB AND clean in-process connector pool AND clean registry per test. No cross-test pollution concern.
- **`idle_timeout_seconds=0` validation path — server-side 422 is canonical**. Do NOT add a frontend `min=1` HTML constraint; let the form submit reach the backend, and surface the Pydantic 422 error inline. This keeps the validation source-of-truth single (backend) and tests assert the exact path operators experience. The test at #10 of the editor file asserts exactly this path.
- **Probe-failure dirty state — operator lands in edit-mode with dirty=false**. The account WAS saved (Create succeeded); subsequent dirty-tracking applies to post-save edits. The failure banner is a state observation, not a dirty-state trigger. Cancel button on entry to edit-mode is disabled.
- **Existing MCP editor as a code-quality reference** — when something in the connector editor feels "wrong" relative to the MCP editor, lean toward mirroring MCP unless the divergence is documented in the leg artifact. The MCP editor has been through multiple iterations and shipped patterns are likely the right call.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — wholesale replacement (~800-1100 LoC).
- `tests/browser/seeders.py` — add `seed_connector_account` helper (~30 LoC).
- `tests/browser/test_flow_studio_connector_account_editor.py` — new file (~400 LoC, ~12 tests).
- `tests/browser/test_connector_test_connection_button.py` — new file (~250 LoC, ~6 tests).
- `tests/browser/test_flow_studio_connector_account_create_and_test.py` — new file (~200 LoC, ~3 tests).
- `tests/browser/test_flow_studio_connector_account_navigation.py` — update tests 4 and 7 (~10 LoC net).
- `missions/10-bi-directional-comms-connectors/flights/02-admin-surface-for-connector-accounts/flight-log.md` — Leg Progress entry + design-language screenshot review note.
- `missions/10-bi-directional-comms-connectors/flights/02-admin-surface-for-connector-accounts/flight.md` — leg-6 checkbox + status: `in-flight` → `landed`.
- `missions/10-bi-directional-comms-connectors/mission.md` — Flight 2 checkbox ticked.

## State-Machine Reachability Audit

The editor introduces no new persisted state or lifecycle values; all state shape is consumed from the existing REST surface (legs 3 + 4).

UI state machine for the create-and-test flow:
- `idle → submitting (Create) → success | failed`
- On Create success: `submitting (Test) → success | failed | error-wrapped`
- On Test resolution: `displaying-banner`; user-driven transitions can move back to `idle` via dirty input or Cancel/Back navigation.

Failure modes covered:
- Create 422: stay on create form, surface error inline. Probe NOT fired.
- Create 5xx: stay on create form, surface error inline. Probe NOT fired.
- Create success + Probe success: transition to edit-mode, render green banner.
- Create success + Probe failure: transition to edit-mode, render red banner. Account is persisted.
- Create success + Probe network error (5xx, timeout): transition to edit-mode, render an "error" banner with the network failure reason.

## Cache Freshness Contract

For the editor's local form state:

- **Source of truth**: the operator's typing + the original GET response.
- **Rebuild trigger**: editor mount fires GET (via studio.js's `findConnectorAccount` cache lookup or via direct fetch for direct-load); the editor renders from the response.
- **Maximum staleness**: until the operator submits Save (which re-fetches via the response of PUT) or navigates away and back.
- **User-action invalidation map**:
  - Save → PUT → response carries the updated form → editor re-renders from the response → form is in-sync.
  - Type change on create → no cache invalidation needed (type is form-local until create).
  - Delete → editor unmounts; no further cache concern.
  - Test Connection → no cache invalidation; the probe is read-only.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `make test` clean (no unit regressions on 1805 baseline)
- [ ] `make test-browser` clean (delta: +21-23 tests on leg-5 baseline)
- [ ] `make lint` clean
- [ ] Design-language screenshot review captured + filed under `tests/browser/__snapshots__/connector-account-editor/`
- [ ] Flight log updated with a "Leg Progress" entry + screenshot review note
- [ ] This leg's status updated to `landed`
- [ ] FLIGHT status updated to `landed` in `flight.md`
- [ ] Flight 2 checked off in the mission artifact
- [ ] Do NOT commit — review and commit happen once at the end of the flight per `/agentic-workflow`

---

## Citation Audit

7 code-location citations verified against current code at leg design time:

- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:1950 LoC` — **OK** (the structural template).
- `mcp-server-editor.js:28 — MASKED_SENTINEL constant` — **OK** (verified).
- `mcp-server-editor.js:819-821, 1607-1621 — data-original-masked round-trip` — **OK** (verified).
- `mcp-server-editor.js:406-438 — renderMcpSourceEditor + editor-header` — **OK** (verified).
- `tests/browser/test_flow_studio_mcp_editor.py:1610 LoC` — **OK** (the editor browser-test template).
- `tests/browser/test_mcp_test_connection_button.py:420 LoC` — **OK** (the test-connection button template).
- `tests/browser/test_flow_studio_connector_account_navigation.py:7 tests from leg 5` — **OK** (verified; tests 4 and 7 reference the placeholder selector).

0 citations drifted, 0 unverifiable.
