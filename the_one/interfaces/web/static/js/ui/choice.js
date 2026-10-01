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
})();
