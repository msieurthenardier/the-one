# Flight: System / Admin Re-skin

**Status**: landed
**Mission**: [UI Redesign — Clean, Professional, Consistent](../../mission.md)

## Contributing to Criteria

> Boxes stay unchecked — mission-end gates. Annotations record F6's share; F7 closes the sweep.

- [ ] SC1 — visual-language replacement (System surfaces to vocabulary; badge eyebrows quieted) — **F6 share:** all System surfaces (providers grid+editor+Ollama panel, tools grid+editor, General page) render the v3 quiet vocabulary; badge/subtitle eyebrows quieted (mono/uppercase/letter-spacing dropped via area-scoped override, per-type ink preserved); 0 alien remnants across the admin surface. The one `.cap-chip` cross-area eyebrow survivor (shared admin/studio markup — an area-scoped quiet would split the shared vocabulary) is **deferred to F7's cross-area sweep**, not omitted.
- [ ] SC3 — one component vocabulary (System consumes it; `.admin-pf-row`→`.field-group`; `.section-title` overload resolved) — **F6 share:** System consumes the shared vocabulary with no per-area variants; the 6 `.admin-pf-row` provider rows + the `.tools-editor` rows (shared `renderField`, both lanes) migrated to `.field-group`; the two `.area-admin` gutter exceptions retired (dead `.field-description` rule deleted, `.field-error` label-gutter folded into the base); the `.section-title` two-role overload resolved by DOCUMENTING the element-scoped convention (gallery note; no restyle, chat lane untouched).
- [ ] SC5 — keyboard/AT operability (provider/tool editors keyboard-operable; the shared chip-list `label[for]` dangle fixed systemically) — **F6 share:** provider + tool editors keyboard-operable with visible focus (both themes); the shared chip-list `label[for]` runtime-dangle **CLOSED systemically** (`options.controlId` on the real `.chip-list-input`, mcp-server-editor placeholder-div repoint) — fixing admin tools **and all studio chip-list consumers** at once — carried by a new runtime DOM guard (`test_flow_chiplist_label_resolver.py`) that a static source-scan provably can't cover.
- [ ] SC7 — behavior-verified core flows (system-provider-config spec authored + run) — **F6 share:** the `system-provider-config` behavior gate **PASSED both themes, 20/20** (light 10/10, dark 10/10; run log `tests/behavior/system-provider-config/runs/2026-07-06-02-37-37.md`) — the full-UI provider create/edit/test/delete flow witnessed on the re-skinned admin surface. The green System down-payment on the mission-end SC7.

---

## Pre-Flight

### Objective

Re-skin the System area (labeled "System"; area id `admin`) — the General page, LLM Providers grid + editor (+ Ollama models panel), and Built-in Tools grid + editor — to the v3 quiet vocabulary. Migrate the provider-editor + tools-editor label-left rows to `.field-group`; retire the `.area-admin .field-error`/`.field-description` gutter exceptions (admin.css:445/:461 — the twin F5 retired studio-side); quiet the badge mono/uppercase eyebrow survivors; resolve the `.section-title` two-role overload; fix the shared chip-list `label[for]` runtime-dangle systemically (admin + all studio consumers) with a runtime guard companion; add composite-a11y gates for the two danger-on-soft-fill surfaces; and verify with a fresh system-provider-config behavior spec. This is the LAST surface.

### Open Questions

- [x] `.section-title` two-role rename → Design Decisions (targeted split, minimal cross-area churn)
- [x] Chip-list `label[for]` dangle — fix here or defer to F7? → Design Decisions (fix here in the shared helper — F6 is already in tools-form-helpers)
- [x] Badge mono/uppercase eyebrows — quiet or keep? → Design Decisions (quiet to vocabulary)

### Design Decisions

**Consume the vocabulary directly, no per-area variants** (SC3): System grids/tiles → the F3 `.entity-tile` + `.btn-*`; tabs → F3 tabs; modals → dialog.js; badges → the F4-gated per-badge-ink badges; forms → `.field-group`/`.field-input`/`.field-select` + the shared `.field-group-label`; banners → the `components.css` `banner banner-warning`/`-error` primitives (already used). admin.css is already 0-alien for effects; this flight replaces the remaining per-area treatments (badge eyebrows, gutter exception, overloaded section-title) with vocabulary, not new CSS.

