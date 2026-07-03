# Leg: thinking-enable-admin-field

**Status**: completed
**Flight**: [Extended-Thinking / Reasoning Support (A1)](../flight.md)

> **★ Reshaped by the 2026-07-02 adaptive pivot** (was `thinking-budget-admin-field`). Adaptive
> mode has no token budget, so the operator control is a simple **on/off toggle**, not a number.
> It writes the boolean `config["thinking_enabled"]` that Leg 03's resolver already reads.

## Objective

Add a Studio provider-editor **on/off "Extended thinking" toggle**, gated to the **Anthropic**
provider type, default **off**, that reads/writes the boolean `config["thinking_enabled"]` —
mirroring the F09-05 `num_ctx` field end-to-end (render, type-gate, collect, round-trip) as a
checkbox instead of a number input.

## Context

- Legs 01–05 landed: the backend reads `config["thinking_enabled"]` via `_coerce_bool`
  (`anthropic_provider.py:71–89`, `:135–137`) → `resolve_extended_thinking` → adaptive
  enablement. This leg is the **operator surface** for that key; no backend/provider change.
- **Off by default** (matches the flight's off-by-default decision): a fresh Anthropic provider
  has thinking disabled; the operator opts in with the toggle. The behavior-test disabled variant
  (Leg 07) is a real regression guard that the toggle truly gates enablement.
- **Anthropic-only (DD5).** The toggle shows for the `anthropic` provider type only. OpenRouter
  (even routing to Anthropic models) is out of scope this flight — no toggle there.
- **F09-01/07 config convention.** The value rides the free-form `config` dict (like `num_ctx`,
  OpenRouter `referer`/`title`), persisted opaquely by the API; `model_copy(update=data)`
  (`api.py:4031`) preserves unrelated config keys across an edit. The `__MASKED__` API-key
  sentinel handling is untouched.
- **Key drift from `num_ctx`:** `num_ctx` is a required positive-integer number input;
  `thinking_enabled` is a **checkbox → native `.checked` bool** — no client-side numeric
  validation/coercion, and the backend's `_coerce_bool` leniently accepts a bool or a stray
  `"true"`/`"1"` string from a JSON round-trip.

## Inputs (current hook points — verified 2026-07-02)

- `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` — the `num_ctx` field is the
  template: **render** (`:160–178`, `data-field="config.num_ctx"` + label + info-icon +
  visually-hidden desc), **populate-on-edit** (`:169`, reads `provider.config.num_ctx`),
  **type-change toggle** (`:242–256`, toggles `.admin-pf-num-ctx` via `is-hidden` on
  `defaults.showNumCtx`), **collect-on-save** (`:536–550`, reads the field, attaches to
  `payload.config`). The type dropdown is `#pf-type` / `data-field="type"` (`:131–141`).
- `the_one/interfaces/web/static/js/areas/admin/admin.js` — `TYPE_DEFAULTS` (`:182–189`);
  `'ollama'` has `showNumCtx: true`; `getTypeDefaults(type)` (`:344`).
- `the_one/interfaces/web/api.py` — `create_provider` (`:3985–4004`), `update_provider`
  (`:4007–4042`, merge at `:4031`); config flows through opaquely.
- `the_one/db/models.py` — `LLMProviderConfig.config: dict` (`:29`, no schema — any key flows).
- `the_one/llm/anthropic_provider.py` — `_coerce_bool` (`:71–89`) + `__init__` read
  (`:135–137`), **already present** (Leg 03) — nothing to change here.
- `tests/browser/test_flow_provider_editor.py` — the `num_ctx` field tests (`:213–257`) are the
  browser-test template. `tests/test_provider_api.py` — the config-persistence API test template.

## Outputs

- `provider-editor.js` — a checkbox "Extended Thinking" field (render + populate + collect),
  gated on `defaults.showThinkingEnabled` via a `.admin-pf-thinking-enabled` row.
- `admin.js` — `showThinkingEnabled: true` on the `'anthropic'` `TYPE_DEFAULTS` entry (only).
- `tests/browser/test_flow_provider_editor.py` — toggle visibility/gating/default/a11y/dirty +
  persistence.
- `tests/test_provider_api.py` — `config.thinking_enabled` create + masked-key-update round-trip.
- No backend/provider change (config passthrough + `_coerce_bool` read already exist).

## Acceptance Criteria

- [x] The provider editor shows an **"Extended thinking"** checkbox (`data-field=
      "config.thinking_enabled"`) **only when the provider type is `anthropic`** — hidden for
      ollama/openai/openai-compatible/openrouter/mock. Gated via `showThinkingEnabled: true` on the
      `anthropic` `TYPE_DEFAULTS` entry + the type-change handler toggling
      `.admin-pf-thinking-enabled`.
- [x] Default **unchecked** (off) for a new Anthropic provider; when editing an existing provider
      it reflects the stored `provider.config.thinking_enabled` (checked iff truthy).
- [x] On save, the checkbox's native boolean state is written to `payload.config.thinking_enabled`
      (a real `bool`, not a string) — collected only when the field is shown (anthropic).
- [x] Backend round-trip: creating an Anthropic provider with the toggle on persists
      `config.thinking_enabled == true` (GET returns it); editing (PUT) with a masked API key keeps
      the stored api_key and round-trips `thinking_enabled`. (Note: `model_copy(update=data)`
      replaces the `config` dict wholesale — the client re-collects the full anthropic config on
      save, so preservation of any other config keys is a client-re-send property, not a backend
      nested merge; the test seeds a second key in the PUT body to prove the round-trip.)
- [x] End-to-end wiring: an Anthropic provider saved with the toggle ON produces an adapter whose
      `resolve_extended_thinking(self._thinking_enabled_config)` is True (the value the toggle
      writes is the exact key Leg 03 reads). No backend change needed — assert the key contract
      only. (Verified via grep: `anthropic_provider.py:135-136` reads `config["thinking_enabled"]`
      via `_coerce_bool`, `:175` feeds it to `resolve_extended_thinking`.)
- [x] Accessibility mirrors the `num_ctx` field: a real `<label for=…>`, and a description via the
      focusable info-icon + `aria-describedby` + visually-hidden span (or the project's existing
      checkbox-field a11y idiom — see guidance). Keyboard-toggleable.
- [x] Dirty-tracking works for the checkbox: toggling it marks the form dirty (Save flips from
      `disabled` to enabled) and Cancel reverts it. This REQUIRES making the provider-editor's
      `getFormSnapshot`, change-listener wiring, and Cancel-revert checkbox-aware (they are
      `.value`-based today — a checkbox is invisible to them without the patch; see guidance 4b).
- [x] Browser provider-editor suite + provider-API suite green; full unit suite green minus the
      known aiosqlite flake. No regression to the `num_ctx` field or the masked-key handling.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_flow_provider_editor.py -m browser -x --timeout 60`
  — the new toggle tests pass; existing `num_ctx` tests still pass.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_provider_api.py -x --timeout 30`
  — the `config.thinking_enabled` create + masked-update round-trip test passes.
- Manual/HAT (Leg 07): open the Anthropic provider editor, toggle Extended thinking on, save,
  reopen — the toggle is on and thinking activates in chat.
- `make test-unit` once at leg end — green minus the known teardown flake.

## Implementation Guidance

1. **Checkbox idiom (confirmed to exist — mirror it).** The admin checkbox idiom is
   `class="checkbox-primary" type="checkbox"` with a `checked` attr (`tools-form-helpers.js:137`),
   read via `readFieldValue` which does `if (inputEl.type === 'checkbox') return inputEl.checked;`
   (`:362`), with the label + `field-info-icon` + `aria-describedby` + visually-hidden-span a11y
   pattern. Mirror this **markup + a11y**. **CRITICAL:** the tools-editor that hosts that idiom has
   its OWN checkbox-aware snapshot; the **provider-editor does NOT** — so the markup transfers but
   the dirty-tracking does NOT. You must ALSO patch the provider-editor's snapshot/listener/revert
   (step 4b below) or the toggle will render + save but never mark the form dirty.

2. **Render the field** in `provider-editor.js` just after the `num_ctx` block (`~:178`), inside
   the connection-fields builder, wrapped in `<div class="field-row admin-pf-row
   admin-pf-thinking-enabled' + (defaults.showThinkingEnabled ? '' : ' is-hidden') + '">`:
   - `<label for="pf-thinking-enabled">Extended thinking</label>`
   - `<input type="checkbox" id="pf-thinking-enabled" class="field-input checkbox-primary"
     data-field="config.thinking_enabled" …>`, `checked` iff `(!isCreate && provider.config &&
     provider.config.thinking_enabled)`. **The `field-input` class is required** so the existing
     change/input listener (`:233`, bound to `.field-input, .field-select`) attaches;
     `checkbox-primary` matches the admin checkbox styling.
   - An info-icon + visually-hidden desc, e.g. *"When on, the model reasons step-by-step before
     answering (adaptive thinking). Requires Claude Sonnet 4.6 or newer."*

3. **Gate by type** — in `admin.js` add `showThinkingEnabled: true` to the `'anthropic'`
   `TYPE_DEFAULTS` entry (`:182–189`), and in `provider-editor.js`'s type-change handler
   (`:242–256`) grab the `.admin-pf-thinking-enabled` row and
   `row.classList.toggle('is-hidden', !defaults.showThinkingEnabled)` (mirror the `numCtxRow`
   line). Ensure it also renders correctly on initial edit-load of an existing anthropic provider.

4. **Collect on save** — in the collect phase (`~:536–550`, after the `num_ctx` block), when
   `defaults.showThinkingEnabled`:
   ```javascript
   var teInput = container.querySelector('[data-field="config.thinking_enabled"]');
   payload.config = payload.config || {};
   payload.config.thinking_enabled = !!(teInput && teInput.checked);
   ```
   Always persist the explicit bool (matches `num_ctx`'s always-persist; makes the edit round-trip
   deterministic). No numeric validation.

4b. **Patch the checkbox-blind dirty machinery (design-review [high] — do NOT skip).** The
   provider-editor's snapshot/listener/revert are `.value`-based and ignore `.checked`. A checkbox
   toggle would leave the form "clean" (Save disabled) and Cancel wouldn't restore it. Three edits
   in `provider-editor.js`:
   - **`getFormSnapshot` (`:183–190`)** — currently `data[field] = fields[i].value`. Change to
     read checkbox state: `data[field] = el.type === 'checkbox' ? el.checked : el.value;`.
   - **Listener wiring (`:233`)** — the `field-input` class on the checkbox (step 2) makes the
     existing `.field-input, .field-select` listener attach; verify the listener fires on the
     checkbox `change`/`input` event (add an explicit `change` listener only if it doesn't).
   - **Cancel-revert (`:288–292`)** — currently sets `.value`; make it set `.checked` for checkbox
     fields (`el.type === 'checkbox' ? el.checked = <snap bool> : el.value = <snap>`).
   These three are the load-bearing fix; the render + collect steps alone are insufficient.

5. **No backend change.** `config` is opaque (`models.py:29`); `create`/`update` pass it through;
   `_coerce_bool` (`anthropic_provider.py:71`) already reads `thinking_enabled`. Confirm with a
   grep that nothing else needs touching.

6. **Tests:**
   - **Browser** (`test_flow_provider_editor.py`, mirror `:213–257` + the single-toggle precedent
     `test_flow_studio_per_agent_admit_dms.py` using `to_be_checked()`/`not_to_be_checked()`):
     (a) toggle visible + unchecked by default when type=anthropic; (b) hidden
     (`.admin-pf-thinking-enabled.is-hidden`) for a non-anthropic type; (c) info-icon tooltip +
     `aria-describedby` a11y; (d) **toggling the checkbox flips the Save button from `disabled` to
     enabled** (this directly guards the [high] dirty-machinery fix — it fails loudly if the
     snapshot patch is omitted); (e) save with toggle on then reopen → checked (edit-load reflects
     the stored value); (f) Cancel after toggling reverts the checkbox.
   - **API** (`test_provider_api.py`, mirror `test_update_preserves_masked_key:203`): POST an
     `anthropic` provider with `config={"thinking_enabled": true}` → GET returns
     `config.thinking_enabled == true`. For non-clobbering: PUT with a **masked api_key** and
     `config={"thinking_enabled": true, "num_ctx": 4096}` (both keys present in the body, since
     `model_copy(update=data)` replaces the `config` dict **wholesale** — preservation is a
     client-re-send property, not a backend merge) → GET returns both keys, and the stored api_key
     is unchanged.

## Edge Cases

- **Type switch away from Anthropic mid-edit.** The toggle hides; its value is not collected for a
  non-anthropic type (mirrors how `num_ctx` isn't collected off-Ollama). Switching back shows it
  again with the loaded value (don't clobber on hide — mirror the base_url/api_key
  "preserve across type switch" behavior).
- **Legacy Anthropic providers with no `thinking_enabled` key.** Populate → unchecked (off);
  `_coerce_bool(None)` → None → resolver default off. Byte-compatible with pre-flight configs.
- **Stray `thinking_budget` key from the superseded design.** No persisted configs are expected
  (the budget UI never shipped), but if one exists it is simply ignored (backend no longer reads
  it); the operator re-enables via this toggle. (Recorded in the Leg 03 edge notes.)
- **Checkbox serialization.** `.checked` yields a native bool; it must reach the backend as JSON
  `true`/`false`. If the form's serializer stringifies it, `_coerce_bool` still parses it — but
  prefer sending a real bool.

## Files Affected

- `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` — checkbox render + populate +
  type-toggle + collect, **AND the checkbox-aware dirty machinery** (`getFormSnapshot` `:186`,
  listener wiring `:233`, Cancel-revert `:288–292`).
- `the_one/interfaces/web/static/js/areas/admin/admin.js` — `showThinkingEnabled` on the anthropic
  `TYPE_DEFAULTS` entry.
- `tests/browser/test_flow_provider_editor.py` — toggle tests.
- `tests/test_provider_api.py` — config round-trip test.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (browser provider-editor + provider-API + full unit suite green minus known
      teardown flake)
- [x] Update flight-log.md with the Leg 06 progress entry
- [x] Set this leg's status to `landed` (NOT `completed` — commit deferred to Phase 2d)
- [x] Do NOT commit; do NOT check off in flight.md; do NOT touch mission.md
- [x] Signal `[HANDOFF:review-needed]`
