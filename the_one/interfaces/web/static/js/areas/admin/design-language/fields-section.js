(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  function render(host) {
    host.innerHTML =
      '<input type="text" class="field-input" placeholder="field-input placeholder" value="sample value" />' +
      '<textarea class="field-textarea" placeholder="field-textarea placeholder" rows="3">sample multi-line value</textarea>' +
      '<select class="field-input field-select">' +
        '<option>field-select option A</option>' +
        '<option>field-select option B</option>' +
        '<option>field-select option C</option>' +
      '</select>' +
      '<div style="display: flex; align-items: center; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-body-sm);">Label with info icon</span>' +
        '<button type="button" class="field-info-icon" aria-label="info">' +
          '<svg viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg">' +
            '<circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.5"/>' +
            '<rect x="7.25" y="6.5" width="1.5" height="5" fill="currentColor"/>' +
            '<rect x="7.25" y="4" width="1.5" height="1.5" fill="currentColor"/>' +
          '</svg>' +
        '</button>' +
      '</div>' +
      '<label style="display: flex; align-items: center; gap: 8px; font-size: var(--font-size-body-sm);">' +
        '<input type="checkbox" class="checkbox-primary" checked />' +
        '<span>Single .checkbox-primary (checked)</span>' +
      '</label>' +
      '<div style="display: flex; flex-direction: column; gap: 4px;">' +
        '<label style="display: flex; align-items: center; gap: 8px; font-size: var(--font-size-body-sm);">' +
          '<input type="checkbox" class="checkbox-primary" checked />' +
          '<span>Multi-select option one</span>' +
        '</label>' +
        '<label style="display: flex; align-items: center; gap: 8px; font-size: var(--font-size-body-sm);">' +
          '<input type="checkbox" class="checkbox-primary" />' +
          '<span>Multi-select option two</span>' +
        '</label>' +
        '<label style="display: flex; align-items: center; gap: 8px; font-size: var(--font-size-body-sm);">' +
          '<input type="checkbox" class="checkbox-primary" checked />' +
          '<span>Multi-select option three</span>' +
        '</label>' +
      '</div>';
  }

  window.App.admin.designLanguage.fieldsSection = { render: render };
})();
