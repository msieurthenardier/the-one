(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.modal(opts) -> {el, open(opener), close(result), isOpen()}  (M25 F2 L2, DD6)
  //
  // A native <dialog> opened with showModal(), implementing the DD8 stacking rule:
  //   - the opener is recorded EXPLICITLY (open(opener)), never document.activeElement;
  //   - focus moves explicitly on open (the action with autofocus: true, else the first action, else the first focusable, else the card);
  //   - Escape is handled on keydown on the dialog with preventDefault AND
  //     stopPropagation and closes the topmost modal only; `cancel` is prevented and
  //     routed through the same path;
  //   - a close event while dlg.open is true is a STALE event (close() queues its event
  //     as a task, so a dialog reopened in the same turn receives the old one) and is
  //     ignored; a genuine close that bypassed the router (!dlg.open, not finished) runs
  //     the full cancel path exactly once;
  //   - a backdrop click closes only when dismissible AND both mousedown and click
  //     targeted the <dialog> itself (a text-selection drag out of the card never closes);
  //   - Tab / Shift+Tab wrap manually (native modals let Tab escape to browser chrome).
  //
  // opts:
  //   title      heading text (an <h2>, set with textContent)
  //   body       text (a <p>) or a Node (wrapped in a div); both are the described-by target
  //   actions    [{label, variant, value, testid, autofocus}] built with App.ui.button
  //   dismissible  backdrop click closes (default false)
  //   cancelValue  the value Escape / backdrop / unrouted closes report (default null)
  //   onClose(value)  fires exactly once per open, AFTER close, DOM removal and focus restore
  //   id, testid  placed on the <dialog>
  //
  // Chooser options (M25 F4 L1, DD14), all optional; with none of them set a modal is
  // built exactly as before (padding, aria-describedby, centring):
  //   width        a pixel number: the card's width (inline style); its max-width stays
  //                100% of the overlay's content box, i.e. the viewport minus 32px
  //   top          a pixel number: the card aligns to that offset from the viewport's
  //                top instead of the centre (inline align-self + margin-top on the card,
  //                net of the overlay's 16px padding), and its max-height becomes the
  //                viewport height minus top and 16px
  //   initialFocus a Node inside the card, focused on open() instead of the default order
  //   closeButton  {label, ariaLabel, testid}: a btn-ghost btn-sm button at the end of
  //                the header row that closes with cancelValue (it takes part in the Tab
  //                wrap; focus then returns to the opener as on any close)
  //   footer       a Node rendered after the body, in .modal-dialog-footer (pass a
  //                DocumentFragment to make its items the row's flex children -- it is
  //                copied per open(), so listeners on it are not kept; an item with
  //                .modal-dialog-footer-end is pushed to the end)
  //   layout       'chooser': zero card padding, a flex header row (title, close) padded
  //                16px 20px 12px, the body (a Node) full-bleed in .modal-dialog-body, the
  //                footer as the 11px muted row; NO aria-describedby (a screen reader must
  //                not read a whole list on open) and no actions row (actions throw). The
  //                title stays the <h2> the dialog's aria-labelledby references.
  // Focus on open(): initialFocus when given and connected inside the card; else, when a
  // close button or the chooser layout is in play, the first focusable in the BODY (never
  // the header's close button); else the usual order above.
  //
  // ariaLabel (M25 F4 L7, DD14): a non-empty string that names a modal with NO visible
  // title (the jump-to palette). The dialog gets aria-label and no aria-labelledby, and
  // the card has no <h2> and no .modal-dialog-header row at all. It throws with a title
  // (pass one or the other) or a closeButton (there is no header to hold one): the
  // caller's body owns any close button and calls controller.close(); the Tab wrap
  // includes it like any other focusable in the card.
  //
  // App.ui.modal.anyOpen() (M25 F4 L7) -> true while any modal built here is open, on any
  // controller (stack.length > 0). Every App.confirmDialog is one of them (it is an
  // adapter over this factory), so this is the one source for "is a modal in charge".
  //
  // The <dialog> is created on open() and removed from the DOM on close. Modals stack:
  // there is no singleton here, and App.confirmDialog (its adapter) stacks too.

  var el = App.ui.util.el;
  var stack = [];

  function focusables(root) {
    var nodes = root.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    var out = [];
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (!n.disabled && n.getClientRects().length > 0) out.push(n);
    }
    return out;
  }

  App.ui.modal = function (opts) {
    opts = opts || {};
    var actions = opts.actions || [];
    var cancelValue = opts.cancelValue === undefined ? null : opts.cancelValue;
    var session = null;
    if (opts.layout !== undefined && opts.layout !== 'chooser') {
      throw new Error('App.ui.modal: unknown layout "' + opts.layout + '"');
    }
    var chooser = opts.layout === 'chooser';
    if (chooser && actions.length) throw new Error('App.ui.modal: the chooser layout has no actions');
    if (chooser && !(opts.body && opts.body.nodeType)) {
      throw new Error('App.ui.modal: the chooser layout needs a Node body');
    }
    if (opts.footer !== undefined && opts.footer !== null && !opts.footer.nodeType) {
      throw new Error('App.ui.modal: footer must be a Node');
    }
    if (opts.closeButton && !opts.closeButton.label && !opts.closeButton.ariaLabel) {
      throw new Error('App.ui.modal: closeButton needs a label or an ariaLabel');
    }
    if (opts.ariaLabel !== undefined && opts.ariaLabel !== null &&
        (typeof opts.ariaLabel !== 'string' || !opts.ariaLabel)) {
      throw new Error('App.ui.modal: ariaLabel must be a non-empty string');
    }
    var labelOnly = !!opts.ariaLabel;
    if (labelOnly && opts.title) {
      throw new Error('App.ui.modal: ariaLabel names a modal with no title (pass one, not both)');
    }
    if (labelOnly && opts.closeButton) {
      throw new Error('App.ui.modal: a modal named by ariaLabel has no header for a closeButton');
    }

    function topmost() {
      return stack.length ? stack[stack.length - 1] : null;
    }

    function restoreFocus(s) {
      var target = s.opener && s.opener.isConnected ? s.opener : null;
      if (!target) target = document.getElementById('main-content');
      if (target && typeof target.focus === 'function') {
        try {
          target.focus();
        } catch (e) {
          /* ignore */
        }
      }
    }

    // finish(s, value): close, remove from the DOM, restore focus, then onClose.
    // Idempotent per session: onClose fires exactly once however the close arrives.
    function finish(s, value) {
      if (s.done) return;
      s.done = true;
      var i = stack.indexOf(s);
      if (i !== -1) stack.splice(i, 1);
      if (session === s) session = null;
      if (s.dlg.open) s.dlg.close();
      if (s.dlg.parentNode) s.dlg.parentNode.removeChild(s.dlg);
      restoreFocus(s);
      if (typeof opts.onClose === 'function') opts.onClose(value);
    }

    function closeTopmost() {
      var top = topmost();
      if (top) top.finish(cancelValue);
    }

    function build() {
      var s = { done: false, opener: null, downTarget: null, bodyEl: null, closeBtn: null };
      var titleId = App.ui.util.uid('modal-title');
      var bodyId = App.ui.util.uid('modal-body');
      var children = [];
      // ariaLabel: no heading at all (the dialog's aria-label names it).
      var title = labelOnly
        ? null
        : el('h2', { className: 'modal-dialog-title', id: titleId, text: opts.title || '' });
      var cb = opts.closeButton;
      if (cb) {
        s.closeBtn = App.ui.button({
          label: cb.label,
          ariaLabel: cb.ariaLabel,
          variant: 'ghost',
          size: 'sm',
          testid: cb.testid,
          onClick: function () {
            finish(s, cancelValue);
          }
        });
      }
      // With ariaLabel there is no header row: the body comes first (and may hold
      // its own close button).
      if (!labelOnly && (chooser || s.closeBtn)) {
        children.push(el('div', { className: 'modal-dialog-header' }, [title, s.closeBtn]));
      } else if (!labelOnly) {
        children.push(title);
      }
      var hasBody = opts.body !== undefined && opts.body !== null && opts.body !== '';
      if (chooser) {
        s.bodyEl = el('div', { className: 'modal-dialog-body' }, [opts.body]);
        children.push(s.bodyEl);
      } else if (hasBody) {
        if (typeof opts.body === 'string') {
          s.bodyEl = el('p', { className: 'modal-dialog-message', id: bodyId, text: opts.body });
        } else {
          s.bodyEl = el('div', { className: 'modal-dialog-message', id: bodyId }, [opts.body]);
        }
        children.push(s.bodyEl);
      }
      if (opts.footer) {
        // A fragment empties when appended, so each open() gets a copy of it.
        var footerNode = opts.footer.nodeType === 11 ? opts.footer.cloneNode(true) : opts.footer;
        children.push(el('div', { className: 'modal-dialog-footer' }, [footerNode]));
      }
      var buttons = [];
      var autofocusBtn = null;
      actions.forEach(function (a) {
        var btn = App.ui.button({
          label: a.label,
          variant: a.variant || 'secondary',
          testid: a.testid,
          onClick: function () {
            finish(s, a.value);
          }
        });
        if (a.autofocus && !autofocusBtn) autofocusBtn = btn;
        buttons.push(btn);
      });
      if (buttons.length) {
        children.push(el('div', { className: 'modal-actions form-actions' }, buttons));
      }
      var card = el('div', {
        className: chooser ? 'modal-dialog modal-dialog-chooser' : 'modal-dialog',
        tabindex: '-1'
      }, children);
      // width / top: inline styles on the opted-in card only (the overlay and every
      // other card keep their stylesheet geometry). 16 is the overlay's padding.
      if (typeof opts.width === 'number') {
        card.style.width = opts.width + 'px';
        card.style.maxWidth = '100%';
      }
      if (typeof opts.top === 'number') {
        card.style.alignSelf = 'flex-start';
        card.style.marginTop = Math.max(0, opts.top - 16) + 'px';
        card.style.maxHeight = 'calc(100vh - ' + (Math.max(16, opts.top) + 16) + 'px)';
      }
      var attrs = {
        className: 'modal-overlay',
        role: 'dialog',
        'aria-modal': 'true',
        'aria-labelledby': labelOnly ? null : titleId,
        'aria-label': labelOnly ? opts.ariaLabel : null,
        'aria-describedby': hasBody && !chooser ? bodyId : null,
        id: opts.id
      };
      var dlg = el('dialog', attrs, [card]);
      if (opts.testid) dlg.setAttribute('data-testid', opts.testid);
      s.dlg = dlg;
      s.card = card;
      s.buttons = buttons;
      s.autofocusBtn = autofocusBtn;
      s.finish = function (value) {
        finish(s, value);
      };

      dlg.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
          e.preventDefault();
          e.stopPropagation();
          closeTopmost();
          return;
        }
        if (e.key === 'Tab') {
          var fs = focusables(card);
          if (fs.length === 0) {
            e.preventDefault();
            card.focus();
            return;
          }
          var active = document.activeElement;
          var first = fs[0];
          var last = fs[fs.length - 1];
          // Focus on the <dialog> or the card itself (not in the list): enter at an end.
          var outside = fs.indexOf(active) === -1;
          if (e.shiftKey && (active === first || outside)) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && (active === last || outside)) {
            e.preventDefault();
            first.focus();
          }
        }
      });
      dlg.addEventListener('cancel', function (e) {
        e.preventDefault();
        closeTopmost();
      });
      dlg.addEventListener('close', function () {
        // A close while dlg.open is true is a stale event from an earlier close.
        if (dlg.open || s.done) return;
        // A genuine close that bypassed the router: run the full cancel path once.
        finish(s, cancelValue);
      });
      dlg.addEventListener('mousedown', function (e) {
        s.downTarget = e.target;
      });
      dlg.addEventListener('click', function (e) {
        var down = s.downTarget;
        s.downTarget = null;
        if (opts.dismissible && down === dlg && e.target === dlg) finish(s, cancelValue);
      });
      return s;
    }

    var controller = {
      open: function (opener) {
        if (session) return;
        var s = build();
        s.opener = opener || null;
        session = s;
        stack.push(s);
        document.body.appendChild(s.dlg);
        s.dlg.showModal();
        var target = null;
        var init = opts.initialFocus;
        if (init && init.nodeType && init.isConnected && s.card.contains(init)) target = init;
        if (!target && (chooser || s.closeBtn) && s.bodyEl) target = focusables(s.bodyEl)[0] || null;
        if (!target) target = s.autofocusBtn || s.buttons[0] || null;
        if (!target) {
          var fs = focusables(s.card);
          for (var i = 0; i < fs.length && !target; i++) {
            if (fs[i] !== s.closeBtn) target = fs[i];
          }
          if (!target) target = fs[0] || s.card;
        }
        target.focus();
      },
      close: function (result) {
        if (session) finish(session, result);
      },
      isOpen: function () {
        return !!session && !session.done;
      }
    };
    Object.defineProperty(controller, 'el', {
      enumerable: true,
      get: function () {
        return session ? session.dlg : null;
      }
    });
    return controller;
  };

  // True while any modal is open (the shared stack is non-empty), the leave guard's
  // App.confirmDialog included. The shell's Ctrl K rule asks it (M25 F4 L7, DD9).
  App.ui.modal.anyOpen = function () {
    return stack.length > 0;
  };
})();
