(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var INPUT_TYPES = ['text', 'password', 'search', 'email', 'url', 'number'];

  function tokens(value) {
    return (value || '').split(/\s+/).filter(Boolean);
  }

  // App.ui.textInput(opts) -> HTMLInputElement (class field-input).
  //   id (default: a generated ui-in-<n>), name, type (text | password |
  //   search | email | url | number; default text), value, placeholder,
  //   disabled, required, autocomplete, onInput, dataset (a plain object copied to
  //   data-*; a `testid` key is ignored, the test id option wins).
  //   The test id option is placed on the input itself (supplied by the caller).
  App.ui.textInput = function (opts) {
    opts = opts || {};
    var type = opts.type || 'text';
    if (INPUT_TYPES.indexOf(type) === -1) {
      throw new Error('App.ui.textInput: unknown type "' + type + '"');
    }
    var input = App.ui.util.el('input', { className: 'field-input' });
    input.type = type;
    input.id = opts.id || App.ui.util.uid('in');
    if (opts.name) input.name = opts.name;
    if (opts.value !== undefined && opts.value !== null) input.value = String(opts.value);
    if (opts.placeholder) input.placeholder = opts.placeholder;
    if (opts.disabled) input.disabled = true;
    if (opts.required) input.required = true;
    if (opts.autocomplete) input.setAttribute('autocomplete', opts.autocomplete);
    App.ui.util.applyDataset(input, opts.dataset);
    if (opts.testid) input.setAttribute('data-testid', opts.testid);
    if (typeof opts.onInput === 'function') input.addEventListener('input', opts.onInput);
    return input;
  };

  // App.ui.textarea(opts) -> HTMLTextAreaElement (class field-input
  // field-textarea).
  //   id (default: a generated ui-ta-<n>), name, value, placeholder, rows
  //   (default 4), disabled, required, onInput, dataset.
  //   The test id option is placed on the textarea itself (supplied by the caller).
  App.ui.textarea = function (opts) {
    opts = opts || {};
    var area = App.ui.util.el('textarea', { className: 'field-input field-textarea' });
    area.id = opts.id || App.ui.util.uid('ta');
    if (opts.name) area.name = opts.name;
    area.rows = opts.rows || 4;
    if (opts.value !== undefined && opts.value !== null) area.value = String(opts.value);
    if (opts.placeholder) area.placeholder = opts.placeholder;
    if (opts.disabled) area.disabled = true;
    if (opts.required) area.required = true;
    App.ui.util.applyDataset(area, opts.dataset);
    if (opts.testid) area.setAttribute('data-testid', opts.testid);
    if (typeof opts.onInput === 'function') area.addEventListener('input', opts.onInput);
    return area;
  };

  function buildOption(spec) {
    var option = App.ui.util.el('option', { text: spec.label });
    option.value = String(spec.value);
    if (spec.disabled) option.disabled = true;
    return option;
  }

  // App.ui.select(opts) -> HTMLSelectElement (class field-input field-select).
  //   id (default: a generated ui-sel-<n>), name, options (required, non-empty:
  //   {value, label, disabled} entries, or groups {label, options} rendered as
  //   optgroups), value (must be one of the option values), disabled, required,
  //   dataset, onChange(event). Labels are set with textContent.
  //   The test id option is placed on the select itself (supplied by the caller).
  App.ui.select = function (opts) {
    opts = opts || {};
    var specs = opts.options;
    if (!Array.isArray(specs) || !specs.length) {
      throw new Error('App.ui.select: options must be a non-empty array');
    }
    var select = App.ui.util.el('select', { className: 'field-input field-select' });
    var values = [];
    var i;
    var j;
    for (i = 0; i < specs.length; i++) {
      var spec = specs[i];
      if (Array.isArray(spec.options)) {
        var group = App.ui.util.el('optgroup', { label: spec.label });
        for (j = 0; j < spec.options.length; j++) {
          values.push(String(spec.options[j].value));
          group.appendChild(buildOption(spec.options[j]));
        }
        select.appendChild(group);
      } else {
        values.push(String(spec.value));
        select.appendChild(buildOption(spec));
      }
    }
    if (!values.length) throw new Error('App.ui.select: options must be a non-empty array');
    if (opts.value !== undefined && opts.value !== null) {
      if (values.indexOf(String(opts.value)) === -1) {
        throw new Error('App.ui.select: value "' + opts.value + '" is not among the options');
      }
      select.value = String(opts.value);
    }
    select.id = opts.id || App.ui.util.uid('sel');
    if (opts.name) select.name = opts.name;
    if (opts.disabled) select.disabled = true;
    if (opts.required) select.required = true;
    App.ui.util.applyDataset(select, opts.dataset);
    if (opts.testid) select.setAttribute('data-testid', opts.testid);
    if (typeof opts.onChange === 'function') select.addEventListener('change', opts.onChange);
    return select;
  };

  // App.ui.infoButton(opts) -> {el, button, descriptionId} (M31 F1 L4).
  //   description (required), label (the control's label; names the button), testid
  //   (on the button).
  //   el is span.ui-info wrapping button.field-info-icon[type=button] (title is the
  //   full description, the hover tooltip; aria-label is the short "More information
  //   about {label}", or "More information" without a label, so the description is not
  //   heard twice; 14px info icon) and a span.visually-hidden carrying the description,
  //   so a control can reference descriptionId from aria-describedby. Tab reaches the
  //   button.
  App.ui.infoButton = function (opts) {
    opts = opts || {};
    if (!opts.description) throw new Error('App.ui.infoButton: description is required');
    var util = App.ui.util;
    var button = util.el('button', {
      type: 'button',
      className: 'field-info-icon',
      title: opts.description,
      'aria-label': opts.label ? 'More information about ' + opts.label : 'More information'
    }, [App.ui.icon('info', { size: 'sm' })]);
    if (opts.testid) button.setAttribute('data-testid', opts.testid);
    var desc = util.el('span', {
      className: 'visually-hidden',
      id: util.uid('info'),
      text: opts.description
    });
    var wrap = util.el('span', { className: 'ui-info' }, [button, desc]);
    return { el: wrap, button: button, descriptionId: desc.id };
  };

  // App.ui.field(opts) -> controller {el, control, setError(msg|null),
  // setHint(msg|null)}. The same controller shape is used for every composite.
  //   label (required), labelHidden (visually hidden, still in the DOM),
  //   control (required element; gets a generated id when it has none),
  //   host (optional element that CONTAINS the control, such as a secretInput's
  //   wrapper: the group places it in the control's slot, while the label,
  //   aria-describedby and aria-invalid still belong to the control),
  //   hint, hintTestid (the test id of the hint element, kept across setHint
  //   calls), error, info (a description: the label then sits in
  //   div.field-group-label beside an infoButton, as siblings, and the control's
  //   aria-describedby leads with the description id). The test id option goes
  //   on the .field-group wrapper.
  //   Throws for a control marked data-ui-own-label (checkbox, toggle).
  // setLabel(text) replaces the visible label text.
  // The label is a direct child of the wrapper (the CSS keys off
  // .field-group > label). Hint and error elements each carry an id and are
  // joined into the control's aria-describedby, hint first, then error.
  App.ui.field = function (opts) {
    opts = opts || {};
    var control = opts.control;
    if (!control || control.nodeType !== 1) throw new Error('App.ui.field: control must be an element');
    if (!opts.label) throw new Error('App.ui.field: label is required');
    if (control.getAttribute('data-ui-own-label') === 'true' ||
        (control.querySelector && control.querySelector('[data-ui-own-label="true"]'))) {
      throw new Error('field: checkbox/toggle carry their own label');
    }
    if (!control.id) control.id = App.ui.util.uid('ctl');

    var label = App.ui.util.el('label', {
      className: opts.labelHidden ? 'visually-hidden' : null,
      text: opts.label
    });
    label.htmlFor = control.id;
    var info = opts.info ? App.ui.infoButton({ description: opts.info, label: opts.label }) : null;
    var head = info ? App.ui.util.el('div', { className: 'field-group-label' }, [label, info.el]) : label;
    var wrapper = App.ui.util.el('div', { className: 'field-group' }, [head, opts.host || control]);
    if (opts.testid) wrapper.setAttribute('data-testid', opts.testid);

    var hintEl = null;
    var errorEl = null;
    var foreign = tokens(control.getAttribute('aria-describedby'));
    if (info) foreign.push(info.descriptionId);

    function wire() {
      var ids = foreign.slice();
      if (hintEl) ids.push(hintEl.id);
      if (errorEl) ids.push(errorEl.id);
      if (ids.length) {
        control.setAttribute('aria-describedby', ids.join(' '));
      } else {
        control.removeAttribute('aria-describedby');
      }
    }

    function setHint(message) {
      if (message === null || message === undefined || message === '') {
        if (hintEl) {
          wrapper.removeChild(hintEl);
          hintEl = null;
        }
      } else if (hintEl) {
        hintEl.textContent = message;
      } else {
        hintEl = App.ui.util.el('div', {
          className: 'field-hint',
          id: App.ui.util.uid('hint'),
          text: message
        });
        if (opts.hintTestid) hintEl.setAttribute('data-testid', opts.hintTestid);
        wrapper.insertBefore(hintEl, errorEl);
      }
      wire();
    }

    function setError(message) {
      if (message === null || message === undefined || message === '') {
        if (errorEl) {
          wrapper.removeChild(errorEl);
          errorEl = null;
        }
        control.classList.remove('is-invalid');
        control.removeAttribute('aria-invalid');
      } else {
        if (errorEl) {
          if (errorEl.textContent !== message) errorEl.textContent = message;
        } else {
          errorEl = App.ui.util.el('div', {
            className: 'field-error',
            id: App.ui.util.uid('err'),
            role: 'alert',
            text: message
          });
          wrapper.appendChild(errorEl);
        }
        control.classList.add('is-invalid');
        control.setAttribute('aria-invalid', 'true');
      }
      wire();
    }

    if (opts.hint) setHint(opts.hint);
    if (opts.error) setError(opts.error);
    // An info description alone (no hint or error) still joins aria-describedby.
    wire();

    return {
      el: wrapper,
      control: control,
      setError: setError,
      setHint: setHint,
      setLabel: function (text) {
        label.textContent = text;
      }
    };
  };

  // App.ui.secretInput(opts) -> controller {el, input, button, setRevealed(bool),
  // setValue(text)} (M31 F1 L7, DD9): a password field with a reveal button.
  //   value, label (the input's accessible name, for a field with no visible
  //   label), id, placeholder, autocomplete (default new-password), dataset
  //   (copied onto the INPUT, never the wrapper), testid (on the input),
  //   revealTestid (on the reveal button).
  //   el is div.api-key-wrap holding input.field-input[type=password] and an
  //   icon-only button.api-key-eye (eye / eye-off), named "Show password" or
  //   "Hide password", with aria-pressed. Placed in App.ui.field through
  //   host: el (control: input).
  //   Secret handling: the value is only ever written through the .value
  //   property, never an attribute, a title or an aria-label; revealing flips
  //   only the input type. setValue replaces the value and hides it again.
  //   Focus stays on the button when it is toggled (only its icon is swapped).
  App.ui.secretInput = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var input = App.ui.textInput({
      type: 'password',
      id: opts.id,
      placeholder: opts.placeholder,
      autocomplete: opts.autocomplete || 'new-password',
      dataset: opts.dataset,
      testid: opts.testid,
      value: opts.value
    });
    if (opts.label) input.setAttribute('aria-label', opts.label);
    var button = util.el('button', {
      type: 'button',
      className: 'api-key-eye',
      'aria-label': 'Show password',
      'aria-pressed': 'false'
    }, [App.ui.icon('eye', { size: 'sm' })]);
    if (opts.revealTestid) button.setAttribute('data-testid', opts.revealTestid);
    var revealed = false;
    function setRevealed(value) {
      revealed = !!value;
      input.type = revealed ? 'text' : 'password';
      button.replaceChildren(App.ui.icon(revealed ? 'eye-off' : 'eye', { size: 'sm' }));
      button.setAttribute('aria-label', revealed ? 'Hide password' : 'Show password');
      button.setAttribute('aria-pressed', revealed ? 'true' : 'false');
    }
    button.addEventListener('click', function () {
      setRevealed(!revealed);
    });
    return {
      el: util.el('div', { className: 'api-key-wrap' }, [input, button]),
      input: input,
      button: button,
      setRevealed: setRevealed,
      setValue: function (text) {
        input.value = text === null || text === undefined ? '' : String(text);
        setRevealed(false);
      }
    };
  };
})();
