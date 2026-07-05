# Flight Log: Studio Re-skin

**Flight**: [Studio Re-skin](flight.md)

## Summary

Leg 06 (studio-verification) landed. Suites run green under the flake disposition:
`make test-unit` **3779 passed / 10 skipped** (328s); the **studio browser lane** 252
passed / 3 skipped (wall 7:38); the **full `-m browser` suite** 562 passed / 6 skipped /
**1 flake** (wall 12:33). The single failure —
`test_flow_studio_connector_discoverable_dropdown.py::...::test_dropdown_stale_entry_renders_with_data_stale_attribute`
(`App.studio` undefined when `page.evaluate` ran — a load-timing error under heavy
full-suite concurrency) — **passed in the studio lane AND passed 8/8 on a clean isolated
module rerun (12s)**, so it is dispositioned a load-flake, not a regression (the documented
run-tests.sh back-to-back load-flake class). Dual-theme CDP visual pass on 8485 (fresh page,
ignoreCache) across the enumerated studio surfaces — all clean of alien remnants (SC1). The
SC7 `studio-agent-crud.md` spec was **authored** (status active) and the SC5
`connector-editor-keyboard-a11y.md` staleness was updated (8485, prose); `studio-smoke.md`
archived. **The two behavior-gate RUNS are FD-pending** (this leg authors + statically
verifies; the Flight Director runs the Executor/Validator crews after this leg lands).

Leg 01 (agent-surface) landed. Agent-editor General tab migrated to the `.field-group`
vocabulary with full label-association, M07 F10 lazy-discovery copy added, the
save→delete race fixed + regression-tested, two composited-a11y gates + a light
`--status-warning` deepen landed, and two static label-association guards added
(probe-tested). Both themes verified via CDP.

Leg 02 (connector-editor-core) landed. connector-editor + connectors-tab re-skinned to
the vocabulary (drop redundant `admin-pf-*`); 13 form-field rows migrated to
`.field-group` with label-association (new shared `.field-group-label` primitive for
the info-icon fields); the `.area-studio .field-row .field-error` gutter exception
**retired in this leg** (connector-editor was its sole + last consumer — inline
validation rewired onto the `.is-invalid` + `.field-error` vocabulary); one connector
composite-a11y gate added; M12 F4 routing-reorder / live-region a11y preserved verbatim.
connectors-grid needed no changes. Both themes verified via CDP.

Leg 04 (mcp-surface) landed. mcp-server-editor.js's form rows migrated to the
`.field-group` vocabulary with label-association; the "12 `.field-row`" in the DD
was grep-inflated (the true render-site count is 11 — one is a comment line) with
**9 genuine form fields** migrated (name, type, command-runtime, custom-command,
cwd, args chip-list, url, sandbox network-toggle, sandbox writable-paths chip-list)
and **2 chrome rows** (empty-label action/hint rows). The redundant `admin-pf-input
admin-pf-select` composition was dropped from every migrated control (the vocabulary
`.field-input`/`.field-select` are self-sufficient — the Leg 2 move). **mcps-tab.js
and mcp-servers-grid.js needed ZERO changes** — both already render pure vocabulary
(mcp-source-tile echoing `.entity-tile`, createElement-based, no `.field-row`), the
connectors-grid/mcps-tab pattern from Legs 1-2. Both themes verified via CDP.

Leg 05 (browser-lanes-guards-docs) landed. Per-area browser test lanes
(`chat` / `studio` / `system` / `shared`) added to `scripts/run-tests.sh` as a
`--lane` selector — hand-rolled basename globs over `tests/browser/`, no new
deps, no per-test markers; `shared` is the complement so the four lanes' union
is always exactly the full browser suite (569 = 569 verified). The dirty-back
confirm-dialog flake was fixed (generous `_DIALOG_TIMEOUT` poll window on the
confirm-dialog-appears assertions), and the same root-cause fix was extended to
the sibling `test_flow_provider_dirty_confirm.py` (the `system` lane surfaced it).
markdown.js's header comment corrected 18 → 19 node-types (a comment; `NodeType`
freezes 19). Guard/registry bookkeeping was a no-op (Legs 1-4 introduced no new
testids; the Leg 01 label-association guards run green in the unit lane). All four
lanes run independently green; `make test-unit` green (3779); ruff clean.

Leg 03 (discord-and-dropdown) landed. connector-form-discord.js's 4 form rows
migrated to the stacked `.field-group` vocabulary (the "8" in the flight DD was a
grep-inflated line count — only 4 real render sites, matching the Legs 1-2 pattern);
the 3 info-icon rows reuse Leg 2's shared `.field-group-label`, and the Bot-Token
info-icon `<button>` was un-nested from inside its `<label>` (an a11y fix — a button
nested in a label is invalid). The discoverable-dropdown's sole alien remnant — the
group-header mono/uppercase/letter-spacing typography — was quieted to the vocabulary
label style; the WAI-listbox keyboard a11y is preserved verbatim (the JS file has
ZERO git diff). A dropdown focus/hover-wash composite-a11y gate was added. Both themes
verified via CDP.

---

## Leg Progress

### Leg 06 — studio-verification (landed)

- **Suites (via lanes) + flake disposition**:
  - `make test-unit` — **3779 passed, 10 skipped** (328.64s). Identical to Leg 05's
    baseline (this leg made zero source changes).
  - **studio browser lane** (`PYTHON=.venv/bin/python TEST_TIMEOUT=2400 bash
    scripts/run-tests.sh --lane studio -q`) — **252 passed, 3 skipped**, exit 0, wall
    clock **7:38** (pytest 456.91s). 33 studio test files. Clean, no flakes.
  - **full `-m browser` suite** (`TEST_TIMEOUT=3600 make test-browser`) — **562 passed,
    6 skipped, 12 deselected, 1 failed**, wall clock **12:33** (pytest 751.30s).
  - **Flake disposed** (pre-specified rule: passes-in-isolation + clean-module-rerun =
    flake): the lone failure was
    `test_flow_studio_connector_discoverable_dropdown.py::TestDiscoverableDropdown::test_dropdown_stale_entry_renders_with_data_stale_attribute`
    with `Page.evaluate: TypeError: Cannot read properties of undefined (reading
    'discoverableDropdown')` — i.e. `App.studio` had not finished loading when the test's
    `page.evaluate` ran, a load-timing error under heavy full-suite concurrency (the same
    run-tests.sh back-to-back load-flake class documented in Legs 04/05). The same file
    **passed inside the green studio lane** and **passed 8/8 on a clean isolated module
    rerun** (`run-tests.sh -m browser <file>`, 12.03s). Dispositioned a flake — NOT a
    regression. No source touched.
