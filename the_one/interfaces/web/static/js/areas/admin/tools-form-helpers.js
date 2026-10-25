// Chip-list string helpers for the MCP editor (studio/mcp-server-editor.js).
//
// Extracted from admin/tools-editor.js in F6 leg 05 so the per-agent tool_overrides editor
// and the per-tool admin editor shared one field-rendering substrate. Both of those now
// build their fields from the control library (App.toolConfigFields, M31 F4 legs 05 and
// 07), so what is left here is the string-built chip list that the MCP editor still mounts
// through App.adminFormHelpers (Flight 5 moves it onto App.ui.chipList and deletes this
// module): renderChipListEditor, wireChipListEditor, readChipListValue and chipExists.
(function () {
  'use strict';
  window.App = window.App || {};

  // ── Chip-list editor ───────────────────────────────────────────────
  //
  // renderChipListEditor(name, items, marker, options)
  //   options.lockedItems: {value: true} → these chips render WITHOUT a
  //     <button class="chip-remove"> element entirely (NOT just hidden via
  //     CSS — keyboard focus order excludes them; screen readers don't
  //     announce them). They get `data-locked` for visual styling.
  //   options.attrPrefix: 'data-field' | 'data-tool-override-field'
  //   options.toolName: string (when agent mode)
  //   options.controlId: string → lands as `id` on the REAL focusable
  //     `.chip-list-input` so a label's for-target can point at a labelable
  //     control (the `.chip-list-editor` wrapper is a <div> — NOT labelable).
  //     The M17 F6 L3 systemic fix for the chip-list label-for runtime-dangle.
  function renderChipListEditor(name, items, marker, options) {
    options = options || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var safeName = escapeAttr(name);
    var attrPrefix = options.attrPrefix || 'data-field';
    var toolName = options.toolName || null;
    var lockedItems = options.lockedItems || null;
    var controlIdAttr = options.controlId ? ' id="' + escapeAttr(options.controlId) + '"' : '';

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
    html += '<input type="text"' + controlIdAttr + ' class="chip-list-input" placeholder="Add entry…" aria-label="Add entry" />';
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

  window.App.adminFormHelpers = {
    renderChipListEditor: renderChipListEditor,
    readChipListValue: readChipListValue,
    wireChipListEditor: wireChipListEditor,
    chipExists: chipExists
  };
})();
