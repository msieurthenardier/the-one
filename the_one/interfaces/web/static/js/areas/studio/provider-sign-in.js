// App.studio.wirePlanSignIn -- the Anthropic plan sign-in of the provider editor (M19 F01 L03),
// split out of provider-editor.js (M36 F5 L2). provider-editor.js calls
//
//   App.studio.wirePlanSignIn(h, container, provider, requestCreateSave)
//
// once per mount. App.studio.clearProviderSignInHandoff() (providers-section.js's reset) clears
// the create-to-edit hand-off below.
//
// OAuth sign-in UX for the anthropic-plan type (flight DD-1 / DD-7).
// State machine: signed-out → awaiting-code → connected, derived
// from provider.oauth_active plus a local awaitingUrl. There is NO
// persistent "revoked" state — the /test result's reauth_required status
// is the only revoked signal; the connected state's Re-authenticate
// control is the standing re-auth affordance.
//
// Create mode is auto-save-then-start (HAT fix, supersedes the original
// disabled-until-saved gate): the OAuth endpoints are
// /api/providers/{id}/… and need the row to exist, so a create-mode
// Sign-in click first runs the EXACT create path the Create button uses
// (inline validation included, via the shared performSave). The
// create→edit transition replaces the editor closure (orchestrator
// re-render), so the "now start OAuth" intent crosses instances through
// the module-scoped pendingAutoSignInId one-shot below: the re-mounted
// edit-mode wirePlanSignIn sees its provider id flagged and calls
// startFlow immediately.
//
// Nothing here polls and nothing carries data-field: state advances only
// on explicit user actions and endpoint responses, and the dirty
// machinery ([data-field] snapshot) never sees these inputs. After a
// successful /oauth/code the server has already persisted the tokens —
// the local provider reference is refreshed in place (Object.assign on
// the same object the orchestrator holds) WITHOUT touching the snapshot,
// so no unsaved-changes trap appears.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // One-shot handoff across the create→edit editor re-render: holds the id
  // of a provider just created by a sign-in-initiated auto-save. Consumed
  // (and cleared) by the next edit-mode wirePlanSignIn mount for that id.
  var pendingAutoSignInId = null;
  // providers-section.js's reset() clears the hand-off, so an abandoned
  // create-to-edit cannot fire a sign-in on a later mount (sortie 02, DD4).
  window.App.studio.clearProviderSignInHandoff = function () { pendingAutoSignInId = null; };

  function wirePlanSignIn(h, container, provider, requestCreateSave) {
    var isEdit = !!provider;

    // Local sub-state: non-null while the consent (URL + code paste) UI is
    // shown. Cleared on success/reset; survives nothing (an editor reload
    // mid-flow is fine — the backend keeps the pending verifier and a
    // re-click of Sign in replaces it cleanly).
    var awaitingUrl = null;

    function isConnected() {
      return !!(isEdit && provider && provider.oauth_active);
    }

    function showError(msg) {
      h.planErrBanner.set(msg); h.planErrBanner.show();
    }

    function clearError() {
      h.planErrBanner.set(''); h.planErrBanner.hide();
    }

    function readErrorResponse(r, fallback) {
      // Extract the endpoint's actionable detail; throw as Error either way.
      return r.json().then(
        function (e) { throw new Error(e.detail || fallback); },
        function () { throw new Error(fallback); }
      );
    }

    function openConsentPopup(url) {
      // Mirrors the MCP server editor's consent-popup geometry. NOTE
      // (documented expectation): when invoked after the /oauth/start
      // fetch resolves, the user-gesture context is lost and popup
      // blockers will often reject this — that degradation is EXPECTED
      // and silent, because the copyable URL + the gesture-context "Open
      // sign-in page" button are first-class paths.
      var popupW = 600;
      var popupH = 700;
      var parentX = window.screenX !== undefined ? window.screenX : window.screenLeft;
      var parentY = window.screenY !== undefined ? window.screenY : window.screenTop;
      var parentW = window.outerWidth || window.innerWidth || screen.width;
      var parentH = window.outerHeight || window.innerHeight || screen.height;
      var features = (
        'width=' + popupW + ',height=' + popupH +
        ',left=' + Math.round(parentX + Math.max(0, (parentW - popupW) / 2)) +
        ',top=' + Math.round(parentY + Math.max(0, (parentH - popupH) / 2))
      );
      try {
        window.open(url, 'plan-oauth-consent', features);
      } catch (e) { /* popup blocked — copyable URL is the visible path */ }
    }

    function startFlow(initiatingBtn) {
      clearError();
      if (initiatingBtn) initiatingBtn.disabled = true;
      fetch('/api/providers/' + encodeURIComponent(provider.id) + '/oauth/start', { method: 'POST' })
        .then(function (r) {
          if (!r.ok) return readErrorResponse(r, 'Could not start sign-in.');
          return r.json();
        })
        .then(function (data) {
          awaitingUrl = data.authorize_url;
          renderState();
          // Attempt the popup AFTER the consent UI is on screen so a
          // blocked popup leaves a complete fallback path visible.
          openConsentPopup(awaitingUrl);
        })
        .catch(function (err) {
          if (initiatingBtn) initiatingBtn.disabled = false;
          showError(err.message || String(err));
        });
    }

    function submitCode(codeInput, submitBtn) {
      clearError();
      var code = (codeInput.value || '').trim();
      if (!code) {
        showError('Paste the sign-in code first.');
        return;
      }
      submitBtn.disabled = true;
      fetch('/api/providers/' + encodeURIComponent(provider.id) + '/oauth/code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code })
      })
        .then(function (r) {
          if (!r.ok) return readErrorResponse(r, 'Sign-in code exchange failed.');
          return r.json();
        })
        .then(function (updated) {
          App.store.invalidate('providers');
          // Tokens are persisted server-side; refresh the local provider
          // reference in place (same object the orchestrator holds) and
          // DO NOT touch the form snapshot — no unsaved-changes trap.
          Object.assign(provider, updated);
          awaitingUrl = null;
          renderState();
          App.ui.flash('Signed in to Anthropic');
        })
        .catch(function (err) {
          // Inline (not a vanishing toast); the paste field stays usable.
          submitBtn.disabled = false;
          showError(err.message || String(err));
        });
    }

    function doReset(btn, revertFn) {
      fetch('/api/providers/' + encodeURIComponent(provider.id) + '/oauth', { method: 'DELETE' })
        .then(function (r) {
          if (!r.ok) return readErrorResponse(r, 'Reset failed.');
          return r.json();
        })
        .then(function (updated) {
          App.store.invalidate('providers');
          Object.assign(provider, updated);
          awaitingUrl = null;
          renderState();
          App.ui.flash('Connection reset');
        })
        .catch(function (err) {
          revertFn();
          showError(err.message || String(err));
        });
    }

    function buildSignedOutBlock() {
      var util = App.ui.util;
      var signInBtn = App.ui.button({ label: 'Sign in with Anthropic', testid: 'plan-signin-btn' });
      var block = util.el('div', { className: 'plan-signin-start' }, [
        util.el('p', {
          className: 'plan-signin-desc',
          text: 'Sign in with your Anthropic account to use your Claude plan. No API key is needed.'
        }),
        util.el('div', { className: 'plan-signin-actions' }, [signInBtn])
      ]);
      if (!isEdit) {
        // Auto-save-then-start (HAT fix): run the shared create path first
        // (the row must exist for /oauth/start). Validation failure renders
        // the editor's normal inline error and nothing is saved; save
        // failure renders the existing save-error handling and the flow is
        // NOT entered. On success the create→edit re-render consumes
        // pendingAutoSignInId and starts the OAuth flow (see module note).
        signInBtn.addEventListener('click', function () {
          clearError();
          if (requestCreateSave) {
            requestCreateSave(function (created) {
              pendingAutoSignInId = created.id;
            });
          }
        });
      } else {
        signInBtn.addEventListener('click', function () { startFlow(signInBtn); });
      }
      return { el: block, signInBtn: signInBtn };
    }

    function buildConnectedRow() {
      var util = App.ui.util;
      var status = App.ui.status({ testid: 'plan-connected-indicator' });
      status.set('success', 'Connected to Anthropic');
      var reauthBtn = App.ui.button({ label: 'Re-authenticate', testid: 'plan-reauth-btn' });
      reauthBtn.addEventListener('click', function () { startFlow(reauthBtn); });
      var resetBtn = App.ui.button({ testid: 'plan-reset-btn' });
      resetBtn.appendChild(util.el('span', { 'data-confirm-title': '', text: 'Reset connection' }));
      resetBtn.addEventListener('click', function () {
        // Two-step inline confirm (the library's armed style; the MCP reset-
        // connection precedent). Existing tokens are cleared locally only; no
        // upstream revocation. A state re-render replaces an armed button (it
        // returns to "Reset connection"), as before.
        App.ui.confirm(resetBtn, doReset, { confirmLabel: 'Confirm reset?' });
      });
      return util.el('div', { className: 'plan-connected-row' }, [status.el, reauthBtn, resetBtn]);
    }

    function buildConsentBlock(url) {
      var util = App.ui.util;
      // The library consent link supplies the read-only URL, the Open anchor
      // (a real link, target=_blank) and the Copy button with its "Copied" /
      // "Link copied" feedback. The URL is the only sensitive-looking value and
      // it is public authorize-endpoint text; the code below is never written to
      // an attribute.
      var link = App.ui.consentLink(url, {
        surface: 'chat',
        help: false,
        urlTestid: 'plan-signin-url',
        openTestid: 'plan-signin-open-btn',
        copyTestid: 'plan-signin-copy-btn'
      });
      var codeInput = App.ui.textInput({
        placeholder: 'Paste the code here', autocomplete: 'off', testid: 'plan-code-input'
      });
      codeInput.setAttribute('aria-label', 'Sign-in code');
      var submitBtn = App.ui.button({ variant: 'primary', label: 'Confirm code', testid: 'plan-code-submit-btn' });
      submitBtn.addEventListener('click', function () { submitCode(codeInput, submitBtn); });
      return util.el('div', { className: 'plan-signin-consent', 'data-testid': 'plan-signin-consent' }, [
        util.el('p', {
          className: 'plan-signin-desc',
          text: 'Approve access in the sign-in window — if none opened, open or copy the link below in any browser. Then paste the code shown after approval.'
        }),
        link,
        util.el('div', { className: 'plan-code-row' }, [codeInput, submitBtn])
      ]);
    }

    function renderState() {
      var nodes = [];
      var signedOut = null;
      if (isConnected()) nodes.push(buildConnectedRow());
      if (awaitingUrl) {
        // Re-authenticate renders the consent flow OVER the connected
        // state — existing tokens survive until the new exchange succeeds.
        nodes.push(buildConsentBlock(awaitingUrl));
      } else if (!isConnected()) {
        signedOut = buildSignedOutBlock();
        nodes.push(signedOut.el);
      }
      h.planState.replaceChildren.apply(h.planState, nodes);
      return signedOut;
    }

    var initial = renderState();

    // Consume the create→edit auto-start handoff (HAT fix): this edit-mode
    // mount is the re-render that immediately follows a sign-in-initiated
    // create — start the OAuth flow now. One-shot: cleared before starting.
    // A just-created provider is never connected, so the signed-out block
    // (and its sign-in button) is on screen when this fires.
    if (isEdit && provider && pendingAutoSignInId === provider.id) {
      pendingAutoSignInId = null;
      startFlow(initial && initial.signInBtn);
    }
  }

  window.App.studio.wirePlanSignIn = wirePlanSignIn;
})();