- **Dual-theme visual pass (CDP, 8485, fresh page + ignoreCache reload)** — chrome-devtools
  MCP (the Leg 04 deviation: chrome-devtools `navigate_page reload ignoreCache` loads the
  post-restart JS past the static `?v=` cache footgun; goldfinch has no ignoreCache reload).
  Enumerated re-skinned studio surfaces swept in **both light and dark**:
  - **Agent grid** + **agent editor all 5 tabs** (General / Knowledge / MCPs / Connectors /
    Built-in Tools): General 0 `admin-pf-*` / 0 `.field-row` / all `.field-group`, no alien
    typography, no dangling `label[for]`; Built-in Tools carries the M07 F10 lazy-discovery
    copy; Knowledge/MCPs/Connectors panels 0 `admin-pf-*` / 0 `.field-row` / no alien.
  - **Connector editor** — create form (Connection/Credentials/Session, 0 `.field-row`,
    14 `.field-group`) and the saved-connector **Advanced tab** (routing / allowlist /
    Direct-Messages) via a seeded discord connector: the 8 remaining `.field-row` are
    **exactly** the documented Leg 02 exceptions — 5 chrome rows (live-status, Validate,
    pairing status, pairing reveal, allowlist banner) + 3 label-left ACL rows (DM admission,
    Users, Servers); no alien typography, no dangling `for`.
  - **Discord form** — 15 `.field-group`, 0 `.field-row`; Bot-Token info-icon is a label
    **sibling** (not nested) — the Leg 03 a11y fix holds.
  - **discoverable-dropdown** — 4 present on the Advanced surface (WAI combobox/listbox);
    the group-header computed style is **de-aliened both themes** (Geist, `text-transform:
    none`, `letter-spacing: normal`, weight 500 — the Leg 03 quieting holds). Open-state
    *with populated groups* needs a live Discord connection (empty without one); the
    group-header rule was verified via a synthesized element + the Leg 03 CDP evidence.
  - **mcp-editor** — stdio form 9 `.field-group`, 0 `.field-row`, no alien, both themes.
  - **CDP keyboard focus** — `:focus-visible` = **2px solid `--accent`** on Tab-focus:
    light `rgb(109,40,217)` = `#6d28d9`, dark `rgb(167,139,250)` = `#a78bfa`.
  - **SC1 spot-check: PASS** — zero alien remnants across the studio surface (no mono/
    uppercase/letter-spaced labels, no leftover `admin-pf-*` on migrated controls, no
    unmigrated `.field-row` outside the documented ACL + chrome exceptions).
- **Behavior specs (authored / updated — NOT run; FD runs the gates)**:
  - Authored **`tests/behavior/studio-agent-crud.md`** (status **active**, SC7): mock-provider
    precondition (seed via `POST /api/providers` type `mock`, teardown `DELETE`; active
    dev-mode probe on `/api/providers/types`), create-agent (`new-agent-btn` → `tab-general`
    → name/description/provider/model → `save-agent-btn`) → grid tile appears → re-select +
    edit + save → General-tab Danger-Zone **two-step** `App.confirmDelete` ("Confirm Delete?"
    armed intermediate is a judged `[a11y]` checkpoint) → agent gone. Both-theme variant;
    cache-defeat across mutation boundaries; Out-of-Scope + Observables sections well-formed
    per ARTIFACTS.md.
  - Updated **`tests/behavior/connector-editor-keyboard-a11y.md`** staleness: target
    `http://localhost:8485` (was implicit 8484), the gone "Discord Constellation" fixture
    de-named (seed-fresh-or-use-existing connector with ≥3 routing rules + teardown), the
    `// ROUTING` marker prose → **Routing** section, apparatus note (chrome-devtools or
    goldfinch per mission). **Keyboard-reorder + live-region assertions UNCHANGED** (`Last
    Run` left at the real 2026-06-04 run).
  - Archived **`tests/behavior/studio-smoke.md`** (status **archived** + superseded-by note;
    file kept for history — draft/never-run, stale 8484/goldfinch/gone-fixture; SC7 coverage
    now via studio-agent-crud, connector a11y via connector-editor-keyboard-a11y).
- **Ledger**:
  - **innerHTML sink baseline** — unchanged this leg (zero source changes; verification +
    spec-authoring only). Legs 01–05 recorded their sink deltas; the sink-baseline test
    stayed green in `make test-unit` here.
  - **Registry** — no new `data-testid`s (this leg adds none; the CRUD spec references
    existing testids `new-agent-btn` / `tab-general` / `save-agent-btn` / `delete-agent-btn`).
    `docs/ui-testid-registry.md` needs no update.
  - **Chip-list `label[for]` runtime-dangle — carried forward to F7.** The visual pass
    re-observed the two mcp-editor chip-list fields (`mf-args`,
    `mf-sandbox-writable-paths`) whose `<label for=…>` targets are stripped from the
    `.chip-list-editor` div at mount (`mountChipListEditors`), so the runtime `for` resolves
    to nothing. **Pre-existing, cross-editor, NOT a Leg-05-flight regression** (source markup
    byte-identical; static label-assoc guard scans source where the id is present). Flagged
    Leg 04; **carried to Flight 07 (System)** as a systemic chip-list a11y pass.
  - **Browser wall-clock via lanes** — studio lane 7:38; full suite 12:33; unit 5:28.
    The lanes deliver the intended tax-reduction: a studio-only verification pays ~7.5min,
    not the full ~12.5min.
