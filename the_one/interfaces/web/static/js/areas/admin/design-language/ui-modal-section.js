(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // App.ui.modal: a static card preview (the visible .modal-dialog, no backdrop),
  // a live "Open modal" button that opens a real App.ui.modal (appended to body on
  // click only, never inside a [data-ui-demo] root) and a live "Open confirm
  // dialog" button that calls the App.confirmDialog adapter. Escape closes either.
  var el = App.ui.util.el;

  function preview() {
    return el('div', { className: 'modal-dialog design-language-modal-preview' }, [
      el('h2', { className: 'modal-dialog-title', text: 'Sample modal' }),
      el('p', {
        className: 'modal-dialog-message',
        text: 'The visible card of a modal, rendered statically for shape reference.'
      }),
      el('div', { className: 'modal-actions form-actions' }, [
        App.ui.button({ label: 'Cancel', variant: 'secondary' }),
        App.ui.button({ label: 'OK', variant: 'primary' })
      ])
    ]);
  }

  function render(host) {
    var d = App.admin.designLanguage.uiDemo;

    d.demo(host, 'modal', function (pane) {
      var openModal = App.ui.button({ label: 'Open modal', variant: 'secondary' });
      openModal.addEventListener('click', function () {
        App.ui.modal({
          title: 'Sample modal',
          body: 'A real App.ui.modal. Press OK, Cancel or Escape to close it.',
          testid: 'ui-demo-modal',
          dismissible: true,
          actions: [
            { label: 'Cancel', variant: 'secondary', value: 'cancel', autofocus: true },
            { label: 'OK', variant: 'primary', value: 'ok' }
          ]
        }).open(openModal);
      });
      var openConfirm = App.ui.button({ label: 'Open confirm dialog', variant: 'secondary' });
      openConfirm.addEventListener('click', function () {
        App.confirmDialog({
          title: 'Sample confirm dialog',
          message: 'The App.confirmDialog adapter. Press Continue, Stay or Escape.'
        });
      });
      pane.appendChild(d.caption('static preview, no backdrop'));
      pane.appendChild(preview());
      pane.appendChild(d.caption('live'));
      pane.appendChild(d.row([openModal, openConfirm]));
    });
  }

  window.App.admin.designLanguage.uiModalSection = { render: render };
})();
