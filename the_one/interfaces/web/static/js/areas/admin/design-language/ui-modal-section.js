(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // App.ui.modal: a static card preview (the visible .modal-dialog, no backdrop),
  // a live "Open modal" button that opens a real App.ui.modal (appended to body on
  // click only, never inside a [data-ui-demo] root) and a live "Open confirm
  // dialog" button that calls the App.confirmDialog adapter. Escape closes either.
  // M25 F4 L1 (DD14): a live "Open chooser" button opens the chooser layout (the
  // agent picker's shape: width 640, top 72, the "Esc" close button, an
  // App.ui.searchList body with initialFocus on its input, the 11px footer).
  // Picking a row closes it with the agent's id.
  // M25 F4 L7 (DD14): a live "Open labelled chooser" button opens a chooser
  // named by `ariaLabel` (no title, no header row: the jump-to palette's
  // shape, with the palette's bar and body classes), whose body owns its
  // "Esc" close button (it calls close()). A caption under the buttons shows
  // App.ui.modal.anyOpen() (every pane's), refreshed when that chooser opens
  // and closes.
  var el = App.ui.util.el;

  var CHOOSER_AGENTS = [
    { id: 'archivist', label: 'Archivist', description: 'Files notes into the team wiki.', model: 'llama3.1:8b' },
    { id: 'reviewer', label: 'Code reviewer', description: 'Reviews diffs for correctness.', model: 'gpt-4.1-mini' },
    { id: 'planner', label: 'Planner', description: 'Turns goals into a week of tasks.', model: 'llama3.1:8b' },
    { id: 'research', label: 'Research assistant', description: 'Finds and summarises papers.', model: 'claude-sonnet-4-5' },
    { id: 'translator', label: 'Translator', description: 'Translates between eight languages.', model: 'claude-sonnet-4-5' }
  ];

  function openChooser(opener) {
    var modal = null;
    var list = App.ui.searchList({
      label: 'Find an agent',
      placeholder: 'Find an agent by name, model or provider',
      inputTestid: 'ui-demo-chooser-search',
      rowTestid: 'ui-demo-chooser-row',
      source: function (query) {
        var q = query.trim().toLowerCase();
        var items = [];
        for (var i = 0; i < CHOOSER_AGENTS.length; i++) {
          var a = CHOOSER_AGENTS[i];
          if (!q || (a.label + ' ' + a.model).toLowerCase().indexOf(q) !== -1) {
            items.push({ id: a.id, label: a.label, description: a.description, meta: a.model, metaMono: true });
          }
        }
        return [{ id: 'agents', label: q ? items.length + ' matching' : 'All agents', items: items }];
      },
      emptyText: function (query) {
        return 'No agents match "' + query.trim() + '".';
      },
      onPick: function (item) {
        modal.close(item.id);
      }
    });
    // A fragment, so the two items are the footer row's own flex children.
    var footer = document.createDocumentFragment();
    footer.appendChild(el('span', { text: 'Picking an agent starts a new chat with it' }));
    footer.appendChild(el('span', { className: 'modal-dialog-footer-end', text: 'Enter to start' }));
    // The demo's own inset for the list (the picker styles its own body).
    var body = el('div', null, [list.el]);
    body.style.display = 'flex';
    body.style.flexDirection = 'column';
    body.style.minHeight = '0';
    body.style.height = '360px';
    body.style.padding = '0 20px 12px';
    modal = App.ui.modal({
      title: 'Start a chat with…',
      layout: 'chooser',
      width: 640,
      top: 72,
      testid: 'ui-demo-chooser',
      dismissible: true,
      closeButton: { label: 'Esc', ariaLabel: 'Close (Esc)', testid: 'ui-demo-chooser-close' },
      body: body,
      footer: footer,
      initialFocus: list.input,
      onClose: function () {
        list.destroy();
      }
    });
    modal.open(opener);
  }

  // The labelled chooser: an input bar (the search list's field wrapper with
  // the body's own Esc button appended) over the list, no visible title.
  function openLabelledChooser(opener, onChange) {
    var modal = null;
    var list = App.ui.searchList({
      label: 'Find a sample',
      placeholder: 'Find a sample by name',
      source: function (query) {
        var q = query.trim().toLowerCase();
        var items = [];
        for (var i = 0; i < CHOOSER_AGENTS.length; i++) {
          var a = CHOOSER_AGENTS[i];
          if (!q || a.label.toLowerCase().indexOf(q) !== -1) {
            items.push({ id: a.id, label: a.label, meta: 'Agent' });
          }
        }
        return [{ id: 'results', items: items }];
      },
      emptyText: function (query) {
        return 'No matches for "' + query.trim() + '".';
      },
      onPick: function (item) {
        modal.close(item.id);
      }
    });
    // The palette's own input-bar and body classes (components.css), so the
    // demo shows the shape the jump-to palette uses.
    var bar = list.input.parentNode;
    bar.classList.add('jump-to-bar');
    bar.appendChild(App.ui.button({
      label: 'Esc',
      ariaLabel: 'Close (Esc)',
      variant: 'ghost',
      size: 'sm',
      onClick: function () { modal.close(); }
    }));
    var body = el('div', { className: 'jump-to-body' }, [list.el]);
    var footer = document.createDocumentFragment();
    footer.appendChild(el('span', { text: 'No title: the dialog is named by ariaLabel' }));
    modal = App.ui.modal({
      ariaLabel: 'Find a sample',
      layout: 'chooser',
      width: 600,
      top: 96,
      dismissible: true,
      body: body,
      footer: footer,
      initialFocus: list.input,
      onClose: function () {
        list.destroy();
        onChange();
      }
    });
    modal.open(opener);
    onChange();
  }

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
      var openChooserBtn = App.ui.button({ label: 'Open chooser', variant: 'secondary' });
      openChooserBtn.addEventListener('click', function () {
        openChooser(openChooserBtn);
      });
      var anyOpenLine = el('span', { className: 'design-language-caption', dataset: { anyOpenCaption: '' } });
      // anyOpen() is page-wide, so every pane's caption is refreshed.
      function showAnyOpen() {
        var text = 'App.ui.modal.anyOpen(): ' + App.ui.modal.anyOpen();
        var lines = document.querySelectorAll('[data-any-open-caption]');
        for (var k = 0; k < lines.length; k++) lines[k].textContent = text;
        anyOpenLine.textContent = text;
      }
      var openLabelledBtn = App.ui.button({ label: 'Open labelled chooser', variant: 'secondary' });
      openLabelledBtn.addEventListener('click', function () {
        openLabelledChooser(openLabelledBtn, showAnyOpen);
      });
      showAnyOpen();
      pane.appendChild(d.caption('static preview, no backdrop'));
      pane.appendChild(preview());
      pane.appendChild(d.caption('live'));
      pane.appendChild(d.row([openModal, openConfirm, openChooserBtn, openLabelledBtn]));
      pane.appendChild(anyOpenLine);
    });
  }

  window.App.admin.designLanguage.uiModalSection = { render: render };
})();
