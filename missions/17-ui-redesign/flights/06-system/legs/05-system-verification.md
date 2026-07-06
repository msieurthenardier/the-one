# Leg: system-verification

**Status**: completed
**Flight**: [System / Admin Re-skin](../flight.md)

## Objective

Flight-wide system verification: suites via lanes (system + cross-area studio + chat), dual-theme visual pass (CDP focus) over the re-skinned admin surfaces, AUTHOR the `system-provider-config` SC7 behavior spec, and record the ledger. (The behavior-gate RUN is executed by the Flight Director via a sync chrome-devtools sub-orchestrator after this leg lands — this leg AUTHORS + verifies-statically.)

## Scope

- Suites: `make test-unit` (record + reconcile the authoritative count — Leg 3 reported 3822, Leg 4 3781; run once and state the true number). The browser lanes: `system` + cross-area `studio` + `chat` (Legs 1-4 touched shared code) + a full `-m browser` confirmation via run-tests.sh (PYTHON=.venv/bin/python). Record counts + wall-clock; apply the pre-specified flake disposition.
- Dual-theme visual pass on 8485 (fresh chrome-devtools page, ignoreCache): the re-skinned admin surfaces — providers grid + editor (+ Ollama models panel), tools grid + editor (incl. a schema field with a chip-list), General page — both themes; focus via chrome-devtools (fields, buttons, tabs, chip-list input). printToPDF pixels; record+restore theme preference; close own tabs; never touch 8484. SC1 spot-check: no alien remnants across the admin surface (note the known `.cap-chip` cross-area eyebrow survivor — decide: quiet here via a safe area-scoped override, or defer to F7's sweep).
- **Author `tests/behavior/system-provider-config.md`** (status active; do NOT run — FD runs it): mock-provider config. Preconditions: 8485 dev-mode (the `mock` provider type is dev-gated-available + cred-less — name+type only). Steps (chrome-devtools apparatus — multi-step seed+drive; goldfinch wedges + lacks ignoreCache): Providers grid → `new-provider-btn` → editor: fill name + type=Mock(dev) → `save-provider-btn` → provider appears in grid as `provider-card` → re-select + edit + `test-connection-btn` → delete `delete-provider-btn` (agent-usage pre-gate + TWO-STEP confirmDelete — the "Confirm Delete?" armed state is a judged a11y checkpoint) → gone. Both-theme variant. DRIVE THE FULL UI CREATE (not the seed_mock_provider API helper). SC7 reference.
- Ledger in flight log: per-file sink counts, registry state, the `.cap-chip` cross-area survivor disposition, the authoritative unit count reconciliation, browser wall-clock via lanes.

## Acceptance Criteria

- [x] Unit green (authoritative count reconciled → 3781); system + studio + chat lanes + full browser suite green (zero flakes — disposition not invoked); wall-clock recorded
- [x] Dual-theme visual pass evidence (both themes, enumerated admin surfaces + CDP focus + a chip-list field); SC1 spot-check; `.cap-chip` survivor disposition stated (DEFER to F7)
- [x] `system-provider-config.md` authored (well-formed per ARTIFACTS.md, status active, full-UI-create, mock provider, both themes, two-step confirmDelete judged); NOT run here
- [x] Ledger in flight log (sinks, registry, cap-chip disposition, unit reconciliation, wall-clock); ruff clean; `git status` clean of snapshots

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md (behavior-gate RUN noted FD-pending)
