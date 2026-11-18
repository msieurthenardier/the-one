// App.studio.mcpEditor.connectionStatus — the MCP source editor's connection state:
// the status line, the Test flow's result area, and Reset connection / Forget tools
// list (M31 F5 L08b, on the control library).
//
// create({container, mount, callbacks, getSource, testBtn, serverInfo, setError, titleEl,
//         onTestHoldChange})
// builds, once per mount, the tail of the Connection section:
//   div.mcp-connection-state
//     div.mcp-connection-status-row   the App.ui.status line (the words come only from
//                                      App.usage.mcpStateLabel) + Reset / Forget
//     div[data-testid=mcp-test-status]  the result area: empty and hidden at rest and
//                                      after a success (the line says Connected)
// and returns {el, render, runTest, showInvalid, isTesting}.
//
// The line reads App.usage.mcpState(getSource()), the Library list's own derivation, so
// the two name one state. After EVERY Test outcome, the sign-in poll, Reset and Forget,
// an identity-guarded refetch copies _cache, oauth_active and has_access_token into the
// controller's CURRENT source (read through getSource(), so a Save that replaced it
// meanwhile is not overwritten) and re-renders; a failed refetch leaves the optimistic
// state a clean Test set. A Test of unsaved form values records nothing server-side, so
// it leaves the line on the saved record and labels its result.
//
// Test's disabled state and label are the shell's (M31 F5 L10): this module never writes
// the button. It reports a Test starting and settling through onTestHoldChange(), whose
// one implementation (the controller's syncTestHold) reads isTesting() and the mount's
// session. testBtn is the shell's button and is null for a create form or a type other
// than stdio and streamable-http; it is read-only here (the focus targets) and every use
// tolerates null.
//
// Reset is for a signed-in HTTP server only. Forget tools list is shown for a cached HTTP
// server without a sign-in and, since sortie 19, for a local-command server (type stdio)
// whose cache holds a tools list.
//
// Reset and Forget are built once, on first need, and then only toggle `hidden`: a
// refetch never rebuilds a button, armed or not (squawk 0088's invariant). Both are
// disabled while a consent session runs (the session's mount hook). The sign-in popup is
// in mcp-oauth-consent.js and still opens synchronously where the click handed it over.
// Exposes: create.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  var hasOAuthState = window.App.studio.mcpEditor.shared.hasOAuthState;

  // The status line's LED state for each connection state.
  var LED_FOR_STATE = { connected: 'success', none: 'idle', error: 'danger', signin: 'warning' };

  // "3:42 PM", with the date first when it is not today, in the operator's zone.
  function whenText(seconds) {
    var then = new Date(seconds * 1000);
    var text = App.time.formatClock(then);
    if (App.time.dayNumber(new Date()) !== App.time.dayNumber(then)) {
      text = App.time.formatDate(then) + ', ' + text;
    }
    return text;
  }

  function cacheOf(source) {
    return (source && source.config && source.config._cache) || null;
  }

  function detailOf(resp) {
    return resp.text().then(function (body) {
      var detail = '';
      try { detail = (JSON.parse(body) || {}).detail || ''; } catch (e) { /* not JSON */ }
      return typeof detail === 'string' ? detail : '';
    });
  }

  function create(opts) {
    var container = opts.container;
    var mount = opts.mount;
    var callbacks = opts.callbacks || {};
    var getSource = opts.getSource;
    var testBtn = opts.testBtn;
    var serverInfo = opts.serverInfo;
    var setError = opts.setError || function () {};
    var titleEl = opts.titleEl || function () { return null; };
    var onTestHoldChange = opts.onTestHoldChange || function () {};
    var testing = false;
    var latest = App.ui.util.latest();

    var statusCtl = App.ui.status({
      testid: 'mcp-connection-status', ledTestid: 'mcp-connection-led'
    });
    var rowEl = document.createElement('div');
    rowEl.className = 'mcp-connection-status-row';
    rowEl.appendChild(statusCtl.el);
    var areaEl = document.createElement('div');
    areaEl.className = 'mcp-test-result';
    areaEl.setAttribute('data-testid', 'mcp-test-status');
    areaEl.hidden = true;
    var el = document.createElement('div');
    el.className = 'mcp-connection-state';
    el.appendChild(rowEl);
    el.appendChild(areaEl);
    // One persistent polite live region (WCAG 4.1.3), created here and never recreated:
    // a node inserted already-populated is often not announced, so the transient
    // "Testing connection..." and sign-in prompt are announced by setting this text.
    // It sits after the (hidden-at-rest) area so display:none never removes it.
    var liveEl = document.createElement('div');
    liveEl.className = 'visually-hidden';
    liveEl.setAttribute('role', 'status');
    liveEl.setAttribute('data-testid', 'mcp-test-live');
    el.appendChild(liveEl);

    var resetBtn = null;
    var forgetBtn = null;

    // ── The status row ────────────────────────────────────────────────

    function lineText(ms, source) {
      var text = App.usage.mcpStateLabel(ms.state);
      if (ms.state === 'connected' && ms.checkedAt) {
        text += ' · checked ' + whenText(ms.checkedAt);
      } else if (ms.state === 'error') {
        var cache = cacheOf(source);
        if (cache && Array.isArray(cache.tools) && typeof cache.last_updated === 'number') {
          text += ' · last connected ' + whenText(cache.last_updated);
        }
      }
      return text;
    }

    // btn: the App.ui.button the caller built (its testid is a literal there).
    function confirmButton(btn, title, confirmLabel, doIt) {
      var span = document.createElement('span');
      span.setAttribute('data-confirm-title', '');
      span.textContent = title;
      btn.appendChild(span);
      btn.addEventListener('click', function () {
        App.ui.confirm(btn, function (b, revert) { doIt(b, revert); }, {
          confirmLabel: confirmLabel,
          announceName: (getSource() || {}).name || 'this server'
        });
      });
      rowEl.appendChild(btn);
      return btn;
    }

    // Insert a button once, then only toggle it.
    function syncButton(btn, show, make) {
      if (!btn && show) btn = make();
      if (btn) {
        btn.hidden = !show;
        btn.disabled = mount.sessionActive();
      }
      return btn;
    }

    function updateButtons() {
      var source = getSource();
      var cache = cacheOf(source);
      var reset = hasOAuthState(source);
      var forget = !!(source && source.type === 'streamable-http' && source.oauth_active !== true &&
        cache && (cache.auth_posture || cache.tools));
      // A local-command server has no sign-in, but a stored tools list can go stale.
      if (!forget && source && source.type === 'stdio' && cache && Array.isArray(cache.tools)) {
        forget = true;
      }
      resetBtn = syncButton(resetBtn, reset, function () {
        return confirmButton(App.ui.button({ testid: 'reset-mcp-connection-btn' }),
          'Reset connection', 'Reset connection?', function (b, revert) {
            runDelete(b, revert, 'Connection reset');
          });
      });
      forgetBtn = syncButton(forgetBtn, forget, function () {
        return confirmButton(App.ui.button({ testid: 'forget-mcp-connection-btn' }),
          'Forget tools list', 'Forget tools list?', function (b, revert) {
            runDelete(b, revert, 'Tools list forgotten');
          });
      });
    }

    function render() {
      var source = getSource();
      var ms = App.usage.mcpState(source);
      statusCtl.set(LED_FOR_STATE[ms.state] || 'idle', lineText(ms, source));
      statusCtl.el.setAttribute('data-mcp-state', ms.state);
      updateButtons();
    }

    mount.onSessionChange(updateButtons);
    App.time.onChange(render, el);

    // ── The result area ───────────────────────────────────────────────

    function clearArea() {
      liveEl.textContent = '';
      areaEl.replaceChildren();
      areaEl.hidden = true;
    }

    function showText(text) {
      var span = document.createElement('span');
      span.textContent = text;
      areaEl.replaceChildren(span);
      areaEl.hidden = false;
      liveEl.textContent = text;
    }

    function addNote(text) {
      var note = document.createElement('p');
      note.className = 'mcp-test-note';
      note.textContent = text;
      areaEl.appendChild(note);
    }

    function showError(raw, transport, dirty) {
      var errEl = window.App.buildMcpError(raw, { transport: transport, live: 'none' });
      errEl.setAttribute('data-testid', 'mcp-connection-error');
      areaEl.replaceChildren(errEl);
      areaEl.hidden = false;
      if (dirty) addNote('Tested with your unsaved changes.');
    }

    // A dirty form that cannot be sent: say why, send nothing.
    function showInvalid(message) {
      var box = document.createElement('div');
      box.className = 'mcp-tools-error';
      box.setAttribute('role', 'alert');
      box.textContent = message;
      areaEl.replaceChildren(box);
      areaEl.hidden = false;
      liveEl.textContent = '';
    }

    // ── The Tools list ────────────────────────────────────────────────
    // Owned by serverInfo (M31 F5 L09); the status module only feeds it.

    // data: a /test/connect "ok" body ({tools}).
    function showTools(data) {
      serverInfo.setTools(data.tools);
    }

    function emptyTools() {
      serverInfo.setTools(null);
    }

    // ── The server record ─────────────────────────────────────────────

    function applyServerState(source, fresh) {
      source.oauth_active = !!fresh.oauth_active;
      source.has_access_token = !!fresh.has_access_token;
      source.config = source.config || {};
      var cache = fresh.config && fresh.config._cache;
      if (cache) source.config._cache = cache; else delete source.config._cache;
    }

    // Refetch the saved record and repaint, behind an identity and latest-wins guard.
    function syncFromServer() {
      var id = (getSource() || {}).id;
      var token = latest.next();
      return fetch('/api/mcp-sources/' + encodeURIComponent(id))
        .then(function (r) { return r && r.ok ? r.json() : null; })
        .then(function (fresh) {
          if (!fresh || !mount.alive() || !latest.isCurrent(token)) return;
          var source = getSource();
          if (!source || source.id !== id) return;
          applyServerState(source, fresh);
          render();
          serverInfo.update(cacheOf(source));
        })
        .catch(function () { /* best-effort: the optimistic state stands */ });
    }

    // A clean Test records a result server-side; mirror it until the refetch confirms.
    function recordLocally(status, tools) {
      var source = getSource();
      if (!source) return;
      source.config = source.config || {};
      var cache = source.config._cache = source.config._cache || {};
      var now = Date.now() / 1000;
      cache.last_check = { status: status, at: now };
      if (tools) { cache.tools = tools; cache.last_updated = now; }
      render();
    }

    // ── Reset connection / Forget tools list ──────────────────────────

    function runDelete(btn, revert, doneText) {
      var source = getSource();
      var id = source && source.id;
      if (!id) return;
      var tok = App.focusAfter.begin(btn);
      fetch('/api/mcp-sources/' + encodeURIComponent(id) + '/connection', { method: 'DELETE' })
        .then(function (r) {
          if (r.ok) return null;
          return detailOf(r).then(function (d) { throw new Error(d || 'Reset failed'); });
        })
        .then(function () {
          // The route dropped config._cache and the sign-in: the Library list is stale
          // even when this editor is gone.
          App.store.invalidate('mcp-sources');
          App.store.invalidate('agents');
          if (callbacks.onListStale) callbacks.onListStale();
          if (!mount.alive() || !getSource() || getSource().id !== id) return;
          // The button is about to be hidden (or stay): put it back at rest so it is
          // never shown again armed (squawk 0371).
          revert();
          var s = getSource();
          s.oauth_active = false;
          s.has_access_token = false;
          if (s.config) delete s.config._cache;
          setError('');
          clearArea();
          emptyTools();
          render();
          serverInfo.update(null);
          App.ui.flash(doneText);
          App.focusAfter.restore(tok, function () {
            return (testBtn && !testBtn.disabled && testBtn) || titleEl();
          });
          syncFromServer();
        })
        .catch(function (err) {
          if (!mount.alive()) return;
          revert();
          setError(err.message || String(err));
          App.focusAfter.restore(tok, btn);
        });
    }

    // ── The Test flow ─────────────────────────────────────────────────
    // Promise-chain style only (.then/.catch), like the rest of the editor.

    // formData: null (the form is clean: the server tests, and records, the saved
    // server) or the form's {type, config, secrets} (unsaved values; nothing recorded).
    function runTest(formData, ro) {
      ro = ro || {};
      var source = getSource();
      var sourceId = source.id;
      var dirty = !!formData;
      var noAutoPopup = !!ro.noAutoPopup;
      var transport = formData ? formData.type : source.type;
      // Focus inside the result area (the sign-in link block) is lost when it is
      // rewritten; on success it is handed to Test.
      var focusWasInArea = !!(document.activeElement && areaEl.contains(document.activeElement));
      showText('Testing connection…');
      testing = true;
      onTestHoldChange(); // concurrent-Test guard: released only on a final state

      function settle() {
        testing = false;
        if (!mount.alive()) return;
        onTestHoldChange();
        // M25 F6 L1b (DD2): focus returns to the button the keyboard user pressed. A null
        // token (the auto-run after create) is a no-op.
        App.focusAfter.restore(ro.focusTok, testBtn || titleEl);
      }
      // A sign-in that ended without a token: the record may still have changed.
      function settleAndSync() { settle(); syncFromServer(); }

      function rerun() {
        runTest(formData, { noAutoPopup: true, focusTok: null });
      }
      function launchConsentPopup(consentUrl) {
        window.App.studio.mcpEditor.oauthConsent.launchConsentPopup({
          consentUrl: consentUrl, statusEl: areaEl, sourceId: sourceId, settle: settleAndSync,
          rerun: rerun, mount: mount
        });
      }

      // F8 L4: send the operator's in-flight form values so Test tests what is in the
      // field, not what is in the DB. An empty body tests the persisted state.
      var fetchOpts = { method: 'POST', headers: { 'Content-Type': 'application/json' } };
      if (formData) {
        fetchOpts.body = JSON.stringify({
          type: formData.type,
          config: formData.config || {},
          secrets: formData.secrets || {}
        });
      }
      fetch('/api/mcp-sources/' + encodeURIComponent(sourceId) + '/test/connect', fetchOpts)
        .then(function (resp) {
          // Defense in depth against a non-JSON 500: read the body as text so the catch
          // renders something actionable rather than "Unexpected token <".
          if (resp.ok) return resp.json();
          return resp.text().then(function (body) {
            var snippet = (body || '').trim().slice(0, 500);
            throw new Error('Server error ' + resp.status + ' ' + resp.statusText +
              (snippet ? ': ' + snippet : ''));
          });
        })
        .then(function (data) {
          // Every outcome changes the server-side record (a connect rewrote the cache, an
          // error / auth_required Test recorded last_check), so the Library list is
          // stale either way, even when the editor is already torn down.
          App.store.invalidate('mcp-sources');
          if (callbacks.onListStale) {
            try { callbacks.onListStale(); } catch (e) { /* swallow */ }
          }
          if (!mount.alive()) return;
          if (data.status === 'ok') {
            testing = false;
            showTools(data);
            if (dirty) {
              showText(App.usage.mcpStateLabel('connected') + '. Tested with your unsaved changes.');
            } else {
              clearArea();
              recordLocally('ok', data.tools);
            }
            settle();
            var ae = document.activeElement;
            if (focusWasInArea && (!ae || ae === document.body)) {
              var focusEl = testBtn || titleEl();
              if (focusEl) focusEl.focus();
            }
            syncFromServer();
          } else if (data.status === 'auth_required') {
            if (!dirty) recordLocally('auth_required');
            syncFromServer();
            if (noAutoPopup) {
              // Auto-run-after-create path: the Save click's gesture is gone, so render an
              // explicit "Sign in" button; its own click is the gesture for the popup.
              var prompt = document.createElement('span');
              prompt.textContent = 'This server requires authorization. ';
              var consentBtn = App.ui.button({
                label: 'Sign in', testid: 'mcp-consent-btn',
                onClick: function () { launchConsentPopup(data.consent_url); }
              });
              areaEl.replaceChildren(prompt, consentBtn);
              areaEl.hidden = false;
              liveEl.textContent = 'This server requires authorization.';
              settle();
            } else {
              // Manual-click path: the Test click IS the user gesture; open the popup now.
              // Test stays disabled across the popup flow (the mount's session hold).
              launchConsentPopup(data.consent_url);
            }
          } else {
            showError(data.error || '', transport, dirty);
            if (!dirty) recordLocally('error');
            settle();
            syncFromServer();
          }
        })
        .catch(function (err) {
          testing = false;
          if (!mount.alive()) return;
          showError(err && err.message ? err.message : '', transport, dirty);
          settle();
        });
    }

    render();
    return {
      el: el,
      render: render,
      runTest: runTest,
      showInvalid: showInvalid,
      isTesting: function () { return testing; }
    };
  }

  window.App.studio.mcpEditor.connectionStatus = { create: create };
})();
