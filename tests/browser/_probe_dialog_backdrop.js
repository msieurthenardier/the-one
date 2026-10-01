// WebKitGTK probe setup script (M25 F1 L2, AC9 f): opens a harness modal dialog
// in the real desktop engine and reports the computed ::backdrop colour against
// the resolved token value and a literal control. The observation is left on
// window.__probeReport (echoed by the probe as "report"). Statements only.
var dlgPrevious = document.getElementById('ui-probe-root');
if (dlgPrevious) dlgPrevious.remove();
var dlgRoot = document.createElement('div');
dlgRoot.id = 'ui-probe-root';
var dlgStyle = document.createElement('style');
dlgStyle.textContent =
  ':root { --x-scrim: rgb(12, 34, 56); }' +
  ' #probe-dlg::backdrop { background: var(--x-scrim); }' +
  ' #probe-dlg-literal::backdrop { background-color: rgb(1, 2, 3); }';
dlgRoot.appendChild(dlgStyle);
var dlgButton = document.createElement('button');
dlgButton.type = 'button';
dlgButton.textContent = 'Dialog probe opener';
dlgRoot.appendChild(dlgButton);
var dlgToken = document.createElement('dialog');
dlgToken.id = 'probe-dlg';
dlgToken.setAttribute('aria-label', 'Token backdrop probe');
var dlgLiteral = document.createElement('dialog');
dlgLiteral.id = 'probe-dlg-literal';
dlgLiteral.setAttribute('aria-label', 'Literal backdrop probe');
dlgRoot.appendChild(dlgToken);
dlgRoot.appendChild(dlgLiteral);
document.body.appendChild(dlgRoot);
var dlgSwatch = document.createElement('div');
dlgSwatch.style.backgroundColor = 'var(--x-scrim)';
document.body.appendChild(dlgSwatch);
var dlgExpected = getComputedStyle(dlgSwatch).backgroundColor;
dlgSwatch.remove();
dlgToken.showModal();
var dlgReported = getComputedStyle(dlgToken, '::backdrop').backgroundColor;
var dlgModal = dlgToken.matches(':modal');
dlgToken.close();
dlgLiteral.showModal();
var dlgLiteralReported = getComputedStyle(dlgLiteral, '::backdrop').backgroundColor;
dlgLiteral.close();
window.__probeReport = {
  showModalOpened: dlgModal,
  expectedToken: dlgExpected,
  reportedBackdrop: dlgReported,
  literalControl: dlgLiteralReported,
  backdropMatchesToken: dlgReported === dlgExpected,
  unverifiable: dlgLiteralReported !== 'rgb(1, 2, 3)'
};
