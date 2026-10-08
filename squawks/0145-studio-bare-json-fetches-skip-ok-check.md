# Squawk 0145: Four Studio fetches parse error bodies as data

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: —

## Report
Four reads in `areas/studio.js` do `fetch(url).then(r => r.json())` with no `r.ok` check, so a 401/404/500 JSON error body is handed to the render code as if it were the expected payload, which most likely ends in a TypeError and a blank or partial editor. Other traced Studio paths handle errors correctly. Found by routine maintenance 2026-10-08 (finding #29; the wider raw-fetch cleanup belongs to issue #207).

## Evidence
- `the_one/interfaces/web/static/js/areas/studio.js` ~1900 (`/api/tools`), ~1907 (`/api/mcp-sources?include_agent_surfaces=1`), ~1930 (`/api/agents/{name}`), ~2118 (`/api/tools/configs`)
- `App.api.fetchJson` is used nowhere in studio.js

## Corrective Action
*(written at completion)* Expected: route these four through `App.api.fetchJson` (or an explicit `r.ok` check) so a failure reaches the existing error handling.

## Verification
A browser test that makes one of these routes fail (e.g. a deleted agent's GET) and asserts a visible error rather than a blank editor, or a unit-level guard pinning that these four call sites use `fetchJson`.

## Sign-Off
*(written at completion)*
