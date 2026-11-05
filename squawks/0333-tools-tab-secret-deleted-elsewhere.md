# Squawk 0333: A secret deleted in another tab keeps its Tools-tab row

**Status**: escalated
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-05
**Completed**: —

## Report
With an agent's Tools tab open, deleting a secret in another browser tab leaves its row in the Secrets section until a refresh. The next Save drops the id, matching the server, so nothing wrong is stored, but the open tab shows a secret that no longer exists. Carried from the sortie 10 leg 3 part B review; not raised in the HAT.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/secrets-section.js` builds the rows once from the list it is given, and nothing re-renders them on a `secrets` store change.
- `the_one/interfaces/web/static/js/store.js` already notifies `secrets` subscribers. Does a delete in another tab reach this window? That's the first thing to check: only if a push or refetch arrives can this be fixed in the section alone.

## Corrective Action
*(written at completion)* Planned: subscribe the section to the `secrets` store, and drop any row whose secret has gone, keeping the switch states of the rest. If no cross-tab signal reaches the window, stop and escalate: a new push frame is a shared-interface change and exceeds a squawk.

## Disposition (blocked: exceeds squawk scope)
**Escalated** (2026-11-05, turnaround): this fails criterion 3, bounded blast radius. The fix needs a new cross-tab trigger, either a `secrets_changed` push frame (a shared interface) or a new focus or visibility refetch mechanism, plus keeping unsaved toggles across a rebuild. → a future sortie (not yet planned). The harm is low: the next Save drops the deleted id, matching the server.

Investigated; no code changed. No cross-tab signal reaches an open window for secrets:
- `store.js` has no focus, visibility or timer refetch, and no push frame covers `secrets` (the server's only list push is `sessions_changed`, for sessions; grep of `the_one/` finds no secrets equivalent).
- The Tools tab gets its list from `agent-data.js::refreshSecretsCache` (`App.store.get('secrets', {force: true})`), called only on an agent-editor mount (`agents-list.js` select and create paths). Nothing calls it while the editor stays open, so a store subscription in the section would never fire for another tab's delete.
- A fix therefore needs a new trigger: a server push frame (shared interface) or a new window-focus / visibility / polling refetch (a new mechanism; the only precedent is the Self-configuration tab's own focus listener). Either exceeds a squawk. Suggested route: a sortie that decides between a `secrets_changed` push and a focus refetch, then subscribes the section (rebuilds on id-set change already work via `setAgent`; unsaved toggles are lost on rebuild today, so that needs a state-keeping step).

## Verification
(Planned, not done.) A browser test in `tests/browser/test_flow_agent_secrets.py`: with the Tools tab open, a delete through the API followed by the store's refresh path removes the row with no reload.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
