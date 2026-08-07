# Behavior Test: Connector Inference Provider Config Round-Trip (F13 L4)

**Slug**: `connector-inference-provider-config-roundtrip`
**Status**: active
**Created**: 2026-05-31
**Last Run**: 2026-05-31-23-56-31 (PASS 8/8)

## Intent

Verify that an operator can configure per-connector inference LLM settings (Provider + Model) through the Studio connector editor's Session section, and that those settings persist across an editor close/reopen — exercising the L2 substrate (Pydantic + v26 migration), L3 dispatcher refactor (connector-scope reads), and L4 UI (conditional render + collect-path) together as a single round-trip. This is a UI-flow regression net the unit browser tests don't reach — they hit the surfaces in isolation; this hits them as the operator does: master toggle ON → rows appear → select provider → enter model → save → reopen → state persists. The Witnessed pattern (Validator independent of Executor) catches false-positive scenarios where the DOM says one thing but the rendered UI says another (e.g., a save indicator fires but the persisted value didn't actually update).

## Preconditions

- The-one is running host-native on a **non-default port with a scratch data directory**
  (never the operator's default `:8484` instance) and Studio loads at that URL (verified
  by an active probe: the operator opens the URL in a browser and sees the Studio render
  before invoking the test). **Note**: this spec's Steps literally write
  `http://localhost:8484` in several places — treat every such instance as a placeholder
  for this instance's actual base URL, never as a literal instruction to target port 8484.
- The operator has the chrome-devtools MCP browser session attached to that URL, reached
  via CLAUDE.md's "Behavior-test credential convention" (a handoff-authenticated
  navigation, not a bare `goto`).
- **Credential**: this instance is gated (Mission 20 Flight 1). Read the long-lived
  credential from the instance's data directory per the convention above; attach it as
  `Authorization: Bearer <credential>` to every `curl` call below, and mint a fresh
  handoff for each browser navigation to the app root (a handoff is single-use).
