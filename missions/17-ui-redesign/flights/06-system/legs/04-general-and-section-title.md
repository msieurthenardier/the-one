# Leg: general-and-section-title

**Status**: completed
**Flight**: [System / Admin Re-skin](../flight.md)

## Objective

Re-skin the System General page (system-page.js) to the vocabulary; resolve the `.section-title` two-role overload by DOCUMENTING the element-scoped convention (NOT restyling); and retire the `.area-admin` gutter exceptions now that the form rows have migrated.

## Scope (flight DDs authoritative)

- **system-page.js (General page)** → vocabulary: the three `.admin-system-section` blocks (Appearance/theme toggle, Base Prompt `.code-block`, Encryption rotate-key w/ `banner-warning` + confirmDelete). Consume F3 sections/buttons/banners. Quiet any remaining `.section-title.admin-section-title` per-area treatment (but see the section-title DD — it renders correctly by element; only quiet if it carries an actual eyebrow/mono treatment, else leave).
- **`.section-title` two-role resolution — DOCUMENT, do NOT restyle** (architect-corrected): the class is element-differentiated (`h2.section-title` heading bump at components.css:435; `<div>`/`<label>` render body-sm quiet-label) and F3 deliberately deferred the rename. **Close the SC3 item by adding a design-gallery note** documenting the element-scoped convention (the components.css:427-434 comment already records it internally — surface it in the gallery). Do NOT touch chat.js:136, do NOT introduce a new quiet-label recipe, do NOT migrate the correctly-rendering `div.section-title` uses. Keeps the chat lane out of the blast radius.
- **Gutter retirement — SPLIT the two rules** (now the provider + tools `.field-row` sites migrated in Legs 1-3):
  - `.field-description` gutter (admin.css:461) — ALREADY DEAD (no render site emits `.field-description`; renderField uses the info-icon tooltip). Confirm no render site (grep), then DELETE the dead rule.
  - `.field-error` gutter (admin.css:445, `margin: 4px 0 0 100px`) — verify NO remaining `.area-admin .field-row .field-error` consumer (Legs 1-3 migrated provider + tools + shared renderField; the only surviving label-left `.field-row`s are the documented toggle exceptions, which carry no `.field-error`). Retire the gutter rule; simplify the `.area-admin .field-group .field-error {margin:0}` escape (:454) into the base `.field-error` rule (stacked is now the default).
- Guard bookkeeping: label-association guards green; DYNAMIC_SINK_BASELINE updated if a system-page markup site changed; registry unchanged.

## Acceptance Criteria

- [x] General page (Appearance/Base Prompt/Encryption) renders the vocabulary, both themes (CDP visual + focus); rotate-key banner-warning + confirmDelete intact — already vocabulary-compliant (`.page-header`/`.page-title`, `.code-block`, `.banner banner-warning`, `.btn-muted-destructive`, confirmDelete); verified both themes via chrome-devtools (light + dark screenshots + computed style); confirmDelete arms to "Confirm Rotate?" + `.confirm-delete`, second click never sent (key not rotated). No code change needed on the page.
- [x] `.section-title` convention DOCUMENTED in the design-gallery (element-scoped: h2 heading vs div/label quiet-label); NO restyle, chat.js untouched; SC3 overload item closed as intentional/element-handled — note added to the Typography gallery section (`typography-section.js`, createElement); demonstrates h2.section-title @ 15px (h3 bump) vs div/label.section-title @ 12px (body-sm quiet-label) both themes; `chat.js:136` untouched; no new recipe; no `div.section-title` migrated
- [x] `.field-description` dead gutter rule (now at admin.css:471 post-L1-3 shift) deleted (grep-confirmed no `class="field-description"` render site — only comment references remain)
- [x] `.field-error` gutter (now at admin.css:455) retired (no remaining `.area-admin .field-row .field-error` consumer — the only admin `.field-error` emitters are the design-language gallery + `renderFieldErrors`, both landing inside `.field-group`; the surviving label-left `.field-row`s are the documented toggle exceptions, which carry no `.field-error`); the `.field-group .field-error {margin:0}` escape folded into the base rule (`margin:0`; the flex-column gap supplies spacing); a stacked `.field-group .field-error` verified rendering correctly (margin-left 0, no gutter) both themes
- [x] system lane (92 passed) + chat lane (49 passed — chat.js untouched, no regression) green via run-tests.sh; make test-unit green (3781 passed); ruff clean; label-association guards green; DYNAMIC_SINK_BASELINE honest (createElement gallery note + untouched system-page markup → no sink change)

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
