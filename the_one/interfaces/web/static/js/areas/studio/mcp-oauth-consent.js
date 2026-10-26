// App.studio.mcpEditor.oauthConsent — the MCP source editor's OAuth sign-in
// popup (M31 F5 L02, split out of mcp-server-editor.js's handleTestConnection,
// moved verbatim).
//
// Holds: launchConsentPopup({consentUrl, statusEl, sourceId, settle, rerun}) and
// what it owns: the status sub-nodes (text, retry, link block), the consent
// link, the popup, the `message` listener, the token poll and renderRetryUi.
// `rerun` re-runs the connection test on success, so this module never calls
// back into connectionStatus.
// launchConsentPopup registers its session with the mount (args.mount) and
// returns {cancel, isDone}; cancel stops the poll without closing the popup
// (M31 F5 L03).
// Exposes: launchConsentPopup.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  // F9 L1 (vibing follow-up) + F4 L3 popup-loop fix: popup-launch +
  // close-watcher extracted so both the auto-popup branch (manual
  // click) and the explicit "Sign in" consent-button branch (auto-run
  // after create) share one implementation. `consentUrl` is the
  // auth_required response's URL.
  //
  // Close-watcher contract (F4 L3 — fix the Cloudflare-class popup
  // loop): the backend's /api/oauth/callback page posts a result
  // message to `window.opener` BEFORE closing. The watcher branches
  // on the received result rather than blindly re-POSTing /test/connect:
  //   - 'success' → defensive re-POST with noAutoPopup=true. Phase A
  //     should now succeed; if the token-exchange race wins we'd loop
  //     forever without noAutoPopup, so we set it as a guard.
  //   - 'failed' / 'expired' → render error + "Sign in" retry button.
  //     The IdP's error_description is surfaced so the operator can
  //     diagnose. NO re-POST.
  //   - no message received (the postMessage was blocked, or the user
  //     never finished) → keep polling for the token to CONSENT_WAIT_MS,
  //     then render "Sign-in timed out" + retry button. NO re-POST.
  // One text for the Test button's hold, the first status text and the popup-closed
  // text (A19): the operator is waiting for the same thing in all three.
  var WAITING_TEXT = 'Waiting for sign-in\u2026';

  function launchConsentPopup(args) {
    // The free variables of the old closure inside handleTestConnection, passed
    // in explicitly: the status panel, the source id, the caller's `settle`, and
    // `rerun`, a closure over the caller's own arguments that re-runs Phase A (so
    // this module never names connectionStatus).
    var consentUrl = args.consentUrl;
    var statusEl = args.statusEl;
    var sourceId = args.sourceId;
    var settle = args.settle;
    var rerun = args.rerun;
    // The mount owns the one live session (mcp-editor-lifecycle.js): launching
    // cancels the previous one and disables Test until this one ends (defect 8).
    var mount = args.mount;
    var handle = { cancel: cancel, isDone: function () { return state === 'DONE'; } };
    if (!mount.alive()) return handle;
    mount.setSession(handle);

    // Sortie 04 DD1/DD2: the status panel (testid mcp-test-status, kept on the
    // outer element) gets a status-text child, a retry area and the sign-in
    // link block, so the text updates below never wipe the link. A fresh
    // launch (including the retry "Sign in") rebuilds all three.
    var focusWasInStatus = !!(document.activeElement &&
      statusEl.contains(document.activeElement));
    statusEl.replaceChildren();
    var textEl = document.createElement('span');
    textEl.className = 'mcp-consent-status-text';
    textEl.setAttribute('role', 'status');
    var retryEl = document.createElement('span');
    retryEl.className = 'mcp-consent-retry';
    retryEl.setAttribute('role', 'status');
    var blockEl = document.createElement('div');
    blockEl.className = 'mcp-consent-block';
    statusEl.appendChild(textEl);
    statusEl.appendChild(retryEl);
    statusEl.appendChild(blockEl);
    blockEl.appendChild(App.ui.consentLink.build(consentUrl, {
      surface: 'mcp',
      sourceName: (document.getElementById('mf-name') || {}).value || '',
    }));
    if (focusWasInStatus) {
      var landing = App.ui.consentLink.focusTarget(blockEl);
      if (landing) landing.focus();
    }

    var popupW = 600;
    var popupH = 700;
    var parentX = window.screenX !== undefined ? window.screenX : window.screenLeft;
    var parentY = window.screenY !== undefined ? window.screenY : window.screenTop;
    var parentW = window.outerWidth || window.innerWidth || screen.width;
    var parentH = window.outerHeight || window.innerHeight || screen.height;
    var popupLeft = parentX + Math.max(0, (parentW - popupW) / 2);
    var popupTop = parentY + Math.max(0, (parentH - popupH) / 2);
    var features = (
      'width=' + popupW + ',height=' + popupH +
      ',left=' + Math.round(popupLeft) +
      ',top=' + Math.round(popupTop)
    );
    // A null from window.open is NOT a failure: the desktop webview always
    // returns null (it hands the URL to the system browser), and a real
    // popup blocker leaves the link block as the way in. Either way keep
    // waiting for the token. Every use of the handle below is null-guarded.
    var popup = App.ui.consentLink.isSafeUrl(consentUrl)
      ? window.open(consentUrl, 'mcp-oauth-consent', features) : null;
    function popupClosed() {
      try { return !!popup && popup.closed; } catch (e) { return false; }
    }
    function closePopup() {
      try { if (popup && !popup.closed) popup.close(); } catch (e) { /* */ }
    }
    // F4 L3 — postMessage-independent polling. Earlier iterations
    // gated polling on a `success` postMessage from /oauth/callback,
    // but Cloudflare's OAuth page sets COOP (or similar) which severs
    // `window.opener` across the cross-origin navigation chain. By
    // the time the popup is back on loopback, opener is null and the
    // postMessage silently no-ops — polling never starts, popup
    // closes, UI shows "did not complete" even though OAuth succeeded.
    //
    // Decoupled design: poll `GET /api/mcp-sources/{id}` for
    // `has_access_token: true` from the moment the block shows. Polling
    // is the source of truth for success, whether or not a popup exists
    // or closes (sortie 04: a user can finish through the link after
    // closing the popup). postMessage demotes to a fast-fail signal
    // for failed/expired (short-circuits the wait to give the
    // operator the IdP's error text immediately).
    //
    // States:
    //   POLLING — checking for tokens, up to CONSENT_WAIT_MS.
    //   DONE    — final action taken (re-POST or retry-UI). Idempotent.
    var state = 'POLLING';
    var pollTimer = null;
    var textTimer = null;
    var pollAttempts = 0;
    // Overall consent-wait ceiling: 2 minutes, long enough for a real
    // sign-in (IdP login, MFA, consent screen). The server-side pending
    // flow lives 10 minutes (_TTL_SECONDS), so this stays inside it.
    var CONSENT_WAIT_MS = 120000;
    var POLL_INTERVAL_MS = 500;
    var maxPollAttempts = CONSENT_WAIT_MS / POLL_INTERVAL_MS; // 240

    function cleanup() {
      if (pollTimer) clearInterval(pollTimer);
      if (textTimer) clearTimeout(textTimer);
      window.removeEventListener('message', onOAuthMessage);
    }

    // Idempotent. Stops the poll, the listener and the delayed first status write,
    // and never calls rerun, settle or a finalize writer. It does not close the
    // popup: a sign-in the operator is finishing in the browser still lands on
    // the server.
    function cancel() {
      if (state === 'DONE') return;
      state = 'DONE';
      cleanup();
      mount.endSession(handle);
    }

    function finalize(action) {
      if (state === 'DONE') return;
      state = 'DONE';
      cleanup();
      mount.endSession(handle);
      action();
    }

    function renderRetryUi(headerText) {
      // The link's URL is dead once the flow failed/expired/timed out.
      var focusWasInBlock = blockEl.contains(document.activeElement);
      blockEl.replaceChildren();
      textEl.textContent = '';
      retryEl.replaceChildren();
      var msg = document.createElement('span');
      msg.className = 'mcp-tools-error';
      msg.textContent = headerText + ' ';
      retryEl.appendChild(msg);
      var retryBtn = App.ui.button({
        label: 'Sign in', testid: 'mcp-consent-btn',
        onClick: function () { launchConsentPopup(args); }
      });
      retryEl.appendChild(retryBtn);
      if (focusWasInBlock) retryBtn.focus();
    }

    function onOAuthMessage(evt) {
      if (state === 'DONE') return;
      if (evt.origin !== window.location.origin) return;
      var d = evt.data;
      if (!d || typeof d !== 'object') return;
      if (d.type !== 'mcp-oauth-result') return;
      // success status is informational only — polling owns that
      // transition. failed/expired short-circuit to retry so the
      // operator sees the IdP's error without waiting out the poll.
      if (d.status === 'failed') {
        var failMsg = d.description || d.error || 'sign-in failed';
        finalize(function () {
          closePopup();
          renderRetryUi('✗ Sign-in failed: ' + failMsg + '.');
          settle();
        });
      } else if (d.status === 'expired') {
        finalize(function () {
          closePopup();
          renderRetryUi('✗ Sign-in window expired.');
          settle();
        });
      }
    }
    window.addEventListener('message', onOAuthMessage);

    // The live region (textEl) is in the DOM empty; its first text goes in on
    // the next tick so assistive tech sees the change rather than a new node.
    textTimer = setTimeout(function () {
      if (state === 'POLLING' && !textEl.textContent) textEl.textContent = WAITING_TEXT;
    }, 0);

    pollTimer = setInterval(function () {
      if (state === 'DONE') return;

      // A popup that closed while we still wait only changes the wording:
      // the token can still land through the link.
      if (popupClosed()) textEl.textContent = WAITING_TEXT;

      pollAttempts++;

      fetch('/api/mcp-sources/' + encodeURIComponent(sourceId))
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (src) {
          if (state === 'DONE') return;
          if (src && src.has_access_token === true) {
            finalize(function () {
              closePopup();
              // Phase A re-POST (it rewrites the whole panel, so the link
              // block goes with it). noAutoPopup defensive — if something
              // weird leaves Phase A still failing, retry UI surfaces
              // instead of looping.
              rerun();
            });
            return;
          }
          if (pollAttempts >= maxPollAttempts) {
            finalize(function () {
              renderRetryUi('Sign-in timed out — tokens did not persist within '
                + (CONSENT_WAIT_MS / 1000) + 's.');
              settle();
            });
          }
        })
        .catch(function () { /* transient fetch error; next tick retries */ });
    }, POLL_INTERVAL_MS);
    return handle;
  }

  window.App.studio.mcpEditor.oauthConsent = {
    launchConsentPopup: launchConsentPopup
  };
})();
