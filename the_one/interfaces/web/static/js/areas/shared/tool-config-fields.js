// App.toolConfigFields -- the shared tool-settings field module (M31 F4 L05b,
// flight DD13). One field of a built-in tool's Config schema, built as DOM from the
// control library, for two hosts:
//   admin   Settings > Built-in tools (the operator's own settings)
//   agent   the agent editor's Tools tab (an agent's narrowing overrides)
// Grown from areas/studio/tool-override-fields.js (agent mode only), which stays
// until leg 05c moves the Tools tab onto this module; the admin editor moves in
// leg 07a. Nothing here is a string-built sink.
//
//   var h = App.toolConfigFields.render(name, prop, value, opts)
//     name   the field name; prop the JSON-schema property (type, x_marker, ui_hint,
//            ui_choices, minimum, maximum, title, description, items, show_if)
//     value  the value the field starts with (agent mode: already seeded, see seedValue)
//     opts   { mode: 'admin' | 'agent' (default admin), toolName (agent), operatorValue
//              (agent), onChange }
//   -> { el, control, field, value(), setValue(v), setError(msg|null), setVisible(bool),
//        validate(), chips? }, or null when agent mode hides the field.
//     el       the row (a div.field-group, or the checkbox row)
//     control  the value node that carries the data hooks (the input, select, the chip
//              list root, the checkbox input)
//     field    the App.ui.field controller (null for a checkbox, which has its own label)
//     value()  readValue(control)        validate()  the agent-mode whole-number check:
//              returns the message (and shows it on the field) or null
//
//   App.toolConfigFields.showIf(properties, handles) -> { apply(), destroy() }
//     Wires each property's `show_if` ({controllingField: expectedValue}) to the row's
//     visibility (setVisible). `handles` maps field name -> render() handle. A condition
//     whose controlling field has no handle (a field the tool does not show) is treated
//     as absent: the row stays shown. A hidden row keeps its value (it is still read).
//
//   App.toolConfigFields.readValue(el) -> the value of a control rendered by render()
//   App.toolConfigFields.invalidMessage(el) -> "Enter a whole number." / "Must be N or more" /
//     "Must be at most N" (agent override range) for a number control
//     whose text is not a whole number or out of range, else null
//   App.toolConfigFields.seedValue / allowed   (agent mode helpers, see below)
//
// DOM hooks (tests and the save paths depend on them; do not move them):
//   admin  control: data-field="{name}", id "tef-{name}" (the chip list: data-field on
//          its root, the id on its inner input); row: .tools-editor-field and
//          data-field-name.
//   agent  control: data-tool-override-tool, data-tool-override-field (agent-form-data.js
//          derives the squawk 0223 "loaded tools" set from them); row: .tool-override-field
//          and data-field-name; the row has NO data-tool-override-field.
//   both   data-field-type on the control (integer | string | array | unknown; a
//          checkbox has none) and data-marker on a chip list that has a marker.
//
// Field kinds:
//   boolean                      App.ui.checkbox, label inline, info button (A10)
//   integer + ui_hint dropdown   select over ui_choices; agent mode: numeric choices
//                                above the operator's value are dropped (Narrow); a value
//                                that is not a choice stays selectable as "<humanised>
//                                (custom)" (A8)
//   integer                      text input, inputmode numeric (not type=number, which
//                                reads "12abc" as ''); min/max are attributes only,
//                                never checked here (the server and the resolver do)
//   string + dropdown            select over ui_choices, "(custom)" for an unknown value
//   string + password            App.ui.secretInput
//   string                       text input
//   array                        App.ui.chipList; agent mode + NarrowSuperset: the
//                                operator's items are locked chips and part of the union
//   anything else                JSON text input (data-field-type unknown)
//
// Number parsing (readValue): blank -> '' (skipped by the save paths); an integer
// string -> the number; anything else -> the raw string. Admin mode sends it and the
// tools PUT's 422 lands on the field (leg 07a); agent mode shows "Enter a whole
// number." on the field as you type and the agent Save is refused (leg 05c).
//
// A8, custom preset values: the unit comes from the field name (a `_bytes` or
// `_seconds` token), not a schema hint. Bytes: MB / KB (divided by 1024) when the value
// divides evenly, else "{n} B"; seconds: h / m (60) when it divides evenly, else "{n}s".
// A field without a unit token shows the plain number.
(function () {
  'use strict';
  window.App = window.App || {};

  var INT_RE = /^-?\d+$/;
  var WHOLE_NUMBER_MESSAGE = 'Enter a whole number.';

  // Only Narrow, NarrowSuperset, NarrowPrefix and Substitute fields (and booleans)
  // are agent-overridable; the resolver would reject any other.
  function allowed(prop) {
    var marker = prop.x_marker;
    if (prop.type === 'boolean') return true;
    return marker === 'Narrow' || marker === 'NarrowSuperset' ||
      marker === 'NarrowPrefix' || marker === 'Substitute';
  }

  // The value an agent override field starts with: the agent's stored override, else
  // the inherited baseline (Substitute starts blank; NarrowSuperset starts at the
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

  // A8: the plain label of a custom numeric value, from the field name's unit token.
  function humanValue(name, value) {
    if (typeof value !== 'number' || !isFinite(value)) return optionValue(value);
    var units;
    var i;
    if (/_bytes(_|$)/.test(name)) {
      units = [['MB', 1048576], ['KB', 1024]];
      for (i = 0; i < units.length; i++) {
        if (value >= units[i][1] && value % units[i][1] === 0) {
          return (value / units[i][1]) + units[i][0];
        }
      }
      return value + ' B';
    }
    if (/_seconds(_|$)/.test(name)) {
      units = [['h', 3600], ['m', 60]];
      for (i = 0; i < units.length; i++) {
        if (value >= units[i][1] && value % units[i][1] === 0) {
          return (value / units[i][1]) + units[i][0];
        }
      }
      return value + 's';
    }
    return String(value);
  }

  // The select's options and selected value, with the "(custom)" entry for a current
  // value that is not among the choices. Returns null with no options.
  function selectOptions(name, choices, value, stringMode) {
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
      options.push({
        value: custom,
        label: (stringMode ? custom : humanValue(name, value)) + ' (custom)'
      });
      selected = custom;
    }
    if (!options.length) return null;
    return { options: options, value: selected === null ? options[0].value : selected };
  }

  // Numeric choices are filtered to <= the operator's value under Narrow (agent mode);
  // other choice types pass through (command_denylist baselines are arrays).
  function narrowedChoices(prop, operatorValue) {
    if (prop.x_marker !== 'Narrow' || typeof operatorValue !== 'number') return prop.ui_choices;
    var out = [];
    for (var i = 0; i < prop.ui_choices.length; i++) {
      var cv = prop.ui_choices[i].value;
      if (typeof cv !== 'number' || cv <= operatorValue) out.push(prop.ui_choices[i]);
    }
    return out;
  }

  function readValue(el) {
    if (el.dataset && el.dataset.fieldType === 'array') {
      return window.App.ui.chipList.valuesOf(el);
    }
    if (el.type === 'checkbox') return el.checked;
    var ftype = el.dataset.fieldType;
    var val = el.value;
    if (ftype === 'integer') {
      if (val.charAt(0) === '[' || val.charAt(0) === '{') {
        try { return JSON.parse(val); } catch (e) { /* fall through */ }
      }
      var trimmed = val.trim();
      if (trimmed === '') return '';
      return INT_RE.test(trimmed) ? Number(trimmed) : val;
    }
    if (ftype === 'unknown') {
      try { return JSON.parse(val); } catch (e2) { return val; }
    }
    return val;
  }

  // The message for a number control whose text is not a whole number, else null (a
  // blank is fine: it is skipped). Only a text input read as an integer can be invalid;
  // a select cannot. The agent editor's Save asks every override control through this.
  function invalidMessage(el) {
    if (!el.dataset || el.dataset.fieldType !== 'integer' || el.tagName !== 'INPUT') return null;
    var raw = el.value.trim();
    if (raw === '') return null;
    if (!INT_RE.test(raw)) return WHOLE_NUMBER_MESSAGE;
    // An agent override is also held to the schema's range (the operator's value for a
    // Narrow field); the controls carry it as min/max, set in agent mode only.
    if (el.dataset.toolOverrideTool === undefined) return null;
    var n = Number(raw);
    var lo = el.getAttribute('min');
    var hi = el.getAttribute('max');
    if (lo !== null && lo !== '' && n < Number(lo)) return 'Must be ' + lo + ' or more';
    if (hi !== null && hi !== '' && n > Number(hi)) return 'Must be at most ' + hi;
    return null;
  }

  function render(name, prop, value, opts) {
    opts = opts || {};
    prop = prop || {};
    var mode = opts.mode === 'agent' ? 'agent' : 'admin';
    var admin = mode === 'admin';
    if (!admin && !allowed(prop)) return null;
    var ui = window.App.ui;
    var toolName = opts.toolName;
    var operatorValue = opts.operatorValue;
    var marker = prop.x_marker;
    var ftype = prop.type;
    var hint = prop.ui_hint;
    var labelText = prop.title || name;
    var controlId = admin ? 'tef-' + name : undefined;
    var fire = function () { if (typeof opts.onChange === 'function') opts.onChange(); };

    function dataFor(type, extra) {
      var d = admin ? { field: name } : { toolOverrideTool: toolName, toolOverrideField: name };
      if (type) d.fieldType = type;
      if (extra) {
        for (var k in extra) {
          if (Object.prototype.hasOwnProperty.call(extra, k)) d[k] = extra[k];
        }
      }
      return d;
    }
    function decorate(row) {
      row.setAttribute('data-field-name', name);
      row.classList.add(admin ? 'tools-editor-field' : 'tool-override-field');
    }
    function listen(control) {
      control.addEventListener('change', fire);
      control.addEventListener('input', fire);
    }
    function fieldAround(control, host) {
      var f = ui.field({
        label: labelText,
        info: prop.description || undefined,
        control: control,
        host: host
      });
      decorate(f.el);
      return f;
    }
    function setVisible(row, visible) {
      row.classList.toggle('is-hidden', !visible);
      if (visible) row.removeAttribute('aria-hidden');
      else row.setAttribute('aria-hidden', 'true');
    }
    // The handle every kind returns. `setControlValue` writes a value into the control.
    function handle(row, control, field, setControlValue, extra) {
      var h = {
        el: row,
        control: control,
        field: field,
        value: function () { return readValue(control); },
        setValue: setControlValue,
        setError: function (msg) { if (field) field.setError(msg); },
        setVisible: function (visible) { setVisible(row, visible); },
        validate: function () { return null; }
      };
      if (extra) {
        for (var k in extra) {
          if (Object.prototype.hasOwnProperty.call(extra, k)) h[k] = extra[k];
        }
      }
      return h;
    }
    function setSelectValue(select, selectName, stringMode) {
      return function (v) {
        var want = optionValue(v);
        var found = false;
        for (var i = 0; i < select.options.length; i++) {
          if (select.options[i].value === want) found = true;
        }
        if (!found) {
          var o = document.createElement('option');
          o.value = want;
          o.textContent = (stringMode ? want : humanValue(selectName, v)) + ' (custom)';
          select.appendChild(o);
        }
        select.value = want;
      };
    }

    if (ftype === 'boolean') {
      var cb = ui.checkbox({
        label: labelText,
        id: controlId,
        checked: !!value,
        info: prop.description || undefined,
        dataset: dataFor(null),
        onChange: fire
      });
      decorate(cb.el);
      var boolError = null;
      var h = handle(cb.el, cb.control, null, function (v) { cb.setChecked(!!v); });
      // A checkbox has no field wrapper, so its error line is a library status line
      // placed under the checkbox.
      var baseDescribedBy = cb.control.getAttribute('aria-describedby');
      h.setError = function (msg) {
        if (!msg) {
          if (boolError) {
            boolError.el.parentNode.removeChild(boolError.el);
            boolError = null;
          }
          cb.control.removeAttribute('aria-invalid');
          if (baseDescribedBy) cb.control.setAttribute('aria-describedby', baseDescribedBy);
          else cb.control.removeAttribute('aria-describedby');
          return;
        }
        if (!boolError) {
          boolError = ui.status({ role: 'alert', led: false, textTone: true });
          boolError.el.id = ui.util.uid('err');
          cb.el.appendChild(boolError.el);
        }
        boolError.set('danger', msg);
        cb.control.setAttribute('aria-invalid', 'true');
        cb.control.setAttribute(
          'aria-describedby',
          (baseDescribedBy ? baseDescribedBy + ' ' : '') + boolError.el.id
        );
      };
      return h;
    }

    if (ftype === 'integer' && hint === 'dropdown' &&
        Array.isArray(prop.ui_choices) && prop.ui_choices.length > 0) {
      var intSel = selectOptions(name, narrowedChoices(prop, operatorValue), value, false);
      if (intSel) {
        var intSelect = ui.select({
          id: controlId,
          options: intSel.options,
          value: intSel.value,
          dataset: dataFor('integer')
        });
        listen(intSelect);
        var intField = fieldAround(intSelect);
        return handle(intField.el, intSelect, intField, setSelectValue(intSelect, name, false));
      }
    }

    if (ftype === 'string' && hint === 'dropdown' &&
        Array.isArray(prop.ui_choices) && prop.ui_choices.length > 0) {
      var strSel = selectOptions(name, prop.ui_choices, value, true);
      if (strSel) {
        var strSelect = ui.select({
          id: controlId,
          options: strSel.options,
          value: strSel.value,
          dataset: dataFor('string')
        });
        listen(strSelect);
        var strField = fieldAround(strSelect);
        return handle(strField.el, strSelect, strField, setSelectValue(strSelect, name, true));
      }
    }

    if (ftype === 'integer') {
      var min = (prop.minimum !== undefined && prop.minimum !== null) ? prop.minimum : null;
      if (typeof prop.exclusiveMinimum === 'number' &&
          (min === null || prop.exclusiveMinimum + 1 > min)) {
        min = prop.exclusiveMinimum + 1;
      }
      var max;
      if (!admin && marker === 'Narrow' && typeof operatorValue === 'number') {
        max = operatorValue;
      } else {
        max = (prop.maximum !== undefined && prop.maximum !== null) ? prop.maximum : null;
        if (typeof prop.exclusiveMaximum === 'number' &&
            (max === null || prop.exclusiveMaximum - 1 < max)) {
          max = prop.exclusiveMaximum - 1;
        }
      }
      var numOpts = {
        id: controlId,
        value: value !== undefined && value !== null ? value : '',
        inputMode: 'numeric',
        dataset: dataFor('integer')
      };
      if (min !== null) numOpts.min = min;
      if (max !== null) numOpts.max = max;
      if (admin) numOpts.width = 'short';
      var num = ui.textInput(numOpts);
      var numField = fieldAround(num);
      var numHandle = handle(numField.el, num, numField, function (v) {
        num.value = v === undefined || v === null ? '' : String(v);
        if (!admin) numHandle.validate();
      });
      if (!admin) {
        // Agent mode checks the number as you type; the save path asks validate() too.
        numHandle.validate = function () {
          var msg = invalidMessage(num);
          numField.setError(msg);
          return msg;
        };
        num.addEventListener('input', numHandle.validate);
      }
      listen(num);
      return numHandle;
    }

    if (ftype === 'array') {
      var locked = (!admin && marker === 'NarrowSuperset' && Array.isArray(operatorValue))
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
        inputId: controlId || ui.util.uid('ovr'),
        dataset: dataFor('array', { marker: marker || '' }),
        validate: function () { return true; },
        onChange: fire
      });
      if (!marker) chips.el.removeAttribute('data-marker');
      var chipField = fieldAround(chips.input, chips.el);
      return handle(chipField.el, chips.el, chipField, function (v) {
        chips.setValues(Array.isArray(v) ? v.map(String) : [], locked);
      }, {
        chips: chips,
        setError: function (msg) {
          chipField.setError(msg);
          chips.setError(!!msg);
        }
      });
    }

    if (ftype === 'string' && hint === 'password') {
      var secret = ui.secretInput({
        id: controlId,
        value: value !== undefined && value !== null ? String(value) : '',
        dataset: dataFor('string')
      });
      listen(secret.input);
      var secretField = fieldAround(secret.input, secret.el);
      return handle(secretField.el, secret.input, secretField, function (v) {
        secret.setValue(v);
      });
    }

    if (ftype === 'string') {
      var text = ui.textInput({
        id: controlId,
        type: 'text',
        value: value !== undefined && value !== null ? String(value) : '',
        dataset: dataFor('string')
      });
      listen(text);
      var textField = fieldAround(text);
      return handle(textField.el, text, textField, function (v) {
        text.value = v === undefined || v === null ? '' : String(v);
      });
    }

    var unknown = ui.textInput({
      id: controlId,
      type: 'text',
      value: JSON.stringify(value),
      dataset: dataFor('unknown')
    });
    listen(unknown);
    var unknownField = fieldAround(unknown);
    return handle(unknownField.el, unknown, unknownField, function (v) {
      unknown.value = JSON.stringify(v);
    });
  }

  function showIf(properties, handles) {
    properties = properties || {};
    handles = handles || {};
    var names = Object.keys(properties);
    var controllers = Object.create(null);
    function apply() {
      names.forEach(function (fname) {
        var cond = properties[fname] && properties[fname].show_if;
        var h = handles[fname];
        if (!cond || typeof cond !== 'object' || !h) return;
        var visible = true;
        Object.keys(cond).forEach(function (ctrl) {
          var ch = handles[ctrl];
          if (!ch) return;  // the controlling field is not shown: no constraint
          if (String(ch.value()) !== String(cond[ctrl])) visible = false;
        });
        h.setVisible(visible);
      });
    }
    names.forEach(function (fname) {
      var cond = properties[fname] && properties[fname].show_if;
      if (!cond || typeof cond !== 'object' || !handles[fname]) return;
      Object.keys(cond).forEach(function (ctrl) {
        if (handles[ctrl]) controllers[ctrl] = handles[ctrl];
      });
    });
    Object.keys(controllers).forEach(function (ctrl) {
      controllers[ctrl].control.addEventListener('change', apply);
    });
    apply();
    return {
      apply: apply,
      destroy: function () {
        Object.keys(controllers).forEach(function (ctrl) {
          controllers[ctrl].control.removeEventListener('change', apply);
        });
      }
    };
  }

  window.App.toolConfigFields = {
    render: render,
    showIf: showIf,
    readValue: readValue,
    invalidMessage: invalidMessage,
    seedValue: seedValue,
    allowed: allowed,
    humanValue: humanValue,
    WHOLE_NUMBER_MESSAGE: WHOLE_NUMBER_MESSAGE
  };
})();