- **8484 untouched**; theme preference on 8485 recorded (unset / `null`) and restored to
  unset; seeded discord connector (`9cd2f753f61b`) deleted (connectors list back to empty);
  own CDP tab closed (operator's original page left intact).

### Leg 05 — browser-lanes-guards-docs (landed)

- **Per-area browser lanes** — added a `--lane {chat|studio|system|shared}`
  selector to `scripts/run-tests.sh`. `run-tests.sh` already forwarded `"$@"`
  straight to `pytest`; the lane block parses `--lane` out of the args, expands
  the lane's basename globs to real files under `tests/browser/`, and rebuilds
  the invocation as `-m browser <files…> <remaining-args>` (mirroring
  `make test-browser` semantics). No new deps, no per-test markers — pure bash.
  - `chat` = `test_flow_chat*` + `test_flow_markdown_chat` + `test_flow_new_chat`
    + `test_flow_streaming` + `test_flow_context_overlay_thresholds` +
    `test_flow_usage_restore`; `studio` = `test_flow_studio_*` + `test_studio_*`
    + `test_connector_*` + `test_mcp_*` + `test_flow_agent_*` +
    `test_flow_connector_*`; `system` = `test_flow_admin_*` + `test_flow_provider_*`.
  - **`shared` is the COMPLEMENT** (all browser test files minus the three area
    lanes and the pixel-only `test_visual_snapshots.py`). This is the key design
    choice: it makes "no file orphaned" a structural guarantee — the four lanes'
    union is *always* exactly the browser suite, and any newly added
    `tests/browser/test_*.py` auto-lands in `shared` until it earns an area glob.
    The DD's literal `chat`/`shared` enumerations would have orphaned ~14 files
    (agent, connector_detach, mcp, streaming, context/usage overlays,
    dirty_confirm, cross_area_dirty_gate, picker, theme_toggle_cleanup, seeders);
    the complement + broadened area globs cover them all.
  - **Union verified with a count/diff**: the four lanes collect **569** tests,
    identical to `-m browser tests/browser/` (569 collected, 12 pixel deselected),
    with zero overlap (unique == with-dupes) and zero orphaned browser-marked
    files. Per-lane counts: chat 49, studio 255 (252+3 skip), system 92,
    shared 173 (170+3 skip).
- **dirty-back confirm-dialog flake fix** — `App.confirmDialog` appends the
  overlay and focuses Cancel *synchronously* (`dialog.js`), so there is no rAF /
  transition to sync on; the flake is pure event-loop scheduling delay under
  load overrunning Playwright's default expect timeout. Added a documented
  `_DIALOG_TIMEOUT = 8000` module constant in `test_flow_dirty_confirm.py` and
  applied it to every confirm-dialog-appears assertion (negatives left at default).
  Ran `test_flow_dirty_confirm.py` 3× standalone (20 passed each) + once inside a
  green `shared` lane — no flake.
- **markdown.js comment** — corrected the header comment "18 node-type string
  constants" → "19" (the sole sanctioned product-source touch: a comment;
  `NodeType` freezes 19 — DOCUMENT … HARD_BREAK). `test_markdown.py` green (it's
  browser-marked, ran green inside the `shared` lane).
- **Guards/registry bookkeeping** — no-op this leg. Legs 1-4 each recorded "no
  new `data-testid`s; registry unchanged," and the Leg 01 label-association
  guards (`test_ui_guards.py`) run green inside `make test-unit`. Nothing to
  reconcile in `docs/ui-testid-registry.md`.

**Verification**: `make test-unit` green (**3779 passed**, 10 skipped); all four
lanes independently green via `PYTHON=.venv/bin/python bash scripts/run-tests.sh
--lane …` (chat 49 / studio 252+3 / system 92 / shared 170+3); ruff check +
format clean on every edited file. No product-source changes beyond the one
markdown.js comment.

### Leg 01 — agent-surface (landed)

- **Re-skin decisions**: studio.css was already 0-alien (F2); the agent-editor
  tab strip, grid, and 5 tab modules already consume the F3 tile / `.btn-*` / `.tab`
  vocabulary — no new per-area CSS was needed beyond the field migration. The
  Knowledge tab stays a stub. Re-skin verified by CDP computed-style + focus in
  both themes (2px accent `focus-visible` outline, correct label/input/VRAM tokens).
- **.field-group migration**: general-tab's 6 `.field-row` sites → `.field-group`
  (stacked, label above, `label[for]`→control `id` preserved verbatim). The flight
  DD said "general-tab 7 / studio.js 3"; the true counts are **6 in general-tab**
  (system_prompt is a bare textarea + visually-hidden label, never a field-row) and
  **0 in studio.js** (its only `.field-row` references are wrapper skip-logic in
  collectFormData, not render sites). The `.model-capabilities` 112px gutter pad
  was dropped (stacked fields align flush-left).
- **Gutter exception LEFT in place**: verified general-tab is NOT the sole consumer
  of `.area-studio .field-row .field-error` (studio.css:896-900) — connector-editor,
  mcp-server-editor, discord-form, connectors-tab still render `.field-row`. Deletion
  rides the connector-editor-core leg per the flight DD.
- **M07 copy**: Built-in Tools tab now opens with a lazy-semantics intro paragraph
  ("tools the agent CAN load", agent loads on demand). Rendered via createElement /
  textContent (no new innerHTML sink). The "N / M enabled" count word reviewed and
  kept (accurate for CAN-load semantics).
- **Save-race fix + test**: added the null-`found` else fallback to the agent-editor
  save re-select (studio.js ~2489) mirroring `handleDeleteEditor` / `_refresh` —
  a concurrent delete between PUT-resolve and loadAll now falls to first-agent /
  empty instead of stranding a stale editor. Tested deterministically in
  `tests/browser/test_flow_studio_agent_save_race.py` by route-stubbing the post-PUT
  loadAll to return `[]` (the exact "agent vanished" observable) — not a wall-clock
  race. JS has no unit harness, so the DD's sanctioned route-stub form was used.
- **Composite gates + ratios**: two new gates in test_design_tokens_a11y.py.
  (1) VRAM/model warning — `--status-warning` text on the composited
  `--status-warning-bg-soft` fill (body AA ≥4.5, both themes, over bg/surface/elevated).
  Light `#a16207` failed at ≈4.42 / 4.27 / 4.04, so it was deepened to **#8f5606**
  (amber-700; now 5.34 / 5.14 / 4.88) with the soft washes tracking the base hue —
  the exact fix-then-gate move as the F3 danger `#dc2626→#b91c1c` deepen. Dark warning
  `#fbbf24` unchanged (8.55–9.84). (2) Indeterminate tool-switch thumb — solid
  `--accent` on the composited `--accent-translucent` track (UI ≥3.0, both themes:
  dark 5.29, light 5.70). design_tokens.py mirror updated in lockstep.
