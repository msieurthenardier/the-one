// GleepGlorp drawer, WebKitGTK run 1 of 3 (M36 F3 L9): the corner button opens the drawer.
//
// Run by scripts/webkitgtk_probe.py as a --setup-script on '#settings/appearance' (off Chats, where the
// button shows). The probe wraps the file in a synchronous (function(){ ...; return true; })() and does
// not await a Promise, so the async work is a poll that writes window.__probeReport.
//
//   /usr/bin/python3 scripts/webkitgtk_probe.py --url 'http://127.0.0.1:PORT/#settings/appearance' \
//     --data-dir SCRATCH --setup-script scripts/probe/gg-drawer/open.js \
//     --assert-selector '#gleepglorp-drawer:not([hidden])' --assert-timeout 15 \
//     --root-selector '#gleepglorp-drawer'
//
// Report: {button_found, opened, drawer_width, window_inner_width, route}. The width is recorded, not
// asserted (the drawer pushes <main> at 1280px and wider and overlays below).
var report = { button_found: false, opened: false, drawer_width: null, window_inner_width: null, route: null };
window.__probeReport = report;
var tries = 0;
var timer = setInterval(function () {
  tries += 1;
  var button = document.querySelector('[data-testid="gg-corner-button"]');
  var drawer = document.getElementById('gleepglorp-drawer');
  report.route = location.hash;
  if (button && !button.hidden && button.offsetParent !== null && drawer) {
    clearInterval(timer);
    report.button_found = true;
    button.click();
    setTimeout(function () {
      report.opened = !drawer.hidden;
      report.drawer_width = Math.round(drawer.getBoundingClientRect().width);
      report.window_inner_width = window.innerWidth;
    }, 400);
  } else if (tries > 150) {
    clearInterval(timer);
    report.error = 'the corner button never showed';
  }
}, 100);
