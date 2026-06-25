# Leg: search-config-admin-ui

**Status**: completed
**Flight**: [Agent-loop Resource Governance & Context-budget Management](../flight.md)

## Objective
Make the `web_search` engine config usable in the built-in-tools admin form: render
secret fields as **masked password inputs with an eye-toggle**, and **show each engine's
fields only when that engine is selected** (generic `show_if` conditional visibility) — so
an operator picks an engine from the dropdown and sees exactly that engine's key/URL
fields, with keys masked and preserved on save (the leg-3 contract).

## Context
- **Flight pivot / DD3 refinement**: leg 2 added `WebSearchConfig` (`search_backend`
  dropdown + 5 per-engine fields, 3 secret-marked); leg 3 made the API mask secrets on GET
  and preserve-on-masked on PUT + encrypt at rest. This leg is the **UI half** — the
  rendering + interaction that consumes that contract. No backend/persistence change.
- **Codebase facts (verified — Explore):**
  - **Form serialization already handles hidden fields**: `tools-editor.js:225-238`
    `getFormSnapshot` collects every `[data-field]` via `querySelector` regardless of CSS
    visibility, so a masked-but-untouched secret (hidden or shown) is sent as-is →
    leg-3's `_looks_masked` PRESERVE fires. **No submit-path change needed.**
  - **`renderField`** (`tools-form-helpers.js:59-256`) dispatches on `ftype` + `prop.ui_hint`
    and returns a static HTML string; the **password branch inserts between the `array`
    block (:236) and the plain `string` block (:237)** as `ftype==='string' &&
    hint==='password'`. Element ids `tef-{field}`, `data-field="{field}"`, row
    `data-field-name`, `aria-describedby` already wired.
  - **No post-render hook inside `renderField`** — event listeners are attached by the
    caller in **`tools-editor.js` `wireEvents` (~:240-302)** after render (it already wires
    `input`/`change` dirty-tracking on `input[data-field], select[data-field]` and chip-list
    editors). The eye-toggle + dropdown-change show/hide handlers go here.
  - **No conditional-visibility mechanism exists** — `show_if` is NEW. `json_schema_extra`
    flattens into each schema property (same path `ui_hint`/`ui_choices`/`secret` already
    take via `model_json_schema()` → GET `/tools/configs/{name}` `schema`), so a
    `json_schema_extra={"show_if": {...}}` surfaces as `prop.show_if` in JS
    (`tools-editor.js:98-100` unpacks `schema.properties`).
  - **Eye-toggle precedent to port**: `provider-editor.js:155-157` (button markup) +
    `:236-251` (click handler: toggle `type` password↔text, swap `eye`/`eye-off` icon, swap
    `aria-label` "Show password"/"Hide password"). Uses `.api-key-eye` / `.api-key-wrap`
    classes + `is-hidden` (CSS `display:none`) for hide.
  - **Dropdown-change precedent**: `provider-editor.js:222-234` toggles `is-hidden` rows on
    a type-`<select>` change. The tools editor has NO such handler yet.
  - **Frontend tests**: Playwright via pytest, `tests/browser/`, `make test-browser`
    (`THE_ONE_DEV_MODE=true`). Precedents: `test_flow_provider_editor.py` (eye-toggle, render
    + reveal), `test_flow_admin_openrouter.py` (type-change show/hide), `test_flow_admin_tools_editor.py`
    (tools form save/cancel/validation).
- **Studio parity — RESOLVED (design review): NOT applicable.** The form renders in two
  places (`tools-editor.js:153` admin, `studio/tools-tab.js:401` agent-mode), but
  `renderField` early-returns `''` in agent mode for any non-boolean field lacking a
  resolver marker (`tools-form-helpers.js:71-82`), and ALL `WebSearchConfig` fields are
  markerless `str` (operator-only by design). So Studio renders "No constraints to narrow."
  for web_search and NEVER shows a password/conditional field. → the eye-toggle + `show_if`
  wiring lands ONLY in `tools-editor.js` `wireEvents`; no Studio change. **Forward-looking
  caveat**: if a future leg ever marks one of these fields `Substitute`/`Narrow`, agent-mode
  would start rendering it and would then need the wiring — out of scope now.

## Inputs
- Legs 2 & 3 landed: `WebSearchConfig` with secret-marked fields; API masks/preserves;
  GET returns masked secret values; the tools-admin form renders schema-driven.
- `tools-form-helpers.js` `renderField`; `tools-editor.js` `wireEvents`/`getFormSnapshot`.
- `_web_search_config.py` `WebSearchConfig` (5 per-engine fields to gain `show_if`).

## Outputs
- A `ftype==='string' && hint==='password'` branch in `renderField` → masked input +
  eye-toggle button (a11y aria-label), value pre-filled with the GET masked value.
- Generic `show_if` support: a field whose `prop.show_if` condition is unmet renders hidden
  (`is-hidden` + `aria-hidden="true"`); a change listener on the controlling field toggles
  visibility live + `checkDirty()`. Generic — any field controlled by any sibling.
