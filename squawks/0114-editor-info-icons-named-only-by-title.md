# Squawk 0114: Editor info-icon buttons are named only by `title`

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-02
**Completed**: —

## Report

The editors' field info icons are `<button type="button" class="field-info-icon"
title="{description}" aria-describedby="{id}">{svg}</button>`. The button's only content
is the SVG icon, and nothing but the `title` attribute names it. The shared runtime
resolver (`tests/browser/_a11y_resolve.js`) does not accept `title` as a name, so it
reports every icon as "control has no accessible name":

- 3 in the provider editor (Context Window, Extended thinking, Reasoning Effort);
- up to 7 in the tool editor (one per schema field with a description, plus the Test
  connection section's hint).

Mission 25 Flight 3 leg 5b found them with the WebKitGTK probe. Settings items now open
below their list, and the leg's probe at `#settings/providers/{id}` and
`#settings/tools/{name}` reached the mounted editors for the first time. Earlier probes
scanned only the page roots. Leg 5b did not change the icons (editor internals are
next-mission work, mission decision 7).

Browsers fall back to `title` for the accessible name, so assistive tech usually hears
the description. But a `title`-only name is the weakest source: it is not exposed
consistently, and touch and keyboard users get no visible tooltip. The inventory already
records "Tooltip carried by `title` plus `aria-describedby`; no keyboard-visible popover".

## Evidence

- Probe output (WebKitGTK 2.52.6, dev instance on 8485, scratch data dir):
  `<button> <button type="button" class="field-info-icon" title="A larger window allows long :: control has no accessible name`
  (and the same for the other icons), with the root selector
  `#main-content .content-panel.area-admin:has(.settings-item [data-testid="save-provider-btn"])`
  and `…[data-testid="save-tool-btn"])`.
- Sources: `the_one/interfaces/web/static/js/areas/admin/provider-editor.js`
  (`renderConnectionFields`), `areas/admin/tools-form-helpers.js` (`renderField`),
  `areas/admin/tools-editor.js` (the test section's hint), and the same pattern in
  `areas/studio/mcp-server-editor.js`.
- `docs/ui-control-inventory.md`, the "Info-icon button (`.field-info-icon`)" row.
- Recorded in the leg 5b entry of
  `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`.

## Corrective Action

*(written at completion)*

## Verification

## Sign-Off

*(written at completion)*