- **Label-association guards (firm AC)**: two static-source guards in test_ui_guards.py
  — every literal `label[for]` resolves to a control `id` in the same file, and every
  `.is-invalid` control's `aria-describedby` resolves to a `.field-error` `id`. Both
  probe-tested (synthetic broken snippet flagged; correct one passes). Two pre-existing
  connector-editor for-targets whose ids come through a concatenation helper
  (`renderLifecycleSelect`) are allowlisted in `FIELD_FOR_ID_HELPER_INDIRECTED` (the
  testid-registry manual-exception pattern) so the global scan stays false-positive-free.

**Verification**: unit lane 3812 passed / 18 skipped / 0 failed; a11y+guards+mirror+token
suites green (142); affected studio browser slice + F4 markdown suite green (154 passed);
full pixel suite green (12) after regenerating the two `studio-with-agent` baselines
(gitignored, local-only); ruff clean.

---

### Leg 02 — connector-editor-core (landed)

- **Re-skin decisions**: like Leg 01, studio was already 0-alien (F2) and the
  connector surface already consumes the F3 tile / `.btn-outlined-primary` /
  `.entity-tile-*` / `.section-title` / `.indicator-led` vocabulary — no new
  per-area CSS was needed for the re-skin beyond the field migration. The
  re-skin work reduced to (a) dropping the redundant `admin-pf-input
  admin-pf-select` composition from migrated `<select>`s (the vocabulary
  `.field-input`/`.field-select` already carry surface + hairline + pinned
  focus; the `admin-pf-*` classes only duplicated a focus-visible rule) and
  (b) migrating form-field rows to `.field-group`. **connectors-grid.js needed
  ZERO changes** — it already renders pure vocabulary (`entity-tile`,
  `entity-tile-badge`, `page-header`, `empty-canvas`).
- **`.field-row`→`.field-group` migration — TRUE counts**: the flight DD /
  leg said "24 (connector-editor 22 + connectors-tab 2)", but that was a
  grep-line count. The 22 connector-editor matches included 2 `[data-field-row]`
  querySelectors + 3 comments; the real render sites are **17** (connector-editor)
  + **2** (connectors-tab). Of the 17, **12 are genuine label+editable-control
  form fields** (migrated to `.field-group`), **3 are the dense ACL editor rows**
  (kept label-left — documented exception, see Decisions), and **5 are chrome**
  (status/action rows: allowlist-banner, live-status, Validate/test, pairing
  status + pairing-reveal — LED / button rows, not form fields; left as
  `.field-row` layout). Same "counts are approximate" pattern Leg 01 hit
  (7→6, 3→0). **Migrated 13 rows total** (11 connector-editor + 2 connectors-tab):
  name, type, config, Chat-session-window, Idle-timeout, Always-Listen,
  Inference-provider, Inference-model, Default-agent (routing), + connectors-tab
  Allow-DMs & Always-listen. All carry `label[for]`→control-`id` association
  (the 2 helper-indirected `renderLifecycleSelect` targets stay resolvable via
  the `FIELD_FOR_ID_HELPER_INDIRECTED` allowlist — comment refreshed; they are
  now `.field-group` sites but their `<select>` id is still helper-emitted).
- **New shared vocabulary primitive `.field-group-label`** (components.css):
  a flex row that keeps a field-group's `<label>` + inline `.field-info-icon`
  tooltip on ONE line above the stacked control (label + icon stay SIBLINGS —
  never nest interactive content in `<label>`). The 6 info-icon fields consume
  it; Legs 3/4 (discord-form / mcp) can reuse it. Not a per-area variant (lives
  in components.css, area-agnostic). The `.field-group > label` style selector
  was extended to `.field-group-label > label` so wrapped labels keep the look.
- **GUTTER EXCEPTION DELETED HERE (not deferred to Leg 4)**: proved by grep that
  connector-editor's name/type rows were the **sole + last** consumers of the
  `.area-studio .field-row .field-error` 100px-gutter block AND the
  `.field-error-highlight` border/label rules — discord-form (Leg 3) and
  mcp-server-editor (Leg 4) render `.field-row` but **zero** `.field-error` /
  `.field-error-highlight` (grep-verified); general-tab (Leg 1, migrated) never
  used them. So the entire studio.css:888–911 block was removed in THIS leg. The
  inline name/type validation was rewritten onto the vocabulary: `setFieldError`
  now toggles `.is-invalid` + `aria-invalid` + `aria-describedby` on the CONTROL
  (was `.field-error-highlight` on the row) and shows the `.field-error` message
  span (now carrying an `id` for the describedby link); the components.css
  `.field-input.is-invalid` border + un-scoped `.field-error` render it with no
  gutter. components.css comment updated to record the retirement.
- **M12 F4 keyboard a11y PRESERVED verbatim**: only wrapper classes / chrome
  changed. `data-routing-drag-handle` (tabindex-0 reorder handle + both keydown
  handlers), `data-routing-live-region` (aria-live polite), the
  `connector-live-status` / `-error-wrap` (aria-live / role=alert) are byte-for-
  byte intact (grep-confirmed at leg end). The routing-rule reorder table and its
  per-rule `<td><select>`s were left entirely untouched (the a11y-sensitive zone).
- **Composite-a11y gate (connector wash)**: added
  `test_connector_empty_types_banner_prose_passes_body_aa` — `--fg` banner prose
  ≥4.5:1 on the composited `--status-warning-bg-soft` wash, over bg/surface/
  surface-elevated, both themes (the NEW coverage). The banner's `--status-warning`
  `<strong>` reuses the EXACT pair already gated by Leg 01's
  `test_warning_text_on_soft_fill_passes_body_aa`, so no duplicate assertion; the
  `<code>` sits on a solid surface (fg-ladder covers it, not composite-gated).
  No token VALUES changed → the `design_tokens.py` mirror (single source the a11y
  test imports) already carried every token the gate reads; no mirror edit needed.