**`.admin-pf-row` + tools-editor rows → `.field-group`** (F5 playbook): the 6 provider-editor `.admin-pf-row` sites (provider-editor.js:126-208: Name/Type/Base URL/API Key/num_ctx/thinking) + the tools-editor enabled-row (tools-editor.js:216) + the shared renderField emitter (leg 3) migrate to stacked `.field-group` with full label-association. **GREP TO REAL RENDER SITES first** (F5 lesson ~1.4×; survey confirmed 6 provider real). **AC INVARIANT — preserve the `.admin-pf-{base-url,api-key,num-ctx,thinking-enabled}` row-marker classes** on the migrated `.field-group` rows (or migrate the selectors in lockstep): `wireEditorEvents` toggles `is-hidden` by those exact classes on provider-type change (provider-editor.js:278-289) — dropping them silently breaks the type-driven field show/hide. The `thinking_enabled` toggle (js:200-208, a `.tool-enable-switch` label-left toggle) + `num_ctx` stay as a **documented label-left toggle exception** (F5 chrome-row precedent) if stacking reads worse — default to stacking the text fields, keep the toggle label-left. **Gutter retirement — SPLIT the two rules**: `.field-description` gutter (admin.css:461) is ALREADY DEAD (no render site emits `.field-description` — renderField replaced it with the info-icon tooltip) → trivial dead-rule delete (confirm no render site). `.field-error` gutter (:445) → retire after the real `.field-row` sites migrate (verify last-consumer like F5), simplifying the `.area-admin .field-group .field-error {margin:0}` escape (:454) to the base rule.

**Shared tools-form-helpers migration is CROSS-AREA** (admin + studio): `tools-form-helpers.js:298 renderField` emits `.field-row.tools-editor-field` consumed by exactly TWO call sites — admin `tools-editor.js:153` AND studio `tools-tab.js:415` (the other studio chip-list consumers use `renderChipListEditor` DIRECTLY, not `renderField`). So it's a 2-path change — realistic in one leg, no transitional wrapper needed; re-verify the `studio` AND `system` lanes after. **AC INVARIANT — do NOT drop `.tools-editor-field` or `data-field-name`** on the migrated emitter: `renderFieldErrors`' selector is `.tools-editor-field[data-field-name=…], .field-row[data-field-name=…]` (tools-form-helpers.js:552), used by both lanes — dropping the marker silently breaks 422-error rendering in BOTH. Keep the marker classes on the `.field-group` rows.

**Chip-list `label[for]` runtime-dangle — fix systemically here + add a RUNTIME guard** (F5 carry-forward): the TRUE mount-time strip is in `mcp-server-editor.js` (wires `for="mf-{name}"` on a PLACEHOLDER `<div id="mf-{name}">` that `mountChipListEditors` replaces via `outerHTML=`, stripping the id). A `<div>` is NOT a labelable element, so `label[for]` must target the real focusable `.chip-list-input`, not the wrapper. **Fix**: add an `options.controlId` param to the shared `renderChipListEditor`, land it as `id` on the `.chip-list-input`; `renderField` passes `idAttr`; `mcp-server-editor` passes `mf-{name}` and DROPS the placeholder-div id (its post-mount selectors key on `[data-field="args"].chip-list-editor`, not the id — verified js:857/873 — so dropping is safe). **Enumerate the mcp-server-editor repoint explicitly in the leg AC** — it's the actual runtime-strip site, on a different label convention than the renderField path. This fixes admin tools + ALL studio chip-list consumers at once. **Add a RUNTIME DOM guard in `tests/browser/`** (a Playwright flow — pattern precedent `test_flow_studio_per_agent_overlay_label_resolver.py` — driving a mount and asserting via `page.evaluate` that `label[for=X]` resolves to a real element) — NOT in the static `tests/test_ui_guards.py` (that's the source-scan guard that provably can't catch the mount strip). Update DYNAMIC_SINK_BASELINE for any new markup sites.

