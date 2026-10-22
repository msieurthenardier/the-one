// App.studio.toolOverrideFields -- the per-agent tool-override field renderer
// (M31 F2 L08b, flight DD3/DD8). Builds one override field as DOM nodes from the
// control library (App.ui.field, chipList, infoButton through field's `info`,
// secretInput, select, textInput, checkbox); the Tools tab mounts them in a tool
// row's "Overrides" disclosure. The admin Built-in tools editor keeps its
// string-built twin (areas/admin/tools-form-helpers.js) until Flight 3.
//
//   var r = App.studio.toolOverrideFields.render(name, prop, value, ctx)
//     name   the field name; prop the JSON-schema property (type, x_marker,
//            ui_hint, ui_choices, minimum, maximum, title, description, items)
//     value  the agent's value, already seeded by the caller (see seedValue)
//     ctx    { toolName, operatorValue, onChange }
//   -> { el, control } or null when the field is hidden (see below).
//
// Hidden (null): a non-boolean field with no agent marker. Only Narrow,
// NarrowSuperset, NarrowPrefix and Substitute fields (and booleans) are
// agent-overridable; the resolver would reject any other.
//
// Every value-bearing control carries, on the control element itself (never the
// field wrapper), data-tool-override-tool, data-tool-override-field and
// data-field-type (array: also data-marker). agent-form-data.js::collectFormData
// walks `[data-tool-override-tool][data-tool-override-field]` and reads each
// through App.adminFormHelpers.readFieldValue, and derives the "loaded tools" set
// (squawk 0223) from the same attributes: do not move them.
//
// Field kinds:
//   boolean                          checkbox (App.ui.checkbox's input in a stacked field)
//   integer + ui_hint dropdown       select over ui_choices, numeric choices
//     (+ ui_choices)                 filtered to <= operatorValue under Narrow;
//                                    "(custom)" option for an unknown current value
//   integer                          number input; min = prop.minimum, max = the
//                                    operator's value under Narrow (else prop.maximum)
//   string + dropdown                select over ui_choices, "(custom)" option
//   string + password                App.ui.secretInput
//   string                           text input (Substitute)
//   array                            App.ui.chipList; NarrowSuperset: the operator's
//                                    items are locked chips (no remove button) and are
//                                    part of the union that is sent
//   anything else                    JSON text input (data-field-type unknown)
//
// Chip validation (chipList `validate`), each rule exactly as the string path had it:
//   Narrow         array: any value accepted (the server checks the subset, 422)
//   NarrowSuperset array: any value accepted; operator items are locked so they cannot
//                  be removed (that is the superset rule)
//   NarrowPrefix   array: any value accepted (the server checks the prefix, 422)
//   other markers  accepted.
// No per-override error painting exists in the agent editor (a PUT 422 shows the
// editor's own error), so there is no node version of renderFieldErrors/applyShowIf.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function allowed(prop) {
    var marker = prop.x_marker;
    if (prop.type === 'boolean') return true;
    return marker === 'Narrow' || marker === 'NarrowSuperset' ||
      marker === 'NarrowPrefix' || marker === 'Substitute';
  }

  // The value an override field starts with: the agent's stored override, else the
  // inherited baseline (Substitute starts blank; NarrowSuperset starts at the
  // operator's items; everything else at the operator's value).
  function seedValue(prop, agentOverride, fieldName, operatorVal) {
    var marker = prop.x_marker;
    var agentVal = (fieldName in agentOverride) ? agentOverride[fieldName] : null;
    if (agentVal !== null) return agentVal;
    if (marker === 'Substitute') return '';
    if (marker === 'NarrowSuperset' && Array.isArray(operatorVal)) return operatorVal.slice();
    return operatorVal;
  }

  function optionValue(v) {
    return (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean')
      ? String(v)
      : JSON.stringify(v);
  }

  function sameChoice(choiceValue, value) {
    return (typeof choiceValue === 'object' && choiceValue !== null)
      ? JSON.stringify(choiceValue) === JSON.stringify(value)
      : choiceValue === value;
  }

  // The select's options and selected value, with the "(custom)" entry for a
  // current value that is not among the choices. Returns null with no options.
  function selectOptions(choices, value, stringMode) {
    var options = [];
    var selected = null;
    var sawValue = false;
    for (var i = 0; i < choices.length; i++) {
      var cv = choices[i].value;
      var ov = optionValue(cv);
      var equal = stringMode
        ? ov === String(value !== undefined && value !== null ? value : '')
        : sameChoice(cv, value);
      if (equal) {
        sawValue = true;
        selected = ov;
      }
      options.push({ value: ov, label: choices[i].label || ov });
    }
    var hasValue = value !== undefined && value !== null && (!stringMode || value !== '');
    if (!sawValue && hasValue) {
      var custom = optionValue(value);
      options.push({ value: custom, label: custom + ' (custom)' });
      selected = custom;
    }
    if (!options.length) return null;
    return { options: options, value: selected === null ? options[0].value : selected };
  }

  // Numeric choices are filtered to <= the operator's value under Narrow; other
  // choice types pass through (command_denylist baselines are arrays).
  function narrowedChoices(prop, operatorValue) {
    if (prop.x_marker !== 'Narrow' || typeof operatorValue !== 'number') return prop.ui_choices;
    var out = [];
    for (var i = 0; i < prop.ui_choices.length; i++) {
      var cv = prop.ui_choices[i].value;
      if (typeof cv !== 'number' || cv <= operatorValue) out.push(prop.ui_choices[i]);
    }
    return out;
  }

  function render(name, prop, value, ctx) {
    ctx = ctx || {};
    prop = prop || {};
    if (!allowed(prop)) return null;
    var ui = window.App.ui;
    var toolName = ctx.toolName;
    var operatorValue = ctx.operatorValue;
    var marker = prop.x_marker;
    var ftype = prop.type;
    var hint = prop.ui_hint;
    var labelText = prop.title || name;
    var fire = function () { if (typeof ctx.onChange === 'function') ctx.onChange(); };
    var dataset = { toolOverrideTool: toolName, toolOverrideField: name };

    function withType(type) {
      return { toolOverrideTool: toolName, toolOverrideField: name, fieldType: type };
    }
    function wrap(control, host) {
      var f = ui.field({
        label: labelText,
        info: prop.description || undefined,
        control: control,
        host: host
      });
      f.el.setAttribute('data-field-name', name);
      f.el.classList.add('tool-override-field');
      return { el: f.el, control: control, field: f };
    }
    function listen(control) {
      control.addEventListener('change', fire);
      control.addEventListener('input', fire);
    }

    if (ftype === 'boolean') {
      // The checkbox keeps the stacked layout of every other override field (the label
      // above the control, DD4: no visible change beyond the approved ones), so only the
      // library's input is taken: App.ui.checkbox builds it, and it is placed in an
      // App.ui.field instead of the checkbox's own label row.
      var cb = ui.checkbox({
        label: labelText,
        checked: !!value,
        dataset: dataset,
        onChange: fire
      });
      var box = cb.control;
      box.removeAttribute('data-ui-own-label');
      box.parentNode.removeChild(box);
      return wrap(box);
    }

    if (ftype === 'integer' && hint === 'dropdown' &&
        Array.isArray(prop.ui_choices) && prop.ui_choices.length > 0) {
      var intSel = selectOptions(narrowedChoices(prop, operatorValue), value, false);
      if (intSel) {
        var intSelect = ui.select({
          options: intSel.options,
          value: intSel.value,
          dataset: withType('integer')
        });
        listen(intSelect);
        return wrap(intSelect);
      }
    }

    if (ftype === 'string' && hint === 'dropdown' &&
        Array.isArray(prop.ui_choices) && prop.ui_choices.length > 0) {
      var strSel = selectOptions(prop.ui_choices, value, true);
      if (strSel) {
        var strSelect = ui.select({
          options: strSel.options,
          value: strSel.value,
          dataset: withType('string')
        });
        listen(strSelect);
        return wrap(strSelect);
      }
    }

    if (ftype === 'integer') {
      var min = (prop.minimum !== undefined && prop.minimum !== null) ? prop.minimum : null;
      var max;
      if (marker === 'Narrow') {
        max = (typeof operatorValue === 'number')
          ? operatorValue
          : ((prop.maximum !== undefined && prop.maximum !== null) ? prop.maximum : null);
      } else {
        max = (prop.maximum !== undefined && prop.maximum !== null) ? prop.maximum : null;
      }
      var num = ui.textInput({
        type: 'number',
        value: value !== undefined && value !== null ? value : '',
        dataset: withType('integer')
      });
      if (min !== null) num.setAttribute('min', String(min));
      if (max !== null) num.setAttribute('max', String(max));
      listen(num);
      return wrap(num);
    }

    if (ftype === 'array') {
      var locked = (marker === 'NarrowSuperset' && Array.isArray(operatorValue))
        ? operatorValue.map(String)
        : [];
      var items = Array.isArray(value) ? value.map(String) : [];
      // The union the string path rendered: operator items first, then the agent's.
      var union = [];
      var seen = Object.create(null);
      locked.concat(items).forEach(function (v) {
        if (!seen[v]) {
          seen[v] = true;
          union.push(v);
        }
      });
      var chips = ui.chipList({
        values: union,
        locked: locked,
        inputId: ui.util.uid('ovr'),
        dataset: {
          toolOverrideTool: toolName,
          toolOverrideField: name,
          fieldType: 'array',
          marker: marker || ''
        },
        validate: function () { return true; },
        onChange: fire
      });
      if (!marker) chips.el.removeAttribute('data-marker');
      var chipField = wrap(chips.input, chips.el);
      chipField.chips = chips;
      chipField.control = chips.el;
      return chipField;
    }

    if (ftype === 'string' && hint === 'password') {
      var secret = ui.secretInput({
        value: value !== undefined && value !== null ? String(value) : '',
        dataset: withType('string')
      });
      listen(secret.input);
      return wrap(secret.input, secret.el);
    }

    if (ftype === 'string') {
      var text = ui.textInput({
        type: 'text',
        value: value !== undefined && value !== null ? String(value) : '',
        dataset: withType('string')
      });
      listen(text);
      return wrap(text);
    }

    var unknown = ui.textInput({
      type: 'text',
      value: JSON.stringify(value),
      dataset: withType('unknown')
    });
    listen(unknown);
    return wrap(unknown);
  }

  window.App.studio.toolOverrideFields = {
    render: render,
    seedValue: seedValue,
    allowed: allowed
  };
})();
