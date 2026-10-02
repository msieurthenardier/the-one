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
      var s = { done: false, opener: null, downTarget: null };
      var titleId = App.ui.util.uid('modal-title');
      var bodyId = App.ui.util.uid('modal-body');
      var children = [];
      children.push(el('h2', { className: 'modal-dialog-title', id: titleId, text: opts.title || '' }));
      var hasBody = opts.body !== undefined && opts.body !== null && opts.body !== '';
      if (hasBody) {
        if (typeof opts.body === 'string') {
          children.push(el('p', { className: 'modal-dialog-message', id: bodyId, text: opts.body }));
        } else {
          children.push(el('div', { className: 'modal-dialog-message', id: bodyId }, [opts.body]));
        }
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
      var card = el('div', { className: 'modal-dialog', tabindex: '-1' }, children);
      var attrs = {
        className: 'modal-overlay',
        role: 'dialog',
        'aria-modal': 'true',
        'aria-labelledby': titleId,
        'aria-describedby': hasBody ? bodyId : null,
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
        var target = s.autofocusBtn || s.buttons[0] || focusables(s.card)[0] || s.card;
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
})();
