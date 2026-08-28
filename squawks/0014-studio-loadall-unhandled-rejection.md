# Squawk 0014: Studio `loadAll()` chains have no `.catch` — one failed fetch leaves the area silently blank

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: —

## Report

Studio's `init()` and `_refresh` both call `loadAll().then(...)` with no rejection
handler. `loadAll` is a `Promise.all` over six fetches (agents, tools, MCP sources,
knowledge bases, providers, connectors), none of which catch internally. Any single
non-2xx, network blip, or non-JSON error body becomes an unhandled promise rejection:
the Studio area never mounts (or stops refreshing), nothing is shown to the operator,
and only the console knows. The newer self-configuration tab already does this
correctly — its status fetch has a `.catch` that writes a visible "Unable to load …"
line. Found by the 2026-08-27 maintenance inspection (E6).

Fix: add a `.catch` to both `loadAll()` call sites that renders a visible error state
in the Studio area, following the self-configuration tab's pattern.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio.js:2919` (`init`) —
  `loadAll().then(function () { … });` — no `.catch`
- `the_one/interfaces/web/static/js/areas/studio.js:2878` (`self._refresh`) — same
- `the_one/interfaces/web/static/js/areas/studio.js:1377` — `loadAll` =
  `Promise.all([fetchAgents(), fetchTools(), fetchMcpSources(), fetchKnowledgeBases(),
  fetchProviders(), fetchConnectorsList()])`
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js:1386-1390`
  — the in-repo pattern to copy (`.catch(function () { statusLine.textContent =
  'Unable to load …'; … })`)

## Corrective Action
*(written at completion)*

## Verification
*(written at completion — a browser test that stubs one of the six endpoints to 500
and asserts a visible error message rather than a blank area)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
