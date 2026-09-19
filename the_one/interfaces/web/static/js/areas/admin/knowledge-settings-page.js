(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Administration → Knowledge panel (M24 F06 L04, DD-7 / L4-D1..D6).
  //
  // Four sections: chunking + monitoring are editable (one form, one
  // explicit Save — L4-D4); embedding + vector store are read-only, each
  // with the reason stated on screen rather than a disabled input (L4-D1).
  // Client-side bounds mirror the server's exactly (L4-D3): size_chars
  // 200-2000, reconcile_interval_seconds 10-86400, and overlap_chars at
  // most floor(size_chars / 2) — the overlap check re-evaluates whenever
  // size_chars changes, not only on overlap edits.
  //
  // Modelled on system-page.js: one static single-string-literal innerHTML
  // for the chrome (exempt from the dynamic-sink freeze), then a fetch that
  // fills values in via textContent/.value, mirroring the
  // `.admin-system-section` / `.section-title admin-section-title` /
  // `.admin-system-text` vocabulary that page established.

  var CHUNK_SIZE_MIN = 200;
  var CHUNK_SIZE_MAX = 2000;
  var RECONCILE_MIN = 10;
  var RECONCILE_MAX = 86400;

  function renderKnowledgeSettingsPage(container, callbacks) {
    callbacks = callbacks || {};
    var onDirtyChange = callbacks.onDirtyChange || function () {};

    container.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">Knowledge</h1>' +
      '</div>' +
      '<div class="admin-form" data-testid="knowledge-settings-panel">' +
        '<div class="banner banner-error" role="alert" hidden data-testid="knowledge-settings-load-error">' +
          "Couldn't load knowledge settings — showing nothing so as not to save defaults over your stored values. Reload to try again." +
        '</div>' +
        '<div class="admin-system-section" data-testid="knowledge-settings-chunking-section">' +
          '<div class="section-title admin-section-title">Chunking</div>' +
          '<p class="admin-system-text" data-testid="knowledge-chunking-note">' +
            'Applies to future indexing only — existing chunks are never re-chunked in place. ' +
            'The corpus stays mixed until affected items are re-indexed.' +
          '</p>' +
          '<div class="field-group">' +
            '<label for="ks-size-chars">Chunk size (characters)</label>' +
            '<input class="field-input" id="ks-size-chars" type="number" min="' + CHUNK_SIZE_MIN + '" max="' + CHUNK_SIZE_MAX + '" step="1" data-testid="knowledge-size-chars-input" />' +
            '<div class="field-hint">' + CHUNK_SIZE_MIN + '–' + CHUNK_SIZE_MAX + ' characters.</div>' +
            '<div class="field-error" id="field-error-size-chars" hidden data-testid="knowledge-size-chars-error"></div>' +
          '</div>' +
          '<div class="field-group">' +
            '<label for="ks-overlap-chars">Chunk overlap (characters)</label>' +
            '<input class="field-input" id="ks-overlap-chars" type="number" min="0" step="1" data-testid="knowledge-overlap-chars-input" />' +
            '<div class="field-hint" data-testid="knowledge-overlap-hint">At most half the chunk size.</div>' +
            '<div class="field-error" id="field-error-overlap-chars" hidden data-testid="knowledge-overlap-chars-error"></div>' +
          '</div>' +
        '</div>' +
        '<div class="admin-system-section" data-testid="knowledge-settings-monitoring-section">' +
          '<div class="section-title admin-section-title">Monitoring</div>' +
          '<p class="admin-system-text" data-testid="knowledge-monitoring-note">' +
            'Applies immediately — the watcher on/off switch and the reconciliation interval take effect on this save, not on the next indexing pass.' +
          '</p>' +
          '<div class="field-row admin-pf-row">' +
            '<label for="ks-watch-enabled">Watch registered folders for changes</label>' +
            '<label class="tool-enable-switch">' +
              '<input class="field-input" id="ks-watch-enabled" type="checkbox" data-testid="knowledge-watch-enabled-toggle" />' +
              '<span class="tool-enable-switch-track" aria-hidden="true"></span>' +
            '</label>' +
          '</div>' +
          '<div class="field-group">' +
            '<label for="ks-reconcile-interval">Reconciliation interval (seconds)</label>' +
            '<input class="field-input" id="ks-reconcile-interval" type="number" min="' + RECONCILE_MIN + '" max="' + RECONCILE_MAX + '" step="1" data-testid="knowledge-reconcile-interval-input" />' +
            '<div class="field-hint">' + RECONCILE_MIN + '–' + RECONCILE_MAX + ' seconds.</div>' +
            '<div class="field-error" id="field-error-reconcile-interval" hidden data-testid="knowledge-reconcile-interval-error"></div>' +
          '</div>' +
        '</div>' +
        '<div class="admin-system-flash" aria-live="polite" data-testid="knowledge-settings-flash"></div>' +
        '<button class="btn-filled-primary" type="button" data-testid="knowledge-settings-save-btn" disabled>Save</button>' +
        '<div class="admin-system-section" data-testid="knowledge-settings-embedding-section">' +
          '<div class="section-title admin-section-title">Embedding</div>' +
          '<p class="admin-system-text" data-testid="knowledge-embedding-readonly-reason">' +
            'Read-only: the embedding model is pinned to the bundled local model in this release. ' +
            'Changing it would invalidate every stored vector, and there is no operator path to change it.' +
          '</p>' +
          '<div class="admin-kv-row"><span class="admin-kv-key">Backend</span><span class="admin-kv-value" data-testid="knowledge-embedding-backend">—</span></div>' +
          '<div class="admin-kv-row"><span class="admin-kv-key">Model</span><span class="admin-kv-value" data-testid="knowledge-embedding-model">—</span></div>' +
          '<div class="admin-kv-row"><span class="admin-kv-key">Dimensions</span><span class="admin-kv-value" data-testid="knowledge-embedding-dim">—</span></div>' +
        '</div>' +
        '<div class="admin-system-section" data-testid="knowledge-settings-vector-store-section">' +
          '<div class="section-title admin-section-title">Vector Store</div>' +
          '<p class="admin-system-text" data-testid="knowledge-vector-store-readonly-reason">' +
            'Read-only: this record is written by the app when it builds the index, not chosen by the operator.' +
          '</p>' +
          '<div class="admin-kv-row"><span class="admin-kv-key">Backend</span><span class="admin-kv-value" data-testid="knowledge-vector-store-backend">—</span></div>' +
          '<div class="admin-kv-row"><span class="admin-kv-key">Data type</span><span class="admin-kv-value" data-testid="knowledge-vector-store-dtype">—</span></div>' +
        '</div>' +
      '</div>';

    wireKnowledgeSettings(container, onDirtyChange);
  }

  function wireKnowledgeSettings(container, onDirtyChange) {
    var sizeInput = container.querySelector('#ks-size-chars');
    var overlapInput = container.querySelector('#ks-overlap-chars');
    var watchToggle = container.querySelector('#ks-watch-enabled');
    var intervalInput = container.querySelector('#ks-reconcile-interval');
    var saveBtn = container.querySelector('[data-testid="knowledge-settings-save-btn"]');
    var flashEl = container.querySelector('[data-testid="knowledge-settings-flash"]');
    var loadErrorEl = container.querySelector('[data-testid="knowledge-settings-load-error"]');
    var sizeErrEl = container.querySelector('#field-error-size-chars');
    var overlapErrEl = container.querySelector('#field-error-overlap-chars');
    var intervalErrEl = container.querySelector('#field-error-reconcile-interval');

    // null until the first successful GET — recomputeDirty() no-ops while
    // null so a load failure can never read as "clean, safe to save
    // defaults over the stored values" (Edge Case in the leg artifact).
    var baseline = null;
    var dirty = false;

    function setFieldError(errEl, inputEl, message) {
      if (message) {
        errEl.textContent = message;
        errEl.hidden = false;
        inputEl.classList.add('is-invalid');
        inputEl.setAttribute('aria-describedby', errEl.id);
      } else {
        errEl.textContent = '';
        errEl.hidden = true;
        inputEl.classList.remove('is-invalid');
        inputEl.removeAttribute('aria-describedby');
      }
    }

    function validateSizeChars() {
      var v = parseInt(sizeInput.value, 10);
      if (isNaN(v) || v < CHUNK_SIZE_MIN || v > CHUNK_SIZE_MAX) {
        setFieldError(sizeErrEl, sizeInput, 'Chunk size must be between ' + CHUNK_SIZE_MIN + ' and ' + CHUNK_SIZE_MAX + '.');
        return false;
      }
      setFieldError(sizeErrEl, sizeInput, null);
      return true;
    }

    // Cross-field per L4-D3: the overlap bound is floor(size_chars / 2),
    // re-evaluated here on every call regardless of which input changed —
    // called from BOTH the size and the overlap input listeners (AC-6).
    function validateOverlapChars(sizeValid) {
      var v = parseInt(overlapInput.value, 10);
      if (isNaN(v) || v < 0) {
        setFieldError(overlapErrEl, overlapInput, 'Chunk overlap must be 0 or greater.');
        return false;
      }
      if (sizeValid) {
        var sizeVal = parseInt(sizeInput.value, 10);
        var maxOverlap = Math.floor(sizeVal / 2);
        if (v > maxOverlap) {
          setFieldError(overlapErrEl, overlapInput, 'Chunk overlap must not exceed ' + maxOverlap + ' (half the chunk size, rounded down).');
          return false;
        }
      }
      setFieldError(overlapErrEl, overlapInput, null);
      return true;
    }

    function validateInterval() {
      var v = parseInt(intervalInput.value, 10);
      if (isNaN(v) || v < RECONCILE_MIN || v > RECONCILE_MAX) {
        setFieldError(intervalErrEl, intervalInput, 'Reconciliation interval must be between ' + RECONCILE_MIN + ' and ' + RECONCILE_MAX + '.');
        return false;
      }
      setFieldError(intervalErrEl, intervalInput, null);
      return true;
    }

    function validateAll() {
      var sizeValid = validateSizeChars();
      var overlapValid = validateOverlapChars(sizeValid);
      var intervalValid = validateInterval();
      return sizeValid && overlapValid && intervalValid;
    }

    function currentSnapshot() {
      return {
        size_chars: sizeInput.value,
        overlap_chars: overlapInput.value,
        watch_enabled: watchToggle.checked,
        reconcile_interval_seconds: intervalInput.value
      };
    }

    function setDirtyState(d) {
      if (dirty === d) return;
      dirty = d;
      onDirtyChange(dirty);
    }

    function recomputeDirty() {
      if (!baseline) return;
      var cur = currentSnapshot();
      var isDirty = cur.size_chars !== baseline.size_chars ||
        cur.overlap_chars !== baseline.overlap_chars ||
        cur.watch_enabled !== baseline.watch_enabled ||
        cur.reconcile_interval_seconds !== baseline.reconcile_interval_seconds;
      setDirtyState(isDirty);
    }

    function revalidateAndUpdate() {
      var valid = validateAll();
      recomputeDirty();
      saveBtn.disabled = !dirty || !valid;
    }

    sizeInput.addEventListener('input', revalidateAndUpdate);
    overlapInput.addEventListener('input', revalidateAndUpdate);
    intervalInput.addEventListener('input', revalidateAndUpdate);
    watchToggle.addEventListener('change', revalidateAndUpdate);

    function formatDetail(detail) {
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) {
        var msgs = [];
        for (var i = 0; i < detail.length; i++) {
          var d = detail[i];
          msgs.push(d && d.msg ? d.msg : JSON.stringify(d));
        }
        return msgs.join('; ');
      }
      return 'Save failed.';
    }

    function applyLoadedSettings(data) {
      var chunking = data.chunking || {};
      var monitoring = data.monitoring || {};
      var embedding = data.embedding || {};
      var vectorStore = data.vector_store || {};

      sizeInput.value = chunking.size_chars;
      overlapInput.value = chunking.overlap_chars;
      watchToggle.checked = !!monitoring.watch_enabled;
      intervalInput.value = monitoring.reconcile_interval_seconds;

      setText('knowledge-embedding-backend', embedding.backend);
      setText('knowledge-embedding-model', embedding.model_id);
      setText('knowledge-embedding-dim', embedding.dim);
      setText('knowledge-vector-store-backend', vectorStore.backend);
      setText('knowledge-vector-store-dtype', vectorStore.dtype);

      baseline = currentSnapshot();
      revalidateAndUpdate();
    }

    function setText(testid, value) {
      var el = container.querySelector('[data-testid="' + testid + '"]');
      if (!el) return;
      el.textContent = (value === undefined || value === null) ? '—' : String(value);
    }

    function showFlash(text, cls) {
      flashEl.textContent = text;
      flashEl.className = 'admin-system-flash' + (cls ? ' ' + cls : '');
    }

    saveBtn.addEventListener('click', function () {
      if (!validateAll()) return;
      saveBtn.disabled = true;
      showFlash('', '');
      var payload = {
        chunking: {
          size_chars: parseInt(sizeInput.value, 10),
          overlap_chars: parseInt(overlapInput.value, 10)
        },
        monitoring: {
          watch_enabled: watchToggle.checked,
          reconcile_interval_seconds: parseInt(intervalInput.value, 10)
        }
      };
      fetch('/api/knowledge-settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function (r) {
        if (!r.ok) {
          return r.json().then(function (e) {
            throw new Error(formatDetail(e && e.detail));
          });
        }
        return r.json();
      }).then(function (data) {
        applyLoadedSettings(data);
        showFlash('Saved.', 'success');
        setTimeout(function () { showFlash('', ''); }, 3000);
      }).catch(function (err) {
        showFlash('Error: ' + err.message, 'error');
        revalidateAndUpdate();
      });
    });

    loadErrorEl.hidden = true;
    fetch('/api/knowledge-settings')
      .then(function (r) {
        if (!r.ok) throw new Error('load failed');
        return r.json();
      })
      .then(function (data) {
        applyLoadedSettings(data);
      })
      .catch(function () {
        loadErrorEl.hidden = false;
        saveBtn.disabled = true;
      });
  }

  window.App.admin.renderKnowledgeSettingsPage = renderKnowledgeSettingsPage;
})();
