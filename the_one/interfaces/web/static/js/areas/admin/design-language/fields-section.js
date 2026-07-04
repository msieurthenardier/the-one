(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // M17 F3 field vocabulary: stacked .field-group (label ABOVE the control),
  // inline validation (color + message via .is-invalid + .field-error),
  // .field-hint captions, and the self-sufficient .field-select. Rendered
  // via createElement per the innerHTML-sink freeze (M17 F1).

  // Monotonic id source so each field group's label `for` / control `id`
  // (and error `aria-describedby` / error `id`) pair uniquely within the DOM.
  var _fieldSeq = 0;
  function nextFieldId() {
    _fieldSeq += 1;
    return 'dl-field-' + _fieldSeq;
  }

  // Returns { group, label, fieldId }. The label carries `for=fieldId`; the
  // caller MUST set its control's `id` to fieldId to complete the pairing.
  // This is the documented v3 field convention (F4–F6 copy it), so the
  // gallery pattern models a correctly-associated label from the start.
  function fieldGroup(labelText) {
    var group = document.createElement('div');
    group.className = 'field-group';
    var fieldId = nextFieldId();
    var label = document.createElement('label');
    label.textContent = labelText;
    label.htmlFor = fieldId;
    group.appendChild(label);
    return { group: group, label: label, fieldId: fieldId };
  }

  function render(host) {
    // --- Stacked text input ---
    var inputField = fieldGroup('Field label (stacked)');
    var input = document.createElement('input');
    input.type = 'text';
    input.id = inputField.fieldId;
    input.className = 'field-input';
    input.placeholder = 'field-input placeholder';
    input.value = 'sample value';
    inputField.group.appendChild(input);
    host.appendChild(inputField.group);

    // --- Stacked select (.field-select — the vocabulary dropdown) ---
    var selectField = fieldGroup('Select label');
    var select = document.createElement('select');
    select.id = selectField.fieldId;
    select.className = 'field-select';
    var options = ['field-select option A', 'field-select option B', 'field-select option C'];
    for (var i = 0; i < options.length; i++) {
      var opt = document.createElement('option');
      opt.textContent = options[i];
      select.appendChild(opt);
    }
    selectField.group.appendChild(select);
    host.appendChild(selectField.group);

    // --- Stacked textarea with hint ---
    var textareaField = fieldGroup('Textarea label');
    var textarea = document.createElement('textarea');
    textarea.id = textareaField.fieldId;
    textarea.className = 'field-textarea';
    textarea.placeholder = 'field-textarea placeholder';
    textarea.rows = 3;
    textarea.value = 'sample multi-line value';
    textareaField.group.appendChild(textarea);
    var hint = document.createElement('span');
    hint.className = 'field-hint';
    hint.textContent = 'Optional hint text sits below the control.';
    textareaField.group.appendChild(hint);
    host.appendChild(textareaField.group);

    // --- Invalid state: color + message, never color alone ---
    var invalidField = fieldGroup('Invalid field');
    var invalidInput = document.createElement('input');
    invalidInput.type = 'text';
    invalidInput.id = invalidField.fieldId;
    invalidInput.className = 'field-input is-invalid';
    invalidInput.value = 'not-a-valid-value';
    invalidInput.setAttribute('aria-invalid', 'true');
    // Associate the validation message with the control so assistive tech
    // announces the error when the field takes focus.
    var errorId = invalidField.fieldId + '-error';
    invalidInput.setAttribute('aria-describedby', errorId);
    invalidField.group.appendChild(invalidInput);
    var error = document.createElement('span');
    error.className = 'field-error';
    error.id = errorId;
    error.textContent = 'Validation message explains what is wrong.';
    invalidField.group.appendChild(error);
    host.appendChild(invalidField.group);

    // --- Label with info icon ---
    var infoRow = document.createElement('div');
    infoRow.style.display = 'flex';
    infoRow.style.alignItems = 'center';
    infoRow.style.gap = '8px';
    var infoLabel = document.createElement('span');
    infoLabel.style.fontFamily = 'var(--font-family-mono)';
    infoLabel.style.fontSize = 'var(--font-size-body-sm)';
    infoLabel.textContent = 'Label with info icon';
    infoRow.appendChild(infoLabel);
    infoRow.appendChild(infoIconButton());
    host.appendChild(infoRow);

    // --- Checkboxes ---
    host.appendChild(checkboxLabel('Single .checkbox-primary (checked)', true));
    var multi = document.createElement('div');
    multi.style.display = 'flex';
    multi.style.flexDirection = 'column';
    multi.style.gap = '4px';
    multi.appendChild(checkboxLabel('Multi-select option one', true));
    multi.appendChild(checkboxLabel('Multi-select option two', false));
    multi.appendChild(checkboxLabel('Multi-select option three', true));
    host.appendChild(multi);
  }

  function infoIconButton() {
    var SVG_NS = 'http://www.w3.org/2000/svg';
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'field-info-icon';
    btn.setAttribute('aria-label', 'info');
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 16 16');
    svg.setAttribute('fill', 'currentColor');
    var circle = document.createElementNS(SVG_NS, 'circle');
    circle.setAttribute('cx', '8');
    circle.setAttribute('cy', '8');
    circle.setAttribute('r', '7');
    circle.setAttribute('fill', 'none');
    circle.setAttribute('stroke', 'currentColor');
    circle.setAttribute('stroke-width', '1.5');
    svg.appendChild(circle);
    var stem = document.createElementNS(SVG_NS, 'rect');
    stem.setAttribute('x', '7.25');
    stem.setAttribute('y', '6.5');
    stem.setAttribute('width', '1.5');
    stem.setAttribute('height', '5');
    svg.appendChild(stem);
    var dot = document.createElementNS(SVG_NS, 'rect');
    dot.setAttribute('x', '7.25');
    dot.setAttribute('y', '4');
    dot.setAttribute('width', '1.5');
    dot.setAttribute('height', '1.5');
    svg.appendChild(dot);
    btn.appendChild(svg);
    return btn;
  }

  function checkboxLabel(text, checked) {
    var label = document.createElement('label');
    label.style.display = 'flex';
    label.style.alignItems = 'center';
    label.style.gap = '8px';
    label.style.fontSize = 'var(--font-size-body-sm)';
    var box = document.createElement('input');
    box.type = 'checkbox';
    box.className = 'checkbox-primary';
    box.checked = !!checked;
    label.appendChild(box);
    var span = document.createElement('span');
    span.textContent = text;
    label.appendChild(span);
    return label;
  }

  window.App.admin.designLanguage.fieldsSection = { render: render };
})();
