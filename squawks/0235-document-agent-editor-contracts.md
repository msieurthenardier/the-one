# Squawk 0235: the agent editor's tab-handle contract, `state` fields and hidden-editor patch are undocumented

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-22
**Completed**: 2026-10-23

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
New `the_one/agents.md` subsection "Editor contracts (M31 F3 L01)" (before "Agents list and detail") states the tab-handle contract (required `destroy`, the General and Rules-and-notes exemptions with reasons, the finding that `agent-editor.js`'s `h.destroy` calls only `selfConfig.destroy()` and `tabs.destroy()`, and which tabs it should also cover, and the optional members with their callers), the real `App.ui.util.mountSlot()` API and late-binding rule, each of the 21 studio `state` fields with its owner, and the hidden-editor patch (cross-referencing squawk 0232). `tests/test_studio_editor_contracts_static.py` pins the `state` key set by a static, brace-balanced parse of `studio.js` (and fails on any `state.x =` write to an undeclared key) and checks that every tab returns a `destroy` except the allow-listed exemptions. Landed in Mission 31 Flight 3 Leg 01.

## Verification
- Done: the three static tests pass; adding a `state` key fails the key-set pin and removing the knowledge tab's `destroy` fails the destroy check (tried once, reverted).
- `the_one/agents.md` "Agents list and detail" (or a new subsection) states the handle contract (required and optional members, and which tabs omit `setAgent` and why), lists the `state` fields, and describes the hidden-editor patch. A reviewer can find each from CLAUDE.md's pointer.

## Sign-Off
**Reviewer**: Sonnet, the Mission 31 Flight 3 flight review (code and accessibility reviewers, then a scoped re-review of the fix pass)
**Verdict**: confirmed
**Commit**: `flight/3: Knowledge and connectors on the library (Mission 31)` on branch `flight/03-knowledge-and-connectors-on-the-library`
