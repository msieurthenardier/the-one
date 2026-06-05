# Leg: retention-input-general-tab

**Status**: completed
**Flight**: [Retention Setting](../flight.md)

## Objective

Render the `chat_history_retention_days` value as a number input in the General-tab Behavior
section, positioned above Max Iterations, and wire it through form collection and save/load so
it round-trips to the backend field added in Leg 1.

## Context

- **Depends on Leg 1** (`landed`): `AgentConfig.chat_history_retention_days` exists and is
  persisted/served via `model_dump()`; the API returns it on `GET /api/agents/{name}` and accepts
  it on POST/PUT (rejecting out-of-range with 422). This leg only adds the UI surface.
- **Mission criterion**: the setting must appear in the Behavior section **above Max Iterations**.
- **Flight DD6 (raw-value preserving collection)**: the `collectFormData` branch for this field
  must NOT use the `parseInt(...) || 20` falsy-coercion idiom that `max_iterations` uses
  (`studio.js:1929`, fallback `20`). `parseInt("0", 10) || 30` evaluates to `30` (0 is falsy),
  which would silently coerce a typed
  out-of-range `0` into a valid `30` and save it — the "silently accepted or clamped" failure mode
  mission criterion 2 forbids. Preserve the raw value so `0`/`400` reach the server and are
  rejected with a visible 422: `var n = parseInt(f.value, 10); data[key] = Number.isNaN(n) ? 30 : n;`
- **Image-baked path**: JS edits are not live until `make rebuild`.

## Inputs

What exists before this leg runs:
- `the_one/interfaces/web/static/js/areas/studio/general-tab.js` — `renderGeneralTab`; the
  Behavior `editor-section` with the Max Iterations `field-row` at `:116–121`; the create-mode
  default `cfg` object at `:24–31` (currently seeds `name`, `description`, `provider_config_id`,
  `llm_model`, `system_prompt`, `max_iterations: 20`).
- `the_one/interfaces/web/static/js/areas/studio.js` — `collectFormData` at `:1920–1935`; the
  `max_iterations` branch at `:1928–1929` (`data[key] = parseInt(f.value, 10) || 20;`); the save
  flow (PUT at `:2429–2433`, `!r.ok` throw at `:2436`, reload via `loadAll()` at `:2442`, error
  surfaced to `errorEl` at `:2459`).
- `tests/browser/test_flow_agent_tabs.py` — agent-editor flow tests using the `app_with_agent`
  fixture + `_wait_editor_ready(page)` helper; the General tab mounts `[data-field="..."]` inputs.
  No existing browser test references the Behavior section / Max Iterations (verified by grep), so
  inserting above Max Iterations breaks nothing.

## Outputs

What exists after this leg completes:
- A number input in the Behavior section above Max Iterations:
  `id="studio-retention-days"`, `data-field="chat_history_retention_days"`, `type="number"`,
  `min="1"`, `max="365"`, value seeded from `cfg.chat_history_retention_days || 30`.
- The create-mode default `cfg` object seeds `chat_history_retention_days: 30`.
- A `collectFormData` branch that preserves the raw value (DD6), so out-of-range values reach the
  server (422) instead of being client-coerced.
- A browser test asserting the input renders in the Behavior section above Max Iterations.

## Acceptance Criteria

- [x] The General tab renders a number input with `data-field="chat_history_retention_days"` and
  `id="studio-retention-days"`, inside the Behavior `editor-section`, **before** (above) the
  `data-field="max_iterations"` input in DOM order.
- [x] The input carries `type="number"`, `min="1"`, `max="365"`, and is seeded from the agent's
  current `chat_history_retention_days` (30 for a freshly-migrated agent; the create-mode default
  object also seeds 30).
- [x] `collectFormData` includes `chat_history_retention_days` as an integer, preserving raw
  out-of-range input (a typed `0` or `400` is sent as-is, NOT coerced to 30); only NaN/empty
  falls back to 30.
- [x] Saving a valid retention value persists it and it survives a full page reload (the input
  reflects the saved value on reload — backed by `GET /api/agents`).
- [x] A new browser test in `tests/browser/test_flow_agent_tabs.py` asserts the input's presence
  and above-Max-Iterations placement; `make test-browser` passes (no regression in the agent-tab
  flow suite).
- [x] `ruff check`/`ruff format --check` remain clean (no Python touched beyond the test file,
  which must still pass format/lint).
- [ ] The flight-level behavior test `agent-retention-setting-roundtrip` passes (run by the Flight
  Director after this leg; not executed by the implementer).

## Verification Steps

