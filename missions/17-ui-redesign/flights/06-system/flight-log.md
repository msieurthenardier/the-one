# Flight Log: System / Admin Re-skin

**Flight**: [System / Admin Re-skin](flight.md)

## Summary

In flight. Leg 1 (providers-surface) landed: the LLM Providers surface re-skinned to
the v3 vocabulary, the 6 provider-editor label-left rows migrated to `.field-group`
(marker classes preserved for the type-driven show/hide), and the provider badge
eyebrow quieted. Leg 2 (tools-surface) landed: the Built-in Tools grid + editor
(admin-only rows) closed their two remaining v2 remnants — the tool badge / subtitle
eyebrows quieted, the enabled toggle kept as a documented label-left exception — and
the `.editor-error-banner` danger pair pinned by a source-grep guard. Leg 3
(shared-helpers-and-chiplist, the flight's highest-coupling leg) landed: the shared
`renderField` emitter migrated `.field-row`→`.field-group` across both its admin +
studio call sites (markers preserved; 422 rendering re-verified), and the chip-list
`label[for]` runtime-dangle was fixed systemically via `renderChipListEditor`'s new
`controlId` (the mcp-server-editor placeholder-div repoint enumerated) with a runtime
DOM guard — the system + studio lanes both re-verified green. Leg 4
(general-and-section-title) landed: the System General page was already
vocabulary-compliant (verified, no code change); the `.section-title` two-role overload
was closed by DOCUMENTING the element-scoped convention in the design gallery (no
restyle, chat lane out of the blast radius); and both `.area-admin` gutter exceptions
(the dead `.field-description` rule + the `.field-error` label-gutter) were retired with
consumer-grep evidence. Leg 5 (system-verification) landed: all suites green (unit 3781
reconciled as authoritative; system + cross-area studio + chat lanes + full `-m browser`
all pass, zero flakes); a dual-theme chrome-devtools visual pass over every re-skinned
admin surface (both themes, focus + label + composite evidence); the `system-provider-config`
SC7 behavior spec AUTHORED (status active, full-UI-create, both themes — RUN is FD-pending);
and the `.cap-chip` cross-area eyebrow survivor DEFERRED to F7 (shared studio/admin markup
— an admin-scoped override would split a shared vocabulary).

---

## Leg Progress

### Leg 1 — providers-surface (landed)

**Re-skin.** providers-grid / provider-editor / provider-models already consumed the
F3 vocabulary (`.entity-tile`, `.btn-*`, `.field-input`/`.field-select`, `.page-header`,
`.chip`, `.indicator-led`) from the prior editor scaffold; this leg closed the two
remaining v2 remnants on the surface (label-left rows + badge eyebrow) and verified the
whole surface in both themes via chrome-devtools (CDP visual + `:focus-visible` evidence
that goldfinch can't observe). No per-area variants, no alien remnants.

**`.field-group` migration + marker-class preservation.** The 6 `.admin-pf-row` real
render sites (provider-editor.js Name / Type / Base URL / API Key / num_ctx / thinking —
GREP-confirmed 6, no F5-style inflation) migrated to the stacked `.field-group` vocabulary.
The 5 text fields stack (label above control); num_ctx's info-icon moved into the shared
`.field-group-label` primitive (label + ⓘ on one line above the input, `<button>` a
SIBLING of `<label>`). The `.admin-pf-{base-url,api-key,num-ctx,thinking-enabled}` marker
classes were PRESERVED on the migrated rows — `wireEditorEvents` (js:278-289) toggles
`is-hidden` by those exact classes on provider-type change.

**Show/hide verified both themes.** Drove live provider-type switches in the running
8485 dev instance: Ollama → base_url + num_ctx shown, api_key + thinking hidden;
Anthropic → api_key + thinking shown, base_url + num_ctx hidden. Verified in BOTH light
and dark. Focus rings (`.field-input:focus-visible`, 2px accent outline) confirmed on the
migrated inputs in both themes.

**Thinking toggle label-left exception (documented).** The `config.thinking_enabled`
iOS-style toggle stays on the label-left `.field-row` layout (`label | ⓘ | switch` on one
row) — stacking a single toggle under its own label reads worse (F5 chrome-row precedent).
Documented inline in provider-editor.js and in the leg spec; `.admin-pf-thinking-enabled`
marker preserved. (Mid-leg the editor intentionally carries mixed `.field-group` +
`.field-row` rows — the toggle exception.)

**Badge quiet.** `.admin-provider-badge` (admin.css) quieted to the vocabulary
(font-family sans, text-transform none, letter-spacing normal). NB: the eyebrow also lives
in the shared `.entity-tile-badge` base (components.css), which the area-scoped selector
outranks (0,2,0 > 0,1,0) — so quieting is an explicit OVERRIDE, not a mere deletion of the
three declarations. Per-type ink stays on the `--badge-ink-*`-gated
`.admin-provider-badge--{type}` modifiers (verified in both themes: anthropic white ink,
ollama dark ink; typography quiet). Scoped to the provider surface — studio's shared base
untouched.

**cap-chip-no-tools composite gate — CONFIRMED, no new gate.** `.cap-chip-no-tools`
(admin.css) consumes the EXACT `--status-danger` on `--status-danger-bg-soft` pair already
gated by `test_danger_text_on_soft_fill_passes_body_aa` (test_design_tokens_a11y.py). Per
the flight's promoted-invariant DD, no new `_alpha_composite` math was added. Added the
optional source-grep guard (`test_cap_chip_no_tools_consumes_the_gated_danger_pair`) that
pins the usage so a future retune to a novel fg/bg triple trips loudly.

**Guards / tests.** Label-association guards green; DYNAMIC_SINK_BASELINE unchanged (the
`.field-group` edits are inside `renderConnectionFields`; the `container.innerHTML = html`
sink statement is untouched, so no new/changed sink); testid registry unchanged (no new
ids). System browser lane green (92 passed), `make test-unit` green (3780 passed), ruff
check + format clean. Admin pixel baselines regenerated locally (badge shift) —
`admin-with-provider-{dark,light}` + `admin-empty-{dark,light}`; gitignored, pass on clean
re-run.

### Leg 2 — tools-surface (landed)

**Re-skin.** tools-grid (`.entity-tile.tool-tile`, `role=tablist` category tabs,
`.tool-enable-switch--corner`) and tools-editor (`.editor-header`, `.editor-section`,
`.section-title`, `.btn-*`, schema fields via the shared renderField) already consumed
the F3 vocabulary from the prior editor scaffold; this leg closed the remaining v2
remnants on the surface (two badge eyebrows) and verified the whole surface — grid +
editor — in both themes via chrome-devtools (CDP computed-style + `:focus-visible`
evidence). No per-area variants, no alien remnants.

**Badge/eyebrow quiet — OVERRIDE for the tile badge, plain quiet for the subtitle.**
`.admin-tool-badge` (admin.css) quieted to sans / none / normal. As in Leg 1, this is an
explicit OVERRIDE, not a deletion: the shared `.entity-tile-badge` base (components.css)
declares mono/uppercase/letter-spacing and the area-scoped `.area-admin .admin-tool-badge`
outranks it (0,2,0 > 0,1,0) — a bare delete would let the base reassert the eyebrow.
Per-type ink stays on the `--badge-ink-*`-gated `.admin-tool-badge--{category}` modifiers
(verified dark: filesystem teal fill, dark ink; typography quiet). `.editor-subtitle-meta`
(the tools-editor header category subtitle) quieted to sans / none / normal — here a plain
quiet, since only that rule declares the three (the `.editor-subtitle` base carries none),
size (tiny) + `--fg-muted` ink kept. Both scoped to the tools surface — studio's shared
base untouched.

**Enabled-row — documented label-left toggle exception.** The `.tools-editor-enabled-row`
(tools-editor.js) is a single toggle, so it stays on the label-left `.field-row` layout
rather than stacking into a `.field-group` — same call as Leg 1's provider
`thinking_enabled` toggle (F5 chrome-row precedent; stacking a lone toggle under its own
label reads worse). Documented inline in `renderEnabledRow`. The `.tools-editor-enabled-row`
marker + `data-field-name="enabled"` preserved; `label[for="tef-enabled"]` resolves to the
real labelable `<input id="tef-enabled">` at mount (verified via `page.evaluate` in both
themes) — label-association green.

**Mixed field-group/field-row state (expected).** Post-L2 the tools-editor's Configuration
section carries the label-left enabled-row `.field-row` plus the schema-field `.field-row`
rows emitted by the shared `renderField` (Leg 3, cross-area). Once Leg 3 migrates
renderField to `.field-group`, the editor will carry mixed `.field-group` schema rows +
the `.field-row` enabled-toggle exception. This intentional mid-flight mix is NOT a defect.

**editor-error-banner composite gate — CONFIRMED, no new gate.** `.editor-error-banner`
(admin.css) consumes the EXACT `--status-danger` on `--status-danger-bg-soft` pair already
gated by `test_danger_text_on_soft_fill_passes_body_aa`. Verified the rendered values in
both themes via computed style (light: `rgb(185,28,28)` text on `rgba(185,28,28,0.06)`;
dark: `rgb(248,113,113)` on `rgba(248,113,113,0.08)`). Per the flight's promoted-invariant
DD, no new `_alpha_composite` math. Added the source-grep guard
(`test_editor_error_banner_consumes_the_gated_danger_pair`, the sibling of Leg 1's
cap-chip guard) that pins the usage so a future retune to a novel fg/bg triple trips loudly.

**Guards / tests.** Label-association guards green; DYNAMIC_SINK_BASELINE unchanged (badge
quiet is pure CSS; the enabled-row edit is a comment only — no innerHTML sink changed);
testid registry unchanged (no new ids). System browser lane green (92 passed:
`test_flow_admin_tools_editor` / `test_flow_admin_tools_grid` / `test_flow_admin_openrouter`
+ the rest), `make test-unit` green (3781 passed — +1 for the new banner guard), ruff check
+ format clean. No pixel-baseline regen needed: the 12 baselines snapshot the Chat / Studio /
providers-grid views, none of which render `.admin-tool-badge` or `.editor-subtitle-meta`
(both live on the tools grid / editor only).

### Leg 3 — shared-helpers-and-chiplist (landed)

**renderField `.field-row` → `.field-group` (cross-area).** The shared
`tools-form-helpers.js` `renderField` emitter migrated from the label-left
`.field-row` to the stacked `.field-group` vocabulary — feeding its exactly TWO
call sites (admin `tools-editor.js:153` + studio `tools-tab.js:415`, GREP-confirmed,
no other consumer). The label now pairs with the info-icon on one line ABOVE the
control via the shared `.field-group-label` primitive (`<button>` a SIBLING of
`<label>`, never nested), with the `visually-hidden` description span + control
stacked below — the same shape as the Leg 1 provider-editor migration. Plain
fields (no description) keep the label as a direct `.field-group` child. **AC
INVARIANT preserved:** `.tools-editor-field` + `data-field-name` stay on the
migrated row — `renderFieldErrors`' selector (`:552`) AND `applyShowIf`
(tools-editor.js:265) key on them in BOTH lanes; dropping either would silently
break 422-error rendering + show_if visibility. Verified stacked layout +
label-association in both themes via chrome-devtools (`label.control` resolves,
`.field-group-label` header, label above control).

**422-error rendering verified (admin tools-editor).** Drove the `fetch_url`
model-validator 422 live on 8485: set `timeout_seconds_max=10` (< default 30) →
Save → `.editor-error-banner` visible with humanized text ("… must be <= …", no
"Value error," prefix) AND `.field-error-highlight` applied to BOTH offending
`.tools-editor-field` rows (`timeout_seconds_default` + `timeout_seconds_max`).
The renderFieldErrors marker selector is intact. Inside a stacked `.field-group`
the inline `.field-error` sits flush (the `.area-admin .field-group .field-error
{margin:0}` escape already handles it — no gutter offset).

**Chip-list `label[for]` systemic fix — the F5 runtime-dangle CLOSED.** Added an
`options.controlId` param to the shared `renderChipListEditor` → lands as `id` on
the real focusable `.chip-list-input` (a `<div>` wrapper is NOT labelable, so the
label's for-target must point at the input). Wiring: `renderField` passes
`controlId: idAttr` (the `tef-{name}` it already computes for its label — both
array branches, plain + NarrowSuperset). **mcp-server-editor.js — the TRUE
mount-time strip site — repointed and ENUMERATED (4 render sites + 2
placeholders):** the two placeholder `<div>`s (`mf-args` at the Arguments field,
`mf-sandbox-writable-paths` at the Sandbox Writable-paths field) DROPPED their
`id` (mountChipListEditors replaces them via `outerHTML=`, which strips the id),
and all four `renderChipListEditor` call sites now pass `controlId` — the two
mount sites (`mountChipListEditors`, js:868/876) and the two Cancel/revert
re-mount sites (js:1492/1508). Post-mount selectors key on
`[data-field="…"].chip-list-editor` (js:857/873/915/1484/1505), never the id, so
dropping the placeholder id is safe — verified live that only ONE element carries
each id (the `<input class="chip-list-input">`, no stray div). Confirmed both
admin tools (`tef-host_allowlist` et al.) and mcp (`mf-args`,
`mf-sandbox-writable-paths`) labels resolve to the real input in both themes.

**RUNTIME DOM guard added** (`tests/browser/test_flow_chiplist_label_resolver.py`,
2 tests, green). A Playwright flow (precedent
`test_flow_studio_per_agent_overlay_label_resolver.py`) that mounts each
chip-list-bearing editor and asserts — via the DOM's own
`HTMLLabelElement.control` resolver (null for a non-labelable / missing target) —
that every chip-list `label[for]` resolves to the real `.chip-list-input`. Covers
admin tools-editor + mcp-server-editor. Placed in the `shared` lane complement
(cross-cutting). NOT in the static `test_ui_guards.py` — that source scan
provably cannot catch a mount-time id strip.

**Guards / tests.** Static label-association guard green: the two mcp chip-list
for-targets (`mf-args`, `mf-sandbox-writable-paths`) added to
`FIELD_FOR_ID_HELPER_INDIRECTED` (their id is now emitted through the shared
helper's concatenation, invisible to the literal-id scan — the same
manual-exception pattern the two `cf-*` lifecycle-select rows use; the runtime
guard is what actually proves resolution). DYNAMIC_SINK_BASELINE unchanged — the
`controlId` args land past the 80-char normalized snippet prefix, so no sink
snippet shifted; testid registry unchanged. **Cross-area verification:** BOTH
`--lane system` (92 passed) AND `--lane studio` (251 passed, 3 skipped) green via
run-tests.sh — the shared change regressed neither. (One studio file,
`test_flow_studio_connector_create_and_test`, flaked once under full-lane load on
an 8s wait for a heavy page; passes 4/4 in isolation — unrelated to this leg,
which never touches connector-editor.js.) `make test-unit` green (3822 passed),
ruff check + format clean. No pixel-baseline regen: the 12 baselines snapshot the
Chat / Studio / admin-landing views, none of which render the tools-editor schema
fields or the mcp-server-editor.

**CSS follow-through (minimal).** Removed the two `.area-admin
.tools-editor-field .field-info-icon` overrides (the `align-self:center` +
chip-list-row `:has(...) {padding-top:8px}` top-align) — they keyed on the old
`.field-row` flex-row geometry (icon as third flex child beside the wrapping
chip-list); in the stacked `.field-group` the icon now sits in the
`.field-group-label` header where the base `.field-info-icon` reset +
`align-items:center` place it correctly. Repointed the now-dead `.area-studio
.tool-row-overrides .field-row` spacing rule to `.field-group` to preserve the
override panel's compact 8px inter-field spacing.

### Leg 4 — general-and-section-title (landed)

**General page re-skin — already vocabulary-compliant, verified not rewritten.** Like
Legs 1-2, the System General page (`system-page.js`) already consumed the F3 vocabulary
from the prior scaffold: `.page-header`/`.page-title`, the three `.admin-system-section`
blocks, `.code-block` (Base Prompt), `.banner banner-warning` + `.btn-muted-destructive`
+ shared `confirmDelete` (Encryption rotate). No v2 remnant to quiet — the three
`.section-title admin-section-title` blocks render as body-sm quiet-labels (`div` element,
12px), and `.admin-section-title` carries NO CSS treatment (a dead hook class, no
eyebrow/mono), so per the section-title DD they were LEFT untouched (not migrated to h2,
not restyled). Verified the whole page in BOTH themes via chrome-devtools: page title,
three sections, quiet-label headings @ 12px, warning banner (amber, `rgb(251,191,36)` in
dark), rotate button (danger ink `rgb(248,113,113)` + muted border in dark), code-block
with the base prompt loaded. **confirmDelete intact:** a single click arms the button to
`.btn-muted-destructive.confirm-delete` with the title "Confirm Rotate?" and `disabled=false`
(second click never sent — the encryption key was NOT rotated). No code change to the page.

**`.section-title` two-role overload — CLOSED by documenting, not restyling.** Per the
architect-corrected DD, the SC3 `.section-title` overload item was closed by surfacing the
element-scoped convention in the design gallery (`design-language/typography-section.js`,
via createElement per the innerHTML-sink freeze): a note demonstrating `h2.section-title`
@ 15px (the h3 size bump — editor section headers) side-by-side with `div`/`label`
`.section-title` @ 12px (the body-sm quiet standalone label — chat agent-select, system
page sections), plus prose recording that the overload is intentional and
element-differentiated and that the class rename was deferred as churn without payoff (M17
F3). The internal record already lives in the `components.css` `.section-title` comment;
this surfaces it where operators see both renderings. **`chat.js:136` untouched**, no new
quiet-label recipe introduced, no correctly-rendering `div.section-title` use migrated —
the chat lane stayed entirely out of the blast radius (verified: 49 passed).

**Two `.area-admin` gutter exceptions retired — consumer-grep evidence.** (a) The
`.field-description` gutter rule (`margin: 4px 0 0 100px`; had shifted to admin.css:471
post-Legs-1-3) was ALREADY DEAD — `grep` over `the_one/` for a `class="field-description"`
render site found only comment references (renderField replaced the paragraph with the
info-icon tooltip in the L3 migration). Deleted. (b) The `.field-error` label-gutter rule
(`margin: 4px 0 0 100px`; admin.css:455) was retired: `grep` confirmed the only admin
`.field-error` emitters are the design-language gallery's Invalid-field demo (child of a
`.field-group`) and `renderFieldErrors` (attaches to the `.field-group.tools-editor-field`
rows, post-L3) — BOTH land inside `.field-group`; the only surviving label-left `.field-row`s
are the documented toggle exceptions (provider `thinking_enabled`, tools `enabled`), which
carry no `.field-error`. So NO `.area-admin .field-row .field-error` consumer remained. The
`.area-admin .field-group .field-error {margin:0}` escape was folded into the base
`.area-admin .field-error` rule (now `margin:0`; the `.field-group`'s own flex-column gap
supplies the top spacing) and the escape deleted. Verified a stacked `.field-group
.field-error` still renders correctly (margin-left 0, no gutter, display block, danger ink)
in BOTH themes via the gallery's Invalid-field demo.

**Guards / tests.** `make test-unit` green (3781 passed, 10 skipped) — label-association
guards + DYNAMIC_SINK_BASELINE honest (the gallery note is createElement, not an innerHTML
sink; `system-page.js` markup untouched — no sink shifted). `--lane system` green (92
passed), `--lane chat` green (49 passed — chat.js untouched, no regression). ruff check +
format clean. No pixel-baseline regen: the 12 baselines snapshot Chat / Studio /
providers-grid / admin-landing — none render the design-language gallery, the General page,
or a rendered `.field-error`, so nothing in the baselines shifted.

### Leg 5 — system-verification (landed)

**Suites — all green, zero flakes.** No failure surfaced on any run, so the pre-specified
flake disposition (passes-in-isolation + clean-module-rerun = flake) was never invoked —
there was nothing to disposition. Ran once each, host-native via the venv python:

| Suite | Result | Wall-clock |
|-------|--------|-----------|
| `make test-unit` | 3781 passed, 10 skipped, 654 deselected | 5m29s |
| browser `--lane system` | 92 passed | 2m20s |
| browser `--lane studio` (cross-area) | 252 passed, 3 skipped | 7m28s |
| browser `--lane chat` (cross-area) | 49 passed | 1m37s |
| full `-m browser` (confirmation) | 565 passed, 6 skipped, 12 deselected | 12m56s |

Browser suites all through `scripts/run-tests.sh` (`PYTHON=.venv/bin/python`), run
strictly sequentially (one group at a time — no concurrent browser load to starve
another into a false-timeout). The four lanes' union = the full suite (92+252+49 area +
~172 shared = 565), matching the CLAUDE.md complement invariant — nothing orphaned. The
cross-area studio + chat lanes (touched by Legs 1-3's shared-helper + chip-list changes)
are green: no regression from the F6 shared-code edits.

**Authoritative unit-count reconciliation → 3781.** A single clean run on the Legs-1-4
tree yields **3781 passed / 10 skipped / 654 deselected** (collection: 3840 selected of
4445 total; the 49-test gap between 3791 run and 3840 collected is `requires_bwrap` et al.
deselected at runtime by the `addopts` marker). This corroborates Leg 4's independent 3781.
**Leg 3's 3822 is the outlier and is not reproducible on the current tree.** It corresponds
to no net unit-test delta between Leg 3 and now: Leg 4 added/removed zero unit tests (it
retired two CSS rules, added a `createElement` gallery note, and guard-index entries);
Legs 1-2 each added exactly one a11y source-grep guard; Leg 3's added guard is a *browser*
test (deselected from the unit set). The 3822 figure was therefore a Leg-3 mis-record —
most plausibly the collected/selected count (~3840) or a run whose marker set didn't
exclude `requires_bwrap` — superseded by the reproducible 3781.

**Dual-theme visual pass (chrome-devtools, fresh page, ignoreCache) — clean both themes.**
On 8485 (dev-mode), a fresh CDP page with an `ignoreCache` reload (picks up the Legs-1-4
static CSS/JS from disk without a server restart). Enumerated the re-skinned admin surfaces
in **light AND dark**:
- **Providers grid** — cards with quiet type badges (anthropic purple / ollama green,
  lowercase sans, no uppercase eyebrow; per-type ink preserved).
- **Provider editor** — the 6 `.admin-pf-row`→`.field-group` migration renders stacked
  (Name/Type/Base URL/Context Window ⓘ); type-driven show/hide verified live (Ollama →
  base_url+num_ctx shown, api_key+thinking hidden; Anthropic → api_key `.field-group` +
  the **Extended thinking** label-left toggle exception shown) — marker classes intact.
  Focus: Name `:focus-visible` = 2px accent outline (light rgb(109,40,217) / dark
  rgb(167,139,250)); label `for="pf-name"` resolves via `label.control`.
- **Ollama models panel** — capability chips render; `.cap-chip-no-tools` consumes the
  exact gated danger pair (light rgb(185,28,28) on rgba(185,28,28,0.06); dark
  rgb(248,113,113) on rgba(248,113,113,0.08)).
- **Tools grid** — tool tiles with quiet category badges (filesystem teal / execution
  amber, lowercase), corner enable toggles, tablist tabs.
- **Tools editor** (shell) — all 7 `.tools-editor-field` rows are now `.field-group`
  (`data-field-name` markers preserved); the enabled-row stays `.field-row` (label-left
  exception); subtitle-meta quieted (none/normal/sans). **Chip-list** ("Command Denylist",
  `id=tef-command_denylist`): `label[for]` resolves to the real `.chip-list-input`
  (the L3 systemic fix holds); focus indicated by the wrapper border → accent on
  focus-within.
- **General page** — Appearance (Light/Dark/Auto), Base Prompt code-block (read-only),
  Encryption amber warning banner + danger Rotate button (danger ink + muted border in
  dark); three section headings render as body-sm quiet-labels.

Theme preference recorded (none stored → default light) and **restored** (removed the
`theme-preference` key set during the dark pass, since localStorage is origin-shared).
Own CDP tab closed; the two pre-existing operator tabs left untouched; **8484 never
touched**.

**SC1 spot-check + `.cap-chip` survivor disposition → DEFER to F7.** No alien remnants
across the admin surface EXCEPT the known `.cap-chip` eyebrow (uppercase + 0.5px
letter-spacing on COMPLETION/TOOLS/VISION and the "NO TOOLS" chip; mono already dropped).
**Decision: defer to F7, do NOT quiet here.** `.cap-chip` is defined UN-scoped in
admin.css and rendered by `renderCapabilityChips` (provider-models.js), which is exposed
as `window.App.admin.renderCapabilityChips` and consumed by studio's model selector
(studio.js:1383/1747) — the identical markup renders on BOTH the admin Ollama panel AND
the studio picker. Unlike the Leg-1/2 badge overrides (whose classes are admin-only, so an
`.area-admin` scope quiets the sole render site), an area-scoped `.cap-chip` override would
quiet ONLY the admin instance and leave studio's identical chips uppercase — splitting a
shared vocabulary into a per-area variant, exactly what SC3 forbids. The correct fix is a
single UN-scoped quiet covering both surfaces together — a cross-area change that belongs
to F7 (which "closes the sweep"). Deferred with this rationale.

**system-provider-config SC7 spec — AUTHORED (not run here).** Wrote
`tests/behavior/system-provider-config.md` (status **active**). Well-formed per
ARTIFACTS.md (Intent / Preconditions / Observables Required / Steps table / Out of Scope /
Variants). Drives the **full UI create** (not the `seed_mock_provider` API helper):
Providers grid → `new-provider-btn` → editor fill Name + Type=Mock(dev) (cred-less →
name+type only, `TYPE_DEFAULTS.mock showBaseUrl/showApiKey:false`) → `save-provider-btn`
→ `provider-card` in grid → re-select + edit + `test-connection-btn` → Danger-Zone
`delete-provider-btn` with the agent-usage pre-gate + two-step `confirmDelete` armed
"Confirm Delete?" state as a judged `[a11y]` checkpoint → gone. Precondition: 8485 dev-mode
with an active `GET /api/providers/types` includes-`mock` probe. Both-theme variant.
chrome-devtools apparatus (multi-step drive + ignoreCache; goldfinch wedges). **The RUN is
FD-pending** — this leg authors + verifies-statically; the Flight Director runs the gate
via the sync chrome-devtools sub-orchestrator after this leg lands.

**Sinks / registry / lint / snapshots.** This leg made **no source changes** (authored a
markdown spec + updated the leg/flight/flight-log artifacts only) — so DYNAMIC_SINK_BASELINE
is unchanged (no innerHTML sink added/shifted) and the testid registry is unchanged (no
new ids). `ruff check` + `ruff format --check` clean (399 files). `git status` clean of
snapshots (no pixel baseline regen — no CSS change this leg; baselines stay gitignored).

---

## Decisions

- **Badge quiet is an OVERRIDE, not a deletion.** Because the shared `.entity-tile-badge`
  base carries the mono/uppercase/letter-spacing eyebrow and the area-scoped
  `.area-admin .admin-provider-badge` outranks it, the leg's "drop mono/uppercase/
  letter-spacing" is implemented as explicit sans/none/normal values (a bare deletion
  would be a no-op — the base would reassert the eyebrow). Kept area-scoped to avoid
  dragging studio (F1-F5, shared base) into F6's blast radius.
- **num_ctx info-icon moved into `.field-group-label`** (was `label | input | ⓘ`) to match
  the v3 stacked vocabulary; the icon stays a descendant of `.admin-pf-num-ctx` and the
  `aria-describedby` → `#pf-num-ctx-desc` wiring is unchanged (provider tests + label
  guards stay green).

---

## Deviations

- None material. `run-tests.sh --snapshot-update` isn't registered at rootdir; used the
  documented `UPDATE_SNAPSHOTS=1` env-var bridge instead (equivalent).

---

## Anomalies

- `.cap-chip` (admin.css, UN-scoped, shared with studio's model selector) still carries
  uppercase + letter-spacing — a flight-DD (line 41) eyebrow survivor. The leg AC scoped
  cap-chip work to the composite-gate CONFIRMATION only (not typography), and quieting the
  un-scoped `.cap-chip` would be a cross-area change to studio's model-selector chips — out
  of this leg's scope. Flagged for a later leg / flight decision (F7 "closes the sweep").
  **RESOLVED (Leg 5): DEFER to F7.** Confirmed the class is genuinely cross-area —
  `renderCapabilityChips` (provider-models.js) is exposed as
  `window.App.admin.renderCapabilityChips` and consumed by studio.js:1383/1747, so the same
  markup renders on the admin Ollama panel AND the studio picker. An `.area-admin`-scoped
  quiet (the Leg-1/2 badge playbook) would only affect the admin instance and leave studio's
  identical chips uppercase — a per-area variant SC3 forbids. The right fix is one UN-scoped
  quiet covering both surfaces together (F7's cross-area sweep). Not a defect; deferred by
  design, not omission.

---

## Session Notes

- Verified on the mission dev instance (8485, dev-mode — mock provider type available);
  fresh chrome-devtools page with ignoreCache reload (JS not cache-busted). Theme
  preference recorded (none stored → default light) and restored (removed the
  `theme-preference` key introduced during dark-theme verification, since localStorage is
  shared across the origin's tabs). Own tab closed; the two pre-existing tabs left
  untouched; 8484 never touched.

- **Flight 6 complete — System re-skin landed (5 legs).** The LAST surface is on the v3
  quiet vocabulary. What the flight delivered and the lessons it banked:
  - **Shared-helper cross-area migration.** The shared `renderField` emitter
    (`tools-form-helpers.js`) migrated `.field-row`→`.field-group` feeding BOTH its call
    sites at once (admin tools-editor + studio tools-tab) — a 2-path change realistic in
    one leg with no transitional wrapper; both the `system` and `studio` lanes re-verified
    green afterward (markers + 422-error rendering intact in both).
  - **Chip-list `label[for]` systemic fix — the F5 carry-forward CLOSED.** The runtime
    mount-strip (a `<div>` placeholder is not labelable) fixed via `options.controlId`
    landing on the real `.chip-list-input`, plus the `mcp-server-editor` placeholder-div
    repoint (id dropped; post-mount selectors key on `[data-field].chip-list-editor`, not
    the id). One shared fix covered admin tools + all studio chip-list consumers. Carried
    by a new **runtime DOM guard** (`test_flow_chiplist_label_resolver.py`) asserting
    resolution via `HTMLLabelElement.control` — a static source-scan provably can't catch a
    mount-time id strip.
  - **Composite-gate-already-covered simplification.** Both danger-on-soft-fill admin
    surfaces (`.cap-chip-no-tools`, `.editor-error-banner`) consume the EXACT
    `--status-danger`/`--status-danger-bg-soft` pair already gated once at the token level
    (`test_danger_text_on_soft_fill_passes_body_aa`). The promoted-token invariant worked
    as intended — CONFIRM-and-cheap-source-grep-pin, NO per-surface `_alpha_composite`
    rediscovery. This is what the "gate the pair once at definition" design buys.
  - **Section-title documented, not restyled.** The `.section-title` two-role overload
    (h2 heading vs div/label quiet-label) renders correctly by element already; closed the
    SC3 item by DOCUMENTING the element-scoped convention in the design gallery (F3 had
    deferred the rename as churn-without-payoff). No restyle, `chat.js` untouched, chat lane
    out of the blast radius.
  - **Badge-quiet-via-override lesson.** Because the shared `.entity-tile-badge` base
    carries the eyebrow and the area-scoped `.area-admin .admin-*-badge` outranks it,
    quieting is an explicit sans/none/normal OVERRIDE — a bare deletion would be a no-op
    (the base reasserts). Kept area-scoped to keep studio (shared base) out of F6.
  - **`.cap-chip` cross-area survivor → F7.** The one remaining eyebrow is on markup
    (`renderCapabilityChips`, exposed as `window.App.admin.renderCapabilityChips`) shared by
    the admin Ollama panel AND studio's model picker. An area-scoped quiet would split the
    shared vocabulary into a per-area variant (SC3-forbidden); the right fix is one
    un-scoped quiet covering both surfaces — deferred to F7's cross-area sweep by design.
  - **SC7 gate PASSED both themes (20/20).** The `system-provider-config` behavior gate ran
    via the sync chrome-devtools sub-orchestrator and passed light 10/10 + dark 10/10
    (full-UI provider create/edit/test/two-step-confirm-delete on the re-skinned surface;
    seeded provider cleaned up). Run log
    `tests/behavior/system-provider-config/runs/2026-07-06-02-37-37.md`.
  - **Advisory finding (behavior test caught it) → F7.** The gate surfaced an
    H1-header/Name-field desync in the provider editor — theme-independent and likely
    pre-existing (not an F6 regression). Referred to the F7 consistency sweep.
  - **Standing lesson — `test_aiat.py` live tests target 8484.** The general reviewer's
    "4 `test_aiat.py` failures" are `@pytest.mark.live` tests EXCLUDED from the canonical
    `make test-unit` (clean at 3781/0-fail); F6 never touched `test_aiat.py`; they failed
    only for lack of a live agent — NOT a regression. Those live tests default
    `THE_ONE_TEST_URL` to `localhost:8484` (the operator's PROD packaged app) — reviewers
    must use the canonical `make test-unit` and never `-m live`.
  - Flight committed as a single commit (`flight/06: system re-skin …`) on
    `mission/17-ui-redesign`; hash to follow.
