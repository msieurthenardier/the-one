# Flight Log: Studio — Agent Builder

**Flight**: [Studio — Agent Builder](flight.md)

## Summary

Legs 1-3 were implemented in a single session before flight artifacts were created (retroactive tracking). Tools API, sidebar, and editor panel are all complete. UAT leg is next.

---

## Leg Progress

### tools-api
**Status**: completed
**Started**: 2026-04-23
**Completed**: 2026-04-23

#### Changes Made
- Added `GET /api/tools` endpoint to `the_one/interfaces/web/api.py`
- Returns JSON array of `{name, description}` for all 14 built-in tools via `BuiltinToolProvider`

#### Notes
Minimal change — 7 lines of code. Import is deferred inside the handler to match the pattern used by agent endpoints.

---

### sidebar-and-crud
**Status**: completed
**Started**: 2026-04-23
**Completed**: 2026-04-23

#### Changes Made
- Replaced 19-line stub in `studio.js` with full sidebar implementation
- Agent list with active highlighting, hover-reveal delete button
- Inline delete confirmation (3-second red state)
- Create mode via "+" button
- Empty state message
- Dirty-state guard on agent switching (confirm dialog)

#### Notes
Implemented together with editor panel in a single pass (legs 2 and 3 were done atomically).

---

### editor-panel
**Status**: completed
**Started**: 2026-04-23
**Completed**: 2026-04-23

#### Changes Made
- Full editor form in `studio.js`: identity, LLM config, system prompt textarea, tool toggles (grouped by category with CSS toggle switches), MCP/KB chip attachment with add dropdown, max iterations, save/create button
- ~90 CSS rules added to `styles.css` under `.area-studio` scope
- Dirty tracking via JSON snapshot comparison
- Smart tool state mapping (all-on, blacklist, or whitelist based on count)
- Save sends POST (create) or PUT (edit) with error display

#### Notes
Tool categories are a static JS map matching the 14 tools from BuiltinToolProvider. If tools are added/removed in the backend, the category map in studio.js needs updating.

---

## Decisions

### Retroactive Flight Tracking
**Context**: Implementation was done before flight artifacts existed
**Decision**: Created flight.md and flight-log.md retroactively, marking implementation legs as completed
**Impact**: UAT leg will be the first leg tracked in real-time

---

## Deviations

### Combined Leg 2 and 3 Implementation
**Planned**: Separate sidebar and editor legs
**Actual**: Implemented as a single atomic change in studio.js
**Reason**: The sidebar and editor are tightly coupled (selection drives editor rendering), making separate implementation impractical

---

### uat-and-alignment
**Status**: completed
**Started**: 2026-04-23
**Completed**: 2026-04-23

#### Changes Made
- Added flash toast notification on create/save (top-center, 2-second fade)
- All 13 acceptance criteria verified interactively in browser

#### Notes
One alignment fix during UAT: save/create had no visible success feedback. Added a flash toast ("Agent created" / "Saved") — initially bottom-right, moved to top-center per user preference.

---

## Session Notes

2026-04-23: All implementation complete. Studio area replaces stub with full agent CRUD, editor, tool toggles, and connection management. Ready for interactive UAT.

2026-04-23: UAT complete. All criteria pass. Flight landed.
