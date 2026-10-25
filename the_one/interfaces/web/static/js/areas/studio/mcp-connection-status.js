// App.studio.mcpEditor.connectionStatus — the MCP source editor's connection
// row and Test connection flow (M31 F5 L02, split out of mcp-server-editor.js,
// moved verbatim).
//
// Holds: renderConnectionActions (the Refresh, Reset, LED and "Last updated"
// markup), wireResetButton and syncResetButtonVisibility (the Reset connection
// button), and handleTestConnection (POST /test/connect, the tools list and the
// error panel). The sign-in popup is in mcp-oauth-consent.js, called through
// its namespace at call time. wireResetButton re-mounts through
// App.studio.renderMcpSourceEditor, also read at call time.
// Exposes: renderConnectionActions, wireResetButton, syncResetButtonVisibility,
// handleTestConnection.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  var hasOAuthState = window.App.studio.mcpEditor.shared.hasOAuthState;
  var formatTimeAgo = window.App.studio.mcpEditor.shared.formatTimeAgo;
  var renderToolsListHtml = window.App.studio.mcpEditor.serverInfo.renderToolsListHtml;

  // The connection-actions row (Refresh, Reset, LED, Last updated) for an
  // existing stdio or streamable-http source; '' otherwise.
  function renderConnectionActions(source) {
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !source;
    var html = '';
    if (!isCreate && source && (source.type === 'streamable-http' || source.type === 'stdio')) {
      // De-guttered (HAT): dropped the empty label-slot + `.field-row` wrapper
      // so the actions left-align with the stacked fields.
      html += '<div class="mcp-test-row">';
      html += '<div class="mcp-connection-actions">';
      html += '<button type="button" class="btn-outlined-primary mcp-refresh-connection-btn" data-testid="mcp-test-connection">' +
              window.App.icon('refresh-cw') + ' Refresh connection</button>';
      if (hasOAuthState(source)) {
        var resetTooltip = 'Reset this connection? This clears the stored login and tools list. ' +
          'You will need to log in again on the next refresh.';
        html += '<button type="button" class="btn-outlined-primary mcp-reset-connection-btn" data-testid="reset-mcp-connection-btn" title="' + escapeAttr(resetTooltip) + '" aria-label="' + escapeAttr(resetTooltip) + '" data-name="' + escapeAttr(source.name || '') + '"><span data-confirm-title>Reset connection</span></button>';
      }
      var connCache = (source.config && source.config._cache) || null;
      // F4 L7 (M08): LED moved from the Tools-status banner up to the
      // connection-actions row so it sits adjacent to the Refresh button
      // that drives its state. Computed from cache shape (mirrors the
      // success-when-tools-present heuristic the banner uses below).
      var connLedState = (connCache && Array.isArray(connCache.tools)) ? 'success' : 'idle';
      var connLedLabel = (connLedState === 'success') ? 'Connected' : 'Not connected';
      html += '<span class="indicator-led indicator-led--' + connLedState +
              '" data-testid="mcp-connection-led" data-state="' + connLedState +
              '" aria-label="' + connLedLabel + '"></span>';
      var connLastUpdatedText = connCache ? formatTimeAgo(connCache.last_updated) : '';
      var connLastUpdatedHidden = connLastUpdatedText ? '' : ' hidden';
      html += '<div class="mcp-tools-last-updated" data-testid="mcp-tools-last-updated"' +
              connLastUpdatedHidden + '>' +
              (connLastUpdatedText ? 'Last updated: ' + escapeHtml(connLastUpdatedText) : '') +
              '</div>';
      html += '</div>';
      html += '</div>';
    }
    return html;
  }

  // Read at call time: the controller loads after this module.
  function renderMcpSourceEditor(container, source, mcpTypes, callbacks) {
    return window.App.studio.renderMcpSourceEditor(container, source, mcpTypes, callbacks);
  }

  // F9 L1 (vibing follow-up): wire the Reset connection button's click
  // handler. Extracted from inline wireEditorEvents so it can also fire
  // after dynamic injection (post-OAuth-grant), where the original
  // wireEditorEvents pass already ran without finding the button in the
  // DOM. Idempotent: skips wiring if a marker dataset is already set on
  // the button (re-runs from syncResetButtonVisibility are no-ops on
  // already-wired buttons).
  function wireResetButton(container, source, mcpTypes, callbacks, mount) {
    var resetBtn = container.querySelector('[data-testid="reset-mcp-connection-btn"]');
    if (!resetBtn) return;
    if (resetBtn.dataset.resetWired === '1') return;
    resetBtn.dataset.resetWired = '1';
    function doReset(btn, revertFn) {
      fetch('/api/mcp-sources/' + encodeURIComponent(source.id) + '/connection', { method: 'DELETE' })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (e) { throw new Error((e && e.detail) || 'Reset failed'); });
          // The reset drops config._cache (the list's tool count) server-side.
          App.store.invalidate('mcp-sources');
          App.store.invalidate('agents');
          if (callbacks.onListStale) callbacks.onListStale();
          return fetch('/api/mcp-sources/' + encodeURIComponent(source.id));
        })
        .then(function (r) {
          if (!r || !r.ok) throw new Error('Failed to refetch source after reset');
          return r.json();
        })
        .then(function (refreshed) {
          // The mount died during the refetch (the server change already
          // invalidated the list above): nothing is mounted.
          if (!mount.alive()) return;
          // Re-render from the refreshed source: destroy this mount, mount the
          // new one (its onMounted hands the glue the new controller), then
          // focus and flash. The Tools section collapses to empty-state, the
          // Reset button hides itself, and the editor is clean again.
          var tok = App.focusAfter.begin(resetBtn);
          mount.destroy();
          renderMcpSourceEditor(container, refreshed, mcpTypes, callbacks);
          App.focusAfter.restore(tok, function () {
            return container.querySelector('[data-testid="mcp-test-connection"]') ||
              container.querySelector('h1');
          });
          window.App.showFlash(container, 'Connection reset');
        })
        .catch(function (err) {
          if (!mount.alive()) return;
          revertFn();
          window.App.showFlash(container, 'Error: ' + err.message, true);
        });
    }
    resetBtn.addEventListener('click', function () {
      window.App.confirmDelete(resetBtn, doReset, { confirmLabel: 'Confirm Reset?' });
    });
  }

  // F9 L1 (vibing follow-up): inject or remove the Reset connection button
  // based on the source's current OAuth-state. Called after a successful
  // /test/connect refetch reveals oauth_active changed (e.g., after a
  // fresh OAuth grant via the popup). Targeted DOM mutation — does NOT
  // re-render the editor (would clobber in-flight form edits).
  function syncResetButtonVisibility(container, source, mcpTypes, callbacks, mount) {
    var escapeAttr = window.App.escapeAttr;
    var actionsHost = container.querySelector('.mcp-connection-actions');
    if (!actionsHost) return;
    var existing = actionsHost.querySelector('[data-testid="reset-mcp-connection-btn"]');
    if (hasOAuthState(source)) {
      if (existing) return; // already present
      var resetTooltip = 'Reset this connection? This clears the stored login and tools list. ' +
        'You will need to log in again on the next refresh.';
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-outlined-primary mcp-reset-connection-btn';
      btn.setAttribute('data-testid', 'reset-mcp-connection-btn');
      btn.setAttribute('title', resetTooltip);
      btn.setAttribute('aria-label', resetTooltip);
      btn.setAttribute('data-name', source.name || '');
      btn.innerHTML = '<span data-confirm-title>Reset connection</span>';
      // escapeAttr is used in the static-render path; for dynamic creation
      // the DOM API handles attribute encoding, so escapeAttr is unused
      // here. The reference is kept to mirror the static path's import.
      void escapeAttr;
      // Insert before the "Last updated" label (if present) so the label
      // stays the trailing element with `margin-left: auto`. Falls back
      // to appendChild when no label sibling exists yet.
      var luSibling = actionsHost.querySelector('[data-testid="mcp-tools-last-updated"]');
      if (luSibling) {
        actionsHost.insertBefore(btn, luSibling);
      } else {
        actionsHost.appendChild(btn);
      }
      wireResetButton(container, source, mcpTypes, callbacks, mount);
    } else if (existing) {
      existing.parentNode.removeChild(existing);
    }
  }

  // ── Test Connection handler ─────────────────────────────────────────
  // Promise-chain style ONLY — the entire file uses .then().catch() with
  // zero async/await. Diverging would create a stylistic outlier and may
  // not transpile if the build pipeline targets ES5.

  function handleTestConnection(sourceId, container, testBtn, formData, onSuccess, opts) {
    var escapeHtml = window.App.escapeHtml;
    var statusEl = container.querySelector('[data-testid="mcp-test-status"]');
    var listEl = container.querySelector('[data-testid="mcp-tools-list"]');
    // F9 L1 (vibing follow-up): opts.noAutoPopup suppresses the
    // window.open() call on auth_required and instead renders an
    // explicit "Sign in" consent button into the status panel. Used by
    // the auto-run-after-create path (studio.js onSaveSuccess), where
    // the original Save click's user-gesture context is lost by the
    // time the create POST resolves and Phase A surfaces auth_required —
    // popup-blockers reject popups not triggered by direct interaction.
    // Default false preserves the manual-Refresh-click behavior verbatim.
    var noAutoPopup = !!(opts && opts.noAutoPopup);
    // The mount context (mcp-editor-lifecycle.js): a continuation that lands
    // after destroy writes nothing; the server-change invalidations still run.
    var mount = (opts && opts.mount) || { alive: function () { return true; }, destroy: function () {} };
    // Focus inside the status panel (the sign-in link block) is lost when the
    // panel is rewritten; on success it is handed to Refresh connection.
    var focusWasInStatus = !!(document.activeElement &&
      statusEl.contains(document.activeElement));
    statusEl.textContent = 'Testing connection…';
    statusEl.hidden = false;
    listEl.hidden = true;
    listEl.innerHTML = '';
    testBtn.disabled = true; // concurrent-Test guard: re-enabled only on final state

    function settle() {
      if (!mount.alive()) return;
      testBtn.disabled = false; // re-enable on final state
      // M25 F6 L1b (DD2): focus returns to the button the keyboard user pressed.
      // A null token (the auto-run after create) is a no-op.
      App.focusAfter.restore(opts && opts.focusTok, testBtn);
    }

    // Starts the OAuth sign-in popup (mcp-oauth-consent.js); `rerun` re-runs this
    // test with noAutoPopup once the token lands.
    function rerun() {
      handleTestConnection(sourceId, container, testBtn, formData, onSuccess,
        { noAutoPopup: true, mount: mount });
    }
    function launchConsentPopup(consentUrl) {
      window.App.studio.mcpEditor.oauthConsent.launchConsentPopup({
        consentUrl: consentUrl, statusEl: statusEl, sourceId: sourceId, settle: settle,
        rerun: rerun, mount: mount
      });
    }


    // F8 L4: send the operator's in-flight form values so Test connection
    // tests what's in the field, not what's in the DB. Backend mirrors PUT's
    // secrets-resolution (per-key __MASKED__ + OAuth-managed-key preservation).
    // Empty body falls back to persisted state — preserves the prior contract.
    var fetchOpts = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    };
    if (formData) {
      fetchOpts.body = JSON.stringify({
        type: formData.type,
        config: formData.config || {},
        secrets: formData.secrets || {},
      });
    }
    fetch('/api/mcp-sources/' + encodeURIComponent(sourceId) + '/test/connect', fetchOpts)
      .then(function (resp) {
        // F9 L2 vibing: defense-in-depth against non-JSON 500s. The backend
        // helpers now ship a catch-all envelope that converts unexpected
        // exceptions into 200 {status: "error"}, but if anything escapes
        // (FastAPI itself raising before our handler, an upstream proxy
        // returning HTML, etc.) we'd choke on resp.json() with "Unexpected
        // token <" and surface a useless message. Read the body as text on
        // !ok so the .catch handler renders something actionable.
        if (resp.ok) return resp.json();
        return resp.text().then(function (body) {
          var snippet = (body || '').trim().slice(0, 500);
          var err = new Error('Server error ' + resp.status + ' ' + resp.statusText +
                              (snippet ? ': ' + snippet : ''));
          err.serverStatus = resp.status;
          throw err;
        });
      })
      .then(function (data) {
        var live = mount.alive();
        // Every outcome changes the server-side record: a successful connect
        // rewrote config._cache (DD9) and an error / auth_required Test recorded
        // _cache.last_check (leg 08a, DD6), so the Library list is stale either way,
        // even when the editor is already torn down. An ok reaches the list
        // through onSuccess; the other outcomes through opts.onListStale, once.
        App.store.invalidate('mcp-sources');
        if (data.status !== 'ok' && opts && typeof opts.onListStale === 'function') {
          try { opts.onListStale(); } catch (e) { /* swallow */ }
        }
        if (!live && data.status !== 'ok') return;
        if (data.status === 'ok') {
          if (!live) {
            if (typeof onSuccess === 'function') onSuccess();
            return;
          }
          // Render summary + collapsible tool list. Cloudflare-class servers
          // ship verbose multi-paragraph descriptions; <details> keeps the
          // section scannable while preserving full content.
          // F8 L2: append capability-flags one-liner after the tools count.
          // F4 L7 (M08): LED moved up to the connection-actions row; the
          // status banner here keeps only the tool-count line. Update both
          // sites so the new LED reflects the post-/test/connect success.
          statusEl.innerHTML = (
            'Server exposes <strong>' + data.tools.length + '</strong> tool' +
            (data.tools.length === 1 ? '' : 's') + '.'
          );
          var ledEl = container.querySelector('[data-testid="mcp-connection-led"]');
          if (ledEl) {
            ledEl.className = 'indicator-led indicator-led--success';
            ledEl.setAttribute('data-state', 'success');
            ledEl.setAttribute('aria-label', 'Connected');
          }
          listEl.innerHTML = renderToolsListHtml(data.tools);
          listEl.hidden = false;
          // F9 L1 (vibing): backend just persisted last_updated to ~now;
          // mirror that locally so the displayed timestamp updates
          // immediately (the operator doesn't have to reload to see
          // "just now"). The exact server-side time is close enough.
          var luEl = container.querySelector('[data-testid="mcp-tools-last-updated"]');
          if (luEl) {
            luEl.textContent = 'Last updated: just now';
            luEl.hidden = false;
          }
          // F9 L1 (vibing follow-up): caller-supplied hook fires after
          // any successful /test/connect (Phase A or Phase 2). Used to
          // refetch source state for OAuth-state-dependent UI (Reset
          // button visibility) — see callsite in wireEditorEvents.
          if (typeof onSuccess === 'function') {
            try { onSuccess(); } catch (e) { /* swallow */ }
          }
          settle();
          var ae = document.activeElement;
          if (focusWasInStatus && (!ae || ae === document.body)) testBtn.focus();
        } else if (data.status === 'auth_required') {
          if (noAutoPopup) {
            // Auto-run-after-create path: render an explicit "Sign in"
            // consent button instead of opening the popup directly.
            // Direct user-click on this button restores the gesture
            // context required for window.open() to bypass popup
            // blockers. The button is wired one-shot — clicking it
            // invokes launchConsentPopup() which opens the popup AND
            // wires the close-watcher → Phase 2 re-POST.
            statusEl.innerHTML = '';
            var prompt = document.createElement('span');
            prompt.textContent = 'This server requires authorization. ';
            statusEl.appendChild(prompt);
            var consentBtn = document.createElement('button');
            consentBtn.type = 'button';
            consentBtn.className = 'btn-outlined-primary';
            consentBtn.setAttribute('data-testid', 'mcp-consent-btn');
            consentBtn.textContent = 'Sign in';
            consentBtn.addEventListener('click', function () {
              launchConsentPopup(data.consent_url);
            });
            statusEl.appendChild(consentBtn);
            // Re-enable Refresh button so the operator can also retry
            // from there if they prefer; the consent button is the
            // primary affordance.
            settle();
          } else {
            // Manual-click path: the original Refresh click IS the user
            // gesture; open the popup immediately. Keep button disabled
            // across the popup-flow — re-enabled when Phase 2 re-POST
            // settles (in this same function).
            launchConsentPopup(data.consent_url);
          }
        } else {
          statusEl.innerHTML = '';
          var errEl = window.App.buildMcpError(data.error || '');
          errEl.setAttribute('data-testid', 'mcp-connection-error');
          statusEl.appendChild(errEl);
          settle();
        }
      })
      .catch(function (err) {
        if (!mount.alive()) return;
        statusEl.innerHTML = '';
        var netErrEl = window.App.buildMcpError(err && err.message ? err.message : '');
        netErrEl.setAttribute('data-testid', 'mcp-connection-error');
        statusEl.appendChild(netErrEl);
        settle();
      });
  }

  window.App.studio.mcpEditor.connectionStatus = {
    renderConnectionActions: renderConnectionActions,
    wireResetButton: wireResetButton,
    syncResetButtonVisibility: syncResetButtonVisibility,
    handleTestConnection: handleTestConnection
  };
})();
