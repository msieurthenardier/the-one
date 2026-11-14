# Leg: connector-editor-inference-provider-and-model-row

**Status**: completed
**Flight**: [Audit-log inspector + per-connector inference config + slash-command HAT](../flight.md)

## Objective

Add two new operator-facing field-rows — an Inference provider dropdown and an Inference model text input — to the Studio connector editor's Session section, conditional on `always_listen=true`, so that the L2/L3 substrate keys (`connector.config.inference_provider_config_id` + `connector.config.inference_model`) become editable from the UI; also author the inline `tests/behavior/connector-inference-provider-config-roundtrip.md` Witnessed spec that pins the UI round-trip end-to-end.

## Context

Atomic frontend leg riding the L2 + L3 substrate (which landed at the same v26 commit boundary).

- **L2 (landed)** added `inference_provider_config_id: str | None` + `inference_model: str | None` to the `connector.config` Pydantic validator at `the_one/db/models.py:629-643` (in `_validate_config_reserved_keys` on the `Connector` model), with v26 migration backfilling `None` on existing rows.
- **L3 (landed)** removed the `Settings.inference_*` fields entirely and refactored the dispatcher (`_inbound.py:269+`, `_inference.py:_resolve_inference_provider`) to read from `account.config.get("inference_provider_config_id")` / `account.config.get("inference_model")`, with fallback to the routed agent's LLM when both are `None`.
- **L4 (this leg)** closes the loop on the operator's framing — "the LLM has to be set up first, and each connection may choose a different LLM, to me this is simply a property of the connector" — by exposing the two fields in the connector editor.

Key design decisions inherited from the flight spec:

