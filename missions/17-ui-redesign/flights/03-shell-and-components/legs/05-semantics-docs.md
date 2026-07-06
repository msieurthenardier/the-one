# Leg: semantics-docs

**Status**: completed
**Flight**: [Shell and Shared Components](../flight.md)

## Objective

Element-scoped section-title heading fix + admin label quieting (flight DD "Section-title semantics"); agents.md vocabulary conventions + apparatus doctrine completion (flight DD "Apparatus doctrine completed").

## Scope (flight DDs authoritative)

- `h2.section-title { font-size: var(--font-size-h3) }` element-scoped ONLY (the `<label class="section-title">` at chat.js:136 must not inflate — verify).
- Admin `-pf-models-title`/`-pf-section-label` mono-uppercase → vocabulary label style.
- agents.md: component vocabulary conventions section (buttons/fields/tiles/tables/tabs/modals/toasts/empty-states/badges + one-primary-per-region + inline-validation rules); apparatus doctrine additions: UnknownVizError escalation, PDF fill-palette cross-check technique, goldfinch-cannot-observe-focus → CDP page for focus evidence.
- CLAUDE.md: only if commands/workflow changed (likely no).

## Acceptance Criteria

- [x] Heading bump verified on a real h2.section-title AND the chat label verified NOT inflated (both themes) — live computed-style probes (port 8485, hard-reload): `h2.section-title` = 15px (`--font-size-h3`), `label.section-title` = 12px (`--font-size-body-sm`), real chat "Select Agent" label = 12px, identical in dark AND light.
- [x] `grep -in "uppercase\|letter-spacing" the_one/interfaces/web/static/css/admin.css` → the two named labels (`-pf-models-title`/`-pf-section-label`) quieted; remaining hits are badges/chips/category-eyebrow/telemetry-value (justified — vocabulary primitives + F6-surface metadata, not section-heading labels).
- [x] agents.md greps: doctrine items present (UnknownVizError, fill-palette cross-check, hasFocus/CDP, getAnimations().finish()); no stale F3-pending vocabulary in the design section.
- [x] Suites green (unit 3743 passed / 15 skipped + guard slice 115 passed); ruff clean.

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