**Verification**: unit lane **3818 passed** / 18 skipped / 0 failed (+6 = the new
gate, 2 themes × 3 surfaces); a11y+guards+token suites green (149); connector +
connectors-tab browser slice green — connector_editor / dm_admission_row /
inference_provider_row / routing_dropdown / create_and_test / navigation (54) +
per_agent_admit_dms / always_listen_toggles / per_agent_overlay_dropdown /
allowlist_dropdown / discoverable_dropdown / invite_section / detach / live_status /
test_connection / form_registry / discord_form / discord_vocabulary (74); markdown-chat
+ keyboard flows green (10); pixel suite green (12, **no drift** — no connector
baseline exists and the agent-editor `studio-with-agent` baseline is untouched, so
NO regeneration needed); ruff + format clean. **Both themes** verified on a fresh
CDP page (ignoreCache): keyboard `:focus-visible` = true with a 2px solid `--accent`
outline (dark `#a78bfa` / light `#6d28d9`) on the migrated `cf-name`; `.is-invalid`
renders the `--status-danger` border (dark `#f87171` / light `#b91c1c`); the
`.field-error` message renders danger, 11px, **margin-left 0** (gutter gone); the
info-icon `.field-group-label` renders flex with label + icon inline above the
stacked control. Dark + light `printToPDF` pixels captured.

---

### Leg 04 — mcp-surface (landed)

- **Re-skin decisions**: like Legs 1-3, studio was already 0-alien (F2). The MCP
  surface splits three ways: **mcp-server-editor.js** carried all 11 `.field-row`
  render sites (the only file that needed edits); **mcps-tab.js** (agent-editor MCPs
  tab) and **mcp-servers-grid.js** already render pure vocabulary (mcp-source-tile
  echoing `.entity-tile`, `page-header`, `empty-canvas`, createElement-based) with
  ZERO `.field-row` — no changes, matching the connectors-grid/mcps-tab precedent
  from Legs 1-2.
- **`.field-row`→`.field-group` migration — TRUE count is 11 render sites, not 12.**
  The DD's "12" is a grep-line count (one of the 12 grep hits is a `// ...field-row...`
  comment, line 522) — the same inflation Legs 1-3 hit (general-tab 7→6, connector 22→17,
  discord 8→4). Of the 11 render sites: **9 are genuine label+editable-control form
  fields** (migrated to `.field-group` with `label[for]`→control-`id` association):
  name (`mf-name`), type (`mf-type` select), command-runtime (`mf-command-runtime`
  select), custom-command (`mf-command`), working-directory (`mf-cwd`), arguments
  (`mf-args` chip-list), url (`mf-url`), sandbox network-toggle
  (`mf-sandbox-network-allowed`), sandbox writable-paths (`mf-sandbox-writable-paths`
  chip-list). **2 are chrome** (empty `<label></label>`, not form fields):
  the `.mcp-test-row` (Refresh-connection button + LED + last-updated cluster) and
  the `.mcp-command-hint-row` (dynamic args helper text).
- **Network toggle stacked** (like Leg 2's connectors-tab Allow-DMs): the
  `Allow network access` label now sits ABOVE the `.tool-enable-switch` (the
  `.field-group` column flex), replacing the old 2-column label-left toggle. No
  `.mf-sandbox-network-row` CSS rule exists (only comments reference it), so nothing
  broke. Verified via CDP: the group renders `flex-direction: column` with the switch
  below the label.
- **`.mcp-command-hint-row` de-guttered** (chrome, but alignment-coupled): its whole
  purpose (per the CSS comment) was to line the args helper text up under the
  *label-left* args chip-list via a 100px empty-label gutter. The migration moved args
  to stacked flush-left, invalidating that alignment. So the empty `<label>` +
  `.field-row` wrapper were dropped and the hint now renders flush-left directly under
  the args `.field-group` (a small negative top-margin snugs it). The now-dead
  `.area-studio .mcp-command-hint-row label` CSS rule was removed and the comment
  refreshed. CDP-confirmed: `.mcp-command-hint-row` has no `<label>` and the hint
  aligns flush with the args chip-list above.
- **`.mcp-test-row` KEPT as `.field-row`** (chrome): the Refresh-connection action
  cluster stays `field-row admin-pf-row mcp-test-row` with its empty label — this
  exactly mirrors the connector-editor's `.connector-test-row` (Leg 2 precedent:
  chrome action rows keep `.field-row` layout), so the two editors read consistently.
  The shared `.mcp-test-row, .connector-test-row { margin-top: 8px }` rule is untouched.
- **The env kv-table is NOT a `.field-row`** — it is rendered by `renderKvTable` as its
  own `.section-title` + `.mcp-kv-table` tabular structure (KEY / VALUE / SENSITIVE
  columns). So the leg's "env kv-table dense exception" question resolves cleanly: there
  was nothing to migrate there and no exception to document — it was never part of the
  `.field-row` family. CDP-confirmed 0 `.field-row` inside `.mcp-kv-table`.
- **No new composite-a11y gate.** The migration is class-swaps only — no new alpha wash
  carrying text was introduced. The `.mcp-auth-required-notice` (studio.css:702) uses a
  SOLID `--surface-elevated` bg (not composite-gated; fg-ladder covers it), exactly as
  the leg predicted. No `_alpha_composite` reconstruct needed this leg.

**Verification**: unit lane **3779 passed** / 10 skipped / 0 failed (make test-unit,
includes a11y + token + label-association guards + sink-baseline); ruff check + format
clean; label-association guards green (test_ui_guards.py, 14). MCP browser slice via
`run-tests.sh` (`PYTHON=.venv/bin/python`): `test_flow_studio_mcp_editor.py` **47
passed**, `test_studio_mcps_tab.py` **8 passed**, `test_flow_studio_mcp_navigation.py`
+ `test_mcp_test_connection_button.py` **12 passed / 1 skipped** — all green run
per-file (a few 8s-timeout flakes appeared only when 4 files ran back-to-back under
concurrent uvicorn-startup load; every test passes clean in isolation / per-file, the
documented run-tests.sh load-flake pattern). **Both themes** verified on a fresh CDP
page (chrome-devtools, `ignoreCache` reload — the JS is served with a static
`?v=<appversion>` that didn't bump on restart, so a plain reload reuses the old
module, per the Leg 3 deviation): 9 `.field-group` + 1 `.field-row` (the kept chrome
test-row) + 0 `.admin-pf-*`; keyboard `:focus-visible` = 2px solid `--accent` (light
`#6d28d9` / dark `#a78bfa`) on `mf-name` / `mf-type`; network toggle stacked; args hint
flush-left. A seeded stdio MCP source (`POST /api/mcp-sources`, `DELETE`d after) backed
the edit-mode visual pass; 8484 not touched; theme preference on 8485 recorded (unset,
real key `theme-preference`) and restored to unset.

