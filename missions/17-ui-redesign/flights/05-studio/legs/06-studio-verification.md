# Leg: studio-verification

**Status**: completed
**Flight**: [Studio Re-skin](../flight.md)

## Objective

Flight-wide studio verification: suites via the new lanes, dual-theme visual pass (CDP focus), AUTHOR the `studio-agent-crud` SC7 behavior spec + update the `connector-editor-keyboard-a11y` spec's staleness, retire the dead `studio-smoke`, and record the ledger. (The behavior-gate RUNS are executed by the Flight Director via a sync-crew sub-orchestrator after this leg lands — this leg AUTHORS + verifies-statically.)

## Scope

- Suites: `make test-unit`; the browser lanes (`studio` lane + a full-suite confirmation) via run-tests.sh (PYTHON=.venv/bin/python). Record counts + wall-clock; apply the pre-specified flake disposition.
- Dual-theme visual pass on 8485 (fresh CDP page, ignoreCache): the re-skinned studio surfaces — agent grid + editor (5 tabs), connector-editor (tabs/routing/allowlist), discord-form, mcp-editor, the discoverable-dropdown open state — both themes; focus via CDP (fields, buttons, tabs, dropdown). printToPDF pixels; record+restore theme preference; close own tabs; never touch 8484. SC1 spot-check: no alien remnants across the studio surface.
- **Author `tests/behavior/studio-agent-crud.md`** (status active; do NOT run — FD runs it): mock-provider agent CRUD. Preconditions: 8485 dev-mode; seed a mock provider (agent creation dead-ends without one — general-tab.js:56); clean up after. Steps (goldfinch apparatus + doctrine — printToPDF fallback, a11y-tree, CDP for focus): open Studio→Agents → click `new-agent-btn` → General tab (`tab-general`): fill name/description, pick provider/model → `save-agent-btn` → the agent appears in the grid → re-select + edit a field + save → delete via General-tab Danger Zone `delete-agent-btn` (TWO-STEP `App.confirmDelete` — the "Confirm Delete?" intermediate state is a judged checkpoint) → agent gone from grid. Both-theme variant. SC7 reference.
- **Update `tests/behavior/connector-editor-keyboard-a11y.md` staleness** (do NOT run — FD runs it): port 8484→8485 in Preconditions/Observables; apparatus note; the `// ROUTING`→`Routing` prose (the marker is retired); document the fixture re-seed (a connector with ≥3 routing rules — the "Discord Constellation" fixture is gone, so the spec's own "add rules if <3, restore on exit" fallback covers it, or seed a fresh connector). Assertions (keyboard reorder + live-region) UNCHANGED.
- **Retire `tests/behavior/studio-smoke.md`**: mark status `archived` with a note (draft/never-run, 8484, goldfinch, gone fixture; superseded by studio-agent-crud for SC7). Do NOT delete the file (history); flip status + add a superseded-by note.
- Ledger in flight log: per-file sink counts, registry state (no new testids expected), the chip-list `label[for]` runtime-dangle gap (flagged Leg 4 — carry to F7), browser wall-clock via lanes.

## Acceptance Criteria

- [x] Unit green; studio lane + full browser suite green (flake disposition applied); wall-clock recorded — unit 3779p/10s (5:28); studio lane 252p/3s (7:38); full `-m browser` 562p/6s + 1 load-flake disposed (passed in studio lane + 8/8 clean isolated rerun) (12:33)
- [x] Dual-theme visual pass evidence (both themes, enumerated studio surfaces + CDP focus); SC1 spot-check no alien remnants — agent grid+5 tabs, connector create+Advanced (routing/allowlist), discord-form, discoverable-dropdown (group-header de-aliened both themes), mcp-editor; 2px `--accent` `:focus-visible` (#6d28d9 / #a78bfa); zero alien remnants
- [x] `studio-agent-crud.md` authored (well-formed per ARTIFACTS.md, status active); NOT run here
- [x] `connector-editor-keyboard-a11y.md` staleness updated (8485, prose); assertions unchanged; NOT run here
- [x] `studio-smoke.md` archived with superseded-by note
- [x] Ledger in flight log (sinks, registry, chip-list gap carry-forward); ruff clean (no source changes); `git status` clean of snapshots

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md (behavior-gate RUNS noted FD-pending)
