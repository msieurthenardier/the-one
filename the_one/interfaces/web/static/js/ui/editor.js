(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // The editor family (M31 F1 L4, DD1/DD8): editorShell, section, dangerZone.
  // The shell boundary (DD1): the shell builds the header and nothing else.
  // It reads no store or router and fetches nothing: the breadcrumb href is
  // supplied by the caller and no click handler is attached to the link (the
  // router's interceptor handles `a[href^="#"]`). setDirty only drives the
  // caption and the buttons' enablement. The shell exposes titleEl and
  // focusTitle() and never calls App.focusAfter; the caller decides when focus
  // moves.

  function buildBreadcrumb(spec) {
    var util = App.ui.util;
    var link = util.el('a', {
      className: 'editor-breadcrumb-link',
      href: spec.href,
      'data-testid': 'editor-breadcrumb-link',
      text: spec.label
    });
    var crumb = util.el('div', { className: 'editor-breadcrumb' });
    // lead and trail are always plain text nodes; only label is the link.
    if (spec.lead) crumb.appendChild(document.createTextNode(spec.lead));
    crumb.appendChild(link);
    if (spec.trail) crumb.appendChild(document.createTextNode(spec.trail));
    return crumb;
  }

  function actionButton(spec, variant, className, label) {
    return App.ui.button({
      variant: variant,
      label: spec.label || label,
      className: className,
      testid: spec.testid,
      onClick: spec.onClick
    });
  }

  // App.ui.editorShell(opts) -> controller {el, titleEl, focusTitle(),
  // setTitle(text), setSubtitle(text|null), setDirty(bool), setBusy(bool),
  // setError(text|null), setSaveLabel(text), cancelButton, saveButton,
  // testButton}.
  //   breadcrumb: {label, href, trail} ("Library" + " / Model providers") or
  //     {lead, label, href} ("Settings / " + the link); lead/trail are text.
  //   title (required), titleLevel (1 default, or 2): hN.editor-title with
  //     tabindex -1. subtitle: p.editor-subtitle. afterTitle: a node placed
  //     between the title and the subtitle. The test id option: on the header.
  //   actions: {cancel, save (required), test, extra}.
  //     cancel {label, testid, onClick, enabledWhenClean}: btn-outlined-primary
  //       cancel-btn; disabled at first unless enabledWhenClean (create forms).
  //     save {label, testid, onClick}: btn-filled-primary save-btn; disabled in
  //       every mode until setDirty(true).
  //     test {label 'Test', testid, onClick, className}: secondary, small, with
  //       the play icon; class test-provider-btn unless className overrides.
  //     extra: nodes placed before Cancel.
  //   div.form-actions holds span.editor-unsaved[role=status] first and
  //   span.editor-error last.
  //   setDirty(true): caption "Unsaved changes", Save and Cancel enabled;
  //   setDirty(false): caption cleared, Save disabled, Cancel enabled only
  //   when enabledWhenClean. setBusy(true) disables Save, Cancel and Test and
  //   setBusy(false) restores the dirty-derived state.
  App.ui.editorShell = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    if (!opts.title) throw new Error('App.ui.editorShell: title is required');
    var actions = opts.actions || {};
    if (!actions.save) throw new Error('App.ui.editorShell: actions.save is required');
    var level = opts.titleLevel === 2 ? 2 : 1;

    var titleEl = util.el('h' + level, {
      className: 'editor-title',
      tabindex: '-1',
      text: opts.title
    });
    var textCol = util.el('div', { className: 'editor-header-text' });
    if (opts.breadcrumb) textCol.appendChild(buildBreadcrumb(opts.breadcrumb));
    textCol.appendChild(titleEl);
    if (opts.afterTitle) textCol.appendChild(opts.afterTitle);
    var subtitleEl = null;

    function setSubtitle(text) {
      if (text === null || text === undefined || text === '') {
        if (subtitleEl && subtitleEl.parentNode) subtitleEl.parentNode.removeChild(subtitleEl);
        subtitleEl = null;
      } else if (subtitleEl) {
        subtitleEl.textContent = text;
      } else {
        subtitleEl = util.el('p', { className: 'editor-subtitle', text: text });
        textCol.appendChild(subtitleEl);
      }
    }
    setSubtitle(opts.subtitle);

    var unsaved = util.el('span', {
      className: 'editor-unsaved',
      role: 'status',
      'data-testid': 'editor-unsaved'
    });
    var errorEl = util.el('span', { className: 'editor-error' });
    var cluster = util.el('div', { className: 'form-actions' }, [unsaved]);
    var i;
    if (actions.extra) {
      for (i = 0; i < actions.extra.length; i++) cluster.appendChild(actions.extra[i]);
    }
    var cancelButton = null;
    if (actions.cancel) {
      cancelButton = actionButton(actions.cancel, 'secondary', 'cancel-btn', 'Cancel');
      cluster.appendChild(cancelButton);
    }
    var saveButton = actionButton(actions.save, 'primary', 'save-btn', 'Save');
    cluster.appendChild(saveButton);
    var testButton = null;
    if (actions.test) {
      testButton = App.ui.button({
        variant: 'secondary',
        size: 'sm',
        icon: 'play',
        label: actions.test.label || 'Test',
        className: actions.test.className || 'test-provider-btn',
        testid: actions.test.testid,
        onClick: actions.test.onClick
      });
      cluster.appendChild(testButton);
    }
    cluster.appendChild(errorEl);

    var header = util.el('div', { className: 'editor-header' }, [textCol, cluster]);
    if (opts.testid) header.setAttribute('data-testid', opts.testid);

    var dirty = false;
    var busy = false;
    var cleanCancel = !!(actions.cancel && actions.cancel.enabledWhenClean);

    function apply() {
      unsaved.textContent = dirty ? 'Unsaved changes' : '';
      saveButton.disabled = busy || !dirty;
      if (cancelButton) cancelButton.disabled = busy || !(dirty || cleanCancel);
      if (testButton) testButton.disabled = busy;
    }
    apply();

    return {
      el: header,
      titleEl: titleEl,
      cancelButton: cancelButton,
      saveButton: saveButton,
      testButton: testButton,
      focusTitle: function () {
        titleEl.focus();
      },
      // textContent only, so a title change keeps focus on the heading.
      setTitle: function (text) {
        titleEl.textContent = text;
      },
      setSubtitle: setSubtitle,
      setSaveLabel: function (text) {
        saveButton.textContent = text;
      },
      setDirty: function (value) {
        dirty = !!value;
        apply();
      },
      setBusy: function (value) {
        busy = !!value;
        apply();
      },
      setError: function (text) {
        errorEl.textContent = text || '';
      }
    };
  };

  // App.ui.section(opts) -> {el, body, setTitle(text)}.
  //   title, titleTag ('div' default, 'h2' or 'h3'), description, testid,
  //   className (appended to editor-section), children (nodes).
  //   div.editor-section holds the .section-title, an optional
  //   p.section-description, then the children; body is the element children
  //   append to (the section itself).
  App.ui.section = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var tag = opts.titleTag || 'div';
    if (tag !== 'div' && tag !== 'h2' && tag !== 'h3') {
      throw new Error('App.ui.section: unknown titleTag "' + tag + '"');
    }
    var root = util.el('div', {
      className: 'editor-section' + (opts.className ? ' ' + opts.className : '')
    });
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    var titleEl = null;
    if (opts.title) {
      titleEl = util.el(tag, { className: 'section-title', text: opts.title });
      root.appendChild(titleEl);
    }
    if (opts.description) {
      root.appendChild(util.el('p', { className: 'section-description', text: opts.description }));
    }
    var children = opts.children || [];
    for (var i = 0; i < children.length; i++) {
      if (children[i]) root.appendChild(children[i]);
    }
    return {
      el: root,
      body: root,
      setTitle: function (text) {
        if (titleEl) titleEl.textContent = text;
      }
    };
  };

  // App.ui.dangerZone(opts) -> {el, button, setNotice(text|null),
  // setDisabled(bool)}.
  //   title ('Danger Zone'), action {label, testid, confirmLabel ('Confirm
  //   delete?'), revertMs, dataset, onConfirm(revert), beforeArm(proceed)},
  //   notice {testid}. beforeArm, when given, runs on the first click and
  //   decides whether to call proceed() (arm the button); it is skipped on the
  //   second click, which commits.
  //   div.editor-section.danger-zone holds div.section-title.danger-zone-title,
  //   then button.btn-muted-destructive.delete-btn (a 16px trash icon, then
  //   span[data-confirm-title] with the label, so the confirm title swap leaves
  //   the icon alone). With notice, a hidden banner follows the button as its
  //   sibling. A click runs App.ui.confirm on the button.
  App.ui.dangerZone = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var action = opts.action;
    if (!action || !action.label) throw new Error('App.ui.dangerZone: action.label is required');
    var root = util.el('div', { className: 'editor-section danger-zone' }, [
      util.el('div', { className: 'section-title danger-zone-title', text: opts.title || 'Danger Zone' })
    ]);
    var button = util.el('button', {
      type: 'button',
      className: 'btn-muted-destructive delete-btn',
      'data-testid': action.testid
    }, [
      App.ui.icon('trash'),
      util.el('span', { 'data-confirm-title': '', text: action.label })
    ]);
    util.applyDataset(button, action.dataset);
    function arm() {
      App.ui.confirm(button, function (el, revert) {
        if (typeof action.onConfirm === 'function') action.onConfirm(revert);
      }, { confirmLabel: action.confirmLabel || 'Confirm delete?', revertMs: action.revertMs });
    }
    button.addEventListener('click', function () {
      // beforeArm(proceed) gates the FIRST click (the provider editor checks for
      // agents that use the provider); the second click, on the armed button,
      // commits without asking again.
      if (typeof action.beforeArm === 'function' && !button.classList.contains('confirm-delete')) {
        action.beforeArm(arm);
      } else {
        arm();
      }
    });
    root.appendChild(button);
    var notice = null;
    if (opts.notice) {
      notice = util.el('div', {
        className: 'action-blocked-message banner banner-error',
        'data-testid': opts.notice.testid,
        role: 'alert'
      });
      root.appendChild(notice);
    }
    return {
      el: root,
      button: button,
      setNotice: function (text) {
        if (!notice) return;
        if (text === null || text === undefined || text === '') {
          notice.textContent = '';
        } else {
          notice.textContent = text;
        }
      },
      setDisabled: function (value) {
        button.disabled = !!value;
      }
    };
  };
})();
