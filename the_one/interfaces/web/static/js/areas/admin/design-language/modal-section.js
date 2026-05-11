(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // MODAL section: static .modal-dialog preview (no overlay backdrop —
  // positioned relative so it sits in the gallery flow) + ONE live
  // "Open modal" button wired to App.confirmDialog. The canonical signature
  // per dialog.js:11, :82-83 uses confirmText/cancelText (NOT confirmLabel —
  // the helper silently ignores unknown keys and falls back to defaults).
  // Overlay-click-to-dismiss is intentionally a no-op per dialog.js:203-211.
  function render(host) {
    host.innerHTML =
      // --- Static dialog preview (no backdrop) ---
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">modal-dialog (static preview, no overlay)</span>' +
        '<div class="modal-dialog" style="position: relative; inset: auto; max-width: 480px;">' +
          '<div class="modal-dialog-title">Sample modal</div>' +
          '<div class="modal-dialog-message">This is the canonical confirm dialog primitive, rendered statically inside the gallery for shape reference.</div>' +
          '<div class="modal-actions form-actions">' +
            '<button type="button" class="btn-outlined-primary">Cancel</button>' +
            '<button type="button" class="btn-filled-primary">OK</button>' +
          '</div>' +
        '</div>' +
      '</div>' +

      // --- Live trigger ---
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">live trigger</span>' +
        '<div>' +
          '<button type="button" class="btn-outlined-primary" data-action="open-sample-modal">Open modal</button>' +
        '</div>' +
      '</div>';

    var trigger = host.querySelector('[data-action="open-sample-modal"]');
    if (trigger && window.App && typeof window.App.confirmDialog === 'function') {
      trigger.addEventListener('click', function () {
        window.App.confirmDialog({
          title: 'Sample modal',
          message: 'This is the canonical confirm dialog primitive. Press OK or Cancel (or Escape) to dismiss.',
          confirmText: 'OK',
          cancelText: 'Cancel',
          onConfirm: function () { /* no-op */ },
          onCancel: function () { /* no-op */ }
        });
      });
    }
  }

  window.App.admin.designLanguage.modalSection = { render: render };
})();
