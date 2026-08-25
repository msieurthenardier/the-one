// App.studio.renderSelfConfigurationTab — agent-editor Self-configuration
// tab content (M21 F01 L02).
//
// A single enable/disable control + status line. Enabling mints a
// per-agent credential and creates a `streamable-http` MCP source row that
// the agent's own client presents to reach a loopback endpoint the
// platform serves itself — off by default for every agent (mission
// constraint). This tab is the ONLY place that toggles it; the row's
// attach checkbox on the MCPs tab renders checked-and-disabled (see
// mcps-tab.js) so the operator's per-tool controls still govern individual
// capabilities from there.
//
// Public API:
//   App.studio.renderSelfConfigurationTab(panel, agent, callbacks)
//     panel      — DOM element (the Self-configuration tabpanel)
//     agent      — AgentConfig object, or null in create-mode
//     callbacks  — { fetchStatus(name) -> Promise<{enabled, ...}>,
//                    onEnable(name) -> Promise<{enabled, ...}>,
//                    onDisable(name) -> Promise<{enabled, ...}> }
//
// Save-flow note: unlike every other tab, this control does NOT participate
// in collectFormData()/dirty-tracking — enable/disable are immediate API
// calls (mirrors the Danger Zone's Delete/Purge buttons), not form fields
// staged for the Save button.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function renderSelfConfigurationTab(panel, agent, callbacks) {
    callbacks = callbacks || {};
    panel.innerHTML = '';

    if (!agent) {
      var notice = document.createElement('p');
      notice.className = 'empty-state';
      notice.setAttribute('data-testid', 'self-configuration-save-first');
      notice.textContent = 'Save the agent first to enable self-configuration.';
      panel.appendChild(notice);
      return;
    }

    var section = document.createElement('div');
    section.className = 'editor-section';

    var title = document.createElement('div');
    title.className = 'section-title';
    title.textContent = 'Self-configuration';
    section.appendChild(title);

    var description = document.createElement('p');
    description.className = 'self-configuration-description';
    description.textContent = 'When enabled, this agent can read its own configuration ' +
      'and revise its own description and system prompt through a dedicated MCP source. ' +
      'The operator’s per-tool controls on the MCPs tab still govern which capabilities ' +
      'the agent can actually use.';
    section.appendChild(description);

    var statusLine = document.createElement('p');
    statusLine.className = 'self-configuration-status';
    statusLine.setAttribute('data-testid', 'self-configuration-status');
    statusLine.setAttribute('role', 'status');
    statusLine.setAttribute('aria-live', 'polite');
    statusLine.textContent = 'Loading…';
    section.appendChild(statusLine);

    var errorLine = document.createElement('p');
    errorLine.className = 'self-configuration-error';
    errorLine.setAttribute('data-testid', 'self-configuration-error');
    errorLine.hidden = true;
    section.appendChild(errorLine);

    var toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.className = 'btn-outlined-primary self-configuration-toggle-btn';
    toggleBtn.setAttribute('data-testid', 'self-configuration-toggle-btn');
    toggleBtn.disabled = true;
    toggleBtn.textContent = '…';
    section.appendChild(toggleBtn);

    panel.appendChild(section);

    function renderState(enabled) {
      statusLine.textContent = enabled
        ? 'Self-configuration is enabled for this agent.'
        : 'Self-configuration is disabled for this agent.';
      toggleBtn.textContent = enabled ? 'Disable' : 'Enable';
      toggleBtn.disabled = false;
      errorLine.hidden = true;
      errorLine.textContent = '';
      toggleBtn.onclick = function () {
        var action = enabled ? callbacks.onDisable : callbacks.onEnable;
        if (!action) return;
        toggleBtn.disabled = true;
        action(agent.name).then(function (result) {
          renderState(!!(result && result.enabled));
        }).catch(function (err) {
          errorLine.hidden = false;
          errorLine.textContent = 'Failed to ' + (enabled ? 'disable' : 'enable') +
            ' self-configuration: ' + (err && err.message ? err.message : String(err));
          toggleBtn.disabled = false;
        });
      };
    }

    if (!callbacks.fetchStatus) {
      renderState(false);
      return;
    }
    callbacks.fetchStatus(agent.name).then(function (status) {
      renderState(!!(status && status.enabled));
    }).catch(function () {
      statusLine.textContent = 'Unable to load self-configuration status.';
    });
  }

  window.App.studio.renderSelfConfigurationTab = renderSelfConfigurationTab;
})();