---

### Leg 03 — discord-and-dropdown (landed)

- **`.field-row`→`.field-group` migration — TRUE count is 4, not 8.** The flight
  DD's "discord-form 8" was a grep-line count (same inflation Legs 1-2 hit:
  general-tab 7→6, connector-editor 22→17). connector-form-discord.js has exactly
  **4 `.field-row` render sites**, all migrated to stacked `.field-group`:
  (1) **Bot status** (presence — compound type-select + name-input; "Bot status" is a
  GROUP caption, each inner control keeps its own visually-hidden `<label for>`);
  (2) **Additional Config** (kv-table inside the `<details>` Advanced disclosure — the
  pseudo-label is a `<div>`, no single control to bind `<label for>` to);
  (3) **Bot Token** (the one genuine single-control field with a real `label[for]`);
  (4) **Invite link** (URL display + copy/refresh — a caption over a display row).
  The 3 info-icon rows (presence / Bot Token / Invite) reuse Leg 2's shared
  `.field-group-label` primitive (label + icon siblings on one line above the control).
- **Bot-Token info-icon un-nested from its `<label>` (a11y fix).** Pre-leg the
  `.field-info-icon` `<button>` sat INSIDE `<label for="cf-discord-bot-token">` — a
  `<button>` nested in a `<label>` is invalid HTML and a click-target ambiguity. The
  migration moves it into `.field-group-label` as a sibling of the label (the canonical
  vocabulary shape). `label[for]`→control-id association confirmed intact (CDP).
- **discoverable-dropdown group-header quieted — CSS ONLY.** The sole alien remnant
  (`.discoverable-dropdown-group-header`: `font-family: mono` + `text-transform:
  uppercase` + `letter-spacing: 1px`, studio.css) was dropped; now a plain muted small
  caption in the body font (Geist) at weight 500. CDP computed style confirmed both
  themes: `font-family` Geist (not mono), `text-transform: none`, `letter-spacing:
  normal`. The dropdown's `--surface` menu bg + `--border` hairline + `--shadow-popover`
  are unchanged (already on-vocabulary).
- **WAI-listbox keyboard a11y PRESERVED verbatim.** `discoverable-dropdown.js` was NOT
  touched — the change is entirely in studio.css. `git diff --stat` shows ZERO diff on
  the JS file. Grep-confirmed intact at leg end: `role="combobox"` /
  `aria-autocomplete` / `aria-haspopup="listbox"` / `aria-controls` /
  `aria-activedescendant` on the input, `role="listbox"` on the menu, `role="option"` /
  `aria-selected` on items, and the ArrowUp/Down/Enter/Escape/Tab handlers in
  `_handleKeydown`. The a11y reviewer gates this at flight close.
- **Composite-a11y gate (dropdown focus/hover wash).** Added
  `test_discoverable_dropdown_hover_item_text_passes_body_aa` — the hovered/focused menu
  item paints `--fg` text on the `--accent-translucent` wash, which composites over the
  menu's solid `--surface` bg (NOT `--bg`). The gate reconstructs `--accent` at the
  theme's `--accent-translucent` alpha over `--surface` and asserts `--fg` clears body
  AA (≥4.5:1), both themes — mirrors the existing `test_tinted_user_bubble_text` pattern
  but over `--surface`. No new token → no `design_tokens.py` mirror edit (the alpha,
  `--accent`, `--surface`, `--fg` were all already mirrored). The `aria-selected`
  `--accent`-on-`--surface` case is pre-existing (covered by the UI ladder ≥3.0), not
  re-gated.

**Verification**: unit lane **3779 passed** / 15 skipped / 0 failed (+2 = the new
dropdown gate, 2 themes); a11y+guards+token suites green (151); discord + dropdown
browser slice green — `discoverable_dropdown` / `discord_form` / `discord_vocabulary`
(26 passed via `run-tests.sh`, `PYTHON=.venv/bin/python`); ruff + format clean; sink
baseline unchanged (class-string edits + added wrapper divs in the existing
string-concat `innerHTML` render — no `innerHTML`→`createElement` migration). **Both
themes** verified on a fresh CDP page (ignoreCache): all 4 discord rows render
`display: flex; flex-direction: column` (stacked); `#cf-discord-bot-token`'s
`label[for]` resolves and its info-icon is a label SIBLING (not nested); group-header
computed style de-aliened; keyboard `:focus-visible` = true with a 2px solid `--accent`
outline on the presence-type select / bot-token input (dark `#a78bfa` / light
`#6d28d9`). Dark + light `printToPDF` pixels captured. A seeded discord connector
fixture (created via `POST /api/connectors`, deleted after) backed the visual pass;
8484 not touched; theme preference on 8485 recorded (unset) and restored to unset.

---

## Decisions

- **Deepened light `--status-warning` #a16207→#8f5606** to clear the new VRAM
  soft-fill composite gate (body AA). Safe: no text sits on a `--status-warning`
  FILL anywhere (all fill uses are bars/LEDs/dots), so every warning consumer only
  gains contrast on light backgrounds. Soft washes (`-bg-soft`, `-bg-soft-2`,
  `-border`) retuned to the new base hue to keep the family matched.
- **Save-race tested via route-stub, not JS unit.** No JS unit-test harness exists
  in this repo; the DD explicitly permits "a route-stub forcing DELETE-during-PUT
  ordering" as the deterministic alternative to a wall-clock browser race.
