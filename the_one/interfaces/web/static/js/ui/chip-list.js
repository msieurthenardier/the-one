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
  //   toolOverrideField, toolOverrideTool), className, suggest(term) ->
  //   [{value, label, detail}] (sortie 10, DD3: sync; absent = no change at all to the DOM or
  //   behaviour). With it the input is a role=combobox (aria-autocomplete=list, aria-expanded,
  //   aria-controls, aria-activedescendant) over a popover div.ui-chip-list-suggest inside the
  //   root (root gains ui-chip-list--suggest, position: relative) holding a role=listbox of
  //   div.ui-chip-list-option rows (label mono + detail muted; the listbox is named by
  //   suggestLabel, default "Suggestions", and the input by `label`) and an aria-hidden visible
  //   line "No tool matches “{term}”." / "Showing 8 of N. Keep typing to narrow.". The ONE live
  //   region is a permanent visually hidden div.ui-chip-list-live (role=status, outside the
  //   popover) written after a tick; aria-expanded is true only while the listbox has options.
  //   A non-empty trimmed term shows at most 8 matches
  //   (case-insensitive substring over value and label, chosen values left out); an empty term
  //   closes it. ArrowDown/Up move (wrapping), Enter or a click on an option adds it, clears the
  //   input and keeps focus; Escape closes it and stops propagation while open; blur closes it;
  //   Enter with no active option, Tab and comma keep committing the typed text. No document
  //   listener.
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

    var suggest = typeof opts.suggest === 'function' ? opts.suggest : null;

    var root = util.el('div', {
      className: 'chip-list-editor ui-chip-list' + (suggest ? ' ui-chip-list--suggest' : '') +
        (opts.className ? ' ' + opts.className : ''),
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
      // With suggest the input is a combobox: its name must contain the visible label.
      'aria-label': suggest && opts.label ? opts.label : 'Add entry'
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

    // ---- suggest (sortie 10, DD3): a search-ahead combobox, present only with opts.suggest.
    // The ARIA contract is search-list.js's (role=combobox, aria-autocomplete=list,
    // aria-controls, aria-activedescendant); the popover lives inside the root, so no
    // document listener is needed (blur closes it).
    var SUGGEST_MAX = 8;
    var pop = null;
    var listbox = null;
    var statusEl = null;
    var liveEl = null;
    var liveTimer = null;
    var hits = [];
    var optionEls = [];
    var activeIdx = -1;
    var popOpen = false;
    // The one live region (visually hidden, always in the DOM, outside the popover): its text is
    // written after a tick so the change is announced, not swallowed by the popover opening.
    function say(text) {
      if (liveTimer) clearTimeout(liveTimer);
      liveEl.textContent = '';
      if (!text) return;
      liveTimer = setTimeout(function () {
        liveTimer = null;
        liveEl.textContent = text;
      }, 60);
    }
    // open: the popover is shown; expanded: it holds options (aria-expanded is true only then).
    function setPopOpen(open, expanded) {
      popOpen = open;
      pop.hidden = !open;
      input.setAttribute('aria-expanded', open && expanded ? 'true' : 'false');
      if (!open || !expanded) {
        activeIdx = -1;
        input.removeAttribute('aria-activedescendant');
      }
    }
    function paintActive() {
      for (var i = 0; i < optionEls.length; i++) {
        optionEls[i].setAttribute('aria-selected', i === activeIdx ? 'true' : 'false');
      }
      if (activeIdx >= 0 && optionEls[activeIdx]) {
        var row = optionEls[activeIdx];
        input.setAttribute('aria-activedescendant', row.id);
        // Scroll within the listbox only (scrollIntoView would move ancestors).
        if (row.offsetTop < listbox.scrollTop) {
          listbox.scrollTop = row.offsetTop;
        } else if (row.offsetTop + row.offsetHeight > listbox.scrollTop + listbox.clientHeight) {
          listbox.scrollTop = row.offsetTop + row.offsetHeight - listbox.clientHeight;
        }
      } else {
        input.removeAttribute('aria-activedescendant');
      }
    }
    function renderSuggest() {
      var term = input.value.trim();
      listbox.textContent = '';
      statusEl.textContent = '';
      statusEl.hidden = true;
      hits = [];
      optionEls = [];
      activeIdx = -1;
      if (!term) {
        say('');
        setPopOpen(false, false);
        return;
      }
      var have = values();
      var all = suggest(term) || [];
      var lower = term.toLowerCase();
      var total = 0;
      for (var i = 0; i < all.length; i++) {
        var item = all[i];
        if (!item || have.indexOf(item.value) >= 0) continue;
        var hay = (String(item.value) + ' ' + String(item.label || '')).toLowerCase();
        if (hay.indexOf(lower) < 0) continue;
        total += 1;
        if (hits.length < SUGGEST_MAX) hits.push(item);
      }
      listbox.hidden = !hits.length;
      for (var h = 0; h < hits.length; h++) {
        var row = util.el('div', {
          className: 'ui-chip-list-option',
          role: 'option',
          id: util.uid('cl-opt'),
          'aria-selected': 'false'
        });
        row.setAttribute('data-value', String(hits[h].value));
        row.appendChild(util.el('span', {
          className: 'ui-chip-list-option-label',
          text: String(hits[h].label || hits[h].value)
        }));
        if (hits[h].detail) {
          row.appendChild(util.el('span', {
            className: 'ui-chip-list-option-detail',
            text: String(hits[h].detail)
          }));
        }
        listbox.appendChild(row);
        optionEls.push(row);
      }
      var msg = '';
      if (!hits.length) {
        msg = 'No tool matches “' + term + '”.';
      } else if (total > hits.length) {
        msg = 'Showing ' + hits.length + ' of ' + total + '. Keep typing to narrow.';
      }
      // The visible line is for sighted users only; the live node speaks.
      statusEl.textContent = msg;
      statusEl.hidden = !msg;
      say(msg);
      setPopOpen(true, hits.length > 0);
    }
    function pickSuggestion(idx) {
      var item = hits[idx];
      if (!item) return;
      var added = addChips(String(item.value).replace(/,/g, ''));
      input.value = '';
      renderSuggest();
      if (added) fire();
      input.focus();
    }
    if (suggest) {
      var listId = util.uid('cl-list');
      pop = util.el('div', { className: 'ui-chip-list-suggest' });
      pop.hidden = true;
      listbox = util.el('div', {
        className: 'ui-chip-list-listbox', role: 'listbox', id: listId,
        'aria-label': opts.suggestLabel || 'Suggestions'
      });
      statusEl = util.el('div', { className: 'ui-chip-list-status', 'aria-hidden': 'true' });
      statusEl.hidden = true;
      liveEl = util.el('div', { className: 'ui-chip-list-live visually-hidden', role: 'status' });
      pop.appendChild(listbox);
      pop.appendChild(statusEl);
      root.appendChild(pop);
      root.appendChild(liveEl);
      input.setAttribute('role', 'combobox');
      input.setAttribute('aria-autocomplete', 'list');
      input.setAttribute('aria-expanded', 'false');
      input.setAttribute('aria-controls', listId);
    }
    function onInput() {
      renderSuggest();
    }
    function onBlur() {
      setPopOpen(false);
    }
    function onPopMouseDown(e) {
      // Keep focus in the input: a click on an option picks without a blur.
      e.preventDefault();
    }
    function onPopClick(e) {
      var row = e.target.closest && e.target.closest('.ui-chip-list-option');
      if (!row) return;
      pickSuggestion(optionEls.indexOf(row));
    }
    function onPopMouseOver(e) {
      var row = e.target.closest && e.target.closest('.ui-chip-list-option');
      if (!row) return;
      var idx = optionEls.indexOf(row);
      if (idx !== activeIdx) {
        activeIdx = idx;
        paintActive();
      }
    }
    // Returns true when the key was consumed by the open suggestion list.
    function suggestKey(e) {
      if (!popOpen) return false;
      if (e.key === 'Escape') {
        e.stopPropagation();
        setPopOpen(false);
        return true;
      }
      if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && hits.length) {
        e.preventDefault();
        if (e.key === 'ArrowDown') {
          activeIdx = activeIdx < 0 ? 0 : (activeIdx + 1) % hits.length;
        } else {
          activeIdx = activeIdx < 0 ? hits.length - 1 : (activeIdx - 1 + hits.length) % hits.length;
        }
        paintActive();
        return true;
      }
      if (e.key === 'Enter' && activeIdx >= 0) {
        e.preventDefault();
        pickSuggestion(activeIdx);
        return true;
      }
      return false;
    }

    function onKeydown(e) {
      if (suggest && suggestKey(e)) return;
      if (e.key === 'Enter' || e.key === ',' || e.key === 'Tab') {
        // Tab on an EMPTY input lets focus advance: the operator is leaving.
        if (e.key === 'Tab' && input.value === '') return;
        e.preventDefault();
        if (addChips(input.value)) {
          input.value = '';
          if (suggest) renderSuggest();
          fire();
        } else {
          input.value = '';
          if (suggest) renderSuggest();
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
    if (suggest) {
      input.addEventListener('input', onInput);
      input.addEventListener('blur', onBlur);
      pop.addEventListener('mousedown', onPopMouseDown);
      pop.addEventListener('click', onPopClick);
      pop.addEventListener('mouseover', onPopMouseOver);
    }

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
        if (suggest) {
          input.removeEventListener('input', onInput);
          input.removeEventListener('blur', onBlur);
          pop.removeEventListener('mousedown', onPopMouseDown);
          pop.removeEventListener('click', onPopClick);
          pop.removeEventListener('mouseover', onPopMouseOver);
          if (liveTimer) clearTimeout(liveTimer);
        }
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
