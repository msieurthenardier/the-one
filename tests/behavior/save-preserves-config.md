# Behavior Test: Save preserves out-of-band provider config (seed-before-overlay)

**Slug**: `save-preserves-config`
**Status**: active
**Created**: 2026-07-10
**Last Run**: 2026-07-10-19-51-00 (pass, 4/4)

## Intent

Verify that saving a provider through the Admin UI editor — which only exposes a subset of
`LLMProviderConfig.config` fields (today: `reasoning_effort`; NOT `response_format` or `stop`,
which are config/env-only) — does not silently drop config keys that were set out-of-band via
the API. This is the regression net for the `seed-before-overlay for partial-field UI saves`
convention (`the_one/agents.md`, `### Mission-specific (M16)`): the editor's save path seeds
`payload.config` from the existing provider's config object before overlaying the fields the UI
actually edited, so `response_format`/`stop` survive a UI-triggered save instead of being wiped
by the backend's field-level-replace update (`existing.model_copy(update=data)`). This needs a
**behavior test** rather than a unit test because the defect this guards against is a UI+API
interaction — a unit test on the save-payload seeding logic in isolation would not catch a
regression introduced by, e.g., a future editor rewrite that stops calling the seed step before
POSTing.

## Preconditions

- the-one is running host-native and reachable on `http://localhost:8485` (the mission dev
  instance), with `THE_ONE_DEV_MODE=true`. Verify with an **active probe**:
  `GET http://localhost:8485/api/providers/types` returns 200.
- **No pre-seeded provider is required** — the provider under test is created through the API by
  this flow's setup step and deleted by teardown. To keep the run deterministic, use a
  distinctive name (`SPC-test-provider`); if a prior partial run left a provider by that name,
  delete it before Step 1 (`GET /api/providers` → find by name → `DELETE /api/providers/{id}`).
- A **chrome-devtools** browser apparatus is attached to 8485 for the UI-editing steps. **Never
  touch 8484.**
- An `http` apparatus (curl via Bash, or an equivalent MCP) for the API setup/verification steps.

## Observables Required

- http (provider create/PUT/GET response status + body — measured via curl/Bash; used for setup,
  the out-of-band config write, and the final re-fetch verification).
- browser (rendered admin/providers UI: the provider editor's `.field-group` fields, the
  Reasoning Effort `<select>`, the Save button's enabled/disabled state — measured via
  chrome-devtools; a11y-tree + screenshot as primary rendered-state evidence).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | (Setup, no judgment) Probe `GET /api/providers/types` for 200. If a provider named `SPC-test-provider` already exists (`GET /api/providers`), `DELETE` it. Via the API, `POST /api/providers` with `{"name": "SPC-test-provider", "type": "openai-compatible", "base_url": "https://example.invalid/v1", "api_key": "sk-test-not-real"}`. | (empty) |
| 2 | (Setup, no judgment) Via the API, `PUT /api/providers/{id}` (the id from Step 1) with `{"config": {"response_format": "json_object", "stop": ["END"]}}`. | (empty) |
| 3 | (Setup, no judgment) `GET /api/providers/{id}` and confirm the response's `config` contains `response_format: "json_object"` and `stop: ["END"]` — establishes the out-of-band baseline the rest of the test protects. | (empty) |
| 4 | Open a fresh chrome-devtools page at `http://localhost:8485/#admin/providers` with an `ignoreCache` hard-reload. Re-select the `SPC-test-provider` card to open its editor. | The provider editor opens in edit mode for `SPC-test-provider`: the **Reasoning Effort** field-group is visible (its select is bound to `config.reasoning_effort`), showing **"Provider default"** selected (the field was never set). The primary button reads **Save** and is disabled (no unsaved changes). |
| 5 | In the Reasoning Effort select, choose **"high"**. | The select shows "high" selected; the **Save** button is now enabled (the form is dirty). |
| 6 | Click **Save**. | The save succeeds (no error flash). The Save button returns to disabled (no unsaved changes); the Reasoning Effort select still shows "high". |
| 7 | Via the API, `GET /api/providers/{id}` and inspect the `config` object. | `config.reasoning_effort` is `"high"` (the UI-edited field), AND `config.response_format` is still `"json_object"`, AND `config.stop` is still `["END"]` — all three keys survive the UI-triggered save together. |
| 8 | (Teardown, no judgment) `DELETE /api/providers/{id}`. Confirm it no longer appears in `GET /api/providers`. | (empty) |

**Row conventions:** one row = one logical checkpoint. Step 7 is the test's load-bearing
assertion; a failure there (missing `response_format` or `stop`) is the exact seed-before-overlay
regression this test exists to catch.

**Locators (apparatus-agnostic — the Executor maps to its MCP):** provider grid tile
`data-testid="provider-card"` (providers-grid.js); Reasoning Effort select
`data-field="config.reasoning_effort"` / `id="pf-reasoning-effort"` (provider-editor.js); Save
button `data-testid="save-provider-btn"` (provider-editor.js). **Cache discipline:** the grid and
editor are client-rendered SPA views — hard-reload with `ignoreCache` before re-observing after
the API-side mutations in Steps 1-3, so a stale in-memory provider list doesn't mask the setup.

## Out of Scope

- The **Reasoning Effort** field's functional effect on actual LLM requests (that the resolved
  value reaches the provider's request kwargs) — covered by
  `tests/test_llm_provider_cross_provider_conformance.py` and the per-provider request-kwargs unit
  tests, not this flow.
- **Response Format / Stop UI editing** — these fields have no UI surface by design (config/env
  only, `provider-request-param-config-surface (M16 F11)`); this test only verifies they survive
  a save that edits a *different* field, not that they're independently editable.
- The full provider CRUD flow (create via UI, delete via UI, Test Connection) — covered by
  `tests/behavior/system-provider-config.md`.
- Non-`openai-compatible` provider types — the seed-before-overlay save path is type-agnostic
  (it operates on the generic `payload.config` object before the type-specific overlay), so one
  type is sufficient to exercise it; not re-verified per type here.

## Variants

None — a single deterministic run is sufficient; this is a persistence-correctness check, not a
rendering check that benefits from a light/dark theme matrix.
