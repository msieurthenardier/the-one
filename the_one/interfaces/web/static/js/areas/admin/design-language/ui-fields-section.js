(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // App.ui.textInput, textarea, select and field (with hint, with error,
  // disabled). Every control is labelled through App.ui.field.
  var OPTIONS = [
    { value: 'one', label: 'Option one' },
    { value: 'two', label: 'Option two' },
    { value: 'three', label: 'Option three (disabled)', disabled: true }
  ];

  function render(host) {
    var d = App.admin.designLanguage.uiDemo;
    var ui = App.ui;

    function field(label, control, extra) {
      var opts = extra || {};
      opts.label = label;
      opts.control = control;
      return ui.field(opts).el;
    }

    d.demo(host, 'textInput', function (pane) {
      pane.appendChild(field('Text input', ui.textInput({ placeholder: 'Placeholder' })));
      pane.appendChild(field('With value', ui.textInput({ value: 'Entered text' })));
      pane.appendChild(field('Password', ui.textInput({ type: 'password', value: 'secret' })));
      pane.appendChild(field('Disabled', ui.textInput({ value: 'Not editable', disabled: true })));
    });
    d.demo(host, 'textarea', function (pane) {
      pane.appendChild(field('Textarea', ui.textarea({ rows: 3, placeholder: 'Longer text' })));
      pane.appendChild(field('Disabled textarea', ui.textarea({ rows: 2, value: 'Locked', disabled: true })));
    });
    d.demo(host, 'select', function (pane) {
      pane.appendChild(field('Select', ui.select({ options: OPTIONS, value: 'two' })));
      pane.appendChild(field('Grouped select', ui.select({
        options: [
          { label: 'Group A', options: [{ value: 'a1', label: 'A one' }] },
          { label: 'Group B', options: [{ value: 'b1', label: 'B one' }] }
        ]
      })));
      pane.appendChild(field('Disabled select', ui.select({ options: OPTIONS, disabled: true })));
    });
    d.demo(host, 'field', function (pane) {
      pane.appendChild(field('Field with hint', ui.textInput({}), { hint: 'A hint under the control.' }));
      pane.appendChild(field('Field with error', ui.textInput({ value: 'bad' }), { error: 'This value is not valid.' }));
      pane.appendChild(field('Field with hint and error', ui.textInput({}), {
        hint: 'Hint text.', error: 'Error text.'
      }));
      pane.appendChild(field('Disabled field', ui.textInput({ disabled: true }), { hint: 'Disabled.' }));
    });
  }

  window.App.admin.designLanguage.uiFieldsSection = { render: render };
})();
