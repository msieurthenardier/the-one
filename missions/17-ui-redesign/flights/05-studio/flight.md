# Flight: Studio Re-skin

**Status**: landed
**Mission**: [UI Redesign — Clean, Professional, Consistent](../../mission.md)

## Contributing to Criteria

> Boxes stay unchecked — these are mission-end verification gates. The annotations record F5's share; F7 closes SC5/SC7 with the behavior-gate RUNS.

- [ ] SC1 — visual-language replacement. **F5 share**: all studio surfaces (agent grid + editor 5 tabs, connector-editor + tabs + discord-form, mcp-editor, discoverable-dropdown) re-skinned to the v3 quiet vocabulary; dual-theme CDP visual pass confirms **0 alien remnants** across the studio surface (both themes).
- [ ] SC3 — one component vocabulary. **F5 share**: studio consumes the vocabulary directly (no per-area variants); **32 real form fields migrated `.field-row`→`.field-group`** with full label-association (general-tab 6, connector 13, discord 4, mcp 9); the `.area-studio .field-error` gutter exception retired.
- [ ] SC5 — keyboard/AT operability. **F5 share**: keyboard a11y **preserved** — discoverable-dropdown WAI-listbox (JS zero-diff) + M12 F4 connector routing-reorder / live-region (grep-confirmed intact); a11y reviewer live-drove the dropdown keyboard flow. The `connector-editor-keyboard-a11y` behavior spec's staleness was updated but it was **NOT re-run against the re-skinned editor** (last run 2026-06-04, pre-re-skin) — its fresh RUN is **deferred to F7**; the a11y reviewer's live verification + the dual-theme visual pass evidence the interaction meanwhile.
- [ ] SC7 — behavior-verified core flows. **F5 share**: the `studio-agent-crud` gate **RAN and PASSED both themes** (2026-07-05-22-32-24 — light 9/9 checkpoints, dark variant 4/4; run log `tests/behavior/studio-agent-crud/runs/2026-07-05-22-32-24.md`, driven synchronously by the Flight-5 studio behavior-gate orchestrator). Studio's SC7 core-flow gate is green — the studio down-payment on the mission-end both-theme SC7 sweep.

---

## Pre-Flight

### Objective