- **(Leg 02) ACL editor rows kept label-left as a documented exception.** The three
  dense ACL rows (DM admission select + peers chiplist + servers/guilds chiplist,
  studio.css:1199 `flex:1` slot rule) form one cohesive 3-column `label | info-icon |
  chiplist/select` editor. The flight DD explicitly permits keeping a "3-column dense
  layout label-left as a documented, gated exception"; migrating only some of the
  section to stacked would read broken beside the rest, and the chiplist rows host
  the complex `_mountAllowlistHierarchicalEditor` mount. Default-to-label-above was
  applied everywhere else. Chrome status/action rows (banner / live-status / Validate /
  pairing) also stay `.field-row` — they are LED/button layout rows, not form fields.
- **(Leg 02) Gutter exception DELETED in this leg, not deferred to Leg 4.** The leg
  anticipated the exception surviving to Leg 4, but grep proved connector-editor's
  name/type rows were its sole + last consumers (discord-form + mcp-server-editor
  render `.field-row` with zero `.field-error`/`.field-error-highlight`). Deleting
  here is within AC #3 ("deleted here if last consumer"). Legs 3/4 therefore do NOT
  re-touch this rule.

---

## Deviations

- **(Leg 05) The dirty-back confirm-dialog flake fix extended to the sibling
  provider file.** The leg scoped the flake fix to `test_flow_dirty_confirm.py`
  (studio), but hedged "or wherever the dirty-back confirm test lives — grep for
  it." Running the new `system` lane surfaced the *same* modal-under-load flake in
  `test_flow_provider_dirty_confirm.py` (`test_dialog_escape_cancels`), whose
  confirm-dialog-appears assertions used timeouts as low as 3s — tighter than
  default, so more flake-prone. Applied the identical `_DIALOG_TIMEOUT = 8000`
  fix there (same modal, same `dialog.js` synchronous-append root cause). Both are
  "dirty-back confirm" tests, so this is within the leg's flake-fix intent, not
  scope creep. Test-only.
- **(Leg 05) `test_flow_admin_tools_editor::test_editor_field_change_clears_highlight`
  was a collateral load-flake, not fixed directly.** It failed once in the first
  `system` lane run but is a *different* flake class — a 422 server round-trip
  (`.editor-error-banner` visibility), not a confirm modal — and is outside the
  leg's confirm-dialog flake scope. It passes in isolation, and once the provider
  modal's tight-timeout waits were relaxed (lightening the lane's back-to-back
  load) the `system` lane went green with this test passing. Left as-is; noted as
  a candidate 422-roundtrip-timeout tidy for a future test-infra pass.
- **(Leg 05) Lanes cover 14 files the DD's literal enumeration would have
  orphaned.** The DD listed `chat`/`shared` as fixed name lists that did not
  mention agent/connector_detach/mcp/streaming/overlay/dirty_confirm/cross_area/
  picker/theme_toggle_cleanup/seeders. Rather than a brittle enumerated `shared`,
  `shared` is implemented as the complement and the area globs broadened, so the
  AC's "no file orphaned" holds by construction and survives future test additions.
- **Label-association guards landed as STATIC source guards in test_ui_guards.py**
  (the AC's named file) rather than a DOM guard. test_ui_guards.py is a pure
  repo-source linter with no browser fixture; a literal `for`→`id` / `aria-describedby`
  →`.field-error` scan covers the general-tab migration (all literal ids) and catches
  the "easy silent-drop", with a documented allowlist for the 2 helper-indirected
  connector for-targets. The `.is-invalid`→`.field-error` clause is vacuously green
  today (no JS renders inline `.is-invalid` HTML-string validation — studio uses
  `.field-error-highlight` on the row) but is frozen for future inline-validation sites.
- **Field-row counts differed from the flight DD** (general-tab 6 not 7; studio.js 0
  not 3) — see Leg Progress. No functional impact; the DD's per-editor total (54)
  should be treated as approximate.
- **(Leg 02) connector-editor field-row count is grep-inflated too** — "22" =
  grep-lines incl. 2 querySelectors + 3 comments; real render sites = 17 (12 form
  fields migrated + 3 ACL exception + 5 chrome). Migrated 13 total across
  connector-editor (11) + connectors-tab (2), not 24. Same "approximate" caveat.
- **(Leg 02) sink baseline unchanged.** connector-editor kept its existing string-concat
  `innerHTML` render path (migration only swapped wrapper class strings + dropped
  `admin-pf-*`); connectors-tab's two rows are createElement (className string change
  only). No innerHTML→createElement migration occurred, so the sink count did NOT
  move (neither direction) — the sink-baseline test stayed green in the unit lane.

