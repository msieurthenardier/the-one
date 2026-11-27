// Narrow-window report (sortie 21 leg 3, DD9): what a real WebKitGTK window shows at the smallest size.
//
// Run by scripts/webkitgtk_probe.py as a --setup-script, right after the hash route is set and before the
// router commits, so the report is a GETTER measured when the probe reads it (after --root-selector has
// matched). The probe wraps this file in a synchronous (function(){ ...; return true; })() and echoes
// window.__probeReport as "report".
//
//   /usr/bin/python3 scripts/webkitgtk_probe.py --window-size 640x360 \
//     --url 'http://127.0.0.1:PORT/#chats/SESSION_ID' --data-dir SCRATCH \
//     --setup-script scripts/probe/narrow/report.js \
//     --root-selector '.app-shell-row[data-pane="detail"] .chat-instance .ui-message'
//
// Report: innerWidth, innerHeight, devicePixelRatio, route, the visible pane (id and width: the pane
// App.shellPane.visiblePane() names, else #main-content), whether the page scrolls sideways
// (scrollWidth <= clientWidth is `no_sideways_scroll`), how many transcript lines fit above the composer
// (`transcript_lines`, null when no chat is open), and the header height. Nothing is asserted here: the
// run's caller reads the numbers (the viewport can be smaller than the requested window size).
Object.defineProperty(window, '__probeReport', {
  configurable: true,
  get: function () {
    var doc = document.scrollingElement || document.documentElement;
    var pane = (window.App && App.shellPane && App.shellPane.visiblePane && App.shellPane.visiblePane()) ||
      document.getElementById('main-content');
    var msgs = document.querySelector('.chat-instance .messages');
    var message = document.querySelector('.chat-instance .ui-message');
    var lines = null;
    if (msgs && message && msgs.clientHeight > 0) {
      var cs = getComputedStyle(msgs);
      var lh = parseFloat(getComputedStyle(message).lineHeight);
      if (lh > 0) {
        lines = Math.floor((msgs.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom)) / lh);
      }
    }
    var header = document.querySelector('.chat-instance .chat-header');
    var row = document.querySelector('.app-shell-row');
    return {
      route: location.hash,
      inner_width: window.innerWidth,
      inner_height: window.innerHeight,
      device_pixel_ratio: window.devicePixelRatio,
      data_pane: row ? row.getAttribute('data-pane') : null,
      visible_pane: pane ? pane.id : null,
      visible_pane_width: pane ? Math.round(pane.getBoundingClientRect().width) : null,
      scroll_width: doc.scrollWidth,
      client_width: doc.clientWidth,
      no_sideways_scroll: doc.scrollWidth <= doc.clientWidth,
      transcript_lines: lines,
      chat_header_height: header && header.getClientRects().length
        ? Math.round(header.getBoundingClientRect().height) : null
    };
  }
});
