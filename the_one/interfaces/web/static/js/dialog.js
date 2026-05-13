// App.confirmDialog — modal blocking-decision helper (F5 leg 04).
//
// Mirrors the F4-debrief-queued recommendation: a true modal dialog with
// focus-trap + Escape-cancel + Enter-confirm + restore-focus-on-close. Used
// by studio's dirty-state navigation gates (Back, section-nav, tile click,
// tab change). Distinct from App.confirmDelete (in-place two-step destructive
// confirm) — App.confirmDialog is the BLOCKING modal primitive for the
// "you are about to lose unsaved work" decision.
//
// Signature:
//   App.confirmDialog({title, message, confirmText, cancelText,
//                      onConfirm, onCancel, danger})
//   - All fields optional; defaults below.
//   - danger: bool (optional) — when true, adds the .danger class to the
//     Confirm button so the Holograph .confirm-dialog .btn-primary.danger
//     rule renders it red for destructive actions.
//   - Returns void (callback-driven, NOT a promise).
//
// Defaults — wording avoids the false-promise of "Discard" because this
// helper does NOT auto-revert form state on confirm; it only proceeds with
// navigation. So "Continue" / "Stay" reads more accurately than
// "Discard" / "Cancel".
//   title = 'Unsaved changes'
//   message = 'You have unsaved changes. Continue without saving?'
//   confirmText = 'Continue'
//   cancelText = 'Stay'
//
// DOM (Holograph modal vocabulary from L1.6 components.css):
//   <div class="modal-backdrop" role="dialog" aria-modal="true"
//        aria-labelledby="<title-id>" aria-describedby="<message-id>"
//        data-testid="confirm-dialog-overlay">
//     <div class="modal-shell confirm-dialog">
//       <div class="modal-header">
//         <h2 class="modal-title" id="<title-id>">{title}</h2>
//       </div>
//       <div class="modal-body">
//         <p id="<message-id>">{message}</p>
//       </div>
//       <div class="modal-footer">
//         <button class="btn btn-ghost" type="button"
//                 data-testid="modal-cancel-btn">{cancelText}</button>
//         <button class="btn btn-primary" type="button"
//                 data-testid="modal-confirm-btn">{confirmText}</button>
//       </div>
//     </div>
//   </div>
//
// Behavior:
//   - On open: append backdrop to document.body, capture document.activeElement
//     as the trigger (for restore-on-close), focus the Cancel button (safer
//     default for destructive-discard prompts).
//   - On Escape: onCancel() then close.
//   - On Enter (when focus is NOT in a textarea — let textareas keep their
//     newline behavior): onConfirm() then close.
//   - On Tab/Shift-Tab: full focus-trap — wrap focus within the dialog's
//     focusable descendants.
//   - On Cancel-button click: onCancel() then close.
//   - On Confirm-button click: onConfirm() then close.
//   - On backdrop click (outside the shell): no-op (does NOT call onCancel).
//     Prevents accidental dismissal when user accidentally taps outside.
//   - On close: remove backdrop from DOM, restore focus to the captured
//     trigger element.
//
// Singleton: a module-level `openDialog` ref ensures only one dialog is open
// at a time. Second call while one is open is a no-op + console.warn —
// surfaces spurious double-dispatch in dev/test without crashing or queuing.
//
// Capture-phase keydown listener (`document.addEventListener(..., true)`)
// ensures the modal sees keys before any focused-field listener can swallow
// them.
//
// OAuth-status modal note: the spec (Mission 09 §"OAuth-status modal") describes
// an aspirational 480px .modal-shell with an inline-spinner shown while an OAuth
// popup is open. The current OAuth UX uses an inline "Login required" button
// rendered into the chat stream + a system-browser popup for the IdP consent
// screen — no in-app modal between click and resolution. L6.3 leaves that
// existing inline-button UX in place; implementing the aspirational modal is
// deferred to a future flight.
(function (window, document) {
  'use strict';
  window.App = window.App || {};

  var openDialog = null;

  window.App.confirmDialog = function (opts) {
    if (openDialog) {
      if (window.console && console.warn) {
        console.warn('App.confirmDialog: already open; second call ignored.');
      }
      return;
    }
    opts = opts || {};
    var title = opts.title || 'Unsaved changes';
    var message = opts.message ||
      'You have unsaved changes. Continue without saving?';
    var confirmText = opts.confirmText || 'Continue';
    var cancelText = opts.cancelText || 'Stay';
    var onConfirm = typeof opts.onConfirm === 'function' ? opts.onConfirm : function () {};
    var onCancel = typeof opts.onCancel === 'function' ? opts.onCancel : function () {};
    var danger = !!opts.danger;

    var trigger = document.activeElement;

    // ── Backdrop (was .modal-overlay) ────────────────────────────────────────
    var backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop';
    backdrop.setAttribute('role', 'dialog');
    backdrop.setAttribute('aria-modal', 'true');
    backdrop.setAttribute('data-testid', 'confirm-dialog-overlay');

    // Unique ids per-open so multiple sequential opens don't collide and
    // aria-labelledby/describedby always point at the right elements.
    var stamp = String(Date.now()) + '-' + Math.floor(Math.random() * 100000);
    var titleId = 'modal-title-' + stamp;
    var msgId = 'modal-msg-' + stamp;
    backdrop.setAttribute('aria-labelledby', titleId);
    backdrop.setAttribute('aria-describedby', msgId);

    // ── Shell (was .modal-dialog) ─────────────────────────────────────────────
    var shell = document.createElement('div');
    shell.className = 'modal-shell confirm-dialog';
    backdrop.appendChild(shell);

    // ── Header ────────────────────────────────────────────────────────────────
    var header = document.createElement('div');
    header.className = 'modal-header';
    shell.appendChild(header);

    var titleEl = document.createElement('h2');
    titleEl.className = 'modal-title';
    titleEl.id = titleId;
    titleEl.textContent = title;
    header.appendChild(titleEl);

    // ── Body ──────────────────────────────────────────────────────────────────
    var body = document.createElement('div');
    body.className = 'modal-body';
    shell.appendChild(body);

    var msgEl = document.createElement('p');
    msgEl.id = msgId;
    msgEl.textContent = message;
    body.appendChild(msgEl);

    // ── Footer (was .modal-actions form-actions) ───────────────────────────────
    var footer = document.createElement('div');
    footer.className = 'modal-footer';
    shell.appendChild(footer);

    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn btn-ghost';
    cancelBtn.textContent = cancelText;
    cancelBtn.setAttribute('data-testid', 'modal-cancel-btn');
    footer.appendChild(cancelBtn);

    var confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.className = danger ? 'btn btn-primary danger' : 'btn btn-primary';
    confirmBtn.textContent = confirmText;
    confirmBtn.setAttribute('data-testid', 'modal-confirm-btn');
    footer.appendChild(confirmBtn);

    function close() {
      document.removeEventListener('keydown', onKey, true);
      backdrop.removeEventListener('click', onBackdropClick);
      if (backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
      openDialog = null;
      // Restore focus. If the trigger was removed from the DOM (e.g., a
      // deleted tile), .focus() is a no-op (browser falls back to body).
      if (trigger && typeof trigger.focus === 'function') {
        try { trigger.focus(); } catch (e) { /* ignore */ }
      }
    }

    cancelBtn.addEventListener('click', function () {
      onCancel();
      close();
    });
    confirmBtn.addEventListener('click', function () {
      onConfirm();
      close();
    });

    function focusables() {
      var sel = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
      var nodes = shell.querySelectorAll(sel);
      var arr = Array.prototype.slice.call(nodes);
      return arr.filter(function (n) {
        return !n.disabled && n.offsetParent !== null;
      });
    }

    function onKey(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
        close();
        return;
      }
      if (e.key === 'Enter') {
        var tag = e.target && e.target.tagName;
        // Let textareas keep newline behavior. Inputs commit; the dialog
        // body has no inputs by default, so this just affects future
        // modals that grow form fields.
        if (tag === 'TEXTAREA') return;
        e.preventDefault();
        onConfirm();
        close();
        return;
      }
      if (e.key === 'Tab') {
        var fs = focusables();
        if (fs.length === 0) {
          e.preventDefault();
          return;
        }
        var first = fs[0];
        var last = fs[fs.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    function onBackdropClick(e) {
      // Click on the backdrop itself (NOT a shell descendant) is a no-op.
      // This is a deliberate choice — we require explicit Cancel/Escape to
      // dismiss. Prevents accidental loss of work from a stray outside-click.
      if (e.target === backdrop) {
        e.preventDefault();
        e.stopPropagation();
      }
    }

    // Capture-phase keydown so the modal sees keys before any focused-field
    // handler can swallow them.
    document.addEventListener('keydown', onKey, true);
    backdrop.addEventListener('click', onBackdropClick);

    openDialog = { close: close };
    document.body.appendChild(backdrop);

    // Focus Cancel by default — safer for destructive-discard prompts (the
    // user must move focus to Confirm explicitly).
    cancelBtn.focus();
  };
})(window, document);
