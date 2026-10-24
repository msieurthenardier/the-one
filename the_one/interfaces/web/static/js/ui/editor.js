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

  // variant: 'default' | 'page' (M31 F4 L04a). The page variant builds the
  //   header with App.ui.pageHeader (div.page-header.ui-page-header; the
  //   h1.page-title also carries editor-title and tabindex -1) and puts the
  //   actions cluster in its actions slot; subtitle becomes the header intro.
  //   It takes no breadcrumb and titleLevel 2 (both throw). inset: 'none' drops
  //   the header's horizontal padding (editor-header--flush).
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
    var variant = opts.variant === undefined ? 'default' : opts.variant;
    if (variant !== 'default' && variant !== 'page') {
      throw new Error('App.ui.editorShell: unknown variant "' + variant + '"');
    }
    if (opts.inset !== undefined && opts.inset !== 'none') {
      throw new Error('App.ui.editorShell: unknown inset "' + opts.inset + '"');
    }
    var isPage = variant === 'page';
    if (isPage && opts.breadcrumb) {
      throw new Error('App.ui.editorShell: a page variant takes no breadcrumb');
    }
    if (isPage && opts.titleLevel === 2) {
      throw new Error('App.ui.editorShell: a page variant title is always an h1');
    }

    // The default variant builds its header text column now; the page variant
    // composes pageHeader below, once the actions cluster exists.
    var titleEl = null;
    var textCol = null;
    var pageHdr = null;
    var subtitleEl = null;
    if (!isPage) {
      titleEl = util.el('h' + level, {
        className: 'editor-title',
        tabindex: '-1',
        text: opts.title
      });
      textCol = util.el('div', { className: 'editor-header-text' });
      if (opts.breadcrumb) textCol.appendChild(buildBreadcrumb(opts.breadcrumb));
      textCol.appendChild(titleEl);
      if (opts.afterTitle) textCol.appendChild(opts.afterTitle);
    }

    function setSubtitle(text) {
      if (isPage) {
        pageHdr.setIntro(text);
        return;
      }
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
    if (!isPage) setSubtitle(opts.subtitle);

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

    var header;
    if (isPage) {
      // The h1 also carries editor-title (App.focusAfter and the editor
      // selectors target it); tabindex -1 comes from pageHeader.
      pageHdr = App.ui.pageHeader({
        title: opts.title,
        intro: opts.subtitle,
        testid: opts.testid,
        titleClassName: 'editor-title',
        actions: cluster
      });
      titleEl = pageHdr.titleEl;
      if (opts.afterTitle) pageHdr.titleEl.parentNode.insertBefore(
        opts.afterTitle, pageHdr.titleEl.nextSibling);
      header = pageHdr.el;
    } else {
      header = util.el('div', { className: 'editor-header' }, [textCol, cluster]);
      if (opts.testid) header.setAttribute('data-testid', opts.testid);
    }
    if (opts.inset === 'none') header.classList.add('editor-header--flush');

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
  //   className (appended to editor-section), children (nodes), layout ('stack'
  //   opts in to a flex column with a --space-3 gap between the title, the
  //   description and the children, so a consumer needs no sibling-margin rule;
  //   the default layout is unchanged, M31 F4 L03b), inset ('none' removes the
  //   section's horizontal padding through editor-section--flush, L04a).
  //   info ({text, label}, M31 F4 L04b): the title is followed by an
  //   App.ui.infoButton (description text, label) and then the eyebrow rule, all in
  //   a div.ui-section-title-row; the title keeps its tag and class, its own rule
  //   is suppressed inside the row, and the row draws the rule after the button.
  //   Without a title, info throws.
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
    if (opts.layout !== undefined && opts.layout !== 'stack') {
      throw new Error('App.ui.section: unknown layout "' + opts.layout + '"');
    }
    if (opts.inset !== undefined && opts.inset !== 'none') {
      throw new Error('App.ui.section: unknown inset "' + opts.inset + '"');
    }
    var root = util.el('div', {
      className: 'editor-section' + (opts.layout === 'stack' ? ' editor-section--stack' : '') +
        (opts.inset === 'none' ? ' editor-section--flush' : '') +
        (opts.className ? ' ' + opts.className : '')
    });
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    if (opts.info && !opts.title) throw new Error('App.ui.section: info needs a title');
    var titleEl = null;
    if (opts.title) {
      titleEl = util.el(tag, { className: 'section-title', text: opts.title });
      if (opts.info) {
        var infoBtn = App.ui.infoButton({
          description: opts.info.text,
          label: opts.info.label || opts.title,
          testid: opts.info.testid
        });
        root.appendChild(util.el('div', { className: 'ui-section-title-row' }, [titleEl, infoBtn.el]));
      } else {
        root.appendChild(titleEl);
      }
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
  //   confirm title swap leaves the icon alone). With notice, an App.ui.banner
  //   (tone error, live 'alert': role=alert, rendered while empty) follows the
  //   last button as its sibling. A click runs App.ui.confirm on
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
    var noticeBanner = null;
    if (opts.notice) {
      noticeBanner = App.ui.banner({
        tone: 'error', live: 'alert', className: 'action-blocked-message',
        testid: opts.notice.testid
      });
      notice = noticeBanner.el;
      root.appendChild(notice);
    }
    return {
      el: root,
      button: buttons[0],
      buttons: buttons,
      setNotice: function (text) {
        if (!notice) return;
        noticeBanner.set(text === null || text === undefined ? '' : text);
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
