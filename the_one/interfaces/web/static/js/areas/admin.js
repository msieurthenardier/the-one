App.registerArea({
  id: 'admin',
  label: 'Admin',
  icon: '\u2699\uFE0F',
  order: 30,

  init: function (sidebar, content) {
    var categories = [
      { id: 'general', label: 'General', active: true },
      { id: 'providers', label: 'LLM Providers', active: true },
      { id: 'system', label: 'System', active: true }
    ];
    var currentCategory = 'general';
    var categoryListEl;
    var contentEl;

    // Providers state
    var providers = [];
    var editingProvider = null; // null = list view, 'new' = add form, id = edit form
    var providerModels = []; // models fetched for a provider

    // Settings grouped into sections
    var settingSections = [
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
      data_dir: 'Data Directory',
      workspace_dir: 'Workspace Directory',
      host: 'Host',
      port: 'Port',
      concourse_target: 'Target',
      concourse_pipeline: 'Pipeline'
    };

    // Provider type defaults
    var PROVIDER_DEFAULTS = {
      'ollama': { base_url: 'http://localhost:11434/v1', needs_key: false },
      'openai-compatible': { base_url: '', needs_key: false },
      'openai': { base_url: 'https://api.openai.com/v1', needs_key: true },
      'anthropic': { base_url: 'https://api.anthropic.com', needs_key: true }
    };

    var TYPE_BADGES = {
      'ollama': { label: 'Ollama', color: '#4ecdc4' },
      'openai-compatible': { label: 'OpenAI-Compatible', color: '#f39c12' },
      'openai': { label: 'OpenAI', color: '#10a37f' },
      'anthropic': { label: 'Anthropic', color: '#d4a574' }
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
      } else if (currentCategory === 'providers') {
        renderProvidersPanel();
      } else if (currentCategory === 'system') {
        renderSystemPanel();
      } else {
        var cat = null;
        for (var i = 0; i < categories.length; i++) {
          if (categories[i].id === currentCategory) { cat = categories[i]; break; }
        }
        renderPlaceholder(cat ? cat.label : currentCategory);
      }
    }

    // ── General Panel ─────────────────────────────────────────────────

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

    // ── Providers Panel ───────────────────────────────────────────────

    function renderProvidersPanel() {
      contentEl.innerHTML =
        '<div class="admin-header">' +
          '<span class="admin-title">LLM Providers</span>' +
          '<button class="admin-add-btn">+ Add Provider</button>' +
        '</div>' +
        '<div class="admin-providers-content">' +
          '<div class="admin-loading">Loading providers\u2026</div>' +
        '</div>' +
        '<div class="admin-flash" role="status" aria-live="polite"></div>';

      contentEl.querySelector('.admin-add-btn').onclick = function () {
        editingProvider = 'new';
        providerModels = [];
        renderProviderForm(null);
      };

      fetchProviders();
    }

    function fetchProviders() {
      fetch('/api/providers')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          providers = data;
          if (editingProvider && editingProvider !== 'new') {
            // Find the provider being edited
            var found = null;
            for (var i = 0; i < providers.length; i++) {
              if (providers[i].id === editingProvider) { found = providers[i]; break; }
            }
            if (found) {
              renderProviderForm(found);
            } else {
              editingProvider = null;
              renderProviderList();
            }
          } else if (editingProvider === 'new') {
            renderProviderForm(null);
          } else {
            renderProviderList();
          }
        })
        .catch(function () {});
    }

    function renderProviderList() {
      var wrap = contentEl.querySelector('.admin-providers-content');
      if (!wrap) return;

      if (providers.length === 0) {
        wrap.innerHTML =
          '<div class="admin-placeholder">' +
            '<div class="admin-placeholder-title">No providers configured</div>' +
            '<div class="admin-placeholder-text">Click "+ Add Provider" to get started.</div>' +
          '</div>';
        return;
      }

      var html = '<div class="admin-provider-list" role="list">';
      for (var i = 0; i < providers.length; i++) {
        var p = providers[i];
        var badge = TYPE_BADGES[p.type] || { label: p.type, color: '#888' };
        html += '<div class="admin-provider-card" role="listitem" data-id="' + escapeAttr(p.id) + '">';
        html += '<div class="admin-provider-info">';
        html += '<span class="admin-provider-name">' + escapeHtml(p.name) + '</span>';
        html += '<span class="admin-provider-badge" style="background:' + badge.color + '">' + escapeHtml(badge.label) + '</span>';
        html += '</div>';
        html += '<div class="admin-provider-actions">';
        html += '<button class="admin-provider-edit-btn" data-id="' + escapeAttr(p.id) + '">Edit</button>';
        html += '<button class="admin-provider-delete-btn" data-id="' + escapeAttr(p.id) + '">Delete</button>';
        html += '</div>';
        html += '</div>';
      }
      html += '</div>';
      wrap.innerHTML = html;

      // Wire edit buttons
      var editBtns = wrap.querySelectorAll('.admin-provider-edit-btn');
      for (var e = 0; e < editBtns.length; e++) {
        editBtns[e].addEventListener('click', function (ev) {
          var id = ev.target.dataset.id;
          editingProvider = id;
          var found = null;
          for (var j = 0; j < providers.length; j++) {
            if (providers[j].id === id) { found = providers[j]; break; }
          }
          providerModels = [];
          renderProviderForm(found);
        });
      }

      // Wire delete buttons
      var delBtns = wrap.querySelectorAll('.admin-provider-delete-btn');
      for (var d = 0; d < delBtns.length; d++) {
        delBtns[d].addEventListener('click', function (ev) {
          var id = ev.target.dataset.id;
          deleteProvider(id, ev.target);
        });
      }
    }

    function deleteProvider(id, btn) {
      if (btn.classList.contains('confirm')) {
        fetch('/api/providers/' + encodeURIComponent(id), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) throw new Error('Delete failed');
            showAdminFlash('Provider deleted');
            editingProvider = null;
            fetchProviders();
          })
          .catch(function (err) { showAdminFlash(err.message, true); });
        return;
      }

      // Check agent usage first
      fetch('/api/agents')
        .then(function (r) { return r.json(); })
        .then(function (agents) {
          var count = 0;
          for (var i = 0; i < agents.length; i++) {
            if (agents[i].provider_config_id === id) count++;
          }

          btn.classList.add('confirm');
          var original = btn.textContent;
          if (count > 0) {
            btn.textContent = count + ' agent' + (count > 1 ? 's' : '') + ' use this \u2014 Confirm?';
          } else {
            btn.textContent = 'Confirm delete?';
          }
          setTimeout(function () {
            btn.classList.remove('confirm');
            btn.textContent = original;
          }, 4000);
        });
    }

    // ── Provider Form ─────────────────────────────────────────────────

    function renderProviderForm(provider) {
      var wrap = contentEl.querySelector('.admin-providers-content');
      if (!wrap) return;

      var isNew = !provider;
      var type = provider ? provider.type : 'ollama';
      var name = provider ? provider.name : '';
      var base_url = provider ? provider.base_url : PROVIDER_DEFAULTS[type].base_url;
      var api_key = provider ? (provider.api_key || '') : '';

      var html = '<div class="admin-provider-form">';
      html += '<div class="admin-provider-form-header">';
      html += '<span class="admin-provider-form-title">' + (isNew ? 'Add Provider' : 'Edit Provider') + '</span>';
      html += '<button class="admin-provider-back-btn">\u2190 Back</button>';
      html += '</div>';

      // Name
      html += '<div class="admin-pf-row">';
      html += '<label for="pf-name">Name</label>';
      html += '<input id="pf-name" class="admin-pf-input" data-field="name" value="' + escapeAttr(name) + '" placeholder="My Provider" />';
      html += '</div>';

      // Type
      html += '<div class="admin-pf-row">';
      html += '<label for="pf-type">Type</label>';
      html += '<select id="pf-type" class="admin-pf-input admin-pf-select" data-field="type">';
      var types = ['ollama', 'openai-compatible', 'openai', 'anthropic'];
      for (var t = 0; t < types.length; t++) {
        var sel = types[t] === type ? ' selected' : '';
        var lbl = TYPE_BADGES[types[t]] ? TYPE_BADGES[types[t]].label : types[t];
        html += '<option value="' + types[t] + '"' + sel + '>' + escapeHtml(lbl) + '</option>';
      }
      html += '</select>';
      html += '</div>';

      // Type-specific fields container
      html += '<div class="admin-pf-type-fields">';
      html += renderTypeFields(type, base_url, api_key);
      html += '</div>';

      // Actions
      html += '<div class="admin-pf-actions">';
      html += '<span class="admin-pf-error"></span>';
      html += '<button class="admin-pf-save-btn">' + (isNew ? 'Create' : 'Save') + '</button>';
      html += '</div>';

      // Test + Models section (only for existing providers)
      if (!isNew) {
        html += '<div class="admin-pf-section">';
        html += '<div class="admin-pf-section-title">Connection</div>';
        html += '<div class="admin-pf-test-row">';
        html += '<button class="admin-pf-test-btn">Test Connection</button>';
        html += '<button class="admin-pf-refresh-btn">Refresh Models</button>';
        html += '<span class="admin-pf-test-result" aria-live="polite"></span>';
        html += '</div>';

        // Models list
        html += '<div class="admin-pf-models" aria-live="polite">';
        if (providerModels.length > 0) {
          html += renderModelsList(providerModels);
        }
        html += '</div>';
        html += '</div>';
      }

      html += '</div>';
      wrap.innerHTML = html;

      // Wire events
      wireProviderFormEvents(isNew, provider);

      // Auto-fetch models when editing an existing provider
      if (!isNew && provider.id) {
        fetchModels(provider.id);
      }
    }

    function renderTypeFields(type, base_url, api_key) {
      var defaults = PROVIDER_DEFAULTS[type] || {};
      var html = '';

      // Base URL field — show for ollama and openai-compatible
      if (type === 'ollama' || type === 'openai-compatible') {
        html += '<div class="admin-pf-row">';
        html += '<label for="pf-base-url">Base URL</label>';
        html += '<input id="pf-base-url" class="admin-pf-input" data-field="base_url" value="' + escapeAttr(base_url || defaults.base_url || '') + '" placeholder="' + escapeAttr(defaults.base_url || 'http://...') + '" />';
        html += '</div>';
      }

      // API key field — show for openai-compatible, openai, anthropic
      if (type !== 'ollama') {
        var keyRequired = type === 'openai' || type === 'anthropic';
        html += '<div class="admin-pf-row">';
        html += '<label for="pf-api-key">API Key' + (keyRequired ? '' : ' (optional)') + '</label>';
        html += '<div class="admin-pf-key-wrap">';
        html += '<input id="pf-api-key" class="admin-pf-input admin-pf-key" data-field="api_key" type="password" value="' + escapeAttr(api_key) + '" placeholder="sk-..." />';
        html += '<button class="admin-pf-key-toggle" type="button" aria-label="Toggle API key visibility">Show</button>';
        html += '</div>';
        html += '</div>';
      }

      return html;
    }

    function renderModelsList(models) {
      if (models.length === 0) return '<div class="admin-pf-models-empty">No models found</div>';
      var html = '<div class="admin-pf-models-title">Available Models (' + models.length + ')</div>';
      html += '<div class="admin-pf-models-list">';
      for (var i = 0; i < models.length; i++) {
        html += '<div class="admin-pf-model-item">' + escapeHtml(models[i].name || models[i].id) + '</div>';
      }
      html += '</div>';
      return html;
    }

    function wireProviderFormEvents(isNew, provider) {
      // Back button
      var backBtn = contentEl.querySelector('.admin-provider-back-btn');
      if (backBtn) {
        backBtn.onclick = function () {
          editingProvider = null;
          providerModels = [];
          renderProviderList();
        };
      }

      // Type change — update fields
      var typeSelect = contentEl.querySelector('[data-field="type"]');
      if (typeSelect) {
        typeSelect.onchange = function () {
          var newType = typeSelect.value;
          var fieldsWrap = contentEl.querySelector('.admin-pf-type-fields');
          if (fieldsWrap) {
            var defaults = PROVIDER_DEFAULTS[newType] || {};
            fieldsWrap.innerHTML = renderTypeFields(newType, defaults.base_url || '', '');
            wireKeyToggle();
          }
        };
      }

      // Key toggle
      wireKeyToggle();

      // Save
      var saveBtn = contentEl.querySelector('.admin-pf-save-btn');
      if (saveBtn) {
        saveBtn.onclick = function () { saveProvider(isNew, provider); };
      }

      // Test connection
      var testBtn = contentEl.querySelector('.admin-pf-test-btn');
      if (testBtn) {
        testBtn.onclick = function () { testProviderConnection(provider.id); };
      }

      // Refresh models
      var refreshBtn = contentEl.querySelector('.admin-pf-refresh-btn');
      if (refreshBtn) {
        refreshBtn.onclick = function () { fetchModels(provider.id); };
      }
    }

    function wireKeyToggle() {
      var toggleBtn = contentEl.querySelector('.admin-pf-key-toggle');
      if (toggleBtn) {
        toggleBtn.onclick = function () {
          var keyInput = contentEl.querySelector('.admin-pf-key');
          if (keyInput) {
            if (keyInput.type === 'password') {
              keyInput.type = 'text';
              toggleBtn.textContent = 'Hide';
            } else {
              keyInput.type = 'password';
              toggleBtn.textContent = 'Show';
            }
          }
        };
      }
    }

    function collectProviderFormData() {
      var data = {};
      var nameInput = contentEl.querySelector('[data-field="name"]');
      var typeInput = contentEl.querySelector('[data-field="type"]');
      var baseUrlInput = contentEl.querySelector('[data-field="base_url"]');
      var apiKeyInput = contentEl.querySelector('[data-field="api_key"]');

      data.name = nameInput ? nameInput.value.trim() : '';
      data.type = typeInput ? typeInput.value : 'ollama';

      // Always send base_url
      var type = data.type;
      if (baseUrlInput) {
        data.base_url = baseUrlInput.value.trim() || PROVIDER_DEFAULTS[type].base_url;
      } else {
        // For openai/anthropic, use the default base_url
        data.base_url = PROVIDER_DEFAULTS[type].base_url;
      }

      if (apiKeyInput) {
        data.api_key = apiKeyInput.value;
      }

      return data;
    }

    function saveProvider(isNew, provider) {
      var data = collectProviderFormData();
      var errorEl = contentEl.querySelector('.admin-pf-error');

      if (!data.name) {
        if (errorEl) errorEl.textContent = 'Name is required.';
        return;
      }
      if (!data.base_url) {
        if (errorEl) errorEl.textContent = 'Base URL is required.';
        return;
      }

      var url, method;
      if (isNew) {
        url = '/api/providers';
        method = 'POST';
      } else {
        url = '/api/providers/' + encodeURIComponent(provider.id);
        method = 'PUT';
      }

      fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Save failed'); });
          return r.json();
        })
        .then(function (saved) {
          showAdminFlash(isNew ? 'Provider created' : 'Provider saved');
          editingProvider = saved.id;
          providerModels = [];
          fetchProviders();
        })
        .catch(function (err) {
          if (errorEl) errorEl.textContent = err.message;
        });
    }

    function testProviderConnection(providerId) {
      var resultEl = contentEl.querySelector('.admin-pf-test-result');
      var testBtn = contentEl.querySelector('.admin-pf-test-btn');
      if (resultEl) resultEl.textContent = 'Testing\u2026';
      if (testBtn) testBtn.disabled = true;

      fetch('/api/providers/' + encodeURIComponent(providerId) + '/test', { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (testBtn) testBtn.disabled = false;
          if (resultEl) {
            if (data.status === 'ok') {
              resultEl.textContent = '\u2713 ' + (data.detail || 'Connected');
              resultEl.className = 'admin-pf-test-result success';
              // Auto-fetch models on success
              fetchModels(providerId);
            } else {
              resultEl.textContent = '\u2717 ' + (data.detail || 'Failed');
              resultEl.className = 'admin-pf-test-result error';
            }
          }
        })
        .catch(function () {
          if (testBtn) testBtn.disabled = false;
          if (resultEl) {
            resultEl.textContent = '\u2717 Request failed';
            resultEl.className = 'admin-pf-test-result error';
          }
        });
    }

    function fetchModels(providerId) {
      var modelsEl = contentEl.querySelector('.admin-pf-models');
      if (modelsEl) modelsEl.innerHTML = '<div class="admin-loading">Loading models\u2026</div>';

      fetch('/api/providers/' + encodeURIComponent(providerId) + '/models')
        .then(function (r) {
          if (!r.ok) throw new Error('Failed to fetch models');
          return r.json();
        })
        .then(function (models) {
          providerModels = models;
          if (modelsEl) modelsEl.innerHTML = renderModelsList(models);
        })
        .catch(function (err) {
          if (modelsEl) modelsEl.innerHTML = '<div class="admin-pf-models-empty">' + escapeHtml(err.message) + '</div>';
        });
    }

    // ── System Panel ──────────────────────────────────────────────────

    function renderSystemPanel() {
      contentEl.innerHTML =
        '<div class="admin-header">' +
          '<span class="admin-title">System</span>' +
        '</div>' +
        '<div class="admin-form">' +
          '<div class="admin-section">' +
            '<div class="admin-section-title">Encryption</div>' +
            '<div class="admin-note">' +
              'Rotating the encryption key will re-encrypt all stored API keys with a new key. ' +
              'This is a security maintenance operation. The old key will be replaced.' +
            '</div>' +
            '<div class="admin-system-row">' +
              '<button class="admin-rotate-btn">Rotate Encryption Key</button>' +
              '<span class="admin-rotate-result" role="status" aria-live="polite"></span>' +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="admin-flash" role="status" aria-live="polite"></div>';

      var rotateBtn = contentEl.querySelector('.admin-rotate-btn');
      rotateBtn.onclick = function () {
        if (rotateBtn.classList.contains('confirm')) {
          rotateBtn.disabled = true;
          rotateBtn.textContent = 'Rotating\u2026';
          var resultEl = contentEl.querySelector('.admin-rotate-result');

          fetch('/api/encryption/rotate', { method: 'POST' })
            .then(function (r) {
              if (!r.ok) throw new Error('Rotation failed');
              return r.json();
            })
            .then(function () {
              rotateBtn.disabled = false;
              rotateBtn.classList.remove('confirm');
              rotateBtn.textContent = 'Rotate Encryption Key';
              if (resultEl) {
                resultEl.textContent = '\u2713 Key rotated successfully';
                resultEl.className = 'admin-rotate-result success';
              }
              showAdminFlash('Encryption key rotated');
            })
            .catch(function (err) {
              rotateBtn.disabled = false;
              rotateBtn.classList.remove('confirm');
              rotateBtn.textContent = 'Rotate Encryption Key';
              if (resultEl) {
                resultEl.textContent = '\u2717 ' + err.message;
                resultEl.className = 'admin-rotate-result error';
              }
            });
          return;
        }

        rotateBtn.classList.add('confirm');
        rotateBtn.textContent = 'Click again to confirm rotation';
        setTimeout(function () {
          rotateBtn.classList.remove('confirm');
          rotateBtn.textContent = 'Rotate Encryption Key';
        }, 4000);
      };
    }

    // ── Flash ─────────────────────────────────────────────────────────

    function showAdminFlash(msg, isError) {
      var el = contentEl.querySelector('.admin-flash');
      if (!el) {
        el = document.createElement('div');
        el.className = 'admin-flash';
        el.setAttribute('role', 'status');
        el.setAttribute('aria-live', 'polite');
        contentEl.appendChild(el);
      }
      el.textContent = msg;
      el.classList.toggle('error', !!isError);
      el.classList.add('visible');
      setTimeout(function () {
        el.classList.remove('visible');
      }, 3000);
    }

    // ── Placeholder ───────────────────────────────────────────────────

    function renderPlaceholder(name) {
      contentEl.innerHTML =
        '<div class="admin-placeholder">' +
          '<div class="admin-placeholder-title">' + escapeHtml(name) + '</div>' +
          '<div class="admin-placeholder-text">Coming soon</div>' +
        '</div>';
    }

    // ── Helpers ───────────────────────────────────────────────────────

    var escapeHtml = App.escapeHtml;

    function escapeAttr(s) {
      if (!s) return '';
      return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // Store reference for activate() to reuse
    var self = this;
    self._refreshGeneral = function () {
      if (currentCategory === 'general') {
        fetchSettings();
      } else if (currentCategory === 'providers') {
        fetchProviders();
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
