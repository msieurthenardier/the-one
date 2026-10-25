(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.chipList(opts) -> {el, input, values(), setValues(values, locked),
  // setError(bool), destroy()} (M31 F2 L4, flight DD3). The editable list of
  // short strings (host allowlists, tool overrides, the MCP editor's arguments and
  // writable paths). It copies, exactly, the behaviour of the hand-built editor that
  // lived in areas/admin/tools-form-helpers.js (deleted in M31 F5 L06).
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
  //   [data-locked="true"] and a .visually-hidden " (locked by operator)" text; editable:
  //   the text node then button.ui-chip-remove "×" named "Remove <v>") and
  //   input.chip-list-input.ui-chip-list-input (aria-label "Add entry"). A chip carries its FULL value in
  //   data-value and a title; its visible text is span.ui-chip-text, middle-ellipsized
  //   to chipList.BUDGET (40) characters (a truncated text is aria-hidden, with a
  //   .visually-hidden full-value twin; the remove button stays named "Remove <full>").
  //   chipList.valuesOf(el) reads the full values from any container of chips.
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
    var CHIP_BUDGET = App.ui.chipList.BUDGET;
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
      return chip.getAttribute('data-value') || '';
    }
    function values() {
      return App.ui.chipList.valuesOf(root);
    }
    // The chip body: the visible text (middle-ellipsized past the budget) in
    // span.ui-chip-text. A truncated text is aria-hidden and followed by a
    // .visually-hidden twin with the full value, so a screen reader never reads "…".
    function chipBody(chip, v) {
      chip.setAttribute('data-value', v);
      chip.setAttribute('title', v);
      var shown = util.middleEllipsis(v, CHIP_BUDGET);
      var text = util.el('span', { className: 'ui-chip-text', text: shown });
      chip.appendChild(text);
      if (shown !== v) {
        text.setAttribute('aria-hidden', 'true');
        chip.appendChild(util.el('span', { className: 'visually-hidden', text: v }));
      }
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
      var chip = util.el('span', {
        className: 'chip',
        'data-locked': 'true'
      });
      chipBody(chip, v);
      // A role-less span's aria-label is not announced: say the state in text.
      chip.appendChild(util.el('span', { className: 'visually-hidden', text: ' (locked by operator)' }));
      return chip;
    }
    function editableChip(v) {
      var chip = util.el('span', { className: 'chip' });
      chipBody(chip, v);
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

  // The visible character budget of one chip (a library constant, M31 F4 L04e).
  App.ui.chipList.BUDGET = 40;
  // chipList.valuesOf(el) -> [string]: the full values of the chips under el
  // (a chipList's el, or any container of its chips), in DOM order, locked
  // chips included, read from data-value, never from the (truncated) text.
  App.ui.chipList.valuesOf = function (el) {
    var chips = el.querySelectorAll('.chip[data-value]');
    var out = [];
    for (var i = 0; i < chips.length; i++) out.push(chips[i].getAttribute('data-value'));
    return out;
  };
})();
