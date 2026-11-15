// App.studio.renderProviderEditor — the provider editor, built once per mount
// from App.ui library controls (M31 F1 L7, flight DD1).
//
//   renderProviderEditor(container, provider, providerTypes, callbacks)
//
// callbacks: { onCancel, onSaveSuccess, onDeleteSuccess, onDirtyChange, getTypeDefaults }
//
// One handle object per mount (`h`) holds every control handle (the shell, the
// fields, the status line, the sections, the danger zone and the models
// controller); after the mount a type change, Save, Cancel and Test patch the
// DOM through those handles and never rebuild it. Only the create-to-edit
// transition re-mounts (providers-section.js re-renders, keeping its mountToken
// and editorGen guards).
//
//   App.ui.editorShell   header: breadcrumb "Library / Model providers", title,
//                        `type · base_url` subtitle, Cancel / Save (Create) / Test,
//                        the unsaved caption and the error slot
//   App.ui.section       Connection, Anthropic account, Available models
//   App.ui.field + the form controls (textInput, select, toggle, secretInput)
//   App.ui.status        the Test result line (provider-test-result)
//   App.ui.dangerZone    Delete provider (agent-usage block, then arm and commit)
//
// Fields keep their ids (#pf-*), testids and data-field attributes, so the dirty
// snapshot and the payload builder read them unchanged. The breadcrumb link
// carries no handler: studio's router interception closes the item. The title
// has tabindex -1 so studio.js can focus it on an intent open.
//
// Secret handling: the API key is only ever written to the input through its
// .value property (App.ui.secretInput), never into an attribute, a title, an
// aria-label or a log line; no request payload is logged.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var MASKED_SENTINEL = '__MASKED__';
  // The handle object of the current mount, held in a mount slot. A create
  // re-mounts the editor in edit mode, and the deferred focus after that Save
  // targets the NEW mount's title through the slot (the closure that saved is gone
  // by then).
  var slot = window.App.ui.util.mountSlot();
  var DEFAULT_NUM_CTX = 32768;
  var NUM_CTX_DESC = 'A larger window allows longer conversations but will slow down on partial-GPU setups because fewer layers fit in VRAM';
  var THINKING_DESC = 'When on, models that support adaptive thinking (Claude models from version 4.6 on) reason step by step before answering. Older models on this provider answer without it.';
  var EFFORT_DESC = 'Guides how much the model reasons before answering (reasoning-capable models). Leave on Provider default to omit.';
  var EFFORT_OPTIONS = [
    { value: '', label: 'Provider default' },
    { value: 'low', label: 'low' },
    { value: 'medium', label: 'medium' },
    { value: 'high', label: 'high' }
  ];

  function subtitleText(row) {
    var parts = [row.type];
    if (row.base_url) parts.push(row.base_url);
    return parts.join(' · ');
  }

  function renderProviderEditor(container, provider, providerTypes, callbacks) {
    callbacks = callbacks || {};
    var util = window.App.ui.util;
    var isCreate = !provider;
    var isEdit = !isCreate;
    var type = isCreate ? '' : provider.type;
    var h = { modelsCtl: null, fieldEls: [] };
    slot.mount(function () {}, h);

    function typeDefaults(t) {
      return (callbacks.getTypeDefaults && callbacks.getTypeDefaults(t)) ||
        { base_url: '', showBaseUrl: false, showApiKey: false };
    }
    var defaults = typeDefaults(type);

    var snapshot = '';
    var dirty = false;
    // Capture the pre-filled (masked) key so an untouched field is sent as the
    // sentinel and the stored key survives. Empty in create mode.
    var originalMaskedApiKey = isEdit ? (provider.api_key || '') : '';
    // The expiry line renders from the last SAVED row (an edit-mode Save
    // replaces it with the PUT response, since the editor does not re-mount).
    var expiryRow = provider || null;

    function checkDirty() {
      dirty = getFormSnapshot(h) !== snapshot;
      // Cancel follows `dirty` in edit mode only; the create form's Cancel
      // (abandon creation) stays enabled whether or not anything was typed.
      h.shell.setDirty(dirty);
      // Notify the orchestrator's mirror so the leave guard (App.nav) reads the
      // same logical state.
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(dirty);
    }
    function watch(el) {
      h.fieldEls.push(el);
      el.addEventListener('input', checkDirty);
      el.addEventListener('change', checkDirty);
      return el;
    }

    // ── Header ──────────────────────────────────────────────────────
    h.shell = App.ui.editorShell({
      breadcrumb: {
        label: 'Library',
        href: window.App.router.href({ destination: 'library' }),
        trail: ' / Model providers'
      },
      title: isCreate ? 'New model provider' : (provider.name || ''),
      subtitle: isCreate ? null : subtitleText(provider),
      actions: {
        cancel: { testid: 'cancel-provider-btn', enabledWhenClean: isCreate, onClick: onCancelClick },
        save: { label: isCreate ? 'Create' : 'Save', testid: 'save-provider-btn', onClick: function () { performSave(); } },
        test: isCreate ? null : { label: 'Test', testid: 'test-connection-btn', className: 'provider-test-btn', onClick: onTestClick }
      }
    });

    // ── Connection fields ───────────────────────────────────────────
    var nameInput = watch(App.ui.textInput({
      id: 'pf-name', value: isCreate ? '' : provider.name, placeholder: 'My provider', dataset: { field: 'name' }
    }));
    h.name = App.ui.field({ label: 'Name', control: nameInput });
    nameInput.addEventListener('input', function () { h.name.setError(null); });

    var typeOptions = [];
    if (isCreate) typeOptions.push({ value: '', label: 'Select a provider…', disabled: true });
    var known = false;
    var t;
    for (t = 0; t < providerTypes.length; t++) {
      if (providerTypes[t].value === type) known = true;
      typeOptions.push({ value: providerTypes[t].value, label: providerTypes[t].label });
    }
    // A saved type the server no longer offers (a mock provider with dev mode
    // off) still shows as itself.
    if (isEdit && !known) typeOptions.push({ value: type, label: type });
    var typeSelect = watch(App.ui.select({
      id: 'pf-type', options: typeOptions, value: type, dataset: { field: 'type' }
    }));
    h.type = App.ui.field({ label: 'Type', control: typeSelect });

    var baseUrlInput = watch(App.ui.textInput({
      id: 'pf-base-url', value: (isCreate ? defaults.base_url : provider.base_url) || '',
      placeholder: 'https://...', dataset: { field: 'base_url' }
    }));
    h.baseUrl = App.ui.field({ label: 'Base URL', control: baseUrlInput });
    h.baseUrl.el.classList.add('admin-pf-base-url');
    h.baseUrl.el.hidden = !defaults.showBaseUrl;

    // The API key. Label, placeholder and help line come from TYPE_DEFAULTS (the
    // token type relabels this row "Token"); a type change patches the same
    // nodes through the field handle.
    h.secret = App.ui.secretInput({
      id: 'pf-api-key', value: isCreate ? '' : (provider.api_key || ''),
      placeholder: defaults.apiKeyPlaceholder || 'sk-...', dataset: { field: 'api_key' }
    });
    watch(h.secret.input);
    h.apiKey = App.ui.field({
      label: defaults.apiKeyLabel || 'API Key', control: h.secret.input, host: h.secret.el,
      hint: defaults.apiKeyHelp, hintTestid: 'provider-api-key-help'
    });
    h.apiKey.el.classList.add('admin-pf-api-key');
    h.apiKey.el.hidden = !defaults.showApiKey;
    // The token's added/expires line (edit mode); filled by renderTokenExpiry.
    h.expiryHost = null;
    if (isEdit) {
      h.expiryHost = util.el('div', { className: 'admin-pf-token-expiry', hidden: true });
      h.apiKey.el.appendChild(h.expiryHost);
    }

    // Context window (config.num_ctx): Ollama-only, required, always carries a
    // value (the default window for a new provider, else the stored one).
    var numCtx = (isEdit && provider.config && provider.config.num_ctx != null)
      ? provider.config.num_ctx : DEFAULT_NUM_CTX;
    var numCtxInput = watch(App.ui.textInput({
      id: 'pf-num-ctx', type: 'number', value: String(numCtx), required: true,
      dataset: { field: 'config.num_ctx' }
    }));
    numCtxInput.min = '1';
    numCtxInput.step = '1';
    h.numCtx = App.ui.field({ label: 'Context window', control: numCtxInput, info: NUM_CTX_DESC });
    h.numCtx.el.classList.add('admin-pf-num-ctx');
    h.numCtx.el.hidden = !defaults.showNumCtx;

    // Extended thinking (config.thinking_enabled): an Anthropic on/off switch.
    // The native checkbox drives collect and dirty through .checked.
    h.thinking = App.ui.toggle({
      id: 'pf-thinking-enabled', label: 'Extended thinking', info: THINKING_DESC,
      checked: isEdit ? !!(provider.config && provider.config.thinking_enabled) : true,
      dataset: { field: 'config.thinking_enabled' }
    });
    watch(h.thinking.control);
    h.thinking.el.classList.add('admin-pf-thinking-enabled');
    h.thinking.el.hidden = !defaults.showThinkingEnabled;

    // Reasoning effort (config.reasoning_effort): optional; the empty "Provider
    // default" option omits the key server-side.
    var effortSelect = watch(App.ui.select({
      id: 'pf-reasoning-effort', options: EFFORT_OPTIONS,
      value: (isEdit && provider.config && provider.config.reasoning_effort) || '',
      dataset: { field: 'config.reasoning_effort' }
    }));
    h.effort = App.ui.field({ label: 'Reasoning effort', control: effortSelect, info: EFFORT_DESC });
    h.effort.el.classList.add('admin-pf-reasoning-effort');
    h.effort.el.hidden = !defaults.showReasoningEffort;

    // The Test result line (edit only); shown once a test starts.
    h.testStatus = App.ui.status({ testid: 'provider-test-result' });
    h.testStatus.el.hidden = true;

    h.connection = App.ui.section({
      title: 'Connection',
      children: [h.name.el, h.type.el, h.baseUrl.el, h.apiKey.el, h.numCtx.el, h.thinking.el, h.effort.el, h.testStatus.el]
    });

    // ── Anthropic account (M19 F01 L03) ─────────────────────────────
    // Present in every mode and type, hidden unless the selected type carries
    // showPlanSignIn (the OAuth type only). The body is populated by
    // wirePlanSignIn; nothing inside carries a data-field (the dirty snapshot
    // selects [data-field], so the sign-in machinery stays out of it).
    // The state node is replaced per state; the error line is built once, outside
    // it, so an error shown after a re-render is not lost.
    h.planState = util.el('div', { className: 'plan-signin-state' });
    h.planErrBanner = App.ui.banner({ tone: 'error', role: 'status', hidden: true,
      className: 'plan-signin-error', testid: 'plan-signin-error' });
    h.planErr = h.planErrBanner.el;
    h.planBody = util.el('div', { className: 'plan-signin-body' }, [h.planState, h.planErr]);
    h.planSection = App.ui.section({
      title: 'Anthropic account', className: 'admin-pf-plan-signin', children: [h.planBody]
    });
    h.planSection.el.hidden = !defaults.showPlanSignIn;

    var sections = [h.shell.el, h.connection.el, h.planSection.el];

    // ── Models (edit only) ──────────────────────────────────────────
    if (isEdit) {
      // DD10: the list is information, not a picker; one line of help whose
      // "Agents" word links.
      var modelsHelp = util.el('p', { className: 'admin-pf-models-help', 'data-testid': 'provider-models-help' }, [
        'Each of your ',
        util.el('a', {
          href: window.App.router.href({ destination: 'agents' }), 'data-testid': 'provider-models-agents-link', text: 'Agents'
        }),
        ' chooses one of these in its Model section.'
      ]);
      h.modelsHost = util.el('div', { className: 'provider-models' });
      sections.push(App.ui.section({ title: 'Available models', children: [modelsHelp, h.modelsHost] }).el);

      h.danger = App.ui.dangerZone({
        title: 'Danger zone',
        action: {
          label: 'Delete provider', testid: 'delete-provider-btn', dataset: { name: provider.name || '' },
          beforeArm: beforeDeleteArm, onConfirm: doDelete
        },
        notice: { testid: 'delete-blocked-message' }
      });
      sections.push(h.danger.el);
    }

    container.replaceChildren.apply(container, sections);

    // Mount the Models panel synchronously (so tests find selectors at once). It
    // returns a controller {refresh, destroy}; Test success refreshes it in place.
    if (isEdit && window.App.studio.renderProviderModels) {
      h.modelsCtl = window.App.studio.renderProviderModels(h.modelsHost, provider);
    }

    snapshot = getFormSnapshot(h);
    h.shell.setDirty(false);

    // ── Type change ─────────────────────────────────────────────────
    // Show or hide the rows, reset base_url to the type's default and relabel the
    // key row. api_key is NOT clobbered, so values survive a type switch. The
    // models panel is not re-dispatched.
    typeSelect.addEventListener('change', function () {
      var d = typeDefaults(typeSelect.value);
      h.baseUrl.el.hidden = !d.showBaseUrl;
      h.apiKey.el.hidden = !d.showApiKey;
      h.numCtx.el.hidden = !d.showNumCtx;
      h.thinking.el.hidden = !d.showThinkingEnabled;
      h.effort.el.hidden = !d.showReasoningEffort;
      h.planSection.el.hidden = !d.showPlanSignIn;
      baseUrlInput.value = d.base_url || '';
      applyApiKeyCopy(d);
      renderExpiry();
      checkDirty();
    });

    // The API-key row's label, placeholder and help line follow the selected type.
    function applyApiKeyCopy(d) {
      h.apiKey.setLabel(d.apiKeyLabel || 'API Key');
      h.secret.input.placeholder = d.apiKeyPlaceholder || 'sk-...';
      h.apiKey.setHint(d.apiKeyHelp || null);
      // The hint is inserted at the end of the group: keep the expiry line below it.
      if (h.expiryHost) h.apiKey.el.appendChild(h.expiryHost);
    }

    function renderExpiry() {
      renderTokenExpiry(h.expiryHost, expiryRow, typeSelect.value);
    }
    renderExpiry();
    // The dates follow the operator zone live (squawk 0196). The editor has no
    // teardown hook, so the listener is owner-scoped to the Connection section,
    // which stays connected for the editor's lifetime; App.time drops it when
    // the section leaves the page.
    if (h.expiryHost) {
      window.App.time.onChange(renderExpiry, h.connection.el);
    }

    // Anthropic plan sign-in section (M19 F01 L03): owns its own OAuth fetches,
    // deliberately outside the dirty machinery. performSave is handed in so the
    // create-mode sign-in button can run the auto-save-then-start path.
    wirePlanSignIn(h, container, provider, performSave);

    // ── Cancel ──────────────────────────────────────────────────────
    // Edit mode reverts in place; create mode delegates to onCancel (enabled from
    // the first render, so it runs on a pristine form too).
    function onCancelClick() {
      if (isEdit) {
        var cancelTok = App.focusAfter.begin(h.shell.cancelButton);
        var snap = JSON.parse(snapshot);
        for (var j = 0; j < h.fieldEls.length; j++) {
          var el = h.fieldEls[j];
          // Checkbox-aware revert: .checked for checkboxes, .value otherwise.
          if (el.type === 'checkbox') {
            el.checked = !!snap[el.dataset.field];
          } else {
            el.value = snap[el.dataset.field] || '';
          }
        }
        h.secret.setRevealed(false);
        h.name.setError(null);
        checkDirty();
        App.focusAfter.restore(cancelTok, h.shell.titleEl);
      } else if (callbacks.onCancel) {
        callbacks.onCancel();
      }
    }

    // ── Save ────────────────────────────────────────────────────────
    // Factored into performSave so the plan sign-in button reuses the same path.
    // onCreateSuccess (optional) fires only on a successful CREATE and BEFORE
    // onSaveSuccess, so the pendingAutoSignInId handoff is in place at the re-mount.
    var saving = false; // the plan sign-in button is outside the shell's busy state
    function busy(v) { saving = v; h.shell.setBusy(v); }
    function performSave(onCreateSuccess) {
      if (saving) return;
      h.shell.setError('');
      var payload = collectFormData(h, callbacks, originalMaskedApiKey, isEdit, provider, h.shell.setError);
      if (!payload) return; // validation failed; collectFormData wrote the error
      var saveTok = App.focusAfter.begin(h.shell.saveButton);
      busy(true); // squawk 0236; a create stays busy: the remount replaces the shell
      var url = isEdit ? '/api/providers/' + encodeURIComponent(provider.id) : '/api/providers';
      var method = isEdit ? 'PUT' : 'POST';
      App.api.fetchJson(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(function (updated) {
          App.store.invalidate('providers');
          // A flash across the create re-mount is dropped (DD7).
          if (isEdit) App.ui.flash('Provider saved');
          if (!isEdit && onCreateSuccess) onCreateSuccess(updated);
          // Create re-mounts the editor in edit mode asynchronously (the
          // orchestrator's `ready` promise): park the restore for that mount.
          // The target resolves at the NEW mount: the latest mount's shell title.
          if (!isEdit) App.focusAfter.defer(saveTok, function () { var cur = slot.current(); return cur && cur.data.shell && cur.data.shell.titleEl; });
          if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, !isEdit);
          // Create to edit replaces this closure (the orchestrator re-renders).
          // On edit to edit the editor stays mounted: patch the display-only
          // header, the expiry line and the snapshot through the handles.
          if (isEdit) {
            h.shell.setTitle(updated.name || '');
            h.shell.setSubtitle(subtitleText(updated));
            // KEY RE-MASK FIX: show the server's masked value again and hide it, so
            // the typed plaintext does not linger in the field and is not re-sent
            // by the next Save.
            h.secret.setValue(updated.api_key || '');
            originalMaskedApiKey = updated.api_key || '';
            expiryRow = updated;
            renderTokenExpiry(h.expiryHost, expiryRow, updated.type);
            snapshot = getFormSnapshot(h);
            checkDirty();
            busy(false);
            App.focusAfter.restore(saveTok, h.shell.titleEl);
          }
        })
        .catch(function (err) {
          // Keep the trace for DevTools; log the error only, never the payload.
          console.error('provider save failed', err);
          var fe = App.api.fieldErrors(err, ['name']);
          h.name.setError(fe.fields.name || null); h.shell.setError(fe.text || '');
          busy(false);
          App.focusAfter.defer(null);
          App.focusAfter.restore(saveTok, h.shell.saveButton);
          if (fe.fields.name) nameInput.focus();
        });
    }

    // ── Test (edit only) ────────────────────────────────────────────
    function setTestResult(state, text, reauth) {
      h.testStatus.set(state, text);
      var label = h.testStatus.el.lastChild;
      if (reauth) label.setAttribute('data-testid', 'plan-test-reauth');
      else label.removeAttribute('data-testid');
      h.testStatus.el.hidden = false;
    }

    function onTestClick() {
      var testBtn = h.shell.testButton;
      setTestResult('pending', 'Testing…');
      // Recorded before the disable below (M25 F6 L1b, DD2).
      var testTok = App.focusAfter.begin(testBtn);
      testBtn.disabled = true;
      fetch('/api/providers/' + encodeURIComponent(provider.id) + '/test', { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function (result) {
          testBtn.disabled = false;
          App.focusAfter.restore(testTok, testBtn);
          if (result.status === 'ok') {
            setTestResult('success', result.detail || 'Connected');
            App.ui.flash('Connection successful');
            if (h.modelsCtl) h.modelsCtl.refresh();
          } else if (result.status === 'warning') {
            // Reachable but non-functional (e.g. openrouter with no key).
            setTestResult('warning', result.detail || 'Warning');
            App.ui.flash('Connection reachable, action required', { error: true });
            if (h.modelsCtl) h.modelsCtl.refresh();
          } else if (result.status === 'reauth_required') {
            // anthropic-plan only (M19 F01 L03): renewal is no longer possible.
            // EXPLICIT branch: never the generic failure below. This line is the
            // one revoked signal; the standing affordance is the connected
            // state's Re-authenticate control.
            setTestResult('danger', result.detail ||
              'Re-authentication required — use Re-authenticate in the Anthropic account section to sign in again.', true);
            App.ui.flash('Re-authentication required', { error: true });
          } else {
            setTestResult('danger', result.detail || 'Failed');
            App.ui.flash('Connection failed', { error: true });
          }
        })
        .catch(function (err) {
          testBtn.disabled = false;
          App.focusAfter.restore(testTok, testBtn);
          setTestResult('danger', err.message || 'Request failed');
          App.ui.flash('Connection test error', { error: true });
        });
    }

    // ── Delete (edit only) ──────────────────────────────────────────
    // Agent-usage pre-gate on the first click: a provider that agents use is
    // blocked (a sibling banner, not inside the button), else the zone arms.
    var deleteBlockTimer = null;
    function beforeDeleteArm(proceed) {
      fetch('/api/providers/' + encodeURIComponent(provider.id) + '/agents')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var agents = data.agents || [];
          if (agents.length > 0) {
            h.danger.setNotice('Used by: ' + agents.join(', '));
            h.danger.setDisabled(true);
            if (deleteBlockTimer) clearTimeout(deleteBlockTimer);
            deleteBlockTimer = setTimeout(function () {
              h.danger.setDisabled(false);
              h.danger.setNotice(null);
            }, 3000);
          } else {
            proceed();
          }
        })
        .catch(function () {
          // Network failure on the agent-usage check: fail open and arm anyway.
          proceed();
        });
    }

    function doDelete(revertFn) {
      fetch('/api/providers/' + encodeURIComponent(provider.id), { method: 'DELETE' })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Delete failed'); });
          App.store.invalidate('providers');
          App.ui.flash('Provider deleted');
          if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
        })
        .catch(function (err) {
          revertFn();
          App.ui.flash(err.message, { error: true });
        });
    }
  }

  // ── Claude Plan (Token) expiry line (sortie 03 DD6) ───────────────────
  var PLAN_TOKEN_TYPE = 'anthropic-plan-token';
  var DAY_MS = 86400000;
  var SOON_MS = 30 * DAY_MS;
  var EXPIRY_LED = { ok: 'success', soon: 'warning', past: 'danger' };

  /* Pure: the expiry line's state and wording from the server-stamped dates
     (ISO strings) and a clock reading. `past` when now >= expires, `soon`
     when expires - now <= 30 days, else `ok`. Dates are formatted in the
     operator zone by App.time.formatDate. Returns null for unparseable dates. */
  function planTokenExpiry(setAtIso, expiresIso, nowMs) {
    var setMs = Date.parse(setAtIso);
    var expiresMs = Date.parse(expiresIso);
    if (isNaN(setMs) || isNaN(expiresMs)) return null;
    var setText = window.App.time.formatDate(new Date(setMs));
    var expiresText = window.App.time.formatDate(new Date(expiresMs));
    if (nowMs >= expiresMs) {
      return { state: 'past', text: 'This token may have expired (around ' + expiresText + '). Run claude setup-token and paste a new token.' };
    }
    if (expiresMs - nowMs <= SOON_MS) {
      return { state: 'soon', text: 'Expires around ' + expiresText + '. Run claude setup-token and paste a new token.' };
    }
    return { state: 'ok', text: 'Token added ' + setText + ' \u00b7 expires around ' + expiresText };
  }
  window.App.studio.planTokenExpiry = planTokenExpiry;

  /* Fill (or hide) the expiry line from the last saved provider row. Shown
     only for a saved token-type row with a stamp while the type select still
     reads the token type. DOM APIs only. */
  function renderTokenExpiry(host, row, selectedType) {
    if (!host) return;
    host.replaceChildren();
    var info = null;
    if (row && row.type === PLAN_TOKEN_TYPE && selectedType === PLAN_TOKEN_TYPE &&
        row.token_set_at && row.token_expires_around) {
      info = planTokenExpiry(row.token_set_at, row.token_expires_around, Date.now());
    }
    if (!info) { host.hidden = true; return; }
    // The status line: ok is a success LED, soon a warning, past a danger. Its
    // own data-state follows the token's wording (ok | soon | past).
    var line = App.ui.status({ testid: 'provider-token-expiry' });
    line.set(EXPIRY_LED[info.state], info.text);
    line.el.setAttribute('data-state', info.state);
    host.appendChild(line.el);
    host.hidden = false;
  }

  // ── Anthropic plan sign-in (M19 F01 L03) ──────────────────────────────
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

  function getFormSnapshot(h) {
    var data = {};
    for (var i = 0; i < h.fieldEls.length; i++) {
      var el = h.fieldEls[i];
      // Checkbox-aware: read .checked for checkboxes (the thinking_enabled
      // toggle), .value otherwise. Without this the checkbox is invisible to
      // the dirty machinery (Save never enables).
      data[el.dataset.field] = el.type === 'checkbox' ? el.checked : el.value;
    }
    return JSON.stringify(data);
  }

  /* Validate and collect the payload from the control handles; returns null and
     calls setError when invalid. An unmodified pre-filled (masked) API key is
     sent as the MASKED_SENTINEL so the backend preserves the stored key. */
  function collectFormData(h, callbacks, originalMaskedApiKey, isEdit, provider, setError) {
    var name = h.name.control.value.trim();
    if (!name) {
      setError('Name is required.');
      return null;
    }
    var selectedType = h.type.control.value;
    if (!selectedType) {
      setError('Type is required.');
      return null;
    }
    var defaults = (callbacks.getTypeDefaults && callbacks.getTypeDefaults(selectedType)) || {};
    var baseUrl = h.baseUrl.control.value.trim();
    if (!defaults.showBaseUrl) baseUrl = defaults.base_url || '';
    if (!baseUrl && defaults.showBaseUrl) {
      setError('Base URL is required.');
      return null;
    }
    var apiKey = h.secret.input.value;
    /* Trim whitespace BEFORE the truthy check so a paste like "  sk-x  "
       canonicalizes to "sk-x" client-side, and a whitespace-only paste
       collapses to null instead of silently round-tripping to a 401. The
       backend validator does the same (defense in depth). */
    if (apiKey !== null) apiKey = apiKey.trim();
    if (!apiKey) apiKey = null;
    if (isEdit && originalMaskedApiKey && apiKey === originalMaskedApiKey) {
      apiKey = MASKED_SENTINEL;
    }
    var payload = { name: name, type: selectedType, base_url: baseUrl, api_key: apiKey };

    /* Config-preservation seed. The backend's update_provider does
       existing.model_copy(update=data), a field-level REPLACE, not a deep merge.
       So whatever `config` this sends becomes the ENTIRE stored config; any key
       the UI does not render (config/env-only response_format + stop) would be
       silently wiped on every Save. Seed from a shallow clone of the existing
       config (edit mode) so the blocks below only overlay the fields they own. */
    payload.config = (isEdit && provider && provider.config) ? Object.assign({}, provider.config) : {};

    // Ollama Context window (config.num_ctx): REQUIRED and always persisted (the
    // field is pre-filled with the default, so a blank means the operator cleared
    // it). Validated client-side (the server re-validates): non-empty, a positive
    // whole number.
    if (defaults.showNumCtx) {
      var numCtxRaw = h.numCtx.control.value.trim();
      if (!numCtxRaw) {
        setError('Context window is required.');
        return null;
      }
      var numCtxVal = Number(numCtxRaw);
      if (!Number.isInteger(numCtxVal) || numCtxVal <= 0) {
        setError('Context window must be a positive whole number.');
        return null;
      }
      payload.config.num_ctx = numCtxVal;
    }

    // Extended thinking (config.thinking_enabled): collected only when shown
    // (Anthropic). Always persist the explicit bool.
    if (defaults.showThinkingEnabled) {
      payload.config.thinking_enabled = !!h.thinking.control.checked;
    }

    // Reasoning effort (config.reasoning_effort): collected only when shown
    // (reasoning-capable types). The empty string is a valid, harmless value (the
    // server-side _coerce_effort('') falls through to None).
    if (defaults.showReasoningEffort) {
      payload.config.reasoning_effort = h.effort.control.value;
    }

    return payload;
  }

  window.App.studio.renderProviderEditor = renderProviderEditor;
})();
