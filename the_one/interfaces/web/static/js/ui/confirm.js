(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.confirm (alias App.confirmDelete) — canonical two-step in-place confirm helper (F5 leg 02).
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
  //
  // Lapse cue (M24 F07 leg confirm-lapse). Before this change, a timed-out
  // arm and a never-armed control were visually identical — a returning
  // operator could not tell "I let it lapse" from "I committed." The fix adds
  // a `.confirm-lapsed` class, marked ONLY by the timer's own expiry callback
  // and cleared unconditionally on the NEXT call to confirmDelete for this
  // itemEl (arm or commit branch alike, at the top of the function, before
  // the arm/commit decision is made).
  //
  // This is feedback-only, mechanically (leg AC-3): the arm/commit decision
  // below still depends solely on the binary `.confirm-delete` class —
  // `.confirm-lapsed` never gates it, it is purely a cosmetic marker cleared
  // on sight. Click count to commit is unchanged (still 2). revertMs's role
  // is unchanged (first click still starts it, commit still clears it via
  // the same clearTimeout call inside revert()).
  //
  // `revert()` is NOT where the lapse class is set — it has three callers
  // (timer expiry, a transport-failure `.catch`, and system-page.js's
  // credential-rotation SUCCESS path, which calls revertFn() after a
  // successful rotation with a comment saying so). Decorating `revert()`
  // itself would label a successful rotation "lapsed". Instead the timer's
  // own callback (below) marks the class, THEN calls the shared `revert()`
  // cleanup — so the two callers that invoke `revert` as `revertFn` (success,
  // transport failure) never touch `.confirm-lapsed` at all.
  //
  // Purely visual — no aria-live announcement. `self-configuration-tab.js`
  // already announces the ARM transition via its own `role=status` region
  // (added for WCAG 4.1.2, since its persistent aria-label overrides the
  // swapped title text as the accessible name); wiring an equivalent
  // announcement for LAPSE would mean either a per-call-site opt-in (which
  // AC-5 forbids — no call site may be special-cased) or the helper owning
  // a generic live-region contract, which is a larger surface than this leg
  // covers. Recorded as a deliberate decision, not an omission.

  // Moved into the library from static/js/confirm.js (M31 F1 L4); the
  // behaviour is unchanged. App.confirmDelete stays as the same function.
  App.ui.confirm = function (itemEl, onConfirm, opts) {
    if (!itemEl) return;
    opts = opts || {};
    var titleSelector = opts.titleSelector || '[data-confirm-title]';
    var confirmLabel = opts.confirmLabel || 'Confirm delete?';
    var revertMs = opts.revertMs || 3000;
    var titleEl = itemEl.querySelector(titleSelector);

    // Cleared on every call — arm or commit — so a returning operator's
    // next interaction with this control always starts from a clean visual
    // slate. This does NOT gate the arm/commit decision below; it runs
    // unconditionally before that decision is made.
    itemEl.classList.remove('confirm-lapsed');

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

    // Timer-expiry-only path: marks the lapse cue, THEN reverts. Distinct
    // from `revert` itself so the revertFn handed to callers (transport
    // failure, and system-page.js's success path) never marks lapse.
    function lapse() {
      itemEl.classList.add('confirm-lapsed');
      revert();
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
    itemEl._confirmRevertTimer = setTimeout(lapse, revertMs);
  };
  window.App.confirmDelete = App.ui.confirm;
})();
