# Leg: cta-unification

**Status**: completed
**Flight**: [Shell and Shared Components](../flight.md)

## Objective

Unify the entity-grid create affordance (flight DD "CTA unification") and execute the studio cleanup bundle (dead `connector-test-status` queries + `KNOWN_DEAD_SELECTORS` entry).

## Scope (flight DDs authoritative)

- Product: delete `components.css:672` state-split rule + `:633` hover-reveal; header CTA always visible with icon + text label (vocabulary secondary/primary button per grid context); empty-state canvas CTA becomes the same component class; the four `-empty` button variants retire from the four grid JS files (`studio.js`, `providers-grid.js`, `mcp-servers-grid.js`, `connectors-grid.js` — empty-state canvases keep copy, their CTA uses the unified testid `new-{entity}-btn` via a second instance or event delegation to the same handler).
- Tests: ALL SIX consumers migrated (trio re-simplified: `test_flow_agent_crud`, `test_flow_provider_setup`, `test_flow_provider_grid` — delete the state-split assertions, assert the unified always-visible contract; entry-path trio migrated to the unified testid: `test_flow_studio_openrouter_picker`, `test_flow_studio_connector_navigation`, `test_flow_studio_mcp_navigation`).
- Registry: prune the 4 `-empty` rows (`docs/ui-testid-registry.md:164-171`).
- Cleanup bundle: remove dead queries `connector-editor.js:1775,1828` + the `KNOWN_DEAD_SELECTORS` entry (guard delta 3 — fail-stales).
- Mission KI entry for the state-split CTA: mark resolved with a pointer to this leg.

## Acceptance Criteria

- [x] Header CTA visible in BOTH empty and populated states, both themes (evidence); one testid family per entity
- [x] All six test files green via run-tests.sh (targeted run), then full studio/admin browser slice green
- [x] Registry sync guard green after pruning; dead-selector guard green after cleanup
- [x] `make test-unit` green; ruff clean; sink baseline: expected small shrinkage or neutral in the four grid files (justify)
- [x] Keyboard: CTA reachable/operable, pinned focus [a11y gate]

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry (registry/sink ledger); leg `landed`; checked off in flight.md; mission KI updated