Re-skin the Agent Studio — agents/knowledge/MCP-servers/connectors grids and their editors (agent-editor's 5 tabs, mcp-server-editor, connector-editor + connectors-tab + discord-form) — to the v3 quiet vocabulary, migrate all 54 `.field-row` (label-left, 100px gutter) form fields to the `.field-group` vocabulary with full label-association, restyle the discoverable-dropdown, fix the save→delete race, add the M07 F10 lazy-discovery label copy, introduce per-area browser test lanes, and verify with a new agent-create/edit behavior spec plus a re-run of the connector-editor keyboard-a11y spec (SC5 preservation).

### Open Questions

- [x] Discoverable-dropdown: rewrite or restyle? → Design Decisions (restyle — it's already ~on-vocabulary)
- [x] `.field-row`→`.field-group`: per-editor with the re-skin, or one migration leg? → Design Decisions (per-editor)
- [x] SC7 studio spec: reuse studio-smoke or author new? → Design Decisions (author new; studio-smoke retired)

### Design Decisions

**Consume the vocabulary directly, no per-area variants** (SC3): studio grids/tiles → the F3 tile/card + `.btn-*` vocabulary; tabs → the F3 tab treatment (already de-chamfered); modals → dialog.js vocabulary; badges → the F4-gated per-badge-ink badges; empty states → the vocabulary empty-state. studio.css is already 0-alien (F2); this flight replaces any remaining per-area treatments with vocabulary consumption, not new CSS. Any remaining mono-uppercase/`.section-description`-style per-area rules are quieted or lifted to components.css.

**`.field-row`→`.field-group` migration, per-editor** (F3/F4 debrief debt): all 54 `.field-row` sites (connector-editor 22, mcp-server-editor 12, discord-form 8, general-tab 7, connectors-tab 2, studio.js 3) migrate to the stacked `.field-group` primitive WITH full label-association (unique id, `label.for`→control id, invalid→`aria-describedby`→`.field-error` id — the gallery `fieldGroup()` reference at fields-section.js:24). The `.area-studio .field-error` 100px-gutter exception (studio.css:896-900) is DELETED when its rows migrate. Migration rides each editor's re-skin leg — the editor is open anyway. Where a 3-column dense layout genuinely needs label-left, keep it as a documented, gated exception (but default to label-above). NOTE: the `.area-admin .field-error` gutter exception (admin.css:445) is a SEPARATE, F6/System concern — NOT this flight's. **Migration-safety guards (firm per-leg AC, not optional)**: a guard asserting every `.field-group label[for]` resolves to a present control id, AND every `.is-invalid` control's `aria-describedby` resolves to a present `.field-error` id — since `fieldGroup()` is gallery-local (not exported) and all 54 sites hand-wire the triad, these guards catch the easy silent-drop. Consider extracting a shared `App.ui.fieldGroup` helper to remove per-site drift.

**Discoverable-dropdown: restyle, preserve a11y** (mission Open Question closed): the widget is already on-vocabulary (surface + `--border` + `--shadow-popover`, `discoverable-dropdown.js`/`studio.css:1527`). The ONE alien remnant is the group-header typography (mono + uppercase + letter-spacing, studio.css:1546-1552) — quiet it to the vocabulary label style. The WAI-listbox keyboard a11y (combobox/listbox roles, `aria-activedescendant`, ArrowUp/Down/Enter/Escape, roving focus — `discoverable-dropdown.js:181-194,503-605`) is PRESERVED verbatim; the a11y reviewer gates it. The focus/hover `--accent-translucent` wash carrying `--fg` text gets a composite-a11y gate.

**Save→delete race fix** (F1 debrief): agent-editor's save re-select (studio.js:2485-2503) is `if (found) {…}` with NO `else` — if a concurrent delete removed the agent between the PUT resolving and `loadAll()`, `found` is null and the block silently no-ops, leaving a stale editor. Both `handleDeleteEditor` (~1636) and `_refresh` (~2661) DO fall through to first-agent/empty. Add the same fallback to save's null-`found` branch. **Test as a UNIT test of the null-`found` fallback branch** (or a route-stub forcing DELETE-during-PUT ordering) — NOT a wall-clock browser race (the reviewer confirmed it's inherently racy at the Witnessed/browser level; the existing `test_flow_agent_crud.py:84-91` already fights this interleaving by syncing on `save_btn` disabled).

**M07 F10 lazy-discovery label copy** (mission KI re-scoped remainder): the "Built-in Tools" tab has no lazy-semantics copy. Author intro/subtitle copy conveying "tools the agent CAN load" vs "has loaded" (tone reference: the MCPs tab's "Expand to load tools…"); the category count word "enabled" (tools-tab.js:132,315) reviewed for lazy-accuracy. NO chat-time loaded-set indicator (out of scope per the mission note).

**Composited-a11y gates per leg** (F3/F4 discipline): studio washes carrying text — the indeterminate tool-switch (`--accent-translucent`, studio.css:66), the dropdown focus/hover wash (`--fg` on `--accent-translucent`, :1565), the connector-empty-types-banner soft wash (:926), **the VRAM/model warning (`--status-warning` text on `--status-warning-bg-soft`, studio.css:83 — the EXACT F3-headline soft-fill-fg genre, do NOT miss it)** — each gets an `_alpha_composite` reconstruct-and-gate test (rgba-over-one-known-surface), both themes, at the leg that touches it. `.mcp-auth-required-notice` (:695) uses a SOLID `--surface-elevated` bg → NOT composite-gated (fg-ladder sweep covers it). Solids are never composite-gated.

**Per-area browser test lanes** (F4 debrief decision — now ripe at 13:08 wall): introduce lanes (chat / studio / system / shared) so no single verification leg pays the full ~13min tax and F7's SC6 gate isn't a monolith. Files are cleanly area-prefixed (`test_flow_studio_*`/`_chat_*`/`_admin_*`/`_provider_*`); the "shared" lane is the cross-cutting bucket (`test_smoke`, `test_theme_cross_tab_sync`, `test_markdown`, `test_app_fixture`, `test_flow_keyboard`, `test_flow_hash_routing`, `test_oauth_modal_flow`). Implement as a run-tests.sh lane arg (path-glob) or markers (hand-rolled, no new deps); document in CLAUDE.md. Also fold in the **dirty-back confirm-dialog flake fix** (F3 rec 6 assigned to F5; F4 flagged it →F5): bump the 4s expect-timeout / add a wait-for-render sync point in `test_flow_dirty_confirm.py` (the studio module where it lives).

**SC7 studio behavior spec — author + RUN synchronously** (F4 lesson): studio-smoke.md is genuinely unfit (draft/never-run, 8484, goldfinch, gone "Discord Constellation" fixture — retiring it loses no regression coverage) — retire it; do NOT rely on it. Author `studio-agent-crud.md`: **precondition — seed/ensure a mock provider exists on 8485** (agent creation dead-ends on "No provider — configure in Admin" per general-tab.js:56 if none; dev-mode only makes mock *acceptable*, doesn't create it — seed via API/Admin, clean up after); then create an agent (`new-agent-btn` studio.js:402 → General tab `tab-general` → name/description/provider/model → `save-agent-btn` agent-editor.js:86), edit it, verify it in the grid, delete via the General-tab Danger Zone (`delete-agent-btn` general-tab.js:141 — a TWO-STEP `App.confirmDelete` arm-then-fire; the spec calls out the "Confirm Delete?" intermediate state for the Validator to judge) — both themes. Uses an existing/seeded provider; no connector fixture needed. **RUN it as a synchronous sub-orchestrator crew INSIDE the verification leg** (Executor/Validator spawned `run_in_background: false` — the F4 orphaning lesson).

**connector-editor-keyboard-a11y re-verify** (SC5, M12 F4 preservation): the spec (tests/behavior/connector-editor-keyboard-a11y.md, active, last 8/8) verifies keyboard routing-rule reorder + live-region announcements. Update its staleness (port 8485, apparatus per mission, the `// ROUTING`→`Routing` prose) and re-establish the required connector fixture with ≥3 routing rules (seed on 8485; delete after), then RUN it (sync sub-orchestrator) to confirm the M12 F4 keyboard/ARIA code survived the connector-editor re-skin. If re-seeding the exact fixture is infeasible, adapt the spec to a seedable connector — the deliverable is confirming the reorder-keyboard-a11y still holds post-re-skin.

**Guard bookkeeping** (standing): registry churn as grids/editors change testids (update docs/ui-testid-registry.md; expected: some churn as `.field-row`→`.field-group` adds field ids); sink baseline honest (studio re-skin may migrate static-template innerHTML → createElement, ratcheting DOWN — state per leg); the `.field-group label[for]` resolution could get a guard assertion. Fix the markdown.js "18"→"19" node-types comment while in docs (F4 debrief).

### Prerequisites

- [x] Flights 1-4 completed (vocabulary + tokens + shell + chat live)
- [x] Studio surface surveyed (submodule map, .field-row sites, discoverable-dropdown coupling, save-race path, fixture state)
- [x] 8485 mission dev instance; mock provider via dev mode for the agent-crud spec

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Re-skin surface by surface (agent-editor + agent grid → connector surface → MCP surface), migrating `.field-row`→`.field-group` and adding composite-a11y gates within each editor's leg; the save-race + M07 F10 copy ride the agent-editor leg; the discoverable-dropdown restyle + gutter-exception deletion ride the connector leg. Then a test-infra leg (browser lanes + guard bookkeeping + docs). Then verification: full suites (via the new lanes), dual-theme visual pass (focus via CDP), and the two SC5/SC7 behavior specs RUN synchronously inside the leg.

### Checkpoints

- [x] Agent surface (editor + grid + 5 tabs) to vocabulary, .field-group migrated, save-race fixed, M07 F10 copy in; composite gates green
- [x] Connector surface (editor + tabs + discord-form + grid + dropdown) to vocabulary, .field-group migrated, gutter exception gone, dropdown a11y preserved
- [x] MCP surface (editor + tab + grid) to vocabulary, .field-group migrated
- [x] Browser lanes in; guards green; docs (node-types) fixed
- [x] Suites green (via lanes); dual-theme visual pass; ledger — **behavior specs authored/updated (studio-agent-crud active; connector-a11y staleness updated); their RUNS are FD-pending** (Flight Director runs the Executor/Validator crews after this leg)

### Adaptation Criteria

**Divert if**: the `.field-group` migration breaks a dense 3-column editor layout beyond a documented exception (re-scope that editor's layout), or the connector-a11y re-verify can't re-establish a workable fixture (fall back to browser-test-level a11y confirmation + log).

**Acceptable variations**: exact studio CSS within the vocabulary; leg order among the three surfaces; keeping a documented label-left exception where a dense layout needs it.

### Legs

> **Note:** Tentative; created one at a time as the flight progresses.

- [x] `agent-surface` - agent-editor (General/Knowledge-stub/MCPs/Built-in Tools tab strip done once here) + agent grid to vocabulary; general-tab (6) .field-row→.field-group; M07 F10 lazy copy; save-race fix (route-stub regression test of the null-found fallback); VRAM-warning + tool-switch composite gates; label-association guards. **Landed.**
- [x] `connector-editor-core` - connector-editor (4956 LOC) + connectors-tab (agent-editor Connectors panel content) + connectors-grid to vocabulary; 13 .field-row→.field-group (of 17 real render sites; 3 ACL rows label-left exception, 5 chrome); retired the .area-studio .field-error gutter exception (connector-editor was its last consumer — NOT deferred to Leg 4); connector-empty-types-banner composite gate. **Landed.**
- [x] `discord-and-dropdown` - discord-form (4 real .field-row render sites → .field-group; "8" was grep-inflated) + discoverable-dropdown group-header quiet (a11y PRESERVED verbatim — JS zero-diff, roles+handlers grep-confirmed) + dropdown-wash composite gate. Bot-Token info-icon un-nested from its `<label>` (a11y fix). *(Split from connector-editor to isolate the a11y-sensitive dropdown work from bulk editor churn.)* **Landed.**
- [x] `mcp-surface` - mcp-server-editor migrated (9 real form-field render sites of the "12" grep count → `.field-group`; 1 chrome test-row kept as `.field-row` per the connector-test-row precedent; command-hint row de-guttered); mcps-tab + mcp-servers-grid needed ZERO changes (already pure vocabulary, zero `.field-row`); the env kv-table is not a `.field-row` (own tabular structure — no exception needed); a11y (label-assoc, MCPs-tab aria-expanded) preserved. **Landed.**
- [x] `browser-lanes-guards-docs` - per-area browser lanes (chat/studio/system/shared) via `run-tests.sh --lane` (shared=complement → union always = full suite; 569=569 verified) + CLAUDE.md; dirty-back confirm-dialog flake fix (test_flow_dirty_confirm.py; extended to sibling test_flow_provider_dirty_confirm.py — same modal-under-load root cause surfaced by the system lane); guard/registry bookkeeping no-op (Legs 1-4: no new testids, label-assoc guards already green); markdown.js node-types 18→19 comment fix. **Landed.**
- [x] `studio-verification` - suites via lanes (unit 3779p; studio lane 252p/7:38; full `-m browser` 562p/12:33 + 1 load-flake disposed) + dual-theme CDP visual pass (SC1 clean, both themes, all enumerated surfaces + focus) + **authored** studio-agent-crud.md (active, mock-provider precondition) + **updated** connector-editor-keyboard-a11y staleness (8485/Routing prose; assertions unchanged) + archived studio-smoke + ledger. **Behavior-gate RUNS are FD-pending** (this leg authors + statically verifies; the FD runs the sync Executor/Validator crews). **Landed.**

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [x] Tests passing (via lanes)
- [x] Flight log updated
- [x] Documentation updated (CLAUDE.md lanes; node-types fix)

### Verification

Studio renders the vocabulary in both themes (no per-area variants, no alien remnants); all `.field-row` migrated to `.field-group` with label-association (gutter exception gone); discoverable-dropdown restyled with a11y preserved; save-race fixed + tested; M07 F10 copy in; browser lanes work; `studio-agent-crud` passes both themes; `connector-editor-keyboard-a11y` re-passes (SC5 preserved); `shell-navigation-smoke` still passes; suites green; ledger honest.
