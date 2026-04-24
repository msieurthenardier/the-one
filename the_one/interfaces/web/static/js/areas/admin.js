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

    // Provider state
    var providers = [];
    var providerFormMode = null; // null | 'add' | 'edit'
    var editingProvider = null;

    var PROVIDER_TYPES = [
      { value: 'ollama', label: 'Ollama' },
      { value: 'openai-compatible', label: 'OpenAI-Compatible' },
      { value: 'openai', label: 'OpenAI' },
      { value: 'anthropic', label: 'Anthropic' }
    ];

    var TYPE_DEFAULTS = {
      'ollama': { base_url: 'http://localhost:11434/v1', showBaseUrl: true, showApiKey: false },
      'openai-compatible': { base_url: '', showBaseUrl: true, showApiKey: true },
      'openai': { base_url: 'https://api.openai.com/v1', showBaseUrl: false, showApiKey: true },
      'anthropic': { base_url: 'https://api.anthropic.com', showBaseUrl: false, showApiKey: true }
    };

    var TYPE_BADGE_COLORS = {
      'ollama': '#2ecc71',
      'openai-compatible': '#d4a800',
      'openai': '#4a9eff',
      'anthropic': '#9b59b6'
    };

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
            providerFormMode = null;
            editingProvider = null;
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

    // ── System Panel ──────────────────────────────────────────────────

    var rotateConfirmTimer = null;

    function renderSystemPanel() {
      contentEl.innerHTML =
        '<div class="admin-header">' +
          '<span class="admin-title">System</span>' +
        '</div>' +
        '<div class="admin-form">' +
          '<div class="admin-system-section">' +
            '<div class="admin-section-title">Encryption</div>' +
            '<p class="admin-system-text">' +
              'API keys for LLM providers are encrypted at rest. ' +
              'You can rotate the encryption key to re-encrypt all stored credentials with a new key.' +
            '</p>' +
            '<div class="admin-system-warning" role="note">' +
              'Rotating the encryption key re-encrypts all stored API credentials with a new key. This is irreversible.' +
            '</div>' +
            '<button class="admin-system-btn" type="button">Rotate Encryption Key</button>' +
            '<div class="admin-system-flash" aria-live="polite"></div>' +
          '</div>' +
        '</div>';

      var rotateBtn = contentEl.querySelector('.admin-system-btn');
      var flashEl = contentEl.querySelector('.admin-system-flash');

      rotateBtn.addEventListener('click', function () {
        if (rotateBtn.classList.contains('admin-system-btn-confirm')) {
          // Second click — actually rotate
          rotateBtn.disabled = true;
          rotateBtn.textContent = 'Rotating\u2026';

          fetch('/api/encryption/rotate', { method: 'POST' })
            .then(function (r) {
              if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Rotation failed'); });
              return r.json();
            })
            .then(function () {
              rotateBtn.disabled = false;
              rotateBtn.classList.remove('admin-system-btn-confirm');
              rotateBtn.textContent = 'Rotate Encryption Key';
              if (rotateConfirmTimer) { clearTimeout(rotateConfirmTimer); rotateConfirmTimer = null; }
              flashEl.textContent = 'Encryption key rotated successfully.';
              flashEl.className = 'admin-system-flash success';
              setTimeout(function () { flashEl.textContent = ''; flashEl.className = 'admin-system-flash'; }, 3000);
            })
            .catch(function (err) {
              rotateBtn.disabled = false;
              rotateBtn.classList.remove('admin-system-btn-confirm');
              rotateBtn.textContent = 'Rotate Encryption Key';
              if (rotateConfirmTimer) { clearTimeout(rotateConfirmTimer); rotateConfirmTimer = null; }
              flashEl.textContent = 'Error: ' + err.message;
              flashEl.className = 'admin-system-flash error';
              setTimeout(function () { flashEl.textContent = ''; flashEl.className = 'admin-system-flash'; }, 4000);
            });
          return;
        }

        // First click — show confirmation
        rotateBtn.classList.add('admin-system-btn-confirm');
        rotateBtn.textContent = 'Click again to confirm rotation';

        if (rotateConfirmTimer) clearTimeout(rotateConfirmTimer);
        rotateConfirmTimer = setTimeout(function () {
          rotateBtn.classList.remove('admin-system-btn-confirm');
          rotateBtn.textContent = 'Rotate Encryption Key';
        }, 4000);
      });
    }

    // ── Providers Panel ───────────────────────────────────────────────

    function renderProvidersPanel() {
      if (providerFormMode) {
        renderProviderForm(editingProvider);
        return;
      }

      contentEl.innerHTML =
        '<div class="admin-header">' +
          '<span class="admin-title">LLM Providers</span>' +
          '<button class="admin-provider-add-btn">+ Add Provider</button>' +
        '</div>' +
        '<div class="admin-provider-list" role="list">' +
          '<div class="admin-loading">Loading providers\u2026</div>' +
        '</div>';

      var addBtn = contentEl.querySelector('.admin-provider-add-btn');
      addBtn.onclick = function () {
        providerFormMode = 'add';
        editingProvider = null;
        renderProvidersPanel();
      };

      fetchProviders();
    }

    function fetchProviders() {
      fetch('/api/providers')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          providers = data;
          renderProviderList();
        })
        .catch(function () {
          var listEl = contentEl.querySelector('.admin-provider-list');
          if (listEl) listEl.innerHTML = '<div class="admin-loading">Failed to load providers.</div>';
        });
    }

    function renderProviderList() {
      var listEl = contentEl.querySelector('.admin-provider-list');
      if (!listEl) return;

      if (providers.length === 0) {
        listEl.innerHTML =
          '<div class="admin-provider-empty">' +
            'No providers configured. Add one to get started.' +
          '</div>';
        return;
      }

      var html = '';
      for (var i = 0; i < providers.length; i++) {
        var p = providers[i];
        var badgeColor = TYPE_BADGE_COLORS[p.type] || '#888';
        html +=
          '<div class="admin-provider-card" role="listitem" data-id="' + escapeAttr(p.id) + '">' +
            '<span class="admin-provider-badge" style="background:' + badgeColor + '">' + escapeHtml(p.type) + '</span>' +
            '<span class="admin-provider-name">' + escapeHtml(p.name) + '</span>' +
            '<div class="admin-provider-actions">' +
              '<button class="admin-provider-edit-btn" data-id="' + escapeAttr(p.id) + '">Edit</button>' +
              '<button class="admin-provider-delete-btn" data-id="' + escapeAttr(p.id) + '">Delete</button>' +
            '</div>' +
          '</div>';
      }
      listEl.innerHTML = html;

      // Wire edit buttons
      var editBtns = listEl.querySelectorAll('.admin-provider-edit-btn');
      for (var e = 0; e < editBtns.length; e++) {
        editBtns[e].addEventListener('click', function (ev) {
          var id = ev.target.dataset.id;
          var provider = findProvider(id);
          if (provider) {
            providerFormMode = 'edit';
            editingProvider = provider;
            renderProvidersPanel();
          }
        });
      }

      // Wire delete buttons
      var delBtns = listEl.querySelectorAll('.admin-provider-delete-btn');
      for (var d = 0; d < delBtns.length; d++) {
        delBtns[d].addEventListener('click', function (ev) {
          var btn = ev.target;
          var id = btn.dataset.id;
          handleProviderDelete(id, btn);
        });
      }
    }

    function findProvider(id) {
      for (var i = 0; i < providers.length; i++) {
        if (providers[i].id === id) return providers[i];
      }
      return null;
    }

    // ── Provider Delete ───────────────────────────────────────────────

    var deleteConfirmTimer = null;

    function handleProviderDelete(id, btn) {
      if (btn.classList.contains('admin-provider-delete-confirm')) {
        // Second click — actually delete
        fetch('/api/providers/' + encodeURIComponent(id), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Delete failed'); });
            showAdminFlash('Provider deleted');
            providerFormMode = null;
            editingProvider = null;
            renderProvidersPanel();
          })
          .catch(function (err) {
            showAdminFlash('Error: ' + err.message, true);
          });
        return;
      }

      // First click — check agent usage and show confirm
      fetch('/api/agents')
        .then(function (r) { return r.json(); })
        .then(function (agents) {
          var count = 0;
          for (var i = 0; i < agents.length; i++) {
            if (agents[i].provider_config_id === id) count++;
          }

          btn.classList.add('admin-provider-delete-confirm');
          btn.setAttribute('aria-live', 'assertive');
          if (count > 0) {
            btn.textContent = count + ' agent' + (count > 1 ? 's' : '') + ' use this — confirm?';
          } else {
            btn.textContent = 'Confirm delete?';
          }

          if (deleteConfirmTimer) clearTimeout(deleteConfirmTimer);
          deleteConfirmTimer = setTimeout(function () {
            btn.classList.remove('admin-provider-delete-confirm');
            btn.removeAttribute('aria-live');
            btn.textContent = 'Delete';
          }, 3000);
        })
        .catch(function () {
          // If agent fetch fails, still allow delete with basic confirm
          btn.classList.add('admin-provider-delete-confirm');
          btn.setAttribute('aria-live', 'assertive');
          btn.textContent = 'Confirm delete?';
          if (deleteConfirmTimer) clearTimeout(deleteConfirmTimer);
          deleteConfirmTimer = setTimeout(function () {
            btn.classList.remove('admin-provider-delete-confirm');
            btn.removeAttribute('aria-live');
            btn.textContent = 'Delete';
          }, 3000);
        });
    }

    // ── Provider Form ─────────────────────────────────────────────────

    function renderProviderForm(provider) {
      var isEdit = !!provider;
      var type = isEdit ? provider.type : 'ollama';
      var defaults = TYPE_DEFAULTS[type];

      var html =
        '<div class="admin-header">' +
          '<span class="admin-title">' + (isEdit ? 'Edit Provider' : 'Add Provider') + '</span>' +
        '</div>' +
        '<div class="admin-provider-form">';

      // Name field
      html +=
        '<div class="admin-pf-row">' +
          '<label class="admin-pf-label" for="pf-name">Name</label>' +
          '<input class="admin-pf-input" id="pf-name" data-field="name" value="' + escapeAttr(isEdit ? provider.name : '') + '" placeholder="My Provider" />' +
        '</div>';

      // Type dropdown
      html += '<div class="admin-pf-row">' +
        '<label class="admin-pf-label" for="pf-type">Type</label>' +
        '<select class="admin-pf-input admin-pf-select" id="pf-type" data-field="type">';
      for (var t = 0; t < PROVIDER_TYPES.length; t++) {
        var pt = PROVIDER_TYPES[t];
        html += '<option value="' + escapeAttr(pt.value) + '"' + (type === pt.value ? ' selected' : '') + '>' + escapeHtml(pt.label) + '</option>';
      }
      html += '</select></div>';

      // Base URL field
      var baseUrlValue = isEdit ? provider.base_url : defaults.base_url;
      html +=
        '<div class="admin-pf-row admin-pf-base-url" style="display:' + (defaults.showBaseUrl ? 'flex' : 'none') + '">' +
          '<label class="admin-pf-label" for="pf-base-url">Base URL</label>' +
          '<input class="admin-pf-input" id="pf-base-url" data-field="base_url" value="' + escapeAttr(baseUrlValue) + '" placeholder="https://..." />' +
        '</div>';

      // API Key field
      var apiKeyValue = isEdit ? (provider.api_key || '') : '';
      html +=
        '<div class="admin-pf-row admin-pf-api-key" style="display:' + (defaults.showApiKey ? 'flex' : 'none') + '">' +
          '<label class="admin-pf-label" for="pf-api-key">API Key</label>' +
          '<div class="admin-pf-password-wrap">' +
            '<input class="admin-pf-input admin-pf-password" id="pf-api-key" type="password" data-field="api_key" value="' + escapeAttr(apiKeyValue) + '" placeholder="sk-..." />' +
            '<button class="admin-pf-eye" type="button" title="Show/Hide" aria-label="Show password">\u25CF\u25CF\u25CF</button>' +
          '</div>' +
        '</div>';

      // Action buttons
      html += '<div class="admin-pf-actions">';
      html += '<span class="admin-pf-error"></span>';
      html += '<button class="admin-pf-cancel">Cancel</button>';
      html += '<button class="admin-pf-save">' + (isEdit ? 'Save' : 'Create') + '</button>';
      if (isEdit) {
        html += '<button class="admin-pf-test">Test Connection</button>';
      }
      html += '</div>';

      // Test result area
      html += '<div class="admin-pf-test-result" aria-live="polite"></div>';

      // Model list area
      html += '<div class="admin-pf-models"></div>';

      html += '</div>'; // .admin-provider-form

      contentEl.innerHTML = html;

      wireProviderFormEvents(isEdit, provider);
    }

    function wireProviderFormEvents(isEdit, provider) {
      var typeSelect = contentEl.querySelector('[data-field="type"]');
      var baseUrlRow = contentEl.querySelector('.admin-pf-base-url');
      var baseUrlInput = contentEl.querySelector('[data-field="base_url"]');
      var apiKeyRow = contentEl.querySelector('.admin-pf-api-key');
      var cancelBtn = contentEl.querySelector('.admin-pf-cancel');
      var saveBtn = contentEl.querySelector('.admin-pf-save');
      var testBtn = contentEl.querySelector('.admin-pf-test');
      var eyeBtn = contentEl.querySelector('.admin-pf-eye');
      var passwordInput = contentEl.querySelector('.admin-pf-password');

      // Type change handler
      typeSelect.addEventListener('change', function () {
        var val = typeSelect.value;
        var defaults = TYPE_DEFAULTS[val];
        baseUrlRow.style.display = defaults.showBaseUrl ? 'flex' : 'none';
        apiKeyRow.style.display = defaults.showApiKey ? 'flex' : 'none';
        // Set default base_url when switching types
        if (defaults.base_url) {
          baseUrlInput.value = defaults.base_url;
        } else {
          baseUrlInput.value = '';
        }
      });

      // Eye toggle
      if (eyeBtn && passwordInput) {
        eyeBtn.addEventListener('click', function () {
          if (passwordInput.type === 'password') {
            passwordInput.type = 'text';
            eyeBtn.textContent = '\u25CB\u25CB\u25CB';
            eyeBtn.setAttribute('aria-label', 'Hide password');
          } else {
            passwordInput.type = 'password';
            eyeBtn.textContent = '\u25CF\u25CF\u25CF';
            eyeBtn.setAttribute('aria-label', 'Show password');
          }
        });
      }

      // Cancel
      cancelBtn.addEventListener('click', function () {
        providerFormMode = null;
        editingProvider = null;
        renderProvidersPanel();
      });

      // Save
      saveBtn.addEventListener('click', function () {
        var errorEl = contentEl.querySelector('.admin-pf-error');
        var nameInput = contentEl.querySelector('[data-field="name"]');
        var name = nameInput.value.trim();
        if (!name) {
          errorEl.textContent = 'Name is required.';
          return;
        }

        var selectedType = typeSelect.value;
        var defaults = TYPE_DEFAULTS[selectedType];

        // Always include base_url — it's required on the model
        var baseUrl = baseUrlInput.value.trim();
        if (!defaults.showBaseUrl) {
          baseUrl = defaults.base_url;
        }
        if (!baseUrl) {
          errorEl.textContent = 'Base URL is required.';
          return;
        }

        var apiKeyInput = contentEl.querySelector('[data-field="api_key"]');
        var apiKey = apiKeyInput ? apiKeyInput.value : null;
        if (!apiKey) apiKey = null;

        var payload = {
          name: name,
          type: selectedType,
          base_url: baseUrl,
          api_key: apiKey
        };

        errorEl.textContent = '';

        if (isEdit) {
          fetch('/api/providers/' + encodeURIComponent(provider.id), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          })
            .then(function (r) {
              if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Save failed'); });
              return r.json();
            })
            .then(function (updated) {
              editingProvider = updated;
              showAdminFlash('Provider saved');
              // Re-render form with updated data (now has id, show test btn)
              renderProviderForm(updated);
            })
            .catch(function (err) {
              errorEl.textContent = err.message;
            });
        } else {
          fetch('/api/providers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          })
            .then(function (r) {
              if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Create failed'); });
              return r.json();
            })
            .then(function (created) {
              showAdminFlash('Provider created');
              // Switch to edit mode for the newly created provider
              providerFormMode = 'edit';
              editingProvider = created;
              renderProviderForm(created);
            })
            .catch(function (err) {
              errorEl.textContent = err.message;
            });
        }
      });

      // Test connection
      if (testBtn && isEdit) {
        testBtn.addEventListener('click', function () {
          var resultEl = contentEl.querySelector('.admin-pf-test-result');
          resultEl.innerHTML = '<span class="admin-pf-testing">Testing\u2026</span>';
          testBtn.disabled = true;

          fetch('/api/providers/' + encodeURIComponent(provider.id) + '/test', { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(function (result) {
              testBtn.disabled = false;
              if (result.status === 'ok') {
                resultEl.innerHTML = '<span class="admin-pf-test-ok">\u2713 ' + escapeHtml(result.detail || 'Connected') + '</span>';
                showAdminFlash('Connection successful');
                // Auto-fetch models
                fetchProviderModels(provider.id);
              } else {
                resultEl.innerHTML = '<span class="admin-pf-test-fail">\u2717 ' + escapeHtml(result.detail || 'Failed') + '</span>';
                showAdminFlash('Connection failed', true);
              }
            })
            .catch(function (err) {
              testBtn.disabled = false;
              resultEl.innerHTML = '<span class="admin-pf-test-fail">\u2717 ' + escapeHtml(err.message || 'Request failed') + '</span>';
              showAdminFlash('Connection test error', true);
            });
        });
      }
    }

    // ── Model Discovery ───────────────────────────────────────────────

    function fetchProviderModels(providerId) {
      var modelsEl = contentEl.querySelector('.admin-pf-models');
      if (!modelsEl) return;

      modelsEl.innerHTML =
        '<div class="admin-pf-models-header">' +
          '<span class="admin-pf-models-title">Models</span>' +
          '<button class="admin-pf-models-refresh">Refresh</button>' +
        '</div>' +
        '<div class="admin-pf-models-list" aria-live="polite"><span class="admin-loading">Loading models\u2026</span></div>';

      var refreshBtn = modelsEl.querySelector('.admin-pf-models-refresh');
      refreshBtn.addEventListener('click', function () {
        fetchProviderModels(providerId);
      });

      fetch('/api/providers/' + encodeURIComponent(providerId) + '/models')
        .then(function (r) {
          if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Failed to load models'); });
          return r.json();
        })
        .then(function (models) {
          var listEl = modelsEl.querySelector('.admin-pf-models-list');
          if (!listEl) return;

          if (models.length === 0) {
            listEl.innerHTML = '<span class="admin-pf-models-empty">No models found.</span>';
            return;
          }

          var html = '';
          for (var i = 0; i < models.length; i++) {
            html += '<div class="admin-pf-model-item">' + escapeHtml(models[i].id || models[i].name) + '</div>';
          }
          listEl.innerHTML = html;
        })
        .catch(function (err) {
          var listEl = modelsEl.querySelector('.admin-pf-models-list');
          if (listEl) {
            listEl.innerHTML = '<span class="admin-pf-test-fail">' + escapeHtml(err.message || 'Failed to load models') + '</span>';
          }
        });
    }

    // ── Flash Feedback ────────────────────────────────────────────────

    function showAdminFlash(msg, isError) {
      var el = document.createElement('div');
      el.className = 'admin-flash' + (isError ? ' error' : '');
      if (isError) {
        el.setAttribute('role', 'alert');
      } else {
        el.setAttribute('role', 'status');
        el.setAttribute('aria-live', 'polite');
      }
      el.textContent = msg;
      contentEl.appendChild(el);
      setTimeout(function () { el.classList.add('visible'); }, 10);
      setTimeout(function () {
        el.classList.remove('visible');
        setTimeout(function () { el.remove(); }, 300);
      }, 2000);
    }

    // ── Helpers ────────────────────────────────────────────────────────

    var escapeHtml = App.escapeHtml;

    function escapeAttr(s) {
      if (!s) return '';
      return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // Store reference for activate() to reuse
    var self = this;
    self._refresh = function () {
      if (currentCategory === 'general') {
        fetchSettings();
      } else if (currentCategory === 'providers' && !providerFormMode) {
        fetchProviders();
      }
    };

    // ── Init ──────────────────────────────────────────────────────────

    renderCategoryList();
    renderContent();
  },

  activate: function () {
    if (this._refresh) {
      this._refresh();
    }
  },

  deactivate: function () {}
});
