(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.chipList(opts) -> {el, input, values(), setValues(values, locked),
  // setError(bool), destroy()} (M31 F2 L4, flight DD3). The editable list of
  // short strings (host allowlists, tool overrides). It copies, exactly, the
  // behaviour of the hand-built editor in areas/admin/tools-form-helpers.js,
  // which stays until its consumers migrate.
  //   label (the group's aria-label), values [string], locked [string] (a locked
  //   chip has no remove button and cannot be re-positioned; a locked value
  //   missing from values is added first), placeholder ('Add entry…'),
  //   validate(value) -> true | false | string (the accept/reject hook: false or
  //   any string other than 'accept' rejects; a string other than 'reject' is
  //   passed to onReject(value, message)), onChange(values), testid, inputId
  //   (the id of the real focusable input, for a label's for), dataset (data-*
  //   on the root: field, fieldType (default 'array'), marker,
  //   toolOverrideField, toolOverrideTool), className.
  //   el is div.chip-list-editor.ui-chip-list (the marker the area CSS is narrowed
  //   against, M31 F3 L03c) holding span.chip per value (locked:
  //   [data-locked="true"] and aria-label "<v> (locked by operator)"; editable:
  //   the text node then button.ui-chip-remove "×" named "Remove <v>") and
  //   input.chip-list-input.ui-chip-list-input (aria-label "Add entry"). A chip's textContent is
  //   the value plus the trailing "×", as in the legacy editor.
  //   Keys on the input: Enter, comma and Tab commit a non-empty input (Tab on
  //   an empty input moves focus on); Backspace on an empty input removes the
  //   nearest editable chip before the input; a paste containing a comma splits
  //   and adds; duplicates are ignored; an empty or all-rejected commit clears
  //   the input without onChange. A click on a chip body (not locked) moves the
  //   input before that chip. values() lists every chip, locked ones included,
  //   in DOM order. setError(bool) sets aria-invalid on the input and the
  //   is-invalid class.
  App.ui.chipList = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var validate = typeof opts.validate === 'function' ? opts.validate : null;

    var root = util.el('div', {
      className: 'chip-list-editor ui-chip-list' + (opts.className ? ' ' + opts.className : ''),
      role: opts.label ? 'group' : null,
      'aria-label': opts.label || null
    });
    util.applyDataset(root, opts.dataset);
    if (!root.hasAttribute('data-field-type')) root.setAttribute('data-field-type', 'array');
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    var input = util.el('input', {
      type: 'text',
      className: 'chip-list-input ui-chip-list-input',
      id: opts.inputId,
      placeholder: opts.placeholder || 'Add entry…',
      'aria-label': 'Add entry'
    });
    root.appendChild(input);

    function textOf(chip) {
      var text = chip.textContent || '';
      if (text.charAt(text.length - 1) === '×') text = text.slice(0, -1);
      return text;
    }
    function values() {
      var chips = root.querySelectorAll('.chip');
      var out = [];
      for (var i = 0; i < chips.length; i++) out.push(textOf(chips[i]));
      return out;
    }
    function exists(value) {
      var chips = root.querySelectorAll('.chip');
      for (var i = 0; i < chips.length; i++) {
        if (textOf(chips[i]) === value) return true;
      }
      return false;
    }
    function fire() {
      if (typeof opts.onChange === 'function') opts.onChange(values());
    }
    function lockedChip(v) {
      return util.el('span', {
        className: 'chip',
        'data-locked': 'true',
        'aria-label': v + ' (locked by operator)',
        text: v
      });
    }
    function editableChip(v) {
      var chip = util.el('span', { className: 'chip' });
      chip.appendChild(document.createTextNode(v));
      chip.appendChild(util.el('button', {
        type: 'button',
        className: 'ui-chip-remove',
        'aria-label': 'Remove ' + v,
        text: '×'
      }));
      return chip;
    }

    function setValues(list, lockedList) {
      var chips = root.querySelectorAll('.chip');
      for (var r = 0; r < chips.length; r++) root.removeChild(chips[r]);
      // The input returns to the end, as on a fresh render.
      root.appendChild(input);
      var lockedMap = Object.create(null);
      var seen = Object.create(null);
      var ordered = [];
      var inValues = Object.create(null);
      var i;
      lockedList = lockedList || [];
      list = list || [];
      for (i = 0; i < list.length; i++) inValues[String(list[i])] = true;
      // A locked value missing from values leads; values keep the caller's order.
      for (i = 0; i < lockedList.length; i++) {
        lockedMap[String(lockedList[i])] = true;
        if (!inValues[String(lockedList[i])]) ordered.push(String(lockedList[i]));
      }
      for (i = 0; i < list.length; i++) ordered.push(String(list[i]));
      for (i = 0; i < ordered.length; i++) {
        var v = ordered[i];
        if (seen[v]) continue;
        seen[v] = true;
        root.insertBefore(lockedMap[v] ? lockedChip(v) : editableChip(v), input);
      }
    }
    setValues(opts.values, opts.locked);

    function addChips(rawText) {
      if (!rawText) return false;
      var parts = rawText.split(',');
      var added = false;
      for (var i = 0; i < parts.length; i++) {
        var v = parts[i].trim();
        if (!v) continue;
        if (exists(v)) continue;
        if (validate) {
          var verdict = validate(v);
          if (verdict === false || (typeof verdict === 'string' && verdict !== 'accept')) {
            if (typeof verdict === 'string' && verdict !== 'reject' &&
                typeof opts.onReject === 'function') {
              opts.onReject(v, verdict);
            }
            continue;
          }
        }
        root.insertBefore(editableChip(v), input);
        added = true;
      }
      return added;
    }

    function onKeydown(e) {
      if (e.key === 'Enter' || e.key === ',' || e.key === 'Tab') {
        // Tab on an EMPTY input lets focus advance: the operator is leaving.
        if (e.key === 'Tab' && input.value === '') return;
        e.preventDefault();
        if (addChips(input.value)) {
          input.value = '';
          fire();
        } else {
          input.value = '';
        }
      } else if (e.key === 'Backspace' && input.value === '') {
        // The chip IMMEDIATELY BEFORE the input's DOM position (the input may
        // have been re-positioned by a click), skipping locked chips.
        var prev = input.previousElementSibling;
        while (prev) {
          if (prev.classList && prev.classList.contains('chip') && prev.dataset.locked !== 'true') {
            prev.remove();
            fire();
            break;
          }
          prev = prev.previousElementSibling;
        }
      }
    }
    function onPaste(e) {
      var text = (e.clipboardData || window.clipboardData).getData('text');
      if (text && text.indexOf(',') !== -1) {
        e.preventDefault();
        if (addChips(text)) {
          input.value = '';
          fire();
        }
      }
    }
    function onClick(e) {
      var btn = e.target.closest && e.target.closest('.ui-chip-remove');
      if (btn) {
        var chip = btn.closest('.chip');
        if (chip) {
          chip.remove();
          fire();
        }
        return;
      }
      var clicked = e.target.closest && e.target.closest('.chip');
      if (clicked && clicked.dataset.locked !== 'true') {
        root.insertBefore(input, clicked);
        input.focus();
      }
    }
    input.addEventListener('keydown', onKeydown);
    input.addEventListener('paste', onPaste);
    root.addEventListener('click', onClick);

    return {
      el: root,
      input: input,
      values: values,
      setValues: setValues,
      setError: function (on) {
        if (on) {
          input.setAttribute('aria-invalid', 'true');
        } else {
          input.removeAttribute('aria-invalid');
        }
        root.classList.toggle('is-invalid', !!on);
      },
      destroy: function () {
        input.removeEventListener('keydown', onKeydown);
        input.removeEventListener('paste', onPaste);
        root.removeEventListener('click', onClick);
      }
    };
  };
})();
