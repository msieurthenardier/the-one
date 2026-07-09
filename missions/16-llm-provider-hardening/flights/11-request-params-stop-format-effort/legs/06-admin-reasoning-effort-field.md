# Leg: admin-reasoning-effort-field

**Status**: completed
**Flight**: [Request-Param Capabilities (A4)](../flight.md)

## Objective

Add a minimal `reasoning_effort` field to the Administration provider-config editor
(the `num_ctx` / `thinking_enabled` precedent) so the primary A4 knob is
operator-settable for the HAT — a `<select>` writing `config.reasoning_effort`,
shown for the reasoning-capable provider types, round-tripping through the existing
free-form config dict with **no** production Python change.

## Context

- **DD6**: admin exposure is minimal and scoped to provider config (not the chat
  surface the mission constraints fence off). Only `reasoning_effort` gets a field;
  `response_format` and `stop` stay config/env-only. **Droppable** to config/env-only
  if the operator prefers — this leg is deliberately small.
- **Depends on L02–L04** (the config keys are read by every provider `__init__`).
  This leg only adds the UI that writes `config.reasoning_effort`; the read side and
  wire mapping already exist and are tested.
- **Exact precedent to mirror** — two config-dict fields already in the editor:
  - `num_ctx`: `provider-editor.js` render (`data-field="config.num_ctx"`, number
    input, `.field-group` + info-icon), the type-change show/hide toggle
    (`~:301-304`), and the save-payload block (`~:610` `if (defaults.showNumCtx)`).
    Gated by `TYPE_DEFAULTS.ollama.showNumCtx` (`admin.js:183`).
  - `thinking_enabled`: render (`data-field="config.thinking_enabled"`, checkbox),
    toggle, save-payload block (`~:630` `if (defaults.showThinkingEnabled)`). Gated
    by `TYPE_DEFAULTS.anthropic.showThinkingEnabled` (`admin.js:186`).
- **Collection is generic**: `getFormSnapshot` (`provider-editor.js:228`) reads all
  `[data-field]` elements; a `<select>`'s `.value` is picked up automatically (it's
  not a checkbox). Save-payload construction, however, is **explicit per field**
  (`if (defaults.showX) { payload.config.X = ... }`) — so a new block is needed.
- **No schema/Python change**: `LLMProviderConfig.config` is a free-form dict
  (`db/models.py`); `reasoning_effort` rides it exactly like `num_ctx` /
  `thinking_enabled`. The provider `__init__`s already coerce+read it (L02–L04).

## Inputs

- `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` — the render
  block (`~:161-222` for the num_ctx + thinking fields), the type-change toggle
  (`~:301-304`), `getFormSnapshot` (`:228`), the save-payload builder (`~:600-640`).
- `the_one/interfaces/web/static/js/areas/admin.js` — `TYPE_DEFAULTS` (`:182-189`).
- The admin-editor asset test (`tests/test_tools_admin_editor_assets.py`) — the
  established pattern for hermetically asserting editor JS content.

## Outputs

- `provider-editor.js` — a `reasoning_effort` `<select>` field (render + toggle +
  save-payload block).
- `admin.js` — `showReasoningEffort: true` on the reasoning-capable `TYPE_DEFAULTS`.
- A hermetic asset-presence test for the new field.

## Acceptance Criteria

- [x] **Field renders**: `provider-editor.js` emits a `reasoning_effort`
      `<select>` with `data-field="config.reasoning_effort"`, gated by
      `defaults.showReasoningEffort` (hidden otherwise), following the `num_ctx`
      `.field-group` + label + info-icon structure. Options: a default/empty
      option (label like `Provider default`, value `""`) plus `low`, `medium`,
      `high`.
- [x] **Pre-fill on edit**: the select reflects `provider.config.reasoning_effort`
      when set, else the empty/default option.
- [x] **Type-gating**: `TYPE_DEFAULTS` (`admin.js`) gains `showReasoningEffort:
      true` for the reasoning-capable types — **anthropic, openai, openrouter,
      ollama, AND openai-compatible** (not mock). `openai-compatible` is **included**
      (design-review finding): `factory.py:122-129,283-284` maps it to the **same**
      `OllamaProvider` class as `ollama` (differing only by `native_api`), and
      `OllamaProvider.__init__` reads `config.reasoning_effort` unconditionally and
      applies it on both paths — so `reasoning_effort` is already functional for
      `openai-compatible`; excluding it from the UI would be an avoidable gap, not a
      capability boundary (unlike `num_ctx`, which is genuinely Ollama-native-only).
      The type-change handler shows/hides the row like the other config fields
      (`~:301-304`).
- [x] **Save round-trips**: the save-payload builder adds
      `payload.config.reasoning_effort` from the select when
      `defaults.showReasoningEffort` (mirror the `thinking_enabled` always-persist
      block). Persisting the empty string `""` is acceptable — the server-side
      `_coerce_effort("")` → `None` (falls through), so the round-trip is
      deterministic and harmless.
- [x] **No production Python change** and **no schema change**: `git diff --stat`
      shows only the two JS files + the test (+ flight artifacts); no `the_one/**`
      `.py`, no migration.
