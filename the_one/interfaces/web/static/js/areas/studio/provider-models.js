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
// One provider editor is mounted at a time, so a module-level mount slot
// (App.ui.util.mountSlot) destroys the previous controller before a new mount (a
// full editor re-render never orphans a poll or a pull).
//
// `.admin-pf-*` layout classes stay (per-area scoping kept intentionally).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var util = App.ui.util;
  var slot = util.mountSlot();

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
  // order, BEFORE the model list control (App.ui.modelList), which owns the rows.
  // `mode(m, msg)` shows exactly one of 'loading' | 'error' | 'empty' | 'list'.
  function buildListRegion(emptyBody, listEl) {
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
    var host = util.el('div', { className: 'provider-models-region', 'aria-live': 'polite' },
      [loading, error.el, empty, listEl]);
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

  function renderProviderModels(container, provider) {
    if (!provider || !provider.id || !container) return null;
    var ctl = null;
    var token = slot.mount(function () { if (ctl) ctl.destroy(); });
    try {
      container.textContent = '';
      ctl = provider.type === 'ollama'
        ? mountOllama(provider, container)
        : mountBasic(provider, container);
    } catch (err) {
      slot.release(token);
      throw err;
    }
    // A controller's own destroy releases the slot (a no-op when the slot is
    // already past this mount).
    var innerDestroy = ctl.destroy;
    ctl.destroy = function () {
      slot.release(token);
      innerDestroy();
    };
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
    var shown = false; // a result has been applied (the loading line is for the first load)

    var refreshBtn = buildRefreshButton(function () { refresh(); });
    var list = App.ui.modelList({ label: 'Models', density: 'compact' });
    var region = buildListRegion(undefined, list.el);
    container.appendChild(util.el('div', { className: 'admin-pf-models-header' }, [refreshBtn]));
    container.appendChild(region.el);
    region.mode('loading');

    function showModels(models) {
      var rowSpecs = [];
      for (var i = 0; i < models.length; i++) {
        var name = models[i].id || models[i].name;
        if (name) rowSpecs.push({ name: name });
      }
      list.reconcile([{ key: 'models', label: null, rows: rowSpecs }]);
      region.mode(list.el.children.length ? 'list' : 'empty');
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
        list.destroy();
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

    var list = App.ui.modelList({
      label: 'Models',
      actions: ['unload', 'load', 'delete'],
      onAction: function (name, action) { ollamaAction(name, action); },
      onFocusLost: function () { if (!refreshBtn.disabled) refreshBtn.focus(); }
    });
    var region = buildListRegion('Use Pull to download one.', list.el);

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
      App.ui.flash(message);
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
      var lastPct = 0;
      progress.set(0, 'Pulling ' + model + '… 0%');

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
                    if (evt.total && evt.total > 0) {
                      lastPct = Math.min(100, Math.floor(((evt.completed || 0) / evt.total) * 100));
                    }
                    progress.set(lastPct / 100, 'Pulling ' + model + '… ' + lastPct + '%');
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

    // The control sets the row busy and records its held focus; this runs the work.
    function ollamaAction(name, action) {
      fetch(modelsUrl(provider, '/' + action), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: name })
      })
        .then(jsonOrThrow(action + ' failed'))
        .then(function () {
          if (destroyed) return;
          flash('Model ' + action + (action === 'delete' ? 'd' : 'ed') + ' successfully');
          // The busy state ends when the refresh that follows lands (the row is
          // re-sectioned or removed then).
          list.setRowBusy(name, 'done');
          refresh();
        })
        .catch(function (err) {
          if (destroyed) return;
          list.setRowBusy(name, null);
          list.setRowError(name, err.message);
        });
    }

    function updateVram(running, totalVram) {
      var key = running.length === 0 ? 'none' : totalVram > 0 ? 'v' + totalVram : 'unavailable';
      if (key === vramKey) return;
      vramKey = key;
      vram.textContent = '';
      if (running.length === 0) {
        vram.textContent = 'No models loaded';
      } else if (totalVram > 0) {
        vram.textContent = formatSize(totalVram) + ' loaded';
      } else {
        vram.textContent = 'VRAM info unavailable';
      }
    }

    // Reconcile the list: rows keyed by model name, in two sections.
    function applyModels(allModels, runningModels) {
      var totalVram = 0;
      var capsBy = Object.create(null);
      var seen = Object.create(null);
      var running = [];
      var available = [];
      var i;
      for (i = 0; i < allModels.length; i++) {
        var cm = allModels[i];
        var cname = cm.name || cm.id || '';
        if (cname) capsBy[cname] = cm.capabilities || null;
      }
      for (i = 0; i < runningModels.length; i++) {
        var run = runningModels[i];
        var runName = run.name || run.model || 'unknown';
        if (seen[runName]) continue;
        seen[runName] = true;
        if (run.size_vram) totalVram += run.size_vram;
        running.push({
          name: runName,
          state: 'running',
          caps: capsBy[runName],
          size: run.size_vram ? formatSize(run.size_vram) : ''
        });
      }
      for (i = 0; i < allModels.length; i++) {
        var am = allModels[i];
        var availName = am.name || am.id || 'unknown';
        if (seen[availName]) continue; // running, or a duplicate
        seen[availName] = true;
        available.push({
          name: availName,
          state: 'idle',
          caps: capsBy[availName],
          size: am.size ? formatSize(am.size) : ''
        });
      }
      updateVram(running, totalVram);
      list.reconcile([
        { key: 'running', label: 'Running', rows: running },
        { key: 'available', label: 'Available', rows: available }
      ]);
      region.mode(running.length + available.length ? 'list' : 'empty');
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
        list.destroy();
      }
    };
    refresh();
    return controller;
  }

  window.App.studio.renderProviderModels = renderProviderModels;
})();
