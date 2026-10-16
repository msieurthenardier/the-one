// App.studio.renderProviderModels — the provider models panel.
//
// Built on the control library under flight DD1 (M31 F1 L6): the panel's shell is
// built ONCE per mount, with DOM APIs and App.ui controls, and nothing after mount
// rebuilds it from markup. renderProviderModels(container, provider) returns a
// controller {refresh(), destroy()}:
//   - refresh() re-fetches and RECONCILES: the Ollama list is patched by model name
//     (a row node is updated in place, moved when its section changes, added or
//     removed), so a pull in progress, the pull select's choice, a row's busy or
//     armed state, row errors and keyboard focus all survive.
//   - destroy() aborts a pull and clears the library poll and row-error timers.
//
// Dispatch on provider.type, decided at mount from the SAVED type (a type change in
// the editor's form does not re-dispatch; today's behaviour):
//   - 'ollama'  → Ollama lifecycle UI (refresh / pull / list / unload / load /
//                 delete-row + VRAM summary + streaming pull progress).
//   - other     → basic model list (Refresh + GET /api/providers/{id}/models).
//
// One provider editor is mounted at a time, so a module-level `activeController`
// is destroyed before a new mount (a full editor re-render never orphans a poll or
// a pull).
//
// `.admin-pf-*` layout classes stay (per-area scoping kept intentionally).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var util = App.ui.util;
  var activeController = null;

  var NO_TOOLS_TITLE =
    'This model does not support tool calling — agents will run in single-shot chat mode.';

  // Render the Ollama capability list as a row of chips. `caps` is the array
  // returned by /api/show (e.g. ['completion', 'tools', 'vision']); null means the
  // capability lookup failed (network/missing model) and we render nothing rather
  // than misleadingly implying "no capabilities". Absence of `tools` adds a danger
  // "no tools" chip so the operator sees it at a glance. Returns a node, or null.
  function renderCapabilityChips(caps) {
    if (!Array.isArray(caps) || caps.length === 0) return null;
    var row = util.el('span', { className: 'cap-chip-row' });
    for (var i = 0; i < caps.length; i++) {
      row.appendChild(App.ui.chip({ label: caps[i], size: 'sm' }));
    }
    if (caps.indexOf('tools') === -1) {
      row.appendChild(App.ui.chip({
        label: 'no tools',
        tone: 'danger',
        size: 'sm',
        title: NO_TOOLS_TITLE
      }));
    }
    return row;
  }

  // Exposed so Studio's model selector can reuse the same chip vocabulary.
  window.App.studio.renderCapabilityChips = renderCapabilityChips;

  // Decimal units, like App.formatBytes (matches ollama.com and `ollama pull`). Kept
  // separate on purpose: its output differs (whole MB, '' for an unknown size, one-decimal
  // GB with no TB tier), so it is not a drop-in for App.formatBytes.
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

  function jsonOrThrow(fallback) {
    return function (r) {
      if (!r.ok) {
        return r.json().catch(function () { return {}; }).then(function (e) {
          throw new Error((e && e.detail) || fallback);
        });
      }
      return r.json();
    };
  }

  function modelsUrl(provider, suffix) {
    return '/api/providers/' + encodeURIComponent(provider.id) + '/models' + (suffix || '');
  }

  // The list region: loading line, error line and empty state are built once, in this
  // order, BEFORE the rows (so a row is always the last child while there are rows).
  // `mode(m, msg)` shows exactly one of 'loading' | 'error' | 'empty' | 'list'.
  function buildListRegion(emptyBody) {
    var loading = util.el('span', { className: 'admin-loading', text: 'Loading models…' });
    var error = App.ui.status({ state: 'danger', text: 'Failed to load models' });
    error.el.hidden = true;
    var empty = App.ui.emptyState({
      title: 'No models found.',
      body: emptyBody,
      titleTag: 'p'
    });
    empty.classList.add('admin-pf-models-empty');
    empty.hidden = true;
    var host = util.el('div', { className: 'admin-pf-models-list', 'aria-live': 'polite' },
      [loading, error.el, empty]);
    return {
      el: host,
      anchor: empty,
      mode: function (m, msg) {
        loading.hidden = m !== 'loading';
        error.el.hidden = m !== 'error';
        empty.hidden = m !== 'empty';
        if (m === 'error') error.set('danger', msg || 'Failed to load models');
      }
    };
  }

  // Make `parent`'s children after `anchor` exactly `desired` (in order), moving a node
  // only when it is out of place and removing anything left over.
  function placeNodes(parent, anchor, desired) {
    var ref = anchor.nextSibling;
    for (var i = 0; i < desired.length; i++) {
      if (desired[i] === ref) {
        ref = ref.nextSibling;
      } else {
        parent.insertBefore(desired[i], ref);
      }
    }
    while (ref) {
      var next = ref.nextSibling;
      parent.removeChild(ref);
      ref = next;
    }
  }

  function renderProviderModels(container, provider) {
    if (!provider || !provider.id || !container) return null;
    if (activeController) activeController.destroy();
    container.textContent = '';
    var ctl = provider.type === 'ollama'
      ? mountOllama(provider, container)
      : mountBasic(provider, container);
    activeController = ctl;
    return ctl;
  }

  function buildRefreshButton(onClick) {
    return App.ui.button({
      size: 'sm',
      icon: 'refresh-cw',
      label: 'Refresh',
      className: 'admin-pf-models-refresh',
      onClick: onClick
    });
  }

  // ── Basic (non-Ollama) list ─────────────────────────────────────────────

  function mountBasic(provider, container) {
    var destroyed = false;
    var generation = 0;
    var rows = Object.create(null);
    var shown = false; // a result has been applied (the loading line is for the first load)

    var refreshBtn = buildRefreshButton(function () { refresh(); });
    var region = buildListRegion();
    container.appendChild(util.el('div', { className: 'admin-pf-models-header' }, [refreshBtn]));
    container.appendChild(region.el);
    region.mode('loading');

    function showModels(models) {
      var names = [];
      var seen = Object.create(null);
      var i;
      for (i = 0; i < models.length; i++) {
        var name = models[i].id || models[i].name;
        if (!name || seen[name]) continue;
        seen[name] = true;
        names.push(name);
      }
      var desired = [];
      for (i = 0; i < names.length; i++) {
        var row = rows[names[i]];
        if (!row) {
          row = util.el('div', { className: 'admin-pf-model-item', text: names[i] });
          rows[names[i]] = row;
        }
        desired.push(row);
      }
      Object.keys(rows).forEach(function (key) { if (!seen[key]) delete rows[key]; });
      placeNodes(region.el, region.anchor, desired);
      region.mode(names.length ? 'list' : 'empty');
    }

    function refresh() {
      var mine = ++generation;
      if (!shown) region.mode('loading');
      fetch(modelsUrl(provider))
        .then(jsonOrThrow('Failed to load models'))
        .then(function (models) {
          if (destroyed || mine !== generation) return;
          shown = true;
          showModels(models);
        })
        .catch(function (err) {
          if (destroyed || mine !== generation) return;
          shown = true;
          showModels([]);
          region.mode('error', (err && err.message) || 'Failed to load models');
        });
    }

    var controller = {
      refresh: refresh,
      destroy: function () {
        destroyed = true;
        generation++;
        if (activeController === controller) activeController = null;
      }
    };
    refresh();
    return controller;
  }

  // ── Ollama lifecycle panel ──────────────────────────────────────────────

  function mountOllama(provider, container) {
    var destroyed = false;
    var generation = 0; // the models+status refresh
    var libraryGeneration = 0; // the pull library fetch
    var libraryTimer = null;

    // Pull state
    var pullAbort = null;
    var checking = false; // the size re-check is in flight
    var libraryReady = false; // the select holds real entries
    var libraryEntries = Object.create(null); // name -> {name, size, status}
    var optionsSignature = null;

    // List state
    var rows = Object.create(null); // model name -> row
    var order = []; // model names in display order
    var loaded = false;

    // ── The shell, built once ─────────────────────────────────────────
    var refreshBtn = buildRefreshButton(function () { refresh(); });

    var pullSelect = App.ui.select({
      options: [{ value: '', label: 'Loading library…' }],
      disabled: true,
      testid: 'admin-pf-pull-select',
      onChange: function () {
        renderPullButton();
        renderSizeLine();
      }
    });
    pullSelect.classList.add('admin-pf-select', 'admin-pf-pull-name');
    pullSelect.setAttribute('aria-label', 'Model to pull');

    var pullBtn = App.ui.button({
      variant: 'primary',
      size: 'sm',
      label: 'Pull',
      disabled: true,
      className: 'admin-pf-pull-go',
      testid: 'admin-pf-pull-btn',
      onClick: function () { requestPull(); }
    });

    var sizeLine = util.el('div', {
      className: 'admin-pf-pull-size',
      'aria-live': 'polite',
      'data-testid': 'admin-pf-pull-size'
    });

    var progress = App.ui.progress({
      label: 'Pull progress',
      value: 0,
      text: '',
      cancelLabel: 'Cancel pull',
      testid: 'admin-pf-pull-progress',
      cancelTestid: 'admin-pf-pull-cancel',
      onCancel: function () { cancelPull(); }
    });
    progress.el.hidden = true;

    var pullError = App.ui.status({
      state: 'danger',
      text: 'Pull failed',
      testid: 'admin-pf-pull-error'
    });
    pullError.el.hidden = true;

    var vram = util.el('div', { className: 'admin-pf-vram-summary' });
    var vramKey = null;

    var region = buildListRegion('Use Pull Model to download one.');
    var runningLabel = util.el('div', { className: 'admin-pf-section-label', text: 'Running' });
    var availableLabel = util.el('div', { className: 'admin-pf-section-label', text: 'Available' });

    container.appendChild(util.el('div', { className: 'admin-pf-models-header' }, [refreshBtn]));
    container.appendChild(util.el('div', { className: 'admin-pf-pull-input' }, [pullSelect, pullBtn]));
    container.appendChild(sizeLine);
    container.appendChild(progress.el);
    container.appendChild(pullError.el);
    container.appendChild(vram);
    container.appendChild(region.el);
    region.mode('loading');

    function cancelButton() {
      return progress.cancelButton;
    }

    function flash(message) {
      if (destroyed) return;
      App.ui.flash(message, { container: container });
    }

    // ── Pull: select, button, size line ───────────────────────────────

    function selectedEntry() {
      var v = pullSelect.value;
      return v && libraryEntries[v] ? libraryEntries[v] : null;
    }

    // The Pull button: label carries the size when known; disabled with nothing
    // selected, during the re-check and during a pull.
    function renderPullButton() {
      var entry = selectedEntry();
      if (checking) {
        pullBtn.textContent = 'Checking size…';
        pullBtn.disabled = true;
        return;
      }
      if (entry && entry.status === 'ok' && entry.size) {
        pullBtn.textContent = 'Pull · ' + formatSize(entry.size);
      } else {
        pullBtn.textContent = 'Pull';
      }
      pullBtn.disabled = !entry || !!pullAbort;
    }

    function setSizeLine(text, warn) {
      sizeLine.textContent = text;
      sizeLine.classList.toggle('admin-pf-pull-size--warn', !!warn);
      if (warn) {
        sizeLine.setAttribute('data-state', 'warn');
      } else {
        sizeLine.removeAttribute('data-state');
      }
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
      libraryEntries = Object.create(null);
      optionsSignature = null;
      pullSelect.textContent = '';
      var opt = util.el('option', { text: text });
      opt.value = '';
      pullSelect.appendChild(opt);
      pullSelect.disabled = true;
      renderPullButton();
    }

    function optionFor(m) {
      var opt = util.el('option');
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

    // Show the catalog. The chosen model survives while it is still offered; the
    // options are only rebuilt when the list differs.
    function showLibrary(models) {
      var previous = pullSelect.value;
      var signature = JSON.stringify(models.map(function (m) { return [m.name, m.size, m.status]; }));
      libraryEntries = Object.create(null);
      for (var i = 0; i < models.length; i++) libraryEntries[models[i].name] = models[i];
      if (signature !== optionsSignature) {
        optionsSignature = signature;
        pullSelect.textContent = '';
        var first = util.el('option', { text: 'Select a model…' });
        first.value = '';
        pullSelect.appendChild(first);
        for (var j = 0; j < models.length; j++) pullSelect.appendChild(optionFor(models[j]));
      }
      var kept = previous && libraryEntries[previous] &&
        libraryEntries[previous].status !== 'cloud' && libraryEntries[previous].status !== 'missing';
      pullSelect.value = kept ? previous : '';
      libraryReady = true;
      pullSelect.disabled = !!pullAbort;
      renderPullButton();
      if (pullSelect.value !== previous) renderSizeLine();
    }

    // Ask the catalog. While it answers "loading" keep asking every 2 s through the one
    // timer; cached models in a loading answer are shown at once (squawk 0139). `reset`
    // clears the select to a message first (the first load; a stale entry).
    function loadLibrary(reset) {
      if (destroyed) return;
      clearTimeout(libraryTimer);
      libraryTimer = null;
      var mine = ++libraryGeneration;
      if (reset) setSelectMessage('Loading library…');
      fetch('/api/ollama-library/search')
        .then(function (r) { return r.ok ? r.json() : { loading: false, models: [] }; })
        .then(function (data) {
          if (destroyed || mine !== libraryGeneration) return;
          var models = data.models || [];
          if (models.length) showLibrary(models);
          if (data.loading) {
            if (!models.length) setSelectMessage(LOADING_COPY);
            libraryTimer = setTimeout(function () {
              // Fallback for a mount that is truly gone (the editor closed).
              if (!container.isConnected) {
                controller.destroy();
                return;
              }
              loadLibrary(false);
            }, 2000);
            return;
          }
          if (!models.length) setSelectMessage('Library unavailable');
        })
        .catch(function () {
          if (destroyed || mine !== libraryGeneration) return;
          setSelectMessage('Library unavailable');
        });
    }

    function showPullErrorLine(msg) {
      pullError.set('danger', msg);
      pullError.el.hidden = false;
    }

    // Pull click: re-check this one entry's size, then always confirm.
    function requestPull() {
      var entry = selectedEntry();
      if (!entry || checking || pullAbort) return;
      pullError.el.hidden = true;
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
          if (destroyed) return;
          renderPullButton();
          if (res.status === 'cloud' || res.status === 'missing') {
            // The registry changed since the list loaded: refresh the list only.
            loadLibrary(true);
            setSizeLine(entry.name + ' is no longer downloadable.', true);
            return;
          }
          confirmPull(entry.name, res.status === 'ok' && res.size ? res.size : null);
        })
        .catch(function (err) {
          checking = false;
          if (destroyed) return;
          renderPullButton();
          showPullErrorLine(err.message || 'Size check failed');
        });
    }

    function confirmPull(name, size) {
      var known = size !== null;
      var where = provider.name + ' (' + hostOf(provider.base_url) + ')';
      var dialog = App.ui.modal({
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
          // Runs after the modal restored focus. The shell survives refreshes, so this
          // only stops when the editor itself was closed.
          if (destroyed) return;
          startPull(name);
          var cancel = cancelButton();
          if (cancel) cancel.focus();
        }
      });
      dialog.open(pullBtn);
    }

    function cancelPull() {
      if (pullAbort) {
        pullAbort.abort();
        pullAbort = null;
      }
      finishPull(false);
      flash('Pull cancelled');
    }

    function startPull(model) {
      if (!model) return;

      pullAbort = new AbortController();
      pullSelect.disabled = true;
      refreshBtn.disabled = true;
      renderPullButton();
      pullError.el.hidden = true;
      progress.el.hidden = false;
      progress.set(0, 'Pulling ' + model + '…');

      fetch(modelsUrl(provider, '/pull'), {
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
                    progress.set(pct / 100, (evt.status || '') + (pct > 0 ? ' — ' + pct + '%' : ''));
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
          if (err.name === 'AbortError') return; // cancelled by user, or the editor closed
          showPullError(err.message || 'Pull failed');
        });
    }

    function showPullError(msg) {
      if (destroyed) return;
      pullAbort = null;
      progress.el.hidden = true;
      showPullErrorLine(msg);
      pullSelect.disabled = !libraryReady;
      refreshBtn.disabled = false;
      renderPullButton();
    }

    function finishPull(success) {
      if (destroyed) return;
      pullAbort = null;
      progress.el.hidden = true;
      pullSelect.disabled = !libraryReady;
      pullSelect.value = '';
      refreshBtn.disabled = false;
      renderPullButton();
      renderSizeLine();
      if (success) {
        flash('Model pulled successfully');
        refresh();
      }
    }

    // ── The list: keyed rows ──────────────────────────────────────────

    function firstAction(row) {
      var buttons = [row.unloadBtn, row.loadBtn, row.deleteBtn];
      for (var i = 0; i < buttons.length; i++) {
        if (!buttons[i].hidden && !buttons[i].disabled) return buttons[i];
      }
      return null;
    }

    function setButtonText(btn, text) {
      if (btn === undefined || btn === null) return;
      if (btn._titleEl) {
        btn._titleEl.textContent = text;
      } else {
        btn.textContent = text;
      }
    }

    function clearRowError(row) {
      clearTimeout(row.errorTimer);
      row.errorTimer = null;
      if (row.errorLine) row.errorLine.el.hidden = true;
    }

    function showRowError(row, message) {
      if (!row.errorLine) {
        row.errorLine = App.ui.status({ state: 'danger', text: message });
        row.errorLine.el.classList.add('admin-pf-model-error');
        row.el.appendChild(row.errorLine.el);
      }
      row.errorLine.set('danger', message);
      row.errorLine.el.hidden = false;
      clearTimeout(row.errorTimer);
      row.errorTimer = setTimeout(function () { clearRowError(row); }, 4000);
    }

    // End a row's in-flight action: its button back to its label and enabled.
    function clearBusy(row) {
      var was = row.busy;
      row.busy = null;
      row.busyDone = false;
      if (was === 'unload') {
        row.unloadBtn.disabled = false;
        setButtonText(row.unloadBtn, 'Unload');
      } else if (was === 'load') {
        row.loadBtn.disabled = false;
        setButtonText(row.loadBtn, 'Load');
      } else if (was === 'delete') {
        row.deleteBtn.disabled = false;
        if (row.deleteRevert) {
          row.deleteRevert();
          row.deleteRevert = null;
        }
        setButtonText(row.deleteBtn, 'Delete');
      }
    }

    function ollamaAction(row, action) {
      var btn = action === 'unload' ? row.unloadBtn : action === 'load' ? row.loadBtn : row.deleteBtn;
      clearRowError(row);
      row.busy = action;
      row.busyDone = false;
      row.heldFocus = document.activeElement === btn;
      row.focusBtn = btn;
      btn.disabled = true;
      setButtonText(btn, action === 'unload' ? 'Unloading…' : action === 'load' ? 'Loading…' : 'Deleting…');
      fetch(modelsUrl(provider, '/' + action), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: row.name })
      })
        .then(jsonOrThrow(action + ' failed'))
        .then(function () {
          if (destroyed) return;
          flash('Model ' + action + (action === 'delete' ? 'd' : 'ed') + ' successfully');
          // The busy state ends when the refresh that follows lands (the row is
          // re-sectioned or removed then).
          row.busyDone = true;
          refresh();
        })
        .catch(function (err) {
          if (destroyed) return;
          clearBusy(row);
          showRowError(row, err.message);
          if (row.heldFocus && (!document.activeElement || document.activeElement === document.body)) {
            btn.focus();
          }
          row.heldFocus = false;
        });
    }

    function buildRow(name) {
      var row = {
        name: name,
        section: null,
        busy: null,
        busyDone: false,
        capsKey: null,
        errorLine: null,
        errorTimer: null,
        deleteRevert: null,
        heldFocus: false,
        focusBtn: null
      };
      row.led = App.ui.status({ state: 'idle', ledLabel: 'Model state', live: 'off' });
      row.led.el.classList.add('admin-pf-model-led');
      row.nameEl = util.el('span', { className: 'admin-pf-model-name', text: name });
      row.capsEl = util.el('span', { className: 'admin-pf-model-caps' });
      row.capsEl.hidden = true;
      row.sizeEl = util.el('span', { className: 'admin-pf-model-size' });

      row.unloadBtn = App.ui.button({
        size: 'sm',
        label: 'Unload',
        className: 'admin-pf-model-btn admin-pf-model-unload',
        onClick: function () { ollamaAction(row, 'unload'); }
      });
      row.loadBtn = App.ui.button({
        size: 'sm',
        label: 'Load',
        className: 'admin-pf-model-btn admin-pf-model-load',
        onClick: function () { ollamaAction(row, 'load'); }
      });
      row.deleteBtn = App.ui.button({
        variant: 'danger',
        size: 'sm',
        className: 'admin-pf-model-btn admin-pf-model-delete'
      });
      row.deleteBtn._titleEl = util.el('span', { text: 'Delete' });
      row.deleteBtn._titleEl.setAttribute('data-confirm-title', '');
      row.deleteBtn.appendChild(row.deleteBtn._titleEl);
      row.deleteBtn.addEventListener('click', function () {
        App.ui.confirm(row.deleteBtn, function (itemEl, revert) {
          row.deleteRevert = revert;
          ollamaAction(row, 'delete');
        }, { confirmLabel: 'Confirm delete?' });
      });

      var actions = util.el('div', { className: 'admin-pf-model-actions' },
        [row.unloadBtn, row.loadBtn, row.deleteBtn]);
      row.el = util.el('div', { className: 'admin-pf-model-row' },
        [row.led.el, row.nameEl, row.capsEl, row.sizeEl, actions]);
      return row;
    }

    // Update a row in place for its section ('running' | 'available') and data.
    function setRowState(row, section, size, caps) {
      var running = section === 'running';
      row.section = section;
      row.el.setAttribute('data-section', section);
      row.led.set(running ? 'success' : 'idle', '', { ledLabel: running ? 'Running' : 'Not running' });
      if (row.sizeEl.textContent !== size) row.sizeEl.textContent = size;
      var capsKey = Array.isArray(caps) ? caps.join('\n') : '';
      if (capsKey !== row.capsKey) {
        row.capsKey = capsKey;
        row.capsEl.textContent = '';
        var chips = renderCapabilityChips(caps);
        if (chips) row.capsEl.appendChild(chips);
        row.capsEl.hidden = !chips;
      }
      row.unloadBtn.hidden = !running;
      row.loadBtn.hidden = running;
      row.deleteBtn.hidden = running;
      // The refresh that follows a finished action ends its busy state. An in-flight
      // action keeps its busy state through any other refresh.
      if (row.busyDone) clearBusy(row);
    }

    function updateVram(running, totalVram) {
      var key = running.length === 0 ? 'none' : totalVram > 0 ? 'v' + totalVram : 'unavailable';
      if (key === vramKey) return;
      vramKey = key;
      vram.textContent = '';
      if (running.length === 0) {
        vram.textContent = 'No models loaded';
      } else if (totalVram > 0) {
        vram.appendChild(util.el('span', {
          className: 'admin-pf-vram-value',
          text: formatSize(totalVram) + ' loaded'
        }));
      } else {
        vram.textContent = 'VRAM info unavailable';
      }
    }

    // The row that holds keyboard focus. A button this panel just disabled (a row
    // action in flight) drops focus to the body, so such a row remembers it held focus
    // (`heldFocus`); that memory only counts while focus is nowhere.
    function focusedRow() {
      var active = document.activeElement;
      var names = Object.keys(rows);
      var i;
      if (active && active !== document.body) {
        for (i = 0; i < names.length; i++) {
          if (rows[names[i]].el.contains(active)) return { row: rows[names[i]], active: active };
        }
        return null;
      }
      for (i = 0; i < names.length; i++) {
        if (rows[names[i]].heldFocus) return { row: rows[names[i]], active: rows[names[i]].focusBtn };
      }
      return null;
    }

    function restoreFocus(row, active, oldOrder, present) {
      if (present[row.name]) {
        if (document.activeElement === active) return;
        if (active.isConnected && !active.hidden && !active.disabled) {
          active.focus();
          return;
        }
        var action = firstAction(row);
        if (action) action.focus();
        return;
      }
      // The row is gone: the neighbouring row's first action, else Refresh.
      var at = oldOrder.indexOf(row.name);
      var i;
      for (i = at + 1; i < oldOrder.length; i++) {
        if (present[oldOrder[i]]) {
          var after = firstAction(rows[oldOrder[i]]);
          if (after) { after.focus(); return; }
        }
      }
      for (i = at - 1; i >= 0; i--) {
        if (present[oldOrder[i]]) {
          var before = firstAction(rows[oldOrder[i]]);
          if (before) { before.focus(); return; }
        }
      }
      if (!refreshBtn.disabled) refreshBtn.focus();
    }

    function clearRows() {
      Object.keys(rows).forEach(function (name) {
        clearRowError(rows[name]);
        delete rows[name];
      });
      order = [];
    }

    // Reconcile the list: rows keyed by model name, in two sections.
    function applyModels(allModels, runningModels) {
      var focused = focusedRow();
      var oldOrder = order;

      var totalVram = 0;
      var capsBy = Object.create(null);
      var i;
      for (i = 0; i < allModels.length; i++) {
        var cm = allModels[i];
        var cname = cm.name || cm.id || '';
        if (cname) capsBy[cname] = cm.capabilities || null;
      }

      var present = Object.create(null);
      var runningRows = [];
      var availableRows = [];

      function rowFor(name, section, size, caps) {
        var row = rows[name];
        if (!row) {
          row = buildRow(name);
          rows[name] = row;
        }
        present[name] = true;
        setRowState(row, section, size, caps);
        return row;
      }

      for (i = 0; i < runningModels.length; i++) {
        var run = runningModels[i];
        var runName = run.name || run.model || 'unknown';
        if (present[runName]) continue;
        if (run.size_vram) totalVram += run.size_vram;
        runningRows.push(rowFor(runName, 'running', run.size_vram ? formatSize(run.size_vram) : '',
          capsBy[runName]));
      }
      for (i = 0; i < allModels.length; i++) {
        var am = allModels[i];
        var availName = am.name || am.id || 'unknown';
        if (present[availName]) continue; // running, or a duplicate
        availableRows.push(rowFor(availName, 'available', am.size ? formatSize(am.size) : '',
          capsBy[availName]));
      }

      Object.keys(rows).forEach(function (name) {
        if (present[name]) return;
        clearRowError(rows[name]);
        delete rows[name];
      });

      updateVram(runningRows, totalVram);

      var desired = [];
      var names = [];
      var k;
      if (runningRows.length) {
        desired.push(runningLabel);
        for (k = 0; k < runningRows.length; k++) {
          desired.push(runningRows[k].el);
          names.push(runningRows[k].name);
        }
      }
      if (availableRows.length) {
        desired.push(availableLabel);
        for (k = 0; k < availableRows.length; k++) {
          desired.push(availableRows[k].el);
          names.push(availableRows[k].name);
        }
      }
      placeNodes(region.el, region.anchor, desired);
      order = names;
      region.mode(names.length ? 'list' : 'empty');

      // A row still mid-action keeps its focus memory for the refresh that ends it.
      if (focused && !(present[focused.row.name] && focused.row.busy && !focused.row.busyDone)) {
        restoreFocus(focused.row, focused.active, oldOrder, present);
        focused.row.heldFocus = false;
      }
    }

    // Re-fetch the models and the running set and reconcile. Overlapping calls: a stale
    // response is dropped. The Refresh button's pull lock lives on the button, not here,
    // so a Test-success refresh mid-pull still runs.
    function refresh() {
      if (destroyed) return;
      var mine = ++generation;
      if (!loaded) region.mode('loading');
      loadLibrary(!loaded);
      Promise.all([
        fetch(modelsUrl(provider)).then(jsonOrThrow('Failed to load models')),
        fetch(modelsUrl(provider, '/status')).then(jsonOrThrow('Failed to load status'))
      ])
        .then(function (results) {
          if (destroyed || mine !== generation) return;
          loaded = true;
          applyModels(results[0], results[1]);
        })
        .catch(function (err) {
          if (destroyed || mine !== generation) return;
          loaded = true;
          applyModels([], []);
          vram.textContent = '';
          vramKey = null;
          region.mode('error', (err && err.message) || 'Failed to load models');
        });
    }

    var controller = {
      refresh: refresh,
      destroy: function () {
        destroyed = true;
        generation++;
        libraryGeneration++;
        clearTimeout(libraryTimer);
        libraryTimer = null;
        if (pullAbort) {
          pullAbort.abort();
          pullAbort = null;
        }
        Object.keys(rows).forEach(function (name) { clearRowError(rows[name]); });
        if (activeController === controller) activeController = null;
      }
    };
    refresh();
    return controller;
  }

  window.App.studio.renderProviderModels = renderProviderModels;
})();
