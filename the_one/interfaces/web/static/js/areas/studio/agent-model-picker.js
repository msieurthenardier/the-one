// App.studio.agentModelPicker -- the agent editor's provider/model picker wiring
// (M31 F2 L03, DD1): the model list fetch (with its abort + live-provider race
// guards), the capability and context chips, the provider-change side effects,
// dirty-tracking listeners and the Ollama VRAM check. Moved verbatim out of
// studio.js; a factory studio calls once in init:
//
//   var picker = App.studio.agentModelPicker.create(ctx);
//
// ctx (studio -> module): self, state, editorEl, formData (the agent-form-data
// handle: checkDirty and getFormSnapshot, so the async model fetch re-takes the
// dirty baseline through the same functions the editor uses).
//
// handle (module -> studio): wireEditorEvents(isCreate, cfg), fetchModelsForProvider(id),
// renderModelCapabilities().
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var self = ctx.self;
    var state = ctx.state;
    var editorEl = ctx.editorEl;
    var getFormSnapshot = ctx.formData.getFormSnapshot;
    var checkDirty = ctx.formData.checkDirty;

    function optionNode(value, label, flags) {
      var o = document.createElement('option');
      o.value = value;
      o.textContent = label;
      if (flags && flags.disabled) o.disabled = true;
      if (flags && flags.selected) o.selected = true;
      return o;
    }

    // Capability lookup keyed by model id. Populated by fetchModelsForProvider
    // and consumed by renderModelCapabilities on change. Reset per fetch so
    // a provider switch doesn't bleed stale caps into the new dropdown.
    var modelCapsBy = {};
    // F6.5 L04: parallel cache for the per-model context-window value
    // returned by /api/providers/{id}/models. Same lifecycle as modelCapsBy.
    var modelCtxBy = {};

    function fmtCtxTokens(n) {
      if (typeof n !== 'number' || !(n > 0)) return null;
      if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
      if (n >= 1000) return (n / 1000).toFixed(0) + 'k';
      return String(n);
    }

    function renderModelCapabilities() {
      var capsEl = editorEl.querySelector('.model-capabilities');
      var selectEl = editorEl.querySelector('#studio-model');
      if (!capsEl || !selectEl) return;
      var modelId = selectEl.value;
      var caps = modelCapsBy[modelId];
      var ctx = modelCtxBy[modelId];
      var renderer = window.App.studio && window.App.studio.renderCapabilityChips;
      var chips = (modelId && renderer && caps !== undefined && caps !== null)
        ? renderer(caps)
        : null;
      var ctxLabel = fmtCtxTokens(ctx);
      capsEl.textContent = '';
      if (chips) {
        var capsLabel = document.createElement('span');
        capsLabel.className = 'model-capabilities-label';
        capsLabel.textContent = 'Capabilities:';
        capsEl.appendChild(capsLabel);
        capsEl.appendChild(document.createTextNode(' '));
        capsEl.appendChild(chips);
      }
      if (ctxLabel) {
        if (chips) capsEl.appendChild(document.createTextNode(' \u00b7 '));
        var ctxText = document.createElement('span');
        ctxText.className = 'model-capabilities-label';
        ctxText.textContent = 'Max context:';
        capsEl.appendChild(ctxText);
        capsEl.appendChild(document.createTextNode(' '));
        var ctxChip = document.createElement('span');
        ctxChip.className = 'model-ctx-chip';
        ctxChip.setAttribute('data-testid', 'model-ctx-chip');
        ctxChip.textContent = ctxLabel;
        capsEl.appendChild(ctxChip);
      }
    }

    // Race-condition guard for fetchModelsForProvider (review I6). Rapid
    // provider switching fires concurrent fetches; without a guard a slow
    // earlier response silently clobbers a fresh later one. Two layers:
    //   1. AbortController cancels the in-flight request on the next call.
    //   2. providerId equality check on resolution drops any response that
    //      no longer matches the live selection (covers AbortController
    //      gaps and any future fetch path that doesn't honor signals).
    var _modelsFetchController = null;
    var _activeProviderId = null;
    // M31 F2 L06a: the liveness guard of the latest wireEditorEvents call (the
    // controller's mount token plus its panel-build generation). Each async
    // callback captures the guard that was current when it started and drops its
    // result once that mount or panel build is gone.
    var currentGuard = function () { return true; };

    function fetchModelsForProvider(providerId) {
      var selectEl = editorEl.querySelector('#studio-model');
      var loadingEl = editorEl.querySelector('.model-loading');
      if (!selectEl) return;

      // Cancel any in-flight fetch from a prior provider selection.
      if (_modelsFetchController) {
        try { _modelsFetchController.abort(); } catch (_) { /* noop */ }
      }
      _modelsFetchController = (typeof AbortController !== 'undefined')
        ? new AbortController()
        : null;
      _activeProviderId = providerId;
      var fetchProviderId = providerId;
      var fetchSignal = _modelsFetchController ? _modelsFetchController.signal : undefined;

      var currentVal = selectEl.dataset.pendingValue || selectEl.value;
      var live = currentGuard;

      if (!providerId) {
        selectEl.replaceChildren(optionNode('', 'Select a provider first',
          { disabled: true, selected: true }));
        if (loadingEl) loadingEl.textContent = '';
        modelCapsBy = {};
        modelCtxBy = {};
        renderModelCapabilities();
        return;
      }

      if (loadingEl) loadingEl.textContent = 'Loading models…';

      fetch('/api/providers/' + encodeURIComponent(providerId) + '/models', {
        signal: fetchSignal,
      })
        .then(function (r) {
          if (!r.ok) throw new Error('Failed');
          return r.json();
        })
        .then(function (models) {
          // Drop the response if the user has since switched providers.
          // Without this guard a slow A-fetch arriving after B-fetch
          // would clobber the picker with A's models while B is selected.
          if (!live() || _activeProviderId !== fetchProviderId) return;
          modelCapsBy = {};
          modelCtxBy = {};
          var optNodes = [optionNode('', 'Choose a model', { disabled: true })];
          for (var i = 0; i < models.length; i++) {
            var modelId = models[i].id || models[i].name;
            optNodes.push(optionNode(modelId, modelId, { selected: modelId === currentVal }));
            // Capability cache shape: dict<model_id, list|null>.
            // Both ollama (`capabilities`) and openrouter (`supported_parameters`,
            // server-side aliased to `capabilities`) flow through this single
            // path. Empty list \u2192 null (fail-open: "fetched but no caps known"
            // \u2192 no chip, mirrors openrouter_api.get_model_capabilities).
            // Absent field \u2192 cache entry stays unset \u2192 no chip.
            var capsRaw = models[i].capabilities;
            if (Array.isArray(capsRaw) && capsRaw.length > 0) {
              modelCapsBy[modelId] = capsRaw;
            } else if (Array.isArray(capsRaw) && capsRaw.length === 0) {
              modelCapsBy[modelId] = null;
            }
            // F6.5 L04: context_length is the per-model max-context-tokens
            // surfaced via /api/providers/{id}/models. Number > 0 \u2192 chip;
            // null/missing \u2192 no chip (operator sees nothing rather than a
            // potentially-wrong value).
            var ctxRaw = models[i].context_length;
            if (typeof ctxRaw === 'number' && ctxRaw > 0) {
              modelCtxBy[modelId] = ctxRaw;
            }
          }
          selectEl.replaceChildren.apply(selectEl, optNodes);
          // Surface a previously-saved or carried-over value that isn't
          // in the freshly fetched list as a visible "(custom)" option —
          // a clear cue that the selection won't match a known model
          // under this provider, without silently wiping it.
          if (currentVal && !selectEl.querySelector('option[value="' + CSS.escape(currentVal) + '"]')) {
            selectEl.appendChild(optionNode(currentVal, currentVal + ' (custom)', { selected: true }));
          }
          if (loadingEl) {
            loadingEl.textContent = models.length === 0 ? 'No models discovered' : '';
          }
          delete selectEl.dataset.pendingValue;
          renderModelCapabilities();
          // The dirty baseline (renderEditor) was taken before this list
          // arrived, so the select's value moved under it. While the user has
          // changed nothing, re-take it: otherwise an edit that is reverted
          // still reads dirty (Save enabled, "Unsaved changes" shown).
          if (!state.dirty) {
            state.snapshot = getFormSnapshot();
            checkDirty();
          }
        })
        .catch(function (err) {
          // Aborted fetches (provider changed mid-flight) are not errors —
          // skip the failure UI so the next fetch's success can paint
          // cleanly without a flash of "Failed to load models".
          if (err && err.name === 'AbortError') return;
          if (!live() || _activeProviderId !== fetchProviderId) return;
          var failOpt = document.createElement('option');
          failOpt.value = '';
          failOpt.disabled = true;
          failOpt.selected = true;
          failOpt.textContent = 'Failed to load models';
          selectEl.replaceChildren(failOpt);
          if (loadingEl) loadingEl.textContent = '';
          modelCapsBy = {};
          modelCtxBy = {};
          renderModelCapabilities();
        });
    }

    function recomputeTestDisabled() {
      var providerSelect = editorEl.querySelector('#studio-provider');
      var testBtn = editorEl.querySelector('[data-testid="test-provider-btn"]');
      if (!testBtn) return;
      testBtn.disabled = !providerSelect || !providerSelect.value;
    }

    function wireEditorEvents(isCreate, cfg, isCurrent) {
      currentGuard = typeof isCurrent === 'function' ? isCurrent : function () { return true; };
      // Dirty tracking on all inputs (skips disabled Advanced stubs).
      // General is mounted once per identity and its controls call the dirty check
      // themselves (flagged _dirtyWired); the sweep covers the controls of the
      // panels that are still rebuilt, each only once (a spurious check is cheap:
      // checkDirty compares the form against its snapshot).
      var inputs = editorEl.querySelectorAll(
        'input:not([type=checkbox]):not([type=radio]):not([type=button]), textarea, select, .tool-toggle');
      for (var i = 0; i < inputs.length; i++) {
        if (inputs[i].disabled || inputs[i]._dirtyWired) continue;
        inputs[i]._dirtyWired = true;
        inputs[i].addEventListener('input', checkDirty);
        inputs[i].addEventListener('change', checkDirty);
      }

      // Provider change → repopulate model select, clear VRAM warning,
      // recompute Test btn. Model picker is always a <select> (browsers
      // give us free type-ahead via the native dropdown), so no element
      // swap is needed across provider types.
      var providerSelect = editorEl.querySelector('#studio-provider');
      // The listeners are attached once per General mount (the controls outlive a
      // patch); the initial fetch below runs on every call, which is how setAgent's
      // provider/model reset is refetched.
      if (providerSelect && !providerSelect._pickerWired) {
        providerSelect._pickerWired = true;
        providerSelect.addEventListener('change', function () {
          var selectedProviderId = providerSelect.value;
          var modelEl = editorEl.querySelector('#studio-model');
          if (modelEl) {
            // Carry the current choice across the switch so
            // fetchModelsForProvider can surface it as "(custom)" when the new
            // provider doesn't list it (squawk 0156). It is consumed (and
            // deleted) by that fetch's success path.
            if (modelEl.value) modelEl.dataset.pendingValue = modelEl.value;
            else delete modelEl.dataset.pendingValue;
            modelEl.selectedIndex = 0;
          }
          clearVramWarning();
          fetchModelsForProvider(selectedProviderId);
          recomputeTestDisabled();
        });
      }
      if (providerSelect && cfg.provider_config_id) {
        var modelSelect = editorEl.querySelector('#studio-model');
        if (modelSelect && cfg.llm_model) modelSelect.dataset.pendingValue = cfg.llm_model;
        fetchModelsForProvider(cfg.provider_config_id);
      }

      // Model change → debounced VRAM check + capability panel refresh.
      var modelInput = editorEl.querySelector('#studio-model');
      if (modelInput) {
        if (!modelInput._pickerWired) {
          modelInput._pickerWired = true;
          modelInput.addEventListener('change', debouncedVramCheck);
          modelInput.addEventListener('change', renderModelCapabilities);
        }
        if (cfg.llm_model && cfg.provider_config_id) {
          debouncedVramCheck();
        }
      }
    }

    var formatBytes = App.formatBytes;
    var vramCheckTimer = null;

    function getSelectedProviderType() {
      var providerSelect = editorEl.querySelector('#studio-provider');
      if (!providerSelect || !providerSelect.value) return null;
      for (var i = 0; i < self._allProviders.length; i++) {
        if (String(self._allProviders[i].id) === String(providerSelect.value)) {
          return self._allProviders[i];
        }
      }
      return null;
    }

    function clearVramWarning() {
      var el = editorEl.querySelector('.studio-vram-warning');
      if (el) {
        el.textContent = '';
        el.classList.remove('visible');
      }
    }

    function checkVramForModel() {
      var live = currentGuard;
      if (!live()) return;
      var provider = getSelectedProviderType();
      if (!provider || provider.type !== 'ollama') {
        clearVramWarning();
        return;
      }

      var modelInput = editorEl.querySelector('#studio-model');
      if (!modelInput || !modelInput.value.trim()) {
        clearVramWarning();
        return;
      }

      var modelName = modelInput.value.trim();
      var providerId = provider.id;

      Promise.all([
        fetch('/api/providers/' + encodeURIComponent(providerId) + '/models/status')
          .then(function (r) { return r.ok ? r.json() : []; }),
        fetch('/api/providers/' + encodeURIComponent(providerId) + '/models')
          .then(function (r) { return r.ok ? r.json() : []; })
      ])
        .then(function (results) {
          if (!live()) return;
          var running = results[0] || [];
          var models = results[1] || [];

          for (var i = 0; i < running.length; i++) {
            var runName = running[i].name || running[i].model || '';
            if (runName === modelName || runName.split(':')[0] === modelName.split(':')[0]) {
              clearVramWarning();
              return;
            }
          }

          var modelSize = 0;
          for (var j = 0; j < models.length; j++) {
            var mId = models[j].id || models[j].name || '';
            if (mId === modelName || mId.split(':')[0] === modelName.split(':')[0]) {
              modelSize = models[j].size || 0;
              break;
            }
          }

          if (!modelSize) {
            clearVramWarning();
            return;
          }

          var totalLoaded = 0;
          var loadedCount = running.length;
          for (var k = 0; k < running.length; k++) {
            totalLoaded += running[k].size_vram || 0;
          }

          var warningEl = editorEl.querySelector('.studio-vram-warning');
          if (warningEl) {
            var msg = 'This model requires ~' + formatBytes(modelSize) + '.';
            if (loadedCount > 0) {
              msg += ' Currently ' + formatBytes(totalLoaded) +
                ' loaded across ' + loadedCount + ' model' + (loadedCount !== 1 ? 's' : '') + '.';
            }
            warningEl.textContent = msg;
            warningEl.classList.add('visible');
          }
        })
        .catch(function () {
          if (live()) clearVramWarning();
        });
    }

    function debouncedVramCheck() {
      if (vramCheckTimer) clearTimeout(vramCheckTimer);
      vramCheckTimer = setTimeout(checkVramForModel, 500);
    }

    return {
      wireEditorEvents: wireEditorEvents,
      fetchModelsForProvider: fetchModelsForProvider,
      renderModelCapabilities: renderModelCapabilities
    };
  }

  window.App.studio.agentModelPicker = { create: create };
})();