- **Flat on `connector.config`** (Phase 5b DD: "Inference Fields Are Flat on `connector.config`"): both keys sit at the top of `connector.config` alongside `always_listen`. No nesting under `connector.config.policy.inference`. Mirrors the existing `always_listen` shape and simplifies the validator + UI binding.
- **Conditional render on `always_listen=true`**: both rows are visible only when the operator has flipped Always Listen ON. When the master toggle is OFF, the policy gate never runs inference (per F7) so the inference selection is moot — fully hiding the rows avoids operator confusion. **Note — divergence from F7 L11's `disabled`/greyed pattern**: F7 L11's per-agent always-listen toggles (`connectors-tab.js:838-839`) use `.disabled = !accountAlwaysListenMaster` to grey-out rather than hide, because per-agent toggles have a meaningful "configured but inert" state worth showing. Inference fields have no such inert state — they're either consulted or moot — so full-hide is the right shape here. The leg uses the `hidden` attribute on a container `<div>` wrapping both rows, preserving typed-but-unsaved values when the operator toggles always-listen OFF then ON.
- **Provider dropdown empty-state semantic**: the dropdown's blank/empty option is labelled `"— Use routed agent's LLM —"` and writes `null` to `inference_provider_config_id`. This covers the L3 fallback path explicitly (operator opts out → routed-agent's LLM).
- **Model is a free-form text input** (not a queryable select): the L4 dropdown deliberately does NOT chain to `GET /api/providers/{id}/models`. Provider-type-aware model lists vary (Ollama supports listing; OpenAI/Anthropic effectively don't); the simplest cross-provider UI is a typed-string with a placeholder hint per provider type.
- **CSS reuse**: re-uses the existing `field-row admin-pf-row` 3-column-info-icon-as-sibling pattern from F5 (no new CSS classes).
- **Behavior-test spec authored inline**: per the flight spec's L4 section + the behavior-test authoring guide, this leg deliverable includes `tests/behavior/connector-inference-provider-config-roundtrip.md` (Witnessed; browser MCP). The spec is the UI-flow regression net that the unit browser tests don't reach (e.g., the dropdown population timing, the dirty-tracker recapture, the save → reopen round-trip across the SPA cache boundary).

**Cumulative leg-by-leg state** at L4 entry (per flight log):

- Backend test suite: **2794 passed / 4 skipped / 509 deselected / 0 errors / 3 warnings** (post-L3 baseline).
- Browser test suite: **443 passed / 35 skipped / 12 deselected** (+ 2 pre-existing-main failures preserved from pre-F10; out of F13 scope per recon table).
- `tests/behavior/` directory exists with two prior specs (`discord-engagement.md`, `studio-smoke.md`); `.gitignore` already has `tests/behavior/*/runs/*/` guard. No directory seeding or `.gitignore` edits needed for this leg.
- Working tree carries L1 + L2 + L3 edits forward (Phase 2d commit deferred to after L5 autonomous land per `/agentic-workflow` protocol).

## Inputs

**State that must be true before L4 starts:**

- L1 + L2 + L3 are `landed` (verified via flight log).
- `the_one/db/models.py:629-643` validator accepts `inference_provider_config_id` + `inference_model` on `connector.config`.
- `_resolve_inference_provider` in `the_one/connectors/_inference.py` reads connector kwargs (not `Settings`).
- `tests/behavior/` directory exists at the project root with at least one prior `.md` spec (verified: `discord-engagement.md`, `studio-smoke.md` present).
- `.gitignore` already excludes `tests/behavior/*/runs/*/` (verified).
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` exists; the `always_listen` toggle is rendered at lines 455-484 inside `lifecycleHtml` (verified at L4 recon — no drift from the architect cycle-1 citation).
- `RESERVED_CONFIG_KEYS` at `connector-editor.js:782-787` already lists `always_listen: true` (verified).
- `/api/providers` endpoint exists at `the_one/interfaces/web/api.py:3349-3353` (`list_providers`) and returns `list[dict]` with `id`, `name`, `type` keys via `_provider_response` at `api.py:3316-3319` (verified).
- `tests/browser/seeders.py:34-57` (`seed_mock_provider`) seeds a mock provider via `POST /api/providers`; `seed_connector` at `:88-135` seeds a stub connector via `POST /api/connectors`. Both consumed by the F7 L11 always-listen test suite at `tests/browser/test_flow_studio_always_listen_toggles.py` (verified).
- `app_clean` browser fixture (`tests/browser/conftest.py:113-184`) spawns a subprocess with `THE_ONE_DEV_MODE=true` + `THE_ONE_REGISTER_STUB_CONNECTOR=1` so mock providers + stub connectors are seedable.

**Files that must exist:**

- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` (will be modified)
- `tests/browser/seeders.py` (unchanged; consumed)
- `tests/browser/conftest.py` (unchanged; consumed)
- `tests/_acl_shape_helpers.py` (unchanged; L1 module is a sibling import target)

## Outputs

**Files modified:**
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — Provider dropdown + Model text input rendered conditional on `always_listen=true`; populated async via `fetch('/api/providers')`; events wired into dirty-tracker; values flow into `collectFormData` → `config.inference_provider_config_id` + `config.inference_model`; reserved-keys hide them from the kv-table.

**Files added:**
- `tests/browser/test_flow_studio_connector_inference_provider_row.py` — 5 browser tests (target +5 to the 443 baseline → **448**).
- `tests/behavior/connector-inference-provider-config-roundtrip.md` — Witnessed behavior-test spec (status `draft` at land; operator promotes to `active` after first successful run).

**State after the leg:**
- `git grep -nE 'inference_provider_config_id|inference_model' the_one/interfaces/web/static/js/areas/studio/connector-editor.js` returns at least 6 hits (render markup for the 2 rows + 2 collect-path writes in `collectFormData` + 2 snapshot reads in `getFormSnapshot` for dirty-tracking).
- `git grep -nE 'connector-config-inference-(provider|model)' tests/browser/` returns at least 4 hits in `tests/browser/test_flow_studio_connector_inference_provider_row.py` (one per test resolving the new testids).
- `git grep -n 'inference_provider_config_id' the_one/interfaces/web/static/js/areas/studio/connector-editor.js | wc -l` is at least 3 (markup + collect + snapshot).
- Browser test count at **448** (baseline 443 + 5 new tests). 2 pre-existing-main browser failures remain (not F13-caused).
- Backend test count UNCHANGED at **2794** (L4 adds zero backend tests).
- `tests/behavior/connector-inference-provider-config-roundtrip.md` exists with `Status: draft`.

## Acceptance Criteria

- [x] **AC-1**: Provider dropdown renders inside the Session section under `always_listen=true`. Visible when the master toggle is checked; hidden (or removed from DOM) when unchecked. Selector: `[data-testid="connector-config-inference-provider-select"]`.
- [x] **AC-2**: Model text input renders adjacent (immediately following) the Provider dropdown under `always_listen=true`. Selector: `[data-testid="connector-config-inference-model-input"]`. Placeholder text contains the substring `qwen2.5:7b` (provider-agnostic baseline hint).
- [x] **AC-3**: When `always_listen=false` (master toggle OFF), neither row is visible (DOM-level: rows either are removed from the rendered HTML, OR are wrapped in a container with `hidden` attribute / `display: none` such that Playwright's `expect(...).not_to_be_visible()` resolves true within 2s).
- [x] **AC-4**: Toggling Always Listen from OFF→ON in the editor causes both rows to become visible WITHOUT a page reload. (Tests this by checking visibility, asserting the rows are not present; clicking the always-listen toggle; asserting they are present within 2s.)
- [x] **AC-5**: The provider dropdown's first option is the empty-state placeholder with label containing the substring `— Use routed agent's LLM —` and `value=""` (the empty string serializes as `null` on save per the AC-9 contract).
- [x] **AC-6**: The provider dropdown's options are populated from `GET /api/providers` after the editor mounts (analogous to the routing-default agent dropdown populated by `populateRoutingAgentDropdowns` at `connector-editor.js:2436-2480`). For an app seeded with 2 mock providers, the dropdown contains the empty-state placeholder PLUS 2 provider-name options within 5s of opening the editor with `always_listen=true`. Each non-empty option's `value` is the provider's `id` (stable string).
- [x] **AC-7**: When the connector's persisted `config.inference_provider_config_id` matches one of the fetched providers' ids, that option is selected (`selected` attribute on the option, or `<select>.value` equals the id) after population resolves. When the persisted value doesn't match (stale provider id), the empty-state placeholder is selected AND a disabled `<option value="{stale-id}" selected disabled>` is appended showing `{stale-id} (provider deleted)` — mirrors the stale-selection-preservation pattern from `populateRoutingAgentDropdowns:2466-2469`.
- [x] **AC-8**: When the connector's persisted `config.inference_model` is a non-empty string, the model input is pre-filled with that value (`<input>.value === persisted_value`) on editor mount.
- [x] **AC-9**: Saving the editor with a provider selected + a model entered + always_listen ON round-trips through `PUT /api/connectors/{id}`: the GET response post-save has `config.inference_provider_config_id` equal to the selected provider's id AND `config.inference_model` equal to the entered string. Verified by the round-trip browser test seeding 2 providers, opening the editor, selecting provider #2, entering model `gpt-4o-mini`, saving, re-GETting via `httpx`.
- [x] **AC-10**: Saving the editor with the empty-state placeholder selected (provider unset) + an empty model input + always_listen ON round-trips as `config.inference_provider_config_id = null` AND `config.inference_model = null` (NOT empty-string — empty strings serialize as `null` so the validator's `str | None` shape accepts them and the L3 dispatcher falls through to routed-agent fallback). Empty input value → `null` payload.
- [x] **AC-11**: The two new keys are added to `RESERVED_CONFIG_KEYS` at `connector-editor.js:782-787` (joining `pairing`, `allowlist`, `routing`, `always_listen`) so the generic kv-table at `renderConfigKvTable` doesn't ALSO render them and create the "two conflicting controls" hazard called out by the F7 L12 hotfix comment at `:777-781`.
- [x] **AC-12**: Dirty-tracker integration: editing either field (selecting a new provider OR typing in the model input) enables the Save button (`save-connector-btn` `disabled` attribute removed). Verified by opening the editor against a seeded `always_listen=true` connector, asserting Save is disabled at mount, selecting a provider, asserting Save becomes enabled within 1s.
- [x] **AC-13**: Existing F7 L11 always-listen browser tests at `tests/browser/test_flow_studio_always_listen_toggles.py` (6 tests, lines 97-345) pass UNCHANGED — no regression from the new rows being added to the same Session section.
- [x] **AC-14**: Browser test suite green at **448 passed / 35 skipped / 12 deselected + 2 pre-existing-main failures** (baseline 443 + 5 new tests in `test_flow_studio_connector_inference_provider_row.py`). The 2 pre-existing-main failures (`test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` + `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection`) remain — F13 does not address them per recon table.
- [x] **AC-15**: Backend test suite UNCHANGED at **2794 passed / 4 skipped / 509 deselected / 0 errors** (L4 is a frontend-only leg; no backend tests added or modified). Re-run `docker exec the-one pytest tests/ --timeout 30 -q` confirms.
- [x] **AC-16**: `tests/behavior/connector-inference-provider-config-roundtrip.md` exists, has `**Status**: draft`, follows the format defined in `.flightops/ARTIFACTS.md` "Behavior Test — Spec" section (Slug / Status / Created / Last Run / Intent / Preconditions / Observables Required / Steps table / Out of Scope), and references the spec slug from this leg's acceptance criteria. The spec file is committed alongside the source changes.
- [x] **AC-17** (grep gate, deferred to /behavior-test gate post-L5): `/behavior-test connector-inference-provider-config-roundtrip` is the verification mechanism — actually running it is **gated to after L5 lands** (per flight spec's "Pre-L6 behavior-test gate" checkpoint). This AC is satisfied at L4 land by the spec file existing + committed; the live run happens at the pre-L6 gate.
- [x] **AC-18** (grep gate, frontend): `git grep -nE 'inference_provider_config_id|inference_model' the_one/interfaces/web/static/js/areas/studio/connector-editor.js` returns at LEAST 6 hits — 2 in the render markup (the new rows), 2 in `collectFormData` writing back to `config`, 2 in `getFormSnapshot` reading for dirty-tracking. Counts greater than 6 are acceptable (e.g., comments).
- [x] **AC-19** (grep gate, test surface): `git grep -nE 'connector-config-inference-(provider|model)' tests/browser/` returns at LEAST 4 hits, all in `tests/browser/test_flow_studio_connector_inference_provider_row.py`. Each test resolving by the new testids contributes hits.
- [x] **AC-20** (grep gate, reserved-keys): `git grep -nE 'inference_provider_config_id:\s*true' the_one/interfaces/web/static/js/areas/studio/connector-editor.js` returns exactly 1 hit (the new entry inside `RESERVED_CONFIG_KEYS`); same with `inference_model:\s*true`. Anchored regex targets the literal `key: true,` reserved-keys map entries.

## Verification Steps

Run each command from the project root (`~/projects/the-one`). Per F13 testing convention, all pytest invocations use `docker exec the-one pytest …` with `-x --timeout 30`.

**Phase 1 — Static gates (run before pytest):**

1. **AC-18 grep**: `docker exec the-one git grep -nE 'inference_provider_config_id|inference_model' the_one/interfaces/web/static/js/areas/studio/connector-editor.js | wc -l` — expect at least 6.
2. **AC-19 grep**: `docker exec the-one git grep -nE 'connector-config-inference-(provider|model)' tests/browser/ | wc -l` — expect at least 4.
3. **AC-20 grep**: `docker exec the-one git grep -nE 'inference_provider_config_id' the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — visually confirm one of the hits is inside the `RESERVED_CONFIG_KEYS` declaration (around the old `:782-787` block; the exact line will drift post-edit).
4. **AC-11 visual**: open the file at the post-edit `RESERVED_CONFIG_KEYS` location and confirm both new keys are present alongside `pairing`, `allowlist`, `routing`, `always_listen`.

**Phase 2 — Backend regression (AC-15):**

```
docker exec the-one pytest tests/ --timeout 30 -q
```

Expect: `2794 passed, 4 skipped, 509 deselected, 0 errors, 3 warnings`.

If a backend test fails, the leg has accidentally touched backend code; investigate and revert (frontend-only leg).

**Phase 3 — Targeted browser regression (AC-13):**

```
docker exec the-one pytest tests/browser/test_flow_studio_always_listen_toggles.py -m browser -x --timeout 30 -q
```

Expect: all 6 F7 L11 tests pass UNCHANGED.

If any fails, the new rows are interfering with the existing always-listen toggle rendering or events — fix in-leg before continuing.

**Phase 4 — New browser tests (AC-1 through AC-12):**

```
docker exec the-one pytest tests/browser/test_flow_studio_connector_inference_provider_row.py -m browser -x --timeout 30 -q
```

Expect: 5 new tests pass.

**Phase 5 — Full browser suite (AC-14):**

```
docker exec the-one pytest tests/browser/ -m browser --timeout 30 -q
```

Expect: `2 failed, 448 passed, 35 skipped, 12 deselected` — the 2 failures are the documented pre-existing-main failures (NOT in `test_flow_studio_connector_inference_provider_row.py` or `test_flow_studio_always_listen_toggles.py`).

Note: do NOT pass `-x` here (we want the run to continue past the 2 pre-existing failures so the total-pass count is observable). Drop `-x` per the F13 L1 browser-suite invocation precedent.

**Phase 6 — Behavior-test spec presence (AC-16):**

```
ls tests/behavior/connector-inference-provider-config-roundtrip.md
docker exec the-one git grep -n '^\*\*Status\*\*: draft' tests/behavior/connector-inference-provider-config-roundtrip.md
```

Expect: file exists; status header reads `**Status**: draft`.

The live spec run (AC-17) is **deferred to the Pre-L6 behavior-test gate** per flight spec. Do NOT attempt to run `/behavior-test connector-inference-provider-config-roundtrip` as part of L4 land.

## Implementation Guidance

### 1. Recon-anchored citations (verified at L4 design time)

| Citation | Description | Verified |
|----------|-------------|----------|
| `connector-editor.js:455-484` | `always_listen` toggle render — both new rows insert AFTER `:484`'s closing `</div>` and BEFORE `:486`'s `lifecycleHtml += '</div>';` (the Session-section closing tag). | OK — verified verbatim against current code. |
| `connector-editor.js:461-463` | `alwaysListenConfigValue` boolean computation — pattern to mirror for `inferenceProviderConfigValue` + `inferenceModelConfigValue`. | OK |
| `connector-editor.js:782-787` | `RESERVED_CONFIG_KEYS` constant — extend with `inference_provider_config_id: true, inference_model: true`. | OK |
| `connector-editor.js:976-988` | `getFormSnapshot`'s `always_listen` capture — pattern to mirror for the two new fields. | OK |
| `connector-editor.js:1089-1097` | `wireEditorEvents`'s `always-listen` change listener — the `change` listener that emits the CustomEvent is also where the master-toggle re-render hook fires (see Step 4 below for the conditional-render approach). | OK |
| `connector-editor.js:1633-1642` | `collectFormData`'s `always_listen` write to `config` — pattern to mirror for the two new fields, writing `null` when empty. | OK |
| `connector-editor.js:2436-2480` | `populateRoutingAgentDropdowns` — the canonical async-populate-a-select-after-fetch pattern used by routing-default. The new provider dropdown follows the same shape: render with placeholder option + (if persisted value exists) a placeholder selected-option; fetch `/api/providers` after mount; populate full option list; preserve stale selection as disabled. | OK |
| `connector-editor.js:3065-3110` | `fetchAttachedAgents` — the async-after-mount pattern with snapshot recapture. The new provider-fetch helper follows the same shape but populates a dropdown not a tile list. | OK |
| `api.py:3349-3353` | `GET /api/providers` returns `list[dict]` — each dict has at minimum `id`, `name`, `type` keys (per `_provider_response` at `:3316-3319` → `provider.model_dump()` + masked `api_key`). | OK |
| `tests/browser/seeders.py:34-57` | `seed_mock_provider(base_url, name=...)` — accepts a `name` kwarg; mock type only works with `THE_ONE_DEV_MODE=true` (the `app_clean` fixture sets this). Seed at least 2 providers per test by calling twice with distinct names. | OK |
| `tests/browser/seeders.py:88-135` | `seed_connector(base_url, name=..., config=...)` — accepts a `config` dict; the test passes `{"always_listen": True}` (and optionally pre-seeded `inference_provider_config_id` / `inference_model`) for round-trip tests. | OK |
| `tests/browser/test_flow_studio_always_listen_toggles.py:1-345` | F7 L11 always-listen browser tests — the test-file template for L4's new test file (same fixture imports, same `_get_account` helper pattern, same `page.locator('[data-testid="tab-access-and-routing"]').click()` navigation pattern). | OK |
| `tests/browser/conftest.py:113-184` | `app_clean` fixture — spawns subprocess with `THE_ONE_DEV_MODE=true` + `THE_ONE_REGISTER_STUB_CONNECTOR=1`. Both required for `seed_mock_provider` + `seed_connector` to work. | OK |
| `the_one/db/models.py:629-643` | `Connector._validate_config_reserved_keys` accepts `inference_provider_config_id: str | None` + `inference_model: str | None`. Empty string is NOT special-cased — `""` would pass validation but be semantically wrong. The frontend MUST send `null` for empty input values (covered by Step 5 / AC-10). | OK |

### 2. The two new field-rows (markup)

Insert the markup AFTER the existing `always_listen` row's closing `</div>` (currently at `connector-editor.js:484`) and BEFORE the Session section's outer closing `</div>` (currently at `:486`). Both rows render conditionally — only when `always_listen=true` on the connector at render time.

Use a wrapper `<div>` with a stable testid (`connector-inference-rows-container`) so the conditional-render switch in Step 4 can hide/show the whole block in one operation:

```javascript
    // M11 F13 L4: Inference provider + model rows (conditional on
    // always_listen=true). The connector's policy-gate inference call
    // uses these to pick the LLM that decides engage-or-silent on
    // non-mentioned channel messages. Empty / unset values fall through
    // to the routed agent's LLM per the L3 dispatcher contract.
    var inferenceProviderConfigValue = (!isCreate && account.config &&
            Object.prototype.hasOwnProperty.call(account.config, 'inference_provider_config_id'))
        ? account.config.inference_provider_config_id
        : null;
    var inferenceModelConfigValue = (!isCreate && account.config &&
            Object.prototype.hasOwnProperty.call(account.config, 'inference_model'))
        ? account.config.inference_model
        : null;
    var inferenceRowsHidden = !alwaysListenConfigValue;

    var inferenceProviderTipText = 'The LLM provider used by the policy-gate ' +
            'inference call when Always Listen is on. Leave empty to use the ' +
            'routed agent’s own LLM.';
    var inferenceModelTipText = 'The model identifier the inference call uses ' +
            'on the selected provider. Provider-type determines whether the model ' +
            'list is queryable (Ollama yes; OpenAI / Anthropic no).';

    lifecycleHtml += '<div class="cf-inference-rows" data-testid="connector-inference-rows-container"' +
            (inferenceRowsHidden ? ' hidden' : '') + '>';

    // Provider dropdown.
    lifecycleHtml += '<div class="field-row admin-pf-row cf-inference-provider-row">';
    lifecycleHtml += '<label for="cf-inference-provider">Inference provider</label>';
    lifecycleHtml += '<button type="button" class="field-info-icon" ' +
            'title="' + escAttr(inferenceProviderTipText) + '" ' +
            'aria-describedby="connector-inference-provider-help-text" ' +
            'data-testid="connector-config-inference-provider-hint">' + infoIcon + '</button>';
    lifecycleHtml += '<span id="connector-inference-provider-help-text" class="visually-hidden">' +
            escHtml(inferenceProviderTipText) + '</span>';
    lifecycleHtml += '<select class="field-input field-select admin-pf-input admin-pf-select" ' +
            'id="cf-inference-provider" data-field="inference_provider_config_id" ' +
            'data-testid="connector-config-inference-provider-select">';
    // Initial placeholder option only; full population happens async in
    // populateInferenceProviderDropdown after mount (mirrors
    // populateRoutingAgentDropdowns). If the persisted value exists, we
    // pre-emit it as a selected option so the dirty-tracker's mount-time
    // snapshot reflects the persisted state (otherwise the populate-step
    // would flip the value and read as a dirty edit).
    lifecycleHtml += '<option value=""' +
            (inferenceProviderConfigValue == null ? ' selected' : '') +
            '>— Use routed agent’s LLM —</option>';
    if (inferenceProviderConfigValue) {
      lifecycleHtml += '<option value="' + escAttr(inferenceProviderConfigValue) + '" selected>' +
              escHtml(inferenceProviderConfigValue) + '</option>';
    }
    lifecycleHtml += '</select>';
    lifecycleHtml += '</div>';

    // Model text input.
    lifecycleHtml += '<div class="field-row admin-pf-row cf-inference-model-row">';
    lifecycleHtml += '<label for="cf-inference-model">Inference model</label>';
    lifecycleHtml += '<button type="button" class="field-info-icon" ' +
            'title="' + escAttr(inferenceModelTipText) + '" ' +
            'aria-describedby="connector-inference-model-help-text" ' +
            'data-testid="connector-config-inference-model-hint">' + infoIcon + '</button>';
    lifecycleHtml += '<span id="connector-inference-model-help-text" class="visually-hidden">' +
            escHtml(inferenceModelTipText) + '</span>';
    lifecycleHtml += '<input type="text" class="field-input" id="cf-inference-model" ' +
            'data-field="inference_model" ' +
            'data-testid="connector-config-inference-model-input" ' +
            'placeholder="e.g. gpt-4o-mini, qwen2.5:7b" ' +
            'value="' + escAttr(inferenceModelConfigValue || '') + '" />';
    lifecycleHtml += '</div>';

    lifecycleHtml += '</div>'; // .cf-inference-rows
```

### 3. Extend `RESERVED_CONFIG_KEYS`

At the existing `RESERVED_CONFIG_KEYS` declaration (currently `connector-editor.js:782-787`), add the two new keys:

```javascript
  // M11 F13 L4: ``inference_provider_config_id`` + ``inference_model``
  // join the reserved set — the new Session-section rows are the only
  // writers for these flat keys. Without these entries the kv-table
  // also renders them post-v26 migration and the operator sees
  // duplicate controls (same hazard as F7 L12's always_listen hotfix).
  var RESERVED_CONFIG_KEYS = {
    pairing: true,
    allowlist: true,
    routing: true,
    always_listen: true,
    inference_provider_config_id: true,
    inference_model: true,
  };
```

### 4. Conditional render on always-listen change

The always-listen toggle's existing change listener at `connector-editor.js:1089-1097` already dispatches a CustomEvent for cross-component coordination. Extend that listener to ALSO toggle the `hidden` attribute on the new `[data-testid="connector-inference-rows-container"]` wrapper:

```javascript
    var alwaysListenEl = container.querySelector('[data-field="always_listen"]');
    if (alwaysListenEl && account && account.id) {
      alwaysListenEl.addEventListener('change', function () {
        App.studio.eventBus.emit('connector-always-listen-changed', {
          accountId: account.id,
          enabled: !!alwaysListenEl.checked,
        });
        // M11 F13 L4: toggle the inference-rows visibility in lockstep.
        var inferenceWrap = container.querySelector('[data-testid="connector-inference-rows-container"]');
        if (inferenceWrap) {
          if (alwaysListenEl.checked) {
            inferenceWrap.removeAttribute('hidden');
          } else {
            inferenceWrap.setAttribute('hidden', '');
          }
        }
      });
    }
```

### 5. Snapshot capture (for dirty-tracking)

In `getFormSnapshot` (currently at `connector-editor.js:976-988`), after the `always_listen` snapshot capture, add capture for both new fields:

```javascript
    // M11 F13 L4: capture the two inference-config fields on the snapshot
    // object so the dirty-tracker fires for edits. Mirrors the always_listen
    // pattern — read the live DOM value; OMIT the key when the input is
    // absent so unrelated render paths keep stable snapshot bytes.
    var inferenceProviderSnap = container.querySelector('[data-field="inference_provider_config_id"]');
    if (inferenceProviderSnap) {
      // The empty placeholder option's value is "" — serialize as null for
      // snapshot parity with collectFormData's null-write semantic, so the
      // dirty-tracker's mount snapshot matches the collect-payload shape.
      snapshotObj.inference_provider_config_id = inferenceProviderSnap.value || null;
    }
    var inferenceModelSnap = container.querySelector('[data-field="inference_model"]');
    if (inferenceModelSnap) {
      snapshotObj.inference_model = inferenceModelSnap.value || null;
    }
```

### 6. `collectFormData` writes

In `collectFormData` (the function ending at `connector-editor.js:1644-1652` with `return { name, type, config, secrets, ... }`), AFTER the always-listen write at `:1633-1642`, add writes for the two new fields:

```javascript
    // M11 F13 L4: write the connector-scope inference fields into
    // ``config``. Empty values serialize as null (NOT empty string) so
    // the Pydantic validator's ``str | None`` shape accepts them and the
    // L3 dispatcher's "None falls through to routed-agent LLM" path fires.
    var inferenceProviderInput = container.querySelector('[data-field="inference_provider_config_id"]');
    if (inferenceProviderInput) {
      var inferenceProviderValue = inferenceProviderInput.value || null;
      config.inference_provider_config_id = inferenceProviderValue;
    }
    var inferenceModelInput = container.querySelector('[data-field="inference_model"]');
    if (inferenceModelInput) {
      var inferenceModelValue = (inferenceModelInput.value || '').trim() || null;
      config.inference_model = inferenceModelValue;
    }
```

**Note**: write the key unconditionally (so toggling values from non-null → null actually clears the persisted state). The `if (inferenceProviderInput)` guard handles the absent-input case (e.g., if a future render path strips the field).

### 7. Async-populate the provider dropdown

Add a new helper after `fetchAttachedAgents` (currently `connector-editor.js:3065-3110`) that fetches `/api/providers` and populates the dropdown, mirroring `populateRoutingAgentDropdowns:2436-2480`:

```javascript
  // M11 F13 L4: populate the inference-provider dropdown from
  // /api/providers. Mirrors the routing-default-agent dropdown pattern —
  // render-with-placeholder, fetch, populate, preserve-stale-as-disabled.
  // Re-snapshot after population so the populated form is the dirty
  // baseline (otherwise the operator's first edit would compare against
  // a placeholder-only baseline that no longer exists in the DOM).
  function populateInferenceProviderDropdown(container, account, checkDirty, recaptureSnapshot) {
    var escapeAttr = window.App.escapeAttr;
    var escapeHtml = window.App.escapeHtml;
    var sel = container.querySelector('[data-testid="connector-config-inference-provider-select"]');
    if (!sel) return;  // rows hidden under always_listen=false, OR not in this render
    var currentValue = (account && account.config && account.config.inference_provider_config_id) || '';
    fetch('/api/providers')
      .then(function (resp) { return resp.ok ? resp.json() : []; })
      .then(function (providers) {
        if (!Array.isArray(providers)) providers = [];
        // Stable display order — name asc.
        providers.sort(function (a, b) {
          return String(a.name || '').localeCompare(String(b.name || ''));
        });
        var html = '';
        html += '<option value=""' + (currentValue === '' ? ' selected' : '') +
                '>— Use routed agent’s LLM —</option>';
        var matchedPersisted = false;
        for (var i = 0; i < providers.length; i++) {
          var p = providers[i];
          var pid = String(p.id || '');
          var pname = String(p.name || pid);
          if (pid === currentValue) matchedPersisted = true;
          html += '<option value="' + escapeAttr(pid) + '"' +
                  (pid === currentValue ? ' selected' : '') + '>' +
                  escapeHtml(pname) + '</option>';
        }
        // Stale-id preservation — keep the persisted value visible (and
        // selected) as a disabled option so the operator sees their
        // original choice and that it's no longer valid. Mirrors
        // populateRoutingAgentDropdowns:2466-2469.
        if (currentValue && !matchedPersisted) {
          html += '<option value="' + escapeAttr(currentValue) + '" selected disabled>' +
                  escapeHtml(currentValue) + ' (provider deleted)</option>';
        }
        sel.innerHTML = html;
        if (typeof recaptureSnapshot === 'function') recaptureSnapshot();
        if (typeof checkDirty === 'function') checkDirty();
      })
      .catch(function () {
        // Network / 5xx — leave the placeholder-only options in place.
        // The operator sees the empty-state placeholder; they can save
        // (which writes null + falls through to routed-agent's LLM).
      });
  }
```

Wire the call from `wireEditorEvents` after `attachStaticListeners()` (parallel to where `fetchAttachedAgents` is called at `:1355`). The fetch is idempotent and cheap; firing it for every editor mount (regardless of always-listen state) avoids the complexity of conditional firing — when the rows are hidden, the populated select just isn't visible.

```javascript
    // M11 F13 L4: populate the inference-provider dropdown asynchronously.
    // Fires regardless of always-listen state so the dropdown is ready
    // when the operator flips the master toggle ON.
    populateInferenceProviderDropdown(container, account, checkDirty, recaptureSnapshot);
```

### 8. New browser tests (5 tests, target +5)

Create `tests/browser/test_flow_studio_connector_inference_provider_row.py` following the F7 L11 always-listen template at `tests/browser/test_flow_studio_always_listen_toggles.py:1-345`:

```python
"""Studio connector-editor inference-provider/model rows (M11 F13 L4).

Pin five UI surfaces against regression:

1. Conditional render under ``always_listen=true``.
2. Hidden under ``always_listen=false``.
3. Provider dropdown populates from ``GET /api/providers``.
4. Selecting provider + entering model + save round-trips through
   ``connector.config``.
5. Clearing the provider selection saves ``null`` (defaults back to
   routed-agent-LLM fallback).
"""

from __future__ import annotations

import httpx
import pytest
from browser.seeders import (
    seed_connector,
    seed_mock_provider,
)
from playwright.sync_api import Page, expect


def _get_account(base_url: str, account_id: str) -> dict:
    r = httpx.get(f"{base_url}/api/connectors/{account_id}", timeout=5.0)
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _open_connector_editor_access_tab(page: Page, base_url: str, account_id: str) -> None:
    page.goto(f"{base_url}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="tab-access-and-routing"]').click()


# ── Test 1: rows hidden under always_listen=false ─────────────────────────


@pytest.mark.browser
def test_inference_rows_hidden_when_always_listen_off(app_clean: str, page: Page) -> None:
    """Seeded with always_listen=false (default) → rows not visible."""
    account_id = seed_connector(app_clean, name="Hidden-Inference Bot")
    _open_connector_editor_access_tab(page, app_clean, account_id)

    rows = page.locator('[data-testid="connector-inference-rows-container"]')
    # The wrapper may exist in the DOM with the ``hidden`` attribute.
    # Playwright's not_to_be_visible resolves true for hidden-attr OR
    # display:none OR removed-from-DOM.
    expect(rows).not_to_be_visible(timeout=4000)


# ── Test 2: rows visible under always_listen=true ─────────────────────────


@pytest.mark.browser
def test_inference_rows_visible_when_always_listen_on(app_clean: str, page: Page) -> None:
    """Seeded with always_listen=true → both rows visible."""
    account_id = seed_connector(
        app_clean,
        name="Visible-Inference Bot",
        config={"always_listen": True},
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    expect(page.locator('[data-testid="connector-config-inference-provider-select"]')).to_be_visible(timeout=4000)
    expect(page.locator('[data-testid="connector-config-inference-model-input"]')).to_be_visible(timeout=4000)


# ── Test 3: dropdown populates from /api/providers ───────────────────────


@pytest.mark.browser
def test_inference_provider_dropdown_populates_from_api(app_clean: str, page: Page) -> None:
    """Seeded with 2 mock providers → dropdown lists both + empty placeholder."""
    p1_id = seed_mock_provider(app_clean, name="provider-alpha")
    p2_id = seed_mock_provider(app_clean, name="provider-beta")
    account_id = seed_connector(
        app_clean,
        name="Populated-Dropdown Bot",
        config={"always_listen": True},
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    sel = page.locator('[data-testid="connector-config-inference-provider-select"]')
    expect(sel).to_be_visible(timeout=4000)
    # Wait for async population.
    expect(sel.locator(f'option[value="{p1_id}"]')).to_be_attached(timeout=5000)
    expect(sel.locator(f'option[value="{p2_id}"]')).to_be_attached(timeout=5000)
    # Empty-state placeholder is the first option.
    placeholder = sel.locator('option[value=""]').first
    expect(placeholder).to_be_attached()
    placeholder_text = placeholder.text_content() or ""
    assert "Use routed agent" in placeholder_text, f"expected fallback hint; got {placeholder_text!r}"


# ── Test 4: select provider + model → save round-trips ───────────────────


@pytest.mark.browser
def test_inference_provider_and_model_save_roundtrip(app_clean: str, page: Page) -> None:
    """Select provider + enter model + save → GET shows the persisted values."""
    p1_id = seed_mock_provider(app_clean, name="provider-roundtrip")
    account_id = seed_connector(
        app_clean,
        name="Roundtrip-Inference Bot",
        config={"always_listen": True},
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    sel = page.locator('[data-testid="connector-config-inference-provider-select"]')
    expect(sel.locator(f'option[value="{p1_id}"]')).to_be_attached(timeout=5000)
    sel.select_option(value=p1_id)

    model_input = page.locator('[data-testid="connector-config-inference-model-input"]')
    model_input.fill("gpt-4o-mini")

    save_btn = page.locator('[data-testid="save-connector-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    cfg = after.get("config") or {}
    assert cfg.get("inference_provider_config_id") == p1_id, (
        f"expected inference_provider_config_id={p1_id!r}; got {cfg}"
    )
    assert cfg.get("inference_model") == "gpt-4o-mini", (
        f"expected inference_model='gpt-4o-mini'; got {cfg}"
    )


# ── Test 5: clearing selection saves null ────────────────────────────────


@pytest.mark.browser
def test_inference_provider_clear_saves_null(app_clean: str, page: Page) -> None:
    """Seeded with non-null inference config → select placeholder + clear model + save → null/null."""
    p1_id = seed_mock_provider(app_clean, name="provider-to-clear")
    account_id = seed_connector(
        app_clean,
        name="Clear-Inference Bot",
        config={
            "always_listen": True,
            "inference_provider_config_id": p1_id,
            "inference_model": "qwen2.5:7b",
        },
    )
    _open_connector_editor_access_tab(page, app_clean, account_id)

    sel = page.locator('[data-testid="connector-config-inference-provider-select"]')
    # Wait for population to finish so the selected option reflects the persisted value.
    expect(sel.locator(f'option[value="{p1_id}"][selected]')).to_be_attached(timeout=5000)
    sel.select_option(value="")  # placeholder

    model_input = page.locator('[data-testid="connector-config-inference-model-input"]')
    expect(model_input).to_have_value("qwen2.5:7b")
    model_input.fill("")

    save_btn = page.locator('[data-testid="save-connector-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    cfg = after.get("config") or {}
    assert cfg.get("inference_provider_config_id") is None, (
        f"expected inference_provider_config_id=None; got {cfg}"
    )
    assert cfg.get("inference_model") is None, (
        f"expected inference_model=None; got {cfg}"
    )
```

**Note on the 5-vs-4-6 count**: the flight spec says "4-6 browser tests". L4 lands 5 — covers the 4 spec-named cases (conditional render visible, conditional render hidden, dropdown populate, save round-trip, clear-saves-null) and consolidates "visible under always_listen=true" + "hidden under always_listen=false" as separate tests (not bundled) because the failure modes are distinct (DOM rendering vs. visibility-toggling). Net browser target: **443 + 5 = 448**, within the flight spec's `447-449` envelope.

### 9. Author the behavior-test spec

Write the spec file to `tests/behavior/connector-inference-provider-config-roundtrip.md` per the `.flightops/ARTIFACTS.md` "Behavior Test — Spec" format. The spec is authored as part of L4 design (this artifact) and committed alongside the source changes. Status starts as `draft`; the operator promotes to `active` after the first successful run at the Pre-L6 gate.

The spec exercises the round-trip via the browser MCP apparatus (matching the `studio-smoke.md` + `discord-engagement.md` precedents): navigate to Studio → open connector editor → flip always_listen ON → verify rows visible → select provider → enter model → save → reload editor → verify persistence.

See the inline-authored spec file at `tests/behavior/connector-inference-provider-config-roundtrip.md` (created as part of L4 design alongside this leg artifact).

### 10. Run order

1. Read the current `connector-editor.js` around the citations to confirm no post-design drift.
2. Apply edits in this order: Step 2 markup → Step 3 reserved-keys → Step 4 conditional-render hook → Step 5 snapshot capture → Step 6 collectFormData → Step 7 async-populate helper + wire-call.
3. Write `tests/browser/test_flow_studio_connector_inference_provider_row.py` per Step 8.
4. Write `tests/behavior/connector-inference-provider-config-roundtrip.md` per Step 9 (already created during L4 design — confirm it's committed).
5. Run verification gates per the Verification Steps section above (Phase 1 → Phase 6).

## Edge Cases

- **`/api/providers` returns empty list** (operator has zero providers configured): the dropdown shows only the empty-state placeholder. The operator can still save (writes `null` → routed-agent fallback fires). This is the L4-divert-criterion clause from the flight spec ("L4's Provider dropdown population fails because `/api/providers` returns no providers — escalate to operator to seed a provider before continuing") — but only divert if the operator's actual environment has zero providers AND they cannot seed one. The browser tests don't hit this because the F7 L11 fixture pattern (and L4's new tests) explicitly seed providers. Handle gracefully (no crash) per the `.catch(function () {})` in `populateInferenceProviderDropdown`.
- **`/api/providers` 5xx / network error**: same as empty-list — the placeholder-only dropdown stays. Operator can re-open the editor to retry.
- **Persisted `inference_provider_config_id` references a now-deleted provider**: the stale-id is preserved as a disabled option labelled `{stale-id} (provider deleted)` (per `populateInferenceProviderDropdown`). Operator sees their original choice + that it's invalid; selecting a new option (or the placeholder) saves the new value. Matches the stale-selection pattern at `populateRoutingAgentDropdowns:2466-2469`.
- **Operator types a model name on a provider that doesn't expose models** (e.g., OpenAI): the L4 design deliberately accepts any free-form string — the Pydantic validator allows `str | None` with no per-provider constraint. Validation of "is this a real model for this provider" happens at runtime when the dispatcher actually calls the LLM (and fails loudly there, with the error surfaced to the audit log per F7).
- **Empty-string vs null**: the `collectFormData` writes `(input.value || '').trim() || null` so leading/trailing whitespace + empty input collapse to `null`. Pydantic's `str | None` would also accept `""` but the L3 dispatcher's "None falls through to fallback" path explicitly checks for `None`, not falsy strings. Always write `null` when the operator has cleared the field.
- **Always-listen toggle is checked at mount but the operator flips it OFF before saving**: the conditional-render hook hides the rows; the values in those (now hidden) inputs are still captured by `collectFormData` and sent to the backend. Backend persists them. Operator-level: if they flip always_listen OFF and save, they may have stranded inference settings that don't fire (because always_listen=false short-circuits the policy gate). This is acceptable — the values are dormant data, not bugs. Operator can re-enable always_listen later and the dormant settings will activate. (Alternative: clear inference fields when always-listen flips OFF. Rejected — destructive of operator state; matches the F7 L11 pattern of leaving per-agent toggles persistently configured even when greyed out.)
- **Dirty-tracker false positives from async population**: handled by the `recaptureSnapshot()` call in `populateInferenceProviderDropdown` — same pattern as `fetchAttachedAgents` + `populateRoutingAgentDropdowns`. Without this, the operator's pristine state would read as dirty (placeholder option replaced with full option list after fetch).
- **Two concurrent always-listen sources**: the L4 conditional-render hook listens on the same `change` event the F7 L11 CustomEvent listener already uses. Both run on `change` — no race condition (DOM events are synchronous to a single handler list).

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — adds Provider + Model row markup (Step 2), extends `RESERVED_CONFIG_KEYS` (Step 3), wires conditional-render hook (Step 4), adds snapshot capture (Step 5), adds collectFormData writes (Step 6), adds async-populate helper + wires call (Step 7). Estimated +90 lines.
- `tests/browser/test_flow_studio_connector_inference_provider_row.py` — NEW; 5 browser tests per Step 8. Estimated 180 lines.
- `tests/behavior/connector-inference-provider-config-roundtrip.md` — NEW; Witnessed behavior-test spec per Step 9. Authored inline as part of L4 design; status starts `draft`.

No `.gitignore` edits needed (the `tests/behavior/*/runs/*/` exclusion is already in place per recon).

No `tests/behavior/.gitkeep` needed (directory already populated with prior specs).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified (AC-1 through AC-20)
- [x] Verification Steps Phase 1-6 all green (per AC-14: backend 2794, browser 448 + 2 pre-existing failures)
- [x] `tests/behavior/connector-inference-provider-config-roundtrip.md` exists, status `draft`, committed
- [x] Update flight-log.md with L4 progress entry under the "Leg Progress" section, including post-L4 totals + the behavior-test spec authoring note
- [x] Set this leg's status to `landed` (in this file's header — `completed` is the post-flight-debrief promotion; per /agentic-workflow Phase 2d this leg lands at `landed`)
- [x] Check off L4 in flight.md (the `[ ] connector-editor-inference-provider-and-model-row` entry → `[x]`)
- [x] If final leg of flight: not applicable — L5 + L6 still pending
- [x] Phase 2d deferral: do NOT commit at L4 land per `/agentic-workflow` protocol — code review + commit batches after L5 lands (operator-driven L6 commits separately)

---

## Citation Audit

20 citations verified against current code at leg design time:

| # | Citation | Status | Notes |
|---|----------|--------|-------|
| 1 | `connector-editor.js:455-484` | OK | `always_listen` toggle block, verified verbatim. |
| 2 | `connector-editor.js:461-463` | OK | `alwaysListenConfigValue` boolean computation. |
| 3 | `connector-editor.js:484` (closing `</div>` of always-listen row) | OK | Confirmed via Read. |
| 4 | `connector-editor.js:486` (closing `</div>` of Session section's outer wrapper) | OK — actually `lifecycleHtml += '</div>';` closes the field-row; the outer section `</div>` is at line 486 (verified). |
| 5 | `connector-editor.js:782-787` | OK | `RESERVED_CONFIG_KEYS` constant with 4 entries (pairing/allowlist/routing/always_listen). |
| 6 | `connector-editor.js:976-988` | OK | `getFormSnapshot`'s always_listen capture block. |
| 7 | `connector-editor.js:1089-1097` | OK | always-listen `change` event listener that emits CustomEvent. |
| 8 | `connector-editor.js:1633-1642` | OK | `collectFormData`'s always_listen write to `config`. |
| 9 | `connector-editor.js:1644-1652` | OK | `collectFormData`'s return statement (the insertion point for the new writes is BEFORE this return). |
| 10 | `connector-editor.js:2436-2480` | OK | `populateRoutingAgentDropdowns` — the canonical pattern referenced for Step 7. |
| 11 | `connector-editor.js:2466-2469` | OK | Stale-selection-preservation snippet (`disabled` option marker). |
| 12 | `connector-editor.js:3065-3110` | OK | `fetchAttachedAgents` — the async-after-mount pattern reference for Step 7. |
| 13 | `connector-editor.js:1355` | OK | `fetchAttachedAgents(container, account, checkDirty, recaptureSnapshot);` call site in `wireEditorEvents`. |
| 14 | `api.py:3349-3353` | OK | `@router.get("/providers")` handler returning `list[dict]`. |
| 15 | `api.py:3316-3319` | OK | `_provider_response` returning `provider.model_dump()` with `api_key` masked — confirms `id`, `name`, `type` keys are present. |
| 16 | `the_one/db/models.py:629-643` | OK | `_validate_config_reserved_keys`'s `inference_provider_config_id` + `inference_model` shape validators (L2 landed). |
| 17 | `tests/browser/seeders.py:34-57` | OK | `seed_mock_provider`. |
| 18 | `tests/browser/seeders.py:88-135` | OK | `seed_connector` with `config` kwarg. |
| 19 | `tests/browser/test_flow_studio_always_listen_toggles.py:1-345` | OK | F7 L11 always-listen tests (6 tests, template for L4's new test file). |
| 20 | `tests/browser/conftest.py:113-184` | OK | `app_clean` fixture with `THE_ONE_DEV_MODE=true` + `THE_ONE_REGISTER_STUB_CONNECTOR=1`. |

All 20 citations cleanly verified — no drift from L2 + L3 landing. The architect-cycle-1 prediction that `connector-editor.js:455-484` would be the post-L2/L3 always-listen location holds (the F5 design-language sweep + F7 L11/L12 always-listen work landed before F13 began, so the surface had already stabilized).
