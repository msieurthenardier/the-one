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
      renderOllamaModels(provider, container);
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

  // Decimal units on purpose (matches ollama.com and `ollama pull`). App.formatBytes is
  // binary maths labelled "GB", which would read a model as 2.0 GB in the Pull list and
  // 1.9 GB once installed. Do not "simplify" this into App.formatBytes.
  function formatSize(bytes) {
    var n = Number(bytes);
    if (!(n > 0)) return '';
    if (n < 1e9) return Math.max(1, Math.round(n / 1e6)) + ' MB';
    return (n / 1e9).toFixed(1) + ' GB';
  }

  // "localhost:11434" for the modal; the raw base_url if it does not parse.
  function hostOf(baseUrl) {
    try {
      return new URL(baseUrl).host;
    } catch (e) {
      return baseUrl;
    }
  }

  var LOADING_COPY = 'Loading models and sizes. The first load takes a little while…';

  function renderOllamaModels(provider, container) {
    if (!container) return;
    var providerId = provider.id;

    container.innerHTML =
      '<div class="admin-pf-models-header">' +
        '<button class="btn-outlined-primary refresh-btn admin-pf-models-refresh">' + window.App.icon('refresh-cw') + ' Refresh</button>' +
      '</div>' +
      '<div class="admin-pf-pull-input">' +
        '<select class="field-input admin-pf-select admin-pf-pull-name" data-testid="admin-pf-pull-select" aria-label="Model to pull" disabled>' +
          '<option value="">Loading library…</option>' +
        '</select>' +
        '<button class="btn-filled-primary btn-sm admin-pf-pull-go" data-testid="admin-pf-pull-btn" disabled>Pull</button>' +
      '</div>' +
      '<div class="admin-pf-pull-size" data-testid="admin-pf-pull-size" aria-live="polite"></div>' +
      '<div class="admin-pf-pull-progress is-hidden" data-testid="admin-pf-pull-progress">' +
        '<div class="admin-pf-pull-fill"></div>' +
        '<span class="admin-pf-pull-text"></span>' +
        '<button class="admin-pf-pull-cancel" data-testid="admin-pf-pull-cancel" aria-label="Cancel pull">' + window.App.icon('x') + '</button>' +
      '</div>' +
      '<div class="admin-pf-pull-error is-hidden" data-testid="admin-pf-pull-error"></div>' +
      '<div class="admin-pf-vram-summary"></div>' +
      '<div class="admin-pf-models-list" aria-live="polite"><span class="admin-loading">Loading models…</span></div>';

    var refreshBtn = container.querySelector('.admin-pf-models-refresh');
    refreshBtn.addEventListener('click', function () {
      renderOllamaModels(provider, container);
    });

    // Pull UI wiring
    var pullNameInput = container.querySelector('.admin-pf-pull-name');
    var pullGoBtn = container.querySelector('.admin-pf-pull-go');
    var pullSizeEl = container.querySelector('.admin-pf-pull-size');
    var pullProgress = container.querySelector('.admin-pf-pull-progress');
    var pullFill = container.querySelector('.admin-pf-pull-fill');
    var pullText = container.querySelector('.admin-pf-pull-text');
    var pullError = container.querySelector('.admin-pf-pull-error');
    var pullCancelBtn = container.querySelector('.admin-pf-pull-cancel');

    var pullAbort = null;
    var checking = false; // the size re-check is in flight
    var libraryReady = false; // the select holds real entries
    var libraryEntries = {}; // name -> {name, size, status}
    var libraryTimer = null;

    function selectedEntry() {
      var v = pullNameInput.value;
      return v && libraryEntries[v] ? libraryEntries[v] : null;
    }

    // The Pull button: label carries the size when known; disabled with nothing
    // selected, during the re-check and during a pull.
    function renderPullButton() {
      var entry = selectedEntry();
      if (checking) {
        pullGoBtn.textContent = 'Checking size…';
        pullGoBtn.disabled = true;
        return;
      }
      if (entry && entry.status === 'ok' && entry.size) {
        pullGoBtn.textContent = 'Pull · ' + formatSize(entry.size);
      } else {
        pullGoBtn.textContent = 'Pull';
      }
      pullGoBtn.disabled = !entry || !!pullAbort;
    }

    function setSizeLine(text, warn) {
      pullSizeEl.textContent = text;
      pullSizeEl.classList.toggle('test-result-warning', !!warn);
    }

    function renderSizeLine() {
      var entry = selectedEntry();
      if (entry && entry.status === 'ok' && entry.size) {
        setSizeLine('Download: ' + formatSize(entry.size) + ', from the Ollama registry.', false);
      } else if (entry && entry.status === 'unknown') {
        setSizeLine("Size unknown: the Ollama registry couldn't be reached. Pull will ask before it starts.", true);
      } else {
        setSizeLine('', false);
      }
    }

    function setSelectMessage(text) {
      libraryReady = false;
      libraryEntries = {};
      pullNameInput.textContent = '';
      var opt = document.createElement('option');
      opt.value = '';
      opt.textContent = text;
      pullNameInput.appendChild(opt);
      pullNameInput.disabled = true;
      renderPullButton();
    }

    function optionFor(m) {
      var opt = document.createElement('option');
      opt.value = m.name;
      if (m.status === 'ok' && m.size) {
        opt.textContent = m.name + ' (' + formatSize(m.size) + ')';
      } else if (m.status === 'cloud') {
        opt.textContent = m.name + ' (cloud only, not downloadable)';
        opt.disabled = true;
      } else if (m.status === 'missing') {
        opt.textContent = m.name + ' (not downloadable)';
        opt.disabled = true;
      } else {
        opt.textContent = m.name + ' (size unknown)';
      }
      return opt;
    }

    function showLibrary(models) {
      libraryEntries = {};
      pullNameInput.textContent = '';
      var first = document.createElement('option');
      first.value = '';
      first.textContent = 'Select a model…';
      pullNameInput.appendChild(first);
      for (var i = 0; i < models.length; i++) {
        libraryEntries[models[i].name] = models[i];
        pullNameInput.appendChild(optionFor(models[i]));
      }
      libraryReady = true;
      pullNameInput.disabled = !!pullAbort;
      renderPullButton();
    }

    // Ask the catalog; while it answers "loading" keep the select disabled and ask
    // again every 2 s. Stops once this render's controls are gone (a re-render).
    function requestLibrary() {
      if (!pullNameInput.isConnected) return;
      fetch('/api/ollama-library/search')
        .then(function (r) { return r.ok ? r.json() : { loading: false, models: [] }; })
        .then(function (data) {
          if (!pullNameInput.isConnected) return;
          if (data.loading) {
            setSelectMessage(LOADING_COPY);
            libraryTimer = setTimeout(requestLibrary, 2000);
            return;
          }
          var models = data.models || [];
          if (!models.length) {
            setSelectMessage('Library unavailable');
            return;
          }
          showLibrary(models);
        })
        .catch(function () {
          if (pullNameInput.isConnected) setSelectMessage('Library unavailable');
        });
    }

    function loadLibraryOptions() {
      clearTimeout(libraryTimer);
      setSelectMessage('Loading library…');
      requestLibrary();
    }

    pullGoBtn.addEventListener('click', function () { requestPull(); });

    pullNameInput.addEventListener('change', function () {
      renderPullButton();
      renderSizeLine();
    });

    // Load the library on render so the dropdown is populated immediately.
    // Refresh re-enters renderOllamaModels which re-runs this.
    loadLibraryOptions();

    // Cancel button
    pullCancelBtn.addEventListener('click', function () {
      if (pullAbort) {
        pullAbort.abort();
        pullAbort = null;
      }
      finishPull(false);
      window.App.showFlash(container, 'Pull cancelled');
    });

    function showError(msg) {
      pullError.classList.remove('is-hidden');
      pullError.textContent = msg;
    }

    // Pull click: re-check this one entry's size, then always confirm.
    function requestPull() {
      var entry = selectedEntry();
      if (!entry || checking || pullAbort) return;
      pullError.classList.add('is-hidden');
      checking = true;
      renderPullButton();
      fetch('/api/ollama-library/size?model=' + encodeURIComponent(entry.name))
        .then(function (r) {
          if (!r.ok) {
            return r.json().catch(function () { return {}; }).then(function (e) {
              throw new Error(typeof e.detail === 'string' ? e.detail : 'Size check failed');
            });
          }
          return r.json();
        })
        .then(function (res) {
          checking = false;
          if (!pullGoBtn.isConnected) {
            window.App.showFlash(container, 'The panel refreshed; choose the model again');
            return;
          }
          renderPullButton();
          if (res.status === 'cloud' || res.status === 'missing') {
            // The registry changed since the list loaded: refresh the list only.
            loadLibraryOptions();
            setSizeLine(entry.name + ' is no longer downloadable.', true);
            return;
          }
          confirmPull(entry.name, res.status === 'ok' && res.size ? res.size : null);
        })
        .catch(function (err) {
          checking = false;
          if (!pullGoBtn.isConnected) return;
          renderPullButton();
          showError(err.message || 'Size check failed');
        });
    }

    function confirmPull(name, size) {
      var known = size !== null;
      var where = provider.name + ' (' + hostOf(provider.base_url) + ')';
      var dialog = window.App.ui.modal({
        title: known ? 'Pull ' + name + '?' : 'Pull ' + name + ' without knowing its size?',
        body: known
          ? 'This downloads ' + formatSize(size) + ' to ' + where + '.'
          : "The Ollama registry couldn't be reached, so the download size is unknown. It could be very large.",
        actions: [
          { label: 'Cancel', value: null, autofocus: true, testid: 'admin-pf-pull-confirm-cancel' },
          {
            label: known ? 'Pull ' + formatSize(size) : 'Pull anyway',
            variant: 'primary',
            value: 'pull',
            testid: 'admin-pf-pull-confirm-go'
          }
        ],
        testid: 'admin-pf-pull-confirm',
        onClose: function (value) {
          if (value !== 'pull') return;
          // Runs after the modal restored focus. Start only if this render's controls
          // are still live (a Load/Unload/Refresh may have re-rendered the panel).
          if (!pullGoBtn.isConnected) {
            window.App.showFlash(container, 'The panel refreshed; choose the model again');
            return;
          }
          startPull(name);
          pullCancelBtn.focus();
        }
      });
      dialog.open(pullGoBtn);
    }

    function startPull(model) {
      if (!model) return;

      pullAbort = new AbortController();
      pullNameInput.disabled = true;
      refreshBtn.disabled = true;
      renderPullButton();
      pullError.classList.add('is-hidden');
      pullProgress.classList.remove('is-hidden');
      pullFill.style.width = '0%';
      pullText.textContent = 'Pulling ' + model + '…';

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
                    pullText.textContent = (evt.status || '') + (pct > 0 ? ' — ' + pct + '%' : '');
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
      showError(msg);
      pullNameInput.disabled = !libraryReady;
      refreshBtn.disabled = false;
      renderPullButton();
    }

    function finishPull(success) {
      pullAbort = null;
      pullProgress.classList.add('is-hidden');
      pullNameInput.disabled = !libraryReady;
      pullNameInput.value = '';
      refreshBtn.disabled = false;
      renderPullButton();
      renderSizeLine();
      if (success) {
        window.App.showFlash(container, 'Model pulled successfully');
        renderOllamaModels(provider, container);
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
          var vramValue = document.createElement('span');
          vramValue.className = 'admin-pf-vram-value';
          vramValue.textContent = formatSize(totalVram) + ' loaded';
          vramEl.textContent = '';
          vramEl.appendChild(vramValue);
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
            var runVram = run.size_vram ? formatSize(run.size_vram) : '';
            html +=
              '<div class="admin-pf-model-row">' +
                '<span class="indicator-led indicator-led--success" aria-hidden="true"></span>' +
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
            var availSize = avail.size ? formatSize(avail.size) : '';
            html +=
              '<div class="admin-pf-model-row">' +
                '<span class="indicator-led indicator-led--idle" aria-hidden="true"></span>' +
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
        wireOllamaActions(provider, container);
      })
      .catch(function (err) {
        var listEl = container.querySelector('.admin-pf-models-list');
        if (listEl) {
          listEl.innerHTML = '<span class="test-result-fail">' + escapeHtml(err.message || 'Failed to load models') + '</span>';
        }
      });
  }

  function wireOllamaActions(provider, container) {
    // Unload buttons
    var unloadBtns = container.querySelectorAll('.admin-pf-model-unload');
    for (var u = 0; u < unloadBtns.length; u++) {
      unloadBtns[u].addEventListener('click', function (ev) {
        var btn = ev.target;
        var model = btn.dataset.model;
        btn.disabled = true;
        btn.textContent = 'Unloading…';
        ollamaAction(provider, container, 'unload', model, btn);
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
        ollamaAction(provider, container, 'load', model, btn);
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
          ollamaAction(provider, container, 'delete', model, btn);
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

  function ollamaAction(provider, container, action, model, btn) {
    var url = '/api/providers/' + encodeURIComponent(provider.id) + '/models/' + action;
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
        renderOllamaModels(provider, container);
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
