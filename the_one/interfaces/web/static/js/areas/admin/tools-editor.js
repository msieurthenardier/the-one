// App.admin.renderToolsEditor -- the per-tool config editor (F6 leg 03; rebuilt on the
// control library in M31 F4 legs 07a-07d).
//
// Schema-driven editor mounted at #settings/tools/{name} in the Built-in tools page's
// item section, below the tool list. Save invokes PUT /api/tools/configs/{name} with
// `{enabled, config}` -- L1's REPLACE-not-merge contract.
//
//   var api = App.admin.renderToolsEditor(container, toolDetail, callbacks)
//     -> { setEnabled(bool), destroy() }
//   callbacks: { isCurrent(), onSaved(updated), onSaveSuccess(updated), onCancel(),
//                onDirtyChange(bool) }
//     isCurrent() is the page's mount-slot check: false once another tool's editor (or
//       none) owns the item section. A stale editor writes nothing shared.
//     onSaved(updated) runs whenever a Save response arrives (even for a stale editor):
//       the list cache and the list tiles follow the server.
//     onSaveSuccess(updated), onCancel() and onDirtyChange(d) run only while current.
//
// The frame is App.ui.editorShell (default variant, flush): the "Settings / Built-in
// tools" breadcrumb, the tool name as the h2 title (the Settings page header owns the
// page's one h1), the category's display name as the subtitle, the unsaved caption and
// Cancel and Save. Below it: the tool prompt (a code block) in its own section, the
// Configuration section (the Enabled switch, then one control per served property from
// App.toolConfigFields in admin mode), and, for web_search and fetch_url, Test connection.
//
// Value model (DD5): `snapshot` is read from the field handles (`value()`) and the
// Enabled switch, never from the DOM; dirty is snapshot !== baseline. Save and Cancel
// patch in place (nothing remounts): Save re-baselines from the SERVER'S response, field
// by field, and keeps a value typed while the request was in flight (dirty stays true);
// a secret is re-masked from the response only if it still holds what was submitted.
// Cancel writes the baseline back into the handles. While a Save is in flight the shell
// is busy (Save, Cancel and Test disabled; the fields stay live). A Test in flight blocks
// Save too: the Test reads the SAVED row.
//
// Errors (DD3): a 422 whose `loc` names a rendered field goes on that field; everything
// else (a model-level 422, any other status, a network failure) goes through
// editorShell.setError, announced once (role=alert). A field's message is never repeated
// at editor level.
//
// Field widths and the show_if reveal come from the shared module; a show_if-hidden row
// stays in the form and is still submitted.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Tools that ship a connection-test surface (F6 leg 04). Mirrors the backend's
  // `_TESTABLE_TOOLS` frozenset in api.py -- duplicated client-side so the test section's
  // mount is conditional without a backend round-trip. Adding a new testable tool
  // requires updating BOTH this constant and the backend frozenset.
  var _TESTABLE_TOOLS = ['web_search', 'fetch_url'];

  // Per-tool test-input fixtures. Mirrors the backend defaults in `test_tool_config`
  // (api.py): the editable input next to the Test button is pre-filled with the default.
  // The backend re-checks the value and falls back to its default for a blank one.
  var TEST_FIXTURES = {
    'web_search': { param: 'query', default: 'the one cli agent', label: 'Query' },
    'fetch_url': { param: 'url', default: 'https://example.com/', label: 'URL' }
  };

  // The head of a long result is shown (the first 2 KB), with an ellipsis at the cut.
  var TEST_OUTPUT_LIMIT = 2048;

  // Fixed headline per outcome (DD6): the client never parses the tool's model-facing
  // string; the route says which outcome it was.
  var HEADLINES = {
    ok: ['success', 'Returned a result'],
    blocked: ['warning', "Blocked by this tool's settings"],
    failed: ['danger', 'Request failed']
  };

  function categoryLabel(name) {
    var cat = App.toolCategories.categoryOf[name];
    return (cat && App.toolCategories.labels[cat]) || null;
  }

  function pageLabel() {
    var pages = App.settingsPages || [];
    for (var i = 0; i < pages.length; i++) if (pages[i].section === 'tools') return pages[i].label;
    return 'Built-in tools';
  }

  function same(a, b) {
    return JSON.stringify(a) === JSON.stringify(b);
  }

  function renderToolsEditor(container, toolDetail, callbacks) {
    callbacks = callbacks || {};
    var util = App.ui.util;
    var name = toolDetail.name || '';
    var properties = (toolDetail.schema || {}).properties || {};
    var config = toolDetail.config || {};
    // Pydantic declaration order from the Config class, NOT alphabetic: it is the order
    // of the form and of every snapshot.
    var fieldNames = Object.keys(properties);
    var toolUrl = '/api/tools/configs/' + encodeURIComponent(name);

    var alive = true;
    var saving = false;
    var testing = false;
    var dirty = false;
    var saveLatest = util.latest();
    var testLatest = util.latest();
    var handles = {};
    var baseline = null; // { enabled, config } -- what the server holds (as last known)
    var showIfCtl = null;
    var testBtn = null;
    var testInput = null;
    var testResult = null; // the polite live region holding the status
    var testDetails = null; // where the Technical details disclosure goes
    var testHint = null;
    var shell = null;
    var enabledToggle = null;

    // This editor may write shared state (the leave guard, the flash, the page's
    // handles) only while it is the page's current mount.
    function current() {
      return alive && (typeof callbacks.isCurrent !== 'function' || callbacks.isCurrent());
    }

    // ── Value model ───────────────────────────────────────────────────

    function snapshot() {
      var cfg = {};
      fieldNames.forEach(function (f) {
        if (handles[f]) cfg[f] = handles[f].value();
      });
      return { enabled: enabledToggle.control.checked, config: cfg };
    }

    function checkDirty() {
      var next = !same(snapshot(), baseline);
      if (testHint) testHint.hidden = !next;
      if (next === dirty) return;
      dirty = next;
      shell.setDirty(dirty);
      if (current() && callbacks.onDirtyChange) callbacks.onDirtyChange(dirty);
    }

    function refreshBusy() {
      shell.setBusy(saving || testing);
      if (testBtn) testBtn.disabled = saving || testing;
    }

    function clearErrors() {
      shell.setError('');
      fieldNames.forEach(function (f) {
        if (handles[f]) handles[f].setError(null);
      });
    }

    // ── Frame ─────────────────────────────────────────────────────────

    shell = App.ui.editorShell({
      breadcrumb: {
        lead: 'Settings / ',
        label: pageLabel(),
        href: App.router.href({ destination: 'settings', section: 'tools' })
      },
      title: name,
      titleLevel: 2,
      subtitle: categoryLabel(name),
      inset: 'none',
      testid: 'tool-editor-header',
      errorRole: 'alert',
      actions: {
        cancel: { testid: 'cancel-tool-btn', onClick: cancel },
        save: { testid: 'save-tool-btn', onClick: save }
      }
    });

    var promptBlock = App.ui.codeBlock({
      text: toolDetail.description || '',
      label: 'Tool prompt',
      maxHeight: 'short'
    });
    var promptSection = App.ui.section({
      title: 'Prompt',
      inset: 'none',
      children: [promptBlock.el]
    });

    // ── Configuration ─────────────────────────────────────────────────

    enabledToggle = App.ui.toggle({
      label: 'Enabled for all agents',
      id: 'tef-enabled',
      checked: !!toolDetail.enabled,
      dataset: { field: 'enabled' },
      onChange: checkDirty
    });
    var configSection = App.ui.section({
      title: 'Configuration',
      layout: 'stack',
      inset: 'none',
      children: [enabledToggle.el]
    });
    fieldNames.forEach(function (fname) {
      var prop = properties[fname];
      var saved = (fname in config) ? config[fname] : prop['default'];
      var h = App.toolConfigFields.render(fname, prop, saved, {
        mode: 'admin',
        toolName: name,
        onChange: function () {
          // Typing in a field signals the operator is addressing its error.
          if (handles[fname]) handles[fname].setError(null);
          checkDirty();
        }
      });
      if (!h) return;
      handles[fname] = h;
      configSection.body.appendChild(h.el);
    });
    if (fieldNames.length === 0) {
      configSection.body.appendChild(App.ui.emptyState({
        title: 'No additional configuration.',
        titleTag: 'p',
        variant: 'flush'
      }));
    }
    showIfCtl = App.toolConfigFields.showIf(properties, handles);

    // ── Test connection (web_search, fetch_url) ───────────────────────

    var testSection = null;
    if (_TESTABLE_TOOLS.indexOf(name) !== -1) {
      var fixture = TEST_FIXTURES[name];
      testSection = App.ui.section({
        title: 'Test connection',
        inset: 'none',
        info: {
          text: 'Runs ' + name + ' against a fixed input using your currently-saved ' +
            'configuration. Use this to verify a narrow / denylist actually refuses, or to ' +
            'confirm that a network change still works.',
          label: 'About Test connection'
        }
      });
      var row = util.el('div', { className: 'tools-test-row' });
      if (fixture) {
        testInput = App.ui.textInput({
          type: 'text',
          value: fixture.default,
          dataset: { testParam: fixture.param }
        });
        var testField = App.ui.field({ label: fixture.label, control: testInput });
        row.appendChild(util.el('div', { className: 'tools-test-field' }, [testField.el]));
      }
      testBtn = App.ui.button({
        label: 'Test connection',
        icon: 'play',
        variant: 'secondary',
        testid: 'test-tool-btn',
        onClick: runTest
      });
      row.appendChild(testBtn);
      testSection.body.appendChild(row);
      testHint = util.el('p', {
        className: 'tools-test-hint',
        'data-testid': 'test-saved-hint',
        text: 'Tests the saved settings.'
      });
      testHint.hidden = true;
      testSection.body.appendChild(testHint);
      testResult = util.el('div', {
        className: 'tools-test-result',
        'data-testid': 'test-result',
        'aria-live': 'polite'
      });
      testDetails = util.el('div', { className: 'tools-test-details' });
      testSection.body.appendChild(testResult);
      testSection.body.appendChild(testDetails);
    }

    container.textContent = '';
    container.appendChild(shell.el);
    container.appendChild(promptSection.el);
    container.appendChild(configSection.el);
    if (testSection) container.appendChild(testSection.el);

    baseline = snapshot();

    // ── Test ──────────────────────────────────────────────────────────

    function clearTestResult() {
      if (!testResult) return;
      testResult.textContent = '';
      testResult.removeAttribute('data-state');
      testDetails.textContent = '';
    }

    function showTestResult(state, headline, details) {
      testResult.textContent = '';
      var status = App.ui.status({ live: 'off' });
      status.set(state, headline);
      testResult.appendChild(status.el);
      testResult.setAttribute('data-state', state);
      testDetails.textContent = '';
      if (details) {
        var text = details.length > TEST_OUTPUT_LIMIT
          ? details.slice(0, TEST_OUTPUT_LIMIT) + '…'
          : details;
        var code = App.ui.codeBlock({
          text: text,
          label: 'Test output',
          maxHeight: 'short',
          testid: 'tool-test-output'
        });
        var disclosure = App.ui.disclosure({
          variant: 'plain',
          summary: 'Technical details',
          testid: 'tool-test-details',
          onToggle: function () { code.refresh(); }
        });
        disclosure.body.appendChild(code.el);
        testDetails.appendChild(disclosure.el);
      }
    }

    function runTest() {
      if (testing || saving || !testBtn) return;
      var token = testLatest.next();
      var focusTok = App.focusAfter.begin(testBtn); // before the disable below
      testing = true;
      refreshBusy();
      clearTestResult();
      var pending = App.ui.status({ live: 'off' });
      pending.set('pending', 'Testing…');
      testResult.appendChild(pending.el);
      testResult.setAttribute('data-state', 'pending');
      var body = {};
      if (testInput) body[testInput.dataset.testParam] = testInput.value;

      function live() { return alive && testLatest.isCurrent(token); }
      App.api.fetchJson(toolUrl + '/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      }).then(function (resp) {
        if (!live()) return;
        var outcome = HEADLINES[resp.outcome] ? resp.outcome : 'ok';
        var spec = HEADLINES[outcome];
        var ms = resp.elapsed_ms != null ? Math.round(resp.elapsed_ms) : null;
        var headline = outcome === 'failed' || ms === null ? spec[1] : spec[1] + ' (' + ms + ' ms)';
        showTestResult(spec[0], headline, String(resp.output || ''));
      }).catch(function (err) {
        if (!live()) return;
        showTestResult('danger', 'Request failed', String((err && err.message) || err || ''));
      }).then(function () {
        if (!live()) return;
        testing = false;
        refreshBusy();
        App.focusAfter.restore(focusTok, testBtn);
      });
    }

    // ── Cancel ────────────────────────────────────────────────────────

    // Writes the baseline back into the handles; nothing remounts. Cancel is disabled
    // while a Save is in flight (setBusy), so it can never run against a request that
    // would land afterwards.
    function cancel() {
      if (saving || testing) return;
      var focusTok = App.focusAfter.begin(shell.cancelButton);
      var changed = dirty;
      enabledToggle.setChecked(baseline.enabled);
      fieldNames.forEach(function (f) {
        if (handles[f]) handles[f].setValue(baseline.config[f]);
      });
      clearErrors();
      showIfCtl.apply();
      if (changed) clearTestResult();
      checkDirty();
      if (current() && callbacks.onCancel) callbacks.onCancel();
      App.focusAfter.restore(focusTok, shell.titleEl);
    }

    // ── Save ──────────────────────────────────────────────────────────

    // The server's response becomes the baseline. A field whose control still holds what
    // was submitted follows the response (a secret becomes its mask); one the operator
    // changed meanwhile keeps its value and so stays dirty. A field the response omits is
    // at its Config default.
    function applyResponse(submitted, updated) {
      var respConfig = updated.config || {};
      var next = { enabled: !!updated.enabled, config: {} };
      fieldNames.forEach(function (f) {
        var h = handles[f];
        if (!h) return;
        var resp = (f in respConfig) ? respConfig[f] : properties[f]['default'];
        var held = h.value();
        if (same(held, submitted.config[f])) {
          if (!same(held, resp)) h.setValue(resp);
          next.config[f] = h.value();
        } else {
          next.config[f] = resp;
        }
      });
      // The Enabled control follows the new baseline unless the operator touched it.
      if (enabledToggle.control.checked === baseline.enabled) {
        enabledToggle.setChecked(next.enabled);
      }
      baseline = next;
    }

    function save() {
      if (saving || testing) return;
      clearErrors();
      var submitted = snapshot();
      var token = saveLatest.next();
      var focusTok = App.focusAfter.begin(shell.saveButton); // before the disable below
      saving = true;
      refreshBusy();
      function live() { return alive && saveLatest.isCurrent(token); }
      App.api.fetchJson(toolUrl, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: submitted.enabled, config: submitted.config })
      }).then(function (updated) {
        if (callbacks.onSaved) callbacks.onSaved(updated);
        if (!live() || !current()) return;
        applyResponse(submitted, updated);
        App.ui.flash('Tool saved', { container: container });
        if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated);
        dirty = null; // force the report: the baseline moved
        checkDirty();
        saving = false;
        refreshBusy();
        App.focusAfter.restore(focusTok, shell.titleEl);
      }, function (err) {
        if (!live()) return;
        showSaveError(err);
        saving = false;
        refreshBusy();
        App.focusAfter.restore(focusTok, shell.saveButton);
      });
    }

    function showSaveError(err) {
      var text = (err && err.message) || 'Save failed';
      if (err && err.status === 422) {
        var result = App.api.fieldErrors(err, fieldNames);
        var extra = [];
        fieldNames.forEach(function (f) {
          if (!(f in result.fields)) return;
          var h = handles[f];
          // A message for a row the form hides would go unseen: say it at editor level.
          if (h && !h.el.classList.contains('is-hidden')) h.setError(result.fields[f]);
          else extra.push(result.fields[f]);
        });
        text = result.text;
        if (extra.length) text = (text ? text + ' ' : '') + extra.join(' ');
      }
      shell.setError(text);
    }

    // ── The list toggle for the open tool ─────────────────────────────

    // The list's toggle saved `enabled` for this tool: the baseline follows the server
    // and, unless the operator already changed the Enabled control here, so does the
    // control -- in place, keeping every other unsaved edit.
    function setEnabled(value) {
      value = !!value;
      var previous = baseline.enabled;
      baseline.enabled = value;
      if (enabledToggle.control.checked === previous) enabledToggle.setChecked(value);
      checkDirty();
    }

    return {
      setEnabled: setEnabled,
      destroy: function () {
        alive = false;
        saveLatest.invalidate();
        testLatest.invalidate();
        if (showIfCtl) showIfCtl.destroy();
      }
    };
  }

  window.App.admin.renderToolsEditor = renderToolsEditor;
})();
