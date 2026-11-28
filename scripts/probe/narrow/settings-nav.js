// Show the Settings nav in a small window (sortie 21 leg 3, DD9): click the current destination's rail icon.
//
// A cold load of #settings shows the Appearance page (an arrival shows the page, guide: overview), so the
// nav is reached the way an operator reaches it: the rail's Settings icon. Run after report.js:
//
//   /usr/bin/python3 scripts/webkitgtk_probe.py --window-size 640x360 \
//     --url 'http://127.0.0.1:PORT/#settings/appearance' --data-dir SCRATCH \
//     --setup-script scripts/probe/narrow/report.js --setup-script scripts/probe/narrow/settings-nav.js \
//     --root-selector '.app-shell-row[data-pane="list"] [data-testid="settings-nav"]'
//
// The probe wraps the file in a synchronous (function(){ ...; return true; })() and does not await a
// Promise, so the click is a poll that stops once the Settings page is the current route and the rail link exists.
var tries = 0;
var timer = setInterval(function () {
  tries += 1;
  var link = document.querySelector('[data-testid="rail-settings"]');
  var row = document.querySelector('.app-shell-row');
  if (link && row && location.hash.indexOf('#settings') === 0 && row.getAttribute('data-pane') === 'detail') {
    clearInterval(timer);
    link.click();
  } else if (tries > 150) {
    clearInterval(timer);
  }
}, 100);
