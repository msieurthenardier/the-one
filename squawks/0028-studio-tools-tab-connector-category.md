# Squawk 0028: Studio Tools tab has no category for the connector tools

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-01
**Completed**: —

## Report

`studio.js`'s `TOOL_CATEGORIES` (~`:273-277`) buckets built-in tools into Filesystem/Execution/Web
only, and `tools-tab.js` renders no fallback for uncategorized tools — so `send_to_platform_channel`
and `fetch_channel_history` (Mission 23 Flight 2) are completely invisible in the per-agent Built-in
Tools tab. DD-4's authorization model presumes "the operator toggles it on the agent they bind"; today
the only affordance is default-all-on or raw config editing. Not a security hole (authorization is
enforced at `execute()` against live DB state regardless), but the deliberate-enablement premise has
no UI. Add a "Connectors" (or "Platform") category with the two checkboxes.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio.js:273-277` — `TOOL_CATEGORIES`
- Behavior-test run `tests/behavior/stub-connector-round-trip/runs/2026-08-31-22-43-08.md` — Executor
  precondition anomaly + Validator closing (spec's confirm-the-checkbox precondition unsatisfiable)
- Flight 2 flight-end review, deviation ruling 4 (non-blocking, Flight 3 or squawk)

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
