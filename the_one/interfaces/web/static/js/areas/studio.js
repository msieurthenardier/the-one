App.registerArea({
  id: 'studio',
  label: 'Agent Studio',
  icon: App.icons.studio,
  order: 20,
  sidebarLabel: 'Agent list',

  // ── Hash-routing serialize/hydrate ──────────────────────────────────
  //
  // serializeState branch order (explicit):
  //   1. _activeSection === 'knowledge' → 'knowledge'
  //   2. _activeSection === 'tools' → 'tools'
  //   3. _activeSection === 'agents' && agent selected && !createMode →
  //      'agents/<encoded-name>/<tab>'   (F5 leg 03 — appended /{tab})
  //   4. otherwise (no agent OR createMode) → 'agents'
  //
  // F5 leg 03 extends branch 3 by appending the active tab segment so the
  // URL reflects the editor's tab state. Defaults to 'general'. The F3
  // router's serialize-after-hydrate path performs the
  // #studio/agents/{name} → #studio/agents/{name}/general upgrade for free
  // (no new redirect logic in studio.js).
  serializeState: function () {
    if (this._activeSection === 'knowledge') return 'knowledge';
    if (this._activeSection === 'tools') return 'tools';
    if (this._activeSection === 'agents' && this._selectedAgent && !this._createMode) {
      return 'agents/' + encodeURIComponent(this._selectedAgent.name) +
        '/' + (this._activeTab || 'general');
    }
    // Hydrate-before-loadAll race: when the user lands on
    // #studio/agents/{name}/{tab} but agents fetch hasn't completed,
    // _selectedAgent is null even though we already know the target.
    // Without this branch, the F3 router's serialize-after-hydrate would
    // clobber the URL to #studio/agents before tryConsumePendingSelect
    // resolves. Returning the deep form keeps the URL stable.
    if (this._activeSection === 'agents' && this._pendingSelectName) {
      return 'agents/' + encodeURIComponent(this._pendingSelectName) +
        '/' + (this._activeTab || 'general');
    }
    return 'agents';
  },

  // hydrateState parses sub and updates the area's _activeSection + pending
  // agent selection state. After hydrate returns, the F3 router at
  // app.js:179-185 calls serializeState and writes URL via replaceState if
  // serialized !== sub (idempotent). Therefore hydrate MUST NOT call
  // _writeUrl itself — pass {writeUrl: false} when calling setActiveSection.
  //
  // F5 leg 03: extended to parse 'agents/<name>/<tab>'. Four cases:
  //   - 'agents/{name}'         → activeTab='general' (router rewrites URL)
  //   - 'agents/{name}/'        → activeTab='general' (defensive trailing-slash)
  //   - 'agents/{name}/general|knowledge|tools' → use that tab
  //   - 'agents/{name}/<other>' → defensively default to 'general'
  // Encoding note: agent names with literal '/' are encoded as '%2F' by
  // encodeURIComponent, so rest.indexOf('/') unambiguously finds the segment
  // separator.
  hydrateState: function (sub) {
    var section = 'agents';
    var pending = null;
    var pendingTab = 'general';
    if (sub === 'knowledge') {
      section = 'knowledge';
    } else if (sub === 'tools') {
      section = 'tools';
    } else if (sub && sub.indexOf('agents/') === 0) {
      section = 'agents';
      var rest = sub.slice('agents/'.length);
      var slashIdx = rest.indexOf('/');
      if (slashIdx === -1) {
        pending = decodeURIComponent(rest);
        pendingTab = 'general';
      } else if (slashIdx === rest.length - 1) {
        // Trailing-slash defensive — treat as no-tab.
        pending = decodeURIComponent(rest.slice(0, slashIdx));
        pendingTab = 'general';
      } else {
        pending = decodeURIComponent(rest.slice(0, slashIdx));
        var tab = rest.slice(slashIdx + 1);
        if (tab === 'general' || tab === 'knowledge' || tab === 'tools') {
          pendingTab = tab;
        } else {
          pendingTab = 'general';
        }
      }
    } else if (sub === 'agents' || !sub) {
      section = 'agents';
    } else {
      // Defensive: unrecognized sub defaults to 'agents'. Do NOT throw.
      section = 'agents';
    }
    this._activeSection = section;
    this._activeTab = pendingTab;
    if (pending) {
      this._pendingSelectName = pending;
      this._pendingTabName = pendingTab;
      if (this._tryConsumePendingSelect) this._tryConsumePendingSelect();
    } else if (section !== 'agents') {
      this._pendingSelectName = null;
      this._pendingTabName = null;
    }
    if (this._setActiveSection) {
      this._setActiveSection(section, { writeUrl: false });
    }
  },

  init: function (sidebar, content) {
    var self = this;

    // ── Per-instance state (promoted from closure locals to this.* so
    //    serializeState reads the right values) ────────────────────────────
    self._agents = [];
    self._allTools = [];
    self._allMcpSources = [];
    self._allKnowledgeBases = [];
    self._allProviders = [];
    self._selectedAgent = null;
    self._pendingSelectName = self._pendingSelectName || null;
    self._pendingTabName = self._pendingTabName || null;
    self._createMode = false;
    self._activeSection = self._activeSection || 'agents';
    self._activeTab = self._activeTab || 'general';
    var dirty = false;
    var snapshot = '';
    // Tab handle returned by App.studio.renderAgentEditor — used for
    // imperative activate(tabId) calls after hydrate.
    var tabHandle = null;

    // ── beforeunload listener (F5 leg 04) ────────────────────────────────
    //
    // Registered ONCE at init() time (init runs once per area lifetime,
    // gated by app.js's initialized[areaId] check). The closure `dirty` flag
    // is the sole gate — when in another area, dirty is false because the
    // editor isn't mounted; when in studio with unsaved changes, dirty is
    // true and the listener calls e.preventDefault(); e.returnValue = ''.
    //
    // **Do NOT remove on deactivate()** — deactivate runs on every cross-area
    // transition, so removing there would silently break tab-close
    // protection after a chat → studio → chat round-trip. The closure-flag
    // gate handles all cases.
    //
    // Modern browsers ignore the custom returnValue string and show a
    // generic "Leave site?" dialog; setting returnValue = '' is the modern
    // incantation that triggers the prompt.
    window.addEventListener('beforeunload', function (e) {
      if (dirty) {
        e.preventDefault();
        e.returnValue = '';
        return '';
      }
    });

    var TOOL_CATEGORIES = {
      'Filesystem': ['read_file', 'write_file', 'list_dir'],
      'Execution': ['shell', 'python_exec', 'run_tests'],
      'Web': ['http_request', 'web_search'],
      'System': ['git', 'self_deploy', 'rollback', 'restart', 'mission_control', 'memory']
    };

    // ── Layout: sidebar = section-nav only; main panel hosts both the
    // section-content (tile grid / Knowledge / Tools) and the editor,
    // toggled via .is-hidden based on whether an agent is being edited.
    sidebar.innerHTML = '<div class="studio-section-nav"></div>';
    var sectionNavEl = sidebar.querySelector('.studio-section-nav');

    content.innerHTML =
      '<div class="studio-section-content"></div>' +
      '<div class="studio-editor"></div>';
    var sectionContentEl = content.querySelector('.studio-section-content');
    var editorEl = content.querySelector('.studio-editor');

    var agentsContentEl = document.createElement('div');
    agentsContentEl.className = 'studio-agents-content';
    agentsContentEl.innerHTML =
      '<div class="studio-page-header">' +
        '<h1 class="studio-page-title">Agents</h1>' +
        '<button class="btn-outlined-cyan new-agent-btn" type="button" data-testid="new-agent-btn">' +
          App.icon('square-pen') + '<span>New Agent</span>' +
        '</button>' +
      '</div>' +
      '<div class="agent-tile-grid" role="listbox" aria-label="Agents"></div>';
    var agentListEl = agentsContentEl.querySelector('.agent-tile-grid');
    var newAgentBtn = agentsContentEl.querySelector('.new-agent-btn');

    // ── Section navigation ─────────────────────────────────────────────

    App.studio.renderSectionNav(sectionNavEl, self._activeSection, {
      onSelect: function (section) {
        // F5 leg 04: dirty gate — only fires when leaving the
        // Agents-section + selected-agent context. Knowledge → Tools
        // transitions (no editor mounted) navigate immediately.
        var commit = function () { setActiveSection(section); };
        var inEditingContext = self._activeSection === 'agents' && self._selectedAgent;
        if (dirty && inEditingContext) {
          App.confirmDialog({ onConfirm: commit });
        } else {
          commit();
        }
      }
    });

    function renderAgentsSection() {
      sectionContentEl.innerHTML = '';
      sectionContentEl.appendChild(agentsContentEl);
      renderAgentList();
    }

    function renderKnowledgeSection() {
      sectionContentEl.innerHTML = '';
      App.studio.renderKnowledgeStub(sectionContentEl);
    }

    function renderToolsSection() {
      sectionContentEl.innerHTML = '';
      App.studio.renderToolsStub(sectionContentEl);
    }

    function setActiveSection(section, options) {
      options = options || {};
      var writeUrl = options.writeUrl !== false; // default true
      self._activeSection = section;
      App.studio.updateActiveSection(sectionNavEl, section);
      if (section === 'knowledge') {
        renderKnowledgeSection();
      } else if (section === 'tools') {
        renderToolsSection();
      } else {
        renderAgentsSection();
      }
      updateContentVisibility();
      if (writeUrl) writeUrl_();
    }
    self._setActiveSection = setActiveSection;

    // Section-content (tile grid / Knowledge / Tools stub) and the editor
    // share the main panel; only one is visible at a time. The editor takes
    // over when an agent is selected or being created in the Agents section;
    // otherwise section-content is the visible child.
    function updateContentVisibility() {
      var inEditor = self._activeSection === 'agents' &&
                     (self._selectedAgent || self._createMode);
      sectionContentEl.classList.toggle('is-hidden', !!inEditor);
      editorEl.classList.toggle('is-hidden', !inEditor);
    }

    // ── Single URL-write call site ──────────────────────────────────────
    function writeUrl_() {
      if (window.App && window.App.router) {
        App.router.replaceSub(self.serializeState());
      }
    }
    self._writeUrl = writeUrl_;

    // ── Data fetching ────────────────────────────────────────────────

    function fetchAgents() { return fetch('/api/agents').then(function (r) { return r.json(); }); }
    function fetchTools() { return fetch('/api/tools').then(function (r) { return r.json(); }); }
    function fetchMcpSources() { return fetch('/api/mcp-sources').then(function (r) { return r.json(); }); }
    function fetchKnowledgeBases() { return fetch('/api/knowledge-bases').then(function (r) { return r.json(); }); }
    function fetchProviders() { return fetch('/api/providers').then(function (r) { return r.json(); }); }

    function loadAll() {
      return Promise.all([fetchAgents(), fetchTools(), fetchMcpSources(), fetchKnowledgeBases(), fetchProviders()])
        .then(function (results) {
          self._agents = results[0];
          self._allTools = results[1];
          self._allMcpSources = results[2];
          self._allKnowledgeBases = results[3];
          self._allProviders = results[4];
          if (self._activeSection === 'agents') renderAgentList();
        });
    }

    // ── Agents tile grid rendering (F5 leg 02) ──────────────────────────
    function renderAgentList() {
      agentListEl.innerHTML = '';
      var agents = self._agents;
      if (agents.length === 0 && !self._createMode) {
        var empty = document.createElement('div');
        empty.className = 'empty-state agent-empty';
        empty.setAttribute('data-testid', 'agent-empty');
        empty.textContent = 'No agents yet. Click New Agent to create one.';
        agentListEl.appendChild(empty);
        return;
      }
      for (var i = 0; i < agents.length; i++) {
        (function (agent) {
          var isActive = self._selectedAgent && self._selectedAgent.name === agent.name && !self._createMode;

          var tileEl = document.createElement('button');
          tileEl.type = 'button';
          tileEl.className = 'agent-tile agent-item' + (isActive ? ' active' : '');
          tileEl.setAttribute('data-testid', 'agent-item');
          tileEl.setAttribute('role', 'option');
          tileEl.dataset.name = agent.name;
          tileEl.setAttribute('aria-selected', isActive ? 'true' : 'false');
          tileEl.setAttribute('aria-label', agent.name);

          var nameSpan = document.createElement('span');
          nameSpan.className = 'agent-tile-name';
          nameSpan.textContent = agent.name;
          tileEl.appendChild(nameSpan);

          var descSpan = document.createElement('span');
          descSpan.className = 'agent-tile-description';
          descSpan.textContent = agent.description || '';
          tileEl.appendChild(descSpan);

          var metaSpan = document.createElement('span');
          metaSpan.className = 'agent-tile-meta';
          var providerLabel = '';
          if (agent.provider_config_id) {
            for (var pi = 0; pi < self._allProviders.length; pi++) {
              if (self._allProviders[pi].id === agent.provider_config_id) {
                providerLabel = self._allProviders[pi].name || '';
                break;
              }
            }
          }
          var modelLabel = agent.llm_model || '';
          if (providerLabel && modelLabel) {
            metaSpan.textContent = providerLabel + ' · ' + modelLabel;
          } else if (providerLabel) {
            metaSpan.textContent = providerLabel;
          } else if (modelLabel) {
            metaSpan.textContent = modelLabel;
          } else {
            metaSpan.textContent = 'no provider';
          }
          tileEl.appendChild(metaSpan);

          tileEl.onclick = function () { selectAgent(agent); };
          tileEl.addEventListener('keydown', function (e) {
            if (e.target !== tileEl) return;
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              selectAgent(agent);
            }
          });

          agentListEl.appendChild(tileEl);
        })(agents[i]);
      }
    }

    // ── Agent selection ──────────────────────────────────────────────

    // F5 leg 04: doSelect / doEnterCreateMode — extracted bodies past the
    // dirty-check so the App.confirmDialog onConfirm callback can invoke
    // the real navigation. The async dialog pattern requires the guard to
    // dispatch the dialog and let onConfirm proceed (the synchronous
    // window.confirm guard-and-return pattern doesn't translate directly).
    function doSelect(agent) {
      // Preserve the current tab when re-selecting the same agent (e.g.,
      // when activate() triggers a refresh after the user is already
      // viewing this agent on a non-default tab). Honor any pending tab
      // from hydrate, otherwise keep the existing _activeTab; only reset
      // to 'general' on a genuine agent change.
      var sameAgent = self._selectedAgent && self._selectedAgent.name === agent.name && !self._createMode;
      var tabToActivate;
      if (self._pendingTabName) {
        tabToActivate = self._pendingTabName;
      } else if (sameAgent) {
        tabToActivate = self._activeTab || 'general';
      } else {
        tabToActivate = 'general';
      }
      self._createMode = false;
      self._selectedAgent = agent;
      dirty = false;
      self._pendingTabName = null;
      self._activeTab = tabToActivate;
      if (self._activeSection !== 'agents') {
        setActiveSection('agents', { writeUrl: false });
      }
      renderAgentList();
      renderEditor(agent);
      updateContentVisibility();
      writeUrl_();
    }

    function selectAgent(agent) {
      if (dirty) {
        App.confirmDialog({ onConfirm: function () { doSelect(agent); } });
        return;
      }
      doSelect(agent);
    }

    function doEnterCreateMode() {
      self._createMode = true;
      self._selectedAgent = null;
      self._activeTab = 'general';
      dirty = false;
      if (self._activeSection !== 'agents') {
        setActiveSection('agents', { writeUrl: false });
      }
      renderAgentList();
      renderEditor(null);
      updateContentVisibility();
      writeUrl_();
    }

    function enterCreateMode() {
      if (dirty) {
        App.confirmDialog({ onConfirm: doEnterCreateMode });
        return;
      }
      doEnterCreateMode();
    }

    // ── Editor rendering ─────────────────────────────────────────────

    function renderEmptyEditor() {
      editorEl.innerHTML = '';
      tabHandle = null;
    }

    // F5 leg 03: renderEditor delegates to the agent-editor module which
    // builds the header + action cluster + tablist + three tab panels.
    // Per-tab render helpers populate the panels; the General tab is mounted
    // synchronously so existing form-field tests find their selectors
    // immediately.
    function renderEditor(agent) {
      var isCreate = !agent;
      tabHandle = App.studio.renderAgentEditor(editorEl, agent, self._allProviders, {
        initialTab: self._activeTab || 'general',
        onBack: handleBack,
        onDelete: handleDeleteEditor,
        onSave: function () { save(isCreate); },
        onCancel: function () { cancelEdit(); },
        onTabChange: function (tabId) { setActiveTab(tabId); },
        // F5 leg 05: tabs in the same agent share the form's dirty state, so
        // switching tabs does NOT lose unsaved data — no confirmation prompt.
        // The dirty gate still fires on Back, section nav, and hash-route
        // navigation to a different agent.
        onTestProvider: testProvider,
        toolCategories: TOOL_CATEGORIES,
        allTools: self._allTools,
        onChange: checkDirty
      });

      // Wire field-level dirty tracking + provider-change side-effects.
      // These run AFTER the editor DOM is in place.
      wireEditorEvents(isCreate, agent || {
        provider_config_id: self._allProviders.length > 0 ? self._allProviders[0].id : null,
        llm_model: ''
      });

      // Dirty snapshot baseline.
      snapshot = getFormSnapshot();
    }

    // setActiveTab — analogous to setActiveSection. Updates _activeTab,
    // calls the tab handle's activate (which swaps panel visibility +
    // aria-selected + roving tabindex), writes URL via _writeUrl unless
    // the caller opts out (hydrate path).
    function setActiveTab(tab, options) {
      options = options || {};
      var writeUrl = options.writeUrl !== false;
      self._activeTab = tab;
      if (tabHandle && tabHandle.getActive() !== tab) {
        tabHandle.activate(tab);
      }
      if (writeUrl) writeUrl_();
    }
    self._setActiveTab = setActiveTab;

    // ── Action-cluster handlers ──────────────────────────────────────

    // Back: clear selection, exit create mode, return to #studio/agents.
    // F5 leg 04: dirty gate via App.confirmDialog. The async restructure
    // mirrors selectAgent / enterCreateMode — extract the body past the
    // dirty-check into doHandleBack so the dialog's onConfirm callback can
    // invoke it.
    function doHandleBack() {
      self._selectedAgent = null;
      self._createMode = false;
      dirty = false;
      self._activeTab = 'general';
      renderEmptyEditor();
      renderAgentList();
      updateContentVisibility();
      writeUrl_();
    }

    function handleBack() {
      if (dirty) {
        App.confirmDialog({ onConfirm: doHandleBack });
        return;
      }
      doHandleBack();
    }

    // Cancel discards in-progress edits and restores the editor to the
    // current agent's saved state. In create-mode, it returns to the tile
    // grid (there is no saved state to revert to). The button only fires
    // when dirty (disabled by checkDirty otherwise), so no extra guard.
    function cancelEdit() {
      if (self._createMode) {
        doHandleBack();
        return;
      }
      if (self._selectedAgent) {
        renderEditor(self._selectedAgent);
        dirty = false;
        checkDirty();
      }
    }

    // Editor's Delete button — KEEPS its inline two-step flow at the
    // pre-leg-03 spec exactly. Class state on .delete-btn.confirm,
    // capital-D label "Confirm Delete?", 3s revert timer, second-click
    // DELETE. NOT migrated to App.confirmDelete (intentional — that helper
    // is for the tile X-button; the editor flow keeps the capital-D label
    // for test_flow_agent_crud.py:73 stability).
    function handleDeleteEditor(deleteBtn) {
      var name = self._selectedAgent ? self._selectedAgent.name : null;
      if (!name) return;
      if (deleteBtn.classList.contains('confirm')) {
        fetch('/api/agents/' + encodeURIComponent(name), { method: 'DELETE' })
          .then(function () {
            self._selectedAgent = null;
            dirty = false;
            return loadAll();
          })
          .then(function () {
            if (self._agents.length > 0) {
              selectAgent(self._agents[0]);
            } else {
              renderEmptyEditor();
              updateContentVisibility();
              writeUrl_();
            }
          });
        return;
      }
      deleteBtn.classList.add('confirm');
      deleteBtn.textContent = 'Confirm Delete?';
      setTimeout(function () {
        deleteBtn.classList.remove('confirm');
        deleteBtn.textContent = 'Delete Agent';
      }, 3000);
    }

    // Test provider — POST /api/providers/{id}/test with empty body.
    // Reads the LIVE #studio-provider value (NOT cfg.provider_config_id)
    // so unsaved provider changes are testable.
    function testProvider() {
      var providerSelect = editorEl.querySelector('#studio-provider');
      var resultSpan = editorEl.querySelector('.test-result');
      if (!providerSelect || !providerSelect.value) {
        if (resultSpan) {
          resultSpan.className = 'test-result test-result-fail';
          resultSpan.textContent = '✗ No provider selected';
        }
        return;
      }
      var providerId = providerSelect.value;
      if (resultSpan) {
        resultSpan.className = 'test-result';
        resultSpan.textContent = 'Testing…';
      }
      fetch('/api/providers/' + encodeURIComponent(providerId) + '/test', { method: 'POST' })
        .then(function (r) {
          return r.json().then(function (body) { return { ok: r.ok, body: body }; });
        })
        .then(function (res) {
          var detail = (res.body && res.body.detail) || '';
          var isOk = res.ok && res.body && res.body.status === 'ok';
          if (resultSpan) {
            resultSpan.className = 'test-result ' + (isOk ? 'test-result-ok' : 'test-result-fail');
            resultSpan.textContent = (isOk ? '✓ ' : '✗ ') + detail;
          }
          if (isOk) {
            App.showFlash(editorEl, detail || 'Provider test ok');
          } else {
            // Bypass the local one-arg showFlash wrapper which drops the
            // error flag — call App.showFlash directly with isError=true
            // to preserve the error styling.
            App.showFlash(editorEl, detail || 'Provider test failed', true);
          }
        })
        .catch(function (err) {
          var msg = (err && err.message) || 'Network error';
          if (resultSpan) {
            resultSpan.className = 'test-result test-result-fail';
            resultSpan.textContent = '✗ ' + msg;
          }
          App.showFlash(editorEl, msg, true);
        });
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

      if (loadingEl) loadingEl.textContent = 'Loading models…';

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

    function recomputeTestDisabled() {
      var providerSelect = editorEl.querySelector('#studio-provider');
      var testBtn = editorEl.querySelector('.test-provider-btn');
      if (!testBtn) return;
      testBtn.disabled = !providerSelect || !providerSelect.value;
    }

    function wireEditorEvents(isCreate, cfg) {
      // Dirty tracking on all inputs (skips disabled Advanced stubs).
      var inputs = editorEl.querySelectorAll('.field-input, .field-textarea, .field-select, .tool-toggle');
      for (var i = 0; i < inputs.length; i++) {
        if (inputs[i].disabled) continue;
        inputs[i].addEventListener('input', checkDirty);
        inputs[i].addEventListener('change', checkDirty);
      }

      // Provider change → fetch models + clear VRAM warning + recompute Test btn.
      // The Test-button-disabled recompute chains into the existing change
      // handler (locality preferred over a second listener).
      var providerSelect = editorEl.querySelector('#studio-provider');
      if (providerSelect) {
        providerSelect.addEventListener('change', function () {
          var modelSelect = editorEl.querySelector('#studio-model');
          if (modelSelect) modelSelect.selectedIndex = 0;
          clearVramWarning();
          fetchModelsForProvider(providerSelect.value);
          recomputeTestDisabled();
        });
        if (cfg.provider_config_id) {
          var modelSelect = editorEl.querySelector('#studio-model');
          if (modelSelect && cfg.llm_model) modelSelect.dataset.pendingValue = cfg.llm_model;
          fetchModelsForProvider(cfg.provider_config_id);
        }
      }

      // Model change → debounced VRAM check.
      var modelInput = editorEl.querySelector('#studio-model');
      if (modelInput) {
        modelInput.addEventListener('change', debouncedVramCheck);
        if (cfg.llm_model && cfg.provider_config_id) {
          debouncedVramCheck();
        }
      }
    }

    // ── Dirty tracking ───────────────────────────────────────────────

    function getFormSnapshot() {
      var data = collectFormData();
      return JSON.stringify(data);
    }

    function checkDirty() {
      var current = getFormSnapshot();
      dirty = current !== snapshot;
      // `disabled` is the single source of truth for both Save and Cancel.
      var saveBtn = editorEl.querySelector('.save-btn');
      if (saveBtn) saveBtn.disabled = !dirty;
      var cancelBtn = editorEl.querySelector('.cancel-btn');
      if (cancelBtn) cancelBtn.disabled = !dirty;
    }

    // ── Form data collection ─────────────────────────────────────────
    //
    // collectFormData queries by [data-field="..."] selectors which work
    // regardless of which tab/panel the field lives in. Fields that span
    // tabs (provider, model, system_prompt, max_iterations on General;
    // tool toggles on Tools) are all reachable from editorEl.
    function collectFormData() {
      var data = {};
      var fields = editorEl.querySelectorAll('.field-input, .field-textarea, .field-select');
      for (var i = 0; i < fields.length; i++) {
        var f = fields[i];
        if (f.disabled) continue; // skip Advanced-stub disabled inputs
        var key = f.dataset.field;
        if (!key) continue;
        if (key === 'max_iterations') {
          data[key] = parseInt(f.value, 10) || 20;
        } else if (key === 'provider_config_id') {
          data[key] = f.value || null;
        } else {
          data[key] = f.value;
        }
      }

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

      // Connections (chips) — Tools tab does not currently render chips
      // (MCP/KB attach is a future-flight stub), so this collects whatever
      // chip-areas exist (none in F5 leg 03; future legs may add them).
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
          if (errorEl) errorEl.textContent = 'Name is required.';
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
            self._createMode = false;
            return loadAll().then(function () {
              var found = null;
              for (var i = 0; i < self._agents.length; i++) {
                if (self._agents[i].name === created.name) { found = self._agents[i]; break; }
              }
              if (found) selectAgent(found);
              showFlash('Agent created');
            });
          })
          .catch(function (err) {
            if (errorEl) errorEl.textContent = err.message;
          });
      } else {
        var name = self._selectedAgent.name;
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
            self._selectedAgent = updated;
            return loadAll().then(function () {
              var found = null;
              for (var i = 0; i < self._agents.length; i++) {
                if (self._agents[i].name === updated.name) { found = self._agents[i]; break; }
              }
              if (found) {
                self._selectedAgent = found;
                renderEditor(found);
                showFlash('Saved');
              }
            });
          })
          .catch(function (err) {
            if (errorEl) errorEl.textContent = err.message;
          });
      }
    }

    // ── Helpers ──────────────────────────────────────────────────────

    var showFlash = function (msg) { App.showFlash(editorEl, msg); };

    var formatBytes = App.formatBytes;
    var vramCheckTimer = null;

    function getSelectedProviderType() {
      var providerSelect = editorEl.querySelector('#studio-provider');
      if (!providerSelect || !providerSelect.value) return null;
      for (var i = 0; i < self._allProviders.length; i++) {
        if (String(self._allProviders[i].id) === String(providerSelect.value)) {
          return self._allProviders[i];
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

          for (var i = 0; i < running.length; i++) {
            var runName = running[i].name || running[i].model || '';
            if (runName === modelName || runName.split(':')[0] === modelName.split(':')[0]) {
              clearVramWarning();
              return;
            }
          }

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

          var totalLoaded = 0;
          var loadedCount = running.length;
          for (var k = 0; k < running.length; k++) {
            totalLoaded += running[k].size_vram || 0;
          }

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

    function tryConsumePendingSelect() {
      if (!self._pendingSelectName) return;
      if (!self._agents || self._agents.length === 0) return;
      var target = null;
      for (var i = 0; i < self._agents.length; i++) {
        if (self._agents[i].name === self._pendingSelectName) { target = self._agents[i]; break; }
      }
      self._pendingSelectName = null;
      if (target && (!self._selectedAgent || self._selectedAgent.name !== target.name)) {
        selectAgent(target);
      }
    }

    newAgentBtn.addEventListener('click', enterCreateMode);

    self._refresh = function () {
      loadAll().then(function () {
        if (self._selectedAgent) {
          var found = null;
          for (var i = 0; i < self._agents.length; i++) {
            if (self._agents[i].name === self._selectedAgent.name) { found = self._agents[i]; break; }
          }
          if (found) selectAgent(found);
          else if (self._agents.length > 0) selectAgent(self._agents[0]);
          else renderEmptyEditor();
        }
      });
    };
    self._tryConsumePendingSelect = function () { tryConsumePendingSelect(); };

    setActiveSection(self._activeSection || 'agents', { writeUrl: false });

    loadAll().then(function () {
      if (self._activeSection === 'agents') {
        if (self._pendingSelectName) {
          tryConsumePendingSelect();
          if (self._selectedAgent) return;
        }
        // Bare #studio/agents shows the tile grid in the main panel; no
        // agent is auto-selected. The user picks a tile (or +) to enter
        // the editor.
        renderEmptyEditor();
        updateContentVisibility();
      }
    });
  },

  activate: function () {
    if (this._refresh) this._refresh();
  },
  deactivate: function () {}
});
