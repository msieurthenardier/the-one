# Leg: consistency-fixes

**Status**: completed
**Flight**: [Hardening & Mission-End Acceptance](../flight.md)

## Objective

Close the two deferred cross-area items — the `.cap-chip` last eyebrow (SC1/SC3 consistency) and the pre-existing provider-editor H1/subtitle desync (F6-behavior-gate-caught) — and dispose of the aiosqlite `TestSchemaV17` warning. Re-verify the affected lanes.

## Scope (flight DDs authoritative)

- **`.cap-chip` un-scoped quiet**: admin.css:144 `.cap-chip` is already un-scoped (no `.area-admin`) — carries `text-transform:uppercase` + `letter-spacing:0.5px`, the last uppercase eyebrow (inconsistent with the F5/F6-quieted provider/tool badges). Drop uppercase + letter-spacing (keep size/padding + the `.chip` base + `.cap-chip-no-tools` danger ink). ONE rule change covers BOTH the admin Ollama panel (provider-models.js) AND studio's model picker + agent tiles (studio.js:1747/1383 via `window.App.admin.renderCapabilityChips`). Frame as a CONSISTENCY quiet, not an SC1-effect fix. Re-verify admin + studio lanes both themes.
- **H1/subtitle desync fix**: re-render the WHOLE header text block (`.editor-title` + `.editor-subtitle`) — NOT just the title. The subtitle (provider-editor.js:55-56, `provider.type · provider.base_url`) goes stale by the same mechanism (both editable). Fix in the edit→edit save success path: re-render title + subtitle from the `updated` provider `onSaveSuccess(updated,…)` receives (admin.js:319/335-337 + provider-editor.js:387-390). LOW RISK: display-only nodes, invisible to `getFormSnapshot`/dirty. Add an assertion-level browser regression check (edit name + base_url → save → assert H1 + subtitle updated). Re-verify system lane. (The mandatory Leg-3a system-provider-config re-run is the behavior-level proof.)
- **aiosqlite `TestSchemaV17` disposition**: the single-location "event loop is closed" teardown warning in tests/test_db_migration.py::TestSchemaV17 (not a failure). Either a small teardown-loop-alignment fix (if clearly low-risk) OR an explicit "accept + document" in the flight log with the rationale. State the decision.

## Acceptance Criteria

- [x] `.cap-chip` quieted (no uppercase/letter-spacing), both admin + studio, both themes (CDP visual — the capability chips render lowercase/sans matching the other quieted badges); `.cap-chip-no-tools` danger ink preserved
- [x] H1 + subtitle re-render on edit-save (name AND base_url/type edits reflected in the header); assertion-level regression check added + green; dirty/snapshot logic unaffected (getFormSnapshot still reads only data-field inputs)
- [x] aiosqlite disposition decided + recorded (fix + warning gone, OR accept + documented rationale)
- [x] system + studio + admin + chat lanes green via run-tests.sh (PYTHON=.venv/bin/python); make test-unit green (canonical, NOT -m live); ruff clean; label-association + sink + banned-token guards green; sink baseline honest

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