- [x] **Hermetic test**: a source-content test asserts the field markup
      (`data-field="config.reasoning_effort"`, the `<select>` + the low/medium/high
      options) is present in `provider-editor.js` AND that `admin.js` `TYPE_DEFAULTS`
      carries `showReasoningEffort` for the reasoning-capable types. **Use the
      `Path.read_text()` scan idiom** from `tests/_ui_guard_helpers.py` /
      `tests/test_ui_guards.py` (a plain read-and-substring-assert over `JS_DIR`) —
      NOT the heavier `test_tools_admin_editor_assets.py` machinery (that spins up a
      full FastAPI app + SQLite + `AsyncClient` to verify a *newly-mounted* asset is
      wired into the SPA shell; these files are already served, so that overhead is
      unwarranted here — design-review finding).
- [x] Targeted tests green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      tests/test_tools_admin_editor_assets.py -x --timeout 30` (+ whatever file the
      new test lands in), and `make test-unit` shows no regression.

## Verification Steps

- Run the asset test file — green, incl. the new reasoning_effort assertions.
- `git diff --stat` — only `provider-editor.js`, `admin.js`, and the test file (+
  flight artifacts); no Python/schema changes.
- Read the render + save + TYPE_DEFAULTS diffs — confirm the field mirrors the
  num_ctx/thinking_enabled structure and is gated to the reasoning-capable types.
- (Behavioral round-trip through a live browser is the **L07 HAT**, not this leg.)

## Implementation Guidance

1. **Render** (`provider-editor.js`, next to the num_ctx/thinking blocks): build a
   `.field-group admin-pf-reasoning-effort` row (mirror `admin-pf-num-ctx`'s
   structure — label + info-icon + control), hidden when `!defaults.showReasoningEffort`.
   Control:
   ```html
   <select class="field-input field-select admin-pf-input admin-pf-select"
           id="pf-reasoning-effort" data-field="config.reasoning_effort">
     <option value="">Provider default</option>
     <option value="low">low</option>
     <option value="medium">medium</option>
     <option value="high">high</option>
   </select>
   ```
   Pre-select from `provider.config.reasoning_effort` (mark the matching option
   `selected`; use the same `escapeAttr` helpers the file already uses). Info-icon
   copy: something like "Guides how much the model reasons before answering
   (reasoning-capable models). Leave on Provider default to omit."
2. **Type-change toggle**: add a `reasoningEffortRow` lookup + a
   `classList.toggle('is-hidden', !defaults.showReasoningEffort)` line alongside the
   existing `numCtxRow`/`thinkingEnabledRow` toggles (`~:301-304`).
3. **Save-payload block** (`~:630`, after the thinking_enabled block):
   ```js
   if (defaults.showReasoningEffort) {
     var reInput = container.querySelector('[data-field="config.reasoning_effort"]');
     payload.config = payload.config || {};
     payload.config.reasoning_effort = reInput ? reInput.value : '';
   }
   ```
   (Always-persist, matching thinking_enabled — deterministic round-trip; `""`
   coerces to `None` server-side.)
4. **`TYPE_DEFAULTS`** (`admin.js:182-189`): add `showReasoningEffort: true` to
   `anthropic`, `openai`, `openrouter`, `ollama`, **and `openai-compatible`** (it
   shares OllamaProvider's reasoning_effort path — see criteria). Leave `mock`
   untouched.
5. **Test**: add a source-content test using the `Path.read_text()` scan idiom from
   `tests/_ui_guard_helpers.py` / `tests/test_ui_guards.py` (add to
   `test_ui_guards.py` or a sibling) — read `provider-editor.js` + `admin.js` and
   assert the field markup (`data-field="config.reasoning_effort"`, the `<select>`,
   the `low`/`medium`/`high` option values) and the `showReasoningEffort` flags.
   Do NOT use the FastAPI-app/`AsyncClient` fixture of
   `test_tools_admin_editor_assets.py`.

## Edge Cases

- **Existing providers without the key**: `provider.config.reasoning_effort` is
  undefined → the empty/default option is selected → nothing sent → provider uses
  env/default. Backward-compatible.
- **A persisted `""`**: harmless — `_coerce_effort("")` → `None`. The select shows
  "Provider default". Deterministic round-trip.
- **Exotic effort values** (`xhigh`/`max`/`minimal`/`none`): intentionally NOT in
  the select (minimal UI, DD6). Operators needing them use `config`/env directly;
  the canonical layer accepts them there. Note this in the info-copy or the leg log,
  not as a UI affordance.
- **Droppable**: if the operator decides during review they'd rather keep
  reasoning_effort config/env-only, this whole leg drops with no impact on L02–L05
  (the read/wire path is independent). Record that if it happens.

## Files Affected

- `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` — render +
  toggle + save block.
- `the_one/interfaces/web/static/js/areas/admin.js` — `TYPE_DEFAULTS` show flags.
- Admin-editor asset test — new reasoning_effort assertions.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (asset test + `make test-unit` regression)
- [x] Update flight-log.md with a Leg Progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] **Last autonomous leg** — but do NOT set flight → landed or check the flight
      off in mission.md here: that happens at the post-L06 batch review + commit
      (Phase 2d), and only after L07 (the optional HAT) is dispositioned.
- [x] Changes stay uncommitted — batch commit after this leg's review (do NOT commit)
