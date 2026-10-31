# Squawk 0288: Saving a connector editor opened before pairing drops the paired peer

**Status**: escalated
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-29
**Completed**: —

## Report
A peer paired by DMing a pairing code is added to the connector's
allowlist server-side, behind any open connector editor. If the operator
then saves an editor that was opened before the pairing, the form's empty
Allowlist peers replaces the stored allowlist, and the paired peer's later
DMs are silently dropped. Found by the Mission 33 Flight 4 design review
(cycle 2); not yet reproduced live.

## Evidence
- `the_one/connectors/inbound.py::_pair_peer` (:129) adds the peer to
  `config.allowlist.peers` when a pairing code is consumed (:370).
- `the_one/interfaces/web/api.py::update_connector` (~:4398):
  `merged = existing.model_dump(); merged.update(data)`, so `config` is
  replaced whole.
- `static/js/areas/studio/connector-editor.js` `buildPayload` (:345-357)
  sends `allowlist_peers` from the form's textarea, as loaded when the
  editor opened.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

A test pairs a peer while an editor holding the pre-pairing config is open,
saves that editor with an unrelated change, and the paired peer is still on
the allowlist (or the save is refused as stale and says so).

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition
**Escalated**: fails *no design decisions*: the fix needs a choice between a server-side peer union and a stale-save 409 (traced live on 2026-10-30: `update_connector` shallow-merges, so a stale `config` replaces stored `allowlist.peers`; [maintenance 2026-10-30](../maintenance/2026-10-30.md), finding #4) →
[Mission 34 Flight 2: Data safety and routine observability](../missions/34-maintenance/flights/02-data-safety-and-routine-observability/flight.md), leg `connector-peers-survive-stale-save`
