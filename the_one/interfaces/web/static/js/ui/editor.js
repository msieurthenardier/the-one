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
  // setError(text|null), setSaveLabel(text), errorEl (the span.editor-error, for a
  // testid; M31 F4 L10), cancelButton, saveButton, testButton}. subtitleTestid puts a
  // testid on the subtitle (or page intro) paragraph.
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
  //     secondary (sortie 21 HAT feature): [{label, icon, testid, className,
  //       onClick({opener})}]. At 768px and wider each is an App.ui.button right after
  //       the extra nodes, before Cancel (the controller's secondaryButtons). Below 768px
  //       (App.ui.util.narrow) one App.ui.menu trigger (icon "more", aria-label "More
  //       actions", testid editor-more-btn, align end) takes that place; its items are the
  //       secondary actions (testid `<testid>-menu-item`), a hidden or disabled wide
  //       button hides or disables its item. onClick gets the visible control as opener
  //       (the button, or the menu trigger). The mode switches on the media change and
  //       keeps focus; destroy() releases the media subscription (also released on the
  //       first change after the header leaves the document). Test stays a button.
  //   div.form-actions holds span.editor-unsaved[role=status] first. The error
  //   (span.editor-error.ui-editor-error-row) is the header's last child, a
  //   full-width row under the title and the cluster (M31 F5 L05, A1); it
  //   carries data-empty while it has no text, so it takes no height. The
  //   header carries ui-editor-shell-header.
  //   setTestState({disabled, label}): holds Test disabled across setDirty and
  //   setBusy (DD4) and relabels its text node (null restores); no-op without
  //   actions.test.
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
        if (opts.subtitleTestid) subtitleEl.setAttribute('data-testid', opts.subtitleTestid);
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
    // The error is the header's last child, a full-width row of its own (M31 F5 L05,
    // A1): inside the cluster a long message squeezed the title column to nothing.
    // data-empty (never hidden or display none, so a role=alert region stays in the
    // tree) lets an empty row take no height and no gap.
    var errorEl = util.el('span', {
      className: 'editor-error ui-editor-error-row',
      'data-empty': ''
    });
    if (opts.errorRole) errorEl.setAttribute('role', 'alert');
    var cluster = util.el('div', { className: 'form-actions' }, [unsaved]);
    var i;
    if (actions.extra) {
      for (i = 0; i < actions.extra.length; i++) cluster.appendChild(actions.extra[i]);
    }
    // secondary (sortie 21 HAT feature): the header's secondary actions. At 768px and wider
    // each is a button in the place `extra` nodes take (before Cancel); below 768px
    // (App.ui.util.narrow) one "More actions" menu replaces them, in the same place.
    var secondary = actions.secondary || [];
    var secondaryButtons = [];
    var secondaryMenu = null;     // the App.ui.menu while narrow
    var secondaryMenuSpecs = [];  // spec index of each menu item
    var narrowMode = false;
    var unsubscribeNarrow = null;
    var observer = null;
    var wasConnected = false;
    var destroyed = false;
    secondary.forEach(function (spec) {
      var btn = App.ui.button({
        variant: 'secondary',
        icon: spec.icon,
        label: spec.label,
        className: spec.className,
        testid: spec.testid,
        onClick: function () {
          if (typeof spec.onClick === 'function') spec.onClick({ opener: btn });
        }
      });
      secondaryButtons.push(btn);
    });
    var cancelButton = null;
    var cancelAt = null; // the child the secondary controls go in front of
    function insertSecondary(node) {
      cluster.insertBefore(node, cancelAt);
    }
    function buildNarrowMenu() {
      var items = [];
      secondaryMenuSpecs = [];
      secondary.forEach(function (spec, k) {
        if (secondaryButtons[k].hidden) return;
        var mi = {
          label: spec.label,
          icon: spec.icon,
          disabled: secondaryButtons[k].disabled,
          onSelect: function () {
            if (typeof spec.onClick === 'function') spec.onClick({ opener: secondaryMenu.trigger });
          }
        };
        if (spec.testid) mi.testid = spec.testid + '-menu-item';
        items.push(mi);
        secondaryMenuSpecs.push(k);
      });
      if (!items.length) return;
      secondaryMenu = App.ui.menu({
        trigger: { variant: 'secondary', iconOnly: true, icon: 'more', ariaLabel: 'More actions' },
        popupLabel: 'More actions',
        align: 'end',
        items: items
      });
      secondaryMenu.trigger.setAttribute('data-testid', 'editor-more-btn');
    }
    // Draws the secondary controls for the current mode (wide buttons or the menu),
    // keeping focus: a focused control that goes away hands it to its counterpart.
    function renderSecondary() {
      var active = document.activeElement;
      var wasOnButton = secondaryButtons.indexOf(active) !== -1;
      var menuSpec = null; // spec index the focus was on in the menu (-1 for the trigger)
      if (secondaryMenu && secondaryMenu.el.contains(active)) {
        var nodes = secondaryMenu.popup.querySelectorAll('[role="menuitem"]');
        var at = Array.prototype.indexOf.call(nodes, active);
        menuSpec = at === -1 ? -1 : secondaryMenuSpecs[at];
      }
      var k;
      for (k = 0; k < secondaryButtons.length; k++) {
        if (secondaryButtons[k].parentNode) secondaryButtons[k].parentNode.removeChild(secondaryButtons[k]);
      }
      if (secondaryMenu) {
        secondaryMenu.destroy();
        if (secondaryMenu.el.parentNode) secondaryMenu.el.parentNode.removeChild(secondaryMenu.el);
        secondaryMenu = null;
      }
      if (narrowMode) {
        buildNarrowMenu();
        if (secondaryMenu) insertSecondary(secondaryMenu.el);
        if ((wasOnButton || menuSpec !== null) && secondaryMenu) secondaryMenu.trigger.focus();
      } else {
        for (k = 0; k < secondaryButtons.length; k++) insertSecondary(secondaryButtons[k]);
        if (menuSpec !== null) {
          var target = menuSpec >= 0 ? secondaryButtons[menuSpec] : null;
          if (!target || target.hidden) {
            target = secondaryButtons.filter(function (b) { return !b.hidden; })[0];
          }
          if (target) target.focus();
        }
      }
    }
    if (actions.cancel) {
      cancelButton = actionButton(actions.cancel, 'secondary', 'cancel-btn', 'Cancel');
      cluster.appendChild(cancelButton);
    }
    var saveButton = actionButton(actions.save, 'primary', 'save-btn', 'Save');
    cluster.appendChild(saveButton);
    cancelAt = cancelButton || saveButton;
    if (secondary.length) {
      narrowMode = util.narrow.matches();
      renderSecondary();
    }
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

    var header;
    if (isPage) {
      // The h1 also carries editor-title (App.focusAfter and the editor
      // selectors target it); tabindex -1 comes from pageHeader.
      pageHdr = App.ui.pageHeader({
        title: opts.title,
        intro: opts.subtitle,
        introTestid: opts.subtitleTestid,
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
    header.classList.add('ui-editor-shell-header');
    header.appendChild(errorEl);

    var dirty = false;
    var errorToken = 0;
    var busy = false;
    var cleanSave = !!actions.save.enabledWhenClean;
    var cleanCancel = !!(actions.cancel && actions.cancel.enabledWhenClean);
    var testHeld = false;
    var testLabelNode = null;
    var testLabelText = null;
    if (testButton) {
      // The visible label is the button's last text node; the icon is left alone.
      for (i = testButton.childNodes.length - 1; i >= 0; i--) {
        if (testButton.childNodes[i].nodeType === 3) {
          testLabelNode = testButton.childNodes[i];
          testLabelText = testLabelNode.nodeValue;
          break;
        }
      }
    }

    function apply() {
      unsaved.textContent = dirty ? 'Unsaved changes' : '';
      saveButton.disabled = busy || !(dirty || cleanSave);
      if (cancelButton) cancelButton.disabled = busy || !(dirty || cleanCancel);
      if (testButton) testButton.disabled = busy || testHeld;
    }
    apply();

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      if (unsubscribeNarrow) unsubscribeNarrow();
      if (observer) observer.disconnect();
      if (secondaryMenu) secondaryMenu.destroy();
    }
    if (secondary.length) {
      unsubscribeNarrow = util.narrow.subscribe(function (isNarrow) {
        // A header wiped from the document without destroy() lets go on the next change.
        if (header.isConnected) wasConnected = true;
        else if (wasConnected) {
          destroy();
          return;
        }
        if (isNarrow === narrowMode) return;
        narrowMode = isNarrow;
        renderSecondary();
      });
      // The narrow menu follows a wide button's hidden and disabled state.
      if (typeof MutationObserver === 'function') {
        observer = new MutationObserver(function () {
          if (narrowMode) renderSecondary();
        });
        secondaryButtons.forEach(function (b) {
          observer.observe(b, { attributes: true, attributeFilter: ['hidden', 'disabled'] });
        });
      }
    }

    return {
      el: header,
      secondaryButtons: secondaryButtons,
      destroy: destroy,
      titleEl: titleEl,
      errorEl: errorEl,
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
        var next = text || '';
        if (next && errorEl.textContent === next) {
          // The same message again must re-announce: clear, then restore next frame.
          errorEl.textContent = '';
          var token = ++errorToken;
          requestAnimationFrame(function () {
            if (token === errorToken) errorEl.textContent = next;
          });
        } else {
          errorToken++;
          errorEl.textContent = next;
        }
        if (text) errorEl.removeAttribute('data-empty');
        else errorEl.setAttribute('data-empty', '');
      },
      // setTestState({disabled, label}) (M31 F5 L05, DD4): holds Test disabled
      // across setDirty and setBusy until released with {disabled: false}; a label
      // replaces the visible text only (the icon survives), null restores the
      // configured one. A no-op without actions.test.
      setTestState: function (state) {
        if (!testButton) return;
        state = state || {};
        testHeld = !!state.disabled;
        if (testLabelNode) {
          var want = state.label === undefined || state.label === null ? testLabelText : state.label;
          if (testLabelNode.nodeValue !== want) testLabelNode.nodeValue = want;
          if (testButton.hasAttribute('aria-label') && !testButton.hasAttribute('data-orig-aria')) {
            testButton.setAttribute('data-orig-aria', testButton.getAttribute('aria-label'));
          }
          if (testButton.hasAttribute('data-orig-aria')) {
            testButton.setAttribute('aria-label',
              state.label ? state.label : testButton.getAttribute('data-orig-aria'));
          }
        }
        apply();
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
  //   action (a node, M36 F1 HAT): sits at the end of the title row, after the rule,
  //   right-aligned (div.ui-section-title-row > .ui-section-action); needs a title.
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
    if (opts.action && !opts.title) throw new Error('App.ui.section: action needs a title');
    var titleEl = null;
    if (opts.title) {
      titleEl = util.el(tag, { className: 'section-title', text: opts.title });
      if (opts.info || opts.action) {
        var rowKids = [titleEl];
        if (opts.info) {
          rowKids.push(App.ui.infoButton({
            description: opts.info.text,
            label: opts.info.label || opts.title,
            testid: opts.info.testid
          }).el);
        }
        if (opts.action) {
          rowKids.push(util.el('div', { className: 'ui-section-action' }, [opts.action]));
        }
        root.appendChild(util.el('div', { className: 'ui-section-title-row' }, rowKids));
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
  //   title ('Danger zone'), action {label, testid, confirmLabel ('Confirm
  //   delete?'), revertMs, dataset, onConfirm(revert), beforeArm(proceed),
  //   icon ('trash')}, or actions [action, ...] (M31 F2 L4: one delete-style
  //   button per action, in order; action is the one-item form), notice
  //   {testid}. Each action has its own beforeArm, which runs on that button's
  //   first click and decides whether to call proceed() (arm the button); it is
  //   skipped on the second click, which commits. An action with `heading` and/or
  //   `description` (opt-in) is wrapped with them in div.danger-zone-row (text block
  //   div.danger-zone-row-text: span.danger-zone-row-heading, span.danger-zone-row-desc,
  //   then the button); the description is the button's aria-describedby.
  //   div.editor-section.danger-zone holds div.section-title.danger-zone-title,
  //   then one button.btn-muted-destructive.delete-btn per action (a 16px icon,
  //   trash by default, then span[data-confirm-title] with the label, so the
  //   confirm title swap leaves the icon alone). With notice, an App.ui.banner
  //   (tone error, live 'alert': role=alert, rendered while empty) follows the
  //   last button as its sibling. A click runs App.ui.confirm on
  //   the button. button is the first button; setDisabled(value) applies to
  //   every button, setDisabled(value, index) to the one at index.
  var rowSeq = 0; // unique ids for the opt-in row descriptions (page-wide, never reused)
  App.ui.dangerZone = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var actions = opts.actions || (opts.action ? [opts.action] : []);
    if (!actions.length) throw new Error('App.ui.dangerZone: action.label is required');
    var root = util.el('div', { className: 'editor-section danger-zone' }, [
      util.el('div', { className: 'section-title danger-zone-title', text: opts.title || 'Danger zone' })
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
      if (actions[i].heading || actions[i].description) {
        // Opt-in row (an action with a heading and/or description): the text block on the
        // left, the button on the right; the rows stack. The description names the button.
        var text = util.el('div', { className: 'danger-zone-row-text' });
        if (actions[i].heading) {
          text.appendChild(util.el('span', {
            className: 'danger-zone-row-heading', text: actions[i].heading
          }));
        }
        if (actions[i].description) {
          rowSeq += 1;
          var desc = util.el('span', {
            className: 'danger-zone-row-desc', text: actions[i].description
          });
          desc.id = 'danger-zone-desc-' + rowSeq;
          b.setAttribute('aria-describedby', desc.id);
          text.appendChild(desc);
        }
        root.appendChild(util.el('div', { className: 'danger-zone-row' }, [text, b]));
      } else {
        root.appendChild(b);
      }
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