**`.section-title` two-role resolution — DOCUMENT the convention, do NOT restyle** (mission Open Question; architect-corrected): the class is worn by BOTH a section-heading role (`h2.section-title`, larger font) AND a quiet standalone-label role (`<label class="section-title">` chat.js:136; `<div class="section-title">` admin). It ALREADY renders correctly element-differentiated (components.css:435 `h2.section-title` heading bump; everything else body-sm quiet-label), and **F3 deliberately deferred the rename as "churn without payoff"** (comment at components.css:427-434). Nothing is visually broken. **Resolution — close the SC3 item by DOCUMENTING the element-scoped convention** (add a design-gallery note; the CSS comment already records it) and recording that the overload is intentional and element-handled. Do NOT touch `chat.js:136` (dragging the CHAT lane into an admin flight for zero payoff), do NOT introduce a new quiet-label recipe, do NOT migrate the correctly-rendering `div.section-title` uses. This keeps the chat lane out of F6's blast radius. (Folds into the general leg — no separate section-title work.)

**Quiet the badge eyebrow survivors** (SC1): `.admin-provider-badge` (admin.css:82), `.admin-tool-badge` (:168), `.editor-subtitle-meta` (:296), `.cap-chip` (:137) carry mono + uppercase + letter-spacing (v2-eyebrow survivors). Quiet to the vocabulary badge/label style (drop mono/uppercase/letter-spacing; keep the per-badge-ink color coding). `.telemetry-value` is gallery-only (dev Design Language) — quiet if trivial, else note.

**Composite-a11y gates — the pair is ALREADY gated at the token level; do NOT re-gate per surface** (architect-corrected — this IS the promoted invariant): both admin danger-on-soft-fill surfaces — `.cap-chip-no-tools` (admin.css:138) and `.editor-error-banner` (:589) — consume the EXACT `--status-danger` text on `--status-danger-bg-soft` pair that `test_design_tokens_a11y.py::test_danger_text_on_soft_fill_passes_body_aa` (line 265) already gates over each ladder surface, both themes, with no novel color/alpha. The whole point of the promoted invariant is to gate the pair ONCE at definition and stop rediscovering per surface. **So: CONFIRM both surfaces consume the already-gated pair (they do, by construction); optionally add a cheap source-grep guard pinning that usage — NO new `_alpha_composite` math.** A fresh gate is warranted ONLY if a surface introduces a novel fg/bg/alpha triple; neither does. The tool-switch + LEDs + badges are already gated.

**system-provider-config SC7 spec — author + RUN synchronously via chrome-devtools** (F5 apparatus lesson): author `tests/behavior/system-provider-config.md`. Precondition: 8485 dev-mode (the `mock` provider type is dev-gated-available; it's cred-less — `showApiKey:false, showBaseUrl:false` — so the dev-mode create form is **name + type only**, a clean deterministic witness). Steps — DRIVE THE FULL UI CREATE (not the `seed_mock_provider` API helper — the point is to witness the flow): Providers grid → `new-provider-btn` → provider editor: fill name + type=Mock(dev) → `save-provider-btn` → provider appears in grid as a `provider-card` → edit + Test Connection (`test-connection-btn`) → delete (`delete-provider-btn` — the agent-usage pre-gate + two-step confirmDelete armed state is a judged a11y checkpoint, like F5's Danger Zone). Both themes. **RUN via chrome-devtools** (multi-step seed+drive; goldfinch wedges + lacks ignoreCache reload), synchronous sub-orchestrator, WELL before the commit boundary (sync crews run ~60-90 min). Clean up seeded provider.

**Independent a11y review at flight close** (F5 lesson — its biggest wins came from the second independent a11y pass): the verification leg's batch review includes a separate Accessibility Reviewer gating the label-association migrations, the chip-list runtime fix, the composite surfaces, and keyboard-operability of the provider/tool editors. The `system` browser lane already exists (scripts/run-tests.sh: `system_pat=('test_flow_admin_*' 'test_flow_provider_*')`) — verification runs it plus the cross-area `studio` + `chat` lanes.

### Prerequisites

- [x] Flights 1-5 completed (vocabulary + all other surfaces live)
- [x] Admin/system surface surveyed (submodule map, .admin-pf-row sites, gutter exception, section-title overload, chip-list dangle location, provider-config testids, mock-provider availability)
- [x] 8485 dev instance; mock provider type available in dev mode

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Providers surface → tools surface (admin-only parts) → the shared tools-form-helpers migration + chip-list fix (cross-area, both-lane verified) → general page + section-title resolution + gutter-exception retirement (cross-area section-title, chat-lane verified) → verification (suites via lanes, dual-theme visual pass, the SC7 provider-config gate run via chrome-devtools). Composite gates + label-association at each editor's leg.