- `make rebuild` (JS edits require it).
- Browser flow suite — **must use the browser marker**, because `pyproject.toml:76` `addopts`
  deselects `browser` by default, so a bare `pytest tests/browser/...` runs ZERO tests and exits
  0 (false green). Use the canonical form:
  `docker exec the-one bash /app/scripts/run-tests.sh -m browser tests/browser/test_flow_agent_tabs.py -v --tb=short`
  (or the full `make test-browser`). `THE_ONE_DEV_MODE` is set internally by `conftest.py` on the
  app subprocess — the caller does NOT need to export it. Run the new placement test plus the
  existing agent-tab tests to confirm no regression.
- Manual (or via the behavior test): open Studio → an agent → General tab; confirm the retention
  input sits above Max Iterations in the Behavior section, set a value, Save, reload, confirm it
  persists.
- Lint/format: `docker exec the-one ruff check tests` and `docker exec the-one ruff format --check tests`.

## Implementation Guidance

1. **Render the input above Max Iterations** (`general-tab.js`, Behavior section `:116–121`)
   - Inside the Behavior `editor-section`, emit the retention `field-row` BEFORE the Max
     Iterations `field-row`, mirroring the existing markup idiom:
     ```js
     html += '<div class="field-row"><label for="studio-retention-days">Chat History Retention (days)</label>' +
       '<input id="studio-retention-days" class="field-input field-input-short" ' +
       'data-field="chat_history_retention_days" type="number" value="' +
       (cfg.chat_history_retention_days || 30) + '" min="1" max="365" /></div>';
     ```
   - Keep the existing Max Iterations row immediately after it. (Exact label wording is cosmetic —
     Flight 4 owns UX polish — but use a clear label; "Chat History Retention (days)" is fine.)

2. **Seed the create-mode default** (`general-tab.js:24–31`)
   - Add `chat_history_retention_days: 30` to the fallback `cfg` object used when `agent` is null,
     so the create form renders 30 by default.

3. **Collect the field, preserving raw value** (`studio.js`, `collectFormData` `:1920–1935`)
   - Add a branch alongside the `max_iterations` branch (DD6 — do NOT use `|| 30`):
     ```js
     } else if (key === 'chat_history_retention_days') {
       var n = parseInt(f.value, 10);
       data[key] = Number.isNaN(n) ? 30 : n;
     } else if (key === 'provider_config_id') {
     ```
   - This routes the existing `data-field` collector; no save-path change is needed (the PUT already
     sends the whole `data` object, and the server validates).

4. **Add the placement browser test** (`tests/browser/test_flow_agent_tabs.py`)
   - Add a `@pytest.mark.browser` test using `app_with_agent` + `_wait_editor_ready(page)` that:
     - asserts `page.locator('[data-field="chat_history_retention_days"]')` is visible with
       `id="studio-retention-days"`, `type="number"`, `min="1"`, `max="365"`;
     - asserts it precedes `[data-field="max_iterations"]` in DOM order. Use
       `compareDocumentPosition` as the primary approach (the project idiom — see
       `test_flow_studio_mcp_editor.py:722–732`): evaluate
       `el_retention.compareDocumentPosition(el_maxiter) & Node.DOCUMENT_POSITION_FOLLOWING`
       (truthy ⇒ retention comes before max-iterations).

5. **Rebuild + run** — `make rebuild`, then the browser flow suite + ruff (see Verification).

## Edge Cases

- **Out-of-range typed value**: a typed `0` or `400` must reach the server (422), NOT be coerced
  client-side — guaranteed by the DD6 raw-preserving branch. The error surfaces in `errorEl`
  (`studio.js:2459`). (UI reject behavior is exercised by the flight behavior test, not this leg's
  browser test.)
- **Empty / non-numeric input**: `Number.isNaN(n)` falls back to 30 (mirrors the existing
  empty-input default intent without the falsy-0 bug).
- **Create vs edit mode**: edit mode seeds from the loaded agent; create mode seeds from the
  default `cfg` object (both 30 for a fresh/default agent).
- **Reload persistence**: after Save, the editor re-renders from `GET /api/agents` (`studio.js:2442`),
  so the input reflects the stored value — no extra wiring needed.
- **Field-row width class**: reuse `field-input-short` (as Max Iterations does) for visual
  consistency; cosmetic, adjustable in Flight 4.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/general-tab.js` — render the retention input
  above Max Iterations; seed the create-mode default.
- `the_one/interfaces/web/static/js/areas/studio.js` — add the raw-preserving `collectFormData`
  branch.
- `tests/browser/test_flow_agent_tabs.py` — add the placement/presence browser test.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified (behavior-test criterion pending Flight Director's acceptance gate)
- [x] Tests passing (browser flow suite; ruff clean)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] Do NOT commit, do NOT check off flight.md/mission.md — deferred to the flight-level commit
  after this final autonomous leg (per `/agentic-workflow` deferred-commit model) — flight-level commit created at end of Flight 1
