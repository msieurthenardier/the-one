// GleepGlorp drawer, WebKitGTK run 2 of 3 (M36 F3 L9): Esc closes the drawer and focus returns to the button.
//
// This script is SYNCHRONOUS on purpose: the probe sends its GTK key right after the setup scripts
// return and does not wait for a timer, so the drawer must already be open, with focus inside it, when
// this file ends. It clicks the real corner button, then moves focus to the drawer's own Close button
// (opening focuses the composer; the Close button is the plainest focusable element inside the drawer,
// so the drawer's own Escape handler receives the key). If the button is not there yet (the GleepGlorp
// state loads after the page's load event) the report says so and the run fails at its assert; the
// Flight Director then re-runs it or adds a wait to the probe (a Part B decision).
//
//   /usr/bin/python3 scripts/webkitgtk_probe.py --url 'http://127.0.0.1:PORT/#settings/appearance' \
//     --data-dir SCRATCH --setup-script scripts/probe/gg-drawer/esc.js \
//     --press-keys Escape --assert-timeout 15 \
//     --assert-selector '[data-testid="gg-corner-button"]:focus' \
//     --root-selector '[data-testid="gg-corner-button"]'
//
// "Escape" is case-sensitive (Gdk.keyval_from_name).
var report = { button_found: false, opened: false, focus_in_drawer: false, route: location.hash };
window.__probeReport = report;
var button = document.querySelector('[data-testid="gg-corner-button"]');
var drawer = document.getElementById('gleepglorp-drawer');
if (button && !button.hidden && drawer) {
  report.button_found = true;
  button.click();
  var close = document.querySelector('[data-testid="gg-drawer-close"]');
  if (close) close.focus();
  report.opened = !drawer.hidden;
  report.focus_in_drawer = !!(document.activeElement && drawer.contains(document.activeElement));
  report.focused_testid = document.activeElement
    ? document.activeElement.getAttribute('data-testid')
    : null;
} else {
  report.error = 'the corner button was not shown when the script ran';
}
