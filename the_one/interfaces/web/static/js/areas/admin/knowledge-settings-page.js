(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Settings > Knowledge indexing (M24 F06 L04, DD-7; rebuilt on the control library in
  // M31 F4 L10, flight DD6 and DD8 14-18).
  //
  // The page is an App.ui.editorShell page variant (Cancel and Save top right, the
  // unsaved caption, busy and dirty from the shell) over four App.ui.sections: Chunking
  // and Monitoring are editable (one form, one explicit Save), Embedding and Vector store
  // are read-only facts with the reason stated on screen. Client-side bounds mirror the
  // server's exactly: size_chars 200-2000, reconcile_interval_seconds 10-86400, and
  // overlap_chars at most floor(size_chars / 2), re-checked whenever either changes.
  //
  // The save model (DD8-15 to DD8-18): the baseline is whatever the server last returned
  // ({chunking, monitoring}); the fields are never overwritten by a response, so text typed
  // during the request stays dirty against the new baseline. Save is busy through the shell
  // while the PUT is out (the fields stay live, one PUT at a time). The "Saved." line has
  // one timer, cleared by every attempt and on teardown. A 422 maps onto its field through
  // App.api.fieldErrors, an unnamed one onto the shell's error text. Focus returns through
  // App.focusAfter. The page returns {destroy()}: a late response from a torn-down page is
  // ignored (App.ui.util.latest).

  var CHUNK_SIZE_MIN = 200;
  var CHUNK_SIZE_MAX = 2000;
  var RECONCILE_MIN = 10;
  var RECONCILE_MAX = 86400;
  var SAVED_MS = 3000;
  var LOAD_ERROR = { testid: 'knowledge-settings-load-error' };
  var SAVE_ERROR = { testid: 'knowledge-settings-error' };
  var FIELD_NAMES = ['size_chars', 'overlap_chars', 'reconcile_interval_seconds'];

  var BACKEND_LABELS = { local: 'Local (bundled)', usearch: 'USearch' };
  var DTYPE_LABELS = { f16: '16-bit float', f32: '32-bit float', f64: '64-bit float' };

  var HINT_SIZE = CHUNK_SIZE_MIN + ' to ' + CHUNK_SIZE_MAX + ' characters.';
  var HINT_OVERLAP = 'At most half the chunk size.';
  var HINT_INTERVAL = '10 seconds to 24 hours';

  function plural(n, word) {
    return n + ' ' + word + (n === 1 ? '' : 's');
  }

  // Seconds as words: 900 -> "15 minutes", 90 -> "1 minute 30 seconds".
  function humanSeconds(total) {
    var parts = [];
    var rest = total;
    var units = [['day', 86400], ['hour', 3600], ['minute', 60], ['second', 1]];
    for (var i = 0; i < units.length; i++) {
      var n = Math.floor(rest / units[i][1]);
      if (n > 0) parts.push(plural(n, units[i][0]));
      rest -= n * units[i][1];
    }
    return parts.join(' ');
  }

  function label(map, value) {
    if (value === undefined || value === null) return '—';
    return Object.prototype.hasOwnProperty.call(map, value) ? map[value] : String(value);
  }

  function renderKnowledgeSettingsPage(container, callbacks) {
    var App = window.App;
    var el = App.ui.util.el;
    callbacks = callbacks || {};
    var onDirtyChange = callbacks.onDirtyChange || function () {};
    var gen = App.ui.util.latest();

    // null until the first successful GET: nothing is dirty and Save never enables while
    // null, so a load failure can never read as "clean, safe to save defaults over the
    // stored values".
    var baseline = null;
    var dirty = false;
    var saving = false;
    var destroyed = false;
    var savedTimer = null;
    var serverErrors = {};

    // ── Shell ──────────────────────────────────────────────────────────

    var shell = App.ui.editorShell({
      variant: 'page',
      title: 'Knowledge indexing',
      subtitle: 'Choose how your knowledge bases are split into chunks and kept up to date. ' +
        'The embedding model and the vector store are set by the app.',
      subtitleTestid: 'knowledge-settings-intro',
      errorRole: 'alert',
      actions: {
        cancel: { testid: 'knowledge-settings-cancel-btn', onClick: cancel },
        save: { testid: 'knowledge-settings-save-btn', onClick: save }
      }
    });
    var errorEl = shell.errorEl;

    function showShellError(text, loadFailed) {
      shell.setError(text || null);
      if (!errorEl) return;
      if (text) {
        errorEl.setAttribute('data-testid', (loadFailed ? LOAD_ERROR : SAVE_ERROR).testid);
      } else {
        errorEl.removeAttribute('data-testid');
      }
    }

    // The "Saved." line: a persistent polite region holding one App.ui.status that is
    // inserted when there is something to say and removed when there is not.
    var savedRegion = el('div', { role: 'status' });
    savedRegion.setAttribute('data-testid', 'knowledge-settings-flash');
    function clearSaved() {
      if (savedTimer) {
        clearTimeout(savedTimer);
        savedTimer = null;
      }
      savedRegion.textContent = '';
    }
    function showSaved() {
      clearSaved();
      savedRegion.appendChild(App.ui.status({ state: 'success', text: 'Saved.', live: 'off' }).el);
      savedTimer = setTimeout(function () {
        savedTimer = null;
        if (savedRegion.isConnected) savedRegion.textContent = '';
      }, SAVED_MS);
    }

    // ── Fields ─────────────────────────────────────────────────────────

    var sizeInput = App.ui.textInput({
      type: 'number', min: CHUNK_SIZE_MIN, max: CHUNK_SIZE_MAX, step: 1, width: 'short',
      testid: 'knowledge-size-chars-input'
    });
    var overlapInput = App.ui.textInput({
      type: 'number', min: 0, step: 1, width: 'short',
      testid: 'knowledge-overlap-chars-input'
    });
    var intervalInput = App.ui.textInput({
      type: 'number', min: RECONCILE_MIN, max: RECONCILE_MAX, step: 1, width: 'short',
      testid: 'knowledge-reconcile-interval-input'
    });
    var echoEl = el('span', { className: 'knowledge-interval-echo' });
    echoEl.setAttribute('data-testid', 'knowledge-reconcile-interval-echo');
    var intervalRow = el('div', { className: 'knowledge-interval-row' }, [intervalInput, echoEl]);

    var sizeField = App.ui.field({
      label: 'Chunk size (characters)', control: sizeInput, hint: HINT_SIZE,
      errorTestid: 'knowledge-size-chars-error'
    });
    var overlapField = App.ui.field({
      label: 'Chunk overlap (characters)', control: overlapInput, hint: HINT_OVERLAP,
      hintTestid: 'knowledge-overlap-hint', errorTestid: 'knowledge-overlap-chars-error'
    });
    var intervalField = App.ui.field({
      label: 'Reconciliation interval (seconds)', control: intervalInput, host: intervalRow,
      hint: HINT_INTERVAL, errorTestid: 'knowledge-reconcile-interval-error'
    });

    var watchToggle = App.ui.toggle({
      label: 'Watch registered folders for changes',
      testid: 'knowledge-watch-enabled-toggle',
      onChange: function () { revalidate(); }
    });
    var watchInput = watchToggle.control;

    // ── Read-only facts ────────────────────────────────────────────────

    var embeddingFacts = App.ui.facts({ rows: embeddingRows(null) });
    var vectorFacts = App.ui.facts({ rows: vectorRows(null) });

    function embeddingRows(e) {
      e = e || {};
      return [
        { label: 'Backend', value: label(BACKEND_LABELS, e.backend),
          valueTestid: 'knowledge-embedding-backend' },
        { label: 'Model', value: label({}, e.model_id), valueTestid: 'knowledge-embedding-model' },
        { label: 'Dimensions', value: label({}, e.dim), valueTestid: 'knowledge-embedding-dim' }
      ];
    }
    function vectorRows(v) {
      v = v || {};
      return [
        { label: 'Backend', value: label(BACKEND_LABELS, v.backend),
          valueTestid: 'knowledge-vector-store-backend' },
        { label: 'Data type', value: label(DTYPE_LABELS, v.dtype),
          valueTestid: 'knowledge-vector-store-dtype' }
      ];
    }

    // ── Validation ─────────────────────────────────────────────────────

    function intOf(input) {
      var v = parseInt(input.value, 10);
      return isNaN(v) ? null : v;
    }

    // Each check returns an error text or null. The overlap is checked against its own
    // limit, floor(size / 2), even while the size itself is invalid: the size typed so far
    // counts when it is a number, and the saved size stands in when it is blank.
    function sizeError() {
      var v = intOf(sizeInput);
      if (v === null || v < CHUNK_SIZE_MIN || v > CHUNK_SIZE_MAX) {
        return 'Chunk size must be between ' + CHUNK_SIZE_MIN + ' and ' + CHUNK_SIZE_MAX + '.';
      }
      return null;
    }
    function overlapError() {
      var v = intOf(overlapInput);
      if (v === null || v < 0) return 'Chunk overlap must be 0 or greater.';
      var size = intOf(sizeInput);
      if (size === null && baseline) size = baseline.size_chars;
      if (size !== null) {
        var max = Math.floor(size / 2);
        if (v > max) {
          return 'Chunk overlap must not exceed ' + max + ' (half the chunk size, rounded down).';
        }
      }
      return null;
    }
    function intervalError() {
      var v = intOf(intervalInput);
      if (v === null || v < RECONCILE_MIN || v > RECONCILE_MAX) {
        return 'Reconciliation interval must be between ' + RECONCILE_MIN + ' and ' +
          RECONCILE_MAX + '.';
      }
      return null;
    }

    // The error replaces the hint while it shows (A21), and the hint comes back with it.
    function paintField(field, hint, name, clientError) {
      var text = clientError || serverErrors[name] || null;
      field.setError(text);
      field.setHint(text ? null : hint);
    }

    function paintEcho() {
      var v = intOf(intervalInput);
      echoEl.textContent = (v !== null && v >= RECONCILE_MIN && v <= RECONCILE_MAX)
        ? humanSeconds(v) : '';
    }

    function snapshot() {
      return {
        size_chars: sizeInput.value,
        overlap_chars: overlapInput.value,
        watch_enabled: watchInput.checked,
        reconcile_interval_seconds: intervalInput.value
      };
    }

    function isDirty() {
      if (!baseline) return false;
      var cur = snapshot();
      return cur.size_chars !== String(baseline.size_chars) ||
        cur.overlap_chars !== String(baseline.overlap_chars) ||
        cur.watch_enabled !== baseline.watch_enabled ||
        cur.reconcile_interval_seconds !== String(baseline.reconcile_interval_seconds);
    }

    // One pass: validate, paint, then drive the shell and the leave guard. Save is enabled
    // only for a dirty, valid form that is not already saving (the shell holds the busy
    // state; validity is layered over it here).
    function revalidate() {
      var e1 = sizeError();
      var e2 = overlapError();
      var e3 = intervalError();
      paintField(sizeField, HINT_SIZE, 'size_chars', e1);
      paintField(overlapField, HINT_OVERLAP, 'overlap_chars', e2);
      paintField(intervalField, HINT_INTERVAL, 'reconcile_interval_seconds', e3);
      paintEcho();
      var nowDirty = isDirty();
      if (nowDirty !== dirty) {
        dirty = nowDirty;
        onDirtyChange(dirty);
      }
      shell.setDirty(dirty);
      shell.setBusy(saving);
      var valid = !e1 && !e2 && !e3 && !Object.keys(serverErrors).length;
      if (!valid) shell.saveButton.disabled = true;
      return !e1 && !e2 && !e3;
    }

    function onInput(name) {
      return function () {
        delete serverErrors[name];
        showShellError(null);
        revalidate();
      };
    }
    sizeInput.addEventListener('input', onInput('size_chars'));
    overlapInput.addEventListener('input', onInput('overlap_chars'));
    intervalInput.addEventListener('input', onInput('reconcile_interval_seconds'));

    // ── Loading and the baseline ───────────────────────────────────────

    function setBaseline(data) {
      var chunking = data.chunking || {};
      var monitoring = data.monitoring || {};
      baseline = {
        size_chars: chunking.size_chars,
        overlap_chars: chunking.overlap_chars,
        watch_enabled: !!monitoring.watch_enabled,
        reconcile_interval_seconds: monitoring.reconcile_interval_seconds
      };
      embeddingFacts.set(embeddingRows(data.embedding));
      vectorFacts.set(vectorRows(data.vector_store));
    }

    // Fields take the baseline (the first load and Cancel only; a Save response never
    // touches them).
    function fillFromBaseline() {
      sizeInput.value = baseline.size_chars;
      overlapInput.value = baseline.overlap_chars;
      intervalInput.value = baseline.reconcile_interval_seconds;
      watchToggle.setChecked(baseline.watch_enabled);
    }

    function cancel() {
      if (!baseline || saving) return;
      var focus = App.focusAfter.begin(shell.cancelButton);
      serverErrors = {};
      showShellError(null);
      clearSaved();
      fillFromBaseline();
      revalidate();
      App.focusAfter.restore(focus, shell.titleEl);
    }

    // ── Save ───────────────────────────────────────────────────────────

    function save() {
      if (saving || !baseline || !revalidate()) return;
      saving = true;
      serverErrors = {};
      clearSaved();
      showShellError(null);
      var focus = App.focusAfter.begin(shell.saveButton);
      var token = gen.next();
      var payload = {
        chunking: { size_chars: intOf(sizeInput), overlap_chars: intOf(overlapInput) },
        monitoring: {
          watch_enabled: watchInput.checked,
          reconcile_interval_seconds: intOf(intervalInput)
        }
      };
      revalidate();
      function settle() {
        saving = false;
        revalidate();
        // The Save button is disabled when nothing is left to save; the page title then
        // takes the focus the click had.
        App.focusAfter.restore(focus, function () {
          return shell.saveButton.disabled ? shell.titleEl : shell.saveButton;
        });
      }
      App.api.fetchJson('/api/knowledge-settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function (data) {
        if (!gen.isCurrent(token)) return;
        setBaseline(data);
        showSaved();
        settle();
      }).catch(function (err) {
        if (!gen.isCurrent(token)) return;
        var mapped = App.api.fieldErrors(err, FIELD_NAMES);
        FIELD_NAMES.forEach(function (name) {
          if (mapped.fields[name]) serverErrors[name] = mapped.fields[name];
        });
        showShellError(mapped.text || (Object.keys(mapped.fields).length ? '' : 'Save failed.'),
          false);
        settle();
      });
    }

    function load() {
      var token = gen.next();
      App.api.fetchJson('/api/knowledge-settings').then(function (data) {
        if (!gen.isCurrent(token)) return;
        setBaseline(data);
        fillFromBaseline();
        revalidate();
      }).catch(function () {
        if (!gen.isCurrent(token)) return;
        showShellError("Couldn't load the knowledge settings. Reload to try again.",
          true);
        [sizeInput, overlapInput, intervalInput, watchInput].forEach(function (input) {
          input.disabled = true;
        });
      });
    }

    // ── Layout ─────────────────────────────────────────────────────────

    var chunking = App.ui.section({
      title: 'Chunking', titleTag: 'h2', layout: 'stack', inset: 'none',
      testid: 'knowledge-settings-chunking-section',
      description: 'Changes apply to files indexed from now on. Files already indexed keep ' +
        'their current chunks until they are re-indexed.',
      descriptionTestid: 'knowledge-chunking-note',
      children: [sizeField.el, overlapField.el]
    });
    var monitoring = App.ui.section({
      title: 'Monitoring', titleTag: 'h2', layout: 'stack', inset: 'none',
      testid: 'knowledge-settings-monitoring-section',
      description: 'Changes take effect as soon as you save, not at the next indexing pass.',
      descriptionTestid: 'knowledge-monitoring-note',
      children: [watchToggle.el, intervalField.el]
    });
    var embedding = App.ui.section({
      title: 'Embedding', titleTag: 'h2', layout: 'stack', inset: 'none',
      testid: 'knowledge-settings-embedding-section',
      description: 'Fixed in this release: the app uses one built-in embedding model. ' +
        'Changing it would make every stored vector unusable.',
      descriptionTestid: 'knowledge-embedding-readonly-reason',
      children: [embeddingFacts.el]
    });
    var vectorStore = App.ui.section({
      title: 'Vector store', titleTag: 'h2', layout: 'stack', inset: 'none',
      testid: 'knowledge-settings-vector-store-section',
      description: 'Set by the app when it builds the index. It isn’t something you can change.',
      descriptionTestid: 'knowledge-vector-store-readonly-reason',
      children: [vectorFacts.el]
    });

    container.textContent = '';
    container.appendChild(shell.el);
    var body = el('div', { className: 'admin-form' }, [
      savedRegion, chunking.el, monitoring.el, embedding.el, vectorStore.el
    ]);
    body.setAttribute('data-testid', 'knowledge-settings-panel');
    container.appendChild(body);

    shell.setDirty(false);
    load();

    return {
      // Teardown only: every in-flight response is ignored from here and the "Saved."
      // timer is cleared. Never touches the leave guard's flag.
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        gen.invalidate();
        clearSaved();
        App.focusAfter.cancel();
      }
    };
  }

  window.App.admin.renderKnowledgeSettingsPage = renderKnowledgeSettingsPage;
})();