- **Dev-server JS cache**: 8485 serves JS with a static `?v=<appversion>` param and
  no long-max-age cache-control, so a plain reload reused the pre-restart module.
  The visual pass used a fresh CDP page with `ignoreCache` reload to load the new JS.
  (Matches the "CSS not cache-busted; hard-reload per the doctrine" note — it also
  applies to JS when the app version string doesn't bump.)

- **(Leg 03) discord-form field-row count is grep-inflated too** — the flight DD's
  "discord-form 8" is a grep-line count; the real render sites are **4** (Bot status,
  Additional Config, Bot Token, Invite link), all migrated. Same "counts are
  approximate" caveat as Legs 1-2. Of the 4, only Bot Token is a single-control field
  with a true `label[for]`; the other 3 are group/section/display captions (no single
  control to bind), so label-association guards apply meaningfully to Bot Token only.

- **(Leg 04) mcp-server-editor field-row count is grep-inflated too** — the DD's "12"
  is a grep-line count including 1 comment line; real render sites = 11 (9 form fields
  migrated + 2 chrome kept). Same "counts are approximate" caveat as Legs 1-3. mcps-tab
  + mcp-servers-grid contributed 0 (already pure vocabulary), so the flight's per-file
  expectation ("editor + tab + grid") really only had editor work.

- **(Leg 04) Pre-existing chip-list runtime `label[for]` dangle — NOT introduced here,
  out of scope.** The two chip-list fields (`mf-args`, `mf-sandbox-writable-paths`) carry
  `<label for="mf-args">` / `<label for="mf-sandbox-writable-paths">` pointing at the
  `.chip-list-editor` div's `id`, but `mountChipListEditors` strips that `id` from the
  div at mount time, so at runtime the `for` target resolves to nothing (CDP-observed).
  This is **pre-existing** cross-editor chip-list behavior — the source markup (`for` +
  the div `id`) is byte-identical before and after this leg (only the wrapper class
  changed `field-row`→`field-group`), and the mount code was not touched. The static
  label-association guard stays green because it scans source (where the `id` is
  present). Flagged as a standing chip-list a11y gap for a future systemic pass, not a
  regression of this leg.

- **(Leg 04) Pixel evidence via chrome-devtools `take_screenshot` (ignoreCache), not
  goldfinch `printToPDF`.** goldfinch has no ignoreCache reload, so its tab kept serving
  the pre-restart cached JS (the static `?v=` footgun); the chrome-devtools MCP's
  `navigate_page reload ignoreCache` loaded the fresh module. Both-theme full-page
  screenshots captured from that fresh-JS page — equivalent pixel evidence, correct JS.

- **(Leg 03) `run-tests.sh` needs `PYTHON=.venv/bin/python`.** The script defaults to
  `${PYTHON:-python3}` (system python), which lacks `discord` → collection
  `ModuleNotFoundError`. `make test-browser` sets `PYTHON` to the venv; a bare
  `scripts/run-tests.sh` invocation must pass it explicitly. Non-blocking (env, not code).

---

## Session Notes

- No new `data-testid`s introduced; registry unchanged. Field control ids
  (`studio-name`, etc.) are `id=` attributes, out of the testid registry's scope.
- innerHTML-sink baseline unchanged: general-tab kept its single `panel.innerHTML = html`
  sink; the tools-tab intro is createElement/textContent.
- 8484 not touched. Theme preference on 8485 recorded (unset) and restored to unset.

---

## Flight Completion (2026-07-05)

Flight 5 (studio re-skin) **landed** across **6 legs** (agent-surface, connector-editor-core,
discord-and-dropdown, mcp-surface, browser-lanes-guards-docs, studio-verification). The studio
surface now reads as one calm vocabulary in both themes with **0 alien remnants** (SC1 dual-theme
CDP spot-check).

- **The `.field-row` grep-inflation pattern.** Every leg's DD field count was a grep-line count
  inflated ~1.4× over real render sites (querySelectors + comments + `[data-field-row]` matches
  padded the totals): general-tab 7→6, connector-editor 22→17 render sites, discord-form 8→4,
  mcp-server-editor 12→11. The flight DD's **54 nominal `.field-row`** resolved to
  **~32 real migrated form fields** (general-tab 6 + connector 13 incl. connectors-tab +
  discord 4 + mcp 9; the balance are documented ACL label-left + chrome exceptions). Treat per-editor field-row counts in future
  DDs as approximate — grep them to render sites before committing a leg AC to a number.
- **Both reviews confirmed.** The general Reviewer signed off `[HANDOFF:confirmed]`; the
  Accessibility Reviewer independently `[HANDOFF:confirmed]` after live-driving the
  discoverable-dropdown keyboard flow, grep-confirming the M12 F4 routing/live-region attrs
  intact, and recomputing every composite-gate contrast ratio.
- **Per-area browser lanes.** `run-tests.sh --lane {chat|studio|system|shared}` with `shared`
  as the **complement**, so the four lanes' union is *always* exactly the full browser suite
  (**569 = 569** verified, zero orphans) — a structural "no file orphaned" guarantee. A studio-only
  verification now pays ~7.5min, not the full ~12.5min. Documented in CLAUDE.md.
- **Chip-list `label[for]` runtime-dangle carried to F7.** The two mcp-editor chip-list fields
  (`mf-args`, `mf-sandbox-writable-paths`) have `<label for>` targets stripped from the
  `.chip-list-editor` div at mount, so the runtime `for` resolves to nothing. Pre-existing,
  cross-editor, NOT an F5 regression (source markup byte-identical; static guard scans source
  where the id is present). Flagged Leg 4; **carried to Flight 07 (System)** as a systemic
  chip-list a11y pass.
- **Two a11y polish fixes** (found by the a11y reviewer, applied at flight close): (a)
  `.field-info-icon:focus-visible` outline in components.css — the info-icon became a
  `.field-group-label` sibling across 4 editors (F5's migration amplified this) and was falling
  back to the browser's thin native focus ring; (b) fixed a pre-existing double-closing-paren
  typo at studio.css:934 (`var(--surface-elevated))` → `var(--surface-elevated)`) in the
  `.connector-empty-types-banner code` rule. `make test-unit` re-confirmed green
  (**3779 passed / 10 skipped**); ruff clean (CSS-only; no Python touched).
- **SC7 studio-agent-crud gate — RAN and PASSED both themes.** The
  `studio-agent-crud.md` spec (active, mock-provider precondition) was executed synchronously
  by the Flight-5 studio behavior-gate orchestrator on **2026-07-05-22-32-24**: **light 9/9
  checkpoints + dark variant 4/4, 0 failed**, both themes pass (run log
  `tests/behavior/studio-agent-crud/runs/2026-07-05-22-32-24.md`; spec `Last Run` updated
  accordingly). The re-skinned Agent Studio CRUD flow (create → grid → re-select/edit →
  two-step Danger-Zone delete) is verified end-to-end with backend-API corroboration and
  independent Witnessed validators. `captureScreenshot` was never needed (printToPDF +
  computed-style + a11y-tree evidence path); no apparatus wedge. **Studio's SC7 core-flow gate
  is green** — the studio down-payment on the mission-end both-theme SC7 sweep.
- **SC5 connector-editor-keyboard-a11y — NOT re-run against the re-skin; deferred to F7.** Its
  staleness was updated (8485 / prose; assertions unchanged) but its **last run is 2026-06-04**
  (pre-re-skin). A fresh RUN against the re-skinned connector editor is **deferred to F7**; the
  Accessibility Reviewer's live keyboard-a11y verification (dropdown flow live-driven, M12 F4
  routing/live-region attrs grep-confirmed intact) + the Leg 6 dual-theme visual pass evidence
  the interaction meanwhile. Non-blocking.
- **Commit hash**: <to follow — this flight-completion commit>.
