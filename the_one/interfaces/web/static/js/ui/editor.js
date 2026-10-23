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
  //     save {label, testid, onClick, enabledWhenClean}: btn-filled-primary save-btn;
  //       disabled until setDirty(true), unless enabledWhenClean (Save is then
  //       enabled on a clean form; the caption still follows dirty alone).
  //   errorRole: 'alert' (the only value) puts role=alert on span.editor-error.
  //     test {label 'Test', testid, onClick, className}: secondary, default size
  //       (same as Cancel and Save), with the play icon; no shrinking class.
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
    if (opts.errorRole !== undefined && opts.errorRole !== 'alert') {
      throw new Error('App.ui.editorShell: unknown errorRole "' + opts.errorRole + '"');
    }
    var errorEl = util.el('span', { className: 'editor-error' });
    if (opts.errorRole) errorEl.setAttribute('role', 'alert');
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
        icon: 'play',
        label: actions.test.label || 'Test',
        className: actions.test.className,
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
    var cleanSave = !!actions.save.enabledWhenClean;
    var cleanCancel = !!(actions.cancel && actions.cancel.enabledWhenClean);

    function apply() {
      unsaved.textContent = dirty ? 'Unsaved changes' : '';
      saveButton.disabled = busy || !(dirty || cleanSave);
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
  //   title, titleTag ('div' default, 'h2' or 'h3'), description, descriptionTestid
  //   (on the p.section-description), testid,
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
      var descEl = util.el('p', { className: 'section-description', text: opts.description });
      if (opts.descriptionTestid) descEl.setAttribute('data-testid', opts.descriptionTestid);
      root.appendChild(descEl);
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

  // App.ui.dangerZone(opts) -> {el, button, buttons, setNotice(text|null),
  // setDisabled(bool, index?)}.
  //   title ('Danger Zone'), action {label, testid, confirmLabel ('Confirm
  //   delete?'), revertMs, dataset, onConfirm(revert), beforeArm(proceed),
  //   icon ('trash')}, or actions [action, ...] (M31 F2 L4: one delete-style
  //   button per action, in order; action is the one-item form), notice
  //   {testid}. Each action has its own beforeArm, which runs on that button's
  //   first click and decides whether to call proceed() (arm the button); it is
  //   skipped on the second click, which commits.
  //   div.editor-section.danger-zone holds div.section-title.danger-zone-title,
  //   then one button.btn-muted-destructive.delete-btn per action (a 16px icon,
  //   trash by default, then span[data-confirm-title] with the label, so the
  //   confirm title swap leaves the icon alone). With notice, a hidden banner
  //   follows the last button as its sibling. A click runs App.ui.confirm on
  //   the button. button is the first button; setDisabled(value) applies to
  //   every button, setDisabled(value, index) to the one at index.
  App.ui.dangerZone = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var actions = opts.actions || (opts.action ? [opts.action] : []);
    if (!actions.length) throw new Error('App.ui.dangerZone: action.label is required');
    var root = util.el('div', { className: 'editor-section danger-zone' }, [
      util.el('div', { className: 'section-title danger-zone-title', text: opts.title || 'Danger Zone' })
    ]);
    var buttons = [];
    function build(action) {
      if (!action || !action.label) throw new Error('App.ui.dangerZone: action.label is required');
      var button = util.el('button', {
        type: 'button',
        className: 'btn-muted-destructive delete-btn',
        'data-testid': action.testid
      }, [
        App.ui.icon(action.icon || 'trash'),
        util.el('span', { 'data-confirm-title': '', text: action.label })
      ]);
      util.applyDataset(button, action.dataset);
      function arm() {
        App.ui.confirm(button, function (el, revert) {
          if (typeof action.onConfirm === 'function') action.onConfirm(revert);
        }, { confirmLabel: action.confirmLabel || 'Confirm delete?', revertMs: action.revertMs });
      }
      button.addEventListener('click', function () {
        // beforeArm(proceed) gates the FIRST click (the provider editor checks
        // for agents that use the provider); the second click, on the armed
        // button, commits without asking again.
        if (typeof action.beforeArm === 'function' && !button.classList.contains('confirm-delete')) {
          action.beforeArm(arm);
        } else {
          arm();
        }
      });
      return button;
    }
    for (var i = 0; i < actions.length; i++) {
      var b = build(actions[i]);
      buttons.push(b);
      root.appendChild(b);
    }
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
      button: buttons[0],
      buttons: buttons,
      setNotice: function (text) {
        if (!notice) return;
        if (text === null || text === undefined || text === '') {
          notice.textContent = '';
        } else {
          notice.textContent = text;
        }
      },
      setDisabled: function (value, index) {
        if (index === undefined || index === null) {
          for (var k = 0; k < buttons.length; k++) buttons[k].disabled = !!value;
        } else if (buttons[index]) {
          buttons[index].disabled = !!value;
        }
      }
    };
  };
})();
