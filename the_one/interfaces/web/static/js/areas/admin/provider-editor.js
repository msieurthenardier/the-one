// App.admin.renderProviderEditor — provider-editor scaffold (F6 leg 03).
//
// Builds the editor surface mirroring studio's agent-editor (F5 leg 03):
//   <div class="editor-header">
//     <div class="editor-header-text">
//       <div class="editor-breadcrumb">Settings / <a href="#settings/providers">Providers</a></div>
//       <h2 class="editor-title" tabindex="-1">{name | "New Provider"}</h2>
//       <p class="editor-subtitle">{type · base_url}</p>  (edit only)
//     </div>
//     <div class="form-actions">
//       <span class="editor-unsaved" role="status"></span>
//       <button class="cancel-btn">Cancel</button>  (disabled while clean, edit only)
//       <button class="save-btn" disabled>{Save | Create}</button>
//       <button class="test-provider-btn">Test</button>  (edit only)
//       <span class="editor-error"></span>
//     </div>
//   </div>
//   <div class="editor-section">
//     <div class="section-title">Connection</div>
//     {name + type + base_url + api_key fields}
//     <div class="test-result"></div>
//   </div>
//   <div class="editor-section">                    (edit only)
//     <div class="section-title">Available models</div>
//     <p class="admin-pf-models-help">…Agents link…</p>
//     <div class="provider-models"></div>
//   </div>
//   <div class="editor-section danger-zone">        (edit only)
//     <div class="section-title danger-zone-title">Danger Zone</div>
//     <button class="delete-btn">Delete Provider</button>
//   </div>
//
// callbacks: { onCancel, onSaveSuccess, onDeleteSuccess, onDirtyChange, getTypeDefaults }
//
// M25 F3 L5b (flight DD2/DD7): the editor mounts in the Providers page's item
// section, below the table. Back is retired: the breadcrumb (inserted after
// innerHTML, its "Providers" segment a link to #settings/providers) is the
// visible way to close the item, routed by admin.js. The title is an h2 (the
// Settings page header owns the page's one h1; flight-end review) and carries
// tabindex="-1" so admin.js can move focus to it when an intent opens the
// item. The unsaved caption is a stable span at the start of .form-actions
// whose text checkDirty sets or clears (the same value it reports through
// onDirtyChange, which feeds the App.nav dirty source).
//
// Editor Delete uses App.confirmDelete (canonical destructive-confirm helper)
// since F6 leg 04. The agent-usage hard-block remains as a pre-confirmDelete
// gate (no confirm flow when agents reference the provider).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  function renderProviderEditor(container, provider, providerTypes, callbacks) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !provider;
    var name = isCreate ? 'New Provider' : (provider.name || '');

    // ── Header HTML ─────────────────────────────────────────────────
    var html = '';
    html += '<div class="editor-header">';
    html += '<div class="editor-header-text">';
    html += '<h2 class="editor-title" tabindex="-1">' + escapeHtml(name) + '</h2>';
    if (!isCreate) {
      var subtitleParts = [escapeHtml(provider.type)];
      if (provider.base_url) subtitleParts.push(escapeHtml(provider.base_url));
      html += '<p class="editor-subtitle">' + subtitleParts.join(' · ') + '</p>';
    }
    html += '</div>';

    // ── Action cluster ──────────────────────────────────────────────
    // M25 F3 L5b (DD2): Back is retired; the cluster opens with the stable
    // unsaved caption (checkDirty sets or clears its text). Cancel on the
    // create form abandons creation (DD8), so it is enabled from first
    // render, clean or dirty (the M25 F3 behavior-gate fix); in edit mode it
    // reverts, and checkDirty keeps it disabled while there is nothing to
    // revert.
    html += '<div class="form-actions">';
    html += '<span class="editor-unsaved" role="status" data-testid="editor-unsaved"></span>';
    html += '<button type="button" class="btn-outlined-primary cancel-btn" data-testid="cancel-provider-btn"' + (isCreate ? '' : ' disabled') + '>Cancel</button>';
    html += '<button type="button" class="btn-filled-primary save-btn" data-testid="save-provider-btn" disabled>' + (isCreate ? 'Create' : 'Save') + '</button>';
    if (!isCreate) {
      html += '<button type="button" class="btn-outlined-primary test-provider-btn" data-testid="test-connection-btn">Test</button>';
    }
    html += '<span class="editor-error"></span>';
    html += '</div>';
    html += '</div>'; // .editor-header

    // ── Connection section ──────────────────────────────────────────
    html += '<div class="editor-section">';
    html += '<div class="section-title">Connection</div>';
    html += renderConnectionFields(provider, providerTypes, callbacks);
    html += '<div class="test-result" aria-live="polite"></div>';
    html += '</div>';

    // ── Anthropic Account section (M19 F01 L03) ─────────────────────
    // Rendered for ALL modes/types but hidden unless the selected type's
    // TYPE_DEFAULTS carries showPlanSignIn (the anthropic-plan type) —
    // same is-hidden toggle pattern as the base_url/api_key rows. The
    // body is populated by wirePlanSignIn; nothing inside carries a
    // data-field attribute (no-trap rule: the dirty snapshot selects
    // [data-field], so the sign-in machinery stays out of it entirely).
    html += renderPlanSignInShell(provider, callbacks);

    // ── Models section (edit only) ──────────────────────────────────
    if (!isCreate) {
      html += '<div class="editor-section">';
      html += '<div class="section-title">Available models</div>';
      html += '<p class="admin-pf-models-help" data-testid="provider-models-help"></p>';
      html += '<div class="provider-models"></div>';
      html += '</div>';
    }

    // ── Danger Zone section (edit only) ─────────────────────────────
    if (!isCreate) {
      html += '<div class="editor-section danger-zone">';
      html += '<div class="section-title danger-zone-title">Danger Zone</div>';
      html += '<button type="button" class="btn-muted-destructive delete-btn" data-testid="delete-provider-btn" data-name="' + escapeAttr(provider.name || '') + '"><span data-confirm-title>Delete Provider</span></button>';
      // Hard-block message banner — shown when the provider is in use by
      // ≥1 agents. Sibling of the button (NOT inside it) so long agent-name
      // lists don't deform the button. aria-live="assertive" announces
      // when revealed. F6 HAT refinement.
      html += '<div class="action-blocked-message banner banner-error" data-testid="delete-blocked-message" role="status" aria-live="assertive" hidden></div>';
      html += '</div>';
    }

    container.innerHTML = html;

    // The breadcrumb (M25 F3 DD2): "Settings / Providers", inserted with DOM
    // APIs after the markup is in place (this editor is string-built), as the
    // first child of .editor-header-text, in edit and create modes. Its
    // "Providers" segment links to the page root (the DD2 refinement): with
    // Back retired it is the visible way to close the item. admin.js routes
    // the click (the router's guard asks once about a dirty editor) and
    // focuses the item's row after the close (DD8).
    var headerText = container.querySelector('.editor-header-text');
    var crumb = document.createElement('div');
    crumb.className = 'editor-breadcrumb';
    crumb.appendChild(document.createTextNode('Settings / '));
    var crumbLink = document.createElement('a');
    crumbLink.className = 'editor-breadcrumb-link';
    crumbLink.setAttribute('href', window.App.router.href({ destination: 'settings', section: 'providers' }));
    crumbLink.setAttribute('data-testid', 'editor-breadcrumb-link');
    crumbLink.textContent = 'Providers';
    crumb.appendChild(crumbLink);
    headerText.insertBefore(crumb, headerText.firstChild);

    // DD10: the Models list is information, not a picker. Its one line of help
    // is built with DOM APIs (this editor is string-built) so "Agents" can link.
    var modelsHelp = container.querySelector('.admin-pf-models-help');
    if (modelsHelp) {
      modelsHelp.appendChild(document.createTextNode('Each agent chooses one of these in its Model section. '));
      var agentsLink = document.createElement('a');
      agentsLink.setAttribute('href', window.App.router.href({ destination: 'agents' }));
      agentsLink.setAttribute('data-testid', 'provider-models-agents-link');
      agentsLink.textContent = 'Agents';
      modelsHelp.appendChild(agentsLink);
    }

    wireEditorEvents(container, provider, providerTypes, callbacks);

    // Mount the Models panel synchronously in edit mode (mirrors agent-editor's
    // synchronous General-tab mount so tests find selectors immediately).
    if (!isCreate && window.App.admin.renderProviderModels) {
      var modelsHost = container.querySelector('.provider-models');
      if (modelsHost) {
        window.App.admin.renderProviderModels(modelsHost, provider);
      }
    }
  }

  function renderConnectionFields(provider, providerTypes, callbacks) {
    /* Render the four field rows: name, type, base_url, api_key.
       Reuses pre-leg-03 admin.js:314-351 markup verbatim (DOM/selectors
       preserved for backward compat with tests that locate by #pf-name etc.). */
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !provider;
    var type = isCreate ? '' : provider.type;
    var defaults = (callbacks.getTypeDefaults && callbacks.getTypeDefaults(type)) || { base_url: '', showBaseUrl: false, showApiKey: false };

    var html = '';
    // Name — stacked `.field-group` (label above control), M17 F6 L1 migration
    // from the label-left `.field-row admin-pf-row` layout.
    html += '<div class="field-group">';
    html += '<label for="pf-name">Name</label>';
    html += '<input class="field-input admin-pf-input" id="pf-name" data-field="name" value="' + escapeAttr(isCreate ? '' : provider.name) + '" placeholder="My Provider" />';
    html += '</div>';

    // Type
    html += '<div class="field-group">';
    html += '<label for="pf-type">Type</label>';
    html += '<select class="field-input field-select admin-pf-input admin-pf-select" id="pf-type" data-field="type">';
    if (isCreate) html += '<option value="" disabled selected>Select a provider…</option>';
    for (var t = 0; t < providerTypes.length; t++) {
      var pt = providerTypes[t];
      html += '<option value="' + escapeAttr(pt.value) + '"' + (!isCreate && type === pt.value ? ' selected' : '') + '>' + escapeHtml(pt.label) + '</option>';
    }
    html += '</select>';
    html += '</div>';

    // Base URL
    var baseUrlValue = isCreate ? defaults.base_url : provider.base_url;
    html += '<div class="field-group admin-pf-base-url' + (defaults.showBaseUrl ? '' : ' is-hidden') + '">';
    html += '<label for="pf-base-url">Base URL</label>';
    html += '<input class="field-input admin-pf-input" id="pf-base-url" data-field="base_url" value="' + escapeAttr(baseUrlValue || '') + '" placeholder="https://..." />';
    html += '</div>';

    // API Key (canonical .api-key-wrap + .api-key-eye)
    var apiKeyValue = isCreate ? '' : (provider.api_key || '');
    html += '<div class="field-group admin-pf-api-key' + (defaults.showApiKey ? '' : ' is-hidden') + '">';
    html += '<label for="pf-api-key">API Key</label>';
    html += '<div class="api-key-wrap">';
    html += '<input class="field-input admin-pf-input admin-pf-password" id="pf-api-key" type="password" data-field="api_key" value="' + escapeAttr(apiKeyValue) + '" placeholder="sk-..." />';
    html += '<button class="api-key-eye" type="button" title="Show/Hide" aria-label="Show password">' + window.App.icon('eye') + '</button>';
    html += '</div>';
    html += '</div>';

    // Context Window (config.num_ctx) — Ollama-only override (F09-05). Rides in
    // the free-form config dict (config.num_ctx), same pattern as the OpenRouter
    // referer/title config fields. Required + always carries a value: pre-filled
    // with the default window (DEFAULT_NUM_CTX, mirrors _DEFAULT_NUM_CTX in
    // ollama_provider.py) for new providers, or the provider's stored value when
    // editing one that has it. Description is a tooltip on a focusable info-icon
    // button. M17 F6 L1: migrated to the stacked `.field-group` + shared
    // `.field-group-label` vocabulary — label + info-icon sit on one line ABOVE
    // the control (the `.field-group-label` primitive keeps the <button> a
    // SIBLING of the <label>, never nested). The `.admin-pf-num-ctx` marker
    // class is preserved so the type-driven show/hide (wireEditorEvents) keeps
    // working; the info-icon stays a descendant of that row so the a11y wiring
    // (`aria-describedby` → `#pf-num-ctx-desc`) is unchanged.
    var DEFAULT_NUM_CTX = 32768;
    var numCtx = (!isCreate && provider.config && provider.config.num_ctx != null) ? provider.config.num_ctx : DEFAULT_NUM_CTX;
    var numCtxDesc = 'A larger window allows longer conversations but will slow down on partial-GPU setups because fewer layers fit in VRAM';
    var numCtxIcon = (window.App && window.App.icon) ? window.App.icon('info') : '';
    if (!numCtxIcon) numCtxIcon = 'ⓘ';
    html += '<div class="field-group admin-pf-num-ctx' + (defaults.showNumCtx ? '' : ' is-hidden') + '">';
    html += '<div class="field-group-label">';
    html += '<label for="pf-num-ctx">Context Window</label>';
    html += '<button type="button" class="field-info-icon" title="' + escapeAttr(numCtxDesc) + '" aria-label="' + escapeAttr(numCtxDesc) + '">' + numCtxIcon + '</button>';
    html += '</div>';
    html += '<span id="pf-num-ctx-desc" class="visually-hidden">' + escapeHtml(numCtxDesc) + '</span>';
    html += '<input class="field-input admin-pf-input" id="pf-num-ctx" type="number" min="1" step="1" required data-field="config.num_ctx" aria-describedby="pf-num-ctx-desc" value="' + escapeAttr(String(numCtx)) + '" />';
    html += '</div>';

    // Extended thinking (config.thinking_enabled) — Anthropic-only on/off toggle
    // (F10-06). Rides the free-form config dict (config.thinking_enabled), same
    // pattern as num_ctx. Off by default: a fresh Anthropic provider has thinking
    // disabled; the operator opts in. The native checkbox .checked bool is written
    // straight to payload.config.thinking_enabled — no numeric validation; the
    // backend's _coerce_bool (anthropic_provider.py) reads the key.
    //
    // HAT inline fix (F10-07): rendered as the canonical iOS-style toggle switch
    // (`.tool-enable-switch` + `.tool-enable-switch-track`, CSS in admin.css under
    // `.area-admin`/`.area-studio`) — the same widget the tools editor/grid and
    // the per-agent admit-DMs toggle use, for cross-screen consistency. The REAL
    // <input type="checkbox"> (id/data-field/`field-input` preserved) is
    // visually-hidden inside the switch label but stays keyboard-operable and
    // drives the collect + dirty machinery via `.checked`. The info-icon follows
    // the LABEL (`label (i) field` order) to match the established icon-tooltip
    // pattern, not the num_ctx `label | input | ⓘ` order.
    var thinkingEnabled = !!(!isCreate && provider.config && provider.config.thinking_enabled);
    var teDesc = 'When on, a model reasons step-by-step before answering (adaptive thinking). Requires Claude Sonnet 4.6 or newer.';
    var teIcon = (window.App && window.App.icon) ? window.App.icon('info') : '';
    if (!teIcon) teIcon = 'ⓘ';
    // M17 F6 L1 DOCUMENTED LABEL-LEFT EXCEPTION: the text fields above migrated
    // to the stacked `.field-group` vocabulary, but the Extended-thinking toggle
    // stays on the label-left `.field-row` layout (`label | ⓘ | switch` on one
    // row). Stacking a single iOS-style toggle under its own label reads worse
    // than the compact label-left form (the F5 chrome-row precedent). The
    // `.admin-pf-thinking-enabled` marker class is preserved for the type-driven
    // show/hide.
    html += '<div class="field-row admin-pf-row admin-pf-thinking-enabled' + (defaults.showThinkingEnabled ? '' : ' is-hidden') + '">';
    html += '<label for="pf-thinking-enabled">Extended thinking</label>';
    html += '<button type="button" class="field-info-icon" title="' + escapeAttr(teDesc) + '" aria-label="' + escapeAttr(teDesc) + '">' + teIcon + '</button>';
    html += '<span id="pf-thinking-enabled-desc" class="visually-hidden">' + escapeHtml(teDesc) + '</span>';
    html += '<label class="tool-enable-switch">';
    html += '<input class="field-input" id="pf-thinking-enabled" type="checkbox" data-field="config.thinking_enabled" aria-describedby="pf-thinking-enabled-desc"' + (thinkingEnabled ? ' checked' : '') + ' />';
    html += '<span class="tool-enable-switch-track" aria-hidden="true"></span>';
    html += '</label>';
    html += '</div>';

    // Reasoning effort (config.reasoning_effort) — F11-06. Rides the free-form
    // config dict (config.reasoning_effort), same pattern as num_ctx. Shown for
    // reasoning-capable provider types (anthropic, anthropic-plan, openai,
    // openrouter, ollama, openai-compatible — see
    // TYPE_DEFAULTS.showReasoningEffort in admin.js).
    // Optional: the empty "Provider default" option means omit the key
    // entirely (server-side _coerce_effort('') -> None), so an operator who
    // never touches this field gets prior behavior unchanged.
    var reasoningEffort = (!isCreate && provider.config && provider.config.reasoning_effort) ? provider.config.reasoning_effort : '';
    var reDesc = 'Guides how much the model reasons before answering (reasoning-capable models). Leave on Provider default to omit.';
    var reIcon = (window.App && window.App.icon) ? window.App.icon('info') : '';
    if (!reIcon) reIcon = 'ⓘ';
    html += '<div class="field-group admin-pf-reasoning-effort' + (defaults.showReasoningEffort ? '' : ' is-hidden') + '">';
    html += '<div class="field-group-label">';
    html += '<label for="pf-reasoning-effort">Reasoning Effort</label>';
    html += '<button type="button" class="field-info-icon" title="' + escapeAttr(reDesc) + '" aria-label="' + escapeAttr(reDesc) + '">' + reIcon + '</button>';
    html += '</div>';
    html += '<span id="pf-reasoning-effort-desc" class="visually-hidden">' + escapeHtml(reDesc) + '</span>';
    html += '<select class="field-input field-select admin-pf-input admin-pf-select" id="pf-reasoning-effort" data-field="config.reasoning_effort" aria-describedby="pf-reasoning-effort-desc">';
    html += '<option value=""' + (reasoningEffort === '' ? ' selected' : '') + '>Provider default</option>';
    html += '<option value="low"' + (reasoningEffort === 'low' ? ' selected' : '') + '>low</option>';
    html += '<option value="medium"' + (reasoningEffort === 'medium' ? ' selected' : '') + '>medium</option>';
    html += '<option value="high"' + (reasoningEffort === 'high' ? ' selected' : '') + '>high</option>';
    html += '</select>';
    html += '</div>';

    return html;
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

  function renderPlanSignInShell(provider, callbacks) {
    var isCreate = !provider;
    var type = isCreate ? '' : provider.type;
    var defaults = (callbacks.getTypeDefaults && callbacks.getTypeDefaults(type)) || {};
    var html = '';
    html += '<div class="editor-section admin-pf-plan-signin' + (defaults.showPlanSignIn ? '' : ' is-hidden') + '">';
    html += '<div class="section-title">Anthropic Account</div>';
    html += '<div class="plan-signin-body"></div>';
    html += '</div>';
    return html;
  }

  function wirePlanSignIn(container, provider, requestCreateSave) {
    var isEdit = !!provider;
    var body = container.querySelector('.admin-pf-plan-signin .plan-signin-body');
    if (!body) return;

    // Local sub-state: non-null while the consent (URL + code paste) UI is
    // shown. Cleared on success/reset; survives nothing (an editor reload
    // mid-flow is fine — the backend keeps the pending verifier and a
    // re-click of Sign in replaces it cleanly).
    var awaitingUrl = null;

    function isConnected() {
      return !!(isEdit && provider && provider.oauth_active);
    }

    function errorEl() {
      return body.querySelector('[data-testid="plan-signin-error"]');
    }

    function showError(msg) {
      var el = errorEl();
      if (!el) return;
      el.textContent = msg;
      el.removeAttribute('hidden');
    }

    function clearError() {
      var el = errorEl();
      if (!el) return;
      el.textContent = '';
      el.setAttribute('hidden', '');
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
          window.App.showFlash(container, 'Signed in to Anthropic');
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
          window.App.showFlash(container, 'Connection reset');
        })
        .catch(function (err) {
          revertFn();
          showError(err.message || String(err));
        });
    }

    function buildSignedOutBlock() {
      var block = document.createElement('div');
      block.className = 'plan-signin-start';
      var desc = document.createElement('p');
      desc.className = 'plan-signin-desc';
      desc.textContent = 'Sign in with your Anthropic account to use your Claude plan. No API key is needed.';
      block.appendChild(desc);
      var row = document.createElement('div');
      row.className = 'plan-signin-actions';
      var signInBtn = document.createElement('button');
      signInBtn.type = 'button';
      signInBtn.className = 'btn-outlined-primary';
      signInBtn.setAttribute('data-testid', 'plan-signin-btn');
      signInBtn.textContent = 'Sign in with Anthropic';
      row.appendChild(signInBtn);
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
      block.appendChild(row);
      return block;
    }

    function buildConnectedRow() {
      var row = document.createElement('div');
      row.className = 'plan-connected-row';
      var led = document.createElement('span');
      led.className = 'indicator-led indicator-led--success';
      led.setAttribute('aria-hidden', 'true');
      row.appendChild(led);
      var label = document.createElement('span');
      label.className = 'plan-connected-text';
      label.setAttribute('data-testid', 'plan-connected-indicator');
      label.textContent = 'Connected to Anthropic';
      row.appendChild(label);
      var reauthBtn = document.createElement('button');
      reauthBtn.type = 'button';
      reauthBtn.className = 'btn-outlined-primary';
      reauthBtn.setAttribute('data-testid', 'plan-reauth-btn');
      reauthBtn.textContent = 'Re-authenticate';
      reauthBtn.addEventListener('click', function () { startFlow(reauthBtn); });
      row.appendChild(reauthBtn);
      var resetBtn = document.createElement('button');
      resetBtn.type = 'button';
      resetBtn.className = 'btn-outlined-primary';
      resetBtn.setAttribute('data-testid', 'plan-reset-btn');
      resetBtn.innerHTML = '<span data-confirm-title>Reset connection</span>';
      resetBtn.addEventListener('click', function () {
        // Two-step inline confirm — the canonical destructive-confirm
        // helper (MCP reset-connection precedent). Existing tokens are
        // cleared locally only; no upstream revocation.
        window.App.confirmDelete(resetBtn, doReset, { confirmLabel: 'Confirm Reset?' });
      });
      row.appendChild(resetBtn);
      return row;
    }

    function buildConsentBlock(url) {
      var block = document.createElement('div');
      block.className = 'plan-signin-consent';
      block.setAttribute('data-testid', 'plan-signin-consent');

      var desc = document.createElement('p');
      desc.className = 'plan-signin-desc';
      desc.textContent = 'Approve access in the sign-in window — if none opened, open or copy the link below in any browser. Then paste the code shown after approval.';
      block.appendChild(desc);

      var urlRow = document.createElement('div');
      urlRow.className = 'plan-signin-url-row';
      var urlInput = document.createElement('input');
      urlInput.className = 'field-input plan-signin-url';
      urlInput.setAttribute('data-testid', 'plan-signin-url');
      urlInput.readOnly = true;
      urlInput.value = url;
      urlInput.setAttribute('aria-label', 'Sign-in page URL');
      urlRow.appendChild(urlInput);
      var openBtn = document.createElement('button');
      openBtn.type = 'button';
      openBtn.className = 'btn-outlined-primary';
      openBtn.setAttribute('data-testid', 'plan-signin-open-btn');
      openBtn.textContent = 'Open sign-in page';
      openBtn.addEventListener('click', function () {
        // Direct user click — gesture context restored, so this popup is
        // NOT subject to the post-fetch blocking noted in openConsentPopup.
        openConsentPopup(url);
      });
      urlRow.appendChild(openBtn);
      var copyBtn = document.createElement('button');
      copyBtn.type = 'button';
      copyBtn.className = 'btn-outlined-primary';
      copyBtn.setAttribute('data-testid', 'plan-signin-copy-btn');
      copyBtn.textContent = 'Copy';
      copyBtn.addEventListener('click', function () {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(url).then(function () {
            window.App.showFlash(container, 'Sign-in link copied');
          }, function () { fallbackCopy(); });
        } else {
          fallbackCopy();
        }
        function fallbackCopy() {
          urlInput.select();
          try { document.execCommand('copy'); } catch (e) { /* selection remains for manual copy */ }
          window.App.showFlash(container, 'Sign-in link copied');
        }
      });
      urlRow.appendChild(copyBtn);
      block.appendChild(urlRow);

      var codeRow = document.createElement('div');
      codeRow.className = 'plan-code-row';
      var codeInput = document.createElement('input');
      codeInput.className = 'field-input plan-code-input';
      codeInput.setAttribute('data-testid', 'plan-code-input');
      codeInput.setAttribute('placeholder', 'Paste the code here');
      codeInput.setAttribute('aria-label', 'Sign-in code');
      codeRow.appendChild(codeInput);
      var submitBtn = document.createElement('button');
      submitBtn.type = 'button';
      submitBtn.className = 'btn-filled-primary';
      submitBtn.setAttribute('data-testid', 'plan-code-submit-btn');
      submitBtn.textContent = 'Confirm code';
      submitBtn.addEventListener('click', function () { submitCode(codeInput, submitBtn); });
      codeRow.appendChild(submitBtn);
      block.appendChild(codeRow);

      return block;
    }

    function renderState() {
      body.innerHTML = '';
      if (isConnected()) body.appendChild(buildConnectedRow());
      if (awaitingUrl) {
        // Re-authenticate renders the consent flow OVER the connected
        // state — existing tokens survive until the new exchange succeeds.
        body.appendChild(buildConsentBlock(awaitingUrl));
      } else if (!isConnected()) {
        body.appendChild(buildSignedOutBlock());
      }
      var err = document.createElement('div');
      err.className = 'plan-signin-error banner banner-error';
      err.setAttribute('data-testid', 'plan-signin-error');
      err.setAttribute('role', 'status');
      err.setAttribute('aria-live', 'polite');
      err.setAttribute('hidden', '');
      body.appendChild(err);
    }

    renderState();

    // Consume the create→edit auto-start handoff (HAT fix): this edit-mode
    // mount is the re-render that immediately follows a sign-in-initiated
    // create — start the OAuth flow now. One-shot: cleared before starting.
    // A just-created provider is never connected, so the signed-out block
    // (and its sign-in button) is on screen when this fires.
    if (isEdit && provider && pendingAutoSignInId === provider.id) {
      pendingAutoSignInId = null;
      startFlow(body.querySelector('[data-testid="plan-signin-btn"]'));
    }
  }

  function getFormSnapshot(container) {
    var data = {};
    var fields = container.querySelectorAll('[data-field]');
    for (var i = 0; i < fields.length; i++) {
      var el = fields[i];
      // Checkbox-aware: read .checked for checkboxes (the thinking_enabled
      // toggle), .value otherwise. Without this the checkbox is invisible to
      // the dirty machinery (Save never enables). Backward-compatible for all
      // existing .value-based fields.
      data[el.dataset.field] = el.type === 'checkbox' ? el.checked : el.value;
    }
    return JSON.stringify(data);
  }

  function wireEditorEvents(container, provider, providerTypes, callbacks) {
    /* Wire: type-change show/hide, eye-toggle, dirty tracking, Cancel,
       Save, Test, Delete (Back retired in M25 F3 L5b). Replaces pre-leg-03
       admin.js:385-558 with these substitutions:
         - .admin-pf-cancel        → .cancel-btn
         - .admin-pf-save          → .save-btn
         - .admin-pf-test          → .test-provider-btn
         - .admin-pf-eye           → .api-key-eye
         - .admin-pf-error         → .editor-error
         - .admin-pf-test-result   → .test-result
         - .admin-pf-testing       → .test-result-pending (span class)
         - .admin-pf-test-ok       → .test-result-ok      (span class)
         - .admin-pf-test-fail     → .test-result-fail    (span class)
       Adds: MASKED_SENTINEL capture (originalMaskedApiKey); dirty-tracking
       shim (snapshot + checkDirty); .delete-btn handler
       with agent-usage hard-block + inline two-step. Sub-module owns the
       fetch (POST/PUT/DELETE/test); onSaveSuccess + onDeleteSuccess
       callbacks notify orchestrator AFTER successful response. */
    var isEdit = !!provider;
    var snapshot = getFormSnapshot(container);
    var dirty = false;
    /* MASKED_SENTINEL preservation (preserves admin.js:466-470 behavior).
       Capture the originally pre-filled (masked) api-key value so we can
       detect "user did not modify the field" on submit. In create mode this
       is empty. */
    var MASKED_SENTINEL = '__MASKED__';
    var originalMaskedApiKey = isEdit ? (provider.api_key || '') : '';

    function checkDirty() {
      var current = getFormSnapshot(container);
      dirty = current !== snapshot;
      var saveBtn = container.querySelector('.save-btn');
      var cancelBtn = container.querySelector('.cancel-btn');
      if (saveBtn) saveBtn.disabled = !dirty;
      // Cancel follows `dirty` in edit mode only; the create form's Cancel
      // (abandon creation, DD8) stays enabled whether or not anything was
      // typed.
      if (cancelBtn) cancelBtn.disabled = isEdit && !dirty;
      // The header's unsaved caption (M25 F3 DD2) follows the same value.
      var unsavedEl = container.querySelector('.editor-unsaved');
      if (unsavedEl) unsavedEl.textContent = dirty ? 'Unsaved changes' : '';
      // F6 leg 04 bridge: notify orchestrator's mirror so the leave guard
      // (App.nav: the breadcrumb, a Settings nav link, any routed leave,
      // beforeunload) can read the same logical state.
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(dirty);
    }

    /* Wire input/change listeners on all .field-input + .field-select */
    var inputs = container.querySelectorAll('.field-input, .field-select');
    for (var i = 0; i < inputs.length; i++) {
      inputs[i].addEventListener('input', checkDirty);
      inputs[i].addEventListener('change', checkDirty);
    }

    /* Type-change: show/hide base_url + api_key rows + reset base_url
       default. Does NOT clobber api_key so values are preserved across
       provider-type switches. */
    var typeSelect = container.querySelector('[data-field="type"]');
    var baseUrlRow = container.querySelector('.admin-pf-base-url');
    var baseUrlInput = container.querySelector('[data-field="base_url"]');
    var apiKeyRow = container.querySelector('.admin-pf-api-key');
    var numCtxRow = container.querySelector('.admin-pf-num-ctx');
    var thinkingEnabledRow = container.querySelector('.admin-pf-thinking-enabled');
    var reasoningEffortRow = container.querySelector('.admin-pf-reasoning-effort');
    var planSignInSection = container.querySelector('.admin-pf-plan-signin');
    if (typeSelect) {
      typeSelect.addEventListener('change', function () {
        var defaults = (callbacks.getTypeDefaults && callbacks.getTypeDefaults(typeSelect.value)) || {};
        baseUrlRow.classList.toggle('is-hidden', !defaults.showBaseUrl);
        apiKeyRow.classList.toggle('is-hidden', !defaults.showApiKey);
        if (numCtxRow) numCtxRow.classList.toggle('is-hidden', !defaults.showNumCtx);
        if (thinkingEnabledRow) thinkingEnabledRow.classList.toggle('is-hidden', !defaults.showThinkingEnabled);
        if (reasoningEffortRow) reasoningEffortRow.classList.toggle('is-hidden', !defaults.showReasoningEffort);
        if (planSignInSection) planSignInSection.classList.toggle('is-hidden', !defaults.showPlanSignIn);
        baseUrlInput.value = defaults.base_url || '';
        checkDirty();
      });
    }

    /* Anthropic plan sign-in section (M19 F01 L03) — mounted for every
       editor instance; visibility is type-driven (above). Owns its own
       OAuth fetches; deliberately outside the dirty machinery. performSave
       (hoisted declaration below) is handed in so the create-mode sign-in
       button can run the auto-save-then-start path (HAT fix). */
    wirePlanSignIn(container, provider, performSave);

    /* Eye toggle. */
    var eyeBtn = container.querySelector('.api-key-eye');
    var passwordInput = container.querySelector('.admin-pf-password');
    if (eyeBtn && passwordInput) {
      eyeBtn.addEventListener('click', function () {
        if (passwordInput.type === 'password') {
          passwordInput.type = 'text';
          eyeBtn.innerHTML = window.App.icon('eye-off');
          eyeBtn.setAttribute('aria-label', 'Hide password');
        } else {
          passwordInput.type = 'password';
          eyeBtn.innerHTML = window.App.icon('eye');
          eyeBtn.setAttribute('aria-label', 'Show password');
        }
      });
    }

    /* Cancel: edit mode reverts in place; create mode delegates to onCancel
       (the orchestrator discards and returns to the page root). The create
       form's Cancel is enabled from first render, so onCancel runs on a
       pristine form as well as a dirty one. */
    var cancelBtn = container.querySelector('.cancel-btn');
    /* Focus after an in-place action (M25 F6 L1b, DD2): the title and Save are
       re-resolved when the focus timer fires. */
    function focusTitle() { return container.querySelector('.editor-title'); }
    function focusSave() { return container.querySelector('.save-btn'); }
    if (cancelBtn) {
      cancelBtn.addEventListener('click', function () {
        if (isEdit) {
          var cancelTok = App.focusAfter.begin(cancelBtn);
          // Revert to snapshot.
          var snap = JSON.parse(snapshot);
          var fields2 = container.querySelectorAll('[data-field]');
          for (var j = 0; j < fields2.length; j++) {
            var el2 = fields2[j];
            // Checkbox-aware revert: restore .checked (bool) for checkboxes,
            // .value otherwise. Mirrors the getFormSnapshot checkbox branch.
            if (el2.type === 'checkbox') {
              el2.checked = !!snap[el2.dataset.field];
            } else {
              el2.value = snap[el2.dataset.field] || '';
            }
          }
          dirty = false;
          checkDirty();
          App.focusAfter.restore(cancelTok, focusTitle);
        } else if (callbacks.onCancel) {
          callbacks.onCancel();
        }
      });
    }

    /* Save: editor sub-module owns the fetch. Orchestrator's
       onSaveSuccess callback handles state mutation + URL update.
       Factored into performSave (HAT fix) so the create-mode plan sign-in
       button reuses the EXACT same path — validation, payload construction
       (seed-before-overlay), error rendering. onCreateSuccess (optional)
       fires only on a successful CREATE, and BEFORE onSaveSuccess so the
       pendingAutoSignInId handoff is in place when the create→edit
       re-render (a microtask behind onSaveSuccess) mounts the new editor. */
    function performSave(onCreateSuccess) {
      var errorEl = container.querySelector('.editor-error');
      errorEl.textContent = '';
      var payload = collectFormData(container, callbacks, originalMaskedApiKey, MASKED_SENTINEL, isEdit, provider);
      if (!payload) return; // validation failed; collectFormData wrote error
      var saveTok = App.focusAfter.begin(focusSave());
      var url = isEdit ? '/api/providers/' + encodeURIComponent(provider.id) : '/api/providers';
      var method = isEdit ? 'PUT' : 'POST';
      // fetchJson flattens a 422 detail list to "field: message" (squawk 0112).
      App.api.fetchJson(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(function (updated) {
          App.store.invalidate('providers');
          window.App.showFlash(container, isEdit ? 'Provider saved' : 'Provider created');
          if (!isEdit && onCreateSuccess) onCreateSuccess(updated);
          // Create re-mounts the editor in edit mode asynchronously (the
          // orchestrator's `ready` promise): park the restore for that mount.
          if (!isEdit) App.focusAfter.defer(saveTok, focusTitle);
          if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, !isEdit);
          // For create→edit transition the orchestrator re-renders the
          // editor with the new provider — closure is replaced. The
          // snapshot reset below only matters for the edit→edit case
          // where the editor stays mounted.
          if (isEdit) {
            // Re-render the WHOLE display-only header text block (title +
            // subtitle) from the freshly saved provider. On edit→edit the
            // editor stays mounted and nothing else refreshes the header,
            // so an edited Name / Base URL / Type would otherwise leave the
            // title and the `type · base_url` subtitle stale. These nodes carry
            // no data-field, so getFormSnapshot / dirty tracking are
            // unaffected — textContent-only writes.
            var titleEl = container.querySelector('.editor-title');
            if (titleEl) titleEl.textContent = updated.name || '';
            var subtitleEl = container.querySelector('.editor-subtitle');
            if (subtitleEl) {
              var subtitleParts = [updated.type];
              if (updated.base_url) subtitleParts.push(updated.base_url);
              subtitleEl.textContent = subtitleParts.join(' · ');
            }
            snapshot = getFormSnapshot(container);
            dirty = false;
            checkDirty();
            App.focusAfter.restore(saveTok, focusTitle);
          }
        })
        .catch(function (err) {
          // Surface the trace to DevTools so backend stacks (which
          // would otherwise die with the next click as errorEl.textContent
          // is overwritten) survive for debugging.
          console.error('provider save failed', err);
          errorEl.textContent = err.message || String(err);
          App.focusAfter.defer(null);
          App.focusAfter.restore(saveTok, focusSave);
        });
    }

    var saveBtn = container.querySelector('.save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', function () { performSave(); });
    }

    /* Test: only in edit mode. */
    var testBtn = container.querySelector('.test-provider-btn');
    if (testBtn && isEdit) {
      testBtn.addEventListener('click', function () {
        var resultEl = container.querySelector('.test-result');
        resultEl.innerHTML = '<span class="test-result-pending">Testing…</span>';
        // Recorded before the disable below (M25 F6 L1b, DD2).
        var testTok = App.focusAfter.begin(testBtn);
        testBtn.disabled = true;
        fetch('/api/providers/' + encodeURIComponent(provider.id) + '/test', { method: 'POST' })
          .then(function (r) { return r.json(); })
          .then(function (result) {
            testBtn.disabled = false;
            App.focusAfter.restore(testTok, testBtn);
            // Render via DOM API (textContent on a class-tagged span) so
            // operator-supplied detail text cannot break out of the
            // surrounding markup. Three states: ok / warning / error.
            var span = document.createElement('span');
            // Glyph prefixes (✓/⚠/✗) intentionally absent — the .test-result-*
            // ::before LED retrofit from M08F2L5 already conveys status visually.
            if (result.status === 'ok') {
              span.className = 'test-result-ok';
              span.textContent = result.detail || 'Connected';
              resultEl.replaceChildren(span);
              window.App.showFlash(container, 'Connection successful');
              var modelsHost = container.querySelector('.provider-models');
              if (modelsHost && window.App.admin.renderProviderModels) {
                window.App.admin.renderProviderModels(modelsHost, provider);
              }
            } else if (result.status === 'warning') {
              // Reachable but non-functional (e.g., openrouter with no key).
              // Distinct LED color from the green ok state cues incomplete config.
              span.className = 'test-result-warning';
              span.textContent = result.detail || 'Warning';
              resultEl.replaceChildren(span);
              window.App.showFlash(container, 'Connection reachable, action required', true);
              var modelsHost2 = container.querySelector('.provider-models');
              if (modelsHost2 && window.App.admin.renderProviderModels) {
                window.App.admin.renderProviderModels(modelsHost2, provider);
              }
            } else if (result.status === 'reauth_required') {
              // anthropic-plan only (M19 F01 L03): renewal is no longer
              // possible (refresh token revoked/expired). EXPLICIT branch —
              // must never fall into the generic else-fail below. This
              // rendered message is the one revoked signal; the standing
              // affordance is the connected state's Re-authenticate control.
              span.className = 'test-result-warning';
              span.setAttribute('data-testid', 'plan-test-reauth');
              span.textContent = result.detail ||
                'Re-authentication required — use Re-authenticate in the Anthropic Account section to sign in again.';
              resultEl.replaceChildren(span);
              window.App.showFlash(container, 'Re-authentication required', true);
            } else {
              span.className = 'test-result-fail';
              span.textContent = result.detail || 'Failed';
              resultEl.replaceChildren(span);
              window.App.showFlash(container, 'Connection failed', true);
            }
          })
          .catch(function (err) {
            testBtn.disabled = false;
            App.focusAfter.restore(testTok, testBtn);
            resultEl.innerHTML = '<span class="test-result-fail">' + window.App.escapeHtml(err.message || 'Request failed') + '</span>';
            window.App.showFlash(container, 'Connection test error', true);
          });
      });
    }

    /* Delete: only in edit mode. Agent-usage hard-block pre-gate +
       App.confirmDelete for the confirm flow (F6 leg 04). */
    var deleteBtn = container.querySelector('.delete-btn');
    if (deleteBtn && isEdit) {
      var deleteHardBlockTimer = null;
      var blockedMsgEl = container.querySelector('.action-blocked-message');

      function doDelete(btn, revertFn) {
        fetch('/api/providers/' + encodeURIComponent(provider.id), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Delete failed'); });
            App.store.invalidate('providers');
            window.App.showFlash(container, 'Provider deleted');
            if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
          })
          .catch(function (err) {
            revertFn();
            window.App.showFlash(container, 'Error: ' + err.message, true);
          });
      }

      deleteBtn.addEventListener('click', function () {
        // OQ2 RESOLUTION: explicit "already armed → commit" branch removed.
        // App.confirmDelete (confirm.js:58-67) handles the second-click
        // commit internally when the button already has the .confirm-delete
        // class. The agent-usage pre-gate fetch on the second click is
        // wasted work but functionally harmless (result is ignored on the
        // commit path because the helper's class check beats us to
        // onConfirm).
        //
        // Pre-gate: agent-usage hard-block.
        fetch('/api/providers/' + encodeURIComponent(provider.id) + '/agents')
          .then(function (r) { return r.json(); })
          .then(function (data) {
            var agents = data.agents || [];
            if (agents.length > 0) {
              // Hard-block: surface the message in a sibling banner (NOT
              // inside the button, which would deform with long agent-name
              // lists). Button text stays "Delete Provider".
              if (blockedMsgEl) {
                blockedMsgEl.textContent = 'Used by: ' + agents.join(', ');
                blockedMsgEl.removeAttribute('hidden');
              }
              deleteBtn.disabled = true;
              if (deleteHardBlockTimer) clearTimeout(deleteHardBlockTimer);
              deleteHardBlockTimer = setTimeout(function () {
                deleteBtn.disabled = false;
                if (blockedMsgEl) {
                  blockedMsgEl.setAttribute('hidden', '');
                  blockedMsgEl.textContent = '';
                }
              }, 3000);
            } else {
              // No agent usage: arm via App.confirmDelete.
              window.App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' });
            }
          })
          .catch(function () {
            // Network failure on agent-usage check: fail open — arm anyway.
            window.App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' });
          });
      });
    }
  }

  function collectFormData(container, callbacks, originalMaskedApiKey, MASKED_SENTINEL, isEdit, provider) {
    /* Validate + collect payload. Mirrors pre-leg-03 admin.js:440-477 (Save
       handler's prologue) but returns null + writes error when invalid.
       Preserves the MASKED_SENTINEL substitution from admin.js:466-470. */
    var errorEl = container.querySelector('.editor-error');
    var nameInput = container.querySelector('[data-field="name"]');
    var name = nameInput.value.trim();
    if (!name) {
      errorEl.textContent = 'Name is required.';
      return null;
    }
    var typeSelect = container.querySelector('[data-field="type"]');
    var selectedType = typeSelect.value;
    if (!selectedType) {
      errorEl.textContent = 'Type is required.';
      return null;
    }
    var defaults = (callbacks.getTypeDefaults && callbacks.getTypeDefaults(selectedType)) || {};
    var baseUrlInput = container.querySelector('[data-field="base_url"]');
    var baseUrl = baseUrlInput.value.trim();
    if (!defaults.showBaseUrl) baseUrl = defaults.base_url || '';
    if (!baseUrl && defaults.showBaseUrl) {
      errorEl.textContent = 'Base URL is required.';
      return null;
    }
    var apiKeyInput = container.querySelector('[data-field="api_key"]');
    var apiKey = apiKeyInput ? apiKeyInput.value : null;
    /* Trim whitespace BEFORE the truthy check so a paste like "  sk-x  "
       canonicalizes to "sk-x" client-side, and a whitespace-only paste
       collapses to null instead of silently round-tripping to a 401.
       The backend Pydantic validator does the same on the server side
       (defense in depth + UX: avoids the round-trip to discover the
       whitespace was a no-op). */
    if (apiKey !== null) apiKey = apiKey.trim();
    if (!apiKey) apiKey = null;
    /* MASKED_SENTINEL: if editing and the user did not modify the pre-filled
       (masked) value, send the sentinel so the backend preserves the existing
       stored key. Mirrors admin.js:466-470. */
    if (isEdit && originalMaskedApiKey && apiKey === originalMaskedApiKey) {
      apiKey = MASKED_SENTINEL;
    }
    var payload = { name: name, type: selectedType, base_url: baseUrl, api_key: apiKey };

    /* Config-preservation seed (Phase-2d review fix, F11). The backend's
       update_provider does existing.model_copy(update=data) — a field-level
       REPLACE, not a deep merge. So whatever `config` object this function
       sends becomes the ENTIRE stored config; any key the UI doesn't render
       (e.g. config/env-only response_format + stop, DD6) would otherwise be
       silently wiped on every Save. Seed from a shallow clone of the existing
       provider config (edit mode) so the type-specific blocks below only
       overlay the fields they own, preserving everything else. Create mode
       has no existing provider, so it starts from {}. */
    payload.config = (isEdit && provider && provider.config) ? Object.assign({}, provider.config) : {};

    // OpenRouter optional ranking-header inputs (Task 9) — read values,
    // validate client-side (server re-validates), drop empty values so
    // the saved config doesn't carry empty-string keys. Overlays onto the
    // seeded payload.config (add/delete only the keys this branch owns)
    // rather than replacing it outright.
    if (selectedType === 'openrouter') {
      var refererInput = container.querySelector('[data-field="config.referer"]');
      var titleInput = container.querySelector('[data-field="config.title"]');
      var orReferer = refererInput ? refererInput.value.trim() : '';
      var orTitle = titleInput ? titleInput.value.trim() : '';

      if (orReferer && /[\r\n\x00]/.test(orReferer)) {
        errorEl.textContent = 'App URL contains an invalid control character.';
        return null;
      }
      if (orReferer && !/^https?:\/\//i.test(orReferer)) {
        errorEl.textContent = 'App URL must start with http:// or https://.';
        return null;
      }
      if (orTitle && /[\r\n\x00]/.test(orTitle)) {
        errorEl.textContent = 'App Name contains an invalid control character.';
        return null;
      }

      if (orReferer) payload.config.referer = orReferer; else delete payload.config.referer;
      if (orTitle) payload.config.title = orTitle; else delete payload.config.title;
    }

    // Ollama Context Window (config.num_ctx) — F09-05. Now REQUIRED and always
    // persisted (the field is pre-filled with the default, so a blank means the
    // operator cleared it). Same config.* precedent: parse + validate
    // client-side (server re-validates / coerces); reject empty + non-positive +
    // non-integer.
    if (defaults.showNumCtx) {
      var numCtxInput = container.querySelector('[data-field="config.num_ctx"]');
      var numCtxRaw = numCtxInput ? numCtxInput.value.trim() : '';
      if (!numCtxRaw) {
        errorEl.textContent = 'Context Window is required.';
        return null;
      }
      var numCtxVal = Number(numCtxRaw);
      if (!Number.isInteger(numCtxVal) || numCtxVal <= 0) {
        errorEl.textContent = 'Context Window must be a positive whole number.';
        return null;
      }
      payload.config = payload.config || {};
      payload.config.num_ctx = numCtxVal;
    }

    // Anthropic Extended thinking (config.thinking_enabled) — F10-06. Collected
    // only when the field is shown (anthropic). Always persist the explicit bool
    // (matches num_ctx's always-persist; makes the edit round-trip deterministic).
    // The native .checked is a real bool; no validation/coercion.
    if (defaults.showThinkingEnabled) {
      var teInput = container.querySelector('[data-field="config.thinking_enabled"]');
      payload.config = payload.config || {};
      payload.config.thinking_enabled = !!(teInput && teInput.checked);
    }

    // Reasoning effort (config.reasoning_effort) — F11-06. Collected only when
    // the field is shown (reasoning-capable types). Always persist the
    // explicit value (matches thinking_enabled's always-persist; makes the
    // edit round-trip deterministic). The empty string is a valid, harmless
    // value — the server-side _coerce_effort('') falls through to None.
    if (defaults.showReasoningEffort) {
      var reInput = container.querySelector('[data-field="config.reasoning_effort"]');
      payload.config = payload.config || {};
      payload.config.reasoning_effort = reInput ? reInput.value : '';
    }

    return payload;
  }

  window.App.admin.renderProviderEditor = renderProviderEditor;
})();