### Checkpoints

- [x] Providers surface (grid + editor + models) to vocabulary, .admin-pf-row migrated, badge eyebrows quieted, cap-chip-no-tools gate
- [x] Tools surface (grid + editor) to vocabulary, editor-error-banner gate, tool-badge quieted
- [x] Shared tools-form-helpers → .field-group + chip-list label[for] fix + runtime guard; BOTH studio + system lanes green
- [x] General page to vocabulary; section-title two-role resolved (targeted); .area-admin gutter exceptions retired; chat lane green
- [x] Suites green (via lanes); dual-theme visual pass; ledger — DONE (Leg 5). system-provider-config SC7 gate spec AUTHORED (Leg 5); the gate **RUN PASSED both themes 20/20** (light 10/10, dark 10/10; run log `tests/behavior/system-provider-config/runs/2026-07-06-02-37-37.md`, chrome-devtools sync crew, seeded provider cleaned up) — FD-driven post-Leg-5

### Adaptation Criteria

**Divert if**: the shared tools-form-helpers `.field-group` migration breaks studio's tools-tab/connector rendering beyond a quick fix (re-scope — keep admin/studio on a shared transitional wrapper), or the section-title split cascades into a broad cross-area rename (narrow to admin + the one chat field-label, defer the rest with a documented convention).

**Acceptable variations**: exact admin CSS within the vocabulary; leg order among providers/tools; keeping a documented dense label-left exception; the exact quiet-label recipe name.

### Legs

> **Note:** Tentative; created one at a time as the flight progresses.

- [x] `providers-surface` - providers-grid + provider-editor + provider-models to vocabulary; 6 .admin-pf-row→.field-group (PRESERVE .admin-pf-* marker classes for the type-driven show/hide; thinking/num_ctx toggle stays label-left exception); badge eyebrow quiet; confirm .cap-chip-no-tools consumes the already-gated danger pair (no new gate); label-association
- [x] `tools-surface` - tools-grid + tools-editor (admin-only rows) to vocabulary; enabled-row→.field-group; confirm .editor-error-banner consumes the already-gated danger pair (no new gate); tool-badge quiet. (Note: tools-editor schema-field rows come from the shared renderField — migrated in leg 3; mid-flight the editor carries mixed .field-group + .field-row rows, expected, not a defect)
- [x] `shared-helpers-and-chiplist` - tools-form-helpers renderField .field-row→.field-group (2 call sites: admin tools-editor + studio tools-tab; KEEP .tools-editor-field + data-field-name markers) + chip-list label[for] systemic fix (options.controlId on .chip-list-input; enumerate the mcp-server-editor mf-{name} placeholder-div repoint) + RUNTIME guard in tests/browser/; re-verify studio + system lanes
- [x] `general-and-section-title` - system-page (General) to vocabulary; .section-title overload RESOLVED BY DOCUMENTING the element-scoped convention (gallery note; do NOT restyle, do NOT touch chat.js); delete the dead .field-description gutter rule (:461) + retire the .area-admin .field-error gutter (:445) after the .field-row sites migrate
- [x] `system-verification` - suites via lanes (system + cross-area studio + chat) + full `-m browser`, all green (unit 3781 reconciled); dual-theme visual pass (CDP focus) over all admin surfaces; `.cap-chip` survivor DEFERRED to F7; `system-provider-config.md` AUTHORED (status active, full-UI-create, both themes) — the behavior-gate **RUN is FD-pending** (FD drives it via the sync chrome-devtools sub-orchestrator + independent a11y review after this leg lands) + ledger

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [x] Tests passing (via lanes — studio + system + chat re-verified for the cross-area changes)
- [x] Flight log updated
- [x] Documentation updated (section-title convention in the gallery)

### Verification

System renders the vocabulary in both themes (no per-area variants, no alien remnants, badge eyebrows quieted); provider + tools editors migrated to `.field-group` with label-association; the `.area-admin` gutter exceptions retired; the `.section-title` overload resolved; the shared chip-list `label[for]` dangle fixed (admin + studio) with a runtime guard; the two danger-on-soft-fill surfaces gated; `system-provider-config` passes both themes; the studio + chat lanes still green (cross-area changes); suites green; ledger honest.