- The operator has **at least 2 configured LLM providers** in `/api/providers` (verified by an active probe: the operator opens Studio's Providers area and confirms 2+ providers are listed; or runs `curl -s http://localhost:8484/api/providers | jq 'length'` and confirms `>= 2`). The flight spec's L4 Prerequisites already require "at least one configured LLM provider"; this spec asks for two so the dropdown's option-set is more than just the empty placeholder, and the round-trip can verify a non-placeholder selection persists.
- At least one connector account exists in Studio (any type — Discord, Stub, or other). The test does NOT require the connector to be paired or live — only that it has an editable Session section. If none exists, the operator creates a Stub connector named `Inference-Test Bot` before invoking the test (verified by an active probe: `curl -s http://localhost:8484/api/connectors | jq 'length'` returns `>= 1`).
- The operator knows the target connector's name (passed in as a parameter at run time or selected during step 1).
- The build under test includes F13 L1+L2+L3+L4 commits (verified by checking the connector-editor source has the `inference_provider_config_id` reserved-key entry — `git grep -n 'inference_provider_config_id' the_one/interfaces/web/static/js/areas/studio/connector-editor.js` returns at least 3 hits).

## Observables Required

- browser (Studio DOM + rendered visual state of the connector editor — measured via chrome-devtools MCP; screenshot + a11y snapshot are the primary evidence; DOM eval is supplementary)
- http (the connector's `GET /api/connectors/{id}` response after save — measured via shell `curl` or equivalent, used in step 6 as the substrate-level confirmation that the value persisted)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Open Studio at `http://localhost:8484/`. Navigate to the Agent Studio area's Connector Accounts list. Identify a target connector account (any type with an editable Session section) and open its editor. Click the "Advanced" tab (formerly "Access and Routing"). | The connector editor loads. The Advanced tab is selected. The Session section is visible at the bottom of the tab and contains a "Chat-session window" dropdown, an "Idle timeout" dropdown, and an "Always Listen" toggle. The Always Listen toggle is in some state (checked or unchecked — record which); the test will normalize to ON in step 2 if needed. The Inference provider row and Inference model row are NOT visible if the toggle is unchecked; ARE visible if it is checked. |
| 2 | If the Always Listen toggle is unchecked, click it to check it. Wait briefly for any conditional-render reflow. | The Always Listen toggle is checked. Two new field-rows appear in the Session section (without a page reload): an "Inference provider" dropdown and an **"Inference model" dropdown** (post-enhancement: was a free-text input pre-enhancement; now a provider-aware select). Both rows render in the same field-row 3-column pattern as surrounding Session rows (label + info-icon button + control). When no provider is selected, the model dropdown shows a disabled placeholder option containing the phrase "Select a provider first" (since model selection is meaningless without a provider). |
| 3 | Click the Inference provider dropdown to open it. Observe the option list. | The dropdown opens. The first option's text contains a fallback hint resembling "Use routed agent's LLM" (the empty-state placeholder). At least two other options are present, each labelled with a configured provider's name. The list is sorted alphabetically by name (a stable display order). |
| 4 | Select one of the provider options (NOT the empty placeholder — pick a specific named provider; remember which one). **Wait briefly** for the model dropdown to populate from `GET /api/providers/{id}/models`. Then click the **Inference model dropdown** and select a model from the list (record the selected model identifier — e.g. `qwen2.5:7b` for the Ollama provider, or any model listed for the chosen provider). | **Rendered state**: the provider dropdown trigger displays the selected provider name as visible text (screenshot evidence). The **model dropdown** is now populated — its trigger no longer shows "Select a provider first"; it shows either "— No model —" (default placeholder) or the selected model id once chosen. After selection, the model dropdown trigger displays the selected model identifier. The Save button at the top of the editor becomes enabled (the dirty-tracker detected the edits). |
| 5 | Click the Save button. Wait for the save confirmation. | A confirmation indicator appears — typically a transient toast / banner with text like "Connector saved" or "Changes saved" (the exact text may vary; the test records what was observed). The Save button becomes disabled again (the dirty-tracker considers the form clean post-save). No error banner appears. |
| 6 | Cache-defeat: navigate away from the editor to the Connector Accounts list (or hard-reload the page with `Ctrl+Shift+R`). Then re-open the same connector account's editor. Click the Advanced tab. Confirm the Session section is visible. | The editor loads cleanly. The Advanced tab is selected. The Session section's Always Listen toggle is still checked (persisted from step 2). The Inference provider row and Inference model row are visible. **Rendered state**: the Inference provider dropdown trigger displays the provider name chosen in step 4 as visible text (screenshot evidence confirms the rendered text, not just an internal `.value`). The Inference model input visibly contains the same text typed in step 4. `[mixed-frame]` Confirm at the HTTP layer (curl on a separate line for clean copy-paste): see the curl probe in the row below. The HTTP probe confirms the substrate persisted the correct **provider id** (canonical stored form), distinguishing "looks right in the UI but wrong on disk" from a true round-trip. |
| 7 | (Cleanup / negative-path validation, optional but recommended.) In the still-open editor from step 6, change the Inference provider dropdown back to the empty placeholder option ("Use routed agent's LLM"). The model dropdown should automatically revert to "Select a provider first" (since selecting the provider-cleared option triggers the model-repopulate to the no-provider state). Click Save. Wait for confirmation. Reload the editor (as in step 6) and re-inspect. | Save confirmation appears; Save button disables. After reload, the Inference provider dropdown is on the empty placeholder; the **model dropdown shows "Select a provider first" disabled placeholder** (no model selectable when no provider). `[mixed-frame]` HTTP probe: `curl -s http://localhost:8484/api/connectors/{account_id} \| jq '.config \| {inference_provider_config_id, inference_model}'` returns `{"inference_provider_config_id": null, "inference_model": null}`. Justification: confirms empty values serialize as JSON `null` (per the L4 collect-path's `(value \|\| '').trim() \|\| null` rule), not empty strings — the L3 dispatcher's "None → routed-agent fallback" path requires actual `null`. |

| 8 | (Optional but recommended — verifies the `(custom)` fallback for persisted models that aren't in the API's model list, e.g. for an Ollama model the operator pulled locally but hasn't enabled yet, or for an OpenAI/Anthropic model the provider doesn't enumerate.) Via direct PUT, set the connector's `inference_provider_config_id` to a provider id AND `inference_model` to a string that is NOT in that provider's `GET /api/providers/{id}/models` response (e.g. `my-custom-untracked-model`). Reload the editor + click Advanced + observe the model dropdown. | The model dropdown's selected option text reads `{the-typed-value} (custom)` — the persisted model is preserved as a visible-and-selected `(custom)` option (mirrors chat agent-editor's pattern for models the API can't enumerate). The HTTP probe confirms the substrate still has the original string verbatim (no `(custom)` suffix on disk — that's display-only). |

## Out of Scope

- The dispatcher actually USING the configured inference provider/model at policy-gate time (covered by the existing `discord-engagement.md` behavior test and by `tests/test_connectors_inference.py` unit tests).
- The v26 migration backfill correctness (covered by `tests/test_db_migration.py::TestSchemaV26` from L2).
- The L3 Settings-removal startup warning (covered by `tests/test_lifespan.py` from L3).
- The audit-log inspector UI rendering the chosen provider/model in routing entries (covered by the L5 behavior test `audit-log-inspector-renders-routing-entries.md`, authored separately).
- Per-agent always-listen toggles in the agent editor's Connectors tab (covered by the F7 L11 browser tests).
- Provider validity at the LLM call site (e.g., a typo'd model name causing the inference call to 4xx) — that's a runtime error surfaced by the audit log + dispatcher, not a UI-config-flow concern.
- Slash-command verification against the real Discord bot (covered by L6 HAT).
- Performance / accessibility audits — separate concerns.

## Variants (optional)

None for this initial round. Future variants could:
- Parametrize the connector type (Discord vs Stub vs future types) to confirm the rows render uniformly across types.
- Test the stale-provider-id case: seed a connector with `inference_provider_config_id` pointing to a now-deleted provider, then verify the dropdown shows the disabled `{stale-id} (provider deleted)` option per the L4 stale-preservation pattern.
- Test cross-tab coordination: open the editor in two browser tabs, change the provider in tab A, save, refresh tab B, confirm tab B reflects the change.
