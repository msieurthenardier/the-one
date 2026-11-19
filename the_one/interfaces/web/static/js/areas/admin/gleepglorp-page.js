(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Settings > GleepGlorp (M36 F1 L03, flight DD7; screen 1 of the approved board; the
  // Memory section is L06 and acts at once, outside the form's Save).
  //
  // The page is an App.ui.editorShell page variant (Cancel and Save top right, the unsaved
  // caption, busy and dirty from the shell) over two App.ui.sections: Model (a provider
  // select and a model select) and Behavior (the GleepGlorp, Web access and Memory switches
  // and "Keep chats for N days"). One form, one explicit Save through PUT /api/gleepglorp.
  //
  // The save model is the Knowledge indexing page's: the baseline is whatever the server last
  // returned; the fields are never overwritten by a Save response, so text typed during the
  // request stays dirty against the new baseline. A 422 lands on its field through
  // App.api.fieldErrors, an unnamed one on the shell's error text. Focus returns through
  // App.focusAfter. The page returns {destroy()}: a late response from a torn-down page is
  // ignored (App.ui.util.latest).
  //
  // The two selects never throw (App.ui.select refuses an empty option list and an unknown
  // value): each always starts with a placeholder option, and the saved value is added as an
  // option when the list lacks it (a removed provider, a model the list did not return).
  // The model select is built once and its options are replaced, with a loading and an error
  // state, whenever the provider changes.

  var RETENTION_MIN = 1;
  var RETENTION_MAX = 365;
  var SAVED_MS = 3000;
  var LOAD_ERROR = { testid: 'gleepglorp-load-error' };
  var SAVE_ERROR = { testid: 'gleepglorp-error' };
  var FIELD_NAMES = ['provider_config_id', 'model', 'retention_days'];
  var PROVIDER_PLACEHOLDER = 'Choose a model provider…';
  var MODEL_PLACEHOLDER = 'Choose a model…';
  var REMOVED_PROVIDER = 'Removed provider';
  var HINT_MODEL = 'Small local models may struggle.';
  var HINT_RETENTION = RETENTION_MIN + ' to ' + RETENTION_MAX + ' days.';

  function renderGleepGlorpPage(container, callbacks) {
    var App = window.App;
    var el = App.ui.util.el;
    callbacks = callbacks || {};
    var onDirtyChange = callbacks.onDirtyChange || function () {};
    var gen = App.ui.util.latest();
    var modelGen = App.ui.util.latest();

    // null until the first successful GET: nothing is dirty and Save never enables while
    // null, so a load failure can never read as "clean, safe to save defaults over the
    // stored values".
    var baseline = null;
    var dirty = false;
    var saving = false;
    var destroyed = false;
    var savedTimer = null;
    var serverErrors = {};
    var providerIds = [];
    var modelLoadFailed = false;

    // ── Shell ──────────────────────────────────────────────────────────

    var shell = App.ui.editorShell({
      variant: 'page',
      title: 'GleepGlorp',
      subtitle: 'The built-in assistant that helps you set up and tune the app.',
      subtitleTestid: 'gleepglorp-intro',
      errorRole: 'alert',
      actions: {
        cancel: { testid: 'gleepglorp-cancel-btn', onClick: cancel },
        save: { testid: 'gleepglorp-save-btn', onClick: save }
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

    // The "Saved." line: a persistent polite region holding one App.ui.status.
    var savedRegion = el('div', { role: 'status' });
    savedRegion.setAttribute('data-testid', 'gleepglorp-flash');
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

    function option(value, text) {
      var o = el('option', { text: text });
      o.value = value;
      return o;
    }

    var providerSelect = App.ui.select({
      options: [{ value: '', label: PROVIDER_PLACEHOLDER }],
      value: '',
      testid: 'gleepglorp-provider',
      onChange: function () {
        delete serverErrors.provider_config_id;
        delete serverErrors.model;
        showShellError(null);
        loadModels(providerSelect.value, '');
        revalidate();
      }
    });
    var modelSelect = App.ui.select({
      options: [{ value: '', label: MODEL_PLACEHOLDER }],
      value: '',
      disabled: true,
      testid: 'gleepglorp-model',
      onChange: function () {
        delete serverErrors.model;
        showShellError(null);
        revalidate();
      }
    });
    var retentionInput = App.ui.textInput({
      type: 'number', min: RETENTION_MIN, max: RETENTION_MAX, step: 1, width: 'short',
      testid: 'gleepglorp-retention'
    });
    var daysEl = el('span', { className: 'gleepglorp-days', text: 'days' });
    var retentionRow = el('div', { className: 'gleepglorp-retention-row' }, [retentionInput, daysEl]);

    var providerField = App.ui.field({
      label: 'Provider', control: providerSelect, errorTestid: 'gleepglorp-provider-error'
    });
    var modelField = App.ui.field({
      label: 'Model', control: modelSelect, hint: HINT_MODEL, hintTestid: 'gleepglorp-model-hint',
      errorTestid: 'gleepglorp-model-error'
    });
    var retentionField = App.ui.field({
      label: 'Keep chats for', control: retentionInput, host: retentionRow, hint: HINT_RETENTION,
      errorTestid: 'gleepglorp-retention-error'
    });

    function onToggle() {
      showShellError(null);
      revalidate();
    }
    var enabledToggle = App.ui.toggle({
      label: 'GleepGlorp', hint: 'Offer GleepGlorp in Chats.',
      testid: 'gleepglorp-enabled', onChange: onToggle
    });
    var webToggle = App.ui.toggle({
      label: 'Web access', hint: 'Search the web and read pages.',
      testid: 'gleepglorp-web', onChange: onToggle
    });
    // Under the Web access switch, while it is on and no search engine is usable: web
    // search is set up on the Built-in tools page (a keyed engine with a field empty).
    var searchAvailable = true;
    var webHintLink = el('a', { text: 'Set up web search' });
    webHintLink.setAttribute('href',
      App.router.href({ destination: 'settings', section: 'tools', id: 'web_search' }));
    webHintLink.setAttribute('data-testid', 'gleepglorp-web-hint-link');
    var webHintText = document.createTextNode(
      "Web search isn't set up, so GleepGlorp can only read pages you give it. ");
    // A persistent live region (WCAG 4.1.3): always in the DOM, its content set or cleared,
    // so a screen reader announces the hint appearing.
    var webHint = el('p', { className: 'gleepglorp-web-hint' });
    webHint.setAttribute('role', 'status');
    webHint.setAttribute('data-testid', 'gleepglorp-web-hint');
    function paintWebHint() {
      var show = webToggle.control.checked && !searchAvailable;
      var shown = webHint.firstChild !== null;
      if (show === shown) return;
      if (show) {
        webHint.appendChild(webHintText);
        webHint.appendChild(webHintLink);
      } else {
        webHint.textContent = '';
      }
    }
    // The notes switch lives in the Notes section and saves at once (like the agent's);
    // the setting key stays `memory`. saveMemorySwitch is defined with the notes code below.
    var memoryToggle = App.ui.toggle({
      label: 'Let GleepGlorp keep notes',
      testid: 'gleepglorp-memory', onChange: function (checked) { saveMemorySwitch(checked); }
    });

    // ── Provider and model options ─────────────────────────────────────

    function setProviderOptions(providers, savedId) {
      var sel = providerSelect;
      sel.textContent = '';
      sel.appendChild(option('', PROVIDER_PLACEHOLDER));
      providerIds = [];
      providers.forEach(function (p) {
        providerIds.push(p.id);
        sel.appendChild(option(p.id, p.name || p.id));
      });
      if (savedId && providerIds.indexOf(savedId) === -1) {
        sel.appendChild(option(savedId, REMOVED_PROVIDER));
      }
      sel.value = savedId || '';
    }

    function setModelOptions(models, selected) {
      var sel = modelSelect;
      sel.textContent = '';
      sel.appendChild(option('', MODEL_PLACEHOLDER));
      var seen = false;
      models.forEach(function (m) {
        var id = m && (m.id || m.name);
        if (!id) return;
        if (id === selected) seen = true;
        sel.appendChild(option(id, id));
      });
      // The saved model stays an option when the list lacks it or failed to load.
      if (selected && !seen) sel.appendChild(option(selected, selected));
      sel.value = selected || '';
    }

    // Replace the model options for `providerId`, keeping `selected` when it is there.
    function loadModels(providerId, selected) {
      var token = modelGen.next();
      modelLoadFailed = false;
      if (!providerId) {
        setModelOptions([], '');
        modelSelect.disabled = true;
        modelSelect.setAttribute('aria-busy', 'false');
        paintModelHint();
        return;
      }
      // Loading: the saved model stays selectable while the list is fetched.
      modelSelect.textContent = '';
      modelSelect.appendChild(option('', 'Loading models…'));
      if (selected) modelSelect.appendChild(option(selected, selected));
      modelSelect.value = selected || '';
      modelSelect.disabled = true;
      modelSelect.setAttribute('aria-busy', 'true');
      App.api.fetchJson('/api/providers/' + encodeURIComponent(providerId) + '/models')
        .then(function (models) {
          if (!modelGen.isCurrent(token)) return;
          var current = modelSelect.value;
          setModelOptions(Array.isArray(models) ? models : [], current || selected || '');
          modelSelect.disabled = false;
          modelSelect.setAttribute('aria-busy', 'false');
          revalidate();
        }).catch(function () {
          if (!modelGen.isCurrent(token)) return;
          modelLoadFailed = true;
          setModelOptions([], modelSelect.value || selected || '');
          modelSelect.disabled = false;
          modelSelect.setAttribute('aria-busy', 'false');
          revalidate();
        });
    }

    function paintModelHint() {
      var text = serverErrors.model || null;
      modelField.setError(text);
      if (text) {
        modelField.setHint(null);
      } else if (modelLoadFailed) {
        modelField.setHint("Couldn't load this provider's models. " + HINT_MODEL);
      } else {
        modelField.setHint(HINT_MODEL);
      }
    }

    // A saved provider that no longer exists (state provider_missing) is a warning, not a
    // crash: the select shows "Removed provider" and says what to do.
    function providerHint() {
      var v = providerSelect.value;
      return v && providerIds.indexOf(v) === -1
        ? 'The provider GleepGlorp used was removed. Choose another one.' : null;
    }

    // ── Validation ─────────────────────────────────────────────────────

    function retentionValue() {
      var v = parseInt(retentionInput.value, 10);
      return isNaN(v) || String(v) !== String(retentionInput.value).trim() ? null : v;
    }
    function retentionError() {
      var v = retentionValue();
      if (v === null || v < RETENTION_MIN || v > RETENTION_MAX) {
        return 'Keep chats for ' + RETENTION_MIN + ' to ' + RETENTION_MAX + ' days.';
      }
      return null;
    }

    // The error replaces the hint while it shows (A21), and the hint comes back with it.
    function paintField(field, hint, name, clientError) {
      var text = clientError || serverErrors[name] || null;
      field.setError(text);
      field.setHint(text ? null : hint);
    }

    function snapshot() {
      return {
        enabled: enabledToggle.control.checked,
        provider_config_id: providerSelect.value || null,
        model: modelSelect.value || null,
        web_access: webToggle.control.checked,
        retention_days: retentionInput.value
      };
    }

    function isDirty() {
      if (!baseline) return false;
      var cur = snapshot();
      return cur.enabled !== baseline.enabled ||
        cur.provider_config_id !== baseline.provider_config_id ||
        cur.model !== baseline.model ||
        cur.web_access !== baseline.web_access ||
        cur.retention_days !== String(baseline.retention_days);
    }

    // One pass: validate, paint, then drive the shell and the leave guard.
    function revalidate() {
      var retErr = retentionError();
      paintField(providerField, providerHint(), 'provider_config_id', null);
      paintModelHint();
      paintField(retentionField, HINT_RETENTION, 'retention_days', retErr);
      paintWebHint();
      var nowDirty = isDirty();
      if (nowDirty !== dirty) {
        dirty = nowDirty;
        onDirtyChange(dirty);
      }
      shell.setDirty(dirty);
      shell.setBusy(saving);
      var valid = !retErr && !Object.keys(serverErrors).length;
      if (!valid) shell.saveButton.disabled = true;
      return !retErr;
    }

    retentionInput.addEventListener('input', function () {
      delete serverErrors.retention_days;
      showShellError(null);
      revalidate();
    });

    // ── Loading and the baseline ───────────────────────────────────────

    function setBaseline(data) {
      searchAvailable = data.web_search_available !== false;
      baseline = {
        enabled: !!data.enabled,
        provider_config_id: data.provider_config_id || null,
        model: data.model || null,
        web_access: !!data.web_access,
        memory: !!data.memory,
        retention_days: data.retention_days,
        state: data.state
      };
    }

    // Fields take the baseline (the first load and Cancel only; a Save response never
    // touches them).
    function fillFromBaseline(providers) {
      setProviderOptions(providers || [], baseline.provider_config_id);
      loadModels(baseline.provider_config_id || '', baseline.model || '');
      enabledToggle.setChecked(baseline.enabled);
      webToggle.setChecked(baseline.web_access);
      memoryToggle.setChecked(baseline.memory);
      retentionInput.value = baseline.retention_days;
    }

    var providersCache = [];

    function cancel() {
      if (!baseline || saving) return;
      var focus = App.focusAfter.begin(shell.cancelButton);
      serverErrors = {};
      showShellError(null);
      clearSaved();
      fillFromBaseline(providersCache);
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
      var cur = snapshot();
      var payload = {
        enabled: cur.enabled,
        provider_config_id: cur.provider_config_id,
        model: cur.model,
        web_access: cur.web_access,
        memory: baseline.memory,
        retention_days: retentionValue()
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
      App.api.fetchJson('/api/gleepglorp', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function (data) {
        if (!gen.isCurrent(token)) return;
        setBaseline(data);
        App.gleepglorp.prime(data);
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
      Promise.all([
        App.gleepglorp.get({ force: true }),
        App.store.get('providers', { force: true }).catch(function () { return []; })
      ]).then(function (results) {
        if (!gen.isCurrent(token)) return;
        providersCache = results[1] || [];
        setBaseline(results[0]);
        fillFromBaseline(providersCache);
        revalidate();
      }).catch(function () {
        if (!gen.isCurrent(token)) return;
        showShellError("Couldn't load the GleepGlorp settings. Reload to try again.", true);
        [providerSelect, modelSelect, retentionInput, enabledToggle.control, webToggle.control,
          memoryToggle.control].forEach(function (input) { input.disabled = true; });
      });
    }

    // ── Notes (M36 F1 L06; first called Memory) ────────────────────────────────────────────
    //
    // GleepGlorp's saved notes, listed with the agent Notes tab's row (App.studio.noteRow).
    // Delete and Clear all act at once (they are not part of Save). The list reloads after
    // each, when the saved settings change (App.gleepglorp subscription, which a Save
    // primes) and on a notes push from another window. Note text is rendered with
    // textContent only (the shared row does so).

    var memoryGen = App.ui.util.latest();
    var memoryNotes = [];
    var memoryEnabled = true;
    var memoryBusy = false;
    var memoryLimits = null;
    var memoryUsed = 0;
    var memorySwitchGen = App.ui.util.latest();
    var MEMORY_OFF = 'Notes are off. GleepGlorp keeps no new notes; these stay until you ' +
      'delete them.';

    var memoryError = el('p', { className: 'gleepglorp-memory-error', role: 'alert' });
    memoryError.setAttribute('data-testid', 'gleepglorp-memory-error');
    memoryError.hidden = true;
    var memoryOff = el('p', { className: 'gleepglorp-memory-off', text: MEMORY_OFF });
    memoryOff.setAttribute('data-testid', 'gleepglorp-memory-off');
    memoryOff.hidden = true;
    var memoryList = el('div', { className: 'gleepglorp-memory-list' });
    memoryList.setAttribute('data-testid', 'gleepglorp-memory-list');
    var memorySectionEl = null;

    var header = App.studio.buildNotesHeaderAction(function () { clearMemory(); });
    var usageEl = header.usageEl;
    var clearBtn = header.clearBtn;
    usageEl.setAttribute('data-testid', 'gleepglorp-memory-usage');
    clearBtn.setAttribute('data-testid', 'gleepglorp-memory-clear');
    header.el.appendChild(usageEl);
    header.el.appendChild(clearBtn);

    function showMemoryError(text) {
      memoryError.textContent = text || '';
      memoryError.hidden = !text;
    }

    function focusAfterMemory(neighbourId) {
      var target = neighbourId && memoryList.querySelector(
        '[data-id="' + neighbourId + '"] [data-testid="gleepglorp-memory-delete"]');
      if (!target && memorySectionEl) {
        memorySectionEl.setAttribute('tabindex', '-1');
        target = memorySectionEl;
      }
      if (target) target.focus();
    }

    function renderMemory() {
      memoryOff.hidden = memoryEnabled;
      clearBtn.hidden = !memoryNotes.length;
      clearBtn.disabled = memoryBusy;
      usageEl.textContent = App.studio.notesUsageText(memoryUsed, memoryLimits);
      memoryList.textContent = '';
      if (!memoryNotes.length) {
        var empty = el('p', { className: 'gleepglorp-memory-empty', text: 'No saved notes yet.' });
        empty.setAttribute('data-testid', 'gleepglorp-memory-empty');
        memoryList.appendChild(empty);
        return;
      }
      var ul = el('ul', { className: 'notes-list' });
      ul.setAttribute('aria-label', 'GleepGlorp notes');
      memoryNotes.forEach(function (note) {
        var del = App.studio.rulesNotesShared.buildDeleteButton({
          ariaLabel: 'Delete note ' + note.number,
          iconOnly: true,
          onConfirm: function (revert) { deleteNote(note, revert); }
        });
        del.setAttribute('data-testid', 'gleepglorp-memory-delete');
        del.disabled = memoryBusy;
        var actions = el('div', { className: 'rules-row-actions notes-row-actions' }, [del]);
        ul.appendChild(App.studio.noteRow(note, { actions: actions }));
      });
      memoryList.appendChild(ul);
    }

    function loadMemory() {
      var token = memoryGen.next();
      return App.api.fetchJson('/api/gleepglorp/notes').then(function (body) {
        if (destroyed || !memoryGen.isCurrent(token)) return;
        body = body || {};
        memoryEnabled = body.enabled !== false;
        memoryNotes = body.notes || [];
        memoryLimits = body.limits || null;
        memoryUsed = body.usage && typeof body.usage.total_chars === 'number'
          ? body.usage.total_chars
          : memoryNotes.reduce(function (n, x) { return n + x.text.length; }, 0);
        memoryToggle.setChecked(memoryEnabled);
        renderMemory();
      }).catch(function () {
        if (destroyed || !memoryGen.isCurrent(token)) return;
        showMemoryError("Couldn't load GleepGlorp's notes.");
      });
    }

    // The switch saves at once: the last SAVED settings with `memory` toggled, never the
    // form's unsaved values; only the baseline's `memory` moves, so an unsaved Model or
    // Behavior edit stays unsaved. An error puts the switch back.
    var memorySwitchBusy = false;
    var memorySwitchPending = false;
    function setMemorySwitchBusy(on) {
      if (on) {
        memoryToggle.control.setAttribute('aria-busy', 'true');
        memoryToggle.control.setAttribute('aria-disabled', 'true');
      } else {
        memoryToggle.control.removeAttribute('aria-busy');
        memoryToggle.control.removeAttribute('aria-disabled');
      }
    }
    function saveMemorySwitch(checked) {
      if (!baseline) { memoryToggle.setChecked(!checked); return; }
      // Focus stays on the switch while saving: a busy guard and aria-busy/aria-disabled,
      // never `disabled` (which drops focus). A change made meanwhile is put back.
      if (memorySwitchBusy) { memoryToggle.setChecked(memorySwitchPending); return; }
      memorySwitchBusy = true;
      memorySwitchPending = checked;
      setMemorySwitchBusy(true);
      var token = memorySwitchGen.next();
      showMemoryError(null);
      App.api.fetchJson('/api/gleepglorp', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: baseline.enabled,
          provider_config_id: baseline.provider_config_id,
          model: baseline.model,
          web_access: baseline.web_access,
          memory: checked,
          retention_days: baseline.retention_days
        })
      }).then(function (data) {
        if (destroyed || !memorySwitchGen.isCurrent(token)) return;
        baseline.memory = !!data.memory;
        memoryEnabled = baseline.memory;
        memorySwitchBusy = false;
        setMemorySwitchBusy(false);
        memoryToggle.setChecked(baseline.memory);
        renderMemory();
        App.gleepglorp.prime(data);
        revalidate();
      }).catch(function (err) {
        if (destroyed || !memorySwitchGen.isCurrent(token)) return;
        memorySwitchBusy = false;
        setMemorySwitchBusy(false);
        memoryToggle.setChecked(baseline.memory);
        var mapped = App.api.fieldErrors(err, FIELD_NAMES);
        showMemoryError(mapped.text || "Couldn't change the notes setting. Try again.");
      });
    }

    function mutateMemory(request, after) {
      if (memoryBusy) return Promise.resolve();
      memoryBusy = true;
      showMemoryError(null);
      renderMemory();
      return request().then(function () {
        memoryBusy = false;
        return loadMemory().then(function () { if (after) after(); });
      }).catch(function (err) {
        memoryBusy = false;
        showMemoryError((err && err.status === 404)
          ? 'That note is already gone.' : "Couldn't change the notes. Try again.");
        return loadMemory();
      });
    }

    function deleteNote(note, revert) {
      var idx = memoryNotes.indexOf(note);
      var neighbour = memoryNotes[idx + 1] || memoryNotes[idx - 1] || null;
      mutateMemory(function () {
        return App.api.fetchJson('/api/gleepglorp/notes/' + encodeURIComponent(note.id),
          { method: 'DELETE' });
      }, function () { focusAfterMemory(neighbour && neighbour.id); }).then(function () {
        if (revert) revert();
      });
    }

    function clearMemory() {
      var n = memoryNotes.length;
      if (!n) return;
      App.confirmDialog({
        title: 'Clear all notes',
        message: 'Clear all ' + n + ' ' + (n === 1 ? 'note' : 'notes') +
          ' GleepGlorp has saved? This can’t be undone.',
        confirmText: 'Clear all',
        cancelText: 'Cancel',
        opener: clearBtn,
        onConfirm: function () {
          mutateMemory(function () {
            return App.api.fetchJson('/api/gleepglorp/notes', { method: 'DELETE' });
          }, function () { focusAfterMemory(null); });
        }
      });
    }

    var unsubscribe = App.gleepglorp.subscribe(function () { loadMemory(); });
    function onNotesPush() { loadMemory(); }
    window.addEventListener('gleepglorp-notes-changed', onNotesPush);

    // ── Layout ─────────────────────────────────────────────────────────

    var model =App.ui.section({
      title: 'Model', titleTag: 'h2', layout: 'stack', inset: 'none',
      testid: 'gleepglorp-model-section',
      children: [providerField.el, modelField.el]
    });
    var behavior = App.ui.section({
      title: 'Behavior', titleTag: 'h2', layout: 'stack', inset: 'none',
      testid: 'gleepglorp-behavior-section',
      children: [enabledToggle.el, webToggle.el, webHint, retentionField.el]
    });
    var memorySection = App.ui.section({
      title: 'Notes', titleTag: 'h2', layout: 'stack', inset: 'none',
      testid: 'gleepglorp-memory-section',
      action: header.el,
      children: [memoryToggle.el, memoryOff, memoryError, memoryList]
    });
    memorySectionEl = memorySection.el;

    container.textContent = '';
    container.appendChild(shell.el);
    var body = el('div', { className: 'admin-form' }, [savedRegion, model.el, behavior.el, memorySection.el]);
    body.setAttribute('data-testid', 'gleepglorp-settings');
    container.appendChild(body);

    shell.setDirty(false);
    load();
    loadMemory();

    return {
      // Teardown only: every in-flight response is ignored from here and the "Saved."
      // timer is cleared. Never touches the leave guard's flag.
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        gen.invalidate();
        modelGen.invalidate();
        memoryGen.invalidate();
        memorySwitchGen.invalidate();
        unsubscribe();
        window.removeEventListener('gleepglorp-notes-changed', onNotesPush);
        clearSaved();
        App.focusAfter.cancel();
      }
    };
  }

  window.App.admin.renderGleepGlorpPage = renderGleepGlorpPage;
})();