- `show_if={"search_backend": "<engine>"}` on the 5 per-engine `WebSearchConfig` fields.
- Eye-toggle wiring in `wireEvents` (+ Studio tools tab if it renders the form — TBD review).
- Eye-toggle CSS (`.api-key-wrap`/`.api-key-eye`) available to the tools form.
- Browser tests (DOM/role-based, NOT pixel snapshots) for render/reveal/conditional/persist.

## Acceptance Criteria
- [x] A secret-marked field (`ui_hint:"password"`) renders as `<input type="password">`
      inside an eye-toggle wrapper; the eye button toggles the input between password/text,
      swaps the `eye`/`eye-off` icon, and swaps its `aria-label` "Show password"/"Hide
      password" (port the provider-editor pattern). Button is keyboard-operable
      (`type="button"`, focusable, not `aria-hidden`). — `renderField` password branch +
      `wireEvents` eye-toggle; `test_web_search_secret_field_masked_with_eye_toggle`.
- [x] The masked value returned by GET pre-fills the password input; leaving it untouched
      and saving PRESERVES the stored secret (leg-3 `_looks_masked`); typing a real value
      replaces it. Verified end-to-end (save → reload shows mask again). —
      `test_web_search_secret_persists_encrypted_and_reloads_masked` (asserts reload value is
      `***...{tail4}`, not plaintext).
- [x] Generic `show_if` conditional visibility: a field with `prop.show_if = {ctrlField:
      value}` is hidden (`is-hidden` class → `display:none`, AND `aria-hidden="true"` on the
      row) when `ctrlField`'s current value ≠ `value`, and shown otherwise. Applied on
      initial render AND live on the controlling field's `change`. Field rows stay in the
      DOM (not removed/re-added). `checkDirty()` runs on the change. — `applyShowIf` +
      controller `change` listeners in `wireEvents`.
- [x] The 5 `WebSearchConfig` per-engine fields carry `show_if` → `searxng_base_url`
      (searxng), `google_pse_api_key` + `google_pse_cse_id` (google_pse), `brave_api_key`
      (brave), `tavily_api_key` (tavily). Selecting an engine reveals exactly its fields and
      hides the others; DuckDuckGo shows none. — `_web_search_config.py` metadata;
      `test_web_search_show_if_reveals_only_selected_engine_fields`.
- [x] Switching engines does NOT lose an already-entered key (hidden fields remain in the
      payload via `getFormSnapshot`, so the value persists) — confirmed by a test. —
      `test_web_search_engine_switch_preserves_entered_key`.
- [x] The wiring lands in `tools-editor.js` `wireEvents` (admin) ONLY — Studio agent-mode
      never renders these markerless fields, so no Studio wiring (resolved at design review).
- [x] **`tests/browser/test_flow_admin_tools_editor.py` is updated** — it is ALREADY broken
      by legs 2-3 (asserts the old `WebConfig` fields `timeout_seconds_max`/`host_allowlist`/
      `default_user_agent` for `web_search`, which no longer exist on `WebSearchConfig`).
      Re-target its field-enumeration + save/cancel/dirty tests to the `WebSearchConfig`
      field set (e.g. `searxng_base_url`) and RE-HOME the 422-model-validator test (which
      relied on WebConfig's `timeout_seconds_default <= timeout_seconds_max` validator,
      gone) onto a still-`WebConfig` tool (`http_request`/`fetch_url`). NOTE: `make
      test-browser` is RED before this leg's new code — that pre-existing break is this
      leg's to fix; don't mistake it for a regression. — Re-homed to `fetch_url`; suite now
      19 passed.
- [x] a11y: WCAG 2.1 AA — eye-toggle aria-label state; hidden rows `aria-hidden`; focus
      order sane; existing error wiring (`aria-invalid`/`aria-describedby`/`role=alert`)
      unaffected. (Accessibility reviewer signs off at flight-end review.) — aria-label
      Show/Hide flip + `aria-hidden="true"` on hidden rows asserted in tests; error wiring
      untouched. Reviewer sign-off pending at flight-end review.
