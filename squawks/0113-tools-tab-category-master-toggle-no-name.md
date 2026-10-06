# Squawk 0113: Built-in Tools tab category master toggles have no accessible name

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-01
**Completed**: —

## Report

In the agent editor's Built-in Tools tab, each category tile (Filesystem, Execution,
Web, Connectors) has a master on/off switch: a checkbox
`<input type="checkbox" class="tool-toggle" data-category-master="{category}">` inside a
`<label class="tools-category-tile-toggle">` whose only other child is the decorative
`.tool-switch` span. The label has no text, the input has no `aria-label` or
`aria-labelledby`, so the four switches have no accessible name.

The shared runtime resolver (`tests/browser/_a11y_resolve.js`) flags all four. Mission 25
Flight 3 leg 3 found them with the WebKitGTK probe when it scoped the scan to the
mounted agent editor (`--root-selector '#main-content .studio-editor:not(.is-hidden)'`
at `#agents/{name}/general`). Earlier probes ran before the editor mounted, or scanned
other surfaces, so they never reached the tab. Leg 3 did not change the tab.

Assistive tech that reaches a master switch hears an unnamed checkbox. The category's
name is the visible tile heading next to it, so sighted operators are unaffected.

## Evidence

- Probe output (WebKitGTK 2.52.6, dev instance on 8485): four failures,
  `<input type="checkbox" class="tool-toggle" data-category-master="Filesystem|Execution|Web|Connectors"> :: control has no accessible name`.
- Source: `the_one/interfaces/web/static/js/areas/studio/tools-tab.js` (the `masterWrap`
  / `masterCb` construction in the category tile).
- Recorded in the leg 3 entry of
  `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`.

## Corrective Action

*(written at completion)*
