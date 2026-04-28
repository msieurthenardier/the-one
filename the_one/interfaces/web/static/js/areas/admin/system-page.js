(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Combined System page — Environment (read-only env-var-derived rows) +
  // Appearance (theme toggle) + Encryption (rotate flow). Replaces the
  // previously-separate General + System pages (F6 leg 01).

  var SETTING_SECTIONS = [
    { title: 'Paths', fields: ['data_dir', 'workspace_dir'] },
    { title: 'Server', fields: ['host', 'port'] },
    { title: 'Concourse CI', fields: ['concourse_target', 'concourse_pipeline'] }
  ];

  var FIELD_LABELS = {
    data_dir: 'Data Directory',
    workspace_dir: 'Workspace Directory',
    host: 'Host',
    port: 'Port',
    concourse_target: 'Target',
    concourse_pipeline: 'Pipeline'
  };

  function renderSystemPage(container) {
    container.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">System</h1>' +
      '</div>' +
      '<div class="admin-form">' +
        '<div class="admin-system-section">' +
          '<div class="section-title admin-section-title">Environment</div>' +
          '<div class="admin-note">' +
            'Environment settings are configured via environment variables. ' +
            'Restart the server after changing values.' +
          '</div>' +
          '<div class="admin-environment-rows"><div class="admin-loading">Loading settings…</div></div>' +
        '</div>' +
        '<div class="admin-system-section">' +
          '<div class="section-title admin-section-title" id="admin-appearance-heading">Appearance</div>' +
          '<p class="admin-system-text">' +
            'Choose a theme. Auto follows your operating system preference.' +
          '</p>' +
          '<div class="admin-theme-toggle" id="admin-theme-toggle-mount" aria-labelledby="admin-appearance-heading"></div>' +
        '</div>' +
        '<div class="admin-system-section">' +
          '<div class="section-title admin-section-title">Encryption</div>' +
          '<p class="admin-system-text">' +
            'API keys for LLM providers are encrypted at rest. ' +
            'You can rotate the encryption key to re-encrypt all stored credentials with a new key.' +
          '</p>' +
          '<div class="admin-system-warning" role="note">' +
            'Rotating the encryption key re-encrypts all stored API credentials with a new key. This is irreversible.' +
          '</div>' +
          '<button class="btn-muted-destructive" data-testid="rotate-key-btn" type="button"><span data-confirm-title>Rotate Encryption Key</span></button>' +
          '<div class="admin-system-flash" aria-live="polite"></div>' +
        '</div>' +
      '</div>';

    fetchSettings(container);
    mountThemeToggle(container);
    wireEncryptionRotate(container);
  }

  function fetchSettings(container) {
    fetch('/api/settings')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var rowsEl = container.querySelector('.admin-environment-rows');
        if (!rowsEl) return;
        var html = '';
        for (var s = 0; s < SETTING_SECTIONS.length; s++) {
          var section = SETTING_SECTIONS[s];
          html += '<div class="admin-environment-subsection">';
          html += '<div class="admin-environment-subtitle">' + window.App.escapeHtml(section.title) + '</div>';
          for (var f = 0; f < section.fields.length; f++) {
            var field = section.fields[f];
            var label = FIELD_LABELS[field] || field;
            var value = data[field];
            var envVar = 'THE_ONE_' + field.toUpperCase();
            html += settingRow(label, value, envVar);
          }
          html += '</div>';
        }
        rowsEl.innerHTML = html;
      })
      .catch(function () { /* loading message stays */ });
  }

  function settingRow(label, value, envVar) {
    var escapeHtml = window.App.escapeHtml;
    var displayValue;
    if (value === null || value === undefined || value === '') {
      displayValue = '<span class="admin-field-not-set">not set</span>';
    } else {
      displayValue = escapeHtml(String(value));
    }
    return '<div class="admin-field-row">' +
      '<div class="admin-field-label">' + escapeHtml(label) + '</div>' +
      '<div class="admin-field-value">' + displayValue + '</div>' +
      '<div class="admin-field-env">' + escapeHtml(envVar) + '</div>' +
    '</div>';
  }

  function mountThemeToggle(container) {
    var themeToggleEl = container.querySelector('#admin-theme-toggle-mount');
    if (window.App && window.App.theme && window.App.theme.renderToggle) {
      window.App.theme.renderToggle(themeToggleEl, { labelledBy: 'admin-appearance-heading' });
    }
  }

  function wireEncryptionRotate(container) {
    var rotateBtn = container.querySelector('[data-testid="rotate-key-btn"]');
    var flashEl = container.querySelector('.admin-system-flash');
    rotateBtn.addEventListener('click', function () {
      window.App.confirmDelete(rotateBtn, function (btn, revertFn) {
        var titleEl = btn.querySelector('[data-confirm-title]');
        btn.disabled = true;
        if (titleEl) titleEl.textContent = 'Rotating…';
        fetch('/api/encryption/rotate', { method: 'POST' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Rotation failed'); });
            return r.json();
          })
          .then(function () {
            btn.disabled = false;
            // Helper's revertFn restores the original "Rotate Encryption Key"
            // text + removes the .confirm-delete class.
            revertFn();
            flashEl.textContent = 'Encryption key rotated successfully.';
            flashEl.className = 'admin-system-flash success';
            setTimeout(function () { flashEl.textContent = ''; flashEl.className = 'admin-system-flash'; }, 3000);
          })
          .catch(function (err) {
            btn.disabled = false;
            revertFn();
            flashEl.textContent = 'Error: ' + err.message;
            flashEl.className = 'admin-system-flash error';
            setTimeout(function () { flashEl.textContent = ''; flashEl.className = 'admin-system-flash'; }, 4000);
          });
      }, { confirmLabel: 'Confirm Rotate?' });
    });
  }

  window.App.admin.renderSystemPage = renderSystemPage;
})();
