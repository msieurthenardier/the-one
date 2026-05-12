// App.admin.renderProviderModels — provider-models panel (F6 leg 03).
//
// Top-level dispatch on provider.type:
//   - 'ollama'  → Ollama lifecycle UI (refresh / pull / list / unload / load /
//                 delete-row + VRAM summary + streaming pull progress).
//   - other     → Basic model list (Refresh + GET /api/providers/{id}/models).
//
// Migrated verbatim from pre-leg-03 admin.js:562-1021 with these substitutions:
//   - showAdminFlash(msg, isError)            → window.App.showFlash(container, msg, isError)
//   - <span class="admin-pf-test-fail">       → <span class="test-result-fail">
//                                               (canonical class; the per-area
//                                               .admin-pf-test-fail CSS rule
//                                               was deleted in F6 leg 03)
//
// All `.admin-pf-pull*` / `.admin-pf-vram*` / `.admin-pf-model*` selectors
// preserved (per-area scoping kept intentionally — Ollama-specific UI).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  var escapeHtml = window.App.escapeHtml;
  var escapeAttr = window.App.escapeAttr;

  // Render the Ollama capability list as a row of chips. `caps` is the
  // array returned by /api/show (e.g. ['completion', 'tools', 'vision']);
  // null means the capability lookup failed (network/missing model) and
  // we render nothing rather than misleadingly implying "no capabilities".
  // The `tools` capability gets a positive emphasis class; absence of
  // `tools` adds a muted "no tools" chip so the operator sees it at a glance.
  function renderCapabilityChips(caps) {
    if (!Array.isArray(caps) || caps.length === 0) return '';
    var chips = '';
    for (var i = 0; i < caps.length; i++) {
      chips += '<span class="chip cap-chip">' + escapeHtml(caps[i]) + '</span>';
    }
    if (caps.indexOf('tools') === -1) {
      chips += '<span class="chip cap-chip cap-chip-no-tools" ' +
        'title="This model does not support tool calling — agents will run in single-shot chat mode.">no tools</span>';
    }
    return '<span class="cap-chip-row">' + chips + '</span>';
  }

  // Exposed so Studio's model selector can reuse the same chip vocabulary.
  window.App.admin.renderCapabilityChips = renderCapabilityChips;

  function renderProviderModels(container, provider) {
    if (!provider || !provider.id) return;
    if (provider.type === 'ollama') {
      renderOllamaModels(provider.id, container);
    } else {
      renderBasicModels(provider.id, container);
    }
  }

  function renderBasicModels(providerId, modelsEl) {
    if (!modelsEl) return;

    modelsEl.innerHTML =
      '<div class="admin-pf-models-header">' +
        '<button class="btn-outlined-primary refresh-btn admin-pf-models-refresh">' + window.App.icon('refresh-cw') + ' Refresh</button>' +
      '</div>' +
      '<div class="admin-pf-models-list" aria-live="polite"><span class="admin-loading">Loading models…</span></div>';

    var refreshBtn = modelsEl.querySelector('.admin-pf-models-refresh');
    refreshBtn.addEventListener('click', function () {
      renderBasicModels(providerId, modelsEl);
    });

    fetch('/api/providers/' + encodeURIComponent(providerId) + '/models')
      .then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Failed to load models'); });
        return r.json();
      })
      .then(function (models) {
        var listEl = modelsEl.querySelector('.admin-pf-models-list');
        if (!listEl) return;

        if (models.length === 0) {
          listEl.innerHTML = '<span class="empty-state admin-pf-models-empty">No models found.</span>';
          return;
        }

        var html = '';
        for (var i = 0; i < models.length; i++) {
          html += '<div class="admin-pf-model-item">' + escapeHtml(models[i].id || models[i].name) + '</div>';
        }
        listEl.innerHTML = html;
      })
      .catch(function (err) {
        var listEl = modelsEl.querySelector('.admin-pf-models-list');
        if (listEl) {
          listEl.innerHTML = '<span class="test-result-fail">' + escapeHtml(err.message || 'Failed to load models') + '</span>';
        }
      });
  }

  function renderOllamaModels(providerId, container) {
    if (!container) return;
    var formatBytes = window.App.formatBytes;

    container.innerHTML =
      '<div class="admin-pf-models-header">' +
        '<button class="btn-outlined-primary refresh-btn admin-pf-models-refresh">' + window.App.icon('refresh-cw') + ' Refresh</button>' +
      '</div>' +
      '<div class="admin-pf-pull-input">' +
        '<select class="field-input admin-pf-select admin-pf-pull-name" disabled>' +
          '<option value="">Loading library…</option>' +
        '</select>' +
        '<button class="btn-filled-primary btn-sm admin-pf-pull-go" disabled>Pull</button>' +
      '</div>' +
      '<div class="admin-pf-pull-progress is-hidden">' +
        '<div class="admin-pf-pull-fill"></div>' +
        '<span class="admin-pf-pull-text"></span>' +
        '<button class="admin-pf-pull-cancel" aria-label="Cancel pull">' + window.App.icon('x') + '</button>' +
      '</div>' +
      '<div class="admin-pf-pull-error is-hidden"></div>' +
      '<div class="admin-pf-vram-summary"></div>' +
      '<div class="admin-pf-models-list" aria-live="polite"><span class="admin-loading">Loading models…</span></div>';

    var refreshBtn = container.querySelector('.admin-pf-models-refresh');
    refreshBtn.addEventListener('click', function () {
      renderOllamaModels(providerId, container);
    });

    // Pull UI wiring
    var pullNameInput = container.querySelector('.admin-pf-pull-name');
    var pullGoBtn = container.querySelector('.admin-pf-pull-go');
    var pullProgress = container.querySelector('.admin-pf-pull-progress');
    var pullFill = container.querySelector('.admin-pf-pull-fill');
    var pullText = container.querySelector('.admin-pf-pull-text');
    var pullError = container.querySelector('.admin-pf-pull-error');

    var pullAbort = null;

    function loadLibraryOptions() {
      pullNameInput.disabled = true;
      pullNameInput.innerHTML = '<option value="">Loading library…</option>';
      fetch('/api/ollama-library/search')
        .then(function (r) { return r.ok ? r.json() : []; })
        .then(function (models) {
          if (!models.length) {
            pullNameInput.innerHTML = '<option value="">Library unavailable</option>';
            pullNameInput.disabled = true;
            return;
          }
          var html = '<option value="">Select a model…</option>';
          for (var i = 0; i < models.length; i++) {
            var sz = models[i].size && Number(models[i].size) > 0
              ? ' (' + formatBytes(Number(models[i].size)) + ')'
              : '';
            html += '<option value="' + escapeAttr(models[i].name) + '">' +
              escapeHtml(models[i].name) + escapeHtml(sz) + '</option>';
          }
          pullNameInput.innerHTML = html;
          pullNameInput.disabled = false;
        })
        .catch(function () {
          pullNameInput.innerHTML = '<option value="">Library unavailable</option>';
          pullNameInput.disabled = true;
        });
    }

    pullGoBtn.addEventListener('click', function () { startPull(); });

    pullNameInput.addEventListener('change', function () {
      pullGoBtn.disabled = !pullNameInput.value;
    });

    // Load the library on render so the dropdown is populated immediately.
    // Refresh re-enters renderOllamaModels which re-runs this.
    loadLibraryOptions();

    // Cancel button
    var pullCancelBtn = container.querySelector('.admin-pf-pull-cancel');
    pullCancelBtn.addEventListener('click', function () {
      if (pullAbort) {
        pullAbort.abort();
        pullAbort = null;
      }
      finishPull(false);
      window.App.showFlash(container, 'Pull cancelled');
    });

    function startPull() {
      var model = pullNameInput.value.trim();
      if (!model) return;

      pullAbort = new AbortController();
      pullGoBtn.disabled = true;
      pullBtn.disabled = true;
      pullNameInput.disabled = true;
      pullError.classList.add('is-hidden');
      pullProgress.classList.remove('is-hidden');
      pullFill.style.width = '0%';
      pullText.textContent = 'Pulling ' + escapeHtml(model) + '…';

      fetch('/api/providers/' + encodeURIComponent(providerId) + '/models/pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: model }),
        signal: pullAbort.signal
      })
        .then(function (resp) {
          if (!resp.ok) {
            return resp.json().then(function (e) { throw new Error(e.detail || 'Pull request failed'); });
          }
          var reader = resp.body.getReader();
          var decoder = new TextDecoder();
          var buffer = '';

          function read() {
            return reader.read().then(function (result) {
              if (result.done) {
                finishPull(true);
                return;
              }
              buffer += decoder.decode(result.value, { stream: true });
              var lines = buffer.split('\n');
              buffer = lines.pop();

              for (var i = 0; i < lines.length; i++) {
                var line = lines[i].trim();
                if (line.indexOf('data: ') === 0) {
                  try {
                    var evt = JSON.parse(line.substring(6));
                    if (evt.error) {
                      showPullError(evt.error);
                      return;
                    }
                    if (evt.status === 'success') {
                      finishPull(true);
                      return;
                    }
                    var pct = 0;
                    if (evt.total && evt.total > 0) {
                      pct = Math.round((evt.completed / evt.total) * 100);
                    }
                    pullFill.style.width = pct + '%';
                    pullText.textContent = escapeHtml(evt.status || '') + (pct > 0 ? ' — ' + pct + '%' : '');
                  } catch (parseErr) {
                    // skip unparseable lines
                  }
                }
              }
              return read();
            });
          }

          return read();
        })
        .catch(function (err) {
          if (err.name === 'AbortError') return; // cancelled by user
          showPullError(err.message || 'Pull failed');
        });
    }

    function showPullError(msg) {
      pullAbort = null;
      pullProgress.classList.add('is-hidden');
      pullError.classList.remove('is-hidden');
      pullError.textContent = escapeHtml(msg);
      pullGoBtn.disabled = false;
      pullNameInput.disabled = false;
    }

    function finishPull(success) {
      pullAbort = null;
      pullProgress.classList.add('is-hidden');
      pullGoBtn.disabled = false;
      pullNameInput.disabled = false;
      pullNameInput.value = '';
      if (success) {
        window.App.showFlash(container, 'Model pulled successfully');
        renderOllamaModels(providerId, container);
      }
    }

    // Fetch both endpoints in parallel
    var modelsPromise = fetch('/api/providers/' + encodeURIComponent(providerId) + '/models')
      .then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Failed to load models'); });
        return r.json();
      });

    var statusPromise = fetch('/api/providers/' + encodeURIComponent(providerId) + '/models/status')
      .then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Failed to load status'); });
        return r.json();
      });

    Promise.all([modelsPromise, statusPromise])
      .then(function (results) {
        var allModels = results[0];
        var runningModels = results[1];

        var listEl = container.querySelector('.admin-pf-models-list');
        var vramEl = container.querySelector('.admin-pf-vram-summary');
        if (!listEl || !vramEl) return;

        // Build set of running model names
        var runningNames = {};
        var totalVram = 0;
        for (var r = 0; r < runningModels.length; r++) {
          var rm = runningModels[r];
          var rname = rm.name || rm.model || '';
          runningNames[rname] = rm;
          if (rm.size_vram) totalVram += rm.size_vram;
        }

        // Capability lookup keyed by model name. Sourced from /models (which
        // enriches each entry with capabilities); /models/status doesn't
        // carry them, so the Running section also reads from this map.
        var capsBy = {};
        for (var ci = 0; ci < allModels.length; ci++) {
          var cm = allModels[ci];
          var cname = cm.name || cm.id || '';
          if (cname) capsBy[cname] = cm.capabilities || null;
        }

        // VRAM summary
        if (runningModels.length === 0) {
          vramEl.textContent = 'No models loaded';
        } else if (totalVram > 0) {
          vramEl.innerHTML = '<span class="admin-pf-vram-value">' + escapeHtml(formatBytes(totalVram)) + ' loaded</span>';
        } else {
          vramEl.textContent = 'VRAM info unavailable';
        }

        // Build model rows
        if (allModels.length === 0 && runningModels.length === 0) {
          listEl.innerHTML = '<span class="empty-state admin-pf-models-empty">No models found. Use Pull Model to download one.</span>';
          return;
        }

        var html = '';

        // Running models section
        if (runningModels.length > 0) {
          html += '<div class="admin-pf-section-label">Running</div>';
          for (var i = 0; i < runningModels.length; i++) {
            var run = runningModels[i];
            var runName = run.name || run.model || 'unknown';
            var runVram = run.size_vram ? formatBytes(run.size_vram) : '';
            html +=
              '<div class="admin-pf-model-row">' +
                '<span class="indicator-led indicator-led--success"></span>' +
                '<span class="admin-pf-model-name">' + escapeHtml(runName) + '</span>' +
                renderCapabilityChips(capsBy[runName]) +
                '<span class="admin-pf-model-size">' + escapeHtml(runVram) + '</span>' +
                '<div class="admin-pf-model-actions">' +
                  '<button class="btn-outlined-primary btn-sm admin-pf-model-btn admin-pf-model-unload" data-model="' + escapeAttr(runName) + '">Unload</button>' +
                '</div>' +
              '</div>';
          }
        }

        // Available models section (not currently running)
        var availableModels = [];
        for (var j = 0; j < allModels.length; j++) {
          var am = allModels[j];
          var aname = am.name || am.id || '';
          if (!runningNames[aname]) {
            availableModels.push(am);
          }
        }

        if (availableModels.length > 0) {
          html += '<div class="admin-pf-section-label">Available</div>';
          for (var k = 0; k < availableModels.length; k++) {
            var avail = availableModels[k];
            var availName = avail.name || avail.id || 'unknown';
            var availSize = avail.size ? formatBytes(avail.size) : '';
            html +=
              '<div class="admin-pf-model-row">' +
                '<span class="indicator-led indicator-led--idle"></span>' +
                '<span class="admin-pf-model-name">' + escapeHtml(availName) + '</span>' +
                renderCapabilityChips(capsBy[availName]) +
                '<span class="admin-pf-model-size">' + escapeHtml(availSize) + '</span>' +
                '<div class="admin-pf-model-actions">' +
                  '<button class="btn-outlined-primary btn-sm admin-pf-model-btn admin-pf-model-load" data-model="' + escapeAttr(availName) + '">Load</button>' +
                  '<button class="btn-muted-destructive btn-sm admin-pf-model-btn admin-pf-model-delete" data-model="' + escapeAttr(availName) + '">Delete</button>' +
                '</div>' +
              '</div>';
          }
        }

        listEl.innerHTML = html;

        // Wire action buttons
        wireOllamaActions(providerId, container);
      })
      .catch(function (err) {
        var listEl = container.querySelector('.admin-pf-models-list');
        if (listEl) {
          listEl.innerHTML = '<span class="test-result-fail">' + escapeHtml(err.message || 'Failed to load models') + '</span>';
        }
      });
  }

  function wireOllamaActions(providerId, container) {
    // Unload buttons
    var unloadBtns = container.querySelectorAll('.admin-pf-model-unload');
    for (var u = 0; u < unloadBtns.length; u++) {
      unloadBtns[u].addEventListener('click', function (ev) {
        var btn = ev.target;
        var model = btn.dataset.model;
        btn.disabled = true;
        btn.textContent = 'Unloading…';
        ollamaAction(providerId, container, 'unload', model, btn);
      });
    }

    // Load buttons
    var loadBtns = container.querySelectorAll('.admin-pf-model-load');
    for (var l = 0; l < loadBtns.length; l++) {
      loadBtns[l].addEventListener('click', function (ev) {
        var btn = ev.target;
        var model = btn.dataset.model;
        btn.disabled = true;
        btn.textContent = 'Loading…';
        ollamaAction(providerId, container, 'load', model, btn);
      });
    }

    // Delete buttons (with confirmation)
    var delBtns = container.querySelectorAll('.admin-pf-model-delete');
    for (var d = 0; d < delBtns.length; d++) {
      delBtns[d].addEventListener('click', function (ev) {
        var btn = ev.target;
        var model = btn.dataset.model;
        if (btn.classList.contains('admin-pf-model-delete-confirm')) {
          btn.disabled = true;
          btn.textContent = 'Deleting…';
          ollamaAction(providerId, container, 'delete', model, btn);
        } else {
          btn.classList.add('admin-pf-model-delete-confirm');
          btn.textContent = 'Confirm?';
          setTimeout(function () {
            btn.classList.remove('admin-pf-model-delete-confirm');
            btn.textContent = 'Delete';
          }, 3000);
        }
      });
    }
  }

  function ollamaAction(providerId, container, action, model, btn) {
    var url = '/api/providers/' + encodeURIComponent(providerId) + '/models/' + action;
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: model })
    })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || action + ' failed'); });
        return r.json();
      })
      .then(function () {
        window.App.showFlash(container, 'Model ' + action + (action === 'delete' ? 'd' : 'ed') + ' successfully');
        renderOllamaModels(providerId, container);
      })
      .catch(function (err) {
        btn.disabled = false;
        btn.textContent = action.charAt(0).toUpperCase() + action.slice(1);
        // Show inline error
        var row = btn.closest('.admin-pf-model-row');
        if (row) {
          var existing = row.querySelector('.admin-pf-model-error');
          if (existing) existing.remove();
          var errEl = document.createElement('div');
          errEl.className = 'admin-pf-model-error';
          errEl.textContent = err.message;
          row.appendChild(errEl);
          setTimeout(function () { errEl.remove(); }, 4000);
        }
      });
  }

  window.App.admin.renderProviderModels = renderProviderModels;
})();
