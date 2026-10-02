// WebKitGTK probe setup script (M25 F2 L2): opens a real App.ui.modal on the
// reference page, so the shared resolver can run over the open <dialog> in the
// real desktop engine (--root-selector 'dialog[open]'). Evaluated verbatim by
// scripts/webkitgtk_probe.py (--setup-script) and by the Playwright test
// test_probe_modal_script_opens_a_modal. Statements only; the caller appends
// the trailing true.
var probeModalPrev = document.querySelector('dialog[data-testid="probe-modal"]');
if (probeModalPrev) probeModalPrev.remove();
var probeModalOpener = document.createElement('button');
probeModalOpener.type = 'button';
probeModalOpener.textContent = 'Probe modal opener';
document.body.appendChild(probeModalOpener);
var probeModal = App.ui.modal({
  title: 'Probe modal',
  body: 'A real App.ui.modal opened by the WebKitGTK probe.',
  testid: 'probe-modal',
  actions: [
    { label: 'Stay', variant: 'secondary', value: 'stay', autofocus: true },
    { label: 'Continue', variant: 'primary', value: 'go' }
  ]
});
probeModal.open(probeModalOpener);
window.__probeReport = {
  open: probeModal.isOpen(),
  isModal: probeModal.el.matches(':modal'),
  focusInside: probeModal.el.contains(document.activeElement),
  scrim: getComputedStyle(probeModal.el, '::backdrop').backgroundColor
};
