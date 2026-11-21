// GleepGlorp drawer, WebKitGTK run 3 of 3 (M36 F3 L9): a message sent from the drawer makes the seeded
// mock GleepGlorp call fill_form, and the fill lands in the agent editor as unsaved edits.
//
// Prerequisite: scripts/gleepglorp_drawer_seed.py has pointed GleepGlorp at the scripted mock provider.
// The probe wraps this file in a synchronous (function(){ ...; return true; })() and does not await a
// Promise, so the work is a timer chain (open, type, send) plus an observer; both write
// window.__probeReport, which the probe prints after the root-selector poll.
//
//   /usr/bin/python3 scripts/webkitgtk_probe.py --url 'http://127.0.0.1:PORT/#settings/appearance' \
//     --data-dir SCRATCH --setup-script scripts/probe/gg-drawer/fill.js --timeout 120 \
//     --root-selector '[data-testid="agent-filled-note"]'
//
// The root selector waits (up to --timeout) for the editor's "filled" note. The resolver's a11y "ok" over
// that note is read separately from the fill verdict: judge the fill by report.note_present,
// report.name_value, report.unsaved_text and report.route, then run
//   python3 scripts/gleepglorp_drawer_seed.py --base-url ... --data-dir SCRATCH --check-fill
// (exit 0 = the fill row is `filled` and no agent was created).
var MESSAGE = 'Fill in a new agent for me';
var report = {
  opened: false,
  sent: false,
  note_present: false,
  name_value: null,
  unsaved_text: null,
  route: null,
  window_inner_width: window.innerWidth
};
window.__probeReport = report;

function observe() {
  var note = document.querySelector('[data-testid="agent-filled-note"]');
  var name = document.getElementById('studio-name');
  var unsaved = document.querySelector('[data-testid="editor-unsaved"]');
  report.route = location.hash;
  report.note_present = !!note;
  report.name_value = name ? name.value : null;
  report.unsaved_text = unsaved ? unsaved.textContent.trim() : null;
}
setInterval(observe, 200);

var tries = 0;
var opener = setInterval(function () {
  tries += 1;
  var button = document.querySelector('[data-testid="gg-corner-button"]');
  var drawer = document.getElementById('gleepglorp-drawer');
  if (button && !button.hidden && button.offsetParent !== null && drawer) {
    clearInterval(opener);
    button.click();
    report.opened = !drawer.hidden;
    sendWhenReady();
  } else if (tries > 150) {
    clearInterval(opener);
    report.error = 'the corner button never showed';
  }
}, 100);

function sendWhenReady() {
  var waits = 0;
  var t = setInterval(function () {
    waits += 1;
    var input = document.querySelector('[data-testid="gg-chat-input"]');
    var send = document.querySelector('[data-testid="gg-chat-send-btn"]');
    if (input && send && !input.disabled) {
      clearInterval(t);
      // The native setter plus an input event, so the composer's own listener sees the text.
      var setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
      setter.call(input, MESSAGE);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      setTimeout(function () {
        send.click();
        report.sent = true;
      }, 150);
    } else if (waits > 150) {
      clearInterval(t);
      report.error = 'the drawer composer never enabled (GleepGlorp not ready?)';
    }
  }, 100);
}
