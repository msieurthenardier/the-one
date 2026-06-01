# Leg: l4-enhancement-unit-test-backfill

**Status**: completed
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](../flight.md)

## Objective

Backfill browser-test coverage for the F13 L4-enhancement (`populateInferenceModelDropdown` + `wireInferenceModelRepopulate` in `connector-editor.js`), which shipped with zero unit tests AND broke 3 existing tests in its own file (it swapped the model `<input>` for a `<select>` and never updated the tests). L4 (1) repairs the 3 stale-fixture failures and (2) adds 3-5 new browser tests covering the documented dropdown flows. Test-only — no production JS/backend change.

## Context

- **Design-review finding (cycle 1) — the file is NOT a clean 5-test baseline.** 3 of the 5 existing tests in `test_flow_studio_connector_inference_provider_row.py` currently FAIL on this branch: `test_inference_rows_visible_when_always_listen_on`, `test_inference_provider_and_model_save_roundtrip`, `test_inference_provider_clear_saves_null`. They reference `data-testid="connector-config-inference-model-input"`, which never existed — the F13 L4-enhancement (commit `ed78d0e`) rendered the model field as `connector-config-inference-model-select` (a `<select>`), so `.fill("gpt-4o-mini")` on a `<select>` is impossible. **These are stale TEST fixtures, not production bugs** — repairing them is squarely L4's purpose. L4 fixes them (input→select: use `.select_option()`, and the model value must be one the seeded provider serves so the option exists) AND adds the new flows.
- **Flight baseline discrepancy (for L5 reconciliation)**: flight.md:76/125/212 declare the browser baseline as "454 passed / 2 pre-existing-main failures" naming ONLY `test_tablist_renders_with_three_tabs` + `test_studio_section_round_trip_preserves_agent_selection` (L5's scope). These 3 inference-file failures are NOT in that inventory — the true main browser-failure set is larger. L4 OWNS these 3 (they're its file); L5 stays scoped to its 2 named ones. The flight's "460" arithmetic is stale; counts are recorded as actuals and reconciled at Phase 2d. Flagged in flight-log for L5's design.
- **F13 debrief carry-forward**: the model-dropdown enhancement (provider→models fetch, race-guard via `AbortController`, `(custom)` fallback, no-provider placeholder, GUI-clear-fires-synthetic-change) landed post-F13-L4 with no test coverage. F14 closes that test debt.
- **Confirmed harness facts (design review)**: a `type=="mock"` provider's `GET /api/providers/{id}/models` returns `config["models"]` directly (`api.py:3576-3586`) — so `seed_mock_provider(app_clean, name="x", config={"models": ["m1","m2"]})` self-serves models; NO `page.route()` stub needed for populate/custom/placeholder. Model dropdown testid: `connector-config-inference-model-select` (`<select id="cf-inference-model" data-field="inference_model">`, connector-editor.js:556-558). Provider-clear = `select_option(value="")` on `connector-config-inference-provider-select` (existing test 5 does this). Race-guard precedent to mirror VERBATIM: `tests/browser/test_flow_studio_openrouter_picker.py:177-207` (`page.route` handler `time.sleep(0.6); route.continue_()`, switch mid-flight, assert stale provider's models absent).
- **Code under test**: `connector-editor.js` — `populateInferenceModelDropdown` (`:3349-3431`), `wireInferenceModelRepopulate` (`:3332-3346`), the model `<select>` render (`:541-566`, default placeholder "Select a provider first"). The fetch hits `GET /api/providers/{id}/models` (mirrors the chat agent-editor model dropdown). Race-guard: `_connectorModelsFetchController` (`:3365`) aborts an in-flight fetch when the provider changes.
- **Existing test file**: `tests/browser/test_flow_studio_connector_inference_provider_row.py` (175 lines, 5 tests) covers the inference *provider-select* row + save round-trip + clear-saves-null, but NOT the *model dropdown*. L4 extends this file (or a sibling) with model-dropdown tests.
- **This is test-only** — no JS or backend production change. If a test surfaces a real bug in `populateInferenceModelDropdown`, STOP and report it (do not silently fix production in a test-backfill leg — that would be a scope change to flag).

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js:3329-3431` (+ `:541-566`, `:1497`) — the functions under test.
- `tests/browser/test_flow_studio_connector_inference_provider_row.py` — existing harness: `seed_mock_provider`, `app_clean`, `page`, the `connector-config-inference-provider-select` testid, the always-listen toggle that reveals the inference rows.
- `GET /api/providers/{id}/models` — the models endpoint the dropdown fetches; the implementer determines how to make a seeded mock provider return models (real endpoint behavior vs `page.route()` stub).

## Outputs

- 3-5 new browser tests in `test_flow_studio_connector_inference_provider_row.py` covering the documented model-dropdown flows.

## Acceptance Criteria

- [ ] **The 3 stale-fixture failures are repaired** (input→select): `test_inference_rows_visible_when_always_listen_on`, `test_inference_provider_and_model_save_roundtrip`, `test_inference_provider_clear_saves_null` all PASS. Use `connector-config-inference-model-select` + `.select_option(...)`; the round-trip test's model value must be one the seeded mock provider serves via `config={"models":[...]}` so the option exists.
- [ ] **Net file state: all tests passing** — the 5 existing (3 repaired + 2 already-green) + 3-5 new = **8-10 tests, 0 failing** in this file.
- [ ] New browser tests cover (target 3-5 of) these documented flows:
  - (a) **populate**: provider selected (e.g. an Ollama-style mock with models) → model dropdown populates with 1+ model options.
  - (b) **race-guard**: switching provider (A→B) while A's model fetch is in flight cancels the stale fetch via `AbortController` — the dropdown ends with B's models, not A's (no stale overwrite).
  - (c) **custom fallback**: a persisted model value NOT in the fetched list surfaces as a selected `"{value} (custom)"` option.
  - (d) **no-provider placeholder**: with no provider selected, the model dropdown shows the disabled `"Select a provider first"` placeholder.
  - (e) **GUI-clear fires synthetic change** (the F13 bug-fix regression target): clearing the provider via the GUI fires a synthetic change event so Save becomes enabled / the model dropdown resets.
- [ ] Each test uses real testids/selectors (`connector-config-inference-provider-select` + `connector-config-inference-model-select`).
- [ ] Browser suite: net file goes from 2-passing/3-failing → 8-10 passing/0-failing (record actuals; the flight's "460" target is stale — see Context).
- [ ] No orphaned chromium after the run (bounded wrapper used).
- [ ] **No production JS/backend change.** The "report don't fix" rule applies to PRODUCTION defects in `populateInferenceModelDropdown` only — repairing the 3 stale TEST fixtures IS authorized and required. If a genuine production defect surfaces (e.g. the race-guard doesn't actually cancel, `(custom)` doesn't render), STOP and report it rather than fixing inline.

## Verification Steps

- `docker exec the-one bash -c 'TEST_TIMEOUT=600 bash /app/scripts/run-tests.sh -m browser tests/browser/test_flow_studio_connector_inference_provider_row.py -q'` — file passes (existing 5 + new 3-5); confirm no stragglers afterward (`docker exec the-one ps -eo pid,cmd | grep -iE "chrome-headless|pytest|playwright" | grep -v defunct | grep -v grep` empty).
- Record the file's before/after test count.

## Implementation Guidance

1. **Determine the models-endpoint approach FIRST.** Inspect how the chat agent-editor model dropdown is tested (the L4-enhancement mirrors it) and how `GET /api/providers/{id}/models` behaves for a seeded mock provider. Two viable paths: (i) seed a mock provider whose `/models` returns real model rows; (ii) `page.route()`-stub `**/api/providers/*/models*` with a controlled payload. Use whichever the existing browser harness already supports for model dropdowns — match precedent, don't invent.
2. **(a) populate**: enable always-listen to reveal the inference rows, select a provider, assert the model `<select>` gets ≥1 option (beyond the placeholder).
3. **(b) race-guard**: this is the trickiest. To exercise the `AbortController` cancel, you need provider A's `/models` fetch in flight when you switch to B. Use `page.route()` with a deferred/delayed fulfill for A's models (or a route that controls timing) so the switch happens mid-flight; assert the final options are B's. If deterministic timing proves flaky, a lighter assertion (switching providers repopulates with the new provider's models and never shows a mix) is acceptable — document the chosen rigor in the test docstring.
4. **(c) custom fallback**: seed/edit a connector whose persisted inference model is a string NOT in the provider's `/models` list; open the editor; assert the model select has a selected option labeled `"{value} (custom)"`.
5. **(d) no-provider placeholder**: with provider cleared/unset, assert the model select shows the disabled `"Select a provider first"` option.
6. **(e) GUI-clear synthetic change**: clear the provider via the GUI control; assert Save becomes enabled (or the dirty-state fires) — this is the regression target for the F13 recapture bug. Reuse the existing file's dirty/save assertions.
7. **Run via the bounded wrapper**, scoped to this one file. Record counts; confirm no orphans.

## Edge Cases

- **Race-guard flakiness**: if `AbortController` timing can't be made deterministic in the harness, fall back to the lighter "repopulate with new provider, never a mix" assertion and note it — do NOT add a real `sleep` that could wedge.
- **`AbortController` undefined guard** (`:3365` checks `typeof AbortController !== 'undefined'`): the headless chromium has it, so the guard isn't exercised — fine, not in scope.
- **A real bug surfaces**: e.g. the race-guard doesn't actually cancel, or `(custom)` doesn't render. Report as `[BLOCKED]` / a finding — this leg backfills tests, it does not authorize production fixes.

## Files Affected

- `tests/browser/test_flow_studio_connector_inference_provider_row.py` — +3 to +5 model-dropdown tests.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]` — except commit, which is deferred to Phase 2d per agentic-workflow batch protocol:**

- [x] All acceptance criteria verified (5 model-dropdown tests pass)
- [x] No orphaned chromium (wrapper used); browser count recorded (2-pass/3-fail → 10-pass/0-fail)
- [x] Update flight-log.md with L4 leg progress entry (tests added, models-endpoint approach, race-guard rigor chosen)
- [x] Set this leg's status to `landed`
- [ ] Do NOT check off this leg in flight.md yet (Phase 2d)
- [ ] Do NOT commit (batched at Phase 2d)
