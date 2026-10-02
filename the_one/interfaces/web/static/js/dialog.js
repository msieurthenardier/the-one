// App.confirmDialog — modal blocking-decision helper (F5 leg 04).
//
// A thin adapter over App.ui.modal (M25 F2 L2, DD6): a native <dialog> with
// showModal(), Escape-cancel, a manual Tab wrap and restore-focus-on-close. Used
// by studio's dirty-state navigation gates (Back, section-nav, tile click,
// tab change). Distinct from App.confirmDelete (in-place two-step destructive
// confirm) — App.confirmDialog is the BLOCKING modal primitive for the
// "you are about to lose unsaved work" decision.
//
// Signature:
//   App.confirmDialog({title, message, confirmText, cancelText,
//                      opener, onConfirm, onCancel})
//   - All fields optional; defaults below.
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
// DOM (built by App.ui.modal):
//   <dialog class="modal-overlay" role="dialog" aria-modal="true"
//           data-testid="confirm-dialog-overlay" aria-labelledby aria-describedby>
//     <div class="modal-dialog" tabindex="-1">
//       <h2 class="modal-dialog-title">{title}</h2>
//       <p class="modal-dialog-message">{message}</p>
//       <div class="modal-actions form-actions">
//         <button data-testid="modal-cancel-btn">{cancelText}</button>
//         <button data-testid="modal-confirm-btn">{confirmText}</button>
//       </div>
//     </div>
//   </dialog>
//
// Behavior:
//   - Opener: opts.opener (an element; focus returns to it on close), else
//     document.activeElement when it is not <body>, else #main-content. Cancel
//     (Stay) is focused on open: the safer default for a destructive-discard
//     prompt.
//   - Escape: onCancel(). Cancel button: onCancel(). Confirm button: onConfirm().
//   - Enter is NATIVE: it activates the focused button (Stay by default). There
//     is no document-level Enter handler (a visibly focused Stay must never
//     discard work).
//   - Tab / Shift+Tab wrap inside the dialog. A backdrop click does nothing
//     (the modal is not dismissible).
//   - The dialog is removed from the DOM on close, then focus is restored,
//     then the callback runs.
//
// No singleton (M25 F2 L5): a second call stacks above the first, like
// App.ui.modal. Production code never stacks two -- App.nav (nav.js) is the only
// caller of guard dialogs and owns de-duplication -- but isOpen() is backed by an
// open COUNT so it stays true while any confirm is open and closing the top one
// never clears the one beneath.
(function (window, document) {
  'use strict';
  window.App = window.App || {};

  var openCount = 0;

  window.App.confirmDialog = function (opts) {
    opts = opts || {};
    var onConfirm = typeof opts.onConfirm === 'function' ? opts.onConfirm : function () {};
    var onCancel = typeof opts.onCancel === 'function' ? opts.onCancel : function () {};

    var active = document.activeElement;
    var opener = opts.opener ||
      (active && active !== document.body && active !== document.documentElement
        ? active
        : document.getElementById('main-content'));

    var modal = window.App.ui.modal({
      title: opts.title || 'Unsaved changes',
      body: opts.message || 'You have unsaved changes. Continue without saving?',
      testid: 'confirm-dialog-overlay',
      cancelValue: 'cancel',
      actions: [
        {
          label: opts.cancelText || 'Stay',
          variant: 'secondary',
          value: 'cancel',
          testid: 'modal-cancel-btn',
          autofocus: true
        },
        {
          label: opts.confirmText || 'Continue',
          variant: 'primary',
          value: 'confirm',
          testid: 'modal-confirm-btn'
        }
      ],
      onClose: function (value) {
        openCount = Math.max(0, openCount - 1);
        if (value === 'confirm') onConfirm();
        else onCancel();
      }
    });
    // showModal() can throw (e.g. a detached element). modal.open() has by then
    // registered its session, so close it: that runs onClose exactly once, which
    // drops the count and settles the caller as Stay (onCancel), then rethrow.
    // If onClose somehow did not run, drop the count here so isOpen() cannot
    // stay stuck true and make every later navigation resolve Stay.
    openCount += 1;
    try {
      modal.open(opener);
    } catch (err) {
      var before = openCount;
      modal.close('cancel');
      if (openCount === before) openCount = Math.max(0, openCount - 1);
      throw err;
    }
  };

  // True while any dialog opened through this adapter is open. The router's
  // guard adapter uses it to resolve Stay when a dialog is already in charge.
  window.App.confirmDialog.isOpen = function () { return openCount > 0; };
})(window, document);
