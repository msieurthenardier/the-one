(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // Shared construction for checkbox and toggle: a <label> that wraps the
  // native input and the text, plus an optional hint that is a SIBLING of the
  // label (so the accessible name stays the label text alone).
  function build(opts, name, rootClass, labelClass, inputClass, extras) {
    opts = opts || {};
    if (!opts.label) throw new Error('App.ui.' + name + ': label is required');
    var util = App.ui.util;
    var input = util.el('input', { type: 'checkbox', className: inputClass });
    input.id = opts.id || util.uid(name === 'toggle' ? 'tg' : 'cb');
    input.setAttribute('data-ui-own-label', 'true');
    if (opts.checked) input.checked = true;
    if (opts.disabled) input.disabled = true;
    if (opts.testid) input.setAttribute('data-testid', opts.testid);
    var parts = [input];
    var i;
    for (i = 0; i < extras.before.length; i++) parts.push(extras.before[i]);
    var text = util.el('span', {
      className: opts.labelHidden ? 'visually-hidden' : 'ui-choice-text',
      text: opts.label
    });
    parts.push(text);
    var label = util.el('label', { className: labelClass }, parts);
    label.htmlFor = input.id;
    var root = util.el('div', { className: rootClass + (opts.disabled ? ' is-disabled' : '') }, [label]);
    if (opts.hint) {
      var hint = util.el('div', {
        className: 'field-hint ui-choice-hint',
        id: util.uid('hint'),
        text: opts.hint
      });
      root.appendChild(hint);
      input.setAttribute('aria-describedby', hint.id);
    }
    if (typeof opts.onChange === 'function') {
      input.addEventListener('change', function () {
        opts.onChange(input.checked);
      });
    }
    return { input: input, root: root };
  }

  // App.ui.checkbox(opts) -> controller {el, control, setChecked(bool),
  // setIndeterminate(bool)}.
  //   label (required), id, checked, indeterminate, disabled, hint,
  //   onChange(checked).
  //   el is div.ui-checkbox > label.ui-checkbox-label wrapping
  //   input.checkbox-primary and the label text; the optional .field-hint is a
  //   sibling after the label, wired by aria-describedby. The input carries
  //   data-ui-own-label, so App.ui.field refuses it.
  //   The test id option is placed on the native input (supplied by the caller).
  //   setChecked clears indeterminate. Space toggles; the browser draws focus.
  App.ui.checkbox = function (opts) {
    opts = opts || {};
    var built = build(opts, 'checkbox', 'ui-checkbox', 'ui-checkbox-label', 'checkbox-primary', {
      before: []
    });
    var input = built.input;
    if (opts.indeterminate) input.indeterminate = true;
    // A user toggle resolves the mixed state, as in a native checkbox.
    return {
      el: built.root,
      control: input,
      setChecked: function (value) {
        input.checked = !!value;
        input.indeterminate = false;
      },
      setIndeterminate: function (value) {
        input.indeterminate = !!value;
      }
    };
  };

  // App.ui.toggle(opts) -> controller {el, control, setChecked(bool)}. On/off
  // only (no indeterminate state).
  //   label (required), labelHidden (label stays the accessible name but is
  //   visually hidden), id, checked, disabled, hint, onChange(checked).
  //   el is div.ui-toggle > label.ui-toggle-label wrapping a visually hidden
  //   input[type=checkbox][role=switch].ui-toggle-input, a decorative
  //   span.ui-toggle-track (aria-hidden; the thumb is its ::after) and the
  //   text. The optional .field-hint is a sibling after the label.
  //   The test id option is placed on the native input (supplied by the caller).
  App.ui.toggle = function (opts) {
    var track = App.ui.util.el('span', { className: 'ui-toggle-track', 'aria-hidden': 'true' });
    var built = build(opts, 'toggle', 'ui-toggle', 'ui-toggle-label', 'ui-toggle-input', {
      before: [track]
    });
    built.input.setAttribute('role', 'switch');
    return {
      el: built.root,
      control: built.input,
      setChecked: function (value) {
        built.input.checked = !!value;
      }
    };
  };

  // App.ui.radioGroup(opts) -> controller {el, value(), setValue(v),
  // setDescription(value, text), optionEl(value), input(value), focus(),
  // destroy()}.
  //   legend (required), legendHidden, name, value, onChange(value), and
  //   options[] of {value, label (both required), description, disabled, and
  //   the option's own test id}. The group's own test id goes on the fieldset;
  //   an option's goes on its native radio input.
  //   el is fieldset.ui-radio-group > legend, then one div.ui-radio-option per
  //   option holding three siblings: a label.ui-radio-label wrapping the native
  //   radio and span.ui-radio-text, an optional div.field-hint (wired by
  //   aria-describedby, so the accessible name stays the label text alone) and
  //   an empty div.ui-radio-slot for caller content (optionEl). .is-checked is
  //   kept on every wrapper as a fallback for :has().
  //   name defaults to a unique id; an explicit name shared by two groups is
  //   the caller's problem (the browser would merge them into one radio set).
  //   setValue is silent (no onChange); an unknown or disabled value is a
  //   no-op, null clears. One delegated change listener sits on the fieldset;
  //   destroy() removes it and leaves el to the caller.
  App.ui.radioGroup = function (opts) {
    opts = opts || {};
    if (!opts.legend) throw new Error('App.ui.radioGroup: legend is required');
    if (!opts.options || !opts.options.length) {
      throw new Error('App.ui.radioGroup: options are required');
    }
    var util = App.ui.util;
    var name = opts.name || util.uid('radio');
    var rows = [];
    var seen = {};
    var fieldset = util.el('fieldset', { className: 'ui-radio-group' });
    if (opts.testid) fieldset.setAttribute('data-testid', opts.testid);
    fieldset.appendChild(util.el('legend', {
      className: opts.legendHidden ? 'visually-hidden' : 'ui-radio-legend',
      text: opts.legend
    }));

    function find(value) {
      for (var k = 0; k < rows.length; k++) {
        if (rows[k].value === value) return rows[k];
      }
      return null;
    }
    function sync() {
      for (var k = 0; k < rows.length; k++) {
        var on = rows[k].input.checked;
        rows[k].wrap.classList.toggle('is-checked', on);
      }
    }

    var i;
    for (i = 0; i < opts.options.length; i++) {
      var o = opts.options[i];
      if (!o || o.value === undefined || o.value === null || !o.label) {
        throw new Error('App.ui.radioGroup: each option needs a value and a label');
      }
      var key = String(o.value);
      if (seen[key]) throw new Error('App.ui.radioGroup: duplicate value');
      seen[key] = true;
      var input = util.el('input', { type: 'radio', className: 'ui-radio-input' });
      input.name = name;
      input.value = key;
      input.id = util.uid('rd');
      input.setAttribute('data-ui-own-label', 'true');
      if (o.testid) input.setAttribute('data-testid', o.testid);
      if (o.disabled) input.disabled = true;
      var label = util.el('label', { className: 'ui-radio-label' }, [
        input,
        util.el('span', { className: 'ui-radio-text', text: o.label })
      ]);
      label.htmlFor = input.id;
      var slot = util.el('div', { className: 'ui-radio-slot' });
      var wrap = util.el('div', {
        className: 'ui-radio-option' + (o.disabled ? ' is-disabled' : '')
      }, [label]);
      var row = { value: o.value, input: input, wrap: wrap, slot: slot, desc: null };
      if (o.description) {
        row.desc = util.el('div', {
          className: 'field-hint ui-radio-description',
          id: util.uid('hint'),
          text: o.description
        });
        wrap.appendChild(row.desc);
        input.setAttribute('aria-describedby', row.desc.id);
      }
      wrap.appendChild(slot);
      fieldset.appendChild(wrap);
      rows.push(row);
    }

    function setValue(value) {
      if (value === null || value === undefined) {
        for (var k = 0; k < rows.length; k++) rows[k].input.checked = false;
      } else {
        var row = find(value);
        if (!row || row.input.disabled) return;
        row.input.checked = true;
      }
      sync();
    }
    setValue(opts.value);

    function onChange(e) {
      sync();
      var t = e.target;
      if (typeof opts.onChange !== 'function' || !t || !t.checked) return;
      for (var k = 0; k < rows.length; k++) {
        if (rows[k].input === t) {
          opts.onChange(rows[k].value);
          return;
        }
      }
    }
    fieldset.addEventListener('change', onChange);

    return {
      el: fieldset,
      value: function () {
        for (var k = 0; k < rows.length; k++) {
          if (rows[k].input.checked) return rows[k].value;
        }
        return null;
      },
      setValue: setValue,
      setDescription: function (value, text) {
        var row = find(value);
        if (!row) return;
        if (!text) {
          if (row.desc && row.desc.parentNode) row.desc.parentNode.removeChild(row.desc);
          row.desc = null;
          row.input.removeAttribute('aria-describedby');
          return;
        }
        if (!row.desc) {
          row.desc = util.el('div', {
            className: 'field-hint ui-radio-description',
            id: util.uid('hint')
          });
          row.wrap.insertBefore(row.desc, row.slot);
          row.input.setAttribute('aria-describedby', row.desc.id);
        }
        row.desc.textContent = text;
      },
      optionEl: function (value) {
        var row = find(value);
        return row ? row.slot : null;
      },
      input: function (value) {
        var row = find(value);
        return row ? row.input : null;
      },
      focus: function () {
        var first = null;
        for (var k = 0; k < rows.length; k++) {
          if (rows[k].input.disabled) continue;
          if (rows[k].input.checked) {
            rows[k].input.focus();
            return;
          }
          if (!first) first = rows[k].input;
        }
        if (first) first.focus();
      },
      destroy: function () {
        fieldset.removeEventListener('change', onChange);
      }
    };
  };
})();
