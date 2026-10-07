// App.admin.renderToolsEditor — per-tool config editor (F6 leg 03).
//
// Schema-driven editor mounted at #settings/tools/{name}. Builds one widget
// per top-level schema property via dispatch on type × x_marker × ui_hint.
// Save invokes PUT /api/tools/configs/{name} with `{enabled, config}` —
// L1's REPLACE-not-merge contract. Cancel re-mounts with the original
// `toolDetail` snapshot (option A — cleaner than rebuilding chip-list DOM
// from a JSON string).
//
// callbacks: { onCancel, onSaveSuccess, onDirtyChange, onMount }
//
// M25 F3 L5b (flight DD2/DD7): the editor mounts in the Built-in tools page's
// item section, below the tool list. Back is retired: the breadcrumb
// "Settings / Built-in tools" (inserted after innerHTML; its last segment a
// link to #settings/tools, routed by admin.js) closes the item. The title is
// an h2 (the Settings page header owns the page's one h1; flight-end review)
// and carries tabindex="-1" so admin.js can focus it when an intent opens the
// tool. The unsaved caption is a stable span at the start of .form-actions:
// reportDirty sets or clears it with the value it reports through
// onDirtyChange, and Cancel's re-mount keeps the same span node.
// onMount(api) fires after every mount (Cancel's re-mount included) with
// { setEnabled(bool) }: the list's toggle PUT for the OPEN tool updates the
// editor's Enabled control and its saved snapshot in place, never re-mounting
// (an unrelated unsaved edit is kept).
//
// F6 leg 05: the field-rendering helpers (renderField, chip-list editor,
// readFieldValue, error rendering, cssEscape) were extracted to
// admin/tools-form-helpers.js so studio/tools-tab.js can reuse the same
// substrate for per-agent `tool_overrides` editing. This module is now
// the admin orchestrator: enabled-row, snapshot/dirty tracking, Save/
// Cancel/Test handlers, and the test-button section. All form
// rendering delegates to `window.App.adminFormHelpers`.
//
// Field widget dispatch (renderField — see tools-form-helpers.js):
//   bool                                      → <input type=checkbox>
//   integer + ui_hint=dropdown + ui_choices   → <select> of ui_choices
//                                               (synthetic option for non-canonical saved values)
//   integer (no dropdown / empty ui_choices)  → <input type=number> with min/max IFF ge/le declared
//   array (list[str])                         → chip-list editor (ignores ui_hint for type=array)
//   string                                    → <input type=text>
//   unknown                                   → <input type=text class="field-unknown-type">
//                                               + console.warn (developer cue)
//
// Iteration order is `Object.keys(schema.properties)` — Pydantic
// declaration order from the Config class, NOT alphabetic. Matches the
// operator's mental model from the Config docstrings.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Tools that ship a connection-test surface (F6 leg 04). Mirrors the
  // backend's `_TESTABLE_TOOLS` frozenset in api.py — duplicated client-side
  // so the test section's mount is conditional without a backend round-trip.
  // Adding a new testable tool requires updating BOTH this constant and the
  // backend frozenset.
  var _TESTABLE_TOOLS = ['web_search', 'fetch_url'];

  // F6 HAT addition — per-tool test-input fixtures. Mirrors the backend
  // defaults in `test_tool_config` (api.py) — duplicated client-side to
  // pre-fill the editable input next to the Test button. Operator can edit
  // before clicking Test; whitespace-only or missing values fall back to
  // backend defaults (the backend re-checks). Adding a new entry here
  // without a corresponding backend default is harmless (backend will
  // simply ignore the param); adding a backend default without an entry
  // here means the input field won't render and the operator can only
  // test against the backend default.
  var TEST_FIXTURES = {
    'web_search': { param: 'query', default: 'the one cli agent', label: 'Query' },
    'fetch_url': { param: 'url', default: 'https://example.com/', label: 'URL' }
  };

  // Tool name -> category slug for the editor's subtitle ("{description} ·
  // {category}"), from the one shared table (static/js/tool-categories.js,
  // M25 F4 L6, AC9; it replaced this file's copy).
  var TOOL_CATEGORIES = App.toolCategories.categoryOf;

  function renderToolsEditor(container, toolDetail, callbacks) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var helpers = window.App.adminFormHelpers;
    // Capture the original toolDetail at mount time — Cancel re-mounts
    // with this exact reference so chip-list DOM is rebuilt from the
    // canonical source (cleaner than restoring from a JSON snapshot).
    var originalToolDetail = toolDetail;
    var name = toolDetail.name || '';
    var description = toolDetail.description || '';
    var category = TOOL_CATEGORIES[name] || 'unknown';
    var schema = toolDetail.schema || {};
    var properties = schema.properties || {};
    var config = toolDetail.config || {};
    var enabled = !!toolDetail.enabled;
    // Field iteration order — Pydantic declaration order from
    // Object.keys(schema.properties). Capture once so save and dirty
    // tracking iterate the same set deterministically.
    var fieldNames = Object.keys(properties);

    // ── Header HTML ─────────────────────────────────────────────────
    // Description re-labeled as "// prompt" (F6 HAT inline fix #1) — the
    // tool's `description` IS the prompt baked into the LLM tools schema.
    // Rendering it as a labeled prompt-block (monospace label + body-text
    // description) cues the operator that this is what the agent sees.
    // The category continues to render as the small subtitle.
    var html = '';
    html += '<div class="editor-header">';
    html += '<div class="editor-header-text">';
    html += '<h2 class="editor-title" tabindex="-1">' + escapeHtml(name) + '</h2>';
    html += '<p class="editor-subtitle editor-subtitle-meta">' + escapeHtml(category) + '</p>';
    html += '<div class="editor-prompt-block">';
    html += '<div class="section-title">Prompt</div>';
    html += '<pre class="editor-prompt-text code-block">' + escapeHtml(description) + '</pre>';
    html += '</div>';
    html += '</div>';

    // ── Action cluster ──────────────────────────────────────────────
    // M25 F3 L5b (DD2): Back is retired; the cluster opens with the stable
    // unsaved caption (reportDirty sets or clears its text).
    html += '<div class="form-actions">';
    html += '<span class="editor-unsaved" role="status" data-testid="editor-unsaved"></span>';
    html += '<button type="button" class="btn-outlined-primary cancel-btn" data-testid="cancel-tool-btn" disabled>Cancel</button>';
    html += '<button type="button" class="btn-filled-primary save-btn" data-testid="save-tool-btn" disabled>Save</button>';
    html += '<span class="editor-error"></span>';
    html += '</div>';
    html += '</div>'; // .editor-header

    // ── Error banner (F6 HAT inline fix #3) ────────────────────────
    // Sits between .editor-header and the first .editor-section so model-
    // level (loc:[]) and unmatched-field 422 errors render prominently
    // instead of being lost in the small `.editor-error` span next to
    // Save/Cancel. Field-level errors that map to a rendered field row
    // still render as inline `.field-error` spans (existing L3 behavior,
    // preserved). See wireEvents save-handler error routing below.
    html += '<div class="editor-error-banner" hidden role="alert" aria-live="assertive"></div>';

    // ── Configuration section ──────────────────────────────────────
    html += '<div class="editor-section">';
    html += '<div class="section-title">Configuration</div>';
    html += renderEnabledRow(enabled);
    if (fieldNames.length === 0) {
      html += '<p class="empty-state">No additional configuration.</p>';
    } else {
      for (var i = 0; i < fieldNames.length; i++) {
        var fname = fieldNames[i];
        var prop = properties[fname];
        var saved = (fname in config) ? config[fname] : prop['default'];
        html += helpers.renderField(fname, prop, saved, {
          mode: 'admin',
          attrPrefix: 'data-field'
        });
      }
    }
    html += '</div>';

    // ── Test connection section (F6 leg 04) ────────────────────────
    // Mounted only for testable tools (web_search, fetch_url). Click handler
    // is wired in wireEvents; helpers renderTestSuccess / renderTestError are
    // IIFE-level (below).
    if (_TESTABLE_TOOLS.indexOf(name) !== -1) {
      // F6 HAT inline tweak — section hint moved to a tooltip on an info
      // icon next to the section title (parity with the per-field info-icon
      // pattern from `tools-form-helpers.js`). The prior `<p
      // class="field-description tools-editor-test-help">` was visually
      // dense and operators preferred the hover-revealed form. Same
      // `App.icon('info')` + literal `ⓘ` fallback as the per-field path.
      var testHint = 'Runs ' + name + ' against a fixed input using your currently-saved configuration. Use this to verify a narrow / denylist actually refuses, or to confirm that a network change still works.';
      var testHintAttr = escapeAttr(testHint);
      var infoIconHtml = (window.App && window.App.icon) ? window.App.icon('info') : '';
      if (!infoIconHtml) infoIconHtml = 'ⓘ';
      html += '<div class="editor-section tools-editor-test-section">';
      html += '<div class="section-title-row">';
      html += '<span class="section-title">Test connection</span>';
      html += '<button type="button" class="field-info-icon" title="' + testHintAttr + '" aria-label="' + testHintAttr + '">' + infoIconHtml + '</button>';
      html += '</div>';
      html += '<div class="form-actions tools-editor-test-actions">';
      // F6 HAT addition — editable input pre-filled with the per-tool
      // default fixture. Defensive: if a tool name is in _TESTABLE_TOOLS
      // but not in TEST_FIXTURES, skip the input (button still works
      // against the backend default). Mirrors backend defaults in
      // api.py::test_tool_config.
      var fixture = TEST_FIXTURES[name];
      if (fixture) {
        html += '<label class="test-tool-input-label">';
        html += '<span class="test-tool-input-label-text">' + escapeHtml(fixture.label) + '</span>';
        html += '<input type="text" class="test-tool-input" data-test-param="' + escapeAttr(fixture.param) + '" value="' + escapeAttr(fixture.default) + '" />';
        html += '</label>';
      }
      html += '<button type="button" class="btn-outlined-primary test-tool-btn" data-testid="test-tool-btn">';
      html += window.App.icon('play') + ' Test connection';
      html += '</button>';
      html += '<span class="test-result" aria-live="polite"></span>';
      html += '</div>';
      html += '<pre class="tool-test-output" hidden></pre>';
      html += '</div>';
    }

    container.innerHTML = html;

    // The breadcrumb (M25 F3 DD2): "Settings / Built-in tools", inserted with
    // DOM APIs after the markup is in place, as the first child of
    // .editor-header-text. Its last segment links to the page root (the DD2
    // refinement): with Back retired it is the visible way to close the tool.
    var headerText = container.querySelector('.editor-header-text');
    var crumb = document.createElement('div');
    crumb.className = 'editor-breadcrumb';
    crumb.appendChild(document.createTextNode('Settings / '));
    var crumbLink = document.createElement('a');
    crumbLink.className = 'editor-breadcrumb-link';
    crumbLink.setAttribute('href', window.App.router.href({ destination: 'settings', section: 'tools' }));
    crumbLink.setAttribute('data-testid', 'editor-breadcrumb-link');
    crumbLink.textContent = 'Built-in tools';
    crumb.appendChild(crumbLink);
    headerText.insertBefore(crumb, headerText.firstChild);

    wireEvents(container, toolDetail, originalToolDetail, fieldNames, properties, callbacks);
  }

  function renderEnabledRow(enabled) {
    // Use the iOS-style toggle widget from L2's tools-grid (F6 HAT inline
    // fix #2) for visual parity with the grid tile's enable-switch. The
    // CSS lives under `.area-admin .tool-enable-switch …` (admin.css). The
    // `data-field="enabled"` attribute is preserved — drives getFormSnapshot.
    //
    // M17 F6 L2 — DOCUMENTED label-left toggle exception. This is a single
    // toggle, so it stays on the label-left `.field-row` layout rather than
    // stacking into a `.field-group` (stacking a lone toggle under its own
    // label reads worse — same call as the L1 provider `thinking_enabled`
    // toggle; F5 chrome-row precedent). The `.tools-editor-enabled-row` marker
    // class + `data-field-name="enabled"` are PRESERVED. `<label for="tef-
    // enabled">` targets the real `<input id="tef-enabled">` (labelable), so
    // the association resolves at mount — label-association guards stay green.
    // (Mid-flight the editor intentionally carries mixed `.field-group` +
    // `.field-row` rows — this toggle exception plus the shared renderField
    // schema rows, which migrate to `.field-group` in L3.)
    var titleText = enabled ? 'Enabled for all agents' : 'Disabled for all agents';
    return '<div class="field-row tools-editor-enabled-row" data-field-name="enabled">' +
           '<label for="tef-enabled">Enabled for all agents</label>' +
           '<label class="tool-enable-switch" title="' + titleText + '">' +
             '<input id="tef-enabled" type="checkbox" data-field="enabled"' + (enabled ? ' checked' : '') + ' aria-label="' + titleText + '" />' +
             '<span class="tool-enable-switch-track" aria-hidden="true"></span>' +
           '</label>' +
           '</div>';
  }

  function getFormSnapshot(container, fieldNames) {
    var helpers = window.App.adminFormHelpers;
    var enabledInput = container.querySelector('[data-field="enabled"]');
    var snap = { enabled: enabledInput ? enabledInput.checked : false, config: {} };
    for (var i = 0; i < fieldNames.length; i++) {
      var fname = fieldNames[i];
      // Find the field's input by data-field — works for input, select,
      // and the chip-list-editor wrapper div.
      var el = container.querySelector('[data-field="' + helpers.cssEscape(fname) + '"]');
      if (!el) continue;
      snap.config[fname] = helpers.readFieldValue(el);
    }
    return JSON.stringify(snap);
  }

  // Generic conditional-visibility pass (F08 leg 04). For each property
  // carrying `show_if = {ctrlField: value}`, find the field's row and hide
  // it unless the controlling field's CURRENT value === value. Hidden rows
  // stay in the DOM (display:none via `is-hidden`) so getFormSnapshot keeps
  // submitting them — an already-entered secret survives an engine switch.
  // Reads the schema only; no field names are hardcoded.
  function applyShowIf(container, properties) {
    var helpers = window.App.adminFormHelpers;
    for (var fname in properties) {
      if (!Object.prototype.hasOwnProperty.call(properties, fname)) continue;
      var prop = properties[fname];
      var cond = prop && prop.show_if;
      if (!cond || typeof cond !== 'object') continue;
      var row = container.querySelector('.tools-editor-field[data-field-name="' + helpers.cssEscape(fname) + '"]');
      if (!row) continue;
      var visible = true;
      for (var ctrl in cond) {
        if (!Object.prototype.hasOwnProperty.call(cond, ctrl)) continue;
        var ctrlEl = container.querySelector('[data-field="' + helpers.cssEscape(ctrl) + '"]');
        var ctrlVal = ctrlEl ? helpers.readFieldValue(ctrlEl) : undefined;
        if (String(ctrlVal) !== String(cond[ctrl])) { visible = false; break; }
      }
      if (visible) {
        row.classList.remove('is-hidden');
        row.removeAttribute('aria-hidden');
      } else {
        row.classList.add('is-hidden');
        row.setAttribute('aria-hidden', 'true');
      }
    }
  }

  function wireEvents(container, toolDetail, originalToolDetail, fieldNames, properties, callbacks) {
    var helpers = window.App.adminFormHelpers;
    var snapshot = getFormSnapshot(container, fieldNames);
    var dirty = false;

    // Every dirty report goes through here: the header's unsaved caption
    // (M25 F3 DD2) follows the value that feeds the orchestrator's mirror.
    function reportDirty(d) {
      var unsavedEl = container.querySelector('.editor-unsaved');
      if (unsavedEl) unsavedEl.textContent = d ? 'Unsaved changes' : '';
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(d);
    }

    function checkDirty() {
      var current = getFormSnapshot(container, fieldNames);
      var newDirty = current !== snapshot;
      if (newDirty !== dirty) {
        dirty = newDirty;
        var saveBtn = container.querySelector('.save-btn');
        var cancelBtn = container.querySelector('.cancel-btn');
        if (saveBtn) saveBtn.disabled = !dirty;
        if (cancelBtn) cancelBtn.disabled = !dirty;
        reportDirty(dirty);
      }
    }

    // Field-change handlers also clear field-error highlights — the
    // operator's typing implies they're addressing the validation issue
    // (F6 HAT inline fix #7). The clear is per-row so other rows that
    // are still in-error keep their highlight until they too change.
    function clearHighlightOnChange(ev) {
      var row = ev.target && ev.target.closest && ev.target.closest('.tools-editor-field');
      if (row) {
        row.classList.remove('field-error-highlight');
        // F2 Leg 2 (A.2): also drop a11y wiring (aria-invalid +
        // aria-describedby error id) when the operator addresses a
        // field — matches the highlight-clear semantics.
        if (window.App && window.App.adminFormHelpers && window.App.adminFormHelpers.clearFieldErrorA11y) {
          window.App.adminFormHelpers.clearFieldErrorA11y(row);
        }
      }
      checkDirty();
    }

    // Wire change/input listeners on every form control that has a
    // data-field attribute (excluding the chip-list-editor wrapper —
    // chip-list mutations fire checkDirty from inside their own handlers).
    var simpleInputs = container.querySelectorAll('input[data-field], select[data-field]');
    for (var i = 0; i < simpleInputs.length; i++) {
      simpleInputs[i].addEventListener('change', clearHighlightOnChange);
      simpleInputs[i].addEventListener('input', clearHighlightOnChange);
    }

    // Wire chip-list editors (delegated handlers per editor element).
    // Chip add/remove also clears that row's highlight.
    var chipEditors = container.querySelectorAll('.chip-list-editor');
    for (var j = 0; j < chipEditors.length; j++) {
      (function (editorEl) {
        helpers.wireChipListEditor(editorEl, function () {
          var row = editorEl.closest('.tools-editor-field');
          if (row) {
            row.classList.remove('field-error-highlight');
            // F2 Leg 2 (A.2): drop a11y wiring on chip-list mutation
            // (chip add/remove signals the operator is addressing the
            // field — mirrors the highlight-clear path above).
            if (helpers.clearFieldErrorA11y) helpers.clearFieldErrorA11y(row);
          }
          checkDirty();
        });
      })(chipEditors[j]);
    }

    // ── Eye-toggle for masked secret fields (F08 leg 04) ────────────
    // Ported from provider-editor.js:236-251, but the input is selected BY
    // STRUCTURE (the input inside the same .api-key-wrap) rather than by a
    // provider-specific class — the tools form may have several masked
    // secret fields (WebSearchConfig's google_pse/brave/tavily keys), each
    // in its own wrapper. Toggles type password↔text, swaps the eye/eye-off
    // icon, swaps the aria-label.
    var eyeBtns = container.querySelectorAll('.api-key-eye');
    for (var e = 0; e < eyeBtns.length; e++) {
      (function (eyeBtn) {
        var wrap = eyeBtn.closest('.api-key-wrap');
        var passwordInput = wrap ? wrap.querySelector('input') : null;
        if (!passwordInput) return;
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
      })(eyeBtns[e]);
    }

    // ── Generic show_if conditional visibility (F08 leg 04) ─────────
    // A field whose schema carries `show_if = {ctrlField: value}` is hidden
    // unless the current value of [data-field="ctrlField"] === value. Read
    // straight from the schema (NOT hardcoded to search_backend) so any
    // field controlled by any sibling participates. Hidden rows stay in the
    // DOM (so getFormSnapshot still submits them — preserving an entered key
    // across engine switches); they get `is-hidden` (display:none) +
    // aria-hidden="true". applyShowIf runs once after render, and on every
    // change of a controlling field (which also re-runs checkDirty).
    applyShowIf(container, properties);
    var ctrlFields = {};
    for (var pk in properties) {
      if (!Object.prototype.hasOwnProperty.call(properties, pk)) continue;
      var si = properties[pk] && properties[pk].show_if;
      if (si && typeof si === 'object') {
        for (var ck in si) {
          if (Object.prototype.hasOwnProperty.call(si, ck)) ctrlFields[ck] = true;
        }
      }
    }
    for (var cf in ctrlFields) {
      if (!Object.prototype.hasOwnProperty.call(ctrlFields, cf)) continue;
      var ctrlEl = container.querySelector('[data-field="' + helpers.cssEscape(cf) + '"]');
      if (!ctrlEl) continue;
      ctrlEl.addEventListener('change', function () {
        applyShowIf(container, properties);
        checkDirty();
      });
    }

    // Cancel: re-mount with the original toolDetail (option A pinned per
    // Reviewer high-severity). The new closure starts at dirty=false; the
    // onDirtyChange(false) bridge fires AFTER the prior closure already
    // fired its final transition (orchestrator mirror is correct).
    var cancelBtn = container.querySelector('.cancel-btn');
    // Focus after an in-place action (M25 F6 L1b, DD2): the title and Save are
    // re-resolved when the focus timer fires.
    function focusTitle() { return container.querySelector('.editor-title'); }
    function focusSave() { return container.querySelector('.save-btn'); }
    if (cancelBtn) {
      cancelBtn.addEventListener('click', function () {
        var cancelTok = App.focusAfter.begin(cancelBtn);
        if (callbacks.onCancel) callbacks.onCancel();
        // Re-mount — this rebuilds the closure wholesale; the new one
        // captures originalToolDetail again (idempotent: re-mounting with
        // already-original is a no-op). The unsaved caption is a live region
        // (role=status), so the SAME span node is kept across the re-mount,
        // cleared (M25 F3 DD2: a stable node, never re-created).
        var unsavedEl = container.querySelector('.editor-unsaved');
        renderToolsEditor(container, originalToolDetail, callbacks);
        var freshEl = container.querySelector('.editor-unsaved');
        if (unsavedEl && freshEl && freshEl.parentNode) {
          unsavedEl.textContent = '';
          freshEl.parentNode.replaceChild(unsavedEl, freshEl);
        }
        App.focusAfter.restore(cancelTok, focusTitle);
      });
    }

    // setEnabled (M25 F3 L5b): the list's toggle saved `enabled` for this
    // tool. Update the saved snapshot (and the detail Cancel re-mounts from)
    // and, unless the user has already changed the Enabled control here,
    // the control itself -- in place, keeping every other unsaved edit.
    function setEnabled(value) {
      value = !!value;
      var enabledInput = container.querySelector('[data-field="enabled"]');
      var snap = JSON.parse(snapshot);
      var untouched = !enabledInput || enabledInput.checked === snap.enabled;
      snap.enabled = value;
      snapshot = JSON.stringify(snap);
      originalToolDetail = Object.assign({}, originalToolDetail, { enabled: value });
      if (enabledInput && untouched) {
        enabledInput.checked = value;
        var titleText = value ? 'Enabled for all agents' : 'Disabled for all agents';
        enabledInput.setAttribute('aria-label', titleText);
        var sw = enabledInput.closest('.tool-enable-switch');
        if (sw) sw.setAttribute('title', titleText);
      }
      checkDirty();
    }

    // Save: PUT {enabled, config} to /api/tools/configs/{name}.
    var saveBtn = container.querySelector('.save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', function () {
        var errorEl = container.querySelector('.editor-error');
        if (errorEl) errorEl.textContent = '';
        helpers.clearFieldErrors(container);
        // Clear field-error highlights at the START of every save attempt
        // (F6 HAT inline fix #7) — re-applied below if validation fails.
        clearFieldHighlights(container);
        // Clear the prominent error banner at the START of every save
        // attempt — successful save then naturally leaves it hidden, error
        // path repopulates if needed. (F6 HAT inline fix #3.)
        clearErrorBanner(container);

        var snap = JSON.parse(getFormSnapshot(container, fieldNames));
        var url = '/api/tools/configs/' + encodeURIComponent(toolDetail.name);
        var saveTok = App.focusAfter.begin(saveBtn); // before the disable below
        saveBtn.disabled = true;
        fetch(url, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: snap.enabled, config: snap.config })
        }).then(function (r) {
          if (!r.ok) {
            return r.json().then(function (body) {
              var err = new Error('Save failed: ' + r.status);
              err.status = r.status;
              err.body = body;
              throw err;
            }, function () {
              var err = new Error('Save failed: ' + r.status);
              err.status = r.status;
              throw err;
            });
          }
          return r.json();
        }).then(function (updated) {
          window.App.showFlash(container, 'Tool saved');
          // Banner already cleared at save start; defensively ensure it
          // stays hidden on success (covers any future edits that move
          // the start-clear logic).
          clearErrorBanner(container);
          // Re-snapshot from current form state so dirty flips to clean.
          snapshot = getFormSnapshot(container, fieldNames);
          dirty = false;
          var cancelBtnInner = container.querySelector('.cancel-btn');
          if (cancelBtnInner) cancelBtnInner.disabled = true;
          if (saveBtn) saveBtn.disabled = true;
          reportDirty(false);
          // Cancel now re-mounts from what was just saved.
          originalToolDetail = Object.assign({}, originalToolDetail, {
            enabled: updated.enabled,
            config: updated.config
          });
          if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated);
          App.focusAfter.restore(saveTok, focusTitle);
        }).catch(function (err) {
          // Error path: re-enable Save (form remains dirty).
          if (saveBtn) saveBtn.disabled = false;
          App.focusAfter.restore(saveTok, focusSave);
          if (err && err.status === 422 && err.body && Array.isArray(err.body.detail)) {
            // renderFieldErrors attaches inline `.field-error` spans to
            // matching `[data-field-name]` rows (and adds the
            // .field-error-highlight class — F6 HAT inline fix #7), and
            // writes any unmatched entries (joined by ' | ') into
            // `.editor-error`. We then promote that unmatched text to the
            // prominent banner — model-level errors (loc:[]) and entries
            // that don't map to a rendered field both surface there. The
            // inline span is left empty so we don't duplicate the message.
            helpers.renderFieldErrors(container, err.body.detail);
            // Heuristic: model-level (loc:[]) errors don't map to a row,
            // so highlight any field whose name appears in the msg text.
            // Covers the common case of model-validators that mention the
            // offending fields by name (e.g. timeout_seconds_default <=
            // timeout_seconds_max). (F6 HAT inline fix #7.)
            applyModelLevelHighlights(container, err.body.detail, properties);
            if (errorEl && errorEl.textContent) {
              showErrorBanner(container, errorEl.textContent);
              errorEl.textContent = '';
            }
          } else if (err && err.body && err.body.detail) {
            // Non-422 with a server-provided detail string (e.g. 400/409/5xx
            // FastAPI HTTPException). Surface in the banner — same prominence
            // as model-level 422s, distinct from the per-field inline path.
            showErrorBanner(container, String(err.body.detail));
          } else {
            // Network / unparsable response / generic fallback: surface in
            // the banner so the operator sees it at the top of the form,
            // not just as a transient flash.
            showErrorBanner(container, (err && err.message) || 'Save failed');
          }
        });
      });
    }

    // Test connection (F6 leg 04). Mounted only when the test section was
    // emitted (i.e. for testable tools). Independent of Save/Cancel/dirty:
    // the test endpoint reads from the DB; touching it does NOT modify the
    // form snapshot.
    var testBtn = container.querySelector('.test-tool-btn');
    if (testBtn) {
      var resultEl = container.querySelector('.test-result');
      var outputEl = container.querySelector('.tool-test-output');
      testBtn.addEventListener('click', function () {
        // In-flight: clear prior output, show spinner, disable button.
        resultEl.innerHTML = '<span class="test-result-pending">Testing…</span>';
        outputEl.hidden = true;
        outputEl.textContent = '';
        var testTok = App.focusAfter.begin(testBtn); // before the disable below
        testBtn.disabled = true;

        // F6 HAT addition — read the editable test-input field (if
        // present) and pass its value as the override param. The backend
        // re-validates and falls back to defaults on whitespace-only or
        // missing values; sending an empty string is harmless.
        var inputEl = container.querySelector('.test-tool-input');
        var bodyPayload = {};
        if (inputEl) {
          var param = inputEl.dataset.testParam;
          var val = inputEl.value;
          if (param && val !== undefined) bodyPayload[param] = val;
        }

        fetch('/api/tools/configs/' + encodeURIComponent(toolDetail.name) + '/test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(bodyPayload)
        })
          .then(function (r) {
            return r.json().then(function (body) {
              return { ok: r.ok, status: r.status, body: body };
            });
          })
          .then(function (resp) {
            testBtn.disabled = false;
            App.focusAfter.restore(testTok, testBtn);
            if (resp.ok) {
              renderTestSuccess(resp.body, resultEl, outputEl);
            } else {
              renderTestError(resp.status, resp.body, resultEl, outputEl);
            }
          })
          .catch(function (err) {
            testBtn.disabled = false;
            App.focusAfter.restore(testTok, testBtn);
            resultEl.innerHTML = '<span class="test-result-fail">✗ Request failed</span>';
            outputEl.hidden = false;
            outputEl.textContent = String(err && err.message ? err.message : err);
          });
      });
    }

    if (callbacks.onMount) callbacks.onMount({ setEnabled: setEnabled });
  }

  // ── Error banner helpers (F6 HAT inline fix #3) ─────────────────
  // The banner is the prominent error surface for the L3 tools-editor:
  // model-level Pydantic errors (loc:[], fired by `model_validator`),
  // unmatched-field 422 entries, and non-422 server / network failures
  // all route here. Field-level errors that map to a rendered field row
  // continue to use inline `.field-error` spans (rendered by
  // helpers.renderFieldErrors). Visibility is driven by the `hidden`
  // attribute — CSS hides via `[hidden] { display: none }`.
  //
  // Banner text passes through `humanizeValidationMsg` (F6 HAT inline fix
  // #6) which strips Pydantic's "Value error, "/"Input should be …"
  // prefixes and capitalizes the first letter — operators read concise
  // human-readable strings rather than internal pydantic phrasing.
  function showErrorBanner(container, message) {
    var banner = container.querySelector('.editor-error-banner');
    if (!banner) return;
    // Prefer alert-circle; fall back to alert-triangle if (somehow) the
    // primary icon isn't registered — `App.icon` returns '' for unknown
    // names, which lets us detect the miss without throwing.
    var icon = (window.App && window.App.icon) ? window.App.icon('alert-circle') : '';
    if (!icon && window.App && window.App.icon) icon = window.App.icon('alert-triangle');
    // Build DOM via property setters so the message text is escaped by
    // the browser (textContent on the inner `.editor-error-banner-text`
    // span). Icon HTML is trusted (registry-defined SVG).
    banner.innerHTML = icon + '<span class="editor-error-banner-text"></span>';
    var textSpan = banner.querySelector('.editor-error-banner-text');
    if (textSpan) textSpan.textContent = humanizeValidationMsg(message);
    banner.hidden = false;
  }

  function clearErrorBanner(container) {
    var banner = container.querySelector('.editor-error-banner');
    if (!banner) return;
    banner.hidden = true;
    banner.textContent = '';
  }

  // Strip Pydantic-internal prefixes from validation messages and
  // capitalize the first letter (F6 HAT inline fix #6). Used by the
  // banner show path AND mirrored inside `helpers.renderFieldErrors` so
  // inline `.field-error` spans get the same treatment.
  function humanizeValidationMsg(msg) {
    if (!msg) return '';
    var cleaned = String(msg)
      .replace(/^Value error, /, '')
      .replace(/^Input should be /, '')
      .replace(/^Assertion failed, /, '');
    if (!cleaned) return '';
    return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  }

  // Clear all .field-error-highlight classes (F6 HAT inline fix #7).
  // Called at save-attempt START (re-applied below if validation fails)
  // and per-row inside the field-change handlers (operator's typing
  // implies they're addressing the issue).
  function clearFieldHighlights(container) {
    var rows = container.querySelectorAll('.tools-editor-field.field-error-highlight');
    for (var i = 0; i < rows.length; i++) {
      rows[i].classList.remove('field-error-highlight');
    }
  }

  // Heuristic for model-level (loc:[]) 422 errors (F6 HAT inline fix #7):
  // iterate the schema's field names; for each, if the error msg mentions
  // it by name (substring match), add .field-error-highlight to that
  // row. Covers e.g. `timeout_seconds_default (30s) must be <=
  // timeout_seconds_max (10s)` — both names appear in the msg, both rows
  // get highlighted. Field-level errors (loc ending in a field name) are
  // already highlighted by `helpers.renderFieldErrors` directly.
  function applyModelLevelHighlights(container, details, properties) {
    if (!details || !properties) return;
    var fieldNames = Object.keys(properties);
    for (var i = 0; i < details.length; i++) {
      var d = details[i];
      var loc = Array.isArray(d.loc) ? d.loc : [];
      // Skip field-level entries — their highlight came from renderFieldErrors.
      if (loc.length > 0) continue;
      var msg = String(d.msg || '');
      for (var j = 0; j < fieldNames.length; j++) {
        var name = fieldNames[j];
        if (msg.indexOf(name) === -1) continue;
        var row = container.querySelector('.tools-editor-field[data-field-name="' + window.App.adminFormHelpers.cssEscape(name) + '"]');
        if (row) row.classList.add('field-error-highlight');
      }
    }
  }

  function renderTestSuccess(body, resultEl, outputEl) {
    // 200 → {output: str, elapsed_ms: float}. The "success" classification
    // means the HTTP request succeeded; the tool's OUTPUT may itself be an
    // [error] [constraint] ... refusal — that's still a successful test (the
    // operator learns their config blocked it). Distinguish via the
    // [error]-prefix heuristic: agent-visible error strings always start at
    // index 0 of the tool's output.
    var ms = (body.elapsed_ms != null) ? body.elapsed_ms.toFixed(0) : '?';
    var output = String(body.output || '');
    var isToolRefusal = output.indexOf('[error]') === 0;
    var statusClass = isToolRefusal ? 'test-result-fail' : 'test-result-ok';
    var icon = isToolRefusal ? '✗ Refused' : '✓ Returned';
    resultEl.innerHTML =
      '<span class="' + statusClass + '">' + icon +
      ' (' + ms + ' ms)</span>';
    // Truncate to last 2 KB tail-style; matches the F4 chat-output truncation
    // contract (operators see the most recent bytes when output overruns).
    var rendered = output.length > 2048
      ? '… [truncated; showing last 2 KB]\n' + output.slice(-2048)
      : output;
    outputEl.hidden = false;
    outputEl.textContent = rendered;  // textContent preserves [error] prefix
  }

  function renderTestError(status, body, resultEl, outputEl) {
    // 400 / 404 / 5xx etc. — body.detail is FastAPI HTTPException convention.
    var msg = (body && body.detail) ? String(body.detail) : 'HTTP ' + status;
    resultEl.innerHTML =
      '<span class="test-result-fail">✗ ' + window.App.escapeHtml(msg) + '</span>';
    outputEl.hidden = true;
    outputEl.textContent = '';
  }

  window.App.admin.renderToolsEditor = renderToolsEditor;
})();
