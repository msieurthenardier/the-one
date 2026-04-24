App.registerArea({
  id: 'admin',
  label: 'Admin',
  icon: '\u2699\uFE0F',
  order: 30,

  init: function (sidebar, content) {
    var categories = [
      { id: 'general', label: 'General', active: true },
      { id: 'agents', label: 'Agents', active: false },
      { id: 'integrations', label: 'Integrations', active: false },
      { id: 'system', label: 'System', active: false }
    ];
    var currentCategory = 'general';
    var categoryListEl;
    var contentEl;

    // Settings grouped into sections
    var settingSections = [
      {
        title: 'LLM Configuration',
        fields: ['llm_provider', 'llm_model', 'llm_base_url']
      },
      {
        title: 'Paths',
        fields: ['data_dir', 'workspace_dir']
      },
      {
        title: 'Server',
        fields: ['host', 'port']
      },
      {
        title: 'Concourse CI',
        fields: ['concourse_target', 'concourse_pipeline']
      }
    ];

    var fieldLabels = {
      llm_provider: 'Provider',
      llm_model: 'Model',
      llm_base_url: 'Base URL',
      data_dir: 'Data Directory',
      workspace_dir: 'Workspace Directory',
      host: 'Host',
      port: 'Port',
      concourse_target: 'Target',
      concourse_pipeline: 'Pipeline'
    };

    // Build sidebar
    sidebar.innerHTML =
      '<div class="admin-sidebar-header">' +
        '<span class="title">Administration</span>' +
      '</div>' +
      '<div class="admin-category-list"></div>';

    categoryListEl = sidebar.querySelector('.admin-category-list');

    // Build content
    content.innerHTML = '<div class="admin-content"></div>';
    contentEl = content.querySelector('.admin-content');

    // ── Rendering ─────────────────────────────────────────────────────

    function renderCategoryList() {
      categoryListEl.innerHTML = '';
      for (var i = 0; i < categories.length; i++) {
        (function (cat) {
          var el = document.createElement('div');
          el.className = 'admin-category-item' + (currentCategory === cat.id ? ' active' : '');

          var nameSpan = document.createElement('span');
          nameSpan.className = 'admin-category-name';
          nameSpan.textContent = cat.label;
          el.appendChild(nameSpan);

          if (!cat.active) {
            var badge = document.createElement('span');
            badge.className = 'admin-category-badge';
            badge.textContent = 'Soon';
            el.appendChild(badge);
          }

          el.onclick = function () {
            currentCategory = cat.id;
            renderCategoryList();
            renderContent();
          };
          categoryListEl.appendChild(el);
        })(categories[i]);
      }
    }

    function renderContent() {
      if (currentCategory === 'general') {
        renderGeneralPanel();
      } else {
        var cat = null;
        for (var i = 0; i < categories.length; i++) {
          if (categories[i].id === currentCategory) { cat = categories[i]; break; }
        }
        renderPlaceholder(cat ? cat.label : currentCategory);
      }
    }

    function renderGeneralPanel() {
      contentEl.innerHTML =
        '<div class="admin-header">' +
          '<span class="admin-title">General Settings</span>' +
        '</div>' +
        '<div class="admin-form">' +
          '<div class="admin-loading">Loading settings\u2026</div>' +
        '</div>';

      fetchSettings();
    }

    function fetchSettings() {
      fetch('/api/settings')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var formEl = contentEl.querySelector('.admin-form');
          if (!formEl) return;

          var html =
            '<div class="admin-note">' +
              'Settings are configured via environment variables. ' +
              'Restart the server after changing values.' +
            '</div>';

          for (var s = 0; s < settingSections.length; s++) {
            var section = settingSections[s];
            html += '<div class="admin-section">';
            html += '<div class="admin-section-title">' + escapeHtml(section.title) + '</div>';
            for (var f = 0; f < section.fields.length; f++) {
              var field = section.fields[f];
              var label = fieldLabels[field] || field;
              var value = data[field];
              var envVar = 'THE_ONE_' + field.toUpperCase();
              html += settingRow(label, value, envVar);
            }
            html += '</div>';
          }

          formEl.innerHTML = html;
        })
        .catch(function () {
          // On failure, loading message stays — no crash
        });
    }

    function settingRow(label, value, envVar) {
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

    function renderPlaceholder(name) {
      contentEl.innerHTML =
        '<div class="admin-placeholder">' +
          '<div class="admin-placeholder-title">' + escapeHtml(name) + '</div>' +
          '<div class="admin-placeholder-text">Coming soon</div>' +
        '</div>';
    }

    var escapeHtml = App.escapeHtml;

    // Store reference for activate() to reuse
    var self = this;
    self._refreshGeneral = function () {
      if (currentCategory === 'general') {
        fetchSettings();
      }
    };

    // ── Init ──────────────────────────────────────────────────────────

    renderCategoryList();
    renderContent();
  },

  activate: function () {
    if (this._refreshGeneral) {
      this._refreshGeneral();
    }
  },

  deactivate: function () {}
});
