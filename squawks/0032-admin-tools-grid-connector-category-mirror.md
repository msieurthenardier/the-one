# Squawk 0032: Admin Tools grid's TOOL_CATEGORIES mirror lacks the connector tools

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-01
**Completed**: —

## Report

Squawk 0028 fixed the per-agent Studio Tools tab, but the Administration area's Tools grid
(`admin/tools-grid.js` / `admin/tools-editor.js`) keeps its own separate `TOOL_CATEGORIES`
mirror, which also lacks `send_to_platform_channel` and `fetch_channel_history` — they render
with an "unknown" badge there. Same class of fix: add the Connectors bucket to the admin
mirror (or better, note whether the two mirrors can share one source). Found during squawk
0028's implementation; deliberately left out of that squawk's scope (its report/evidence
named the per-agent tab only).

## Evidence

- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` / `tools-editor.js` — the mirror
- Squawk 0028's Corrective Action scope note (turnaround 2026-09-01)

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