- [x] Browser tests (`tests/browser/`, DOM/role assertions — NOT pixel snapshots per the
      project's gitignored-baseline policy) cover: password render + eye reveal; engine
      selection show/hides the right fields; a saved key persists encrypted and reloads
      masked; engine-switch preserves an entered key. — all four covered; DOM/role only.
- [x] FULL unit suite green at/above the leg-3 baseline (3565); `make test-browser` green. —
      unit 3565 passed / 10 skipped / 0 failed; browser 19 passed.

## Verification Steps
- `make test-browser` (or `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser
  tests/browser/test_flow_admin_tools_editor.py -v --tb=short`).
- `make test-unit` once — still green (this leg is JS + a schema-metadata add; the
  `_web_search_config.py` `show_if` add may shift the field's schema — re-run the
  `WebSearchConfig` guard test from leg 2/3).
- Manual: open Administration → Tools → web_search; pick each engine; confirm fields
  appear/mask/reveal; save a Brave key; reload → masked; switch to Tavily and back → Brave
  key still there.

## Implementation Guidance
1. **Password branch** (`tools-form-helpers.js`, between :236 and :237). Mirror
   `provider-editor.js:155-157`: a `.api-key-wrap` div containing `<input id="tef-{field}"
   data-field="{field}" data-field-type="string" type="password" …>` + an `.api-key-eye`
   `<button type="button" aria-label="Show password">{eye icon}</button>`. **`data-field-
   type="string"` is load-bearing** — `readFieldValue` (`:318`) returns `inputEl.value` only
   when fieldType is `"string"`; without it the masked value won't round-trip. Keep
   `data-field`, `data-tool-override-tool`/`attrPrefix`, `aria-describedby`, error hooks
   identical to the string branch (so the branch is mode-agnostic).
2. **Eye-toggle handler** (`tools-editor.js` `wireEvents`). For each `.api-key-eye`, on
   click toggle the sibling input `type`, swap the icon (`window.App.icon('eye'/'eye-off')`),
   swap `aria-label`. Copy `provider-editor.js:236-251` — but select the input **by
   structure** (the input inside the same `.api-key-wrap`), NOT by `.admin-pf-password`
   (that class is provider-specific).
3. **Generic `show_if`** (`tools-editor.js`). A small `applyShowIf(container, properties)`:
   for each property with `show_if = {ctrl: val}`, find the field row; set hidden when the
   current value of `[data-field="ctrl"]` ≠ `val`. Call it once after render, and attach a
   `change` listener to each distinct controlling `[data-field]` that re-runs it +
   `checkDirty()`. Hide = add `is-hidden` + `row.setAttribute('aria-hidden','true')`; show =
   remove both. Keep it generic (read from schema, not hardcoded to search_backend).
4. **`show_if` metadata** (`_web_search_config.py`). Add `show_if` to each per-engine field's
   `json_schema_extra` (merge with the existing `ui_hint`/`secret` for the secret ones):
   e.g. `brave_api_key` → `{"ui_hint":"password","secret":True,"show_if":{"search_backend":"brave"}}`.
5. **CSS — none needed.** `.api-key-wrap`/`.api-key-eye` (`components.css:1063-1068`) and
   `.is-hidden` (`components.css:1236`) are GLOBAL/unscoped — they apply in the tools form
   already. Do NOT add new CSS.
6. **Studio: no wiring** (resolved — markerless fields never render in agent mode). Keep
   `applyShowIf`/eye-toggle in the admin `wireEvents`; do not add a Studio call site.
7. **Tests** (`tests/browser/`). DOM/role assertions only (NO pixel baselines). (a) ADD
   coverage for the new behaviors; (b) FIX the already-broken
   `test_flow_admin_tools_editor.py` (legs 2-3 changed `web_search`→`WebSearchConfig` but
   left this file asserting old WebConfig fields) — re-target field enumeration + save/
   cancel/dirty to `WebSearchConfig` fields and re-home the 422-validator test to a
   `WebConfig` tool. Follow `test_flow_provider_editor.py` (eye-toggle) +
   `test_flow_admin_tools_editor.py` shape. Optionally assert the 5 per-engine fields carry
   the expected `show_if` extra (locks the contract; the leg-2/3 guard only counts fields).

## Edge Cases
- **Two fields, one controller** (google_pse has key + cse_id): `applyShowIf` must handle
  multiple fields keyed to the same `search_backend` value.
- **Hidden field still submitted**: intended — preserves an entered key across engine
  switches; don't "fix" it by stripping hidden fields from the payload.
- **Masked value typed into a hidden field**: not reachable by the user (hidden), value is
  the GET mask → preserved. Fine.
- **No-secret / non-conditional tools**: `show_if` absent → field always shown (unchanged
  behavior); password branch only triggers on `ui_hint:"password"` (other tools unaffected).
- **Pixel/snapshot tests**: do NOT add committed-baseline pixel tests — the project gitignores
  snapshot baselines; use DOM-shape/role assertions as the regression net.

## Files Affected
- `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js` — password branch.
- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` — eye-toggle + generic
  `show_if` wiring in `wireEvents`.
- `the_one/tools/_web_search_config.py` — `show_if` on the 5 per-engine fields.
- _(No Studio change — markerless fields don't render in agent mode. No new CSS —
  `.api-key-wrap`/`.api-key-eye`/`.is-hidden` are global in `components.css`.)_
- `tests/browser/test_flow_admin_tools_editor.py` — FIX the legs-2/3 breakage (re-target to
  `WebSearchConfig` fields; re-home the 422-validator test) AND add render/reveal/conditional/
  persist coverage (DOM/role).
- Docs: note the web_search admin config (engine dropdown + masked keys) in the relevant
  user/admin doc.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (full unit suite + `make test-browser`)
- [ ] Update flight-log.md (password rendering, generic show_if, Studio parity outcome,
      browser-test results)
- [ ] Set this leg's status to `landed` (commit deferred to flight end)
- [ ] Check off this leg in flight.md
- [ ] (Not the final leg — do not land the flight here)
