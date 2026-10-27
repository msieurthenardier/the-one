// App.chat.signIn -- the in-chat MCP sign-in: the consent popups, the per-(session, source)
// login flows, the "Log in" group and its link block, and the auth_required / auth_resolved /
// auth_failed handlers (M31 F6 L02, split out of areas/chat.js, moved verbatim apart from the
// ctx./state. prefixes).
//
// settleClose is the popup close that runs above the socket's frame gate (any session's
// settle closes its own popup); the three on* handlers run behind the gate.
// Exposes: clearLoginRequiredButton, renderLoginRequiredButton, settleClose, onAuthRequired,
// onAuthResolved, onAuthFailed.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function create(ctx) {
    var chatState = ctx.chatState;
    var messagesEl = ctx.messagesEl;
    var inputEl = ctx.inputEl;

    // F5 L5: Login-required inline button helpers.
    //
    // Idempotent: clearLoginRequiredButton removes any stale buttons for the
    // same source_id BEFORE renderLoginRequiredButton appends a new one. This
    // keeps the L3 reconnect-snapshot replay from creating duplicate buttons
    // (the cached auth_required event is re-broadcast on every WS reconnect
    // when the agent has a pending pause).
    function clearLoginRequiredButton(data) {
      var sid = data && data.source_id ? data.source_id : null;
      var sel = sid
        ? '.login-required-btn[data-source-id="' + ctx.transcript.cssEscape(sid) + '"]'
        : '.login-required-btn';
      var existing = messagesEl.querySelectorAll(sel);
      for (var i = 0; i < existing.length; i++) {
        var btn = existing[i];
        // L05: prefer removing the wrapper when present (post-L05 DOM);
        // fall back to the bare button (legacy / pre-L05 / test-synthesized).
        var group = btn.closest('.login-required-group');
        var toRemove = group || btn;
        var parent = toRemove.parentNode;
        if (parent) parent.removeChild(toRemove);
      }
    }

    // Track per-source consent popups so the WS-delivered consent_url
    // (which arrives AFTER /api/oauth/start) can navigate the popup that
    // was opened during the user's click gesture. Opening the popup at
    // click time (with about:blank as placeholder) preserves the
    // user-gesture chain — browsers will block window.open() called
    // later from inside a WS event handler.
    var oauthPopups = Object.create(null);
    // Preserve source_name across re-renders. The SECOND auth_required
    // event (broadcast by the SDK's redirect_handler) carries the real
    // consent_url but historically lacked source_name; the backend now
    // includes it, but we keep this map as a defensive cache so a stale
    // event still renders the friendly name.
    var sourceNames = Object.create(null);

    function openConsentPopup(url, sourceId) {
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
      var name = 'mcp-oauth-consent-' + (sourceId || 'unknown');
      return window.open(url || 'about:blank', name, features);
    }

    // Sortie 04 DD2: per-(chat session, source) sign-in state. A consent_url
    // frame for a flow THIS client started (startedHere, set by its "Log in"
    // click) stores it; the login-required group then shows the link block
    // (App.consentLink) instead of the "Log in" button. Any other consent_url
    // is ignored. Replayed auth_required
    // frames carry consent_url=null (rebuilt from tool-result metadata), so the
    // map is what keeps the link across a reconnect and stops a second
    // /api/oauth/start. Cleared on auth_resolved / auth_failed.
    var loginFlows = Object.create(null);
    var LOGIN_KEY_SEP = '\u0000';

    function loginFlowKey(sourceId) {
      return (chatState.activeId() || '') + LOGIN_KEY_SEP + sourceId;
    }

    function clearLoginFlows(sourceId) {
      // Above the frame gate: a switched-away session's entry must still clear,
      // so match every session's key for this source.
      var suffix = LOGIN_KEY_SEP + sourceId;
      Object.keys(loginFlows).forEach(function (k) {
        if (k.slice(-suffix.length) === suffix) delete loginFlows[k];
      });
    }

    function startLoginFlow(data) {
      var sourceId = data.source_id;
      var key = loginFlowKey(sourceId);
      var known = loginFlows[key];
      // The consent URL is already known (idempotent re-emission): open it
      // again and do not POST /api/oauth/start a second time.
      // Only for a flow THIS client started: an in-band consent URL (or another
      // client's) is never stored, so every other click starts a fresh flow.
      if (known && known.startedHere && known.consentUrl) {
        if (App.consentLink.isSafeUrl(known.consentUrl)) {
          var again = openConsentPopup(known.consentUrl, sourceId);
          if (again) oauthPopups[sourceId] = again;
        }
        return;
      }
      // startedHere is set synchronously, BEFORE the fetch, so a consent frame
      // that beats the POST response finds the entry.
      loginFlows[key] = { consentUrl: null, startedHere: true, autoOpened: false };
      // A browser keeps the click-time about:blank pre-open (it preserves the
      // user gesture; navigated when the consent frame arrives). The desktop
      // webview skips it: window.open there hands the URL straight to the
      // system browser and always returns null, so an about:blank would open
      // the system browser on nothing.
      if (!(App.desktop && App.desktop.isWebview())) {
        var popup = openConsentPopup('about:blank', sourceId);
        if (popup) oauthPopups[sourceId] = popup;
      }
      function abandon() {
        delete loginFlows[key];
        closeOauthPopup(sourceId);
      }
      fetch('/api/oauth/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_id: sourceId,
          chat_session_id: chatState.activeId(),
          tool_call_id: data.tool_call_id,
          resource_metadata_url: data.resource_metadata_url,
        }),
      }).then(function (r) {
        if (r.ok) return;
        return r.json().then(function (err) {
          var detail = (err && err.detail) || 'OAuth start failed';
          ctx.transcript.addMsg('system', detail);
          abandon();
        });
      }).catch(function (e) {
        ctx.transcript.addMsg('system', 'Network error: ' + (e && e.message ? e.message : e));
        abandon();
      });
    }

    function resetLoginGroups(sourceId) {
      var groups = messagesEl.querySelectorAll(
        '.login-required-group[data-source-id="' + ctx.transcript.cssEscape(sourceId || '') + '"]'
      );
      for (var i = 0; i < groups.length; i++) {
        var link = groups[i].querySelector('.consent-link');
        var hadFocus = !!(link && link.contains(document.activeElement));
        if (link && link.parentNode) link.parentNode.removeChild(link);
        var btn = groups[i].querySelector('.login-required-btn');
        if (btn) btn.hidden = false;
        if (hadFocus && btn) btn.focus();
      }
    }

    function closeOauthPopup(sourceId) {
      var popup = oauthPopups[sourceId];
      if (!popup) return;
      try { if (!popup.closed) popup.close(); } catch (e) { /* ignore */ }
      delete oauthPopups[sourceId];
    }

    function renderLoginRequiredButton(data) {
      // Focus inside this source's current group would be lost when it is
      // replaced; remember it so the new link block can take it over.
      var active = document.activeElement;
      var focusWasInGroup = !!(active && active.closest && data.source_id &&
        active.closest('.login-required-group[data-source-id="' +
          ctx.transcript.cssEscape(data.source_id) + '"]'));
      // Drop any prior button for this source first (reconnect idempotency).
      clearLoginRequiredButton(data);
      if (data.source_id && data.source_name) {
        sourceNames[data.source_id] = data.source_name;
      }
      // L05: wrapper groups the attribution + button into one node (one
      // thing to find, replace and remove per auth_required event).
      var group = document.createElement('div');
      group.className = 'login-required-group';
      group.dataset.sourceId = data.source_id || '';

      var attr = document.createElement('div');
      attr.className = 'login-required-attribution';
      attr.textContent = 'Authorization required to continue.';
      group.appendChild(attr);

      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-filled-primary login-required-btn';
      btn.dataset.sourceId = data.source_id || '';
      btn.dataset.toolCallId = data.tool_call_id || '';
      btn.dataset.resourceMetadataUrl = data.resource_metadata_url || '';
      if (data.consent_url) btn.dataset.consentUrl = data.consent_url;
      var label = data.source_name
        || (data.source_id && sourceNames[data.source_id])
        || data.source_id
        || '<unknown>';
      btn.textContent = 'Log in to ' + label;
      btn.addEventListener('click', function () {
        startLoginFlow(data);
      });
      group.appendChild(btn);
      // Sortie 04 DD2: a known consent URL (this frame's, or kept from the
      // flow's earlier frame when this one is a replay with consent_url=null)
      // shows the link block; the "Log in" button stays in the DOM, hidden, so
      // the group is still found by its button on the next replay and
      // un-hides if the flow fails.
      var flow = data.source_id ? loginFlows[loginFlowKey(data.source_id)] : null;
      var linkBlock = null;
      if (flow && flow.consentUrl) {
        btn.hidden = true;
        linkBlock = App.consentLink.build(flow.consentUrl, {
          surface: 'chat', sourceName: label,
        });
        group.appendChild(linkBlock);
      }
      // Sortie 04 (operator HAT decision): the sign-in control must not hide
      // in a collapsed panel. The "Tool activity" trace is a collapsible
      // disclosure, so the group goes in .messages as the NEXT SIBLING of this
      // turn's trace shell (reads right after that turn's tool activity),
      // never inside it (and so never counted by the trace's item count).
      // The shell is only looked up, never created, here. With no
      // parent_message_id, or no shell for it, append to .messages instead
      // (legacy/null cases, e.g. synthetic auth_required events in tests).
      var authShell = data.parent_message_id
        ? (ctx.transcript.traceShellFor(data.parent_message_id) || messagesEl.querySelector(
            '.trace-shell[data-parent-msg-id="' + ctx.transcript.cssEscape(data.parent_message_id) + '"]'))
        : null;
      if (authShell && authShell.parentNode === messagesEl) {
        messagesEl.insertBefore(group, authShell.nextSibling);
      } else {
        messagesEl.appendChild(group);
      }
      if (focusWasInGroup && linkBlock) {
        var target = App.consentLink.focusTarget(linkBlock);
        if (target) target.focus();
      }
      ctx.transcript.scrollToBottomIfPinned();
    }

    function renderResumingPlaceholder(data) {
      // Lightweight system message indicating the resumed tool call is
      // re-running. The eventual tool_result event renders normally; this
      // placeholder is purely cosmetic so the chat doesn't go silent
      // between auth_resolved and the resumed tool_result arrival.
      ctx.transcript.addMsg('system', 'Resuming…');
    }

    // Above the frame gate: the popup close and the login-flow cleanup for a settled flow.
    function settleClose(data) {
      closeOauthPopup(data.source_id);
      clearLoginFlows(data.source_id);
    }

    // The auth_required frame (moved from the gated frame chain, turn-frames.js).
    function onAuthRequired(data) {
      ctx.transcript.hideThinking();
      ctx.transcript.finalizeStreamingBubble();
      ctx.transcript.clearStreamingVisibility();
      var flowKey = data.source_id ? loginFlowKey(data.source_id) : null;
      var flow = flowKey ? loginFlows[flowKey] : null;
      // Sortie 04 DD2 amendment: store a consent URL only for a flow this
      // client started (its own "Log in" click). An in-band frame (the SDK's
      // own flow, killed by the connect timeout) or another client's flow is
      // ignored: the normal "Log in" group renders and a click starts fresh.
      var ownFlow = !!(flow && flow.startedHere);
      if (data.consent_url && flowKey && ownFlow) {
        flow.consentUrl = data.consent_url;
      }
      var popupHeld = false;
      var consentSafe = App.consentLink.isSafeUrl(data.consent_url);
      if (data.consent_url && ownFlow && oauthPopups[data.source_id]) {
        var p = oauthPopups[data.source_id];
        if (!consentSafe) {
          // Never navigate the pre-opened popup to a non-web address.
          closeOauthPopup(data.source_id);
        } else {
          try {
            if (!p.closed) {
              popupHeld = true;
              p.location.href = data.consent_url;
              p.focus();
            }
          } catch (e) { /* cross-origin or closed; ignore */ }
        }
      }
      renderLoginRequiredButton(data);
      // One best-effort open of the consent page, only for the flow started
      // from this page's click, only when no popup is held and not yet tried.
      // The desktop webview hands this to the system browser (it may be
      // swallowed without a user gesture; the link block is the fallback).
      if (consentSafe && ownFlow && !popupHeld && !flow.autoOpened) {
        flow.autoOpened = true;
        try { window.open(data.consent_url, '_blank'); } catch (e) { /* link block remains */ }
      }
    }

    function onAuthResolved(data) {
      var ar = document.activeElement;
      var arLost = !!(ar && ar.closest && ar.closest('.login-required-group'));
      clearLoginRequiredButton(data);
      renderResumingPlaceholder(data);
      if (arLost && !inputEl.disabled) inputEl.focus();
    }

    function onAuthFailed(data) {
      var failMsg = 'OAuth failed: ' + (data.description || data.error || 'unknown error');
      ctx.transcript.addMsg('system', failMsg);
      // The consent URL is dead: drop the link block and offer "Log in" again.
      resetLoginGroups(data.source_id);
    }

    return {
      clearLoginRequiredButton: clearLoginRequiredButton,
      renderLoginRequiredButton: renderLoginRequiredButton,
      settleClose: settleClose,
      onAuthRequired: onAuthRequired,
      onAuthResolved: onAuthResolved,
      onAuthFailed: onAuthFailed
    };
  }

  window.App.chat.signIn = { create: create };
})();
