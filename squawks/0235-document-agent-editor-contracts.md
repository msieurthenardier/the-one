# Squawk 0235: the agent editor's tab-handle contract, `state` fields and hidden-editor patch are undocumented

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-22
**Completed**: —

## Report
Mission 31 Flight 2 built the agent editor as "mount once, patch through per-tab handles", but the contract lives only in the flight log. Flight 3 will reuse the pattern for the Library editors. The undocumented pieces are:
- **The tab handles:** `destroy` is always present. `setAgent` is optional, and Rules and notes deliberately has none. MCPs adds `setSources`, Self-configuration adds `deactivate`, and General adds `applyStored`/`setStoredChangeNote`.
- **The shared `state` object's fields:** `dirty`, `snapshot`, `saveInFlight` and so on.
- **The hidden-editor patch:** a self-configuration write that resolves while the user is on Chats or Settings patches the hidden editor in place.

Recommended in the Mission 31 Flight 2 debrief.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` (the handles `h.general`, `h.mcps`, `h.selfConfig`, ...) and `agent-editor-controller.js` `onSelfConfigChanged`.
- The flight log's `### self-config-refresh` and `### rules-and-notes-tab` entries.

## Corrective Action
*(written at completion)*

## Verification
- `the_one/agents.md` "Agents list and detail" (or a new subsection) states the handle contract (required and optional members, and which tabs omit `setAgent` and why), lists the `state` fields, and describes the hidden-editor patch. A reviewer can find each from CLAUDE.md's pointer.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
