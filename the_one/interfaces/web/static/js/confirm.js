// App.confirmDelete — canonical two-step in-place confirm helper (F5 leg 02).
//
// Extracted from chat.js + studio.js inline implementations so chat session
// items, studio agent tiles, and any future destructive-affordance site share
// one source of truth.
//
// Signature:
//   App.confirmDelete(itemEl, onConfirm, opts?)
//   - itemEl: parent activatable element bearing the confirm-delete class
//     state and containing the title element identified by titleSelector.
//   - onConfirm: (itemEl, revertFn) => void  — called on the second click.
//     The revertFn argument lets transport-failure paths roll back the UI
//     (e.g., studio's DELETE fetch's .catch calls revertFn() to restore the
//     tile's name + remove the confirm-delete class).
//   - opts: { titleSelector?, confirmLabel?, revertMs? }
//     defaults: '[data-confirm-title]', 'Confirm delete?', 3000.
//
// Behavior:
//   First call (itemEl does NOT have .confirm-delete) — adds the class,
//   replaces the title element's text with confirmLabel, captures the
//   ORIGINAL title on itemEl._confirmOriginalTitle, starts a revertMs
//   timer that on expiry restores the original text + removes the class.
//
//   Second call (within the timer window) — clears the timer and invokes
//   onConfirm(itemEl, revertFn). The caller decides when to call revertFn.
//
// Capture discipline: original title is captured ONLY in the first-click
// branch. Capturing on every call would record the placeholder ('Confirm
// delete?') on the second click, and a subsequent revert would overwrite
// the user's data. The leg artifact step 1 spells this out verbatim.
//
// Keydown-bubble guard is NOT this helper's responsibility — that lives on
// the parent activatable element (per the resolved Open Question for F5).
(function (window) {
  'use strict';
  window.App = window.App || {};

  window.App.confirmDelete = function (itemEl, onConfirm, opts) {
    if (!itemEl) return;
    opts = opts || {};
    var titleSelector = opts.titleSelector || '[data-confirm-title]';
    var confirmLabel = opts.confirmLabel || 'Confirm delete?';
    var revertMs = opts.revertMs || 3000;
    var titleEl = itemEl.querySelector(titleSelector);

    function revert() {
      if (itemEl._confirmRevertTimer) {
        clearTimeout(itemEl._confirmRevertTimer);
        itemEl._confirmRevertTimer = null;
      }
      itemEl.classList.remove('confirm-delete');
      if (titleEl && itemEl._confirmOriginalTitle != null) {
        titleEl.textContent = itemEl._confirmOriginalTitle;
      }
      itemEl._confirmOriginalTitle = null;
    }

    if (itemEl.classList.contains('confirm-delete')) {
      // Second click within the revert window — commit.
      if (itemEl._confirmRevertTimer) {
        clearTimeout(itemEl._confirmRevertTimer);
        itemEl._confirmRevertTimer = null;
      }
      // revertFn lets transport-failure callers roll the UI back.
      if (typeof onConfirm === 'function') onConfirm(itemEl, revert);
      return;
    }

    // First click — arm. Capture the original title NOW (before swap).
    itemEl._confirmOriginalTitle = titleEl ? titleEl.textContent : '';
    itemEl.classList.add('confirm-delete');
    if (titleEl) titleEl.textContent = confirmLabel;
    itemEl._confirmRevertTimer = setTimeout(revert, revertMs);
  };
})(window);
