(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.confirm — canonical two-step in-place confirm helper (F5 leg 02).
  //
  // Extracted from chat.js + studio.js inline implementations so chat session
  // items, studio agent tiles, and any future destructive-affordance site share
  // one source of truth.
  //
  // Signature:
  //   App.ui.confirm(itemEl, onConfirm, opts?)
  //   - itemEl: parent activatable element bearing the confirm-delete class
  //     state and containing the title element identified by titleSelector.
  //   - onConfirm: (itemEl, revertFn) => void  — called on the second click.
  //     The revertFn argument lets transport-failure paths roll back the UI
  //     (e.g., studio's DELETE fetch's .catch calls revertFn() to restore the
  //     tile's name + remove the confirm-delete class).
  //   - opts: { titleSelector?, confirmLabel?, revertMs?, announceName? }
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
  // and cleared unconditionally on the NEXT call to App.ui.confirm for this
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
  // Announcement (M31 F2 L5, squawk 0220; reverses the old "purely visual" decision).
  // Arming, lapsing and committing are announced through ONE shared polite live
  // region (div.visually-hidden[role=status][aria-live=polite],
  // data-testid="ui-confirm-live"), appended to document.body lazily on the first
  // arm, cached, and re-appended if detached. The wording lives in one place
  // (armSentence / lapseSentence):
  //   arm:    "Press {subject} again to {confirmLabel lower-cased, no trailing ?}."
  //   lapse:  "{subject}: not confirmed"
  //   commit: the region is cleared.
  // {subject} is opts.announceName, else the control's aria-label, else the
  // original title text, read at arm time, so the item identity survives a
  // persistent aria-label that overrides the swapped title as the accessible name.
  // Every write goes through one pending-timeout handle: the region is cleared,
  // then written on the next tick (so a repeated identical arm re-announces), and
  // each new write cancels the previous one, so a lapse cannot race a following arm.
  // Visual behaviour is unchanged. No call site opts in.

  // Moved into the library from static/js/confirm.js (M31 F1 L4); the
  // behaviour is unchanged. 
  var liveRegion = null;
  var livePending = null;

  function ensureRegion() {
    if (!liveRegion) {
      liveRegion = document.createElement('div');
      liveRegion.className = 'visually-hidden';
      liveRegion.setAttribute('role', 'status');
      liveRegion.setAttribute('aria-live', 'polite');
      liveRegion.setAttribute('data-testid', 'ui-confirm-live');
    }
    if (!liveRegion.isConnected) document.body.appendChild(liveRegion);
    return liveRegion;
  }

  // Writes text (or clears it, for empty text) through the single pending handle.
  function announce(text) {
    if (livePending) {
      clearTimeout(livePending);
      livePending = null;
    }
    if (!text) {
      if (liveRegion) liveRegion.textContent = '';
      return;
    }
    var region = ensureRegion();
    region.textContent = '';
    livePending = setTimeout(function () {
      livePending = null;
      region.textContent = text;
    }, 0);
  }

  function armSentence(subject, confirmLabel) {
    var action = String(confirmLabel).replace(/\?\s*$/, '').toLowerCase();
    return 'Press ' + subject + ' again to ' + action + '.';
  }

  function lapseSentence(subject) {
    return subject + ': not confirmed';
  }

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

    function armChange(armed) {
      if (typeof opts.onArmChange === 'function') opts.onArmChange(armed);
    }

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
      armChange(false);
    }

    // Timer-expiry-only path: marks the lapse cue, THEN reverts. Distinct
    // from `revert` itself so the revertFn handed to callers (transport
    // failure, and system-page.js's success path) never marks lapse.
    function lapse() {
      // Squawk 0237 (M31 F4 L03b): an element removed from the page while armed only
      // reverts - no cue and no announcement for a control the user can no longer reach.
      if (!itemEl.isConnected) {
        revert();
        return;
      }
      itemEl.classList.add('confirm-lapsed');
      var subject = itemEl._confirmSubject;
      revert();
      announce(lapseSentence(subject));
    }

    if (itemEl.classList.contains('confirm-delete')) {
      // Second click within the revert window — commit.
      if (itemEl._confirmRevertTimer) {
        clearTimeout(itemEl._confirmRevertTimer);
        itemEl._confirmRevertTimer = null;
      }
      announce('');
      armChange(false);
      // revertFn lets transport-failure callers roll the UI back.
      if (typeof onConfirm === 'function') onConfirm(itemEl, revert);
      return;
    }

    // First click — arm. Capture the original title NOW (before swap).
    itemEl._confirmOriginalTitle = titleEl ? titleEl.textContent : '';
    itemEl._confirmSubject = opts.announceName || itemEl.getAttribute('aria-label') ||
      itemEl._confirmOriginalTitle || 'this control';
    itemEl.classList.add('confirm-delete');
    if (titleEl) titleEl.textContent = confirmLabel;
    announce(armSentence(itemEl._confirmSubject, confirmLabel));
    armChange(true);
    itemEl._confirmRevertTimer = setTimeout(lapse, revertMs);
  };
})();
