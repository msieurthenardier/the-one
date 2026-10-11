# Squawk 0176: The rules-and-notes tab's `App.time` listener accumulates per mount

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
Each mount of the notes section subscribes to `App.time.onChange`, and the listener only unsubscribes itself when it next fires with its list disconnected. Zone changes are rare, so a long-lived desktop session accumulates one closure (and its detached DOM) per tab open.

## Evidence
`static/js/areas/studio/rules-notes-tab.js` (notes `renderList` subscription, the `isConnected` self-unsubscribe). The fix: an owner-scoped `App.time.onChange(fn, ownerEl)` that prunes disconnected owners on every subscribe, or a teardown hook for Studio tabs. Found by the M28 F2 debrief Architect.

Logged from the Mission 28 flight debriefs.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
