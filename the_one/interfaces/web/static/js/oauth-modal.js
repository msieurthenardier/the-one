// App.oauthModal — OAuth Login modal (F5 leg 05).
//
// Mirrors the App.confirmDialog (dialog.js) pattern: focus-trap +
// Escape-to-close + Tab-cycling + restore-focus-on-close.
//
// API:
//   App.oauthModal.open({source_id, chat_session_id, tool_call_id,
//                        resource_metadata_url, consent_url})
//     - Opens the modal in "Connect" mode. If consent_url is present,
//       Connect-click opens the consent URL in a new tab. Otherwise it
//       POSTs /api/oauth/start to drive the SDK auth flow → a SECOND
//       auth_required event with the real consent_url arrives via
//       WebSocket; chat.js routes it back through this modal's open()
//       which sees the consent_url and opens the new tab.
//
//   App.oauthModal.close()
//     - Closes the modal and restores focus to the original trigger.
//
// DOM (mirrors confirmDialog's class set):
//   <div class="modal-overlay oauth-modal-overlay" role="dialog" aria-modal="true"
//        aria-labelledby="oauth-modal-title-...">
//     <div class="modal-dialog">
//       <h2 class="modal-dialog-title" id="oauth-modal-title-...">
//         Login required for {source_id}
//       </h2>
//       <p class="modal-dialog-message">
//         Connect to authenticate. The OAuth provider will open in a new browser tab.
//       </p>
//       <button class="btn-filled-cyan" data-testid="oauth-modal-connect-btn">
//         Connect
//       </button>
//       <button class="btn-outlined-cyan" data-testid="oauth-modal-close-btn">
//         Close
//       </button>
//     </div>
//   </div>
//
// Singleton: a module-level `openModalRef` ensures only one OAuth modal
// is open at a time. Re-opening with new data reroutes the existing
// modal (e.g. consent_url-bearing second open after Connect click);
// chat.js's routing relies on this for the lazy-path UX.
(function (window, document) {
  'use strict';
  window.App = window.App || {};

  var openModalRef = null;
  var openState = null;  // { source_id, chat_session_id, tool_call_id, ... }

  function open(opts) {
    opts = opts || {};
    // If a modal is already open AND a consent_url is now available,
    // route the consent open instead of constructing a fresh modal.
    if (openModalRef && opts.consent_url) {
      try { window.open(opts.consent_url, '_blank', 'noopener,noreferrer'); } catch (e) { /* ignore */ }
      return;
    }
    if (openModalRef) {
      // Already open — second open() call is a no-op so the user's in-
      // progress interaction (e.g. mid-typing manual entry) is not blown
      // away by an idempotent reconnect-snapshot replay.
      return;
    }
    openState = opts;
    buildAndAttach(opts);
  }

  function close() {
    if (!openModalRef) return;
    openModalRef.close();
  }

  function buildAndAttach(opts) {
    var trigger = document.activeElement;

    var stamp = String(Date.now()) + '-' + Math.floor(Math.random() * 100000);
    var titleId = 'oauth-modal-title-' + stamp;

    var overlay = document.createElement('div');
    overlay.className = 'modal-overlay oauth-modal-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', titleId);
    overlay.setAttribute('data-testid', 'oauth-modal-overlay');

    var dlg = document.createElement('div');
    dlg.className = 'modal-dialog';
    overlay.appendChild(dlg);

    var titleEl = document.createElement('h2');
    titleEl.className = 'modal-dialog-title';
    titleEl.id = titleId;
    titleEl.textContent = 'Login required for ' + (opts.source_id || '<unknown>');
    dlg.appendChild(titleEl);

    var msgEl = document.createElement('p');
    msgEl.className = 'modal-dialog-message';
    // WCAG 4.1.3 (Status Messages): error text written into msgEl via the
    // fetch-failure paths below must be announced to screen readers.
    msgEl.setAttribute('aria-live', 'assertive');
    msgEl.setAttribute('aria-atomic', 'true');
    msgEl.textContent = 'Connect to authenticate. The OAuth provider will open in a new browser tab.';
    dlg.appendChild(msgEl);

    var connectBtn = document.createElement('button');
    connectBtn.type = 'button';
    connectBtn.className = 'btn-filled-cyan';
    connectBtn.textContent = 'Connect';
    connectBtn.setAttribute('data-testid', 'oauth-modal-connect-btn');
    dlg.appendChild(connectBtn);

    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-outlined-cyan';
    closeBtn.textContent = 'Close';
    closeBtn.setAttribute('data-testid', 'oauth-modal-close-btn');
    dlg.appendChild(closeBtn);

    function doClose() {
      document.removeEventListener('keydown', onKey, true);
      overlay.removeEventListener('click', onOverlayClick);
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      openModalRef = null;
      openState = null;
      if (trigger && typeof trigger.focus === 'function') {
        try { trigger.focus(); } catch (e) { /* ignore */ }
      }
    }

    closeBtn.addEventListener('click', doClose);

    connectBtn.addEventListener('click', function () {
      if (openState && openState.consent_url) {
        try { window.open(openState.consent_url, '_blank', 'noopener,noreferrer'); } catch (e) { /* ignore */ }
        return;
      }
      // POST /api/oauth/start to kick off the SDK flow. The server
      // schedules a background task that drives the auth_flow → the
      // SDK's redirect_handler broadcasts a SECOND auth_required event
      // with the real consent_url; chat.js routes it back here.
      var body = {
        source_id: openState && openState.source_id,
        chat_session_id: openState && openState.chat_session_id,
        tool_call_id: openState && openState.tool_call_id,
        resource_metadata_url: openState && openState.resource_metadata_url,
      };
      fetch('/api/oauth/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }).then(function (r) {
        if (!r.ok) {
          return r.json().then(function (err) {
            var detail = (err && err.detail) || 'OAuth start failed';
            msgEl.textContent = detail;
          });
        }
      }).catch(function (e) {
        msgEl.textContent = 'Network error: ' + (e && e.message ? e.message : e);
      });
    });

    function focusables() {
      var sel = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
      var nodes = dlg.querySelectorAll(sel);
      var arr = Array.prototype.slice.call(nodes);
      return arr.filter(function (n) {
        return !n.disabled && n.offsetParent !== null;
      });
    }

    function onKey(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        doClose();
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

    function onOverlayClick(e) {
      // Click on overlay (NOT a descendant) is a no-op (matches confirmDialog).
      if (e.target === overlay) {
        e.preventDefault();
        e.stopPropagation();
      }
    }

    document.addEventListener('keydown', onKey, true);
    overlay.addEventListener('click', onOverlayClick);

    openModalRef = { close: doClose };
    document.body.appendChild(overlay);

    connectBtn.focus();
  }

  window.App.oauthModal = {
    open: open,
    close: close,
  };
})(window, document);
