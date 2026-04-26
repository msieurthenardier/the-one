App.registerArea({
  id: 'studio',
  label: 'Studio',
  icon: App.icons.studio,
  order: 20,

  init: function (sidebar, content) {
    var agents = [];
    var allTools = [];
    var allMcpSources = [];
    var allKnowledgeBases = [];
    var allProviders = [];
    var selectedAgent = null;
    var createMode = false;
    var dirty = false;
    var snapshot = '';
    var deleteTimer = null;

    var TOOL_CATEGORIES = {
      'Filesystem': ['read_file', 'write_file', 'list_dir'],
      'Execution': ['shell', 'python_exec', 'run_tests'],
      'Web': ['http_request', 'web_search'],
      'System': ['git', 'self_deploy', 'rollback', 'restart', 'mission_control', 'memory']
    };

    // Build sidebar
    sidebar.innerHTML =
      '<div class="studio-sidebar-header">' +
        '<span class="title">Studio</span>' +
        '<button class="new-agent-btn" data-testid="new-agent-btn" aria-label="New agent">' + App.icon('plus') + '</button>' +
      '</div>' +
      '<div class="agent-list"></div>';

    var agentListEl = sidebar.querySelector('.agent-list');
    var newAgentBtn = sidebar.querySelector('.new-agent-btn');

    // Build content
    content.innerHTML = '<div class="studio-editor"></div>';
    var editorEl = content.querySelector('.studio-editor');

    // ── Data fetching ────────────────────────────────────────────────

    function fetchAgents() {
      return fetch('/api/agents').then(function (r) { return r.json(); });
    }

    function fetchTools() {
      return fetch('/api/tools').then(function (r) { return r.json(); });
    }

    function fetchMcpSources() {
      return fetch('/api/mcp-sources').then(function (r) { return r.json(); });
    }

    function fetchKnowledgeBases() {
      return fetch('/api/knowledge-bases').then(function (r) { return r.json(); });
    }

    function fetchProviders() {
      return fetch('/api/providers').then(function (r) { return r.json(); });
    }

    function loadAll() {
      return Promise.all([fetchAgents(), fetchTools(), fetchMcpSources(), fetchKnowledgeBases(), fetchProviders()])
        .then(function (results) {
          agents = results[0];
          allTools = results[1];
          allMcpSources = results[2];
          allKnowledgeBases = results[3];
          allProviders = results[4];
          renderAgentList();
        });
    }

    // ── Sidebar rendering ────────────────────────────────────────────

    function renderAgentList() {
      agentListEl.innerHTML = '';
      if (agents.length === 0 && !createMode) {
        var empty = document.createElement('div');
        empty.className = 'agent-empty';
        empty.setAttribute('data-testid', 'agent-empty');
        empty.textContent = 'No agents yet. Click + to create one.';
        agentListEl.appendChild(empty);
        return;
      }
      for (var i = 0; i < agents.length; i++) {
        (function (agent) {
          var el = document.createElement('div');
          el.className = 'agent-item' + (selectedAgent && selectedAgent.name === agent.name && !createMode ? ' active' : '');
          el.dataset.name = agent.name;
          el.setAttribute('data-testid', 'agent-item');

          var nameSpan = document.createElement('span');
          nameSpan.className = 'agent-item-name';
          nameSpan.textContent = agent.name;
          el.appendChild(nameSpan);

          var delBtn = document.createElement('span');
          delBtn.className = 'agent-item-delete';
          delBtn.innerHTML = App.icon('x');
          delBtn.onclick = function (e) {
            e.stopPropagation();
            deleteAgentInline(agent.name, el);
          };
          el.appendChild(delBtn);

          el.onclick = function () { selectAgent(agent); };
          agentListEl.appendChild(el);
        })(agents[i]);
      }
    }

    function deleteAgentInline(name, el) {
      if (el.classList.contains('confirm-delete')) {
        fetch('/api/agents/' + encodeURIComponent(name), { method: 'DELETE' })
          .then(function () {
            if (selectedAgent && selectedAgent.name === name) {
              selectedAgent = null;
              createMode = false;
              dirty = false;
            }
            return loadAll();
          })
          .then(function () {
            if (!selectedAgent && agents.length > 0) {
              selectAgent(agents[0]);
            } else if (agents.length === 0) {
              renderEmptyEditor();
            }
          });
        return;
      }
      el.classList.add('confirm-delete');
      var nameEl = el.querySelector('.agent-item-name');
      var original = nameEl.textContent;
      nameEl.textContent = 'Confirm delete?';
      if (deleteTimer) clearTimeout(deleteTimer);
      deleteTimer = setTimeout(function () {
        el.classList.remove('confirm-delete');
        nameEl.textContent = original;
      }, 3000);
    }

    // ── Agent selection ──────────────────────────────────────────────

    function selectAgent(agent) {
      if (dirty) {
        if (!confirm('You have unsaved changes. Discard them?')) return;
      }
      createMode = false;
      selectedAgent = agent;
      dirty = false;
      renderAgentList();
      renderEditor(agent);
    }

    function enterCreateMode() {
      if (dirty) {
        if (!confirm('You have unsaved changes. Discard them?')) return;
      }
      createMode = true;
      selectedAgent = null;
      dirty = false;
      renderAgentList();
      renderEditor(null);
    }

    // ── Editor rendering ─────────────────────────────────────────────

    function renderEmptyEditor() {
      editorEl.innerHTML = '<div class="editor-empty">Select an agent or click + to create one.</div>';
    }

    function renderEditor(agent) {
      var isCreate = !agent;
      var cfg = agent || {
        name: '', description: '', provider_config_id: allProviders.length > 0 ? allProviders[0].id : null, llm_model: '',
        system_prompt: '', enabled_tools: null, disabled_tools: [],
        kb_ids: [], mcp_source_ids: [], max_iterations: 20
      };

      // Determine enabled tool set
      var enabledSet = {};
      for (var i = 0; i < allTools.length; i++) {
        var tn = allTools[i].name;
        if (cfg.enabled_tools !== null && cfg.enabled_tools !== undefined) {
          enabledSet[tn] = cfg.enabled_tools.indexOf(tn) >= 0;
        } else {
          enabledSet[tn] = cfg.disabled_tools.indexOf(tn) < 0;
        }
      }

      var html = '';

      // Header
      html += '<div class="editor-header">';
      if (isCreate) {
        html += '<span class="editor-title">New Agent</span>';
      } else {
        html += '<span class="editor-title">' + escapeHtml(cfg.name) + '</span>';
        html += '<button class="delete-btn" data-testid="delete-agent-btn" data-name="' + escapeHtml(cfg.name) + '">Delete Agent</button>';
      }
      html += '</div>';

      html += '<div class="editor-form">';

      // Identity
      html += '<div class="editor-section"><div class="section-title">Identity</div>';
      if (isCreate) {
        html += '<div class="field-row"><label>Name</label><input class="field-input" data-field="name" value="" placeholder="agent-name" /></div>';
      }
      html += '<div class="field-row"><label>Description</label><input class="field-input" data-field="description" value="' + escapeAttr(cfg.description) + '" placeholder="What does this agent do?" /></div>';
      html += '</div>';

      // LLM Configuration
      html += '<div class="editor-section"><div class="section-title">LLM Configuration</div>';

      // Provider dropdown
      html += '<div class="field-row"><label for="studio-provider">Provider</label>';
      html += '<select id="studio-provider" class="field-input field-select" data-field="provider_config_id">';
      if (!cfg.provider_config_id) {
        html += '<option value="" disabled selected>No provider \u2014 configure in Admin</option>';
      }
      var providerFound = false;
      for (var p = 0; p < allProviders.length; p++) {
        var prov = allProviders[p];
        var provSelected = cfg.provider_config_id === prov.id ? ' selected' : '';
        if (cfg.provider_config_id === prov.id) providerFound = true;
        html += '<option value="' + escapeAttr(prov.id) + '"' + provSelected + '>' + escapeHtml(prov.name) + ' (' + escapeHtml(prov.type) + ')</option>';
      }
      if (cfg.provider_config_id && !providerFound) {
        html += '<option value="' + escapeAttr(cfg.provider_config_id) + '" selected>Unknown provider (' + escapeAttr(cfg.provider_config_id) + ')</option>';
      }
      html += '</select></div>';

      // Model select dropdown
      html += '<div class="field-row"><label for="studio-model">Model</label>';
      html += '<div class="field-model-wrap">';
      html += '<select id="studio-model" class="field-input field-select" data-field="llm_model">';
      html += '<option value="" disabled selected>Select a provider first</option>';
      html += '</select>';
      html += '<span class="model-loading" aria-live="polite"></span>';
      html += '</div></div>';

      // VRAM warning placeholder (ollama only)
      html += '<div class="studio-vram-warning" role="status" aria-live="polite"></div>';

      html += '</div>';

      // System Prompt
      html += '<div class="editor-section"><div class="section-title">System Prompt</div>';
      html += '<textarea class="field-textarea" data-field="system_prompt" rows="8" placeholder="Instructions for the agent...">' + escapeHtml(cfg.system_prompt) + '</textarea>';
      html += '</div>';

      // Tools
      html += '<div class="editor-section"><div class="section-title">Tools</div>';
      html += '<div class="tool-actions"><button class="tool-select-all">All</button><button class="tool-select-none">None</button></div>';
      var catKeys = Object.keys(TOOL_CATEGORIES);
      for (var c = 0; c < catKeys.length; c++) {
        var cat = catKeys[c];
        var toolNames = TOOL_CATEGORIES[cat];
        html += '<div class="tool-group">' + escapeHtml(cat) + '</div>';
        for (var t = 0; t < toolNames.length; t++) {
          var tName = toolNames[t];
          var toolInfo = findTool(tName);
          var checked = enabledSet[tName] ? ' checked' : '';
          html += '<label class="tool-row">';
          html += '<input type="checkbox" class="tool-toggle" data-tool="' + escapeAttr(tName) + '"' + checked + ' />';
          html += '<span class="tool-switch"></span>';
          html += '<span class="tool-name">' + escapeHtml(tName) + '</span>';
          html += '<span class="tool-desc">' + escapeHtml(toolInfo ? toolInfo.description : '') + '</span>';
          html += '</label>';
        }
      }
      html += '</div>';

      // Connections
      html += '<div class="editor-section"><div class="section-title">Connections</div>';

      // MCP Sources
      html += '<div class="connection-group"><span class="connection-label">MCP Sources</span>';
      html += '<div class="chip-area" data-type="mcp">';
      for (var m = 0; m < cfg.mcp_source_ids.length; m++) {
        html += '<span class="chip" data-id="' + escapeAttr(cfg.mcp_source_ids[m]) + '">' +
          escapeHtml(mcpName(cfg.mcp_source_ids[m])) + '<span class="chip-remove">' + App.icon('x') + '</span></span>';
      }
      html += '<button class="chip-add" data-type="mcp">+ Add</button>';
      html += '</div></div>';

      // Knowledge Bases
      html += '<div class="connection-group"><span class="connection-label">Knowledge Bases</span>';
      html += '<div class="chip-area" data-type="kb">';
      for (var k = 0; k < cfg.kb_ids.length; k++) {
        html += '<span class="chip" data-id="' + escapeAttr(cfg.kb_ids[k]) + '">' +
          escapeHtml(kbName(cfg.kb_ids[k])) + '<span class="chip-remove">' + App.icon('x') + '</span></span>';
      }
      html += '<button class="chip-add" data-type="kb">+ Add</button>';
      html += '</div></div>';
      html += '</div>';

      // Max iterations
      html += '<div class="editor-section"><div class="section-title">Behavior</div>';
      html += '<div class="field-row"><label>Max Iterations</label><input class="field-input field-input-short" data-field="max_iterations" type="number" value="' + cfg.max_iterations + '" min="1" max="100" /></div>';
      html += '</div>';

      // Save button
      html += '<div class="editor-actions">';
      html += '<span class="editor-error"></span>';
      html += '<button class="save-btn clean" data-testid="save-agent-btn">' + (isCreate ? 'Create' : 'Save') + '</button>';
      html += '</div>';

      html += '</div>'; // .editor-form

      editorEl.innerHTML = html;

      // Take snapshot for dirty tracking
      snapshot = getFormSnapshot();

      // Wire events
      wireEditorEvents(isCreate, cfg);
    }

    function fetchModelsForProvider(providerId) {
      var selectEl = editorEl.querySelector('#studio-model');
      var loadingEl = editorEl.querySelector('.model-loading');
      if (!selectEl) return;

      var currentVal = selectEl.dataset.pendingValue || selectEl.value;

      if (!providerId) {
        selectEl.innerHTML = '<option value="" disabled selected>Select a provider first</option>';
        if (loadingEl) loadingEl.textContent = '';
        return;
      }

      if (loadingEl) loadingEl.textContent = 'Loading models\u2026';

      fetch('/api/providers/' + encodeURIComponent(providerId) + '/models')
        .then(function (r) {
          if (!r.ok) throw new Error('Failed');
          return r.json();
        })
        .then(function (models) {
          var html = '<option value="" disabled>Choose a model</option>';
          for (var i = 0; i < models.length; i++) {
            var modelId = models[i].id || models[i].name;
            var sel = modelId === currentVal ? ' selected' : '';
            html += '<option value="' + escapeAttr(modelId) + '"' + sel + '>' + escapeHtml(modelId) + '</option>';
          }
          selectEl.innerHTML = html;
          // If current value wasn't in the list, add it as a custom option
          if (currentVal && !selectEl.querySelector('option[value="' + CSS.escape(currentVal) + '"]')) {
            var customOpt = '<option value="' + escapeAttr(currentVal) + '" selected>' + escapeHtml(currentVal) + ' (custom)</option>';
            selectEl.insertAdjacentHTML('beforeend', customOpt);
          }
          if (loadingEl) {
            loadingEl.textContent = models.length === 0 ? 'No models discovered' : '';
          }
          delete selectEl.dataset.pendingValue;
        })
        .catch(function () {
          selectEl.innerHTML = '<option value="" disabled selected>Failed to load models</option>';
          if (loadingEl) loadingEl.textContent = '';
        });
    }

    function wireEditorEvents(isCreate, cfg) {
      // Dirty tracking on all inputs
      var inputs = editorEl.querySelectorAll('.field-input, .field-textarea, .field-select, .tool-toggle');
      for (var i = 0; i < inputs.length; i++) {
        inputs[i].addEventListener('input', checkDirty);
        inputs[i].addEventListener('change', checkDirty);
      }

      // Provider change -> fetch models + clear VRAM warning
      var providerSelect = editorEl.querySelector('#studio-provider');
      if (providerSelect) {
        providerSelect.addEventListener('change', function () {
          var modelSelect = editorEl.querySelector('#studio-model');
          if (modelSelect) modelSelect.selectedIndex = 0;
          clearVramWarning();
          fetchModelsForProvider(providerSelect.value);
        });
        // Auto-fetch models for currently selected provider
        if (cfg.provider_config_id) {
          var modelSelect = editorEl.querySelector('#studio-model');
          if (modelSelect && cfg.llm_model) modelSelect.dataset.pendingValue = cfg.llm_model;
          fetchModelsForProvider(cfg.provider_config_id);
        }
      }

      // Model input -> debounced VRAM check (ollama only)
      var modelInput = editorEl.querySelector('#studio-model');
      if (modelInput) {
        modelInput.addEventListener('change', debouncedVramCheck);
        // Check on initial load if model is already set
        if (cfg.llm_model && cfg.provider_config_id) {
          debouncedVramCheck();
        }
      }

      // Tool select all/none
      var selectAllBtn = editorEl.querySelector('.tool-select-all');
      var selectNoneBtn = editorEl.querySelector('.tool-select-none');
      if (selectAllBtn) selectAllBtn.onclick = function () { setAllTools(true); };
      if (selectNoneBtn) selectNoneBtn.onclick = function () { setAllTools(false); };

      // Delete button
      var deleteBtn = editorEl.querySelector('.delete-btn');
      if (deleteBtn) {
        deleteBtn.onclick = function () {
          if (deleteBtn.classList.contains('confirm')) {
            fetch('/api/agents/' + encodeURIComponent(cfg.name), { method: 'DELETE' })
              .then(function () {
                selectedAgent = null;
                dirty = false;
                return loadAll();
              })
              .then(function () {
                if (agents.length > 0) selectAgent(agents[0]);
                else renderEmptyEditor();
              });
            return;
          }
          deleteBtn.classList.add('confirm');
          deleteBtn.textContent = 'Confirm Delete?';
          setTimeout(function () {
            deleteBtn.classList.remove('confirm');
            deleteBtn.textContent = 'Delete Agent';
          }, 3000);
        };
      }

      // Chip removal
      editorEl.addEventListener('click', function (e) {
        if (e.target.classList.contains('chip-remove')) {
          e.target.parentElement.remove();
          checkDirty();
        }
      });

      // Chip add buttons
      var addBtns = editorEl.querySelectorAll('.chip-add');
      for (var a = 0; a < addBtns.length; a++) {
        addBtns[a].addEventListener('click', function (e) {
          var type = e.target.dataset.type;
          showAddDropdown(e.target, type);
        });
      }

      // Save
      var saveBtn = editorEl.querySelector('.save-btn');
      saveBtn.onclick = function () { save(isCreate); };
    }

    // ── Tool helpers ─────────────────────────────────────────────────

    function setAllTools(on) {
      var toggles = editorEl.querySelectorAll('.tool-toggle');
      for (var i = 0; i < toggles.length; i++) toggles[i].checked = on;
      checkDirty();
    }

    function findTool(name) {
      for (var i = 0; i < allTools.length; i++) {
        if (allTools[i].name === name) return allTools[i];
      }
      return null;
    }

    // ── Connection helpers ───────────────────────────────────────────

    function mcpName(id) {
      for (var i = 0; i < allMcpSources.length; i++) {
        if (allMcpSources[i].id === id) return allMcpSources[i].name || id;
      }
      return id;
    }

    function kbName(id) {
      for (var i = 0; i < allKnowledgeBases.length; i++) {
        if (allKnowledgeBases[i].id === id) return allKnowledgeBases[i].name || id;
      }
      return id;
    }

    function showAddDropdown(btn, type) {
      // Remove existing dropdown
      var existing = editorEl.querySelector('.add-dropdown');
      if (existing) existing.remove();

      var chipArea = btn.closest('.chip-area');
      var currentIds = [];
      var chips = chipArea.querySelectorAll('.chip');
      for (var i = 0; i < chips.length; i++) currentIds.push(chips[i].dataset.id);

      var items = type === 'mcp' ? allMcpSources : allKnowledgeBases;
      var available = [];
      for (var j = 0; j < items.length; j++) {
        if (currentIds.indexOf(items[j].id) < 0) available.push(items[j]);
      }

      if (available.length === 0) return;

      var dropdown = document.createElement('div');
      dropdown.className = 'add-dropdown';
      for (var k = 0; k < available.length; k++) {
        (function (item) {
          var opt = document.createElement('div');
          opt.className = 'add-dropdown-item';
          opt.textContent = item.name || item.id;
          opt.onclick = function () {
            var chip = document.createElement('span');
            chip.className = 'chip';
            chip.dataset.id = item.id;
            chip.innerHTML = escapeHtml(item.name || item.id) + '<span class="chip-remove">' + App.icon('x') + '</span>';
            chipArea.insertBefore(chip, btn);
            dropdown.remove();
            checkDirty();
          };
          dropdown.appendChild(opt);
        })(available[k]);
      }

      btn.parentElement.style.position = 'relative';
      btn.parentElement.appendChild(dropdown);

      // Close on outside click
      setTimeout(function () {
        document.addEventListener('click', function close(e) {
          if (!dropdown.contains(e.target) && e.target !== btn) {
            dropdown.remove();
            document.removeEventListener('click', close);
          }
        });
      }, 0);
    }

    // ── Dirty tracking ───────────────────────────────────────────────

    function getFormSnapshot() {
      var data = collectFormData();
      return JSON.stringify(data);
    }

    function checkDirty() {
      var current = getFormSnapshot();
      dirty = current !== snapshot;
      var saveBtn = editorEl.querySelector('.save-btn');
      if (saveBtn) {
        saveBtn.classList.toggle('clean', !dirty);
        saveBtn.classList.toggle('dirty', dirty);
      }
    }

    // ── Form data collection ─────────────────────────────────────────

    function collectFormData() {
      var data = {};
      var fields = editorEl.querySelectorAll('.field-input, .field-textarea, .field-select');
      for (var i = 0; i < fields.length; i++) {
        var f = fields[i];
        var key = f.dataset.field;
        if (key === 'max_iterations') {
          data[key] = parseInt(f.value, 10) || 20;
        } else if (key === 'provider_config_id') {
          data[key] = f.value || null;
        } else {
          data[key] = f.value;
        }
      }

      // Tool state
      var toggles = editorEl.querySelectorAll('.tool-toggle');
      var enabledNames = [];
      var disabledNames = [];
      var allOn = true;
      var allOff = true;
      for (var t = 0; t < toggles.length; t++) {
        if (toggles[t].checked) {
          enabledNames.push(toggles[t].dataset.tool);
          allOff = false;
        } else {
          disabledNames.push(toggles[t].dataset.tool);
          allOn = false;
        }
      }

      if (allOn) {
        data.enabled_tools = null;
        data.disabled_tools = [];
      } else if (enabledNames.length <= disabledNames.length) {
        data.enabled_tools = enabledNames;
        data.disabled_tools = [];
      } else {
        data.enabled_tools = null;
        data.disabled_tools = disabledNames;
      }

      // Connections
      var mcpChips = editorEl.querySelectorAll('.chip-area[data-type="mcp"] .chip');
      var kbChips = editorEl.querySelectorAll('.chip-area[data-type="kb"] .chip');
      data.mcp_source_ids = [];
      data.kb_ids = [];
      for (var m = 0; m < mcpChips.length; m++) data.mcp_source_ids.push(mcpChips[m].dataset.id);
      for (var k = 0; k < kbChips.length; k++) data.kb_ids.push(kbChips[k].dataset.id);

      return data;
    }

    // ── Save ─────────────────────────────────────────────────────────

    function save(isCreate) {
      var data = collectFormData();
      var errorEl = editorEl.querySelector('.editor-error');

      if (isCreate) {
        if (!data.name || !data.name.trim()) {
          errorEl.textContent = 'Name is required.';
          return;
        }
        fetch('/api/agents', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Create failed'); });
            return r.json();
          })
          .then(function (created) {
            dirty = false;
            createMode = false;
            return loadAll().then(function () {
              var found = null;
              for (var i = 0; i < agents.length; i++) {
                if (agents[i].name === created.name) { found = agents[i]; break; }
              }
              if (found) selectAgent(found);
              showFlash('Agent created');
            });
          })
          .catch(function (err) {
            errorEl.textContent = err.message;
          });
      } else {
        var name = selectedAgent.name;
        data.name = name;
        fetch('/api/agents/' + encodeURIComponent(name), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Save failed'); });
            return r.json();
          })
          .then(function (updated) {
            dirty = false;
            selectedAgent = updated;
            return loadAll().then(function () {
              var found = null;
              for (var i = 0; i < agents.length; i++) {
                if (agents[i].name === updated.name) { found = agents[i]; break; }
              }
              if (found) {
                selectedAgent = found;
                renderEditor(found);
                showFlash('Saved');
              }
            });
          })
          .catch(function (err) {
            errorEl.textContent = err.message;
          });
      }
    }

    // ── Helpers ──────────────────────────────────────────────────────

    var showFlash = function (msg) { App.showFlash(editorEl, msg); };

    // ── VRAM warning helpers ─────────────────────────────────────────

    var formatBytes = App.formatBytes;

    var vramCheckTimer = null;

    function getSelectedProviderType() {
      var providerSelect = editorEl.querySelector('#studio-provider');
      if (!providerSelect || !providerSelect.value) return null;
      for (var i = 0; i < allProviders.length; i++) {
        if (String(allProviders[i].id) === String(providerSelect.value)) {
          return allProviders[i];
        }
      }
      return null;
    }

    function clearVramWarning() {
      var el = editorEl.querySelector('.studio-vram-warning');
      if (el) {
        el.innerHTML = '';
        el.classList.remove('visible');
      }
    }

    function checkVramForModel() {
      var provider = getSelectedProviderType();
      if (!provider || provider.type !== 'ollama') {
        clearVramWarning();
        return;
      }

      var modelInput = editorEl.querySelector('#studio-model');
      if (!modelInput || !modelInput.value.trim()) {
        clearVramWarning();
        return;
      }

      var modelName = modelInput.value.trim();
      var providerId = provider.id;

      Promise.all([
        fetch('/api/providers/' + encodeURIComponent(providerId) + '/models/status')
          .then(function (r) { return r.ok ? r.json() : []; }),
        fetch('/api/providers/' + encodeURIComponent(providerId) + '/models')
          .then(function (r) { return r.ok ? r.json() : []; })
      ])
        .then(function (results) {
          var running = results[0] || [];
          var models = results[1] || [];

          // Check if model is already loaded
          for (var i = 0; i < running.length; i++) {
            var runName = running[i].name || running[i].model || '';
            if (runName === modelName || runName.split(':')[0] === modelName.split(':')[0]) {
              clearVramWarning();
              return;
            }
          }

          // Find model in available list to get its size
          var modelSize = 0;
          for (var j = 0; j < models.length; j++) {
            var mId = models[j].id || models[j].name || '';
            if (mId === modelName || mId.split(':')[0] === modelName.split(':')[0]) {
              modelSize = models[j].size || 0;
              break;
            }
          }

          if (!modelSize) {
            clearVramWarning();
            return;
          }

          // Calculate total VRAM currently loaded
          var totalLoaded = 0;
          var loadedCount = running.length;
          for (var k = 0; k < running.length; k++) {
            totalLoaded += running[k].size_vram || 0;
          }

          // Show warning with model size and current load
          var warningEl = editorEl.querySelector('.studio-vram-warning');
          if (warningEl) {
            var msg = 'This model requires ~' + escapeHtml(formatBytes(modelSize)) + '.';
            if (loadedCount > 0) {
              msg += ' Currently ' + escapeHtml(formatBytes(totalLoaded)) +
                ' loaded across ' + loadedCount + ' model' + (loadedCount !== 1 ? 's' : '') + '.';
            }
            warningEl.innerHTML = msg;
            warningEl.classList.add('visible');
          }
        })
        .catch(function () {
          // Silently skip on network errors
          clearVramWarning();
        });
    }

    function debouncedVramCheck() {
      if (vramCheckTimer) clearTimeout(vramCheckTimer);
      vramCheckTimer = setTimeout(checkVramForModel, 500);
    }

    var escapeHtml = App.escapeHtml;
    var escapeAttr = App.escapeAttr;

    // ── Init ─────────────────────────────────────────────────────────

    newAgentBtn.addEventListener('click', enterCreateMode);

    var self = this;
    self._refresh = function () {
      loadAll().then(function () {
        if (selectedAgent) {
          var found = null;
          for (var i = 0; i < agents.length; i++) {
            if (agents[i].name === selectedAgent.name) { found = agents[i]; break; }
          }
          if (found) selectAgent(found);
          else if (agents.length > 0) selectAgent(agents[0]);
          else renderEmptyEditor();
        }
      });
    };

    loadAll().then(function () {
      if (agents.length > 0) {
        selectAgent(agents[0]);
      } else {
        renderEmptyEditor();
      }
    });
  },

  activate: function () {
    if (this._refresh) this._refresh();
  },
  deactivate: function () {}
});
