// Shared form-helper module — owned by admin/ but consumed by studio/tools-tab.js too.
// Future: move to shared/ if a third consumer appears.
//
// Extracted from admin/tools-editor.js in F6 leg 05 so the per-agent
// `tool_overrides` editor (Studio's Tools tab) and the per-tool admin
// editor share the field-rendering substrate. The two modes differ in:
//   1. The DOM data-attribute namespace (`data-field` vs
//      `data-tool-override-field` + `data-tool-override-tool`).
//   2. The numeric/list ceiling (admin uses the schema's `le`/`ge`; agent
//      uses the operator's saved value as the Narrow ceiling).
//   3. NarrowSuperset rendering (agent locks operator's chips with no ×
//      button; admin renders the same chips fully removable).
//   4. Marker dispatch — agent mode HIDES un-marked operator-only fields;
//      admin renders all schema fields.
//
// All exports live under `window.App.adminFormHelpers`. Callers are
// `admin/tools-editor.js` (mode='admin') and `studio/tools-tab.js`
// (mode='agent'). The IIFE wrapper keeps the closure private.
(function () {
  'use strict';
  window.App = window.App || {};

  // ── Field renderer ─────────────────────────────────────────────────
  //
  // renderField(name, prop, value, context) → HTML string for one
  // .field-row. context object:
  //   - mode: 'admin' | 'agent'
  //   - operatorValue: any (when mode='agent'; the saved operator value
  //     used as ceiling for Narrow / locked entries for NarrowSuperset)
  //   - attrPrefix: 'data-field' | 'data-tool-override-field'
  //   - toolName: string (when mode='agent'; surfaces as
  //     data-tool-override-tool="{name}" on every input — feeds
  //     studio.js::collectFormData's walk)
  //
  // Agent-mode dispatch (after the bool/integer/array/string baseline):
  //   - bool                                              → checkbox
  //   - integer + Narrow + ui_hint=dropdown               → <select>
  //                                                         filtered to
  //                                                         ui_choices
  //                                                         <= operatorValue
  //   - integer + Narrow (no dropdown)                    → number input
  //                                                         min={prop.minimum}
  //                                                         max={operatorValue}
  //   - integer + no marker                               → HIDDEN
  //   - array + Narrow                                    → chip-list
  //                                                         constrained
  //                                                         to operator's
  //                                                         items
  //   - array + NarrowSuperset                            → chip-list
  //                                                         with operator's
  //                                                         items rendered
  //                                                         as locked
  //                                                         (no × button)
  //   - array + NarrowPrefix                              → chip-list
  //                                                         (admin-style;
  //                                                         server validates)
  //   - string + Substitute                               → text input
  //   - unknown / un-marked                               → HIDDEN
  function renderField(name, prop, value, context) {
    context = context || {};
    var mode = context.mode || 'admin';
    var attrPrefix = context.attrPrefix || 'data-field';
    var toolName = context.toolName || null;
    var operatorValue = context.operatorValue;
    var marker = prop.x_marker;

    // Agent-mode marker gating — un-marked fields are operator-only and
    // would be rejected by the resolver at AgentFactory.create() time, so
    // we hide them entirely here. Returning empty string short-circuits
    // the iteration without rendering a row.
    if (mode === 'agent') {
      var allowed = false;
      var type = prop.type;
      if (type === 'boolean') {
        // Booleans don't carry markers — agent toggles freely.
        allowed = true;
      } else if (marker === 'Narrow' || marker === 'NarrowSuperset' || marker === 'NarrowPrefix') {
        allowed = true;
      } else if (marker === 'Substitute') {
        allowed = true;
      }
      if (!allowed) return '';
    }

    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var hint = prop.ui_hint;
    var safeName = escapeAttr(name);
    var idAttr = 'tef-' + safeName + (mode === 'agent' && toolName ? '-' + escapeAttr(toolName) : '');
    var labelText = prop.title || name;
    // F6 HAT inline fix #4: per-field descriptions become tooltips on an
    // info icon next to the label rather than a `.field-description`
    // paragraph below the input. Native HTML `title` attribute provides
    // the tooltip; `aria-label` mirrors for screen readers. Falls back to
    // a literal `ⓘ` if `App.icon('info')` returns empty (defensive — the
    // info icon is registered, but the registry warns + returns '' on
    // miss rather than throwing).
    //
    // F6 HAT inline fix #4b: the info icon emits as a SIBLING after the
    // input (rendered below) rather than nested inside the <label>, so
    // operators see `label | input | ⓘ` per row. Operator-driven UX
    // tweak after re-testing scenario 3.
    var label = '<label for="' + idAttr + '">' + escapeHtml(labelText) + '</label>';
    var infoIcon = '';
    var descId = '';
    if (prop.description) {
      var iconHtml = (window.App && window.App.icon) ? window.App.icon('info') : '';
      if (!iconHtml) iconHtml = 'ⓘ';  // ⓘ
      var descAttr = escapeAttr(prop.description);
      descId = idAttr + '-desc';
      // Render as a focusable <button> so keyboard users can reach the
      // tooltip and screen readers announce the description via
      // aria-describedby. Keep `title=` for mouse-hover UX (and to
      // preserve compatibility with browser tests that assert on the
      // title attribute).
      infoIcon = '<button type="button" class="field-info-icon" title="' + descAttr + '" aria-describedby="' + descId + '">' +
                 iconHtml + '</button>' +
                 '<span id="' + descId + '" class="visually-hidden">' + escapeHtml(prop.description) + '</span>';
    }
    var input = '';
    var ftype = prop.type;

    // Common attribute fragments. In agent mode, every input also carries
    // `data-tool-override-tool="{name}"` so studio.js's collectFormData
    // walks them into a tool_overrides[toolName][fieldName] map.
    var dataAttrs = attrPrefix + '="' + safeName + '"';
    if (mode === 'agent' && toolName) {
      dataAttrs += ' data-tool-override-tool="' + escapeAttr(toolName) + '"';
    }
    // Wire the input to the same description span so focusing the input
    // (not just the info-icon button) announces the field description.
    if (descId) {
      dataAttrs += ' aria-describedby="' + descId + '"';
    }

    if (ftype === 'boolean') {
      input = '<input id="' + idAttr + '" class="checkbox-primary" type="checkbox" ' + dataAttrs + (value ? ' checked' : '') + ' />';
    } else if (
      ftype === 'integer'
      && hint === 'dropdown'
      && Array.isArray(prop.ui_choices)
      && prop.ui_choices.length > 0
    ) {
      // Filter ui_choices in agent mode to entries <= operatorValue.
      // Admin mode shows the full list.
      var choices = prop.ui_choices;
      if (mode === 'agent' && marker === 'Narrow' && (typeof operatorValue === 'number')) {
        choices = [];
        for (var ci = 0; ci < prop.ui_choices.length; ci++) {
          var c = prop.ui_choices[ci];
          var cv = c.value;
          // Only int-typed choices participate in the <=-filter; arrays
          // (e.g. command_denylist baselines) drop through unchanged.
          if (typeof cv === 'number' && cv <= operatorValue) {
            choices.push(c);
          } else if (typeof cv !== 'number') {
            choices.push(c);
          }
        }
      }
      input = '<select id="' + idAttr + '" class="form-control" ' + dataAttrs + ' data-field-type="integer">';
      var sawValue = false;
      for (var i = 0; i < choices.length; i++) {
        var ch = choices[i];
        var cVal = ch.value;
        var optValue = (typeof cVal === 'string' || typeof cVal === 'number' || typeof cVal === 'boolean')
          ? String(cVal)
          : JSON.stringify(cVal);
        var equal = (typeof cVal === 'object' && cVal !== null)
          ? JSON.stringify(cVal) === JSON.stringify(value)
          : cVal === value;
        if (equal) sawValue = true;
        input += '<option value="' + escapeAttr(optValue) + '"' + (equal ? ' selected' : '') + '>' + escapeHtml(ch.label || optValue) + '</option>';
      }
      if (!sawValue && value !== undefined && value !== null) {
        var customStr = (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
          ? String(value)
          : JSON.stringify(value);
        input += '<option value="' + escapeAttr(customStr) + '" selected>' + escapeHtml(customStr) + ' (custom)</option>';
      }
      input += '</select>';
    } else if (ftype === 'integer') {
      // Plain integer input. Admin mode uses schema minimum/maximum.
      // Agent mode uses operator's value as the ceiling, schema minimum
      // as the floor (per F6 Decision 4 narrowing-downward semantics).
      var minVal;
      var maxVal;
      if (mode === 'agent' && marker === 'Narrow') {
        minVal = (prop.minimum !== undefined && prop.minimum !== null) ? prop.minimum : null;
        maxVal = (typeof operatorValue === 'number') ? operatorValue : (prop.maximum !== undefined ? prop.maximum : null);
      } else {
        minVal = (prop.minimum !== undefined && prop.minimum !== null) ? prop.minimum : null;
        maxVal = (prop.maximum !== undefined && prop.maximum !== null) ? prop.maximum : null;
      }
      var minAttr = (minVal !== null) ? ' min="' + escapeAttr(String(minVal)) + '"' : '';
      var maxAttr = (maxVal !== null) ? ' max="' + escapeAttr(String(maxVal)) + '"' : '';
      input = '<input id="' + idAttr + '" class="form-control" type="number" ' + dataAttrs + ' data-field-type="integer" value="' + escapeAttr(String(value !== undefined && value !== null ? value : '')) + '"' + minAttr + maxAttr + ' />';
    } else if (ftype === 'array') {
      if (prop.items && prop.items.type && prop.items.type !== 'string') {
        // eslint-disable-next-line no-console
        console.warn('chip-list editor: items.type is "%s" (expected "string") for field "%s"; rendering as chip-list anyway', prop.items.type, name);
      }
      // Determine locked items for NarrowSuperset (operator's items become
      // immovable chips that the agent must contain).
      var lockedItems = null;
      if (mode === 'agent' && marker === 'NarrowSuperset' && Array.isArray(operatorValue)) {
        lockedItems = {};
        for (var li = 0; li < operatorValue.length; li++) {
          lockedItems[String(operatorValue[li])] = true;
        }
        // Agent's value contains operator's items + agent additions.
        // Render the union — operator's items as locked, agent's
        // additional items as removable.
        var union = [];
        var seenU = Object.create(null);
        for (var lj = 0; lj < operatorValue.length; lj++) {
          var ov = String(operatorValue[lj]);
          if (!seenU[ov]) { union.push(ov); seenU[ov] = true; }
        }
        if (Array.isArray(value)) {
          for (var lk = 0; lk < value.length; lk++) {
            var av = String(value[lk]);
            if (!seenU[av]) { union.push(av); seenU[av] = true; }
          }
        }
        input = renderChipListEditor(name, union, marker, {
          lockedItems: lockedItems,
          attrPrefix: attrPrefix,
          toolName: toolName
        });
      } else {
        input = renderChipListEditor(name, value || [], marker, {
          attrPrefix: attrPrefix,
          toolName: toolName
        });
      }
    } else if (ftype === 'string') {
      input = '<input id="' + idAttr + '" class="form-control" type="text" ' + dataAttrs + ' data-field-type="string" value="' + escapeAttr(String(value !== undefined && value !== null ? value : '')) + '" />';
    } else {
      // eslint-disable-next-line no-console
      console.warn('renderField: unknown type "%s" for field "%s"; rendering as text input', ftype, name);
      input = '<input id="' + idAttr + '" class="form-control field-unknown-type" type="text" ' + dataAttrs + ' data-field-type="unknown" value="' + escapeAttr(JSON.stringify(value)) + '" />';
    }

    // Field-row data-attribute mirrors the input's attrPrefix so
    // renderFieldErrors can find the row by its inner field name.
    var rowAttrs = 'data-field-name="' + safeName + '"';
    if (mode === 'agent' && toolName) {
      rowAttrs += ' data-tool-override-tool="' + escapeAttr(toolName) + '" data-tool-override-field="' + safeName + '"';
    }
    // F6 HAT inline fix #4: the inline `<p class="field-description">` is
    // gone — the description is now a tooltip on a sibling info-icon
    // rendered AFTER the input (label | input | ⓘ).
    return '<div class="form-row tools-editor-field" ' + rowAttrs + '>' +
           label + input + infoIcon + '</div>';
  }

  // ── Chip-list editor ───────────────────────────────────────────────
  //
  // renderChipListEditor(name, items, marker, options)
  //   options.lockedItems: {value: true} → these chips render WITHOUT a
  //     <button class="chip-remove"> element entirely (NOT just hidden via
  //     CSS — keyboard focus order excludes them; screen readers don't
  //     announce them). They get `data-locked` for visual styling.
  //   options.attrPrefix: 'data-field' | 'data-tool-override-field'
  //   options.toolName: string (when agent mode)
  function renderChipListEditor(name, items, marker, options) {
    options = options || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var safeName = escapeAttr(name);
    var attrPrefix = options.attrPrefix || 'data-field';
    var toolName = options.toolName || null;
    var lockedItems = options.lockedItems || null;

    var dataAttrs = attrPrefix + '="' + safeName + '" data-field-type="array"';
    if (toolName) {
      dataAttrs += ' data-tool-override-tool="' + escapeAttr(toolName) + '"';
    }
    if (marker) {
      dataAttrs += ' data-marker="' + escapeAttr(marker) + '"';
    }

    var seen = Object.create(null);
    var html = '<div class="chip-list-editor" ' + dataAttrs + '>';
    for (var i = 0; i < items.length; i++) {
      var v = String(items[i]);
      if (seen[v]) continue;
      seen[v] = true;
      var locked = lockedItems && lockedItems[v];
      if (locked) {
        // Locked chip: NO chip-remove button — keyboard tab order skips
        // it, screen readers don't announce a remove affordance. The
        // data-locked attribute keys the visual differentiation in CSS.
        html += '<span class="chip" data-locked="true" aria-label="' + escapeAttr(v) + ' (locked by operator)">' + escapeHtml(v) + '</span>';
      } else {
        html += '<span class="chip">' + escapeHtml(v) +
                '<button type="button" class="chip-remove" aria-label="Remove ' + escapeAttr(v) + '">×</button>' +
                '</span>';
      }
    }
    html += '<input type="text" class="chip-list-input" placeholder="Add entry…" aria-label="Add entry" />';
    html += '</div>';
    return html;
  }

  function readChipListValue(editorEl) {
    var chips = editorEl.querySelectorAll('.chip');
    var out = [];
    for (var i = 0; i < chips.length; i++) {
      var text = chips[i].textContent || '';
      if (text.charAt(text.length - 1) === '×') text = text.slice(0, -1);
      out.push(text);
    }
    return out;
  }

  function readFieldValue(inputEl) {
    if (inputEl.classList && inputEl.classList.contains('chip-list-editor')) {
      return readChipListValue(inputEl);
    }
    if (inputEl.type === 'checkbox') return inputEl.checked;
    var ftype = inputEl.dataset.fieldType;
    var val = inputEl.value;
    if (ftype === 'integer') {
      if (val.charAt(0) === '[' || val.charAt(0) === '{') {
        try { return JSON.parse(val); } catch (e) { /* fall through */ }
      }
      var n = parseInt(val, 10);
      return isNaN(n) ? val : n;
    }
    if (ftype === 'unknown') {
      try { return JSON.parse(val); } catch (e) { return val; }
    }
    return val;
  }

  // Minimal CSS.escape polyfill for selector building (ASCII-only field
  // names from Pydantic — no need for full Unicode handling).
  function cssEscape(s) {
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, function (ch) { return '\\' + ch; });
  }

  // wireChipListEditor(editorEl, callbacksOrOnChange)
  //   callbacks.onChange: fired when chips added/removed
  //   callbacks.onChipAttempt: optional (value) → 'accept' | 'reject'
  //     hook for agent-mode validation against operator's set
  //
  // Backwards-compat: if a function is passed in place of an object, it
  // is treated as the onChange callback.
  function wireChipListEditor(editorEl, callbacksOrOnChange) {
    var callbacks;
    if (typeof callbacksOrOnChange === 'function') {
      callbacks = { onChange: callbacksOrOnChange };
    } else {
      callbacks = callbacksOrOnChange || {};
    }
    var inputEl = editorEl.querySelector('.chip-list-input');
    if (!inputEl) return;

    function addChips(rawText) {
      if (!rawText) return false;
      var parts = rawText.split(',');
      var added = false;
      for (var i = 0; i < parts.length; i++) {
        var v = parts[i].trim();
        if (!v) continue;
        if (chipExists(editorEl, v)) continue;
        if (callbacks.onChipAttempt) {
          var verdict = callbacks.onChipAttempt(v);
          if (verdict === 'reject') continue;
        }
        var chip = document.createElement('span');
        chip.className = 'chip';
        chip.appendChild(document.createTextNode(v));
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'chip-remove';
        btn.setAttribute('aria-label', 'Remove ' + v);
        btn.textContent = '×';
        chip.appendChild(btn);
        editorEl.insertBefore(chip, inputEl);
        added = true;
      }
      return added;
    }

    inputEl.addEventListener('keydown', function (e) {
      // Enter, Tab, and comma all commit the current input as a chip
      // (preventing Tab's default focus-advance so rapid-fire typing
      // works the same way for all three commit keys).
      if (e.key === 'Enter' || e.key === ',' || e.key === 'Tab') {
        // Tab on EMPTY input: let default focus-advance happen — operator
        // is leaving the chip-list, not committing an empty chip.
        if (e.key === 'Tab' && inputEl.value === '') return;
        e.preventDefault();
        if (addChips(inputEl.value)) {
          inputEl.value = '';
          if (callbacks.onChange) callbacks.onChange();
        } else {
          inputEl.value = '';
        }
      } else if (e.key === 'Backspace' && inputEl.value === '') {
        // Locked chips (NarrowSuperset operator's items) carry no
        // chip-remove button — but Backspace-on-empty would still try to
        // remove the last chip. Skip locked chips when walking back.
        // Backspace deletes the chip IMMEDIATELY BEFORE the input's
        // current DOM position (not always the last chip — the input may
        // have been re-positioned by a click-to-insert action below).
        var prev = inputEl.previousElementSibling;
        while (prev) {
          if (prev.classList && prev.classList.contains('chip') && prev.dataset.locked !== 'true') {
            prev.remove();
            if (callbacks.onChange) callbacks.onChange();
            break;
          }
          prev = prev.previousElementSibling;
        }
      }
    });

    inputEl.addEventListener('paste', function (e) {
      var text = (e.clipboardData || window.clipboardData).getData('text');
      if (text && text.indexOf(',') !== -1) {
        e.preventDefault();
        if (addChips(text)) {
          inputEl.value = '';
          if (callbacks.onChange) callbacks.onChange();
        }
      }
    });

    editorEl.addEventListener('click', function (e) {
      // Click on the × button → remove the chip.
      var btn = e.target.closest && e.target.closest('.chip-remove');
      if (btn) {
        var chip = btn.closest('.chip');
        if (chip) {
          chip.remove();
          if (callbacks.onChange) callbacks.onChange();
        }
        return;
      }
      // Click on a chip body (NOT the × button) → re-position the input
      // before that chip so the next Enter/Tab/comma inserts at this
      // point. Locked chips are skipped (operator's items in agent mode).
      var clickedChip = e.target.closest && e.target.closest('.chip');
      if (clickedChip && clickedChip.dataset.locked !== 'true') {
        editorEl.insertBefore(inputEl, clickedChip);
        inputEl.focus();
      }
    });
  }

  function chipExists(editorEl, value) {
    var chips = editorEl.querySelectorAll('.chip');
    for (var i = 0; i < chips.length; i++) {
      var text = chips[i].textContent || '';
      if (text.charAt(text.length - 1) === '×') text = text.slice(0, -1);
      if (text === value) return true;
    }
    return false;
  }

  // ── Field error rendering ──────────────────────────────────────────
  //
  // Parameterized for both admin (data-field-name) and agent
  // (data-tool-override-tool + data-tool-override-field) DOM patterns.
  // options.fieldRowSelector: callable (lastSeg) → CSS selector string
  //   for the row to attach the error span to. Defaults to the admin
  //   pattern; Studio overrides for the per-tool override panels.
  function clearFieldErrors(container) {
    var errors = container.querySelectorAll('.field-error');
    for (var i = 0; i < errors.length; i++) errors[i].remove();
  }

  // Strip Pydantic-internal prefixes from validation messages and
  // capitalize the first letter (F6 HAT inline fix #6). Mirrors the
  // identically-named helper in tools-editor.js so both inline
  // `.field-error` spans and the prominent banner get the same
  // human-readable phrasing.
  function humanizeValidationMsg(msg) {
    if (!msg) return '';
    var cleaned = String(msg)
      .replace(/^Value error, /, '')
      .replace(/^Input should be /, '')
      .replace(/^Assertion failed, /, '');
    if (!cleaned) return '';
    return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  }

  function renderFieldErrors(container, details, options) {
    options = options || {};
    var fieldRowSelector = options.fieldRowSelector || function (lastSeg) {
      return '.tools-editor-field[data-field-name="' + cssEscape(lastSeg) + '"], .form-row[data-field-name="' + cssEscape(lastSeg) + '"]';
    };
    var unmatched = [];
    for (var i = 0; i < details.length; i++) {
      var d = details[i];
      var loc = Array.isArray(d.loc) ? d.loc : [];
      var rawMsg = d.msg || 'invalid';
      var humanMsg = humanizeValidationMsg(rawMsg);  // F6 HAT inline fix #6
      var lastSeg = loc.length > 0 ? String(loc[loc.length - 1]) : '';
      var row = null;
      if (lastSeg) {
        try {
          row = container.querySelector(fieldRowSelector(lastSeg));
        } catch (e) {
          row = null;
        }
      }
      if (row) {
        // F6 HAT inline fix #7: mark the row as in-error so the CSS adds
        // a red border + label-color tint. Cleared at next save attempt
        // and on field change inside the editor's wireEvents.
        row.classList.add('field-error-highlight');
        var span = document.createElement('span');
        span.className = 'field-error';
        span.textContent = humanMsg;
        row.appendChild(span);
      } else {
        // Loc-prefix kept for unmatched entries since the human can't
        // tell which input the message refers to without it. For
        // model-level errors (loc:[]) the loc prefix is empty so the
        // join+colon yields just `: <msg>` — strip the lone leading ': '
        // so the banner reads cleanly.
        var prefix = loc.join('.');
        unmatched.push(prefix ? (prefix + ': ' + humanMsg) : humanMsg);
      }
    }
    if (unmatched.length > 0) {
      var errorEl = container.querySelector('.editor-error');
      if (errorEl) errorEl.textContent = unmatched.join(' | ');
    }
  }

  window.App.adminFormHelpers = {
    renderField: renderField,
    renderChipListEditor: renderChipListEditor,
    readChipListValue: readChipListValue,
    readFieldValue: readFieldValue,
    cssEscape: cssEscape,
    wireChipListEditor: wireChipListEditor,
    chipExists: chipExists,
    clearFieldErrors: clearFieldErrors,
    renderFieldErrors: renderFieldErrors
  };
})();
