# Squawk 0333: A secret deleted in another tab keeps its Tools-tab row

**Status**: open
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

## Verification
A browser test in `tests/browser/test_flow_agent_secrets.py`: with the Tools tab open, a delete through the API followed by the store's refresh path removes the row with no reload.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
